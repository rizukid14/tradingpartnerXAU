"""
position_manager.py — Real-time Position Protection, BEP, Dynamic Trailing & Stagnation Exit.
Operates on a 5-second cadence. Monitors floating P/L, peak MFE, and automatically shields capital.
"""

import time
import logging
import requests
from typing import Dict, Any, List, Optional

try:
    from crypto_bot.btc_perp import config
except ImportError:
    import config

logger = logging.getLogger("btc_perp.position_manager")


class BTCPositionManager:
    """Manages active BTC Perpetual positions with BEP, Trailing, and Stagnation Exit."""

    def __init__(self, exchange_router):
        self.router = exchange_router
        self.bep_ratio = config.BEP_TRIGGER_RATIO
        self.trailing_s1 = config.TRAILING_STAGE1_RATIO
        self.trailing_s2 = config.TRAILING_STAGE2_RATIO
        self.stagnation_hours = config.STAGNATION_TIMEOUT_HOURS

        # Track internal position metadata: { order_id/coin: { peak_price, entry_time, bep_done, trailing_stage } }
        self._pos_meta: Dict[str, Dict[str, Any]] = {}

    def _notify_controller(self, event_type: str, details: Dict[str, Any]) -> None:
        """Dispatches position event to Unified Controller."""
        try:
            payload = {
                "worker": "BTC",
                "type": event_type,
                "timestamp": time.time(),
                "details": details,
            }
            requests.post(config.CONTROLLER_WEBHOOK, json=payload, timeout=2)
        except Exception:
            pass

    def manage_positions(self, atr_h1: float = 800.0) -> None:
        """Evaluates active positions and adjusts SL/TP or closes stagnant trades."""
        positions = self.router.get_positions()
        if not positions:
            return

        mkt = self.router.get_market_data(config.BTC_SYMBOL)
        current_price = mkt.get("mid_price", 0.0)
        if current_price <= 0.0:
            return

        now = time.time()

        for pos in positions:
            coin = pos.get("coin", config.BTC_SYMBOL)
            side = pos.get("side", "BUY")
            entry_px = float(pos.get("entry_price", current_price))
            sl_px = float(pos.get("sl_price") or 0.0)
            tp_px = float(pos.get("tp_price") or 0.0)
            size = float(pos.get("size", 0.0))

            meta = self._pos_meta.setdefault(coin, {
                "peak_price": current_price,
                "entry_time": now,
                "bep_applied": False,
                "trailing_stage": 0,
            })

            # Track peak price
            if side == "BUY":
                meta["peak_price"] = max(meta["peak_price"], current_price)
                floating_gain = current_price - entry_px
                tp_dist = tp_px - entry_px if tp_px > entry_px else atr_h1 * 2.0
            else:
                meta["peak_price"] = min(meta["peak_price"], current_price)
                floating_gain = entry_px - current_price
                tp_dist = entry_px - tp_px if tp_px < entry_px else atr_h1 * 2.0

            progress_ratio = floating_gain / tp_dist if tp_dist > 0 else 0.0

            # 1. Break-Even Protection (BEP at 50% TP)
            if progress_ratio >= self.bep_ratio and not meta["bep_applied"]:
                fee_buffer = 15.0  # $15 buffer to cover round-trip taker fees
                new_sl = entry_px + fee_buffer if side == "BUY" else entry_px - fee_buffer
                pos["sl_price"] = new_sl
                meta["bep_applied"] = True
                logger.info(f"[BEP ACTIVATED] Moved SL to ${new_sl:,.2f} for {side} {coin} (Profit: ${floating_gain:,.2f})")
                self._notify_controller("BEP_ACTIVATED", {"coin": coin, "new_sl": new_sl, "price": current_price})

            # 2. Dynamic Trailing Stop
            # Stage 2 (Terminal Lock >= 90% TP): Trail at 0.50x ATR
            if progress_ratio >= self.trailing_s2:
                trail_buffer = atr_h1 * 0.50
                target_sl = meta["peak_price"] - trail_buffer if side == "BUY" else meta["peak_price"] + trail_buffer
                if (side == "BUY" and target_sl > sl_px) or (side == "SELL" and target_sl < sl_px):
                    pos["sl_price"] = target_sl
                    meta["trailing_stage"] = 2
                    logger.info(f"[TRAILING S2] Tightened SL to ${target_sl:,.2f} for {side} {coin}")

            # Stage 1 (Breathing Trail 65% - 90% TP): Trail at 0.75x ATR
            elif progress_ratio >= self.trailing_s1 and meta["trailing_stage"] < 2:
                trail_buffer = atr_h1 * 0.75
                target_sl = meta["peak_price"] - trail_buffer if side == "BUY" else meta["peak_price"] + trail_buffer
                if (side == "BUY" and target_sl > sl_px) or (side == "SELL" and target_sl < sl_px):
                    pos["sl_price"] = target_sl
                    meta["trailing_stage"] = 1
                    logger.info(f"[TRAILING S1] Adjusted SL to ${target_sl:,.2f} for {side} {coin}")

            # 3. Peak-Aware Stagnation Exit
            hold_hours = (now - meta["entry_time"]) / 3600.0
            if hold_hours >= self.stagnation_hours:
                # If progress is small (-0.2R to +0.2R) and peak was weak (< 0.3R)
                if abs(progress_ratio) < 0.20:
                    logger.warning(
                        f"[STAGNATION EXIT] Position {coin} open for {hold_hours:.1f}h with flat momentum. Closing position."
                    )
                    self.router.close_position(coin)
                    self._pos_meta.pop(coin, None)
                    self._notify_controller("STAGNATION_CLOSE", {"coin": coin, "hold_hours": hold_hours})
                    continue

            # 4. Check SL / TP Hits in DRY_RUN
            if config.BTC_DRY_RUN:
                hit_sl = (side == "BUY" and current_price <= sl_px) or (side == "SELL" and current_price >= sl_px)
                hit_tp = tp_px > 0 and ((side == "BUY" and current_price >= tp_px) or (side == "SELL" and current_price <= tp_px))

                if hit_sl or hit_tp:
                    reason = "TAKE_PROFIT" if hit_tp else "STOP_LOSS"
                    pnl = floating_gain * abs(size)
                    logger.info(f"[SIMULATED EXIT] {coin} hit {reason} @ ${current_price:,.2f} | PnL: ${pnl:,.2f}")
                    self.router.close_position(coin)
                    self._pos_meta.pop(coin, None)
                    self._notify_controller("POSITION_CLOSED", {"coin": coin, "reason": reason, "pnl": pnl})
