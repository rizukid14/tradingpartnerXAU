# AGENTS.md — Konteks Proyek Trading Bot

> Ringkasan cepat untuk sesi coding. Baca ini dulu sebelum ngapa-ngapain.

## Apa ini

Bot trading **multi-LLM consensus** (OpenAI + Gemini + Claude) yang jalan di **MetaTrader 5**.
- **XAUUSD-ECNc** (Gold): scalping **M5**, weekday, MTF context M15/M30
- **BTCUSD.c** (Bitcoin): intraday **M30**, weekend + setelah jam 22:00 Jumat WIB (rotasi otomatis, `config.get_active_symbol`). **MTF context H1/H4, forecast horizon T+4h/T+D1 (bebas swap overnight).**
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
| `main.py` | Loop utama: manage posisi tiap 5 detik, full cycle tiap candle (M5 utk XAU / M30 utk BTC) |
| `config.py` | Semua parameter + helper per-symbol (`get_timeframe`, `get_higher_timeframes`, `lot_size_for`, `risk_percent_for`, `default_sl/tp`, `max_spread_points`, `confidence_threshold_for`) |
| `src/core/llm_client.py` | **Build prompt dinamis per-symbol** + call 3 LLM paralel (OpenAI, Gemini, Claude) |
| `src/core/consensus.py` | **Weighted confidence consensus** (skor = Σ confidence per arah, threshold per-symbol, min 2 model searah) + SL/TP floor mode-aware (`config.TP_SL_RULES`: ATR-Based → max(2× spread, 1.2× ATR) + TP ≥ 1.5× SL; LLM → cuma 2× spread) + **outlier filter SL/TP (average, nilai "beda sendiri" dibuang)** |
| `src/core/risk_engine.py` | Gate: spread, sesi, danger zone, daily loss, recovery mode, BEP tolerance, **risk-based lot sizing** |
| `src/core/mt5_connector.py` | Order send/close (retry + fill policy dinamis), history deals, market data, magic filter |
| `src/analytics/forecast_engine.py` | Forecast multi-horizon per-symbol (XAU T+15m/T+30m, BTC T+4h/T+D1), invalidation, entry zone — **informational, tidak memblokir** |
| `src/analytics/macro_analyst.py` | Fundamental + MTF context (per-symbol: XAU M15/M30, BTC H1/H4), cache per symbol |
| `src/analytics/trade_evaluator.py` | Post-mortem tiap trade → lessons (`data/memory_lessons.json`), per-symbol |
| `src/analytics/dynamic_config.py` | Adaptasi otomatis: win rate <40% → threshold 3/3; >70% → 2/3 |
| `src/analytics/position_manager.py` | Trailing stop, break-even, partial close — **semua symbol, skip kalau market tutup** |
| `src/analytics/decision_memory.py` | 6 keputusan terakhir per symbol (HOLD-streak awareness) |

## Alur cycle (main.py → run_trading_cycle)

1. `risk.can_trade()` — spread/sesi/danger zone/daily loss gate. Gagal → skip (nggak ada biaya LLM)
2. Ambil 50 candle timeframe aktif (M5 XAU / M30 BTC) + tick
3. Post-mortem evaluasi trade tertutup + dynamic rules (BEP excluded dari win rate)
4. **Panggil 3 LLM paralel** (decision prompt + forecast context + lessons + macro + open positions)
5. **Weighted consensus**: skor BUY/SELL = Σ confidence model searah; menang kalau ≥ 2 model & skor > threshold (XAU 1.0, BTC 1.2, defensif ×1.5). Plus AI re-evaluator CLOSE posisi
6. Forecast context (bias/target/entry zone) **murni informational** — di-inject ke prompt LLM, TIDAK memblokir eksekusi (tidak ada gate counter-trend; `validate_forecast_trigger` sudah dihapus)
7. **Risk-based lot sizing** — lot dihitung dari equity & SL (BTC 1.5%, XAU 0.5%), bukan statis
8. Cek max posisi, eksekusi order (2 posisi kalau 3/3 sepakat)

## Gate eksekusi yang SEBENERNYA (hard)

