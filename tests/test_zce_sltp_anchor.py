"""
Unit test ZCE SL/TP anchor gate (Fase 3, task #7) — sintetik, tanpa MT5 live.
Memverifikasi:
  1. Mode shadow/off (default): ceiling lama tetap clamp (perilaku 1:1, tidak berubah).
  2. Mode legacy/full (ZCE supply walls): SL anchor > ceiling -> SKIP ANCHOR_TOO_WIDE (ok=False).
  3. Mode legacy/full: ATR gagal dimuat -> REJECT ATR_UNAVAILABLE (tanpa fallback statis).

Run: python -m pytest tests/test_zce_sltp_anchor.py -q
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest

import config
from src.core.consensus import _apply_sltp_rules


def _rates_ndarray(n=60, base=1.10000, step=0.00030):
    """Structured numpy array meniru output MT5 copy_rates (ATR > 0)."""
    dtype = [("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"),
             ("close", "f8"), ("tick_volume", "i8"), ("spread", "i4"),
             ("real_volume", "i8")]
    arr = np.zeros(n, dtype=dtype)
    px = base
    for i in range(n):
        arr[i]["time"] = i
        arr[i]["open"] = px
        arr[i]["high"] = px + step
        arr[i]["low"] = px - step
        arr[i]["close"] = px + step * 0.4
        arr[i]["tick_volume"] = 100
        px += step * 0.5
    return arr


@pytest.fixture()
def mt5_ok(monkeypatch):
    """Mock MT5 data sehat: spread kecil + ATR tersedia."""
    monkeypatch.setattr(config.mt5, "symbol_info",
                        lambda sym: type("SI", (), {"point": 0.00001})())
    monkeypatch.setattr(config.mt5, "symbol_info_tick",
                        lambda sym: type("TK", (), {"bid": 1.10000, "ask": 1.10001})())
    monkeypatch.setattr(config.mt5, "copy_rates_from_pos",
                        lambda sym, tf, start, n: _rates_ndarray())
    monkeypatch.setattr(config, "get_timeframe", lambda sym: 16385)  # MT5 H1
    monkeypatch.setattr(config, "sltp_mode_for", lambda sym: "LLM")


@pytest.fixture()
def mt5_atr_gagal(monkeypatch):
    """Mock MT5 sehat tapi copy_rates None (ATR gagal)."""
    monkeypatch.setattr(config.mt5, "symbol_info",
                        lambda sym: type("SI", (), {"point": 0.00001})())
    monkeypatch.setattr(config.mt5, "symbol_info_tick",
                        lambda sym: type("TK", (), {"bid": 1.10000, "ask": 1.10001})())
    monkeypatch.setattr(config.mt5, "copy_rates_from_pos",
                        lambda sym, tf, start, n: None)
    monkeypatch.setattr(config, "get_timeframe", lambda sym: 16385)  # MT5 H1
    monkeypatch.setattr(config, "sltp_mode_for", lambda sym: "LLM")


def _set_zce(monkeypatch, enabled: bool, mode: str):
    monkeypatch.setattr(config, "ZCE_ENABLED", enabled)
    monkeypatch.setattr(config, "ZCE_MODE", mode)


def test_mode_off_ceiling_clamp_tetap(mt5_ok, monkeypatch):
    """Default (off/shadow): SL runaway tetap di-clamp ke ceiling — perilaku lama."""
    _set_zce(monkeypatch, False, "shadow")
    sl, tp, ok, reason = _apply_sltp_rules(
        sl_points=5000, tp_points=6000, symbol="EURUSD-ECNc")
    assert ok is True
    # ceiling = atr * 2.5; ATR sintetik ~0.0005 -> ~50 pts * 2.5 = 125 pts -> SL di-clamp
    assert sl < 5000
    assert "ANCHOR_TOO_WIDE" not in reason


def test_mode_legacy_anchor_too_wide_skip(mt5_ok, monkeypatch):
    """Mode legacy (ZCE supply walls): SL anchor > ceiling -> SKIP, bukan clamp."""
    _set_zce(monkeypatch, True, "legacy")
    sl, tp, ok, reason = _apply_sltp_rules(
        sl_points=5000, tp_points=6000, symbol="EURUSD-ECNc")
    assert ok is False
    assert "ANCHOR_TOO_WIDE" in reason
    # Nilai SL tidak diubah (skip total), bukan diparkir ke ceiling
    assert sl == 5000


def test_mode_full_atr_gagal_reject(mt5_atr_gagal, monkeypatch):
    """Mode full: ATR gagal -> REJECT ATR_UNAVAILABLE, tanpa fallback statis 350."""
    _set_zce(monkeypatch, True, "full")
    sl, tp, ok, reason = _apply_sltp_rules(
        sl_points=200, tp_points=300, symbol="EURUSD-ECNc")
    assert ok is False
    assert "ATR_UNAVAILABLE" in reason


def test_mode_off_atr_gagal_fallback_statistik(mt5_atr_gagal, monkeypatch):
    """Mode off: ATR gagal tetap pakai fallback statis (regresi perilaku lama)."""
    _set_zce(monkeypatch, False, "shadow")
    sl, tp, ok, reason = _apply_sltp_rules(
        sl_points=200, tp_points=300, symbol="EURUSD-ECNc")
    assert ok is True
    assert "ANCHOR_TOO_WIDE" not in reason
    assert "ATR_UNAVAILABLE" not in reason
