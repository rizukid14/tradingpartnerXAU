"""Test fetch balance TokoCrypto."""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.ERROR)

from src.core import ccxt_connector as conn

try:
    b = conn.get_account_balance_usdt()
    print("balance:", b)
except Exception as e:
    print("ERR:", type(e).__name__, str(e)[:400])
