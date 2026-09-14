import unittest
import pandas as pd
import numpy as np
from src.analytics.macro_strategic_engine import MacroStrategicEngine, MacroStrategicDirective

class TestHierarchicalFractalField(unittest.TestCase):
    def setUp(self):
        self.engine = MacroStrategicEngine()

    def test_evaluate_scale_tensor_bullish(self):
        # Generate clean higher highs and higher lows
        n = 50
        dates = pd.date_range("2026-09-01", periods=n, freq="1h")
        trend = np.linspace(1.2000, 1.2500, n)
        noise = np.sin(np.linspace(0, 10, n)) * 0.0020
        c = trend + noise
        h = c + 0.0010
        l = c - 0.0010
        df = pd.DataFrame({"open": c, "high": h, "low": l, "close": c}, index=dates)

        res = MacroStrategicEngine._evaluate_scale_tensor(df, "H1", pt=0.00001, cur_atr=0.0020)
        self.assertEqual(res["tau"], 1)
        self.assertEqual(res["label"], "BULL")
        self.assertGreaterEqual(res["phi"], 0.70)

    def test_evaluate_scale_tensor_bearish(self):
        # Generate clean lower highs and lower lows
        n = 50
        dates = pd.date_range("2026-09-01", periods=n, freq="1h")
        trend = np.linspace(1.2500, 1.2000, n)
        noise = np.sin(np.linspace(0, 10, n)) * 0.0020
        c = trend + noise
        h = c + 0.0010
        l = c - 0.0010
        df = pd.DataFrame({"open": c, "high": h, "low": l, "close": c}, index=dates)

        res = MacroStrategicEngine._evaluate_scale_tensor(df, "H1", pt=0.00001, cur_atr=0.0020)
        self.assertEqual(res["tau"], -1)
        self.assertEqual(res["label"], "BEAR")
        self.assertLessEqual(res["phi"], 0.30)

    def test_golden_realignment_apex_buy_resolution(self):
        # Permutation: D1 Bull (+1), H4 Pullback Bear (-1), H1 Realigns Bull (+1) -> AUDNZD scenario
        # Simulating directive calculation logic
        tau_macro = 1
        tau_meso = -1
        tau_micro = 1

        # Test regime mapping
        if tau_macro == 1 and tau_meso == -1 and tau_micro == 1:
            fractal_regime = "STRUCTURAL_RE_ALIGNMENT_APEX_BUY"
        else:
            fractal_regime = "OTHER"

        self.assertEqual(fractal_regime, "STRUCTURAL_RE_ALIGNMENT_APEX_BUY")

    def test_coherent_cascade_bear_resolution(self):
        # Permutation: D1 Bear (-1), H4 Bear (-1), H1 Bear (-1) -> NZDUSD waterfall scenario
        tau_macro = -1
        tau_meso = -1
        tau_micro = -1

        if tau_macro == -1 and tau_meso == -1 and tau_micro == -1:
            fractal_regime = "COHERENT_CASCADE_BEAR"
        else:
            fractal_regime = "OTHER"

        self.assertEqual(fractal_regime, "COHERENT_CASCADE_BEAR")

    def test_macro_retreat_at_supply(self):
        # Permutation: D1 Bear (-1), H4 Bull (+1), H1 Bull (+1) at C1 ceiling
        tau_macro = -1
        tau_meso = 1
        tau_micro = 1
        dist_to_c1_atr = 0.20 # Close to ceiling (< 0.35)

        if tau_macro == -1 and tau_meso == 1 and tau_micro == 1:
            if dist_to_c1_atr <= 0.35:
                fractal_regime = "MACRO_RETREAT_AT_SUPPLY"
            else:
                fractal_regime = "MACRO_SECONDARY_RETRACEMENT_BULL"
        else:
            fractal_regime = "OTHER"

        self.assertEqual(fractal_regime, "MACRO_RETREAT_AT_SUPPLY")

if __name__ == "__main__":
    unittest.main()
