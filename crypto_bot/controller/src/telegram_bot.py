"""
telegram_bot.py — Unified Telegram Interactive Controller for Crypto Engines.
Provides commands:
  - /crypto   : Portfolio health & daily P/L status
  - /btc      : btc_perp positions & whale positioning bias
  - /sol      : sol_dex active tokens & whitelist status
  - /whale    : List top tracked whales
  - /killall  : EMERGENCY HALT (Close all & lock risk pool)
  - /unlock   : Unlock circuit breaker
"""

import time
import logging
import requests
from typing import Optional

try:
    from crypto_bot.controller import config
    from crypto_bot.controller.src.risk_pool import SharedRiskPool
except ImportError:
    import config
    from src.risk_pool import SharedRiskPool

logger = logging.getLogger("crypto_controller.telegram")


class CryptoTelegramController:
    """Telegram Bot Controller with Emergency Circuit Breaker Commands."""

    def __init__(self, risk_pool: Optional[SharedRiskPool] = None):
        self.token = config.CRYPTO_TELEGRAM_TOKEN
        self.chat_id = config.CRYPTO_TELEGRAM_CHAT_ID
        self.risk_pool = risk_pool or SharedRiskPool()
        self.api_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""

    def send_message(self, text: str) -> bool:
        """Sends an HTML formatted message to the configured Telegram chat."""
        if not self.token or not self.chat_id:
            logger.info(f"[TELEGRAM LOG (Simulated)]:\n{text}")
            return True

        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            res = requests.post(url, json=payload, timeout=5)
            return res.status_code == 200
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False

    def handle_command(self, command: str) -> str:
        """Processes text command and returns reply string."""
        cmd = command.strip().lower()

        if cmd in ("/crypto", "/status"):
            summary = self.risk_pool.get_summary()
            lock_str = "🔒 LOCKED" if summary["locked"] else "🟢 ACTIVE"
            return (
                f"📊 <b>CRYPTO PORTFOLIO DASHBOARD</b>\n"
                f"Status: {lock_str}\n"
                f"Date: {summary['date']}\n"
                f"Start Equity: ${summary['start_equity']:,.2f}\n"
                f"Realized PnL: ${summary['realized_pnl_usd']:+,.2f} ({summary['realized_pnl_percent']:+.2f}%)\n"
                f"BTC Breakdown: ${summary['worker_breakdown'].get('BTC', 0.0):+,.2f}\n"
                f"SOL Breakdown: ${summary['worker_breakdown'].get('SOL', 0.0):+,.2f}\n"
            )

        elif cmd == "/btc":
            return (
                f"📈 <b>BTC PERP ENGINE STATUS</b>\n"
                f"Mode: {'DRY_RUN' if getattr(config, 'BTC_DRY_RUN', True) else 'ACTIVE'}\n"
                f"Leverage Cap: 2x\n"
                f"Funding Rate Filter: Active (±0.05% threshold)\n"
                f"Jury Model: 3-LLM Unanimous Consensus\n"
            )

        elif cmd == "/sol":
            return (
                f"⚡ <b>SOLANA DEX ENGINE STATUS</b>\n"
                f"Execution: Jupiter V6 Priority Swap\n"
                f"Anti-Rugpull Gate: Active (<500ms, 0 LLM)\n"
                f"Position Cap: $10 USD per trade\n"
                f"Exit Strategy: +100% TP1 (50% lot) | -50% Hard SL\n"
            )

        elif cmd == "/killall":
            self.risk_pool.lock("Manual /killall triggered from Telegram")
            return "🚨 <b>EMERGENCY HALT TRIGGERED</b>\nRisk pool locked. All trading halted."

        elif cmd == "/unlock":
            self.risk_pool.unlock()
            return "🟢 <b>RISK POOL UNLOCKED</b>\nTrading is now re-enabled."

        elif cmd in ("/help", "/start"):
            return (
                "🤖 <b>CRYPTO BOT CONTROLLER COMMANDS</b>\n\n"
                "/crypto — Dashboard equity & daily P/L\n"
                "/btc    — BTC Perpetual engine status\n"
                "/sol    — Solana DEX engine status\n"
                "/killall — Emergency close & lock system\n"
                "/unlock — Re-enable trading\n"
            )

        return "Unknown command. Send /help for command list."
