# AGENTS.md — Konteks Proyek Trading Bot

> Ringkasan cepat untuk sesi coding. Baca ini dulu sebelum ngapa-ngapain.

## Apa ini

Bot trading **multi-LLM consensus** (OpenAI + Gemini + Claude) yang jalan di **MetaTrader 5**.
- **XAUUSD-ECNc** (Gold): short-term intraday swing **M15**, weekday, MTF context M30/H1. Config default `WEEKDAY_SYMBOL = "XAUUSD-ECNc"` (langsung nama broker live — FASE 1; `get_valid_trade_symbol` tetap auto-correct kalau suffix beda, mis. demo).
- **BTCUSD.c** (Bitcoin): intraday **M30**, weekend + setelah jam 22:00 Jumat WIB (rotasi otomatis, `config.get_active_symbol`). **MTF context H1/H4, forecast horizon T+4h/T+D1 (bebas swap overnight).**
- **TRADING_MODE** (config/.env/UI dashboard): `"xau"` (default, XAU only) | `"xau_pairs"` (**parallel scan pool 7 simbol**: XAU + 6 FX cross, FASE 1). Pool = `WEEKDAY_SYMBOL` + `FX_PAIR_SYMBOLS` (default `GBPCHF-ECNc, EURCHF-ECNc, GBPNZD-ECNc, EURJPY-ECNc, GBPUSD-ECNc, EURAUD-ECNc`), dipotong `MAX_ROTATION_SYMBOLS` (7). **Timeframe per aset: XAU M15 (swing pendek), FX H1 (swing), BTC M30** — risk per trade XAU 1.0% / FX 1.0% / BTC 1.5% (XAU naik dari 0.5% pada 13 Agustus: min lot 0.01 broker gak bisa mewakili risk 0.5% dengan SL struktur lebar). **Smart Timeframe Rotation (FASE 5)**: LLM call per simbol HANYA pas candle timeframe simbol itu berganti (`_symbol_last_candle` di main.py) — XAU tiap 15 menit, FX tiap 1 jam, BTC tiap 30 menit (hemat token drastis). Weekend: FX tutup → pool jatuh ke XAU (atau BTC kalau `ENABLE_BTC_ROTATION`). Max posisi & daily loss **aggregate semua simbol** (bukan per-simbol). Implementasi: `run_trading_cycle()` → loop `for sym in pool: config.SYMBOL = sym; _run_cycle_for_current_symbol()` (post-mortem 1× aggregate per candle, macro/MTF per-symbol di-populate di dalam loop).
- Akun: **LIVE** `VTMarkets-Live 3` (login `27556325`) — jangan pernah test sembarangan tanpa konfirmasi
- Balance awal $1000, sekarang ~$1065
- Waktu semua pakai **WIB** (Asia/Jakarta)

## Cara jalanin

```bash
python main.py
```
- `config.DRY_RUN = False` → **LIVE trading** (order beneran dikirim). Jangan ubah tanpa bilang user.
- **Ganti mode trading**: `.env` `TRADING_MODE=xau` / `TRADING_MODE=xau_pairs`, atau via UI dashboard (dropdown Mode Trading → POST `/api/config`, di-persist ke `.env`) → **restart bot** biar apply (dashboard serve = proses terpisah dari bot).
- Log: `trading_bot.log` (auto-rotate 2MB, keep 5000 baris). **Log ini CAMPUR sesi demo + live** — akun demo lama `1157958` (ticket `568xxx`/`569xxx`), akun live `27556325` (ticket `1159xxx`). Jangan hitung profit dari log tanpa pisahin sesi — query MT5 langsung lebih akurat.

## Arsitektur file

| File | Fungsi |
|---|---|
| `main.py` | Loop utama: manage posisi tiap 3 detik, full cycle tiap candle per-symbol (M15 XAU / H1 FX / M30 BTC) dengan **Smart Timeframe Rotation** (`_symbol_last_candle`) |
| `config.py` | Semua parameter + helper per-symbol (`get_timeframe`, `get_higher_timeframes`, `lot_size_for`, `risk_percent_for`, `default_sl/tp`, `max_spread_points`, `confidence_threshold_for`) |
| `src/core/llm_client.py` | **Build prompt dinamis per-symbol** + call LLM paralel sesuai **time-based AI mode** (single→OpenAI, dual→OpenAI+Gemini, triple→OpenAI+Gemini+DeepSeek) |
| `src/core/consensus.py` | **Weighted confidence consensus** (skor = Σ confidence per arah, threshold per-symbol, min 2 model searah) + SL/TP mode-aware **per-kategori** (`config.sltp_mode_for(symbol)`, 13 Agustus): **XAU & BTC = fix ATR-Based** → **GATE**: proposal AI dipakai, tapi trade DITOLAK kalau SL < SL_MULT× ATR atau TP < TP_MULT× ATR (bukan dinaikkan — cari setup yang secara alamiah 2R); **multiplier dinamis per AI mode: single 1.25/2.5, dual 1.5/3.0, triple 1.75/3.5 — R:R 2:1 selalu**; **FX = LLM** → bebas struktur, Safety Floor `max(2x spread, 0.5x default_sl_points)` + gate R:R minimum **1:1** (TP ≥ SL)) + **outlier filter SL/TP (average, nilai "beda sendiri" dibuang)** |
| `src/core/risk_engine.py` | Gate: spread, sesi, daily loss, recovery mode, BEP tolerance, **risk-based lot sizing** (danger zone dimatikan — full 24 jam) |
| `src/core/mt5_connector.py` | Order send/close (retry + fill policy dinamis), history deals, market data, magic filter |
| `src/analytics/forecast_engine.py` | Forecast multi-horizon per-symbol (XAU T+15m/T+30m, BTC T+4h/T+D1), invalidation, entry zone — **informational, tidak memblokir** |
| `src/analytics/macro_analyst.py` | Fundamental + MTF context per-symbol (XAU M30/H1, FX H4/D1, BTC H1/H4), **cache berlaci per-symbol** (FASE 4 — nggak di-reset pas simbol bergeser; window proporsional: M15=48 bar, M30=72 bar, H4/D1=30 bar) |
| `src/analytics/trade_evaluator.py` | Post-mortem tiap trade → lessons (`data/memory_lessons.json`), per-symbol |
| `src/analytics/dynamic_config.py` | Adaptasi otomatis: win rate <40% → threshold 3/3; >70% → 2/3 |
| `src/analytics/position_manager.py` | Trailing stop, break-even, partial close — **semua symbol, skip kalau market tutup** |
| `src/analytics/decision_memory.py` | 6 keputusan terakhir per symbol (HOLD-streak awareness) + **outcome tracking**: `record(..., result="OPEN")` pas trade dieksekusi, `update_result(symbol, result, profit, commission)` pas close (profit NET sudah termasuk komisi) → `summarize_recent_outcomes` hitung win/loss/BEP AKURAT dari profit (BEP tolerance dinamis per komisi), bukan cuma count HOLD |

## Alur cycle (main.py → run_trading_cycle)

