"""Test symbol rotation and helper logic for both Scanner Mode and Legacy Pairs Mode."""
import sys
import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import config

WIB = ZoneInfo("Asia/Jakarta")


class TestSymbolRotationAndHelpers(unittest.TestCase):
    def setUp(self):
        config.ENABLE_BTC_ROTATION = True

    def test_scanner_pool(self):
        # In scanner mode, rotation pool should contain all configured scanner symbols on weekdays
        wednesday = datetime(2026, 8, 12, 10, 0, tzinfo=WIB)
        pool = config.get_rotation_pool(wednesday)
        if config.SCANNER_MODE:
            self.assertEqual(len(pool), len(config.get_scanner_symbols(wednesday)))
            self.assertTrue(any("GBPUSD" in s for s in pool))
            self.assertTrue(all("XAUUSD" not in s for s in pool))
            self.assertNotIn("BTCUSD.c", pool)  # BTC must be OFF on weekdays
            self.assertTrue(any("EURJPY" in s for s in pool))
            self.assertTrue(any("USDJPY" in s for s in pool))
            self.assertEqual(config.get_max_open_positions(now=wednesday), config.MAX_OPEN_POSITIONS)

    def test_weekend_switch(self):
        # Weekend should return BTC if enabled and cap max positions to 2
        saturday = datetime(2026, 8, 8, 12, 0, tzinfo=WIB)
        pool = config.get_rotation_pool(saturday)
        self.assertEqual(pool, [config.WEEKEND_SYMBOL])
        self.assertEqual(config.get_max_open_positions(now=saturday), 2)

    def test_per_symbol_helpers(self):
        # XAU helpers
        self.assertEqual(config.lot_size_for("XAUUSD-ECNc"), 0.01)
        self.assertEqual(config.default_sl_points_for("XAUUSD-ECNc"), config.DEFAULT_SL_POINTS_XAU)
        self.assertEqual(config.default_tp_points_for("XAUUSD-ECNc"), config.DEFAULT_TP_POINTS_XAU)
        self.assertEqual(config.max_spread_points_for("XAUUSD-ECNc"), 50)

        # FX pairs
        self.assertEqual(config.default_sl_points_for("EURUSD-ECNc"), 200)
        self.assertEqual(config.default_tp_points_for("EURUSD-ECNc"), 400)
        self.assertEqual(config.default_sl_points_for("USDJPY-ECNc"), 250)
        self.assertEqual(config.default_tp_points_for("USDJPY-ECNc"), 500)

        # BTC helpers
        self.assertEqual(config.lot_size_for("BTCUSD.c"), 0.01)
        self.assertEqual(config.default_sl_points_for("BTCUSD.c"), config.DEFAULT_SL_POINTS_BTC)
        self.assertEqual(config.default_tp_points_for("BTCUSD.c"), config.DEFAULT_TP_POINTS_BTC)
        self.assertEqual(config.max_spread_points_for("BTCUSD.c"), config.MAX_SPREAD_POINTS_BTC)
        self.assertTrue(config.is_crypto("BTCUSD.c"))
        self.assertFalse(config.is_crypto("XAUUSD-ECNc"))

        # Risk percent
        self.assertEqual(config.risk_percent_for("XAUUSD-ECNc"), config.RISK_PERCENT_XAU)
        self.assertEqual(config.risk_percent_for("GBPUSD-ECNc"), config.RISK_PERCENT_FX)
        self.assertEqual(config.risk_percent_for("BTCUSD.c"), config.RISK_PERCENT_BTC)

    def test_session_aware_helpers(self):
        # Asian session pairs should include JPY, AUD, NZD
        self.assertTrue(config.is_asian_session_pair("AUDNZD-ECNc"))
        self.assertTrue(config.is_asian_session_pair("USDJPY-ECNc"))
        self.assertTrue(config.is_asian_session_pair("NZDCAD-ECNc"))
        self.assertTrue(config.is_asian_session_pair("AUDCAD-ECNc"))
        self.assertTrue(config.is_asian_session_pair("GBPJPY-ECNc"))
        
        # Pure European / American pairs should NOT be Asian session pairs
        self.assertFalse(config.is_asian_session_pair("EURUSD-ECNc"))
        self.assertFalse(config.is_asian_session_pair("GBPUSD-ECNc"))
        self.assertFalse(config.is_asian_session_pair("EURGBP-ECNc"))
        self.assertFalse(config.is_asian_session_pair("EURCHF-ECNc"))
        self.assertFalse(config.is_asian_session_pair("GBPCHF-ECNc"))
        self.assertFalse(config.is_asian_session_pair("GBPCAD-ECNc"))
        self.assertFalse(config.is_asian_session_pair("USDCAD-ECNc"))
        self.assertFalse(config.is_asian_session_pair("USDCHF-ECNc"))


if __name__ == "__main__":
    unittest.main()
