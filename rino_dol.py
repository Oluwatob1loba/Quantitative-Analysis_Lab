"""RINO DOL lifecycle (CORE §19 / P4.3 port).
Roles from completed-candle body direction; monotone disturbance states
0 untouched -> 1 swept (wick equality-or-better) -> 2 consumed (strict native close
beyond stored polarity); no reverse transitions. Untouched SDOL emits nothing.
TF1 draws: available at their stamp roll; cannot be swept on their own creation roll.
Extra anchors: own-native consumption, coverage established by the next complete
packet after availability. Confluence = distinct-key participating untouched covered
PDOLs within proximity. Participation = TF1, or consume-toggle, or rank above TF1.
State lives in parallel records; rino_tf1.py is untouched (additive port)."""
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from rino_clocks import attach_native, bucket_start


@dataclass
class DolRecord:
    owner: object                 # Tf1Level ref or AnchorDraw
    tf_key: str
    role: str                     # "PDOL" | "SDOL" | ""
    state: int = 0
    changed_at: Optional[pd.Timestamp] = None
    coverage: bool = True
    confluent: bool = False


@dataclass
class AnchorDraw:
    side: str
    price: float
    origin: pd.Timestamp
    available_at: pd.Timestamp
    tf_key: str
    active: bool = True
    end_time: Optional[pd.Timestamp] = None


def tf_key(tf: str) -> str:
    return tf.strip()


def near(a: float, b: float, mintick: float, tol_pct: float) -> bool:
    return 100.0 * abs(a - b) / max(abs(a), abs(b), mintick) <= tol_pct


