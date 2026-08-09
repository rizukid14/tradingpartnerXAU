"""Test dashboard parser, metrics, dan renderer (konvensi proyek: fungsi test_* + return failed)."""
import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dashboard  # noqa: E402

SAMPLE_LOG = """\
============================================================
    BOT TRADING MULTI-LLM CONSENSUS - PROTECTED EXECUTION    
============================================================
Mode: 🔥 LIVE EXECUTION (Duit Asli/Demo)
Simbol: BTCUSD.c | Timeframe: M30 | Lot Size: 0.01
Models: OpenAI (gpt-5.4-mini), Gemini (gemini-3.5-flash-lite), Claude (claude-sonnet-4-6)
------------------------------------------------------------
[MT5] Mencoba masuk ke akun 27556325 pada server VTMarkets-Live 3...
[MT5] Login berhasil!
✅ Terhubung ke MT5 dengan sukses!
⚡ [CYCLE START] Memulai analisa market pada 2026-08-09 13:50:33...
📈 Harga saat ini BTCUSD.c - Bid: 64847.66, Ask: 64864.77, Spread: 1711.0 pts
⏱️ [LATENSI MODEL (Ronde 1)] OpenAI: 1.87s | Gemini: 1.24s | Claude: 3.48s (Total: 3.49s)
🤖 [Gemini] Decision: SELL (Conf: 72.0%)
   SL: 8300 pts, TP: 13500 pts
   Reason: Bearish multi-horizon forecast aligns with H1 pressure.
🤖 [OpenAI] Decision: SELL (Conf: 68.0%)
   SL: 8200 pts, TP: 12300 pts
   Reason: M30 remains below EMA20.
🤖 [Claude] Decision: SELL (Conf: 68.0%)
   SL: 8000 pts, TP: 14000 pts
   Reason: Price within optimal entry zone.
🚀 [KONSENSUS DISETUJUI] Sinyal: SELL (skor 2.08 >= threshold 1.8)
   Model yang sepakat: Gemini, OpenAI, Claude
   Rata-rata Keyakinan: 69.3%
🔥 [UNANIMOUS 3/3 HIGH CONFIDENCE] Ketiga AI sepakat SELL! Membuka 2 posisi sekaligus (Sisa slot: 6)...
[MT5] Mengirim order: SELL BTCUSD.c 0.19 lot pada harga 64847.58 (SL: 64929.24, TP: 64714.92)...
[MT5] Order BERHASIL! Ticket: 1161839635
🎉 Sukses menempatkan order #1: SELL (Ticket: 1161839635, Lot: 0.19)
[MT5] Mengirim order: SELL BTCUSD.c 0.19 lot pada harga 64847.04 (SL: 64928.7, TP: 64687.85)...
[MT5] Order BERHASIL! Ticket: 1161839638
🎉 Sukses menempatkan order #2: SELL (Ticket: 1161839638, Lot: 0.19)
⚡ [CYCLE START] Memulai analisa market pada 2026-08-09 14:20:33...
📈 Harga saat ini BTCUSD.c - Bid: 64800.0, Ask: 64817.0, Spread: 1700.0 pts
⏱️ [LATENSI MODEL (Ronde 1)] OpenAI: 2.0s | Gemini: 1.5s | Claude: 3.0s (Total: 3.0s)
🤖 [Gemini] Decision: HOLD (Conf: 55.0%)
   SL: 0 pts, TP: 0 pts
   Reason: Waiting.
🤖 [OpenAI] Decision: HOLD (Conf: 60.0%)
   SL: 0 pts, TP: 0 pts
   Reason: Waiting.
🤖 [Claude] Decision: HOLD (Conf: 65.0%)
   SL: 0 pts, TP: 0 pts
   Reason: Waiting.
🚨 [KONSENSUS GAGAL] Tidak memenuhi threshold konsensus (2 model). Posisi: HOLD.
🔮 [FORECAST INFO] Bias: BEARISH | Proyeksi R:R (T+1h/T+4h): 0.79
[POST-MORTEM] Menganalisis hasil trade tiket #1161839635 (BTCUSD.c, P/L: -14.75)...
💡 [PELAJARAN BARU DITERIMA] [entry] [LESSON] Avoid 5-minute BTC scalps when price is stretched.
"""


