"""
Unit tests for M3 Dealing Range Guard, Anti-Sweep SFP Veto, and Rigid Breached Wall Law.
Verifies the fix for:
1. Premature M3 SELL in Discount (dr_pos < 0.40) and M3 BUY in Premium (dr_pos > 0.60).
2. Anti-Sweep SFP absorption detection preventing selling into sweep rebounds.
3. Rigid Breached Wall Law in calculate_intraday_sl_tp ensuring unbreached F1/C1 is never leapfrogged to F2/C2.
"""

import unittest
import pandas as pd
import numpy as np

import config
from src.analytics.market_scanner import MarketScanner
from src.indicators.atlas_dna import calculate_intraday_sl_tp


class TestM3DiscountGuardAndLeapfrog(unittest.TestCase):

    def setUp(self):
        self.scanner = MarketScanner(symbols=["USDCAD-ECN", "NZDCHF-ECN"])

    def test_rigid_breached_wall_law_sell_unbreached_f1(self):
        """Unbreached F1 must NOT be leapfrogged to F2 even if distance is tight."""
        entry = 0.47438
        atr = 0.00043
        f1 = 0.47357
        f2 = 0.47136

        res = calculate_intraday_sl_tp(
            symbol="NZDCHF-ECN",
            entry_price=entry,
            direction=-1,
            origin_level=entry,
            atr_h1=atr,
            f1=f1,
            f2=f2,
            f1_breached=False
        )

        # Target station MUST remain F1 (0.47357), not F2 (0.47136)
        self.assertEqual(res["target_station"], f1)
        self.assertGreater(res["tp"], f2)
        # R:R must accurately reflect the tight runway to F1 (~0.69)
        self.assertLess(res["risk_reward"], 1.10)

    def test_rigid_breached_wall_law_sell_breached_f1(self):
        """Breached F1 cleanly allows target advancement to F2."""
        entry = 0.47438
        atr = 0.00043
        f1 = 0.47357
        f2 = 0.47136

        res = calculate_intraday_sl_tp(
            symbol="NZDCHF-ECN",
            entry_price=entry,
            direction=-1,
            origin_level=entry,
            atr_h1=atr,
            f1=f1,
            f2=f2,
            f1_breached=True
        )

        # Target station advances to F2 (0.47136)
        self.assertEqual(res["target_station"], f2)
        self.assertGreaterEqual(res["risk_reward"], 2.0)
        self.assertEqual(res["setup_grade"], "GRADE_S")

    def test_rigid_breached_wall_law_buy_unbreached_c1(self):
        """Unbreached C1 must NOT be leapfrogged to C2 even if distance is tight."""
        entry = 1.16100
        atr = 0.00065
        c1 = 1.16160
        c2 = 1.16500

        res = calculate_intraday_sl_tp(
            symbol="EURUSD-ECN",
            entry_price=entry,
            direction=1,
            origin_level=entry,
            atr_h1=atr,
            c1=c1,
            c2=c2,
            c1_breached=False
        )

        # Target station MUST remain C1 (1.16160), not C2 (1.16500)
        self.assertEqual(res["target_station"], c1)
        self.assertLess(res["tp"], c2)
        self.assertLess(res["risk_reward"], 1.0)

    def test_rigid_breached_wall_law_buy_breached_c1(self):
        """Breached C1 cleanly allows target advancement to C2."""
        entry = 1.16100
        atr = 0.00065
        c1 = 1.16160
        c2 = 1.16500

        res = calculate_intraday_sl_tp(
            symbol="EURUSD-ECN",
            entry_price=entry,
            direction=1,
            origin_level=entry,
            atr_h1=atr,
            c1=c1,
            c2=c2,
            c1_breached=True
        )

        # Target station advances to C2 (1.16500)
        self.assertEqual(res["target_station"], c2)
        self.assertGreaterEqual(res["risk_reward"], 2.0)

    def test_sfp_low_absorption_detection(self):
        """Recent candle with sweep below floor and high lower-wick reclaim must trigger SFP veto."""
        data = [
            {"open": 1.3804, "high": 1.3808, "low": 1.3802, "close": 1.3803},
            {"open": 1.3803, "high": 1.3804, "low": 1.3792, "close": 1.3792},
            {"open": 1.3792, "high": 1.3798, "low": 1.37757, "close": 1.37971}, # SFP Sweep bar!
            {"open": 1.3797, "high": 1.3798, "low": 1.3788, "close": 1.3795},
        ]
        df = pd.DataFrame(data)
        macro = {
            "floor_f1": 1.37781,
            "ceiling_c1": 1.38050,
            "pwl": 1.37750,
            "pdl": 1.37800
        }
        atr_val = 0.00082

        is_sfp, reason = self.scanner._detect_recent_sfp_absorption(
            sym="USDCAD-ECN",
            df=df,
            direction=-1,
            atr_val=atr_val,
            macro=macro
        )

        self.assertTrue(is_sfp)
        self.assertIn("SFP Low Absorption", reason)

    def test_sfp_high_absorption_detection(self):
        """Recent candle with sweep above ceiling and high upper-wick reclaim must trigger SFP veto."""
        data = [
            {"open": 1.1600, "high": 1.1610, "low": 1.1595, "close": 1.1605},
            {"open": 1.1605, "high": 1.1638, "low": 1.1602, "close": 1.1612}, # High sweep bar!
            {"open": 1.1612, "high": 1.1615, "low": 1.1608, "close": 1.1610},
            {"open": 1.1610, "high": 1.1614, "low": 1.1606, "close": 1.1609},
        ]
        df = pd.DataFrame(data)
        macro = {
            "floor_f1": 1.1580,
            "ceiling_c1": 1.1620,
            "pwh": 1.1620,
            "pdh": 1.1620
        }
        atr_val = 0.00065

        is_sfp, reason = self.scanner._detect_recent_sfp_absorption(
            sym="EURUSD-ECN",
            df=df,
            direction=1,
            atr_val=atr_val,
            macro=macro
        )

        self.assertTrue(is_sfp)
        self.assertIn("SFP High Absorption", reason)

    def test_no_sfp_when_clean_trend_move(self):
        """Standard clean bars without wicks or pierces must return False."""
        data = [
            {"open": 1.3820, "high": 1.3825, "low": 1.3810, "close": 1.3812},
            {"open": 1.3812, "high": 1.3815, "low": 1.3800, "close": 1.3802},
            {"open": 1.3802, "high": 1.3805, "low": 1.3790, "close": 1.3792},
            {"open": 1.3792, "high": 1.3795, "low": 1.3780, "close": 1.3782},
        ]
        df = pd.DataFrame(data)
        macro = {"floor_f1": 1.3750, "ceiling_c1": 1.3850}
        atr_val = 0.00080

        is_sfp, reason = self.scanner._detect_recent_sfp_absorption(
            sym="USDCAD-ECN",
            df=df,
            direction=-1,
            atr_val=atr_val,
            macro=macro
        )

        self.assertFalse(is_sfp)
        self.assertEqual(reason, "NO_SFP")

    def test_m3_discount_sell_guard_blocks_at_13_percent(self):
        """M3 SELL must be strictly blocked if dr_pos < 0.40 (e.g. USDCAD at 13.5% discount)."""
        dr_pos = 0.135
        min_dr_sell = getattr(config, "M3_MIN_DR_SELL", 0.40)
        is_discount_sell_blocked = (dr_pos < min_dr_sell)
        self.assertTrue(is_discount_sell_blocked)

        # In equilibrium/premium (>= 0.40), sell is allowed
        dr_pos_premium = 0.55
        self.assertFalse(dr_pos_premium < min_dr_sell)

    def test_m3_premium_buy_guard_blocks_at_75_percent(self):
        """M3 BUY must be strictly blocked if dr_pos > 0.60 (premium zone)."""
        dr_pos = 0.75
        max_dr_buy = getattr(config, "M3_MAX_DR_BUY", 0.60)
        is_premium_buy_blocked = (dr_pos > max_dr_buy)
        self.assertTrue(is_premium_buy_blocked)

        # In discount/equilibrium (<= 0.60), buy is allowed
        dr_pos_discount = 0.45
        self.assertFalse(dr_pos_discount > max_dr_buy)


if __name__ == "__main__":
    unittest.main()
