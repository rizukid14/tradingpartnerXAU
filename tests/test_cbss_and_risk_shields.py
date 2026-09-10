"""
tests/test_cbss_and_risk_shields.py
====================================
Comprehensive test suite for the 4-Pilar Systemic Improvements (9 Sep 2026):
1. CBSS (Currency Basket Structural Synchronization) Engine:
   - Pair-to-Basket Mapping & Bilateral Runway Calculation
   - Local Pair G3 Wall Veto (The EURAUD Law: EURAUD blocked, EURCAD allowed)
   - Basket Concurrency Cap (Max 2 trades per currency basket in same direction)
   - Laggard / Top Runway Selector Ranking
2. Economic News Volatility Blackout Window Gate (±30m US vs Non-USD)
3. Night Freeze Gate (23:00–07:00 WIB for FX, BTC exempt)
4. Daily Profit Target 7.0% Net Equity Gain Lockout
5. Session NY 0.50x Lot Multiplier
"""

import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import MagicMock, patch

import config
from src.analytics.basket_sync_engine import (
    get_currency_basket_pairs,
    get_pair_currencies,
    calculate_pair_runway,
    is_pair_blocked_by_g3_wall,
    check_basket_concurrency_cap,
    rank_basket_candidates_by_runway,
    clean_symbol
)
from src.analytics.economic_calendar import EconomicCalendar
from src.core.risk_engine import RiskEngine

WIB = ZoneInfo("Asia/Jakarta")


# =============================================================================
#  1. CBSS BASKET SYNC ENGINE TESTS
# =============================================================================

def test_cbss_currency_basket_mapping():
    """Verify constituent mapping for major currency baskets."""
    eur_pairs = get_currency_basket_pairs("EUR")
    assert "EURUSD" in eur_pairs
    assert "EURAUD" in eur_pairs
    assert "EURCAD" in eur_pairs
    assert len(eur_pairs) >= 6

    jpy_pairs = get_currency_basket_pairs("JPY")
    assert "USDJPY" in jpy_pairs
    assert "EURJPY" in jpy_pairs
    assert "GBPJPY" in jpy_pairs

    base, quote = get_pair_currencies("EURUSD-ECNc")
    assert base == "EUR"
    assert quote == "USD"

    base_jpy, quote_jpy = get_pair_currencies("GBPJPY.c")
    assert base_jpy == "GBP"
    assert quote_jpy == "JPY"


def test_cbss_pair_runway_calculation():
    """Test bilateral runway calculation normalized by ATR H1."""
    macro_cache = {
        "EURUSD": {
            "current_mid": 1.0500,
            "atr_h1": 0.0050,  # 50 pips
            "imm_ceiling_c1": 1.0600,  # +100 pips = 2.0x ATR
            "imm_floor_f1": 1.0450,    # -50 pips = 1.0x ATR
            "imm_ceiling_c1_grade": "GRADE_2_INTERMEDIATE",
            "imm_floor_f1_grade": "GRADE_3_MACRO",
        }
    }

    # BUY runway towards C1
    buy_info = calculate_pair_runway("EURUSD", direction=1, macro_cache=macro_cache)
    assert buy_info["runway_atr"] == pytest.approx(2.0, 0.05)
    assert buy_info["is_at_wall_g3"] is False

    # SELL runway towards F1
    sell_info = calculate_pair_runway("EURUSD", direction=-1, macro_cache=macro_cache)
    assert sell_info["runway_atr"] == pytest.approx(1.0, 0.05)


