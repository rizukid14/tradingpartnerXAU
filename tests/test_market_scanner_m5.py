import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

import config
from src.analytics.market_scanner import CandidateSetup
from src.analytics.market_scanner_m5 import MarketScannerM5, calculate_m5_sl_tp


class TestMarketScannerM5(unittest.TestCase):

    def test_calculate_m5_sl_tp_buy(self):
        # EURUSD BUY at 1.10000, M5 ATR = 0.00050 (5 pips), C1 at 1.10200 (20 pips), F1 at 1.09800 (20 pips)
        res = calculate_m5_sl_tp(
            symbol="EURUSD-ECNc",
            entry_price=1.10000,
            direction=1,
            atr_m5=0.00050,
            c1=1.10200,
            f1=1.09800,
            spread_pts=10,
            pt=0.00001
        )
        self.assertLess(res["sl"], 1.10000)
        self.assertGreater(res["tp"], 1.10000)
        self.assertGreaterEqual(res["sl_pts"], 45)
        self.assertLessEqual(res["sl_pts"], 120)
        self.assertGreaterEqual(res["risk_reward"], 1.0)

    def test_calculate_m5_sl_tp_sell(self):
        # GBPUSD SELL at 1.35000, M5 ATR = 0.00060 (6 pips), C1 at 1.35200 (20 pips), F1 at 1.34800 (20 pips)
        res = calculate_m5_sl_tp(
            symbol="GBPUSD-ECNc",
            entry_price=1.35000,
            direction=-1,
            atr_m5=0.00060,
            c1=1.35200,
            f1=1.34800,
            spread_pts=12,
            pt=0.00001
        )
        self.assertGreater(res["sl"], 1.35000)
        self.assertLess(res["tp"], 1.35000)
        self.assertGreaterEqual(res["sl_pts"], 45)
        self.assertLessEqual(res["sl_pts"], 120)
        self.assertGreaterEqual(res["risk_reward"], 1.0)

    def test_scanner_m5_initialization(self):
        scanner = MarketScannerM5(symbols=["EURUSD-ECNc", "GBPUSD-ECNc"])
        self.assertEqual(len(scanner.symbols), 2)
        self.assertIn("M5", scanner._micro_zce_params["grid"])
        self.assertIn("M15", scanner._micro_zce_params["grid"])
        self.assertIn("H1", scanner._micro_zce_params["grid"])

    def test_m5_pending_expiration_and_bep(self):
        # M5 Pending order expiration must be 20 minutes
        with patch.object(config, "TIMEFRAME_STR", "M5"):
            exp_mins = config.get_pending_order_expiry_minutes()
            self.assertEqual(exp_mins, 20)

        # BEP trigger ratio must be 0.80 for M5
        self.assertEqual(getattr(config, "BREAK_EVEN_TRIGGER_TP_PCT", 0.0), 0.80)
        self.assertFalse(getattr(config, "TRAILING_STOP_ENABLED", True))
        self.assertFalse(getattr(config, "PARTIAL_CLOSE_ENABLED", True))

    def test_m5_cooldowns(self):
        self.assertEqual(getattr(config, "POST_LOSS_COOLDOWN_SECONDS", 0), 600)
        self.assertEqual(getattr(config, "SCANNER_MECHANISM_REJECTION_COOLDOWN_SECONDS", 0), 600)
        self.assertEqual(getattr(config, "PENDING_ORDER_CANCEL_COOLDOWN_SECONDS", 0), 600)

    def test_m5_pending_cancel_cooldown_lock(self):
        scanner = MarketScannerM5(symbols=["EURUSD-ECNc"])
        sym = "EURUSD-ECNc"
        scanner.mark_symbol_cancelled(sym, cooldown_seconds=600, reason="Test 75% TP Runaway")
        is_locked, msg = scanner.is_symbol_cancel_locked(sym)
        self.assertTrue(is_locked)
        self.assertIn("10m", msg)


    def test_xau_btc_quarantined_to_paper_trade(self):
        # XAUUSD and BTCUSD must strictly be paper trade only (quarantined from MT5 live execution)
        self.assertTrue(config.is_paper_only("XAUUSD-ECNc"))
        self.assertTrue(config.is_paper_only("BTCUSD.c"))
        self.assertFalse(config.is_paper_only("EURUSD-ECNc"))
        self.assertFalse(config.is_paper_only("GBPUSD-ECNc"))
    def test_m5_sl_less_than_tp_and_thin_jpy(self):
        # GBPJPY M5 scalping must have thin SL (not 250 pts H1 floor) and SL < TP (R:R >= 1.25)
        pt = 0.001
        atr_m5 = 0.077
        res = calculate_m5_sl_tp(
            symbol="GBPJPY-ECNc",
            entry_price=208.551,
            direction=1,
            atr_m5=atr_m5,
            spread_pts=11,
            pt=pt
        )
        self.assertLess(res["sl_pts"], res["tp_pts"])
        self.assertGreaterEqual(res["risk_reward"], 1.25)
        # Verify SL is thin (around 90-100 pts), NOT clamped to 250 pts H1 floor
        self.assertLess(res["sl_pts"], 150)

    def test_pure_demo_atr_sl(self):
        # GBPJPY JPY tier: SL is purely proportional to M5 ATR (1.25x ATR), NOT stretched by distant C1
        # atr_m5 = 0.070 (7 pips) -> 1.25 * 70 pts = 88 pts
        res_near = calculate_m5_sl_tp(
            symbol="GBPJPY-ECNc",
            entry_price=190.000,
            direction=-1,
            atr_m5=0.070,
            c1=190.115,
            spread_pts=12,
            pt=0.001
        )
        self.assertEqual(res_near["sl_pts"], 88)
        self.assertLess(res_near["sl_pts"], 120)

        # Far C1 at 190.250 (25.0 pips away) -> SL remains strictly 88 pts (pure ATR, fast-in fast-out)
        res_far = calculate_m5_sl_tp(
            symbol="GBPJPY-ECNc",
            entry_price=190.000,
            direction=-1,
            atr_m5=0.070,
            c1=190.250,
            spread_pts=12,
            pt=0.001
        )
        self.assertEqual(res_far["sl_pts"], 88)

    def test_nzd_low_beta_atr_scaling(self):
        # NZDCHF low-beta Pacific cross with tight M5 ATR (1.3 pips = 13 pts)
        # SL must scale to thin volatility (~30-60 pts), NOT clamped to 80-100 pts Major FX floor
        res = calculate_m5_sl_tp(
            symbol="NZDCHF-ECNc",
            entry_price=0.47200,
            direction=1,
            atr_m5=0.00013,
            c1=0.47300,
            f1=0.47160,
            spread_pts=10,
            pt=0.00001
        )
        self.assertLess(res["sl_pts"], 70)
        self.assertGreaterEqual(res["sl_pts"], 30)
        self.assertGreaterEqual(res["risk_reward"], 1.25)

    def test_fast_fallback_tp_when_cramped(self):
        # Entry at 0.47270 is right under C1 (0.47280) - only 10 pts headroom
        # Instead of artificial limit re-anchoring, pure demo triggers fast fallback TP (1.75x SL)
        res = calculate_m5_sl_tp(
            symbol="NZDCHF-ECNc",
            entry_price=0.47270,
            direction=1,
            atr_m5=0.00013,
            c1=0.47280,
            f1=0.47160,
            spread_pts=10,
            pt=0.00001
        )
        self.assertFalse(res["is_reanchored_limit"])
        self.assertEqual(res["limit_entry_price"], 0.47270)
        self.assertGreater(res["tp"], 0.47270)
        self.assertGreaterEqual(res["risk_reward"], 1.25)

    def test_single_ticket_scalp_geometry(self):
        # Single ticket scalping: has_runner is False and tp_runner equals tp
        res = calculate_m5_sl_tp(
            symbol="EURUSD-ECNc",
            entry_price=1.10000,
            direction=1,
            atr_m5=0.00050,
            c1=1.10200,
            f1=1.09800,
            c2=1.10450,
            spread_pts=10,
            pt=0.00001
        )
        self.assertFalse(res["has_runner"])
        self.assertEqual(res["tp_runner"], res["tp"])
        self.assertGreaterEqual(res["risk_reward"], 1.25)

    def test_micro_zce_3tf_grid(self):
        scanner = MarketScannerM5(symbols=["EURUSD-ECNc"])
        grid = scanner._micro_zce_params["grid"]
        self.assertIn("M5", grid)
        self.assertIn("M15", grid)
        self.assertNotIn("M30", grid)
        self.assertIn("H1", grid)
        self.assertEqual(grid["H1"], [50, 100, 200])

    def test_m5_dealing_range_and_metadata_sync(self):
        scanner = MarketScannerM5(symbols=["GBPAUD-ECNc"])
        
        # Test candidate metadata synchronization
        cand = CandidateSetup(
            symbol="GBPAUD-ECNc",
            setup_type="TREND_ALIGNED_PULLBACK",
            direction=-1,
            trigger_price=1.89157,
            timeframe="M5",
            macro_compass="BEAR",
            dealing_range_pos=0.66,
            rejection_wick_ratio=0.25,
            current_spread_pts=6,
            current_atr_pts=45,
            suggested_sl=1.89434,
            suggested_tp=1.89084,
            risk_reward_ratio=1.5,
            metadata={"entry_type": "market", "entry_price": 1.89157}
        )
        
        # Reanchoring override
        geom = {
            "sl": 1.89434,
            "tp": 1.89084,
            "tp_runner": 1.88800,
            "risk_reward": 1.5,
            "is_reanchored_limit": True,
            "limit_entry_price": 1.89294,
            "sl_pts": 140,
            "tp_pts": 210,
            "tp1_pts": 210,
            "tp2_pts": 315,
            "has_runner": True
        }
        
        if geom.get("is_reanchored_limit"):
            cand.trigger_price = geom["limit_entry_price"]
            cand.order_type = "SELL_LIMIT"
            
        cand.metadata["entry_price"] = cand.trigger_price
        cand.metadata["entry_type"] = getattr(cand, "order_type", "market")
        
        self.assertEqual(cand.trigger_price, 1.89294)
        self.assertEqual(cand.metadata["entry_price"], 1.89294)
        self.assertEqual(cand.metadata["entry_type"], "SELL_LIMIT")


if __name__ == "__main__":
    unittest.main()

