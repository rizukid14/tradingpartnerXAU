# AGENTS.md — Trading Partner Repository Guide

Dokumen ini berisi panduan lokasi file aktif, tempat log, dan struktur branch untuk navigasi cepat AI & Developer.

---

## 📌 1. Lokasi Log & State Aktif (PENTING)

* **Log Utama Aktif**: `c:\Vibe\tradingpartner\data\trading_bot.log`
  *(Semua output konsol `main.py` disimpan secara otomatis di file ini).*
* **Data Memory & Cache (di folder `/data`)**:
  - `data/risk_state.json`: State consecutive loss & recovery mode.
  - `data/decision_memory.json`: Histori keputusan AI per candle.
  - `data/dynamic_rules.json`: Aturan dinamis hasil evaluasi performa.
  - `data/forecast_cache.json`: Cache proyeksi multi-horizon.
  - `data/position_manager_state.json`: State tracking BEP, trailing, & partial close.

---

## 📁 2. File-File Utama & Navigasi Kode

* **`main.py`**: Entry point utama penggerak loop bot trading (setiap penutupan candle M5).
* **`config.py`**: Pusat konfigurasi parameter (model AI, symbol, timeframe, SL/TP ATR, risk %, session WIB).
* **`.env`**: File kredensial (API Keys OpenAI, Gemini, DeepSeek, MT5 Login/Server/Mode Demo vs Live, Telegram).
* **`src/core/llm_client.py`**: Handler pemanggilan LLM (OpenAI `gpt-5.4-mini`, Gemini `gemini-2.5-flash-lite`, DeepSeek `deepseek-v4-flash`).
* **`src/core/mt5_connector.py`**: Connector MetaTrader 5 (eksekusi order, rounding `digits`, slice comment `[:25]`, auto-resolve symbol `XAUUSD-ECN` vs `XAUUSD-ECNc`).
* **`src/core/risk_engine.py`**: Engine manajemen risiko (dynamic 1.5% equity risk sizing, recovery mode, max daily loss).
* **`src/core/telegram_alerts.py`**: Alert Telegram & batching recap kegagalan order.
* **`src/core/cli_theme.py`**: Visualisasi banner CLI (Gold & Pure White Theme untuk Branch Legacy).

---

## 📜 4. ATURAN KHUSUS BRANCH `legacy` (GOLD M5 ULTRA-FAST SCALPER)

### A. AI Setup & Speed Mode
* **3 Model Aktif**: OpenAI (`gpt-5.4-mini`), Gemini (`gemini-2.5-flash-lite`), DeepSeek (`deepseek-v4-flash`).
* **Non-Reasoning Fast Mode**: Semua model dipanggil tanpa penundaan reasoning (`reasoning_effort="none"`).
* **Single-Pass Ultra-Fast (~1.0s)**:
  * `DEBATE_ENABLED = False` (Tanpa ronde debate yang memakan waktu).
  * `MTF_ANALYSIS_ENABLED = False` & `FUNDAMENTAL_ANALYSIS_ENABLED = False` (Tanpa delay analisa latar belakang).

### B. Arsitektur Prompt Ultra-Lean M5
* **10 M5 Candles**: Menampilkan detail Open, High, Low, Close, Volume, RSI(14), EMA20, EMA50.
* **50-Bar Range Summary**: Ringkasan High & Low 50-bar M5 beserta persentase posisi harga live.
* **Tanpa Lessons/Memory Trauma**: `lessons_str` dihapus total agar AI mengevaluasi setiap candle 100% *fresh* tanpa bias rugi masa lalu.
* **Tanpa Rule Berita**: Pembatasan jam berita dihapus agar murni berfokus pada momentum & *price action* teknikal M5.
* **STRICT NO-HOLD MANDATE**: Opsi `HOLD` dihapus total dari prompt. Setiap AI diwajibkan memilih arah aktif: **`BUY` atau `SELL`**. Dengan 3 AI dan 2 opsi, konsensus 2/3 atau 3/3 dijamin 100% selalu tercapai di setiap candle M5.

### C. Risk Management & Lot Sizing
* **Dynamic 1.5% Equity Risk Sizing**: Ukuran lot dihitung otomatis berdasarkan nominal 1.5% equity modal dibagi jarak `sl_points` dari AI:
  $$\text{Lot Size} = \frac{\text{Equity} \times 1.5\%}{\text{SL Points} \times \text{Tick Value}}$$
