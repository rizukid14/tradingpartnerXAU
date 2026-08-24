# Multi-LLM Consensus Trading Bot (MT5 + Python)

Bot trading berbasis AI yang mengintegrasikan data pasar dari **MetaTrader 5 (MT5)** dengan tiga slot model LLM via API: **OpenAI**, **Google Gemini**, dan **slot ketiga (default DeepSeek V4 Flash, bisa di-switch ke Claude)**.

- **Weekday**: `XAUUSD-ECNc` (Gold) — intraday **M30** — **Weekend**: `BTCUSD.c` (Bitcoin) — intraday **M30** (rotasi otomatis via `config.get_active_symbol`)
- **Multi-scan (opsional, mode `xau_pairs`)**: bot melakukan scan **7 simbol dalam pool sekaligus**: XAUUSD M30 (intraday swing) + 6 FX cross non-USD H1 (swing).
- **Smart Timeframe Rotation**: LLM call hanya dipicu ketika candle timeframe spesifik aset tersebut berganti (XAU tiap 30 menit, FX tiap 1 jam, BTC tiap 30 menit). Menghemat ~90% biaya API LLM!
- Bot memanggil AI sesuai **time-based mode** (single/dual/triple — lihat jadwal WIB), menghitung **weighted-confidence consensus**, lalu mengeksekusi order ke MT5.
- Akun: **LIVE** `VTMarkets-Live 3` (login `27556325`), magic number `20260625`.
- Semua timestamp internal pakai **WIB** (Asia/Jakarta).

## 🎯 Multi-Symbol Scan (Mode `xau_pairs`)

Default bot cuma trading **XAU** (`TRADING_MODE=xau`). Ada mode kedua: **FX Pairs Pool** (`TRADING_MODE=xau_pairs`) — di mode ini bot memantau **8 simbol FX Cross & Major** secara paralel dengan timeframe H1 expert intraday-swing:

| # | Simbol (base) | Live Suffix | Timeframe | Risk % | Gaya Trading |
|---|---|---|---|---|---|
| 1 | `GBPUSD` | `GBPUSD-ECNc` | H1 | 1.25% | Expert Intraday-Swing |
| 2 | `GBPAUD` | `GBPAUD-ECNc` | H1 | 1.25% | Expert Intraday-Swing |
| 3 | `AUDCAD` | `AUDCAD-ECNc` | H1 | 1.25% | Expert Intraday-Swing |
| 4 | `EURCHF` | `EURCHF-ECNc` | H1 | 1.25% | Expert Intraday-Swing |
| 5 | `AUDCHF` | `AUDCHF-ECNc` | H1 | 1.25% | Expert Intraday-Swing |
| 6 | `CADCHF` | `CADCHF-ECNc` | H1 | 1.25% | Expert Intraday-Swing |

**Kenapa 6 pair ini?** Kombinasi Major (GBPUSD) dan FX Cross CHF/AUD pilihan dengan edge statistik kuat (24–37 EDGE per pair vs EURJPY hanya 2 EDGE). Suffix `-ECN`/`-ECNc` di-auto-correct otomatis oleh `get_valid_trade_symbol` sesuai akun (live vs demo).

**Cara kerja per cycle:**
1. Pool di-resolve via `config.get_rotation_pool()` → `[XAU] + FX_PAIR_SYMBOLS`, dipotong `MAX_ROTATION_SYMBOLS` (default 7)
2. Post-mortem trade tertutup dijalankan **1× aggregate** (bukan per-simbol)
3. Loop `for sym in pool:` → `config.SYMBOL = sym` → Cek apakah candle timeframe asli simbol tersebut sudah berganti (`_symbol_last_candle`).
4. Jika candle baru terbentuk: jalankan cycle penuh per-simbol (risk gate → data MT5 → macro/MTF per-simbol → LLM call → weighted consensus → eksekusi). Jika belum berganti, skip LLM call untuk menghemat token.
5. **Weekend**: XAU + FX market tutup Sabtu–Minggu → **bot istirahat (mode 24/5)**. Pool jatuh ke `[XAUUSD-ECN]` yang tutup (risk gate menolak semua, tidak ada LLM call). Opsional: set `ENABLE_BTC_ROTATION=True` → weekend ganti ke `[BTCUSD.c]` M30 (24/7).

