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


def calculate_squeeze_momentum(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    bb_length: int = 20,
    bb_mult: float = 2.0,
    kc_length: int = 20,
    kc_mult: float = 1.5,
    use_true_range: bool = True
) -> Dict[str, Any]:
    """
    Computes LazyBear Squeeze Momentum on historical bar series.
    Returns dictionary with latest values, history arrays, and squeeze duration.
    """
    n = len(closes)
    if n < max(bb_length, kc_length) + 5:
        return {
            "sqz_on": False,
            "sqz_off": False,
            "no_sqz": True,
            "squeeze_bars": 0,
            "momentum_val": 0.0,
            "momentum_color": "BLUE",
            "is_bearish_grind": False,
            "is_bullish_thrust": False,
            "is_exhaustion_turn": False
        }

    h_arr = np.array(highs, dtype=np.float64)
    l_arr = np.array(lows, dtype=np.float64)
    c_arr = np.array(closes, dtype=np.float64)

    # 1. Bollinger Bands
    sma_c = np.convolve(c_arr, np.ones(bb_length) / bb_length, mode='valid')
    stdev_c = np.array([np.std(c_arr[i - bb_length + 1: i + 1], ddof=0) for i in range(bb_length - 1, n)])
    
    upper_bb = sma_c + (bb_mult * stdev_c)
    lower_bb = sma_c - (bb_mult * stdev_c)

    # 2. Keltner Channels
    if use_true_range:
        tr_list = [h_arr[0] - l_arr[0]]
        for i in range(1, n):
            tr_list.append(max(h_arr[i] - l_arr[i], abs(h_arr[i] - c_arr[i-1]), abs(l_arr[i] - c_arr[i-1])))
        tr_arr = np.array(tr_list, dtype=np.float64)
    else:
        tr_arr = h_arr - l_arr

    sma_tr = np.convolve(tr_arr, np.ones(kc_length) / kc_length, mode='valid')
    sma_kc_c = np.convolve(c_arr, np.ones(kc_length) / kc_length, mode='valid')

    upper_kc = sma_kc_c + (sma_tr * kc_mult)
    lower_kc = sma_kc_c - (sma_tr * kc_mult)

    min_len = min(len(upper_bb), len(upper_kc))
    u_bb = upper_bb[-min_len:]
    l_bb = lower_bb[-min_len:]
    u_kc = upper_kc[-min_len:]
    l_kc = lower_kc[-min_len:]

    sqz_on_arr = (l_bb > l_kc) & (u_bb < u_kc)
    sqz_off_arr = (l_bb < l_kc) & (u_bb > u_kc)

    donchian_mid = []
    for i in range(kc_length - 1, n):
        h_max = np.max(h_arr[i - kc_length + 1: i + 1])
        l_min = np.min(l_arr[i - kc_length + 1: i + 1])
        donchian_mid.append((h_max + l_min) / 2.0)
    donchian_mid = np.array(donchian_mid)

    sma_c_kc = sma_kc_c[-len(donchian_mid):]
    avg_mid = (donchian_mid + sma_c_kc) / 2.0
    c_tail = c_arr[-len(avg_mid):]
    diff_series = c_tail - avg_mid

    def _calc_linreg(series: np.ndarray, length: int) -> np.ndarray:
        if len(series) < length:
            return np.zeros_like(series)
        x = np.arange(length, dtype=np.float64)
        x_mean = np.mean(x)
        x_dev = x - x_mean
        denom = np.sum(x_dev ** 2)
        res = []
        for i in range(length - 1, len(series)):
            y = series[i - length + 1: i + 1]
            y_mean = np.mean(y)
            slope = np.sum(x_dev * (y - y_mean)) / denom
            intercept = y_mean - slope * x_mean
            val_endpoint = intercept + slope * (length - 1)
            res.append(val_endpoint)
        return np.array(res, dtype=np.float64)

    val_arr = _calc_linreg(diff_series, kc_length)
    if len(val_arr) < 2:
        return {
            "sqz_on": bool(sqz_on_arr[-1]) if len(sqz_on_arr) else False,
            "sqz_off": bool(sqz_off_arr[-1]) if len(sqz_off_arr) else False,
            "no_sqz": not bool(sqz_on_arr[-1]) if len(sqz_on_arr) else True,
            "squeeze_bars": int(np.sum(sqz_on_arr)) if len(sqz_on_arr) else 0,
            "momentum_val": 0.0,
            "momentum_color": "BLUE",
            "is_bearish_grind": False,
            "is_bullish_thrust": False,
            "is_exhaustion_turn": False
        }

    val_curr = float(val_arr[-1])
    val_prev = float(val_arr[-2])

    if val_curr > 0:
        mom_color = "LIME" if val_curr > val_prev else "GREEN"
    else:
        mom_color = "RED" if val_curr < val_prev else "MAROON"

    sqz_bars = 0
    for s in reversed(sqz_on_arr):
        if s:
            sqz_bars += 1
        else:
            break

    is_bearish_grind = (mom_color == "RED") and (sqz_bars >= 3 or not sqz_on_arr[-1])
    is_bullish_thrust = (mom_color == "LIME") and (val_curr > val_prev * 1.2)
    is_exhaustion_turn = (mom_color == "MAROON") and (val_prev < 0)

    return {
        "sqz_on": bool(sqz_on_arr[-1]),
        "sqz_off": bool(sqz_off_arr[-1]),
        "no_sqz": not (sqz_on_arr[-1] or sqz_off_arr[-1]),
        "squeeze_bars": int(sqz_bars),
        "momentum_val": float(val_curr),
        "momentum_color": str(mom_color),
        "is_bearish_grind": bool(is_bearish_grind),
        "is_bullish_thrust": bool(is_bullish_thrust),
        "is_exhaustion_turn": bool(is_exhaustion_turn)
    }


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
