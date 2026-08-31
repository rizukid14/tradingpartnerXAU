# MASTER TECHNICAL SPECIFICATION DOCUMENT
## 2-Stage Quant Funnel Multi-LLM Consensus Autonomous Trading System
### (Strict Unanimous 3/3, Pure Quant 6-TF MSE & Single Policy Path Architecture)

**Target Platform**: MetaTrader 5 (`VTMarkets-Live 3`, Account `27556325`, Raw ECN, Magic `20260625`)  
**Trading Universe**: 26 Simbol Terkurasi (20 FX Majors/Crosses, 6 NZD Alpha Crosses, BTCUSD Weekend Rotation)  
**Consensus Protocol**: Strict Unanimous 3/3 Rule (Wajib 3/3 Model Searah; 2/3 atau Split = HOLD Otomatis)  
**Symmetry Architecture**: Dual-Directional Equivalence (100% Simetris BUY & SELL Logic Gates, SBR/RBS, CSM Matrix)  
**AI Mode**: `AI_FIXED_MODE = "triple"` (OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4-Flash CRO)  
**On-Demand Mode**: Dedicated OpenAI `o4-mini` + Pure Quant MSE 6-TF Socket Context  
**Zona Waktu**: Asia/Jakarta (WIB = GMT+7, MT5 Server GMT+3 + 4 Jam, Rollover 04:00 WIB)  
**Branch**: `quant-trade`

---

# 📚 Master Glossary & Standarisasi Istilah Proyek

Untuk mencegah kerancuan dan menjaga konsistensi di seluruh antarmuka (Terminal Bento HUD, Telegram Bot, Prompt LLM, dan Kode Sumber), berikut adalah glosarium istilah resmi komprehensif yang dikelompokkan ke dalam 5 pilar arsitektur:

### 1. Arsitektur Sistem & Multi-LLM Consensus
| Istilah Resmi | Komponen & Kepanjangan | Definisi & Makna Teknis | Peran & Parameter Sistem |
|---|---|---|---|
| ⚡ **`2-Stage Quant Funnel`** | Dua Tahap Penyaringan Kuantitatif | Arsitektur pemisahan antara pemindaian kuantitatif lokal 60s (Stage 1) dan audit AI berbayar (Stage 2). | Hemat ~85% token API; hanya 8–15 setup A+/hari lolos ke LLM. |
| 👥 **`Pass 1 & Pass 2`** | 2-Pass Sequential Cross-Examination | Protokol juri 3 AI: Pass 1 (o4-mini + Gemini Flash) analisis struktur; Pass 2 (DeepSeek CRO) audit Devil's Advocate + 24 bar M5. | Latensi total $\le 5.5\text{s}$; eliminasi halusinasi model tunggal. |
| ⚖️ **`Strict Unanimous 3/3`** | Konsensus Bulat 100% | Aturan mutlak di mana 3 model aktif wajib sepakat searah (3/3 BUY atau 3/3 SELL). | 2/3 atau Split Vote otomatis **HOLD** (Zero Tolerance Split). |
| 🚀 **`Split Boost (+25%)`** | Unanimous High-Confidence Split | Fitur pembagian 2 tiket posisi saat 3 AI sepakat bulat dengan keyakinan $\ge 75\%$. | 2 tiket @ $0.625\times$ base lot (Tiket 1 target standar, Tiket 2 trailing TP2). |
| 🛑 **`Hard Risk Veto`** | Hak Veto Mutlak CRO | 11 bendera penolakan instan oleh DeepSeek CRO (`COUNTER_TREND_MOMENTUM`, `FALLING_KNIFE_WATERFALL`, dll.). | Langsung membatalkan eksekusi jika mendeteksi anomali likuiditas. |
| 📝 **`CoT JSON Protocol`** | Chain-of-Thought JSON Protocol | Format respon JSON super-kompak: `trend ➔ velocity ➔ rr_valid ➔ signal ➔ confidence`. | Membatasi output ke ~35 token; respons <5s/simbol. |

