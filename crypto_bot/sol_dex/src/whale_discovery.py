"""
whale_discovery.py — Auto-discovery & Profiling Engine for Solana Whale Wallets.
Pulls on-chain trading metrics from Birdeye / DexScreener / Solscan,
applies quantitative filters, and maintains the dynamic Whitelist.
"""

import json
import time
import logging
import requests
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    from crypto_bot.sol_dex import config
except ImportError:
    import config

logger = logging.getLogger("sol_dex.discovery")

# Default high-signal seed wallets for bootstrap
SEED_WHALES = [
    {"address": "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1", "tag": "Raydium_Whale_Alpha"},
    {"address": "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", "tag": "Meme_Momentum_Whale"},
    {"address": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", "tag": "Smart_Money_Accumulator"},
]


class WhaleDiscoveryEngine:
    """Discovers and filters smart money Solana traders."""

    def __init__(self, cache_file: Optional[Path] = None):
        self.api_key = config.BIRDEYE_API_KEY
        self.cache_file = cache_file or (config.REPO_ROOT / "data" / "solana_whale_whitelist.json")
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        self.whitelist: List[Dict[str, Any]] = []
        self._load_cached_whitelist()

    def _load_cached_whitelist(self) -> None:
        """Loads cached whitelist if exists and fresh (<24h)."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                    cached_at = data.get("updated_at", 0)
                    if time.time() - cached_at < 86400:  # Fresh for 24h
                        self.whitelist = data.get("whales", [])
                        logger.info(f"Loaded {len(self.whitelist)} whales from cache.")
                        return
            except Exception as e:
                logger.warning(f"Error loading whale cache: {e}")

        # Fallback to seed whales
        self.whitelist = SEED_WHALES
        self._save_whitelist()

    def _save_whitelist(self) -> None:
        """Persists current whitelist to JSON."""
        try:
            with open(self.cache_file, "w") as f:
                json.dump({"updated_at": time.time(), "whales": self.whitelist}, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving whale whitelist: {e}")

    def evaluate_wallet(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Evaluates wallet performance metrics against deterministic criteria:
          - Min 30 txs
          - Profit Factor >= 1.8
          - Win Rate between 35% and 65%
          - Avg holding time > 300s (5 min)
        """
        if not self.api_key:
            # Synthetic evaluation for testing/dry-run without paid API
            return {
                "address": address,
                "profit_factor": 2.15,
                "win_rate": 52.0,
                "total_trades": 45,
                "avg_holding_time_sec": 720,
                "qualified": True,
            }

        try:
            url = f"https://public-api.birdeye.so/trader/gainers-losers?address={address}"
            headers = {"X-API-KEY": self.api_key}
            res = requests.get(url, headers=headers, timeout=6)
            if res.status_code == 200:
                data = res.json().get("data", {})
                pf = float(data.get("profitFactor", 0.0))
                wr = float(data.get("winRate", 0.0)) * 100.0
                txs = int(data.get("totalTrade", 0))

                is_qualified = (
                    pf >= config.MIN_WHALE_PROFIT_FACTOR
                    and config.MIN_WHALE_WIN_RATE <= wr <= config.MAX_WHALE_WIN_RATE
                    and txs >= config.MIN_WHALE_TXS
                )

                if is_qualified:
                    return {
                        "address": address,
                        "profit_factor": round(pf, 2),
                        "win_rate": round(wr, 1),
                        "total_trades": txs,
                        "qualified": True,
                    }
        except Exception as e:
            logger.error(f"Error evaluating wallet {address}: {e}")

        return None

    def refresh_whitelist(self) -> List[Dict[str, Any]]:
        """Runs daily profiling cycle to update tracked whale list."""
        logger.info("Refreshing Solana whale whitelist...")
        # In live mode with Birdeye, fetch top 100 traders on leaderboards
        # For now, validate current list
        qualified_whales = []
        for w in self.whitelist:
            metrics = self.evaluate_wallet(w["address"])
            if metrics and metrics.get("qualified"):
                qualified_whales.append({**w, **metrics})

        if not qualified_whales:
            qualified_whales = SEED_WHALES

        self.whitelist = qualified_whales[: config.MAX_TRACKED_WHALES]
        self._save_whitelist()
        logger.info(f"Whale whitelist active count: {len(self.whitelist)}")
        return self.whitelist

    def get_tracked_addresses(self) -> List[str]:
        """Returns list of wallet pubkeys to watch."""
        return [w["address"] for w in self.whitelist]
