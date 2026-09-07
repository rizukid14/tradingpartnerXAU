"""
whale_tracker.py — Hyperliquid Top Traders & Whale Sentiment Tracker.
Monitors top PnL accounts on Hyperliquid L1, computes Net Long/Short Positioning Bias,
and generates whale positioning context for the 3-LLM Jury.
"""

import time
import logging
import requests
from typing import Dict, Any, List

logger = logging.getLogger("btc_perp.whale_tracker")

HL_INFO_URL = "https://api.hyperliquid.xyz/info"


class WhaleTracker:
    """Tracks top institutional & whale traders on Hyperliquid."""

    def __init__(self, cache_ttl_sec: int = 120):
        self.cache_ttl_sec = cache_ttl_sec
        self._cached_bias: Optional[Dict[str, Any]] = None
        self._last_fetch_time: float = 0.0

    def get_whale_positioning(self, coin: str = "BTC") -> Dict[str, Any]:
        """Fetches top traders' positioning and computes Net Directional Bias."""
        now = time.time()
        if self._cached_bias and (now - self._last_fetch_time < self.cache_ttl_sec):
            return self._cached_bias

        try:
            # Query leaderboard top performers
            payload = {"type": "leaderboard", "req": {"limit": 50}}
            res = requests.post(HL_INFO_URL, json=payload, timeout=6)
            
            if res.status_code == 200:
                data = res.json()
                leaderboard_rows = data.get("rows", [])
                
                long_count = 0
                short_count = 0
                neutral_count = 0
                total_evaluated = 0

                # Sample top 20 traders with active positions
                for row in leaderboard_rows[:25]:
                    user_addr = row.get("ethAddress")
                    if not user_addr:
                        continue

                    # Fetch user's clearinghouse state
                    pos_payload = {"type": "clearinghouseState", "user": user_addr}
                    pos_res = requests.post(HL_INFO_URL, json=pos_payload, timeout=4)
                    if pos_res.status_code == 200:
                        user_state = pos_res.json()
                        asset_positions = user_state.get("assetPositions", [])
                        user_btc_size = 0.0
                        for ap in asset_positions:
                            p = ap.get("position", {})
                            if p.get("coin") == coin:
                                user_btc_size += float(p.get("szi", 0.0))

                        if user_btc_size > 0.001:
                            long_count += 1
                            total_evaluated += 1
                        elif user_btc_size < -0.001:
                            short_count += 1
                            total_evaluated += 1
                        else:
                            neutral_count += 1

                if total_evaluated > 0:
                    long_ratio = long_count / total_evaluated
                    short_ratio = short_count / total_evaluated

                    if long_ratio >= 0.60:
                        bias = "LONG_BIASED"
                    elif short_ratio >= 0.60:
                        bias = "SHORT_BIASED"
                    else:
                        bias = "NEUTRAL"

                    result = {
                        "coin": coin,
                        "net_whale_bias": bias,
                        "long_ratio": round(long_ratio, 3),
                        "short_ratio": round(short_ratio, 3),
                        "traders_tracked": total_evaluated,
                        "long_count": long_count,
                        "short_count": short_count,
                        "timestamp": now,
                    }
                    self._cached_bias = result
                    self._last_fetch_time = now
                    logger.info(f"Whale bias updated: {bias} (Long: {long_ratio:.1%}, Short: {short_ratio:.1%})")
                    return result
        except Exception as e:
            logger.warning(f"Failed to fetch live Hyperliquid whale leaderboard: {e}. Using baseline neutral bias.")

        # Fallback baseline bias
        fallback = {
            "coin": coin,
            "net_whale_bias": "NEUTRAL",
            "long_ratio": 0.50,
            "short_ratio": 0.50,
            "traders_tracked": 0,
            "long_count": 0,
            "short_count": 0,
            "timestamp": now,
        }
        self._cached_bias = fallback
        self._last_fetch_time = now
        return fallback

    def format_for_prompt(self, coin: str = "BTC") -> str:
        """Formats whale sentiment data as a clean block for the LLM prompt."""
        data = self.get_whale_positioning(coin)
        return (
            f"WHALE POSITIONING MATRIX (Hyperliquid Top PnL Traders):\n"
            f"- Net Bias: {data['net_whale_bias']}\n"
            f"- Long Ratio: {data['long_ratio']*100:.1f}%\n"
            f"- Short Ratio: {data['short_ratio']*100:.1f}%\n"
            f"- Tracked Active Whales: {data['traders_tracked']}\n"
        )
