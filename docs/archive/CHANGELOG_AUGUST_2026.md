# Arsip Changelog Historis Trading Bot (8–15 Agustus 2026)

> Dokumen ini mengarsipkan seluruh catatan perubahan historis arsitektur, bugfix, dan iterasi konfigurasi bot selama periode awal 8–15 Agustus 2026.

---

## 1. Perubahan Struktural 8 Agustus 2026

1. **BTC pindah ke M30** (dari M5): spread BTC ~$17 = 78% dari ATR M5 ($21), tapi kecil relatif ke ATR M30. `config.get_timeframe()` $\rightarrow$ BTC M30.
2. **MTF per-symbol**: XAU scan M15/M30, FX scan H4/D1, BTC scan H1/H4 (`config.get_higher_timeframes()`).
3. **Weighted confidence consensus**: skor arah = $\Sigma$ confidence; menang jika $\ge 2$ model searah DAN skor > threshold (XAU 1.0, BTC 1.2; defensif $\times 1.5$).
4. **Prompt dinamis per-symbol**: BTC "M30 Intraday Strategy", XAU "M5 Scalping Strategy".
5. **Money scale di prompt**: `usd_per_point`, spread USD, "NEVER set SL closer than 2x spread".
6. **SL/TP floor di consensus (mode-aware)**: ATR-Based $\rightarrow$ SL $\ge \max(2\times \text{spread}, \text{SL\_MULT}\times \text{ATR})$, TP $\ge \max(2\times \text{spread}, \text{TP\_MULT}\times \text{ATR})$ (**R:R 2:1**).
7. **`get_open_positions` filter magic** — bot tidak bisa menutup posisi manual milik user.
8. **Position manager multi-symbol + tick freshness**: kelola semua posisi bot, lewati jika pasar tutup.
9. **BEP tolerance $\pm 0.04$** (`BREAK_EVEN_TOLERANCE_USD`).
10. **Risk-based lot sizing**: lot = risk_usd / (SL pts $\times$ usd_per_point). BTC 1.5%, XAU 1.0%, FX 1.0%.
11. **Slot-3 DeepSeek V4 Flash**: fallback `claude-haiku-4-5-20251001`.
12. **Gemini ganti ke `gemini-3.1-flash-lite`**: benchmark membuktikan 3.1-flash-lite paling konsisten vs 2.5-flash-lite yang sering HOLD.
13. **Deteksi close manual (magic=0)**: `get_closed_positions_today` menerima OUT magic=0 hanya jika posisi dibuka oleh bot.
14. **Post-mortem langsung saat close**: dipicu di loop pas `sync_closed_positions` mendeteksi deal baru.

---

## 2. Iterasi FASE 1 s/d FASE 7 (11–12 Agustus 2026)

1. **FASE 1 — Ekspansi rotasi 7 simbol + FX pindah H1**: pool dari 3 $\rightarrow$ 7 simbol. FX ditetapkan ke H1 swing, risk 1.0%.
2. **FASE 2 — ATR SL Guidance**: AI membaca batas ATR HARD GATE di baris dinamis data pasar.
3. **FASE 3 — Fix terminal wrap**: status line dinamis dipendekkan dan di-render in-place dengan ANSI VT.
4. **FASE 4 — Multi-symbol macro cache**: cache HTF (H4/D1) dirombak menjadi berlaci per-simbol (`self.cache[symbol]`), menghemat download MT5 ~99%.
5. **FASE 5 — Smart Timeframe Rotation**: LLM hanya dipanggil saat lilin timeframe simbol ditutup (FX tiap 1 jam, BTC tiap 30m, XAU tiap 5/15m). Menghemat kuota LLM ~90%.
6. **FASE 6 — Prompt Sync LLM Mode**: penyesuaian teks prompt saat mode SL/TP bebas struktur (LLM).
7. **FASE 7 — Dynamic Micro Candles**: jumlah candle mikro disesuaikan (H1 $\rightarrow$ 24 candle M5 untuk mencakup 2 jam penuh).

---

## 3. Perubahan 13 Agustus 2026 — Pemisahan SL/TP Mode & Trailing Fix

1. **Pemisahan Mode per Kategori**:
   - `XAUUSD` & `BTCUSD` $\rightarrow$ Fix ATR-Based (R:R 2:1).
   - `FX pairs` $\rightarrow$ LLM Mode (bebas struktur + safety floor 50 pts).
2. **BEP & Trailing SL-Based di Mode LLM**:
   - BEP trigger: $\min(1\times \text{SL original}, 50\% \text{ TP})$.
   - Trailing activation: $\max(1.5\times \text{SL}, \text{fallback})$.
   - State `original_sl_points` di `position_manager_state.json`.
3. **Gate OVER-RISK di Consensus**:
   - Menolak trade jika SL melebihi toleransi risiko maksimal akun pada minimum lot broker.

---

## 4. Perubahan 14–15 Agustus 2026 — LLM Rules Baru & BEP/Trailing Pure % TP

1. **Daily Profit Target 6%** (`DAILY_PROFIT_TARGET_PERCENT = 6.0`): menolak posisi baru jika target profit harian telah tercapai.
2. **Dead Zone 02:00–06:00 WIB** (`DANGER_ZONES_WIB`): blokir pembukaan posisi baru saat likuiditas subuh tipis (kecuali BTC).
3. **R:R minimum 1.25:1** (`LLM_MIN_RR_RATIO = 1.25`): TP dinaikkan otomatis jika AI mengusulkan R:R di bawah 1.25.
4. **Perubahan Format Harga FX 5-Desimal**: perbaikan bug formatting `.2f` pada pair Forex.
5. **AI Re-evaluator tetap aktif saat posisi MAX (6/6)**: jika slot penuh, bot tetap memanggil re-evaluator untuk mencari peluang *early exit* pada posisi yang melemah.

---

## 5. Perubahan 24 Agustus 2026 — Transisi ke Ultra-Compact Chain-of-Thought JSON Schema

### 📜 Arsip Skema JSON Lama (Digantikan):
```json
// Skema Lama (HOLD):
{
  "signal": "HOLD",
  "reasoning": "string (MAX 20 WORDS: single key technical reason why no setup exists)"
}

// Skema Lama (BUY/SELL):
{
  "signal": "BUY" | "SELL",
  "confidence": float (0.50 to 1.00),
  "setup": "string (short label for setup type)",
  "reasoning": "string (MAX 60 WORDS: detailed entry thesis, key levels, and core edge for this trade)",
  "invalidation": "string (key technical condition that invalidates this thesis)",
  "sl_points": integer (Stop Loss distance in broker POINTS from current price),
  "tp_points": integer (Take Profit distance in broker POINTS from current price),
  "invalidation_price": float (OPTIONAL: reference price level for invalidation),
  "target_price": float (OPTIONAL: reference price level for target),
  "entry_type": "market" | "buy_stop" | "sell_stop" | "buy_limit" | "sell_limit",
  "entry_price": float
}
```

### ✨ Skema Baru: Ultra-Compact Chain-of-Thought JSON:
```json
{
  "trend": "BULL_PULLBACK | BEAR_PULLBACK | BREAKOUT | RANGING",
  "velocity": "NORMAL | CRASH | STAGNANT",
  "rr_valid": true | false,
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": float (0.00 to 1.00),
  "sl_points": integer (Stop Loss distance in broker POINTS),
  "tp_points": integer (Take Profit distance in broker POINTS),
  "invalidation_price": float (OPTIONAL reference price level),
  "target_price": float (OPTIONAL reference price level),
  "reasoning": "string (1 concise sentence explaining the trade thesis)"
}
```

### 💎 Rangkuman Peningkatan 24 Agustus 2026:
1. **Forced Logic Chain-of-Thought**: Token `trend`, `velocity`, dan `rr_valid` diproses sebelum `signal`, memangkas halusinasi & salah arah pada OpenAI, Gemini, dan DeepSeek.
2. **Kenaikan Threshold FX/XAU $\rightarrow$ 1.20**: Meningkatkan standar kualitas konsensus Forex dan Emas (wajib $\ge 2$ model searah, skor $\ge 1.20$).
3. **Efisiensi & Kecepatan Respons**: Ukuran output terpangkas menjadi ~35 token dengan waktu respons < 5 detik per simbol.

---

## 4. Pembaruan Produksi 25 Agustus 2026 (M30 Intraday & Precision Shield)

1. **Peralihan FX Pairs ke Timeframe M30 & Pool 4 Simbol Liquid**:
   * Seluruh instrumen bot (`FX`, `BTC`, `XAU`) kini seragam berjalan di timeframe **M30 Intraday**.
   * Pool dikurasi menjadi **4 Pair Terbaik**: `GBPUSD-ECNc`, `GBPCHF-ECNc`, `NZDCAD-ECNc`, `AUDCAD-ECNc`.
   * Net Exposure seimbang: `GBP` (2), `CAD` (2), `CHF` (1), `USD` (1), `AUD` (1), `NZD` (1).
   * Eliminasi `EURCHF` *(likuiditas malam tipis)* dan `EURNZD` *(spread lebar $2.5 - 5.0\text{ pips}$)* untuk menghilangkan risiko lonjakan rollover subuh.
2. **Pre-Rollover Precision Distance-to-SL Shield (03:50–04:15 WIB - RFC 9)**:
   * Menutup posisi berisiko secara bersih di jam 03:50 WIB JIKA sisa jarak fisik harga ke level SL $\le$ threshold lonjakan slippage broker per-simbol (`EURCHF`/`EURNZD` 240 pts, `GBPCHF` 210 pts, `GBPUSD` 180 pts, `NZDCAD` 140 pts, `AUDCAD` 130 pts). Posisi dengan SL jauh atau profit tebal dibiarkan jalan ke TP.
