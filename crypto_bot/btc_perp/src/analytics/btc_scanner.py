"""
btc_scanner.py — Stage 1 Fast Execution Radar for BTC Perpetual (0 LLM Tokens).
Implements 3 quantitative mechanisms:
  - M1: BTC Universal Liquidity Sweep (PDH/PDL false break + structural reclaim)
  - M2: Trend-Aligned Pullback to Discount/Premium Equilibrium
  - M3: Open Interest & Volume Profile Accumulation Compression
"""

import time
import logging
import numpy as np
from typing import Dict, List, Any, Tuple

try:
    from crypto_bot.btc_perp import config
except ImportError:
    import config

logger = logging.getLogger("btc_perp.scanner")


class BTCScanner:
    """Stage 1 Quantitative Radar for BTC Perpetual."""

    def __init__(self, exchange_router):
        self.router = exchange_router

    def calculate_atr(self, candles: List[Dict[str, float]], period: int = 14) -> float:
        """Calculates 14-period Average True Range (ATR)."""
        if len(candles) < period + 1:
            return 800.0  # Default BTC ATR fallback

        trs = []
        for i in range(1, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)

        if not trs:
            return 800.0
        return float(np.mean(trs[-period:]))

    def calculate_ema(self, prices: List[float], period: int) -> float:
        """Calculates Exponential Moving Average."""
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        weights = np.exp(np.linspace(-1.0, 0.0, period))
        weights /= weights.sum()
        return float(np.dot(prices[-period:], weights))

    def scan(self) -> Dict[str, Any]:
        """
        Executes radar scan across M1, M2, and M3 mechanisms on H1 candles.
        Returns setup dictionary.
        """
        candles = self.router.get_candles(config.BTC_SYMBOL, interval="1h", limit=60)
        mkt = self.router.get_market_data(config.BTC_SYMBOL)
        current_price = mkt.get("mid_price", 60000.0)

        if len(candles) < 25:
            return {
                "symbol": config.BTC_SYMBOL,
                "direction": "HOLD",
                "mechanism": "NONE",
                "score": 0.0,
                "atr_h1": 800.0,
                "reason": "Insufficient candle data",
            }

        atr = self.calculate_atr(candles, period=14)
        closes = [c["close"] for c in candles]
        ema21 = self.calculate_ema(closes, 21)
        ema50 = self.calculate_ema(closes, 50)

        # 1. Mechanism 1: Universal Liquidity Sweep (PDH/PDL false break + reclaim)
        m1_setup = self._check_universal_liquidity_sweep(candles, current_price, atr)
        if m1_setup["direction"] != "HOLD":
            m1_setup["atr_h1"] = atr
            return m1_setup

        # 2. Mechanism 2: Trend-Aligned Pullback
        m2_setup = self._check_trend_pullback(candles, ema21, ema50, current_price, atr)
        if m2_setup["direction"] != "HOLD":
            m2_setup["atr_h1"] = atr
            return m2_setup

        # 3. Mechanism 3: OI Accumulation Compression
        m3_setup = self._check_oi_compression(candles, mkt, atr)
        if m3_setup["direction"] != "HOLD":
            m3_setup["atr_h1"] = atr
            return m3_setup

        return {
            "symbol": config.BTC_SYMBOL,
            "direction": "HOLD",
            "mechanism": "NONE",
            "score": 40.0,
            "atr_h1": atr,
            "reason": "No high-probability quant setup detected",
        }

    def _check_universal_liquidity_sweep(
        self,
        candles: List[Dict[str, float]],
        current_price: float,
        atr: float,
    ) -> Dict[str, Any]:
        """
        Detects Universal Liquidity Sweep:
        - Price spikes above Previous Day High (PDH) or 24-bar high then closes back below -> SELL
        - Price spikes below Previous Day Low (PDL) or 24-bar low then closes back above -> BUY
        """
        # Look back 24 bars (approx 1 day on H1)
        lookback = candles[-25:-1]
        pdh = max(c["high"] for c in lookback)
        pdl = min(c["low"] for c in lookback)

        last_candle = candles[-1]
        c_open = last_candle["open"]
        c_high = last_candle["high"]
        c_low = last_candle["low"]
        c_close = last_candle["close"]

        # Bullish Universal Sweep: low pierced PDL, but close reclaimed above PDL
        if c_low < pdl and c_close > pdl and (c_close - c_low) >= 0.25 * atr:
            return {
                "symbol": config.BTC_SYMBOL,
                "direction": "BUY",
                "mechanism": "M1_UNIVERSAL_LIQUIDITY_SWEEP",
                "score": 88.0,
                "details": {
                    "level_swept": pdl,
                    "reclaim_price": c_close,
                    "sweep_wick": c_close - c_low,
                },
            }

        # Bearish Universal Sweep: high pierced PDH, but close rejected back below PDH
        if c_high > pdh and c_close < pdh and (c_high - c_close) >= 0.25 * atr:
            return {
                "symbol": config.BTC_SYMBOL,
                "direction": "SELL",
                "mechanism": "M1_UNIVERSAL_LIQUIDITY_SWEEP",
                "score": 88.0,
                "details": {
                    "level_swept": pdh,
                    "reclaim_price": c_close,
                    "sweep_wick": c_high - c_close,
                },
            }

        return {"direction": "HOLD", "mechanism": "NONE", "score": 0.0}

    def _check_trend_pullback(
        self,
        candles: List[Dict[str, float]],
        ema21: float,
        ema50: float,
        current_price: float,
        atr: float,
    ) -> Dict[str, Any]:
        """Detects trend pullback into EMA21/EMA50 value area."""
        last_candle = candles[-1]
        c_close = last_candle["close"]
        c_low = last_candle["low"]
        c_high = last_candle["high"]

        # Uptrend condition
        if ema21 > ema50 + (0.1 * atr):
            # Pullback to EMA21 with rejection wick
            if c_low <= ema21 and c_close >= ema21:
                return {
                    "symbol": config.BTC_SYMBOL,
                    "direction": "BUY",
                    "mechanism": "M2_TREND_PULLBACK",
                    "score": 78.0,
                    "details": {"trend": "BULLISH", "ema21": ema21, "ema50": ema50},
                }

        # Downtrend condition
        if ema21 < ema50 - (0.1 * atr):
            # Pullback up to EMA21 with rejection wick
            if c_high >= ema21 and c_close <= ema21:
                return {
                    "symbol": config.BTC_SYMBOL,
                    "direction": "SELL",
                    "mechanism": "M2_TREND_PULLBACK",
                    "score": 78.0,
                    "details": {"trend": "BEARISH", "ema21": ema21, "ema50": ema50},
                }

        return {"direction": "HOLD", "mechanism": "NONE", "score": 0.0}

    def _check_oi_compression(
        self,
        candles: List[Dict[str, float]],
        mkt: Dict[str, Any],
        atr: float,
    ) -> Dict[str, Any]:
        """Detects volatility compression when Open Interest is expanding."""
        recent_bars = candles[-6:]  # Last 6 hours
        highest = max(b["high"] for b in recent_bars)
        lowest = min(b["low"] for b in recent_bars)
        compression_range = highest - lowest

        # If range is narrow (< 1.2x ATR) and OI > 10,000 BTC
        if compression_range < 1.2 * atr and mkt.get("open_interest", 0.0) > 10000:
            last_close = candles[-1]["close"]
            mid_range = (highest + lowest) / 2.0
            bias = "BUY" if last_close >= mid_range else "SELL"
            return {
                "symbol": config.BTC_SYMBOL,
                "direction": bias,
                "mechanism": "M3_OI_COMPRESSION",
                "score": 75.0,
                "details": {
                    "range_pts": compression_range,
                    "open_interest": mkt.get("open_interest"),
                },
            }

        return {"direction": "HOLD", "mechanism": "NONE", "score": 0.0}
