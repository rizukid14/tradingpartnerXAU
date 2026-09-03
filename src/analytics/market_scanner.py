import os
import sys
import json
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any, Tuple

import numpy as np  # type: ignore
import pandas as pd  # type: ignore

import config
from src.indicators.lux_smc import LuxSMCAnalyzer
from src.indicators.candle_quality import classify_candle, classify_breakout_sequence
from src.indicators.sweep_detector import detect as sweep_detect
from src.indicators.wave_regime import evaluate_wave_regime
from src.indicators.atlas_dna import calculate_intraday_sl_tp, calculate_dynamic_stations, calculate_dual_grid_stations, get_symbol_step
from src.analytics.currency_strength import get_csm_delta_for_symbol, evaluate_systemic_basket_lock
from src.analytics.macro_strategic_engine import (
    macro_strategic_engine, 
    MacroStrategicDirective,
    CLEAN_RESPECT_PAIRS,
    SWEEP_SPECIALIST_PAIRS,
    MOMENTUM_RUNNER_PAIRS
)

logger = logging.getLogger("market_scanner")
WIB = ZoneInfo("Asia/Jakarta")


def evaluate_universal_sweep_gates(
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
    3-Gate Hierarchical Structural Validator for UNIVERSAL_LIQUIDITY_SWEEP.
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
    # GATE C: Anti-Expansion Momentum Vector (Anti-Trend Fade Gate)
    # =========================================================================
    # If Macro is in BULLISH EXPANSION, do NOT SELL an Asian/PDH high sweep if C1 ceiling is still far above!
    if signal_type == 'SELL' and "BULLISH" in str(macro_trend).upper():
        if dist_to_htf_ceiling > atr_threshold:
            return False, (
                f"LOCKED BY GATE C [Anti-Expansion]: Macro is BULLISH_EXPANSION and structural ceiling C1 "
                f"is still {dist_to_htf_ceiling/atr_val:.2f}x ATR above (> {atr_threshold:.5f}). "
                f"High sweep is breakout momentum expansion toward C1, NOT a reversal."
            )

    # Symmetrically: If Macro is in BEARISH EXPANSION, do NOT BUY an Asian/PDL low sweep if F1 floor is still far below!
    if signal_type == 'BUY' and "BEARISH" in str(macro_trend).upper():
        if dist_to_htf_floor > atr_threshold:
            return False, (
                f"LOCKED BY GATE C [Anti-Expansion]: Macro is BEARISH_EXPANSION and structural floor F1 "
                f"is still {dist_to_htf_floor/atr_val:.2f}x ATR below (> {atr_threshold:.5f}). "
                f"Low sweep is breakdown waterfall toward F1, NOT a reversal."
            )

    # =========================================================================
    # GATE A: HTF Anchor & Deep Discount / Extreme Premium Area of Value
    # =========================================================================
    if signal_type == 'BUY':
        if dealing_range_pos > 0.45:
            return False, f"LOCKED BY GATE A [Range Discipline]: Bullish Sweep forbidden in Premium/Equilibrium (DR {dealing_range_pos*100:.1f}% > 45%)."
        is_deep_discount = dealing_range_pos <= 0.25
        is_anchored_floor = dist_to_htf_floor <= atr_threshold
        if not (is_deep_discount or is_anchored_floor):
            return False, (
                f"LOCKED BY GATE A [HTF Anchor]: Low sweep at DR {dealing_range_pos*100:.1f}% "
                f"lacks HTF Support Floor (Requires Deep Discount DR <= 25% or Floor Distance <= {atr_threshold:.5f})."
            )
        return True, f"PASSED ALL GATES: Valid Universal Sweep BUY anchored at HTF Floor (DR {dealing_range_pos*100:.1f}%)."

    elif signal_type == 'SELL':
        if dealing_range_pos < 0.55:
            return False, f"LOCKED BY GATE A [Range Discipline]: Bearish Sweep forbidden in Discount/Equilibrium (DR {dealing_range_pos*100:.1f}% < 55%)."
        is_extreme_premium = dealing_range_pos >= 0.75
        is_anchored_ceiling = dist_to_htf_ceiling <= atr_threshold
        if not (is_extreme_premium or is_anchored_ceiling):
            return False, (
                f"LOCKED BY GATE A [HTF Anchor]: High sweep at DR {dealing_range_pos*100:.1f}% "
                f"lacks HTF Resistance Ceiling (Requires Extreme Premium DR >= 75% or Ceiling Distance <= {atr_threshold:.5f})."
            )
        return True, f"PASSED ALL GATES: Valid Universal Sweep SELL anchored at HTF Ceiling (DR {dealing_range_pos*100:.1f}%)."

    return False, "LOCKED: Default Fallback."


# Backward compatibility alias
evaluate_judas_sweep_gates = evaluate_universal_sweep_gates


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

# Sesi Tokyo (08:00 - 14:00 WIB): Diarahkan dinamis via config.is_asian_session_pair(symbol).
# Semua pair dengan driver mata uang aktif Asia/Pasifik (JPY, AUD, NZD) diizinkan;
# pair tanpa JPY/AUD/NZD (seperti EURCAD, GBPCAD, USDCAD, EURUSD, GBPUSD, dll.) dikunci.

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
    scan_mid: float = 0.0

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
        self._cooldown_file = os.path.join(config.DATA_DIR, "scanner_cooldowns.json")
        self._symbol_last_trigger: Dict[str, float] = self._load_cooldowns()
        # ── M4: SYSTEMIC FLOW CONTINUATION (Radar Mechanism 4 — 3 Sep 2026) ──
        # State machine episode per simbol (2 arah) + feed z per currency (rolling 24-bar H1,
        # z-score warm 720 — metodologi identik scratch/study_mirror_flow.py). AKTIF forward test.
        self._m4_universe: List[str] = []                      # clean 6-huruf FX (exclude crypto + M4_EXCLUDED_PAIRS)
        self._m4_df: Dict[str, "pd.DataFrame"] = {}            # sym -> OHLC H1 closed (index = epoch server, sorted)
        self._m4_state: Dict[str, Dict[str, Dict[str, Any]]] = {}  # sym -> side(SELL/BUY) -> {ep, level, last_break, pending}
        self._m4_processed_ts: Dict[str, Optional[float]] = {} # sym -> epoch bar terakhir yang diproses state machine
        self._m4_z_last: Dict[str, float] = {}                 # currency -> z terbaru (konteks LLM/label)
        self._m4_feed_updated: float = 0.0                     # wall-clock terakhir feed di-refresh
        self._m4_feed_hour: Optional[int] = None               # jam WIB refresh feed (sekali per jam)
        self._last_snapshot_ts: float = 0.0                    # wall-clock snapshot 5-menit ke gate_debug.log
        self._retest_rejected_levels: Dict[str, Dict[str, Any]] = {} # sym -> {level, rejected_at, entry_atr} (1 Episode Retest Debounce)
        MarketScanner._instance = self

    def _load_cooldowns(self) -> Dict[str, float]:
        try:
            if os.path.exists(self._cooldown_file):
                with open(self._cooldown_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    now_ts = time.time()
                    return {k: float(v) for k, v in data.items() if (now_ts - float(v)) < 1800}
        except Exception:
            pass
        return {}

    def _save_cooldowns(self):
        try:
            now_ts = time.time()
            valid_cd = {k: v for k, v in self._symbol_last_trigger.items() if (now_ts - v) < 1800}
            with open(self._cooldown_file, "w", encoding="utf-8") as f:
                json.dump(valid_cd, f, indent=2)
        except Exception:
            pass

    def mark_symbol_cancelled(self, symbol: str, cooldown_seconds: int = 1800):
        """Applies a cooldown when a pending order is cancelled or expired."""
        clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
        now_ts = time.time()
        self._symbol_last_trigger[clean_sym] = now_ts + max(0, cooldown_seconds - 900)
        self._save_cooldowns()
        logger.info(f"⏳ Cooldown {cooldown_seconds // 60}m diaktifkan untuk {clean_sym} (Pending Cancelled/Expired).")

    def record_retest_rejection(self, symbol: str, level: float, current_atr: float = 0.0):
        """
        Mencatat level retest yang di-reject atau di-hold oleh 3-LLM Jury (1 Episode Retest Debounce).
        Kunci level tersebut dari trigger ulang sampai harga keluar (>0.5x ATR) atau 2 jam berlalu.
        """
        clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
        now_ts = time.time()
        self._retest_rejected_levels[clean_sym] = {
            "level": float(level),
            "rejected_at": now_ts,
            "entry_atr": float(current_atr)
        }
        # Naikkan juga symbol trigger cooldown ke minimal 45 menit
        self._symbol_last_trigger[clean_sym] = now_ts + 1800 # 45 min cooldown total
        self._save_cooldowns()
        logger.info(f"🔒 [RETEST REJECTION MEMORY] {clean_sym} dikunci pada level {level:.5f} (2 jam / displacement >0.50x ATR).")

    def is_retest_locked(self, symbol: str, current_mid: float, current_atr: float) -> Tuple[bool, str]:
        """
        True jika level masih terkunci dalam 1 Episode Retest Debounce:
        - Terkunci selama 2 jam (7200s), KECUALI harga bergerak keluar sejauh > 0.50x ATR.
        """
        clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
        rej = self._retest_rejected_levels.get(clean_sym)
        if not rej:
            return False, ""
        
        now_ts = time.time()
        elapsed = now_ts - rej["rejected_at"]
        max_duration = getattr(config, "M3_RETEST_DEBOUNCE_HOURS", 2.0) * 3600.0 # 7200s
        
        if elapsed >= max_duration:
            del self._retest_rejected_levels[clean_sym]
            return False, ""
            
        atr_ref = current_atr if current_atr > 0 else rej.get("entry_atr", 0.0)
        dist = abs(current_mid - rej["level"])
        if atr_ref > 0 and (dist > 0.50 * atr_ref):
            del self._retest_rejected_levels[clean_sym]
            return False, ""
            
        return True, f"level {rej['level']:.5f} previously rejected ({dist/atr_ref:.2f}x ATR <= 0.50x ATR, elapsed {elapsed/60:.1f}m < {max_duration/60:.0f}m)"

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

    # ═══════════════════════════════════════════════════════════════════════════
    # M4: SYSTEMIC FLOW CONTINUATION (Radar Mechanism 4 — 3 Sep 2026)
    # Studi #1 (scratch/study_surge_retest.py) & #1b mirror (scratch/study_mirror_flow.py):
    #   SELL saat quote surge (zQ>=+1.5) / base dump (zB<=-1.5); BUY saat base surge /
    #   quote dump. Breakdown swing 120-bar -> limit retest di level. SL struktural 0.45xATR,
    #   TP 1.1R (keputusan user; bypass floor/ceiling default di consensus._apply_sltp_rules).
    # ═══════════════════════════════════════════════════════════════════════════
    @staticmethod
    def _m4_clean(sym: str) -> Optional[str]:
        c = str(sym).replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
        if len(c) == 6 and c.isalpha():
            return c
        return None

    def _m4_build_universe(self):
        """Universe M4 = seluruh simbol FX scanner (26) dua arah, minus crypto & M4_EXCLUDED_PAIRS."""
        univ, cmap, bmap = [], {}, {}
        for s in config.get_scanner_symbols():
            c = self._m4_clean(s)
            if not c:
                continue
            if any(k in c for k in ("XAU", "GOLD", "XAG", "BTC", "SILVER", "US500", "NAS", "GER")):
                continue
            if c in config.M4_EXCLUDED_PAIRS:
                continue
            if c not in cmap:
                univ.append(c)
                cmap[c] = (c[:3], c[3:])
                bmap[c] = s  # nama broker asli untuk MT5 fetch
        self._m4_universe = univ
        self._m4_cur_map = cmap
        self._m4_broker = bmap

    def _m4_fetch_merge(self, sym_clean: str, cold: bool = False):
        """Fetch bar H1 CLOSED (pos=1 skip forming bar) lalu merge ke buffer per simbol."""
        broker = self._m4_broker.get(sym_clean, sym_clean)
        count = config.M4_COLD_FETCH_BARS if cold else config.M4_FETCH_BARS
        rates = None
        try:
            mt = getattr(config, "mt5", None)
            if mt is not None and hasattr(mt, "copy_rates_from_pos"):
                rates = mt.copy_rates_from_pos(broker, getattr(mt, "TIMEFRAME_H1", 16385), 1, count)
        except Exception:
            rates = None
        if rates is None or len(rates) == 0:
            return
        try:
            d = pd.DataFrame(rates)
            d = d[["time", "high", "low", "close"]].astype({"time": np.int64, "high": float, "low": float, "close": float})
            d = d.set_index("time").sort_index()
        except Exception:
            return
        prev = self._m4_df.get(sym_clean)
        merged = d if (prev is None or len(prev) == 0) else pd.concat([prev, d])
        merged = merged[~merged.index.duplicated(keep="last")].sort_index()
        self._m4_df[sym_clean] = merged.tail(max(config.M4_HIST_KEEP_BARS, config.M4_FLOW_WARM_BARS + 200))

    @staticmethod
    def _m4_wilder_atr(hi: np.ndarray, lo: np.ndarray, cl: np.ndarray, period: int = 14):
        n = len(cl)
        if n < period + 3:
            return None
        tr = np.empty(n)
        tr[0] = hi[0] - lo[0]
        for i in range(1, n):
            tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))
        atr = np.full(n, np.nan)
        atr[period] = tr[1:period + 1].mean()
        for i in range(period + 1, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
        return atr

    def _m4_refresh_z(self) -> bool:
        """Hitung z per currency (rolling 24-bar log-return, warm 720) di atas union index semua simbol."""
        closes = {}
        for c in self._m4_universe:
            df = self._m4_df.get(c)
            if df is not None and len(df) > 100:
                closes[c] = df["close"]
        if len(closes) < 4:
            return False
        all_close = pd.DataFrame(closes).sort_index()
        ret = np.log(all_close).diff()
        z_hist: Dict[str, "pd.Series"] = {}
        for cur in ("USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"):
            legs = []
            for c, (b, q) in getattr(self, "_m4_cur_map", {}).items():
                if c not in all_close.columns:
                    continue
                if b == cur:
                    legs.append((c, 1.0))
                elif q == cur:
                    legs.append((c, -1.0))
            if len(legs) < 3:
                continue
            cols = [x for x, _ in legs]
            sg = pd.Series({x: s for x, s in legs})
            part = ret[cols].mul(sg, axis=1)
            minp = max(3, len(cols) - 1)
            flow = part.mean(axis=1).where(part.count(axis=1) >= minp)
            idx24 = flow.rolling(config.M4_FLOW_LOOKBACK_BARS).sum()
            mu = idx24.rolling(config.M4_FLOW_WARM_BARS).mean()
            sd = idx24.rolling(config.M4_FLOW_WARM_BARS).std()
            z_hist[cur] = (idx24 - mu) / sd
        self._m4_z_hist = z_hist
        if z_hist:
            self._m4_z_last = {k: float(v.dropna().iloc[-1]) if v.notna().any() else 0.0 for k, v in z_hist.items()}
        return True

    def _m4_advance(self):
        """Proses bar H1 closed baru per simbol: trig episode z>=1.5 -> breakdown 120-bar -> pending."""
        for c in self._m4_universe:
            df = self._m4_df.get(c)
            if df is None or len(df) < 5:
                continue
            b, q = self._m4_cur_map.get(c, ("", ""))
            zb_all, zq_all = self._m4_z_hist.get(b), self._m4_z_hist.get(q)
            if zb_all is None or zq_all is None:
                continue
            zBser = zb_all.reindex(df.index).ffill()
            zQser = zq_all.reindex(df.index).ffill()
            n = len(df)
            last_ts = self._m4_processed_ts.get(c)
            start = 0 if last_ts is None else int(np.searchsorted(df.index.values, last_ts, side="right"))
            if start >= n:
                continue
            hi = df["high"].to_numpy()
            lo = df["low"].to_numpy()
            cl = df["close"].to_numpy()
            atr = self._m4_wilder_atr(hi, lo, cl, 14)
            st_all = self._m4_state.setdefault(c, {
                "SELL": {"ep": None, "level": None, "last_break": None, "pending": None},
                "BUY": {"ep": None, "level": None, "last_break": None, "pending": None},
            })
            for p in range(start, n):
                zbv = zBser.iloc[p]
                zqv = zQser.iloc[p]
                try:
                    if np.isnan(float(zbv)) or np.isnan(float(zqv)):
                        continue
                except Exception:
                    continue
                self._m4_step_side(st_all["SELL"], -1, p, float(zbv), float(zqv), cl, lo, hi, atr)
                self._m4_step_side(st_all["BUY"], 1, p, float(zbv), float(zqv), cl, lo, hi, atr)
            self._m4_processed_ts[c] = float(df.index[-1])

    def _m4_step_side(self, st: dict, side: int, p: int, zb: float, zq: float,
                      cl: np.ndarray, lo: np.ndarray, hi: np.ndarray, atr):
        """Translasi 1:1 state machine studi mirror ke bar H1 live (per sisi SELL/BUY)."""
        EP = config.M4_TRIGGER_Z
        CT = config.M4_CONT_Z
        conflict = (zb >= EP and zq >= EP) or (zb <= -EP and zq <= -EP)
        if side == -1:  # SELL: quote surge / base dump
            trig = (not conflict) and (zb <= -EP or zq >= EP)
            cont = (not conflict) and (zb <= -CT or zq >= CT)
        else:           # BUY: base surge / quote dump
            trig = (not conflict) and (zb >= EP or zq <= -EP)
            cont = (not conflict) and (zb >= CT or zq <= -CT)
        # 1) pending fill-wait kadaluarsa (studi MAX_WAIT)
        if st.get("pending") is not None:
            if (p - st["pending"]["break_pos"]) >= config.M4_MAX_WAIT_BARS:
                st["pending"] = None
        # 2) episode hidup?
        if st.get("ep") is not None:
            if not cont:
                st["ep"] = None
                st["level"] = None
            elif (p - st["ep"]) >= config.M4_MIN_EPISODE_BARS:
                level = st.get("level")
                if level is None:
                    st["ep"] = None
                    return
                broke = (cl[p] < level) if side == -1 else (cl[p] > level)
                gap_ok = st.get("last_break") is None or (p - st["last_break"]) >= config.M4_MIN_GAP_BARS
                if broke and gap_ok:
                    st["last_break"] = p
                    atr_p = None
                    if atr is not None and p < len(atr) and not np.isnan(atr[p]):
                        atr_p = float(atr[p])
                    if atr_p and atr_p > 0:
                        R = config.M4_SL_ATR_MULT * atr_p
                        if side == -1:
                            sl, tp = level + R, level - config.M4_TP_R_MULT * R
                        else:
                            sl, tp = level - R, level + config.M4_TP_R_MULT * R
                        st["pending"] = {"break_pos": p, "level": float(level), "atr": atr_p,
                                         "sl": float(sl), "tp": float(tp)}
        else:
            if trig:
                w0 = max(0, p - config.M4_LOOKBACK_BARS)
                st["ep"] = p
                # level = swing 120-bar SEBELUM episode: SELL pakai lantai low, BUY pakai atap high (studi 1:1)
                st["level"] = float(hi[w0:p].max()) if side == 1 else float(lo[w0:p].min())

    def _m4_feed_refresh(self):
        """Refresh feed currency-z M4 — sekali per jam WIB (0 token LLM, ~26x900 bar H1 cold)."""
        if not config.M4_ENABLED:
            return
        now_h = datetime.now(WIB).hour
        if self._m4_feed_updated > 0.0 and self._m4_feed_hour == now_h:
            return
        self._m4_feed_hour = now_h
        try:
            if not self._m4_universe:
                self._m4_build_universe()
            cold = self._m4_feed_updated <= 0.0
            for c in self._m4_universe:
                try:
                    self._m4_fetch_merge(c, cold)
                except Exception as e:
                    logger.debug(f"M4 fetch error {c}: {e}")
            if not self._m4_refresh_z():
                return
            self._m4_advance()
        except Exception as e:
            logger.debug(f"M4 feed refresh error: {e}")
            return
        self._m4_feed_updated = time.time()

    def _m4_pending_ready(self, sym_clean: str, side_key: str, mid: float, atr_now: float) -> Optional[dict]:
        """Ambil pending M4 yang valid & sedang dalam band pendekatan retest level."""
        st = self._m4_state.get(sym_clean, {}).get(side_key)
        if not st:
            return None
        pend = st.get("pending")
        if not pend:
            return None
        level = pend["level"]
        atr_ref = max(pend.get("atr", atr_now), atr_now) if atr_now > 0 else pend.get("atr", 0.0)
        if atr_ref <= 0:
            return None
        band = config.M4_EMIT_BAND_ATR * atr_ref
        tol = 0.10 * atr_ref
        if side_key == "SELL":
            # harga mendekati level dari bawah (retest) — belum reclaim jauh di atas level
            if not (level - band <= mid <= level + tol):
                return None
        else:
            if not (level - tol <= mid <= level + band):
                return None
        return pend

    @staticmethod
    def _is_m4_supported(sym_clean: str) -> bool:
        if not sym_clean or len(sym_clean) != 6 or not sym_clean.isalpha():
            return False
        if any(k in sym_clean for k in ("XAU", "GOLD", "XAG", "BTC")):
            return False
        return sym_clean not in config.M4_EXCLUDED_PAIRS

    @staticmethod
    def is_symbol_allowed_for_session(symbol: str, hour_wib: int) -> bool:
        """
        Filters symbols based on active session currency drivers:
        - Tokyo Session (08:00 - 14:00 WIB): Any symbol containing Asian/Pacific drivers (JPY, AUD, NZD) is allowed
          (e.g., AUDCAD, CADJPY, NZDCAD, EURJPY, GBPJPY, CHFJPY, AUDUSD, NZDUSD, GBPAUD, EURNZD, etc.).
          Symbols without JPY/AUD/NZD (e.g., EURCAD, GBPCAD, USDCAD, EURUSD, GBPUSD, USDCHF, EURCHF, etc.) are locked.
        - London & NY Sessions (14:00 - 23:59 WIB): Allow all configured pairs.
        """
        if 8 <= hour_wib < 14:
            return config.is_asian_session_pair(symbol)
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
            "max_high": mid,
            "max_low": mid,
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
                "prev_body_ratio": prev_qual.get('body_ratio', 0.35),
                "live_high": cur_h,
                "live_low": cur_l,
                "max_high": max(cur_h, prev_h),
                "max_low": min(cur_l, prev_l),
            }
        except Exception as e:
            logger.debug(f"Error classifying candle for {sym}: {e}")
            return default_res

    def find_ema_confluence_anchor(
        self,
        symbol: str,
        mid: float,
        direction: int,
        macro: Dict[str, Any],
        pt: float = 0.00001,
        atr_val: float = 0.0060
    ) -> Tuple[float, str]:
        """
        Pure Quant EMA Confluence Anchor Finder for Mechanism 2 (Trend-Aligned Pullback).
        Calculates the institutional confluence between the dynamic EMA20/50 corridor
        and real price structure:
          1. SMC Unmitigated Order Block (OB)
          2. Structural Wall (Floor F1 for BUY, Ceiling C1 for SELL)
          3. SMC Fair Value Gap (FVG)
          4. Atlas DNA Psychological Stations (1.0x Super, 0.5x Sub, or 0.25x Quarter Step)
        Prioritizes the nearest institutional barrier tested during a pullback.
        """
        clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
        digits = 3 if "JPY" in clean_sym else 5
        pt = pt if pt > 0 else (0.001 if "JPY" in clean_sym else 0.00001)
        m_atr = float(macro.get('current_atr') or 0.0)
        atr_val = m_atr if m_atr > 0 else (atr_val if atr_val > 0 else 60.0 * pt)
        step = get_symbol_step(clean_sym)

        ema20 = float(macro.get('ema20', mid) or mid)
        ema50 = float(macro.get('ema50', ema20) or ema20)
        corridor_lo = min(ema20, ema50)
        corridor_hi = max(ema20, ema50)
        corridor_pad = 0.50 * atr_val

        candidates = []

        if direction == 1:
            # Bullish Pullback: Support level must be <= mid
            ob_top = float(macro.get('bullish_ob_top', 0.0) or 0.0)
            if ob_top > 0 and ob_top <= mid:
                candidates.append((ob_top, f"Bullish OB ({ob_top:.{digits}f})", 1))

            f1 = float(macro.get('immediate_floor_f1', 0.0) or 0.0)
            if f1 > 0 and f1 <= mid:
                candidates.append((f1, f"F1 Structural Floor ({f1:.{digits}f})", 2))

            fvg_top = float(macro.get('bullish_fvg_top', 0.0) or 0.0)
            if fvg_top > 0 and fvg_top <= mid:
                candidates.append((fvg_top, f"Bullish FVG ({fvg_top:.{digits}f})", 3))

            search_lo = min(corridor_lo - corridor_pad, mid - 1.5 * atr_val)
            search_hi = min(corridor_hi + corridor_pad, mid)
            for frac in [1.0, 0.5, 0.25]:
                g_step = step * frac
                min_k = int(search_lo / g_step)
                max_k = int(search_hi / g_step) + 1
                for k in range(min_k, max_k):
                    p_lvl = round(k * g_step, digits)
                    if search_lo <= p_lvl <= search_hi and p_lvl <= mid:
                        candidates.append((p_lvl, f"Atlas Psych Level ({p_lvl:.{digits}f})", 4))
        else:
            # Bearish Pullback: Resistance level must be >= mid
            ob_bot = float(macro.get('bearish_ob_bot', 0.0) or 0.0)
            if ob_bot > 0 and ob_bot >= mid:
                candidates.append((ob_bot, f"Bearish OB ({ob_bot:.{digits}f})", 1))

            c1 = float(macro.get('immediate_ceiling_c1', 0.0) or 0.0)
            if c1 > 0 and c1 >= mid:
                candidates.append((c1, f"C1 Structural Ceiling ({c1:.{digits}f})", 2))

            fvg_bot = float(macro.get('bearish_fvg_bot', 0.0) or 0.0)
            if fvg_bot > 0 and fvg_bot >= mid:
                candidates.append((fvg_bot, f"Bearish FVG ({fvg_bot:.{digits}f})", 3))

            search_lo = max(corridor_lo - corridor_pad, mid)
            search_hi = max(corridor_hi + corridor_pad, mid + 1.5 * atr_val)
            for frac in [1.0, 0.5, 0.25]:
                g_step = step * frac
                min_k = int(search_lo / g_step)
                max_k = int(search_hi / g_step) + 1
                for k in range(min_k, max_k):
                    p_lvl = round(k * g_step, digits)
                    if search_lo <= p_lvl <= search_hi and p_lvl >= mid:
                        candidates.append((p_lvl, f"Atlas Psych Level ({p_lvl:.{digits}f})", 4))

        if candidates:
            valid_cands = [c for c in candidates if abs(c[0] - mid) <= 3.0 * atr_val]
            if not valid_cands:
                valid_cands = candidates
            valid_cands.sort(key=lambda x: (abs(x[0] - mid), x[2]))
            best_price, best_desc, _ = valid_cands[0]
            label_prefix = "Bullish Pullback (EMA + " if direction == 1 else "Bearish Pullback (EMA + "
            return round(best_price, digits), f"{label_prefix}{best_desc} Confluence)"
        else:
            fallback = round(mid - 0.5 * atr_val, digits) if direction == 1 else round(mid + 0.5 * atr_val, digits)
            label_prefix = "Bullish Pullback (EMA + " if direction == 1 else "Bearish Pullback (EMA + "
            return round(fallback, digits), f"{label_prefix}Dynamic Barrier {fallback:.{digits}f} Confluence)"

    def get_radar_standbys(self, symbol: str, mid: float, macro: Optional[Dict[str, Any]] = None, pt: float = 0.00001, atr_val: float = 0.0060) -> List[Dict[str, Any]]:
        """
        Pure Quant 1:1 Radar Standby Extractor with Temporal Point Tracking.
        Calculates the exact institutional price targets and standbys evaluated by
        Stage 1 Fast Radar across M1, M2, M3, and M4 for live observation and cockpit telemetry.
        Includes temporal occurrence timestamps (event_time), bar_age, and projected time for precise tracking.
        """
        if mid <= 0:
            return []

        clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
        if macro is None:
            macro = self.macro_cache.get(symbol) or self.macro_cache.get(clean_sym) or {}

        digits = 3 if "JPY" in clean_sym else 5
        pt = pt if pt > 0 else (0.001 if "JPY" in clean_sym else 0.00001)
        m_atr = float(macro.get('current_atr') or 0.0)
        atr_val = m_atr if m_atr > 0 else (atr_val if atr_val > 0 else 60.0 * pt)
        tf_mins = 30 if "JPY" in clean_sym else 60

        is_bull = bool(macro.get("is_bull", False))
        is_bear = bool(macro.get("is_bear", False))
        m_corr = str(macro.get("macro_corridor", "NEUTRAL"))

        dr_pos = float(macro.get('dealing_range_pos', 0.5) or 0.5)

        df = macro.get('df')

        standbys = []

        # ── 1. M1: UNIVERSAL LIQUIDITY SWEEP & SFP ──
        asian_h = float(macro.get('asian_high', 0.0) or 0.0)
        asian_l = float(macro.get('asian_low', 0.0) or 0.0)
        pdh_val = float(macro.get('pdh', 0.0) or 0.0)
        pdl_val = float(macro.get('pdl', 0.0) or 0.0)
        pwh_val = float(macro.get('pwh', 0.0) or 0.0)
        pwl_val = float(macro.get('pwl', 0.0) or 0.0)
        c1_val = float(macro.get('immediate_ceiling_c1') or pwh_val or 0.0)
        f1_val = float(macro.get('immediate_floor_f1') or pwl_val or 0.0)

        m1_price = 0.0
        m1_lbl = "Universal Sweep Target"
        m1_event_time = 0
        m1_bar_age = 0
        m1_status = "WAITING_SWEEP"
        m1_dir = -1 if (dr_pos >= 0.50 or is_bear) else 1

        if dr_pos >= 0.50 or is_bear:
            valid_tops = [v for v in [asian_h, pdh_val, pwh_val, c1_val] if v > 0 and v >= mid - 0.15 * atr_val]
            m1_price = min(valid_tops) if valid_tops else (c1_val or asian_h or (mid + 0.5 * atr_val))
            m1_lbl = "Bearish Sweep Resistance (SFP High)"

            # Temporal sweep detection in recent bars
            if df is not None and len(df) >= 3:
                pierce_bars = [i for i in range(max(0, len(df) - 10), len(df)) if df.iloc[i]['high'] >= m1_price - 0.15 * atr_val]
                if pierce_bars:
                    best_i = max(pierce_bars, key=lambda idx: df.iloc[idx]['high'])
                    m1_event_time = int(df.index[best_i].timestamp())
                    m1_bar_age = len(df) - 1 - best_i
                    m1_status = "RECLAIMED_FADING" if df.iloc[best_i]['close'] < m1_price else "WAITING_CLOSE_RECLAIM"
        else:
            valid_bots = [v for v in [asian_l, pdl_val, pwl_val, f1_val] if v > 0 and v <= mid + 0.15 * atr_val]
            m1_price = max(valid_bots) if valid_bots else (f1_val or asian_l or (mid - 0.5 * atr_val))
            m1_lbl = "Bullish Sweep Support (SFP Low)"

            # Temporal sweep detection in recent bars
            if df is not None and len(df) >= 3:
                pierce_bars = [i for i in range(max(0, len(df) - 10), len(df)) if df.iloc[i]['low'] <= m1_price + 0.15 * atr_val]
                if pierce_bars:
                    best_i = min(pierce_bars, key=lambda idx: df.iloc[idx]['low'])
                    m1_event_time = int(df.index[best_i].timestamp())
                    m1_bar_age = len(df) - 1 - best_i
                    m1_status = "RECLAIMED_FADING" if df.iloc[best_i]['close'] > m1_price else "WAITING_CLOSE_RECLAIM"

        if m1_price > 0:
            standbys.append({
                "type": "M1",
                "price": round(m1_price, digits),
                "label": m1_lbl,
                "event_time": m1_event_time,
                "status": m1_status,
                "bar_age": m1_bar_age,
                "direction": m1_dir
            })

        # ── 2. M2: TREND-ALIGNED MULTI-TIMEFRAME PULLBACK & RETEST (CONFLUENCE) ──
        m2_dir = 1 if (is_bull or m_corr == "BULLISH_CORRIDOR") else -1
        m2_price, m2_lbl = self.find_ema_confluence_anchor(symbol, mid, m2_dir, macro, pt, atr_val)

        if m2_price > 0:
            m2_event_time = 0
            m2_status = "PROJECTED_PULLBACK"
            m2_bar_age = 0

            dist_pts = abs(mid - m2_price)
            est_bars = max(1, int(round(dist_pts / (0.45 * atr_val)))) if atr_val > 0 else 2
            est_time_str = f"~{est_bars * tf_mins}m" if est_bars * tf_mins < 120 else f"~{est_bars * tf_mins / 60:.1f}h"

            # Check if any recent bar already tested this zone
            if df is not None and len(df) >= 3:
                lookback = min(10, len(df))
                for i in range(len(df) - lookback, len(df)):
                    bar = df.iloc[i]
                    if m2_dir == 1:
                        if bar['low'] <= m2_price + 0.20 * atr_val and bar['close'] >= m2_price - 0.25 * atr_val:
                            m2_event_time = int(df.index[i].timestamp())
                            m2_bar_age = len(df) - 1 - i
                            m2_status = "RETEST_ACTIVE"
                    else:
                        if bar['high'] >= m2_price - 0.20 * atr_val and bar['close'] <= m2_price + 0.25 * atr_val:
                            m2_event_time = int(df.index[i].timestamp())
                            m2_bar_age = len(df) - 1 - i
                            m2_status = "RETEST_ACTIVE"

            standbys.append({
                "type": "M2",
                "price": round(m2_price, digits),
                "label": m2_lbl,
                "event_time": m2_event_time,
                "status": m2_status,
                "bar_age": m2_bar_age,
                "direction": m2_dir,
                "est_bars": est_bars,
                "est_time": est_time_str
            })

        # ── 3. M3: MULTI-TOUCH CLUSTER BREAKOUT & DELAYED RETEST ──
        c_res = float(macro.get('cluster_resistance', 0.0) or 0.0)
        c_sup = float(macro.get('cluster_support', 0.0) or 0.0)
        t_res = int(macro.get('touches_resistance', 0) or 0)
        t_sup = int(macro.get('touches_support', 0) or 0)
        pdh_b = float(macro.get('pdh', 0.0) or 0.0)
        pwh_b = float(macro.get('pwh', 0.0) or 0.0)
        pdl_b = float(macro.get('pdl', 0.0) or 0.0)
        pwl_b = float(macro.get('pwl', 0.0) or 0.0)
        bos_b = float(macro.get('h1_bos_level', 0.0) or 0.0) if macro.get('h1_bos_direction') == 'bullish' else 0.0
        bos_s = float(macro.get('h1_bos_level', 0.0) or 0.0) if macro.get('h1_bos_direction') == 'bearish' else 0.0
        rbs_b = float(macro.get('micro_rbs_h1') or macro.get('inter_rbs_h4') or 0.0)
        sbr_b = float(macro.get('micro_sbr_h1') or macro.get('inter_sbr_h4') or 0.0)
        f1_floor = float(macro.get('immediate_floor_f1', 0.0) or 0.0)
        c1_ceiling = float(macro.get('immediate_ceiling_c1', 0.0) or 0.0)

        m3_price = 0.0
        m3_lbl = "SBR/RBS Breakout Retest"
        m3_dir = 1 if (is_bull or m_corr == "BULLISH_CORRIDOR") else -1
        m3_event_time = 0
        m3_bar_age = 0
        m3_status = "WAITING_RETEST"

        if m3_dir == 1:
            # Priority 1: Multi-Touch Cluster with >= 2 touches
            if c_res > 0 and t_res >= 2 and c_res < mid:
                m3_price = c_res
                m3_lbl = f"Multi-Touch Cluster Breakout ({t_res}x Touches)"
            elif f1_floor > 0 and f1_floor < mid and abs(mid - f1_floor) <= 2.5 * atr_val:
                m3_price = f1_floor
                m3_lbl = "Breakout Structural Floor (F1 Retest)"
            else:
                cand_res = [lvl for lvl in (pdh_b, pwh_b, bos_b, rbs_b) if (lvl > 0 and lvl < mid)]
                m3_price = max(cand_res) if cand_res else (rbs_b or f1_floor or 0.0)
                m3_lbl = "Broken Resistance RBS Retest"

            # Temporal breakout detection
            if df is not None and len(df) >= 3 and m3_price > 0:
                lookback = min(20, len(df))
                for i in range(len(df) - lookback, len(df)):
                    p_bar = df.iloc[i - 1]
                    c_bar = df.iloc[i]
                    if (p_bar['close'] <= m3_price and c_bar['close'] > m3_price) or (p_bar['high'] <= m3_price and c_bar['close'] > m3_price):
                        m3_event_time = int(df.index[i].timestamp())
                        m3_bar_age = len(df) - 1 - i
                        m3_status = "WAITING_RETEST" if mid > m3_price else "RETEST_ACTIVE"
        else:
            if c_sup > 0 and t_sup >= 2 and c_sup > mid:
                m3_price = c_sup
                m3_lbl = f"Multi-Touch Cluster Breakdown ({t_sup}x Touches)"
            elif c1_ceiling > 0 and c1_ceiling > mid and abs(c1_ceiling - mid) <= 2.5 * atr_val:
                m3_price = c1_ceiling
                m3_lbl = "Breakdown Structural Ceiling (C1 Retest)"
            else:
                cand_sup = [lvl for lvl in (pdl_b, pwl_b, bos_s, sbr_b) if (lvl > 0 and lvl > mid)]
                m3_price = min(cand_sup) if cand_sup else (sbr_b or c1_ceiling or 0.0)
                m3_lbl = "Broken Support SBR Retest"

            # Temporal breakdown detection
            if df is not None and len(df) >= 3 and m3_price > 0:
                lookback = min(20, len(df))
                for i in range(len(df) - lookback, len(df)):
                    p_bar = df.iloc[i - 1]
                    c_bar = df.iloc[i]
                    if (p_bar['close'] >= m3_price and c_bar['close'] < m3_price) or (p_bar['low'] >= m3_price and c_bar['close'] < m3_price):
                        m3_event_time = int(df.index[i].timestamp())
                        m3_bar_age = len(df) - 1 - i
                        m3_status = "WAITING_RETEST" if mid < m3_price else "RETEST_ACTIVE"

        if m3_price > 0:
            standbys.append({
                "type": "M3",
                "price": round(m3_price, digits),
                "label": m3_lbl,
                "event_time": m3_event_time,
                "status": m3_status,
                "bar_age": m3_bar_age,
                "direction": m3_dir
            })

        # ── 4. M4: SYSTEMIC FLOW CONTINUATION ──
        if hasattr(self, "_m4_state"):
            for side in ("SELL", "BUY"):
                p = self._m4_state.get(clean_sym, {}).get(side, {}).get("pending")
                if p and p.get("level"):
                    standbys.append({
                        "type": "M4",
                        "price": round(float(p.get("level")), digits),
                        "label": f"Systemic Flow Limit ({side})",
                        "event_time": int(df.index[-1].timestamp()) if (df is not None and len(df) > 0) else 0,
                        "status": "WAITING_FLOW_RETEST",
                        "bar_age": 0,
                        "direction": 1 if side == "BUY" else -1
                    })
        return standbys

    def update_macro_context(self, mt5_connector=None, force: bool = False) -> None:
        """
        Updates multi-timeframe macro indicators (D1 Trend, H4 Order Blocks, Asian Range, 100-bar Dealing Range).
        Cached & di-refresh per interval _zce_refresh_due_seconds() (900s saat ZCE legacy/full, 3600s default)
        atau saat force=True. (Patch #1, 2 Sep 2026: hour-gate -> elapsed-gate agar dinding ZCE tidak basi ~60 mnt.)
        """
        now = datetime.now(WIB)
        max_age_s = self._zce_refresh_due_seconds()
        if not force and self.last_macro_update is not None:
            if (now - self.last_macro_update).total_seconds() <= max_age_s:
                return

        logger.info(f"🔄 Updating Macro Context Layer for {len(self.symbols)} symbols in parallel (Hour: {now.hour}:00 WIB)...")
        
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(self._build_single_macro_context, s, mt5_connector, now) for s in self.symbols]
            for f in futures:
                res = f.result()
                if res is not None:
                    valid_sym, data = res
                    self.macro_cache[valid_sym] = data

        self.last_macro_update = now
        logger.info(f"✅ Macro Context Layer updated for {len(self.macro_cache)}/{len(self.symbols)} symbols.")

    def _build_single_macro_context(self, sym: str, mt5_connector=None, now=None) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Calculates single-symbol macro context in isolation (thread-safe)."""
        if now is None:
            now = datetime.now(WIB)
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
                return None

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
                
                # SMC Structural Anchor on D1: Mutually exclusive & responsive to breakdowns
                if len(df_d1) >= 20:
                    d1_smc = LuxSMCAnalyzer(swing_length=3).analyze(df_d1, point_size=pt)
                    d1_anchor_low = d1_smc.strong_low if d1_smc.strong_low > 0 else d1_50_lo
                    d1_anchor_high = d1_smc.strong_high if d1_smc.strong_high > 0 else d1_50_hi
                    
                    if (d1_c >= d1_ema_short and d1_c >= d1_ema_long) and (d1_c > d1_anchor_low):
                        d1_is_bull = True
                        d1_is_bear = False
                        d1_trend_label = "D1_BULLISH_EXPANSION"
                    elif (d1_c <= d1_ema_short and d1_c <= d1_ema_long) and (d1_c < d1_anchor_high):
                        d1_is_bull = False
                        d1_is_bear = True
                        d1_trend_label = "D1_BEARISH_EXPANSION"
                    elif d1_c < d1_ema_short and d1_ema_short > d1_ema_long:
                        d1_is_bull = False
                        d1_is_bear = True
                        d1_trend_label = "D1_BEARISH_PULLBACK"
                    elif d1_c > d1_ema_short and d1_ema_short < d1_ema_long:
                        d1_is_bull = True
                        d1_is_bear = False
                        d1_trend_label = "D1_BULLISH_PULLBACK"
                    else:
                        d1_is_bull = False
                        d1_is_bear = False
                        d1_trend_label = "D1_SIDEWAYS"
                else:
                    if d1_c > d1_ema_long and d1_ema_short >= d1_ema_long:
                        d1_is_bull = True
                        d1_is_bear = False
                        d1_trend_label = "D1_BULLISH_EXPANSION"
                    elif d1_c < d1_ema_long and d1_ema_short <= d1_ema_long:
                        d1_is_bull = False
                        d1_is_bear = True
                        d1_trend_label = "D1_BEARISH_EXPANSION"
                    else:
                        d1_is_bull = False
                        d1_is_bear = False
                        d1_trend_label = "D1_SIDEWAYS"

            cur_day_move = abs(cur_close - daily_open)
            adr_used_pct = (cur_day_move / adr20) if (adr20 > 0) else 0.5

            # ── 2. H4 DISCRETE LEVEL, SMC SWING ANCHOR & MONTHLY RANGE ──
            h4_is_bull = False
            h4_is_bear = False
            h4_trend_label = "H4_SIDEWAYS"
            h4_swing_high = pdh
            h4_swing_low = pdl
            h4_monthly_range_str = f"[{pdl:.5f} - {pdh:.5f}]"
            is_h4_ranging = False
            is_h4_flag_triangle = False
            h4_dr_pos = 0.5
            h4_bos_count = 0

            if rates_h4 is not None and len(rates_h4) >= 5:
                df_h4 = pd.DataFrame(rates_h4)
                h4_c = float(df_h4['close'].iloc[-1])
                h4_ema20 = df_h4['close'].ewm(span=20, adjust=False).mean().iloc[-1]
                h4_ema50 = df_h4['close'].ewm(span=50, adjust=False).mean().iloc[-1] if len(df_h4) >= 15 else h4_ema20
                
                if len(df_h4) >= 25:
                    h4_smc = LuxSMCAnalyzer(swing_length=5).analyze(df_h4, point_size=pt)
                    h4_swing_high = h4_smc.strong_high if h4_smc.strong_high > 0 else float(df_h4['high'].iloc[-12:].max())
                    h4_swing_low = h4_smc.strong_low if h4_smc.strong_low > 0 else float(df_h4['low'].iloc[-12:].min())
                    is_h4_ranging = h4_smc.is_ranging_box
                    is_h4_flag_triangle = h4_smc.is_triangle_compression
                    h4_dr_pos = h4_smc.dealing_range_pos
                    h4_bos_count = h4_smc.bos_count

                    if is_h4_ranging or is_h4_flag_triangle:
                        h4_is_bull = False
                        h4_is_bear = False
                        h4_trend_label = "H4_RANGING_FLAG_BOX" if is_h4_flag_triangle else "H4_SIDEWAYS_RANGE"
                    else:
                        if (h4_c >= h4_ema20 and h4_c >= h4_ema50) and (h4_c > h4_swing_low):
                            h4_is_bull = True
                            h4_is_bear = False
                            h4_trend_label = "H4_BULLISH_EXPANSION"
                        elif (h4_c <= h4_ema20 and h4_c <= h4_ema50) and (h4_c < h4_swing_high):
                            h4_is_bull = False
                            h4_is_bear = True
                            h4_trend_label = "H4_BEARISH_EXPANSION"
                        elif h4_c < h4_ema20 and h4_ema20 >= h4_ema50:
                            h4_is_bull = False
                            h4_is_bear = True
                            h4_trend_label = "H4_BEARISH_PULLBACK"
                        elif h4_c > h4_ema20 and h4_ema20 <= h4_ema50:
                            h4_is_bull = True
                            h4_is_bear = False
                            h4_trend_label = "H4_BULLISH_PULLBACK"
                        else:
                            h4_is_bull = False
                            h4_is_bear = False
                            h4_trend_label = "H4_PULLBACK_RANGE"
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
                zce_walls = None
                if getattr(config, "ZCE_ENABLED", False) and getattr(config, "ZCE_MODE", "shadow") in ("legacy", "full"):
                    zm = getattr(self, "_zce_maps", {}).get(valid_sym)
                    if zm is None:
                        # Patch #1 (2 Sep 2026): macro_cache TIDAK boleh dibangun tanpa dinding
                        # ZCE — compute inline bila peta belum ada (cold start / boot force /
                        # rebuild pertama setelah weekend & dead zone). Aman dari thread worker
                        # karena _compute_zce_map_for membuat engine lokal saat eng=None.
                        zm = self._compute_zce_map_for(valid_sym, mt5_connector=mt5_connector)
                    if zm is not None:
                        w = zm.wall_override
                        # Override PER-SISI (fix INV-2): cukup SATU sisi non-None —
                        # MSE mengisi sisi yang kosong dengan baseline-nya sendiri.
                        if w.get("imm_floor_f1") is not None or w.get("imm_ceiling_c1") is not None:
                            zce_walls = w  # dinding ZCE (RFC 11 Phase-2)
                strat_dir = macro_strategic_engine.get_directive(valid_sym, mt5_connector=mt5_connector, zce_walls=zce_walls)
            except Exception as e_strat:
                logger.debug(f"[STRAT ENGINE] Error computing directive for {valid_sym}: {e_strat}")

            # Determine ZCE wall attribution for this symbol (Lapis 4 audit)
            zce_class = "MSE_BASE"
            zce_f1_src = "MSE"
            zce_c1_src = "MSE"
            if zce_walls is not None and strat_dir is not None:
                _zw_f1 = zce_walls.get("imm_floor_f1")
                _zw_c1 = zce_walls.get("imm_ceiling_c1")
                _sd_f1 = getattr(strat_dir, 'immediate_floor_f1', None)
                _sd_c1 = getattr(strat_dir, 'immediate_ceiling_c1', None)
                if _zw_f1 is not None and _sd_f1 == _zw_f1:
                    zce_f1_src = "ZCE"
                if _zw_c1 is not None and _sd_c1 == _zw_c1:
                    zce_c1_src = "ZCE"
                if zce_f1_src == "ZCE" and zce_c1_src == "ZCE":
                    zce_class = "ZCE_FULL"
                elif zce_f1_src == "ZCE" or zce_c1_src == "ZCE":
                    zce_class = "ZCE_MIXED"

            zce_meta = {
                "zce_class": zce_class,
                "zce_f1_src": zce_f1_src,
                "zce_c1_src": zce_c1_src,
                "zce_f1_price": round(float(getattr(strat_dir, 'immediate_floor_f1', 0.0) or 0.0), 5 if pt < 0.01 else 3),
                "zce_c1_price": round(float(getattr(strat_dir, 'immediate_ceiling_c1', 0.0) or 0.0), 5 if pt < 0.01 else 3),
            }

            # HTF Delivery Vector Memory (Gate B for Judas Sweep)
            recent_ceiling_touch = False
            recent_floor_touch = False
            if pwh > 0 and pwl > 0:
                h4_tail_hi = float(df_h4['high'].iloc[-8:].max()) if (rates_h4 is not None and len(rates_h4) >= 8 and len(df_h4) >= 8) else float(df['high'].iloc[-24:].max())
                h4_tail_lo = float(df_h4['low'].iloc[-8:].min()) if (rates_h4 is not None and len(rates_h4) >= 8 and len(df_h4) >= 8) else float(df['low'].iloc[-24:].min())
                recent_ceiling_touch = (h4_tail_hi >= (pwh - (cur_atr * 0.25))) or (pos_in_range >= 0.85)
                recent_floor_touch = (h4_tail_lo <= (pwl + (cur_atr * 0.25))) or (pos_in_range <= 0.15)

            htf_delivery = "NEUTRAL"
            if recent_ceiling_touch and cur_close < cur_ema20:
                htf_delivery = "BEARISH_DELIVERY_FROM_CEILING"
            elif recent_floor_touch and cur_close > cur_ema20:
                htf_delivery = "BULLISH_DELIVERY_FROM_FLOOR"

            # Direct MSE 6-TF Action Tier mapping to Permission State
            mse_tier = getattr(strat_dir, 'action_tier', 'FULL_ALLOW') if strat_dir else 'FULL_ALLOW'
            if mse_tier == "FULL_ALLOW":
                derived_perm = "GO" if (pos_in_range <= 0.20 or pos_in_range >= 0.80) else "ARM"
            elif mse_tier in ("TP1_ONLY_SCALP", "REDUCED_CONFIDENCE"):
                derived_perm = "ARM"
            elif mse_tier == "WATCH_ONLY":
                derived_perm = "WATCH"
            elif mse_tier == "HARD_BLOCK":
                derived_perm = "LOCK"
            else:
                derived_perm = "WATCH"

            # Harmonize D1 trend label and directional flags with MSE Macro Bias (Single Source of Truth)
            mse_bias_score = getattr(strat_dir, 'macro_bias_score', 0.0) if strat_dir else 0.0
            if mse_bias_score <= -0.35:
                d1_is_bull = False
                d1_is_bear = True
                d1_trend_label = "D1_BEARISH_EXPANSION" if d1_c <= d1_ema_long else "D1_BEARISH_PULLBACK"
            elif mse_bias_score >= 0.35:
                d1_is_bull = True
                d1_is_bear = False
                d1_trend_label = "D1_BULLISH_EXPANSION" if d1_c >= d1_ema_long else "D1_BULLISH_PULLBACK"

            combined_trend_label = f"{d1_trend_label} | {h4_trend_label}"

            # Monotonic levels guarantee: F2 < F1 < C1 < C2
            eff_f1 = getattr(strat_dir, 'immediate_floor_f1', 0.0) if strat_dir else 0.0
            eff_c1 = getattr(strat_dir, 'immediate_ceiling_c1', 0.0) if strat_dir else 0.0
            raw_c2 = (strat_dir.ceiling_c2 if (strat_dir and getattr(strat_dir, 'ceiling_c2', None)) else (getattr(strat_dir, 'deep_target_ceiling_c2', 0.0) if strat_dir else 0.0))
            raw_f2 = (strat_dir.floor_f2 if (strat_dir and getattr(strat_dir, 'floor_f2', None)) else (getattr(strat_dir, 'deep_target_floor_f2', 0.0) if strat_dir else 0.0))
            eff_c2 = raw_c2 if (raw_c2 and raw_c2 > eff_c1) else (getattr(strat_dir, 'deep_target_ceiling_c2', 0.0) if (getattr(strat_dir, 'deep_target_ceiling_c2', 0.0) > eff_c1) else 0.0)
            eff_f2 = raw_f2 if (raw_f2 and raw_f2 < eff_f1) else (getattr(strat_dir, 'deep_target_floor_f2', 0.0) if (getattr(strat_dir, 'deep_target_floor_f2', 0.0) < eff_f1) else 0.0)

            return valid_sym, {
                'symbol': valid_sym,
                'trend_label': combined_trend_label,
                'w1_trend_label': w1_trend_label,
                'd1_trend_label': d1_trend_label,
                'h4_trend_label': h4_trend_label,
                'is_d1_bull': d1_is_bull and not d1_is_bear,
                'is_d1_bear': d1_is_bear and not d1_is_bull,
                'is_h4_bull': h4_is_bull and not h4_is_bear,
                'is_h4_bear': h4_is_bear and not h4_is_bull,
                'is_bull': d1_is_bull and not d1_is_bear,
                'is_bear': d1_is_bear and not d1_is_bull,
                'permission_state': derived_perm,
                'csm_delta': csm_delta_val,
                'recent_ceiling_touch': recent_ceiling_touch,
                'recent_floor_touch': recent_floor_touch,
                'htf_delivery': htf_delivery,
                'pdh': pdh,
                'pdl': pdl,
                'asian_high': asian_high,
                'asian_low': asian_low,
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
                'h4_50_range': h4_monthly_range_str,
                'h4_monthly_range': h4_monthly_range_str,
                'h4_swing_high': h4_swing_high,
                'h4_swing_low': h4_swing_low,
                'is_h4_ranging': is_h4_ranging,
                'is_h4_flag_triangle': is_h4_flag_triangle,
                'h4_dr_pos': h4_dr_pos,
                'h4_bos_count': h4_bos_count,
                'h4_trend_label': h4_trend_label,
                'dealing_range_high': sess_h,
                'dealing_range_low': sess_l,
                'dealing_range_pos': pos_in_range,
                'adr_20': adr20,
                'current_atr': cur_atr,
                'atr_pts': int(round(cur_atr / pt)) if pt > 0 else 300,
                'current_price': cur_close,
                'ema20': cur_ema20,
                'ema50': cur_ema50,
                'ema200': cur_ema200,
                'strong_low': smc_sig.strong_low if smc_sig else 0.0,
                'strong_high': smc_sig.strong_high if smc_sig else 0.0,
                'h1_bos_level': smc_sig.bos.get('level', 0.0) if (smc_sig and getattr(smc_sig, 'bos', None)) else 0.0,
                'h1_bos_direction': smc_sig.bos.get('direction', 'none') if (smc_sig and getattr(smc_sig, 'bos', None)) else 'none',
                'bullish_ob_zone': bull_ob_str,
                'bearish_ob_zone': bear_ob_str,
                'bullish_ob_top': smc_sig.order_blocks_bullish[-1]['top'] if (smc_sig and getattr(smc_sig, 'order_blocks_bullish', None) and len(smc_sig.order_blocks_bullish) > 0) else 0.0,
                'bearish_ob_bot': smc_sig.order_blocks_bearish[-1]['bottom'] if (smc_sig and getattr(smc_sig, 'order_blocks_bearish', None) and len(smc_sig.order_blocks_bearish) > 0) else 0.0,
                'bullish_fvg_top': smc_sig.fvg_bullish[-1]['top'] if (smc_sig and getattr(smc_sig, 'fvg_bullish', None) and len(smc_sig.fvg_bullish) > 0) else 0.0,
                'bullish_fvg_bot': smc_sig.fvg_bullish[-1]['bottom'] if (smc_sig and getattr(smc_sig, 'fvg_bullish', None) and len(smc_sig.fvg_bullish) > 0) else 0.0,
                'bearish_fvg_top': smc_sig.fvg_bearish[-1]['top'] if (smc_sig and getattr(smc_sig, 'fvg_bearish', None) and len(smc_sig.fvg_bearish) > 0) else 0.0,
                'bearish_fvg_bot': smc_sig.fvg_bearish[-1]['bottom'] if (smc_sig and getattr(smc_sig, 'fvg_bearish', None) and len(smc_sig.fvg_bearish) > 0) else 0.0,
                'fvg_zone': fvg_str,
                'liquidity_pools': liq_str,
                'frvp_summary': frvp_summary_str,
                'cluster_resistance': cluster_res,
                'cluster_support': cluster_sup,
                'df': df,
                'touches_resistance': touches_res,
                'touches_support': touches_sup,
                'range_age_hours': regime_res.get('range_age_hours', 24.0),
                'effective_sqz_bars': regime_res.get('effective_sqz_bars', 0),
                'wave_regime_name': regime_res.get('regime', 'YOUNG_OSCILLATION'),
                'wave_state': f"MSE_{mse_tier}",
                'permission_v3': derived_perm,
                'correction_type': 'NEUTRAL',
                'is_reclaim_confirmed': False,
                'overlap_ratio': 0.0,
                'correction_velocity': 0.0,
                'body_efficiency': 0.0,
                'wave_permitted': (derived_perm in ("ARM", "GO")),
                'wave_summary': f"[{getattr(strat_dir, 'primary_execution_directive', 'NEUTRAL') if strat_dir else 'NEUTRAL'} | MSE: {mse_tier} | CSM {csm_delta_val:+.2f}] -> {derived_perm}",
                'wave_pullback_atr': 0.0,
                'wave_zigzag_legs': 0,
                'macro_corridor': getattr(strat_dir, 'primary_execution_directive', 'NEUTRAL') if strat_dir else 'NEUTRAL',
                'target_station': getattr(strat_dir, 'entry_limit_anchor', 0.0) if strat_dir else 0.0,
                'psych_step': get_symbol_step(valid_sym),
                'is_ceiling_rejected': recent_ceiling_touch,
                'is_floor_rejected': recent_floor_touch,
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
                'immediate_ceiling_c1': eff_c1,
                'immediate_floor_f1': eff_f1,
                'ceiling_c1': eff_c1,
                'floor_f1': eff_f1,
                'ceiling_c2': eff_c2,
                'floor_f2': eff_f2,
                'deep_target_ceiling_c2': getattr(strat_dir, 'deep_target_ceiling_c2', 0.0) if strat_dir else 0.0,
                'deep_target_floor_f2': getattr(strat_dir, 'deep_target_floor_f2', 0.0) if strat_dir else 0.0,
                'c1_reaction_grade': getattr(strat_dir, 'c1_reaction_grade', 'GRADE_1_MICRO') if strat_dir else 'GRADE_1_MICRO',
                'f1_reaction_grade': getattr(strat_dir, 'f1_reaction_grade', 'GRADE_1_MICRO') if strat_dir else 'GRADE_1_MICRO',
                'c1_fortress_tag': getattr(strat_dir, 'c1_fortress_tag', 'MODERATE') if strat_dir else 'MODERATE',
                'f1_fortress_tag': getattr(strat_dir, 'f1_fortress_tag', 'MODERATE') if strat_dir else 'MODERATE',
                'daily_mandate_thesis': getattr(strat_dir, 'daily_mandate_thesis', '') if strat_dir else '',
                'structural_stage': getattr(strat_dir, 'structural_stage', '') if strat_dir else '',
                'strategic_raw_payload': getattr(strat_dir, 'raw_payload', {}) if strat_dir else {},
                'zce_meta': zce_meta,
                'point': pt,
            }
        except Exception as e:
            logger.warning(f"Error updating macro context for {valid_sym}: {e}")
            return None

    # ── ZCE (RFC 11) rotation refresh — dipanggil per siklus scan, ZCE_ENABLED off = no-op ──
    def _zce_refresh_due_seconds(self) -> int:
        """Interval rebuild macro_cache: 900 dtk (15 mnt) saat ZCE aktif (legacy/full),
        3600 dtk (1 jam) default. Membatasi umur dinding ZCE maks ~15 mnt (bukan 60 mnt)."""
        if getattr(config, "ZCE_ENABLED", False) and getattr(config, "ZCE_MODE", "shadow") in ("legacy", "full"):
            return int(getattr(config, "ZCE_REFRESH_INTERVAL_SECONDS", 900))
        return int(getattr(config, "MACRO_STRATEGIC_REFRESH_SECONDS", 3600))

    def _compute_zce_map_for(self, valid, mt5_connector=None, eng=None):
        """Compute & cache peta zona ZCE untuk SATU simbol (Patch #1, 2 Sep 2026).
        - eng=None  -> engine lokal baru (aman dipanggil dari thread worker
                       _build_single_macro_context / cold-start inline fallback).
        - eng!=None -> engine bersama (dipakai _refresh_zce_rotation secara berurutan).
        Returns None bila gagal -> caller fallback ke MSE baseline (perilaku pra-ZCE)."""
        try:
            from src.analytics.zone_confluence_engine import ZoneConfluenceEngine
        except Exception as e:
            logger.debug(f"[ZCE] engine import gagal: {e}")
            return None
        try:
            if eng is None:
                eng = ZoneConfluenceEngine()
            if mt5_connector is not None and hasattr(mt5_connector, "get_valid_trade_symbol"):
                valid = mt5_connector.get_valid_trade_symbol(valid)
            try:
                if hasattr(config.mt5, "symbol_select"):
                    config.mt5.symbol_select(valid, True)
            except Exception:
                pass
            tf_cfg = [("MN1", getattr(config.mt5, "TIMEFRAME_MN1", 49167), 100),
                      ("W1", getattr(config.mt5, "TIMEFRAME_W1", 32769), 200),
                      ("D1", getattr(config.mt5, "TIMEFRAME_D1", 16408), 350),
                      ("H4", getattr(config.mt5, "TIMEFRAME_H4", 16388), 400),
                      ("H1", getattr(config.mt5, "TIMEFRAME_H1", 16385), 520),
                      ("M30", getattr(config.mt5, "TIMEFRAME_M30", 16386), 600)]
            dfs = {}
            for name, tfid, cnt in tf_cfg:
                rr = config.mt5.copy_rates_from_pos(valid, tfid, 0, cnt)
                if rr is None or len(rr) == 0:
                    continue
                dfs[name] = pd.DataFrame(rr)
            h1 = dfs.get("H1")
            if h1 is None or len(h1) < 60:
                return None
            pt = self._get_point(valid)
            digits = 5
            try:
                import math as _m
                digits = int(round(-_m.log10(pt))) if pt > 0 else 5
            except Exception:
                digits = 5
            zm = eng.compute_zone_map(valid, dfs, point_size=pt, digits=digits)
            maps = getattr(self, "_zce_maps", {})
            maps[valid] = zm
            self._zce_maps = maps
            return zm
        except Exception as e:
            logger.debug(f"[ZCE] peta zona gagal untuk {valid}: {e}")
            return None

    def _refresh_zce_rotation(self, mt5_connector=None, full_sweep: bool = False) -> None:
        """Refresh peta zona ZCE.
        Default: ZCE_REFRESH_ROTATION simbol per siklus (rotasi 60 dtk).
        full_sweep=True: refresh SEMUA simbol sekaligus — dipanggil tepat SEBELUM rebuild
        macro_cache agar cache tidak pernah dibangun dari peta basi (cold start / Senin pagi
        setelah weekend / bangun dari dead zone).
        Default config.ZCE_ENABLED=False -> metode ini no-op (0 biaya runtime)."""
        if not getattr(config, "ZCE_ENABLED", False):
            return
        try:
            from src.analytics.zone_confluence_engine import ZoneConfluenceEngine
        except Exception as e:
            logger.debug(f"[ZCE] engine import gagal: {e}")
            return
        eng = getattr(self, "_zce_engine", None)
        if eng is None:
            eng = ZoneConfluenceEngine()
            self._zce_engine = eng
        syms = self.symbols
        if not syms:
            return
        rot = int(getattr(self, "_zce_rot", 0)) % len(syms)
        n = len(syms) if full_sweep else max(1, int(getattr(config, "ZCE_REFRESH_ROTATION", 6)))
        for k in range(n):
            sym = syms[(rot + k) % len(syms)]
            valid = sym
            if mt5_connector is not None and hasattr(mt5_connector, "get_valid_trade_symbol"):
                valid = mt5_connector.get_valid_trade_symbol(sym)
            self._compute_zce_map_for(valid, mt5_connector=None, eng=eng)
        if not full_sweep:
            self._zce_rot = (rot + n) % len(syms)

    def scan_all(self, mt5_connector=None) -> List[CandidateSetup]:
        """Alias untuk scan_fast_radar guna memindai seluruh 26 simbol universe."""
        return self.scan_fast_radar(mt5_connector=mt5_connector)

    def scan_fast_radar(self, mt5_connector=None) -> List[CandidateSetup]:
        """
        Fast Execution Radar: Runs every 60 seconds across 26 symbols.
        Checks live tick / M5-M15 wicks against cached macro levels.
        Returns list of qualifying CandidateSetup objects (0 Tokens).
        """
        now = datetime.now(WIB)
        h = now.hour
        dow = now.weekday()

        is_asian = (8 <= h < 17)
        req_body = 0.30 if is_asian else 0.40
        req_wick = 0.25 if is_asian else 0.333

        
        # Dead Zone / Weekend Filter (00:00 - 08:00 WIB weekday, full block Sabtu-Minggu)
        # FIX 29 Agu: weekend = Sabtu (5) + Minggu (6), cutoff Sabtu 00:00 (bukan Jumat 22:00).
        if dow in (5, 6) or (0 <= h < 8):
            return []

        # Ensure macro cache is initialized & dinding ZCE tidak basi (Patch #1, 2 Sep 2026).
        # Saat refresh due: full-sweep peta ZCE SEMUA simbol DULU, baru rebuild macro_cache —
        # cache tidak pernah dibangun dari peta basi/absent (cold start, Senin pagi, bangun
        # dari dead zone 00:00-08:00 WIB). Interval = 900s saat ZCE legacy/full, 3600s default.
        refresh_secs = self._zce_refresh_due_seconds()
        if not self.macro_cache or (self.last_macro_update and (now - self.last_macro_update).total_seconds() > refresh_secs):
            self._refresh_zce_rotation(mt5_connector=mt5_connector, full_sweep=True)
            self.update_macro_context(mt5_connector=mt5_connector)
        else:
            self._refresh_zce_rotation(mt5_connector=mt5_connector)

        # ── M4: SYSTEMIC FLOW CONTINUATION — refresh feed currency-z (sekali per jam WIB) ──
        if config.M4_ENABLED:
            self._m4_feed_refresh()

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

            # ── SESSION-AWARE PAIR ROUTER (Anti-European Trap in Asian Session) ──
            if getattr(config, "SESSION_AWARE_ROUTING_ENABLED", True):
                asia_start = getattr(config, "ASIA_SESSION_START_HOUR_WIB", 8)
                asia_end = getattr(config, "ASIA_SESSION_END_HOUR_WIB", 14)
                if asia_start <= h < asia_end:
                    if not config.is_asian_session_pair(sym):
                        logger.debug(f"[RADAR] {sym} SKIP: Sesi Asia ({asia_start:02d}:00-{asia_end:02d}:00 WIB) hanya mengizinkan pair Pasifik/Asia (AUD/NZD/JPY).")
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
                atr_pts = macro.get('atr_pts') or (int(round(macro.get('current_atr', 0.0020) / pt)) if pt > 0 else 300)
                df = macro.get('df')

                # Evaluate live candle quality for real wick measurement & waterfall detection
                c_qual = self._evaluate_live_candle_quality(sym, mid, atr_pts, pt, mt5_connector=mt5_connector)
                live_h = c_qual.get('live_high', max(ask, mid))
                live_l = c_qual.get('live_low', min(bid, mid))

                cal_text = ""
                try:
                    from src.analytics import economic_calendar
                    cal_obj = getattr(economic_calendar, "calendar", None)
                    if cal_obj:
                        cal_text = cal_obj.get_context(symbol=sym) or ""
                        # Stage 1 High-Impact News Shield: Skip symbol if high-impact news is within 30m or just released (<10m)
                        is_news_imminent, news_desc = cal_obj.is_high_impact_imminent(symbol=sym, window_minutes=30)
                        if is_news_imminent:
                            logger.debug(f"[RADAR NEWS SHIELD] {sym} SKIP: Imminent high-impact event ({news_desc})")
                            continue
                except Exception:
                    cal_text = ""

                # ── 4-LAYER TRADE PERMISSION GATE (Hard Lockout Enforcement) ──
                perm_state = macro.get('permission_state', 'ARM')
                csm_delta_val = macro.get('csm_delta', 0.0)
                strat_dir_sym = macro.get('strat_dir')
                zce_meta = macro.get('zce_meta') or {
                    "zce_class": "MSE_BASE",
                    "zce_f1_src": "MSE",
                    "zce_c1_src": "MSE",
                    "zce_f1_price": round(float(macro.get('immediate_floor_f1', 0.0) or 0.0), 5 if pt < 0.01 else 3),
                    "zce_c1_price": round(float(macro.get('immediate_ceiling_c1', 0.0) or 0.0), 5 if pt < 0.01 else 3),
                }
                if getattr(config, 'ENABLE_WAVE_STATE_PERMISSION', False):
                    if perm_state == "LOCK" and getattr(config, 'WAVE_STATE_LOCK_PHASE2', False):
                        logger.debug(f"[RADAR] {sym} SKIP: Hard Lockout {macro.get('wave_state', 'LOCK')} ({macro.get('wave_summary', '')}).")
                        continue

                # ── DIRECTIONAL 5-TIER OPERATIONAL ACTION MATRIX & CIRCUIT BREAKER ──
                def _is_direction_allowed(target_dir: int, setup_label: str, entry_price: Optional[float] = None) -> tuple:
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
                        return False, "HARD_BLOCK", "[MSE GATING] Missing MSE Directive -> Defensive WATCH_ONLY"

                    strat_tier = getattr(strat_dir_sym, 'action_tier', 'FULL_ALLOW')
                    is_limit_retest = any(k in setup_label.upper() for k in ("PULLBACK", "SYSTEMIC", "BREAKOUT", "RETEST"))
                    if strat_tier in ("INACTION_ZONE", "CHAMBER_MID_BLOCK") and not is_limit_retest:
                        return False, "HARD_BLOCK", f"[MSE GATING] Inaction Zone / Mid-Chamber ({strat_tier})"
                    if strat_tier == "HARD_LOCK":
                        return False, "HARD_BLOCK", f"[MSE GATING] Hard Lock ({strat_tier})"

                    bias_score = getattr(strat_dir_sym, 'macro_bias_score', 0.0)
                    circuit_breaker = getattr(strat_dir_sym, 'hard_circuit_breaker', False)

                    # 2. Hard Circuit Breaker Collision Check (Extreme Traps & Invalidation)
                    if circuit_breaker:
                        if target_dir == 1 and bias_score < -0.40:
                            return False, "HARD_BLOCK", f"[MSE CIRCUIT BREAKER] BUY blocked at ceiling trap / past invalidation"
                        if target_dir == -1 and bias_score > 0.40:
                            return False, "HARD_BLOCK", f"[MSE CIRCUIT BREAKER] SELL blocked at floor trap / past invalidation"

                    if strat_dir_sym.forbidden_traps:
                        is_limit_setup = is_limit_retest
                        f1_lvl = macro.get('immediate_floor_f1') or macro.get('floor_f1') or 0.0
                        c1_lvl = macro.get('immediate_ceiling_c1') or macro.get('ceiling_c1') or 0.0

                        for trap in strat_dir_sym.forbidden_traps:
                            trap_u = trap.upper()
                            if ("DO NOT EXECUTE" in trap_u or "CONSOLIDATION ZONE" in trap_u or "MID-CHAMBER" in trap_u) and not is_limit_retest:
                                return False, "HARD_BLOCK", f"[MSE TRAP VETO] Trade forbidden in consolidation: {trap}"

                            if target_dir == 1 and ("DO NOT BUY" in trap_u or "DON'T BUY" in trap_u):
                                # Contextual Limit Awareness: Jika Buy Limit berada cukup jauh di bawah plafon C1 (C1 adalah target TP, bukan harga entri)
                                if is_limit_setup and entry_price is not None and c1_lvl > 0.0 and entry_price <= (c1_lvl - 0.40 * atr_val):
                                    continue
                                return False, "HARD_BLOCK", f"[MSE TRAP VETO] BUY forbidden: {trap}"

                            if target_dir == -1 and ("DO NOT SELL" in trap_u or "DO NOT SHORT" in trap_u or "DON'T SELL" in trap_u):
                                # Contextual Limit Awareness: Jika Sell Limit berada cukup jauh di atas lantai F1 (F1 adalah target TP, bukan harga entri)
                                if is_limit_setup and entry_price is not None and f1_lvl > 0.0 and entry_price >= (f1_lvl + 0.40 * atr_val):
                                    continue
                                return False, "HARD_BLOCK", f"[MSE TRAP VETO] SELL forbidden: {trap}"

                    # 3. CSM Flow Opposition Check (Systemic Currency Pressure)
                    is_csm_opposed = (target_dir == 1 and csm_delta_val <= -1.0) or (target_dir == -1 and csm_delta_val >= 1.0)

                    # 4. Macro Bias Alignment & Action Tier Resolution
                    is_aligned = (target_dir == 1 and bias_score >= 0.35) or (target_dir == -1 and bias_score <= -0.35)
                    is_counter = (target_dir == 1 and bias_score <= -0.35) or (target_dir == -1 and bias_score >= 0.35)

                    if is_csm_opposed and not is_aligned:
                        return False, "HARD_BLOCK", f"[CSM OPPOSED] Net Delta ({csm_delta_val:+.2f}) opposes direction"

                    if is_aligned:
                        return True, "FULL_ALLOW", f"ALIGNED_MACRO_EXPANSION ({bias_score:+.2f})"
                    elif is_counter:
                        # Counter-trend allows only high quality M1 liquidity sweep / SFP with TP1 cap, or M4 systemic flow
                        if "SWEEP" in setup_label.upper() or "RECLAIM" in setup_label.upper() or "SYSTEMIC" in setup_label.upper():
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
                    c1_val = macro.get('immediate_ceiling_c1') or pwh_val
                    f1_val = macro.get('immediate_floor_f1') or pwl_val
                    dist_floor = abs(mid - f1_val) if f1_val > 0 else 9999.0
                    dist_ceiling = abs(c1_val - mid) if c1_val > 0 else 9999.0
                    atr_price_val = atr_pts * pt
                    ema20_val = macro.get('ema20', mid)
                    dr_pos_val = macro.get('dealing_range_pos', 0.5)

                    # Bearish Liquidity Sweep (SFP High): Sweep above Asian High, PDH, EQH, or Psychological Ceiling (PREMIUM ZONE ONLY)
                    valid_tops = [v for v in [asian_h, pdh_val, eqh_val, p_ceil] if v > 0 and 0 < (v - mid) <= 1.0 * atr_price_val]
                    ref_top = min(valid_tops) if valid_tops else (macro.get('immediate_ceiling_c1') or asian_h or (mid + atr_price_val))
                    if dr_pos_val >= 0.55 and (ref_top > 0) and (ref_top - sweep_tol <= mid <= ref_top + (atr_pts * 0.50 * pt)):
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
                            clean_s = sym.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
                            is_sweep_pair = clean_s in SWEEP_SPECIALIST_PAIRS
                            sweep_buffer = (8.0 * pt * 10) if is_sweep_pair else 0.0

                            # 1. Asian Session Liquidity Filter for European Pairs (GBP, EUR, CHF)
                            is_euro_pair = any(k in clean_s for k in ("EUR", "GBP", "CHF"))
                            is_asian_session = (8 <= h < 14)
                            c1_struct = macro.get('immediate_ceiling_c1') or 0.0
                            c1_grade = macro.get('c1_reaction_grade', 'GRADE_1_MICRO')
                            is_macro_wall = (c1_struct > 0 and abs(ref_top - c1_struct) <= config.SWEEP_WALL_MATCH_ATR_MULT * atr_price_val)
                            is_macro_wall_g2_g3 = (is_macro_wall and c1_grade in ("GRADE_2_INTERMEDIATE", "GRADE_3_MACRO"))
                            is_macro_wall_g3 = (is_macro_wall and c1_grade == "GRADE_3_MACRO")

                            if is_euro_pair and is_asian_session and not is_macro_wall_g3:
                                logger.debug(f"[SWEEP SELL ASIA NOISE] {sym} SKIP: European pair sweep in Asian session lacks Grade 3 Macro Wall (Current: {c1_grade}).")
                                continue

                            # 2. Anti-Trend Veto: Fading a bullish trend is strictly forbidden unless hitting G3 Macro Fortress Wall!
                            is_macro_bull = (macro.get('is_bull', False) or (strat_dir_sym and getattr(strat_dir_sym, 'macro_bias_score', 0.0) >= 0.35))
                            if is_macro_bull and not is_macro_wall_g3:
                                logger.debug(f"[SWEEP SELL ANTI-BULL VETO] {sym} SKIP: Fading bullish trend is forbidden unless hitting G3 Macro Fortress Wall (Current: {c1_grade}).")
                                continue

                            # 3. Wall Rank Gate: In trending markets, sweeping high is ONLY permitted at G2/G3 Macro Fortress!
                            is_ranging_market = (macro.get('daily_macro_bias') == "RANGE_BOUND" or (not macro.get('is_bull') and not macro.get('is_bear')))
                            if not is_ranging_market and not is_macro_wall_g2_g3:
                                logger.debug(f"[SWEEP SELL WALL GRADE] {sym} SKIP: Sweep at {ref_top:.5f} is {c1_grade} in trending market. Requires G2/G3 Macro Fortress.")
                                continue

                            # 4. Pure SMC Stop-Hunt Penetration Requirement (Must pierce liquidity pool to trigger retail SLs!)
                            has_penetrated_high = (live_h >= ref_top + (0.04 * atr_price_val)) or (c_qual.get('max_high', live_h) >= ref_top + (0.04 * atr_price_val))
                            if not has_penetrated_high:
                                logger.debug(f"[SWEEP SELL NO STOP HUNT] {sym} SKIP: High {live_h:.5f} did not pierce above liquidity pool {ref_top:.5f} to trigger retail SL.")
                                continue

                            if not gate_ok:
                                logger.debug(f"[SWEEP SELL GATE] {sym} SKIP: {gate_reason}")
                            else:
                                # 5. Strict Close Reclaim Requirement (Price and Completed Bar MUST be closed back below ref_top!)
                                has_closed_below = (c_qual.get('prev_close', mid) < ref_top)
                                if mid >= ref_top or not has_closed_below:
                                    logger.debug(f"[SWEEP SELL RECLAIM] {sym} SKIP: mid {mid:.5f} >= ref_top {ref_top:.5f} or bar unclosed below (Unconfirmed breakout expansion in progress)")
                                    continue

                                # 6. Rejection Wick / Candle Pattern Verification (Rule of Thirds: Upper Wick >= 33.3%)
                                is_bull_breakout = (c_qual['direction'] == 'bullish' and c_qual['body_ratio'] >= req_body and c_qual['upper_wick_pct'] < req_wick)
                                has_rejection = (c_qual['max_upper_wick'] >= req_wick) or (c_qual['sweep_side'] == 'top' and c_qual['upper_wick_pct'] >= req_wick) or c_qual['is_bearish_engulf']
                                
                                if has_rejection and not is_bull_breakout:
                                    # Delayed Limit Retest Entry at discount/retest zone with empirical sweep offset
                                    raw_limit_s = min(ref_top + sweep_buffer, mid + (0.20 * atr_price_val))
                                    limit_entry = min(raw_limit_s, mid + (1.0 * atr_price_val)) - (spread_pts * 0.5 * pt)
                                    sl_tp = calculate_intraday_sl_tp(
                                        symbol=sym,
                                        entry_price=limit_entry,
                                        direction=-1,
                                        origin_level=ref_top,
                                        atr_h1=atr_pts * pt,
                                        pwl=pwl_val,
                                        pwh=pwh_val,
                                        rbs=macro.get('micro_rbs_h1') or macro.get('inter_rbs_h4'),
                                        sbr=macro.get('micro_sbr_h1') or macro.get('inter_sbr_h4'),
                                        spread_pts=spread_pts,
                                        c1=macro.get('immediate_ceiling_c1') or macro.get('ceiling_c1'),
                                        f1=macro.get('immediate_floor_f1') or macro.get('floor_f1')
                                    )
                                    sl = sl_tp['sl']
                                    tp = sl_tp['tp']
                                    if action_tier_m1_s == "TP1_ONLY_SCALP":
                                        tp = sl_tp.get('tp1', round(limit_entry - (1.25 * abs(limit_entry - sl)), 5 if pt < 0.01 else 2))
                                    rr_val = sl_tp['risk_reward']
                                    if abs(limit_entry - mid) > 1.0 * atr_price_val:
                                        logger.debug(f"[M1 SELL DISTANCE GUARD] {sym} SKIP: limit_entry {limit_entry:.5f} too far from mid {mid:.5f}")
                                    elif abs(limit_entry - sl) / pt >= 15:
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
                                            economic_context=cal_text,
                                            action_tier=action_tier_m1_s,
                                            macro_bias_score=macro.get('macro_bias_score', 0.0),
                                            regime_stability=macro.get('regime_stability', 'STABLE'),
                                            metadata={
                                                "entry_type": "sell_limit",
                                                "entry_price": round(limit_entry, 5 if pt < 0.01 else 2),
                                                "ref_top": ref_top,
                                                "target_station": sl_tp.get('target_station', 0.0),
                                                "action_tier": action_tier_m1_s,
                                                "macro_corridor": macro.get('macro_corridor', 'NEUTRAL'),
                                                **zce_meta
                                            }
                                        ))
                                        continue

                    # Bullish Liquidity Sweep (SFP Low): Sweep below Asian Low, PDL, EQL, or Psychological Floor (DISCOUNT ZONE ONLY)
                    valid_bots = [v for v in [asian_l, pdl_val, eql_val, p_floor] if v > 0 and 0 < (mid - v) <= 1.0 * atr_price_val]
                    ref_bot = max(valid_bots) if valid_bots else (macro.get('immediate_floor_f1') or asian_l or (mid - atr_price_val))
                    if dr_pos_val <= 0.45 and (ref_bot > 0) and (ref_bot - (atr_pts * 0.50 * pt) <= mid <= ref_bot + sweep_tol):
                        allowed_m1_b, action_tier_m1_b, reason_m1_b = _is_direction_allowed(1, "BULLISH_SWEEP")
                        if not allowed_m1_b:
                            logger.debug(f"[SWEEP BUY GATE] {sym} SKIP ({action_tier_m1_b}): {reason_m1_b}")
                        else:
                            gate_ok, gate_reason = evaluate_judas_sweep_gates(
                                signal_type='BUY',
                                dealing_range_pos=dr_pos_val,
                                dist_to_htf_floor=dist_floor,
                                dist_to_htf_ceiling=dist_ceiling,
                                atr_val=atr_price_val,
                                recent_ceiling_touch=macro.get('recent_ceiling_touch', False),
                                recent_floor_touch=macro.get('recent_floor_touch', False),
                                close_below_ema20=(mid < macro.get('ema20', mid)),
                                close_above_ema20=(mid > macro.get('ema20', mid)),
                                macro_trend=macro_trend_str
                            )
                            clean_s = sym.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
                            is_sweep_pair = clean_s in SWEEP_SPECIALIST_PAIRS
                            sweep_buffer = (8.0 * pt * 10) if is_sweep_pair else 0.0

                            # 1. Asian Session Liquidity Filter for European Pairs (GBP, EUR, CHF)
                            is_euro_pair = any(k in clean_s for k in ("EUR", "GBP", "CHF"))
                            is_asian_session = (8 <= h < 14)
                            f1_struct = macro.get('immediate_floor_f1') or 0.0
                            f1_grade = macro.get('f1_reaction_grade', 'GRADE_1_MICRO')
                            is_macro_wall = (f1_struct > 0 and abs(ref_bot - f1_struct) <= config.SWEEP_WALL_MATCH_ATR_MULT * atr_price_val)
                            is_macro_wall_g2_g3 = (is_macro_wall and f1_grade in ("GRADE_2_INTERMEDIATE", "GRADE_3_MACRO"))
                            is_macro_wall_g3 = (is_macro_wall and f1_grade == "GRADE_3_MACRO")

                            if is_euro_pair and is_asian_session and not is_macro_wall_g3:
                                logger.debug(f"[SWEEP BUY ASIA NOISE] {sym} SKIP: European pair sweep in Asian session lacks Grade 3 Macro Wall (Current: {f1_grade}).")
                                continue

                            # 2. Anti-Trend Veto: Catching falling knife in a bearish trend is strictly forbidden unless hitting G3 Macro Fortress Floor!
                            is_macro_bear = (macro.get('is_bear', False) or (strat_dir_sym and getattr(strat_dir_sym, 'macro_bias_score', 0.0) <= -0.35))
                            if is_macro_bear and not is_macro_wall_g3:
                                logger.debug(f"[SWEEP BUY ANTI-BEAR VETO] {sym} SKIP: Catching falling knife in bearish trend is forbidden unless hitting G3 Macro Fortress Floor (Current: {f1_grade}).")
                                continue

                            # 3. Wall Rank Gate: In trending markets, sweeping low is ONLY permitted at G2/G3 Macro Fortress!
                            is_ranging_market = (macro.get('daily_macro_bias') == "RANGE_BOUND" or (not macro.get('is_bull') and not macro.get('is_bear')))
                            if not is_ranging_market and not is_macro_wall_g2_g3:
                                logger.debug(f"[SWEEP BUY WALL GRADE] {sym} SKIP: Sweep at {ref_bot:.5f} is {f1_grade} in trending market. Requires G2/G3 Macro Fortress.")
                                continue

                            # 4. Pure SMC Stop-Hunt Penetration Requirement (Must pierce liquidity pool to trigger retail SLs!)
                            has_penetrated_low = (live_l <= ref_bot - (0.04 * atr_price_val)) or (c_qual.get('max_low', live_l) <= ref_bot - (0.04 * atr_price_val))
                            if not has_penetrated_low:
                                logger.debug(f"[SWEEP BUY NO STOP HUNT] {sym} SKIP: Low {live_l:.5f} did not pierce below liquidity pool {ref_bot:.5f} to trigger retail SL.")
                                continue

                            if not gate_ok:
                                logger.debug(f"[SWEEP BUY GATE] {sym} SKIP: {gate_reason}")
                            else:
                                # 5. Strict Close Reclaim Requirement (Price and Completed Bar MUST be closed back above ref_bot!)
                                has_closed_above = (c_qual.get('prev_close', mid) > ref_bot)
                                if mid <= ref_bot or not has_closed_above:
                                    logger.debug(f"[SWEEP BUY RECLAIM] {sym} SKIP: mid {mid:.5f} <= ref_bot {ref_bot:.5f} or bar unclosed above (Unconfirmed breakdown waterfall in progress)")
                                    continue

                                # 6. Rejection Wick / Candle Pattern Verification (Rule of Thirds: Lower Wick >= 33.3%)
                                is_bear_breakdown = (c_qual['direction'] == 'bearish' and c_qual['body_ratio'] >= req_body and c_qual['lower_wick_pct'] < req_wick)
                                has_rejection = (c_qual['max_lower_wick'] >= req_wick) or (c_qual['sweep_side'] == 'bottom' and c_qual['lower_wick_pct'] >= req_wick) or c_qual['is_bullish_engulf']
                                
                                if has_rejection and not is_bear_breakdown:
                                    # Delayed Limit Retest Entry at premium/retest zone with empirical sweep offset
                                    raw_limit_b = max(ref_bot - sweep_buffer, mid - (0.20 * atr_price_val))
                                    limit_entry = max(raw_limit_b, mid - (1.0 * atr_price_val)) + (spread_pts * 0.5 * pt)
                                    sl_tp = calculate_intraday_sl_tp(
                                        symbol=sym,
                                        entry_price=limit_entry,
                                        direction=1,
                                        origin_level=ref_bot,
                                        atr_h1=atr_pts * pt,
                                        pwl=pwl_val,
                                        pwh=pwh_val,
                                        rbs=macro.get('micro_rbs_h1') or macro.get('inter_rbs_h4'),
                                        sbr=macro.get('micro_sbr_h1') or macro.get('inter_sbr_h4'),
                                        spread_pts=spread_pts,
                                        c1=macro.get('immediate_ceiling_c1') or macro.get('ceiling_c1'),
                                        f1=macro.get('immediate_floor_f1') or macro.get('floor_f1')
                                    )
                                    sl = sl_tp['sl']
                                    tp = sl_tp['tp']
                                    if action_tier_m1_b == "TP1_ONLY_SCALP":
                                        tp = sl_tp.get('tp1', round(limit_entry + (1.25 * abs(limit_entry - sl)), 5 if pt < 0.01 else 2))
                                    rr_val = sl_tp['risk_reward']
                                    if abs(limit_entry - mid) > 1.0 * atr_price_val:
                                        logger.debug(f"[M1 BUY DISTANCE GUARD] {sym} SKIP: limit_entry {limit_entry:.5f} too far from mid {mid:.5f}")
                                    elif abs(limit_entry - sl) / pt >= 15:
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
                                            economic_context=cal_text,
                                            action_tier=action_tier_m1_b,
                                            macro_bias_score=macro.get('macro_bias_score', 0.0),
                                            regime_stability=macro.get('regime_stability', 'STABLE'),
                                            metadata={
                                                "entry_type": "buy_limit",
                                                "entry_price": round(limit_entry, 5 if pt < 0.01 else 2),
                                                "ref_bot": ref_bot,
                                                "target_station": sl_tp.get('target_station', 0.0),
                                                "action_tier": action_tier_m1_b,
                                                "macro_corridor": macro.get('macro_corridor', 'NEUTRAL'),
                                                **zce_meta
                                            }
                                        ))
                                        continue

                # ── MECHANISM 2: TREND-ALIGNED MULTI-TIMEFRAME PULLBACK & DELAYED RETEST (H1/M30) ──
                is_h4_ranging = macro.get('is_h4_ranging', False)
                is_h4_flag = macro.get('is_h4_flag_triangle', False)

                if (8 <= h <= 23) and self.is_symbol_allowed_for_session(sym, h) and not is_h4_ranging and not is_h4_flag:
                    ema20 = macro['ema20']
                    ema50 = macro.get('ema50', ema20)
                    pos_in_range = macro['dealing_range_pos']
                    m_corr = macro.get('macro_corridor', 'NEUTRAL')
                    atr_val = atr_pts * pt
                    
                    # BUY: (Bullish Macro OR Bullish Corridor) AND NOT Bearish Corridor + Pullback to FVG / OB / EMA50 / Support Floor
                    allowed_m2_b, action_tier_m2_b, reason_m2_b = _is_direction_allowed(1, "BUY_PULLBACK")
                    can_buy_m2 = allowed_m2_b and (macro['is_bull'] or m_corr == "BULLISH_CORRIDOR") and (m_corr != "BEARISH_CORRIDOR")
                    
                    fvg_bull_top = macro.get('bullish_fvg_top', 0.0)
                    ob_bull_top = macro.get('bullish_ob_top', 0.0)
                    f1_floor = macro.get('immediate_floor_f1', 0.0)
                    has_fvg_or_ob_retest_b = (fvg_bull_top > 0 and abs(mid - fvg_bull_top) <= 0.50 * atr_val) or (ob_bull_top > 0 and abs(mid - ob_bull_top) <= 0.50 * atr_val)
                    has_ema_or_f1_retest_b = (abs(mid - ema50) <= 0.50 * atr_val) or (f1_floor > 0 and abs(mid - f1_floor) <= 0.50 * atr_val)
                    is_valid_pullback_range_b = (pos_in_range <= 0.65) and ((pos_in_range <= 0.55) or has_fvg_or_ob_retest_b or has_ema_or_f1_retest_b)

                    if not allowed_m2_b:
                        logger.debug(f"[PULLBACK BUY GATE] {sym} SKIP ({action_tier_m2_b}): {reason_m2_b}")
                    elif can_buy_m2 and is_valid_pullback_range_b:
                        base_floor, m2_confluence_desc = self.find_ema_confluence_anchor(sym, mid, 1, macro, pt, atr_val)

                        # Dynamic EMA Corridor: Price must NOT be collapsed far below EMA50, and must be in healthy pullback value area
                        is_ema_pullback_valid = (mid >= ema50 - 0.45 * atr_val) and (mid <= ema20 + 0.45 * atr_val)
                        if not is_ema_pullback_valid:
                            logger.debug(f"[PULLBACK BUY EMA GUARD] {sym} SKIP: mid {mid:.5f} outside healthy EMA zone [{ema50 - 0.45*atr_val:.5f} <= mid <= {ema20 + 0.45*atr_val:.5f}]")
                            continue

                        in_action_zone = (abs(mid - base_floor) <= 0.50 * atr_val) or (live_l <= base_floor + 0.15 * atr_val) or (base_floor <= mid <= base_floor + 0.65 * atr_val)
                        has_support_hold = (mid >= base_floor - 0.15 * atr_val) or (c_qual['max_lower_wick'] >= 0.10) or (c_qual['sweep_side'] == 'bottom')
                        if in_action_zone and has_support_hold and base_floor > 0:
                            lim_entry = base_floor + (spread_pts * 0.5 * pt)
                            sl_tp = calculate_intraday_sl_tp(
                                symbol=sym,
                                entry_price=lim_entry,
                                direction=1,
                                origin_level=base_floor,
                                atr_h1=atr_pts * pt,
                                pwl=macro.get('pwl', 0.0),
                                pwh=macro.get('pwh', 0.0),
                                rbs=macro.get('micro_rbs_h1') or macro.get('inter_rbs_h4'),
                                sbr=macro.get('micro_sbr_h1') or macro.get('inter_sbr_h4'),
                                spread_pts=spread_pts,
                                c1=macro.get('immediate_ceiling_c1') or macro.get('ceiling_c1'),
                                f1=macro.get('immediate_floor_f1') or macro.get('floor_f1')
                            )
                            sl = sl_tp['sl']
                            tp = sl_tp['tp']
                            if action_tier_m2_b in ("TP1_ONLY_SCALP", "REDUCED_SCALP"):
                                tp = sl_tp.get('tp1', round(lim_entry + (1.10 * abs(lim_entry - sl)), 5 if pt < 0.01 else 2))
                            rr_val = sl_tp['risk_reward']
                            if abs(lim_entry - mid) > 1.0 * atr_val:
                                logger.debug(f"[M2 BUY DISTANCE GUARD] {sym} SKIP: lim_entry {lim_entry:.5f} too far from mid {mid:.5f}")
                            elif abs(lim_entry - sl) / pt >= 15:
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
                                    economic_context=cal_text,
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
                                        "macro_corridor": m_corr,
                                        **zce_meta
                                    }
                                ))
                                continue

                    # SELL: (Bearish Macro OR Bearish Corridor) AND NOT Bullish Corridor + Pullback to FVG / OB / EMA50 / Resistance Ceiling
                    allowed_m2_s, action_tier_m2_s, reason_m2_s = _is_direction_allowed(-1, "SELL_PULLBACK")
                    can_sell_m2 = allowed_m2_s and (macro['is_bear'] or m_corr == "BEARISH_CORRIDOR") and (m_corr != "BULLISH_CORRIDOR")
                    
                    fvg_bear_bot = macro.get('bearish_fvg_bot', 0.0)
                    ob_bear_bot = macro.get('bearish_ob_bot', 0.0)
                    c1_ceiling = macro.get('immediate_ceiling_c1', 0.0)
                    has_fvg_or_ob_retest_s = (fvg_bear_bot > 0 and abs(mid - fvg_bear_bot) <= 0.50 * atr_val) or (ob_bear_bot > 0 and abs(mid - ob_bear_bot) <= 0.50 * atr_val)
                    has_ema_or_c1_retest_s = (abs(mid - ema50) <= 0.50 * atr_val) or (c1_ceiling > 0 and abs(mid - c1_ceiling) <= 0.50 * atr_val)
                    is_valid_pullback_range_s = (pos_in_range >= 0.35) and ((pos_in_range >= 0.45) or has_fvg_or_ob_retest_s or has_ema_or_c1_retest_s)

                    if not allowed_m2_s:
                        logger.debug(f"[PULLBACK SELL GATE] {sym} SKIP ({action_tier_m2_s}): {reason_m2_s}")
                    elif can_sell_m2 and is_valid_pullback_range_s:
                        base_ceiling, m2_confluence_desc = self.find_ema_confluence_anchor(sym, mid, -1, macro, pt, atr_val)

                        # Dynamic EMA Corridor: Price must NOT be blown up far above EMA50, and must be in healthy pullback value area
                        is_ema_pullback_valid = (mid <= ema50 + 0.45 * atr_val) and (mid >= ema20 - 0.45 * atr_val)
                        if not is_ema_pullback_valid:
                            logger.debug(f"[PULLBACK SELL EMA GUARD] {sym} SKIP: mid {mid:.5f} outside healthy EMA zone [{ema20 - 0.45*atr_val:.5f} <= mid <= {ema50 + 0.45*atr_val:.5f}]")
                            continue

                        in_action_zone = (abs(mid - base_ceiling) <= 0.50 * atr_val) or (live_h >= base_ceiling - 0.15 * atr_val) or (base_ceiling - 0.65 * atr_val <= mid <= base_ceiling)
                        has_res_hold = (mid <= base_ceiling + 0.15 * atr_val) or (c_qual['max_upper_wick'] >= 0.10) or (c_qual['sweep_side'] == 'top')
                        if in_action_zone and has_res_hold and base_ceiling > 0:
                            lim_entry = base_ceiling - (spread_pts * 0.5 * pt)
                            sl_tp = calculate_intraday_sl_tp(
                                symbol=sym,
                                entry_price=lim_entry,
                                direction=-1,
                                origin_level=base_ceiling,
                                atr_h1=atr_pts * pt,
                                pwl=macro.get('pwl', 0.0),
                                pwh=macro.get('pwh', 0.0),
                                rbs=macro.get('micro_rbs_h1') or macro.get('inter_rbs_h4'),
                                sbr=macro.get('micro_sbr_h1') or macro.get('inter_sbr_h4'),
                                spread_pts=spread_pts,
                                c1=macro.get('immediate_ceiling_c1') or macro.get('ceiling_c1'),
                                f1=macro.get('immediate_floor_f1') or macro.get('floor_f1')
                            )
                            sl = sl_tp['sl']
                            tp = sl_tp['tp']
                            if action_tier_m2_s in ("TP1_ONLY_SCALP", "REDUCED_SCALP"):
                                tp = sl_tp.get('tp1', round(lim_entry - (1.10 * abs(lim_entry - sl)), 5 if pt < 0.01 else 2))
                            rr_val = sl_tp['risk_reward']
                            if abs(lim_entry - mid) > 1.0 * atr_val:
                                logger.debug(f"[M2 SELL DISTANCE GUARD] {sym} SKIP: lim_entry {lim_entry:.5f} too far from mid {mid:.5f}")
                            elif abs(sl - lim_entry) / pt >= 15:
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
                                    economic_context=cal_text,
                                    action_tier=action_tier_m2_s,
                                    macro_bias_score=macro.get('macro_bias_score', 0.0),
                                    regime_stability=macro.get('regime_stability', 'STABLE'),
                                    metadata={
                                        "entry_type": "sell_limit",
                                        "entry_price": round(lim_entry, 5 if pt < 0.01 else 2),
                                        "base_floor": base_ceiling,
                                        "target_station": sl_tp.get('target_station', 0.0),
                                        "permission": perm_state,
                                        "csm_delta": csm_delta_val,
                                        "action_tier": action_tier_m2_s,
                                        "macro_corridor": m_corr,
                                        **zce_meta
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
                    dr_pos = macro.get('dealing_range_pos', 0.5)

                    # Bullish Breakout Retest: Broke above structural resistance (PDH/PWH/BOS H1/Cluster), now acting as RBS floor
                    pdh_barrier = macro.get('pdh', 0.0)
                    pwh_barrier = macro.get('pwh', 0.0)
                    bos_barrier = macro.get('h1_bos_level', 0.0) if macro.get('h1_bos_direction') == 'bullish' else 0.0
                    rbs_barrier = macro.get('micro_rbs_h1') or macro.get('inter_rbs_h4') or 0.0

                    # Broken resistance candidate levels (must be physically below current mid price)
                    # Priority 1: Multi-Touch Cluster with >= 2 touches (The Core Edge of M3)
                    if c_res > 0 and t_res >= 2 and c_res < mid:
                        target_res = c_res
                    else:
                        cand_res_list = [lvl for lvl in (pdh_barrier, pwh_barrier, bos_barrier, rbs_barrier) if (lvl > 0 and lvl < mid)]
                        target_res = max(cand_res_list) if cand_res_list else 0.0

                    allowed_m3_b, action_tier_m3_b, reason_m3_b = _is_direction_allowed(1, "BUY_BREAKOUT_RETEST", entry_price=target_res)
                    can_buy_m3 = allowed_m3_b and (macro['is_bull'] or m_corr == "BULLISH_CORRIDOR") and (m_corr != "BEARISH_CORRIDOR")
                    
                    is_locked_b, lock_reason_b = self.is_retest_locked(clean_sym, mid, atr_val)
                    if is_locked_b:
                        logger.debug(f"[BREAKOUT BUY DEBOUNCE] {sym} SKIP: {lock_reason_b}")
                    elif not allowed_m3_b:
                        logger.debug(f"[BREAKOUT BUY GATE] {sym} SKIP ({action_tier_m3_b}): {reason_m3_b}")
                    elif can_buy_m3 and (target_res > 0):
                        # Fresh Breakout Law & Displacement Guard (3 Sep 2026 - Branch 1 & 2)
                        # Breakout wajib terjadi dalam 3-4 bar H1 terakhir dan candle breakout wajib memiliki body >= 55%
                        recency_bars = getattr(config, "M3_BREAKOUT_RECENCY_BARS", 4)
                        min_disp_body = getattr(config, "M3_MIN_DISPLACEMENT_BODY", 0.55)
                        
                        has_fresh_break_b = False
                        is_displacement_b = False
                        
                        if df is not None and len(df) >= (recency_bars + 2):
                            recent_df = df.iloc[-(recency_bars + 1):]
                            for idx in range(1, len(recent_df)):
                                prev_bar = recent_df.iloc[idx - 1]
                                curr_bar = recent_df.iloc[idx]
                                crossed_up = (prev_bar['close'] <= target_res and curr_bar['close'] > target_res) or \
                                             (curr_bar['low'] <= target_res and curr_bar['close'] > target_res)
                                if crossed_up:
                                    has_fresh_break_b = True
                                    bar_range = curr_bar['high'] - curr_bar['low']
                                    bar_body = abs(curr_bar['close'] - curr_bar['open'])
                                    body_ratio = (bar_body / bar_range) if bar_range > 0 else 0.0
                                    if body_ratio >= min_disp_body and curr_bar['close'] > curr_bar['open']:
                                        is_displacement_b = True
                                        break
                        
                        if not has_fresh_break_b:
                            logger.debug(f"[BREAKOUT BUY RECENCY] {sym} SKIP: target_res {target_res:.5f} has no fresh breakout in last {recency_bars} H1 bars")
                        elif not is_displacement_b:
                            logger.debug(f"[BREAKOUT BUY DISPLACEMENT] {sym} SKIP: breakout candle body < {min_disp_body*100:.0f}% (no momentum displacement)")
                        else:
                            # Strict Retest Approach Gate: Trigger ONLY when price has pulled back within retest proximity of target_res
                            in_retest_window_b = (target_res - 0.10 * atr_val <= mid <= target_res + 0.28 * atr_val) or (live_l <= target_res + 0.15 * atr_val and mid >= target_res - 0.05 * atr_val)
                            if not in_retest_window_b:
                                logger.debug(f"[BREAKOUT BUY DISTANCE] {sym} SKIP: mid {mid:.5f} outside active retest touch zone [{target_res - 0.10*atr_val:.5f} - {target_res + 0.28*atr_val:.5f}]")
                            else:
                                # Runaway Flash Spike Guard: Excursion must not exceed 2.50x ATR
                                max_push_b = (max(df['high'].iloc[-(recency_bars + 2):]) - target_res) / atr_val if (df is not None and len(df) >= (recency_bars + 2) and atr_val > 0) else 0.0
                                if max_push_b > 2.50:
                                    logger.debug(f"[BREAKOUT BUY RUNAWAY] {sym} SKIP: excursion {max_push_b:.2f}x ATR > 2.50x ATR (flash spike exhaustion)")
                                else:
                                    # Cek Runway Struktural ke Plafon C1 berikutnya:
                                    target_ceiling = (macro.get('ceiling_c1') or macro.get('immediate_ceiling_c1') or 0.0)
                                    has_upward_runway = (target_ceiling <= 0.0) or ((target_ceiling - target_res) >= 0.80 * atr_val)
                                    if not has_upward_runway and dr_pos > 0.72:
                                        logger.debug(f"[BREAKOUT BUY EXTREME] {sym} SKIP: runway to ceiling {target_ceiling:.5f} insufficient ({target_ceiling - target_res:.5f}) and dr_pos {dr_pos*100:.1f}%")
                                    else:
                                        entry_lim = target_res - (spread_pts * 0.5 * pt) # Limit retest entry at broken resistance (now RBS)
                                sl_tp = calculate_intraday_sl_tp(
                                    symbol=sym,
                                entry_price=entry_lim,
                                direction=1,
                                origin_level=target_res,
                                atr_h1=atr_val,
                                pwl=macro.get('pwl', 0.0),
                                pwh=macro.get('pwh', 0.0),
                                rbs=macro.get('micro_rbs_h1') or macro.get('inter_rbs_h4'),
                                sbr=macro.get('micro_sbr_h1') or macro.get('inter_sbr_h4'),
                                spread_pts=spread_pts,
                                c1=((macro.get('ceiling_c1') or 0.0) if ((macro.get('ceiling_c1') or 0.0) > entry_lim) else ((macro.get('ceiling_c2') or 0.0) if ((macro.get('ceiling_c2') or 0.0) > entry_lim) else 0.0)) or (macro.get('immediate_ceiling_c1') or 0.0),
                                f1=target_res
                            )
                            sl = sl_tp['sl']
                            tp = sl_tp['tp']
                            if action_tier_m3_b in ("TP1_ONLY_SCALP", "REDUCED_SCALP"):
                                tp = sl_tp.get('tp1', round(entry_lim + (1.10 * abs(entry_lim - sl)), 5 if pt < 0.01 else 2))
                            rr_val = sl_tp['risk_reward']
                            if abs(entry_lim - mid) > 1.0 * atr_val:
                                logger.debug(f"[M3 BUY DISTANCE GUARD] {sym} SKIP: entry_lim {entry_lim:.5f} too far from mid {mid:.5f}")
                            elif abs(entry_lim - sl) / pt >= 15:
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
                                    key_support=target_res,
                                    key_resistance=macro['dealing_range_high'],
                                    suggested_sl=sl,
                                    suggested_tp=tp,
                                    risk_reward_ratio=rr_val,
                                    strong_low=target_res,
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
                                    economic_context=cal_text,
                                    action_tier=action_tier_m3_b,
                                    macro_bias_score=macro.get('macro_bias_score', 0.0),
                                    regime_stability=macro.get('regime_stability', 'STABLE'),
                                    metadata={
                                        "entry_type": "buy_limit",
                                        "entry_price": round(entry_lim, 5 if pt < 0.01 else 2),
                                        "zone_level": target_res,
                                        "zone_touches": t_res,
                                        "range_age_hours": macro.get('range_age_hours', 24),
                                        "wave_regime": macro.get('wave_regime_name', 'YOUNG_OSCILLATION'),
                                        "target_station": sl_tp.get('target_station', 0.0),
                                        "permission": perm_state,
                                        "csm_delta": csm_delta_val,
                                        "action_tier": action_tier_m3_b,
                                        "macro_corridor": m_corr,
                                        **zce_meta
                                    }
                                ))
                                continue

                    # Bearish Breakout Retest: Broke below structural support (PDL/PWL/BOS H1/Cluster), now acting as SBR ceiling
                    pdl_barrier = macro.get('pdl', 0.0)
                    pwl_barrier = macro.get('pwl', 0.0)
                    bos_sup_barrier = macro.get('h1_bos_level', 0.0) if macro.get('h1_bos_direction') == 'bearish' else 0.0
                    sbr_barrier = macro.get('micro_sbr_h1') or macro.get('inter_sbr_h4') or 0.0

                    # Broken support candidate levels (must be physically above current mid price)
                    # Priority 1: Multi-Touch Cluster with >= 2 touches (The Core Edge of M3)
                    if c_sup > 0 and t_sup >= 2 and c_sup > mid:
                        target_sup = c_sup
                    else:
                        cand_sup_list = [lvl for lvl in (pdl_barrier, pwl_barrier, bos_sup_barrier, sbr_barrier) if (lvl > 0 and lvl > mid)]
                        target_sup = min(cand_sup_list) if cand_sup_list else 0.0

                    allowed_m3_s, action_tier_m3_s, reason_m3_s = _is_direction_allowed(-1, "SELL_BREAKOUT_RETEST", entry_price=target_sup)
                    can_sell_m3 = allowed_m3_s and (macro['is_bear'] or m_corr == "BEARISH_CORRIDOR") and (m_corr != "BULLISH_CORRIDOR")
                    
                    is_locked_s, lock_reason_s = self.is_retest_locked(clean_sym, mid, atr_val)
                    if is_locked_s:
                        logger.debug(f"[BREAKOUT SELL DEBOUNCE] {sym} SKIP: {lock_reason_s}")
                    elif not allowed_m3_s:
                        logger.debug(f"[BREAKOUT SELL GATE] {sym} SKIP ({action_tier_m3_s}): {reason_m3_s}")
                    elif can_sell_m3 and (target_sup > 0):
                        # Fresh Breakout Law & Displacement Guard (3 Sep 2026 - Branch 1 & 2)
                        # Breakdown wajib terjadi dalam 3-4 bar H1 terakhir dan candle breakdown wajib memiliki body >= 55%
                        recency_bars = getattr(config, "M3_BREAKOUT_RECENCY_BARS", 4)
                        min_disp_body = getattr(config, "M3_MIN_DISPLACEMENT_BODY", 0.55)
                        
                        has_fresh_break_s = False
                        is_displacement_s = False
                        
                        if df is not None and len(df) >= (recency_bars + 2):
                            recent_df = df.iloc[-(recency_bars + 1):]
                            for idx in range(1, len(recent_df)):
                                prev_bar = recent_df.iloc[idx - 1]
                                curr_bar = recent_df.iloc[idx]
                                crossed_down = (prev_bar['close'] >= target_sup and curr_bar['close'] < target_sup) or \
                                               (curr_bar['high'] >= target_sup and curr_bar['close'] < target_sup)
                                if crossed_down:
                                    has_fresh_break_s = True
                                    bar_range = curr_bar['high'] - curr_bar['low']
                                    bar_body = abs(curr_bar['close'] - curr_bar['open'])
                                    body_ratio = (bar_body / bar_range) if bar_range > 0 else 0.0
                                    if body_ratio >= min_disp_body and curr_bar['close'] < curr_bar['open']:
                                        is_displacement_s = True
                                        break
                        
                        if not has_fresh_break_s:
                            logger.debug(f"[BREAKOUT SELL RECENCY] {sym} SKIP: target_sup {target_sup:.5f} has no fresh breakdown in last {recency_bars} H1 bars")
                        elif not is_displacement_s:
                            logger.debug(f"[BREAKOUT SELL DISPLACEMENT] {sym} SKIP: breakdown candle body < {min_disp_body*100:.0f}% (no momentum displacement)")
                        else:
                            # Strict Retest Approach Gate: Trigger ONLY when price has pulled back within retest proximity of target_sup
                            in_retest_window_s = (target_sup - 0.28 * atr_val <= mid <= target_sup + 0.10 * atr_val) or (live_h >= target_sup - 0.15 * atr_val and mid <= target_sup + 0.05 * atr_val)
                            if not in_retest_window_s:
                                logger.debug(f"[BREAKOUT SELL DISTANCE] {sym} SKIP: mid {mid:.5f} outside active retest touch zone [{target_sup - 0.28*atr_val:.5f} - {target_sup + 0.10*atr_val:.5f}]")
                            else:
                                # Runaway Flash Dump Guard: Excursion must not exceed 2.50x ATR
                                max_push_s = (target_sup - min(df['low'].iloc[-(recency_bars + 2):])) / atr_val if (df is not None and len(df) >= (recency_bars + 2) and atr_val > 0) else 0.0
                                if max_push_s > 2.50:
                                    logger.debug(f"[BREAKOUT SELL RUNAWAY] {sym} SKIP: excursion {max_push_s:.2f}x ATR > 2.50x ATR (flash dump exhaustion)")
                                else:
                                    # Cek Runway Struktural ke Lantai F1 berikutnya:
                                    target_floor = (macro.get('floor_f1') or macro.get('immediate_floor_f1') or 0.0)
                                    has_downward_runway = (target_floor <= 0.0) or ((target_sup - target_floor) >= 0.80 * atr_val)
                                    if not has_downward_runway and dr_pos < 0.28:
                                        logger.debug(f"[BREAKOUT SELL EXTREME] {sym} SKIP: runway to floor {target_floor:.5f} insufficient ({target_sup - target_floor:.5f}) and dr_pos {dr_pos*100:.1f}%")
                                    else:
                                        entry_lim = target_sup + (spread_pts * 0.5 * pt) # Limit retest entry at broken support (now SBR)
                                sl_tp = calculate_intraday_sl_tp(
                                symbol=sym,
                                entry_price=entry_lim,
                                direction=-1,
                                origin_level=target_sup,
                                atr_h1=atr_val,
                                pwl=macro.get('pwl', 0.0),
                                pwh=macro.get('pwh', 0.0),
                                rbs=macro.get('micro_rbs_h1') or macro.get('inter_rbs_h4'),
                                sbr=macro.get('micro_sbr_h1') or macro.get('inter_sbr_h4'),
                                spread_pts=spread_pts,
                                c1=target_sup,
                                f1=((macro.get('floor_f1') or 0.0) if ((macro.get('floor_f1') or 0.0) > 0.0 and (macro.get('floor_f1') or 0.0) < entry_lim) else ((macro.get('floor_f2') or 0.0) if ((macro.get('floor_f2') or 0.0) > 0.0 and (macro.get('floor_f2') or 0.0) < entry_lim) else 0.0)) or (macro.get('immediate_floor_f1') or 0.0)
                            )
                            sl = sl_tp['sl']
                            tp = sl_tp['tp']
                            if action_tier_m3_s in ("TP1_ONLY_SCALP", "REDUCED_SCALP"):
                                tp = sl_tp.get('tp1', round(entry_lim - (1.10 * abs(entry_lim - sl)), 5 if pt < 0.01 else 2))
                            rr_val = sl_tp['risk_reward']
                            if abs(entry_lim - mid) > 1.0 * atr_val:
                                logger.debug(f"[M3 SELL DISTANCE GUARD] {sym} SKIP: entry_lim {entry_lim:.5f} too far from mid {mid:.5f}")
                            elif abs(sl - entry_lim) / pt >= 15:
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
                                    key_resistance=target_sup,
                                    suggested_sl=sl,
                                    suggested_tp=tp,
                                    risk_reward_ratio=rr_val,
                                    strong_low=macro.get('strong_low', 0.0),
                                    strong_high=target_sup,
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
                                    economic_context=cal_text,
                                    action_tier=action_tier_m3_s,
                                    macro_bias_score=macro.get('macro_bias_score', 0.0),
                                    regime_stability=macro.get('regime_stability', 'STABLE'),
                                    metadata={
                                        "entry_type": "sell_limit",
                                        "entry_price": round(entry_lim, 5 if pt < 0.01 else 2),
                                        "zone_level": target_sup,
                                        "zone_touches": t_sup,
                                        "range_age_hours": macro.get('range_age_hours', 24),
                                        "wave_regime": macro.get('wave_regime_name', 'YOUNG_OSCILLATION'),
                                        "target_station": sl_tp.get('target_station', 0.0),
                                        "permission": perm_state,
                                        "csm_delta": csm_delta_val,
                                        "action_tier": action_tier_m3_s,
                                        "macro_corridor": m_corr,
                                        **zce_meta
                                    }
                                ))
                                continue

                # ═══════════════════════════════════════════════════════════════
                # M4: SYSTEMIC FLOW CONTINUATION (Mechanism 4 — 3 Sep 2026)
                # Studi #1/#1b mirror: breakdown swing 120-bar mengikuti currency flow
                # z>=1.5 -> limit retest di level. SL/TP STRUKTURAL (0.45xATR & 1.1R)
                # dibekukan di consensus._apply_sltp_rules (bypass floor/ceiling/RR).
                # ═══════════════════════════════════════════════════════════════
                if (config.M4_ENABLED and (8 <= h <= 23) and self.is_symbol_allowed_for_session(sym, h)
                        and clean_sym in self._m4_universe
                        and (now_ts - self._m4_feed_updated) < 4200.0):
                    try:
                        atr_now = float(macro.get('current_atr', 0.0) or 0.0)
                        if atr_now <= 0:
                            atr_now = atr_pts * pt
                        for _side_key in ("SELL", "BUY"):
                            pend = self._m4_pending_ready(clean_sym, _side_key, mid, atr_now)
                            if pend is None:
                                continue
                            _dir = -1 if _side_key == "SELL" else 1
                            _alw, _tier, _why = _is_direction_allowed(_dir, config.M4_SETUP_TYPE, entry_price=pend["level"])
                            if not _alw:
                                logger.debug(f"[M4] {sym} {_side_key} gate-blocked: {_why}")
                                continue
                            _level = pend["level"]
                            _sl = pend["sl"]
                            _tp = pend["tp"]
                            _dec = 5 if pt < 0.01 else 2
                            _r_pts = max(1, int(round(abs(_sl - _level) / pt)))
                            _tp_pts = max(1, int(round(abs(_tp - _level) / pt)))
                            _entry = round(_level, _dec)
                            _etype = "sell_limit" if _side_key == "SELL" else "buy_limit"
                            _m4_cand = CandidateSetup(
                                symbol=sym,
                                setup_type=config.M4_SETUP_TYPE,
                                direction=_dir,
                                trigger_price=_entry,
                                timeframe="H1",
                                macro_compass=str(macro.get('macro_compass', macro.get('trend_compass', '')) or ''),
                                dealing_range_pos=float(macro.get('dealing_range_pos', macro.get('dr_pos', 0.5)) or 0.5),
                                rejection_wick_ratio=0.0,
                                current_spread_pts=int(spread_pts),
                                current_atr_pts=int(atr_pts),
                                suggested_sl=round(_sl, _dec),
                                suggested_tp=round(_tp, _dec),
                                risk_reward_ratio=round(_tp_pts / _r_pts, 2),
                                permission=perm_state,
                                csm_delta=csm_delta_val,
                                timestamp_wib=now.strftime("%H:%M:%S WIB"),
                                economic_context=cal_text or '',
                                action_tier=_tier,
                                macro_bias_score=macro.get('macro_bias_score', 0.0),
                                regime_stability=macro.get('regime_stability', 'STABLE'),
                                scan_mid=mid,
                                metadata={
                                    "entry_type": _etype,
                                    "entry_price": _entry,
                                    "m4_level": _level,
                                    "m4_sl_pts": _r_pts,
                                    "m4_tp_pts": _tp_pts,
                                    "m4_atr_price": round(pend.get("atr", 0.0), 6),
                                    "m4_direction": _side_key,
                                    "permission": perm_state,
                                    "csm_delta": csm_delta_val,
                                    "action_tier": _tier,
                                    **zce_meta
                                },
                            )
                            candidates.append(_m4_cand)
                            self._m4_state[clean_sym][_side_key]["pending"] = None  # 1 percobaan Stage-2 per break
                            self._symbol_last_trigger[clean_sym] = now_ts
                            logger.info(f"[M4] {sym} {_side_key} @ {_entry} | SL {_sl:.{_dec}f} (0.45xATR) | TP {_tp:.{_dec}f} (1.1R) | tier {_tier}")
                            break
                    except Exception as _m4e:
                        logger.debug(f"M4 eval error on {sym}: {_m4e}")

            except Exception as e:
                logger.debug(f"Radar check error on {sym}: {e}")

        for c in candidates:
            # --- A5 FIX: bind scan-time market price as drift baseline for stale-guard (trigger_price = limit anchor, not market) ---
            if c.scan_mid <= 0.0 and c.symbol:
                try:
                    _tk = None
                    if mt5_connector is not None and hasattr(mt5_connector, 'get_live_tick'):
                        _tk = mt5_connector.get_live_tick(c.symbol)
                    elif hasattr(config.mt5, 'symbol_info_tick'):
                        _tk = config.mt5.symbol_info_tick(c.symbol)
                    if _tk is not None and hasattr(_tk, 'bid') and hasattr(_tk, 'ask'):
                        c.scan_mid = float((_tk.bid + _tk.ask) / 2.0)
                except Exception:
                    pass
            c_clean = c.symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").upper()
            self._symbol_last_trigger[c_clean] = now_ts
        if candidates:
            self._save_cooldowns()

        # ── Periodic Quant Funnel Snapshot Logger (Dump ke gate_debug.log tiap 5 menit) ──
        if (now_ts - getattr(self, "_last_snapshot_ts", 0.0)) >= 300.0:
            self._log_periodic_quant_snapshot()
            self._last_snapshot_ts = now_ts

        self.last_candidates = candidates
        return candidates

    def _log_periodic_quant_snapshot(self) -> None:
        """Dump ringkasan spatial grid 26-pair (ZCE walls, MSE state/tier, M4 standbys)
        ke gate_debug.log tiap 5 menit (0% komputasi baru, hanya baca memori RAM)."""
        try:
            lines = ["[QUANT FUNNEL 5-MIN SNAPSHOT] 26-Pair Spatial Grid (ZCE Walls | MSE State & Tier | M4 Standby):"]
            for sym in self.symbols:
                clean = sym.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
                macro = self.macro_cache.get(sym, {})
                strat = macro.get("strat_dir")
                tier = getattr(strat, "action_tier", macro.get("action_tier", "N/A"))
                m_state = getattr(strat, "market_state", "N/A")
                f1 = macro.get("immediate_floor_f1") or macro.get("floor_f1")
                c1 = macro.get("immediate_ceiling_c1") or macro.get("ceiling_c1")
                pos = float(macro.get("dealing_range_pos", macro.get("dr_pos", 0.5)) or 0.5) * 100.0

                m4_str = "None"
                if hasattr(self, "_m4_state"):
                    for s in ("SELL", "BUY"):
                        p = self._m4_state.get(clean, {}).get(s, {}).get("pending")
                        if p:
                            lvl = p.get("level", 0.0)
                            m4_str = f"{s}@{lvl:.4f}"
                            break

                f1_txt = f"F1={f1:.4f}" if f1 else "F1=None"
                c1_txt = f"C1={c1:.4f}" if c1 else "C1=None"
                lines.append(f"  {clean:8} | MSE: {tier:<16} ({m_state:<18}) | ZCE: {f1_txt} {c1_txt} | Pos: {pos:5.1f}% | M4: {m4_str}")
            logger.debug("\n" + "\n".join(lines))
        except Exception as e:
            logger.debug(f"Snapshot logging error: {e}")

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
            d_st = "BULLISH" if m.get('is_bull') else ("BEARISH" if m.get('is_bear') else "NEUTRAL")
            pos_p = int(m.get('dealing_range_pos', 0.5) * 100)
            
            if perm == "GO":
                go_pairs.append(f"{clean} ({d_st} {pos_p}%)")
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
