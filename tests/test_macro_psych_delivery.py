import unittest
import pandas as pd
import numpy as np

from src.indicators.wave_state import (
    WaveState,
    WaveStateResult,
    get_symbol_psych_step,
    evaluate_macro_compass_corridor,
    evaluate_wave_state
)

class TestMacroPsychDelivery(unittest.TestCase):
    def test_symbol_psych_step_calibration(self):
        self.assertEqual(get_symbol_psych_step("XAUUSD-ECNc"), 50.0)
        self.assertEqual(get_symbol_psych_step("USDJPY-ECNc"), 1.000)
        self.assertEqual(get_symbol_psych_step("EURJPY-ECNc"), 1.000)
        self.assertEqual(get_symbol_psych_step("GBPJPY-ECNc"), 2.000)
        self.assertEqual(get_symbol_psych_step("EURUSD-ECNc"), 0.0100)
        self.assertEqual(get_symbol_psych_step("GBPUSD-ECNc"), 0.0100)
        self.assertEqual(get_symbol_psych_step("AUDUSD-ECNc"), 0.0050)
        self.assertEqual(get_symbol_psych_step("GBPAUD-ECNc"), 0.0200)

    def test_macro_compass_corridor_rejections(self):
        # 1. Bearish Ceiling Collision at 1.2000 on EURUSD with Upper Rejection Wick
        corr, target, step, is_ceil, is_flr = evaluate_macro_compass_corridor(
            symbol="EURUSD",
            current_price=1.1980,
            pwh=1.2010,
            pwl=1.1600,
            macro_high=1.2010,
            macro_low=1.1600,
            cur_atr=0.0060,
            last_high=1.2005,
            last_low=1.1960,
            last_open=1.1970,
            last_close=1.1975 # Upper wick = 1.2005 - 1.1975 = 0.0030 (66% of range 0.0045)
        )
        self.assertEqual(corr, "BEARISH_CORRIDOR")
        self.assertTrue(is_ceil)
        self.assertFalse(is_flr)
        self.assertAlmostEqual(target, 1.1805, places=4)

        # 2. Bullish Floor Collision at 1.1400 on EURUSD with Lower Rejection Wick
        corr_b, target_b, step_b, is_ceil_b, is_flr_b = evaluate_macro_compass_corridor(
            symbol="EURUSD",
            current_price=1.1420,
            pwh=1.2000,
            pwl=1.1405,
            macro_high=1.2000,
            macro_low=1.1405,
            cur_atr=0.0060,
            last_high=1.1460,
            last_low=1.1400,
            last_open=1.1450,
            last_close=1.1440 # Lower wick = 1.1440 - 1.1400 = 0.0040 (66% of range 0.0060)
        )
        self.assertEqual(corr_b, "BULLISH_CORRIDOR")
        self.assertFalse(is_ceil_b)
        self.assertTrue(is_flr_b)
        self.assertAlmostEqual(target_b, 1.17025, places=4)

    def test_evaluate_wave_state_with_macro_corridor(self):
        n = 50
        base = 1.2000
        # Simulating descent from 1.2000
        closes = np.linspace(base, 1.1850, n)
        highs = closes + 0.0020
        lows = closes - 0.0020
        opens = closes + 0.0010
        # Last bar has upper rejection wick near 1.1900
        highs[-1] = 1.1905
        opens[-1] = 1.1870
        closes[-1] = 1.1865
        lows[-1] = 1.1860
        
        df = pd.DataFrame({'high': highs, 'low': lows, 'open': opens, 'close': closes})
        
        res = evaluate_wave_state(
            df_h1=df,
            h4_trend_direction=-1,
            current_price=1.1865,
            atr_pts=60,
            point_val=0.0001,
            csm_delta=-0.8,
            symbol="EURUSD",
            pwh=1.2010,
            pwl=1.1400,
            macro_high=1.2010,
            macro_low=1.1400
        )
        
        self.assertIn(res.macro_corridor, ("BEARISH_CORRIDOR", "NEUTRAL"))
        self.assertGreater(res.psych_step, 0.0)
        self.assertIsNotNone(res.target_station)

if __name__ == '__main__':
    unittest.main()
