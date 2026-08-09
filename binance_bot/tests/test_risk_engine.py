"""Test risk_engine: sizing, daily loss, consensus 2+1 (mock connector)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
config.DRY_RUN = True

from src.core import binance_connector as connector  # noqa: E402
from src.core.risk_engine import RiskEngine  # noqa: E402
from src.core import consensus  # noqa: E402


def test_consensus_2_2():
    failed = 0
    proposals = {
        "OpenAI": {"signal": "BUY", "confidence": 0.65, "sl_pct": 1.0, "tp_pct": 2.0, "reasoning": "x"},
        "Gemini": {"signal": "BUY", "confidence": 0.62, "sl_pct": 1.2, "tp_pct": 2.5, "reasoning": "y"},
    }
    dec = consensus.calculate_consensus(proposals)
    if not dec["approved"] or dec["signal"] != "BUY":
        print("FAIL consensus: 2/2 BUY harus approve")
        failed += 1
    if dec["score"] < 1.27 or dec["score"] > 1.28:
        print(f"FAIL consensus: score {dec['score']}")
        failed += 1
    return failed


def test_consensus_split():
    failed = 0
    proposals = {
        "OpenAI": {"signal": "BUY", "confidence": 0.9, "sl_pct": 1.0, "tp_pct": 2.0, "reasoning": "x"},
        "Gemini": {"signal": "HOLD", "confidence": 0.0, "sl_pct": None, "tp_pct": None, "reasoning": "y"},
    }
    dec = consensus.calculate_consensus(proposals)
    if dec["approved"]:
        print("FAIL consensus: 1 BUY + 1 HOLD harus HOLD")
        failed += 1
    return failed


def test_sizing():
    failed = 0
    engine = RiskEngine()
    # Mock equity $12, harga $65000, SL 1%
    # risk = 1.5% * 12 = $0.18; sl_dist = 650; qty = 0.18/650 = 0.0002769 → round 0.00027
    # notional = 0.00027 * 65000 = $17.55 — tapi equity $12 harusnya cuma bisa ~$12
    # qty dari risk% itu yang benar; cek hasilnya bukan None kalau notional >= min
    connector.get_account_balance_usdt = lambda: 12.0
    connector.round_qty = lambda s, q: round(int(q / 0.00001) * 0.00001, 5)
    connector.validate_order = lambda s, q, p: (True, "")
    config.MIN_NOTIONAL_USD = 1.0
    qty, msg = engine.get_effective_qty(65000.0, 1.0)
    if qty is None:
        print(f"FAIL sizing: {msg}")
        failed += 1
    elif abs(qty - 0.00027) > 1e-6:
        print(f"FAIL sizing: qty {qty}, expected ~0.00027")
        failed += 1
    return failed


def test_daily_loss_gate():
    failed = 0
    engine = RiskEngine()
    connector.get_closed_positions_today = lambda s=None: [{"profit": -4.0}]
    ok, reason = engine._check_daily_loss()
    if ok:
        print("FAIL daily loss: -$4 harus block (batas $3)")
        failed += 1
    connector.get_closed_positions_today = lambda s=None: [{"profit": -1.0}]
    ok, _ = engine._check_daily_loss()
    if not ok:
        print("FAIL daily loss: -$1 harus lolos")
        failed += 1
    return failed


if __name__ == "__main__":
    total = 0
    for fn in (test_consensus_2_2, test_consensus_split, test_sizing, test_daily_loss_gate):
        total += fn()
    print(f"\n{'✅ SEMUA TEST PASS' if total == 0 else f'❌ {total} TEST GAGAL'}")
    sys.exit(1 if total else 0)
