import unittest
import numpy as np  # type: ignore
import pandas as pd  # type: ignore
from datetime import datetime
from zoneinfo import ZoneInfo

import config
from src.analytics.market_scanner import MarketScanner, CandidateSetup
from src.core.llm_client import build_high_density_dossier_prompt

WIB = ZoneInfo("Asia/Jakarta")

class MockMT5Connector:
    def __init__(self):
        self.rates_cache = {}
        self.tick_cache = {}

    def get_closed_bars(self, symbol, count=120, timeframe=None):
        # Generate synthetic 100 bars
        n = count
        dates = pd.date_range("2026-08-20 00:00:00", periods=n, freq="1h", tz=WIB)
        close = 1.3000 + np.cumsum(np.random.normal(0, 0.0005, n))
        high = close + 0.0008
        low = close - 0.0008
        open_p = close - 0.0001
        
        rates = []
        for i in range(n):
            rates.append({
                'time': int(dates[i].timestamp()),
                'open': open_p[i],
                'high': high[i],
                'low': low[i],
                'close': close[i],
                'tick_volume': 500
            })
        return rates

    def get_live_tick(self, symbol):
        return {'ask': 1.3015, 'bid': 1.3013, 'time': int(datetime.now(WIB).timestamp())}


class TestMarketScanner(unittest.TestCase):
    def setUp(self):
        self.scanner = MarketScanner(symbols=["GBPUSD-ECNc", "USDJPY-ECNc", "XAUUSD-ECNc"])
        self.connector = MockMT5Connector()

    def test_candidate_payload_dict(self):
        cand = CandidateSetup(
            symbol="GBPUSD-ECNc",
            setup_type="LONDON_JUDAS_SWEEP",
            direction=1,
            trigger_price=1.2950,
            macro_compass="D1_BULLISH_TREND (ADX 28.4)",
            dealing_range_pos=0.28,
            rejection_wick_ratio=0.42,
            current_spread_pts=15,
            current_atr_pts=320,
            key_support=1.2920,
            key_resistance=1.3050,
            suggested_sl=1.2915,
            suggested_tp=1.3040,
            risk_reward_ratio=2.6,
            timestamp_wib="14:15:00 WIB"
        )
        payload = cand.to_payload_dict()
        self.assertEqual(payload["event"], "FAST_RADAR_TRIGGER_CONFIRMED")
        self.assertEqual(payload["symbol"], "GBPUSD-ECNc")
        self.assertEqual(payload["direction"], "BUY")
        self.assertEqual(payload["risk_reward_ratio"], 2.6)
        self.assertIn("DEEP DISCOUNT", payload["dealing_range_position"])

    def test_macro_context_update(self):
        self.scanner.update_macro_context(self.connector, force=True)
        self.assertGreater(len(self.scanner.macro_cache), 0)
        for sym in ["GBPUSD-ECNc", "USDJPY-ECNc", "XAUUSD-ECNc"]:
            if sym in self.scanner.macro_cache:
                m = self.scanner.macro_cache[sym]
                self.assertIn('trend_label', m)
                self.assertIn('dealing_range_pos', m)
                self.assertIn('asian_high', m)
                self.assertIn('asian_low', m)

    def test_market_structure_report(self):
        self.scanner.update_macro_context(self.connector, force=True)
        report = self.scanner.get_market_structure_report()
        self.assertIn("MARKET STRUCTURE", report)
        self.assertIn("Bullish Compass", report)

    def test_high_density_dossier_prompt(self):
        cand = CandidateSetup(
            symbol="GBPJPY-ECNc",
            setup_type="TREND_ALIGNED_PULLBACK",
            direction=1,
            trigger_price=194.50,
            macro_compass="D1_BULLISH_TREND",
            dealing_range_pos=0.32,
            rejection_wick_ratio=0.35,
            current_spread_pts=18,
            current_atr_pts=450,
            key_support=194.10,
            key_resistance=195.80,
            suggested_sl=194.00,
            suggested_tp=195.75,
            risk_reward_ratio=2.5
        )
        prompt = build_high_density_dossier_prompt(cand)
        self.assertIn("INSTITUTIONAL TRADING JURY: CANDIDATE VERIFICATION & ORDER OPTIMIZER DOSSIER", prompt)
        self.assertIn("EVALUATION DIRECTIVE", prompt)
        self.assertIn("veto_reason", prompt)
        self.assertIn("risk_flag", prompt)
        self.assertIn("APPROVE", prompt)
        self.assertIn("REVISE", prompt)


    def test_session_aware_pair_filtering(self):
        # 1. Tokyo Session (10:00 WIB)
        # Proven pairs should be ALLOWED
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("AUDCAD-ECNc", 10))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("USDCAD", 10))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("XAUUSD-ECNc", 10))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("GBPJPY-ECNc", 10))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("AUDJPY", 10))
        
        # Non-Tokyo European pairs should be BLOCKED in morning
        self.assertFalse(MarketScanner.is_symbol_allowed_for_session("GBPUSD-ECNc", 10))
        self.assertFalse(MarketScanner.is_symbol_allowed_for_session("EURUSD-ECNc", 10))
        self.assertFalse(MarketScanner.is_symbol_allowed_for_session("EURCHF-ECNc", 10))
        self.assertFalse(MarketScanner.is_symbol_allowed_for_session("GBPAUD", 10))
        
        # 2. London / NY Session (15:00 WIB)
        # ALL pairs should be ALLOWED
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("GBPUSD-ECNc", 15))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("EURUSD-ECNc", 15))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("AUDCAD-ECNc", 15))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("XAUUSD-ECNc", 20))


if __name__ == "__main__":
    unittest.main()
