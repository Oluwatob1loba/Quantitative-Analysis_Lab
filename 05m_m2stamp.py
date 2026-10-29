"""05m_m2stamp.py - stamp the TRUE Model-2 population (D-PY-33).

Runs the certified engine with admission="m2" (TSM gate + FVG POI gate bypassed
at record time; draw-anchored enumeration and the PDOL-target requirement
UNCHANGED) and writes reports/setups_m2_<SYMBOL>.csv - M2 and M3 ledgers never
share a file. Evidence fields (breakClass, confluence, class, grade) remain
stamped, non-gating.

RUN ONLY AFTER the D-PY-33 equivalence gates passed (test_setup green +
05_multisymbol bit-identical summary).
"""
import copy
import pandas as pd
from lab import load, pip_size
from rino_config import config_for
from rino_engine import RinoEngine

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD",
           "USDCAD", "USDCHF", "AUDJPY", "NZDJPY"]

for sym in SYMBOLS:
    cfg = copy.deepcopy(config_for(sym))
    cfg.admission = "m2"
    eng = RinoEngine(cfg, pip_size(sym) / 10)
    eng.run(load(sym))
    st = pd.DataFrame(eng.setup.all_setups())
    st.to_csv(f"reports/setups_m2_{sym}.csv", index=False)
    print(f"[{sym}] m2 population: {len(st)} setups, {int(st.actionable.sum()) if len(st) else 0} admitted")
print("\nstamped reports/setups_m2_*.csv - point 12's SETS_PREFIX at them.")
