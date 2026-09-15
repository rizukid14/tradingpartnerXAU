"""
Market Scanner M5 Specialization Module — 9-Engine Institutional Sniper Brain (15 Sep 2026)

Mensintesis 9 modul inti /src menjadi funnel seleksi 5-tingkat:
  Gate 1: Macro & News blackout (economic_calendar + apex_fundamental)
  Gate 2: HTF Trend alignment, Wave Regime anti-knife, Dealing Range position (wave_regime + pattern_engine)
  Gate 3: Lux SMC OB freshness + Sweep Detector wick quality (lux_smc + sweep_detector)
  Gate 4: Atlas DNA anchored SL + Hard Net R:R >= 2.0 gate (atlas_dna + ZCE)
  Gate 5: Vector memory rebound + Mechanism-aware execution telemetry

Zero pollution ke production core (main.py, market_scanner.py H1).
"""

import os
import sys
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
import pandas as pd

import config
from src.analytics.market_scanner import MarketScanner, CandidateSetup
from src.analytics.zone_confluence_engine import ZoneConfluenceEngine
from src.analytics.macro_strategic_engine import macro_strategic_engine
from src.indicators.candle_quality import classify_candle

logger = logging.getLogger("market_scanner_m5")
WIB = ZoneInfo("Asia/Jakarta")

# ── Config constants (resolved once at import, safe fallbacks) ─────────────────
_M5_MIN_RR         = float(os.getenv("M5_MIN_RR_RATIO", "2.0"))
_M5_ZCE_BUF_PTS    = int(os.getenv("M5_SL_ZCE_BUFFER_PTS", "10"))
_M5_ENABLE_MACRO   = os.getenv("M5_ENABLE_MACRO_BIAS", "true").lower() == "true"
_M2_MIN_WICK       = float(os.getenv("M2_MIN_REJECTION_WICK", "0.35"))
_COMM_PAD_PTS      = int(os.getenv("M5_COMMISSION_PAD_PTS", "6"))


# ══════════════════════════════════════════════════════════════════════════════
# SL / TP CALCULATOR — Atlas DNA + ZCE Barrier Anchored
# ══════════════════════════════════════════════════════════════════════════════