- **Weighted consensus**: ≥ 2 model searah, skor confidence > threshold per-symbol (XAU 1.0 / BTC 1.2; 3/3 defensif = ×1.5)
- SL/TP di-floor per mode (`config.TP_SL_RULES`): **ATR-Based** → SL ≥ max(2× spread, 1.2× ATR), TP ≥ 1.5× SL; **LLM** → SL ≥ 2× spread aja, TP bebas
- Spread ≤ 50 pts (XAU) / 2400 pts (BTC)
- Session London/NY WIB + bukan danger zone (kecuali crypto)
- Max daily loss $50, max 3 consecutive loss, max 6 posisi (4 recovery)
- **TIDAK ada** gate confidence minimum numerik tambahan di luar weighted score
- **TIDAK ada** gate entry zone numerik — `optimal_entry_min/max` di-load tapi nggak dipakai
- Forecast bias/target/R:R cuma konteks buat LLM (informational) — **TIDAK ada gate counter-trend**

## Status terkini (AGUSTUS 2026 — PENTING)

### Optimasi kecepatan loop (11 Agustus — bersama fitur TP_SL_RULES)

- **Cache query MT5 di hot path** (`mt5_connector.py`): sebelumnya tiap loop 5 detik manggil `history_deals_get` 2× — termasuk window 7 HARI (query termahal, bisa 0.5-2 detik) — itu bikin tiap iterasi loop nge-blok. Sekarang:
  - `bot_opened` (window 7 hari) di-cache **60 detik** + invalidate saat order/close sukses (`invalidate_deals_cache()`)
  - `get_closed_positions_today` di-cache **4 detik** (key per symbol / `__ALL__`) — deteksi close real-time tetap jalan
  - `get_all_open_positions` di-cache **3 detik** (dipakai status line CLI tiap loop)
- **Loop utama `time.sleep(5)` → `time.sleep(3)`** — tiap iterasi jadi lebih responsif (status line update tiap 3 detik, manage posisi lebih sering).

### Perubahan struktural 8 Agustus (sudah di-commit & push ke `dev`)