0. **Time-Based AI Mode** (WIB, 12 Agustus): 00:01–09:59 = **single** (OpenAI), 10:00–15:00 = **dual** (OpenAI+Gemini), 15:01–19:29 = **single** (OpenAI), **19:30–21:30 = triple** (OpenAI+Gemini+DeepSeek — London-NY overlap, volatilitas tertinggi), 21:31–23:59 = **single** (OpenAI). Config: `AI_MODE_POLICY` (schedule|fixed), `AI_MODE_SCHEDULE`, `AI_FIXED_MODE`. Mode di-resolve **fresh tiap cycle** (gak ada cache) — rotasi jalan mulus mid-trade.
1. `risk.can_trade()` — spread/sesi/daily loss gate. Gagal → skip (nggak ada biaya LLM)
2. Ambil 50 candle timeframe aktif (M15 XAU / H1 FX / M30 BTC) + tick
3. Post-mortem evaluasi trade tertutup + dynamic rules (BEP excluded dari win rate)
4. **Panggil LLM paralel sesuai time-based AI mode** (single: 1 model / dual: 2 / triple: 3 — lihat jadwal WIB di bawah)
5. **Weighted consensus**: skor BUY/SELL = Σ confidence model searah; menang kalau ≥ min_models searah & skor > threshold (XAU 1.0, BTC 1.2, defensif ×1.5; **single mode: 1 model + threshold ×0.6**). Plus AI re-evaluator CLOSE posisi
6. Forecast context (bias/target/entry zone) **murni informational** — di-inject ke prompt LLM, TIDAK memblokir eksekusi (tidak ada gate counter-trend; `validate_forecast_trigger` sudah dihapus)
7. **Risk-based lot sizing** — lot dihitung dari equity & SL (BTC 1.5%, XAU 1.0%, FX 1.0%), bukan statis
8. Cek max posisi, eksekusi order (2 posisi kalau 3/3 sepakat)

## Gate eksekusi yang SEBENERNYA (hard)

- **Weighted consensus**: ≥ 2 model searah, skor confidence > threshold per-symbol (XAU 1.0 / BTC 1.2; 3/3 defensif = ×1.5)
- SL/TP per kategori (`config.sltp_mode_for(symbol)` — **13 Agustus, pisah logic per-simbol biar enak debug**):
  - **XAUUSD & BTC = fix ATR-Based (SELALU, tidak bisa di-override ke LLM)**: **GATE LAYAK/TIDAK (Non-negotiable)** — proposal AI dipakai apa adanya, tapi trade DITOLAK otomatis kalau SL < SL_MULT× ATR atau TP < TP_MULT× ATR (**R:R 2:1 selalu**). Multiplier dinamis per AI mode: single 1.25×/2.5×, dual 1.5×/3.0×, triple 1.75×/3.5×. Position management tetap ATR-based. Alasan: floor 400 pts cuma 0.49× ATR M15 (~819 pts) — terlalu scalping utk swing M15.
  - **FX pairs = LLM (bebas struktur)**: SL/TP murni struktur LLM (`invalidation_price`/`target_price`), dibatasi **Safety Floor** minimal `max(2x spread, 0.5x default_sl_points)` (FX 50 pts) + **gate R:R minimum 1:1** (TP ≥ SL). **Position management (BEP/trailing) pindah ke basis SL posisi (bukan ATR/%-TP)** — lihat entri 13 Agustus di bawah.
  - **Force override**: kalau `config.TP_SL_RULES` di-set eksplisit "ATR-Based" via CLI/`--tpsl-rules`/`.env`, SEMUA kategori (termasuk FX) ikut ATR-Based. Default "LLM" = aturan per-kategori di atas.
- Spread ≤ 50 pts (XAU & FX) / 2400 pts (BTC)
- **Trading 24 jam** (XAU + BTC, 11-08): danger zone dimatikan (`DANGER_ZONES_WIB = []`) + session XAU diperluas — Asia Dawn 05:00-07:00 (×0.7), Tokyo 07:00-16:00 (×0.7), London 15:00-23:59 (×1.0), London-NY 20:00-23:59 (×1.2), NY 20:00-05:00 (×1.0). Tidak ada jam yang diblokir
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
2. **MTF per-symbol**: XAU scan M15/M30, FX scan H4/D1, BTC scan H1/H4 (`config.get_higher_timeframes()`).
3. **Weighted confidence consensus** (bukan vote 2/3 murni): skor arah = Σ confidence; menang kalau ≥ 2 model searah DAN skor > threshold (`confidence_threshold_for()`: XAU 1.0, BTC 1.2; defensif ×1.5). Model @51% tidak lagi setara @90%.
4. **Prompt dinamis per-symbol**: BTC "M30 Intraday Strategy", XAU "M5 Scalping Strategy". Sebelumnya hardcode M5 — LLM dikasih candle H1 tapi disuruh scalper M5 → semua HOLD.
5. **Money scale di prompt**: `usd_per_point` (dari `trade_tick_value`), spread USD, "NEVER set SL closer than 2x spread". Sebelumnya prompt bilang "(1 point = 0.01)" yang menyesatkan → LLM kasih SL di dalam spread.
6. **SL/TP floor di consensus (mode-aware)**: ATR-Based → SL ≥ max(2× spread, SL_MULT× ATR), TP ≥ max(2× spread, TP_MULT× ATR) (**R:R 2:1**); LLM → dibatasi oleh **Safety Floor** minimal `max(2x spread, 0.5x default_sl_points)` (XAU 250 pts, FX 50 pts, BTC 25000 pts) untuk mencegah rogue/hallucinated stops yang membengkakkan lot size. **Multiplier per AI mode (11 Agustus): single 1.25/2.5, dual 1.5/3.0, triple 1.75/3.5** — `config.atr_sl_multiplier()` / `atr_tp_multiplier()`, sinkron di consensus gate + prompt `atr_gate_str`.
7. **`get_open_positions` filter magic** — bot tidak bisa close posisi manual user.
8. **Position manager multi-symbol + tick freshness**: manage semua posisi bot, skip kalau market tutup (XAU weekend) — `POSITION_MANAGER_MAX_TICK_AGE_SECONDS`.
9. **BEP tolerance ±0.04** (`BREAK_EVEN_TOLERANCE_USD`) — trade dengan |profit| ≤ $0.04 dianggap BEP (tidak nambah loss streak, tidak reset, excluded dari win rate).
10. **Recovery exit threshold**: win < $0.10 tidak exit recovery mode (`RECOVERY_EXIT_PROFIT_USD`).
11. **Per-symbol breakdown** di log harian: `BTCUSD.c: 4T 0W-4L WR 0% | 4 BEP $-1.73`.
12. **Banner dinamis**: "Simbol: BTCUSD.c | Timeframe: M30 | Spread Filter: 2400 pts maks (BTCUSD.c)".
13. **Risk-based lot sizing** (`get_effective_lot_size(sl_points)`): lot = risk_usd / (SL pts × usd_per_point). Per-symbol risk: **BTC 1.5%** equity, **XAU 1.0%** (naik dari 0.5% — min lot 0.01 gak bisa mewakili risk 0.5% dengan SL lebar), **FX 1.0%**. Urutan: risk-based → recovery/session multiplier → clamp+round ke volume_step. Margin safety net (lot diturunkan kalau margin > 50% free). Fallback 0.01 kalau SL tidak diketahui.
14. **Forecast horizon per-symbol**: XAU T+15m/T+30m, **BTC T+4h/T+D1** (15 menit itu noise untuk M30 swing + spread $17; XAU M5 cukup horizon pendek — nggak nangkep trend jangka panjang). Cache refresh: XAU 15 menit, **BTC 1 jam**. `horizon_label` di forecast dict.
15. **Slot ke-3 = DeepSeek V4 Flash (default, configurable)**: `CLAUDE_MODEL = "deepseek/deepseek-v4-flash"` — jauh lebih murah dari `claude-sonnet-4-6` (buat akun cent, ~$2/hari Claude itu mahal vs risk per trade puluhan sen). Routing otomatis di `query_claude()`: `deepseek/...` → DeepSeek API (OpenAI-compatible, base `https://api.deepseek.com/v1`), `claude-...` → Anthropic. Fallback `claude-haiku-4-5-20251001` (cuma kepanggil kalau DeepSeek error). Ganti model via menu setup / `--claude-model`. Log label otomatis ("DeepSeek" vs "Claude"). **Catatan lama (historis):** era sonnet-4-6 = model paling analitis (sadar R:R vs spread); DeepSeek konservatif (HOLD/SELL dominan).
16. **Pemisahan entry vs position management di prompt**: `signal` = murni entry baru, `position_actions` = posisi existing, dinilai independen (cegah LLM campur "existing BUY masih bagus" sebagai alasan HOLD entry). **Pullback Tolerance**: Prompt Re-Evaluator di-enhance untuk melarang keras aksi CLOSE dini pada koreksi/pullback M15 normal (hanya boleh CLOSE jika level invalidasi teknis rusak nyata atau terjadi reversal terkonfirmasi).
17. **Gemini ganti ke `gemini-3.1-flash-lite`** (fallback `gemini-3.5-flash-lite`): benchmark 5 model Gemini (10 iterasi, prompt produksi, sesi bearish) — 3.5-flash-lite dominan HOLD (8/10), 2.5-flash-lite parah (10/10 HOLD conf 36%), **3.1-flash-lite paling konsisten ngikutin sinyal (10/10 SELL, conf 65%, latency 1.1s)**. 3.6-flash juga bagus (9/10, conf 69%) tapi 7.5s latency. Catatan: Gemini return confidence skala 0-1 (bukan 0-100), di-×100 di consensus.
18. **Deteksi close manual (magic=0)**: manual close dari MT5 mobile menghasilkan OUT deal `magic=0` (magic tidak diteruskan). `get_closed_positions_today` menerima OUT magic=0 **hanya jika posisi dibuka bot** (ada IN magic bot) — posisi manual user tidak ikut kehitung. Window P/L = tengah malam WIB → next-midnight (bukan rolling 24h, biar loss kemarin tidak masuk "hari ini"). **Jangan diubah ke rolling 24h** — itu bikin daily loss cap ke-trip dari loss hari sebelumnya. **Reason close di-label** ("manual" untuk magic=0, SL/TP/stop-out dari kode MT5) — bukan "unknown".
19. **Post-mortem langsung saat close**: dipicu di loop 5 detik pas `sync_closed_positions` return `new_deals` (background thread biar nggak nge-block), bukan nunggu candle. `check_and_evaluate_closed_trades(deals)` nerima deals langsung. **Jangan seed `evaluated_tickets` dari `known_closed` tiap cycle** — itu nge-block tiket baru (bug yang udah diperbaiki); re-evaluation dicegah oleh `evaluated_tickets` persist di `memory_lessons.json`.
20. **Trailing stop (mode-aware, update 13 Agustus)**: activation `min(0.85×ATR, cap)` (XAU 500 / BTC 40000 pts) — **mode LLM: activation `max(1.5×SL original, fallback)`, cap 60% TP; distance SL-based `0.8→0.3×SL`** (lihat entri 13 Agustus). Distance `0.5×ATR` (dulu 2.0×/1.5× yang bikin trailing nggak pernah aktif — activation 760+ pts jauh di atas TP M5). SL di-trail dari **harga ekstrem** sejak entry (`trailing_extremes` di `position_manager_state.json`) — pullback nggak narik SL mundur. **Partial close di-skip di lot 0.01** (`volume <= volume_min`) karena gabisa dipecah.

