# Hasil Riset Kuantitatif Bebas Bias & Temuan Edge Statistik

> Dokumen ini merangkum seluruh hasil pengujian statistik kuantitatif (*lookahead-bias-free*) selama 3–4 tahun pada data historis broker live VTMarkets (Mei 2022 – Agustus 2026).
> 
> **Kriteria Kelolosan Edge:**
> - Jumlah sampel $n \ge 100$
> - Nilai p-value $p < 0.05$ (uji z-score statistik)
> - Batas bawah Interval Kepercayaan 95% ($CI_{95\% \text{ low}} > 0$)
> - Biaya spread broker sudah dipotong (*subtracted*) dari tiap trade
> - Sinyal dieksekusi pada Open candle berikutnya (bebas bias intip masa depan)

---

## 1. Temuan Edge Pola Candlestick FX H1 (Riset 16 Agustus 2026)

Seluruh pola candlestick yang terbukti memiliki keunggulan statistik riil adalah **pola Bearish (Sell) yang tereksekusi pada sesi New York (WIB malam)**:

### Ringkasan Edge per Pasangan Mata Uang:

* **`GBPCHF-ECNc` (4 EDGE Utama):**
  * `Bearish Sweep` (R:R 1:2) | Win Rate **55.5%** | EV **+0.65** ($n=254$, $p=0.039$) — *Performa Terbaik!*
  * `Bearish Engulfing` (R:R 1:1.5) | Win Rate **59.4%** | EV **+0.47** ($n=475$)
  * `Inside Bar Bearish` (R:R 1:1.5) | Win Rate **58.8%** | EV **+0.46** ($n=447$)
  * `Bearish Pin Bar` (R:R 1:1.5) | Win Rate **55.0%** | EV **+0.36** ($n=444$)

* **`EURCHF-ECNc` (4 EDGE Utama):**
  * `Inside Bar Bearish` (R:R 1:1.5) | Win Rate **59.2%** | EV **+0.46** ($n=417$)
  * `Bearish Engulfing` (R:R 1:1.5) | Win Rate **57.0%** | EV **+0.41** ($n=528$)
  * `Bearish Sweep` (R:R 1:1.5) | Win Rate **55.9%** | EV **+0.38** ($n=272$)
  * `Bearish Pin Bar` (R:R 1:1) | Win Rate **60.6%** | EV **+0.19** ($n=439$)

* **`GBPNZD-ECNc` (4 EDGE Utama):**
  * `Inside Bar Bearish` (R:R 1:1) | Win Rate **63.6%** | EV **+0.27** ($n=385$)
  * `Bearish Engulfing` (R:R 1:1) | Win Rate **61.6%** | EV **+0.23** ($n=485$)
  * `Bearish Sweep` (R:R 1:1) | Win Rate **60.5%** | EV **+0.20** ($n=339$)
  * `Bearish Pin Bar` (R:R 1:1) | Win Rate **57.9%** | EV **+0.15** ($n=451$)

* **`EURAUD-ECNc` (3 EDGE Utama):**
  * `Bearish Pin Bar` (regime=range, R:R 1:1) | Win Rate **64.0%** | EV **+0.27** ($n=175$)
  * `Inside Bar Bearish` (session=ny, R:R 1:1) | Win Rate **63.5%** | EV **+0.26** ($n=452$)
  * `Bearish Engulfing` (session=ny, R:R 1:1) | Win Rate **55.7%** | EV **+0.11** ($n=515$)

* **`EURJPY-ECNc` (2 EDGE Utama):**
  * `Bearish Sweep` (R:R 1:1) | Win Rate **58.8%** | EV **+0.17** ($n=374$)
  * `Bearish Pin Bar` (R:R 1:1) | Win Rate **55.6%** | EV **+0.10** ($n=423$)

* **`GBPAUD-ECNc`:**
  * Memiliki **15+ EDGE** valid dengan performa sangat konsisten di R:R 1:1 (EV +0.22 s/d +0.31).
  * `Inside Bar Bearish` (session=ny, R:R 1:1): Win Rate **65.6%** | EV **+0.31** ($n=459$).
  * `Bearish Engulfing` (session=ny, R:R 1:1): Win Rate **61.2%** | EV **+0.22** ($n=516$).

---

## 2. Perankingan Komprehensif Pair Forex (DeepSeek Kuantitatif)

Berdasarkan kelimpahan, kualitas, dan konsistensi *EDGE* tervalidasi dari riset statistik terhadap 11 pair Forex (H1) dan Emas (M15):

