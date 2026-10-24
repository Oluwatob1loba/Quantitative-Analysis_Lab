# DECISIONS.md — RINO Python port ruling register
One line per ruling. Amendments replace the line and cite the date; nothing is deleted silently.

- D-PY-01 | DOC-02 (POI gate return-scope) ported as-is from frozen source; parity harness settles runtime behavior. (2026-10-16)
- D-PY-02 | DOC-08 (anchorBonus raw TF strings, no enable/slot check) ported as-is. (2026-10-16)
- D-PY-03 | DOC-09 (intact = last-change timestamp predicate) ported as-is. (2026-10-16)
- D-PY-04 | DOC-16 (DONE guard can include the following adjacent candle) ported as-is. (2026-10-16)
- D-PY-05 | The numeric field beside "Show Open" is line WIDTH, not open-width; config split into tf1_show_open (bool) + tf1_line_width (int). (2026-10-17)
- D-PY-06 | ADD-01 rev 2: key-time liquidity raid is an LTF observation (<=30m series timestamps the cross); TS arena may be any TF1; weight default 1; gate default off. (2026-10-17)
- D-PY-07 | Sydney key-time window ships provisional=true; NY/London/Tokyo ratified; Asia bounds to be settled empirically from raid timestamps. (2026-10-17)
- D-PY-08 | Sessions freeze at fixed UTC+1; DST via explicit server->UTC+1 bridge (EU last-Sunday Mar/Oct rule); repeated fall-back hour assigned to summer (market closed). (2026-10-17)
- D-PY-09 | Sunday 22:00+ server bars fold into Monday's D1/W1 bucket (terminal parity); "look from 00:00" is an analysis filter, not a bucketing rule. (2026-10-17)
- D-PY-10 | Universal recipe across FX majors for now; per-symbol TF ladders arrive with the architect's table; pump.fun deferred to its own lake and presets. (2026-10-17)
- D-PY-11 | Mid never price-invalidates (eviction-only); no historical Open stamps (Show Open is live bar-0 display only). (2026-10-17)
- D-PY-12 | Unassigned numbering gap left intentionally after the BUG-PY reworks; do not reuse. (2026-10-19)
- D-PY-13 | Equal-price same-side pivot: the incoming pivot is the loser and becomes Minor; the pending candidate stands. (2026-10-18)
- D-PY-14 | Anchored TF2 memory uses the TF1 window cutoff; manual lookback applies only when unanchored. (2026-10-18)
- D-PY-15 | Bias/CHoCH/protected-swing OUT of the Python port until the architect defines trend/CHoCH/BOS inside DOL logic; bias constant "undefined"; TF2_BIAS suppressed; BiasProvider plug-in reserved. (2026-10-18)
- D-PY-16 | Implementation-extent verification: docs describe intent, only executed code describes behavior; every ported subsystem cites its executed source path, mirrors its extent (computed / toggle-gated / dormant / deferred), and carries a test asserting that extent. (2026-10-19)
- D-PY-17 | Time stamps split by kind: origin/endTime/pivot/parent stamps use the confirmed native candle's own open bucket (cbucket); detection/availability/changed stamps use the roll bar; the two never substitute for each other. (2026-10-19)

## Defect log (not rulings; kept for traceability)
- BUG-PY-01 | Mid/Open were price-invalidated contrary to P4.2; fixed rev2 TF1 (Mid eviction-only, no Open stamps); Gate 0 sentinel added. (2026-10-19)
- BUG-PY-02 | Confluence pool iterated all history instead of retention-pruned arrays; O(pool^2) hang; fixed by pruning records to live TF1 levels/anchor draws; Gate 7 sentinel added. (2026-10-19)
- BUG-PY-03 | DOL engine read TF1 final-state (is_active / levels membership) inside per-roll loop, silencing TF1 consumption and breaking retention view; fixed with incremental origin cutoff and no is_active guard. (2026-10-19)
- BUG-PY-04 | Origins/endTimes/pivot-parents stamped with the developing bucket instead of the confirmed bucket (cbucket); fixed via D-PY-17 across clocks/TF1/TF2/DOL and test lookups. (2026-10-19)

- D-PY-18 | Critical proximity semantics = side-matched (High vs parent High, Low vs parent Low, denom abs(parentPrice); frozen C:L457..L497), config flag critical_side_matched=True; legacy min-distance variant retained behind flag=False. PENDING architect ratification (handover §18.1 recommends True). Flips Critical counts upward. (2026-10-24)
- BUG-PY-05 | rino_tf2 keyed confirmed TF1 OHLC and deferred-Critical resolution by the DEVELOPING bucket; every Critical tested against the previous candle's extremes, resolved one roll early. Fixed: cbucket keying + resolve at parent_bucket <= cbucket. Root cause class = D-PY-17/BUG-PY-04. (2026-10-24)
- TEST-PY-02 | test_tf1 Gate 1 conf lookup keyed by tf1_bucket (developing) instead of tf1_cbucket; strict-close check compared against the candle AFTER the breaker. Engine was correct; gate was wrong (green boards pre-D-PY-17 were stale). Fixed. (2026-10-24)
- TEST-PY-03 | test_clocks bar-before-roll window used calendar-day offsets, empty across weekends (Monday prior window); fixed to window the exposed confirmed bucket. Engine was correct. (2026-10-24)

WE ARE HERE (2026-10-24): all four foundation boards green in the sandbox on a synthetic lake after BUG-PY-05 + TEST-PY-02/03 + D-PY-18; rino_episode.py + test_episode.py delivered (25/25 fixture gates) awaiting orchestrator. NEXT: re-run all tests on the REAL lake and paste boards (synthetic green != real green); paste test_dol Gate 1 offenders if any; architect to ratify D-PY-18. Then rino_engine.py orchestrator (P3 order), then rino_setup.py per the LIVE frozen pine (incl. TSM direction gate, F-strict slice POI gate, class-B grade cap, t1 logic, poiDiag export — handover §14 predates these; port the executed file, flag divergences).

WE ARE HERE (superseded 2026-10-19): clocks, TF1 anatomy, TF2 structure (bias-free per D-PY-15) and DOL lifecycle ported; test_dol Gates 1-5, 7 green, Gate 6 pending the D-PY-17 re-key; next: seven-green test_dol and test_tf2 re-run, then rino_episode.py (window packet [2] offset, opening pairwise sweep over covered state-0 PDOLs, frozen bounds with swept-side fallbacks, close-reference completion at main+1).