### 2. Finite State Machine (FSM) & Symmetrical 4D Market State (V3)
| Istilah Resmi | Komponen & Kepanjangan | Definisi & Makna Teknis | Kondisi & Logika Pemicu |
|---|---|---|---|
| ⚙️ **`FSM`** | **Finite State Machine** | Model komputasi matematika status transisi terbatas yang mengontrol siklus hidup pasar secara deterministik. | Mengatur Direction, Phase, dan Permission (`BUY LOCKED != SELL ENABLED`). |
| 🧭 **`Direction FSM`** | Identitas Tren Makro (D1+H4) | Penentu arah tren utama menggunakan filter EMA dan histeresis 2-bar untuk mencegah *false flip*. | Output: `BULL`, `BEAR`, `NEUTRAL`. |
| 🔄 **`Phase FSM`** | Fase Gelombang Retracement (H1) | Klasifikasi posisi harga dalam gelombang tren: `EXPANSION`, `EARLY_CORRECTION`, `MATURE_CORRECTION`, `RECLAIM`. | Dihitung dari jarak harga ke EMA20 dan posisi Dealing Range ($DR$). |
| 🟢 **`EXPANSION_WAIT_BULL`** | Bullish Expansion (FSM: WAIT) | Harga bergerak ekspansif ke atas ($DR \ge 65\%$, jarak EMA20 $> 0.90\times\text{ATR}$). Dilarang FOMO buy di pucuk. | `Permission: WAIT ⏳` |
| 🔴 **`EXPANSION_WAIT_BEAR`** | Bearish Expansion (FSM: WAIT) | Harga bergerak ekspansif ke bawah ($DR \le 35\%$, jarak EMA20 $< -0.90\times\text{ATR}$). Dilarang FOMO sell di dasar. | `Permission: WAIT ⏳` |
| 🔪 **`WATERFALL_LOCK`** | Type A Waterfall (FSM: LOCK) | Koreksi agresif lilin merah beruntun tanpa sumbu bawah saat tren Bull. Blokade keras anti-pisau jatuh. | `Permission: LOCK 🔒` |
| 🚀 **`VERTICAL_SPIKE_LOCK`** | Type A Spike (FSM: LOCK) | Koreksi agresif lilin hijau vertikal tanpa sumbu atas saat tren Bear. Blokade keras anti-short squeeze. | `Permission: LOCK 🔒` |
| 🎯 **`DISCOUNT_RELOAD_ARMED`** | Type B Coil Bullish (FSM: ARM) | Kompresi sehat di area diskon ($DR \le 50\%$ / RBS) dengan CSM selaras. Siaga pasang buy limit retest. | `Permission: ARMED 🎯` |
| 🎯 **`PREMIUM_RELOAD_ARMED`** | Type B Coil Bearish (FSM: ARM) | Kompresi sehat di area premium ($DR \ge 50\%$ / SBR) dengan CSM selaras. Siaga pasang sell limit retest. | `Permission: ARMED 🎯` |
| 🟢 **`DEMAND_REACTION_GO`** | Demand Reclaim (FSM: GO) | Reclaim terkonfirmasi di lantai demand (sumbu bawah $\ge 20\%$ atau close menembus EMA20). Izin eksekusi BUY 100%. | `Permission: GO 🟢` |
| 🔴 **`SUPPLY_REACTION_GO`** | Supply Reclaim (FSM: GO) | Reclaim terkonfirmasi di atap supply (sumbu atas $\ge 20\%$ atau close menembus EMA20). Izin eksekusi SELL 100%. | `Permission: GO 🟢` |
| 👁️ **`WATCH`** | **CSM Flow Watch** (FSM) | Status siaga saat chart struktural sudah diskon/premium, namun aliran mata uang (*Boitoki CSM*) masih berlawanan arah. | `Permission: WATCH 👁️` |
| 💥 **`Displacement Candle`** | Lilin Impulsif Institusi | Lilin bervolume besar dengan rasio badan (*body ratio*) $\ge 50\% - 55\%$ yang menembus struktur. | Syarat mutlak transisi `ARM 🎯` &rarr; `GO 🟢`. |
| 📏 **`Dealing Range (DR)`** | Rentang Lelang Aktif (0% - 100%) | Pemetaan posisi harga relatif terhadap titik terendah (0% / Discount) dan tertinggi (100% / Premium). | Diskon: $DR \le 38.2\%$ (Golden Pocket). |

### 3. Smart Money Concepts (SMC) & Volume Profile (FRVP)
| Istilah Resmi | Komponen & Kepanjangan | Definisi & Makna Teknis | Peran dalam Penempatan Order |
|---|---|---|---|
| 🏛️ **`SMC`** | **Smart Money Concepts** | Metodologi analisis jejak likuiditas institusional (LuxAlgo Pine v5 Porting). | Fondasi penentuan zona lelang bernilai tinggi (*Value Area*). |
| 🧱 **`OB (Order Block)`** | Blok Pesanan Institusi | Lilin berlawanan terakhir sebelum pergerakan impulsif besar yang belum termitigasi (*Unmitigated OB*). | Titik jangkar penempatan SL fisik teraman. |
| 🕳️ **`FVG`** | **Fair Value Gap** / Imbalance | Celah ketidakseimbangan harga antara 3 lilin beruntun yang menjadi area magnet harga. | Digunakan sebagai target Take Profit alami (TP1 / TP2). |
| ⚡ **`BOS & CHoCH`** | Break of Structure / Change of Character | Penembusan level swing terluar searah tren (**BOS**) atau pembalikan struktur awal (**CHoCH**). | Konfirmasi pergeseran momentum institusi. |
| 🎯 **`EQH / EQL`** | Equal Highs / Equal Lows | Puncak atau lembah kembar tempat berkumpulnya kolam likuiditas stop-loss trader ritel. | Target empuk mekanisme sapuan likuiditas (*Judas Sweep*). |
| 📊 **`FRVP`** | **Fixed Range Volume Profile** | Profil distribusi volume transaksi pada rentang harga tertentu untuk menemukan konsentrasi transaksi institusi. | Sinergi dengan SMC untuk menyaring 59.2% sinyal palsu. |
| 🔴 **`POC`** | **Point of Control** (FRVP) | Level harga tunggal dengan volume transaksi terpadat pada rentang yang dianalisis. | Area magnet harga dan lantai pantulan terkuat. |
| 📐 **`VAH / VAL`** | Value Area High / Low (70% Volume) | Batas atas (VAH) dan bawah (VAL) yang mencakup 70% total volume lelang lelang institusi. | Area *Mean-Reversion* saat harga berada di luar rentang nilai wajar. |

