"""
Quant V3 Market State & 4-Dimensional Permission Engine (src/indicators/wave_state.py)
-------------------------------------------------------------------------------------
Implements causal, zero look-ahead 4-dimensional market state classification:
1. DIMENSION 1 (Direction Identity): D1/H4 Anchor-Based Trend (Strong Low/High BOS Hysteresis).
2. DIMENSION 2 (Correction Anatomy): Type A (Waterfall / Falling Knife -> LOCK) vs Type B (Compression Coil -> ARM).
3. DIMENSION 3 (Pressure Gauge): Boitoki CSM Delta flow alignment.
4. DIMENSION 4 (Event Layer): Displacement Candle & Micro BOS Reclaim.

Permission Matrix Outputs:
- WAIT : Price near peak / Expansion (No FOMO Chase)
- LOCK : Type A Violent Waterfall (Anti-Falling Knife Protection)
- ARM  : Type B Compression Coil in Area of Value (Watching for Reclaim)
- GO   : Type B Coil + CSM Aligned + Displacement/BOS Reclaim (100% Risk Execution)
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Any, Optional
import numpy as np
import pandas as pd


class WaveState:
    # V3 Canonical State Aliases
    EXPANSION_WAIT = "EXPANSION_WAIT"
    TYPE_A_WATERFALL_LOCK = "TYPE_A_WATERFALL_LOCK"
    TYPE_B_COMPRESSION_ARMED = "TYPE_B_COMPRESSION_ARMED"
    RECLAIM_CONFIRMED_GO = "RECLAIM_CONFIRMED_GO"
    NEUTRAL_RANGING = "NEUTRAL_RANGING"
    
    # Backwards-compatibility aliases
    IMPULSE_CHASE = "EXPANSION_WAIT"
    EARLY_CORRECTION_LOCK = "TYPE_A_WATERFALL_LOCK"
    MATURE_CORRECTION_ARMED = "TYPE_B_COMPRESSION_ARMED"
    BASE_RECLAIM_ENABLE = "RECLAIM_CONFIRMED_GO"


@dataclass
class WaveStateResult:
    state: str
    permission: str                     # "WAIT", "LOCK", "ARM", "GO"
    is_trade_permitted: bool            # True if GO (or ARM for pending limit watch)
    direction: int                      # 1 for BUY bias, -1 for SELL bias, 0 for neutral
    correction_type: str                # "TYPE_A_WATERFALL", "TYPE_B_COIL", "EXPANSION", "NEUTRAL"
    pullback_depth_atr: float
    correction_velocity: float          # ATR retraced per bar
    overlap_ratio: float                # Mean overlap between adjacent bars in ATR
    body_efficiency: float              # Counter-trend body dominance ratio
    bars_since_pivot: int
    dealing_range_pos: float            # 0.0 (Deep Discount) to 1.0 (Extreme Premium)
    in_discount: bool                   # Backwards-compatible flag: True if in favorable discount/premium
    in_favorable_zone: bool             # Explicit clean flag: Discount for BUY, Premium for SELL
    is_reclaim_confirmed: bool          # True if Displacement or Micro BOS occurred
    macro_corridor: str = "NEUTRAL"     # "BULLISH_CORRIDOR", "BEARISH_CORRIDOR", "NEUTRAL"
    target_station: float = 0.0         # Target price for active station corridor
    psych_step: float = 0.0100          # Calibrated natural psychological step
    is_ceiling_rejected: bool = False   # True if rejected from psychological ceiling/PWH
    is_floor_rejected: bool = False     # True if rejected from psychological floor/PWL
    summary: str = ""


def get_symbol_psych_step(symbol: str, cur_atr: float = 0.0) -> float:
    """
    Menghitung langkah psikologis alami khusus per-simbol (ADR/Vol-Calibrated Grid dari Atlas DNA).
    """
    try:
        from src.indicators.atlas_dna import get_symbol_step
        return get_symbol_step(symbol)
    except Exception:
        sym = (symbol or "").upper()
        if 'XAU' in sym: return 50.0
        elif 'JPY' in sym: return 2.000 if 'GBP' in sym or 'CHF' in sym else 1.000
        elif 'AUD' in sym or 'NZD' in sym or 'CHF' in sym or 'CAD' in sym: return 0.0025
        else: return 0.0100


def evaluate_macro_compass_corridor(
    symbol: str,
    current_price: float,
    pwh: float = 0.0,
    pwl: float = 0.0,
    macro_high: float = 0.0,
    macro_low: float = 0.0,
    cur_atr: float = 0.0050,
    last_high: float = 0.0,
    last_low: float = 0.0,
    last_open: float = 0.0,
    last_close: float = 0.0
) -> Tuple[str, float, float, bool, bool]:
    """
    M3 Macro Compass Navigator:
    Mengevaluasi status koridor harga makro secara dinamis berdasarkan Dual-Reaction:
    1. Reversal Rejection: Jika level dirispek (Rejection Wick >= 25%) -> Balik arah ke 50% Eq / Stasiun Lawan.
    2. Breakout Expansion: Jika level dijebol (Clean Close >= 55% body) -> Lanjut ke stasiun berikutnya.
    
    Returns:
        (corridor_state, target_station, psych_step, is_ceiling_rejected, is_floor_rejected)
    """
    psych_step = get_symbol_psych_step(symbol, cur_atr)
    zone_tol = 0.35 * max(cur_atr, 1e-5)
    
    w_mid = (pwl + 0.50 * (pwh - pwl)) if (pwh > pwl and pwl > 0) else current_price
    
    bar_rng = max(last_high - last_low, 1e-5)
    body = abs(last_close - last_open)
    u_wick = max(0.0, last_high - max(last_open, last_close))
    l_wick = max(0.0, min(last_open, last_close) - last_low)
    
    # 1. Psychological Levels Dinamis
    base_pl = round(current_price / psych_step) * psych_step
    psych_levels = [base_pl - psych_step, base_pl, base_pl + psych_step]
    near_psych_top = any(abs(last_high - pl) <= zone_tol for pl in psych_levels)
    near_psych_bot = any(abs(last_low - pl) <= zone_tol for pl in psych_levels)
    
    # 2. EQH / EQL (Weekly PWH/PWL)
    near_eqh = (pwh > 0) and (last_high >= pwh - zone_tol) and (last_close <= pwh + zone_tol)
    near_eql = (pwl > 0) and (last_low <= pwl + zone_tol) and (last_close >= pwl - zone_tol)
    
    # 3. Fibonacci 61.8% of preceding major wave
    macro_span = max(macro_high - macro_low, 1e-5)
    fib_618_bear_retrace = macro_low + 0.618 * macro_span
    fib_618_bull_retrace = macro_high - 0.618 * macro_span
    near_fib_618_top = (macro_high > macro_low) and (abs(last_high - fib_618_bear_retrace) <= zone_tol)
    near_fib_618_bot = (macro_high > macro_low) and (abs(last_low - fib_618_bull_retrace) <= zone_tol)
    
    # Reversal Signals (Level Dirispek)
    is_ceil_rej = bool((near_psych_top or near_eqh or near_fib_618_top) and (u_wick / bar_rng >= 0.25))
    is_flr_rej = bool((near_psych_bot or near_eql or near_fib_618_bot) and (l_wick / bar_rng >= 0.25))
    
    # Breakout Signals (Level Dijebol)
    is_bull_breakout = bool((last_close > last_open) and (body / bar_rng >= 0.55) and (u_wick / bar_rng < 0.20) and (last_close > max(pwh, base_pl) + zone_tol))
    is_bear_breakdown = bool((last_close < last_open) and (body / bar_rng >= 0.55) and (l_wick / bar_rng < 0.20) and (last_close < min(pwl, base_pl) - zone_tol))
    
    if is_ceil_rej:
        return "BEARISH_CORRIDOR", w_mid, psych_step, True, False
    elif is_flr_rej:
        return "BULLISH_CORRIDOR", w_mid, psych_step, False, True
    elif is_bull_breakout:
        return "BULLISH_EXPANSION", (base_pl + psych_step), psych_step, False, False
    elif is_bear_breakdown:
        return "BEARISH_EXPANSION", (base_pl - psych_step), psych_step, False, False
    else:
        return "NEUTRAL", w_mid, psych_step, False, False


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
        if highs[p] == np.max(highs[p-left : p+right+1]):
            swings.append((p + right, True, float(highs[p]), p))
        if lows[p] == np.min(lows[p-left : p+right+1]):
            swings.append((p + right, False, float(lows[p]), p))

    swings.sort(key=lambda x: x[0])
    return swings


def evaluate_wave_state(
    df_h1: pd.DataFrame,
    h4_trend_direction: int = 0,
    current_price: Optional[float] = None,
    atr_pts: Optional[float] = None,
    point_val: float = 0.0001,
    csm_delta: float = 0.0,
    symbol: str = "",
    pwh: float = 0.0,
    pwl: float = 0.0,
    macro_high: float = 0.0,
    macro_low: float = 0.0
) -> WaveStateResult:
    """
    Evaluates real-time H1 market state strictly causally using the 4-Dimensional Quant V3 Engine
    AND integrates M3 Macro Compass Station-to-Station Corridor tracking.
    
    Args:
        df_h1: H1 closed bars DataFrame (must have 'high', 'low', 'close', 'open')
        h4_trend_direction: 1 (Bullish), -1 (Bearish), 0 (Neutral)
        current_price: live market price. If None, uses last closed bar close.
        atr_pts: current ATR in points. If None, computes ATR(14) from df_h1.
        point_val: broker point value (e.g. 0.001 for JPY, 0.00001 for FX, 0.01 for XAU)
        csm_delta: Boitoki CSM Net Delta (e.g. +1.5 for bullish base, -1.5 for bearish base)
        symbol: instrument symbol (e.g. 'EURUSD-ECNc', 'USDJPY-ECNc', 'XAUUSD-ECNc')
        pwh: Previous Week High
        pwl: Previous Week Low
        macro_high: D1/H4 rolling swing high anchor
        macro_low: D1/H4 rolling swing low anchor
    
    Returns:
        WaveStateResult containing 4D metrics, permission, macro corridor, and actionable trade flag.
    """
    if df_h1 is None or len(df_h1) < 30:
        return WaveStateResult(
            state=WaveState.NEUTRAL_RANGING,
            permission="WAIT",
            is_trade_permitted=True,
            direction=0,
            correction_type="NEUTRAL",
            pullback_depth_atr=0.0,
            correction_velocity=0.0,
            overlap_ratio=0.0,
            body_efficiency=0.0,
            bars_since_pivot=0,
            dealing_range_pos=0.5,
            in_discount=True,
            in_favorable_zone=True,
            is_reclaim_confirmed=False,
            macro_corridor="NEUTRAL",
            target_station=0.0,
            psych_step=get_symbol_psych_step(symbol, 0.0050),
            is_ceiling_rejected=False,
            is_floor_rejected=False,
            summary="Insufficient H1 data (<30 bars) -> Default WAIT"
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

    # 0. Evaluate M3 Macro Compass Corridor
    m_corr, m_target, m_step, is_ceil_rej, is_flr_rej = evaluate_macro_compass_corridor(
        symbol=symbol,
        current_price=c_price,
        pwh=pwh,
        pwl=pwl,
        macro_high=macro_high,
        macro_low=macro_low,
        cur_atr=atr_price,
        last_high=h1_highs[-1],
        last_low=h1_lows[-1],
        last_open=h1_opens[-1],
        last_close=h1_closes[-1]
    )

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

    # 3. Bar Range & Reclaim Event Detection on Live/Last Closed Bar
    curr_bar_range = max(h1_highs[-1] - h1_lows[-1], 1e-5)
    curr_bar_body = abs(h1_closes[-1] - h1_opens[-1])
    is_bull_bar = h1_closes[-1] > h1_opens[-1]
    is_bear_bar = h1_closes[-1] < h1_opens[-1]
    
    # Event C: Displacement Candle (Body >= 60% of range and Range >= 1.0x ATR)
    is_bull_displacement = is_bull_bar and (curr_bar_body / curr_bar_range >= 0.60) and (curr_bar_range >= 0.95 * atr_price)
    is_bear_displacement = is_bear_bar and (curr_bar_body / curr_bar_range >= 0.60) and (curr_bar_range >= 0.95 * atr_price)
    
    # Event D: Micro BOS Reclaim (Close > High of previous 2 bars for BULL; Close < Low of previous 2 bars for BEAR)
    prev_2_high = float(np.max(h1_highs[-3:-1])) if n >= 3 else h1_highs[-1]
    prev_2_low = float(np.min(h1_lows[-3:-1])) if n >= 3 else h1_lows[-1]
    is_bull_micro_bos = h1_closes[-1] > prev_2_high
    is_bear_micro_bos = h1_closes[-1] < prev_2_low

    # 4. Fallback if insufficient swings
    if len(known_sh) < 1 or len(known_sl) < 1:
        in_fav = (dr_pos <= 0.50) if h4_trend_direction == 1 else ((dr_pos >= 0.50) if h4_trend_direction == -1 else True)
        is_csm_opposed = (h4_trend_direction == 1 and csm_delta <= -1.0) or (h4_trend_direction == -1 and csm_delta >= 1.0)
        
        if is_csm_opposed:
            perm_fb = "WAIT"
        else:
            perm_fb = "ARM" if in_fav else "LOCK"
            
        return WaveStateResult(
            state=WaveState.TYPE_B_COMPRESSION_ARMED if in_fav else WaveState.TYPE_A_WATERFALL_LOCK,
            permission=perm_fb,
            is_trade_permitted=(perm_fb in ("ARM", "GO")),
            direction=h4_trend_direction,
            correction_type="TYPE_B_COIL" if in_fav else "TYPE_A_WATERFALL",
            pullback_depth_atr=0.0,
            correction_velocity=0.0,
            overlap_ratio=0.0,
            body_efficiency=0.0,
            bars_since_pivot=0,
            dealing_range_pos=dr_pos,
            in_discount=in_fav,
            in_favorable_zone=in_fav,
            is_reclaim_confirmed=False,
            macro_corridor=m_corr,
            target_station=m_target,
            psych_step=m_step,
            is_ceiling_rejected=is_ceil_rej,
            is_floor_rejected=is_flr_rej,
            summary=f"Sparse swings -> Dealing Range fallback (Pos: {dr_pos*100:.1f}%)"
        )

    # =========================================================================
    # 5. 4-DIMENSIONAL EVALUATION (DIRECTION = BULL)
    # =========================================================================
    if h4_trend_direction == 1:
        last_peak_p, last_peak_bar = known_sh[-1]
        bars_since_pivot = max(1, curr_idx - last_peak_bar)
        retrace_dist = max(0.0, last_peak_p - c_price)
        pullback_depth_atr = retrace_dist / atr_price
        
        # Dimension 2: Continuous Correction Anatomy
        corr_w = max(1, min(bars_since_pivot, 15))
        w_slice_h = h1_highs[n - corr_w : n]
        w_slice_l = h1_lows[n - corr_w : n]
        w_slice_o = h1_opens[n - corr_w : n]
        w_slice_c = h1_closes[n - corr_w : n]
        
        # Velocity (ATR retraced per bar)
        velocity = pullback_depth_atr / max(bars_since_pivot, 1)
        
        # Overlap of adjacent bars
        adj_overlaps = [max(0.0, min(w_slice_h[k], w_slice_h[k+1]) - max(w_slice_l[k], w_slice_l[k+1])) for k in range(len(w_slice_h)-1)]
        overlap_ratio = float(np.mean(adj_overlaps) / atr_price) if adj_overlaps else 0.0
        
        # Counter-trend (bearish) body efficiency
        bear_bodies = np.maximum(0.0, w_slice_o - w_slice_c)
        total_ranges = np.maximum(1e-5, w_slice_h - w_slice_l)
        body_efficiency = float(np.sum(bear_bodies) / np.sum(total_ranges))
        
        in_favorable_zone = dr_pos <= 0.50
        is_reclaim = is_bull_displacement or is_bull_micro_bos
        
        # Classification of Correction Character
        is_waterfall = (velocity >= 0.30) and (overlap_ratio < 0.35) and (body_efficiency >= 0.45) and (bars_since_pivot <= 5)
        is_compression = not is_waterfall and (bars_since_pivot >= 3)
        
        # Permission Matrix Resolution
        if pullback_depth_atr < 0.40 and bars_since_pivot <= 2:
            state = WaveState.EXPANSION_WAIT
            permission = "WAIT"
            corr_type = "EXPANSION"
            summary = f"EXPANSION WAIT: Price near peak ({pullback_depth_atr:.2f} ATR) -> WAIT (No FOMO)"
            
        elif is_waterfall or (not in_favorable_zone and velocity >= 0.35):
            state = WaveState.TYPE_A_WATERFALL_LOCK
            permission = "LOCK"
            corr_type = "TYPE_A_WATERFALL"
            summary = f"TYPE A WATERFALL LOCK: Violent Plunge ({velocity:.2f} ATR/b, BodyEff {body_efficiency*100:.0f}%) -> LOCK"
            
        elif csm_delta <= -1.0:
            state = WaveState.TYPE_B_COMPRESSION_ARMED
            permission = "WAIT"
            corr_type = "TYPE_B_COIL"
            summary = f"CSM OPPOSED WAIT: Flow Mismatch (Delta {csm_delta:+.2f}) -> WAIT"
            
        elif in_favorable_zone and is_compression and is_reclaim and csm_delta >= -0.2:
            state = WaveState.RECLAIM_CONFIRMED_GO
            permission = "GO"
            corr_type = "TYPE_B_COIL"
            summary = f"RECLAIM CONFIRMED GO: Type B Coil Reclaimed (DR {dr_pos*100:.1f}%, Reclaim {is_reclaim}) -> GO"
            
        elif in_favorable_zone and is_compression:
            state = WaveState.TYPE_B_COMPRESSION_ARMED
            permission = "ARM"
            corr_type = "TYPE_B_COIL"
            summary = f"TYPE B COMPRESSION ARMED: Basing in Area of Value (DR {dr_pos*100:.1f}%, Overlap {overlap_ratio:.2f}) -> ARM"
            
        else:
            state = WaveState.TYPE_B_COMPRESSION_ARMED if in_favorable_zone else WaveState.TYPE_A_WATERFALL_LOCK
            permission = "ARM" if in_favorable_zone else "WAIT"
            corr_type = "TYPE_B_COIL" if in_favorable_zone else "TYPE_A_WATERFALL"
            summary = f"EQUILIBRIUM: DR Pos {dr_pos*100:.1f}% -> {permission}"

        return WaveStateResult(
            state=state,
            permission=permission,
            is_trade_permitted=(permission in ("ARM", "GO")),
            direction=1,
            correction_type=corr_type,
            pullback_depth_atr=pullback_depth_atr,
            correction_velocity=velocity,
            overlap_ratio=overlap_ratio,
            body_efficiency=body_efficiency,
            bars_since_pivot=bars_since_pivot,
            dealing_range_pos=dr_pos,
            in_discount=in_favorable_zone,
            in_favorable_zone=in_favorable_zone,
            is_reclaim_confirmed=is_reclaim,
            macro_corridor=m_corr,
            target_station=m_target,
            psych_step=m_step,
            is_ceiling_rejected=is_ceil_rej,
            is_floor_rejected=is_flr_rej,
            summary=summary
        )

    # =========================================================================
    # 6. 4-DIMENSIONAL EVALUATION (DIRECTION = BEAR)
    # =========================================================================
    elif h4_trend_direction == -1:
        last_trough_p, last_trough_bar = known_sl[-1]
        bars_since_pivot = max(1, curr_idx - last_trough_bar)
        retrace_dist = max(0.0, c_price - last_trough_p)
        pullback_depth_atr = retrace_dist / atr_price
        
        corr_w = max(1, min(bars_since_pivot, 15))
        w_slice_h = h1_highs[n - corr_w : n]
        w_slice_l = h1_lows[n - corr_w : n]
        w_slice_o = h1_opens[n - corr_w : n]
        w_slice_c = h1_closes[n - corr_w : n]
        
        velocity = pullback_depth_atr / max(bars_since_pivot, 1)
        
        adj_overlaps = [max(0.0, min(w_slice_h[k], w_slice_h[k+1]) - max(w_slice_l[k], w_slice_l[k+1])) for k in range(len(w_slice_h)-1)]
        overlap_ratio = float(np.mean(adj_overlaps) / atr_price) if adj_overlaps else 0.0
        
        bull_bodies = np.maximum(0.0, w_slice_c - w_slice_o)
        total_ranges = np.maximum(1e-5, w_slice_h - w_slice_l)
        body_efficiency = float(np.sum(bull_bodies) / np.sum(total_ranges))
        
        in_favorable_zone = dr_pos >= 0.50 # Premium for SELL
        is_reclaim = is_bear_displacement or is_bear_micro_bos
        
        is_waterfall = (velocity >= 0.30) and (overlap_ratio < 0.35) and (body_efficiency >= 0.45) and (bars_since_pivot <= 5)
        is_compression = not is_waterfall and (bars_since_pivot >= 3)
        
        # Permission Matrix Resolution
        if pullback_depth_atr < 0.40 and bars_since_pivot <= 2:
            state = WaveState.EXPANSION_WAIT
            permission = "WAIT"
            corr_type = "EXPANSION"
            summary = f"EXPANSION WAIT: Price near floor ({pullback_depth_atr:.2f} ATR) -> WAIT (No FOMO)"
            
        elif is_waterfall or (not in_favorable_zone and velocity >= 0.35):
            state = WaveState.TYPE_A_WATERFALL_LOCK
            permission = "LOCK"
            corr_type = "TYPE_A_WATERFALL"
            summary = f"TYPE A RALLY LOCK: Violent Surge ({velocity:.2f} ATR/b, BodyEff {body_efficiency*100:.0f}%) -> LOCK"
            
        elif csm_delta >= 1.0:
            state = WaveState.TYPE_B_COMPRESSION_ARMED
            permission = "WAIT"
            corr_type = "TYPE_B_COIL"
            summary = f"CSM OPPOSED WAIT: Flow Mismatch (Delta {csm_delta:+.2f}) -> WAIT"
            
        elif in_favorable_zone and is_compression and is_reclaim and csm_delta <= 0.2:
            state = WaveState.RECLAIM_CONFIRMED_GO
            permission = "GO"
            corr_type = "TYPE_B_COIL"
            summary = f"RECLAIM CONFIRMED GO: Type B Coil Reclaimed (DR {dr_pos*100:.1f}%, Reclaim {is_reclaim}) -> GO"
            
        elif in_favorable_zone and is_compression:
            state = WaveState.TYPE_B_COMPRESSION_ARMED
            permission = "ARM"
            corr_type = "TYPE_B_COIL"
            summary = f"TYPE B COMPRESSION ARMED: Basing in Premium (DR {dr_pos*100:.1f}%, Overlap {overlap_ratio:.2f}) -> ARM"
            
        else:
            state = WaveState.TYPE_B_COMPRESSION_ARMED if in_favorable_zone else WaveState.TYPE_A_WATERFALL_LOCK
            permission = "ARM" if in_favorable_zone else "WAIT"
            corr_type = "TYPE_B_COIL" if in_favorable_zone else "TYPE_A_WATERFALL"
            summary = f"EQUILIBRIUM: DR Pos {dr_pos*100:.1f}% -> {permission}"

        return WaveStateResult(
            state=state,
            permission=permission,
            is_trade_permitted=(permission in ("ARM", "GO")),
            direction=-1,
            correction_type=corr_type,
            pullback_depth_atr=pullback_depth_atr,
            correction_velocity=velocity,
            overlap_ratio=overlap_ratio,
            body_efficiency=body_efficiency,
            bars_since_pivot=bars_since_pivot,
            dealing_range_pos=dr_pos,
            in_discount=in_favorable_zone,
            in_favorable_zone=in_favorable_zone,
            is_reclaim_confirmed=is_reclaim,
            macro_corridor=m_corr,
            target_station=m_target,
            psych_step=m_step,
            is_ceiling_rejected=is_ceil_rej,
            is_floor_rejected=is_flr_rej,
            summary=summary
        )

    # =========================================================================
    # 7. NEUTRAL RANGING
    # =========================================================================
    else:
        return WaveStateResult(
            state=WaveState.NEUTRAL_RANGING,
            permission="ARM",
            is_trade_permitted=True,
            direction=0,
            correction_type="NEUTRAL",
            pullback_depth_atr=0.0,
            correction_velocity=0.0,
            overlap_ratio=0.0,
            body_efficiency=0.0,
            bars_since_pivot=0,
            dealing_range_pos=dr_pos,
            in_discount=True,
            in_favorable_zone=True,
            is_reclaim_confirmed=False,
            macro_corridor=m_corr,
            target_station=m_target,
            psych_step=m_step,
            is_ceiling_rejected=is_ceil_rej,
            is_floor_rejected=is_flr_rej,
            summary=f"NEUTRAL RANGING: DR Pos {dr_pos*100:.1f}% -> Open for Boundary Mean Reversion"
        )
