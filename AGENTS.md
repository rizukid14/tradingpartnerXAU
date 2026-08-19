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
* **`src/core/cli_theme.py`**: Visualisasi banner CLI (Gold Amber Theme untuk Branch Legacy).

---

## 🌿 3. Peta Branch Repository

1. **`legacy`** (Branch Aktif Saat Ini):
   - **Fokus**: Scalping Emas (`XAUUSD-ECN` / `XAUUSD-ECNc`) Timeframe M5.
   - **AI Setup**: 3 Model (OpenAI `gpt-5.4-mini`, Gemini `gemini-2.5-flash-lite`, DeepSeek `deepseek-v4-flash`) tanpa reasoning delay.
   - **Tampilan**: CLI Theme **GOLD Amber** (`[GOLD] BOT TRADING`).
   - **Risk**: Dynamic 1.5% Equity Risk Sizing.

2. **`feature/forex-pairs`**:
   - **Fokus**: Rotasi 8 Pair Forex (H1) + Emas M30.
   - **AI Setup**: Dual Mode (OpenAI + Gemini) jam biasa, Triple Mode jam News.

3. **`legacy-2`**:
   - **Fokus**: Emas M5 dengan Prompt Caching 2-block structure & pemisahan keputusan entry vs posisi.

4. **`legacy-3`**:
   - **Fokus**: Emas M5 + Rotasi BTC M30, Fibonacci Retracement, & forecast horizon T+5m.
