"""
Pure Quant Hierarchical Top-Down Macro Strategic Engine (src/analytics/macro_strategic_engine.py)
--------------------------------------------------------------------------------------------------
Implements a 100% dynamic, multi-scale institutional market analysis engine:
1. Native socket fetch of 6 MT5 fractal timeframes (MN1 50 bars, W1 100 bars, D1 350 bars, H4 400 bars, H1 250 bars, M30 200 bars).
2. Dual-Grid Psychological Stations (Macro 100-pip vs Micro 50-pip Sub-Stations for JPY & FX).
3. Structural Zonal Bands (Proximal Edge, Distal Edge, Equilibrium) for SBR, RBS, Drop-Base-Drop, and Rally-Base-Rally.
4. Station Collision & Dual-Reaction Protocols (Skenario A Reversal Fade vs Skenario B Breakout Upgrade).
5. Wyckoff AMD & Stop-Hunt Dip discount entry calculations with tight Intraday SL anchoring.

Performance: 0 API Tokens, <50 ms computation time per symbol.
"""

import os
import sys
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any, Tuple

import numpy as np  # type: ignore
import pandas as pd  # type: ignore

import config
from src.indicators.atlas_dna import get_symbol_step, calculate_dynamic_stations

# ── 3-PROFILE PAIR DNA (Based on 4.3-Year Multi-TF Empirical Research) ──
CLEAN_RESPECT_PAIRS = {"EURGBP", "AUDCHF", "NZDCHF", "EURCHF", "AUDUSD"}
SWEEP_SPECIALIST_PAIRS = {"USDCAD", "EURUSD", "GBPUSD", "USDJPY", "NZDCAD", "CADJPY", "GBPCHF", "GBPCAD", "EURCAD"}
MOMENTUM_RUNNER_PAIRS = {"GBPNZD", "GBPJPY", "EURNZD", "XAUUSD", "BTCUSD"}
from src.indicators.lux_smc import LuxSMCAnalyzer

logger = logging.getLogger("macro_strategic_engine")
WIB = ZoneInfo("Asia/Jakarta")


@dataclass
class StructuralZone:
    zone_type: str        # 'RBS', 'SBR', 'ORDER_BLOCK', 'DROP_BASE_DROP', 'RALLY_BASE_RALLY'
    proximal: float       # Entry edge (closest to price)
    distal: float         # Invalidation edge (farthest from price)
    midpoint: float       # 50% Equilibrium
    timeframe: str        # 'D1', 'H4', 'H1'
    touches: int = 1


@dataclass
class MacroStrategicDirective:
    symbol: str
    calculation_time_ms: float
    daily_macro_bias: str                 # "BULLISH_EXPANSION" | "BEARISH_PULLBACK" | "BULLISH_PULLBACK" | "RANGE_BOUND"
    primary_execution_directive: str      # "HUNT_SELL_PULLBACK" | "HUNT_BUY_AT_RBS" | "HUNT_BUY_CONTINUATION" | "FADE_CORRIDOR_EXTREMES"
    target_station_price: float
    ceiling_frontier_price: float
    floor_rbs_support_price: float
    invalidation_stop_price: float
    entry_limit_anchor: float
    intraday_sl_price: float
    intraday_sl_pips: float
    tp1_price: float
    tp1_pips: float
    tp2_price: float
    tp2_pips: float
    risk_reward_ratio: float
    max_allowed_buy_price: float
    min_allowed_sell_price: float
    forbidden_traps: List[str]
    confidence_score: int
    structural_stage: str
    daily_mandate_thesis: str
    future_macro_roadmap: str
    macro_rbs_w1: Optional[float] = None
    macro_sbr_w1: Optional[float] = None
    macro_rbs_d1: float = 0.0
    macro_sbr_d1: float = 0.0
    inter_rbs_h4: float = 0.0
    inter_sbr_h4: float = 0.0
    micro_rbs_h1: float = 0.0
    micro_sbr_h1: float = 0.0
    d1_annual_high: float = 0.0
    d1_annual_low: float = 0.0
    sub_floor_50: float = 0.0
    sub_ceiling_50: float = 0.0
    market_state: str = "NEUTRAL_CHAMBER"
    immediate_ceiling_c1: float = 0.0
    immediate_floor_f1: float = 0.0
    deep_target_floor_f2: float = 0.0
    deep_target_ceiling_c2: float = 0.0
    c1_density_score: float = 0.0
    f1_density_score: float = 0.0
    c1_fortress_tag: str = ""
    f1_fortress_tag: str = ""
    chamber_position_pct: float = 0.50
    retest_touch_count: int = 1
    interaction_sequence: List[str] = field(default_factory=list)
    bullish_contingency_path: str = ""
    bearish_contingency_path: str = ""
    atr_d1_pips: float = 0.0
    atr_h1_pips: float = 0.0
    atr_m30_pips: float = 0.0
    current_spread_pts: int = 0
    entry_zone_proximal: float = 0.0
    total_bars_computed: int = 0
    w1_key_demand: float = 0.0
    w1_key_supply: float = 0.0
    macro_bias_score: float = 0.0
    regime_stability: str = "STABLE"
    hard_circuit_breaker: bool = False
    action_tier: str = "WATCH_ONLY"
    contingency_target: float = 0.0
    fundamental_backing: str = ""
    fundamental_grade: str = "GRADE_A"
    current_bid: float = 0.0
    current_ask: float = 0.0
    current_mid: float = 0.0
    raw_payload: Dict[str, Any] = field(default_factory=dict)


