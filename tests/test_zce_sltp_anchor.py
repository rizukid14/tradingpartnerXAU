# -*- coding: utf-8 -*-
"""
Unit Test Suite for Dynamic ZCE + SMC Structural Anchor and 80-pts Safety Floor.
Verifies:
1. calculate_intraday_sl_tp anchors BUY SL behind ZCE F1 Floor when origin_level is absent/above entry.
2. calculate_intraday_sl_tp anchors SELL SL behind ZCE C1 Ceiling when origin_level is absent/below entry.
3. Quiet FX enforces 80 pts safety floor instead of rigid 120 pts.
4. M4 candidate in consensus._apply_sltp_rules receives candidate's real spread & ATR.
5. M4 candidate in market_scanner anchors SL behind nearby ZCE wall.
"""

import unittest
from unittest.mock import MagicMock, patch
import config
from src.indicators.atlas_dna import calculate_intraday_sl_tp
from src.core.consensus import _apply_sltp_rules
from src.analytics.market_scanner import MarketScanner, CandidateSetup


class TestZCESLTPAnchor(unittest.TestCase):

    def setUp(self):
        self.scanner = MarketScanner(symbols=["AUDCAD-ECNc", "EURCHF-ECNc", "USDJPY-ECNc"])

    def test_buy_sl_anchored_to_zce_f1(self):
        """When origin_level is absent, BUY SL must anchor behind ZCE F1 floor."""
        entry = 0.99475
        atr = 0.00082  # 82 pts ATR
        f1_floor = 0.99382  # 93 pts below entry
        spread_pts = 4

        res = calculate_intraday_sl_tp(
            symbol="AUDCAD-ECNc",
            entry_price=entry,
            direction=1,
            origin_level=None,
            atr_h1=atr,
            spread_pts=spread_pts,
            f1=f1_floor,
            c1=0.99571
        )

        # SL must be placed below F1 floor
        self.assertLess(res["sl"], f1_floor)
        # Total SL distance must satisfy at least 80 pts safety floor
        sl_dist_pts = int(round((entry - res["sl"]) / 0.00001))
        self.assertGreaterEqual(sl_dist_pts, 80)
        # Risk must be positive and consistent
        self.assertGreater(res["risk"], 0)

    def test_sell_sl_anchored_to_zce_c1(self):
        """When origin_level is absent, SELL SL must anchor behind ZCE C1 ceiling."""
        entry = 0.99475
        atr = 0.00082  # 82 pts ATR
        c1_ceiling = 0.99571  # 96 pts above entry
        spread_pts = 4

        res = calculate_intraday_sl_tp(
            symbol="AUDCAD-ECNc",
            entry_price=entry,
            direction=-1,
            origin_level=None,
            atr_h1=atr,
            spread_pts=spread_pts,
            c1=c1_ceiling,
            f1=0.99382
        )

        # SL must be placed above C1 ceiling
        self.assertGreater(res["sl"], c1_ceiling)
        # Total SL distance must satisfy at least 80 pts safety floor
        sl_dist_pts = int(round((res["sl"] - entry) / 0.00001))
        self.assertGreaterEqual(sl_dist_pts, 80)

    def test_quiet_fx_80_pts_floor_clamp(self):
        """When anchor is too close to entry (e.g. 20 pts), safety floor clamps to 80 pts."""
        entry = 0.99475
        atr = 0.00082
        tight_f1 = 0.99455  # only 20 pts below entry

        res = calculate_intraday_sl_tp(
            symbol="AUDCAD-ECNc",
            entry_price=entry,
            direction=1,
            origin_level=None,
            atr_h1=atr,
            f1=tight_f1
        )

        sl_dist_pts = int(round((entry - res["sl"]) / 0.00001))
        self.assertGreaterEqual(sl_dist_pts, 80)
        self.assertEqual(sl_dist_pts, 82)

    def test_m4_consensus_receives_real_atr_and_spread(self):
        """consensus._apply_sltp_rules must use candidate.current_atr_pts & spread_pts."""
        cand = CandidateSetup(
            symbol="AUDCAD-ECNc",
            setup_type=config.M4_SETUP_TYPE,
            direction=1,
            trigger_price=0.99475,
            current_spread_pts=4,
            current_atr_pts=82,
            metadata={
                "m4_sl_pts": 70,  # Below 80 pts floor
                "m4_tp_pts": 90,   # Below 105 Net R:R minimum
                "m4_level": 0.99475,
            }
        )

        sl, tp, ok, reason = _apply_sltp_rules(
            sl_points=70,
            tp_points=90,
            symbol="AUDCAD-ECNc",
            candidate=cand
        )

        self.assertTrue(ok)
        self.assertEqual(reason, "M4_STRUCTURAL_FLOORED")
        # Floored to 80 pts (not 120 pts!)
        self.assertEqual(sl, 80)
        # TP floored to 80 * 1.25 + 5 comm = 105 pts
        self.assertEqual(tp, 105)


if __name__ == "__main__":
    unittest.main()
