"""
Sweep Detector — Classifies post-compression breakouts as SWEEP or BREAKOUT.

Combines all 5 detection dimensions:
1. Candle quality (body ratio, wick, velocity, engulfing) — candle_quality.py
2. Wave regime & compression age — wave_regime.py
3. CHoCH / BOS (close inside/outside range) — lux_smc.py
4. Retest timing (bars from breakout to retest of broken level)
5. H4 structural context (OB, FVG, EQH/EQL proximity)

Entry Mode:
  WAIT_RETEST    — Breakout valid, but wait for pullback to broken level
  CHASE_BREAKOUT — Strong momentum breakout, enter market/stop order now
  COUNTER_SWEEP  — This was a sweep, enter opposite direction at sweep level
  SKIP           — Ambiguous or insufficient evidence
"""
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from src.indicators.candle_quality import classify_candle, classify_breakout_sequence
from src.indicators.wave_regime    import evaluate_wave_regime


# ── Constants ─────────────────────────────────────────────────────────────────
RETEST_BARS_INSTANT  = 3    # <= 3 bars → instant retest (sweep signal)
RETEST_BARS_QUICK    = 12   # 4–12 bars → quick retest (ambiguous)
RETEST_BARS_DELAYED  = 13   # >= 13 bars → delayed / healthy pullback


def _count_zone_tests(highs: List[float], lows: List[float],
                       level: float, atr: float,
                       lookback: int = 50) -> int:
    """Count how many prior bars respected (touched & reversed from) a price level."""
    count = 0
    recent_h = highs[-lookback:]
    recent_l = lows[-lookback:]
    tolerance = atr * 0.25
    for i in range(len(recent_h) - 1):
        # Touch from above (support test)
        if abs(recent_l[i] - level) <= tolerance and recent_h[i + 1] > recent_l[i]:
            count += 1
        # Touch from below (resistance test)
        elif abs(recent_h[i] - level) <= tolerance and recent_l[i + 1] < recent_h[i]:
            count += 1
    return count


