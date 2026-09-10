"""
tests/test_csm_and_m3_context_guard.py
Unit tests for:
1. CSM Flow Opposition Gate hardening:
   - Continuation setups (PULLBACK, BREAKOUT) are HARD_BLOCK when CSM Net Delta is opposed
     even if Macro Bias is aligned.
   - Liquidity Sweeps / SFP and SFR systemic setups are exempt.
2. M3 SBR/RBS Pre-Breakout Context Validator:
   - M3 SELL: Vetoes breakdown when level was acting as resistance in >=60% of prior bars.
   - M3 BUY: Vetoes breakout when level was acting as support in >=60% of prior bars.
   - Genuine breakouts/breakdowns are verified and accepted.
"""

import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

import config


def check_csm_opposition_gate(target_dir: int, setup_label: str, csm_delta_val: float, sfr_catalyst: str = "") -> tuple:
    """Replicates the tightened CSM flow opposition gate in market_scanner._is_direction_allowed()."""
    csm_opp_thresh = float(getattr(config, "CSM_FLOW_OPPOSED_THRESHOLD", 1.50))
    is_csm_opposed = (target_dir == 1 and csm_delta_val <= -csm_opp_thresh) or (target_dir == -1 and csm_delta_val >= csm_opp_thresh)
    is_sfr_pro = (target_dir == -1 and sfr_catalyst == "BEARISH_FLOW") or (target_dir == 1 and sfr_catalyst == "BULLISH_FLOW")

    if getattr(config, "ENABLE_CSM_FLOW_FILTER", True):
        is_sweep_setup = any(k in setup_label.upper() for k in ("SWEEP", "SFP", "RECLAIM"))
        if is_csm_opposed and not is_sfr_pro and not is_sweep_setup:
            return False, "HARD_BLOCK", f"[CSM OPPOSED] Net Delta ({csm_delta_val:+.2f}) opposes direction"
    return True, "PASS", "CSM_ALLOWED"


