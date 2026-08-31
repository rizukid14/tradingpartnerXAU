import os
import sys
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any, Tuple

import numpy as np  # type: ignore
import pandas as pd  # type: ignore

import config
from src.indicators.lux_smc import LuxSMCAnalyzer
from src.indicators.candle_quality import classify_candle, classify_breakout_sequence
from src.indicators.sweep_detector import detect as sweep_detect
from src.indicators.wave_regime import evaluate_wave_regime
from src.indicators.wave_state import evaluate_wave_state, WaveState, WaveStateResult
from src.indicators.atlas_dna import calculate_intraday_sl_tp, calculate_dynamic_stations, calculate_dual_grid_stations, get_symbol_step
from src.analytics.currency_strength import get_csm_delta_for_symbol, evaluate_systemic_basket_lock
from src.analytics.macro_strategic_engine import macro_strategic_engine, MacroStrategicDirective

logger = logging.getLogger("market_scanner")
WIB = ZoneInfo("Asia/Jakarta")


class Direction(Enum):
    BULL = 1
    BEAR = -1
    NEUTRAL = 0


class Phase(Enum):
    EXPANSION = 1
    EARLY_CORRECTION = 2
    MATURE_CORRECTION = 3
    RECLAIM = 4


class Permission(Enum):
    WAIT = auto()
    LOCK = auto()
    WATCH = auto()
    ARM = auto()
    GO = auto()


def resolve_permission(direction: Direction, phase: Phase, csm_delta: float = 0.0) -> Permission:
    """
    4-Layer Trend-Aligned Permission Matrix with default fallback to Permission.WAIT.
    Enforces BUY LOCKED != SELL ENABLED.
    """
    if direction == Direction.BULL:
        if phase == Phase.EXPANSION:
            return Permission.WAIT  # Don't chase top
        elif phase == Phase.EARLY_CORRECTION:
            return Permission.LOCK  # Anti-falling knife
        elif phase == Phase.MATURE_CORRECTION:
            return Permission.ARM if csm_delta >= -0.5 else Permission.WATCH
        elif phase == Phase.RECLAIM:
            return Permission.GO if csm_delta >= -1.5 else Permission.WATCH

    elif direction == Direction.BEAR:
        if phase == Phase.EXPANSION:
            return Permission.WAIT  # Don't chase bottom
        elif phase == Phase.EARLY_CORRECTION:
            return Permission.LOCK  # Anti-short squeeze
        elif phase == Phase.MATURE_CORRECTION:
            return Permission.ARM if csm_delta <= 0.5 else Permission.WATCH
        elif phase == Phase.RECLAIM:
            return Permission.GO if csm_delta <= 1.5 else Permission.WATCH

    return Permission.WAIT


def evaluate_judas_sweep_gates(
    signal_type: str,             # 'BUY' or 'SELL'
    dealing_range_pos: float,     # 0.0 (PWL) to 1.0 (PWH)
    dist_to_htf_floor: float,     # Distance in price to PWL or H4 Bullish OB
    dist_to_htf_ceiling: float,   # Distance in price to PWH or H4 Bearish OB
    atr_val: float,               # ATR H1 value
    recent_ceiling_touch: bool,   # True if price touched PWH ceiling in last 24-32h
    recent_floor_touch: bool,     # True if price touched PWL floor in last 24-32h
    close_below_ema20: bool,      # True if Close < EMA20 H1
    close_above_ema20: bool,      # True if Close > EMA20 H1
    macro_trend: str              # 'BULLISH', 'BEARISH', or 'NEUTRAL'
) -> Tuple[bool, str]:
    """
    3-Gate Hierarchical Structural Validator for LONDON_JUDAS_SWEEP.
    Eliminates 'Catching a Falling Knife' when Bearish Delivery from HTF Ceiling is active.
    
    Returns:
        (is_allowed: bool, log_reason: str)
    """
    atr_threshold = 0.35 * atr_val

    # =========================================================================
    # GATE B: Anti-Ceiling / Anti-Floor Rebound Vector (Vector Memory)
    # =========================================================================
    # 1. Bearish Delivery: Rejected PWH Ceiling & moving down below EMA20
    is_htf_bearish_delivery = recent_ceiling_touch and close_below_ema20
    if is_htf_bearish_delivery and signal_type == 'BUY':
        if dealing_range_pos > 0.20 and dist_to_htf_floor > atr_threshold:
            return False, (
                f"LOCKED BY GATE B [Anti-Ceiling Vector]: Bearish Delivery from Plafon is ACTIVE. "
                f"Asian Low break at DR {dealing_range_pos*100:.1f}% is breakdown continuation toward HTF floor."
            )

    # 2. Bullish Delivery: Bounced from PWL Floor & surging up above EMA20
    is_htf_bullish_delivery = recent_floor_touch and close_above_ema20
    if is_htf_bullish_delivery and signal_type == 'SELL':
        if dealing_range_pos < 0.80 and dist_to_htf_ceiling > atr_threshold:
            return False, (
                f"LOCKED BY GATE B [Anti-Floor Vector]: Bullish Delivery from Floor is ACTIVE. "
                f"Asian High break at DR {dealing_range_pos*100:.1f}% is breakout expansion toward HTF ceiling."
            )

    # =========================================================================
    # GATE C: Asymmetric Trend-Aligned Permission
    # =========================================================================
    if macro_trend == 'BEARISH' and signal_type == 'BUY':
        # In Bearish Macro Trend, Judas BUY is locked unless at extreme PWL floor (DR <= 0.20)
        if dealing_range_pos > 0.20 and dist_to_htf_floor > atr_threshold:
            return False, (
                f"LOCKED BY GATE C [Macro Asymmetry]: Macro trend is BEARISH. "
                f"Judas BUY locked outside extreme PWL floor (DR {dealing_range_pos*100:.1f}% > 20%)."
            )

    elif macro_trend == 'BULLISH' and signal_type == 'SELL':
        # In Bullish Macro Trend, Judas SELL is locked unless at extreme PWH ceiling (DR >= 0.80)
        if dealing_range_pos < 0.80 and dist_to_htf_ceiling > atr_threshold:
            return False, (
                f"LOCKED BY GATE C [Macro Asymmetry]: Macro trend is BULLISH. "
                f"Judas SELL locked outside extreme PWH ceiling (DR {dealing_range_pos*100:.1f}% < 80%)."
            )

    # =========================================================================
    # GATE A: HTF Anchor & Deep Discount / Extreme Premium Area of Value
    # =========================================================================
    if signal_type == 'BUY':
        is_deep_discount = dealing_range_pos <= 0.35
        is_anchored_floor = dist_to_htf_floor <= atr_threshold
        if not (is_deep_discount or is_anchored_floor):
            return False, (
                f"LOCKED BY GATE A [HTF Anchor]: Asian Low sweep at DR {dealing_range_pos*100:.1f}% "
                f"lacks HTF Support Floor (Requires Deep Discount DR <= 35% or Floor Distance <= {atr_threshold:.5f})."
            )
        return True, f"PASSED ALL GATES: Valid Judas BUY anchored at HTF Floor (DR {dealing_range_pos*100:.1f}%)."

    elif signal_type == 'SELL':
        is_extreme_premium = dealing_range_pos >= 0.65
        is_anchored_ceiling = dist_to_htf_ceiling <= atr_threshold
        if not (is_extreme_premium or is_anchored_ceiling):
            return False, (
                f"LOCKED BY GATE A [HTF Anchor]: Asian High sweep at DR {dealing_range_pos*100:.1f}% "
                f"lacks HTF Resistance Ceiling (Requires Extreme Premium DR >= 65% or Ceiling Distance <= {atr_threshold:.5f})."
            )
        return True, f"PASSED ALL GATES: Valid Judas SELL anchored at HTF Ceiling (DR {dealing_range_pos*100:.1f}%)."

    return False, "LOCKED: Default Fallback."


# Point and pip multipliers per category
POINT_MAP = {
    'XAUUSD': 0.01, 'XAUUSD-ECNc': 0.01, 'XAUUSD-ECN': 0.01,
    'USDJPY': 0.001, 'USDJPY-ECNc': 0.001, 'USDJPY-ECN': 0.001,
    'GBPJPY': 0.001, 'GBPJPY-ECNc': 0.001, 'GBPJPY-ECN': 0.001,
    'EURJPY': 0.001, 'EURJPY-ECNc': 0.001, 'EURJPY-ECN': 0.001,
    'AUDJPY': 0.001, 'AUDJPY-ECNc': 0.001, 'AUDJPY-ECN': 0.001,
    'CADJPY': 0.001, 'CADJPY-ECNc': 0.001, 'CADJPY-ECN': 0.001,
    'CHFJPY': 0.001, 'CHFJPY-ECNc': 0.001, 'CHFJPY-ECN': 0.001,
}

# Proven positive-EV pairs for Tokyo Session (08:00 - 14:00 WIB) based on 10.7-year FBS MT5 backtest
TOKYO_PROVEN_SYMBOLS = {
    'USDCAD', 'AUDCAD', 'AUDUSD', 'EURCAD', 'USDCHF',
    'GBPJPY', 'XAUUSD', 'GBPCHF', 'AUDJPY', 'CADJPY'
}

@dataclass
class CandidateSetup:
    symbol: str
    setup_type: str                  # 'UNIVERSAL_LIQUIDITY_SWEEP' (M1), 'TREND_ALIGNED_PULLBACK' (M2), 'MULTI_TOUCH_BREAKOUT_RETEST' (M3)
    direction: int                   # 1 (BUY) or -1 (SELL)
    trigger_price: float
    timeframe: str = "H1"
    macro_compass: str = ""          # e.g. "D1_BULLISH_TREND (ADX 28.4, EMA50 > EMA200)"
    dealing_range_pos: float = 0.5   # 0.0 (Deep Discount) to 1.0 (Extreme Premium)
    rejection_wick_ratio: float = 0.0 # Upper or Lower wick %
    current_spread_pts: int = 20
    current_atr_pts: float = 0.0
    key_support: float = 0.0
    key_resistance: float = 0.0
    suggested_sl: float = 0.0
    suggested_tp: float = 0.0
    risk_reward_ratio: float = 2.0
    strong_low: float = 0.0
    strong_high: float = 0.0
    bullish_ob_zone: str = ""
    bearish_ob_zone: str = ""
    fvg_zone: str = ""
    liquidity_pools: str = ""
    pdh: float = 0.0
    pdl: float = 0.0
    daily_open: float = 0.0
    adr_used_pct: float = 0.0
    h4_trend: str = ""
    d1_50_range: str = ""
    d1_100_range: str = ""
    pwh: float = 0.0
    pwl: float = 0.0
    h4_monthly_range: str = ""
    economic_context: str = ""
    frvp_confluence: str = ""
    wave_state: str = ""
    wave_summary: str = ""
    permission: str = "GO"
    csm_delta: float = 0.0
    timestamp_wib: str = ""
    action_tier: str = "FULL_ALLOW"
    macro_bias_score: float = 0.0
    regime_stability: str = "STABLE"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_payload_dict(self) -> Dict[str, Any]:
        """Convert setup to high-density JSON payload for 3-LLM Consensus Jury."""
        return {
            "event": "FAST_RADAR_TRIGGER_CONFIRMED",
            "symbol": self.symbol,
            "setup_type": self.setup_type,
            "action_tier": self.action_tier,
            "macro_bias_score": self.macro_bias_score,
            "regime_stability": self.regime_stability,
            "direction": "BUY" if self.direction == 1 else "SELL",
            "trigger_price": self.trigger_price,
            "timeframe": self.timeframe,
            "timestamp_wib": self.timestamp_wib or datetime.now(WIB).strftime("%H:%M:%S WIB"),
            "macro_compass": self.macro_compass,
            "h4_trend": self.h4_trend or "H4_CONFLUENCE_ALIGNED",
            "wave_state": self.wave_state or "BASE_RECLAIM_ENABLE",
            "wave_state_summary": self.wave_summary,
            "trade_permission": self.permission or "GO",
            "csm_net_delta": self.csm_delta,
            "previous_day_high_pdh": self.pdh,
            "previous_day_low_pdl": self.pdl,
            "previous_week_high_pwh": self.pwh,
            "previous_week_low_pwl": self.pwl,
            "daily_open": self.daily_open,
            "adr_used_pct": f"{self.adr_used_pct*100:.1f}%",
            "d1_50_day_range": self.d1_50_range,
            "d1_100_day_range": self.d1_100_range,
            "h4_monthly_range": self.h4_monthly_range,
            "dealing_range_position": f"{self.dealing_range_pos*100:.1f}% ({'DEEP DISCOUNT' if self.dealing_range_pos <= 0.38 else ('EXTREME PREMIUM' if self.dealing_range_pos >= 0.62 else 'EQUILIBRIUM')})",
            "rejection_wick_ratio": f"{self.rejection_wick_ratio*100:.1f}%",
            "current_spread_pts": self.current_spread_pts,
            "current_atr_pts": round(self.current_atr_pts, 1),
            "key_support": self.key_support,
            "key_resistance": self.key_resistance,
            "suggested_sl": self.suggested_sl,
            "suggested_tp": self.suggested_tp,
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "frvp_confluence": self.frvp_confluence or "STANDARD_LIQUIDITY",
            "economic_calendar": self.economic_context or "NO_HIGH_IMPACT_NEWS_IN_NEXT_4_HOURS",
            "daily_macro_bias": self.metadata.get("daily_macro_bias", ""),
            "primary_execution_directive": self.metadata.get("primary_execution_directive", ""),
            "macro_rbs_d1": self.metadata.get("macro_rbs_d1", 0.0),
            "macro_sbr_d1": self.metadata.get("macro_sbr_d1", 0.0),
            "micro_rbs_h1": self.metadata.get("micro_rbs_h1", 0.0),
            "micro_sbr_h1": self.metadata.get("micro_sbr_h1", 0.0),
            "sub_floor_50": self.metadata.get("sub_floor_50", 0.0),
            "sub_ceiling_50": self.metadata.get("sub_ceiling_50", 0.0),
            "forbidden_traps": self.metadata.get("forbidden_traps", []),
            "daily_mandate_thesis": self.metadata.get("daily_mandate_thesis", ""),
            "directive_for_llm": f"Evaluate macro sentiment and confirm {'BUY' if self.direction == 1 else 'SELL'} with structural SL at {self.suggested_sl} and TP at {self.suggested_tp}"
        }


