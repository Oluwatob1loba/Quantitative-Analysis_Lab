"""dispute_aug13.py - adjudicate the skipped range-trade buy, EURUSD 2026-08-13.

Reruns the certified engine on your lake and prints, for the days around
2026-08-13:
  1. the TF1 candles (which candle did what)
  2. every draw alive or recently disturbed there (PDOL/SDOL, state, side)
  3. every EPISODE that opened/completed in the window (swept sides, close refs)
  4. every SETUP the engine produced there (actionable or CONTEXT, with class,
     grade, target, and the POI-zone bounds)

Paste the whole output to the audit chat. From it we can tell whether the
miss was: (a) no undisturbed draw to anchor direction, (b) the FVG gate
demoting it to CONTEXT, (c) close-through already consuming the draw, or
(d) a genuine port bug.
"""
import pandas as pd
from lab import load, pip_size
from rino_config import config_for
from rino_engine import RinoEngine
from rino_dol import tf_key

DAY = pd.Timestamp("2026-09-14")
SYMBOL = "AUDUSD"
PAD = pd.Timedelta(days=5)

cfg = config_for(SYMBOL)
eng = RinoEngine(cfg, pip_size(SYMBOL) / 10)
df = eng.run(load(SYMBOL))
k1 = tf_key(cfg.tf1)

print(f"=== 1) TF1 candles {DAY - PAD:%Y-%m-%d} .. {DAY + PAD:%Y-%m-%d} ===")
rolls = df[df["tf1_roll"]].reset_index()
win = rolls[(rolls["tf1_cbucket"] >= DAY - PAD) & (rolls["tf1_cbucket"] <= DAY + PAD)]
for _, r in win.iterrows():
    ud = "up  " if r.tf1_close > r.tf1_open else "down" if r.tf1_close < r.tf1_open else "flat"
    print(f"  {r.tf1_cbucket:%Y-%m-%d} {ud}  O {r.tf1_open}  H {r.tf1_high}  "
          f"L {r.tf1_low}  C {r.tf1_close}")

print(f"\n=== 2) draws alive or disturbed near {DAY:%Y-%m-%d} ===")
for r in eng.dol.records.values():
    ow = r.owner
    o = getattr(ow, "origin", None)
    if o is None or o > DAY + PAD:
        continue
    if r.changed_at is not None and r.changed_at < DAY - PAD:
        continue
    side = getattr(ow, "side", None) or getattr(ow, "kind", "?")
    print(f"  {r.tf_key:<4} {r.role:<5} {side:<5} @{ow.price:<10} "
          f"state {r.state}  origin {o:%Y-%m-%d}  changed {r.changed_at}")

comp = eng.frame()
w = comp[(comp.origin >= DAY - PAD) & (comp.origin <= DAY + PAD)]
print(f"\n=== 3) episodes with origin in window: {len(w)} ===")
for _, r in w.iterrows():
    print(f"  {r.origin:%Y-%m-%d} {'LONG' if r.direction == 1 else 'SHORT'} "
          f"{r.variant} candles={r.candles} sweptH={r.sweptHigh} sweptL={r.sweptLow} "
          f"closeRefL={r.closeRefLow} closeRefH={r.closeRefHigh} raid={r.keyTimeSweep}")

st = pd.DataFrame(eng.setup.all_setups())
w2 = st[(st.origin >= DAY - PAD) & (st.origin <= DAY + PAD)]
print(f"\n=== 4) setups with origin in window: {len(w2)} "
      f"(actionable {int(w2.actionable.sum()) if len(w2) else 0}) ===")
for _, r in w2.iterrows():
    print(f"  {r.origin:%Y-%m-%d} {'LONG ' if r.direction == 1 else 'SHORT'} "
          f"{'ACTIONABLE' if r.actionable else 'CONTEXT   '} cls={r.setupClass} "
          f"grade={r.grade} stop={r.stop} t1={r.t1} target={r.target} ({r.targetTf}) "
          f"conf={r.confluenceLayers} raid={r.keyTimeSweep}")
    if not r.actionable:
        print(f"        zone [{r.zoneLow}, {r.zoneHigh}]")

near = st[(st.origin >= DAY - pd.Timedelta(days=12)) & (st.origin <= DAY + pd.Timedelta(days=12))]
print(f"\n=== 5) nearest setups +/-12 days (for context): {len(near)} ===")
for _, r in near.iterrows():
    print(f"  {r.origin:%Y-%m-%d} {'LONG ' if r.direction == 1 else 'SHORT'} "
          f"{'ACTIONABLE' if r.actionable else 'CONTEXT   '} cls={r.setupClass} grade={r.grade}")
