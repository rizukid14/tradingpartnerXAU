# Estimasi Frekuensi & Biaya Call LLM Harian

> Dokumen ini menghitung estimasi jumlah panggilan API dan biaya bulanan bot trading multi-LLM consensus (OpenAI + Gemini + DeepSeek/Claude) berdasarkan arsitektur **Smart Timeframe Rotation (FASE 5)**.
> 
> *Asumsi Ukuran: Input ~3.5k tokens/call, Output ~150 tokens/call. Kurs 1 USD = Rp 15.500,-*

---

## 1. Frekuensi Panggilan per Hari (24 Jam)

LLM dipanggil hanya saat lilin timeframe simbol ditutup (FX H1 = 60 menit, BTC M30 = 30 menit, XAU M30 = 30 menit):

* **Mode XAU Only (`TRADING_MODE = "xau"`)**: 96 siklus/hari
  * OpenAI (`gpt-5.2` window / `gpt-4o-mini` luar window): **96 call/hari**
  * Gemini (`gemini-3.1-flash-lite`): **28 call/hari** (di sesi Dual & Triple)
  * DeepSeek (`deepseek-v4-flash`): **8 call/hari** (di sesi Triple)
  * **Total Panggilan:** 132 call/hari.

* **Mode XAU + Pairs (`TRADING_MODE = "xau_pairs"`) — POOL 8 SIMBOL**:
  * 240 siklus/hari (96 XAU M30 + 144 FX H1 dari 6 pair).
  * OpenAI: **240 call/hari**
  * Gemini: **70 call/hari**
  * DeepSeek: **20 call/hari**
  * **Total Panggilan:** 330 call/hari.

* **Mode BTC Only (Weekend/Rotasi)**: 48 siklus/hari
  * OpenAI: **48 call/hari** | Gemini: **14 call/hari** | DeepSeek: **4 call/hari**
  * **Total Panggilan:** 66 call/hari.

---

## 2. Estimasi Tarif Model (Harga Pasar API)

| Model LLM | Tarif Input / 1M | Tarif Output / 1M | Estimasi Biaya / Call |
|---|---|---|---|
| **OpenAI Mini** (`gpt-5.2` / `gpt-4o-mini`) | Free Tier 2.5M/hari ($0.15 paid) | Free Tier ($0.60 paid) | **$0.00** (Free Tier) / ~$0.0006 |
| **Gemini Lite** (`gemini-3.1-flash-lite`) | $0.075 | $0.30 | **~$0.0003** |
| **DeepSeek** (`deepseek-v4-flash`) | $0.14 | $0.28 | **~$0.0005** |
| **Claude Sonnet** (`claude-3-5-sonnet`) | $3.00 | $15.00 | **~$0.0128** |

---

## 3. Estimasi Biaya Harian & Bulanan

### Opsi A: Menggunakan DeepSeek di Slot 3 (DEFAULT BOT — Super Hemat)

| Mode Trading | Biaya Harian (USD) | Biaya Harian (IDR) | Biaya Bulanan (30 Hari) |
|---|---|---|---|
| **XAU Only** | ~$0.0124 / hari | ± Rp 190,- | **~$0.37 / bulan (± Rp 5.700,-)** |
| **XAU + Pairs (8 Simbol)** | ~$0.0310 / hari | ± Rp 480,- | **~$0.93 / bulan (± Rp 14.400,-)** |
| **BTC Only (Weekend)** | ~$0.0062 / hari | ± Rp 96,- | **~$0.19 / bulan (± Rp 2.900,-)** |

*(Catatan: Jika kuota free tier OpenAI habis dan menjadi berbayar, biaya bulanan mode XAU+Pairs menjadi ~$5.25 / bulan atau ± Rp 81.000,-).*

---

### Opsi B: Menggunakan Claude 3.5 Sonnet di Slot 3 (Premium)

| Mode Trading | Biaya Harian (USD) | Biaya Harian (IDR) | Biaya Bulanan (30 Hari) |
|---|---|---|---|
| **XAU Only** | ~$0.1108 / hari | ± Rp 1.710,- | **~$3.32 / bulan (± Rp 51.500,-)** |
| **XAU + Pairs (8 Simbol)** | ~$0.2770 / hari | ± Rp 4.290,- | **~$8.31 / bulan (± Rp 128.800,-)** |
| **BTC Only (Weekend)** | ~$0.0554 / hari | ± Rp 860,- | **~$1.66 / bulan (± Rp 25.700,-)** |
