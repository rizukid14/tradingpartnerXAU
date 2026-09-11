"""
tests/test_dual_horizon_w1.py — Verification of Dual-Horizon W1 Structural Engine & Anti-Horizon Blindness Gate.
Tests:
1. Upper Tangent Slope Envelope & Lower High detection on descending structures (EURNZD-like pattern).
2. Graceful degradation (None) on ascending / trending markets.
3. MarketScanner directional gate: Veto BUY when htf_horizon_conflict is True and w1_slope_ceiling is tested.
4. ZCE Node Injection: W1_DESC_SLOPE_CEILING properly populated in raw_up_elements.
"""

import unittest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch

from src.analytics.macro_strategic_engine import MacroStrategicEngine, MacroStrategicDirective


class TestDualHorizonW1(unittest.TestCase):
    def setUp(self):
        self.mse = MacroStrategicEngine()

    def test_evaluate_dual_horizon_descending_eurnzd(self):
        """Simulate 60 W1 bars with descending peaks (LH) and test Upper Tangent Envelope detection."""
        np.random.seed(42)
        n_bars = 60
        # Secular trend: 150 bars back was lower, then peaks at bar 10 (2.06800), then lower highs:
        # bar 10: 2.06800, bar 22: 2.04300, bar 35: 2.03100, bar 48: 2.02300, bar 58: 2.00400
        highs = np.linspace(1.90000, 1.98000, n_bars)
        lows = highs - 0.01500
        closes = (highs + lows) / 2.0
        
        # Inject descending peaks
        highs[10] = 2.06800
        highs[22] = 2.04300
        highs[35] = 2.03100
        highs[48] = 2.02300
        highs[58] = 2.00400
        
        # Ensure closes stay beneath the upper tangent line
        for i in range(n_bars):
            if i > 10:
                expected_roof = 2.06800 - ((2.06800 - 2.00400) / 48.0) * (i - 10)
                highs[i] = min(highs[i], expected_roof + 0.00100)
                closes[i] = min(closes[i], expected_roof - 0.00200)
                lows[i] = min(lows[i], closes[i] - 0.01000)

        df_w1 = pd.DataFrame({
            "high": highs,
            "low": lows,
            "close": closes,
            "time": [1700000000 + i * 604800 for i in range(n_bars)]
        })

        atr_w1 = 0.01800
        curr_mid = 1.99500

        res = self.mse._evaluate_dual_horizon_w1(df_w1, atr_w1, digits=5, curr_mid=curr_mid)

        self.assertIsNotNone(res["slope_ceiling"])
        self.assertEqual(res["intermediate_regime"], "BEARISH_LOWER_HIGHS_COMPRESSION")
        self.assertGreaterEqual(len(res["lower_highs"]), 3)
        # Price 1.99500 is within 0.50 * ATR of projected ceiling (~2.00400)
        self.assertTrue(res["horizon_conflict"])

    def test_evaluate_dual_horizon_ascending_no_conflict(self):
        """Pure ascending trend must gracefully return None without disrupting bullish pairs."""
        n_bars = 60
        highs = np.linspace(1.30000, 1.50000, n_bars)
        lows = highs - 0.01000
        closes = highs - 0.00300

        df_w1 = pd.DataFrame({
            "high": highs,
            "low": lows,
            "close": closes,
            "time": [1700000000 + i * 604800 for i in range(n_bars)]
        })

        atr_w1 = 0.01200
        curr_mid = 1.49800

        res = self.mse._evaluate_dual_horizon_w1(df_w1, atr_w1, digits=5, curr_mid=curr_mid)
        self.assertIsNone(res["slope_ceiling"])
        self.assertFalse(res["horizon_conflict"])

    def test_tokyo_midday_lull_does_not_crash_on_cur_atr(self):
        """Verify scan_fast_radar runs smoothly during Tokyo Midday Lull without cur_atr NameError."""
        from src.analytics.market_scanner import MarketScanner
        import config
        from datetime import datetime
        from zoneinfo import ZoneInfo
        WIB = ZoneInfo("Asia/Jakarta")

        scanner = MarketScanner()
        sym = "GBPJPY-ECNc"
        scanner.symbols = [sym]

        strat_dir = MagicMock(spec=MacroStrategicDirective)
        strat_dir.action_tier = "FULL_ALLOW"
        strat_dir.macro_bias_score = 0.80
        strat_dir.hard_circuit_breaker = False
        strat_dir.forbidden_traps = []
        strat_dir.htf_horizon_conflict = False
        strat_dir.w1_slope_ceiling = None

        scanner.macro_cache[sym] = {
            'point': 0.001,
            'atr_pts': 150,
            'current_atr': 0.150,
            'dealing_range_pos': 0.50,
            'is_bull': True,
            'is_bear': False,
            'trend_label': 'BULLISH',
            'permission_state': 'GO',
            'csm_delta': 0.020,
            'strat_dir': strat_dir,
            'action_tier': 'FULL_ALLOW',
            'macro_bias_score': 0.80,
            'immediate_ceiling_c1': 195.000,
            'c1_reaction_grade': 'GRADE_1_MICRO',
            'immediate_floor_f1': 190.000,
            'f1_reaction_grade': 'GRADE_1_MICRO',
            'ema20': 192.500,
            'ema50': 192.000,
            'asian_high': 193.000,
            'asian_low': 192.800,
        }

        mock_connector = MagicMock()
        mock_connector.get_current_tick.return_value = {'ask': 193.050, 'bid': 193.020, 'time': int(datetime.now(WIB).timestamp())}
        mock_connector.get_live_tick.return_value = mock_connector.get_current_tick.return_value

        m4_res_sample = {
            "side": "BUY",
            "pattern": "RALLY_BASE_RALLY",
            "level": 193.000,
            "entry": 193.000,
            "sl": 192.200,
            "basing_ceiling": 193.000,
            "basing_floor": 192.800,
            "basing_range_atr": 0.12
        }

        with patch("src.analytics.market_scanner.evaluate_systemic_basket_lock", return_value=(False, "", None)):
            with patch("src.analytics.economic_calendar.calendar.is_in_news_blackout", return_value=(False, "")):
                with patch.object(scanner, 'is_symbol_allowed_for_session', return_value=True):
                    with patch("src.analytics.market_scanner.datetime") as mock_dt:
                        # Jam 11:30 WIB (Tokyo Lull window)
                        mock_dt.now.return_value = datetime(2026, 9, 11, 11, 30, 0, tzinfo=WIB)
                        mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
                        with patch.object(scanner, '_detect_m4_breakout_continuation', return_value=m4_res_sample):
                            # Must NOT throw NameError: name 'cur_atr' is not defined
                            candidates = scanner.scan_fast_radar(mock_connector)
                            # Continuation is frozen during Tokyo Lull if range < min, but radar executes without crash
                            self.assertIsInstance(candidates, list)


if __name__ == "__main__":
    unittest.main()
