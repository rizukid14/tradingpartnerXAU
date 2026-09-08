"""
Unit tests for Magic Number isolation in RiskEngine._check_max_positions().
Validates that:
1. Manual trades (magic == 0 or other EA magic) do NOT consume bot's currency basket limits.
2. Bot trades (magic == config.MAGIC_NUMBER) are properly counted for currency basket & capacity limits.
3. Total absolute account ceiling (MAX_ABSOLUTE_OPEN_POSITIONS) still monitors all trades as a global emergency shield.
"""
import unittest
from unittest.mock import patch, MagicMock
import config
from src.core.risk_engine import RiskEngine


class TestRiskEngineMagicFilter(unittest.TestCase):

    def setUp(self):
        self.risk = RiskEngine()

    @patch("src.core.risk_engine.connector.get_account_info")
    @patch("src.core.risk_engine.mt5.orders_get")
    @patch("src.core.risk_engine.mt5.positions_get")
    def test_manual_positions_do_not_block_currency_basket(self, mock_positions_get, mock_orders_get, mock_account):
        """Two manual EURUSD positions (magic 0) + 1 bot AUDUSD position (magic 20260625) must NOT block USDJPY."""
        mock_account.return_value = {"equity": 10000.0, "free_margin": 9000.0}
        mock_orders_get.return_value = []

        # Position 1: Manual EURUSD
        pos1 = MagicMock()
        pos1.ticket = 101
        pos1.symbol = "EURUSD-ECN"
        pos1.magic = 0
        pos1.sl = 0.0

        # Position 2: Manual EURUSD
        pos2 = MagicMock()
        pos2.ticket = 102
        pos2.symbol = "EURUSD-ECN"
        pos2.magic = 0
        pos2.sl = 0.0

        # Position 3: Bot AUDUSD
        pos3 = MagicMock()
        pos3.ticket = 103
        pos3.symbol = "AUDUSD-ECN"
        pos3.magic = config.MAGIC_NUMBER
        pos3.sl = 0.0

        mock_positions_get.return_value = [pos1, pos2, pos3]

        allowed, msg = self.risk._check_max_positions("USDJPY-ECN")
        self.assertTrue(allowed, f"USDJPY should be allowed because manual trades are excluded, got: {msg}")

    @patch("src.core.risk_engine.config.get_max_open_positions", return_value=6)
    @patch("src.core.risk_engine.connector.get_account_info")
    @patch("src.core.risk_engine.mt5.orders_get")
    @patch("src.core.risk_engine.mt5.positions_get")
    def test_bot_positions_properly_enforce_currency_basket(self, mock_positions_get, mock_orders_get, mock_account, mock_get_max):
        """Three bot positions containing USD must block a 4th USD position under standard limits (MAX=3)."""
        mock_account.return_value = {"equity": 10000.0, "free_margin": 9000.0}
        mock_orders_get.return_value = []

        # 3 Bot positions with USD
        p1 = MagicMock(ticket=201, symbol="EURUSD-ECN", magic=config.MAGIC_NUMBER, sl=0.0)
        p2 = MagicMock(ticket=202, symbol="GBPUSD-ECN", magic=config.MAGIC_NUMBER, sl=0.0)
        p3 = MagicMock(ticket=203, symbol="AUDUSD-ECN", magic=config.MAGIC_NUMBER, sl=0.0)

        mock_positions_get.return_value = [p1, p2, p3]

        orig_basket = config.MAX_CURRENCY_BASKET_EXPOSURE
        config.MAX_CURRENCY_BASKET_EXPOSURE = 3
        try:
            allowed, msg = self.risk._check_max_positions("USDJPY-ECN")
            self.assertFalse(allowed)
            self.assertIn("Konsentrasi mata uang USD", msg)
        finally:
            config.MAX_CURRENCY_BASKET_EXPOSURE = orig_basket

    @patch("src.core.risk_engine.config.get_max_open_positions", return_value=6)
    @patch("src.core.risk_engine.connector.get_account_info")
    @patch("src.core.risk_engine.mt5.orders_get")
    @patch("src.core.risk_engine.mt5.positions_get")
    def test_basket_exposure_unlimited_when_set_to_99(self, mock_positions_get, mock_orders_get, mock_account, mock_get_max):
        """When MAX_CURRENCY_BASKET_EXPOSURE=99, a 4th USD position must be permitted."""
        mock_account.return_value = {"equity": 10000.0, "free_margin": 9000.0}
        mock_orders_get.return_value = []

        p1 = MagicMock(ticket=201, symbol="EURUSD-ECN", magic=config.MAGIC_NUMBER, sl=0.0)
        p2 = MagicMock(ticket=202, symbol="GBPUSD-ECN", magic=config.MAGIC_NUMBER, sl=0.0)
        p3 = MagicMock(ticket=203, symbol="AUDUSD-ECN", magic=config.MAGIC_NUMBER, sl=0.0)
        mock_positions_get.return_value = [p1, p2, p3]

        orig_basket = config.MAX_CURRENCY_BASKET_EXPOSURE
        config.MAX_CURRENCY_BASKET_EXPOSURE = 99
        try:
            allowed, msg = self.risk._check_max_positions("USDJPY-ECN")
            self.assertTrue(allowed)
        finally:
            config.MAX_CURRENCY_BASKET_EXPOSURE = orig_basket

    @patch("src.core.risk_engine.connector.get_account_info")
    @patch("src.core.risk_engine.mt5.orders_get")
    @patch("src.core.risk_engine.mt5.positions_get")
    def test_total_absolute_ceiling_monitors_all_trades(self, mock_positions_get, mock_orders_get, mock_account):
        """Total absolute ceiling (8) must block new orders if total account trades reach 8, even if manual."""
        mock_account.return_value = {"equity": 10000.0, "free_margin": 9000.0}
        mock_orders_get.return_value = []

        # 8 manual trades
        positions = [
            MagicMock(ticket=300 + i, symbol="EURGBP-ECN", magic=0, sl=0.0)
            for i in range(8)
        ]
        mock_positions_get.return_value = positions

        allowed, msg = self.risk._check_max_positions("USDJPY-ECN")
        self.assertFalse(allowed)
        self.assertIn("batas absolut", msg)


if __name__ == "__main__":
    unittest.main()
