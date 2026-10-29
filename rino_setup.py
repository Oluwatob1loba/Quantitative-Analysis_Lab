"""
rino_setup.py — RINO setup engine (live frozen pine port, as amended by D-PY-20/22).

Admission mode D-PY-33: 'm2' bypasses the TSM direction gate and the FVG POI gate
AT RECORD TIME (default 'full' = frozen V3.2-TSM-L1-O9 behavior).

Turns completed episodes into graded setups:
  geometry (P4.11) | targets f_v3PickTarget (slot priority, nearest, DOC-08 quirk)
  TSM direction gate (live pine) | POI gate (F-strict slice, live executed semantics:
  fill-by-close invalidation is DIAGNOSTIC-ONLY — the live comment claims otherwise;
  divergence flagged, D-PY-16) | class A/B/A+ | t1-by-class with profit-side flip
  confluence layers | intact (DOC-09 timestamp predicate) | alignment (DOC-08 quirk)
  opposition | gap tags | ranking+grade (DOC-08 anchorBonus quirk, class-B grade cap,
  ADD-01 keyTimeSweep weight per D-PY-06) | owner lifecycle (D-PY-04 DONE guard,
  dualHit, retention) | rino.v3.phase1 TS/RANGE_STATE/GRADE export (P4.14 + live keys).

Pure logic: consumes dol record lists + Completion objects; no pandas.
"""
from dataclasses import dataclass, field
from typing import List, Optional


# -------------------------------------------------------------------------- gaps
@dataclass
class Gap:
    kind: str; native_tf: str; direction: int
    lower: float; upper: float
    origin: object; available_at: object; sequence_origin: object
    active: bool = True; ended_at: object = None


class FvgFeed:
    """Section 20 TF1 pass: FVG/VI formation on confirmed candles, fill BY CLOSE
    ('PAINT ON THE WALL'), shared cap with oldest-TF1 victim, native-age cutoff.
    TF1 VI computed regardless of draw toggle (DOC-14); only FVGs gate."""

    def __init__(self, cfg, tf1_key):
        self.cfg = cfg; self.k1 = tf1_key
        self.gaps: List[Gap] = []
        self.hist = []          # confirmed (cbucket, o, h, l, c) in roll order

    def on_roll(self, t, o, h, l, c, cbucket):
        self.hist.append((cbucket, o, h, l, c))
        # fill by CLOSE through the far bound (live executed rule)
        for g in self.gaps:
            if g.active and g.available_at is not None and g.available_at <= t:
                if (g.direction == 1 and c <= g.lower) or (g.direction == -1 and c >= g.upper):
                    g.active = False; g.ended_at = t
        # formation from candle 0 vs candles 1/2
        if len(self.hist) >= 3:
            (_, o2, h2, l2, c2), (_, o1, h1, l1, c1) = self.hist[-3], self.hist[-2]
            made = []
            if l > h2:
                made.append(Gap("FVG", self.k1, 1, h2, l, cbucket, t, self.hist[-3][0]))
            if h < l2:
                made.append(Gap("FVG", self.k1, -1, h, l2, cbucket, t, self.hist[-3][0]))
            # VI: body gap close1->open0 with overlapping wicks
            ov_lo, ov_hi = max(l, l1), min(h, h1)
            width = abs(o - c1)
            if ov_hi >= ov_lo and o != c1 and (self.cfg.min_vi_width_pct <= 0 or
                    width >= (h - l) * self.cfg.min_vi_width_pct / 100.0):
                made.append(Gap("VI", self.k1, 1 if o > c1 else -1,
                                min(o, c1), max(o, c1), cbucket, t, self.hist[-3][0]))
            self.gaps.extend(made)
            while len(self.gaps) > self.cfg.retained_zones:
                self.gaps.pop(0)                      # TF1-only pool: oldest victim
        # native-age cutoff
        if len(self.hist) > self.cfg.zone_age:
            cut = self.hist[-self.cfg.zone_age][0]
            self.gaps = [g for g in self.gaps if g.origin >= cut]

    def candidates_today(self):
        return list(self.gaps)


