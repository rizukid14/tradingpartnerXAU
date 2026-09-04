"""
Unit test ZCE Chamber Clearance & Level Role Invariance (RFC 11 Phase-2, 4 Sep 2026).
Memverifikasi:
  1. Penusukan tipis di atas C1 (< 0.30x ATR) mempertahankan C1 sebagai Ceiling (tidak lompat ke floor).
  2. Penembusan bersih (>= 0.30x ATR) mengizinkan C1 bermigrasi sah menjadi F1 (RBS Floor).
  3. Penusukan tipis di bawah F1 (< 0.30x ATR) mempertahankan F1 sebagai Floor (tidak lompat ke ceiling).
  4. Penembusan bersih di bawah F1 mengizinkan F1 bermigrasi sah menjadi C1 (SBR Ceiling).
  5. Unifikasi timeframe: get_timeframe_str("USDJPY-ECNc") == "H1" dan SL floor H1.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.analytics.zone_confluence_engine import ZoneConfluenceEngine, ZoneCluster


class TestZCEChamberClearance(unittest.TestCase):
    def setUp(self):
        self.engine = ZoneConfluenceEngine()
        self.atr_h1 = 0.500  # 50 pips ATR H1
        self.probe_tol = 0.30 * self.atr_h1  # 0.150 (15 pips)

        # Cluster Plafon di 181.80 - 181.85 (seperti Asian High EURJPY)
        self.ceil_cluster = ZoneCluster(
            cluster_id=1,
            band_low=181.800,
            band_high=181.850,
            score_final=4.5,
            grade="GRADE_2_INTRADAY",
            fortress_tag="C_ASIAN_HIGH",
        )

        # Cluster Lantai di 180.00 - 180.05 (seperti Asian Low EURJPY)
        self.floor_cluster = ZoneCluster(
            cluster_id=2,
            band_low=180.000,
            band_high=180.050,
            score_final=4.5,
            grade="GRADE_2_INTRADAY",
            fortress_tag="F_ASIAN_LOW",
        )

    def test_c1_probe_zone_penetration_retains_ceiling(self):
        """
        Saat harga menusuk tipis di atas C1 (misal 181.864, menusuk 1.4 pips di atas 181.850),
        C1 HARUS TETAP DIKUNCI sebagai Ceiling, DILARANG lompat menjadi Floor!
        """
        cur_price = 181.864  # menusuk 0.014 (< 0.150 probe_tol)
        walls = self.engine._elect_walls([self.ceil_cluster], cur_price, self.atr_h1, digits=3)

        self.assertIsNotNone(walls["imm_ceiling_c1"], "C1 harus tetap terpilih saat dalam probe zone!")
        self.assertEqual(walls["imm_ceiling_c1"], 181.850)
        self.assertEqual(walls["ceilings"][0]["tag"], "C_ASIAN_HIGH")
        self.assertIsNone(walls["imm_floor_f1"], "F1 TIDAK BOLEH mengambil level C1 yang sedang ditusuk tipis!")
        self.assertEqual(len(walls["floors"]), 0)

    def test_c1_clean_breakout_migrates_to_floor(self):
        """
        Saat harga menembus bersih di atas C1 dengan jarak >= probe_tol (misal 182.020, > 181.850 + 0.150),
        C1 sah bermigrasi menjadi F1 (RBS Support Floor).
        """
        cur_price = 182.020  # menembus 0.170 (>= 0.150 probe_tol)
        walls = self.engine._elect_walls([self.ceil_cluster], cur_price, self.atr_h1, digits=3)

        self.assertIsNotNone(walls["imm_floor_f1"], "C1 harus sah menjadi F1 setelah chamber clearance!")
        self.assertEqual(walls["imm_floor_f1"], 181.850)
        self.assertIsNone(walls["imm_ceiling_c1"], "C1 lama tidak lagi menjadi Ceiling setelah ditembus bersih!")
        self.assertEqual(len(walls["ceilings"]), 0)

    def test_f1_probe_zone_penetration_retains_floor(self):
        """
        Saat harga menusuk tipis di bawah F1 (misal 179.986, menusuk 1.4 pips di bawah 180.000),
        F1 HARUS TETAP DIKUNCI sebagai Floor, DILARANG lompat menjadi Ceiling!
        """
        cur_price = 179.986  # menusuk 0.014 di bawah 180.000 (< 0.150 probe_tol)
        walls = self.engine._elect_walls([self.floor_cluster], cur_price, self.atr_h1, digits=3)

        self.assertIsNotNone(walls["imm_floor_f1"], "F1 harus tetap terpilih saat dalam probe zone!")
        self.assertEqual(walls["imm_floor_f1"], 180.000)
        self.assertEqual(walls["floors"][0]["tag"], "F_ASIAN_LOW")
        self.assertIsNone(walls["imm_ceiling_c1"], "C1 TIDAK BOLEH mengambil level F1 yang sedang ditusuk tipis!")
        self.assertEqual(len(walls["ceilings"]), 0)

    def test_f1_clean_breakdown_migrates_to_ceiling(self):
        """
        Saat harga menembus bersih di bawah F1 dengan jarak >= probe_tol (misal 179.830, < 180.000 - 0.150),
        F1 sah bermigrasi menjadi C1 (SBR Resistance Ceiling).
        """
        cur_price = 179.830  # tembus 0.170 di bawah band_low
        walls = self.engine._elect_walls([self.floor_cluster], cur_price, self.atr_h1, digits=3)

        self.assertIsNotNone(walls["imm_ceiling_c1"], "F1 harus sah menjadi C1 setelah breakdown chamber clearance!")
        self.assertEqual(walls["imm_ceiling_c1"], 180.000)
        self.assertIsNone(walls["imm_floor_f1"], "F1 lama tidak lagi menjadi Floor setelah breakdown bersih!")
        self.assertEqual(len(walls["floors"]), 0)

    def test_unified_h1_timeframe_and_jpy_sl_floor(self):
        """
        Verifikasi bahwa JPY crosses telah 100% seragam di H1 dan segmented floor JPY diatur untuk H1.
        """
        self.assertEqual(config.get_timeframe_str("USDJPY-ECNc"), "H1")
        self.assertEqual(config.get_timeframe_str("EURJPY-ECNc"), "H1")
        self.assertEqual(config.get_timeframe_str("GBPJPY-ECNc"), "H1")
        self.assertEqual(config.get_timeframe_str("GBPUSD-ECNc"), "H1")

        # Floor JPY H1: 250 pts fallback, multiplier 0.50x ATR
        floor_pts = config.get_sl_floor_points("USDJPY-ECNc", spread_pts=15, atr_points=600)
        # max(2*15 + 20 = 50, int(0.50 * 600) = 300, 250) -> 300 pts
        self.assertEqual(floor_pts, 300)


if __name__ == "__main__":
    unittest.main()
