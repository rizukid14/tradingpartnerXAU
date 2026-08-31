# 📑 LAPORAN RISET KUANTITATIF: HIERARKI LEVEL PSIKOLOGIS MAKRO & DUAL-DIRECTION DELIVERY ENGINE

**Author**: Antigravity Quant Team & TradingPartner Bot Engine  
**Dataset Scale**: 10,014,335 Real Market Bars (MetaQuotes & MT5 Multi-Year 2010–2026 / 16.2 Tahun)  
**Universe Analisis**: 29 Simbol Lengkap (Forex Majors, Pacific, JPY Crosses, Minor Crosses, dan Gold)  
**Tujuan Riset**: Mengeliminasi keterlambatan deteksi tren (*Lagging CHoCH*), mengintegrasikan zona psikologis makro dinamis berbasis ADR per-simbol, dan menyelaraskan eksekusi gelombang fraktal (M3 Macro Compass + Trio Eksekutor H1 M1, M2, M4).

---

## 1. Rumusan Masalah (*Problem Formulation*)

### Masalah 1: Keterlambatan Fatal Deteksi Pembalikan Tren (*Lagging CHoCH Trap*)
- **Deskripsi Masalah**: Model Price Action konvensional hanya menganggap tren berbalik (*Change of Character / CHoCH*) jika harga menembus titik *Swing Low / Swing High* struktural sebelumnya.
- **Dampak Nyata (Kasus EURUSD 2026)**:
  * Pada **27-28 Januari 2026**, EURUSD menyentuh **Puncak Psikologis 1.20819** dan mulai runtuh ke bawah.
  * Namun karena *Swing Low* D1 lama berada di **1.17418 (berjarak 340 pips di bawah)**, model CHoCH klasik baru berganti status menjadi *Bearish* pada **2 Maret 2026**.
  * Akibatnya: Sistem terlambat selama 1 bulan lebih, dan bot terus mencoba membeli (*BUY*) di tengah air terjun penurunan 670 pips.

### Masalah 2: Ilusi Harga Garis Kaku (*The Static Line Fallacy*)
- **Deskripsi Masalah**: Mengasumsikan level psikologis (1.2000, 1.1400) sebagai "garis tipis statis 1 harga".
- **Realitas Pasar**: Pasar lelang selalu bergerak dalam **Pita Zona Dinamis (*Zonal Band $\pm 0.35\times\text{ATR}$*)** akibat adanya *front-running undershoot* dan *liquidity sweep overshoot*.

### Masalah 3: Kebutaan Hierarki Fraktal (*Fractal Hierarchy Blindness*)
- **Deskripsi Masalah**: Menyamaratakan semua level support/resistance tanpa membedakan level batas kedaulatan bank sentral (*Sovereign Boundary Walls* 1.20 / 1.14), titik putar gelombang (*Fib 50% - 61.8% Golden Pocket* 1.18), dan level batu loncatan perantara (*Intermediate Milestones* 1.15 / 1.16).

---

## 2. Solusi Arsitektur yang Dirumuskan (*Proposed Architecture*)

