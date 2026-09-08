"""
Unit tests for BTCUSD in Dashboard Cockpit & 7-Gate X-Ray Surveillance.
Verifies that:
1. BTCUSD is included in overview pairs list.
2. get_symbol_detail('BTCUSD') calculates proper 7-Gate X-Ray audit without crashes.
3. Gate 1 (dead zone exempt), Gate 2 (fiat basket exempt), Gate 4 (CSM exempt),
   Gate 6 (Pure Quant active), and Gate 7 (BTC risk sizing) evaluate accurately.
"""

import unittest
from unittest.mock import patch, MagicMock
import config
from dashboard import CockpitDataEngine

class TestDashboardBtcXray(unittest.TestCase):

    def setUp(self):
        self.engine = CockpitDataEngine()
        self.engine.scanner = MagicMock()
        self.engine.scanner._m4_z_last = {}
        self.engine.scanner.get_radar_standbys.return_value = []
        self.engine.scanner.get_all_active_standbys.return_value = []
        self.engine.scanner.symbols = ["EURUSD-ECN", "BTCUSD"]
        self.engine.scanner.macro_cache = {
            "BTCUSD": {
                "permission_state": "GO",
                "action_tier": "FULL_ALLOW",
                "current_atr_pts": 30000.0,
                "floor_f1": 94000.0,
                "ceiling_c1": 97500.0,
                "is_bull": True,
                "is_bear": False,
                "csm_delta": 0.0
            }
        }

    @patch("dashboard.connector.get_valid_trade_symbol", return_value="BTCUSD")
    @patch("dashboard.connector.get_account_info", return_value={"balance": 10000.0, "equity": 10000.0, "login": "1157958"})
    @patch("dashboard.connector.get_all_open_positions", return_value=[])
    @patch("dashboard.connector.get_closed_positions_today", return_value=[])
    def test_overview_cache_includes_btc(self, mock_closed, mock_open, mock_acc, mock_valid_sym):
        """Overview cache must always include BTCUSD in pairs list."""
        mock_si = MagicMock()
        mock_si.digits = 2
        mock_si.point = 1.0
        mock_tick = MagicMock()
        mock_tick.bid = 95000.0
        mock_tick.ask = 95050.0

        with patch.object(config.mt5, "symbol_info", return_value=mock_si):
            with patch.object(config.mt5, "symbol_info_tick", return_value=mock_tick):
                self.engine._build_overview_cache()
                
                overview = self.engine.cached_overview
                pairs = overview.get("pairs", [])
                symbols = [p["symbol"] for p in pairs]
                self.assertIn("BTCUSD", symbols, "BTCUSD must be present in dashboard overview pairs")
                
                btc_p = next(p for p in pairs if p["symbol"] == "BTCUSD")
                self.assertEqual(btc_p["clean_symbol"], "BTCUSD")
                self.assertEqual(btc_p["tier"], "FULL_ALLOW")

    @patch("dashboard.connector.get_valid_trade_symbol", return_value="BTCUSD")
    def test_symbol_detail_and_7_gate_xray_for_btc(self, mock_valid_sym):
        """get_symbol_detail('BTCUSD') must return 7 calibrated decision gates."""
        mock_si = MagicMock()
        mock_si.digits = 2
        mock_si.point = 1.0
        mock_tick = MagicMock()
        mock_tick.bid = 95000.0
        mock_tick.ask = 95050.0

        rates_data = [
            {"time": 1700000000 + i * 3600, "open": 95000.0, "high": 95500.0, "low": 94800.0, "close": 95200.0}
            for i in range(100)
        ]

        with patch.object(config.mt5, "symbol_info", return_value=mock_si):
            with patch.object(config.mt5, "symbol_info_tick", return_value=mock_tick):
                with patch.object(config.mt5, "copy_rates_from_pos", return_value=rates_data):
                    with patch.object(config, "ENABLE_LLM_JURY", False):
                        detail = self.engine.get_symbol_detail("BTCUSD", "H1")
                        
                        self.assertEqual(detail["symbol"], "BTCUSD")
                        self.assertGreater(len(detail["candles"]), 0)
                        
                        gates = detail.get("gates", [])
                        self.assertEqual(len(gates), 7, "X-Ray Surveillance must evaluate exactly 7 decision gates")
                        
                        # Gate 1: Session & Spread (BTC exempt from dead zone)
                        g1 = next(g for g in gates if g["id"] == 1)
                        self.assertNotIn("[DEAD ZONE]", g1["reason"], "BTCUSD should not be blocked by FX dead zone")
                        
                        # Gate 2: Basket Lock (BTC exempt from fiat shock)
                        g2 = next(g for g in gates if g["id"] == 2)
                        self.assertEqual(g2["status"], "PASS")
                        self.assertIn("crypto", g2["reason"].lower())
                        
                        # Gate 4: CSM Flow Alignment (BTC exempt from fiat CSM)
                        g4 = next(g for g in gates if g["id"] == 4)
                        self.assertEqual(g4["status"], "PASS")
                        
                        # Gate 6: Pure Quant Direct Execution (No-LLM mode)
                        g6 = next(g for g in gates if g["id"] == 6)
                        self.assertEqual(g6["status"], "PASS")
                        self.assertIn("Pure Quant", g6["title"])
                        
                        # Gate 7: BTC Risk Floor & Ceiling
                        g7 = next(g for g in gates if g["id"] == 7)
                        self.assertEqual(g7["status"], "PASS")
                        self.assertIn(str(config.DEFAULT_SL_POINTS_BTC), g7["reason"])

if __name__ == "__main__":
    unittest.main()
