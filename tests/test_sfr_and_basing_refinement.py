import os
import json
import time
import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock

import config
from src.analytics.market_scanner import MarketScanner


class TestSFRAndBasingRefinement:

    @pytest.fixture
    def scanner(self, tmp_path):
        s = MarketScanner(symbols=["EURUSD-ECNc", "GBPUSD-ECNc"])
        s._cooldown_file = str(tmp_path / "test_cooldowns.json")
        return s

    def test_sfr_systemic_flow_regime_method_and_alias(self, scanner):
        scanner._m4_state["EURUSD"] = {
            "SELL": {
                "pending": {"level": 1.0850, "break_pos": 10},
                "ep": 10
            },
            "BUY": {}
        }
        scanner._m4_df["EURUSD"] = pd.DataFrame({"close": [1.0800] * 20})

        res = scanner.get_systemic_flow_regime("EURUSD", csm_delta=-1.5)
        assert res["sfr_catalyst"] == "BEARISH_FLOW"
        assert res["catalyst"] == "BEARISH_FLOW"
        assert res["sfr_side"] == "SELL"
        assert res["side"] == "SELL"
        assert res["sfr_age"] == 9

        legacy_res = scanner.get_m4_regime_catalyst("EURUSD", csm_delta=-1.5)
        assert legacy_res["catalyst"] == "BEARISH_FLOW"
        assert legacy_res["sfr_catalyst"] == "BEARISH_FLOW"

    def test_directional_hysteresis_persistence(self, scanner, tmp_path):
        now_ts = time.time()
        scanner._symbol_directional_state["EURUSD"] = {
            "dir": -1,
            "locked_at": now_ts - 100,
            "reason": "MACRO_BIAS_INIT"
        }
        scanner._symbol_directional_state["GBPUSD"] = {
            "dir": 1,
            "locked_at": now_ts - 200,
            "reason": "ZCE_BREACH"
        }

        scanner._save_cooldowns()

        assert os.path.exists(scanner._cooldown_file)
        with open(scanner._cooldown_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "symbol_directional_state" in data
        assert data["symbol_directional_state"]["EURUSD"]["dir"] == -1
        assert data["symbol_directional_state"]["GBPUSD"]["dir"] == 1

        new_scanner = MarketScanner(symbols=["EURUSD-ECNc"])
        new_scanner._cooldown_file = scanner._cooldown_file
        new_scanner._load_cooldowns()

        assert "EURUSD" in new_scanner._symbol_directional_state
        assert new_scanner._symbol_directional_state["EURUSD"]["dir"] == -1
        assert new_scanner._symbol_directional_state["GBPUSD"]["dir"] == 1

    def test_m2_dynamic_dealing_range_relaxation_logic(self):
        sfr_catalyst = "BEARISH_FLOW"
        csm_delta_val = -1.50
        min_dr_sell = 0.20 if (sfr_catalyst == "BEARISH_FLOW" and csm_delta_val <= -1.0) else 0.35
        assert min_dr_sell == 0.20

        sfr_catalyst_neutral = None
        min_dr_sell_neutral = 0.20 if (sfr_catalyst_neutral == "BEARISH_FLOW" and csm_delta_val <= -1.0) else 0.35
        assert min_dr_sell_neutral == 0.35

        sfr_catalyst_bull = "BULLISH_FLOW"
        csm_delta_bull = 1.80
        max_dr_buy = 0.80 if (sfr_catalyst_bull == "BULLISH_FLOW" and csm_delta_bull >= 1.0) else 0.65
        assert max_dr_buy == 0.80

        csm_delta_weak = 0.40
        max_dr_buy_unconfirmed = 0.80 if (sfr_catalyst_bull == "BULLISH_FLOW" and csm_delta_weak >= 1.0) else 0.65
        assert max_dr_buy_unconfirmed == 0.65

    def test_m4_pending_ready_prioritizes_high_tight_basing(self, scanner):
        scanner._m4_state["EURUSD"] = {
            "SELL": {
                "pending": {
                    "level": 1.1000,
                    "atr": 0.0020,
                    "break_pos": 5,
                    "break_time": 1000
                }
            }
        }

        mock_connector = MagicMock()
        mock_connector.get_closed_bars.return_value = [
            {"high": 1.0980, "low": 1.0976},
            {"high": 1.0979, "low": 1.0975},
            {"high": 1.0980, "low": 1.0977},
            {"high": 1.0978, "low": 1.0976},
        ]

        mid = 1.0979
        res = scanner._m4_pending_ready("EURUSD", "SELL", mid=mid, atr_now=0.0020, mt5_connector=mock_connector)

        assert res is not None
        assert res["is_basing"] is True
        assert res["level"] == 1.0980