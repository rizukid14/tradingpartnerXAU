import unittest
from unittest.mock import patch
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

    def test_multi_touch_candidate_payload(self):
        cand = CandidateSetup(
            symbol="CADJPY-ECNc",
            setup_type="MULTI_TOUCH_BREAKOUT_RETEST",
            direction=1,
            trigger_price=108.50,
            macro_compass="D1_BULLISH_TREND (ADX 26.5)",
            dealing_range_pos=0.45,
            rejection_wick_ratio=0.25,
            current_spread_pts=12,
            current_atr_pts=380,
            key_support=108.40,
            key_resistance=109.80,
            suggested_sl=108.15,
            suggested_tp=109.35,
            risk_reward_ratio=2.5,
            metadata={
                "entry_type": "buy_limit",
                "entry_price": 108.50,
                "zone_level": 108.40,
                "zone_touches": 3,
                "range_age_hours": 48.0,
                "wave_regime": "SUPER_COMPRESSION_THRUST"
            }
        )
        prompt = build_high_density_dossier_prompt(cand)
        self.assertIn("MULTI_TOUCH_BREAKOUT_RETEST", prompt)
        self.assertIn("Structural Zone Touch Count: 3 touches", prompt)
        self.assertIn("SUPER_COMPRESSION_THRUST", prompt)
        self.assertIn("BUY_LIMIT @ 108.5", prompt)


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

    def test_alert_hourly_radar_recap(self):
        from src.core import telegram_alerts as tg
        self.scanner.update_macro_context(self.connector, force=True)
        # Mock positions
        mock_positions = [
            {"ticket": 12345, "symbol": "GBPUSD-ECNc", "type": "BUY", "volume": 0.05, "profit": 15.20},
            {"ticket": 12346, "symbol": "USDJPY-ECNc", "type": "SELL", "volume": 0.05, "profit": -4.80}
        ]
        # Test that calling alert_hourly_radar_recap executes without error and does NOT send live Telegram messages
        with patch("src.core.telegram_alerts.send_message", return_value=True) as mock_send:
            result = tg.alert_hourly_radar_recap(
                scanner=self.scanner,
                open_positions=mock_positions,
                today_pnl=42.50
            )
            self.assertTrue(result)
            mock_send.assert_called_once()

    def test_evaluate_live_candle_quality(self):
        # Test with custom rates
        class CustomMockMT5:
            def get_closed_bars(self, symbol, count=5, timeframe=None):
                return [
                    {'open': 0.9400, 'high': 0.9410, 'low': 0.9380, 'close': 0.9385, 'tick_volume': 100},
                    {'open': 0.9385, 'high': 0.9390, 'low': 0.9350, 'close': 0.9355, 'tick_volume': 100}
                ]
        mock_conn = CustomMockMT5()
        res = self.scanner._evaluate_live_candle_quality("EURCHF-ECNc", mid=0.9355, atr_pts=70, pt=0.00001, mt5_connector=mock_conn)
        self.assertIn("body_ratio", res)
        self.assertIn("max_lower_wick", res)
        self.assertIn("max_upper_wick", res)
        self.assertEqual(res["direction"], "bearish")

    def test_judas_sweep_anti_waterfall_rejection(self):
        """Ensure falling knife / bearish waterfall is rejected in Judas Sweep, while real rejection wick is accepted."""
        # 1. Bearish waterfall (falling knife with 0 lower wick breaking below Asian low 0.9380)
        waterfall_rates = [
            {'open': 0.9400, 'high': 0.9410, 'low': 0.9380, 'close': 0.9385, 'tick_volume': 100},
            {'open': 0.9385, 'high': 0.9385, 'low': 0.9350, 'close': 0.9350, 'tick_volume': 100} # Marubozu waterfall, no lower wick
        ]
        class WaterfallMock:
            def get_closed_bars(self, symbol, count=5, timeframe=None):
                return waterfall_rates
        
        qual_waterfall = self.scanner._evaluate_live_candle_quality("EURCHF-ECNc", mid=0.9350, atr_pts=70, pt=0.00001, mt5_connector=WaterfallMock())
        is_bear_breakdown = (qual_waterfall['direction'] == 'bearish' and qual_waterfall['body_ratio'] >= 0.50 and qual_waterfall['lower_wick_pct'] < 0.20 and 0.9350 < 0.9380)
        has_rejection = (0.9350 >= 0.9380) or (qual_waterfall['max_lower_wick'] >= 0.20) or (qual_waterfall['sweep_side'] == 'bottom') or qual_waterfall['is_bullish_engulf']
        self.assertTrue(is_bear_breakdown, "Waterfall marubozu should be flagged as bear breakdown")
        self.assertFalse(has_rejection, "Waterfall should not have valid rejection confirmation")

        # 2. Real Judas Sweep Reversal (Hammer candle with 60% lower wick sweeping Asian low and bouncing)
        sweep_rates = [
            {'open': 0.9400, 'high': 0.9410, 'low': 0.9380, 'close': 0.9385, 'tick_volume': 100},
            {'open': 0.9380, 'high': 0.9382, 'low': 0.9350, 'close': 0.9378, 'tick_volume': 100} # Strong pinbar / hammer
        ]
        class SweepMock:
            def get_closed_bars(self, symbol, count=5, timeframe=None):
                return sweep_rates
        
        qual_sweep = self.scanner._evaluate_live_candle_quality("EURCHF-ECNc", mid=0.9378, atr_pts=70, pt=0.00001, mt5_connector=SweepMock())
        is_bear_breakdown_sweep = (qual_sweep['direction'] == 'bearish' and qual_sweep['body_ratio'] >= 0.50 and qual_sweep['lower_wick_pct'] < 0.20 and 0.9378 < 0.9380)
        has_rejection_sweep = (0.9378 >= 0.9380) or (qual_sweep['max_lower_wick'] >= 0.20) or (qual_sweep['sweep_side'] == 'bottom') or qual_sweep['is_bullish_engulf']
        self.assertFalse(is_bear_breakdown_sweep, "Hammer should not be flagged as bear breakdown")
        self.assertTrue(has_rejection_sweep, "Hammer should have valid rejection confirmation")
        self.assertGreaterEqual(qual_sweep['max_lower_wick'], 0.50)


if __name__ == "__main__":
    unittest.main()

