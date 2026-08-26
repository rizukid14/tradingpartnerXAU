import unittest
import pandas as pd
import numpy as np
from src.indicators.lux_smc import LuxSMCAnalyzer

class TestLuxSMC(unittest.TestCase):
    def setUp(self):
        np.random.seed(42)
        p = 1.2500 + np.cumsum(np.random.randn(100) * 0.0010)
        self.df = pd.DataFrame({
            'open': p,
            'high': p + np.random.rand(100) * 0.0015,
            'low': p - np.random.rand(100) * 0.0015,
            'close': p + np.random.randn(100) * 0.0005,
        })
        self.analyzer = LuxSMCAnalyzer()

    def test_analyze_execution(self):
        sig = self.analyzer.analyze(self.df)
        self.assertIn(sig.trend_bias, ['bullish', 'bearish', 'neutral'])
        self.assertLessEqual(sig.discount_zone, sig.equilibrium)
        self.assertLessEqual(sig.equilibrium, sig.premium_zone)
        self.assertIsInstance(sig.order_blocks_bullish, list)
        self.assertIsInstance(sig.order_blocks_bearish, list)
        self.assertIsInstance(sig.fvg_bullish, list)
        self.assertIsInstance(sig.fvg_bearish, list)

if __name__ == '__main__':
    unittest.main()
