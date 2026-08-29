import unittest
from src.indicators.atlas_dna import get_symbol_step, calculate_dynamic_stations, calculate_intraday_sl_tp


class TestAtlasDNA(unittest.TestCase):

    def test_symbol_step_dna(self):
        self.assertEqual(get_symbol_step("XAUUSD-ECNc"), 50.0)
        self.assertEqual(get_symbol_step("EURJPY"), 1.000)
        self.assertEqual(get_symbol_step("GBPJPY"), 2.000)
        self.assertEqual(get_symbol_step("EURUSD"), 0.0100)
        self.assertEqual(get_symbol_step("GBPUSD"), 0.0100)
        self.assertEqual(get_symbol_step("NZDCAD"), 0.0025)
        self.assertEqual(get_symbol_step("AUDCAD"), 0.0025)

    def test_dynamic_stations_calculation(self):
        stations_gu = calculate_dynamic_stations("GBPUSD", 1.35320)
        self.assertEqual(stations_gu["step"], 0.0100)
        self.assertAlmostEqual(stations_gu["base_station"], 1.3500, places=4)
        self.assertAlmostEqual(stations_gu["upper_station"], 1.3600, places=4)
        self.assertAlmostEqual(stations_gu["lower_station"], 1.3400, places=4)

        stations_nzdcad = calculate_dynamic_stations("NZDCAD", 0.82400)
        self.assertEqual(stations_nzdcad["step"], 0.0025)
        self.assertAlmostEqual(stations_nzdcad["base_station"], 0.8250, places=4)

    def test_intraday_sl_tp_calculation(self):
        # BUY on GBPUSD
        res_buy = calculate_intraday_sl_tp(
            symbol="GBPUSD",
            entry_price=1.35320,
            direction=1,
            origin_level=1.35196, # PWL
            atr_h1=0.0020,
            pwl=1.35196,
            pwh=1.36756
        )
        self.assertTrue(res_buy["sl"] < 1.35320)
        self.assertTrue(res_buy["tp"] > 1.35320)
        self.assertTrue(res_buy["risk_reward"] >= 1.25)

        # SELL on GBPUSD
        res_sell = calculate_intraday_sl_tp(
            symbol="GBPUSD",
            entry_price=1.35320,
            direction=-1,
            origin_level=1.35976, # 50% Eq / EMA20
            atr_h1=0.0020,
            pwl=1.35196,
            pwh=1.36756
        )
        self.assertTrue(res_sell["sl"] > 1.35320)
        self.assertTrue(res_sell["tp"] < 1.35320)
        self.assertTrue(res_sell["risk_reward"] >= 1.25)


if __name__ == "__main__":
    unittest.main()
