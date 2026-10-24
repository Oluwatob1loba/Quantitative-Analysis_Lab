import pandas as pd
from lab import load
from rino_clocks import attach_native, bucket_start, server_utc_offset_hours, key_time_at
from rino_config import KEY_TIMES

# 1. DST rule sanity (2026: switches 29 Mar and 25 Oct)
checks = [
    (pd.Timestamp(2026, 1, 15, 12), 2), (pd.Timestamp(2026, 3, 29, 2), 2),
    (pd.Timestamp(2026, 3, 29, 4), 3), (pd.Timestamp(2026, 7, 1, 12), 3),
    (pd.Timestamp(2026, 10, 25, 2), 3), (pd.Timestamp(2026, 10, 25, 4), 2),
]
for ts, want in checks:
    got = server_utc_offset_hours(ts)
    print(f"offset {ts} -> {got} {'OK' if got == want else 'MISMATCH want ' + str(want)}")
print("key-time probe (server 16:30 summer):", key_time_at(pd.Timestamp(2026, 7, 1, 16, 30), KEY_TIMES))

# 2. Bucketing, rolls, no-lookahead
df = load("EURUSD")
for tf, prefix, step_days in (("1D", "d", 1), ("1W", "w", 7)):
    d = attach_native(df, tf, prefix)
    rolls = d[d[f"{prefix}_roll"]]
    print(f"\n{tf}: {len(rolls):,} native candles | first roll {rolls.index[0]} | last {rolls.index[-1]}")
    if tf == "1W":
        assert all(b.weekday() == 0 for b in rolls[f"{prefix}_bucket"]), "week bucket not Monday!"
    sun = df[(df.index.weekday == 6) & (df.index.hour >= 22)]
    if len(sun) and tf == "1D":
        b = bucket_start(sun.index[0], tf)
        print(f"  Sunday-evening fold: {sun.index[0]} -> bucket {b.date()} (expect Monday)")
        assert b.weekday() == 0
    bar = rolls.index[len(rolls) // 2]
    b = bucket_start(bar, tf)
    prev = df[(df.index >= b - pd.Timedelta(days=step_days)) & (df.index < b)]
    ok1 = abs(d.loc[bar, f"{prefix}_high"] - prev["high"].max()) < 1e-9
    prev_bar = d.index[d.index.get_loc(bar) - 1]
    # TEST-PY-03: window the EXPOSED confirmed bucket itself. Calendar-day offsets break across
    # weekends (Monday's prior window is empty) — the bar exposes the previous native candle.
    b_prev_conf = d.loc[prev_bar, f"{prefix}_cbucket"]
    prev2 = df[(df.index >= b_prev_conf) & (df.index < b_prev_conf + pd.Timedelta(days=step_days))]
    ok2 = abs(d.loc[prev_bar, f"{prefix}_high"] - prev2["high"].max()) < 1e-9
    print(f"  @roll: exposed high = confirmed prev bucket -> {'MATCH' if ok1 else 'MISMATCH'}")
    print(f"  @bar-before-roll: one step behind, no lookahead -> {'MATCH' if ok2 else 'MISMATCH'}")
print("\nClocks verified.")