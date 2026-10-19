"""RINO TF2 structure (CORE §8 / P4.2 port, Layer-A transcription, bias-free per D-PY-15).
3-bar wick pivots on confirmed TF2 candles (pivot at B-2 knowable at the roll bar of B);
alternation with Minor retention (supersession demotes the pending candidate; equal-price
loser = incoming, D-PY-13); opposite-side arrival confirms pending as Major; close-only
invalidation of Major+Minor (wick never retires, equality never breaks); memory-horizon
pruning (TF1-anchored or manual, D-PY-14) plus pending-candidate expiry; Critical
classification with proximity %, deferral while the parent TF1 candle develops, retry on
TF1 rolls, latch once resolved. NO bias state, NO bootstrap, NO protected swing, NO CHoCH:
the architect defines trend/CHoCH/BOS later; BiasProvider is the reserved seam."""
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional
from rino_clocks import attach_native, bucket_start


@dataclass
class Tf2Swing:
    side: str                          # "High" | "Low"
    price: float
    origin: pd.Timestamp               # TF2 bucket of the pivot candle
    confirmed_at: pd.Timestamp
    klass: str = "Pending"             # Pending -> Major | Minor
    demoted_by: str = ""               # "supersession" | "equal" | "loss"
    is_critical: Optional[bool] = None
    critical_at: Optional[pd.Timestamp] = None
    parent_bucket: Optional[pd.Timestamp] = None
    end_time: Optional[pd.Timestamp] = None   # attributed: breaking candle's OPEN
    observed_at: Optional[pd.Timestamp] = None  # knowable: roll bar
    end_reason: str = ""               # "invalidated" | "evicted"
    broken_by_close: Optional[float] = None

    @property
    def is_active(self) -> bool:
        return self.end_time is None


class BiasProvider:
    """Reserved plug-in point (D-PY-15). The architect's future Layer-B definition
    (trend / CHoCH / BOS inside the DOL logic) subclasses this, implements update(),
    and reads engine.swings / engine.majors. Until then bias is the constant
    'undefined', update() is a no-op, and events() is empty."""
    bias = "undefined"

    def update(self, engine, t, confirmed_close):
        return None

    def events(self) -> List:
        return []


