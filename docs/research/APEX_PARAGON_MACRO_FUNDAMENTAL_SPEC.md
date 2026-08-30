# Apex Paragon Macro Fundamental Engine: Complete Institutional Specification

> **Dokumen Arsitektur & Spesifikasi Resmi**: Integrasi Analisis Fundamental Makro 40%, Kalender Ekonomi Dual-Source, Peluruhan Eksponensial *Half-Life*, Sistem Kualitas Setup 4-Grade (Grade S s/d B), dan 7 Master *Hard Risk Veto Flags*.

---

## 1. Executive Summary & Design Philosophy

Dalam filosofi **Apex Paragon Atlas**, analisis fundamental **bukanlah alat pemicu entri mandiri (bukan standalone alpha generator)**. Analisis fundamental bertindak sebagai **Multi-Layer Bias Filter, Dynamic Risk Modifier, dan Institutional Trap Detector** yang beroperasi secara harmonis di atas **Pure Quant MSE 6-TF Native Sockets**, **Boitoki CSM Basket Flow**, dan **LuxAlgo Smart Money Concepts (SMC)**.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION LAYER (Every 15-30 Min)                          │
│  • Primary Calendar : ForexFactory Official JSON Feed (Fastly CDN, Folder Impacts)     │
│  • Bank Holiday     : Active Bank Holiday Detection (UK/US/EU Thin Liquidity Guard)   │
│  • Fallback Calendar: TradingView Economic Calendar API                                │
│  • Live Headlines   : TradingView Real-Time Forex Headlines Feed                       │
│  • Central Bank Data: 8 Global Benchmark Policy Rates & Policy Cycles                  │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   APEX PARAGON MACRO FUNDAMENTAL ENGINE (Apex FE)                      │
│  • Dynamic Regime-Aware Weighting (The Storm vs The Calm vs Normal)                    │
│  • Tiered Half-Life Exponential Decay (4h Minor / 12h Medium / 36h Major)              │
│  • 8-Currency Composite Fundamental Score [-1.00, +1.00]                               │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                   MSE 6-TF NATIVE CONVERGENCE & SETUP GRADING ENGINE                   │
│  👑 GRADE S  : God-Tier Setup (MSE Sockets + SMC + CSM + Fundamental 100% Aligned)    │
│  🟢 GRADE A+ : High Conviction (Technical Setup + Macro Fundamental Support)           │
│  🟡 GRADE A  : Pure Technical Mode (Priced-In Equilibrium / Normal Flat Macro)         │
│  ⚪ GRADE B  : Defensive Reduced Size (Bank Holiday / Mild Friction Sizing 0.50x)     │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│               STAGE 2 3-LLM JURY & 7 MASTER HARD RISK VETO GATES                       │
│  Pass 1 (~3s) : OpenAI o4-mini (Structure) + Gemini 3.1-Flash (Target Feasibility)    │
│  Pass 2 (~1.5s): DeepSeek V4-Flash (Chief Risk Officer & 7 Master Hard Veto Audit)     │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Dual-Source Data Ingestion Layer & Bank Holiday Guard

Arsitektur data mengadopsi struktur multi-provider guna menjamin **Zero Downtime, Akurasi Folder 100%, dan Proteksi Libur Pasar**:

1. **🏆 Primary Provider (ForexFactory JSON CDN)**:
   - Endpoint: `https://nfs.faireconomy.media/ff_calendar_thisweek.json` (Fastly CDN global, latensi <0.2s).
   - Menyediakan data terstruktur: `actual`, `forecast`, `previous`, dan klasifikasi folder resmi (🔴 `HIGH`, 🟠 `MEDIUM`, 🟡 `LOW`, 🏖️ `HOLIDAY`).
2. **🏖️ Deteksi Hari Libur Bank (*Bank Holiday Guard*)**:
   - Jika pasar utama libur (contoh: *UK Summer Bank Holiday*), sistem otomatis mendeteksi kondisi likuiditas tipis (*shallow order-book*).
   - Menurunkan grade setup ke **GRADE B**, memangkas ukuran lot menjadi **$0.50\times$**, dan melarang keras mengejar *breakout* di sesi sepi.
3. **🛡️ Fallback Provider (TradingView API & Central Bank Overrides)**:
   - Endpoint: `https://economic-calendar.tradingview.com/events`
   - Beralih otomatis jika CDN utama mengalami gangguan.
