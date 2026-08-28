# DOKUMEN ARSITEKTUR: TRADE PERMISSION ENGINE, WAVE PHASE & CSM PRESSURE MATRIX

> **Tanggal**: 28 Agustus 2026  
> **Status**: Approved Architecture (Revisi Berbasis Kritik & Validasi Kuantitatif)  
> **Komponen Terdampak**: `src/analytics/market_scanner.py`, `src/analytics/currency_strength.py`, `src/core/consensus.py`  
> **Dataset Validasi**: 29 Simbol MetaQuotes H1 (723.103 Bar, 2010–2026)

---

## 1. Refleksi & Koreksi Filosofi Arsitektur

### 1.1. Prinsip Fundamental: `BUY LOCKED ≠ SELL ENABLED`
Proposal awal yang mengusulkan *"Ketika terjadi Deep Retracement D1, aktifkan SELL Intraday"* terbukti **keliru secara filosofis dan toksik secara matematis**:

* **Hasil Uji Kuantitatif (35.390 Event Koreksi Makro)**:
  * Mengeksekusi Counter-Trend SELL saat tren makro masih Bullish menghasilkan **Net Loss -2.594,9R (Win Rate 29.0%, Profit Factor 0.90)**.
  * **67.2%** dari seluruh peristiwa koreksi akhirnya **melanjutkan tren makro** menuju rekor harga baru. Mencoba "menjual koreksi" adalah jebakan *selling the dip* yang melanggar hukum Trend Following.
* **Kesimpulan Filosofis**:
  Ketika pasar Bullish mengalami koreksi tajam dan CSM berubah negatif:
  $$\text{Kesimpulannya BUKAN "SELL", melainkan "BULLISH TREND — CORRECTION — WAIT / LOCK BUY"}$$

---

### 1.2. Koreksi Peran Boitoki CSM: Pressure/Permission, Bukan Switch Arah
Mengunci aturan `Net Delta <= -2.0 -> FORCE BEARISH` adalah bahaya besar karena mengganti masalah *EMA Lagging* dengan masalah *CSM Noise / Temporary Whipsaw*.
* Kasus seperti `AUDCAD` membuktikan bahwa CAD bisa menguat sesaat (memicu koreksi mikro), sebelum tren Bullish AUD kembali berlanjut.
* **Peran CSM yang Benar**: CSM mengukur **Relative Flow Velocity / Capital Pressure**, bukan struktur arah.

---

## 2. Hirarki Arsitektur 4-Layer (Direction, Phase, Pressure, Timing)

Untuk menciptakan bot yang **seluwes pertimbangan LLM** namun **berdisiplin matematis tinggi**:

```
                       ┌───────────────────────────────┐
                       │   LAYER 1: MACRO DIRECTION    │
                       │          (D1 + H4)            │
                       │     Menentukan Arah Tren      │
                       │    (Stabil / Jarang Berubah)  │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │    LAYER 2: MARKET PHASE      │
                       │       (H1 Wave Engine)        │
                       │   Menentukan Status Siklus:   │
                       │  Expansion vs Early/Mature    │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │   LAYER 3: CSM FLOW PRESSURE  │
                       │    (Boitoki Real-Time Delta)  │
                       │     Menyesuaikan Permission:  │
                       │      LOCK vs WATCH vs ARM     │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │   LAYER 4: POI & M5 TIMING    │
                       │    (SMC FVG/OB + Wicks)       │
                       │     Pemicu Eksekusi Order     │
                       └───────────────┬───────────────┘
                                       │
                                       ▼
                       ┌───────────────────────────────┐
                       │ STAGE 2: 3-LLM JURY AUDIT     │
                       │ (Hanya Dipanggil Saat ARMED)  │
                       └───────────────────────────────┘
```

---

## 3. Matriks Izin Trading Komprehensif (Trade Permission Matrix)

