"""apply_dpy34.py - D-PY-34 V3.2-EXECUTED parity fix batch, v2 (structure-anchored).

Local rino_setup.py / rino_engine.py carry uncommitted Qwen edits, so anchors are
exact-or-REGEX with context dumps on miss. Any miss prints nearby lines, writes NOTHING.

FIXES: rino_setup.py (1) class prev-candle = candle before COMPLETION (C-6/D-101),
(2) pick_target A1-first (EXECUTED f_v3PickTarget), (3) TSM since/last_bos stamps;
rino_engine.py (4) _priority_layers TF1 -> A3 -> A2 -> A1 (S-6), (5) rank_of fail-fast.

VALIDATION (behavior changes - no bit-identity gate):
  test_setup/test_episode/test_dol -> explain+update every fixture failure;
  05 (record deltas); then 05m + 12(SETS_PREFIX=setups_m2_) + 10 full rerun.
"""
import re
import sys

def show(path, needle):
    print(f"  --- {path}: lines containing {needle!r} ---")
    try:
        lines = open(path).read().splitlines()
    except FileNotFoundError:
        print("    (file not found)"); return
    for i, ln in enumerate(lines, 1):
        if needle in ln:
            print(f"    {i:>4}: {ln}")

ok = True
_find = '            _po, _pc = self._prev_oc(dol, ep.origin)\n'
_repl = "            # V3.2 parity (C-6/D-101): prev = candle before the COMPLETING candle -\n            # live tf1PrevO/tf1PrevC = open[2]/close[2] at the completion roll\n            # (hist[-1] is this roll's completing candle). NOT the candle before the\n            # episode origin: that diverges for every WindowMulti setup.\n            _po, _pc = (self.feed.hist[-2][1], self.feed.hist[-2][4]) \\\n                if len(self.feed.hist) >= 2 else (None, None)\n"
_s = open("rino_setup.py").read()
_n = _s.count(_find)
if _n != 1:
    print(f"  rino_setup.py: [class prev-candle] found {_n}x - context:"); show("rino_setup.py", "_prev_oc"); ok = False
else:
    open("rino_setup.py", "w").write(_s.replace(_find, _repl))
    print("  rino_setup.py: [class prev-candle] applied (exact)")

_TPL_ts_bos = 'if self.dir == act_side:\n@I@    self.last_bos = t  # TSM-2 BOS stamp (D-901)\n@I@    self.pend_side = 0\n@I@    return\n'
_TPL_ts_flip = 'if act_anchor:\n@I@    self.dir = act_side; self.since = t; self.pend_side = 0\n@I@    return\n@I@if self.dir == 0:\n@I@    self.dir = act_side; self.since = t; self.pend_side = 0\n'
_TPL_ts_sub = 'if holds:\n@I@    self.pend_side = act_side\n@I@else:\n@I@    self.dir = act_side; self.since = t; self.pend_side = 0\n'
_TPL_pl = '# V3.2 parity (S-6): executed f_v3PriorityDir scans TF1 FIRST, then A3, A2, A1\n@I@# (slot = 3 - layerIdx). Old A1,A2,A3,TF1 was the pre-S-6 reading.\n@I@layers.append(PriorityLayer(True, k1, draws_for(k1)))\n@I@for a in reversed(self.cfg.anchors):\n@I@    layers.append(PriorityLayer(enabled=a.enabled and tf_key(a.tf) != k1,\n@I@                                tf_key=tf_key(a.tf), draws=draws_for(tf_key(a.tf))))\n'
_TPL_ro = 'self.rank_of.setdefault(k1, 1.0)\n@I@# D-PY-34: fail-fast on unmapped timeframes (no silent defaults; SR-1).\n@I@unknown = [a.tf for a in cfg.anchors\n@I@           if tf_key(a.tf) not in self.rank_of and tf_key(a.tf) != k1]\n@I@if unknown:\n@I@    raise ValueError(f"rank_of: unmapped timeframe(s) {unknown} - extend the ladder")\n'
_pat = re.compile('(?:[ \\t]*#[^\\n]*\\n)?[ \\t]*pri = 0 if len\\(cfg\\.anchors\\)[^\\n]*\\\\\\n[ \\t]*1 if len\\(cfg\\.anchors\\)[^\\n]*\\\\\\n[ \\t]*2 if[^\\n]*else 4\\n')
_repl = "            # V3.2 parity (EXECUTED f_v3PickTarget): A1 slot = 0 FIRST, A2 = 1, A3 = 2, TF1 = 3.\n            # The O-9 'highest-first' text was never applied to this function in the live\n            # Pine (D-PY-16: executed code wins). Architect ruling pending: patch Pine or re-ratify.\n            pri = 0 if raw == tf_key_(cfg.anchors[0].tf) else \\\n                  1 if len(cfg.anchors) > 1 and raw == tf_key_(cfg.anchors[1].tf) else \\\n                  2 if len(cfg.anchors) > 2 and raw == tf_key_(cfg.anchors[2].tf) else 4\n"
_s = open('rino_setup.py').read()
_new, _n = _pat.subn(_repl, _s, count=1)
if _n != 1:
    print(f"  {'rino_setup.py'}: [PT] matched {_n}x - context:"); show('rino_setup.py', 'pri = 0 if'); ok = False
else:
    open('rino_setup.py', "w").write(_new)
    print(f"  {'rino_setup.py'}: [PT] applied (regex)")

