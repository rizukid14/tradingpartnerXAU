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
    def __init__(self, ticket=1001, symbol="GBPUSD-ECNc", pos_type=0, price_open=1.35000, sl=1.34500, tp=1.36000, volume=0.05, open_time=0):
        self.ticket = ticket
        self.symbol = symbol
        self.type = pos_type  # 0 = BUY, 1 = SELL
        self.price_open = price_open
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


def test_time_decay_stagnation():
    print("Testing Time-Decay Stagnation Exit...")
    now = 100000.0
    point = 0.00001
    si = DummySymbolInfo(point=point)

    # 1. Posisi stagnan 9 jam (>= 8 jam) saat sesi London-NY (16:00 WIB), floating +0.10R, Peak +0.15R (< +0.30R) -> HARUS CLOSE
    pos1 = DummyPosition(ticket=2001, open_time=now - (9 * 3600))  # 9 jam lalu
    position_manager._original_sl[2001] = 500.0  # SL distance = 500 pts
    position_manager._peak_mfe_points[2001] = 75.0  # Peak +75 pts = +0.15R
    profit_points = 50.0  # Curr +50 pts = +0.10R

    dt_london = datetime(2026, 8, 24, 16, 0, tzinfo=WIB)
    with patch("src.analytics.position_manager.datetime") as mock_dt:
        mock_dt.now.return_value = dt_london
        with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
            closed = position_manager._check_time_decay_stagnation(pos1, "GBPUSD-ECNc", profit_points, point, si, now)
            assert closed is True
            assert mock_close.called

    # 1b. Posisi stagnan 9 jam tapi di Sesi Tokyo (10:00 WIB) -> TIDAK DI-CLOSE (Stagnasi wajar di sesi sepi)
    dt_tokyo = datetime(2026, 8, 24, 10, 0, tzinfo=WIB)
    with patch("src.analytics.position_manager.datetime") as mock_dt:
        mock_dt.now.return_value = dt_tokyo
        with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
            closed = position_manager._check_time_decay_stagnation(pos1, "GBPUSD-ECNc", profit_points, point, si, now)
            assert closed is False
            assert not mock_close.called

    # 2. Posisi 9 jam lalu di sesi London (16:00 WIB), floating +0.10R, tapi PEAK PERNAH +0.50R (+250 pts) -> JANGAN DI-CLOSE (Let Winner Run)
    pos2 = DummyPosition(ticket=2002, open_time=now - (9 * 3600))
    position_manager._original_sl[2002] = 500.0
    position_manager._peak_mfe_points[2002] = 250.0  # Peak +0.50R >= +0.30R
    with patch("src.analytics.position_manager.datetime") as mock_dt:
        mock_dt.now.return_value = dt_london
        with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
            closed = position_manager._check_time_decay_stagnation(pos2, "GBPUSD-ECNc", profit_points, point, si, now)
            assert closed is False
            assert not mock_close.called

    # 3. Posisi baru 3 jam (kurang dari 8 jam) -> JANGAN DI-CLOSE
    pos3 = DummyPosition(ticket=2003, open_time=now - (3 * 3600))
    position_manager._original_sl[2003] = 500.0
    position_manager._peak_mfe_points[2003] = 50.0
    with patch("src.analytics.position_manager.datetime") as mock_dt:
        mock_dt.now.return_value = dt_london
        with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
            closed = position_manager._check_time_decay_stagnation(pos3, "GBPUSD-ECNc", profit_points, point, si, now)
            assert closed is False
            assert not mock_close.called

    print("  -> OK: Time-Decay Peak-Aware logic valid!")


def test_pre_rollover_shield():
    print("Testing Pre-Rollover Shield...")
    point = 0.00001
    si = DummySymbolInfo(point=point)
    now = 100000.0

    pos = DummyPosition(ticket=3001)
    position_manager._original_sl[3001] = 500.0  # SL = 500 pts

    # 1. Jam 04:15 WIB (dalam window 03:00 - 05:00), floating loss 48% SL (-240 pts) -> HARUS CUT LOSS
    dt_roll = datetime(2026, 8, 24, 4, 15, tzinfo=WIB)
    profit_loss_48 = -240.0  # -0.48R <= -0.45R threshold

    with patch("src.analytics.position_manager.datetime") as mock_dt:
        mock_dt.now.return_value = dt_roll
        with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
            closed = position_manager._check_pre_rollover_shield(pos, "GBPUSD-ECNc", profit_loss_48, point, si, now)
            assert closed is True
            assert mock_close.called

    # 2. Jam 14:00 WIB (di luar window 03:00 - 05:00), floating loss 48% -> TIDAK DI-CLOSE
    dt_day = datetime(2026, 8, 24, 14, 0, tzinfo=WIB)
    with patch("src.analytics.position_manager.datetime") as mock_dt:
        mock_dt.now.return_value = dt_day
        with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True) as mock_close:
            closed = position_manager._check_pre_rollover_shield(pos, "GBPUSD-ECNc", profit_loss_48, point, si, now)
            assert closed is False
            assert not mock_close.called

    print("  -> OK: Pre-Rollover Shield valid!")


def test_dynamic_volatility_scaling():
    print("Testing Dynamic Volatility Scaling (Ide 4)...")
    risk = RiskEngine()

    # 1. Low Volatility (< 0.70x baseline) -> 0.75x
    risk._atr_h1_pts = 50.0
    with patch("src.core.risk_engine.mt5.copy_rates_from_pos") as mock_rates, \
         patch("src.core.risk_engine.mt5.symbol_info") as mock_si:
        mock_si.return_value = DummySymbolInfo(point=0.00001)
        # Dummy rates producing baseline ATR = 100.0 pts (0.00100)
        dummy_r = [{"high": 1.35100, "low": 1.35000, "close": 1.35050} for _ in range(50)]
        mock_rates.return_value = dummy_r

        regime, mult, ratio = risk.get_volatility_regime_and_multiplier("GBPUSD-ECNc")
        assert regime == "LOW"
        assert mult == 0.75
        assert ratio < 0.70

    # 2. High Volatility (> 1.20x baseline) -> 1.15x
    risk._atr_h1_pts = 150.0
    with patch("src.core.risk_engine.mt5.copy_rates_from_pos") as mock_rates, \
         patch("src.core.risk_engine.mt5.symbol_info") as mock_si:
        mock_si.return_value = DummySymbolInfo(point=0.00001)
        dummy_r = [{"high": 1.35100, "low": 1.35000, "close": 1.35050} for _ in range(50)]
        mock_rates.return_value = dummy_r

        regime, mult, ratio = risk.get_volatility_regime_and_multiplier("GBPUSD-ECNc")
        assert regime == "HIGH"
        assert mult == 1.15
        assert ratio > 1.20

    print("  -> OK: Volatility Regime Scaling valid!")


def test_peak_mfe_info_helper():
    print("Testing Peak MFE info getter...")
    position_manager._peak_mfe_points[9999] = 120.0
    position_manager._original_sl[9999] = 240.0
    peak_pts, peak_r = position_manager.get_peak_mfe_info(9999)
    assert peak_pts == 120.0
    assert abs(peak_r - 0.50) < 1e-5
    print("  -> OK: Peak MFE info getter valid!")


if __name__ == "__main__":
    test_time_decay_stagnation()
    test_pre_rollover_shield()
    test_dynamic_volatility_scaling()
    test_peak_mfe_info_helper()
    print("\nALL IDE 1 & IDE 4 TESTS PASSED SUCCESSFULLY! (4/4)")
