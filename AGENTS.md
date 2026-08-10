# AGENTS.md — Konteks Proyek Trading Bot

> Ringkasan cepat untuk sesi coding. Baca ini dulu sebelum ngapa-ngapain.

## Apa ini

Bot trading **multi-LLM consensus** (OpenAI + Gemini + Claude) yang jalan di **MetaTrader 5**.
- **XAUUSD-ECNc** (Gold): scalping **M5**, weekday, MTF context M30/H1
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
| `src/core/consensus.py` | **Weighted confidence consensus** (skor = Σ confidence per arah, threshold per-symbol, min 2 model searah) + SL/TP floor (2× spread, 1× ATR) |
| `src/core/risk_engine.py` | Gate: spread, sesi, danger zone, daily loss, recovery mode, BEP tolerance, **risk-based lot sizing** |
| `src/core/mt5_connector.py` | Order send/close (retry + fill policy dinamis), history deals, market data, magic filter |
| `src/analytics/forecast_engine.py` | Forecast multi-horizon per-symbol (XAU T+15m/T+60m, BTC T+4h/T+D1), invalidation, entry zone — **informational, tidak memblokir** |
| `src/analytics/macro_analyst.py` | Fundamental + MTF context (per-symbol: XAU M30/H1, BTC H1/H4), cache per symbol |
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
6. `validate_forecast_trigger` — **HANYA INFORMATIONAL** (di-print, TIDAK ngeblokir eksekusi)
7. **Risk-based lot sizing** — lot dihitung dari equity & SL (BTC 1.5%, XAU 0.5%), bukan statis
8. Cek max posisi, eksekusi order (2 posisi kalau 3/3 sepakat)

## Gate eksekusi yang SEBENERNYA (hard)

- **Weighted consensus**: ≥ 2 model searah, skor confidence > threshold per-symbol (XAU 1.0 / BTC 1.2; 3/3 defensif = ×1.5)
- SL/TP di-floor: SL ≥ max(2× spread, 1× ATR), TP ≥ 1.5× SL
- Spread ≤ 50 pts (XAU) / 2400 pts (BTC)
- Session London/NY WIB + bukan danger zone (kecuali crypto)
- Max daily loss $50, max 3 consecutive loss, max 6 posisi (4 recovery)
- **TIDAK ada** gate confidence minimum numerik tambahan di luar weighted score
- **TIDAK ada** gate entry zone numerik — `optimal_entry_min/max` di-load tapi nggak dipakai
- Forecast R:R cuma print (informational)
- **Counter-trend di-block**: entry SELL saat forecast BULLISH (atau sebaliknya) langsung ditolak

## Status terkini (AGUSTUS 2026 — PENTING)

### Perubahan struktural 8 Agustus (sudah di-commit & push ke `dev`)