def test_cbss_local_pair_veto_the_euraud_law():
    """
    CRITICAL USER REQUIREMENT TEST (The EURAUD Law):
    If EURAUD is right at a G3 macro floor (dist <= 0.35x ATR),
    EURAUD SELL is BLOCKED.
    However, EURCAD with ample runway (>= 1.2x ATR) is CLEAR (NOT BLOCKED)!
    """
    macro_cache = {
        "EURAUD": {
            "current_mid": 1.6205,
            "atr_h1": 0.0080,
            "imm_floor_f1": 1.6200,  # Only 5 pips away! (0.0005 / 0.0080 = 0.06x ATR <= 0.35x)
            "imm_floor_f1_grade": "GRADE_3_MACRO",
        },
        "EURCAD": {
            "current_mid": 1.4850,
            "atr_h1": 0.0060,
            "imm_floor_f1": 1.4730,  # 120 pips away! (0.0120 / 0.0060 = 2.0x ATR)
            "imm_floor_f1_grade": "GRADE_3_MACRO",
        }
    }

    # 1. EURAUD SELL should be VETOED by local G3 wall
    is_blocked_ea, reason_ea = is_pair_blocked_by_g3_wall("EURAUD", direction=-1, macro_cache=macro_cache)
    assert is_blocked_ea is True
    assert "[CBSS VETO]" in reason_ea
    assert "EURAUD" in reason_ea

    # 2. EURCAD SELL should be CLEAR to run!
    is_blocked_ec, reason_ec = is_pair_blocked_by_g3_wall("EURCAD", direction=-1, macro_cache=macro_cache)
    assert is_blocked_ec is False
    assert reason_ec == "CLEAR"


def test_cbss_basket_concurrency_cap():
    """Test concurrency cap (max 2 active positions per currency in same direction)."""
    # Create 2 mock EUR BUY positions
    pos1 = MagicMock()
    pos1.symbol = "EURUSD-ECN"
    pos1.type = 0  # BUY
    
    pos2 = MagicMock()
    pos2.symbol = "EURGBP-ECN"
    pos2.type = 0  # BUY

    # Order 3rd EUR pair in same direction (EURCAD BUY) -> should be capped
    cap_ok, reason = check_basket_concurrency_cap(
        symbol="EURCAD-ECN",
        direction=1,  # BUY EUR
        active_positions=[pos1, pos2],
        active_orders=[]
    )
    assert cap_ok is False
    assert "[CBSS CAP] Basket EUR sudah memiliki 2/2 trade aktif searah" in reason

    # Order in opposite direction (e.g. EURCAD SELL) -> allowed
    cap_ok_opp, _ = check_basket_concurrency_cap(
        symbol="EURCAD-ECN",
        direction=-1,  # SELL EUR
        active_positions=[pos1, pos2],
        active_orders=[]
    )
    assert cap_ok_opp is True


def test_cbss_rank_basket_candidates():
    """Verify that candidate pairs are ranked in descending order of ZCE runway."""
    macro_cache = {
        "EURUSD": {"current_mid": 1.0500, "atr_h1": 0.0050, "imm_ceiling_c1": 1.0550},  # 1.0x ATR
        "EURCAD": {"current_mid": 1.4800, "atr_h1": 0.0050, "imm_ceiling_c1": 1.4920},  # 2.4x ATR
        "EURAUD": {"current_mid": 1.6200, "atr_h1": 0.0080, "imm_ceiling_c1": 1.6280},  # 1.0x ATR
    }

    ranked = rank_basket_candidates_by_runway(["EURUSD", "EURCAD", "EURAUD"], direction=1, macro_cache=macro_cache)
    assert len(ranked) == 3
    # EURCAD has highest runway (2.4x) so it must be first
    assert ranked[0]["clean_symbol"] == "EURCAD"
    assert ranked[0]["runway_atr"] == pytest.approx(2.4, 0.05)


# =============================================================================
#  2. ECONOMIC NEWS VOLATILITY BLACKOUT TESTS
# =============================================================================

