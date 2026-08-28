# AGENTS.md — Konteks Proyek Trading Bot

> Ringkasan cepat untuk sesi coding. Baca ini dulu sebelum ngapa-ngapain.

## ⚠️ ATURAN WAJIB AI AGENT (MANDATORY AGENT RULES)
 
1. **SELALU MINTA KONFIRMASI SEBELUM MENGUBAH KODE (ALWAYS ASK BEFORE EDITING CODE)**:
   - Sebelum melakukan edit/perubahan file kode apa pun, AI WAJIB menjelaskan masalah dan menampilkan rencana/perubahan yang diusulkan.
   - AI DILARANG mengeksekusi tool edit file (`replace_file_content`, `write_to_file`, `multi_replace_file_content`) sebelum pengguna memberikan persetujuan/konfirmasi eksplisit.

2. **`.env` ADALAH SINGLE SOURCE OF TRUTH UNTUK KONFIGURASI (CONFIGURATION OVERRIDE)**:
   - File `.env` SELALU me-*override* nilai default di `config.py` via `load_dotenv()`.
   - Jika mengubah parameter konfigurasi/fitur (enable/disable fitur, jam operasi, threshold, risk), AI WAJIB mengecek dan mengubah langsung file `.env` di samping `config.py`. Mengubah `config.py` saja tanpa menyelaraskan `.env` adalah KESALAHAN FATAL karena `.env` yang akan dimuat saat bot berjalan.

3. **KONVERSI WAKTU SERVER MT5 KE WIB (SERVER TIME + 4 JAM = WIB)**:
   - Server MT5 (`VTMarkets-Live 3`) beroperasi di zona **GMT+3**.
   - **Waktu WIB (GMT+7) = Jam Server MT5 + 4 Jam**.
   - **Pergantian Hari / Daily Rollover (00:00 Server) = TEPAT JAM 04:00 WIB**.
   - Jendela bahaya lonjakan spread rollover dan *liquidity gap* terjadi di **03:55 – 04:15 WIB** (00:00 server). AI DILARANG keras salah menghitung waktu rollover sebagai jam 05:00 atau jam 07:00.

4. **ANALISIS DAMPAK HOLISTIK & PENYELARASAN MENYELURUH (ZERO HALF-BAKED CHANGES)**:
   - Setiap kali melakukan perubahan besar (timeframe, rotasi pool pair, jam sesi, SL/TP rules, model AI, atau risk gate), AI WAJIB memikirkan dan memeriksa SEMUA file yang terdampak secara holistik dalam 1 kali jalan tanpa menunggu diminta satu per satu.
   - **INTEGRITAS IMPORT & SINTAKS (ZERO MISSING IMPORTS / ZERO NAME_ERROR)**:
     - AI WAJIB memastikan semua library (`datetime`, `ZoneInfo`, `os`, `sys`, `json`, dll), konstanta, dan helper module internal ter-import dengan sempurna di bagian atas file yang diedit.
     - DILARANG menggunakan variabel/konstanta tanpa deklarasi atau import eksplisit (mencegah `NameError` saat runtime).
   - **Daftar Checklist 8 File Wajib Diperiksa & Diselaraskan Setiap Ada Perubahan**:
     1. **`config.py` & `.env`**: Parameter konfigurasi, default fallback, helpers per-simbol (`get_timeframe`, `lot_size_for`, `risk_percent_for`, `get_higher_timeframes`), dan import `ZoneInfo`/`datetime`.
     2. **`src/core/llm_client.py`**: Prompt AI, deteksi label timeframe (`tf_label`), jumlah candle intra-period (`num_micro_send`), format JSON output, ringkasan momentum mikro, dan variabel lokal candle.
     3. **`src/core/cli_theme.py` & `main.py`**: Banner utama terminal, dynamic status clock line (`[POOL 4 PAIRS (H1) | HH:MM:SS]`), dan log range candle.
     4. **`src/core/telegram_bot.py` & `telegram_alerts.py`**: Label tombol menu keyboard (`GBPUSD H1/M30`), command on-demand (`/analisa`, `/scan`, `/status`), dan pesan alert.
     5. **`src/analytics/macro_analyst.py`**: Hirarki timeframe MTF (`H1`, `H4`, `D1`), key levels caching, dan background analysis.
     6. **`src/core/risk_engine.py` & `position_manager.py`**: Filter spread, dead zone, ATR-based safety floor, time-decay stagnation, dan pre-rollover shield.
     7. **`tests/test_*.py`**: Unit test suite (`test_symbol_rotation.py`, `test_time_decay_and_vol_regime.py`, `test_macro.py`) wajib diupdate dan dipastikan **100% PASS**.
     8. **`docs/archive/CHANGELOG_AUGUST_2026.md` & `AGENTS.md`**: Pencatatan changelog detail dan sinkronisasi ringkasan arsitektur.