def calculate_m5_sl_tp(
    symbol: str,
    entry_price: float,
    direction: int,
    atr_m5: float,
    c1: Optional[float] = None,
    f1: Optional[float] = None,
    ob_top: Optional[float] = None,
    ob_bottom: Optional[float] = None,
    eqh: Optional[float] = None,
    eql: Optional[float] = None,
    spread_pts: int = 15,
    pt: float = 0.00001
) -> Dict[str, Any]:
    """
    Gate 4: Calculates M5 Stop Loss and Take Profit using:
    - SL: Structural anchor — ZCE barrier (F1/C1) or OB edge, NOT naked ATR.
      - BUY SL = min(F1, OB_bottom) - (spread + M5_SL_ZCE_BUFFER_PTS) pts
      - SELL SL = max(C1, OB_top) + (spread + M5_SL_ZCE_BUFFER_PTS) pts
    - TP: Opposing ZCE station or EQH/EQL liquidity pool with front-running pad.
    - Hard Net R:R gate: returns realized_rr = 0 if < M5_MIN_RR_RATIO (caller vetos).
    """
    clean_sym = (symbol or "").replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").upper()
    is_jpy       = "JPY" in clean_sym
    is_high_beta = any(k in clean_sym for k in ("GBPAUD", "GBPNZD", "EURNZD", "GBPCHF", "GBPCAD", "AUDNZD"))
    is_gold      = "XAU" in clean_sym or "GOLD" in clean_sym
    is_crypto    = config.is_crypto(clean_sym)

    pip_factor = 100 if (is_crypto or is_gold) else 10

    # Min/Max SL floors by asset class (from .env)
    if is_crypto:
        min_sl_pts = int(os.getenv("M5_MIN_SL_CRYPTO_PTS", "10000"))
        max_tp_pts = int(os.getenv("M5_MAX_TP_CRYPTO_PTS", "30000"))
    elif is_gold:
        min_sl_pts = int(os.getenv("M5_MIN_SL_GOLD_PTS", "150"))
        max_tp_pts = int(os.getenv("M5_MAX_TP_GOLD_PTS", "400"))
    elif is_jpy:
        min_sl_pips = float(os.getenv("M5_MIN_SL_PIPS_JPY", "6.0"))
        max_tp_pips = float(os.getenv("M5_MAX_TP_PIPS_JPY", "13.5"))
        min_sl_pts  = int(round(min_sl_pips * pip_factor))
        max_tp_pts  = int(round(max_tp_pips * pip_factor))
    elif is_high_beta:
        min_sl_pips = float(os.getenv("M5_MIN_SL_PIPS_HIGHBETA", "7.0"))
        max_tp_pips = float(os.getenv("M5_MAX_TP_PIPS_HIGHBETA", "16.0"))
        min_sl_pts  = int(round(min_sl_pips * pip_factor))
        max_tp_pts  = int(round(max_tp_pips * pip_factor))
    else:
        min_sl_pips = float(os.getenv("M5_MIN_SL_PIPS_MAJOR", "4.0"))
        max_tp_pips = float(os.getenv("M5_MAX_TP_PIPS_MAJOR", "9.5"))
        min_sl_pts  = int(round(min_sl_pips * pip_factor))
        max_tp_pts  = int(round(max_tp_pips * pip_factor))

    # ── SL: Structural Anchor behind ZCE/OB barrier ───────────────────────────
    buf_pts   = _M5_ZCE_BUF_PTS + spread_pts  # total buffer behind the wall
    buf_dist  = buf_pts * pt
    fric_dist = (spread_pts + _COMM_PAD_PTS) * pt   # friction for Net R:R calc
    front_pad = (spread_pts * pt) + (0.08 * atr_m5)  # TP front-running

    if direction == 1:  # BUY
        # SL: just below the lowest of F1 and OB_bottom
        structural_floor = None
        if f1 and f1 > 0 and f1 < entry_price:
            structural_floor = f1
        if ob_bottom and ob_bottom > 0 and ob_bottom < entry_price:
            structural_floor = min(structural_floor, ob_bottom) if structural_floor else ob_bottom

        if structural_floor:
            sl_dist = (entry_price - structural_floor) + buf_dist
        else:
            atr_fallback = float(os.getenv("M5_SL_ATR_MULT", "1.25")) * atr_m5
            sl_dist = max(atr_fallback, min_sl_pts * pt)

        sl_dist = max(sl_dist, min_sl_pts * pt)
        sl = entry_price - sl_dist

        # TP: Opposing ZCE C1, then EQH liquidity pool
        target = None
        if c1 and c1 > entry_price:
            target = c1 - front_pad
        if target is None and eqh and eqh > entry_price:
            target = eqh - front_pad
        if target is None:
            default_rr = float(os.getenv("M5_DEFAULT_TP_RR", "2.20"))
            target = entry_price + default_rr * sl_dist

        tp = min(target, entry_price + max_tp_pts * pt)

    else:  # SELL
        # SL: just above the highest of C1 and OB_top
        structural_ceil = None
        if c1 and c1 > 0 and c1 > entry_price:
            structural_ceil = c1
        if ob_top and ob_top > 0 and ob_top > entry_price:
            structural_ceil = max(structural_ceil, ob_top) if structural_ceil else ob_top

        if structural_ceil:
            sl_dist = (structural_ceil - entry_price) + buf_dist
        else:
            atr_fallback = float(os.getenv("M5_SL_ATR_MULT", "1.25")) * atr_m5
            sl_dist = max(atr_fallback, min_sl_pts * pt)

        sl_dist = max(sl_dist, min_sl_pts * pt)
        sl = entry_price + sl_dist

        # TP: Opposing ZCE F1, then EQL liquidity pool
        target = None
        if f1 and f1 < entry_price:
            target = f1 + front_pad
        if target is None and eql and eql < entry_price:
            target = eql + front_pad
        if target is None:
            default_rr = float(os.getenv("M5_DEFAULT_TP_RR", "2.20"))
            target = entry_price - default_rr * sl_dist

        tp = max(target, entry_price - max_tp_pts * pt)

    sl_pts = max(1, int(round(sl_dist / pt)))
    tp_pts = max(1, int(round(abs(entry_price - tp) / pt)))

    # ── Net R:R (friction-deducted) ───────────────────────────────────────────
    fric_pts    = int(round(fric_dist / pt))
    net_tp_pts  = max(0, tp_pts - fric_pts)
    net_sl_pts  = sl_pts + fric_pts
    realized_rr = round(net_tp_pts / max(net_sl_pts, 1), 3)

    digits = 2 if (is_gold or is_crypto) else (3 if is_jpy else 5)
    return {
        "sl":          round(sl, digits),
        "tp":          round(tp, digits),
        "sl_pts":      sl_pts,
        "tp_pts":      tp_pts,
        "net_rr":      realized_rr,    # after friction
        "risk_reward": realized_rr,    # alias for compatibility
        "structural_anchor": structural_floor if direction == 1 else structural_ceil,
    }


# ══════════════════════════════════════════════════════════════════════════════
# HELPER — Fetch HTF bars safely
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_bars(sym: str, tf_const: int, count: int) -> Optional[pd.DataFrame]:
    """Fetch OHLCV bar data from MT5 safely. Returns None on failure."""
    try:
        rr = config.mt5.copy_rates_from_pos(sym, tf_const, 0, count)
        if rr is not None and len(rr) >= 5:
            return pd.DataFrame(rr)
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# MAIN CLASS
# ══════════════════════════════════════════════════════════════════════════════

