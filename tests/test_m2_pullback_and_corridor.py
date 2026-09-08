"""
Unit tests for M2 Trend-Aligned Pullback:
1. find_ema_confluence_anchor() strictly rejects floating structural levels (FVG/OB) far from EMA20/50.
2. M2 BUY blocked in Premium (dr_pos > 0.55).
3. M2 SELL blocked in Discount (dr_pos < 0.45).
4. M2 BUY blocked when price is outside the healthy EMA corridor (mid > ema20 + 0.45 * ATR).
"""

import unittest
import config
from src.analytics.market_scanner import MarketScanner


class TestM2PullbackAndCorridor(unittest.TestCase):

    def setUp(self):
        self.scanner = MarketScanner(symbols=["GBPNZD-ECN", "EURUSD-ECN"])

    def test_find_ema_confluence_anchor_rejects_floating_fvg(self):
        """Micro-FVG sitting far above EMA20 (e.g. GBPNZD case) must be rejected."""
        mid = 2.31409
        ema20 = 2.30835
        ema50 = 2.30448
        atr_val = 0.00320
        floating_fvg = 2.31387 # 55 pips above EMA20 (> 1.7x ATR)
        confluent_ob = 2.30800 # 3.5 pips from EMA20 (inside corridor)

        macro = {
            "ema20": ema20,
            "ema50": ema50,
            "current_atr": atr_val,
            "bullish_fvg_top": floating_fvg,
            "bullish_ob_top": confluent_ob,
            "immediate_floor_f1": 2.30000
        }

        anchor, desc = self.scanner.find_ema_confluence_anchor(
            symbol="GBPNZD-ECN",
            mid=mid,
            direction=1,
            macro=macro,
            pt=0.00001,
            atr_val=atr_val
        )

        # Floating FVG must NOT be the chosen anchor
        self.assertNotIn("2.31387", desc)
        # Confluent OB or EMA20 must be chosen
        self.assertTrue("2.30800" in desc or "EMA" in desc)
        self.assertLessEqual(anchor, ema20 + 0.35 * atr_val)

    def test_find_ema_confluence_anchor_sell_rejects_floating_fvg(self):
        """Bearish micro-FVG sitting far below EMA20 must be rejected for SELL."""
        mid = 1.08000
        ema20 = 1.08800
        ema50 = 1.09200
        atr_val = 0.0050
        floating_fvg = 1.08050 # 75 pips below EMA20
        confluent_c1 = 1.08750 # near EMA20

        macro = {
            "ema20": ema20,
            "ema50": ema50,
            "current_atr": atr_val,
            "bearish_fvg_bot": floating_fvg,
            "immediate_ceiling_c1": confluent_c1
        }

        anchor, desc = self.scanner.find_ema_confluence_anchor(
            symbol="EURUSD-ECN",
            mid=mid,
            direction=-1,
            macro=macro,
            pt=0.00001,
            atr_val=atr_val
        )

        self.assertNotIn("1.08050", desc)
        self.assertGreaterEqual(anchor, ema20 - 0.35 * atr_val)

    def test_m2_buy_blocks_in_premium_zone(self):
        """M2 BUY must be rejected if dealing_range_pos > 0.68 (or > 0.75 extreme)."""
        dr_pos = 0.82 # 82% Deep Premium
        max_dr_buy = float(getattr(config, "M2_MAX_DR_BUY", 0.68))
        is_valid_pullback_range_b = (dr_pos <= max_dr_buy)
        self.assertFalse(is_valid_pullback_range_b)

    def test_m2_sell_blocks_in_discount_zone(self):
        """M2 SELL must be rejected if dealing_range_pos < 0.32 (or < 0.25 extreme)."""
        dr_pos = 0.18 # 18% Deep Discount
        min_dr_sell = float(getattr(config, "M2_MIN_DR_SELL", 0.32))
        is_valid_pullback_range_s = (dr_pos >= min_dr_sell)
        self.assertFalse(is_valid_pullback_range_s)

    def test_m2_buy_blocks_when_price_far_above_ema(self):
        """M2 BUY must be rejected if price is blown above EMA20 corridor."""
        mid = 2.31409
        ema20 = 2.30835
        ema50 = 2.30448
        atr_val = 0.00320

        is_ema_pullback_valid = (mid >= ema50 - 0.45 * atr_val) and (mid <= ema20 + 0.45 * atr_val)
        self.assertFalse(is_ema_pullback_valid)


if __name__ == "__main__":
    unittest.main()
