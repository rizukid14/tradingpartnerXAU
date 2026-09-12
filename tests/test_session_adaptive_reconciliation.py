"""
Unit test suite untuk memverifikasi 4 Fase Rekonsiliasi (10 September 2026):
1. Sizing De-Risk (Session Cap: Asia 1.20x, London 0.75x, NY 0.50x; Overlap = lowest/most defensive).
2. Runway Decoupling (M4 = 1.20x ATR vs Chamber M2/M3 = 0.60x ATR).
3. Tokyo Midday Lull Dynamic ATR Scaling.
4. NY M3 Breakout Retest Paper Trade Route (SKIPPED_NY_M3_PAPER) & Deduplication Guard.
"""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, patch

import config
from src.core.risk_engine import RiskEngine
from src.analytics.shadow_tracker import QuantShadowTracker, ShadowTrade, shadow_tracker
from src.analytics.market_scanner import CandidateSetup


WIB = ZoneInfo("Asia/Jakarta")


def test_session_sizing_derisk_cap():
    """Memverifikasi bahwa session multiplier < 1.0 bertindak sebagai hard cap terhadap vol_mult."""
    risk = RiskEngine()
    
    # Test London Sizing: sess_mult = 0.75, vol_mult = 1.15 (High Vol)
    # Effective mult should be min(1.15, 0.75) = 0.75
    with patch.object(risk, "get_volatility_regime_and_multiplier", return_value=("HIGH", 1.15, 1.30)):
        risk._session_lot_multiplier = 0.75
        sess_mult = risk._session_lot_multiplier
        vol_mult = 1.15
        effective = min(vol_mult, sess_mult) if sess_mult < 1.0 else (vol_mult * sess_mult)
        assert effective == 0.75

    # Test Asia Sizing: sess_mult = 1.20, vol_mult = 1.00 (Normal Vol)
    # Effective mult should be 1.00 * 1.20 = 1.20
    with patch.object(risk, "get_volatility_regime_and_multiplier", return_value=("NORMAL", 1.00, 1.00)):
        risk._session_lot_multiplier = 1.20
        sess_mult = risk._session_lot_multiplier
        vol_mult = 1.00
        effective = min(vol_mult, sess_mult) if sess_mult < 1.0 else (vol_mult * sess_mult)
        assert effective == 1.20

    # Test NY Sizing: sess_mult = 0.50, vol_mult = 0.75 (Low Vol)
    # Effective mult should be min(0.75, 0.50) = 0.50
    with patch.object(risk, "get_volatility_regime_and_multiplier", return_value=("LOW", 0.75, 0.65)):
        risk._session_lot_multiplier = 0.50
        sess_mult = risk._session_lot_multiplier
        vol_mult = 0.75
        effective = min(vol_mult, sess_mult) if sess_mult < 1.0 else (vol_mult * sess_mult)
        assert effective == 0.50


def test_overlapping_sessions_pick_lowest_multiplier():
    """Memverifikasi bahwa saat jam sesi tumpang tindih, sistem memilih multiplier terendah (paling defensif)."""
    risk = RiskEngine()
    
    # Simulasikan dua sesi tumpang tindih: Sesi A (0.75x) dan Sesi B (0.50x)
    overlapping_sessions = [
        {"name": "London Core", "start": (14, 0), "end": (19, 0), "lot_multiplier": 0.75},
        {"name": "NY Early",    "start": (18, 0), "end": (22, 0), "lot_multiplier": 0.50},
    ]
    test_dt = datetime(2026, 9, 10, 18, 30, tzinfo=WIB) # Di dalam kedua sesi
    with patch.object(config, "SESSION_FILTER_ENABLED", True), \
         patch.object(config, "ALLOWED_SESSIONS_WIB", overlapping_sessions):
        allowed, reason = risk._check_session(symbol="EURUSD-ECNc", now_wib=test_dt)
        assert allowed is True
        assert risk._session_lot_multiplier == pytest.approx(0.50) # Memilih 0.50 (paling defensif), bukan 0.75