5. **GAYA KOMUNIKASI & VERIFIKASI FAKTUAL (COMMUNICATION STYLE & ZERO FLATTERY)**:
   - Dilarang membuka respon dengan frasa validasi basi seperti *"Kamu benar 100%"*, *"Pertanyaan bagus"*, *"Kekhawatiranmu sangat tepat"*, dll.
   - Jangan membenarkan asumsi pengguna sebelum melakukan verifikasi langsung ke kode atau log data. Jika belum diverifikasi, katakan belum diverifikasi.
   - Lewati kalimat pembuka persetujuan/basa-basi. Langsung jawab substansi teknikal terlebih dahulu.
   - Sebelum menyetujui klaim, periksa faktanya di kode/data riil. Jika tidak bisa diverifikasi, sebutkan secara lugas.
   - Jika asumsi pengguna keliru atau hanya benar sebagian, katakan langsung apa adanya dan jelaskan alasannya tanpa perlu melembutkan dengan pujian.
---

## Apa ini

Bot trading **multi-LLM consensus** (OpenAI + Gemini + Claude/DeepSeek) yang berjalan di **MetaTrader 5**.
- **TRADING_MODE = "pairs" (Default)**: **Pool 4 simbol FX paralel**: `WEEKDAY_SYMBOL = "GBPUSD-ECNc"` + 3 FX pairs (`GBPCHF-ECNc`, `USDJPY-ECNc`, `AUDCAD-ECNc`). **Dynamic Session-Adaptive Timeframe**: **H1 di Sesi Tokyo (08:00–14:00 WIB)** untuk menyaring noise + **M30 di Sesi London/NY (14:00–00:00 WIB)** untuk menangkap momentum breakout lincah. Risk per trade: **1.0%**. Net currency exposure seimbang (GBP×2, USD×2, CAD×1, CHF×1, AUD×1, JPY×1).
- **BTCUSD.c (Bitcoin)**: Intraday **M30 (24/7)**, risk: **1.5%**, aktif di weekend + setelah jam 22:00 Jumat WIB (`ENABLE_BTC_ROTATION`). Bebas swap overnight.
- **XAUUSD-ECNc (Gold)**: Sesi adaptif **H1 Tokyo / M30 London-NY**, risk: **1.0%** (aktif saat mode `xau`).
- **Smart Timeframe Rotation**: AI dipanggil per-simbol HANYA pas candle timeframe aktif berganti (`_symbol_last_candle` di `main.py`) — H1 tiap 60 menit saat pagi, M30 tiap 30 menit saat sore/malam (hemat token drastis ~92%).
- **Akun**: **LIVE** `VTMarkets-Live 3` (login `27556325`), Balance ~$6000, Waktu **WIB** (Asia/Jakarta).

---

## Cara jalanin

```bash
python main.py
```
- `config.DRY_RUN = False` $\rightarrow$ **LIVE trading** (order beneran dikirim). Jangan ubah tanpa izin user.
- **Ganti mode trading**: `.env` `TRADING_MODE=pairs` / `TRADING_MODE=xau`, atau via UI dashboard $\rightarrow$ restart bot biar apply.
- Log: `data/trading_bot.log` (auto-rotate 2MB, keep 5000 baris). Log ini campur sesi demo lama + live baru; verifikasi akurat dilakukan dengan query MT5 langsung.

---

## Arsitektur file

| File | Fungsi |
|---|---|
| `main.py` | Loop utama: manage posisi tiap 3 detik, full cycle tiap candle per-simbol dengan **Smart Timeframe Rotation** |
| `config.py` | Parameter konfigurasi global + helper per-simbol (`lot_size_for`, `risk_percent_for`, `default_sl/tp`, dll) |
| `src/core/llm_client.py` | Build prompt dinamis per-simbol + pemanggilan LLM paralel sesuai jadwal **Time-Based AI Mode** |
| `src/core/consensus.py` | **Weighted confidence consensus** (skor $\ge$ threshold, min 2 model) + filter safety floor + AI re-evaluator CLOSE |
| `src/core/risk_engine.py` | Filter spread, daily loss ($50), daily profit target 6%, dead zone 02:00-06:00 WIB, recovery mode, risk lot sizing |
| `src/core/mt5_connector.py` | Order send/close, history deals, market data MT5, magic filter |
| `src/core/economic_calendar.py` | Dynamic fetch kalender ekonomi (TradingView/Investing.com) + anti-FOMC/news context |
| `src/core/telegram_bot.py` | 2-Way Interactive Telegram Controller (On-demand 3-AI analysis, position manager, status command via POST fast-polling) |
| `src/analytics/position_manager.py` | Global Break-Even (58% TP + komisi), Trailing Stop (70% TP, konstan 0.5×ATR), evaluasi posisi |
| `src/analytics/macro_analyst.py` | Fundamental + MTF context per-simbol (H4/D1, EMA200, slope EMA50), cache berlaci per-simbol |
| `src/analytics/trade_evaluator.py` | Post-mortem evaluasi trade tertutup $\rightarrow$ lessons (`data/memory_lessons.json`) |
| `src/analytics/decision_memory.py` | Tracking hasil & 6 keputusan terakhir per-simbol |

