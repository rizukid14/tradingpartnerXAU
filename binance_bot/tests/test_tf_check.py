"""Cek mapping timeframe ccxt tokocrypto."""
import ccxt

ex = ccxt.tokocrypto()
print("timeframes:", list(ex.timeframes.keys()))
try:
    print("parseTimeframe 15m:", ex.parse_timeframe("15m"))
except Exception as e:
    print("parse err:", e)

# Cek kode sumber implementasi fetch_ohlcv tokocrypto
import inspect
src = inspect.getsource(type(ex).fetch_ohlcv)
print("--- fetch_ohlcv source (first 40 lines) ---")
print("\n".join(src.splitlines()[:40]))
