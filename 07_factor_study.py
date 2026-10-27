"""07_factor_study.py — which grade factors carry negative marginal expectancy?
Joins trades with setups on (origin, direction); for each factor, pooled
expectancy when true vs false + per-symbol consistency. The poisoned factor(s)
are the amendment target."""
import glob
import pandas as pd

rows = []
frames = []
for f in sorted(glob.glob("reports/trades_*.csv")):
    sym = f.split("_")[-1].replace(".csv", "")
    tr = pd.read_csv(f, parse_dates=["origin"])
    st = pd.read_csv(f"reports/setups_{sym}.csv", parse_dates=["origin", "availableAt"])
    m = tr.merge(st[["origin", "direction", "aligned", "fvg", "vi", "intactPrimary",
                     "opposition", "location", "breakClass", "caution", "t1Flipped"]],
                 on=["origin", "direction"], how="left")
    m["symbol"] = sym
    frames.append(m)
allt = pd.concat(frames, ignore_index=True)

FACTORS = [("confluence x1", lambda d: d.confluenceLayers >= 1),
           ("confluence x2", lambda d: d.confluenceLayers >= 2),
           ("aligned", lambda d: d.aligned == True),
           ("fvg tag", lambda d: d.fvg == True),
           ("vi tag", lambda d: d.vi == True),
           ("intactPrimary", lambda d: d.intactPrimary == True),
           ("opposition", lambda d: d.opposition == True),
           ("location(prem/disc)", lambda d: d.location == True),
           ("caution", lambda d: d.caution == True),
           ("t1Flipped", lambda d: d.t1Flipped == True),
           ("keyTimeSweep", lambda d: d.keyTimeSweep == True),
           ("break Critical", lambda d: d.breakClass == "Critical"),
           ("break Major", lambda d: d.breakClass == "Major"),
           ("break Minor", lambda d: d.breakClass == "Minor")]

print(f"{'factor':<22} {'n(True)':>8} {'R|True':>8} {'R|False':>8} {'delta':>8} {'symbols +':>9}")
for name, fn in FACTORS:
    t, fl = allt[fn(allt)], allt[~fn(allt)]
    if not len(t) or not len(fl):
        continue
    rt, rf = t.pnl_R.mean(), fl.pnl_R.mean()
    sym_delta = allt.assign(_f=fn(allt)).groupby("symbol").apply(
        lambda g: g.loc[g._f, "pnl_R"].mean() - g.loc[~g._f, "pnl_R"].mean()
        if g._f.any() and (~g._f).any() else None, include_groups=False)
    pos = int((sym_delta.dropna() > 0).sum())
    rows.append(dict(factor=name, n_true=len(t), R_true=round(rt, 3),
                     R_false=round(rf, 3), delta=round(rt - rf, 3), symbols_pos=pos))
    print(f"{name:<22} {len(t):>8} {rt:>8.3f} {rf:>8.3f} {rt-rf:>+8.3f} {pos:>5}/{len(sym_delta.dropna())}")

out = pd.DataFrame(rows)
out.to_csv("reports/factor_study.csv", index=False)
print("\nsaved reports/factor_study.csv")
print("READ: positive delta = factor HELPS when present. A factor with negative")
print("delta on most symbols is poison: candidates for kill/invert in the amendment.")
