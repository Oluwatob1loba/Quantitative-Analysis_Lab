import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from datetime import datetime
import os


# ============ CONFIG — THE ARCHITECT'S DIALS ============
SYMBOLS    = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCHF",
              "USDCAD", "USDJPY", "AUDJPY", "NZDJPY"]
TIMEFRAME  = mt5.TIMEFRAME_M15
TF_NAME    = "M15"
START_DATE = datetime(2021, 1, 1)
PAGE_SIZE  = 10_000
MAX_PAGES  = 200
SKIP_EXISTING = True    # set False to force a fresh pull of everything
# =========================================================

def fetch_symbol(symbol):
    """Page backwards through one symbol's history. Returns (DataFrame, reached_start)."""
    if not mt5.symbol_select(symbol, True):
        print(f"  [{symbol}] not found in Market Watch - skipped.")
        return None, False
    chunks, pos, reached_start = [], 0, False
    for page_no in range(1, MAX_PAGES + 1):
        page = mt5.copy_rates_from_pos(symbol, TIMEFRAME, pos, PAGE_SIZE)
        if page is None or len(page) == 0:
            print(f"    p{page_no}: empty (last_error={mt5.last_error()})")
            break
        chunks.append(page)
        oldest = pd.to_datetime(int(page[0]["time"]), unit="s")
        print(f"    p{page_no}: {len(page):>6,} bars | oldest {oldest}")
        pos += len(page)
        if oldest <= pd.Timestamp(START_DATE):
            reached_start = True
            break
        if len(page) < PAGE_SIZE:
            break                      # organic end of server memory
    if not chunks:
        return None, False
    df = pd.concat([pd.DataFrame(c) for c in chunks], ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df = df.set_index("time")
    df = df[~df.index.duplicated(keep="first")].sort_index()
    df = df[df.index >= pd.Timestamp(START_DATE)]
    return df, reached_start

print(f"Fetching {len(SYMBOLS)} symbols @ {TF_NAME} from {START_DATE.date()} ...")
if not mt5.initialize():
    print("initialize() failed. Is MT5 open?")
    quit()

os.makedirs("data", exist_ok=True)
report = []
for symbol in SYMBOLS:
    path = f"data/{symbol}_{TF_NAME}.csv"
    if SKIP_EXISTING and os.path.exists(path):
        print(f"[{symbol}] CSV already exists - skipped.")
        report.append((symbol, "existing"))
        continue
    print(f"[{symbol}] paging...")
    df, reached_start = fetch_symbol(symbol)
    if df is None or len(df) == 0:
        print(f"[{symbol}] FAILED - no data.")
        report.append((symbol, "FAILED"))
        continue
    df.to_csv(path)
    if not reached_start:
        print(f"[{symbol}] NOTE: server depth ends {df.index[0].date()} for {TF_NAME}.")
    print(f"[{symbol}] saved {len(df):,} bars | {df.index[0]} -> {df.index[-1]}")
    report.append((symbol, f"{len(df):,} bars  {df.index[0].date()} -> {df.index[-1].date()}"))

mt5.shutdown()

print()
print("=" * 60)
print("DATA LAKE MANIFEST")
print("=" * 60)
for symbol, status in report:
    print(f"  {symbol:<10} {status}")
print("=" * 60)