"""Test binance_connector: parsing kline, rounding qty, validasi order, OCO params (mock HTTP)."""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
config.DRY_RUN = True  # pastikan dry-run di test

from src.core import binance_connector as connector  # noqa: E402


class FakeResponse:
    def __init__(self, data, code=200):
        self._data = json.dumps(data).encode("utf-8") if not isinstance(data, bytes) else data
        self.code = code

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch(method, fake):
    import urllib.request
    original = getattr(urllib.request, method)
    setattr(urllib.request, method, staticmethod(lambda *a, **k: fake))
    return original


def test_klines_parsing():
    failed = 0
    sample = [
        [1786000000000, "65000.0", "65100.0", "64900.0", "65050.0", "12.5", 1786000059999,
         "812345.6", 100, "10.0", "650000.0", "0"]
    ]
    orig = _patch("urlopen", FakeResponse(sample))
    try:
        df = connector.get_klines("BTCUSDT", "30m", 1)
        if df is None or len(df) != 1:
            print(f"FAIL klines: len {0 if df is None else len(df)}")
            failed += 1
        elif df.iloc[0]["close"] != 65050.0 or df.iloc[0]["high"] != 65100.0:
            print("FAIL klines: nilai candle")
            failed += 1
    finally:
        _patch("urlopen", orig)
    return failed


def test_round_qty():
    failed = 0
    # step size 0.00001 → floor ke kelipatan
    info = {"symbol": "BTCUSDT", "filters": {"step_size": 0.00001, "min_qty": 0.00001}}
    connector._symbol_info_cache["BTCUSDT"] = info
    r = connector.round_qty("BTCUSDT", 0.00012345)
    if r != 0.00012:
        print(f"FAIL round_qty: got {r}, expected 0.00012")
        failed += 1
    return failed


def test_validate_order():
    failed = 0
    info = {"symbol": "BTCUSDT", "filters": {"step_size": 0.00001, "min_qty": 0.00001, "min_notional": 5.0}}
    connector._symbol_info_cache["BTCUSDT"] = info
    ok, _ = connector.validate_order("BTCUSDT", 0.0001, 65000.0)  # $6.5 >= $5
    if not ok:
        print("FAIL validate: order $6.5 harus lolos")
        failed += 1
    ok2, reason = connector.validate_order("BTCUSDT", 0.00001, 65000.0)  # $0.65 < $5
    if ok2:
        print("FAIL validate: order $0.65 harus ditolak (min notional)")
        failed += 1
    return failed


def test_ticker():
    failed = 0
    sample = {"symbol": "BTCUSDT", "bidPrice": "65000.00", "askPrice": "65001.00"}
    orig = _patch("urlopen", FakeResponse(sample))
    try:
        t = connector.get_ticker("BTCUSDT")
        if t is None or t["bid"] != 65000.0 or t["ask"] != 65001.0:
            print("FAIL ticker")
            failed += 1
        elif t["spread_pct"] <= 0:
            print("FAIL ticker spread_pct")
            failed += 1
    finally:
        _patch("urlopen", orig)
    return failed


if __name__ == "__main__":
    total = 0
    for fn in (test_klines_parsing, test_round_qty, test_validate_order, test_ticker):
        total += fn()
    print(f"\n{'✅ SEMUA TEST PASS' if total == 0 else f'❌ {total} TEST GAGAL'}")
    sys.exit(1 if total else 0)
