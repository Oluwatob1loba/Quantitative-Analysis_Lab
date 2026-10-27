"""test_setup.py — fixture gates for rino_setup.py (hand-scripted ground truth)."""
from types import SimpleNamespace as NS
from rino_episode import Episode
from rino_setup import (Gap, poi_gate, pick_target, setup_class, t1_by_class,
                        grade, TrendState, SetupEngine, FvgFeed)

FAILS = []
def check(gate, ok, detail=""):
    print(f"{gate:<46}: {'PASS' if ok else 'FAIL ' + str(detail)}")
    if not ok: FAILS.append(gate)

T0 = 1000; T1 = 2000; T2 = 3000
def rec(price, kind, state=0, role="PDOL", cov=True, tf="1D", origin=T1, chg=None):
    return NS(owner=NS(price=price, kind=kind, origin=origin, available_at=T0),
              tf_key=tf, role=role, state=state, coverage=cov, changed_at=chg)
def comp(o, h, l, c, direction=1, candles=1):
    ep = Episode(T0, h, l, T1, o, h, l, c, T2, candles,
                 swept_high=(direction == -1), swept_low=(direction == 1))
    if direction == 1: ep.close_ref_low = l + 0.0010
    else: ep.close_ref_high = h - 0.0010
    return NS(episode=ep, direction=direction,
              variant="Window" if candles == 1 else "WindowMulti")

import rino_config as rc
cfg = rc.PRESET_A
cfg.anchors = [rc.AnchorCfg("1W", 5, True, True), rc.AnchorCfg("1M", 5, True, True),
               rc.AnchorCfg("3M", 3, True, False)]
RANK = {"tf1_key": "1D", "1D": 1.0, "4h": 4/24, "1W": 7.0, "1M": 30.4375, "3M": 91.3125}

# G1: POI gate — penetration requires band INTERSECT of slice; fill is diagnostic-only
gaps = [Gap("FVG", "1D", 1, 1.1000, 1.1010, T0, T0, T0),
        Gap("FVG", "1D", 1, 1.2000, 1.2010, T0, T0, T0)]   # wrong direction
hit, diag = poi_gate(gaps, 1, T1, T2, 1.1005, 1.1007, [], True, "1D")
check("G1a slice penetration hits", hit, diag)
filled = [Gap("FVG", "1D", 1, 1.1000, 1.1010, T0, T0, T0, active=False, ended_at=T1 - 5)]
hit2, diag2 = poi_gate(filled, 1, T1, T2, 1.1005, 1.1007, [], True, "1D")
check("G1b pre-origin fill VETOES (D-610 L1 ratified)", not hit2, diag2)
episode_fill = [Gap("FVG", "1D", 1, 1.1000, 1.1010, T0, T0, T0, active=False, ended_at=T1 + 5)]
hit2c, _ = poi_gate(episode_fill, 1, T1, T2, 1.1005, 1.1007, [], True, "1D")
check("G1c episode-caused fill still authorizes", hit2c, "")

# G2: targets — slot priority + nearest; DOC-08 raw-TF anchorBonus in grade
recs_tf1 = [rec(1.1100, "High"), rec(1.1200, "High"), rec(1.0900, "Low", role="SDOL")]
recs_a1  = [rec(1.1300, "High", tf="1W")]
tgt, tf_, org, sec, sec_org = pick_target(cfg, 1, 1.1050, T2, recs_tf1, recs_a1, RANK)
check("G2a anchor slot wins primary", tf_ == "1W" and abs(tgt - 1.1300) < 1e-12, (tf_, tgt))
check("G2b TF1 nearest is secondary", abs(sec - 1.1100) < 1e-12, sec)
s = {"actionable": True, "targetTf": "1W", "confluenceLayers": 1, "aligned": True,
     "fvg": True, "vi": False, "opposition": False, "intactPrimary": True,
     "breakClass": "Critical", "setupClass": "A", "keyTimeSweep": False}
g, sc = grade(s, cfg)
# 1*1 + 1 + 1 + 2 + 1 + 4*1 = 10 -> A (unclamped, class A)
check("G2c grade math, A1 bonus now 2 (S-7)", g == "A" and sc == 8, (g, sc))
s2 = dict(s, setupClass="B", confluenceLayers=0, aligned=False, fvg=False, breakClass="None",
          targetTf="1D")
g2, sc2 = grade(s2, cfg)
check("G2d class B capped at B", g2 == "B", (g2, sc2))
s3 = dict(s, keyTimeSweep=True, confluenceLayers=0, aligned=False, fvg=False, breakClass="None")
g3, sc3 = grade(s3, cfg)
check("G2e ADD-01 keyTimeSweep weight adds 1", sc3 == 4, (g3, sc3))  # intact 1 + bonus 2 (S-7) + keyTime 1

# G3: class + t1
check("G3a opposing close = A", setup_class(1.10, 1.11, 1.11, 1.10) == "A")
check("G3b same color = B", setup_class(1.10, 1.11, 1.09, 1.10) == "B")
t1, flip = t1_by_class("A", True, 1.1200, 1.1000, 1.1050, 1)
check("G3c class A bullish -> PDOL high", abs(t1 - 1.1200) < 1e-12 and not flip, (t1, flip))
t1b, flipb = t1_by_class("B", True, 1.1200, 1.1000, 1.1150, 1)
check("G3d class B bullish T1 low -> profit-guard flips to high",
      abs(t1b - 1.1200) < 1e-12 and flipb, (t1b, flipb))

# G4: TSM veto — TF1 counter-event vetoed while anchor holds old-side PDOL
tsm = TrendState(cfg)
anc = [rec(1.2000, "High", tf="1W"), rec(1.0500, "Low", tf="1W")]
tsm.dir = 1
tsm.update(-1, False, anc, [True, True, False])
check("G4a TF1 counter-event vetoed into pending", tsm.dir == 1 and tsm.pend_side == -1,
      (tsm.dir, tsm.pend_side))
tsm2 = TrendState(cfg); tsm2.dir = 1
tsm2.update(-1, False, [rec(1.0500, "Low", tf="1W")], [True])  # no old-side anchor hold
check("G4b flips when no anchor holds", tsm2.dir == -1 and tsm2.pend_side == 0, (tsm2.dir,))

# G5: owner lifecycle — failure precedence + dualHit (via range_state on a setup)
from rino_setup import range_state
own = {"state": "MANIPULATION", "endTime": None, "dualHit": False, "k1": "1D",
       "origin": T1, "setupId": "x", "target": 1.12}
check("G5a transition stamps endTime", range_state(own, "DONE", T2) is not None
      and own["endTime"] == T2, own)
check("G5b idempotent transition returns None", range_state(own, "DONE", T2) is None)

print()
if FAILS:
    print("BOARD:", len(FAILS), "FAILURE(S)"); raise SystemExit(1)
print("BOARD: all setup gates PASS")
