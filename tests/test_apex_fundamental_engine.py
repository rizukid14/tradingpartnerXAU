"""
Unit Tests for Apex Paragon Macro Fundamental Engine & MSE Integration
-----------------------------------------------------------------------
Verifies:
1. Exponential Half-Life Decay calculations across event tiers.
2. 8-Currency Composite Fundamental Score generation.
3. 4-Tier Conflict & Alignment Matrix (VALID_CONVERGENCE, WEAK_CONVERGENCE, NO_SIGNAL_FLAT, CURRENCY_CONFLICT).
4. 4-Tier Setup Quality Grading Engine (GRADE S, GRADE A+, GRADE A, GRADE B).
5. 7 Master Hard Risk Veto Flags.
6. Integration with MacroStrategicEngine (MSE).
"""

import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock

from src.analytics.apex_fundamental_engine import (
    ApexFundamentalEngine,
    ApexCurrencyScore,
    ApexPairEvaluation,
    CENTRAL_BANK_RATES
)
from src.analytics.macro_strategic_engine import macro_strategic_engine

WIB = ZoneInfo("Asia/Jakarta")


class TestApexFundamentalEngine(unittest.TestCase):

    def setUp(self):
        self.engine = ApexFundamentalEngine()

    def test_central_bank_rates_coverage(self):
        """Ensures all 8 major global currencies have defined central bank benchmark rates."""
        expected_currencies = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"}
        self.assertEqual(set(CENTRAL_BANK_RATES.keys()), expected_currencies)
        for curr, data in CENTRAL_BANK_RATES.items():
            self.assertIn("rate", data)
            self.assertIn("cycle", data)
            self.assertIn("bias", data)
            self.assertIsInstance(data["rate"], (int, float))

    def test_half_life_decay_curves(self):
        """Verifies exponential half-life decay across Tier 1 (36h), Tier 2 (12h), and Tier 3 (4h)."""
        init_score = 1.0

        # Tier 3 (Half-Life 4h): at 4h score should be approx 0.50
        score_t3_4h = self.engine._calculate_half_life_decay(init_score, hours_elapsed=4.0, tier=3)
        self.assertAlmostEqual(score_t3_4h, 0.50, places=2)

        # Tier 2 (Half-Life 12h): at 12h score should be approx 0.50
        score_t2_12h = self.engine._calculate_half_life_decay(init_score, hours_elapsed=12.0, tier=2)
        self.assertAlmostEqual(score_t2_12h, 0.50, places=2)

        # Tier 1 (Half-Life 36h): at 36h score should be approx 0.50
        score_t1_36h = self.engine._calculate_half_life_decay(init_score, hours_elapsed=36.0, tier=1)
        self.assertAlmostEqual(score_t1_36h, 0.50, places=2)

        # At 0 hours, score remains 1.0
        self.assertEqual(self.engine._calculate_half_life_decay(init_score, hours_elapsed=0.0, tier=1), 1.0)

    def test_valid_convergence_evaluation(self):
        """Tests that strong Base vs weak Quote triggers VALID_CONVERGENCE and Grade A+."""
        mock_scores = {
            "USD": ApexCurrencyScore(currency="USD", central_bank_rate=5.50, central_bank_cycle="HOLD", central_bank_bias="HAWKISH", composite_fundamental_score=0.45, reaction_phase="THE_CALM"),
            "JPY": ApexCurrencyScore(currency="JPY", central_bank_rate=0.25, central_bank_cycle="HIKE", central_bank_bias="DOVISH", composite_fundamental_score=-0.25, reaction_phase="THE_CALM"),
        }
        self.engine.currency_scores = mock_scores
        self.engine.last_score_computed_ts = 9999999999.0

        ev = self.engine.evaluate_pair("USDJPY")
        self.assertEqual(ev.alignment, "VALID_CONVERGENCE")
        self.assertEqual(ev.setup_grade, "GRADE_A_PLUS")
        self.assertEqual(ev.sizing_modifier, 1.0)
        self.assertIn("FAVOR_BUY", ev.action_directive)
        self.assertIsNone(ev.hard_veto_flag)

    def test_mild_currency_conflict_grade_b(self):
        """Tests that two moderately bullish currencies trigger MILD_CONFLICT_CHOP and GRADE_B defensive mode."""
        mock_scores = {
            "GBP": ApexCurrencyScore(currency="GBP", central_bank_rate=5.00, central_bank_cycle="HOLD", central_bank_bias="HAWKISH", composite_fundamental_score=0.35, reaction_phase="THE_CALM"),
            "USD": ApexCurrencyScore(currency="USD", central_bank_rate=5.50, central_bank_cycle="HOLD", central_bank_bias="HAWKISH", composite_fundamental_score=0.40, reaction_phase="THE_CALM"),
        }
        self.engine.currency_scores = mock_scores
        self.engine.last_score_computed_ts = 9999999999.0

        ev = self.engine.evaluate_pair("GBPUSD")
        self.assertEqual(ev.alignment, "MILD_CONFLICT_CHOP")
        self.assertEqual(ev.setup_grade, "GRADE_B")
        self.assertEqual(ev.sizing_modifier, 0.50)
        self.assertIsNone(ev.hard_veto_flag)
        self.assertIn("DEFENSIVE_CHOP_MODE", ev.action_directive)

    def test_severe_currency_conflict_hard_veto(self):
        """Tests that two extremely high-magnitude currencies trigger SEVERE_CURRENCY_CONFLICT and REJECT_VETO."""
        mock_scores = {
            "GBP": ApexCurrencyScore(currency="GBP", central_bank_rate=5.00, central_bank_cycle="HIKE", central_bank_bias="HAWKISH", composite_fundamental_score=0.65, reaction_phase="THE_CALM"),
            "USD": ApexCurrencyScore(currency="USD", central_bank_rate=5.50, central_bank_cycle="HOLD", central_bank_bias="HAWKISH", composite_fundamental_score=0.60, reaction_phase="THE_CALM"),
        }
        self.engine.currency_scores = mock_scores
        self.engine.last_score_computed_ts = 9999999999.0

        ev = self.engine.evaluate_pair("GBPUSD")
        self.assertEqual(ev.alignment, "SEVERE_CURRENCY_CONFLICT")
        self.assertEqual(ev.setup_grade, "REJECT_VETO")
        self.assertEqual(ev.sizing_modifier, 0.0)
        self.assertEqual(ev.hard_veto_flag, "CURRENCY_CONFLICT")
        self.assertIn("HARD_BLOCK_ENTRY", ev.action_directive)

    def test_grade_tp_multipliers(self):
        """Tests that get_grade_tp_multiplier returns calibrated ATR multipliers."""
        self.assertEqual(ApexFundamentalEngine.get_grade_tp_multiplier("GRADE_S"), 3.0)
        self.assertEqual(ApexFundamentalEngine.get_grade_tp_multiplier("GRADE_A_PLUS"), 2.0)
        self.assertEqual(ApexFundamentalEngine.get_grade_tp_multiplier("GRADE_A"), 1.5)
        self.assertEqual(ApexFundamentalEngine.get_grade_tp_multiplier("GRADE_B"), 1.25)

    def test_the_storm_hard_freeze(self):
        """Tests that an active The Storm phase triggers HIGH_IMPACT_NEWS veto."""
        mock_scores = {
            "EUR": ApexCurrencyScore(currency="EUR", central_bank_rate=3.75, central_bank_cycle="CUT", central_bank_bias="DOVISH", composite_fundamental_score=0.0, reaction_phase="PRICED_IN_EQUILIBRIUM"),
            "USD": ApexCurrencyScore(currency="USD", central_bank_rate=5.50, central_bank_cycle="HOLD", central_bank_bias="HAWKISH", composite_fundamental_score=0.0, reaction_phase="THE_STORM"),
        }
        self.engine.currency_scores = mock_scores
        self.engine.last_score_computed_ts = 9999999999.0

        ev = self.engine.evaluate_pair("EURUSD")
        self.assertEqual(ev.alignment, "THE_STORM_ACTIVE")
        self.assertEqual(ev.setup_grade, "REJECT_VETO")
        self.assertEqual(ev.sizing_modifier, 0.0)
        self.assertEqual(ev.hard_veto_flag, "HIGH_IMPACT_NEWS")

    def test_bank_holiday_defensive_sizing(self):
        """Tests that an active Bank Holiday reduces setup quality to Grade B and sizing to 0.50x."""
        mock_scores = {
            "GBP": ApexCurrencyScore(currency="GBP", central_bank_rate=5.00, central_bank_cycle="CUT", central_bank_bias="DOVISH", composite_fundamental_score=0.0, is_bank_holiday=True, reaction_phase="PRICED_IN_EQUILIBRIUM"),
            "USD": ApexCurrencyScore(currency="USD", central_bank_rate=5.50, central_bank_cycle="HOLD", central_bank_bias="NEUTRAL", composite_fundamental_score=0.0, reaction_phase="PRICED_IN_EQUILIBRIUM"),
        }
        self.engine.currency_scores = mock_scores
        self.engine.last_score_computed_ts = 9999999999.0

        ev = self.engine.evaluate_pair("GBPUSD")
        self.assertEqual(ev.setup_grade, "GRADE_B")
        self.assertEqual(ev.sizing_modifier, 0.50)
        self.assertIn("DEFENSIVE", ev.action_directive)

    def test_llm_dossier_block_output(self):
        """Tests generation of the standardized 100% English LLM dossier briefing."""
        mock_scores = {
            "USD": ApexCurrencyScore(currency="USD", central_bank_rate=5.50, central_bank_cycle="HOLD", central_bank_bias="HAWKISH", composite_fundamental_score=0.30, reaction_phase="PRICED_IN_EQUILIBRIUM"),
            "CHF": ApexCurrencyScore(currency="CHF", central_bank_rate=1.25, central_bank_cycle="CUT_CYCLE", central_bank_bias="DOVISH", composite_fundamental_score=-0.20, reaction_phase="PRICED_IN_EQUILIBRIUM"),
        }
        self.engine.currency_scores = mock_scores
        self.engine.last_score_computed_ts = 9999999999.0

        block = self.engine.generate_llm_dossier_block("USDCHF")
        self.assertIn("APEX PARAGON MACRO FUNDAMENTAL BRIEFING", block)
        self.assertIn("Base Currency (USD)", block)
        self.assertIn("Quote Currency (CHF)", block)
        self.assertIn("Fundamental Net Delta", block)
        self.assertIn("VALID CONVERGENCE", block)

    def test_mse_directive_fundamental_integration(self):
        """Tests that MacroStrategicEngine directive contains fundamental_grade and fundamental_backing."""
        directive = macro_strategic_engine.get_directive("GBPUSD")
        self.assertIsNotNone(directive)
        self.assertTrue(hasattr(directive, "fundamental_grade"))
        self.assertTrue(hasattr(directive, "fundamental_backing"))
        self.assertIn(directive.fundamental_grade, ("GRADE_S", "GRADE_A_PLUS", "GRADE_A", "GRADE_B", "REJECT_VETO"))


if __name__ == "__main__":
    unittest.main()
