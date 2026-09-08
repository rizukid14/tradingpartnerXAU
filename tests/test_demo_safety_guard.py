"""
Unit tests for MT5 institutional demo vs live safety guard in mt5_connector.py.
Ensures that if MT5_ACCOUNT_MODE is set to 'demo', the connector strictly refuses
to trade or initialize if the active MT5 terminal is connected to a LIVE / REAL account.
"""

import unittest
from unittest.mock import patch, MagicMock
import config
from src.core import mt5_connector

class TestDemoSafetyGuard(unittest.TestCase):

    @patch("src.core.mt5_connector.mt5")
    def test_demo_safety_guard_blocks_real_account(self, mock_mt5):
        """When MT5_ACCOUNT_MODE == 'demo', connecting to a REAL account must return False."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.ACCOUNT_TRADE_MODE_DEMO = 0
        mock_mt5.ACCOUNT_TRADE_MODE_REAL = 2
        
        # Mock active account as REAL (trade_mode=2)
        mock_acc = MagicMock()
        mock_acc.login = 27556325
        mock_acc.server = "VTMarkets-Live 3"
        mock_acc.trade_mode = 2  # REAL
        mock_mt5.account_info.return_value = mock_acc
        
        with patch.object(config, "MT5_ACCOUNT_MODE", "demo"):
            with patch.object(config, "MT5_LOGIN", 1157958):
                with patch.object(config, "MT5_PASSWORD", "demo_pass"):
                    with patch.object(config, "MT5_SERVER", "VTMarkets-Demo"):
                        res = mt5_connector.init_mt5()
                        self.assertFalse(res, "init_mt5 should fail and abort when terminal is on REAL account while config is demo")
                        mock_mt5.shutdown.assert_called_once()

    @patch("src.core.mt5_connector.mt5")
    def test_demo_safety_guard_allows_demo_account(self, mock_mt5):
        """When MT5_ACCOUNT_MODE == 'demo', connecting to a DEMO account (trade_mode=0) must succeed."""
        mock_mt5.initialize.return_value = True
        mock_mt5.login.return_value = True
        mock_mt5.ACCOUNT_TRADE_MODE_DEMO = 0
        mock_mt5.ACCOUNT_TRADE_MODE_REAL = 2
        
        # Mock active account as DEMO (trade_mode=0)
        mock_acc = MagicMock()
        mock_acc.login = 1157958
        mock_acc.server = "VTMarkets-Demo"
        mock_acc.trade_mode = 0  # DEMO
        mock_acc.balance = 10000.0
        mock_mt5.account_info.return_value = mock_acc
        
        mock_sym = MagicMock()
        mock_sym.visible = True
        mock_mt5.symbol_info.return_value = mock_sym
        
        mock_term = MagicMock()
        mock_term.trade_allowed = True
        mock_mt5.terminal_info.return_value = mock_term
        
        with patch.object(config, "MT5_ACCOUNT_MODE", "demo"):
            with patch.object(config, "MT5_LOGIN", 1157958):
                with patch.object(config, "MT5_PASSWORD", "demo_pass"):
                    with patch.object(config, "MT5_SERVER", "VTMarkets-Demo"):
                        with patch("src.core.mt5_connector.get_valid_trade_symbol", return_value="BTCUSD.c"):
                            res = mt5_connector.init_mt5()
                            self.assertTrue(res, "init_mt5 should succeed when connected to verified DEMO account")

if __name__ == "__main__":
    unittest.main()