def poi_gate(gaps, direction, origin, boundary, slice_lo, slice_hi, pending, tf1_fvg_on, k1):
    """Live executed f_v3PoiGate: penetration = band INTERSECTS the operative slice.
    Fill (ended_at) is DIAGNOSTIC-ONLY in the executed code — the live comment
    ('permanently invalidated, cannot be souped') is NOT enforced. D-PY-16 flag."""
    hit = False; scanned = dirm = pen = fillok = tim = lay = 0; witness = ""
    for g in gaps:
        if g.kind != "FVG":
            continue
        scanned += 1
        if g.direction != direction:
            continue
        dirm += 1
        if not (g.upper >= slice_lo and g.lower <= slice_hi):
            continue
        pen += 1
        if g.ended_at is None or g.ended_at >= origin:
            fillok += 1
        if g.available_at <= boundary:
            tim += 1
            # D-610 (L1, ratified V3.2-TSM-L1-O9): pre-origin close-through VETOES authorization.
            # Only fills caused by the soup's own path (ended_at >= origin) or live gaps count.
            if g.native_tf == k1 and tf1_fvg_on and (g.ended_at is None or g.ended_at >= origin):
                lay += 1; hit = True
                if not witness:
                    witness = f"{g.native_tf} {str(g.origin)[:10]} {g.lower}-{g.upper}" + \
                              (" live" if g.ended_at is None else " filled")
    # pending candidates: same slice test (live v3PoiPending path)
    for cd, clo, chi, cav in pending:
        if cd == direction and cav <= boundary and (chi >= slice_lo and clo <= slice_hi):
            if tf1_fvg_on:
                hit = True
    diag = (f"scanned {scanned} dir {dirm} pen {pen} fill {fillok} time {tim} "
            f"auth {lay} pend {len(pending)}" + (f" via {witness}" if witness else ""))
    return hit, diag


# -------------------------------------------------------------------------- targets
def _participates(cfg, rank_of, tfk):
    k1 = rank_of["tf1_key"]
    return tfk == k1 or cfg.tf2_draws_in_tf1_target_math or \
        rank_of.get(tfk, 0) > rank_of[k1]


def pick_target(cfg, direction, entry, manipulation_start, tf1_records, anchor_records, rank_of):
    """f_v3PickTarget: slot priority by RAW timeframe string (DOC-08 quirk: no
    enable/selected-slot check), then nearest |entry-price|, then latest origin.
    Secondary = nearest on-side TF1 PDOL."""
    sel_p = sel_tf = sel_org = None; sel_pri = 99; best_d = None
    sec_p = sec_org = None; sec_d = None
    anchor_tfs = [(tf_key_(a.tf), a.enabled) for a in cfg.anchors]
    pools = [(r, False) for r in tf1_records] + [(r, True) for r in anchor_records]
    for r, is_anchor in pools:
        if r.role != "PDOL" or r.state != 0 or not r.coverage:
            continue
        side = r.owner.kind if hasattr(r.owner, "kind") else r.owner.side
        if not _participates(cfg, rank_of, r.tf_key):
            continue
        if r.owner.available_at is None or r.owner.available_at > manipulation_start:
            continue
        price = r.owner.price
        if not (price > entry if direction == 1 else price < entry):
            continue
        if is_anchor:
            raw = r.tf_key
            # V3.2 parity (EXECUTED f_v3PickTarget): A1 slot = 0 FIRST, A2 = 1, A3 = 2, TF1 = 3.
            # The O-9 'highest-first' text was never applied to this function in the live
            # Pine (D-PY-16: executed code wins). Architect ruling pending: patch Pine or re-ratify.
            pri = 0 if raw == tf_key_(cfg.anchors[0].tf) else \
                  1 if len(cfg.anchors) > 1 and raw == tf_key_(cfg.anchors[1].tf) else \
                  2 if len(cfg.anchors) > 2 and raw == tf_key_(cfg.anchors[2].tf) else 4
        else:
            pri = 3
        d = abs(price - entry)
        if (pri < sel_pri or (pri == sel_pri and (sel_p is None or d < best_d or
                (d == best_d and r.owner.origin > sel_org)))):
            sel_p, sel_tf, sel_org, sel_pri, best_d = price, r.tf_key, r.owner.origin, pri, d
        if not is_anchor:
            if sec_p is None or d < sec_d or (d == sec_d and r.owner.origin > sec_org):
                sec_p, sec_org, sec_d = price, r.owner.origin, d
    return sel_p, (sel_tf or ""), sel_org, sec_p, sec_org


