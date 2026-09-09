# Design Specification: Currency Basket Structural Synchronization (CBSS) & ZCE Pro Architecture

> **Dokumen Spesifikasi Teknis & Desain Kuantitatif**  
> **Tanggal**: 9 September 2026  
> **Status**: DRAFT / VALIDATED BY EMPIRICAL BACKTEST  
> **Ruang Lingkup**: 8 Mata Uang Utama (USD, EUR, GBP, JPY, AUD, CAD, NZD, CHF) & Universe 26 Simbol FX  

---

## 1. Executive Summary & Problem Formulation

### 1.1. Latar Belakang Masalah
Dalam analisis teknikal dan algoritma trading konvensional, setiap pasangan mata uang (pair) sering kali dievaluasi secara terisolasi seolah-olah bergerak di ruang hampa. Hal ini memicu dua kegagalan kuantitatif mendasar:

1. **The Vacuum Fallacy (Geometric Bias)**:
   - Mengasumsikan bahwa ketiadaan hambatan di satu sisi (misalnya ruang atas $89\%$) secara otomatis berarti *probabilitas naik tinggi*.
   - **Kenyataan**: Ruang kosong hanyalah *kapasitas pergerakan jika terjadi pembalikan*, bukan probabilitas arah. Arah didikte oleh aliran modal makro (*capital flows*) dan kebijakan bank sentral.
2. **Blind Trend-Following into Multi-Year Fortress Walls (Kasus Riil EURAUD)**:
   - Pada saat tren H4/D1 menunjukkan penurunan kuat, indikator tren (ADX, Moving Average, Momentum) memicu setup kelanjutan tren (*continuation / breakdown* seperti M3 Breakout Retest atau M4 Systemic Flow).
   - Namun, harga ternyata sedang menabrak **Dinding Terendah 2 Tahun / Multi-Year Extreme Wall (G3)** (contoh: EURAUD di `1.60815` yang merupakan titik terendah sejak November 2024).
   - Menjual di dasar lembah multi-tahun tepat di depan akumulasi likuiditas institusional menyebabkan order langsung terperangkap dalam *short squeeze* atau *violent absorption wick*.

### 1.2. Keterbatasan Currency Strength Matrix (CSM) Klasik
CSM standar (seperti Boitoki CSM berbasis rolling 24-bar H1) mengukur *momentum harga jangka pendek*. Namun, CSM mudah berfluktuasi oleh *noise* intrahari dan **tidak memahami koordinat geometris horizontal** (apakah mata uang yang sedang menguat/melemah itu berada di tengah ruang kosong atau sudah menabrak dinding penahan makro).

---

## 2. Fondasi Teoretis: 3 Dimensi Aliran Pasar Finansial

Sistem **CBSS (Currency Basket Structural Synchronization)** memadukan 3 dimensi untuk membaca timing pergerakan mata uang secara global:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       SISTEM KOGNISI 3 DIMENSI CBSS                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [DIMENSI 1: STRUKTUR ZCE PRO]       [DIMENSI 2: REAL ECONOMY & PPP]       │
│  • Multi-TF (M30 s/d MN1)            • Purchasing Power Parity (PPP)       │
│  • Multi-Horizon (50–500 bar)        • Terms of Trade & Neraca Dagang      │
│  • Basket Synchronization (8 Currencies) • Valuation Stretch (Deviasi Mean) │
│                        │                               │                    │
│                        └───────────────┬───────────────┘                    │
│                                        ▼                                    │
│                       [DIMENSI 3: INSTITUTIONAL SFP]                        │
│                       • Stop-Loss Hunt / Liquidity Grab                     │
│                       • Absorption Footprint                                │
│                       • Strict Reclaim Rule (H1 Close > Wall)               │
│                                        │                                    │
│                                        ▼                                    │
│              HASIL: SYSTEMIC BASKET TIDAL WAVE / REVERSAL                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1. Dimensi 1: Fenomena "Tunggu-Tungguannya" (Cross-Pair Lead-Lag Desynchronization)
Mengapa sebuah mata uang (misalnya EUR) tidak bergerak serempak di seluruh 7 pasangannya pada menit yang sama?
- **Penyebab**: Setiap pasangan mata uang memiliki **lanskap rintangan geometris lokal (D1/W1 G3 Walls) yang berbeda**.
- **Kasus Riil Audit EUR (September 2026)**:
  - `EURAUD`: Sudah menabrak benteng terendah 2 tahun (**hanya berjarak 3.2 pips dari Floor G3**). EURAUD adalah *Lead Pair* yang sampai duluan di garis akhir.
  - `EURNZD`: Masih meluncur di tengah jalan (**berjarak 31.6 pips di atas lantainya**).
  - `EURCAD`: Tertahan 18.2 pips di bawah plafon.
  - `EURUSD` & `EURGBP`: Terkunci dalam *tight chamber compression* (5–13 pips).
