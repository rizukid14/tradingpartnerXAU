# Perbandingan Branch: legacy → legacy-2 → xau-stable/main

> Ringkasan evolusi branch dari era awal (DeepSeek) sampai era modern (Claude + risk management).
> Di-update: 2026-08-09

## Ringkasan

| Branch | Basis | Isi | Status |
|---|---|---|---|
| `legacy` (origin/legacy) | Awal | Era DeepSeek: consensus 2/3, lot statis, forecast multi-horizon, M5 scalping BTC | Historic |
| `legacy-2` | legacy | = legacy + state runtime + test telegram (hampir identik) | Historic |
| `main` | merge dev | Era modern: Claude, weighted consensus, risk-based sizing, BTC M30, Hurst/Monte Carlo | **Stable** |
| `xau-stable` | main | = main + fix terakhir (M30 sync, weekend OFF, real-time close) | Stable snapshot |
| `dev` | main + fitur | = main + dashboard + binance_bot + docs | Active development |

## 1. `legacy` → `legacy-2` (kecil, 4 file)

`legacy-2` hampir identik dengan `legacy` — hanya:
- `data/dynamic_rules.json`, `data/forecast_cache.json`, `data/memory_lessons.json` — state runtime
- `tests/test_telegram.py` (+4 baris)

## 2. `legacy-2` → `main`/`xau-stable` (BESAR: 29 file, +3084/−579)

### A. Model LLM (terbesar)
- DeepSeek → **Claude** (`claude-sonnet-4-6`) di slot konsensus (DeepSeek konservatif, tidak efektif)
- `claude-haiku-4-5` untuk respon cepat; fix truncated JSON + `max_tokens` naik
- `llm_client.py` +453: prompt dinamis per-symbol, money scale (`usd_per_point`), micro candle, pemisahan entry vs position management

### B. Risk & Money Management
- **Risk-based lot sizing** (BTC 1.5%, XAU 0.5% dari equity) — bukan lot statis
- **Weighted-confidence consensus** per-symbol (XAU 1.0, BTC 1.2) + defensif ×1.5
- **BEP tolerance ±0.04** (tidak nambah loss streak)
- **Recovery exit threshold** ($0.10), SL/TP floor (2× spread, 1× ATR), counter-trend block
- `risk_engine.py` +203: sync closed positions, weekend handling, session lot multiplier

### C. Timeframe & Strategi BTC
- BTC **M5 → M30** (spread $17 terlalu besar untuk scalping M5)
- MTF context per-symbol (XAU M30/H1, BTC H1/H4)
- Forecast horizon per-symbol (XAU T+15m/T+60m, **BTC T+4h/T+D1**)
- Prompt "M30 Intraday Strategy" untuk BTC

### D. Quant & Analytics (fitur baru)
- **Hurst Exponent** + fat-tail kurtosis (`market_randomness.py` +171)
- **Monte Carlo quant probability** (`quant_probability.py` +95)
- `decision_memory.py` (+101), `economic_calendar.py` (+150)
- Forecast engine ditingkatkan (+186)

### E. Operational
- Position manager multi-symbol + tick freshness (+161)
- Status display semua posisi + P/L tiap 5 detik
- Telegram alerts (+56)
- `AGENTS.md` (+115), `README.md` (+200)

## 3. `xau-stable` (commit `6b73d96`) — yang terakhir

= `main` + satu commit fix:
- Sync label M30 (bukan H1) di semua kode
- `WEEKEND_TRADING_ENABLED = False` (weekend tidak buka posisi baru)
- `sync_closed_positions()` real-time + alert Telegram tiap 5 detik
- trade_evaluator tidak alert ganda

## 4. `dev` (di depan main)

- Dashboard analisis (`dashboard.py` + `dashboard_assets.py`)
- Bot Binance spot (`binance_bot/`) — 2 proposer + 1 approver
- Design specs (`docs/superpowers/specs/`)

## Kesimpulan

- `legacy`/`legacy-2` = era DeepSeek + lot statis + M5 BTC (sudah usang)
- `main`/`xau-stable` = era modern yang stabil (Claude, weighted consensus, risk-based sizing, BTC M30)
- `dev` = pengembangan aktif (dashboard + binance_bot)
