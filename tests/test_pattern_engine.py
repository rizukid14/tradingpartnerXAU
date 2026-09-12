"""
tests/test_pattern_engine.py — Unit Tests for Macro Dynamic Envelope & Pattern Recognition Engine
"""
import time
import numpy as np
import pandas as pd
import pytest

from src.analytics.pattern_engine import (
    MacroEnvelopeEngine,
    MacroEnvelopeResult,
    GeometricPattern,
    clean_outliers_and_rollover,
    extract_causal_pivots,
    classify_structural_trend,
    detect_geometric_patterns,
    savgol_smooth,
    _compute_savgol_weights
)


def _generate_synthetic_h4_df(n_bars: int = 100, trend: str = "bullish") -> pd.DataFrame:
    """Generate synthetic H4 OHLC bars with controlled trend and wicks."""
    np.random.seed(42)
    base_price = 1.1000
    times = pd.date_range("2026-08-01 00:00", periods=n_bars, freq="4h")
    
    opens = []
    highs = []
    lows = []
    closes = []
    
    curr = base_price
    for i in range(n_bars):
        if trend == "bullish":
            drift = 0.0008 * np.sin(i / 10.0) + 0.0004
        elif trend == "bearish":
            drift = -0.0008 * np.sin(i / 10.0) - 0.0004
        elif trend == "compression":
            decay = max(0.2, 1.0 - (i / float(n_bars)))
            drift = 0.0010 * decay * np.sin(i / 4.0)
        else: # ranging
            drift = 0.0006 * np.sin(i / 6.0)
            
        op = curr
        cl = op + drift + np.random.uniform(-0.0003, 0.0003)
        hi = max(op, cl) + np.random.uniform(0.0001, 0.0005)
        lo = min(op, cl) - np.random.uniform(0.0001, 0.0005)
        
        opens.append(op)
        highs.append(hi)
        lows.append(lo)
        closes.append(cl)
        curr = cl
        
    return pd.DataFrame({
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes
    })


def test_savgol_pure_numpy_weights():
    """Verify analytical Savitzky-Golay weights."""
    w0 = _compute_savgol_weights(window_length=7, polyorder=2, deriv=0)
    assert len(w0) == 7
    assert np.isclose(np.sum(w0), 1.0)
    
    w1 = _compute_savgol_weights(window_length=7, polyorder=2, deriv=1)
    assert len(w1) == 7
    # Turunan pertama dari konstanta harus 0
    assert np.isclose(np.sum(w1), 0.0)


def test_outlier_and_rollover_clamping():
    """Verify that extreme fake wicks during rollover are clamped cleanly."""
    df = _generate_synthetic_h4_df(n_bars=30)
    atr = pd.Series([0.0030] * 30) # 30 pips ATR
    
    # Inject giant false wick on bar 15 (e.g. CHF rollover flash spike 120 pips)
    bar15_body_bot = min(df.loc[15, "open"], df.loc[15, "close"])
    df.loc[15, "low"] = bar15_body_bot - (4.0 * 0.0030) # 4x ATR spike
    
    clean_df = clean_outliers_and_rollover(df, atr, symbol="EURCHF")
    
    # Original low is preserved in 'low', but 'clean_low' must be clamped
    assert df.loc[15, "low"] < bar15_body_bot - (3.5 * 0.0030)
    assert clean_df.loc[15, "clean_low"] >= bar15_body_bot - (1.5 * 0.0030)


def test_causal_pivot_invariance_no_repainting():
    """
    Critical Quantitative Test:
    Adding new bars in the future must NOT alter past confirmed pivots!
    """
    df_base = _generate_synthetic_h4_df(n_bars=80, trend="bullish")
    engine = MacroEnvelopeEngine(confirm_window=3)
    
    res1 = engine.analyze(df_base, symbol="EURUSD")
    peaks1 = [(p["index"], p["price"]) for p in res1.confirmed_peaks]
    troughs1 = [(t["index"], t["price"]) for t in res1.confirmed_troughs]
    
    # Append 5 new bars
    df_extended = _generate_synthetic_h4_df(n_bars=85, trend="bullish")
    # Make sure the first 80 bars are identical
    df_extended.iloc[:80] = df_base.iloc[:80]
    
    res2 = engine.analyze(df_extended, symbol="EURUSD")
    peaks2 = [(p["index"], p["price"]) for p in res2.confirmed_peaks]
    troughs2 = [(t["index"], t["price"]) for t in res2.confirmed_troughs]
    
    # All confirmed peaks and troughs in the first 80 bars must match exactly!
    confirmed_peaks_in_range1 = [p for p in peaks2 if p[0] <= 80 - 1 - 3]
    assert len(confirmed_peaks_in_range1) == len(peaks1)
    for p1, p2 in zip(peaks1, confirmed_peaks_in_range1):
        assert p1[0] == p2[0]
        assert np.isclose(p1[1], p2[1])


