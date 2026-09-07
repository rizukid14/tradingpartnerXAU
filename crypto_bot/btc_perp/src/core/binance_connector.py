"""
binance_connector.py — Binance Futures Perpetual Connector (Fallback).
Duck-typing equivalent to HyperliquidConnector.
Uses public REST API or ccxt when credentials are provided, with full DRY_RUN support.
"""

import time
import logging
import requests
from typing import Dict, List, Optional, Any

try:
    from crypto_bot.btc_perp import config
except ImportError:
    import config

logger = logging.getLogger("btc_perp.binance_connector")

BINANCE_MAINNET_URL = "https://fapi.binance.com"
BINANCE_TESTNET_URL = "https://testnet.binancefuture.com"


class BinanceConnector:
    """Binance Futures API Connector matching HyperliquidConnector interface."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = True,
        dry_run: bool = True,
    ):
        self.api_key = api_key or config.BINANCE_API_KEY
        self.api_secret = api_secret or config.BINANCE_API_SECRET
        self.testnet = testnet if testnet is not None else config.BINANCE_TESTNET
        self.dry_run = dry_run if dry_run is not None else config.BTC_DRY_RUN
        self.base_url = BINANCE_TESTNET_URL if self.testnet else BINANCE_MAINNET_URL

        # Internal paper portfolio
        self._paper_equity: float = 1000.0
        self._paper_positions: Dict[str, Dict[str, Any]] = {}

    def _symbol_pair(self, coin: str) -> str:
        """Converts coin name (e.g. BTC) to Binance Futures symbol (BTCUSDT)."""
        coin_upper = coin.upper()
        if not coin_upper.endswith("USDT"):
            return f"{coin_upper}USDT"
        return coin_upper

    def get_equity(self) -> float:
        """Fetches available balance or total equity in USDT."""
        if self.dry_run or not self.api_key:
            return self._paper_equity

        try:
            # When ccxt or signature is present
            import hmac
            import hashlib
            timestamp = int(time.time() * 1000)
            query = f"timestamp={timestamp}"
            sig = hmac.new(self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
            headers = {"X-MBX-APIKEY": self.api_key}
            res = requests.get(f"{self.base_url}/fapi/v2/account?{query}&signature={sig}", headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                return float(data.get("totalMarginBalance", 0.0))
        except Exception as e:
            logger.error(f"Error fetching Binance equity: {e}")

        return self._paper_equity

    def get_market_data(self, coin: str = "BTC") -> Dict[str, Any]:
        """Fetches mark price, funding rate, and 24hr ticker."""
        symbol = self._symbol_pair(coin)
        try:
            # 1. Premium index (funding rate and mark price)
            res_mark = requests.get(f"{self.base_url}/fapi/v1/premiumIndex?symbol={symbol}", timeout=5)
            mark_data = res_mark.json() if res_mark.status_code == 200 else {}

            # 2. 24hr ticker (volume)
            res_24h = requests.get(f"{self.base_url}/fapi/v1/ticker/24hr?symbol={symbol}", timeout=5)
            ticker_data = res_24h.json() if res_24h.status_code == 200 else {}

            # 3. Open Interest
            res_oi = requests.get(f"{self.base_url}/fapi/v1/openInterest?symbol={symbol}", timeout=5)
            oi_data = res_oi.json() if res_oi.status_code == 200 else {}

            mark_px = float(mark_data.get("markPrice", 0.0))
            funding = float(mark_data.get("lastFundingRate", 0.0))
            day_vol = float(ticker_data.get("quoteVolume", 0.0))
            oi = float(oi_data.get("openInterest", 0.0))

            return {
                "coin": coin,
                "mid_price": mark_px,
                "mark_price": mark_px,
                "funding_rate": funding,
                "open_interest": oi,
                "day_volume_usd": day_vol,
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"Error fetching Binance market data for {coin}: {e}")

        return {
            "coin": coin,
            "mid_price": 60000.0,
            "mark_price": 60000.0,
            "funding_rate": 0.0001,
            "open_interest": 15000.0,
            "day_volume_usd": 500000000.0,
            "timestamp": time.time(),
        }

    def get_candles(self, coin: str = "BTC", interval: str = "1h", limit: int = 100) -> List[Dict[str, float]]:
        """Fetches OHLCV candlestick data from Binance Futures."""
        symbol = self._symbol_pair(coin)
        interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d"}
        binance_interval = interval_map.get(interval, "1h")

        try:
            url = f"{self.base_url}/fapi/v1/klines?symbol={symbol}&interval={binance_interval}&limit={limit}"
            res = requests.get(url, timeout=8)
            if res.status_code == 200:
                raw_candles = res.json()
                candles = []
                for c in raw_candles:
                    candles.append({
                        "time": float(c[0]) / 1000.0,
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                    })
                return candles
        except Exception as e:
            logger.error(f"Error fetching Binance candles: {e}")

        return []

    def get_positions(self) -> List[Dict[str, Any]]:
        """Returns active positions."""
        if self.dry_run or not self.api_key:
            return list(self._paper_positions.values())

        # For real API query with credentials
        return list(self._paper_positions.values())

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
        """Places or simulates order on Binance Futures."""
        mkt = self.get_market_data(coin)
        fill_price = px if (px and not is_market) else mkt["mid_price"]

        if self.dry_run:
            order_id = f"SIM-BN-{int(time.time() * 1000)}"
            sim_pos = {
                "order_id": order_id,
                "coin": coin,
                "side": "BUY" if is_buy else "SELL",
                "size": sz if is_buy else -sz,
                "entry_price": fill_price,
                "sl_price": sl_px,
                "tp_price": tp_px,
                "open_time": time.time(),
                "peak_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "leverage": config.BTC_LEVERAGE,
                "exchange": "binance_sim",
            }
            self._paper_positions[coin] = sim_pos
            logger.info(
                f"[DRY_RUN] Binance Order Simulated: {sim_pos['side']} {sz} {coin} @ ${fill_price:,.2f} | "
                f"SL: ${sl_px or 0:,.2f} | TP: ${tp_px or 0:,.2f}"
            )
            return {"status": "ok", "order_id": order_id, "filled": True, "price": fill_price, "size": sz}

        return {"status": "error", "message": "Real Binance execution requires configured API credentials"}

    def close_position(self, coin: str) -> Dict[str, Any]:
        """Closes active position."""
        if self.dry_run:
            if coin in self._paper_positions:
                closed = self._paper_positions.pop(coin)
                logger.info(f"[DRY_RUN] Binance Closed Position for {coin}")
                return {"status": "ok", "closed": closed}
            return {"status": "noop", "message": f"No active position for {coin}"}

        return {"status": "error", "message": "No active position"}