- **Hukum "Tunggu-Tungguannya"**:
  - `EURAUD` tidak dapat menembus lantai 2 tahun sendirian jika 6 pasangan EUR lainnya masih netral atau tertahan di chamber masing-masing.
  - `EURAUD` terpaksa **berhenti dan berkonsolidasi (*stall / basing*)** menunggu pasangan sekeranjangnya menyelesaikan siklus perjalanannya.

### 2.2. Dimensi 2: Ekonomi Riil & Paritas Daya Beli (Purchasing Power Parity / Terms of Trade)
Pasar valas pada akhirnya melayani perdagangan internasional riil:
- Ketika EURAUD berada di titik terendah multi-tahun (`1.6090` vs rata-rata 5 tahun `1.6800`):
  - **Bagi Pengusaha / Warga Eropa**: Dolar Australia (AUD) menjadi **sangat mahal**. Biaya mengimpor komoditas (bijih besi, batubara, gandum) dari Australia melonjak. Reaksi rasional: *Menunda atau memangkas kontrak impor dari Australia* $\rightarrow$ **Volume penjualan EUR untuk membeli AUD anjlok**.
  - **Bagi Pengusaha / Warga Australia**: Euro menjadi **sangat murah (diskon besar)**. Mengimpor mesin pabrik Jerman, mobil Eropa, produk farmasi, atau liburan ke Eropa menjadi sangat terjangkau. Reaksi rasional: *Memborong barang impor dari Eropa* $\rightarrow$ **Pengusaha Australia menukar AUD ke EUR dalam volume masif untuk membayar pabrik di Eropa**.
- **Gaya Pegas Neraca Perdagangan**:
  Deviasi nilai tukar ekstrem dari nilai wajarnya secara alami menciptakan **tekanan beli struktural pada mata uang yang terdiskon (EUR)** dan **tekanan jual pada mata uang yang overvalued (AUD)**.

### 2.3. Dimensi 3: Mekanika Likuiditas Institusional (Stop-Loss Hunt & SFP Reclaim)
Institusi besar tidak pernah melakukan akumulasi posisi beli secara "membabi buta" di atas level support:
1. **Kebutuhan Counterparty Liquidity**:
   - Untuk membeli volume raksasa (ratusan juta EUR), institusi membutuhkan likuiditas jual lawan yang masif agar harga tidak melonjak (*slippage*).
2. **The Liquidity Pool**:
   - Tepat di bawah lantai 2 tahun (`1.60815`) berkumpul ribuan order *Stop Loss* posisi Buy ritel (yang dieksekusi sebagai *Market Sell Orders*) dan order *Sell Stop* dari *breakout traders*.
3. **Mekanisme Sapuan (The Hunt)**:
   - Institusi sengaja membiarkan harga menusuk ke bawah `1.60815` (misalnya ke `1.6060`–`1.6075`) bertepatan dengan rilis berita untuk memanen likuiditas jual tersebut.
   - Di zona itulah institusi memasang *Passive Buy Limit Orders* dalam volume besar untuk melahap semua barang obral (*absorption*).
4. **The Footprint (SFP Reclaim Rule)**:
   - Sistem dilarang menebak dasar dengan Buy Limit pasif.
   - Sistem wajib menunggu **bukti fisik penutupan candle H1 kembali di atas level kunci (`Close > 1.60815`) dengan sumbu bawah panjang ($\ge 35\%$)**. Penutupan di atas level membuktikan bahwa penjual telah kehabisan inventaris dan penembusan tersebut sah sebagai *False Breakout / Liquidity Grab*.

---