def test_news_blackout_us_global_freezes_all_fx():
    """US High-Impact event (e.g. CPI) must freeze ALL FX pairs within ±30m."""
    cal = EconomicCalendar()
    ref_time = datetime(2026, 9, 9, 19, 30, tzinfo=WIB)  # 19:30 WIB
    
    # Event at 19:45 WIB (15 minutes ahead)
    event_dt = datetime(2026, 9, 9, 19, 45, tzinfo=WIB)
    mock_events = [
        {
            "name": "US CPI (Inflation)",
            "dt": event_dt,
            "impact": "HIGH",
            "country": "US",
            "currency": "USD"
        }
    ]

    with patch.object(cal, "get_events", return_value=mock_events):
        # EURUSD must be blocked
        is_blocked, reason = cal.is_in_news_blackout(symbol="EURUSD", now_wib=ref_time)
        assert is_blocked is True
        assert "US High-Impact News Blackout" in reason

        # Cross pair (EURGBP) must ALSO be blocked because US news affects the entire liquidity pool
        is_blocked_cross, reason_cross = cal.is_in_news_blackout(symbol="EURGBP", now_wib=ref_time)
        assert is_blocked_cross is True
        assert "US High-Impact News Blackout" in reason_cross


def test_news_blackout_non_usd_pair_specific():
    """Non-USD High-Impact event (e.g. BOE Rate Decision) freezes only GBP pairs."""
    cal = EconomicCalendar()
    ref_time = datetime(2026, 9, 17, 17, 50, tzinfo=WIB)
    event_dt = datetime(2026, 9, 17, 18, 0, tzinfo=WIB)  # 10 minutes ahead
    
    mock_events = [
        {
            "name": "BOE Rate Decision",
            "dt": event_dt,
            "impact": "HIGH",
            "country": "GB",
            "currency": "GBP"
        }
    ]

    with patch.object(cal, "get_events", return_value=mock_events):
        # GBP pair (GBPUSD) is blocked
        is_blocked_gbp, reason_gbp = cal.is_in_news_blackout(symbol="GBPUSD", now_wib=ref_time)
        assert is_blocked_gbp is True
        assert "GBP" in reason_gbp

        # Non-GBP pair (AUDCAD) is NOT blocked
        is_blocked_cad, _ = cal.is_in_news_blackout(symbol="AUDCAD", now_wib=ref_time)
        assert is_blocked_cad is False


# =============================================================================
#  3. NIGHT FREEZE & SPREAD SHIELD TESTS
# =============================================================================

def test_night_freeze_blocks_fx_allows_btc():
    """Night freeze blocks new FX orders between 23:00 and 07:00 WIB; BTC allowed 24/7."""
    risk = RiskEngine()
    
    # 23:30 WIB -> Night freeze active
    time_night = datetime(2026, 9, 9, 23, 30, tzinfo=WIB)
    
    # FX blocked
    ok_fx, msg_fx = risk._check_night_freeze(symbol="EURUSD", now_wib=time_night)
    assert ok_fx is False
    assert "Night Freeze" in msg_fx

    # BTC allowed
    ok_btc, _ = risk._check_night_freeze(symbol="BTCUSD", now_wib=time_night)
    assert ok_btc is True

    # 15:00 WIB (London session) -> Allowed for all
    time_day = datetime(2026, 9, 9, 15, 0, tzinfo=WIB)
    ok_day, _ = risk._check_night_freeze(symbol="EURUSD", now_wib=time_day)
    assert ok_day is True


# =============================================================================
#  4. DAILY PROFIT TARGET 7.0% NET EQUITY GAIN TESTS
# =============================================================================