🏆 **Top 3 Pair Terkuat (Edge Paling Banyak & Konsisten):**
1. **`GBPCHF-ECNc` (Juara Mutlak):** 36 EDGE, 17 di antaranya memiliki EV > 0.20. Sangat dominan di sesi New York (9 EDGE). Pola terbaik: `Bearish Sweep` sesi NY R:R 1:2 (EV **+0.65**, $n=254$).
2. **`EURCHF-ECNc` (Total Edge Terbanyak):** 37 EDGE, 12 di antaranya memiliki EV > 0.20. Dominan di sesi NY & London. Pola terbaik: `Inside Bar Bearish` sesi NY R:R 1:1.5 (EV **+0.46**).
3. **`CADCHF-ECNc` (Paling Terdiversifikasi):** 27 EDGE, 8 di antaranya memiliki EV > 0.20. Konsisten meloloskan edge di 5 pola berbeda. Pola terbaik: `Bearish Sweep` sesi NY R:R 1:1.5 (EV **+0.43**).

🥈 **Kandidat Kuat Berikutnya (Pair Backup & Pengganti):**
4. **`AUDCHF-ECNc` (Peringkat 4):** 24 EDGE, 6 di antaranya memiliki EV > 0.20. Pola terbaik: `Inside Bar Bearish` sesi NY WR 70% (EV **+0.38 s/d +0.41**).
5. **`GBPNZD-ECNc`:** 17 EDGE, 4 di antaranya memiliki EV > 0.20. Edge merata di 4 pola berbeda.
6. **`GBPAUD-ECNc`:** 19 EDGE, 3 di antaranya memiliki EV > 0.20.

> *Catatan Kuantitatif: Seluruh 4 peringkat teratas dikuasai oleh cross CHF. Karakteristik Swiss Franc (safe haven) memiliki pergerakan harga bersih, stabil, dan kepatuhan tinggi pada pembalikan arah/mean-reversion di sesi NY.*

---

## 3. Temuan Confluence & Pembongkaran Mitos HTF Trend Alignment

Hasil pengujian terhadap **8.908 kombinasi confluence** (210 EDGE lolos):
* **Mitos "HTF Trend Alignment" Terbongkar:** Mengharuskan pola searah dengan tren HTF (EMA 50 vs 200) terbukti **tidak memiliki edge statistik yang kuat** (hanya meloloskan 2 EDGE lemah).
* **Kekuatan Counter-Trend di Resistance:** Mengambil pola bearish (Sell) saat HTF sedang naik (*counter-trend*) **di dekat area Resistance** (jarak $\le$ 0.5 ATR) terbukti menghasilkan edge yang sangat superior (contoh: EURCHF Inside Bar Bearish saat HTF sedang naik menghasilkan EV **+0.44**). Ini karena area resistance memberikan batas Stop Loss yang tipis dengan ruang Take Profit yang lebar.
* **Near Resistance (Penambah Edge Terkuat):** Pola bearish yang dipadukan dengan lokasi dekat resistance adalah filter terkuat:
  * `Bearish Pin Bar` GBPCHF dekat resistance: Win Rate **69.0%** | EV **+0.37** ($n=145$).
* **Sesi NY Tetap Juara:** Meloloskan 48 EDGE di semua 12 simbol trading. Sesi New York (WIB malam) adalah filter waktu terbaik.

---

## 4. Riset Pair CAD-EUR-GBP (18 Agustus 2026 — 3 Tahun H1)

Riset untuk mencari alternatif pengganti pair dengan spread lebar:
- **Spread Real Broker**: NZDCAD 2.2 pts | AUDCAD 3.4 | EURCAD 4.6 | EURNZD 5.2 | GBPCAD 7.4.
- **Hasil Edge**:
  - **`NZDCAD-ECNc` (JUARA):** 27 EDGE. `Bearish Engulfing` htf=up WR 63.2% EV +0.24 ($n=190$); `Inside Bar Bearish` London WR 62.3% EV +0.23; `Bearish Engulfing` NY WR 61.1% EV +0.20.
  - **`EURNZD-ECNc` (KUAT):** 22 EDGE. `Bearish Pin Bar` range WR 63.0% EV +0.23; NY WR 62.9% EV +0.22.
  - **`AUDCAD-ECNc` (SOLID):** 5 EDGE. `Bearish Engulfing` NY WR 62.1% EV +0.21.
  - **`EURCAD-ECNc` & `GBPCAD-ECNc`:** 0 EDGE (Gugur).

---

## 5. Riset Pair JPY (18 Agustus 2026 — 4 Tahun H1)

