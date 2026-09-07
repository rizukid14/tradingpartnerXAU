"""
test_btc_perp.py — Unit and integration tests for btc_perp module components.
Verifies syntax, imports, risk calculations, exchange router, and consensus jury.
"""

import pytest
import time
from crypto_bot.btc_perp import config
from crypto_bot.btc_perp.src.core.hl_connector import HyperliquidConnector
from crypto_bot.btc_perp.src.core.binance_connector import BinanceConnector
from crypto_bot.btc_perp.src.core.exchange_router import ExchangeRouter
from crypto_bot.btc_perp.src.core.whale_tracker import WhaleTracker
from crypto_bot.btc_perp.src.core.risk_engine import BTCRiskEngine
from crypto_bot.btc_perp.src.core.consensus import BTCConsensusJury
from crypto_bot.btc_perp.src.core.position_manager import BTCPositionManager
from crypto_bot.btc_perp.src.analytics.btc_scanner import BTCScanner


def test_config_defaults():
    assert config.BTC_SYMBOL == "BTC"
    assert config.BTC_LEVERAGE == 2
    assert config.BTC_DRY_RUN is True
    assert config.BTC_RISK_PERCENT == 1.0


def test_hl_connector_dry_run():
    hl = HyperliquidConnector(dry_run=True)
    equity = hl.get_equity()
    assert equity >= 1000.0

    order = hl.place_order(coin="BTC", is_buy=True, sz=0.01, px=60000.0, sl_px=59000.0, tp_px=62000.0)
    assert order["status"] == "ok"
    assert order["filled"] is True

    positions = hl.get_positions()
    assert len(positions) == 1
    assert positions[0]["coin"] == "BTC"
    assert positions[0]["side"] == "BUY"

    close_res = hl.close_position("BTC")
    assert close_res["status"] == "ok"
    assert len(hl.get_positions()) == 0


def test_binance_connector_dry_run():
    bn = BinanceConnector(dry_run=True)
    equity = bn.get_equity()
    assert equity >= 1000.0

    order = bn.place_order(coin="BTC", is_buy=False, sz=0.02, px=61000.0)
    assert order["status"] == "ok"
    assert len(bn.get_positions()) == 1

    bn.close_position("BTC")
    assert len(bn.get_positions()) == 0


def test_exchange_router():
    router = ExchangeRouter()
    assert router.get_active_exchange_name() in ("hyperliquid", "binance")
    equity = router.get_equity()
    assert equity > 0.0


def test_whale_tracker():
    tracker = WhaleTracker(cache_ttl_sec=60)
    data = tracker.get_whale_positioning("BTC")
    assert "net_whale_bias" in data
    assert data["net_whale_bias"] in ("LONG_BIASED", "SHORT_BIASED", "NEUTRAL")
    prompt_str = tracker.format_for_prompt("BTC")
    assert "WHALE POSITIONING MATRIX" in prompt_str


def test_risk_engine_sizing():
    engine = BTCRiskEngine()
    equity = 1000.0  # $1,000 equity
    entry_price = 60000.0
    sl_price = 59000.0  # $1,000 SL distance

    # risk_usd = 1% of 1000 = $10
    # btc_size = $10 / $1000 = 0.01 BTC
    # notional = 0.01 * 60000 = $600 (well within 2x leverage $2000 cap)
    size, notional, err = engine.calculate_position_size(equity, entry_price, sl_price)
    assert err == ""
    assert size == 0.01
    assert notional == 600.0


def test_risk_engine_leverage_cap():
    engine = BTCRiskEngine()
    equity = 100.0  # $100 equity, max 2x leverage = $200 notional
    entry_price = 60000.0
    sl_price = 59990.0  # Tiny SL ($10 distance) -> unconstrained size would be $1 / $10 = 0.1 BTC = $6,000 notional!

    size, notional, err = engine.calculate_position_size(equity, entry_price, sl_price)
    assert err == ""
    assert notional <= 200.01  # Must be capped at 2x equity ($200)


def test_consensus_veto():
    jury = BTCConsensusJury()
    # Funding rate is > 0.05% on BUY -> Veto
    mkt = {"mid_price": 60000.0, "funding_rate": 0.0008}
    setup = {"direction": "BUY", "mechanism": "M1_UNIVERSAL_LIQUIDITY_SWEEP", "score": 85.0}
    whale = {"net_whale_bias": "LONG_BIASED"}

    res = jury.evaluate(setup, mkt, whale, atr_h1=800.0)
    assert res["signal"] == "HOLD"
    assert res["veto_triggered"] is True
    assert res["reason_code"] == "EXTREME_FUNDING_RATE"


def test_btc_scanner_atr():
    router = ExchangeRouter()
    scanner = BTCScanner(router)
    dummy_candles = [
        {"high": 60500.0, "low": 59500.0, "open": 60000.0, "close": 60200.0}
        for _ in range(30)
    ]
    atr = scanner.calculate_atr(dummy_candles, 14)
    assert atr > 0.0