---

## Alur cycle (`main.py` $\rightarrow$ `run_trading_cycle`)

0. **Time-Based AI Mode (WIB)**: 
   - **00:00–18:59 = Dual** (OpenAI o4-mini + Gemini 3.1-flash-lite — Dead Zone 02:00-06:00 auto-skip).
   - **19:00–22:00 = Triple** (OpenAI o4-mini + Gemini 3.1-flash-lite + DeepSeek V4 Flash / Claude — overlap London-NY).
   - **22:01–23:59 = Dual** (OpenAI o4-mini + Gemini 3.1-flash-lite — Late NY).
1. `risk.can_trade()` — filter spread/sesi/daily loss/profit target. Gagal $\rightarrow$ skip (0 token).
2. Ambil data 100 closed bars + tick live + indikator ADX(14), ATR, EMA, Fib 50/100-bar.
3. Sinkronisasi deal tertutup + update post-mortem lessons.
4. **Panggil LLM paralel sesuai Time-Based AI Mode**.
5. **Weighted Consensus Engine**: skor $\Sigma$ confidence $\ge$ threshold (FX/XAU/BTC **1.2**; defensif $\times 1.5$) + eksekusi rekomendasi CLOSE dari AI Re-evaluator.
6. Forecast context (bias/target) bersifat murni *informational* (tidak memblokir eksekusi).
7. **Risk-based lot sizing**: lot dihitung dari equity & SL (FX 1.0%, BTC 1.5%, XAU 1.0%).
8. Cek kapasitas max posisi (aggregate pool 6 posisi), lalu eksekusi order MT5.

---

## Gate eksekusi aktif (Hard Rules)

- **Weighted Consensus**: $\ge 2$ model searah, skor confidence $\ge$ threshold per-simbol (FX/XAU/BTC **1.2**).
- **Aturan SL/TP (`config.sltp_mode_for(symbol)`)**:
  - **FX Pairs = Mode LLM**: SL/TP murni struktur teknikal LLM, dibatasi **Safety Floor** $\max(2\times \text{spread}, 50\text{ pts})$ + **Gate R:R minimum 1.25:1** (TP dinaikkan otomatis jika R:R < 1.25).
  - **BTC & XAU = Mode ATR-Based**: Gate ATR non-negotiable (R:R 2:1 fix).
- **Spread Filter**: FX = ATR-based $\max(15\% \times \text{ATR H1 pts}, 20\text{ pts floor})$; XAU $\le 50$ pts; BTC $\le 2400$ pts.
- **Dead Zone**: 00:00–08:00 WIB (Trading aktif mulai 08:00 WIB untuk FX & XAU; BTC tetap aktif 24/7).
- **Proteksi Akun**: Max daily loss 4% equity, max 5 consecutive loss, daily profit target 6% equity, max 6 total open posisi bot (shared pool), max 4 active pending orders (shared pool).
- **Proteksi Posisi Real-Time (`position_manager.py`)**:
  - **Break-Even (BEP)**: Aktif di **45%–55% TP** + padding komisi round-trip + Pocket Profit 1.5 pips (15 pts).
  - **Partial Close (TP1)**: Aktif di **45%–55% TP**, mencairkan 50% lot ke saldo balance + geser sisa posisi ke Risk-Free BEP.
  - **2-Stage Dynamic Trailing Stop**:
    * **Stage 1 (Swing Breathing: 65% s/d < 90% TP)**: Mengacu ke **ATR H1 ($0.75\times\text{ATR H1}$)** dengan floor absolut 80 pts (8 pips) untuk memberikan ruang ayun longgar dari noise wick saat menuju TP2.
    * **Stage 2 (Terminal Lock: $\ge$ 90% TP)**: Otomatis mengencang (*tightening*) ke **ATR M30 ($0.50\times\text{ATR M30}$)** dengan floor 30 pts (3 pips) untuk mengunci cuan 90% secara rapat di pucuk sebelum terjadi pembalikan harga mendadak.
  - **Peak-Aware Time-Decay Stagnation Exit**: Posisi $\ge 4$ jam hold (8 bar M30) di rentang $[-0.20R, +0.20R]$ ditutup jika Peak MFE $< +0.30R$.
  - **Pre-Rollover Precision Distance-to-SL Shield (03:50–04:15 WIB)**: Menutup posisi secara bersih di jam 03:50 WIB JIKA sisa jarak fisik ke SL $\le$ threshold lonjakan rollover per-simbol (EURCHF/EURNZD 240 pts, GBPCHF 210 pts, GBPUSD 180 pts, USDJPY 150 pts, NZDCAD 140 pts, AUDCAD 130 pts) untuk mencegah gap down & slippage 2x SL. Posisi dengan SL aman atau profit tebal dibiarkan jalan ke TP.

