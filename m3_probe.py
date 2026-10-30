"""m3_probe.py - full-context dump for ONE disputed M3 trade.
Usage: python m3_probe.py SYMBOL YYYY-MM-DD DIRECTION
Prints: the stamped trade row (all quadrants), the M3 setup row, the M2 setup
row, and the lake bars around entry/exit - so stop provenance is decided by
data, not theory. The audit detail constrains the truth: for an SL exit at xi,
engine_stop must be <= bar[xi].high and > every bar in (ft, xi). If the M3 and
M2 setup rows disagree on stop for the same origin, that is the bug.
"""
import sys
import numpy as np
import pandas as pd
from lab import load, pip_size

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "GBPUSD"
DAY = sys.argv[2] if len(sys.argv) > 2 else "2024-11-26"
DIRECTION = int(sys.argv[3]) if len(sys.argv) > 3 else -1
mt = pip_size(SYMBOL) / 10

found = False
for tag in ("trades", "trades_m2", "trades_m3"):
    try:
        tr = pd.read_csv(f"reports/{tag}_{SYMBOL}.csv", parse_dates=["origin"])
    except FileNotFoundError:
        continue
    row = tr[(tr.origin == pd.Timestamp(DAY)) & (tr.direction == DIRECTION)]
    print(f"=== {tag} stamped trade rows ===")
    if len(row):
        found = True
        print(row.to_string(index=False))
if not found:
    print("=== NO trade rows in any ledger ===")

for tag, path in (("M3", f"reports/setups_{SYMBOL}.csv"),
                  ("M2", f"reports/setups_m2_{SYMBOL}.csv")):
    try:
        st = pd.read_csv(path, parse_dates=["origin", "availableAt"])
    except FileNotFoundError:
        print(f"=== {tag} setups: file missing ==="); continue
    s = st[(st.origin == pd.Timestamp(DAY)) & (st.direction == DIRECTION)]
    print(f"=== {tag} setup row ===")
    if len(s):
        cols = ["actionable", "setupClass", "grade", "manHigh", "manLow", "manOpen",
                "manClose", "stop", "t1", "t1Flipped", "target", "zoneLow",
                "zoneHigh", "breakClass", "breakAt", "availableAt"]
        cols = [c for c in cols if c in s.columns]
        print(s[cols].to_string(index=False))
    else:
        print("no row")

if len(row):
    t = row.iloc[0]
    df = load(SYMBOL)
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    ei, xi = int(t.entry_i), int(t.exit_i)
    lo = max(0, ei - 2); hi = min(len(df), xi + 3)
    seg = df.iloc[lo:hi]
    print(f"=== lake bars {lo}..{hi-1} (entry {ei}, exit {xi}) ===")
    for i in range(lo, hi):
        r = df.iloc[i]
        mark = ""
        if i == ei: mark = " <== entry"
        if i == xi: mark = " <== recorded exit"
        print(f"{i}  {df.index[i]}  O {r.open:.10f} H {r.high:.10f} "
              f"L {r.low:.10f} C {r.close:.10f} spr {r.spread}{mark}")
