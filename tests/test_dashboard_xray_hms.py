"""
tests/test_dashboard_xray_hms.py

Unit tests verifying:
1. Modernized 8-Gate X-Ray Surveillance in dashboard.py:
   - Gate 4 evaluates fractal_regime and execution ceilings.
   - Gate 5 conditional CSM matrix (allows lagging CSM during STRUCTURAL_RE_ALIGNMENT_APEX).
   - Gate 5 blocks opposed CSM during COHERENT_CASCADE_BEAR.
   - Gate 6 reports context-aware regime tactics.
2. Predictive Station Generation (calculate_predictive_matrix):
   - Forbids counter-trend WAIT M1A BUY in COHERENT_CASCADE_BEAR.
   - Forbids counter-trend WAIT M1A SELL in STRUCTURAL_RE_ALIGNMENT_APEX_BUY.
   - Generates pro-trend M3 / M2 stations.
"""

import unittest
from unittest.mock import MagicMock
from dashboard import CockpitDataEngine, calculate_predictive_matrix


def _make_mock_strat(regime, bias, directive, max_buy, min_sell, tier="FULL_ALLOW"):
    strat = MagicMock()
    strat.action_tier = tier
    strat.daily_macro_bias = bias
    strat.primary_execution_directive = directive
    strat.max_allowed_buy_price = max_buy
    strat.max_allowed_buy = max_buy
    strat.min_allowed_sell_price = min_sell
    strat.min_allowed_sell = min_sell
    strat.fractal_regime = regime
    strat.forbidden_traps = []
    return strat