---

## Status Terkini Sistem (Live Production — Agustus 2026)

1. **FX Pairs 4-Symbol Pool (M30 Intraday)**: Parallel scan 4 simbol (`GBPUSD`, `GBPCHF`, `USDJPY`, `AUDCAD`) update 25 Agu 2026 (Eliminasi NZDCAD untuk upgrade volatilitas 2x lipat dan spread super tipis di Sesi Tokyo).
2. **Trend-Aware Dual-Window Fibonacci**: Window 50-bar Intraday + 100-bar Macro Multi-Day dengan formula sadar arah tren.
3. **Dynamic Pending Orders Prompt**: Jika `PENDING_ORDERS_ENABLED = False`, blok pending rules dan field `entry_type`/`entry_price` dihilangkan 100% dari prompt (menghemat ~459 token).
4. **Paket Anti-FOMC & High-Impact News (Dynamic TradingView API)**:
   - Dynamic fetch kalender TradingView/Investing.com (cache 6 jam, filter US, GB, EU, CH, JP, AU, CA).
   - Window 6 jam sebelum & 6 jam sesudah rilis berita.
   - Conditional prompt rule: larang keras fade momentum breakout / mean-reversion counter-trend saat ada event berita.
5. **Indikator ADX(14) & Slope EMA50**: Deteksi kekuatan tren real-time + Critical Trend Filter untuk mencegah melawan tren kuat.
6. **Top-Down Attention Flow Prompt**: Urutan prompt: Macro H4/D1 $\rightarrow$ Key Levels $\rightarrow$ Technical Indicators $\rightarrow$ Structure 50/100-bar $\rightarrow$ Recent Candles $\rightarrow$ Execution Directives.
7. **2-Way Interactive Telegram Bot Controller (`src/core/telegram_bot.py`)**:
   - Menu kontrol institusional `[ ☰ Menu ]` via `setMyCommands` & inline interactive keyboard.
   - On-demand 3-AI consensus analysis trigger (`/analisa <symbol>` atau klik button pair).
   - Pemantauan akun real-time (`/status`, `/posisi`, `/scan`, `/closeall`).
   - Fast POST polling via Vercel proxy (`https://tg-proxy-vercel-eight.vercel.app`).
   - *Status task fixing*: Perlu finalisasi stabilitas penerimaan input/command background listener saat berdampingan dengan main cycle MT5.
8. **Peak-Aware Time-Decay Stagnation Exit & Pre-Rollover Precision Distance-to-SL Shield (`position_manager.py`)**:
   - Perlindungan modal dari time-decay momentum dan pelebaran spread broker saat rollover dini hari.
9. **Dynamic Volatility Scaling (ATR Percentile)**:
   - Menggantikan jam dinding statis dengan rasio volatilitas aktual vs baseline 30-hari (Low `0.75x`, Normal `1.00x`, High `1.15x`) + injeksi objektif Peak MFE ke AI Re-evaluator.
10. **Ultra-Compact Chain-of-Thought JSON Protocol (24 Agu 2026)**:
    - Mengunci urutan inferensi LLM: `trend` $\rightarrow$ `velocity` $\rightarrow$ `rr_valid` $\rightarrow$ `signal` $\rightarrow$ `confidence`.
    - Memangkas token output menjadi ~35 token dan mempercepat respons inferensi menjadi < 5 detik per simbol.
    - Menghilangkan *analysis paralysis* pada pair live dan menjaga konsensus tetap tajam & tegas.
11. **Multi-Year FBS Historical Dataset & SMC Validation (26 Agu 2026)**:
    - 88 file dataset offline riil FBS MT5 di `data/historical/fbs/` (3.788.000+ bar, 22 simbol: M30 4.6 thn, H1 10.7 thn, H4 19–55.6 thn, D1 16.6 thn).
    - Validasi 396.183 trade: H1 mengalahkan M30 sebesar **+22.8% Profit Factor** pada rentang tanggal identik 2022–2026 (hemat token 47% & kebal wick noise).
    - Arketipe *Mean Reversion* (PF 0.72) dan *SMC CHoCH/Displacement* (PF 0.81–1.00) mendominasi intraday, sedangkan *Breakout* terbukti toksik di pasar FX intraday (PF 0.20).