## 3. Pembuktian Empiris: Hasil Backtest Path-Dependent (15 Bulan MT5)

Untuk memastikan bahwa hipotesis ini bukan sekadar narasi teoretis, dilakukan simulasi backtest *path-dependent* (menguji urutan sentuhan TP vs SL secara kronologis bar-per-bar) pada **7.000 candle H1 (~15 bulan data historis broker MT5)** mencakup 18 pair dari 3 keranjang utama (EUR, USD, JPY):

```
Dataset: 7.000 H1 Bars (Juli 2025 – September 2026)
Total Peristiwa Tabrakan Dinding 200-Bar Makro (N): 2.009 Events
Parameter Trade:
- Continuation (Breakout): SL = 0.8x ATR, TP = 1.2x ATR (1.5:1 RR)
- Reversal (SFP / Bounce): SL = 0.6x ATR di balik dinding, TP = 1.2x ATR (2.0:1 RR)
```

### Tabel Hasil Backtest Kuantitatif:

| Kategori Sinkronisasi Keranjang | Mode Trade | Sample ($N$) | Win Rate (WR) | Wilson Score 95% CI | Expected Value ($EV$) | Profit Factor (PF) | Kesimpulan Statistik |
|---|:---:|:---:|:---:|:---:|:---:|:---:|---|
| **ISOLATED COLLISION**<br>*(Keselarasan Keranjang $\le 29\%$)* | **Continuation (Breakout)** | 77 | <mark>**33.8%**</mark> | [24.2% – 44.9%] | <mark>**$-0.16R$**</mark> | <mark>**0.76**</mark> | **RUGI (Losing Trade)** |
| *(Kasus EURAUD di 3.2p dari lantai)* | **Reversal (Bounce / SFP)** | 77 | **45.5%** | [34.8% – 56.5%] | <mark>**$+0.36R$**</mark> | <mark>**1.67**</mark> | **EDGE TINGGI (Profitable)** |
| **MIXED BREADTH**<br>*(Keselarasan Keranjang $30\% - 70\%$)* | **Continuation (Breakout)** | 310 | 37.1% | [31.9% – 42.6%] | $-0.07R$ | 0.88 | Sub-Optimal |
| | **Reversal (Bounce / SFP)** | 310 | 40.0% | [34.7% – 45.5%] | $+0.20R$ | 1.33 | Moderat |
| **STRONG_SYNC**<br>*(Keselarasan Keranjang $\ge 71\%$)* | **Continuation (Breakout)** | 1.622 | 39.1% | [36.7% – 41.5%] | $-0.02R$ | 0.96 | Breakeven |
| *(Armada Keranjang Selaras)* | **Reversal (Bounce / SFP)** | 1.622 | 40.6% | [38.3% – 43.0%] | $+0.22R$ | 1.37 | Stabil Positif |

### Temuan Kunci Backtest:
1. **Edge Negatif pada Continuation Terisolasi ($PF = 0.76$)**:
   - Membuka trade continuation (misalnya SELL EURAUD saat menabrak lantai 2 tahun sendirian) menghasilkan kerugian dalam 2 dari 3 trade. Ini membuktikan secara matematis bahwa fenomena *Isolated Barrier Collision* adalah jebakan likuiditas.
2. **Edge Positif Signifikan pada SFP Reversal ($PF = 1.67, EV = +0.36R$)**:
   - Menunggu harga menyapu dinding terisolasi lalu mengambil posisi *Reversal SFP* menghasilkan profit factor **1.67** dengan ekspektasi positif $+0.36R$ per trade.

---

## 4. Arsitektur Teknis Sistem CBSS (Global untuk 26 Pair & 8 Valas)

Sistem CBSS diimplementasikan secara universal di atas arsitektur ZCE yang sudah ada, memperluas ZCE dari 2D (*Timeframe $\times$ Horizon*) menjadi 3D (*Timeframe $\times$ Horizon $\times$ Currency Basket Space*).

### 4.1. Definisi Matriks Keranjang 8 Mata Uang Utama
Sistem mengelompokkan 26 pair terkurasi ke dalam 8 keranjang mata uang konstituen ($C \in \{\text{USD, EUR, GBP, JPY, AUD, CAD, NZD, CHF}\}$):