def _write_sample(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(SAMPLE_LOG)
    return path


def test_parser_events():
    failed = 0
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as tf:
        tf.write(SAMPLE_LOG)
        path = tf.name
    try:
        events = dashboard.parse_log(path)
        types = [e["type"] for e in events]
        # session, cycle, price, latency, decisions, consensus, order, trade_close, lesson, forecast
        checks = {
            "session": 1,
            "cycle": 2,
            "latency": 2,
            "model_decision": 6,
            "consensus": 2,
            "order": 2,
            "trade_close": 1,
            "lesson": 1,
            "forecast": 1,
        }
        for typ, cnt in checks.items():
            got = types.count(typ)
            if got != cnt:
                print(f"FAIL parser: {typ} expected {cnt} got {got}")
                failed += 1
        # order fields
        orders = [e for e in events if e["type"] == "order"]
        if orders[0]["ticket"] != 1161839635:
            print(f"FAIL parser: ticket {orders[0]['ticket']}")
            failed += 1
        if orders[0]["side"] != "SELL" or orders[0]["symbol"] != "BTCUSD.c":
            print("FAIL parser: order side/symbol")
            failed += 1
        if abs(orders[0]["lot"] - 0.19) > 1e-9:
            print(f"FAIL parser: lot {orders[0]['lot']}")
            failed += 1
        # consensus approved fields
        cons = [e for e in events if e["type"] == "consensus" and e["approved"]]
        if not cons or cons[0]["signal"] != "SELL" or cons[0]["score"] != 2.08:
            print(f"FAIL parser: consensus {cons}")
            failed += 1
        # trade_close
        tc = [e for e in events if e["type"] == "trade_close"]
        if tc[0]["pnl"] != -14.75:
            print(f"FAIL parser: close pnl {tc[0]['pnl']}")
            failed += 1
        # cycle ts
        cycles = [e for e in events if e["type"] == "cycle"]
        if cycles[0]["ts"] is None:
            print("FAIL parser: cycle ts")
            failed += 1
    finally:
        os.unlink(path)
    return failed


def test_metrics():
    failed = 0
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as tf:
        tf.write(SAMPLE_LOG)
        path = tf.name
    try:
        events = dashboard.parse_log(path)
        # state: risk_state with known_closed (both orders closed)
        state = {
            "risk_state": {"known_closed": [1161839635, 1161839638]},
            "memory_lessons": {
                "BTCUSD.c": {
                    "lessons": [
                        {"symbol": "BTCUSD.c", "lesson": "[LESSON] test", "theme": "entry"}
                    ],
                    "lessons_summary": "",
                }
            },
            "decision_memory": {},
            "dynamic_rules": {},
            "forecast_cache": {},
        }
        m = dashboard.compute_metrics(events, state)
        s = m["summary"]
        if s["total_orders"] != 2:
            print(f"FAIL metrics: total_orders {s['total_orders']}")
            failed += 1
        if s["total_closed"] != 1:
            print(f"FAIL metrics: total_closed {s['total_closed']}")
            failed += 1
        if s["net_pnl"] != -14.75:
            print(f"FAIL metrics: net_pnl {s['net_pnl']}")
            failed += 1
        if s["win_rate"] != 0.0:
            print(f"FAIL metrics: win_rate {s['win_rate']}")
            failed += 1
        if s["total_cycles"] != 2:
            print(f"FAIL metrics: total_cycles {s['total_cycles']}")
            failed += 1
        # model stats
        ms = m["model_stats"]
        if "Gemini" not in ms or ms["Gemini"]["n"] != 2:
            print(f"FAIL metrics: model_stats Gemini {ms.get('Gemini')}")
            failed += 1
        # agreement: 2 cycles, 1 ge2 (SELL x3), 1 split? second cycle all HOLD
        if m["agreement"]["ge2"] != 1:
            print(f"FAIL metrics: agreement ge2 {m['agreement']['ge2']}")
            failed += 1
        # lessons
        if len(m["lessons"]) != 1:
            print(f"FAIL metrics: lessons {len(m['lessons'])}")
            failed += 1
        # trades table
        if len(m["trades"]) != 2:
            print(f"FAIL metrics: trades {len(m['trades'])}")
            failed += 1
        # consensus approved
        if s["consensus_approved"] != 1 or s["consensus_failed"] != 1:
            print(f"FAIL metrics: consensus {s['consensus_approved']}/{s['consensus_failed']}")
            failed += 1
    finally:
        os.unlink(path)
    return failed


def test_render():
    failed = 0
    with tempfile.NamedTemporaryFile("w", suffix=".log", delete=False, encoding="utf-8") as tf:
        tf.write(SAMPLE_LOG)
        path = tf.name
    try:
        events = dashboard.parse_log(path)
        m = dashboard.compute_metrics(events, {"risk_state": {"known_closed": [1161839635, 1161839638]}})
        html = dashboard.render_html(m)
        for needle in ("<html", "chart-equity", "chart-decisions", "trades-table",
                       "DATA =", "Kualitas Sinyal", "Equity Curve", "Lessons &amp; Post-Mortem"):
            if needle not in html:
                print(f"FAIL render: missing {needle}")
                failed += 1
    finally:
        os.unlink(path)
    return failed


def test_load_json_defensive():
    failed = 0
    # file tidak ada → None
    if dashboard._load_json("__nonexistent__.json") is not None:
        print("FAIL load_json: nonexistent should be None")
        failed += 1
    return failed


if __name__ == "__main__":
    total = 0
    for fn in (test_parser_events, test_metrics, test_render, test_load_json_defensive):
        total += fn()
    print(f"\n{'✅ SEMUA TEST PASS' if total == 0 else f'❌ {total} TEST GAGAL'}")
    sys.exit(1 if total else 0)
