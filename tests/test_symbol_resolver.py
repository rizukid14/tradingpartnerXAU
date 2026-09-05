"""
Unit tests for get_valid_trade_symbol in mt5_connector.py.
Verifies that root tickers are cleanly stripped and matched across both Demo and Live suffix conventions:
- Demo: BTCUSD (no .c, no ECN), EURUSD-ECN (no trailing c)
- Live: BTCUSD.c, EURUSD-ECNc
"""

import unittest
from unittest.mock import patch, MagicMock
from src.core import mt5_connector

class TestSymbolResolver(unittest.TestCase):

    def setUp(self):
        mt5_connector._valid_symbol_cache.clear()

    @patch("src.core.mt5_connector.mt5")
    def test_demo_symbol_resolution(self, mock_mt5):
        """Simulates MT5 connected to Demo broker where BTCUSD and EURUSD-ECN exist."""
        def mock_symbol_info(sym):
            if sym in ("BTCUSD", "EURUSD-ECN", "GBPUSD-ECN"):
                m = MagicMock()
                m.trade_mode = 4  # FULL
                return m
            return None

        mock_mt5.symbol_info.side_effect = mock_symbol_info
        mock_mt5.SYMBOL_TRADE_MODE_FULL = 4

        # 1. BTCUSD.c passed from config/env -> resolved to Demo BTCUSD
        res_btc = mt5_connector.get_valid_trade_symbol("BTCUSD.c")
        self.assertEqual(res_btc, "BTCUSD")

        # 2. EURUSD-ECNc passed from config/env -> resolved to Demo EURUSD-ECN
        res_eur = mt5_connector.get_valid_trade_symbol("EURUSD-ECNc")
        self.assertEqual(res_eur, "EURUSD-ECN")

        # 3. Clean root EURUSD -> resolved to EURUSD-ECN
        res_clean = mt5_connector.get_valid_trade_symbol("EURUSD")
        self.assertEqual(res_clean, "EURUSD-ECN")

    @patch("src.core.mt5_connector.mt5")
    def test_live_symbol_resolution(self, mock_mt5):
        """Simulates MT5 connected to Live broker where BTCUSD.c and EURUSD-ECNc exist."""
        def mock_symbol_info(sym):
            if sym in ("BTCUSD.c", "EURUSD-ECNc"):
                m = MagicMock()
                m.trade_mode = 4  # FULL
                return m
            return None

        mock_mt5.symbol_info.side_effect = mock_symbol_info
        mock_mt5.SYMBOL_TRADE_MODE_FULL = 4

        # 1. BTCUSD passed -> resolved to Live BTCUSD.c
        res_btc = mt5_connector.get_valid_trade_symbol("BTCUSD")
        self.assertEqual(res_btc, "BTCUSD.c")

        # 2. EURUSD-ECN passed -> resolved to Live EURUSD-ECNc
        res_eur = mt5_connector.get_valid_trade_symbol("EURUSD-ECN")
        self.assertEqual(res_eur, "EURUSD-ECNc")

if __name__ == "__main__":
    unittest.main()