def tf_key_(tf):
    return tf.strip()


def near(a, b, mintick, tol):
    return 100.0 * abs(a - b) / max(abs(a), abs(b), mintick) <= tol


def confluence_layers(records, target, native_tf, k1, mintick, tol, rank_of, cfg):
    seen = set(); n = 0
    for r in records:
        if r.role != "PDOL" or r.state != 0 or not r.coverage or not _participates(cfg, rank_of, r.tf_key):
            continue
        if r.tf_key == native_tf:
            continue
        if near(r.owner.price, target, mintick, tol) and r.tf_key not in seen:
            seen.add(r.tf_key); n += 1
    return n


def intact_primary(tf1_records, direction, entry, boundary):
    """DOC-09: timestamp predicate — dolChangedAt absent or >= boundary. No state-0 test."""
    for r in tf1_records:
        if r.role != "PDOL" or not r.coverage:
            continue
        if r.changed_at is not None and r.changed_at < boundary:
            continue
        p = r.owner.price
        if (p > entry) if direction == 1 else (p < entry):
            return True
    return False


def alignment(records, direction, entry, selected_tf, k1, rank_of, cfg):
    """DOC-08: outer condition references the TF2-sweep DISPLAY toggle (cfg.tf2_sweep_layer)."""
    highest = -1.0; above = below = False
    for r in records:
        if r.role != "PDOL" or r.state != 0 or not r.coverage:
            continue
        if not (r.tf_key == k1 or cfg.tf2_sweep_layer or cfg.tf2_draws_in_tf1_target_math):
            continue
        if not _participates(cfg, rank_of, r.tf_key):
            continue
        rk = rank_of.get(r.tf_key, 0)
        p = r.owner.price
        if rk > highest:
            highest = rk; above = p > entry; below = p < entry
        elif rk == highest:
            above = above or p > entry; below = below or p < entry
    same = selected_tf != "" and rank_of.get(selected_tf, -1) == highest  # selected TF rank vs highest draw rank
    return same or ((above and not below) if direction == 1 else (below and not above))


def setup_class(o, c, prev_o, prev_c):
    return "A" if (c > o) != (prev_c > prev_o) else "B"


def t1_by_class(cls, ts_bullish, h, l, entry, direction):
    if cls in ("A", "A+"):
        cand = h if ts_bullish else l
    else:
        cand = l if ts_bullish else h
    flip = False
    if cand is not None and entry is not None:
        ok = cand > entry if direction == 1 else cand < entry
        if not ok:
            cand = (l if ts_bullish else h) if cls in ("A", "A+") else (h if ts_bullish else l)
            flip = True
    return cand, flip


