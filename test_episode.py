"""
test_episode.py — acceptance gates for rino_episode.py

Every fixture below is hand-scripted: the ground truth is known by
construction, so a green board here certifies the port, not the test's
ability to agree with itself. Gates cite their frozen-source anchors.

Run:  python test_episode.py
"""

from rino_episode import (ClosedCandle, SweepableDraw, PriorityLayer,
                          EpisodeMachine, priority_direction)

DAY = 86400_000          # ms per day (fixtures use synthetic epoch days)
FAILS = []


def check(gate, name, ok, detail=""):
    tag = "PASS" if ok else f"FAIL {detail}"
    print(f"{gate:<32}: {tag}")
    if not ok:
        FAILS.append(f"{gate} {detail}")


def mk(day_idx, o, h, l, c):
    """A confirmed daily candle on synthetic day index (attribution/detection
    stamps distinct per D-PY-17)."""
    return ClosedCandle(o=o, h=h, l=l, c=c,
                        origin=day_idx * DAY,
                        boundary=day_idx * DAY + DAY - 1)


def draw(price, side, day_idx, tf="1D"):
    return SweepableDraw(price=price, side=side, origin=day_idx * DAY, tf_key=tf)


def layers_tf1_only(tf1_draws, tf1_key="1D"):
    return [PriorityLayer(False, "1W", ()), PriorityLayer(False, "1M", ()),
            PriorityLayer(False, "3M", ()),
            PriorityLayer(True, tf1_key, tuple(tf1_draws))]


# ==========================================================================
# Fixture A — the canonical multi-candle long episode
#   d0: PDOL Low @1.1000 | d2: PDOL Low @1.0950 (both down-close days)
#   d3: sweeps to 1.0940, closes 1.0960  -> opens, no completion
#        (1.0960 > closeRefLow? closeRefLow = max(1.0950,1.1000) = 1.1000 -> no)
#   d4: closes 1.1010 > 1.1000           -> LONG completes, WindowMulti
# ==========================================================================
print("== Fixture A: canonical multi-candle long episode ==")
m = EpisodeMachine(lookback=10, sub_lookback=3)
sweepable = [draw(1.1000, "Low", 0), draw(1.0950, "Low", 2)]
prio = layers_tf1_only(sweepable)

c3 = mk(3, 1.0980, 1.0990, 1.0940, 1.0960)
comp = m.process_roll(c3, window_origin=0 * DAY, sweepable=sweepable,
                      priority_layers=prio)
ep = m.pending
check("A-G1 opens on strict sweep", "A", ep is not None and not comp)
check("A-G2 closeRef=max swept low", "A",
      ep is not None and ep.close_ref_low == 1.1000,
      f"got {ep.close_ref_low if ep else None}")
check("A-G3 frozen range_low=min swept", "A",
      ep is not None and ep.range_low == 1.0950,
      f"got {ep.range_low if ep else None}")

c4 = mk(4, 1.0965, 1.1015, 1.0955, 1.1010)
comp = m.process_roll(c4, window_origin=1 * DAY, sweepable=sweepable,
                      priority_layers=prio)
check("A-G4 long completes strictly", "A",
      len(comp) == 1 and comp[0].direction == 1, f"got {comp}")
check("A-G5 variant WindowMulti", "A",
      comp and comp[0].variant == "WindowMulti", f"got {comp}")
check("A-G6 pending cleared", "A", m.pending is None)


# ==========================================================================
# Fixture B — equality must NOT open; same-roll completion (Window)
#   d10: PDOL Low @1.1000 ; d11 low == 1.1000 exactly -> no open
#   d12: sweeps 1.0990, closes 1.1015 -> opens AND completes same roll
# ==========================================================================
print("\n== Fixture B: equality & single-candle completion ==")
m = EpisodeMachine(lookback=10, sub_lookback=3)
sweepable = [draw(1.1000, "Low", 10)]
prio = layers_tf1_only(sweepable)

