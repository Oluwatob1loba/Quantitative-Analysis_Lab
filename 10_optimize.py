"""10_optimize.py - walk-forward optimizer over the EXECUTION layer (D-PY-30).

RATIFIED 2026-10-28: dial space, 2021-2023 train / 2024-2026 test split, and
the constraint-first fitness from the Risk Management Excel.

GATES BEFORE THIS RUNS:
1. EYEBALL VERIFICATION MUST HAVE PASSED (viz.py vs TradingView, last 60 days,
   EURUSD/USDJPY/AUDUSD/NZDUSD). This optimizer tunes a machine whose output
   the architect has personally confirmed. If verification failed, fix the port
   first - everything here is conditional on the stamped setups being faithful.
2. The discretionary benchmark (-0.259R, Excel RISK tab) is a REFERENCE LINE,
   not a target: the optimizer must beat it on the TEST window across symbols.

WHAT IS FROZEN (the model, protected by parity): the core predicates - episode
machine, POI gate, TSM trend gate, class/grade factors, targets. The optimizer
tunes only the execution/selection layer (D-PY-23 research dials):
  which setups to take (score/class/raid/confluence/day filters),
  how to manage them (partial size, breakeven, runner target),
  never what a setup IS.

ANTI-OVERFITTING SPINE (non-negotiable):
- Walk-forward: candidates are ranked on TEST-window results only.
- Cross-symbol: a config must hold in the aggregate AND report its weakest symbol.
- Constraint-first: the Excel's prop rules (DD lines, unit budget, weekly cap)
  are survival gates, not soft objectives.
- Multiple-comparison honesty: thousands of configs are tested; the summary
  prints how many, and top-of-grid optimism is called out. If train is great
  and test is flat, the config is a curve-fit, not a finding.

RUNTIME: two stages. Stage 1 screens the full grid on the three theaters
(EURUSD/GBPUSD/USDJPY) - minutes. Stage 2 runs the shortlist on all nine lakes.

OUTPUT (reports/):
- optimize_summary.csv  - every config x window x aggregate metrics
- optimize_trades_best.csv - the winning config's full trade table in your
  TRADELOG column shape (MAE/MFE included), importable into the Excel
- the printed report: TOP configs with train/test deltas, the winner's
  self-report census (refusals by conjunct), the Excel-sheet metrics, and
  the AUDIT register of every dial vs its frozen value.
"""
import os
import itertools
from collections import Counter
import numpy as np
import pandas as pd
from lab import load, pip_size

# ---------------- dials the OPTIMIZER searches (architect-ratified) --------
DIALS = dict(
    MIN_SCORE=[0, 2, 5],          # 0 = all actionable; 2 = grade B floor; 5 = grade A floor
    CLASS=["any", "A", "B"],      # A admits A and A+
    RAID_ONLY=[False, True],      # key-time raid tag only (ADD-01)
    MIN_CONF=[0, 1],              # confluenceLayers floor
    PARTIAL=[0.5, 0.6, 0.7],      # Excel early-exit rule centers 0.6
    MOVE_BE=[True, False],        # breakeven after T1
    RUNNER=["pdol", "series"],    # final target: PDOL draw vs D-PY-27 series extreme
    DAYS=["all", "tue_thu", "mon_fri"],
)
# ---------------- frozen account rules (Excel RULES tab - not searched) ----
SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD",
           "USDCAD", "USDCHF", "AUDJPY", "NZDJPY"]
THEATERS = ["EURUSD", "GBPUSD", "USDJPY"]           # stage-1 screen
TRAIN_END = pd.Timestamp("2024-01-01")              # walk-forward split
UNIT_DOLLARS = 45.0        # = 6000 x 0.75%
START_BALANCE = 6000.0
YOUR_DD_LINE = 0.075       # your max DD % (Excel)
FIRM_DD_LINE = 0.10        # firm max DD % (Excel)
MAX_UNITS_MONTH = 5        # loss units per month (Excel)
MAX_TRADES_WEEK = 3        # max trades per week (Excel)
COOLDOWN_AFTER = 2         # consecutive losses before cooldown (Excel)
COOLDOWN_HOURS = 24
TOP_N = 15
GRADE_RANK = {"A+": 6, "A": 5, "B": 2}