4. **📡 Live Headlines & Geopolitics (TradingView Real-Time Forex Stream)**:
   - Endpoint: `https://news-headlines.tradingview.com/v2/headlines?category=forex&client=web&lang=en`
   - 3-Stage Filtering Funnel:
     * *Stage 1*: Penandaan Entitas Mata Uang (Fed, ECB, BOE, BOJ, SNB, RBA, BOC, RBNZ).
     * *Stage 2*: Pencocokan Kata Kunci Makro (*Rate Hike/Cut, Hawkish/Dovish, Sanctions, Tariff, War*).
     * *Stage 3*: Filter Kedaluwarsa ($\le 12\text{ jam}$).
     * *Apex Flat Principle*: Jika tidak ada guncangan berita akut, skor sentimen headline default ke `0.00 (FLAT)`.

---

## 3. Siklus Hidup Katalis Berita Makro (4-Stage Lifecycle)

Pasar valas institusional bereaksi terhadap data ekonomi melalui **4 Fase Waktu Resmi**:

```
  [0 - 30 Menit]       [30m - 6 Jam]         [1 - 3 Hari]           [4+ Hari / Menjelang Event]
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐
│ 1. THE STORM    │ ➔│ 2. THE CALM     │ ➔│ 3. THE REGIME   │ ➔│ 4. PRICED-IN EQUILIBRIUM    │
│ (Volatility     │  │ (Institutional  │  │    EXTENSION    │  │ (Wait-and-See Consolidation │
│  Shock & Trap)  │  │  Drift)         │  │ (Continuation)  │  │  Pure Technical SMC/MSE)    │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘
```

| Fase | Durasi Waktu | Karakteristik Pasar | Aksi Sistem Bot |
|---|---|---|---|
| **1. THE STORM** | $0 - 30\text{ Menit}$ | Perang algo HFT, spread melebar $5-10\times$, sapuan likuiditas liar (*whipsaw*). | **FREEZE / HARD VETO** (Mencegah kerugian *slippage*). |
| **2. THE CALM** | $30\text{m} - 6\text{ Jam}$ | Spread normal rapat, *Real Money Funds* mulai mereposisi modal teratur (*orderly drift*). | **FAVOR ENTRY** (Mengeksekusi searah kejutan data dengan R:R terbaik). |
| **3. REGIME EXTENSION** | $1 - 3\text{ Hari}$ | Berita menjadi tema dominan mingguan; membentuk tangga harga rapi (*HH/HL*). | **TREND-ALIGNED PULLBACK (M2/M3)** di zona diskon/premium. |
| **4. PRICED-IN EQUILIBRIUM** | $4+\text{ Hari}$ | Berita telah 100% terserap pasar (*priced-in*); volatilitas mengompresi di sekitar 50% Dealing Range. | **PURE TECHNICAL MODE** (Murni MSE Sockets & SMC dengan ukuran standar). |

---

## 4. Formula Peluruhan Eksponensial (*Tiered Half-Life Decay*)

Dampak berita tidak berhenti secara kaku di jam ke-6, melainkan meluruh secara matematis mengikuti rumus eksponensial *Half-Life*:

$$\text{Score}(t) = \text{Score}_0 \cdot e^{-\lambda \cdot \Delta t}$$

$$\lambda = \frac{\ln(2)}{T_{1/2}}$$

```
Impact Score
  1.0 ┼─────────────────────── Tier 1 (FOMC / NFP / CPI / Rate Decision) ─ Half-Life 36h
      │                      ╲
  0.5 ┼────────────── Tier 2 (PMI / GDP / Retail Sales) ─ Half-Life 12h
      │              ╲        ╲
  0.2 ┼────── Tier 3 (Minor Headlines / Speeches) ─ Half-Life 4h
      │      ╲        ╲        ╲
  0.0 ┴──────┴────────┴────────┴────────┴────────┴────────┴────────► Waktu (Jam)
      0h     4h       8h      12h      24h      36h      48h
```

* **Tier 1 (Major FOMC, NFP, Core CPI, Keputusan Suku Bunga)**: **Half-Life $36\text{ Jam}$**.
* **Tier 2 (Medium PMI, GDP, Retail Sales, Unemployment Claims)**: **Half-Life $12\text{ Jam}$**.
* **Tier 3 (Minor Headlines, Komentar Geopolitik, Pidato Pejabat)**: **Half-Life $4\text{ Jam}$**.

---

## 5. Matriks Suku Bunga & Siklus 8 Mata Uang Utama (2026)

