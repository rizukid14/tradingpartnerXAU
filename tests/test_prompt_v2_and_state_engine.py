"""Unit tests for Streamlined Prompt V2, State Machine Schema, and Clearance Engine."""
import os
import sys
import pandas as pd
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.core import llm_client, consensus


def test_clean_json_response_v2():
    print("Testing clean_json_response with V2 schema...")

    # 1. Full Streamlined V2 JSON (Exhaustion Sell Limit)
    raw_v2_sell = """```json
    {
      "market_regime": "RANGE",
      "setup": "EXHAUSTION",
      "state": "REJECTION",
      "signal": "SELL",
      "confidence": 0.75,
      "rr_valid": true,
      "entry_type": "sell_limit",
      "entry_price": 0.99180,
      "sl_points": 105,
      "tp_points": 360,
      "invalidation_price": 0.99285,
      "target_price": 0.98820,
      "reasoning": "Rejection at resistance with falling M5 momentum; 3.43 R:R back to support."
    }
    ```"""
    parsed = llm_client.clean_json_response(raw_v2_sell)
    assert parsed["market_regime"] == "RANGE"
    assert parsed["setup"] == "EXHAUSTION"
    assert parsed["state"] == "REJECTION"
    assert parsed["signal"] == "SELL"
    assert parsed["confidence"] == 0.75
    assert parsed["rr_valid"] is True
    assert parsed["entry_type"] == "sell_limit"
    assert parsed["entry_price"] == 0.99180
    assert parsed["sl_points"] == 105
    assert parsed["tp_points"] == 360
    assert parsed["invalidation_price"] == 0.99285
    assert parsed["target_price"] == 0.98820

    # 2. Fallback "direction" instead of "signal"
    raw_direction = """{
      "setup": "CONTINUATION",
      "state": "COMPRESSION",
      "direction": "BUY",
      "confidence": 0.80,
      "sl_points": 120,
      "tp_points": 300
    }"""
    parsed_dir = llm_client.clean_json_response(raw_direction)
    assert parsed_dir["signal"] == "BUY"
    assert parsed_dir["setup"] == "CONTINUATION"
    assert parsed_dir["state"] == "COMPRESSION"

    # 3. HOLD response with nulls
    raw_hold = """{
      "market_regime": "RANGE",
      "setup": "NONE",
      "state": "FAR",
      "signal": "HOLD",
      "confidence": 0.30,
      "rr_valid": false,
      "reasoning": "Trapped mid-range."
    }"""
    parsed_hold = llm_client.clean_json_response(raw_hold)
    assert parsed_hold["signal"] == "HOLD"
    assert parsed_hold["setup"] == "NONE"
    assert parsed_hold["state"] == "FAR"
    assert parsed_hold["sl_points"] is None

    print("  -> OK: clean_json_response V2 parsing 100% valid!")


def test_structure_location_and_clearance():
    print("Testing _structure_block location & clearance calculations...")

    # Create dummy 50-bar M30 dataframe
    # Range 0.98800 to 0.99200 (diff = 400 pts, point = 0.00001)
    # Current close = 0.99000 -> 50.0% location (Mid-Range)
    bars = []
    for i in range(50):
        bars.append({
            "high": 0.99050,
            "low": 0.98950,
            "close": 0.99000,
            "open": 0.98980,
            "ema_20": 0.99010,
            "ema_50": 0.98990,
            "rsi_14": 50.0,
            "adx_14": 18.5,
            "atr_14": 0.00080
        })
    bars[10]["high"] = 0.99200  # High extreme
    bars[20]["low"] = 0.98800   # Low extreme
    df = pd.DataFrame(bars)

    tick = {"point": 0.00001, "bid": 0.99000, "ask": 0.99003}
    block = llm_client._structure_block(df, tick, atr_points=80, tf_label="M30")

    assert "Location in 50-bar Range: 50.0% (Mid-Range / Value Zone)" in block
    assert "Clearance: 200 pts to Resistance High (0.99200) | 200 pts to Support Low (0.98800)" in block
    assert "weak/ranging" in block  # Neutral ADX label

    print("  -> OK: _structure_block location & clearance 100% valid!")


def test_consensus_v2_handling():
    print("Testing calculate_consensus with V2 decisions...")

    decisions = {
        "OpenAI": {
            "market_regime": "RANGE",
            "setup": "EXHAUSTION",
            "state": "REJECTION",
            "signal": "SELL",
            "confidence": 0.70,
            "rr_valid": True,
            "entry_type": "sell_limit",
            "entry_price": 0.99180,
            "sl_points": 105,
            "tp_points": 360,
            "invalidation_price": 0.99285,
            "target_price": 0.98820,
            "reasoning": "Rejection at resistance."
        },
        "Gemini": {
            "market_regime": "RANGE",
            "setup": "EXHAUSTION",
            "state": "REJECTION",
            "signal": "SELL",
            "confidence": 0.75,
            "rr_valid": True,
            "entry_type": "sell_limit",
            "entry_price": 0.99180,
            "sl_points": 105,
            "tp_points": 360,
            "invalidation_price": 0.99285,
            "target_price": 0.98820,
            "reasoning": "Upper wick rejection confirmed."
        },
        "DeepSeek": {
            "market_regime": "RANGE",
            "setup": "NONE",
            "state": "TESTING",
            "signal": "HOLD",
            "confidence": 0.30,
            "rr_valid": False,
            "reasoning": "Wait for confirmation."
        }
    }

    # Mock MT5 symbol info and tick
    with patch("src.core.consensus.config.mt5.symbol_info") as mock_si, \
         patch("src.core.consensus.config.mt5.symbol_info_tick") as mock_tick, \
         patch("src.core.consensus.config.mt5.account_info") as mock_acc:
        mock_si.return_value = MagicMock(point=0.00001, trade_tick_value=1.0, trade_tick_size=0.00001, volume_min=0.01)
        mock_tick.return_value = MagicMock(bid=0.99020, ask=0.99023)
        mock_acc.return_value = MagicMock(equity=1000.0)

        res = consensus.calculate_consensus(decisions)
        assert res["signal"] == "SELL"
        assert res["setup"] == "EXHAUSTION"
        assert res["state"] == "REJECTION"
        assert res["agreeing_count"] == 2
        assert "OpenAI" in res["agreeing_models"]
        assert "Gemini" in res["agreeing_models"]

    print("  -> OK: calculate_consensus V2 integration 100% valid!")


if __name__ == "__main__":
    test_clean_json_response_v2()
    test_structure_location_and_clearance()
    test_consensus_v2_handling()
    print("\nALL PROMPT V2 & STATE MACHINE TESTS PASSED! (3/3)")