1. **BTC pindah ke M30** (dari M5): spread BTC ~$17 = 78% dari ATR M5 ($21), tapi kecil relatif ke ATR M30. M5 scalping BTC cuma bleed spread. `config.get_timeframe()` → BTC M30, XAU M5.
2. **MTF per-symbol**: XAU scan M15/M30, BTC scan H4/D1 (`config.get_higher_timeframes()`).
3. **Weighted confidence consensus** (bukan vote 2/3 murni): skor arah = Σ confidence; menang kalau ≥ 2 model searah DAN skor > threshold (`confidence_threshold_for()`: XAU 1.0, BTC 1.2; defensif ×1.5). Model @51% tidak lagi setara @90%.
4. **Prompt dinamis per-symbol**: BTC "M30 Intraday Strategy", XAU "M5 Scalping Strategy". Sebelumnya hardcode M5 — LLM dikasih candle H1 tapi disuruh scalper M5 → semua HOLD.
5. **Money scale di prompt**: `usd_per_point` (dari `trade_tick_value`), spread USD, "NEVER set SL closer than 2x spread". Sebelumnya prompt bilang "(1 point = 0.01)" yang menyesatkan → LLM kasih SL di dalam spread.
6. **SL/TP floor di consensus (mode-aware)**: ATR-Based → SL ≥ max(2× spread, 1.2× ATR), TP ≥ 1.5× SL; LLM → cuma floor 2× spread (anti INVALID_STOPS). Cegah SL di dalam noise/spread.
7. **`get_open_positions` filter magic** — bot tidak bisa close posisi manual user.
8. **Position manager multi-symbol + tick freshness**: manage semua posisi bot, skip kalau market tutup (XAU weekend) — `POSITION_MANAGER_MAX_TICK_AGE_SECONDS`.
9. **BEP tolerance ±0.04** (`BREAK_EVEN_TOLERANCE_USD`) — trade dengan |profit| ≤ $0.04 dianggap BEP (tidak nambah loss streak, tidak reset, excluded dari win rate).
10. **Recovery exit threshold**: win < $0.10 tidak exit recovery mode (`RECOVERY_EXIT_PROFIT_USD`).
11. **Per-symbol breakdown** di log harian: `BTCUSD.c: 4T 0W-4L WR 0% | 4 BEP $-1.73`.
12. **Banner dinamis**: "Simbol: BTCUSD.c | Timeframe: M30 | Spread Filter: 2400 pts maks (BTCUSD.c)".
13. **Risk-based lot sizing** (`get_effective_lot_size(sl_points)`): lot = risk_usd / (SL pts × usd_per_point). Per-symbol risk: **BTC 1.5%** equity, **XAU 0.5%** (karena XAU bisa 6 posisi → max ~3% aggregate). Urutan: risk-based → recovery/session multiplier → clamp+round ke volume_step. Margin safety net (lot diturunkan kalau margin > 50% free). Fallback 0.01 kalau SL tidak diketahui.
14. **Forecast horizon per-symbol**: XAU T+15m/T+30m, **BTC T+4h/T+D1** (15 menit itu noise untuk M30 swing + spread $17; XAU M5 cukup horizon pendek — nggak nangkep trend jangka panjang). Cache refresh: XAU 15 menit, **BTC 1 jam**. `horizon_label` di forecast dict.
15. **Slot ke-3 = DeepSeek V4 Flash (default, configurable)**: `CLAUDE_MODEL = "deepseek/deepseek-v4-flash"` — jauh lebih murah dari `claude-sonnet-4-6` (buat akun cent, ~$2/hari Claude itu mahal vs risk per trade puluhan sen). Routing otomatis di `query_claude()`: `deepseek/...` → DeepSeek API (OpenAI-compatible, base `https://api.deepseek.com/v1`), `claude-...` → Anthropic. Fallback `claude-haiku-4-5-20251001` (cuma kepanggil kalau DeepSeek error). Ganti model via menu setup / `--claude-model`. Log label otomatis ("DeepSeek" vs "Claude"). **Catatan lama (historis):** era sonnet-4-6 = model paling analitis (sadar R:R vs spread); DeepSeek konservatif (HOLD/SELL dominan).
16. **Pemisahan entry vs position management di prompt**: `signal` = murni entry baru, `position_actions` = posisi existing, dinilai independen (cegah LLM campur "existing BUY masih bagus" sebagai alasan HOLD entry). **Pullback Tolerance**: Prompt Re-Evaluator di-enhance untuk melarang keras aksi CLOSE dini pada koreksi/pullback M5 normal (hanya boleh CLOSE jika level invalidasi teknis rusak nyata atau terjadi reversal terkonfirmasi).
17. **Gemini ganti ke `gemini-3.1-flash-lite`** (fallback `gemini-3.5-flash-lite`): benchmark 5 model Gemini (10 iterasi, prompt produksi, sesi bearish) — 3.5-flash-lite dominan HOLD (8/10), 2.5-flash-lite parah (10/10 HOLD conf 36%), **3.1-flash-lite paling konsisten ngikutin sinyal (10/10 SELL, conf 65%, latency 1.1s)**. 3.6-flash juga bagus (9/10, conf 69%) tapi 7.5s latency. Catatan: Gemini return confidence skala 0-1 (bukan 0-100), di-×100 di consensus.
18. **Deteksi close manual (magic=0)**: manual close dari MT5 mobile menghasilkan OUT deal `magic=0` (magic tidak diteruskan). `get_closed_positions_today` menerima OUT magic=0 **hanya jika posisi dibuka bot** (ada IN magic bot) — posisi manual user tidak ikut kehitung. Window P/L = tengah malam WIB → next-midnight (bukan rolling 24h, biar loss kemarin tidak masuk "hari ini"). **Jangan diubah ke rolling 24h** — itu bikin daily loss cap ke-trip dari loss hari sebelumnya. **Reason close di-label** ("manual" untuk magic=0, SL/TP/stop-out dari kode MT5) — bukan "unknown".
19. **Post-mortem langsung saat close**: dipicu di loop 5 detik pas `sync_closed_positions` return `new_deals` (background thread biar nggak nge-block), bukan nunggu candle. `check_and_evaluate_closed_trades(deals)` nerima deals langsung. **Jangan seed `evaluated_tickets` dari `known_closed` tiap cycle** — itu nge-block tiket baru (bug yang udah diperbaiki); re-evaluation dicegah oleh `evaluated_tickets` persist di `memory_lessons.json`.
20. **Trailing stop ATR-adaptif**: activation `min(0.85×ATR, cap)` (XAU 500 / BTC 40000 pts), distance `0.5×ATR` (dulu 2.0×/1.5× yang bikin trailing nggak pernah aktif — activation 760+ pts jauh di atas TP M5). SL di-trail dari **harga ekstrem** sejak entry (`trailing_extremes` di `position_manager_state.json`) — pullback nggak narik SL mundur. **Partial close di-skip di lot 0.01** (`volume <= volume_min`) karena gabisa dipecah.

### Perubahan 11 Agustus (sesi ini — PENTING: branch split!)

