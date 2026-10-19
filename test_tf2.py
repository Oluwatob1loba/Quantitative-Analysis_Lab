import pandas as pd
from lab import load
from rino_config import PRESET_A
from rino_clocks import attach_native
from rino_tf2 import Tf2Structure

cfg = PRESET_A
df = load("EURUSD")
eng = Tf2Structure(cfg)
eng.run(df)
f = eng.frame()

print("counters:", eng.counters)
print(f"swings: {len(f)} | majors: {len(eng.majors)} | "
      f"critical: {sum(1 for s in eng.swings if s.is_critical)} | "
      f"unresolved deferred: {len(eng.pending_critical)}")

d = attach_native(df, cfg.tf2, "tf2")
cbc = d[d["tf2_roll"]].set_index("tf2_bucket")["tf2_close"]
tf1d = attach_native(df, cfg.tf1, "tf1")
hist = {r["tf1_bucket"]: (r["tf1_high"], r["tf1_low"])
        for _, r in tf1d[tf1d["tf1_roll"]].iterrows()}

alt = all(a.side != b.side for a, b in zip(eng.majors, eng.majors[1:]))
print(f"Gate 1 Majors alternate sides            : {'PASS' if alt else 'FAIL'}")

ok2 = (sum(1 for s in eng.swings if s.demoted_by == "supersession") == eng.counters["supersession"]
       and sum(1 for s in eng.swings if s.demoted_by == "equal") == eng.counters["equal_loser"]
       and len(eng.majors) == eng.counters["opposite_confirm"])
print(f"Gate 2 retention bookkeeping identity    : {'PASS' if ok2 else 'FAIL'}")

inv = f[f.end_reason == "invalidated"]
bad3 = 0
for s in inv.itertuples():
    c = cbc.loc[s.end_time]
    strict = (c > s.price) if s.side == "High" else (c < s.price)
    if not strict or abs(c - s.broken_by_close) > 1e-12:
        bad3 += 1
print(f"Gate 3 TF2 close-only invalidation       : {'PASS' if bad3 == 0 else f'FAIL {bad3}'}")

bad4 = 0
for s in eng.swings:
    if s.is_critical is None:
        continue
    h, l = hist[s.parent_bucket]
    want = min(abs(s.price - h), abs(s.price - l)) / s.price * 100 <= cfg.tf2_critical_proximity_pct
    if want != s.is_critical:
        bad4 += 1
print(f"Gate 4 Critical proximity reproducible   : {'PASS' if bad4 == 0 else f'FAIL {bad4}'}")

act = f[f.end_reason == ""]
ok5 = eng.cutoff is not None and bool((act["origin"] >= eng.cutoff).all())
print(f"Gate 5 memory-horizon pruning            : {'PASS' if ok5 else 'FAIL'}")

ok6 = eng.bias_provider.bias == "undefined" and len(eng.bias_provider.events()) == 0
print(f"Gate 6 D-PY-15 bias machine absent       : {'PASS' if ok6 else 'FAIL'}")

print("\nlast 5 Majors:")
print(pd.DataFrame([dict(side=m.side, price=m.price, origin=str(m.origin),
                         klass=m.klass, critical=m.is_critical)
                    for m in eng.majors[-5:]]).to_string(index=False))