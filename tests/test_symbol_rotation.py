"""Test symbol rotation logic (weekday XAUUSD, weekend BTCUSD)."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from zoneinfo import ZoneInfo
import config

WIB = ZoneInfo("Asia/Jakarta")
config.ENABLE_BTC_ROTATION = True


def test_active_symbol():
    cases = [
        ("Jumat 21:59", datetime(2026, 8, 7, 21, 59, tzinfo=WIB), config.WEEKDAY_SYMBOL),
        ("Jumat 22:00", datetime(2026, 8, 7, 22, 0, tzinfo=WIB), config.WEEKEND_SYMBOL),
        ("Sabtu 12:00", datetime(2026, 8, 8, 12, 0, tzinfo=WIB), config.WEEKEND_SYMBOL),
        ("Minggu 23:59", datetime(2026, 8, 9, 23, 59, tzinfo=WIB), config.WEEKEND_SYMBOL),
        ("Senin 00:00", datetime(2026, 8, 10, 0, 0, tzinfo=WIB), config.WEEKDAY_SYMBOL),
        ("Rabu 10:00", datetime(2026, 8, 12, 10, 0, tzinfo=WIB), config.WEEKDAY_SYMBOL),
    ]
    failed = 0
    for label, dt, expected in cases:
        got = config.get_active_symbol(dt)
        ok = got == expected
        failed += 0 if ok else 1
        print(f"{'OK  ' if ok else 'FAIL'} {label}: expected={expected} got={got}")
    return failed


def test_per_symbol_helpers():
    failed = 0
    # XAU helpers (default naik ke 400/800 — ATR M5 XAU ~300 pts, gate
    # butuh SL >= 1.25x ATR ~375+)
    assert config.lot_size_for("XAUUSD-ECNc") == 0.01
    assert config.default_sl_points_for("XAUUSD-ECNc") == 400
    assert config.default_tp_points_for("XAUUSD-ECNc") == 800
    assert config.max_spread_points_for("XAUUSD-ECNc") == 50
    # FX pairs (H1 swing, FASE 1): default flat 100/200 pts (10/20 pips EURJPY scale)
    for sym in ["EURJPY-ECNc", "GBPCHF-ECNc", "GBPNZD-ECNc", "EURCHF-ECNc", "GBPUSD-ECNc", "EURAUD-ECNc"]:
        assert config.default_sl_points_for(sym) == 100
        assert config.default_tp_points_for(sym) == 200
    # BTC helpers (scaled for BTC point size — see config comments)
    assert config.lot_size_for("BTCUSD.c") == 0.01
    assert config.default_sl_points_for("BTCUSD.c") == config.DEFAULT_SL_POINTS_BTC
    assert config.default_tp_points_for("BTCUSD.c") == config.DEFAULT_TP_POINTS_BTC
    assert config.max_spread_points_for("BTCUSD.c") == config.MAX_SPREAD_POINTS_BTC
    # is_crypto
    assert config.is_crypto("BTCUSD.c") is True
    assert config.is_crypto("XAUUSD-ECNc") is False
    # Timeframe per-symbol (FASE 1): XAU M5 scalping, FX H1 swing, BTC M30
    assert config.get_timeframe("XAUUSD-ECNc") == config.TIMEFRAME
    assert config.get_timeframe("EURJPY-ECNc") == config.H1_TIMEFRAME
    assert config.get_timeframe("GBPCHF-ECNc") == config.H1_TIMEFRAME
    assert config.get_timeframe("BTCUSD.c") == config.mt5.TIMEFRAME_M30
    # Risk per-trade (FASE 1): XAU 0.5%, FX 1.0%, BTC 1.5%
    assert config.risk_percent_for("XAUUSD-ECNc") == config.RISK_PERCENT_XAU
    assert config.risk_percent_for("EURJPY-ECNc") == 1.0
    assert config.risk_percent_for("GBPNZD-ECNc") == 1.0
    assert config.risk_percent_for("BTCUSD.c") == config.RISK_PERCENT_BTC
    print("OK  per-symbol helpers (lot/sl/tp/spread/is_crypto/timeframe/risk)")
    return failed

def test_rotation_pool():
    failed = 0
    pool = config.get_rotation_pool()
    # FASE 1: pool = 1 XAU + 6 FX (MAX_ROTATION_SYMBOLS = 7)
    assert len(pool) == 7, f"pool harus 7 simbol, dapat {len(pool)}: {pool}"
    assert pool[0] == config.WEEKDAY_SYMBOL
    for sym in config.FX_PAIR_SYMBOLS:
        assert sym in pool, f"{sym} harus ada di pool"
    print(f"OK  rotation pool: {pool}")
    return failed


def test_refresh_symbol():
    failed = 0
    # Simulate: currently XAU, at Saturday -> should switch to BTC
    saturday = datetime(2026, 8, 8, 10, 0, tzinfo=WIB)
    # reset internal state first
    config.refresh_active_symbol(datetime(2026, 8, 5, 10, 0, tzinfo=WIB))  # Wednesday
    config.refresh_active_symbol(saturday)
    new_sym, changed = config.refresh_active_symbol(saturday)
    ok = (new_sym == config.WEEKEND_SYMBOL and changed is False)
    failed += 0 if ok else 1
    print(f"{'OK  ' if ok else 'FAIL'} refresh: active={new_sym} changed={changed}")
    # Now switch back to Monday
    monday = datetime(2026, 8, 10, 0, 0, tzinfo=WIB)
    new_sym, changed = config.refresh_active_symbol(monday)
    ok = (new_sym == config.WEEKDAY_SYMBOL and changed is True)
    failed += 0 if ok else 1
    print(f"{'OK  ' if ok else 'FAIL'} refresh: active={new_sym} changed={changed}")
    return failed


if __name__ == "__main__":
    total = 0
    total += test_active_symbol()
    total += test_per_symbol_helpers()
    total += test_rotation_pool()
    total += test_refresh_symbol()
    print(f"\n{'PASS' if total == 0 else 'FAIL'} — {total} failures")
    sys.exit(1 if total else 0)
