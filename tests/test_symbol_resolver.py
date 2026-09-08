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

    @patch("src.core.mt5_connector.mt5")
    def test_get_current_tick_auto_resolves_symbol(self, mock_mt5):
        """Verify get_current_tick auto-resolves symbol variations like BTCUSD.c to Demo BTCUSD."""
        def mock_symbol_info(sym):
            if sym == "BTCUSD":
                m = MagicMock()
                m.trade_mode = 4
                m.point = 0.01
                m.digits = 2
                m.trade_tick_value = 1.0
                m.trade_tick_size = 0.01
                return m
            return None

        def mock_symbol_info_tick(sym):
            if sym == "BTCUSD":
                t = MagicMock()
                t.ask = 80100.0
                t.bid = 80090.0
                t.last = 80095.0
                t.volume = 10
                t.time = 1700000000
                return t
            return None

        mock_mt5.symbol_info.side_effect = mock_symbol_info
        mock_mt5.symbol_info_tick.side_effect = mock_symbol_info_tick
        mock_mt5.SYMBOL_TRADE_MODE_FULL = 4

        # Calling with BTCUSD.c on demo broker should auto-resolve to BTCUSD and succeed
        tick = mt5_connector.get_current_tick("BTCUSD.c")
        self.assertIsNotNone(tick)
        self.assertEqual(tick["ask"], 80100.0)
        self.assertEqual(tick["bid"], 80090.0)
        self.assertEqual(tick["point"], 0.01)
        self.assertEqual(tick["digits"], 2)
        self.assertIn("usd_per_point", tick)

    @patch("src.core.mt5_connector.mt5")
    def test_get_current_tick_returns_none_when_unavailable(self, mock_mt5):
        """Verify get_current_tick returns None gracefully when tick is not available."""
        mock_mt5.symbol_info.return_value = None
        mock_mt5.symbol_info_tick.return_value = None
        mock_mt5.SYMBOL_TRADE_MODE_FULL = 4

        tick = mt5_connector.get_current_tick("NONEXISTENT")
        self.assertIsNone(tick)

if __name__ == "__main__":
    unittest.main()
