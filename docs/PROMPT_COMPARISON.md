# Perbandingan Prompt LLM Trading Bot: `legacy` vs `main` vs `dev-backtest` vs `dev-backtest-prompt`

Dokumen ini memuat analisis komparatif dan perbandingan mendalam mengenai struktur, instruksi, batasan risk, serta format output prompt LLM di 4 branch repository **tradingpartnerXAU**.

---

## 📊 1. Ringkasan Matriks Perbandingan

| Fitur / Parameter | `legacy` | `main` | `dev-backtest` | `dev-backtest-prompt` |
| :--- | :--- | :--- | :--- | :--- |
| **Arsitektur Prompt** | Monolitik dalam `prepare_prompt` | Modular (`_SYSTEM_PROMPT_TEMPLATE` + Market Data) | Modular + Dynamic SL/TP Rules per-Kategori Aset | Templatized Modular (`{{EXECUTION_NOTE}}`, `{{PENDING_FIELDS}}`, `{{PENDING_RULES}}`) |
| **Ukuran System Prompt** | ~1,200 karakter (inline) | 3,938 karakter | 6,161 karakter | ~6,057+ karakter (dinamis) |
| **Role & Persona AI** | Generic Scalper / Trader | `M5 Scalping Analyst` | `Short-term Swing Analyst` | `Short-term Swing Analyst` (Adaptif ke Pending Order) |
| **Eksekusi Order** | Market Order Only | Market Order Only | Market Order Only (`### EXECUTION CONTEXT`) | **Market Order + Pending Limit Order** (`BUY_LIMIT` / `SELL_LIMIT`) |
| **Output JSON Schema** | `action`, `confidence`, `sl_points`, `tp_points`, `reasoning` | Tambah `position_actions` (manajemen tiket terbuka) | Tambah `invalidation_price` & `target_price` | Tambah `order_type`, `limit_price`, `expiration_candles` (opsional) |
| **Pengaturan SL/TP** | Multiplier ATR sederhana (1.5x - 2.0x) | Points integer generik | Dual Mode: **LLM Mode** (Safety Floor) vs **ATR-Based Mode** (Fix R:R 2:1) | Dual Mode + Aturan khusus untuk Pending Limit Price |
| **Penanganan Multi-Symbol** | Tidak ada | Terbatas | Support XAU, BTC, FX Pair per-kategori | Support XAU, BTC, FX Pair + Templating fleksibel |
| **Batas Reasoning** | Tidak dibatasi | 1-2 kalimat (max 40 kata) | 2-3 kalimat (max 45 kata) | 1-2 kalimat (max 40 kata) |

---

## 🔍 2. Analisis Per Branch secara Detail

### 1. Branch `legacy`
* **Pendekatan**: Prompt bersifat **monolitik** dan langsung di-generate dalam fungsi `prepare_prompt()` di `src/core/llm_client.py`.
* **Karakteristik**:
  - Hanya mengambil 10 candle terakhir dengan beberapa indikator dasar (RSI, EMA20, EMA50).
  - SL/TP langsung ditentukan menggunakan range ATR yang dihitung secara kaku di Python (misal SL = 1.5x - 2.0x ATR).
  - Skema JSON output sangat sederhana tanpa adanya manajemen posisi berjalan (`position_actions`).
  - Tidak ada instruksi spesifik mengenai kerangka analisis (Analysis Freedom, Price Action, Trend Context, dsb.).

---

### 2. Branch `main`
* **Pendekatan**: Memisahkan prompt menjadi **System Prompt Static Template** (`_SYSTEM_PROMPT_TEMPLATE`) dan **Dynamic Market Data Block**.
* **Peningkatan Utama**:
  - Pengenalan 5 Seksi Utama: `### ROLE`, `### ANALYSIS FREEDOM`, `### DATA INTEGRITY`, `### RISK CONSTRAINTS`, `### OUTPUT FORMAT`.
  - Penambahan skema JSON `position_actions` untuk mengevaluasi posisi yang sedang terbuka (`CLOSE` / `HOLD`).
  - Penekanan unit pengukuran SL/TP dalam **broker points** (integer).
  - Penyesuaian persona menjadi `M5 Scalping Analyst`.

