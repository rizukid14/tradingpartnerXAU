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

- **Semua perubahan 7-8 Agustus SUDAH di-commit & push ke `dev`** (terakhir `f9643db`):
  1. **Prompt di-trim ramping** (5 baris inti, "data lengkap prompt tipis"): balanced BUY/SELL, M5 momentum > H1 trend, R:R ≥ 1.0 (0.8 kalau momentum jelas), news rule dari calendar
  2. **Calendar programatik** (`src/analytics/economic_calendar.py`): NFP/CPI/PCE/GDP/FOMC/ECB/BOE/BOJ/SNB, DST-aware, inject cuma kalau event dalam **3 jam** (hemat token)
  3. **Fundamental analysis OFF** (`FUNDAMENTAL_ANALYSIS_ENABLED=False`) — search grounding Gemini sering kasih konteks basi ("ahead of NFP" berjam-jam setelah rilis). Murni penilaian LLM dari data teknikal.
  4. **Debate di-disable** (`DEBATE_ENABLED=False`) — 53 debate nggak pernah ngubah keputusan jadi trade, cuma buang token
  5. **Timezone fix**: MT5 server (GMT+3) → WIB via `server_to_wib()`; log candle & prompt pake WIB
  6. **3 M1 candle** di-inject ke prompt (micro price action)
  7. **Forecast auto-refresh dihapus** — refresh tiap 15 menit (cache), bukan tiap invalidation breach (ngurangin 3 LLM call/cycle)
  8. **Model**: OpenAI = `gpt-5.4-mini` (utama=fallback), Gemini = `gemini-3.1-flash-lite`, DeepSeek = `deepseek-chat`. `PRIMARY_ANALYSIS_MODEL = "gpt-5.4-mini"` (OpenAI free tier 2.5M token/hari) — `query_primary_model` urutan OpenAI → Gemini → DeepSeek
  9. **Parameter BTC di-scale** ke target **$10/trade** (0.01 lot): SL 50000 pts (~$5 risk, 0.5% modal), TP 100000 pts (~$10), trailing activation 25000/distance 15000, BE 20000/padding 1000, partial TP1 40000. (1 pt BTC = ~$0.0001; 10000 pts = $1)
  10. **Lessons memory**: pas 15 lessons penuh → di-summary jadi 1 blok via gpt-5.4-mini, lalu reset dari 0. Prompt inject summary aja.

- **Bug fix & improvement sesi 8 Agustus 2026** (akan di-commit+push, branch `dev`):
  1. **Dynamic config wired ke consensus**: `dynamic_rules.consensus_threshold` sekarang live dipakai `consensus.calculate_consensus()` lewat helper `_effective_consensus_threshold()`. Sebelumnya cuma di-print & simpan JSON tanpa efek ke keputusan.
  2. **AI re-evaluator close pass real profit**: di `main.py`, sebelum `connector.close_position(ticket)`, tangkap profit dari `mt5.positions_get(ticket=...)` lalu pass ke `risk.record_position_closed(ticket, pre_profit)`. Sebelumnya di-pass `0.0` → daily P/L & loss streak jadi ngaco.
  3. **Position manager state persisted**: `_partial_closed_tickets` & `_break_even_tickets` di-load/save ke `data/position_manager_state.json` (module-level di-import). Restart bot gak double-trigger partial close atau BE.
  4. **Order retry + fill-policy fallback**: helper `_send_with_retry()` di `mt5_connector.py`. Retry sampai 2× pada retcode PRICE_OFF/PRICE_CHANGED/REQUOTE/REJECT (deviation melebar 5 pts tiap retry), fallback ke `ORDER_FILLING_RETURN` kalo IOC gagal. Dipakai `send_trade_order` + `close_position`.
  5. **Recent Decision Memory (per-symbol)**: `src/analytics/decision_memory.py` baru. Record 6 keputusan terakhir per symbol, inject ke prompt dengan HOLD-streak note kalo ≥3 trailing HOLD. LLM jadi aware perpetual-HOLD & bisa self-correct.
  6. **Forecast pre-warm di background thread**: `_kick_background_refresh()` di `forecast_engine.py` dengan `_refresh_lock` + `_refresh_in_progress` flag. Caller `get_active_forecast()` return cache immediately, refresh di background. Plus explicit pre-call di `main.py` setelah macro context, biar cache fresh tiap cycle.
  7. **Lesson theme tagging + diversified summary**: `_extract_theme()` di `trade_evaluator.py` dengan keyword-based classifier (hard-override untuk timing/psychology/risk markers). Tiap lesson di-tag `{symbol, lesson, theme}`. Saat summary, lessons dikelompokkan per-theme dengan prompt eksplisit "preserve coverage of each theme".
  8. **Per-symbol Daily Breakdown**: di `main.py`, tambah baris `📊 [PERFORMA PER SIMBOL]` setelah aggregate line — breakdown XAU vs BTC (hanya muncul kalo `len(by_symbol) > 1`).

- **File baru sesi 8 Agustus**: `src/analytics/decision_memory.py`. File modified: `main.py`, `src/core/consensus.py`, `src/core/llm_client.py`, `src/core/mt5_connector.py`, `src/analytics/forecast_engine.py`, `src/analytics/position_manager.py`, `src/analytics/trade_evaluator.py`, `README.md`, `AGENTS.md`.

- **Catatan akun**: LIVE `VTMarkets-Live 3` login `27556325`, balance ~$1065 (cent account? profit kecil per trade). Profit verifikasi = query MT5 langsung (`scratch/` script, hapus setelah dipakai).
- Git branch: `dev`. Commit terakhir sesi 7 Agustus: `f9643db`. Sesi 8 Agustus akan buat commit baru.
- `git status` biasanya ada `data/dynamic_rules.json`, `data/forecast_cache.json`, `data/memory_lessons.json`, `data/decision_memory.json`, `data/position_manager_state.json` ter-modif — itu runtime state, jangan commit kalau nggak sengaja.

## Konvensi & hal yang perlu diingat

- User komunikasi dalam **Bahasa Indonesia** (santai).
- **Risk-averse**: jangan naikin lot (tetap 0.01), jangan longgarkan daily loss. Kalau mau eksperimen agresif → demo dulu, bukan live.
- Perubahan prompt = diskusi dulu sebelum apply (user minta bahas dulu).
- User suka angka dari sumber kebenaran: profit = query MT5 langsung, bukan log campuran.
- Kalau bikin skrip analisis sementara → taruh di `scratch/`, lalu HAPUS setelah dipakai (user minta dibersihin).
- User minta commit + push ke `dev` setelah kerjaan verified (tapi tanya dulu / tunggu permintaan eksplisit).
- Magic number bot: `20260625`. Bot cuma kelola posisi dengan magic ini.
- LLM timeout 24s, fallback berurutan (Gemini → OpenAI → DeepSeek untuk primary).
