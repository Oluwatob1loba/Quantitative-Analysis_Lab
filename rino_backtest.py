"""rino_backtest.py — Model 2 (lowest level): market entry at bar-0 open, setup stop,
T1 partials + breakeven, runner to target. Costs = lake spread only. Conservative
same-bar rule: stop checked before targets. This is the FLOOR: what the raw model
returns before any refinement."""
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


def run_backtest(df, setups, partial=PARTIAL, mintick=MINTICK):
    trades = []
    for _, s in setups.iterrows():
        if not s.actionable or not np.isfinite(s.stop) or not np.isfinite(s.target):
            continue
        d = 1 if s.direction == 1 else -1
        seg = df.loc[df.index >= s.availableAt]
        if not len(seg):
            continue
        spread_px = float(seg.iloc[0]["spread"]) * mintick
        entry = float(seg.iloc[0]["open"]) + d * spread_px
        R = abs(entry - float(s.stop))
        if not np.isfinite(R) or R == 0:
            continue
        stop = float(s.stop); t1 = float(s.t1) if np.isfinite(s.t1) else None
        t2 = float(s.target)
        t1_done = False; pnl = 0.0; reason = "OPEN"
        for ts, bar in seg.iterrows():
            h, l, c = float(bar.high), float(bar.low), float(bar.close)
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
                    stop = entry                      # breakeven (research dial)
                continue
            if hit_t2:
                pnl += (1 if not t1_done else (1 - partial)) * (t2 - entry) * d / R
                reason = "T2"; break
        else:
            c = float(seg.iloc[-1]["close"])
            pnl += ((1 - partial) if t1_done else 1.0) * (c - entry) * d / R
            reason = "EOD"
        trades.append(dict(origin=s.origin, direction=d, grade=s.grade,
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