def grade(setup, cfg):
    """f_v3Grade: DOC-08 anchorBonus raw-TF strings; class B capped at grade B
    (V3.2 Fix B); ADD-01 keyTimeSweep weight (D-PY-06 research amendment)."""
    if not setup["actionable"]:
        return None, None
    # S-7 (ratified): 4/3/2 = Anchor3/Anchor2/Anchor1 — highest authority earns the most.
    bonus = 4.0 if len(cfg.anchors) > 2 and setup["targetTf"] == tf_key_(cfg.anchors[2].tf) else \
            3.0 if len(cfg.anchors) > 1 and setup["targetTf"] == tf_key_(cfg.anchors[1].tf) else \
            2.0 if cfg.anchors and setup["targetTf"] == tf_key_(cfg.anchors[0].tf) else 1.0
    score = (setup["confluenceLayers"] * cfg.w_dol_confluence
             + (cfg.w_htf_alignment if setup["aligned"] else 0)
             + (cfg.w_fvg_vi if (setup["fvg"] or setup["vi"]) else 0)
             + (cfg.key_time_sweep_weight if setup.get("keyTimeSweep") else 0))
    score += {"Critical": cfg.w_critical_break, "Major": cfg.w_major_break,
              "Minor": cfg.w_minor_break}.get(setup["breakClass"], 0)
    score += cfg.w_opposes_owner if setup["opposition"] else 0
    score += cfg.w_undisturbed_tf1 if setup["intactPrimary"] else 0
    score += bonus * cfg.w_anchor_priority
    a, b = max(cfg.grade_a_threshold, cfg.grade_b_threshold), min(cfg.grade_a_threshold, cfg.grade_b_threshold)
    g = "A" if score >= a else "B" if score >= b else "C"
    if setup["setupClass"] == "B" and g == "A":
        g = "B"
    return g, score


