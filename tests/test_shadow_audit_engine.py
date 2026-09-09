"""
test_shadow_audit_engine.py — Unit Test Suite for Quant Shadow Executive Audit Engine.
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta

from src.analytics.shadow_audit_engine import (
    ShadowAuditEngine,
    compute_wilson_ci
)


class TestShadowAuditEngine(unittest.TestCase):

    def test_compute_wilson_ci(self):
        # 1. Zero trades
        p, low, high = compute_wilson_ci(0, 0)
        self.assertEqual(p, 0.0)
        self.assertEqual(low, 0.0)
        self.assertEqual(high, 0.0)

        # 2. 70 wins out of 100 trades
        p, low, high = compute_wilson_ci(70, 100)
        self.assertEqual(p, 70.0)
        self.assertTrue(low < 70.0 < high)
        self.assertTrue(55.0 <= low <= 65.0)
        self.assertTrue(75.0 <= high <= 85.0)

        # 3. 100% win rate on 10 trades
        p, low, high = compute_wilson_ci(10, 10)
        self.assertEqual(p, 100.0)
        self.assertTrue(low < 100.0)
        self.assertEqual(high, 100.0)

    def test_debiasing_overlap_consolidation(self):
        engine = ShadowAuditEngine()

        t0 = datetime(2026, 9, 8, 23, 0, 0)
        # 3 overlapping trades on CHFJPY SELL
        synthetic_trades = [
            {
                "shadow_id": "T1",
                "symbol": "CHFJPY-ECN",
                "direction": "SELL",
                "setup_type": "UNIVERSAL_LIQUIDITY_SWEEP",
                "entry_price": 190.50,
                "sl_price": 191.00,
                "tp_price": 189.50,
                "created_at": (t0).isoformat(),
                "resolved_time": (t0 + timedelta(minutes=60)).isoformat(),
                "status": "RESOLVED",
                "outcome": "BEP_HIT",
                "net_r": 0.06,
                "peak_mfe_r": 0.45,
                "max_mae_r": -0.15,
                "mt5_disposition": "SKIPPED_MAX_POSITIONS"
            },
            {
                "shadow_id": "T2",
                "symbol": "CHFJPY-ECN",
                "direction": "SELL",
                "setup_type": "TREND_ALIGNED_PULLBACK",
                "entry_price": 190.45,
                "sl_price": 191.00,
                "tp_price": 189.50,
                "created_at": (t0 + timedelta(minutes=5)).isoformat(),
                "resolved_time": (t0 + timedelta(minutes=60)).isoformat(),
                "status": "RESOLVED",
                "outcome": "TP_HIT",
                "net_r": 1.90,
                "peak_mfe_r": 1.90,
                "max_mae_r": -0.20,
                "mt5_disposition": "EXECUTED_MT5"
            },
            {
                "shadow_id": "T3",
                "symbol": "CHFJPY-ECN",
                "direction": "SELL",
                "setup_type": "UNIVERSAL_LIQUIDITY_SWEEP",
                "entry_price": 190.40,
                "sl_price": 191.00,
                "tp_price": 189.50,
                "created_at": (t0 + timedelta(minutes=35)).isoformat(),
                "resolved_time": (t0 + timedelta(minutes=60)).isoformat(),
                "status": "RESOLVED",
                "outcome": "BEP_HIT",
                "net_r": 0.06,
                "peak_mfe_r": 0.60,
                "max_mae_r": -0.10,
                "mt5_disposition": "SKIPPED_MAX_POSITIONS"
            },
            # 1 non-overlapping trade on another pair
            {
                "shadow_id": "T4",
                "symbol": "EURUSD-ECN",
                "direction": "BUY",
                "setup_type": "TREND_ALIGNED_PULLBACK",
                "entry_price": 1.1620,
                "sl_price": 1.1600,
                "tp_price": 1.1660,
                "created_at": (t0).isoformat(),
                "resolved_time": (t0 + timedelta(minutes=45)).isoformat(),
                "status": "RESOLVED",
                "outcome": "TP_HIT",
                "net_r": 2.00,
                "peak_mfe_r": 2.00,
                "max_mae_r": -0.05,
                "mt5_disposition": "EXECUTED_MT5"
            }
        ]

        debiased_legs = engine.consolidate_debiased_legs(synthetic_trades)
        # Should consolidate the 3 CHFJPY trades into 1 leg, plus 1 EURUSD leg -> total 2 legs
        self.assertEqual(len(debiased_legs), 2)

        chf_leg = next(l for l in debiased_legs if l["symbol"] == "CHFJPY-ECN")
        self.assertEqual(chf_leg["ticket_count"], 3)
        self.assertEqual(chf_leg["mt5_disposition"], "EXECUTED_MT5")
        self.assertEqual(chf_leg["outcome"], "TP_HIT")
        self.assertEqual(chf_leg["peak_mfe_r"], 1.90)
        self.assertEqual(chf_leg["max_mae_r"], -0.20)
        # Expected average net R: (0.06 + 1.90 + 0.06) / 3 = 0.67R
        self.assertAlmostEqual(chf_leg["net_r"], 0.67, places=2)

    def test_compute_analytics_metrics(self):
        engine = ShadowAuditEngine()
        sample_trades = [
            {"shadow_id": "S1", "status": "RESOLVED", "outcome": "TP_HIT", "net_r": 1.5, "setup_type": "M2_PULLBACK", "mt5_disposition": "EXECUTED_MT5", "max_mae_r": -0.2, "peak_mfe_r": 1.5, "risk_reward": 1.5},
            {"shadow_id": "S2", "status": "RESOLVED", "outcome": "SL_HIT", "net_r": -1.0, "setup_type": "M2_PULLBACK", "mt5_disposition": "EXECUTED_MT5", "max_mae_r": -1.0, "peak_mfe_r": 0.1, "risk_reward": 1.5},
            {"shadow_id": "S3", "status": "RESOLVED", "outcome": "TP_HIT", "net_r": 2.0, "setup_type": "M1_SWEEP", "mt5_disposition": "SKIPPED_MAX_POSITIONS", "max_mae_r": -0.3, "peak_mfe_r": 2.0, "risk_reward": 2.0},
            {"shadow_id": "S4", "status": "RESOLVED", "outcome": "SL_HIT", "net_r": -1.0, "setup_type": "M1_SWEEP", "mt5_disposition": "SKIPPED_MAX_POSITIONS", "max_mae_r": -1.0, "peak_mfe_r": 0.2, "risk_reward": 1.5},
            {"shadow_id": "S5", "status": "RESOLVED", "outcome": "BEP_HIT", "net_r": 0.1, "setup_type": "M3_BREAKOUT", "mt5_disposition": "SKIPPED_ANCHOR_TOO_WIDE", "max_mae_r": -0.9, "peak_mfe_r": 0.5, "risk_reward": 1.5},
        ]

        metrics = engine.compute_analytics(sample_trades)
        self.assertEqual(metrics["total_resolved"], 5)
        self.assertEqual(metrics["tp_count"], 2)
        self.assertEqual(metrics["sl_count"], 2)
        self.assertEqual(metrics["bep_count"], 1)
        self.assertEqual(metrics["winrate_pct"], 50.0)
        self.assertEqual(metrics["cumulative_net_r"], 1.6)

        # Opportunity cost: S3 (+2.0), S4 (-1.0), S5 (+0.1) -> net skipped = +1.1R
        self.assertEqual(metrics["lost_profit_r"], 1.1)
        self.assertEqual(metrics["capital_saved_r"], 1.0)

        # BEP efficiency: S5 had MAE -0.9 <= -0.85 -> saved by BEP
        self.assertEqual(metrics["bep_saved_count"], 1)
        self.assertEqual(metrics["bep_stolen_count"], 0)
        self.assertEqual(metrics["bep_efficiency_pct"], 100.0)

    def test_render_html_dashboard(self):
        engine = ShadowAuditEngine()
        # Mock minimal records
        engine.raw_resolved = [
            {"shadow_id": "TEST1", "symbol": "EURUSD-ECN", "direction": "BUY", "setup_type": "TREND_ALIGNED_PULLBACK",
             "entry_price": 1.16, "sl_price": 1.158, "tp_price": 1.164, "status": "RESOLVED", "outcome": "TP_HIT",
             "net_r": 2.0, "peak_mfe_r": 2.0, "max_mae_r": -0.2, "mt5_disposition": "EXECUTED_MT5",
             "created_at": datetime.now().isoformat(), "resolved_time": datetime.now().isoformat()}
        ]

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tf:
            temp_out = tf.name

        try:
            rendered_path = engine.render_html_dashboard(output_path=temp_out)
            self.assertTrue(os.path.exists(rendered_path))
            with open(rendered_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Quant Shadow Executive Audit", content)
            self.assertIn("AUDIT_DATA", content)
            self.assertIn("Chart.js", content)
            self.assertIn("EURUSD-ECN", content)
        finally:
            if os.path.exists(temp_out):
                os.remove(temp_out)


if __name__ == "__main__":
    unittest.main()
