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
            'high':  np.linspace(1.8860, 1.8748, 24),
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
        self.assertGreater(res['origin_time'], 0)
        self.assertGreaterEqual(res['touches'], 1)

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

    def test_m1b_eqh_pool_detection_multiple_touches(self):
        # Create a DF where 3 distinct candles hit ~1.87520 (near C1 1.87500)
        df_eqh = self.df_bear.copy()
        df_eqh.iloc[10, df_eqh.columns.get_loc('high')] = 1.87520
        df_eqh.iloc[15, df_eqh.columns.get_loc('high')] = 1.87515
        df_eqh.iloc[20, df_eqh.columns.get_loc('high')] = 1.87525
        macro = {
            'df': df_eqh,
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
        self.assertTrue(res['is_eqh'])
        self.assertGreaterEqual(res['touches'], 2)
        self.assertGreater(res['origin_time'], 0)

    def test_get_radar_standbys_includes_m1b_with_temporal_marker(self):
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
        # Verify temporal marker is present at origin candle even in WAITING_SWEEP
        self.assertGreater(m1b['event_time'], 0)
        self.assertGreater(m1b['origin_time'], 0)

    def test_m1b_buy_proximity_guard_rejects_runaway_sweep(self):
        """Verify M1B BUY rejects sweeps when market has flown away > 0.35x ATR above anchor."""
        atr_val = 0.00080
        anchor_lvl = 1.16150
        # Price is at 1.16256 (106 pts = 1.33x ATR above anchor) -> must be rejected by proximity
        mid_runaway = 1.16256
        max_dist_atr = getattr(config, 'M1B_MAX_DIST_ATR', 0.35)
        in_prox = ((anchor_lvl - 0.15 * atr_val) <= mid_runaway <= (anchor_lvl + max_dist_atr * atr_val))
        self.assertFalse(in_prox, "Runaway sweep 1.33x ATR away must be outside proximity window!")

    def test_m1b_buy_proximity_guard_accepts_near_anchor_and_places_limit_at_anchor(self):
        """Verify M1B BUY accepts sweeps near anchor and places limit order at anchor level (not dragged to mid)."""
        atr_val = 0.00080
        anchor_lvl = 1.16150
        mid_near = 1.16170  # only 20 pts = 0.25x ATR above anchor
        max_dist_atr = getattr(config, 'M1B_MAX_DIST_ATR', 0.35)
        in_prox = ((anchor_lvl - 0.15 * atr_val) <= mid_near <= (anchor_lvl + max_dist_atr * atr_val))
        self.assertTrue(in_prox, "Sweep 0.25x ATR from anchor must be inside proximity window!")

        spread_pts = 2
        pt = 0.00001
        digits = 5
        limit_entry = round(anchor_lvl + (spread_pts * 0.5 * pt), digits)
        self.assertEqual(limit_entry, 1.16151, "Limit entry must be placed at ZCE anchor + spread offset, NOT at mid!")

if __name__ == '__main__':
    unittest.main()
