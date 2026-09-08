# Changelog September 2026 — Trading Bot Multi-LLM Consensus

> Dokumen ini mencatat seluruh perubahan arsitektur, fitur baru, dan riset kuantitatif sistem bot trading MetaTrader 5 periode September 2026.

## 0.0.0.0.0.0. Perubahan 8 September 2026 (Sore II) — Integrasi Pipeline Dynamic Basing Box ke Macro Cache, Scan Retest Window, dan Normalisasi F1/C1 Fallback Guarantee

### Latar Belakang & Identifikasi Masalah:
1. **Putusnya Pipeline Data Basing Box**:
   - `_build_single_macro_context()` di `market_scanner.py` belum memanggil `detect_dynamic_basing_box()` dan belum memasukkan field `basing_box` ke `macro_cache`.
   - Karena `dashboard.py` membaca `macro = self.scanner.macro_cache.get(sym)`, field `basing_box` selalu bernilai `{}` kosong dan telemetry menampilkan `Basing Box: —` di seluruh 26 pair.
2. **Kebutuhan Identifikasi Window Retest M3**:
   - Pasar saat ini berada dalam fase ekspansi/tren aktif London–NY (rentang candle $\ge 2.0\times\text{ s/d } 3.7\times\text{ATR}$ vs batas horizontal $\le 1.60\times\text{ATR}$).
   - Jendela retest M3 membutuhkan deteksi box yang baru saja tertembus ($\le 4$ bar) untuk menangkap level breakout/breakdown.
3. **Filter F1/C1 Chart Mengalami Asimetri**:
   - Di `dashboard.py`, fallback `F1`/`C1` hanya mengecek `if not zce_floors:` / `if not zce_ceils:`. Jika ZCE hanya memilih tier sekunder (`C2` atau `F2`), fallback terlewati sehingga `zce_walls` tidak memiliki `C1` atau `F1`.
   - Di `dashboard_assets.py`, pengecekan string tipe hanya memeriksa `"ceil"`, padahal Python mengirimkan `"ceiling"`.

---

### Komponen & Solusi Utama:
1. **Koneksi Pipeline Basing Box ke `macro_cache` (`src/analytics/market_scanner.py`)**:
   - Menghitung `detect_dynamic_basing_box(df, atr_val=cur_atr)` langsung di `_build_single_macro_context()` dan menyimpannya ke `self.macro_cache[valid_sym]['basing_box']`.
2. **Deteksi Jendela Breakout Retest & Telemetri Ekspansi (`src/indicators/wave_regime.py`)**:
   - Memindai offset $k \in [1, 5]$ bar jika bar live `[-1]` tidak sedang kompresi. Mengembalikan status `is_broken: True`, `broken_recency: k`, dan level fisik `box_ceiling` / `box_floor` (contoh: `EURCAD-ECN` BROKEN 11b, 4b ago; `GBPUSD-ECN` BROKEN 18b, 2b ago).
   - Menghitung `current_range_atr` untuk memberikan informasi kuantitatif saat pasar sedang ekspansi (contoh: `EURUSD-ECN` INACTIVE 3.75x ATR, expanding).
3. **Normalisasi Dinding F1/C1 & Fallback Primary (`dashboard.py` & `dashboard_assets.py`)**:
   - Memastikan setiap pair dijamin memiliki minimal 1 `F1` (Support) dan 1 `C1` (Resistance) via `has_f1` / `has_c1` checks.
   - Memperbaiki pengecekan string tipe `"ceiling"` dan menambahkan fallback `primaryFloor` / `primaryCeil` pada preset `Primary (F1/C1 Only)`.
   - Watchlist mendukung chip oranye `RETEST {bars}b` jika baru tertembus $\le 4$ bar lalu.
4. **Verifikasi Test Suite**:
   - `test_basing_box_and_csm_bailout.py`: **6/6 PASSED (100%)**.
   - `test_market_scanner.py`: **34/34 PASSED (100%)**.
   - Full test suite: **209/209 PASSED (100%)**.

---

## 0.0.0.0.0. Perubahan 8 September 2026 (Sore) — Granular 1-by-1 ZCE Fortress Ladder Filter, Standardisasi Google Material Symbols (0% Emoji), Eliminasi Garis Horizontal EMA, dan Dual Collapsible Drawers

### Latar Belakang & Identifikasi Masalah:
1. **Visual Clutter pada Candlestick Chart**:
   - Level ZCE multi-horizon sebelumnya ditampilkan seluruhnya secara default (`all`), ditambah garis putus-putus reticle standby M1–M4 dan temporal markers, sehingga memenuhi area chart dan menyulitkan operator membaca formasi candlestick live.
   - Indikator EMA (20, 50, 200) menampilkan garis horizontal statis dan label harga pada sumbu kanan yang membingungkan dengan level order/ZCE.
   - Baris metrik HUD kiri atas (`ADX`, `STATE`, `SESSION`, `WAVE REGIME`, `PRE-ROLLOVER`) terlalu panjang dan melebar melebihi batas pandang nyaman.
2. **Keterbatasan Screen Real Estate Chart**:
   - Sidebar kiri (26-Pair Proximity Watchlist) dan bottom drawer (MT5 Positions & Telemetry) memakan ruang vertikal dan horizontal yang besar, sehingga candlestick chart utama menjadi sempit pada layar monitor standar/laptop.

---

### Komponen & Solusi Utama:
1. **Granular Multi-Tier ZCE & Radar Filter (`dashboard_assets.py`)**:
   - **Ladder Presets**:
     * `F1/C1` (Default): Hanya menampilkan dinding primer terdekat (F1 Floor & C1 Ceiling).
     * `Macro G3`: Menampilkan dinding primer + macro multi-day liquidity walls.
     * `All Zones`: Menampilkan seluruh spektrum zona ZCE multi-horizon.
     * `Off`: Mematikan seluruh garis level ZCE untuk tampilan chart bersih murni.
   - **Filter 1-1 Granular Chips (Standardisasi Google Material Symbols — 0% Emoji)**:
     * `Floors`: Icon `vertical_align_bottom`, toggle instan lantai support.
     * `Ceils`: Icon `vertical_align_top`, toggle instan atap resistance.
     * `M1-M4`: Icon `radar`, silencer garis putus-putus radar dan marker proyeksi 3-point trajectory vectors.
     * `F1`, `C1`, `F2/C2`, `G3`: Kontrol granular per-tier struktural.
2. **Eliminasi Garis Horizontal EMA & Penambahan Legenda Kanan Atas (`dashboard_assets.py`)**:
   - `addLineSeries` untuk EMA 20, EMA 50, dan EMA 200 diatur dengan `priceLineVisible: false`, `lastValueVisible: false`, dan `title: ""` (mengeliminasi seluruh garis horizontal statis dan teks pada price axis).
   - Menambahkan legenda EMA terdedikasi `#chart-ema-legend` pada sudut kanan atas (`top: 10px; right: 65px;`) dengan garis indikator warna (`#00e5ff`, `#ffd740`, `#b388ff`).
   - Menyelaraskan posisi `#chart-mini-legend` ke `top: 38px; right: 65px;` agar tersusun rapi di bawah legenda EMA.
3. **Pemisahan Metrik HUD Kiri Atas Menjadi 2 Baris (`dashboard_assets.py`)**:
   - Baris 1: Symbol Tag + Multi-TF Compass Pills (`W1`, `D1`, `H4`, `H1`).
   - Baris 2 (`hud-line-2`): `ADX` • `STATE` • `SESSION`.
   - Baris 3 (`hud-line-3`): `WAVE REGIME` • `PRE-ROLLOVER`.
4. **Dual Collapsible Drawers (`dashboard_assets.py`)**:
   - **Left Sidebar Watchlist**: Ditambahkan tombol `#btn-toggle-left` dan label vertikal `26-PAIR RADAR WATCHLIST`. Mengklik toggle atau label vertikal melipat sidebar menjadi 32px, memperluas lebar chart secara drastis.
   - **Bottom Drawer**: Ditambahkan tombol `#btn-toggle-bottom`. Mengklik toggle melipat panel bawah menjadi 38px (hanya menampilkan tab bar). Mengklik sembarang tab drawer saat terlipat otomatis membuka kembali drawer.
   - **Auto-Resizing Canvas & Chart**: Pemanggilan `chart.resize()` dan `resizeOverlayCanvas()` dengan delay 220ms untuk memastikan sinkronisasi sempurna pasca-transisi CSS layout flexbox.
   - **Persistensi Preferensi Browser (`localStorage`)**:
     * Preferensi lipat (`left_collapsed`, `bottom_collapsed`, `xray_collapsed`), ladder preset (`zce_preset`), dan radar silencer (`zce_radar`) disimpan dan direstorasi otomatis saat page refresh.
5. **Verifikasi & Kompilasi**:
   - `python -m py_compile dashboard_assets.py dashboard.py`: **OK (Exit 0)**.
   - Test suite `python -m pytest tests/ -q`: **209/209 PASSED (100% OK)**.
   - `python dashboard.py`: Template HTML berhasil digenerate ulang.

---

## 0.0.0.0. Perubahan 8 September 2026 (Siang III) — Dynamic Basing Box Breakout & Retest (M3 Mean-Reversion), Rollover Outlier Filtering, dan CSM Dynamic Bailout Protection

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Pelewatan Setup Institutional Mean-Reversion Breakdown pada Titik Infleksi Tren (Studi Kasus AUDCAD)**:
   - Pada 08/09/2026 04:00 server (08:00 WIB), `AUDCAD-ECN` mengalami kompresi horizontal 35-bar H1 (sejak 04/09 16:00 server) dan menembus lantai kompresi di level `0.99634–0.99655`, lalu me-retest level tersebut di jam 07:00 server (11:00 WIB) dengan target runway terbuka lebar 180–200 poin menuju $F_1-G_3$ RBS. Setup short ini didukung kuat oleh Boitoki CSM Net Delta (-2.77 s/d -3.52).
   - Radar melewatkan trade short ini karena:
     * M3 sebelumnya hanya memantau level statis ekstrim (`PDL`, `PWL`, `BOS H1`), buta terhadap lantai konsolidasi lokal (*basing range box*).
     * Filter arah `can_sell_m3` mengunci short karena bias makro HTF berstatus netral (`0.0`), mengabaikan fakta bahwa seller mendominasi via CSM.
2. **Suicide Exit pada CSM Dynamic Bailout (`position_manager.py`)**:
   - Posisi BUY `AUDCAD-ECN` Ticket #675324733 dibuka di `csm_open = -2.77`.
   - Saat posisi floating rugi minor -30 pts (-0.25R), fungsi `_check_csm_dynamic_bailout()` melihat `csm_delta <= -2.0` secara statis kaku dan langsung membunuh trade di -0.25R, padahal pergeseran riil (*adverse shift*) hanya -0.75 (dari -2.77 ke -3.52).
3. **Distorsi Rollover Outlier Spike MT5 (00:00 Server / 04:00 WIB)**:
   - Pelebaran spread dan anomali wick saat pergantian hari broker mendistorsi rentang box kompresi jika dihitung menggunakan titik ekstrim High/Low murni.

---

### ✨ Komponen & Solusi Utama:
1. **Dynamic Basing Box Extraction & Rollover Sanitization (`src/indicators/wave_regime.py`)**:
   - Menambahkan fungsi `detect_dynamic_basing_box(df, min_bars=10, max_bars=48, max_range_atr=1.60, atr_val=None)`:
     * Menggunakan **Body Box** ($\max(\text{open}, \text{close})$ sebagai atap dan $\min(\text{open}, \text{close})$ sebagai lantai) untuk menolak distorsi spike rollover 00:00 server.
     * Mengidentifikasi rentang konsolidasi horizontal terpanjang ($10 \le N \le 48$ bar) yang memiliki rentang $\le 1.60\times\text{ATR}$.
     * Mengembalikan batas `box_ceiling`, `box_floor`, `box_bars`, dan `range_atr`.
2. **Integrasi M3 Mean-Reversion Breakdown & Retest (`src/analytics/market_scanner.py`)**:
   - Injeksi kandidat level `basing_floor` ke M3 SELL dan `basing_ceil` ke M3 BUY.
   - **Gate Arah Mean-Reversion**: Mengizinkan M3 beroperasi pada kondisi makro Netral atau Counter-Trend jika terkonfirmasi penembusan box dan CSM searah kuat ($|\text{CSM Delta}| \ge 1.50$).
   - **Sizing & Risk Rules**: Ditetapkan sebagai setup defensif **`GRADE_B`** (`REDUCED_CONFIDENCE`), Stop Loss ketat ($0.35\times\text{ATR}$ dengan safety floor per-simbol), TP dikunci di $F_1+5\text{ pts}$ (SELL) atau $C_1-5\text{ pts}$ (BUY) dengan Net R:R $\ge 0.75R + \text{friksi}$.
   - **ZCE Runway Relaksasi**: Ambang batas runway minimum diselaraskan ke $\ge 0.60\times\text{ATR}$ untuk Grade B Wall Scalp.
   - Memperbarui `get_radar_standbys()` agar menampilkan `Basing Box Breakdown Retest (Nb)` dan mengarahkan vektor ke -1 saat kondisi terpenuhi.
3. **Perbaikan Presisi CSM Dynamic Bailout (`src/analytics/position_manager.py`)**:
   - Mengganti filter statis kaku dengan kalkulasi delta pergeseran riil:
     * Trade BUY hanya di-bailout jika terjadi pergeseran negatif tajam `csm_shift <= -2.50`, ATAU jika trade dibuka saat CSM netral/positif (`csm_open >= -0.50`) lalu runtuh ke `csm_delta <= -2.0` dengan pergeseran $\le -1.50$.
     * Menghilangkan 100% false bailout pada trade yang sudah dibuka dengan opposed CSM.
4. **Telemetri Visual Cockpit Dashboard (`dashboard.py` & `dashboard_assets.py`)**:
   - Watchlist menampilkan chip `📦 BOX Nb` jika pair berada dalam status kompresi horizontal.
   - Tab Telemetry M3 menampilkan metrik `Basing Box: BOX Nb (Xx ATR)`.
5. **Verifikasi Test Suite**:
   - Unit test baru `tests/test_basing_box_and_csm_bailout.py`: **6/6 PASSED (100%)**.
   - Full test suite: **197/197 PASSED (100% OK)** tanpa ada regresi.

---

## 0.0.0. Perubahan 8 September 2026 (Siang II) — Pemisahan Taksonomi Layer 0 SFR vs Layer 1 M4 Basing, Dynamic Dealing Range M2 (Ride the Wave), dan Persistensi Directional Hysteresis ke Disk

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Kerancuan Taksonomi Layer 0 vs Layer 1 ("M4 Override M1-M3")**:
   - Filter pengunci arah global di baris 2846 `market_scanner.py` menggunakan nama `m4_catalyst` dan log `[M4 CATALYST VETO]`. Hal ini menciptakan miskonsepsi seolah-olah taktik entri M4 "meng-override" M1-M3, padahal yang mengunci arah adalah **Layer 0: Systemic Flow Regime (SFR)** berbasis anomali Z-score modal institusional ($|z| \ge 1.50$).
   - Di sisi lain, eksekusi M4 horizon swing retest tumpang-tindih dengan M2 (Pullback) dan M3 (Horizontal Breakout Retest). Edge unik M4 yang sesungguhnya adalah **High-Tight Basing** ($\le 0.35\times\text{ATR}$) saat harga bergerak terlalu kencang dan menolak pullback dalam.
2. **Kekakuan Dealing Range M2 Saat Aliran Modal Deras (Missing the Wave)**:
   - Ambang Dealing Range M2 legacy (SELL $\ge 0.35$, BUY $\le 0.65$) memblokir shallow pullback saat terjadi systemic surge/dump yang kuat, menyebabkan bot melewatkan momentum tren deras.
3. **Volatilitas RAM pada Directional Hysteresis 8 Jam**:
   - Status `_symbol_directional_state` (pengunci inersia arah 8 jam) sebelumnya murni hidup di memori RAM. Restart bot menyebabkan inersia ter-reset kembali ke nilai macro bias awal.
4. **Desinkronisasi Tampilan Dashboard Cockpit**:
   - Badge watchlist dan hero banner menampilkan label `M4 Shock`, membingungkan operator seolah-olah order M4 sedang aktif, padahal yang aktif adalah Layer 0 Systemic Flow Shock.

---

### ✨ Komponen & Solusi Utama:
1. **Pemisahan Taksonomi Layer 0 SFR vs Layer 1 M4 (`market_scanner.py`)**:
   - Menambahkan method `get_systemic_flow_regime(...)` dan return key bersih (`sfr_catalyst`, `sfr_side`, `sfr_age`).
   - Mengubah log penolakan di `_is_direction_allowed()` menjadi **`[SFR VETO]`**.
   - Menyelaraskan status preseden tertinggi menjadi `ALIGNED_SFR_SYSTEMIC_EXPANSION [SFR_CATALYST]`.
   - Mengkhususkan M4 pada `_m4_pending_ready()` dengan memprioritaskan **Mode B: High-Tight Basing Compression ($\le 0.35\times\text{ATR}$)** sebagai identitas primer.
2. **Dynamic Dealing Range M2 (Ride the Wave) (`market_scanner.py`)**:
   - **M2 BUY**: Batas dealing range dilonggarkan dari $\le 0.65$ ke $\le 0.80$ jika didukung `sfr_catalyst == "BULLISH_FLOW"` dan $\text{CSM Delta} \ge +1.0$.
   - **M2 SELL**: Batas dealing range dilonggarkan dari $\ge 0.35$ ke $\ge 0.20$ jika didukung `sfr_catalyst == "BEARISH_FLOW"` dan $\text{CSM Delta} \le -1.0$.
3. **Persistensi Disk Directional Hysteresis 8 Jam (`market_scanner.py`)**:
   - `_save_cooldowns()` dan `_load_cooldowns()` kini menyerialisasikan `symbol_directional_state` ke `data/scanner_cooldowns.json` dengan masa berlaku 8 jam (28800 detik).
   - Penguncian arah kini sepenuhnya bertahan saat bot direstart.
4. **Standardisasi Visual Dashboard Cockpit (`dashboard.py` & `dashboard_assets.py`)**:
   - Watchlist shock badge diubah menjadi **`⚡ SFR | z: ...`**.
   - Hero banner diubah menjadi **`SYSTEMIC FLOW REGIME (SFR) ACTIVE`**.
   - Status penguncian arah `dir_locked: BUY / SELL` diekspos ke UI cockpit.
   - Kolom Active Setup memprioritaskan setup entri actionable (M1, M2, M3, M4 Basing) dan tidak lagi tertutupi oleh background flow watching.
5. **Verifikasi Test Suite**:
   - Unit test baru `tests/test_sfr_and_basing_refinement.py`: **4/4 PASSED**.
   - Full test suite: **203/203 PASSED (100% OK)** dalam 38.94 detik.

---

## 0.0. Perubahan 8 September 2026 (Pagi) — Penyelarasan M4 Systemic Flow ke ZCE Structural Walls (Anchor Dekat F1/C1 & Target Vektor F2/C2 dengan G-Grade Attribution)

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Lookback Kaku 120-Bar H1 Terlalu Jauh dari Aksi Harga**:
   - Parameter legacy `M4_LOOKBACK_BARS = 120` (~5 hari bursa) menuntut harga menembus titik ekstrem mingguan sebelum breakdown/breakout dicatat. Jarak fisik sering mencapai $2.0\times - 3.5\times\text{ATR}$ (150–250 pips), menyebabkan bot kehilangan momentum awal ekspansi saat systemic surge terjadi di tengah dealing range.
2. **Latensi Tunggu 6 Jam (`M4_MIN_EPISODE_BARS = 6`)**:
   - Menunda evaluasi breakdown hingga 6 candle H1 pasca-lonjakan aliran modal membuat respons radar terlambat terhadap tembusan struktur dekat yang terjadi dalam 1–2 jam pertama.
3. **Ketiadaan Vektor Tujuan Struktural Berbasis ZCE**:
   - Target TP legacy bersifat kaku ($1.1R$ fixed) dan tidak mengidentifikasi stasiun tujuan ZCE ($F_2 / C_2$) maupun bobot densitas likuiditas klaster ($G_1, G_2, G_3$).

---

### ✨ Komponen & Solusi Utama:
1. **Penyelarasan Anchor Struktur Dekat ($F_1 / C_1$) (`market_scanner.py`)**:
   - Untuk **SELL ($z \le -1.50$)**: Mengunci **$F_1$ (ZCE Immediate Floor)** sebagai level tembusan dan retest (SBR). Jika $F_1$ tidak ada/terlalu jauh, menggunakan fallback swing 24-bar H1 (1 hari bursa).
   - Untuk **BUY ($z \ge +1.50$)**: Mengunci **$C_1$ (ZCE Immediate Ceiling)** sebagai level tembusan dan retest (RBS). Jika $C_1$ tidak ada/terlalu jauh, menggunakan fallback swing 24-bar H1.
2. **Vektor Tujuan & Target Runway ($F_2 / C_2$ dengan Grade Attribution)**:
   - Target SELL diarahkan langsung ke **$F_2$ (ZCE Deep Floor)** dengan front-run $5\text{ pts}$ sebelum dinding.
   - Target BUY diarahkan langsung ke **$C_2$ (ZCE Deep Ceiling)** dengan front-run $5\text{ pts}$ sebelum dinding.
   - Label telemetri dan radar standbys mencantumkan grade dinding ZCE ($G_1, G_2, G_3$):
     * Watch: `[M4 SELL WATCH: Floor F1 (G2) -> Destination F2 (G3)]`
     * Retest: `[M4 SELL RETEST: F1 (G2) -> F2 (G3)]`
3. **Harmonisasi Parameter Konfigurasi (`config.py` & `.env`)**:
   - `M4_LOOKBACK_BARS`: Diturunkan dari `120` ke `24` (1 hari perdagangan, selaras dengan rolling flow window 24-bar).
   - `M4_MIN_EPISODE_BARS`: Disesuaikan dari `6` ke `2` bar H1 guna merespons penetrasi struktur dekat secara cepat.
4. **Visualisasi Presisi di Dashboard (`dashboard_assets.py`)**:
   - Garis horizontal emas putus-putus digambar di level $F_1 / C_1$ yang relevan dan dekat dengan harga.
   - Marker candle menampilkan tooltip lengkap dengan anchor grade dan stasiun target $F_2 / C_2$.
5. **Verifikasi Test Suite**:
   - `tests/test_dashboard.py`, `tests/test_market_scanner.py`, `tests/test_shadow_tracker.py`: **50/50 Tests PASS (100% OK)**.

---

## 0.1. Perubahan 8 September 2026 (Malam Lanjut) — Implementasi 4-Tier Setup Quality System (Grade B, A, A+, S), Penegakan Rigid Breached Wall Law, dan Kompensasi Friksi Broker

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Blind-Spot Kompresi R:R Bersih pada Grade B Wall Scalp ($0.75R - 1.25R$)**:
   - Menghitung target TP kotor semata di $0.75\times\text{SL}$ pada pair dengan spread moderat (AUDCHF, EURGBP) dan komisi broker ECN ($6/lot round-trip) mereduksi return bersih menjadi $0.50R - 0.54R$.
   - Diperlukan *Friction Compensation Formula*: $\text{TP}_{\text{Gross}} \ge (0.75 \times \text{SL}) + \text{Spread} + \text{Commission}$, memastikan net reward bersih terjamin $\ge 0.75R$ dan menurunkan break-even winrate dari $66.7\%$ ke $57.1\%$.
2. **Rejection Wick Trap pada Pelompatan Target Stasiun C1/F1 ke C2/F2**:
   - Jika satu wick menembus C1/F1 namun candle H1 close di bawah C1 (rejection wick), melompatkan target TP ke C2 adalah fatal (membeli di atap resistensi institusional).
   - Diperlukan *Rigid Breached Wall Law*: Target dilarang keras melompati C1/F1 ke C2/F2 kecuali candle H1 terakhir sah close di luar batas distal ($Close > C_1$ BUY / $Close < F_1$ SELL) dengan body displacement $\ge 50\%$.
3. **Dual-Path Architecture untuk Grade S ($\ge 2.50R$)**:
   - Jalur LLM Aktif: Unanimous 3/3 $\ge 85\%$ + M4 / Apex.
   - Jalur Pure Quant No-AI (`ENABLE_LLM_JURY=False`): M4 Super-Shock ($|z| \ge 1.80$ + CSM Delta $|\Delta| \ge 2.00$ + ZCE Grade 3 Macro Wall Anchor) membuka target Macro Expansion ($2.50R - 3.50R$) dengan BEP dilonggarkan ke $65\%$ TP guna memberikan ruang ayunan tren.

---

### ✨ Komponen & Solusi Utama:
1. **Kompensasi Friksi & Runway Capacity Gate (`consensus.py` & `config.py`)**:
   - `min_wall_floor = int(sl_points * GRADE_B_MIN_RR) + friction_pts`.
   - Setup dengan runway di rentang $[0.75R + \text{friksi}, 1.25R + \text{friksi}]$ ditransisikan otomatis ke **Grade B Wall Scalp** (1 tiket, target C1/F1 murni, no partial close, BEP dipercepat 35%).
2. **Rigid Breached Wall Law & 4-Tier Setup Tagging (`atlas_dna.py`)**:
   - Menambahkan parameter `c1_breached` dan `f1_breached` ke `calculate_intraday_sl_tp`.
   - C2/F2 hanya dapat dibidik jika C1/F1 telah sah breached atau tidak ada halangan dinding tebal.
   - Tagging presisi: `GRADE_S` ($\ge 2.50R$), `GRADE_A_PLUS` ($1.80R - 2.50R$), `GRADE_A` ($1.25R - 1.80R$), dan `GRADE_B` ($0.75R - 1.25R$ / Wall Scalp).
3. **Validasi Displacement Candle H1 (`market_scanner.py`)**:
   - Implementasi helper `_is_zce_wall_breached`: mengecek penutupan fisik H1 bar terakhir di luar dinding + body ratio $\ge 50\%$ (`BREACHED_WALL_MIN_DISPLACEMENT`).
   - Meneruskan status breach ke pemanggilan kalkulasi SL/TP di M1, M2, dan M3.
   - Elevasi M4 Super-Shock ke `GRADE_S` pada mode Pure Quant No-AI.
4. **Proteksi Posisi & BEP Grade-Aware (`position_manager.py`)**:
   - Partial close 50% di-bypass total untuk Grade B Wall Scalp dan M4 guna menghemat kuota komisi broker.
   - BEP threshold diselaraskan: Grade S aktif di 65% TP, Grade B/Defensive di 35% TP, M4 di 70% TP, dan Grade A/A+ di 50% TP.
5. **Verifikasi Test Suite Penuh**:
   - Unit test suite: **195/195 Tests PASS (100% OK)** termasuk pengujian rigid breached wall dan dynamic BEP.

---

## 0.1. Perubahan 8 September 2026 (Malam) — Penandaan Visual M4 Systemic Flow Shock & Standardisasi Google Material Symbols di Cockpit Dashboard

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Visibilitas M4 Systemic Flow Shock Rendah di Watchlist**:
   - Shock anomali aliran sistemik ($|z| \ge 1.5$ atau reference bar / high-tight basing aktif) sebelumnya hanya tersimpan di memori radar backend dan tabel telemetri drawer, sehingga trader/observer tidak langsung mengetahui pair mana yang sedang mengalami shock aliran sistemik pada watchlist 26-pair utama.
2. **Kerapatan Vertikal Watchlist Sidebar Terlalu Sempit (2-Baris Padat)**:
   - Layout 2 baris sebelumnya (`padding: 6px 10px`) memadatkan teks jarak pips/ATR, setup pill, dan tag taktis sehingga sulit menyisipkan status Dealing Range % dan badge M4 Shock tanpa membuat elemen bertabrakan (*cluttered*).
