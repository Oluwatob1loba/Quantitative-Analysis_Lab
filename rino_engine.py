"""
rino_engine.py — RINO orchestrator (P3 statement order, research stages only).

Wires the certified modules per confirmed TF1 roll, in frozen CORE order:
    1. TF1 native-close consumption of draws      (rino_dol._on_tf1_consume, C:L519..L531)
    2. EPISODE machine                            (rino_episode, opening scan C:L2113..L2128)
    3. DOL touch pass (wick, state 0 -> 1)        (rino_dol._on_tf1_touch, C:L2137..L2145)
    4. extra-anchor consumption/creation          (rino_dol._on_anchor, as DolEngine.run)
Rendering, collision registries, status tables: never ported (display-only).

DR-07 is structural: the `between` hook runs the episode scan AFTER consumption and
BEFORE touching, exactly as frozen CORE.

EXTENT NOTES (D-PY-16):
- OPENING SCAN (D-PY-20 + D-PY-22, architect rulings): sweep = FLAT, any in-window
  TF1 candle extreme, PDOL or SDOL, eligible while not closed through (state 0/1;
  re-sweeps register). Admission = DRAW-ANCHORED: undisturbed covered PDOLs on TF1
  AND ACTIVE anchors set the direction; swept side is the opposite one; the close
  confirms; no undisturbed draw -> no event. Diverges from frozen C:L2115-2120
  (PDOL-only, TF1-only scan, state-0-only): the port follows the rulings; logged.
- QUEUED (D-PY-21 taxonomy): TF2 sweep through a draw = operator CAUTION (not a
  kill); TF1-swept PDOLs are dead for TARGETING but alive for setup events; TF1
  close-through consumes and targeting moves to the next undisturbed PDOL.
- f_v3PriorityDir (live source) admits covered PDOLs that are state-0 OR disturbed
  at/after the episode origin (dolChangedAt >= origin). _priority_layers mirrors it.
- ADD-01 rev 2 (D-PY-06): key-time raid = first LTF bar inside the episode span whose
  range crosses the pool level (the close reference), mapped to fixed UTC+1 windows.

Setup construction (targets / POI gate / class / rank / owner / TSM direction gate)
is rino_setup.py, the next module; this engine emits completed EPISODES (raw setups).
"""

import os
import pandas as pd

from lab import load
from rino_config import config_for
from rino_clocks import key_time_at
from rino_tf1 import Tf1Anatomy
from rino_dol import DolEngine, tf_key
from rino_episode import ClosedCandle, SweepableDraw, PriorityLayer, EpisodeMachine

SYMBOL = "EURUSD"
MINTICK = 1e-5          # EURUSD family; JPY family uses 1e-3