### Perubahan 14 Agustus — LLM Rules baru (Daily Profit Target 6%, Dead Zone subuh, Safety Floor/R:R 1.25)

**Latar belakang:** prompt dev-quant (6 enhancement blocks) diuji ~13 jam → 14 trade, 4W-10L, −$94.83 (didominasi FX −$77.90, semua SL penuh, nol TP hit). Sample terlalu kecil utk menyimpulkan; user balik ke `dev` (prompt bersih) dan minta aturan risk baru alih-alih ngutak-atik prompt.

**Perubahan (config + risk_engine + consensus + prompt sync):**
1. **Daily Profit Target 6%** (`DAILY_PROFIT_TARGET_PERCENT`, default 6.0): begitu net profit harian (window WIB-midnight via `get_closed_positions_today`) ≥ 6% balance MT5 → `can_trade()` nolak semua posisi baru sampai tengah malam WIB berikutnya (reset otomatis). Implementasi: `_check_daily_profit_target()` di risk_engine (dipanggil setelah `_check_daily_loss`). **Pakai `c["profit"]` saja** — profit dari connector SUDAH net (termasuk swap+komisi); jangan tambah `c["commission"]` lagi (double-count). Balance ≤ 0 (MT5 disconnect) → skip (jangan blokir).
2. **Dead Zone 02:00–06:00 WIB** (`DANGER_ZONES_WIB` diisi lagi, sebelumnya `[]`): blokir TOTAL posisi baru jam 02:00-06:00 WIB utk XAU & FX (crypto/BTC otomatis di-skip di `_check_danger_zones` — BTC tetap 24/7). Sesi lain tetap bebas.
3. **Safety Floor Mode LLM per-kategori** (config): `LLM_SAFETY_FLOOR_FX_PTS = 250` (25 pips, ganti dari `0.5×default_sl` = 50 pts), `LLM_SAFETY_FLOOR_XAU_PTS = 400` (tetap). Di `_apply_sltp_rules` mode LLM: SL di-floor ke minimal tsb (max dgn 2×spread).
4. **R:R minimum 1.25:1** (`LLM_MIN_RR_RATIO = 1.25`, ganti dari 1.0): **TP di-NAIKKAN ke minimal 1.25×SL** (bukan tolak trade) — `tp_points = max(tp_points, int(sl_points*1.25))`. Konsisten dgn filosofi floor (SL juga di-floor, bukan ditolak).
5. **Prompt sync** (`llm_client._build_sltp_rules_block`): teks "R:R at least 1:1" diganti `{min_rr}:1` (1.25) utk XAU/BTC/FX; FX tambah "SL ≥ 250 pts (25 pips)"; docstring/CLI help ikut di-update.
6. **Lot sizing murni risk-based** — `config.max_lot_for()` DIHAPUS 14 Agustus (XAU cap 0.01 tidak ada lagi); lot = risk_usd / (SL pts × usd_per_point), clamp ke volume_min/max broker + margin safety net. Gate OVER-RISK di consensus tetap melindungi (SL > max budget risk di min lot → tolak).
7. **Test**: `scratch/test_llm_rules_and_risk.py` — 16 PASS (floor FX 50→250 & TP→312, XAU 300→400 & TP→500, SL wajar 600/900 tak diubah, daily target +$65 → tolak & +$20 → boleh, dead zone 03:00 tolak & 01:00/07:00 boleh & BTC bebas).
8. **Fix kontradiksi prompt "exactly at" + format harga FX** (llm_client + macro_analyst): 
   - Teks lama "SL is placed **exactly at** the invalidation price level / TP at target_price" dihapus (teknisnya salah: bot geser SL pas floor aktif) → diganti **"at or slightly beyond"** + pernyataan eksplisit **"bot enforces floors automatically — kamu tidak perlu stretch level"** + HOLD message digabung jadi satu. Berlaku di static RISK CONSTRAINTS + blok XAU/BTC/FX (LLM) + blok ATR-Based.
   - RISK CONSTRAINTS ditambah 3 hal: (a) instruksi proses **"read data first → form thesis → validate against constraints"** (anti force-fit); (b) definisi invalidation eksplisit: **nearest opposing swing structure di belakang entry** (BUY → swing low terakhir di bawah; SELL → swing high terakhir di atas) — *bukan* extreme latest candle, *bukan* swing terjauh window; (c) **ATR(14) sanity check lunak**: SL << 0.5×ATR = noise-level, prefer ~0.5-1×ATR kalau struktur ngizinin.
   - **Format harga FX 5-desimal** (fix kritis, ketahuan pas print prompt GBPCHF): `.2f` meratakan ATR 0.00091 → "0.00", EMA 1.096 → "1.10", Fib semua "1.10" → LLM buta struktur. Sekarang pakai `_fmt_price()` (10-desimal strip trailing zero) di indikator summary, Fib (round 6-desimal dulu), PDH/PDL/Today Open, MTF macro (`_fmt()` di macro_analyst). EURJPY 3-desimal juga ikut kebener otomatis.
   - **Typical SL FX di unit definition** disinkronkan ke floor: 50-150 → **250-625 pts** (mode LLM, pola sama XAU 400-1000) — sebelumnya kontradiksi "typical 50-150" vs floor 250.
   - **Nearest Round Number FX**: `round(1.09815)` = 1 → "1.00" (9% jauh) → sekarang `round(bid, 2)` → 1.10 untuk harga < 100; BTC/XAU tetap kelipatan 1000/integer.
   - Preview prompt produksi: `scratch/preview_full_prompt.py` (XAU) + `scratch/preview_fx_prompt.py` (FX H1, build_system_prompt dipanggil dgn point_size dari tick) → hasil print di `testmd.md` / `testmdfx.md` (UTF-8 bersih via Python redirect, bukan PowerShell).
