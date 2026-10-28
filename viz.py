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
PRICE_TF = "4h"        # candle size for the price backdrop ("1h"/"4h"/"1D")
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
trades_path = f"reports/trades_{SYMBOL}.csv"
if os.path.exists(trades_path):
    tr = pd.read_csv(trades_path, parse_dates=["origin"])
    for _, t in tr.iterrows():
        outcome[(t.origin, int(t.direction))] = f"{t.pnl_R:+.2f}R ({t.reason})"

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

fig = go.Figure()
fig.add_trace(go.Candlestick(
    x=px.index, open=px.open, high=px.high, low=px.low, close=px.close,
    name=f"{SYMBOL} {PRICE_TF}",
    increasing_line_color="#26a69a", decreasing_line_color="#ef5350"))

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
    fig.add_shape(type="rect", x0=r.origin, y0=r.manLow, x1=r.availableAt, y1=r.manHigh,
                  line=dict(color="RoyalBlue", width=1),
                  fillcolor="rgba(65,105,225,0.12)")
    if r.get("zoneLow") == r.get("zoneLow"):
        fig.add_shape(type="rect", x0=r.availableAt, y0=r.zoneLow, x1=t_fut, y1=r.zoneHigh,
                      line=dict(color=edge, width=1, dash="dash"),
                      fillcolor="rgba(128,128,128,0.10)")

fig.update_layout(
    title=f"RINO eyeball - {SYMBOL} | {PRICE_TF} | drag the bottom strip to move the window",
    template="plotly_dark", hovermode="closest", dragmode="pan",
    xaxis=dict(rangeslider=dict(visible=True),
               range=[win_start, win_end]),
    yaxis=dict(range=[y_lo - y_pad, y_hi + y_pad], fixedrange=False),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    margin=dict(t=90, b=40),
)
fig.update_xaxes(rangeselector=dict(buttons=[
    dict(count=1, label="1m", step="month", stepmode="backward"),
    dict(count=3, label="3m", step="month", stepmode="backward"),
    dict(count=6, label="6m", step="month", stepmode="backward"),
    dict(count=1, label="1y", step="year", stepmode="backward"),
    dict(step="all", label="all")]))

# --- embedded y-refit: y-axis follows whichever time window is visible ---
_t = (px.index.view("int64") // 10**6).tolist()   # ms ints
_lo = px.low.tolist(); _hi = px.high.tolist()
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