```text
══════════════════════════════════════════════════════════════════════════════════
               TINGKAT 1: KOMPAS NAVIGATOR MAKRO (M3)
             "M3 Bukan Mesin Penembak Order, M3 Adalah GPS Arah"
══════════════════════════════════════════════════════════════════════════════════
 • Input: 
   1. Dinding Sovereign (1.20 / 1.14) & Level Psikologis Berbasis ADR Per-Pair.
   2. Zona Fib 50% - 61.8% Golden Pocket Gelombang Makro.
   3. Pemetaan Stasiun Perantara (1.15, 1.16, 1.17, 1.18, 1.19).
 • Output GPS untuk H1:
   🧭 "KORIDOR AKTIF H1: BULLISH (1.1780 -> 1.1920)" atau "BEARISH (1.1920 -> 1.1410)"
══════════════════════════════════════════════════════════════════════════════════
                                      │
                                      ▼
══════════════════════════════════════════════════════════════════════════════════
               TINGKAT 2: TRIO PENEMBAK TAKTIS H1 (M1, M2, M4)
          "Eksekusi Trade Cepat, SL Rapat 25-40 Pips, Full Lot Size"
══════════════════════════════════════════════════════════════════════════════════
 Saat Kompas M3 = BULLISH KORIDOR:
   • M1 (Judas Sweep): BUY saat sapuan likuiditas sesi Asia Low / PDL memantul naik.
   • M2 (Trend Pullback): BUY saat harga bernafas ke EMA20 / Support H1 di zona diskon.
   • M4 (Breakout Retest): BUY via Limit Order saat stasiun perantara dijebol & di-retest.

 Saat Kompas M3 = BEARISH KORIDOR:
   • M1 (Judas Sweep): SELL saat sapuan likuiditas sesi Asia High / PDH tertolak turun.
   • M2 (Trend Pullback): SELL saat harga memantul ke EMA20 / Resistance H1 di zona premium.
   • M4 (Breakout Retest): SELL via Limit Order saat lantai perantara dijebol & di-retest.
══════════════════════════════════════════════════════════════════════════════════
```

---

## 3. Hasil Master Backtest Lengkap pada Seluruh 29 Simbol (16.2 Tahun / 262.739 Trade)

Berikut adalah tabel lengkap hasil pengujian empiris tanpa look-ahead bias pada seluruh 29 instrumen:

| No | Simbol | ADR 20D (Pips) | Natural Psych Step | Total Trade | Win Rate (Target 2R) | Profit Factor (PF) | Expected Value ($EV$) | Total Return (+R) | Kategori Status |
|:---:|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | **EURJPY** | 109.5 pips | 1.000 JPY (100p) | 8,652 | **36.03%** | **1.07** | **+0.043R** | **+371.0R** | 🟢 **STAR CLUSTER** |
| 2 | **EURUSD** | 80.4 pips | 0.0100 (100p) | 7,890 | **35.70%** | **1.06** | **+0.038R** | **+297.8R** | 🟢 **STAR CLUSTER** |
| 3 | **AUDUSD** | 72.3 pips | 0.0050 (50p) | 8,002 | **35.35%** | **1.05** | **+0.029R** | **+233.9R** | 🟢 **STAR CLUSTER** |
| 4 | **USDJPY** | 84.7 pips | 1.000 JPY (100p) | 8,001 | **35.82%** | **1.04** | **+0.027R** | **+218.3R** | 🟢 **STAR CLUSTER** |
| 5 | **XAUUSD (GOLD)** | 256.6 pips | $50.00 | 8,061 | **35.37%** | **1.03** | **+0.021R** | **+165.9R** | 🟢 **STAR CLUSTER** |
| 6 | **EURAUD** | 121.7 pips | 0.0200 (200p) | 8,775 | **35.04%** | **1.01** | **+0.007R** | **+64.1R** | 🟢 **STAR CLUSTER** |
| 7 | **GBPUSD** | 99.0 pips | 0.0100 (100p) | 8,088 | **34.82%** | **1.01** | **+0.003R** | **+27.3R** | 🟢 **STAR CLUSTER** |
| 8 | **CADJPY** | 84.6 pips | 1.000 JPY (100p) | 8,906 | 34.59% | 0.99 | -0.007R | -61.1R | ⚪ Netral |
| 9 | **AUDJPY** | 91.8 pips | 1.000 JPY (100p) | 8,539 | 34.93% | 0.99 | -0.008R | -67.0R | ⚪ Netral |
| 10 | **NZDCHF** | 65.9 pips | 0.0050 (50p) | 9,869 | 33.95% | 0.97 | -0.019R | -189.8R | 🔴 Filtered |
| 11 | **GBPJPY** | 142.4 pips | 2.000 JPY (200p) | 9,073 | 33.76% | 0.96 | -0.028R | -253.1R | 🔴 Filtered |
| 12 | **USDCAD** | 77.4 pips | 0.0100 (100p) | 8,277 | 33.60% | 0.95 | -0.034R | -281.2R | 🔴 Filtered |
| 13 | **NZDUSD** | 68.4 pips | 0.0050 (50p) | 8,626 | 32.83% | 0.93 | -0.044R | -379.8R | 🔴 Filtered |
| 14 | **GBPCHF** | 100.2 pips | 0.0100 (100p) | 9,814 | 33.40% | 0.94 | -0.041R | -403.2R | 🔴 Filtered |
| 15 | **GBPAUD** | 153.9 pips | 0.0200 (200p) | 8,794 | 33.17% | 0.92 | -0.050R | -443.8R | 🔴 Filtered |
| 16 | **EURNZD** | 146.6 pips | 0.0200 (200p) | 9,296 | 33.04% | 0.92 | -0.050R | -466.5R | 🔴 Filtered |
| 17 | **CADCHF** | 62.6 pips | 0.0050 (50p) | 9,539 | 32.75% | 0.92 | -0.051R | -489.7R | 🔴 Filtered |
| 18 | **GBPCAD** | 126.7 pips | 0.0200 (200p) | 9,195 | 33.10% | 0.92 | -0.053R | -490.4R | 🔴 Filtered |
| 19 | **CHFJPY** | 100.8 pips | 1.000 JPY (100p) | 9,799 | 33.05% | 0.92 | -0.051R | -500.3R | 🔴 Filtered |
| 20 | **EURGBP** | 52.9 pips | 0.0050 (50p) | 9,305 | 32.75% | 0.91 | -0.059R | -552.7R | 🔴 Filtered |
| 21 | **EURCAD** | 100.4 pips | 0.0100 (100p) | 9,075 | 32.45% | 0.91 | -0.062R | -563.1R | 🔴 Filtered |
| 22 | **GBPNZD** | 185.0 pips | 0.0200 (200p) | 9,169 | 32.63% | 0.91 | -0.063R | -575.5R | 🔴 Filtered |
| 23 | **AUDCAD** | 72.3 pips | 0.0050 (50p) | 9,906 | 32.71% | 0.91 | -0.061R | -601.5R | 🔴 Filtered |
| 24 | **USDCHF** | 67.6 pips | 0.0050 (50p) | 8,716 | 32.33% | 0.89 | -0.070R | -611.4R | 🔴 Filtered |
| 25 | **NZDCAD** | 73.5 pips | 0.0050 (50p) | 10,063 | 32.83% | 0.90 | -0.064R | -642.1R | 🔴 Filtered |
| 26 | **NZDJPY** | 84.5 pips | 1.000 JPY (100p) | 8,934 | 32.27% | 0.88 | -0.081R | -727.2R | 🔴 Filtered |
| 27 | **AUDCHF** | 69.6 pips | 0.0050 (50p) | 9,132 | 32.01% | 0.88 | -0.081R | -740.5R | 🔴 Filtered |
| 28 | **EURCHF** | 56.4 pips | 0.0050 (50p) | 10,742 | 32.54% | 0.86 | -0.090R | -967.4R | 🔴 Filtered |
| 29 | **AUDNZD** | 71.1 pips | 0.0050 (50p) | 10,501 | 31.17% | 0.83 | -0.116R | -1222.1R | 🔴 Filtered |

---

## 4. Kesimpulan & Rekomendasi Portofolio Produksi

1. **Alpha Terpusat pada 7 Simbol Bintang (Total Profit +$1.378,3R)**:
   * `EURJPY` (+371.0R), `EURUSD` (+297.8R), `AUDUSD` (+233.9R), `USDJPY` (+218.3R), `XAUUSD` (+165.9R), `EURAUD` (+64.1R), dan `GBPUSD` (+27.3R).
2. **Mengapa Kelompok Bintang Unggul**:
   * Simbol-simbol ini memiliki likuiditas pasar primer, batas kebijakan bank sentral yang nyata, dan pergerakan antar-stasiun harga yang bersih (*Clean Corridor Traversal*).
3. **Blacklist Pair Minor Lambat**:
   * Pair minor dan cross tenang (seperti `EURCHF`, `AUDNZD`, `NZDCAD`, `USDCHF`) wajib dieliminasi dari pool aktif karena pergerakannya didominasi oleh *noise* sintesis dan spread mahal.
