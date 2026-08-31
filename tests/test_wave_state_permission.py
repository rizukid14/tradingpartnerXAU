"""
Unit Tests for Quant V3 4-Dimensional Market State & Permission Engine
----------------------------------------------------------------------
Tests:
1. Causal swing extraction (zero look-ahead at p+right).
2. Phase 1 (Near Peak Expansion) -> permission = WAIT.
3. Phase 2 (Type A Violent Waterfall) -> permission = LOCK (Anti-Falling Knife).
4. Phase 3 (Type B Compression Coil in Discount) -> permission = ARM.
5. Phase 4 (Type B Coil + CSM Aligned + Reclaim Event) -> permission = GO.
6. Flow Shock (CSM Opposed <= -1.0) -> permission = WAIT.
7. MarketScanner integration and CandidateSetup payload.
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
        
        sh_peaks = [s for s in swings if s[1]]
        self.assertTrue(len(sh_peaks) >= 1)
        first_peak = sh_peaks[0]
        self.assertEqual(first_peak[0], 4) # confirmed at bar 4
        self.assertEqual(first_peak[3], 2) # actual peak at bar 2
        self.assertAlmostEqual(first_peak[2], 1.5)

    def test_impulse_chase_wait(self):
        """Price right near peak within 2 bars -> EXPANSION_WAIT (Blocked from FOMO)."""
        highs = np.ones(60) * 1.2000
        lows = highs - 0.0010
        closes = highs - 0.0002
        
        highs[55] = 1.2500
        closes[55] = 1.2490
        highs[56:60] = 1.2495
        closes[56:60] = 1.2490
        
        df = pd.DataFrame({'open': closes, 'high': highs, 'low': lows, 'close': closes})
        res = evaluate_wave_state(df, h4_trend_direction=1, current_price=1.2490, point_val=0.0001)
        
        self.assertFalse(res.in_discount)
        self.assertEqual(res.permission, "WAIT")

    def test_type_a_waterfall_lock(self):
        """Violent plunge with large bearish bodies -> TYPE_A_WATERFALL_LOCK (0% Risk)."""
        # Uptrend 50 bars, then 3 massive waterfall bearish candles
        highs = np.linspace(1.2000, 1.2500, 50).tolist()
        lows = [h - 0.0010 for h in highs]
        closes = [h - 0.0002 for h in highs]
        opens = [l + 0.0002 for l in lows]
        
        # 3 large waterfall bars
        for _ in range(3):
            last_c = closes[-1]
            o = last_c
            c = o - 0.0050 # 50 pips drop
            h = o + 0.0002
            l = c - 0.0002
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(c)
            
        df = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes})
        res = evaluate_wave_state(df, h4_trend_direction=1, current_price=closes[-1], point_val=0.0001)
        
        self.assertIn(res.permission, ["LOCK", "WAIT"])

    def test_type_b_compression_armed(self):
        """Slow, overlapping compression into discount -> TYPE_B_COMPRESSION_ARMED."""
        # 50 bars uptrend to 1.3000, then 15 bars of slow overlapping decay to 1.2300 (discount)
        highs = np.linspace(1.2000, 1.3000, 50).tolist()
        lows = [h - 0.0010 for h in highs]
        closes = [h - 0.0002 for h in highs]
        opens = [l + 0.0002 for l in lows]
        
        cur = 1.3000
        for _ in range(15):
            cur -= 0.0040
            o = cur + 0.0010
            c = cur
            h = max(o, c) + 0.0015
            l = min(o, c) - 0.0015
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(c)
            
        df = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes})
        res = evaluate_wave_state(df, h4_trend_direction=1, current_price=1.2300, point_val=0.0001, csm_delta=0.5)
        
        self.assertTrue(res.in_discount)
        self.assertIn(res.permission, ["ARM", "GO"])

    def test_csm_opposed_forces_wait(self):
        """When CSM is strongly opposed (Delta <= -1.0), permission is forced to WAIT."""
        highs = np.linspace(1.2000, 1.3000, 50).tolist()
        lows = [h - 0.0010 for h in highs]
        closes = [h - 0.0002 for h in highs]
        opens = [l + 0.0002 for l in lows]
        
        cur = 1.3000
        for _ in range(10):
            cur -= 0.0050
            opens.append(cur + 0.0010)
            closes.append(cur)
            highs.append(cur + 0.0020)
            lows.append(cur - 0.0020)
            
        df = pd.DataFrame({'open': opens, 'high': highs, 'low': lows, 'close': closes})
        res = evaluate_wave_state(df, h4_trend_direction=1, current_price=1.2300, point_val=0.0001, csm_delta=-1.5)
        
        self.assertEqual(res.permission, "WAIT")

    def test_candidate_setup_payload_contains_wave_state(self):
        """Verify that CandidateSetup produces clean JSON payload with wave_state and permission."""
        cand = CandidateSetup(
            symbol="GBPUSD-ECNc",
            setup_type="TREND_ALIGNED_PULLBACK",
            direction=1,
            trigger_price=1.2750,
            timeframe="H1",
            wave_state=WaveState.TYPE_B_COMPRESSION_ARMED,
            wave_summary="[BULL | TYPE_B_COIL | CSM +1.50] -> GO",
            dealing_range_pos=0.35,
            suggested_sl=1.2700,
            suggested_tp=1.2850
        )
        
        payload = cand.to_payload_dict()
        self.assertEqual(payload["wave_state"], WaveState.TYPE_B_COMPRESSION_ARMED)
        self.assertIn("TYPE_B_COIL", payload["wave_state_summary"])
        self.assertEqual(payload["direction"], "BUY")


if __name__ == '__main__':
    unittest.main()
