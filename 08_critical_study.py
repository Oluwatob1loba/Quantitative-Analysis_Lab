"""08_critical_study.py — time-split validation of the break Critical king factor.
Reads reports/trades_*.csv + setups_*.csv (already on disk). Verdict rule: Critical
must beat non-Critical in BOTH halves before the ranking amendment is ruled."""
import glob
import pandas as pd

SPLIT = pd.Timestamp("2023-07-01")
rows = []
for f in sorted(glob.glob("reports/trades_*.csv")):
    sym = f.split("_")[-1].replace(".csv", "")
    tr = pd.read_csv(f, parse_dates=["origin"])
    st = pd.read_csv(f"reports/setups_{sym}.csv", parse_dates=["origin", "availableAt"])
    m = tr.merge(st[["origin", "direction", "breakClass"]], on=["origin", "direction"], how="left")
    for half, sub in (("P1_21-23", m[m.origin < SPLIT]), ("P2_23-26", m[m.origin >= SPLIT])):
        if not len(sub):
            continue
        crit = sub[sub.breakClass == "Critical"]
        oth = sub[sub.breakClass != "Critical"]
        rows.append(dict(symbol=sym, half=half, n=len(sub),
                         crit_n=len(crit), crit_R=round(float(crit.pnl_R.mean()), 3) if len(crit) else None,
                         oth_n=len(oth), oth_R=round(float(oth.pnl_R.mean()), 3) if len(oth) else None))

out = pd.DataFrame(rows)
out.to_csv("reports/critical_study.csv", index=False)
print(out.to_string(index=False))

p1 = out[out.half == "P1_21-23"].set_index("symbol")
p2 = out[out.half == "P2_23-26"].set_index("symbol")
holds = [s for s in p1.index if s in p2.index
         and p1.loc[s, "crit_R"] is not None and p2.loc[s, "crit_R"] is not None
         and pd.notna(p1.loc[s, "crit_R"]) and pd.notna(p2.loc[s, "crit_R"])
         and p1.loc[s, "crit_R"] > p1.loc[s, "oth_R"] and p2.loc[s, "crit_R"] > p2.loc[s, "oth_R"]]
pos = [s for s in p1.index if s in p2.index
       and pd.notna(p1.loc[s, "crit_R"]) and pd.notna(p2.loc[s, "crit_R"])
       and p1.loc[s, "crit_R"] > 0 and p2.loc[s, "crit_R"] > 0]
print(f"\nCritical-beats-other in BOTH halves: {len(holds)} symbols: {holds}")
print(f"Critical POSITIVE in both halves:    {len(pos)} symbols: {pos}")
print("saved reports/critical_study.csv")