3. **Inkonsistensi Visual Emoji Ritel (AI-Slop)**:
   - Penggunaan emoticon/emoji ritel (`⚠️`, `📊`, `🟢`, `🔴`, `🟡`, `🔵`, `⚪`, `🟣`, `▶`) menurunkan standar visual institusional dan tidak selaras dengan standar antarmuka kuantitatif profesional.

---

### ✨ Komponen & Solusi Utama:
1. **Watchlist Sidebar 3-Baris Longgar & Penandaan M4 Shock (`dashboard_assets.py`)**:
   - Peregangan vertikal baris watchlist: padding `.pair-row` dinaikkan ke `9px 10px` dengan `gap: 4px`.
   - Tata letak 3 baris teratur:
     * **Baris 1**: Simbol (`pair-symbol`) + CSM Delta (`csm-text`) | spacer | Action Tier Badge (`tier-badge` `GO`/`ARM`/`WATCH`/`LOCK`).
     * **Baris 2**: Active Setup Pill (`pair-setup-pill`) | Tactical Pill (`tactical-pill`) | HTF Bias Tag (`htf-bias-tag`).
     * **Baris 3**: Jarak Pips & ATR (`pair-dist-text`) | Dealing Range % (`DR: xx%`) | **M4 Shock Badge** (jika `p.m4_shock` aktif).
   - Penandaan khusus pair M4 Shock:
     * Border kiri emas: `border-left: 3.5px solid #facc15`.
     * Background tinting halus: `background: rgba(250, 204, 21, 0.04)`.
     * Badge baris ke-3: `<span class="m4-shock-pill"><span class="material-symbols-outlined">bolt</span> M4 | z:+/-X.X (DIR)</span>`.
2. **Hero Chart Header Banner untuk M4 Shock (`dashboard_assets.py` & `dashboard.py`)**:
   - Menambahkan banner emas responsif `#m4-hero-banner` di sub-header chart:
     `[bolt SYSTEMIC M4 FLOW SHOCK DETECTED • Dominant Currency z: +/-X.X (BULL/BEAR) • Standby Level / Basing Active]`.
   - Menyelaraskan endpoint backend `/api/symbol` (`get_symbol_detail` di `dashboard.py`) agar mengembalikan field `m4_shock`, `m4_z`, dan `m4_dir`.
3. **Standardisasi 100% Google Material Symbols Outlined (0% Emoji)**:
   - Memuat stylesheet resmi Google Fonts `Material Symbols Outlined` di `<head>` dan class `.material-symbols-outlined`.
   - Mengganti seluruh emoji ritel di HTML template, script, dan drawer telemetri:
     * Error banner `⚠️` $\rightarrow$ `warning`
     * Tombol laporan `📊 LAPORAN` $\rightarrow$ `monitoring` / `analytics` + `open_in_new`
     * Toggle Decision Gates `▶`/`◀` $\rightarrow$ `chevron_right`/`chevron_left`
     * Distribusi resolusi shadow `🟢 TP / 🔵 BEP / 🟡 Time-Decay / 🔴 SL / ⚪ Exp` $\rightarrow$ `check_circle`, `shield`, `timer`, `cancel`, `history_toggle_off`
     * Badge status MT5 `🟢 REAL MT5` / `🟣 PAPER` $\rightarrow$ `verified` / `science`
4. **Verifikasi Regresi Lengkap**:
   - Full test suite: **192/192 Tests PASS (100% OK)** dalam 50.61 detik.

---

## 0.2. Perubahan 8 September 2026 (Sore) — Harmonisasi Runway Capacity Gate dengan Floor Grade B (0.75R) & Quickfix UnboundLocalError Scanner

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Rejection Palsu Setup Valid Akibat Runway Capacity Gate Kaku 1.25R (`NZDCHF-ECN`)**:
   - Pada setup live `NZDCHF-ECN` (09:26 WIB), entry `0.47492`, raw SL 95 pts (`0.47587`), TP 165 pts (`0.47327` / target dinding $F_1$) memiliki R:R awal $1.74:1 \ge 1.25$ (`GRADE_A`).
   - Di `_apply_sltp_rules`, Safety Floor khusus NZD menaikkan SL ke 140 pts ($\max(120, 0.5\times\text{ATR}) + 20\text{ pts anti-wick padding}$).
   - Kenaikan SL ini mengompresi rasio R:R menjadi $165/140 = 1.18:1$.
   - Runway Capacity Gate pagi hari secara kaku memvalidasi $165 < 140 \times 1.25 = 175\text{ pts}$ dan membatalkan trade dengan pesan:
     `[!] Trade NZDCHF-ECN Dibatalkan (SL/TP Rules): ANCHOR_TOO_WIDE: ZCE Runway ke target terhalang dinding terdekat (165 pts < 1.25x SL 140 pts = 175 pts). SKIP trade — kapasitas runway tidak mencukupi.`
   - Padahal secara kuantitatif, setup ini adalah **Grade B Wall Scalp** yang sangat sehat ($1.18R \ge 0.75R$ floor) dengan target dinding $F_1$ presisi.
2. **Potensi Crash `UnboundLocalError: sl_tp` pada Mekanisme 3 (Breakout Retest)**:
   - Pada blok M3 BUY dan M3 SELL di `market_scanner.py`, evaluasi `if not in_retest_window_b:` / `_s:` tidak memiliki instruksi `continue`.
   - Ketika harga live berada di luar jendela sentuh retest, eksekusi melompat keluar dari blok `if/else` langsung menuju baris `sl = sl_tp['sl']`, menyebabkan `UnboundLocalError` karena variabel `sl_tp` belum diinisialisasi.

---

### ✨ Komponen & Solusi Utama:
1. **Harmonisasi ZCE Runway Capacity Gate dengan Floor Grade B 0.75R (`src/core/consensus.py`)**:
   - Menyelaraskan ambang pembatalan keras `ANCHOR_TOO_WIDE`: trade hanya di-skip jika jarak Runway menuju target $< 0.75 \times \text{SL}$ (`min_wall_floor = int(sl_points * 0.75)`).
   - Jika $0.75 \times \text{SL} \le \text{Runway} < 1.25 \times \text{SL}$: sistem secara otomatis mentransisikan setup menjadi **`GRADE_B` Wall Scalp** (`setup_grade = "GRADE_B"`, `action_tier = "GRADE_B"`).
   - Menyetel `min_rr = 0.75` dan `max_rr = 1.25` khusus untuk `GRADE_B` dan setup scalp.
   - Pada mode ZCE Wall Scalp (`is_grade_b_scalp and zce_wall_mode`), target TP diizinkan mengunci murni pada dinding $C_1/F_1$ tanpa dipaksa melampaui dinding oleh friksi komisi/spread jika jarak sudah $\ge 0.75R$.
2. **Pencegahan Multi-Position & Sinkronisasi Setup Grade (`main.py`)**:
   - Memperbarui variabel lokal `action_tier_val` dan `setup_grade_val` pasca eksekusi `_apply_sltp_rules` agar transisi ke `GRADE_B` terbaca langsung oleh dispatcher order.
   - Mengunci eksekusi `GRADE_B` pada 1 tiket murni (`num_positions = 1`), melarang split 2 posisi atau bonus runner.
   - Meneruskan `eff_grade` (`cand.setup_grade or cand.action_tier`) ke `position_manager.set_ticket_setup_grade`, menjamin posisi Grade B otomatis:
     * Menghindari partial close TP1 50% (`is_grade_b` bypass).
     * Mengaktifkan Break-Even Protection (BEP) agresif dipercepat di **35% TP**.
3. **Quickfix Bug Fallthrough Scanner (`src/analytics/market_scanner.py`)**:
   - Menambahkan `continue` pada baris `if not in_retest_window_b:` (BUY) dan `if not in_retest_window_s:` (SELL) di M3 Breakout Retest.
   - Menambahkan atribut `setup_grade: str = "GRADE_A"` pada dataclass `CandidateSetup` dan payload `to_payload_dict()`.
   - Mengisi `setup_grade` pada instansiasi kandidat M1, M2, dan M3: `"GRADE_B" if (sl_tp.get("setup_grade") == "GRADE_B" or rr_val < 1.25) else "GRADE_A"`.
4. **Verifikasi Unit Test Suite Lengkap**:
   - Menambahkan test case `test_zce_runway_grade_b_wall_scalp_pass` di `tests/test_zce_sltp_anchor.py` yang memverifikasi kasus nyata NZDCHF (SL 140 pts, TP 165 pts / 1.18R) lulus 100% dengan status `GRADE_B Wall Scalp` tanpa didorong melampaui dinding.
   - Hasil pengujian: **12/12 Tests PASS (100% OK)** di `test_zce_sltp_anchor.py`, serta **58/58 Tests PASS** pada rangkaian test regresi scanner dan M4.

---

## 0.3. Perubahan 8 September 2026 (Siang) — Paket Pembaruan Kuantitatif Komprehensif (Grade B Wall Scalp, Directional Hysteresis Memory, Multiplier Sesi, Bank Holiday Breaker, dan CSM Dynamic Bailout)

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Peluang Profit Terbuang Akibat Lompatan Target ke Dinding C2/F2**:
   - Pada setup di mana dinding struktural terdekat $C_1/F_1$ berada pada jarak $0.80 - 1.20R$ (misal 18 pips), sistem menolak $C_1$ karena aturan lama mewajibkan $R:R \ge 1.25R$.
   - Akibatnya, target dipaksa melompat jauh ke $C_2/F_2$ (40+ pips). Harga menyentuh $C_1/F_1$ dengan akurasi 100%, namun kemudian berbalik arah (reversal) sebelum mencapai $C_2$, merubah posisi profit tebal menjadi impas atau loss.
2. **Ketiadaan Inersia Arah (Flip-Flop Whipsaw)**:
   - Bot sebelumnya dapat melakukan BUY pada jam 15:00 lalu tiba-tiba melompat SELL pada jam 15:30 pada simbol yang sama hanya karena pullback tipis pada chart intraday, terjebak dalam whipsaw dua arah.
3. **Risiko Likuiditas Tipis Bank Holiday & Sesi New York**:
   - Pada hari libur perbankan AS (seperti US Labor Day 7 Sep 2026), likuiditas antar-bank menyusut drastis memicu spread spike dan sinyal palsu di sesi New York.
   - Sesi New York secara empiris membukukan tingkat kegagalan lebih tinggi dibanding sesi Asia yang beroperasi rapi di zona supply/demand.
4. **Drawdown Terlambat Cut Saat Arus Sistemik Berbalik Tajam**:
   - Ketika arus mata uang (CSM Net Delta) berbalik ekstrem melawan posisi (seperti GBP meledak kuat melawan CHF hingga shift $+4.51$), membiarkan posisi menunggu hit SL penuh mengakibatkan loss $1.0R$ padahal sinyal aliran modal sudah terbalik total sejak awal.

---

### ✨ Komponen & Solusi Utama:

1. **Quickfix Bug Scanner & Defensive Attribute Extraction (`src/analytics/market_scanner.py`)**:
   - Menambahkan `continue` pada runaway spike guard baris 3604 (BUY) dan 3773 (SELL) di `market_scanner.py` guna mengeliminasi `UnboundLocalError: sl_tp`.
   - Menggunakan safe `.get()` dengan pair-aware fallback untuk atribut `point`, `dealing_range_pos`, `is_bull`, `is_bear`, dan `trend_label` di seluruh modul scanner guna mencegah `KeyError`.
   - Memastikan variabel `clean_s` terdefinisi lokal di `_is_direction_allowed` dan loop simbol utama guna mencegah `free variable scope error`.
2. **Chamber Runway & Grade B Wall Scalp (`src/indicators/atlas_dna.py` & `src/analytics/position_manager.py`)**:
   - Di `atlas_dna.py`: Mengizinkan penguncian target stasiun langsung pada dinding terdekat $C_1/F_1$ jika jaraknya $\ge (0.75 \times \text{risk} + \text{friction})$ tanpa melompat ke $C_2/F_2$.
   - Mengembalikan metadata `setup_grade = "GRADE_B"` dan `is_wall_scalp = True` jika $R:R < 1.25$.
   - Di `position_manager.py`: Tiket dengan tag `GRADE_B` atau `SCALP` secara otomatis membypass Partial Close (TP1 50%) dan mengunci BEP agresif di 35% TP.
3. **Directional Hysteresis Memory Gate (`src/analytics/market_scanner.py`)**:
   - Menambahkan `_symbol_directional_state` pada radar scanner yang mengunci arah operasional simbol selama 8 jam (`DIRECTIONAL_LOCK_HOURS = 8.0`).
   - Melarang pembalikan arah 180° kecuali memenuhi salah satu dari 3 syarat sah kuantitatif:
     * **Syarat 1 (ZCE Chamber Breach)**: Harga menembus lantai $F_1$ ke bawah ($mid < F_1 - 0.20\times\text{ATR}$) untuk BUY-to-SELL atau menembus plafon $C_1$ ke atas untuk SELL-to-BUY.
     * **Syarat 2 (MSE Macro Inversion)**: Skor bias makro berbalik tajam ($\ge +0.35$ BUY / $\le -0.35$ SELL).
     * **Syarat 3 (Universal Liquidity Sweep M1A Ekstrem)**: Sapuan likuiditas M1A di batas Dealing Range ekstrim ($\ge 0.80$ SELL / $\le 0.20$ BUY). M1B dilarang membalik arah.
   - Status penguncian arah diekspor ke visualisasi dashboard (`DIR: BUY ONLY / SELL ONLY / FREE`) dan diaudit pada Gate 3 X-Ray Surveillance.
4. **Multiplier Sesi Lot & Bank Holiday Circuit Breaker (`config.py`, `.env`, `src/analytics/economic_calendar.py`)**:
   - Di `.env` & `config.py`: Menambahkan `SESSION_ASIA_LOT_MULT=1.2`, `SESSION_LONDON_LOT_MULT=1.0`, `SESSION_NY_LOT_MULT=0.8`.
   - Membatasi durasi sesi London di `ALLOWED_SESSIONS_WIB` hingga 20:00 WIB (bukan 23:00) agar multiplier New York (0.8x) otomatis aktif di rentang 20:00–00:00 WIB.
   - Di `economic_calendar.py`: Menambahkan deteksi event `impact == 'HOLIDAY'` dan metode `is_bank_holiday_today("ALL")` untuk membekukan order baru di sesi New York saat libur bank nasional.
5. **CSM Dynamic Flow Bailout (`src/analytics/position_manager.py`)**:
   - Mengimplementasikan `_check_csm_dynamic_bailout()` berbasis dual-gate:
     * **Gate Finansial**: Posisi sedang floating rugi $\le -0.25R$ (`CSM_BAILOUT_MIN_LOSS_R = -0.25`).
     * **Gate Aliran Sistemik**: Arus mata uang berbalik tajam melawan trade (shift $\ge 2.5$ dari harga buka atau nilai absolut opposed $\ge 2.0$).
   - Posisi yang sedang floating profit dilindungi dan dibiarkan bernapas hingga target TP.
6. **Audit Visual & Telemetri Real-Time Dashboard (`dashboard.py` & `dashboard_assets.py`)**:
   - Menambahkan kolom `CSM Shift` pada tabel Open Positions drawer untuk memantau pergeseran delta CSM live dan indikator `⚠️ BAILOUT RISK`.
   - Menambahkan badge status Directional Lock (`DIR: BUY ONLY / SELL ONLY / FREE`) pada strip header atas instrumen.
   - Memperbarui evaluasi Gate 1 (Session Multiplier & Bank Holiday) dan Gate 3 (Direction Lock) pada matriks X-Ray 7-Gate.
7. **Unit Test Suite Lengkap (`tests/test_sep8_enhancements.py`)**:
   - Mengembangkan 5 test case komprehensif yang menguji validitas Grade B Wall Scalp, bypass partial close, pemicu CSM bailout, deteksi bank holiday, dan directional lock.
   - Hasil pengujian: **5/5 Tests PASS (100% OK)**.

---

## 0.4. Perubahan 8 September 2026 (Pagi) — Dynamic ZCE Runway & Capacity Gate (Eliminasi Deadlock ANCHOR_TOO_WIDE) & Pembaruan Distribusi Outcome Komprehensif Shadow Tracker

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Deadlock Matematis Plafon Ceiling vs Safety Floor (`ANCHOR_TOO_WIDE`)**:
   - Di sesi malam dan Asia (00:00–08:00 WIB), volatilitas pair-pair tenang (*Quiet FX* seperti AUDCHF, EURGBP, NZDCHF) mengecil drastis dengan ATR H1 berkisar antara 36–44 pts.
   - Rumus plafon lama menetapkan ceiling kaku: $2.5 \times \text{ATR H1} = 90 - 110\text{ pts}$.
   - Sedangkan aturan Safety Floor menetapkan batas minimal proteksi spread broker sebesar $120\text{ pts}$ ($140\text{ pts}$ untuk NZD).
   - Akibatnya terjadi **Deadlock**: $\text{Ceiling (110 pts)} < \text{Floor (120 pts)}$. Sistem menaikkan SL ke 120 pts, lalu seketika membatalkan trade dengan pesan `[!] Trade AUDCHF-ECN Dibatalkan (SL/TP Rules): ANCHOR_TOO_WIDE: SL anchor 120 pts > ceiling 110 pts (2.5x ATR). SKIP trade — clamp akan memarkir SL di tengah struktur.`
   - Hal ini mematikan seluruh peluang trading valid di pair tenang selama sesi malam dan pagi hari.
2. **Kekurangan Transparansi Winrate Biner Shadow Tracker**:
   - Dashboard Shadow Tracker sebelumnya hanya menyajikan winrate biner sempit dari 30 sampel (`TP: 16 | SL: 14`), mengabaikan 60+ trade terselesaikan lainnya (BEP Locked, Time-Decay Stagnation Exit, Expired Limit).
   - Pengguna membutuhkan distribusi outcome yang komprehensif, terpisah, dan memiliki persentase masing-masing baik terhadap total setup maupun terhadap order yang terjemput (*filled trades*).

---

### ✨ Komponen & Solusi Utama:
1. **Dynamic ZCE Runway & Capacity Gate (`src/core/consensus.py`)**:
   - Menghapus pembatasan kaku $2.5 \times \text{ATR}$ yang menolak trade secara buta.
   - Menerapkan **ZCE Runway Capacity Gate**: Sistem memvalidasi kapasitas ruang jelajah (Runway) menuju dinding lawan ZCE terdekat ($C_1$ untuk BUY, $F_1$ untuk SELL).
   - **Aturan Evaluasi**:
     * Jika $\text{Runway (TP)} \ge \text{SL} \times \text{min\_rr}$ ($1.25R$): Setup memiliki jalan bebas hambatan menuju target struktural $\rightarrow$ **TRADE DITERIMA (PASS)**.
     * Jika $\text{Runway (TP)} < \text{SL} \times \text{min\_rr}$: Target terbentur dinding lawan ZCE terdekat $\rightarrow$ **TRADE DI-SKIP** dengan alasan kuantitatif: `"ANCHOR_TOO_WIDE: ZCE Runway ke target terhalang dinding terdekat (Runway < 1.25x SL)"`.
     * Plafon ekstrim struktural anti-runaway diperlebar ke $\max(3.5 \times \text{ATR}, 1.5 \times \text{Floor})$ guna mengeliminasi 100% false deadlock pada trade normal, sambil tetap memblokir swing liar multi-hari ($> 350\text{ pts}$ / test $5000\text{ pts}$).
2. **Pembaruan Distribusi Outcome Komprehensif Shadow Tracker (`shadow_tracker.py`, `shadow_report.py`, `dashboard_assets.py`)**:
   - **Kalkulasi Metrik Lengkap**: Menambahkan payload `outcome_breakdown` dengan persentase terpisah untuk 5 kategori hasil:
     * 🟢 **TP Hits (Win)**: 17.8% total / 21.6% filled ($\Sigma +16.72\text{R}$)
     * 🔵 **BEP Locked**: 27.8% total / 33.8% filled ($\Sigma +2.82\text{R}$)
     * 🟡 **Time-Decay Exit**: 21.1% total / 25.7% filled ($\Sigma -2.08\text{R}$)
     * 🔴 **SL Hits (Loss)**: 15.6% total / 18.9% filled ($\Sigma -14.00\text{R}$)
     * ⚪ **Expired / No-Fill**: 17.8% total ($0.00\text{R}$)
   - **Metrik Preservasi Modal**: Menampilkan **Capital Preservation Rate (Non-Loss Rate) 55.4%** dan **Profit Factor 1.22**.
   - **Multi-Segment Visual Bar**: Progress bar interaktif 5 segmen berwarna proporsional di `http://localhost:8765/shadow` dengan sinkronisasi real-time via polling 30 detik.
   - **Cockpit Telemetry Sync**: Memperbarui 4 kartu telemetri pada drawer Virtual Shadow di `dashboard.py` / `dashboard_assets.py`.
3. **Unit Test Suite 100% PASS**:
   - Menambahkan pengujian `test_zce_runway_capacity_pass_with_small_atr` dan `test_zce_runway_insufficient_skip` di `tests/test_zce_sltp_anchor.py`.
   - Menjalankan verifikasi regresi penuh: **186/186 Unit Tests Lulus (100% OK)**.

---

## 0.5. Perubahan 7 September 2026 (Sore) — Implementasi Mekanisme M1B (Trend-Following Induced Liquidity Sweep) dengan Konfluensi Geometris ZCE & Integrasi Visual Dashboard

### 🎯 Latar Belakang & Identifikasi Kebutuhan:
1. **Pemisahan M1A (Macro Counter-Trend SFP) dan M1B (Trend-Following Induced Sweep)**:
   - M1A beroperasi di batas ekstrem Dealing Range (Premium/Discount) untuk menangkap pembalikan harga (Mean Reversion).
   - M1B dirancang khusus untuk kondisi tren kuat (searah Macro Bias & CSM Net Delta) di mana harga membentuk internal basing/konsolidasi, melakukan false sweep (induced wick) menembus atap/lantai basing, lalu ditutup reclaim ke dalam area basing searah tren utama.
2. **Mandat Konfluensi Geometris ZCE (Anti-Arbitrary Basing)**:
   - Basing yang disapu DILARANG sembarang swing candle lokal. Basing WAJIB memiliki konfluensi geometris ($\le 0.50\times\text{ATR}$) dengan level Zone Confluence Engine (ZCE): Resistance C1/C2/SBR untuk setup SELL, atau Support F1/F2/RBS untuk setup BUY.
3. **Persyaratan Visibilitas Penuh di Dashboard Cockpit (`http://localhost:8765`)**:
   - Seluruh status radar M1B, level target, wick rejection ratio, konfluensi ZCE, dan garis horizontal reticle ungu neon `[M1B SWEEP ANCHOR]` di canvas chart wajib tersedia secara real-time di Cockpit Dashboard.

---

### ✨ Komponen & Solusi Utama:
1. **Parameter Konfigurasi (`config.py` & `.env`)**:
   - Menambahkan `M1B_ENABLED = True`, `M1B_SETUP_TYPE = "TREND_ALIGNED_INDUCED_SWEEP"`.
   - Menetapkan batas kuantitatif: `M1B_MIN_WICK_RATIO = 0.30` (wick $\ge 30\%$), `M1B_PENETRATION_ATR_MULT = 0.04`, `M1B_LOOKBACK_BARS = 24`, dan Dealing Range filter (`M1B_DR_SELL_MAX = 0.60`, `M1B_DR_BUY_MIN = 0.40`).
2. **Deteksi Anchor & Radar Fast Scanner (`src/analytics/market_scanner.py`)**:
   - Mengimplementasikan `find_m1b_zce_basing_anchor()`: memindai swing high/low internal 12-24 bar H1 dan mencocokkan secara ketat dengan hierarki ZCE (`C1`, `C2`, `SBR`, `F1`, `F2`, `RBS`).
   - Mengintegrasikan M1B ke dalam `get_radar_standbys()` dan `scan_fast_radar()`: memvalidasi wick penetration, wick ratio $\ge 30\%$, close reclaim, serta Macro Bias dan CSM Delta alignment.
3. **Visualisasi Cockpit Dashboard (`dashboard.py` & `dashboard_assets.py`)**:
   - Menambahkan kartu telemetri `M1B: TREND SWEEP` pada grid 5 kolom responsif di tab Radar Telemetry.
   - Mengintegrasikan garis harga putus-putus reticle horizontal warna ungu neon (`#c084fc`) berlabel `[M1B SWEEP ANCHOR]` di canvas chart SVG.
   - Memperbarui checklist Gate 5 menjadi `M1..M4 (inc. M1B) Radar Prerequisites`.
4. **Unit Test Suite & Verifikasi Sistem (`tests/test_m1b_sweep.py`)**:
   - Membuat pengujian unit test khusus untuk M1B yang menguji deteksi anchor dengan konfluensi ZCE, penolakan anchor tanpa ZCE, dan eksport reticle standby M1B (3/3 test PASS).
   - Pengujian keseluruhan `python -m unittest discover tests/` terverifikasi **157/157 PASS (100% OK)**.

---

## 0.6. Perubahan 7 September 2026 (Siang) — Isolasi Hermetis Unit Test Pure Quant (Zero Production State Pollution) & Pembersihan Telemetri BTCUSD

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Kebocoran Data Uji (*Test Pollution*) ke Database Produksi**:
   - Di `tests/test_pure_quant_execution.py`, pengujian alur `main.run_scanner_trading_cycle()` menggunakan candidate dummy `BTCUSD.c` (harga 95.000, SL 94.000).
   - Fungsi tersebut memanggil `shadow_tracker.register_candidate()`, `position_manager.record_trade_open_telemetry()`, dan `record_funnel_event()`. Karena modul-modul ini belum di-patch dalam test tersebut, setiap kali unit test dijalankan (`test discover`), dummy order `BTCUSD.c` tertulis langsung ke database state produksi: `data/quant_shadow_state.json`, `data/quant_shadow_trades.jsonl`, `data/trade_lifecycle_telemetry.json`, dan `data/quant_funnel_metrics.json`.
2. **False SL Hit saat Startup `main.py`**:
   - Saat `main.py` dijalankan di weekday, loop memanggil `shadow_tracker.update_shadow_orders(connector)`. Tracker mengevaluasi dummy limit order BTCUSD (95.000) terhadap harga live MT5 (~54.000). Karena harga pasar jauh di bawah harga limit dan SL (94.000), tracker seketika menandai trade sebagai `SL_HIT (-1.00R)` dan mencetak:
     `[SHADOW RADAR RESOLVED] BTCUSD.c (UNIVER) -> SL_HIT (-1.00R) | MFE: +0.00R | MAE: -15.38R`.
   - Hal ini mendistorsi statistik shadow tracker dengan 6 SL hit palsu (`cumulative_net_r: -6.0R`).
3. **Klarifikasi Status Weekday BTCUSD**:
   - Ditegaskan bahwa BTCUSD **100% TIDAK AKTIF pada weekday**. Di `config.py` (`get_scanner_symbols`), filter `not is_crypto(s)` secara ketat membatasi radar hanya pada 26 pair FX. BTCUSD hanya aktif pada akhir pekan jika `ENABLE_BTC_ROTATION=True`.

---

### ✨ Komponen & Solusi Utama:
1. **Isolasi Hermetis Unit Test (`tests/test_pure_quant_execution.py`)**:
   - Menambahkan mocking via `setUp` untuk:
     * `patch("main.shadow_tracker.register_candidate")`
     * `patch("main.position_manager.record_trade_open_telemetry")`
     * `patch("main.record_funnel_event")`
   - Memastikan eksekusi unit test tidak menghasilkan efek samping (*side-effects*) ke database atau file state produksi mana pun.
