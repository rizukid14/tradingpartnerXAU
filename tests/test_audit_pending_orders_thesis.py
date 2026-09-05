"""
Unit tests for audit_pending_orders_thesis() in position_manager.py.
Validates:
1. SELL pending orders are NOT cancelled when MSE reports CEILING_REJECTION (fixes prior critical bug).
2. BUY pending orders are NOT cancelled when MSE reports FLOOR_REJECTION (fixes prior critical bug).
3. Orders are cancelled when price severely penetrates past the invalidation anchor (> 0.50x ATR).
4. Orders are cancelled when CSM currency flow inverts violently against the position.
"""
import unittest
from unittest.mock import patch, MagicMock
import config
from src.analytics.position_manager import audit_pending_orders_thesis


class TestAuditPendingOrdersThesis(unittest.TestCase):

    @patch("src.analytics.position_manager.mt5")
    @patch("src.analytics.macro_strategic_engine.macro_strategic_engine.get_directive")
    @patch("src.analytics.currency_strength.get_csm_delta_for_symbol")
    def test_sell_limit_not_cancelled_on_ceiling_rejection(self, mock_csm, mock_get_dir, mock_mt5):
        """SELL limit orders waiting at resistance must NOT be cancelled when MSE reports CEILING_REJECTION."""
        mock_order = MagicMock()
        mock_order.ticket = 11111
        mock_order.symbol = "CADJPY-ECNc"
        mock_order.magic = config.MAGIC_NUMBER
        mock_order.comment = "RADAR M3 SELL"
        mock_order.type = 3  # ORDER_TYPE_SELL_LIMIT
        mock_order.price_open = 113.000
        mock_order.sl = 113.500

        mock_mt5.orders_get.return_value = [mock_order]
        mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
        mock_mt5.ORDER_TYPE_BUY_STOP = 4
        mock_mt5.ORDER_TYPE_SELL_STOP = 5

        mock_si = MagicMock()
        mock_si.point = 0.001
        mock_mt5.symbol_info.return_value = mock_si

        # MSE market_state is CEILING_REJECTION (the exact reason to SELL!)
        mock_strat = MagicMock()
        mock_strat.market_state = "CEILING_REJECTION"
        mock_get_dir.return_value = mock_strat

        # Price close is near anchor (112.980), ATR is 0.300
        mock_mt5.copy_rates_from_pos.return_value = [{"close": 112.980}]
        mock_csm.return_value = -0.10  # Neutral/slightly bearish CAD vs JPY

        audit_pending_orders_thesis()

        # order_send must NOT be called to remove the order!
        mock_mt5.order_send.assert_not_called()

    @patch("src.analytics.position_manager.mt5")
    @patch("src.analytics.macro_strategic_engine.macro_strategic_engine.get_directive")
    @patch("src.analytics.currency_strength.get_csm_delta_for_symbol")
    def test_buy_limit_not_cancelled_on_floor_rejection(self, mock_csm, mock_get_dir, mock_mt5):
        """BUY limit orders waiting at support must NOT be cancelled when MSE reports FLOOR_REJECTION."""
        mock_order = MagicMock()
        mock_order.ticket = 22222
        mock_order.symbol = "GBPUSD-ECNc"
        mock_order.magic = config.MAGIC_NUMBER
        mock_order.comment = "RADAR M2 BUY"
        mock_order.type = 2  # ORDER_TYPE_BUY_LIMIT
        mock_order.price_open = 1.35000
        mock_order.sl = 1.34600

        mock_mt5.orders_get.return_value = [mock_order]
        mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
        mock_mt5.ORDER_TYPE_BUY_STOP = 4
        mock_mt5.ORDER_TYPE_SELL_STOP = 5

        mock_si = MagicMock()
        mock_si.point = 0.00001
        mock_mt5.symbol_info.return_value = mock_si

        # MSE market_state is FLOOR_REJECTION (the exact reason to BUY!)
        mock_strat = MagicMock()
        mock_strat.market_state = "FLOOR_REJECTION"
        mock_get_dir.return_value = mock_strat

        mock_mt5.copy_rates_from_pos.return_value = [{"close": 1.35020}]
        mock_csm.return_value = +0.15

        audit_pending_orders_thesis()

        mock_mt5.order_send.assert_not_called()

    @patch("src.analytics.position_manager.mt5")
    @patch("src.analytics.macro_strategic_engine.macro_strategic_engine.get_directive")
    @patch("src.analytics.currency_strength.get_csm_delta_for_symbol")
    def test_buy_cancelled_when_m15_close_penetrates_invalidation_floor(self, mock_csm, mock_get_dir, mock_mt5):
        """BUY limit order must be cancelled if M15 close penetrates below the invalidation floor."""
        mock_order = MagicMock()
        mock_order.ticket = 33333
        mock_order.symbol = "GBPUSD-ECNc"
        mock_order.magic = config.MAGIC_NUMBER
        mock_order.comment = "RADAR M3 BUY"
        mock_order.type = 2  # ORDER_TYPE_BUY_LIMIT
        mock_order.price_open = 1.35000
        mock_order.sl = 1.34600

        mock_mt5.orders_get.return_value = [mock_order]
        mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
        mock_mt5.ORDER_TYPE_BUY_STOP = 4
        mock_mt5.ORDER_TYPE_SELL_STOP = 5

        mock_si = MagicMock()
        mock_si.point = 0.00001
        mock_mt5.symbol_info.return_value = mock_si

        mock_strat = MagicMock()
        mock_strat.market_state = "NEUTRAL"
        mock_get_dir.return_value = mock_strat

        # Price penetrates below SL (1.34600) -> 1.34550
        mock_mt5.copy_rates_from_pos.return_value = [{"close": 1.34550}]
        mock_csm.return_value = 0.0

        mock_send_res = MagicMock()
        mock_send_res.retcode = 10009  # TRADE_RETCODE_DONE
        mock_mt5.order_send.return_value = mock_send_res

        audit_pending_orders_thesis()

        mock_mt5.order_send.assert_called_once()
        sent_req = mock_mt5.order_send.call_args[0][0]
        self.assertEqual(sent_req["order"], 33333)

    @patch("src.analytics.position_manager.mt5")
    @patch("src.analytics.macro_strategic_engine.macro_strategic_engine.get_directive")
    @patch("src.analytics.currency_strength.get_csm_delta_for_symbol")
    def test_sell_cancelled_when_csm_reverses_strongly(self, mock_csm, mock_get_dir, mock_mt5):
        """SELL limit order must NOT be cancelled at moderate CSM (+0.45), but MUST be cancelled if CSM turns strongly bullish (>= +1.0)."""
        mock_order = MagicMock()
        mock_order.ticket = 44444
        mock_order.symbol = "EURJPY-ECNc"
        mock_order.magic = config.MAGIC_NUMBER
        mock_order.comment = "RADAR M2 SELL"
        mock_order.type = 3  # ORDER_TYPE_SELL_LIMIT
        mock_order.price_open = 162.500
        mock_order.sl = 163.000

        mock_mt5.orders_get.return_value = [mock_order]
        mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
        mock_mt5.ORDER_TYPE_BUY_STOP = 4
        mock_mt5.ORDER_TYPE_SELL_STOP = 5

        mock_si = MagicMock()
        mock_si.point = 0.001
        mock_mt5.symbol_info.return_value = mock_si

        mock_strat = MagicMock()
        mock_strat.market_state = "NEUTRAL"
        mock_get_dir.return_value = mock_strat

        # Price close is still safe (162.400)
        mock_mt5.copy_rates_from_pos.return_value = [{"close": 162.400}]
        
        # 1. Moderate CSM delta (+0.45) allowed by scanner must NOT cancel the order!
        mock_csm.return_value = +0.45
        audit_pending_orders_thesis()
        mock_mt5.order_send.assert_not_called()

        # 2. BUT extreme opposed CSM delta (+1.25 >= +1.0) MUST cancel the order!
        mock_csm.return_value = +1.25
        mock_send_res = MagicMock()
        mock_send_res.retcode = 10009
        mock_mt5.order_send.return_value = mock_send_res

        audit_pending_orders_thesis()

        mock_mt5.order_send.assert_called_once()
        sent_req = mock_mt5.order_send.call_args[0][0]
        self.assertEqual(sent_req["order"], 44444)

    @patch("src.analytics.position_manager.mt5")
    @patch("src.analytics.macro_strategic_engine.macro_strategic_engine.get_directive")
    @patch("src.analytics.currency_strength.get_csm_delta_for_symbol")
    def test_buy_pending_csm_harmonized_tolerance(self, mock_csm, mock_get_dir, mock_mt5):
        """BUY limit order with CSM delta -0.69 (EURNZD case) must NOT be cancelled, but cancelled at <= -1.0."""
        mock_order = MagicMock()
        mock_order.ticket = 77777
        mock_order.symbol = "EURNZD-ECNc"
        mock_order.magic = config.MAGIC_NUMBER
        mock_order.comment = "RADAR M2 BUY"
        mock_order.type = 2  # ORDER_TYPE_BUY_LIMIT
        mock_order.price_open = 1.97450
        mock_order.sl = 1.97250

        mock_mt5.orders_get.return_value = [mock_order]
        mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
        mock_mt5.ORDER_TYPE_BUY_STOP = 4
        mock_mt5.ORDER_TYPE_SELL_STOP = 5

        mock_si = MagicMock()
        mock_si.point = 0.00001
        mock_mt5.symbol_info.return_value = mock_si

        mock_strat = MagicMock()
        mock_strat.market_state = "NEUTRAL"
        mock_get_dir.return_value = mock_strat

        # Price close is above SL (1.97500 > 1.97250)
        mock_mt5.copy_rates_from_pos.return_value = [{"close": 1.97500}]

        # Moderate negative CSM delta (-0.69) must NOT cancel
        mock_csm.return_value = -0.69
        audit_pending_orders_thesis()
        mock_mt5.order_send.assert_not_called()

        # Extreme opposed CSM delta (-1.15 <= -1.0) MUST cancel
        mock_csm.return_value = -1.15
        mock_send_res = MagicMock()
        mock_send_res.retcode = 10009
        mock_mt5.order_send.return_value = mock_send_res

        audit_pending_orders_thesis()
        mock_mt5.order_send.assert_called_once()
        sent_req = mock_mt5.order_send.call_args[0][0]
        self.assertEqual(sent_req["order"], 77777)

    @patch("src.analytics.position_manager.mt5")
    @patch("src.analytics.macro_strategic_engine.macro_strategic_engine.get_directive")
    @patch("src.analytics.currency_strength.get_csm_delta_for_symbol")
    def test_buy_limit_cancelled_on_target_proximity_expiration(self, mock_csm, mock_get_dir, mock_mt5):
        """BUY limit order must be cancelled if market achieves >=75% of TP without fill."""
        mock_order = MagicMock()
        mock_order.ticket = 55555
        mock_order.symbol = "GBPUSD-ECNc"
        mock_order.magic = config.MAGIC_NUMBER
        mock_order.comment = "RADAR M2 BUY"
        mock_order.type = 2  # ORDER_TYPE_BUY_LIMIT
        mock_order.price_open = 1.35000
        mock_order.tp = 1.36000
        mock_order.sl = 1.34500

        mock_mt5.orders_get.return_value = [mock_order]
        mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
        mock_mt5.ORDER_TYPE_BUY_STOP = 4
        mock_mt5.ORDER_TYPE_SELL_STOP = 5

        mock_si = MagicMock()
        mock_si.point = 0.00001
        # Market price moved to 1.35760 (76% of target move to 1.36000 without hitting 1.35000)
        mock_si.bid = 1.35760
        mock_si.ask = 1.35770
        mock_mt5.symbol_info.return_value = mock_si

        mock_strat = MagicMock()
        mock_strat.market_state = "NEUTRAL"
        mock_get_dir.return_value = mock_strat

        mock_mt5.copy_rates_from_pos.return_value = [{"close": 1.35760}]
        mock_csm.return_value = +0.10

        mock_send_res = MagicMock()
        mock_send_res.retcode = 10009
        mock_mt5.order_send.return_value = mock_send_res

        audit_pending_orders_thesis()

        mock_mt5.order_send.assert_called_once()
        sent_req = mock_mt5.order_send.call_args[0][0]
        self.assertEqual(sent_req["order"], 55555)
        self.assertEqual(sent_req["comment"], "Thesis Failure Cancel")

    @patch("src.analytics.position_manager.mt5")
    @patch("src.analytics.macro_strategic_engine.macro_strategic_engine.get_directive")
    @patch("src.analytics.currency_strength.get_csm_delta_for_symbol")
    def test_sell_limit_cancelled_on_target_proximity_expiration(self, mock_csm, mock_get_dir, mock_mt5):
        """SELL limit order must be cancelled if market achieves >=75% of TP without fill."""
        mock_order = MagicMock()
        mock_order.ticket = 66666
        mock_order.symbol = "EURCAD-ECNc"
        mock_order.magic = config.MAGIC_NUMBER
        mock_order.comment = "RADAR M2 SELL"
        mock_order.type = 3  # ORDER_TYPE_SELL_LIMIT
        mock_order.price_open = 1.60560
        mock_order.tp = 1.60160
        mock_order.sl = 1.60760

        mock_mt5.orders_get.return_value = [mock_order]
        mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
        mock_mt5.ORDER_TYPE_BUY_STOP = 4
        mock_mt5.ORDER_TYPE_SELL_STOP = 5

        mock_si = MagicMock()
        mock_si.point = 0.00001
        # Target distance is 0.00400. 75% target is 1.60260. Market at 1.60250 (77.5% progress).
        mock_si.bid = 1.60240
        mock_si.ask = 1.60250
        mock_mt5.symbol_info.return_value = mock_si

        mock_strat = MagicMock()
        mock_strat.market_state = "NEUTRAL"
        mock_get_dir.return_value = mock_strat

        mock_mt5.copy_rates_from_pos.return_value = [{"close": 1.60250}]
        mock_csm.return_value = -0.15

        mock_send_res = MagicMock()
        mock_send_res.retcode = 10009
        mock_mt5.order_send.return_value = mock_send_res

        audit_pending_orders_thesis()

        mock_mt5.order_send.assert_called_once()
        sent_req = mock_mt5.order_send.call_args[0][0]
        self.assertEqual(sent_req["order"], 66666)

    @patch("src.analytics.position_manager.mt5")
    @patch("src.analytics.macro_strategic_engine.macro_strategic_engine.get_directive")
    @patch("src.analytics.currency_strength.get_csm_delta_for_symbol")
    def test_sell_limit_not_cancelled_when_proximity_below_75_percent(self, mock_csm, mock_get_dir, mock_mt5):
        """SELL limit order must NOT be cancelled when price has only moved a small fraction toward TP."""
        mock_order = MagicMock()
        mock_order.ticket = 77777
        mock_order.symbol = "EURCAD-ECNc"
        mock_order.magic = config.MAGIC_NUMBER
        mock_order.comment = "RADAR M2 SELL"
        mock_order.type = 3  # ORDER_TYPE_SELL_LIMIT
        mock_order.price_open = 1.60560
        mock_order.tp = 1.60160
        mock_order.sl = 1.60760

        mock_mt5.orders_get.return_value = [mock_order]
        mock_mt5.ORDER_TYPE_BUY_LIMIT = 2
        mock_mt5.ORDER_TYPE_SELL_LIMIT = 3
        mock_mt5.ORDER_TYPE_BUY_STOP = 4
        mock_mt5.ORDER_TYPE_SELL_STOP = 5

        mock_si = MagicMock()
        mock_si.point = 0.00001
        # Market price at 1.60450 (only 27.5% toward TP)
        mock_si.bid = 1.60440
        mock_si.ask = 1.60450
        mock_mt5.symbol_info.return_value = mock_si

        mock_strat = MagicMock()
        mock_strat.market_state = "NEUTRAL"
        mock_get_dir.return_value = mock_strat

        mock_mt5.copy_rates_from_pos.return_value = [{"close": 1.60450}]
        mock_csm.return_value = -0.15

        audit_pending_orders_thesis()

        mock_mt5.order_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
