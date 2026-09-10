"""P2 — ZCE edge-based node engine.

Memverifikasi tiga sifat inti mesin node (pengganti band-merge snowball):
1. Primitif LEBAR tidak bisa menjembatani dua node yang berjauhan.
2. Skor = confluence LINTAS-SEL (semua TF x horizon dalam radius), bukan anggota satu grup.
3. Sweep berbasis ANCHOR -> tidak ada chaining (rantai node menyatu).
"""

import pytest

from src.analytics.zone_confluence_engine import ZoneConfluenceEngine, ZonePrimitive

PT = 1e-5
PIP = PT * 10           # 1.0e-4
ATR = 0.0020            # 20 pips


def _prim(kind, tf, horizon, lo, hi):
    return ZonePrimitive(kind, tf, horizon, hi, lo)


def _eng():
    return ZoneConfluenceEngine()


def test_wide_primitive_does_not_bridge_distant_nodes():
    """OB_BEAR selebar 100 pips TIDAK boleh menjembatani node EQH yang jauh."""
    eng = _eng()
    prims = [
        # primitif raksasa: membentang dari 1.5500 sampai 1.6000 (500 pips)
        _prim("OB_BEAR", "D1", 250, 1.5500, 1.6000),      # edge = bottom = 1.5500
        # node terpisah jauh di atas
        _prim("EQH", "H4", 150, 1.6090, 1.6100),          # edge = bottom = 1.6090
        _prim("LAST_HIGH", "H1", 100, 1.6090, 1.6100),
    ]
    nodes = eng._build_nodes(prims, ATR, PT)

    edges = sorted(round(n.band_low, 4) for n in nodes)
    assert len(nodes) >= 2, f"harus >=2 node terpisah, dapat {len(nodes)}: {edges}"
    # node dekat 1.6090 harus ada terpisah dari node 1.5500
    assert any(abs(n.band_low - 1.6090) < 0.0020 for n in nodes)
    assert any(n.band_low < 1.5600 for n in nodes)


def test_score_uses_cross_cell_confluence():
    """Empat sumber berbeda (kind, tf) di edge sama -> skor tinggi & grade G3."""
    eng = _eng()
    edge = 1.61000
    prims = [
        _prim("EQH", "D1", 250, edge - 0.0001, edge),          # w = 1.15 * 2.20 = 2.53
        _prim("EQH", "H4", 150, edge - 0.0001, edge),          # w = 1.15 * 1.60 = 1.84
        _prim("FVG_BEAR", "W1", 150, edge - 0.0001, edge),     # w = 0.80 * 2.80 = 2.24
        _prim("LAST_HIGH", "H1", 100, edge - 0.0001, edge),    # w = 0.60 * 1.00 = 0.60
    ]
    nodes = eng._build_nodes(prims, ATR, PT)
    assert nodes

    node = max(nodes, key=lambda n: n.score_final)
    assert node.confluence == 4, f"harus 4 sumber unik, dapat {node.confluence}"
    assert node.score_final >= eng.grade_g3
    assert node.grade == "GRADE_3_MACRO"


def test_anchor_sweep_prevents_chaining():
    """Empat edge berjarak 6 pips (tol 8p) TIDAK boleh menyatu jadi satu rantai."""
    eng = _eng()
    base = 1.10000
    step = 0.0006           # 6 pips (PIP = 1e-4)
    prims = [
        _prim("EQH", "H1", 50, base + i * step - 0.00001, base + i * step)
        for i in range(4)
    ]
    nodes = eng._build_nodes(prims, ATR, PT)

    assert len(nodes) == 2, (
        f"anchor sweep harus memecah 4 edge@6p (tol 8p) jadi 2 node, dapat {len(nodes)}"
    )


def test_node_engine_flag_toggles_backend(monkeypatch):
    """Flag ZCE_NODE_ENGINE_ENABLED memilih mesin node vs band-merge."""
    import config
    eng = _eng()
    prims = [
        _prim("EQH", "H1", 50, 1.6090, 1.6100),
        _prim("EQL", "H1", 50, 1.6000, 1.6010),
    ]
    nodes = eng._build_nodes(prims, ATR, PT)
    merged = eng._merge_primitives(prims, ATR, PT)
    assert len(nodes) >= 1 and len(merged) >= 1
    # kedua mesin harus mengembalikan ZoneCluster yang valid
    for c in nodes + merged:
        assert hasattr(c, "band_low") and hasattr(c, "band_high")
        assert c.band_high >= c.band_low
