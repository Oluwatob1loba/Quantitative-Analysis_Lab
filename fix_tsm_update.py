"""fix_tsm_update.py - repair TrendState.update in rino_setup.py (D-PY-34 follow-up).

apply_dpy34.py's regex splices for the TSM stamps corrupted indentation on the
locally-modified file (stand-in tests used a different layout). Rather than debug
blind indentation, this replaces the ENTIRE update() method with canonical text -
deterministic regardless of the damage. Parity target: V3.2 TSM application block.

Idempotent: refuses to run if the canonical method is already present.
"""
import ast
import sys

CANONICAL = '    def update(self, act_side, act_anchor, anchor_records, anchor_keys_on, t=None):\n        """Apply the highest-authority event (A3 -> A2 -> A1 -> TF1 per the caller).\n        BOS refresh stamps last_bos; anchor events flip; a TF1 flip is subordinated to\n        any active anchor still holding an undisturbed covered PDOL on the old side."""\n        if self.dir == act_side:\n            self.last_bos = t            # TSM-2 BOS refresh stamp (D-901 diagnostics)\n            self.pend_side = 0\n            return\n        if act_anchor:\n            self.dir = act_side; self.since = t; self.pend_side = 0\n            return\n        if self.dir == 0:\n            self.dir = act_side; self.since = t; self.pend_side = 0\n            return\n        holds = any(r.role == "PDOL" and r.state == 0 and r.coverage and\n                    (r.owner.kind if hasattr(r.owner, "kind") else r.owner.side)\n                    == ("High" if self.dir == 1 else "Low")\n                    for r in anchor_records)\n        if holds:\n            self.pend_side = act_side\n        else:\n            self.dir = act_side; self.since = t; self.pend_side = 0\n'

path = "rino_setup.py"
src = open(path).read()

if "self.last_bos = t            # TSM-2 BOS refresh stamp" in src:
    print("canonical update() already present - nothing to do.")
    sys.exit(0)

anchor = "    def update(self, act_side, act_anchor, anchor_records, anchor_keys_on, t=None):"
assert src.count(anchor) == 1, f"anchor found {src.count(anchor)}x - STOP, nothing written"

lines = src.splitlines(keepends=True)
start = next(i for i, ln in enumerate(lines) if ln.rstrip("\n") == anchor.rstrip("\n"))
stop = start + 1
while stop < len(lines):
    ln = lines[stop]
    if ln.strip() == "":
        stop += 1
        continue
    if ln.startswith("    def ") or ln.startswith("class ") or (ln and not ln[0].isspace()):
        break
    stop += 1

lines[start:stop] = [CANONICAL]
open(path, "w").write("".join(lines))
ast.parse(open(path).read())
print("TrendState.update replaced with canonical method; rino_setup.py parses clean.")
print("Run: python test_setup.py (then test_episode.py, test_dol.py).")