class MacroStrategicEngine:
    """
    Pure Quant Hierarchical State Engine:
    Computes top-down macro directives and structural zones across 6 native MT5 timeframes.
    """

    @staticmethod
    def _cluster_merge(
        elements: List[Tuple[float, float, str]],
        cluster_tol: float,
        digits: int,
        is_ascending: bool = True
    ) -> List[Tuple[float, float, str]]:
        """
        Groups nearby barrier elements within cluster_tol into weighted composite clusters.
        Returns: List of (composite_price, total_score, composite_tags_str)
        """
        if not elements:
            return []
        sorted_elems = sorted(elements, key=lambda x: x[0], reverse=not is_ascending)
        clusters: List[Dict[str, Any]] = []

        for p, sc, tag in sorted_elems:
            merged = False
            for cl in clusters:
                if abs(cl['rep_price'] - p) <= cluster_tol:
                    cl['prices'].append((p, sc))
                    cl['total_score'] += sc
                    cl['tags'].append(tag)
                    total_w = sum(w for _, w in cl['prices'])
                    cl['rep_price'] = sum(pr * w for pr, w in cl['prices']) / max(total_w, 1e-6)
                    merged = True
                    break
            if not merged:
                clusters.append({
                    'rep_price': p,
                    'total_score': sc,
                    'prices': [(p, sc)],
                    'tags': [tag]
                })

        res = []
        for cl in clusters:
            comp_price = round(cl['rep_price'], digits)
            score = round(cl['total_score'], 1)
            unique_tags = sorted(list(set(cl['tags'])))
            tag_str = "+".join(unique_tags)
            res.append((comp_price, score, tag_str))

        res.sort(key=lambda x: x[0], reverse=not is_ascending)
        return res

    @staticmethod
    def _get_fortress_tag(score: float) -> str:
        if score >= 8.0: return "SUPER_FORTRESS"
        if score >= 5.0: return "FORTRESS"
        if score >= 3.0: return "MODERATE"
        return "MINOR"

    def __init__(self, cache_ttl_sec: float = 60.0):
        self._cache: Dict[str, MacroStrategicDirective] = {}
        self._cache_ts: Dict[str, float] = {}
        self._cache_ttl_sec: float = cache_ttl_sec
        self._last_update_ts: float = 0.0

    @staticmethod
    def _to_df(rates) -> pd.DataFrame:
        if rates is None or len(rates) == 0:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df.set_index('time', inplace=True)
        return df

    @staticmethod
    def _calc_atr(df: pd.DataFrame, span: int = 14) -> float:
        if df.empty or len(df) < 5:
            return 0.0050
        tr = pd.concat([
            (df['high'] - df['low']),
            (df['high'] - df['close'].shift(1)).abs(),
            (df['low'] - df['close'].shift(1)).abs()
        ], axis=1).max(axis=1)
        return float(tr.ewm(span=span).mean().iloc[-1])

    @staticmethod
    def _find_swings(df: pd.DataFrame, n_lookback: int = 60, window: int = 2) -> Tuple[List[Tuple[Any, float]], List[Tuple[Any, float]]]:
        if df.empty or len(df) < (window * 2 + 1):
            return [], []
        tail = df.tail(n_lookback)
        swings_h = []
        swings_l = []
        for i in range(window, len(tail) - window):
            if tail['high'].iloc[i] == tail['high'].iloc[i - window:i + window + 1].max():
                swings_h.append((tail.index[i], float(tail['high'].iloc[i])))
            if tail['low'].iloc[i] == tail['low'].iloc[i - window:i + window + 1].min():
                swings_l.append((tail.index[i], float(tail['low'].iloc[i])))
        return swings_h, swings_l

    @staticmethod
    def _detect_drop_base_drop(df_h1: pd.DataFrame, digits: int) -> Tuple[Optional[float], Optional[float]]:
        if df_h1.empty or len(df_h1) < 5:
            return None, None
        for i in range(len(df_h1) - 4, len(df_h1) - 1):
            c1, c2, c3 = df_h1.iloc[i - 1], df_h1.iloc[i], df_h1.iloc[i + 1]
            is_c1_drop = (c1['open'] - c1['close']) >= (0.45 * max(c1['high'] - c1['low'], 1e-5))
            is_c2_base = abs(c2['open'] - c2['close']) <= (0.40 * max(c2['high'] - c2['low'], 1e-5))
            is_c3_drop = (c3['open'] - c3['close']) >= (0.50 * max(c3['high'] - c3['low'], 1e-5))
            if is_c1_drop and is_c2_base and is_c3_drop:
                return round(float(c2['low']), digits), round(float(c2['high']), digits)
        return None, None

    @staticmethod
    def _detect_rally_base_rally(df_h1: pd.DataFrame, digits: int) -> Tuple[Optional[float], Optional[float]]:
        if df_h1.empty or len(df_h1) < 5:
            return None, None
        for i in range(len(df_h1) - 4, len(df_h1) - 1):
            c1, c2, c3 = df_h1.iloc[i - 1], df_h1.iloc[i], df_h1.iloc[i + 1]
            is_c1_rally = (c1['close'] - c1['open']) >= (0.45 * max(c1['high'] - c1['low'], 1e-5))
            is_c2_base = abs(c2['open'] - c2['close']) <= (0.40 * max(c2['high'] - c2['low'], 1e-5))
            is_c3_rally = (c3['close'] - c3['open']) >= (0.50 * max(c3['high'] - c3['low'], 1e-5))
            if is_c1_rally and is_c2_base and is_c3_rally:
                return round(float(c2['high']), digits), round(float(c2['low']), digits)
        return None, None

    def compute_directive(self, symbol: str, mt5_connector=None) -> MacroStrategicDirective:
        """
        Calculates the complete Pure Quant Top-Down Strategic Directive for a symbol.
        """
        t0 = time.perf_counter()
        from config import mt5

        clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").upper()
        
        info = mt5.symbol_info(symbol)
        if info is None:
            alt = clean_sym
            info = mt5.symbol_info(alt)
            if info: symbol = alt
            
        pt = info.point if info and info.point else (0.001 if "JPY" in symbol else (0.01 if "XAU" in symbol or "BTC" in symbol else 0.00001))
        digits = info.digits if info and info.digits else (3 if "JPY" in symbol else (2 if "XAU" in symbol or "BTC" in symbol else 5))
        pip_div = (10 if digits in (3, 5) else 1)

        # Get Live Tick
        tick = mt5.symbol_info_tick(symbol)
        curr_bid = float(tick.bid) if tick and tick.bid else 0.0
        curr_ask = float(tick.ask) if tick and tick.ask else 0.0
        curr_mid = (curr_bid + curr_ask) / 2.0 if (curr_bid > 0 and curr_ask > 0) else curr_bid
        spread_pts = int(round(abs(curr_ask - curr_bid) / pt)) if (curr_ask > 0 and curr_bid > 0 and pt > 0) else 10

        # 1. Fetch 6 Timeframes Native from MT5
        rates_mn1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_MN1, 0, 50)
        rates_w1  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_W1, 0, 100)
        rates_d1  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_D1, 0, 350)
        rates_h4  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H4, 0, 400)
        rates_h1  = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 250)
        rates_m30 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 200)

        df_mn1 = self._to_df(rates_mn1)
        df_w1  = self._to_df(rates_w1)
        df_d1  = self._to_df(rates_d1)
        df_h4  = self._to_df(rates_h4)
        df_h1  = self._to_df(rates_h1)
        df_m30 = self._to_df(rates_m30)

        if curr_mid <= 0 and not df_d1.empty:
            curr_mid = float(df_d1['close'].iloc[-1])

        # 2. Multi-Timeframe ATR Calculations
        atr_d1 = self._calc_atr(df_d1)
        atr_h4 = self._calc_atr(df_h4)
        atr_h1 = self._calc_atr(df_h1)
        atr_m30 = self._calc_atr(df_m30)

        # 3. Macro Horizon Extremes
        mn1_low = float(df_mn1['low'].min()) if not df_mn1.empty else curr_mid * 0.8
        mn1_high = float(df_mn1['high'].max()) if not df_mn1.empty else curr_mid * 1.2
        mn1_low_date = df_mn1['low'].idxmin().strftime('%b %Y') if not df_mn1.empty else "N/A"
        mn1_high_date = df_mn1['high'].idxmax().strftime('%b %Y') if not df_mn1.empty else "N/A"

        d1_annual_high = float(df_d1['high'].tail(250).max()) if not df_d1.empty else curr_mid * 1.1
        d1_annual_low = float(df_d1['low'].tail(250).min()) if not df_d1.empty else curr_mid * 0.9

        # 4. Dual-Grid Psychological Stations
        psych_step_macro = get_symbol_step(symbol)
        stations = calculate_dynamic_stations(symbol, curr_mid)
        floor_station = float(stations['lower_station'])
        base_station = float(stations['base_station'])
        ceiling_station = float(stations['upper_station'])
        next_macro_target = round(ceiling_station + psych_step_macro, digits)

        psych_step_micro = round(psych_step_macro * 0.50, digits)
        micro_base = round(round(curr_mid / psych_step_micro) * psych_step_micro, digits)
        if curr_mid >= micro_base:
            sub_floor = micro_base
            sub_ceiling = round(micro_base + psych_step_micro, digits)
        else:
            sub_floor = round(micro_base - psych_step_micro, digits)
            sub_ceiling = micro_base

        # 5. Multi-Scale SBR & RBS Calculator (W1, D1, H4, H1)
        w1_sh, w1_sl = self._find_swings(df_w1, min(len(df_w1), 100), 2)
        rbs_w1_cand = [sh[1] for sh in w1_sh if sh[1] < curr_mid - (0.35 * atr_d1)]
        macro_rbs_w1 = round(max(rbs_w1_cand), digits) if rbs_w1_cand else None
        sbr_w1_cand = [sl[1] for sl in w1_sl if sl[1] > curr_mid + (0.35 * atr_d1)]
        macro_sbr_w1 = round(min(sbr_w1_cand), digits) if sbr_w1_cand else None

        d1_sh, d1_sl = self._find_swings(df_d1, min(len(df_d1), 250), 2)
        rbs_d1_cand = [sh[1] for sh in d1_sh if sh[1] < curr_mid - (0.25 * atr_d1)]
        macro_rbs_d1 = round(max(rbs_d1_cand), digits) if rbs_d1_cand else (macro_rbs_w1 or floor_station)
        sbr_d1_cand = [sl[1] for sl in d1_sl if sl[1] > curr_mid + (0.25 * atr_d1)]
        macro_sbr_d1 = round(min(sbr_d1_cand), digits) if sbr_d1_cand else (macro_sbr_w1 or ceiling_station)

        h4_sh, h4_sl = self._find_swings(df_h4, 60, 2)
        rbs_h4_cand = [sh[1] for sh in h4_sh if sh[1] < curr_mid - (0.20 * atr_h4)]
        inter_rbs_h4 = round(max(rbs_h4_cand), digits) if rbs_h4_cand else macro_rbs_d1
        sbr_h4_cand = [sl[1] for sl in h4_sl if sl[1] > curr_mid + (0.20 * atr_h4)]
        inter_sbr_h4 = round(min(sbr_h4_cand), digits) if sbr_h4_cand else macro_sbr_d1

        h1_sh, h1_sl = self._find_swings(df_h1, 48, 2)
        rbs_h1_cand = [sh[1] for sh in h1_sh if sh[1] < curr_mid - (0.15 * atr_h1)]
        micro_rbs_h1 = round(max(rbs_h1_cand), digits) if rbs_h1_cand else inter_rbs_h4
        sbr_h1_cand = [sl[1] for sl in h1_sl if sl[1] > curr_mid + (0.15 * atr_h1)]
        micro_sbr_h1 = round(min(sbr_h1_cand), digits) if sbr_h1_cand else inter_sbr_h4

        # 6. Supply / Demand Detection (DBD & RBR)
        dbd_entry, dbd_roof = self._detect_drop_base_drop(df_h1, digits)
        rbr_entry, rbr_floor = self._detect_rally_base_rally(df_h1, digits)

        # 7. Multi-Month Equal Lows / Equal Highs Sweep Detection
        eqh_d1_cands: List[float] = []
        for i in range(len(d1_sh)):
            for j in range(i + 1, len(d1_sh)):
                t1, h1_lvl = d1_sh[i]
                t2, h2_lvl = d1_sh[j]
                if abs(h1_lvl - h2_lvl) <= (0.20 * atr_d1):
                    eqh_d1_cands.append(round(max(h1_lvl, h2_lvl), digits))

        eql_d1_cands: List[float] = []
        for i in range(len(d1_sl)):
            for j in range(i + 1, len(d1_sl)):
                t1, l1_lvl = d1_sl[i]
                t2, l2_lvl = d1_sl[j]
                if abs(l1_lvl - l2_lvl) <= (0.20 * atr_d1):
                    eql_d1_cands.append(round(min(l1_lvl, l2_lvl), digits))

        eq_low_price = d1_annual_low
        eq_low_date_str = ""
        for i in range(len(d1_sl)):
            for j in range(i + 1, len(d1_sl)):
                t1, l1 = d1_sl[i]
                t2, l2 = d1_sl[j]
                if abs(l1 - l2) <= (0.25 * atr_d1):
                    min_after = df_d1['low'][df_d1.index >= t2].min()
                    if min_after <= min(l1, l2) and curr_mid > max(l1, l2) + (0.50 * atr_d1):
                        eq_low_price = min(l1, l2)
                        eq_low_date_str = t2.strftime("%d %b %Y")
                        break

        # 8. SMC Order Blocks & FRVP Confluence Extraction
        smc_analyzer = LuxSMCAnalyzer(swing_length=5)
        smc_h1 = smc_analyzer.analyze(df_h1, point_size=pt) if not df_h1.empty else None
        smc_h4 = smc_analyzer.analyze(df_h4, point_size=pt) if not df_h4.empty else None
        smc_d1 = smc_analyzer.analyze(df_d1, point_size=pt) if not df_d1.empty else None
        smc_w1 = smc_analyzer.analyze(df_w1, point_size=pt) if not df_w1.empty else None
        
        bull_obs = []
        bear_obs = []
        if smc_h1:
            bull_obs.extend(smc_h1.order_blocks_bullish)
            bear_obs.extend(smc_h1.order_blocks_bearish)
        if smc_h4:
            bull_obs.extend(smc_h4.order_blocks_bullish)
            bear_obs.extend(smc_h4.order_blocks_bearish)
        if smc_d1:
            bull_obs.extend(smc_d1.order_blocks_bullish)
            bear_obs.extend(smc_d1.order_blocks_bearish)
        if smc_w1:
            bull_obs.extend(smc_w1.order_blocks_bullish)
            bear_obs.extend(smc_w1.order_blocks_bearish)

        macro_bull_obs = (smc_d1.order_blocks_bullish if smc_d1 else []) + (smc_w1.order_blocks_bullish if smc_w1 else [])
        macro_bear_obs = (smc_d1.order_blocks_bearish if smc_d1 else []) + (smc_w1.order_blocks_bearish if smc_w1 else [])
        
        def _get_ob_core(ob):
            poc = ob.get('poc', 0.0)
            top = ob.get('top', 0.0)
            bot = ob.get('bottom', 0.0)
            if ob.get('poc_confluence') and bot <= poc <= top:
                return poc
            return (top + bot) / 2.0

        w1_demand_cands = [_get_ob_core(ob) for ob in macro_bull_obs if _get_ob_core(ob) < curr_mid]
        w1_key_demand = round(max(w1_demand_cands), digits) if w1_demand_cands else floor_station
        w1_supply_cands = [_get_ob_core(ob) for ob in macro_bear_obs if _get_ob_core(ob) > curr_mid]
        w1_key_supply = round(min(w1_supply_cands), digits) if w1_supply_cands else ceiling_station

        # 9. Real-Time Price Boundary & Wick Ratios (D1)
        recent_frontier_high = float(df_d1['high'].tail(15).max()) if not df_d1.empty else curr_mid * 1.05
        recent_frontier_low = float(df_d1['low'].tail(15).min()) if not df_d1.empty else curr_mid * 0.95
        zone_boundary_tol = min(0.35 * atr_d1, psych_step_micro * 0.40)
        is_near_ceiling = curr_mid >= (sub_ceiling - zone_boundary_tol)
        is_near_floor = curr_mid <= (sub_floor + zone_boundary_tol)
        
        # Check if price tested ceiling / D1 Bearish OB recently
        recent_tested_ceiling = (recent_frontier_high >= sub_ceiling - zone_boundary_tol) or any(
            recent_frontier_high >= ob.get('bottom', 0.0) - zone_boundary_tol and recent_frontier_high <= ob.get('top', 0.0) + zone_boundary_tol
            for ob in bear_obs
        )
        recent_tested_floor = (recent_frontier_low <= sub_floor + zone_boundary_tol) or any(
            recent_frontier_low <= ob.get('top', 0.0) + zone_boundary_tol and recent_frontier_low >= ob.get('bottom', 0.0) - zone_boundary_tol
            for ob in bull_obs
        )
        
        d1_recent = df_d1.tail(5)
        u_wicks_d1 = []
        l_wicks_d1 = []
        for _, r in d1_recent.iterrows():
            rng = max(r['high'] - r['low'], 1e-5)
            uw = max(0.0, r['high'] - max(r['open'], r['close']))
            lw = max(0.0, min(r['open'], r['close']) - r['low'])
            u_wicks_d1.append(uw / rng)
            l_wicks_d1.append(lw / rng)

        peak_u_wick_pct = int(round(max(u_wicks_d1[-4:]) * 100)) if u_wicks_d1 else 0
        peak_l_wick_pct = int(round(max(l_wicks_d1[-4:]) * 100)) if l_wicks_d1 else 0

        anti_wick_buffer = (0.35 * atr_h1) + (spread_pts * pt)
        pips_rallied = int(round(abs(curr_mid - eq_low_price) / pt / pip_div))

        is_crypto = "BTC" in symbol
        
        # 10. Calibrated Institutional Reload Zone Width (0.55 * ATR H1 with Safety Floors)
        if is_crypto:
            reload_width = max(0.55 * atr_h1, 120.0)
        elif "JPY" in symbol:
            reload_width = max(0.55 * atr_h1, 10 * pt * pip_div)
        elif "XAU" in symbol:
            reload_width = max(0.55 * atr_h1, 1.5)
        else:
            reload_width = max(0.55 * atr_h1, 6 * pt * pip_div)

        # 11. Structural Model: Density-Ranked Barrier Chamber Resolver
        clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
        if clean_sym in SWEEP_SPECIALIST_PAIRS:
            sweep_offset = 8.0 * pt * pip_div
            pair_profile_tag = "SWEEP_SPECIALIST"
        elif clean_sym in CLEAN_RESPECT_PAIRS:
            sweep_offset = 1.5 * pt * pip_div
            pair_profile_tag = "CLEAN_RESPECT"
        else:
            sweep_offset = 4.0 * pt * pip_div
            pair_profile_tag = "STANDARD"

        # ── 1. STRUCTURAL MODEL: DENSITY-RANKED CLUSTER RESOLVER WITH FRVP ──
        # FRVP Calculation (D1 60-bar rolling & H4 100-bar rolling)
        vp_d1, vp_h4 = None, None
        try:
            from src.indicators.volume_profile import compute_fixed_range_volume_profile
            if rates_d1 is not None and len(rates_d1) >= 20:
                s_i = max(0, len(rates_d1) - 60)
                e_i = len(rates_d1) - 1
                vp_d1 = compute_fixed_range_volume_profile(
                    rates_d1['high'], rates_d1['low'], closes=rates_d1['close'], volumes=rates_d1['tick_volume'],
                    start_idx=s_i, end_idx=e_i, num_bins=50
                )
            if rates_h4 is not None and len(rates_h4) >= 20:
                s_i = max(0, len(rates_h4) - 100)
                e_i = len(rates_h4) - 1
                vp_h4 = compute_fixed_range_volume_profile(
                    rates_h4['high'], rates_h4['low'], closes=rates_h4['close'], volumes=rates_h4['tick_volume'],
                    start_idx=s_i, end_idx=e_i, num_bins=50
                )
        except Exception as e:
            logger.debug(f"FRVP calculation bypass for {symbol}: {e}")

        # Candidate Upper Barriers
        raw_up_elements: List[Tuple[float, float, str]] = []
        for p, sc, tag in [
            (sub_ceiling, 1.5, "PSYCH_50"),
            (ceiling_station, 2.5, "PSYCH_100"),
            (next_macro_target, 2.5, "PSYCH_200")
        ]:
            if p > curr_mid:
                raw_up_elements.append((round(p, digits), sc, tag))

        # W1 & Multi-Year Upper Resistance Structures
        if macro_sbr_w1 and macro_sbr_w1 > curr_mid + (0.01 * atr_h1):
            raw_up_elements.append((round(macro_sbr_w1, digits), 5.0, "W1_SBR"))
        if w1_key_supply and w1_key_supply > curr_mid + (0.01 * atr_h1):
            raw_up_elements.append((round(w1_key_supply, digits), 4.0, "W1_SUPPLY"))
        if d1_annual_high and d1_annual_high > curr_mid + (0.01 * atr_h1):
            raw_up_elements.append((round(d1_annual_high, digits), 4.5, "ANNUAL_HIGH"))
        if mn1_high and mn1_high > curr_mid + (0.01 * atr_h1):
            raw_up_elements.append((round(mn1_high, digits), 5.0, "MN1_HIGH"))

        # Multi-Month Equal Highs (EQH) Liquidity Pools
        for eqh_p in eqh_d1_cands:
            if eqh_p > curr_mid + (0.01 * atr_h1):
                raw_up_elements.append((round(eqh_p, digits), 3.5, "D1_EQH_POOL"))

        # SBR Structures with Multi-TF Weighting
        if macro_sbr_d1 and macro_sbr_d1 > curr_mid + (0.01 * atr_h1):
            raw_up_elements.append((round(macro_sbr_d1, digits), 4.5, "D1_SBR"))
        if inter_sbr_h4 and inter_sbr_h4 > curr_mid + (0.01 * atr_h1):
            raw_up_elements.append((round(inter_sbr_h4, digits), 3.5, "H4_SBR"))
        if micro_sbr_h1 and micro_sbr_h1 > curr_mid + (0.01 * atr_h1):
            raw_up_elements.append((round(micro_sbr_h1, digits), 2.0, "H1_SBR"))
        if dbd_entry and dbd_entry > curr_mid + (0.01 * atr_h1):
            raw_up_elements.append((round(dbd_entry, digits), 2.0, "DBD_SUPPLY"))

        # SMC Bearish Order Blocks
        for ob in bear_obs:
            bot = ob.get('bottom', 0.0)
            if bot > curr_mid + (0.01 * atr_h1):
                raw_up_elements.append((round(bot, digits), 2.5, "BEAR_OB"))

        # FRVP Upper Resistance Anchors
        if vp_d1:
            if vp_d1.poc > curr_mid + (0.01 * atr_h1):
                raw_up_elements.append((round(vp_d1.poc, digits), 3.5, "D1_POC"))
            if vp_d1.vah > curr_mid + (0.01 * atr_h1):
                raw_up_elements.append((round(vp_d1.vah, digits), 2.5, "D1_VAH"))
            for hvn in getattr(vp_d1, 'hvn_nodes', []):
                if hvn > curr_mid + (0.01 * atr_h1):
                    raw_up_elements.append((round(hvn, digits), 2.0, "D1_HVN"))
        if vp_h4:
            if vp_h4.poc > curr_mid + (0.01 * atr_h1):
                raw_up_elements.append((round(vp_h4.poc, digits), 3.0, "H4_POC"))
            if vp_h4.vah > curr_mid + (0.01 * atr_h1):
                raw_up_elements.append((round(vp_h4.vah, digits), 2.0, "H4_VAH"))
            for hvn in getattr(vp_h4, 'hvn_nodes', []):
                if hvn > curr_mid + (0.01 * atr_h1):
                    raw_up_elements.append((round(hvn, digits), 1.5, "H4_HVN"))

        # Candidate Lower Barriers
        raw_down_elements: List[Tuple[float, float, str]] = []
        for p, sc, tag in [
            (sub_floor, 1.5, "PSYCH_50"),
            (floor_station, 2.5, "PSYCH_100"),
            (round(floor_station - psych_step_macro, digits), 2.5, "PSYCH_200")
        ]:
            if p < curr_mid:
                raw_down_elements.append((round(p, digits), sc, tag))

        # W1 & Multi-Year Lower Support Structures
        if macro_rbs_w1 and macro_rbs_w1 < curr_mid - (0.01 * atr_h1):
            raw_down_elements.append((round(macro_rbs_w1, digits), 5.0, "W1_RBS"))
        if w1_key_demand and w1_key_demand < curr_mid - (0.01 * atr_h1):
            raw_down_elements.append((round(w1_key_demand, digits), 4.0, "W1_DEMAND"))
        if d1_annual_low and d1_annual_low < curr_mid - (0.01 * atr_h1):
            raw_down_elements.append((round(d1_annual_low, digits), 4.5, "ANNUAL_LOW"))
        if mn1_low and mn1_low < curr_mid - (0.01 * atr_h1):
            raw_down_elements.append((round(mn1_low, digits), 5.0, "MN1_LOW"))

        # Multi-Month Equal Lows (EQL) Liquidity Pools
        for eql_p in eql_d1_cands:
            if eql_p < curr_mid - (0.01 * atr_h1):
                raw_down_elements.append((round(eql_p, digits), 3.5, "D1_EQL_POOL"))

        # RBS Structures with Multi-TF Weighting
        if macro_rbs_d1 and macro_rbs_d1 < curr_mid - (0.01 * atr_h1):
            raw_down_elements.append((round(macro_rbs_d1, digits), 4.5, "D1_RBS"))
        if inter_rbs_h4 and inter_rbs_h4 < curr_mid - (0.01 * atr_h1):
            raw_down_elements.append((round(inter_rbs_h4, digits), 3.5, "H4_RBS"))
        if micro_rbs_h1 and micro_rbs_h1 < curr_mid - (0.01 * atr_h1):
            raw_down_elements.append((round(micro_rbs_h1, digits), 2.0, "H1_RBS"))
        if rbr_entry and rbr_entry < curr_mid - (0.01 * atr_h1):
            raw_down_elements.append((round(rbr_entry, digits), 2.0, "RBR_DEMAND"))

        # SMC Bullish Order Blocks
        for ob in bull_obs:
            top = ob.get('top', 0.0)
            if top < curr_mid - (0.01 * atr_h1):
                raw_down_elements.append((round(top, digits), 2.5, "BULL_OB"))

        # FRVP Lower Support Anchors
        if vp_d1:
            if vp_d1.poc < curr_mid - (0.01 * atr_h1):
                raw_down_elements.append((round(vp_d1.poc, digits), 3.5, "D1_POC"))
            if vp_d1.val < curr_mid - (0.01 * atr_h1):
                raw_down_elements.append((round(vp_d1.val, digits), 2.5, "D1_VAL"))
            for hvn in getattr(vp_d1, 'hvn_nodes', []):
                if hvn < curr_mid - (0.01 * atr_h1):
                    raw_down_elements.append((round(hvn, digits), 2.0, "D1_HVN"))
        if vp_h4:
            if vp_h4.poc < curr_mid - (0.01 * atr_h1):
                raw_down_elements.append((round(vp_h4.poc, digits), 3.0, "H4_POC"))
            if vp_h4.val < curr_mid - (0.01 * atr_h1):
                raw_down_elements.append((round(vp_h4.val, digits), 2.0, "H4_VAL"))
            for hvn in getattr(vp_h4, 'hvn_nodes', []):
                if hvn < curr_mid - (0.01 * atr_h1):
                    raw_down_elements.append((round(hvn, digits), 1.5, "H4_HVN"))

        # Cluster Merging with tolerance = 0.15 * atr_h1
        cl_tol = max(0.15 * atr_h1, 3 * pt * pip_div)
        up_clusters = self._cluster_merge(raw_up_elements, cl_tol, digits, is_ascending=True)
        down_clusters = self._cluster_merge(raw_down_elements, cl_tol, digits, is_ascending=False)

        # Minimum Chamber Height to eliminate micro-chambers (e.g. 4.7 pips)
        min_chamber_height = max(0.60 * atr_h1, 0.40 * psych_step_macro, 12 * pt * pip_div)

        # Elect C1
        if up_clusters:
            imm_ceiling_c1 = up_clusters[0][0]
            c1_density_score = up_clusters[0][1]
            c1_tag = up_clusters[0][2]
        else:
            imm_ceiling_c1 = sub_ceiling
            c1_density_score = 2.0
            c1_tag = "FALLBACK_PSYCH"

        # Elect F1 (Ensuring separation from C1 >= min_chamber_height)
        imm_floor_f1 = sub_floor
        f1_density_score = 2.0
        f1_tag = "FALLBACK_PSYCH"
        if down_clusters:
            for cand_p, cand_sc, cand_tag in down_clusters:
                if (imm_ceiling_c1 - cand_p) >= min_chamber_height:
                    imm_floor_f1 = cand_p
                    f1_density_score = cand_sc
                    f1_tag = cand_tag
                    break
            else:
                imm_floor_f1 = sub_floor

        if (imm_ceiling_c1 - imm_floor_f1) < min_chamber_height:
            imm_floor_f1 = round(imm_ceiling_c1 - min_chamber_height, digits)

        # Elect C2 (Deep Ceiling Extension)
        deep_ceiling_c2 = round(imm_ceiling_c1 + max(psych_step_macro, 1.50 * atr_h1), digits)
        c2_density_score = 2.0
        c2_tag = "EXTENSION_TARGET"
        for cand_p, cand_sc, cand_tag in up_clusters[1:]:
            if cand_p >= imm_ceiling_c1 + max(0.60 * atr_h1, 0.40 * psych_step_macro):
                deep_ceiling_c2 = cand_p
                c2_density_score = cand_sc
                c2_tag = cand_tag
                break

        # Elect F2 (Deep Floor Extension)
        deep_floor_f2 = round(imm_floor_f1 - max(psych_step_macro, 1.50 * atr_h1), digits)
        f2_density_score = 2.0
        f2_tag = "DEEP_SUPPORT_TARGET"
        for cand_p, cand_sc, cand_tag in down_clusters:
            if cand_p <= imm_floor_f1 - max(0.60 * atr_h1, 0.40 * psych_step_macro):
                deep_floor_f2 = cand_p
                f2_density_score = cand_sc
                f2_tag = cand_tag
                break

        c1_fortress_tag = self._get_fortress_tag(c1_density_score)
        f1_fortress_tag = self._get_fortress_tag(f1_density_score)

        # Chamber Metrics
        chamber_width = max(imm_ceiling_c1 - imm_floor_f1, pt * 10)
        chamber_pos = min(1.0, max(0.0, (curr_mid - imm_floor_f1) / chamber_width))
        dist_to_c1 = abs(imm_ceiling_c1 - curr_mid)
        dist_to_f1 = abs(curr_mid - imm_floor_f1)

        # ── 2. BARRIER INTERACTION SEQUENCE TRACKER ──
        interaction_seq: List[str] = []
        if not df_h1.empty:
            for i in range(min(8, len(df_h1)), 0, -1):
                bar = df_h1.iloc[-i]
                b_high, b_low, b_open, b_close = bar['high'], bar['low'], bar['open'], bar['close']
                b_rng = max(b_high - b_low, 1e-5)
                u_wick = (b_high - max(b_open, b_close)) / b_rng
                l_wick = (min(b_open, b_close) - b_low) / b_rng
                
                if b_high >= imm_ceiling_c1 - (0.15 * atr_h1):
                    tag = "C1_SWEEP" if u_wick >= 0.25 else "C1_TOUCH"
                    if not interaction_seq or interaction_seq[-1] != tag:
                        interaction_seq.append(tag)
                elif b_low <= imm_floor_f1 + (0.15 * atr_h1):
                    tag = "F1_SWEEP" if l_wick >= 0.25 else "F1_TOUCH"
                    if not interaction_seq or interaction_seq[-1] != tag:
                        interaction_seq.append(tag)

        # ── 3. LEAN 7-STATE MACHINE CLASSIFIER ──
        h4_hl = len(h4_sl) >= 2 and (h4_sl[-1][1] > h4_sl[-2][1])
        h4_lh = len(h4_sh) >= 2 and (h4_sh[-1][1] < h4_sh[-2][1])
        last_h1_bear = not df_h1.empty and (df_h1['close'].iloc[-1] < df_h1['open'].iloc[-1])
        last_h1_bull = not df_h1.empty and (df_h1['close'].iloc[-1] > df_h1['open'].iloc[-1])
        last_d1_bull = not df_d1.empty and (df_d1['close'].iloc[-1] > df_d1['open'].iloc[-1])
        last_d1_bear = not df_d1.empty and (df_d1['close'].iloc[-1] < df_d1['open'].iloc[-1])

        # Boundary threshold: in outer 25% of chamber OR within 0.35 ATR H1 of boundary
        at_extreme_ceiling = (chamber_pos >= 0.75) or (dist_to_c1 <= 0.35 * atr_h1)
        at_extreme_floor = (chamber_pos <= 0.25) or (dist_to_f1 <= 0.35 * atr_h1)

        if curr_mid > imm_ceiling_c1 + (0.10 * atr_h1):
            market_state = "CEILING_BREAKOUT"
        elif curr_mid < imm_floor_f1 - (0.10 * atr_h1):
            market_state = "FLOOR_BREAKDOWN"
        elif at_extreme_ceiling:
            market_state = "CEILING_REJECTION" if (peak_u_wick_pct >= 25 or last_h1_bear or h4_lh) else "CHAMBER_CEILING_TEST"
        elif at_extreme_floor:
            market_state = "FLOOR_REJECTION" if (peak_l_wick_pct >= 25 or last_h1_bull or h4_hl) else "CHAMBER_FLOOR_TEST"
        else:
            market_state = "NEUTRAL_CHAMBER"

        # ── 4. EXECUTION LAYER ("Market State" != "Trade Signal") ──
        # Calibrate Minimum & Maximum Intraday Stop Loss Distances (Sniper Precision)
        if is_crypto:
            min_sl_dist = max(1.00 * atr_h1, 200.0)
            max_sl_dist = max(2.00 * atr_h1, 500.0)
        elif "XAU" in symbol:
            min_sl_dist = max(1.00 * atr_h1, 2.5)
            max_sl_dist = max(2.00 * atr_h1, 6.0)
        elif clean_sym in MOMENTUM_RUNNER_PAIRS or "NZD" in clean_sym or "JPY" in clean_sym or "GBP" in clean_sym:
            # High-volatility cross pairs (GBPNZD, GBPJPY, EURNZD, GBPAUD, CADJPY)
            min_sl_dist = max(0.80 * atr_h1, 15 * pt * pip_div) # ~16-20 pips
            max_sl_dist = max(1.50 * atr_h1, 35 * pt * pip_div) # ~35 pips
        else:
            min_sl_dist = max(0.80 * atr_h1, 10 * pt * pip_div) # ~10-15 pips
            max_sl_dist = min(1.50 * atr_h1, 25 * pt * pip_div) # ~25 pips

        if market_state in ("FLOOR_REJECTION", "CHAMBER_FLOOR_TEST"):
            macro_bias = "BULLISH_PULLBACK"
            primary_directive = "HUNT_BUY_AT_RBS"
            macro_bias_score = +0.85 if market_state == "FLOOR_REJECTION" else +0.70
            if h4_hl or last_d1_bull: macro_bias_score += 0.10
            macro_bias_score = round(min(1.0, macro_bias_score), 2)

            entry_anchor = round(imm_floor_f1 - (sweep_offset if clean_sym in SWEEP_SPECIALIST_PAIRS else 0.0), digits)
            entry_zone_proximal = round(entry_anchor + reload_width, digits)
            # Shield is the Immediate Floor F1
            calculated_sl = imm_floor_f1 - anti_wick_buffer
            if (entry_anchor - calculated_sl) < min_sl_dist:
                calculated_sl = entry_anchor - min_sl_dist
            elif (entry_anchor - calculated_sl) > max_sl_dist:
                calculated_sl = entry_anchor - max_sl_dist
            intraday_sl = round(calculated_sl, digits)

            macro_invalidation = round(imm_floor_f1 - (0.35 * atr_d1), digits)
            target_station_final = ceiling_station
            hard_circuit_breaker = bool((curr_mid <= imm_floor_f1 - (0.25 * atr_h1)) or (curr_mid < macro_invalidation))
            action_tier = "HARD_BLOCK" if hard_circuit_breaker else "FULL_ALLOW"

            sl_dist = max(abs(entry_anchor - intraday_sl), pt * 10)
            front_pad = (0.15 * atr_h1) + (spread_pts * pt)
            tp1_target = entry_anchor + max(1.25 * sl_dist, 0.50 * abs(imm_ceiling_c1 - entry_anchor))
            tp1_price = round(min(tp1_target, imm_ceiling_c1 - front_pad), digits)
            tp2_price = round(deep_ceiling_c2 - front_pad, digits)
            stage_label = f"RBS_SUPPORT_RETEST_AT_{imm_floor_f1:.{digits}f}"
            thesis = f"{symbol} in {market_state} at floor {imm_floor_f1:.{digits}f}. Reload targeting ceiling {imm_ceiling_c1:.{digits}f} with breakout extension to {deep_ceiling_c2:.{digits}f}."
            confidence_score = 88
            max_allowed_buy = round(entry_anchor + (0.25 * atr_d1), digits)
            min_allowed_sell = 0.0
            forbidden_traps = [f"Do NOT short into confirmed RBS support at {imm_floor_f1:.{digits}f}"]

        elif market_state in ("CEILING_REJECTION", "CHAMBER_CEILING_TEST"):
            if market_state == "CEILING_REJECTION":
                macro_bias = "BEARISH_PULLBACK"
                primary_directive = "HUNT_SELL_PULLBACK"
                macro_bias_score = -0.80
                entry_anchor = round(imm_ceiling_c1 + (sweep_offset if clean_sym in SWEEP_SPECIALIST_PAIRS else 0.0), digits)
                entry_zone_proximal = round(entry_anchor - reload_width, digits)
                # Shield is the Immediate Ceiling C1
                calculated_sl = imm_ceiling_c1 + anti_wick_buffer
                if (calculated_sl - entry_anchor) < min_sl_dist:
                    calculated_sl = entry_anchor + min_sl_dist
                elif (calculated_sl - entry_anchor) > max_sl_dist:
                    calculated_sl = entry_anchor + max_sl_dist
                intraday_sl = round(calculated_sl, digits)

                macro_invalidation = round(imm_ceiling_c1 + (0.35 * atr_d1), digits)
                target_station_final = floor_station
                hard_circuit_breaker = bool((curr_mid >= imm_ceiling_c1 + (0.25 * atr_h1)) or (curr_mid > macro_invalidation))
                action_tier = "HARD_BLOCK" if hard_circuit_breaker else "FULL_ALLOW"
                sl_dist = max(abs(intraday_sl - entry_anchor), pt * 10)
                front_pad = (0.15 * atr_h1) + (spread_pts * pt)
                tp1_target = entry_anchor - max(1.25 * sl_dist, 0.50 * abs(entry_anchor - imm_floor_f1))
                tp1_price = round(max(tp1_target, imm_floor_f1 + front_pad), digits)
                tp2_price = round(deep_floor_f2 + front_pad, digits)
                stage_label = f"FRONTIER_EXHAUSTION_AT_{imm_ceiling_c1:.{digits}f}"
                thesis = f"{symbol} in {market_state} at ceiling {imm_ceiling_c1:.{digits}f}. Mean-reversion targeting primary floor {imm_floor_f1:.{digits}f}."
                confidence_score = 85
                max_allowed_buy = 0.0
                min_allowed_sell = round(curr_mid - (0.20 * atr_d1), digits)
                forbidden_traps = [f"Do NOT BUY into ceiling resistance {imm_ceiling_c1:.{digits}f}"]
            else:
                macro_bias = "RANGE_BOUND"
                primary_directive = "FADE_CORRIDOR_EXTREMES"
                macro_bias_score = 0.0
                entry_anchor = imm_ceiling_c1
                entry_zone_proximal = round(entry_anchor - reload_width, digits)
                intraday_sl = round(entry_anchor + min_sl_dist, digits)
                tp1_price = round(imm_floor_f1, digits)
                tp2_price = round(deep_floor_f2, digits)
                stage_label = f"TESTING_CEILING_{imm_ceiling_c1:.{digits}f}"
                thesis = f"{symbol} is testing ceiling {imm_ceiling_c1:.{digits}f}. Wait for breakout or rejection confirmation."
                confidence_score = 75
                hard_circuit_breaker = False
                action_tier = "WATCH_ONLY"
                max_allowed_buy = 0.0
                min_allowed_sell = 0.0
                forbidden_traps = ["Wait for test resolution"]

        elif market_state == "CEILING_BREAKOUT":
            macro_bias = "BULLISH_EXPANSION"
            primary_directive = "HUNT_BUY_CONTINUATION"
            macro_bias_score = +0.85
            entry_anchor = imm_ceiling_c1
            entry_zone_proximal = round(entry_anchor + reload_width, digits)
            # Shield is the broken ceiling (now flipped to RBS support)
            calculated_sl = imm_ceiling_c1 - anti_wick_buffer
            if (entry_anchor - calculated_sl) < min_sl_dist:
                calculated_sl = entry_anchor - min_sl_dist
            intraday_sl = round(calculated_sl, digits)
            sl_dist = max(abs(entry_anchor - intraday_sl), pt * 10)
            front_pad = (0.15 * atr_h1) + (spread_pts * pt)
            tp1_price = round(deep_ceiling_c2 - front_pad, digits)
            tp2_price = round(deep_ceiling_c2 + (1.5 * sl_dist) - front_pad, digits)
            macro_invalidation = round(imm_ceiling_c1 - (0.20 * atr_d1), digits)
            target_station_final = next_macro_target
            hard_circuit_breaker = False
            action_tier = "FULL_ALLOW"
            stage_label = f"BREAKOUT_ABOVE_{imm_ceiling_c1:.{digits}f}"
            thesis = f"{symbol} confirmed breakout above {imm_ceiling_c1:.{digits}f} targeting extension {deep_ceiling_c2:.{digits}f}."
            confidence_score = 82
            max_allowed_buy = round(curr_mid + (0.20 * atr_d1), digits)
            min_allowed_sell = 0.0
            forbidden_traps = ["Do NOT short into confirmed breakout"]

        elif market_state == "FLOOR_BREAKDOWN":
            macro_bias = "BEARISH_EXPANSION"
            primary_directive = "HUNT_SELL_CONTINUATION"
            macro_bias_score = -0.85
            entry_anchor = imm_floor_f1
            entry_zone_proximal = round(entry_anchor - reload_width, digits)
            # Shield is the broken floor (now flipped to SBR resistance)
            calculated_sl = imm_floor_f1 + anti_wick_buffer
            if (calculated_sl - entry_anchor) < min_sl_dist:
                calculated_sl = entry_anchor + min_sl_dist
            intraday_sl = round(calculated_sl, digits)
            sl_dist = max(abs(intraday_sl - entry_anchor), pt * 10)
            front_pad = (0.15 * atr_h1) + (spread_pts * pt)
            tp1_price = round(deep_floor_f2 + front_pad, digits)
            tp2_price = round(deep_floor_f2 - (1.5 * sl_dist) + front_pad, digits)
            macro_invalidation = round(imm_floor_f1 + (0.20 * atr_d1), digits)
            target_station_final = floor_station
            hard_circuit_breaker = False
            action_tier = "FULL_ALLOW"
            stage_label = f"BREAKDOWN_BELOW_{imm_floor_f1:.{digits}f}"
            thesis = f"{symbol} broke down below {imm_floor_f1:.{digits}f} targeting deep support {deep_floor_f2:.{digits}f}."
            confidence_score = 82
            max_allowed_buy = 0.0
            min_allowed_sell = round(curr_mid - (0.20 * atr_d1), digits)
            forbidden_traps = ["Do NOT buy into confirmed breakdown"]

        else: # NEUTRAL_CHAMBER (Mid-Range Consolidation / Chop Zone)
            macro_bias = "RANGE_BOUND"
            primary_directive = "FADE_CORRIDOR_EXTREMES"
            macro_bias_score = 0.0
            last_event = interaction_seq[-1] if interaction_seq else ""
            
            entry_anchor = round(imm_floor_f1, digits)
            entry_zone_proximal = round(entry_anchor + reload_width, digits)
            structural_floor = deep_floor_f2
            calculated_sl = structural_floor - anti_wick_buffer
            if (entry_anchor - calculated_sl) < min_sl_dist:
                calculated_sl = entry_anchor - min_sl_dist
            intraday_sl = round(calculated_sl, digits)
            sl_dist = max(abs(entry_anchor - intraday_sl), pt * 10)
            front_pad = (0.15 * atr_h1) + (spread_pts * pt)
            tp1_price = round(imm_ceiling_c1 - front_pad, digits)
            tp2_price = round(deep_ceiling_c2 - front_pad, digits)
            
            stage_label = f"CHAMBER_CONSOLIDATION_[{imm_floor_f1:.{digits}f}-{imm_ceiling_c1:.{digits}f}]"
            thesis = f"{symbol} is consolidating inside dealing chamber (Range: {chamber_pos:.0%}). Discipline requires waiting for extreme boundary touch at {imm_floor_f1:.{digits}f} or {imm_ceiling_c1:.{digits}f}."
            confidence_score = 70
            hard_circuit_breaker = False
            action_tier = "WATCH_ONLY"
            max_allowed_buy = round(imm_floor_f1 + (0.15 * atr_h1), digits)
            min_allowed_sell = round(imm_ceiling_c1 - (0.15 * atr_h1), digits)
            forbidden_traps = [f"Do NOT execute market orders in mid-chamber consolidation zone (Range: {chamber_pos:.0%})"]
            macro_invalidation = round(deep_floor_f2 - (0.20 * atr_d1), digits)
            target_station_final = ceiling_station

        if is_crypto:
            sl_pips = round(abs(intraday_sl - entry_anchor), 1)
            tp1_pips = round(abs(entry_anchor - tp1_price), 1)
            tp2_pips = round(abs(entry_anchor - tp2_price), 1)
        else:
            sl_pips = round(abs(intraday_sl - entry_anchor) / pt / pip_div, 1)
            tp1_pips = round(abs(entry_anchor - tp1_price) / pt / pip_div, 1)
            tp2_pips = round(abs(entry_anchor - tp2_price) / pt / pip_div, 1)
        rr_ratio = round(tp2_pips / max(sl_pips, 1.0), 2)

        calc_ms = round((time.perf_counter() - t0) * 1000, 2)
        total_bars_cnt = (
            (len(rates_mn1) if rates_mn1 is not None else 0) +
            (len(rates_w1) if rates_w1 is not None else 0) +
            (len(rates_d1) if rates_d1 is not None else 0) +
            (len(rates_h4) if rates_h4 is not None else 0) +
            (len(rates_h1) if rates_h1 is not None else 0) +
            (len(rates_m30) if rates_m30 is not None else 0)
        )

        # ── 5. NARRATIVE OUTPUT LAYER (Pure Consumer String Formatting) ──
        bull_roadmap = (
            f"▲ BULLISH PATH: Hold > Immediate Floor {imm_floor_f1:.{digits}f} -> Tests Ceiling {imm_ceiling_c1:.{digits}f} │ "
            f"Breakout > {imm_ceiling_c1:.{digits}f} -> Extension {deep_ceiling_c2:.{digits}f}"
        )
        bear_roadmap = (
            f"▼ BEARISH PATH: Reject < Immediate Ceiling {imm_ceiling_c1:.{digits}f} -> Retests Floor {imm_floor_f1:.{digits}f} │ "
            f"Breakdown < {imm_floor_f1:.{digits}f} -> Slips to Deep Support {deep_floor_f2:.{digits}f}"
        )

        # Fundamental Engine
        fundamental_backing, fundamental_grade = "", "GRADE_A"
        try:
            from src.analytics.apex_fundamental_engine import apex_fundamental_engine
            fund_eval = apex_fundamental_engine.evaluate_pair(symbol)
            fundamental_backing = fund_eval.action_directive
            fundamental_grade = fund_eval.setup_grade
            if fund_eval.hard_veto_flag:
                hard_circuit_breaker = True
                action_tier = "HARD_BLOCK"
        except Exception: pass

        vol_ratio = atr_h1 / max((atr_d1 / 24.0), 1e-6)
        if vol_ratio > 2.0: regime_stability = "HIGH_VOLATILITY"
        elif vol_ratio < 0.6: regime_stability = "COMPRESSION"
        elif abs(macro_bias_score) >= 0.70: regime_stability = "EXPANSION"
        else: regime_stability = "STABLE"

        directive = MacroStrategicDirective(
            symbol=symbol,
            calculation_time_ms=calc_ms,
            daily_macro_bias=macro_bias,
            primary_execution_directive=primary_directive,
            target_station_price=target_station_final,
            ceiling_frontier_price=round(recent_frontier_high, digits),
            floor_rbs_support_price=macro_rbs_d1,
            invalidation_stop_price=macro_invalidation,
            entry_limit_anchor=entry_anchor,
            intraday_sl_price=intraday_sl,
            intraday_sl_pips=sl_pips,
            tp1_price=tp1_price,
            tp1_pips=tp1_pips,
            tp2_price=tp2_price,
            tp2_pips=tp2_pips,
            risk_reward_ratio=rr_ratio,
            max_allowed_buy_price=max_allowed_buy,
            min_allowed_sell_price=min_allowed_sell,
            forbidden_traps=forbidden_traps,
            confidence_score=confidence_score,
            structural_stage=stage_label,
            daily_mandate_thesis=thesis,
            future_macro_roadmap=f"{bull_roadmap}\n{bear_roadmap}",
            macro_rbs_w1=macro_rbs_w1,
            macro_sbr_w1=macro_sbr_w1,
            macro_rbs_d1=macro_rbs_d1,
            macro_sbr_d1=macro_sbr_d1,
            inter_rbs_h4=inter_rbs_h4,
            inter_sbr_h4=inter_sbr_h4,
            micro_rbs_h1=micro_rbs_h1,
            micro_sbr_h1=micro_sbr_h1,
            d1_annual_high=round(d1_annual_high, digits),
            d1_annual_low=round(d1_annual_low, digits),
            sub_floor_50=sub_floor,
            sub_ceiling_50=sub_ceiling,
            market_state=market_state,
            immediate_ceiling_c1=imm_ceiling_c1,
            immediate_floor_f1=imm_floor_f1,
            deep_target_floor_f2=deep_floor_f2,
            deep_target_ceiling_c2=deep_ceiling_c2,
            c1_density_score=c1_density_score,
            f1_density_score=f1_density_score,
            c1_fortress_tag=c1_fortress_tag,
            f1_fortress_tag=f1_fortress_tag,
            chamber_position_pct=round(chamber_pos, 2),
            retest_touch_count=len(interaction_seq),
            interaction_sequence=interaction_seq,
            bullish_contingency_path=bull_roadmap,
            bearish_contingency_path=bear_roadmap,
            atr_d1_pips=round(atr_d1, 1) if is_crypto else round(atr_d1 / pt / pip_div, 1),
            atr_h1_pips=round(atr_h1, 1) if is_crypto else round(atr_h1 / pt / pip_div, 1),
            atr_m30_pips=round(atr_m30, 1) if is_crypto else round(atr_m30 / pt / pip_div, 1),
            current_spread_pts=spread_pts,
            entry_zone_proximal=entry_zone_proximal,
            total_bars_computed=total_bars_cnt,
            w1_key_demand=w1_key_demand,
            w1_key_supply=w1_key_supply,
            macro_bias_score=macro_bias_score,
            regime_stability=regime_stability,
            hard_circuit_breaker=hard_circuit_breaker,
            action_tier=action_tier,
            contingency_target=0.0,
            fundamental_backing=fundamental_backing,
            fundamental_grade=fundamental_grade,
            current_bid=round(curr_bid, digits),
            current_ask=round(curr_ask, digits),
            current_mid=round(curr_mid, digits),
            raw_payload={
                "market_state": market_state,
                "chamber_pos": chamber_pos,
                "c1": imm_ceiling_c1,
                "f1": imm_floor_f1,
                "c1_density_score": c1_density_score,
                "f1_density_score": f1_density_score,
                "c1_fortress_tag": c1_fortress_tag,
                "f1_fortress_tag": f1_fortress_tag,
                "c1_structure_tags": c1_tag,
                "f1_structure_tags": f1_tag,
                "f2_deep": deep_floor_f2,
                "c2_deep": deep_ceiling_c2,
                "interaction_sequence": interaction_seq,
                "sweep_offset": sweep_offset,
                "NARRATIVE_STORYTELLING": {
                    "macro_annual_corridor": f"Annual Range: [{d1_annual_low:.{digits}f} - {d1_annual_high:.{digits}f}]",
                    "w1_major_anchor": f"W1 Key Demand: {w1_key_demand:.{digits}f} │ W1 Key Supply: {w1_key_supply:.{digits}f}",
                    "current_structural_stage": stage_label,
                    "daily_mandate_thesis": thesis,
                    "future_macro_roadmap": f"{bull_roadmap}\n{bear_roadmap}"
                }
            }
        )

        self._cache[symbol] = directive
        self._cache_ts[symbol] = time.time()
        return directive

    def get_directive(self, symbol: str, mt5_connector=None, force_refresh: bool = False) -> MacroStrategicDirective:
        """
        Retrieves cached directive or recomputes if missing / expired (>60s) / forced.
        """
        now = time.time()
        if not force_refresh and symbol in self._cache:
            if (now - self._cache_ts.get(symbol, 0.0)) < self._cache_ttl_sec:
                return self._cache[symbol]
        return self.compute_directive(symbol, mt5_connector=mt5_connector)

    def refresh_all_symbols(self, symbols: List[str], mt5_connector=None) -> Dict[str, MacroStrategicDirective]:
        """
        Batch refreshes all scanner symbols in sequence (<0.5s for 26 symbols).
        """
        t0 = time.perf_counter()
        results = {}
        for sym in symbols:
            try:
                results[sym] = self.compute_directive(sym, mt5_connector=mt5_connector)
            except Exception as e:
                logger.warning(f"Error computing strategic directive for {sym}: {e}")
        self._last_update_ts = time.time()
        calc_total_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info(f"✅ MacroStrategicEngine refreshed {len(results)}/{len(symbols)} symbols in {calc_total_ms} ms (0 Tokens).")
        return results


# Global singleton instance
macro_strategic_engine = MacroStrategicEngine()