class DolEngine:
    def __init__(self, cfg, mintick: float):
        self.cfg = cfg
        self.mintick = mintick
        self.records: Dict[Tuple[str, str, str], DolRecord] = {}   # (tf_key, origin, side)
        self.anchors: List[AnchorDraw] = []
        self.events: List[dict] = []
        self.first_observed: Optional[pd.Timestamp] = None
        self.max_pool = 0
        self._tf1eng = None
        self._tf1_origins = []

    # ---------------------------------------------------------------- helpers
    def _emit(self, rec: DolRecord, origin, detected):
        if rec.role == "SDOL" and rec.state == 0:
            return
        self.events.append(dict(kind="DOL_STATE", tf=rec.tf_key, origin=origin,
                                detected=detected, role=rec.role,
                                price=rec.owner.price, state=rec.state))

    def _price_side(self, rec):
        return rec.owner.price, rec.owner.side if hasattr(rec.owner, "side") else rec.owner.kind

    def _participates(self, tfk: str) -> bool:
        from rino_clocks import bucket_start  # rank via config tf strings
        rank = {"1D": 1.0, "4h": 4 / 24.0, "1W": 7.0, "1M": 30.4375, "3M": 91.3125}
        r_tf1 = rank.get(tf_key(self.cfg.tf1), 1.0)
        r_lvl = rank.get(tfk, 1.0)
        return tfk == tf_key(self.cfg.tf1) or self.cfg.tf2_draws_in_tf1_target_math or r_lvl > r_tf1

    def _recompute_confluence(self):
        # Retention view computed HERE so confluence scope is correct even if the
        # record dict still holds evicted owners (BUG-PY-02 hardening). CORE iterates
        # the pruned tf1Levels/v3ExtraDols arrays; we mirror that set directly.
        tf1_alive = {id(lv) for lv in self._tf1eng.levels} if self._tf1eng is not None else set()
        alive_ids = tf1_alive | {id(d) for d in self.anchors}
        pool = [r for r in self.records.values()
                if id(r.owner) in alive_ids
                and r.role == "PDOL" and r.state == 0 and r.coverage
                and self._participates(r.tf_key)]
        self.max_pool = max(getattr(self, "max_pool", 0), len(pool))
        tol = getattr(self.cfg, "v3_dol_proximity_pct", 0.1)
        for r in pool:
            r.confluent = any(o is not r and o.tf_key != r.tf_key
                              and near(o.owner.price, r.owner.price, self.mintick, tol)
                              for o in pool)
        pool_ids = {id(r) for r in pool}          # id-set, NOT dataclass equality
        for r in self.records.values():
            if id(r) not in pool_ids:
                r.confluent = False

    # ---------------------------------------------------------------- driver
    def run(self, df: pd.DataFrame, tf1eng):
        self._tf1eng = tf1eng
        cfg = self.cfg
        self.first_observed = df.index[0]
        if "tf1_roll" not in df.columns:
            df = attach_native(df, cfg.tf1, "tf1")
        anchor_cols = []
        for i, a in enumerate(cfg.anchors):
            if not a.enabled or tf_key(a.tf) == tf_key(cfg.tf1):
                continue
            p = f"a{i}"
            df = attach_native(df, a.tf, p)
            anchor_cols.append((i, a, p))
        mask = df["tf1_roll"]
        for _, a, p in anchor_cols:
            mask = mask | df[f"{p}_roll"]
        for t, row in df[mask].iterrows():
            if row["tf1_roll"]:
                self._on_tf1(t, row, tf1eng)
            for i, a, p in anchor_cols:
                if row[f"{p}_roll"]:
                    self._on_anchor(t, row, a, p)
        return df

    def _on_tf1(self, t, row, tf1eng):
        c, h, l = row["tf1_close"], row["tf1_high"], row["tf1_low"]
        origin = row["tf1_cbucket"]
        # Temporal retention view (BUG-PY-03): cutoff as of THIS roll, from origins seen
        # so far — mirrors Pine's array.remove at eviction (C:L568..L603) without reading
        # the TF1 engine's final state, which would leak future knowledge (DR-02).
        self._tf1_origins.append(origin)
        lb = self.cfg.tf1_lookback
        cutoff = self._tf1_origins[-lb] if len(self._tf1_origins) >= lb else None
        if cutoff is not None:
            for key in [k for k, r in self.records.items()
                        if r.tf_key == tf_key(self.cfg.tf1) and r.owner.origin < cutoff]:
                del self.records[key]
        # Roles for the two levels stamped from this confirmed candle (P4.3).
        direction = "up" if c > row["tf1_open"] else "down" if c < row["tf1_open"] else "neutral"
        for lv in tf1eng.levels:
            if lv.origin == origin and lv.kind in ("High", "Low"):
                role = "" if direction == "neutral" else (
                    "PDOL" if (direction == "up") == (lv.kind == "High") else "SDOL")
                self.records[(tf_key(self.cfg.tf1), str(origin), lv.kind)] = DolRecord(
                    owner=lv, tf_key=tf_key(self.cfg.tf1), role=role, coverage=True)
        # Consumption then sweep, per-roll packet only (C:L519..L531, C:L1673..L1683).
        # NO is_active guard: the close that invalidates is the close that consumes, and
        # is_active is a final-state flag that would leak end-of-history knowledge here.
        for key, rec in list(self.records.items()):
            if rec.tf_key != tf_key(self.cfg.tf1) or rec.state >= 2 or rec.role == "":
                continue
            lv = rec.owner
            broke = (lv.kind == "High" and c > lv.price) or (lv.kind == "Low" and c < lv.price)
            if broke:
                rec.state, rec.changed_at = 2, t
                self._emit(rec, origin, t)
                continue
            if rec.state == 0 and origin > lv.available_at:
                touched = (lv.kind == "High" and h >= lv.price) or (lv.kind == "Low" and l <= lv.price)
                if touched:
                    rec.state, rec.changed_at = 1, t
                    self._emit(rec, origin, t)
        self._recompute_confluence()

    def _on_anchor(self, t, row, a, p):
        c, h, l = row[f"{p}_close"], row[f"{p}_high"], row[f"{p}_low"]
        origin = row[f"{p}_cbucket"]
        key = tf_key(a.tf)
        for d in self.anchors:
            if d.tf_key != key or not d.active:
                continue
            rec = self.records.get((key, str(d.origin), d.side))
            if rec is None:
                continue
            rec.coverage = True
            if rec.state >= 2:
                continue
            broke = (d.side == "High" and c > d.price) or (d.side == "Low" and c < d.price)
            if broke:
                d.active, d.end_time = False, origin
                rec.state, rec.changed_at = 2, t
                self._emit(rec, origin, t)
            elif rec.state == 0 and origin >= d.available_at:
                touched = (d.side == "High" and h >= d.price) or (d.side == "Low" and l <= d.price)
                if touched:
                    rec.state, rec.changed_at = 1, t
                    self._emit(rec, origin, t)
        direction = "up" if c > row[f"{p}_open"] else "down" if c < row[f"{p}_open"] else "neutral"
        if direction != "neutral":
            for side, price in (("High", h), ("Low", l)):
                role = "PDOL" if (direction == "up") == (side == "High") else "SDOL"
                d = AnchorDraw(side, price, origin, t, key)
                self.anchors.append(d)
                self.records[(key, str(origin), side)] = DolRecord(
                    owner=d, tf_key=key, role=role,
                    coverage=(t >= self.first_observed))
        # per-slot retention
        origins = sorted({d.origin for d in self.anchors if d.tf_key == key})
        if len(origins) > a.candles > 0:
            cut = origins[-a.candles]
            self.anchors = [d for d in self.anchors
                            if not (d.tf_key == key and d.origin < cut)]
        self._recompute_confluence()
        alive_draws = {id(d) for d in self.anchors}
        for key in [k for k, r in self.records.items()
                    if isinstance(r.owner, AnchorDraw) and id(r.owner) not in alive_draws]:
            del self.records[key]