def test_daily_profit_target_7_percent_lockout():
    """Real-time net equity gain >= 7.0% locks trading until rollover."""
    with patch.object(RiskEngine, "_save_state"):
        risk = RiskEngine()
        risk._start_day_balance = 10000.0
        risk._start_day_date = "2026-09-09"
        risk._daily_profit_locked = False

        # 1. Equity at $10,400 (+4.0% gain) -> Not locked
        mock_acc_4pct = MagicMock()
        mock_acc_4pct.equity = 10400.0
        mock_acc_4pct.balance = 10000.0

        with patch("config.mt5.account_info", return_value=mock_acc_4pct):
            ok, _ = risk._check_daily_profit_target()
            assert ok is True
            assert risk._daily_profit_locked is False

        # 2. Equity reaches $10,750 (+7.5% gain >= 7.0% target) -> LOCKED!
        mock_acc_7pct = MagicMock()
        mock_acc_7pct.equity = 10750.0
        mock_acc_7pct.balance = 10000.0

        with patch("config.mt5.account_info", return_value=mock_acc_7pct):
            ok_locked, msg = risk._check_daily_profit_target()
            assert ok_locked is False
            assert risk._daily_profit_locked is True
            assert "Target Profit Harian Tercapai" in msg
            assert "+7.50% >= +7.0%" in msg

        # 3. Subsequent check remains locked
        with patch("config.mt5.account_info", return_value=mock_acc_7pct):
            ok_still, msg_still = risk._check_daily_profit_target()
            assert ok_still is False
            assert "Target Profit Harian Telah Terkunci" in msg_still


# =============================================================================
#  5. SESSION NY 0.50X LOT MULTIPLIER TESTS
# =============================================================================

def test_session_ny_lot_multiplier():
    """NY Session (18:00 - 00:00 WIB) sets lot multiplier to 0.50x."""
    risk = RiskEngine()
    
    # 19:00 WIB -> NY session
    time_ny = datetime(2026, 9, 9, 19, 0, tzinfo=WIB)
    ok, _ = risk._check_session(symbol="EURUSD", now_wib=time_ny)
    assert ok is True
    assert risk._session_lot_multiplier == pytest.approx(0.50, 0.01)

    # 15:00 WIB -> London session (1.0x)
    time_ldn = datetime(2026, 9, 9, 15, 0, tzinfo=WIB)
    ok_ldn, _ = risk._check_session(symbol="EURUSD", now_wib=time_ldn)
    assert ok_ldn is True
    assert risk._session_lot_multiplier == pytest.approx(1.0, 0.01)


# =============================================================================
#  6. CBSS BASKET FULL -> PAPER TRADE ROUTING TEST
# =============================================================================

def test_cbss_basket_full_routes_to_paper_trade():
    """When CBSS basket concurrency cap is reached, candidate is routed to paper trade (0 token)."""
    from main import run_scanner_trading_cycle
    from src.analytics.market_scanner import CandidateSetup

    cand = CandidateSetup(
        symbol="EURCAD-ECN",
        setup_type="UNIVERSAL_LIQUIDITY_SWEEP",
        direction=1,
        trigger_price=1.48500,
        suggested_sl=1.48200,
        suggested_tp=1.49100,
        action_tier="CBSS_CAP_BLOCKED",
        metadata={
            "cbss_cap_blocked": True,
            "cbss_cap_reason": "[CBSS CAP] Basket EUR saturated: 2/2 active LONG positions (EURUSD, EURGBP)"
        }
    )

    mock_risk = MagicMock()
    mock_risk.can_trade.return_value = (True, "")

    with patch("src.analytics.shadow_tracker.shadow_tracker.register_candidate") as mock_reg, \
         patch("src.core.mt5_connector.get_current_tick", return_value={"ask": 1.48500, "bid": 1.48480, "point": 0.00001, "spread": 20}), \
         patch("main.record_funnel_event"):

        result = run_scanner_trading_cycle(cand, mock_risk)

        # MT5 live execution is blocked (returns False)
        assert result is False

        # shadow_tracker must be registered with SKIPPED_CBSS_BASKET_CAP
        assert mock_reg.called is True
        call_kwargs = mock_reg.call_args[1]
        assert call_kwargs["mt5_disposition"] == "SKIPPED_CBSS_BASKET_CAP"
        assert call_kwargs["candidate"].symbol == "EURCAD-ECN"

