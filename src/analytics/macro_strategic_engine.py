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
    macro_rbs_d1: float
    macro_sbr_d1: float
    inter_rbs_h4: float
    inter_sbr_h4: float
    micro_rbs_h1: float
    micro_sbr_h1: float
    sub_floor_50: float
    sub_ceiling_50: float
    immediate_ceiling_c1: float = 0.0
    immediate_floor_f1: float = 0.0
    deep_target_floor_f2: float = 0.0
    deep_target_ceiling_c2: float = 0.0
    chamber_position_pct: float = 0.50
    retest_touch_count: int = 1
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

        # 5. Multi-Scale SBR & RBS Calculator (D1, H4, H1)
        d1_sh, d1_sl = self._find_swings(df_d1, 90, 2)
        rbs_d1_cand = [sh[1] for sh in d1_sh if sh[1] < curr_mid - (0.25 * atr_d1)]
        macro_rbs_d1 = round(max(rbs_d1_cand), digits) if rbs_d1_cand else floor_station
        sbr_d1_cand = [sl[1] for sl in d1_sl if sl[1] > curr_mid + (0.25 * atr_d1)]
        macro_sbr_d1 = round(min(sbr_d1_cand), digits) if sbr_d1_cand else ceiling_station

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

        # 7. Equal Lows / Equal Highs Sweep Detection
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

        # 11. Station Collision & Dual-Reaction Synthesis
        last_d1_bearish = not df_d1.empty and (df_d1['close'].iloc[-1] < df_d1['open'].iloc[-1])
        # 11. Station Collision & State Machine Engine
        last_d1_bullish = not df_d1.empty and (df_d1['close'].iloc[-1] > df_d1['open'].iloc[-1])
        h1_momentum_down = not df_h1.empty and len(df_h1) >= 12 and (df_h1['close'].iloc[-1] < df_h1['close'].iloc[-12])
        h1_momentum_up = not df_h1.empty and len(df_h1) >= 12 and (df_h1['close'].iloc[-1] > df_h1['close'].iloc[-12])

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

        # ── LAYER 1: CONFLUENCE CLUSTER ASSEMBLY (Mesh Mapping) ──
        psych_cands_up = [sub_ceiling, ceiling_station, next_macro_target]
        sbr_cands_up = [v for v in [micro_sbr_h1, inter_sbr_h4, macro_sbr_d1, dbd_entry] if v and v > curr_mid + (0.05 * atr_h1)]
        bear_obs_up = [ob.get('bottom', 0.0) for ob in bear_obs if ob.get('bottom', 0.0) > curr_mid + (0.05 * atr_h1)]
        all_ceilings = sorted(list(set([round(v, digits) for v in (psych_cands_up + sbr_cands_up + bear_obs_up) if v > curr_mid])))
        
        imm_ceiling_c1 = all_ceilings[0] if all_ceilings else sub_ceiling
        deep_ceiling_c2 = all_ceilings[1] if len(all_ceilings) > 1 else round(imm_ceiling_c1 + psych_step_micro, digits)

        psych_cands_down = [sub_floor, floor_station, round(floor_station - psych_step_macro, digits)]
        rbs_cands_down = [v for v in [micro_rbs_h1, inter_rbs_h4, macro_rbs_d1, rbr_entry] if v and v < curr_mid - (0.05 * atr_h1)]
        bull_obs_down = [ob.get('top', 0.0) for ob in bull_obs if ob.get('top', 0.0) < curr_mid - (0.05 * atr_h1)]
        all_floors = sorted(list(set([round(v, digits) for v in (psych_cands_down + rbs_cands_down + bull_obs_down) if v < curr_mid])), reverse=True)
        
        imm_floor_f1 = all_floors[0] if all_floors else sub_floor
        deep_floor_f2 = all_floors[1] if len(all_floors) > 1 else round(imm_floor_f1 - psych_step_micro, digits)

        # ── LAYER 2: ACTIVE CHAMBER RESOLUTION ──
        chamber_width = max(imm_ceiling_c1 - imm_floor_f1, pt * 10)
        chamber_pos = min(1.0, max(0.0, (curr_mid - imm_floor_f1) / chamber_width))
        dist_to_c1 = abs(imm_ceiling_c1 - curr_mid)
        dist_to_f1 = abs(curr_mid - imm_floor_f1)

        # ── LAYER 3: MULTI-NODE PING-PONG & RETEST STATE ENGINE ──
        h4_hl = len(h4_sl) >= 2 and (h4_sl[-1][1] > h4_sl[-2][1])
        h4_lh = len(h4_sh) >= 2 and (h4_sh[-1][1] < h4_sh[-2][1])

        # Node A: At/Near Floor F1 (Bouncing off F1)
        if dist_to_f1 <= max(0.35 * atr_h1, 8 * pt * pip_div) or chamber_pos <= 0.35:
            macro_bias = "BULLISH_PULLBACK"
            primary_directive = "HUNT_BUY_AT_RBS"
            macro_bias_score = +0.85
            if h4_hl or last_d1_bullish:
                macro_bias_score += 0.10
            macro_bias_score = round(min(1.0, macro_bias_score), 2)

            entry_anchor = round(imm_floor_f1 - (sweep_offset if clean_sym in SWEEP_SPECIALIST_PAIRS else 0.0), digits)
            entry_zone_proximal = round(entry_anchor + reload_width, digits)
            structural_floor = deep_floor_f2 if deep_floor_f2 < entry_anchor else (macro_rbs_d1 if macro_rbs_d1 < entry_anchor else entry_anchor - 1.25 * atr_h1)
            
            calculated_sl = structural_floor - anti_wick_buffer
            intraday_sl = round(calculated_sl, digits)

            macro_invalidation = round(deep_floor_f2 - (0.20 * atr_d1), digits)
            target_station_final = ceiling_station
            hard_circuit_breaker = bool((curr_mid <= imm_floor_f1 - (0.25 * atr_h1)) or (curr_mid < macro_invalidation))
            action_tier = "HARD_BLOCK" if hard_circuit_breaker else "FULL_ALLOW"

            sl_dist = max(abs(entry_anchor - intraday_sl), pt * 10)
            front_pad = (0.15 * atr_h1) + (spread_pts * pt)
            
            tp1_price = round(imm_ceiling_c1 - front_pad, digits)
            tp2_price = round(deep_ceiling_c2 - front_pad, digits)
            
            stage_label = f"RBS_SUPPORT_RETEST_AT_{imm_floor_f1:.{digits}f}"
            thesis = f"{symbol} landed on structural RBS support at {imm_floor_f1:.{digits}f}. Reload targeting {imm_ceiling_c1:.{digits}f} with breakout extension to {deep_ceiling_c2:.{digits}f}."
            confidence_score = 88
            max_allowed_buy = round(entry_anchor + (0.25 * atr_d1), digits)
            min_allowed_sell = 0.0
            forbidden_traps = [f"Do NOT short into fresh confirmed RBS support at {imm_floor_f1:.{digits}f}"]

        # Node B: At/Near Ceiling C1 (Testing Ceiling)
        elif dist_to_c1 <= max(0.35 * atr_h1, 8 * pt * pip_div) or chamber_pos >= 0.70:
            is_exhaustion = peak_u_wick_pct >= 30 or h4_lh or (not df_h1.empty and df_h1['close'].iloc[-1] < df_h1['open'].iloc[-1])
            if is_exhaustion:
                macro_bias = "BEARISH_PULLBACK"
                primary_directive = "HUNT_SELL_PULLBACK"
                macro_bias_score = -0.80
                entry_anchor = round(imm_ceiling_c1 + (sweep_offset if clean_sym in SWEEP_SPECIALIST_PAIRS else 0.0), digits)
                entry_zone_proximal = round(entry_anchor - reload_width, digits)
                structural_roof = deep_ceiling_c2 if deep_ceiling_c2 > entry_anchor else (macro_sbr_d1 if macro_sbr_d1 > entry_anchor else entry_anchor + 1.25 * atr_h1)
                calculated_sl = structural_roof + anti_wick_buffer
                intraday_sl = round(calculated_sl, digits)
                macro_invalidation = round(deep_ceiling_c2 + (0.20 * atr_d1), digits)
                target_station_final = floor_station
                hard_circuit_breaker = bool((curr_mid >= imm_ceiling_c1 + (0.25 * atr_h1)) or (curr_mid > macro_invalidation))
                action_tier = "HARD_BLOCK" if hard_circuit_breaker else "FULL_ALLOW"
                sl_dist = max(abs(intraday_sl - entry_anchor), pt * 10)
                front_pad = (0.15 * atr_h1) + (spread_pts * pt)
                tp1_price = round(imm_floor_f1 + front_pad, digits)
                tp2_price = round(deep_floor_f2 + front_pad, digits)
                stage_label = f"FRONTIER_EXHAUSTION_AT_{imm_ceiling_c1:.{digits}f}"
                thesis = f"{symbol} reached psychological ceiling {imm_ceiling_c1:.{digits}f} with upper rejection pressure. Mean-reversion targeting primary RBS {imm_floor_f1:.{digits}f}."
                confidence_score = 85
                max_allowed_buy = 0.0
                min_allowed_sell = round(curr_mid - (0.20 * atr_d1), digits)
                forbidden_traps = [f"Do NOT BUY above {round(curr_mid + (0.15 * atr_d1), digits):.{digits}f}"]
            else:
                macro_bias = "BULLISH_EXPANSION"
                primary_directive = "HUNT_BUY_CONTINUATION"
                macro_bias_score = +0.85
                entry_anchor = imm_ceiling_c1
                entry_zone_proximal = round(entry_anchor + reload_width, digits)
                structural_floor = imm_floor_f1
                calculated_sl = structural_floor - anti_wick_buffer
                intraday_sl = round(calculated_sl, digits)
                sl_dist = max(abs(entry_anchor - intraday_sl), pt * 10)
                front_pad = (0.15 * atr_h1) + (spread_pts * pt)
                tp1_price = round(deep_ceiling_c2 - front_pad, digits)
                tp2_price = round(deep_ceiling_c2 + (1.5 * sl_dist) - front_pad, digits)
                stage_label = f"BREAKOUT_EXPANSION_ABOVE_{imm_ceiling_c1:.{digits}f}"
                thesis = f"{symbol} is breaking out above psychological ceiling {imm_ceiling_c1:.{digits}f}."
                confidence_score = 82
                max_allowed_buy = round(curr_mid + (0.20 * atr_d1), digits)
                min_allowed_sell = 0.0
                forbidden_traps = [f"Do NOT short during unmitigated bullish breakout"]

        # Node C: Mid-Chamber Corridor
        else:
            is_corridor_bear = h4_lh or (last_d1_bullish == False)
            if is_corridor_bear:
                macro_bias = "BEARISH_EXPANSION"
                primary_directive = "HUNT_SELL_CONTINUATION"
                macro_bias_score = -0.75
                entry_anchor = round(imm_ceiling_c1, digits)
                entry_zone_proximal = round(entry_anchor - reload_width, digits)
                structural_roof = deep_ceiling_c2
                calculated_sl = structural_roof + anti_wick_buffer
                intraday_sl = round(calculated_sl, digits)
                sl_dist = max(abs(intraday_sl - entry_anchor), pt * 10)
                front_pad = (0.15 * atr_h1) + (spread_pts * pt)
                tp1_price = round(imm_floor_f1 + front_pad, digits)
                tp2_price = round(deep_floor_f2 + front_pad, digits)
                stage_label = f"BEARISH_CHAMBER_ROTATION_TO_{imm_floor_f1:.{digits}f}"
                thesis = f"{symbol} is rotating down within dealing chamber (Range: {chamber_pos:.0%})."
                confidence_score = 78
                max_allowed_buy = 0.0
                min_allowed_sell = round(curr_mid - (0.20 * atr_d1), digits)
            else:
                macro_bias = "BULLISH_EXPANSION"
                primary_directive = "HUNT_BUY_CONTINUATION"
                macro_bias_score = +0.75
                entry_anchor = round(imm_floor_f1, digits)
                entry_zone_proximal = round(entry_anchor + reload_width, digits)
                structural_floor = deep_floor_f2
                calculated_sl = structural_floor - anti_wick_buffer
                intraday_sl = round(calculated_sl, digits)
                sl_dist = max(abs(entry_anchor - intraday_sl), pt * 10)
                front_pad = (0.15 * atr_h1) + (spread_pts * pt)
                tp1_price = round(imm_ceiling_c1 - front_pad, digits)
                tp2_price = round(deep_ceiling_c2 - front_pad, digits)
                stage_label = f"BULLISH_CHAMBER_ROTATION_TO_{imm_ceiling_c1:.{digits}f}"
                thesis = f"{symbol} is rotating up within dealing chamber (Range: {chamber_pos:.0%})."
                confidence_score = 78
                max_allowed_buy = round(curr_mid + (0.20 * atr_d1), digits)

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

        # Contingency Targets
        contingency_demand_cands = [_get_ob_core(ob) for ob in macro_bull_obs if _get_ob_core(ob) < (macro_invalidation - 0.15 * atr_d1)]
        contingency_demand = round(max(contingency_demand_cands), digits) if contingency_demand_cands else round(floor_station - psych_step_macro, digits)
        contingency_supply_cands = [_get_ob_core(ob) for ob in macro_bear_obs if _get_ob_core(ob) > (macro_invalidation + 0.15 * atr_d1)]
        contingency_supply = round(min(contingency_supply_cands), digits) if contingency_supply_cands else next_macro_target

        inval_floor = macro_invalidation if macro_invalidation < deep_floor_f2 else round(deep_floor_f2 - (0.20 * atr_d1), digits)
        contingency_demand_val = contingency_demand if contingency_demand < inval_floor else round(inval_floor - psych_step_macro, digits)
        contingency_supply_val = contingency_supply if contingency_supply > deep_ceiling_c2 else round(deep_ceiling_c2 + psych_step_macro, digits)

        bull_roadmap = (
            f"▲ BULLISH PATH: Hold > Immediate Floor {imm_floor_f1:.{digits}f} -> Tests Ceiling {imm_ceiling_c1:.{digits}f} │ "
            f"Breakout > {imm_ceiling_c1:.{digits}f} -> Extension {deep_ceiling_c2:.{digits}f} / W1 Supply {contingency_supply_val:.{digits}f}"
        )
        bear_roadmap = (
            f"▼ BEARISH PATH: Reject < Immediate Ceiling {imm_ceiling_c1:.{digits}f} -> Retests Floor {imm_floor_f1:.{digits}f} │ "
            f"Breakdown < {imm_floor_f1:.{digits}f} -> Slips to Deep FVG {deep_floor_f2:.{digits}f} -> W1 Demand {contingency_demand_val:.{digits}f}"
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
        if vol_ratio > 2.0:
            regime_stability = "HIGH_VOLATILITY"
        elif vol_ratio < 0.6:
            regime_stability = "COMPRESSION"
        elif abs(macro_bias_score) >= 0.70:
            regime_stability = "EXPANSION"
        else:
            regime_stability = "STABLE"

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
            macro_rbs_d1=macro_rbs_d1,
            macro_sbr_d1=macro_sbr_d1,
            inter_rbs_h4=inter_rbs_h4,
            inter_sbr_h4=inter_sbr_h4,
            micro_rbs_h1=micro_rbs_h1,
            micro_sbr_h1=micro_sbr_h1,
            sub_floor_50=sub_floor,
            sub_ceiling_50=sub_ceiling,
            immediate_ceiling_c1=imm_ceiling_c1,
            immediate_floor_f1=imm_floor_f1,
            deep_target_floor_f2=deep_floor_f2,
            deep_target_ceiling_c2=deep_ceiling_c2,
            chamber_position_pct=round(chamber_pos, 2),
            retest_touch_count=1,
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
                "regime_stability": regime_stability,
                "hard_circuit_breaker": hard_circuit_breaker,
                "action_tier": action_tier,
                "NARRATIVE_STORYTELLING": {
                    "macro_annual_corridor": f"Annual Range: [{d1_annual_low:.{digits}f} - {d1_annual_high:.{digits}f}] (4-Year: [{mn1_low:.{digits}f} - {mn1_high:.{digits}f}])",
                    "w1_major_anchor": f"W1 Key Demand: {w1_key_demand:.{digits}f} │ W1 Key Supply: {w1_key_supply:.{digits}f}",
                    "discovered_liquidity_sweeps": f"Equal Lows swept at {eq_low_price:.{digits}f} ({eq_low_date_str}) -> +{pips_rallied} pips",
                    "current_structural_stage": stage_label,
                    "daily_mandate_thesis": thesis,
                    "future_macro_roadmap": f"Hold above RBS {macro_rbs_d1:.{digits}f} -> Target {next_macro_target:.{digits}f}"
                },
                "QUANT_DIRECTIVE_VALUES": {
                    "daily_macro_bias": macro_bias,
                    "macro_bias_score": macro_bias_score,
                    "action_tier": action_tier,
                    "regime_stability": regime_stability,
                    "hard_circuit_breaker": hard_circuit_breaker,
                    "primary_execution_directive": primary_directive,
                    "entry_limit_anchor": entry_anchor,
                    "intraday_sl_price": intraday_sl,
                    "sl_distance_pips": sl_pips,
                    "tp1_partial_50_pct": tp1_price,
                    "tp1_pips": tp1_pips,
                    "tp2_station_target": tp2_price,
                    "tp2_pips": tp2_pips,
                    "risk_reward_ratio": f"1 : {rr_ratio}",
                    "invalidation_stop_price": macro_invalidation,
                    "forbidden_traps": forbidden_traps,
                    "confidence_score": confidence_score
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