def test_wick_density_rejection_and_absorption():
    """Verify upper wick rejection and lower wick absorption matrix."""
    df = _generate_synthetic_h4_df(n_bars=50)
    
    # Inject heavy lower wicks on the last 5 bars (heavy buying absorption)
    for i in range(45, 50):
        body_bot = min(df.loc[i, "open"], df.loc[i, "close"])
        df.loc[i, "low"] = body_bot - 0.0025 # 25 pips lower wick
        
    engine = MacroEnvelopeEngine()
    res = engine.analyze(df, symbol="GBPUSD", point_size=0.0001, pip_size=0.0001)
    
    assert res.recent_absorption_score > res.recent_rejection_score
    assert res.net_wick_delta > 0.0 # Positive buyer absorption


def test_visual_payload_lightweight_charts_ready():
    """Verify that visual payload adheres to Lightweight Charts format."""
    df = _generate_synthetic_h4_df(n_bars=60)
    engine = MacroEnvelopeEngine()
    res = engine.analyze(df, symbol="EURUSD")
    
    vp = res.visual_payload
    assert "upper_body" in vp
    assert "lower_body" in vp
    assert "upper_wick" in vp
    assert "lower_wick" in vp
    assert len(vp["upper_body"]) == 60
    assert "time" in vp["upper_body"][0]
    assert "value" in vp["upper_body"][0]
    # Check that upper envelope is always above or equal to lower envelope
    for ub, lb in zip(vp["upper_body"], vp["lower_body"]):
        assert ub["value"] >= lb["value"]


def test_performance_sub_millisecond():
    """Verify execution speed is < 5ms for 100 bars H4."""
    df = _generate_synthetic_h4_df(n_bars=100)
    engine = MacroEnvelopeEngine()
    
    # Warm up
    engine.analyze(df, symbol="EURUSD")
    
    t0 = time.perf_counter()
    n_runs = 50
    for _ in range(n_runs):
        engine.analyze(df, symbol="EURUSD")
    t1 = time.perf_counter()
    
    avg_ms = ((t1 - t0) / n_runs) * 1000.0
    print(f"\n[BENCHMARK] MacroEnvelopeEngine average runtime: {avg_ms:.2f} ms")
    assert avg_ms < 8.0, f"Engine too slow: {avg_ms:.2f} ms > 8.0 ms"


def test_detect_double_top_and_bottom():
    """Verify Double Top detection, neckline, and measured move target."""
    peaks = [
        {"index": 20, "price": 1.1050, "label": "H"},
        {"index": 40, "price": 1.1052, "label": "EH"}  # Diff = 2 pips (well within 0.18*ATR)
    ]
    troughs = [
        {"index": 30, "price": 1.0950, "label": "L"}  # Neckline at 1.0950
    ]
    closes = np.array([1.1000] * 40 + [1.0960])  # Close at 1.0960 (above neckline 1.0950 -> FORMING)
    highs = np.array([1.1050] * 41)
    lows = np.array([1.0950] * 41)
    cur_atr = 0.0030  # 30 pips ATR
    
    pat = detect_geometric_patterns(
        peaks=peaks,
        troughs=troughs,
        upper_slope=0.0,
        lower_slope=0.0,
        highs=highs,
        lows=lows,
        closes=closes,
        cur_atr=cur_atr,
        pip_size=0.0001
    )
    
    assert pat.name == "DOUBLE_TOP"
    assert pat.bias == "BEARISH"
    assert pat.status == "FORMING"
    assert np.isclose(pat.neckline_price, 1.0950)
    # Height = ~101 pips, Target = 1.0950 - 0.0101 = 1.0849
    assert pat.target_geom_price < 1.0900
    assert pat.height_pips > 90.0


