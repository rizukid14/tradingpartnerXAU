"""
Market Scanner M5 Specialization Module (Isolated Demo Architecture)
Runs fast-in fast-out scanning using Micro-ZCE (M5/M15/H1) and M5-scaled SL/TP.
Zero pollution to production core files (main.py, market_scanner.py, atlas_dna.py).
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


def calculate_m5_sl_tp(
    symbol: str,
    entry_price: float,
    direction: int,
    atr_m5: float,
    c1: Optional[float] = None,
    f1: Optional[float] = None,
    c2: Optional[float] = None,
    f2: Optional[float] = None,
    spread_pts: int = 15,
    pt: float = 0.00001
) -> Dict[str, Any]:
    """
    Calculates precise M5 scalping Stop Loss and Take Profit anchored to Micro-ZCE Stations:
    - 3-Tier Clamped SL (Major 5-7.5p, High-Beta 6.5-8.5p, JPY 7-9.5p).
    - TP1 guaranteed >= 1.50x SL with commission padding (0.6 pips).
    - TP2 Runner anchored to C2/F2 (if within 1.35x-1.80x TP1) or 1.50x TP1 pts.
    - Zero Skip Trade: preserves currency basket natural hedging.
    """
    clean_sym = (symbol or "").replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").upper()
    is_jpy = "JPY" in clean_sym
    is_high_beta = any(k in clean_sym for k in ("GBPAUD", "GBPNZD", "EURNZD", "GBPCHF", "GBPCAD", "AUDNZD"))
    is_gold = "XAU" in clean_sym or "GOLD" in clean_sym
    is_crypto = config.is_crypto(clean_sym)

    # Multiplier: 1.10x ATR M5 for tight intraday scalping
    sl_atr_mult = float(os.getenv("M5_SL_ATR_MULT", "1.10"))

    # Dynamic 3-Tier Clamping [min_sl_pts, max_sl_pts, tier_min_tp1_pts, max_tp1_pts]
    if is_crypto:
        min_sl_pts = int(os.getenv("M5_MIN_SL_CRYPTO_PTS", "10000"))
        max_sl_pts = int(os.getenv("M5_MAX_SL_CRYPTO_PTS", "25000"))
        tier_min_tp1 = int(os.getenv("M5_MIN_TP1_CRYPTO_PTS", "15000"))
        max_tp1_pts = int(os.getenv("M5_MAX_TP1_CRYPTO_PTS", "35000"))
    elif is_gold:
        min_sl_pts = int(os.getenv("M5_MIN_SL_GOLD_PTS", "150"))
        max_sl_pts = int(os.getenv("M5_MAX_SL_GOLD_PTS", "350"))
        tier_min_tp1 = int(os.getenv("M5_MIN_TP1_GOLD_PTS", "250"))
        max_tp1_pts = int(os.getenv("M5_MAX_TP1_GOLD_PTS", "400"))
    elif is_jpy:
        # Tier 3: JPY Crosses (10.0 - 12.0 pips SL, min 14.0 pips TP1)
        min_sl_pts = int(round(float(os.getenv("M5_MIN_SL_PIPS_JPY", "10.0")) * 10))
        max_sl_pts = int(round(float(os.getenv("M5_MAX_SL_PIPS_JPY", "12.0")) * 10))
        tier_min_tp1 = int(round(float(os.getenv("M5_MIN_TP1_PIPS_JPY", "14.0")) * 10))
        max_tp1_pts = max(int(round(float(os.getenv("M5_MAX_TP1_PIPS_JPY", "20.0")) * 10)), int(round(2.0 * atr_m5 / pt)) if pt > 0 else 200)
    elif is_high_beta:
        # Tier 2: High-Beta Crosses (12.0 - 14.0 pips SL, min 15.0 pips TP1)
        min_sl_pts = int(round(float(os.getenv("M5_MIN_SL_PIPS_HIGHBETA", "12.0")) * 10))
        max_sl_pts = int(round(float(os.getenv("M5_MAX_SL_PIPS_HIGHBETA", "14.0")) * 10))
        tier_min_tp1 = int(round(float(os.getenv("M5_MIN_TP1_PIPS_HIGHBETA", "15.0")) * 10))
        max_tp1_pts = max(int(round(float(os.getenv("M5_MAX_TP1_PIPS_HIGHBETA", "24.0")) * 10)), int(round(2.0 * atr_m5 / pt)) if pt > 0 else 240)
    else:
        # Tier 1: Major FX Pairs (8.0 - 10.0 pips SL, min 10.0 pips TP1)
        min_sl_pts = int(round(float(os.getenv("M5_MIN_SL_PIPS_MAJOR", "8.0")) * 10))
        max_sl_pts = int(round(float(os.getenv("M5_MAX_SL_PIPS_MAJOR", "10.0")) * 10))
        tier_min_tp1 = int(round(float(os.getenv("M5_MIN_TP1_PIPS_MAJOR", "10.0")) * 10))
        max_tp1_pts = max(int(round(float(os.getenv("M5_MAX_TP1_PIPS_MAJOR", "18.0")) * 10)), int(round(2.0 * atr_m5 / pt)) if pt > 0 else 180)

    # Spread friction floor & commission padding
    fric_floor_pts = (spread_pts * 2) + 10
    comm_pts = int(os.getenv("M5_COMMISSION_PAD_PTS", "6"))
    sl_buffer = (spread_pts * pt) + (comm_pts * pt) + (0.10 * atr_m5)
    default_sl_dist = max(sl_atr_mult * atr_m5, min_sl_pts * pt)

    # Elastic Structural Leeway: allows SL to stretch ~18% behind nearby C1/F1 to prevent front-running wall
    leeway_ratio = float(os.getenv("M5_SL_STRETCH_LEEWAY_RATIO", "1.18"))
    stretch_cap_pts = int(round(max_sl_pts * leeway_ratio))

    # 1. Stop Loss Calculation (Anchored to Micro-ZCE Invalidation with Elastic Leeway)
    if direction == 1:  # BUY: Invalidation below Micro Floor F1
        if f1 and f1 < entry_price:
            raw_sl_dist = (entry_price - f1) + sl_buffer
        elif f2 and f2 < entry_price:
            raw_sl_dist = (entry_price - f2) + sl_buffer
        else:
            raw_sl_dist = default_sl_dist

        raw_sl_pts = int(round(raw_sl_dist / pt)) if pt > 0 else 80
        effective_max = stretch_cap_pts if raw_sl_pts <= stretch_cap_pts else max_sl_pts
        sl_pts = max(min(raw_sl_pts, effective_max), min_sl_pts, fric_floor_pts)
        sl_dist = sl_pts * pt
        sl = entry_price - sl_dist

    else:  # SELL: Invalidation above Micro Ceiling C1
        if c1 and c1 > entry_price:
            raw_sl_dist = (c1 - entry_price) + sl_buffer
        elif c2 and c2 > entry_price:
            raw_sl_dist = (c2 - entry_price) + sl_buffer
        else:
            raw_sl_dist = default_sl_dist

        raw_sl_pts = int(round(raw_sl_dist / pt)) if pt > 0 else 80
        effective_max = stretch_cap_pts if raw_sl_pts <= stretch_cap_pts else max_sl_pts
        sl_pts = max(min(raw_sl_pts, effective_max), min_sl_pts, fric_floor_pts)
        sl_dist = sl_pts * pt
        sl = entry_price + sl_dist

    # Front-running pad for Take Profit (exit before hitting exact wall)
    front_pad = (spread_pts * pt) + (comm_pts * pt) + (0.05 * atr_m5)

    # TP1 Calculation: minimum 1.25x SL distance or tier floor; capped dynamically by max_tp1_dist
    min_tp1_dist = max(sl_dist * 1.25, tier_min_tp1 * pt)
    default_tp1_dist = max(sl_dist * 1.50, tier_min_tp1 * pt)
    max_tp1_dist = max(max_tp1_pts * pt, min_tp1_dist * 1.15)

    if direction == 1:  # BUY
        if c1 and c1 > entry_price:
            c1_net_tp = c1 - front_pad
            raw_c1_dist = c1_net_tp - entry_price
            if raw_c1_dist >= min_tp1_dist:
                # Micro-ZCE C1 is Single Source of Truth, capped at max_tp1_dist
                tp1 = min(c1_net_tp, entry_price + max_tp1_dist)
            else:
                tp1 = entry_price + default_tp1_dist
        else:
            tp1 = entry_price + default_tp1_dist
    else:  # SELL
        if f1 and f1 < entry_price:
            f1_net_tp = f1 + front_pad
            raw_f1_dist = entry_price - f1_net_tp
            if raw_f1_dist >= min_tp1_dist:
                # Micro-ZCE F1 is Single Source of Truth, capped at max_tp1_dist
                tp1 = max(f1_net_tp, entry_price - max_tp1_dist)
            else:
                tp1 = entry_price - default_tp1_dist
        else:
            tp1 = entry_price - default_tp1_dist

    # Enforce hard quant floor and ceiling for TP1
    if direction == 1:
        if (tp1 - entry_price) < min_tp1_dist:
            tp1 = entry_price + min_tp1_dist
        elif (tp1 - entry_price) > max_tp1_dist:
            tp1 = entry_price + max_tp1_dist
    else:
        if (entry_price - tp1) < min_tp1_dist:
            tp1 = entry_price - min_tp1_dist
        elif (entry_price - tp1) > max_tp1_dist:
            tp1 = entry_price - max_tp1_dist

    tp1_pts = int(round(abs(entry_price - tp1) / pt)) if pt > 0 else 80

    # TP2 Runner Calculation: anchored to Micro-ZCE C2/F2 (if within reach 1.35x-1.80x TP1) or 1.50x TP1 pts
    runner_ratio = float(os.getenv("M5_RUNNER_TP2_RATIO", "1.50"))
    default_tp2_dist = (tp1_pts * runner_ratio) * pt
    max_tp2_dist = max_tp1_dist * 1.55

    if direction == 1:  # BUY
        if c2 and c2 > entry_price:
            c2_net_tp = c2 - front_pad
            c2_dist = c2_net_tp - entry_price
            if (1.35 * (tp1 - entry_price)) <= c2_dist <= (1.80 * (tp1 - entry_price)):
                tp2 = min(c2_net_tp, entry_price + max_tp2_dist)
            else:
                tp2 = entry_price + default_tp2_dist
        else:
            tp2 = entry_price + default_tp2_dist
    else:  # SELL
        if f2 and f2 < entry_price:
            f2_net_tp = f2 + front_pad
            f2_dist = entry_price - f2_net_tp
            if (1.35 * (entry_price - tp1)) <= f2_dist <= (1.80 * (entry_price - tp1)):
                tp2 = max(f2_net_tp, entry_price - max_tp2_dist)
            else:
                tp2 = entry_price - default_tp2_dist
        else:
            tp2 = entry_price - default_tp2_dist

    tp2_pts = int(round(abs(entry_price - tp2) / pt)) if pt > 0 else int(round(tp1_pts * 1.5))
    min_tp2_pts = int(round(tp1_pts * 1.30))
    if tp2_pts < min_tp2_pts:
        tp2_pts = int(round(tp1_pts * 1.50))
        tp2 = entry_price + (tp2_pts * pt) if direction == 1 else entry_price - (tp2_pts * pt)

    digits = 5 if pt < 0.01 else (3 if is_jpy else 2)
    return {
        "sl": round(sl, digits),
        "tp": round(tp1, digits),
        "tp_runner": round(tp2, digits),
        "sl_pts": sl_pts,
        "tp_pts": tp1_pts,
        "tp1_pts": tp1_pts,
        "tp2_pts": tp2_pts,
        "risk_reward": round(tp1_pts / max(sl_pts, 1), 2),
        "risk_reward_runner": round(tp2_pts / max(sl_pts, 1), 2)
    }


class MarketScannerM5(MarketScanner):
    """
    Dedicated Market Scanner for M5 Fast Execution Radar:
    - Uses Micro-ZCE (M5, M15, H1) with tight clustering horizons (10-25 pip stations).
    - Scaled M5 SL/TP (8-16 pip SL, 15-28 pip TP).
    - Unconstrained execution: all candidates bypass shadow paper trade and route to MT5 Demo.
    """

    def __init__(self, symbols: Optional[List[str]] = None):
        super().__init__(symbols=symbols)
        _prefix = "_demo" if getattr(config, "MT5_ACCOUNT_MODE", "live").lower() == "demo" else ""
        self._cooldown_file = os.path.join(config.DATA_DIR, f"scanner_cooldowns_m5{_prefix}.json")
        self._symbol_last_trigger = self._load_cooldowns()
        self._micro_zce_params = {
            "grid": {
                "M5": [30, 60, 120],
                "M15": [30, 60, 120],
                "H1": [50, 100, 200]
            },
            "w_tf": {"M5": 1.0, "M15": 1.25, "H1": 1.50},
            "merge_atr_mult": 0.20,
            "max_imm_atr": 3.0,
            "grade_g2": 4.0,
            "grade_g3": 7.0,
        }
        self._zce_engine = ZoneConfluenceEngine(params=self._micro_zce_params)
        logger.info("[M5 SCANNER] MarketScannerM5 initialized with Micro-ZCE (M5/M15/H1).")

    def update_macro_context(self, mt5_connector=None, force: bool = False) -> None:
        """
        Fast dedicated Micro-ZCE preheat for M5 Demo Lab.
        Sequential, thread-safe, 0-token, ~6 seconds for all 28 symbols.
        Enriches macro_cache with Micro-ZCE (M5/M15/H1), authentic MacroStrategicDirective,
        M5 bars DataFrame, EMA20/50, and dynamic M5 dealing range coordinates.
        """
        now = datetime.now(WIB)
        for sym in self.symbols:
            try:
                valid_sym = sym
                if mt5_connector is not None and hasattr(mt5_connector, "get_valid_trade_symbol"):
                    valid_sym = mt5_connector.get_valid_trade_symbol(sym)
                zm = self._zce_build_map(valid_sym, mt5_connector=mt5_connector)
                w = zm.wall_override if (zm and hasattr(zm, "wall_override")) else {}
                c1 = w.get("imm_ceiling_c1")
                f1 = w.get("imm_floor_f1")
                c2 = w.get("deep_ceiling_c2")
                f2 = w.get("deep_floor_f2")
                c1_g = w.get("c1_grade", "GRADE_2_INTERMEDIATE")
                f1_g = w.get("f1_grade", "GRADE_2_INTERMEDIATE")

                pt = self._get_point(valid_sym)

                # Fetch M5 rates for dynamic indicators & dealing range
                rates_m5 = None
                if hasattr(config.mt5, "copy_rates_from_pos"):
                    rates_m5 = config.mt5.copy_rates_from_pos(valid_sym, config.mt5.TIMEFRAME_M5, 0, 60)

                df_m5 = pd.DataFrame(rates_m5) if (rates_m5 is not None and len(rates_m5) > 0) else None
                cur_c = float(df_m5["close"].iloc[-1]) if df_m5 is not None else 0.0
                ema20 = float(df_m5["close"].ewm(span=20, adjust=False).mean().iloc[-1]) if df_m5 is not None else cur_c
                ema50 = float(df_m5["close"].ewm(span=50, adjust=False).mean().iloc[-1]) if df_m5 is not None else cur_c

                # Calculate authentic M5 ATR (14 period)
                atr_m5 = 50.0 * pt
                if df_m5 is not None and len(df_m5) >= 14:
                    h_arr = df_m5['high'].to_numpy()
                    l_arr = df_m5['low'].to_numpy()
                    c_arr = df_m5['close'].to_numpy()
                    tr = np.maximum(h_arr[1:] - l_arr[1:], np.maximum(abs(h_arr[1:] - c_arr[:-1]), abs(l_arr[1:] - c_arr[:-1])))
                    atr_m5 = float(np.mean(tr[-14:]))
                atr_pts = int(round(atr_m5 / pt)) if pt > 0 else 50

                # Dealing range bounds anchored to Micro-ZCE stations
                f1_ref = f1 if f1 else (cur_c - (100 * pt))
                c1_ref = c1 if c1 else (cur_c + (100 * pt))
                dr_span = max(c1_ref - f1_ref, 1e-5)
                dr_pos = max(0.0, min(1.0, (cur_c - f1_ref) / dr_span)) if cur_c > 0 else 0.50

                # Authentic Macro Strategic Directive (Pure Quant native sockets, ~0.02s)
                strat_dir = None
                try:
                    strat_dir = macro_strategic_engine.get_directive(valid_sym, mt5_connector=mt5_connector, zce_walls=w)
                except Exception as e_sd:
                    logger.debug(f"[M5 PREHEAT] MSE directive error for {valid_sym}: {e_sd}")

                self.macro_cache[valid_sym] = {
                    "symbol": valid_sym,
                    "point": pt,
                    "current_atr": atr_m5,
                    "atr_pts": atr_pts,
                    "immediate_ceiling_c1": c1,
                    "immediate_floor_f1": f1,
                    "ceiling_c1": c1,
                    "floor_f1": f1,
                    "deep_ceiling_c2": c2,
                    "deep_floor_f2": f2,
                    "c1_reaction_grade": c1_g,
                    "f1_reaction_grade": f1_g,
                    "trend_label": "M5_MICRO_CONFLUENCE",
                    "spread_pts": 15,
                    "action_tier": getattr(strat_dir, "action_tier", "FULL_ALLOW") if strat_dir else "FULL_ALLOW",
                    "strat_dir": strat_dir,
                    "macro_bias_score": getattr(strat_dir, "macro_bias_score", 0.0) if strat_dir else 0.0,
                    "primary_execution_directive": getattr(strat_dir, "primary_execution_directive", "") if strat_dir else "",
                    "fractal_regime": getattr(strat_dir, "fractal_regime", "CHAMBER_CONSOLIDATION") if strat_dir else "CHAMBER_CONSOLIDATION",
                    "df": df_m5,
                    "current_price": cur_c,
                    "ema20": ema20,
                    "ema50": ema50,
                    "dealing_range_high": c1_ref,
                    "dealing_range_low": f1_ref,
                    "dealing_range_pos": dr_pos,
                    "is_bull": cur_c > ema20,
                    "is_bear": cur_c < ema20,
                    "asian_high": float(df_m5["high"].max()) if df_m5 is not None else 0.0,
                    "asian_low": float(df_m5["low"].min()) if df_m5 is not None else 0.0,
                    "recent_ceiling_touch": False,
                    "recent_floor_touch": False,
                }
            except Exception as e:
                logger.debug(f"[M5 PREHEAT] Error preheating {sym}: {e}")
        self.last_macro_update = now
        logger.info(f"✅ Micro-ZCE Context updated for {len(self.macro_cache)}/{len(self.symbols)} symbols.")

    def _zce_build_map(self, valid: str, eng: Optional[ZoneConfluenceEngine] = None, mt5_connector=None) -> Any:
        """
        Overrides ZCE map building to use Micro Timeframes (M5, M15, H1)
        instead of slow macro sockets (MN1, W1, D1, H4).
        """
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

            # Micro-Timeframe Configuration for ZCE
            tf_cfg = [
                ("H1", getattr(config.mt5, "TIMEFRAME_H1", 16385), 250),
                ("M15", getattr(config.mt5, "TIMEFRAME_M15", 16386), 250),
                ("M5", getattr(config.mt5, "TIMEFRAME_M5", 5), 250)
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

            pt = self._get_point(valid)
            digits = 3 if "JPY" in valid.upper() else (2 if config.is_crypto(valid) else 5)

            # Compute micro zone map
            zm = eng.compute_zone_map(valid, dfs, point_size=pt, digits=digits)
            maps = getattr(self, "_zce_maps", {})
            maps[valid] = zm
            self._zce_maps = maps
            return zm
        except Exception as e:
            logger.debug(f"[M5 ZCE] Error building micro zone map for {valid}: {e}")
            return None

    def _compute_zce_map_for(self, valid: str, mt5_connector=None, eng=None) -> Any:
        """Route ZCE map computation directly to micro timeframes (M5/M15/H1)."""
        return self._zce_build_map(valid, eng=eng, mt5_connector=mt5_connector)

    def _evaluate_live_candle_quality(self, sym: str, mid: float, atr_pts: float, pt: float, mt5_connector=None) -> Dict[str, Any]:
        """
        Overrides candle quality evaluation to use M5 candles for M5 fast execution.
        """
        default_res = {
            "body_ratio": 0.35,
            "upper_wick_pct": 0.30,
            "lower_wick_pct": 0.30,
            "velocity_atr": 0.50,
            "direction": "neutral",
            "verdict": "INDECISION",
            "sweep_side": None,
            "max_lower_wick": 0.30,
            "max_upper_wick": 0.30,
            "is_bullish_engulf": False,
            "is_bearish_engulf": False,
            "live_high": mid,
            "live_low": mid,
            "max_high": mid,
            "max_low": mid,
        }

        rates = None
        tf = getattr(config.mt5, 'TIMEFRAME_M5', 5)
        if hasattr(config.mt5, 'copy_rates_from_pos'):
            rates = config.mt5.copy_rates_from_pos(sym, tf, 0, 5)
        if (rates is None or len(rates) < 2) and mt5_connector is not None and hasattr(mt5_connector, 'get_closed_bars'):
            rates = mt5_connector.get_closed_bars(sym, count=5, timeframe=tf)

        if rates is None or len(rates) < 2:
            return default_res

        try:
            cur_bar = rates[-1]
            prev_bar = rates[-2]
            atr_val = max(atr_pts * pt, 1e-6)

            cur_o = float(cur_bar['open'])
            cur_h = max(float(cur_bar['high']), mid)
            cur_l = min(float(cur_bar['low']), mid)
            cur_c = mid

            prev_o = float(prev_bar['open'])
            prev_h = float(prev_bar['high'])
            prev_l = float(prev_bar['low'])
            prev_c = float(prev_bar['close'])

            live_qual = classify_candle(
                cur_o, cur_h, cur_l, cur_c, atr_val,
                prev_o=prev_o, prev_h=prev_h, prev_l=prev_l, prev_c=prev_c
            )
            prev_qual = classify_candle(
                prev_o, prev_h, prev_l, prev_c, atr_val
            )

            max_lw = max(live_qual.get('lower_wick_pct', 0.0), prev_qual.get('lower_wick_pct', 0.0))
            max_uw = max(live_qual.get('upper_wick_pct', 0.0), prev_qual.get('upper_wick_pct', 0.0))
            max_h = max(cur_h, prev_h)
            max_l = min(cur_l, prev_l)

            return {
                "body_ratio": live_qual.get('body_ratio', 0.35),
                "upper_wick_pct": live_qual.get('upper_wick_pct', 0.30),
                "lower_wick_pct": live_qual.get('lower_wick_pct', 0.30),
                "velocity_atr": live_qual.get('velocity_atr', 0.50),
                "direction": live_qual.get('direction', 'neutral'),
                "verdict": live_qual.get('verdict', 'INDECISION'),
                "sweep_side": live_qual.get('sweep_side'),
                "max_lower_wick": max_lw,
                "max_upper_wick": max_uw,
                "is_bullish_engulf": live_qual.get('is_bullish_engulf', False),
                "is_bearish_engulf": live_qual.get('is_bearish_engulf', False),
                "prev_verdict": prev_qual.get('verdict', 'INDECISION'),
                "prev_body_ratio": prev_qual.get('body_ratio', 0.35),
                "live_high": cur_h,
                "live_low": cur_l,
                "max_high": max_h,
                "max_low": max_l
            }
        except Exception:
            return default_res

    def scan_fast_radar(self, mt5_connector=None) -> List[CandidateSetup]:
        """
        Executes fast M5 radar scan. Bypasses macro day/session freeze filters and routes
        all qualifying candidates with calibrated M5 SL/TP directly to MT5 execution.
        """
        # Call base scan_fast_radar
        candidates = super().scan_fast_radar(mt5_connector=mt5_connector)

        if not candidates:
            return []

        # Post-process candidates with M5 Geometry
        m5_candidates = []
        for cand in candidates:
            sym = cand.symbol
            pt = self._get_point(sym)
            macro = self.macro_cache.get(sym, {})

            # Calculate M5 ATR from live rates
            rates_m5 = config.mt5.copy_rates_from_pos(sym, config.mt5.TIMEFRAME_M5, 0, 20)
            if rates_m5 is not None and len(rates_m5) >= 14:
                df_m5 = pd.DataFrame(rates_m5)
                h_arr = df_m5['high'].to_numpy()
                l_arr = df_m5['low'].to_numpy()
                c_arr = df_m5['close'].to_numpy()
                tr = np.maximum(h_arr[1:] - l_arr[1:], np.maximum(abs(h_arr[1:] - c_arr[:-1]), abs(l_arr[1:] - c_arr[:-1])))
                atr_m5 = float(np.mean(tr[-14:]))
            else:
                atr_m5 = (cand.current_atr_pts * pt * 0.35) if cand.current_atr_pts > 0 else (100 * pt)

            c1 = macro.get('immediate_ceiling_c1')
            f1 = macro.get('immediate_floor_f1')
            c2 = macro.get('deep_ceiling_c2')
            f2 = macro.get('deep_floor_f2')

            geom = calculate_m5_sl_tp(
                symbol=sym,
                entry_price=cand.trigger_price,
                direction=cand.direction,
                atr_m5=atr_m5,
                c1=c1,
                f1=f1,
                c2=c2,
                f2=f2,
                spread_pts=cand.current_spread_pts,
                pt=pt
            )

            # Override with M5 Geometry
            cand.timeframe = "M5"
            cand.suggested_sl = geom["sl"]
            cand.suggested_tp = geom["tp"]
            cand.suggested_tp_runner = geom["tp_runner"]
            cand.risk_reward_ratio = geom["risk_reward"]
            cand.current_atr_pts = int(round(atr_m5 / pt)) if pt > 0 else 50
            cand.action_tier = "M5_DIRECT_DEMO"

            # Set metadata to bypass shadow paper trade
            if not cand.metadata:
                cand.metadata = {}
            cand.metadata["is_m5_demo"] = True
            cand.metadata["m5_sl_pts"] = geom["sl_pts"]
            cand.metadata["m5_tp_pts"] = geom["tp_pts"]
            cand.metadata["m5_tp1_pts"] = geom["tp1_pts"]
            cand.metadata["m5_tp2_pts"] = geom["tp2_pts"]

            m5_candidates.append(cand)

        return m5_candidates
