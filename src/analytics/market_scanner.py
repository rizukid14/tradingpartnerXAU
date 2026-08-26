import os
import sys
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any

import numpy as np  # type: ignore
import pandas as pd  # type: ignore

import config
from src.indicators.lux_smc import LuxSMCAnalyzer

logger = logging.getLogger("market_scanner")
WIB = ZoneInfo("Asia/Jakarta")

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
    setup_type: str                  # 'TREND_ALIGNED_PULLBACK', 'LONDON_JUDAS_SWEEP', 'NY_ADR_REVERSAL', 'SMC_CHOCH'
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
    economic_context: str = ""
    timestamp_wib: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_payload_dict(self) -> Dict[str, Any]:
        """Convert setup to high-density JSON payload for 3-LLM Consensus Jury."""
        return {
            "event": "FAST_RADAR_TRIGGER_CONFIRMED",
            "symbol": self.symbol,
            "setup_type": self.setup_type,
            "direction": "BUY" if self.direction == 1 else "SELL",
            "trigger_price": self.trigger_price,
            "timeframe": self.timeframe,
            "timestamp_wib": self.timestamp_wib or datetime.now(WIB).strftime("%H:%M:%S WIB"),
            "macro_compass": self.macro_compass,
            "dealing_range_position": f"{self.dealing_range_pos*100:.1f}% ({'DEEP DISCOUNT' if self.dealing_range_pos <= 0.38 else ('EXTREME PREMIUM' if self.dealing_range_pos >= 0.62 else 'EQUILIBRIUM')})",
            "rejection_wick_ratio": f"{self.rejection_wick_ratio*100:.1f}%",
            "current_spread_pts": self.current_spread_pts,
            "current_atr_pts": round(self.current_atr_pts, 1),
            "key_support": self.key_support,
            "key_resistance": self.key_resistance,
            "suggested_sl": self.suggested_sl,
            "suggested_tp": self.suggested_tp,
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "economic_calendar": self.economic_context or "NO_HIGH_IMPACT_NEWS_IN_NEXT_4_HOURS",
            "directive_for_llm": f"Evaluate macro sentiment and confirm {'BUY' if self.direction == 1 else 'SELL'} with structural SL at {self.suggested_sl} and TP at {self.suggested_tp}"
        }