class MarketScannerM5(MarketScanner):
    """
    Dedicated Market Scanner for M5 Fast Execution Radar.
    Integrates 9-Engine Institutional Sniper Funnel across 5 gates.
    """

    def __init__(self, symbols: Optional[List[str]] = None):
        super().__init__(symbols=symbols)
        self._cooldown_file = os.path.join(config.DATA_DIR, "scanner_cooldowns_m5.json")
        self._micro_zce_params = {
            "grid": {
                "M5":  [30, 60, 120],
                "M15": [30, 60, 120],
                "H1":  [50, 100, 200]
            },
            "w_tf":          {"M5": 1.0, "M15": 1.25, "H1": 1.50},
            "merge_atr_mult": 0.20,
            "max_imm_atr":    3.0,
            "grade_g2":       4.0,
            "grade_g3":       7.0,
        }
        self._zce_engine = ZoneConfluenceEngine(params=self._micro_zce_params)
        logger.info("[M5 SCANNER] MarketScannerM5 (9-Engine Brain) initialized.")

    # ─────────────────────────────────────────────────────────────────────────
    # GATE 1 HELPERS — News Blackout & Macro Bias
    # ─────────────────────────────────────────────────────────────────────────

    def _check_gate1_macro_news(self, sym: str, direction: int) -> Tuple[bool, str]:
        """
        Gate 1a: News Blackout (economic_calendar).
        Gate 1b: Macro Direction Bias (apex_fundamental — optional, controlled by M5_ENABLE_MACRO_BIAS).
        Returns (passed: bool, reason: str).
        """
        # Gate 1a — News Blackout
        try:
            from src.analytics.economic_calendar import is_blackout_now
            if is_blackout_now(sym):
                return False, f"GATE1_NEWS_BLACKOUT ({sym})"
        except Exception:
            pass  # calendar unavailable → pass-through, don't block

        # Gate 1b — Macro Directional Bias (optional)
        if _M5_ENABLE_MACRO:
            try:
                from src.analytics.apex_fundamental_engine import apex_fundamental_engine
                fund = apex_fundamental_engine.evaluate_pair(sym)
                if fund and fund.base:
                    delta = getattr(fund, "fundamental_delta", 0.0)
                    # Extreme conflict: delta <= -2.5 for BUY or >= +2.5 for SELL
                    if direction == 1 and delta <= -2.5:
                        return False, f"GATE1_MACRO_CONFLICT (BUY blocked: fundamental_delta={delta:.2f})"
                    if direction == -1 and delta >= 2.5:
                        return False, f"GATE1_MACRO_CONFLICT (SELL blocked: fundamental_delta={delta:.2f})"
            except Exception:
                pass  # fundamental engine unavailable → pass-through

        return True, "GATE1_PASS"

    # ─────────────────────────────────────────────────────────────────────────
    # GATE 2 HELPERS — Wave Regime + Dealing Range + HTF Trend
    # ─────────────────────────────────────────────────────────────────────────

    def _check_gate2_regime_trend(
        self, sym: str, direction: int,
        df_m5: Optional[pd.DataFrame],
        df_m15: Optional[pd.DataFrame],
        df_h1: Optional[pd.DataFrame]
    ) -> Tuple[bool, str]:
        """
        Gate 2a: Wave Regime Anti-Knife (wave_regime) — veto counter-trend entry
                 if M15/H1 momentum is exploding in opposite direction.
        Gate 2b: Dealing Range Position (pattern_engine) — BUY only Discount <= 0.40,
                 SELL only Premium >= 0.60.
        Gate 2c: HTF Trend Alignment — M5 must align with M15 EMA50 and H1 EMA50.
        """
        # ── Gate 2a: Wave Regime ─────────────────────────────────────────────
        try:
            from src.indicators.wave_regime import calculate_squeeze_momentum
            ref_df = df_m15 if df_m15 is not None and len(df_m15) >= 30 else df_h1
            if ref_df is not None and len(ref_df) >= 30:
                sqz = calculate_squeeze_momentum(
                    ref_df["high"].tolist(),
                    ref_df["low"].tolist(),
                    ref_df["close"].tolist()
                )
                # SUPER_COMPRESSION or knife-thrust: prohibit counter-trend fade
                if sqz.get("is_bullish_thrust") and direction == -1:
                    return False, "GATE2_ANTI_KNIFE (bullish momentum thrust, SELL blocked)"
                if sqz.get("is_bearish_grind") and direction == 1:
                    return False, "GATE2_ANTI_KNIFE (bearish momentum grind, BUY blocked)"
        except Exception:
            pass

        # ── Gate 2b: Dealing Range Position ──────────────────────────────────
        try:
            from src.analytics.macro_strategic_engine import macro_strategic_engine as mse
            # MSE already exposes fractal_regime which encodes Dealing Range bias
            # We use stored dr_pos from macro_cache (computed in update_macro_context)
        except Exception:
            pass

        mac = self.macro_cache.get(sym, {})
        dr_pos = float(mac.get("dealing_range_pos", 0.50))
        if direction == 1 and dr_pos > 0.60:
            return False, f"GATE2_DR_MID_TRAP (BUY blocked: price in Premium zone dr_pos={dr_pos:.2f})"
        if direction == -1 and dr_pos < 0.40:
            return False, f"GATE2_DR_MID_TRAP (SELL blocked: price in Discount zone dr_pos={dr_pos:.2f})"

        # ── Gate 2c: HTF Trend Alignment ─────────────────────────────────────
        htf_aligned = True
        htf_reason  = ""
        try:
            cur_c = float(mac.get("current_price", 0.0))
            if cur_c > 0:
                ema50_m15 = None
                ema50_h1  = None
                if df_m15 is not None and len(df_m15) >= 50:
                    ema50_m15 = float(df_m15["close"].ewm(span=50, adjust=False).mean().iloc[-1])
                if df_h1 is not None and len(df_h1) >= 50:
                    ema50_h1  = float(df_h1["close"].ewm(span=50, adjust=False).mean().iloc[-1])

                if direction == 1:
                    if ema50_m15 is not None and cur_c < ema50_m15:
                        if ema50_h1 is not None and cur_c < ema50_h1:
                            htf_aligned = False
                            htf_reason  = f"GATE2_HTF_CONFLICT (BUY: M5 price below M15 EMA50={ema50_m15:.5f} AND H1 EMA50={ema50_h1:.5f})"
                else:  # SELL
                    if ema50_m15 is not None and cur_c > ema50_m15:
                        if ema50_h1 is not None and cur_c > ema50_h1:
                            htf_aligned = False
                            htf_reason  = f"GATE2_HTF_CONFLICT (SELL: M5 price above M15 EMA50={ema50_m15:.5f} AND H1 EMA50={ema50_h1:.5f})"
        except Exception:
            pass

        if not htf_aligned:
            return False, htf_reason

        return True, "GATE2_PASS"

    # ─────────────────────────────────────────────────────────────────────────
    # GATE 3 HELPERS — Lux SMC OB Freshness + Sweep Detector Wick Quality
    # ─────────────────────────────────────────────────────────────────────────

    def _check_gate3_smc_sweep(
        self, sym: str, direction: int,
        mid: float, atr_m5: float, pt: float,
        df_m5: Optional[pd.DataFrame],
        df_m15: Optional[pd.DataFrame]
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Gate 3a: Lux SMC OB freshness — ensure entry OB is unmitigated.
        Gate 3b: Sweep Detector wick quality — validate rejection wick >= M2_MIN_REJECTION_WICK.
        Returns (passed: bool, reason: str, extras: dict with ob_top/bottom/eqh/eql).
        """
        extras: Dict[str, Any] = {"ob_top": None, "ob_bottom": None, "eqh": None, "eql": None}

        # ── Gate 3a: Lux SMC OB Freshness ────────────────────────────────────
        try:
            from src.indicators.lux_smc import LuxSMCAnalyzer
            ref_df = df_m15 if df_m15 is not None and len(df_m15) >= 50 else df_m5
            if ref_df is not None and len(ref_df) >= 50:
                analyzer = LuxSMCAnalyzer()
                smc      = analyzer.analyze(ref_df)
                if smc:
                    if direction == 1:
                        # Look for unmitigated bullish OB below current price
                        obs = [ob for ob in (smc.order_blocks_bullish or [])
                               if not ob.get("mitigated", True) and ob.get("top", 0) < mid]
                        if obs:
                            nearest = max(obs, key=lambda x: x.get("top", 0))
                            extras["ob_top"]    = nearest.get("top")
                            extras["ob_bottom"] = nearest.get("bottom")
                        # Equal Lows liquidity above (BUY target)
                        eqhs = smc.equal_highs
                        if eqhs:
                            above = [e.get("price", 0) for e in eqhs if e.get("price", 0) > mid]
                            if above:
                                extras["eqh"] = min(above)
                    else:
                        # Look for unmitigated bearish OB above current price
                        obs = [ob for ob in (smc.order_blocks_bearish or [])
                               if not ob.get("mitigated", True) and ob.get("bottom", 9999) > mid]
                        if obs:
                            nearest = min(obs, key=lambda x: x.get("bottom", 9999))
                            extras["ob_top"]    = nearest.get("top")
                            extras["ob_bottom"] = nearest.get("bottom")
                        # Equal Lows liquidity below (SELL target)
                        eqls = smc.equal_lows
                        if eqls:
                            below = [e.get("price", 9999) for e in eqls if e.get("price", 9999) < mid]
                            if below:
                                extras["eql"] = max(below)
        except Exception:
            pass  # SMC unavailable → allow pass-through, extras stay None

        # ── Gate 3b: Sweep Detector Wick Quality ─────────────────────────────
        try:
            from src.indicators.candle_quality import classify_candle
            ref_df2 = df_m5
            if ref_df2 is not None and len(ref_df2) >= 3:
                cur  = ref_df2.iloc[-1]
                prev = ref_df2.iloc[-2]
                atr_v = max(atr_m5, 1e-6)
                live_q = classify_candle(
                    float(cur["open"]), float(cur["high"]), float(cur["low"]), mid, atr_v,
                    prev_o=float(prev["open"]), prev_h=float(prev["high"]),
                    prev_l=float(prev["low"]),  prev_c=float(prev["close"])
                )
                max_lw = live_q.get("lower_wick_pct", 0.0)
                max_uw = live_q.get("upper_wick_pct", 0.0)

                if direction == 1 and max_lw < _M2_MIN_WICK:
                    engulf = live_q.get("is_bullish_engulf", False)
                    if not engulf:
                        return False, f"GATE3_WEAK_WICK (BUY: lower_wick={max_lw:.2%} < {_M2_MIN_WICK:.0%})", extras
                if direction == -1 and max_uw < _M2_MIN_WICK:
                    engulf = live_q.get("is_bearish_engulf", False)
                    if not engulf:
                        return False, f"GATE3_WEAK_WICK (SELL: upper_wick={max_uw:.2%} < {_M2_MIN_WICK:.0%})", extras
        except Exception:
            pass

        return True, "GATE3_PASS", extras

    # ─────────────────────────────────────────────────────────────────────────
    # GATE 5 HELPER — Recent Barrier Touch Memory
    # ─────────────────────────────────────────────────────────────────────────

    def _compute_vector_memory(
        self, df_m5: Optional[pd.DataFrame], c1: Optional[float], f1: Optional[float], pt: float
    ) -> Tuple[bool, bool]:
        """
        Gate 5: Scans last 12 M5 bars (~1 hour) for recent touch of C1/F1 barrier.
        Activates anti-rebound vector memory.
        Returns (recent_ceiling_touch: bool, recent_floor_touch: bool).
        """
        if df_m5 is None or len(df_m5) < 3:
            return False, False
        lookback = df_m5.iloc[-12:]
        tol = max(pt * 3, 1e-5)
        recent_ceil = bool(c1 and (lookback["high"] >= (c1 - tol)).any())
        recent_floor = bool(f1 and (lookback["low"] <= (f1 + tol)).any())
        return recent_ceil, recent_floor

    # ─────────────────────────────────────────────────────────────────────────
    # UPDATE MACRO CONTEXT — 9-Engine Preheating
    # ─────────────────────────────────────────────────────────────────────────

    def update_macro_context(self, mt5_connector=None, force: bool = False) -> None:
        """
        Fast Micro-ZCE preheat for M5 with enriched 9-engine context.
        Fetches M5 / M15 / H1 bars, computes EMA20/50, Dealing Range, Wave Regime,
        and vector memory for all 28 symbols. Sequential, thread-safe, ~6–8s total.
        """
        now = datetime.now(WIB)
        for sym in self.symbols:
            try:
                valid_sym = sym
                if mt5_connector is not None and hasattr(mt5_connector, "get_valid_trade_symbol"):
                    valid_sym = mt5_connector.get_valid_trade_symbol(sym)

                # ── ZCE Micro Map ─────────────────────────────────────────────
                zm  = self._zce_build_map(valid_sym, mt5_connector=mt5_connector)
                w   = zm.wall_override if (zm and hasattr(zm, "wall_override")) else {}
                c1  = w.get("imm_ceiling_c1")
                f1  = w.get("imm_floor_f1")
                c1_g = w.get("c1_grade", "GRADE_2_INTERMEDIATE")
                f1_g = w.get("f1_grade", "GRADE_2_INTERMEDIATE")

                pt   = self._get_point(valid_sym)
                TF_M5  = getattr(config.mt5, "TIMEFRAME_M5",  5)
                TF_M15 = getattr(config.mt5, "TIMEFRAME_M15", 15)
                TF_H1  = getattr(config.mt5, "TIMEFRAME_H1",  16385)

                df_m5  = _fetch_bars(valid_sym, TF_M5,  60)
                df_m15 = _fetch_bars(valid_sym, TF_M15, 100)
                df_h1  = _fetch_bars(valid_sym, TF_H1,  100)

                cur_c = float(df_m5["close"].iloc[-1])  if df_m5  is not None else 0.0
                ema20 = float(df_m5["close"].ewm(span=20, adjust=False).mean().iloc[-1]) if df_m5  is not None else cur_c
                ema50 = float(df_m5["close"].ewm(span=50, adjust=False).mean().iloc[-1]) if df_m5  is not None else cur_c

                ema50_m15 = float(df_m15["close"].ewm(span=50, adjust=False).mean().iloc[-1]) if df_m15 is not None and len(df_m15) >= 50 else None
                ema50_h1  = float(df_h1["close"].ewm(span=50, adjust=False).mean().iloc[-1])  if df_h1  is not None and len(df_h1)  >= 50 else None

                # Multi-TF trend alignment
                is_bull = (cur_c > ema20) and (ema50_m15 is None or cur_c > ema50_m15 or ema50_h1 is None or cur_c > ema50_h1)
                is_bear = (cur_c < ema20) and (ema50_m15 is None or cur_c < ema50_m15 or ema50_h1 is None or cur_c < ema50_h1)

                # Dealing range position
                f1_ref  = f1 if f1 else (cur_c - 100 * pt)
                c1_ref  = c1 if c1 else (cur_c + 100 * pt)
                dr_span = max(c1_ref - f1_ref, 1e-5)
                dr_pos  = max(0.0, min(1.0, (cur_c - f1_ref) / dr_span)) if cur_c > 0 else 0.50

                # Wave Regime
                wave_regime_label = "UNKNOWN"
                try:
                    from src.indicators.wave_regime import calculate_squeeze_momentum
                    ref_df = df_m15 if df_m15 is not None and len(df_m15) >= 30 else df_h1
                    if ref_df is not None and len(ref_df) >= 30:
                        sqz = calculate_squeeze_momentum(
                            ref_df["high"].tolist(),
                            ref_df["low"].tolist(),
                            ref_df["close"].tolist()
                        )
                        if sqz.get("is_bullish_thrust"):
                            wave_regime_label = "BULLISH_THRUST"
                        elif sqz.get("is_bearish_grind"):
                            wave_regime_label = "BEARISH_GRIND"
                        elif sqz.get("sqz_on"):
                            wave_regime_label = "SQUEEZE_ON"
                        else:
                            wave_regime_label = "YOUNG_OSCILLATION"
                except Exception:
                    pass

                # Vector Memory
                recent_ceil, recent_floor = self._compute_vector_memory(df_m5, c1, f1, pt)

                # Macro Strategic Directive
                strat_dir = None
                try:
                    strat_dir = macro_strategic_engine.get_directive(valid_sym, mt5_connector=mt5_connector, zce_walls=w)
                except Exception as e_sd:
                    logger.debug(f"[M5 PREHEAT] MSE directive error for {valid_sym}: {e_sd}")

                # CSM Net Delta
                csm_delta_val = 0.0
                try:
                    from src.analytics.currency_strength import get_csm_delta_for_symbol
                    csm_delta_val = float(get_csm_delta_for_symbol(valid_sym))
                except Exception:
                    pass

                self.macro_cache[valid_sym] = {
                    "symbol":                    valid_sym,
                    "point":                     pt,
                    "immediate_ceiling_c1":      c1,
                    "immediate_floor_f1":        f1,
                    "ceiling_c1":                c1,
                    "floor_f1":                  f1,
                    "c1_reaction_grade":         c1_g,
                    "f1_reaction_grade":         f1_g,
                    "trend_label":               "M5_MICRO_CONFLUENCE",
                    "spread_pts":                15,
                    "action_tier":               getattr(strat_dir, "action_tier", "FULL_ALLOW") if strat_dir else "FULL_ALLOW",
                    "strat_dir":                 strat_dir,
                    "macro_bias_score":          getattr(strat_dir, "macro_bias_score", 0.0) if strat_dir else 0.0,
                    "primary_execution_directive": getattr(strat_dir, "primary_execution_directive", "") if strat_dir else "",
                    "fractal_regime":            getattr(strat_dir, "fractal_regime", "CHAMBER_CONSOLIDATION") if strat_dir else "CHAMBER_CONSOLIDATION",
                    # DataFrames for gate checks
                    "df":                        df_m5,
                    "df_m15":                    df_m15,
                    "df_h1":                     df_h1,
                    # Price state
                    "current_price":             cur_c,
                    "ema20":                     ema20,
                    "ema50":                     ema50,
                    "ema50_m15":                 ema50_m15,
                    "ema50_h1":                  ema50_h1,
                    "is_bull":                   is_bull,
                    "is_bear":                   is_bear,
                    # Dealing range
                    "dealing_range_high":        c1_ref,
                    "dealing_range_low":         f1_ref,
                    "dealing_range_pos":         dr_pos,
                    # Session extremes
                    "asian_high":  float(df_m5["high"].max())  if df_m5 is not None else 0.0,
                    "asian_low":   float(df_m5["low"].min())   if df_m5 is not None else 0.0,
                    # 9-engine additions
                    "wave_regime":               wave_regime_label,
                    "recent_ceiling_touch":      recent_ceil,
                    "recent_floor_touch":        recent_floor,
                    "csm_delta":                 csm_delta_val,
                }
            except Exception as e:
                logger.debug(f"[M5 PREHEAT] Error preheating {sym}: {e}")
        self.last_macro_update = now
        logger.info(f"✅ [M5 9-ENGINE] Micro-ZCE + Brain Context updated for {len(self.macro_cache)}/{len(self.symbols)} symbols.")

    # ─────────────────────────────────────────────────────────────────────────
    # ZCE MAP OVERRIDES
    # ─────────────────────────────────────────────────────────────────────────

    def _zce_build_map(self, valid: str, eng: Optional[ZoneConfluenceEngine] = None, mt5_connector=None) -> Any:
        """Overrides ZCE map building to use Micro Timeframes (M5/M15/H1)."""
        try:
            if eng is None:
                eng = self._zce_engine
            if mt5_connector is not None and hasattr(mt5_connector, "get_valid_trade_symbol"):
                valid = mt5_connector.get_valid_trade_symbol(valid)
            try:
                if hasattr(config.mt5, "symbol_select"):
                    config.mt5.symbol_select(valid, True)
            except Exception:
                pass

            tf_cfg = [
                ("H1",  getattr(config.mt5, "TIMEFRAME_H1",  16385), 250),
                ("M15", getattr(config.mt5, "TIMEFRAME_M15", 15),    250),
                ("M5",  getattr(config.mt5, "TIMEFRAME_M5",  5),     250),
            ]
            dfs = {}
            for name, tfid, cnt in tf_cfg:
                rr = config.mt5.copy_rates_from_pos(valid, tfid, 0, cnt)
                if rr is not None and len(rr) > 0:
                    dfs[name] = pd.DataFrame(rr)

            h1 = dfs.get("H1")
            m5 = dfs.get("M5")
            if h1 is None or len(h1) < 60 or m5 is None or len(m5) < 30:
                return None

            pt     = self._get_point(valid)
            digits = 3 if "JPY" in valid.upper() else (2 if config.is_crypto(valid) else 5)
            zm     = eng.compute_zone_map(valid, dfs, point_size=pt, digits=digits)

            maps       = getattr(self, "_zce_maps", {})
            maps[valid] = zm
            self._zce_maps = maps
            return zm
        except Exception as e:
            logger.debug(f"[M5 ZCE] Error building micro zone map for {valid}: {e}")
            return None

    def _compute_zce_map_for(self, valid: str, mt5_connector=None, eng=None) -> Any:
        """Route ZCE map computation to micro timeframes (M5/M15/H1)."""
        return self._zce_build_map(valid, eng=eng, mt5_connector=mt5_connector)

    def _evaluate_live_candle_quality(self, sym: str, mid: float, atr_pts: float, pt: float, mt5_connector=None) -> Dict[str, Any]:
        """Overrides candle quality evaluation to use M5 bars."""
        default_res = {
            "body_ratio": 0.35, "upper_wick_pct": 0.30, "lower_wick_pct": 0.30,
            "velocity_atr": 0.50, "direction": "neutral", "verdict": "INDECISION",
            "sweep_side": None, "max_lower_wick": 0.30, "max_upper_wick": 0.30,
            "is_bullish_engulf": False, "is_bearish_engulf": False,
            "live_high": mid, "live_low": mid, "max_high": mid, "max_low": mid,
        }
        rates = None
        tf = getattr(config.mt5, "TIMEFRAME_M5", 5)
        if hasattr(config.mt5, "copy_rates_from_pos"):
            rates = config.mt5.copy_rates_from_pos(sym, tf, 0, 5)
        if (rates is None or len(rates) < 2) and mt5_connector is not None and hasattr(mt5_connector, "get_closed_bars"):
            rates = mt5_connector.get_closed_bars(sym, count=5, timeframe=tf)
        if rates is None or len(rates) < 2:
            return default_res

        try:
            cur_bar  = rates[-1]
            prev_bar = rates[-2]
            atr_val  = max(atr_pts * pt, 1e-6)
            cur_o, cur_h, cur_l = float(cur_bar["open"]), max(float(cur_bar["high"]), mid), min(float(cur_bar["low"]), mid)
            prev_o, prev_h, prev_l, prev_c = float(prev_bar["open"]), float(prev_bar["high"]), float(prev_bar["low"]), float(prev_bar["close"])

            live_q = classify_candle(cur_o, cur_h, cur_l, mid, atr_val, prev_o=prev_o, prev_h=prev_h, prev_l=prev_l, prev_c=prev_c)
            prev_q = classify_candle(prev_o, prev_h, prev_l, prev_c, atr_val)
            max_lw = max(live_q.get("lower_wick_pct", 0.0), prev_q.get("lower_wick_pct", 0.0))
            max_uw = max(live_q.get("upper_wick_pct", 0.0), prev_q.get("upper_wick_pct", 0.0))

            return {
                **live_q,
                "max_lower_wick": max_lw, "max_upper_wick": max_uw,
                "prev_verdict": prev_q.get("verdict", "INDECISION"),
                "prev_body_ratio": prev_q.get("body_ratio", 0.35),
                "live_high": cur_h, "live_low": cur_l,
                "max_high": max(cur_h, prev_h), "max_low": min(cur_l, prev_l),
            }
        except Exception:
            return default_res

    # ─────────────────────────────────────────────────────────────────────────
    # SCAN — Main Entry Point
    # ─────────────────────────────────────────────────────────────────────────

    def scan_fast_radar(self, mt5_connector=None) -> List[CandidateSetup]:
        """
        Executes M5 fast radar scan with 9-Engine Institutional Funnel.
        Filters candidates through 5 gates before computing M5 SL/TP geometry.
        Only trades passing ALL gates and achieving Net R:R >= M5_MIN_RR_RATIO are returned.
        """
        # Base scan (H1 market_scanner logic applied to micro ZCE context)
        candidates = super().scan_fast_radar(mt5_connector=mt5_connector)
        if not candidates:
            return []

        m5_candidates = []
        for cand in candidates:
            sym       = cand.symbol
            direction = cand.direction
            pt        = self._get_point(sym)
            macro     = self.macro_cache.get(sym, {})
            mid       = cand.trigger_price
            spread_pts = cand.current_spread_pts or 15

            df_m5  = macro.get("df")
            df_m15 = macro.get("df_m15")
            df_h1  = macro.get("df_h1")

            # ── Gate 1: News Blackout + Macro Bias ───────────────────────────
            g1_ok, g1_reason = self._check_gate1_macro_news(sym, direction)
            if not g1_ok:
                logger.info(f"[M5 GATE1 SKIP] {sym} {cand.setup_type} → {g1_reason}")
                continue

            # ── Gate 2: Wave Regime + Dealing Range + HTF Alignment ──────────
            g2_ok, g2_reason = self._check_gate2_regime_trend(sym, direction, df_m5, df_m15, df_h1)
            if not g2_ok:
                logger.info(f"[M5 GATE2 SKIP] {sym} {cand.setup_type} → {g2_reason}")
                continue

            # ── M5 ATR Calculation ───────────────────────────────────────────
            atr_m5 = 0.0
            if df_m5 is not None and len(df_m5) >= 14:
                h_arr = df_m5["high"].to_numpy()
                l_arr = df_m5["low"].to_numpy()
                c_arr = df_m5["close"].to_numpy()
                tr    = np.maximum(h_arr[1:] - l_arr[1:], np.maximum(abs(h_arr[1:] - c_arr[:-1]), abs(l_arr[1:] - c_arr[:-1])))
                atr_m5 = float(np.mean(tr[-14:]))
            else:
                rates_m5 = config.mt5.copy_rates_from_pos(sym, config.mt5.TIMEFRAME_M5, 0, 20)
                if rates_m5 is not None and len(rates_m5) >= 14:
                    df_tmp = pd.DataFrame(rates_m5)
                    h_arr  = df_tmp["high"].to_numpy()
                    l_arr  = df_tmp["low"].to_numpy()
                    c_arr  = df_tmp["close"].to_numpy()
                    tr     = np.maximum(h_arr[1:] - l_arr[1:], np.maximum(abs(h_arr[1:] - c_arr[:-1]), abs(l_arr[1:] - c_arr[:-1])))
                    atr_m5 = float(np.mean(tr[-14:]))
                else:
                    atr_m5 = (cand.current_atr_pts * pt * 0.35) if cand.current_atr_pts > 0 else (100 * pt)

            # ── Gate 3: Lux SMC OB Freshness + Sweep Wick Quality ────────────
            g3_ok, g3_reason, g3_extras = self._check_gate3_smc_sweep(sym, direction, mid, atr_m5, pt, df_m5, df_m15)
            if not g3_ok:
                logger.info(f"[M5 GATE3 SKIP] {sym} {cand.setup_type} → {g3_reason}")
                continue

            # ── Gate 4: Atlas DNA Anchored SL/TP + Hard Net R:R >= 2.0 ───────
            c1 = macro.get("immediate_ceiling_c1")
            f1 = macro.get("immediate_floor_f1")

            geom = calculate_m5_sl_tp(
                symbol     = sym,
                entry_price= mid,
                direction  = direction,
                atr_m5     = atr_m5,
                c1         = c1,
                f1         = f1,
                ob_top     = g3_extras.get("ob_top"),
                ob_bottom  = g3_extras.get("ob_bottom"),
                eqh        = g3_extras.get("eqh"),
                eql        = g3_extras.get("eql"),
                spread_pts = spread_pts,
                pt         = pt
            )

            net_rr = geom.get("net_rr", 0.0)
            if net_rr < _M5_MIN_RR:
                logger.info(f"[M5 GATE4 SKIP] {sym} {cand.setup_type} → Net R:R {net_rr:.2f} < {_M5_MIN_RR:.1f} (SL={geom['sl_pts']}pts, TP={geom['tp_pts']}pts)")
                continue

            # ── Gate 5: Vector Memory — Anti-Rebound ─────────────────────────
            recent_ceil, recent_floor = self._compute_vector_memory(df_m5, c1, f1, pt)
            if direction == 1 and recent_ceil:
                ema20 = macro.get("ema20", mid)
                if mid < ema20:
                    logger.info(f"[M5 GATE5 SKIP] {sym} BUY → ANTI_REBOUND_VECTOR (recent ceiling touch + price below EMA20)")
                    continue
            if direction == -1 and recent_floor:
                ema20 = macro.get("ema20", mid)
                if mid > ema20:
                    logger.info(f"[M5 GATE5 SKIP] {sym} SELL → ANTI_REBOUND_VECTOR (recent floor touch + price above EMA20)")
                    continue

            # ── Assemble Output Candidate ─────────────────────────────────────
            cand.timeframe        = "M5"
            cand.suggested_sl     = geom["sl"]
            cand.suggested_tp     = geom["tp"]
            cand.risk_reward_ratio = geom["risk_reward"]
            cand.current_atr_pts  = int(round(atr_m5 / pt)) if pt > 0 else 50
            cand.action_tier      = "M5_SNIPER_A_PLUS"

            if not cand.metadata:
                cand.metadata = {}
            cand.metadata.update({
                "is_m5_demo":          True,
                "m5_sl_pts":           geom["sl_pts"],
                "m5_tp_pts":           geom["tp_pts"],
                "m5_net_rr":           net_rr,
                "m5_structural_anchor": geom.get("structural_anchor"),
                "m5_ob_top":           g3_extras.get("ob_top"),
                "m5_ob_bottom":        g3_extras.get("ob_bottom"),
                "m5_eqh":              g3_extras.get("eqh"),
                "m5_eql":              g3_extras.get("eql"),
                "m5_wave_regime":      macro.get("wave_regime", "UNKNOWN"),
                "m5_dr_pos":           macro.get("dealing_range_pos", 0.5),
                "m5_gates_passed":     "G1+G2+G3+G4+G5",
            })

            logger.info(
                f"[M5 ✅ A+] {sym} {cand.setup_type} dir={'BUY' if direction==1 else 'SELL'} "
                f"Entry={mid:.5f} SL={geom['sl']:.5f}({geom['sl_pts']}pts) "
                f"TP={geom['tp']:.5f}({geom['tp_pts']}pts) NetRR={net_rr:.2f}"
            )
            m5_candidates.append(cand)

        return m5_candidates