3. **Trade-Inception Daily Loss Attribution (`DAILY_LOSS_OPENED_TODAY_ONLY=true`)**:
   * Posisi multi-day yang dibuka kemarin dan terkena SL subuh hari ini tidak lagi memakan kuota 4% max daily loss hari baru. Kuota 4% ($248.73) murni diperuntukkan bagi trade yang dibuka hari ini.
4. **Time-Decay Stagnation Disesuaikan ke 4 Jam (8 Bar M30)**:
   * Parameter `TIME_DECAY_HOURS = 4.0` memotong posisi flat yang hold $\ge 4\text{ jam}$ di rentang $[-0.20R, +0.20R]$ jika Peak MFE $< +0.30R$.
5. **Jadwal Trading Dimulai Jam 08:00 WIB**:
   * Dead zone dipersempit menjadi `00:00 - 08:00 WIB`, sesi Tokyo/Asia Pagi dimulai jam `08:00 - 16:00 WIB`.
6. **Prompt Dinamis Timeframe-Agnostic**:
   * Prompt AI sepenuhnya otomatis membaca dan menyesuaikan label timeframe (`M30`/`H1`), candle price action, ATR aktif, dan momentum summary langsung dari MT5 tanpa perlu modifikasi template prompt.
7. **Sinkronisasi Data Mikro M5 (12 Candle Intra-Period + M5 Momentum Summary)**:
   * Data mikro sub-candle dipadatkan menjadi **12 bar M5 (tepat 1 jam / 2 bar M30)** dan **M5 Momentum Summary (ADX M5, DI delta, EMA20 M5)**. Menghemat ~120 token per cycle dan memberikan deteksi momentum lincah tanpa fetch tambahan.
   * Label struktur 50-bar dan 100-bar kini secara eksplisit mencantumkan nama timeframe (`50-bar M30 Window` & `100-bar M30 Window`).
8. **Dynamic Session-Adaptive Timeframe (`H1 Tokyo` -> `M30 London/NY`)**:
   * Fitur configurable via `.env` (`DYNAMIC_SESSION_TIMEFRAME=true`, `ASIA_TIMEFRAME=H1`, `LONDON_NY_TIMEFRAME=M30`, `DYNAMIC_TF_SWITCH_HOUR_WIB=14`).
   * **Pukul 08:00–14:00 WIB (Tokyo)**: Beroperasi pada timeframe **H1** (60 menit) untuk menyaring noise pasar sepi dan menghemat 50% kuota token pagi.
   * **Pukul 14:00–00:00 WIB (London/NY)**: Otomatis beralih ke timeframe **M30** (30 menit) untuk menangkap ledakan momentum breakout institusi secara lincah.
   * Terintegrasi penuh dan otomatis berubah secara real-time pada: **Prompt AI, CLI Banner, Status Bar Terminal, Menu & Tombol Telegram, serta MTF Macro Context**.

---

## 5. Pembaruan 25 Agustus 2026 (Malam) — Streamlined Prompt V2 & State Machine Clearance Engine

### 📦 Arsip Prompt Lama (Versi 24–25 Agustus Siang — Rollback Reference)
```text
### ROLE
You are an expert {{TIMEFRAME}} short-term intraday-swing analyst for {{SYMBOL}} -- {{ASSET_DESC}}. Your job is to find a high-quality short-term trading opportunity directly from the market data given each cycle, or to conclude that no valid opportunity currently exists.

### EXECUTION CONTEXT
{{EXECUTION_NOTE}}

### ANALYSIS FREEDOM
You are NOT required to follow a single predefined trading strategy. You may use any market interpretation you judge relevant, including but not limited to: trend following, momentum, breakout, pullback, mean reversion, reversal/exhaustion, support/resistance, price action, volatility, or indicator confluence -- alone or combined.

### RISK CONSTRAINTS (apply regardless of chosen strategy)
- A concrete, statable entry thesis (why this direction, why now)
- A clear invalidation condition: the nearest opposing swing structure behind your entry (for BUY: the last relevant swing low below; for SELL: the last relevant swing high above)
{{SLTP_RULES_BLOCK}}

{{POINTS_EXPLANATION}}

### OUTPUT FORMAT
{
  "trend": "BULL_PULLBACK" | "BEAR_PULLBACK" | "BREAKOUT" | "RANGING",
  "velocity": "NORMAL" | "CRASH" | "STAGNANT",
  "rr_valid": true | false,
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": float (0.00 to 1.00),
  "sl_points": integer,
  "tp_points": integer,
  "invalidation_price": float,
  "target_price": float,
{{PENDING_FIELDS}}
  "reasoning": "string (MAX 30 WORDS)"
}
```

### 🚀 Fitur Baru Streamlined Prompt V2 (25 Agustus Malam):
1. **7-Step Decision Framework**: Membimbing inferensi: `Regime` $\rightarrow$ `Location & Clearance` $\rightarrow$ `Setup` $\rightarrow$ `Entry` $\rightarrow$ `Invalidation` $\rightarrow$ `Target` $\rightarrow$ `R:R` (hemat token ~65%, latensi < 3s).
2. **3 Playbooks & Penghapusan Dogma Anti-Fade**: Mengeliminasi klausul kaku *"DO NOT FADE OR SELL"*, membuka peluang *Exhaustion SELL di pucuk* dan *Pullback BUY di support*.
3. **5-State Machine Context**: `FAR`, `TESTING`, `REJECTION`, `COMPRESSION`, `BREAKOUT` sebagai status kesepakatan antara Python dan AI.
4. **Python Deterministic Clearance & ADR Gate**: Menghitung `Range Location %`, `Clearance`, dan `Remaining Daily Range` untuk mencegah pasang TP melayang di sesi sepi.
5. **Konsistensi Jarak SL/TP dari `entry_price`**: Menghilangkan ambiguitas jarak pada pending orders.

---

## 6. Pembaruan 26 Agustus 2026 — 2-Stage Quant Funnel Architecture (Branch `quant-trade`)

1. **Stage 1 (Hybrid Dual-Speed Market Scanner `src/analytics/market_scanner.py`)**:
   * **Slow Macro Layer (H1/D1 Close)**: Meng-cache Kompas Tren D1/H4 (EMA200, ADX $\ge 20$), Range Sesi Asia (08:00–13:00 WIB), dan Dealing Range 100-bar H1 (Diskon $\le 38\%$, Premium $\ge 62\%$) untuk 22 pasangan mata uang & Gold (0 Token).
   * **Fast Execution Radar (60s Tick Scan)**: Memindai live tick 22 pair setiap 60 detik di memori lokal untuk mendeteksi sentuhan level kunci (*London Judas Sweep*, *Trend-Aligned Pullback*, *NY ADR Exhaustion Reversal*).
2. **Stage 2 (3-LLM Consensus Jury with High-Density Structured Dossier `src/core/llm_client.py`)**:
   * AI hanya dipanggil ketika Stage 1 mengonfirmasi setup matang A+ (~4–8 call/hari, hemat kuota ~85%).
   * Mengirimkan *High-Density Pre-Computed Dossier* lengkap dengan validasi skeptisisme *Devil's Advocate*.
3. **Telegram Controller & CLI Overhaul**:
   * Penambahan command `/radar`, `/levels`, `/smc` untuk menampilkan matriks level kunci 22 pair secara real-time.
   * Banner matrix visual di terminal (`render_scanner_banner` & `render_candidate_alert_box`).
4. **Test Suite Verification**:
   * Pembuatan unit test `tests/test_market_scanner.py` dan verifikasi 100% PASS pada seluruh test suite sistem.

---

## 7. Pembaruan 26 Agustus 2026 (Sesi Siang) — LuxAlgo SMC, 2-Pass Jury, Direct Telegram Controller, & Flexible `/analisa`

1. **LuxAlgo Smart Money Concepts (SMC) & Liquidity Map Engine (`src/indicators/lux_smc.py` & `market_scanner.py`)**:
   * Porting algoritma Pine Script LuxAlgo v5 ke Python: mendeteksi *Unmitigated Order Blocks (Bullish/Bearish OB)*, *Fair Value Gaps (FVG)*, *Strong Low / Strong High*, dan *Equal Highs/Lows (EQH/EQL)*.
   * Injeksi langsung ke Bagian 2 Dossier Prompt sehingga AI menaruh Stop Loss presisi di balik Order Block dan Take Profit pada area magnet FVG/Weak High.