| Currency | Central Bank | Benchmark Rate | Policy Cycle | Bias Regime |
|---|---|---|---|---|
| **USD** | Federal Reserve (Fed) | **$5.50\%$** | HOLD / CUT_WATCH | NEUTRAL_HAWKISH |
| **EUR** | European Central Bank (ECB) | **$3.75\%$** | CUT_CYCLE | DOVISH |
| **GBP** | Bank of England (BOE) | **$5.00\%$** | CUT_CYCLE | MODERATE_DOVISH |
| **JPY** | Bank of Japan (BOJ) | **$0.25\%$** | HIKE_CYCLE | HAWKISH_HIKE |
| **CHF** | Swiss National Bank (SNB) | **$1.25\%$** | CUT_CYCLE | DOVISH |
| **AUD** | Reserve Bank of Australia (RBA) | **$4.35\%$** | HOLD / HAWKISH | HAWKISH |
| **CAD** | Bank of Canada (BOC) | **$4.50\%$** | CUT_CYCLE | DOVISH |
| **NZD** | Reserve Bank of New Zealand (RBNZ) | **$5.25\%$** | CUT_CYCLE | DOVISH |

---

## 6. Matriks Konflik 4 Tingkat (*4-Tier Gating Matrix*)

Untuk setiap pasangan mata uang ($Base / Quote$):

$$\Delta_{\text{Fund}} = \text{Score}(Base) - \text{Score}(Quote)$$

$$\Delta_{\text{Carry}} = \text{Rate}(Base) - \text{Rate}(Quote)$$

```
                         Quote Currency Score
                 Weak (-1.0)       Flat (0.0)      Strong (+1.0)
             ┌─────────────────┬─────────────────┬─────────────────┐
Strong (+1.0)│ 🟢 VALID         │ 🟢 WEAK         │ 🔴 CURRENCY     │
             │   CONVERGENCE   │   CONVERGENCE   │   CONFLICT      │
             │   (Favor Buy)   │   (Favor Buy)   │   (Chop / Block)│
             ├─────────────────┼─────────────────┼─────────────────┤
Base   (0.0) │ 🟢 WEAK         │ ⚪ NO_SIGNAL    │ 🟢 WEAK         │
Score        │   CONVERGENCE   │   (Pure Tech    │   CONVERGENCE   │
             │   (Favor Buy)   │    SMC & MSE)   │   (Favor Sell)  │
             ├─────────────────┼─────────────────┼─────────────────┤
Weak   (-1.0)│ 🔴 CURRENCY     │ 🟢 WEAK         │ 🟢 VALID         │
             │   CONFLICT      │   CONVERGENCE   │   CONVERGENCE   │
             │   (Low Convict) │   (Favor Sell)  │   (Favor Sell)  │
             └─────────────────┴─────────────────┴─────────────────┘
```

1. 🟢 **`VALID_CONVERGENCE` ($|\Delta_{\text{Fund}}| \ge 0.35$ atau Selisih Bunga $|\Delta_{\text{Carry}}| \ge 2.0\%$)**:
   - **Kondisi**: Arah fundamental sangat tajam (Base Kuat vs Quote Lemah atau sebaliknya).
   - **Aksi**: **Full Sizing ($1.0\times$)** searah fundamental.
2. 🟢 **`WEAK_CONVERGENCE` ($0.15 \le |\Delta_{\text{Fund}}| < 0.35$)**:
   - **Kondisi**: Kemiringan makro moderat (Satu mata uang aktif, satu mata uang netral).
   - **Aksi**: **Diizinkan dengan Konfirmasi Teknikal M1/M2/M3 ($1.0\times$)**.
3. ⚪ **`NO_SIGNAL_FLAT` ($|\Delta_{\text{Fund}}| < 0.15$)**:
   - **Kondisi**: Fundamental kedua mata uang tenang (*Priced-In Equilibrium*).
   - **Aksi**: **Pure Technical Mode**. Sistem beroperasi $100\%$ berdasarkan **MSE 6-TF Sockets & SMC**.
4. 🔴 **`CURRENCY_CONFLICT` (Kedua Skor $\ge +0.25$ atau Kedua Skor $\le -0.25$)**:
   - **Kondisi**: Perang tarik tambang kedua mata uang.
   - **Aksi**: **Hard Risk Veto (Hold / Reject Trade)**.

---

## 7. Sistem Kualitas Setup 4-Grade (*Setup Quality & Dynamic Sizing*)

Sistem ini **tidak memblokir trade sembarangan**, melainkan menyesuaikan tingkat keyakinan dan ukuran lot:

