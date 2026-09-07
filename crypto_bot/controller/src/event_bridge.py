"""
event_bridge.py — FastAPI Webhook Bridge for sol_dex and btc_perp Events.
Receives asynchronous trade events, updates the shared risk pool,
and dispatches real-time Telegram alerts.
"""

import time
import logging
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:
    from crypto_bot.controller.src.risk_pool import SharedRiskPool
except ImportError:
    from src.risk_pool import SharedRiskPool

logger = logging.getLogger("crypto_controller.bridge")


class TradeEventPayload(BaseModel):
    worker: str                     # "BTC" or "SOL"
    type: str                       # "POSITION_OPENED", "POSITION_CLOSED", "BEP_ACTIVATED", "HARD_SL", etc.
    timestamp: float = 0.0
    details: Dict[str, Any] = {}


def create_app(risk_pool: Optional[SharedRiskPool] = None, telegram_notifier=None) -> FastAPI:
    """Factory creating the FastAPI event bridge application."""
    app = FastAPI(title="Crypto Bot Controller Event Bridge")
    pool = risk_pool or SharedRiskPool()

    @app.get("/health")
    def health_check():
        return {"status": "ok", "timestamp": time.time()}

    @app.get("/status")
    def get_status():
        summary = pool.get_summary()
        return summary

    @app.post("/event")
    def receive_event(event: TradeEventPayload):
        logger.info(f"[EVENT RECEIVED] {event.worker} -> {event.type} | Details: {event.details}")

        # Check if trade closed with realized PnL
        if "pnl" in event.details:
            pnl = float(event.details["pnl"])
            locked, msg = pool.record_trade_result(event.worker, pnl)
            if locked and telegram_notifier:
                telegram_notifier(f"🚨 <b>CIRCUIT BREAKER TRIGGERED</b>\n{msg}")

        # Dispatch Telegram notification if notifier is wired
        if telegram_notifier:
            try:
                msg = (
                    f"⚡ <b>[{event.worker} ENGINE] {event.type}</b>\n"
                    f"Details: <code>{event.details}</code>"
                )
                telegram_notifier(msg)
            except Exception as e:
                logger.error(f"Telegram notification dispatch error: {e}")

        return {"status": "ok", "received": event.type}

    @app.post("/lock")
    def manual_lock(reason: str = "Manual Admin Lock via Webhook"):
        pool.lock(reason)
        return {"status": "locked", "reason": reason}

    @app.post("/unlock")
    def manual_unlock():
        pool.unlock()
        return {"status": "unlocked"}

    return app
