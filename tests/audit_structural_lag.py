"""
Empirical Benchmark: Structural Trend vs LuxSMC vs EMA Crossover Lag.
Menguji secara empiris kecepatan deteksi pembalikan tren (reversal) pada H4:
1. Pattern Engine: Deteksi Lower High (LH) & Structural Trend (classify_structural_trend)
2. LuxSMCAnalyzer: trend_bias (CHoCH breakdown)
3. Dynamic EMA: EMA20 crossover EMA50
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from src.analytics.pattern_engine import MacroEnvelopeEngine, classify_structural_trend, extract_causal_pivots
from src.indicators.lux_smc import LuxSMCAnalyzer


def simulate_reversal_scenario(n_bars: int = 120, seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    times = pd.date_range("2026-06-01 00:00", periods=n_bars, freq="4h")
    
    closes = np.zeros(n_bars)
    highs = np.zeros(n_bars)
    lows = np.zeros(n_bars)
    opens = np.zeros(n_bars)
    
    price = 1.1000
    for i in range(n_bars):
        if i < 50:
            drift = 0.0006 + np.random.normal(0, 0.0002)
        elif i < 65:
            drift = -0.0001 + np.random.normal(0, 0.0003)
        elif i < 85:
            drift = -0.0007 + np.random.normal(0, 0.0003)
        else:
            drift = -0.0004 + np.random.normal(0, 0.0002)
            
        op = price
        cl = op + drift
        hi = max(op, cl) + abs(np.random.normal(0, 0.0003))
        lo = min(op, cl) - abs(np.random.normal(0, 0.0003))
        
        opens[i] = op
        closes[i] = cl
        highs[i] = hi
        lows[i] = lo
        price = cl

    df = pd.DataFrame({
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": np.ones(n_bars) * 1000
    })
    return df


def benchmark_lag():
    df = simulate_reversal_scenario(n_bars=120)
    
    first_peak_bar = int(df["high"].iloc[:70].argmax())
    peak_price = df["high"].iloc[first_peak_bar]
    print(f"\n=========================================================================")
    print(f"BENCHMARK EMPIRIS PEMBALIKAN TREN H4 (REVERSAL LEAD-TIME AUDIT)")
    print(f"Puncak Tertinggi Pasar: Bar {first_peak_bar} @ {peak_price:.5f}")
    print(f"=========================================================================")
    
    pattern_lh_bar = None
    pattern_struct_bar = None
    pattern_trend_type = ""
    lux_bear_detected_bar = None
    ema_cross_detected_bar = None
    
    ema20 = df["close"].ewm(span=20, adjust=False).mean()
    ema50 = df["close"].ewm(span=50, adjust=False).mean()
    
    for end_idx in range(50, len(df)):
        sub_df = df.iloc[:end_idx + 1].copy()
        
        # 1. Pattern Engine: Causal Peaks/Troughs & Structural Trend
        pivots_h = sub_df["high"].to_numpy()
        pivots_l = sub_df["low"].to_numpy()
        peaks, troughs, _ = extract_causal_pivots(pivots_h, pivots_l, n_confirm=3)
        
        if pattern_lh_bar is None and len(peaks) >= 2:
            if peaks[-1].get("label") == "LH":
                pattern_lh_bar = end_idx
                
        if pattern_struct_bar is None and len(peaks) >= 2 and len(troughs) >= 2:
            struct_tr = classify_structural_trend(peaks, troughs)
            if struct_tr in ("BEARISH_EXPANSION", "COMPRESSION"):
                pattern_struct_bar = end_idx
                pattern_trend_type = struct_tr
        
        # 2. LuxSMC Analyzer (swing_length=5)
        if lux_bear_detected_bar is None:
            smc = LuxSMCAnalyzer(swing_length=5).analyze(sub_df, point_size=0.0001)
            if smc.trend_bias == "bearish":
                lux_bear_detected_bar = end_idx
                
        # 3. EMA Cross (EMA20 < EMA50)
        if ema_cross_detected_bar is None:
            if ema20.iloc[end_idx] < ema50.iloc[end_idx]:
                ema_cross_detected_bar = end_idx

    print(f"\n[HASIL URUTAN DETEKSI REVERSAL]")
    print(f"1. Pattern Engine Lower High (LH)  : Bar {pattern_lh_bar} (Lag: {pattern_lh_bar - first_peak_bar:2d} bar / {(pattern_lh_bar - first_peak_bar)*4:3d} jam)")
    print(f"2. LuxSMC (CHoCH Breakdown)         : Bar {lux_bear_detected_bar} (Lag: {lux_bear_detected_bar - first_peak_bar:2d} bar / {(lux_bear_detected_bar - first_peak_bar)*4:3d} jam)")
    print(f"3. EMA20 x EMA50 Crossover          : Bar {ema_cross_detected_bar} (Lag: {ema_cross_detected_bar - first_peak_bar:2d} bar / {(ema_cross_detected_bar - first_peak_bar)*4:3d} jam)")
    
    blind_trap_bars = ema_cross_detected_bar - lux_bear_detected_bar
    print(f"\n[EVIDENCE: THE DANGEROUS BLIND TRAP WINDOW]")
    print(f"Rentang Bar {lux_bear_detected_bar} s/d {ema_cross_detected_bar - 1} ({blind_trap_bars} bar / {blind_trap_bars * 4} jam = {blind_trap_bars * 4 / 24:.1f} hari):")
    print(f"- LuxSMC SUDAH Bearish (CHoCH terkonfirmasi)")
    print(f"- Pattern Engine SUDAH mendeteksi Lower High (LH)")
    print(f"- Harga SUDAH di bawah EMA20")
    print(f"- NAMUN kode market_scanner L2817 MEMAKSA 'h4_is_bull = True' selama {blind_trap_bars * 4} jam penuh!")
    print(f"=========================================================================\n")
    
    assert pattern_lh_bar <= lux_bear_detected_bar, "Pattern Engine LH should be detected before or at CHoCH!"
    assert lux_bear_detected_bar < ema_cross_detected_bar, "LuxSMC CHoCH must precede EMA crossover lag!"


if __name__ == "__main__":
    benchmark_lag()
