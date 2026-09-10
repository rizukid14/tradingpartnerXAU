"""
Unit Test Suite for Confluence Timing, Basket Saturation Index (BSSI),
Basket Champion Selection, Midday Retracement Guard, and Pre-News Emergency Shield.
"""
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, date
from zoneinfo import ZoneInfo
import config
from src.analytics.basket_sync_engine import (
    calculate_basket_saturation_index,
    select_basket_champion,
    BASKETS
)
from src.analytics.macro_strategic_engine import evaluate_session_confluence_timing
import src.analytics.position_manager as pm

WIB = ZoneInfo("Asia/Jakarta")


class TestConfluenceTimingAndLaggard(unittest.TestCase):

    def setUp(self):
        # Reset position manager global state for isolation
        pm._break_even_tickets.clear()
        pm._peak_mfe_points.clear()
        pm._original_sl.clear()

    # -------------------------------------------------------------------------
    # 1. Basket Structural Saturation Index (BSSI)
    # -------------------------------------------------------------------------
    def test_basket_saturation_index_high(self):
        """When pairs in a basket are near opposing walls (dist <= 0.35x ATR), BSSI should be high."""
        mock_macro_cache = {
            "AUDUSD": {"current_mid": 0.6550, "point": 0.00001, "current_atr_pts": 50.0,
                       "zce_walls": {"c1": 0.6551, "f1": 0.6500}}, # 10 pts away -> 0.20x ATR (colliding)
            "AUDJPY": {"current_mid": 95.50, "point": 0.001, "current_atr_pts": 60.0,
                       "zce_walls": {"c1": 95.51, "f1": 94.80}},  # 10 pts away -> 0.16x ATR (colliding)
            "AUDCHF": {"current_mid": 0.5800, "point": 0.00001, "current_atr_pts": 40.0,
                       "zce_walls": {"c1": 0.5801, "f1": 0.5750}}, # 10 pts away -> 0.25x ATR (colliding)
            "AUDCAD": {"current_mid": 0.8900, "point": 0.00001, "current_atr_pts": 50.0,
                       "zce_walls": {"c1": 0.8901, "f1": 0.8850}}, # 10 pts away -> 0.20x ATR (colliding)
            "AUDNZD": {"current_mid": 1.0900, "point": 0.00001, "current_atr_pts": 45.0,
                       "zce_walls": {"c1": 1.0901, "f1": 1.0850}}, # 10 pts away -> 0.22x ATR (colliding)
            "EURAUD": {"current_mid": 1.6500, "point": 0.00001, "current_atr_pts": 80.0,
                       "zce_walls": {"c1": 1.6580, "f1": 1.6490}}, # 10 pts away -> 0.12x ATR (colliding)
            "GBPAUD": {"current_mid": 1.9500, "point": 0.00001, "current_atr_pts": 90.0,
                       "zce_walls": {"c1": 1.9590, "f1": 1.9485}}, # 15 pts away -> 0.16x ATR (colliding)
        }
        bssi, col, tot = calculate_basket_saturation_index("AUD", 1, mock_macro_cache)
        self.assertGreaterEqual(bssi, 0.70)
        self.assertGreaterEqual(col, 5)
        self.assertGreaterEqual(tot, 6)

    def test_basket_saturation_index_low(self):
        """When pairs have ample runway (> 1.0x ATR), BSSI should be low."""
        mock_macro_cache = {
            "AUDUSD": {"current_mid": 0.6500, "point": 0.00001, "current_atr_pts": 50.0,
                       "zce_walls": {"c1": 0.6650, "f1": 0.6400}}, # 150 pts away -> 3.0x ATR
            "AUDJPY": {"current_mid": 95.00, "point": 0.001, "current_atr_pts": 60.0,
                       "zce_walls": {"c1": 96.50, "f1": 93.80}},  # 150 pts away -> 2.5x ATR
        }
        bssi, col, tot = calculate_basket_saturation_index("AUD", 1, mock_macro_cache)
        self.assertLess(bssi, 0.50)

    # -------------------------------------------------------------------------
    # 2. Select Basket Champion
    # -------------------------------------------------------------------------
    def test_select_basket_champion(self):
        """Pair with adequate runway (>= 0.85x ATR) and no G3 blockage should be chosen."""
        mock_macro_cache = {
            "AUDUSD": {"current_mid": 0.6550, "point": 0.00001, "current_atr_pts": 50.0,
                       "zce_walls": {"c1": 0.6555, "f1": 0.6500, "c1_grade": "GRADE_3_MACRO"}}, # Blocked
            "AUDCHF": {"current_mid": 0.5800, "point": 0.00001, "current_atr_pts": 40.0,
                       "zce_walls": {"c1": 0.5880, "f1": 0.5750, "c1_grade": "GRADE_1_MICRO"}}, # 80 pts = 2.0x ATR
        }
        with patch("src.analytics.currency_strength.get_csm_delta_for_symbol", return_value=1.5):
            champ = select_basket_champion("AUD", 1, mock_macro_cache, candidate_pairs=["AUDUSD", "AUDCHF"], hour_wib=9)
            self.assertIsNotNone(champ)
            self.assertIn("AUDCHF", champ.get("pair", ""))

    # -------------------------------------------------------------------------
    # 3. Session Confluence Timing Evaluation
    # -------------------------------------------------------------------------
    def test_evaluate_session_confluence_timing(self):
        # Tokyo Morning Expansion (09:00 WIB)
        dir_09 = evaluate_session_confluence_timing("EURUSD", 9)
        self.assertEqual(dir_09["timing_phase"], "TOKYO_EXPANSION")
        self.assertFalse(dir_09["is_lull_window"])
        self.assertTrue(dir_09["allow_continuation"])

        # Tokyo Midday Lull (11:30 WIB)
        dir_11 = evaluate_session_confluence_timing("EURUSD", 11)
        self.assertEqual(dir_11["timing_phase"], "TOKYO_MIDDAY_LULL")
        self.assertTrue(dir_11["is_lull_window"])
        self.assertFalse(dir_11["allow_continuation"])
        self.assertEqual(dir_11["target_mode"], "GRADE_B_C1")

        # London Core (15:00 WIB)
        dir_15 = evaluate_session_confluence_timing("EURUSD", 15)
        self.assertEqual(dir_15["timing_phase"], "LONDON_CORE")
        self.assertFalse(dir_15["is_lull_window"])
        self.assertTrue(dir_15["allow_continuation"])

        # NY Peak Velocity (20:00 WIB)
        dir_20 = evaluate_session_confluence_timing("EURUSD", 20)
        self.assertEqual(dir_20["timing_phase"], "NY_PEAK_VELOCITY")
        self.assertEqual(dir_20["target_mode"], "GRADE_A_PLUS_C2")
        self.assertEqual(dir_20["max_recommended_rr"], 3.00)

        # Night Dead Zone (03:00 WIB)
        dir_03 = evaluate_session_confluence_timing("EURUSD", 3)
        self.assertEqual(dir_03["timing_phase"], "NIGHT_DEAD_ZONE")
        self.assertFalse(dir_03["allow_continuation"])

    # -------------------------------------------------------------------------
    # 4. Midday Retracement Guard
    # -------------------------------------------------------------------------
    def test_midday_retracement_guard_triggers_at_70_pct(self):
        """Retracement > 65% triggers defensive BEP lock."""
        now_wib = datetime(2026, 9, 10, 11, 45, tzinfo=WIB)
        open_time = datetime(2026, 9, 10, 8, 30, tzinfo=WIB).timestamp()

        mock_pos = MagicMock()
        mock_pos.ticket = 12345
        mock_pos.symbol = "AUDUSD-ECN"
        mock_pos.type = 0  # BUY
        mock_pos.time = open_time
        mock_pos.price_open = 0.6500
        mock_pos.sl = 0.6470
        mock_pos.tp = 0.6580
        mock_pos.volume = 0.50

        mock_si = MagicMock()
        mock_si.point = 0.00001
        mock_si.digits = 5

        # Peak MFE was +100 pts, now current profit dropped to +25 pts (75% retrace > 65%)
        pm._peak_mfe_points[12345] = 100.0

        with patch("src.analytics.position_manager.datetime") as mock_dt, \
             patch("src.analytics.position_manager._force_move_to_bep", return_value=True) as mock_bep:
            mock_dt.now.return_value = now_wib
            mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp

            triggered = pm._check_midday_retracement_guard(
                mock_pos, "AUDUSD-ECN", profit_points=25.0, point=0.00001, symbol_info=mock_si, now=now_wib.timestamp()
            )
            self.assertTrue(triggered)
            mock_bep.assert_called_once()

    def test_midday_retracement_guard_allows_normal_breathing(self):
        """Retracement <= 65% does NOT trigger defensive BEP (lets position breathe)."""
        now_wib = datetime(2026, 9, 10, 11, 45, tzinfo=WIB)
        open_time = datetime(2026, 9, 10, 8, 30, tzinfo=WIB).timestamp()

        mock_pos = MagicMock()
        mock_pos.ticket = 12346
        mock_pos.symbol = "AUDUSD-ECN"
        mock_pos.type = 0  # BUY
        mock_pos.time = open_time
        mock_pos.price_open = 0.6500
        mock_pos.sl = 0.6470
        mock_pos.tp = 0.6580
        mock_pos.volume = 0.50

        mock_si = MagicMock()
        mock_si.point = 0.00001
        mock_si.digits = 5

        # Peak MFE was +100 pts, current profit is +50 pts (50% retrace <= 65%)
        pm._peak_mfe_points[12346] = 100.0

        with patch("src.analytics.position_manager.datetime") as mock_dt, \
             patch("src.analytics.position_manager._force_move_to_bep") as mock_bep:
            mock_dt.now.return_value = now_wib
            mock_dt.fromtimestamp.side_effect = datetime.fromtimestamp

            triggered = pm._check_midday_retracement_guard(
                mock_pos, "AUDUSD-ECN", profit_points=50.0, point=0.00001, symbol_info=mock_si, now=now_wib.timestamp()
            )
            self.assertFalse(triggered)
            mock_bep.assert_not_called()

    # -------------------------------------------------------------------------
    # 5. Pre-News Emergency Shield
    # -------------------------------------------------------------------------
    def test_pre_news_emergency_shield_closes_thin_position(self):
        """Thin floating position (< +0.20R) is closed flat ahead of Tier-1 news."""
        now_wib = datetime(2026, 9, 10, 18, 45, tzinfo=WIB)

        mock_pos = MagicMock()
        mock_pos.ticket = 99901
        mock_pos.symbol = "EURUSD-ECN"
        mock_pos.type = 0  # BUY
        mock_pos.price_open = 1.0850
        mock_pos.sl = 1.0820  # 300 pts SL
        mock_pos.tp = 1.0910
        mock_pos.volume = 0.50

        mock_si = MagicMock()
        mock_si.point = 0.00001
        mock_si.digits = 5

        pm._original_sl[99901] = 300.0  # 300 pts SL
        # Current profit is +30 pts -> +0.10R (< +0.20R)
        profit_points = 30.0

        with patch("src.analytics.economic_calendar.calendar.is_in_news_blackout", return_value=(True, "ECB Rate Decision in 30m")), \
             patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close, \
             patch("src.analytics.position_manager.datetime") as mock_dt:
            mock_dt.now.return_value = now_wib

            closed = pm._check_pre_news_emergency_shield(
                mock_pos, "EURUSD-ECN", profit_points, point=0.00001, symbol_info=mock_si, now=now_wib.timestamp()
            )
            self.assertTrue(closed)
            mock_close.assert_called_once()

    def test_pre_news_emergency_shield_locks_bep_on_healthy_position(self):
        """Healthy floating position (>= +0.20R) locks BEP instead of flat closing."""
        now_wib = datetime(2026, 9, 10, 18, 45, tzinfo=WIB)

        mock_pos = MagicMock()
        mock_pos.ticket = 99902
        mock_pos.symbol = "EURUSD-ECN"
        mock_pos.type = 0  # BUY
        mock_pos.price_open = 1.0850
        mock_pos.sl = 1.0820  # 300 pts SL
        mock_pos.tp = 1.0910
        mock_pos.volume = 0.50

        mock_si = MagicMock()
        mock_si.point = 0.00001
        mock_si.digits = 5

        pm._original_sl[99902] = 300.0
        # Current profit is +150 pts -> +0.50R (>= +0.20R)
        profit_points = 150.0

        with patch("src.analytics.economic_calendar.calendar.is_in_news_blackout", return_value=(True, "ECB Rate Decision in 30m")), \
             patch("src.analytics.position_manager._close_position_by_ticket") as mock_close, \
             patch("src.analytics.position_manager._force_move_to_bep", return_value=True) as mock_bep, \
             patch("src.analytics.position_manager.datetime") as mock_dt:
            mock_dt.now.return_value = now_wib

            locked = pm._check_pre_news_emergency_shield(
                mock_pos, "EURUSD-ECN", profit_points, point=0.00001, symbol_info=mock_si, now=now_wib.timestamp()
            )
            self.assertTrue(locked)
            mock_close.assert_not_called()
            mock_bep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