# -------------------------------------------------------------------------- TSM
class TrendState:
    """Live TSM port: scan authority Anchor3->Anchor2->Anchor1->TF1; anchor events
    flip outright; TF1 counter-events are vetoed into `pending` while any active
    anchor holds an undisturbed PDOL on the old side; undefined falls to prioDir."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.dir = 0
        self.since = None
        self.last_bos = None
        self.pend_side = 0
        self.pend_at = None

    def event(self, records, key, cc):
        bull = bear = False
        for r in records:
            if r.tf_key != key or r.role != "PDOL" or r.state != 0 or not r.coverage:
                continue
            side = r.owner.kind if hasattr(r.owner, "kind") else r.owner.side
            if side == "High" and cc > r.owner.price:
                bull = True
            if side == "Low" and cc < r.owner.price:
                bear = True
        return 1 if bull and not bear else -1 if bear and not bull else 0

    def update(self, act_side, act_anchor, anchor_records, anchor_keys_on, t=None):
        """Apply the highest-authority event (A3 -> A2 -> A1 -> TF1 per the caller).
        BOS refresh stamps last_bos; anchor events flip; a TF1 flip is subordinated to
        any active anchor still holding an undisturbed covered PDOL on the old side."""
        if self.dir == act_side:
            self.last_bos = t            # TSM-2 BOS refresh stamp (D-901 diagnostics)
            self.pend_side = 0
            return
        if act_anchor:
            self.dir = act_side; self.since = t; self.pend_side = 0
            return
        if self.dir == 0:
            self.dir = act_side; self.since = t; self.pend_side = 0
            return
        holds = any(r.role == "PDOL" and r.state == 0 and r.coverage and
                    (r.owner.kind if hasattr(r.owner, "kind") else r.owner.side)
                    == ("High" if self.dir == 1 else "Low")
                    for r in anchor_records)
        if holds:
            self.pend_side = act_side
        else:
            self.dir = act_side; self.since = t; self.pend_side = 0

# -------------------------------------------------------------------------- export
def ts_export(s, k1):
    n = lambda v: "null" if v is None else repr(round(v, 10))
    q = lambda s_: '"' + str(s_) + '"'
    f = {"kind": "TS", "nativeTf": k1, "originTime": s["origin"], "detectedAt": s["availableAt"],
         "setupId": s["setupId"], "variant": s["variant"], "direction": s["direction"],
         "actionable": s["actionable"], "referenceTime": s["referenceTime"],
         "rangeHigh": s["rangeHigh"], "rangeLow": s["rangeLow"],
         "open": s["manOpen"], "high": s["manHigh"], "low": s["manLow"], "close": s["manClose"],
         "target": s["target"], "targetTf": s["targetTf"], "targetOrigin": s["targetOrigin"],
         "secondaryTarget": s["secondaryTarget"], "secondaryOrigin": s["secondaryOrigin"],
         "secondaryTf": s["secondaryTf"] if s["secondaryTarget"] is not None else "",
         "entry": s["entry"], "zoneLow": s["zoneLow"], "zoneHigh": s["zoneHigh"],
         "stop": s["stop"], "r3": s["r3"], "r5": s["r5"],
         "confluence": s["confluenceLayers"] > 0, "aligned": s["aligned"],
         "fvg": s["fvg"], "vi": s["vi"], "session": None, "tsTiming": None, "crtTiming": None,
         "premiumDiscount": s["location"], "patternContext": False,
         "opposition": s["opposition"], "manipulationCandles": s["manipulationCandles"],
         "twoSided": s["twoSided"], "setupClass": s["setupClass"],
         "confluenceLayers": s["confluenceLayers"], "intactPrimary": s["intactPrimary"],
         "contextReason": None if s["actionable"] else s["contextReason"],
         "t1": s["t1"], "t1Flipped": s["t1Flipped"], "poiDiag": s["poiDiag"],
         "tf2PatternFlags": None}
    return f


def range_state(s, to, stamp):
    if s["state"] == to:
        return None
    f = {"kind": "RANGE_STATE", "nativeTf": s["k1"], "originTime": s["origin"],
         "detectedAt": stamp, "setupId": s["setupId"], "from": s["state"], "to": to,
         "target": s["target"], "dualHit": s["dualHit"]}
    s["state"] = to
    if to in ("DONE", "INVALIDATED", "EXPIRED"):
        s["endTime"] = stamp
    return f


# -------------------------------------------------------------------------- engine
class SetupEngine:
    def __init__(self, cfg, mintick, tf1_key, rank_of):
        self.cfg = cfg; self.mintick = mintick; self.k1 = tf1_key
        self.rank_of = rank_of
        self.feed = FvgFeed(cfg, tf1_key)
        self.tsm = TrendState(cfg)
        self.setups: List[dict] = []        # live records (retention-capped, owner domain)
        self.setups_all: List[dict] = []    # research history: EVERY setup ever created
        self.owner: Optional[dict] = None
        self.events: List[dict] = []
        self.anchor_ev = {}          # slot key -> latest event side (set at anchor rolls)
        self.counters = {"TS": 0, "actionable": 0, "CONTEXT": 0}

    # -- helpers ------------------------------------------------------------
    def _all_records(self, dol):
        return list(dol.records.values())

    def _anchor_records(self, dol):
        k1 = self.k1
        keys = {tf_key_(a.tf) for a in self.cfg.anchors if a.enabled and tf_key_(a.tf) != k1}
        return [r for r in dol.records.values() if r.tf_key in keys]

    def _tf1_records(self, dol):
        return [r for r in dol.records.values() if r.tf_key == self.k1]

    def _owner_clean(self, dol):
        if self.owner is None or self.owner.get("endTime") is not None:
            return False
        tgt = self.owner
        for r in self._all_records(dol):
            if r.owner.origin == tgt["targetOrigin"] and r.tf_key == tgt["targetTf"] \
                    and r.role == "PDOL" and r.state == 0 and r.coverage:
                return True
        return False

    # -- TF2 roll: break-class updates + TSM anchor events -------------------
    def on_tf2(self, t, cbucket, close, tf2_index, dol):
        ev_keys = [tf_key_(a.tf) for a in self.cfg.anchors
                   if a.enabled and tf_key_(a.tf) != self.k1]
        for key in ev_keys:
            side = self.tsm.event(self._anchor_records(dol), key, close)
            if side != 0:
                self.anchor_ev[key] = side
        for s in self.setups:
            if not s["actionable"] or s.get("endTime") is not None:
                continue
            if s["availableAt"] is None or t < s["availableAt"]:
                continue
            for sw in tf2_index.get((cbucket, t), []):
                if sw.side == ("High" if s["direction"] == 1 else "Low"):
                    cls = "Critical" if sw.is_critical else sw.klass
                    rank = {"Critical": 3, "Major": 2, "Minor": 1}.get(cls, 0)
                    pr = {"Critical": 3, "Major": 2, "Minor": 1}.get(s["breakClass"], 0)
                    if rank >= pr:
                        s["breakClass"] = cls
                        if s["breakAt"] is None:
                            s["breakAt"] = t            # first post-entry break arrival
                        if cls == "Critical":
                            s["breakCritAt"] = t        # confirmed-spark stamp
                        g, sc = grade(s, self.cfg)
                        if g != s["grade"]:
                            s["grade"] = g; s["score"] = sc
                            self.events.append({"kind": "GRADE", "setupId": s["setupId"],
                                                "grade": g, "score": sc, "detectedAt": t})

    # -- TF1 roll (post-touch): owner monitor + construction ----------------
    def on_tf1_after(self, t, row, comps, dol, prio_dir, key_time_raid, layers=None):
        c, h, l = row["tf1_close"], row["tf1_high"], row["tf1_low"]
        origin = row["tf1_cbucket"]
        # owner monitor (failure precedence, dualHit, D-PY-04 guard)
        if self.owner is not None and origin >= self.owner["availableAt"] and \
                (self.owner.get("endTime") is None or
                 (self.owner["state"] == "DONE" and self.owner["endTime"] >= origin)):
            failed = c < self.owner["manLow"] if self.owner["direction"] == 1 else c > self.owner["manHigh"]
            hit_t = h >= self.owner["target"] if self.owner["direction"] == 1 else l <= self.owner["target"]
            if failed:
                self.owner["dualHit"] = hit_t
                e = range_state(self.owner, "INVALIDATED", t)
                if e: self.events.append(e)
            elif hit_t and self.owner.get("endTime") is None:
                e = range_state(self.owner, "DONE", t)
                if e: self.events.append(e)
        # FVG feed: same-roll formation, then candidates offered (DR-27)
        self.feed.on_roll(t, row["tf1_open"], h, l, c, origin)
        prior_live = self.owner if (self.owner and self.owner.get("endTime") is None) else None
        prior_clean = self._owner_clean(dol) if prior_live is not None else False
        prior_dir = prior_live["direction"] if prior_live else 0
        tf1_recs = self._tf1_records(dol)
        anc_recs = self._anchor_records(dol)
        from rino_episode import priority_direction as _pd
        _pl = layers          # loop-invariant: 'layers' is shadowed by the confluence count below
        for comp in comps:
            ep = comp.episode
            direction = comp.direction
            # D-506: prioDir reference = raid extreme (per completion, not roll midpoint)
            ref = ep.l if ep.swept_low else ep.h if ep.swept_high else (ep.h + ep.l) / 2.0
            prio = _pd(ref, _pl, self.k1) if _pl is not None else (prio_dir or 0)
            zone_lo = ep.l if direction == 1 else max(ep.o, ep.c)
            zone_hi = min(ep.o, ep.c) if direction == 1 else ep.h
            entry = (zone_lo + zone_hi) / 2.0
            stop = ep.l - self.cfg.stop_buffer_ticks * self.mintick if direction == 1 \
                   else ep.h + self.cfg.stop_buffer_ticks * self.mintick
            risk = abs(stop - entry)
            tgt, tgt_tf, tgt_org, sec, sec_org = pick_target(
                self.cfg, direction, entry, ep.origin, tf1_recs, anc_recs, self.rank_of)
            actionable = tgt is not None
            reason = "" if actionable else "no clean PDOL target (TF1 or higher)"
            # TSM direction gates (live pine) - D-PY-33: bypassed when admission == "m2"
            if self.cfg.admission == "full":
                if actionable and self.tsm.dir != 0 and self.tsm.dir != direction:
                    actionable = False; reason = f"opposes trend (trend {self.tsm.dir} vs dir {direction})"
                if actionable and self.tsm.dir == 0 and prio != 0 and prio != direction:
                    actionable = False; reason = f"opposes TF1 draw (prio {prio} vs dir {direction})"
            slice_lo = ep.l if direction == 1 else max(ep.o, ep.c)
            slice_hi = min(ep.o, ep.c) if direction == 1 else ep.h
            pend = [(g.direction, g.lower, g.upper, g.available_at) for g in self.feed.candidates_today()]
            hit, diag = poi_gate(self.feed.gaps, direction, ep.origin, ep.boundary,
                                 slice_lo, slice_hi, pend, self.cfg.tf1_fvg, self.k1)
            # POI gate - D-PY-33: bypassed when admission == "m2"
            if self.cfg.admission == "full" and actionable and not hit:
                actionable = False; reason = "no POI souped: " + diag
            conf_tgt = tgt if tgt is not None else entry
            conf_tf = tgt_tf if tgt is not None else self.k1
            all_recs = tf1_recs + anc_recs
            layers = confluence_layers(all_recs, conf_tgt, conf_tf if tgt is not None else "",
                                       self.k1, self.mintick, self.cfg.v3_dol_proximity_pct,
                                       self.rank_of, self.cfg)
            intact = intact_primary(tf1_recs, direction, entry, ep.boundary)
            # V3.2 parity (C-6/D-101): prev = candle before the COMPLETING candle -
            # live tf1PrevO/tf1PrevC = open[2]/close[2] at the completion roll
            # (hist[-1] is this roll's completing candle). NOT the candle before the
            # episode origin: that diverges for every WindowMulti setup.
            _po, _pc = (self.feed.hist[-2][1], self.feed.hist[-2][4]) \
                if len(self.feed.hist) >= 2 else (None, None)
            cls = setup_class(ep.o, ep.c, _po, _pc)
            if cls == "A" and layers > 0:
                cls = "A+"
            ts_bull = ep.c > ep.o
            t1, t1_flip = t1_by_class(cls, ts_bull, ep.h, ep.l, entry, direction)
            # gap tags (pre-existing overlap during episode)
            fvg_tag = vi_tag = False
            for g in self.feed.gaps:
                if g.available_at is None or g.available_at > ep.origin:
                    continue
                live = g.active or (g.ended_at is not None and g.ended_at > ep.origin
                                    and g.ended_at <= ep.boundary)
                if live and (slice_hi >= g.lower and slice_lo <= g.upper):
                    fvg_tag = fvg_tag or g.kind == "FVG"
                    vi_tag = vi_tag or g.kind == "VI"
            kts = key_time_raid(direction, ep) if key_time_raid else False
            # D-PY-27 (architect ruling): attach the PDOL->TS candle SERIES extremes.
            # series = confirmed TF1 candles from the undisturbed-PDOL candle (targetOrigin,
            # inclusive) through the TS opening candle (episode.origin, inclusive). The PDOL
            # draw remains the FINAL/DONE target; these fields feed future scaling-out logic.
            series_hi = series_lo = None
            if tgt_org is not None:
                lo_b, hi_b = min(tgt_org, ep.origin), max(tgt_org, ep.origin)
                hv, lv = None, None
                for (cb, _o, _h, _l, _c) in self.feed.hist:
                    if lo_b <= cb <= hi_b:
                        hv = _h if hv is None else max(hv, _h)
                        lv = _l if lv is None else min(lv, _l)
                series_hi, series_lo = hv, lv
            alig = bool(actionable and alignment(
                all_recs, direction, entry, tgt_tf if tgt is not None else "",
                self.k1, self.rank_of, self.cfg))
            s = {"k1": self.k1, "setupId": f"{self.k1}:{ep.origin}:{direction}",
                 "origin": ep.origin, "availableAt": ep.boundary,
                 "referenceTime": ep.reference_time, "direction": direction,
                 "variant": comp.variant, "manOpen": ep.o, "manHigh": ep.h,
                 "manLow": ep.l, "manClose": ep.c, "rangeHigh": ep.range_high,
                 "rangeLow": ep.range_low, "manipulationCandles": ep.candles,
                 "twoSided": ep.swept_high and ep.swept_low,
                 "actionable": actionable, "target": tgt, "targetTf": tgt_tf,
                 "targetOrigin": tgt_org, "secondaryTarget": sec, "secondaryOrigin": sec_org,
                 "secondaryTf": self.k1 if sec is not None else "",
                 "entry": entry if actionable else None,
                 "zoneLow": zone_lo if actionable else None,
                 "zoneHigh": zone_hi if actionable else None,
                 "stop": stop if actionable else None,
                 "r3": entry + direction * 3 * risk if actionable else None,
                 "r5": entry + direction * 5 * risk if actionable else None,
                 "confluenceLayers": layers, "intactPrimary": intact, "setupClass": cls,
                 "aligned": alig,
                 "fvg": fvg_tag, "vi": vi_tag,
                 "location": (entry < (ep.range_high + ep.range_low) / 2) if direction == 1
                             else (entry > (ep.range_high + ep.range_low) / 2),
                 "opposition": bool(prior_clean and prior_live and direction != prior_dir),
                 "breakClass": "None", "state": "MANIPULATION" if actionable else "CONTEXT",
                 "endTime": None if actionable else ep.boundary,
                 "dualHit": False, "caution": bool(self.tsm.pend_side != 0
                                                   and self.tsm.pend_side == direction),
                 "contextReason": reason, "poiDiag": diag, "t1": t1, "t1Flipped": t1_flip,
                 "seriesHigh": series_hi, "seriesLow": series_lo,
                 "seriesStart": tgt_org, "seriesEnd": ep.origin,
                 "breakAt": None, "breakCritAt": None,
                 "keyTimeSweep": kts, "grade": "", "score": None}
            g, sc = grade(s, self.cfg)
            s["grade"], s["score"] = g or "", sc
            self.counters["TS"] += 1
            self.counters["actionable" if actionable else "CONTEXT"] += 1
            self.events.append(ts_export(s, self.k1))
            if actionable:
                self.owner = s
                self.events.append({"kind": "RANGE_STATE", "setupId": s["setupId"],
                                    "from": "Recorded", "to": "MANIPULATION",
                                    "detectedAt": ep.boundary})
                if g:
                    self.events.append({"kind": "GRADE", "setupId": s["setupId"],
                                        "grade": g, "score": sc, "detectedAt": ep.boundary})
            self.setups.append(s)
            self.setups_all.append(s)
            while len(self.setups) > self.cfg.retained_ts_events:
                old = self.setups.pop(0)
                if self.owner is old:
                    e = range_state(old, "EXPIRED", t)
                    if e: self.events.append(e)
                    self.owner = None
        # TSM update from this TF1 roll's own event
        ev_t = self.tsm.event(tf1_recs, self.k1, c)
        act_anchor_side = 0
        for a in reversed(self.cfg.anchors):        # TSM-1: highest authority first A3->A2->A1
            side = self.anchor_ev.get(tf_key_(a.tf), 0)
            if side != 0:
                act_anchor_side = side
                break
        act_side = act_anchor_side if act_anchor_side != 0 else ev_t
        self.tsm.update(act_side, act_anchor_side != 0, anc_recs,
                        [a.enabled for a in self.cfg.anchors], t=t)
        self.anchor_ev = {}
        # horizon eviction
        anchor_cut = None
        if len(dol._tf1_origins) >= self.cfg.tf1_lookback:
            anchor_cut = dol._tf1_origins[-self.cfg.tf1_lookback]
        if anchor_cut is not None:
            for s in list(self.setups):
                if s["availableAt"] <= anchor_cut:
                    if s.get("endTime") is None:
                        e = range_state(s, "EXPIRED", t)
                        if e: self.events.append(e)
                    self.setups.remove(s)
                    if self.owner is s:
                        self.owner = None

    def all_setups(self):
        return list(self.setups_all)

    def _prev_oc(self, dol, origin):
        # previous confirmed TF1 candle's O/C from the feed history
        for i in range(len(self.feed.hist) - 1, 0, -1):
            if self.feed.hist[i][0] < origin:
                return self.feed.hist[i][1], self.feed.hist[i][4]
        return None, None
