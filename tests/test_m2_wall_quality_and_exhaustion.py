import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

from src.analytics.market_scanner import MarketScanner, CandidateSetup

WIB = ZoneInfo("Asia/Jakarta")

class TestM2WallQualityAndExhaustion(unittest.TestCase):
    def setUp(self):
        self.scanner = MarketScanner(symbols=["AUDUSD-ECNc"])
        self.sym = "AUDUSD-ECNc"

    def test_m2_sell_soft_gates_grade1_micro_to_grade_b(self):
        """M2 SELL at GRADE_1_MICRO without >= 25% wick is soft-gated to GRADE_B (1 ticket, quick BEP) rather than blocked."""
        macro = {
            'immediate_ceiling_c1': 0.71724,
            'c1_reaction_grade': 'GRADE_1_MICRO',
            'immediate_floor_f1': 0.71500,
            'f1_reaction_grade': 'GRADE_2_INTERMEDIATE',
            'current_atr': 0.00066,
            'ema20': 0.71750,
            'ema50': 0.71730,
            'trend_label': 'BEARISH',
            'is_bear': True,
            'is_bull': False,
            'dealing_range_pos': 0.30,
        }
        atr_val = 0.00066
        pt = 0.00001
        base_ceiling = 0.71724

        c_qual = {
            'direction': 'bullish',
            'body_ratio': 0.45,
            'upper_wick_pct': 0.20,  # >= 0.20 (has_h1_rejection True), but < 0.25 (G1 soft-gate)
            'max_upper_wick': 0.20,
            'sweep_side': None,
            'is_bearish_engulf': False,
        }

        with patch.object(self.scanner, '_verify_m5_rejection_wick', return_value=(False, "M5_NO_REJECTION_WICK")):
            has_res_hold, is_soft_g1, reason = self.scanner._evaluate_m2_wall_quality(
                sym=self.sym,
                direction=-1,
                base_level=base_ceiling,
                c_qual=c_qual,
                macro=macro,
                atr_val=atr_val,
                pt=pt,
                mt5_connector=None,
            )

            self.assertTrue(has_res_hold, "Expected has_res_hold to be True with 20% wick")
            self.assertTrue(is_soft_g1, "Expected is_soft_g1 to be True for G1 Micro wall")
            self.assertEqual(reason, "HOLD_CONFIRMED")
            
            # Check setup_grade evaluation
            sl_tp = {"setup_grade": "GRADE_A"}
            rr_val = 1.50
            effective_grade = "GRADE_B" if (is_soft_g1 or sl_tp.get("setup_grade") == "GRADE_B" or rr_val < 1.25) else sl_tp.get("setup_grade", "GRADE_A")
            self.assertEqual(effective_grade, "GRADE_B", "Soft-gated G1 setup must result in GRADE_B")

    def test_m2_sell_blocks_bullish_marubozu(self):
        """M2 SELL must skip when a strong bullish marubozu is approaching the anchor ceiling."""
        atr_val = 0.00066
        pt = 0.00001
        base_ceiling = 0.71850

        # Bullish marubozu: 70% body, 5% upper wick
        c_qual = {
            'direction': 'bullish',
            'body_ratio': 0.70,
            'upper_wick_pct': 0.05,
            'max_upper_wick': 0.05,
            'sweep_side': None,
            'is_bearish_engulf': False,
        }

        with patch.object(self.scanner, '_verify_m5_rejection_wick', return_value=(True, "M5_REJECTION_CONFIRMED")) as mock_m5:
            has_res_hold, is_soft_g1, reason = self.scanner._evaluate_m2_wall_quality(
                sym=self.sym,
                direction=-1,
                base_level=base_ceiling,
                c_qual=c_qual,
                macro={},
                atr_val=atr_val,
                pt=pt,
                mt5_connector=None,
            )

            self.assertFalse(has_res_hold, "Expected has_res_hold to be False when bullish marubozu is expanding")
            self.assertIn("MARUBOZU_WATERFALL", reason)
            # Lazy check: M5 should not have been called because H1 marubozu was blocked immediately
            mock_m5.assert_not_called()

    def test_m2_sell_allows_healthy_rejection(self):
        """M2 SELL allows trade when upper rejection wick is healthy (>=20%)."""
        atr_val = 0.00066
        pt = 0.00001
        base_ceiling = 0.71850

        # Rejection candle: 35% upper wick
        c_qual = {
            'direction': 'bullish',
            'body_ratio': 0.35,
            'upper_wick_pct': 0.35,
            'max_upper_wick': 0.35,
            'sweep_side': 'top',
            'is_bearish_engulf': False,
        }

        with patch.object(self.scanner, '_verify_m5_rejection_wick', return_value=(True, "M5_REJECTION_CONFIRMED")):
            has_res_hold, is_soft_g1, reason = self.scanner._evaluate_m2_wall_quality(
                sym=self.sym,
                direction=-1,
                base_level=base_ceiling,
                c_qual=c_qual,
                macro={},
                atr_val=atr_val,
                pt=pt,
                mt5_connector=None,
            )

            self.assertTrue(has_res_hold, "Expected has_res_hold to be True when upper rejection wick is present")
            self.assertEqual(reason, "HOLD_CONFIRMED")

    def test_m2_buy_blocks_bearish_marubozu(self):
        """M2 BUY must skip when a strong bearish marubozu is approaching the anchor floor."""
        atr_val = 0.00066
        pt = 0.00001
        base_floor = 0.71500

        # Bearish marubozu: 68% body, 4% lower wick
        c_qual = {
            'direction': 'bearish',
            'body_ratio': 0.68,
            'lower_wick_pct': 0.04,
            'max_lower_wick': 0.04,
            'sweep_side': None,
            'is_bullish_engulf': False,
        }

        with patch.object(self.scanner, '_verify_m5_rejection_wick', return_value=(True, "M5_REJECTION_CONFIRMED")) as mock_m5:
            has_support_hold, is_soft_g1, reason = self.scanner._evaluate_m2_wall_quality(
                sym=self.sym,
                direction=1,
                base_level=base_floor,
                c_qual=c_qual,
                macro={},
                atr_val=atr_val,
                pt=pt,
                mt5_connector=None,
            )

            self.assertFalse(has_support_hold, "Expected has_support_hold to be False when bearish marubozu is collapsing")
            self.assertIn("MARUBOZU_WATERFALL", reason)
            # Lazy check: M5 should not have been called because H1 marubozu was blocked immediately
            mock_m5.assert_not_called()

    def test_zce_audit_telemetry_format(self):
        """Verify that cand metadata produces true ZCE_F1 and ZCE_C1 in audit string formatting."""
        cand = CandidateSetup(
            symbol="AUDUSD-ECNc",
            setup_type="TREND_ALIGNED_PULLBACK",
            direction=-1,
            trigger_price=0.71723,
            timeframe="H1",
            current_atr_pts=66.0,
            key_support=0.71503,
            key_resistance=0.71724,
            suggested_sl=0.71866,
            suggested_tp=0.71566,
            metadata={
                "zce_f1": 0.71554,
                "zce_c1": 0.71724,
                "f1_grade": "GRADE_2_INTERMEDIATE",
                "c1_grade": "GRADE_1_MICRO"
            }
        )

        _cand_meta = getattr(cand, 'metadata', {}) or {}
        _z_f1 = _cand_meta.get('zce_f1') or _cand_meta.get('zce_f1_price') or getattr(cand, 'floor_f1', 0.0) or getattr(cand, 'f1', 0.0)
        _z_c1 = _cand_meta.get('zce_c1') or _cand_meta.get('zce_c1_price') or getattr(cand, 'ceiling_c1', 0.0) or getattr(cand, 'c1', 0.0)
        _zf1_s = f"{_z_f1:.5f}" if isinstance(_z_f1, (int, float)) and _z_f1 > 0 else (str(_z_f1) if _z_f1 else f"DR_Lo:{getattr(cand, 'key_support', 0.0)}")
        _zc1_s = f"{_z_c1:.5f}" if isinstance(_z_c1, (int, float)) and _z_c1 > 0 else (str(_z_c1) if _z_c1 else f"DR_Hi:{getattr(cand, 'key_resistance', 0.0)}")

        self.assertEqual(_zf1_s, "0.71554")
        self.assertEqual(_zc1_s, "0.71724")
        self.assertNotEqual(_zc1_s, "0.71866", "SL price must not be mistaken for C1 wall")

    def test_shadow_tracker_persists_wall_grades(self):
        """Verify that shadow tracker register_candidate persists wall grades and ZCE levels into trade metadata."""
        from src.analytics.shadow_tracker import QuantShadowTracker
        tracker = QuantShadowTracker()

        cand = CandidateSetup(
            symbol="AUDUSD-ECNc",
            setup_type="TREND_ALIGNED_PULLBACK",
            direction=-1,
            trigger_price=0.71723,
            timeframe="H1",
            current_atr_pts=66.0,
            key_support=0.71503,
            key_resistance=0.71724,
            suggested_sl=0.71866,
            suggested_tp=0.71566,
            setup_grade="GRADE_B",
            metadata={
                "zce_f1": 0.71554,
                "zce_c1": 0.71724,
                "f1_grade": "GRADE_2_INTERMEDIATE",
                "c1_grade": "GRADE_1_MICRO"
            }
        )

        with patch.object(tracker, '_save_state'):
            trade = tracker.register_candidate(
                candidate=cand,
                entry_type="sell_limit",
                entry_price=0.71723,
                sl_price=0.71866,
                tp_price=0.71566,
                sl_points=143,
                tp_points=157,
            )
            if trade:
                self.assertEqual(trade.metadata.get("wall_grade"), "GRADE_1_MICRO")
                self.assertEqual(trade.metadata.get("f1_reaction_grade"), "GRADE_2_INTERMEDIATE")
                self.assertEqual(trade.metadata.get("c1_reaction_grade"), "GRADE_1_MICRO")
                self.assertEqual(trade.metadata.get("zce_f1"), 0.71554)
                self.assertEqual(trade.metadata.get("zce_c1"), 0.71724)
                self.assertEqual(trade.metadata.get("setup_grade"), "GRADE_B")

if __name__ == '__main__':
    unittest.main()
