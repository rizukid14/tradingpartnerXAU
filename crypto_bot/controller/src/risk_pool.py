"""
risk_pool.py — Global Shared Risk Pool & Daily Loss Circuit Breaker.
Tracks cumulative realized and unrealized P/L across both sol_dex and btc_perp engines.
Locks execution automatically if cumulative drawdown exceeds CRYPTO_DAILY_LOSS_PERCENT (5.0%).
"""

import json
import time
import logging
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from pathlib import Path

try:
    from crypto_bot.controller import config
except ImportError:
    import config

logger = logging.getLogger("crypto_controller.risk_pool")


class SharedRiskPool:
    """Aggregates portfolio risk and manages the emergency circuit breaker."""

    def __init__(self, state_file: Optional[Path] = None):
        self.state_file = state_file or config.STATE_FILE
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.max_daily_loss_pct = config.CRYPTO_DAILY_LOSS_PERCENT
        self.state: Dict[str, Any] = self._load_or_init_state()

    def _get_current_date_str(self) -> str:
        """Returns current date in WIB (GMT+7)."""
        return datetime.now(config.TIMEZONE_WIB).strftime("%Y-%m-%d")

    def _load_or_init_state(self) -> Dict[str, Any]:
        """Loads existing state file or initializes a fresh daily state."""
        today = self._get_current_date_str()
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    if data.get("date") == today:
                        return data
            except Exception as e:
                logger.warning(f"Error reading risk state: {e}")

        # Fresh daily state
        init_state = {
            "date": today,
            "start_equity_usd": 1000.0,
            "realized_pnl_usd": 0.0,
            "unrealized_pnl_usd": 0.0,
            "worker_pnl": {"BTC": 0.0, "SOL": 0.0},
            "locked": False,
            "lock_reason": "",
            "last_updated": time.time(),
        }
        self._save_state(init_state)
        return init_state

    def _save_state(self, state: Optional[Dict[str, Any]] = None) -> None:
        """Flushes state to disk."""
        st = state or self.state
        st["last_updated"] = time.time()
        try:
            with open(self.state_file, "w") as f:
                json.dump(st, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save risk state: {e}")

    def is_locked(self) -> Tuple[bool, str]:
        """Returns whether trading is globally locked."""
        return self.state.get("locked", False), self.state.get("lock_reason", "")

    def lock(self, reason: str) -> None:
        """Triggers global trading halt."""
        self.state["locked"] = True
        self.state["lock_reason"] = reason
        self._save_state()
        logger.critical(f"[GLOBAL RISK LOCK TRIGGERED] Reason: {reason}")

    def unlock(self) -> None:
        """Manual reset/unlock."""
        self.state["locked"] = False
        self.state["lock_reason"] = ""
        self._save_state()
        logger.info("[GLOBAL RISK UNLOCKED] Trading manually re-enabled.")

    def record_trade_result(self, worker: str, pnl_usd: float) -> Tuple[bool, str]:
        """
        Records a realized trade outcome.
        Evaluates cumulative loss against the daily limit.
        Returns: (locked_status: bool, message: str)
        """
        self.state["realized_pnl_usd"] += pnl_usd
        worker_dict = self.state.setdefault("worker_pnl", {"BTC": 0.0, "SOL": 0.0})
        worker_dict[worker] = worker_dict.get(worker, 0.0) + pnl_usd

        start_equity = self.state.get("start_equity_usd", 1000.0)
        current_loss_usd = -self.state["realized_pnl_usd"]

        max_allowed_loss_usd = start_equity * (self.max_daily_loss_pct / 100.0)

        if current_loss_usd >= max_allowed_loss_usd:
            reason = (
                f"Cumulative daily loss (${current_loss_usd:,.2f}) exceeded "
                f"{self.max_daily_loss_pct}% limit (${max_allowed_loss_usd:,.2f})"
            )
            self.lock(reason)
            return True, reason

        self._save_state()
        return False, "Trade recorded within acceptable risk limits"

    def get_summary(self) -> Dict[str, Any]:
        """Returns portfolio health summary."""
        start_eq = self.state.get("start_equity_usd", 1000.0)
        realized = self.state.get("realized_pnl_usd", 0.0)
        pnl_pct = (realized / start_eq) * 100.0 if start_eq > 0 else 0.0

        return {
            "date": self.state.get("date"),
            "start_equity": start_eq,
            "realized_pnl_usd": round(realized, 2),
            "realized_pnl_percent": round(pnl_pct, 2),
            "locked": self.state.get("locked", False),
            "lock_reason": self.state.get("lock_reason", ""),
            "worker_breakdown": self.state.get("worker_pnl", {}),
        }