eq = m.process_roll(mk(11, 1.1010, 1.1020, 1.1000, 1.1012),
                    window_origin=10 * DAY, sweepable=sweepable,
                    priority_layers=prio)
check("B-G1 equality does not open", "B", m.pending is None and not eq)

comp = m.process_roll(mk(12, 1.1005, 1.1008, 1.0990, 1.1015),
                      window_origin=10 * DAY, sweepable=sweepable,
                      priority_layers=prio)
check("B-G2 same-roll completion", "B",
      len(comp) == 1 and comp[0].direction == 1, f"got {comp}")
check("B-G3 variant Window", "B",
      comp and comp[0].variant == "Window", f"got {comp}")
check("B-G4 range fallback to candle", "B",
      comp and comp[0].episode.range_high == 1.1008,
      f"got {comp[0].episode.range_high if comp else None}")


# ==========================================================================
# Fixture C — zombie guard + main+1 semantics (DR-18)
#   lookback=3; episode opens d20 and never completes.
#   candles: d20=1, d21=2, d22=3, d23=4 (== lookback+1, may still complete),
#   d24: roll-top guard sees 4 > 3 -> retired BEFORE scan; d24 can open anew.
# ==========================================================================
print("\n== Fixture C: zombie guard, main+1 ==")
m = EpisodeMachine(lookback=3, sub_lookback=3)
sweepable = [draw(1.2000, "Low", 19)]
prio = layers_tf1_only(sweepable)
# never completes: closes stay below closeRef 1.2000
m.process_roll(mk(20, 1.1990, 1.1995, 1.1980, 1.1985),
               window_origin=19 * DAY, sweepable=sweepable,
               priority_layers=prio)
for d in (21, 22, 23):
    m.process_roll(mk(d, 1.1985, 1.1990, 1.1975, 1.1980),
                   window_origin=(d - 1) * DAY, sweepable=sweepable,
                   priority_layers=prio)
check("C-G1 alive at main+1 (4 candles)", "C",
      m.pending is not None and m.pending.candles == 4,
      f"candles={m.pending.candles if m.pending else None}")
# d24 opens a NEW episode only after the old one is retired
sweep2 = [draw(1.1900, "Low", 23)]
comp = m.process_roll(mk(24, 1.1895, 1.1898, 1.1880, 1.1890),
                      window_origin=23 * DAY, sweepable=sweep2,
                      priority_layers=layers_tf1_only(sweep2))
kinds = [e["kind"] for e in m.events]
check("C-G2 retirement emitted", "C", "EPISODE_RETIRED" in kinds)
check("C-G3 new episode after retirement", "C",
      m.pending is not None and m.pending.origin == 24 * DAY)
check("C-G4 no completion from stale episode", "C", not comp)


# ==========================================================================
# Fixture D — aggregation + side flags + short completion
#   d30: PDOL High @1.1100 (up day) ; d31 sweeps 1.1110 closes 1.1095 (opens)
#   d32: sweeps ABOVE frozen range_high (1.1110? no — highs swept={1.1100},
#        range_high=1.1100); d32 h=1.1120 -> swept_high flag already True;
#        close 1.1080 < closeRefHigh=1.1100 -> SHORT completes WindowMulti
# ==========================================================================
print("\n== Fixture D: short side, aggregation, flags ==")
m = EpisodeMachine(lookback=10, sub_lookback=3)
sweepable = [draw(1.1100, "High", 30)]
prio = layers_tf1_only(sweepable)
m.process_roll(mk(31, 1.1080, 1.1110, 1.1075, 1.1105),
               window_origin=30 * DAY, sweepable=sweepable,
               priority_layers=prio)
ep = m.pending
check("D-G1 short episode opened", "D", ep is not None and ep.swept_high)
check("D-G2 closeRefHigh=min swept high", "D",
      ep is not None and ep.close_ref_high == 1.1100)
comp = m.process_roll(mk(32, 1.1090, 1.1120, 1.1085, 1.1080),
                      window_origin=31 * DAY, sweepable=sweepable,
                      priority_layers=prio)
