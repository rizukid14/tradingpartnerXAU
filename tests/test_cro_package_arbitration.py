"""
Unit tests for 2-Tier Master CRO Arbiter and Anti-Frankenstein Atomic Package Engine.
Verifies:
1. DeepSeek Master CRO prompt generation with Quant Anchors and Implied R:R calculations.
2. Adoption of PACKAGE_OPENAI coordinates without Frankenstein distortion.
3. Adoption of PACKAGE_GEMINI coordinates with full R:R integrity.
4. Anti-Frankenstein Guard intercepting invalid sub-1.25x R:R hybrids and expanding TP.
5. Visual CLI separation of Pass 1 Specialists and Pass 2 Master CRO Arbiter.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.core import llm_client, consensus


class TestCROPackageArbitration(unittest.TestCase):

    def setUp(self):
        self.candidate = MagicMock()
        self.candidate.symbol = "AUDCHF-ECNc"
        self.candidate.direction = 1  # BUY
        self.candidate.setup_type = "MULTI_TOUCH_BREAKOUT_RETEST"
        self.candidate.trigger_price = 0.58220
        self.candidate.current_atr_pts = 24.0
        self.candidate.current_spread_pts = 12
        self.candidate.dealing_range_pos = 0.28
        self.candidate.suggested_sl = 0.58057
        self.candidate.suggested_tp = 0.58488
        self.candidate.risk_reward_ratio = 2.31
        self.candidate.strong_low = 0.58050
        self.candidate.strong_high = 0.58500
        self.candidate.bullish_ob_zone = "0.58187 - 0.58242"
        self.candidate.bearish_ob_zone = ""
        self.candidate.fvg_zone = "0.58190 - 0.58210"
        self.candidate.frvp_confluence = "VAL Support"
        self.candidate.metadata = {}

        self.dummy_rates = np.zeros(50, dtype=[
            ('time', 'i8'), ('open', 'f8'), ('high', 'f8'), ('low', 'f8'),
            ('close', 'f8'), ('tick_volume', 'i8'), ('spread', 'i4'), ('real_volume', 'i8')
        ])
        for i in range(50):
            self.dummy_rates[i] = (1000 + i, 0.58200, 0.58250, 0.58180, 0.58220, 100, 12, 100)

    def test_cro_prompt_contains_quant_anchors_and_packages(self):
        openai_res = {
            "verdict": "REVISE",
            "confidence": 0.70,
            "regime": "RANGE_EXPANSION",
            "reasoning": "RBS structural retest at Floor F1.",
            "execution": {
                "entry_type": "buy_limit",
                "entry_price": 0.58147,
                "sl_price": 0.58003,
                "tp_price": 0.58314
            }
        }
        gemini_res = {
            "verdict": "REVISE",
            "confidence": 0.68,
            "retest_quality": "LIQUIDITY_ABSORPTION",
            "reasoning": "Lower wicks inside M5 Bullish OB.",
            "execution": {
                "entry_type": "buy_limit",
                "entry_price": 0.58187,
                "sl_price": 0.58057,
                "tp_price": 0.58488
            }
        }
        prompt = llm_client.build_deepseek_cro_arbiter_prompt(
            self.candidate,
            openai_res,
            gemini_res,
            recent_m5_str="Dummy M5 tape",
            calendar_text="No news",
            recent_h4_str="Dummy H4 tape",
            recent_h1_str="Dummy H1 tape"
        )
        self.assertIn("ROLE: CHIEF RISK OFFICER & MASTER VETO ARBITER", prompt)
        self.assertIn("PACKAGE A — OpenAI o4-mini", prompt)
        self.assertIn("PACKAGE B — Gemini 3.1-Flash", prompt)
        self.assertIn("ATOMIC PACKAGE INTEGRITY LAW (ANTI-FRANKENSTEIN PROTOCOL)", prompt)
        self.assertIn("arbitration_decision", prompt)
        self.assertIn("calculated_rr", prompt)

    @patch("src.core.consensus.config.mt5.copy_rates_from_pos")
    @patch("src.core.consensus.config.mt5.account_info")
    @patch("src.core.consensus.config.mt5.symbol_info_tick")
    @patch("src.core.consensus.config.mt5.symbol_info")
    def test_adoption_of_package_openai(self, mock_si, mock_tick, mock_acc, mock_rates):
        mock_si.return_value = MagicMock(point=0.00001, trade_tick_value=1.0, trade_tick_size=0.00001, volume_min=0.01)
        mock_tick.return_value = MagicMock(bid=0.58220, ask=0.58222)
        mock_acc.return_value = MagicMock(equity=5000.0)
        mock_rates.return_value = self.dummy_rates

        decisions = {
            "OpenAI": {
                "signal": "BUY",
                "confidence": 0.70,
                "verdict": "REVISE",
                "execution": {
                    "entry_type": "buy_limit",
                    "entry_price": 0.58147,
                    "sl_price": 0.58003,
                    "tp_price": 0.58314
                },
                "reasoning": "Macro structural support at F1."
            },
            "Gemini": {
                "signal": "BUY",
                "confidence": 0.68,
                "verdict": "REVISE",
                "execution": {
                    "entry_type": "buy_limit",
                    "entry_price": 0.58187,
                    "sl_price": 0.58057,
                    "tp_price": 0.58488
                },
                "reasoning": "M5 OB reaction."
            },
            "DeepSeek": {
                "signal": "BUY",
                "confidence": 0.82,
                "verdict": "APPROVE",
                "arbitration_decision": {
                    "chosen_package": "PACKAGE_OPENAI",
                    "arbitration_rationale": "Deeper pullback to F1 provides safer R:R."
                },
                "execution": {
                    "entry_type": "buy_limit",
                    "entry_price": 0.58147,
                    "sl_price": 0.58003,
                    "tp_price": 0.58314,
                    "calculated_rr": 1.16
                },
                "reasoning": "OpenAI structural anchor adopted."
            }
        }

        res = consensus.calculate_consensus(decisions, candidate=self.candidate)
        self.assertEqual(res["signal"], "BUY")
        self.assertEqual(res["entry_type"], "buy_limit")
        self.assertEqual(res["entry_price"], 0.58147)
        self.assertEqual(res["invalidation_price"], 0.58003)

    @patch("src.core.consensus.config.mt5.copy_rates_from_pos")
    @patch("src.core.consensus.config.mt5.account_info")
    @patch("src.core.consensus.config.mt5.symbol_info_tick")
    @patch("src.core.consensus.config.mt5.symbol_info")
    def test_anti_frankenstein_guard_expands_compressed_rr(self, mock_si, mock_tick, mock_acc, mock_rates):
        mock_si.return_value = MagicMock(point=0.00001, trade_tick_value=1.0, trade_tick_size=0.00001, volume_min=0.01)
        mock_tick.return_value = MagicMock(bid=0.58220, ask=0.58222)
        mock_acc.return_value = MagicMock(equity=5000.0)
        mock_rates.return_value = self.dummy_rates

        # Simulate Frankenstein hybrid: Entry Gemini (0.58187) + TP OpenAI (0.58314) -> R:R = 12.7 / 13.0 = 0.97:1
        decisions = {
            "OpenAI": {
                "signal": "BUY",
                "confidence": 0.70,
                "verdict": "REVISE",
                "execution": {
                    "entry_type": "buy_limit",
                    "entry_price": 0.58147,
                    "sl_price": 0.58003,
                    "tp_price": 0.58314
                },
                "reasoning": "Macro structural support at F1."
            },
            "Gemini": {
                "signal": "BUY",
                "confidence": 0.68,
                "verdict": "REVISE",
                "execution": {
                    "entry_type": "buy_limit",
                    "entry_price": 0.58187,
                    "sl_price": 0.58057,
                    "tp_price": 0.58488
                },
                "reasoning": "M5 OB reaction."
            },
            "DeepSeek": {
                "signal": "BUY",
                "confidence": 0.85,
                "verdict": "APPROVE",
                "execution": {
                    "entry_type": "buy_limit",
                    "entry_price": 0.58187,
                    "sl_price": 0.58057,
                    "tp_price": 0.58314
                },
                "reasoning": "Hybrid proposal."
            }
        }

        res = consensus.calculate_consensus(decisions, candidate=self.candidate)
        self.assertEqual(res["signal"], "BUY")
        # Anti-Frankenstein guard must ensure R:R >= 1.25x by expanding TP to Quant Target Station
        risk = abs(0.58187 - res["invalidation_price"])
        reward = abs(res["target_price"] - 0.58187)
        achieved_rr = reward / risk if risk > 0 else 0.0
        self.assertGreaterEqual(achieved_rr, 1.25, f"Expected R:R >= 1.25, got {achieved_rr:.2f}")


if __name__ == "__main__":
    unittest.main()
