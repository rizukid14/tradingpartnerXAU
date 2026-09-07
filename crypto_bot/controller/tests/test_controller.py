"""
test_controller.py — Unit and integration tests for Unified Crypto Controller.
Validates Shared Risk Pool, Circuit Breaker, FastAPI Event Bridge, and Telegram Commands.
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from crypto_bot.controller.src.risk_pool import SharedRiskPool
from crypto_bot.controller.src.event_bridge import create_app
from crypto_bot.controller.src.telegram_bot import CryptoTelegramController


@pytest.fixture
def temp_risk_pool(tmp_path):
    state_file = tmp_path / "test_risk_state.json"
    return SharedRiskPool(state_file=state_file)


def test_risk_pool_initialization(temp_risk_pool):
    summary = temp_risk_pool.get_summary()
    assert summary["realized_pnl_usd"] == 0.0
    assert summary["locked"] is False


def test_risk_pool_record_profit(temp_risk_pool):
    locked, msg = temp_risk_pool.record_trade_result("BTC", 25.0)
    assert locked is False
    summary = temp_risk_pool.get_summary()
    assert summary["realized_pnl_usd"] == 25.0
    assert summary["worker_breakdown"]["BTC"] == 25.0


def test_risk_pool_circuit_breaker(temp_risk_pool):
    # Start equity is $1000, 5% max loss = $50
    # Loss of -$60 should trigger circuit breaker
    locked, msg = temp_risk_pool.record_trade_result("BTC", -60.0)
    assert locked is True
    assert "exceeded" in msg.lower()
    
    is_locked, reason = temp_risk_pool.is_locked()
    assert is_locked is True
    assert "60.00" in reason


def test_risk_pool_manual_unlock(temp_risk_pool):
    temp_risk_pool.lock("Emergency Test Lock")
    assert temp_risk_pool.is_locked()[0] is True

    temp_risk_pool.unlock()
    assert temp_risk_pool.is_locked()[0] is False


def test_event_bridge_api(temp_risk_pool):
    app = create_app(risk_pool=temp_risk_pool)
    client = TestClient(app)

    # 1. Health check
    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"

    # 2. Status
    res_status = client.get("/status")
    assert res_status.status_code == 200
    assert "realized_pnl_usd" in res_status.json()

    # 3. Post Event
    payload = {
        "worker": "BTC",
        "type": "POSITION_OPENED",
        "timestamp": 123456789.0,
        "details": {"coin": "BTC", "size": 0.01, "price": 60000.0},
    }
    res_event = client.post("/event", json=payload)
    assert res_event.status_code == 200
    assert res_event.json()["received"] == "POSITION_OPENED"


def test_telegram_command_handler(temp_risk_pool):
    tg = CryptoTelegramController(risk_pool=temp_risk_pool)

    # 1. Status command
    reply = tg.handle_command("/crypto")
    assert "CRYPTO PORTFOLIO DASHBOARD" in reply

    # 2. Killall command
    kill_reply = tg.handle_command("/killall")
    assert "EMERGENCY HALT TRIGGERED" in kill_reply
    assert temp_risk_pool.is_locked()[0] is True

    # 3. Unlock command
    unlock_reply = tg.handle_command("/unlock")
    assert "RISK POOL UNLOCKED" in unlock_reply
    assert temp_risk_pool.is_locked()[0] is False