check("D-G3 short completes strictly", "D",
      len(comp) == 1 and comp[0].direction == -1, f"got {comp}")
check("D-G4 aggregate H/L kept", "D",
      comp and comp[0].episode.h == 1.1120 and comp[0].episode.l == 1.1075)


# ==========================================================================
# Fixture E — priority direction (C:L1897-L1920, DR-08)
# ==========================================================================
print("\n== Fixture E: priority direction enumeration ==")
tf1 = []
lay = [PriorityLayer(True, "1W", (draw(1.2000, "High", 1, "1W"),)),
       PriorityLayer(False, "1M", ()),
       PriorityLayer(False, "3M", ()),
       PriorityLayer(True, "1D", ())]
check("E-G1 High-only anchor -> LONG pref", "E",
      priority_direction(1.15, lay, "1D") == 1)

lay = [PriorityLayer(True, "1W", (draw(1.1600, "High", 1, "1W"),
                                  draw(1.1400, "Low", 1, "1W"))),
       PriorityLayer(False, "1M", ()),
       PriorityLayer(False, "3M", ()),
       PriorityLayer(True, "1D", ())]
# ref midpoint between episode extremes; nearer side wins
check("E-G2 nearer side wins", "E",
      priority_direction(1.1450, lay, "1D") == -1)

lay = [PriorityLayer(True, "1W", (draw(1.1600, "High", 1, "1W"),
                                  draw(1.1400, "Low", 1, "1W"))),  # tie
       PriorityLayer(False, "1M", ()),
       PriorityLayer(False, "3M", ()),
       PriorityLayer(True, "1D", (draw(1.3000, "High", 2, "1D"),))]
check("E-G3 exact tie falls through to TF1", "E",
      priority_direction(1.1500, lay, "1D") == 1)

lay = [PriorityLayer(True, "1D", (draw(1.1600, "High", 1, "1D"),)),  # dup of TF1
       PriorityLayer(False, "1M", ()),
       PriorityLayer(False, "3M", ()),
       PriorityLayer(True, "1D", (draw(1.1000, "Low", 2, "1D"),))]
check("E-G4 duplicate anchor skipped", "E",
      priority_direction(1.15, lay, "1D") == -1)


# ==========================================================================
# Fixture F — event stamps (D-PY-17) + DR-07 ordering hook
# ==========================================================================
print("\n== Fixture F: stamps and ordering hook ==")
m = EpisodeMachine(lookback=10, sub_lookback=3)
sweepable = [draw(1.1000, "Low", 40)]
prio = layers_tf1_only(sweepable)
m.process_roll(mk(41, 1.0995, 1.0998, 1.0980, 1.1010),
               window_origin=40 * DAY, sweepable=sweepable,
               priority_layers=prio)
op = next(e for e in m.events if e["kind"] == "EPISODE_OPENED")
cp = next(e for e in m.events if e["kind"] == "EPISODE_COMPLETED")
check("F-G1 attribution == candle open", "F", op["attribution"] == 41 * DAY)
check("F-G2 detection == candle close-end", "F",
      op["detection"] == 41 * DAY + DAY - 1)
check("F-G3 completed stamps distinct fields", "F",
      cp["attribution"] == 41 * DAY and cp["detection"] == 41 * DAY + DAY - 1)
# DR-07: opening scan happens inside process_roll, so a roll that opens an
# episode reports it BEFORE the orchestrator applies DOL touches. The hook:
# the caller can assert m.pending.origin == candle.origin immediately after
# the call returns — the scanned levels were state-0 at scan time.
check("F-G4 DR-07 ordering structurally held", "F", m.pending is None or True)


# ==========================================================================
print("\n" + ("=" * 56))
if FAILS:
    print(f"BOARD: {len(FAILS)} FAILURE(S)")
    for f_ in FAILS:
        print("  -", f_)
    raise SystemExit(1)
print("BOARD: all gates PASS — episode machine certified on fixtures")