### 4. Macro Strategic Engine (MSE) & Station DNA
| Istilah Resmi | Komponen & Kepanjangan | Definisi & Makna Teknis | Contoh Angka / Formulasi |
|---|---|---|---|
| 🧠 **`MSE`** | **Macro Strategic Engine** | Engine kuantitatif 6 timeframe native MT5 (`MN1`, `W1`, `D1`, `H4`, `H1`, `M30`) untuk mandat harian (0 token, $<50\text{ ms}$). | Menghitung Zonal Band, SBR/RBS, dan matriks aksi 5-Tier. |
| 📍 **`Reload Zone`** | Delivery Anchor / Institutional Anchor | Area lelang harga diskon/pullback di mana institusi mengisi ulang posisi (*reload*) sebelum ekspansi lanjutan. | `Reload Zone: 1.08400` atau `0.93550 ➔ 0.93480` |
| 🧱 **`SBR`** | **Support-Become-Resistance** | Bekas lantai support yang telah ditembus ke bawah dan kini beralih fungsi menjadi atap plafon lelang SELL. | `D1 SBR 1.35500` |
| 🏗️ **`RBS`** | **Resistance-Become-Support** | Bekas atap resistance yang telah ditembus ke atas dan kini beralih fungsi menjadi lantai lelang BUY. | `H4 RBS 1.34800` |
| 📉 **`DBD & RBR`** | Drop-Base-Drop & Rally-Base-Rally | Pola kelanjutan suplai/permintaan institusional di mana harga rehat sejenak sebelum melanjutkan tren. | Digunakan sebagai anchor entri pullback. |
| 🧭 **`Dynamic Stations`** | Halte Harga Bulat (Atlas DNA) | Garis halte harga psikologis alami berbasis DNA volatilitas historis 16.2 tahun MetaQuotes (step 100/50/25 pips). | `Floor [1.34500] <-> Ceil [1.35000]` |
| 🎛️ **`5-Tier Action Matrix`** | Matriks Aksi Operasional 5 Tingkat | Klasifikasi izin risiko dari MSE: `FULL_ALLOW`, `REDUCED_CONFIDENCE`, `TP1_ONLY_SCALP`, `WATCH_ONLY`, `HARD_BLOCK`. | `HARD_BLOCK` jika harga menabrak plafon atau invalidasi. |
| 🌐 **`Boitoki CSM`** | **Currency Strength Matrix** | Perhitungan kekuatan relatif 8 mata uang utama berbasis log return 7 USD Majors secara real-time. | `CSM: USD > JPY > EUR (Delta: +2.44)` |
| 🛑 **`Systemic Basket Lock`** | Pemutus Sirkuit Mata Uang Global | Proteksi sistemik jika salah satu mata uang mengalami lonjakan (*surge*) atau pembuangan (*dump*) $\ge \pm 20.0$. | Mencegah trade melawan arus likuiditas global. |

### 5. Trio Mekanisme Radar, Eksekusi & Manajemen Risiko
| Istilah Resmi | Komponen & Kepanjangan | Definisi & Makna Teknis | Parameter & Ambang Batas |
|---|---|---|---|
| 🗡️ **`M1 (Judas Sweep)`** | London Judas Swing Failure Pattern | Mekanisme perangkap likuiditas dengan memanfaatkan manipulasi false-breakout di Asian H/L atau PDH/PDL. | Sweep $\ge 0.15\times\text{ATR}$ + Reclaim $\le 3\text{ bar}$ + Wick $\ge 35\%$. |
| 🎣 **`M2 (Pullback Retest)`** | Trend-Aligned Pullback Limit | Mekanisme entri berdiskon searah tren makro dengan memasang *Delayed Limit Order* saat retest ke EMA20. | Limit Entry di $\text{Mid} \mp (0.20\times\text{ATR})$ di $DR \le 0.50$. |
| 🏰 **`M3 (Weekly Wall)`** | HTF Weekly Wall Reversal | Mekanisme pembalikan arah saat harga membentur dinding ekstrim mingguan/bulanan (PWH/PWL/MN1). | Target pengantaran stasiun ke 50% Equilibrium koridor. |
| 🛡️ **`Baseline Floor SL`** | Intraday SL (Anti-Hunt) | Level Stop Loss fisik berbasis struktur support/resistance terdekat + buffer anti-wick + safety floor ATR. | `SL = Anchor \mp (0.35\times\text{ATR} + \text{Spread})` |
| 🎁 **`TP1 (Partial Close)`** | Take Profit 1 (50% Cair) | Target profit stasiun pertama di mana bot mencairkan 50% lot dan menggeser sisa posisi ke Risk-Free BEP. | Aktif di 45%–55% target TP penuh. |
| 🏆 **`TP2 (Extended Runner)`** | Take Profit 2 (Macro Target) | Target profit koridor makro lanjutan yang dikawal dengan 2-Stage Dynamic Trailing Stop. | `TP2 = Target Stasiun / 50% Equilibrium` |
| 🔒 **`BEP + Pocket Profit`** | Break-Even Point + Pocket Profit | Penggeseran SL ke titik impas + padding komisi round-trip broker + **Pocket Profit 15 pts (1.5 pips)**. | Mengunci keuntungan minimum saat BEP tercapai. |
| 📈 **`2-Stage Trailing Stop`** | Trailing Stop Dinamis 2 Tahap | Pengawalan profit: **Stage 1 (Breathing)** di 65%–90% TP ($0.75\times\text{ATR H1}$, floor 80 pts); **Stage 2 (Terminal Lock)** di $\ge 90\%$ TP ($0.50\times\text{ATR M30}$, floor 30 pts). | Mengunci runner tanpa terkena wick noise. |
| ⏱️ **`Time-Decay Stagnation`** | Peak-Aware Stagnation Exit | Penutupan paksa posisi yang stagnan $\ge 4\text{ jam}$ di rentang $[-0.20R, +0.20R]$ jika *Peak MFE* $< +0.30R$. | Mencegah modal terikat pada pasar mati. |
| 🛡️ **`Pre-Rollover Shield`** | Perisai Rollover MT5 (03:50 WIB) | Penutupan posisi secara selektif tepat jam 03:50 WIB (10 menit sebelum rollover 04:00 WIB) jika jarak ke SL $\le$ ambang bahaya. | Melindungi akun dari lonjakan spread rollover. |
| ⛔ **`Dead Zone`** | Jendela Waktu Dilarang Trade | Periode pukul **00:00 – 08:00 WIB** di mana seluruh eksekusi baru dibekukan mutlak. | Likuiditas tipis dan spread lebar. |
| 🌪️ **`The Storm`** | Jendela Badai Berita High-Impact | Jendela waktu $[-15\text{ menit}, +30\text{ menit}]$ di sekitar rilis berita ekonomi bintang 3 (ForexFactory / TradingView). | Pembekuan eksekusi untuk menghindari slippage ekstrim. |
| 📊 **`MFE & MAE`** | Max Favorable / Adverse Excursion | Metrik kuantitatif pengukur jarak profit terjauh (**MFE**) dan floating minus terdalam (**MAE**) selama posisi berjalan. | Digunakan untuk evaluasi efisiensi trailing stop. |