| Setup Grade | Kondisi Pasar | Lot Sizing Modifier | Strategi Target TP |
|---|---|---|---|
| 👑 **GRADE S** | Level MSE + SMC + Arus CSM + Fundamental **100% Konvergen** | **Full Size ($1.0\times$)** | Target Extended TP2 ($1.2\times$ R:R Boost) |
| 🟢 **GRADE A+** | Setup Teknikal Tajam + Angin Fundamental Mendukung | **Full Size ($1.0\times$)** | Target Standar (TP1 $50\%$ + TP2 Stasiun) |
| 🟡 **GRADE A** | Pasar Tenang Normal / *Priced-In Equilibrium (Flat)* | **Standard Size ($1.0\times$)** | Murni Eksekusi Teknikal (MSE Sockets & SMC) |
| ⚪ **GRADE B** | Ada Friksi Makro Ringan atau Sedang Terjadi *Bank Holiday* | **Reduced Size ($0.50\times - 0.75\times$)** | Target Defensif (Kunci Cepat BEP & TP1) |

---

## 8. 7 Master Institutional Hard Risk Veto Flags

Daftar tameng risiko telah dirampingkan dari 12 flag redundan menjadi **7 Master Flags**:

```
┌────────────────────────────────────────────────────────────────────────┐
│ A. LEVEL GRAFIK TEKNIKAL (Single-Pair Price Action)                    │
│ 1. COUNTER_TREND_MOMENTUM : Melawan tren utama H4/D1 atau air terjun.  │
│ 2. LIQUIDITY_TRAP         : Pucuk EQH/EQL, Judas Swing, beli di SBR.   │
│ 3. IMPULSE_CHASE          : FOMO mengejar lilin panjang tanpa retest.  │
├────────────────────────────────────────────────────────────────────────┤
│ B. LEVEL KERANJANG MATA UANG GLOBAL (Boitoki CSM Basket Flow)          │
│ 4. SYSTEMIC_CURRENCY_DUMP : Keranjang mata uang dibuang di 7 pair CSM. │
├────────────────────────────────────────────────────────────────────────┤
│ C. LEVEL MAKRO FUNDAMENTAL & BERITA (Apex Paragon Fundamental Engine)  │
│ 5. HIGH_IMPACT_NEWS       : Tepat di jendela badai rilis (The Storm).  │
│ 6. CURRENCY_CONFLICT      : Perang tarik tambang kedua mata uang.      │
│ 7. MACRO_HEADWIND         : Melawan selisih suku bunga Bank Sentral.   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 9. Format Memo Prompt Stage 2 Jury

Injeksi data ke Stage 2 Jury prompt bersifat deterministik dalam Bahasa Inggris:

```yaml
### APEX PARAGON MACRO FUNDAMENTAL BRIEFING (40% Weight)
• Base Currency (GBP)   : Score -0.08 | CB Rate: 5.0% (CUT_CYCLE) | Phase: PRICED_IN_EQUILIBRIUM
• Quote Currency (USD)  : Score -0.40 | CB Rate: 5.5% (HOLD / CUT_WATCH) | Phase: PRICED_IN_EQUILIBRIUM
• Fundamental Net Delta  : +0.32 | Net Carry Spread: -0.50%
• Currency Conflict Gate : 🟢 WEAK CONVERGENCE (TILT BUY)
• Setup Classification   : GRADE_A (Sizing: 1.0x)
• Macro Directive        : ALLOW_BUY_WITH_TECH_CONFIRMATION (Mild macro drift +0.32)
• Recent Catalysts/Decay :
  • [Trading Economics] Pound Slips on Stronger US Dollar (0.0h ago)
  • [Binance News] Dollar Rises After Fed Chair Warsh Remarks (0.0h ago)
```

---

## 10. Panduan Perintah Telegram (2-Way Controller)

* **`/fundamental`** (alias `/fund`, `/bias`) $\rightarrow$ Menampilkan Scoreboard 8 Mata Uang & Rekomendasi Pair Konvergen.
* **`/fund <pair>`** (contoh `/fund GBPUSD`) $\rightarrow$ Menampilkan evaluasi mendalam per-pair, skor base/quote, fase peluruhan, dan status *conflict gate*.
* **`/macro <pair>`** $\rightarrow$ Menampilkan 6-TF Top-Down Strategic Directive terintegrasi dengan Grade Fundamental.
* **`/news`** $\rightarrow$ Menampilkan Jadwal Kalender Berita & Peringatan *Bank Holiday*.
* **`/help`** $\rightarrow$ Direktori lengkap seluruh command bot.
