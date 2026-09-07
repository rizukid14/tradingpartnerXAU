"""
hl_connector.py — Hyperliquid L1 Perpetual Connector.
Handles account queries, order placement, market data, and funding rates.
Provides full DRY_RUN simulation support when real credentials are not supplied or testing is active.
"""

import time
import logging
import requests
from typing import Dict, List, Optional, Any

try:
    from crypto_bot.btc_perp import config
except ImportError:
    import config

logger = logging.getLogger("btc_perp.hl_connector")

MAINNET_API_URL = "https://api.hyperliquid.xyz"
TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"


class HyperliquidConnector:
    """Hyperliquid Perpetual DEX API Connector with DRY_RUN simulation mode."""

    def __init__(
        self,
        private_key: Optional[str] = None,
        wallet_address: Optional[str] = None,
        testnet: bool = False,
        dry_run: bool = True,
    ):
        self.private_key = private_key or config.HL_PRIVATE_KEY
        self.wallet_address = wallet_address or config.HL_WALLET_ADDRESS
        self.testnet = testnet if testnet is not None else config.HL_TESTNET
        self.dry_run = dry_run if dry_run is not None else config.BTC_DRY_RUN
        self.base_url = TESTNET_API_URL if self.testnet else MAINNET_API_URL
        
        # Internal paper portfolio for DRY_RUN mode
        self._paper_equity: float = 1000.0  # Default $1,000 virtual USDC
        self._paper_positions: Dict[str, Dict[str, Any]] = {}

        self._init_sdk()

    def _init_sdk(self) -> None:
        """Initializes hyperliquid Python SDK if available and private key is present."""
        self.exchange = None
        self.info = None
        
        try:
            from hyperliquid.info import Info
            from hyperliquid.utils import constants
            
            base_url = constants.TESTNET_API_URL if self.testnet else constants.MAINNET_API_URL
            self.info = Info(base_url, skip_ws=True)
            
            if self.private_key and not self.dry_run:
                import eth_account
                from hyperliquid.exchange import Exchange
                account = eth_account.Account.from_key(self.private_key)
                self.exchange = Exchange(account, base_url)
                logger.info(f"Hyperliquid SDK initialized for account: {account.address}")
            else:
                logger.info("Hyperliquid running in Read-Only / DRY_RUN mode.")
        except Exception as e:
            logger.warning(f"Hyperliquid SDK init notice (using direct REST fallback): {e}")

    def get_equity(self) -> float:
        """Fetches total account equity in USDC. Falls back to paper equity in DRY_RUN."""
        if self.dry_run or not self.wallet_address:
            return self._paper_equity

        try:
            url = f"{self.base_url}/info"
            payload = {"type": "clearinghouseState", "user": self.wallet_address}
            res = requests.post(url, json=payload, timeout=5)
            if res.status_code == 200:
                data = res.json()
                margin_summary = data.get("marginSummary", {})
                account_value = float(margin_summary.get("accountValue", 0.0))
                return account_value
        except Exception as e:
            logger.error(f"Error fetching Hyperliquid equity: {e}")
            
        return self._paper_equity

    def get_market_data(self, coin: str = "BTC") -> Dict[str, Any]:
        """Fetches live mid price, mark price, funding rate, and open interest."""
        try:
            url = f"{self.base_url}/info"
            payload = {"type": "metaAndAssetCtxs"}
            res = requests.post(url, json=payload, timeout=5)
            if res.status_code == 200:
                meta, asset_ctxs = res.json()
                universe = meta.get("universe", [])
                for idx, asset in enumerate(universe):
                    if asset.get("name") == coin:
                        ctx = asset_ctxs[idx]
                        mid_px = float(ctx.get("midPx", 0.0))
                        mark_px = float(ctx.get("markPx", mid_px))
                        funding = float(ctx.get("funding", 0.0))
                        open_interest = float(ctx.get("openInterest", 0.0))
                        day_ntnl_vol = float(ctx.get("dayNtnlVlm", 0.0))
                        return {
                            "coin": coin,
                            "mid_price": mid_px,
                            "mark_price": mark_px,
                            "funding_rate": funding,  # Hourly or 8h funding
                            "open_interest": open_interest,
                            "day_volume_usd": day_ntnl_vol,
                            "timestamp": time.time(),
                        }
        except Exception as e:
            logger.error(f"Error fetching market data for {coin}: {e}")

        # Fallback simulation market price for BTC if offline
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
        """Fetches OHLCV candlestick data from Hyperliquid info endpoint."""
        now_ms = int(time.time() * 1000)
        # interval mapping to ms
        interval_ms_map = {
            "1m": 60 * 1000,
            "5m": 5 * 60 * 1000,
            "15m": 15 * 60 * 1000,
            "1h": 60 * 60 * 1000,
            "4h": 4 * 60 * 60 * 1000,
            "1d": 24 * 60 * 60 * 1000,
        }
        step_ms = interval_ms_map.get(interval, 60 * 60 * 1000)
        start_time = now_ms - (limit * step_ms)

        try:
            url = f"{self.base_url}/info"
            payload = {
                "type": "candleSnapshot",
                "req": {
                    "coin": coin,
                    "interval": interval,
                    "startTime": start_time,
                    "endTime": now_ms,
                },
            }
            res = requests.post(url, json=payload, timeout=8)
            if res.status_code == 200:
                raw_candles = res.json()
                candles = []
                for c in raw_candles:
                    candles.append({
                        "time": c.get("t") / 1000.0,
                        "open": float(c.get("o")),
                        "high": float(c.get("h")),
                        "low": float(c.get("l")),
                        "close": float(c.get("c")),
                        "volume": float(c.get("v")),
                    })
                return candles
        except Exception as e:
            logger.error(f"Error fetching candles for {coin} ({interval}): {e}")

        return []

    def get_positions(self) -> List[Dict[str, Any]]:
        """Returns list of open positions."""
        if self.dry_run or not self.wallet_address:
            return list(self._paper_positions.values())

        try:
            url = f"{self.base_url}/info"
            payload = {"type": "clearinghouseState", "user": self.wallet_address}
            res = requests.post(url, json=payload, timeout=5)
            if res.status_code == 200:
                data = res.json()
                asset_positions = data.get("assetPositions", [])
                positions = []
                for pos_item in asset_positions:
                    p = pos_item.get("position", {})
                    coin = p.get("coin")
                    size = float(p.get("szi", 0.0))
                    if abs(size) > 0.0:
                        positions.append({
                            "coin": coin,
                            "size": size,
                            "side": "BUY" if size > 0 else "SELL",
                            "entry_price": float(p.get("entryPx", 0.0)),
                            "unrealized_pnl": float(p.get("unrealizedPnl", 0.0)),
                            "leverage": float(p.get("leverage", {}).get("value", 1.0)),
                            "liquidation_price": float(p.get("liquidationPx") or 0.0),
                        })
                return positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")

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
        """Places a Perpetual Order with optional SL/TP parameters."""
        mkt = self.get_market_data(coin)
        current_price = mkt["mid_price"]
        fill_price = px if (px and not is_market) else current_price

        if self.dry_run:
            order_id = f"SIM-HL-{int(time.time() * 1000)}"
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
                "exchange": "hyperliquid_sim",
            }
            self._paper_positions[coin] = sim_pos
            logger.info(
                f"[DRY_RUN] Hyperliquid Order Simulated: {sim_pos['side']} {sz} {coin} @ ${fill_price:,.2f} | "
                f"SL: ${sl_px or 0:,.2f} | TP: ${tp_px or 0:,.2f}"
            )
            return {"status": "ok", "order_id": order_id, "filled": True, "price": fill_price, "size": sz}

        # Real Execution using SDK
        if self.exchange:
            try:
                res = self.exchange.market_open(coin, is_buy, sz, px=fill_price)
                logger.info(f"Hyperliquid Real Order Sent: {res}")
                return {"status": "ok", "raw": res}
            except Exception as e:
                logger.error(f"Hyperliquid execution failed: {e}")
                return {"status": "error", "message": str(e)}

        return {"status": "error", "message": "No exchange instance configured"}

    def close_position(self, coin: str) -> Dict[str, Any]:
        """Closes any active position for coin."""
        if self.dry_run:
            if coin in self._paper_positions:
                closed = self._paper_positions.pop(coin)
                logger.info(f"[DRY_RUN] Hyperliquid Closed Position for {coin}: Entry @ ${closed['entry_price']:,.2f}")
                return {"status": "ok", "closed": closed}
            return {"status": "noop", "message": f"No active dry-run position for {coin}"}

        if self.exchange:
            try:
                res = self.exchange.market_close(coin)
                logger.info(f"Hyperliquid Position Closed: {res}")
                return {"status": "ok", "raw": res}
            except Exception as e:
                logger.error(f"Hyperliquid market close failed: {e}")
                return {"status": "error", "message": str(e)}

        return {"status": "error", "message": "No active position or exchange connection"}
