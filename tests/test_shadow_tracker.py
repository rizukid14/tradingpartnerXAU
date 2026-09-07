"""
Unit tests for QuantShadowTracker (Unconstrained Data Collector).
Verifies:
1. Registration of market and pending shadow orders.
2. Deduplication guard against rapid spam triggers.
3. Pending limit fill detection when price touches entry.
4. Target Proximity Expiration (>=75% move without fill).
5. MFE & MAE excursion tracking.
6. TP Hit (+R) and SL Hit (-1.0R) resolutions.
7. State persistence and performance summary statistics.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo

from src.analytics.shadow_tracker import QuantShadowTracker, ShadowTrade, SHADOW_STATE_FILE, SHADOW_TRADES_LOG
from src.analytics.market_scanner import CandidateSetup
import config

WIB = ZoneInfo("Asia/Jakarta")


class TestQuantShadowTracker(unittest.TestCase):

    def setUp(self):
        # Create a fresh temporary directory for testing state and log files
        self.test_dir = tempfile.mkdtemp()
        self.orig_state_file = SHADOW_STATE_FILE
        self.orig_log_file = SHADOW_TRADES_LOG
        self.orig_prox = getattr(config, "ENABLE_SHADOW_PROXIMITY_CANCEL", True)
        config.ENABLE_SHADOW_PROXIMITY_CANCEL = True

        import src.analytics.shadow_tracker as st_module
        st_module.SHADOW_STATE_FILE = os.path.join(self.test_dir, "test_shadow_state.json")
        st_module.SHADOW_TRADES_LOG = os.path.join(self.test_dir, "test_shadow_trades.jsonl")

        # Reset singleton instance
        QuantShadowTracker._instance = None
        self.tracker = QuantShadowTracker()

    def tearDown(self):
        config.ENABLE_SHADOW_PROXIMITY_CANCEL = self.orig_prox
        import src.analytics.shadow_tracker as st_module
        st_module.SHADOW_STATE_FILE = self.orig_state_file
        st_module.SHADOW_TRADES_LOG = self.orig_log_file
        QuantShadowTracker._instance = None
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _make_candidate(self, symbol="EURUSD-ECN", direction=1, setup_type="MULTI_TOUCH_BREAKOUT_RETEST"):
        return CandidateSetup(
            symbol=symbol,
            setup_type=setup_type,
            direction=direction,
            trigger_price=1.10000,
            suggested_sl=1.09800,
            suggested_tp=1.10400,
            risk_reward_ratio=2.0,
            current_spread_pts=15,
            current_atr_pts=250.0
        )

    def test_register_market_order(self):
        cand = self._make_candidate(direction=1)
        trade = self.tracker.register_candidate(
            candidate=cand,
            entry_type="market",
            entry_price=1.10000,
            sl_price=1.09800,
            tp_price=1.10400,
            sl_points=200,
            tp_points=400,
            mt5_disposition="EXECUTED_MT5",
            mt5_ticket=123456
        )

        self.assertIsNotNone(trade)
        self.assertEqual(trade.status, "ACTIVE")
        self.assertIsNotNone(trade.fill_time)
        self.assertEqual(trade.risk_reward, 2.0)
        self.assertEqual(trade.mt5_ticket, 123456)
        self.assertEqual(len(self.tracker.active_trades), 1)

    def test_register_pending_order_and_deduplication(self):
        cand = self._make_candidate(direction=1)
        trade1 = self.tracker.register_candidate(
            candidate=cand,
            entry_type="buy_limit",
            entry_price=1.09900,
            sl_price=1.09700,
            tp_price=1.10300,
            sl_points=200,
            tp_points=400,
            mt5_disposition="SKIPPED_SLOT_FULL"
        )
        self.assertIsNotNone(trade1)
        self.assertEqual(trade1.status, "PENDING")
        self.assertIsNone(trade1.fill_time)
        self.assertEqual(trade1.mt5_disposition, "SKIPPED_SLOT_FULL")

        # Second identical candidate should be deduplicated (return None)
        trade2 = self.tracker.register_candidate(
            candidate=cand,
            entry_type="buy_limit",
            entry_price=1.09900,
            sl_price=1.09700,
            tp_price=1.10300,
            sl_points=200,
            tp_points=400
        )
        self.assertIsNone(trade2)
        self.assertEqual(len(self.tracker.active_trades), 1)

    def test_pending_to_active_fill(self):
        cand = self._make_candidate(direction=1)
        trade = self.tracker.register_candidate(
            candidate=cand,
            entry_type="buy_limit",
            entry_price=1.09900,
            sl_price=1.09700,
            tp_price=1.10300,
            sl_points=200,
            tp_points=400
        )

        mock_connector = MagicMock()
        # Price is above entry: not filled yet
        mock_connector.get_current_tick.return_value = {"ask": 1.10050, "bid": 1.10035, "point": 0.00001}
        res = self.tracker.update_shadow_orders(mock_connector)
        self.assertEqual(len(res), 0)
        self.assertEqual(self.tracker.active_trades[0].status, "PENDING")

        # Price drops and touches entry: fills!
        mock_connector.get_current_tick.return_value = {"ask": 1.09895, "bid": 1.09880, "point": 0.00001}
        res = self.tracker.update_shadow_orders(mock_connector)
        self.assertEqual(len(res), 0)
        self.assertEqual(self.tracker.active_trades[0].status, "ACTIVE")
        self.assertIsNotNone(self.tracker.active_trades[0].fill_time)

    def test_target_proximity_expiration(self):
        cand = self._make_candidate(direction=1)
        # Entry 1.09900, TP 1.10300 (range 400 pts). 75% progress = 1.09900 + 300 pts = 1.10200
        self.tracker.register_candidate(
            candidate=cand,
            entry_type="buy_limit",
            entry_price=1.09900,
            sl_price=1.09700,
            tp_price=1.10300,
            sl_points=200,
            tp_points=400
        )

        mock_connector = MagicMock()
        # Price moves to 1.10220 without filling limit
        mock_connector.get_current_tick.return_value = {"ask": 1.10225, "bid": 1.10220, "point": 0.00001}
        resolved = self.tracker.update_shadow_orders(mock_connector)

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].outcome, "EXPIRED_NO_FILL")
        self.assertEqual(resolved[0].net_r, 0.0)
        self.assertEqual(len(self.tracker.active_trades), 0)

    def test_tp_hit_and_mfe_tracking(self):
        cand = self._make_candidate(direction=1)
        self.tracker.register_candidate(
            candidate=cand,
            entry_type="market",
            entry_price=1.10000,
            sl_price=1.09800,
            tp_price=1.10400,
            sl_points=200,
            tp_points=400
        )

        mock_connector = MagicMock()
        # Price rises partially (+1.0R)
        mock_connector.get_current_tick.return_value = {"ask": 1.10200, "bid": 1.10200, "point": 0.00001}
        self.tracker.update_shadow_orders(mock_connector)
        self.assertEqual(self.tracker.active_trades[0].peak_mfe_r, 1.0)

        # Price hits TP
        mock_connector.get_current_tick.return_value = {"ask": 1.10410, "bid": 1.10405, "point": 0.00001}
        resolved = self.tracker.update_shadow_orders(mock_connector)

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].outcome, "TP_HIT")
        self.assertEqual(resolved[0].net_r, 2.0)
        self.assertEqual(len(self.tracker.active_trades), 0)

        # Check performance summary
        summary = self.tracker.get_performance_summary()
        self.assertEqual(summary["total_resolved"], 1)
        self.assertEqual(summary["tp_hits"], 1)
        self.assertEqual(summary["winrate_pct"], 100.0)
        self.assertEqual(summary["cumulative_net_r"], 2.0)

    def test_sl_hit_and_mae_tracking(self):
        cand = self._make_candidate(direction=-1, setup_type="UNIVERSAL_LIQUIDITY_SWEEP")
        # SELL: Entry 1.10000, SL 1.10200, TP 1.09600
        self.tracker.register_candidate(
            candidate=cand,
            entry_type="market",
            entry_price=1.10000,
            sl_price=1.10200,
            tp_price=1.09600,
            sl_points=200,
            tp_points=400
        )

        mock_connector = MagicMock()
        # Price moves adverse (up to 1.10150, -0.75R)
        mock_connector.get_current_tick.return_value = {"ask": 1.10150, "bid": 1.10150, "point": 0.00001}
        self.tracker.update_shadow_orders(mock_connector)
        self.assertEqual(self.tracker.active_trades[0].max_mae_r, -0.75)

        # Price hits SL (ask >= 1.10200)
        mock_connector.get_current_tick.return_value = {"ask": 1.10205, "bid": 1.10200, "point": 0.00001}
        resolved = self.tracker.update_shadow_orders(mock_connector)

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].outcome, "SL_HIT")
        self.assertEqual(resolved[0].net_r, -1.0)
        self.assertEqual(len(self.tracker.active_trades), 0)

        summary = self.tracker.get_performance_summary()
        self.assertEqual(summary["sl_hits"], 1)
        self.assertEqual(summary["cumulative_net_r"], -1.0)

    def test_risk_block_disposition_and_get_all_resolved_trades(self):
        cand = self._make_candidate(symbol="NZDUSD-ECN", direction=1, setup_type="SYSTEMIC_FLOW_CONTINUATION")
        trade = self.tracker.register_candidate(
            candidate=cand,
            entry_type="market",
            entry_price=0.72000,
            sl_price=0.71800,
            tp_price=0.72400,
            sl_points=200,
            tp_points=400,
            mt5_disposition="SKIPPED_RISK_BASKET"
        )
        self.assertIsNotNone(trade)
        self.assertEqual(trade.mt5_disposition, "SKIPPED_RISK_BASKET")

        summary = self.tracker.get_performance_summary()
        self.assertEqual(summary["disposition_breakdown"]["SKIPPED_RISK_BASKET"], 1)

        # Resolve it
        mock_connector = MagicMock()
        mock_connector.get_current_tick.return_value = {"ask": 0.72410, "bid": 0.72405, "point": 0.00001}
        self.tracker.update_shadow_orders(mock_connector)

        resolved_list = self.tracker.get_all_resolved_trades()
        self.assertEqual(len(resolved_list), 1)
        self.assertEqual(resolved_list[0]["symbol"], "NZDUSD-ECN")
        self.assertEqual(resolved_list[0]["mt5_disposition"], "SKIPPED_RISK_BASKET")

    def test_floating_pnl_and_live_price_tracking(self):
        cand = self._make_candidate(direction=1)
        # BUY: entry 1.10000, sl 1.09800 (200 pts), tp 1.10400 (400 pts)
        self.tracker.register_candidate(
            candidate=cand,
            entry_type="market",
            entry_price=1.10000,
            sl_price=1.09800,
            tp_price=1.10400,
            sl_points=200,
            tp_points=400
        )
        mock_connector = MagicMock()
        # Price is at 1.10100 (+100 pts, +0.50R)
        mock_connector.get_current_tick.return_value = {"ask": 1.10105, "bid": 1.10095, "point": 0.00001, "digits": 5}
        self.tracker.update_shadow_orders(mock_connector)

        trade = self.tracker.active_trades[0]
        self.assertEqual(trade.current_price, 1.10100)
        self.assertEqual(trade.floating_points, 100)
        self.assertEqual(trade.floating_r, 0.50)

    def test_mt5_ticket_reconciliation_on_closed_deal(self):
        cand = self._make_candidate(direction=1)
        self.tracker.register_candidate(
            candidate=cand,
            entry_type="market",
            entry_price=1.10000,
            sl_price=1.09800,
            tp_price=1.10400,
            sl_points=200,
            tp_points=400,
            mt5_disposition="EXECUTED_MT5",
            mt5_ticket=999888
        )
        mock_deal = MagicMock()
        mock_deal.entry = 1
        mock_deal.price = 1.10350
        mock_deal.profit = 85.50
        mock_deal.comment = "[tp 1.10350]"
        mock_deal._asdict.return_value = {
            "entry": 1,
            "price": 1.10350,
            "profit": 85.50,
            "comment": "[tp 1.10350]"
        }

        from unittest.mock import patch
        with patch.object(config.mt5, "positions_get", return_value=[]):
            with patch.object(config.mt5, "history_deals_get", return_value=[mock_deal]):
                mock_connector = MagicMock()
                mock_connector.get_current_tick.return_value = {"ask": 1.10300, "bid": 1.10290, "point": 0.00001}
                resolved = self.tracker.update_shadow_orders(mock_connector)

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].outcome, "TP_HIT")
        self.assertEqual(resolved[0].exit_price, 1.10350)
        self.assertEqual(resolved[0].net_r, 1.75)

    def test_virtual_bep_activation_and_hit(self):
        cand = self._make_candidate(direction=1)
        # BUY: entry 1.10000, sl 1.09800 (risk 200 pts), tp 1.10400 (400 pts)
        self.tracker.register_candidate(
            candidate=cand,
            entry_type="market",
            entry_price=1.10000,
            sl_price=1.09800,
            tp_price=1.10400,
            sl_points=200,
            tp_points=400
        )
        mock_connector = MagicMock()
        # Price moves up to 1.10110 (+110 pts, +0.55R) -> BEP triggers (+15 pts above entry -> 1.10015)
        mock_connector.get_current_tick.return_value = {"ask": 1.10115, "bid": 1.10105, "point": 0.00001, "digits": 5}
        self.tracker.update_shadow_orders(mock_connector)

        trade = self.tracker.active_trades[0]
        self.assertTrue(trade.bep_activated)
        self.assertEqual(trade.current_sl, 1.10015)

        # Price pulls back to 1.10010 (below current_sl 1.10015)
        mock_connector.get_current_tick.return_value = {"ask": 1.10010, "bid": 1.10005, "point": 0.00001, "digits": 5}
        resolved = self.tracker.update_shadow_orders(mock_connector)

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].outcome, "BEP_HIT")
        self.assertGreaterEqual(resolved[0].net_r, 0.0)
        self.assertEqual(resolved[0].exit_price, 1.10015)

    def test_virtual_trailing_stop_activation_and_hit(self):
        cand = self._make_candidate(direction=1)
        # BUY: entry 1.10000, sl 1.09800 (risk 200 pts), tp 1.10400 (400 pts)
        self.tracker.register_candidate(
            candidate=cand,
            entry_type="market",
            entry_price=1.10000,
            sl_price=1.09800,
            tp_price=1.10400,
            sl_points=200,
            tp_points=400
        )
        mock_connector = MagicMock()
        # Price surges to 1.10200 (+200 pts, +1.00R, like EURUSD today)
        # Trailing triggers: current_sl = entry + (1.00 - 0.40) * 0.00200 = 1.10120 (+0.60R)
        mock_connector.get_current_tick.return_value = {"ask": 1.10205, "bid": 1.10195, "point": 0.00001, "digits": 5}
        self.tracker.update_shadow_orders(mock_connector)

        trade = self.tracker.active_trades[0]
        self.assertTrue(trade.bep_activated)
        self.assertTrue(trade.trailing_activated)
        self.assertEqual(trade.current_sl, 1.10120)

        # Price pulls back and hits trailing SL (ask <= 1.10120)
        mock_connector.get_current_tick.return_value = {"ask": 1.10115, "bid": 1.10110, "point": 0.00001, "digits": 5}
        resolved = self.tracker.update_shadow_orders(mock_connector)

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].outcome, "TRAILING_SL_HIT")
        self.assertEqual(resolved[0].net_r, 0.60)
        self.assertEqual(resolved[0].exit_price, 1.10120)

        summary = self.tracker.get_performance_summary()
        self.assertEqual(summary["cumulative_net_r"], 0.60)


if __name__ == "__main__":
    unittest.main()
