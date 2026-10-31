"""12_m2_study.py - MODEL 2 baseline (architect ruling D-PY-31): raw price delivery.

M2 (user naming; freeze-log D-201 "Model 2" + "Model 1"):
  admission = the EVENT only (episode completed). NO FVG gate, NO TSM gate.
  execution = (a) bar-0 market open after detection, and/or
              (b) resting limits along the rejection wick.
  QUADRANT LABELING (matches the architect's TradingView drawing, Pine
  bottom-up): for a LONG the wick zone runs low(tip) -> min(O,C)(body/open).
    p0  = the wick TIP (deepest point)
    p25 = 25% of the way from tip toward the body   (your "25 line")
    p50 = midpoint                                    (your "50 line")
    p75 = 75% from tip, close to the body             (your "75 line")
    p100 = the body/open (never a limit - no retrace needed)
  For SHORTS the zone is inverted: high(tip) -> max(O,C), same labeling.
  (Earlier tables labeled these from the extreme: old q1.0 = p0, old q0.75 =
  p25. Same prices, renamed.)

  geometry  = G1: long zone [manLow, min(manOpen,manC)], entry = midpoint;
              stop = extreme +/- 1 tick (v3StopTicksInput default).
  sanity    = CLASS_MIN / RAID_ONLY dials - the anti-"firing blindly" floor.
  hygiene   = FILL_MAX_DAYS: skip limit fills that happen more than N days
              after detection (a stale fill is a different thesis).

WHY THIS FILE EXISTS: M2 tested THROUGH the FVG gate is not M2. The engine
stamps every episode (incl. CONTEXT) with manOHLC + t1/target, so this study
runs without touching certified code. Pairs with 10_optimize (the gated
ledger): the DIFFERENCE between 12 and 10 is the price of the gates.
"""
import os
import importlib.util
import numpy as np
import pandas as pd
from lab import load, pip_size

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD",
           "USDCAD", "USDCHF", "AUDJPY", "NZDJPY"]
SPLIT_AT = pd.Timestamp("2024-01-01")
MODES = ["bar0", "limits"]
QUADRANTS = [1.0, 0.75, 0.5, 0.25]        # entry fraction from TIP toward body
CLASS_MIN = None                          # e.g. "A" -> only A/A+; None = all
RAID_ONLY = False
MIN_BREAK = "Major"                          # e.g. "Critical" -> the break-class gate alone
                                          # (Qwen true-sequence-minus-gates test, D-PY-51)
PARTIAL, MOVE_BE = 0.6, True
FILL_MAX_DAYS = 5                         # skip limit fills older than this
SETS_PREFIX = 'setups_m2_'                   # 'setups_m2_' for the D-PY-33 raw population

_spec = importlib.util.spec_from_file_location("opt", "10_optimize.py")
_opt = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_opt)
Bars, scan = _opt.Bars, _opt.scan


def reconstruct(row, mintick):
    d = 1 if row.direction == 1 else -1
    o, c, lo, hi = (float(row.manOpen), float(row.manClose),
                    float(row.manLow), float(row.manHigh))
    if d == 1:
        ext, body = lo, min(o, c)
    else:
        ext, body = hi, max(o, c)
    entry = (ext + body) / 2.0
    stop = ext - d * 1 * mintick
    return d, entry, stop, ext, body


