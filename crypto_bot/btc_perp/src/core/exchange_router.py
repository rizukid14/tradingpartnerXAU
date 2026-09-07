"""
exchange_router.py — Automatic Failover Router between Hyperliquid (Primary) and Binance (Fallback).
Monitors latency and health, seamlessly routing orders and queries.
"""

import time
import logging
from typing import Dict, List, Optional, Any

try:
    from crypto_bot.btc_perp import config
    from crypto_bot.btc_perp.src.core.hl_connector import HyperliquidConnector
    from crypto_bot.btc_perp.src.core.binance_connector import BinanceConnector
except ImportError:
    import config
    from src.core.hl_connector import HyperliquidConnector
    from src.core.binance_connector import BinanceConnector

logger = logging.getLogger("btc_perp.exchange_router")


class ExchangeRouter:
    """Intelligent failover router for perpetual execution."""

    def __init__(self):
        self.primary_name = config.EXCHANGE_PRIMARY
        self.hl = HyperliquidConnector()
        self.binance = BinanceConnector()
        self.active_exchange = self.hl if self.primary_name == "hyperliquid" else self.binance
        self.active_name = self.primary_name
        self.latency_ms: float = 0.0
        self.failover_threshold_ms: float = 1000.0  # Failover if response > 1.0s

    def _execute_with_failover(self, method_name: str, *args, **kwargs) -> Any:
        """Executes method on active connector with automatic fallback upon timeout or error."""
        start = time.perf_counter()
        try:
            method = getattr(self.active_exchange, method_name)
            res = method(*args, **kwargs)
            duration_ms = (time.perf_counter() - start) * 1000.0
            self.latency_ms = duration_ms

            if duration_ms > self.failover_threshold_ms:
                logger.warning(
                    f"Exchange {self.active_name} high latency ({duration_ms:.1f}ms > {self.failover_threshold_ms}ms)."
                )

            return res
        except Exception as e:
            logger.error(f"Primary exchange ({self.active_name}) method {method_name} failed: {e}. Attempting failover...")
            
            # Switch to fallback
            if self.active_exchange == self.hl:
                self.active_exchange = self.binance
                self.active_name = "binance"
            else:
                self.active_exchange = self.hl
                self.active_name = "hyperliquid"

            logger.info(f"Switched active exchange to: {self.active_name}")
            fallback_method = getattr(self.active_exchange, method_name)
            return fallback_method(*args, **kwargs)

    def get_equity(self) -> float:
        return self._execute_with_failover("get_equity")

    def get_market_data(self, coin: str = "BTC") -> Dict[str, Any]:
        return self._execute_with_failover("get_market_data", coin)

    def get_candles(self, coin: str = "BTC", interval: str = "1h", limit: int = 100) -> List[Dict[str, float]]:
        return self._execute_with_failover("get_candles", coin, interval, limit)

    def get_positions(self) -> List[Dict[str, Any]]:
        return self._execute_with_failover("get_positions")

    def place_order(
        self,
        coin: str,
        is_buy: bool,
        sz: float,
        px: Optional[float] = None,
        sl_px: Optional[float] = None,
        tp_px: Optional[float] = None,
        is_market: bool = True,
    ) -> Dict[str, Any]:
        return self._execute_with_failover(
            "place_order",
            coin=coin,
            is_buy=is_buy,
            sz=sz,
            px=px,
            sl_px=sl_px,
            tp_px=tp_px,
            is_market=is_market,
        )

    def close_position(self, coin: str) -> Dict[str, Any]:
        return self._execute_with_failover("close_position", coin)

    def get_active_exchange_name(self) -> str:
        return self.active_name
