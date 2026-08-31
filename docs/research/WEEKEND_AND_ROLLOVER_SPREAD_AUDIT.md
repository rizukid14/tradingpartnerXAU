# Audit Komparatif Spread Weekend & Daily Rollover — 26 FX Universe + BTC

> **Waktu Audit**: Minggu, 30 Agustus 2026  
> **Akun**: VTMarkets-Live 3 (Login: 27556325) — Server GMT+3  
> **Tujuan**: Dokumentasi resmi fenomena pelebaran spread saat pasar tutup (Weekend) dan jendela pergantian hari (Daily Rollover 04:00 WIB), serta implikasinya terhadap *Pre-Rollover Shield*, *Dead Zone*, dan *Reload Zone Calibration*.

---

## 📊 1. Master Data Spread Weekend 26 Simbol Scanner Universe

Berikut adalah data live snapshot spread akun real pada penutupan pasar weekend:

| No | Simbol Universe | Broker Simbol | Spread Weekend (pts) | Spread Weekend (pips) | Estimasi Normal Weekday | Rasio Lonjakan (Multiplier) | Klasifikasi Risiko Weekend |
|:---:|---|---|:---:|:---:|:---:|:---:|:---:|
| 1 | **GBPNZD** | GBPNZD-ECNc | **183.0** | **18.3 pips** | ~1.8 pips | **10.1x** | 🚨 EKSTREM TINGGI |
| 2 | **CHFJPY** | CHFJPY-ECNc | **138.0** | **13.8 pips** | ~1.5 pips | **9.2x** | 🚨 EKSTREM TINGGI |
| 3 | **EURNZD** | EURNZD-ECNc | **123.0** | **12.3 pips** | ~1.6 pips | **7.7x** | 🚨 EKSTREM TINGGI |
| 4 | **AUDNZD** | AUDNZD-ECNc | **109.0** | **10.9 pips** | ~1.4 pips | **7.8x** | 🚨 EKSTREM TINGGI |
| 5 | **GBPAUD** | GBPAUD-ECNc | **101.0** | **10.1 pips** | ~1.5 pips | **6.7x** | 🚨 EKSTREM TINGGI |
| 6 | **GBPCHF** | GBPCHF-ECNc | **83.0** | **8.3 pips** | ~1.4 pips | **5.9x** | ⚠️ TINGGI |
| 7 | **GBPJPY** | GBPJPY-ECNc | **77.0** | **7.7 pips** | ~1.2 pips | **6.4x** | ⚠️ TINGGI |
| 8 | **GBPCAD** | GBPCAD-ECNc | **64.0** | **6.4 pips** | ~1.3 pips | **4.9x** | ⚠️ TINGGI |
| 9 | **NZDCAD** | NZDCAD-ECNc | **60.0** | **6.0 pips** | ~1.2 pips | **5.0x** | ⚠️ TINGGI |
| 10 | **EURAUD** | EURAUD-ECNc | **53.0** | **5.3 pips** | ~1.2 pips | **4.4x** | 🟡 MODERAT |
| 11 | **NZDCHF** | NZDCHF-ECNc | **51.0** | **5.1 pips** | ~1.3 pips | **3.9x** | 🟡 MODERAT |
| 12 | **AUDJPY** | AUDJPY-ECNc | **49.0** | **4.9 pips** | ~1.1 pips | **4.5x** | 🟡 MODERAT |
| 13 | **AUDCHF** | AUDCHF-ECNc | **48.0** | **4.8 pips** | ~1.2 pips | **4.0x** | 🟡 MODERAT |
| 14 | **USDCHF** | USDCHF-ECNc | **45.0** | **4.5 pips** | ~0.9 pips | **5.0x** | 🟡 MODERAT |
| 15 | **EURCHF** | EURCHF-ECNc | **41.0** | **4.1 pips** | ~0.9 pips | **4.6x** | 🟡 MODERAT |
| 16 | **EURJPY** | EURJPY-ECNc | **39.0** | **3.9 pips** | ~1.0 pips | **3.9x** | 🟡 MODERAT |
| 17 | **NZDUSD** | NZDUSD-ECNc | **39.0** | **3.9 pips** | ~1.0 pips | **3.9x** | 🟡 MODERAT |
| 18 | **AUDCAD** | AUDCAD-ECNc | **38.0** | **3.8 pips** | ~1.1 pips | **3.5x** | 🟡 MODERAT |
| 19 | **GBPUSD** | GBPUSD-ECNc | **31.0** | **3.1 pips** | ~0.9 pips | **3.4x** | 🟢 RENDAH |
| 20 | **EURGBP** | EURGBP-ECNc | **28.0** | **2.8 pips** | ~0.8 pips | **3.5x** | 🟢 RENDAH |
| 21 | **EURCAD** | EURCAD-ECNc | **28.0** | **2.8 pips** | ~1.0 pips | **2.8x** | 🟢 RENDAH |
| 22 | **CADJPY** | CADJPY-ECNc | **28.0** | **2.8 pips** | ~1.1 pips | **2.5x** | 🟢 RENDAH |
| 23 | **USDJPY** | USDJPY-ECNc | **24.0** | **2.4 pips** | ~0.8 pips | **3.0x** | 🟢 RENDAH |
| 24 | **AUDUSD** | AUDUSD-ECNc | **19.0** | **1.9 pips** | ~0.8 pips | **2.4x** | 🟢 RENDAH |
| 25 | **EURUSD** | EURUSD-ECNc | **9.0** | **0.9 pips** | ~0.7 pips | **1.3x** | 💎 ULTRA STABIL |
| 26 | **USDCAD** | USDCAD-ECNc | **7.0** | **0.7 pips** | ~0.7 pips | **1.0x** | 💎 ULTRA STABIL |
| -- | **BTCUSD** | BTCUSD.c | **170.0** | **.70** | ~.70 | **1.0x** | 💎 CRYPTO 24/7 |

