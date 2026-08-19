# Analisis Perubahan Remote Repo — 9-10 Agustus 2026

**Status:** Analisis saja, **belum pull / belum merge** (sesuai permintaan).
**Dibuat:** 2026-08-09 (sesi lokal, commit lokal terakhir `e7e1397`)
**Repo:** `github.com/rizukid14/tradingpartnerXAU` (origin: `https`)

---

## 1. Ringkasan

- Local branch `dev` tertinggal **60 commit** dari `origin/dev` (`e7e1397` → `2e6553b`).
- Ada **4 branch remote baru** yang tidak ada di lokal: `legacy-2`, `try-crypto`, `xau-stable`, plus `main` yang juga sudah maju.
- Perubahan terbesar: **bot Binance spot baru** (`binance_bot/`, ~7.800+ baris + test + docs), **dashboard web** (`dashboard.py`, ~1.000 baris), dan **rombakan besar MT5 bot** (Claude ganti DeepSeek, weighted consensus, risk-based lot sizing, quant analysis, CLI setup, dll).
- Total: **71 file, +14.052 / −555 baris** (antara lokal vs remote dev).

---

## 2. Status Branch

| Branch | Lokal | Remote | Catatan |
|---|---|---|---|
| `dev` | `e7e1397` | `2e6553b` (60 commit di depan) | **Ini yang utama — paling relevan** |
| `main` | `2be7263` (52 behind) | `57775ad` | Mengandung 8 commit yang tidak ada di dev lokal |
| `legacy` | ada | `d4fcd0f` (sama) | Tidak berubah |
| `legacy-2` | **tidak ada** | `2be7263` | Snapshot lama (7 Agu), isinya = merge dev→main saat itu |
| `try-crypto` | **tidak ada** | `2e6553b` | **Sama persis dengan tip `origin/dev`** (percobaan crypto) |
| `xau-stable` | **tidak ada** | `6b73d96` (9 Agu) | Cabang "XAU stable": fix BTC M30 labels, weekend trading OFF, real-time close detection |

> Catatan: `try-crypto` dan `dev` menunjuk commit yang sama (`2e6553b`). `legacy-2` menunjuk commit yang sama dengan `main` lama (`2be7263`).

---

## 3. Commit Baru di `origin/dev` (60 commit) — Pengelompokan Tematik

### A. Fase MT5 (8-9 Agustus, ~30 commit)
1. **DeepSeek → Claude**: `08266d3` (claude-sonnet-5), `e0824e2` (→ claude-sonnet-4-6), `a9ed931` (→ claude-haiku-4-5 fallback), `43cf62d`, `1a3c43a` (fix JSON truncated + max_tokens 2000).
2. **Risk-based lot sizing**: `d6b023f` (BTC 1.5%, XAU 0.5% equity), `2d3ccbf` (LOT_SIZE_BTC 0.03 → di-reject user, balik 0.01), `bb04cd8` (0.25 → di-reject juga).
3. **BTC pindah M5 → M30 intraday**: `bdb4c1d`, `83dd849`, `8634d7f` (forecast horizon T+4h/T+D1), `37eb02d` (cache 1 jam), `da74753` (H1 ATR basis SL/TP).
4. **Weighted confidence consensus**: `9d4cd2f` (skor = Σ confidence, threshold per-symbol XAU 1.0 / BTC 1.2, defensif ×1.5).
5. **Per-symbol isolation**: `b7d29fa` (lessons per symbol), `d9019fa` (money-scale prompt, magic filter positions, position manager semua symbol + tick freshness), `297caa7` (semua posisi di status line).
6. **Fix bug startup**: `da74753` (TradeEvaluator `_load_memory()` duplikat), `1de0810` (SELL SL/TP terbalik + filling policy dinamis), `5ab4e01` (false loss streak startup).
7. **Fitur MT5**: `259708d` (**quant**: Hurst exponent + fat-tail kurtosis + Monte Carlo prob), `2dcf0cd` (pause countdown), `27fef1f` (dynamic import mt5linux), `fd09e07` + `3548241` + `b77fa84` (dashboard + spec), `af53ee4` (CLI overrides), `0554945` (interactive setup), `055f39a` (feature toggles + era presets), `4920839` (protection settings di setup), `344c190` (rename era → V1/V2/V3), `1e76640` (MEMORY_CONTEXT_ENABLED), `75f2a9f` (KeyboardInterrupt), `33887b1` (grouped setup UI).

