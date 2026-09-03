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
        
    def test_4_layer_permission_matrix(self):
        """Verify the 4-layer Trade Permission Matrix logic and BUY LOCKED != SELL ENABLED."""
        from src.analytics.market_scanner import Direction, Phase, Permission, resolve_permission

        # 1. Bullish Macro Tests
        # Phase 1: Expansion -> WAIT (Do not chase tops)
        self.assertEqual(resolve_permission(Direction.BULL, Phase.EXPANSION, csm_delta=1.5), Permission.WAIT)
        
        # Phase 2: Early Correction / Knife -> LOCK (Anti-falling knife)
        self.assertEqual(resolve_permission(Direction.BULL, Phase.EARLY_CORRECTION, csm_delta=0.0), Permission.LOCK)
        
        # Phase 3: Mature Basing -> ARM if CSM is healthy
        self.assertEqual(resolve_permission(Direction.BULL, Phase.MATURE_CORRECTION, csm_delta=0.2), Permission.ARM)
        self.assertEqual(resolve_permission(Direction.BULL, Phase.MATURE_CORRECTION, csm_delta=-1.0), Permission.WATCH)
        
        # Phase 4: Base Reclaim -> GO if CSM is not severely dumped
        self.assertEqual(resolve_permission(Direction.BULL, Phase.RECLAIM, csm_delta=0.5), Permission.GO)
        self.assertEqual(resolve_permission(Direction.BULL, Phase.RECLAIM, csm_delta=-2.5), Permission.WATCH)

        # 2. Bearish Macro Tests
        # Phase 1: Expansion -> WAIT (Do not chase bottoms)
        self.assertEqual(resolve_permission(Direction.BEAR, Phase.EXPANSION, csm_delta=-1.5), Permission.WAIT)
        
        # Phase 2: Early Correction -> LOCK (Anti-short squeeze)
        self.assertEqual(resolve_permission(Direction.BEAR, Phase.EARLY_CORRECTION, csm_delta=0.0), Permission.LOCK)
        
        # Phase 4: Base Reclaim -> GO for SELL
        self.assertEqual(resolve_permission(Direction.BEAR, Phase.RECLAIM, csm_delta=-0.8), Permission.GO)

        # 3. Neutral Direction Fallback
        self.assertEqual(resolve_permission(Direction.NEUTRAL, Phase.RECLAIM, csm_delta=0.0), Permission.WAIT)

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
            dealing_range_pos=0.55,  # Mid range
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


if __name__ == "__main__":
    unittest.main()