9. **ROLLBACK SL/TP: points-based lagi, invalidation cuma referensi probability** (fix 14 Agustus): model yang ngasih `invalidation_price`/`target_price` harga absolut ternyata SERING kontradiksi sama `sl_points`/`tp_points` (contoh: sl_points 610 tapi invalidation 147 pts dari entry) → bot pakai harga absolut → SL jadi 147 → di-floor 400, display "SL: 610" menyesatkan. Sekarang **`sl_points`/`tp_points` = REQUIRED & satu-satunya yang dipakai bot untuk order** (average + outlier filter di consensus, lalu floor/R:R/over-risk gate). `invalidation_price`/`target_price` = **OPTIONAL, cuma konteks thesis/probability model — TIDAK dipakai bot untuk SL/TP** (di prompt + OUTPUT FORMAT dipertegas). Main.py: tidak re-calc dari harga absolut lagi; hitung sl_price/tp_price dari points + tick live, spread gate tetap (`max(spread*2, sl)`), re-check `_apply_sltp_rules` tetap (batal kalau gagal). Display "Price SL/TP" di consensus = di-sync dari points final (bukan harga absolut model).
10. **OpenAI primary → `gpt-5.2`, fallback `gpt-4o-mini`** + **floor FX berbasis ATR** (fix 14 Agustus, hasil benchmark multi-sampel): `_execute_openai_single` diuji 13 model × real data (XAU + 5 FX, `scratch/compare_sltp_models.py` + `compare_sltp_multi.py`): gpt-5.2 = 4/6 trade, 4 SL natural, cepat 4.4s (vs gpt-5.4-mini/DeepSeek HOLD 6/6 — "nearest invalidation di bawah floor, no clean setup" = akar masalah bot jarang trade; gpt-5 = 50s (lewati timeout), gpt-4o-mini = SL generik 250/625 "main aman ke floor"). **Floor FX `LLM_SAFETY_FLOOR_FX_PTS=250` statis → dinamis `max(2x spread, 1.5x ATR H1)`** (`LLM_FX_FLOOR_ATR_MULT=1.5`, fallback 250 kalau ATR gagal) — floor statis 250 = 2.5-2.8×ATR H1 FX (~90-100 pts) bikin SL struktural asli (60-200) di-floor paksa + TP 312 (3.2×ATR) jarang kesampean (diduga penyebab performa FX merah). Efek: GBPCHF SL 63→136 (bukan 250), TP 170 (bukan 312), gpt-5.4-mini mulai trade di EURAUD (147/183). Implementasi: `consensus._apply_sltp_rules` (atr_points sudah dihitung di sana, `LLM_FX_FLOOR_ATR_MULT` di config), prompt FX sinkron via `_fx_atr_h1_points()` (cache 60s) di blok rules + typical range (contoh: "~142 pts = 1.5x ATR H1"). XAU tetap 400 statis (0.4×ATR M15, sudah proporsional). **Catatan benchmark 14 Agustus**: hasil multi-sampel itu diambil PAS floor FX masih statis 250 — semua SL "250" di hasil (termasuk o3-mini) kemungkinan floor-copying, BUKAN struktur asli. o3-mini SL struktural aslinya 155 (EURAUD) & 73 (GBPCHF) malah di-widen paksa ke 250 — korban floor yang sama. Keputusan fallback o3-mini vs 4o-mini BELUM final, perlu re-run benchmark dengan floor ATR baru.
11. **Window scheduling OpenAI primary (14 Agustus)**: `OPENAI_PRIMARY_WINDOW_WIB` (default `"15:00-19:30"` WIB, London open) — di dalam window pakai `OPENAI_MODEL` (gpt-5.2), di luar langsung `OPENAI_DEFAULT_MODEL` (**o3-mini**, main sejak 14 Agustus — SL struktural, reason spesifik, confidence bervariasi vs 4o-mini yang generik: "momentum continuation" copy-paste + SL/TP/confidence template 75% flat di semua pair), error/timeout → `OPENAI_FALLBACK_MODEL` (**gpt-4o-mini**). Alasan: gpt-5.2 free tier cuma 250k token/hari (SHARED antar model besar) vs 4o-mini 2.5M/hari; estimasi konsumsi ~6k token/call (prompt ~21.6k chars ≈ 5.7k input + ~250 output) → mode xau 96 cycle ≈ 576k token/hari, xau_pairs 240 ≈ 1.44M/hari → gpt-5.2 cuma tahan ~41 call (~4-10 jam) → dipakai pas volatilitas tertinggi aja (London-NY), sisanya 4o-mini. Implementasi: `_resolve_openai_primary()` di `query_openai` (llm_client.py) + `_parse_windows_wib()` di config. Usage API gratis (400/0) tidak expose → estimasi matematis. `FORECAST_MODEL` default gpt-5.4 (terpisah, forecast engine).

**Catatan**: prompt dev-quant (commit `a8192ad` + `4050517`) TIDAK ikut ke dev — enhancement blocks/RSI Direction eksperimen tetap di branch dev-quant. AGENTS.md/README yang menyebut 6 enhancement blocks hanya berlaku di dev-quant.

### Perubahan 11 Agustus (sesi ini — PENTING: branch split!)

**Sekarang ada DUA versi prompt yang berbeda antara branch:**
- **`main` = prompt LAMA** (`744ad0a`): Fibonacci + counter-trend pullback rules + prompt preview prints. **TIDAK ada** prompt_claude.md, **TIDAK ada** strip emoji.
- **`dev` = prompt BARU** (`06159f6`): semuanya dari main + prompt_claude.md + strip emoji.
- **JANGAN merge `dev` → `main` tanpa konfirmasi user** — user sengaja mau main pakai prompt lama, prompt baru eksperimen di dev.

