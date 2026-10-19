"""Quant_Lab shared loader. Research reads CSVs, never the terminal."""
import os
import pandas as pd

DATA_DIR = "data"
SYMBOLS = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCHF",
           "USDCAD", "USDJPY", "AUDJPY", "NZDJPY"]

def load(symbol, tf="M15"):
    """Load one symbol's history from the lake as a DataFrame."""
    path = os.path.join(DATA_DIR, f"{symbol}_{tf}.csv")
    return pd.read_csv(path, index_col="time", parse_dates=["time"])

def pip_size(symbol):
    """JPY pairs quote pips at 0.01; everything else at 0.0001."""
    return 0.01 if symbol.endswith("JPY") else 0.0001