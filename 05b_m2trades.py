"""05b_m2trades.py - stamp the Model-2 population's execution records (D-PY-33).
Writes reports/trades_m2_<SYMBOL>.csv so viz can render M2 EXACTLY as the
code executed it - no render-time recompute. Run after 05m_m2stamp.py."""
import os
import pandas as pd
from lab import load, SYMBOLS, pip_size
from rino_backtest import run_backtest

for sym in SYMBOLS:
    sp = f"reports/setups_m2_{sym}.csv"
    if not os.path.exists(sp):
        print(f"[{sym}] no m2 stamps - skipped"); continue
    su = pd.read_csv(sp, parse_dates=["origin", "availableAt"])
    tr = run_backtest(load(sym), su, mintick=pip_size(sym) / 10, mode="base")
    tr.to_csv(f"reports/trades_m2_{sym}.csv", index=False)
    print(f"[{sym}] {len(tr)} m2 trades stamped (base mode)")
