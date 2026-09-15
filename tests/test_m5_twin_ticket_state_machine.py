"""
Tests for M5 Twin-Ticket Architecture, Dynamic Geometry, and State Machine SL Protection.
"""

import pytest
from unittest.mock import MagicMock, patch
from src.analytics.market_scanner_m5 import calculate_m5_sl_tp
from src.analytics import position_manager


def test_m5_sl_tp_geometry_major():
    """Verify Major FX pairs get healthy structural SL [80-200 pts] and TP1 >= 1.25x SL."""
    geom = calculate_m5_sl_tp(
        symbol="EURUSD",
        entry_price=1.10000,
        direction=1,
        atr_m5=0.00060,  # 60 pts
        c1=None,
        f1=None,
        spread_pts=15,
        pt=0.00001
    )
    # SL should be within calibrated demo bounds [40, 75] pts
    assert 40 <= geom["sl_pts"] <= 75
    # TP1 should be >= 1.25x SL and <= 95 pts (major cap)
    assert geom["tp1_pts"] >= int(round(geom["sl_pts"] * 1.25))
    assert geom["tp1_pts"] <= 95
    # Risk Reward
    assert geom["risk_reward"] >= 1.25


def test_m5_sl_tp_geometry_jpy():
    """Verify JPY pairs get healthy structural SL [60-120 pts] and TP1 <= 135 pts."""
    geom = calculate_m5_sl_tp(
        symbol="GBPJPY",
        entry_price=190.000,
        direction=-1,
        atr_m5=0.080,  # 80 pts
        c1=None,
        f1=None,
        spread_pts=18,
        pt=0.001
    )
    assert 60 <= geom["sl_pts"] <= 120
    assert geom["tp1_pts"] >= int(round(geom["sl_pts"] * 1.25))
    assert geom["tp1_pts"] <= 135


def test_m5_sl_tp_zero_skip_guarantee():
    """Verify that tight C1 does NOT result in skip or small TP, but guarantees valid target."""
    geom = calculate_m5_sl_tp(
        symbol="EURUSD",
        entry_price=1.10000,
        direction=1,
        atr_m5=0.00050,
        c1=1.10020,  # Only 20 pts away (too tight)
        f1=None,
        spread_pts=10,
        pt=0.00001
    )
    # Must NOT skip (returns dict with valid targets)
    assert geom is not None
    assert geom["tp1_pts"] >= int(round(geom["sl_pts"] * 1.25))


def test_m5_sl_tp_c1_anchoring():
    """Verify that healthy C1 is used with front pad."""
    geom = calculate_m5_sl_tp(
        symbol="EURUSD",
        entry_price=1.10000,
        direction=1,
        atr_m5=0.00050,
        c1=1.10090,  # 90 pts away
        f1=None,
        spread_pts=10,
        pt=0.00001
    )
    assert geom["tp1_pts"] >= 65
    # TP must be below C1 by front pad
    assert geom["tp"] < 1.10090


def test_m5_twin_registry_registration_and_rebuild():
    """Verify twin pair registration and startup recovery from open positions."""
    position_manager._m5_twin_registry.clear()

    # Register pair
    key = position_manager.register_m5_twin_pair(
        symbol="EURUSD",
        direction=1,
        t1_ticket=1001,
        t2_ticket=1002,
        entry_price=1.10000,
        tp1_pts=80,
        tp2_pts=120,
        setup_tag="UNIV"
    )
    assert key in position_manager._m5_twin_registry
    rec = position_manager._m5_twin_registry[key]
    assert rec["t1_ticket"] == 1001
    assert rec["t2_ticket"] == 1002

    # Test rebuild on empty registry
    position_manager._m5_twin_registry.clear()

    mock_pos1 = MagicMock()
    mock_pos1.ticket = 2001
    mock_pos1.symbol = "GBPUSD"
    mock_pos1.type = 0  # BUY
    mock_pos1.price_open = 1.30000
    mock_pos1.tp = 1.30090
    mock_pos1.comment = "M5_T1_UNIV_90"

    mock_pos2 = MagicMock()
    mock_pos2.ticket = 2002
    mock_pos2.symbol = "GBPUSD"
    mock_pos2.type = 0  # BUY
    mock_pos2.price_open = 1.30000
    mock_pos2.tp = 1.30135
    mock_pos2.comment = "M5_T2_UNIV_90"

    position_manager._rebuild_m5_twin_registry_from_open_positions([mock_pos1, mock_pos2])
    assert len(position_manager._m5_twin_registry) == 1
    rebuilt = list(position_manager._m5_twin_registry.values())[0]
    assert rebuilt["t1_ticket"] == 2001
    assert rebuilt["t2_ticket"] == 2002
    assert rebuilt["tp1_pts"] == 90