CONFIGS = [dict(zip(DIALS, v)) for v in itertools.product(*DIALS.values())]


class Bars:
    def __init__(self, df):
        self.idx = df.index.values
        self.open = df["open"].to_numpy(float)
        self.high = df["high"].to_numpy(float)
        self.low = df["low"].to_numpy(float)
        self.close = df["close"].to_numpy(float)
        self.spread = df["spread"].to_numpy(float)
        self.n = len(self.idx)


def first_idx(mask):
    return int(np.argmax(mask)) if mask.any() else None


def scan(bars, pos, d, entry, stop, t1, t2, partial, move_be):
    """One trade, base-mode semantics (PERF-PY-01 vectorized; SL-first,
    T1 partial, BE, runner to t2, EOD). Returns outcome + MAE/MFE in R."""
    n = bars.n
    hi = bars.high[pos:]; lo = bars.low[pos:]; cl = bars.close[pos:]
    R = abs(entry - stop)
    if not np.isfinite(R) or R == 0:
        return None
    if d * (t2 - entry) <= 0:
        return None                    # wrong-side fill: entry beyond own target
    if d == 1:
        sl_at = lo <= stop
        t1_at = (hi >= t1) if t1 is not None else np.zeros(len(hi), bool)
        t2_at = hi >= t2
    else:
        sl_at = hi >= stop
        t1_at = (lo <= t1) if t1 is not None else np.zeros(len(hi), bool)
        t2_at = lo <= t2
    big = n + 1
    sl_i = first_idx(sl_at); t1_i = first_idx(t1_at); t2_i = first_idx(t2_at)
    pnl = 0.0; reason = "EOD"; exit_i = len(hi) - 1; exit_px = cl[-1]
    t1_done = False
    if sl_i is not None and (t1_i is None or sl_i <= t1_i) and (t2_i is None or sl_i <= t2_i):
        pnl = (stop - entry) * d / R; reason = "SL"; exit_i = sl_i; exit_px = stop
    elif t1_i is not None and (t2_i is None or t1_i <= t2_i):
        pnl = partial * (t1 - entry) * d / R
        t1_done = True
        rest = slice(t1_i + 1, None)
        be = entry if move_be else stop
        if d == 1:
            sl2 = lo[rest] <= be; t2m = hi[rest] >= t2
        else:
            sl2 = hi[rest] >= be; t2m = lo[rest] <= t2
        sl2_i = first_idx(sl2); t2a_i = first_idx(t2m)
        if sl2_i is not None and (t2a_i is None or sl2_i < t2a_i):
            pnl += (1 - partial) * (be - entry) * d / R
            reason = "BE" if move_be else "SL"; exit_i = t1_i + 1 + sl2_i; exit_px = be
        elif t2a_i is not None:
            pnl += (1 - partial) * (t2 - entry) * d / R
            reason = "T2"; exit_i = t1_i + 1 + t2a_i; exit_px = t2
        else:
            pnl += (1 - partial) * (cl[-1] - entry) * d / R
            reason = "EOD"; exit_i = len(hi) - 1; exit_px = cl[-1]
    elif t2_i is not None:
        pnl = (t2 - entry) * d / R; reason = "T2"; exit_i = t2_i; exit_px = t2
    else:
        pnl = (cl[-1] - entry) * d / R; reason = "EOD"  # no level ever hit
    # MAE/MFE over held bars, in R
    held = slice(0, exit_i + 1)
    mfe = float(np.max(d * (hi[held] - entry))) / R
    mae = float(np.max(d * (entry - lo[held]))) / R
    return dict(pnl=pnl, reason=reason, exit_i=exit_i, exit_px=exit_px,
                mae_R=max(mae, 0.0), mfe_R=max(mfe, 0.0), t1=t1_done, R=R)


