# Unified Quantitative Engine Replay & Predictive Matrix ("Where to Wait")

## 1. Executive Summary & Problem Context

Dalam sistem trading partner XAU/FX saat ini, arsitektur kuantitatif inti kita telah dilengkapi dengan modul-modul institusional berkemampuan tinggi:
1. **Macro Strategic Engine (MSE)**: Pemetaan 6-Timeframe Native Sockets (`MN1/W1/D1/H4/H1/M30`), stasiun benteng $C_1..C_4$ dan $F_1..F_4$, serta 5-Tier Action Matrix.
2. **Zone Confluence Engine (ZCE)**: True Zonal Bands, Dynamic EMA Bands (20/50/100/200), dan penandaan level Support-Become-Resistance (SBR) serta Resistance-Become-Support (RBS).
3. **Macro Envelope & Pattern Engine**: Deteksi Active Inducement Dealing Range, Order Flow Backbone Zigzag, dan klasifikasi pola geometris.
4. **Wave Regime Engine**: Pengenalan rezim pasar (`YOUNG_OSCILLATION`, `COMPRESSION_BOX`, `MATURE_RANGE`, `EXHAUSTION`).

Namun, fungsi penanda historis pada dashboard (`detect_historical_triggers`) sebelumnya dibangun secara terpisah menggunakan rumus lokal yang disederhanakan (*isolated stateless checklist*). Hal ini menimbulkan diskoneksi:
- Penanda di masa lalu tidak mencerminkan narasi struktural yang utuh (seperti siklus: *Impulse $\to$ Retracement 50% EQ $\to$ Box Compression $\to$ Inducement Sweep M1B $\to$ Breakdown Expansion M4 $\to$ SBR Retest M3*).
- Ketika dibatasi pada Dealing Range terakhir secara statis, penanda historis menjadi terlalu sedikit atau terpotong sebelum narasi pembentukan selesai.
- Pengguna belum disajikan proyeksi prediktif yang eksplisit mengenai **"Di mana kita harus menunggu setup berikutnya (Where to Wait)"** berdasarkan posisi harga live terhadap stasiun ZCE dan EMA.

Tujuan dari dokumen desain ini adalah menyatukan seluruh kecerdasan engine kuantitatif ke dalam **Historical Engine Replay** yang presisi dan menghadirkan panel prediktif **"Where to Wait"** pada cockpit dashboard.

---

## 2. Arsitektur Komponen

Sistem dibagi menjadi 2 komponen utama yang saling terintegrasi:

```
┌────────────────────────────────────────────────────────────────────────┐
│               UNIFIED ENGINE REPLAY & PREDICTIVE SYSTEM                │
└────────────────────────────────────────────────────────────────────────┘
                                   │
         ┌─────────────────────────┴─────────────────────────┐
         ▼                                                   ▼
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│          KOMPONEN 1             │       │          KOMPONEN 2             │
│  Stateful Structural Replay     │       │     Predictive Radar Matrix     │
│       (Narasi Bar Historis)     │       │     ("Where to Wait" Standby)   │
├─────────────────────────────────┤       ├─────────────────────────────────┤
│ • Rolling 120-bar context       │       │ • Menghitung 3 stasiun tunggu:  │
│ • Deteksi Box & Inducement M1B  │       │   1. Pullback Zone (M2 / M3)    │
│ • Deteksi EQ & EMA Pullback M2  │       │   2. Liquidity Sweep (M1A)      │
│ • Deteksi SBR/RBS Retest M3     │       │   3. Breakout Expansion (M4)    │
│ • Deteksi Shock Breakdown M4    │       │ • Jarak pips & R:R terproyeksi  │
│ • 8-Gate Execution Verification │       │ • Kondisi trigger eksplisit     │
└─────────────────────────────────┘       └─────────────────────────────────┘
```

---

## 3. Komponen 1: Stateful Structural Replay (Deteksi Historis)

### 3.1. Rentang Waktu (Temporal Horizon)
- Jendela pengamatan: **Rolling 120 bar H1** (~5–7 hari pasar aktif).
- Tidak lagi dipotong oleh dealing range tunggal yang baru terbentuk, melainkan membaca siklus swing dan box point-in-time.
- Tetap mematuhi **Session Window & Dead Zone Guard**:
  - Veto bar pada akhir pekan (Sabtu/Minggu).
  - Veto bar pada **Dead Zone 00:00 – 07:00 WIB**.
  - Veto bar pada **Friday Night Freeze $\ge$23:00 WIB**.