def sim_symbol(sym):
    sp = f"reports/{SETS_PREFIX}{sym}.csv"
    if not os.path.exists(sp):
        return None
    su = pd.read_csv(sp, parse_dates=["origin", "availableAt"])
    if CLASS_MIN:
        su = su[su.setupClass.isin({"A": ("A", "A+"), "B": ("B",)}[CLASS_MIN])]
    if RAID_ONLY:
        su = su[su.keyTimeSweep == True]
    if MIN_BREAK:
        su = su[su.breakClass == MIN_BREAK]
    if not len(su):
        return None
    mintick = pip_size(sym) / 10
    bars = Bars(load(sym))
    out = {}
    skipped_r = 0
    for mode in MODES:
        for q in (QUADRANTS if mode == "limits" else [None]):
            rows = []
            for _, r in su.iterrows():
                d, entry, stop, ext, body = reconstruct(r, mintick)
                entry_px = ext + (body - ext) * (1.0 - q) if mode == "limits" else entry
                pos = int(np.searchsorted(bars.idx.view("int64"), r.availableAt.value))
                if pos >= bars.n:
                    continue
                if mode == "limits":
                    seg = slice(pos, None)
                    touch = (bars.low[seg] <= entry_px) if d == 1 else (bars.high[seg] >= entry_px)
                    j = int(np.argmax(touch))
                    if not touch[j]:
                        continue
                    if pd.Timestamp(bars.idx[pos + j]) - r.availableAt > pd.Timedelta(days=FILL_MAX_DAYS):
                        continue
                    pos = pos + j
                    fill = entry_px + d * float(bars.spread[pos]) * mintick
                else:
                    fill = float(bars.open[pos]) + d * float(bars.spread[pos]) * mintick
                    stop = float(r.stop) if pd.notna(r.stop) else stop
                spread_px = float(bars.spread[pos]) * mintick
                # degenerate R guard, belt AND braces: relative to cost AND an
                # absolute floor - spread can be 0 on some bars, which would
                # otherwise let a 1-tick stop through and explode expectancy.
                if abs(fill - stop) <= max(3 * spread_px, 15 * mintick):
                    skipped_r += 1
                    continue
                t1 = float(r.t1) if pd.notna(r.get("t1")) else None
                t2 = float(r.target)
                res = scan(bars, pos, d, fill, stop, t1, t2, PARTIAL, MOVE_BE)
                if res is None:
                    continue
                rows.append((r.availableAt, res["pnl"], d))
            if not rows:
                out[(mode, q)] = None; continue
            t = pd.DataFrame(rows, columns=["av", "r", "d"])
            def agg(seg):
                if not len(seg): return (0, np.nan)
                return (len(seg), seg["r"].mean())
            piece = {}
            for name, seg in (("all", t), ("long", t[t.d == 1]), ("short", t[t.d == -1])):
                piece[(name, "test")] = agg(seg[seg.av >= SPLIT_AT])
                piece[(name, "train")] = agg(seg[seg.av < SPLIT_AT])
            out[(mode, q)] = piece
    return out, skipped_r


def main():
    print(f"M2 baseline | CLASS_MIN={CLASS_MIN} RAID_ONLY={RAID_ONLY} "
          f"MIN_BREAK={MIN_BREAK} "
          f"PARTIAL={PARTIAL} BE={MOVE_BE} FILL_MAX_DAYS={FILL_MAX_DAYS} "
          f"| split {SPLIT_AT:%Y-%m-%d}")
    print("cells = test exp / train exp (trades) | p0 = wick tip ... p75 = toward body\n")
    cols = [f"{m} p{int((1-q)*100)}" if m == "limits" else m
            for m in MODES for q in (QUADRANTS if m == "limits" else [None])]
    print(f"{'symbol / dir':<14}" + "".join(f"{c:>21}" for c in cols))
    for sym in SYMBOLS:
        res = sim_symbol(sym)
        if res is None:
            print(f"{sym:<14}(missing)"); continue
        o, skipped_r = res
        for band in ("all", "long", "short"):
            label = sym if band == "all" else f"  {band}"
            cells = []
            for mode in MODES:
                for q in (QUADRANTS if mode == "limits" else [None]):
                    piece = o[(mode, q)]
                    if piece is None:
                        cells.append("-"); continue
                    (nt, et) = piece[(band, "test")]
                    (nr, er) = piece[(band, "train")]
                    cells.append(f"{et:+.3f}/{er:+.3f}({nt})" if nt else f"-/{er:+.3f}(0)")
            print(f"{label:<14}" + "".join(f"{c:>21}" for c in cells))
        if skipped_r:
            print(f"  ({skipped_r} trades skipped: stop within 3x spread - degenerate R)")


if __name__ == "__main__":
    main()