### B. Fase Binance (9-10 Agustus, 10 commit — paling baru)
1. `fd09e07` — bot Binance spot: **2 proposer (GPT+Gemini) + 1 approver (Claude)**.
2. `38e2dbb` — pola risk Freqtrade: SL reserve, dry-run simulation, OCO safety.
3. `f3b9f6f` — fix REST_BASE dobel `/api` + User-Agent testnet.
4. `c64e412` — track posisi lokal (`positions.json`).
5. `c00e1cc` — status line via log (bukan `\r`).
6. `495f3fb` — timeframe M5 (spread tipis) + countdown candle.
7. `df27ba4` — countdown langsung setelah cycle + label timeframe dinamis.
8. `c0afc6b` — log reasoning 200 char.
9. `4e71570` — MTF context (M30/H1) + indikator (RSI/EMA/ATR) di prompt.
10. `93dca37` — **migrate ke ccxt connector** → support **TokoCrypto** (legal ID).
11. `dc652ab` — min notional 0.5 (TokoCrypto min Rp10rb, bukan $5).
12. `2e6553b` (TIP) — **approver independen** (data mentah sama dengan proposer), **HOLD-streak** (5 cycle HOLD → 1 BUY ≥ 0.60 lanjut ke approver), **sizing clamp** ke free USDT, fix balance=0 skip cycle, fix TIMEFRAME `.strip()`, market_structure.py (S/R + sweeps), 4 test baru.

### C. Commit `main` yang belum ada di lokal
- `57775ad` (10 Agu, tip main) — **prompt caching Anthropic** (cache 2 blok, hemat ~46% input), **decision framework + confidence calibration** di prompt, guard None/NaN (ATR floor, point/tick/symbol_info).
- `33887b1`, `75f2a9f`, `1e76640`, `845ee8d` — sama dengan fase MT5 di atas (sudah masuk dev).

---

## 4. Perubahan Besar pada Bot MT5 (lokal → remote dev)

| Area | Lokal (e7e1397) | Remote dev (2e6553b) |
|---|---|---|
| Model ke-3 | DeepSeek (`deepseek-chat`) | **Claude** (`claude-sonnet-4-6`, fallback `claude-haiku-4-5-20251001`) |
| Konsensus | Vote 2/3 sederhana | **Weighted confidence** (Σ conf, ≥ 2 model searah, threshold XAU 1.0 / BTC 1.2; defensif ×1.5) |
| SL/TP | ATR-adaptive, tanpa floor | **Floor `_apply_sltp_floors()`**: SL ≥ max(2× spread, 1× ATR), TP ≥ 1.5× SL |
| Lot | Statis 0.01 | **Risk-based**: lot = risk% × equity / SL USD (BTC 1.5%, XAU 0.5%) + margin safety net |
| Timeframe BTC | M5 | **M30** (MTF H4/D1, forecast T+4h/T+D1) |
| Prompt | M5 scalping hardcode | Per-symbol (M5 scalp XAU / M30 intraday BTC), money-scale, **2 blok statis+dinamis** (cacheable), decision framework, confidence calibration |
| Status line | `\r` sederhana | Pause countdown + **semua posisi open** (semua symbol) |
| Config | Statis | **CLI overrides** + **interactive setup** + **era presets V1/V2/V3** + feature toggles (`QUANT_ANALYSIS_ENABLED`, `FORECAST_ENABLED`, `MEMORY_CONTEXT_ENABLED`) |
| Quant | Tidak ada | **Hurst exponent + fat-tail kurtosis + Monte Carlo** (informational, di-print) |
| Weekend BTC | Trading aktif (rotasi) | **`WEEKEND_TRADING_ENABLED=False`** — tidak buka posisi baru weekend (posisi lama tetap di-manage) |
| Telegram | Tidak ada | **`src/core/telegram_alerts.py`** (trade open/close, risk halt, daily summary, dll) |
| Close detection | Per cycle candle | **Real-time** tiap 5 detik (`sync_closed_positions()` → return deals baru → alert Telegram) |
| BEP | Tidak ada | **`BREAK_EVEN_TOLERANCE_USD = 0.04`** (BEP excluded dari win rate & tidak reset streak) |
| Recovery | Exit setelah win berapa pun | Exit hanya kalau win ≥ **`RECOVERY_EXIT_PROFIT_USD = 0.10`** |

