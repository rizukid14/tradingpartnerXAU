# Comprehensive Technical Architecture — Multi-LLM Quant Trading Engine

> **Dokumentasi Teknis Lengkap Sistem Trading Bot Kuantitatif Institusional**  
> Terakhir Diperbarui: **12 September 2026** | Branch: `quant-trade-pattern` / `quant-trade`

---

## 1. Ikhtisar Sistem & Filosofi Desain

Sistem ini adalah bot trading algoritmik berbasis **2-Stage Quant Funnel** yang beroperasi di **MetaTrader 5 (MT5)** dengan akun riil Cent (`VTMarkets-Live 3`, login `27556325`, magic number `20260625`).

### Prinsip Inti:
1. **Asimetri Biaya Komputasi (Zero Token by Default)**:
   - Seluruh pemindaian 26 pair FX dilakukan di Stage 1 menggunakan algoritma kuantitatif murni NumPy/Pandas sub-milidetik (0 token API).
   - Stage 2 (3-LLM Consensus Jury: OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4-Flash) hanya dipanggil jika ada sinyal Grade A / A+ yang lolos dari seluruh filter fisik.
2. **Kedaulatan Struktur Pasar (First Principles SMC)**:
   - Aksi harga struktural (Origin Impulse Anchor, Order Blocks, Liquidity Sweeps, Zone Confluence) berdiri di atas indikator turunan.
   - Tidak ada trade limit yang boleh dipasang di koridor transit (mid-chamber). Entry wajib di area ekstrim (Diskon untuk BUY, Premium untuk SELL).
3. **Proteksi Modal Institusional Tanpa Kompromi**:
   - Friction-aware risk floor (SL tidak boleh tergerus oleh spread/komisi > 20%).
   - Cap lot maksimal 0.50 lot untuk akun Cent demi mencegah lonjakan risiko saat SL ketat.
   - Circuit breaker harian (4% equity max loss, 7% profit lockout).

---

## 2. Universe Aset & Pembagian Sesi

| Simbol | Tipe | Timeframe | Status Eksekusi | Keterangan |
|---|---|---|---|---|
| **26 FX Pairs** | Forex Major & Cross | **H1 Unified** | **LIVE MT5 Cent** | Dipindai paralel tiap 60 detik oleh Stage 1 Radar. |
| **XAUUSD-ECNc** | Gold | M30 / H1 | **Virtual Paper Only** (`ENABLE_XAU_PAPER=True`) | Dipindai radar & cockpit X-Ray, dikarantina dari akun cent. |
| **BTCUSD.c** | Crypto | M30 / H1 | **Virtual Paper Weekend** (`ENABLE_BTC_247_PAPER=True`) | 24/7 aktif akhir pekan, 0 risiko modal live. |

### Jam Sesi Operasional (Waktu WIB / GMT+7):
- **Server MT5**: Beroperasi di GMT+3. **Waktu WIB = Jam Server MT5 + 4 Jam**.
- **Pergantian Hari / Rollover (00:00 Server)**: **Tepat 04:00 WIB**.
- **Jendela Bahaya Rollover (03:50 – 04:15 WIB)**: Pre-Rollover Shield aktif menutup posisi yang berjarak dekat ke SL.
- **Dead Zone (00:00 – 07:00 WIB)**: Tidak ada order baru dibuka untuk instrumen FX & Gold.
- **Tokyo Session (07:00 – 14:00 WIB)**: Khusus pair aktif Asia (JPY, AUD, NZD). Multiplier lot 1.20x.
- **London Core (14:00 – 18:00 WIB)**: Seluruh 26 FX diizinkan. Multiplier lot 1.00x.
  - *London Defensive Window (15:00 – 17:59 WIB)*: Sell limit pasif dilarang.
- **New York Session (18:00 – 00:00 WIB)**: Multiplier lot 0.50x flat. M3 Breakout Retest dialihkan ke virtual paper.

---

## 3. Stage 1 Fast Execution Radar (4 Mekanisme)

Pemindaian dilakukan paralel setiap 60 detik (`market_scanner.py`):

