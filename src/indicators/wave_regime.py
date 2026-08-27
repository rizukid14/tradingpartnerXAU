"""
Market Wave Regime & Consolidation Age Classifier.
Combines:
1. Elliott Wave Correction & Triangle Detection (LuxAlgo Pivot Highs/Lows)
2. Range Age Counter (Consolidation Age in Bars & Hours)
3. LazyBear Squeeze Momentum Integration

Classifies Market Regime:
- YOUNG_OSCILLATION (< 24h): High-probability intraday sweeps (Judas Sweep H1 Active).
- MATURE_SQUEEZE (24-72h): Compression building, requires H4 SL anchor.
- SUPER_COMPRESSION_THRUST (> 72h): Wave 4 Triangle -> PROHIBIT Judas Sweep, Wave 5 Breakout.

Changelog:
- FIX: range_age_bars uses MOST RECENT extreme (min distance), not max index.
- FIX: prev_sqz_bars param preserves SUPER_COMPRESSION context after squeeze releases.
"""
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from src.indicators.squeeze_momentum import calculate_squeeze_momentum


def find_pivots(highs: List[float], lows: List[float], length: int = 14) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Finds Pivot Highs and Pivot Lows across the series."""
    n = len(highs)
    pivot_highs: List[Dict[str, Any]] = []
    pivot_lows:  List[Dict[str, Any]] = []

    if n < (length * 2 + 1):
        return pivot_highs, pivot_lows

    for i in range(length, n - length):
        is_ph = all(highs[i] >= highs[i - j] and highs[i] >= highs[i + j] for j in range(1, length + 1))
        if is_ph:
            pivot_highs.append({"index": i, "price": highs[i]})

        is_pl = all(lows[i] <= lows[i - j] and lows[i] <= lows[i + j] for j in range(1, length + 1))
        if is_pl:
            pivot_lows.append({"index": i, "price": lows[i]})

    return pivot_highs, pivot_lows


def evaluate_wave_regime(
    highs: List[float],
    lows:  List[float],
    closes: List[float],
    timeframe_hours:      float = 1.0,
    dealing_range_window: int   = 100,
    prev_sqz_bars:        int   = 0,
) -> Dict[str, Any]:
    """
    Evaluates market consolidation age, wave structure, and squeeze compression state.

    Args:
        prev_sqz_bars: Consecutive squeeze bars that just ended before this call.
                       Caller should pass its manual sqz_count before resetting to 0.
                       Prevents loss of SUPER_COMPRESSION context after squeeze fires.
    """
    n = len(closes)

    # Always compute range_age first — independent of data length
    window  = min(n, dealing_range_window)
    h_win   = highs[-window:]
    l_win   = lows[-window:]
    max_idx = int(np.argmax(h_win))
    min_idx = int(np.argmin(l_win))
    bars_since_high = (window - 1) - max_idx
    bars_since_low  = (window - 1) - min_idx
    range_age_bars  = max(1, min(bars_since_high, bars_since_low))
    range_age_hours = round(range_age_bars * timeframe_hours, 1)

    if n < 30:
        return {
            "regime": "YOUNG_OSCILLATION",
            "range_age_bars": range_age_bars,
            "range_age_hours": range_age_hours,
            "effective_sqz_bars": prev_sqz_bars,
            "is_triangle_compression": False,
            "squeeze_state": {},
            "allow_judas_sweep": True,
            "required_sl_mode": "STANDARD",
            "narrative": f"Data terbatas ({n} bars). range_age={range_age_hours}h."
        }

    # 1. Squeeze Momentum
    sqz_info = calculate_squeeze_momentum(highs, lows, closes)
    sqz_on   = sqz_info.get("sqz_on", False)
    sqz_bars = sqz_info.get("squeeze_bars", 0)
    is_grind = sqz_info.get("is_bearish_grind", False)

    # Effective squeeze = whichever is larger: current active OR just-ended
    effective_sqz_bars = max(sqz_bars, prev_sqz_bars)

    # 2. Dealing Range already computed above (before n < 30 check)

    # 3. Elliott Wave Triangle Detection
    ph_list, pl_list = find_pivots(highs, lows, length=10)
    is_triangle = False
    if len(ph_list) >= 2 and len(pl_list) >= 2:
        ph1, ph2 = ph_list[-2]["price"], ph_list[-1]["price"]
        pl1, pl2 = pl_list[-2]["price"], pl_list[-1]["price"]
        if ph2 < ph1 and pl2 > pl1:   # descending highs + ascending lows = converging triangle
            is_triangle = True

    # 4. Regime Classification
    is_super = (
        range_age_hours > 72.0
        or is_triangle
        or effective_sqz_bars >= 16   # >= 16 consecutive H1 squeeze bars
    )
    is_mature = (
        range_age_hours >= 24.0
        or effective_sqz_bars >= 6
    )

    if is_super:
        regime      = "SUPER_COMPRESSION_THRUST"
        allow_judas = False
        sl_mode     = "BREAKOUT_ONLY"
        tri_note    = ", Triangle" if is_triangle else ""
        narrative   = (
            f"Super-Kompresi Wave 4 jenuh ({range_age_hours}h, sqz {effective_sqz_bars} bars{tri_note}). "
            "Dilarang Judas Sweep! Bersiap Wave 5 Breakout."
        )
    elif is_mature:
        regime      = "MATURE_SQUEEZE"
        allow_judas = True
        sl_mode     = "H4_STRUCTURAL_EXPANSION"
        narrative   = (
            f"Kompresi menengah ({range_age_hours}h, sqz {effective_sqz_bars} bars). "
            "Wajib SL Struktur H4."
        )
    else:
        regime      = "YOUNG_OSCILLATION"
        allow_judas = True
        sl_mode     = "STANDARD"
        narrative   = (
            f"Wave pendek aktif ({range_age_hours}h). "
            "Osilasi sesi normal, Judas Sweep H1 valid."
        )

    if is_grind:
        allow_judas = False
        narrative  += " [BLOCKED: Momentum SQZ Bearish Grind aktif]."

    return {
        "regime":                  regime,
        "range_age_bars":          range_age_bars,
        "range_age_hours":         range_age_hours,
        "effective_sqz_bars":      effective_sqz_bars,
        "is_triangle_compression": is_triangle,
        "squeeze_state":           sqz_info,
        "allow_judas_sweep":       allow_judas,
        "required_sl_mode":        sl_mode,
        "narrative":               narrative,
    }
