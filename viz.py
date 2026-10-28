"""viz.py - interactive eyeball-verification chart for RINO setups.

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
SYMBOL = "EURUSD"      # which symbol's setups to draw
PRICE_TF = "1D"        # candle size for the price backdrop ("1h"/"4h"/"1D")
WINDOW_DAYS = 60       # length of the time window (slide it from the browser)
START_AT = None        # "YYYY-MM-DD" to center the window elsewhere, None = latest data
SHOW_CONTEXT = True    # True = also draw CONTEXT records (faded)
# --------------------------------------

setups_path = f"reports/setups_{SYMBOL}.csv"
if not os.path.exists(setups_path):
    raise SystemExit(f"{setups_path} not found - run 05_multisymbol.py first.")
su = pd.read_csv(setups_path, parse_dates=["origin", "availableAt"])

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
outcome = {}
try:
    from rino_backtest import run_backtest
    from lab import pip_size
    _tr = run_backtest(lake, su, mintick=pip_size(SYMBOL) / 10, mode="base")
    for _, t in _tr.iterrows():
        outcome[(t.origin, int(t.direction))] = f"{t.pnl_R:+.2f}R ({t.reason})"
    print(f"outcomes: BASE mode, {len(_tr)} trades (computed here, not read from the 05 CSV)")
except Exception as e:
    print(f"outcomes unavailable ({e}) - hover cards will skip results")

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
    k = (r.origin, int(r.direction))
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

for direction, dname, color in [(1, "LONG", "#2ecc71"), (-1, "SHORT", "#e74c3c")]:
    sub = act[act.direction == direction]
    if not len(sub):
        continue
    fig.add_trace(go.Scatter(
        x=sub.availableAt, y=sub.manClose, mode="markers",
        marker=dict(symbol="triangle-up" if direction == 1 else "triangle-down",
                    size=11, color=color, line=dict(width=1, color="white")),
        name=f"Setup {dname}", legendgroup=f"setup{direction}",
        text=[hover_card(r) for _, r in sub.iterrows()], hoverinfo="text"))

if SHOW_CONTEXT:
    ctx = su[su["actionable"] != True]
    fig.add_trace(go.Scatter(
        x=ctx.availableAt, y=ctx.manClose, mode="markers",
        marker=dict(symbol="circle", size=6, color="#888888", opacity=0.4),
        name=f"CONTEXT ({len(ctx)})", legendgroup="ctx",
        text=[hover_card(r) for _, r in ctx.iterrows()], hoverinfo="text"))

# gate-provider check: D1 FVGs from the lake whose band intersects an
# actionable setup's slice - answers "are gated setups on REAL gaps?" visually
SHOW_FVG = True
d1 = lake.resample("1D").agg({"low": "min", "high": "max", "open": "first", "close": "last"}).dropna()
bx, by, sx, sy, btxt, stxt = [], [], [], [], [], []
for i in range(2, len(d1)):
    lo0, hi0 = float(d1.low.iloc[i]), float(d1.high.iloc[i])
    hi2, lo2 = float(d1.high.iloc[i - 2]), float(d1.low.iloc[i - 2])
    if lo0 > hi2:
        band = (hi2, lo0); kind = 1
    elif hi0 < lo2:
        band = (hi0, lo2); kind = -1
    else:
        continue
    hit = None
    for _, r in act.iterrows():
        zl, zh = r.get("zoneLow"), r.get("zoneHigh")
        if pd.notna(zl) and pd.notna(zh) and max(band[0], zl) <= min(band[1], zh):
            hit = r; break
    if hit is None:
        continue
    y = (band[0] + band[1]) / 2
    txt = f"FVG {'bull' if kind == 1 else 'bear'} [{band[0]:g}, {band[1]:g}] - provider for {hit.origin:%Y-%m-%d} {'LONG' if hit.direction == 1 else 'SHORT'}"
    if kind == 1:
        bx.append(d1.index[i]); by.append(y); btxt.append(txt)
    else:
        sx.append(d1.index[i]); sy.append(y); stxt.append(txt)
if SHOW_FVG and (bx or sx):
    fig.add_trace(go.Scatter(x=bx, y=by, mode="markers",
        marker=dict(symbol="square", size=7, color="#3b82f6", line=dict(width=1, color="white")),
        name=f"FVG bull provider ({len(bx)})", legendgroup="fvgb", text=btxt, hoverinfo="text"))
    fig.add_trace(go.Scatter(x=sx, y=sy, mode="markers",
        marker=dict(symbol="square", size=7, color="#f59e0b", line=dict(width=1, color="white")),
        name=f"FVG bear provider ({len(sx)})", legendgroup="fvgs", text=stxt, hoverinfo="text"))

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
    title=dict(text=f"RINO eyeball - {SYMBOL} | {PRICE_TF}", font=dict(size=15)),
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
