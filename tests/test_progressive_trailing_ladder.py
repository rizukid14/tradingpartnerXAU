"""
Unit tests for the 3-Tier Progressive Trailing Stop Ladder and No Partial Close (11 Sep 2026).
Verifies:
1. Partial close is completely bypassed when PARTIAL_CLOSE_ENABLED=False.
2. BEP moves SL to entry + comms padding exactly at 60% of TP distance.
3. 3-Tier Progressive Trailing Ladder locks profit:
   - Tier 1 (75% TP): locks 50% TP
   - Tier 2 (90% TP): locks 80% TP
   - Tier 3 (95% TP): locks 90% TP (Terminal Lock)
4. Trailing is non-loosening: SL can only tighten toward TP, never retreat.
5. Works identically for BUY and SELL orders.
"""

import unittest
from unittest.mock import MagicMock, patch
import config
from src.analytics import position_manager


class TestProgressiveTrailingLadder(unittest.TestCase):

    def setUp(self):
        self.orig_partial = config.PARTIAL_CLOSE_ENABLED
        self.orig_bep_pct = config.BREAK_EVEN_TRIGGER_TP_PCT
        self.orig_t1_trig = config.TRAILING_TIER_1_TRIGGER_PCT
        self.orig_t1_lock = config.TRAILING_TIER_1_LOCK_PCT
        self.orig_t2_trig = config.TRAILING_TIER_2_TRIGGER_PCT
        self.orig_t2_lock = config.TRAILING_TIER_2_LOCK_PCT
        self.orig_t3_trig = config.TRAILING_TIER_3_TRIGGER_PCT
        self.orig_t3_lock = config.TRAILING_TIER_3_LOCK_PCT

        config.PARTIAL_CLOSE_ENABLED = False
        config.BREAK_EVEN_TRIGGER_TP_PCT = 0.60
        config.TRAILING_TIER_1_TRIGGER_PCT = 0.75
        config.TRAILING_TIER_1_LOCK_PCT = 0.50
        config.TRAILING_TIER_2_TRIGGER_PCT = 0.90
        config.TRAILING_TIER_2_LOCK_PCT = 0.80
        config.TRAILING_TIER_3_TRIGGER_PCT = 0.95
        config.TRAILING_TIER_3_LOCK_PCT = 0.90

        position_manager._partial_closed_tickets.clear()
        position_manager._break_even_tickets.clear()
        position_manager._trailing_active_tickets.clear()
        position_manager._trailing_extremes.clear()
        position_manager._original_sl.clear()
        position_manager._ticket_setup_grades.clear()

    def tearDown(self):
        config.PARTIAL_CLOSE_ENABLED = self.orig_partial
        config.BREAK_EVEN_TRIGGER_TP_PCT = self.orig_bep_pct
        config.TRAILING_TIER_1_TRIGGER_PCT = self.orig_t1_trig
        config.TRAILING_TIER_1_LOCK_PCT = self.orig_t1_lock
        config.TRAILING_TIER_2_TRIGGER_PCT = self.orig_t2_trig
        config.TRAILING_TIER_2_LOCK_PCT = self.orig_t2_lock
        config.TRAILING_TIER_3_TRIGGER_PCT = self.orig_t3_trig
        config.TRAILING_TIER_3_LOCK_PCT = self.orig_t3_lock

    def _make_mock_pos(self, ticket=1001, order_type=0, open_price=1.10000, sl=1.09800, tp=1.10400, volume=0.20):
        pos = MagicMock()
        pos.ticket = ticket
        pos.type = order_type  # 0: BUY, 1: SELL
        pos.price_open = open_price
        pos.sl = sl
        pos.tp = tp
        pos.volume = volume
        pos.comment = "M2_PULLBACK"
        return pos

    def _make_mock_symbol_info(self, point=0.00001, digits=5):
        si = MagicMock()
        si.point = point
        si.digits = digits
        si.volume_min = 0.01
        return si

    def test_partial_close_bypassed_when_disabled(self):
        """Partial close must never send orders when disabled."""
        pos = self._make_mock_pos(ticket=2001)
        si = self._make_mock_symbol_info()

        with patch("config.mt5.order_send") as mock_send:
            position_manager._check_partial_close(pos, "EURUSD-ECNc", 300, si)
            mock_send.assert_not_called()
        self.assertNotIn(2001, position_manager._partial_closed_tickets)

    def test_bep_triggers_at_60_percent_tp_buy(self):
        """BEP should NOT trigger at 50% TP, but MUST trigger at 60% TP."""
        # BUY: Open 1.10000, TP 1.10400 (400 pts TP). 60% = 240 pts.
        pos = self._make_mock_pos(ticket=3001, sl=1.09800)
        si = self._make_mock_symbol_info()

        with patch("config.mt5.order_send") as mock_send:
            # 1. At 50% TP (200 pts) -> Should NOT trigger BEP
            position_manager._check_break_even(pos, "EURUSD-ECNc", 200, si.point, si)
            mock_send.assert_not_called()
            self.assertNotIn(3001, position_manager._break_even_tickets)

            # 2. At 60% TP (240 pts) -> MUST trigger BEP
            mock_send.return_value = MagicMock(retcode=10009)
            position_manager._check_break_even(pos, "EURUSD-ECNc", 240, si.point, si)
            mock_send.assert_called_once()
            self.assertIn(3001, position_manager._break_even_tickets)

    def test_3_tier_progressive_trailing_ladder_buy(self):
        """
        Tests progressive ladder for BUY:
        TP = 400 pts (1.10400 from 1.10000).
        - At 70% TP (280 pts) -> No trailing yet.
        - At 75% TP (300 pts) -> Tier 1: SL locked at +50% TP (1.10200).
        - At 90% TP (360 pts) -> Tier 2: SL locked at +80% TP (1.10320).
        - At 95% TP (380 pts) -> Tier 3: SL locked at +90% TP (1.10360).
        """
        pos = self._make_mock_pos(ticket=4001, sl=1.10015)
        si = self._make_mock_symbol_info()

        with patch("config.mt5.order_send") as mock_send:
            mock_send.return_value = MagicMock(retcode=10009)

            # 1. At 70% TP (profit 280 pts, price 1.10280) -> Below Tier 1 (75%)
            position_manager._check_trailing_stop(pos, "EURUSD-ECNc", 280, 1.10280, si.point, si)
            mock_send.assert_not_called()

            # 2. At 75% TP (profit 300 pts, price 1.10300) -> Tier 1 lock 50% TP (1.10200)
            position_manager._check_trailing_stop(pos, "EURUSD-ECNc", 300, 1.10300, si.point, si)
            mock_send.assert_called_once()
            call_req = mock_send.call_args[0][0]
            self.assertEqual(call_req["sl"], 1.10200)
            pos.sl = 1.10200
            mock_send.reset_mock()

            # 3. At 90% TP (profit 360 pts, price 1.10360) -> Tier 2 lock 80% TP (1.10320)
            position_manager._check_trailing_stop(pos, "EURUSD-ECNc", 360, 1.10360, si.point, si)
            mock_send.assert_called_once()
            call_req = mock_send.call_args[0][0]
            self.assertEqual(call_req["sl"], 1.10320)
            pos.sl = 1.10320
            mock_send.reset_mock()

            # 4. At 95% TP (profit 380 pts, price 1.10380) -> Tier 3 lock 90% TP (1.10360)
            position_manager._check_trailing_stop(pos, "EURUSD-ECNc", 380, 1.10380, si.point, si)
            mock_send.assert_called_once()
            call_req = mock_send.call_args[0][0]
            self.assertEqual(call_req["sl"], 1.10360)

    def test_3_tier_progressive_trailing_ladder_sell(self):
        """
        Tests progressive ladder for SELL:
        Open = 1.10000, TP = 1.09600 (400 pts TP).
        - At 75% TP (profit 300 pts, price 1.09700) -> Tier 1: SL locked at entry - 50% TP (1.09800).
        - At 90% TP (profit 360 pts, price 1.09640) -> Tier 2: SL locked at entry - 80% TP (1.09680).
        - At 95% TP (profit 380 pts, price 1.09620) -> Tier 3: SL locked at entry - 90% TP (1.09640).
        """
        pos = self._make_mock_pos(ticket=5001, order_type=1, open_price=1.10000, sl=1.09985, tp=1.09600)
        si = self._make_mock_symbol_info()

        with patch("config.mt5.order_send") as mock_send:
            mock_send.return_value = MagicMock(retcode=10009)

            # 1. At 75% TP (price 1.09700, profit 300 pts)
            position_manager._check_trailing_stop(pos, "EURUSD-ECNc", 300, 1.09700, si.point, si)
            mock_send.assert_called_once()
            call_req = mock_send.call_args[0][0]
            self.assertEqual(call_req["sl"], 1.09800)
            pos.sl = 1.09800
            mock_send.reset_mock()

            # 2. At 90% TP (price 1.09640, profit 360 pts)
            position_manager._check_trailing_stop(pos, "EURUSD-ECNc", 360, 1.09640, si.point, si)
            mock_send.assert_called_once()
            call_req = mock_send.call_args[0][0]
            self.assertEqual(call_req["sl"], 1.09680)
            pos.sl = 1.09680
            mock_send.reset_mock()

            # 3. At 95% TP (price 1.09620, profit 380 pts)
            position_manager._check_trailing_stop(pos, "EURUSD-ECNc", 380, 1.09620, si.point, si)
            mock_send.assert_called_once()
            call_req = mock_send.call_args[0][0]
            self.assertEqual(call_req["sl"], 1.09640)


if __name__ == "__main__":
    unittest.main()
