"""
Squeeze Momentum Indicator [LazyBear] - Python Port.
Based on TradingView Pine Script by LazyBear (SQZMOM_LB).

Calculates:
1. Bollinger Bands (20, mult=2.0)
2. Keltner Channels (20, multKC=1.5, TrueRange)
3. Squeeze State:
   - sqzOn: (lowerBB > lowerKC) and (upperBB < upperKC) -> Compression ON (Black dot)
   - sqzOff: (lowerBB < lowerKC) and (upperBB > upperKC) -> Expansion / Squeeze Fired (Gray dot)
   - noSqz: neither -> Normal volatility (Blue dot)
4. Linear Regression Momentum Histogram:
   - val = linreg(close - avg(avg(highest(20), lowest(20)), sma(close, 20)), 20, 0)
   - Colors:
     - LIME: val > 0 and val > val[1] (Bullish Acceleration)
     - GREEN: val > 0 and val <= val[1] (Bullish Deceleration)
     - RED: val < 0 and val < val[1] (Bearish Acceleration / Slow Bleed)
     - MAROON: val < 0 and val >= val[1] (Bearish Deceleration / Exhaustion Reversal)
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
    # SMA(20)
    sma_c = np.convolve(c_arr, np.ones(bb_length) / bb_length, mode='valid')
    # Rolling STDEV
    stdev_c = np.array([np.std(c_arr[i - bb_length + 1: i + 1], ddof=0) for i in range(bb_length - 1, n)])
    
    upper_bb = sma_c + (bb_mult * stdev_c)
    lower_bb = sma_c - (bb_mult * stdev_c)

    # 2. Keltner Channels
    # True Range
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

    # Align arrays to the valid length
    min_len = min(len(upper_bb), len(upper_kc))
    u_bb = upper_bb[-min_len:]
    l_bb = lower_bb[-min_len:]
    u_kc = upper_kc[-min_len:]
    l_kc = lower_kc[-min_len:]

    # Squeeze States
    sqz_on_arr = (l_bb > l_kc) & (u_bb < u_kc)
    sqz_off_arr = (l_bb < l_kc) & (u_bb > u_kc)

    # 3. Momentum: linreg(close - avg(avg(highest, lowest), sma), kc_length, 0)
    # Donchian mid
    donchian_mid = []
    for i in range(kc_length - 1, n):
        h_max = np.max(h_arr[i - kc_length + 1: i + 1])
        l_min = np.min(l_arr[i - kc_length + 1: i + 1])
        donchian_mid.append((h_max + l_min) / 2.0)
    donchian_mid = np.array(donchian_mid)

    sma_kc_aligned = sma_kc_c[-len(donchian_mid):]
    avg_mid = (donchian_mid + sma_kc_aligned) / 2.0
    c_sub = c_arr[-len(avg_mid):] - avg_mid

    # Rolling Linear Regression (endpoint value at offset 0)
    x = np.arange(kc_length, dtype=np.float64)
    x_mean = np.mean(x)
    x_var = np.var(x) * kc_length
    
    val_list = []
    for i in range(kc_length - 1, len(c_sub)):
        y_slice = c_sub[i - kc_length + 1: i + 1]
        y_mean = np.mean(y_slice)
        slope = np.sum((x - x_mean) * (y_slice - y_mean)) / x_var
        intercept = y_mean - slope * x_mean
        linreg_val = intercept + slope * (kc_length - 1)
        val_list.append(linreg_val)
    val_arr = np.array(val_list)

    # Current States
    cur_sqz_on = bool(sqz_on_arr[-1])
    cur_sqz_off = bool(sqz_off_arr[-1])
    cur_no_sqz = not (cur_sqz_on or cur_sqz_off)

    # Calculate consecutive squeeze bars
    squeeze_bars = 0
    for s in reversed(sqz_on_arr):
        if s:
            squeeze_bars += 1
        else:
            break

    # Momentum value & color
    cur_val = float(val_arr[-1]) if len(val_arr) > 0 else 0.0
    prev_val = float(val_arr[-2]) if len(val_arr) > 1 else cur_val

    if cur_val > 0:
        color = "LIME" if cur_val > prev_val else "GREEN"
    else:
        color = "RED" if cur_val < prev_val else "MAROON"

    # Behavior flags
    is_bearish_grind = (color == "RED") and (cur_val < 0)
    is_bullish_thrust = (color == "LIME") and (cur_val > 0)
    is_exhaustion_turn = (color == "MAROON") and (prev_val < cur_val < 0)

    return {
        "sqz_on": cur_sqz_on,
        "sqz_off": cur_sqz_off,
        "no_sqz": cur_no_sqz,
        "squeeze_bars": squeeze_bars,
        "momentum_val": round(cur_val, 6),
        "prev_momentum_val": round(prev_val, 6),
        "momentum_color": color,
        "is_bearish_grind": is_bearish_grind,
        "is_bullish_thrust": is_bullish_thrust,
        "is_exhaustion_turn": is_exhaustion_turn,
        "momentum_history": val_arr[-10:].tolist() if len(val_arr) >= 10 else []
    }
