import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

import config
from src.analytics.market_scanner_m5 import MarketScannerM5, calculate_m5_sl_tp


class TestMarketScannerM5(unittest.TestCase):

    def test_calculate_m5_sl_tp_buy(self):
        # EURUSD BUY at 1.10000, M5 ATR = 0.00050 (5 pips), C1 at 1.10200 (20 pips)
        res = calculate_m5_sl_tp(
            symbol="EURUSD-ECNc",
            entry_price=1.10000,
            direction=1,
            atr_m5=0.00050,
            c1=1.10200,
            f1=1.09800,
            spread_pts=10,
            pt=0.00001
        )
        self.assertLess(res["sl"], 1.10000)
        self.assertGreater(res["tp"], 1.10000)
        self.assertGreaterEqual(res["sl_pts"], 75)
        self.assertLessEqual(res["sl_pts"], 120)
        self.assertGreaterEqual(res["risk_reward"], 1.5)

    def test_calculate_m5_sl_tp_sell(self):
        # GBPUSD SELL at 1.35000, M5 ATR = 0.00060 (6 pips), F1 at 1.34800 (20 pips)
        res = calculate_m5_sl_tp(
            symbol="GBPUSD-ECNc",
            entry_price=1.35000,
            direction=-1,
            atr_m5=0.00060,
            c1=1.35200,
            f1=1.34800,
            spread_pts=12,
            pt=0.00001
        )
        self.assertGreater(res["sl"], 1.35000)
        self.assertLess(res["tp"], 1.35000)
        self.assertGreaterEqual(res["sl_pts"], 80)
        self.assertGreaterEqual(res["risk_reward"], 1.5)

    def test_scanner_m5_initialization(self):
        scanner = MarketScannerM5(symbols=["EURUSD-ECNc", "GBPUSD-ECNc"])
        self.assertEqual(len(scanner.symbols), 2)
        self.assertIn("M5", scanner._micro_zce_params["grid"])
        self.assertIn("M15", scanner._micro_zce_params["grid"])
        self.assertIn("H1", scanner._micro_zce_params["grid"])


if __name__ == "__main__":
    unittest.main()