**Risk tetap aggregate**: max posisi (6) & daily loss ($50) dihitung **lintas semua simbol** (magic filter `20260625`), bukan per-simbol. Ganti mode: `.env` (`TRADING_MODE=...`), menu setup (item "Scan Mode"), atau dropdown dashboard (persist ke `.env`).

---

## 🤖 Bot Binance Spot (Branch `binance`)

Bot **kedua** untuk trading **Binance spot** (BTC/ETH/SOL) — **tidak ada di branch `dev`/`main`**. Kode-nya dipisah ke branch `binance` (arch: 2 proposer + 1 approver, OCO SL/TP, dry-run realistis, risk 1.5%, trading 24/7).

```bash
git checkout binance   # branch ini berisi binance_bot/ lengkap
```


---

## 🏗️ Arsitektur Sistem (Branch `dev`)

```mermaid
graph TD
    A["Trading Cycle (M15 XAU / M30 BTC)"] --> B{"Risk Gate (spread/session/daily-loss)"}
    B -- Fail --> Z["Skip cycle (no LLM cost)"]
    B -- Pass --> C["Multi-LLM Parallel Query (3 models)"]
    C --> D{"Weighted Consensus? (skor confidence > threshold)"}
    D -- No --> Z2["HOLD (next cycle)"]
    D -- Yes --> E["Execute Trade (MT5) — risk-based lot sizing"]
    E --> F["Trade Close Detected"]
    F --> G["Post-Mortem Lessons"]
    G --> H["memory_lessons.json"]
    G --> I["dynamic_rules.json (self-tuning)"]
    H --> J["Inject Lessons into Future Prompts"]
```