class RinoEngine:
    def __init__(self, cfg, mintick=MINTICK):
        self.cfg = cfg
        self.mintick = mintick
        self.tf1 = Tf1Anatomy(cfg)
        self.dol = DolEngine(cfg, mintick)
        self.ep = EpisodeMachine(cfg.tf1_lookback, cfg.tf1_sub_lookback)
        self.tf1_origins = []        # confirmed cbuckets, roll order
        self.completions = []        # completed-episode records (raw setups)
        self._df = None              # M15 frame kept for the ADD-01 raid lookup

    # ------------------------------------------------------------------ roll hook
    def _episode_step(self, t, row):
        """Runs between DOL consumption and the DOL touch pass (DR-07 midpoint)."""
        origin = row["tf1_cbucket"]
        self.tf1_origins.append(origin)
        N = min(self.cfg.tf1_sub_lookback, self.cfg.tf1_lookback)
        window_origin = (self.tf1_origins[-(N + 2)]      # time[N+1]: candle before window
                         if len(self.tf1_origins) >= N + 2 else None)
        candle = ClosedCandle(o=row["tf1_open"], h=row["tf1_high"],
                              l=row["tf1_low"], c=row["tf1_close"],
                              origin=origin, boundary=t)
        k1 = tf_key(self.cfg.tf1)
        # DPY-20/22 (architect rulings): the sweep starts FLAT — any in-window TF1 candle
        # extreme, PDOL or SDOL, eligible while NOT closed through (state 0 OR 1: the
        # re-sweep case, "the setup candle gets swept one more time before the move").
        # Admission is DRAW-ANCHORED (D-PY-22): undisturbed covered PDOLs on TF1 AND
        # ACTIVE anchors set the expected direction; the swept side is the opposite one;
        # no undisturbed draw -> no event. Deliberate divergence from frozen C:L2115-2120.
        active_anchor_keys = {tf_key(a.tf) for a in self.cfg.anchors
                              if a.enabled and tf_key(a.tf) != k1}
        draws = [r for r in self.dol.records.values()
                 if r.role == "PDOL" and r.state == 0 and r.coverage
                 and (r.tf_key == k1 or r.tf_key in active_anchor_keys)]
        admit = set()
        for r in draws:
            side = r.owner.kind if hasattr(r.owner, "kind") else r.owner.side
            if side == "High":
                admit.add(1)     # draw above -> LONG on low sweeps
            else:
                admit.add(-1)    # draw below -> SHORT on high sweeps
        sweepable = [SweepableDraw(price=r.owner.price, side=r.owner.kind,
                                   origin=r.owner.origin, tf_key=k1)
                     for r in self.dol.records.values()
                     if r.tf_key == k1 and r.role != ""
                     and r.state in (0, 1) and r.coverage]
        layers = self._priority_layers(origin)
        for comp in self.ep.process_roll(candle, window_origin, sweepable,
                                         layers, tf1_key=k1, admit_dirs=admit):
            self.completions.append(self._record(comp, candle))

    def _priority_layers(self, episode_origin):
        """Live-source f_v3PriorityDir predicate: covered PDOLs state-0 OR disturbed
        at/after the episode origin, per layer in slot order A1,A2,A3,TF1."""
        k1 = tf_key(self.cfg.tf1)
        layers = []

        def side_of(owner):
            return owner.kind if hasattr(owner, "kind") else owner.side  # Tf1Level | AnchorDraw

        def draws_for(key):
            return tuple(SweepableDraw(price=r.owner.price, side=side_of(r.owner),
                                       origin=r.owner.origin, tf_key=r.tf_key)
                         for r in self.dol.records.values()
                         if r.tf_key == key and r.role == "PDOL" and r.coverage
                         and (r.state == 0 or (r.changed_at is not None
                                               and r.changed_at >= episode_origin)))

        for a in self.cfg.anchors:
            layers.append(PriorityLayer(enabled=a.enabled and tf_key(a.tf) != k1,
                                        tf_key=tf_key(a.tf), draws=draws_for(tf_key(a.tf))))
        layers.append(PriorityLayer(True, k1, draws_for(k1)))
        return layers

    # ------------------------------------------------------------------ ADD-01 raid
    def _key_time_raid(self, rec):
        """First LTF bar inside the episode span whose range crosses the pool level
        (close reference), mapped onto the fixed-UTC+1 key-time windows."""
        span = self._df.loc[rec["origin"]:rec["availableAt"]]
        pool = rec["closeRefLow"] if rec["direction"] == 1 else rec["closeRefHigh"]
        if not len(span) or pool is None:
            return False, None, ""
        if rec["direction"] == 1:
            hit = span[span["low"] <= pool]
        else:
            hit = span[span["high"] >= pool]
        if not len(hit):
            return False, None, ""
        ts = hit.index[0]
        return True, ts, key_time_at(ts, self.cfg.key_times)

    # ------------------------------------------------------------------ record
    def _record(self, comp, candle):
        ep = comp.episode
        rec = dict(
            origin=ep.origin, availableAt=ep.boundary,   # attribution / detection (D-PY-17)
            referenceTime=ep.reference_time, direction=comp.direction, variant=comp.variant,
            manOpen=ep.o, manHigh=ep.h, manLow=ep.l, manClose=ep.c,
            rangeHigh=ep.range_high, rangeLow=ep.range_low,
            closeRefLow=ep.close_ref_low, closeRefHigh=ep.close_ref_high,
            sweptHigh=ep.swept_high, sweptLow=ep.swept_low, candles=ep.candles,
            twoSided=ep.swept_high and ep.swept_low,
        )
        hit, raid_ts, raid_window = self._key_time_raid(rec)
        rec.update(keyTimeSweep=bool(hit and raid_window != ""),
                   raidTime=raid_ts, raidWindow=raid_window)
        return rec

    # ------------------------------------------------------------------ driver
    def run(self, df):
        self._df = df
        df = self.tf1.run(df)
        df = self.dol.run(df, self.tf1, between=self._episode_step)
        return df

    def frame(self):
        return pd.DataFrame(self.completions)


if __name__ == "__main__":
    cfg = config_for(SYMBOL)
    eng = RinoEngine(cfg, MINTICK)
    eng.run(load(SYMBOL))

    ev = pd.DataFrame(eng.ep.events)
    opened = int((ev["kind"] == "EPISODE_OPENED").sum()) if len(ev) else 0
    retired = int((ev["kind"] == "EPISODE_RETIRED").sum()) if len(ev) else 0
    comp = eng.frame()
    print(f"rolls: {len(eng.tf1_origins):,}")
    print(f"episodes opened: {opened} | completed: {len(comp)} | retired: {retired}")
    if len(comp):
        print(f"directions: LONG {int((comp.direction == 1).sum())} | "
              f"SHORT {int((comp.direction == -1).sum())}")
        print(f"variants: {comp.variant.value_counts().to_dict()}")
        print(f"multi-candle: {int((comp.candles > 1).sum())} | "
              f"two-sided: {int(comp.twoSided.sum())} | "
              f"key-time raid: {int(comp.keyTimeSweep.sum())}")
        print(f"raid windows: {comp[comp.keyTimeSweep].raidWindow.value_counts().to_dict()}")
    os.makedirs("reports", exist_ok=True)
    out = f"reports/episodes_{SYMBOL}.csv"
    comp.to_csv(out, index=False)
    ev.to_csv(f"reports/episode_events_{SYMBOL}.csv", index=False)
    print(f"\nsaved {out} ({len(comp)} raw setups) + episode events ({len(ev)})")