* **Max Open Positions**: Maksimal 6 posisi simultan (`MAX_OPEN_POSITIONS = 6`).
* **Layering 3/3 Unanimous**: Jika ketiga AI sepakat (3/3), bot membuka **2 layer posisi sekaligus** (Posisi #1 TP Standar + Posisi #2 TP 1.2x) dengan total risk tetap 1.5%.

### D. Eksekusi MT5 & Proteksi M1 Micro Scalper
* **Auto-Resolve Symbol**: Otomatis mendeteksi `XAUUSD-ECN` (Demo) vs `XAUUSD-ECNc` (Live).
* **Order Guard**: Pembulatan harga SL/TP ke `symbol_info.digits` dan pemotongan string `comment` maksimal **25 karakter** (`[:25]`) untuk mencegah retcode MT5 `10013`.
* **Tight SL/TP Bounds**: SL ketat 80–150 pts ($0.80–$1.50) & TP ketat 120–250 pts ($1.20–$2.50) untuk eksekusi kilat.
* **Trailing Stop Disabled**: `TRAILING_STOP_ENABLED = False` (Ditinggalkan untuk eksekusi murni kilat murni hit TP atau SL tanpa pemotongan profit premature).
* **Break-Even (BEP)**: Geser SL ke entry (+10 pts) setelah profit +300 pts.
* **Partial Close**: Menutup 50% lot di TP1 (+400 pts).
* **Post-Mortem Evaluator Disabled**: Evaluator trade ditutup dinonaktifkan di loop utama agar siklus tetap 100% cepat & independen.
* **Telegram Failure Recap**: Kegagalan order MT5 direkap secara batch per siklus dan dikirim dalam 1 pesan Telegram berisi parameter lengkap untuk eksekusi manual.
* **CLI Visual**: Tema **Gold & Pure White** (`src/core/cli_theme.py`).

---

## 🌿 5. Peta Branch Repository

1. **`legacy`** (Branch Aktif Saat Ini):
   - **Fokus**: Scalping Emas (`XAUUSD-ECN` / `XAUUSD-ECNc`) Timeframe M5.
   - **AI Setup**: 3 Model (`gpt-5.4-mini`, `gemini-2.5-flash-lite`, `deepseek-v4-flash`) non-reasoning single-pass ~1.0s.
   - **Tampilan**: CLI Theme **Gold & Pure White** (`[GOLD] BOT TRADING`).
   - **Risk**: Dynamic 1.5% Equity Risk Sizing, STRICT NO-HOLD Mandate.

2. **`feature/forex-pairs`**:
   - **Fokus**: Rotasi 8 Pair Forex (H1) + Emas M30.
   - **AI Setup**: Dual Mode (OpenAI + Gemini) jam biasa, Triple Mode jam News.

3. **`legacy-2`**:
   - **Fokus**: Emas M5 dengan Prompt Caching 2-block structure & pemisahan keputusan entry vs posisi.

4. **`legacy-3`**:
   - **Fokus**: Emas M5 + Rotasi BTC M30, Fibonacci Retracement, & forecast horizon T+5m.

5. **`feature/m1-micro-scalper`** (Branch M1 SuperScalper Active):
   - **Fokus**: Scalping Emas Micro M1/M5 (`XAUUSD-ECN` / `XAUUSD-ECNc`).
   - **Mega Lot Jumbo**: SL Super Ketat 30–60 pts ($0.30–$0.60) -> Lot ~0.25–0.40 per $1.000.
   - **Mega Fast TP**: TP Super Kilat 40–80 pts ($0.40–$0.80, R:R 1:1.15+).
   - **Log File**: `data/trading_bot_m1_scalper.log`.

---

## 📜 6. ATURAN & RENCANA PRODUCTION BRANCH `feature/m1-micro-scalper`

### A. Rencana Eksekusi Production (Live Account)
* **Dedicated Account**: Bot versi ini disiapkan khusus untuk akun **ECNc** terpisah (`XAUUSD-ECNc`).
* **Jam Operasional Terbatas**: Hanya aktif pada **2 Jam Prime Overlap London-NY** (misal `19:30 – 21:30 WIB`). Pada jam ini likuiditas tertinggi, spread ECN tertipis (5-10 pts), dan momentum micro M1 paling bersih.
* **Target & Max Loss Harian (Rekomendasi)**:
  * Target Profit Harian: `+$80 – +$100 USD` (+8% – +10% Equity).
  * Max Loss Harian: `-$45 – -$60 USD` (-4.5% – -6% Equity).

### B. Spesifikasi Technical Execution
* **Super-Tight SL Bounds**: SL 30–60 points ($0.30–$0.60 pergerakan Emas).
* **Super-Fast TP Bounds**: TP 40–80 points ($0.40–$0.80 pergerakan Emas, R:R 1:1.15+).
* **Mega Lot Jumbo Sizing**: Dynamic 1.5% Equity Risk otomatis menghasilkan **~0.25 s.d 0.40 Lot Mega Jumbo** per $1.000 modal.
* **Real-time Closed Tracker (5s)**: Deteksi tertutupnya posisi (Hit TP/SL/Close Manual) terjadi setiap 5 detik dengan notifikasi instan CLI & Telegram.
* **1-Hour Telegram Recap**: Notifikasi rekap P/L harian & win rate dikirim otomatis setiap 1 jam.
* **Log Terisolasi**: Log disimpan di `data/trading_bot_m1_scalper.log`.