2. **2-Pass Sequential Cross-Examination 3-LLM Jury & Qualified Hard Risk Veto (`src/core/llm_client.py` & `consensus.py`)**:
   * **Pass 1**: OpenAI o4-mini (Structure) + Gemini 3.1-Flash (Momentum) voting independen (~3.0s).
   * **Pass 2**: DeepSeek V4-Flash (Devil's Advocate) membaca seluruh berkas Dossier + usulan OpenAI & Gemini, menguji kelemahan logika mereka terhadap 24 candle M5 (~1.5s).
   * **Qualified Hard Risk Veto**: Otomatis menolak trade jika model mengangkat bendera bahaya kritis (`COUNTER_TREND_MOMENTUM`, `HIGH_IMPACT_NEWS`, `LIQUIDITY_TRAP`, `SPREAD_SPIKE`) dengan alasan tertulis untuk mencegah *falling knife*.
3. **Direct Telegram Controller & Proxy Toggle (`config.py`, `.env`, `telegram_bot.py`)**:
   * Menambahkan toggle `TELEGRAM_USE_PROXY=false` dan fallback `TELEGRAM_PROXY_URL` di `.env`. Default beralih ke direct `api.telegram.org` untuk kecepatan respons instan tanpa buffer Vercel.
   * Menambahkan `allowed_updates: ["message", "callback_query"]` pada polling `getUpdates` untuk penanganan klik tombol *inline button* seketika.
   * Penguatan autentikasi `_is_user_authorized` untuk mencegah bentrok multi-instance dan mengeliminasi popup *Access Denied*.
4. **Flexible Custom Timeframe & Auto-Correction di `/analisa` (`telegram_bot.py`, `mt5_connector.py`)**:
   * Dukungan command `/analisa <symbol> [timeframe]` (contoh: `/analisa GBPUSD M15`, `/analisa XAUUSD H4`, `/analisa BTCUSD D1`).
   * Normalisasi timeframe fleksibel (`1H` $\rightarrow$ `H1`, `15M` $\rightarrow$ `M15`, `4H` $\rightarrow$ `H4`, `1D` $\rightarrow$ `D1`).
   * Auto-Correction simbol broker VT Markets (`GBPUSD` $\rightarrow$ `GBPUSD-ECNc`, `GOLD` $\rightarrow$ `XAUUSD-ECNc`, `BTC` $\rightarrow$ `BTCUSD.c`) yang memprioritaskan simbol aktif dengan izin trading penuh (`trade_mode = FULL`).
   * Perbaikan deklarasi menu keyboard `_build_main_menu_keyboard()` 5. **Master Quant Dossier HTML Report (Book-Grade Report — Chapter 11 & 12)**:
    * Pembaruan Chapter 11 (LuxAlgo SMC Framework) dan Chapter 12 (2-Pass Cross-Examination Jury, Veto Engine, Live Transcripts, dan Benchmark Matrix) di `report.html`.

## 8. Pembaruan 26 Agustus 2026 (Sesi Sore) — Session-Aware Pair Selection, Visual MT5 Indicator Upgrade, & `/indicators`

1. **Session-Aware Pair Selection Engine (`src/analytics/market_scanner.py`)**:
   * **Aktivasi Terukur Sesi Tokyo (08:00–14:00 WIB)**: Berdasarkan backtest 10.7 tahun FBS MT5 (22.812 trade), radar Stage 1 Mechanism 2 (*Trend-Aligned Pullback*) diaktifkan di Sesi Tokyo khusus untuk 10 pair ber-EV positif: `USDCAD` (PF 1.18), `AUDCAD` (PF 1.18), `AUDUSD` (PF 1.15), `EURCAD` (PF 1.11), `USDCHF` (PF 1.09), `GBPJPY` (PF 1.08), `XAUUSD` (PF 1.05), `GBPCHF` (PF 1.05), `AUDJPY` (PF 1.04), dan `CADJPY` (PF 1.01).
   * **Proteksi Pair Eropa (08:00–14:00 WIB)**: Pair Eropa murni (`GBPUSD` PF 0.76, `EURCHF` PF 0.65, `GBPAUD` PF 0.77, `EURJPY` PF 0.80) secara otomatis diblokir saat pagi untuk mencegah *false wick* dan kebocoran modal, baru dibuka penuh saat sesi London/Frankfurt resmi dimulai jam 14:00 WIB.
2. **Upgrade Indikator Visual MT5 (`mql5/LuxAlgo_SMC_MT5.mq5` & `.ex5`)**:
   * Menambahkan visualisasi **Dealing Range 100-bar**: Kotak **Premium Zone (61.8% – 100%)** bernuansa *Muted Dark Rose*, kotak **Discount Zone (0% – 38.2%)** bernuansa *Muted Deep Emerald*, garis putus-putus **100% High** & **0% Low** dengan label harga aktual, serta garis titik-titik **50% Equilibrium**.
   * Otomatis di-compile via `MetaEditor64.exe` (0 errors, 0 warnings) dan disinkronkan ke seluruh direktori data terminal MT5.
3. **Telegram Command `/indicators` & `/levels` (`src/core/telegram_bot.py`)**:
   * Menambahkan perintah `/indicators <symbol>` (atau `/levels` / `/smc`) yang merangkum koordinat harga eksak untuk 100% Range High, Zona Premium, 50% Equilibrium, Zona Diskon, 0% Range Low, Order Blocks, dan Fair Value Gaps secara real-time.
4. **Unit Test & Linter Green Verification (`tests/test_market_scanner.py`)**:
   * Menambahkan unit test `test_session_aware_pair_filtering` yang memvalidasi isolasi pair Tokyo vs London/NY. Seluruh 9 unit test suite lulus **100% PASS (OK)**.

---

## 9. Pembaruan 26 Agustus 2026 (Sesi Malam) — High-Confidence Multi-Position Split, H1/M30 Execution Hierarchy, Tri-Hourly Digest, & Atlas DNA Overhaul

1. **High-Confidence 3/3 Consensus Multi-Position Split (+25% Boost per Posisi)**:
   * Jika 3 AI sepakat bulat, confidence rata-rata $\ge 75\%$, dan akun memiliki $\ge 2$ slot kapasitas MT5:
     - Sistem memecah eksekusi menjadi 2 posisi sekaligus @ $0.625\times$ Base Lot (Pos #1 Target Standar TP1, Pos #2 Target Extended 1.2x TP2 + Trailing Stop).
     - *True Clean Arithmetic Mean* diterapkan pada seluruh level konsensus dengan plafon realistis $1.25\times \le \text{TP} \le 3.0\times \text{SL}$.
2. **Strict High-Timeframe Execution Hierarchy (H1 & M30 Only — Anti-Overtrading)**:
   * Stage 1 Fast Radar memindai secara ketat HANYA pada timeframe struktural **H1 & M30** (*London Judas Sweep, Trend Pullback, NY ADR Exhaustion*).
   * Timeframe M5 DILARANG KERAS dijadikan trigger pembuka posisi langsung guna menyaring noise wick broker, mencegah overtrading, dan menekan fee churn.
   * 25 candlestick M5 live dicadangkan eksklusif sebagai berkas audit mikro bagi **DeepSeek V4-Flash (Devil's Advocate)** untuk mendeteksi *falling knife* dan menjatuhkan Hard Risk VETO (`COUNTER_TREND_MOMENTUM`, `LIQUIDITY_TRAP`) sebelum eksekusi MT5.
3. **Penyelarasan Kapasitas Akun & Pembersihan Duplikasi `.env`**:
   * Memperbaiki duplikasi `MAX_OPEN_POSITIONS = 6` dan `PENDING_ORDER_MAX_ACTIVE = 4` di [.env](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/.env) sehingga kuota 6 posisi dan 4 pending aktif konsisten di seluruh modul.
4. **Rekapitulasi 3 Jam Terjadwal Telegram (`alert_trihourly_radar_recap`)**:
   * Pengiriman rekap otomatis setiap jam kelipatan 3 (00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, dan 21:00 WIB) yang merangkum:
     - 📥 Order yang berhasil terpasang dalam 3 jam terakhir
     - 🛡️ Sinyal yang berhasil di-VETO beserta alasan penolakannya
     - 💼 Portofolio & Floating P/L
     - 📊 Arah Kompas Pasar 22 Pair & Zona Diskon/Premium SMC.
5. **Pewarnaan Vonis Yuridis Konsensus CLI (`UI.badge_verdict`)**:
   * `[APPROVE]` Hijau, `[REVISE]` Kuning, dan `[REJECT]` Merah pada terminal CLI.
6. **Overhaul Bab 05: Master Atlas DNA 22 Pasangan Mata Uang di HTML & Markdown**:
   * Master table 22 baris tunggal di [report.html](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/report.html) dan [QUANT_RESEARCH_EDGES.md](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/docs/research/QUANT_RESEARCH_EDGES.md) dilengkapi legenda visual metrik kuantitatif dan pemetaan Dual-DNA (🥇 Alpha Utama & 🥈 Alpha Sekunder) untuk setiap simbol.

---

## 10. Pembaruan 27 Agustus 2026 (Sesi Pagi) — Multi-Touch Cluster Breakout & Delayed Retest Engine

1. **Multi-Touch Cluster Breakout & Delayed Retest Engine (M5 — 27 Agu 2026)**:
   * Validasi 10.7 tahun FBS (23.173 trade, PF 1.11, 21/22 pair profitable): level cluster support/resistance yang disentuh $\ge 2\times$ dan ditembus candle momentum $(\ge 55\%\text{ body})$ dieksekusi via **Pending Limit Order saat retest** (delay 3–4 bar). Dilarang keras *chase breakout* langsung guna mencegah jebakan *Judas Sweep*.
   * Integrasi modul `src/indicators/candle_quality.py` & `src/indicators/sweep_detector.py` ke dalam Fast Radar Stage 1 dan pengayaan payload 8 layer ke LLM Veto (DeepSeek CRO).

---

## 11. Pembaruan 27 Agustus 2026 (Sesi Sore) — Boitoki Currency Strength Matrix & Intraday Market Cycle

1. **Boitoki Currency Strength Matrix Engine (`src/analytics/currency_strength.py`)**:
   * Porting 1:1 algoritma Boitoki CSM ([`csm.txt`](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/external_repos/csm.txt)) via 7 USD Majors di MT5 (`EURUSD`, `USDJPY`, `USDCHF`, `GBPUSD`, `AUDUSD`, `USDCAD`, `NZDUSD`).
   * Menghitung nilai logaritmik relatif ($\ln(P_1/P_2)\times 10000$) dan menurunkan 21 cross pair secara instan via hubungan aljabar matematis (waktu eksekusi < 0.05s, cache 30 detik).
2. **Injeksi Kuantitatif Murni ke Prompt LLM (`src/core/llm_client.py`)**:
   * Menambahkan blok `GLOBAL CURRENCY STRENGTH MATRIX` (Ranking 8-Mata Uang, Base/Quote Score & Rank, Net Currency Delta) ke dalam *Market Data Context*.
   * Murni berupa data/fakta kuantitatif tanpa kalimat direktif perintah (*clean quantitative matrix*), memberikan kebebasan penalaran (*reasoning autonomy*) bagi OpenAI o4-mini, Gemini 3.1 Flash, dan DeepSeek CRO.
3. **Dokumen Spesifikasi & Validasi Backtest 21 Pair FBS (2022–2026)**:
   * Pembuatan dokumen arsitektur [INTRADAY_CSM_AND_DAILY_CYCLE_SPEC.md](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/docs/research/INTRADAY_CSM_AND_DAILY_CYCLE_SPEC.md).
   * Validasi 31.161 trade: memotong 90% trade overtrading, memulihkan modal $+7.333\text{R}$ (+92% kerugian terpangkas), dan membalikkan 6 pair utama menjadi profitabel (`EURUSD` PF 1.09, `GBPUSD` PF 1.08, `AUDJPY` PF 1.09, `EURJPY` PF 1.07, `EURAUD` PF 1.05, `GBPJPY` PF 1.03).

---

## 12. Pembaruan 27 Agustus 2026 (Sesi Malam) — 2-Stage Dynamic Trailing Stop Engine

1. **2-Stage Dynamic Trailing Stop (`src/analytics/position_manager.py` & `config.py`)**:
   * **Stage 1 (Swing Breathing Zone: 65% s/d < 90% TP)**: Jarak dihitung berbasis **ATR H1 ($0.75\times\text{ATR H1}$)** dengan floor absolut 80 pts (8 pips FX) untuk memberi ruang nafas yang longgar dari noise wick agar posisi dapat melaju mulus ke TP2.
   * **Stage 2 (Terminal Profit Lock: $\ge$ 90% TP)**: Otomatis mengencang (*tightening*) berbasis **ATR M30 ($0.50\times\text{ATR M30}$)** dengan floor 30 pts (3 pips FX) untuk mengunci cuan 90% secara rapat di pucuk sebelum terjadi pembalikan harga mendadak tepat di depan target TP.

---

## 13. Pembaruan 28 Agustus 2026 (Sesi Pagi & Siang) — FRVP Confluence, Wave State Machine, & Anti-Wick SL Buffer

1. **Fixed Range Volume Profile (FRVP) Confluence Engine (`src/indicators/volume_profile.py`, `lux_smc.py`, `market_scanner.py`)**:
   * Validasi kuantitatif 110.460 trade (4.3 tahun data broker MT5, 24 simbol): sinergi **SMC + FRVP** memangkas 59.2% trade noise dan melipatgandakan **Expected Value (+104% R)** serta menaikkan Profit Factor (`EURCHF` PF 1.79, `GBPCHF` PF 1.53, `XAUUSD` & `USDJPY` berbalik net profit).
   * Menghitung Point of Control (POC), Value Area High (VAH), Value Area Low (VAL), dan rating Order Block (A+, A, B).
2. **Wave State Machine & Trade Permission Engine (`src/indicators/wave_state.py`)**:
   * Validasi 2.793.591 trade (2010–2026): memisahkan *Direction* (Macro D1/H4) dari *Trade Permission* (kapan waktu yang tepat untuk masuk H1).
   * Menghilangkan *Impulse Chase* (Phase 1, PF 0.52) dan *Early Falling Knife* (Phase 2, PF 0.97).
   * Membuka izin trading HANYA pada *Mature Basing* (Phase 3, PF 1.30) dan *Base Reclaim* (Phase 4, PF 1.42) di zona Dealing Range Discount ($\le 0.50$, Golden Pocket $\le 0.382$).
   * Asymmetric CSM Flow: Melarang BUY hanya saat terjadi *systemic dump* ($\text{Delta} \le -2.0$), membebaskan *neutral flow* saat pullback diskon yang sehat.
3. **Anti-Wick Buffer & Structural SL Anchoring (M30 — `market_scanner.py`)**:
   * Validasi kuantitatif 2.900.000 candle M30 (2018–2026, 29 instrumen): Stop Loss wajib dijangkar **di balik lantai support/order block fisik ditambah Anti-Wick Buffer $0.35\times\text{ATR} + \text{Spread}$**, bukan dihitung dari harga entri (`mid`).
   * Menghilangkan *False Wick Stop-Out* saat harga menguji lantai akumulasi/diskon, meningkatkan Win Rate Trend-Aligned Supply/Demand Retest menjadi **57.2% – 58.1% (PF 1.17 – 1.23)**.

---

## 14. Pembaruan 28 Agustus 2026 (Sesi Sore) — Real Wick Measurement, Anti-Waterfall Judas Sweep, Dynamic Point & Live News

1. **Real Candlestick Wick Measurement & Anti-Waterfall Judas Sweep Protection (`src/analytics/market_scanner.py` & `tests/test_market_scanner.py`)**:
   * Mengeliminasi nilai statis `rejection_wick_ratio` yang sebelumnya ter-hardcode (0.35 / 0.30) di seluruh 4 mekanisme `market_scanner.py`.
   * Mengintegrasikan helper `_evaluate_live_candle_quality` menggunakan modul `classify_candle` pada data candle live M15 & candle tertutup sebelumnya.
   * Menambahkan filter *Anti-Breakdown Waterfall* pada `LONDON_JUDAS_SWEEP`: melarang keras trigger BUY jika lilin live berupa marubozu merah tebal yang menembus level tanpa sumbu bawah, serta mewajibkan konfirmasi pembalikan fisik (*reclaim* atau *lower rejection wick* $\ge 20\%$). Mencegah false trigger saat terjadi reli/dumping mata uang ekstrem.
2. **Dynamic MT5 Point Resolution (`src/analytics/market_scanner.py`)**:
   * Mengubah `_get_point(sym)` di `market_scanner.py` agar meminta `symbol_info.point` langsung dari broker MT5 dengan fallback cerdas berbasis aset (JPY $\rightarrow 0.001$, XAU/BTC $\rightarrow 0.01$, FX $\rightarrow 0.00001$).
3. **Live Economic News Injection (`src/core/llm_client.py`)**:
   * Mengaktifkan live fetch berita ekonomi via API TradingView/Investing.com di `llm_client.py` (`build_high_density_dossier_prompt`) saat menyusun dossier untuk 3-LLM Jury.
   * Menampilkan event berita berdampak tinggi ($\le 6$ jam sebelum & sesudah rilis) pada Section 4: *ECONOMIC CONTEXT & NEWS SHIELD*.
4. **Dynamic Risk-to-Reward Ratio & Full FRVP Injection (`src/analytics/market_scanner.py`)**:
   * Menginjeksikan ringkasan Fixed Range Volume Profile (`frvp_confluence` POC/VAL/VAH) ke seluruh 8 kandidat radar di `market_scanner.py`.
   * Menghitung `risk_reward_ratio` secara dinamis dari formula matematis $|\text{TP} - \text{Trigger}| / |\text{Trigger} - \text{SL}|$.
5. **Telegram Interactive `/news` Command & Cyberpunk Bento HUD Live News Ticker (`src/core/telegram_bot.py` & `src/core/cli_theme.py`)**:
   * Menambahkan perintah interaktif `/news` (beserta alias `/kalender`, `/berita`, `/event`) dan tombol inline keyboard pada menu utama Telegram Controller.
   * Mengintegrasikan ticker berita real-time pada Tile 3 (*Dual-Horizon Boitoki CSM*) dan Tile 4 (*2-Pass Sequential Jury*) di Bento Box Terminal HUD (`cli_theme.py`), menampilkan hitung mundur waktu rilis (misal: `[CA] GDP MoM Prel in 2.0h (19:30 WIB)`).
6. **Intraday Entry-Anchored SL/TP with Anti-Wick Padding & Risk Safety Ceiling (`src/analytics/market_scanner.py` & `src/core/consensus.py`)**:
   * Mengembalikan formula SL/TP intraday pada `TREND_ALIGNED_PULLBACK` dan `NY_ADR_REVERSAL` di `market_scanner.py` berbasis harga entri (`mid`) dengan penambahan **Anti-Wick Padding (+15 pts / 1.5 pips)** untuk mencegah SL tersapu noise wick broker.
   * Mengeliminasi pencarian swing low/high makro D1/H4 yang berpotensi menghasilkan SL swing >600 pts.
   * Menambahkan **Hard Intraday Safety Ceiling** pada `_apply_sltp_rules` di `consensus.py` (FX: $\max \text{SL} = \min(2.0\times\text{ATR}, 160\text{ pts})$; Gold: $\max \text{SL} = 2.5\times\text{ATR}$) untuk menjamin secara matematis SL tidak pernah lepas kendali.

---

## 15. Pembaruan 28 Agustus 2026 (Sesi Malam) — 4-Layer Trend-Aligned Permission Engine, Delayed Limit Retest & NZD Alpha Expansion

1. **4-Layer Trend-Aligned Trade Permission Engine (`src/analytics/market_scanner.py`, `currency_strength.py`, `wave_state.py`)**:
   * **Pemisahan Irama (Cadence Separation)**:
     - `Direction FSM (D1+H4)`: Lambat, butuh `confirm_count=2` hysteresis (anti flip-flop).
     - `Phase FSM (H1 Wave)`: Menentukan fase siklus (`EXPANSION`, `EARLY_CORRECTION`, `MATURE_CORRECTION`, `RECLAIM`).
     - `CSM Pressure Gauge`: Modifier real-time continuous flow sub-detik (`get_csm_delta_for_symbol`).
     - `Permission Matrix`: Lookup table deterministik (`WAIT`, `LOCK`, `WATCH`, `ARM`, `GO`).
   * **Prinsip `BUY LOCKED != SELL ENABLED`**: Mencegah *falling knife* (saat koreksi tajam dalam tren bullish, status adalah `LOCK`, bukan mencari posisi SELL counter-trend).
2. **Delayed Limit Retest & Structural SL Anchoring ($0.20\times\text{ATR}$)**:
   * Memasang Limit Order saat retest ke zona diskon ($0.20\times\text{ATR}$) dengan Stop Loss di balik support fisik ditambah Anti-Wick Buffer $0.35\times\text{ATR}$.
   * Validasi Walk-Forward 16 Tahun (2010–2026): Out-of-Sample PF **1.25** (+8.391,6R) dengan Edge Retention **78.7%** (Total Return 16 thn: **+$34.462,6R**).
3. **Ekspansi 5 Pasangan NZD Alpha (Universe 27 Simbol — `.env` & `config.py`)**:
   * Validasi 16 tahun 7 pasangan NZD: berbalik dari rugi **-9.251,1R** (metode lama) menjadi untung bersih **+$1.842,3R (PF 1.34)**.
   * Memasukkan `NZDCAD`, `NZDCHF`, `NZDUSD`, `GBPNZD`, `AUDNZD`, `EURNZD` ke `SCANNER_SYMBOLS` (Universe 27 pasang).
4. **Cross-Pair Asymmetric Dispersion Discovery**:
   * Analisis 19.765 snapshot multi-pair: 83.25% waktu pasar tersebar di berbagai fase berbeda, menjamin peluang trading harian konsisten sebesar **93.3%**.
5. **Dokumentasi Riset & Test Suite 100% PASS**:
   * Hasil riset tersimpan lengkap di `docs/research/RESEARCH_4_LAYER_PERMISSION_AND_NZD_BENCHMARK.md`.
   * Seluruh test suite (23 unit tests) lulus 100% OK.

---

## 16. Pembaruan 28 Agustus 2026 (Larut Malam) — Eliminasi NY ADR Reversal & Integrasi M3 (M6) HTF Weekly Wall Reversal

1. **Eliminasi Total Mechanism 3 Lama (`NY_ADR_REVERSAL`)**:
   * Backtest 16.2 tahun MetaQuotes H1 (71.831 trade) mengungkap bahwa fading 75% ADR di sesi New York menghasilkan rugi bersih **-3.637,3R (PF 0.93)** akibat *institutional steamroller effect* saat rilis berita ekonomi AS.
   * Mekanisme ini dihapus 100% dari arsitektur live `market_scanner.py`.
2. **Implementasi Mechanism 3 Baru: `HTF_WEEKLY_WALL_REVERSAL` (M6)**:
   * Memanfaatkan tabrak dinding *Previous Week High/Low (PWH/PWL)* dengan *Rejection Wick $\ge 25\%$* di H1.
   * Target Take Profit dijangkar secara objektif ke **Weekly 50% Equilibrium (Pijakan Keseimbangan)** atau Order Block terdekat, dengan SL di balik sumbu PWH/PWL ($0.35\times\text{ATR} + \text{Spread} + 20\text{ pts}$).
   * Backtest 16.2 tahun membuktikan strategi ini menghasilkan **+$586,1R$ (PF 1.05 – 1.23)** pada cluster pair alpha (`EURCHF`, `AUDCHF`, `GBPCAD`, `CADCHF`, `AUDUSD`, `EURUSD`, `USDJPY`).
3. **Sinkronisasi 4 Mekanisme Produksi di `market_scanner.py`**:
   * **M1**: `LONDON_JUDAS_SWEEP` (Asian High/Low sweep $\ge 20\%$ wick).
   * **M2**: `TREND_ALIGNED_PULLBACK` (4-Layer FSM + Delayed Limit Retest $0.20\times\text{ATR}$).
   * **M3**: `HTF_WEEKLY_WALL_REVERSAL` (Tabrak Dinding HTF $\rightarrow$ Pijakan 50% Equilibrium).
   * **M4**: `MULTI_TOUCH_BREAKOUT_RETEST` (Breakout Retest $\ge 2\times$ touches).
4. **Master Quant Dossier 16.2 Tahun & Overhaul `report.html`**:
   * Dokumen riset teknikal tersimpan di [`docs/research/METAQUOTES_16YEAR_MASTER_BACKTEST_REPORT.md`](file:///c:/Vibe/tradingpartner/docs/research/METAQUOTES_16YEAR_MASTER_BACKTEST_REPORT.md).
   * Web report 20 Bab diperbarui di [`report.html`](file:///c:/Vibe/tradingpartner/report.html).
   * Unit test suite lulus 100% OK (23/23 tests pass).

---

## 17. Pembaruan 29 Agustus 2026 (Sesi Siang) — Pure Quant Hierarchical Macro Strategic Engine (MSE) & Atlas DNA Station Delivery

1. **Pure Quant Hierarchical Top-Down Macro Strategic Engine (`src/analytics/macro_strategic_engine.py`)**:
   * Integrasi 6 timeframe asli MT5 (`MN1` 50 bar, `W1` 100 bar, `D1` 350 bar, `H4` 400 bar, `H1` 250 bar, `M30` 200 bar).
   * Komputasi matematis sub-detik ($<50\text{ ms per pair}$, 0 Token LLM).
   * Menghasilkan direktif koridor institusional (`HUNT_SELL_AT_SBR`, `HUNT_BUY_AT_RBS`) dan daftar jebakan visual (`forbidden_traps`).
2. **Atlas DNA Dual-Grid Station Calculator (`src/indicators/atlas_dna.py`)**:
   * **Major Stations (100-Pip Grid / $10.00 Gold)**: Angka bulat institusional.
   * **Sub-Stations (50-Pip Grid / $5.00 Gold)**: Koridor pergerakan harga intraday.
   * **Formula Intraday SL/TP Anchoring**: Menjangkar SL di balik support/resistance fisik $+ 0.35\times\text{ATR}$ Anti-Wick Buffer dan mengunci Safety Ceiling ($\le 16.0\text{ pips}$ / 160 pts).
3. **Telegram Command `/macro <symbol>` (`src/core/telegram_bot.py`)**:
   * Menyediakan laporan on-demand status koridor makro, station ladder, zona SBR/RBS, dan rekomendasi eksekusi per pair secara visual di chat Telegram.

---

## 18. Pembaruan 29 Agustus 2026 (Sesi Malam) — Universal 8-Currency Basket Circuit Breaker & Live E2E 3-LLM Jury Replay

1. **Universal 8-Currency Basket Circuit Breaker (`src/analytics/currency_strength.py` & `config.py` / `.env`)**:
   * Generalisasi perlindungan sirkuit ke seluruh 8 mata uang utama (`USD, EUR, GBP, JPY, CHF, AUD, CAD, NZD`).
   * Dual-Horizon Basket Flow weighting: 60% kecepatan sesi M15 (16 bar) + 40% jangkar tren H1 (24 bar).
   * **Kalibrasi Threshold Empiris**:
     - `SYSTEMIC_BASKET_USD_THRESHOLD = 2.0` (20.0 pts Boitoki).
     - `SYSTEMIC_BASKET_JPY_THRESHOLD = 2.0` (20.0 pts Boitoki).
     - `SYSTEMIC_BASKET_CROSS_THRESHOLD = 2.0` (20.0 pts Boitoki).
     - `SYSTEMIC_BASKET_SPREAD_THRESHOLD = 1.8` (18.0 pts Boitoki Relative Delta Spread).
   * Otomatis mengunci (Hard Lock) order counter-flow saat Base/Quote mengalami systemic dump/surge atau selisih kekuatan melebihi toleransi.
2. **Directional Hard Gate di Stage 1 Radar (`src/analytics/market_scanner.py`)**:
   * Menolak kandidat setup yang dilarang oleh MSE Directive atau Basket Gate sebelum pemanggilan LLM Jury (hemat 100% token).
3. **End-to-End Live Multi-LLM Replay Validation (27–28 Agustus 2026)**:
   * Validasi audit 3-LLM Jury (OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4-Flash CRO) pada 11 pair live account.
   * **Hasil Finansial**:
     - `GBPUSD` berbalik dari loss -$82.69 (akun riil) menjadi **+$135.00 (+2.25 R, 3/3 Win)** via SELL Pullbacks.
     - `EURUSD`: +2.00 R (+$120.00), `GBPCHF`: +2.15 R (+$129.00), `EURCHF`: +0.30 R (+$18.00).
     - **Net Return Terverifikasi**: **+2.85 R (+$171.00 pada equity $6,000)** dengan Win Rate 58.8%.
4. **Master Report HTML Bab 21**:
   * Web report `report.html` diperbarui dengan Bab 21 (Universal 8-Currency Basket & Pure Quant MSE Corridor Engine).
   * Seluruh unit test suite lulus **100% OK (44/44 Tests Pass)**.

---

## 19. Pembaruan 30 Agustus 2026 — Eliminasi Permanen XAUUSD (Gold) & Transisi Portofolio Murni 26 FX Universe

1. **Audit Riil 788 Deals Akun Live (`VTMarkets-Live 3`, Login `27556325`)**:
   * Audit menemukan sumber utama drawdown dari modal awal $\$6,500$ ke $\$5,819$ ($-\$681$ loss) adalah **$100\%$ disebabkan oleh Gold (`XAUUSD-ECNc`) yang menyumbang kerugian sebesar $-\$1,067.79$**.
   * Sebaliknya, seluruh portofolio 26 pasangan mata uang (**FX Majors & Yen Crosses**) membukukan net profit gabungan **$+\$387.08$** (`CADJPY` +$98.02, `USDCAD` +$63.86, `AUDJPY` +$43.88, `EURAUD` +$41.96, `EURJPY` +$41.45).
2. **Penghapusan Total & Permanen `XAUUSD-ECNc`**:
   * `XAUUSD-ECNc` dihapus $100\%$ dari `SCANNER_SYMBOLS` di `.env` dan `ALL_SCANNER_SYMBOLS` di `config.py`.
   * Scanner universe kini murni terdiri dari **26 FX Majors & Crosses Terkurasi**.
3. **Penyelarasan Seluruh Stack & Antarmuka**:
   * **CLI Theme**: Banner terminal diperbarui menjadi `[26-PAIR PRO]`.
   * **Telegram Controller (`telegram_bot.py`)**: Menu keyboard diperbarui menggantikan tombol Gold dengan `EURJPY H1` dan `CADJPY H1` serta label `[ SMC Radar 26 Pairs ]`.
   * **Unit Tests**: [`tests/test_symbol_rotation.py`](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/tests/test_symbol_rotation.py) diperbarui dengan `assertNotIn("XAUUSD-ECNc")` — seluruh **44/44 Unit Tests (100%) LULUS**.
   * **MQL5 EA Reference**: Diberi nama institusional `mql5/XAU_Institutional_SMC_EA.mq5` dengan kalkulasi komisi dinamis 1:1 dari `position_manager.py`.

---

## 9. Pembaruan 26 Agustus 2026 (Sesi Malam) — High-Confidence Multi-Position Split, H1/M30 Execution Hierarchy, Tri-Hourly Digest, & Atlas DNA Overhaul

1. **High-Confidence 3/3 Consensus Multi-Position Split (+25% Boost per Posisi)**:
   * Jika 3 AI sepakat bulat, confidence rata-rata $\ge 75\%$, dan akun memiliki $\ge 2$ slot kapasitas MT5:
     - Sistem memecah eksekusi menjadi 2 posisi sekaligus @ $0.625\times$ Base Lot (Pos #1 Target Standar TP1, Pos #2 Target Extended 1.2x TP2 + Trailing Stop).
     - *True Clean Arithmetic Mean* diterapkan pada seluruh level konsensus dengan plafon realistis $1.25\times \le \text{TP} \le 3.0\times \text{SL}$.
2. **Strict High-Timeframe Execution Hierarchy (H1 & M30 Only — Anti-Overtrading)**:
   * Stage 1 Fast Radar memindai secara ketat HANYA pada timeframe struktural **H1 & M30** (*London Judas Sweep, Trend Pullback, NY ADR Exhaustion*).
   * Timeframe M5 DILARANG KERAS dijadikan trigger pembuka posisi langsung guna menyaring noise wick broker, mencegah overtrading, dan menekan fee churn.
   * 25 candlestick M5 live dicadangkan eksklusif sebagai berkas audit mikro bagi **DeepSeek V4-Flash (Devil's Advocate)** untuk mendeteksi *falling knife* dan menjatuhkan Hard Risk VETO (`COUNTER_TREND_MOMENTUM`, `LIQUIDITY_TRAP`) sebelum eksekusi MT5.
3. **Penyelarasan Kapasitas Akun & Pembersihan Duplikasi `.env`**:
   * Memperbaiki duplikasi `MAX_OPEN_POSITIONS = 6` dan `PENDING_ORDER_MAX_ACTIVE = 4` di [.env](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/.env) sehingga kuota 6 posisi dan 4 pending aktif konsisten di seluruh modul.
4. **Rekapitulasi 3 Jam Terjadwal Telegram (`alert_trihourly_radar_recap`)**:
   * Pengiriman rekap otomatis setiap jam kelipatan 3 (00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, dan 21:00 WIB) yang merangkum:
     - 📥 Order yang berhasil terpasang dalam 3 jam terakhir
     - 🛡️ Sinyal yang berhasil di-VETO beserta alasan penolakannya
     - 💼 Portofolio & Floating P/L
     - 📊 Arah Kompas Pasar 22 Pair & Zona Diskon/Premium SMC.
5. **Pewarnaan Vonis Yuridis Konsensus CLI (`UI.badge_verdict`)**:
   * `[APPROVE]` Hijau, `[REVISE]` Kuning, dan `[REJECT]` Merah pada terminal CLI.
6. **Overhaul Bab 05: Master Atlas DNA 22 Pasangan Mata Uang di HTML & Markdown**:
   * Master table 22 baris tunggal di [report.html](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/report.html) dan [QUANT_RESEARCH_EDGES.md](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/docs/research/QUANT_RESEARCH_EDGES.md) dilengkapi legenda visual metrik kuantitatif dan pemetaan Dual-DNA (🥇 Alpha Utama & 🥈 Alpha Sekunder) untuk setiap simbol.

---

## 10. Pembaruan 27 Agustus 2026 (Sesi Pagi) — Multi-Touch Cluster Breakout & Delayed Retest Engine

1. **Multi-Touch Cluster Breakout & Delayed Retest Engine (M5 — 27 Agu 2026)**:
   * Validasi 10.7 tahun FBS (23.173 trade, PF 1.11, 21/22 pair profitable): level cluster support/resistance yang disentuh $\ge 2\times$ dan ditembus candle momentum $(\ge 55\%\text{ body})$ dieksekusi via **Pending Limit Order saat retest** (delay 3–4 bar). Dilarang keras *chase breakout* langsung guna mencegah jebakan *Judas Sweep*.
   * Integrasi modul `src/indicators/candle_quality.py` & `src/indicators/sweep_detector.py` ke dalam Fast Radar Stage 1 dan pengayaan payload 8 layer ke LLM Veto (DeepSeek CRO).

---

## 11. Pembaruan 27 Agustus 2026 (Sesi Sore) — Boitoki Currency Strength Matrix & Intraday Market Cycle

1. **Boitoki Currency Strength Matrix Engine (`src/analytics/currency_strength.py`)**:
   * Porting 1:1 algoritma Boitoki CSM ([`csm.txt`](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/external_repos/csm.txt)) via 7 USD Majors di MT5 (`EURUSD`, `USDJPY`, `USDCHF`, `GBPUSD`, `AUDUSD`, `USDCAD`, `NZDUSD`).
   * Menghitung nilai logaritmik relatif ($\ln(P_1/P_2)\times 10000$) dan menurunkan 21 cross pair secara instan via hubungan aljabar matematis (waktu eksekusi < 0.05s, cache 30 detik).
2. **Injeksi Kuantitatif Murni ke Prompt LLM (`src/core/llm_client.py`)**:
   * Menambahkan blok `GLOBAL CURRENCY STRENGTH MATRIX` (Ranking 8-Mata Uang, Base/Quote Score & Rank, Net Currency Delta) ke dalam *Market Data Context*.
   * Murni berupa data/fakta kuantitatif tanpa kalimat direktif perintah (*clean quantitative matrix*), memberikan kebebasan penalaran (*reasoning autonomy*) bagi OpenAI o4-mini, Gemini 3.1 Flash, dan DeepSeek CRO.
3. **Dokumen Spesifikasi & Validasi Backtest 21 Pair FBS (2022–2026)**:
   * Pembuatan dokumen arsitektur [INTRADAY_CSM_AND_DAILY_CYCLE_SPEC.md](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/docs/research/INTRADAY_CSM_AND_DAILY_CYCLE_SPEC.md).
   * Validasi 31.161 trade: memotong 90% trade overtrading, memulihkan modal $+7.333\text{R}$ (+92% kerugian terpangkas), dan membalikkan 6 pair utama menjadi profitabel (`EURUSD` PF 1.09, `GBPUSD` PF 1.08, `AUDJPY` PF 1.09, `EURJPY` PF 1.07, `EURAUD` PF 1.05, `GBPJPY` PF 1.03).

---

## 12. Pembaruan 27 Agustus 2026 (Sesi Malam) — 2-Stage Dynamic Trailing Stop Engine

1. **2-Stage Dynamic Trailing Stop (`src/analytics/position_manager.py` & `config.py`)**:
   * **Stage 1 (Swing Breathing Zone: 65% s/d < 90% TP)**: Jarak dihitung berbasis **ATR H1 ($0.75\times\text{ATR H1}$)** dengan floor absolut 80 pts (8 pips FX) untuk memberi ruang nafas yang longgar dari noise wick agar posisi dapat melaju mulus ke TP2.
   * **Stage 2 (Terminal Profit Lock: $\ge$ 90% TP)**: Otomatis mengencang (*tightening*) berbasis **ATR M30 ($0.50\times\text{ATR M30}$)** dengan floor 30 pts (3 pips FX) untuk mengunci cuan 90% secara rapat di pucuk sebelum terjadi pembalikan harga mendadak tepat di depan target TP.

---

## 13. Pembaruan 28 Agustus 2026 (Sesi Pagi & Siang) — FRVP Confluence, Wave State Machine, & Anti-Wick SL Buffer

1. **Fixed Range Volume Profile (FRVP) Confluence Engine (`src/indicators/volume_profile.py`, `lux_smc.py`, `market_scanner.py`)**:
   * Validasi kuantitatif 110.460 trade (4.3 tahun data broker MT5, 24 simbol): sinergi **SMC + FRVP** memangkas 59.2% trade noise dan melipatgandakan **Expected Value (+104% R)** serta menaikkan Profit Factor (`EURCHF` PF 1.79, `GBPCHF` PF 1.53, `XAUUSD` & `USDJPY` berbalik net profit).
   * Menghitung Point of Control (POC), Value Area High (VAH), Value Area Low (VAL), dan rating Order Block (A+, A, B).
2. **Wave State Machine & Trade Permission Engine (`src/indicators/wave_state.py`)**:
   * Validasi 2.793.591 trade (2010–2026): memisahkan *Direction* (Macro D1/H4) dari *Trade Permission* (kapan waktu yang tepat untuk masuk H1).
   * Menghilangkan *Impulse Chase* (Phase 1, PF 0.52) dan *Early Falling Knife* (Phase 2, PF 0.97).
   * Membuka izin trading HANYA pada *Mature Basing* (Phase 3, PF 1.30) dan *Base Reclaim* (Phase 4, PF 1.42) di zona Dealing Range Discount ($\le 0.50$, Golden Pocket $\le 0.382$).
   * Asymmetric CSM Flow: Melarang BUY hanya saat terjadi *systemic dump* ($\text{Delta} \le -2.0$), membebaskan *neutral flow* saat pullback diskon yang sehat.
3. **Anti-Wick Buffer & Structural SL Anchoring (M30 — `market_scanner.py`)**:
   * Validasi kuantitatif 2.900.000 candle M30 (2018–2026, 29 instrumen): Stop Loss wajib dijangkar **di balik lantai support/order block fisik ditambah Anti-Wick Buffer $0.35\times\text{ATR} + \text{Spread}$**, bukan dihitung dari harga entri (`mid`).
   * Menghilangkan *False Wick Stop-Out* saat harga menguji lantai akumulasi/diskon, meningkatkan Win Rate Trend-Aligned Supply/Demand Retest menjadi **57.2% – 58.1% (PF 1.17 – 1.23)**.

---

## 14. Pembaruan 28 Agustus 2026 (Sesi Sore) — Real Wick Measurement, Anti-Waterfall Judas Sweep, Dynamic Point & Live News

1. **Real Candlestick Wick Measurement & Anti-Waterfall Judas Sweep Protection (`src/analytics/market_scanner.py` & `tests/test_market_scanner.py`)**:
   * Mengeliminasi nilai statis `rejection_wick_ratio` yang sebelumnya ter-hardcode (0.35 / 0.30) di seluruh 4 mekanisme `market_scanner.py`.
   * Mengintegrasikan helper `_evaluate_live_candle_quality` menggunakan modul `classify_candle` pada data candle live M15 & candle tertutup sebelumnya.
   * Menambahkan filter *Anti-Breakdown Waterfall* pada `LONDON_JUDAS_SWEEP`: melarang keras trigger BUY jika lilin live berupa marubozu merah tebal yang menembus level tanpa sumbu bawah, serta mewajibkan konfirmasi pembalikan fisik (*reclaim* atau *lower rejection wick* $\ge 20\%$). Mencegah false trigger saat terjadi reli/dumping mata uang ekstrem.
2. **Dynamic MT5 Point Resolution (`src/analytics/market_scanner.py`)**:
   * Mengubah `_get_point(sym)` di `market_scanner.py` agar meminta `symbol_info.point` langsung dari broker MT5 dengan fallback cerdas berbasis aset (JPY $\rightarrow 0.001$, XAU/BTC $\rightarrow 0.01$, FX $\rightarrow 0.00001$).
3. **Live Economic News Injection (`src/core/llm_client.py`)**:
   * Mengaktifkan live fetch berita ekonomi via API TradingView/Investing.com di `llm_client.py` (`build_high_density_dossier_prompt`) saat menyusun dossier untuk 3-LLM Jury.
   * Menampilkan event berita berdampak tinggi ($\le 6$ jam sebelum & sesudah rilis) pada Section 4: *ECONOMIC CONTEXT & NEWS SHIELD*.
4. **Dynamic Risk-to-Reward Ratio & Full FRVP Injection (`src/analytics/market_scanner.py`)**:
   * Menginjeksikan ringkasan Fixed Range Volume Profile (`frvp_confluence` POC/VAL/VAH) ke seluruh 8 kandidat radar di `market_scanner.py`.
   * Menghitung `risk_reward_ratio` secara dinamis dari formula matematis $|\text{TP} - \text{Trigger}| / |\text{Trigger} - \text{SL}|$.
5. **Telegram Interactive `/news` Command & Cyberpunk Bento HUD Live News Ticker (`src/core/telegram_bot.py` & `src/core/cli_theme.py`)**:
   * Menambahkan perintah interaktif `/news` (beserta alias `/kalender`, `/berita`, `/event`) dan tombol inline keyboard pada menu utama Telegram Controller.
   * Mengintegrasikan ticker berita real-time pada Tile 3 (*Dual-Horizon Boitoki CSM*) dan Tile 4 (*2-Pass Sequential Jury*) di Bento Box Terminal HUD (`cli_theme.py`), menampilkan hitung mundur waktu rilis (misal: `[CA] GDP MoM Prel in 2.0h (19:30 WIB)`).
6. **Intraday Entry-Anchored SL/TP with Anti-Wick Padding & Risk Safety Ceiling (`src/analytics/market_scanner.py` & `src/core/consensus.py`)**:
   * Mengembalikan formula SL/TP intraday pada `TREND_ALIGNED_PULLBACK` dan `NY_ADR_REVERSAL` di `market_scanner.py` berbasis harga entri (`mid`) dengan penambahan **Anti-Wick Padding (+15 pts / 1.5 pips)** untuk mencegah SL tersapu noise wick broker.
   * Mengeliminasi pencarian swing low/high makro D1/H4 yang berpotensi menghasilkan SL swing >600 pts.
   * Menambahkan **Hard Intraday Safety Ceiling** pada `_apply_sltp_rules` di `consensus.py` (FX: $\max \text{SL} = \min(2.0\times\text{ATR}, 160\text{ pts})$; Gold: $\max \text{SL} = 2.5\times\text{ATR}$) untuk menjamin secara matematis SL tidak pernah lepas kendali.

---

## 15. Pembaruan 28 Agustus 2026 (Sesi Malam) — 4-Layer Trend-Aligned Permission Engine, Delayed Limit Retest & NZD Alpha Expansion

1. **4-Layer Trend-Aligned Trade Permission Engine (`src/analytics/market_scanner.py`, `currency_strength.py`, `wave_state.py`)**:
   * **Pemisahan Irama (Cadence Separation)**:
     - `Direction FSM (D1+H4)`: Lambat, butuh `confirm_count=2` hysteresis (anti flip-flop).
     - `Phase FSM (H1 Wave)`: Menentukan fase siklus (`EXPANSION`, `EARLY_CORRECTION`, `MATURE_CORRECTION`, `RECLAIM`).
     - `CSM Pressure Gauge`: Modifier real-time continuous flow sub-detik (`get_csm_delta_for_symbol`).
     - `Permission Matrix`: Lookup table deterministik (`WAIT`, `LOCK`, `WATCH`, `ARM`, `GO`).
   * **Prinsip `BUY LOCKED != SELL ENABLED`**: Mencegah *falling knife* (saat koreksi tajam dalam tren bullish, status adalah `LOCK`, bukan mencari posisi SELL counter-trend).
2. **Delayed Limit Retest & Structural SL Anchoring ($0.20\times\text{ATR}$)**:
   * Memasang Limit Order saat retest ke zona diskon ($0.20\times\text{ATR}$) dengan Stop Loss di balik support fisik ditambah Anti-Wick Buffer $0.35\times\text{ATR}$.
   * Validasi Walk-Forward 16 Tahun (2010–2026): Out-of-Sample PF **1.25** (+8.391,6R) dengan Edge Retention **78.7%** (Total Return 16 thn: **+$34.462,6R**).
3. **Ekspansi 5 Pasangan NZD Alpha (Universe 27 Simbol — `.env` & `config.py`)**:
   * Validasi 16 tahun 7 pasangan NZD: berbalik dari rugi **-9.251,1R** (metode lama) menjadi untung bersih **+$1.842,3R (PF 1.34)**.
   * Memasukkan `NZDCAD`, `NZDCHF`, `NZDUSD`, `GBPNZD`, `AUDNZD`, `EURNZD` ke `SCANNER_SYMBOLS` (Universe 27 pasang).
4. **Cross-Pair Asymmetric Dispersion Discovery**:
   * Analisis 19.765 snapshot multi-pair: 83.25% waktu pasar tersebar di berbagai fase berbeda, menjamin peluang trading harian konsisten sebesar **93.3%**.
5. **Dokumentasi Riset & Test Suite 100% PASS**:
   * Hasil riset tersimpan lengkap di `docs/research/RESEARCH_4_LAYER_PERMISSION_AND_NZD_BENCHMARK.md`.
   * Seluruh test suite (23 unit tests) lulus 100% OK.

---

## 16. Pembaruan 28 Agustus 2026 (Larut Malam) — Eliminasi NY ADR Reversal & Integrasi M3 (M6) HTF Weekly Wall Reversal

1. **Eliminasi Total Mechanism 3 Lama (`NY_ADR_REVERSAL`)**:
   * Backtest 16.2 tahun MetaQuotes H1 (71.831 trade) mengungkap bahwa fading 75% ADR di sesi New York menghasilkan rugi bersih **-3.637,3R (PF 0.93)** akibat *institutional steamroller effect* saat rilis berita ekonomi AS.
   * Mekanisme ini dihapus 100% dari arsitektur live `market_scanner.py`.
2. **Implementasi Mechanism 3 Baru: `HTF_WEEKLY_WALL_REVERSAL` (M6)**:
   * Memanfaatkan tabrak dinding *Previous Week High/Low (PWH/PWL)* dengan *Rejection Wick $\ge 25\%$* di H1.
   * Target Take Profit dijangkar secara objektif ke **Weekly 50% Equilibrium (Pijakan Keseimbangan)** atau Order Block terdekat, dengan SL di balik sumbu PWH/PWL ($0.35\times\text{ATR} + \text{Spread} + 20\text{ pts}$).
   * Backtest 16.2 tahun membuktikan strategi ini menghasilkan **+$586,1R$ (PF 1.05 – 1.23)** pada cluster pair alpha (`EURCHF`, `AUDCHF`, `GBPCAD`, `CADCHF`, `AUDUSD`, `EURUSD`, `USDJPY`).
3. **Sinkronisasi 4 Mekanisme Produksi di `market_scanner.py`**:
   * **M1**: `LONDON_JUDAS_SWEEP` (Asian High/Low sweep $\ge 20\%$ wick).
   * **M2**: `TREND_ALIGNED_PULLBACK` (4-Layer FSM + Delayed Limit Retest $0.20\times\text{ATR}$).
   * **M3**: `HTF_WEEKLY_WALL_REVERSAL` (Tabrak Dinding HTF $\rightarrow$ Pijakan 50% Equilibrium).
   * **M4**: `MULTI_TOUCH_BREAKOUT_RETEST` (Breakout Retest $\ge 2\times$ touches).
4. **Master Quant Dossier 16.2 Tahun & Overhaul `report.html`**:
   * Dokumen riset teknikal tersimpan di [`docs/research/METAQUOTES_16YEAR_MASTER_BACKTEST_REPORT.md`](file:///c:/Vibe/tradingpartner/docs/research/METAQUOTES_16YEAR_MASTER_BACKTEST_REPORT.md).
   * Web report 20 Bab diperbarui di [`report.html`](file:///c:/Vibe/tradingpartner/report.html).
   * Unit test suite lulus 100% OK (23/23 tests pass).

---

## 17. Pembaruan 29 Agustus 2026 (Sesi Siang) — Pure Quant Hierarchical Macro Strategic Engine (MSE) & Atlas DNA Station Delivery

1. **Pure Quant Hierarchical Top-Down Macro Strategic Engine (`src/analytics/macro_strategic_engine.py`)**:
   * Integrasi 6 timeframe asli MT5 (`MN1` 50 bar, `W1` 100 bar, `D1` 350 bar, `H4` 400 bar, `H1` 250 bar, `M30` 200 bar).
   * Komputasi matematis sub-detik ($<50\text{ ms per pair}$, 0 Token LLM).
   * Menghasilkan direktif koridor institusional (`HUNT_SELL_AT_SBR`, `HUNT_BUY_AT_RBS`) dan daftar jebakan visual (`forbidden_traps`).
2. **Atlas DNA Dual-Grid Station Calculator (`src/indicators/atlas_dna.py`)**:
   * **Major Stations (100-Pip Grid / $10.00 Gold)**: Angka bulat institusional.
   * **Sub-Stations (50-Pip Grid / $5.00 Gold)**: Koridor pergerakan harga intraday.
   * **Formula Intraday SL/TP Anchoring**: Menjangkar SL di balik support/resistance fisik $+ 0.35\times\text{ATR}$ Anti-Wick Buffer dan mengunci Safety Ceiling ($\le 16.0\text{ pips}$ / 160 pts).
3. **Telegram Command `/macro <symbol>` (`src/core/telegram_bot.py`)**:
   * Menyediakan laporan on-demand status koridor makro, station ladder, zona SBR/RBS, dan rekomendasi eksekusi per pair secara visual di chat Telegram.

---

## 18. Pembaruan 29 Agustus 2026 (Sesi Malam) — Universal 8-Currency Basket Circuit Breaker & Live E2E 3-LLM Jury Replay

1. **Universal 8-Currency Basket Circuit Breaker (`src/analytics/currency_strength.py` & `config.py` / `.env`)**:
   * Generalisasi perlindungan sirkuit ke seluruh 8 mata uang utama (`USD, EUR, GBP, JPY, CHF, AUD, CAD, NZD`).
   * Dual-Horizon Basket Flow weighting: 60% kecepatan sesi M15 (16 bar) + 40% jangkar tren H1 (24 bar).
   * **Kalibrasi Threshold Empiris**:
     - `SYSTEMIC_BASKET_USD_THRESHOLD = 2.0` (20.0 pts Boitoki).
     - `SYSTEMIC_BASKET_JPY_THRESHOLD = 2.0` (20.0 pts Boitoki).
     - `SYSTEMIC_BASKET_CROSS_THRESHOLD = 2.0` (20.0 pts Boitoki).
     - `SYSTEMIC_BASKET_SPREAD_THRESHOLD = 1.8` (18.0 pts Boitoki Relative Delta Spread).
   * Otomatis mengunci (Hard Lock) order counter-flow saat Base/Quote mengalami systemic dump/surge atau selisih kekuatan melebihi toleransi.
2. **Directional Hard Gate di Stage 1 Radar (`src/analytics/market_scanner.py`)**:
   * Menolak kandidat setup yang dilarang oleh MSE Directive atau Basket Gate sebelum pemanggilan LLM Jury (hemat 100% token).
3. **End-to-End Live Multi-LLM Replay Validation (27–28 Agustus 2026)**:
   * Validasi audit 3-LLM Jury (OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4-Flash CRO) pada 11 pair live account.
   * **Hasil Finansial**:
     - `GBPUSD` berbalik dari loss -$82.69 (akun riil) menjadi **+$135.00 (+2.25 R, 3/3 Win)** via SELL Pullbacks.
     - `EURUSD`: +2.00 R (+$120.00), `GBPCHF`: +2.15 R (+$129.00), `EURCHF`: +0.30 R (+$18.00).
     - **Net Return Terverifikasi**: **+2.85 R (+$171.00 pada equity $6,000)** dengan Win Rate 58.8%.
4. **Master Report HTML Bab 21**:
   * Web report `report.html` diperbarui dengan Bab 21 (Universal 8-Currency Basket & Pure Quant MSE Corridor Engine).
   * Seluruh unit test suite lulus **100% OK (44/44 Tests Pass)**.

---

## 19. Pembaruan 30 Agustus 2026 — Eliminasi Permanen XAUUSD (Gold) & Transisi Portofolio Murni 26 FX Universe

1. **Audit Riil 788 Deals Akun Live (`VTMarkets-Live 3`, Login `27556325`)**:
   * Audit menemukan sumber utama drawdown dari modal awal $\$6,500$ ke $\$5,819$ ($-\$681$ loss) adalah **$100\%$ disebabkan oleh Gold (`XAUUSD-ECNc`) yang menyumbang kerugian sebesar $-\$1,067.79$**.
   * Sebaliknya, seluruh portofolio 26 pasangan mata uang (**FX Majors & Yen Crosses**) membukukan net profit gabungan **$+\$387.08$** (`CADJPY` +$98.02, `USDCAD` +$63.86, `AUDJPY` +$43.88, `EURAUD` +$41.96, `EURJPY` +$41.45).
2. **Penghapusan Total & Permanen `XAUUSD-ECNc`**:
   * `XAUUSD-ECNc` dihapus $100\%$ dari `SCANNER_SYMBOLS` di `.env` dan `ALL_SCANNER_SYMBOLS` di `config.py`.
   * Scanner universe kini murni terdiri dari **26 FX Majors & Crosses Terkurasi**.
3. **Penyelarasan Seluruh Stack & Antarmuka**:
   * **CLI Theme**: Banner terminal diperbarui menjadi `[26-PAIR PRO]`.
   * **Telegram Controller (`telegram_bot.py`)**: Menu keyboard diperbarui menggantikan tombol Gold dengan `EURJPY H1` dan `CADJPY H1` serta label `[ SMC Radar 26 Pairs ]`.
   * **Unit Tests**: [`tests/test_symbol_rotation.py`](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/tests/test_symbol_rotation.py) diperbarui dengan `assertNotIn("XAUUSD-ECNc")` — seluruh **44/44 Unit Tests (100%) LULUS**.
   * **MQL5 EA Reference**: Diberi nama institusional `mql5/XAU_Institutional_SMC_EA.mq5` dengan kalkulasi komisi dinamis 1:1 dari `position_manager.py`.

---

## 20. Pembaruan 30 Agustus 2026 (Sesi Malam) — Probabilistic Macro Strategic Engine (MSE) & 5-Tier Operational Action Matrix

1. **Pemisahan Peran Arsitektural MSE vs SMC vs FRVP**:
   - **MSE (`macro_strategic_engine.py`)**: Bertanggung jawab atas arah makro, koridor, level invalidasi, dan continuous `macro_bias_score` ($\in [-1.0, +1.0]$). Dilengkapi `Smart 60-Second TTL Cache` untuk data intraday $\le\text{H4}$.
   - **SMC (`lux_smc.py`)**: Bertanggung jawab mendeteksi titik trigger (Judas Swing Failure, Liquidity Sweep, Order Block / FVG mitigation).
   - **FRVP (`volume_profile.py`)**: Bertindak sebagai *Auction Disambiguator* (`ACCEPTANCE` jika harga di Value Area / POC vs `REJECTION` di Low Volume Node / LVN single prints) + *Thin-Volume Danger* (cap rating di Grade B jika berada di LVN vacuum).

2. **5-Tier Operational Action Matrix & End-to-End Risk Engine Integration (`market_scanner.py`, `risk_engine.py`, `consensus.py`, `main.py`)**:
   - 🟢 `FULL_ALLOW`: Setup searah ekspansi makro ($|\text{score}| \ge 0.35$), eksekusi standar $100\%$ lot dengan target penuh koridor (TP1 + TP2 runner). Jika 3 AI unanimous $\ge 75\%$, membuka 2 tiket @ $0.625\times\text{Base Lot}$ (+25% boost).
   - 🟡 `REDUCED_CONFIDENCE`: Setup valid pada makro netral/transisi ($-0.25 \le \text{score} \le +0.35$). Di `risk_engine.py`, lot otomatis dipangkas **$0.75\times$ lot size** (pemotongan risiko 25%) dan di `consensus.py`, target TP2 dibatasi $\le 2.00 \times \text{SL}$.
   - 🟠 `TP1_ONLY_SCALP`: Setup counter-trend berkualitas tinggi (M1 Judas Sweep / SFP) melawan tren moderat ($|\text{score}| \le 0.70$). Wajib sweep bersih + reclaim + wick $\ge 35\%$ + ruang ke TP1 $\ge 1.25\times\text{SL}$ + zero hard trap. Di `consensus.py`, TP dikunci ketat $\le 1.50 \times \text{SL}$ dan di `main.py`, **fitur 2-posisi split dimatikan** (`num_positions = 1` ditutup 100% di TP1 tunggal).
   - 🔵 `WATCH_ONLY`: Harga di dalam Reload Zone namun trigger belum terkonfirmasi $\rightarrow$ monitor saja, 0 order MT5.
   - 🔴 `HARD_BLOCK`: Tabrak hard trap struktural, jebol invalidasi makro, atau waterfall 25-candle M5 $\rightarrow$ hard lock mutlak (0 token LLM).

3. **Injeksi ke Stage 2 LLM Dossier, Direct Fast Telegram & UI (`llm_client.py`, `cli_theme.py`, `telegram_bot.py`)**:
   - Dossier prompt LLM menyajikan `Macro Probabilistic Score`, `Action Tier`, `Regime Stability`, dan `Contingency Target`.
   - Telegram command `/macro` menyajikan output murni Python Pure Quant MSE secara instan (<100ms, 0 token API) tanpa latensi OpenAI.
   - CLI Bento Card dan Telegram alerts menampilkan lencana Action Tier dan Macro Bias Score terkalibrasi.
   - Seluruh test suite lulus **100% OK (44/44 Tests Pass)**.
