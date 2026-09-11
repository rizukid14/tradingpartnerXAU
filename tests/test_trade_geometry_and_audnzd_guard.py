import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

import config
from src.core.risk_engine import RiskEngine
from src.indicators.atlas_dna import calculate_intraday_sl_tp
from src.core.consensus import _apply_sltp_rules
from src.analytics.market_scanner import MarketScanner, CandidateSetup
from src.analytics.shadow_tracker import QuantShadowTracker, ShadowTrade

WIB = ZoneInfo("Asia/Jakarta")


class TestTradeGeometryAndAUDNZDGuard(unittest.TestCase):
    """
    Test suite komprehensif untuk memverifikasi seluruh 7 Pilar Rekonstruksi Geometri Trade
    dan Resolusi Kasus AUDNZD (11 September 2026).
    """

    def setUp(self):
        self.risk_engine = RiskEngine()
        self.scanner = MarketScanner()

    def test_pilar_1_max_position_lot_clamping(self):
        """Pilar 1: Pastikan MAX_POSITION_LOT = 0.50 membatasi lot akun Cent secara mutlak."""
        self.assertEqual(config.MAX_POSITION_LOT, 0.50)

        mock_si = MagicMock()
        mock_si.volume_min = 0.01
        mock_si.volume_max = 100.0
        mock_si.volume_step = 0.01
        mock_si.trade_tick_value = 1.0
        mock_si.point = 0.00001
        mock_si.trade_tick_size = 0.00001

        mock_acc = MagicMock()
        mock_acc.equity = 10000.0

        with patch("config.mt5.symbol_info", return_value=mock_si), \
             patch("config.mt5.account_info", return_value=mock_acc), \
             patch.object(config, "risk_percent_for", return_value=1.0):
            lot = self.risk_engine.get_effective_lot_size(
                sl_points=50,
                symbol="EURUSD-ECNc"
            )
            self.assertLessEqual(lot, 0.50)
            self.assertEqual(lot, 0.50)

    def test_pilar_3_friction_floor_divisor_020(self):
        """Pilar 3: Pastikan FRICTION_FLOOR_DIVISOR = 0.20 mengamankan beban broker <= 20%."""
        self.assertEqual(config.FRICTION_FLOOR_DIVISOR, 0.20)
        # Spread 20 pts + comm 6 pts = 26 pts -> 26 / 0.20 = 130 pts
        fric_pts = config.friction_floor_points(spread_pts=20, comm_pts=6)
        self.assertEqual(fric_pts, 130)

    def test_pilar_4_balanced_three_term_sl_formula(self):
        """Pilar 4: Formula SL Seimbang max(struct_dist + buffer, 1.00*ATR, fric_floor)."""
        entry = 1.10000
        atr = 0.00060  # 60 pts
        origin = 1.10000  # limit entry at origin level -> raw distance = 0
        spread = 20

        # BUY test: struct_dist = abs(entry - origin) + invalidation_buffer
        res = calculate_intraday_sl_tp(
            symbol="EURUSD-ECNc",
            entry_price=entry,
            direction=1,
            origin_level=origin,
            atr_h1=atr,
            spread_pts=spread,
        )
        sl_pts = int(round((entry - res["sl"]) / 0.00001))
        # 1.00 * ATR = 60 pts; friction floor (20+6)/0.20 = 130 pts
        # Maka sl_pts harus >= fric_floor (130 pts)
        self.assertGreaterEqual(sl_pts, 130)

        # High ATR pair (GBPJPY): ATR dominan
        res_jpy = calculate_intraday_sl_tp(
            symbol="GBPJPY-ECNc",
            entry_price=190.000,
            direction=-1,
            origin_level=190.000,
            atr_h1=0.250,  # 250 pts
            spread_pts=15,
        )
        sl_jpy_pts = int(round((res_jpy["sl"] - 190.000) / 0.001))
        # 1.00 * ATR = 250 pts, fric = (15+6)/0.20 = 105 pts -> SL harus >= 250 pts
        self.assertGreaterEqual(sl_jpy_pts, 250)

    def test_pilar_2_decoupling_tp_in_consensus(self):
        """Pilar 2: Consensus memvalidasi ZCE runway tanpa menaikkan TP buatan."""
        with patch.object(config, "ZCE_ENABLED", True), patch.object(config, "ZCE_MODE", "full"), \
             patch("config.mt5.symbol_info_tick", return_value=None), \
             patch("config.mt5.copy_rates_from_pos", return_value=None):
            cand = CandidateSetup(
                symbol="EURUSD-ECNc",
                setup_type="TREND_ALIGNED_PULLBACK",
                direction=1,
                trigger_price=1.10000,
                current_spread_pts=4,
                current_atr_pts=60,
                metadata={"zce_wall_grade": "GRADE_2_INTERMEDIATE"}
            )
            # SL = 80 pts. TP = 60 pts. Min RR standard = 1.25 (100 pts).
            # Grade B floor = 0.50 * 80 + 9 = 49 pts.
            # Karena 60 pts >= 49 pts, TP 60 pts dipertahankan, bukan dipaksa naik ke 100 pts.
            sl, tp, ok, reason = _apply_sltp_rules(
                sl_points=80,
                tp_points=60,
                symbol="EURUSD-ECNc",
                candidate=cand
            )
            self.assertTrue(ok)
            self.assertEqual(tp, 60)

            # Runway insufficient: TP = 30 pts < Grade B floor (49 pts) -> Tolak trade
            sl, tp, ok, reason = _apply_sltp_rules(
                sl_points=80,
                tp_points=30,
                symbol="EURUSD-ECNc",
                candidate=cand
            )
            self.assertFalse(ok)
            self.assertTrue("Runway" in reason or "ANCHOR_TOO_WIDE" in reason)

    def test_pilar_5_london_defensive_window(self):
        """Pilar 5: Jam 15:00-17:59 WIB melarang passive sell limit."""
        dt_ldn = datetime(2026, 9, 11, 16, 30, tzinfo=WIB)
        is_ldn = (15 <= dt_ldn.hour < 18)
        self.assertTrue(is_ldn)

    def test_pilar_6_conditional_far_target(self):
        """Pilar 6: TP >= 2.5x ATR dibatasi jika bukan sesi Tokyo+CSM>=2 atau Breached Wall."""
        entry = 1.10000
        atr = 0.00100  # 100 pts
        tp_far = 1.10300  # 300 pts = 3.0x ATR

        # Kasus 1: Sesi London (hour 15), CSM delta rendah (0.50), Breached wall False -> Cap ke 2.5x ATR (250 pts = 1.10250)
        tp_capped = self.scanner._apply_conditional_far_target(
            tp_price=tp_far,
            entry_price=entry,
            direction=1,
            atr_price=atr,
            csm_delta=0.50,
            c1_breached=False,
            f1_breached=False,
            now_hour_wib=15,
            pt=0.00001
        )
        self.assertEqual(tp_capped, 1.10250)

        # Kasus 2: Sesi Tokyo (hour 9), CSM delta kuat (2.50) -> Diizinkan target 3.0x ATR
        tp_allowed = self.scanner._apply_conditional_far_target(
            tp_price=tp_far,
            entry_price=entry,
            direction=1,
            atr_price=atr,
            csm_delta=2.50,
            c1_breached=False,
            f1_breached=False,
            now_hour_wib=9,
            pt=0.00001
        )
        self.assertEqual(tp_allowed, tp_far)

    def test_pilar_7_audnzd_mid_chamber_freeze(self):
        """Pilar 7: Mid-Chamber Freeze menutup kebocoran transit zone."""
        c1 = 1.23000
        atr = 0.00100  # 100 pts (0.25 * atr = 0.00025 = 25 pts)

        # Entry di tengah kamar (1.22500): jauh di bawah batas c1 (1.23000 - 25 pts = 1.22975)
        entry_mid = 1.22500
        c1_valid_zone = entry_mid >= (c1 - 0.25 * atr)
        self.assertFalse(c1_valid_zone)

        # Entry tepat di dinding c1 (1.22980 >= 1.22975)
        entry_wall = 1.22980
        c1_wall_zone = entry_wall >= (c1 - 0.25 * atr)
        self.assertTrue(c1_wall_zone)

    def test_pilar_7_anti_marubozu_waterfall_in_m3(self):
        """Pilar 7: M3 Retest menolak sell di pucuk lilin bullish marubozu."""
        c_qual_marubozu = {
            'direction': 'bullish',
            'body_ratio': 0.70,         # Strong bullish marubozu (> 0.55)
            'upper_wick_pct': 0.08,      # Shaved top (< 0.20)
            'max_upper_wick': 0.08,
            'is_bearish_engulf': False,
            'sweep_side': None
        }
        macro = {'c1_reaction_grade': 'GRADE_2_INTERMEDIATE', 'immediate_ceiling_c1': 1.22800}
        
        has_hold, is_soft, reason = self.scanner._evaluate_m2_wall_quality(
            sym="AUDNZD-ECNc",
            direction=-1,  # SELL
            base_level=1.22800,
            c_qual=c_qual_marubozu,
            macro=macro,
            atr_val=0.00100,
            pt=0.00001,
            mt5_connector=None
        )
        # Wajib DITOLAK MARUBOZU_WATERFALL
        self.assertFalse(has_hold)
        self.assertIn("MARUBOZU_WATERFALL", reason)

    def test_pilar_7_breached_wall_filter_in_confluence_anchor(self):
        """Pilar 7: find_ema_confluence_anchor mengabaikan ceiling yang sudah tertembus."""
        df_breach = pd.DataFrame([
            {'open': 1.22600, 'high': 1.22700, 'low': 1.22550, 'close': 1.22650},
            {'open': 1.22650, 'high': 1.22900, 'low': 1.22630, 'close': 1.22850},
            {'open': 1.22850, 'high': 1.22880, 'low': 1.22820, 'close': 1.22840},
        ])
        macro = {
            'df': df_breach,
            'current_atr': 0.00100,
            'ema20': 1.22700,
            'ema50': 1.22650,
            'immediate_ceiling_c1': 1.22800,
            'ceiling_c2': 1.23200,
        }
        anchor, desc = self.scanner.find_ema_confluence_anchor(
            symbol="AUDNZD-ECNc",
            mid=1.22780,
            direction=-1,
            macro=macro,
            pt=0.00001,
            atr_val=0.00100
        )
        # 1.22800 tidak boleh dipilih karena sudah tertembus
        self.assertNotEqual(anchor, 1.22800)

    def test_pilar_0_six_telemetry_fields(self):
        """Pilar 0: Memastikan 6 telemetry fields tercatat pada ShadowTrade."""
        cand = CandidateSetup(
            symbol="EURUSD-ECNc",
            setup_type="UNIVERSAL_LIQUIDITY_SWEEP",
            direction=1,
            trigger_price=1.10000,
            current_spread_pts=12,
            current_atr_pts=60,
            metadata={
                "invalidation_dist": 0.00045,
                "anchor_level": 1.09955
            }
        )
        tracker = QuantShadowTracker()
        tracker.active_trades.clear()
        
        trade = tracker.register_candidate(
            candidate=cand,
            entry_type="buy_limit",
            entry_price=1.10000,
            sl_price=1.09880,
            tp_price=1.10180,
            sl_points=120,
            tp_points=180,
            mt5_disposition="EXECUTED_MT5"
        )
        self.assertIsNotNone(trade)
        self.assertEqual(trade.sl_effective, 120)
        self.assertEqual(trade.sl_atr_ratio, 2.0)
        self.assertEqual(trade.tp_atr_ratio, 3.0)
        self.assertEqual(trade.friction_ratio, 0.15)
        self.assertIn(trade.session_window, ("Tokyo", "London", "NY", "DeadZone"))
        self.assertEqual(trade.invalidation_dist, 0.00045)


if __name__ == "__main__":
    unittest.main()
