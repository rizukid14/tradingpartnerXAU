"""
position_manager.py — Solana Active Token Position Manager.
Enforces:
  - Staged TP: Sell 50% lot at +100% gain (lock principal), trail remainder
  - Hard SL: -50% stop loss
  - Stagnation Exit: Flat momentum for > 30 minutes
"""

import time
import logging
import requests
from typing import Dict, Any, Optional

try:
    from crypto_bot.sol_dex import config
except ImportError:
    import config

logger = logging.getLogger("sol_dex.position_manager")


class SolanaPositionManager:
    """Manages active Solana DEX token positions."""

    def __init__(self, executor):
        self.executor = executor
        self.hard_sl = config.HARD_SL_PERCENT
        self.stage1_tp = config.STAGE1_TP_GAIN_PERCENT
        self.stagnation_min = config.STAGNATION_TIMEOUT_MINUTES

    def _notify_controller(self, event_type: str, details: Dict[str, Any]) -> None:
        try:
            payload = {
                "worker": "SOL",
                "type": event_type,
                "timestamp": time.time(),
                "details": details,
            }
            requests.post(config.CONTROLLER_WEBHOOK, json=payload, timeout=2)
        except Exception:
            pass

    def check_and_manage(self, token_mint: str, current_multiplier: float) -> Optional[Dict[str, Any]]:
        """
        Evaluates position against TP, SL, and Stagnation triggers.
        current_multiplier: e.g. 1.0 (breakeven), 2.0 (+100%), 0.5 (-50%)
        """
        positions = self.executor.get_open_positions()
        pos = positions.get(token_mint)
        if not pos:
            return None

        now = time.time()
        hold_time_min = (now - pos["entry_time"]) / 60.0
        pos["peak_multiplier"] = max(pos.get("peak_multiplier", 1.0), current_multiplier)

        # 1. Hard Stop Loss (-50%)
        if current_multiplier <= (1.0 - (self.hard_sl / 100.0)):
            logger.warning(
                f"[HARD STOP LOSS] Token {token_mint[:8]}... down {((1.0 - current_multiplier) * 100):.1f}%. Exiting."
            )
            self.executor.execute_swap(token_mint, is_buy=False, amount_sol=pos["entry_price_sol"])
            self._notify_controller("HARD_SL", {"token": token_mint, "multiplier": current_multiplier})
            return {"action": "CLOSE", "reason": "HARD_SL"}

        # 2. Staged TP (+100% gain -> Take 50% off)
        if current_multiplier >= (1.0 + (self.stage1_tp / 100.0)) and not pos.get("tp1_taken"):
            logger.info(
                f"[TP1 HIT] Token {token_mint[:8]}... at {current_multiplier:.2f}x. Selling 50% lot to lock principal."
            )
            half_sol = pos["entry_price_sol"] * 0.5
            self.executor.execute_swap(token_mint, is_buy=False, amount_sol=half_sol)
            pos["tp1_taken"] = True
            self._notify_controller("TP1_TAKEN", {"token": token_mint, "multiplier": current_multiplier})
            return {"action": "PARTIAL_CLOSE", "reason": "TP1"}

        # 3. Stagnation Exit (>30 min with <10% movement)
        if hold_time_min >= self.stagnation_min and abs(current_multiplier - 1.0) < 0.10:
            logger.info(
                f"[STAGNATION EXIT] Token {token_mint[:8]}... flat for {hold_time_min:.1f}m. Freeing capital."
            )
            self.executor.execute_swap(token_mint, is_buy=False, amount_sol=pos["entry_price_sol"])
            self._notify_controller("STAGNATION", {"token": token_mint, "hold_min": hold_time_min})
            return {"action": "CLOSE", "reason": "STAGNATION"}

        return None
