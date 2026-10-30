"""trade_audit.py v7 - INDEPENDENT geometric audit of every stamped trade.

Replays each stamped execution record against the RAW lake bars. Checks:
  ENTRY_FILL     base/m2: fill == bar open +/- spread*d at the entry bar.
                 m3: the fill bar's range SPANS the limit price (fills are limits).
  EXIT_BAR_SPAN  exit bar's range really spans the booked exit px - or a documented
                 gap-fill convention applies (GAP_STOP / GAP_TARGET / GAP_BE).
  ORDER_*        no terminal level touched before the recorded exit bar; touch
                 semantics by SIDE (below -> low, above -> high), not direction.
  SAME_BAR_T1T2  target spanned the T1 bar: the runner needs a later bar
                 (documented engine conservatism - a CONVENTION, not a defect).
  PNL_MATH       stamped pnl_R recomputes exactly from stamped geometry.
Bars are located BY TIMESTAMP (time is truth); stamped-index drift is reported
as LAKE_DISORDER (data quality, not an engine defect). d703 probe ledgers are
skipped. Era stamps expose stale-file mixing in any paste.
Usage: python trade_audit.py [SYMBOL ...]
"""
import glob
import os
import sys
import numpy as np
import pandas as pd
from lab import load, pip_size

VERSION = "v7.5"
PARTIAL = 0.6        # rino_backtest module default (D-PY-23 dial)
NEED = {"entry_i", "entry_px", "exit_i", "exit_px", "entry_time", "exit_time",
        "R", "pnl_R", "reason", "t1"}
CONVENTION_CODES = {"GAP_STOP", "GAP_TARGET", "GAP_BE", "SAME_BAR_T1T2"}


def first_touch(hi, lo, start, level, side, upto):
    """First bar in [start, upto) whose range touches level.
    side="below": touched via low (lo <= level). side="above": via high."""
    if upto <= start:
        return None
    seg = (lo[start:upto] <= level) if side == "below" else (hi[start:upto] >= level)
    j = int(np.argmax(seg))
    return start + j if seg[j] else None


