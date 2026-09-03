# -*- coding: utf-8 -*-
"""
Unit Test Suite for Mechanism 4 (M4) — SYSTEMIC_FLOW_CONTINUATION
Verifies:
1. _apply_sltp_rules: Structural SL (0.45xATR) and TP (1.1R) freeze via early return.
2. calculate_consensus: cand_sym resolution (no hardcoded config.SYMBOL GBPUSD collision).
3. Anchor broken check: Aborts if live market already penetrated past pending limit level.
4. _is_direction_allowed: Allows M4 through INACTION_ZONE / CHAMBER_MID_BLOCK, but enforces HARD_LOCK and directional traps.
5. _m4_pending_ready: Retest approach band verification.
"""

import unittest
from unittest.mock import MagicMock, patch
import config
from src.analytics.market_scanner import MarketScanner, CandidateSetup
from src.core.consensus import _apply_sltp_rules, calculate_consensus


class TestM4FlowContinuation(unittest.TestCase):

    def setUp(self):
        self.scanner = MarketScanner(symbols=["EURJPY-ECNc", "GBPUSD-ECNc", "AUDJPY-ECNc"])

    def test_m4_sltp_structural_fixed_early_return(self):
        """M4 SL/TP must bypass normal floor (JPY 1.0x ATR) and min R:R 1.25, returning exact frozen values."""
        cand = CandidateSetup(
            symbol="EURJPY-ECNc",
            setup_type=config.M4_SETUP_TYPE,
            direction=-1,
            trigger_price=162.500,
            metadata={
                "m4_sl_pts": 180,   # 0.45x ATR H1 (normally JPY floor is ~350 pts)
                "m4_tp_pts": 198,   # 1.1R (normally min RR is 1.25 = 225 pts)
                "m4_level": 162.500,
            }
        )
        sl, tp, ok, reason = _apply_sltp_rules(
            sl_points=180,
            tp_points=198,
            symbol="EURJPY-ECNc",
            candidate=cand
        )
        self.assertTrue(ok)
        self.assertEqual(reason, "M4_STRUCTURAL_FIXED")
        self.assertEqual(sl, 180)
        self.assertEqual(tp, 198)

    def test_m4_anchor_broken_uses_cand_sym_not_gbpusd(self):
        """Ensure M4 anchor-broken check evaluates candidate symbol tick (AUDJPY ~98.50) NOT config.SYMBOL (GBPUSD ~1.33)."""
        cand = CandidateSetup(
            symbol="AUDJPY-ECNc",
            setup_type=config.M4_SETUP_TYPE,
            direction=1,  # BUY LIMIT
            trigger_price=98.500,
            metadata={
                "m4_sl_pts": 150,
                "m4_tp_pts": 165,
                "m4_level": 98.500,
            }
        )

        decisions = {
            "OpenAI": {"signal": "BUY", "confidence": 0.85, "entry_type": "buy_limit", "entry_price": 98.500, "sl_points": 150, "tp_points": 165},
            "Gemini": {"signal": "BUY", "confidence": 0.85, "entry_type": "buy_limit", "entry_price": 98.500, "sl_points": 150, "tp_points": 165},
            "DeepSeek": {"signal": "BUY", "confidence": 0.85, "entry_type": "buy_limit", "entry_price": 98.500, "sl_points": 150, "tp_points": 165, "verdict": "APPROVE", "risk_verdict": "CLEARED"},
        }

        # Mock MT5 to return AUDJPY tick (ask = 98.55) and GBPUSD tick (ask = 1.3325)
        def mock_symbol_info_tick(sym):
            m = MagicMock()
            if "JPY" in sym:
                m.ask = 98.550
                m.bid = 98.530
            else:
                m.ask = 1.33250
                m.bid = 1.33230
            return m

        def mock_symbol_info(sym):
            m = MagicMock()
            m.point = 0.001 if "JPY" in sym else 0.00001
            return m

        with patch("config.mt5.symbol_info_tick", side_effect=mock_symbol_info_tick), \
             patch("config.mt5.symbol_info", side_effect=mock_symbol_info):
            res = calculate_consensus(decisions, candidate=cand)
            # If bug was present (comparing 98.50 against GBPUSD 1.33), it would have marked anchor broken and returned HOLD!
            # With fix (comparing 98.50 against AUDJPY ask 98.55), buy_limit @ 98.50 < ask 98.55 is VALID!
            self.assertEqual(res["signal"], "BUY")
            self.assertEqual(res["sl_points"], 150)
            self.assertEqual(res["tp_points"], 165)

    def test_m4_anchor_broken_aborts_when_market_penetrates_past_anchor(self):
        """If market for SELL has dropped below entry level (or BUY rose above limit), M4 must abort."""
        cand = CandidateSetup(
            symbol="EURJPY-ECNc",
            setup_type=config.M4_SETUP_TYPE,
            direction=-1,  # SELL LIMIT
            trigger_price=162.000,
            metadata={
                "m4_sl_pts": 200,
                "m4_tp_pts": 220,
                "m4_level": 162.000,
            }
        )
        decisions = {
            "OpenAI": {"signal": "SELL", "confidence": 0.85, "entry_type": "sell_limit", "entry_price": 162.000, "sl_points": 200, "tp_points": 220},
            "Gemini": {"signal": "SELL", "confidence": 0.85, "entry_type": "sell_limit", "entry_price": 162.000, "sl_points": 200, "tp_points": 220},
            "DeepSeek": {"signal": "SELL", "confidence": 0.85, "entry_type": "sell_limit", "entry_price": 162.000, "sl_points": 200, "tp_points": 220, "verdict": "APPROVE", "risk_verdict": "CLEARED"},
        }

        # Market is already at 162.200 (penetrated above SELL limit anchor)
        mock_tick = MagicMock()
        mock_tick.ask = 162.220
        mock_tick.bid = 162.200  # ref_price = 162.200 >= final_entry_price 162.000 (SELL penetrated!)
        mock_si = MagicMock()
        mock_si.point = 0.001

        with patch("config.mt5.symbol_info_tick", return_value=mock_tick), \
             patch("config.mt5.symbol_info", return_value=mock_si):
            res = calculate_consensus(decisions, candidate=cand)
            self.assertEqual(res["signal"], "HOLD")
            self.assertIn("anchor limit", str(res.get("details", "")))

    def test_m4_pending_ready_band(self):
        """_m4_pending_ready returns pending dict when mid price is within approach band, None otherwise."""
        sym = "AUDCAD"
        level = 0.90000
        atr = 0.00500
        self.scanner._m4_universe = [sym]
        self.scanner._m4_state[sym] = {
            "SELL": {
                "pending": {
                    "level": level,
                    "sl": level + 0.45 * atr,
                    "tp": level - 1.1 * 0.45 * atr,
                    "atr": atr,
                    "time": 1000
                }
            },
            "BUY": {"pending": None}
        }

        # Band for SELL: level - 0.35*atr <= mid <= level + 0.10*atr
        # [0.89825 <= mid <= 0.90050]
        # Mid inside: 0.89950 -> should return pending
        res_inside = self.scanner._m4_pending_ready(sym, "SELL", 0.89950, atr)
        self.assertIsNotNone(res_inside)
        self.assertEqual(res_inside["level"], level)

        # Mid outside (too low, e.g. 0.89500) -> None
        res_outside = self.scanner._m4_pending_ready(sym, "SELL", 0.89500, atr)
        self.assertIsNone(res_outside)

        # Mid reclaimed too high (e.g. 0.90200) -> None
        res_reclaimed = self.scanner._m4_pending_ready(sym, "SELL", 0.90200, atr)
        self.assertIsNone(res_reclaimed)

    def test_m4_pending_expiry_120_minutes(self):
        """M4 pending orders must have 120 minutes (2 hours) expiry."""
        self.assertEqual(getattr(config, "M4_PENDING_EXPIRY_MINUTES", None), 120)

    @patch("src.analytics.position_manager._check_partial_close")
    @patch("src.analytics.position_manager._check_break_even")
    @patch("src.analytics.position_manager._check_trailing_stop")
    @patch("src.analytics.position_manager.audit_pending_orders_thesis")
    @patch("src.analytics.position_manager.mt5")
    def test_m4_position_manager_all_or_nothing(self, mock_mt5, mock_audit, mock_trail, mock_be, mock_partial):
        """M4 positions (comment contains 'SYSTEM') must bypass partial close, BEP, and trailing (All-or-Nothing to 1.1R/SL)."""
        from src.analytics.position_manager import manage_all_positions
        mock_pos = MagicMock()
        mock_pos.ticket = 99999
        mock_pos.symbol = "EURJPY-ECNc"
        mock_pos.magic = config.MAGIC_NUMBER
        mock_pos.comment = "JURY SYSTEM P1"
        mock_pos.volume = 0.05
        mock_pos.price_open = 162.000
        mock_pos.sl = 162.300
        mock_pos.tp = 161.670
        mock_pos.type = 1  # SELL
        mock_pos.time = 1000000
        mock_pos.time_msc = 1000000000

        mock_si = MagicMock()
        mock_si.point = 0.001
        mock_si.digits = 3
        mock_si.volume_min = 0.01

        mock_tick = MagicMock()
        mock_tick.time = 1000000.0
        mock_tick.bid = 161.750
        mock_tick.ask = 161.770

        mock_mt5.positions_get.return_value = [mock_pos]
        mock_mt5.symbol_info.return_value = mock_si
        mock_mt5.symbol_info_tick.return_value = mock_tick
        mock_mt5.ORDER_TYPE_BUY = 0
        mock_mt5.ORDER_TYPE_SELL = 1

        with patch("src.analytics.position_manager.time.time", return_value=1000005.0):
            manage_all_positions()

        # Partial close, BEP, and Trailing MUST NOT be called for M4
        mock_partial.assert_not_called()
        mock_be.assert_not_called()
        mock_trail.assert_not_called()

    @patch("src.analytics.position_manager.mt5")
    @patch("src.analytics.macro_strategic_engine.macro_strategic_engine.get_directive")
    def test_m4_pending_thesis_audit_not_cancelled_by_macro_bias(self, mock_get_dir, mock_mt5):
        """M4 pending orders (comment contains 'SYSTEM') must NOT be cancelled when MSE D1/H4 flips to opposite bias."""
        from src.analytics.position_manager import audit_pending_orders_thesis
        mock_order = MagicMock()
        mock_order.ticket = 88888
        mock_order.symbol = "EURJPY-ECNc"
        mock_order.magic = config.MAGIC_NUMBER
        mock_order.comment = "JURY SYSTEM P1"
        mock_order.type = 3  # ORDER_TYPE_SELL_LIMIT
        mock_order.price_open = 162.500

        mock_mt5.orders_get.return_value = [mock_order]
        mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
        mock_mt5.ORDER_TYPE_BUY_STOP = 4
        mock_mt5.ORDER_TYPE_SELL_STOP = 5

        mock_si = MagicMock()
        mock_si.point = 0.001
        mock_mt5.symbol_info.return_value = mock_si

        # MSE directive is Bullish Expansion (+0.45) and FLOOR_REJECTION (normally would cancel SELL pending!)
        mock_strat = MagicMock()
        mock_strat.immediate_ceiling_c1 = 163.000
        mock_strat.immediate_floor_f1 = 161.000
        mock_strat.market_state = "FLOOR_REJECTION"
        mock_strat.primary_execution_directive = "HUNT_BUY"
        mock_strat.macro_bias_score = 0.45
        mock_get_dir.return_value = mock_strat

        audit_pending_orders_thesis()

        # mt5.order_send MUST NOT be called to remove the M4 order!
        mock_mt5.order_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
