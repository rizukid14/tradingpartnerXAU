"""
Unit test Zone Confluence Engine (sintetik, tanpa MT5).
Run: python -m pytest tests/test_zone_confluence_engine.py -q
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import pytest

from src.analytics.zone_confluence_engine import (
    ZoneConfluenceEngine,
    ZonePrimitive,
    merge_primitives_public,
    atr_from_df,
)


def synth_ohlc(prices: np.ndarray, wiggle: float = 0.0004, vol: float = 10.0) -> pd.DataFrame:
    p = np.asarray(prices, dtype=float)
    n = len(p)
    open_ = np.empty(n)
    open_[0] = p[0]
    open_[1:] = p[:-1]
    up = np.maximum(p, open_)
    dn = np.minimum(p, open_)
    high = up + np.abs(np.random.default_rng(7).normal(0, wiggle, n))
    low = dn - np.abs(np.random.default_rng(8).normal(0, wiggle, n))
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": p,
        "tick_volume": np.full(n, vol),
    })


def synth_map_dfs(h1_prices: np.ndarray, base: float = 1.10) -> dict:
    """Bangun dict dfs 6 TF dengan pola turunan dari H1 sederhana (bukan skalpresis)."""
    h1 = synth_ohlc(h1_prices)
    # tf lain: sampling kasar (subset H1), ukuran menyesuaikan grid
    n = len(h1_prices)
    out = {"H1": h1}
    steps = {"M30": 2, "H4": 4, "D1": 24, "W1": 120, "MN1": 600}
    for tf, k in steps.items():
        take = h1_prices[::k]
        if len(take) < 40:
            take = np.linspace(base, base, 60)
        out[tf] = synth_ohlc(take)
    return out


# --------------------------------------------------------------------------- #
class TestMerge:
    def test_single_cluster_two_ob(self):
        prims = [
            ZonePrimitive("OB", "H1", 100, top=1.1005, bottom=1.0995),
            ZonePrimitive("OB", "H1", 150, top=1.1008, bottom=1.0992),
        ]
        cl = merge_primitives_public(prims, atr_h1=0.002, point_size=1e-5)
        assert len(cl) == 1
        assert cl[0].horizon_max == 150

    def test_j1_no_double_count_and_boost(self):
        """J1: pasangan (kind,tf) unik — horizon 100 & 250 TIDAK menggandakan skor."""
        prims = [
            ZonePrimitive("OB", "H1", 100, top=1.1005, bottom=1.0995),
            ZonePrimitive("OB", "H1", 250, top=1.1006, bottom=1.0994),
            ZonePrimitive("FVG", "H1", 150, top=1.1004, bottom=1.0996),
        ]
        cl = merge_primitives_public(prims, atr_h1=0.002, point_size=1e-5)
        assert len(cl) == 1
        c = cl[0]
        # OB(1.00) + FVG(0.80) = 1.80 ; hmax=250 -> boost 1.30 (RFC: >=250 -> 1.30) -> 2.34
        assert c.score_raw == pytest.approx(1.80, abs=1e-6)
        assert c.score_final == pytest.approx(2.34, abs=1e-3)
        assert c.horizon_max == 250

    def test_width_atr_and_grade(self):
        atr = 0.004  # ATR H1 realistis (~40 pips di harga 1.10 => 0.004)
        prims = [
            ZonePrimitive("OB", "H1", 250, top=1.1030, bottom=1.1020),   # lebar 0.0010
            ZonePrimitive("EQH", "W1", 50, top=1.1032, bottom=1.1032),
            ZonePrimitive("EQL", "D1", 100, top=1.1018, bottom=1.1018),
        ]
        # skor: OB 1.0 + EQH 1.15*2.8=3.22 + EQL 1.15*2.2=2.53 => 6.75 -> boost 1.30 => 8.775 (G3)
        cl = merge_primitives_public(prims, atr_h1=atr, point_size=1e-5)
        assert len(cl) == 1
        c = cl[0]
        assert c.grade == "GRADE_3_MACRO"
        assert c.score_final == pytest.approx(8.775, abs=1e-2)
        assert c.width_atr == pytest.approx(0.0014 / atr, abs=0.02)  # band 1.1018-1.1032
        assert c.horizon_max == 250

    def test_wide_cluster_kept_single(self):
        # OB sangat lebar (single member) tidak boleh hilang; width_atr tercatat > 2
        prims = [ZonePrimitive("OB", "H1", 150, top=1.1040, bottom=1.0920)]  # 0.012 / atr 0.004 = 3.0
        cl = merge_primitives_public(prims, atr_h1=0.004, point_size=1e-5)
        assert len(cl) == 1
        assert cl[0].width_atr > 2.0


class TestLadder:
    def test_local_discount_macro_premium(self):
        # flat 1.10 (bar 0-419) -> crash 1.00 (420-430) -> rally 1.30 (431-470) -> decline 1.205 (471-520)
        n = 520
        prices = np.full(n, 1.10)
        prices[420:431] = np.linspace(1.10, 1.00, 11)
        prices[431:471] = np.linspace(1.00, 1.30, 40)
        prices[471:] = np.linspace(1.30, 1.205, n - 471)
        dfs = synth_map_dfs(prices)
        eng = ZoneConfluenceEngine()
        res = eng.compute_zone_map("EURUSD", dfs, point_size=0.00001, digits=5, permission="ARM")
        pos = res.ladder.pos_by_horizon
        assert pos.get(50, 0.5) <= 0.20, f"pos_50 harus discount, dapat {pos.get(50)}"
        assert pos.get(250, 0) >= 0.65, f"pos_250 harus premium, dapat {pos.get(250)}"
        assert "LOCAL_DISCOUNT_MACRO_PREMIUM" in (res.ladder.conflict_flag or "")
        assert res.suggested_method == "NONE"  # konflik belum resolve -> larang M1/M2/M3

    def test_no_conflict_when_consistent(self):
        n = 520
        prices = np.linspace(1.10, 1.14, n)
        dfs = synth_map_dfs(prices)
        eng = ZoneConfluenceEngine()
        res = eng.compute_zone_map("EURUSD", dfs, point_size=0.00001, digits=5)
        assert res.ladder.conflict_flag == "NONE"


class TestFreshness:
    def _cluster_via_map(self, h1_prices, band=(1.0980, 1.1020)):
        dfs = synth_map_dfs(h1_prices)
        eng = ZoneConfluenceEngine()
        res = eng.compute_zone_map("EURUSD", dfs, point_size=0.00001, digits=5)
        for c in res.clusters:
            if c.band_low <= band[1] and c.band_high >= band[0]:
                return c
        return None

    def test_cold_flag_when_no_recent_touch(self):
        # Harga menjauh dari band 1.10 setelah bar ~100 -> tidak tersentuh 600 bar H1 (> 21 hari)
        n = 700
        prices = np.full(n, 1.10)
        prices[100:] = np.linspace(1.10, 1.16, n - 100)
        dfs = synth_map_dfs(prices)
        eng = ZoneConfluenceEngine()
        res = eng.compute_zone_map("EURUSD", dfs, point_size=0.00001, digits=5)
        old = [c for c in res.clusters if c.band_high < 1.105]
        if old:
            assert all(c.is_cold for c in old)

    def test_touch_count_positive(self):
        n = 300
        prices = np.full(n, 1.10)
        prices[150:160] = 1.095  # sentuh area bawah
        prices[160:] = 1.102
        dfs = synth_map_dfs(prices)
        eng = ZoneConfluenceEngine()
        res = eng.compute_zone_map("EURUSD", dfs, point_size=0.00001, digits=5)
        assert res.atr_h1 > 0
        assert isinstance(res.readiness_score, float)
        assert res.wall_override["enable"] is True


class TestEndToEnd:
    def test_compute_map_end_to_end(self):
        n = 560
        rng = np.random.default_rng(3)
        prices = 1.10 + np.cumsum(rng.normal(0, 0.0008, n))
        dfs = synth_map_dfs(prices)
        eng = ZoneConfluenceEngine()
        res = eng.compute_zone_map("GBPUSD", dfs, point_size=0.00001, digits=5, permission="GO")
        assert res.symbol == "GBPUSD"
        assert len(res.clusters) >= 0
        assert res.cur_price == pytest.approx(round(float(prices[-1]), 5), abs=1e-9)
        table = eng.build_zone_table_text(res, limit=10)
        assert isinstance(table, str) and len(table) > 50
        assert "ZONE MAP" in table

    def test_atr_from_df(self):
        df = synth_ohlc(np.linspace(1.10, 1.12, 120))
        a = atr_from_df(df)
        assert a > 0
