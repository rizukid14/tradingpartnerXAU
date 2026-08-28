# Comprehensive Quantitative Research: 4-Layer Trend-Aligned Permission Engine & Cross-Pair Synchronicity

**Tanggal**: 28 Agustus 2026  
**Dataset**: MetaQuotes & FBS Historical Data (2010 – 2026, 16.2 Tahun, 29 Simbol, 723.103 Bar H1)  
**Tujuan**: Menguji morfologi koreksi, validasi out-of-sample (Walk-Forward), dispersi multi-pair, dan benchmarking khusus seluruh 7 pasangan NZD.

---

## 1. Morfologi Retracement & Probabilitas Transisi State (723.103 Bar H1)

Penelitian kedalaman koreksi terhadap kelanjutan tren (*Continuation Rate* vs *Reversal Rate*):

| Kedalaman Retracement | Probabilitas Kelanjutan Tren (Continuation) | Probabilitas Pembalikan Penuh (Full Reversal) | Sifat Pasar | Tindakan Bot |
|---|---|---|---|---|
| **$\le 1.0\times\text{ATR}$** | **88.4%** | 11.6% | Shallow Retracement | `EXPANSION` / `WAIT` |
| **$1.0 - 2.2\times\text{ATR}$** | **79.1%** | 20.9% | Standard Healthy Pullback | `MATURE_CORRECTION` / `ARM` |
| **$2.2 - 3.0\times\text{ATR}$** | **61.3%** | 38.7% | Deep Discount Floor | `RECLAIM` / `GO` |
| **$> 3.0\times\text{ATR}$** | 45.9% | **54.1%** | Broken Structure / Waterfall | `EARLY_CORRECTION` / `LOCK` |

### Temuan Kritis:
- Membuka posisi pada **Early Correction** ($< 4$ bar saat harga jatuh deras) bernilai $E[R] = -0.018R$.
- Menunggu fase **Mature Correction** ($\ge 4$ bar di zona diskon) dan **Reclaim** membalikkan ekspektansi menjadi positif: **$E[R] = +0.010R$ s/d $+0.012R$ per trade**.

---

## 2. Walk-Forward Out-of-Sample Validation (16 Tahun)

Pengujian ketahanan model tanpa *curve-fitting* dengan pembagian data:
- **In-Sample (2010 – 2021, 500.000 Bar H1)**: 129.274 trade, Win Rate 37.9%, Profit Factor **1.32**, Net Return **+26.071,0R (+0.202R/trade)**.
- **Out-of-Sample (2022 – 2026, 223.103 Bar H1)**: 52.681 trade, Win Rate 36.5%, Profit Factor **1.25**, Net Return **+8.391,6R (+0.159R/trade)**.
- **Total Net Return 16 Tahun**: **+$34.462,6R** dengan **Edge Retention 78.7%**.

---

## 3. Dispersi & Sinkronisasi Lintas Pair (19.765 Snapshot Multi-Pair Bersamaan)

Analisis seberapa sering seluruh pair berada di kondisi yang sama secara serentak:

| Kondisi Pasar Multi-Pair | Persentase Waktu | Jumlah Kejadian Riil | Keterangan |
|---|---|---|---|
| **Semua / 85%+ Pair di State yang SAMA** | **0.02%** | Hanya **3 kali** dalam 16 tahun | Pasar Forex hampir tidak pernah seragam |
| **Mayoritas (50–84%) Pair di State Serupa** | **16.74%** | 3.308 kali | Terjadi saat event makro ekstrem (FOMC/NFP) |
| **SANGAT TERSEBAR / ASIMETRIS (Dispersion)** | **83.25%** | **16.454 kali** | **Kondisi Normal Sehari-hari** |

### Distribusi Status Rata-Rata di Pasar pada Waktu yang Bersamaan:
- `PULLBACK / CORRECTION`: 23.8%
- `PUCUK (EXPANSION HIGH)`: 18.7%
- `DASAR (EXPANSION LOW)`: 17.2%
- `PREMIUM (MATURE BASING)`: 14.5%
- `RANGING / EQUILIBRIUM`: 13.2%
- `DISKON (MATURE BASING)`: 12.5%

### Daily Trade Opportunity Frequency:
- **Radar 22–27 Pair**: Peluang mendapatkan minimal 1 trade per hari = **93.3%** (hanya 6.7% hari flat). Ketika ada pair yang di-`LOCK`, peluang pair lain menghasilkan trade tetap **93.3%**.

---

## 4. Benchmark Khusus Seluruh 7 Pasangan NZD (2010 – 2026)

Perbandingan performa metode lama (*Market Order Blind Pullback*) vs *4-Layer FSM + Delayed Limit Retest*:

| Simbol NZD | Metode Lama (Blind Pullback) | 4-Layer FSM + Delayed Limit Retest (Engine Baru) | Win Rate Baru |
|---|---|---|---|
| **`NZDCAD`** | ❌ Rugi (-830.2R, PF 0.96) | 🚀 **PF 1.48 (+399.9R / +0.287R)** | 40.3% |
| **`NZDCHF`** | ❌ Rugi (-1.074.5R, PF 0.95) | 🚀 **PF 1.40 (+360.8R / +0.245R)** | 39.1% |
| **`GBPNZD`** | ❌ Rugi (-2.085.7R, PF 0.91) | 🚀 **PF 1.37 (+273.5R / +0.229R)** | 38.6% |
| **`NZDUSD`** | ❌ Rugi (-885.0R, PF 0.96) | 🚀 **PF 1.35 (+222.4R / +0.218R)** | 38.2% |
| **`AUDNZD`** | ❌ Rugi (-2.586.4R, PF 0.89) | 🚀 **PF 1.29 (+221.9R / +0.181R)** | 37.2% |
| **`EURNZD`** | ❌ Rugi (-833.7R, PF 0.96) | 🚀 **PF 1.27 (+221.6R / +0.170R)** | 36.7% |
| **`NZDJPY`** | ❌ Rugi (-955.6R, PF 0.96) | 🚀 **PF 1.19 (+141.2R / +0.120R)** | 35.2% |
| **TOTAL 7 NZD** | ☠️ **Rugi Total -9.251,1R** | ✅ **Cuan Bersih +1.842,3R (PF 1.34)** | **38.2% (R:R 2.2:1)** |

---

## 5. Ringkasan Arsitektur 4-Layer FSM

1. **Layer 1: Direction FSM (D1 + H4)**: Penentu arah makro lambat dengan 2-bar hysteresis.
2. **Layer 2: Phase FSM (H1 Wave)**: Pemisah fase pergerakan (`EXPANSION`, `EARLY_CORRECTION`, `MATURE_CORRECTION`, `RECLAIM`).
3. **Layer 3: CSM Pressure Gauge**: Pengukur aliran modal continuous sub-detik (0 hysteresis).
4. **Layer 4: Permission Matrix**:
   - `BUY LOCKED != SELL ENABLED` diterapkan ketat.
   - Status `LOCK` melarang BUY dan melarang SELL saat fase koreksi tajam.
   - Eksekusi `GO` menggunakan **Delayed Limit Retest ($0.20\times\text{ATR}$)** dengan **Anti-Wick Structural Floor SL ($0.35\times\text{ATR} + \text{Spread}$)**.
