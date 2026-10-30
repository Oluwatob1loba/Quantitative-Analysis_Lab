"""apply_dpy39b.py - TSM demoted from GATE to GUIDANCE (architect ruling, 2026-10-29).

Replaces the two hard-veto blocks in rino_setup.on_tf1_after with caution stamps:
trend-opposed setups remain ACTIONABLE and carry caution=True. The Pine arm owes the
same amendment (Qwen lane). Idempotent; AST check before write; prints context on miss.
"""
import ast
import re
import sys

src = open("rino_setup.py").read()

if "D-PY-39b: TSM demoted from GATE to GUIDANCE" in src:
    print("already applied - nothing to do.")
    sys.exit(0)

pat = re.compile(
    r'            # TSM direction gates \(live pine\)[^\n]*\n'
    r'            if self\.cfg\.admission == "full":\n'
    r'                if actionable and self\.tsm\.dir != 0 and self\.tsm\.dir != direction:\n'
    r'                    actionable = False; reason = f"opposes trend \(trend \{self\.tsm\.dir\} vs dir \{direction\}\)"\n'
    r'                if actionable and self\.tsm\.dir == 0 and prio != 0 and prio != direction:\n'
    r'                    actionable = False; reason = f"opposes TF1 draw \(prio \{prio\} vs dir \{direction\}\)"\n')
new_block = (
    '            # D-PY-39b: TSM demoted from GATE to GUIDANCE (architect ruling 2026-10-29).\n'
    '            # Trend opposition stamps caution; it never suppresses. Pine arm: same amendment owed.\n'
    '            trend_caution = False\n'
    '            if actionable and self.tsm.dir != 0 and self.tsm.dir != direction:\n'
    '                trend_caution = True\n'
    '            if actionable and self.tsm.dir == 0 and prio != 0 and prio != direction:\n'
    '                trend_caution = True\n')
src, n = pat.subn(new_block, src, count=1)
if n != 1:
    print("TSM gate block not matched - STOP, nothing written. Context:")
    for i, ln in enumerate(open("rino_setup.py").read().splitlines(), 1):
        if "opposes trend" in ln or "TSM direction gates" in ln:
            print(f"  {i:>4}: {ln}")
    sys.exit(1)

pat2 = re.compile(r'(?P<full>(?:"caution": |caution=)bool\(self\.tsm\.pend_side[^)]*\))')
src, n2 = pat2.subn(lambda m: m.group('full') + ' or trend_caution', src, count=1)
if n2 != 1:
    print('caution dict entry not matched - STOP, nothing written. Lines with "caution":')
    for i, ln in enumerate(open("rino_setup.py").read().splitlines(), 1):
        if "caution" in ln:
            print(f"  {i:>4}: {ln}")
    sys.exit(1)

ast.parse(src)
open("rino_setup.py", "w").write(src)
print("D-PY-39b applied: TSM demoted to guidance (caution), s-dict wired. Parses clean.")
