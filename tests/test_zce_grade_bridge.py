import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

from src.analytics.zone_confluence_engine import (
    ZoneMapResult,
)
from src.analytics.macro_strategic_engine import (
    MacroStrategicEngine,
)


import config


def _rates_ndarray(n=120, base=1.6120, step=0.0001):
    dt = np.dtype([
        ("time", "<i8"),
        ("open", "<f8"),
        ("high", "<f8"),
        ("low", "<f8"),
        ("close", "<f8"),
        ("tick_volume", "<u8"),
        ("spread", "<i4"),
        ("real_volume", "<u8"),
    ])
    arr = np.zeros(n, dtype=dt)
    px = base
    for i in range(n):
        arr[i]["time"] = i
        arr[i]["open"] = px
        arr[i]["high"] = px + step
        arr[i]["low"] = px - step
        arr[i]["close"] = px + step * 0.4
        arr[i]["tick_volume"] = 100
        px += step * 0.1
    return arr


class TestZCEGradeBridge(unittest.TestCase):
    def setUp(self):
        self.mse = MacroStrategicEngine()

    def test_zone_map_result_wall_override_exports_grades(self):
        zm = ZoneMapResult(
            symbol="EURAUD",
            ts=1725000000.0,
            immediate_floor_f1=1.61063,
            immediate_ceiling_c1=1.61291,
            deep_floor_f2=1.60500,
            deep_ceiling_c2=1.62000,
            immediate_floor_f1_grade="GRADE_2_INTERMEDIATE",
            immediate_ceiling_c1_grade="GRADE_3_MACRO",
            immediate_floor_f1_score=4.8,
            immediate_ceiling_c1_score=9.28,
            deep_floor_f2_grade="GRADE_2_INTERMEDIATE",
            deep_ceiling_c2_grade="GRADE_3_MACRO",
            deep_floor_f2_score=3.5,
            deep_ceiling_c2_score=7.1,
        )
        override = zm.to_wall_override()
        self.assertTrue(override["enable"])
        self.assertEqual(override["imm_ceiling_c1"], 1.61291)
        self.assertEqual(override["imm_floor_f1"], 1.61063)
        self.assertEqual(override["imm_ceiling_c1_grade"], "GRADE_3_MACRO")
        self.assertEqual(override["imm_floor_f1_grade"], "GRADE_2_INTERMEDIATE")
        self.assertEqual(override["c1_grade"], "GRADE_3_MACRO")
        self.assertEqual(override["f1_grade"], "GRADE_2_INTERMEDIATE")
        self.assertAlmostEqual(override["imm_ceiling_c1_score"], 9.28)
        self.assertAlmostEqual(override["imm_floor_f1_score"], 4.8)
        self.assertEqual(override["c2_grade"], "GRADE_3_MACRO")
        self.assertEqual(override["f2_grade"], "GRADE_2_INTERMEDIATE")

    def test_mse_compute_directive_absorbs_zce_g3_grade(self):
        with unittest.mock.patch.object(config.mt5, "symbol_info", return_value=type("SI", (), {"point": 0.00001, "digits": 5})()), \
             unittest.mock.patch.object(config.mt5, "symbol_info_tick", return_value=type("TK", (), {"bid": 1.61200, "ask": 1.61210})()), \
             unittest.mock.patch.object(config.mt5, "copy_rates_from_pos", return_value=_rates_ndarray()):

            zce_override = {
                "enable": True,
                "imm_ceiling_c1": 1.61350,
                "imm_floor_f1": 1.61050,
                "deep_ceiling_c2": 1.62000,
                "deep_floor_f2": 1.60500,
                "imm_ceiling_c1_grade": "GRADE_3_MACRO",
                "imm_ceiling_c1_score": 9.28,
                "imm_floor_f1_grade": "GRADE_3_MACRO",
                "imm_floor_f1_score": 8.50,
                "deep_ceiling_c2_grade": "GRADE_3_MACRO",
                "deep_ceiling_c2_score": 7.00,
                "deep_floor_f2_grade": "GRADE_2_INTERMEDIATE",
                "deep_floor_f2_score": 4.50,
            }

            directive = self.mse.compute_directive("EURAUD", zce_walls=zce_override)

            self.assertEqual(directive.immediate_ceiling_c1, 1.61350)
            self.assertEqual(directive.immediate_floor_f1, 1.61050)
            self.assertEqual(directive.c1_reaction_grade, "GRADE_3_MACRO")
            self.assertEqual(directive.f1_reaction_grade, "GRADE_3_MACRO")
            self.assertAlmostEqual(directive.c1_density_score, 9.28)
            self.assertAlmostEqual(directive.f1_density_score, 8.50)
            self.assertEqual(directive.c2_reaction_grade, "GRADE_3_MACRO")
            self.assertEqual(directive.f2_reaction_grade, "GRADE_2_INTERMEDIATE")

            self.assertTrue(len(directive.layered_ceilings) >= 1)
            self.assertEqual(directive.layered_ceilings[0]["reaction_grade"], "GRADE_3_MACRO")
            self.assertAlmostEqual(directive.layered_ceilings[0]["density_score"], 9.28)

            self.assertTrue(len(directive.layered_floors) >= 1)
            self.assertEqual(directive.layered_floors[0]["reaction_grade"], "GRADE_3_MACRO")
            self.assertAlmostEqual(directive.layered_floors[0]["density_score"], 8.50)

    def test_mse_compute_directive_per_side_zce_absorption(self):
        with unittest.mock.patch.object(config.mt5, "symbol_info", return_value=type("SI", (), {"point": 0.00001, "digits": 5})()), \
             unittest.mock.patch.object(config.mt5, "symbol_info_tick", return_value=type("TK", (), {"bid": 1.61200, "ask": 1.61210})()), \
             unittest.mock.patch.object(config.mt5, "copy_rates_from_pos", return_value=_rates_ndarray()):

            zce_override = {
                "enable": True,
                "imm_ceiling_c1": 1.61350,
                "imm_floor_f1": None,
                "imm_ceiling_c1_grade": "GRADE_3_MACRO",
                "imm_ceiling_c1_score": 9.28,
            }

            directive = self.mse.compute_directive("EURAUD", zce_walls=zce_override)

            self.assertEqual(directive.immediate_ceiling_c1, 1.61350)
            self.assertEqual(directive.c1_reaction_grade, "GRADE_3_MACRO")
            self.assertAlmostEqual(directive.c1_density_score, 9.28)
            self.assertEqual(directive.layered_ceilings[0]["reaction_grade"], "GRADE_3_MACRO")


if __name__ == "__main__":
    unittest.main()