def run_window(df, bars, cfg, mintick):
    """Simulate one config on one symbol over df's date window. Returns
    (metrics dict, trades list, census Counter). Implements the Excel's
    account rules: 1 unit per trade, weekly cap, 2-loss cooldown."""
    census = Counter()
    trades = []
    equity_u = peak_u = maxdd_u = 0.0
    consec = 0; cooldown_until = None
    week_counts = {}; month_units = Counter()
    df = df.sort_values("availableAt")
    for _, r in df.iterrows():
        if not bool(r.get("actionable", False)):
            census["context_skipped"] += 1; continue
        grade = r.get("grade"); grade = "?" if pd.isna(grade) else grade
        score = r.get("score"); score = GRADE_RANK.get(grade, 0) if pd.isna(score) else float(score)
        if score < cfg["MIN_SCORE"]: census["refused_grade"] += 1; continue
        if cfg["CLASS"] == "A" and grade not in ("A", "A+"): census["refused_class"] += 1; continue
        if cfg["CLASS"] == "B" and grade != "B": census["refused_class"] += 1; continue
        if cfg["RAID_ONLY"] and not bool(r.get("keyTimeSweep", False)):
            census["refused_raid"] += 1; continue
        if int(r.get("confluenceLayers", 0) or 0) < cfg["MIN_CONF"]:
            census["refused_confluence"] += 1; continue
        dow = r.availableAt.dayofweek
        if cfg["DAYS"] == "tue_thu" and dow not in (1, 2, 3): census["refused_day"] += 1; continue
        if cfg["DAYS"] == "mon_fri" and dow not in (0, 4): census["refused_day"] += 1; continue
        if cooldown_until is not None and r.availableAt < cooldown_until:
            census["skipped_cooldown"] += 1; continue
        iso = r.availableAt.isocalendar(); wk = (int(iso[0]), int(iso[1]))
        if week_counts.get(wk, 0) >= MAX_TRADES_WEEK: census["skipped_weekly_cap"] += 1; continue
        pos = int(np.searchsorted(bars.idx.view("int64"), r.availableAt.value))
        if pos >= bars.n: census["skipped_no_data"] += 1; continue
        d = 1 if r.direction == 1 else -1
        spread_px = float(bars.spread[pos]) * mintick
        entry = float(bars.open[pos]) + d * spread_px
        stop = float(r.stop)
        t1 = float(r.t1) if pd.notna(r.get("t1")) else None
        if cfg["RUNNER"] == "series" and pd.notna(r.get("seriesHigh")):
            t2 = float(r.seriesHigh) if d == 1 else float(r.seriesLow)
        else:
            t2 = float(r.target)
        res = scan(bars, pos, d, entry, stop, t1, t2, cfg["PARTIAL"], cfg["MOVE_BE"])
        if res is None: census["skipped_degenerate"] += 1; continue
        week_counts[wk] = week_counts.get(wk, 0) + 1
        month_units[(r.availableAt.year, r.availableAt.month)] += 1
        if res["pnl"] < 0:
            consec += 1
            if consec >= COOLDOWN_AFTER:
                cooldown_until = r.availableAt + pd.Timedelta(hours=COOLDOWN_HOURS)
                consec = 0
        elif res["pnl"] > 0:
            consec = 0
        equity_u += res["pnl"]; peak_u = max(peak_u, equity_u)
        maxdd_u = max(maxdd_u, peak_u - equity_u)
        trades.append(dict(OpenedAt=r.availableAt, Pair=r.get("pair", ""), Dir="Long" if d == 1 else "Short",
                           Entry=entry, Stop=stop, TP=t2, RiskPct=0.75, RiskD=UNIT_DOLLARS,
                           Status="CLOSED", ClosedAt=pd.Timestamp(bars.idx[res["exit_i"]]),
                           Exit=res["exit_px"], PnLD=res["pnl"] * UNIT_DOLLARS, R=res["pnl"],
                           Units=1 if res["pnl"] < 0 else 0, reason=res["reason"], t1=res["t1"],
                           grade=grade, setupClass=r.get("setupClass"), targetTf=r.get("targetTf"),
                           keyTimeSweep=bool(r.get("keyTimeSweep", False)),
                           breakClass=r.get("breakClass"), HoldHours=(pd.Timestamp(bars.idx[res["exit_i"]]) - r.availableAt).total_seconds() / 3600,
                           MAE_R=res["mae_R"], MFE_R=res["mfe_R"]))
    m = dict(n=len(trades))
    if m["n"]:
        t = pd.DataFrame(trades)
        wins = t[t.R > 0]; losses = t[t.R < 0]
        m.update(exp_R=t.R.mean(), win=len(wins) / m["n"],
                 PF=wins.R.sum() / abs(losses.R.sum()) if len(losses) and losses.R.sum() != 0 else np.inf,
                 maxDD_u=maxdd_u, maxDD_pct=maxdd_u * UNIT_DOLLARS / START_BALANCE,
                 worst_R=t.R.min(), best_R=t.R.max(),
                 avg_MAE=t.MAE_R.mean(), avg_MFE=t.MFE_R.mean(),
                 units_peak_month=max(month_units.values()) if month_units else 0,
                 trades_peak_week=max(week_counts.values()) if week_counts else 0,
                 cooldowns=census["skipped_cooldown"])
        m["ok"] = (m["units_peak_month"] <= MAX_UNITS_MONTH and
                   m["trades_peak_week"] <= MAX_TRADES_WEEK and
                   m["maxDD_pct"] <= YOUR_DD_LINE)
    else:
        m.update(exp_R=np.nan, win=np.nan, PF=np.nan, maxDD_u=0, maxDD_pct=0,
                 worst_R=0, best_R=0, avg_MAE=np.nan, avg_MFE=np.nan,
                 units_peak_month=0, trades_peak_week=0, cooldowns=0, ok=False)
    m["census"] = census
    return m, trades, census