_pat = re.compile('def update\\(self, act_side, act_anchor, anchor_records, anchor_keys_on\\):')
_repl = 'def update(self, act_side, act_anchor, anchor_records, anchor_keys_on, t=None):'
_s = open('rino_setup.py').read()
_new, _n = _pat.subn(_repl, _s, count=1)
if _n != 1:
    print(f"  {'rino_setup.py'}: [TS_SIG] matched {_n}x - context:"); show('rino_setup.py', 'def update(self'); ok = False
else:
    open('rino_setup.py', "w").write(_new)
    print(f"  {'rino_setup.py'}: [TS_SIG] applied (regex)")

_pat = re.compile('([ \\t]+)if self\\.dir == act_side:\\n[ \\t]+self\\.pend_side = 0\\n[ \\t]+return\\n')
_repl = lambda m: _TPL_ts_bos.replace("@I@", m.group(1))
_s = open('rino_setup.py').read()
_new, _n = _pat.subn(_repl, _s, count=1)
if _n != 1:
    print(f"  {'rino_setup.py'}: [TS_BOS] matched {_n}x - context:"); show('rino_setup.py', 'if self.dir == act_side:'); ok = False
else:
    open('rino_setup.py', "w").write(_new)
    print(f"  {'rino_setup.py'}: [TS_BOS] applied (regex)")

_pat = re.compile('([ \\t]+)if act_anchor:\\n[ \\t]+self\\.dir = act_side; self\\.pend_side = 0\\n[ \\t]+return\\n[ \\t]+if self\\.dir == 0:\\n[ \\t]+self\\.dir = act_side; self\\.pend_side = 0\\n')
_repl = lambda m: _TPL_ts_flip.replace("@I@", m.group(1))
_s = open('rino_setup.py').read()
_new, _n = _pat.subn(_repl, _s, count=1)
if _n != 1:
    print(f"  {'rino_setup.py'}: [TS_FLIP] matched {_n}x - context:"); show('rino_setup.py', 'if act_anchor:'); ok = False
else:
    open('rino_setup.py', "w").write(_new)
    print(f"  {'rino_setup.py'}: [TS_FLIP] applied (regex)")

_pat = re.compile('([ \\t]+)if holds:\\n[ \\t]+self\\.pend_side = act_side\\n[ \\t]+else:\\n[ \\t]+self\\.dir = act_side; self\\.pend_side = 0\\n')
_repl = lambda m: _TPL_ts_sub.replace("@I@", m.group(1))
_s = open('rino_setup.py').read()
_new, _n = _pat.subn(_repl, _s, count=1)
if _n != 1:
    print(f"  {'rino_setup.py'}: [TS_SUB] matched {_n}x - context:"); show('rino_setup.py', 'if holds:'); ok = False
else:
    open('rino_setup.py', "w").write(_new)
    print(f"  {'rino_setup.py'}: [TS_SUB] applied (regex)")

_pat = re.compile('self\\.tsm\\.update\\(act_side, act_anchor_side != 0, anc_recs,\\n[ \\t]+\\[a\\.enabled for a in self\\.cfg\\.anchors\\]\\)')
_repl = 'self.tsm.update(act_side, act_anchor_side != 0, anc_recs,\n                        [a.enabled for a in self.cfg.anchors], t=t)'
_s = open('rino_setup.py').read()
_new, _n = _pat.subn(_repl, _s, count=1)
if _n != 1:
    print(f"  {'rino_setup.py'}: [TS_CALL] matched {_n}x - context:"); show('rino_setup.py', 'self.tsm.update('); ok = False
else:
    open('rino_setup.py', "w").write(_new)
    print(f"  {'rino_setup.py'}: [TS_CALL] applied (regex)")

_pat = re.compile('([ \\t]+)for a in self\\.cfg\\.anchors:\\n[ \\t]+layers\\.append\\(PriorityLayer\\(enabled=a\\.enabled and tf_key\\(a\\.tf\\) != k1,\\n[ \\t]+tf_key=tf_key\\(a\\.tf\\), draws=draws_for\\(tf_key\\(a\\.tf\\)\\)\\)\\)\\n[ \\t]+layers\\.append\\(PriorityLayer\\(True, k1, draws_for\\(k1\\)\\)\\)')
_repl = lambda m: _TPL_pl.replace("@I@", m.group(1))
_s = open('rino_engine.py').read()
_new, _n = _pat.subn(_repl, _s, count=1)
if _n != 1:
    print(f"  {'rino_engine.py'}: [PL] matched {_n}x - context:"); show('rino_engine.py', 'for a in self.cfg.anchors'); ok = False
else:
    open('rino_engine.py', "w").write(_new)
    print(f"  {'rino_engine.py'}: [PL] applied (regex)")

_pat = re.compile('([ \\t]+)self\\.rank_of\\.setdefault\\(k1, 1\\.0\\)\\n')
_repl = lambda m: _TPL_ro.replace("@I@", m.group(1))
_s = open('rino_engine.py').read()
_new, _n = _pat.subn(_repl, _s, count=1)
if _n != 1:
    print(f"  {'rino_engine.py'}: [RO] matched {_n}x - context:"); show('rino_engine.py', 'rank_of.setdefault'); ok = False
else:
    open('rino_engine.py', "w").write(_new)
    print(f"  {'rino_engine.py'}: [RO] applied (regex)")

if not ok:
    sys.exit("STOP - one or more anchors missed; nothing written. Paste this output.")
print()
print("D-PY-34 v2 applied. Next: test_setup/test_episode/test_dol (explain+update every")
print("fixture failure), then 05 (record deltas), then 05m + 12(SETS_PREFIX=setups_m2_) + 10.")
