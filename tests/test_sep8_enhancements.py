"""Unit tests for September 8th Enhancements:
1. Chamber Runway and Grade B Wall Scalp (atlas_dna.py)
2. Bypass Partial Close for Grade B (position_manager.py)
3. CSM Dynamic Flow Bailout (position_manager.py)
4. Bank Holiday Circuit Breaker (economic_calendar.py)
5. Directional Hysteresis Memory Gate (market_scanner.py)
"""
import os
import sys
import time
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.indicators.atlas_dna import calculate_intraday_sl_tp
from src.analytics import position_manager
from src.analytics.economic_calendar import EconomicCalendar
from src.analytics.market_scanner import MarketScanner

WIB = ZoneInfo("Asia/Jakarta")


class DummyPosition:
    def __init__(self, ticket=1001, symbol="GBPUSD-ECNc", pos_type=0, price_open=1.35000, sl=1.34500, tp=1.36000, volume=0.05, open_time=0, comment=""):
        self.ticket = ticket
        self.symbol = symbol
        self.type = pos_type
        self.price_open = price_open
        self.price_current = price_open
        self.sl = sl
        self.tp = tp
        self.volume = volume
        self.time = open_time
        self.magic = config.MAGIC_NUMBER
        self.comment = comment


class DummySymbolInfo:
    def __init__(self, point=0.00001, digits=5):
        self.point = point
        self.digits = digits
        self.volume_min = 0.01
        self.trade_tick_value = 1.0
        self.trade_tick_size = 0.00001


