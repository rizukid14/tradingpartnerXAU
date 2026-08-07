# AGENTS.md — Konteks Proyek Trading Bot

> Ringkasan cepat untuk sesi coding. Baca ini dulu sebelum ngapa-ngapain.

## Apa ini

Bot trading scalping **M5 multi-LLM consensus** (OpenAI + Gemini + DeepSeek) yang jalan di **MetaTrader 5**.
- Simbol weekday: **XAUUSD-ECNc** (Gold) → weekend: **BTCUSD.c** (rotasi otomatis, `config.get_active_symbol`)
- Timeframe: M5, scan tiap candle baru (loop 5 detik, full cycle tiap M5 close)
- Akun: **LIVE** `VTMarkets-Live 3` (login `27556325`) — jangan pernah test sembarangan tanpa konfirmasi
- Balance awal $1000, sekarang ~$1065
- Waktu semua pakai **WIB** (Asia/Jakarta)

## Cara jalanin

```bash
python main.py
```
- `config.DRY_RUN = False` → **LIVE trading** (order beneran dikirim). Jangan ubah tanpa bilang user.
- Log: `trading_bot.log` (auto-rotate 2MB, keep 5000 baris). **Log ini CAMPUR sesi demo + live** — akun demo lama `1157958` (ticket `568xxx`/`569xxx`), akun live `27556325` (ticket `1159xxx`). Jangan hitung profit dari log tanpa pisahin sesi — query MT5 langsung lebih akurat.

## Arsitektur file

| File | Fungsi |
|---|---|
| `main.py` | Loop utama: manage posisi tiap 5 detik, full cycle tiap candle M5 |
| `config.py` | Semua parameter: sesi WIB, spread, SL/TP ATR, proteksi, model |
| `src/core/llm_client.py` | **Build prompt + call 3 LLM paralel** (stateless, fresh session tiap call) |
| `src/core/consensus.py` | Konsensus 2/3 model (`CONSENSUS_THRESHOLD`), average SL/TP, close votes |
| `src/core/risk_engine.py` | Gate: spread, sesi, danger zone, daily loss, recovery mode, lot multiplier |
| `src/core/mt5_connector.py` | Order send/close, history deals, market data |
| `src/analytics/forecast_engine.py` | Forecast multi-horizon (T+15m/T+60m, invalidation, optimal entry zone) |
| `src/analytics/macro_analyst.py` | Fundamental + MTF (M30/H1) context, cache per symbol |
| `src/analytics/trade_evaluator.py` | Post-mortem tiap trade → lessons (`data/memory_lessons.json`) |
| `src/analytics/dynamic_config.py` | Adaptasi otomatis: win rate <40% → threshold 3/3; >70% → 2/3 |
| `src/analytics/position_manager.py` | Trailing stop, break-even, partial close |

## Alur cycle (main.py → run_trading_cycle)

1. `risk.can_trade()` — spread/sesi/danger zone/daily loss gate. Gagal → skip (nggak ada biaya LLM)
2. Ambil 50 candle M5 + tick
3. Post-mortem evaluasi trade tertutup + dynamic rules
4. **Panggil 3 LLM paralel** (decision prompt + forecast context + lessons + macro + open positions)
5. Konsensus 2/3 → BUY/SELL/HOLD, plus AI re-evaluator CLOSE posisi
6. `validate_forecast_trigger` — **HANYA INFORMATIONAL** (di-print, TIDAK ngeblokir eksekusi)
7. Cek max posisi, eksekusi order (2 posisi kalau 3/3 sepakat)

## Gate eksekusi yang SEBENERNYA (hard)

- Konsensus ≥ 2/3 model setuju (dynamic: bisa 3/3 kalau win rate rendah)
- Spread ≤ 50 pts (XAU) / 2400 pts (BTC)
- Session London/NY WIB + bukan danger zone (kecuali crypto)
- Max daily loss $50, max 3 consecutive loss, max 6 posisi (4 recovery)
- **TIDAK ada** gate confidence minimum numerik — LLM bebas kasih confidence berapa pun
- **TIDAK ada** gate entry zone numerik — `optimal_entry_min/max` di-load tapi nggak dipakai
- R:R ≥ 1.2 di forecast engine cuma print (informational)

## Status terkini (AGUSTUS 2026 — PENTING)

- **Prompt SUDAH diedit tapi BELUM di-commit** (`src/core/llm_client.py`):
  - Aturan "OPTIMAL ENTRY RANGE & R:R RULE" (paksa HOLD kalau R:R < 0.5) **DIHAPUS**
  - Diganti: "jangan tunggu pullback/breakout hipotetis; entry filter R:R ≥ 1.0; HOLD cuma kalau alasan konkret"
  - Evaluasi posisi diubah jadi "DECISION REQUIRED" (CLOSE/HOLD wajib per ticket + alasan kuantitatif)
- **Kenapa diubah**: user komplain prompt lama bikin jarang entry & melewatkan momen (log: banyak HOLD "wait for pullback/overbought/NFP"). Trade live justru profit konsisten (17 trade, 16W/1L, +$65.18 net hari ini 7 Agustus).
- **Eksperimen disetujui tapi BELUM diimplementasi**: "Recent Decision Memory" — simpan 5-6 keputusan terakhir per symbol ke `data/decision_memory.json`, inject ke prompt (biar LLM sadar udah HOLD berapa lama, karena tiap call LLM = fresh session / stateless).
- Git branch: `dev`. Commit terakhir: `72f797a` (rotasi weekend BTCUSD).
- `git status` biasanya ada `data/dynamic_rules.json`, `data/forecast_cache.json`, `data/memory_lessons.json` ter-modif — itu runtime state, jangan commit kalau nggak sengaja.

## Konvensi & hal yang perlu diingat

- User komunikasi dalam **Bahasa Indonesia** (santai).
- **Risk-averse**: jangan naikin lot (tetap 0.01), jangan longgarkan daily loss. Kalau mau eksperimen agresif → demo dulu, bukan live.
- Perubahan prompt = diskusi dulu sebelum apply (user minta bahas dulu).
- User suka angka dari sumber kebenaran: profit = query MT5 langsung, bukan log campuran.
- Kalau bikin skrip analisis sementara → taruh di `scratch/`, lalu HAPUS setelah dipakai (user minta dibersihin).
- User minta commit + push ke `dev` setelah kerjaan verified (tapi tanya dulu / tunggu permintaan eksplisit).
- Magic number bot: `20260625`. Bot cuma kelola posisi dengan magic ini.
- LLM timeout 24s, fallback berurutan (Gemini → OpenAI → DeepSeek untuk primary).