**Sekarang ada DUA versi prompt yang berbeda antara branch:**
- **`main` = prompt LAMA** (`744ad0a`): Fibonacci + counter-trend pullback rules + prompt preview prints. **TIDAK ada** prompt_claude.md, **TIDAK ada** strip emoji.
- **`dev` = prompt BARU** (`06159f6`): semuanya dari main + prompt_claude.md + strip emoji.
- **JANGAN merge `dev` → `main` tanpa konfirmasi user** — user sengaja mau main pakai prompt lama, prompt baru eksperimen di dev.

21. **Fibonacci retracement di prompt** (sudah di main `744ad0a`): `prepare_prompt` hitung Swing High/Low dari 50 candle + Fib 38.2/50/61.8 → di-inject ke "CURRENT INDICATORS & FIBONACCI SUMMARY". Tujuannya: bot bisa lihat potensi SELL koreksi di tren bullish (target Fib) tanpa panik — LLM tidak lagi buta soal level retracement.
22. **Prompt template baru `docs/prompt_claude.md`** (hanya di `dev`, commit `ab42c17`): ganti static block kaku (STRATEGY/DECISION ORDER/counter-trend rules) dengan:
    - **ANALYSIS FREEDOM**: LLM bebas pilih interpretasi (trend/momentum/breakout/pullback/mean-reversion/reversal/exhaustion) — tidak dipaksa ke satu template strategi. Indikator (RSI/EMA/Fib/ATR/forecast) adalah **input untuk judgment, bukan trigger/block wajib**.
    - **DATA INTEGRITY**: jangan invent indikator yang tidak diberikan; macro/HTF note = background only (kalau generik/stale → abaikan); forecast = informational only (NEUTRAL ≠ wajib HOLD); recent outcomes = win/loss history, bukan sinyal arah.
    - **RISK CONSTRAINTS** (satu-satunya yang non-negotiable): thesis konkret + invalidation jelas, SL beyond invalidation & ~1.5-2× ATR & ≥ 2× spread, TP ≥ 1.5× SL, spread tidak makan SL.
    - **Output schema baru**: `setup` (label bebas), `edge` (1-2 kalimat), `invalidation` (1 kalimat) + `sl_points`/`tp_points`/`reasoning`. Field baru opsional — HOLD tetap valid, consensus tetap jalan.
    - `build_system_prompt(symbol, timeframe, asset_desc)` = statis per bot (cache-friendly, ≥1024 token); `prepare_prompt` gabung statis + dinamis.
23. **Anti-anchor: `summarize_recent_outcomes`** (di `dev`): ganti inject narasi decision history dengan ringkasan outcome-only ("3 trade taken, 2 hit SL, 3 HOLD"). Sebelumnya decision_memory_str inject keputusan lama lengkap → LLM ke-anchor ke bias bullish basi berjam-jam. Sekarang cuma win/loss counts.
24. **Macro & forecast diberi label advisory** (di `dev`): macro_str → "background only — disregard if generic/stale"; forecast_str → "informational only — NEUTRAL tidak wajib HOLD, aligned tidak otomatis trade".
25. **Strip emoji dari prompt LLM** (di `dev`, commit `06159f6`): `_EMOJI_PATTERN` + `_strip_emoji()` diterapkan ke prompt final sebelum dikirim. **Requirement user: prompt LLM HARUS bebas emoji** (UI/CLI/log boleh pakai emoji). Sumber emoji bisa dari macro/forecast/lessons/calendar — strip di prompt final menangani semua.
26. **Unicode safety**: `≈` diganti `approx` di prompt (UnicodeEncodeError saat print di console cp1252 Windows).
27. **`scratch/prompt_preview_test.py`**: test file untuk preview prompt LLM dengan data MT5 asli (XAUUSD-ECNc — bukan XAUUSD, broker pakai suffix `-ECNc`). Pakai `config.get_timeframe()`; fallback ke `XAUUSD` kalau simbol utama gagal.
28. **`config.TP_SL_RULES` — 2 mode SL/TP** (default `"ATR-Based"`, configurable via config):
    - **ATR-Based** (safe): SL ≥ max(2× spread, 1.2× ATR), TP ≥ 1.5× SL. Prompt minta SL ~1.5-2× ATR.
    - **LLM** (bebas): SL/TP sesuai thesis model. Floor dibatasi **max(2× spread, 0.5× ATR)** untuk membatasi ukuran lot maksimal (~0.03-0.05 lot Gold) agar tidak terjadi over-leverage akibat SL mepet dan trading tidak berasa M1. **Prompt di-enhance** untuk mengarahkan model ke struktur stop-loss yang sesuai timeframe (100-350 pts untuk Gold M5, 20000-60000 pts untuk BTC M30) dan melarang model mengambil stop M1 hyper-scalping (di bawah 80 pts untuk Gold / 10000 pts untuk BTC) agar terhindar dari noise eksekusi dan spread, sementara lot size tetap dihitung otomatis berbasis resiko dari hasil SL tersebut di main.py.
    - **Agregasi SL/TP**: nilai dari model yang sepakat di-average; outlier dibuang dengan `_drop_standalone_outlier`.
    - **Cara ganti mode**: `config.TP_SL_RULES`, menu setup interaktif, atau flag CLI `--tpsl-rules {ATR-Based|LLM|atr|llm}`.