### Config baru yang penting (remote)
- `RISK_PERCENT_BTC = 1.5` / `RISK_PERCENT_XAU = 0.5`
- `CONFIDENCE_CONSENSUS_THRESHOLD_XAU = 1.0` / `_BTC = 1.2`, `MIN_CONSENSUS_MODELS = 2`
- `CLAUDE_MODEL = "claude-sonnet-4-6"`, `CLAUDE_FALLBACK_MODEL = "claude-haiku-4-5-20251001"`
- `GEMINI_MODEL = "gemini-3.5-flash-lite"` (upgrade dari 3.1)
- `BREAK_EVEN_TOLERANCE_USD = 0.04`, `RECOVERY_EXIT_PROFIT_USD = 0.10`
- `WEEKEND_TRADING_ENABLED = False`, `POSITION_MANAGER_MAX_TICK_AGE_SECONDS = 300`
- `QUANT_ANALYSIS_ENABLED = True`, `FORECAST_ENABLED = True`, `MEMORY_CONTEXT_ENABLED = True`
- `ERA_PRESETS` (v1/v2/v3), `HIGHER_TIMEFRAMES_CRYPTO` (H1/H4)
- Trailing BTC: activation 17000 pts, distance 12500 pts; BE trigger 33500 pts; partial TP1 44500 pts (semua di-scale ke M30)

### Hal yang perlu diwaspadai sebelum pull
1. **Dua nilai "testing" di remote**: `BREAK_EVEN_TOLERANCE_USD = 0.04` (komentar di recap session bilang "untuk LIVE, 0.04 sudah dikembalikan" — OK) tapi recap lama sempat bilang 0.50 untuk testing. Verifikasi nilai final di config.
2. **`WEEKEND_TRADING_ENABLED=False`** — ini mengubah perilaku rotasi weekend BTC yang dulu kita set (taste: user minta rotasi weekend). Di remote, entry weekend di-block, posisi lama tetap di-manage. **Ini perubahan keputusan — perlu konfirmasi user.**
3. **Lot risk-based bisa > 0.01** (BTC 1.5% ≈ lot 0.05, XAU 0.5% ≈ lot 0.02) — **melanggar preferensi user "lot tetap 0.01"** yang sudah berkali-kali ditegaskan. Ini konflik langsung dengan taste risk-averse. **Harus dibahas dulu.**
4. **Claude menggantikan DeepSeek** — model baru, butuh `ANTHROPIC_API_KEY` di `.env`.
5. `data/*.json` di remote berubah (decision_memory, dynamic_rules, dll) — runtime state, jangan di-merge manual kalau tidak perlu.

---

## 5. Bot Binance Spot (`binance_bot/`) — Fitur Utama

