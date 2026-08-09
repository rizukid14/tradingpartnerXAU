"""Test koneksi testnet via connector (dengan User-Agent fix)."""
import sys
import logging

sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO, format="%(message)s")

import config
from src.core import binance_connector as c

print("REST_BASE:", config.REST_BASE)

st = c.server_time()
print("1. server_time:", "OK" if st else "FAIL")

info = c.get_symbol_info(config.SYMBOL)
print("2. symbol_info:", info)

t = c.get_ticker(config.SYMBOL)
print("3. ticker:", {k: t[k] for k in ("price", "spread_usd", "spread_pct")} if t else None)

bal = c.get_account_balance_usdt()
print("4. balance_usdt (signed):", bal)

qty = c.get_asset_balance(config.SYMBOL)
print("5. asset_balance (signed):", qty)

acc = c.get_account()
print("6. account OK:", acc is not None, "| balances:", len(acc.get("balances", [])) if acc else 0)

df = c.get_klines(config.SYMBOL, config.TIMEFRAME, 5)
print("7. klines:", "OK" if df is not None and len(df) > 0 else "FAIL", f"({len(df)} candles)" if df is not None else "")
