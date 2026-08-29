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
    atr_d1_pips: float
    atr_h1_pips: float
    atr_m30_pips: float
    current_spread_pts: int
    raw_payload: Dict[str, Any] = field(default_factory=dict)


class MacroStrategicEngine:
    """
    Pure Quant Hierarchical State Engine:
    Computes top-down macro directives and structural zones across 6 native MT5 timeframes.
    """

    def __init__(self):
        self._cache: Dict[str, MacroStrategicDirective] = {}
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

        psych_step_micro = 0.500 if "JPY" in symbol else (25.0 if "XAU" in symbol else 0.0050)
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

        # 8. Frontier Rejection & Wick Ratios (D1)
        recent_frontier_high = float(df_d1['high'].tail(15).max()) if not df_d1.empty else curr_mid * 1.05
        is_near_ceiling = (abs(recent_frontier_high - sub_ceiling) <= (0.35 * atr_d1)) or (recent_frontier_high >= sub_ceiling)
        
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

        # 9. Station Collision & Dual-Reaction Synthesis
        last_d1_bearish = not df_d1.empty and (df_d1['close'].iloc[-1] < df_d1['open'].iloc[-1])
        last_d1_bullish = not df_d1.empty and (df_d1['close'].iloc[-1] > df_d1['open'].iloc[-1])

        # Skenario A: Ceiling Rejection / Frontier Exhaustion
        if is_near_ceiling and (peak_u_wick_pct >= 35 or last_d1_bearish):
            macro_bias = "BEARISH_PULLBACK"
            primary_directive = "HUNT_SELL_PULLBACK"

            entry_anchor = dbd_entry if (dbd_entry and dbd_entry > curr_mid) else micro_sbr_h1
            structural_roof = dbd_roof if dbd_roof else recent_frontier_high
            
            calculated_sl = structural_roof + anti_wick_buffer
            max_sl_dist = min(2.0 * atr_h1, 160 * pt) if "XAU" not in symbol else (2.5 * atr_h1)
            if (calculated_sl - entry_anchor) > max_sl_dist:
                calculated_sl = entry_anchor + max_sl_dist
            intraday_sl = round(calculated_sl, digits)

            macro_invalidation = round(recent_frontier_high + (0.20 * atr_d1), digits)
            target_station_final = macro_rbs_d1
            
            tp1_price = sub_floor if sub_floor < entry_anchor else round(entry_anchor - (abs(entry_anchor - target_station_final) * 0.50), digits)
            tp2_price = target_station_final

            sl_pips = round(abs(intraday_sl - entry_anchor) / pt / pip_div, 1)
            tp1_pips = round(abs(entry_anchor - tp1_price) / pt / pip_div, 1)
            tp2_pips = round(abs(entry_anchor - tp2_price) / pt / pip_div, 1)
            rr_ratio = round(tp2_pips / max(sl_pips, 1.0), 2)

            max_allowed_buy = round(curr_mid + (0.15 * atr_d1), digits)
            min_allowed_sell = round(curr_mid + (0.10 * atr_d1), digits)
            forbidden_traps = [
                f"Do NOT BUY above {max_allowed_buy:.{digits}f} (Ceiling Trap into {sub_ceiling:.{digits}f})",
                f"Do NOT chase breakdown below {sub_floor:.{digits}f} without H1 confirmation"
            ]
            confidence_score = 88
            stage_label = f"FRONTIER_EXHAUSTION_AT_{sub_ceiling:.{digits}f}"
            thesis = (
                f"{symbol} reached psychological ceiling {sub_ceiling:.{digits}f} with selling pressure (Peak Upper Wick: {peak_u_wick_pct}%). "
                f"Institutional thesis requires a Mean-Reversion Pullback targeting the D1 RBS zone at {macro_rbs_d1:.{digits}f} "
                f"(with intermediate H4 RBS at {inter_rbs_h4:.{digits}f}) to reload before attempting {next_macro_target:.{digits}f}."
            )

        # Skenario B: RBS Retest / Sub-Floor Bouncing (Bullish Pullback Reload)
        elif curr_mid <= sub_floor + (0.35 * atr_d1) and (peak_l_wick_pct >= 35 or last_d1_bullish):
            macro_bias = "BULLISH_PULLBACK"
            primary_directive = "HUNT_BUY_AT_RBS"

            entry_anchor = rbr_entry if (rbr_entry and rbr_entry < curr_mid) else (round(sub_floor + (0.02 * atr_h1), digits))
            structural_floor = rbr_floor if rbr_floor else inter_rbs_h4

            calculated_sl = structural_floor - anti_wick_buffer
            max_sl_dist = min(2.0 * atr_h1, 160 * pt) if "XAU" not in symbol else (2.5 * atr_h1)
            if (entry_anchor - calculated_sl) > max_sl_dist:
                calculated_sl = entry_anchor - max_sl_dist
            intraday_sl = round(calculated_sl, digits)

            macro_invalidation = round(sub_floor - (0.20 * atr_d1), digits)
            target_station_final = sub_ceiling

            tp1_price = round(entry_anchor + (abs(target_station_final - entry_anchor) * 0.50), digits)
            tp2_price = target_station_final

            sl_pips = round(abs(entry_anchor - intraday_sl) / pt / pip_div, 1)
            tp1_pips = round(abs(tp1_price - entry_anchor) / pt / pip_div, 1)
            tp2_pips = round(abs(tp2_price - entry_anchor) / pt / pip_div, 1)
            rr_ratio = round(tp2_pips / max(sl_pips, 1.0), 2)

            max_allowed_buy = round(entry_anchor + (0.25 * atr_d1), digits)
            min_allowed_sell = 0.0
            forbidden_traps = [
                f"Do NOT short into fresh confirmed RBS support at {sub_floor:.{digits}f}",
                f"Do NOT BUY above {round(curr_mid + (0.20 * atr_d1), digits):.{digits}f} (Impulse Chase)"
            ]
            confidence_score = 85
            stage_label = f"RBS_SUPPORT_RETEST_AT_{sub_floor:.{digits}f}"
            thesis = f"{symbol} is retesting primary structural RBS support at {sub_floor:.{digits}f}. Favorable Bull Flag reload zone towards {sub_ceiling:.{digits}f}."

        # Skenario C: Bullish Open Corridor Expansion
        else:
            macro_bias = "BULLISH_EXPANSION"
            primary_directive = "HUNT_BUY_CONTINUATION"

            entry_anchor = micro_rbs_h1
            calculated_sl = entry_anchor - anti_wick_buffer
            max_sl_dist = min(2.0 * atr_h1, 160 * pt) if "XAU" not in symbol else (2.5 * atr_h1)
            if (curr_mid - calculated_sl) > max_sl_dist:
                calculated_sl = curr_mid - max_sl_dist
            intraday_sl = round(calculated_sl, digits)

            macro_invalidation = round(floor_station - (0.20 * atr_d1), digits)
            target_station_final = ceiling_station

            tp1_price = sub_ceiling
            tp2_price = target_station_final

            sl_pips = round(abs(curr_mid - intraday_sl) / pt / pip_div, 1)
            tp1_pips = round(abs(tp1_price - curr_mid) / pt / pip_div, 1)
            tp2_pips = round(abs(tp2_price - curr_mid) / pt / pip_div, 1)
            rr_ratio = round(tp2_pips / max(sl_pips, 1.0), 2)

            max_allowed_buy = round(curr_mid + (0.20 * atr_d1), digits)
            min_allowed_sell = 0.0
            forbidden_traps = ["Do NOT short into strong open-corridor momentum"]
            confidence_score = 75
            stage_label = "BULLISH_CORRIDOR_EXPANSION"
            thesis = f"{symbol} maintaining bullish corridor expansion towards station {ceiling_station:.{digits}f}."

        calc_ms = round((time.perf_counter() - t0) * 1000, 2)

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
            future_macro_roadmap=f"Pullback to RBS {macro_rbs_d1:.{digits}f} -> Bull Flag formation -> Target {next_macro_target:.{digits}f} vs Breakdown below {macro_invalidation:.{digits}f}",
            macro_rbs_d1=macro_rbs_d1,
            macro_sbr_d1=macro_sbr_d1,
            inter_rbs_h4=inter_rbs_h4,
            inter_sbr_h4=inter_sbr_h4,
            micro_rbs_h1=micro_rbs_h1,
            micro_sbr_h1=micro_sbr_h1,
            sub_floor_50=sub_floor,
            sub_ceiling_50=sub_ceiling,
            atr_d1_pips=round(atr_d1 / pt / pip_div, 1),
            atr_h1_pips=round(atr_h1 / pt / pip_div, 1),
            atr_m30_pips=round(atr_m30 / pt / pip_div, 1),
            current_spread_pts=spread_pts,
            raw_payload={
                "symbol": symbol,
                "calculation_time_ms": calc_ms,
                "engine_token_cost": 0,
                "NARRATIVE_STORYTELLING": {
                    "macro_annual_corridor": f"Annual Range: [{d1_annual_low:.{digits}f} - {d1_annual_high:.{digits}f}] (4-Year: [{mn1_low:.{digits}f} - {mn1_high:.{digits}f}])",
                    "discovered_liquidity_sweeps": f"Equal Lows swept at {eq_low_price:.{digits}f} ({eq_low_date_str}) -> +{pips_rallied} pips",
                    "current_structural_stage": stage_label,
                    "daily_mandate_thesis": thesis,
                    "future_macro_roadmap": f"Pullback to RBS {macro_rbs_d1:.{digits}f} -> Target {next_macro_target:.{digits}f}"
                },
                "QUANT_DIRECTIVE_VALUES": {
                    "daily_macro_bias": macro_bias,
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
        return directive

    def get_directive(self, symbol: str, mt5_connector=None, force_refresh: bool = False) -> MacroStrategicDirective:
        """
        Retrieves cached directive or recomputes if missing / forced.
        """
        if not force_refresh and symbol in self._cache:
            return self._cache[symbol]
        return self.compute_directive(symbol, mt5_connector=mt5_connector)

    def refresh_all_symbols(self, symbols: List[str], mt5_connector=None) -> Dict[str, MacroStrategicDirective]:
        """
        Batch refreshes all scanner symbols in sequence (<0.5s for 27 symbols).
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
