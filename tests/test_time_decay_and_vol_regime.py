"""Unit tests for Ide 1 (Time-Decay Stagnation & Pre-Rollover Shield) and Ide 4 (Dynamic Volatility Scaling)."""
import os
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.analytics import position_manager
from src.core.risk_engine import RiskEngine

WIB = ZoneInfo("Asia/Jakarta")


class DummyPosition:
    def __init__(self, ticket=1001, symbol="GBPUSD-ECNc", pos_type=0, price_open=1.35000, sl=1.34500, tp=1.36000, volume=0.05, open_time=0, price_current=None):
        self.ticket = ticket
        self.symbol = symbol
        self.type = pos_type  # 0 = BUY, 1 = SELL
        self.price_open = price_open
        self.price_current = price_current if price_current is not None else price_open
        self.sl = sl
        self.tp = tp
        self.volume = volume
        self.time = open_time  # Unix timestamp
        self.magic = config.MAGIC_NUMBER


class DummySymbolInfo:
    def __init__(self, point=0.00001, digits=5):
        self.point = point
        self.digits = digits
        self.volume_min = 0.01
        self.trade_tick_value = 1.0
        self.trade_tick_size = 0.00001


import unittest

class TestTimeDecayAndVolRegime(unittest.TestCase):
    def test_time_decay_stagnation(self):
        now = 100000.0
        point = 0.00001
        si = DummySymbolInfo(point=point)

        # 1. Posisi stagnan 9 jam saat sesi London-NY (16:00 WIB), floating +0.10R, Peak +0.15R (< +0.30R) -> HARUS CLOSE
        pos1 = DummyPosition(ticket=2001, open_time=now - (9 * 3600))
        position_manager._original_sl[2001] = 500.0
        position_manager._peak_mfe_points[2001] = 75.0
        profit_points = 50.0

        dt_london = datetime(2026, 8, 24, 16, 0, tzinfo=WIB)
        with patch("src.analytics.position_manager.datetime") as mock_dt:
            mock_dt.now.return_value = dt_london
            with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
                closed = position_manager._check_time_decay_stagnation(pos1, "GBPUSD-ECNc", profit_points, point, si, now)
                self.assertTrue(closed)
                self.assertTrue(mock_close.called)

        # 1b. Posisi stagnan 9 jam tapi di Sesi Tokyo (10:00 WIB) -> TIDAK DI-CLOSE
        dt_tokyo = datetime(2026, 8, 24, 10, 0, tzinfo=WIB)
        with patch("src.analytics.position_manager.datetime") as mock_dt:
            mock_dt.now.return_value = dt_tokyo
            with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
                closed = position_manager._check_time_decay_stagnation(pos1, "GBPUSD-ECNc", profit_points, point, si, now)
                self.assertFalse(closed)
                self.assertFalse(mock_close.called)

        # 2. Posisi 9 jam lalu di sesi London (16:00 WIB), floating +0.10R, tapi PEAK PERNAH +0.50R (+250 pts) -> JANGAN DI-CLOSE
        pos2 = DummyPosition(ticket=2002, open_time=now - (9 * 3600))
        position_manager._original_sl[2002] = 500.0
        position_manager._peak_mfe_points[2002] = 250.0
        with patch("src.analytics.position_manager.datetime") as mock_dt:
            mock_dt.now.return_value = dt_london
            with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
                closed = position_manager._check_time_decay_stagnation(pos2, "GBPUSD-ECNc", profit_points, point, si, now)
                self.assertFalse(closed)
                self.assertFalse(mock_close.called)

        # 3. Posisi baru 3 jam -> JANGAN DI-CLOSE
        pos3 = DummyPosition(ticket=2003, open_time=now - (3 * 3600))
        position_manager._original_sl[2003] = 500.0
        position_manager._peak_mfe_points[2003] = 50.0
        with patch("src.analytics.position_manager.datetime") as mock_dt:
            mock_dt.now.return_value = dt_london
            with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
                closed = position_manager._check_time_decay_stagnation(pos3, "GBPUSD-ECNc", profit_points, point, si, now)
                self.assertFalse(closed)
                self.assertFalse(mock_close.called)

    def test_pre_rollover_shield(self):
        point = 0.00001
        si = DummySymbolInfo(point=point)
        now = 100000.0

        # 1. Jam 03:55 WIB (dalam window 03:50 - 04:15), EURCHF (threshold = 240 pts)
        pos_mepet = DummyPosition(ticket=3001, sl=0.93450, price_current=0.93600)
        dt_roll = datetime(2026, 8, 24, 3, 55, tzinfo=WIB)

        with patch("src.analytics.position_manager.datetime") as mock_dt:
            mock_dt.now.return_value = dt_roll
            with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
                closed = position_manager._check_pre_rollover_shield(pos_mepet, "EURCHF-ECNc", 0.0, point, si, now)
                self.assertTrue(closed)
                self.assertTrue(mock_close.called)

        # 2. Jam 03:55 WIB, EURCHF posisi profit/SL aman -> JALAN TERUS
        pos_aman = DummyPosition(ticket=3002, sl=0.93450, price_current=0.93850)
        with patch("src.analytics.position_manager.datetime") as mock_dt:
            mock_dt.now.return_value = dt_roll
            with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
                closed = position_manager._check_pre_rollover_shield(pos_aman, "EURCHF-ECNc", 400.0, point, si, now)
                self.assertFalse(closed)
                self.assertFalse(mock_close.called)

        # 3. Jam 14:00 WIB (di luar window 03:50 - 04:15), SL mepet -> TIDAK DI-CLOSE
        dt_day = datetime(2026, 8, 24, 14, 0, tzinfo=WIB)
        with patch("src.analytics.position_manager.datetime") as mock_dt:
            mock_dt.now.return_value = dt_day
            with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
                closed = position_manager._check_pre_rollover_shield(pos_mepet, "EURCHF-ECNc", 0.0, point, si, now)
                self.assertFalse(closed)
                self.assertFalse(mock_close.called)

    def test_dynamic_volatility_scaling(self):
        risk = RiskEngine()

        # 1. Low Volatility (< 0.70x baseline) -> 0.75x
        risk._atr_h1_pts = 50.0
        with patch("src.core.risk_engine.mt5.copy_rates_from_pos") as mock_rates, \
             patch("src.core.risk_engine.mt5.symbol_info") as mock_si:
            mock_si.return_value = DummySymbolInfo(point=0.00001)
            dummy_r = [{"high": 1.35100, "low": 1.35000, "close": 1.35050} for _ in range(50)]
            mock_rates.return_value = dummy_r

            regime, mult, ratio = risk.get_volatility_regime_and_multiplier("GBPUSD-ECNc")
            self.assertEqual(regime, "LOW")
            self.assertEqual(mult, 0.75)
            self.assertLess(ratio, 0.70)

        # 2. High Volatility (> 1.20x baseline) -> 1.15x
        risk._atr_h1_pts = 150.0
        with patch("src.core.risk_engine.mt5.copy_rates_from_pos") as mock_rates, \
             patch("src.core.risk_engine.mt5.symbol_info") as mock_si:
            mock_si.return_value = DummySymbolInfo(point=0.00001)
            dummy_r = [{"high": 1.35100, "low": 1.35000, "close": 1.35050} for _ in range(50)]
            mock_rates.return_value = dummy_r

            regime, mult, ratio = risk.get_volatility_regime_and_multiplier("GBPUSD-ECNc")
            self.assertEqual(regime, "HIGH")
            self.assertEqual(mult, 1.15)
            self.assertGreater(ratio, 1.20)

    def test_peak_mfe_info_helper(self):
        position_manager._peak_mfe_points[9999] = 120.0
        position_manager._original_sl[9999] = 240.0
        peak_pts, peak_r = position_manager.get_peak_mfe_info(9999)
        self.assertEqual(peak_pts, 120.0)
        self.assertAlmostEqual(peak_r, 0.50, places=4)

    def test_is_london_ny_active_detection(self):
        # 10:00 WIB -> Tokyo (False)
        dt_tokyo = datetime(2026, 9, 10, 10, 0, tzinfo=WIB)
        self.assertFalse(position_manager.is_london_ny_active(dt_tokyo))

        # 14:00 WIB -> London Core start (True)
        dt_london_start = datetime(2026, 9, 10, 14, 0, tzinfo=WIB)
        self.assertTrue(position_manager.is_london_ny_active(dt_london_start))

        # 16:30 WIB -> London Core (True)
        dt_london = datetime(2026, 9, 10, 16, 30, tzinfo=WIB)
        self.assertTrue(position_manager.is_london_ny_active(dt_london))

        # 21:00 WIB -> New York (True)
        dt_ny = datetime(2026, 9, 10, 21, 0, tzinfo=WIB)
        self.assertTrue(position_manager.is_london_ny_active(dt_ny))

        # 02:00 WIB -> Late / Dead Zone (False)
        dt_dead = datetime(2026, 9, 10, 2, 0, tzinfo=WIB)
        self.assertFalse(position_manager.is_london_ny_active(dt_dead))

    def test_session_adaptive_break_even_and_partial_close(self):
        point = 0.00001
        si = DummySymbolInfo(point=point)
        # Clean initial state
        position_manager._break_even_tickets.discard(4001)
        # Position with TP 1000 pts (100 pips)
        pos = DummyPosition(ticket=4001, price_open=1.35000, tp=1.36000, sl=1.34500, volume=0.10)

        dummy_res = MagicMock()
        dummy_res.retcode = config.mt5.TRADE_RETCODE_DONE

        # 1. Di Sesi Tokyo (10:00 WIB): BEP aktif di 45% TP (450 pts)
        with patch("src.analytics.position_manager.is_london_ny_active", return_value=False):
            with patch("src.analytics.position_manager.mt5.order_send", return_value=dummy_res) as mock_send:
                # Profit 440 pts (< 450 pts) -> Belum BEP
                position_manager._check_break_even(pos, "GBPUSD-ECNc", 440.0, point, si)
                self.assertNotIn(4001, position_manager._break_even_tickets)
                # Profit 460 pts (>= 450 pts) -> BEP aktif
                position_manager._check_break_even(pos, "GBPUSD-ECNc", 460.0, point, si)
                self.assertIn(4001, position_manager._break_even_tickets)
                self.assertTrue(mock_send.called)

        # Reset state
        position_manager._break_even_tickets.discard(4001)

        # 2. Di Sesi London/NY (16:00 WIB): BEP aktif di 55% TP (550 pts)
        with patch("src.analytics.position_manager.is_london_ny_active", return_value=True):
            with patch("src.analytics.position_manager.mt5.order_send", return_value=dummy_res) as mock_send:
                # Profit 460 pts (< 550 pts) -> JANGAN BEP (memberi ruang nafas wick di London/NY)
                position_manager._check_break_even(pos, "GBPUSD-ECNc", 460.0, point, si)
                self.assertNotIn(4001, position_manager._break_even_tickets)
                # Profit 560 pts (>= 550 pts) -> BEP aktif
                position_manager._check_break_even(pos, "GBPUSD-ECNc", 560.0, point, si)
                self.assertIn(4001, position_manager._break_even_tickets)
                self.assertTrue(mock_send.called)

        # Reset state
        position_manager._break_even_tickets.discard(4001)

    def test_session_adaptive_trailing_and_h1_terminal(self):
        point = 0.00001
        si = DummySymbolInfo(point=point)
        pos = DummyPosition(ticket=5001, price_open=1.35000, tp=1.36000, sl=1.34500, volume=0.10)
        position_manager._ticket_setup_grades[5001] = "GRADE_A"
        position_manager._ticket_setup_grades[5002] = "GRADE_A"
        position_manager._ticket_setup_grades[5003] = "GRADE_A"

        dummy_res = MagicMock()
        dummy_res.retcode = config.mt5.TRADE_RETCODE_DONE

        # 1. Sesi Tokyo: Trailing aktif di 65% TP (650 pts), Stage 1 breathing 0.75x H1
        with patch("src.analytics.position_manager.is_london_ny_active", return_value=False):
            with patch("src.analytics.position_manager._get_atr_points_tf", return_value=200.0) as mock_atr:
                with patch("src.analytics.position_manager.mt5.order_send", return_value=dummy_res) as mock_send:
                    # Profit 640 pts (< 650 pts) -> Belum aktif
                    position_manager._check_trailing_stop(pos, "GBPUSD-ECNc", 640.0, 1.35640, point, si)
                    self.assertFalse(mock_send.called)
                    # Profit 660 pts (>= 650 pts) -> Aktif Stage 1 Breathing (0.75x H1 = 150 pts)
                    position_manager._check_trailing_stop(pos, "GBPUSD-ECNc", 660.0, 1.35660, point, si)
                    self.assertTrue(mock_send.called)
                    # new_sl = trail_ref (1.35660) - 150 pts (0.00150) = 1.35510
                    call_args = mock_send.call_args[0][0]
                    self.assertAlmostEqual(call_args["sl"], 1.35510, places=4)

        # 2. Sesi London/NY: Trailing aktif di 75% TP (750 pts), Stage 1 breathing 1.00x H1
        pos_ny = DummyPosition(ticket=5002, price_open=1.35000, tp=1.36000, sl=1.34500, volume=0.10)
        with patch("src.analytics.position_manager.is_london_ny_active", return_value=True):
            with patch("src.analytics.position_manager._get_atr_points_tf", return_value=200.0) as mock_atr:
                with patch("src.analytics.position_manager.mt5.order_send", return_value=dummy_res) as mock_send:
                    # Profit 660 pts (< 750 pts) -> Di London/NY JANGAN aktif dulu (cushion)
                    position_manager._check_trailing_stop(pos_ny, "GBPUSD-ECNc", 660.0, 1.35660, point, si)
                    self.assertFalse(mock_send.called)
                    # Profit 760 pts (>= 750 pts) -> Aktif Stage 1 Breathing London/NY (1.00x H1 = 200 pts)
                    position_manager._check_trailing_stop(pos_ny, "GBPUSD-ECNc", 760.0, 1.35760, point, si)
                    self.assertTrue(mock_send.called)
                    # new_sl = trail_ref (1.35760) - 200 pts (0.00200) = 1.35560
                    call_args = mock_send.call_args[0][0]
                    self.assertAlmostEqual(call_args["sl"], 1.35560, places=4)

        # 3. Stage 2 Terminal Lock: Verifikasi bahwa TIMEFRAME_H1 dipakai (BUKAN M30)
        pos_term = DummyPosition(ticket=5003, price_open=1.35000, tp=1.36000, sl=1.34500, volume=0.10)
        with patch("src.analytics.position_manager.is_london_ny_active", return_value=True):
            with patch("src.analytics.position_manager._get_atr_points_tf") as mock_atr:
                mock_atr.return_value = 200.0
                with patch("src.analytics.position_manager.mt5.order_send", return_value=dummy_res) as mock_send:
                    # Profit 920 pts (>= 90% TP) -> Terminal Lock
                    position_manager._check_trailing_stop(pos_term, "GBPUSD-ECNc", 920.0, 1.35920, point, si)
                    self.assertTrue(mock_send.called)
                    # Periksa bahwa timeframe yang dioper ke _get_atr_points_tf adalah TIMEFRAME_H1 (bukan M30)
                    tf_arg = mock_atr.call_args[0][1]
                    self.assertEqual(tf_arg, config.mt5.TIMEFRAME_H1)


if __name__ == "__main__":
    unittest.main()