21. **Fibonacci retracement di prompt** (sudah di main `744ad0a`): `prepare_prompt` hitung Swing High/Low dari 50 candle + Fib 38.2/50/61.8 → di-inject ke "CURRENT INDICATORS & FIBONACCI SUMMARY". Tujuannya: bot bisa lihat potensi SELL koreksi di tren bullish (target Fib) tanpa panik — LLM tidak lagi buta soal level retracement.
21b. **Key levels + candle M5 25 / M1 10** (11 Agustus): `prepare_prompt` inject **KEY LEVELS** (PDH/PDL dari D1, Today Open, nearest round number, active WIB session) — di-cache 5 menit (D1 berubah sekali sehari), 1 query D1 murah. Candle M5 naik dari 7 → **25** (cukup baca pola swing tanpa boros token), M1 5 → **10** (konfirmasi entry). Sumber: saran Claude soal top-down MTF (H4/H1/M15 tetap diringkas jadi teks bias di macro_analyst — bukan candle mentah).
21c. **Candle M15 25 → 50 (OHLC-only) + MTF XAU tambah M30/H1**: sebelumnya prompt kirim 25 candle M15 tapi klaim "50-Bar Swing High/Low" → LLM gak bisa verifikasi swing. Sekarang kirim **50 candle OHLC-only** (volume dibuang, window penuh sama dengan swing/Fib) + header "RECENT CANDLES (Last 50 candles, OHLC only — full swing window)". Plus `HIGHER_TIMEFRAMES` XAU disesuaikan ke M30/H1 (sesuai spesifikasi MTF swing pendek). Token naik ~1.1k chars per prompt, sepadan dengan konteks struktur yang bisa diverifikasi.
22. **Prompt template baru `docs/prompt_claude.md`** (hanya di `dev`, commit `ab42c17`): ganti static block kaku (STRATEGY/DECISION ORDER/counter-trend rules) dengan:
    - **ANALYSIS FREEDOM**: LLM bebas pilih interpretasi (trend/momentum/breakout/pullback/mean-reversion/reversal/exhaustion) — tidak dipaksa ke satu template strategi. Indikator (RSI/EMA/Fib/ATR/forecast) adalah **input untuk judgment, bukan trigger/block wajib**.
    - **DATA INTEGRITY**: jangan invent indikator yang tidak diberikan; MTF analysis = dihitung dari candle HTF asli (EMA/RSI/ATR/swing) → faktual, pakai untuk struktur besar (pullback vs reversal); news/fundamental = advisory only (kalau generik/stale → abaikan); forecast = informational only (NEUTRAL ≠ wajib HOLD); recent outcomes = win/loss history, bukan sinyal arah.
    - **RISK CONSTRAINTS** (satu-satunya yang non-negotiable): thesis konkret + invalidation jelas, SL beyond invalidation & ≥ SL_MULT× ATR & ≥ 2× spread, TP ≥ 2× SL (R:R 2:1, TP = TP_MULT× ATR; multiplier per AI mode: single 1.25/2.5, dual 1.5/3.0, triple 1.75/3.5), spread tidak makan SL.
    - **Output schema baru**: `setup` (label bebas), `edge` (1-2 kalimat), `invalidation` (1 kalimat) + `sl_points`/`tp_points`/`reasoning`. Field baru opsional — HOLD tetap valid, consensus tetap jalan.
    - `build_system_prompt(symbol, timeframe, asset_desc)` = statis per bot (cache-friendly, ≥1024 token); `prepare_prompt` gabung statis + dinamis.
23. **Anti-anchor: `summarize_recent_outcomes`** (di `dev`): ganti inject narasi decision history dengan ringkasan outcome-only ("3 trade taken, 2 hit SL, 3 HOLD"). Sebelumnya decision_memory_str inject keputusan lama lengkap → LLM ke-anchor ke bias bullish basi berjam-jam. Sekarang cuma win/loss counts.
24. **Macro & forecast framing** (di `dev`): macro_str → MTF analysis di-framing **faktual** ("COMPUTED from actual higher-timeframe candles — pullback vs reversal"), news/fundamental → "advisory only — disregard if generic or stale"; forecast_str → "informational only — NEUTRAL tidak wajib HOLD, aligned tidak otomatis trade". (Update 11 Agustus: sebelumnya MTF ikut di-frame "advisory/background only" → LLM cenderung buang konteks HTF yang faktual; sekarang dipisah tegas.)
25. **Strip emoji dari prompt LLM** (di `dev`, commit `06159f6`): `_EMOJI_PATTERN` + `_strip_emoji()` diterapkan ke prompt final sebelum dikirim. **Requirement user: prompt LLM HARUS bebas emoji** (UI/CLI/log boleh pakai emoji). Sumber emoji bisa dari macro/forecast/lessons/calendar — strip di prompt final menangani semua.
26. **Unicode safety**: `≈` diganti `approx` di prompt (UnicodeEncodeError saat print di console cp1252 Windows).
27. **`scratch/prompt_preview_test.py`**: test file untuk preview prompt LLM dengan data MT5 asli (XAUUSD-ECNc — bukan XAUUSD, broker pakai suffix `-ECNc`). Pakai `config.get_timeframe()`; fallback ke `XAUUSD` kalau simbol utama gagal.
28. **`config.TP_SL_RULES` — 2 mode SL/TP** (default `"LLM"` sejak 13 Agustus, configurable via config):
    - **ATR-Based** (safe): **GATE layak/tidak** — proposal SL/TP AI dipakai apa adanya (setelah outlier filter), tapi trade **DITOLAK otomatis** kalau SL < max(2× spread, SL_MULT× ATR) atau TP < max(2× spread, TP_MULT× ATR). Bukan dinaikkan: memaksa SL/TP lebih jauh dari invalidation model = mengubah setup tanpa persetujuan. **Multiplier dinamis per AI mode: single 1.25×/2.5×, dual 1.5×/3.0×, triple 1.75×/3.5×** (R:R 2:1 selalu). **Prompt di-enhance** (blok HARD GATE + `atr_gate_str` dinamis di market data dengan angka minimum konkret per mode) biar AI gak usul SL/TP di bawah requirement (yang ujung-ujungnya ditolak gate).
    - **LLM** (bebas): SL/TP sesuai thesis model. Batasan minimal murni didasarkan pada **Safety Floor** `max(2x spread, 0.5x default_sl_points)` untuk menghindari stops yang terlalu sempit yang membengkakkan lot resiko. Model mengajukan Stop Loss dan Target menggunakan tingkat harga mutlak (`invalidation_price` & `target_price`). Jarak poin dihitung dinamis saat eksekusi di main.py, dan SL dipasang presisi di MT5 sesuai harga mutlak tersebut.
    - **Agregasi SL/TP**: nilai harga desimal dari model yang sepakat di-average; outlier dibuang dengan `_drop_standalone_outlier`.
    - **Cara ganti mode**: `config.TP_SL_RULES`, menu setup interaktif, atau flag CLI `--tpsl-rules {ATR-Based|LLM|atr|llm}`.
29. **Dynamic Timezone Alignment**: `get_broker_offset_seconds` menghitung selisih jam server broker (GMT+3) dengan UTC secara dinamis. Jarak pencarian deals dan timestamp di-shift proporsional agar batas harian `get_closed_positions_today` cocok 100% dengan kalender WIB-midnight dan mencegah trade "jatuh di masa depan" atau lolos ke hari sebelumnya.
30. **Default SL/TP per-symbol + multiplier ATR per AI mode** (11-12 Agustus):
    - `default_sl_points_for()`/`default_tp_points_for()` per-symbol: **XAU 400/800** (dinaikkan dari 300/600 karena ATR M15 XAU ~1180 pts → gate butuh SL ≥ 1.25×ATR ~1475; default 300 malah gagal lolos gate sendiri), **FX flat 100/200** (10/20 pips EURJPY scale), BTC 50000/100000.
    - **Multiplier gate ATR per AI mode** (`config.atr_sl_multiplier()`/`atr_tp_multiplier()`, sinkron di consensus + prompt): single 1.25×/2.5×, dual 1.5×/3.0×, triple 1.75×/3.5× — **R:R 2:1 selalu** (TP = 2× SL). Makin banyak model setuju, makin lebar SL/TP. `atr_gate_str` di market data inject angka minimum konkret per mode.
    - **Prompt unit explanation dinamis per-symbol** (`_build_points_explanation`): konversi point→pip dihitung dari `point_size` aktual (XAU 0.01, EURJPY 0.001, GBPCHF 0.00001).
31. **GPT/gemini/deepseek comment mapping** (11 Agustus): order comment dibangun dari `agreeing_models` → `"GPT"`, `"GPT+DeepSeek"`, `"GPT+Gemini+DeepSeek"` dst (bukan "Multi-LLM Bot").
32. **Outcome tracking di decision memory** (11 Agustus): `record()` simpan `result="OPEN"` kalau order sukses; pas posisi close, `update_result()` set hasil (TP/SL/SL-BEP/SL-trailing/manual) + **profit NET** (sudah termasuk komisi, dari `deal.profit+swap+net_comm`). `summarize_recent_outcomes` sekarang klasifikasi win/loss dari **profit** (BEP tolerance dinamis `config.bep_tolerance_for`), bukan label aja — count AKURAT di prompt ("3 trade(s) taken (2 win, 1 loss, 1 BEP), 1 still open, 2 HOLD"). Tetap **anti-anchor**: cuma count, TIDAK kirim harga entry/alasan lama ke AI.
33. **Structure-Based Dynamic SL/TP Routing (12 Agustus)**: Model LLM tidak lagi mengembalikan poin jarak statis, melainkan tingkat harga mutlak `invalidation_price` dan `target_price`. Bot menghitung `sl_points` secara dinamis saat eksekusi berdasarkan harga Ask/Bid aktual. SL ditempatkan secara presisi pada harga mutlak tersebut di MT5, meniadakan slippage/latency gap, dan lot size dihitung berdasarkan jarak SL aktual. Jika di bawah Safety Floor (`250 pts` untuk Gold), SL dinaikkan ke floor secara deterministik dan TP disesuaikan untuk menjaga R:R.