12. **Multi-Decade H4 & D1 Macro Expansion Discovery (1971–2026)**:
    - Gold (XAUUSD) menghasilkan **+$36.8k (PF 1.64)** di H4 (30.5 thn) dan **+$29.5k (PF 2.50)** di D1 (16.6 thn) pada strategi Donchian Breakout.
    - Menyingkap hukum fraktal: **Macro (D1/H4) Expands (Breakout/Trend)** vs **Micro (H1/M30) Mean-Reverts (Osilasi/Diskon)**.
    - Master Strategy: *Trend-Aligned Mean Reversion* (Beli di diskon H1 searah arus breakout D1/H4).
13. **Master Quant Dossier HTML (Book-Grade Report)**:
    - Tersedia di `report.html` (9 Bab lengkap, visual flow 2-stage screener, perbandingan 4 timeframe, dan atlas DNA 22 simbol).
14. **2-Stage Quant Funnel Architecture (Branch `quant-trade` — 26 Agu 2026)**:
    - **Stage 1 (Hybrid Dual-Speed Market Scanner `market_scanner.py`)**: Caching struktur makro D1/H4 (0 token) + Fast Execution Radar tiap 60 detik pada 22 pair (M1 Judas Sweep, M2 Trend Pullback, M3 NY ADR Exhaustion).
    - **Stage 2 (3-LLM Consensus Jury with High-Density Dossier Prompt)**: Dipanggil HANYA saat setup A+ terdeteksi (~4–8 call/hari). Menghemat biaya API ~85% dan menaikkan Win Rate ke 55–60% & PF > 1.40.
    - **Telegram & CLI Overhaul**: Command `/radar`, `/levels`, & `/smc` menampilkan live heat-table 22 pair, daily morning SMC briefing, dan glow matrix CLI terminal.