- **Arsitektur**: 2 proposer (GPT + Gemini) paralel + 1 approver (Claude) — Claude dipanggil hanya saat 2/2 sepakat (hemat biaya). Di tip `2e6553b`, approver jadi **independen** (analisis sendiri dari data mentah).
- **Spot** (tanpa margin/futures): tidak bisa short; SELL saat tidak punya posisi = hold USDT; SELL saat punya posisi = exit.
- **SL/TP via OCO order** (`POST /api/v3/orderList/oco`), `stopLimitPrice` di sisi aman (0.99×/1.01× — pola Freqtrade).
- **Connector**: `ccxt` (multi-exchange) dengan `binance_connector.py` (REST `/api/v3/*` langsung, fallback).
- **Sizing**: `POSITION_ALLOCATION_PCT=0` = risk-based 1.5% equity; `>0` = % equity langsung. **Notional di-clamp ke free USDT** (minus fee buffer).
- **HOLD-streak**: 5 cycle HOLD → 1 BUY ≥ 0.60 langsung lanjut ke approver (di-track `risk_state.json`).
- **Risk**: daily loss $3 (ketat untuk modal $12), cooldown, min notional $0.5 (TokoCrypto), max 2 posisi, 24/7.
- **Dry-run realistis**: simulasi fill + slippage 0.05% + fee 0.1% (Freqtrade pattern). `TESTNET=True` + `DRY_RUN=True` default (aman).
- **Testnet verified**: server_time, symbol_info, balance $10k, klines OK. Ada 7 test file (approver prompt, hold-streak, hold threshold, risk engine, sizing alloc, TF check, balance check, binance connector).
- **TokoCrypto** (legal ID, Rp10rb = $0.5 min notional) — alasan utama migrate ke ccxt.
- **File non-code yang masuk**: `binance_bot/list.jpg` (3 MB!), `binance_bot/list_crypto.md`, `docs/Tokocrypto API Documentation.html` (+ 6 file pendukung ~7.300 baris), `docs/extract_toko*.py` — kemungkinan artefak riset yang sebaiknya tidak ikut commit (atau dipindah ke scratch).

---

## 6. Dashboard (`dashboard.py` + `dashboard_assets.py` + `tests/test_dashboard.py`)

- **Spec approved** (`docs/superpowers/specs/2026-08-09-trading-dashboard-design.md`).
- Sumber data: **hanya** `logs/trading_bot.log` + `data/*.json` (tanpa query MT5 langsung).
- Tiga komponen: `parse_log()` → `compute_metrics()` → `render_html()` (satu file HTML + Chart.js CDN, tema gelap, filter JS: era/symbol/rentang waktu).
- KPI: win rate (BEP excluded), expectancy, max drawdown, equity curve, akurasi per model, kalibrasi confidence, efektivitas SL/TP, lessons per theme.
- Parser menandai **era + akun** dari banner (demo `1157958` vs live `27556325`) — default era aktif (banner terakhir), dengan toggle.
- Read-only terhadap log (`errors='replace'`, tahan log sedang ditulis).

---

## 7. Docs & File Lain

- `docs/recap_session_2026-08-08.md` — rekap sesi 8 Agu (bug SELL SL/TP, BTC H1, BEP, dll).
- `docs/superpowers/specs/2026-08-09-binance-bot-design.md` — spec bot Binance.
- `docs/superpowers/specs/2026-08-09-trading-dashboard-design.md` — spec dashboard.
- `docs/branch-comparison.md`, `docs/command_code_review.md`, `docs/gpt-mini-code_review.md`, `docs/opus_review.md`, `docs/vps_deployment.md` — review & deploy.
- `AGENTS.md` / `README.md` — di-update remote (berisi state BTC M30, Claude, risk-based lot, binance bot).

---

## 8. Rekomendasi / Langkah Selanjutnya

1. **Diskusikan dulu 3 konflik keputusan** sebelum pull/merge:
   - **Lot risk-based vs "lot tetap 0.01"** (preferensi user yang sudah ditegaskan berkali-kali).
   - **`WEEKEND_TRADING_ENABLED=False`** vs fitur rotasi weekend yang pernah diminta.
   - **Claude ganti DeepSeek** — model baru + butuh API key baru.
2. **Merge strategy yang aman**: `git merge origin/dev` (lokal tidak punya commit unik di dev selain e7e1397 yang juga ada di remote — sebenarnya lokal adalah ancestor, jadi bisa fast-forward atau merge biasa tanpa konflik). Verifikasi dengan `git merge-base` dulu.
3. **Bersihkan artefak** kalau mau: `binance_bot/list.jpg`, `docs/Tokocrypto API Documentation*`, `docs/extract_toko*.py`, `binance_bot/test_status.md` (kemungkinan hasil riset).
4. **Jangan commit `data/*.json`** (runtime state) — sudah jadi konvensi AGENTS.md.
5. Kalau sudah pull, jalankan `python main.py` untuk verifikasi (user suka tes sendiri).
