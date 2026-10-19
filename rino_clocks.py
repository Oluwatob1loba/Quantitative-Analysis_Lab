"""RINO clocks - native bucketing, roll detection, confirmed-data availability,
and the server->UTC+1 bridge (D-PY-08). Confirmed OHLC becomes visible on the FIRST
chart bar of the NEXT native candle (lookahead_on + [1]). Buckets match the MT5
terminal: Sunday bars from 22:00 server fold into Monday's D1/W1 candle (D-PY-09)."""
import pandas as pd

_INTRADAY_MINUTES = {"1min": 1, "5min": 5, "15min": 15, "30min": 30,
                     "1h": 60, "2h": 120, "3h": 180, "4h": 240,
                     "6h": 360, "8h": 480, "12h": 720}
FOLD_SUNDAY_FROM_HOUR = 22
SUNDAY = 6


def _folded(ts: pd.Timestamp, fold_sunday: bool) -> pd.Timestamp:
    if fold_sunday and ts.weekday() == SUNDAY and ts.hour >= FOLD_SUNDAY_FROM_HOUR:
        return ts + pd.Timedelta(days=1)
    return ts


def bucket_start(ts: pd.Timestamp, tf: str, fold_sunday: bool = True) -> pd.Timestamp:
    tf = tf.strip()
    if tf in _INTRADAY_MINUTES:
        m = _INTRADAY_MINUTES[tf]
        mins = ts.hour * 60 + ts.minute
        return ts.normalize() + pd.Timedelta(minutes=mins - mins % m)
    if tf == "1D":
        return _folded(ts, fold_sunday).normalize()
    if tf == "1W":
        day = _folded(ts, fold_sunday)
        return (day - pd.Timedelta(days=day.weekday())).normalize()
    if tf == "1M":
        return ts.normalize().replace(day=1)
    if tf == "3M":
        q = ((ts.month - 1) // 3) * 3 + 1
        return ts.normalize().replace(month=q, day=1)
    raise ValueError(f"unsupported timeframe: {tf}")


def attach_native(df: pd.DataFrame, tf: str, prefix: str) -> pd.DataFrame:
    """Adds {prefix}_bucket, {prefix}_roll and the CONFIRMED PREVIOUS native candle's
    OHLCV, visible from each chart bar forward. The developing candle is never exposed."""
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    buckets = pd.Series([bucket_start(ts, tf) for ts in df.index],
                        index=df.index, name=f"{prefix}_bucket")
    roll = buckets.ne(buckets.shift(1))
    roll.iloc[0] = True
    g = df.groupby(buckets).agg(open=("open", "first"), high=("high", "max"),
                                low=("low", "min"), close=("close", "last"),
                                tick_volume=("tick_volume", "sum"))
    mapped = g.shift(1).loc[buckets]
    out = df.copy()
    out[buckets.name] = buckets
    out[f"{prefix}_roll"] = roll
    for c in ("open", "high", "low", "close", "tick_volume"):
        out[f"{prefix}_{c}"] = mapped[c].to_numpy()
    return out


# ---- server -> fixed UTC+1 bridge (D-PY-08, assumption A-2: MetaQuotes-Demo = EU DST) ----
def _last_sunday(year: int, month: int) -> int:
    end = pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(1)
    return end.day - ((end.weekday() - SUNDAY) % 7)


def server_utc_offset_hours(ts: pd.Timestamp) -> int:
    """EU rule in SERVER wall time: +3 from last-Sun-Mar 04:00 until last-Sun-Oct 04:00,
    else +2. The repeated 03:00 hour on fall-back Sunday is assigned to summer; the FX
    market is closed through both switch moments, so no traded bar is ever ambiguous."""
    summer_start = pd.Timestamp(ts.year, 3, _last_sunday(ts.year, 3), 4)
    summer_end = pd.Timestamp(ts.year, 10, _last_sunday(ts.year, 10), 4)
    return 3 if summer_start <= ts < summer_end else 2


def server_to_utc1(ts: pd.Timestamp) -> pd.Timestamp:
    return ts - pd.Timedelta(hours=server_utc_offset_hours(ts) - 1)


def key_time_at(ts_server: pd.Timestamp, key_times) -> str:
    """Name of the key-time window containing this server timestamp, in fixed UTC+1."""
    u = server_to_utc1(ts_server)
    mins = u.hour * 60 + u.minute
    for w in key_times:
        if w.start_min <= mins < w.end_min:
            return w.name
    return ""