def audit_symbol(sym, tr_path, st_path, kind="m3g"):
    tr = pd.read_csv(tr_path, parse_dates=["origin", "entry_time", "exit_time"])
    skipped_probe = 0
    if "mode" in tr.columns:
        skipped_probe = int((tr["mode"] != "base").sum())
        tr = tr[tr["mode"] == "base"]
    if not NEED.issubset(tr.columns):
        return [], [f"MISSING_STAMPS {sorted(NEED - set(tr.columns))} - rerun 05/09/05b"], 0, skipped_probe
    st = pd.read_csv(st_path, parse_dates=["origin", "availableAt"])
    df = load(sym)
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    fp_cur = (f"{len(df)}|{int(df.index[0].value)}|{int(df.index[-1].value)}|"
              f"{float(np.nansum(df['close'].to_numpy()[::997])):.4f}|"
              f"{float(np.nansum(df['high'].to_numpy()[::997])):.4f}|"
              f"{float(np.nansum(df['low'].to_numpy()[::997])):.4f}")
    if "lake_fp" in tr.columns and len(tr) and str(tr.lake_fp.iloc[0]) != fp_cur:
        return [], [f"!!! STALE LEDGER: lake drifted since these trades were stamped "
                    f"(fp {tr.lake_fp.iloc[0]} vs current {fp_cur}). Every 'defect' here would "
                    f"be a vintage artifact - rerun 05 -> 05m -> 05b -> 09, then audit."], 0, skipped_probe
    hi = df["high"].to_numpy(float); lo = df["low"].to_numpy(float)
    op = df["open"].to_numpy(float); sp = df["spread"].to_numpy(float)
    mt = pip_size(sym) / 10
    n = len(df)
    idx_i = df.index.values.view("int64")   # TIME is truth; stamped indices may
    defects = []                            # drift where the lake is disordered
    for _, t in tr.iterrows():
        d = int(t.direction)
        s = st[(st.origin == t.origin) & (st.direction == d)]
        if not len(s):
            defects.append((sym, kind, t.origin, d, t.reason, t.pnl_R, "NO_SETUP_ROW", ""))
            continue
        s = s.iloc[0]
        ei, xi = int(t.entry_i), int(t.exit_i)
        ei_t = int(np.searchsorted(idx_i, t.entry_time.value))
        xi_t = int(np.searchsorted(idx_i, t.exit_time.value))
        if ei_t != ei or xi_t != xi:
            defects.append((sym, kind, t.origin, d, t.reason, t.pnl_R, "LAKE_DISORDER",
                            f"stamped idx {ei}/{xi} vs time-located {ei_t}/{xi_t}"))
        ei, xi = ei_t, xi_t          # audit the bars the TIMESTAMPS point to
        entry, xpx, R = float(t.entry_px), float(t.exit_px), float(t.R)
        stop0 = float(s.stop); t2 = float(s.target)
        t1p = float(s.t1) if pd.notna(s.t1) else None
        s_stop = "below" if d == 1 else "above"      # losing side
        s_targ = "above" if d == 1 else "below"      # profit side
        code = detail = None
        # ENTRY_FILL
        if kind == "m3":
            ap = int(np.searchsorted(idx_i, s.availableAt.value))
            raw_limit = entry - d * float(sp[ap]) * mt
            # one-sided fill rule (mirrors the engine trigger): a LONG limit fills
            # via the LOW (lo <= L); a SHORT limit fills via the HIGH (hi >= L).
            # A bar entirely beyond the limit = gap-through fill AT the limit (valid).
            if d == 1:
                filled = lo[ei] - 2 * mt <= raw_limit
            else:
                filled = hi[ei] + 2 * mt >= raw_limit
            if not filled:
                code, detail = ("ENTRY_FILL",
                                f"fill bar {lo[ei]:.10f}-{hi[ei]:.10f} never traded limit {raw_limit:.10f}")
        else:
            e_exp = op[ei] + d * float(sp[ei]) * mt
            if abs(e_exp - entry) > 2 * mt:
                code, detail = "ENTRY_FILL", f"stamped {entry:.10f} vs bar open+spread {e_exp:.10f}"
        # EXIT_BAR_SPAN / gap conventions
        if code is None and not (lo[xi] - 2 * mt <= xpx <= hi[xi] + 2 * mt):
            if t.reason == "SL" and ((d == 1 and hi[xi] < stop0) or (d == -1 and lo[xi] > stop0)):
                code, detail = "GAP_STOP", f"bar {lo[xi]:.10f}-{hi[xi]:.10f} gapped through stop {stop0:.10f}"
            elif t.reason == "T2" and ((d == 1 and lo[xi] > t2) or (d == -1 and hi[xi] < t2)):
                code, detail = "GAP_TARGET", f"bar {lo[xi]:.10f}-{hi[xi]:.10f} gapped beyond target {t2:.10f}"
            elif t.reason == "BE" and ((d == 1 and hi[xi] < entry) or (d == -1 and lo[xi] > entry)):
                code, detail = "GAP_BE", f"bar {lo[xi]:.10f}-{hi[xi]:.10f} gapped through BE {entry:.10f}"
            else:
                code, detail = ("EXIT_BAR_SPAN",
                                f"exit bar {lo[xi]:.10f}-{hi[xi]:.10f} never touched booked {xpx:.10f}")
        # ORDER with correct touch sides
        if code is None:
            t1bar = (first_touch(hi, lo, ei, t1p, s_targ, xi) if (t1p is not None and bool(t.t1))
                     else None)
            if t.reason == "SL" and not bool(t.t1):
                ft = first_touch(hi, lo, ei, stop0, s_stop, xi + 1)
                if ft != xi:
                    extra = ""
                    if ft is not None:
                        extra = (f" | ft bar {lo[ft]:.10f}-{hi[ft]:.10f}"
                                 f" vs exit bar {lo[xi]:.10f}-{hi[xi]:.10f}")
                    code, detail = "ORDER_SL", f"stop first touched at bar {ft}, exit at {xi}{extra}"
            elif t.reason == "BE":
                if t1bar is None:
                    code, detail = "ORDER_BE", "BE exit without a T1 fill bar"
                else:
                    ft = first_touch(hi, lo, t1bar + 1, entry, s_stop, xi + 1)
                    if ft != xi:
                        code, detail = "ORDER_BE", f"BE level first touched at {ft}, exit at {xi}"
            elif t.reason == "T2":
                stop_end = (t1bar + 1) if t1bar is not None else xi
                ft_sl = first_touch(hi, lo, ei, stop0, s_stop, stop_end)
                ft_t2 = first_touch(hi, lo, ei, t2, s_targ, xi + 1)
                if ft_t2 != xi:
                    if ft_t2 is not None and ft_t2 == t1bar:
                        code, detail = ("SAME_BAR_T1T2",
                                        "target spanned the T1 bar; runner needs a later bar (documented)")
                    else:
                        code, detail = "ORDER_T2", f"target first touched at {ft_t2}, exit at {xi}"
                elif ft_sl is not None:
                    code, detail = "ORDER_T2", f"stop touched at {ft_sl} before recorded target exit"
            elif t.reason == "EOD":
                if xi > n - 1:
                    code, detail = "ORDER_EOD", f"exit_i {xi} beyond last bar {n-1}"
                elif (first_touch(hi, lo, ei, stop0, s_stop, n) is not None or
                        first_touch(hi, lo, ei, t2, s_targ, n) is not None):
                    code, detail = "ORDER_EOD", "terminal level touched but booked EOD"
        # PNL_MATH (same conventions as the engine)
        if code is None:
            if t.reason == "SL":
                p = (xpx - entry) * d / R
            elif t.reason == "BE":
                p = PARTIAL * (t1p - entry) * d / R
            elif t.reason == "T2":
                p = (PARTIAL * (t1p - entry) if bool(t.t1) else (xpx - entry)) * d / R \
                    + ((1 - PARTIAL) * (xpx - entry) * d / R if bool(t.t1) else 0.0)
            else:  # EOD: runner term PLUS the T1 partial booked when T1 filled
                p = ((1 - PARTIAL) if bool(t.t1) else 1.0) * (xpx - entry) * d / R
                if bool(t.t1):
                    p += PARTIAL * (t1p - entry) * d / R
            if abs(p - float(t.pnl_R)) > 1e-6:
                code, detail = "PNL_MATH", f"stamped {t.pnl_R:+.6f} vs recomputed {p:+.6f}"
        if code:
            defects.append((sym, kind, t.origin, d, t.reason, t.pnl_R, code, detail))
    return defects, [], len(tr), skipped_probe