2. **Pembersihan Database State & Telemetri**:
   - `data/quant_shadow_state.json`: Menghapus 6 riwayat dummy `BTCUSD.c`, merestorasi statistik ke keadaan riil 26 pair FX (4 active, 2 resolved expired, 0 SL hit, 0.0R net).
   - `data/quant_shadow_trades.jsonl`: Membersihkan baris log dummy `BTCUSD.c`, mempertahankan hanya data trade riil (`NZDUSD` dan `AUDJPY`).
   - `data/trade_lifecycle_telemetry.json`: Menghapus tiket uji `999999` dan `888888`.
   - `data/quant_funnel_metrics.json`: Menghapus event dummy `BTCUSD.c` dan menyesuaikan counter funnel metrics.
3. **Konfigurasi Mode Forward Test di `.env`**:
   - `ENABLE_CSM_FLOW_FILTER=false`: Hard gate filter CSM dinonaktifkan di radar untuk mengeksekusi seluruh setup ke demo, sementara perhitungannya tetap aktif dan dicatat di CLI/telemetri.
   - `ENABLE_PENDING_THESIS_AUDIT=false`: Audit pembatalan pending order diubah ke Shadow Observer Mode tanpa membatalkan order MT5.
4. **Verifikasi Suite Lengkap**:
   - Seluruh test suite (`python -m unittest discover tests/`) dijalankan: **154/154 PASS (100% OK)** dan diverifikasi bahwa file database state di `data/` tetap bersih tanpa polusi data baru.

---

## 0.1. Perubahan 7 September 2026 (Pagi VI) — Mode Forward Test Agresif (Bypass Limitasi USD & Filter CSM, Shadow Observer Thesis Invalidation, dan Telemetri CSM Open/Close)

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Kebutuhan Sampel Data Forward Test Maksimal**:
   - Untuk menguji efektivitas strategi secara kuantitatif tanpa hambatan pembatasan basket (`MAX_CURRENCY_BASKET_EXPOSURE=99`) dan tanpa filter arah CSM (`ENABLE_CSM_FLOW_FILTER=false`), sistem diaktifkan dalam mode pengumpulan data agresif.
2. **Kebutuhan Counterfactual Telemetry (CSM Open & Close)**:
   - Sebelumnya, nilai Net Delta CSM hanya dicatat pada saat radar memindai setup (open). Nilai CSM saat posisi ditutup belum terekam, sehingga sulit menganalisis korelasi pergeseran CSM terhadap hasil P/L.
3. **Shadow Observer untuk Thesis Invalidation**:
   - Ketika pembatalan pending order dinonaktifkan (`ENABLE_PENDING_THESIS_AUDIT=false`), audit tidak boleh keluar diam-diam (*silent return*). Audit harus tetap mengevaluasi kondisi tesis dan mencatatnya sebagai *Observer Event* (`[THESIS SHADOW OBSERVER]`) tanpa membatalkan order di MT5. Dengan begitu, kita mendapatkan bukti apakah trade yang seharusnya dibatalkan tersebut akhirnya menang (false invalidation) atau kalah (saved loss).

---

### ✨ Komponen & Solusi Utama:
1. **Pencatatan Telemetri CSM Open/Close (`position_manager.py` & `main.py`)**:
   - Membuat file persistence `data/trade_lifecycle_telemetry.json` via helper `record_trade_open_telemetry()` dan `record_trade_close_telemetry()`.
   - Di `main.py`: Menangkap snapshot `csm_delta_open` saat order dipasang, dan menangkap `csm_delta_close` saat deal tertutup terdeteksi via `risk.sync_closed_positions()`, menghitung `csm_delta_shift`.
2. **Shadow Tracker Telemetry Integration (`shadow_tracker.py`)**:
   - Menyimpan `csm_delta_open` dan `csm_opposed_open` di `ShadowTrade.metadata`.
   - Mengambil `csm_delta_close` seketika saat shadow trade ter-resolve (`TP_HIT`, `SL_HIT`, `TIME_DECAY_EXIT`), menghitung `csm_delta_shift`, dan menulis ke `quant_shadow_trades.jsonl`.
3. **Observer Mode pada Invalidation Audit (`position_manager.py`)**:
   - Menghapus *silent early return* di `audit_pending_orders_thesis()`.
   - Ketika syarat pembatalan terpenuhi namun `ENABLE_PENDING_THESIS_AUDIT=False`: Mencetak alert `[THESIS SHADOW OBSERVER]` dan mencatat event ke telemetri tanpa membatalkan order MT5.
4. **Penyelarasan Unit Test Suite Lengkap**:
   - `tests/test_audit_pending_orders_thesis.py`: Mengisolasi `config.ENABLE_PENDING_THESIS_AUDIT` dan menambahkan test observer.
   - `tests/test_risk_engine_magic_filter.py`: Mengisolasi `MAX_CURRENCY_BASKET_EXPOSURE=3` dan menguji mode forward test `MAX=99`.
   - `tests/test_shadow_tracker.py`: Mengisolasi `ENABLE_SHADOW_PROXIMITY_CANCEL`.
   - Hasil pengujian: **154/154 Unit Tests PASS (100% OK)**.

---

## 0.1. Perubahan 7 September 2026 (Pagi V) — Pembukaan Sesi Asia 07:00 WIB Khusus Pair Pasifik & Asia (Tokyo Cash Open & Tokyo Fix Capture) & Penyesuaian Dead Zone 00:00–07:00 WIB

### 🎯 Latar Belakang & Validasi Empiris:
1. **Penyelidikan Distribusi Waktu 10 Tahun MetaQuotes H1 (2016–2026)**:
   - Audit membuktikan timestamp MetaQuotes MT5 merupakan Jam Server (GMT+3). Penerapan formula wajib Rule 3 `WIB = Jam Server + 4 Jam` mengonfirmasi bahwa puncak likuiditas dunia sesungguhnya berada di **19:00 – 21:00 WIB** (puncak 21:00 WIB dengan Mean 27.78 pips pada pair Barat).
   - Di pagi hari, Bursa Saham Tokyo resmi dibuka pukul 09:00 JST (**07:00 WIB**) dan penetapan kurs harian perbankan Jepang (*Tokyo Fixing / Nakane*) terjadi pada 09:55 JST (**07:55 WIB**).
   - Pair ber-driver Asia/Pasifik (`USDJPY`, `AUDJPY`, `NZDJPY`, `AUDUSD`, `NZDUSD`, dll) melonjak aktivitasnya dari 13.6 pips ke **16.68 pips/jam** pada rentang 07:00–08:00 WIB.
   - Sebelumnya, Dead Zone `DANGER_ZONES_WIB` memblokir semua pair hingga pukul 08:00 WIB, sehingga bot melewatkan momentum likuiditas institusional Tokyo Cash Open dan Tokyo Fix.
2. **Kedaulatan Sesi Asia vs Penguncian Pair Barat**:
   - Data empiris membuktikan bahwa pair Barat murni (`EURUSD`, `GBPUSD`, `USDCAD`, `EURGBP`, dll) sepanjang 07:00–14:00 WIB memiliki **Modus lilin H1 hanya 5.0 pips** (pasar mati/tergerus spread).
   - Oleh karena itu, pembukaan jam 07:00 WIB **wajib dikhususkan hanya untuk pair yang memiliki driver JPY, AUD, atau NZD** (`is_asian_session_pair`), sementara pair Barat tetap dikunci 100% hingga sesi Eropa (14:00 WIB).

---

### ✨ Komponen & Solusi Utama:
1. **Penyelarasan Konfigurasi (`config.py` & `.env`)**:
   - Menambahkan `ASIA_SESSION_START_HOUR_WIB=7` dan `DANGER_ZONES_WIB=00:00-07:00` di `.env` sebagai *Single Source of Truth*.
   - Di `config.py`:
     * `ASIA_SESSION_START_HOUR_WIB = _getenv_int("ASIA_SESSION_START_HOUR_WIB", 7)`
     * `ALLOWED_SESSIONS_WIB`: Sesi `"Tokyo / Asia Pagi"` dimajukan dimulai pukul `(7, 0)`.
     * `DANGER_ZONES_WIB`: Diperbarui menjadi `(0, 0)` s/d `(7, 0)` (`Overnight Rollover Dead Zone (00:00 - 07:00 WIB)`).
2. **Penyelarasan Scanner Engine (`src/analytics/market_scanner.py`)**:
   - `MarketScanner.is_symbol_allowed_for_session()`: Menggunakan batas dinamis `ASIA_SESSION_START_HOUR_WIB` (7) dan mengunci pair non-Asia pada rentang 07:00–14:00 WIB.
   - `scan_fast_radar()`: Filter dead zone diperbarui dari `0 <= h < 8` menjadi `0 <= h < asia_start` (7).
3. **Pembaruan Cockpit Surveillance Dashboard (`dashboard.py`)**:
   - Memperbarui visualisasi status sesi `_get_session_name()`: `DEAD_ZONE` (00:00–07:00 WIB) dan `ASIAN_ACTIVE / ASIAN_LOCKED` (07:00–14:00 WIB).
   - Menyelaraskan audit Gate 1 (Session & Spread Filter) dan card parameter `DEAD_ZONE_HOURS = 00:00 - 07:00 WIB`.
4. **Pengujian Kuantitatif & Verifikasi Sistem**:
   - Menambahkan unit test di `tests/test_market_scanner.py` (`test_session_aware_pair_filtering`) untuk memvalidasi:
     * Jam 07:00 WIB: Pair Asia (`USDJPY`, `AUDUSD`, `NZDUSD`, `GBPJPY`) $\rightarrow$ `PASS / True`.
     * Jam 07:00 WIB: Pair Barat (`EURUSD`, `GBPUSD`, `USDCAD`) $\rightarrow$ `LOCKED / False`.
     * Jam 06:00 WIB: Seluruh pair FX $\rightarrow$ `DEAD ZONE / False`.
   - Full test suite: **152/152 tests PASS (100%)**.

---

## 1. Perubahan 7 September 2026 (Pagi IV) — Isolasi Magic Number pada Risk Engine & Multi-Position Sizing (Pemisahan Trade Manual vs Bot)

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Pemicu False Currency Basket Block oleh Posisi Manual User**:
   - Di akun MT5 terdapat 2 posisi manual `EURUSD-ECN` (tiket `#663308920` dan `#663314002`, `magic = 0`).
   - Di `risk_engine.py:544` (`_check_max_positions()`), fungsi mengambil seluruh posisi akun via `mt5.positions_get()` tanpa menyaring `magic == config.MAGIC_NUMBER`.
   - Akibatnya, 2 trade manual `EURUSD` ditambah 1 trade bot `AUDUSD` dihitung bersamaan sebagai 3 posisi USD, memicu penolakan *Currency Basket Concentration Limit (3/3)* pada seluruh pair USD (`USDJPY` dan `NZDUSD`).
2. **Kalkulasi Sisa Kapasitas Split Ticket di `main.py:955`**:
   - `main.py` juga menghitung slot tersisa dari seluruh posisi akun tanpa menyaring magic number, sehingga trade manual memotong kuota split-order bot.

---

### ✨ Komponen & Solusi Utama:
1. **Isolasi Magic Number di `risk_engine.py`**:
   - Memisahkan `raw_positions`/`raw_orders` (seluruh akun) dari `positions`/`orders` milik bot (`magic == config.MAGIC_NUMBER`).
   - Aturan *Total Absolute Account Ceiling* (max 8 posisi total) tetap memantau seluruh akun (`raw_positions`) sebagai rem darurat margin.
   - Aturan *Risk-Weighted Slot Accounting* (max 6 posisi bot) dan *Currency Basket Concentration Limit* (max 3 posisi per mata uang) hanya menghitung posisi dan order milik bot.
   - Posisi USD bot kini dihitung akurat (1 posisi `AUDUSD`), sehingga slot USD bot tersisa 2 posisi lagi dan `USDJPY` diizinkan membuka posisi.
2. **Isolasi Magic Number di `main.py`**:
   - Menyelaraskan kalkulasi `total_active` dan `remaining_slots` untuk pembagian tiket 2-posisi agar hanya menghitung posisi milik bot.
3. **Penambahan Unit Test Suite (`tests/test_risk_engine_magic_filter.py`)**:
   - `test_manual_positions_do_not_block_currency_basket`: Memvalidasi bahwa 2 trade manual `EURUSD` + 1 trade bot `AUDUSD` tidak memblokir `USDJPY`.
   - `test_bot_positions_properly_enforce_currency_basket`: Memvalidasi bahwa 3 trade bot berunsur USD tetap memblokir order USD ke-4.
   - `test_total_absolute_ceiling_monitors_all_trades`: Memvalidasi bahwa plafon darurat 8 posisi akun tetap memblokir trade jika total akun mencapai 8.
   - Seluruh test suite sistem (152 tests): **100% PASS**.

---

