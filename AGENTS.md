# RINO Python Port — Working Contract

GOAL: Independent Python port of OSOK_EA[RINO CORE_V3.1].pine for MT5
historical replay. Output must produce rino.v3.phase1 JSON events that can be
diffed against a TradingView capture of the same period.

## Sources of truth (strict order)
1. RINO_V3_1_System_Documentation.md — port from the DOCUMENTED predicates
   (P3/P4 sections). Cite the section (e.g. "P4.4") in a comment above each
   function you write.
2. OSOK_EA[RINO CORE_V3.1].pine — exact comparison semantics only.
3. TAD files — historical context, never behavior.

## Hard rules
- ONE module per session, from the sequence below. Never skip ahead.
- Run the module's test_*.py before claiming done. Paste the test output.
- If a test fails 3 times: STOP, report the failure, change nothing else.
- Reproduce known Pine quirks exactly; do NOT "fix" them. Flag with
  `# DOC-XX:` comments (DOC-02 gate return scope, DOC-08 anchorBonus raw-TF,
  DOC-09 intact timestamp, DOC-16 DONE guard). List is in the system doc, P6.1.
- Only completed candles ever enter the engine. Native timestamps only.
- pandas/numpy/MetaTrader5 only. New dependencies require asking first.
- After green test: git commit "module &lt;name&gt; — stage &lt;N&gt;".

## Sequence (we are here: step 0)
0. rino_config + fetch_data + test_connection   [MT5 terminal reachable, OHLC pull works]
1. rino_tf1    + test_tf1    [TF1 levels, invalidation, candle direction]
2. rino_tf2    + test_tf2    [pivots, alternation, bias/CHoCH, Critical]
3. rino_dol    + test_dol    [PDOL/SDOL roles, states 0→1→2, coverage]
4. rino_episode + test_episode [window, sweep, closeRef, completion, targets]
5. rino_gate   + test_gate   [POI gate + ranking + ownership + export schema]
6. rino_diff                 [event diff vs TradingView JSON capture]

## Definition of done (whole project)
diff of Python-emitted events vs TradingView capture shows: identical event
kinds, order, setupIds, timestamps, and prices within mintick tolerance of
the same broker feed.

EXECUTOR CONTRACT
- You are EXECUTOR-ONLY. You never author, refactor, fix, or "improve" code.
- You create or replace files ONLY with content the user pastes verbatim.
- You run the test the user names. You paste the full output. You stop.
- If a test fails, you report the failure. You do not attempt a fix.

If any instruction is ambiguous or missing, STOP and ask — do not
fill gaps with judgment. If you changed code the user did not paste
verbatim, that is a contract violation: say so immediately.

SOURCES OF TRUTH (strict order):
1. RINO System Documentation + freeze logs + DECISIONS.md — behavior authority.
2. Frozen Pine / Python port — executable truth (D-PY-16: executed code, not comments).
3. CRT & TS Guide, DOL pdf, HTF Mystery Book, RANGE_POI_MIT notes —
   HYPOTHESIS LIBRARIES ONLY. They may propose predicates; they never define
   them. A concept enters the system only via: precise definition → fixture →
   gate → replication. No exceptions, regardless of the source's reputation.

   EYE-TEST PROTOCOL: never explain a TV-vs-Python diff by assuming either side
is stale. Classify first: (A) freeze-scope logic -> both SHOULD match; any
diff is a REAL discrepancy - log date, TV's verdict, Python's verdict, and
hand it to the parity harness as a fixture. (B) post-freeze Python rulings
(D-PY-20/21/22/27/28) -> documented divergence, parity defined against the
amended spec. When unsure which bucket, assume A and prove otherwise.