"""05_multisymbol.py — full pipeline + Model-2 backtest across every lake symbol.
Replication gate: a split that survives 9 symbols is evidence; one that dies was noise."""
import os
import pandas as pd
from lab import load, SYMBOLS, pip_size

# DIAL: which symbols to run. SYMBOLS = full 9-symbol sweep; or a shortlist.
RUN = SYMBOLS
if isinstance(RUN, str):
    RUN = SYMBOLS if RUN.strip('"\'[] ').upper() == "SYMBOLS" else [RUN]
from rino_config import config_for
from rino_engine import RinoEngine
from rino_backtest import run_backtest

rows = []
for sym in RUN:
    if not os.path.exists(f"data/{sym}_M15.csv"):
        print(f"[{sym}] no lake, skipped"); continue
    cfg = config_for(sym)
    eng = RinoEngine(cfg, mintick=pip_size(sym) / 10)
    eng.run(load(sym), verbose=True)
    st = pd.DataFrame(eng.setup.all_setups())
    if not len(st):
        rows.append(dict(symbol=sym, setups=0)); continue
    row = dict(symbol=sym, setups=len(st), actionable=int(st.actionable.sum()))
    for mode in ("base", "d703"):
        tr = run_backtest(eng._df, st, mintick=pip_size(sym) / 10, mode=mode)
        if not len(tr):
            continue
        row[f"{mode}_n"] = len(tr)
        row[f"{mode}_exp"] = round(float(tr.pnl_R.mean()), 3)
        row[f"{mode}_PF"] = (round(float(tr[tr.pnl_R > 0].pnl_R.sum()
                     / abs(tr[tr.pnl_R < 0].pnl_R.sum())), 2) if (tr.pnl_R < 0).any() else None)
        if mode == "base":
            kt = tr.groupby(tr.keyTimeSweep).pnl_R.mean()
            gr = tr.groupby(tr.grade).pnl_R.mean()
            row.update(
                win=f"{(tr.pnl_R > 0).mean():.1%}",
                raidT=round(kt.get(True, float("nan")), 3) if True in kt.index else None,
                raidF=round(kt.get(False, float("nan")), 3) if False in kt.index else None,
                gradeA=round(gr.get("A", float("nan")), 3) if "A" in gr.index else None,
                gradeB=round(gr.get("B", float("nan")), 3) if "B" in gr.index else None)
        out_name = f"reports/trades_{sym}.csv" if mode == "base" else f"reports/trades_{mode}_{sym}.csv"
        tr.to_csv(out_name, index=False, float_format="%.17g")   # D-PY-44/49
    rows.append(row)
    # D-PY-49: exact float64 serialization - pandas default to_csv truncates
    # (e.g. fl(114.653+0.001) -> "114.654"), which desyncs CSV geometry from the
    # engine's in-memory values by 1 ulp and manufactures phantom audit defects.
    st.to_csv(f"reports/setups_{sym}.csv", index=False, float_format="%.17g")
    print(f"[{sym}] done: {rows[-1]}")

ms = pd.DataFrame(rows)
ms.to_csv("reports/multisymbol_summary.csv", index=False)
print("\n=== MULTISYMBOL SUMMARY ===")
print(ms.to_string(index=False))
print("\nsaved reports/multisymbol_summary.csv")