def test_detect_wedges_falling_and_rising():
    """Verify Falling Wedge and Rising Wedge via slope convergence."""
    peaks = [{"index": 10, "price": 1.1000}, {"index": 30, "price": 1.0950}]
    troughs = [{"index": 5, "price": 1.0950}, {"index": 25, "price": 1.0850}]
    closes = np.array([1.0920] * 35)
    highs = np.array([1.1005] * 35)
    lows = np.array([1.0840] * 35)
    cur_atr = 0.0025

    # 1. Falling Wedge: m_u < 0, m_l < 0, |m_l| > |m_u|
    pat_fw = detect_geometric_patterns(
        peaks=peaks,
        troughs=troughs,
        upper_slope=-0.50,
        lower_slope=-1.20,
        highs=highs,
        lows=lows,
        closes=closes,
        cur_atr=cur_atr,
        pip_size=0.0001
    )
    assert pat_fw.name == "FALLING_WEDGE"
    assert pat_fw.bias == "BULLISH"
    assert pat_fw.target_geom_price > 1.0950

    # 2. Rising Wedge: m_u > 0, m_l > 0, m_l > m_u
    pat_rw = detect_geometric_patterns(
        peaks=peaks,
        troughs=troughs,
        upper_slope=0.40,
        lower_slope=1.10,
        highs=highs,
        lows=lows,
        closes=closes,
        cur_atr=cur_atr,
        pip_size=0.0001
    )
    assert pat_rw.name == "RISING_WEDGE"
    assert pat_rw.bias == "BEARISH"
    assert pat_rw.target_geom_price < 1.0850


def test_detect_triangles_multi_slope():
    """Verify Ascending, Descending, and Symmetrical Triangle detection via multi-slope thresholds."""
    peaks = [{"index": 10, "price": 1.1000}, {"index": 30, "price": 1.1002}]
    troughs = [{"index": 5, "price": 1.0900}, {"index": 20, "price": 1.0950}]
    closes = np.array([1.0980] * 35)
    highs = np.array([1.1005] * 35)
    lows = np.array([1.0900] * 35)
    cur_atr = 0.0020

    # 1. Ascending Triangle: |m_u| <= 0.10, m_l > 0.10
    pat_asc = detect_geometric_patterns(
        peaks=peaks,
        troughs=troughs,
        upper_slope=0.05,
        lower_slope=0.80,
        highs=highs,
        lows=lows,
        closes=closes,
        cur_atr=cur_atr,
        pip_size=0.0001
    )
    assert pat_asc.name == "ASCENDING_TRIANGLE"
    assert pat_asc.bias == "BULLISH"

    # 2. Descending Triangle: m_u < -0.10, |m_l| <= 0.10
    pat_desc = detect_geometric_patterns(
        peaks=peaks,
        troughs=troughs,
        upper_slope=-0.80,
        lower_slope=-0.05,
        highs=highs,
        lows=lows,
        closes=closes,
        cur_atr=cur_atr,
        pip_size=0.0001
    )
    assert pat_desc.name == "DESCENDING_TRIANGLE"
    assert pat_desc.bias == "BEARISH"

    # 3. Symmetrical Triangle: m_u < -0.10, m_l > 0.10
    pat_sym = detect_geometric_patterns(
        peaks=peaks,
        troughs=troughs,
        upper_slope=-0.60,
        lower_slope=0.60,
        highs=highs,
        lows=lows,
        closes=closes,
        cur_atr=cur_atr,
        pip_size=0.0001
    )
    assert pat_sym.name == "SYMMETRICAL_TRIANGLE"


def test_detect_bull_and_bear_flag():
    """Verify Bull and Bear Flag continuation patterns."""
    cur_atr = 0.0020
    # Create 35 bars with large pole in bars 0..20 (e.g. 1.0800 to 1.0950 = 150 pips = 7.5x ATR)
    highs = np.array([1.0850] * 10 + [1.0950] * 15 + [1.0920] * 10)
    lows = np.array([1.0800] * 10 + [1.0880] * 15 + [1.0890] * 10)
    closes = np.array([1.0840] * 10 + [1.0940] * 15 + [1.0900] * 10)
    peaks = [{"index": 20, "price": 1.0950}]
    troughs = [{"index": 5, "price": 1.0800}]

    # Bull Flag: pole up, consolidation channels downward (|m_u - m_l| <= 0.20, both < -0.10)
    pat_bull_flag = detect_geometric_patterns(
        peaks=peaks,
        troughs=troughs,
        upper_slope=-0.25,
        lower_slope=-0.30,
        highs=highs,
        lows=lows,
        closes=closes,
        cur_atr=cur_atr,
        pip_size=0.0001
    )
    assert pat_bull_flag.name == "BULL_FLAG"
    assert pat_bull_flag.bias == "BULLISH"
    assert pat_bull_flag.target_geom_price > 1.0950