### Perubahan FASE 1-7 (12 Agustus — H1 rotation, Prompt Sync & Dynamic Micro Candles)

1. **FASE 1 — Ekspansi rotasi 7 simbol + FX pindah H1**: pool dari 3 → 7 simbol (1 XAUUSD + 6 FX cross non-USD: GBPCHF, EURCHF, GBPNZD, EURJPY, GBPUSD, EURAUD). FX ditetapkan ke **H1 swing, risk 1.0%** (XAU tetap M5 scalping risk 0.5%, BTC M30 risk 1.5%). MTF window proporsional di `macro_analyst.py` (M15=48 bar/12 jam, M30=72 bar/36 jam, H4/D1=30 bar) supaya Previous Daily High/Low terdeteksi tanpa EMA50 kekurangan data. Default SL/TP FX jadi flat 100/200.
2. **FASE 2 — ATR SL Guidance**: hapus instruksi hardcode "SL wajar 50-150 poin" di System Prompt (menyesatkan untuk pair beringas seperti GBPNZD) → AI WAJIB baca batas **ATR HARD GATE** di baris dinamis Market Data sebelum usul SL/TP. Hasil: tidak ada lagi proposal yang ditolak mesin validator `consensus.py` (anti pemborosan token).
3. **FASE 3 — Fix terminal wrap**: status line gabungan multi-symbol kepanjangan → wrap di Windows Terminal → `\r` mati (print numpuk ke bawah). Fix: truncation dinamis < lebar terminal **aktual** (`shutil.get_terminal_size`, emoji dihitung 2 kolom via `_disp_width`/`_truncate_disp`) + enable ANSI VT (`_enable_windows_vt`) + tulis `\x1b[2K` (hapus isi baris) sebelum status. **Status line dipendekin**: `🕒 [XAUUSD-ECNc | 08:50:26] | EURJPY-ECNc: 1 pos $-0.22 | ...` (tanpa "Waiting for next tick / M5 candle..." — semua orang tau dia waiting).
4. **FASE 4 — Multi-symbol macro cache**: bug lama — cache analisis HTF (H4/D1) di-reset tiap simbol bergeser dalam loop 3 detik → bot download ulang puluhan candle untuk 7 pair terus-terusan. Dirombak jadi **berlaci per-simbol** (`self.cache[symbol]`): sekali tarik H4/D1 di startup, tidak ada koneksi ulang ke MT5 untuk pair itu sampai candle-nya habis (hemat download ~99%).
5. **FASE 5 — Smart Timeframe Rotation**: sebelumnya LLM dipanggil untuk pair H1 (EURJPY dst) tiap 5 menit (ikut candle M5 XAU) — boros kuota API. `_symbol_last_candle` dict di main.py mengunci pemanggilan AI **per-timeframe aset**: FX H1 cuma memicu LLM call 1 jam sekali (tepat pas pergantian candle H1), XAU tetap tiap 5 menit, BTC tiap 30 menit. Hemat LLM call ~90% untuk pair FX.
6. **FASE 6 — Prompt Sync LLM Mode**: jika `TP_SL_RULES` disetel ke `"LLM"`, bot menyembunyikan baris `ATR HARD GATE` dari data pasar dan menghapus petunjuk *"respect ATR HARD GATE"* di system prompt. Ini menyelaraskan prompt agar AI secara psikologis bebas mengajukan Stop Loss tipis sesuai analisis teknisnya tanpa merasa dibatasi aturan ATR.
7. **FASE 7 — Dynamic Micro Candles**: timeframe & jumlah candle mikro intra-period yang dikirim ke LLM disesuaikan dinamis agar tidak ada *blind spot* pada candle berjalan: Gold M5 main -> 15 M1 candles (15m), BTC M30 main -> 12 M5 candles (60m / 1h), FX H1 main -> 24 M5 candles (120m / 2h). 24 candle M5 untuk H1 mencakup seluruh pergerakan candle berjalan saat ini dan candle sebelumnya secara penuh.

### Perubahan 13 Agustus — TP_SL_RULES default LLM + Position Management SL-based (bug fix trailing)

**Latar belakang bug (ditemukan dari analisis log):** di mode LLM, BEP/trailing sebelumnya pakai aturan `% TP` (BEP 50% TP, activation 60% TP) + distance **ATR-based**. Masalahnya:
- TP LLM bisa jauh/asimetris (bahkan < SL) → 50%/60% TP jarang kesampean → BEP & trailing nyaris gak pernah aktif (log: trailing XAU cuma jalan lewat fallback posisi tanpa TP)
- Distance ATR (1.2×ATR ≈ 1416 pts XAU) gak nyambung sama struktur SL LLM (400–2000 pts) → longgar total, nol proteksi
- BTC: distance `0.5×ATR` ≈ $20–40 **jauh di bawah stop_level broker** (~$100–200) → semua modifikasi SL ditolak MT5 `Invalid stops` → 300+ error storm di log (tiket 1160983088 dkk), BTC **tidak pernah dapat trailing protection**

**Perubahan (mode LLM = position management pindah ke basis SL posisi, thesis-relative, ATR-free):**
1. **Default `TP_SL_RULES` diganti `"LLM"`** (sebelumnya `"ATR-Based"`). Mode ATR-Based tetap ada via `.env`/menu/`--tpsl-rules` — di mode itu BEP/trailing tetap ATR-based (konsisten karena SL/TP-nya juga turunan ATR).
2. **BEP trigger** (mode LLM): `min(1× SL original, 50% TP)` — `BREAK_EVEN_TRIGGER_SL_MULT = 1.0`. R:R 2:1 → 1×SL = 50% TP (sama dengan aturan lama); R:R tinggi → lebih awal (1×SL); R:R ≤ 1 → tetap 50% TP (fire, bukan 100%+ TP yang gak pernah kesampean). Bonus BTC: trigger sebesar SL otomatis > stop_level broker → modifikasi gak ditolak MT5.
3. **Trailing activation** (mode LLM): `max(1.5× SL, fallback_act)`, di-cap `60% TP` kalau TP ada (`TRAILING_ACTIVATION_SL_MULT = 1.5`). Untuk R:R 2:1 tetap setara 60% TP; R:R tinggi dapat proteksi lebih awal.
4. **Trailing distance** (mode LLM): SL-based progressive `0.8 → 0.3× SL` (floor `0.2`) — bukan ATR. Berlaku semua simbol (termasuk BTC, yang tadinya statis).
5. **Fix bug progress_ref**: `progress_ref = tp_points` (bukan `max(tp, 2× activation)` yang selalu 1.2×TP) → distance **beneran mencapai end_mult tepat di TP** (sebelumnya cuma 2/3 jalan).
6. **Referensi SL original**: state baru `original_sl_points` di `position_manager_state.json` — SL reference di-rekam saat posisi pertama kali terlihat (sebelum BE/trailing geser SL), biar `sl_points` gak mengecil ke padding setelah BE. State dict dibersihkan otomatis saat posisi close.
7. **Konstanta baru di config**: `BREAK_EVEN_TRIGGER_SL_MULT`, `TRAILING_ACTIVATION_SL_MULT`, `TRAILING_DISTANCE_START/END/MIN_SL_MULT` (env-configurable).

