import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from lab import load
from participation import add_participation_layer

SYMBOL = "EURUSD"
df = add_participation_layer(load(SYMBOL))

n = len(df)
print(f"{SYMBOL} participation layer over {n:,} candles")
print(f"  aggressive candles    : {df['is_aggressive'].sum():>8,}  ({df['is_aggressive'].mean():.1%})")
print(f"  strong displacement   : {df['strong_displacement'].sum():>8,}  ({df['strong_displacement'].mean():.1%})")
print(f"  absorption candidates : {df['is_absorption'].sum():>8,}  ({df['is_absorption'].mean():.1%})")
print(f"  mean aggression       : {df['aggression'].mean():.3f}")
print(f"  mean |CLV|            : {df['clv'].abs().mean():.3f}")

sd = df[df["strong_displacement"]]
print("\nStrong displacement by hour (server time), top 5:")
print(sd.groupby(sd.index.hour).size().sort_values(ascending=False).head(5).to_string())

os.makedirs("reports", exist_ok=True)
w = df.iloc[-2000:]
fig, ax = plt.subplots(figsize=(14, 7))
ax.plot(w.index, w["close"], lw=0.8, color="tab:blue", label="close")
ax.scatter(w.index[w["strong_displacement"]], w["close"][w["strong_displacement"]],
           color="green", marker="^", s=60, label="strong displacement", zorder=3)
ax.scatter(w.index[w["is_absorption"]], w["close"][w["is_absorption"]],
           color="blue", marker="o", s=40, label="absorption", zorder=3)
ax.set_title(f"{SYMBOL} M15 - participation layer (last 2,000 candles)")
ax.legend(loc="upper right")
fig.tight_layout()
fig.savefig("reports/participation.png", dpi=120)
print("\nChart saved to reports/participation.png")