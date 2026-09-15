import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

import config
from src.analytics.market_scanner_m5 import MarketScannerM5, calculate_m5_sl_tp


class TestMarketScannerM5(unittest.TestCase):

    def test_calculate_m5_sl_tp_buy(self):
        # EURUSD BUY at 1.10000 — Sniper entry at Discount zone:
        # F1 floor at 1.09960 (40 pts below entry — tight structural SL)
        # C1 ceiling at 1.10200 (200 pts above entry — generous TP target)
        # Expected: SL ~60 pts (40 structural + 20 buffer), Net R:R >= 2.0
        entry  = 1.10000
        f1     = 1.09960  # 40 pts below (tight floor)
        c1     = 1.10200  # 200 pts above (ceiling target)
        spread = 10
        pt     = 0.00001
        buf    = 10  # M5_SL_ZCE_BUFFER_PTS default

        res = calculate_m5_sl_tp(
            symbol="EURUSD-ECNc",
            entry_price=entry,
            direction=1,
            atr_m5=0.00050,
            c1=c1,
            f1=f1,
            spread_pts=spread,
            pt=pt
        )
        # SL must be below entry and below F1
        self.assertLess(res["sl"], entry, "SL must be below entry price")
        self.assertLess(res["sl"], f1, "SL must be below F1 structural floor")

        # TP must be above entry
        self.assertGreater(res["tp"], entry, "TP must be above entry price")

        # SL distance: structural (40) + buffer (spread+buf=20 pts) = min 55 pts
        structural_dist_pts = int(round((entry - f1) / pt))  # 40
        expected_sl_min_pts = structural_dist_pts + spread + buf - 5  # small tolerance = 45
        self.assertGreaterEqual(res["sl_pts"], expected_sl_min_pts,
            f"SL should be >= structural dist ({structural_dist_pts}) + buffer")

        # Net R:R must be >= 2.0 (9-engine sniper spec)
        self.assertGreaterEqual(res["risk_reward"], 2.0,
            f"Net R:R {res['risk_reward']:.2f} must be >= 2.0")

        # Function must return structural_anchor key
        self.assertIn("structural_anchor", res)
        self.assertIsNotNone(res["structural_anchor"])

    def test_calculate_m5_sl_tp_sell(self):
        # GBPUSD SELL at 1.35000 — Sniper entry at Premium zone:
        # C1 ceiling at 1.35040 (40 pts above entry — tight structural SL)
        # F1 floor at 1.34800 (200 pts below entry — generous TP target)
        # Expected: SL ~62 pts (40 structural + 22 buffer), Net R:R >= 2.0
        entry  = 1.35000
        c1     = 1.35040  # 40 pts above (tight ceiling)
        f1     = 1.34800  # 200 pts below (floor target)
        spread = 12
        pt     = 0.00001
        buf    = 10  # M5_SL_ZCE_BUFFER_PTS default

        res = calculate_m5_sl_tp(
            symbol="GBPUSD-ECNc",
            entry_price=entry,
            direction=-1,
            atr_m5=0.00060,
            c1=c1,
            f1=f1,
            spread_pts=spread,
            pt=pt
        )
        # SL must be above entry and above C1
        self.assertGreater(res["sl"], entry, "SL must be above entry price")
        self.assertGreater(res["sl"], c1, "SL must be above C1 structural ceiling")

        # TP must be below entry
        self.assertLess(res["tp"], entry, "TP must be below entry price")

        # SL distance: structural (40) + buffer (spread+buf=22 pts) = min 57 pts
        structural_dist_pts = int(round((c1 - entry) / pt))  # 40
        expected_sl_min_pts = structural_dist_pts + spread + buf - 5  # small tolerance = 47
        self.assertGreaterEqual(res["sl_pts"], expected_sl_min_pts,
            f"SL should be >= structural dist ({structural_dist_pts}) + buffer")

        # Net R:R must be >= 2.0 (9-engine sniper spec)
        self.assertGreaterEqual(res["risk_reward"], 2.0,
            f"Net R:R {res['risk_reward']:.2f} must be >= 2.0")

        # Function must return structural_anchor key
        self.assertIn("structural_anchor", res)
        self.assertIsNotNone(res["structural_anchor"])

    def test_calculate_m5_sl_tp_no_structure(self):
        # When no F1/C1 provided, falls back to ATR-based SL; Net R:R may be below 2.0
        res = calculate_m5_sl_tp(
            symbol="EURUSD-ECNc",
            entry_price=1.10000,
            direction=1,
            atr_m5=0.00050,
            c1=None,
            f1=None,
            spread_pts=10,
            pt=0.00001
        )
        self.assertLess(res["sl"], 1.10000, "SL must be below entry even on ATR fallback")
        self.assertGreater(res["tp"], 1.10000, "TP must be above entry")
        self.assertGreater(res["sl_pts"], 0)
        self.assertIn("structural_anchor", res)
        self.assertIsNone(res["structural_anchor"], "Anchor should be None when no structure")

    def test_scanner_m5_initialization(self):
        scanner = MarketScannerM5(symbols=["EURUSD-ECNc", "GBPUSD-ECNc"])
        self.assertEqual(len(scanner.symbols), 2)
        self.assertIn("M5",  scanner._micro_zce_params["grid"])
        self.assertIn("M15", scanner._micro_zce_params["grid"])
        self.assertIn("H1",  scanner._micro_zce_params["grid"])


if __name__ == "__main__":
    unittest.main()