### 🧠 Fitur AI Aktif
1. **Weighted-Confidence Consensus (per-symbol)**: Tiga slot model (OpenAI, Gemini, slot-3: DeepSeek/Claude) dipanggil paralel tiap candle. Skor arah (BUY/SELL) = Σ confidence model yang vote arah itu. Sinyal menang kalau **≥ 2 model searah** DAN skor > threshold per-symbol (`confidence_threshold_for()`: **XAU 1.0**, **BTC 1.2**; saat defensif 3/3 = ×1.5). Model @51% tidak lagi setara @90%.
2. **Post-Mortem Trade Evaluator & In-Context Memory (per-symbol + theme-tagged)**: Tiap trade tertutup dievaluasi → 1 aturan ringkas masuk `memory_lessons.json` dengan tag tema (`entry`/`risk`/`timing`/`psychology`). Saat cap 15 tercapai, semua lessons di-summary jadi 1 blok via gpt-5.4-mini — dikelompokkan per-theme. Prompt berikutnya inject summary itu saja.
3. **Adaptive Dynamic Config (wired to consensus)**: Win-rate < 40% → konsensus diketat (3/3 defensif, threshold confidence ×1.5); win-rate > 65% → kembali normal 2/3. **Break-even trades excluded** dari win-rate.
4. **Recent Decision Memory (per-symbol)**: 6 keputusan terakhir per symbol. Inject ke prompt agar LLM sadar kalau sudah HOLD beruntun dan bisa self-correct.
5. **Calendar Dinamis TradingView API (6h TTL) + Per-Pair News Filter (20 Agustus)**: Event ekonomi high-impact di-fetch otomatis dari TradingView API (`https://economic-calendar.tradingview.com/events`) dengan TTL cache 6 jam (`data/economic_events_cache.json`). Event **GLOBAL** (FOMC/NFP/Powell/Trump speech/Fed Chair) di-inject ke **SEMUA simbol**; event negara lain (ECB/BoJ/RBA/SNB/CPI GB/Unemployment US) **hanya disuntikkan ke pair yang mengandung mata uangnya**. Di-inject ke prompt sebagai `NEWS WINDOW GUARD` hanya jika ada event dalam window **6 jam sebelum/sesudah** jam eksekusi candle saat ini.
6. **Forecast Multi-Horizon per-symbol (background-pre-warmed)**: Proyeksi harga + invalidation level + optimal entry zone. **XAU: T+15m/T+60m** (cache 15 menit), **BTC: T+4h/T+D1** (cache 1 jam). Refresh di background thread (non-blocking). Bersifat **informational** — tidak memblokir eksekusi.
7. **Sistem Dynamic Micro Candles (Intra-Period Detail)**: Penyerahan data candle mikro disesuaikan dinamis berdasarkan timeframe utama untuk menghilangkan *blind spot* (Gold M15 -> 12 M5 candles (1h), BTC M30 -> 12 M5 candles (1h), FX H1 -> 24 M5 candles (2h)). Ini membantu AI melihat internal *swing* dan *pullback* tanpa *overreacting* berlebih.
8. **AI Position Re-Evaluator (close via consensus)**: Tiap cycle, model diminta keputusan per posisi terbuka (`CLOSE`/`HOLD`). Kalau ≥ 2/3 sepakat CLOSE → bot eksekusi close dengan profit real (bukan 0.0), supaya daily P/L + loss streak akurat. **`signal` (entry baru) dan `position_actions` (posisi existing) dinilai independen** di prompt.
9. **Per-Symbol Daily Breakdown**: Agregat + breakdown per-symbol (`XAUUSD-ECNc` vs `BTCUSD.c`) — BEP dipisah eksplisit dari loss.
10. **Order Retry & Fill-Policy Fallback**: `send_trade_order` & `close_position` retry sampai 2× pada retcode PRICE_OFF/PRICE_CHANGED/REQUOTE/REJECT (deviation melebar), fallback ke fill mode yang didukung broker (`get_filling_policy`).
11. **Position Manager State Persistence + Multi-Symbol + Tick Freshness**: `_partial_closed_tickets` & `_break_even_tickets` di-persist ke `data/position_manager_state.json`. Manage semua posisi bot (XAU + BTC), skip symbol yang market-nya tutup (tick stale — XAU weekend).
12. **Risk-Based Lot Sizing**: Lot dihitung dari equity & SL — **BTC 1.5%**, **XAU 1.0%** per trade (`RISK_PERCENT_BTC/XAU`; XAU naik dari 0.5% di 13 Agustus karena min lot 0.01 gak bisa mewakili risk 0.5% dengan SL struktur lebar). Urutan: risk-based → recovery (×0.5) / session (×1.2) multiplier → clamp+round ke `volume_step`. Margin safety net (lot diturunkan kalau margin > 50% free). Fallback 0.01 kalau SL tidak diketahui.
13. **Model Slot Configurable + Routing Otomatis**: Slot ke-3 default **DeepSeek V4 Flash** (`deepseek/deepseek-v4-flash` — jauh lebih murah dari Claude sonnet, cukup untuk decision & forecast JSON) dengan fallback `claude-haiku-4-5-20251001`. Routing otomatis di `query_claude()`: `deepseek/...` → DeepSeek API (OpenAI-compatible), `claude-...` → Anthropic. Ganti model via **menu setup** (item "Model Claude Slot") atau **CLI flag** `--claude-model`. Log label otomatis ("DeepSeek" vs "Claude").
14. **Deteksi Close Manual (magic=0)**: `get_closed_positions_today` menerima OUT deal dengan `magic=0` (manual close dari MT5 mobile — magic tidak diteruskan) **hanya jika posisinya dibuka bot** (ada IN magic bot). Posisi yang dibuka manual user tidak ikut kehitung. Window P/L pakai tengah malam WIB → next-midnight (loss hari kemarin tidak masuk "hari ini"). **Reason close di-label jelas** ("manual" untuk magic=0, "SL"/"TP"/"stop-out" dst. dari kode MT5) — bukan "unknown".
15. **Post-Mortem Langsung saat Close**: Post-mortem + lesson dipicu **saat itu juga** saat close di-detect (loop 5 detik, background thread) — bukan nunggu candle berikutnya. `evaluated_tickets` persist di `memory_lessons.json` mencegah re-evaluasi tiket lama saat restart.
16. **Trailing Stop & Break-Even Mode-Aware (13 Agustus)**: **mode LLM (default)** = SL-based thesis-relative (BEP aktif di `min(1×SL, 50% TP)`, trailing aktif di `max(1.5×SL, fallback)` cap 60% TP, distance `0.8→0.3×SL`) — fix trailing yang tadinya jarang aktif karena % TP jauh + distance ATR gak nyambung struktur LLM. **mode ATR-Based** = activation `min(1.0×ATR, cap)` (XAU 500 pts / BTC 40000 pts), distance `0.5×ATR`. SL di-trail dari **harga ekstrem** sejak entry (tracked per-ticket di state file) — pullback tidak bisa narik SL mundur. Partial close di-`skip` di lot 0.01 (50% dari 0.01 = 0, gabisa dipecah).
17. **Fibonacci Retracement di Prompt**: `prepare_prompt` menghitung Swing High/Low dari 50 candle terakhir + level Fib 38.2%/50.0%/61.8% → di-inject ke blok "CURRENT INDICATORS & FIBONACCI SUMMARY". Bot bisa membaca potensi SELL koreksi / pullback di tren bullish dengan target Fib — tidak lagi buta soal level retracement.
18. **Prompt Template "ANALYSIS FREEDOM" & Top-Down Layout (20 Agustus Update)**: prompt dirapikan sesuai *Top-Down Attention Flow* (`Macro Context` → `Active Timeframe Indicators H1` → `Intraday Structure 50-bar` → `Macro Structure 100-bar` → `Price Action`). Dilengkapi **CRITICAL TREND FILTER** (anti-fade tren tajam) & **ADX(14) Trend-Strength Label**.
19. **Anti-Anchoring: Outcome-Only Decision History (branch `dev`)**: keputusan lama tidak lagi di-inject sebagai narasi arah — diganti ringkasan win/loss saja ("3 trade taken, 2 hit SL, 3 HOLD"). Mencegah LLM ke-anchor ke bias bullish/bearish basi berjam-jam. Macro & forecast diberi label advisory/informational-only.
20. **Prompt LLM Bebas Emoji (branch `dev`)**: `_strip_emoji()` diterapkan ke prompt final — emoji dari sumber mana pun (macro/forecast/lessons/calendar) dihilangkan sebelum dikirim ke LLM. UI/CLI/log tetap boleh pakai emoji.
21. **Structure-Based Dynamic SL/TP Routing (12 Agustus)**: Model LLM tidak lagi mengembalikan poin jarak statis, melainkan tingkat harga mutlak `invalidation_price` dan `target_price`. Bot menghitung `sl_points` secara dinamis saat eksekusi berdasarkan harga Ask/Bid aktual. SL ditempatkan secara presisi pada harga mutlak tersebut di MT5, meniadakan slippage/latency gap, dan lot size dihitung berdasarkan jarak SL aktual. Jika di bawah Safety Floor (14 Agustus: `400 pts` XAU / `250 pts` FX), SL dinaikkan ke floor secara deterministik dan TP disesuaikan untuk menjaga R:R min 1.25.


