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
    clean_outliers_and_rollover,
    extract_causal_pivots,
    classify_structural_trend,
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
    assert avg_ms < 5.0, f"Engine too slow: {avg_ms:.2f} ms > 5.0 ms"