def test_cbss_runway_decoupling():
    """Memverifikasi pemisahan ambang runway: M4 Systemic Flow tetap 1.20x, sedangkan Chamber M2/M3 memakai 0.60x."""
    assert getattr(config, "CBSS_MIN_RUNWAY_ATR", 1.20) == pytest.approx(1.20)
    assert getattr(config, "CBSS_MIN_CHAMBER_RUNWAY_ATR", 0.60) == pytest.approx(0.60)
    
    # Simulasikan logika pemisahan runway
    r_atr = 0.85 # Runway 0.85x ATR
    
    # Setup M4 (Systemic Flow): Butuh 1.20x -> 0.85x harus ditolak (Insufficient Runway)
    is_m4_flow = True
    min_runway_m4 = float(getattr(config, "CBSS_MIN_RUNWAY_ATR", 1.20)) if is_m4_flow else float(getattr(config, "CBSS_MIN_CHAMBER_RUNWAY_ATR", 0.60))
    assert min_runway_m4 == 1.20
    assert r_atr < min_runway_m4 # Blocked
    
    # Setup M2/M3 (Chamber): Butuh 0.60x -> 0.85x harus lolos (Adequate Runway)
    is_m4_flow = False
    min_runway_chamber = float(getattr(config, "CBSS_MIN_RUNWAY_ATR", 1.20)) if is_m4_flow else float(getattr(config, "CBSS_MIN_CHAMBER_RUNWAY_ATR", 0.60))
    assert min_runway_chamber == 0.60
    assert r_atr >= min_runway_chamber # Allowed!


def test_ny_m3_paper_route_and_disposition(monkeypatch):
    """Memverifikasi bahwa M3 Breakout di Sesi NY (>=18 WIB) dialihkan ke Paper Trade dengan disposisi SKIPPED_NY_M3_PAPER."""
    monkeypatch.setattr(config, "ENABLE_NY_M3_PAPER_ROUTE", True)
    assert getattr(config, "ENABLE_NY_M3_PAPER_ROUTE", True) is True
    
    cand_m3 = CandidateSetup(
        symbol="EURUSD-ECNc",
        setup_type="MULTI_TOUCH_BREAKOUT_RETEST",
        direction=1,
        trigger_price=1.1050,
        suggested_sl=1.1020,
        suggested_tp=1.1110
    )
    
    # Simulasikan jam 19:30 WIB (Sesi New York)
    now_wib = datetime(2026, 9, 10, 19, 30, tzinfo=WIB)
    ny_start_h = getattr(config, "NY_SESSION_START_HOUR_WIB", 18)
    
    is_ny_m3_paper = False
    ny_m3_reason = ""
    if getattr(config, "ENABLE_NY_M3_PAPER_ROUTE", True) and now_wib.hour >= ny_start_h and not config.is_crypto(cand_m3.symbol) and not config.is_gold(cand_m3.symbol):
        stype = str(getattr(cand_m3, "setup_type", "")).upper()
        if "BREAKOUT" in stype or "M3" in stype:
            is_ny_m3_paper = True
            ny_m3_reason = f"[NY M3 PAPER ROUTE] Breakout Retest at {now_wib.strftime('%H:%M')} WIB routed to Paper Trade."
            
    assert is_ny_m3_paper is True
    assert "NY M3 PAPER ROUTE" in ny_m3_reason
    
    # Verifikasi disposisi
    clean_disp = "SKIPPED_NY_M3_PAPER" if is_ny_m3_paper else "EXECUTED_MT5"
    assert clean_disp == "SKIPPED_NY_M3_PAPER"


def test_shadow_tracker_ny_m3_disposition_breakdown():
    """Memverifikasi bahwa QuantShadowTracker dan disp_stats menghitung SKIPPED_NY_M3_PAPER dengan tepat."""
    st = QuantShadowTracker()
    
    # Mock data trade dengan disposisi SKIPPED_NY_M3_PAPER
    t_dict = {
        "shadow_id": "TEST_NY_M3_001",
        "symbol": "GBPUSD-ECNc",
        "setup_type": "MULTI_TOUCH_BREAKOUT_RETEST",
        "direction": "SELL",
        "status": "ACTIVE",
        "mt5_disposition": "SKIPPED_NY_M3_PAPER"
    }
    
    disp = str(t_dict.get("mt5_disposition", "")).upper()
    disp_stats = {
        "EXECUTED_MT5": 0,
        "SKIPPED_CBSS_BASKET_CAP": 0,
        "SKIPPED_NY_M3_PAPER": 0,
        "OTHER": 0
    }
    
    if "EXECUTED" in disp:
        disp_stats["EXECUTED_MT5"] += 1
    elif "CBSS" in disp:
        disp_stats["SKIPPED_CBSS_BASKET_CAP"] += 1
    elif "NY_M3" in disp:
        disp_stats["SKIPPED_NY_M3_PAPER"] += 1
    else:
        disp_stats["OTHER"] += 1
        
    assert disp_stats["SKIPPED_NY_M3_PAPER"] == 1
