"""Unit tests for Institutional Quant Decision Surveillance Cockpit (dashboard.py)."""
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dashboard


class TestDashboardCockpit(unittest.TestCase):
    def test_session_name_detection(self):
        wib = ZoneInfo("Asia/Jakarta")
        self.assertEqual(dashboard._get_session_name(datetime(2026, 9, 4, 3, 30, tzinfo=wib)), "DEAD_ZONE")
        self.assertEqual(dashboard._get_session_name(datetime(2026, 9, 4, 9, 0, tzinfo=wib)), "TOKYO")
        self.assertEqual(dashboard._get_session_name(datetime(2026, 9, 4, 15, 0, tzinfo=wib)), "LONDON")
        self.assertEqual(dashboard._get_session_name(datetime(2026, 9, 4, 20, 0, tzinfo=wib)), "OVERLAP")
        self.assertEqual(dashboard._get_session_name(datetime(2026, 9, 4, 23, 15, tzinfo=wib)), "LATE_NY")

    def test_countdown_to_rollover(self):
        wib = ZoneInfo("Asia/Jakarta")
        dt = datetime(2026, 9, 4, 2, 50, 0, tzinfo=wib)
        self.assertEqual(dashboard._get_countdown_to_rollover(dt), "1h 00m")

    def test_consolidate_zce_zones_empty(self):
        res = dashboard._consolidate_zce_zones(None, 1.0, 0.5, 1.5, 0.01, 0.0001, 5)
        self.assertEqual(res, [])

    def test_cockpit_data_engine_init(self):
        engine = dashboard.CockpitDataEngine()
        self.assertFalse(engine._is_running)
        self.assertIsNone(engine.scanner)
        self.assertEqual(engine.cached_overview, {})
        self.assertEqual(engine.cached_symbol_data, {})

    def test_radar_standbys_trajectory_and_confluence(self):
        import pandas as pd
        from src.analytics.market_scanner import MarketScanner
        scanner = MarketScanner()

        # Mock EURJPY H1 data: breakdown 10 bars ago at 181.719, then rebound back to 181.719
        times = pd.date_range('2026-09-04 00:00', periods=25, freq='h')
        closes = [182.200]*10 + [181.200]*10 + [181.710]*5
        df = pd.DataFrame({'close': closes, 'high': [c + 0.10 for c in closes], 'low': [c - 0.10 for c in closes], 'open': closes}, index=times)

        macro = {
            'df': df,
            'is_bear': True,
            'current_atr': 0.35,
            'immediate_ceiling_c1': 181.719,
            'immediate_floor_f1': 181.426,
            'cluster_support': 0.0,
            'touches_support': 0
        }

        standbys = scanner.get_radar_standbys("EURJPY", mid=181.650, macro=macro, pt=0.001, atr_val=0.35)
        m3_list = [s for s in standbys if s["type"] == "M3"]
        self.assertTrue(len(m3_list) > 0)
        m3 = m3_list[0]

        # Verify trajectory object exists
        self.assertIn("trajectory", m3)
        traj = m3["trajectory"]
        self.assertEqual(traj["direction"], -1) # SELL
        self.assertEqual(traj["retest_price"], 181.719)
        self.assertEqual(traj["target_price"], 181.426)
        self.assertTrue(traj["origin_age"] > 0)
        self.assertTrue(traj["origin_time"] > 0)

        # Check confluence fusion if M2 is also near 181.719
        m2_list = [s for s in standbys if s["type"] == "M2"]
        if m2_list and abs(m2_list[0]["price"] - 181.719) <= 0.35 * 0.35:
            self.assertTrue(m3.get("is_confluence", False))
            self.assertIn("CONFLUENCE", m3.get("confluence_label", ""))

    def test_m1_standbys_trajectory(self):
        """M1A sweep standby must export a trajectory dictionary for visual chart projection."""
        import pandas as pd
        from src.analytics.market_scanner import MarketScanner
        scanner = MarketScanner()

        times = pd.date_range('2026-09-08 00:00', periods=20, freq='h')
        closes = [1.35200]*10 + [1.35520]*5 + [1.35500]*5
        highs = [c + 0.00100 for c in closes]
        lows = [c - 0.00100 for c in closes]
        df = pd.DataFrame({'close': closes, 'high': highs, 'low': lows, 'open': closes}, index=times)

        macro = {
            'df': df,
            'is_bear': False,
            'is_bull': True,
            'current_atr': 0.00125,
            'dealing_range_pos': 0.85,
            'immediate_ceiling_c1': 1.35525,
            'immediate_floor_f1': 1.35402,
            'asian_high': 1.35498,
            'pdh': 1.35498,
        }

        standbys = scanner.get_radar_standbys("GBPUSD", mid=1.35506, macro=macro, pt=0.00001, atr_val=0.00125)
        m1_list = [s for s in standbys if s["type"] == "M1"]
        self.assertTrue(len(m1_list) > 0)
        m1 = m1_list[0]

        # Verify trajectory object exists in M1
        self.assertIn("trajectory", m1)
        traj = m1["trajectory"]
        self.assertEqual(traj["direction"], -1) # Bearish Sweep
        self.assertEqual(traj["retest_price"], 1.35498)
        self.assertEqual(traj["target_price"], 1.35402) # F1 target
        self.assertIn("target_tp1", traj)
        self.assertIn("target_tp2", traj)

    def test_gate4_directional_lock_alignment(self):
        """Gate 4 CSM evaluation must respect Directional Lock state (SELL ONLY -> test against SELL)."""
        engine = dashboard.CockpitDataEngine()
        from src.analytics.market_scanner import MarketScanner
        engine.scanner = MarketScanner()

        # Set symbol directional state to SELL ONLY
        engine.scanner._symbol_directional_state["GBPUSD"] = {
            "dir": -1,
            "locked_at": 1788876400.0,
            "reason": "MACRO_BIAS_INIT"
        }

        # Mock macro context where is_bull is True (trend) but CSM delta is +0.89
        engine.scanner.macro_cache["GBPUSD"] = {
            "symbol": "GBPUSD",
            "is_bull": True,
            "is_bear": False,
            "csm_delta": 0.89,
            "action_tier": "FULL_ALLOW",
            "permission_state": "GO",
            "immediate_floor_f1": 1.35402,
            "immediate_ceiling_c1": 1.35525,
            "current_atr": 0.00125,
            "spread_pts": 2
        }

        detail = engine.get_symbol_detail("GBPUSD", "H1")
        gates = {g["id"]: g for g in detail.get("gates", [])}

        # Gate 3 should be SELL ONLY
        self.assertIn("3", [str(k) for k in gates.keys()])
        g3 = gates[3]
        self.assertIn("SELL ONLY", g3["desc"])

        # Gate 4 should align with SELL direction (not BUY)
        self.assertIn("4", [str(k) for k in gates.keys()])
        g4 = gates[4]
        self.assertIn("SELL", g4["reason"])


if __name__ == "__main__":
    unittest.main()


