"""P4 — Dashboard sync: field kekuatan layer ZCE diteruskan ke payload cockpit.

Memverifikasi bahwa `_consolidate_zce_zones` membawa `confluence`, `tf_max`,
`horizon_max`, `at_price` dari ZoneMapResult ke dict yang dipakai UI.
"""

from types import SimpleNamespace

import dashboard as dash


def _layer(price, kind, grade, score, conf, tf, hz, at_price=False):
    return {
        "price": price,
        "band_low": price - 0.00005,
        "band_high": price + 0.00005,
        "tier": "C1",
        "grade": grade,
        "density_score": score,
        "tag": "C_EQH@D1",
        "tfs_present": ["H1", "D1"],
        "kinds_present": [kind],
        "is_cold": False,
        "is_vacuum": False,
        "confluence": conf,
        "tf_max": tf,
        "horizon_max": hz,
        "at_price": at_price,
    }


def test_dashboard_forwards_layer_strength_fields():
    zm = SimpleNamespace(
        floors=[_layer(1.60000, "EQL", "GRADE_3_MACRO", 9.0, 6, "D1", 250)],
        ceilings=[_layer(1.61000, "EQH", "GRADE_2_INTERMEDIATE", 5.0, 4, "H1", 150, at_price=True)],
        clusters=[],
    )
    mid = 1.60500
    out = dash._consolidate_zce_zones(
        zm, mid,
        v_lo=1.58000, v_hi=1.63000,
        atr_val=0.00080, pip_val=0.00010, digits=5,
    )

    assert out, "harus menghasilkan kandidat layer"
    by_type = {w["type"]: w for w in out}
    assert "floor" in by_type and "ceiling" in by_type

    fl = by_type["floor"]
    assert fl["confluence"] == 6
    assert fl["tf_max"] == "D1"
    assert fl["horizon_max"] == 250
    assert fl["grade"] == "GRADE_3_MACRO"

    ce = by_type["ceiling"]
    assert ce["confluence"] == 4
    assert ce["at_price"] is True
    assert ce["horizon_max"] == 150


def test_label_shows_confluence_and_at_price_marker():
    """Label tangga harus memuat jumlah sumber confluence dan penanda at-price."""
    zm = SimpleNamespace(
        floors=[],
        ceilings=[_layer(1.61000, "EQH", "GRADE_3_MACRO", 9.0, 6, "D1", 250, at_price=True)],
        clusters=[],
    )
    out = dash._consolidate_zce_zones(
        zm, 1.60500,
        v_lo=1.58000, v_hi=1.63000,
        atr_val=0.00080, pip_val=0.00010, digits=5,
    )
    assert out
    label = out[0].get("label", "")
    assert "6src" in label, f"label harus memuat jumlah sumber confluence: {label!r}"
    assert label.startswith("~"), f"layer at-price harus ditandai: {label!r}"


def test_dashboard_handles_missing_strength_fields_gracefully():
    """Layer lama (tanpa field P3) tidak boleh error — default aman."""
    zm = SimpleNamespace(
        floors=[{"price": 1.60000, "band_low": 1.59995, "band_high": 1.60005}],
        ceilings=[{"price": 1.61000, "band_low": 1.60995, "band_high": 1.61005}],
        clusters=[],
    )
    out = dash._consolidate_zce_zones(
        zm, 1.60500,
        v_lo=1.58000, v_hi=1.63000,
        atr_val=0.00080, pip_val=0.00010, digits=5,
    )
    assert out
    for w in out:
        assert w["confluence"] == 0
        assert w["tf_max"] == ""
        assert w["horizon_max"] == 0
        assert w["at_price"] is False
