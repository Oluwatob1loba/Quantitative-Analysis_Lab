"""rino_backtest.py — Model 2 (lowest level): market entry at bar-0 open, setup stop,
T1 partials + breakeven, runner to target. Costs = lake spread only. Conservative
same-bar rule: stop checked before targets. This is the FLOOR: what the raw model
returns before any refinement.

PERF-PY-01 (2026-10-28): the per-trade hot loop originally materialized
`list(seg.iterrows())` — up to ~140k pandas Series objects per trade. When 05 went
dual-mode (base + d703) the backtest became the pipeline's dominant cost (>1h for
two symbols). The loop now runs over precomputed numpy views of the same bars with
IDENTICAL semantics; equivalence-gated against the legacy implementation on
synthetic data (same trades, same exit reasons, same PnL). D-PY-23 dials unchanged."""
import numpy as np
import pandas as pd
from lab import load, pip_size

SYMBOL = "EURUSD"
MINTICK = 1e-5
# --- RESEARCH DIALS (D-PY-23, architect ruling 2026-10-24): partial-taking and the
# breakeven move are EXPERIMENT PARAMETERS, tweaked as research directs — never
# hard-coded assumptions. Sweep these, don't marry them.
PARTIAL = 0.6          # fraction closed at T1 (handover range 0.5-0.7)
MOVE_BE_AFTER_T1 = True   # move stop to entry after the partial fills


class _Bars:
    """Precomputed numpy views of the M15 frame, built ONCE per run_backtest call
    and shared by every trade (PERF-PY-01)."""

    def __init__(self, df):
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()
        self.idx = df.index.values               # datetime64[ns], sorted
        self.idx_i = self.idx.view("int64")
        self.open = df["open"].to_numpy(float)
        self.high = df["high"].to_numpy(float)
        self.low = df["low"].to_numpy(float)
        self.close = df["close"].to_numpy(float)
        self.spread = df["spread"].to_numpy(float)
        self.n = len(self.idx)

    def pos_at(self, ts):
        """First bar whose timestamp is >= ts (mirrors df.loc[df.index >= ts])."""
        return int(np.searchsorted(self.idx_i, pd.Timestamp(ts).value, side="left"))


def run_backtest(df, setups, partial=PARTIAL, mintick=MINTICK, mode="base"):
    """mode="base": T1 partial -> BE -> runner to target (the floor).
    mode="d703":  break-driven management (freeze-log D-703, quantified by 08):
                  T1 partial fills as before, but the stop only moves to BE when
                  the T1 fills OR a Critical break arrives. The runner is held to
                  the PDOL target ONLY if a Critical break has confirmed; if T1
                  filled without one, the runner exits at the next bar's close.
                  Rationale: 08 showed non-Critical setups average ~-0.5R."""
    bars = _Bars(df)
    n = bars.n
    has_crit = "breakCritAt" in setups.columns
    trades = []
    for _, s in setups.iterrows():
        if not s.actionable or not np.isfinite(s.stop) or not np.isfinite(s.target):
            continue
        d = 1 if s.direction == 1 else -1
        pos = bars.pos_at(s.availableAt)
        if pos >= n:
            continue
        spread_px = float(bars.spread[pos]) * mintick
        entry = float(bars.open[pos]) + d * spread_px
        R = abs(entry - float(s.stop))
        if not np.isfinite(R) or R == 0:
            continue
        stop = float(s.stop)
        t1 = float(s.t1) if np.isfinite(s.t1) else None
        t2 = float(s.target)
        crit_at = pd.to_datetime(s.breakCritAt) if has_crit and pd.notna(s.breakCritAt) else None
        if mode == "d703" and crit_at is not None and crit_at.value < bars.idx_i[pos]:
            crit_at = None                          # stamp predating entry = not usable
        crit_ns = crit_at.value if crit_at is not None else None
        t1_done = False; pnl = 0.0; reason = "OPEN"; t1_pos = -1
        i = pos
        while i < n:
            crit = crit_ns is not None and bars.idx_i[i] >= crit_ns
            h = bars.high[i]; l = bars.low[i]; c = bars.close[i]
            hit_sl = (l <= stop) if d == 1 else (h >= stop)
            hit_t1 = (not t1_done) and t1 is not None and ((h >= t1) if d == 1 else (l <= t1))
            hit_t2 = (h >= t2) if d == 1 else (l <= t2)
            if hit_sl:
                pnl += ((stop - entry) if not t1_done else (1 - partial) * (stop - entry)) * d / R
                reason = "BE" if (t1_done and abs(stop - entry) < 1e-12) else "SL"
                break
            if hit_t1:
                pnl += partial * (t1 - entry) * d / R
                t1_done = True; t1_pos = i
                if MOVE_BE_AFTER_T1 or (mode == "d703" and crit):
                    stop = entry                    # breakeven (d703: T1 OR Critical)
                i += 1
                continue
            if hit_t2:
                if mode == "d703" and not crit:
                    i += 1                          # no confirmed spark: don't honor the far target
                    continue
                pnl += (1 if not t1_done else (1 - partial)) * (t2 - entry) * d / R
                reason = "T2"; break
            if mode == "d703" and t1_done and not crit and t1_pos >= 0 and i > t1_pos:
                pnl += (1 - partial) * (c - entry) * d / R
                reason = "NOCRIT"; break
            i += 1
        else:
            pnl += ((1 - partial) if t1_done else 1.0) * (float(bars.close[n - 1]) - entry) * d / R
            reason = "EOD"
        trades.append(dict(origin=s.origin, direction=d, grade=s.grade, mode=mode,
                           setupClass=s.setupClass, keyTimeSweep=bool(s.keyTimeSweep),
                           targetTf=s.targetTf, R=R, pnl_R=pnl, reason=reason,
                           t1=t1_done, confluenceLayers=s.confluenceLayers))
    return pd.DataFrame(trades)


