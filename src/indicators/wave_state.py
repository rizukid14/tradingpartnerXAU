"""
Wave State Machine & Trade Permission Engine (src/indicators/wave_state.py)
----------------------------------------------------------------------------
Implements causal, zero look-ahead market wave state classification to separate:
1. IMPULSE_CHASE       (Phase 1: Running impulse -> BLOCK CHASE / Negative Expectancy)
2. EARLY_CORRECTION    (Phase 2: Initial 1-2 leg plunge without basing -> LOCK / Anti-Falling Knife)
3. MATURE_CORRECTION   (Phase 3: Pullback reaching Favorable Zone with Basing/Wicks -> ARMED)
4. BASE_RECLAIM        (Phase 4: Deep Discount / Structural Base Established -> ENABLE)

Empirical Principle:
- Direction tells the bot WHERE the market wants to go (D1/H4).
- Wave State tells the bot WHETHER NOW is the time to participate (H1).
- Entry Location is verified in H1 Dealing Range Discount (<= 0.50) / Deep Discount (<= 0.382).
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd


class WaveState:
    IMPULSE_CHASE = "IMPULSE_CHASE"
    EARLY_CORRECTION_LOCK = "EARLY_CORRECTION_LOCK"
    MATURE_CORRECTION_ARMED = "MATURE_CORRECTION_ARMED"
    BASE_RECLAIM_ENABLE = "BASE_RECLAIM_ENABLE"
    NEUTRAL_RANGING = "NEUTRAL_RANGING"


@dataclass
class WaveStateResult:
    state: str
    is_trade_permitted: bool
    direction: int                      # 1 for BUY bias, -1 for SELL bias, 0 for neutral
    pullback_depth_atr: float
    zigzag_legs_count: int
    bars_since_pivot: int
    dealing_range_pos: float           # 0.0 (Deep Discount) to 1.0 (Extreme Premium)
    in_discount: bool                  # Backwards-compatible flag: True if in favorable discount/premium
    in_favorable_zone: bool            # Explicit clean flag: Discount for BUY, Premium for SELL
    summary: str


def compute_atr_np(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(highs)
    if n == 0:
        return np.zeros(0)
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    atr = np.zeros(n)
    if n >= period:
        atr[period-1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period
    return atr


def extract_causal_swings(highs: np.ndarray, lows: np.ndarray, left: int = 2, right: int = 2) -> List[Tuple[int, bool, float, int]]:
    """
    Extracts causal swings with ZERO look-ahead bias.
    A swing peak at index p (with right=2) is ONLY confirmed at index p + right (p+2).
    Returns list of tuples: (confirmed_bar_idx, is_swing_high, price, peak_bar_idx)
    """
    n = len(highs)
    swings = []
    if n < left + right + 1:
        return swings

    for p in range(left, n - right):
        # Swing High
        if highs[p] == np.max(highs[p-left : p+right+1]):
            swings.append((p + right, True, float(highs[p]), p))
        # Swing Low
        if lows[p] == np.min(lows[p-left : p+right+1]):
            swings.append((p + right, False, float(lows[p]), p))

    swings.sort(key=lambda x: x[0])
    return swings


def evaluate_wave_state(
    df_h1: pd.DataFrame,
    h4_trend_direction: int = 0,
    current_price: Optional[float] = None,
    atr_pts: Optional[float] = None,
    point_val: float = 0.0001
) -> WaveStateResult:
    """
    Evaluates real-time H1 wave state strictly causally without future leak.
    
    Args:
        df_h1: H1 closed bars DataFrame (must have 'high', 'low', 'close', 'open')
        h4_trend_direction: 1 (Bullish), -1 (Bearish), 0 (Neutral)
        current_price: live market price (mid/bid/ask). If None, uses last closed bar close.
        atr_pts: current ATR in points. If None, computes ATR(14) from df_h1.
        point_val: broker point value (e.g. 0.001 for JPY, 0.00001 for FX, 0.01 for XAU)
    
    Returns:
        WaveStateResult containing the state, trade permission flag, and metrics.
    """
    if df_h1 is None or len(df_h1) < 50:
        return WaveStateResult(
            state=WaveState.NEUTRAL_RANGING,
            is_trade_permitted=True,
            direction=0,
            pullback_depth_atr=0.0,
            zigzag_legs_count=0,
            bars_since_pivot=0,
            dealing_range_pos=0.5,
            in_discount=True,
            in_favorable_zone=True,
            summary="Insufficient H1 data (<50 bars) -> Default Allowed"
        )

    h1_highs = df_h1['high'].values
    h1_lows = df_h1['low'].values
    h1_closes = df_h1['close'].values
    h1_opens = df_h1['open'].values if 'open' in df_h1.columns else h1_closes
    n = len(h1_closes)
    curr_idx = n - 1

    c_price = float(current_price if current_price is not None else h1_closes[-1])
    
    if atr_pts is not None and atr_pts > 0:
        atr_price = atr_pts * point_val
    else:
        atr_arr = compute_atr_np(h1_highs, h1_lows, h1_closes, 14)
        atr_price = float(atr_arr[-1]) if atr_arr[-1] > 0 else (h1_highs[-1] - h1_lows[-1])

    if atr_price <= 0:
        atr_price = 1e-5

    # 1. 50-bar Dealing Range & Position
    w_start = max(0, n - 50)
    range_high = float(np.max(h1_highs[w_start:n]))
    range_low = float(np.min(h1_lows[w_start:n]))
    dr_span = max(range_high - range_low, 1e-5)
    dr_pos = float(np.clip((c_price - range_low) / dr_span, 0.0, 1.0))

    # 2. Extract Causal Swings
    all_swings = extract_causal_swings(h1_highs, h1_lows, left=2, right=2)
    known_swings = [s for s in all_swings if s[0] <= curr_idx]

    known_sh = [(s[2], s[3]) for s in known_swings if s[1]]  # (price, bar_idx)
    known_sl = [(s[2], s[3]) for s in known_swings if not s[1]]

    # 3. Bar Range & Wick calculation for deceleration detection
    curr_bar_range = max(h1_highs[-1] - h1_lows[-1], 1e-5)
    lower_wick = max(0.0, min(h1_opens[-1], c_price) - h1_lows[-1])
    upper_wick = max(0.0, h1_highs[-1] - max(h1_opens[-1], c_price))
    lower_wick_ratio = lower_wick / curr_bar_range
    upper_wick_ratio = upper_wick / curr_bar_range

    # 4. Default fallback if insufficient swings
    if len(known_sh) < 1 or len(known_sl) < 1:
        in_fav = (dr_pos <= 0.50) if h4_trend_direction == 1 else ((dr_pos >= 0.50) if h4_trend_direction == -1 else True)
        return WaveStateResult(
            state=WaveState.BASE_RECLAIM_ENABLE if in_fav else WaveState.EARLY_CORRECTION_LOCK,
            is_trade_permitted=in_fav,
            direction=h4_trend_direction,
            pullback_depth_atr=0.0,
            zigzag_legs_count=0,
            bars_since_pivot=0,
            dealing_range_pos=dr_pos,
            in_discount=in_fav,
            in_favorable_zone=in_fav,
            summary=f"Sparse swings -> Dealing Range fallback (Pos: {dr_pos*100:.1f}%)"
        )

    # 5. Wave Classification based on Macro Trend Direction
    if h4_trend_direction == 1:
        # BULLISH BIAS
        last_peak_p, last_peak_bar = known_sh[-1]
        bars_since_pivot = curr_idx - last_peak_bar
        pullback_depth_atr = max(0.0, (last_peak_p - c_price) / atr_price)
        
        # Swings occurred strictly after the last peak
        swings_in_pb = [s for s in known_swings if s[3] > last_peak_bar]
        zigzag_legs = len(swings_in_pb)
        
        in_favorable_zone = dr_pos <= 0.50
        is_deep_discount = dr_pos <= 0.382

        # Phase 1: Early Impulse Chase (Within 0.50 ATR from Peak, <= 3 bars)
        if pullback_depth_atr < 0.50 and bars_since_pivot <= 3:
            state = WaveState.IMPULSE_CHASE
            permitted = False
            summary = f"IMPULSE CHASE: Price near peak ({pullback_depth_atr:.2f} ATR, {bars_since_pivot} bars ago) -> BLOCK CHASE"

        # Phase 2: Early Correction / Falling Knife (Outside discount OR vertical waterfall without rejection)
        elif not in_favorable_zone or (pullback_depth_atr >= 0.50 and bars_since_pivot <= 4 and c_price < h1_closes[-2] and lower_wick_ratio < 0.25):
            state = WaveState.EARLY_CORRECTION_LOCK
            permitted = False
            summary = f"EARLY CORRECTION LOCK: Pullback underway ({pullback_depth_atr:.2f} ATR, DR: {dr_pos*100:.1f}%) -> LOCK (Anti-Falling Knife)"

        # Phase 4: Base Reclaim / Deep Discount Exhaustion (In Deep Discount <= 38.2% or Strong Structural Bounce)
        elif in_favorable_zone and (is_deep_discount or (zigzag_legs >= 2 and lower_wick_ratio >= 0.35)):
            state = WaveState.BASE_RECLAIM_ENABLE
            permitted = True
            summary = f"BASE RECLAIM ENABLE: Deep Floor / Support Reclaimed (DR: {dr_pos*100:.1f}%) -> ENABLE"

        # Phase 3: Mature Basing (In Standard Discount 38.2% - 50.0% with Basing/Wicks)
        elif in_favorable_zone and (zigzag_legs >= 1 or lower_wick_ratio >= 0.25 or pullback_depth_atr >= 0.50):
            state = WaveState.MATURE_CORRECTION_ARMED
            permitted = True
            summary = f"MATURE CORRECTION ARMED: {zigzag_legs} legs formed, Basing in DR {dr_pos*100:.1f}% -> ARMED"

        else:
            state = WaveState.MATURE_CORRECTION_ARMED if in_favorable_zone else WaveState.EARLY_CORRECTION_LOCK
            permitted = in_favorable_zone
            summary = f"EQUILIBRIUM: DR Pos {dr_pos*100:.1f}% -> {'ARMED' if in_favorable_zone else 'LOCK'}"

        return WaveStateResult(
            state=state,
            is_trade_permitted=permitted,
            direction=1,
            pullback_depth_atr=pullback_depth_atr,
            zigzag_legs_count=zigzag_legs,
            bars_since_pivot=bars_since_pivot,
            dealing_range_pos=dr_pos,
            in_discount=in_favorable_zone,
            in_favorable_zone=in_favorable_zone,
            summary=summary
        )

    elif h4_trend_direction == -1:
        # BEARISH BIAS
        last_trough_p, last_trough_bar = known_sl[-1]
        bars_since_pivot = curr_idx - last_trough_bar
        pullback_depth_atr = max(0.0, (c_price - last_trough_p) / atr_price)
        
        swings_in_pb = [s for s in known_swings if s[3] > last_trough_bar]
        zigzag_legs = len(swings_in_pb)
        
        in_favorable_zone = dr_pos >= 0.50 # For SELL, Premium (>=0.50) is the favorable selling zone
        is_deep_premium = dr_pos >= 0.618

        # Phase 1: Early Impulse Chase (Within 0.50 ATR from Trough, <= 3 bars)
        if pullback_depth_atr < 0.50 and bars_since_pivot <= 3:
            state = WaveState.IMPULSE_CHASE
            permitted = False
            summary = f"IMPULSE CHASE: Price near trough ({pullback_depth_atr:.2f} ATR, {bars_since_pivot} bars ago) -> BLOCK CHASE"

        # Phase 2: Early Correction / Rising Knife (Outside premium OR vertical surge without upper rejection)
        elif not in_favorable_zone or (pullback_depth_atr >= 0.50 and bars_since_pivot <= 4 and c_price > h1_closes[-2] and upper_wick_ratio < 0.25):
            state = WaveState.EARLY_CORRECTION_LOCK
            permitted = False
            summary = f"EARLY CORRECTION LOCK: Pullback underway ({pullback_depth_atr:.2f} ATR, DR: {dr_pos*100:.1f}%) -> LOCK"

        # Phase 4: Base Reclaim / Deep Premium Exhaustion (In Deep Premium >= 61.8% or Strong Structural Bounce)
        elif in_favorable_zone and (is_deep_premium or (zigzag_legs >= 2 and upper_wick_ratio >= 0.35)):
            state = WaveState.BASE_RECLAIM_ENABLE
            permitted = True
            summary = f"BASE RECLAIM ENABLE: Deep Ceiling / Resistance Reclaimed (DR: {dr_pos*100:.1f}%) -> ENABLE"

        # Phase 3: Mature Basing (In Standard Premium 50.0% - 61.8% with Basing/Wicks)
        elif in_favorable_zone and (zigzag_legs >= 1 or upper_wick_ratio >= 0.25 or pullback_depth_atr >= 0.50):
            state = WaveState.MATURE_CORRECTION_ARMED
            permitted = True
            summary = f"MATURE CORRECTION ARMED: {zigzag_legs} legs formed, Basing in Premium {dr_pos*100:.1f}% -> ARMED"

        else:
            state = WaveState.MATURE_CORRECTION_ARMED if in_favorable_zone else WaveState.EARLY_CORRECTION_LOCK
            permitted = in_favorable_zone
            summary = f"EQUILIBRIUM: DR Pos {dr_pos*100:.1f}% -> {'ARMED' if in_favorable_zone else 'LOCK'}"

        return WaveStateResult(
            state=state,
            is_trade_permitted=permitted,
            direction=-1,
            pullback_depth_atr=pullback_depth_atr,
            zigzag_legs_count=zigzag_legs,
            bars_since_pivot=bars_since_pivot,
            dealing_range_pos=dr_pos,
            in_discount=in_favorable_zone,
            in_favorable_zone=in_favorable_zone,
            summary=summary
        )

    else:
        # NEUTRAL RANGING
        return WaveStateResult(
            state=WaveState.NEUTRAL_RANGING,
            is_trade_permitted=True,
            direction=0,
            pullback_depth_atr=0.0,
            zigzag_legs_count=0,
            bars_since_pivot=0,
            dealing_range_pos=dr_pos,
            in_discount=True,
            in_favorable_zone=True,
            summary=f"NEUTRAL RANGING: DR Pos {dr_pos*100:.1f}% -> Open for Mean Reversion"
        )
