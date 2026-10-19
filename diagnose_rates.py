import MetaTrader5 as mt5
import importlib.metadata
import time
from datetime import datetime

print("MetaTrader5 package version:", importlib.metadata.version("MetaTrader5"))

if not mt5.initialize():
    print("init failed"); quit()

print("Terminal build:", mt5.terminal_info().build)

sym = "EURUSD"
tf  = mt5.TIMEFRAME_M15
print("symbol_select:", mt5.symbol_select(sym, True))
print("TIMEFRAME_M15 value:", tf)

time.sleep(2)   # give the terminal a moment to sync after init

def report(tag, r):
    print(f"{tag}: {'None' if r is None else str(len(r)) + ' bars'}  last_error={mt5.last_error()}")

# T1: smallest possible request, enum timeframe
report("T1 from_pos(sym, M15, 0, 10)      ", mt5.copy_rates_from_pos(sym, tf, 0, 10))

# T2: same but raw integer timeframe instead of enum
report("T2 from_pos(sym, 15, 0, 10)       ", mt5.copy_rates_from_pos(sym, 15, 0, 10))

# T3: copy_rates_from with a datetime start
report("T3 from(datetime Oct-1, 10)       ", mt5.copy_rates_from(sym, tf, datetime(2026, 10, 1), 10))

# T4: range with datetime objects, short window
report("T4 range(Oct-1 .. now, datetimes) ", mt5.copy_rates_range(sym, tf, datetime(2026, 10, 1), datetime.now()))

# T5: range with INTEGER epoch seconds, short window
report("T5 range(Oct-1 .. now, int epoch) ", mt5.copy_rates_range(sym, tf, int(datetime(2026, 10, 1).timestamp()), int(time.time())))

# T6: the full 2021..now range, int epoch
report("T6 range(2021 .. now, int epoch)  ", mt5.copy_rates_range(sym, tf, int(datetime(2021, 1, 1).timestamp()), int(time.time())))

# T7: different symbol, same shape as T1
report("T7 GBPUSD from_pos tiny           ", mt5.copy_rates_from_pos("GBPUSD", tf, 0, 10))

# T8: different timeframe, same shape as T1
report("T8 EURUSD H1 from_pos tiny        ", mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 10))

# T9: big count on from_pos
report("T9 from_pos(sym, M15, 0, 100000)  ", mt5.copy_rates_from_pos(sym, tf, 0, 100000))

mt5.shutdown()
print("Done. Paste this whole output to your developer.")