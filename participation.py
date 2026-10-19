"""Participation layer: candle-based proxies for aggression, absorption, displacement.
These are PROXIES from OHLC + tick volume, not true order flow.
The lab validates them statistically before any EA is allowed to believe them."""
import numpy as np
import pandas as pd


def add_participation_layer(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    candle_range = df["high"] - df["low"]
    body_size = (df["close"] - df["open"]).abs()

    # 1. Aggression / displacement: share of the candle's range that is body
    df["aggression"] = np.where(candle_range > 0, body_size / candle_range, 0.5)

    # 2. Close Location Value: who won the candle (-1 bears .. +1 bulls)
    df["clv"] = np.where(
        candle_range > 0,
        ((df["close"] - df["low"]) - (df["high"] - df["close"])) / candle_range,
        0.0,
    )

    # 3. Volume z-score (rolling 20): was participation unusual?
    vol_mean = df["tick_volume"].rolling(20).mean()
    vol_std = df["tick_volume"].rolling(20).std().replace(0, 1)
    df["vol_zscore"] = (df["tick_volume"] - vol_mean) / vol_std

    # Dataset-relative threshold (research v1; a live version will use rolling quantiles)
    aggr_thr = df["aggression"].quantile(0.75)

    df["is_aggressive"] = df["aggression"] > aggr_thr
    df["strong_displacement"] = df["is_aggressive"] & (df["vol_zscore"] > 1.0)
    df["is_absorption"] = (
        (df["vol_zscore"] > 1.5) & (df["aggression"] < 0.3) & (candle_range > 0)
    )
    return df