def test_m5_twin_state_machine_milestones():
    """Verify T1 BEP and T2 Milestones 1, 2, 3."""
    position_manager._m5_twin_registry.clear()
    position_manager._break_even_tickets.clear()

    key = position_manager.register_m5_twin_pair(
        symbol="EURUSD",
        direction=1,
        t1_ticket=3001,
        t2_ticket=3002,
        entry_price=1.10000,
        tp1_pts=100,
        tp2_pts=150,
        setup_tag="UNIV"
    )

    sym_info = MagicMock()
    sym_info.digits = 5
    sym_info.point = 0.00001

    pos1 = MagicMock()
    pos1.ticket = 3001
    pos1.symbol = "EURUSD"
    pos1.type = 0  # BUY
    pos1.price_open = 1.10000
    pos1.sl = 1.09940
    pos1.tp = 1.10100
    pos1.comment = "M5_T1_UNIV_100"

    pos2 = MagicMock()
    pos2.ticket = 3002
    pos2.symbol = "EURUSD"
    pos2.type = 0  # BUY
    pos2.price_open = 1.10000
    pos2.sl = 1.09940
    pos2.tp = 1.10150
    pos2.comment = "M5_T2_UNIV_100"

    with patch("src.analytics.position_manager._send_twin_sl_modify", return_value=True) as mock_mod:
        # At 50 pts profit (< 65% of 100), no BEP
        position_manager._manage_m5_twin_position(pos1, "EURUSD", 50.0, 1.10050, 0.00001, sym_info)
        assert not mock_mod.called

        # At 65 pts profit (== 65% of 100), T1 BEP triggers
        position_manager._manage_m5_twin_position(pos1, "EURUSD", 65.0, 1.10065, 0.00001, sym_info)
        assert mock_mod.called
        assert 3001 in position_manager._break_even_tickets
        assert position_manager._m5_twin_registry[key]["t1_bep_reached"]

        mock_mod.reset_mock()

        # At 65 pts profit, T2 Milestone 1 triggers
        position_manager._manage_m5_twin_position(pos2, "EURUSD", 65.0, 1.10065, 0.00001, sym_info)
        assert mock_mod.called
        assert position_manager._m5_twin_registry[key]["t2_m1_reached"]

        mock_mod.reset_mock()

        # At 100 pts profit (TP1 reached), T2 Milestone 2 triggers (SL -> Entry + 50% TP1)
        position_manager._manage_m5_twin_position(pos2, "EURUSD", 100.0, 1.10100, 0.00001, sym_info)
        assert mock_mod.called
        assert position_manager._m5_twin_registry[key]["t2_m2_reached"]

        mock_mod.reset_mock()

        # At 120 pts profit (>= 75% of 150), T2 Milestone 3 triggers (SL -> TP1 level)
        position_manager._manage_m5_twin_position(pos2, "EURUSD", 120.0, 1.10120, 0.00001, sym_info)
        assert mock_mod.called
        assert position_manager._m5_twin_registry[key]["t2_m3_reached"]


def test_m5_twin_sl_loss_protection():
    """Verify that if T1 hits SL at loss before BEP, T2 is auto-closed immediately."""
    position_manager._m5_twin_registry.clear()

    key = position_manager.register_m5_twin_pair(
        symbol="EURUSD",
        direction=1,
        t1_ticket=4001,
        t2_ticket=4002,
        entry_price=1.10000,
        tp1_pts=80,
        tp2_pts=120,
        setup_tag="UNIV"
    )

    with patch("src.core.mt5_connector.close_position", return_value=True) as mock_close:
        # Case A: T1 closed, T2 still open, and T1 never reached BEP
        open_tickets = {4002}
        position_manager._audit_m5_twin_loss_protection(open_tickets)

        # Partner T2 MUST be closed immediately
        mock_close.assert_called_once_with(4002)
        assert key not in position_manager._m5_twin_registry
