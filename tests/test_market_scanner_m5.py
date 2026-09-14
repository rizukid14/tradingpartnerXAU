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
        self.assertGreaterEqual(res["sl_pts"], 40)
        self.assertLessEqual(res["sl_pts"], 100)
        self.assertGreaterEqual(res["risk_reward"], 1.25)

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
        self.assertGreaterEqual(res["sl_pts"], 40)
        self.assertLessEqual(res["sl_pts"], 100)
        self.assertGreaterEqual(res["risk_reward"], 1.25)

    def test_scanner_m5_initialization(self):
        scanner = MarketScannerM5(symbols=["EURUSD-ECNc", "GBPUSD-ECNc"])
        self.assertEqual(len(scanner.symbols), 2)
        self.assertIn("M5", scanner._micro_zce_params["grid"])
        self.assertIn("M15", scanner._micro_zce_params["grid"])
        self.assertIn("H1", scanner._micro_zce_params["grid"])

    def test_m5_pending_expiration_and_bep(self):
        # M5 Pending order expiration must be 20 minutes
        with patch.object(config, "TIMEFRAME_STR", "M5"):
            exp_mins = config.get_pending_order_expiry_minutes()
            self.assertEqual(exp_mins, 20)

        # BEP trigger ratio must be 0.80 for M5
        self.assertEqual(getattr(config, "BREAK_EVEN_TRIGGER_TP_PCT", 0.0), 0.80)
        self.assertFalse(getattr(config, "TRAILING_STOP_ENABLED", True))
        self.assertFalse(getattr(config, "PARTIAL_CLOSE_ENABLED", True))

    def test_m5_cooldowns(self):
        self.assertEqual(getattr(config, "POST_LOSS_COOLDOWN_SECONDS", 0), 600)
        self.assertEqual(getattr(config, "SCANNER_MECHANISM_REJECTION_COOLDOWN_SECONDS", 0), 600)

    def test_xau_btc_quarantined_to_paper_trade(self):
        # XAUUSD and BTCUSD must strictly be paper trade only (quarantined from MT5 live execution)
        self.assertTrue(config.is_paper_only("XAUUSD-ECNc"))
        self.assertTrue(config.is_paper_only("BTCUSD.c"))
        self.assertFalse(config.is_paper_only("EURUSD-ECNc"))
        self.assertFalse(config.is_paper_only("GBPUSD-ECNc"))
    def test_m5_sl_less_than_tp_and_thin_jpy(self):
        # GBPJPY M5 scalping must have thin SL (not 250 pts H1 floor) and SL < TP (R:R >= 1.25)
        pt = 0.001
        atr_m5 = 0.077
        res = calculate_m5_sl_tp(
            symbol="GBPJPY-ECNc",
            entry_price=208.551,
            direction=1,
            atr_m5=atr_m5,
            spread_pts=11,
            pt=pt
        )
        self.assertLess(res["sl_pts"], res["tp_pts"])
        self.assertGreaterEqual(res["risk_reward"], 1.25)
        # Verify SL is thin (around 90-100 pts), NOT clamped to 250 pts H1 floor
        self.assertLess(res["sl_pts"], 150)


if __name__ == "__main__":
    unittest.main()