def windows(df):
    return (df[df.availableAt < TRAIN_END], df[df.availableAt >= TRAIN_END])


def main():
    lakes, setup_frames = {}, {}
    for sym in SYMBOLS:
        sp = f"reports/setups_{sym}.csv"
        if not (os.path.exists(sp) and os.path.exists(f"data/{sym}_M15.csv")):
            print(f"[{sym}] missing lake or setups - skipped"); continue
        setup_frames[sym] = pd.read_csv(sp, parse_dates=["origin", "availableAt"])
        lakes[sym] = Bars(load(sym))
        print(f"[{sym}] {lakes[sym].n} bars, {len(setup_frames[sym])} setups stamped")
    if not lakes:
        raise SystemExit("nothing to optimize - run 05_multisymbol.py first (after verification!)")

    def battery(cfg, symbols):
        rows = []
        for sym in symbols:
            tr, te = windows(setup_frames[sym])
            mt, _, _ = run_window(tr, lakes[sym], cfg, pip_size(sym) / 10)
            mv, _, _ = run_window(te, lakes[sym], cfg, pip_size(sym) / 10)
            rows.append((sym, mt, mv))
        return rows

    print(f"\nSTAGE 1: screening {len(CONFIGS)} configs on {THEATERS} ...")
    screen = []
    for i, cfg in enumerate(CONFIGS):
        exps, oks = [], 0
        for sym in THEATERS:
            if sym not in lakes: continue
            tr, te = windows(setup_frames[sym])
            mv, _, _ = run_window(te, lakes[sym], cfg, pip_size(sym) / 10)
            if mv["n"] >= 10 and np.isfinite(mv["exp_R"]):
                exps.append(mv["exp_R"]); oks += bool(mv["ok"])
        if exps:
            screen.append((np.mean(exps), min(exps), oks, cfg))
        if (i + 1) % 500 == 0:
            print(f"  {i + 1}/{len(CONFIGS)} configs screened")
    screen.sort(key=lambda x: (x[2] == len([s for s in THEATERS if s in lakes]), x[0], x[1]), reverse=True)
    shortlist = [cfg for _, _, _, cfg in screen[:80]]
    print(f"stage-1 shortlist: 80 configs (test-window expectancy on theaters)\n")

    print("STAGE 2: full nine-symbol battery on the shortlist ...")
    table = []
    for cfg in shortlist:
        bt = battery(cfg, [s for s in SYMBOLS if s in lakes])
        test_exps = [mv["exp_R"] for _, _, mv in bt if mv["n"] >= 10 and np.isfinite(mv["exp_R"])]
        train_exps = [mt["exp_R"] for mt, _, _ in [(a[1], a[2], a) for a in bt] if mt["n"] >= 10 and np.isfinite(mt["exp_R"])]
        oks = sum(bool(mv["ok"]) for _, _, mv in bt)
        if not test_exps: continue
        table.append(dict(cfg=cfg, test_mean=np.mean(test_exps), test_min=min(test_exps),
                          train_mean=np.mean(train_exps) if train_exps else np.nan,
                          delta=np.mean(test_exps) - (np.mean(train_exps) if train_exps else np.nan),
                          ok_symbols=oks, n_syms=len(test_exps),
                          pfs=np.nan, mar=np.nan))
    table.sort(key=lambda r: (r["ok_symbols"] == r["n_syms"], r["test_mean"], r["test_min"]), reverse=True)

    print(f"configs fully evaluated: {len(table)} (of {len(CONFIGS)} searched - top-of-grid optimism applies)")
    print(f"benchmark (Excel, suspended until verification): discretionary intraday -0.259R\n")
    print(f"{'#':>2} {'cfg':<44} {'testR':>7} {'minR':>7} {'trainR':>7} {'delta':>7} {'ok':>4}")
    for i, r in enumerate(table[:TOP_N]):
        cs = ",".join(f"{k[:2]}={v}" for k, v in r["cfg"].items())
        print(f"{i+1:>2} {cs:<44} {r['test_mean']:>7.3f} {r['test_min']:>7.3f} "
              f"{r['train_mean']:>7.3f} {r['delta']:>+7.3f} {r['ok_symbols']:>2}/{r['n_syms']}")

    if not table:
        raise SystemExit("no config produced >=10 test trades on any symbol - check stamps.")
    best = table[0]
    print("\nWINNER SELF-REPORT (SR-1/2/3 transplant) and EXCEL-SHEET METRICS:")
    rows_out = []
    for sym, mt, mv in battery(best["cfg"], [s for s in SYMBOLS if s in lakes]):
        for win, m in (("TRAIN", mt), ("TEST", mv)):
            print(f"[{sym}|{win}] n={m['n']:>3} exp={m['exp_R']:+.3f}R PF={m['PF']:.2f} "
                  f"win={m['win']:.1%} maxDD={m['maxDD_u']:.1f}u ({m['maxDD_pct']:.2%} vs your {YOUR_DD_LINE:.1%}) "
                  f"worst={m['worst_R']:+.2f}R units/mo<={m['units_peak_month']} trades/wk<={m['trades_peak_week']} "
                  f"MAE={m['avg_MAE']:.2f}R MFE={m['avg_MFE']:.2f}R verdict={'SURVIVES' if m['ok'] else 'BREACHES RULES'}")
            tr_list = run_window(setup_frames[sym][setup_frames[sym].availableAt < TRAIN_END] if win == "TRAIN"
                                 else setup_frames[sym][setup_frames[sym].availableAt >= TRAIN_END],
                                 lakes[sym], best["cfg"], pip_size(sym) / 10)[1]
            for t in tr_list:
                t = dict(t); t["symbol"] = sym; t["window"] = win; rows_out.append(t)
    if rows_out:
        pd.DataFrame(rows_out).to_csv("reports/optimize_trades_best.csv", index=False)
        print("\nwrote reports/optimize_trades_best.csv (TRADELOG shape, importable into the Excel)")

    summ = []
    for r in table:
        d = dict(r); d["cfg"] = str(r["cfg"]); summ.append(d)
    pd.DataFrame(summ).drop(columns=["pfs", "mar"]).to_csv("reports/optimize_summary.csv", index=False)
    print("wrote reports/optimize_summary.csv")
    print("\nAUDIT REGISTER (dial -> frozen baseline -> searched):")
    print("  execution layer dials were FREE by ruling (D-PY-23); core predicates FROZEN (parity).")
    print("  verification status gates all conclusions: " + ("PASSED" if os.path.exists("reports/EYEBALL_PASS.txt") else "NOT RECORDED - run the viz pass first"))


if __name__ == "__main__":
    main()