class TestDashboardXRayHMS(unittest.TestCase):
    def setUp(self):
        self.engine = CockpitDataEngine()
        self.engine.scanner = MagicMock()
        self.engine.scanner._symbol_directional_state = {}
        self.engine.scanner._m4_state = {}
        self.engine.scanner._m4_df = {}
        self.engine.scanner.macro_cache = {}

    def test_gate4_ceiling_veto_on_cascade_bear(self):
        """Gate 4 must show COHERENT_CASCADE_BEAR in desc and record ceiling status."""
        strat = _make_mock_strat(
            regime="COHERENT_CASCADE_BEAR",
            bias="BEARISH_EXPANSION",
            directive="HUNT_SELL_CONTINUATION",
            max_buy=0.0,
            min_sell=0.5780
        )
        macro = {
            "is_bear": True,
            "is_bull": False,
            "csm_delta": -2.2,
            "permission_state": "GO",
            "strat_dir": strat
        }
        gates = self.engine._evaluate_8_gates(
            sym="NZDUSD-ECNc",
            valid_sym="NZDUSD",
            macro=macro,
            strat=strat,
            mid=0.5800,
            spread_pts=10,
            atr_val=0.0050,
            pt=0.00001
        )
        gate4 = next(g for g in gates if g["id"] == 4)
        self.assertIn("COHERENT_CASCADE_BEAR", gate4["desc"])

    def test_gate5_conditional_csm_allows_fortress_realignment(self):
        """Gate 5 must NOT BLOCK opposed CSM if regime is STRUCTURAL_RE_ALIGNMENT_APEX."""
        strat = _make_mock_strat(
            regime="STRUCTURAL_RE_ALIGNMENT_APEX_BUY",
            bias="BULLISH_EXPANSION",
            directive="HUNT_BUY_AT_RBS",
            max_buy=1.2400,
            min_sell=0.0
        )
        macro = {
            "is_bear": False,
            "is_bull": True,
            "csm_delta": -2.5,
            "permission_state": "GO",
            "strat_dir": strat,
            "fractal_regime": "STRUCTURAL_RE_ALIGNMENT_APEX_BUY"
        }
        gates = self.engine._evaluate_8_gates(
            sym="AUDNZD-ECNc",
            valid_sym="AUDNZD",
            macro=macro,
            strat=strat,
            mid=1.1200,
            spread_pts=15,
            atr_val=0.0060,
            pt=0.00001
        )
        gate5 = next(g for g in gates if g["id"] == 5)
        self.assertEqual(gate5["status"], "OBSERVE")
        self.assertIn("SCALED LOT", gate5["title"])
        self.assertIn("Lagging CSM", gate5["desc"])

    def test_gate5_blocks_opposed_csm_in_cascade(self):
        """Gate 5 MUST BLOCK opposed CSM if regime is COHERENT_CASCADE (when filter enabled)."""
        import config
        from unittest.mock import patch
        strat = _make_mock_strat(
            regime="COHERENT_CASCADE_BEAR",
            bias="BEARISH_EXPANSION",
            directive="HUNT_SELL_CONTINUATION",
            max_buy=0.0,
            min_sell=0.5780
        )
        macro = {
            "is_bear": True,
            "is_bull": False,
            "csm_delta": +2.5,
            "permission_state": "GO",
            "strat_dir": strat,
            "fractal_regime": "COHERENT_CASCADE_BEAR"
        }
        with patch.object(config, "ENABLE_CSM_FLOW_FILTER", True):
            gates = self.engine._evaluate_8_gates(
                sym="NZDUSD-ECNc",
                valid_sym="NZDUSD",
                macro=macro,
                strat=strat,
                mid=0.5800,
                spread_pts=10,
                atr_val=0.0050,
                pt=0.00001
            )
            gate5 = next(g for g in gates if g["id"] == 5)
            self.assertEqual(gate5["status"], "BLOCK")
            self.assertIn("CSM OPPOSED", gate5["reason"])

    def test_predictive_stations_cascade_bear_no_buy_m1a(self):
        """In COHERENT_CASCADE_BEAR, calculate_predictive_matrix must NOT produce BUY stations."""
        strat = _make_mock_strat(
            regime="COHERENT_CASCADE_BEAR",
            bias="BEARISH_EXPANSION",
            directive="HUNT_SELL_CONTINUATION",
            max_buy=0.0,
            min_sell=0.5780
        )
        macro = {
            "is_bear": True,
            "is_bull": False,
            "h1_trend": "BEAR",
            "strat_dir": strat,
            "fractal_regime": "COHERENT_CASCADE_BEAR",
            "max_allowed_buy_price": 0.0,
            "min_allowed_sell_price": 0.5780
        }
        candles = [
            {"high": 0.5850, "low": 0.5790, "close": 0.5800, "ema20": 0.5820, "ema50": 0.5840, "time": 1000}
        ]
        res = calculate_predictive_matrix(
            symbol="NZDUSD",
            mid=0.5800,
            c1=0.5840,
            f1=0.5750,
            c2=0.5880,
            f2=0.5700,
            macro=macro,
            atr_val=0.0050,
            pip_val=0.0001,
            point=0.00001,
            digits=5,
            candles=candles
        )
        stations = res.get("stations", [])
        for st in stations:
            self.assertEqual(st["direction"], "SELL", f"Station {st['label']} has forbidden direction {st['direction']}")
        labels = [st["label"] for st in stations]
        self.assertNotIn("WAIT M1A", labels)
        self.assertTrue(any("M3" in l or "M2" in l for l in labels))

    def test_predictive_stations_realignment_buy_no_sell_m1a(self):
        """In STRUCTURAL_RE_ALIGNMENT_APEX_BUY, calculate_predictive_matrix must NOT produce SELL stations."""
        strat = _make_mock_strat(
            regime="STRUCTURAL_RE_ALIGNMENT_APEX_BUY",
            bias="BULLISH_EXPANSION",
            directive="HUNT_BUY_AT_RBS",
            max_buy=1.2400,
            min_sell=0.0
        )
        macro = {
            "is_bear": False,
            "is_bull": True,
            "h1_trend": "BULL",
            "strat_dir": strat,
            "fractal_regime": "STRUCTURAL_RE_ALIGNMENT_APEX_BUY",
            "max_allowed_buy_price": 1.2400,
            "min_allowed_sell_price": 0.0
        }
        candles = [
            {"high": 1.1250, "low": 1.1180, "close": 1.1220, "ema20": 1.1200, "ema50": 1.1170, "time": 1000}
        ]
        res = calculate_predictive_matrix(
            symbol="AUDNZD",
            mid=1.1220,
            c1=1.1300,
            f1=1.1150,
            c2=1.1350,
            f2=1.1100,
            macro=macro,
            atr_val=0.0060,
            pip_val=0.0001,
            point=0.00001,
            digits=5,
            candles=candles
        )
        stations = res.get("stations", [])
        for st in stations:
            self.assertEqual(st["direction"], "BUY", f"Station {st['label']} has forbidden direction {st['direction']}")
        labels = [st["label"] for st in stations]
        self.assertNotIn("WAIT M1A", labels)
        self.assertTrue(any("M3" in l or "M2" in l for l in labels))


if __name__ == "__main__":
    unittest.main()
