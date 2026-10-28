# DECISIONS ADDENDUM — append to DECISIONS.md (2026-10-28)

- PERF-PY-01 | DIAGNOSED + FIXED (2026-10-28): the >1h 05 slowdown was the BACKTEST,
  not the engine. run_backtest materialized `list(seg.iterrows())` per trade — up to
  ~140k pandas Series objects per trade; when 05 went dual-mode (base + d703, D-PY-28
  batch) the cost doubled and crossed the hour mark for 2 symbols. The hot loop now
  runs over precomputed numpy views of the same bars with IDENTICAL semantics.
  Equivalence gate vs the legacy implementation on synthetic data: same trade set,
  same exit reasons, same PnL (atol 1e-10) across base/d703 x all exit branches
  (SL/BE/T2/NOCRIT/EOD) and model3 quadrants 1.0/0.75/0.5/0.25 + R==0/empty-seg skips.
  Measured 512x at gate scale; the multiplier grows with lake size. D-PY-23 dials and
  all public signatures unchanged — 05 and 09 call it exactly as before.
- DEFERRED (not a defect): attach_native's per-bar bucket_start Python loop
  (~2-5s per symbol) — rino_clocks is a certified module; the microseconds don't
  justify re-certification now. The engine stage line from the instrumented build
  remains the arbiter if anything still looks slow.

## WE ARE HERE (2026-10-28, supersedes 2026-10-24)
Foundation certified on real lake (clocks/TF1/TF2/DOL all gates green). Episode
machine + setup engine + orchestrator delivered; Phase-2 freeze ingested (L1, S-6/S-7,
D-506, TSM order); D-PY-27 series fields attached; Model 3 (D-PY-28) implemented.
09 first cut: q100 wick-extreme CATASTROPHIC (-1.0R), q75 = only positive cell
(GBPUSD +0.149R) — candidate pending 9-symbol replication. OPEN: (1) factor-reweighting
ruling (fvg weight 0, confluence cap x1, Minor deepened, Critical carries grade) gated
on the replicated quadrant table; (2) parity harness vs the six pinned freeze-log
fixtures. NEXT: rerun 05 with the PERF-PY-01 backtest fix (expect minutes/symbol, stage
line now truthful), paste summary -> ruling -> amendment -> parity harness.
