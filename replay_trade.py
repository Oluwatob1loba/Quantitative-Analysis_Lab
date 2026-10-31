"""replay_trade.py - re-run ONE stamped trade through the engine's exact scan
against the lake AS IT IS NOW. Settles vintage drift vs engine inconsistency:
if the replay exits at a different bar than the stamp, the stamp came from
different inputs; if it matches the stamp, the engine's logic is at fault.
Usage: python replay_trade.py SYMBOL YYYY-MM-DD DIRECTION [ledger]
       ledger = trades (default) | trades_m2 | trades_m3
"""
import sys
import numpy as np
import pandas as pd
from lab import load, pip_size

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else "GBPUSD"
DAY = sys.argv[2] if len(sys.argv) > 2 else "2024-11-26"
DIRECTION = int(sys.argv[3]) if len(sys.argv) > 3 else -1
LEDGER = sys.argv[4] if len(sys.argv) > 4 else "trades"
PARTIAL = 0.6
mt = pip_size(SYMBOL) / 10

tr = pd.read_csv(f"reports/{LEDGER}_{SYMBOL}.csv", parse_dates=["origin"])
row = tr[(tr.origin == pd.Timestamp(DAY)) & (tr.direction == DIRECTION)]
if not len(row):
    sys.exit(f"no trade in {LEDGER}_{SYMBOL} at {DAY} dir {DIRECTION}")
t = row.iloc[0]
st = pd.read_csv(f"reports/setups_{SYMBOL}.csv", parse_dates=["origin", "availableAt"])
s = st[(st.origin == pd.Timestamp(DAY)) & (st.direction == DIRECTION)].iloc[0]

df = load(SYMBOL)
if not df.index.is_monotonic_increasing:
    df = df.sort_index()
op = df["open"].to_numpy(float); hi = df["high"].to_numpy(float)
lo = df["low"].to_numpy(float); cl = df["close"].to_numpy(float)
sp = df["spread"].to_numpy(float)
n = len(df)

pos = int(np.searchsorted(df.index.values.view("int64"), s.availableAt.value))
d = DIRECTION
entry = op[pos] + d * sp[pos] * mt
stop = float(s.stop); t1 = float(s.t1) if pd.notna(s.t1) else None; t2 = float(s.target)
R = abs(entry - stop)
print(f"=== REPLAY {SYMBOL} {DAY} {d:+d} (stamped: exit_i {int(t.exit_i)}, "
      f"{t.exit_time}, {t.pnl_R:+.2f}R {t.reason}) ===")
print(f"entry bar {pos} ({df.index[pos]}) px {entry:.10f} | stop {stop:.10f} "
      f"| t1 {t1} | t2 {t2:.10f} | R {R:.10f}")
stamped_exit = int(t.exit_i)
t1_done = False; pnl = 0.0
i = pos
while i < n:
    h = hi[i]; l = lo[i]
    hit_sl = (l <= stop) if d == 1 else (h >= stop)
    hit_t1 = (not t1_done) and t1 is not None and ((h >= t1) if d == 1 else (l <= t1))
    hit_t2 = (h >= t2) if d == 1 else (l <= t2)
    flags = ""
    if hit_sl: flags += " STOP"
    if hit_t1: flags += " T1"
    if hit_t2: flags += " T2"
    if abs(i - stamped_exit) <= 3 or (flags and i >= pos):
        mark = ">>" if i == stamped_exit else "  "
        print(f"{mark} {i} {df.index[i]} O {op[i]:.10f} H {h:.10f} L {l:.10f} "
              f"C {cl[i]:.10f}{flags}")
    if hit_sl:
        pnl += ((stop - entry) if not t1_done else (1 - PARTIAL) * (stop - entry)) * d / R
        print(f"    -> REPLAY EXIT SL @ bar {i} ({df.index[i]}) px {stop:.10f} "
              f"pnl {pnl:+.4f}R | stamped exit {stamped_exit}")
        break
    if hit_t1:
        pnl += PARTIAL * (t1 - entry) * d / R
        t1_done = True
        stop = entry
        i += 1
        continue
    if hit_t2:
        pnl += (1 if not t1_done else (1 - PARTIAL)) * (t2 - entry) * d / R
        print(f"    -> REPLAY EXIT T2 @ bar {i} ({df.index[i]}) px {t2:.10f} "
              f"pnl {pnl:+.4f}R | stamped exit {stamped_exit}")
        break
    i += 1
else:
    pnl += ((1 - PARTIAL) if t1_done else 1.0) * (cl[n - 1] - entry) * d / R
    print(f"    -> REPLAY EXIT EOD @ last bar px {cl[n-1]:.10f} pnl {pnl:+.4f}R "
          f"| stamped exit {stamped_exit}")