15. **2-Pass Sequential Cross-Examination 3-LLM Jury & Qualified Hard Risk Veto**:
    - **Pass 1 (Parallel Investigation: ~3.0s)**: `OpenAI o4-mini` (Structure) & `Gemini 3.1-Flash` (Momentum) menganalisis data candlestick live H1 & M5 secara independen.
    - **Pass 2 (Cross-Examination Audit: ~1.5s)**: `DeepSeek V4-Flash` (Devil's Advocate & Chief Risk Officer) menerima seluruh Master Dossier **PLUS** proposal & argumen tertulis dari OpenAI & Gemini, menguji kelemahan logika mereka terhadap 24 candle M5. Total waktu sidang: < 5.5 detik!
    - **Qualified Hard Risk Veto Engine**: Menolak trade otomatis jika model mengangkat bendera bahaya kritis (`COUNTER_TREND_MOMENTUM`, `HIGH_IMPACT_NEWS`, `LIQUIDITY_TRAP`, `SPREAD_SPIKE`) dengan alasan tertulis, mencegah akun terjebak *falling knife*.
16. **LuxAlgo Smart Money Concepts (SMC) & Liquidity Map Engine (`src/indicators/lux_smc.py`)**:
    - Porting murni 1:1 dari LuxAlgo TradingView Pine Script v5 ke Python: mendeteksi *Unmitigated Order Blocks (OB)*, *Fair Value Gaps (FVG)*, *Strong Low / Strong High*, dan *Equal Highs/Lows (EQH/EQL)*.
    - Diinjeksikan ke Bagian 2 Master Dossier Prompt sehingga AI menaruh Stop Loss presisi di balik Order Block/Strong Low dan Take Profit pada area magnet FVG/Weak High.
17. **Hourly SMC Radar & Market Pulse Telegram Digest (`telegram_alerts.py` & `main.py`)**:
    - Rekap otomatis berkala setiap 1 jam (pada pergantian jam WIB) yang mempublikasikan status Market Compass 22 pair (Bullish/Bearish/Sideways), Dealing Range SMC (Top Discount & Premium watch), status portofolio MT5 (floating & realized P/L), serta ringkasan aktivitas sweep 60 detik tanpa membebani kuota API token.
18. **Strict High-Timeframe Execution Hierarchy (H1 & M30 Only — Anti-Overtrading)**:
    - Stage 1 Fast Radar memindai secara ketat HANYA pada timeframe struktural **H1 & M30** (M1 London Judas Sweep, M2 Trend Pullback, M3 NY ADR Exhaustion).
    - Timeframe M5 DILARANG KERAS dijadikan trigger pembuka posisi langsung guna menyaring noise wick broker, mencegah overtrading, dan menekan fee churn.
19. **M5 Candlestick Micro-Microscope (Exclusive for Pass 2 Risk Veto Audit)**:
    - 25 candle M5 live dicadangkan secara eksklusif sebagai berkas audit mikro bagi **DeepSeek V4-Flash (Devil's Advocate & Chief Risk Officer)** untuk mendeteksi *falling knife* dan menjatuhkan Hard Risk VETO (`COUNTER_TREND_MOMENTUM`, `LIQUIDITY_TRAP`) sebelum eksekusi MT5.
20. **Unanimous 3/3 High Confidence Split (+25% Boost per Posisi)**:
    - Jika 3 AI sepakat bulat dengan rata-rata confidence $\ge 75\%$ dan tersedia $\ge 2$ slot MT5, sistem mengeksekusi 2 posisi sekaligus masing-masing @ $0.625\times$ Base Lot (Pos #1 Target Standar TP1, Pos #2 Target Extended 1.2× TP2 + Trailing Stop).
    - True Clean Arithmetic Mean diterapkan pada seluruh level konsensus dengan plafon realistis $1.25\times \le \text{TP} \le 3.0\times \text{SL}$.
21. **Multi-Touch Cluster Breakout & Delayed Retest Engine (M5 — 27 Agu 2026)**:
    - Validasi 10.7 tahun FBS (23.173 trade, PF 1.11, 21/22 pair profitable): level cluster support/resistance yang disentuh $\ge 2\times$ dan ditembus candle momentum $(\ge 55\%\text{ body})$ dieksekusi via **Pending Limit Order saat retest** (delay 3–4 bar). Dilarang keras *chase breakout* langsung guna mencegah jebakan *Judas Sweep*.
    - Integrasi modul `src/indicators/candle_quality.py` & `src/indicators/sweep_detector.py` ke dalam Fast Radar Stage 1 dan pengayaan payload 8 layer ke LLM Veto (DeepSeek CRO).
22. **Boitoki Currency Strength Matrix & Prompt Relative Flow (H1 — 27 Agu 2026)**:
    - Porting 1:1 algoritma Boitoki CSM ([`csm.txt`](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/external_repos/csm.txt)) via 7 USD Majors di MT5 (`src/analytics/currency_strength.py`).
    - Menghilangkan *Macro Bias Trap* & kebutaan *Single-Pair Silo* (mencegah false BUY saat mata uang dasar sedang di-dump secara sistemik).
    - Injeksi blok kuantitatif murni `GLOBAL CURRENCY STRENGTH MATRIX` (Ranking 8-Currency, Base/Quote Rank & Score, Net Currency Delta) ke prompt LLM agar AI menalar aliran modal secara otonom.
    - Validasi multi-tahun 21 pair FBS (31.161 trade): memotong 90% trade overtrading dan memulihkan modal $+7.333\text{R}$ (+92% kerugian terpangkas) dengan pair bintang (`EURUSD` PF 1.09, `GBPUSD` PF 1.08, `AUDJPY` PF 1.09, `EURJPY` PF 1.07).
23. **2-Stage Dynamic Trailing Stop Engine (H1 Swing Breathing vs M30 Terminal Lock — 27 Agu 2026)**:
    - Mengatasi masalah trailing stop yang terlalu mepet akibat pemakaian ATR M30 statis (hanya 3.5 pips di JPY pairs).
    - **Stage 1 (Swing Breathing: 65% s/d < 90% TP)**: Jarak $0.75\times\text{ATR H1}$ (floor FX 80 pts / 8 pips) memberi ruang nafas dari noise wick menuju TP2.
    - **Stage 2 (Terminal Lock: $\ge$ 90% TP)**: Beralih ke $0.50\times\text{ATR M30}$ (floor FX 30 pts / 3 pips) untuk mengunci cuan 90% di pucuk sebelum terjadi pembalikan harga mendadak.
24. **Fixed Range Volume Profile (FRVP) & Institutional Confluence Engine (28 Agu 2026)**:
    - Validasi kuantitatif 110.460 trade (4.3 tahun data broker MT5, 24 simbol): FRVP standalone terbukti gagal (PF 0.94–0.98), namun sinergi **SMC + FRVP** memangkas 59.2% trade noise dan melipatgandakan **Expected Value (+104% R)** serta menaikkan PF (`EURCHF` PF 1.79, `GBPCHF` PF 1.53, `XAUUSD` & `USDJPY` berbalik net profit).
    - Integrasi modul `src/indicators/volume_profile.py` ke dalam `lux_smc.py`, `market_scanner.py` Stage 1 Radar, dan Dossier Prompt LLM (`llm_client.py`).
25. **Wave State Machine & Trade Permission Engine (H1 — 28 Agu 2026)**:
    - Validasi 2.793.591 trade (2010–2026): memisahkan *Direction* (kemana arah tren makro H4/D1) dari *Trade Permission* (kapan waktu yang tepat untuk masuk H1).
    - Menghilangkan *Impulse Chase* (Phase 1, PF 0.52) dan *Early Falling Knife* (Phase 2, PF 0.97).
    - Membuka izin trading HANYA pada *Mature Basing* (Phase 3, PF 1.30) dan *Base Reclaim* (Phase 4, PF 1.42) di zona Dealing Range Discount ($\le 0.50$, Golden Pocket $\le 0.382$).
    - Seluruh model radar (M1 Judas Sweep, M2 Pullback, M3 ADR Exhaustion, M5 Multi-Touch Retest) tetap aktif dan dieksekusi eksklusif saat Trade Permission Gate bernilai `ARMED` atau `ENABLE`.
    - Asymmetric CSM Flow: Melarang BUY hanya saat terjadi *systemic dump* ($\text{Delta} \le -2.0$), membebaskan *neutral flow* saat pullback diskon yang sehat.
26. **Anti-Wick Buffer & Structural SL Anchoring (M30 — 28 Agu 2026)**:
    - Validasi kuantitatif 2.900.000 candle M30 (2018–2026, 29 instrumen): Stop Loss wajib dijangkar **di balik lantai support/order block fisik ditambah Anti-Wick Buffer $0.35\times\text{ATR} + \text{Spread}$**, bukan dihitung dari harga entri (`mid`).
    - Menghilangkan *False Wick Stop-Out* saat harga menguji lantai akumulasi/diskon, meningkatkan Win Rate Trend-Aligned Supply/Demand Retest menjadi **57.2% – 58.1% (PF 1.17 – 1.23)**.
27. **Real Candlestick Wick Measurement & Anti-Waterfall Judas Sweep Protection (28 Agu 2026)**:
    - Mengeliminasi nilai statis `rejection_wick_ratio` yang sebelumnya ter-hardcode (0.35 / 0.30) di seluruh 4 mekanisme `market_scanner.py`.
    - Mengintegrasikan helper `_evaluate_live_candle_quality` menggunakan modul `classify_candle` pada data candle live M15 & candle tertutup sebelumnya.
    - Menambahkan filter *Anti-Breakdown Waterfall* pada `LONDON_JUDAS_SWEEP`: melarang keras trigger BUY jika lilin live berupa marubozu merah tebal yang menembus level tanpa sumbu bawah, serta mewajibkan konfirmasi pembalikan fisik (*reclaim* atau *lower rejection wick* $\ge 20\%$). Mencegah false trigger saat terjadi reli/dumping mata uang ekstrem.
28. **Dynamic MT5 Point Resolution, Live Economic News & FRVP Confluence Injection (28 Agu 2026)**:
    - Mengubah `_get_point(sym)` di `market_scanner.py` agar meminta `symbol_info.point` langsung dari broker MT5 dengan fallback cerdas berbasis aset (JPY $\rightarrow 0.001$, XAU/BTC $\rightarrow 0.01$, FX $\rightarrow 0.00001$).
    - Mengaktifkan live fetch berita ekonomi via API TradingView/Investing.com di `llm_client.py` (`build_high_density_dossier_prompt`) saat menyusun dossier untuk 3-LLM Jury.
    - Menginjeksikan ringkasan Fixed Range Volume Profile (`frvp_confluence` POC/VAL/VAH) ke seluruh 8 kandidat radar di `market_scanner.py`.
    - Menghitung `risk_reward_ratio` secara dinamis dari formula matematis $|\text{TP} - \text{Trigger}| / |\text{Trigger} - \text{SL}|$.



---

## Konvensi & Catatan Operasional

- **Komunikasi**: Bahasa Indonesia (santai, lugas, teknikal).
- **Risk-Averse**: Prioritas utama adalah perlindungan modal.
- **Magic Number**: `20260625`. Bot hanya mengelola tiket dengan magic ini.
- **Git Workflow**: Branch `dev` = branch aktif utama.
- **File Disk**: Folder `data/` dan `scratch/` di-`.gitignore`. File script sementara di `scratch/` dibersihkan berkala.

---

## 📚 Indeks Dokumentasi & Riset Lengkap

Dokumentasi lengkap telah dikelompokkan ke dalam direktori tematik di [docs/README.md](file:///c:/Vibe/tradingpartner/docs/README.md):

| Kategori | Dokumen | Deskripsi Isi |
|---|---|---|
| 📊 **Research** | **[docs/research/INTRADAY_CSM_AND_DAILY_CYCLE_SPEC.md](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/docs/research/INTRADAY_CSM_AND_DAILY_CYCLE_SPEC.md)** | **Spesifikasi Intraday Market Cycle & Boitoki CSM**: Dokumen arsitektur lengkap 3 pilar: Macro Anchor D1, Boitoki CSM 7 USD Majors, Intraday Phase & 2 Exception Rules (Flow Shock & Retracement to D1 Support). |
| 📊 **Research** | **[report.html](file:///c:/Data%20%28D%29/Vibecoding/tradingpartnerXAU/report.html)** | **Master Quant Dossier (HTML Book Report)**: Laporan buku putih lengkap 9 Bab: 55 tahun dataset FBS (3.78M bar), komparasi 4 timeframe (M30–D1), 4 arketipe, atlas DNA 22 simbol, strategi *Trend-Aligned Mean Reversion*, dan arsitektur 2-Stage Screener. |
| 📊 **Research** | **[docs/research/MULTIYEAR_FBS_BACKTEST_2026.md](file:///c:/Vibe/tradingpartner/docs/research/MULTIYEAR_FBS_BACKTEST_2026.md)** | **Hasil Riset & Backtest Multi-Tahun (Dataset FBS MT5)**: Validasi 396.183 trade (10.7 thn H1, 55.6 thn H4, 16.6 thn D1). Komparasi head-to-head, evaluasi 4 arketipe, validasi SMC CHoCH/Order Block, dan ranking 22 simbol. |
| 💡 **Plans & RFC** | **[docs/plans/IDEAS_AND_PLANS.md](file:///c:/Vibe/tradingpartner/docs/plans/IDEAS_AND_PLANS.md)** | **Daftar Ide & RFC Fitur Baru**: One-Shot Emergency Drawdown Re-Evaluator (80% SL + High-Density Prompt), Refaktor Pending Consensus, Parabolic Filter, Anti-Hedge Gate, **RFC 10: Asymmetric 3-LLM Specialized Roles (Structure Analyst vs Price Action Validator vs Devil's Advocate)**. |
| 🔴 **Plans & RFC** | **[docs/plans/GLM_CRITICAL_REVIEW.md](file:///c:/Vibe/tradingpartner/docs/plans/GLM_CRITICAL_REVIEW.md)** | **GLM Critical Review — Structural Holes & Research Priorities**: 6 temuan kritis (korelasi eksposur currency, spread-to-ATR ratio, asimetri Dual/Triple consensus, swap cost, validasi momentum feature, session multiplier). Priority stack + action table. |
| 📊 **Research** | **[docs/research/QUANT_RESEARCH_EDGES.md](file:///c:/Vibe/tradingpartner/docs/research/QUANT_RESEARCH_EDGES.md)** | **Riset Statistik Bebas Bias (3–4 Tahun)**: Temuan 112 Edge Pola Bearish NY, Ranking Pair Forex, Riset CAD/EUR/GBP & JPY, Riset Donchian XAU BUY NY, Confluence. |
| 📊 **Research** | **[docs/research/DAILY_RANGE_VOLATILITY.md](file:///c:/Vibe/tradingpartner/docs/research/DAILY_RANGE_VOLATILITY.md)** | **Riset Volatilitas Harian D1 (365 hari, 29 pair)**: Mean & Median daily range pips untuk semua Major + Minor/Cross + XAUUSD. Ranking volatilitas, analisis CHF crosses di pool bot, kandidat upgrade pair. |
| 📈 **Research** | **[docs/research/backtest_augustus_2026.md](file:///c:/Vibe/tradingpartner/docs/research/backtest_augustus_2026.md)** | **Hasil Backtest Agustus 2026**: Evaluasi 10 strategi buku (NotebookLM), Erratum S9 Horn, Verifikasi S9 + Target Struktural GBPUSD. |
| 🏗️ **Architecture** | **[docs/architecture/LLM_COST_ESTIMATION.md](file:///c:/Vibe/tradingpartner/docs/architecture/LLM_COST_ESTIMATION.md)** | **Estimasi Frekuensi & Biaya LLM**: Simulasi kuota token, perbandingan opsi DeepSeek vs Claude Sonnet per bulan. |
| 🏗️ **Architecture** | **[docs/architecture/PROMPT_COMPARISON.md](file:///c:/Vibe/tradingpartner/docs/architecture/PROMPT_COMPARISON.md)** | Perbandingan skema prompt antar iterasi versi bot. |
| 🚀 **Deployment** | **[docs/deployment/vps_deployment.md](file:///c:/Vibe/tradingpartner/docs/deployment/vps_deployment.md)** | Panduan deployment production bot ke VPS. |
| 🏗️ **Architecture** | **[docs/architecture/BROKER_INFRASTRUCTURE_AND_SAFETY.md](file:///c:/Vibe/tradingpartner/docs/architecture/BROKER_INFRASTRUCTURE_AND_SAFETY.md)** | **Analisis Broker & Keamanan Dana**: Bedah VT Markets (Mauritius FSC, LD4 ECN), A-Book vs B-Book Algo, Roadmap Broker Multi-Tier (Swissquote, IBKR, Bappebti). |
| 📜 **Archive** | **[docs/archive/CHANGELOG_AUGUST_2026.md](file:///c:/Vibe/tradingpartner/docs/archive/CHANGELOG_AUGUST_2026.md)** | **Arsip Changelog Detail (8–15 Agustus 2026)**: FASE 1–7, pemisahan mode SL/TP, evolusi lot sizing, dan perbaikan historis. |
| 🗂️ **Master Index** | **[docs/README.md](file:///c:/Vibe/tradingpartner/docs/README.md)** | Indeks lengkap seluruh file dokumentasi, buku trading (PDF), dan spesifikasi. |