| Macro Direction (D1/H4) | Siklus Harga (H1 Wave Phase) | CSM Relative Pressure | Status Izin Sistem (Permission Gate) | Tindakan Radar Stage 1 |
|---|---|---|---|---|
| **BULLISH** | **Expansion (Phase 1)** | Bullish | `WAIT` (Don't Chase) | Idle (Menunggu Pullback) |
| **BULLISH** | **Expansion (Phase 1)** | Bearish | `WAIT` (Divergence Warning) | Idle |
| **BULLISH** | **Early Correction (Phase 2)** | Bearish | **`LOCK BUY`** *(Anti-Falling Knife)* | **0 Sinyal (Dilarang BUY)** |
| **BULLISH** | **Mature Basing (Phase 3)** | Bearish | `WATCH` (Consolidation near POI) | Memantau Level Support/FVG |
| **BULLISH** | **Mature Basing (Phase 3)** | Neutral / Bullish | **`ARM BUY`** | Menyiapkan Parameter Sinyal |
| **BULLISH** | **Base Reclaim (Phase 4)** | Neutral / Bullish | **`PERMITTED BUY`** | **Kirim ke 3-LLM Jury / Limit Order** |
| **BEARISH** | **Expansion (Phase 1)** | Bearish | `WAIT` (Don't Chase) | Idle |
| **BEARISH** | **Early Correction (Phase 2)** | Bullish | **`LOCK SELL`** *(Anti-Short Squeeze)* | **0 Sinyal (Dilarang SELL)** |
| **BEARISH** | **Mature Basing (Phase 3)** | Bullish | `WATCH` (Consolidation near POI) | Memantau Level Resistance/FVG |
| **BEARISH** | **Mature Basing (Phase 3)** | Neutral / Bearish | **`ARM SELL`** | Menyiapkan Parameter Sinyal |
| **BEARISH** | **Base Reclaim (Phase 4)** | Neutral / Bearish | **`PERMITTED SELL`** | **Kirim ke 3-LLM Jury / Limit Order** |

---

## 4. Bukti Kuantitatif Siklus Retracement & Trade Expectancy

Hasil pengujian empiris pada **723.103 Bar H1 (29 Simbol, 2010–2026)**:

### 4.1. Dinamika Siklus Koreksi (Retracement Lifecycle)
* **Tingkat Kelanjutan Tren (Continuation Rate)**: **67.2%** (56.878 kali koreksi berhasil melanjutkan tren makro).
* **Tingkat Kegagalan (Full Reversal Rate)**: **32.8%** (27.819 kali koreksi menembus struktur menjadi pembalikan).
* **Kedalaman Koreksi (Retracement Depth)**: **Median 1.62 ATR** (Rata-rata 1.84 ATR, 75th Percentile 2.31 ATR).

### 4.2. Nilai Harapan Matematis ($E[R]$) Berdasarkan Titik Masuk

| Titik Masuk / Lapisan Izin | Total Trade | Win Rate | Profit Factor | Net Return (R) | Expectancy / Trade | Kesimpulan |
|---|---|---|---|---|---|---|
| **1. Early Correction** *(Falling Knife / Masuk Terlalu Cepat)* | 35.390 | 31.0% | 0.99 | -357.6R | -0.010R | ❌ Rugi (Menangkap pisau jatuh) |
| **2. Mature Basing** *(Konsolidasi Awal di POI)* | 31.293 | 31.1% | 0.99 | -289.5R | -0.009R | ❌ Belum ada konfirmasi pantulan |
| **3. Base Reclaim** *(Konfirmasi Wick $\ge 20\%$)* | 23.159 | 31.0% | 0.98 | -250.7R | -0.011R | ❌ Masih rentan jika CSM melawan |
| **4. Base Reclaim + CSM Stabil** *(Delta $> -1.5$)* | **15.900** | **31.7%** | **1.02** | **+171.6R** | **+0.011R** | ✅ **Berbalik Net Profit** |
| **5. Full A+ Funnel** *(Wick $\ge 25\%$ + Limit Retest)* | **270** | **41.5%** | **1.57** | **+88.9R** | **+0.329R** | 🚀 **Optimal Edge Institusional** |
| **6. Counter-Trend Short** *(Menjual Koreksi)* | 35.390 | 29.0% | 0.90 | **-2.594,9R** | -0.073R | ☠️ **TOKSIK (Dilarang Keras)** |

---

## 5. Ringkasan Desain Final

1. **Stabilitas Tren**: Arah Makro (D1/H4) tidak mudah berganti hanya karena penurunan intraday.
2. **Kepekaan Siklus**: H1 Wave Engine mendeteksi fase *Early Correction* dan langsung mengunci (`LOCK BUY`), mencegah bot membeli pisau jatuh seperti pada EURUSD/GBPUSD tadi.
3. **Kekuatan State WAIT**: Bot memiliki kemampuan cerdas untuk menyimpulkan *"Tren masih Bullish, tetapi sekarang saatnya WAIT"*.
4. **Izin Masuk Presisi**: BUY hanya diizinkan ketika fase telah mencapai *Mature Basing $\rightarrow$ Base Reclaim* DAN tekanan CSM telah mereda (stabil/netral).