$$\text{Basket}(C) = \{P \in \text{Universe} \mid C \in \text{Base}(P) \cup \text{Quote}(P)\}$$

| Mata Uang ($C$) | Pasangan Konstituen dalam Universe 26 FX ($N \ge 6$) |
|:---:|---|
| **EUR** | EURUSD, EURGBP, EURJPY, EURCHF, EURAUD, EURCAD, EURNZD (7 pairs) |
| **USD** | EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD (7 pairs) |
| **GBP** | GBPUSD, EURGBP, GBPJPY, GBPCHF, GBPAUD, GBPCAD, GBPNZD (7 pairs) |
| **JPY** | USDJPY, EURJPY, GBPJPY, AUDJPY, CADJPY, CHFJPY, NZDJPY (7 pairs) |
| **AUD** | AUDUSD, EURAUD, GBPAUD, AUDJPY, AUDCAD, AUDCHF, AUDNZD (7 pairs) |
| **CAD** | USDCAD, EURCAD, GBPCAD, CADJPY, AUDCAD, NZDCAD (6 pairs) |
| **NZD** | NZDUSD, EURNZD, GBPNZD, NZDJPY, AUDNZD, NZDCAD (6 pairs) |
| **CHF** | USDCHF, EURCHF, GBPCHF, CHFJPY, AUDCHF (5 pairs) |

### 4.2. Formulasi Kuantitatif CBSS

#### Metrik 1: Directional Basket Breadth Index ($\text{DBI}_C$)
Mengukur konsensus arah struktural seluruh pasangan dalam keranjang mata uang $C$:

$$\text{Role}(P, C) = \begin{cases} +1, & \text{jika } C = \text{Base}(P) \\ -1, & \text{jika } C = \text{Quote}(P) \end{cases}$$

$$\text{EffectiveTrend}(P, C) = \text{Trend}_{\text{D1}}(P) \times \text{Role}(P, C) \in \{-1, 0, +1\}$$

$$\text{DBI}_C = \frac{\sum_{P \in \text{Basket}(C)} \text{EffectiveTrend}(P, C)}{|\text{Basket}(C)|} \in [-1.0, +1.0]$$

- $\text{DBI}_C > +0.60$: *Basket Bullish Surge* (Mata uang $C$ menguat serempak).
- $\text{DBI}_C < -0.60$: *Basket Bearish Dump* (Mata uang $C$ melemah serempak).
- $-0.35 \le \text{DBI}_C \le +0.35$: *Basket Desynchronized / Mixed* (Fase tunggu-tungguannya).

#### Metrik 2: Barrier Proximity Classification per Pair
Untuk setiap pair $P$, dihitung jarak harga live ke Dinding Makro G3 terdekat ($F_1$ Floor atau $C_1$ Ceiling):

$$\Delta_{\text{Wall}}(P) = \frac{|\text{Price} - \text{Level}_{\text{G3}}|}{\text{ATR}_{\text{H1}}(P)}$$

- **`AT_THE_WALL`**: $\Delta_{\text{Wall}} \le 0.40\times\text{ATR}$ (Sedang menempel/menabrak benteng).
- **`IN_TRANSIT`**: $0.40 < \Delta_{\text{Wall}} \le 1.50\times\text{ATR}$ (Sedang bergerak di dalam koridor).
- **`EXPANSION_VOID`**: $\Delta_{\text{Wall}} > 1.50\times\text{ATR}$ (Ruang leluasa tanpa dinding dekat).
- **`TIGHT_CHAMBER`**: Jarak $(C_1 - F_1) < 1.0\times\text{ATR}$ (Terjepit kompresi bilateral).

#### Metrik 3: Basket Barrier Synchronization Index ($\text{BSI}_C$)
Mengukur keselarasan fase barrier di seluruh keranjang mata uang:

$$\text{BSI}_C = \frac{\text{Jumlah Pair dalam Arah yang Sama yang Mencapai Benteng / Barrier}}{\text{Total Pair dalam Keranjang}}$$

- Jika $\text{BSI}_C \le 0.30$ dan sebuah pair $P$ berada pada status `AT_THE_WALL` $\rightarrow$ Deklarasikan status **`ISOLATED_BARRIER_COLLISION`**.

