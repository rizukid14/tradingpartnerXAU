"""
risk_engine.py — Position Sizing, Leverage Ceiling & Daily Loss Risk Engine for BTC Perp.
Calculates mathematically precise lot sizes based on stop-loss distance and equity.
Enforces leverage caps and synchronizes with controller daily loss limits.
"""

import json
import logging
import requests
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

try:
    from crypto_bot.btc_perp import config
except ImportError:
    import config

logger = logging.getLogger("btc_perp.risk_engine")


class BTCRiskEngine:
    """Institutional Risk Management Engine for BTC Perpetual Trading."""

    def __init__(self):
        self.risk_percent = config.BTC_RISK_PERCENT
        self.leverage = config.BTC_LEVERAGE
        self.max_daily_loss = config.DAILY_LOSS_PERCENT
        self.controller_webhook = config.CONTROLLER_WEBHOOK

    def check_daily_loss_limit(self) -> Tuple[bool, str]:
        """
        Checks if global or local daily loss has exceeded the threshold.
        Returns: (allowed: bool, reason: str)
        """
        # 1. Attempt to query controller risk pool
        try:
            res = requests.get(f"{self.controller_webhook.rsplit('/', 1)[0]}/status", timeout=2)
            if res.status_code == 200:
                data = res.json()
                if data.get("locked", False):
                    return False, f"Controller Risk Pool Locked: {data.get('lock_reason', 'Daily Loss Exceeded')}"
        except Exception:
            pass  # Fallback to local check if controller is not yet running

        # 2. Local state fallback check
        state_file = Path("data/crypto_risk_state.json")
        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    state = json.load(f)
                    if state.get("locked", False):
                        return False, "Local Risk State Locked: Daily Loss Limit Reached"
            except Exception as e:
                logger.warning(f"Error reading local risk state: {e}")

        return True, "Risk limits within threshold"

    def calculate_position_size(
        self,
        equity: float,
        entry_price: float,
        sl_price: float,
    ) -> Tuple[float, float, str]:
        """
        Calculates BTC position size (notional and base coins) based on risk percentage.
        Formula:
          risk_usd = equity * (risk_percent / 100)
          sl_distance = abs(entry_price - sl_price)
          btc_size = risk_usd / sl_distance
          notional_usd = btc_size * entry_price
        
        Returns: (btc_size, notional_usd, error_message)
        """
        if equity <= 0.0:
            return 0.0, 0.0, "Invalid equity"

        sl_distance = abs(entry_price - sl_price)
        if sl_distance <= 0.0:
            return 0.0, 0.0, "SL distance cannot be zero"

        risk_usd = equity * (self.risk_percent / 100.0)
        btc_size = risk_usd / sl_distance

        # Apply Leverage Cap Constraint
        max_notional = equity * self.leverage
        notional_usd = btc_size * entry_price

        if notional_usd > max_notional:
            logger.warning(
                f"Sizing {notional_usd:.2f} exceeds leverage cap {self.leverage}x ({max_notional:.2f}). Capping."
            )
            btc_size = max_notional / entry_price
            notional_usd = max_notional

        # Precision rounding (Hyperliquid/Binance minimum BTC size typically 0.001)
        btc_size = round(btc_size, 4)
        if btc_size < 0.001:
            btc_size = 0.001
            notional_usd = btc_size * entry_price

        return btc_size, notional_usd, ""

    def validate_new_trade(
        self,
        equity: float,
        current_positions: list,
        entry_price: float,
        sl_price: float,
    ) -> Tuple[bool, float, str]:
        """
        Comprehensive pre-trade risk check.
        Returns: (approved: bool, btc_size: float, reason: str)
        """
        # Check active position cap
        if len(current_positions) >= config.MAX_OPEN_POSITIONS:
            return False, 0.0, f"Max open positions reached ({config.MAX_OPEN_POSITIONS})"

        # Check daily loss
        allowed, reason = self.check_daily_loss_limit()
        if not allowed:
            return False, 0.0, reason

        # Calculate sizing
        btc_size, notional_usd, err = self.calculate_position_size(equity, entry_price, sl_price)
        if err:
            return False, 0.0, err

        return True, btc_size, "Trade approved by Risk Engine"
