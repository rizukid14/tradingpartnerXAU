import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.consensus import calculate_2d_confluence_tier, _apply_sltp_rules


class Test2DConfluenceAndThesisInvalidation(unittest.TestCase):

    def test_apex_super_conviction_tier(self):
        """Quant S + AI >= 80% -> APEX_SUPER_CONVICTION (1.25x lot, Split 2 tickets)"""
        decisions = {
            "OpenAI": {"verdict": "PASS", "confidence": 0.85, "signal": "BUY"},
            "Gemini": {"verdict": "PASS", "confidence": 0.85, "signal": "BUY"},
            "DeepSeek": {"verdict": "APPROVE", "confidence": 0.85, "signal": "BUY", "risk_verdict": "CLEARED"}
        }
        res = calculate_2d_confluence_tier("GRADE_S", decisions)
        self.assertEqual(res["tier"], "APEX_SUPER_CONVICTION")
        self.assertEqual(res["sizing_multiplier"], 1.25)
        self.assertTrue(res["is_split_ticket"])
        self.assertEqual(res["tp_mode"], "EXTENDED_RUNNER")
        self.assertEqual(res["status"], "EXECUTE")

    def test_high_conviction_tier(self):
        """Quant A + AI >= 80% -> HIGH_CONVICTION (1.0x lot)"""
        decisions = {
            "OpenAI": {"verdict": "PASS", "confidence": 0.85, "signal": "BUY"},
            "Gemini": {"verdict": "PASS", "confidence": 0.80, "signal": "BUY"},
            "DeepSeek": {"verdict": "APPROVE", "confidence": 0.80, "signal": "BUY", "risk_verdict": "CLEARED"}
        }
        res = calculate_2d_confluence_tier("GRADE_A", decisions)
        self.assertEqual(res["tier"], "HIGH_CONVICTION")
        self.assertEqual(res["sizing_multiplier"], 1.00)
        self.assertFalse(res["is_split_ticket"])
        self.assertEqual(res["status"], "EXECUTE")

    def test_standard_trade_tier(self):
        """Quant A + AI 70-79% -> STANDARD_TRADE (1.0x lot)"""
        decisions = {
            "OpenAI": {"verdict": "PASS", "confidence": 0.75, "signal": "BUY"},
            "Gemini": {"verdict": "PASS", "confidence": 0.72, "signal": "BUY"},
            "DeepSeek": {"verdict": "APPROVE", "confidence": 0.70, "signal": "BUY", "risk_verdict": "CLEARED"}
        }
        res = calculate_2d_confluence_tier("GRADE_A", decisions)
        self.assertEqual(res["tier"], "STANDARD_TRADE")
        self.assertEqual(res["sizing_multiplier"], 1.00)
        self.assertEqual(res["status"], "EXECUTE")

    def test_reduced_scalp_half_risk_tier(self):
        """AI Caution 60-69% -> REDUCED_SCALP (0.50x half lot, tight TP1 only)"""
        decisions = {
            "OpenAI": {"verdict": "PASS", "confidence": 0.80, "signal": "BUY"},
            "Gemini": {"verdict": "CAUTION", "confidence": 0.65, "signal": "BUY"},
            "DeepSeek": {"verdict": "APPROVE", "confidence": 0.60, "signal": "BUY", "risk_verdict": "CLEARED"}
        }
        res = calculate_2d_confluence_tier("GRADE_A", decisions)
        self.assertEqual(res["tier"], "REDUCED_SCALP")
        self.assertEqual(res["sizing_multiplier"], 0.50)
        self.assertEqual(res["tp_mode"], "TIGHT_TP1_ONLY")
        self.assertEqual(res["status"], "EXECUTE")

    def test_skip_noise_tier(self):
        """Quant B + AI 60-69% -> SKIP_NOISE (0.0x / VETO)"""
        decisions = {
            "OpenAI": {"verdict": "PASS", "confidence": 0.65, "signal": "BUY"},
            "Gemini": {"verdict": "CAUTION", "confidence": 0.65, "signal": "BUY"},
            "DeepSeek": {"verdict": "APPROVE", "confidence": 0.65, "signal": "BUY", "risk_verdict": "CLEARED"}
        }
        res = calculate_2d_confluence_tier("GRADE_B", decisions)
        self.assertEqual(res["tier"], "SKIP_NOISE")
        self.assertEqual(res["sizing_multiplier"], 0.0)
        self.assertEqual(res["status"], "VETO_NOISE")

    def test_hard_reject_tier(self):
        """Any Model REJECT -> SKIP_VETO (0.0x / VETO)"""
        decisions = {
            "OpenAI": {"verdict": "PASS", "confidence": 0.90, "signal": "BUY"},
            "Gemini": {"verdict": "REJECT", "confidence": 0.30, "signal": "HOLD"},
            "DeepSeek": {"verdict": "APPROVE", "confidence": 0.80, "signal": "BUY", "risk_verdict": "CLEARED"}
        }
        res = calculate_2d_confluence_tier("GRADE_S", decisions)
        self.assertEqual(res["tier"], "SKIP_VETO")
        self.assertEqual(res["sizing_multiplier"], 0.0)
        self.assertEqual(res["status"], "VETO")

    def test_tight_sltp_rules_for_reduced_scalp(self):
        """Verify that REDUCED_SCALP caps TP at max 1.25x SL (Tight Scalp)"""
        import config
        with patch.object(config, "ZCE_ENABLED", False), patch.object(config, "ZCE_MODE", "shadow"):
            sl, tp, ok, reason = _apply_sltp_rules(
                sl_points=100,
                tp_points=800,
                symbol="EURUSD-ECNc",
                action_tier="REDUCED_SCALP",
                setup_grade="GRADE_B"
            )
        self.assertTrue(ok)
        # Should be clamped to max 1.25x of floored SL
        self.assertLessEqual(tp, int(sl * 1.25))


if __name__ == "__main__":
    unittest.main()
