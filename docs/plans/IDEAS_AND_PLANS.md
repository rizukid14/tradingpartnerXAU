# IDEAS & PLANS BACKLOG — Trading Partner Bot

> Dokumen ini menampung seluruh ide, Request for Comments (RFC), formula matematika, desain arsitektur, dan backlog fitur yang sedang diriset atau menunggu implementasi.

---

## 📋 Daftar Rencana & Backlog

| No | Fitur / Ide | Status | Target Modul |
|---|---|---|---|
| 1 | [RFC 1: One-Shot Emergency Drawdown Re-Evaluator (80% SL)](#rfc-1-one-shot-emergency-drawdown-re-evaluator-80-sl) | 🟡 Didesain (Siap Uji) | `position_manager.py`, `llm_client.py` |
| 2 | [RFC 2: Refaktorisasi Konsensus Pending vs Market](#rfc-2-refaktorisasi-konsensus-pending-vs-market) | 🟡 Didesain (Backlog) | `consensus.py`, `llm_client.py` |
| 3 | [RFC 3: Parabolic Filter di Position Manager](#rfc-3-parabolic-filter-di-position-manager) | ⚪ Konsep (Butuh Backtest) | `position_manager.py` |
| 4 | [RFC 4: Anti-Hedge Gate per Simbol](#rfc-4-anti-hedge-gate-per-simbol) | ⚪ Konsep | `main.py`, `consensus.py` |
| 5 | [RFC 5: 2-Way Interactive Telegram Controller Hardening](#rfc-5-2-way-interactive-telegram-controller-hardening) | 🟡 Didesain (Perlu Fixing) | `telegram_bot.py`, `llm_client.py` |
| 6 | [RFC 6: Peak-Aware Time-Decay Stagnation Exit](#rfc-6-peak-aware-time-decay-stagnation-exit) | 🟢 LIVE (Agustus 2026) | `position_manager.py` |
| 7 | [RFC 7: Dynamic Volatility Sizing & Adaptive BEP](#rfc-7-dynamic-volatility-sizing--adaptive-bep) | 🟢 LIVE (Agustus 2026) | `risk_engine.py`, `position_manager.py`, `llm_client.py` |
| 8 | [RFC 8: Intermarket Macro Commodity Pulse](#rfc-8-intermarket-macro-commodity-pulse) | 🟡 Didesain (Backlog) | `macro_analyst.py`, `llm_client.py` |
| 9 | [RFC 9: Revamp Dynamic Distance-to-SL Pre-Rollover Shield](#rfc-9-revamp-dynamic-distance-to-sl-pre-rollover-shield) | 🟢 LIVE (Agustus 2026) | `position_manager.py`, `config.py`, `.env` |

---

## RFC 1: One-Shot Emergency Drawdown Re-Evaluator (80% SL)

### 1. Latar Belakang & Masalah
- **Kondisi saat ini**: AI Re-evaluator posisi terbuka dipanggil **hanya pas pergantian candle** (H1 FX / M30 BTC).
- **Kelemahan**: Jika posisi meluncur deras ke arah SL di tengah candle H1 (misalnya di menit ke-25 karena pergerakan berita atau breakdown tiba-tiba), bot harus menunggu hingga jam selesai. Seringkali harga sudah menyentuh 100% SL penuh sebelum AI sempat mengevaluasi.
- **Tujuan**: Memberikan mekanisme *early emergency exit* untuk menyelamatkan sisa **20% modal (menghemat 0.20R per trade loss yang valid gagal)** jika tesis teknikal terbukti hancur sebelum menyentuh SL fisik penuh.

---

### 2. Saringan Gerbang 4 Tahap (*Deterministic Hard Gates - 0 Token*)
Agar tidak terjadi *panic close* di awal trade atau spam API, evaluasi darurat di luar cycle H1 **HANYA** dipicu jika lolos 4 saringan keras ini:

```
[Tick Check Tiap 3 Detik di position_manager.py]
  │
  ├── 1. Floating Loss >= 80% SL Fisik? ───> TIDAK: Skip
  │     └── YA
  ├── 2. Umur Posisi (Trade Age) >= 2 Jam? ──> TIDAK: Skip (Beri ruang napas pada noise awal)
  │     └── YA
  ├── 3. Jarak SL Fisik >= 60 Points (6 pips)? ──> TIDAK: Skip (Hindari noise spread pada SL tipis)
  │     └── YA
  └── 4. Belum Pernah Dievaluasi di Level 80% (1-Shot Flag)? ──> SUDAH: Skip
        └── YA ───> 🚀 TRIGGER EMERGENCY MICRO-PROMPT KE LLM
```

---

### 3. Analisis Matematika & Expectancy (EV)
- **Asimetri Risk vs Reward**:
  - Cut-loss di 80% SL menghemat **0.20R**.
  - Jika salah potong posisi yang sebenarnya mau memantul ke TP (misal TP 1.5R - 2.0R), *opportunity loss* adalah **1.70R - 2.20R**.
- **Aturan Keputusan LLM**:
  - **DEFAULT = HOLD**: AI wajib mempertahankan posisi kecuali terdapat bukti tak terbantahkan bahwa level makro sudah jebol telak dan momentum lawan arah berlanjut.

---

### 4. Format Prompt *High-Density* Micro-LLM (~350 Token)
Menggunakan model super cepat (`gemini-3.1-flash-lite` / `gpt-4o-mini`, latensi < 1 detik):

```yaml
### EMERGENCY DRAWDOWN RE-EVALUATOR (80% SL HIT)
Ticket: #1159342 | SELL CADCHF @ 0.58000 | Current: 0.58085 (-85 pts, 80% of SL 107 pts)
Duration Held: 4 Hours 15 Mins

### MACRO & KEY LEVELS
- H4 Trend: BEARISH | EMA200: 0.58120 (35 pts ABOVE current price - Major Resistance)
- D1 Key Level: Testing D1 Resistance at 0.58100
- ADX H1: 28.4 (Strong trend)

### RECENT H1 CANDLES (Hourly Progression)
- H1[-3]: O:0.58000 H:0.58040 L:0.57980 C:0.58030 (Bullish drift)
- H1[-2]: O:0.58030 H:0.58060 L:0.58020 C:0.58055 (Bullish drift)
- H1[-1]: O:0.58055 H:0.58090 L:0.58040 C:0.58085 (Testing resistance)

### RECENT M15 CANDLES (Micro Anatomy)
- M15[-3]: +12 pts Bullish (80% body)
- M15[-2]: +15 pts Bullish (85% body)
- M15[-1]: +4 pts Doji / Pinbar (Upper wick 65% - rejection at 0.58090)
- Running M15: Showing upper rejection wick near D1 resistance

### EVALUATION DIRECTIVE
This trade is at 80% SL after 4+ hours.
- CLOSE: If macro resistance is broken AND micro M15 shows continuation momentum through the level.
- HOLD: If price is currently stalling/rejecting at major H4/D1 resistance with rejection wicks.

Output JSON: {"action": "CLOSE" | "HOLD", "confidence": float, "reason": "max 5 words"}
```

---

## RFC 2: Refaktorisasi Konsensus Pending vs Market

### 1. Masalah
Saat ini, jika 1 AI mengusulkan `sell_limit` (retest pullback) dan 1 AI mengusulkan `sell_stop` (breakout momentum):
- `consensus.py` merata-ratakan kedua harga menjadi *Frankenstein price* yang berada di tengah-tengah.
- Fungsi `max()` Python memilih `entry_type` secara acak saat voting seri 1 vs 1.

### 2. Rencana Solusi
1. **Restrukturisasi Output JSON Schema Prompt LLM**:
   ```json
   {
     "execution_mode": "market" | "pending",
     "pending_type": "limit" | "stop",
     "trigger_price": 0.58050
   }
   ```
2. **Kuorum Pending di `consensus.py`**:
   - Jika model sepakat arah (misal BUY) tapi berbeda strategi entri (Limit vs Stop) $\rightarrow$ **Otomatis Fallback ke Market Order** (atau batalkan pending jika tidak memenuhi kuorum murni).
   - Hanya merata-ratakan `entry_price` jika kedua model sepakat pada jenis pending yang sama persis.

---

## RFC 3: Parabolic Filter di Position Manager

### 1. Sumber Ide
Buku *The Complete Guide to Trend Line Trading* (Rayner Teo).

### 2. Masalah
Saat tren berubah menjadi parabolik (lilin membesar $\ge 2.0\times$ ATR, kemiringan harga vertikal $\ge 70^\circ$), trailing stop biasa tertinggal terlalu jauh. Reversal mendadak sering membuang floating profit besar kembali ke nol sebelum trailing sempat mengunci.

### 3. Logika Usulan
```
JIKA  (kemiringan tren > 70 derajat)
DAN   (rata-rata candle running > 2.0 x ATR)
MAKA  -> Mode PARABOLIK AKTIF:
       -> Kunci SL agresif ke Low/High candle sebelumnya (Previous Bar Extreme) pada timeframe eksekusi.
```

### 4. Catatan & Syarat
- Harus di-backtest terlebih dahulu pada data live untuk melihat frekuensi dan dampaknya terhadap *let profits run*.

---

## RFC 4: Anti-Hedge Gate per Simbol

### 1. Masalah
Jika terdapat posisi `BUY` yang masih aktif pada suatu simbol (misal XAUUSD), dan pada cycle berikutnya AI menyetujui konsensus `SELL`, sistem saat ini dapat membuka posisi SELL sehingga terjadi posisi *hedging* bersamaan (BUY + SELL aktif berbarengan di 1 simbol).

### 2. Opsi Solusi
- **Opsi A**: Tolak entry baru jika bertentangan arah dengan posisi aktif di simbol yang sama.
- **Opsi B**: Tutup posisi lama secara paksa terlebih dahulu (*close-and-reverse*), lalu buka posisi baru sesuai sinyal fresh.

---

## RFC 5: 2-Way Interactive Telegram Controller Hardening

### 1. Deskripsi & Arsitektur
Modul pengendali dua arah berbasis Telegram Bot (`src/core/telegram_bot.py`) yang berjalan sebagai background thread daemon di `main.py` menggunakan POST fast-polling via proxy Vercel (`https://tg-proxy-vercel-eight.vercel.app`).

### 2. Fitur yang Sudah Dibuat
- Menu navigasi institusional `[ ☰ Menu ]` via `setMyCommands` & inline keyboard.
- On-Demand 3-AI Consensus Analysis (`/analisa <symbol>` atau ketik nama pair langsung).
- Pemantauan akun & risk (`/status`, `/posisi`, `/scan`, `/rekap`).
- Emergency close ticket (`/close <ticket>`) & close all positions (`/closeall`).
- Perbaikan helper parallel querying `query_all_models_parallel` di `src/core/llm_client.py`.
- Penyelarasan singleton `analyst` dan parameter dinamis `symbol=None` di `src/analytics/macro_analyst.py`.

### 3. Tasklist Perbaikan (Fixing) Sesi Berikutnya
- [ ] **Background Listener Responsiveness**: Verifikasi loop polling `getUpdates` agar tidak menahan/tertunda saat loop utama MT5 sedang memproses 7 pair di `main.py`.
- [ ] **Telegram Markdown Parsing Safety**: Pastikan semua karakter khusus seperti `_`, `*`, `[`, `]` di teks log/error ter-escape dengan benar agar Telegram API tidak menolak payload.
- [ ] **Cross-Platform Verification**: Uji pengiriman command dari Telegram Desktop dan Mobile app saat bot running live.
 
---
 
## RFC 6: Peak-Aware Time-Decay Stagnation Exit & Pre-Rollover Shield
 
### 1. Active-Session Peak-Aware Time-Decay
- Menutup posisi yang hold $\ge 4$ jam aktif (H1) yang floating di $[-0.20R, +0.20R]$ **hanya jika** Peak MFE historis $< +0.30R$.
- Memastikan trade yang sempat ekspansi $+0.4R/+0.5R$ lalu pullback normal **TIDAK TER-CLOSE PREMATUR**.
 
### 2. Pre-Rollover Drawdown & Stagnation Shield (03:00–04:55 WIB)
- Menutup posisi stagnan atau posisi ber-drawdown $\ge 45\%$ SL sebelum pergantian hari (jam 05:00 WIB).
- Menghemat $50\%$ modal risiko dari ancaman pelebaran spread broker saat pergantian hari.
 
---
 
## RFC 7: Dynamic Volatility Sizing & Adaptive BEP
 
### 1. Dynamic Volatility Scaling (ATR Percentile)
- Menggantikan multiplier jam dinding statis (`0.7x`, `1.0x`, `1.2x`) dengan rasio volatilitas aktual terhadap baseline 30-hari:
  - Low Vol ($< 0.70\times$): Multiplier `0.75x` & Adaptive BEP `45% TP`.
  - Normal Vol ($0.70 - 1.20\times$): Multiplier `1.00x` & BEP `58% TP`.
  - High Vol ($> 1.20\times$): Multiplier `1.15x` & BEP `58% TP`.
 
### 2. Peak MFE Awareness di Prompt AI Re-Evaluator
- Menampilkan data objektif `Peak: +$X.XX (+Y.YY R)` pada daftar tiket terbuka agar LLM dapat mendeteksi kegagalan momentum (*U-turn reversal*) secara alami.

---

## RFC 8: Intermarket Macro Commodity Pulse

### 1. Latar Belakang & Masalah
- **Kondisi saat ini**: Analisis makro di `macro_analyst.py` berfokus pada MTF (H4/D1) dan korelasi D1 antar-pair Forex internal.
- **Tujuan**: Memberikan konteks sentimen global dan komoditas utama yang menggerakkan mata uang komoditas (*Commodity Currencies*):
  - `CL-OIL` (Minyak Mentah) $\rightarrow$ Pendorong fundamental CAD (`NZDCAD`, `AUDCAD`).
  - `COPPER` (Tembaga) $\rightarrow$ Pendorong fundamental AUD & NZD (`EURNZD`, `AUDCAD`).
  - `NAS100` / `US500` (Indeks Ekuitas) $\rightarrow$ Pengukur sentimen Risk-On vs Risk-Off (Safe Haven CHF vs Risk FX).
  - `XAUUSD` (Emas) $\rightarrow$ Arah likuiditas moneter global & pelemahan/penguatan DXY.

### 2. Desain Implementasi
- **Fetch Ringan MT5 (Cache 1 Jam)**:
  - Mengambil perubahan persentase harian D1 (Today Open vs Current Bid) dari simbol broker terkait (`CL-OIL`, `COPPER`, `US100`, `XAUUSD`).
  - Diformat menjadi 1 baris teks padat objektif:
    ```yaml
    ### GLOBAL COMMODITY & RISK PULSE (D1 Change)
    - Oil (WTI): +1.2% (CAD bullish) | Copper: -0.8% (AUD/NZD mild drag) | Gold: +0.4% | Nasdaq: +0.6% (Risk-On)
    ```
- **Prinsip**: Data murni numerik dan faktual tanpa instruksi dogmatis, membiarkan LLM memanfaatkan korelasi intermarket secara independen.

---

## RFC 9: Revamp Dynamic Distance-to-SL Pre-Rollover Shield

### 1. Latar Belakang & Masalah
* **Kelemahan Shield Statis Lama**:
  1. Window 03:00–05:00 WIB terlalu lebar dan memotong 2 jam likuiditas aktif sesi US.
  2. Rule stagnasi $[-0.20R, +0.20R]$ membunuh swing H1 yang sehat.
  3. Cut loss statis $\le -0.45R$ buta terhadap sisa jarak harga ke SL fisik dan estimasi spread riil per pair.
* **Hasil Riset Empiris VT Markets (60 Hari)**:
  * Median spread spike rollover hanya $0.8 - 1.8\text{ pips}$.
  * P90 jumping harga pergantian hari: Major $\approx 10\text{ pips}$, Cross $\approx 10 - 25\text{ pips}$, EURNZD $\approx 37\text{ pips}$. Tail risk terparah (EURCAD) pernah mencapai $14\text{ pips}$ ($140\text{ pts}$).

### 2. Desain Arsitektur Baru: Dynamic Distance-to-SL Clearance
* **Jendela Waktu Presisi (Server + 4h = WIB)**:
  * Server Rollover = 00:00 Server $\rightarrow$ **TEPAT 04:00:00 WIB**.
  * Jendela Shield Aktif: **03:50 – 04:15 WIB** (10 menit sebelum s/d 15 menit setelah 00:00 server).
* **Hapus Total Rule Stagnasi**: Posisi flat/profit dibiarkan berjalan.
* **Formula Dynamic Clearance**:
  $$\text{Distance to SL (pts)} = \frac{|\text{Current Price} - \text{pos.sl}|}{\text{point}}$$
  $$\text{Tail-Risk Buffer (pts)} = \max(\text{Config Buffer}, \ 5 \times \text{Live Spread}, \ 25\% \times \text{ATR H1})$$
  * **Major (`GBPUSD`)**: $80\text{ pts}$ ($8.0\text{ pips}$)
  * **Cross Pair (`EURCHF`, `GBPCHF`, `AUDCAD`, `NZDCAD`, `EURNZD`, `EURCAD`)**: $300\text{ pts}$ ($30.0\text{ pips}$) *(menampung spike 226–250 pts yang terjadi pada EURCHF/GBPCHF/EURNZD)*
  * **Gold (`XAUUSD`)**: $400\text{ pts}$ ($40.0\text{ pips}$)
  * **Crypto (`BTCUSD`)**: Bebas / Skip (24/7).
* **Kriteria Eksekusi Emergency Cut-Loss**:
  $$\text{TUTUP BERSIH HANYA JIKA: } \text{Distance to SL} \le \text{Tail-Risk Buffer} \times 1.1 \quad (\text{pada jam } 03:50 - 04:15\text{ WIB})$$
  *(Posisi dengan SL mepet $\le 30\text{ pips}$ langsung ditutup pada 03:50 WIB di harga normal sebelum terjadi gap down & slippage 2x).*

### 3. File Target & Single Source of Truth
* Target implementasi: `src/analytics/position_manager.py` (`_check_pre_rollover_shield`).
* Konfigurasi `.env` & `config.py`:
  * `PRE_ROLLOVER_SHIELD_ENABLED=true` (setelah refactor selesai)
  * `PRE_ROLLOVER_START_MINUTE_WIB=230`  # 03:50 WIB (3*60+50)
  * `PRE_ROLLOVER_END_MINUTE_WIB=255`    # 04:15 WIB (4*60+15)
  * `PRE_ROLLOVER_BUFFER_MAJOR_PTS=80.0`
  * `PRE_ROLLOVER_BUFFER_CROSS_PTS=300.0`
  * `PRE_ROLLOVER_BUFFER_XAU_PTS=400.0`