- **Spread Real Broker**: EURJPY 0.6 pts | CADJPY 4.8 | NZDJPY 5.8 | CHFJPY 7.0 | AUDJPY 7.0 | GBPJPY 10.4.
- **Hasil Edge**:
  - **`CHFJPY-ECNc` (TERKUAT):** 4 EDGE + 3 CANDIDATE. `Inside Bar Bearish` NY WR 62.1% EV +0.20; `Bearish Sweep` NY EV +0.14; CANDIDATE near_resistance R:R 1:2 EV +0.89.
  - **`AUDJPY-ECNc` (KUAT):** 4 EDGE + 4 CANDIDATE. `Inside Bar Bearish` NY WR 63.6% EV +0.22.
  - **`EURJPY-ECNc`:** 2 EDGE (`Bearish Sweep` NY EV +0.17, `Bullish Engulfing` London EV +0.14) + Double Bottom CANDIDATE (Spread termurah: 0.6 pts).
  - **`GBPJPY-ECNc`:** 1 EDGE lemah (EV +0.10) + spread 10.4 pts (Gugur).

---

## 6. Riset XAU M30 (17 Agustus 2026 — Backtest 4.23 Tahun)

- **Pola Candlestick M30**: **0 EDGE valid** (Pola candlestick mentah tidak bekerja di Emas).
- **Strategi Mekanis (Donchian / EMA / RSI)**:
  - **`Donchian50 Breakout BUY di sesi NY (20:00–05:00 WIB), R:R 1:1` $\rightarrow$ EDGE VALID** ($n=605$, WR 58.5%, $p=0.00001$, EV **+0.158**, CI 95% [+0.085, +0.237]). Konsisten 4 tahun berturut-turut.
  - **`Donchian20 Breakout BUY di NY, R:R 1:1` $\rightarrow$ EDGE VALID** ($n=786$, WR 56.2%, $p=0.0002$, EV **+0.111**).
- **Temuan Struktural Emas**:
  - **Asimetri Arah**: Seluruh breakout SELL Donchian negatif (WR 41–45%). **Hanya BUY yang memiliki edge di XAU**.
  - **Target Optimal**: Hanya R:R 1:1 yang lolos edge; R:R lebih tinggi (1.5 / 2 / 3) mengalami kejatuhan win rate drastis.

---

## 7. Pola Harmonik yang Dieliminasi (NO-EDGE)
Pengujian mandiri terhadap **1.068 kombinasi pola Harmonik** (Gartley, Bat, Butterfly, Crab) menghasilkan **1.067 NO-EDGE**. Pola Harmonik dibuang permanen karena performa tinggi di masa lalu terbukti sebagai *Small Sample Bias* ($n < 30$).

---

## 8. Profil DNA Kuantitatif EURUSD & Atlas 22-Pair SMC (Riset 26 Agustus 2026 — 55 Tahun)

### A. Bedah Karakteristik `EURUSD-ECNc`:
- **Peringkat Global**: Rank 7 dari 22 Pasangan Mata Uang.
- **Rasio Spread vs ADR**: Spread 10–12 pts vs ADR 74.4 pips (**$< 2\%$ friksi** — instrumen paling bersih dan likuid di dunia).
- **Edge Utama**:
  1. **`London Judas Sweep (14:00 – 16:00 WIB)`**: Sapuan semu High/Low sesi Asia yang langsung memantul kembali ke rentang dengan *rejection wick* $\ge 30\%$ memiliki Win Rate **58.4%**.
  2. **`SMC Liquidity Sweep H1 (10.7 Tahun)`**: Menghasilkan **Profit Factor 0.84** (Win Rate 42.0% pada R:R 2.2:1), setup terbaik di seluruh pengujian H1 EURUSD.
  3. **`H4 Macro Breakout (19 Tahun)`**: Menghasilkan Net Profit **+$7,300 (PF 1.13)** secara mekanikal mandiri tanpa filter AI.
- **Sesi Terbaik**: London Open (14:00–18:00 WIB) & NY Overlap (19:00–22:00 WIB). Sesi Tokyo dihindari (sideways / range sempit).

### B. Hukum Universal 22-Pair Atlas DNA:
1. **Kluster JPY (`USDJPY`, `GBPJPY`, `EURJPY`, `AUDJPY`, `CHFJPY`)**: Mesin *Trend Pullback*. Dilarang keras counter-trend; buy di diskon saat D1 Bullish.
2. **Kluster Swiss Franc (`GBPCHF`, `USDCHF`, `CHFJPY`)**: Benci breakout (+281% lebih unggul di *Mean Reversion*). Masuk saat harga menyentuh ujung Premium $\ge 80\%$.
3. **Kluster Gold & High Beta (`XAUUSD`, `GBPAUD`, `EURAUD`)**: Kapasitas ekspansi makro raksasa ($+\$36.8k$ di Gold H4). Wajib pasang TP bertingkat (TP1 1.0x & TP2 1.2x + Trailing Stop).
4. **Pasangan yang Dieliminasi dari Intraday (`EURCHF`, `EURGBP`, `NZDCAD`, `AUDCHF`)**: Rasio spread terhadap rentang harian terlalu besar, memicu *fee churn* jika ditradingkan intraday.
