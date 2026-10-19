import MetaTrader5 as mt5

print("Initializing Python Quant Lab...")

# 1. Connect to the MetaTrader 5 terminal running on your computer
if not mt5.initialize():
    print("initialize() failed. Is MT5 open and logged in?")
    mt5.shutdown()
    quit()

print("Successfully connected to MT5!")

# 2. Terminal-level info (the software itself)
terminal_info = mt5.terminal_info()
print(f"Terminal build: {terminal_info.build}")
print(f"Terminal connected: {terminal_info.connected}")

# 3. Account-level info (server, login, balance live HERE)
account_info = mt5.account_info()
if account_info is None:
    print("account_info() is None - MT5 is open but not logged into an account.")
else:
    print(f"Broker/Server: {account_info.server}")
    print(f"Login: {account_info.login}")
    print(f"Balance: {account_info.balance} {account_info.currency}")

# 4. Disconnect cleanly
mt5.shutdown()
print("Connection closed. Lab is ready.")