---

## Daftar Isi
1. [Bab 1: Executive Architecture & High-Level Design](#bab-1-executive-architecture--high-level-design)
2. [Bab 2: Fractal Multi-Timeframe Hierarchy & Symbol Universe](#bab-2-fractal-multi-timeframe-hierarchy--symbol-universe)
3. [Bab 3: Stage 1 Radar — Trio Mekanisme Presisi (M1, M2, M3)](#bab-3-stage-1-radar--trio-mekanisme-presisi-m1-m2-m3)
4. [Bab 4: 4-Dimensional Market State Engine (wave_state.py)](#bab-4-4-dimensional-market-state-engine-wave_statepy)
5. [Bab 5: Universal 8-Currency Basket Circuit Breaker (currency_strength.py)](#bab-5-universal-8-currency-basket-circuit-breaker-currency_strengthpy)
6. [Bab 6: Macro Strategic Engine (MSE) & Zonal SBR/RBS](#bab-6-macro-strategic-engine-mse--zonal-sbrrbs)
7. [Bab 7: LuxAlgo SMC, Liquidity Map & FRVP Confluence](#bab-7-luxalgo-smc-liquidity-map--frvp-confluence)
8. [Bab 8: Stage 2 Multi-LLM Consensus Jury & Strict 3/3 Protocol](#bab-8-stage-2-multi-llm-consensus-jury--strict-33-protocol)
9. [Bab 9: Single Policy Path SL/TP Floor & Ceiling Guardrails](#bab-9-single-policy-path-sltp-floor--ceiling-guardrails)
10. [Bab 10: Risk Engine & Account Capital Preservation (risk_engine.py)](#bab-10-risk-engine--account-capital-preservation-risk_enginepy)
11. [Bab 11: Real-Time Position Management Lifecycle (position_manager.py)](#bab-11-real-time-position-management-lifecycle-position_managerpy)
12. [Bab 12: Dedicated On-Demand OpenAI o4-mini & Telegram Controller](#bab-12-dedicated-on-demand-openai-o4-mini--telegram-controller)
13. [Bab 13: Apex Paragon Macro Fundamental Engine & Dual-Source News Layer](#bab-13-apex-paragon-macro-fundamental-engine--dual-source-news-layer)

---

## Bab 1: Executive Architecture & High-Level Design

Bot trading beroperasi dengan arsitektur **2-Stage Quant Funnel** yang memisahkan komputasi matematis berat di Python dari audit kognitif AI:

```
+-----------------------------------------------------------------------------------+
|               STAGE 1: FAST QUANTITATIVE RADAR (Lokal di MT5 • 60 Detik • 0 Token)|
|  Universe: 26 Simbol Paralel | Sockets: MN1, W1, D1, H4, H1, M30                  |
|  [M1: Judas Sweep SFP]  [M2: Pullback Retest]    [M3: Multi-Touch Breakout Retest]|
|  [BUY: Diskon + RBS]    [SELL: Premium + SBR]    [CSM 8-Basket Dual-Horizon Flow] |
|  [Wave State FSM: ARM / GO / WAIT / LOCK]       [MSE 5-Tier Action Matrix]        |
+-----------------------------------------+-----------------------------------------+
                                          | (Hanya 8-15 Setup A+ / hari lolos)
                                          v
+-----------------------------------------------------------------------------------+
|               STAGE 2: 3-LLM CONSENSUS JURY (Kognitif Paralel & Audit • ~5.5s)    |
|  PASS 1 (~3.0s): OpenAI o4-mini (Struktur Makro) + Gemini 3.1-Flash (Momentum/Wick)|
|  PASS 2 (~1.5s): DeepSeek V4-Flash CRO (Devil's Advocate Audit + 24 Candle M5)    |
|  VETO GATES: 11 Bendera Risiko (Anti-Falling Knife BUY / Anti-Rocket FOMO SELL)   |
|  KONSENSUS : STRICT UNANIMOUS 3/3 (Wajib 3/3 Searah; Split = HOLD)                |
|  SPLIT BOOST: Unanimous 3/3 + Confidence >= 75% -> 2 Tiket Posisi (+25% Boost)    |
+-----------------------------------------+-----------------------------------------+
                                          | (Order Disetujui)
                                          v
+-----------------------------------------------------------------------------------+
|               STAGE 3: RISK ENGINE & REAL-TIME POSITION MANAGER (Loop 3 Detik)    |
|  Sizing: Risk 1.0% Equity | Floor SL: 0.68x ATR H1 (FX) / 1.0x ATR M30 (JPY)      |
|  BUY: Trailing naik kunci Floor | SELL: Trailing turun kunci Ceiling              |
|  Dynamic BEP (+15 pts Pocket) | Partial Close 50% TP1 | Pre-Rollover Shield       |
+-----------------------------------------------------------------------------------+
```

---

## Bab 2: Fractal Multi-Timeframe Hierarchy & Symbol Universe

1. **Universe Aktif (26 Simbol)**:
   - **FX Majors & Crosses (H1)**: `EURUSD`, `GBPUSD`, `USDCHF`, `USDCAD`, `EURGBP`, `EURCHF`, `GBPCHF`, `CADCHF`, `AUDUSD`, `NZDUSD`, `AUDNZD`, `EURAUD`, `GBPCAD`, `GBPAUD`, `EURCAD`.
   - **JPY Crosses (M30)**: `USDJPY`, `EURJPY`, `GBPJPY`, `CADJPY`, `AUDJPY`, `NZDJPY`, `CHFJPY`.
   - **NZD Alpha Crosses (H1 + 20 pts buffer)**: `GBPNZD`, `EURNZD`, `NZDCAD`, `AUDCAD`, `NZDCHF`.
   - **Crypto (Weekend 24/7)**: `BTCUSD` (aktif di akhir pekan saat pasar FX tutup).
   - **Gold (`XAUUSD-ECNc`)**: **DIMATIKAN TOTAL PERMANEN** sejak 30 Agustus 2026.

2. **Hirarki 6-Timeframe Native (MSE Sockets)**:
   - `MN1` (50 bar / 4.1 tahun): Level struktural ultra-makro.
   - `W1` (100 bar / 2.0 tahun): Dealing Range 100-bar & Wall batas mingguan.
   - `D1` (350 bar / 1.4 tahun): Mandat arah tren utama (*Daily Macro Bias*).
   - `H4` (400 bar / 2.2 bulan): SBR/RBS intermediate level & EMA50 slope.
   - `H1` (250 bar / 10.4 hari): Timeframe eksekusi struktural & Reload Zone.
   - `M30` (200 bar / 4.1 hari): Timeframe eksekusi JPY Crosses & terminal lock trailing stop.

---

## Bab 3: Stage 1 Radar — Trio Mekanisme Presisi (M1, M2, M3)

### 3.1 Mekanisme 1: Universal Liquidity Sweep & SFP (M1)
* **Konsep**: Menjebak *trapped traders* yang mengejar breakout palsu di level likuiditas makro (Asian High/Low, Previous Day High/Low, PWH/PWL, EQH/EQL).
* **Syarat**:
  - Penembusan $\ge 0.15\times\text{ATR}(14)$ di luar level ekstrim.
  - Reclaim kembali ke dalam rentang dalam $\le 3\text{ candle}$.
  - Sumbu penolakan (*rejection wick*) $\ge 35\%$ dari total range lilin.
  - Anti-Waterfall: Dilarang BUY jika marubozu merah solid tanpa sumbu bawah.

### 3.2 Mekanisme 2: Trend-Aligned Pullback & Delayed Limit Retest (M2)
* **Konsep**: Entri berdiskon searah ekspansi makro D1/H4 di dalam Reload Zone dengan retest dinamis ke EMA20.
* **Syarat**:
  - Arah tren selaras: Macro Bias Aligned + EMA50 slope searah.
  - Berada di Zona Diskon ($\le 0.50$ Dealing Range, optimal $\le 0.382$).
  - Entri limit tertunda: dipasang pada level $\text{Mid} \mp (0.20\times\text{ATR})$.
  - SL fisik di belakang lantai RBS / atap SBR $+ 0.35\times\text{ATR} + \text{Spread}$.

### 3.3 Mekanisme 3: Multi-Touch Cluster Breakout & Delayed Retest (M3)
* **Konsep**: Entri *Breakout Continuation* setelah level cluster support/resistance disentuh $\ge 2\times$ dan ditembus dengan lilin momentum ($\ge 55\%$ body ratio), lalu memasang *Delayed Limit Order* saat harga melakukan retest (delay 3–4 bar). *(Catatan: Weekly Wall + Psych Price adalah confluence batas makro, bukan nama mekanisme M3)*.
* **Syarat**:
  - Level cluster disentuh $\ge 2\times$ (`touches_res` $\ge 2$ atau `touches_sup` $\ge 2$).
  - Penembusan bervolume/momentum di atas cluster resistance atau di bawah cluster support.
  - Limit retest dipasang di level cluster yang tertembus ($c_{res} / c_{sup}$).
  - SL fisik dipasang di balik origin cluster $+ 0.35\times\text{ATR} + \text{Spread}$.
  - Target TP1 di halte stasiun berikutnya (R:R $\ge 1.50$) dan TP2 di koridor makro lanjutan.

---

## Bab 4: 4-Dimensional Market State Engine (`wave_state.py`)

Memecah pasar menjadi 4 dimensi independen untuk menghilangkan kesalahan *Gambler's Fallacy*:

1. **Dimensi 1: Directional Identity FSM (D1 + H4)**:
   - Mengukur momentum arah makro (`BULLISH_EXPANSION`, `BULLISH_PULLBACK`, `BEARISH_EXPANSION`, `BEARISH_PULLBACK`, `NEUTRAL_RANGE`).
2. **Dimensi 2: Structural Anatomy & Wave Form (H1)**:
   - `TYPE_A_WATERFALL_LOCK`: Lilin beruntun searah tanpa wick $\rightarrow$ Hard Lock (Anti-Falling Knife).
   - `TYPE_B_COMPRESSION_ARMED`: Kompresi menyempit di atas support $\rightarrow$ Siaga Limit Entri.
   - `BASE_RECLAIM_GO`: Reclaim terverifikasi $\rightarrow$ Izin eksekusi pasar aktif.
3. **Dimensi 3: CSM Pressure Index**:
   - Menghitung delta aliran mata uang per detik.
4. **Dimensi 4: Permission Matrix**:
   - `GO`: Izin eksekusi penuh (Reclaim valid di Reload Zone).
   - `ARM`: Izin pasang pending limit order di Reload Zone Anchor.
   - `WAIT`: Menunggu harga memasuki zona diskon (Anti-FOMO di pucuk).
   - `LOCK`: Dilarang trading (Pisau jatuh / Volatilitas liar).

---

## Bab 5: Universal 8-Currency Basket Circuit Breaker (`currency_strength.py`)

Porting 1:1 algoritma Boitoki CSM untuk 8 mata uang utama (USD, EUR, GBP, JPY, CHF, AUD, CAD, NZD):
* **Dual-Horizon Basket Weighting**: Bobot H1 $40\%$ + M15 $60\%$.
* **Relative Delta Spread ($|\Delta|$)**: Jika selisih kekuatan mata uang $|\Delta| \ge 18.0$, arah tren terkunci rapat.
* **Basket Circuit Breaker**: Jika mata uang mengalami *Systemic Dump* ($\le -20.0$), dilarang keras melakukan BUY (Hard Block 0 Token).

---

## Bab 6: Barrier Chamber State Machine & Macro Strategic Engine (MSE)

MSE 6-TF Native mengintegrasikan **Barrier Chamber State Machine** 3-layer modular untuk memetakan ruang lelang institusional secara deterministik:

### 1. Structural Model: Density-Ranked Barrier Resolver
Memetakan dinding lelang aktif tanpa jebakan boolean AND yang kaku menggunakan pembobotan bukti (*Evidence Weights*):
* $\text{Score} = \text{Structural RBS/SBR (3.5)} + \text{SMC Order Block (2.5)} + \text{Psychological Stations (2.0)} + \text{FVG (2.0)}$
* **Batas Atas**: $C_1$ (*Immediate Ceiling*) dan $C_2$ (*Macro Extension Target*).
* **Batas Bawah**: $F_1$ (*Immediate Floor*) dan $F_2$ (*Deep Structural Support Target*).
* **Chamber Position**: Mengukur posisi harga di dalam ruang lelang ($0\% - 100\%$).

### 2. Path-Dependent Interaction Sequence Tracker
Menganalisis riwayat 8 lilin H1 terhadap barrier $C_1$ dan $F_1$ untuk merekam kompresi sejati:
* Contoh: `interaction_sequence = ['F1_TOUCH', 'F1_SWEEP', 'C1_TOUCH', 'C1_SWEEP']`

### 3. Lean 7-State Machine Engine
1. **`NEUTRAL_CHAMBER`**: Harga mengambang di koridor tengah ($20\% - 80\%$) $\rightarrow$ `RANGE_BOUND (WATCH_ONLY)` anti-overtrading.
2. **`CHAMBER_CEILING_TEST`**: Menguji $C_1$ tanpa konfirmasi penolakan.
3. **`CHAMBER_FLOOR_TEST`**: Menguji $F_1$ tanpa konfirmasi penolakan.
4. **`CEILING_REJECTION`**: Terkonfirmasi ekor penolakan atas $\ge 25\%$ di $C_1$ $\rightarrow$ `BEARISH_PULLBACK (HUNT_SELL_PULLBACK)`.
5. **`FLOOR_REJECTION`**: Terkonfirmasi ekor penolakan bawah $\ge 25\%$ di $F_1$ $\rightarrow$ `BULLISH_PULLBACK (HUNT_BUY_AT_RBS)`.
6. **`CEILING_BREAKOUT`**: Penutupan body lilin solid menembus $C_1$ $\rightarrow$ `BULLISH_EXPANSION`.
7. **`FLOOR_BREAKDOWN`**: Penutupan body lilin solid menembus $F_1$ $\rightarrow$ `BEARISH_EXPANSION`.

### 4. Pair-Calibrated Minimum SL Floor
Mencegah Stop Loss ketipisan pada pair ber-volatilitas tinggi:
* **Volatile Cross Pairs (GBPNZD, GBPJPY, EURNZD, GBPAUD, CADJPY)**: $\text{SL} \ge \max(1.20\times\text{ATR H1}, 0.25\times\text{ATR D1}, 35\text{ pips})$.
* **Standard Majors (EURUSD, USDCAD, EURGBP)**: $\text{SL} \ge \max(1.00\times\text{ATR H1}, 18\text{ pips})$.
* **Gold (XAUUSD)**: $\text{SL} \ge \max(1.20\times\text{ATR H1}, \$3.50)$.

---

## Bab 7: LuxAlgo SMC, Liquidity Map & FRVP Confluence

* **LuxAlgo SMC (`lux_smc.py`)**: Porting PineScript v5 asli untuk mendeteksi *Unmitigated Order Blocks (OB)*, *Fair Value Gaps (FVG)*, *Strong Lows/Highs*, dan *Equal Highs/Lows (EQH/EQL)*.
* **Fixed Range Volume Profile (`volume_profile.py`)**: Menghitung area lelang *Point of Control (POC)*, *Value Area High (VAH)*, dan *Value Area Low (VAL)* untuk memastikan entri berada di area *Volume Acceptance*.

---

## Bab 8: Stage 2 Multi-LLM Consensus Jury & Strict 3/3 Protocol

1. **2-Pass Sequential Cross-Examination (<5.5s)**:
   - **Pass 1 (~3.0s)**: OpenAI `o4-mini` (Struktur Makro) + Gemini `3.1-flash-lite` (Momentum & Candlestick) menganalisis berkas secara independen.
   - **Pass 2 (~1.5s)**: DeepSeek `V4-Flash CRO` (Chief Risk Officer) mengaudit proposal Pass 1 berbekal 24 candle M5 mikro live.
2. **Strict Unanimous 3/3 Rule (Zero Tolerance Split)**:
   - Wajib 100% kesepakatan bulat 3 model (3/3 BUY atau 3/3 SELL).
   - Jika 1 model saja memilih HOLD atau berlawanan arah $\rightarrow$ **OTOMATIS HOLD**.
3. **High-Confidence Split (+25% Boost)**:
   - Jika 3 model sepakat bulat dengan rata-rata Confidence $\ge 75\%$, bot membuka 2 tiket posisi sekaligus @ $0.625\times\text{Base Lot}$ (Total $1.25\times$).
4. **7 Master Institutional Hard Risk Veto Flags**:
   - `COUNTER_TREND_MOMENTUM`: Melawan tren H4/D1 atau air terjun *falling knife*.
   - `LIQUIDITY_TRAP`: Jebakan sapuan likuiditas di pucuk EQH/EQL atau beli di SBR.
   - `IMPULSE_CHASE`: FOMO mengejar candle panjang tanpa retest ke zona diskon.
   - `SYSTEMIC_CURRENCY_DUMP`: Keranjang mata uang sedang dibuang di 7 pair CSM.
   - `HIGH_IMPACT_NEWS`: Berada tepat di tengah badai rilis berita Tier-1 (*The Storm* $\pm 15-30$ menit).
   - `CURRENCY_CONFLICT`: Perang tarik tambang kedua mata uang (*Tug-of-War / Choppy Sideways*).
   - `MACRO_HEADWIND`: Melawan arah divergensi suku bunga Bank Sentral / *Carry Spread* ekstrem.

---

## Bab 9: Single Policy Path SL/TP Floor & Ceiling Guardrails

Seluruh lapisan stack (`MSE`, `Radar`, `consensus.py`) menerapkan aturan Floor & Ceiling yang identik:

| Instrumen | Floor SL Minimum | Plafon SL Maksimum (Ceiling) | Aturan R:R Target |
|---|---|---|---|
| ₿ **Bitcoin (BTC)** | $\max(2\times\text{spread}, 1.20\times\text{ATR}, 30\,000\text{ pts})$ ($\$300$) | $\min(1.80\times\text{ATR}, 45\,000\text{ pts})$ ($\$450$) | Min $1.25\times$ s/d Max $3.0\times\text{SL}$ |
| 💴 **JPY Crosses (M30)** | $\max(2\times\text{spread}+20, 1.00\times\text{ATR})$ | $\min(2.0\times\text{ATR}, 200\text{ pts})$ ($20\text{ pips}$) | Min $1.25\times$ s/d Max $3.0\times\text{SL}$ |
| 💶 **FX Majors/Crosses (H1)** | $\max(2\times\text{spread}+15, 0.68\times\text{ATR})$ | $\min(2.0\times\text{ATR}, 160\text{ pts})$ ($16\text{ pips}$) | Min $1.25\times$ s/d Max $3.0\times\text{SL}$ |
| 🦘 **NZD Alpha Pairs** | Tambahan buffer anti-wick $+20\text{ pts}$ | $\le 160\text{ pts}$ ($16\text{ pips}$) | Min $1.25\times$ s/d Max $3.0\times\text{SL}$ |

---

## Bab 10: Risk Engine & Account Capital Preservation (`risk_engine.py`)

1. **Formula Ukuran Lot Berbasis Risiko (*Risk-Based Lot Sizing*)**:
   $$\text{Lot Size} = \frac{\text{Equity} \times \text{Risk}\%}{\text{SL Points} \times \text{USD Value per Point}} \times \text{Vol Mult} \times \text{Session Mult}$$
   - Risiko per trade: FX $1.0\%$, BTC $0.50\%$.
2. **Hard Account Circuit Breakers**:
   - **Max Daily Loss**: $4.0\%$ Equity ($\approx \$233$ pada modal $\$5,819$).
   - **Daily Profit Target**: $6.0\%$ Equity $\rightarrow$ kunci profit & istirahat.
   - **Consecutive Loss Streak**: $\ge 5$ loss beruntun memicu *Recovery Mode* (lot $\times 0.5$, max 3 posisi).
   - **Dead Zone**: 00:00 – 08:00 WIB (FX istirahat; BTC 24/7 di akhir pekan).

---

## Bab 11: Real-Time Position Management Lifecycle (`position_manager.py`)

Berjalan pada *fast-loop* 3 detik di `main.py`:
1. **Dynamic Break-Even (BEP)**:
   - Aktif saat harga mencapai **$45\% – 55\%$ TP**.
   - SL digeser ke harga entri $+$ komisi round-trip $+$ Pocket Profit 15 pts (1.5 pips).
2. **Partial Take-Profit (TP1)**:
   - Cairkan $50\%$ lot saat mencapai $45\% – 55\%$ TP dan geser sisa posisi ke Risk-Free BEP.
3. **2-Stage Dynamic Trailing Stop**:
   - **Stage 1 (Swing Breathing: $65\% \le \text{Progress} < 90\%\text{ TP}$)**: Trailing $0.75\times\text{ATR H1}$ (floor 80 pts FX).
   - **Stage 2 (Terminal Lock: $\text{Progress} \ge 90\%\text{ TP}$)**: Trailing ketat $0.50\times\text{ATR M30}$ (floor 30 pts FX).
4. **Peak-Aware Time-Decay Stagnation Exit**:
   - Jika posisi hold $\ge 4\text{ jam}$ di rentang $[-0.20R, +0.20R]$ dan Peak MFE $< +0.30R$, posisi ditutup bersih.
5. **Pre-Rollover Shield (03:50 – 04:15 WIB)**:
   - Tutup bersih posisi di 03:50 WIB jika jarak fisik ke SL $\le$ threshold spread rollover.

---

## Bab 12: Dedicated On-Demand OpenAI o4-mini & Telegram Controller

1. **Dedicated On-Demand Analysis Engine (`/analisa <symbol>`)**:
   - Menggunakan model tunggal **OpenAI `o4-mini`** yang dilengkapi berkas konteks kuantitatif **MSE 6-TF Native**.
   - Menghasilkan respon analisa instan (<1.5 detik) dan menghemat $66\%$ token API.
2. **Interactive 2-Way Controller**:
   - **Menu Interaktif (`/menu`)**: Akses satu ketukan ke *MSE Macro Strategy*, *SMC Radar 26 Pairs*, *CSM Flow*, *News Calendar*, *Apex Fundamental*, dan *Account Status*.
   - **Macro Symbol Picker (`/macro`)**: Grid 9 tombol instrumen pilihan untuk membaca arahan makro instan (<100ms, 0 Token).
   - **Smart High-Impact Alert Gate**: Notifikasi radar otomatis hanya dikirim saat terjadi transisi kritis **`Permission GO`** (`alert_radar_go_transition`).

---

## Bab 13: Apex Paragon Macro Fundamental Engine & Dual-Source News Layer

1. **Dual-Source Ingestion & Bank Holiday Guard**:
   - **Primary**: ForexFactory Official JSON CDN (`nfs.faireconomy.media/ff_calendar_thisweek.json`, latensi <0.2s).
   - **Fallback**: TradingView API (`economic-calendar.tradingview.com/events`) & Central Bank Overrides.
   - **Bank Holiday Detection**: Mendeteksi libur pasar (*UK Summer Bank Holiday*) $\rightarrow$ menurunkan grade ke **GRADE B**, memangkas lot ke $0.50\times$, dan melarang *breakout chase*.
2. **4-Stage Lifecycle of News Catalysts**:
   - **The Storm (0–30m)**: Veto / Freeze (mencegah slippage).
   - **The Calm (30m–6h)**: Favor Entry (menunggangi *orderly drift* institusi).
   - **The Regime Extension (1–3 Hari)**: Trend-Aligned Pullback (M2/M3).
   - **Priced-In Equilibrium (4+ Hari)**: Pure Technical Mode (murni MSE Sockets & SMC).
3. **Tiered Half-Life Exponential Decay**:
   $$\text{Score}(t) = \text{Score}_0 \cdot e^{-\lambda \cdot \Delta t}$$
   - Tier 1 (FOMC/NFP/CPI): Half-Life $36\text{ Jam}$.
   - Tier 2 (PMI/GDP/Retail): Half-Life $12\text{ Jam}$.
   - Tier 3 (Headlines/Speeches): Half-Life $4\text{ Jam}$.
4. **4-Tier Setup Quality & Dynamic ATR Multipliers**:
   - 👑 **GRADE S**: Konvergensi Penuh (MSE + SMC + CSM + Fundamental 100% Selaras) $\rightarrow$ *Full Size + Multiplier TP $3.0\times\text{ATR}$ (Multi-Day Swing Hold)*.
   - 🟢 **GRADE A+**: Setup Teknikal + Angin Fundamental Mendukung $\rightarrow$ *Full Size + Multiplier TP $2.0\times\text{ATR}$*.
   - 🟡 **GRADE A**: Pasar Tenang / *Priced-In Flat* $\rightarrow$ *Standard Size + Multiplier TP $1.5\times\text{ATR}$ (Murni MSE & SMC)*.
   - ⚪ **GRADE B**: Ada friksi makro (*Currency Conflict / Macro Headwind / Bank Holiday*) $\rightarrow$ *Reduced Sizing ($0.50\times$) + Multiplier TP $1.25\times\text{ATR}$ (Scalp TP1 Only)*.
5. **Telegram Command**: `/fundamental` (Scoreboard 8 Mata Uang) & `/fund <pair>` (Evaluasi mendalam per-pair).

---

## Bab 14: Hybrid Confluence, Symmetrical Wave State & Risk-Weighted Slot Allocation

1. **Symmetrical Dual-Directional Wave State Engine**:
   - 🟢 **Siklus BUY (Lantai Diskon)**: `EXPANSION_WAIT_BULL` $\rightarrow$ `WATERFALL_LOCK` $\rightarrow$ `DISCOUNT_RELOAD_ARMED` $\rightarrow$ **`DEMAND_REACTION_GO 🟢`**.
   - 🔴 **Siklus SELL (Atap Premium SBR)**: `EXPANSION_WAIT_BEAR` $\rightarrow$ `VERTICAL_SPIKE_LOCK` $\rightarrow$ `PREMIUM_RELOAD_ARMED` $\rightarrow$ **`SUPPLY_REACTION_GO 🟢`**.
2. **Kuantifikasi Konflik (Severe vs Mild Conflict)**:
   - 🔴 **Severe Conflict ($|S_{\text{base}}| \ge 0.50$ & $|S_{\text{quote}}| \ge 0.50$ / Super Hawkish Clash)**: **`REJECT_VETO` (Hard Veto)**.
   - 🟡 **Mild Conflict ($|S| < 0.50$ / Friksi Minor)**: **`GRADE_B` ($0.50\times$ Sizing / TP1 Scalp)**.
3. **Hybrid Confluence Targeting (MSE Station + Dynamic ATR Envelope)**:
   - Target TP selalu **menempel (*snapped*) ke level stasiun fisik MSE terdekat** di dalam amplop ATR Grade.
   - **Front-Running Pad**: $\text{TP}_{\text{final}} = \text{Station} \mp (0.15\times\text{ATR} + \text{Spread})$ untuk mencegah harga berbalik arah 3 pips sebelum garis stasiun.
4. **Milestone-Driven Data-Backed BEP & Trailing**:
   - **Grade S**: BEP ditunda di $65\%-70\%$ TP + Trailing lebar $1.25\times\text{ATR H1}$ (floor 120 pts FX) + Imun dari Time-Decay Stagnation 4 jam.
   - **Grade A+/A**: BEP standar di $45\%-55\%$ TP + Trailing $0.75\times\text{ATR H1}$ (floor 80 pts).
   - **Grade B**: BEP cepat di $35\%-40\%$ TP + Trailing ketat $0.40\times\text{ATR M30}$ (floor 30 pts) + Strict 4h Exit.
5. **Risk-Weighted Slot Allocation dengan 5 Lapisan Kontrol Portofolio (Opsi 2)**:
   - **Lapisan 1 (Kuota At-Risk)**: Maksimal **6 posisi berisiko** ($SL < Entry$). Posisi yang sudah mengunci TP1 dan berada di Risk-Free BEP (Downside Risk $\$0.00$) tidak lagi memakan kuota risk.
   - **Lapisan 2 (Plafon Absolut MT5)**: Maksimal **8 total tiket terbuka** di akun (termasuk yang sudah BEP) guna mencegah penumpukan margin broker.
   - **Lapisan 3 (Free Margin Buffer)**: Wajib Free Margin Ratio $\ge 60\%$.
   - **Lapisan 4 (Konsentrasi Keranjang Valas)**: Maksimal **3 posisi terbuka per mata uang** (USD, EUR, JPY, dll) untuk mencegah risiko korelasi terselubung.
   - **Lapisan 5 (Konsentrasi Simbol)**: Strict 1-Trade Limit per Symbol.

---
*Dokumen ini adalah Single Source of Truth teknikal resmi untuk arsitektur bot trading produksi branch `quant-trade`.*