1. **BTC pindah ke M30** (dari M5): spread BTC ~$17 = 78% dari ATR M5 ($21), tapi kecil relatif ke ATR M30. M5 scalping BTC cuma bleed spread. `config.get_timeframe()` → BTC M30, XAU M5.
2. **MTF per-symbol**: XAU scan M30/H1, BTC scan H4/D1 (`config.get_higher_timeframes()`).
3. **Weighted confidence consensus** (bukan vote 2/3 murni): skor arah = Σ confidence; menang kalau ≥ 2 model searah DAN skor > threshold (`confidence_threshold_for()`: XAU 1.0, BTC 1.2; defensif ×1.5). Model @51% tidak lagi setara @90%.
4. **Prompt dinamis per-symbol**: BTC "M30 Intraday Strategy", XAU "M5 Scalping Strategy". Sebelumnya hardcode M5 — LLM dikasih candle H1 tapi disuruh scalper M5 → semua HOLD.
5. **Money scale di prompt**: `usd_per_point` (dari `trade_tick_value`), spread USD, "NEVER set SL closer than 2x spread". Sebelumnya prompt bilang "(1 point = 0.01)" yang menyesatkan → LLM kasih SL di dalam spread.
6. **SL/TP floor di consensus**: SL ≥ max(2× spread, 1× ATR), TP ≥ 1.5× SL. Cegah SL di dalam noise/spread.
7. **`get_open_positions` filter magic** — bot tidak bisa close posisi manual user.
8. **Position manager multi-symbol + tick freshness**: manage semua posisi bot, skip kalau market tutup (XAU weekend) — `POSITION_MANAGER_MAX_TICK_AGE_SECONDS`.
9. **BEP tolerance ±0.04** (`BREAK_EVEN_TOLERANCE_USD`) — trade dengan |profit| ≤ $0.04 dianggap BEP (tidak nambah loss streak, tidak reset, excluded dari win rate).
10. **Recovery exit threshold**: win < $0.10 tidak exit recovery mode (`RECOVERY_EXIT_PROFIT_USD`).
11. **Per-symbol breakdown** di log harian: `BTCUSD.c: 4T 0W-4L WR 0% | 4 BEP $-1.73`.
12. **Banner dinamis**: "Simbol: BTCUSD.c | Timeframe: M30 | Spread Filter: 2400 pts maks (BTCUSD.c)".
13. **Risk-based lot sizing** (`get_effective_lot_size(sl_points)`): lot = risk_usd / (SL pts × usd_per_point). Per-symbol risk: **BTC 1.5%** equity, **XAU 0.5%** (karena XAU bisa 6 posisi → max ~3% aggregate). Urutan: risk-based → recovery/session multiplier → clamp+round ke volume_step. Margin safety net (lot diturunkan kalau margin > 50% free). Fallback 0.01 kalau SL tidak diketahui.
14. **Forecast horizon per-symbol**: XAU T+15m/T+60m, **BTC T+4h/T+D1** (15 menit itu noise untuk M30 swing + spread $17). Cache refresh: XAU 15 menit, **BTC 1 jam**. `horizon_label` di forecast dict.
15. **Claude ganti DeepSeek** (`claude-sonnet-4-6`): DeepSeek konservatif (0% BUY, HOLD/SELL dominan, conf fluktuatif 0-65%) → tidak efektif di weighted voting. Claude reasoning lebih tajam (sadar R:R vs spread). **Truncated JSON recovery** di `clean_json_response` + `max_tokens=2000` karena Claude bisa motong respons. **Catatan: claude-sonnet-5 tidak support `temperature`; sonnet-4-6 ~40% lebih cepat (7.2s vs 12.1s di prompt panjang).**
16. **Pemisahan entry vs position management di prompt**: `signal` = murni entry baru, `position_actions` = posisi existing, dinilai independen (cegah LLM campur "existing BUY masih bagus" sebagai alasan HOLD entry).
17. **Gemini ganti ke `gemini-3.1-flash-lite`** (fallback `gemini-3.5-flash-lite`): benchmark 5 model Gemini (10 iterasi, prompt produksi, sesi bearish) — 3.5-flash-lite dominan HOLD (8/10), 2.5-flash-lite parah (10/10 HOLD conf 36%), **3.1-flash-lite paling konsisten ngikutin sinyal (10/10 SELL, conf 65%, latency 1.1s)**. 3.6-flash juga bagus (9/10, conf 69%) tapi 7.5s latency. Catatan: Gemini return confidence skala 0-1 (bukan 0-100), di-×100 di consensus.
18. **Deteksi close manual (magic=0)**: manual close dari MT5 mobile menghasilkan OUT deal `magic=0` (magic tidak diteruskan). `get_closed_positions_today` menerima OUT magic=0 **hanya jika posisi dibuka bot** (ada IN magic bot) — posisi manual user tidak ikut kehitung. Window P/L = tengah malam WIB → next-midnight (bukan rolling 24h, biar loss kemarin tidak masuk "hari ini"). **Jangan diubah ke rolling 24h** — itu bikin daily loss cap ke-trip dari loss hari sebelumnya.

### Catatan akun & operasional
- LIVE `VTMarkets-Live 3` login `27556325`, balance ~$1065. Profit verifikasi = query MT5 langsung (`scratch/` script, hapus setelah dipakai).
- Git branch: `dev`. Commit terakhir sesi 10 Agustus: `c8079dd` (Gemini 3.1-flash-lite).
- **Gemini 3.1-flash-lite** (primary) + **3.5-flash-lite** (fallback); OpenAI gpt-5.4-mini; Claude sonnet-4-6. Dynamic config ambang optimal **>65%** (bukan 70%). Threshold XAU 1.0 / BTC 1.2 (defensif 3/3 = ×1.5).
- `git status` biasanya ada `data/dynamic_rules.json`, `data/forecast_cache.json`, `data/memory_lessons.json`, `data/decision_memory.json`, `data/position_manager_state.json`, `data/risk_state.json` ter-modif — itu runtime state, jangan commit kalau nggak sengaja.
- Lessons BTC pernah bikin bot HOLD terus (8 lesson "avoid 5-minute BTC scalps" dari era M5 yang gagal) — sudah di-clear. Kalau bot mulai HOLD terus lagi, cek `memory_lessons.json` dulu.
- **Status display live** menampilkan posisi terbuka semua symbol + floating P/L tiap 5 detik (`get_all_open_positions`).
- Claude kadang lambat di prompt panjang (34s di sonnet-5, ~8-20s di sonnet-4-6) — wajar untuk M30 cycle 1x/30 menit.

## Bot Binance Spot (`binance_bot/`) — BOT KEDUA

> Bot terpisah untuk **Binance spot** (BTC/ETH/SOL), modal kecil (tes ~$12/Rp 200rb), deploy Linux. **Tidak menyentuh bot MT5.**

