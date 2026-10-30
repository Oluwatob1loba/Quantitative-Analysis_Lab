"""viz.py - interactive eyeball-verification chart for RINO setups.

RENDERING CONTRACT (D-PY-43): viz NEVER recomputes a trade. Outcomes and
journeys come ONLY from stamped execution records (reports/trades_*.csv,
written by 05 / 05b / 09 with entry_i/entry_px/exit_i/exit_px/times).
If stamps are missing, the chart says so and shows setups only.
Geometric truth of every stamp is enforced by trade_audit.py.

Cheapest possible visual parity harness: real price candles from your
own lake plus every setup the engine emitted, each layer toggleable from
the legend.

HOW TO DRIVE IT (Plotly controls, all in the browser):
- BOTTOM GREY STRIP = time machine. Drag its handles to set window size;
  drag its middle to slide the window across the whole history.
- BOX-DRAG on the plot = zoom that region. DOUBLE-CLICK = reset.
- MOUSE WHEEL = zoom at cursor.
- The y-axis RE-FITS to whatever time window is showing (small embedded
  script; if your browser blocks it, the initial window is still fitted
  and you can zoom manually).
- Hover any marker for the full setup card.

Dials at the top of this file. The terminal prints the lake span and the
exact window shown, so "is this really 60 days?" is always answerable.
"""
import os
import json
import webbrowser
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from lab import load

# ---------------- dials ----------------
SYMBOL = "AUDUSD"      # which symbol's setups to draw
PRICE_TF = "1D"        # candle size for the price backdrop ("1h"/"4h"/"1D")
WINDOW_DAYS = 60       # length of the time window (slide it from the browser)
START_AT = None        # "YYYY-MM-DD" to center the window elsewhere, None = latest data
SHOW_CONTEXT = True    # True = also draw CONTEXT records (faded)
SETS_PREFIX = "setups_"  # "setups_m2_" to view the raw Model-2 population (D-PY-33)
LEDGER = "base"             # which STAMPED ledger to draw: base (05) | m3 (09) | m2 auto
TRADE_MODE = "base"         # within the base ledger: base | d703
EXEC_Q = 0.75              # within the m3 ledger: quadrant to draw
# --------------------------------------

setups_path = f"reports/{SETS_PREFIX}{SYMBOL}.csv"
if not os.path.exists(setups_path):
    raise SystemExit(f"{setups_path} not found - run 05_multisymbol.py first.")
su = pd.read_csv(setups_path, parse_dates=["origin", "availableAt"])
M2_VIEW = SETS_PREFIX == "setups_m2_"

lake = load(SYMBOL)
agg = {c: f for c, f in [("open", "first"), ("high", "max"),
                          ("low", "min"), ("close", "last")] if c in lake.columns}
px = lake.resample(PRICE_TF.lower()).agg(agg).dropna(subset=["open", "high", "low", "close"])

# window: [win_start, win_end] fitted from dials; printed for diagnosis
last = px.index[-1]
if START_AT:
    win_end = min(pd.Timestamp(START_AT) + pd.Timedelta(days=WINDOW_DAYS), last)
else:
    win_end = last
win_start = win_end - pd.Timedelta(days=WINDOW_DAYS)

act = su[su["actionable"] == True].copy()
print(f"{SYMBOL}: {len(px)} {PRICE_TF} candles | lake {px.index[0]:%Y-%m-%d} -> {last:%Y-%m-%d}")
print(f"window shown: {win_start:%Y-%m-%d} -> {win_end:%Y-%m-%d} "
      f"({(win_end - win_start).days} days) | {len(act)} actionable / {len(su)} total setups")

# fitted y fallback (used if the y-refit script is blocked)
m = (px.index >= win_start) & (px.index <= win_end)
y_lo, y_hi = float(px.low[m].min()), float(px.high[m].max())
y_pad = (y_hi - y_lo) * 0.08 or 1e-5

# optional: attach backtest outcomes
# --- stamped execution records ONLY (no recompute; D-PY-43) ---
TR = None
if M2_VIEW:
    trades_path = f"reports/trades_m2_{SYMBOL}.csv"
