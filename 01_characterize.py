import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")            # render to file, no popup window
import matplotlib.pyplot as plt
from lab import load, SYMBOLS, pip_size

os.makedirs("reports", exist_ok=True)

rows = []
for sym in SYMBOLS:
    df = load(sym)
    # True Range per candle, then a 14-candle average = the pair's "normal move"
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr14_pips = tr.rolling(14).mean().iloc[-1] / pip_size(sym)

    # When is this pair actually alive? Average tick volume per hour of day.
    hourly = df.groupby(df.index.hour)["tick_volume"].mean()
    top3 = hourly.sort_values(ascending=False).head(3).index

    rows.append({
        "symbol": sym,
        "bars": f"{len(df):,}",
        "atr14_pips": round(atr14_pips, 1),
        "avg_spread_pts": round(df["spread"].mean(), 1),
        "alive_hours_server": ", ".join(f"{h:02d}:00" for h in top3),
    })

report = pd.DataFrame(rows)
print(report.to_string(index=False))
report.to_csv("reports/characterize.csv", index=False)

# ---- Your first chart, from your own lake ----
df = load("EURUSD")
fig, axes = plt.subplots(2, 1, figsize=(12, 7))
axes[0].plot(df.index[-2000:], df["close"][-2000:], lw=0.8, color="tab:blue")
axes[0].set_title("EURUSD M15 close - last 2,000 candles from your lake")
hourly = df.groupby(df.index.hour)["tick_volume"].mean()
axes[1].bar(hourly.index, hourly.values, color="tab:orange")
axes[1].set_title("EURUSD average tick volume by hour of day (SERVER time)")
axes[1].set_xticks(range(0, 24, 2))
fig.tight_layout()
fig.savefig("reports/first_look.png", dpi=120)
print("\nChart saved to reports/first_look.png - open it.")