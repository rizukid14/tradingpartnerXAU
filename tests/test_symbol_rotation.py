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
        # In scanner mode, rotation pool should contain all 22 symbols on weekdays
        wednesday = datetime(2026, 8, 12, 10, 0, tzinfo=WIB)
        pool = config.get_rotation_pool(wednesday)
        if config.SCANNER_MODE:
            self.assertEqual(len(pool), 22)
            self.assertIn("GBPUSD-ECNc", pool)
            self.assertIn("XAUUSD-ECNc", pool)
            self.assertIn("USDJPY-ECNc", pool)

    def test_weekend_switch(self):
        # Weekend should return BTC if enabled
        saturday = datetime(2026, 8, 8, 12, 0, tzinfo=WIB)
        pool = config.get_rotation_pool(saturday)
        self.assertEqual(pool, [config.WEEKEND_SYMBOL])

    def test_per_symbol_helpers(self):
        # XAU helpers
        self.assertEqual(config.lot_size_for("XAUUSD-ECNc"), 0.01)
        self.assertEqual(config.default_sl_points_for("XAUUSD-ECNc"), config.DEFAULT_SL_POINTS_XAU)
        self.assertEqual(config.default_tp_points_for("XAUUSD-ECNc"), config.DEFAULT_TP_POINTS_XAU)
        self.assertEqual(config.max_spread_points_for("XAUUSD-ECNc"), 50)

        # FX pairs
        for sym in ["GBPUSD-ECNc", "USDJPY-ECNc", "GBPJPY-ECNc", "EURUSD-ECNc"]:
            self.assertEqual(config.default_sl_points_for(sym), 100)
            self.assertEqual(config.default_tp_points_for(sym), 200)

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


if __name__ == "__main__":
    unittest.main()
