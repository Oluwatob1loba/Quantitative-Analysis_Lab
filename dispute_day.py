import pandas as pd
from lab import load
from rino_config import PRESET_A
from rino_clocks import attach_native

cfg = PRESET_A
DAY = "2026-09-25"
N = min(cfg.tf1_sub_lookback, cfg.tf1_lookback)

d = attach_native(load("EURUSD"), cfg.tf1, "tf1")
rolls = d[d["tf1_roll"]].reset_index()
i = rolls.index[rolls["tf1_cbucket"] == pd.Timestamp(DAY)][0]
cur = rolls.loc[i]
print(f"disputed candle {DAY}: O {cur.tf1_open}  H {cur.tf1_high}  L {cur.tf1_low}  C {cur.tf1_close}\n")
print(f"window = the {N} daily candles before it:")
for _, r in rolls.iloc[i - N:i].iterrows():
    updown = "up  " if r.tf1_close > r.tf1_open else "down" if r.tf1_close < r.tf1_open else "flat"
    hi = f"PDOL High @{r.tf1_high}" if r.tf1_close > r.tf1_open else f"SDOL High @{r.tf1_high}"
    lo = f"PDOL Low  @{r.tf1_low}"  if r.tf1_close < r.tf1_open else f"SDOL Low  @{r.tf1_low}"
    sh = "   <-- SWEPT by disputed candle" if cur.tf1_high > r.tf1_high else ""
    sl = "   <-- SWEPT by disputed candle" if cur.tf1_low  < r.tf1_low  else ""
    print(f"  {str(r.tf1_cbucket)[:10]} {updown}  {hi}{sh}    {lo}{sl}")
print("\nA SHORT requires a line ending 'PDOL High ... SWEPT'.")
print("Lines marked SWEPT that say SDOL = swept, but not soup, by your own rule.")