def summarize(tr):
    if not len(tr):
        return "no trades"
    wins = tr[tr.pnl_R > 0]; losses = tr[tr.pnl_R < 0]
    pf = wins.pnl_R.sum() / abs(losses.pnl_R.sum()) if len(losses) and losses.pnl_R.sum() != 0 else float("inf")
    eq = tr.sort_values("origin").pnl_R.cumsum()
    lines = [
        f"trades: {len(tr)} | win rate: {len(wins)/len(tr):.1%} | expectancy: {tr.pnl_R.mean():.3f} R",
        f"median: {tr.pnl_R.median():.3f} R",
        f"profit factor: {pf:.2f} | max drawdown: {(eq - eq.cummax()).min():.1f} R",
        f"exits: {tr.reason.value_counts().to_dict()}",
        f"T1 hit rate: {tr.t1.mean():.1%}",
    ]
    for col in ("grade", "setupClass", "direction", "keyTimeSweep", "targetTf"):
        g = tr.groupby(col).pnl_R.agg(["count", "mean"])
        lines.append(f"by {col}: " + " | ".join(f"{i}:{r['mean']:+.3f}R(n={int(r['count'])})"
                                                for i, r in g.iterrows()))
    return "\n".join(lines)


if __name__ == "__main__":
    df = load(SYMBOL)
    setups = pd.read_csv(f"reports/setups_{SYMBOL}.csv", parse_dates=["origin", "availableAt"])
    tr = run_backtest(df, setups)
    tr.to_csv(f"reports/trades_{SYMBOL}.csv", index=False)
    print(summarize(tr))
    print(f"\nsaved reports/trades_{SYMBOL}.csv")


def run_model3(df, setups, quadrant=1.0, mintick=MINTICK, partial=PARTIAL,
               require_class=("Critical", "Major")):
    """Model 3 (architect ruling D-PY-28): intent-confirmed retrace entry.
    1) setup actionable; 2) TF2 swing break (Major/Critical) in direction BEFORE entry;
    3) resting limit at `quadrant` of the wick range measured from the WICK EXTREME
       (1.0 = extreme = Techfred; 0.75/0.5/25 deeper toward the body; inverted for sells);
    4) stop untouched from availability until fill, else void;
    5) post-entry: T1 partial + BE dial + runner to the PDOL (final target)."""
    bars = _Bars(df)
    n = bars.n
    trades = []
    for _, s in setups.iterrows():
        if not s.actionable or not np.isfinite(s.stop) or not np.isfinite(s.target):
            continue
        if s.breakClass not in require_class or pd.isna(s.breakAt):
            continue                                    # intent gate: no qualifying break, no trade
        d = 1 if s.direction == 1 else -1
        if d == 1:
            ext, body = float(s.zoneLow), float(s.zoneHigh)
        else:
            ext, body = float(s.zoneHigh), float(s.zoneLow)
        entry_price = ext + (body - ext) * (1.0 - quadrant)   # q=1.0 -> wick extreme
        pos = bars.pos_at(s.availableAt)
        if pos >= n:
            continue
        brk_ns = pd.Timestamp(s.breakAt).value
        pre_end = min(int(np.searchsorted(bars.idx_i, brk_ns, side="left")), n)
        pre_end = max(pre_end, pos)
        stop = float(s.stop)
        if d == 1 and (bars.low[pos:pre_end] <= stop).any():
            continue                                    # stop ran before the break: void
        if d == -1 and (bars.high[pos:pre_end] >= stop).any():
            continue
        p2 = pre_end                                    # first bar >= brk (>= pos)
        if p2 >= n:
            continue
        if d == 1:
            hits = np.nonzero(bars.low[p2:] <= entry_price)[0]
        else:
            hits = np.nonzero(bars.high[p2:] >= entry_price)[0]
        if not len(hits):
            continue                                    # never retraced deep enough
        fill_pos = p2 + int(hits[0])
        spread_px = float(bars.spread[pos]) * mintick   # legacy: bar at availableAt
        entry = entry_price + d * spread_px
        R = abs(entry - stop)
        if not np.isfinite(R) or R == 0:
            continue
        t1 = float(s.t1) if np.isfinite(s.t1) else None
        t2 = float(s.target)
        t1_done = False; pnl = 0.0; reason = "OPEN"
        i = fill_pos
        while i < n:
            h = bars.high[i]; l = bars.low[i]; c = bars.close[i]
            hit_sl = (l <= stop) if d == 1 else (h >= stop)
            hit_t1 = (not t1_done) and t1 is not None and ((h >= t1) if d == 1 else (l <= t1))
            hit_t2 = (h >= t2) if d == 1 else (l <= t2)
            if hit_sl:
                pnl += ((stop - entry) if not t1_done else (1 - partial) * (stop - entry)) * d / R
                reason = "BE" if (t1_done and abs(stop - entry) < 1e-12) else "SL"
                break
            if hit_t1:
                pnl += partial * (t1 - entry) * d / R
                t1_done = True
                if MOVE_BE_AFTER_T1:
                    stop = entry
                i += 1
                continue
            if hit_t2:
                pnl += (1 if not t1_done else (1 - partial)) * (t2 - entry) * d / R
                reason = "T2"
                break
            i += 1
        else:
            pnl += ((1 - partial) if t1_done else 1.0) * (float(bars.close[n - 1]) - entry) * d / R
            reason = "EOD"
        trades.append(dict(origin=s.origin, direction=d, grade=s.grade, model="m3",
                           quadrant=quadrant, breakClass=s.breakClass,
                           pnl_R=pnl, reason=reason, t1=t1_done))
    return pd.DataFrame(trades)