elif LEDGER == "m3":
    trades_path = f"reports/trades_m3_{SYMBOL}.csv"
else:
    trades_path = (f"reports/trades_{TRADE_MODE}_{SYMBOL}.csv" if TRADE_MODE != "base"
                   else f"reports/trades_{SYMBOL}.csv")
_stamp_need = {"entry_i", "entry_px", "exit_i", "exit_px", "exit_time", "pnl_R", "reason"}
if os.path.exists(trades_path):
    _tr = pd.read_csv(trades_path, parse_dates=["origin", "entry_time", "exit_time"])
    if _stamp_need.issubset(_tr.columns):
        TR = _tr
        if "quadrant" in TR.columns:
            TR = TR[TR.quadrant == EXEC_Q]
            print(f"trades: {len(TR)} STAMPED M3 records (quadrant={EXEC_Q}) from {trades_path}")
        elif "mode" in TR.columns:
            TR = TR[TR["mode"] == TRADE_MODE]
            print(f"trades: {len(TR)} STAMPED {TRADE_MODE} records from {trades_path}")
    else:
        print(f"{trades_path} lacks execution stamps - rerun 05/05b/09; setups shown WITHOUT outcomes")
else:
    print(f"{trades_path} not found - run 05_multisymbol.py (or 05b/09) first; setups shown WITHOUT outcomes")
outcome = {}
if TR is not None:
    for _, t in TR.drop_duplicates(subset=["origin", "direction"]).iterrows():
        outcome[(t.origin, int(t.direction))] = (f"{t.pnl_R:+.2f}R ({t.reason}) "
                                                 f"@ {t.exit_time:%Y-%m-%d} [{t.exit_px:g}]")

def _ts(r, col):
    """seriesStart/seriesEnd arrive as epoch-MS numbers; pd.to_datetime(int)
    would read nanoseconds and land in 1970, stretching boxes to the chart's
    left edge. Parse numerics explicitly and sanity-floor the result."""
    x = r.get(col)
    if x is None or pd.isna(x):
        return None
    if hasattr(x, "year"):
        return x
    try:
        f = float(x)
    except (TypeError, ValueError):
        return pd.to_datetime(x)                      # ISO string
    if not np.isfinite(f) or f < 1e11:                 # ~1973+ in epoch ms
        return None
    return pd.to_datetime(f, unit="ms")


def hover_card(r):
    grade = r.get("grade", "?"); grade = "?" if pd.isna(grade) else grade
    bits = [
        f"<b>{'LONG' if r.direction == 1 else 'SHORT'} "
        f"{r.get('setupClass','?')} / grade {grade}</b>",
        f"episode {r.origin:%Y-%m-%d} -> eligible {r.availableAt:%Y-%m-%d}",
        f"stop {r.stop:g}   target {r.target:g} ({r.targetTf})",
    ]
    for label, col in [("confluence", "confluenceLayers"), ("break", "breakClass")]:
        v = r.get(col)
        if v is not None and pd.notna(v):
            bits.append(f"{label}: {v}")
    if bool(r.get("keyTimeSweep", False)):
        bits.append("key-time raid: YES")
    why = r.get("contextReason")
    if why is not None and pd.notna(why) and str(why) != "":
        bits.append(f"refused: {why}")
    stt = r.get("state")
    if stt is not None and pd.notna(stt) and stt != "MANIPULATION":
        et = _ts(r, "endTime")
        bits.append(f"state: {stt}" + (f" @ {et:%Y-%m-%d}" if et is not None else ""))
    if not M2_VIEW:
        k = (r.origin, int(r.direction))
        if k in prov_map:
            bits.append(prov_map[k])
        else:
            bits.append("provider: NONE (engine gap feed found no qualifying FVG)")
    if k in outcome:
        bits.append(f"outcome: {outcome[k]}")
    return "<br>".join(bits)

CANDLE_PAD_DAYS = 120     # render candles only this far past the window (freedom without weight)
pad_lo, pad_hi = win_start - pd.Timedelta(days=CANDLE_PAD_DAYS), win_end + pd.Timedelta(days=CANDLE_PAD_DAYS)
pc = px[(px.index >= pad_lo) & (px.index <= pad_hi)]
daily = lake.resample("1D").agg({"low": "min", "high": "max"}).dropna()

fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=pc.index, open=pc.open, high=pc.high, low=pc.low, close=pc.close,
    name=f"{SYMBOL} {PRICE_TF} (window +/-{CANDLE_PAD_DAYS}d)",
    increasing_line_color="#26a69a", decreasing_line_color="#ef5350", showlegend=False))
fig.add_trace(go.Scatter(x=pc.index, y=pc.close, mode="lines",
    line=dict(color="#26a69a", width=3), name=f"{SYMBOL} {PRICE_TF}", legendgroup="price",
    showlegend=True, hoverinfo="skip"))
fig.add_trace(go.Scatter(x=daily.index, y=(daily.low + daily.high) / 2, mode="lines",
    line=dict(color="#3a3a3a", width=1), name="context (1D)", legendgroup="ctx1d",
    showlegend=False, hoverinfo="skip"))

# gate-provider audit (Qwen Task D fix): run the ENGINE'S OWN FvgFeed class with
# pruning disabled for audit visibility, then apply the exact stored-provider
# predicates (direction, slice intersection, availability, D-610 L1 fill). Same
# objects as the gate saw - no recomputation drift.
SHOW_FVG = not M2_VIEW
if M2_VIEW:
    print("M2 view: FVG provider layer suppressed - M2 has no POI gate (D-PY-33)")
bx, by, sx, sy, btxt, stxt = [], [], [], [], [], []
prov_map = {}
try:
    import copy as _copy
    from rino_config import config_for as _config_for
    from rino_dol import tf_key as _tf_key
    from rino_setup import FvgFeed as _FvgFeed
    _cfg = _copy.deepcopy(_config_for(SYMBOL))
    _cfg.retained_zones = 10**9      # audit visibility: keep full gap history
    _cfg.zone_age = 10**9
    _feed = _FvgFeed(_cfg, _tf_key(_cfg.tf1))
    _agg = {c: f for c, f in [("open", "first"), ("high", "max"),
                              ("low", "min"), ("close", "last")] if c in lake.columns}
    _tf1f = lake.resample(_cfg.tf1.lower()).agg(_agg).dropna(subset=["open", "high", "low", "close"])
    _cb = _tf1f.index
    for _i in range(len(_tf1f)):
        _t = _cb[_i + 1] if _i + 1 < len(_cb) else _cb[_i] + (_cb[_i] - _cb[_i - 1])
        _r = _tf1f.iloc[_i]
        _feed.on_roll(_t, float(_r.open), float(_r.high), float(_r.low), float(_r.close), _cb[_i])
    for _, r in act.iterrows():
        zl, zh = r.get("zoneLow"), r.get("zoneHigh")
        if not (pd.notna(zl) and pd.notna(zh)):
            continue
        for g in _feed.gaps:
            if g.kind != "FVG" or g.direction != int(r.direction):
                continue
            if not (g.upper >= zl and g.lower <= zh):
                continue
            if g.available_at is None or g.available_at > r.availableAt:
                continue
            if not (g.ended_at is None or g.ended_at >= r.origin):
                continue
            y = (g.lower + g.upper) / 2
            txt = (f"FVG {'bull' if g.direction == 1 else 'bear'} [{g.lower:g}, {g.upper:g}] "
                   f"formed {str(g.origin)[:10]} - engine gap feed, L1+timing verified")
            prov_map[(r.origin, int(r.direction))] = txt
            if g.direction == 1:
                bx.append(r.availableAt); by.append(y); btxt.append(txt)
            else:
                sx.append(r.availableAt); sy.append(y); stxt.append(txt)
            break
    n_prov = len(bx) + len(sx)
    print(f"FVG provider audit: {n_prov} of {len(act)} actionable setups matched the engine "
          f"gap feed (L1 fill + timing + slice)")
except Exception as e:
    print(f"provider audit unavailable ({e})")
    prov_map = {}