1. **M1: Universal Liquidity Sweep & SFP (Swing Failure Pattern)**:
   - Deteksi sapuan likuiditas di atas Range High (BSL) atau di bawah Range Low (SSL) dengan pembalikan cepat (reclaim) ke dalam range.
   - Wajib memenuhi syarat: BUY hanya di area Deep Diskon ($dr_pos \le 0.382$), SELL hanya di area Deep Premium ($dr_pos \ge 0.618$).
2. **M2: Trend-Aligned Pullback & Delayed Limit Retest**:
   - Pullback searah tren makro menuju batas Action Zone ($F_1$ Floor untuk BUY / $C_1$ Ceiling untuk SELL) dengan toleransi $\le 0.20\times\text{ATR}$.
   - Veto tabrakan: Dilarang BUY jika $dr_pos \ge 0.80$, dilarang SELL jika $dr_pos \le 0.20$.
3. **M3: Multi-Touch Breakout Retest & Wall Reversal**:
   - Retest level struktural setelah valid break dengan konfirmasi rejection wick M5 $\ge 25\%$.
   - Dilengkapi *Pre-Breakout Context Validator* (verifikasi batas riil $\ge 3-5$ bar sebelum break).
4. **M4: DBD / RBR Breakout Continuation (Pure Technical Basing)**:
   - Pola Drop-Base-Drop atau Rally-Base-Rally lokal (impulse candle $\ge 50\%$ body ratio disusul kompresi basing $2-6$ bar $\le 0.35\times\text{ATR}$).

### Confluence Fusion:
Jika sebuah simbol memicu lebih dari 1 mekanisme searah dalam jarak $\le 0.35\times\text{ATR}$, sinyal dilebur menjadi tiket tunggal berkekuatan ganda (misal `M1+M3_CONFLUENCE`), dan grade setup dinaikkan otomatis (`GRADE_A` $\rightarrow$ `GRADE_A+` $\rightarrow$ `GRADE_S`).

---

## 4. Smart Money Concepts (SMC) & Dealing Range Engine

Arsitektur SMC bertumpu pada formula resmi LuxAlgo Pine Script v6 (`src/indicators/lux_smc_official.pine`) dan standar ComLucro:

1. **Active Structural Impulse Leg Anchor**:
   - Menggantikan penarikan naif `np.argmax(highs)` 120-bar.
   - **Bearish Range**: `RANGE HIGH (BSL)` dikunci pada Origin Swing High (`LH`) yang memicu impulse breakdown, dan `RANGE LOW (SSL)` dikunci pada `LL` terbawah yang terkonfirmasi.
   - **Bullish Range**: `RANGE LOW (SSL)` dikunci pada Origin Swing Low (`HL`) yang memicu impulse breakout, dan `RANGE HIGH (BSL)` dikunci pada `HH` teratas.
2. **Sequential Structural Hierarchy Tracking**:
   - Menggunakan *noise buffer* $0.15\times\text{ATR}$ (~1.6 pips).
   - Pantulan minor di dalam tren turun **dilarang keras dilabeli `HH`**. Semua pantulan internal otomatis dilabeli `LH` (merah).
   - Label `HH` murni hanya diberikan jika harga fisik menembus Active Structural High sebelumnya (Bullish BOS).
3. **5-Tier Dealing Range Zones**:
   - Deep Discount: $\le 38.2\%$ (Area OTE Institutional Buy)
   - Shallow Discount: $38.2\% - 50.0\%$ (Inducement Buy)
   - Equilibrium: $50.0\%$ (No Trade Zone / Inaction)
   - Shallow Premium: $50.0\% - 61.8\%$ (Inducement Sell)
   - Deep Premium: $\ge 61.8\%$ (Area OTE Institutional Sell)

---

## 5. Macro Strategic Engine (MSE) & Zone Confluence Engine (ZCE)