class MarketScanner:
    """
    2-Stage Quant Funnel Market Scanner:
    - Stage 1A (Slow Macro Layer): Updates D1/H4 Trend Compass, Asian High/Low, and Dealing Range every hour.
    - Stage 1B (Fast Execution Radar): Scans live ticks / M5/M15 wicks across 26 symbols every 60 seconds (0 Tokens).
    """

    def __init__(self, symbols: Optional[List[str]] = None):
        self.symbols = symbols or config.get_scanner_symbols()
        self.macro_cache: Dict[str, Dict[str, Any]] = {}
        self.last_macro_update: Optional[datetime] = None
        self.last_candidates: List[CandidateSetup] = []
        self._last_radar_scan_time: float = 0.0
        self._symbol_last_trigger: Dict[str, float] = {}
        self._direction_states: Dict[str, Dict[str, Any]] = {}
        self._phase_states: Dict[str, Dict[str, Any]] = {}

    def mark_symbol_cancelled(self, symbol: str, cooldown_seconds: int = 1800):
        """Applies a 30-minute cooldown when a pending order is cancelled or expired."""
        clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
        now_ts = time.time()
        # Cooldown check in scan_fast_radar is `now_ts - last_trigger < 900`.
        # Setting timestamp to now_ts + (cooldown_seconds - 900) ensures cooldown duration of cooldown_seconds.
        self._symbol_last_trigger[clean_sym] = now_ts + max(0, cooldown_seconds - 900)
        logger.info(f"⏳ Cooldown {cooldown_seconds // 60}m diaktifkan untuk {clean_sym} (Pending Cancelled/Expired).")

    def _get_point(self, symbol: str) -> float:
        try:
            if hasattr(config.mt5, "symbol_info"):
                si = config.mt5.symbol_info(symbol)
                if si is not None and getattr(si, "point", 0.0) > 0:
                    return float(si.point)
        except Exception:
            pass
        clean = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
        if clean in POINT_MAP:
            return POINT_MAP[clean]
        if "JPY" in clean:
            return 0.001
        if "XAU" in clean or "GOLD" in clean or "BTC" in clean:
            return 0.01
        return 1e-5

    @staticmethod
    def is_symbol_allowed_for_session(symbol: str, hour_wib: int) -> bool:
        """
        Filters symbols based on empirical expected value (EV) per trading session.
        - Tokyo Session (08:00 - 14:00 WIB): Only allow proven positive-EV pairs (Asia/Commodities).
        - London & NY Sessions (14:00 - 23:59 WIB): Allow all configured 26 pairs.
        """
        clean_sym = symbol.replace('-ECNc', '').replace('-ECN', '').replace('.c', '').replace('m', '').replace('_', '')
        if 8 <= hour_wib < 14:
            return clean_sym in TOKYO_PROVEN_SYMBOLS
        elif 14 <= hour_wib <= 23:
            return True
        return False

    def _evaluate_live_candle_quality(self, sym: str, mid: float, atr_pts: float, pt: float, mt5_connector=None) -> Dict[str, Any]:
        """
        Fetches recent M15/M30/H1 rates and calculates live & recent candle quality:
        body_ratio, lower_wick_pct, upper_wick_pct, velocity_atr, verdict, sweep_side, is_bullish_engulf, is_bearish_engulf.
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
        }
        
        rates = None
        tf = getattr(config.mt5, 'TIMEFRAME_M15', 15)
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
            
            max_lw = max(live_qual['lower_wick_pct'], prev_qual['lower_wick_pct'])
            max_uw = max(live_qual['upper_wick_pct'], prev_qual['upper_wick_pct'])
            
            return {
                "body_ratio": live_qual['body_ratio'],
                "upper_wick_pct": live_qual['upper_wick_pct'],
                "lower_wick_pct": live_qual['lower_wick_pct'],
                "velocity_atr": live_qual['velocity_atr'],
                "direction": live_qual['direction'],
                "verdict": live_qual['verdict'],
                "sweep_side": live_qual['sweep_side'] or prev_qual['sweep_side'],
                "max_lower_wick": round(max_lw, 3),
                "max_upper_wick": round(max_uw, 3),
                "is_bullish_engulf": live_qual['is_bullish_engulf'],
                "is_bearish_engulf": live_qual['is_bearish_engulf'],
                "prev_verdict": prev_qual['verdict'],
                "prev_direction": prev_qual['direction'],
                "live_high": cur_h,
                "live_low": cur_l,
            }
        except Exception as e:
            logger.debug(f"Error classifying candle for {sym}: {e}")
            return default_res

    def update_macro_context(self, mt5_connector=None, force: bool = False) -> None:
        """
        Updates multi-timeframe macro indicators (D1 Trend, H4 Order Blocks, Asian Range, 100-bar Dealing Range).
        Cached and refreshed every hour or when force=True.
        """
        now = datetime.now(WIB)
        if not force and self.last_macro_update is not None:
            # Only refresh if new hour has arrived
            if self.last_macro_update.hour == now.hour and self.last_macro_update.date() == now.date():
                return

        logger.info(f"🔄 Updating Macro Context Layer for {len(self.symbols)} symbols (Hour: {now.hour}:00 WIB)...")
        
        for sym in self.symbols:
            try:
                # Auto-resolve valid broker symbol & ensure visible in MT5 Market Watch
                valid_sym = sym
                if mt5_connector is not None and hasattr(mt5_connector, 'get_valid_trade_symbol'):
                    valid_sym = mt5_connector.get_valid_trade_symbol(sym)
                
                if hasattr(config.mt5, 'symbol_select'):
                    config.mt5.symbol_select(valid_sym, True)

                # ── FETCH DISCRETE DATA: H1 (120 bars), D1 (100 bars), H4 (120 bars), W1 (52 bars) ──
                rates_h1 = None
                rates_d1 = None
                rates_h4 = None
                rates_w1 = None
                if hasattr(config.mt5, 'copy_rates_from_pos'):
                    rates_h1 = config.mt5.copy_rates_from_pos(valid_sym, config.mt5.TIMEFRAME_H1, 0, 120)
                    rates_d1 = config.mt5.copy_rates_from_pos(valid_sym, config.mt5.TIMEFRAME_D1, 0, 100)
                    rates_h4 = config.mt5.copy_rates_from_pos(valid_sym, config.mt5.TIMEFRAME_H4, 0, 120)
                    rates_w1 = config.mt5.copy_rates_from_pos(valid_sym, getattr(config.mt5, 'TIMEFRAME_W1', 32769), 0, 52)

                if (rates_h1 is None or len(rates_h1) < 30) and mt5_connector is not None and hasattr(mt5_connector, 'get_closed_bars'):
                    rates_h1 = mt5_connector.get_closed_bars(valid_sym, count=120, timeframe=getattr(config.mt5, 'TIMEFRAME_H1', 16385))
                if (rates_d1 is None or len(rates_d1) < 2) and mt5_connector is not None and hasattr(mt5_connector, 'get_closed_bars'):
                    rates_d1 = mt5_connector.get_closed_bars(valid_sym, count=100, timeframe=getattr(config.mt5, 'TIMEFRAME_D1', 16408))
                if (rates_h4 is None or len(rates_h4) < 5) and mt5_connector is not None and hasattr(mt5_connector, 'get_closed_bars'):
                    rates_h4 = mt5_connector.get_closed_bars(valid_sym, count=120, timeframe=getattr(config.mt5, 'TIMEFRAME_H4', 16388))
                if (rates_w1 is None or len(rates_w1) < 2) and mt5_connector is not None and hasattr(mt5_connector, 'get_closed_bars'):
                    rates_w1 = mt5_connector.get_closed_bars(valid_sym, count=52, timeframe=getattr(config.mt5, 'TIMEFRAME_W1', 32769))

                if rates_h1 is None or len(rates_h1) < 30:
                    continue

                df = pd.DataFrame(rates_h1)
                if 'time' in df.columns:
                    if not pd.api.types.is_datetime64_any_dtype(df['time']):
                        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True).dt.tz_convert(WIB)
                    df.set_index('time', inplace=True)

                pt = self._get_point(valid_sym)
                cur_close = df['close'].iloc[-1]

                # ── 0. W1 WEEKLY CHART DIRECT PROCESSING (52-week context, PWH, PWL, PWC) ──
                pwh = cur_close + (500 * pt)
                pwl = cur_close - (500 * pt)
                pwc = cur_close
                w1_50_eq = cur_close
                w1_trend_label = "W1_SIDEWAYS"
                w1_is_bull = False
                w1_is_bear = False

                if rates_w1 is not None and len(rates_w1) >= 2:
                    df_w1 = pd.DataFrame(rates_w1)
                    pwh = float(df_w1['high'].iloc[-2])
                    pwl = float(df_w1['low'].iloc[-2])
                    pwc = float(df_w1['close'].iloc[-2])
                    w1_rng = max(pwh - pwl, 1e-5)
                    w1_50_eq = pwl + 0.50 * w1_rng
                    w1_c = float(df_w1['close'].iloc[-1])
                    w1_ema20 = float(df_w1['close'].ewm(span=20, adjust=False).mean().iloc[-1]) if len(df_w1) >= 20 else w1_50_eq
                    w1_is_bull = w1_c > w1_ema20
                    w1_is_bear = w1_c < w1_ema20
                    w1_trend_label = "W1_BULLISH" if w1_is_bull else ("W1_BEARISH" if w1_is_bear else "W1_SIDEWAYS")

                # ── 1. D1 DISCRETE LEVEL & ANCHOR-BASED STRUCTURAL TREND ──
                pdh = cur_close + (300 * pt)
                pdl = cur_close - (300 * pt)
                daily_open = df['open'].iloc[0]
                adr20 = 500 * pt
                d1_is_bull = False
                d1_is_bear = False
                d1_trend_label = "D1_SIDEWAYS_RANGE"
                d1_50_range_str = f"[{pdl:.5f} - {pdh:.5f}]"
                d1_100_range_str = f"[{pdl:.5f} - {pdh:.5f}]"
                d1_anchor_low = pdl
                d1_anchor_high = pdh

                if rates_d1 is not None and len(rates_d1) >= 2:
                    df_d1 = pd.DataFrame(rates_d1)
                    pdh = float(df_d1['high'].iloc[-2])
                    pdl = float(df_d1['low'].iloc[-2])
                    daily_open = float(df_d1['open'].iloc[-1])
                    d_ranges = df_d1['high'] - df_d1['low']
                    adr20 = float(d_ranges.tail(20).mean()) if len(d_ranges) >= 10 else (500 * pt)
                    
                    d1_50_hi = float(df_d1['high'].tail(50).max())
                    d1_50_lo = float(df_d1['low'].tail(50).min())
                    d1_50_range_str = f"[{d1_50_lo:.5f} - {d1_50_hi:.5f}]"

                    d1_100_hi = float(df_d1['high'].tail(100).max())
                    d1_100_lo = float(df_d1['low'].tail(100).min())
                    d1_100_range_str = f"[{d1_100_lo:.5f} - {d1_100_hi:.5f}]"
                    
                    d1_c = float(df_d1['close'].iloc[-1])
                    d1_ema_short = df_d1['close'].ewm(span=20, adjust=False).mean().iloc[-1]
                    d1_ema_long = df_d1['close'].ewm(span=50, adjust=False).mean().iloc[-1] if len(df_d1) >= 30 else d1_ema_short
                    
                    # SMC Structural Anchor on D1
                    if len(df_d1) >= 20:
                        d1_smc = LuxSMCAnalyzer(swing_length=3).analyze(df_d1, point_size=pt)
                        d1_anchor_low = d1_smc.strong_low if d1_smc.strong_low > 0 else d1_50_lo
                        d1_anchor_high = d1_smc.strong_high if d1_smc.strong_high > 0 else d1_50_hi
                        d1_is_bull = (d1_c > d1_anchor_low) and (d1_c > d1_ema_long or d1_ema_short > d1_ema_long)
                        d1_is_bear = (d1_c < d1_anchor_high) and (d1_c < d1_ema_long or d1_ema_short < d1_ema_long)
                    else:
                        d1_is_bull = d1_c > d1_ema_long and d1_ema_short > d1_ema_long
                        d1_is_bear = d1_c < d1_ema_long and d1_ema_short < d1_ema_long
                        
                    d1_trend_label = "D1_BULLISH_EXPANSION" if d1_is_bull else ("D1_BEARISH_EXPANSION" if d1_is_bear else "D1_SIDEWAYS")

                cur_day_move = abs(cur_close - daily_open)
                adr_used_pct = (cur_day_move / adr20) if (adr20 > 0) else 0.5

                # ── 2. H4 DISCRETE LEVEL, SMC SWING ANCHOR & MONTHLY RANGE ──
                h4_is_bull = False
                h4_is_bear = False
                h4_trend_label = "H4_SIDEWAYS"
                h4_swing_high = pdh
                h4_swing_low = pdl
                h4_monthly_range_str = f"[{pdl:.5f} - {pdh:.5f}]"

                if rates_h4 is not None and len(rates_h4) >= 5:
                    df_h4 = pd.DataFrame(rates_h4)
                    h4_c = float(df_h4['close'].iloc[-1])
                    h4_ema20 = df_h4['close'].ewm(span=20, adjust=False).mean().iloc[-1]
                    h4_ema50 = df_h4['close'].ewm(span=50, adjust=False).mean().iloc[-1] if len(df_h4) >= 15 else h4_ema20
                    
                    if len(df_h4) >= 25:
                        h4_smc = LuxSMCAnalyzer(swing_length=5).analyze(df_h4, point_size=pt)
                        h4_swing_high = h4_smc.strong_high if h4_smc.strong_high > 0 else float(df_h4['high'].iloc[-12:].max())
                        h4_swing_low = h4_smc.strong_low if h4_smc.strong_low > 0 else float(df_h4['low'].iloc[-12:].min())
                        h4_is_bull = (h4_c > h4_swing_low) and (h4_c > h4_ema20 or h4_ema20 >= h4_ema50)
                        h4_is_bear = (h4_c < h4_swing_high) and (h4_c < h4_ema20 or h4_ema20 <= h4_ema50)
                    else:
                        h4_swing_high = float(df_h4['high'].iloc[-6:].max())
                        h4_swing_low = float(df_h4['low'].iloc[-6:].min())
                        h4_is_bull = h4_c > h4_ema20 and h4_ema20 >= h4_ema50
                        h4_is_bear = h4_c < h4_ema20 and h4_ema20 <= h4_ema50
                        
                    h4_trend_label = "H4_BULLISH_EXPANSION" if h4_is_bull else ("H4_BEARISH_EXPANSION" if h4_is_bear else "H4_PULLBACK_RANGE")

                    # Monthly H4 Range (120 bars)
                    h4_m_hi = float(df_h4['high'].max())
                    h4_m_lo = float(df_h4['low'].min())
                    h4_monthly_range_str = f"[{h4_m_lo:.5f} - {h4_m_hi:.5f}]"

                # ── 3. H1 INDICATORS & DEALING RANGE ──
                df['atr'] = self._calc_atr(df, 14)
                df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
                df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
                df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

                cur_ema20 = df['ema20'].iloc[-1]
                cur_ema50 = df['ema50'].iloc[-1]
                cur_ema200 = df['ema200'].iloc[-1]
                cur_atr = df['atr'].iloc[-1] if pd.notna(df['atr'].iloc[-1]) else (300 * pt)

                sess_h = df['high'].rolling(100, min_periods=20).max().iloc[-1]
                sess_l = df['low'].rolling(100, min_periods=20).min().iloc[-1]
                rng = max(sess_h - sess_l, 1e-5)
                pos_in_range = (cur_close - sess_l) / rng

                combined_trend_label = f"{d1_trend_label} | {h4_trend_label}"

                # Asian Session Range (08:00 - 13:00 WIB)
                h = df.index.hour
                is_asian = (h >= 8) & (h <= 13)
                asian_bars = df[is_asian]
                if len(asian_bars) > 0:
                    last_asian_date = asian_bars.index[-1].date()
                    today_asian = asian_bars[asian_bars.index.date == last_asian_date]
                    asian_high = today_asian['high'].max() if len(today_asian) else sess_h
                    asian_low = today_asian['low'].min() if len(today_asian) else sess_l
                else:
                    asian_high = sess_h
                    asian_low = sess_l

                # ADR (20-day)
                adr_pct = adr_used_pct

                # ── LUXALGO SMC STRUCTURAL SCANNER (Order Blocks, FVG, Strong/Weak) ──
                smc_analyzer = LuxSMCAnalyzer(swing_length=5)
                smc_sig = smc_analyzer.analyze(df, point_size=pt)

                cur_atr = df['atr'].iloc[-1] if ('atr' in df.columns and pd.notna(df['atr'].iloc[-1])) else (300 * pt)
                max_ob_dist = cur_atr * 1.5

                bull_ob_str = ""
                if smc_sig.order_blocks_bullish:
                    nearby_bull_obs = [ob for ob in smc_sig.order_blocks_bullish if abs(cur_close - ob['top']) <= max_ob_dist]
                    if nearby_bull_obs:
                        lob = nearby_bull_obs[-1]
                        rating_tag = f" [{lob.get('frvp_rating', 'B')} - POC: {lob.get('poc', 0.0):.5f}]" if lob.get('poc_confluence') or lob.get('va_discount') else ""
                        bull_ob_str = f"[{lob['bottom']:.5f} - {lob['top']:.5f}]{rating_tag} (Unmitigated)"

                bear_ob_str = ""
                if smc_sig.order_blocks_bearish:
                    nearby_bear_obs = [ob for ob in smc_sig.order_blocks_bearish if abs(ob['bottom'] - cur_close) <= max_ob_dist]
                    if nearby_bear_obs:
                        lob = nearby_bear_obs[-1]
                        rating_tag = f" [{lob.get('frvp_rating', 'B')} - POC: {lob.get('poc', 0.0):.5f}]" if lob.get('poc_confluence') or lob.get('va_discount') else ""
                        bear_ob_str = f"[{lob['bottom']:.5f} - {lob['top']:.5f}]{rating_tag} (Unmitigated)"

                fvg_str = ""
                active_fvgs = smc_sig.fvg_bullish + smc_sig.fvg_bearish
                if active_fvgs:
                    lfvg = active_fvgs[-1]
                    fvg_str = f"[{lfvg['bottom']:.5f} - {lfvg['top']:.5f}] ({lfvg['direction'].upper()} Imbalance)"

                liq_str = ""
                if smc_sig.equal_highs:
                    liq_str += f"EQH @ {smc_sig.equal_highs[-1]['price']:.5f} "
                if smc_sig.equal_lows:
                    liq_str += f"EQL @ {smc_sig.equal_lows[-1]['price']:.5f}"
                liq_str = liq_str.strip()

                frvp_summary_str = ""
                if smc_sig.active_frvp:
                    af = smc_sig.active_frvp
                    poc_val = af.get('poc', 0.0)
                    val_val = af.get('val', 0.0)
                    vah_val = af.get('vah', 0.0)
                    cur_atr_safe = max(cur_atr, 1e-5)
                    mid_px = float(df['close'].iloc[-1]) if len(df) > 0 else 0.0
                    loc_note = "At POC High Volume Node" if abs(mid_px - poc_val) <= 0.15 * cur_atr_safe else (
                        "Inside Value Area (VAH-VAL)" if val_val <= mid_px <= vah_val else (
                            "Above Value Area (Extreme Premium VAH Extension)" if mid_px > vah_val else "Below Value Area (Discount VAL)"
                        )
                    )
                    frvp_summary_str = f"POC: {poc_val:.5f} | VAL: {val_val:.5f} | VAH: {vah_val:.5f} ({loc_note})"

                # ── H1 CLUSTER ZONE & MULTI-TOUCH CALCULATION (40 bars) ──
                lb_bars = min(40, len(df))
                recent_h = df['high'].iloc[-lb_bars:].tolist()
                recent_l = df['low'].iloc[-lb_bars:].tolist()
                recent_c = df['close'].iloc[-lb_bars:].tolist()
                recent_o = df['open'].iloc[-lb_bars:].tolist()
                cur_atr = df['atr'].iloc[-1] if pd.notna(df['atr'].iloc[-1]) else (300 * pt)

                ref_hi = float(max(recent_h))
                tol_clust = cur_atr * 0.50

                cluster_hi = [x for x in recent_h if abs(x - ref_hi) <= tol_clust]
                cluster_res = float(np.median(cluster_hi)) if cluster_hi else ref_hi
                touches_res = sum(1 for h_val, l_val in zip(recent_h[:-1], recent_l[:-1]) if (cluster_res - tol_clust) <= h_val <= (cluster_res + tol_clust * 1.5))

                ref_lo = float(min(recent_l))
                cluster_lo = [x for x in recent_l if abs(x - ref_lo) <= tol_clust]
                cluster_sup = float(np.median(cluster_lo)) if cluster_lo else ref_lo
                touches_sup = sum(1 for h_val, l_val in zip(recent_h[:-1], recent_l[:-1]) if (cluster_sup - tol_clust * 1.5) <= l_val <= (cluster_sup + tol_clust))

                # Wave Regime & Range Age
                regime_res = evaluate_wave_regime(recent_h, recent_l, recent_c, timeframe_hours=1.0, dealing_range_window=lb_bars)

                # CSM Net Delta for Symbol
                csm_delta_val = get_csm_delta_for_symbol(valid_sym)

                # ── 1. TOP-DOWN LAYER 1: PURE QUANT MACRO STRATEGIC ENGINE (MSE 6-TF) ──
                strat_dir = None
                try:
                    strat_dir = macro_strategic_engine.get_directive(valid_sym, mt5_connector=mt5_connector)
                except Exception as e_strat:
                    logger.debug(f"[STRAT ENGINE] Error computing directive for {valid_sym}: {e_strat}")

                # Resolusi Arah Tunggal dari MSE 6-TF (Single Source of Macro Truth)
                if strat_dir is not None:
                    prim_dir = getattr(strat_dir, 'primary_execution_directive', '')
                    bias_sc = getattr(strat_dir, 'macro_bias_score', 0.0)
                    if "HUNT_BUY" in prim_dir or bias_sc >= 0.35:
                        raw_dir = Direction.BULL
                    elif "HUNT_SELL" in prim_dir or bias_sc <= -0.35:
                        raw_dir = Direction.BEAR
                    else:
                        raw_dir = Direction.NEUTRAL
                else:
                    # Fallback jika MSE data kosong
                    raw_dir = Direction.BULL if (d1_is_bull and (h4_is_bull or (h4_c >= h4_ema50 if 'h4_c' in locals() else True))) else (
                        Direction.BEAR if (d1_is_bear and (h4_is_bear or (h4_c <= h4_ema50 if 'h4_c' in locals() else True))) else Direction.NEUTRAL
                    )

                dir_tracker = self._direction_states.setdefault(valid_sym, {"state": raw_dir, "pending": raw_dir, "confirm": 2})
                if raw_dir == dir_tracker["pending"]:
                    dir_tracker["confirm"] += 1
                    if dir_tracker["confirm"] >= 2:
                        dir_tracker["state"] = raw_dir
                else:
                    dir_tracker["pending"] = raw_dir
                    dir_tracker["confirm"] = 1
                curr_direction = dir_tracker["state"]

                # ── 2. TOP-DOWN LAYER 2: SYMMETRICAL WAVE STATE & PHASE FSM (H1 + CSM) ──
                mse_trend_dir = 1 if curr_direction == Direction.BULL else (-1 if curr_direction == Direction.BEAR else 0)
                wave_res = evaluate_wave_state(
                    df,
                    h4_trend_direction=mse_trend_dir,
                    current_price=cur_close,
                    atr_pts=(cur_atr / pt) if pd.notna(cur_atr) else 300,
                    point_val=pt,
                    csm_delta=csm_delta_val,
                    symbol=valid_sym,
                    pwh=pwh,
                    pwl=pwl,
                    macro_high=d1_anchor_high,
                    macro_low=d1_anchor_low
                )

                # Phase FSM: Retracement & Basing evaluation aligned with MSE direction
                curr_bar_range = max(df['high'].iloc[-1] - df['low'].iloc[-1], 1e-5)
                l_wick = max(0.0, min(df['open'].iloc[-1], cur_close) - df['low'].iloc[-1])
                u_wick = max(0.0, df['high'].iloc[-1] - max(df['open'].iloc[-1], cur_close))
                l_wick_ratio = l_wick / curr_bar_range
                u_wick_ratio = u_wick / curr_bar_range
                dist_ema_atr = (cur_close - cur_ema20) / (cur_atr if cur_atr > 0 else 1e-5)

                raw_phase = Phase.EXPANSION
                if curr_direction == Direction.BULL:
                    if dist_ema_atr > 0.90 and pos_in_range > 0.65:
                        raw_phase = Phase.EXPANSION
                    elif dist_ema_atr <= 0.60:
                        if pos_in_range <= 0.50:
                            if l_wick_ratio >= 0.20 or cur_close > cur_ema20:
                                raw_phase = Phase.RECLAIM
                            else:
                                raw_phase = Phase.MATURE_CORRECTION
                        else:
                            raw_phase = Phase.EARLY_CORRECTION
                elif curr_direction == Direction.BEAR:
                    if dist_ema_atr < -0.90 and pos_in_range < 0.35:
                        raw_phase = Phase.EXPANSION
                    elif dist_ema_atr >= -0.60:
                        if pos_in_range >= 0.50:
                            if u_wick_ratio >= 0.20 or cur_close < cur_ema20:
                                raw_phase = Phase.RECLAIM
                            else:
                                raw_phase = Phase.MATURE_CORRECTION
                        else:
                            raw_phase = Phase.EARLY_CORRECTION

                phase_tracker = self._phase_states.setdefault(valid_sym, {"state": raw_phase, "pending": raw_phase, "confirm": 2})
                if raw_phase == phase_tracker["pending"]:
                    phase_tracker["confirm"] += 1
                    if phase_tracker["confirm"] >= 2:
                        phase_tracker["state"] = raw_phase
                else:
                    phase_tracker["pending"] = raw_phase
                    phase_tracker["confirm"] = 1
                curr_phase = phase_tracker["state"]

                # HTF Delivery Vector Memory (Gate B for Judas Sweep)
                recent_ceiling_touch = False
                recent_floor_touch = False
                if pwh > 0 and pwl > 0:
                    h4_tail_hi = float(df_h4['high'].iloc[-8:].max()) if (rates_h4 is not None and len(df_h4) >= 8) else float(df['high'].iloc[-24:].max())
                    h4_tail_lo = float(df_h4['low'].iloc[-8:].min()) if (rates_h4 is not None and len(df_h4) >= 8) else float(df['low'].iloc[-24:].min())
                    recent_ceiling_touch = (h4_tail_hi >= (pwh - (cur_atr * 0.25))) or (pos_in_range >= 0.85)
                    recent_floor_touch = (h4_tail_lo <= (pwl + (cur_atr * 0.25))) or (pos_in_range <= 0.15)

                htf_delivery = "NEUTRAL"
                if recent_ceiling_touch and cur_close < cur_ema20:
                    htf_delivery = "BEARISH_DELIVERY_FROM_CEILING"
                elif recent_floor_touch and cur_close > cur_ema20:
                    htf_delivery = "BULLISH_DELIVERY_FROM_FLOOR"

                # Layer 3 & 4: CSM Pressure & Permission Matrix
                perm = resolve_permission(curr_direction, curr_phase, csm_delta_val)

                self.macro_cache[valid_sym] = {
                    'symbol': valid_sym,
                    'trend_label': combined_trend_label,
                    'w1_trend_label': w1_trend_label,
                    'd1_trend_label': d1_trend_label,
                    'h4_trend_label': h4_trend_label,
                    'is_d1_bull': d1_is_bull,
                    'is_d1_bear': d1_is_bear,
                    'is_h4_bull': h4_is_bull,
                    'is_h4_bear': h4_is_bear,
                    'is_bull': d1_is_bull,
                    'is_bear': d1_is_bear,
                    'direction_state': curr_direction.name,
                    'phase_state': curr_phase.name,
                    'permission_state': perm.name,
                    'csm_delta': csm_delta_val,
                    'recent_ceiling_touch': recent_ceiling_touch,
                    'recent_floor_touch': recent_floor_touch,
                    'htf_delivery': htf_delivery,
                    'pdh': pdh,
                    'pdl': pdl,
                    'daily_open': daily_open,
                    'adr_used_pct': adr_used_pct,
                    'd1_50_range': d1_50_range_str,
                    'd1_100_range': d1_100_range_str,
                    'd1_anchor_low': d1_anchor_low,
                    'd1_anchor_high': d1_anchor_high,
                    'pwh': pwh,
                    'pwl': pwl,
                    'pwc': pwc,
                    'w1_50_eq': w1_50_eq,
                    'h4_monthly_range': h4_monthly_range_str,
                    'h4_swing_high': h4_swing_high,
                    'h4_swing_low': h4_swing_low,
                    'ema20': cur_ema20,
                    'ema50': cur_ema50,
                    'ema200': cur_ema200,
                    'atr_pts': (cur_atr / pt) if pd.notna(cur_atr) else 300,
                    'dealing_range_high': sess_h,
                    'dealing_range_low': sess_l,
                    'dealing_range_pos': pos_in_range,
                    'asian_high': asian_high,
                    'asian_low': asian_low,
                    'adr_pct': adr_pct,
                    'adr20_pts': (adr20 / pt) if (pd.notna(adr20) and adr20 > 0) else 500,
                    'strong_high': smc_sig.strong_high,
                    'strong_low': smc_sig.strong_low,
                    'bullish_ob_zone': bull_ob_str,
                    'bearish_ob_zone': bear_ob_str,
                    'fvg_zone': fvg_str,
                    'liquidity_pools': liq_str,
                    'frvp_summary': frvp_summary_str,
                    'cluster_resistance': cluster_res,
                    'cluster_support': cluster_sup,
                    'touches_resistance': touches_res,
                    'touches_support': touches_sup,
                    'range_age_hours': regime_res.get('range_age_hours', 24.0),
                    'effective_sqz_bars': regime_res.get('effective_sqz_bars', 0),
                    'wave_regime_name': regime_res.get('regime', 'YOUNG_OSCILLATION'),
                    'wave_state': wave_res.state,
                    'permission_v3': wave_res.permission,
                    'correction_type': wave_res.correction_type,
                    'is_reclaim_confirmed': wave_res.is_reclaim_confirmed,
                    'overlap_ratio': wave_res.overlap_ratio,
                    'correction_velocity': wave_res.correction_velocity,
                    'body_efficiency': wave_res.body_efficiency,
                    'wave_permitted': (perm in (Permission.GO, Permission.ARM)),
                    'wave_summary': f"[{curr_direction.name} | {curr_phase.name} | {wave_res.correction_type} | CSM {csm_delta_val:+.2f}] -> {wave_res.permission}",
                    'wave_pullback_atr': wave_res.pullback_depth_atr,
                    'wave_zigzag_legs': wave_res.bars_since_pivot,
                    'macro_corridor': wave_res.macro_corridor,
                    'target_station': wave_res.target_station,
                    'psych_step': wave_res.psych_step,
                    'is_ceiling_rejected': wave_res.is_ceiling_rejected,
                    'is_floor_rejected': wave_res.is_floor_rejected,
                    # Macro Strategic Directive Fields
                    'strat_dir': strat_dir,
                    'daily_macro_bias': getattr(strat_dir, 'daily_macro_bias', 'RANGE_BOUND') if strat_dir else 'RANGE_BOUND',
                    'macro_bias_score': getattr(strat_dir, 'macro_bias_score', 0.0) if strat_dir else 0.0,
                    'regime_stability': getattr(strat_dir, 'regime_stability', 'STABLE') if strat_dir else 'STABLE',
                    'hard_circuit_breaker': getattr(strat_dir, 'hard_circuit_breaker', False) if strat_dir else False,
                    'action_tier': getattr(strat_dir, 'action_tier', 'WATCH_ONLY') if strat_dir else 'WATCH_ONLY',
                    'primary_execution_directive': getattr(strat_dir, 'primary_execution_directive', 'FADE_CORRIDOR_EXTREMES') if strat_dir else 'FADE_CORRIDOR_EXTREMES',
                    'macro_rbs_d1': getattr(strat_dir, 'macro_rbs_d1', 0.0) if strat_dir else 0.0,
                    'macro_sbr_d1': getattr(strat_dir, 'macro_sbr_d1', 0.0) if strat_dir else 0.0,
                    'inter_rbs_h4': getattr(strat_dir, 'inter_rbs_h4', 0.0) if strat_dir else 0.0,
                    'inter_sbr_h4': getattr(strat_dir, 'inter_sbr_h4', 0.0) if strat_dir else 0.0,
                    'micro_rbs_h1': getattr(strat_dir, 'micro_rbs_h1', 0.0) if strat_dir else 0.0,
                    'micro_sbr_h1': getattr(strat_dir, 'micro_sbr_h1', 0.0) if strat_dir else 0.0,
                    'sub_floor_50': getattr(strat_dir, 'sub_floor_50', 0.0) if strat_dir else 0.0,
                    'sub_ceiling_50': getattr(strat_dir, 'sub_ceiling_50', 0.0) if strat_dir else 0.0,
                    'entry_limit_anchor': getattr(strat_dir, 'entry_limit_anchor', 0.0) if strat_dir else 0.0,
                    'intraday_sl_price': getattr(strat_dir, 'intraday_sl_price', 0.0) if strat_dir else 0.0,
                    'tp1_price': getattr(strat_dir, 'tp1_price', 0.0) if strat_dir else 0.0,
                    'tp2_price': getattr(strat_dir, 'tp2_price', 0.0) if strat_dir else 0.0,
                    'forbidden_traps': getattr(strat_dir, 'forbidden_traps', []) if strat_dir else [],
                    'daily_mandate_thesis': getattr(strat_dir, 'daily_mandate_thesis', '') if strat_dir else '',
                    'structural_stage': getattr(strat_dir, 'structural_stage', '') if strat_dir else '',
                    'strategic_raw_payload': getattr(strat_dir, 'raw_payload', {}) if strat_dir else {},
                    'point': pt,
                    'last_update': now
                }
            except Exception as e:
                logger.warning(f"Error updating macro context for {sym}: {e}")

        self.last_macro_update = now
        logger.info(f"✅ Macro Context Layer updated for {len(self.macro_cache)}/{len(self.symbols)} symbols.")

    def scan_fast_radar(self, mt5_connector=None) -> List[CandidateSetup]:
        """
        Fast Execution Radar: Runs every 60 seconds across 26 symbols.
        Checks live tick / M5-M15 wicks against cached macro levels.
        Returns list of qualifying CandidateSetup objects (0 Tokens).
        """
        now = datetime.now(WIB)
        h = now.hour
        dow = now.weekday()
        
        # Dead Zone / Weekend Filter (00:00 - 08:00 WIB weekday, full block Sabtu-Minggu)
        # FIX 29 Agu: weekend = Sabtu (5) + Minggu (6), cutoff Sabtu 00:00 (bukan Jumat 22:00).
        if dow in (5, 6) or (0 <= h < 8):
            return []

        # Ensure macro cache is initialized
        if not self.macro_cache or (self.last_macro_update and (now - self.last_macro_update).total_seconds() > 3600):
            self.update_macro_context(mt5_connector=mt5_connector)

        candidates: List[CandidateSetup] = []
        is_london_open = (14 <= h <= 18)
        is_ny_session = (19 <= h <= 23)

        # ── SHARED AGGREGATE CAPACITY GATE (Max 6 Total Active Positions + Pending Orders) ──
        positions = config.mt5.positions_get() if hasattr(config.mt5, "positions_get") else []
        orders = config.mt5.orders_get() if hasattr(config.mt5, "orders_get") else []
        
        # Max capacity gate: If total open + pending orders on MT5 account >= max_positions (6), FREEZE radar
        total_active = len(positions or []) + len(orders or [])
        max_positions = config.get_max_open_positions()
        if total_active >= max_positions:
            return []

        active_symbols = set()
        for p in (positions or []):
            active_symbols.add(getattr(p, 'symbol', '').replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper())
        for o in (orders or []):
            active_symbols.add(getattr(o, 'symbol', '').replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper())

        now_ts = time.time()

        for sym, macro in self.macro_cache.items():
            clean_sym = sym.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").upper()
            
            # Anti-Duplicate: Skip if symbol already has active position or pending order!
            if clean_sym in active_symbols:
                continue

            # Per-Symbol Cooldown: Min 15 minutes between LLM Jury evaluations for the same symbol
            if (now_ts - self._symbol_last_trigger.get(clean_sym, 0.0)) < 900:
                continue

            try:
                # Get live tick
                tick = None
                if mt5_connector is not None and hasattr(mt5_connector, 'get_current_tick'):
                    tick = mt5_connector.get_current_tick(sym)
                elif mt5_connector is not None and hasattr(mt5_connector, 'get_live_tick'):
                    tick = mt5_connector.get_live_tick(sym)
                elif hasattr(config.mt5, 'symbol_info_tick'):
                    tick = config.mt5.symbol_info_tick(sym)
                
                if tick is None:
                    continue

                ask = getattr(tick, 'ask', 0.0) if hasattr(tick, 'ask') else (tick.get('ask', 0.0) if isinstance(tick, dict) else 0.0)
                bid = getattr(tick, 'bid', 0.0) if hasattr(tick, 'bid') else (tick.get('bid', 0.0) if isinstance(tick, dict) else 0.0)
                if ask <= 0 or bid <= 0: continue

                mid = (ask + bid) / 2.0
                pt = macro['point']
                spread_pts = int(round(abs(ask - bid) / pt))
                atr_pts = macro['atr_pts']

                # Evaluate live candle quality for real wick measurement & waterfall detection
                c_qual = self._evaluate_live_candle_quality(sym, mid, atr_pts, pt, mt5_connector=mt5_connector)
                live_h = c_qual.get('live_high', max(ask, mid))
                live_l = c_qual.get('live_low', min(bid, mid))

                # ── 4-LAYER TRADE PERMISSION GATE (Lock / Wait Enforcement) ──
                perm_state = macro.get('permission_state', 'GO')
                csm_delta_val = macro.get('csm_delta', 0.0)
                if getattr(config, 'ENABLE_WAVE_STATE_PERMISSION', True):
                    if perm_state in ("LOCK", "WAIT") and getattr(config, 'WAVE_STATE_LOCK_PHASE2', True):
                        logger.debug(f"[RADAR] {sym} SKIP: Permission state is {perm_state} ({macro.get('wave_summary', '')}).")
                        continue

                # ── DIRECTIONAL 5-TIER OPERATIONAL ACTION MATRIX & CIRCUIT BREAKER ──
                def _is_direction_allowed(target_dir: int, setup_label: str) -> tuple:
                    """
                    Resolves the 5-Tier Operational Action Matrix:
                    Returns: (allowed: bool, action_tier: str, reason: str)
                    """
                    # 1. Systemic Currency Basket Lock (M15 + H1 Global Flows)
                    is_basket_locked, basket_reason, _ = evaluate_systemic_basket_lock(sym, target_dir)
                    if is_basket_locked:
                        return False, "HARD_BLOCK", f"[SYSTEMIC BASKET LOCK] {basket_reason}"

                    strat_dir_sym = macro.get('strat_dir')
                    if strat_dir_sym is None:
                        return True, "FULL_ALLOW", "ALLOWED (NO_MSE)"

                    bias_score = getattr(strat_dir_sym, 'macro_bias_score', 0.0)
                    circuit_breaker = getattr(strat_dir_sym, 'hard_circuit_breaker', False)

                    # 2. Hard Circuit Breaker Collision Check (Extreme Traps & Invalidation)
                    if circuit_breaker:
                        if target_dir == 1 and bias_score < -0.40:
                            return False, "HARD_BLOCK", f"[MSE CIRCUIT BREAKER] BUY blocked at ceiling trap / past invalidation"
                        if target_dir == -1 and bias_score > 0.40:
                            return False, "HARD_BLOCK", f"[MSE CIRCUIT BREAKER] SELL blocked at floor trap / past invalidation"

                    if strat_dir_sym.forbidden_traps:
                        for trap in strat_dir_sym.forbidden_traps:
                            if target_dir == 1 and ("DO NOT BUY" in trap.upper() or "DON'T BUY" in trap.upper()):
                                return False, "HARD_BLOCK", f"[MSE TRAP VETO] BUY forbidden: {trap}"
                            if target_dir == -1 and ("DO NOT SELL" in trap.upper() or "DO NOT SHORT" in trap.upper() or "DON'T SELL" in trap.upper()):
                                return False, "HARD_BLOCK", f"[MSE TRAP VETO] SELL forbidden: {trap}"

                    # 3. Macro Bias Alignment & Action Tier Resolution
                    is_aligned = (target_dir == 1 and bias_score >= 0.35) or (target_dir == -1 and bias_score <= -0.35)
                    is_counter = (target_dir == 1 and bias_score <= -0.35) or (target_dir == -1 and bias_score >= 0.35)

                    if is_aligned:
                        return True, "FULL_ALLOW", f"ALIGNED_MACRO_EXPANSION ({bias_score:+.2f})"
                    elif is_counter:
                        # Counter-trend allows only high quality M1 liquidity sweep / SFP with TP1 cap
                        if "SWEEP" in setup_label.upper() or "RECLAIM" in setup_label.upper():
                            return True, "TP1_ONLY_SCALP", f"COUNTER_TREND_SCALP_PERMITTED ({bias_score:+.2f})"
                        else:
                            return False, "HARD_BLOCK", f"[COUNTER TREND BLOCK] Non-sweep setup rejected against macro ({bias_score:+.2f})"
                    else:
                        # Neutral / Transition Macro
                        return True, "REDUCED_CONFIDENCE", f"MODERATE_NEUTRAL_MACRO ({bias_score:+.2f})"

                # ── MECHANISM 1: UNIVERSAL LIQUIDITY SWEEP & STRUCTURAL SFP (H1 / M30) ──
                if (8 <= h <= 23) and self.is_symbol_allowed_for_session(sym, h):
                    asian_h = macro.get('asian_high', 0.0)
                    asian_l = macro.get('asian_low', 0.0)
                    pdh_val = macro.get('pdh', 0.0)
                    pdl_val = macro.get('pdl', 0.0)
                    eqh_val = macro.get('cluster_resistance', 0.0)
                    eql_val = macro.get('cluster_support', 0.0)
                    p_ceil = macro.get('sub_ceiling_50', 0.0)
                    p_floor = macro.get('sub_floor_50', 0.0)
                    sweep_tol = atr_pts * 0.35 * pt
                    
                    macro_trend_str = "BULLISH" if macro.get('is_bull') else ("BEARISH" if macro.get('is_bear') else "NEUTRAL")
                    pwh_val = macro.get('pwh', 0.0)
                    pwl_val = macro.get('pwl', 0.0)
                    dist_floor = abs(mid - pwl_val) if pwl_val > 0 else 9999.0
                    dist_ceiling = abs(mid - pwh_val) if pwh_val > 0 else 9999.0
                    atr_price_val = atr_pts * pt
                    ema20_val = macro.get('ema20', mid)
                    dr_pos_val = macro.get('dealing_range_pos', 0.5)

                    # Bearish Liquidity Sweep (SFP High): Sweep above Asian High, PDH, EQH, or Psychological Ceiling
                    ref_top_cands = [v for v in [asian_h, pdh_val, eqh_val, p_ceil] if v > 0]
                    ref_top = max(ref_top_cands) if ref_top_cands else asian_h
                    if (ref_top > 0) and (ref_top - sweep_tol <= mid <= ref_top + (atr_pts * 0.50 * pt)):
                        allowed_m1_s, action_tier_m1_s, reason_m1_s = _is_direction_allowed(-1, "BEARISH_SWEEP")
                        if not allowed_m1_s:
                            logger.debug(f"[SWEEP SELL GATE] {sym} SKIP ({action_tier_m1_s}): {reason_m1_s}")
                        else:
                            gate_ok, gate_reason = evaluate_judas_sweep_gates(
                                signal_type='SELL',
                                dealing_range_pos=dr_pos_val,
                                dist_to_htf_floor=dist_floor,
                                dist_to_htf_ceiling=dist_ceiling,
                                atr_val=atr_price_val,
                                recent_ceiling_touch=macro.get('recent_ceiling_touch', False),
                                recent_floor_touch=macro.get('recent_floor_touch', False),
                                close_below_ema20=(mid < ema20_val),
                                close_above_ema20=(mid > ema20_val),
                                macro_trend=macro_trend_str
                            )
                            if not gate_ok:
                                logger.debug(f"[SWEEP SELL GATE] {sym} SKIP: {gate_reason}")
                            else:
                                is_bull_breakout = (c_qual['direction'] == 'bullish' and c_qual['body_ratio'] >= 0.50 and c_qual['upper_wick_pct'] < 0.20 and mid > ref_top)
                                has_rejection = (mid <= ref_top) or (c_qual['max_upper_wick'] >= 0.25) or (c_qual['sweep_side'] == 'top') or c_qual['is_bearish_engulf']
                                
                                if has_rejection and not is_bull_breakout:
                                    # Delayed Limit Retest Entry at discount/retest zone
                                    limit_entry = min(ref_top, mid + (0.20 * atr_price_val)) - (spread_pts * 0.5 * pt)
                                    sl_tp = calculate_intraday_sl_tp(
                                        symbol=sym,
                                        entry_price=limit_entry,
                                        direction=-1,
                                        origin_level=ref_top,
                                        atr_h1=atr_pts * pt,
                                        pwl=pwl_val,
                                        pwh=pwh_val
                                    )
                                    sl = sl_tp['sl']
                                    tp = sl_tp['tp']
                                    if action_tier_m1_s == "TP1_ONLY_SCALP":
                                        tp = sl_tp.get('tp1', round(limit_entry - (1.25 * abs(limit_entry - sl)), 5 if pt < 0.01 else 2))
                                    rr_val = sl_tp['risk_reward']
                                    if abs(limit_entry - sl) / pt >= 15:
                                        candidates.append(CandidateSetup(
                                            symbol=sym,
                                            setup_type="UNIVERSAL_LIQUIDITY_SWEEP",
                                            direction=-1,
                                            trigger_price=round(limit_entry, 5 if pt < 0.01 else 2),
                                            timeframe="M30" if ("JPY" in sym) else "H1",
                                            macro_compass=macro['trend_label'],
                                            dealing_range_pos=dr_pos_val,
                                            rejection_wick_ratio=max(0.25, c_qual['max_upper_wick']),
                                            current_spread_pts=spread_pts,
                                            current_atr_pts=atr_pts,
                                            key_support=min(asian_l, pdl_val) if pdl_val > 0 else asian_l,
                                            key_resistance=ref_top,
                                            suggested_sl=round(sl, 5 if pt < 0.01 else 2),
                                            suggested_tp=round(tp, 5 if pt < 0.01 else 2),
                                            risk_reward_ratio=rr_val,
                                            strong_low=macro.get('strong_low', 0.0),
                                            strong_high=macro.get('strong_high', 0.0),
                                            bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                            bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                            fvg_zone=macro.get('fvg_zone', ""),
                                            liquidity_pools=macro.get('liquidity_pools', ""),
                                            frvp_confluence=macro.get('frvp_summary', '') or "Standard Institutional Liquidity",
                                            pdh=macro.get('pdh', 0.0),
                                            pdl=macro.get('pdl', 0.0),
                                            daily_open=macro.get('daily_open', 0.0),
                                            adr_used_pct=macro.get('adr_used_pct', 0.0),
                                            h4_trend=macro.get('h4_trend_label', ''),
                                            d1_50_range=macro.get('d1_50_range', ''),
                                            d1_100_range=macro.get('d1_100_range', ''),
                                            pwh=pwh_val,
                                            pwl=pwl_val,
                                            h4_monthly_range=macro.get('h4_monthly_range', ''),
                                            wave_state=macro.get('wave_state', ''),
                                            wave_summary=macro.get('wave_summary', ''),
                                            permission=perm_state,
                                            csm_delta=csm_delta_val,
                                            timestamp_wib=now.strftime("%H:%M:%S WIB"),
                                            action_tier=action_tier_m1_s,
                                            macro_bias_score=macro.get('macro_bias_score', 0.0),
                                            regime_stability=macro.get('regime_stability', 'STABLE'),
                                            metadata={
                                                "entry_type": "sell_limit",
                                                "entry_price": round(limit_entry, 5 if pt < 0.01 else 2),
                                                "ref_top": ref_top,
                                                "target_station": sl_tp.get('target_station', 0.0),
                                                "action_tier": action_tier_m1_s,
                                                "macro_corridor": macro.get('macro_corridor', 'NEUTRAL')
                                            }
                                        ))
                                        continue

                    # Bullish Liquidity Sweep (SFP Low): Sweep below Asian Low, PDL, EQL, or Psychological Floor
                    ref_bot_cands = [v for v in [asian_l, pdl_val, eql_val, p_floor] if v > 0]
                    ref_bot = min(ref_bot_cands) if ref_bot_cands else asian_l
                    if (ref_bot > 0) and (ref_bot - (atr_pts * 0.50 * pt) <= mid <= ref_bot + sweep_tol):
                        allowed_m1_b, action_tier_m1_b, reason_m1_b = _is_direction_allowed(1, "BULLISH_SWEEP")
                        if not allowed_m1_b:
                            logger.debug(f"[SWEEP BUY GATE] {sym} SKIP ({action_tier_m1_b}): {reason_m1_b}")
                        else:
                            gate_ok, gate_reason = evaluate_judas_sweep_gates(
                                signal_type='BUY',
                                dealing_range_pos=dr_pos_val,
                                dist_to_htf_floor=abs(mid - pwl_val) if pwl_val > 0 else 9999.0,
                                dist_to_htf_ceiling=abs(mid - pwh_val) if pwh_val > 0 else 9999.0,
                                atr_val=atr_price_val,
                                recent_ceiling_touch=macro.get('recent_ceiling_touch', False),
                                recent_floor_touch=macro.get('recent_floor_touch', False),
                                close_below_ema20=(mid < macro.get('ema20', mid)),
                                close_above_ema20=(mid > macro.get('ema20', mid)),
                                macro_trend=macro_trend_str
                            )
                            if not gate_ok:
                                logger.debug(f"[SWEEP BUY GATE] {sym} SKIP: {gate_reason}")
                            else:
                                is_bear_breakdown = (c_qual['direction'] == 'bearish' and c_qual['body_ratio'] >= 0.50 and c_qual['lower_wick_pct'] < 0.20 and mid < ref_bot)
                                has_rejection = (mid >= ref_bot) or (c_qual['max_lower_wick'] >= 0.25) or (c_qual['sweep_side'] == 'bottom') or c_qual['is_bullish_engulf']
                                
                                if has_rejection and not is_bear_breakdown:
                                    # Delayed Limit Retest Entry at premium/retest zone
                                    limit_entry = max(ref_bot, mid - (0.20 * atr_price_val)) + (spread_pts * 0.5 * pt)
                                    sl_tp = calculate_intraday_sl_tp(
                                        symbol=sym,
                                        entry_price=limit_entry,
                                        direction=1,
                                        origin_level=ref_bot,
                                        atr_h1=atr_pts * pt,
                                        pwl=pwl_val,
                                        pwh=pwh_val
                                    )
                                    sl = sl_tp['sl']
                                    tp = sl_tp['tp']
                                    if action_tier_m1_b == "TP1_ONLY_SCALP":
                                        tp = sl_tp.get('tp1', round(limit_entry + (1.25 * abs(limit_entry - sl)), 5 if pt < 0.01 else 2))
                                    rr_val = sl_tp['risk_reward']
                                    if abs(limit_entry - sl) / pt >= 15:
                                        candidates.append(CandidateSetup(
                                            symbol=sym,
                                            setup_type="UNIVERSAL_LIQUIDITY_SWEEP",
                                            direction=1,
                                            trigger_price=round(limit_entry, 5 if pt < 0.01 else 2),
                                            timeframe="M30" if ("JPY" in sym) else "H1",
                                            macro_compass=macro['trend_label'],
                                            dealing_range_pos=dr_pos_val,
                                            rejection_wick_ratio=max(0.25, c_qual['max_lower_wick']),
                                            current_spread_pts=spread_pts,
                                            current_atr_pts=atr_pts,
                                            key_support=ref_bot,
                                            key_resistance=max(asian_h, pdh_val) if pdh_val > 0 else asian_h,
                                            suggested_sl=round(sl, 5 if pt < 0.01 else 2),
                                            suggested_tp=round(tp, 5 if pt < 0.01 else 2),
                                            risk_reward_ratio=rr_val,
                                            strong_low=macro.get('strong_low', 0.0),
                                            strong_high=macro.get('strong_high', 0.0),
                                            bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                            bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                            fvg_zone=macro.get('fvg_zone', ""),
                                            liquidity_pools=macro.get('liquidity_pools', ""),
                                            frvp_confluence=macro.get('frvp_summary', '') or "Standard Institutional Liquidity",
                                            pdh=macro.get('pdh', 0.0),
                                            pdl=macro.get('pdl', 0.0),
                                            daily_open=macro.get('daily_open', 0.0),
                                            adr_used_pct=macro.get('adr_used_pct', 0.0),
                                            h4_trend=macro.get('h4_trend_label', ''),
                                            d1_50_range=macro.get('d1_50_range', ''),
                                            d1_100_range=macro.get('d1_100_range', ''),
                                            pwh=pwh_val,
                                            pwl=pwl_val,
                                            h4_monthly_range=macro.get('h4_monthly_range', ''),
                                            wave_state=macro.get('wave_state', ''),
                                            wave_summary=macro.get('wave_summary', ''),
                                            permission=perm_state,
                                            csm_delta=csm_delta_val,
                                            timestamp_wib=now.strftime("%H:%M:%S WIB"),
                                            action_tier=action_tier_m1_b,
                                            macro_bias_score=macro.get('macro_bias_score', 0.0),
                                            regime_stability=macro.get('regime_stability', 'STABLE'),
                                            metadata={
                                                "entry_type": "buy_limit",
                                                "entry_price": round(limit_entry, 5 if pt < 0.01 else 2),
                                                "ref_bot": ref_bot,
                                                "target_station": sl_tp.get('target_station', 0.0),
                                                "action_tier": action_tier_m1_b,
                                                "macro_corridor": macro.get('macro_corridor', 'NEUTRAL')
                                            }
                                        ))
                                        continue

                # ── MECHANISM 2: TREND-ALIGNED MULTI-TIMEFRAME PULLBACK & DELAYED RETEST (H1/M30) ──
                if (8 <= h <= 23) and self.is_symbol_allowed_for_session(sym, h):
                    ema20 = macro['ema20']
                    pos_in_range = macro['dealing_range_pos']
                    m_corr = macro.get('macro_corridor', 'NEUTRAL')
                    
                    # BUY: (Bullish Macro OR Bullish Corridor) AND NOT Bearish Corridor + Pullback to EMA20 in Discount
                    allowed_m2_b, action_tier_m2_b, reason_m2_b = _is_direction_allowed(1, "BUY_PULLBACK")
                    can_buy_m2 = allowed_m2_b and (macro['is_bull'] or m_corr == "BULLISH_CORRIDOR") and (m_corr != "BEARISH_CORRIDOR")
                    if not allowed_m2_b:
                        logger.debug(f"[PULLBACK BUY GATE] {sym} SKIP ({action_tier_m2_b}): {reason_m2_b}")
                    elif can_buy_m2 and pos_in_range <= 0.65:
                        if abs(mid - ema20) <= (atr_pts * 0.45 * pt):
                            lim_entry = mid - (atr_pts * 0.20 * pt)
                            base_floor = macro['dealing_range_low']
                            sl_tp = calculate_intraday_sl_tp(
                                symbol=sym,
                                entry_price=lim_entry,
                                direction=1,
                                origin_level=base_floor,
                                atr_h1=atr_pts * pt,
                                pwl=macro.get('pwl', 0.0),
                                pwh=macro.get('pwh', 0.0)
                            )
                            sl = sl_tp['sl']
                            tp = sl_tp['tp']
                            if action_tier_m2_b == "TP1_ONLY_SCALP":
                                tp = sl_tp.get('tp1', round(lim_entry + (1.25 * abs(lim_entry - sl)), 5 if pt < 0.01 else 2))
                            rr_val = sl_tp['risk_reward']
                            if abs(lim_entry - sl) / pt >= 15:
                                candidates.append(CandidateSetup(
                                    symbol=sym,
                                    setup_type="TREND_ALIGNED_PULLBACK",
                                    direction=1,
                                    trigger_price=round(lim_entry, 5 if pt < 0.01 else 2),
                                    timeframe="M30" if ("XAU" in sym or "JPY" in sym) else "H1",
                                    macro_compass=f"{macro['trend_label']} | {m_corr}",
                                    dealing_range_pos=pos_in_range,
                                    rejection_wick_ratio=max(0.15, c_qual['max_lower_wick']),
                                    current_spread_pts=spread_pts,
                                    current_atr_pts=atr_pts,
                                    key_support=round(sl, 5 if pt < 0.01 else 2),
                                    key_resistance=macro['dealing_range_high'],
                                    suggested_sl=sl,
                                    suggested_tp=tp,
                                    risk_reward_ratio=rr_val,
                                    strong_low=macro.get('strong_low', 0.0),
                                    strong_high=macro.get('strong_high', 0.0),
                                    bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                    bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                    fvg_zone=macro.get('fvg_zone', ""),
                                    liquidity_pools=macro.get('liquidity_pools', ""),
                                    frvp_confluence=macro.get('frvp_summary', '') or "Standard Institutional Liquidity",
                                    pdh=macro.get('pdh', 0.0),
                                    pdl=macro.get('pdl', 0.0),
                                    daily_open=macro.get('daily_open', 0.0),
                                    adr_used_pct=macro.get('adr_used_pct', 0.0),
                                    h4_trend=macro.get('h4_trend_label', ''),
                                    d1_50_range=macro.get('d1_50_range', ''),
                                    d1_100_range=macro.get('d1_100_range', ''),
                                    pwh=macro.get('pwh', 0.0),
                                    pwl=macro.get('pwl', 0.0),
                                    h4_monthly_range=macro.get('h4_monthly_range', ''),
                                    wave_state=macro.get('wave_state', ''),
                                    wave_summary=macro.get('wave_summary', ''),
                                    permission=perm_state,
                                    csm_delta=csm_delta_val,
                                    timestamp_wib=now.strftime("%H:%M:%S WIB"),
                                    action_tier=action_tier_m2_b,
                                    macro_bias_score=macro.get('macro_bias_score', 0.0),
                                    regime_stability=macro.get('regime_stability', 'STABLE'),
                                    metadata={
                                        "entry_type": "buy_limit",
                                        "entry_price": round(lim_entry, 5 if pt < 0.01 else 2),
                                        "base_floor": base_floor,
                                        "target_station": sl_tp.get('target_station', 0.0),
                                        "permission": perm_state,
                                        "csm_delta": csm_delta_val,
                                        "action_tier": action_tier_m2_b,
                                        "macro_corridor": m_corr
                                    }
                                ))
                                continue

                    # SELL: (Bearish Macro OR Bearish Corridor) AND NOT Bullish Corridor + Pullback to EMA20 in Premium
                    allowed_m2_s, action_tier_m2_s, reason_m2_s = _is_direction_allowed(-1, "SELL_PULLBACK")
                    can_sell_m2 = allowed_m2_s and (macro['is_bear'] or m_corr == "BEARISH_CORRIDOR") and (m_corr != "BULLISH_CORRIDOR")
                    if not allowed_m2_s:
                        logger.debug(f"[PULLBACK SELL GATE] {sym} SKIP ({action_tier_m2_s}): {reason_m2_s}")
                    elif can_sell_m2 and pos_in_range >= 0.35:
                        if abs(mid - ema20) <= (atr_pts * 0.45 * pt):
                            lim_entry = mid + (atr_pts * 0.20 * pt)
                            base_floor = macro['dealing_range_high']
                            sl_tp = calculate_intraday_sl_tp(
                                symbol=sym,
                                entry_price=lim_entry,
                                direction=-1,
                                origin_level=base_floor,
                                atr_h1=atr_pts * pt,
                                pwl=macro.get('pwl', 0.0),
                                pwh=macro.get('pwh', 0.0)
                            )
                            sl = sl_tp['sl']
                            tp = sl_tp['tp']
                            if action_tier_m2_s == "TP1_ONLY_SCALP":
                                tp = sl_tp.get('tp1', round(lim_entry - (1.25 * abs(lim_entry - sl)), 5 if pt < 0.01 else 2))
                            rr_val = sl_tp['risk_reward']
                            if abs(sl - lim_entry) / pt >= 15:
                                candidates.append(CandidateSetup(
                                    symbol=sym,
                                    setup_type="TREND_ALIGNED_PULLBACK",
                                    direction=-1,
                                    trigger_price=round(lim_entry, 5 if pt < 0.01 else 2),
                                    timeframe="M30" if ("XAU" in sym or "JPY" in sym) else "H1",
                                    macro_compass=f"{macro['trend_label']} | {m_corr}",
                                    dealing_range_pos=pos_in_range,
                                    rejection_wick_ratio=max(0.15, c_qual['max_upper_wick']),
                                    current_spread_pts=spread_pts,
                                    current_atr_pts=atr_pts,
                                    key_support=macro['dealing_range_low'],
                                    key_resistance=round(sl, 5 if pt < 0.01 else 2),
                                    suggested_sl=sl,
                                    suggested_tp=tp,
                                    risk_reward_ratio=rr_val,
                                    strong_low=macro.get('strong_low', 0.0),
                                    strong_high=macro.get('strong_high', 0.0),
                                    bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                    bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                    fvg_zone=macro.get('fvg_zone', ""),
                                    liquidity_pools=macro.get('liquidity_pools', ""),
                                    frvp_confluence=macro.get('frvp_summary', '') or "Standard Institutional Liquidity",
                                    pdh=macro.get('pdh', 0.0),
                                    pdl=macro.get('pdl', 0.0),
                                    daily_open=macro.get('daily_open', 0.0),
                                    adr_used_pct=macro.get('adr_used_pct', 0.0),
                                    h4_trend=macro.get('h4_trend_label', ''),
                                    d1_50_range=macro.get('d1_50_range', ''),
                                    d1_100_range=macro.get('d1_100_range', ''),
                                    pwh=macro.get('pwh', 0.0),
                                    pwl=macro.get('pwl', 0.0),
                                    h4_monthly_range=macro.get('h4_monthly_range', ''),
                                    wave_state=macro.get('wave_state', ''),
                                    wave_summary=macro.get('wave_summary', ''),
                                    permission=perm_state,
                                    csm_delta=csm_delta_val,
                                    timestamp_wib=now.strftime("%H:%M:%S WIB"),
                                    action_tier=action_tier_m2_s,
                                    macro_bias_score=macro.get('macro_bias_score', 0.0),
                                    regime_stability=macro.get('regime_stability', 'STABLE'),
                                    metadata={
                                        "entry_type": "sell_limit",
                                        "entry_price": round(lim_entry, 5 if pt < 0.01 else 2),
                                        "base_floor": base_floor,
                                        "target_station": sl_tp.get('target_station', 0.0),
                                        "permission": perm_state,
                                        "csm_delta": csm_delta_val,
                                        "action_tier": action_tier_m2_s,
                                        "macro_corridor": m_corr
                                    }
                                ))
                                continue

                # ── MECHANISM 3: MULTI-TOUCH CLUSTER BREAKOUT & DELAYED RETEST (H1/M30) ──
                if (8 <= h <= 23) and self.is_symbol_allowed_for_session(sym, h):
                    c_res = macro.get('cluster_resistance', 0.0)
                    c_sup = macro.get('cluster_support', 0.0)
                    t_res = macro.get('touches_resistance', 0)
                    t_sup = macro.get('touches_support', 0)
                    atr_val = atr_pts * pt
                    m_corr = macro.get('macro_corridor', 'NEUTRAL')

                    # Bullish Breakout Retest: Tested >= 2 times, broke above cluster resistance, macro bull / bullish corridor
                    allowed_m3_b, action_tier_m3_b, reason_m3_b = _is_direction_allowed(1, "BUY_BREAKOUT_RETEST")
                    can_buy_m3 = allowed_m3_b and (macro['is_bull'] or m_corr == "BULLISH_CORRIDOR") and (m_corr != "BEARISH_CORRIDOR")
                    if not allowed_m3_b:
                        logger.debug(f"[BREAKOUT BUY GATE] {sym} SKIP ({action_tier_m3_b}): {reason_m3_b}")
                    elif can_buy_m3 and t_res >= 2 and (c_res > 0):
                        if (c_res + atr_val * 0.10) <= mid <= (c_res + atr_val * 0.65):
                            entry_lim = c_res - (spread_pts * 0.5 * pt) # Limit retest entry at broken resistance
                            sl_tp = calculate_intraday_sl_tp(
                                symbol=sym,
                                entry_price=entry_lim,
                                direction=1,
                                origin_level=c_res,
                                atr_h1=atr_val,
                                pwl=macro.get('pwl', 0.0),
                                pwh=macro.get('pwh', 0.0)
                            )
                            sl = sl_tp['sl']
                            tp = sl_tp['tp']
                            if action_tier_m3_b == "TP1_ONLY_SCALP":
                                tp = sl_tp.get('tp1', round(entry_lim + (1.25 * abs(entry_lim - sl)), 5 if pt < 0.01 else 2))
                            rr_val = sl_tp['risk_reward']
                            if abs(entry_lim - sl) / pt >= 15:
                                candidates.append(CandidateSetup(
                                    symbol=sym,
                                    setup_type="MULTI_TOUCH_BREAKOUT_RETEST",
                                    direction=1,
                                    trigger_price=round(entry_lim, 5 if pt < 0.01 else 2),
                                    timeframe="M30" if ("XAU" in sym or "JPY" in sym) else "H1",
                                    macro_compass=f"{macro['trend_label']} | {m_corr}",
                                    dealing_range_pos=macro['dealing_range_pos'],
                                    rejection_wick_ratio=max(0.15, c_qual['max_lower_wick']),
                                    current_spread_pts=spread_pts,
                                    current_atr_pts=atr_pts,
                                    key_support=c_res,
                                    key_resistance=macro['dealing_range_high'],
                                    suggested_sl=sl,
                                    suggested_tp=tp,
                                    risk_reward_ratio=rr_val,
                                    strong_low=c_res,
                                    strong_high=macro.get('strong_high', 0.0),
                                    bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                    bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                    fvg_zone=macro.get('fvg_zone', ""),
                                    liquidity_pools=f"Tested {t_res}x (Range Age: {macro.get('range_age_hours', 24)}h)",
                                    frvp_confluence=macro.get('frvp_summary', '') or "Standard Institutional Liquidity",
                                    pdh=macro.get('pdh', 0.0),
                                    pdl=macro.get('pdl', 0.0),
                                    daily_open=macro.get('daily_open', 0.0),
                                    adr_used_pct=macro.get('adr_used_pct', 0.0),
                                    h4_trend=macro.get('h4_trend_label', ''),
                                    d1_50_range=macro.get('d1_50_range', ''),
                                    d1_100_range=macro.get('d1_100_range', ''),
                                    pwh=macro.get('pwh', 0.0),
                                    pwl=macro.get('pwl', 0.0),
                                    h4_monthly_range=macro.get('h4_monthly_range', ''),
                                    wave_state=macro.get('wave_state', ''),
                                    wave_summary=macro.get('wave_summary', ''),
                                    permission=perm_state,
                                    csm_delta=csm_delta_val,
                                    timestamp_wib=now.strftime("%H:%M:%S WIB"),
                                    action_tier=action_tier_m3_b,
                                    macro_bias_score=macro.get('macro_bias_score', 0.0),
                                    regime_stability=macro.get('regime_stability', 'STABLE'),
                                    metadata={
                                        "entry_type": "buy_limit",
                                        "entry_price": round(entry_lim, 5 if pt < 0.01 else 2),
                                        "zone_level": c_res,
                                        "zone_touches": t_res,
                                        "range_age_hours": macro.get('range_age_hours', 24),
                                        "wave_regime": macro.get('wave_regime_name', 'YOUNG_OSCILLATION'),
                                        "target_station": sl_tp.get('target_station', 0.0),
                                        "permission": perm_state,
                                        "csm_delta": csm_delta_val,
                                        "action_tier": action_tier_m3_b,
                                        "macro_corridor": m_corr
                                    }
                                ))
                                continue

                    # Bearish Breakout Retest: Tested >= 2 times, broke below cluster support, macro bear / bearish corridor
                    allowed_m3_s, action_tier_m3_s, reason_m3_s = _is_direction_allowed(-1, "SELL_BREAKOUT_RETEST")
                    can_sell_m3 = allowed_m3_s and (macro['is_bear'] or m_corr == "BEARISH_CORRIDOR") and (m_corr != "BULLISH_CORRIDOR")
                    if not allowed_m3_s:
                        logger.debug(f"[BREAKOUT SELL GATE] {sym} SKIP ({action_tier_m3_s}): {reason_m3_s}")
                    elif can_sell_m3 and t_sup >= 2 and (c_sup > 0):
                        if (c_sup - atr_val * 0.65) <= mid <= (c_sup - atr_val * 0.10):
                            entry_lim = c_sup + (spread_pts * 0.5 * pt) # Limit retest entry at broken support
                            sl_tp = calculate_intraday_sl_tp(
                                symbol=sym,
                                entry_price=entry_lim,
                                direction=-1,
                                origin_level=c_sup,
                                atr_h1=atr_val,
                                pwl=macro.get('pwl', 0.0),
                                pwh=macro.get('pwh', 0.0)
                            )
                            sl = sl_tp['sl']
                            tp = sl_tp['tp']
                            if action_tier_m3_s == "TP1_ONLY_SCALP":
                                tp = sl_tp.get('tp1', round(entry_lim - (1.25 * abs(entry_lim - sl)), 5 if pt < 0.01 else 2))
                            rr_val = sl_tp['risk_reward']
                            if abs(sl - entry_lim) / pt >= 15:
                                candidates.append(CandidateSetup(
                                    symbol=sym,
                                    setup_type="MULTI_TOUCH_BREAKOUT_RETEST",
                                    direction=-1,
                                    trigger_price=round(entry_lim, 5 if pt < 0.01 else 2),
                                    timeframe="M30" if ("XAU" in sym or "JPY" in sym) else "H1",
                                    macro_compass=f"{macro['trend_label']} | {m_corr}",
                                    dealing_range_pos=macro['dealing_range_pos'],
                                    rejection_wick_ratio=max(0.15, c_qual['max_upper_wick']),
                                    current_spread_pts=spread_pts,
                                    current_atr_pts=atr_pts,
                                    key_support=macro['dealing_range_low'],
                                    key_resistance=c_sup,
                                    suggested_sl=sl,
                                    suggested_tp=tp,
                                    risk_reward_ratio=rr_val,
                                    strong_low=macro.get('strong_low', 0.0),
                                    strong_high=c_sup,
                                    bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                    bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                    fvg_zone=macro.get('fvg_zone', ""),
                                    liquidity_pools=f"Tested {t_sup}x (Range Age: {macro.get('range_age_hours', 24)}h)",
                                    frvp_confluence=macro.get('frvp_summary', '') or "Standard Institutional Liquidity",
                                    pdh=macro.get('pdh', 0.0),
                                    pdl=macro.get('pdl', 0.0),
                                    daily_open=macro.get('daily_open', 0.0),
                                    adr_used_pct=macro.get('adr_used_pct', 0.0),
                                    h4_trend=macro.get('h4_trend_label', ''),
                                    d1_50_range=macro.get('d1_50_range', ''),
                                    d1_100_range=macro.get('d1_100_range', ''),
                                    pwh=macro.get('pwh', 0.0),
                                    pwl=macro.get('pwl', 0.0),
                                    h4_monthly_range=macro.get('h4_monthly_range', ''),
                                    wave_state=macro.get('wave_state', ''),
                                    wave_summary=macro.get('wave_summary', ''),
                                    permission=perm_state,
                                    csm_delta=csm_delta_val,
                                    timestamp_wib=now.strftime("%H:%M:%S WIB"),
                                    action_tier=action_tier_m3_s,
                                    macro_bias_score=macro.get('macro_bias_score', 0.0),
                                    regime_stability=macro.get('regime_stability', 'STABLE'),
                                    metadata={
                                        "entry_type": "sell_limit",
                                        "entry_price": round(entry_lim, 5 if pt < 0.01 else 2),
                                        "zone_level": c_sup,
                                        "zone_touches": t_sup,
                                        "range_age_hours": macro.get('range_age_hours', 24),
                                        "wave_regime": macro.get('wave_regime_name', 'YOUNG_OSCILLATION'),
                                        "target_station": sl_tp.get('target_station', 0.0),
                                        "permission": perm_state,
                                        "csm_delta": csm_delta_val,
                                        "action_tier": action_tier_m3_s,
                                        "macro_corridor": m_corr
                                    }
                                ))
                                continue

            except Exception as e:
                logger.debug(f"Radar check error on {sym}: {e}")

        for c in candidates:
            c_clean = c.symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").upper()
            self._symbol_last_trigger[c_clean] = now_ts

        self.last_candidates = candidates
        return candidates
    def get_symbol_smc_levels(self, symbol: str) -> Dict[str, Any]:
        """Calculates and returns exact price boundaries for Dealing Range, Discount, Equilibrium, Premium, OB, and FVG."""
        clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "")
        for k, v in self.macro_cache.items():
            if k.startswith(clean_sym):
                h = v['dealing_range_high']
                l = v['dealing_range_low']
                rng = max(h - l, 1e-5)
                eq = l + 0.500 * rng
                disc_382 = l + 0.382 * rng
                prem_618 = l + 0.618 * rng
                pt = self._get_point(k)
                dec = 2 if pt >= 0.01 else 5
                
                return {
                    "symbol": k,
                    "range_high_100": round(h, dec),
                    "premium_zone_start": round(prem_618, dec),
                    "equilibrium_50": round(eq, dec),
                    "discount_zone_end": round(disc_382, dec),
                    "range_low_0": round(l, dec),
                    "pos_pct": round(v['dealing_range_pos'] * 100, 1),
                    "pos_label": "DEEP DISCOUNT" if v['dealing_range_pos'] <= 0.38 else ("EXTREME PREMIUM" if v['dealing_range_pos'] >= 0.62 else "EQUILIBRIUM"),
                    "asian_high": round(v.get('asian_high', h), dec),
                    "asian_low": round(v.get('asian_low', l), dec),
                    "strong_high": round(v.get('strong_high', 0.0), dec),
                    "strong_low": round(v.get('strong_low', 0.0), dec),
                    "bullish_ob": v.get('bullish_ob_zone', "-"),
                    "bearish_ob": v.get('bearish_ob_zone', "-"),
                    "fvg": v.get('fvg_zone', "-"),
                    "cluster_resistance": round(v.get('cluster_resistance', h), dec),
                    "cluster_support": round(v.get('cluster_support', l), dec),
                    "touches_resistance": v.get('touches_resistance', 0),
                    "touches_support": v.get('touches_support', 0),
                    "wave_regime": v.get('wave_regime_name', "NORMAL"),
                    "range_age_hours": round(v.get('range_age_hours', 24.0), 1),
                    "trend_label": v.get('trend_label', "-")
                }
        return {}

    def get_market_structure_report(self) -> str:
        """Generates institutional market structure text table for Telegram / CLI."""
        now = datetime.now(WIB)
        lines = [
            f"🏛️ *MARKET STRUCTURE & SMC RADAR ({now.strftime('%H:%M:%S WIB')})*",
            "━" * 36
        ]

        if not self.macro_cache:
            lines.append("⚠️ Macro cache belum termuat. Menjalankan sinkronisasi...")
            return "\n".join(lines)

        bull_pairs = []
        bear_pairs = []
        range_pairs = []
        discount_pairs = []
        premium_pairs = []

        for sym, m in self.macro_cache.items():
            clean = sym.replace("-ECNc", "").replace("-ECN", "")
            if m['is_bull']: bull_pairs.append(clean)
            elif m['is_bear']: bear_pairs.append(clean)
            else: range_pairs.append(clean)

            h = m['dealing_range_high']
            l = m['dealing_range_low']
            rng = max(h - l, 1e-5)
            disc_top = l + 0.382 * rng
            prem_bot = l + 0.618 * rng

            if m['dealing_range_pos'] <= 0.38:
                discount_pairs.append(f"• *{clean}*: `{disc_top:.5f}` (Pos: {m['dealing_range_pos']*100:.0f}% Diskon)")
            elif m['dealing_range_pos'] >= 0.62:
                premium_pairs.append(f"• *{clean}*: `{prem_bot:.5f}` (Pos: {m['dealing_range_pos']*100:.0f}% Premium)")

        go_pairs = []
        arm_pairs = []
        locked_pairs = []
        wait_pairs = []

        for sym, m in self.macro_cache.items():
            clean = sym.replace("-ECNc", "").replace("-ECN", "")
            perm = m.get('permission_state', 'WAIT')
            d_st = m.get('direction_state', 'NEUTRAL')
            p_st = m.get('phase_state', 'EXPANSION')
            pos_p = int(m.get('dealing_range_pos', 0.5) * 100)
            
            if perm == "GO":
                go_pairs.append(f"{clean} ({d_st}/{p_st} {pos_p}%)")
            elif perm == "ARM":
                arm_pairs.append(f"{clean} ({pos_p}%)")
            elif perm == "LOCK":
                locked_pairs.append(f"{clean} ({d_st} Knife)")
            elif perm in ("WAIT", "WATCH"):
                wait_pairs.append(clean)

        corridor_bulls = []
        corridor_bears = []
        for sym, m in self.macro_cache.items():
            clean = sym.replace("-ECNc", "").replace("-ECN", "")
            corr = m.get('macro_corridor', 'NEUTRAL')
            target_st = m.get('target_station', 0.0)
            if corr == "BULLISH_CORRIDOR":
                corridor_bulls.append(f"{clean} (🎯 {target_st:.4f})")
            elif corr == "BEARISH_CORRIDOR":
                corridor_bears.append(f"{clean} (🎯 {target_st:.4f})")

        lines.append(f"🟢 *Bullish Compass:* {', '.join(bull_pairs[:6]) if bull_pairs else '-'}")
        lines.append(f"🔴 *Bearish Compass:* {', '.join(bear_pairs[:6]) if bear_pairs else '-'}")
        lines.append(f"⚪ *Sideways Range:* {', '.join(range_pairs[:6]) if range_pairs else '-'}")
        lines.append("━" * 36)
        lines.append("🧭 *M3 MACRO COMPASS STATION CORRIDORS:*")
        lines.append(f"• 🟢 *Bullish Delivery:* {', '.join(corridor_bulls[:4]) if corridor_bulls else '-'}")
        lines.append(f"• 🔴 *Bearish Delivery:* {', '.join(corridor_bears[:4]) if corridor_bears else '-'}")
        lines.append("━" * 36)
        lines.append("🌊 *4-LAYER TRADE PERMISSION ENGINE:*")
        lines.append(f"• 🚀 *Permission GO (Pelatuk Aktif / Reclaim):* {', '.join(go_pairs[:4]) if go_pairs else 'Nihil'}")
        lines.append(f"• 🎯 *Permission ARM (Siaga di Reload Zone):* {', '.join(arm_pairs[:4]) if arm_pairs else '-'}")
        lines.append(f"• 🔒 *Permission LOCK (Anti-Falling Knife):* {', '.join(locked_pairs[:4]) if locked_pairs else '-'}")
        lines.append(f"• ⏳ *Permission WAIT (Anti-FOMO / Di Pucuk):* {', '.join(wait_pairs[:5]) if wait_pairs else '-'}")
        lines.append("━" * 36)
        lines.append("🎯 *ZONA DISKON (Buy Radar <= 38.2%):*")
        lines.extend(discount_pairs[:4] if discount_pairs else ["• Nihil (Tidak ada pair di zona diskon)"])
        lines.append("━" * 36)
        lines.append("🎯 *ZONA PREMIUM (Sell Radar >= 61.8%):*")
        lines.extend(premium_pairs[:4] if premium_pairs else ["• Nihil (Tidak ada pair di zona premium)"])
        
        if self.last_candidates:
            lines.append("━" * 36)
            lines.append(f"⚡ *KANDIDAT RADAR AKTIF ({len(self.last_candidates)}):*")
            for c in self.last_candidates[:3]:
                d_str = "BUY" if c.direction == 1 else "SELL"
                lines.append(f"• *{c.symbol}* [{d_str}] -> {c.setup_type} @ {c.trigger_price} (SL: {c.suggested_sl}, TP: {c.suggested_tp})")
        else:
            lines.append("━" * 36)
            lines.append("📡 *Fast Radar:* 26 Pasang dipantau, 0 sinyal terpicu saat ini.")

        return "\n".join(lines)

    @staticmethod
    def _calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        hl = df['high'] - df['low']
        hc = (df['high'] - df['close'].shift(1)).abs()
        lc = (df['low'] - df['close'].shift(1)).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def _calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df['high']; low = df['low']; close = df['close']
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        hl = high - low
        hc = (high - close.shift(1)).abs()
        lc = (low - close.shift(1)).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        
        tr_smooth = tr.rolling(period).sum()
        plus_di = 100 * (plus_dm.rolling(period).sum() / tr_smooth.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(period).sum() / tr_smooth.replace(0, np.nan))
        
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
        return dx.rolling(period).mean().fillna(20.0)
