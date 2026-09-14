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
    spread_pts: int = 15,
    pt: float = 0.00001
) -> Dict[str, Any]:
    """
    Calculates precise M5 scalping Stop Loss and Take Profit anchored to Micro-ZCE Stations:
    - Target hold time: 15 to 45 minutes (Fast In, Fast Out).
    - SL: 1.5x M5 ATR (Standard FX: 8-10 pips, JPY/High-Beta: 12-16 pips).
    - TP: Micro C1 (for BUY) or Micro F1 (for SELL) with front-running cushion,
          or default 1.75R - 2.0R (15-25 pips).
    """
    clean_sym = (symbol or "").replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").upper()
    is_jpy = "JPY" in clean_sym
    is_high_beta = any(k in clean_sym for k in ("GBPAUD", "GBPNZD", "EURNZD", "GBPCHF", "GBPCAD", "AUDNZD"))
    is_gold = "XAU" in clean_sym or "GOLD" in clean_sym
    is_crypto = config.is_crypto(clean_sym)

    # Dynamic minimum SL floors for M5 (scaled down from H1)
    if is_crypto:
        min_sl_pts = 10000 # $100 on BTC
        default_tp_r = 2.0
    elif is_gold:
        min_sl_pts = 200   # $2.00 on Gold
        default_tp_r = 1.8
    elif is_jpy:
        min_sl_pts = 120   # 12 pips on JPY crosses
        default_tp_r = 1.75
    elif is_high_beta:
        min_sl_pts = 140   # 14 pips on volatile crosses
        default_tp_r = 1.75
    else:
        min_sl_pts = 80    # 8 pips on standard FX majors (EURUSD, GBPUSD, AUDUSD, USDCHF, USDCAD)
        default_tp_r = 1.75

    # Absorb broker spread friction (min 2x spread + 10 pts)
    fric_floor_pts = (spread_pts * 2) + 10
    sl_pts = max(int(round((1.50 * atr_m5) / pt)), min_sl_pts, fric_floor_pts)
    sl_dist = sl_pts * pt

    # Front-running pad: exit before touching exact wall
    front_pad = (spread_pts * pt) + (0.10 * atr_m5)

    if direction == 1:  # BUY
        sl = entry_price - sl_dist
        # Micro C1 Target check
        if c1 and c1 > entry_price:
            raw_c1_dist = c1 - entry_price
            if raw_c1_dist >= (1.20 * sl_dist):
                tp = c1 - front_pad
            else:
                tp = entry_price + (default_tp_r * sl_dist)
        else:
            tp = entry_price + (default_tp_r * sl_dist)
    else:  # SELL
        sl = entry_price + sl_dist
        # Micro F1 Target check
        if f1 and f1 < entry_price:
            raw_f1_dist = entry_price - f1
            if raw_f1_dist >= (1.20 * sl_dist):
                tp = f1 + front_pad
            else:
                tp = entry_price - (default_tp_r * sl_dist)
        else:
            tp = entry_price - (default_tp_r * sl_dist)

    tp_pts = int(round(abs(entry_price - tp) / pt))
    realized_rr = round(tp_pts / max(sl_pts, 1), 2)

    return {
        "sl": round(sl, 5 if pt < 0.01 else 2),
        "tp": round(tp, 5 if pt < 0.01 else 2),
        "sl_pts": sl_pts,
        "tp_pts": tp_pts,
        "risk_reward": realized_rr
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
        self._cooldown_file = os.path.join(config.DATA_DIR, "scanner_cooldowns_m5.json")
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
                    "immediate_ceiling_c1": c1,
                    "immediate_floor_f1": f1,
                    "ceiling_c1": c1,
                    "floor_f1": f1,
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

            geom = calculate_m5_sl_tp(
                symbol=sym,
                entry_price=cand.trigger_price,
                direction=cand.direction,
                atr_m5=atr_m5,
                c1=c1,
                f1=f1,
                spread_pts=cand.current_spread_pts,
                pt=pt
            )

            # Override with M5 Geometry
            cand.timeframe = "M5"
            cand.suggested_sl = geom["sl"]
            cand.suggested_tp = geom["tp"]
            cand.risk_reward_ratio = geom["risk_reward"]
            cand.current_atr_pts = int(round(atr_m5 / pt)) if pt > 0 else 50
            cand.action_tier = "M5_DIRECT_DEMO"

            # Set metadata to bypass shadow paper trade
            if not cand.metadata:
                cand.metadata = {}
            cand.metadata["is_m5_demo"] = True
            cand.metadata["m5_sl_pts"] = geom["sl_pts"]
            cand.metadata["m5_tp_pts"] = geom["tp_pts"]

            m5_candidates.append(cand)

        return m5_candidates
