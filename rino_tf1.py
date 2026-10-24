"""RINO TF1 anatomy (CORE §7 / P4.2 port, rev 2).
High/Low stamped per confirmed TF1 candle with fixed polarity; invalidation is
strict close-only on TF1's own candles (wick never retires, equality never breaks).
Mid stored separately, NEVER price-invalidated (count-cap eviction only).
Historical Open stamps are NOT created (Show Open is display-only in CORE).
Dual timestamps: end_time = breaking candle's OPEN; observed_at = roll bar."""
import pandas as pd
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Tf1Level:
    kind: str                    # "High" | "Low" | "Mid"
    price: float
    polarity: str                # "resistance" | "support" | "" (Mid)
    origin: pd.Timestamp
    available_at: pd.Timestamp
    end_time: Optional[pd.Timestamp] = None
    end_reason: str = ""         # "invalidated" | "evicted"
    observed_at: Optional[pd.Timestamp] = None
    broken_by_close: Optional[float] = None

    @property
    def is_active(self) -> bool:
        return self.end_time is None


class Tf1Anatomy:
    def __init__(self, cfg):
        self.cfg = cfg
        self.levels: List[Tf1Level] = []   # High/Low only
        self.mids: List[Tf1Level] = []     # separate; never price-invalidated

    def _window(self, kind: str) -> int:
        return self.cfg.tf1_mid_lookback if kind == "Mid" else self.cfg.tf1_lookback

    def run(self, df: pd.DataFrame) -> pd.DataFrame:
        p = "tf1"
        if f"{p}_roll" not in df.columns:
            from rino_clocks import attach_native
            df = attach_native(df, self.cfg.tf1, p)
        for t, row in df[df[f"{p}_roll"]].iterrows():
            h, l, c = row[f"{p}_high"], row[f"{p}_low"], row[f"{p}_close"]
            origin = row[f"{p}_cbucket"]      # confirmed candle's own open (D-PY-17)
            if pd.isna(c):
                continue
            # 1. strict close-only invalidation, by stored polarity, High/Low only
            for lv in self.levels:
                if not lv.is_active:
                    continue
                broke = (lv.polarity == "resistance" and c > lv.price) or \
                        (lv.polarity == "support" and c < lv.price)
                if broke:
                    lv.end_time = origin          # attributed: breaking candle's OPEN
                    lv.observed_at = t            # knowable: this roll bar
                    lv.end_reason = "invalidated"
                    lv.broken_by_close = c
            # 2. stamp High/Low with fixed polarity
            self.levels.append(Tf1Level("High", h, "resistance", origin, t))
            self.levels.append(Tf1Level("Low", l, "support", origin, t))
            # 3. Mid: separate array, count-cap eviction only
            self.mids.append(Tf1Level("Mid", (h + l) / 2.0, "", origin, t))
            wm = self._window("Mid")
            for lv in (self.mids[:-wm] if wm > 0 else self.mids[:]):
                if lv.is_active:
                    lv.end_time, lv.observed_at, lv.end_reason = t, t, "evicted"
            # 4. High/Low retention by main lookback, per kind
            wh = self._window("High")
            for kind in ("High", "Low"):
                active = [lv for lv in self.levels if lv.is_active and lv.kind == kind]
                for lv in (active[:-wh] if wh > 0 else active):
                    lv.end_time, lv.observed_at, lv.end_reason = t, t, "evicted"
        return df

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame([vars(lv) for lv in self.levels + self.mids])