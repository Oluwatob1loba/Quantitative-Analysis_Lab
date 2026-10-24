"""
rino_episode.py — RINO V3.1 episode machine (Python port, pure logic)

Pine anchors
  C:L2066-L2081  V3Manipulation UDT (frozen episode record)
  C:L2101-L2102  roll-top zombie guard (pending.candles > lookback -> retire)
  C:L2111-L2128  opening pairwise sweep scan + frozen bounds + close references
  C:L2134        per-roll aggregation (count, H/L/C, side flags vs frozen bounds)
  C:L2173-L2184  completion: strict close-reference crossing, both directions
  C:L1897-L1920  f_v3PriorityDir (Anchor1..3 then TF1; High-only -> LONG pref)
Spec anchors
  P4.4  window packet ([2] offset), opening predicates, frozen display bounds,
        completion, priority enumeration
  DR-04 window = preceding N complete candles; PDOL scan inside it
  DR-05 frozen bounds; aggregate episode OHLC
  DR-06 closeRefLow = highest swept Low / closeRefHigh = lowest swept High
  DR-07 opening scan precedes the Section-19 touch pass
  DR-18 roll-top count retirement; main+1 completion semantics

PURITY CONTRACT
  No I/O, no pandas, no imports from rino_* modules. The orchestrator
  (rino_engine.py, next module) calls process_roll() once per confirmed TF1
  candle, in P3 statement order:
      1. DOL native-close consumption            (rino_dol)
      2. EPISODE process_roll                    (this module)
      3. DOL touch pass for this roll            (rino_dol)   <-- DR-07
      4. owner monitor / provider publish        (rino_setup / rino_gate)
  DR-07 is honored structurally: the opening scan happens inside step 2,
  so a level swept this roll is still state-0 when scanned.

STANDING RULINGS
  D-PY-15  no bias/CHoCH anywhere in this module.
  D-PY-17  attribution (candle OPEN) and detection (candle CLOSE-END) are
           distinct stamps on every emitted event.
"""

from dataclasses import dataclass, field
from typing import Callable, Optional


# --------------------------------------------------------------------------
# Data structures (frozen-source shapes, P4.4)
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class ClosedCandle:
    """One confirmed native TF1 candle, with both timestamps (D-PY-17)."""
    o: float
    h: float
    l: float
    c: float
    origin: int        # attribution stamp: candle OPEN time (ms)
    boundary: int      # detection stamp: candle CLOSE-END time (ms)


@dataclass(frozen=True)
class SweepableDraw:
    """A covered, state-0 PDOL level candidate for the opening scan."""
    price: float
    side: str          # "High" | "Low"  (level polarity, i.e. isHighLow)
    origin: int        # native candle open time of the level
    tf_key: str        # e.g. "1D", "1W" — native key of the level's layer
    covered: bool = True


@dataclass(frozen=True)
class PriorityLayer:
    """One layer for f_v3PriorityDir, in slot order: A1, A2, A3, TF1."""
    enabled: bool
    tf_key: str
    draws: tuple       # tuple[SweepableDraw], covered state-0 PDOLs of this layer


@dataclass
class Episode:
    """Frozen pending episode (C:L2066-L2081, P4.4)."""
    reference_time: int                    # preceding-window origin
    range_high: float                      # frozen display bound (DR-05)
    range_low: float
    origin: int                            # opening sweep candle OPEN
    o: float
    h: float
    l: float
    c: float
    boundary: int                          # last aggregated candle CLOSE-END
    candles: int = 1
    swept_high: bool = False
    swept_low: bool = False
    close_ref_low: Optional[float] = None   # max swept eligible Low (DR-06)
    close_ref_high: Optional[float] = None  # min swept eligible High


@dataclass(frozen=True)
class Completion:
    """One qualified direction at episode completion (enumeration order)."""
    direction: int      # +1 LONG | -1 SHORT
    variant: str        # "Window" (1 candle) | "WindowMulti"
    episode: Episode


# --------------------------------------------------------------------------
# f_v3PriorityDir (C:L1897-L1920, DR-08) — enumeration preference only
# --------------------------------------------------------------------------

def priority_direction(ref: float, layers: list, tf1_key: str) -> int:
    """First enabled layer (A1,A2,A3,TF1) with a one-sided PDOL field wins.

    High-only  -> +1 (LONG preferred: liquidity lies above)
    Low-only   -> -1 (SHORT preferred)
    Both sides -> nearer to ref wins; exact tie -> 0 and the loop FALLS
                  THROUGH to the next layer (frozen semantics, C:L1909-1912).
    Anchors whose key duplicates TF1 are skipped (frozen dedup).
    """
    for idx, layer in enumerate(layers):
        is_tf1 = idx == len(layers) - 1
        if not layer.enabled:
            continue
        if not is_tf1 and layer.tf_key == tf1_key:
            continue                       # duplicate anchor slot
        near_high = None
        near_low = None
        for d in layer.draws:
            if not d.covered:
                continue
            if d.side == "High":
                near_high = d.price if near_high is None else min(near_high, d.price)
            else:
                near_low = d.price if near_low is None else max(near_low, d.price)
        has_h = near_high is not None
        has_l = near_low is not None
        if has_h and not has_l:
            return 1
        if has_l and not has_h:
            return -1
        if has_h and has_l:
            dh = abs(near_high - ref)
            dl = abs(near_low - ref)
            if dh < dl:
                return 1
            if dl < dh:
                return -1
            # exact tie -> prio stays 0, fall through to next layer
    return 0


