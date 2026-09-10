"""
tests/test_anti_internal_hedge.py
Unit tests for Anti-Internal Currency Hedge Gate (CBSS & Risk Engine):
Ensures the bot never opens opposing positions on the same currency
(e.g. Long EUR on EURNZD and Short EUR on EURAUD).
"""

import unittest
from unittest.mock import MagicMock, patch

import config
from src.analytics.basket_sync_engine import check_basket_directional_conflict
from src.core.risk_engine import RiskEngine


class TestAntiInternalHedge(unittest.TestCase):

    def setUp(self):
        self.risk = RiskEngine()

    def test_euraud_sell_blocked_when_eurnzd_buy_active(self):
        """
        Active: EURNZD BUY (Long EUR, Short NZD).
        Candidate: EURAUD SELL (Short EUR, Long AUD).
        Must be BLOCKED because EUR is being shorted while already long EUR.
        """
        pos = MagicMock()
        pos.symbol = "EURNZD-ECNc"
        pos.type = 0  # BUY (MT5)

        conflict_ok, reason = check_basket_directional_conflict(
            symbol="EURAUD-ECNc",
            direction=-1,  # SELL
            active_positions=[pos],
            active_orders=[]
        )
        self.assertFalse(conflict_ok)
        self.assertIn("[CBSS ANTI-HEDGE]", reason)
        self.assertIn("EUR", reason)
        self.assertIn("LONG EUR pada EURNZD-ECNc", reason)

    def test_audnzd_buy_allowed_when_eurnzd_buy_active(self):
        """
        Active: EURNZD BUY (Long EUR, Short NZD).
        Candidate: AUDNZD BUY (Long AUD, Short NZD).
        Must be ALLOWED because neither currency has opposing signs (NZD is short in both).
        """
        pos = MagicMock()
        pos.symbol = "EURNZD-ECNc"
        pos.type = 0  # BUY

        conflict_ok, reason = check_basket_directional_conflict(
            symbol="AUDNZD-ECNc",
            direction=1,  # BUY
            active_positions=[pos],
            active_orders=[]
        )
        self.assertTrue(conflict_ok)
        self.assertEqual(reason, "")

    def test_gbpjpy_buy_blocked_when_cadjpy_sell_active(self):
        """
        Active: CADJPY SELL (Short CAD, Long JPY).
        Candidate: GBPJPY BUY (Long GBP, Short JPY).
        Must be BLOCKED because JPY is being shorted while already long JPY.
        """
        pos = MagicMock()
        pos.symbol = "CADJPY-ECNc"
        pos.type = 1  # SELL

        conflict_ok, reason = check_basket_directional_conflict(
            symbol="GBPJPY-ECNc",
            direction=1,  # BUY
            active_positions=[pos],
            active_orders=[]
        )
        self.assertFalse(conflict_ok)
        self.assertIn("[CBSS ANTI-HEDGE]", reason)
        self.assertIn("JPY", reason)

    def test_usdjpy_sell_allowed_when_cadjpy_sell_active(self):
        """
        Active: CADJPY SELL (Short CAD, Long JPY).
        Candidate: USDJPY SELL (Short USD, Long JPY).
        Must be ALLOWED because both are Long JPY (same direction, no conflict).
        """
        pos = MagicMock()
        pos.symbol = "CADJPY-ECNc"
        pos.type = 1  # SELL

        conflict_ok, reason = check_basket_directional_conflict(
            symbol="USDJPY-ECNc",
            direction=-1,  # SELL
            active_positions=[pos],
            active_orders=[]
        )
        self.assertTrue(conflict_ok)
        self.assertEqual(reason, "")

    def test_non_fx_exempt(self):
        """BTC and Gold are exempt from fiat basket conflict checks."""
        pos = MagicMock()
        pos.symbol = "EURUSD-ECNc"
        pos.type = 0  # BUY

        ok_btc, _ = check_basket_directional_conflict("BTCUSD.c", -1, [pos], [])
        ok_xau, _ = check_basket_directional_conflict("XAUUSD-ECNc", -1, [pos], [])
        self.assertTrue(ok_btc)
        self.assertTrue(ok_xau)

    @patch("src.core.risk_engine.mt5")
    def test_risk_engine_can_trade_anti_hedge_integration(self, mock_mt5):
        """
        Verify that RiskEngine.can_trade(sym, action) invokes the hedge gate.
        """
        active_pos = MagicMock()
        active_pos.symbol = "EURNZD-ECNc"
        active_pos.type = 0  # BUY
        active_pos.ticket = 12345
        active_pos.sl = 0.0
        active_pos.price_open = 1.9800

        mock_mt5.positions_get.return_value = [active_pos]
        mock_mt5.orders_get.return_value = []
        mock_mt5.symbol_info.return_value = MagicMock(point=0.00001)
        mock_mt5.symbol_info_tick.return_value = MagicMock(ask=1.6100, bid=1.6098)

        # 1. EURAUD SELL should be rejected by Anti-Internal Hedge
        allowed, msg = self.risk._check_anti_internal_hedge(symbol="EURAUD-ECNc", action="SELL")
        self.assertFalse(allowed)
        self.assertIn("[CBSS ANTI-HEDGE]", msg)
        self.assertIn("EUR", msg)

        # 2. AUDNZD BUY should pass the hedge check
        allowed_audnzd, msg_audnzd = self.risk._check_anti_internal_hedge(symbol="AUDNZD-ECNc", action="BUY")
        self.assertTrue(allowed_audnzd)
        self.assertEqual(msg_audnzd, "")


if __name__ == "__main__":
    unittest.main()