## 1. Perubahan 7 September 2026 (Pagi III) — Sinkronisasi Macro Bias Alignment pada CSM Pending Order Invalidation & Eksplisitasi Config `.env`

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **False Thesis Invalidation pada Order Pending Macro-Aligned (`NZDCHF-ECN` #669657471)**:
   - Order pending BUY LIMIT NZDCHF disetujui dan ditempatkan oleh Stage 1 radar (M2 Pullback) karena didukung kuat oleh Macro Bias MSE (`bias_score = +0.95`, `action_tier = FULL_ALLOW`, `market_state = FLOOR_REJECTION`).
   - Di `market_scanner.py:2524-2527`, filter CSM berlawanan (`csm_delta <= -1.0`) dikecualikan jika arah trade selaras dengan bias makro (`is_aligned = True`, `bias_score >= 0.35`).
   - Namun di `position_manager.py:855`, engine pembatalan pending order mengecek `csm_delta <= -csm_opposed_thresh` (-1.03 <= -1.00) secara sepihak tanpa memeriksa `is_macro_aligned_buy`. Akibatnya, pending order yang sah diloloskan radar langsung dibatalkan dalam siklus 3 detik berikutnya dengan log `[THESIS FAILURE CANCEL] Pending Order #669657471 (NZDCHF-ECN) Dibatalkan: Systemic CSM Flow reversed strongly to Bearish (-1.03 <= -1.00)`.
2. **Klarifikasi Skala CSM & Parameter Konfigurasi**:
   - Skala desimal `csm_delta` berada pada rentang $\approx [-5.0, +5.0]$ (hasil normalisasi skor Boitoki dibagi 10). Ambang batas pembatalan pending order adalah `1.00` (setara 10 poin Boitoki).
   - Parameter `PENDING_CSM_OPPOSED_THRESHOLD` belum dideklarasikan eksplisit di `.env`.

---

### ✨ Komponen & Solusi Utama:
1. **Penyelarasan Macro Bias Alignment di `position_manager.py`**:
   - Mengekstrak `bias_score` dari `strat_dir.macro_bias_score` secara aman menggunakan helper `_safe_num()`.
   - Menambahkan kondisi pelindung `not is_macro_aligned_buy` (untuk BUY) dan `not is_macro_aligned_sell` (untuk SELL).
   - Pending order yang didukung arah makro struktural ($\text{bias} \ge +0.35$ untuk BUY atau $\le -0.35$ untuk SELL) tidak lagi dibatalkan oleh fluktuasi CSM moderat di sekitar $\pm 1.0$.
2. **Eksplisitasi Konfigurasi `.env`**:
   - Menambahkan parameter `PENDING_CSM_OPPOSED_THRESHOLD=1.0` ke `.env` sebagai Single Source of Truth.
3. **Penambahan Unit Test Suite (`tests/test_audit_pending_orders_thesis.py`)**:
   - Menambahkan `test_buy_limit_not_cancelled_when_macro_aligned_despite_opposed_csm` (memvalidasi kasus NZDCHF: BUY limit tetap aktif pada `csm_delta = -1.18` saat `bias_score = 0.95`).
   - Menambahkan `test_sell_limit_not_cancelled_when_macro_aligned_despite_opposed_csm` (memvalidasi SELL limit tetap aktif pada `csm_delta = +1.35` saat `bias_score = -0.80`).
   - Seluruh test suite sistem (149 tests): **100% PASS**.

---

## 1. Perubahan 7 September 2026 (Pagi II) — Integrasi Paper Trade (Quant Shadow) untuk Sinyal Tertolak Risk Gate & Dedicated HTML Performance Report via Dashboard

### 🎯 Latar Belakang & Identifikasi Kebutuhan:
1. **Penolakan Currency Basket Concentration Limit (`MAX_CURRENCY_BASKET_EXPOSURE`)**:
   - Risk Engine menerapkan aturan konsentrasi mata uang (`src/core/risk_engine.py:601-619`) dengan batas maksimal 3 posisi terbuka per mata uang (misal USD 3/3).
   - Ketika sinyal valid Stage 1 (seperti `NZDUSD-ECN`) muncul saat kuota 3 posisi USD sudah terpenuhi, bot menolak eksekusi MT5 dengan pesan `[RISK GATE] Trade untuk NZDUSD-ECN [H1] tidak diizinkan oleh Risk Engine ( [RISK] Konsentrasi mata uang USD di MT5 sudah mencapai batas (3/3 posisi).).`
   - Sebelumnya, penolakan di `main.py:668` langsung mengembalikan `False` tanpa mendaftarkan setup ke Virtual Shadow Order Book (`shadow_tracker`), sehingga telemetri peluang teknikal tersebut hilang dari riset kuantitatif.
2. **Kebutuhan Akses Laporan Quant Shadow HTML yang Praktis**:
   - Pengguna membutuhkan cara mudah untuk mengunduh/melihat visualisasi laporan kinerja sinyal quant shadow secara komprehensif melalui antarmuka web dashboard (HTML) tanpa harus membuka file json mentah.

---

### ✨ Komponen & Solusi Utama:
1. **Pendaftaran Otomatis Paper Trade saat Risk Gate Terpicu (`main.py`)**:
   - Ketika `risk.can_trade(sym)` menolak pengiriman order ke MT5 pada Stage 2 (`main.py:668`), setup tetap dihitung parameter strukturalnya (entry, SL, TP, R:R) lalu didaftarkan ke `shadow_tracker.register_candidate()` dengan disposisi `SKIPPED_RISK_BASKET` atau `SKIPPED_RISK_BLOCK`.
   - Setup akan dipantau pergerakan harganya secara virtual (fill, MFE, MAE, hingga TP/SL) secara non-invasif.
2. **Penyelarasan Konfigurasi (`config.py` & `.env`)**:
   - Menambahkan parameter `MAX_CURRENCY_BASKET_EXPOSURE = _getenv_int("MAX_CURRENCY_BASKET_EXPOSURE", 3)` di `config.py` dan `.env`.
3. **Modul Generator Laporan HTML Mandiri (`src/analytics/shadow_report.py`)**:
   - `render_shadow_report_html()`: Menghasilkan halaman web laporan lengkap terminal-grade (KPI Cards, Breakdown Mekanisme M1..M4, Status Disposisi MT5, Buku Order Aktif & Riwayat Telemetri Tuntas dengan filter/pencarian real-time).
   - `generate_and_save_shadow_report()`: Otomatis membuat file `docs/quant_shadow_report.html`.
4. **Integrasi Endpoint Dashboard & Web UI (`dashboard.py` & `dashboard_assets.py`)**:
   - Menambahkan rute `/shadow`, `/shadow.html`, dan `/report/shadow` pada HTTP handler `dashboard.py`.
   - Menambahkan tombol langsung `[ 📊 LAPORAN ]` pada header dashboard dan `[ 📊 Buka Laporan Lengkap HTML ↗ ]` pada tab drawer Virtual Shadow.
   - `dashboard.py` secara otomatis memperbarui file statis `docs/quant_shadow_report.html` saat dijalankan.
5. **Pengujian & Verifikasi**:
   - Menambahkan unit test `test_risk_block_disposition_and_get_all_resolved_trades` di `tests/test_shadow_tracker.py`.
   - Test suite: **100% PASS** (7/7 shadow tracker tests, 99/99 regression tests).

---

## 1. Perubahan 7 September 2026 (Pagi I) — Eliminasi Duplikasi `get_current_tick()` & Harmonisasi Simbol Broker Kripto Demo/Live (`BTCUSD` vs `BTCUSD.c`)

### 🎯 Latar Belakang & Identifikasi Kebutuhan:
1. **Penyebab Spam Error `[MT5 ERROR] Gagal mendapatkan tick untuk BTCUSD.c.`**:
   - Terdapat 2 deklarasi fungsi `get_current_tick(symbol)` di [`src/core/mt5_connector.py`](file:///c:/Vibe/tradingpartner/src/core/mt5_connector.py).
   - Fungsi baris 305–327 menimpa fungsi baris 254–278. Fungsi baris 305 langsung memanggil `mt5.symbol_info_tick(symbol)` tanpa me-resolve nama simbol via `get_valid_trade_symbol(symbol)`.
   - Pada akun Demo VTMarkets (`VTMarkets-Demo` #1157958), simbol BTC adalah `BTCUSD` (tanpa suffix `.c`).
   - File state `data/quant_shadow_state.json` menyimpan pending shadow trade dengan `"symbol": "BTCUSD.c"` dari sesi akhir pekan. Setiap 3 detik `shadow_tracker.update_shadow_orders()` meminta tick `BTCUSD.c`, yang selalu gagal (`None`) dan memicu print error spam di terminal serta mencegah pending order basi ter-resolve/expired.

---

### ✨ Komponen & Solusi Utama:
1. **Konsolidasi Kanonikal `get_current_tick()` (`src/core/mt5_connector.py`)**:
   - Menghapus fungsi duplikat baris 305–327.
   - Menyatukan fungsi kanonikal di baris 254 dengan memanggil `symbol = get_valid_trade_symbol(symbol)` pada baris pertama.
   - Mengembalikan dictionary lengkap: `ask`, `bid`, `last`, `volume`, `time`, `spread`, `spread_usd`, `point`, `digits`, `usd_per_point`.
   - Menghapus print error hardcoded pada level tick retriever dasar agar tidak membanjiri log saat symbol unavailable.
2. **Penyelarasan Helper Terkait di `src/core/mt5_connector.py`**:
   - `get_usd_per_point()`: Menambahkan `symbol = get_valid_trade_symbol(symbol)` sebelum query info broker.
   - `get_broker_utc_offset_seconds()`: Menambahkan `symbol = get_valid_trade_symbol(symbol)`.
   - `server_utc_offset_hours()`: Memanggil `get_valid_trade_symbol("BTCUSD.c")` agar secara otomatis mengenali `BTCUSD` pada akun Demo dan `BTCUSD.c` pada akun Live.
3. **Konfigurasi Lingkungan (`.env`)**:
   - Menambahkan `WEEKEND_SYMBOL=BTCUSD` di `.env` yang selaras dengan profil Demo VTMarkets.
4. **Pengujian & Verifikasi**:
   - Menambahkan unit test `test_get_current_tick_auto_resolves_symbol` dan `test_get_current_tick_returns_none_when_unavailable` di `tests/test_symbol_resolver.py`.
   - Pending shadow order lama `SHADOW_20260905_213641_BTCUSD_UNIVER` sukses di-resolve oleh `shadow_tracker`.
   - Seluruh test suite unit test: **100% PASS**.

---

## 1. Perubahan 5 September 2026 (Malam II) — Virtual Shadow Quant Radar: Perekaman Telemetri 100% Sinyal Stage 1 Tanpa Batasan Slot MT5 (Unconstrained Data Collector)

### 🎯 Latar Belakang & Identifikasi Kebutuhan:
1. **Keterbatasan Kapasitas Eksekusi MT5 vs Kebutuhan Riset Kuantitatif**:
   - Portofolio bot menerapkan pembatasan ketat `MAX_OPEN_POSITIONS` (misal 6 posisi) dan `MAX_PENDING_ORDERS` (4 order) demi mencegah *margin cluster* dan risiko korelasi mata uang fiat yang berlebih.
   - Akibatnya, ketika pasar menghasilkan banyak setup A+ valid (misal 15–20 setup dalam sehari), bot terpaksa mengabaikan sebagian besar setup tersebut (`PRE-DISPATCH BLOCKED: Max positions reached`).
   - Hal ini membatasi ukuran sampel ($N$) untuk evaluasi statistik performa murni Stage 1 Fast Radar (M1..M4), terutama dalam mode *Pure Quant No-LLM*.
2. **Kebutuhan Analisis Excursion Tanpa Risiko Modal (Zero-Risk Paper Tracking)**:
   - Diperlukan mekanisme pencatatan independen yang dapat memantau pergerakan harga riil bar-demi-bar (MFE/MAE) untuk setiap peluang kuantitatif yang lolos filter Stage 1 tanpa membebani margin akun demo MT5.

---

### ✨ Komponen & Solusi Utama:

1. **Modul Mandiri Virtual Shadow Tracker (`src/analytics/shadow_tracker.py`)**:
   - Mendefinisikan dataclass `ShadowTrade`: merekam parameter lengkap setup (`shadow_id`, `symbol`, `setup_type`, `direction`, `entry_type`, `entry_price`, `sl_price`, `tp_price`, `risk_reward`, `sl_points`, `tp_points`, `status`, `outcome`, `peak_mfe_r`, `max_mae_r`, `mt5_disposition`, `mt5_ticket`).
   - Class `QuantShadowTracker` (Singleton):
     * `register_candidate()`: Mendaftarkan setup kuantitatif baru yang lolos radar dengan proteksi deduplikasi (anti-spam 30 menit).
     * `update_shadow_orders(connector)`: Memperbarui status seluruh order aktif menggunakan data tick live MT5:
       - Mendeteksi penjemputan pending limit order (*limit fill*).
       - Mendeteksi pembatalan *Target Proximity Expiration* ($\ge 75\%$ menuju TP tanpa fill).
       - Mendeteksi *Timeout Expiration* (pending order $>120$ menit).
       - Menghitung akumulasi *Max Favorable Excursion* (MFE) dan *Max Adverse Excursion* (MAE) dalam satuan R.
       - Menyelesaikan trade saat menyentuh TP (`TP_HIT`, +R), SL (`SL_HIT`, -1.0R), atau stagnasi $>24$ jam (`TIME_DECAY_EXIT`).
     * `get_performance_summary()`: Menghasilkan ringkasan analitik real-time (Total Setups, Winrate %, Realized Net R, Expected Value per trade, dan breakdown per mekanisme M1..M4).
   - Penyimpanan Telemetri Terstruktur:
     * `data/quant_shadow_trades.jsonl`: Log append-only setiap trade yang tuntas (`RESOLVED`).
     * `data/quant_shadow_state.json`: State file order aktif/pending yang tahan terhadap restart bot.

2. **Integrasi Alur Eksekusi Utama (`main.py`)**:
   - Pada `run_scanner_trading_cycle()`:
     * Setiap setup yang lolos validasi SL/TP didaftarkan ke `shadow_tracker`.
     * Menandai disposisi eksekusi MT5: `EXECUTED_MT5` (dengan nomor tiket) jika slot tersedia, atau `SKIPPED_SLOT_FULL` / `SKIPPED_RISK_BLOCKED` jika diblokir oleh kapasitas MT5.
     * Jika mode LLM aktif dan konsensus memutuskan HOLD/VETO, setup tetap dicatat dengan disposisi `SKIPPED_LLM_VETO` untuk menganalisis akurasi keputusan AI secara retrospektif.
   - Pada loop 3 detik:
     * Memanggil `shadow_tracker.update_shadow_orders(connector)` secara otomatis.
     * Mencetak notifikasi ANSI rapi di terminal saat ada trade virtual yang selesai:
       `[SHADOW RADAR RESOLVED] GBPJPY (M3) -> TP_HIT (+1.67R) | MFE: +1.82R | MAE: -0.35R`.

3. **Integrasi Dashboard Surveillance Cockpit (`dashboard.py` & `dashboard_assets.py`)**:
   - Backend `dashboard.py`:
     * Menyuntikkan `shadow_radar` ke payload `/api/overview`.
     * Menambahkan dedicated endpoint `/api/shadow` untuk querying metrik telemetri.
   - Frontend `dashboard_assets.py`:
     * Header bar: Menampilkan pill live status `Virtual Shadow: N rec (act, pend) | WR % (+/-R)`.
     * Drawer tabs: Menambahkan tab baru `Virtual Shadow Quant Radar` berisi 4 summary cards, tabel breakdown performa M1..M4, dan tabel live order virtual aktif & recent resolved.

4. **Unit Test Suite Lengkap (`tests/test_shadow_tracker.py`)**:
   - 6 test cases memverifikasi registrasi market/pending, deduplikasi, transisi pending-to-active fill, target proximity expiration, pelacakan MFE/MAE, dan resolusi TP/SL.
   - Full regression test suite: **144/144 tests 100% PASS**.

---

## 1. Perubahan 5 September 2026 (Malam) — Penyelarasan Vertical Shading (Sessions & Regimes) Sesuai Realita Engine, Dynamic Mini Legend, dan Client Disconnect Guard

### 🎯 Latar Belakang & Identifikasi Kebutuhan:
1. **Desinkronisasi Persepsi Visual Operator vs Realita Engine**:
   - Sesi vertical shading sebelumnya di dashboard bersifat generik dan statis (hanya mengelompokkan jam jam tanpa konteks). Operator tidak bisa melihat apakah suatu candle atau jam tertentu diizinkan trade (`PERMITTED`) atau diblokir keras (`BLOCKED`) oleh risk gate engine.
   - Ketidakhadiran visualisasi **Macro Wave Consolidation Age Regimes** dari `wave_regime.py`: operator tidak mengetahui apakah suatu konsolidasi tergolong muda (`YOUNG_OSCILLATION` <24 jam), mulai matang (`MATURE_SQUEEZE` 24–72 jam), atau berada dalam kompresi institusional ekstrem (`SUPER_COMPRESSION` >72 jam / Squeeze $\ge 16$ bar).
2. **Ketiadaan Chart Legend**:
   - Pengguna tidak memiliki panduan visual (*legend*) di chart untuk mengidentifikasi arti spektrum warna sesi operasional maupun zona usia kompresi gelombang.
3. **Pencemaran Log Terminal oleh Socket Disconnect**:
   - Ketika operator me-refresh halaman dashboard sebelum payload HTTP selesai ditransmisikan, browser memutus koneksi TCP sehingga memicu log `Exception occurred during processing of request from ('127.0.0.1', ...)` (`ConnectionResetError: [WinError 10054]`).

---

### ✨ Komponen & Solusi Utama:

1. **Context-Aware Session Info Provider (`dashboard.py: _get_session_info`)**:
   - Memetakan waktu candle dan status simbol 1:1 dengan seluruh rule eksekusi bot:
     * `CRYPTO_247` (`PERMITTED`): Bitcoin/Crypto aktif non-stop 24/7 (bebas dari filter Dead Zone dan Asian Lock).
     * `FRIDAY_LOCK` (`BLOCKED`): Freeze order baru mulai Jumat $\ge$ 23:00 WIB s/d Minggu untuk seluruh pair Forex.
     * `DEAD_ZONE` (`BLOCKED`): 00:00–08:00 WIB untuk Forex (termasuk jendela kritis rollover 03:50–04:15 WIB).
     * `ASIAN_ACTIVE` (`PERMITTED`): 08:00–14:00 WIB untuk pair bermata uang Tokyo Driver (`JPY`, `AUD`, `NZD`).
     * `ASIAN_LOCKED` (`BLOCKED`): 08:00–14:00 WIB untuk non-Asian pairs (`EURUSD`, `GBPUSD`, dll).
     * `LONDON_EXPANSION` (`PERMITTED`): 14:00–19:00 WIB (High Volume London open).
     * `NY_OVERLAP` (`PERMITTED`): 19:00–23:00 WIB (Peak Liquidity).
     * `LATE_NY` (`PERMITTED`): 23:00–02:00 WIB (Risk cap maksimal 2 posisi).
   - Menyediakan fallback cerdas jika query sesi tidak menyertakan simbol (mengembalikan nama sesi generik).

2. **Kalkulasi Vektorisasi Macro Wave Regime Series (`src/indicators/wave_regime.py`)**:
   - Dibuat fungsi ter-vektorisasi cepat `classify_wave_regimes_series(highs, lows, closes, timeframe_hours=1.0, dealing_range_window=100)`.
   - Menggunakan rolling window pandas dan numpy convolve untuk mendeteksi usia Dealing Range (jam) dan John Carter Squeeze Momentum (`sqz_on`, `sqz_bars`) dalam waktu sub-milidetik (~4 ms per 150 bar), bebas iterasi lambat.
   - Menghasilkan klasifikasi: `YOUNG_OSCILLATION` (<24h), `MATURE_SQUEEZE` (24–72h), `SUPER_COMPRESSION` (>72h atau Squeeze $\ge 16$ bar).

3. **Rendering Dual-Stripe & Dynamic Mini Legend (`dashboard_assets.py`)**:
   - **Visual Shading**:
     * Shading sesi dilengkapi dengan *top 3px stripe* berwarna tegas (Emerald Green untuk `PERMITTED`, Coral Red / Amber untuk `BLOCKED`).
     * Shading wave regime dilengkapi dengan *bottom 3px accent stripe* (Purple untuk `SUPER_COMPRESSION`, Violet untuk `MATURE_SQUEEZE`).
   - **Dynamic Mini Legend Overlay (`#chart-mini-legend`)**:
     * Muncul otomatis di pojok kanan atas grafik candlestick.
     * Beradaptasi secara responsif terhadap filter tombol toolbar aktif (`Sessions`, `Regimes`, `Both`, `Off`) dan konteks simbol aktif (menampilkan legend Crypto 24/7 vs Forex Driver).
   - **Live HUD Display**: Menampilkan status Macro Wave Regime dan durasi squeeze secara real-time pada header simbol.

4. **Silent Exception Guard pada HTTP Server (`dashboard.py: CockpitHTTPHandler`)**:
   - Membungkus `do_GET` dengan penanganan khusus untuk `(ConnectionResetError, ConnectionAbortedError, BrokenPipeError)`.
   - Mengeliminasi log traceback sampah di terminal ketika browser melakukan abort/refresh koneksi.

5. **Unit Test Suite Lengkap (`tests/test_dashboard_shading.py`)**:
   - 6 test cases memverifikasi: Crypto 24/7, Forex Dead Zone, Asian Lock vs Active, Friday Lock, vektorisasi Wave Regime series, dan integritas payload API `/api/symbol/<sym>`.
   - Full regression test suite: **138/138 tests 100% PASS**.

---

## 1. Perubahan 5 September 2026 (Sore) — Integrasi BTCUSD pada Dashboard Cockpit, 7-Gate X-Ray Surveillance, dan Normalisasi Simbol Akun Demo

### 🎯 Latar Belakang & Identifikasi Kebutuhan:
1. **Visibilitas X-Ray Cockpit untuk Bitcoin (BTCUSD)**:
   - Pengguna membutuhkan pemantauan langsung terhadap aset Bitcoin di dashboard Cockpit (`dashboard.py`), termasuk live chart, ZCE macro levels, telemetry radar M1..M4, dan evaluasi 7-Gate Decision Matrix secara transparan.
2. **Desinkronisasi Simbol Akun Demo vs Akun Live**:
   - Di akun Demo broker VTMarkets:
     * Crypto ticker adalah `BTCUSD` (tanpa akhiran `.c` dan tanpa `ECN`).
     * Forex ticker adalah `XXXYYY-ECN` (tanpa akhiran `c`, contoh `EURUSD-ECN`).
   - Kode resolver lama `mt5_connector.py:get_valid_trade_symbol()` tidak memangkas suffix `.c` atau `-ECNc` sebelum menguji kandidat `-ECN`, sehingga gagal mengenali simbol broker demo yang valid saat input berasal dari live environment (`BTCUSD.c` / `EURUSD-ECNc`).

---

### ✨ Komponen & Solusi Utama:

1. **Auto-Correct & Robust Symbol Normalizer (`src/core/mt5_connector.py`)**:
   - `get_valid_trade_symbol()` kini memotong suffix (`-ECNC`, `-ECN`, `.ECN`, `C.ECN`, `.C`) kembali ke akar ticker 6-karakter (`base`) sebelum melakukan pencarian variasi simbol broker.
   - Menguji kandidat secara berurutan: untuk crypto (`BTCUSD`, `BTCUSD.c`, `BTCUSD-ECN`, dll), untuk FX (`base + "-ECN"`, `base + "-ECNc"`, `base + ".c"`, `base`).
   - Menjamin interoperabilitas dwiarah 100% transparan antara akun Demo (`BTCUSD`, `EURUSD-ECN`) dan akun Live (`BTCUSD.c`, `EURUSD-ECNc`).
2. **Integrasi BTCUSD Permanen pada Dashboard Watchlist (`dashboard.py`)**:
   - Inisialisasi scanner internal `MarketScanner` di dashboard kini selalu menyertakan `BTCUSD` bersama 26 pair FX.
   - Cache overview (`_build_overview_cache`) menjamin `BTCUSD` selalu terdaftar dan dapat diklik kapan pun oleh operator.
   - Penanganan nilai `digits` (2), `point` (1.0), dan `pip_div` (1) khusus crypto agar kalkulasi spread dan visualisasi level grafik tidak error.
3. **Kalibrasi 7-Gate X-Ray Surveillance Khusus Crypto (`dashboard.py`)**:
   - **Gate 1 (Session & Spread)**: BTCUSD dikecualikan dari dead zone 00:00–08:00 WIB dan limitasi sesi Asia Tokyo. Menggunakan plafon spread khusus crypto (`MAX_SPREAD_POINTS_BTC` = 2400 pts).
   - **Gate 2 (Systemic Basket Shock)**: BTCUSD ditandai bebas/independen dari matriks shock mata uang fiat.
   - **Gate 4 (Boitoki CSM Flow)**: Ditandai netral/independen dari matriks arus fiat 7 USD Majors.
   - **Gate 6 (Execution Mode)**: Menampilkan status *Pure Quant Direct Execution (No-LLM, 0 Token API)* saat `ENABLE_LLM_JURY=False`.
   - **Gate 7 (Risk Calibration)**: Menguji lantai SL 50,000 pts ($500) dan plafon 45,000 pts ($450) dengan sizing risiko crypto (`0.5%` equity).
4. **Penyelarasan Konfigurasi `.env` & `config.py`**:
   - `.env`: `WEEKEND_SYMBOL=BTCUSD`, `WEEKDAY_SYMBOL=GBPUSD-ECN`, `SCANNER_SYMBOLS` seluruh 26 pair FX format `-ECN`.
   - `config.py`: Penyesuaian `default_sl_points_for`, `default_tp_points_for`, dan `get_pre_rollover_slippage_threshold` dengan `.replace("-ECN", "")`.
5. **Unit Test Suite Lengkap (`tests/test_symbol_resolver.py` & `tests/test_dashboard_btc_xray.py`)**:
   - `test_symbol_resolver.py`: 2/2 tests PASS (memverifikasi auto-correct demo dan live).
   - `test_dashboard_btc_xray.py`: 2/2 tests PASS (memverifikasi overview cache dan 7-Gate X-Ray BTC).
   - Full regression discovery: **132/132 tests 100% PASS**.

---

## 0. Perubahan 5 September 2026 (Siang II) — Branch `quant-trade-noAI`: Mode Pure Quant Weekend BTC Tanpa LLM dan Institutional Demo Safety Lock

### 🎯 Latar Belakang & Identifikasi Kebutuhan:
1. **Trading Weekend Khusus Bitcoin Tanpa Beban Token AI**:
   - Pengguna membutuhkan mode eksekusi murni kuantitatif (*Pure Quant Execution*) khusus untuk aset `BTCUSD.c` pada akhir pekan (Sabtu–Minggu) tanpa memanggil konsensus 3-LLM Jury (0 token API, sub-detik).
   - Seluruh sinyal, entri pending limit, SL struktural, TP quant anchor, dan sizing risiko dieksekusi langsung dari modul Stage 1 Fast Radar.
2. **Isolasi Akun Demo & Perlindungan Akun Riil (Institutional Demo Safety Lock)**:
   - Menghindari kecelakaan di mana bot berjalan pada akun Real/Live padahal dimaksudkan untuk akun Demo.
   - Penambahan proteksi hard lock di `mt5_connector.py` yang memverifikasi `account_info().trade_mode == ACCOUNT_TRADE_MODE_DEMO`. Jika akun terdeteksi `REAL`, inisialisasi langsung dibatalkan keras.

---

### ✨ Komponen & Solusi Utama:

1. **Branch Baru `quant-trade-noAI` (`git checkout -b quant-trade-noAI`)**:
   - Dibuat dari basis commit terverifikasi pada `quant-trade`.
2. **Parameter Konfigurasi `ENABLE_LLM_JURY` (`config.py` & `.env`)**:
   - Memperkenalkan `ENABLE_LLM_JURY = _getenv_bool("ENABLE_LLM_JURY", True)`.
   - Di `.env`, diset `ENABLE_LLM_JURY=false` dan `MT5_ACCOUNT_MODE=demo`.
3. **Pure Quant Direct Execution Engine (`main.py`)**:
   - Jika `ENABLE_LLM_JURY=False`, `run_scanner_trading_cycle` melewati pemanggilan `llm.get_multi_llm_decisions_for_candidate` secara total.
   - Sinyal, harga pemicu, SL, TP, dan lot sizing dihitung langsung dari `CandidateSetup` kuantitatif serta tunduk pada aturan `_apply_sltp_rules` (plafon/lantai BTC 30,000–45,000 pts) dan `risk_engine`.
   - Banner CLI terminal menampilkan `PURE QUANT RADAR (Fast Radar 60s | Direct Quant Execution / No-LLM)`.
4. **Institutional Demo vs Live Safety Guard (`mt5_connector.py`)**:
   - Validasi `trade_mode` terminal MT5: jika konfigurasi meminta `demo` tetapi broker mengembalikan `REAL`, bot langsung memutus koneksi MT5 (`shutdown()`) dan membatalkan start.
5. **Unit Test Suite Baru (`tests/test_demo_safety_guard.py` & `tests/test_pure_quant_execution.py`)**:
   - Validasi pemblokiran akun real saat mode demo aktif (2/2 tests PASS).
   - Validasi eksekusi langsung pending limit dan market order tanpa pemanggilan LLM (2/2 tests PASS).
   - Full regression discovery 128 tests: 100% PASS.

---

## 0. Perubahan 5 September 2026 (Siang I) — Harmonisasi Ambang Batas Invalidation Pending Order (CSM Opposed Threshold), Logging Persistence, dan Friday Pre-Weekend Liquidity Shield

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Desinkronisasi Ambang Batas CSM Scanner vs Position Manager (Auto-Cancel 4–10 Detik)**:
   - Pada sesi perdagangan 4 September 2026, terjadi fenomena di mana pending limit order (EURNZD, GBPCAD, GBPAUD, CHFJPY) yang telah disetujui bulat 3/3 oleh AI Jury dibatalkan oleh sistem hanya dalam waktu 4 hingga 10 detik pasca-approval.
   - Investigasi mendalam membuktikan `market_scanner.py:2509` meloloskan setup selama $|\text{csm\_delta}| < 1.0$, namun `position_manager.py:852, 865` langsung membatalkan pending order jika $\text{csm\_delta} < -0.35$ (BUY) atau $> +0.35$ (SELL).
   - Engine salah mengira nilai delta statis yang sudah ada sejak awal sebagai "pembalikan tajam" (*reversed strongly*), sehingga membatalkan order secara prematur.
   - Forward trajectory audit membuktikan 12 dari 17 pending order yang terjemput (70.6%) sebenarnya profitabel dengan potensi net profit $+\$415.78$ yang terbuang sia-sia.
2. **Friday Late-Session / Pre-Weekend Thin Liquidity Evaporation**:
   - Seluruh slippage Stop Loss parah (14.8 – 17.7 pip) terjadi pada pukul 02:30 WIB (22:30 Server Jumat) akibat menyusutnya likuiditas antar-bank menjelang penutupan mingguan (flash drop NZDUSD dan AUDCAD).
   - Selama rilis berita NFP (19:30 WIB), filter AI bekerja 100% sempurna memblokir trade, membuktikan bahwa kerugian bukan berasal dari berita NFP melainkan operasi pada jam pasar tipis akhir pekan.
3. **Visibilitas Log Terminal yang Tertimpa**:
   - Format `print(f"\r\x1b[2K[THESIS FAILURE CANCEL]...")` di `position_manager.py` tertimpa oleh dynamic status clock line sehingga pembatalan order tidak terbaca oleh operator.

---

### ✨ Komponen & Solusi Utama:

1. **Harmonisasi Ambang Batas CSM Pending Invalidation (`position_manager.py`, `config.py`, `.env`)**:
   - Memperkenalkan parameter `PENDING_CSM_OPPOSED_THRESHOLD = 1.0`, menyelaraskan ambang batas pembatalan pending order dengan filter arah radar di `market_scanner.py` ($1.0$).
   - Order pending BUY hanya dibatalkan jika `csm_delta <= -1.0`, dan order pending SELL hanya jika `csm_delta >= +1.0`.
   - Mengganti print carriage-return dengan newline dan mencatat langsung ke `logger.info()` agar tercatat permanen di `trading_bot.log`.
2. **Friday Pre-Weekend Liquidity Shield (`risk_engine.py`, `config.py`, `.env`)**:
   - Mengimplementasikan `_check_friday_pre_weekend_lock(symbol, now_wib)`.
   - Mulai Jumat malam pukul 23:00 WIB (`FRIDAY_CUTOFF_HOUR_WIB = 23`), bot secara otomatis membekukan pembukaan posisi baru pada instrumen FX & Logam (`can_trade() -> False`), menghindari jendela bahaya likuiditas tipis 01:00–04:00 WIB.
   - Posisi terbuka yang sudah berjalan tetap dikelola penuh oleh trailing, BEP, dan partial close.
   - Aset crypto (BTCUSD) tetap dapat beroperasi secara independen jika `ENABLE_BTC_ROTATION = True`.
3. **Unit Test Suite Lengkap (`tests/test_audit_pending_orders_thesis.py` & `tests/test_friday_pre_weekend_lock.py`)**:
   - Pengujian memverifikasi order dengan CSM moderat (-0.69 / +0.45) tetap dipertahankan, sementara CSM ekstrem (-1.15 / +1.25) dibatalkan secara presisi.
   - Pengujian memvalidasi aktivasi penguncian hari Jumat $\ge 23:00$ WIB dan isolasi perlakuan crypto. 100% PASS.
4. **Integrasi 24/7 Weekend Bitcoin Scanner & Risk Engine Bypass (`market_scanner.py`, `risk_engine.py`, `config.py`, `.env`)**:
   - **Bypass Weekend & Dead Zone di Radar**: `scan_fast_radar()` memeriksa keberadaan instrumen crypto. Pasar FX tetap diblokir pada akhir pekan (`dow in (5, 6)`) dan dead zone subuh (`00:00 - 08:00 WIB`), namun instrumen crypto (`BTCUSD.c`) diizinkan beroperasi 24/7 tanpa henti.
   - **Bypass Jam Sesi & Weekend di Risk Engine**: `_check_weekend_entry(symbol)` dan `_check_danger_zones(symbol)` membebaskan `BTCUSD.c` dari larangan entri baru akhir pekan saat `ENABLE_BTC_ROTATION = True`. `WEEKEND_TRADING_ENABLED=true` diaktifkan di `.env`.
   - **Penyelarasan Sesi Asia**: `is_asian_session_pair()` dan `is_symbol_allowed_for_session()` membebaskan crypto dari pembatasan jam sesi bursa Pasifik/Eropa.
   - **Mekanisme Aktif BTC**: Mekanisme M1 (Universal Liquidity Sweep & SFP), M2 (Trend-Aligned Pullback), dan M3 (Multi-Touch Breakout Retest) aktif penuh menganalisis chart H1 BTCUSD dengan batas kapasitas `MAX_OPEN_POSITIONS_BTC = 2`, sementara M4 (Systemic Currency Flow) tetap non-aktif karena ketiadaan komponen fiat CSM.
   - **Hermetic Unit Test**: `test_m4_grade_3_macro_gate_demands_basing` dipersenjatai dengan mock waktu agar kalender pengujian terisolasi sempurna, dan penambahan `test_btc_weekend_scanner_and_risk_entry_allowed` membuktikan radar dan risk engine meloloskan BTC di akhir pekan.

---

## 0. Perubahan 4 September 2026 (Malam VI) — Penyelarasan ZCE & MSE Chamber Migration, Eliminasi Inversion Bug, dan Unifikasi 26 Pair FX ke Timeframe H1

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Dynamic State Mutation during Penetration (Inversion Bug Kasus EURJPY & USDJPY Live)**:
   - Pada pukul 16:44:48 WIB, harga EURJPY dan USDJPY menusuk tipis ke atas Asian High / Plafon $C_1$ (+1.4 pips).
   - Akibat fungsi `_elect_walls()` di ZCE tidak memiliki syarat *Chamber Clearance*, penusukan tipis tersebut menyebabkan level $C_1$ (181.831) seketika melompat menjadi `imm_floor_f1` (Lantai F1).
   - Di `market_scanner.py`, evaluasi Dealing Range berbasis 100-bar macro menempatkan posisi harga di zona diskon makro (0.26). Akibatnya, sinyal Bearish Sweep (SELL) tertahan oleh filter `dr_pos_val >= 0.55`, sedangkan Bullish Sweep (BUY) lolos karena `dr_pos_val <= 0.45` dan mengambil referensi `ref_bot = imm_floor_f1 = 181.831`!
   - Hasilnya, sapuan likuiditas di atas level tertinggi (High) memicu BUY alih-alih SELL, bertolak belakang dengan analisa retikel dashboard `[M1] SELL @ 181.831`.
2. **Fragmentasi Timeframe JPY Crosses (M30 vs H1)**:
   - Penggunaan timeframe M30 pada JPY Crosses menghasilkan noise micro-structure, SL terlalu tipis, dan ketidaksinkronan dengan arsitektur 26 pair FX lainnya yang beroperasi murni pada H1.

---

### ✨ Komponen & Solusi Utama:

1. **ZCE Chamber Clearance & Probe Zone Lock (`zone_confluence_engine.py`)**:
   - Menerapkan ambang clearance $\ge 0.30 \times \text{ATR H1}$ (`ZCE_CHAMBER_CLEARANCE_ATR_MULT = 0.30`).
   - Ketika harga berada di dalam zona penusukan ($[C_1 - 0.10 \times \text{ATR}, C_1 + 0.30 \times \text{ATR}]$), level $C_1$ tetap dikunci mati sebagai Plafon dan dilarang berpindah ke `floor_cands`.
   - Level Plafon hanya sah bermigrasi menjadi Lantai $F_1$ (RBS Floor) jika harga telah menembus bersih $\ge 0.30 \times \text{ATR H1}$ di atas band atas zona.
   - Berlaku simetris untuk Lantai $F_1$: dilarang melompat menjadi Plafon saat ditusuk tipis ke bawah.
2. **Hukum Invariansi Peran M1 & Decoupled Intraday DR (`market_scanner.py`)**:
   - Menghapus syarat cacat `0 < (v - mid)` pada `valid_tops` yang mendiskualifikasi level saat ditembus, digantikan dengan batas toleransi absolut $\text{abs}(\text{mid} - v) \le 1.0 \times \text{ATR}$.
   - **Strict Directional Category Invariance**:
     * `ref_top` (SELL) dilarang keras mengambil level lantai (`invalid_ceil_levels`).
     * `ref_bot` (BUY) dilarang keras mengambil level plafon (`invalid_floor_levels`).
   - **Intraday Session Dealing Range**: Evaluasi M1 menggunakan rentang sesi Asia (`asian_h`, `asian_l`), sehingga tren turun multi-hari tidak lagi memblokir Bearish Sweep di puncak intraday.
3. **Unifikasi 100% 26 Pair FX ke Timeframe H1 (`config.py` & `.env`)**:
   - `get_timeframe_str(symbol)` mengembalikan `H1` untuk seluruh simbol FX termasuk JPY crosses.
   - `LLM_JPY_FLOOR_ATR_MULT = 0.50` dan `SL_FLOOR_JPY_PTS = 250` diselaraskan ke skala H1.
   - Perbarui inline keyboard menu Telegram di `telegram_bot.py` menjadi `USDJPY H1`, `GBPJPY H1`, `EURJPY H1`, `CADJPY H1`.
4. **Unit Test Suite Lengkap (`tests/test_zce_chamber_clearance.py`)**:
   - 5 pengujian otomatis memverifikasi retensi probe zone, migrasi kamar bersih (breakout/breakdown), dan konsistensi parameter konfigurasi H1. 100% PASS.
5. **Universal Liquidity Sweep (M1) G2/G3 Wall Enforcement & Radar Loop Ladder Fix (`market_scanner.py`)**:
   - Menghapus bypass `is_ranging_market` pada filter grade dinding M1; M1 Universal Liquidity Sweep (BUY dan SELL) kini secara mutlak mewajibkan dinding ZCE berperingkat minimal `GRADE_2_INTERMEDIATE` atau `GRADE_3_MACRO`.
   - Merestrukturisasi seluruh gate evaluasi M1 menjadi tangga `if-elif` terpadu, mengeliminasi `continue` prematur yang sebelumnya menggugurkan loop simbol utama dan mencegah evaluasi mekanisme M2, M3, dan M4.
6. **M4 Supreme Precedence & Grade 3 Anti-Liquidity Trap Basing Gate (`market_scanner.py`)**:
   - Pada `_is_direction_allowed()`, M4 Systemic Flow diberikan hak preseden tertinggi (`ALIGNED_M4_SYSTEMIC_EXPANSION [M4_CATALYST]`), mengesampingkan bias makro statis dan perangkap arah.
   - Pada loop M4, penembusan dinding ZCE Grade 3 ($C_1/F_1$) diwajibkan membentuk High-Tight Basing H1 (`/\/\/\/`, compression $\le 0.35\times\text{ATR}$, `pend["is_basing"] == True`). Jika belum terbentuk konsolidasi, radar menahan emisi tiket dengan status `WATCH_BASING_FORMATION`.
   - Inisialisasi `_m4_universe` saat startup scanner (`__init__`) dan akses defensif atribut `ema20`, `dealing_range_high`, dan `dealing_range_low`.

---

## 0. Perubahan 4 September 2026 (Malam V) — Penyelarasan 2D Confluence Action Tier dengan Anti-Frankenstein Guard & Capping SL/TP

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Pelebaran Target TP Tidak Proporsional pada Setup Reduced Scalp (Kasus GBPCHF Live)**:
   - Pada posisi live GBPCHF (Ticket #1261997759: SELL 0.10 lot, SL 212 pts, TP 400 pts), engine 2D Confluence mengevaluasi tier `REDUCED_SCALP` sehingga lot dipotong 50% ($0.21 \rightarrow 0.10$ lot).
   - DeepSeek CRO di Pass 2 mengusulkan target scalp di F3 (1.09183 = 221 pts, R:R 1.00:1).
   - Namun Anti-Frankenstein Guard sebelumnya memiliki ambang batas kaku `if llm_rr < 1.25`, memperlakukan target 1.00:1 sebagai sub-par dan otomatis memperlebar TP ke Quant Target Station F1 (1.09012 = 392 pts, ~400 pts).
   - Selain itu, `_apply_sltp_rules` menerima `candidate.action_tier` (`FULL_ALLOW`) alih-alih `confluence["tier"]` (`REDUCED_SCALP`), sehingga aturan capping $1.25\times$ R:R tidak aktif.
2. **Karakteristik H1 Intraday Trading**:
   - Untuk pair GBPCHF dengan ATR H1 105 pts dan D1 ADR 531 pts, jarak TP 400 pts (3.8x ATR H1 / 75% ADR) terlalu jauh untuk setup scalp intraday, sementara order AUDCAD (BUY_LIMIT 0.66 lot, SL 120 pts, TP 207 pts, R:R 1.63x net setelah komisi & spread) sudah proporsional (2.3x ATR H1 / 49% ADR).

---

### ✨ Komponen & Solusi Utama:
1. **Penyelarasan Effective Action Tier di Konsensus (`consensus.py`)**:
   - Menghitung `eff_action_tier = confluence.get("tier") or getattr(candidate, 'action_tier', None)`.
   - Menyesuaikan Anti-Frankenstein Guard:
     * Jika `is_reduced_scalp`, `target_min_rr` diturunkan menjadi 1.00:1 (menghormati proposal scalp CRO).
     * Jika TP quant melebihi 1.25x R:R, TP dibatasi pada batas aman 1.25x risk (`max_scalp_dist = 1.25 * curr_cand_risk`).
   - Meneruskan `eff_action_tier` ke fungsi `_apply_sltp_rules(..., action_tier=eff_action_tier, ...)` sehingga aturan pembatasan `max_rr = 1.25` langsung aktif saat 2D Confluence memicu `REDUCED_SCALP`.
2. **Penguatan Ekstraksi Defensif Atribut Cand_TP (`consensus.py`)**:
   - Membungkus parsing `suggested_tp_pts` dengan `try/except` integer casting untuk mencegah `TypeError` saat berhadapan dengan mock/non-int objects pada pengujian.
3. **Unit Test Suite Lengkap (`tests/test_cro_package_arbitration.py`)**:
   - Menambahkan pengujian `test_anti_frankenstein_guard_reduced_scalp_capped` untuk memverifikasi bahwa setup reduced scalp tetap terikat pada rentang R:R $[1.00\times, 1.25\times + \text{friction}]$.
   - 100% full unit test suite PASS tanpa regresi.

---

## 0. Perubahan 4 September 2026 (Malam IV) — Netralisasi Direktif Verdict (APPROVE vs REVISE vs REJECT) & Pengecualian Limit Order Berita Besar

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Disonansi 'REVISE' vs Confidence Level pada Evaluasi EURCHF**:
   - Pada evaluasi live EURCHF, Gemini menyematkan `verdict: "REVISE"`, `signal: "BUY"`, tetapi memberikan `confidence: 55%` dan `risk_flag: "HIGH_IMPACT_NEWS"`.
   - Prompt sebelumnya secara keliru memetakan `REVISE` sebagai tingkat keyakinan kedua yang lebih rendah (*"If 60-69% conviction -> REVISE"*), sehingga saat model ragu karena event berita dalam 30 menit, ia memilih `REVISE` alih-alih `REJECT`.
   - Hal ini menimbulkan anomali di layar: Gemini tertera `[REVISE]` dan vote `BUY`, tetapi trade dibatalkan oleh `CONFIDENCE FLOOR GATE` (55% < 60%) dan dikunci 45 menit (`[HARD VETO LOCK]`) karena berita.
2. **Klarifikasi Esensi Verdict**:
   - `REVISE` bukanlah tingkat keyakinan rendah. `REVISE` adalah tindakan struktural di mana model **setuju dengan arah tren (BUY/SELL)** tetapi ingin **memodifikasi entry type (misal menjadi pending limit) atau menyesuaikan SL/TP**. Model dengan keyakinan 80%–90% sepenuhnya sah memilih `REVISE`.
   - `APPROVE` berarti model menyetujui arah dan menerima koordinat awal tanpa modifikasi.
   - `REJECT` adalah satu-satunya vonis sah ketika keyakinan model berada di bawah batas minimum 60% ($< 0.60$) atau jika terdapat risiko struktural fatal.
3. **Penyelarasan Kebijakan Berita Besar (`HIGH_IMPACT_NEWS`)**:
   - Menempatkan order pasar instan (`MARKET`) tepat sebelum rilis berita berisiko tinggi karena pelebaran spread dan slippage eksekusi.
   - Namun, menempatkan pending limit order (`REVISE`) jauh di stasiun makro yang kokoh (F1/F2 floor atau C1/C2 ceiling) untuk menyerap sumbu (*wick absorption*) berita adalah strategi yang sah dan tidak seharusnya memicu penguncian fatal 45 menit jika keyakinan model $\ge 60\%$.

---

### ✨ Komponen & Solusi Utama:

1. **Netralisasi Panduan Verdict pada Prompt 3 Model (`llm_client.py`)**:
   - Menghapus aturan distorsi *"60-69% -> REVISE"* dari seluruh prompt (OpenAI, Gemini, DeepSeek).
   - Menetapkan direktif netral:
     * **`APPROVE`**: Setuju dengan arah sinyal dan menerima koordinat awal apa adanya.
     * **`REVISE`**: Setuju dengan arah sinyal (BUY/SELL), tetapi memodifikasi entry menjadi pending limit order di F1/C1/OB atau menyesuaikan SL/TP. Keyakinan tinggi (70%, 80%, 90%) sepenuhnya valid.
     * **`REJECT`**: Wajib dipilih jika keyakinan $< 0.60$ ATAU terdapat risiko struktural fatal $\rightarrow$ sinyal wajib `HOLD` dan confidence $\le 0.40$.
2. **Pengecualian Pending Limit Order dari Hard Lockout Berita Besar (`main.py` & `consensus.py`)**:
   - Pada `consensus.py`: `HIGH_IMPACT_NEWS` hanya memveto order instan (`MARKET`). Pending limit order (`REVISE`) di stasiun makro dengan confidence $\ge 60\%$ diizinkan lolos.
   - Pada `main.py`: Jika model menyematkan `HIGH_IMPACT_NEWS` namun order berupa pending limit (`entry_type != "market"`) dengan confidence $\ge 60\%$, sistem tidak mengaktifkan 45-menit hard lockout, melainkan memberlakukan `SOFT_TIMING_HOLD` (3 menit jeda bernapas).
3. **Penyelarasan Dokumentasi Prompt (`docs/prompt/`)**:
   - Mengekspor ulang `openai_prompt.md` dan `gemini_prompt.md` secara utuh.
4. **Verifikasi Test Suite**:
   - Seluruh unit test suite lulus 100% PASS tanpa regresi.

---

## 0. Perubahan 4 September 2026 (Malam III) — Physical SBR/RBS Barrier Override, Proximity Expiration Auto-Cancel, dan Visualisasi Dual-Tier Trajectory (TP1 & TP2)

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Disonansi Multi-Level Konvinsi (EURCAD H1 Case)**:
   - Pada kasus EURCAD H1, radar mendeteksi 3 level terpisah dalam jarak berdekatan: M2 EMA Pullback @ 1.60500, M3 SBR C1 Wall @ 1.60561, dan HTF SBR @ 1.60754.
   - Karena algoritma `find_ema_confluence_anchor` sebelumnya mengurutkan kandidat murni berdasarkan jarak terdekat ke harga mid (`abs(x - mid)`), floating EMA/quarter psych level (1.60500) yang kebetulan lebih dekat 6 pips dipilih mengalahkan dinding fisik SBR C1 (1.60561) yang telah dikonfirmasi oleh aksi harga multi-hari.
   - Konsolidasi 2 hari membuat EMA20/50 mendatar (flat), sehingga menaruh order limit pada angka psikologis/EMA tanpa menempel pada rak resistensi fisik meningkatkan risiko slippage atau false fill.
2. **Jebakan Pending Order Tertinggal Saat Target Tercapai (*Runaway Target Trap*)**:
   - Jika pending limit order ditempatkan di 1.60560 sementara pasar terus meluncur turun mencapai $\ge 75\%$ dari target take profit tanpa pernah pullback menjemput order limit, setup tersebut sejatinya telah terealisasi (*the move already happened*).
   - Membiarkan pending order tetap aktif di pasar menimbulkan bahaya besar: jika harga kemudian berbalik naik menyentuh 1.60560, itu seringkali bukan pullback retest melainkan pembalikan momentum (reversal) berlawanan arah yang berisiko langsung menabrak Stop Loss.
3. **Keterbatasan Visual Trajectory Tunggal di Dashboard**:
   - Radar standbys dan grafik dashboard hanya merender 1 garis target (`target_price` / TP1), sehingga pengguna tidak dapat melihat proyeksi multi-horizon (TP1 di dinding terdekat F1/C1 vs TP2 Macro Expansion di F2/C2).

---

### ✨ Komponen & Solusi Utama:

1. **Physical SBR/RBS Barrier Override (`market_scanner.py`)**:
   - Algoritma `find_ema_confluence_anchor` kini menerapkan pengelompokan klaster institusional:
     * Menghitung jendela klaster terdekat $\text{min\_dist} + (0.35 \times \text{ATR})$.
     * Seluruh kandidat di dalam jendela ini dikelompokkan ke dalam tier struktural: **Physical Structural Barriers (OB = Tier 0, F1/C1 Structural Wall = Tier 0)** diberi prioritas mutlak di atas **FVG (Tier 1)** dan **Atlas Psych Levels / EMA (Tier 2)**.
     * Dalam tier fisik yang sama, sistem memilih barrier yang disentuh pertama kali oleh pullback (`abs(price - mid)` terkecil).
     * Hasil: Pada kasus EURCAD, order limit otomatis menempel presisi di rak resistensi fisik C1 (1.60561), bukan di garis psikologis arbitrer.
2. **Pending Order Target Proximity Invalidation (`position_manager.py`)**:
   - Mesin `audit_pending_orders_thesis()` dipersenjatai dengan penjaga kedaluwarsa target proaktif:
     * **BUY_LIMIT**: Jika harga live pasar $\ge \text{open\_px} + 0.75 \times (\text{tp\_px} - \text{open\_px})$, order pending dibatalkan otomatis dengan notifikasi `"Target proximity expiration: market reached >=75% of TP without fill"`.
     * **SELL_LIMIT**: Jika harga live pasar $\le \text{open\_px} - 0.75 \times (\text{open\_px} - \text{tp\_px})$, order pending dibatalkan otomatis.
     * Menggunakan parser numerik aman (`_safe_num`) guna mencegah konversi nilai mock bawaan (1.0) pada unit test suite.
3. **Eksportasi Dual-Tier TP Standby (`market_scanner.py`)**:
   - Di blok M2, M3, dan M4, `get_radar_standbys` kini menghitung dan mengekspor `target_tp1` (Immediate Floor F1 / Ceiling C1) dan `target_tp2` (Deep Macro Expansion F2 / C2) ke dalam kamus `trajectory`.
4. **Visualisasi Vektor Bercabang di Dashboard Chart (`dashboard_assets.py`)**:
   - Grafik Lightweight Charts kini menggambar 2 vektor proyeksi:
     * **Vector 2a (Solid/Dashed)**: Retest Touch $\rightarrow$ `3a. TP1 <price>` (warna hijau/merah).
     * **Vector 2b (Extended Projection)**: TP1 $\rightarrow$ `3b. TP2 Expansion <price>` jika target makro F2/C2 tersedia.
5. **Unit Test Suite Lengkap (`tests/`)**:
   - `test_audit_pending_orders_thesis.py`: Menambahkan 3 skenario uji target proximity (BUY limit cancelled at 76% TP, SELL limit cancelled at 77.5% TP, SELL limit preserved when only 27.5% progress).
   - `test_market_scanner.py`: Menambahkan uji `test_find_ema_confluence_anchor_physical_override` dan `test_radar_standbys_dual_tp_trajectories`.
   - Seluruh 38 unit test target dan 100% full test suite PASS tanpa regresi.

---

## 0. Perubahan 4 September 2026 (Malam II) — Arsitektur 2-Tier Master CRO Arbiter, Anti-Frankenstein Atomic Package Engine & Pemisahan Visual CLI Pass 1 vs Pass 2

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Jebakan Hibrida Frankenstein (*The Frankenstein Hybrid Trap*)**:
   - Pada evaluasi live AUDCHF: OpenAI mengusulkan paket makro `buy_limit @ 0.58147` (SL 0.58003 di balik Floor F2, TP 0.58314 di Ceiling C1, R:R 1.16:1). Gemini mengusulkan paket micro price action `buy_limit @ 0.58187` (SL 0.58057 di balik M5 OB, TP 0.58488 di Ceiling C2, R:R 2.31:1).
   - DeepSeek V4-Flash (Master CRO di Pass 2) khawatir order OpenAI di F1 tidak terjemput (*"may not fill"*), sehingga memilih **Entry Gemini (0.58187)**. Namun untuk TP, DeepSeek justru mengambil **TP konservatif OpenAI di C1 (0.58314)**!
   - Akibat mencampur entry dekat market dengan TP terpendek, reward terperas menjadi hanya $12.7\text{ pips}$ melawan risk $13.0\text{ pips}$ $\rightarrow$ **R:R runtuh menjadi 0.97:1 (sub-par / negatif EV)**.
2. **Disonansi Visual CLI Konsensus Multi-LLM**:
   - Tampilan terminal CLI sebelumnya mencampur ketiga model secara datar (*flat loop*), menyembunyikan hierarki evaluasi antara Pass 1 (Specialist Investigation) dan Pass 2 (Master CRO Arbitration).

---

### ✨ Komponen & Solusi Utama:

1. **Injeksi Stasiun Quant & Prompt Arbiter DeepSeek CRO (`llm_client.py`)**:
   - Prompt `build_deepseek_cro_arbiter_prompt` diperkaya dengan kalkulasi otomatis R:R dan jarak poin untuk kedua paket Pass 1 (`PACKAGE A — OpenAI` vs `PACKAGE B — Gemini`).
   - Koordinat dealing chamber kuantitatif disuntikkan secara presisi: Floor F1, Floor F2, Ceiling C1, Ceiling C2, serta baseline quant station.
   - **Hukum Integritas Paket Utuh (*The Atomic Package Integrity Law*)**: DeepSeek diwajibkan mengevaluasi proposal sebagai satu kesatuan struktural utuh. Dilarang keras mencampur entry tinggi dengan TP pendek yang menghasilkan R:R $< 1.25\times$.
   - Skema JSON DeepSeek CRO kini menyertakan blok `arbitration_decision` (`openai_eval`, `gemini_eval`, `chosen_package`, `arbitration_rationale`) dan `calculated_rr` di dalam blok `execution`.
2. **Adopsi Paket Utuh & Anti-Frankenstein Guard (`consensus.py`)**:
   - Jika DeepSeek memilih `PACKAGE_OPENAI` atau `PACKAGE_GEMINI`, sistem konsensus secara otomatis mengadopsi satu set koordinat utuh (Entry, SL, TP) dari paket spesialis yang terpilih, alih-alih menghitung median terpisah.
   - **Anti-Frankenstein R:R Guard**: Sistem secara otomatis memverifikasi $R:R = \text{Reward} / \text{Risk} \ge 1.25:1$ dari harga eksekusi riil (bukan harga market). Jika R:R $< 1.25\times$, sistem memperluas TP ke Quant Target Station (atau level minimum $1.25\times$), menjamin perlindungan matematis absolut.
3. **Pemisahan Visualisasi Terminal CLI (`consensus.py`)**:
   - Terminal kini menampilkan kartu terpisah yang terstruktur rapi:
     * **`[ PASS 1: SPECIALIST DOSSIER INVESTIGATION ]`**: Kartu OpenAI (Macro Strategist) dan Gemini (Price Action Tactician) dengan konteks setup, retest quality, dan level.
     * **`[ PASS 2: MASTER CRO & RISK ARBITER ]`**: Kartu DeepSeek (Master CRO Arbiter) menampilkan paket arbitrase yang dipilih (`PACKAGE_OPENAI` / `PACKAGE_GEMINI` / `REVISE_EXPANDED_TP`), kalkulasi R:R, justifikasi risiko, dan tape audit M5.
     * **`[ FINAL CONSENSUS & EXECUTION TICKET ]`**: Ringkasan kesepakatan 3/3 dan tiket order yang divalidasi.
4. **Unit Test Suite Lengkap (`tests/test_cro_package_arbitration.py`)**:
   - 3 test case baru yang memvalidasi injeksi prompt, adopsi paket utuh, dan intersepsi Anti-Frankenstein Guard.
   - Seluruh test suite (105/105 tests) PASS 100%.

---

## 0. Perubahan 4 September 2026 (Sore II) — Sinkronisasi SMC D1/H4 Macro Trend, HTF Wall Collision Gate (M3), & Unshackling M1 Universal Liquidity Sweep

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Jebakan Lagging 2-EMA D1/H4**:
   - `market_scanner.py` menggunakan `close >= ema20 and close >= ema50`. Pada GBPUSD yang sedang mengalami koreksi tajam dari 1.3675 ke 1.3474, pantulan tipis 5 pip di atas EMA20 (1.35336) secara keliru melabeli pasar sebagai `D1_BULLISH_EXPANSION` dan `is_bull = True`.
   - Di H4, pembalikan logika boolean membuat pantulan korektif di dalam tren turun (`h4_c > h4_ema20 and h4_ema20 <= h4_ema50`) dilabeli `h4_is_bull = True`, bertolak belakang dengan MSE 6-TF (`HUNT_SELL_PULLBACK`, `CEILING_REJECTION at 1.35383`).
2. **Pembunuhan Prematur M1 SELL Universal Liquidity Sweep**:
   - Aturan anti-trend `is_macro_bull` membaca `macro['is_bull'] == True`, langsung memicu `[SWEEP SELL ANTI-BULL VETO]`, sehingga peluang M1 SELL sweep di resistensi C1 terbuang meski MSE mengarahkan penjualan di plafon.
3. **M3 BUY Menabrak Plafon di Premium Zone**:
   - M3 BUY breakout mengukur runway plafon dari support lama yang tertinggal (`target_res`) alih-alih harga live (`mid`). Akibatnya radar meloloskan order BUY_LIMIT di 1.35403 tepat ke dinding plafon C1 di Premium (73.8% Range) yang ditolak 0/3 oleh AI Jury (`LIQUIDITY_TRAP`, `DIRTY_SWEEP`).
4. **Klarifikasi Istilah M2**:
   - Menstandarkan penamaan telemetry M2 sebagai `Touched` / `Retest EMA` (kata `Break` murni milik M3/M4).

---

### ✨ Komponen & Solusi Utama:

1. **Integrasi SMC Market Structure pada D1 & H4 (`market_scanner.py`)**:
   - D1 memadukan `d1_smc.trend_bias` (`LuxSMCAnalyzer(swing_length=3)`): jika struktur SMC bearish, pantulan di atas EMA20 diklasifikasikan sebagai `D1_BEARISH_PULLBACK` (`is_bear = True`, `is_bull = False`).
   - Koreksi pembalikan polaritas boolean H4: pantulan dalam tren turun (`h4_ema20 <= h4_ema50`) diklasifikasikan sebagai `H4_BEARISH_PULLBACK` (`h4_is_bear = True`, `h4_is_bull = False`).
   - Harmonisasi dengan MSE 6-TF: direktif strategis MSE (`HUNT_SELL_PULLBACK` / `HUNT_BUY_DIP`) disinkronkan langsung ke `combined_is_bull` / `combined_is_bear`.
2. **HTF Wall Collision & Runway Guard pada M3 Breakout (`market_scanner.py`)**:
   - Mengukur jarak fisik riil `dist_to_ceiling = target_ceiling - mid`.
   - Menolak keras (`[BREAKOUT BUY WALL COLLISION] SKIP` + `continue`) order BUY jika harga berada dalam radius $\le 0.35\times\text{ATR}$ dari plafon C1 atau berada di Premium Zone ($dr\_pos \ge 0.70$). Simetris untuk M3 SELL pada lantai F1 di Discount ($dr\_pos \le 0.30$).
3. **Unshackling M1 Universal Liquidity Sweep di Plafon/Lantai Ekstrem (`market_scanner.py`)**:
   - Anti-trend veto tidak lagi memblokir SELL sweep jika harga berada di Premium Zone ($dr\_pos \ge 0.65$) pada dinding validasi G2/G3 atau di bawah mandat MSE (`HUNT_SELL_PULLBACK`, `CEILING_REJECTION`, `FADE_CORRIDOR_EXTREMES`).
   - Tetap mempertahankan seluruh kualifikasi ketat M1 (penetrasi stop-hunt, reclaim penutupan di balik level, dan rejection wick).
4. **Penegakan Aturan Terminologi Resmi (Universal Liquidity Sweep)**:
   - Memastikan semua pemanggilan gate menggunakan `evaluate_universal_sweep_gates` sesuai Rule 7 AGENTS.md.
5. **Unit Test Suite (102/102 PASS — 100%)**:
   - Isolasi hermetis `setUp` dari file disk `scanner_cooldowns.json`.
   - Penambahan `test_d1_h4_smc_pullback_classification` dan `test_m3_htf_wall_collision_and_m1_unshackling`.

---

## 0. Perubahan 4 September 2026 (Malam) — Pemisahan Rejection (Soft Timing HOLD vs Hard VETO) & Penyelarasan Mandate Thesis MSE

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Disonansi Semantik MSE vs Setup Retest/Limit (Mid-Chamber Trap)**:
   - Ketika harga berada di rentang 20%–80% dari dealing chamber (misalnya 28% atau 2.4 pips di atas Floor F1), MSE mencap kondisi tersebut sebagai `CHAMBER_CONSOLIDATION` dengan teks kaku:
     `Mandate Thesis: Discipline requires waiting for extreme boundary touch...`
     `Forbidden Traps: Do NOT execute market orders in mid-chamber consolidation zone`
   - LLM membaca teks ini sebagai larangan kuantitatif mutlak dari sistem internal, sehingga secara otomatis mengeluarkan `HOLD` / `REJECT`.
2. **Jebakan Hukuman Cooldown Kaku (*The 45-Minute Lockout Trap*)**:
   - Di `main.py`, setiap kali AI menjawab `HOLD`, sistem langsung memanggil `record_setup_rejection()`, mengunci `(symbol, setup_type, direction)` selama **45 menit** (dan level retest M3 selama **2 jam**).
   - Akibatnya: 5–10 menit kemudian harga menyentuh tepat di level boundary (Floor F1) dengan rejection wick 50% (sesuai yang ditunggu), namun Stage 1 Radar melewatinya (*skip*) karena masih tertahan lockout 45 menit. Peluang profit terlewat total.

---

### ✨ Komponen & Solusi Utama:

1. **Bifurkasi Klasifikasi Rejection di `main.py`**:
   - **Hard Risk VETO (45 Menit Lockout)**:
     Jika terdeteksi salah satu fatal risk flag (`COUNTER_TREND_MOMENTUM`, `FALLING_KNIFE_WATERFALL`, `SYSTEMIC_CURRENCY_DUMP`, `HIGH_IMPACT_NEWS`, `LIQUIDITY_TRAP`, `UNMITIGATED_IMPULSE_CHASE`). Kunci mekanisme 45m aktif secara protektif.
   - **Soft Timing HOLD (Hanya 3 Menit Breathing Cooldown)**:
     Jika `risk_flag` adalah `"NONE"` (penolakan murni karena timing atau harga belum menyentuh level). Sistem memanggil `scanner_inst.record_soft_timing_hold(sym)`, HANYA mengaktifkan jeda bernapas simbol 3 menit **TANPA mengunci mekanisme 45 menit**. Begitu harga menyentuh boundary level beberapa menit kemudian, Radar langsung siap memindai dan mengeksekusi kembali!
2. **Penyelarasan Semantik Mandate Thesis & Forbidden Traps (`macro_strategic_engine.py`)**:
   - Teks `thesis` dan `forbidden_traps` diperbarui untuk secara eksplisit membedakan *Market Chase Order* (dilarang mid-chamber) dari *Pending Limit Orders / Structural Retests* di boundary Floor F1 / Ceiling C1 (diizinkan & direkomendasikan via `REVISE`).
3. **Edukasi Resolusi Mid-Chamber pada Prompt Dossier (`llm_client.py`)**:
   - Rule #4 pada prompt OpenAI dan Gemini menegaskan bahwa jika harga berada di mid-chamber mendekati boundary, model diarahkan memilih `REVISE` dengan `buy_limit` / `sell_limit` di anchor level daripada melakukan hard `REJECT`.
4. **Metode Baru `record_soft_timing_hold()` (`market_scanner.py`)**:
   - Menyediakan API mandiri untuk jeda bernapas simbolik tanpa mengotori `_mechanism_rejection_cooldowns`.
5. **Unit Test Suite (120/120 PASS — 100%)**:
   - Test case baru `test_soft_timing_hold_vs_hard_veto_lockout` di `tests/test_market_scanner.py` memverifikasi presisi pemisahan cooldown.

---

## 1. Perubahan 4 September 2026 (Sore) — Penyelarasan Paradigma AI Dossier, Limit Order Priority & Fix Re-Evaluator Pending Order (Thesis Broken)

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **False Rejection Akibat Benturan Paradigma (Audit 13:45–14:05 WIB)**:
   - 4 setup valid yang lolos Stage 1 Radar (AUDCAD BUY, GBPUSD BUY, EURCHF SELL, USDCHF SELL) ditolak bulat oleh Stage 2 LLM Jury.
   - Akar masalah: Prompt sistem multi-LLM mendiktekan bahwa *BUY HANYA diizinkan di Discount (≤ 50%)* dan *SELL HANYA diizinkan di Premium (≥ 50%)*. Ini aturan mean-reversion (M1/M2) yang bertentangan langsung dengan mekanisme breakout/continuation (M3/M4), di mana breakout resistance secara alamiah berada di Premium (> 50%) dan breakdown support berada di Discount (< 50%).
2. **Salah Tafsir Candlestick Tape M5 (Pullback Retest vs Waterfall)**:
   - Saat harga melakukan pullback retracement menuju level retest anchor, lilin M5 secara alami berlawanan arah (2–3 bar merah saat pullback ke support BUY). Model Gemini dan DeepSeek mencapnya sebagai `COUNTER_TREND_MOMENTUM` / `FALLING_KNIFE_WATERFALL`, padahal itu adalah proses pengujian level yang wajar.
   - Tape M5 di `main.py` sebelumnya hanya mengirim string OHLC mentah tanpa kalkulasi pips sumbu/body.
3. **Bug Kritis Re-Evaluator Pending Order (`audit_pending_orders_thesis()`)**:
   - Order limit yang sudah terpasang sering dibatalkan sepihak tiap 3 detik karena evaluasi ambigu `"REJECTION" in m_state`.
   - Akibatnya, `SELL_LIMIT` di ceiling justru dibatalkan saat terdeteksi `CEILING_REJECTION` (yang sebenarnya adalah sinyal jual valid), dan `BUY_LIMIT` dibatalkan saat `FLOOR_REJECTION`!

---

### ✨ Komponen & Solusi Utama:

1. **Pemisahan Paradigma Setup pada System Directives (`llm_client.py`)**:
   - Aturan #4 sistem prompt memisahkan tegas:
     * *Mean-Reversion / Reload (M1 & M2)*: Wajib patuh batas 50% Dealing Range HTF.
     * *Breakout Retest & Continuation (M3 & M4)*: Dibebaskan dari batasan 50% Dealing Range HTF. Evaluasi difokuskan pada kualitas retest level structural flip (RBS/SBR) dan runway stasiun target ZCE.
2. **Prioritaskan `REVISE -> Limit Order` daripada Hard `REJECT` (`llm_client.py`)**:
   - Jika arah dan zona level memiliki probabilitas institusional yang baik namun timing pasar saat ini belum optimal (sedang retracement atau mid-corridor), LLM diinstruksikan memilih `REVISE` dengan memasang Pending Limit Order di level anchor.
   - Status `REJECT` / Veto dicadangkan strictly untuk risiko fatal: Counter-trend mayor tanpa CHoCH, lonjakan berita Tier-1 aktual, atau candle waterfall yang menembus bablas level invalidasi.
3. **Edukasi Candlestick Tape M5 (`llm_client.py`) & Feeder `main.py`**:
   - Header konteks `[PULLBACK RETEST RETRACEMENT CHECK]` ditambahkan ke prompt.
   - Ditegaskan bahwa lilin counter-trend saat mendekati anchor adalah retracement normal, bukan waterfall, selama ada wick rejection $\ge 25\%$ atau deselerasi body.
   - Feeder `main.py` diperbarui menggunakan `llm.format_micro_tape()` sehingga tape M15, M5, H1, H4 menyajikan kalkulasi eksplisit pips `Body / WickU / WickL`.
   - Injeksi data 3-point trajectory (`origin_price`, `origin_age`, `target_price`) ke dossier prompt.
4. **Refactoring Re-Evaluator Pending Order (`position_manager.py`)**:
   - Menghapus pengecekan ambigu `"REJECTION" in m_state`.
   - Menerapkan **Evaluasi Struktural Ketat**:
     * BUY Pending Order HANYA dibatalkan jika M15 close menembus ke bawah SL atau anchor $> 0.50\times\text{ATR}$ (`last_close < anchor - 0.50*atr`), ATAU CSM Net Delta berbalik tajam ($<-0.35$), ATAU terkonfirmasi `FLOOR_BREAKDOWN`.
     * SELL Pending Order HANYA dibatalkan jika M15 close menembus ke atas SL atau anchor $> 0.50\times\text{ATR}$ (`last_close > anchor + 0.50*atr`), ATAU CSM Net Delta berbalik tajam ($>+0.35$), ATAU terkonfirmasi `CEILING_BREAKOUT`.
5. **Unit Test Suite 100% Pass (`tests/test_audit_pending_orders_thesis.py`)**:
   - 4 test case baru memvalidasi perbaikan bug `CEILING_REJECTION` dan `FLOOR_REJECTION`, serta memastikan pembatalan struktural bekerja presisi.

---

## 1. Perubahan 4 September 2026 (Siang) — Dual-Timeframe Microscope (M3 M5-Rejection & M4 M15/M30 Basing Engine)

### 🎯 Latar Belakang & Bukti Kuantitatif (100k Bar M5 + 11k H1 Swings):
1. **Kegagalan Fatal Blind Retest M3 (4.8% Win Rate)**:
   - Dari 6.826 sentuhan retest pada broken support/resistance level, **75.7% (5.166 kasus) adalah *Waterfall Penetration*** di mana lilin M5 menembus bablas tanpa penolakan (Win Rate hanya 0.8%).
   - Memfilter retest dengan **M5 Rejection Wick $\ge 25\%$** terbukti melipatgandakan Win Rate menjadi **71.7%** ($N=99, \chi^2 = 348.2, p < 10^{-10}$).
2. **Kekeliruan Asumsi Deep Retest M4 (10.1% Win Rate)**:
   - Data membuktikan paska penembusan swing 120-bar saat flow meledak ($|z| \ge 1.5$), jika harga sampai turun kembali ke level awal, momentum sering kali sudah mati (Win Rate 10.1%).
   - Sebaliknya, saat harga membentuk **High-Tight Basing M15/M30 (`/\/\/\/`)** di atas level pecahan ($\le 0.35\times\text{ATR}$), peluang kelanjutan tren naik **2.5x lipat (24.9% vs 10.1%)**.
3. **Memori Retest Basi 120 Bar**:
   - Menahan level breakdown selama 120 bar (5 hari bursa) membuat radar dipenuhi antrean M4 gantung yang sudah kehilangan relevansi flow.

---

### ✨ Komponen & Solusi Utama:

1. **M3 M5 Micro-Rejection Gate (`market_scanner.py`, `config.py`, `.env`)**:
   - `M3_M5_REJECTION_FILTER = True`, `M3_M5_MIN_WICK_RATIO = 0.25`:
     - Menarik 6 candle M5 via MT5 (<1ms, 0 token) saat harga memasuki zona retest $0.28\times\text{ATR}$.
     - Wajib mendeteksi sumbu penolakan fisik $\ge 25\%$ (upper wick untuk SELL SBR, lower wick untuk BUY RBS) atau pantulan close menjauh dari level.
     - Lilin marubozu waterfall yang menembus level $>0.15\times\text{ATR}$ tanpa sumbu di-blokir 100% di Stage 1 sebelum memanggil 3-LLM Jury.

2. **M4 Horizon Retest 48 Bar (2 Hari Bursa) (`config.py`, `.env`, `market_scanner.py`)**:
   - `M4_MAX_WAIT_BARS = 48` (dipangkas dari 120 bar ke 48 bar H1).
   - Menghapus antrean M4 basi yang tidak kunjung disentuh dalam 2 hari bursa.

3. **M4 M15/M30 High-Tight Basing Engine (`market_scanner.py`)**:
   - `M4_BASING_MIN_BARS = 4`, `M4_BASING_MAX_RANGE_ATR = 0.35`:
     - Selain Mode A (Deep Retest), sistem mendukung Mode B: Konsolidasi mendatar M15 (FX Majors) dan M30 (JPY Crosses).
     - Jika 4 bar M15/M30 berkonsolidasi ketat $\le 0.35\times\text{ATR}$ di atas level penembusan dan harga menguji batas base tersebut, order limit dipasang di boundary base dengan SL struktural $0.45\times\text{ATR}$ dan TP $1.1R$.

---

## 1. Perubahan 4 September 2026 (Pagi) — Granular Mechanism Cooldown, M4 Range Discipline & Multi-Confluence Architecture

### 🎯 Latar Belakang & Identifikasi Flaw:
1. **Cross-Mechanism Contamination Trap (AUDUSD Case Study)**:
   - Pada saat setup M4 (`SYSTEMIC_FLOW_CONTINUATION` BUY_LIMIT @ 0.7208) ditolak oleh 3-LLM Jury (Pass 2 CRO DeepSeek mendeteksi `IMPULSE_CHASE` di 89.5% Dealing Range), `main.py` memanggil `record_retest_rejection(sym, ...)`.
   - Di `market_scanner.py`, fungsi ini menetapkan `self._symbol_last_trigger[clean_sym] = now_ts + 1800`, yang memicu *blanket symbol lockout* selama 45 menit untuk pasangan tersebut.
   - Akibatnya, setup valid M1 (Universal Liquidity Sweep), M2 (Pullback), dan M3 (Multi-Touch Breakout Retest) yang berada di zona yang sama (0.72071 - 0.72085) ikut terbunuh dan diabaikan total selama 45 menit.
2. **Ketiadaan Filter Range Discipline di Hulu M4 (Stage 1 Radar)**:
   - Mekanisme M4 sebelumnya tidak mengecek Dealing Range sama sekali, sehingga memancarkan BUY di Extreme Premium (>70%) atau SELL di Extreme Discount (<30%), membakar token LLM hanya untuk di-veto oleh DeepSeek CRO.
3. **Ketiadaan Tagging Multi-Mekanisme Confluence**:
   - Ketika M1, M2, dan M3 aktif bersamaan pada rentang sempit ($\le 0.35\times\text{ATR}$), 3-LLM Jury tidak menerima sinyal bahwa level tersebut merupakan konvergensi dari berbagai mekanisme kuantitatif.

---

### ✨ Komponen & Solusi Utama:

1. **Granular Per-Mechanism & Per-Direction Cooldown Engine (`market_scanner.py`, `config.py`, `.env`)**:
   - `SCANNER_SYMBOL_BREATHING_COOLDOWN_SECONDS = 180` (Jeda bernapas simbol 3 menit untuk mencegah spam token beruntun).
   - `SCANNER_MECHANISM_REJECTION_COOLDOWN_SECONDS = 2700` (Lockout granular 45 menit terpisah per tuple `(symbol, setup_type, direction)`).
   - Penolakan M4 BUY hanya mengunci M4 BUY. M1 BUY/SELL, M2 BUY/SELL, dan M3 BUY/SELL pada simbol yang sama tetap dapat dievaluasi setelah jeda bernapas 3 menit.
   - Lockout level harga fisik di `_retest_rejected_levels` dikhususkan hanya untuk setup bertipe `M3_BREAKOUT_RETEST` / `MULTI_TOUCH_BREAKOUT_RETEST`.
   - Format penyimpanan `data/scanner_cooldowns.json` diperbarui mendukung format granular dengan mempertahankan kompatibilitas mundur.

2. **Stage 1 Radar M4 Flexible Range Discipline (`market_scanner.py`, `config.py`, `.env`)**:
   - `M4_EXTREME_DR_THRESHOLD = 0.70`:
     - M4 BUY di atas 70% Dealing Range (Extreme Premium) di-filter di Stage 1 Radar (0 token), KECUALI jika didukung oleh aliran modal global yang sangat ekstrem (`csm_delta >= +0.035`).
     - M4 SELL di bawah 30% Dealing Range (Extreme Discount) di-filter di Stage 1 Radar (0 token), KECUALI jika didukung oleh `csm_delta <= -0.035`.

3. **Multi-Mechanism Confluence Detection & Dossier Injection (`market_scanner.py`, `src/core/llm_client.py`)**:
   - Sebelum emisi kandidat radar, sistem memeriksa apakah terdapat $\ge 2$ mekanisme yang aktif searah dalam radius $\le 0.35\times\text{ATR}$.
   - Jika terdeteksi, radar menyematkan atribut `multi_confluence = True` dan `confluence_mechanisms` (misal: `['M1_UNIVERSAL_LIQUIDITY_SWEEP', 'M2_PULLBACK', 'M3_BREAKOUT_RETEST']`).
   - Injeksi langsung ke Dossier 3-LLM Jury:
     - Pass 1: Baris `MULTI-MECHANISM CONFLUENCE: ACTIVE (M1+M2+M3 within 0.35xATR)` pada metadata.
     - Pass 2: Parameter `Multi-Mechanism Confluence` pada audit `Trade Specification`.

4. **Sinkronisasi Pemanggilan Rejection Memory (`main.py`)**:
   - Memutakhirkan penanganan VETO Pass 2 dan HOLD konsensus di `main.py` untuk meneruskan `cand.setup_type` dan `cand.direction` ke `scanner_inst.record_setup_rejection()`.

---

## 1. Perubahan 4 September 2026 (Dini Hari) — Pemisahan Tren Struktural HTF dari Status Taktikal Kamar & M2 Confluence Anchor

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Pembajakan Tren Struktural oleh Pengujian Batas Kamar (Tactical Contamination)**:
   - Sebelumnya, saat harga menyentuh lantai diskon F1 pada kondisi tren turun tajam (downtrend), pembacaan bias sesaat dapat membalik label makro menjadi bullish, merusak disiplin trend-following.
2. **Ketiadaan Konfluensi Fisik pada Anchor M2 Pullback**:
   - Level M2 Pullback sebelumnya rentan mengambil titik swing acak. Pada tren bearish, level entri bisa terpasang di bawah harga pasar (swing low) alih-alih di rak resistensi/EMA di atas harga.

---

### ✨ Komponen & Solusi Utama:

1. **Pemisahan Tren Struktural HTF vs Status Taktikal Kamar (`market_scanner.py`, `dashboard.py`)**:
   - Tren makro D1/H4 (`combined_is_bull`, `combined_is_bear`) dikunci murni berdasarkan ekspansi/pullback struktural.
   - Status batas ekstrim dipisahkan ke dalam variabel `tactical_state`:
     * `REBOUND_WATCH_AT_FLOOR`: Harga menguji Floor F1 atau berada di diskon $\le 20\%$.
     * `REJECTION_WATCH_AT_CEILING`: Harga menguji Ceiling C1 atau berada di premium $\ge 80\%$.
     * `BALANCED_FLOW`: Berada di jalur pergerakan normal.
   - **Diferensiasi Arah M1 vs M2**:
     * M1 diizinkan fade batas ekstrim: Bullish Sweep Support (SFP Low) saat menguji lantai diskon $\le 30\%$, Bearish Sweep Resistance (SFP High) saat menguji plafon premium $\ge 70\%$.
     * M2 tetap patuh arah tren makro: Bearish Pullback selalu mencari resistensi $\ge \text{mid}$, Bullish Pullback selalu mencari support $\le \text{mid}$.

2. **M2 Confluence Anchor & Retest Identification (`market_scanner.py`)**:
   - Implementasi `find_ema_confluence_anchor()`: Mengaitkan level M2 ke konfluensi terdekat (OB, FVG, F1/C1, Psychological Level, EMA20/50).
   - Menambahkan metadata temporal tracking pada `get_radar_standbys` (`event_time`, `status`, `bar_age`, `direction`, `trajectory`).

3. **Peningkatan Visualisasi Chart Dashboard (`dashboard.py`, `dashboard_assets.py`)**:
   - Merender marker lilin, label status taktikal, dan garis proyeksi trajektori secara real-time pada Lightweight Charts.

4. **Automated Unit Tests (`tests/test_market_scanner.py`)**:
   - `test_get_radar_standbys_bearish_and_bullish`: Verifikasi M2 bearish selalu $\ge \text{mid}$ dan bullish $\le \text{mid}$.
   - `test_find_ema_confluence_anchor_and_temporal_tracking`: Validasi penjangkaran konfluensi dan field temporal.
   - `test_structural_trend_and_tactical_chamber_separation`: Memastikan tren makro tetap bearish saat terjadi pantulan di lantai F1.

---
## 1. Perubahan 3 September 2026 (Malam) — M3 Fresh Breakout Law, Retest Debounce, Segmented SL Floor & Net R:R Commission Engine

### 🎯 Latar Belakang & Identifikasi Flaw:
1. **Pemicu Beruntun M3 Radar (75 Setup / 5 Jam)**:
   - Audit mendapati mekanisme M3 (Multi-Touch Breakout Retest) menyumbang 68 dari 75 setup (90.7%) yang dikirim ke 3-LLM Jury.
   - Pemicunya adalah kombinasi bug scoping variabel `df` di `scan_all` (menyebabkan filter 16-bar recency selalu fallback ke `True`) dan `Retest Hovering Trap` di mana pair berkonsolidasi di pita sempit 2-3 pips selama 4 jam berturut-turut sementara cooldown hanya 15 menit.
2. **Friksi Komisi pada Lot Sizing Mikro**:
   - Pair dengan volatilitas rendah (seperti EURCHF dengan ATR H1 72 pts) menghasilkan SL ultra-sempit (29 pts) akibat M4 bypass total terhadap safety floor.
   - Akibatnya lot membengkak ke 1.60 lot, dan komisi broker round-turn ($9.60) memakan hingga 15-60% dari target TP kotor atau memperbesar risiko rugi melampaui 1% equity.

---

### ✨ Komponen & Solusi Utama:

1. **M3 Fresh Breakout Law & Displacement Guard (`market_scanner.py`)**:
   - `M3_BREAKOUT_RECENCY_BARS = 4`: Breakout wajib terjadi dalam rentang 3–4 candle H1 terakhir (bukan level purba 16-120 bar).
   - `M3_MIN_DISPLACEMENT_BODY = 0.55`: Candle yang menembus level wajib merupakan candle momentum dengan rasio bodi $\ge 55\%$ (mengeliminasi penetrasi sumbu / doji palsu).
   - Scoping DataFrame `df` di-pass secara presisi dari macro cache per-simbol.

2. **1 Episode Retest = 1 Evaluasi LLM (Debounce Memory)**:
   - Method `record_retest_rejection()` dan `is_retest_locked()` di `MarketScanner`: Ketika 3-LLM Jury memberikan keputusan REJECT atau HOLD pada suatu level, level tersebut di-lock total.
   - Un-lock hanya terjadi jika harga mengalami perpindahan struktural $> 0.50\times\text{ATR}$ dari level tersebut ATAU telah berlalu minimal 2 jam (2 candle H1).

3. **Segmented Absolute SL Floor (`config.py`, `.env`, `consensus.py`)**:
   - Formula: $\text{SL Floor} = \max(2\times\text{Spread} + \text{Padding}, \quad \text{Floor Absolut Kategori}, \quad \text{Multiplier}\times\text{ATR})$.
   - **Quiet/Standard FX**: Floor absolut **120 pts (12 pips)**. Membatasi lot sizing pada akun \$5.8k ke $\le 0.40 - 0.45$ lot.
   - **High-Beta Crosses** (`GBPAUD`, `GBPNZD`, `EURNZD`, `GBPCHF`): Floor absolut **180 pts (18 pips)**.
   - **JPY Crosses** (M30): Multiplier $1.00\times\text{ATR M30}$ dengan floor absolut **200 pts (20 pips)**.
   - **M4 Systemic Flow**: Dihapuskannya bypass total anchor beku. Usulan M4 tetap tunduk pada Segmented Safety Floor dan Net R:R (`M4_STRUCTURAL_FLOORED`).

4. **Friction-Aware Net R:R Engine (`consensus.py`, `atlas_dna.py`, `risk_engine.py`)**:
   - Formula TP Minimum Bersih:
     $$\text{min\_tp\_pts} = \text{int}(\text{sl\_points} \times \text{min\_rr}) + \text{spread\_pts} + \text{comm\_pts}$$
   - Round-turn komisi dihitung dinamis dari `COMMISSION_USD_PER_LOT_ROUND = 6.0`.
   - `risk_engine.py` mengaudit rasio friksi: memperingatkan jika friksi transaksi melampaui `MAX_FRICTION_TO_SL_RATIO = 0.20` (20% dari SL fisik).

---

## 2. Perubahan 2 September 2026 — Dual-Basket Confluence & Dispersion Matrix Engine

### 🎯 Latar Belakang & Identifikasi Flaw Single-Basket:
- Analisis kuantitatif mengungkap bahwa menilai posisi pair $P = X/Y$ (misal `GBPCHF`) hanya dari satu basket mata uang (misal basket `CHF`) adalah *Single-Basket Fallacy*.
- Pasangan mata uang $P = X/Y$ berada pada **persimpangan dua basket sekaligus** (Base Currency $X$ dan Quote Currency $Y$).
- Ketika `AUDCHF` menyentuh level support struktural bawah dan melambat, `GBPCHF` bergerak naik bukan hanya karena rotasi CHF, tetapi karena komponen **GBP mengalami penguatan independen** (terbukti dari `GBPAUD` yang ikut naik di saat bersamaan).

---

### ✨ Komponen & Arsitektur Utama (Commit `58510bc` pada branch `quant-trade`):

1. **Normalized Structural Position ($pos_i \in [0.0, 1.0]$)**:
   - Dihitung dari posisi harga relatif terhadap Dealing Range 50-bar H1.
   - $pos_i = 0.0$ merepresentasikan Floor/Discount, dan $pos_i = 1.0$ merepresentasikan Ceiling/Premium.

2. **Basket Dispersion Metric ($\sigma_C$)**:
   - Dihitung deviasi standarnya pada seluruh 26 simbol FX terkurasi ($N \ge 6$ pair per basket):
     $$\sigma_C = \sqrt{\frac{1}{N_C} \sum_{i=1}^{N_C} (pos_{C, i} - \bar{pos}_C)^2}$$
   - $\sigma_C \ge 0.22$: **High Dispersion** (terdapat ketimpangan Leader vs Laggard).
   - $\sigma_C < 0.10$: **Low Dispersion / Systemic Cohesion** (pergerakan serentak).

3. **Explicit Leader Hit Wall Condition**:
   - Menghubungkan skala relatif $[0.0, 1.0]$ dengan jarak fisik ATR secara presisi via kondisi `AND`:
     $$\text{Leader\_Hit\_Wall}(C) = (pos \ge 0.90 \text{ or } pos \le 0.10) \quad \mathbf{AND} \quad (\text{Physical Distance} \le 0.35 \times \text{ATR}_{H1})$$

4. **Deterministic Decision Hierarchy (Mutual Exclusive Order)**:
   - **Tier 1 — `SURGE_OVERRIDE_Y` / `SURGE_OVERRIDE_X`**: Lonjakan kecepatan 4-bar $|\Delta Y| \ge 12.0$ atau $|\Delta X| \ge 12.0$ meng-override basket lawan (pair $X/Y$ mengikuti dorongan mata uang yang mengalami surge).
   - **Tier 2 — `SYSTEMIC_EXPANSION`**: $\sigma_X < 0.10 \text{ AND } \sigma_Y < 0.10$ (kedua basket bergerak serentak, lead-lag catchup dimatikan).
   - **Tier 3 — `PURE_CATCHUP_LEAD_LAG`**: $\sigma_X \ge 0.22 \text{ AND } \text{Leader\_Hit\_Wall} \text{ AND } pos_{X/Y} \in [0.20, 0.80]$ (pair $X/Y$ terkonfirmasi sebagai laggard ber-probabilitas tinggi untuk catch-up).
   - **Tier 4 — `NEUTRAL_ROTATION`**: Rotasi teknis standar.

---

### 🛡️ Zero-Risk Informational Ingestion Deployment:
- **Stage 1 Radar ([src/analytics/market_scanner.py](file:///c:/Vibe/tradingpartner/src/analytics/market_scanner.py))**: **100% UNTOUCHED / ZERO HARD GATING**. Filter eksekusi `Permission.GO/ARM/WATCH/LOCK` tetap berjalan tanpa perubahan threshold.
- **Stage 2 LLM Dossier ([src/core/llm_client.py](file:///c:/Vibe/tradingpartner/src/core/llm_client.py))**: Menyambungkan output `get_dual_basket_context()` ke dalam `get_csm_prompt_payload(symbol)`.
- **Informational Warning**:
  ```text
  ### RESEARCH SHADOW METRIC — EXPERIMENTAL DUAL-BASKET CONFLUENCE
  (Note: Exploratory shadow metric for supplementary context only — do NOT override core technical structure)
  - Dual-Basket Classification (GBPCHF): [NEUTRAL_ROTATION]
  - Base (GBP) Basket Dispersion: σ=0.29 (N=7 pairs) | Leader Status: GBPUSD (6% pos, 0.00x ATR to wall)
  - Quote (CHF) Basket Dispersion: σ=0.28 (N=6 pairs) | Leader Status: EURCHF (8% pos, 0.00x ATR to wall)
  - Analytical Confluence Directive: Balanced cross-basket dispersion (σ_GBP=0.29, σ_CHF=0.28). Standard technical rotation.
  ```

---

### 🧪 Verifikasi & Audit Live MT5:
- Script scratch `live_basket_audit.py` dan unit test `test_dual_basket.py` berhasil mengeksekusi audit live 26 FX pairs dari MT5 dengan **0 Error**.
- Hasil audit membuktikan keberadaan pola propagasi real-time (contoh: `AUDNZD` 100.0% Hit Wall vs `GBPNZD` 70.5% Lagging).

---

## 2. Perubahan 2 September 2026 — Startup Latency Optimization (50s -> 9.1s)

### ⚡ Komponen Optimasi Kinerja Startup:
1. **Vectorized NumPy FRVP (`volume_profile.py`)**:
   - Menggantikan iterasi loop bersarang $O(N \times M)$ dengan operasi *broadcasting* matriks 2D NumPy untuk seluruh *bins* secara simultan ($1.174\text{s} \rightarrow 0.043\text{s}$, **$27\times$ lebih cepat**).
2. **Fast Array Swings & Pattern Detection (`macro_strategic_engine.py`)**:
   - Mengonversi pencarian `.iloc` pandas Series di dalam loop *swings* ke akses array mentah NumPy `.values` (**$10\times$ lebih cepat**).
   - Menonaktifkan kalkulasi FRVP impuls yang redundan pada pemindaian struktur HTF ($H_4, D_1, W_1$), menyisakan kalkulasi FRVP aktif murni pada timeframe eksekusi ($H_1$).
3. **Parallel Macro Context Ingestion (`market_scanner.py`)**:
   - Memodifikasi `update_macro_context` untuk memproses seluruh 26 simbol universe secara paralel menggunakan `ThreadPoolExecutor(max_workers=6)`.
   - **Hasil**: Waktu ingest makro 26 simbol terpangkas dari **39.932s $\rightarrow$ 6.812s ($5.8\times$ speedup)**.
4. **Telegram Controller Lazy Loading (`telegram_bot.py`)**:
   - Memindahkan impor library berat AI SDK (`openai`, `google.genai`, `anthropic`) ke dalam pemanggilan *on-demand* perintah `/analisa`, serta memindahkan eksekusi `register_bot_commands()` ke dalam *daemon thread worker* asinkron.
   - **Hasil**: Waktu impor modul turun drastis dari **19.202s $\rightarrow$ 0.097s ($198\times$ lebih cepat)**.
   - **Total Waktu Startup Bot**: Turun dari **$50.0\text{s} \rightarrow 9.130\text{s}$ ($5.5\times$ akselerasi total)** sampai terminal Cyberpunk Bento HUD live.

---

## 3. Perubahan 2 September 2026 — Modernisasi Cyberpunk Bento Box HUD Tile 4 (`cli_theme.py`)

- Memodernisasi **Tile 4 (Kanan Bawah)** dengan intelijen eksekusi kuantitatif *real-time*:
  * **3-AI Jury & Unanimous Consensus**: Menampilkan model aktif (OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4-Flash) dan aturan konsensus mutlak 3/3 (*Zero-Tolerance Split*).
  * **2D Confluence Sizing**: Multiplier dinamis (`Grade S 1.25x`, `Grade A 1.00x`, `Grade B 0.50x TP1 Scalp`).
  * **Thesis Sentinel**: Status penjaga M15 $C_1/F_1$ Reclaim & Invalidation Guard.
  * **Server & WIB Clock Sync**: Sinkronisasi jam server MT5 GMT+3 ke WIB dengan status hitung mundur *Pre-Rollover Spread Shield* (03:50 WIB).
  * **Safety Floors**: ATR SL Floor ($0.68\times H_1 / 1.00\times M_{30}$) + *Anti-Wick Padding* + batas atas maksimum $\le 160\text{ pips}$.

---

## 4. Perubahan 2 September 2026 — 2D Quant-AI Confluence Matrix & Dynamic Sizing Engine

- **Integrasi Matriks Konfluensi 2 Dimensi (`consensus.py` & `risk_engine.py`)**:
  - Menggabungkan Stage 1 Quant Grade (`GRADE_S`, `GRADE_A`, `GRADE_B`) dengan Skor Komposit 3-AI Stage 2:
    $$S = (0.35 \times S_{\text{OpenAI}}) + (0.35 \times S_{\text{Gemini}}) + (0.30 \times S_{\text{DeepSeek}})$$
  - **Tier 1 (`APEX_SUPER_CONVICTION`)**: Quant Grade S + AI $\ge 80\%$ $\rightarrow$ **$1.25\times$ Base Lot** (Split 2 Tiket @ $0.625\times$), $TP_2$ Extended Runner.
  - **Tier 2 (`HIGH_CONVICTION`)**: Quant Grade S + AI $70-79\%$ / Quant Grade A + AI $\ge 80\%$ $\rightarrow$ **$1.00\times$ Base Lot**, $TP_1 + TP_2$.
  - **Tier 3 (`STANDARD_TRADE`)**: Quant Grade A + AI $70-79\%$ $\rightarrow$ **$1.00\times$ Base Lot**, $TP_1 + \text{BEP}$.
  - **Tier 4 (`REDUCED_SCALP`)**: Quant Grade B atau AI $60-69\%$ $\rightarrow$ **$0.50\times$ Half Lot**, Target Ketat **$1.0\times - 1.25\times\text{ATR}$** (atau $1.10\times$ Jarak SL), **$100\%$ Full Exit di $TP_1$**.
  - **Tier 5 (`SKIP / VETO`)**: Quant Grade B + AI $60-69\%$ atau AI $<60\%$ atau Hard Reject $\rightarrow$ **$0.0\times$ Lot (`HOLD`)**.

---

## 5. Perubahan 2 September 2026 — Unifikasi Single-Source Trade Permission Engine

- **Eliminasi Inkonsistensi Dual-Permission**:
  - Menghapus fungsi *legacy* `resolve_permission` yang mengembalikan status `WAIT` keliru pada pair berkonsolidasi netral.
  - Menjadikan **Quant V3 `WaveStateEngine`** (`wave_res.permission` dan `wave_res.is_trade_permitted`) sebagai *Single Source of Truth* (SSOT).
  - Fast Radar kini mengizinkan pemindaian penuh pada pair berstatus **`ARM`** (siaga di area reload/diskon) dan **`GO`** (trigger aktif), sembari tetap mengunci ketat pergerakan kinetik bahaya **`LOCK`** (*Waterfall / Vertical Spike*).
  - Badge Grid Tile 1 CLI kini 100% konsisten: **`● GO`** (Hijau), **`◆ ARM`** (Cyan), **`■ LOCK`** (Merah), **`○ WAIT`** (Abu-abu).

---

## 6. Perubahan 2 September 2026 — Pure Quant Objective Barrier Cluster Calibration

- **Injeksi Level Ekstrim Institusional (`macro_strategic_engine.py`)**:
  - Memasukkan `PWL` (Previous Week Low), `PWH` (Previous Week High), `PDL` (Previous Day Low), dan `PDH` (Previous Day High) ke dalam array `macro_extremes` dengan bobot skor institusional $4.0 - 4.5$.
  - Menyelaraskan lantai Demand Base EURUSD di `PWL 1.15779` dan resisten Supply di `PDH 1.16245`.
- **Koreksi Toleransi Jarak (Skala ATR Murni)**:
  - Menghapus angka *hardcoded* $25\text{p}/40\text{p}$ (`0.25/0.40 * psych_step`) yang sebelumnya membuang semua level dalam radius 25 pips dari harga pasar.
  - `min_chamber_height` diselaraskan ke $\max(0.60 \times \text{ATR H1}, 8\text{ pips})$.
  - `delta_tol` diselaraskan ke $\max(0.35 \times \text{ATR H1}, 3\text{ pips})$.

---

## 7. Perubahan 2 September 2026 — Stacked Multi-Horizon Liquidity Pool Radar & Persistent Zoom Memory

- **Peleburan Kolam Bertumpuk (*Stacked Fortress Bands*) di `macro_dashboard.html`**:
  - Ketika $\ge 2$ level likuiditas saling berdekatan dalam toleransi $\Delta_{\text{merge}} \le 0.25\times\text{ATR}$, engine otomatis meleburnya menjadi **1 Pita Zona Terpadu (*Dense Fortress Band*)**.
  - Dilengkapi label rincian komponen gabungan dan skor kepadatan (misal `🏰 F1 [H4_EMA200 + D1_HVN + BULL_OB] (Score 8.5)`).
- **Jangkauan Multi-Horizon Penuh (Dekat s/d Jauh)**:
  - Memetakan seluruh rentang kolam likuiditas makro (dari $F_1 \dots F_{10}$ di bawah harga hingga $C_1 \dots C_{10}$ di atas harga), termasuk level psikologis, High/Low 2-Year, 52-Week, dan EQL/EQH Multi-Bulan.
- **Persistent Zoom Memory**:
  - Variabel `currentNumBars` disimpan secara persisten di frontend dashboard. Saat pengguna memilih **120 Bars**, rentang lilin tetap dipertahankan tanpa reset ke 350 bar saat berpindah pair di dropdown.
- **Generator Script Produksi**:
  - Menempatkan script generator resmi di **[`scripts/generate_macro_dashboard.py`](file:///c:/Vibe/tradingpartner/scripts/generate_macro_dashboard.py)** dan membuka *tracking* git untuk `macro_dashboard.html`.

---

## 8. Perubahan 2 September 2026 — Multi-TF Candle Tapes Distribution, Anti-FOMO Pending Limit Retest, M2 Pullback Optimization & Dynamic Economic News Schedule

### 🎯 Komponen & Arsitektur Utama:

1. **Distribusi Spektrum Candlestick Multi-Timeframe Independen (`llm_client.py`)**:
   - Menghilangkan *Candlestick Blindspot* antar model dengan mendistribusikan rekaman bar OHLC native MT5 secara spesifik:
     * **OpenAI o4-mini (Chief Macro Strategist)**: Diinjeksi **Tape D1 (5 Bar)** dan **Tape H4 (8 Bar)** untuk memverifikasi tren makro multi-hari.
     * **Gemini 3.1-Flash (Chief Price Action Tactician)**: Diinjeksi **Tape M1 (15 Bar), M5 (24 Bar), M15 (12 Bar), dan H1 (6 Bar)** untuk menganalisis anatomi sumbu, penolakan support/resisten, dan kualitas retest.
     * **DeepSeek V4-Flash (Chief Risk Officer & Arbiter)**: Diinjeksi **Tape H4 (6 Bar), H1 (6 Bar), dan M5 (24 Bar)** untuk audit independen silang (*Pass 2 Cross-Examination*).

2. **Mandat Eksekusi Anti-FOMO & Intersep Breakout Ekstrim (`consensus.py` & `llm_client.py`)**:
   - Menambahkan klausul aturan baku di seluruh prompt juri 3-AI: Jika harga mengalami penembusan (*breakout*) di area ekstrem (Dealing Range $\ge 85\%$ untuk BUY atau $\le 15\%$ untuk SELL), **DILARANG KERAS** menggunakan entri *Market Order*. Model wajib mengusulkan **`buy_limit` / `sell_limit` di garis retest struktural**, atau memilih **`HOLD`**.
   - **Hard Anti-FOMO Intercept (`consensus.py`)**: Jika kandidat berstatus Breakout di area ekstrem namun output AI menghasilkan *Market Order*, engine konsensus otomatis mengonversinya menjadi **`BUY_LIMIT` / `SELL_LIMIT`** pada level jangkar $F_1 / RBS$ atau $C_1 / SBR$.

3. **Optimalisasi Mekanisme 2 (Trend-Aligned Pullback & Delayed Retest) (`market_scanner.py`)**:
   - **Pembebasan Hambatan Equilibrium ($45\% - 55\%$)**: Menghapus pemblokiran kaku pada mid-chamber di M2 jika harga sedang menyentuh level struktural valid (Order Block, FVG, EMA50 Dinamis, atau Lantai MSE $F_1$). Mengizinkan setup M2 aktif di rentang diskon sehat ($\le 55\%$ untuk BUY, $\ge 45\%$ untuk SELL).
   - **Standardisasi Zona Aksi ($0.35\times\text{ATR}$)**: Memperluas toleransi zona aksi dari $0.20\times\text{ATR}$ menjadi $0.35\times\text{ATR}$ (selaras dengan M1 dan M3).

4. **Injeksi Kalender Berita Ekonomi Live Otomatis (`llm_client.py` & `market_scanner.py`)**:
   - Mengintegrasikan helper `_get_symbol_news_context(sym, candidate)` yang otomatis menarik rilis berita berdampak tinggi dari `economic_calendar.calendar.get_context(symbol=sym)` jika data di objek kandidat kosong.
   - Menyuntikkan jadwal berita ekonomi terkini secara real-time ke **ketiga model AI** (OpenAI, Gemini, DeepSeek), memastikan tidak ada lagi kebutaan model terhadap event suku bunga / NFP (seperti BoC Rate Statement).

5. **Ekspor Full Prompt Markdown (`docs/prompt/`)**:
   - Menyediakan dokumen prompt lengkap (verbatim) untuk setiap model di direktori `docs/prompt/`:
     * [`docs/prompt/openai_prompt.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/prompt/openai_prompt.md)
     * [`docs/prompt/gemini_prompt.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/prompt/gemini_prompt.md)
     * [`docs/prompt/deepseek_prompt.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/prompt/deepseek_prompt.md)

## 9. Perubahan 2 September 2026 — Dokumentasi: Sinkronisasi Realita SL/TP + RFC 11 Zone Confluence Engine

### 📄 Dokumentasi (tanpa perubahan perilaku kode)

1. **Koreksi drift dokumentasi SL/TP** (`AGENTS.md` & komentar `config.py`):
   - AGENTS.md sebelumnya menuliskan ceiling statis "FX ≤ 160 pts / JPY ≤ 200 pts" dan floor FX "0.68×ATR H1" — **tidak cocok dengan kode aktual**.
   - Realita `consensus.py:155-206` (2 Sep 2026): floor FX = $\max(2\times\text{spread}+15, 0.50\times\text{ATR H1})$ (`LLM_FX_FLOOR_ATR_MULT=0.50`), floor JPY = $\max(2\times\text{spread}+20, 1.00\times\text{ATR M30})$, fallback 250 pts kalau ATR gagal; **ceiling dinamis anti-runaway** = $2.5\times\text{ATR}$ FX/JPY/Gold (fallback 350/350/800 pts) dan $1.8\times\text{ATR}$ BTC (fallback 45000) — hardcode, bukan dari `.env`.
   - Komentar `config.py` (3 lokasi) "1.5x ATR H1" → "0.50x ATR H1".
   - Verifikasi: tidak ditemukan sisa logika ceiling statis 160/200 pts di seluruh `src/` (`max_sl` hanya dari `atr × 2.5/1.8`).

2. **RFC 11: Zone Confluence Engine (ZCE)** — [`docs/plans/ZONE_CONFLUENCE_ENGINE_SPEC.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/plans/ZONE_CONFLUENCE_ENGINE_SPEC.md) & [`docs/plans/ZONE_CONFLUENCE_ENGINE_IMPLEMENTATION_PLAN.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/plans/ZONE_CONFLUENCE_ENGINE_IMPLEMENTATION_PLAN.md):
   - Peta zona multi-TF × multi-horizon (OB/FVG/SBR/RBS/DBD/RBR/EQH/EQL/FRVP/psych/macro extremes) + skoring konfluensi + scale ladder 50–500 + flag `SCALE_CONFLICT` + deteksi `COLD`/`VACUUM`.
   - Serah-terima dari MSE: Blok A/B (deteksi & pemilihan zona, baris 464–1077) → ZCE; MSE tetap pemilik state machine, arah, izin, eksekusi.
   - **Keputusan terkunci user**: J1 horizon = penguat bobot (bukan saksi konfluensi); J2 bobot default + forward test; payload LLM per peran (Gemini raw OHLC banyak M1–M30, OpenAI sedikit, DeepSeek zone table lengkap); refresh rotasi ≤ 5 menit.
   - Fase 3 rencana ditambah: SL/TP berbasis anchor struktural ZCE (`consensus.py`) — `SL_MAX_ATR_MULT` configurable, skip `ANCHOR_TOO_WIDE`, fallback statis → reject. Menunggu persetujuan batch pertama eksekusi.

---

## 10. 2 September 2026 — Eksekusi Fase 1-2 & Task #7 ZCE (Zone Confluence Engine)

> Implementasi engine ZCE + integrasi MSE + gate SL/TP anchor struktural. Seluruh perubahan **flag-gated**: `ZCE_ENABLED=false` + `ZCE_MODE=shadow` (default) → perilaku produksi identik (diverifikasi 86 test pass).

### Fase 1: Engine ZCE + Unit Test (10/10 PASS)
- `src/analytics/zone_confluence_engine.py` (BARU): grid 6-TF x multi-horizon, merge primitives (toleransi max(0.25xATR H1, 6x point)), finalize cluster (J1 greedy dedupe), freshness stamping (touch count, COLD > 21 hari), elect walls (F1/C1 chamber >= 0.60xATR / 8 pips), scale ladder (pos_50/pos_250), suggest method, readiness, build zone table text.
- `tests/test_zone_confluence_engine.py` (BARU): 10 test sintetik (merge, J1 no double-count, width/grade, ladder LOCAL_DISCOUNT_MACRO_PREMIUM, COLD flag, E2E) — 10/10 PASS.

### Bug Fix Parity: Eksponen Konversi Pips di `_elect_walls`
- Sebelum: `min_ch = max(0.60*ATR, 8.0*10^(-digits+3))` → untuk 5-digit menghasilkan **800 pips** (bukan 8) → SEMUA pasangan F1/C1 dianggap terlalu dekat → `F1=None` → wall override mati diam-diam.
- Sesudah: `8.0*10^(-digits+1)` → 5-digit = 0.0008 (8 pips), JPY 3-digit = 0.08. Parity live EURUSD kini menghasilkan F1/C1 valid.

### Fase 2: Hook MSE (Zero Consumer Break)
- `src/analytics/macro_strategic_engine.py`: parameter `zce_walls` di `compute_directive`/`get_directive`; blok override menimpa `immediate_ceiling_c1`/`immediate_floor_f1`/deep/layered SEBELUM Chamber Metrics → state machine & branch konsisten.
- Parity live EURUSD (read-only): ZCE C1=1.16108/F1=1.15780; MSE baseline C1=1.16153/F1=1.15845; MSE+ZCE C1/F1 = persis ZCE → override applied: True.
- `_refresh_zce_rotation` di `market_scanner.py` + `zce_walls` diteruskan ke `get_directive` saat mode legacy/full.

### Task #7: SL/TP Anchor Struktural ZCE (`consensus.py`) — flag-gated
- `SL_MAX_ATR_MULT` configurable dari `.env` (default 2.5) menggantikan hardcode `atr_points * 2.5` di ceiling XAU/JPY/FX. BTC tetap 1.80/45000.
- Mode ZCE legacy/full: SL anchor > ceiling → SKIP `ANCHOR_TOO_WIDE` (bukan clamp yang memarkir SL di tengah struktur); ATR gagal → REJECT `ATR_UNAVAILABLE` (bukan fallback statis 350/800).
- Floor ATR + R:R gate invariant (tidak diubah).
- `tests/test_zce_sltp_anchor.py` (BARU): 4 test sintetik (clamp lama di mode off; ANCHOR_TOO_WIDE; ATR_UNAVAILABLE; fallback statis mode off) — 4/4 PASS.

### Verifikasi
- `compileall config.py src main.py` → OK.
- `pytest tests/ -q` → **86 passed, 6 failed (pre-existing, bukan dari ZCE)**. Enam kegagalan (test_dashboard x4, test_prompt_v2 x2) diverifikasi pre-existing via worktree HEAD bersih `0ecf652` — modul `dashboard` lama & ekspektasi voting 2/3 vs aturan unanimouse 3/3 (sengaja tidak disentuh sesuai instruksi).

---

## 11. 2 September 2026 — Aktivasi ZCE Mode FULL untuk Test Live Cent

Perintah user: aktifkan ZCE tanpa shadow agar bisa langsung ditest di akun **live cent** (bukan akun live utama).

- `.env`: `ZCE_ENABLED=true`, `ZCE_MODE=full` (sebelumnya `false`/`shadow`).
- Definisi mode (dari RFC): `legacy` = window single-horizon identik MSE (parity); `full` = elekt dinding dari klaster grid multi-horizon (ZCE sesungguhnya). Tidak ada kode yang membedakan keduanya saat ini — `market_scanner.py` meneruskan `zce_walls` ke `get_directive` di kedua mode bila `ZCE_ENABLED`.
- Konsekuensi aktif (dihitung & diuji): dinding C1/F1 ZCE menggantikan dinding internal MSE → state machine & SL/TP mengikuti peta zona 6-TF; `_apply_sltp_rules` di jalur ZCE menolak SL > ceiling (`ANCHOR_TOO_WIDE`) dan menolak saat ATR gagal (`ATR_UNAVAILABLE`) tanpa fallback statis.
- **Regresi test yang diperbaiki**: `ZCE_ENABLED=true` global membuat 2 test legacy (yang menguji jalur SL/TP non-ZCE tanpa data MT5 live) gagal. Solusi: patch `config.ZCE_ENABLED=False` + `ZCE_MODE=shadow` di `test_confluence_and_thesis_invalidation.py::test_tight_sltp_rules_for_reduced_scalp` dan `test_market_scanner.py::test_consensus_apply_sltp_symbol_specific` — test tetap menguji jalur legacy deterministik, logika produksi tidak disentuh.
- Verifikasi live read-only (akun terhubung, tanpa order):
  - Parity EURUSD mode full: override applied=True, state MSE ikut dinding ZCE.
  - `_refresh_zce_rotation` 6 simbol: 2.5s; 4 simbol: 0.3s → 26 simbol penuh ~2-11s per rotasi, aman untuk siklus 60 detik.
  - `scan_all` 4 simbol: 1.3s, 0 exception, 0 kandidat (normal — setup A+ tidak muncul tiap cycle).
- Suite: `pytest tests/ -q` → **86 passed, 6 failed pre-existing** (sama seperti sebelum aktivasi, tidak ada regresi baru).
- **Catatan keselamatan**: bot tetap membaca akun dari `.env` (login live). Untuk test di akun live cent, pastikan `.env`/terminal MT5 diarahkan ke akun cent yang dimaksud + `DRY_RUN` tidak diubah tanpa persetujuan.

---

## 12. 2 September 2026 — Koreksi AGENTS.md (Referensi `wave_state.py`/CSM) + Spec Verifikasi Koordinat ZCE/MSE

### 🧹 Koreksi AGENTS.md (perintah: "perbaiki agents md")

Latar: AGENTS.md masih mereferensikan `src/indicators/wave_state.py` (file sudah dihapus) sebagai engine CSM/wave state — menyesatkan pembaca & agent baru.

1. **Tabel arsitektur**:
   - Baris `market_scanner.py` diperluas: `permission_state` dihitung DI SINI dari mapping MSE action tier (`FULL_ALLOW→GO/ARM`, `TP1_ONLY_SCALP→ARM`, `WATCH_ONLY→WATCH`, `HARD_BLOCK→LOCK`) + gate arah terpadu `_is_direction_allowed()` (Macro Bias + CSM Flow Opposition + Systemic Basket Lock) + meneruskan `zce_walls` ZCE ke MSE.
   - `wave_state.py` diganti `wave_regime.py` (regime & umur kompresi — pengganti resmi).
   - `currency_strength.py` diklarifikasi: **modul mandiri** (8 mata uang dari 7 USD majors, cache 30 detik), dibaca scanner/llm/UI — BUKAN bagian MSE/ZCE.
   - Ditambah row `zone_confluence_engine.py` (status `ZCE_ENABLED=true`, `ZCE_MODE=full`, test akun live cent).
2. **Alur cycle langkah 2**: "cek Wave State permission (`GO/ARM` only)" → "cek `permission_state` hasil mapping MSE action tier (`FULL_ALLOW→GO/ARM` only; `HARD_BLOCK`/`WATCH_ONLY` = 0 token) + gate arah terpadu `_is_direction_allowed()`".
3. **Entri changelog historis 25 & 45**: tidak dihapus (catatan kronologis tetap akurat), ditambah anotasi *italik* bahwa model FSM Wave State lama (state `EXPANSION_WAIT_BULL`/`WATERFALL_LOCK`/dst.) sejak 1 September telah dilebur ke MSE Barrier State Machine + action tier 5-Tier (lihat entri 40 & 48) — mencegah pembaca mencari modul yang sudah tidak ada di kode aktif.

### 🧭 Klarifikasi Arsitektur CSM vs MSE/ZCE (dari penelusuran kode)

- **Zero coupling**: `macro_strategic_engine.py` dan `zone_confluence_engine.py` TIDAK mengimpor `currency_strength`. `action_tier`, `macro_bias_score`, dinding C1/F1, dan SL/TP anchor **0% dipengaruhi CSM**.
- CSM hanya dikonsumsi di `market_scanner.py`: (a) baris 705 `csm_delta_val` → macro dict (info/prompt); (b) baris 1064 `evaluate_systemic_basket_lock` di dalam gate `_is_direction_allowed()` yang dipakai M1/M2/M3.
- **Hierarki keputusan aktual**: MSE = kompas & tier → ZCE override dinding (mengubah tier & SL/TP) → CSM = **veto eksternal di gate** (allow/block arah, TIDAK mengubah koordinat). Urutan veto gate: (1) Systemic Basket Lock CSM ±18–20 → `HARD_BLOCK` bahkan sebelum MSE dicek; (2) MSE tier gate; (3) circuit breaker + forbidden traps MSE; (4) CSM Flow Opposition (delta ≤ −1.0 lawan BUY / ≥ +1.0 lawan SELL) → block hanya jika tidak aligned MSE; (5) resolusi tier: aligned → `FULL_ALLOW`, counter → `TP1_ONLY_SCALP`, netral → `REDUCED_CONFIDENCE`.
- **Shadow yang masih hidup**: Dual-Basket Confluence & Dispersion Matrix di `currency_strength.py` — sengaja informational-only (hanya ke dossier LLM), tidak menyentuh hard gate Stage 1. Jalur promosi ke hard gate = titik yang sama (`_is_direction_allowed`), bukan MSE/ZCE.

### 📐 Spec Verifikasi Koordinat ZCE/MSE (Lapis 1–3) — `docs/plans/ZCE_COORD_VERIFICATION_SPEC.md`

Latar: bug eksponen pips (`8.0×10^(-digits+3)` = 800 pips, bukan 8 pips) yang baru diperbaiki membuktikan bahwa "baca koordinat" bisa salah DIAM-DIAM tanpa error — perlu verifikasi eksplisit level fisik, bukan asumsi.

- Spec siap-eksekusi untuk agent lain (bukan perubahan produksi): script `scratch/verify_zce_coords.py` read-only (0 order MT5), 8 simbol uji (major/JPY/cross/CHF/NZD).
- Konvensi unit WAJIB dari `atlas_dna.py` + `symbol_info` (EURUSD 5-digit: 100 poin = 10 pips, `pip_div = 10`) — tanpa hardcode.
- **Lapis 1 Parity**: dump F1/C1/F2/C2 (MSE-baseline vs ZCE-map vs MSE+ZCE) + jarak pips + grade → spot-check manual 3 simbol di chart MT5 (level harus = dinding fisik nyata).
- **Lapis 2 Invariant (hard assert, 0 toleransi)**: INV-1 `F2 < F1 < harga < C1 < C2`; INV-2 jarak ≤ 2.0×ATR_H1 (jebakan bug 800-pips); INV-3 deep layer ≥ 0.5×ATR_H1; INV-4 override benar-benar applied; INV-5 tier konsisten dengan dinding valid. 1 FAIL = BUG → stop, lapor planner.
- **Lapis 3 Hierarki TF**: horizon asal tiap klaster (`horizon_max`) — mikro (M30/H1) bersarang di dalam makro (D1/W1/MN1); loncat horizon = FAIL, konflik skor = WARN.
- Kriteria lolos: INV 100% + spot-check 3/8 valid → baru layak Lapis 4 (validasi eksekusi live cent ≥7 hari/≥60 sampel).
- Catatan agent di spec: panggil `compute_directive` langsung (bukan `get_directive`) agar tidak kena cache; baca definisi dataclass `ZoneMapResult`/`MacroStrategicDirective` sebelum akses field.

---

## 13. 2 September 2026 — Eksekusi Verifikasi Koordinat ZCE/MSE Lapis 1–3 + FIX BUG KRITIS Pemilihan Dinding (INV-2)

### 🚨 Hasil Uji Awal (eksekutor, sebelum fix)

Uji live 8 simbol di akun **VTMarkets-Live 3** → **TIDAK LOLOS, STOP sesuai spec**:

| Invariant | Hasil |
|---|---|
| INV-1 (Ladder `F2<F1<harga<C1<C2`) | 7/8 PASS |
| INV-2 (Proximity ≤ 2.0×ATR) | **1/8 PASS (7 FAIL)** 🚨 |
| INV-3 (Deep spacing ≥ 0.5×ATR) | 6/8 PASS |
| INV-4 (Override applied) | 8/8 ✅ |
| INV-5 (Tier konsisten) | 8/8 ✅ |
| INV-H1/H2 (Hierarki TF) | 8/8 ✅ |

Gejala: level "kabur jauh" — EURUSD C1=1.16494 (6.1×ATR), GBPUSD C1=1.35811 (6.2×ATR), USDJPY C1=160.266 (5.8×ATR), EURJPY F1=182.261 (7.9×ATR).

### 🔍 Akar Masalah 1 — `_elect_walls` membuang zona yang MERENTANGI harga

`zone_confluence_engine.py:378-381`:
```python
floors = [c for c in clusters if c.band_high < cur_price - eps]     # salah
ceilings = [c for c in clusters if c.band_low > cur_price + eps]
```
Klaster yang berisi harga (`band_low ≤ harga ≤ band_high`, contoh EURUSD cluster 1.15727–1.16000 berisi OB+FVG+EQL+Psych) gagal kedua kondisi → **dieliminasi total** → ZCE melompat ke klaster jauh berikutnya.

**Fix**: zona merentangi harga TIDAK dibuang — menyumbang DUA dinding: `band_low` sebagai floor-edge & `band_high` sebagai ceiling-edge. Sorting diubah dari `-band_high` → **jarak ke harga naik** (mencegah salah urut saat zona merentangi punya band_high di atas harga). Verifikasi awal setelah fix: F1 mayoritas dekat, tetapi pola baru muncul.

### 🔍 Akar Masalah 2 — Dinding immediate > cap jarak (INV-2)

Pola baru: **C1 melompat jauh saat ZCE tidak punya zona konfluensi dekat di sisi atas** (USDJPY psych 159.0 ada di MSE tapi tidak tertangkap ZCE; C1 ZCE terdekat = 160.266 = 5.9×ATR). Ini bukan bug filter lagi — memang gap zona.

**Fix**:
1. `_elect_walls`: parameter baru `max_imm_atr` (default **2.0×ATR_H1**, spec INV-2). Sisi immediate > cap → di-None-kan → tidak layak override.
2. Override ZCE→MSE (`macro_strategic_engine.py`) diubah dari guard **penuh** (`F1 & C1 keduanya non-None`) menjadi **override PER-SISI**: ZCE menimpa hanya sisi yang valid; sisi kosong TETAP memakai baseline MSE (`FALLBACK_PSYCH`/struktur internal). Sebelumnya fallback penuh justru memilih sisi MSE yang lebih jauh (kasus USDJPY: ZCE F1=158.5 / 1.3×ATR bagus dibuang, MSE F1=157.974 / 3.5×ATR yang dipakai).
3. Guard di `market_scanner.py`: terima `zce_walls` jika **minimal SATU sisi** non-None (sebelumnya harus dua-duanya).
4. Deep layer F2/C2: bukan lagi index `[1]` — dipilih layer pertama dengan jarak **≥ 0.5×ATR_H1** dari F1/C1 (INV-3, kasus GBPCHF F1/C1 nempel).

### ✅ Hasil Akhir (re-run live 8 simbol)

**INV PASS: 40/40 | BUGS: 0** — INV-1..5, INV-H1/H2 semua 100%. Dinding efektif kini campuran terbaik: contoh USDJPY `F1:ZCE 158.5 + C1:MSE 158.989` (1.2×/0.8×ATR), AUDUSD `F1:ZCE 0.71631 + C1:MSE 0.7175`. Laporan: `scratch/verify_zce_coords_report.md`.

**Catatan penting konversi (koreksi laporan eksekutor)**: jarak "setelah fix" di laporan awal salah konversi 10× — F1=1.15727 jarak sebenarnya **18.4 pips** (bukan 1.8) = 1.92×ATR (nyaris gagal INV-2), C1=1.16000 = **8.9 pips** (bukan 0.8). Klaim "100% PASS setelah fix 2 baris" TIDAK valid; fix sebenarnya butuh override per-sisi + cap jarak + deep-layer spacing, dan hanya terbukti lewat re-run verifikasi (bukan asumsi).

### 🧪 Regresi

- Unit test terkait: 22/22 PASS (`test_zone_confluence_engine`, `test_zce_sltp_anchor`, `test_macro`, `test_time_decay_and_vol_regime`, `test_symbol_rotation`).
- Full suite: **86 passed + 6 failed pre-existing** (test_dashboard ×4, test_prompt_v2 ×2) — identik baseline, tanpa regresi baru.
- File berubah: `src/analytics/zone_confluence_engine.py` (fix elect walls + cap + deep-layer), `src/analytics/macro_strategic_engine.py` (override per-sisi), `src/analytics/market_scanner.py` (guard 1-sisi), `scratch/verify_zce_coords.py` + report (update verifier dinding efektif).

### ⏭️ Langkah berikut
- **Lapis 4 (validasi eksekusi live cent ≥7 hari/≥60 sampel)** kini LAYAK dijalankan — syarat koordinat sudah terpenuhi.
- **Runbook Operasional Lapis 4**: Panduan observasi log-driven live cent tersedia di [`docs/plans/ZCE_LAPIS4_LIVE_VALIDATION_RUNBOOK.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/plans/ZCE_LAPIS4_LIVE_VALIDATION_RUNBOOK.md) dengan penanda audit per-trade `[ZCE-AUDIT]` di `main.py`.
- Kandidat follow-up: investigasi kenapa ZCE tidak menangkap psych station dekat (USDJPY 159.0) yang justru ditemukan MSE — berpotensi memperluas cakupan override ZCE di masa depan.

---

## 14. 2 September 2026 — Fix Koneksi ZCE→Radar: Stale Cache + Resync Deep Target (Patch #1 & #2)

**Konfirmasi independen 3 temuan Gemini** (sebelum eksekusi, verifikasi baca kode langsung):
1. **Stale Cache Disconnect** — BENAR: `macro_cache` hanya di-refresh saat kosong/`>3600s` dan `_refresh_zce_rotation` hanya menulis `self._zce_maps` (tidak pernah `macro_cache`); cold start/rebuild pertama setelah dead zone → seluruh cache dibangun tanpa `zce_walls` (ZCE mati total ±1 jam, basi ≤60 mnt di steady state).
2. **F2 inversion** — SEBAGIAN: jalur yang dikutip Gemini (`market_scanner.py:947`) sudah disembuhkan oleh enforcement monotonik 1146-1149 + eff-blend 837-840 (29ab6fb); sisa edge nyata hanya di `deep_target_floor_f2/deep_ceiling_c2` (raw) saat ZCE F1 override lebih dalam dari deep baseline & ZCE deep F2 kosong → deep target ter-inversi terhadap F1/C1.
3. **SCALE_CONFLICT → gate** — SUBSTANSI BENAR, detail salah: token `"SCALE_CONFLICT"` tidak pernah di-assign (nilai riil `LOCAL_DISCOUNT_MACRO_PREMIUM`/`LOCAL_PREMIUM_MACRO_DISCOUNT`); cek di `_suggest_method` adalah dead code. Tidak di-wire (keputusan: JANGAN di-wire ke gate sebelum tervalidasi).

**Patch #1 — Stale Cache Disconnect** (`market_scanner.py`, `config.py`, `.env`):
- `update_macro_context`: hour-gate → **elapsed-gate** `_zce_refresh_due_seconds()` (900s saat ZCE legacy/full; `MACRO_STRATEGIC_REFRESH_SECONDS`/3600s default).
- `_build_single_macro_context`: bila peta ZCE simbol belum ada di `_zce_maps` → **compute inline** (`_compute_zce_map_for`, engine lokal per thread) → cache TIDAK PERNAH dibangun tanpa dinding ZCE (cold start, boot `force`, Senin pagi).
- `_refresh_zce_rotation`: refactor ke helper `_compute_zce_map_for()` + parameter `full_sweep=True` → refresh SEMUA simbol tepat sebelum rebuild macro_cache (menggantikan peta basi lintas weekend/dead zone).
- `scan_fast_radar`: gate refresh dinamis — saat due: **full-sweep ZCE dulu, baru rebuild**.
- Konfigurasi baru: `ZCE_REFRESH_INTERVAL_SECONDS` (config.py default 900, `.env` = 900).

**Patch #2 — Resync Deep Target vs F1/C1 Override** (`macro_strategic_engine.py` 1151-1184):
- Setelah enforcement monotonik: bila `deep_floor_f2 >= floor_f1` (ter-inversi) → resync `deep_floor_f2 = F1 - max(psych_step_macro, 1.5×ATR)` + snap ke cluster struktural terdekat (mirror baseline 941-960); simetris untuk `deep_ceiling_c2`.
- Pulihkan `floor_f2`/`ceiling_c2` = None yang sempat ditetapkan enforcement karena deep lama ter-inversi → tangga retest tetap tersedia.

### 🧪 Regresi
- `py -m py_compile` ketiga file (scanner, MSE, config) hijau.
- Full suite: **86 passed + 6 failed pre-existing** (test_dashboard ×4, test_prompt_v2 ×2) — identik baseline, tanpa regresi baru.
- File berubah: `src/analytics/market_scanner.py`, `src/analytics/macro_strategic_engine.py`, `config.py`, `.env`, `AGENTS.md`.

### ⏭️ Langkah berikut
- #3 (wire konflik ZCE ke gate) sengaja TIDAK dieksekusi — sinyal belum pernah aktif & belum divalidasi; berisiko memangkas setup tanpa bukti edge.
- Observasi Lapis 4 live cent lanjut; pantau log `[ZCE]` + dinding override agar umur peta ≤15 mnt.

---

## 15. 3 September 2026 — M4 SYSTEMIC FLOW CONTINUATION + Circuit Breaker Calibration

### 🎯 Latar Belakang (Studi #1 & #1b Mirror)
- **Studi #1 & #1b**: Systemic currency flow (rolling 24-bar H1 log-return warm 720, z >= 1.5) -> breakdown swing 120-bar -> pending limit retest di level. Validasi empiris 15 tahun FBS (N=650, P(win) 59.4% vs 51.8% control, chi-sq=8.74). SL struktural 0.45xATR, TP 1.1R. Exclude USDJPY (48.1% < netral).

### 🔬 Implementasi & Penyelarasan Menyeluruh (/grill-me)
1. **Parameter M4**: `M4_ENABLED=True`, `M4_TRIGGER_Z=1.5`, `M4_CONT_Z=0.75`, `M4_FLOW_LOOKBACK_BARS=24`, `M4_LOOKBACK_BARS=120`, `M4_MIN_EPISODE_BARS=6`, `M4_MIN_GAP_BARS=240`, `M4_SL_ATR_MULT=0.45`, `M4_TP_R_MULT=1.1`, `M4_PENDING_EXPIRY_MINUTES=120`.
2. **All-or-Nothing Position Management**: Posisi M4 di `position_manager.py` dibebaskan dari Partial Close, BEP, dan Trailing Stop — menjaga integritas target struktural 1.1R, sembari mempertahankan Pre-Rollover Shield & Time-Decay Stagnation.
3. **Thesis Invalidation Bypass**: Pending M4 dikecualikan dari pembatalan bias MSE D1/H4 di `position_manager.py:audit_pending_orders_thesis()`.
4. **Fix Fatal Bug Symbol Collision**: `cand_sym = getattr(candidate, 'symbol', None) or config.SYMBOL` di seluruh alur konsensus multi-LLM, menghapus risiko pembatalan cross JPY/EUR akibat salah banding harga vs GBPUSD.
5. **Unifikasi Filter Sesi Tokyo (08:00 - 14:00 WIB)**: `TOKYO_PROVEN_SYMBOLS` usang dihapus. `is_symbol_allowed_for_session` diselaraskan 100% dengan `config.is_asian_session_pair(symbol)`. Semua pair ber-driver aktif Asia/Pasifik (mengandung JPY, AUD, atau NZD) diizinkan; pair tanpa JPY/AUD/NZD dikunci.
6. **Fix Silent TypeError di `_m4_refresh_z` (`market_scanner.py:414`)**:
   - Mengganti `part.mean(axis=1, min_periods=minp)` (di mana `DataFrame.mean()` tidak menerima parameter `min_periods`) dengan `part.mean(axis=1).where(part.count(axis=1) >= minp)`.
   - Memulihkan 27 episode flow aktif di scanner.
7. **Kalibrasi Threshold Systemic Currency Basket Circuit Breaker ke 35.0 bps**:
   - Menaikkan `SYSTEMIC_BASKET_USD_THRESHOLD`, `JPY_THRESHOLD`, `CROSS_THRESHOLD`, dan `SPREAD_THRESHOLD` dari 2.0 (20 bps) ke 3.5 (35 bps) di `config.py` dan `.env`.
   - Membebaskan pergerakan tren harian wajar (USD -33.4 bps dan EUR -21.8 bps) agar setup trend-following (seperti GBPUSD SELL M4) dapat dieksekusi, sembari tetap mengunci ketat counter-trend pada shock ekstrem (seperti JPY Surge +67.5 bps).
   - Seluruh unit test suite 75 tests lulus 100% PASS.
8. **Periodic Quant Funnel Snapshot Logger (5-Menit)**:
   - Menambahkan `_log_periodic_quant_snapshot()` di `market_scanner.py` yang mencatat ringkasan spasial 26 pair (`[ZCE F1/C1 | MSE State & Tier | Dealing Range Pos | M4 Standbys]`) tiap 300 detik ke `data/gate_debug.log` (<0.0005 detik, 0 token, 0 beban MT5).
9. **Graceful MT5 Shutdown (`atexit` Protection)**:
   - Menambahkan registrasi `atexit.register(_safe_mt5_shutdown)` di `src/core/mt5_connector.py`.
   - Menjamin bahwa saat proses Python dimatikan via `Ctrl+C` atau selesai, koneksi terminal MT5 ditutup secara bersih dan tidak pernah meninggalkan *zombie process headless* (`terminal64.exe` tanpa GUI window) yang mengunci file disk dan membuat laptop ngelag.
10. **Penyelarasan Menu & Command Telegram (`telegram_bot.py`)**:
    - `/macro [pair]`: Sekarang memprioritaskan pembacaan direktif dari `scanner.macro_cache` sehingga level lantai F1 dan plafon C1 di Telegram **100% sinkron dengan dinding konfluensi ZCE** yang digunakan oleh bot eksekusi live.
    - `/macro all`: Terhubung langsung ke cache scanner untuk menghasilkan ringkasan kompas 26 pair instan (<1ms).
    - Macro Picker Menu: Ditambahkan tombol inline `🧭 [ All 26 Pairs Compass ]` (memanggil `cmd:macro_ALL`), serta mengganti pair non-aktif `BTCUSD` dengan pair FX aktif (`EURCHF` dan `AUDCAD`).
    - `/levels` & `/smc`: Diperkaya dengan tampilan **🏰 ZCE FORTRESS WALLS** (F1 Lantai dan C1 Plafon multi-TF beserta Grade G2/G3 dan Fortress Tag).
11. **Eliminasi False-Positive Gate Stacking (M3 Runway & M4 Contextual Trap Veto)**:
    - **Diagnosa Masalah**: Audit `data/gate_debug.log` membuktikan bahwa filter kaku $dr\_pos < 0.28$ (disalin dari M2 Pullback) membunuh 100% setup M3 Breakdown Retest pada broken support (seperti EURCAD menembus support dan retest SBR di `1.60278` dengan target lantai Daily `1.60032`). Selain itu, trap MSE untuk harga pasar (`Do NOT short into support at F1`) memblokir membabi buta Limit Order M4 yang berada di plafon (seperti `CADJPY SELL_LIMIT @ 113.816` dengan target $F_1$ `113.302`).
    - **Perbaikan Kode (`market_scanner.py`)**:
      - `_is_direction_allowed(target_dir, setup_label, entry_price=None)`: Menambahkan *Contextual Limit Awareness*. Jika limit order sell berada $\ge 0.40\times\text{ATR}$ di atas support $F_1$, trap larangan short di support diabaikan karena $F_1$ adalah Take Profit target. Sebaliknya untuk buy limit di bawah resisten $C_1$.
      - **M3 Breakdown Retest Runway**: Mengganti filter kaku $dr\_pos < 0.28$ dengan perhitungan Runway ke lantai target: $\text{Runway to } F_1 = (target\_sup - \text{immediate\_floor\_f1}) \ge 0.80\times\text{ATR}_{H1}$. Peluang breakdown retest dengan ruang gerak lebar kini diizinkan.
12. **Perbaikan NameError `zce_meta` & Validasi Live Setup EURCAD (`market_scanner.py`)**:
    - **Diagnosa Masalah**: Setelah filter runway M3 membuka blokir pada EURCAD, kode eksekusi mencapai tahap pembentukan `CandidateSetup`. Di sana terjadi `NameError: name 'zce_meta' is not defined` karena dictionary `zce_meta` yang dibuat di `_build_macro_context()` lupa disimpan ke return dict `macro`, dan belum diinisialisasi di scope `scan_all()`.
    - **Perbaikan Kode**:
      - Menyimpan `'zce_meta': zce_meta` ke dalam dictionary hasil return `_build_macro_context()`.
      - Menginisialisasi `zce_meta = macro.get('zce_meta') or {...}` dengan fallback lengkap per-simbol di awal pemrosesan `scan_all()`.
13. **Penyelarasan Mid-Chamber Gate untuk Limit Order Retest (`market_scanner.py`)**:
    - **Diagnosa Masalah**: Trap MSE `Do NOT execute market orders in mid-chamber consolidation zone` menargetkan market order spekulatif di tengah kamar. Namun karena omisi kata kunci `"BREAKOUT"` di baris 1485 & 1507, Pending Limit Order M3 Breakout Retest (seperti pada CADJPY di range 73%) diblokir secara keliru padahal setup memiliki level SBR struktural dan runway ke lantai target.
    - **Perbaikan Kode**:
      - Menyatukan definisi `is_limit_retest = any(k in setup_label.upper() for k in ("PULLBACK", "SYSTEMIC", "BREAKOUT", "RETEST"))`.
      - Membebaskan seluruh limit order retest ber-runway dari pemblokiran `INACTION_ZONE` dan trap `MID-CHAMBER / CONSOLIDATION ZONE`. Market order liar tetap diblokir 100%.
    - **Verifikasi Kuantitatif Langsung**:
      - Radar mendeteksi **6 setup A+ terkurasi** dengan runway lebar dan arah selaras CSM:
        * `USDJPY-ECNc` SELL LIMIT @ 156.3505 (CSM Delta -22.41)
        * `EURAUD-ECNc` SELL LIMIT @ 1.61567 (CSM Delta -4.40)
        * `EURCAD-ECNc` SELL LIMIT @ 1.60281 (CSM Delta -5.82)
        * `GBPAUD-ECNc` SELL LIMIT @ 1.87932 (CSM Delta -6.26)
        * `AUDCHF-ECNc` BUY LIMIT @ 0.58142 (CSM Delta +0.39)
        * `AUDCAD-ECNc` SELL LIMIT @ 0.99216 (CSM Delta -1.42)
      - Full test suite: **75/75 tests PASSED (100% OK)** dalam 1.447s.
14. **Penyelarasan Konteks ZCE Retest Chamber pada Prompt Gemini (`llm_client.py`)**:
    - **Diagnosa Masalah**: Gemini 3.1-Flash (Lead Price Action Tactician) menolak setup EURCAD SELL LIMIT dengan flag `LIQUIDITY_TRAP` karena prompt hanya menyajikan `Dealing Range Position: 2.5% (DISCOUNT)`. Mengacu pada aturan baku SMC, melakukan short di area diskon 2.5% dianggap perangkap ritel. Padahal secara struktural, harga sedang melakukan retest di plafon kamar ZCE lokal ($C_1 = 1.60306$, posisi 89%) menuju lantai $F_1 = 1.60032$.
    - **Perbaikan Kode**:
      - Menginjeksi `- Local ZCE Execution Chamber: Floor F1 = ... │ Ceiling C1 = ... │ Local Position: ...%` ke dalam blok Context Gemini.
      - Memperjelas Anti-FOMO Gate (Aturan 2) bahwa untuk Limit Retest Order (M2, M3, M4), retest di broken support (SBR) pada plafon kamar lokal adalah kelanjutan tren yang sah, bukan jebakan diskon.
      - Menjaga spesialisasi 100% utuh: Gemini tetap fokus penuh mengaudit micro tape (M1/M5/M15/H1), wick rejection, dan displacement, sementara OpenAI fokus pada makroekonomi D1/H4.
    - **Verifikasi**:
      - `py_compile` bersih tanpa error.
      - Full test suite: **75/75 tests PASSED (100% OK)**.
15. **Implementasi 15-Bar Recency Guard & 2.5x ATR Flash Runaway Guard pada M3 (`market_scanner.py`)**:
    - **Diagnosa Masalah**: Mekanisme M3 Multi-Touch Breakout Retest berpotensi meloloskan level-level kadaluarsa jika harga telah menjauh berhari-hari lalu berbalik sebagai counter-trend rally atau flash crash rebound.
    - **Perbaikan Kode Kuantitatif (Berdasarkan Riset FBS 10.7 Tahun / 23.173 Trade)**:
      - *15-Bar Recency Guard*: Level support/resistance yang ditembus WAJIB pernah dilewati/disentuh dalam 15 bar H1 terakhir (`has_recent_break`). Jika level ditembus >15 bar lalu tanpa retest, setup dianggap stale/hangus.
      - *2.5x ATR Runaway Flash Crash Guard*: Pergerakan maksimal harga sejak breakout tidak boleh melebihi $2.50\times\text{ATR}$ (`max_push <= 2.50 * atr_val`). Ambang batas ini terbukti aman meloloskan pergerakan intraday normal (1.0x–1.92x ATR seperti GBPCAD yang sukses), namun secara tegas memfilter anomali flash crash / waterfall rebound.
      - Desain zero-deadlock: Jika riwayat lilin < 16 bar (cold start / test harness), pengaman gracefully default ke True.
    - **Verifikasi**:
      - `py_compile` 100% OK.
      - Full test suite: **75/75 tests PASSED (100% OK)** dalam 1.325s.

---

## 16. 4 September 2026 — Dynamic 3-Point Trajectory Vector Engine, M2+M3 Confluence Fusion & Accurate Origin Tracking

### 🎯 Komponen & Arsitektur Utama:

1. **Pemisahan Titik Origin Breakdown vs Retest Bounce (`market_scanner.py`)**:
   - Memperbaiki algoritma deteksi M3 di `get_radar_standbys()` agar menelusuri mundur riwayat candle fisik:
     * **Titik 1 (Origin Break)**: Mendeteksi bar pertama yang menembus level secara tegas (`origin_time`, `origin_price`, `origin_age`).
     * **Titik 2 (Retest Bounce)**: Mendeteksi bar sentuhan retest terkini (`retest_time`, `retest_price`, `bar_age`).
   - Mengeliminasi anomali loop yang menimpa `event_time` dengan lilin saat ini sehingga label penembusan keliru tertulis `(now)`.

2. **Fusi Konfluensi Otomatis Multi-Setup M2 + M3 (`market_scanner.py` & `dashboard_assets.py`)**:
   - Jika M2 (Pullback EMA) dan M3 (Retest SBR/RBS) bertemu di level yang sama ($\le 0.35\times\text{ATR}$) dengan arah yang sama:
     * Standby ditandai dengan flag `is_confluence = True` dan `confluence_label = "[M2+M3 SELL CONFLUENCE] SBR & EMA Retest"`.
     * Frontend chart hanya menampilkan satu penanda terpadu `[M2+M3 SELL RETEST] SBR & EMA @ level (Nb ago)`, mengeliminasi penumpukan panah ganda yang membingungkan operator.

3. **Dynamic 3-Point Trajectory Vector Engine (`dashboard_assets.py`)**:
   - Kanvas 2D overlay chart TradingView menggambar alur trajektori dinamis bergradasi 3-titik:
     * **Segment 1 (Origin -> Retest)**: Garis putus-putus ungu/cyan beraksen titik awal `1. Break (Nb ago)`.
     * **Segment 2 (Retest Anchor)**: Titik cincin beraksen putih di lilin retest aktif.
     * **Segment 3 (Retest -> Target Projection)**: Garis vektor panah berarah tegas (Hijau BUY / Merah SELL) yang memproyeksikan target ke dinding ZCE terdekat ($F_1/C_1$ atau $F_2/C_2$) dengan label `3. TP Target <price>`.
   - Tergambar mulus 60 FPS saat chart digeser (*pan*) atau di-zoom.

4. **Rich Operational Phase di HUD & Watchlist (`dashboard.py` & `dashboard_assets.py`)**:
   - Header Intel HUD baris kedua diperkaya: label `STATE: CONSOLIDATION_RELOAD` digantikan oleh status alur operasional aktif (`PHASE: RETESTING SBR 181.719 -> TARGET 181.426 [SELL CONFLUENCE]`).
   - Tabel scanner watchlist menyajikan status alur per-pair secara eksplisit (`M2+M3 [BEAR]`, `M3 [BULL]`, dll).

5. **Verifikasi Kuantitatif Penuh**:
   - Seluruh test suite unit test: **115/115 tests PASSED (100% OK)** dalam 27.13s.

---

## 17. 8 September 2026 — Friction-Aware Net R:R, Dynamic ZCE Runway Gate & ZCE Reaction Grade Synchronization Bridge

### 🎯 Komponen & Arsitektur Utama:

1. **Sinkronisasi ZCE Reaction Grade (G3/G2/G1) ke MSE & Scanner (`zone_confluence_engine.py`, `macro_strategic_engine.py`, `market_scanner.py`)**:
   - **Diagnosa Masalah**: Terjadi disinkronisasi data di mana Dashboard menampilkan dinding konfluensi sebagai `[G3]` (dari klaster ZCE skor $\ge 6.5$), namun engine eksekusi (`market_scanner.py`) menolaknya karena `c1_reaction_grade` / `f1_reaction_grade` di `macro_cache` tetap bernilai `GRADE_2_INTERMEDIATE` akibat terputusnya jembatan metadata pada `ZoneMapResult.to_wall_override()`.
   - **Perbaikan**:
     * `src/analytics/zone_confluence_engine.py`: `_elect_walls` dan `ZoneMapResult` mengekspor `imm_ceiling_c1_grade`, `imm_floor_f1_grade`, `imm_ceiling_c1_score`, `imm_floor_f1_score`, `deep_ceiling_c2_grade`, `deep_floor_f2_grade`, dll. `to_wall_override()` menyertakan seluruh metadata grade & score secara utuh.
     * `src/analytics/macro_strategic_engine.py`: Blok `zce_walls` override menyerap grade dan density score ZCE ke `c1_reaction_grade`, `f1_reaction_grade`, `c2_reaction_grade`, `f2_reaction_grade`, serta memperbarui `layered_ceilings[0]` dan `layered_floors[0]` (`displacement_thresh`, `wick_band`, `fortress_tag`).
     * `src/analytics/market_scanner.py`: `macro_cache` kini menyimpan `c1_reaction_grade`, `f1_reaction_grade`, `c2_reaction_grade`, `f2_reaction_grade`. Filter likuiditas sesi Asia untuk pair Eropa kini mengenali Grade 3 Macro Fortress Wall secara akurat.
     * `tests/test_zce_grade_bridge.py`: Unit test baru memverifikasi transmisi end-to-end ZCE $\rightarrow$ MSE $\rightarrow$ Scanner macro context (100% PASS).

2. **Friction-Aware Net R:R & 4-Tier Setup Quality Architecture (`consensus.py` & `market_scanner.py`)**:
   - **Grade B Wall Scalp ($0.75R - 1.25R$)**: Target pantulan dinding terdekat ($C_1$ BUY / $F_1$ SELL) dengan kompensasi friksi $\text{TP}_{\text{Gross}} \ge (0.75 \times \text{SL}) + \text{Spread} + \text{Round-turn Commission}$. Partial close di-bypass 100%, BEP dipercepat ke 35% TP.
   - **Grade A Standard Intraday ($1.25R - 1.80R$)**: Target 50-pip psikologis / $C_1/F_1$ dengan partial close 50% di 50% TP dan BEP di 50% TP.
   - **Grade A+ Expansion Runner ($1.80R - 2.50R$)**: Mematuhi *Rigid Breached Wall Law* — target dilarang melompat ke $C_2/F_2$ jika hanya rejection wick; wajib ada konfirmasi fisik penutupan candle H1 di luar batas distal dengan displacement $\ge 50\%$.
   - **Grade S Macro Super-Shock ($\ge 2.50R - 3.50R$)**: Dual-path architecture (Unanimous 3/3 $\ge 85\%$ atau Pure Quant No-AI $|z| \ge 1.80$ + $|\Delta| \ge 2.00$ + ZCE Macro Wall). BEP dilonggarkan ke 65% TP.

3. **Dynamic ZCE Runway & Capacity Gate (`consensus.py`)**:
   - Menghapus plafon kaku statis yang sering menyebabkan false rejection `ANCHOR_TOO_WIDE` saat malam/Asia ketika ATR mengecil ($< 48\text{ pts}$). Plafon ceiling ekstrim diangkat ke $\max(3.5 \times \text{ATR}, 1.5 \times \text{Floor})$.
   - Validasi kapasitas runway ke dinding lawan ZCE terdekat ($C_1$ BUY / $F_1$ SELL). Jika runway $0.75 \le R:R < 1.25$, setup otomatis ditransisikan ke Grade B Wall Scalp.

4. **Verifikasi Kuantitatif Penuh**:
   - Full test suite: **198/198 tests PASSED (100% OK)** dalam 30.78s.

---

## 18. 8 September 2026 (Siang) — Ortogonalitas Action Tier (MSE) vs Setup Grade (ZCE) & Penyelarasan Lot Sizing Defensif

### 🎯 Komponen & Arsitektur Utama:

1. **Pemisahan Field Ortogonal (`market_scanner.py`)**:
   - Menghapus polusi penimpaan field makro `CandidateSetup.action_tier` oleh string geometri `"GRADE_B"`.
   - `action_tier` kini 100% didedikasikan untuk status makro MSE (`FULL_ALLOW`, `REDUCED_CONFIDENCE`, `TP1_ONLY_SCALP`, `WATCH_ONLY`, `HARD_BLOCK`).
   - `setup_grade` didedikasikan secara terpisah untuk status kapasitas runway geometri ZCE (`GRADE_B`, `GRADE_A`, `GRADE_A+`, `GRADE_S`).

2. **Harmonisasi Lot Sizing Single-Layer Defensif (`risk_engine.py` & `main.py`)**:
   - Menambahkan parameter `setup_grade=None` ke `RiskEngine.get_effective_lot_size()`.
   - Menyatukan kondisi defensif sehingga `setup_grade == "GRADE_B"` dan `action_tier == "REDUCED_CONFIDENCE"` diperlakukan setara sebagai satu layer diskon defensif ($0.75\times$ lot), mengeliminasi risiko dobel diskon ($0.75 \times 0.75 = 0.56\times$).
   - Memprioritaskan pengecekan `is_half_risk` (0.50x) dan `is_defensive` (0.75x) sebelum pengali konfluensi, sehingga pengali netral default `sizing_multiplier = 1.0` tidak mem-bypass diskon defensif Grade B.
   - `main.py` meneruskan `setup_grade=setup_grade_val` saat menghitung base lot.

3. **Prioritas BEP Agresif Grade B (`position_manager.py`)**:
   - Pengecekan `GRADE_B` / `REDUCED` (35% TP) diposisikan sebelum evaluasi rule umum M4 (70% TP).
   - Menjamin setiap trade dengan target sempit/pantulan dinding lawan ($0.75R - 1.25R$) langsung mengunci profit di 35% TP tanpa risiko tertahan di 70% TP.

4. **Klarifikasi Banner Radar Terminal (`cli_theme.py` & `main.py`)**:
   - Menampilkan `• Runway Grade : ` (ZCE Geometry Setup Grade & Action Tier) secara terpisah di banner radar.
   - Mengubah label Apex Carry menjadi `• Apex Carry FE: ` guna mencegah tabrakan pemahaman (*label collision*) antara grade geometri runway dan rating carry spread makro.
   - Banner eksekusi Pure Quant mencantumkan grade setup dan *Realized R:R* pasca-market fill.

5. **Verifikasi Kuantitatif Penuh**:
   - Seluruh test suite unit test: **199/199 tests PASSED (100% OK)**.


