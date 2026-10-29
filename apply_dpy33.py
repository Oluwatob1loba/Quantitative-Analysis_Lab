"""apply_dpy33.py - D-PY-33 admission flag: separate the M2 population from M3 records.

WHAT THIS DOES (and only this):
  rino_config.py  : adds `admission: str = 'full'` (DEFAULT = frozen V3.2 behavior;
                    "m2" bypasses the TSM direction gate + FVG POI gate AT RECORD TIME).
  rino_setup.py   : wraps the two gate blocks in `if self.cfg.admission == 'full':`.
                    Every other line byte-identical (anchors verified, 1x each).
  12_m2_study.py  : SETS_PREFIX dial so it can read setups_m2_*.csv.

EQUIVALENCE GATES BEFORE ANY M2 STAMP (BOTH must pass):
  1. python test_setup.py      -> same gates green as before, unchanged.
  2. python 05_multisymbol.py  -> summary BIT-IDENTICAL to the last committed run
     (EURUSD base_exp 0.095 / GBPUSD 0.120 / USDJPY -0.048 ...). Default 'full'
     means zero drift; if either gate fails, REVERT these files and report.
THEN: python apply_dpy33.py && python 05m_m2stamp.py; in 12 set SETS_PREFIX='setups_m2_'.
"""

def splice(path, pairs):
    src = open(path).read()
    for find, repl, tag in pairs:
        n = src.count(find)
        assert n == 1, f'{path}: anchor {tag} found {n}x (expected 1) - STOP, nothing written'
        src = src.replace(find, repl)
    open(path, 'w').write(src)
    print(f'  {path}: {len(pairs)} splice(s) applied')

splice('rino_config.py', [(
    '    utc_offset_fixed: int = 1',
    "    utc_offset_fixed: int = 1\n    # D-PY-33 (architect ruling 2026-10-28): admission mode.\n    # 'full' = frozen Model-3 stack (TSM direction gate + FVG POI gate ACTIVE) - default,\n    #          byte-identical to the certified port.\n    # 'm2'   = raw price-delivery population: BOTH gates bypassed at record time\n    #          (episodes still require a tradeable PDOL target). Geometry is stamped on\n    #          every admitted setup; breakClass/confluence/class remain as EVIDENCE,\n    #          non-gating. M3 records and M2 population never share a CSV.\n    admission: str = 'full'\n",
    'config field')])

splice('rino_setup.py', [
    ('Turns completed episodes into graded setups:', "Admission mode D-PY-33: 'm2' bypasses the TSM direction gate and the FVG POI gate\nAT RECORD TIME (default 'full' = frozen V3.2-TSM-L1-O9 behavior).\n\nTurns completed episodes into graded setups:", 'docstring note'),
    ('            # TSM direction gates (live pine)\n            if actionable and self.tsm.dir != 0 and self.tsm.dir != direction:\n                actionable = False; reason = f"opposes trend (trend {self.tsm.dir} vs dir {direction})"\n            if actionable and self.tsm.dir == 0 and prio != 0 and prio != direction:\n                actionable = False; reason = f"opposes TF1 draw (prio {prio} vs dir {direction})"\n', '            # TSM direction gates (live pine) - D-PY-33: bypassed when admission == "m2"\n            if self.cfg.admission == "full":\n                if actionable and self.tsm.dir != 0 and self.tsm.dir != direction:\n                    actionable = False; reason = f"opposes trend (trend {self.tsm.dir} vs dir {direction})"\n                if actionable and self.tsm.dir == 0 and prio != 0 and prio != direction:\n                    actionable = False; reason = f"opposes TF1 draw (prio {prio} vs dir {direction})"\n', 'TSM gate wrap'),
    ('            if actionable and not hit:\n                actionable = False; reason = "no POI souped: " + diag\n', '            # POI gate - D-PY-33: bypassed when admission == "m2"\n            if self.cfg.admission == "full" and actionable and not hit:\n                actionable = False; reason = "no POI souped: " + diag\n', 'POI gate wrap'),
])

splice('12_m2_study.py', [
    ('FILL_MAX_DAYS = 5                         # skip limit fills older than this', "FILL_MAX_DAYS = 5                         # skip limit fills older than this\nSETS_PREFIX = 'setups_'                   # 'setups_m2_' for the D-PY-33 raw population", '12 dial'),
    ('    sp = f"reports/setups_{sym}.csv"', '    sp = f"reports/{SETS_PREFIX}{sym}.csv"', '12 path'),
])

print()
print('D-PY-33 applied. Equivalence gates (BOTH must pass):')
print('  python test_setup.py')
print('  python 05_multisymbol.py  (compare: EURUSD 0.095 / GBPUSD 0.120 / USDJPY -0.048)')
print("Then: python 05m_m2stamp.py; in 12 set SETS_PREFIX = 'setups_m2_'")