**Catatan**: fix `progress_ref` juga diterapkan di mode ATR-Based (bug yang sama). Clamp ke `trade_stops_level` broker (fix permanen error "Invalid stops") belum diimplementasikan — masih rekomendasi lanjutan.

### Perubahan 13 Agustus (lanjutan) — Split SL/TP mode per kategori: XAU/BTC fix ATR-Based, FX LLM

**Latar belakang:** mode LLM global bikin XAU jadi scalping — OpenAI sering kasih SL 83-400 pts padahal ATR M15 XAU ~819 pts (floor 400 cuma 0.49× ATR), dan OpenAI jadi over-restrictive (HOLD terus: "no clean 400+ point invalidation"). Gemini yang kasih setup valid (R:R 1.22-1.65) selalu diblokir konsensus karena OpenAI HOLD.

**Perubahan (arsitektur baru — logic & config dipisah per kategori biar enak debug):**
1. **`config.sltp_mode_for(symbol)`** — single source of truth mode SL/TP per simbol:
   - **XAUUSD & BTC → `"ATR-Based"` (fix, SELALU)** — gate ATR R:R 2:1, anti-scalping. Prompt XAU/BTC inject ATR HARD GATE lagi (`atr_gate_str` dengan angka minimum konkret per AI mode).
   - **FX pairs → `"LLM"`** — bebas struktur, Safety Floor `max(2x spread, 0.5x default_sl)`, gate R:R minimal 1:1.
   - **Force override**: `config.TP_SL_RULES == "ATR-Based"` (CLI `--tpsl-rules` / `.env`) → FX ikut ATR-Based juga. Default "LLM" = aturan per-kategori.
2. **`consensus.py`**: `_apply_sltp_rules` pakai `config.sltp_mode_for(config.SYMBOL)` (bukan global `TP_SL_RULES`).
3. **`llm_client.py`**: blok SL/TP rules & `atr_gate_str` resolve per-symbol via `sltp_mode_for(symbol)`.
4. **`position_manager.py`**: BEP/trailing mode di-resolve per-posisi (`sltp_mode_for(pos.symbol)`) — XAU/BTC pakai ATR-based, FX pakai SL-based (perubahan 13 Agustus sebelumnya).
5. **R:R minimum 1:1** (dari 1.25, commit `ffaf700`): berlaku di mode LLM (FX) + re-check eksekusi main.py. Prompt klarifikasi (commit `09981e4`): R:R 1:1 itu gate minimal yang diverifikasi bot, bukan alasan HOLD — model wajib kasih `invalidation_price`/`target_price` dari struktur teknis, bot yang hitung & verifikasi.
6. **Re-check gate saat eksekusi** (commit `16644ba`): main.py re-kalkulasi SL/TP dari harga absolut pakai tick fresh, lalu `_apply_sltp_rules` dipanggil lagi — kalau R:R < 1:1 / gagal gate → trade dibatalkan (`gate_blocked → slots 0`).

### Perubahan 13 Agustus (sore) — XAU pindah ke LLM mode + risk 1.0% + max lot 0.01 + GATE OVER-RISK

**Latar belakang:** gate ATR-Based untuk XAU (SL ≥ 1.25×ATR M15 ≈ 1024 pts) bikin SL lebar yang **TIDAK MUAT di min lot 0.01 broker** dengan risk 0.5% — risk aktual meledak 3.2× (0.0031 lot raw di-clamp naik ke 0.01 → risk $17.36 = 1.6%). Simulasi 5 iterasi full prompt live: OpenAI kasih SL 300 pts konsisten (R:R 5:1) kalau nggak di-gate ATR. Keputusan user: XAU ikut mode LLM (bebas struktur), risk dinaikkan ke 1.0% (max SL ~1079 pts di equity $1079 muat sweet spot). **14 Agustus: max lot cap 0.01 DIHAPUS** — lot murni risk-based, volume_max broker yang membatasi (gate OVER-RISK tetap jaga).

**Perubahan:**
1. **`config.sltp_mode_for(symbol)`**: XAU → `"LLM"` (bukan ATR-Based fix lagi; soft floor 400-1000 + gate over-risk). BTC tetap `"ATR-Based"` (fix). FX tetap `"LLM"`.
2. **`config.risk_percent_for()`**: XAU 0.5% → **1.0%** (docstring + DEFAULT_CONFIG v1/v2/v3 ikut).
3. ~~**`config.max_lot_for(symbol)`** (XAU → 0.01 cap keras)~~ — **DIHAPUS 14 Agustus** (user: "aturan max lot hapus aja"). Tidak ada cap per-kategori; `get_effective_lot_size` clamp ke volume_min/max broker saja.
4. **`consensus._apply_sltp_rules` — GATE OVER-RISK (baru, semua mode)**: setelah R:R 1:1 check, hitung `max_sl = (equity × risk_pct) / (volume_min × usd_per_pt_1lot)` — kalau SL resolved > max_sl → **trade DITOLAK** dengan reason "OVER-RISK: SL X pts > max Y pts (risk Z% gak muat di min lot)". Ini menangkap anomali kayak SL 1736 pts (OpenAI tulis sl_points 927 tapi invalidation_price 1736 pts jauh → resolved 1736) yang sebelumnya lolos diam-diam.
5. **`llm_client.py` prompt XAU LLM**: soft guidance (bukan gate): "SL ~400-1000 pts ideal, >1100 pts → risk > 1.0% budget, bot mungkin tolak; prefer structural level yang jaga SL di 400-1000".
6. **Banner/status**: "XAU: LLM (soft floor 400-1000) | BTC: ATR-Based (fix) | FX: LLM" (max lot cap dihapus 14 Agustus).

**Konsekuensi (update 14 Agustus):** dengan max lot cap dihapus, lot sizing XAU murni risk-based: lot = risk 1.0% / (SL pts × usd_per_point), di-clamp ke volume_step broker. SL 400 pts di equity $1079 → lot 0.013 → risk ~$10.8 (1.0%). Gate OVER-RISK tetap tolak kalau SL > budget min lot.

### Catatan akun & operasional
- LIVE `VTMarkets-Live 3` login `27556325`, balance ~$1065. Profit verifikasi = query MT5 langsung (`scratch/` script, hapus setelah dipakai).
- Git branch: **`dev` = branch utama** (prompt baru + FASE 1-5 multi-symbol H1), **`main` = prompt lama** (terakhir `744ad0a`). **Sengaja split — jangan merge dev → main tanpa konfirmasi user.** FASE 1-5 sudah di-commit di `40c7288` (sebelumnya `284ec76` = outcome tracking akurat + default per-symbol + multiplier ATR per AI mode).
- **Slot-3 DeepSeek V4 Flash** (default, configurable via menu/`--claude-model`); Gemini 3.1-flash-lite (primary) + 3.5-flash-lite (fallback); OpenAI gpt-5.2 (window 15:00-19:30 WIB) / o3-mini (default di luar window, 14 Agu) / gpt-4o-mini (fallback error); fallback slot-3 `claude-haiku-4-5-20251001`. Dynamic config ambang optimal **>65%** (bukan 70%). Threshold XAU 1.0 / BTC 1.2 (defensif 3/3 = ×1.5).
- **`data/` dan `scratch/` sudah di-`.gitignore`** (untrack via `git rm --cached`, file tetap ada di disk). `git status` sekarang bersih dari runtime state — cuma source file + `docs/` yang muncul.
- Lessons BTC pernah bikin bot HOLD terus (8 lesson "avoid 5-minute BTC scalps" dari era M5 yang gagal) — sudah di-clear. Kalau bot mulai HOLD terus lagi, cek `memory_lessons.json` dulu.
- **Status display live** menampilkan posisi terbuka semua symbol + floating P/L tiap 3 detik (`get_all_open_positions`). Status line pendek & refresh di tempat (FASE 3).

## Bot Binance Spot — BRANCH TERPISAH (`binance`)