def main():
    print(f"trade_audit {VERSION} | time-located bars | conventions named | era stamps")
    paths = sorted(glob.glob("reports/trades_*.csv"))
    if len(sys.argv) > 1:
        paths = [f"reports/trades_{s}.csv" for s in sys.argv[1:]]
    all_rows = []
    for tp in paths:
        base = tp.replace("\\", "/").split("/")[-1]
        if base.startswith("trades_d703_"):
            print(f"[{base}] d703 probe ledger - not audited (base-semantics audit)")
            continue
        if base.startswith("trades_m3_"):
            kind, sym = "m3", base[len("trades_m3_"):-4]
            stp = f"reports/setups_{sym}.csv"
        elif base.startswith("trades_m2_"):
            kind, sym = "m2", base[len("trades_m2_"):-4]
            stp = f"reports/setups_m2_{sym}.csv"
        else:
            kind, sym = "m3g", base[len("trades_"):-4]
            stp = f"reports/setups_{sym}.csv"
        try:
            raw = pd.read_csv(f"data/{sym}_M15.csv", usecols=["time"])
            tt = pd.to_datetime(raw["time"])
            mono = bool(tt.is_monotonic_increasing)
            ndup = int(tt.duplicated().sum())
            if not mono or ndup:
                print(f"[{sym}|LAKE] WARNING: monotonic={mono} duplicate_timestamps={ndup}")
            dfx, notes, n_tr, n_skip = audit_symbol(sym, tp, stp, kind)
            lake_tp = f"data/{sym}_M15.csv"
            lake_newer = os.path.exists(lake_tp) and os.path.getmtime(lake_tp) > os.path.getmtime(tp)
            if lake_newer:
                print(f"[{sym}|{kind}] !!! LAKE NEWER THAN LEDGER - the lake was touched "
                      f"after these trades were stamped; every defect on this line is "
                      f"a vintage artifact. RESTAMP (05 -> 05b -> 09).")
        except FileNotFoundError as e:
            print(f"[{sym}|{kind}] {e}"); continue
        for note in notes:
            print(f"[{sym}|{kind}] {note}")
        all_rows += dfx
        df_real = [r for r in dfx if r[6] not in CONVENTION_CODES and r[6] != "LAKE_DISORDER"]
        era_t = pd.Timestamp(os.path.getmtime(tp), unit="s").strftime("%H:%M")
        era_s = pd.Timestamp(os.path.getmtime(stp), unit="s").strftime("%H:%M")
        era_l = (pd.Timestamp(os.path.getmtime(f"data/{sym}_M15.csv"), unit="s").strftime("%H:%M")
                 if os.path.exists(f"data/{sym}_M15.csv") else "MISSING")
        print(f"[{sym}|{kind}] audited={n_tr} (probe skipped: {n_skip}) "
              f"real_defects={len(df_real)} conventions={len(dfx)-len(df_real)} "
              f"era trades={era_t} setups={era_s} lake={era_l}")
    if all_rows:
        out = pd.DataFrame(all_rows, columns=["symbol", "ledger", "origin", "direction",
                                              "reason", "pnl_R", "code", "detail"])
        out.to_csv("reports/trade_audit.csv", index=False)
        conventions = out[out.code.isin(CONVENTION_CODES)]
        disorder = out[out.code == "LAKE_DISORDER"]
        defects = out[~out.code.isin(CONVENTION_CODES) & (out.code != "LAKE_DISORDER")]
        print("\n=== CONVENTIONS (documented gap fills / same-bar - NOT defects) ===")
        print(conventions.groupby("code").agg(n=("code", "size"),
                                              pnl_sum=("pnl_R", "sum")).to_string()
              if len(conventions) else "  none")
        print("\n=== LAKE DISORDER (stamped index != timestamp location) ===")
        if len(disorder):
            print(disorder.groupby("symbol").size().to_string())
        else:
            print("  none")
        print("\n=== REAL DEFECTS BY CODE (full table: reports/trade_audit.csv) ===")
        print(defects.groupby("code").agg(n=("code", "size"),
                                          pnl_sum=("pnl_R", "sum")).to_string()
              if len(defects) else "  NONE - AUDIT CLEAN")
        if len(defects):
            print("\nworst 10 defect rows:")
            print(defects.nsmallest(10, "pnl_R").to_string(index=False))
            print(f"\nREAL DEFECT sum: {defects.pnl_R.sum():+.2f}R across {len(defects)} trades")
        else:
            print("\nAUDIT CLEAN on time-located bars: exits geometrically real,"
                  " ordering holds, PnL recomputes exactly.")
    else:
        print("\nAUDIT CLEAN: every stamped exit is geometrically real on the bars,"
              " ordering holds, PnL recomputes exactly.")


if __name__ == "__main__":
    main()
