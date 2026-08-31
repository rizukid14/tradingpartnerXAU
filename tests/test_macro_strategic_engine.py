import unittest
import pandas as pd
import numpy as np
from src.analytics.macro_strategic_engine import MacroStrategicEngine, StructuralZone, MacroStrategicDirective
from src.indicators.atlas_dna import get_symbol_step, calculate_dynamic_stations, calculate_dual_grid_stations, calculate_intraday_sl_tp


class TestMacroStrategicEngine(unittest.TestCase):
    def setUp(self):
        self.engine = MacroStrategicEngine()

    def test_atlas_dual_grid_calculations(self):
        # FX 100-pip vs 50-pip grid
        dual_gu = calculate_dual_grid_stations("GBPUSD", 1.35335)
        self.assertEqual(dual_gu["macro_step"], 0.0100)
        self.assertEqual(dual_gu["micro_step_50"], 0.0050)
        self.assertEqual(dual_gu["sub_floor_50"], 1.35000)
        self.assertEqual(dual_gu["sub_ceiling_50"], 1.35500)

        # JPY 100-pip vs 50-pip grid
        dual_ej = calculate_dual_grid_stations("EURJPY", 185.421)
        self.assertEqual(dual_ej["macro_step"], 1.000)
        self.assertEqual(dual_ej["micro_step_50"], 0.500)
        self.assertEqual(dual_ej["sub_floor_50"], 185.000)
        self.assertEqual(dual_ej["sub_ceiling_50"], 185.500)

    def test_intraday_sl_safety_ceiling(self):
        # SL calculation must never exceed 160 pts (0.00160) for FX
        atr_h1 = 0.00300 # 30 pips
        res = calculate_intraday_sl_tp("GBPUSD", 1.35000, 1, 1.34000, atr_h1)
        self.assertAlmostEqual(res["sl"], 1.34840, places=5)
        self.assertAlmostEqual(abs(res["sl"] - 1.35000), 0.00160, places=5)

    def test_drop_base_drop_detection(self):
        # Create synthetic DBD candles
        dates = pd.date_range("2026-08-29", periods=10, freq="1h")
        data = {
            "open":  [1.3600]*6 + [1.3600, 1.3540, 1.3540, 1.3460],
            "high":  [1.3600]*6 + [1.3610, 1.3550, 1.3545, 1.3465],
            "low":   [1.3600]*6 + [1.3530, 1.3535, 1.3450, 1.3440],
            "close": [1.3600]*6 + [1.3540, 1.3540, 1.3460, 1.3450]
        }
        df = pd.DataFrame(data, index=dates)
        entry, roof = MacroStrategicEngine._detect_drop_base_drop(df, 5)
        self.assertIsNotNone(entry)
        self.assertIsNotNone(roof)
        self.assertLessEqual(entry, roof)
        self.assertEqual(entry, 1.3535)
        self.assertEqual(roof, 1.3550)

    def test_systemic_basket_usd_surge_lock(self):
        from src.analytics.currency_strength import evaluate_systemic_basket_lock
        scores_h1 = {"USD": 45.0, "EUR": -20.0, "GBP": -15.0, "JPY": 0.0, "CHF": 0.0, "AUD": 0.0, "CAD": 0.0, "NZD": 0.0}
        scores_m15 = {"USD": 50.0, "EUR": -25.0, "GBP": -20.0, "JPY": 0.0, "CHF": 0.0, "AUD": 0.0, "CAD": 0.0, "NZD": 0.0}

        # In USD surge: BUY on EURUSD / GBPUSD / XAUUSD must be locked!
        locked_gu, reason_gu, curr_gu = evaluate_systemic_basket_lock("GBPUSD", 1, scores_h1, scores_m15)
        self.assertTrue(locked_gu)
        self.assertIn("SYSTEMIC USD SURGE", reason_gu)
        self.assertEqual(curr_gu, "USD")

        # But SELL on GBPUSD is allowed
        locked_gu_s, _, _ = evaluate_systemic_basket_lock("GBPUSD", -1, scores_h1, scores_m15)
        self.assertFalse(locked_gu_s)

        # In USD surge: SELL on USDCAD must be locked!
        locked_uc, reason_uc, curr_uc = evaluate_systemic_basket_lock("USDCAD", -1, scores_h1, scores_m15)
        self.assertTrue(locked_uc)
        self.assertIn("SYSTEMIC USD SURGE", reason_uc)

    def test_systemic_basket_jpy_dump_lock(self):
        from src.analytics.currency_strength import evaluate_systemic_basket_lock
        scores_h1 = {"JPY": -55.0, "EUR": 5.0, "GBP": 5.0, "USD": 0.0, "CHF": 0.0, "AUD": 0.0, "CAD": 0.0, "NZD": 0.0}
        scores_m15 = {"JPY": -60.0, "EUR": 5.0, "GBP": 5.0, "USD": 0.0, "CHF": 0.0, "AUD": 0.0, "CAD": 0.0, "NZD": 0.0}

        # In JPY dump: SELL on EURJPY / CADJPY must be locked (JPY crosses are expanding bullish)!
        locked_ej, reason_ej, curr_ej = evaluate_systemic_basket_lock("EURJPY", -1, scores_h1, scores_m15)
        self.assertTrue(locked_ej)
        self.assertIn("SYSTEMIC JPY DUMP", reason_ej)
        self.assertEqual(curr_ej, "JPY")

        # But BUY on EURJPY is allowed
        locked_ej_b, _, _ = evaluate_systemic_basket_lock("EURJPY", 1, scores_h1, scores_m15)
        self.assertFalse(locked_ej_b)

    def test_systemic_basket_eur_dump_lock(self):
        from src.analytics.currency_strength import evaluate_systemic_basket_lock
        scores_h1 = {"EUR": -30.0, "USD": 5.0, "GBP": 5.0, "JPY": 0.0, "CHF": 0.0, "AUD": 5.0, "CAD": 5.0, "NZD": 0.0}
        scores_m15 = {"EUR": -35.0, "USD": 5.0, "GBP": 5.0, "JPY": 0.0, "CHF": 0.0, "AUD": 5.0, "CAD": 3.0, "NZD": 0.0}

        # In EUR dump: BUY on EURUSD / EURJPY / EURGBP must be locked!
        locked_eu, reason_eu, curr_eu = evaluate_systemic_basket_lock("EURUSD", 1, scores_h1, scores_m15)
        self.assertTrue(locked_eu)
        self.assertIn("SYSTEMIC EUR DUMP", reason_eu)
        self.assertEqual(curr_eu, "EUR")

        # But SELL on EURUSD is allowed
        locked_eu_s, _, _ = evaluate_systemic_basket_lock("EURUSD", -1, scores_h1, scores_m15)
        self.assertFalse(locked_eu_s)

    def test_systemic_basket_extreme_delta_spread_lock(self):
        from src.analytics.currency_strength import evaluate_systemic_basket_lock
        # Each individual currency is mild (< 20.0 threshold), but their relative delta is 22.0 (>= 18.0 threshold)
        scores_h1 = {"GBP": 10.0, "AUD": -10.0, "USD": 0.0, "EUR": 0.0, "JPY": 0.0, "CHF": 0.0, "CAD": 0.0, "NZD": 0.0}
        scores_m15 = {"GBP": 12.0, "AUD": -12.0, "USD": 0.0, "EUR": 0.0, "JPY": 0.0, "CHF": 0.0, "CAD": 0.0, "NZD": 0.0}

        # Net Delta GBPAUD = +11.2 - (-11.2) = +22.4 (>= +18.0 threshold) -> SELL GBPAUD must be locked!
        locked_ga, reason_ga, _ = evaluate_systemic_basket_lock("GBPAUD", -1, scores_h1, scores_m15)
        self.assertTrue(locked_ga)
        self.assertIn("EXTREME BASKET DELTA", reason_ga)


if __name__ == "__main__":
    unittest.main()