def detect(
    # ── OHLC arrays (execution TF, e.g. H1 or M30), newest last ──
    highs:   List[float],
    lows:    List[float],
    opens:   List[float],
    closes:  List[float],
    atr_exec: float,

    # ── Compression context ──
    prev_sqz_bars: int = 0,          # squeeze bars that just ended (from caller)
    timeframe_hours: float = 1.0,

    # ── Structural zone being broken ──
    zone_top:    Optional[float] = None,   # top of compression range / resistance
    zone_bottom: Optional[float] = None,   # bottom of compression range / support

    # ── H4 context (optional but strongly recommended) ──
    h4_ob_top:    Optional[float] = None,   # nearest H4 Bearish OB top
    h4_ob_bottom: Optional[float] = None,   # nearest H4 Bearish OB bottom
    h4_fvg_top:   Optional[float] = None,   # nearest H4 FVG top
    h4_fvg_bottom: Optional[float] = None,  # nearest H4 FVG bottom
    h4_eqh:       Optional[float] = None,   # Equal High (liquidity above)
    h4_eql:       Optional[float] = None,   # Equal Low  (liquidity below)
    h4_ema50:     Optional[float] = None,   # H4 EMA50 dynamic support/resistance
    d1_ema200:    Optional[float] = None,   # D1 EMA200 macro trend

    # ── Retest tracking (caller provides bars since breakout occurred) ──
    bars_since_break: int = 0,

) -> Dict[str, Any]:
    """
    Classify current market state as SWEEP or BREAKOUT from compression zone.

    Returns:
        verdict       : "SWEEP" | "BREAKOUT" | "AMBIGUOUS"
        entry_mode    : "WAIT_RETEST" | "CHASE_BREAKOUT" | "COUNTER_SWEEP" | "SKIP"
        direction     : "bullish" | "bearish" | None
        confidence    : 0-100
        retest_type   : "INSTANT" | "QUICK" | "DELAYED" | "NONE"
        evidence      : list of signal strings explaining the verdict
        regime        : wave regime result dict
        breakout_seq  : breakout sequence classification dict
    """
    n = len(closes)
    if n < 30 or zone_top is None or zone_bottom is None:
        return {
            "verdict": "AMBIGUOUS", "entry_mode": "SKIP",
            "direction": None, "confidence": 0,
            "retest_type": "NONE", "evidence": ["Insufficient data"],
            "regime": {}, "breakout_seq": {}
        }

    evidence: List[str] = []
    score_sweep    = 0
    score_breakout = 0

    last_c = closes[-1]
    last_h = highs[-1]
    last_l = lows[-1]

    # ── 1. Wave Regime ─────────────────────────────────────────────────────────
    regime = evaluate_wave_regime(
        highs, lows, closes,
        timeframe_hours=timeframe_hours,
        dealing_range_window=min(n, 100),
        prev_sqz_bars=prev_sqz_bars
    )
    eff_sqz = regime["effective_sqz_bars"]
    regime_name = regime["regime"]

    if regime_name == "SUPER_COMPRESSION_THRUST":
        score_breakout += 25
        evidence.append(f"SUPER_COMPRESSION sqz={eff_sqz}b → strong breakout bias")
    elif regime_name == "MATURE_SQUEEZE":
        score_breakout += 10
        evidence.append(f"MATURE_SQUEEZE sqz={eff_sqz}b → moderate breakout bias")
    else:  # YOUNG_OSCILLATION
        score_sweep += 15
        evidence.append(f"YOUNG_OSCILLATION → elevated liquidity sweep probability")

    # ── 2. Candle Quality & Breakout Sequence ──────────────────────────────────
    bars_dicts = [{"o": opens[i], "h": highs[i], "l": lows[i], "c": closes[i]}
                  for i in range(max(0, n - 10), n)]
    bseq = classify_breakout_sequence(bars_dicts, atr_exec, zone_top, zone_bottom)
    btype = bseq["breakout_type"]
    bdir  = bseq["direction"]
    cq    = bseq["candle_quality"]
    bars_in_zone = bseq["bars_in_zone"]

    if btype == "DIRECT_BREAK":
        score_breakout += 30
        evidence.append(f"DIRECT_BREAK body={cq['body_ratio']:.2f} vel={cq['velocity_atr']:.2f}x ATR")
    elif btype == "CONSOLIDATION_BREAK":
        score_breakout += 20
        evidence.append(f"CONSOLIDATION_BREAK {bars_in_zone} bars near zone → controlled break")
    elif btype == "SWEEP_REVERSAL":
        score_sweep += 35
        evidence.append(f"SWEEP_REVERSAL wick={cq.get('sweep_side','?')} side, body={cq['body_ratio']:.2f}")
    elif btype == "WEAK_BREAK":
        score_sweep += 10
        evidence.append(f"WEAK_BREAK body={cq['body_ratio']:.2f} — conviction low")

    # Engulfing bonus
    if cq.get("is_bullish_engulf") or cq.get("is_bearish_engulf"):
        score_breakout += 15
        evidence.append("ENGULFING candle confirms momentum")

    # ── 3. CHoCH: did price close back inside the zone? ───────────────────────
    if bdir == "bearish" and last_c > zone_bottom:
        score_sweep += 25
        evidence.append("CHoCH: closed BACK inside zone after bearish break → sweep")
    elif bdir == "bullish" and last_c < zone_top:
        score_sweep += 25
        evidence.append("CHoCH: closed BACK inside zone after bullish break → sweep")

    # ── 4. Zone Respect Count (multi-TF tests) ─────────────────────────────────
    if bdir == "bearish" and zone_bottom is not None:
        tests = _count_zone_tests(highs, lows, zone_bottom, atr_exec, lookback=80)
        if tests >= 3:
            score_sweep += 20
            evidence.append(f"Zone tested {tests}x → high liquidity, likely sweep before real break")
        elif tests >= 1:
            score_breakout += 10
            evidence.append(f"Zone tested {tests}x → some respect, break plausible")
    elif bdir == "bullish" and zone_top is not None:
        tests = _count_zone_tests(highs, lows, zone_top, atr_exec, lookback=80)
        if tests >= 3:
            score_sweep += 20
            evidence.append(f"Zone tested {tests}x → high liquidity, likely sweep before real break")
        elif tests >= 1:
            score_breakout += 10
            evidence.append(f"Zone tested {tests}x → some respect, break plausible")

    # ── 5. Retest Timing ───────────────────────────────────────────────────────
    if bars_since_break > 0:
        if bars_since_break <= RETEST_BARS_INSTANT:
            retest_type = "INSTANT"
            score_sweep += 20
            evidence.append(f"INSTANT RETEST {bars_since_break}b → sweep confirmed, reversal likely")
        elif bars_since_break <= RETEST_BARS_QUICK:
            retest_type = "QUICK"
            score_breakout += 5
            evidence.append(f"QUICK RETEST {bars_since_break}b → ambiguous pullback")
        else:
            retest_type = "DELAYED"
            score_breakout += 20
            evidence.append(f"DELAYED RETEST {bars_since_break}b → healthy breakout pullback, entry valid")
    else:
        retest_type = "NONE"

    # ── 6. H4 Context ──────────────────────────────────────────────────────────
    if h4_ob_bottom is not None and h4_ob_top is not None:
        in_h4_ob = h4_ob_bottom <= last_c <= h4_ob_top or h4_ob_bottom <= last_h and last_l <= h4_ob_top
        if in_h4_ob:
            score_sweep += 20
            evidence.append("Price in H4 Order Block → institutional reversal zone, sweep likely")

    if h4_eqh is not None and bdir == "bullish":
        near_eqh = abs(last_h - h4_eqh) <= atr_exec * 0.5
        if near_eqh:
            score_sweep += 15
            evidence.append(f"Near H4 EQH {h4_eqh:.5f} → liquidity grab target above")

    if h4_eql is not None and bdir == "bearish":
        near_eql = abs(last_l - h4_eql) <= atr_exec * 0.5
        if near_eql:
            score_sweep += 15
            evidence.append(f"Near H4 EQL {h4_eql:.5f} → liquidity grab target below")

    if d1_ema200 is not None:
        macro_aligned = (bdir == "bearish" and last_c < d1_ema200) or \
                        (bdir == "bullish" and last_c > d1_ema200)
        if macro_aligned:
            score_breakout += 20
            evidence.append(f"D1 EMA200 macro trend aligned with break → continuation bias")
        else:
            score_sweep += 20
            evidence.append(f"COUNTER-TREND vs D1 EMA200 → likely sweep, not breakout")

    # ── Verdict ────────────────────────────────────────────────────────────────
    total = score_sweep + score_breakout
    if total == 0:
        total = 1

    sweep_pct    = score_sweep    / total * 100
    breakout_pct = score_breakout / total * 100

    if sweep_pct >= 60:
        verdict    = "SWEEP"
        entry_mode = "COUNTER_SWEEP"
        confidence = int(sweep_pct)
    elif breakout_pct >= 60:
        verdict    = "BREAKOUT"
        # If delayed retest, wait for retest; if strong momentum, chase
        if retest_type == "DELAYED" or btype == "CONSOLIDATION_BREAK":
            entry_mode = "WAIT_RETEST"
        elif btype == "DIRECT_BREAK" and eff_sqz >= 12:
            entry_mode = "CHASE_BREAKOUT"
        else:
            entry_mode = "WAIT_RETEST"
        confidence = int(breakout_pct)
    else:
        verdict    = "AMBIGUOUS"
        entry_mode = "SKIP"
        confidence = max(int(sweep_pct), int(breakout_pct))

    return {
        "verdict":      verdict,
        "entry_mode":   entry_mode,
        "direction":    bdir,
        "confidence":   confidence,
        "retest_type":  retest_type,
        "evidence":     evidence,
        "regime":       regime,
        "breakout_seq": bseq,
        "score_sweep":     score_sweep,
        "score_breakout":  score_breakout,
    }