1. **Barrier Chamber State Machine (6-TF Native Sockets)**:
   - Mengolah 6 timeframe MT5: `MN1` (50 bar), `W1` (100 bar), `D1` (350 bar), `H4` (400 bar), `H1` (250 bar), `M30` (200 bar).
   - Memetakan 4 stasiun berurutan di atas harga ($C_1, C_2, C_3, C_4$ Ceiling) dan 4 stasiun di bawah harga ($F_1, F_2, F_3, F_4$ Floor).
2. **ZCE (True Zonal Bands & Dynamic EMA)**:
   - Lebar zona wick-to-body: $[0.05\times, 0.35\times\text{ATR_TF}]$.
   - Dynamic EMA Bands: EMA 20, 50, 100, 200 di H1/H4/D1 (bobot 0.25).
   - Special G3 Protocol: Skor konfluensi $\ge 8.5$ wajib didukung confirmed macro swing atau psychological level anchor.
3. **5-Tier Operational Action Matrix**:
   - `FULL_ALLOW`: Searah makro, 100% ukuran lot, runner aktif.
   - `REDUCED_CONFIDENCE`: Makro moderat/netral, pengali lot $0.75\times$.
   - `TP1_ONLY_SCALP`: Counter-trend berkualitas tinggi (M1 SFP), 100% volume exit di TP1.
   - `WATCH_ONLY`: Berada di area mid-chamber / koridor transit, 0 order MT5.
   - `HARD_BLOCK`: Tabrak hard trap, jarak ke dinding $< 1.0\times\text{ATR}$, 0 token LLM.

---

## 6. Currency Basket Synchronization System (CBSS) & Lead-Lag Relay

1. **Pemetaan Keranjang Mata Uang**:
   - 8 mata uang global (USD, EUR, GBP, JPY, CHF, AUD, CAD, NZD) dipetakan ke konstituen masing-masing.
2. **Local Pair G3 Wall Veto (The EURAUD Law)**:
   - Sinyal ditolak jika instrumen menempel langsung pada benteng G3 lawan ($dist \le 0.35\times\text{ATR}$).
3. **Basket Concurrency Cap**:
   - Maksimal 2 posisi terbuka pada keranjang mata uang yang searah.
   - Setup A+ ketiga yang lolos dialihkan otomatis ke Virtual Paper Trade (`SKIPPED_CBSS_BASKET_CAP`, 0 token) agar performa teknikal tetap tercatat tanpa melanggar eksposur risiko portofolio.
4. **Lead-Lag Liquidity Relay**:
   - Mengidentifikasi pair penggerak utama (*Leader*) dan merutekan entri ke pair pengikut (*Laggard*) yang memiliki clearance runway lebih luas.

---

## 7. Stage 2: 3-LLM Consensus Jury & Hard Risk Veto

1. **Pass 1 — Analisis Independen Paralel (~3.0s)**:
   - **OpenAI o4-mini**: Chief Quantitative Macro Strategist.
   - **Gemini 3.1-Flash**: Master Price Action Tactician.
2. **Pass 2 — Audit Cross-Examination (~1.5s)**:
   - **DeepSeek V4-Flash**: Chief Risk Officer (CRO) / Devil's Advocate. Memeriksa 24 candle mikro M5 live untuk mendeteksi anomali *falling knife* atau *waterfall*.
3. **Strict Unanimous 3/3 Rule**:
   - Wajib sepakat bulat 3/3 model aktif (3/3 BUY atau 3/3 SELL).
   - Jika ada 1 model saja yang HOLD/REJECT, sistem otomatis memutuskan **HOLD** (Zero Tolerance Split).
   - Sinyal Unanimous $\ge 80\%$ confidence memicu pembagian 2 posisi (@ $0.625\times$ lot = +25% boost).
4. **Master Hard Risk Veto Flags**:
   - `COUNTER_TREND_MOMENTUM`
   - `LIQUIDITY_TRAP`
   - `HIGH_IMPACT_NEWS`
   - `SPREAD_SPIKE`
   - `FALLING_KNIFE_WATERFALL`
   - `UNMITIGATED_IMPULSE_CHASE`
   - `SYSTEMIC_CURRENCY_DUMP`