class Tf2Structure:
    def __init__(self, cfg, bias_provider: Optional[BiasProvider] = None):
        self.cfg = cfg
        self.bias_provider = bias_provider or BiasProvider()
        self.swings: List[Tf2Swing] = []        # all resolved records (Major/Minor)
        self.active: List[Tf2Swing] = []        # currently live ones (bounded by horizon)
        self.majors: List[Tf2Swing] = []        # confirmation order
        self.pending_critical: List[Tf2Swing] = []
        self.tf1_hist: List = []                # (bucket, h, l, c)
        self.tf2_hist: List = []                # (bucket, o, h, l, c)
        self._tf1_by_bucket = {}
        self.counters = {"pivots": 0, "supersession": 0, "equal_loser": 0,
                         "opposite_confirm": 0, "critical": 0, "deferred": 0,
                         "pending_expired": 0}
        self.cutoff: Optional[pd.Timestamp] = None
        self._pend_high: Optional[Tf2Swing] = None
        self._pend_low: Optional[Tf2Swing] = None

    # ------------------------------------------------------------------ helpers
    def _end(self, s: Tf2Swing, end_time, observed, reason, broken=None):
        s.end_time, s.observed_at, s.end_reason = end_time, observed, reason
        s.broken_by_close = broken
        if s in self.active:
            self.active.remove(s)

    def _prune(self, cut: pd.Timestamp, t: pd.Timestamp):
        self.cutoff = cut
        for s in list(self.active):
            if s.origin < cut:
                self._end(s, t, t, "evicted")
        for name in ("_pend_high", "_pend_low"):
            pend = getattr(self, name)
            if pend is not None and pend.origin < cut:
                setattr(self, name, None)
                self.counters["pending_expired"] += 1

    def _critical(self, s: Tf2Swing, t: pd.Timestamp):
        s.parent_bucket = bucket_start(s.origin, self.cfg.tf1)
        developing = bucket_start(t, self.cfg.tf1)
        if s.parent_bucket >= developing:            # parent still developing: defer
            self.pending_critical.append(s)
            self.counters["deferred"] += 1
        else:
            self._resolve(s, t)

    def _resolve(self, s: Tf2Swing, t: pd.Timestamp):
        rec = self._tf1_by_bucket.get(s.parent_bucket)
        if rec is None:                              # parent not confirmed yet: stay pending
            if s not in self.pending_critical:
                self.pending_critical.append(s)
            return
        h, l = rec
        prox = min(abs(s.price - h), abs(s.price - l)) / s.price * 100.0
        s.is_critical = prox <= self.cfg.tf2_critical_proximity_pct
        s.critical_at = t
        if s.is_critical:
            self.counters["critical"] += 1
        if s in self.pending_critical:
            self.pending_critical.remove(s)

    def classify_break(self, side: str, price: float) -> Optional[str]:
        """Break-class fact for a swept TF2 level: Critical > Major > Minor (bias-free)."""
        for s in reversed(self.swings):
            if s.side == side and abs(s.price - price) <= 1e-12:
                if s.is_critical:
                    return "Critical"
                return s.klass if s.klass in ("Major", "Minor") else None
        return None

    # ------------------------------------------------------------------ arrivals
    def _arrive(self, side: str, price: float, origin: pd.Timestamp, t: pd.Timestamp):
        self.counters["pivots"] += 1
        s = Tf2Swing(side, price, origin, t)
        if side == "High":
            pend, other = self._pend_high, "_pend_low"
        else:
            pend, other = self._pend_low, "_pend_high"
        if pend is None:
            if side == "High":
                self._pend_high = s
            else:
                self._pend_low = s
        elif (price > pend.price) if side == "High" else (price < pend.price):
            pend.klass, pend.demoted_by = "Minor", "supersession"   # supersession
            self.swings.append(pend); self.active.append(pend)
            self.counters["supersession"] += 1
            self._critical(pend, t)
            if side == "High":
                self._pend_high = s
            else:
                self._pend_low = s
        else:
            s.klass = "Minor"
            if price == pend.price:                                  # equal-price loser
                s.demoted_by = "equal"
                self.counters["equal_loser"] += 1
            else:
                s.demoted_by = "loss"
            self.swings.append(s); self.active.append(s)
            self._critical(s, t)
        opp = getattr(self, other)                                   # opposite confirms Major
        if opp is not None:
            opp.klass = "Major"
            self.swings.append(opp); self.active.append(opp); self.majors.append(opp)
            self.counters["opposite_confirm"] += 1
            self._critical(opp, t)
            setattr(self, other, None)

    # ------------------------------------------------------------------ rolls
    def _on_tf2(self, t, o, h, l, c, bucket):
        self.tf2_hist.append((bucket, o, h, l, c))
        if len(self.tf2_hist) >= 3:
            left, mid, right = self.tf2_hist[-3], self.tf2_hist[-2], self.tf2_hist[-1]
            if mid[2] > left[2] and mid[2] > right[2]:
                self._arrive("High", mid[2], mid[0], t)
            if mid[3] < left[3] and mid[3] < right[3]:
                self._arrive("Low", mid[3], mid[0], t)
        for s in list(self.active):                                  # close-only invalidation
            broke = (s.side == "High" and c > s.price) or (s.side == "Low" and c < s.price)
            if broke:
                self._end(s, bucket, t, "invalidated", c)            # end = breaking candle OPEN
        if not self.cfg.tf2_anchor_to_tf1:                           # manual horizon (D-PY-14)
            origins = [x[0] for x in self.tf2_hist]
            if len(origins) >= self.cfg.tf2_manual_lookback:
                self._prune(origins[-self.cfg.tf2_manual_lookback], t)
        self.bias_provider.update(self, t, c)                        # no-op until Layer B

    def _on_tf1(self, t, bucket, h, l, c):
        self.tf1_hist.append((bucket, h, l, c))
        self._tf1_by_bucket[bucket] = (h, l)
        for s in list(self.pending_critical):                        # retry deferred Criticals
            if s.parent_bucket < bucket:
                self._resolve(s, t)
        if self.cfg.tf2_anchor_to_tf1:                               # TF1-anchored horizon
            origins = [x[0] for x in self.tf1_hist]
            if len(origins) >= self.cfg.tf1_lookback:
                self._prune(origins[-self.cfg.tf1_lookback], t)

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        if "tf1_roll" not in df.columns:
            df = attach_native(df, self.cfg.tf1, "tf1")
        if "tf2_roll" not in df.columns:
            df = attach_native(df, self.cfg.tf2, "tf2")
        for t, row in df[df["tf1_roll"] | df["tf2_roll"]].iterrows():
            if row["tf1_roll"]:
                self._on_tf1(t, row["tf1_bucket"], row["tf1_high"], row["tf1_low"], row["tf1_close"])
            if row["tf2_roll"]:
                self._on_tf2(t, row["tf2_open"], row["tf2_high"], row["tf2_low"],
                             row["tf2_close"], row["tf2_bucket"])
        return df

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([vars(s) for s in self.swings])