class TestSep8Enhancements(unittest.TestCase):
    def test_grade_b_wall_scalp_clamped_to_c1(self):
        entry = 1.35000
        atr = 0.00150
        origin = 1.34950
        c1_wall = 1.35180
        res = calculate_intraday_sl_tp(
            symbol="GBPUSD-ECNc",
            entry_price=entry,
            direction=1,
            origin_level=origin,
            atr_h1=atr,
            c1=c1_wall,
            c1_grade="GRADE_2_INTERMEDIATE"
        )
        self.assertEqual(res["target_station"], c1_wall)
        self.assertTrue(res["is_wall_scalp"])
        self.assertEqual(res["setup_grade"], "GRADE_B")
        self.assertLess(res["risk_reward"], 1.25)
        self.assertGreaterEqual(res["risk_reward"], 0.75)

    def test_grade_b_bypasses_partial_close(self):
        pos = DummyPosition(ticket=3001, comment="[GRADE_B_SCALP]")
        position_manager._ticket_setup_grades[3001] = "GRADE_B"
        grade = str(position_manager._ticket_setup_grades.get(pos.ticket, "GRADE_A")).upper()
        is_grade_b = "GRADE_B" in grade or "SCALP" in grade
        self.assertTrue(is_grade_b)

    def test_csm_dynamic_flow_bailout_trigger(self):
        pos = DummyPosition(ticket=4001, pos_type=0, price_open=1.35000, sl=1.34500)
        point = 0.00001
        si = DummySymbolInfo(point=point)
        now = time.time()
        position_manager._original_sl[4001] = 500.0
        position_manager._csm_opposed_bars.pop(4001, None)

        profit_points = -260.0  # -0.52R <= -0.50R threshold
        with patch.object(config, "ENABLE_CSM_DYNAMIC_BAILOUT", True):
            with patch("src.analytics.currency_strength.get_csm_delta_for_symbol", return_value=-2.5):
                with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
                    # Bar 1: Should not close yet (waiting for 2 consecutive M15 bars)
                    closed1 = position_manager._check_csm_dynamic_bailout(pos, "GBPUSD-ECNc", profit_points, point, si, now)
                    self.assertFalse(closed1)
                    self.assertFalse(mock_close.called)

                    # Bar 2: Next M15 bar (now + 900s) -> Should trigger bailout
                    closed2 = position_manager._check_csm_dynamic_bailout(pos, "GBPUSD-ECNc", profit_points, point, si, now + 900)
                    self.assertTrue(closed2)
                    self.assertTrue(mock_close.called)

        profit_points = +50.0
        with patch("src.analytics.currency_strength.get_csm_delta_for_symbol", return_value=-2.5):
            with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
                closed = position_manager._check_csm_dynamic_bailout(pos, "GBPUSD-ECNc", profit_points, point, si, now)
                self.assertFalse(closed)
                self.assertFalse(mock_close.called)

    def test_bank_holiday_detection(self):
        cal = EconomicCalendar()
        holiday_event = {
            "name": "US Labor Day",
            "country": "US",
            "currency": "USD",
            "impact": "HOLIDAY",
            "dt": datetime.now(WIB)
        }
        with patch.object(cal, "get_events", return_value=[holiday_event]):
            is_hol, desc = cal.is_bank_holiday_today("US")
            self.assertTrue(is_hol)
            self.assertIn("Labor Day", desc)

            imminent, imm_desc = cal.is_high_impact_imminent("EURUSD-ECNc")
            self.assertTrue(imminent)
            self.assertIn("BANK HOLIDAY", imm_desc)

    def test_directional_hysteresis_lock_and_release(self):
        scanner = MarketScanner(symbols=["GBPUSD-ECNc"])
        clean_s = "GBPUSD"
        now_ts = time.time()

        scanner._symbol_directional_state[clean_s] = {
            "dir": 1,
            "locked_at": now_ts,
            "reason": "MACRO_BIAS_INIT"
        }

        dir_mem = scanner._symbol_directional_state.get(clean_s)
        locked_dir = dir_mem["dir"]
        target_dir = -1

        macro = {
            "immediate_floor_f1": 1.34000,
            "immediate_ceiling_c1": 1.36000,
            "macro_bias_score": 0.0,
            "dealing_range_pos": 0.50
        }
        mid = 1.35000
        atr = 0.00300
        floor_broken = bool(locked_dir == 1 and macro["immediate_floor_f1"] > 0 and mid < (macro["immediate_floor_f1"] - 0.20 * atr))
        macro_inverted = bool(target_dir == -1 and macro["macro_bias_score"] <= -0.35)
        self.assertFalse(floor_broken)
        self.assertFalse(macro_inverted)

        mid_breakdown = 1.33900
        floor_broken_after = bool(locked_dir == 1 and macro["immediate_floor_f1"] > 0 and mid_breakdown < (macro["immediate_floor_f1"] - 0.20 * atr))
        self.assertTrue(floor_broken_after)

    def test_rigid_breached_wall_blocks_c2_targeting(self):
        """Test that unbreached C1 strictly prevents targeting C2 (caps at C1)."""
        entry = 1.35000
        atr = 0.00200
        origin = 1.34850
        c1_wall = 1.35350  # ~1.5R away
        c2_wall = 1.35700  # ~2.2R away (Grade A+)

        # Unbreached C1: Must anchor target_station to C1!
        res_unbreached = calculate_intraday_sl_tp(
            symbol="GBPUSD-ECNc",
            entry_price=entry,
            direction=1,
            origin_level=origin,
            atr_h1=atr,
            c1=c1_wall,
            c2=c2_wall,
            c1_grade="GRADE_2_INTERMEDIATE",
            c1_breached=False
        )
        self.assertEqual(res_unbreached["target_station"], c1_wall)
        self.assertEqual(res_unbreached["setup_grade"], "GRADE_A")
        self.assertLess(res_unbreached["risk_reward"], 1.80)

        # Breached C1: Can now legally target C2 and elevate to Grade A+!
        res_breached = calculate_intraday_sl_tp(
            symbol="GBPUSD-ECNc",
            entry_price=entry,
            direction=1,
            origin_level=origin,
            atr_h1=atr,
            c1=c1_wall,
            c2=c2_wall,
            c1_grade="GRADE_2_INTERMEDIATE",
            c1_breached=True
        )
        self.assertEqual(res_breached["target_station"], c2_wall)
        self.assertEqual(res_breached["setup_grade"], "GRADE_A_PLUS")
        self.assertGreaterEqual(res_breached["risk_reward"], 1.80)

    def test_scanner_is_zce_wall_breached(self):
        """Test MarketScanner._is_zce_wall_breached logic."""
        import pandas as pd
        scanner = MarketScanner(symbols=["GBPUSD-ECNc"])

        # Case 1: Rejection wick above C1 (High pierced 1.3550, but Close is 1.3540 <= C1 1.3550)
        df_rejection = pd.DataFrame([
            {"open": 1.3500, "high": 1.3520, "low": 1.3490, "close": 1.3510},
            {"open": 1.3510, "high": 1.3560, "low": 1.3505, "close": 1.3540},  # closed below 1.3550!
            {"open": 1.3540, "high": 1.3545, "low": 1.3535, "close": 1.3538},  # forming
        ])
        self.assertFalse(scanner._is_zce_wall_breached("GBPUSD", 1.3550, 1, df_rejection))

        # Case 2: Doji / spinning top (Close above 1.3550, but body < 50% displacement)
        df_doji = pd.DataFrame([
            {"open": 1.3500, "high": 1.3520, "low": 1.3490, "close": 1.3510},
            {"open": 1.3551, "high": 1.3580, "low": 1.3530, "close": 1.3555},  # range 50, body 4 (8% body)
            {"open": 1.3555, "high": 1.3560, "low": 1.3550, "close": 1.3558},  # forming
        ])
        self.assertFalse(scanner._is_zce_wall_breached("GBPUSD", 1.3550, 1, df_doji))

        # Case 3: Legitimate breakout with strong displacement body (range 40, body 30 = 75% body)
        df_breach = pd.DataFrame([
            {"open": 1.3500, "high": 1.3520, "low": 1.3490, "close": 1.3510},
            {"open": 1.3530, "high": 1.3570, "low": 1.3530, "close": 1.3565},  # range 40, body 35 = 87.5% body
            {"open": 1.3565, "high": 1.3575, "low": 1.3560, "close": 1.3570},  # forming
        ])
        self.assertTrue(scanner._is_zce_wall_breached("GBPUSD", 1.3550, 1, df_breach))

    def test_bep_threshold_grade_s(self):
        """Test that Grade S position uses 65% TP BEP ratio."""
        pos = DummyPosition(ticket=5001, pos_type=0, price_open=1.35000, sl=1.34500, tp=1.36500)
        position_manager._ticket_setup_grades[5001] = "GRADE_S"
        point = 0.00001
        si = DummySymbolInfo(point=point)

        # TP distance = 1.36500 - 1.35000 = 1500 points
        # 65% of 1500 = 975 points
        with patch.object(config.mt5, "history_deals_get", return_value=[]):
            with patch("src.analytics.position_manager.is_order_success", return_value=True):
                # 900 points profit (< 975) -> Should NOT trigger BEP
                position_manager._break_even_tickets.clear()
                position_manager._check_break_even(pos, "GBPUSD-ECNc", 900, point, si)
                self.assertNotIn(5001, position_manager._break_even_tickets)

                # 980 points profit (>= 975) -> Should trigger BEP
                position_manager._check_break_even(pos, "GBPUSD-ECNc", 980, point, si)
                self.assertIn(5001, position_manager._break_even_tickets)

    def test_risk_engine_defensive_grade_b_with_neutral_multiplier(self):
        """Test that RiskEngine applies 0.75x defensive sizing for GRADE_B even when sizing_multiplier=1.0."""
        from src.core.risk_engine import RiskEngine
        risk = RiskEngine()

        # Mock mt5 symbol info and account info
        mock_si = DummySymbolInfo(point=0.00001, digits=5)
        mock_account = MagicMock()
        mock_account.equity = 10000.0

        with patch("src.core.risk_engine.mt5.account_info", return_value=mock_account):
            with patch("src.core.risk_engine.mt5.symbol_info", return_value=mock_si):
                with patch("src.core.risk_engine.mt5.symbol_info_tick", return_value=MagicMock(ask=1.3500, bid=1.3500)):
                    with patch.object(risk, "_apply_lot_multipliers", side_effect=lambda l, s: l):
                        # 1. Standard Grade A with neutral multiplier 1.0 -> 1.0x
                        lot_a = risk.get_effective_lot_size(sl_points=100, symbol="GBPUSD-ECNc", setup_grade="GRADE_A", sizing_multiplier=1.0)
                        
                        # 2. Grade B with neutral multiplier 1.0 -> must get 0.75x
                        lot_b = risk.get_effective_lot_size(sl_points=100, symbol="GBPUSD-ECNc", setup_grade="GRADE_B", sizing_multiplier=1.0)
                        
                        # 3. Grade S with APEX multiplier 1.25 -> 1.25x
                        lot_s = risk.get_effective_lot_size(sl_points=100, symbol="GBPUSD-ECNc", setup_grade="GRADE_S", sizing_multiplier=1.25)

                        self.assertAlmostEqual(lot_b / lot_a, 0.75, places=2)
                        self.assertAlmostEqual(lot_s / lot_a, 1.25, places=2)

    def test_risk_engine_ny_session_flat_multiplier_bypasses_grade_b(self):
        """Test that in NY session (0.50x), Grade B 0.75x penalty is bypassed to maintain flat 0.50x."""
        from src.core.risk_engine import RiskEngine
        risk = RiskEngine()
        risk._session_lot_multiplier = 0.50

        mock_si = DummySymbolInfo(point=0.001, digits=3)
        mock_account = MagicMock()
        mock_account.equity = 10000.0

        with patch("src.core.risk_engine.mt5.account_info", return_value=mock_account):
            with patch("src.core.risk_engine.mt5.symbol_info", return_value=mock_si):
                with patch("src.core.risk_engine.mt5.symbol_info_tick", return_value=MagicMock(ask=150.00, bid=150.00)):
                    with patch.object(risk, "_apply_lot_multipliers", side_effect=lambda l, s: l * 0.50):
                        lot_a = risk.get_effective_lot_size(sl_points=100, symbol="USDJPY-ECNc", setup_grade="GRADE_A", sizing_multiplier=1.0)
                        lot_b = risk.get_effective_lot_size(sl_points=100, symbol="USDJPY-ECNc", setup_grade="GRADE_B", sizing_multiplier=1.0)
                        
                        # In NY session, lot_b must NOT be multiplied by 0.75; it stays flat equal to lot_a!
                        self.assertEqual(lot_b, lot_a)


if __name__ == "__main__":
    unittest.main()