> Bot kedua untuk **Binance spot** (BTC/ETH/SOL), modal kecil, deploy Linux. **TIDAK ada di branch `dev`/`main`** — kode lengkap ada di branch `binance` (`git checkout binance`). Arsitektur: 2 proposer + 1 approver, OCO SL/TP, dry-run realistis, HOLD-streak, risk 1.5%, trading 24/7. Detail lengkap ada di AGENTS.md branch binance.

## Estimasi Frekuensi & Biaya Call LLM Harian

Dengan **Smart Timeframe Rotation (FASE 5)**, LLM dipanggil per simbol hanya ketika lilin timeframe-nya ditutup (XAU M15 = 15 menit, BTC M30 = 30 menit, FX H1 = 60 menit). Biaya dihitung menggunakan asumsi ukuran input prompt ~3.5k tokens dan output ~150 tokens.

### 1. Estimasi Call per Hari (24 Jam)
* **Mode XAU Only (`TRADING_MODE = "xau"`)**: 96 siklus/hari.
  * OpenAI (`gpt-5.2` window / `gpt-4o-mini` luar window): **96 call/hari**
  * Gemini (`gemini-3.1-flash-lite`): **28 call/hari** (di sesi Dual & Triple)
  * DeepSeek (`deepseek-v4-flash`): **8 call/hari** (di sesi Triple)
  * **Total Call:** 132 call/hari.
* **Mode XAU + Pairs (`TRADING_MODE = "xau_pairs"`)**: 240 siklus/hari (96 XAU M15 + 6 FX H1).
  * OpenAI: **240 call/hari**
  * Gemini: **70 call/hari**
  * DeepSeek: **20 call/hari**
  * **Total Call:** 330 call/hari.
* **Mode BTC Only (Weekend/Rotasi)**: 48 siklus/hari.
  * OpenAI: **48 call/hari**, Gemini: **14 call/hari**, DeepSeek: **4 call/hari**.
  * **Total Call:** 66 call/hari.

### 2. Estimasi Biaya per Hari & Bulanan (USD & IDR)

Asumsi nilai tukar: **1 USD = Rp 15.500,-**

* **Asumsi Tarif Model Utama:**
  * OpenAI mini (`gpt-5.2` / `gpt-4o-mini`): **GRATIS $0.00** (Dalam batas free tier 2.5 juta token per hari). *[Jika berbayar: Input $0.15/1M, Output $0.60/1M => ~$0.0006 per call]*
  * Gemini Lite (`gemini-3.1-flash-lite`): Input $0.075/1M, Output $0.30/1M => **~$0.0003 per call**
  * DeepSeek (`deepseek-v4-flash` / V3): Input $0.14/1M, Output $0.28/1M => **~$0.0005 per call**
  * Claude Sonnet (`claude-3-5-sonnet`): Input $3.00/1M, Output $15.00/1M => **~$0.0128 per call**

#### OPSI A: Menggunakan DeepSeek di Slot 3 (DEFAULT - Sangat Hemat)
* **Mode XAU Only (`TRADING_MODE = "xau"`)**
  * Biaya Harian: OpenAI: $0.00 ($0.0576 jika berbayar) | Gemini: $0.0084 | DeepSeek: $0.0040
  * **Total Harian:** **~$0.0124 / hari (± Rp 190,-)** — *[Jika OpenAI berbayar: ~$0.0700 / hari (± Rp 1.100,-)]*
  * **Total Bulanan (30 Hari):** **~$0.37 / bulan (± Rp 5.700,-)** — *[Jika OpenAI berbayar: ~$2.10 / bulan (± Rp 32.500,-)]*
* **Mode XAU + Pairs (`TRADING_MODE = "xau_pairs"`)**
  * Biaya Harian: OpenAI: $0.00 ($0.1440 jika berbayar) | Gemini: $0.0210 | DeepSeek: $0.0100
  * **Total Harian:** **~$0.0310 / hari (± Rp 480,-)** — *[Jika OpenAI berbayar: ~$0.1750 / hari (± Rp 2.800,-)]*
  * **Total Bulanan (30 Hari):** **~$0.93 / bulan (± Rp 14.400,-)** — *[Jika OpenAI berbayar: ~$5.25 / bulan (± Rp 81.370,-)]*
* **Mode BTC Only (Weekend/Rotasi)**
  * Biaya Harian: OpenAI: $0.00 ($0.0288 jika berbayar) | Gemini: $0.0042 | DeepSeek: $0.0020
  * **Total Harian:** **~$0.0062 / hari (± Rp 96,-)** — *[Jika OpenAI berbayar: ~$0.0350 / hari (± Rp 550,-)]*
  * **Total Bulanan (30 Hari):** **~$0.19 / bulan (± Rp 2.900,-)** — *[Jika OpenAI berbayar: ~$1.05 / bulan (± Rp 16.275,-)]*

#### OPSI B: Menggunakan Claude Sonnet 3.5 di Slot 3 (Analisis Lebih Tajam tapi Premium)
* **Mode XAU Only (`TRADING_MODE = "xau"`)**
  * Biaya Harian: OpenAI: $0.00 ($0.0576 jika berbayar) | Gemini: $0.0084 | Claude Sonnet (8 call): $0.1024
  * **Total Harian:** **~$0.1108 / hari (± Rp 1.710,-)** — *[Jika OpenAI berbayar: ~$0.1684 / hari (± Rp 2.610,-)]*
  * **Total Bulanan (30 Hari):** **~$3.32 / bulan (± Rp 51.500,-)** — *[Jika OpenAI berbayar: ~$5.05 / bulan (± Rp 78.300,-)]*
* **Mode XAU + Pairs (`TRADING_MODE = "xau_pairs"`)**
  * Biaya Harian: OpenAI: $0.00 ($0.1440 jika berbayar) | Gemini: $0.0210 | Claude Sonnet (20 call): $0.2560
  * **Total Harian:** **~$0.2770 / hari (± Rp 4.290,-)** — *[Jika OpenAI berbayar: ~$0.4210 / hari (± Rp 6.520,-)]*
  * **Total Bulanan (30 Hari):** **~$8.31 / bulan (± Rp 128.800,-)** — *[Jika OpenAI berbayar: ~$12.63 / bulan (± Rp 195.700,-)]*
* **Mode BTC Only (Weekend/Rotasi)**
  * Biaya Harian: OpenAI: $0.00 ($0.0288 jika berbayar) | Gemini: $0.0042 | Claude Sonnet (4 call): $0.0512
  * **Total Harian:** **~$0.0554 / hari (± Rp 860,-)** — *[Jika OpenAI berbayar: ~$0.0842 / hari (± Rp 1.300,-)]*
  * **Total Bulanan (30 Hari):** **~$1.66 / bulan (± Rp 25.700,-)** — *[Jika OpenAI berbayar: ~$2.52 / bulan (± Rp 39.000,-)]*

## Konvensi & hal yang perlu diingat

- User komunikasi dalam **Bahasa Indonesia** (santai).
- **Risk-averse**: risk per trade terkontrol (BTC 1.5% / XAU 1.0% / FX 1.0% equity), jangan longgarkan daily loss. Kalau mau eksperimen agresif → demo dulu, bukan live.
- Perubahan prompt = diskusi dulu sebelum apply (user minta bahas dulu).
- User suka angka dari sumber kebenaran: profit = query MT5 langsung, bukan log campuran.
- Kalau bikin skrip analisis sementara → taruh di `scratch/`, lalu HAPUS setelah dipakai (user minta dibersihin).
- User minta commit + push ke `dev` setelah kerjaan verified (tapi tanya dulu / tunggu permintaan eksplisit).
- Magic number bot: `20260625`. Bot cuma kelola posisi dengan magic ini.
- LLM timeout 24s, fallback berurutan (OpenAI → Gemini → slot-3 untuk primary).
- **Slot-3 (default DeepSeek, historis Claude) = model paling analitis** (detail R:R, struktur, level). **OpenAI = konservatif tapi solid**. **Gemini = variatif, kadang confident tinggi**. HOLD conf 0 = netral di weighted voting.
