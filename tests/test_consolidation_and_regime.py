import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd

from src.indicators.lux_smc import LuxSMCAnalyzer, SMCSignal
from src.analytics.macro_strategic_engine import derive_semantic_state, PrimitiveState, Location, StructuralEvent, Trajectory
from src.analytics.market_scanner import evaluate_universal_sweep_gates


class TestConsolidationAndRegime(unittest.TestCase):

    def test_lux_smc_ranging_flag_detection(self):
        np.random.seed(42)
        n = 60
        highs = [1.2000 - (i * 0.0005) + np.random.uniform(0, 0.0002) for i in range(n)]
        lows = [1.1800 + (i * 0.0005) - np.random.uniform(0, 0.0002) for i in range(n)]
        closes = [(h + l) / 2.0 for h, l in zip(highs, lows)]
        opens = [c - 0.0001 for c in closes]

        df = pd.DataFrame({
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": [100] * n
        })

        analyzer = LuxSMCAnalyzer(swing_length=5)
        sig = analyzer.analyze(df, point_size=0.0001)

        self.assertTrue(sig.is_ranging_box or sig.is_triangle_compression)
        self.assertTrue(0.20 <= sig.dealing_range_pos <= 0.80)

    def test_lux_smc_trending_expansion(self):
        n = 60
        opens = [1.1000 + (i * 0.0020) for i in range(n)]
        closes = [o + 0.0015 for o in opens]
        highs = [c + 0.0005 for c in closes]
        lows = [o - 0.0005 for o in opens]

        df = pd.DataFrame({
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "tick_volume": [100] * n
        })

        analyzer = LuxSMCAnalyzer(swing_length=5)
        sig = analyzer.analyze(df, point_size=0.0001)

        self.assertGreaterEqual(sig.dealing_range_pos, 0.80)

    def test_mid_chamber_mse_derivation(self):
        primitive = PrimitiveState(
            location=Location.MID,
            event=StructuralEvent.COMPRESSION,
            trajectory=Trajectory.ROTATION
        )
        semantic_state = derive_semantic_state(primitive)
        self.assertEqual(semantic_state, "NEUTRAL_CHAMBER")

    def test_universal_sweep_strict_active_zone(self):
        allowed, reason = evaluate_universal_sweep_gates(
            signal_type='BUY',
            dealing_range_pos=0.40,
            dist_to_htf_floor=100.0,
            dist_to_htf_ceiling=100.0,
            atr_val=10.0,
            recent_ceiling_touch=False,
            recent_floor_touch=False,
            close_below_ema20=False,
            close_above_ema20=True,
            macro_trend='NEUTRAL'
        )
        self.assertFalse(allowed)
        self.assertIn("LOCKED BY GATE A", reason)

        allowed_buy, _ = evaluate_universal_sweep_gates(
            signal_type='BUY',
            dealing_range_pos=0.15,
            dist_to_htf_floor=2.0,
            dist_to_htf_ceiling=100.0,
            atr_val=10.0,
            recent_ceiling_touch=False,
            recent_floor_touch=False,
            close_below_ema20=False,
            close_above_ema20=True,
            macro_trend='NEUTRAL'
        )
        self.assertTrue(allowed_buy)

        allowed_sell_mid, reason_sell = evaluate_universal_sweep_gates(
            signal_type='SELL',
            dealing_range_pos=0.447,
            dist_to_htf_floor=100.0,
            dist_to_htf_ceiling=100.0,
            atr_val=10.0,
            recent_ceiling_touch=False,
            recent_floor_touch=False,
            close_below_ema20=True,
            close_above_ema20=False,
            macro_trend='NEUTRAL'
        )
        self.assertFalse(allowed_sell_mid)

        allowed_sell_high, _ = evaluate_universal_sweep_gates(
            signal_type='SELL',
            dealing_range_pos=0.85,
            dist_to_htf_floor=100.0,
            dist_to_htf_ceiling=2.0,
            atr_val=10.0,
            recent_ceiling_touch=False,
            recent_floor_touch=False,
            close_below_ema20=True,
            close_above_ema20=False,
            macro_trend='NEUTRAL'
        )
        self.assertTrue(allowed_sell_high)


if __name__ == '__main__':
    unittest.main()
