"""09_model3_study.py — Model 3 (D-PY-28) quadrant sweep across symbols.
Requires setups CSVs WITH breakAt stamps (rerun 05_multisymbol first after the
rino_setup reship). Prints expectancy per symbol x quadrant: 1.0=wick extreme
(Techfred), 0.75/0.5/0.25 toward the body. The entry-depth research dial."""
import glob
import pandas as pd
from lab import load, pip_size
from rino_backtest import run_model3

QUADRANTS = (1.0, 0.75, 0.5, 0.25)
rows = []
for f in sorted(glob.glob("reports/setups_*.csv")):
    sym = f.split("_")[-1].replace(".csv", "")
    st = pd.read_csv(f, parse_dates=["origin", "availableAt"])
    for col in ("breakAt", "breakCritAt"):        # tolerate pre-stamp CSVs
        if col in st.columns:
            st[col] = pd.to_datetime(st[col], errors="coerce")
        else:
            st[col] = pd.NaT
    df = load(sym)
    row = {"symbol": sym}
    for q in QUADRANTS:
        tr = run_model3(df, st, quadrant=q, mintick=pip_size(sym) / 10)
        row[f"q{int(q*100)}_n"] = len(tr)
        row[f"q{int(q*100)}_R"] = round(float(tr.pnl_R.mean()), 3) if len(tr) else None
    rows.append(row)
    print(f"[{sym}] {row}")
out = pd.DataFrame(rows)
out.to_csv("reports/model3_study.csv", index=False)
print("\nsaved reports/model3_study.csv")
