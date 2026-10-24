import pandas as pd
from lab import load
from rino_config import PRESET_A
from rino_clocks import attach_native
from rino_tf1 import Tf1Anatomy

cfg = PRESET_A                      # tf1 = 1D for this run
df = load("EURUSD")
eng = Tf1Anatomy(cfg)
eng.run(df)
f = eng.frame()

print(f"stamped {len(f):,} levels")
print(f.groupby(["kind", "end_reason"]).size().to_string())

d = attach_native(df, cfg.tf1, "tf1")
# TEST-PY-02: key by the CONFIRMED bucket (cbucket, D-PY-17). tf1_bucket keys the breaking
# candle's close by the NEXT roll, so the strict-close check compared against the wrong candle.
conf = d[d["tf1_roll"]][["tf1_cbucket", "tf1_close"]].dropna().set_index("tf1_cbucket")["tf1_close"]

# Gate 1: every invalidation is a STRICT close break, and end_time is the breaking candle's open
inv = f[f.end_reason == "invalidated"]
bad = 0
for lv in inv.itertuples():
    c = conf.loc[lv.end_time]
    strict = (lv.polarity == "resistance" and c > lv.price) or (lv.polarity == "support" and c < lv.price)
    if not strict or abs(c - lv.broken_by_close) > 1e-12:
        bad += 1
print(f"Gate 1 strict-close + endTime=breaking-open : {'PASS' if bad == 0 else f'FAIL {bad}'}")

# Gate 2: first-break property on a sample (no earlier confirmed close had already broken it)
rolls = d[d["tf1_roll"]]
import random
random.seed(7)
sample = inv.sample(min(25, len(inv)), random_state=7)
bad2 = 0
for lv in sample.itertuples():
    between = rolls[(rolls.index > lv.available_at) & (rolls.index < lv.observed_at)]
    for _, r in between.iterrows():
        beyond = (r["tf1_close"] > lv.price) if lv.kind != "Low" else (r["tf1_close"] < lv.price)
        if beyond:
            bad2 += 1
print(f"Gate 2 first-break (25-level sample)        : {'PASS' if bad2 == 0 else f'FAIL {bad2}'}")

# Gate 3: retention caps never exceeded (research-view concurrency)
ok3 = True
for kind in ("High", "Low", "Mid", "Open"):
    w = eng._window(kind)
    sub = f[f.kind == kind]
    for t in rolls.index[::50]:
        live = ((sub.available_at <= t) & ((sub.observed_at.isna()) | (sub.observed_at > t))).sum()
        ok3 &= live <= w
print(f"Gate 3 retention caps                       : {'PASS' if ok3 else 'FAIL'}")

active = f[f.end_reason == ""]
print("\nactive levels at end of history:")
print(active[["kind", "price", "origin"]].sort_values(["kind", "origin"]).to_string(index=False))

ok0 = not ((f.kind == "Mid") & (f.end_reason == "invalidated")).any() and not (f.kind == "Open").any()
print(f"Gate 0 Mid never invalidated / no Open stamps : {'PASS' if ok0 else 'FAIL'}")