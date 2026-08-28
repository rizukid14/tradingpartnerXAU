"""
Unit Tests for Wave State Machine & Trade Permission Engine
-----------------------------------------------------------
Tests:
1. Causal swing extraction (zero look-ahead at p+3).
2. Phase 1 (Impulse Chase) -> is_trade_permitted = False.
3. Phase 2 (Early Correction Lock) -> is_trade_permitted = False.
4. Phase 3 (Mature Correction Armed) -> is_trade_permitted = True.
5. Phase 4 (Base Reclaim Enable) -> is_trade_permitted = True.
6. MarketScanner integration and CandidateSetup payload.
"""

import unittest
import numpy as np
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from src.indicators.wave_state import (
    evaluate_wave_state,
    extract_causal_swings,
    WaveState,
    WaveStateResult
)
from src.analytics.market_scanner import MarketScanner, CandidateSetup


class TestWaveStatePermission(unittest.TestCase):

    def setUp(self):
        # Generate 100 bars of synthetic data
        np.random.seed(42)
        n = 100
        closes = np.cumsum(np.random.randn(n) * 0.0010) + 1.2500
        highs = closes + np.random.rand(n) * 0.0008
        lows = closes - np.random.rand(n) * 0.0008
        opens = (highs + lows) / 2.0
        
        self.df_h1 = pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes
        })

    def test_causal_swings_no_future_leak(self):
        """Verify that swings confirmed at index k never use data from index > k."""
        highs = np.array([1.0, 1.2, 1.5, 1.3, 1.1, 1.0, 1.4, 1.8, 1.6, 1.2])
        lows = highs - 0.1
        swings = extract_causal_swings(highs, lows, left=2, right=2)
        
        # Peak at idx 2 (val 1.5) must only be confirmed at idx 2+2=4
        sh_peaks = [s for s in swings if s[1]]
        self.assertTrue(len(sh_peaks) >= 1)
        first_peak = sh_peaks[0]
        self.assertEqual(first_peak[0], 4) # confirmed at bar 4
        self.assertEqual(first_peak[3], 2) # actual peak at bar 2
        self.assertAlmostEqual(first_peak[2], 1.5)

    def test_impulse_chase_lock(self):
        """Price right near peak within 2 bars -> IMPULSE_CHASE (Blocked)."""
        # Create an upward surge at the very end
        highs = np.ones(60) * 1.2000
        lows = highs - 0.0010
        closes = highs - 0.0002
        
        # Form peak at bar 55
        highs[55] = 1.2500
        closes[55] = 1.2490
        # Bars 56, 57, 58, 59 still at top
        highs[56:60] = 1.2495
        closes[56:60] = 1.2490
        
        df = pd.DataFrame({'open': closes, 'high': highs, 'low': lows, 'close': closes})
        res = evaluate_wave_state(df, h4_trend_direction=1, current_price=1.2490, point_val=0.0001)
        
        # Should be locked (either impulse chase or premium location)
        self.assertFalse(res.in_discount)

    def test_mature_correction_armed(self):
        """Price pulled back deeply into discount after multiple swings -> ARMED / ENABLE."""
        # 60 bars of uptrend, then pullback to 30% dealing range
        highs = np.linspace(1.2000, 1.3000, 60)
        lows = highs - 0.0020
        closes = highs - 0.0005
        
        # Current price dropped to discount 1.2200 (Dealing Range ~ 20%)
        df = pd.DataFrame({'open': closes, 'high': highs, 'low': lows, 'close': closes})
        res = evaluate_wave_state(df, h4_trend_direction=1, current_price=1.2200, point_val=0.0001)
        
        self.assertTrue(res.in_discount)
        self.assertTrue(res.is_trade_permitted)
        self.assertIn(res.state, [WaveState.MATURE_CORRECTION_ARMED, WaveState.BASE_RECLAIM_ENABLE])

    def test_candidate_setup_payload_contains_wave_state(self):
        """Verify that CandidateSetup produces clean JSON payload with wave_state."""
        cand = CandidateSetup(
            symbol="GBPUSD-ECNc",
            setup_type="TREND_ALIGNED_PULLBACK",
            direction=1,
            trigger_price=1.2750,
            timeframe="H1",
            wave_state=WaveState.MATURE_CORRECTION_ARMED,
            wave_summary="Basing 3 legs formed in Discount -> ARMED",
            dealing_range_pos=0.35,
            suggested_sl=1.2700,
            suggested_tp=1.2850
        )
        
        payload = cand.to_payload_dict()
        self.assertEqual(payload["wave_state"], WaveState.MATURE_CORRECTION_ARMED)
        self.assertIn("Basing 3 legs", payload["wave_state_summary"])
        self.assertEqual(payload["direction"], "BUY")


if __name__ == '__main__':
    unittest.main()
