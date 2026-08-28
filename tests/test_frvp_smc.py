import unittest
import numpy as np
import pandas as pd

from src.indicators.volume_profile import compute_fixed_range_volume_profile, check_ob_frvp_confluence, VolumeProfileResult
from src.indicators.lux_smc import LuxSMCAnalyzer, SMCSignal, SMCOrderBlock


class TestFRVPAndSMCIntegration(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        # Create a synthetic trending series with a clear impulse move
        n = 120
        trend = np.linspace(1.2000, 1.2500, n)
        noise = np.random.randn(n) * 0.0010
        p = trend + noise
        
        highs = p + np.abs(np.random.randn(n) * 0.0015)
        lows = p - np.abs(np.random.randn(n) * 0.0015)
        closes = p + np.random.randn(n) * 0.0005
        opens = np.roll(closes, 1)
        opens[0] = closes[0]
        vols = np.random.randint(100, 1000, size=n).astype(float)
        
        self.df = pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'tick_volume': vols
        })
        self.highs = highs
        self.lows = lows
        self.closes = closes
        self.vols = vols

    def test_compute_frvp_basic(self):
        frvp = compute_fixed_range_volume_profile(
            self.highs, self.lows, self.closes, self.vols,
            start_idx=10, end_idx=50, num_bins=50, value_area_pct=0.70
        )
        self.assertIsNotNone(frvp)
        assert frvp is not None  # type narrowing
        self.assertGreater(frvp.total_volume, 0.0)
        self.assertGreaterEqual(frvp.range_high, frvp.poc)
        self.assertLessEqual(frvp.range_low, frvp.poc)
        self.assertGreaterEqual(frvp.vah, frvp.val)
        self.assertGreaterEqual(frvp.poc, frvp.val)
        self.assertLessEqual(frvp.poc, frvp.vah)
        self.assertGreaterEqual(frvp.value_area_volume / frvp.total_volume, 0.65)

    def test_check_ob_frvp_confluence_bullish(self):
        frvp = VolumeProfileResult(
            poc=1.2250,
            vah=1.2350,
            val=1.2150,
            range_high=1.2400,
            range_low=1.2100,
            total_volume=50000.0,
            poc_volume=8000.0
        )
        # OB overlapping with POC
        conf_poc = check_ob_frvp_confluence(
            ob_top=1.2260,
            ob_bottom=1.2240,
            ob_direction="bullish",
            frvp=frvp,
            atr=0.0020
        )
        self.assertTrue(conf_poc["poc_overlap"])
        self.assertGreaterEqual(conf_poc["confluence_score"], 0.70)
        self.assertIn(conf_poc["rating"], ["A+", "A"])

        # OB at Value Area Low (Discount)
        conf_val = check_ob_frvp_confluence(
            ob_top=1.2140,
            ob_bottom=1.2120,
            ob_direction="bullish",
            frvp=frvp,
            atr=0.0020
        )
        self.assertTrue(conf_val["va_discount"])
        self.assertGreaterEqual(conf_val["confluence_score"], 0.65)

    def test_lux_smc_frvp_integration(self):
        analyzer = LuxSMCAnalyzer(swing_length=5)
        sig = analyzer.analyze(self.df)
        
        self.assertIsInstance(sig, SMCSignal)
        self.assertIn(sig.trend_bias, ['bullish', 'bearish', 'neutral'])
        
        # Verify Order Block fields if any OBs are detected
        all_obs = sig.order_blocks_bullish + sig.order_blocks_bearish
        if all_obs:
            first_ob = all_obs[0]
            self.assertIn('poc', first_ob)
            self.assertIn('vah', first_ob)
            self.assertIn('val', first_ob)
            self.assertIn('poc_confluence', first_ob)
            self.assertIn('va_discount', first_ob)
            self.assertIn('frvp_score', first_ob)
            self.assertIn('frvp_rating', first_ob)


if __name__ == '__main__':
    unittest.main()