---

## 5. Master Rules & Execution Gating Policy

Sistem menerapkan 3 aturan keras (*Hard Gating Rules*) pada Stage 1 Fast Radar (`market_scanner.py`) dan Consensus (`consensus.py`):

### Rule 1: Isolated Barrier Collision Veto (Anti-Premature Breakdown/Breakout)
- **Kondisi Pemicu**:
  1. Setup berjenis kelanjutan tren / penembusan: `M3_BREAKOUT_RETEST` atau `M4_SYSTEMIC_FLOW_CONTINUATION`.
  2. Jarak harga ke dinding lawan ZCE G3 (D1/W1) $\le 0.40\times\text{ATR}$ (status `AT_THE_WALL`).
  3. Keselarasan keranjang $\text{BSI} \le 0.35$ (keranjang desinkron / isolated).
- **Tindakan Sistem**:
  - **HARD BLOCK 100% (0 Order MT5, 0 Token LLM)**.
  - Reason Code: `[CBSS VETO] Isolated Barrier Collision: Pair at G3 wall while basket sync <= 35% (PF 0.76 avoidance)`.

### Rule 2: High-Conviction SFP Reversal Permission (Harvesting Absorption)
- **Kondisi Pemicu**:
  1. Setup berjenis pembalikan: `M1_UNIVERSAL_LIQUIDITY_SWEEP` (SFP).
  2. Terjadi sapuan (*sweep*) menembus Dinding Makro G3 dan harga berhasil ditutup kembali (*reclaim*) di atas/bawah level kunci dengan sumbu $\ge 35\%$.
  3. Status keranjang berada pada `ISOLATED_BARRIER_COLLISION` atau `MIXED`.
- **Tindakan Sistem**:
  - **FULL ALLOW (Eksekusi BUY/SELL SFP Reversal)**.
  - Target: $1.5R - 2.0R$ menuju titik tengah chamber (Equilibrium / EMA50 H1).
  - Reason Code: `[CBSS SFP PERMITTED] Macro Wall SFP with high edge absorption (Backtest PF 1.67)`.

### Rule 3: Systemic Basket Tidal Wave Release (Grade S Expansion)
- **Kondisi Pemicu**:
  1. $\ge 75\%$ pair dalam keranjang menyelesaikan kompresi barrier secara harmonis ($\text{BSI} \ge 0.75$).
  2. Konvergensi Fundamental Apex FE selaras ($\text{Delta} \ge 0.40$ atau Carry Spread searah).
  3. Velocity aliran mata uang $|z| \ge 1.50$.
- **Tindakan Sistem**:
  - Mengaktifkan mode **`GRADE_S_MACRO_EXPANSION`** pada pair-pair terbaik di keranjang.
  - Target diperlebar ke dinding G3 multi-horizon berikutnya ($2.5R - 3.5R$).
  - BEP dilonggarkan ke $65\%$ TP untuk memberikan ruang ayunan tren makro.

---

## 6. Rencana Implementasi & Roadmap Pengembangan

Penyelarasan ini akan diterapkan secara global (seluruh 26 simbol, 8 valas) tanpa hardcode per-simbol:

1. **Modul Analitik Mandiri**:
   - Membuat engine baru `src/analytics/basket_sync_engine.py` yang mengekstrak status D1/W1 G3 walls dari `macro_cache` dan menghitung $\text{DBI}_C$, status barrier, serta $\text{BSI}_C$ secara *zero-token sub-millisecond*.
2. **Integrasi ke Stage 1 Fast Radar (`market_scanner.py`)**:
   - Menghubungkan fungsi `evaluate_basket_sync()` ke dalam gerbang `_is_direction_allowed()` untuk memblokir penembusan prematur pada tabrakan terisolasi.
3. **Penyelarasan Dashboard Cockpit (`dashboard.py`)**:
   - Menambahkan visualisasi status keranjang pada panel dashboard (indikator sinkronisasi 8 mata uang dan radar jarak dinding).
4. **Verifikasi Regression & Unit Tests**:
   - Membuat test suite `tests/test_basket_sync_engine.py` dengan cakupan pengujian 100% untuk semua kasus edge.

---

> **Dokumen ini siap digunakan sebagai acuan implementasi kode produksi.**