---

## 8. Geometri Trade Kuantitatif & Proteksi Modal

1. **Plafon Lot Maksimal Akun Cent (`MAX_POSITION_LOT = 0.50`)**:
   - Mengunci lot efektif maksimal $\le 0.50$ lot pada akun Cent, mengeliminasi risiko ukuran posisi liar akibat SL ketat.
2. **Friction-Aware Net R:R (Divisor 0.20)**:
   - Total friksi (spread + komisi round-turn) tidak boleh melebihi 20% dari jarak SL.
3. **Formula SL Tiga Suku Atlas DNA**:
   $$\text{SL} = \max(\text{struct_dist} + \text{buffer}, 1.00\times\text{ATR}, \text{friction_floor})$$
   dengan $\text{buffer} = \max(0.15\times\text{ATR}, (2\times\text{spread} + 10)\times\text{point})$.
4. **Segmented Safety Floors**:
   - Quiet/Standard FX: $\ge 120\text{ pts}$ ($12\text{ pips}$)
   - High-Beta FX: $\ge 180\text{ pts}$ ($18\text{ pips}$)
   - JPY Crosses: $\ge 250\text{ pts}$ ($25\text{ pips}$)
   - NZD Crosses: Tambahan $+20\text{ pts}$ anti-wick padding.
5. **Kualitas Setup 4-Tier**:
   - **Grade B Wall Scalp** ($0.75R - 1.25R$): 1 tiket, bypass partial, BEP di 35% TP.
   - **Grade A Standard Intraday** ($1.25R - 1.80R$): Partial 50% di 50% TP, BEP di 50% TP.
   - **Grade A+ Expansion Runner** ($1.80R - 2.50R$): Wajib konfirmasi fisik Breached Wall Law H1.
   - **Grade S Macro Super-Shock** ($2.50R - 3.50R$): BEP di 65% TP.

---

## 9. Proteksi Posisi Real-Time (`position_manager.py`)

1. **3-Tier Progressive Trailing Ladder**:
   - **Tier 1 ($\ge 75\%$ TP)**: Kunci floating profit sebesar **50% TP**.
   - **Tier 2 ($\ge 90\%$ TP)**: Kunci floating profit sebesar **80% TP**.
   - **Tier 3 (Terminal Lock $\ge 95\%$ TP)**: Kunci floating profit sebesar **90% TP**.
2. **Midday Retracement Guard (11:00 – 13:00 WIB)**:
   - Melindungi floating profit saat transisi likuiditas siang hari (The 65% Pullback Boundary Rule).
3. **Pre-News Emergency Shield (Window $\pm 30$ Menit)**:
   - Berita High-Impact US membekukan pembukaan trade di seluruh 26 FX pair.
   - Posisi floating profit tipis diamankan ke BEP atau ditutup jika berisiko tergelincir slippage.
4. **Peak-Aware Time-Decay Stagnation Exit**:
   - Posisi tertahan $\ge 4$ jam di rentang $[-0.20R, +0.20R]$ ditutup jika Peak MFE $< +0.30R$.
5. **Pre-Rollover Shield (03:50 – 04:15 WIB)**:
   - Menutup bersih posisi yang berada dalam jarak bahaya lonjakan spread rollover sebelum jam 04:00 WIB.

---

## 10. Integrasi LuxAlgo MCP & Sumber Resmi

- **Endpoint Resmi**: `https://mcp.luxalgo.com/mcp` (Streamable HTTP / SSE, Free, Keyless, Read-Only).
- **Konfigurasi Global**: Terdaftar di `~/.gemini/config/mcp_config.json` dengan identitas `"luxalgo"`.
- **42 Tools Kuantitatif**: Termasuk `library_search`, `library_get_concept`, `library_get_source_code`, `edge_report`, dan `propfirms_simulate_trades`.
- **Source Code Resmi**: Tersimpan permanen di `src/indicators/lux_smc_official.pine` (49.8 KB, 848 baris) sebagai acuan formula BOS, CHoCH, Order Block, FVG, dan Dealing Range.