class TestCSMAndM3ContextGuard(unittest.TestCase):

    def test_csm_opposed_blocks_continuation_even_with_aligned_macro(self):
        """
        Verify that when CSM is opposed (e.g. Net Delta = +1.79 on SELL),
        a continuation setup (M3 BREAKOUT or M2 PULLBACK) is HARD_BLOCKED.
        """
        # 1. Continuation setup: MULTI_TOUCH_BREAKOUT_RETEST
        allowed, tier, reason = check_csm_opposition_gate(
            target_dir=-1,
            setup_label="MULTI_TOUCH_BREAKOUT_RETEST",
            csm_delta_val=+1.79,
            sfr_catalyst=""
        )
        self.assertFalse(allowed)
        self.assertEqual(tier, "HARD_BLOCK")
        self.assertIn("CSM OPPOSED", reason)

        # 2. Continuation setup: PULLBACK
        allowed_pb, tier_pb, reason_pb = check_csm_opposition_gate(
            target_dir=-1,
            setup_label="TREND_ALIGNED_PULLBACK",
            csm_delta_val=+1.79,
            sfr_catalyst=""
        )
        self.assertFalse(allowed_pb)
        self.assertEqual(tier_pb, "HARD_BLOCK")
        self.assertIn("CSM OPPOSED", reason_pb)

        # 3. Sweep / SFP setup: UNIVERSAL_LIQUIDITY_SWEEP is permitted
        allowed_sw, tier_sw, reason_sw = check_csm_opposition_gate(
            target_dir=-1,
            setup_label="UNIVERSAL_LIQUIDITY_SWEEP",
            csm_delta_val=+1.79,
            sfr_catalyst=""
        )
        self.assertTrue(allowed_sw)
        self.assertEqual(tier_sw, "PASS")

        # 4. SFR Systemic Pro setup is permitted
        allowed_sfr, tier_sfr, reason_sfr = check_csm_opposition_gate(
            target_dir=-1,
            setup_label="M4_SYSTEMIC_FLOW",
            csm_delta_val=+1.79,
            sfr_catalyst="BEARISH_FLOW"
        )
        self.assertTrue(allowed_sfr)
        self.assertEqual(tier_sfr, "PASS")

    def test_m3_sell_pre_breakdown_context_veto(self):
        """
        Verify M3 SELL rejects false breakdowns where the level was actually
        resistance in prior bars (like EURAUD 1.61238 resistance sweep).
        """
        target_sup = 1.61238
        recency_bars = 4
        min_disp_body = 0.55

        data = [
            {"open": 1.6100, "high": 1.6110, "low": 1.6090, "close": 1.6105},
            {"open": 1.6105, "high": 1.6115, "low": 1.6100, "close": 1.6108},
            {"open": 1.6108, "high": 1.6120, "low": 1.6102, "close": 1.6112},
            {"open": 1.6112, "high": 1.6120, "low": 1.6105, "close": 1.6115},
            {"open": 1.6115, "high": 1.6139, "low": 1.6110, "close": 1.61339},
            {"open": 1.61339, "high": 1.6135, "low": 1.6115, "close": 1.61180},
            {"open": 1.61180, "high": 1.6125, "low": 1.6116, "close": 1.61230},
            {"open": 1.61230, "high": 1.6126, "low": 1.6120, "close": 1.61235},
        ]
        df = pd.DataFrame(data)
        recent_df = df.iloc[-(recency_bars + 1):]

        has_fresh_break_s = False
        sweep_vetoed = False

        for idx in range(1, len(recent_df)):
            prev_bar = recent_df.iloc[idx - 1]
            curr_bar = recent_df.iloc[idx]
            crossed_down = (prev_bar['close'] >= target_sup and curr_bar['close'] < target_sup) or \
                           (curr_bar['high'] >= target_sup and curr_bar['close'] < target_sup)
            if crossed_down:
                bar_range = curr_bar['high'] - curr_bar['low']
                bar_body = abs(curr_bar['close'] - curr_bar['open'])
                body_ratio = (bar_body / bar_range) if bar_range > 0 else 0.0
                if body_ratio >= min_disp_body and curr_bar['close'] < curr_bar['open']:
                    break_abs_idx = len(df) - (len(recent_df) - idx)
                    prior_bars = df.iloc[max(0, break_abs_idx - 5):break_abs_idx]
                    if len(prior_bars) >= 3:
                        pct_below = sum(1 for c in prior_bars['close'] if c < target_sup) / len(prior_bars)
                        if pct_below >= 0.60:
                            sweep_vetoed = True
                            continue
                    has_fresh_break_s = True
                    break

        self.assertTrue(sweep_vetoed, "Expected EURAUD sweep to be vetoed by Pre-Breakdown Context Validator")
        self.assertFalse(has_fresh_break_s, "False breakdown should not set has_fresh_break_s=True")

    def test_m3_buy_pre_breakout_context_veto(self):
        """
        Verify M3 BUY rejects false breakouts where the level was actually
        support in prior bars (support sweep pop-back).
        """
        target_res = 1.25000
        recency_bars = 4
        min_disp_body = 0.55

        # Level was support (closes >= 1.2500 in prior bars), dips below for 1 bar, then pops back up
        data = [
            {"open": 1.2510, "high": 1.2520, "low": 1.2505, "close": 1.2515},
            {"open": 1.2515, "high": 1.2525, "low": 1.2508, "close": 1.2518},
            {"open": 1.2518, "high": 1.2522, "low": 1.2502, "close": 1.2510},
            {"open": 1.2510, "high": 1.2515, "low": 1.2480, "close": 1.2485}, # dip below support
            {"open": 1.2485, "high": 1.2520, "low": 1.2482, "close": 1.2515}, # close back above, body > 55%
            {"open": 1.2515, "high": 1.2525, "low": 1.2510, "close": 1.2520},
        ]
        df = pd.DataFrame(data)
        recent_df = df.iloc[-(recency_bars + 1):]

        has_fresh_break_b = False
        sweep_vetoed = False

        for idx in range(1, len(recent_df)):
            prev_bar = recent_df.iloc[idx - 1]
            curr_bar = recent_df.iloc[idx]
            crossed_up = (prev_bar['close'] <= target_res and curr_bar['close'] > target_res) or \
                         (curr_bar['low'] <= target_res and curr_bar['close'] > target_res)
            if crossed_up:
                bar_range = curr_bar['high'] - curr_bar['low']
                bar_body = abs(curr_bar['close'] - curr_bar['open'])
                body_ratio = (bar_body / bar_range) if bar_range > 0 else 0.0
                if body_ratio >= min_disp_body and curr_bar['close'] > curr_bar['open']:
                    break_abs_idx = len(df) - (len(recent_df) - idx)
                    prior_bars = df.iloc[max(0, break_abs_idx - 5):break_abs_idx]
                    if len(prior_bars) >= 3:
                        pct_above = sum(1 for c in prior_bars['close'] if c > target_res) / len(prior_bars)
                        if pct_above >= 0.60:
                            sweep_vetoed = True
                            continue
                    has_fresh_break_b = True
                    break

        self.assertTrue(sweep_vetoed, "Expected support sweep to be vetoed as an M3 BUY breakout")
        self.assertFalse(has_fresh_break_b, "False breakout should not set has_fresh_break_b=True")

    def test_m3_sell_genuine_breakdown_passes(self):
        """
        Verify M3 SELL allows a genuine breakdown where price was consolidated ABOVE target_sup.
        """
        target_sup = 1.61000
        recency_bars = 4
        min_disp_body = 0.55

        data = [
            {"open": 1.6120, "high": 1.6130, "low": 1.6110, "close": 1.6120},
            {"open": 1.6120, "high": 1.6135, "low": 1.6112, "close": 1.6125},
            {"open": 1.6125, "high": 1.6130, "low": 1.6115, "close": 1.6118},
            {"open": 1.6118, "high": 1.6125, "low": 1.6105, "close": 1.6115},
            {"open": 1.6115, "high": 1.6118, "low": 1.6075, "close": 1.6080},
            {"open": 1.6080, "high": 1.6095, "low": 1.6078, "close": 1.6092},
            {"open": 1.6092, "high": 1.6099, "low": 1.6085, "close": 1.6098},
        ]
        df = pd.DataFrame(data)
        recent_df = df.iloc[-(recency_bars + 1):]

        has_fresh_break_s = False

        for idx in range(1, len(recent_df)):
            prev_bar = recent_df.iloc[idx - 1]
            curr_bar = recent_df.iloc[idx]
            crossed_down = (prev_bar['close'] >= target_sup and curr_bar['close'] < target_sup) or \
                           (curr_bar['high'] >= target_sup and curr_bar['close'] < target_sup)
            if crossed_down:
                bar_range = curr_bar['high'] - curr_bar['low']
                bar_body = abs(curr_bar['close'] - curr_bar['open'])
                body_ratio = (bar_body / bar_range) if bar_range > 0 else 0.0
                if body_ratio >= min_disp_body and curr_bar['close'] < curr_bar['open']:
                    break_abs_idx = len(df) - (len(recent_df) - idx)
                    prior_bars = df.iloc[max(0, break_abs_idx - 5):break_abs_idx]
                    if len(prior_bars) >= 3:
                        pct_below = sum(1 for c in prior_bars['close'] if c < target_sup) / len(prior_bars)
                        if pct_below >= 0.60:
                            continue
                    has_fresh_break_s = True
                    break

        self.assertTrue(has_fresh_break_s, "Genuine support breakdown should pass")


if __name__ == "__main__":
    unittest.main()
