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
from src.analytics.pattern_engine import MacroEnvelopeEngine
from src.indicators.candle_quality import classify_candle
from src.indicators.atlas_dna import calculate_dual_grid_stations

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
    Calculates precise M5 scalping Stop Loss and Take Profit (Pure Demo Model):
    - Fast In, Fast Out intraday scalping.
    - SL: 1.25x M5 ATR (bounded by tier min/max floors & spread friction). Pure ATR based, no backward search.
    - TP: Micro C1 (for BUY) or Micro F1 (for SELL) with front-running pad if within reach (>= 1.25x SL and <= max_tp_dist * 1.15).
          Otherwise, fast fallback TP: entry + min(1.75 * sl_dist, max_tp_dist).
    - Single ticket execution (no artificial limit re-anchoring, no runner split).
    """
    clean_sym = (symbol or "").replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").upper()
    is_jpy = "JPY" in clean_sym
    is_pacific_jpy = clean_sym in ("NZDJPY", "AUDJPY")
    is_high_beta = any(k in clean_sym for k in ("GBPAUD", "GBPNZD", "EURNZD", "GBPCHF", "GBPCAD"))
    is_gold = "XAU" in clean_sym or "GOLD" in clean_sym
    is_crypto = config.is_crypto(clean_sym)
    is_low_beta = any(k in clean_sym for k in ["NZDCHF", "NZDCAD", "AUDCHF", "CADCHF", "EURCHF", "EURGBP", "AUDCAD", "AUDNZD", "NZDUSD"])
    atr_pts = int(round(atr_m5 / pt)) if pt > 0 else 50

    # Multipliers and ratios from environment (with safe Demo fallbacks)
    sl_atr_mult = float(os.getenv("M5_SL_ATR_MULT", "1.25"))
    default_tp_r = float(os.getenv("M5_DEFAULT_TP_RR", "1.75"))

    # Spread friction floor & commission padding
    fric_floor_pts = (spread_pts * 2) + 10
    comm_pts = int(os.getenv("M5_COMMISSION_PAD_PTS", "6"))
    digits = 5 if pt < 0.01 else (3 if is_jpy else 2)

    # Dynamic 5-Tier Clamping [min_sl_pts, max_sl_pts, max_tp_pts]
    if is_crypto:
        min_sl_pts = int(os.getenv("M5_MIN_SL_CRYPTO_PTS", "10000"))
        max_sl_pts = int(os.getenv("M5_MAX_SL_CRYPTO_PTS", "25000"))
        max_tp_pts = int(os.getenv("M5_MAX_TP_CRYPTO_PTS", "30000"))
    elif is_gold:
        min_sl_pts = int(os.getenv("M5_MIN_SL_GOLD_PTS", "150"))
        max_sl_pts = int(os.getenv("M5_MAX_SL_GOLD_PTS", "350"))
        max_tp_pts = int(os.getenv("M5_MAX_TP_GOLD_PTS", "400"))
    elif is_pacific_jpy:
        # Pacific JPY Crosses (NZDJPY, AUDJPY) - scaled to lower Pacific ATR
        min_sl_pts = int(round(float(os.getenv("M5_MIN_SL_PIPS_PACIFIC_JPY", "4.5")) * 10))
        max_sl_pts = int(round(float(os.getenv("M5_MAX_SL_PIPS_PACIFIC_JPY", "7.5")) * 10))
        max_tp_pts = int(round(float(os.getenv("M5_MAX_TP1_PIPS_PACIFIC_JPY", "13.0")) * 10))
    elif is_jpy:
        # Standard JPY Crosses (USDJPY, EURJPY, GBPJPY...)
        min_sl_pts = int(round(float(os.getenv("M5_MIN_SL_PIPS_JPY", "6.0")) * 10))
        max_sl_pts = int(round(float(os.getenv("M5_MAX_SL_PIPS_JPY", "12.0")) * 10))
        max_tp_pts = int(round(float(os.getenv("M5_MAX_TP_PIPS_JPY", "13.5")) * 10))
    elif is_high_beta:
        # High-Beta Crosses (GBPAUD, GBPNZD, EURNZD, GBPCHF, GBPCAD)
        min_sl_pts = int(round(float(os.getenv("M5_MIN_SL_PIPS_HIGHBETA", "7.0")) * 10))
        max_sl_pts = int(round(float(os.getenv("M5_MAX_SL_PIPS_HIGHBETA", "14.0")) * 10))
        max_tp_pts = int(round(float(os.getenv("M5_MAX_TP_PIPS_HIGHBETA", "16.0")) * 10))
    elif is_low_beta or (atr_pts < 25):
        # Low-Beta / Pacific Crosses (NZDCHF, NZDCAD, NZDUSD, AUDNZD, AUDCAD, EURGBP...)
        min_sl_pts = max(int(round(float(os.getenv("M5_MIN_SL_PIPS_LOWBETA", "3.0")) * 10)), fric_floor_pts)
        max_sl_pts = max(int(round(float(os.getenv("M5_MAX_SL_PIPS_LOWBETA", "5.5")) * 10)), min_sl_pts + 10)
        max_tp_pts = int(round(float(os.getenv("M5_MAX_TP_PIPS_LOWBETA", "8.5")) * 10))
    else:
        # Major FX Pairs (EURUSD, GBPUSD, AUDUSD, USDCAD, USDCHF)
        min_sl_pts = int(round(float(os.getenv("M5_MIN_SL_PIPS_MAJOR", "4.0")) * 10))
        max_sl_pts = int(round(float(os.getenv("M5_MAX_SL_PIPS_MAJOR", "7.5")) * 10))
        max_tp_pts = int(round(float(os.getenv("M5_MAX_TP_PIPS_MAJOR", "9.5")) * 10))

    # 1. Stop Loss: 1.25x ATR M5 directly from entry (Pure Demo Formula)
    raw_sl_pts = int(round((sl_atr_mult * atr_m5) / pt)) if pt > 0 else 50
    sl_pts = max(min(raw_sl_pts, max_sl_pts), min_sl_pts, fric_floor_pts)
    sl_dist = sl_pts * pt

    if direction == 1:
        sl = entry_price - sl_dist
    else:
        sl = entry_price + sl_dist

    # 2. Take Profit: Target opposite ZCE wall if within reach (>= 1.25x SL and <= max_tp_dist * 1.15)
    # Otherwise fallback to fast scalping target: entry ± min(default_tp_r * sl_dist, max_tp_dist)
    max_tp_dist = max_tp_pts * pt
    front_pad = (spread_pts * pt) + (comm_pts * pt) + (0.10 * atr_m5)

    if direction == 1:  # BUY
        if c1 and c1 > entry_price:
            raw_c1_dist = c1 - entry_price
            if raw_c1_dist >= (1.25 * sl_dist) and raw_c1_dist <= (max_tp_dist * 1.15):
                tp = min(c1 - front_pad, entry_price + max_tp_dist)
            else:
                tp = entry_price + min(default_tp_r * sl_dist, max_tp_dist)
        else:
            tp = entry_price + min(default_tp_r * sl_dist, max_tp_dist)
    else:  # SELL
        if f1 and f1 < entry_price:
            raw_f1_dist = entry_price - f1
            if raw_f1_dist >= (1.25 * sl_dist) and raw_f1_dist <= (max_tp_dist * 1.15):
                tp = max(f1 + front_pad, entry_price - max_tp_dist)
            else:
                tp = entry_price - min(default_tp_r * sl_dist, max_tp_dist)
        else:
            tp = entry_price - min(default_tp_r * sl_dist, max_tp_dist)

    tp_pts = int(round(abs(entry_price - tp) / pt)) if pt > 0 else 80
    realized_rr = round(tp_pts / max(sl_pts, 1), 2)

    return {
        "sl": round(sl, digits),
        "tp": round(tp, digits),
        "tp_runner": round(tp, digits),
        "sl_pts": sl_pts,
        "tp_pts": tp_pts,
        "tp1_pts": tp_pts,
        "tp2_pts": tp_pts,
        "risk_reward": realized_rr,
        "risk_reward_runner": realized_rr,
        "has_runner": False,
        "is_reanchored_limit": False,
        "limit_entry_price": entry_price
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
                "M30": [30, 60, 120],
                "H1": [50, 100, 250, 500]
            },
            "w_tf": {"M5": 1.0, "M15": 1.20, "M30": 1.35, "H1": 1.60},
            "merge_atr_mult": 0.20,
            "max_imm_atr": 3.0,
            "grade_g2": 4.0,
            "grade_g3": 7.0,
        }
        self._zce_engine = ZoneConfluenceEngine(params=self._micro_zce_params)
        logger.info("[M5 SCANNER] MarketScannerM5 initialized with Micro-ZCE 4-TF (M5/M15/M30/H1).")

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

                # Fetch M5 rates for dynamic indicators & authentic M5 dealing range
                rates_m5 = None
                if hasattr(config.mt5, "copy_rates_from_pos"):
                    rates_m5 = config.mt5.copy_rates_from_pos(valid_sym, config.mt5.TIMEFRAME_M5, 0, 100)

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

                # ZCE Fortress Chamber bounds
                f1_ref = f1 if f1 else (cur_c - (100 * pt))
                c1_ref = c1 if c1 else (cur_c + (100 * pt))
                chamber_span = max(c1_ref - f1_ref, 1e-5)
                chamber_pos = max(0.0, min(1.0, (cur_c - f1_ref) / chamber_span)) if cur_c > 0 else 0.50

                # Authentic M5 SMC Dealing Range via MacroEnvelopeEngine
                pip_val = pt * 10 if pt < 0.01 else pt
                m5_dr = {}
                dr_hi = c1_ref
                dr_lo = f1_ref
                dr_pos = chamber_pos
                dr_zone = "EQUILIBRIUM"
                if df_m5 is not None and len(df_m5) >= 25:
                    try:
                        m5_env = MacroEnvelopeEngine(window_bars=100).analyze(df_m5, symbol=valid_sym, point_size=pt, pip_size=pip_val)
                        if m5_env and hasattr(m5_env, "visual_payload"):
                            m5_dr = m5_env.visual_payload.get("dealing_range", {})
                            if m5_dr:
                                dr_hi = float(m5_dr.get("range_high") or dr_hi)
                                dr_lo = float(m5_dr.get("range_low") or dr_lo)
                                dr_pos = float(m5_dr.get("dr_position_pct", 50.0)) / 100.0
                                dr_zone = str(m5_dr.get("zone_status", "EQUILIBRIUM"))
                    except Exception as e_m5_dr:
                        logger.debug(f"[M5 DR] Error computing M5 dealing range for {valid_sym}: {e_m5_dr}")

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
                    "dealing_range_high": dr_hi,
                    "dealing_range_low": dr_lo,
                    "dealing_range_pos": dr_pos,
                    "dealing_range_zone": dr_zone,
                    "dealing_range": m5_dr,
                    "chamber_pos": chamber_pos,
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

            # Micro-Timeframe Configuration for ZCE (4-TF Native Sockets)
            tf_cfg = [
                ("H1", getattr(config.mt5, "TIMEFRAME_H1", 16385), 720),
                ("M30", getattr(config.mt5, "TIMEFRAME_M30", 30), 300),
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

            # Conditional ATH / ATL Station Fallback
            # If historical swing data in lookback horizon has no ceiling (e.g. 4-year ATH in AUDNZD)
            # or no floor (ATL), synthesise authentic mathematical stations from ATLAS DNA & ATR.
            if zm is not None:
                cur_p = float(zm.cur_price) if getattr(zm, "cur_price", None) else (float(dfs["M5"]["close"].iloc[-1]) if "M5" in dfs and not dfs["M5"].empty else 0.0)
                st = calculate_dual_grid_stations(valid, cur_p)
                w = getattr(zm, "wall_override", {}) or {}

                if zm.immediate_ceiling_c1 is None:
                    sub_c = st.get("sub_ceiling_50")
                    macro_c = st.get("macro_ceiling")
                    fb_c1 = sub_c if (sub_c and sub_c > cur_p) else macro_c
                    if fb_c1 is None or fb_c1 <= cur_p:
                        fb_c1 = round(cur_p + max(2.5 * zm.atr_h1, 0.0050 if "JPY" not in valid else 0.50), digits)
                    zm.immediate_ceiling_c1 = fb_c1
                    zm.immediate_ceiling_c1_grade = "GRADE_1_PROJECTION [ATLAS_STN]"
                    w["imm_ceiling_c1"] = fb_c1
                    w["c1_grade"] = "GRADE_1_PROJECTION [ATLAS_STN]"
                    w["imm_ceiling_c1_grade"] = "GRADE_1_PROJECTION [ATLAS_STN]"
                    if zm.deep_ceiling_c2 is None:
                        zm.deep_ceiling_c2 = round(fb_c1 + max(1.5 * zm.atr_h1, st.get("micro_step_50", 0.0025)), digits)
                        w["deep_ceiling_c2"] = zm.deep_ceiling_c2
                        w["deep_ceiling_c2_grade"] = "GRADE_1_PROJECTION [ATLAS_STN]"

                if zm.immediate_floor_f1 is None:
                    sub_f = st.get("sub_floor_50")
                    macro_f = st.get("macro_floor")
                    fb_f1 = sub_f if (sub_f and sub_f < cur_p) else macro_f
                    if fb_f1 is None or fb_f1 >= cur_p:
                        fb_f1 = round(cur_p - max(2.5 * zm.atr_h1, 0.0050 if "JPY" not in valid else 0.50), digits)
                    zm.immediate_floor_f1 = fb_f1
                    zm.immediate_floor_f1_grade = "GRADE_1_PROJECTION [ATLAS_STN]"
                    w["imm_floor_f1"] = fb_f1
                    w["f1_grade"] = "GRADE_1_PROJECTION [ATLAS_STN]"
                    w["imm_floor_f1_grade"] = "GRADE_1_PROJECTION [ATLAS_STN]"
                    if zm.deep_floor_f2 is None:
                        zm.deep_floor_f2 = round(fb_f1 - max(1.5 * zm.atr_h1, st.get("micro_step_50", 0.0025)), digits)
                        w["deep_floor_f2"] = zm.deep_floor_f2
                        w["deep_floor_f2_grade"] = "GRADE_1_PROJECTION [ATLAS_STN]"

                zm.wall_override = w

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
        # Dynamically synchronize live tick price into M5 dealing range position for real-time gating
        for sym in self.symbols:
            macro = self.macro_cache.get(sym)
            if not macro:
                continue
            dr_hi = float(macro.get("dealing_range_high", 0.0) or 0.0)
            dr_lo = float(macro.get("dealing_range_low", 0.0) or 0.0)
            if dr_hi > dr_lo:
                tick = config.mt5.symbol_info_tick(sym) if hasattr(config.mt5, "symbol_info_tick") else None
                if tick and (tick.ask > 0 or tick.bid > 0):
                    live_mid = (tick.ask + tick.bid) / 2.0 if (tick.ask > 0 and tick.bid > 0) else (tick.ask or tick.bid)
                    dr_pos_live = max(0.0, min(1.0, (live_mid - dr_lo) / (dr_hi - dr_lo)))
                    macro["dealing_range_pos"] = dr_pos_live
                    macro["dr_pos"] = dr_pos_live

        # Call base scan_fast_radar
        candidates = super().scan_fast_radar(mt5_connector=mt5_connector)

        if not candidates:
            return []

        # Post-process candidates with M5 Geometry
        m5_candidates = []
        twin_enabled = getattr(config, "M5_TWIN_TICKET_ENABLED", False)
        for cand in candidates:
            sym = cand.symbol
            pt = self._get_point(sym)
            macro = self.macro_cache.get(sym, {})

            # Ensure candidate dealing range position reflects live tick price
            if "dealing_range_pos" in macro:
                cand.dealing_range_pos = macro["dealing_range_pos"]

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

            # Dynamic Limit Re-Anchoring: If cramped against ceiling/floor, re-anchor trigger to discount/premium limit
            if geom.get("is_reanchored_limit"):
                cand.trigger_price = geom["limit_entry_price"]
                cand.order_type = "BUY_LIMIT" if cand.direction == 1 else "SELL_LIMIT"

            # Set metadata to bypass shadow paper trade & guide single ticket execution
            if not cand.metadata:
                cand.metadata = {}
            cand.metadata["is_m5_demo"] = True
            cand.metadata["has_runner"] = False if not twin_enabled else geom.get("has_runner", False)
            cand.metadata["is_reanchored_limit"] = geom.get("is_reanchored_limit", False)
            cand.metadata["m5_sl_pts"] = geom["sl_pts"]
            cand.metadata["m5_tp_pts"] = geom["tp_pts"]
            cand.metadata["m5_tp1_pts"] = geom["tp1_pts"]
            cand.metadata["m5_tp2_pts"] = geom["tp2_pts"]
            cand.metadata["entry_price"] = cand.trigger_price
            cand.metadata["entry_type"] = getattr(cand, "order_type", "market")

            m5_candidates.append(cand)

        return m5_candidates
