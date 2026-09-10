import unittest
import pandas as pd
import numpy as np
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from src.analytics.market_scanner import MarketScanner


class TestM4BreakoutContinuation(unittest.TestCase):
    def setUp(self):
        self.scanner = MarketScanner()
        config.ENABLE_CSM_FLOW_FILTER = False
        config.M4_ENABLED = True
        config.M4_BASING_MIN_BARS = 3
        config.M4_BASING_MAX_RANGE_ATR = 0.35
        config.M4_DISPLACEMENT_MIN_BODY_PCT = 0.50
        config.M4_LOOKBACK_SWING_BARS = 20

    def test_rbr_bullish_breakout_basing(self):
        """Test Rally-Base-Rally (RBR) detection -> Buy Limit at basing ceiling."""
        # 20 bars ranging between 1.0900 and 1.1000
        opens = [1.0950] * 21
        closes = [1.0960] * 21
        highs = [1.1000] * 21
        lows = [1.0900] * 21

        # Bar 21: Impulsive bullish breakout
        # High: 1.1070, Low: 1.0980, Open: 1.0990, Close: 1.1060 (Body: 0.0070, Range: 0.0090, 77.8%)
        opens.append(1.0990)
        closes.append(1.1060)
        highs.append(1.1070)
        lows.append(1.0980)

        # Bars 22, 23, 24, 25: High-tight basing (range: 1.1040 - 1.1060 = 0.0020 <= 0.35 * 0.0060 = 0.0021)
        for _ in range(4):
            opens.append(1.1045)
            closes.append(1.1055)
            highs.append(1.1060)
            lows.append(1.1040)

        df = pd.DataFrame({
            "open": opens,
            "close": closes,
            "high": highs,
            "low": lows
        })

        macro = {
            "current_atr": 0.0060,
            "point": 0.00001,
            "immediate_ceiling_c1": 1.1150,
            "immediate_floor_f1": 1.0950,
        }

        mid = 1.1055
        res = self.scanner._detect_m4_breakout_continuation(
            sym="EURUSD-ECNc",
            df=df,
            macro=macro,
            mid=mid,
            pt=0.00001,
            digits=5,
            spread_pts=15,
            atr_pts=600
        )

        self.assertIsNotNone(res)
        self.assertEqual(res["side"], "BUY")
        self.assertEqual(res["pattern"], "RALLY_BASE_RALLY")
        self.assertAlmostEqual(res["entry"], 1.1060, places=4)
        self.assertTrue(res["sl"] < res["entry"])
        self.assertLessEqual(res["basing_range_atr"], 0.35)

    def test_dbd_bearish_breakdown_basing(self):
        """Test Drop-Base-Drop (DBD) detection -> Sell Limit at basing floor."""
        # 20 bars ranging between 1.0900 and 1.1000
        opens = [1.0950] * 21
        closes = [1.0940] * 21
        highs = [1.1000] * 21
        lows = [1.0900] * 21

        # Bar 21: Impulsive bearish breakdown
        # High: 1.0920, Low: 1.0830, Open: 1.0910, Close: 1.0840 (Body: 0.0070, Range: 0.0090, 77.8%)
        opens.append(1.0910)
        closes.append(1.0840)
        highs.append(1.0920)
        lows.append(1.0830)

        # Bars 22, 23, 24, 25: Low-tight basing (range: 1.0840 - 1.0860 = 0.0020 <= 0.35 * 0.0060)
        for _ in range(4):
            opens.append(1.0855)
            closes.append(1.0845)
            highs.append(1.0860)
            lows.append(1.0840)

        df = pd.DataFrame({
            "open": opens,
            "close": closes,
            "high": highs,
            "low": lows
        })

        macro = {
            "current_atr": 0.0060,
            "point": 0.00001,
            "immediate_ceiling_c1": 1.0950,
            "immediate_floor_f1": 1.0750,
        }

        mid = 1.0845
        res = self.scanner._detect_m4_breakout_continuation(
            sym="EURUSD-ECNc",
            df=df,
            macro=macro,
            mid=mid,
            pt=0.00001,
            digits=5,
            spread_pts=15,
            atr_pts=600
        )

        self.assertIsNotNone(res)
        self.assertEqual(res["side"], "SELL")
        self.assertEqual(res["pattern"], "DROP_BASE_DROP")
        self.assertAlmostEqual(res["entry"], 1.0840, places=4)
        self.assertTrue(res["sl"] > res["entry"])
        self.assertLessEqual(res["basing_range_atr"], 0.35)

    def test_basing_too_wide_rejected(self):
        """Test rejection when basing range exceeds 0.35x ATR."""
        opens = [1.0950] * 21
        closes = [1.0960] * 21
        highs = [1.1000] * 21
        lows = [1.0900] * 21

        # Breakout bar
        opens.append(1.0990)
        closes.append(1.1060)
        highs.append(1.1070)
        lows.append(1.0980)

        # Basing bars with wide range (0.0040 > 0.35 * 0.0060 = 0.0021)
        for _ in range(4):
            opens.append(1.1030)
            closes.append(1.1070)
            highs.append(1.1070)
            lows.append(1.1030)

        df = pd.DataFrame({
            "open": opens,
            "close": closes,
            "high": highs,
            "low": lows
        })

        macro = {"current_atr": 0.0060, "point": 0.00001}
        res = self.scanner._detect_m4_breakout_continuation(
            sym="EURUSD-ECNc",
            df=df,
            macro=macro,
            mid=1.1055,
            pt=0.00001,
            digits=5,
            spread_pts=15,
            atr_pts=600
        )

        self.assertIsNone(res)

    def test_get_radar_standbys_emits_m4_basing(self):
        """Test get_radar_standbys emits M4 Basing standby and trajectory for dashboard."""
        opens = [1.0950] * 21
        closes = [1.0960] * 21
        highs = [1.1000] * 21
        lows = [1.0900] * 21

        # Breakout bar
        opens.append(1.0990)
        closes.append(1.1060)
        highs.append(1.1070)
        lows.append(1.0980)

        # 4 bars high-tight basing
        for _ in range(4):
            opens.append(1.1045)
            closes.append(1.1055)
            highs.append(1.1060)
            lows.append(1.1040)

        # Give dataframe datetime index
        times = pd.date_range("2026-09-10 12:00", periods=len(opens), freq="1h")
        df = pd.DataFrame({
            "open": opens,
            "close": closes,
            "high": highs,
            "low": lows
        }, index=times)

        macro = {
            "df": df,
            "current_atr": 0.0060,
            "point": 0.00001,
            "immediate_ceiling_c1": 1.1150,
            "immediate_floor_f1": 1.0950,
            "ceiling_c2": 1.1250,
            "floor_f2": 1.0850,
            "spread_pts": 15
        }

        mid = 1.1055
        standbys = self.scanner.get_radar_standbys(
            symbol="EURUSD-ECNc",
            mid=mid,
            macro=macro,
            pt=0.00001,
            atr_val=0.0060
        )

        m4_items = [s for s in standbys if s.get("type") == "M4"]
        self.assertTrue(len(m4_items) >= 1)
        m4_item = m4_items[0]
        self.assertEqual(m4_item["status"], "WAITING_BASING_RETEST")
        self.assertEqual(m4_item["direction"], 1)
        self.assertAlmostEqual(m4_item["price"], 1.1060, places=4)
        self.assertIn("M4 BUY RBR BASING", m4_item["label"])
        self.assertIn("trajectory", m4_item)
        traj = m4_item["trajectory"]
        self.assertEqual(traj["phase"], "WAITING_BASING_RETEST")
        self.assertEqual(traj["direction"], 1)
        self.assertAlmostEqual(traj["retest_price"], 1.1060, places=4)
        self.assertTrue(traj["target_price"] > m4_item["price"])


if __name__ == "__main__":
    unittest.main()

