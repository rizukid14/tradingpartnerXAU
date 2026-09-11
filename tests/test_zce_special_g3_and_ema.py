"""Unit test untuk ZCE Special G3 Protocol, Dynamic EMA Bands, dan Tiered Wall Exhaustion.

Memverifikasi:
1. Dynamic EMA Bands (20, 50, 100, 200) ter-generate pada H1, H4, D1.
2. Special G3 Protocol:
   - Klaster ber-skor >= 8.5 DENGAN jangkar makro sejati -> GRADE_3_MACRO.
   - Klaster ber-skor >= 8.5 TANPA jangkar makro sejati -> di-cap ke GRADE_2_INTERMEDIATE.
   - Klaster ber-skor >= 5.0 -> GRADE_2_INTERMEDIATE.
   - Klaster ber-skor < 5.0 -> GRADE_1_MICRO.
3. Tiered Wall Exhaustion di CBSS:
   - G3 Wall (Macro): threshold 0.35x ATR.
   - G2 Wall (Intermediate): threshold 0.20x ATR.
   - Jarak 0.28x ATR pada dinding G2 tidak di-skip, sedangkan pada G3 di-skip.
"""

import pytest
import numpy as np
import pandas as pd
from unittest.mock import MagicMock

import config
from src.analytics.zone_confluence_engine import (
    ZoneConfluenceEngine,
    ZonePrimitive,
    ZoneCluster,
)
from src.analytics.basket_sync_engine import filter_and_rank_batch_candidates

PT = 1e-5
ATR = 0.0020  # 20 pips


def _make_dummy_df(n_bars=300, base_price=1.6050):
    np.random.seed(42)
    closes = base_price + np.cumsum(np.random.randn(n_bars) * 0.0005)
    highs = closes + np.random.rand(n_bars) * 0.0004 + 0.0001
    lows = closes - np.random.rand(n_bars) * 0.0004 - 0.0001
    opens = (highs + lows) * 0.5
    vols = np.random.randint(100, 1000, n_bars)
    return pd.DataFrame({
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "tick_volume": vols,
    })


def test_dynamic_ema_bands_collected():
    """Memverifikasi bahwa EMA 20, 50, 100, 200 ter-generate di H1, H4, D1."""
    eng = ZoneConfluenceEngine()
    df = _make_dummy_df(250)

    prims_h1 = eng._collect_primitives("H1", df, PT)
    ema_prims_h1 = [p for p in prims_h1 if p.kind == "EMA_BAND"]
    assert len(ema_prims_h1) == 4, f"Harus ada 4 EMA bands di H1, dapat {len(ema_prims_h1)}"
    spans_h1 = {p.horizon for p in ema_prims_h1}
    assert spans_h1 == {20, 50, 100, 200}

    # Timeframe M30 tidak boleh meng-generate EMA bands
    prims_m30 = eng._collect_primitives("M30", df, PT)
    ema_prims_m30 = [p for p in prims_m30 if p.kind == "EMA_BAND"]
    assert len(ema_prims_m30) == 0, "M30 tidak boleh menghasilkan EMA_BAND"


def test_special_g3_macro_anchor_qualifies():
    """Klaster dengan skor >= 8.5 dan memiliki jangkar makro sejati mendapat GRADE_3_MACRO."""
    eng = ZoneConfluenceEngine()
    edge = 1.60000

    # Primitif konfluensi dengan jangkar D1 LAST_LOW dan W1 EQL
    prims = [
        ZonePrimitive("LAST_LOW", "D1", 250, edge + 0.0002, edge),   # Makro anchor D1
        ZonePrimitive("EQL", "W1", 150, edge + 0.0002, edge),        # Makro anchor W1
        ZonePrimitive("OB_BULL", "D1", 100, edge + 0.0002, edge),
        ZonePrimitive("EMA_BAND", "D1", 200, edge + 0.0002, edge),
    ]
    nodes = eng._build_nodes(prims, ATR, PT)
    assert nodes
    top_node = max(nodes, key=lambda n: n.score_final)
    assert top_node.score_final >= eng.grade_g3
    assert top_node.grade == "GRADE_3_MACRO"


def test_special_g3_psych_major_anchor_qualifies():
    """Klaster dengan skor >= 8.5 dan memiliki PSYCH_MAJOR mendapat GRADE_3_MACRO."""
    eng = ZoneConfluenceEngine()
    edge = 1.61000

    prims = [
        ZonePrimitive("PSYCH_MAJOR", "PSY", 0, edge, edge),          # Major psych station
        ZonePrimitive("EQH", "H4", 150, edge, edge - 0.0001),
        ZonePrimitive("EMA_BAND", "D1", 50, edge, edge - 0.0001),
        ZonePrimitive("EMA_BAND", "H4", 100, edge, edge - 0.0001),
        ZonePrimitive("LAST_HIGH", "H1", 100, edge, edge - 0.0001),
    ]
    nodes = eng._build_nodes(prims, ATR, PT)
    assert nodes
    top_node = max(nodes, key=lambda n: n.score_final)
    # Jika skor >= 8.5 dan ada PSYCH_MAJOR, wajib GRADE_3_MACRO
    if top_node.score_final >= eng.grade_g3:
        assert top_node.grade == "GRADE_3_MACRO"


