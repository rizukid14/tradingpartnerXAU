import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import config
from src.analytics.market_scanner import MarketScanner, CandidateSetup
from src.core.consensus import _apply_sltp_rules


class TestFreshBreakoutAndNetRR(unittest.TestCase):

    def setUp(self):
        self.scanner = MarketScanner(symbols=["EURCHF-ECNc", "GBPAUD-ECNc", "CHFJPY-ECNc", "AUDCHF-ECNc"])

    def test_segmented_sl_floors(self):
        """Test segmented safety floors across low-beta, high-beta, and JPY pairs."""
        # 1. Quiet FX (EURCHF): ATR 70 pts -> floor should clamp to 120 pts
        fl_eurchf = config.get_sl_floor_points("EURCHF-ECNc", spread_pts=15, atr_points=70)
        self.assertEqual(fl_eurchf, 120)

        # 2. High-Beta FX (GBPAUD): ATR 150 pts -> 0.5x ATR is 75, floor clamps to 180 pts
        fl_gbpaud = config.get_sl_floor_points("GBPAUD-ECNc", spread_pts=20, atr_points=150)
        self.assertEqual(fl_gbpaud, 180)

        # 3. High-Beta FX (GBPAUD) with large ATR: ATR 400 pts -> 0.5x ATR is 200, floor uses 200 pts
        fl_gbpaud_high = config.get_sl_floor_points("GBPAUD-ECNc", spread_pts=20, atr_points=400)
        self.assertEqual(fl_gbpaud_high, 200)

        # 4. JPY Cross (CHFJPY): ATR 150 pts -> floor clamps to 200 pts
        fl_chfjpy = config.get_sl_floor_points("CHFJPY-ECNc", spread_pts=15, atr_points=150)
        self.assertEqual(fl_chfjpy, 200)

        # 5. NZD Cross (EURNZD): High-Beta (180) + NZD Padding (20) = 200 pts
        fl_eurnzd = config.get_sl_floor_points("EURNZD-ECNc", spread_pts=20, atr_points=150)
        self.assertEqual(fl_eurnzd, 200)

    def test_friction_aware_net_rr_in_apply_sltp_rules(self):
        """Test that minimum TP covers target R + spread + round-turn commission."""
        with patch.object(config, "ZCE_ENABLED", False), patch.object(config, "ZCE_MODE", "shadow"):
            sl, tp, ok, reason = _apply_sltp_rules(
                sl_points=50,  # Below 120 floor
                tp_points=60,  # Below Net R:R
                symbol="EURCHF-ECNc",
            )
            self.assertTrue(ok)
            # SL should be lifted to at least 120 pts
            self.assertGreaterEqual(sl, 120)
            # TP must be at least int(sl * 1.25) + 5 pts comm
            self.assertGreaterEqual(tp, int(sl * 1.25) + 5)

    def test_retest_debounce_lock_and_unlock(self):
        """Test that record_retest_rejection locks level and unlocks on displacement > 0.50x ATR."""
        sym = "AUDCHF-ECNc"
        target_level = 0.58150
        atr_val = 0.00078 # 78 pts

        # Record rejection
        self.scanner.record_retest_rejection(sym, level=target_level, current_atr=atr_val)

        # 1. Price hovering close to level (0.58160, dist = 10 pts = 0.13x ATR) -> LOCKED
        is_locked, reason = self.scanner.is_retest_locked(sym, current_mid=0.58160, current_atr=atr_val)
        self.assertTrue(is_locked)
        self.assertIn("previously rejected", reason)

        # 2. Price displaces away (> 0.50x ATR = 39 pts, mid = 0.58200, dist = 50 pts) -> UNLOCKED
        is_locked, reason = self.scanner.is_retest_locked(sym, current_mid=0.58200, current_atr=atr_val)
        self.assertFalse(is_locked)

        # 3. Subsequent check remains unlocked (entry deleted)
        is_locked, _ = self.scanner.is_retest_locked(sym, current_mid=0.58160, current_atr=atr_val)
        self.assertFalse(is_locked)


if __name__ == "__main__":
    unittest.main()