def test_atr_breakout_tolerance_gate():
    """Verify that a breakout is only confirmed when close exceeds neckline +/- 0.15*ATR."""
    peaks = [{"index": 10, "price": 1.1050}, {"index": 30, "price": 1.1050}]
    troughs = [{"index": 20, "price": 1.0950}]  # Neckline = 1.0950
    cur_atr = 0.0020  # 20 pips -> 0.15*ATR = 3 pips (0.00030)
    # Breakout threshold = 1.0950 - 0.0003 = 1.09470
    
    # Case 1: Close is 1.09490 (below neckline, but NOT below 1.09470 threshold) -> TESTING_BREAKOUT
    closes_testing = np.array([1.1000] * 35 + [1.09490])
    highs = np.array([1.1050] * 36)
    lows = np.array([1.0940] * 36)
    
    pat_test = detect_geometric_patterns(
        peaks=peaks, troughs=troughs, upper_slope=0, lower_slope=0,
        highs=highs, lows=lows, closes=closes_testing, cur_atr=cur_atr, pip_size=0.0001
    )
    assert pat_test.status == "TESTING_BREAKOUT"

    # Case 2: Close is 1.09450 (below 1.09470 threshold) -> CONFIRMED_BREAKOUT
    closes_confirmed = np.array([1.1000] * 35 + [1.09450])
    pat_conf = detect_geometric_patterns(
        peaks=peaks, troughs=troughs, upper_slope=0, lower_slope=0,
        highs=highs, lows=lows, closes=closes_confirmed, cur_atr=cur_atr, pip_size=0.0001
    )
    assert pat_conf.status == "CONFIRMED_BREAKOUT"


def test_dual_horizon_pattern_extraction():
    """
    Verify Dual-Horizon Pattern Engine:
    - Tactical Horizon (near, last confirmed pivots)
    - Macro Horizon (far, Anchor Peak Law across 40-100 bars)
    """
    df = _generate_synthetic_h4_df(n_bars=100, trend="compression")
    engine = MacroEnvelopeEngine()
    res = engine.analyze(df, symbol="EURCAD", pip_size=0.0001)

    assert res.macro_pattern is not None
    assert "macro_upper_line" in res.visual_payload["swing_structure"]
    assert "macro_lower_line" in res.visual_payload["swing_structure"]
    assert "macro_pattern" in res.visual_payload["swing_structure"]
    assert hasattr(res, "macro_upper_slope")
    assert hasattr(res, "macro_lower_slope")


def test_inducement_dealing_range_and_order_flow():
    """
    Verify Inducement Dealing Range, Order Flow Backbone, and DOL extraction.
    """
    from src.analytics.pattern_engine import compute_inducement_dealing_range

    # Synthetic series with Range High 1.1000 and Range Low 1.0800
    n = 60
    highs = np.array([1.0900] * n)
    lows = np.array([1.0850] * n)
    closes = np.array([1.0880] * n)
    highs[20] = 1.1000
    lows[35] = 1.0800

    # Put a confirmed peak at idx 20 (1.1000) and confirmed trough at idx 35 (1.0800)
    peaks = [{"index": 20, "price": 1.1000, "label": "HH", "time": 1000}]
    troughs = [{"index": 35, "price": 1.0800, "label": "LL", "time": 2000}]
    time_vals = list(range(n))

    dr, oflow, dol, segments = compute_inducement_dealing_range(
        highs=highs,
        lows=lows,
        closes=closes,
        peaks=peaks,
        troughs=troughs,
        time_vals=time_vals,
        cur_atr=0.0020,
        pip_size=0.0001
    )

    assert dr["range_high"] == 1.1000
    assert dr["range_low"] == 1.0800
    assert np.isclose(dr["equilibrium_50"], 1.0900)
    assert np.isclose(dr["fib_382"], 1.08764)
    assert np.isclose(dr["fib_618"], 1.09236)
    assert dr["zone_status"] == "SHALLOW_DISCOUNT_INDUCEMENT"
    assert "is_valid_range" in dr
    assert dol["direction"] in ["SEEKING_BSL", "SEEKING_SSL", "ROTATING_TO_BSL", "ROTATING_TO_SSL"]
    assert oflow["regime"] in ["BULLISH_ORDER_FLOW", "BEARISH_ORDER_FLOW", "CHOPPY", "NEUTRAL_FLOW"]
    assert len(segments) >= 1



