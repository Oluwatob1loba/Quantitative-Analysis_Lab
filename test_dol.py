import pandas as pd
from lab import load
from rino_config import PRESET_A
from rino_clocks import attach_native
from rino_tf1 import Tf1Anatomy
from rino_dol import DolEngine

cfg = PRESET_A
df = load("EURUSD")
tf1 = Tf1Anatomy(cfg)
df = tf1.run(df)
eng = DolEngine(cfg, mintick=1e-5)
eng.run(df, tf1)

recs = list(eng.records.values())
census = pd.Series([(r.tf_key, r.role, r.state) for r in recs]).value_counts()
print("DOL census (tf, role, state):")
print(census.to_string())
print(f"events: {len(eng.events)} | anchor draws: {len(eng.anchors)} | "
      f"confluent: {sum(1 for r in recs if r.confluent)}")

# Gate 1: roles match body direction on every TF1 record
d = attach_native(df, cfg.tf1, "tf1")
oc = d[d["tf1_roll"]].set_index("tf1_bucket")[["tf1_open", "tf1_close"]]
bad1 = 0
for r in recs:
    if r.tf_key != cfg.tf1 or r.role == "":
        continue
    o, c = oc.loc[r.owner.origin, "tf1_open"], oc.loc[r.owner.origin, "tf1_close"]
    want = "PDOL" if ((c > o) == (r.owner.kind == "High")) else "SDOL"
    if want != r.role:
        bad1 += 1
print(f"Gate 1 roles from body direction        : {'PASS' if bad1 == 0 else f'FAIL {bad1}'}")

# Gate 2: monotone states, stamps present
ok2 = all((r.state in (0, 1, 2)) and (r.changed_at is not None or r.state == 0) for r in recs)
print(f"Gate 2 monotone states with stamps      : {'PASS' if ok2 else 'FAIL'}")

# Gate 3: SDOL silence — untouched SDOLs exist but never appear in events
silent = [r for r in recs if r.role == "SDOL" and r.state == 0]
leaked = [e for e in eng.events if e["role"] == "SDOL" and e["state"] == 0]
print(f"Gate 3 untouched SDOL silent ({len(silent)} exist): {'PASS' if not leaked else 'FAIL'}")

# Gate 4: sweep/consume predicates reproduce on a sample
import random
s1 = [r for r in recs if r.state == 1]
s2 = [r for r in recs if r.state == 2]
hb = d[d["tf1_roll"]].set_index("tf1_bucket")[["tf1_high", "tf1_low", "tf1_close"]]
bad4 = 0
for r in random.Random(7).sample(s1, min(25, len(s1))):
    row = hb.loc[r.owner.origin] if r.tf_key == cfg.tf1 else None
    if row is None:
        continue
    side = r.owner.kind if r.tf_key == cfg.tf1 else r.owner.side
    touched = (row["tf1_high"] >= r.owner.price) if side == "High" else (row["tf1_low"] <= r.owner.price)
    broke = (row["tf1_close"] > r.owner.price) if side == "High" else (row["tf1_close"] < r.owner.price)
    if not touched or broke:
        bad4 += 1
for r in random.Random(11).sample(s2, min(25, len(s2))):
    if r.tf_key != cfg.tf1:
        continue
    row = hb.loc[r.owner.origin]
    side = r.owner.kind
    broke = (row["tf1_close"] > r.owner.price) if side == "High" else (row["tf1_close"] < r.owner.price)
    if not broke:
        bad4 += 1
print(f"Gate 4 sweep/consume predicates sample  : {'PASS' if bad4 == 0 else f'FAIL {bad4}'}")

# Gate 5: confluence symmetric and cross-key
bad5 = 0
for r in recs:
    if not r.confluent:
        continue
    partner = [o for o in recs if o is not r and o.tf_key != r.tf_key and o.confluent
               and o.role == "PDOL" and o.state == 0
               and abs(o.owner.price - r.owner.price) / r.owner.price < 0.002]
    if not partner:
        bad5 += 1
print(f"Gate 5 confluence cross-key symmetric   : {'PASS' if bad5 == 0 else f'FAIL {bad5}'}")

# ---------------------------------------------------------------------------
# Gate 6 — disturbance eligibility and the attribution/detection split (P4.3).
# Two conjuncts, both from the frozen contract:
#   6a. A draw may only be swept or consumed by an observation that begins at or
#       after its availability boundary (C:L1673..L1683: "Eligible observation
#       begins at/after draw availability"). Consequence: no TF1 draw may carry a
#       disturbance stamp on or before the roll that created it — a candle cannot
#       soup its own extreme. changed_at is the roll bar time; owner.available_at
#       is the creating roll; strict inequality is the rule.
#   6b. Attribution time and detection time are different timestamps (TAD V2.3 §3:
#       "Detection time and drawing endpoint are different timestamps"). For a
#       consumed TF1 draw, owner.end_time is the BREAKING candle's own opening
#       timestamp while changed_at is the roll bar at which the engine could first
#       know it; end_time must therefore sit strictly before changed_at.
# A failure here means the lifecycle is reading same-roll or future data it is not
# entitled to — the exact failure class DR-02 exists to prevent.
# ---------------------------------------------------------------------------
bad6 = 0
for r in recs:
    if r.tf_key != cfg.tf1 or r.state == 0:
        continue
    if r.changed_at is None or r.changed_at <= r.owner.available_at:
        bad6 += 1                                    # 6a: disturbed before eligible
    if r.state == 2 and r.owner.end_time is not None and not (r.owner.end_time < r.changed_at):
        bad6 += 1                                    # 6b: attribution not before detection
print(f"Gate 6 eligibility + attribution<detection : {'PASS' if bad6 == 0 else f'FAIL {bad6}'}")

# ---------------------------------------------------------------------------
# Gate 7 — the confluence pool is bounded by retention (BUG-PY-02 sentinel).
# Provenance: in frozen CORE, f_v3Confluence / f_v3ConfluenceLayers iterate
# tf1Levels and v3ExtraDols — arrays that P4.10 prunes every roll
# (C:L568..L603, C:L2018..L2059). The first port kept every record ever stamped,
# which made confluence a DIFFERENT predicate (scope is semantics) and O(pool^2)
# per refresh — that is the hang you Ctrl-C'd out of. _recompute_confluence now
# tracks self.max_pool; this gate asserts it never exceeds what retention can
# hold: two TF1 draws per lookback candle, two per enabled anchor candle, plus
# slack for in-flight stamps. For PRESET_A the bound is 2*15 + 2*(5+5+3) + 4 = 60.
# ---------------------------------------------------------------------------
bound = 2 * cfg.tf1_lookback + 2 * sum(a.candles for a in cfg.anchors if a.enabled) + 4
ok7 = eng.max_pool <= bound
print(f"Gate 7 confluence pool bounded by retention : {'PASS' if ok7 else 'FAIL'}"
      f" (max pool {eng.max_pool}, bound {bound})")

print("\nnewest 5 events:")
for e in eng.events[-5:]:
    print("  ", e)