---

### 3. Branch `dev-backtest`
* **Pendekatan**: Prompt diperluas secara signifikan (6,161 karakter) dengan penekanan pada **Swing Analysis** dan **Dual SL/TP Rules**.
* **Peningkatan Utama**:
  - Seksi baru `### EXECUTION CONTEXT`: Menjelaskan bahwa order akan dieksekusi secara instant pada harga pasaran saat ini (Market Order).
  - Persona diubah dari Scalper menjadi `Short-term Swing Analyst` (M30/H1).
  - **Fitur Level Invalidasi Terpisah**: Menambahkan field `invalidation_price` dan `target_price` pada JSON output sebagai referensi harga absolut probabilitas/tesis, sementara `sl_points` dan `tp_points` tetap dipakai bot untuk memasang order.
  - **Integrasi Rule SL/TP Mode-Aware**: Menyuntikkan aturan spesifik secara dinamis via `_build_sltp_rules_block`:
    - **XAUUSD & BTC**: Aturan kaku berbasis ATR (Non-negotiable floor & minimum R:R 2:1).
    - **FX Pairs**: Aturan LLM berstruktur dengan Safety Floor minimal `max(2x spread, 1.5x ATR H1)`.

---

### 4. Branch `dev-backtest-prompt` (Terbaru / Current)
* **Pendekatan**: Menjadikan System Prompt **dinamis dan modular berbasis Template Placeholders** untuk mendukung **Backtesting & Pending Limit Orders**.
* **Fitur & Perubahan Utama**:
  - **Placeholder Templating**:
    - `{{EXECUTION_NOTE}}`: Dapat berganti antara eksekusi Market Order saja atau opsi Pending Order.
    - `{{PENDING_FIELDS}}`: Menyuntikkan instruksi field JSON tambahan (`order_type`, `limit_price`, `expiration_candles`) jika fitur pending order aktif.
    - `{{PENDING_RULES_BLOCK}}`: Menyuntikkan batasan teknis pending limit order (misal: jarak minimum limit price dari current bid/ask, validitas harga limit vs pullback zone).
  - **Dukungan Pending Order (`BUY_LIMIT` / `SELL_LIMIT`)**:
    - Jika harga saat ini berada di pertengahan move dan belum menyentuh zone optimal/pullback, LLM tidak lagi dipaksa memilih `HOLD` atau eksekusi market yang terburu-buru.
    - LLM dapat menyarankan `BUY_LIMIT` atau `SELL_LIMIT` pada `limit_price` tertentu.
  - **Optimasi Token & Caching**: Struktur template dirancang agar bagian static tetap dapat di-cache oleh LLM provider (OpenAI / Anthropic / Gemini), sementara variabel dinamis disuntikkan secara presisi.

---

## 🚀 5. Perbandingan JSON Output Schema antar Branch

### Schema Legacy & Main (Market Order Only):
```json
{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.85,
  "sl_points": 450,
  "tp_points": 900,
  "reasoning": "Breakout of key resistance level with high volume.",
  "position_actions": [
    {"ticket": 123456, "action": "HOLD", "reason": "Trend intact"}
  ]
}
```

### Schema `dev-backtest-prompt` (Market + Pending Order Support):
```json
{
  "action": "BUY" | "SELL" | "HOLD",
  "order_type": "MARKET" | "BUY_LIMIT" | "SELL_LIMIT",
  "limit_price": 2735.50,
  "confidence": 0.85,
  "invalidation_price": 2728.00,
  "target_price": 2755.00,
  "sl_points": 450,
  "tp_points": 900,
  "expiration_candles": 4,
  "reasoning": "Price pulling back to key M30 order block zone.",
  "position_actions": [
    {"ticket": 123456, "action": "HOLD", "reason": "Trend intact"}
  ]
}
```
