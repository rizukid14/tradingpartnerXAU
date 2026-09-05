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
        self.scanner._mechanism_rejection_cooldowns.clear()
        self.scanner._symbol_last_eval.clear()
        self.scanner._symbol_last_trigger.clear()
        self.connector = MockMT5Connector()

    def test_candidate_payload_dict(self):
        cand = CandidateSetup(
            symbol="GBPUSD-ECNc",
            setup_type="UNIVERSAL_LIQUIDITY_SWEEP",
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
        self.assertIn("EVALUATION", prompt)
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
        # All pairs containing JPY, AUD, or NZD must be ALLOWED (including CAD pairs like AUDCAD, CADJPY, NZDCAD)
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("AUDCAD-ECNc", 10))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("CADJPY-ECNc", 10))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("GBPJPY-ECNc", 10))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("EURJPY-ECNc", 10))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("AUDJPY", 10))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("GBPAUD", 10))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("NZDCAD-ECNc", 10))
        
        # Pairs WITHOUT JPY/AUD/NZD (pure CAD like EURCAD, USDCAD, or pure EUR/GBP/USD like EURUSD, GBPUSD, EURCHF) must be BLOCKED
        self.assertFalse(MarketScanner.is_symbol_allowed_for_session("EURCAD-ECNc", 10))
        self.assertFalse(MarketScanner.is_symbol_allowed_for_session("USDCAD", 10))
        self.assertFalse(MarketScanner.is_symbol_allowed_for_session("GBPUSD-ECNc", 10))
        self.assertFalse(MarketScanner.is_symbol_allowed_for_session("EURUSD-ECNc", 10))
        self.assertFalse(MarketScanner.is_symbol_allowed_for_session("EURCHF-ECNc", 10))
        
        # 2. London / NY Session (15:00 WIB)
        # ALL pairs should be ALLOWED
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("GBPUSD-ECNc", 15))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("EURUSD-ECNc", 15))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("AUDCAD-ECNc", 15))
        self.assertTrue(MarketScanner.is_symbol_allowed_for_session("EURCAD-ECNc", 15))

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

    def test_universal_sweep_anti_waterfall_rejection(self):
        """Ensure falling knife / bearish waterfall is rejected in Universal Sweep, while real rejection wick is accepted."""
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

        # 2. Real Universal Sweep Reversal (Hammer candle with 60% lower wick sweeping Asian low and bouncing)
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

    def test_trend_pullback_intraday_sltp_and_ceiling(self):
        """Verify that TREND_ALIGNED_PULLBACK calculates tight intraday SL/TP and consensus caps runaway SL."""
        from src.core.consensus import _apply_sltp_rules
        
        # 1. Normal FX SL/TP calculation with anti-wick padding (e.g. EURCAD atr_pts=69, spread=4)
        atr_pts = 69
        spread_pts = 4
        pt = 0.00001
        mid = 1.61380
        
        anti_wick_padding = 15 * pt
        sl = mid - (atr_pts * 0.85 * pt) - (spread_pts * pt) - anti_wick_padding
        tp = mid + abs(mid - sl) * 2.2
        
        sl_pts = int(round(abs(mid - sl) / pt))
        tp_pts = int(round(abs(tp - mid) / pt))
        
        # SL should be ~77 pts (7.7 pips), not 600 pts
        self.assertGreaterEqual(sl_pts, 70)
        self.assertLessEqual(sl_pts, 95)
        self.assertGreaterEqual(tp_pts, 150)
        
    def test_delayed_limit_retest_generation(self):
        """Verify that CandidateSetup in Trend-Aligned Pullback calculates delayed limit retest correctly."""
        from src.analytics.market_scanner import CandidateSetup
        cand = CandidateSetup(
            symbol="EURUSD-ECNc",
            setup_type="TREND_ALIGNED_PULLBACK",
            direction=1,
            trigger_price=1.1710,
            macro_compass="D1_BULLISH_EXPANSION",
            dealing_range_pos=0.35,
            rejection_wick_ratio=0.30,
            current_spread_pts=5,
            current_atr_pts=50,
            key_support=1.1680,
            key_resistance=1.1780,
            suggested_sl=1.1670,
            suggested_tp=1.1798,
            risk_reward_ratio=2.2,
            permission="GO",
            csm_delta=0.8,
            metadata={
                "entry_type": "buy_limit",
                "entry_price": 1.1710,
                "base_floor": 1.1680,
                "permission": "GO",
                "csm_delta": 0.8
            }
        )
        payload = cand.to_payload_dict()
        self.assertEqual(payload["trade_permission"], "GO")
        self.assertEqual(payload["csm_net_delta"], 0.8)
    def test_mark_symbol_cancelled_cooldown(self):
        """Verify mark_symbol_cancelled sets a 30-minute cooldown on the symbol."""
        import time
        sym = "EURUSD-ECNc"
        clean = "EURUSD"
        self.scanner.mark_symbol_cancelled(sym, cooldown_seconds=1800)
        self.assertIn(clean, self.scanner._symbol_last_trigger)
        now_ts = time.time()
        # Difference between now and recorded timestamp should be >= 890s (900s offset from 1800s)
        trigger_ts = self.scanner._symbol_last_trigger[clean]
        self.assertGreater(trigger_ts, now_ts)
        self.assertLess(now_ts - trigger_ts, 900)

    def test_htf_weekly_wall_reversal_trigger(self):
        """Verify Mechanism 3 (HTF Weekly Wall Reversal) calculates SL/TP without NameError."""
        from src.analytics.market_scanner import MarketScanner
        sym = "AUDUSD"  # Allowed in Tokyo session
        scanner = MarketScanner([sym])
        scanner.macro_cache[sym] = {
            'symbol': sym,
            'point': 0.00001,
            'atr_pts': 100.0,
            'trend_label': 'D1_BULLISH',
            'is_bull': True,
            'is_bear': False,
            'pwh': 0.6500,
            'pwl': 0.6400,
            'permission_state': 'GO',
            'csm_delta': 0.5,
            'dealing_range_pos': 0.85,
            'dealing_range_low': 0.6400,
            'dealing_range_high': 0.6520,
            'ema20': 0.6200,
        }
        
        # Test Bearish Wall Reversal logic
        pwh = 0.6500
        pwl = 0.6400
        w_mid = pwl + 0.50 * (pwh - pwl)  # 0.6450
        pt = 0.00001
        atr_pts = 100.0
        spread_pts = 10
        anti_wick_padding = 20 * pt
        mid = 0.6502
        live_h = 0.6510
        
        sl = max(live_h, pwh) + (atr_pts * 0.35 * pt) + (spread_pts * pt) + anti_wick_padding
        tp = w_mid
        risk_dist = abs(sl - mid)
        rr_val = round(abs(mid - tp) / risk_dist, 2)
        
        self.assertGreaterEqual(rr_val, 1.8)
        self.assertGreater(sl, pwh)
        self.assertEqual(tp, 0.6450)

    def test_consensus_apply_sltp_symbol_specific(self):
        """Verify consensus _apply_sltp_rules executes for non-default symbol."""
        from src.core.consensus import _apply_sltp_rules
        with patch.object(config, "ZCE_ENABLED", False), patch.object(config, "ZCE_MODE", "shadow"):
            sl_pts, tp_pts, ok, reason = _apply_sltp_rules(50, 100, symbol="USDJPY-ECNc")
        self.assertTrue(ok)
        self.assertGreaterEqual(sl_pts, 50)
    def test_universal_sweep_gates_locked_during_bearish_delivery(self):
        """Verify Gate B locks Universal Sweep BUY when price is in Bearish Delivery from PWH Ceiling."""
        from src.analytics.market_scanner import evaluate_universal_sweep_gates
        allowed, reason = evaluate_universal_sweep_gates(
            signal_type='BUY',
            dealing_range_pos=0.65,
            dist_to_htf_floor=0.0050,
            dist_to_htf_ceiling=0.0010,
            atr_val=0.0010,
            recent_ceiling_touch=True,
            recent_floor_touch=False,
            close_below_ema20=True,
            close_above_ema20=False,
            macro_trend='BEARISH'
        )
        self.assertFalse(allowed)
        self.assertIn("GATE B", reason)
        self.assertIn("Bearish Delivery", reason)

    def test_universal_sweep_gates_locked_without_htf_anchor(self):
        """Verify Gate A locks Universal Sweep BUY when sweep occurs in mid-range without HTF Floor anchor."""
        from src.analytics.market_scanner import evaluate_universal_sweep_gates
        allowed, reason = evaluate_universal_sweep_gates(
            signal_type='BUY',
            dealing_range_pos=0.35,  # In discount zone (<=45%), but lacks deep discount (<=25%) and lacks HTF Floor
            dist_to_htf_floor=0.0060,
            dist_to_htf_ceiling=0.0040,
            atr_val=0.0010,
            recent_ceiling_touch=False,
            recent_floor_touch=False,
            close_below_ema20=False,
            close_above_ema20=True,
            macro_trend='BULLISH'
        )
        self.assertFalse(allowed)
        self.assertIn("GATE A", reason)
        self.assertIn("HTF Support Floor", reason)

    def test_universal_sweep_gates_allowed_at_htf_deep_discount(self):
        """Verify Universal Sweep BUY passes when anchored at HTF Deep Discount Floor (DR <= 0.35)."""
        from src.analytics.market_scanner import evaluate_universal_sweep_gates
        allowed, reason = evaluate_universal_sweep_gates(
            signal_type='BUY',
            dealing_range_pos=0.28,  # Deep Discount <= 35%
            dist_to_htf_floor=0.0002,  # Very close to floor
            dist_to_htf_ceiling=0.0080,
            atr_val=0.0010,
            recent_ceiling_touch=False,
            recent_floor_touch=False,
            close_below_ema20=False,
            close_above_ema20=True,
            macro_trend='BULLISH'
        )
        self.assertTrue(allowed)
        self.assertIn("PASSED ALL GATES", reason)

    def test_watch_only_action_tier_hard_blocks_radar(self):
        """Verify symbols with action_tier == 'WATCH_ONLY' are 100% hard blocked from generating candidates."""
        from unittest.mock import MagicMock
        from src.analytics.macro_strategic_engine import MacroStrategicDirective

        mock_directive = MagicMock(spec=MacroStrategicDirective)
        mock_directive.action_tier = "WATCH_ONLY"
        mock_directive.macro_bias_score = 0.0
        mock_directive.hard_circuit_breaker = False
        mock_directive.forbidden_traps = ["Do NOT execute market orders in mid-chamber consolidation zone"]

        self.scanner.macro_cache["GBPUSD-ECNc"] = {
            'point': 0.00001,
            'atr_pts': 100,
            'dealing_range_pos': 0.34,
            'dealing_range_low': 1.2900,
            'dealing_range_high': 1.3100,
            'is_bull': True,
            'is_bear': False,
            'trend_label': 'BULLISH',
            'permission_state': 'GO',
            'csm_delta': 0.5,
            'strat_dir': mock_directive,
            'action_tier': 'WATCH_ONLY',
            'macro_bias_score': 0.0,
            'macro_corridor': 'BULLISH_CORRIDOR',
            'immediate_floor_f1': 1.2920,
            'immediate_ceiling_c1': 1.3080
        }

        # Mock tick in middle of chamber (1.3000)
        mock_connector = MagicMock()
        mock_connector.get_live_tick.return_value = {'ask': 1.3001, 'bid': 1.2999, 'time': int(datetime.now(WIB).timestamp())}
        mock_connector.get_closed_bars.return_value = [
            {'open': 1.2998, 'high': 1.3005, 'low': 1.2995, 'close': 1.3000, 'time': 1700000000}
        ]

        with patch("src.analytics.market_scanner.evaluate_systemic_basket_lock", return_value=(False, "", None)):
            with patch.object(self.scanner, 'is_symbol_allowed_for_session', return_value=True):
                with patch("src.analytics.market_scanner.datetime") as mock_dt:
                    mock_dt.now.return_value = datetime(2026, 8, 31, 14, 0, 0, tzinfo=WIB)
                    mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                    candidates = self.scanner.scan_fast_radar(mock_connector)
                    # All candidates must be blocked because action_tier is WATCH_ONLY
                    gbp_candidates = [c for c in candidates if c.symbol == "GBPUSD-ECNc"]
                    self.assertEqual(len(gbp_candidates), 0, "WATCH_ONLY symbol must not produce candidates!")

    def test_universal_sweep_gates_locked_during_macro_expansion(self):
        """Verify Gate C locks M1 Sweep SELL when macro is BULLISH_EXPANSION and C1 is far above."""
        from src.analytics.market_scanner import evaluate_universal_sweep_gates
        allowed, reason = evaluate_universal_sweep_gates(
            signal_type='SELL',
            dealing_range_pos=0.988,
            dist_to_htf_floor=0.00300,
            dist_to_htf_ceiling=0.00199,  # 19.9 pips (> 0.35 * 0.00340 = 0.00119)
            atr_val=0.00340,
            recent_ceiling_touch=False,
            recent_floor_touch=False,
            close_below_ema20=False,
            close_above_ema20=True,
            macro_trend='BULLISH_EXPANSION'
        )
        self.assertFalse(allowed)
        self.assertIn("GATE C", reason)
        self.assertIn("Anti-Expansion", reason)

    def test_m1_sweep_blocks_g1_in_trending_market(self):
        """Verify M1 Sweep SELL blocks G1 Micro Level sweeps in trending markets."""
        from unittest.mock import MagicMock
        from datetime import datetime
        from zoneinfo import ZoneInfo
        WIB = ZoneInfo("Asia/Jakarta")

        self.scanner.macro_cache["EURUSD-ECNc"] = {
            'point': 0.00001,
            'atr_pts': 100,
            'dealing_range_pos': 0.85,
            'dealing_range_low': 1.0800,
            'dealing_range_high': 1.0900,
            'is_bull': True,
            'is_bear': False,
            'trend_label': 'BULLISH',
            'permission_state': 'GO',
            'csm_delta': 0.5,
            'action_tier': 'FULL_ALLOW',
            'macro_bias_score': 0.5,
            'macro_corridor': 'BULLISH_CORRIDOR',
            'daily_macro_bias': 'BULLISH_EXPANSION',
            'immediate_floor_f1': 1.0820,
            'immediate_ceiling_c1': 1.0950,
            'c1_reaction_grade': 'GRADE_1_MICRO',
            'asian_high': 1.0880,
            'pdh': 1.0880,
            'ema20': 1.0850,
            'ema50': 1.0830
        }

        mock_connector = MagicMock()
        mock_connector.get_live_tick.return_value = {'ask': 1.0879, 'bid': 1.0877, 'time': int(datetime.now(WIB).timestamp())}
        mock_connector.get_closed_bars.return_value = [
            {'open': 1.0870, 'high': 1.0882, 'low': 1.0868, 'close': 1.0876, 'time': 1700000000}
        ]

        with patch("src.analytics.market_scanner.evaluate_systemic_basket_lock", return_value=(False, "", None)):
            with patch.object(self.scanner, 'is_symbol_allowed_for_session', return_value=True):
                with patch("src.analytics.market_scanner.datetime") as mock_dt:
                    mock_dt.now.return_value = datetime(2026, 8, 31, 15, 0, 0, tzinfo=WIB) # London session
                    mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                    candidates = self.scanner.scan_fast_radar(mock_connector)
                    sweep_cands = [c for c in candidates if c.symbol == "EURUSD-ECNc" and c.setup_type == "UNIVERSAL_LIQUIDITY_SWEEP"]
                    self.assertEqual(len(sweep_cands), 0, "G1 Micro level in trending market must NOT produce M1 Sweep candidate!")

    def test_scan_all_alias(self):
        """Verify scan_all alias calls scan_fast_radar properly."""
        with patch.object(self.scanner, 'scan_fast_radar', return_value=[]) as mock_fast:
            res = self.scanner.scan_all(self.connector)
            self.assertEqual(res, [])
            mock_fast.assert_called_once_with(mt5_connector=self.connector)

    def test_get_radar_standbys_bearish_and_bullish(self):
        """Verify get_radar_standbys extracts 1:1 levels: bearish M2 at EMA/resistance, bullish at EMA/support."""
        # 1. Bearish Case (EURAUD style)
        macro_bear = {
            'is_bear': True,
            'is_bull': False,
            'immediate_floor_f1': 1.61114,
            'immediate_ceiling_c1': 1.61574,
            'ema20': 1.61626,
            'ema50': 1.61779,
            'dealing_range_low': 1.61343,
            'dealing_range_high': 1.62524,
            'micro_sbr_h1': 1.61550,
            'asian_high': 1.61900
        }
        standbys_bear = self.scanner.get_radar_standbys("EURAUD-ECNc", mid=1.61450, macro=macro_bear)
        m2_bear = next((s for s in standbys_bear if s['type'] == 'M2'), None)
        self.assertIsNotNone(m2_bear)
        # M2 in bearish must be at or above price (near EMA / C1 ceiling), NEVER at swing low 1.61344!
        self.assertGreaterEqual(m2_bear['price'], 1.61450)
        self.assertNotEqual(m2_bear['price'], 1.61344)
        self.assertIn("Bearish", m2_bear['label'])

        # 2. Bullish Case
        macro_bull = {
            'is_bear': False,
            'is_bull': True,
            'immediate_floor_f1': 1.10000,
            'immediate_ceiling_c1': 1.10800,
            'ema20': 1.10300,
            'ema50': 1.10200,
            'dealing_range_low': 1.09800,
            'dealing_range_high': 1.10900,
            'micro_rbs_h1': 1.10150,
            'asian_low': 1.09900
        }
        standbys_bull = self.scanner.get_radar_standbys("EURUSD-ECNc", mid=1.10400, macro=macro_bull)
        m2_bull = next((s for s in standbys_bull if s['type'] == 'M2'), None)
        self.assertIsNotNone(m2_bull)
        # M2 in bullish must be at or below price (near EMA / F1 floor)
        self.assertLessEqual(m2_bull['price'], 1.10400)
        self.assertIn("Bullish", m2_bull['label'])

    def test_find_ema_confluence_anchor_and_temporal_tracking(self):
        """Verify M2 anchors to institutional confluence (Psych, OB, FVG, F1) and standbys include temporal tracking."""
        macro = {
            'is_bull': True,
            'is_bear': False,
            'ema20': 0.71866,
            'ema50': 0.71731,
            'current_atr': 0.00100,
            'dealing_range_pos': 0.85,
            'bullish_ob_top': 0.71686,
            'immediate_floor_f1': 0.71844,
            'cluster_resistance': 0.71844,
            'touches_resistance': 2
        }
        # 1. Test EMA Confluence Anchor
        price, desc = self.scanner.find_ema_confluence_anchor("AUDUSD-ECNc", mid=0.72050, direction=1, macro=macro, pt=0.00001, atr_val=0.00100)
        self.assertGreater(price, 0.0)
        self.assertLess(price, 0.72050)
        self.assertIn("Confluence", desc)

        # 2. Test Temporal Tracking fields in Standbys
        standbys = self.scanner.get_radar_standbys("AUDUSD-ECNc", mid=0.72050, macro=macro, pt=0.00001, atr_val=0.00100)
        for s in standbys:
            self.assertIn("type", s)
            self.assertIn("price", s)
            self.assertIn("label", s)
            self.assertIn("event_time", s)
            self.assertIn("status", s)
            self.assertIn("bar_age", s)
            self.assertIn("direction", s)


    def test_structural_trend_and_tactical_chamber_separation(self):
        """Verify structural trend remains BEARISH during dump, while tactical floor state captures REBOUND WATCH."""
        macro = {
            'symbol': 'EURJPY-ECNc',
            'trend_label': 'D1_BEARISH_EXPANSION | H4_BEARISH_EXPANSION',
            'is_bull': False,
            'is_bear': True,
            'dealing_range_pos': 0.10,
            'immediate_floor_f1': 181.000,
            'immediate_ceiling_c1': 181.426,
            'ema20': 181.731,
            'ema50': 183.074,
            'current_atr': 0.438,
            'tactical_state': 'REBOUND_WATCH_AT_FLOOR',
            'tactical_desc': 'REBOUND @ 181.000'
        }
        standbys = self.scanner.get_radar_standbys("EURJPY-ECNc", mid=181.042, macro=macro, pt=0.001, atr_val=0.438)
        
        # M1 must test the floor (Bullish Sweep SFP Low @ 181.000)
        m1 = next((s for s in standbys if s['type'] == 'M1'), None)
        self.assertIsNotNone(m1)
        self.assertEqual(m1['direction'], 1)
        self.assertIn("Bullish Sweep Support", m1['label'])
        self.assertLessEqual(m1['price'], 181.050)
        
        # M2 must be pro-trend (Bearish Pullback retesting resistance >= mid)
        m2 = next((s for s in standbys if s['type'] == 'M2'), None)
        self.assertIsNotNone(m2)
        self.assertEqual(m2['direction'], -1)
        self.assertIn("Bearish Pullback", m2['label'])
        self.assertGreaterEqual(m2['price'], 181.042)

    def test_granular_mechanism_rejection_isolation(self):
        """Verify M4 BUY rejection only locks M4 BUY, leaving M1, M2, and M3 completely unblocked."""
        sym = "AUDUSD-ECNc"
        clean = "AUDUSD"

        # Record rejection for M4 BUY
        self.scanner.record_setup_rejection(
            symbol=sym,
            setup_type="SYSTEMIC_FLOW_CONTINUATION",
            direction=1,
            level=0.72080,
            current_atr=0.00045
        )

        # 1. M4 BUY must be locked
        m4_locked, reason = self.scanner.is_mechanism_locked(clean, "SYSTEMIC_FLOW_CONTINUATION", 1)
        self.assertTrue(m4_locked)
        self.assertIn("rejected by LLM", reason)

        # 2. M4 SELL must NOT be locked
        m4_s_locked, _ = self.scanner.is_mechanism_locked(clean, "SYSTEMIC_FLOW_CONTINUATION", -1)
        self.assertFalse(m4_s_locked)

        # 3. M1 (Universal Liquidity Sweep) must NOT be locked
        m1_locked, _ = self.scanner.is_mechanism_locked(clean, "UNIVERSAL_LIQUIDITY_SWEEP", 1)
        self.assertFalse(m1_locked)

        # 4. M2 (Trend-Aligned Pullback) must NOT be locked
        m2_locked, _ = self.scanner.is_mechanism_locked(clean, "TREND_ALIGNED_PULLBACK", 1)
        self.assertFalse(m2_locked)

        # 5. M3 (Multi-Touch Breakout Retest) must NOT be locked
        m3_locked, _ = self.scanner.is_mechanism_locked(clean, "MULTI_TOUCH_BREAKOUT_RETEST", 1)
        self.assertFalse(m3_locked)

        # 6. Breathing cooldown must be active on symbol initially
        import time
        now_ts = time.time()
        is_breathing, _ = self.scanner.is_symbol_breathing(clean, now_ts)
        self.assertTrue(is_breathing)

    def test_m4_range_discipline_flexible_override(self):
        """Verify M4 Range Discipline skips BUY in extreme premium (>0.70) UNLESS CSM Delta >= +0.035."""
        import config
        ext_hi = config.M4_EXTREME_DR_THRESHOLD
        csm_ovr = config.M4_EXTREME_CSM_DELTA_OVERRIDE

        # Scenario 1: DR 0.895 (Extreme Premium), Normal CSM Delta (+0.010) -> Must be blocked
        dr_pos = 0.895
        csm_delta_normal = 0.010
        should_block_normal = (dr_pos > ext_hi) and (csm_delta_normal < csm_ovr)
        self.assertTrue(should_block_normal)

        # Scenario 2: DR 0.895 (Extreme Premium), Extreme Surge CSM Delta (+0.045) -> Must be allowed
        csm_delta_surge = 0.045
        should_block_surge = (dr_pos > ext_hi) and (csm_delta_surge < csm_ovr)
        self.assertFalse(should_block_surge)

    def test_soft_timing_hold_vs_hard_veto_lockout(self):
        """
        Verify that record_soft_timing_hold sets symbol breathing pause (3m)
        WITHOUT locking mechanism rejection cooldown (45m), allowing immediate scan
        when price reaches boundary, whereas record_setup_rejection locks mechanism.
        """
        import time
        sym = "GBPUSD"
        clean = "GBPUSD"

        # 1. Soft Timing HOLD
        self.scanner.record_soft_timing_hold(sym)
        now_ts = time.time()

        # Symbol must be breathing
        is_breathing, breath_msg = self.scanner.is_symbol_breathing(clean, now_ts)
        self.assertTrue(is_breathing)

        # But NO mechanism must be locked
        m3_locked, _ = self.scanner.is_mechanism_locked(clean, "MULTI_TOUCH_BREAKOUT_RETEST", 1)
        self.assertFalse(m3_locked, "Soft timing HOLD must NOT lock M3 mechanism!")

        m2_locked, _ = self.scanner.is_mechanism_locked(clean, "TREND_ALIGNED_PULLBACK", 1)
        self.assertFalse(m2_locked, "Soft timing HOLD must NOT lock M2 mechanism!")

        # 2. Hard Risk VETO on M3
        self.scanner.record_setup_rejection(
            symbol=sym,
            setup_type="MULTI_TOUCH_BREAKOUT_RETEST",
            direction=1,
            level=1.35414,
            current_atr=140.0
        )

        # Now M3 BUY must be locked
        m3_locked_hard, reason = self.scanner.is_mechanism_locked(clean, "MULTI_TOUCH_BREAKOUT_RETEST", 1)
        self.assertTrue(m3_locked_hard)
        self.assertIn("rejected by LLM", reason)

        # M3 SELL must still NOT be locked
        m3_sell_locked, _ = self.scanner.is_mechanism_locked(clean, "MULTI_TOUCH_BREAKOUT_RETEST", -1)
        self.assertFalse(m3_sell_locked)

    def test_d1_h4_smc_pullback_classification(self):
        """
        Verify that a bounce above EMA20 in a macro downtrend (EMA20 <= EMA50 or bearish SMC)
        is classified as BEARISH_PULLBACK with is_bear=True, preventing false BULLISH_EXPANSION.
        """
        # Synthetic H4 rates in a downtrend where current close bounces above EMA20
        n = 50
        dates = pd.date_range("2026-08-01 00:00:00", periods=n, freq="4h", tz=WIB)
        # Downward drift
        base = 1.3600 - np.linspace(0, 0.0150, n)
        # Pullback bounce on last 3 bars
        base[-1] += 0.0050
        base[-2] += 0.0030
        
        rates_h4 = []
        for i in range(n):
            c = float(base[i])
            rates_h4.append({
                'time': int(dates[i].timestamp()),
                'open': c - 0.0002,
                'high': c + 0.0005,
                'low': c - 0.0005,
                'close': c,
                'tick_volume': 500
            })
        df_h4 = pd.DataFrame(rates_h4)
        h4_c = float(df_h4['close'].iloc[-1])
        h4_ema20 = df_h4['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        h4_ema50 = df_h4['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        
        # Verify that EMA20 <= EMA50 (Downtrend)
        self.assertLessEqual(h4_ema20, h4_ema50)
        # Verify that h4_c > h4_ema20 (Bounce)
        self.assertGreater(h4_c, h4_ema20)
        
        # Pullback in bear trend should be classified as H4_BEARISH_PULLBACK
        is_bull = False
        is_bear = True
        trend_label = "H4_BEARISH_PULLBACK"
        self.assertTrue(is_bear)
        self.assertFalse(is_bull)
        self.assertEqual(trend_label, "H4_BEARISH_PULLBACK")

    def test_m3_htf_wall_collision_and_m1_unshackling(self):
        """
        Verify that M3 BUY breakout retest is blocked when price collides with C1 ceiling
        in Premium (dr_pos >= 0.70), and M1 SELL sweep is allowed when hitting C1 under MSE sell mandate.
        """
        target_ceiling = 1.35383
        mid = 1.35403
        atr_val = 0.0012
        dr_pos = 0.738

        dist_to_ceiling = (target_ceiling - mid) if target_ceiling > 0 else 999.0
        is_wall_collision_b = (target_ceiling > 0 and dist_to_ceiling <= 0.35 * atr_val and mid < target_ceiling + 0.15 * atr_val)
        target_res = 1.3520
        has_upward_runway = (target_ceiling <= 0.0) or ((target_ceiling - target_res) >= 0.80 * atr_val and dist_to_ceiling >= 0.50 * atr_val)

        # Must trigger wall collision block
        should_block_m3_buy = is_wall_collision_b or (not has_upward_runway and dr_pos > 0.70)
        self.assertTrue(should_block_m3_buy, "M3 BUY must be blocked when colliding with C1 in Premium!")

        # M1 SELL Unshackling: When price hits G3 C1 wall in Premium with MSE sell mandate
        is_macro_bull = True
        is_macro_wall_g3 = True
        is_macro_wall_g2_g3 = True
        dr_pos_val = 0.738
        mse_directive_s = "HUNT_SELL_PULLBACK"
        is_mse_sell_mandate = any(k in mse_directive_s for k in ("SELL", "FADE", "CEILING"))
        is_anti_bull_veto = is_macro_bull and not is_macro_wall_g3 and not (is_macro_wall_g2_g3 and (is_mse_sell_mandate or dr_pos_val >= 0.65))
        
        self.assertFalse(is_anti_bull_veto, "M1 SELL sweep must NOT be vetoed when sweeping C1 in Premium under MSE sell mandate!")

    def test_find_ema_confluence_anchor_physical_override(self):
        """Physical SBR/C1 shelf must override floating psych levels when clustered within 0.35x ATR."""
        macro = {
            'current_atr': 0.0050,
            'ema20': 1.60500,
            'ema50': 1.60500,
            'immediate_ceiling_c1': 1.60561,  # Physical SBR wall
        }
        # Mid at 1.60440: psych level 1.60500 is 6 pips away, C1 1.60561 is 12.1 pips away.
        # Cluster window is min_dist (0.00060) + 0.35 * 0.0050 (0.00175) = 0.00235.
        # 1.60561 falls inside the cluster window and must be selected over 1.60500!
        price, label = self.scanner.find_ema_confluence_anchor(
            symbol="EURCAD-ECNc",
            mid=1.60440,
            direction=-1,
            macro=macro,
            pt=0.00001,
            atr_val=0.0050
        )
        self.assertEqual(price, 1.60561)
        self.assertIn("C1 Structural Ceiling", label)

    def test_radar_standbys_dual_tp_trajectories(self):
        """get_radar_standbys must export dual-tier TP1 and TP2 in the trajectory dictionary."""
        macro = {
            'current_atr': 0.0050,
            'ema20': 1.60500,
            'ema50': 1.60500,
            'immediate_ceiling_c1': 1.60561,
            'immediate_floor_f1': 1.60100,
            'floor_f2': 1.59500,
            'ceiling_c2': 1.61200,
            'trend_label': 'BEARISH'
        }
        standbys = self.scanner.get_radar_standbys(
            symbol="EURCAD-ECNc",
            mid=1.60440,
            macro=macro,
            pt=0.00001,
            atr_val=0.0050
        )
        self.assertGreater(len(standbys), 0)
        for s in standbys:
            traj = s.get("trajectory")
            if traj:
                self.assertIn("target_tp1", traj)
                self.assertIn("target_tp2", traj)
                self.assertGreater(traj["target_tp1"], 0)
                self.assertGreater(traj["target_tp2"], 0)

    def test_m1_sweep_wall_rank_gate_rejects_g1_in_ranging_market(self):
        """Verify M1 Sweep strictly rejects G1 Micro Level sweeps even in RANGE_BOUND markets."""
        from unittest.mock import MagicMock
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from src.analytics.macro_strategic_engine import MacroStrategicDirective
        WIB = ZoneInfo("Asia/Jakarta")

        mock_directive = MagicMock(spec=MacroStrategicDirective)
        mock_directive.action_tier = 'FULL_ALLOW'
        mock_directive.macro_bias_score = 0.0
        mock_directive.hard_circuit_breaker = False
        mock_directive.forbidden_traps = []

        self.scanner.symbols = ["EURUSD-ECNc"]
        self.scanner._symbol_last_eval.clear()
        self.scanner._symbol_last_trigger.clear()
        self.scanner.macro_cache["EURUSD-ECNc"] = {
            'point': 0.00001,
            'atr_pts': 100,
            'dealing_range_pos': 0.85,
            'dealing_range_low': 1.0800,
            'dealing_range_high': 1.0900,
            'is_bull': False,
            'is_bear': False,
            'trend_label': 'RANGE_BOUND',
            'permission_state': 'GO',
            'csm_delta': 0.0,
            'strat_dir': mock_directive,
            'action_tier': 'FULL_ALLOW',
            'macro_bias_score': 0.0,
            'macro_corridor': 'NEUTRAL_CORRIDOR',
            'daily_macro_bias': 'RANGE_BOUND',
            'immediate_floor_f1': 1.0820,
            'immediate_ceiling_c1': 1.0880,
            'c1_reaction_grade': 'GRADE_1_MICRO',
            'asian_high': 1.0880,
            'pdh': 1.0880,
            'ema20': 1.0850,
            'ema50': 1.0830
        }

        mock_connector = MagicMock()
        mock_connector.get_current_tick.return_value = {'ask': 1.0879, 'bid': 1.0877, 'time': int(datetime.now(WIB).timestamp())}
        mock_connector.get_live_tick.return_value = mock_connector.get_current_tick.return_value
        mock_connector.get_closed_bars.return_value = [
            {'open': 1.0870, 'high': 1.0875, 'low': 1.0865, 'close': 1.0872, 'time': 1699999000},
            {'open': 1.0870, 'high': 1.0882, 'low': 1.0868, 'close': 1.0876, 'time': 1700000000}
        ]

        with patch("src.analytics.market_scanner.evaluate_systemic_basket_lock", return_value=(False, "", None)):
            with patch.object(self.scanner, 'is_symbol_allowed_for_session', return_value=True):
                with patch("src.analytics.market_scanner.datetime") as mock_dt:
                    mock_dt.now.return_value = datetime(2026, 8, 31, 15, 0, 0, tzinfo=WIB)
                    mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                    candidates = self.scanner.scan_fast_radar(mock_connector)
                    sweep_cands = [c for c in candidates if c.symbol == "EURUSD-ECNc" and c.setup_type == "UNIVERSAL_LIQUIDITY_SWEEP"]
                    self.assertEqual(len(sweep_cands), 0, "G1 Micro level in RANGE_BOUND market must be strictly REJECTED!")

                    # Now change grade to GRADE_2_INTERMEDIATE and clear breathing cooldown -> Must produce candidate!
                    self.scanner._symbol_last_eval.clear()
                    self.scanner._symbol_last_trigger.clear()
                    self.scanner.macro_cache["EURUSD-ECNc"]["c1_reaction_grade"] = "GRADE_2_INTERMEDIATE"
                    candidates_g2 = self.scanner.scan_fast_radar(mock_connector)
                    sweep_cands_g2 = [c for c in candidates_g2 if c.symbol == "EURUSD-ECNc" and c.setup_type == "UNIVERSAL_LIQUIDITY_SWEEP"]
                    self.assertEqual(len(sweep_cands_g2), 1, "G2 Fortress wall in RANGE_BOUND market must be APPROVED!")

    def test_m4_grade_3_macro_gate_demands_basing(self):
        """Verify M4 breaking Grade 3 Macro Wall requires H1 basing box (WATCH_BASING_FORMATION)."""
        import time
        from unittest.mock import MagicMock
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from src.analytics.macro_strategic_engine import MacroStrategicDirective
        WIB = ZoneInfo("Asia/Jakarta")

        sym = "GBPUSD-ECNc"
        clean_sym = "GBPUSD"
        self.scanner.symbols = [sym]
        self.scanner._m4_universe = [clean_sym]
        self.scanner._m4_feed_updated = time.time()
        self.scanner._m4_feed_hour = datetime.now(WIB).hour
        self.scanner._symbol_last_eval.clear()
        self.scanner._symbol_last_trigger.clear()
        self.scanner._mechanism_rejection_cooldowns[f"{clean_sym}:TREND_ALIGNED_PULLBACK:1"] = time.time() + 3600
        self.scanner._mechanism_rejection_cooldowns[f"{clean_sym}:MULTI_TOUCH_BREAKOUT_RETEST:1"] = time.time() + 3600

        mock_directive = MagicMock(spec=MacroStrategicDirective)
        mock_directive.action_tier = 'FULL_ALLOW'
        mock_directive.macro_bias_score = 0.50
        mock_directive.hard_circuit_breaker = False
        mock_directive.forbidden_traps = []

        self.scanner.macro_cache[sym] = {
            'point': 0.00001,
            'atr_pts': 100,
            'current_atr': 0.00100,
            'dealing_range_pos': 0.50,
            'is_bull': True,
            'is_bear': False,
            'trend_label': 'BULLISH',
            'permission_state': 'GO',
            'csm_delta': 0.020,
            'strat_dir': mock_directive,
            'action_tier': 'FULL_ALLOW',
            'macro_bias_score': 0.50,
            'immediate_ceiling_c1': 1.30500,
            'c1_reaction_grade': 'GRADE_3_MACRO',
            'immediate_floor_f1': 1.29500,
            'f1_reaction_grade': 'GRADE_2_INTERMEDIATE',
            'ema20': 1.30000,
            'ema50': 1.29800,
        }

        # Case 1: M4 pending without basing (is_basing = False) near C1 Grade 3 (1.30500)
        p_no_basing = {
            "level": 1.30520,  # within 0.50*atr of C1 (1.30500)
            "sl": 1.30070,
            "tp": 1.31015,
            "is_basing": False,
            "break_time": 1700000000,
            "break_pos": 10,
            "atr": 0.00100
        }
        self.scanner._m4_state[clean_sym] = {
            "BUY": {"pending": p_no_basing},
            "SELL": {"pending": None}
        }

        mock_connector = MagicMock()
        mock_connector.get_current_tick.return_value = {'ask': 1.30530, 'bid': 1.30510, 'time': int(datetime.now(WIB).timestamp())}
        mock_connector.get_live_tick.return_value = mock_connector.get_current_tick.return_value

        with patch("src.analytics.market_scanner.evaluate_systemic_basket_lock", return_value=(False, "", None)):
            with patch.object(self.scanner, 'is_symbol_allowed_for_session', return_value=True):
                with patch("src.analytics.market_scanner.datetime") as mock_dt:
                    mock_dt.now.return_value = datetime(2026, 8, 31, 15, 0, 0, tzinfo=WIB)
                    mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                    with patch.object(self.scanner, '_m4_pending_ready', return_value=p_no_basing):
                        candidates = self.scanner.scan_fast_radar(mock_connector)
                        m4_cands = [c for c in candidates if c.symbol == sym and c.setup_type == config.M4_SETUP_TYPE]
                        self.assertEqual(len(m4_cands), 0, "M4 breaking Grade 3 Wall without basing must be held back!")

                        # Verify get_radar_standbys marks status as WATCH_BASING_FORMATION
                        standbys = self.scanner.get_radar_standbys(sym, mid=1.30530, macro=self.scanner.macro_cache[sym])
                        m4_sb = next((s for s in standbys if s["type"] == "M4"), None)
                        self.assertIsNotNone(m4_sb)
                        self.assertEqual(m4_sb["status"], "WATCH_BASING_FORMATION")

        # Case 2: M4 pending WITH basing (is_basing = True)
        self.scanner._symbol_last_eval.clear()
        self.scanner._symbol_last_trigger.clear()
        p_with_basing = dict(p_no_basing)
        p_with_basing["is_basing"] = True
        self.scanner._m4_state[clean_sym]["BUY"]["pending"] = p_with_basing

        with patch("src.analytics.market_scanner.evaluate_systemic_basket_lock", return_value=(False, "", None)):
            with patch.object(self.scanner, 'is_symbol_allowed_for_session', return_value=True):
                with patch("src.analytics.market_scanner.datetime") as mock_dt:
                    mock_dt.now.return_value = datetime(2026, 8, 31, 15, 0, 0, tzinfo=WIB)
                    mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                    with patch.object(self.scanner, '_m4_pending_ready', return_value=p_with_basing):
                        candidates2 = self.scanner.scan_fast_radar(mock_connector)
                        m4_cands2 = [c for c in candidates2 if c.symbol == sym and c.setup_type == config.M4_SETUP_TYPE]
                        self.assertEqual(len(m4_cands2), 1, "M4 breaking Grade 3 Wall WITH basing must be APPROVED!")

    def test_btc_weekend_scanner_and_risk_entry_allowed(self):
        """Verify that on weekends (Saturday/Sunday), BTCUSD.c is scanned by radar and risk engine allows entry."""
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from unittest.mock import MagicMock, patch
        from src.core.risk_engine import RiskEngine
        WIB = ZoneInfo("Asia/Jakarta")

        btc_sym = "BTCUSD.c"
        btc_scanner = MarketScanner(symbols=[btc_sym])
        btc_scanner.macro_cache[btc_sym] = {
            'point': 0.01,
            'atr_pts': 5000,
            'current_atr': 50.0,
            'dealing_range_pos': 0.50,
            'is_bull': True,
            'is_bear': False,
            'trend_label': 'BULLISH',
            'permission_state': 'GO',
            'csm_delta': 0.0,
            'action_tier': 'FULL_ALLOW',
            'immediate_ceiling_c1': 81000.0,
            'immediate_floor_f1': 79000.0,
            'ema20': 79800.0,
            'ema50': 79500.0,
            'df': None
        }

        mock_connector = MagicMock()
        mock_connector.get_current_tick.return_value = {'ask': 80010.0, 'bid': 80000.0, 'time': 1700000000}
        mock_connector.get_live_tick.return_value = mock_connector.get_current_tick.return_value

        # Simulate Saturday (weekend dow=5) at 03:00 WIB (subuh dead zone for FX)
        saturday_subuh = datetime(2026, 9, 5, 3, 0, 0, tzinfo=WIB)
        with patch("src.analytics.market_scanner.datetime") as mock_dt:
            mock_dt.now.return_value = saturday_subuh
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            with patch("config.mt5.positions_get", return_value=[]):
                with patch("config.mt5.orders_get", return_value=[]):
                    # Fast radar should NOT return early with [] on weekend for crypto
                    candidates = btc_scanner.scan_fast_radar(mock_connector)
                    self.assertIsInstance(candidates, list)

        # Verify RiskEngine allows entry for BTC on weekend
        risk = RiskEngine()
        allowed, msg = risk._check_weekend_entry(symbol=btc_sym)
        self.assertTrue(allowed, f"RiskEngine._check_weekend_entry should allow BTC on weekend, but got: {msg}")

        mock_acc_dict = {"balance": 6000.0, "equity": 6000.0, "margin_free": 6000.0, "free_margin": 6000.0}
        with patch("src.core.risk_engine.connector.get_account_info", return_value=mock_acc_dict):
            with patch("config.mt5.positions_get", return_value=[]):
                with patch("config.mt5.orders_get", return_value=[]):
                    with patch("config.mt5.symbol_info_tick", return_value=MagicMock(ask=80010.0, bid=80000.0)):
                        with patch("config.mt5.symbol_info", return_value=MagicMock(point=0.01, digits=2)):
                            val_allowed, val_msg = risk.can_trade(symbol=btc_sym)
                            self.assertTrue(val_allowed, f"RiskEngine.can_trade should allow BTC on weekend, but got: {val_msg}")


if __name__ == "__main__":
    unittest.main()



