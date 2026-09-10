"""P3 — ZCE layered map: aturan "harga di dalam zona" + confluence per layer.

Memverifikasi:
1. Layer yang menempel harga (< inside_band) TIDAK dipakai sebagai C1/F1.
2. Layer tersebut tetap muncul di tangga dan ditandai `at_price`.
3. Output `inside_zone` / `inside_tiers` / confluence terisi.
"""

import pytest

from src.analytics.zone_confluence_engine import (
    ZoneConfluenceEngine,
    ZoneCluster,
    ZonePrimitive,
)

CUR = 1.60600
ATR = 0.00080          # 8 pips
DIGITS = 5


def _cluster(cid, lo, hi, role, grade, score, confluence, kinds, tf, horizon):
    prim = ZonePrimitive(kinds[0], tf, horizon, hi, lo)
    c = ZoneCluster(
        cluster_id=cid,
        band_low=lo,
        band_high=hi,
        members=[prim],
        score_final=score,
        score_raw=score,
        grade=grade,
        fortress_tag=f"{'C_' if role == 'CEILING' else 'F_'}{'+'.join(kinds)}@{tf}",
        horizon_max=horizon,
        tfs_present=[tf],
        kinds_present=list(kinds),
        width_atr=round((hi - lo) / ATR, 3),
        inherent_role=role,
        confluence=confluence,
    )
    return c


def _walls(clusters):
    eng = ZoneConfluenceEngine()
    return eng._elect_walls(clusters, CUR, ATR, DIGITS)


def test_immediate_wall_never_skipped_and_at_price_flagged():
    clusters = [
        # menempel harga: +2..4 pips -> at_price
        _cluster(0, 1.60620, 1.60640, "CEILING", "GRADE_2_INTERMEDIATE", 5.0, 4, ["EQH"], "D1", 150),
        # wall nyata: +15 pips
        _cluster(1, 1.60750, 1.60760, "CEILING", "GRADE_3_MACRO", 11.0, 5, ["EQH", "EQL"], "W1", 250),
        # floor menempel harga: -2..4 pips
        _cluster(2, 1.60560, 1.60580, "FLOOR", "GRADE_1_MICRO", 2.0, 2, ["EQL"], "H1", 50),
        # floor nyata: -24 pips
        _cluster(3, 1.60350, 1.60360, "FLOOR", "GRADE_3_MACRO", 9.0, 6, ["EQL", "FVG_BULL"], "D1", 250),
    ]
    w = _walls(clusters)

    # F1 mutlak mengambil level terdekat sejati (anti-kebutaan radar, tidak dilewati _first_tradeable)
    assert w["imm_floor_f1"] == pytest.approx(1.60580, 1e-9), "F1 harus level terdekat di bawah harga"
    assert w["imm_floor_f1_grade"] == "GRADE_1_MICRO"
    # C1 diperluas ke 1.60750 karena pemisahan chamber minimum (4 pips < min_ch 8 pips)
    assert w["imm_ceiling_c1"] == pytest.approx(1.60750, 1e-9), "C1 stasiun pemisahan chamber sehat"
    assert w["imm_ceiling_c1_grade"] == "GRADE_3_MACRO"
    # Deep station F2 berada di stasiun berikutnya
    assert w["deep_floor_f2"] == pytest.approx(1.60360, 1e-9), "F2 harus level stasiun kedua"
    assert w["imm_floor_f1"] != w["deep_floor_f2"], "F1 dan F2 dilarang kolaps"


def test_at_price_layers_still_listed_in_ladder_with_flag():
    clusters = [
        _cluster(0, 1.60620, 1.60640, "CEILING", "GRADE_2_INTERMEDIATE", 5.0, 4, ["EQH"], "D1", 150),
        _cluster(1, 1.60750, 1.60760, "CEILING", "GRADE_3_MACRO", 11.0, 5, ["EQH", "EQL"], "W1", 250),
    ]
    w = _walls(clusters)

    prices = [l["price"] for l in w["ceilings"]]
    assert 1.60620 in prices, "layer @harga tetap tampil di tangga (peta) "
    assert 1.60750 in prices
    flags = {l["price"]: l["at_price"] for l in w["ceilings"]}
    assert flags[1.60620] is True
    assert flags[1.60750] is False


def test_inside_zone_and_confluence_exposed():
    clusters = [
        _cluster(0, 1.60620, 1.60640, "CEILING", "GRADE_2_INTERMEDIATE", 5.0, 4, ["EQH"], "D1", 150),
        _cluster(1, 1.60750, 1.60760, "CEILING", "GRADE_3_MACRO", 11.0, 5, ["EQH", "EQL"], "W1", 250),
        _cluster(2, 1.60560, 1.60580, "FLOOR", "GRADE_1_MICRO", 2.0, 2, ["EQL"], "H1", 50),
        _cluster(3, 1.60350, 1.60360, "FLOOR", "GRADE_3_MACRO", 9.0, 6, ["EQL", "FVG_BULL"], "D1", 250),
    ]
    w = _walls(clusters)

    assert w["inside_zone"] is True
    assert "C1" in w["inside_tiers"] or "F1" in w["inside_tiers"]
    assert w["layer_count"] == len(w["ceilings"]) + len(w["floors"])
    assert w["imm_ceiling_c1_confluence"] == 5
    assert w["imm_floor_f1_confluence"] == 2

    # tiap layer membawa metadata kekuatan
    for l in w["ceilings"] + w["floors"]:
        assert "confluence" in l
        assert "tf_max" in l
        assert "horizon_max" in l
        assert "grade" in l
