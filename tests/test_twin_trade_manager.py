import unittest
from unittest.mock import MagicMock
from src.analytics.twin_trade_manager import (
    calculate_twin_lot,
    calculate_cushion_sl,
    TwinTradeManager
)


class TestTwinTradeManager(unittest.TestCase):

    def test_lot_allocation_single_on_min_lot(self):
        # 0.01 lot cannot be split -> single order
        lot_a, lot_b, is_twin = calculate_twin_lot(0.01, lot_min=0.01, lot_step=0.01, setup_grade="GRADE_A")
        self.assertEqual(lot_a, 0.01)
        self.assertEqual(lot_b, 0.0)
        self.assertFalse(is_twin)

    def test_lot_allocation_single_on_grade_b(self):
        # Grade B is always single order TP1 only
        lot_a, lot_b, is_twin = calculate_twin_lot(0.10, lot_min=0.01, lot_step=0.01, setup_grade="GRADE_B")
        self.assertEqual(lot_a, 0.10)
        self.assertEqual(lot_b, 0.0)
        self.assertFalse(is_twin)

    def test_lot_allocation_twin_even_and_odd(self):
        # 0.02 -> 0.01 + 0.01
        lot_a, lot_b, is_twin = calculate_twin_lot(0.02, lot_min=0.01, lot_step=0.01, setup_grade="GRADE_A")
        self.assertEqual(lot_a, 0.01)
        self.assertEqual(lot_b, 0.01)
        self.assertTrue(is_twin)

        # 0.05 -> 0.02 + 0.03
        lot_a, lot_b, is_twin = calculate_twin_lot(0.05, lot_min=0.01, lot_step=0.01, setup_grade="GRADE_A_PLUS")
        self.assertEqual(lot_a, 0.02)
        self.assertEqual(lot_b, 0.03)
        self.assertTrue(is_twin)

        # 0.50 -> 0.25 + 0.25
        lot_a, lot_b, is_twin = calculate_twin_lot(0.50, lot_min=0.01, lot_step=0.01, setup_grade="GRADE_S")
        self.assertEqual(lot_a, 0.25)
        self.assertEqual(lot_b, 0.25)
        self.assertTrue(is_twin)

    def test_cushion_sl_calculation_buy(self):
        entry = 0.72000
        tp1 = 0.72300  # +300 pts
        atr = 0.00200   # 200 pts ATR
        # Cushion raw = 0.72300 - (0.35 * 0.00200) = 0.72300 - 0.00070 = 0.72230
        # BE price = 0.72000 + 15 pts = 0.72015
        # Chosen SL = max(0.72015, 0.72230) = 0.72230
        sl = calculate_cushion_sl(direction=1, entry_price=entry, tp1_price=tp1, atr_val=atr, point=0.00001, commission_pad_pts=15)
        self.assertEqual(sl, 0.72230)
        self.assertGreater(sl, entry)
        self.assertLess(sl, tp1)

    def test_cushion_sl_calculation_sell(self):
        entry = 0.72000
        tp1 = 0.71700  # -300 pts
        atr = 0.00200   # 200 pts ATR
        # Cushion raw = 0.71700 + (0.35 * 0.00200) = 0.71700 + 0.00070 = 0.71770
        # BE price = 0.72000 - 15 pts = 0.71985
        # Chosen SL = min(0.71985, 0.71770) = 0.71770
        sl = calculate_cushion_sl(direction=-1, entry_price=entry, tp1_price=tp1, atr_val=atr, point=0.00001, commission_pad_pts=15)
        self.assertEqual(sl, 0.71770)
        self.assertLess(sl, entry)
        self.assertGreater(sl, tp1)

    def test_cushion_sl_floored_at_bep(self):
        # If TP1 is very tight and cushion_raw would be below BEP, SL is clamped to BEP
        entry = 0.72000
        tp1 = 0.72030  # +30 pts (very small)
        atr = 0.00200   # 200 pts ATR
        # Cushion raw = 0.72030 - (0.35 * 0.00200) = 0.72030 - 0.00070 = 0.71960 (below entry!)
        # BE price = 0.72000 + 15 pts = 0.72015
        # Chosen SL = max(0.72015, 0.71960) = 0.72015 (strictly above BEP)
        sl = calculate_cushion_sl(direction=1, entry_price=entry, tp1_price=tp1, atr_val=atr, point=0.00001, commission_pad_pts=15)
        self.assertEqual(sl, 0.72015)
        self.assertGreater(sl, entry)

    def test_milestone_audit_cycle_transitions(self):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(delete=False)
        tmp.close()

        manager = TwinTradeManager(state_file=tmp.name)
        manager.register_pair(
            pair_id="TEST_AUDUSD_1",
            symbol="AUDUSD",
            direction=1,
            ticket_a=1001,
            ticket_b=1002,
            volume_a=0.02,
            volume_b=0.03,
            entry_price=0.72000,
            sl_initial=0.71800,
            tp1=0.72200,
            tp2=0.72350,
            tp3=0.72500,
            setup_grade="GRADE_A_PLUS"
        )

        # Mock objects
        pos_b = MagicMock()
        pos_b.ticket = 1002
        pos_b.symbol = "AUDUSD"
        pos_b.sl = 0.71800
        pos_b.tp = 0.72500

        open_positions = {1002: pos_b}  # Ticket 1001 is closed!

        sym_info = MagicMock()
        sym_info.point = 0.00001
        sym_info.digits = 5

        tick = MagicMock()
        tick.bid = 0.72220  # Price above TP1, between TP1 and TP2
        tick.ask = 0.72230

        modified_sls = {}
        def mock_modify(ticket, sl):
            modified_sls[ticket] = sl
            pos_b.sl = sl
            return True

        # Phase 1: Ticket A closed -> Cushion Lock activated
        updates = manager.audit_cycle(
            open_positions=open_positions,
            get_deals_fn=lambda t: [MagicMock(profit=15.0)],
            modify_sl_fn=mock_modify,
            symbol_info_provider=lambda s: sym_info,
            tick_provider=lambda s: tick,
            atr_provider=lambda s: 0.00200
        )
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0]["action"], "CUSHION_LOCKED")
        self.assertEqual(manager.trades["TEST_AUDUSD_1"]["state"], "TP1_HARVESTED_CUSHION_LOCKED")
        # SL should be Below TP1 (0.72200 - 0.00070 = 0.72130) and Above BEP (0.72015)
        self.assertEqual(modified_sls[1002], 0.72130)

        # Phase 2: Price touches TP2 (0.72350) -> Advance SL to TP1 (0.72200)
        tick.bid = 0.72360
        updates2 = manager.audit_cycle(
            open_positions=open_positions,
            get_deals_fn=lambda t: [],
            modify_sl_fn=mock_modify,
            symbol_info_provider=lambda s: sym_info,
            tick_provider=lambda s: tick,
            atr_provider=lambda s: 0.00200
        )
        self.assertEqual(len(updates2), 1)
        self.assertEqual(updates2[0]["action"], "LOCKED_AT_TP1")
        self.assertEqual(manager.trades["TEST_AUDUSD_1"]["state"], "TP2_REACHED_LOCK_TP1")
        self.assertEqual(modified_sls[1002], 0.72200)

        # Phase 3: Price approaches TP3 (progress >= 80% from TP2 to TP3: 0.72350 -> 0.72500 dist=150 pts; 80%=120 pts -> 0.72470)
        tick.bid = 0.72480  # 130 pts / 150 pts = 86.7%
        updates3 = manager.audit_cycle(
            open_positions=open_positions,
            get_deals_fn=lambda t: [],
            modify_sl_fn=mock_modify,
            symbol_info_provider=lambda s: sym_info,
            tick_provider=lambda s: tick,
            atr_provider=lambda s: 0.00200
        )
        self.assertEqual(len(updates3), 1)
        self.assertEqual(updates3[0]["action"], "LOCKED_AT_TP2")
        self.assertEqual(manager.trades["TEST_AUDUSD_1"]["state"], "TP3_APPROACH_LOCK_TP2")
        self.assertEqual(modified_sls[1002], 0.72350)


if __name__ == "__main__":
    unittest.main()