- **Arsitektur 2 proposer + 1 approver**: GPT + Gemini vote (paralel), **Claude approver INDEPENDEN** — dapat data mentah sama dgn proposer (40 candle M5/M15, indikator, MTF M15/M30/H1, S/R zones, liquidity sweeps) dan diinstruksikan menganalisis sendiri, bukan cuma setuju/tidak dgn proposer. Dipanggil saat 2/2 sepakat ATAU HOLD-streak aktif.
- **HOLD-streak**: `HOLD_STREAK_THRESHOLD=5` cycle HOLD beruntun → cukup **1 BUY kuat (`HOLD_STREAK_BUY_CONFIDENCE=0.60`)** lanjut ke approver. Mencegah Gemini/OpenAI yang konservatif memblokir selamanya. Di-track di `risk_state.json` (`hold_streak`), reset saat ada BUY lolos.
- **Sizing dual-mode**: `POSITION_ALLOCATION_PCT=0` (default) = risk-based 1.5% equity; `>0` (mis. 50) = pakai % equity langsung per posisi (cocok spot). **Notional di-clamp ke saldo free USDT** (minus buffer fee) — dry-run tidak bisa "beli" > saldo. `get_free_usdt()` di connector.
- **Spot, tanpa margin/futures**: tidak bisa short (hanya BUY), nol risiko liquidation/hutang. Signal SELL tanpa posisi = hold USDT; SELL saat punya posisi = exit.
- **SL/TP via OCO order** (`POST /api/v3/orderList/oco`) — spot tanpa SL/TP broker; jalan di sisi exchange. `stopLimitPrice` di sisi aman (SELL 0.99× / BUY 1.01× stop — pola Freqtrade).
- **REST API `/api/v3/*`** + HMAC API key (dari `.env`). Changelog Binance: `/api/v1/*` sudah retire; signed request wajib percent-encode sebelum signing; `userDataStream` REST dihapus (pakai polling REST atau WebSocket API Ed25519).
- **⚠️ Dua gotcha testnet**: (1) `REST_BASE` TANPA `/api` (path endpoint sudah include `/api/v3/*` — dulu dobel → 404); (2) WAF testnet block user-agent `Python-urllib` → semua request wajib User-Agent browser.
- **Timeframe M5 default** (env `BINANCE_TIMEFRAME=15m/30m/1h`) — **M15/M30 lebih cocok buat profit** (fee 0.2% round-trip vs target 0.5-1% M5 = boros); M5 buat validasi sinyal. **⚠️ env `BINANCE_TIMEFRAME` WAJIB `.strip()`** — trailing space bikin error "Illegal characters in interval" (bug "spasi" kedua).
- **Risk 1.5%** per trade dari equity USDT, **daily loss $3** (ketat utk modal $12), cooldown, min notional $0.5 (TokoCrypto), max 2 posisi, trading 24/7.
- **Balance gagal → skip cycle**: kalau `get_account_balance_usdt()` return 0 (rate limit sesaat), cycle di-skip — jangan lanjut dgn equity $0 (bikin Claude salah reject "impossible").
- **Position tracking lokal** (`risk_state.json` → `positions`) — spot tidak simpan entry price di exchange, jadi bot track sendiri (record saat BUY, close saat OCO kena / SELL exit). Posisi dry-run nyangkut kalau tidak pernah di-close → bersihkan state manual.
- **Dry-run realistis**: simulasi fill + slippage 0.05% + fee 0.1% (pola Freqtrade), bukan cuma log.
- Config: `binance_bot/config.py` — `TESTNET=True` + `DRY_RUN=True` default (AMAN). `False` = live, jangan ubah tanpa diskusi.
- Flow: loop 5 detik (manage posisi + deteksi close via OCO status) → candle (M5/M15/M30) → risk gate → 2 proposer → Claude approve → OCO order.
- Test: `binance_bot/tests/` (mock API connector + risk + position tracking + hold-streak + sizing clamp + approver prompt). **Testnet sudah verified** (server_time, symbol_info, balance $10k, klines OK; API key testnet di `.env`).
- Referensi: `external_repos/freqtrade/` (clone utk pola risk/dry-run/stoploss). Repo lain: OpenTrader (TS, grid/DCA), BTC-Trading-Since-2020 (dataset BitMEX 6 tahun).
- Deploy: `pip install -r binance_bot/requirements.txt` + systemd `Restart=always` di VPS Linux.

## Konvensi & hal yang perlu diingat

- User komunikasi dalam **Bahasa Indonesia** (santai).
- **Risk-averse**: risk per trade terkontrol (BTC 1.5% / XAU 0.5% equity), jangan longgarkan daily loss. Kalau mau eksperimen agresif → demo dulu, bukan live.
- Perubahan prompt = diskusi dulu sebelum apply (user minta bahas dulu).
- User suka angka dari sumber kebenaran: profit = query MT5 langsung, bukan log campuran.
- Kalau bikin skrip analisis sementara → taruh di `scratch/`, lalu HAPUS setelah dipakai (user minta dibersihin).
- User minta commit + push ke `dev` setelah kerjaan verified (tapi tanya dulu / tunggu permintaan eksplisit).
- Magic number bot: `20260625`. Bot cuma kelola posisi dengan magic ini.
- LLM timeout 24s, fallback berurutan (OpenAI → Gemini → Claude untuk primary).
- **Claude = model paling analitis** (detail R:R, struktur, level). **OpenAI = konservatif tapi solid**. **Gemini = variatif, kadang confident tinggi**. HOLD conf 0 = netral di weighted voting.
