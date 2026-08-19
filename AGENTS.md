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
* **STRICT CONFIDENCE THRESHOLD**: Opsi `HOLD` diperbolehkan jika kondisi pasar konsolidasi/choppy (confidence < 0.50). Sinyal `BUY` atau `SELL` hanya dieksekusi jika confidence >= 0.50.

### C. Risk Management & Lot Sizing
* **Dynamic 1.5% Equity Risk Sizing**: Ukuran lot dihitung otomatis berdasarkan nominal 1.5% equity modal dibagi jarak `sl_points` dari AI:
  $$\text{Lot Size} = \frac{\text{Equity} \times 1.5\%}{\text{SL Points} \times \text{Tick Value}}$$
* **Max Open Positions**: Maksimal 6 posisi simultan (`MAX_OPEN_POSITIONS = 6`).
* **Layering 3/3 Unanimous**: Jika ketiga AI sepakat (3/3), bot membuka **2 layer posisi sekaligus** (Posisi #1 TP Standar + Posisi #2 TP 1.2x) dengan total risk tetap 1.5%.

### D. Eksekusi MT5 & Proteksi Pasca-Entry
* **Auto-Resolve Symbol**: Otomatis mendeteksi `XAUUSD-ECN` (Demo) vs `XAUUSD-ECNc` (Live).
* **Order Guard**: Pembulatan harga SL/TP ke `symbol_info.digits` dan pemotongan string `comment` maksimal **25 karakter** (`[:25]`) untuk mencegah retcode MT5 `10013`.
* **Trailing Stop Dinamis**: Aktif setelah profit mencapai **50% dari target TP posisi**, dengan jarak trailing **200 points** di belakang harga aktif.
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
