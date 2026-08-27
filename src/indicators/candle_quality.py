"""
Candle Quality Classifier.
Quantifies breakout candle strength: body ratio, wick ratio, velocity vs ATR, engulfing.
Used by sweep_detector.py to differentiate real breakouts from liquidity sweeps.

Verdict:
  STRONG_BREAK   - High body ratio, minimal shadow on break side, velocity >= 0.8x ATR
  WEAK_BREAK     - Moderate body, some shadow, velocity 0.4-0.8x ATR
  SUSPECT_SWEEP  - Large wick on break side / body < 40%, price likely reverting
  INDECISION     - Doji / tiny body, no directional conviction
"""
from typing import List, Dict, Any, Optional
import numpy as np


def classify_candle(
    o: float, h: float, l: float, c: float,
    atr: float,
    prev_o: Optional[float] = None,
    prev_h: Optional[float] = None,
    prev_l: Optional[float] = None,
    prev_c: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Classify a single candle's quality for breakout vs sweep context.

    Returns:
        body_ratio     : abs(c-o) / (h-l). >= 0.60 = strong directional
        upper_wick_pct : (h - max(o,c)) / (h-l). Large = bearish rejection on top
        lower_wick_pct : (min(o,c) - l) / (h-l). Large = bullish rejection on bottom
        velocity_atr   : abs(c-o) / atr. >= 0.8 = strong momentum candle
        is_bullish_engulf : body engulfs prior candle's full body (bullish)
        is_bearish_engulf : body engulfs prior candle's full body (bearish)
        direction      : "bullish" | "bearish" | "neutral"
        verdict        : "STRONG_BREAK" | "WEAK_BREAK" | "SUSPECT_SWEEP" | "INDECISION"
        sweep_side     : "top" | "bottom" | None — which side the wick sweeps liquidity
    """
    candle_range = max(h - l, atr * 0.01, 1e-8)
    body         = abs(c - o)
    body_top     = max(o, c)
    body_bot     = min(o, c)

    body_ratio     = body / candle_range
    upper_wick_pct = (h - body_top) / candle_range
    lower_wick_pct = (body_bot - l) / candle_range
    velocity_atr   = body / max(atr, 1e-8)
    direction      = "bullish" if c > o else ("bearish" if c < o else "neutral")

    # Engulfing: current body fully engulfs prior body
    is_bullish_engulf = False
    is_bearish_engulf = False
    if prev_o is not None and prev_c is not None:
        prev_body_top = max(prev_o, prev_c)
        prev_body_bot = min(prev_o, prev_c)
        if direction == "bullish" and body_bot < prev_body_bot and body_top > prev_body_top:
            is_bullish_engulf = True
        elif direction == "bearish" and body_top > prev_body_top and body_bot < prev_body_bot:
            is_bearish_engulf = True

    # Sweep side: which end has a disproportionately long wick vs body
    sweep_side = None
    if upper_wick_pct >= 0.40 and upper_wick_pct > body_ratio * 0.8:
        sweep_side = "top"      # price swept high liquidity then rejected
    elif lower_wick_pct >= 0.40 and lower_wick_pct > body_ratio * 0.8:
        sweep_side = "bottom"   # price swept low liquidity then rejected

    # Verdict — order matters: sweep_side check first (pin bar IS a sweep signal)
    if sweep_side is not None:
        verdict = "SUSPECT_SWEEP"          # any dominant wick = sweep regardless of body size
    elif body_ratio < 0.15:
        verdict = "INDECISION"
    elif body_ratio >= 0.60 and velocity_atr >= 0.80:
        verdict = "STRONG_BREAK"
    elif body_ratio >= 0.40 and velocity_atr >= 0.40:
        verdict = "WEAK_BREAK"
    else:
        verdict = "INDECISION"

    return {
        "body_ratio":       round(body_ratio, 3),
        "upper_wick_pct":   round(upper_wick_pct, 3),
        "lower_wick_pct":   round(lower_wick_pct, 3),
        "velocity_atr":     round(velocity_atr, 3),
        "is_bullish_engulf": is_bullish_engulf,
        "is_bearish_engulf": is_bearish_engulf,
        "direction":        direction,
        "verdict":          verdict,
        "sweep_side":       sweep_side,
    }


def classify_breakout_sequence(
    bars: List[Dict[str, float]],   # list of {"o","h","l","c"} dicts, newest last
    atr: float,
    zone_top: float,
    zone_bottom: float,
) -> Dict[str, Any]:
    """
    Classify a multi-bar breakout sequence relative to a structural zone.
    Detects: direct breakout, consolidation-then-break, or sweep.

    Args:
        bars        : Recent bars, oldest first, newest last (at least 3)
        atr         : Current ATR for velocity scoring
        zone_top    : Upper boundary of the structural zone (resistance / dealing range top)
        zone_bottom : Lower boundary of the structural zone (support / dealing range bottom)

    Returns:
        breakout_type : "DIRECT_BREAK" | "CONSOLIDATION_BREAK" | "SWEEP_REVERSAL" | "NONE"
        direction     : "bullish" | "bearish" | None
        candle_quality: classify_candle() output for the triggering bar
        bars_in_zone  : how many bars consolidated near the zone edge before breaking
        confidence    : 0-100 score
    """
    if len(bars) < 3:
        return {"breakout_type": "NONE", "direction": None, "confidence": 0}

    last  = bars[-1]
    prev  = bars[-2]
    pprev = bars[-3]

    o, h, l, c = last["o"], last["h"], last["l"], last["c"]
    quality = classify_candle(o, h, l, c, atr, prev["o"], prev["h"], prev["l"], prev["c"])

    breakout_type = "NONE"
    direction     = None
    bars_in_zone  = 0
    confidence    = 0

    # Count recent bars consolidating near zone edge (within 0.5 ATR of boundary)
    for bar in reversed(bars[:-1]):
        near_top = zone_top - atr * 0.5 <= bar["h"] <= zone_top + atr * 0.3
        near_bot = zone_bottom - atr * 0.3 <= bar["l"] <= zone_bottom + atr * 0.5
        if near_top or near_bot:
            bars_in_zone += 1
        else:
            break

    # Bearish breakout: close below zone_bottom
    if c < zone_bottom:
        direction = "bearish"
        broke_clean  = c < zone_bottom - atr * 0.1   # closed clearly below, not just touching
        long_wick_up = quality["upper_wick_pct"] >= 0.35  # body pulled down but wick up = suspect

        if quality["verdict"] == "SUSPECT_SWEEP" or (quality["lower_wick_pct"] >= 0.40 and not broke_clean):
            breakout_type = "SWEEP_REVERSAL"
            confidence    = 70 + int(quality["lower_wick_pct"] * 30)
        elif bars_in_zone >= 3:
            breakout_type = "CONSOLIDATION_BREAK"
            confidence    = 60 + int(quality["body_ratio"] * 40)
        elif quality["verdict"] == "STRONG_BREAK" and broke_clean:
            breakout_type = "DIRECT_BREAK"
            confidence    = 75 + int(quality["velocity_atr"] * 15)
        else:
            breakout_type = "WEAK_BREAK"
            confidence    = 40

    # Bullish breakout: close above zone_top
    elif c > zone_top:
        direction = "bullish"
        broke_clean   = c > zone_top + atr * 0.1
        long_wick_dn  = quality["lower_wick_pct"] >= 0.35

        if quality["verdict"] == "SUSPECT_SWEEP" or (quality["upper_wick_pct"] >= 0.40 and not broke_clean):
            breakout_type = "SWEEP_REVERSAL"
            confidence    = 70 + int(quality["upper_wick_pct"] * 30)
        elif bars_in_zone >= 3:
            breakout_type = "CONSOLIDATION_BREAK"
            confidence    = 60 + int(quality["body_ratio"] * 40)
        elif quality["verdict"] == "STRONG_BREAK" and broke_clean:
            breakout_type = "DIRECT_BREAK"
            confidence    = 75 + int(quality["velocity_atr"] * 15)
        else:
            breakout_type = "WEAK_BREAK"
            confidence    = 40

    return {
        "breakout_type":   breakout_type,
        "direction":       direction,
        "candle_quality":  quality,
        "bars_in_zone":    bars_in_zone,
        "confidence":      min(confidence, 100),
    }