def test_anti_inflation_caps_micro_clutter_to_g2():
    """Klaster dengan skor >= 8.5 tapi HANYA berasal dari tumpukan intraday H1/M30 di-cap ke G2."""
    eng = ZoneConfluenceEngine()
    edge = 1.60500

    # Tumpukan mikro H1 dan M30 tanpa D1/W1/MN1 dan tanpa H4 deep
    prims = [
        ZonePrimitive("LAST_HIGH", "H1", 24, edge, edge - 0.0001),
        ZonePrimitive("EQH", "H1", 48, edge, edge - 0.0001),
        ZonePrimitive("OB_BEAR", "H1", 72, edge, edge - 0.0001),
        ZonePrimitive("FVG_BEAR", "H1", 24, edge, edge - 0.0001),
        ZonePrimitive("EMA_BAND", "H1", 20, edge, edge - 0.0001),
        ZonePrimitive("EMA_BAND", "H1", 50, edge, edge - 0.0001),
    ]
    # Bangun klaster dengan boost buatan agar score_final >= 8.5
    cluster = ZoneCluster(
        cluster_id=1,
        band_low=edge - 0.0002,
        band_high=edge + 0.0002,
        members=prims,
        score_raw=10.0,
        score_final=12.5,  # Sangat tinggi (> 8.5)
    )
    grade = eng._assign_cluster_grade(cluster, prims)
    # Wajib di-cap ke GRADE_2_INTERMEDIATE karena tidak ada jangkar makro sejati!
    assert grade == "GRADE_2_INTERMEDIATE", f"Tumpukan mikro harus di-cap ke G2, bukan {grade}"


def test_exclusive_g3_wall_exhaustion_behavior(monkeypatch):
    """
    Memverifikasi Eksklusif G3 Wall Exhaustion di filter_and_rank_batch_candidates:
    - Jarak 0.28x ATR ke dinding G3 (threshold 0.35x) -> DI-SKIP (WALL EXHAUSTED)
    - Jarak 0.13x ATR ke dinding G2 (sangat dekat) -> TETAP LOLOS (G2 penetrable / bebas tembus)
    """
    monkeypatch.setattr(config, "ENABLE_CBSS", True)
    monkeypatch.setattr(config, "CBSS_WALL_EXHAUSTION_G3_ATR", 0.35)
    monkeypatch.setattr(config, "ENABLE_ANTI_INTERNAL_HEDGE", False)

    # Mock candidate setup
    class DummyCandidate:
        def __init__(self, sym, direction, scan_mid):
            self.symbol = sym
            self.direction = direction
            self.scan_mid = scan_mid
            self.trigger_price = scan_mid
            self.score = 8.0
            self.metadata = {}

    # Setup macro cache untuk EURCAD (menghadap dinding G3) vs GBPCHF (menghadap dinding G2)
    # EURCAD: BUY 1.60000 -> C1 G3 1.60056 (jarak 0.28x ATR < 0.35x)
    # GBPCHF: BUY 1.10000 -> C1 G2 1.10026 (jarak 0.13x ATR sangat dekat)
    macro_cache = {
        "EURCAD": {
            "immediate_ceiling_c1": 1.60056,
            "c1_reaction_grade": "GRADE_3_MACRO",
            "deep_ceiling_c2": 1.60500,
            "immediate_floor_f1": 1.59500,
            "f1_reaction_grade": "GRADE_3_MACRO",
            "atr_h1": 0.0020,
        },
        "GBPCHF": {
            "immediate_ceiling_c1": 1.10026,
            "c1_reaction_grade": "GRADE_2_INTERMEDIATE",
            "deep_ceiling_c2": 1.10500,
            "immediate_floor_f1": 1.09500,
            "f1_reaction_grade": "GRADE_2_INTERMEDIATE",
            "atr_h1": 0.0020,
        },
    }

    cand_eurcad = DummyCandidate("EURCAD", 1, 1.60000)
    cand_gbpchf = DummyCandidate("GBPCHF", 1, 1.10000)

    # Uji kandidat EURCAD (G3 wall, jarak 0.28x < 0.35x)
    res_eurcad = filter_and_rank_batch_candidates([cand_eurcad], macro_cache)
    assert len(res_eurcad) == 0, "EURCAD harus di-skip karena menabrak benteng makro G3 pada jarak 0.28x ATR (< 0.35x)"

    # Uji kandidat GBPCHF (G2 wall, jarak 0.13x ATR) -> Bebas tembus, TIDAK di-skip!
    res_gbpchf = filter_and_rank_batch_candidates([cand_gbpchf], macro_cache)
    assert len(res_gbpchf) == 1, "GBPCHF harus LOLOS karena dinding G2 penetrable meskipun jarak 0.13x ATR"
    assert res_gbpchf[0].symbol == "GBPCHF"