if SHOW_FVG and (bx or sx):
    fig.add_trace(go.Scatter(x=bx, y=by, mode="markers",
        marker=dict(symbol="square", size=7, color="#3b82f6", line=dict(width=1, color="white")),
        name=f"FVG bull provider ({len(bx)})", legendgroup="fvgb", text=btxt, hoverinfo="text"))
    fig.add_trace(go.Scatter(x=sx, y=sy, mode="markers",
        marker=dict(symbol="square", size=7, color="#f59e0b", line=dict(width=1, color="white")),
        name=f"FVG bear provider ({len(sx)})", legendgroup="fvgs", text=stxt, hoverinfo="text"))

for direction, dname, color in [(1, "LONG", "#2ecc71"), (-1, "SHORT", "#e74c3c")]:
    sub = act[act.direction == direction]
    if not len(sub):
        continue
    fig.add_trace(go.Scatter(
        x=sub.availableAt, y=sub.manClose, mode="markers",
        marker=dict(symbol="triangle-up" if direction == 1 else "triangle-down",
                    size=11, color=color, opacity=[0.4 if pd.notna(r.get("endTime")) else 1.0
                                                   for _, r in sub.iterrows()],
                    line=dict(width=1, color="white")),
        name=f"Setup {dname}", legendgroup=f"setup{direction}",
        text=[hover_card(r) for _, r in sub.iterrows()], hoverinfo="text"))

if SHOW_CONTEXT:
    ctx = su[su["actionable"] != True]
    fig.add_trace(go.Scatter(
        x=ctx.availableAt, y=ctx.manClose, mode="markers",
        marker=dict(symbol="circle", size=6, color="#888888", opacity=0.4),
        name=f"CONTEXT ({len(ctx)})", legendgroup="ctx",
        text=[hover_card(r) for _, r in ctx.iterrows()], hoverinfo="text"))

# --- stamped trade journeys: entry marker -> exit marker, exactly as booked ---
if TR is not None and len(TR):
    jx, jy = [], []
    for _, t in TR.iterrows():
        jx += [t.entry_time, t.exit_time, None]
        jy += [t.entry_px, t.exit_px, None]
    fig.add_trace(go.Scatter(x=jx, y=jy, mode="lines", name=f"trade path ({len(TR)})",
                             line=dict(color="#9aa4b2", width=1.2),
                             legendgroup="jrn", hoverinfo="skip"))
    for plus, name, col in ((True, "exit win", "#2ecc71"), (False, "exit loss", "#e74c3c")):
        seg = TR[(TR.pnl_R > 0) == plus]
        if not len(seg):
            continue
        fig.add_trace(go.Scatter(
            x=seg.exit_time, y=seg.exit_px, mode="markers",
            marker=dict(symbol="x", size=10, color=col),
            name=f"{name} ({len(seg)})", legendgroup="jrn",
            text=[f"exit {r.pnl_R:+.2f}R ({r.reason})<br>{r.exit_time} @ {r.exit_px:g}"
                  for _, r in seg.iterrows()], hoverinfo="text"))
    fig.add_trace(go.Scatter(
        x=TR.entry_time, y=TR.entry_px, mode="markers",
        marker=dict(symbol="diamond", size=9, color="#f1c40f",
                    line=dict(width=1, color="white")),
        name=f"entry fill ({len(TR)})", legendgroup="jrn",
        text=[f"ENTRY {r.direction:+d} {r.entry_time:%Y-%m-%d} @ {r.entry_px:g}<br>"
              f"exit {r.exit_time:%Y-%m-%d} @ {r.exit_px:g} -> {r.pnl_R:+.2f}R ({r.reason})"
              for _, r in TR.iterrows()], hoverinfo="text"))

def seg_trace(sub, col, name, color, dash, group):
    xs, ys = [], []
    for _, r in sub.iterrows():
        t0, t1 = r.availableAt, r.availableAt + pd.Timedelta(days=3)
        xs += [t0, t1, None]
        ys += [r[col], r[col], None]
    return go.Scatter(x=xs, y=ys, mode="lines", name=name,
                      line=dict(color=color, width=1, dash=dash),
                      legendgroup=group, hoverinfo="skip")

if len(act):
    fig.add_trace(seg_trace(act, "target", "Target", "Gold", None, "target"))
    fig.add_trace(seg_trace(act, "stop", "Stop", "#999999", "dot", "stop"))

