"""
test_sol_dex.py — Unit tests for sol_dex (Solana On-Chain Whale Copy-Trading Engine).
Validates Discovery, Safety Filter, Jupiter Execution, Position Manager, and Sentinel.
"""

import pytest
import time
from crypto_bot.sol_dex import config
from crypto_bot.sol_dex.src.whale_discovery import WhaleDiscoveryEngine
from crypto_bot.sol_dex.src.whale_watcher import SolanaWhaleWatcher
from crypto_bot.sol_dex.src.safety_filter import SolanaSafetyFilter
from crypto_bot.sol_dex.src.executor import JupiterExecutor
from crypto_bot.sol_dex.src.position_manager import SolanaPositionManager
from crypto_bot.sol_dex.src.ai_sentinel import AISentinelAudit


def test_sol_config_defaults():
    assert config.SOL_DRY_RUN is True
    assert config.SOL_MAX_POSITION_USD == 10.0
    assert config.HARD_SL_PERCENT == 50.0
    assert config.MIN_LP_BURNED_PERCENT == 90.0


def test_whale_discovery():
    engine = WhaleDiscoveryEngine()
    whales = engine.whitelist
    assert len(whales) >= 1
    addresses = engine.get_tracked_addresses()
    assert len(addresses) == len(whales)
    
    # Evaluate a sample address
    eval_res = engine.evaluate_wallet("5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1")
    assert eval_res is not None
    assert eval_res.get("qualified") is True


def test_safety_filter():
    filter_gate = SolanaSafetyFilter()
    token_mint = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"  # Bonk token
    res = filter_gate.evaluate_token(token_mint)
    assert "token_mint" in res
    assert "passed" in res
    assert "reasons" in res


def test_jupiter_executor_dry_run():
    executor = JupiterExecutor()
    assert executor.dry_run is True

    # 1. Test Buy
    res = executor.execute_swap(
        token_mint="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        is_buy=True,
        amount_sol=0.05,
    )
    assert res["status"] == "ok"
    assert res["is_dry_run"] is True

    positions = executor.get_open_positions()
    assert "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263" in positions

    # 2. Test Sell
    res_sell = executor.execute_swap(
        token_mint="DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        is_buy=False,
        amount_sol=0.05,
    )
    assert res_sell["status"] == "ok"
    assert "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263" not in executor.get_open_positions()


def test_position_manager_hard_sl():
    executor = JupiterExecutor()
    pm = SolanaPositionManager(executor)
    token = "TEST_TOKEN_SL"

    # Open position
    executor.execute_swap(token, is_buy=True, amount_sol=0.05)
    assert token in executor.get_open_positions()

    # Drop to 0.45x (-55% drop, exceeds -50% SL)
    action = pm.check_and_manage(token, current_multiplier=0.45)
    assert action is not None
    assert action["action"] == "CLOSE"
    assert action["reason"] == "HARD_SL"
    assert token not in executor.get_open_positions()


def test_position_manager_tp1():
    executor = JupiterExecutor()
    pm = SolanaPositionManager(executor)
    token = "TEST_TOKEN_TP"

    # Open position
    executor.execute_swap(token, is_buy=True, amount_sol=0.05)

    # Surge to 2.1x (+110% gain, exceeds +100% TP1)
    action = pm.check_and_manage(token, current_multiplier=2.1)
    assert action is not None
    assert action["action"] == "PARTIAL_CLOSE"
    assert action["reason"] == "TP1"


def test_ai_sentinel():
    sentinel = AISentinelAudit()
    res = sentinel.audit_position_async("SAMPLE_MINT", {"holder_count": 500, "volume_24h_usd": 150000.0})
    assert res["is_safe"] is True
    assert res["risk_score"] < 50.0


def test_whale_watcher_signal():
    watcher = SolanaWhaleWatcher()
    sig = watcher.simulate_mock_signal("5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1", "BonkMintAddress")
    assert sig["side"] == "BUY"
    assert sig["amount_sol"] > 0