---

## 🔍 2. Temuan Kuantitatif & Pola Likuiditas

1. **Kelompok Cross Minor & Pasifik Paling Rentan Melebar (Cluster 1: NZD, CHF, GBP)**:
   * Pasangan eksotis silang seperti GBPNZD, CHFJPY, EURNZD, dan AUDNZD mengalami lonjakan spread ekstrem antara **7.7x hingga 10.1x**.
   * Ini membuktikan bahwa saat pasar antarbank tutup, penyedia likuiditas (*Liquidity Providers / LPs*) langsung menarik kuotasi bid/ask pada pair bervolume rendah.
2. **Kelompok USD Majors Paling Tangguh (Cluster 2: EURUSD, USDCAD, AUDUSD, USDJPY)**:
   * EURUSD dan USDCAD mempertahankan spread ultra-ketat bahkan di akhir pekan (< 1.0 pip).
   * Pasar institusional global memiliki kedalaman order book yang sangat tebal pada pasangan mata uang utama ini.
3. **Instrumen Kripto (BTCUSD.c)**:
   * Beroperasi 24/7 tanpa penutupan pasar antarbank, dengan spread stabil .70 ( pts) secara konsisten.

---

## 🛡️ 3. Implikasi Langsung pada Fitur Perlindungan Bot

### A. Pre-Rollover Shield (03:50 – 04:15 WIB)
* Lonjakan spread saat **Daily Rollover (00:00 Server / 04:00 WIB)** memiliki karakteristik identik dengan spread weekend.
* Posisi yang mengambang tipis di dekat Stop Loss pada pair rentan (GBPNZD, EURNZD, GBPCHF) **wajib diamankan / ditutup bersih di 03:50 WIB** sebelum lonjakan spread buatan broker menyentuh SL.

### B. Dead Zone Trading Filter (00:00 – 08:00 WIB)
* Filter Dead Zone di 
isk_engine.py yang melarang pembukaan posisi baru antara jam 00:00 - 08:00 WIB terbukti sangat krusial untuk melindungi akun dari churn biaya transaksi berlebih.

### C. Kalibrasi Lebar Reload Zone (.55 	imes 	ext{ATR H1}$)
* Reload Zone dihitung berbasis **volatilitas murni H1 (.55	imes	ext{ATR H1}$)** dengan safety floor:
  * FX Crosses / Majors: Minimal **6.0 pips**.
  * JPY Crosses: Minimal **10.0 pips**.
  * BTC: Minimal ****.
* Ini memastikan saat hari kerja normal (spread 0.7 - 1.5 pip), jaring limit order bot memiliki ruang tangkap yang presisi dan tidak terpengaruh oleh anomali weekend.
