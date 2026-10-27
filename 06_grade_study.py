"""06_grade_study.py — time-split validation of the grade inversion.
Splits each symbol's trades at 2023-07-01: does grade B beat grade A in BOTH
halves? In-sample split != out-of-sample proof, but a failed split kills the
hypothesis cheaply. Reads reports/trades_*.csv (already on disk)."""
import glob
import pandas as pd

SPLIT = pd.Timestamp("2023-07-01")
rows = []
for f in sorted(glob.glob("reports/trades_*.csv")):
    sym = f.split("_")[-1].replace(".csv", "")
    tr = pd.read_csv(f, parse_dates=["origin"])
    for half, sub in (("P1_21-23", tr[tr.origin < SPLIT]),
                      ("P2_23-26", tr[tr.origin >= SPLIT])):
        if not len(sub):
            continue
        g = sub.groupby(sub.grade).pnl_R.agg(["count", "mean"])
        rows.append(dict(symbol=sym, half=half, n=len(sub),
                         A_n=int(g.loc["A", "count"]) if "A" in g.index else 0,
                         A_R=round(float(g.loc["A", "mean"]), 3) if "A" in g.index else None,
                         B_n=int(g.loc["B", "count"]) if "B" in g.index else 0,
                         B_R=round(float(g.loc["B", "mean"]), 3) if "B" in g.index else None))

out = pd.DataFrame(rows)
out.to_csv("reports/grade_study.csv", index=False)
print(out.to_string(index=False))

p1 = out[out.half == "P1_21-23"].set_index("symbol")
p2 = out[out.half == "P2_23-26"].set_index("symbol")
holds = []
for s in p1.index:
    if s in p2.index:
        a1, b1, a2, b2 = (p1.loc[s, "A_R"], p1.loc[s, "B_R"], p2.loc[s, "A_R"], p2.loc[s, "B_R"])
        if None not in (a1, b1, a2, b2) and pd.notna(a1) and pd.notna(b1) and pd.notna(a2) and pd.notna(b2):
            if b1 > a1 and b2 > a2:
                holds.append(s)
print(f"\ngrade-B-beats-A in BOTH halves on {len(holds)} symbols: {holds}")
print("saved reports/grade_study.csv")
