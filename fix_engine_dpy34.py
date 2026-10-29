"""fix_engine_dpy34.py v2 - repair rino_engine.py D-PY-34 splice damage (seen in repo).

Two visible wounds, two exact replacements:
  1. "self.rank_of.setdefault(k1, 1.0)" landed at column 0 -> re-indent to 8 spaces.
  2. The S-6 comment line in _priority_layers landed at column 0 -> re-indent (cosmetic).
Idempotent. Writes only if both anchors behave; parses before writing.
"""
import ast
import sys

src = open("rino_engine.py").read()

if "}\n        self.rank_of.setdefault(k1, 1.0)\n" in src:
    print("already repaired - nothing to do.")
    sys.exit(0)

fixes = [
    ("}\nself.rank_of.setdefault(k1, 1.0)\n",
     "}\n        self.rank_of.setdefault(k1, 1.0)\n", "setdefault indent"),
    ("\n\n# V3.2 parity (S-6): executed f_v3PriorityDir scans TF1 FIRST, then A3, A2, A1\n        # (slot = 3 - layerIdx)",
     "\n        # V3.2 parity (S-6): executed f_v3PriorityDir scans TF1 FIRST, then A3, A2, A1\n        # (slot = 3 - layerIdx)", "S-6 comment indent"),
]
for old, new, tag in fixes:
    n = src.count(old)
    if n != 1:
        print(f"[{tag}] found {n}x - STOP, nothing written.")
        sys.exit(1)
    src = src.replace(old, new)

ast.parse(src)
open("rino_engine.py", "w").write(src)
print("rino_engine.py repaired - parses clean. Run: python 05_multisymbol.py")
