"""05_multisymbol.py — full pipeline + Model-2 backtest across every lake symbol.
Replication gate: a split that survives 9 symbols is evidence; one that dies was noise."""
import os
import pandas as pd
from lab import load, SYMBOLS, pip_size
from rino_config import config_for
from rino_engine import RinoEngine
from rino_backtest import run_backtest

rows = []
for sym in SYMBOLS:
    if not os.path.exists(f"data/{sym}_M15.csv"):
        print(f"[{sym}] no lake, skipped"); continue
    cfg = config_for(sym)
    eng = RinoEngine(cfg, mintick=pip_size(sym) / 10)
    eng.run(load(sym))
    st = pd.DataFrame(eng.setup.all_setups())
    if not len(st):
        rows.append(dict(symbol=sym, setups=0)); continue
    tr = run_backtest(eng._df, st, mintick=pip_size(sym) / 10)
    if not len(tr):
        rows.append(dict(symbol=sym, setups=len(st), actionable=int(st.actionable.sum()))); continue
    kt = tr.groupby(tr.keyTimeSweep).pnl_R.mean()
    gr = tr.groupby(tr.grade).pnl_R.mean()
    rows.append(dict(
        symbol=sym, setups=len(st), actionable=int(st.actionable.sum()), trades=len(tr),
        win=f"{(tr.pnl_R > 0).mean():.1%}",
        exp_R=round(tr.pnl_R.mean(), 3),
        PF=round(tr[tr.pnl_R > 0].pnl_R.sum() / abs(tr[tr.pnl_R < 0].pnl_R.sum()), 2)
        if (tr.pnl_R < 0).any() else None,
        raidT=round(kt.get(True, float("nan")), 3) if True in kt.index else None,
        raidF=round(kt.get(False, float("nan")), 3) if False in kt.index else None,
        gradeA=round(gr.get("A", float("nan")), 3) if "A" in gr.index else None,
        gradeB=round(gr.get("B", float("nan")), 3) if "B" in gr.index else None,
    ))
    tr.to_csv(f"reports/trades_{sym}.csv", index=False)
    st.to_csv(f"reports/setups_{sym}.csv", index=False)
    print(f"[{sym}] done: {rows[-1]}")

ms = pd.DataFrame(rows)
ms.to_csv("reports/multisymbol_summary.csv", index=False)
print("\n=== MULTISYMBOL SUMMARY ===")
print(ms.to_string(index=False))
print("\nsaved reports/multisymbol_summary.csv")