29. **Dynamic Timezone Alignment**: `get_broker_offset_seconds` menghitung selisih jam server broker (GMT+3) dengan UTC secara dinamis. Jarak pencarian deals dan timestamp di-shift proporsional agar batas harian `get_closed_positions_today` cocok 100% dengan kalender WIB-midnight dan mencegah trade "jatuh di masa depan" atau lolos ke hari sebelumnya.

### Catatan akun & operasional
- LIVE `VTMarkets-Live 3` login `27556325`, balance ~$1065. Profit verifikasi = query MT5 langsung (`scratch/` script, hapus setelah dipakai).
- Git branch: **`dev` = prompt baru** (terakhir `06159f6`), **`main` = prompt lama** (terakhir `744ad0a`). **Sengaja split — jangan merge dev → main tanpa konfirmasi user.** Commit terakhir sesi 10 Agustus (sebelum split): `940333e` (post-mortem realtime + reason mapping).
- **Slot-3 DeepSeek V4 Flash** (default, configurable via menu/`--claude-model`); Gemini 3.1-flash-lite (primary) + 3.5-flash-lite (fallback); OpenAI gpt-5.4-mini; fallback slot-3 `claude-haiku-4-5-20251001`. Dynamic config ambang optimal **>65%** (bukan 70%). Threshold XAU 1.0 / BTC 1.2 (defensif 3/3 = ×1.5).
- **`data/` dan `scratch/` sudah di-`.gitignore`** (untrack via `git rm --cached`, file tetap ada di disk). `git status` sekarang bersih dari runtime state — cuma source file + `docs/` yang muncul.
- Lessons BTC pernah bikin bot HOLD terus (8 lesson "avoid 5-minute BTC scalps" dari era M5 yang gagal) — sudah di-clear. Kalau bot mulai HOLD terus lagi, cek `memory_lessons.json` dulu.
- **Status display live** menampilkan posisi terbuka semua symbol + floating P/L tiap 5 detik (`get_all_open_positions`).

## Bot Binance Spot — BRANCH TERPISAH (`binance`)

> Bot kedua untuk **Binance spot** (BTC/ETH/SOL), modal kecil, deploy Linux. **TIDAK ada di branch `dev`/`main`** — kode lengkap ada di branch `binance` (`git checkout binance`). Arsitektur: 2 proposer + 1 approver, OCO SL/TP, dry-run realistis, HOLD-streak, risk 1.5%, trading 24/7. Detail lengkap ada di AGENTS.md branch binance.

## Konvensi & hal yang perlu diingat

- User komunikasi dalam **Bahasa Indonesia** (santai).
- **Risk-averse**: risk per trade terkontrol (BTC 1.5% / XAU 0.5% equity), jangan longgarkan daily loss. Kalau mau eksperimen agresif → demo dulu, bukan live.
- Perubahan prompt = diskusi dulu sebelum apply (user minta bahas dulu).
- User suka angka dari sumber kebenaran: profit = query MT5 langsung, bukan log campuran.
- Kalau bikin skrip analisis sementara → taruh di `scratch/`, lalu HAPUS setelah dipakai (user minta dibersihin).
- User minta commit + push ke `dev` setelah kerjaan verified (tapi tanya dulu / tunggu permintaan eksplisit).
- Magic number bot: `20260625`. Bot cuma kelola posisi dengan magic ini.
- LLM timeout 24s, fallback berurutan (OpenAI → Gemini → slot-3 untuk primary).
- **Slot-3 (default DeepSeek, historis Claude) = model paling analitis** (detail R:R, struktur, level). **OpenAI = konservatif tapi solid**. **Gemini = variatif, kadang confident tinggi**. HOLD conf 0 = netral di weighted voting.
