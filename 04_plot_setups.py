"""04_plot_setups.py — render engine setups on price for eyeball verification.
Trust protocol: compare these markers against TradingView (same dates/directions).
If the picture disagrees with your eye systematically, the engine is wrong somewhere.
If they agree, the backtest numbers are real. Saves reports/setups_view.png."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from lab import load

SYMBOL = "EURUSD"
MONTHS = 7      # how much recent history to draw

df = load(SYMBOL)
d1 = df.resample("1D").agg(open=("open", "first"), high=("high", "max"),
                           low=("low", "min"), close=("close", "last")).dropna()
cut = d1.index[-1] - pd.DateOffset(months=MONTHS)
d1 = d1.loc[d1.index >= cut]

st = pd.read_csv(f"reports/setups_{SYMBOL}.csv", parse_dates=["origin", "availableAt"])
st = st.loc[st.origin >= cut]

fig, ax = plt.subplots(figsize=(16, 9))
# candlesticks
for t, r in d1.iterrows():
    col = "#26a69a" if r.close >= r.open else "#ef5350"
    ax.plot([t, t], [r.low, r.high], color=col, lw=0.7, zorder=2)
    ax.add_patch(plt.Rectangle((t - pd.Timedelta(hours=8), min(r.open, r.close)),
                               pd.Timedelta(hours=16), abs(r.close - r.open) + 1e-9,
                               facecolor=col, edgecolor=col, zorder=3))
# setups
for _, s in st.iterrows():
    d = 1 if s.direction == 1 else -1
    col = "#089981" if s.actionable else "#9e9e9e"
    alpha = 0.95 if s.actionable else 0.45
    m = "^" if d == 1 else "v"
    ax.scatter(s.availableAt, s.entry, marker=m, s=90 if s.actionable else 40,
               facecolor=col if s.actionable else "none", edgecolor=col,
               linewidth=1.6, alpha=alpha, zorder=5)
    if s.actionable:
        ax.plot([s.availableAt, s.availableAt + pd.Timedelta(days=6)],
                [s.stop, s.stop], color="#f23645", lw=1.0, ls="--", alpha=0.8, zorder=4)
        ax.plot([s.availableAt, s.availableAt + pd.Timedelta(days=6)],
                [s.target, s.target], color=col, lw=1.0, ls=":", alpha=0.8, zorder=4)
        ax.annotate(f"{s.grade}/{s.setupClass}", (s.availableAt, s.entry),
                    textcoords="offset points", xytext=(6, 6 if d == 1 else -12),
                    fontsize=7, color=col, alpha=0.9)
ax.set_title(f"{SYMBOL} — engine setups, last {MONTHS} months "
             f"({int(st.actionable.sum())} actionable / {len(st)} total) | "
             "green/red = long/short, faded = CONTEXT, -- stop, : target")
ax.grid(alpha=0.2)
fig.tight_layout()
fig.savefig("reports/setups_view.png", dpi=130)
print(f"setups drawn: {len(st)} (actionable {int(st.actionable.sum())})")
print("saved reports/setups_view.png — open it and compare against TradingView.")
