import unittest
import pandas as pd
import numpy as np
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from src.analytics.market_scanner import MarketScanner

class TestM1BTrendFollowingSweep(unittest.TestCase):
    def setUp(self):
        self.scanner = MarketScanner()
        dates = pd.date_range('2026-09-07 00:00', periods=24, freq='1h')
        self.df_bear = pd.DataFrame({
            'open':  np.linspace(1.8850, 1.8740, 24),
            'high':  np.linspace(1.8860, 1.8755, 24),
            'low':   np.linspace(1.8840, 1.8730, 24),
            'close': np.linspace(1.8845, 1.8735, 24),
            'atr':   [0.00100] * 24
        }, index=dates)

    def test_m1b_anchor_detection_with_zce_confluence_sell(self):
        macro = {
            'df': self.df_bear,
            'current_atr': 0.00100,
            'point': 0.00001,
            'immediate_ceiling_c1': 1.87500,
            'macro_bias_score': -0.80,
            'is_bear': True,
            'is_bull': False,
            'csm_delta': -2.0,
            'dealing_range_pos': 0.20
        }
        res = self.scanner.find_m1b_zce_basing_anchor('GBPAUD-ECNc', mid=1.87400, direction=-1, macro=macro, pt=0.00001, atr_val=0.00100)
        self.assertIsNotNone(res)
        self.assertEqual(res['direction'], -1)
        self.assertLessEqual(abs(res['anchor_level'] - res['zce_level']), 0.00050 + 1e-5)

    def test_m1b_anchor_returns_none_without_zce_confluence(self):
        macro = {
            'df': self.df_bear,
            'current_atr': 0.00100,
            'point': 0.00001,
            'immediate_ceiling_c1': 1.95000,
            'macro_bias_score': -0.80,
            'is_bear': True,
            'is_bull': False,
            'csm_delta': -2.0,
            'dealing_range_pos': 0.20
        }
        res = self.scanner.find_m1b_zce_basing_anchor('GBPAUD-ECNc', mid=1.87400, direction=-1, macro=macro, pt=0.00001, atr_val=0.00100)
        self.assertIsNone(res)

    def test_get_radar_standbys_includes_m1b(self):
        macro = {
            'df': self.df_bear,
            'current_atr': 0.00100,
            'point': 0.00001,
            'immediate_ceiling_c1': 1.87500,
            'immediate_floor_f1': 1.87000,
            'macro_bias_score': -0.80,
            'is_bear': True,
            'is_bull': False,
            'csm_delta': -2.0,
            'dealing_range_pos': 0.20
        }
        standbys = self.scanner.get_radar_standbys('GBPAUD-ECNc', mid=1.87400, macro=macro, pt=0.00001, atr_val=0.00100)
        m1b = next((s for s in standbys if s['type'] == 'M1B'), None)
        self.assertIsNotNone(m1b)
        self.assertEqual(m1b['direction'], -1)
        self.assertIn('status', m1b)
        self.assertIn('price', m1b)

if __name__ == '__main__':
    unittest.main()
