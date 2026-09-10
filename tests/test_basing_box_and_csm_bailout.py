"""
tests/test_basing_box_and_csm_bailout.py
Unit tests for Basing Box Breakout and Retest (M3 Mean Reversion),
Rollover Outlier Filter in wave_regime.py, and CSM Dynamic Bailout Protection in position_manager.py.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.indicators.wave_regime import detect_dynamic_basing_box
from src.analytics.position_manager import _check_csm_dynamic_bailout


def test_detect_dynamic_basing_box_normal_compression():
    """Test standard horizontal compression detection across 20 bars."""
    base_price = 1.00000
    atr_val = 0.0050  # 50 pips
    
    # 20 bars of tight oscillation within 15 pips (0.30x ATR)
    data = []
    for i in range(25):
        o = base_price + (i % 2) * 0.0010
        c = base_price + ((i + 1) % 2) * 0.0010
        h = max(o, c) + 0.0005
        l = min(o, c) - 0.0005
        dt = datetime(2026, 9, 8, 8 + (i % 12), 0)
        data.append({"time": int(dt.timestamp()), "open": o, "high": h, "low": l, "close": c})
        
    df = pd.DataFrame(data)
    box = detect_dynamic_basing_box(df, min_bars=10, max_bars=30, max_range_atr=1.60, atr_val=atr_val)
    
    assert box["is_compressing"] is True
    assert box["box_bars"] >= 10
    assert box["box_ceiling"] >= base_price + 0.0010
    assert box["box_floor"] <= base_price
    assert box["range_atr"] <= 1.60


def test_detect_dynamic_basing_box_rollover_spike_filtered():
    """
    Test that a 00:00 server rollover outlier wick (e.g. at 04:00 WIB)
    is sanitized and does not invalidate an otherwise tight compression box.
    """
    base_price = 0.99600
    atr_val = 0.0060  # 60 pips
    
    data = []
    # 20 bars, where bar index 10 has a massive rollover low spike to 0.99300 (300 pts) at 00:00 server
    for i in range(25):
        o = base_price + 0.0002
        c = base_price - 0.0002
        h = base_price + 0.0005
        l = base_price - 0.0005
        
        # Inject rollover spike at bar 10
        if i == 10:
            dt = datetime(2026, 9, 8, 0, 0) # 00:00 server
            l = base_price - 0.0035 # Massive outlier wick
        else:
            dt = datetime(2026, 9, 8, (i + 1) % 24, 0)
            
        data.append({"time": int(dt.timestamp()), "open": o, "high": h, "low": l, "close": c})
        
    df = pd.DataFrame(data)
    box = detect_dynamic_basing_box(df, min_bars=10, max_bars=30, max_range_atr=1.60, atr_val=atr_val)
    
    assert box["is_compressing"] is True
    # The box floor should be determined by the body box (min of open, close),
    # ignoring the 00:00 spike to 0.99300.
    assert box["box_floor"] > 0.99500
    assert box["range_atr"] < 1.0


def test_detect_dynamic_basing_box_wide_expansion_rejected():
    """Test that wide, high-volatility expanding bars are rejected (is_compressing=False)."""
    base_price = 1.00000
    atr_val = 0.0050
    
    data = []
    for i in range(20):
        # 3.0x ATR wild swings
        o = base_price - 0.0150 if i % 2 == 0 else base_price + 0.0150
        c = base_price + 0.0150 if i % 2 == 0 else base_price - 0.0150
        h = max(o, c) + 0.0020
        l = min(o, c) - 0.0020
        dt = datetime(2026, 9, 8, i, 0)
        data.append({"time": int(dt.timestamp()), "open": o, "high": h, "low": l, "close": c})
        
    df = pd.DataFrame(data)
    box = detect_dynamic_basing_box(df, min_bars=10, max_bars=30, max_range_atr=1.60, atr_val=atr_val)
    
    assert box["is_compressing"] is False


@patch("src.analytics.position_manager._load_telemetry")
@patch("src.analytics.currency_strength.get_csm_delta_for_symbol")
def test_csm_dynamic_bailout_no_premature_exit_on_opposed_open(mock_csm, mock_telemetry):
    """
    Simulate AUDCAD Ticket #675324733:
    Trade opened BUY when CSM was already -2.77.
    Live CSM shifted slightly to -3.52 (shift -0.75).
    Position at -0.25R.
    Must NOT trigger bailout because shift is < 2.50 and trade did not invert from positive/neutral!
    """
    mock_csm.return_value = -3.52
    mock_telemetry.return_value = {
        "trades": {
            "12345": {"csm_delta_open": -2.77}
        }
    }
    
    pos = MagicMock()
    pos.ticket = 12345
    pos.type = 0 # mt5.ORDER_TYPE_BUY
    pos.sl = 0.99417
    pos.price_open = 0.99475
    point = 0.00001
    profit_points = -15.0 # floating loss ~ -0.26R
    
    bailout = _check_csm_dynamic_bailout(
        pos=pos,
        symbol="AUDCAD-ECN",
        profit_points=profit_points,
        point=point,
        symbol_info=None,
        now=datetime.now()
    )
    
    assert bailout is False, "CSM bailout should NOT trigger when adverse shift is only -0.75"


@patch("src.analytics.position_manager._load_telemetry")
@patch("src.analytics.currency_strength.get_csm_delta_for_symbol")
def test_csm_dynamic_bailout_triggers_on_sharp_adverse_shift(mock_csm, mock_telemetry, monkeypatch):
    """
    Pilar 1 Reform (9 Sep 2026):
    Trade opened BUY when CSM was aligned (+1.50).
    Live CSM collapsed to -2.20 (shift -3.70 against BUY).
    1. At -0.30R: Bailout does NOT trigger (-0.30R > -0.50R).
    2. At -0.55R on first M15 bar: Records persistence, does NOT trigger (bars < 2).
    3. At -0.55R on second M15 bar: TRIGGERS bailout and enters 90m cooldown!
    """
    import config
    monkeypatch.setattr(config, "ENABLE_CSM_DYNAMIC_BAILOUT", True)
    mock_csm.return_value = -2.20
    mock_telemetry.return_value = {
        "trades": {
            "88888": {"csm_delta_open": 1.50}
        }
    }
    
    pos = MagicMock()
    pos.ticket = 88888
    pos.type = 0 # mt5.ORDER_TYPE_BUY
    pos.sl = 0.99400
    pos.price_open = 0.99500
    point = 0.00001
    
    # 1. At -0.30R (loss not deep enough) -> False
    bailout_mild = _check_csm_dynamic_bailout(
        pos=pos,
        symbol="EURUSD-ECN",
        profit_points=-30.0,
        point=point,
        symbol_info=None,
        now=datetime(2026, 9, 9, 10, 5)
    )
    assert bailout_mild is False, "CSM bailout should NOT trigger when loss is only -0.30R (min -0.50R required)"

    # 2. At -0.55R on Bar 1 (10:10) -> False (waiting for 2nd bar)
    bailout_bar1 = _check_csm_dynamic_bailout(
        pos=pos,
        symbol="EURUSD-ECN",
        profit_points=-55.0,
        point=point,
        symbol_info=None,
        now=datetime(2026, 9, 9, 10, 10)
    )
    assert bailout_bar1 is False, "CSM bailout should NOT trigger on first M15 bar (requires 2 consecutive M15 bars)"

    # 3. At -0.55R on Bar 2 (10:16, next M15 bar) -> True (triggers bailout)
    with patch("src.analytics.position_manager._close_position_by_ticket", return_value=True):
        bailout_bar2 = _check_csm_dynamic_bailout(
            pos=pos,
            symbol="EURUSD-ECN",
            profit_points=-55.0,
            point=point,
            symbol_info=None,
            now=datetime(2026, 9, 9, 10, 16)
        )
    assert bailout_bar2 is True, "CSM bailout SHOULD trigger when shift is >= 2.5 against trade, loss <= -0.50R, and persisted for 2 M15 bars"



def test_market_scanner_m3_radar_standbys_includes_basing_box():
    """Verify that get_radar_standbys extracts Basing Box Breakdown level and sets direction to -1 with opposed CSM."""
    from src.analytics.market_scanner import MarketScanner
    scanner = MarketScanner(symbols=["AUDCAD-ECN"])
    
    mid = 0.99630
    pt = 0.00001
    atr_val = 0.0060
    
    basing_box = {
        "is_compressing": True,
        "box_ceiling": 0.99750,
        "box_floor": 0.99650,
        "box_bars": 35,
        "range_atr": 1.42
    }
    macro = {
        "is_bull": False,
        "is_bear": False,
        "macro_corridor": "NEUTRAL",
        "csm_delta": -2.50,
        "basing_box": basing_box,
        "current_atr": atr_val,
        "dealing_range_pos": 0.50
    }
    
    standbys = scanner.get_radar_standbys("AUDCAD-ECN", mid=mid, macro=macro, pt=pt, atr_val=atr_val)
    m3 = next((s for s in standbys if s["type"] == "M3"), None)
    
    assert m3 is not None, "M3 standby should be present"
    assert m3["direction"] == -1, "M3 should point -1 (SELL) for broken basing floor with negative CSM"
    assert m3["price"] == 0.99650, "M3 target price should be the broken basing floor"
    assert "Basing Box" in m3["label"], "Label should indicate Basing Box"

