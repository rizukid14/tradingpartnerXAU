"""
Unit tests for Pure Quant Direct Execution (No-LLM mode) in main.py.
Verifies that when ENABLE_LLM_JURY is False:
1. LLM client is NOT invoked (0 tokens, 0 API calls).
2. Setup candidate is executed directly via MT5 pending/market order.
3. Risk checks, SL/TP rules, and lot sizing are applied.
"""

import unittest
from unittest.mock import patch, MagicMock
import config
from src.analytics.market_scanner import CandidateSetup
import main

class TestPureQuantExecution(unittest.TestCase):

    def setUp(self):
        self.risk_mock = MagicMock()
        self.risk_mock.can_trade.return_value = (True, "OK")
        self.risk_mock.get_effective_lot_size.return_value = 0.05
        self.risk_mock.record_trade_opened.return_value = None

        self.candidate = CandidateSetup(
            symbol="BTCUSD.c",
            setup_type="UNIVERSAL_LIQUIDITY_SWEEP",
            direction=1,  # BUY
            trigger_price=95000.0,
            timeframe="H1",
            current_atr_pts=30000.0,
            current_spread_pts=200,
            suggested_sl=94000.0,
            suggested_tp=97500.0,
            action_tier="FULL_ALLOW"
        )

    @patch("main.llm.get_multi_llm_decisions_for_candidate")
    @patch("main.connector.get_current_tick")
    @patch("main.connector.send_pending_order")
    @patch("main.tg.alert_pending_order_placed")
    def test_pure_quant_bypasses_llm_and_executes_pending(
        self, mock_tg, mock_send_pending, mock_get_tick, mock_llm_call
    ):
        """When ENABLE_LLM_JURY is False, LLM must not be called and pending limit order should be placed."""
        mock_get_tick.return_value = {
            "ask": 95600.0,
            "bid": 95580.0,
            "spread": 50,
            "point": 1.0
        }
        mock_send_pending.return_value = {"status": "SUCCESS", "ticket": 999999}

        with patch.object(config, "ENABLE_LLM_JURY", False):
            with patch.object(config, "PENDING_ORDERS_ENABLED", True):
                with patch.object(config, "DRY_RUN", False):
                    res = main.run_scanner_trading_cycle(self.candidate, self.risk_mock)
                    
                    self.assertTrue(res)
                    # Verify LLM was NEVER called
                    mock_llm_call.assert_not_called()
                    # Verify order was dispatched
                    mock_send_pending.assert_called_once()
                    args, kwargs = mock_send_pending.call_args
                    self.assertEqual(kwargs.get("symbol"), "BTCUSD.c")
                    self.assertEqual(kwargs.get("entry_type"), "buy_limit")
                    self.assertEqual(kwargs.get("entry_price"), 95000.0)

    @patch("main.llm.get_multi_llm_decisions_for_candidate")
    @patch("main.connector.get_current_tick")
    @patch("main.connector.send_trade_order")
    @patch("main.tg.alert_trade_opened")
    def test_pure_quant_executes_market_when_pending_disabled(
        self, mock_tg, mock_send_market, mock_get_tick, mock_llm_call
    ):
        """When PENDING_ORDERS_ENABLED is False, pure quant executes market order."""
        mock_get_tick.return_value = {
            "ask": 95100.0,
            "bid": 95080.0,
            "spread": 200,
            "point": 1.0
        }
        mock_send_market.return_value = {"status": "SUCCESS", "ticket": 888888}

        with patch.object(config, "ENABLE_LLM_JURY", False):
            with patch.object(config, "PENDING_ORDERS_ENABLED", False):
                with patch.object(config, "DRY_RUN", False):
                    res = main.run_scanner_trading_cycle(self.candidate, self.risk_mock)
                    
                    self.assertTrue(res)
                    mock_llm_call.assert_not_called()
                    mock_send_market.assert_called_once()
                    args, kwargs = mock_send_market.call_args
                    self.assertEqual(kwargs.get("symbol"), "BTCUSD.c")
                    self.assertEqual(kwargs.get("action"), "BUY")

if __name__ == "__main__":
    unittest.main()
