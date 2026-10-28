"""viz.py - interactive eyeball-verification chart for RINO setups.

Cheapest possible visual parity harness: real price candles from your
own lake plus every setup the engine emitted, each layer toggleable from
the legend. Rewrite of the original viz: the old one never drew price
at all (markers floated on an empty axis) and gave every one of ~375
setups its own legend row (~1,100 entries), which buried the chart.

Dials at the top. Everything else is automatic:
- price candles resampled from the lake (no TradingView needed)
- layers: LONG / SHORT markers, CONTEXT, targets, stops, CRT windows,
  F-strict POI slices
- hover any marker for the full setup card: direction, class, grade,
  target timeframe, confluence, key-time raid tag, break class, and the
  backtest outcome when reports/trades_<SYMBOL>.csv exists
"""
import os
import webbrowser
import pandas as pd
import plotly.graph_objects as go
from lab import load

# ---------------- dials ----------------
SYMBOL = "EURUSD"      # which symbol's setups to draw
PRICE_TF = "1H"        # candle size for the price backdrop ("1H"/"4H"/"1D")
LAST_DAYS = 365        # window shown on load; zoom out for full history
SHOW_CONTEXT = False   # True = also draw CONTEXT records (faded)
# --------------------------------------

setups_path = f"reports/setups_{SYMBOL}.csv"
if not os.path.exists(setups_path):
    raise SystemExit(f"{setups_path} not found - run 05_multisymbol.py first.")
su = pd.read_csv(setups_path, parse_dates=["origin", "availableAt"])

lake = load(SYMBOL)
agg = {c: f for c, f in [("open", "first"), ("high", "max"),
                          ("low", "min"), ("close", "last")] if c in lake.columns}
px = lake.resample(PRICE_TF).agg(agg).dropna(subset=["open", "high", "low", "close"])

act = su[su["actionable"] == True].copy()
print(f"{SYMBOL}: {len(px)} {PRICE_TF} candles | {len(act)} actionable / {len(su)} total setups")

# optional: attach backtest outcomes (from rino_backtest / 05_multisymbol)
outcome = {}
trades_path = f"reports/trades_{SYMBOL}.csv"
if os.path.exists(trades_path):
    tr = pd.read_csv(trades_path, parse_dates=["origin"])
    for _, t in tr.iterrows():
        outcome[(t.origin, int(t.direction))] = f"{t.pnl_R:+.2f}R ({t.reason})"

def hover_card(r):
    grade = r.get("grade", "?")
    grade = "?" if pd.isna(grade) else grade
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

# 1) price candles - the backdrop the old viz was missing
fig.add_trace(go.Candlestick(
    x=px.index, open=px.open, high=px.high, low=px.low, close=px.close,
    name=f"{SYMBOL} {PRICE_TF}",
    increasing_line_color="#26a69a", decreasing_line_color="#ef5350"))

# 2) setup markers - ONE trace per direction (not one per setup)
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

# 3) CONTEXT markers (optional, faded - label-only, never actionable)
if SHOW_CONTEXT:
    ctx = su[su["actionable"] != True]
    fig.add_trace(go.Scatter(
        x=ctx.availableAt, y=ctx.manClose, mode="markers",
        marker=dict(symbol="circle", size=6, color="#888888", opacity=0.4),
        name=f"CONTEXT ({len(ctx)})", legendgroup="ctx",
        text=[hover_card(r) for _, r in ctx.iterrows()], hoverinfo="text"))

# 4) targets + stops - one NaN-separated trace each (toggleable layers)
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

# 5) CRT window + F-strict POI slice per setup (shapes stay subtle)
for _, r in su.iterrows():
    t_fut = r.availableAt + pd.Timedelta(days=3)
    is_long = r.direction == 1
    edge = "#2ecc71" if is_long else "#e74c3c"
    fig.add_shape(type="rect", x0=r.origin, y0=r.manLow, x1=r.availableAt, y1=r.manHigh,
                  line=dict(color="RoyalBlue", width=1),
                  fillcolor="rgba(65,105,225,0.12)")
    if r.get("zoneLow") == r.get("zoneLow"):  # not NaN
        fig.add_shape(type="rect", x0=r.availableAt, y0=r.zoneLow, x1=t_fut, y1=r.zoneHigh,
                      line=dict(color=edge, width=1, dash="dash"),
                      fillcolor="rgba(128,128,128,0.10)")

# 6) layout: dark, legend along the top, every layer one toggleable row
end = px.index[-1]
fig.update_layout(
    title=f"RINO eyeball - {SYMBOL} | {PRICE_TF} | hover any marker for the setup card",
    template="plotly_dark", hovermode="closest",
    xaxis=dict(rangeslider=dict(visible=True), range=[end - pd.Timedelta(days=LAST_DAYS), end]),
    yaxis=dict(title="Price"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    margin=dict(t=90, b=40),
)
fig.update_xaxes(rangeselector=dict(buttons=[
    dict(count=1, label="1m", step="month", stepmode="backward"),
    dict(count=3, label="3m", step="month", stepmode="backward"),
    dict(count=6, label="6m", step="month", stepmode="backward"),
    dict(step="all", label="all")]))

html_path = os.path.abspath("reports/rino_chart.html")
fig.write_html(html_path)
print(f"Success! Open: {html_path}")
webbrowser.open(f"file://{html_path}")