### 🚫 Fitur Non-Aktif (Disabled)
- **Fundamental Search Grounding**: OFF (`FUNDAMENTAL_ANALYSIS_ENABLED=False`). Search grounding Gemini sering kasih konteks basi ("ahead of NFP" berjam-jam setelah rilis).
- **Multi-Agent Debate Protocol**: dihapus total (11 Agustus 2026). 53 debate historis tidak pernah mengubah keputusan jadi trade — murni buang token. Kode debate (`prepare_debate_prompt`, `DEBATE_ENABLED`) sudah dibersihkan, diganti **Time-Based AI Mode** (lihat fitur #21).

### ⏱️ Time-Based AI Mode (20 Agustus 2026 Update)
Single Mode telah **dihapus total** demi keamanan (setiap trade baru wajib disepakati minimal 2 model cerdas). Jumlah dan kombinasi model AI yang dipanggil per cycle mengikuti jam WIB:
- **00:00–18:59 WIB → DUAL** (`OpenAI o4-mini` + `Gemini 3.1-flash-lite`) — Sesi Asia & London (00:00-09:00 Dead Zone auto-skip).
- **19:00–22:00 WIB → TRIPLE** (`OpenAI o4-mini` + `Gemini 3.1-flash-lite` + `Claude 3.5 Haiku / DeepSeek v4-flash`) — London-NY overlap (puncak volatilitas harian, 4x call H1 pada jam 19, 20, 21, 22 WIB).
- **22:01–23:59 WIB → DUAL** (`OpenAI o4-mini` + `Gemini 3.1-flash-lite`) — Late NY session.

Config: `AI_MODE_POLICY` (schedule|fixed), `AI_MODE_SCHEDULE`, `AI_FIXED_MODE`. Konsensus adaptif: dual → 2/2 searah; triple → normal (defensif ×1.5).

---

## 📂 Struktur Proyek Modular (`src/`)

```text
tradingpartnerXAU/
├── main.py                  # Entry point utama loop trading
├── config.py                # Konfigurasi parameter, API keys, sesi, SL/TP, helper per-symbol
├── AGENTS.md                # Konteks proyek untuk sesi coding
├── .env / .env.example      # File environmental variables
├── README.md                # Dokumentasi proyek
├── requirements.txt         # Daftar dependency library Python
│
├── src/                     # Paket Modul Utama
│   ├── core/                # Mesin Utama & Konektivitas
│   │   ├── mt5_connector.py # Konektor API MetaTrader 5 (retry, fill policy, magic filter)
│   │   ├── llm_client.py    # Client API OpenAI, Gemini, DeepSeek/Claude (paralel, routing otomatis)
│   │   ├── consensus.py     # Weighted-Confidence Consensus + SL/TP floor (ATR/spread)
│   │   ├── risk_engine.py   # Master Risk Gate, Circuit Breaker & Limits (BEP tolerance)
│   │   └── telegram_alerts.py # Modul Notifikasi Telegram Bot
│   │
│   └── analytics/           # Fitur Analitis & AI Lanjutan
│       ├── forecast_engine.py       # Proyeksi Harga Multi-Horizon (XAU T+15m/T+60m, BTC T+4h/T+D1)
│       ├── trade_evaluator.py       # Post-Mortem Evaluator & Lessons Memory (theme-tagged)
│       ├── macro_analyst.py         # MTF context per-symbol (XAU M30/H1, BTC H4/D1)
│       ├── dynamic_config.py        # Penyesuai Parameter Risiko Dinamis (Self-Tuning)
│       ├── economic_calendar.py     # Calendar event high-impact (DST-aware, programmatic)
│       ├── decision_memory.py       # Recent Decision Memory per-symbol
│       └── position_manager.py      # Trailing Stop, Break-Even, Partial Close (state persisted)
│
├── data/                    # Cache JSON & State Lokal (runtime, jangan di-commit)
│   ├── analysis_cache.json          # Cache analisis struktur MTF
│   ├── forecast_cache.json          # Cache proyeksi harga Multi-Horizon
│   ├── memory_lessons.json          # Memori pembelajaran hasil Post-Mortem
│   ├── dynamic_rules.json           # Parameter aturan dinamis
│   ├── risk_state.json              # Rekam jejak state risiko & tiket historis
│   ├── decision_memory.json         # 6 keputusan terakhir per-symbol
│   └── position_manager_state.json  # Ticket yg sudah partial-closed / break-even
│
├── docs/                    # Dokumentasi & Tinjauan Kode
│   ├── recap_session_2026-08-08.md  # Rekap kerjaan sesi (untuk review AI lain)
│   ├── prompt_claude.md             # Template prompt "ANALYSIS FREEDOM" (hanya di branch dev)
│   ├── command_code_review.md
│   ├── gpt-mini-code-review.md
│   ├── opus_review.md
│   └── vps_deployment.md
│
├── logs/                    # Log dumps (di-ignore dari git)
├── scratch/                 # Skrip analisis sementara — hapus setelah dipakai
│
└── tests/                   # Script Pengujian API & Modul
    ├── test_apis.py             # Penguji keaktifan API Key
    ├── test_macro.py            # Penguji modul MacroAnalyst
    ├── test_symbol_rotation.py  # Penguji rotasi simbol weekday/weekend + helper
    └── test_telegram.py         # Penguji notifikasi Telegram
```

---

## 🛠️ Langkah-Langkah Instalasi & Penggunaan

### 1. Prasyarat (Prerequisites)
* **Sistem Operasi**: Windows (wajib karena library `MetaTrader5` hanya berjalan di Windows).
* **Python**: Versi 3.8 - 3.11 disarankan.
* **Aplikasi MT5**: Unduh dan instal terminal MetaTrader 5 dari broker Anda (misal: VT Markets) dan login ke akun.

### 2. Instalasi Library Python
Buka terminal/PowerShell di direktori proyek ini, lalu jalankan:
```bash
pip install -r requirements.txt
```

### 3. Konfigurasi API Key & Akun
1. Salin file `.env.example` menjadi `.env`:
   ```bash
   copy .env.example .env
   ```
2. Buka file `.env` dan masukkan API Key Anda untuk:
   * `OPENAI_API_KEY`
   * `GEMINI_API_KEY`
   * `ANTHROPIC_API_KEY` (dipakai kalau slot ke-3 di-switch ke Claude)
   * `DEEPSEEK_API_KEY` (dipakai untuk slot ke-3 default — DeepSeek V4 Flash)
3. (Opsional) Jika ingin bot otomatis login ke akun MT5 Anda, isi data `MT5_LOGIN`, `MT5_PASSWORD`, dan `MT5_SERVER`. Jika dikosongkan, bot akan otomatis menyambung ke terminal MT5 yang sedang aktif di PC Anda.

### 4. Uji Coba API Key & Modul
Jalankan script test untuk memastikan semua komponen aktif:
```bash
python tests/test_apis.py             # Cek API key OpenAI/Gemini/Claude
python tests/test_macro.py            # Cek modul MacroAnalyst
python tests/test_symbol_rotation.py  # Cek rotasi simbol weekday/weekend
python tests/test_telegram.py         # Cek notifikasi Telegram
```

### 5. Menjalankan Bot
Pastikan aplikasi MT5 Anda terbuka dan terhubung ke internet, lalu jalankan:
```bash
python main.py
```
- Saat start muncul **menu setup interaktif** — nomor 3 (`Scan Mode`) untuk ganti XAU Only / XAU + Pairs, preset `[v1]/[v2]/[v3]` untuk pakai preset cepat.
- Log: `trading_bot.log` (auto-rotate 2MB, keep 5000 baris). **Log bisa campur sesi demo + live** — untuk profit akurat, query MT5 langsung (`scratch/` script, hapus setelah dipakai).

> 📘 **Panduan lengkap semua setting** (env var, pair list, risk, SL/TP rules, contoh `.env`) ada di **`CONFIG_TUTORIAL.txt`** di folder root.

### 6. Dashboard Analisis (Opsional)
Menampilkan kualitas trade, kualitas sinyal LLM, dan statistik standar dari log. Dua mode:

**Mode static** (generate satu file HTML, buka di browser):
```bash
python dashboard.py          # generate dashboard.html
```

**Mode live** (server lokal, baca log fresh tiap request + auto-refresh 5 detik **tanpa reload halaman**):
```bash
python dashboard.py --serve --port 8765   # buka http://127.0.0.1:8765/
```

Dashboard read-only — tidak menyentuh bot/MT5. Opsi: `-o out.html` (output static lain), `--all-eras` (tampilkan semua era model, bukan hanya era aktif).

---

## ⚡ Mode Eksekusi

| Mode | Setting | Perilaku |
|---|---|---|
| **Dry-Run** | `config.DRY_RUN = True` | Sinyal AI dihitung, tapi TIDAK kirim order ke MT5. Aman untuk validasi. |
| **Live** | `config.DRY_RUN = False` | Order beneran dieksekusi ke MT5. Magic number `20260625` — bot hanya kelola posisi dengan magic ini. |

> ⚠️ Sangat disarankan mencoba di **Akun Demo** dulu sebelum live. Project ini saat ini berjalan di akun **LIVE** `VTMarkets-Live 3` (login `27556325`) — perubahan parameter live butuh diskusi dulu.

> ⚠️ **Branch split (11 Agustus)**: `main` = prompt lama (Fibonacci + counter-trend rules, commit `744ad0a`), `dev` = prompt baru (ANALYSIS FREEDOM + strip emoji, commit `06159f6`). Sengaja dipisah — jangan merge `dev` → `main` tanpa konfirmasi.

---

## 🛡️ Gate Eksekusi (Hard Gates)

Yang **sebenarnya** memblokir eksekusi, urut:
1. **Risk gate** (`risk.can_trade`): spread ≤ 50 pts (XAU) / 2400 pts (BTC), sesi London/NY WIB + **Dead Zone 02:00-06:00 WIB** (XAU & FX — crypto bebas 24/7), max daily loss $50, **max daily profit 6%** (stop trade sampai besok), max 5 consecutive loss, max 6 posisi (4 saat recovery).
2. **Weighted consensus** ≥ 2 model searah dengan skor confidence > threshold per-symbol (XAU 1.0 / BTC 1.2; defensif 3/3 = ×1.5).
3. **SL/TP mode per kategori (13-14 Agustus, `config.sltp_mode_for(symbol)`)**: **XAU = LLM** — SL/TP bebas struktur (`invalidation_price`/`target_price`), **Safety Floor 400 pts + R:R min 1.25:1** + soft guidance SL 400-1000 pts + **GATE OVER-RISK** (SL > max budget risk di min lot → ditolak). **BTC = fix ATR-Based** — SL ≥ max(2× spread, SL_MULT× ATR), TP ≥ max(2× spread, TP_MULT× ATR) (**R:R 2:1**, multiplier per AI mode: single 1.25×/2.5×, dual 1.5×/3.0×, triple 1.75×/3.5×) — anti-scalping. **FX pairs = LLM** — bebas struktur, **Safety Floor 250 pts (25 pips) + R:R min 1.25:1** (TP di-floor ke 1.25× SL, bukan tolak). Force semua ke ATR-Based via `.env` `TP_SL_RULES=ATR-Based`, menu setup, atau `--tpsl-rules {ATR-Based|LLM|atr|llm}`.
4. **Risk-based lot sizing (murni, tanpa cap per-kategori)**: lot = risk_usd / (SL pts × usd_per_point) (risk BTC 1.5% / XAU 1.0% / FX 1.0% equity), clamp ke volume_min/max/step broker + margin safety net. **Cap XAU 0.01 (`config.max_lot_for`) DIHAPUS 14 Agustus** — gate OVER-RISK di consensus tetap tolak kalau SL > budget risk di min lot.
5. **Max open positions** tercapai → skip.

Yang **TIDAK** memblokir (hanya soft hint di prompt / print):
- Confidence minimum numerik tambahan di luar weighted score
- Entry zone numerik (`optimal_entry_min/max` di-load tapi tidak dipakai)
- R:R forecast (cuma di-print informational)

---

## ⚠️ Disclaimer
Trading instrumen keuangan seperti Forex, Gold, dan Crypto memiliki tingkat risiko yang sangat tinggi. Bot ini adalah alat bantu berbasis AI — bukan saran finansial. Penggunaan bot untuk trading nyata sepenuhnya merupakan tanggung jawab pengguna. Selalu uji coba strategi Anda secara mendalam menggunakan akun demo sebelum mempertaruhkan modal nyata.