for _, r in act.iterrows():   # boxes only for actionable: keeps the SVG light
    t_fut = r.availableAt + pd.Timedelta(days=3)
    edge = "#2ecc71" if r.direction == 1 else "#e74c3c"
    # display box = the EPISODE extent (soup -> completion). The series span
    # (old draw -> soup) is research attachment, not display - architect feedback.
    bx0, bx1 = r.origin, r.availableAt
    fig.add_shape(type="rect", x0=bx0, y0=r.manLow, x1=bx1, y1=r.manHigh,
                  line=dict(color="RoyalBlue", width=0.6),
                  fillcolor="rgba(65,105,225,0.07)")
    if r.get("zoneLow") == r.get("zoneLow"):
        fig.add_shape(type="rect", x0=r.availableAt, y0=r.zoneLow, x1=t_fut, y1=r.zoneHigh,
                      line=dict(color=edge, width=1, dash="dash"),
                      fillcolor="rgba(128,128,128,0.10)")

fig.update_layout(
    title=dict(text=f"RINO eyeball - {SYMBOL} | {PRICE_TF} | {SETS_PREFIX[:-1]} | "
                     f"ledger:{LEDGER}{" q" + str(EXEC_Q) if LEDGER == "m3" else ""}", font=dict(size=15)),
    template="plotly_dark", hovermode="closest", dragmode="pan",
    font=dict(family="Manrope, Geist, Segoe UI, sans-serif", size=13, color="#d9d9d9"),
    xaxis=dict(rangeslider=dict(visible=True),
               range=[win_start, win_end]),
    yaxis=dict(range=[y_lo - y_pad, y_hi + y_pad], fixedrange=False),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                font=dict(size=12), bgcolor="rgba(0,0,0,0)"),
    margin=dict(t=95, b=40),
)

# --- embedded y-refit: y-axis follows whichever time window is visible ---
_t = (daily.index.view("int64") // 10**6).tolist()   # daily context: full span
_lo = daily.low.tolist(); _hi = daily.high.tolist()
js = """
try {
  var T = __T__, LO = __LO__, HI = __HI__, N = T.length;
  var gd = document.querySelector('.js-plotly-plot') || document.querySelector('.plotly-graph-div');
  var self_echo = false;
  function lowerBound(x) { var lo = 0, hi = N - 1; while (lo < hi) { var m = (lo + hi) >> 1; if (T[m] < x) lo = m + 1; else hi = m; } return lo; }
  function upperBound(x) { var lo = 0, hi = N - 1; while (lo < hi) { var m = (lo + hi + 1) >> 1; if (T[m] > x) hi = m - 1; else lo = m; } return lo; }
  function refitY() {
    var lay = gd.layout; if (!lay || !lay.xaxis || !lay.xaxis.range) return;
    var x0 = new Date(lay.xaxis.range[0]).getTime();
    var x1 = new Date(lay.xaxis.range[1]).getTime();
    var i0 = lowerBound(x0), i1 = upperBound(x1); if (i1 < i0) return;
    var mn = Infinity, mx = -Infinity;
    for (var i = i0; i <= i1; i++) { if (LO[i] < mn) mn = LO[i]; if (HI[i] > mx) mx = HI[i]; }
    var pad = (mx - mn) * 0.08 || 1e-5;
    self_echo = true;
    Plotly.relayout(gd, {"yaxis.range": [mn - pad, mx + pad], "yaxis.autorange": false});
  }
  var timer = null;
  gd.on("plotly_relayout", function () {
    if (self_echo) { self_echo = false; return; }
    clearTimeout(timer);
    timer = setTimeout(function () { try { refitY(); } catch (e) {} }, 120);
  });
  refitY();
} catch (e) {}
"""
js = js.replace("__T__", json.dumps(_t)).replace("__LO__", json.dumps(_lo)).replace("__HI__", json.dumps(_hi))

html_path = os.path.abspath("reports/rino_chart.html")
fig.write_html(html_path, config={"scrollZoom": True, "displaylogo": False}, post_script=js)
print(f"Success! Open: {html_path}")
webbrowser.open(f"file://{html_path}")