### 3.2. Taksonomi Setup yang Direkonstruksi
1. **M1A — Extreme Liquidity Sweep (Universal Sweep)**:
   - **Kondisi**: Harga menembus puncak/lembah mayor sebelumnya di area Deep Premium ($\ge 61.8\%$ DR) atau Deep Discount ($\le 38.2\%$ DR) atau menyapu level $C_1/F_1$.
   - **Konfirmasi**: Candle ditutup membalik (rejection) dengan sumbu (wick) $\ge 30\%$ dari rentang lilin.
   - **Label**: `M1A` (Warna: Hijau untuk BUY, Merah/Rose untuk SELL).
2. **M1B — Internal Inducement Trap (Box Sweep)**:
   - **Kondisi**: Terjadi saat pasar berada dalam fase konsolidasi/box (Wave Regime `COMPRESSION_BOX` atau rentang sideways di area $38.2\% - 61.8\%$).
   - **Konfirmasi**: Lilin menyapu batas atas/bawah box (Order Block internal) dengan sumbu $\ge 35\%$, lalu berputar kembali ke dalam range.
   - **Label**: `M1B` (Warna: Oranye / Kuning Amber).
3. **M2 — Trend-Aligned Pullback**:
   - **Kondisi**: Terjadi saat pasar memiliki tren terarah (EMA20 > EMA50 untuk uptrend, EMA20 < EMA50 untuk downtrend) atau retrace ke 50% Equilibrium.
   - **Konfirmasi**: Harga menyentuh koridor EMA20/50 (toleransi $\le 0.15\times\text{ATR}$) lalu memantul dengan rejection wick $\ge 20\%$ atau candle konfirmasi searah tren.
   - **Collision Guard**: Veto BUY jika jarak ke $C_1 < 0.40\times\text{ATR}$ atau $\text{DR} \ge 80\%$; Veto SELL jika jarak ke $F_1 < 0.40\times\text{ATR}$ atau $\text{DR} \le 20\%$.
   - **Label**: `M2` (Warna: Hijau untuk BUY, Merah untuk SELL).
4. **M3 — Support-Become-Resistance (SBR) / RBS Retest**:
   - **Kondisi**: Level struktur horizontal atau benteng ZCE ($C_1..C_4$ / $F_1..F_4$) yang sebelumnya berhasil dijebol, diuji kembali dari sisi sebaliknya.
     - *SBR*: Bekas support dijebol ke bawah, kini bertindak sebagai atap resistance ceiling.
     - *RBS*: Bekas resistance dijebol ke atas, kini bertindak sebagai lantai support floor.
   - **Konfirmasi**: Re-touch pada level tertembus dalam batas $\pm 0.25\times\text{ATR}$ dan ditutup menolak level tersebut.
   - **Exhaustion Guard**: Menghitung jumlah sentuhan (`touch_count`). Jika touch $\ge 4$ tanpa rejection kuat, setup dinilai exhausted.
   - **Label**: `M3` (Warna: Biru / Sky Blue).
5. **M4 — Momentum Expansion Super-Shock**:
   - **Kondisi**: Lilin ekspansi impulsif bervolume tinggi menembus batas box, batas range, atau stasiun ZCE.
   - **Konfirmasi**: Rentang lilin $\ge 1.4\times\text{ATR}$, rasio body $\ge 65\%$, dan ditutup di luar batas penembusan (*physical breach*).
   - **Label**: `M4` (Warna: Ungu / Violet).

---

## 4. Komponen 2: Predictive "Where to Wait" Matrix

Komponen ini menjawab pertanyaan inti: **"Berdasarkan kondisi saat ini, di mana kita harus menunggu harga dan apa syarat eksekusinya?"**

### 4.1. Tiga Stasiun Menunggu Standby (The 3 Waiting Stations)
Untuk simbol apa pun yang dibuka pada cockpit dashboard, mesin menghitung 3 stasiun standby berdasarkan posisi harga bid/ask terkini:

1. **Stasiun Atas: Pullback Retest Zone (M2 Trend Retest / M3 SBR)**:
   - **Level Harga**: Titik temu antara EMA20/50 terdekat atau ceiling $C_1/C_2$ terdekat di atas harga live.
   - **Metrik**: Jarak pips dari live price ($+X.X$ pips), estimasi Stop Loss, Target TP ($F_1$ atau low sebelumnya), dan Net R:R terproyeksi.
   - **Trigger Rule**: *"Tunggu harga naik ke [Price], lalu cetak rejection wick $\ge 20\%$ searah downtrend."*
2. **Stasiun Bawah: Extreme Liquidity Sweep (M1A Universal Sweep)**:
   - **Level Harga**: Lantai terdekat $F_1$ / Previous Daily Low (PDL) / batas 0% Dealing Range di bawah harga live.
   - **Metrik**: Jarak pips dari live price ($-X.X$ pips), estimasi Stop Loss, Target TP (Equilibrium 50%), dan Net R:R terproyeksi.
   - **Trigger Rule**: *"Tunggu harga menusuk di bawah [Price] untuk sapu likuiditas SSL, lalu reclaim kembali ke atas level dengan lower wick $\ge 30\%$."*
3. **Stasiun Tembus: Momentum Expansion Continuation (M4 Breakdown/Breakout)**:
   - **Level Harga**: Garis batas struktural $C_1$ (untuk breakout BUY) atau $F_1$ (untuk breakdown SELL).
   - **Metrik**: Target ekspansi ke $C_2$ atau $F_2$.
   - **Trigger Rule**: *"Tunggu H1 close bersih di luar level [Price] dengan volume/range $\ge 1.4\times\text{ATR}$ dan body ratio $\ge 65\%$."*

### 4.2. Penyajian UI di Cockpit Dashboard
- **Telemetry Card**: Menampilkan panel **"WHERE TO WAIT (NEXT STATIONS)"** di cockpit dengan 3 kartu stasiun yang jelas (Pullback, Sweep, Expansion).
- **Chart Visual**: Menampilkan garis target proyeksi dinamis tipis dengan label stasiun di sisi kanan chart agar trader bisa melihat langsung secara visual seberapa jauh harga live dari stasiun tunggu.

---

## 5. Rencana Pengujian & Verifikasi (Testing Plan)

1. **Unit Test Suite**:
   - Menambahkan pengujian di `tests/test_dashboard.py` untuk memverifikasi bahwa:
     - Deteksi rolling 120-bar berhasil mengenali urutan sekuensial M1A, M1B, M2, M3, M4.
     - Struktur payload `predictive_standbys` / `where_to_wait` terisi dengan 3 stasiun lengkap beserta jarak pips dan aturan trigger.
   - Memastikan unit test `test_dashboard.py` dan `test_pattern_engine.py` lulus 100%.
2. **Audit Verifikasi Kasus Riil (AUDJPY)**:
   - Menjalankan inspeksi pada data riil AUDJPY-ECN dari 8–11 September 2026.
   - Memastikan seluruh tahapan cerita (Impulse 8 Sept, Box & M1B 9 Sept, M4 Breakdown 10 Sept, SBR M3 & M2 11 Sept) terpetakan dengan tepat.
3. **Pemeriksaan Live Server**:
   - Memverifikasi endpoint `/api/symbol/<sym>` memancarkan data `strategy_audit_markers` dan `predictive_matrix`.
   - Menguji tampilan antarmuka web dashboard di `http://localhost:8765`.

---

## 6. Self-Review & Integritas Arsitektur
- **Bebas Placeholder**: Seluruh threshold kuantitatif ($1.4\times\text{ATR}$, $0.40\times\text{ATR}$ collision, $30\%$ wick, Net R:R $\ge 1.25$) didefinisikan secara tegas.
- **Konsistensi Codebase**: Menggunakan modul yang sudah ada (`MacroEnvelopeEngine`, `MarketScanner.get_radar_standbys`, `ZoneConfluenceEngine`) tanpa duplikasi logika.
- **Single Source of Truth**: Tetap mematuhi aturan `.env` dan konversi waktu GMT+3 ke WIB (+4 jam).