class MarketScanner:
    """
    2-Stage Quant Funnel Market Scanner:
    - Stage 1A (Slow Macro Layer): Updates D1/H4 Trend Compass, Asian High/Low, and Dealing Range every hour.
    - Stage 1B (Fast Execution Radar): Scans live ticks / M5/M15 wicks across 22 symbols every 60 seconds (0 Tokens).
    """

    def __init__(self, symbols: Optional[List[str]] = None):
        self.symbols = symbols or config.get_scanner_symbols()
        self.macro_cache: Dict[str, Dict[str, Any]] = {}
        self.last_macro_update: Optional[datetime] = None
        self.last_candidates: List[CandidateSetup] = []
        self._last_radar_scan_time: float = 0.0

    def _get_point(self, symbol: str) -> float:
        clean = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "")
        return POINT_MAP.get(clean, 1e-5)

    @staticmethod
    def is_symbol_allowed_for_session(symbol: str, hour_wib: int) -> bool:
        """
        Filters symbols based on empirical expected value (EV) per trading session.
        - Tokyo Session (08:00 - 14:00 WIB): Only allow proven positive-EV pairs (Asia/Commodities).
        - London & NY Sessions (14:00 - 23:59 WIB): Allow all configured 22 pairs.
        """
        clean_sym = symbol.replace('-ECNc', '').replace('-ECN', '').replace('.c', '').replace('m', '').replace('_', '')
        if 8 <= hour_wib < 14:
            return clean_sym in TOKYO_PROVEN_SYMBOLS
        elif 14 <= hour_wib <= 23:
            return True
        return False

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

                # Fetch 120 bars of H1
                rates = None
                if hasattr(config.mt5, 'copy_rates_from_pos'):
                    rates = config.mt5.copy_rates_from_pos(valid_sym, config.mt5.TIMEFRAME_H1, 0, 120)
                if (rates is None or len(rates) < 30) and mt5_connector is not None and hasattr(mt5_connector, 'get_closed_bars'):
                    rates = mt5_connector.get_closed_bars(valid_sym, count=120, timeframe=config.mt5.TIMEFRAME_H1)
                
                if rates is None or len(rates) < 30:
                    continue

                df = pd.DataFrame(rates)
                if 'time' in df.columns:
                    if not pd.api.types.is_datetime64_any_dtype(df['time']):
                        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True).dt.tz_convert(WIB)
                    df.set_index('time', inplace=True)

                pt = self._get_point(valid_sym)

                # Indicators
                df['atr'] = self._calc_atr(df, 14)
                df['adx'] = self._calc_adx(df, 14)
                df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
                df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
                df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

                # Dealing range (100 bars)
                sess_h = df['high'].rolling(100, min_periods=20).max().iloc[-1]
                sess_l = df['low'].rolling(100, min_periods=20).min().iloc[-1]
                cur_close = df['close'].iloc[-1]
                rng = max(sess_h - sess_l, 1e-5)
                pos_in_range = (cur_close - sess_l) / rng

                # D1 / H4 Trend Compass
                cur_ema20 = df['ema20'].iloc[-1]
                cur_ema50 = df['ema50'].iloc[-1]
                cur_ema200 = df['ema200'].iloc[-1]
                cur_adx = df['adx'].iloc[-1]

                is_d1_bull = (cur_close > cur_ema200) and (cur_ema50 > cur_ema200) and (cur_adx >= 20)
                is_d1_bear = (cur_close < cur_ema200) and (cur_ema50 < cur_ema200) and (cur_adx >= 20)

                trend_label = "D1_BULLISH_TREND" if is_d1_bull else ("D1_BEARISH_TREND" if is_d1_bear else "D1_SIDEWAYS_RANGE")

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
                d_range = df['high'].rolling(24, min_periods=10).max() - df['low'].rolling(24, min_periods=10).min()
                adr20 = d_range.rolling(20 * 24, min_periods=20).mean().iloc[-1]
                cur_day_range = d_range.iloc[-1]
                adr_pct = (cur_day_range / adr20) if (pd.notna(adr20) and adr20 > 0) else 0.5

                # ── LUXALGO SMC STRUCTURAL SCANNER (Order Blocks, FVG, Strong/Weak) ──
                smc_analyzer = LuxSMCAnalyzer(swing_length=5)
                smc_sig = smc_analyzer.analyze(df, point_size=pt)

                bull_ob_str = ""
                if smc_sig.order_blocks_bullish:
                    lob = smc_sig.order_blocks_bullish[-1]
                    bull_ob_str = f"[{lob['bottom']:.5f} - {lob['top']:.5f}] (Unmitigated)"

                bear_ob_str = ""
                if smc_sig.order_blocks_bearish:
                    lob = smc_sig.order_blocks_bearish[-1]
                    bear_ob_str = f"[{lob['bottom']:.5f} - {lob['top']:.5f}] (Unmitigated)"

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

                self.macro_cache[valid_sym] = {
                    'symbol': valid_sym,
                    'trend_label': f"{trend_label} (ADX {cur_adx:.1f}, EMA200={cur_ema200:.5f})",
                    'is_bull': is_d1_bull,
                    'is_bear': is_d1_bear,
                    'ema20': cur_ema20,
                    'ema50': cur_ema50,
                    'ema200': cur_ema200,
                    'adx': cur_adx,
                    'atr_pts': (df['atr'].iloc[-1] / pt) if pd.notna(df['atr'].iloc[-1]) else 300,
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
                    'point': pt,
                    'last_update': now
                }
            except Exception as e:
                logger.warning(f"Error updating macro context for {sym}: {e}")

        self.last_macro_update = now
        logger.info(f"✅ Macro Context Layer updated for {len(self.macro_cache)}/{len(self.symbols)} symbols.")

    def scan_fast_radar(self, mt5_connector=None) -> List[CandidateSetup]:
        """
        Fast Execution Radar: Runs every 60 seconds across 22 symbols.
        Checks live tick / M5-M15 wicks against cached macro levels.
        Returns list of qualifying CandidateSetup objects (0 Tokens).
        """
        now = datetime.now(WIB)
        h = now.hour
        dow = now.weekday()
        
        # Dead Zone / Weekend Filter (00:00 - 08:00 WIB)
        if dow == 5 or (dow == 4 and h >= 22) or (dow == 6 and h < 8) or (0 <= h < 8):
            return []

        # Ensure macro cache is initialized
        if not self.macro_cache or (self.last_macro_update and (now - self.last_macro_update).total_seconds() > 3600):
            self.update_macro_context(mt5_connector=mt5_connector)

        candidates: List[CandidateSetup] = []
        is_london_open = (14 <= h <= 18)
        is_ny_session = (19 <= h <= 23)

        for sym, macro in self.macro_cache.items():
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

                # ── MECHANISM 1: LONDON & NY JUDAS LIQUIDITY SWEEP (M15/M30/H1) ──
                if is_london_open or is_ny_session:
                    asian_h = macro.get('asian_high', 0.0)
                    asian_l = macro.get('asian_low', 0.0)
                    sweep_tol = atr_pts * 0.35 * pt
                    
                    # Bearish Judas Sweep: Price pushed above Asian High / Liquidity Pool, now rejecting back down
                    if (asian_h > 0) and (asian_h - sweep_tol <= mid <= asian_h + (atr_pts * 0.50 * pt)):
                        sl = max(asian_h, mid) + (atr_pts * 0.40 * pt) + (spread_pts * pt)
                        tp = mid - abs(sl - mid) * 2.2
                        if abs(mid - sl) / pt >= 15:
                            candidates.append(CandidateSetup(
                                symbol=sym,
                                setup_type="LONDON_JUDAS_SWEEP",
                                direction=-1,
                                trigger_price=bid,
                                timeframe="M30" if ("XAU" in sym or "JPY" in sym) else "H1",
                                macro_compass=macro['trend_label'],
                                dealing_range_pos=macro['dealing_range_pos'],
                                rejection_wick_ratio=0.35,
                                current_spread_pts=spread_pts,
                                current_atr_pts=atr_pts,
                                key_support=asian_l,
                                key_resistance=asian_h,
                                suggested_sl=round(sl, 5 if pt < 0.01 else 2),
                                suggested_tp=round(tp, 5 if pt < 0.01 else 2),
                                risk_reward_ratio=2.2,
                                strong_low=macro.get('strong_low', 0.0),
                                strong_high=macro.get('strong_high', 0.0),
                                bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                fvg_zone=macro.get('fvg_zone', ""),
                                liquidity_pools=macro.get('liquidity_pools', ""),
                                timestamp_wib=now.strftime("%H:%M:%S WIB")
                            ))
                            continue

                    # Bullish Judas Sweep: Price pushed below Asian Low / Liquidity Pool, now rejecting back up
                    if (asian_l > 0) and (asian_l - (atr_pts * 0.50 * pt) <= mid <= asian_l + sweep_tol):
                        sl = min(asian_l, mid) - (atr_pts * 0.40 * pt) - (spread_pts * pt)
                        tp = mid + abs(mid - sl) * 2.2
                        if abs(mid - sl) / pt >= 15:
                            candidates.append(CandidateSetup(
                                symbol=sym,
                                setup_type="LONDON_JUDAS_SWEEP",
                                direction=1,
                                trigger_price=ask,
                                timeframe="M30" if ("XAU" in sym or "JPY" in sym) else "H1",
                                macro_compass=macro['trend_label'],
                                dealing_range_pos=macro['dealing_range_pos'],
                                rejection_wick_ratio=0.35,
                                current_spread_pts=spread_pts,
                                current_atr_pts=atr_pts,
                                key_support=asian_l,
                                key_resistance=asian_h,
                                suggested_sl=round(sl, 5 if pt < 0.01 else 2),
                                suggested_tp=round(tp, 5 if pt < 0.01 else 2),
                                risk_reward_ratio=2.2,
                                strong_low=macro.get('strong_low', 0.0),
                                strong_high=macro.get('strong_high', 0.0),
                                bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                fvg_zone=macro.get('fvg_zone', ""),
                                liquidity_pools=macro.get('liquidity_pools', ""),
                                timestamp_wib=now.strftime("%H:%M:%S WIB")
                            ))
                            continue

                # ── MECHANISM 2: TREND-ALIGNED MULTI-TIMEFRAME PULLBACK (H1/H4 PULLBACK) ──
                if (8 <= h <= 23) and self.is_symbol_allowed_for_session(sym, h):
                    ema20 = macro['ema20']
                    pos_in_range = macro['dealing_range_pos']
                    
                    # BUY: Bullish Macro + Intraday Pullback into EMA20 / Support zone (pos <= 0.65)
                    if macro['is_bull'] and pos_in_range <= 0.65:
                        if abs(mid - ema20) <= (atr_pts * 0.45 * pt):
                            sl = mid - (atr_pts * 0.75 * pt) - (spread_pts * pt)
                            tp = mid + abs(mid - sl) * 2.2
                            if abs(mid - sl) / pt >= 15:
                                candidates.append(CandidateSetup(
                                    symbol=sym,
                                    setup_type="TREND_ALIGNED_PULLBACK",
                                    direction=1,
                                    trigger_price=ask,
                                    timeframe="M30" if ("XAU" in sym or "JPY" in sym) else "H1",
                                    macro_compass=macro['trend_label'],
                                    dealing_range_pos=pos_in_range,
                                    rejection_wick_ratio=0.30,
                                    current_spread_pts=spread_pts,
                                    current_atr_pts=atr_pts,
                                    key_support=ema20,
                                    key_resistance=macro['dealing_range_high'],
                                    suggested_sl=round(sl, 5 if pt < 0.01 else 2),
                                    suggested_tp=round(tp, 5 if pt < 0.01 else 2),
                                    risk_reward_ratio=2.2,
                                    strong_low=macro.get('strong_low', 0.0),
                                    strong_high=macro.get('strong_high', 0.0),
                                    bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                    bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                    fvg_zone=macro.get('fvg_zone', ""),
                                    liquidity_pools=macro.get('liquidity_pools', ""),
                                    timestamp_wib=now.strftime("%H:%M:%S WIB")
                                ))
                                continue

                    # SELL: Bearish Macro + Intraday Pullback into EMA20 / Resistance zone (pos >= 0.35)
                    if macro['is_bear'] and pos_in_range >= 0.35:
                        if abs(mid - ema20) <= (atr_pts * 0.45 * pt):
                            sl = mid + (atr_pts * 0.75 * pt) + (spread_pts * pt)
                            tp = mid - abs(sl - mid) * 2.2
                            if abs(mid - sl) / pt >= 15:
                                candidates.append(CandidateSetup(
                                    symbol=sym,
                                    setup_type="TREND_ALIGNED_PULLBACK",
                                    direction=-1,
                                    trigger_price=bid,
                                    timeframe="M30" if ("XAU" in sym or "JPY" in sym) else "H1",
                                    macro_compass=macro['trend_label'],
                                    dealing_range_pos=pos_in_range,
                                    rejection_wick_ratio=0.30,
                                    current_spread_pts=spread_pts,
                                    current_atr_pts=atr_pts,
                                    key_support=macro['dealing_range_low'],
                                    key_resistance=ema20,
                                    suggested_sl=round(sl, 5 if pt < 0.01 else 2),
                                    suggested_tp=round(tp, 5 if pt < 0.01 else 2),
                                    risk_reward_ratio=2.2,
                                    strong_low=macro.get('strong_low', 0.0),
                                    strong_high=macro.get('strong_high', 0.0),
                                    bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                    bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                    fvg_zone=macro.get('fvg_zone', ""),
                                    liquidity_pools=macro.get('liquidity_pools', ""),
                                    timestamp_wib=now.strftime("%H:%M:%S WIB")
                                ))
                                continue

                # ── MECHANISM 3: NY ADR RANGE REVERSAL (XAUUSD & Range Majors) ──
                if is_ny_session and macro.get('adr_pct', 0.0) >= 0.75:
                    pos_in_range = macro['dealing_range_pos']
                    if pos_in_range >= 0.65: # Top of range -> Fading SELL
                        sl = mid + (atr_pts * 0.6 * pt) + (spread_pts * pt)
                        tp = mid - abs(sl - mid) * 2.0
                        candidates.append(CandidateSetup(
                            symbol=sym,
                            setup_type="NY_ADR_REVERSAL",
                            direction=-1,
                            trigger_price=bid,
                            timeframe="M30",
                            macro_compass=macro['trend_label'],
                            dealing_range_pos=pos_in_range,
                            rejection_wick_ratio=0.35,
                            current_spread_pts=spread_pts,
                            current_atr_pts=atr_pts,
                            key_support=macro['dealing_range_low'],
                            key_resistance=macro['dealing_range_high'],
                            suggested_sl=round(sl, 5 if pt < 0.01 else 2),
                            suggested_tp=round(tp, 5 if pt < 0.01 else 2),
                            risk_reward_ratio=2.0,
                            strong_low=macro.get('strong_low', 0.0),
                            strong_high=macro.get('strong_high', 0.0),
                            bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                            bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                            fvg_zone=macro.get('fvg_zone', ""),
                            liquidity_pools=macro.get('liquidity_pools', ""),
                            timestamp_wib=now.strftime("%H:%M:%S WIB")
                        ))
                    elif pos_in_range <= 0.35: # Bottom of range -> Fading BUY
                        sl = mid - (atr_pts * 0.6 * pt) - (spread_pts * pt)
                        tp = mid + abs(mid - sl) * 2.0
                        candidates.append(CandidateSetup(
                            symbol=sym,
                            setup_type="NY_ADR_REVERSAL",
                            direction=1,
                            trigger_price=ask,
                            timeframe="M30",
                            macro_compass=macro['trend_label'],
                            dealing_range_pos=pos_in_range,
                            rejection_wick_ratio=0.35,
                            current_spread_pts=spread_pts,
                            current_atr_pts=atr_pts,
                            key_support=macro['dealing_range_low'],
                            key_resistance=macro['dealing_range_high'],
                            suggested_sl=round(sl, 5 if pt < 0.01 else 2),
                            suggested_tp=round(tp, 5 if pt < 0.01 else 2),
                            risk_reward_ratio=2.0,
                            strong_low=macro.get('strong_low', 0.0),
                            strong_high=macro.get('strong_high', 0.0),
                            bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                            bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                            fvg_zone=macro.get('fvg_zone', ""),
                            liquidity_pools=macro.get('liquidity_pools', ""),
                            timestamp_wib=now.strftime("%H:%M:%S WIB")
                        ))
                        continue

                # ── MECHANISM 4: M5 SNIPER LIQUIDITY SWEEP (2-HOUR LOCAL INTRADAY SWEEP) ──
                if config.mt5 is not None and hasattr(config.mt5, "copy_rates_from_pos"):
                    try:
                        m5_rates = config.mt5.copy_rates_from_pos(sym, config.mt5.TIMEFRAME_M5, 0, 26)
                        if m5_rates is not None and len(m5_rates) >= 25:
                            m5_highs = [b['high'] for b in m5_rates[:-1]]
                            m5_lows = [b['low'] for b in m5_rates[:-1]]
                            prev_24_h = max(m5_highs)
                            prev_24_l = min(m5_lows)
                            live_bar = m5_rates[-1]
                            l_open = live_bar['open']
                            l_high = live_bar['high']
                            l_low = live_bar['low']
                            l_close = live_bar['close']
                            c_range = max(l_high - l_low, pt)

                            # Bullish M5 Sweep: Low swept 2h low, rebounded & close >= open
                            if macro['is_bull'] and (l_low < prev_24_l) and (mid > prev_24_l) and (l_close >= l_open):
                                lower_wick = min(l_open, l_close) - l_low
                                if lower_wick / c_range >= 0.30:
                                    sl = l_low - (spread_pts * pt) - (5 * pt)
                                    tp = mid + abs(mid - sl) * 2.0
                                    if abs(mid - sl) / pt >= 10:
                                        candidates.append(CandidateSetup(
                                            symbol=sym,
                                            setup_type="M5_SNIPER_SWEEP",
                                            direction=1,
                                            trigger_price=ask,
                                            timeframe="M5",
                                            macro_compass=macro['trend_label'],
                                            dealing_range_pos=macro['dealing_range_pos'],
                                            rejection_wick_ratio=round(lower_wick / c_range, 2),
                                            current_spread_pts=spread_pts,
                                            current_atr_pts=atr_pts,
                                            key_support=prev_24_l,
                                            key_resistance=prev_24_h,
                                            suggested_sl=round(sl, 5 if pt < 0.01 else 2),
                                            suggested_tp=round(tp, 5 if pt < 0.01 else 2),
                                            risk_reward_ratio=2.0,
                                            strong_low=macro.get('strong_low', 0.0),
                                            strong_high=macro.get('strong_high', 0.0),
                                            bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                            bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                            fvg_zone=macro.get('fvg_zone', ""),
                                            liquidity_pools=macro.get('liquidity_pools', ""),
                                            timestamp_wib=now.strftime("%H:%M:%S WIB")
                                        ))
                                        continue

                            # Bearish M5 Sweep: High swept 2h high, rebounded down & close <= open
                            if macro['is_bear'] and (l_high > prev_24_h) and (mid < prev_24_h) and (l_close <= l_open):
                                upper_wick = l_high - max(l_open, l_close)
                                if upper_wick / c_range >= 0.30:
                                    sl = l_high + (spread_pts * pt) + (5 * pt)
                                    tp = mid - abs(sl - mid) * 2.0
                                    if abs(mid - sl) / pt >= 10:
                                        candidates.append(CandidateSetup(
                                            symbol=sym,
                                            setup_type="M5_SNIPER_SWEEP",
                                            direction=-1,
                                            trigger_price=bid,
                                            timeframe="M5",
                                            macro_compass=macro['trend_label'],
                                            dealing_range_pos=macro['dealing_range_pos'],
                                            rejection_wick_ratio=round(upper_wick / c_range, 2),
                                            current_spread_pts=spread_pts,
                                            current_atr_pts=atr_pts,
                                            key_support=prev_24_l,
                                            key_resistance=prev_24_h,
                                            suggested_sl=round(sl, 5 if pt < 0.01 else 2),
                                            suggested_tp=round(tp, 5 if pt < 0.01 else 2),
                                            risk_reward_ratio=2.0,
                                            strong_low=macro.get('strong_low', 0.0),
                                            strong_high=macro.get('strong_high', 0.0),
                                            bullish_ob_zone=macro.get('bullish_ob_zone', ""),
                                            bearish_ob_zone=macro.get('bearish_ob_zone', ""),
                                            fvg_zone=macro.get('fvg_zone', ""),
                                            liquidity_pools=macro.get('liquidity_pools', ""),
                                            timestamp_wib=now.strftime("%H:%M:%S WIB")
                                        ))
                                        continue
                    except Exception as e_m5:
                        logger.debug(f"M5 sweep check error on {sym}: {e_m5}")

            except Exception as e:
                logger.debug(f"Radar check error on {sym}: {e}")

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

        lines.append(f"🟢 *Bullish Compass:* {', '.join(bull_pairs[:6]) if bull_pairs else '-'}")
        lines.append(f"🔴 *Bearish Compass:* {', '.join(bear_pairs[:6]) if bear_pairs else '-'}")
        lines.append(f"⚪ *Sideways Range:* {', '.join(range_pairs[:6]) if range_pairs else '-'}")
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
            lines.append("📡 *Fast Radar:* 22 Pasang dipantau, 0 sinyal terpicu saat ini.")

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