# --------------------------------------------------------------------------
# Episode machine
# --------------------------------------------------------------------------

class EpisodeMachine:
    """One pending TF1 episode at most (P4.4). Constant-size record."""

    def __init__(self, lookback: int, sub_lookback: int,
                 event_sink: Optional[Callable[[dict], None]] = None):
        self.lookback = lookback
        self.window = min(sub_lookback, lookback)   # DR-04: N = min(sub, main)
        self.pending: Optional[Episode] = None
        self.events: list = []
        self._sink = event_sink

    # -- event helper (D-PY-17: attribution vs detection on every event) ----
    def _emit(self, kind: str, attribution: int, detection: int, **fields):
        ev = {"kind": kind, "attribution": attribution, "detection": detection,
              **fields}
        self.events.append(ev)
        if self._sink:
            self._sink(ev)
        return ev

    # -- main entry, once per confirmed TF1 roll ----------------------------
    def process_roll(self, candle: ClosedCandle,
                     window_origin: Optional[int],
                     sweepable: list,
                     priority_layers: list,
                     tf1_key: str = "1D") -> list:
        """Returns the list[Completion] if the episode completed this roll,
        else []. Side effects: pending episode state + events."""

        # -- zombie guard (C:L2101-L2102, DR-18) ----------------------------
        if self.pending is not None and self.pending.candles > self.lookback:
            self._emit("EPISODE_RETIRED", self.pending.origin,
                       self.pending.boundary, candles=self.pending.candles)
            self.pending = None

        ep = self.pending

        # -- opening scan (C:L2108-L2128) ------------------------------------
        if ep is None:
            if window_origin is None:
                return []
            in_window = [d for d in sweepable
                         if window_origin <= d.origin < candle.origin]
            lows = sorted(d.price for d in in_window
                          if d.side == "Low" and d.covered
                          and candle.l < d.price)     # strict sweep (DR-06)
            highs = sorted(d.price for d in in_window
                           if d.side == "High" and d.covered
                           and candle.h > d.price)
            if not lows and not highs:
                return []
            ep = Episode(
                reference_time=window_origin,
                range_high=max(highs) if highs else candle.h,   # DR-05 fallback
                range_low=min(lows) if lows else candle.l,
                origin=candle.origin,
                o=candle.o, h=candle.h, l=candle.l, c=candle.c,
                boundary=candle.boundary,
                candles=1,
                swept_high=bool(highs),
                swept_low=bool(lows),
                close_ref_low=max(lows) if lows else None,      # DR-06
                close_ref_high=min(highs) if highs else None,
            )
            self.pending = ep
            self._emit("EPISODE_OPENED", ep.origin, candle.boundary,
                       swept_low=ep.swept_low, swept_high=ep.swept_high,
                       close_ref_low=ep.close_ref_low,
                       close_ref_high=ep.close_ref_high,
                       range_low=ep.range_low, range_high=ep.range_high)

        # -- aggregation (C:L2134) -------------------------------------------
        else:
            ep.h = max(ep.h, candle.h)
            ep.l = min(ep.l, candle.l)
            ep.c = candle.c
            ep.boundary = candle.boundary
            ep.candles += 1
            ep.swept_high = ep.swept_high or (candle.h > ep.range_high)
            ep.swept_low = ep.swept_low or (candle.l < ep.range_low)

        # -- completion (C:L2173-L2184): strict crossing of stored reference --
        long_ready = (ep.swept_low and ep.close_ref_low is not None
                      and ep.c > ep.close_ref_low)
        short_ready = (ep.swept_high and ep.close_ref_high is not None
                       and ep.c < ep.close_ref_high)

        if not (long_ready or short_ready):
            return []

        prio = priority_direction((ep.h + ep.l) / 2.0, priority_layers, tf1_key)
        first = prio if prio != 0 else 1
        variant = "Window" if ep.candles == 1 else "WindowMulti"
        completions = []
        for cand in (first, -first):
            qualifies = ((cand == 1 and long_ready)
                         or (cand == -1 and short_ready))
            if qualifies:
                completions.append(Completion(direction=cand, variant=variant,
                                              episode=ep))
        self._emit("EPISODE_COMPLETED", ep.origin, ep.boundary,
                   directions=[c.direction for c in completions],
                   variant=variant, candles=ep.candles,
                   close_ref_low=ep.close_ref_low,
                   close_ref_high=ep.close_ref_high)
        self.pending = None
        return completions
