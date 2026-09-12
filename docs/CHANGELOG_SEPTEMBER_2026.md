# Changelog September 2026 — Trading Bot Multi-LLM Consensus

> Dokumen ini mencatat seluruh perubahan arsitektur, fitur baru, dan riset kuantitatif sistem bot trading MetaTrader 5 periode September 2026.

## 105. Perubahan 12 September 2026 — Integrasi Dedicated Macro Seed 30 Tahun (FBS), Auto-Seeding Engine, Kalibrasi W1 Secular Slope, dan Rich ZCE Confluence Telemetry

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Keterbatasan Riwayat Makro Broker MT5 Live**:
   - Akun live broker hanya menyediakan data W1/MN1 terbatas (~100-200 bar), menyebabkan garis tren sekuler jangka panjang (multi-dekade) dan level makro institusional tidak terpetakan secara utuh.
2. **Kerapuhan Wick Breach pada Garis Tren Sekuler W1**:
   - Aturan deteksi trendline sebelumnya membatalkan garis tren jika terdapat satu sumbu lilin (*wick*) menembus garis, padahal lonjakan likuiditas agresif (misal wicking Jan 2026 pada EURUSD) ditutup kembali di bawah garis (rejeksi), sehingga garis tren sekuler 8 tahun dari puncak 2018 (1.25556) keliru dianulir.
3. **Anomali Telemetry Hover Level ZCE Dashboard ("1src Dummy")**:
   - Tooltip hover level ZCE pada dashboard menampilkan informasi seragam bernilai dummy: `TFs: H1 (1 src)` dan `Structural S/R Anchor` akibat ketiadaan transfer data primitif penyusun klaster dari `_pick_layers` di `zone_confluence_engine.py` ke pipeline `dashboard.py` dan `dashboard_assets.py`.
4. **Distorsi Visual Garis Diagonal W1 & Pola Geometris**:
   - Garis diagonal miring yang dirender di kanvas 2D mengalami distorsi/shearing saat chart di-zoom atau digeser, serta menyisakan garis proyeksi eksperimental Falling Wedge.

---

### ✨ Komponen & Solusi Utama:
1. **Dedicated Multi-Decade Macro Seed (`assets/macro_history/`) & Auto-Seeding Engine (`src/analytics/macro_data_loader.py`)**:
   - Mengunduh riwayat lengkap W1 (618–1.793 bar, ~1995–2026) dan MN1 (143–441 bar, ~1990–2026) dari FBS MT5 untuk seluruh **28 pair universe**.
   - Menyimpan dataset ke folder dedicated `assets/macro_history/` dalam 56 file `.csv.gz` terkompresi ringkas (**947 KB total**, dilacak Git).
   - Membangun `MacroDataLoader.get_deep_macro_rates()` yang menggabungkan baseline FBS dengan live broker bars secara sub-milidetik, dilengkapi mekanisme **auto-seeding** otomatis setiap penutupan candle W1 (1 minggu) dan MN1 (1 bulan).
2. **Kalibrasi W1 Secular Slope Barrier & SMC Close Breach (`src/analytics/macro_strategic_engine.py`)**:
   - Memperpanjang horizon sekuler `W1_SECULAR_LOOKBACK_BARS = 480` (~9.2 tahun) di `config.py` dan `.env`.
   - Mengganti wick breach kaku dengan **SMC Close Breach Law** (`Close > Line + 0.15 * ATR_W1`).
   - Berhasil mendeteksi Puncak Sekuler 2018 (High 1.25556), memetakan plafon tren sekuler EURUSD di level **1.18033** (18 confirmed touch points) dengan outer boundary di **1.19517**.
3. **Rich ZCE Confluence Hover Telemetry (`zone_confluence_engine.py`, `dashboard.py`, `dashboard_assets.py`)**:
   - Mengekstrak primitif struktural riil (`c.members`) di `_pick_layers` (`sources`, `tfs_present`, `kinds_present`, `confluence`).
   - Mempertahankan dan mengakumulasikan metadata saat proses *proximity consolidation* di `dashboard.py`.
   - Menampilkan telemetry konfluensi multi-sumber yang kaya pada tooltip hover (misal `5src` s/d `12src`, `D1+H1+H4+M30+PSY`, struktur `OB_BEAR (M30) • EQH (H4) • LAST_HIGH (H1) • EMA_BAND (H1)`), serta jumlah touch point asli pada W1 Slope (`18 touches`).
4. **Pembersihan Geometri Grafik Dashboard (`dashboard_assets.py`)**:
   - Menghapus rendering kanvas garis miring diagonal W1 DESC SLOPE untuk mengeliminasi distorsi zoom, menggantikannya dengan garis harga horizontal putus-putus yang bersih.
   - Membersihkan sisa elemen Falling Wedge dan memperbarui label toolbar menjadi `SMC Range`.
5. **Verifikasi Suite Lengkap**:
   - Seluruh 34 unit test (`test_pattern_engine.py`, `test_dashboard.py`, `test_symbol_rotation.py`, `test_time_decay_and_vol_regime.py`) lulus **100% PASS**.
   - Verifikasi live API `/api/symbol/EURUSD` dan `/api/overview` terkonfirmasi aktif dengan metadata valid.

---

## 104. Perubahan 11 September 2026 (Malam IV) — Penegakan Hard Floor R:R 0.50:1 Lintas Mekanisme (M1, M2, M3) & Eliminasi Setup Target Station Semu (Resolusi Anomali XAUUSD R:R 0.02:1)

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Anomali R:R 0.02:1 pada Setup XAUUSD-ECNc**:
   - Radar memicu setup paper trade berulang pada XAUUSD-ECNc dengan SL $25.00 ($2500 pts) dan TP hanya $0.40 ($40 pts), menghasilkan $R:R = 0.02:1$.
2. **Ketiadaan Validasi Jarak Minimum ke Target Station di Atlas DNA (`atlas_dna.py`)**:
   - Jika entry berjarak sangat dekat dengan dinding terdekat $C_1$ atau $F_1$ (misal hanya 40 sen di XAUUSD), fungsi `calculate_intraday_sl_tp` tetap memilih dinding tersebut sebagai `target_station` tanpa memeriksa apakah $(entry - F_1) \ge \text{min\_wall\_dist}$.
   - Nilai TP kemudian dijepit ke $F_1$, menghasilkan TP mikro yang tidak proporsional terhadap SL.
   - Blok klasifikasi grade jatuh ke `else: setup_grade = "GRADE_B"` tanpa memeriksa batas bawah $R:R \ge 0.50$, sehingga setup 0.02:1 salah dilabeli sebagai Grade B yang sah.
3. **Ketiadaan Pintu Tolak R:R di Market Scanner (`market_scanner.py`)**:
   - Seluruh blok M1 BUY, M1 SELL, M2 BUY, M2 SELL, M3 BUY, dan M3 SELL hanya mengecek jarak SL absolut (`abs(entry - sl) / pt >= 15`), tanpa mengecek rasio R:R minimum maupun tag `INVALID_RR`.

---

### ✨ Komponen & Solusi Utama:
1. **Validasi Runway Minimum Dinding ZCE & Klasifikasi `INVALID_RR` (`atlas_dna.py`)**:
   - Menambahkan syarat runway minimum `(c1 - entry_price) >= min_wall_dist` (BUY) dan `(entry_price - f1) >= min_wall_dist` (SELL) sebelum menetapkan $C_1/F_1$ sebagai `target_station`.
   - Mengunci grade classification: hanya $R:R \ge 0.50$ yang dapat menerima status `GRADE_B`. Setup dengan $R:R < 0.50$ otomatis diklasifikasikan sebagai `INVALID_RR`.
2. **Penegakan Hard Floor R:R $\ge 0.50$ Lintas Mekanisme di Radar (`market_scanner.py`)**:
   - Menambahkan guard `elif rr_val < 0.50 or sl_tp.get("setup_grade") == "INVALID_RR":` pada seluruh blok eksekusi:
     * M1 SELL & M1 BUY (Universal Liquidity Sweep)
     * M2 BUY & M2 SELL (Trend-Aligned Pullback)
     * M3 BUY & M3 SELL (Multi-Touch Breakout Retest)
   - Setup yang tidak memenuhi rasio minimum 0.50R langsung ditolak sebelum antrean radar dengan log `[M{1,2,3} {BUY/SELL} RR GUARD]`.
3. **Verifikasi Suite Lengkap**:
   - Seluruh 265 unit test (`python -m unittest discover -s tests -p "test_*.py"`) berjalan sukses 100% PASS (`OK`).

---

## 103. Perubahan 11 September 2026 (Malam III) — Penguncian Ketat Dealing Range pada Mekanisme Radar (M1, M2, M3) & Eliminasi Total Anomali Sweep di Zona Diskon (Resolusi Kasus EURGBP)

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Kebocoran Klausa Bypass M1 Universal Liquidity Sweep (`market_scanner.py:4054, 4224`)**:
   - Pada pukul 17:26:20 WIB, bot mengeksekusi order riil `EURGBP-ECNc SELL` via M1 Universal Liquidity Sweep di harga `0.85836`.
   - Investigasi forensik membuktikan bahwa harga `0.85836` berada di **42.7% Dealing Range** (`dr_pos = 0.427`), yang merupakan **Lantai Support Intraday / Zona Diskon** (di bawah garis ekuilibrium 50%).
   - Ditemukan klausa bypass:
     `is_premium_sweep = (dr_pos_val >= 0.55) or (intraday_dr_pos >= 0.50) or (ref_top > 0 and mid >= ref_top - (0.35 * atr_price_val))`
   - Klausa ketiga mem-bypass total syarat Premium sehingga level plafon mikro di area support diskon dipungut oleh `min(valid_tops)` dan dianggap sebagai "Bearish Stop Hunt / SFP High".
2. **Ketiadaan Boundary Collision Guard di M2 dan M3**:
   - M2 Pullback berpotensi membeli saat harga sudah menempel plafon atas ($dr\_pos \ge 0.80$) atau menjual di dasar lantai ($dr\_pos \le 0.20$) jika runway menuju benteng lawan sempit.
   - M3 Breakout Retest berpotensi mengejar breakout di puncak ekstrim ($dr\_pos \ge 0.85$) atau dasar ekstrim ($dr\_pos \le 0.15$) tanpa konfirmasi jebolnya dinding ZCE C1/F1.

---

### ✨ Komponen & Solusi Utama:
1. **Penguncian Mati Dealing Range pada M1 Sweep (`market_scanner.py`)**:
   - Menghapus total klausa bypass `or (ref_top > 0 and mid >= ref_top - 0.35*atr)` pada M1 SELL dan `or (ref_bot > 0 and mid <= ref_bot + 0.35*atr)` pada M1 BUY.
   - **M1 SELL**: Wajib memenuhi `dr_pos_val >= 0.55` atau `intraday_dr_pos >= 0.50`. Jika tidak, order langsung ditolak dengan log `[SWEEP SELL DISCOUNT VETO]`.
   - **M1 BUY**: Wajib memenuhi `dr_pos_val <= 0.45` atau `intraday_dr_pos <= 0.50`. Jika tidak, order langsung ditolak dengan log `[SWEEP BUY PREMIUM VETO]`.
   - **Zone Integrity Filter**: Level plafon (`valid_tops`) dilarang memungut level di zona Diskon ($dr < 0.50$), dan level lantai (`valid_bots`) dilarang memungut level di zona Premium ($dr > 0.50$).
2. **Boundary Collision Guard pada M2 Pullback (`market_scanner.py`)**:
   - M2 BUY: Dilarang beli jika $dr\_pos \ge 0.80$ dan runway ke plafon lawan $C_1 < 0.40\times\text{ATR}$ (`[PULLBACK BUY CEILING COLLISION]`).
   - M2 SELL: Dilarang jual jika $dr\_pos \le 0.20$ dan runway ke lantai lawan $F_1 < 0.40\times\text{ATR}$ (`[PULLBACK SELL FLOOR COLLISION]`).
3. **Exhaustion Retest Guard pada M3 Breakout Retest (`market_scanner.py`)**:
   - M3 BUY: Dilarang mengejar retest di puncak ekstrim $dr\_pos \ge 0.85$ tanpa konfirmasi dinding $C_1$ telah jebol fisik (`[BREAKOUT BUY EXHAUSTION]`).
   - M3 SELL: Dilarang mengejar retest di dasar ekstrim $dr\_pos \le 0.15$ tanpa konfirmasi dinding $F_1$ telah jebol fisik (`[BREAKOUT SELL EXHAUSTION]`).
4. **Unit Testing & Verifikasi Penuh**:
   - Penambahan unit test `test_m1_sweep_dealing_range_locks_veto_discount_sell_and_premium_buy` dan `test_m2_and_m3_dealing_range_boundary_guards` di `tests/test_market_scanner.py`.
   - Seluruh 265 unit test pada sistem berstatus **100% PASS** (`OK`).

---

## 102. Perubahan 11 September 2026 (Malam II) — Resolusi Konflik Multi-Mekanisme Radar (M1, M1B, M2, M3, M4) Berbasis ZCE Runway & Keselarasan Makro/Mikro serta Harmonisasi 1:1 Dashboard Cockpit

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Short-Circuit `continue` Prematur di Radar Engine (`market_scanner.py`)**:
   - Fungsi `scan_fast_radar` sebelumnya langsung memanggil `continue` setelah menemukan suatu mekanisme (M1 -> skip M2-M4, M2 -> skip M3-M4).
   - Akibatnya, pada satu simbol yang sama, jika M2 (Pullback) terdeteksi di EMA, bot mengabaikan M3 (Breakout Retest terkonfirmasi di level struktural) atau M4 (Basing Box Continuation) yang mungkin memiliki R:R dan runway jauh lebih superior.
2. **Desinkronisasi Arah Standby Dashboard vs Engine (Kasus AUDCHF & Pasangan JPY)**:
   - Dashboard Cockpit `_elect_primary_standby` hanya menyortir berdasarkan flag tren D1 (`macro['is_bull']`), mengabaikan posisi dealing range harga di plafon C1 dan momentum mikro (Boitoki CSM Net Delta).
   - Akibatnya, pada AUDCHF di mana harga berada di plafon C1 (0.5838) dengan CSM Delta AUD -2.15 (bearish), dashboard menampilkan sinyal BUY sementara engine radar mengeksekusi SELL.
   - Demikian pula pada pasangan JPY (EURJPY vs CADJPY), seleksi kandidat tanpa penilaian runway menyebabkan benturan arah.

---

### ✨ Komponen & Solusi Utama:
1. **Peniadaan `continue` Prematur & Intra-Symbol Mechanism Resolution (`market_scanner.py`)**:
   - Menghapus seluruh `continue` prematur di M1 BUY/SELL, M1B BUY/SELL, M2 BUY/SELL, dan M3 BUY/SELL.
   - Mengumpulkan seluruh setup kandidat dalam satu siklus scan per simbol ke `sym_candidates = []`.
   - Mengimplementasikan helper `_resolve_best_mechanism_candidate()`:
     * **Confluence Fusion**: Melebur setup yang searah dalam jarak $\le 0.35\times\text{ATR}$ menjadi satu tiket konfluensi berkekuatan ganda (misal: `M1+M3_CONFLUENCE`, `M2+M3_CONFLUENCE`, `M1+M1B+M3_CONFLUENCE`), dan meningkatkan grade setup (`GRADE_A` $\rightarrow$ `GRADE_A+` $\rightarrow$ `GRADE_S`).
     * **Composite Scoring untuk Setup Berlawanan**:
       $$\text{Score} = (2.0 \times \text{macro\_score}) + (1.5 \times \text{micro\_score}) + (1.5 \times \min(3.5, \text{runway\_atr})) + \text{chamber\_bonus}$$
     * Memberikan penalti bagi arah yang menabrak plafon/lantai terdekat dan memberikan bonus bagi pemudaran (*fade*) plafon C1 / lantai F1.
2. **Harmonisasi 1:1 Dashboard Cockpit (`dashboard.py`)**:
   - Memperbarui `_elect_primary_standby` agar mendeteksi posisi Dealing Range ekstrem ($dr\_pos \ge 0.80$ dengan CSM bearish membalikkan preferred direction ke SELL; $dr\_pos \le 0.20$ dengan CSM bullish membalikkan ke BUY).
   - Mengintegrasikan evaluasi kapasitas runway `runway_atr` (dengan ambang `has_healthy_runway >= 0.25x ATR`).
   - Menerapkan sorting hirarki institusional:
     `Confluence > Preferred Direction > Active Physical Interaction > Actionable > Healthy Runway > Distance to Market (Proximity)`.
   - Menyelaraskan kartu visual watchlist, retikel trajectory, dan HUD phase secara 1:1 dengan engine radar.
3. **Unit Testing & Verifikasi Penuh**:
   - Penambahan unit test `test_same_direction_confluence_fusion` dan `test_opposing_direction_runway_and_macro_resolution` di `tests/test_market_scanner.py`.
   - Penyelarasan `test_elect_primary_standby_pro_trend_priority` di `tests/test_dashboard.py`.
   - Verifikasi 263 unit test di seluruh repositori: **100% PASS** (`OK`).

---

## 101. Perubahan 11 September 2026 (Malam) — Rekonstruksi Geometri Trade Kuantitatif MT5 (Pilar 0–7) & Resolusi Tuntas Kasus Forensik AUDNZD (Anti-Marubozu Waterfall, MSE Mid-Chamber Leak Closure, dan Projected SBR / Breached Wall Law)

### Latar Belakang & Investigasi Kuantitatif:
1. **Pembedahan Data 1 Minggu (165 Live Trades & 219 Shadow Trades)**:
   - Evaluasi asimetri performa arah: Buy win rate konsisten menguntungkan, sementara Sell mengalami anomali tajam pada candle ekspansif lawan (*Marubozu Waterfall*), terutama pada pair Crosses seperti AUDNZD @ RBS 1.22800.
   - Analisis geometri menunjukkan 3 cacat kritis pada formula lama:
     * *Struct_dist* bernilai nol pada order limit M2/M3 karena `entry_lim = origin_level`, menyebabkan SL hanya bergantung pada suku statis atau lantai bawah.
     * Keterikatan artifisial TP pada kelipatan SL (`min_tp = 1.25 * SL + friction`) di mode ZCE memaksa target menjauh melompati benteng alami terdekat, memotong win rate secara drastis.
     * Ketiadaan batas atas lot pada akun Cent menyebabkan SL ketat (<60 pts) melompatkan volume posisi hingga $\ge 1.20 - 2.00$ lot.
2. **Kasus Forensik AUDNZD SELL @ 1.22800**:
   - Bot memasang `sell_limit` tepat di puncak candle Marubozu bullish yang sedang menembus level RBS.
   - Ditemukan kebocoran struktural: bypass `is_limit_retest` membocorkan entry di lorong transit terlarang Mid-Chamber MSE, dan level yang sedang ditembus (*breached*) dipungut sebagai anchor limit tanpa validasi penutupan badan lilin.

---

### Solusi Arsitektur & Perubahan Komponen (Pilar 0–7):
1. **Pilar 0 — Telemetri Geometri 6 Kolom (`shadow_tracker.py` & `position_manager.py`)**:
   - Menambahkan 6 kolom telemetri struktural pada `ShadowTrade` dan `trade_lifecycle_telemetry.json`:
     `invalidation_dist`, `sl_effective`, `sl_atr_ratio`, `tp_atr_ratio`, `friction_ratio`, dan `session_window`.
2. **Pilar 1 — Plafon Lot Maksimal Akun Cent (`config.py`, `.env`, `risk_engine.py`)**:
   - Mengunci `MAX_POSITION_LOT = 0.50` di `.env` dan `config.py`.
   - `risk_engine.py` secara tegas meng-clamp ukuran lot efektif maksimal ke `0.50 lot` agar trade dengan SL rapat tidak mengambil eksposur risiko abnormal.
3. **Pilar 2 — Dekopel TP dari Kelipatan SL (`consensus.py`)**:
   - Memisahkan penanganan non-ZCE legacy (sesuaikan ke `min_tp` untuk backward-compatibility test) dari mode ZCE produksi.
   - Pada mode ZCE aktif, target struktural ZCE dipertahankan apa adanya selama memenuhi kapasitas runway Grade B floor ($0.50\times\text{SL} + \text{friksi}$) tanpa menaikkan TP secara artifisial.
4. **Pilar 3 — Floor Turunan Friksi (`config.py`, `.env`)**:
   - Parameter `FRICTION_FLOOR_DIVISOR = 0.20` via helper `config.friction_floor_points(spread_pts, comm_pts=6)` memastikan total friksi broker (spread + round-turn komisi) tidak melebihi 20% dari jarak Stop Loss.
5. **Pilar 4 — Formula SL Seimbang Tiga Suku di Atlas DNA (`atlas_dna.py`)**:
   - Reformulasi Stop Loss:
     $$\text{invalidation\_buffer} = \max(0.15\times\text{ATR}, (2\times\text{spread} + 10)\times\text{pt})$$
     $$\text{struct\_dist} = |\text{entry} - \text{origin}| + \text{invalidation\_buffer}$$
     $$\text{SL} = \max(\text{struct\_dist}, 1.00\times\text{ATR}, \text{fric\_floor})$$
   - Mencegah formula degenerate menjadi nol saat entry berimpit dengan anchor limit di M2/M3.
   - Menghapus pembatasan redundan `(c2 - entry) <= 3.5 * risk` pada pemilihan `target_station` saat dinding C1/F1 telah jebol (`c1_breached` / `f1_breached`), sehingga stasiun target mengakui benteng berikutnya (C2/F2) sementara eksekusi TP tetap ter-clamp aman pada $3.50\times\text{risk}$.
6. **Pilar 5 — Defensif London 15:00–17:59 WIB (`market_scanner.py`)**:
   - Mengaktifkan `ENABLE_LDN_DEFENSIVE_WINDOW = True`.
   - Melarang pemasangan `sell_limit` pasif pada jendela London Open 15:00–17:59 WIB (`[LDN15-17 DEFENSIVE]`), memitigasi anomali performa SELL di jam volatil pembukaan pasar Eropa.
7. **Pilar 6 — Target Jauh Bersyarat $\ge 2.5\times\text{ATR}$ (`market_scanner.py`)**:
   - Injeksi helper `_apply_conditional_far_target` ke seluruh mekanisme (M1 BUY/SELL, M2 BUY/SELL, M3 BUY/SELL, M4).
   - Target TP $\ge 2.5\times\text{ATR}$ hanya diizinkan jika didukung oleh rezim Tokyo dengan $|\text{CSM Delta}| \ge 2.00$ atau konfirmasi dinding ZCE telah ditembus (`c1_breached` / `f1_breached`). Jika tidak, target otomatis disesuaikan ke ambang batas netral $2.5\times\text{ATR}$.
8. **Pilar 7 — Proteksi Momentum Lilin & Integritas Kamar (Resolusi Kasus AUDNZD)**:
   - **Anti-Marubozu Waterfall Guard di M3 Retest**: Memanggil `_evaluate_m2_wall_quality` pada setup M3 BUY & SELL. Jika lilin mendekati anchor dengan momentum ekspansi counter-trend (`body_ratio >= 0.55` dan `rejection_wick < 0.20`), order langsung DITOLAK TOTAL (`MARUBOZU_WATERFALL`).
   - **Penutupan Kebocoran Mid-Chamber MSE**: Menghapus bypass naif `if is_limit_retest: continue` untuk `MID-CHAMBER` di `market_scanner.py`. Membatasi order SELL hanya di area plafon sejati ($entry \ge C_1 - 0.25\times\text{ATR}$) dan BUY di lantai sejati ($entry \le F_1 + 0.25\times\text{ATR}$). Jika berada di koridor transit: `[MID-CHAMBER FREEZE] Entry ditolak`.
   - **Projected SBR / Breached Wall Law**: Menambahkan filter `_is_zce_wall_breached` pada pencarian anchor M3 agar level yang telah ditembus badan lilin tidak dipilih sebagai limit anchor.

---

### Verifikasi & Suite Pengujian:
- Pembuatan test suite komprehensif baru `tests/test_trade_geometry_and_audnzd_guard.py` (10 test cases: 10/10 PASS).
- Penyelarasan test warisan: `tests/test_m3_discount_guard_and_leapfrog.py` (9/9 PASS), `tests/test_pure_quant_execution.py` (2/2 PASS), `tests/test_sep8_enhancements.py` (10/10 PASS).
- Seluruh 261 unit test pada sistem berstatus **100% PASS** (`OK`).

---

## 100. Perubahan 11 September 2026 (Sore) — Rekonsiliasi Kritis Tesis Chamber-to-Chamber vs Telemetri Empiris: Proteksi Edge Diskon Mid-Chamber, Persistensi Telemetri Grade Dinding, Soft-Gate GRADE_B pada Dinding G1, dan Marubozu Guard pada Mechanism 2 (M2 Pullback)

### Latar Belakang & Investigasi Telemetri Empiris (219 Shadow Trades & 43 Live Trades):
1. **Audit Kritis Dokumen Tesis (`THESIS_CHAMBER_TO_CHAMBER_AND_MOMENTUM_CONFIRMATION.md`)**:
   - Tesis mendalilkan kegagalan trade M2 SELL AUDUSD @ 0.71723 sebagai "Mid-Chamber Trap" dan merekomendasikan penghapusan bypass `is_limit_retest` di `market_scanner.py:3576`.
   - **Hasil Uji Kohort Empiris (DeepSeek)**:
     * **Boundary ($\le 0.35 / \ge 0.65$, $n=96$) vs Mid-Range ($0.35-0.65$, $n=78$)**:
       - Take Profit (TP Hit): 30.2% vs 20.5% (Chi-square $p = 0.166$, tidak signifikan).
       - Stop Loss (SL Hit): **21.9% vs 24.4%** (Chi-square $p = 0.699$, **praktis identik!**).
       - Cumulative Net R: +17.75 R vs -1.88 R (Gain jika mid dibuang hanya +1.88 R, sedangkan noise harian M2 adalah 7.96 R: efeknya cuma $0.24\times$ noise).
       - Mean R: +0.185 R vs -0.024 R (Permutasi $p = 0.039$, Bootstrap 95% CI $[+0.014, +0.399]\text{R}$).
     * **Mekanisme Tesis Terbantahkan**: Klaim bahwa order mid-chamber "diinjak waterfall" terbukti keliru karena tingkat hard-SL identik. Masalah sejati adalah efisiensi exit (trade mid-range terpotong di BEP/trailing sebelum sempat lari karena runway sempit).
     * **Bypass Baris 3576 Wajib Dipertahankan**: Limit order diskon dalam chamber terbukti menghasilkan Win Rate 66.7% (vs 55.1% pada chasing breakout). Menghapus bypass ini akan merusak setup diskon M2 dan M4 berbasis R:R asimetris.
     * **Missed M1 BUY AUDUSD**: Terjadi bukan karena toleransi sweep (`sweep_tol`), melainkan akibat `[SFR VETO]` (Supreme Precedence di `market_scanner.py:3453`) yang mengunci keranjang systemic USD.
     * **Akar Masalah M2 SELL AUDUSD**: Bot mengeksekusi limit order tepat di benteng ZCE C1 saat itu (`0.71724`). Namun M2 tidak memiliki Wall Quality Gate dan memiliki klausa trivial `has_res_hold = (mid <= base_ceiling + 0.15*ATR)` yang selalu bernilai True, sehingga bot memasang limit order menabrak candle Marubozu bullish bertenaga tinggi (body 71%, upper wick 13%) di benteng `GRADE_1_MICRO`.
     * **Ilusi Log Audit**: Baris `[ZCE-AUDIT]` di `main.py` salah mencetak level Stop Loss dan Take Profit sebagai F1/C1, menimbulkan ilusi bahwa bot masuk di level ngawur.

---

### Solusi Arsitektur & Perubahan Komponen (Checklist 8 File Wajib):
1. **`src/analytics/shadow_tracker.py` & `src/analytics/position_manager.py` (Persistensi Telemetri Grade Dinding)**:
   - Menyimpan `wall_grade`, `f1_reaction_grade`, `c1_reaction_grade`, `zce_f1`, dan `zce_c1` ke dalam metadata `quant_shadow_trades.jsonl`, `quant_shadow_state.json`, dan `trade_lifecycle_telemetry.json`.
   - Mengakhiri keterbatasan ketiadaan data historis grade dinding, memungkinkan audit counterfactual yang akurat setelah terkumpul $\ge 60-100$ trade berikutnya.
2. **`main.py`**:
   - Menyelaraskan baris cetak `[ZCE-AUDIT]` (market & pending order) agar mengambil level `ZCE_F1` dan `ZCE_C1` sejati dari metadata kandidat radar, bukan lagi Stop Loss (`sl`) atau `dealing_range_low`.
   - Meneruskan metadata ZCE ke `position_manager.record_trade_open_telemetry()`.
3. **`src/analytics/market_scanner.py`**:
   - Menyuntikkan `zce_f1`, `zce_c1`, `f1_grade`, dan `c1_grade` langsung ke `zce_meta` di setiap kandidat radar.
   - **Soft-Gate G1 Micro-Wall (M2 BUY & M2 SELL)**: Jika anchor bertengger di benteng `GRADE_1_MICRO` tanpa konfirmasi wick rejection $\ge 25\%$, setup di-soft-gate ke **`GRADE_B`** (1 tiket murni, no partial, BEP dipercepat ke 35% TP) alih-alih di-hard-block, mempertahankan kelengkapan sampel trade.
   - **Momentum Exhaustion Gate (Marubozu Guard)**: Melarang keras limit order dipasang menabrak candle ekspansif (body $\ge 55\%$ dengan rejection wick $< 20\%$) tanpa adanya tanda kelelahan momentum.
   - **Pembersihan Logika `has_res_hold` / `has_support_hold`**: Menghapus klausa longgar `(mid <= base_ceiling + 0.15*ATR)` yang sebelumnya memicu eksekusi buta.
   - **Key Levels Alignment**: Memetakan `key_support` dan `key_resistance` ke benteng struktural asli, bukan Stop Loss.
4. **`docs/superpowers/specs/2026-09-11-RECONCILIATION-chamber-thesis-vs-telemetry.md`**:
   - Dokumentasi formal audit kuantitatif komprehensif mencakup tabel kohort DeepSeek, pengujian statistik permutasi & chi-square, rasionalisasi penolakan penghapusan bypass mid-chamber, dan adopsi soft-gate.
5. **`tests/test_m2_wall_quality_and_exhaustion.py`**:
   - Penambahan unit test suite khusus 6 skenario (G1 micro wall soft-gate ke GRADE_B, Marubozu guard BUY/SELL, valid rejection pass, ZCE-AUDIT formatting, dan verifikasi persistensi telemetri grade).
   - Seluruh test dipastikan **100% PASS** dalam 1.54 detik.
6. **Status Parameter CBSS**:
   - Sesuai arahan pengguna, modul CBSS tetap dipertahankan nonaktif (`ENABLE_CBSS=false` di `.env` dan `config.py`).

---

## 99. Perubahan 11 September 2026 (Siang) — Dual-Horizon Multi-Timeframe Structural Engine (MSE & ZCE): Eliminasi Kebutaan Horizon (Horizon Blindness) via Anchor Peak Law & Anti-Fake Expansion Gate

### Latar Belakang & Investigasi Kuantitatif:
1. **Diagnosis Anomali Kasus EURNZD-ECNc**:
   - Pada chart H1/D1, bot mendeteksi kenaikan +520 pips dalam 5 hari terakhir sebagai `D1_BULLISH_EXPANSION` dan memicu order BUY limit di harga `1.99226` dengan target `1.99369` (menjelang level psikologis bulat `2.00000`).
   - Secara visual manusia pada chart Weekly (W1), harga sebenarnya berada di ujung atas pola penolakan keras (*Descending Trendline / Channel Compression*) dengan 5 Lower Highs berurutan:
     * $LH_1: 2.06807 > LH_2: 2.04397 > LH_3: 2.03128 > LH_4: 2.02378 > LH_5: 2.00406$.
   - **Kebutaan Horizon (*Horizon Blindness*)**:
     * Single lookback window W1 mengaburkan perbedaan antara tren sekuler multi-tahun (156 minggu/3 tahun: Bullish dari 1.56800) dan tren intermediet struktural (52 minggu/1 tahun: Bearish Lower Highs beruntun).
     * Akibatnya, bot menganggap retest atap miring W1 sebagai setup ekspansi baru padahal merupakan zona bahaya penolakan keras institusional.

---

### Solusi Arsitektur & Perubahan Komponen:
1. **Dual-Horizon Lookback Engine W1 (`src/analytics/macro_strategic_engine.py`)**:
   - Membagi analisis W1 menjadi dua horizon waktu independen:
     * **Secular Horizon (156 bar / ~3 tahun)**: Menentukan konteks siklus makro besar.
     * **Intermediate Horizon (52 bar / ~1 tahun)**: Menentukan struktur ayunan aktif.
2. **Algoritma Outer Tangent Envelope (Anchor Peak Law)**:
   - Titik awal $P_0$ wajib berupa Puncak Tertinggi Mutlak dalam 52 minggu terakhir ($2.06807$).
   - Menghitung garis miring menuju Lower Highs berikutnya yang memenuhi syarat:
     * Garis tidak tertembus oleh penutupan fisik lilin W1 (`Close <= Line + 0.15 ATR`).
     * Wajib memiliki $\ge 3$ titik sentuhan (*3-Touch Confirmation*) dalam batas toleransi $\le 0.30\times\text{ATR W1}$.
   - Memproyeksikan level resistensi miring aktif ke bar saat ini: pada EURNZD, level presisi live berada di **`2.00406`**!
3. **Injeksi Node ZCE (`W1_DESC_SLOPE_CEILING`)**:
   - Node resistensi miring diinjeksi ke `raw_up_elements` dengan bobot Grade 3 Macro (6.5) sehingga ZCE secara otomatis memperhitungkan atap miring ini sebagai benteng resistensi.
4. **Demarkasi W1 Slope: Murni Penggaris Visual & Telemetri (Zero Hard Gating)**:
   - Sesuai prinsip mikrostruktur pasar institusional bahwa likuiditas sejati bertumpu pada level horizontal (ZCE True Zonal Bands, SMC Order Blocks, dan Liquidity Sweeps), trendline miring W1 difungsikan sebagai **penggaris visual & awareness context** di dashboard (tidak memblokir eksekusi secara kaku agar peluang SFP / breakout tidak terbunuh prematur).
   - Seluruh validasi gating eksekusi tetap dipercayakan secara murni kepada benteng horizontal ZCE, SMC, dan FRVP.
4B. **Perbaikan Runtime Bug `NameError: name 'cur_atr' is not defined` di Tokyo Midday Lull Gate (`market_scanner.py`)**:
   - Logika gate Tokyo Midday Lull (10:30–13:00 WIB) di baris 3529 sebelumnya memanggil variabel `cur_atr` yang tidak terdefinisi di scope fungsi, menyebabkan radar crash diam-diam saat memindai setup continuation pada pair Pasifik/Asia (`GBPJPY`, `AUDCHF`, `CADJPY`, `NZDCAD`, `NZDUSD`, `GBPNZD`).
   - Diselaraskan menjadi `atr_val = (macro.get('current_atr', atr_pts * pt))` sehingga radar kembali memindai 28 simbol secara 100% mulus tanpa error.
5. **Visualisasi Komprehensif di Dashboard (`dashboard_assets.py` & `dashboard.py`)**:
   - **Hero Banner**: Banner amber interaktif `#w1-slope-banner` di atas chart saat pair sedang menabrak garis slope W1.
   - **Canvas Overlay**: Garis diagonal putus-putus emas (`rgba(245, 158, 11, 0.85)`) yang ditarik dari anchor peak melintasi chart menuju bar live, dilengkapi titik-titik node $LH_1..LH_n$.
   - **Price Line**: Garis resistensi horizontal putus-putus pada level slope aktif.
   - **Watchlist Pill**: Badge `<span class="w1-conflict-pill">W1 SLOPE</span>` pada kartu pair yang terdampak.
6. **Anti-Disruption Architecture (Graceful Degradation)**:
   - Pasangan mata uang trending (USDJPY, USDCHF, CADJPY) atau sideways horizontal murni secara otomatis menghasilkan `None`, sehingga 100% aman dan tidak mengganggu 25 pair FX lainnya.
7. **Penyelarasan Konfigurasi `.env` dan `config.py`**:
   - `ENABLE_DUAL_HORIZON_W1=true`
   - `W1_INTERMEDIATE_LOOKBACK_BARS=52`
   - `W1_SECULAR_LOOKBACK_BARS=156`
   - `W1_SLOPE_PROXIMITY_TOL_ATR=0.50`
   - `W1_SLOPE_MIN_TOUCHES=3`
8. **Pengujian Unit Test**:
   - Unit test baru `tests/test_dual_horizon_w1.py` lulus 100% (3/3 PASS).
   - Seluruh test suite (305 unit tests) lulus 100% (305/305 PASS).

---

## 98. Perubahan 11 September 2026 (Pagi III) — Perbaikan Rekonsiliasi Pending Order MT5 Batal/Expired di Shadow Tracker & Eliminasi Tiket Hantu

### Latar Belakang & Investigasi:
1. **Tiket Hantu MT5 `#1282833785` (EURCHF-ECNc) Terus Berstatus ACTIVE di Dashboard**:
   - Order `#1282833785` aslinya adalah pending limit buy di MT5 yang telah dibatalkan (`ORDER_STATE_CANCELED = 2`, `position_id = 0`) pada 10 September 17:46 WIB.
   - Karena harga pasar sempat menyentuh level limit secara virtual, `shadow_tracker` mengubah statusnya menjadi `ACTIVE`.
   - Pada siklus rekonsiliasi:
     * `shadow_tracker` mencari deal penutupan di `history_deals_get(position=1282833785)`. Karena pending order dibatalkan sebelum terisi, tidak ada deal yang pernah tercipta.
     * Pengecekan order kedaluwarsa (`history_orders_get`) sebelumnya hanya berjalan jika status bernilai `PENDING` dan salah memeriksa konstanta `ord_state in (4, 6)` (di mana 4 adalah `ORDER_STATE_FILLED`, bukan canceled).
     * Akibatnya, trade menggantung sebagai `ACTIVE REAL MT5` tanpa pernah dilepaskan.

---

### Solusi Arsitektur & Perubahan Komponen:
1. **Penyempurnaan Rekonsiliasi Pending Order MT5 (`src/analytics/shadow_tracker.py`)**:
   - Menyelaraskan status order MT5 yang batal/kedaluwarsa: `ord_state in (2, 5, 6)` (`2=ORDER_STATE_CANCELED`, `5=ORDER_STATE_REJECTED`, `6=ORDER_STATE_EXPIRED`).
   - Di `update_shadow_orders()` dan `get_active_trades_enriched()`:
     * Jika sebuah trade ber-tiket MT5 tidak lagi ada di posisi terbuka (`positions_get`) dan tidak memiliki deal penutupan di `history_deals_get`, sistem secara otomatis memeriksa `history_orders_get(ticket=mt5_ticket)`.
     * Jika order berstatus batal/expired dengan `position_id == 0`, trade seketika diselesaikan sebagai **`EXPIRED_MT5`** (`net_r = 0.0`), melepaskan tiket MT5, dan dibersihkan dari daftar trade aktif.
2. **Eliminasi Tiket Hantu dari Dashboard**:
   - `get_active_trades_enriched()` kini otomatis membersihkan tiket MT5 yang tidak aktif bahkan saat `main.py` sedang tidak berjalan.
3. **Verifikasi Suite Test**:
   - `tests/test_shadow_tracker.py` lulus 100% (11/11 PASS).
   - `tests/test_sep8_enhancements.py` & `tests/test_cbss_and_risk_shields.py` lulus 100% (21/21 PASS).

---

## 97. Perubahan 11 September 2026 (Pagi II) — Special G3 Protocol ZCE: Eliminasi Inflasi Skor Mikro, Injeksi Dynamic EMA Bands (20/50/100/200) & Tiered Wall Exhaustion (G3: 0.35x, G2: 0.20x, G1: 0.10x)

### Latar Belakang & Investigasi Kuantitatif:
1. **Diagnosis False Alarm `[WALL EXHAUSTED]` & `[CBSS VETO] Local G3 Wall Collision` pada EURCAD & GBPCHF**:
   - Audit visual dan telemetri menunjukkan bot membatalkan setup atau menahan order di EURCAD dan GBPCHF dengan pesan `[WALL EXHAUSTED] Jarak ke benteng lawan < 0.50x ATR` atau benteng G3 collision.
   - **Akar Masalah 1 (Inflasi Skor ZCE / "G3 Terlalu Murah")**:
     * Pada status quo ZCE, ambang batas `GRADE_3_MACRO` disetel rendah pada skor $\ge 6.5$.
     * Hampir semua level intraday (C1..C4, F1..F3) menyandang status `GRADE_3_MACRO` hanya karena tumpukan indikator mikro H1/M30 (`EQH/EQL/FVG/OB/LAST_HIGH`), padahal **TIDAK memiliki konfluensi struktural swing makro D1/W1**.
     * Level minor berjarak puluhan pips dari harga dianggap "benteng beton makro" yang mematikan peluang kelanjutan.
   - **Akar Masalah 2 (Ketiadaan Dynamic EMA Band di Primitif ZCE)**:
     * Level kunci seperti `1.61000` di EURCAD (tempat beradanya konfluensi EMA 50, EMA 100, dan EMA 200 D1 serta level psikologis bulat) justru ber-status G2 karena modul `_collect_primitives` di `zone_confluence_engine.py` sebelumnya belum pernah menginjeksi EMA ke dalam daftar primitif.
   - **Akar Masalah 3 (Pukul Rata Ambang Wall Exhaustion 0.50x ATR)**:
     * `basket_sync_engine.py` menerapkan filter kaku `runway_atr < 0.50x ATR` secara flat ke semua grade dinding, memperlakukan level rapuh G1/G2 sama dengan dinding beton G3.

---

### Solusi Arsitektur & Perubahan Komponen:
1. **Special G3 Protocol (Syarat Mutlak Benteng Makro Sejati)**:
   - Menaikkan ambang batas skor: `ZCE_GRADE_G2_THRESHOLD = 5.0`, `ZCE_GRADE_G3_THRESHOLD = 8.5`.
   - **Aturan Verifikasi Jangkar Makro (`_assign_cluster_grade`)**:
     * Syarat 1: `score_final >= 8.5`.
     * Syarat 2: Wajib memiliki minimal satu dari jangkar makro sejati:
       - Primitive `LAST_LOW`, `LAST_HIGH`, `SWING_LOW`, `SWING_HIGH`, `EQL`, `EQH`, `OB_BULL`, `OB_BEAR` pada timeframe makro **D1, W1, atau MN1**.
       - Primitive `LAST_LOW`, `LAST_HIGH` pada **H4 dengan horizon deep ($\ge 100$ bar)**.
       - Primitive **`PSYCH_MAJOR`** (level psikologis bulat utama seperti `1.60000`, `1.61000`).
     * Jika skor $\ge 8.5$ namun tidak memiliki jangkar makro sejati di atas, level **di-cap maksimal ke `GRADE_2_INTERMEDIATE`** (eliminasi 100% inflasi skor dari tumpukan mikro).
2. **Injeksi Dynamic EMA Bands (20, 50, 100, 200) di H1, H4, D1**:
   - Menghitung Exponential Moving Average untuk span 20, 50, 100, 200 pada data H1, H4, dan D1.
   - Diberikan bobot proporsional `ZCE_EMA_WEIGHT = 0.25` dengan ketebalan band simetris $0.03\times\text{ATR}$.
   - Mengangkat level konfluensi EMA makro (seperti EURCAD `1.61000`) ke status benteng yang dihormati.
3. **Eksklusif G3 Wall Exhaustion di CBSS (`basket_sync_engine.py`)**:
   - Membatasi status `[WALL EXHAUSTED]` secara eksklusif **HANYA untuk benteng makro sejati `GRADE_3_MACRO`** pada jarak `< 0.35x ATR` (`CBSS_WALL_EXHAUSTION_G3_ATR = 0.35`).
   - Dinding **`GRADE_2_INTERMEDIATE`** dan **`GRADE_1_MICRO`** dinyatakan **bebas ditembus (*penetrable*)** dan tidak lagi memblokir atau men-skip trade kelanjutan meskipun jaraknya rapat ($\le 0.20\text{x ATR}$).
4. **Pembaruan Telemetri Cockpit Dashboard (`dashboard.py`)**:
   - Gate 3 (Systemic Basket & CBSS Guard) hanya memicu status `WAIT (Relay Pause)` saat menempel benteng makro G3.
   - Jika berhadapan dengan level G1/G2, Gate 3 meloloskan status **`PASS (CBSS Cleared)`** dengan anotasi `(G2/G1 Penetrable)`.
5. **Verifikasi Suite Test**:
   - Penambahan unit test baru di `tests/test_zce_special_g3_and_ema.py` (5/5 PASS).
   - Seluruh unit test ZCE eksisting tetap 100% PASS.

---

## 96. Perubahan 11 September 2026 (Pagi) — Reformasi Manajemen Trade M30: Eliminasi Partial Close, BEP 60% TP & 3-Tier Progressive Trailing Ladder (75%→50%, 90%→80%, 95%→90%)

### Latar Belakang & Investigasi Kuantitatif:
1. **Audit Kuantitatif Performa Trade (Demo vs Live vs Shadow Tracker)**:
   - Evaluasi menyeluruh terhadap 68 trade Demo MT5 (58.8% Win, +$130.47), 15 trade Live MT5 (53.3% Win, -$143.49), dan 417 Virtual Shadow Trades.
   - **Diagnosis "Runway Sebenarnya Reachable Tapi Dibunuh Trailing / BEP Prematur"**:
     * Pada sistem lama, Trailing Stop diaktifkan terlalu dini (65% TP) dengan jarak dinamis yang sering kali menabrak noise mikro pasar sebelum mencapai TP penuh.
     * Partial Close (50% volume di 50% TP) memotong potensi laba (MFE median mencapai +242 pts / 2.83x ATR M30), sementara kerugian ditanggung penuh saat terkena SL penuh atau tergerus komisi.
   - **Evaluasi Validitas ZCE & Timeframe M30**:
     * Backtest empiris 5 hari terakhir terhadap $N = 1.005$ titik sentuh dinding ZCE di 26 pair FX membuktikan bahwa level benteng ZCE ($C_1/F_1$) memiliki presisi sniper tinggi:
       - **Median MAE = 0.0 points** (75% posisi memiliki MAE $\le 46$ pts / 0.66x ATR M30).
       - ZCE telah menghitung konfluensi M30 secara native (600 bar M30).
     * Kesimpulan: Entry sniper di dinding ZCE dipertahankan 100%, namun target runway dan pengawalan trade diselaraskan dengan kapasitas gerak intraday M30 (~50–90 pts, Net R:R $\ge 0.50$).

---

### Solusi Arsitektur & Perubahan Komponen:
1. **Eliminasi Total Partial Close (`PARTIAL_CLOSE_ENABLED = False`)**:
   - Menghapus pemotongan volume di tengah jalan agar trade dapat menangkap 100% pergerakan penuh hingga TP.
2. **BEP Diperketat ke 60% TP (`BREAK_EVEN_TRIGGER_TP_PCT = 0.60`)**:
   - Menggeser trigger Break-Even dari 50% ke **60% TP** (+15 pts pocket profit / komisi round-trip broker) guna memberikan ruang nafas bagi wick retracement normal tanpa premature lock.
3. **3-Tier Progressive Trailing Ladder Monotonik**:
   - Menggantikan trailing stop berbasis ATR yang rawan terkena gocekan wick dengan tangga proteksi bertingkat:
     * **Tier 1 (Trigger $\ge 75\%$ TP)**: Mengunci floating profit sebesar **50% TP**.
     * **Tier 2 (Trigger $\ge 90\%$ TP)**: Mengunci floating profit sebesar **80% TP**.
     * **Tier 3 (Trigger $\ge 95\%$ TP)**: Mengunci floating profit sebesar **90% TP** (*Terminal Lock* sebelum sentuhan TP).
4. **Harmonisasi Parameter & Sinkronisasi 1:1**:
   - Diselaraskan di `.env`, `config.py`, `src/analytics/position_manager.py`, `src/analytics/shadow_tracker.py`, dan `src/core/consensus.py`.
   - Menurunkan batas minimum Net R:R Grade B (`GRADE_B_MIN_RR`) ke `0.50` agar setup pantulan dinding M30 terdekat tetap valid dieksekusi.
5. **Verifikasi Suite Test**:
   - Pembuatan unit test komprehensif `tests/test_progressive_trailing_ladder.py` (4/4 PASS).
   - Penyelarasan `tests/test_time_decay_and_vol_regime.py` (7/7 PASS) dan `tests/test_shadow_tracker.py` (11/11 PASS).
   - Seluruh 239 unit test pada suite bot lulus 100% (**Ran 239 tests in 21.4s, OK**).

---

## 95. Perubahan 10 September 2026 (Malam IV) — Pemulihan Multiplier Sesi London ke 1.00x & Sesi New York Flat 0.50x (Bypass Compounding Grade B 0.75x)

### Latar Belakang & Investigasi:
1. **Pereduksian Ganda (*Compounding Double-Discount*) di Sesi New York**:
   - Pada trade USDJPY-ECNc saat sesi New York (18:00–00:00 WIB), lot size dasar dipotong menjadi `0.50x` melalui `_session_lot_multiplier`.
   - Namun, pada blok tier sizing di `risk_engine.py`, setup yang berstatus `GRADE_B` / `REDUCED_CONFIDENCE` dikalikan lagi dengan `0.75x` (`0.50 * 0.75 = 0.375x`), menyebabkan ukuran lot menyusut berlebihan menjadi `0.08` lot.
   - Sesuai prinsip arsitektur, sesi New York dirancang beroperasi pada **flat lot multiplier 0.50x untuk semua grade setup**, tanpa penalti ganda Grade B.
2. **Pemulihan Multiplier Sesi London ke 1.00x**:
   - Parameter `SESSION_LONDON_LOT_MULT` sebelumnya terset `0.75` di `.env` dan `config.py`.
   - Dipulihkan kembali ke standar normal **`1.00x`** (1x penuh).

---

### Solusi Perbaikan Kode & Komponen:
1. **Konfigurasi Multiplier Sesi (`.env`, `config.py`, `dashboard.py`)**:
   - Menyelaraskan `SESSION_LONDON_LOT_MULT=1.00` di `.env` (baris 66 dan 380), `config.py` (baris 748), dan `dashboard.py` (baris 1692).
2. **Helper `is_ny_session` & Bypass Penalti di `risk_engine.py`**:
   - Menambahkan method `is_ny_session()` pada class `RiskEngine`.
   - Pada `get_effective_lot_size()`:
     * Jika berada di sesi New York (`is_ny_session() == True`): penalti `0.75x` untuk `GRADE_B` / `REDUCED_CONFIDENCE` di-bypass total, mengunci lot pada flat `0.50x`.
     * Jika berada di sesi London (`14:00 - 18:00 WIB`): penalti `0.75x` tetap berlaku ($1.00 \times 0.75 = \mathbf{0.75x}$).
     * Jika berada di sesi Asia (`07:00 - 14:00 WIB`): penalti `0.75x` tetap berlaku ($1.20 \times 0.75 = \mathbf{0.90x}$).
3. **Verifikasi Suite Test**:
   - Menambahkan unit test `test_risk_engine_ny_session_flat_multiplier_bypasses_grade_b` di `tests/test_sep8_enhancements.py`.
   - Memperbarui ekspektasi multiplier sesi London di `tests/test_cbss_and_risk_shields.py`.
   - Seluruh test suite (235 unit tests) **100% PASS (Code 0)**.

---

## 94. Perubahan 10 September 2026 (Malam III) — Penyelarasan M2 Pullback Anchor ke Zona ZCE (F1/F2 G1/G2/G3), Anti-Live-Price Clamping & Eliminasi Sorting Flaw abs(price - mid)

### Latar Belakang & Investigasi Insiden EURCAD (22:07 WIB):
1. **Insiden Eksekusi Market di Pucuk pada EURCAD BUY (M2 Pullback)**:
   - Pada pukul 22:07:36 WIB, setup M2 `TREND_ALIGNED_PULLBACK` pada EURCAD terdeteksi dan mengusulkan `BUY_LIMIT @ 1.60613`.
   - Namun, saat dieksekusi di MT5 akun live, order langsung dikonversi menjadi **`MARKET ORDER @ 1.60632`** (membeli di harga pucuk Ask tanpa diskon pullback).
   - Trader/user mencatat:
     * Mengapa pullback order tidak diletakkan di sekitar **`1.60567`** di mana terdapat **ZCE Floor F2 ber-grade G3** yang tepat berkonfluensi dengan **Dynamic EMA20 (`1.60570`)**?
     * Instruksi arsitektur: *"ga harus G3 wall untuk pullback boleh G1, G2, G3 intinya lagi2 rispek ke ZCE nya bukan limit didekat live price. Zona zce ya."*
     * Countertrend di TF makro (H4) diperbolehkan selama H1 bullish dan runway ke $C_1$ memadai, tanpa peduli makro bearish kecuali runway terhadang benteng G3 skor tinggi.

2. **Akar Masalah di `find_ema_confluence_anchor` (`src/analytics/market_scanner.py`)**:
   - **Koleksi Benteng ZCE Tidak Lengkap**: Fungsi hanya membaca `immediate_floor_f1`, dan mengabaikan tangga benteng ZCE lengkap di `strat_dir.layered_floors` / `layered_ceilings` (F1, F2, F3, F4 dengan grade reaksi G1, G2, G3) serta level RBS/SBR makro. Benteng G3 di `1.60567` terlewat dari pencarian.
   - **Cacat Fatal Sorting Key (`abs(price - mid)`)**: Algoritma mengurutkan kandidat menggunakan `(tier_group, abs(price - mid))` yang memprioritaskan level terdekat ke **harga pasar live (`mid`)**. Level mikro di `1.60611` (hanya 2 poin di bawah `mid = 1.60613`) dipilih mengalahkan zona ZCE EMA20 di `1.60567` (jarak 46 poin).
   - **Penyebab Konversi ke Market Order**: Jarak `1.60613` ke Ask (`1.60632`) hanya 19 poin ($< 20$ poin threshold StopsLevel MT5 di `main.py`), sehingga pending limit order otomatis dieksekusi sebagai Market Order instan.

---

### Solusi Perbaikan Kode & Komponen:
1. **Koleksi Komprehensif Seluruh Benteng ZCE (G1, G2, G3)**:
   - Mengambil seluruh benteng dari `strat_dir.layered_floors` (BUY) dan `strat_dir.layered_ceilings` (SELL) beserta grade reaksinya (`G1`, `G2`, `G3`).
   - Mengumpulkan seluruh level ZCE makro (`floor_f1`, `floor_f2`, `macro_floor_f2`, `deep_target_floor_f2`, `macro_rbs_d1`, `inter_rbs_h4`, `micro_rbs_h1`, `cluster_support`, dll) dengan deduplikasi harga toleransi $\le 3\text{ pts}$.
2. **Anti-Live-Price Clamping**:
   - Menetapkan `min_pullback_gap = max(0.12 * atr_val, 15.0 * pt)`.
   - Memisahkan kandidat yang memiliki kedalaman pullback struktural (`deeper_cands = [c for c in valid_cands if abs(c[0] - mid) >= min_pullback_gap]`). Jika kandidat struktural di dalam koridor EMA tersedia, algoritma WAJIB mengabaikan level mikro yang menempel pada live price agar pending limit benar-benar menunggu retrace ke zona ZCE.
3. **Penyelarasan Sorting Key ke Konfluensi EMA20 (`abs(price - ema20)`)**:
   - Kandidat diurutkan berdasarkan:
     1. Prioritas Struktural: `tier_group 0` (SMC OB & ZCE Walls G1/G2/G3) > `tier_group 1` (SMC FVG) > `tier_group 2` (Dynamic EMA20 & Atlas Psych).
     2. Jarak ke garis basis EMA20: `dist_to_ema20 = abs(price - ema20)`. Benteng ZCE yang berhimpitan dengan EMA20 (seperti `1.60567` pada EURCAD) menang mutlak.
4. **Penjagaan Batas Limit Entry di Evaluasi M2 BUY / SELL**:
   - M2 BUY: `lim_entry = min(base_floor + (spread_pts * 0.5 * pt), mid - (spread_pts * 0.5 * pt)) if mid > base_floor else base_floor`.
   - M2 SELL: `lim_entry = max(base_ceiling - (spread_pts * 0.5 * pt), mid + (spread_pts * 0.5 * pt)) if mid < base_ceiling else base_ceiling`.
   - Menjamin bahwa limit order selalu berada di sisi limit (di bawah harga pasar untuk BUY, di atas harga pasar untuk SELL), mengeliminasi risiko konversi prematur ke Market Order.
5. **Verifikasi Suite Test**:
   - Menambahkan unit test `test_m2_pullback_anchors_to_zce_g3_and_avoids_live_price_clamping` di `tests/test_m2_pullback_and_corridor.py`.
   - Seluruh test suite (234 unit tests) **100% PASS (Code 0)**.

---

## 93. Perubahan 10 September 2026 (Malam II) — Penyelarasan M1B Murni Berbasis Respek Zona ZCE, Eliminasi Runaway Limit Placement & Penonaktifan Unilateral Pending CSM Cancel

### Latar Belakang & Diagnosa Insiden EURUSD & CADJPY:
1. **Insiden CADJPY Pending Cancel (`[THESIS FAILURE CANCEL]`)**:
   - Order pending `SELL_LIMIT` pada CADJPY (setup M2 Pullback) dipasang pada 21:44:39 WIB, namun 3 detik kemudian langsung dibatalkan sepihak oleh bot dengan alasan `Systemic CSM Flow reversed strongly to Bullish (+3.69 >= +1.00)`.
   - **Akar Masalah**: Meskipun filter entry CSM (`ENABLE_CSM_FLOW_FILTER=false`) dan dynamic bailout (`ENABLE_CSM_DYNAMIC_BAILOUT=false`) sudah dinonaktifkan, parameter `ENABLE_PENDING_CSM_CANCEL=true` tertinggal masih aktif di `.env` (baris 216) dan `config.py` (baris 950) dengan ambang rendah `1.00`. Akibatnya, pending limit teknikal non-sistemik dimatikan oleh noise CSM delta pair cross.
2. **Insiden EURUSD Buy Limit di Pucuk / Eksekusi Market di SBR (`1.16256 - 1.16269`)**:
   - Radar mendeteksi setup M1B `TREND_ALIGNED_INDUCED_SWEEP` BUY dan mengusulkan `BUY_LIMIT @ 1.16256`, namun saat dieksekusi dikonversi ke `MARKET ORDER @ 1.16269` menabrak resisten SBR bekas support yang baru jebol di sesi sore.
   - **Investigasi Akar Masalah di `market_scanner.py`**:
     * **Bug Placement Limit (`mid - 0.15*ATR`)**: Baris 4097 menggunakan rumus `limit_entry = max(anchor_lvl, mid - 0.15*ATR)`. Ketika harga pasar (`mid`) sudah reli jauh meninggalkan lantai support ZCE $F_1$ (`1.16151`), rumus ini secara keliru menyeret entri naik ke pucuk reli (`1.16256`). Karena selisih jarak ke ask live hanya 1.3 pips ($< 2.0$ pips), `main.py` mengonversinya menjadi Market Order.
     * **Asymmetric Reclaim Window (Runaway Blindness)**: Syarat `has_reclaim` BUY hanya mengecek batas bawah (`mid >= anchor_lvl - 0.10*ATR`) tanpa batas atas. Sapuan likuiditas yang sudah selesai 1–2 jam lalu dan harganya sudah melesat $1.3\times\text{ATR}$ ke atas masih dianggap sebagai "sweep aktif".
     * **Distorsi Clearance Anchor**: Di `find_m1b_zce_basing_anchor`, parameter `min_clearance = max(0.20*ATR, 50 pts)` memaksa pencarian mengabaikan support ZCE lokal terdekat (jarak $<50$ pts) dan melompat ke support multi-hari 335 pts di bawahnya.

---

### Solusi Perbaikan Kode & Komponen:
1. **Penonaktifan Unilateral Pending CSM Cancel**:
   - Menyelaraskan `.env` (baris 216) dan `config.py` (baris 950): `ENABLE_PENDING_CSM_CANCEL = False`.
   - Pembatalan pending order teknikal non-sistemik kini murni dikendalikan oleh *Structural Invalidation* (candle M15 *close* menembus lantai/plafon invalidasi), *Target Proximity Expiration* ($\ge 75\%$ TP tanpa terisi), dan *Timeout* (60 menit).
2. **Penyelarasan M1B Murni Berbasis Respek Zona ZCE (`market_scanner.py`)**:
   - **Penempatan Limit di Anchor ZCE Sejati**:
     * BUY: `limit_entry = round(anchor_lvl + (spread_pts * 0.5 * pt), digits)` (menunggu di lantai $F_1$ / RBS yang di-sweep).
     * SELL: `limit_entry = round(anchor_lvl - (spread_pts * 0.5 * pt), digits)` (menunggu di plafon $C_1$ / SBR yang di-sweep).
     * Menghapus total rumus runaway `mid +/- 0.15*ATR` yang menyeret entri ke pucuk/lembah.
   - **Batas Toleransi Kedekatan ZCE (*ZCE Proximity Guard*)**:
     * BUY: `(anchor_lvl - 0.15*ATR) <= mid <= (anchor_lvl + 0.35*ATR)`. Jika harga sudah terbang $> 0.35\times\text{ATR}$ di atas lantai $F_1$, sweep otomatis dibatalkan sebagai *Runaway Sweep*.
     * SELL: `(anchor_lvl - 0.35*ATR) <= mid <= (anchor_lvl + 0.15*ATR)`.
   - **Normalisasi Clearance Anchor**: Mengembalikan `min_clearance = max(0.05 * atr_val, 5 * pt)` agar ZCE dapat mengenali lantai/plafon lokal yang sedang diuji tanpa melompat jauh ke level multi-hari.
   - **SL Terlindung di Balik Benteng ZCE**: SL BUY dihitung dari `min(live_l, anchor_lvl)` sehingga SL tidak lagi mengambang di atas support.
3. **Verifikasi Test Suite & Isolasi Hermetik**:
   - Menambahkan unit test M1B proximity guard & anchor limit placement pada `tests/test_m1b_sweep.py`.
   - Menambahkan isolasi hermetik `shadow_tracker.active_trades` pada `tests/test_market_scanner.py`.
   - Seluruh test suite (233 unit tests) **100% PASS (Code 0)**.

---

## 92. Perubahan 10 September 2026 (Malam) — Rework M4: Pure Technical Breakout Continuation (DBD/RBR Micro-Basing), CSM Telemetry Decoupling & Koreksi Mid-Chamber Trap Veto

### Latar Belakang & Investigasi Empiris:
1. **Audit Drawdown Hari Ini & Evaluasi CSM (Boitoki Currency Strength Matrix)**:
   - Evaluasi performa Virtual Paper Trade (Shadow Tracker) mendapati penurunan performa hari ini (-6.56R, 14 loss) dibanding 3 hari sebelumnya (+1.51R, +15.38R, +17.39R).
   - Analisis mendalam telemetri 90 trade riil pada akun live MT5 membuktikan:
     * **Trade CSM OPPOSED saat Open** (membuka posisi saat harga sedang diskon melawan momentum CSM sesaat): 18 trade, **WinRate 66.7%**, P/L bersih **+$130.78**.
     * **Trade CSM ALIGNED saat Open** (membuka posisi mengejar momentum searah CSM): 69 trade, **WinRate 55.1%**, P/L bersih **-$914.84**.
   - Kesimpulan matematis: Menjadikan CSM sebagai *hard veto leading indicator* menyaring trade menang yang sedang pullback dan memaksa bot membeli di pucuk / menjual di lembah. Selain itu, fitur `CSM Dynamic Flow Bailout` memotong dini posisi secara prematur (misal EURUSD -$25.48 dan USDCHF -$18.17) akibat fluktuasi sesaat M15 sebelum invalidasi teknikal tersentuh.
2. **Rekonseptualisasi M4 (Breakout Continuation vs Systemic Flow)**:
   - Generator sinyal M4 sebelumnya bergantung pada rolling 720-bar currency z-score `zb`/`zq`.
   - Pola alami M4 sejatinya adalah aksi harga lokal: kelanjutan dari breakout impulsif yang membentuk *high-tight / low-tight micro-basing* (RBR = Rally-Base-Rally, DBD = Drop-Base-Drop), bukan sekadar kuantitas flow mata uang global.
3. **Koreksi Mid-Chamber Trap Veto**:
   - Veto konsolidasi tengah chamber di MSE sangat bermanfaat untuk M1 (Sweep) guna mencegah *internal chop fakeout*.
   - Namun, memblokir seluruh trade di mid-chamber merusak M2 (Pullback EMA50) dan M4 (Micro-Basing Continuation) yang secara alami bertumpu pada konsolidasi di paruh tengah dealing range.

---

### Solusi Perbaikan Kode & Komponen:
1. **Rework Generator M4 (`_detect_m4_breakout_continuation` di `market_scanner.py`)**:
   - **RBR (BUY)**: Candle H1 impulsif ($Close > Open$, body ratio $\ge 50\%$) menembus *recent swing high* 20-bar $\rightarrow$ diikuti *High-Tight Basing* 2–6 bar (range $\le 0.35\times\text{ATR}$ H1, lantai basing bertahan di paruh atas breakout bar) $\rightarrow$ emisi pending `buy_limit` di atap basing (`base_ceil`).
   - **DBD (SELL)**: Candle H1 impulsif ($Close < Open$, body ratio $\ge 50\%$) menembus *recent swing low* 20-bar $\rightarrow$ diikuti *Low-Tight Basing* 2–6 bar (range $\le 0.35\times\text{ATR}$ H1, atap basing bertahan di paruh bawah breakdown bar) $\rightarrow$ emisi pending `sell_limit` di lantai basing (`base_floor`).
   - Penentuan SL presisi di balik basing box ditambah safety floor & ZCE next barrier targeting ($C_1/C_2$ atau $F_1/F_2$).
2. **Pemisahan Definitif Systemic Flow sebagai Layer 0**:
   - M4 murni berbasis pola chart teknikal OHLC lokal pair.
   - *Systemic Flow* tetap hidup mandiri di Layer 0 (`get_systemic_flow_regime`, `evaluate_systemic_basket_lock`, dan `CBSS Basket Concurrency Cap`), tanpa mem-veto order teknikal individual.
3. **Penonaktifan CSM Hard Veto & Dynamic Bailout (Mode Telemetri / Observasi)**:
   - Diselaraskan di `.env` dan `config.py`: `ENABLE_CSM_FLOW_FILTER = False` dan `ENABLE_CSM_DYNAMIC_BAILOUT = False`.
   - Gate 4/5 di Dashboard Cockpit menampilkan status **`OBSERVE` (Cyan)** informatif tanpa memblokir eksekusi.
4. **Pembebasan M2 dan M4 dari Mid-Chamber Trap Veto**:
   - Di `_is_direction_allowed()` (`market_scanner.py`), penolakan mid-chamber trap dipertahankan untuk M1 dan M3 di batas chamber, namun dilewati (`continue`) untuk M2 (Pullback) dan M4 (Basing Continuation).
5. **Sinkronisasi Feed Dashboard Real-Time (`get_radar_standbys` di `market_scanner.py`)**:
   - Menghubungkan fungsi `get_radar_standbys()` ke generator `_detect_m4_breakout_continuation()`:
     * Saat setup RBR / DBD aktif, emisi standby bertipe `"M4"` dengan harga entry limit basing box, status `WAITING_BASING_RETEST`, dan vektor trajektori 3-titik (*origin* $\rightarrow$ *retest* $\rightarrow$ *target* TP1/TP2 ZCE).
     * Dashboard chart Lightweight Charts otomatis menggambar reticle garis putus-putus warna hijau zamrud (`#34d399`) beserta panah trajektori, dan Watchlist merender badge pill `M4:BASING`.
     * Mempertahankan fallback observasi Layer 0 SFR Shock (`_m4_state`) jika belum ada pola teknikal basing matang pada sisi tersebut.
6. **Verifikasi Unit Test Suite**:
   - Dibuat suite baru `tests/test_m4_breakout_continuation.py` (4 test: RBR, DBD, rejection basing melebar, dan validasi emisi standby trajektori M4 untuk dashboard).
   - Seluruh pengujian unit test suite di repositori: **100% PASS (Code 0)**.

---

## 91. Perubahan 10 September 2026 (Sore III) — Pelepasan Belenggu Anti-Internal Hedge & Restorasi Seleksi Berbasis Struktur Alami (ZCE Runway, MSE Structure & G3 Wall Clearance)

### Latar Belakang & Evaluasi Operasional:
1. **Dampak Penolakan Masif Gate Anti-Internal Hedge**:
   - Audit log radar mengungkap `[CBSS ANTI-HEDGE]` melakukan penolakan masif (801 penolakan, mencakup 75.3% universe).
   - Larangan kaku aljabar silang mata uang memblokir peluang berkualitas tinggi di satu pair hanya karena pair lain di keranjang yang sama memegang eksposur berlawanan (misalnya memblokir `GBPCHF BUY` hanya karena memegang `EURGBP BUY` yang secara teknikal merupakan short GBP di pair lambat Eropa).
2. **Restorasi Prinsip Eksekusi Alami**:
   - Solusi sejati untuk anomali historis (seperti USDCAD) adalah **Local G3 Wall Veto** dan **ZCE Runway Clearance**, bukan melarang trade searah struktur.
   - Sesuai arahan arsitektur, fitur Anti-Internal Hedge dinonaktifkan (`ENABLE_ANTI_INTERNAL_HEDGE=false`) agar sistem kembali mengevaluasi peluang secara alami berlandaskan ZCE Runway, struktur MSE HTF, dan Local Wall Clearance.

---

### Solusi Perbaikan Kode & Hasil Live MT5:
1. **Konfigurasi (`config.py` & `.env`)**:
   - Menyelaraskan `ENABLE_ANTI_INTERNAL_HEDGE=false` di `.env` (single source of truth) dan `config.py`.
2. **Verifikasi Live MT5 & Pembukaan Posisi Alami**:
   - Begitu bot direstart, radar Stage 1 langsung mendeteksi dan mengeksekusi order `GBPCHF-ECNc` (Ticket #1282261758, BUY 0.17 lot @ 1.09725, SL 1.09536, TP 1.10045, R:R 1.69:1).
   - Lot terhitung presisi menerapkan de-risking Sesi London ($0.2334 \times 0.75x = 0.17\text{ lot}$).
   - Log `gate_debug.log` terkonfirmasi 100% bebas dari penolakan `[CBSS ANTI-HEDGE]`.
3. **Penyelarasan Unit Test Suite (`tests/test_basket_relay.py` & `tests/test_anti_internal_hedge.py`)**:
   - Memutakhirkan `test_portfolio_conflict_blocking` dengan fixture `monkeypatch.setattr(config, "ENABLE_ANTI_INTERNAL_HEDGE", True)` agar fungsionalitas algoritma tetap teruji mandiri saat diaktifkan.
   - Seluruh 40 test di seluruh suite rekonsiliasi dan proteksi risiko: **100% PASS**.

---

## 90. Perubahan 10 September 2026 (Sore II) — Rekonsiliasi Holistik: Session De-Risk Sizing, Runway Decoupling CBSS, Dynamic Tokyo Lull, NY M3 Virtual Paper Route & Anti-CLI Noise Suppression

### Latar Belakang & Investigasi Mendalam:
1. **Asimetri Payout Sesi London**:
   - Audit data telemetry mendapati Sesi Asia mencetak WR 70.0% (+$460.98), sedangkan Sesi London mencetak WR 56.2% namun merugi net -$757.80.
   - Evaluasi payout London mengungkap 18 win rata-rata +$33.5 vs 14 loss rata-rata -$97.3 (rasio loss : win = 2.9 : 1).
   - Masalah utama bukan pada akurasi entry, melainkan ukuran loss per tiket yang membengkak di sesi pasar Barat. Solusi struktural adalah de-risking sizing per sesi, bukan menambah gate momentum.
2. **CBSS Runway Deadlock & Chamber Shrinkage**:
   - Ditemukan 4.285 baris penolakan `[CBSS RUNWAY]` di `gate_debug.log`. Ambang kaku $1.20\times\text{ATR}$ memblokir setup chamber M2/M3 intraday yang secara alami berosilasi di rentang $0.80\times - 1.00\times\text{ATR}$.
3. **M3 Sesi New York (Sampel Tipis N=5)**:
   - Data NY M3 menunjukkan 1W-4L (-$233.62), namun $N=5$ (Wilson CI $[3.6\%, 62.5\%]$) belum memenuhi syarat kuantitatif $N \ge 60$ untuk veto keras permanen.
4. **CLI Spamming Alert Box pada Trade Paper yang Sudah Berjalan**:
   - Setiap cycle radar (60s), simbol paper-only (XAUUSD, BTCUSD) atau simbol yang terkena limit keranjang (AUDCAD) terus menerus merender alert box bento raksasa dan mencetak ulang status paper trade, mengaburkan log terminal.

---

### Solusi Perbaikan Kode & Komponen:
1. **Fase 1 — Session Sizing De-Risk (`risk_engine.py`, `config.py`, `.env`)**:
   - Multiplier lot per sesi diselaraskan: Asia 1.20x, London 0.75x, New York 0.50x.
   - Di `risk_engine.py`, multiplier sesi $< 1.0$ berlaku sebagai hard cap: `effective_mult = min(vol_mult, sess_mult)`.
   - Logika overlap sesi di `_check_session` diubah untuk memilih multiplier terendah/paling defensif.
2. **Fase 2 — Runway Decoupling & CBSS Sync (`market_scanner.py`, `basket_sync_engine.py`)**:
   - Ambang runway CBSS dipisahkan: M4 Systemic Flow tetap $\ge 1.20\times\text{ATR}$ (`CBSS_MIN_RUNWAY_ATR`), sementara setup chamber M2/M3 memakai $\ge 0.60\times\text{ATR}$ (`CBSS_MIN_CHAMBER_RUNWAY_ATR`).
   - Memfungsikan parameter `hour_wib` di `filter_and_rank_batch_candidates` untuk session driver confluence (+0.20 skor pada keranjang mata uang primer aktif).
   - Memindahkan evaluasi Tokyo Midday Lull keluar dari blok CBSS ke layer sesi independen.
3. **Fase 3 — Dynamic Tokyo Lull & ZCE Adaptive Floor (`zone_confluence_engine.py`, `dashboard.py`)**:
   - Tokyo Lull diubah dari 25p statis menjadi dinamis $\max(0.40\times\text{ATR}, 12\text{p})$.
   - Penyelarasan ZCE Natural Chamber di `zone_confluence_engine.py`: `pip_floor = 8.0 * pip_val`, `pip_sep = max(pip_floor, min(15.0 * pip_val, 0.75 * atr_h1))`.
   - Dashboard Cockpit: Menambahkan visualisasi Chamber Height (`chamber_pips`, `chamber_atr`), badge sesi dinamis, dan sinkronisasi threshold layer.
4. **Fase 4 — NY M3 Paper Route & Anti-CLI Noise Suppression (`main.py`, `shadow_tracker.py`, `shadow_report.py`)**:
   - Setup M3 Breakout Retest di sesi NY ($\ge 18:00$ WIB) dialihkan ke Virtual Paper Trade dengan disposisi `SKIPPED_NY_M3_PAPER` (0 token API, 0 risiko modal MT5, mengumpulkan sampel menuju $N \ge 60$).
   - Menambahkan guard deduplikasi di awal `run_scanner_trading_cycle` di `main.py`: jika simbol paper-only atau terblokir risk/CBSS sudah memiliki order aktif/pending di `shadow_tracker`, rendering alert box raksasa di-bypass total untuk menjaga kebersihan log CLI.
   - Integrasi disposisi `SKIPPED_NY_M3_PAPER` pada tabel dan breakdown laporan virtual `shadow_report.py`.
5. **Verifikasi Unit Test**:
   - Dibuat suite baru `tests/test_session_adaptive_reconciliation.py` (5 test).
   - Seluruh 33 test unit suite (`test_session_adaptive_reconciliation.py`, `test_cbss_and_risk_shields.py`, `test_basket_relay.py`, `test_zce_chamber_clearance.py`, `test_time_decay_and_vol_regime.py`): **100% PASS**.

---

## 89. Perubahan 10 September 2026 (Sore) — Lead-Lag Liquidity Relay Engine (Estafet Likuiditas) & Zero-Opposing Currency Basket Coordinator

### Latar Belakang & Analisis Flaw Sistemik:
1. **Penyebab Terjadinya Triangulation Paradox & Self-Cannibalization**:
   - Selama transisi Tokyo/London, scanner mendeteksi EURAUD SELL (Short EUR), EURNZD BUY (Long EUR), dan AUDNZD BUY (Long AUD).
   - Penyelidikan mengungkap bahwa `MarketScanner.scan_fast_radar()` memproses kandidat secara sekuensial pair per pair (*first-come first-served race condition*). Pair yang berada di urutan alfabet awal langsung mengunci tiket tanpa koordinasi keranjang.
   - Meskipun fungsi `select_basket_champion()` telah ada di `basket_sync_engine.py`, fungsi tersebut bersifat dorman (tidak pernah dipanggil di dalam loop scanner).
2. **Ketiadaan Mekanisme Estafet Likuiditas (Lead-Lag Liquidity Relay)**:
   - Ketika modal institusional membanjiri sebuah mata uang (misal EUR Inflow), pair dengan volatilitas tertinggi (Leader, misal EURAUD) melesat lebih dulu hingga menabrak benteng ZCE ($C_1/C_2$).
   - Di titik benteng ini, ruang gerak fisik (*runway*) pair Leader menipis hingga habis ($< 0.50\times\text{ATR}$), dan harga mulai mengalami absorpsi/konsolidasi.
   - Tanpa koordinasi keranjang, sistem rentan mengejar BUY yang mepet dinding atau mencoba memudarkan SELL yang melawan momentum makro.
   - Sebaliknya, modal institusional berpindah (estafet) ke pair laggard dalam keranjang yang sama (misal EURNZD atau EURGBP) yang baru memantul dari Support $F_1$ dan memiliki ruang gerak ZCE lapang ($\ge 1.20\times\text{ATR}$).

---

### Solusi Perbaikan Kode & Komponen Utama:
1. **`src/analytics/basket_sync_engine.py`**:
   - **Fungsi Batch Coordinator `filter_and_rank_batch_candidates()`**:
     * **Tahap 1 (Pengecualian Non-Fiat)**: Aset crypto (BTC) dan komoditas (XAU) lolos langsung tanpa terikat aturan basket fiat.
     * **Tahap 2 (Anti-Internal Currency Hedge)**: Memvalidasi seluruh usulan terhadap portofolio MT5 aktif via `check_basket_directional_conflict()`. Dilarang keras membuka posisi yang berlawanan arah mata uang dengan trade aktif.
     * **Tahap 3 (Physical ZCE Runway & Wall-Exhaustion Skip)**: Mendeteksi jika pair mepet benteng lawan ($\text{Runway Ratio} < 0.50\times\text{ATR}$ atau Local G3 Veto). Pair diberi label `WALL_EXHAUSTED` dan di-skip dari eksekusi.
     * **Tahap 4 (Resolusi Konflik Intra-Batch via Composite Currency Vector)**: Menggunakan tanda aljabar Boitoki CSM (`CSM > 0` = Bullish, `CSM < 0` = Bearish) sebagai wasit netral jika muncul usulan berlawanan dalam 1 batch scan (misal EUR Long vs EUR Short). Proposal yang melawan arah makro digugurkan sebelum seleksi champion.
     * **Tahap 5 (Seleksi Basket Champion)**: Memilih tepat 1 Champion terbaik per keranjang mata uang berdasarkan skor komposit: $\text{Skor} = (\text{Runway} \times 0.45) + (\text{CSM Alignment} \times 0.35) + (\text{Chamber Clearance} \times 0.20)$.
   - **Kalkulasi Runway Fleksibel pada Breached Wall / Blue Sky Breakout**:
     * Memperbarui `calculate_pair_runway()` untuk menangani kondisi penembusan benteng $C_1/F_1$. Jika harga telah menembus $C_1$ pada BUY setup, target dialihkan ke $C_2$, atau dinilai sebagai ekspansi unconstrained ($2.5\times\text{ATR}$) alih-alih keliru menganggap runway bernilai 0.
2. **`src/analytics/market_scanner.py`**:
   - Memutakhirkan `scan_fast_radar()`: Mengumpulkan seluruh sinyal awal dalam list batch `candidates`, mengalirkannya ke `filter_and_rank_batch_candidates()`, dan hanya meneruskan kandidat Champion ke tahap cooldown dan eksekusi MT5.
3. **`dashboard.py`**:
   - Mengintegrasikan deteksi `WALL_EXHAUSTED` pada Gate 3: Menampilkan status `WAIT` dengan deskripsi `Relay Pause: Wall Proximity` saat pair mepet benteng lawan ($< 0.50\times\text{ATR}$), serta menampilkan `PASS` dengan metrik `Runway X.Xx ATR` saat jalur lapang.
4. **Unit Test Suite Baru (`tests/test_basket_relay.py`)**:
   - 5 skenario uji: Resolusi konflik intra-batch via CSM sign, penolakan hedging terhadap posisi portofolio, skip wall-exhaustion, seleksi laggard champion berdasarkan runway terlebar, dan pengecualian independen BTC/XAU (5/5 PASS).
   - Seluruh 266 unit test suite di repositori: **100% PASS**.

---

## 88. Perubahan 10 September 2026 (Siang/Sore IV) — Implementasi Anti-Internal Currency Hedge Gate (CBSS & Risk Engine) & Eliminasi Kanibalisasi Posisi Silang

### Latar Belakang & Masalah Sistemik:
1. **Anomali Triad Paradox (EURNZD BUY, EURAUD SELL, AUDNZD BUY)**:
   - Teramati pada portofolio aktif MT5 live: akun memegang posisi `EURNZD-ECNc` BUY (Long EUR, Short NZD) sekaligus `EURAUD-ECNc` SELL (Short EUR, Long AUD) dan `AUDNZD-ECNc` BUY (Long AUD, Short NZD).
   - Dekomposisi matematis menunjukkan bahwa eksposur EUR bernilai 0 (Netral / Hedged against itself), memicu kanibalisasi internal profit dan membebani akun dengan biaya spread/komisi ganda.
   - Selain itu, kombinasi `EURNZD BUY` + `EURAUD SELL` secara sintetis sama dengan `AUDNZD BUY`, menyebabkan portofolio memegang eksposur Long AUDNZD rangkap dua (*synthetic redundancy*).
2. **Celah Logika CBSS Concurrency Cap Sebelumnya**:
   - Fungsi `check_basket_concurrency_cap()` hanya membatasi kuota trade yang *searah* (`item_dir == direction`, max 2).
   - Sistem belum memiliki aturan *Anti-Internal Currency Hedge*: tidak ada filter yang melarang membuka trade berlawanan arah pada mata uang yang sama yang sudah aktif di portofolio.

---

### Solusi Perbaikan Kode & Konfigurasi:
1. **`config.py` & `.env`**:
   - Menambahkan konfigurasi `ENABLE_ANTI_INTERNAL_HEDGE=true`.
2. **`src/analytics/basket_sync_engine.py`**:
   - Menambahkan fungsi `check_basket_directional_conflict(symbol, direction, active_positions, active_orders) -> Tuple[bool, str]`.
   - Mengurai dekomposisi mata uang Base dan Quote dari calon order dan membandingkannya dengan seluruh posisi dan order aktif.
   - Jika terdeteksi adanya mata uang dengan tanda berlawanan (`cand_sign * p_sign < 0`), order langsung ditolak dengan alasan `[CBSS ANTI-HEDGE]`. Simbol kripto dan emas dikecualikan secara deterministik.
3. **`src/analytics/market_scanner.py`**:
   - Di `_is_direction_allowed()`, menambahkan evaluasi `check_basket_directional_conflict()`. Setup yang memicu pertentangan mata uang dengan posisi terbuka langsung di-`HARD_BLOCK` di Stage 1 radar.
4. **`src/core/risk_engine.py`**:
   - Mengupdate `can_trade(symbol, action)` dan menambahkan helper `_check_anti_internal_hedge(symbol, action)` sebagai rem pengaman lapis kedua sebelum pengiriman order ke MT5.
5. **`main.py` & `dashboard.py`**:
   - Di `main.py`: menambahkan evaluasi anti-hedge sebelum dispatch Stage 2 dan meneruskan parameter `action` ke `risk.can_trade()`.
   - Di `dashboard.py`: Gate 3 (Systemic Basket & CBSS Guard) mengevaluasi `check_basket_directional_conflict()` dan menampilkan status `BLOCK` berlatar merah dengan deskripsi `Anti-Internal Currency Hedge Veto` saat terjadi konflik eksposur.
6. **Unit Test Suite (`tests/test_anti_internal_hedge.py`)**:
   - 6 test case baru: penolakan EURAUD SELL saat EURNZD BUY aktif, penerimaan AUDNZD BUY saat EURNZD BUY aktif, penolakan GBPJPY BUY saat CADJPY SELL aktif, penerimaan USDJPY SELL saat CADJPY SELL aktif, pengecualian BTC/XAU, serta integrasi `RiskEngine.can_trade()`.
   - Seluruh 224 unit test repositori: **100% PASS**.

---

## 87. Perubahan 10 September 2026 (Siang/Sore III) — Pengetatan CSM Flow Opposition Gate, M3 Pre-Breakout/Breakdown Context Validator, & Re-Aktivasi Pending CSM Cancellation

### Latar Belakang & Analisis Forensik:
1. **Analisis Eksekusi EURAUD SELL (#1281471103) & AUDNZD BUY (#1281471141)**:
   - Posisi `AUDNZD-ECNc` BUY terkena full Stop Loss setelah aliran Net CSM berbalik tajam menjadi berlawanan (`csm_delta = -1.13` melemah).
   - Posisi `EURAUD-ECNc` SELL terpicu pada harga `1.61238` saat arus mata uang EUR sedang menguat tajam terhadap AUD (`csm_delta = +1.79` berlawanan arah SELL).
   - Penyelidikan mengungkap dua celah mendasar:
     * **Duplicate Key `.env`**: Baris 59 memiliki `ENABLE_CSM_FLOW_FILTER=true`, namun baris 211 `ENABLE_PENDING_CSM_CANCEL=false` dan baris 212 `ENABLE_CSM_FLOW_FILTER=false` menimpa nilai sebelumnya saat runtime sehingga hard gate CSM berada dalam mode pasif/telemetri.
     * **Bypass `is_aligned` di Radar**: Pada `market_scanner.py:3332`, filter CSM memiliki syarat `if is_csm_opposed and not is_aligned and not is_sfr_pro:`. Karena bias makro EURAUD adalah bearish expansion (`bias_score = -0.50`), `is_aligned` bernilai True, yang meloloskan trade kelanjutan (M3 Breakdown / M2 Pullback) meskipun arus mata uang riil sedang melonjak tajam melawan arah trade.
2. **False Breakdown Misclassification pada M3 (Support/Resistance Inversion Fallacy)**:
   - Level `1.61238` pada EURAUD adalah swing low lama dari bar ke-45 (~100 bar lalu).
   - Dalam 3–5 bar sebelum spike ke `1.61393`, 100% harga penutupan berada di bawah `1.61238` (level tersebut berfungsi sebagai Resistance/Plafon, bukan Support/Lantai).
   - Ketika candle jam 08:00 WIB menusuk ke atas `1.61393` dan candle jam 09:00 WIB ditutup kembali di bawah `1.61238`, M3 salah mengklasifikasikannya sebagai *Support Breakdown Retest* padahal kenyataannya itu adalah *Resistance Liquidity Sweep (Bull Trap / SFP)* yang seharusnya ditangani oleh M1.

---

### Solusi Perbaikan Kode & Konfigurasi:
1. **`.env` & `config.py`**:
   - Menghapus override duplikat dan menetapkan `ENABLE_CSM_FLOW_FILTER=true`.
   - Mengaktifkan pembatalan pending limit order saat arus berbalik: `ENABLE_PENDING_CSM_CANCEL=true`.
   - Menyelaraskan ambang batas CSM di seluruh file ke desimal konsisten: `CSM_FLOW_OPPOSED_THRESHOLD=1.50` dan `PENDING_CSM_OPPOSED_THRESHOLD=1.00`.
2. **`src/analytics/market_scanner.py`**:
   - **Pengetatan Gate CSM di `_is_direction_allowed()`**: Menghapus bypass `not is_aligned`. Setup kelanjutan (M2 Pullback, M3 Breakout Retest) diblokir keras (`HARD_BLOCK`) jika `is_csm_opposed` aktif ($|\Delta| \ge 1.50$). Pengecualian hanya diberikan kepada M1 Universal Liquidity Sweep / SFP (yang memang bertujuan memudarkan sweep ekstrem) dan M4 Systemic Flow (`is_sfr_pro`).
   - **Pre-Breakout & Pre-Breakdown Context Validator pada M3**:
     * **M3 SELL (Support Breakdown)**: Menginspeksi 3–5 bar sebelum candle breakdown. Jika $\ge 60\%$ bar sebelumnya ditutup di bawah level target, level tersebut diverifikasi sebagai resistance (bukan support). Kandidat langsung di-veto (`[M3 SELL SWEEP VETO]`) dan diserahkan ke mekanisme M1.
     * **M3 BUY (Resistance Breakout)**: Menginspeksi 3–5 bar sebelum candle breakout. Jika $\ge 60\%$ bar sebelumnya ditutup di atas level target, level tersebut diverifikasi sebagai support (bukan resistance). Kandidat di-veto (`[M3 BUY SWEEP VETO]`).
3. **`dashboard.py`**:
   - Menyelaraskan Gate 5 CSM Flow Opposition dengan membaca `config.CSM_FLOW_OPPOSED_THRESHOLD` (alih-alih nilai hardcode `1.0`).
4. **Unit Test Suite (`tests/test_csm_and_m3_context_guard.py`)**:
   - Menambahkan pengujian komprehensif untuk validasi pemblokiran CSM pada trade kelanjutan, pengecualian M1/M4, veto sweep palsu pada M3 SELL & BUY, serta penerimaan breakdown/breakout yang sah.
   - Seluruh 218 unit test sistem: **100% PASS**.

---

## 86. Perubahan 10 September 2026 (Siang/Sore II) — Re-Aktivasi XAUUSD & BTCUSD Virtual Paper Trade Only, Karantina Total MT5 Live & Integrasi X-Ray Dashboard

### Latar Belakang & Keputusan Pengguna:
1. **Re-Aktivasi XAUUSD & BTCUSD Khusus Virtual Paper Trade**:
   - Pengguna meminta untuk mengaktifkan kembali pemindaian pasar untuk `XAUUSD-ECNc` (weekday) dan `BTCUSD.c` (full 24/7) murni di **Virtual Paper Trade (`shadow_tracker`)** tanpa risiko modal apa pun di MT5 live (0 token API LLM, 0 order MT5).
   - Simbol emas dan kripto wajib dikarantina 100% dari eksekusi riil akun Cent `VTMarkets-Live 3` (login `27556325`), namun seluruh telemetri radar kuantitatif M1..M4, level ZCE, dan shadow performance tetap aktif dipantau.
2. **Integrasi Penuh Multi-Asset ke Dashboard Cockpit & 8-Gate X-Ray**:
   - Menampilkan `XAUUSD-ECNc` pada watchlist utama dashboard, lightweight chart, dan panel 8-Gate X-Ray Surveillance.
   - Penyelarasan Gate 3 (komoditas independen dari matriks shock fiat), Gate 5 (independen dari CSM), Gate 7 (badge status `PAPER` Virtual Paper Trade Execution), dan Gate 8 (floor 500 pts / $5.00, ceiling 1500 pts).
   - Memperbarui label hardcode `ALL (26)` menjadi `ALL` dan `26-PAIR RADAR WATCHLIST` menjadi `RADAR WATCHLIST`.

---

### Solusi Perbaikan Kode:
1. **`config.py` & `.env`**:
   - Menambahkan `ENABLE_XAU_PAPER=true`, `ENABLE_BTC_247_PAPER=true`, `PAPER_TRADE_ONLY_SYMBOLS=XAUUSD-ECNc,BTCUSD.c`, `GOLD_SYMBOL=XAUUSD-ECNc`.
   - Menambahkan helper `is_paper_only(symbol)` yang secara ketat mendeteksi simbol karantina paper trade.
   - Memperbarui `get_scanner_symbols(now)`: menghasilkan 28 simbol pada hari kerja (26 FX + Gold + BTC) dan `[BTCUSD.c]` pada akhir pekan.
2. **`src/core/risk_engine.py`**:
   - `can_trade(sym)` mengintersepsi `is_paper_only(sym)` di baris pertama dan mengembalikan `(False, "[PAPER_ONLY]...")` guna mencegah pengiriman order apa pun ke MT5.
3. **`main.py`**:
   - Pada Stage 2 radar dispatch (Pure Quant & LLM Jury): mendeteksi `is_paper_only` / `[PAPER_ONLY]`, mendaftarkan kandidat langsung ke `shadow_tracker.register_candidate()` dengan disposisi `PAPER_TRADE_ONLY`, mencetak alert cyan di terminal, dan mengaborsi dispatch MT5.
4. **`dashboard.py` & `dashboard_assets.py`**:
   - `start()`, `_build_overview_cache()`, dan `get_symbol_detail()` memuat `XAUUSD-ECNc` dengan spesifikasi point 0.01 dan digits 2.
   - `_evaluate_8_gates()`: Gate 1, 3, 5, 7, 8 diperkaya untuk Gold dan Paper-Only status.
   - Filter tab `ALL (26)` diselaraskan menjadi `ALL` agar adaptif terhadap universe 28 instrumen.
5. **Unit Test Suite (`tests/test_symbol_rotation.py`, `tests/test_market_scanner.py`, `tests/test_dashboard_btc_xray.py`)**:
   - Menyelaraskan pengujian live rotation pool (26 FX) vs scanner pool (28 instrumen) dan memvalidasi karantina `PAPER_ONLY`.
   - Seluruh 214 unit test sistem: **100% PASS**.

---

## 85. Perubahan 10 September 2026 (Siang/Sore) — Transisi ke Akun Live Cent (VTMarkets-Live 3), 8-Gate X-Ray Surveillance & Catatan Riset Diurnal

### Latar Belakang & Keputusan Pengguna:
1. **Transisi ke Akun Live Cent (`VTMarkets-Live 3`)**:
   - Pengguna memutuskan untuk memindahkan operasional trading bot ke akun Live Cent broker VT Markets (Login `27556325`, Server `VTMarkets-Live 3`, Saldo $\approx 5.520$ USC / $\$55.20$ USD).
   - Pengujian login programatis MT5 memverifikasi keberhasilan autentikasi ke server Live 3.
   - Modul Virtual Paper Trade (`shadow_tracker`) tetap aktif 100% secara paralel untuk mencatat peluang A+ tanpa beban kuota MT5 (`SKIPPED_CBSS_BASKET_CAP`).
2. **Standardisasi 8-Gate X-Ray Surveillance**:
   - Panel Decision Gates Audit pada `dashboard.py` mengadopsi struktur 8 Gate mandiri (Gate 2 khusus Economic Calendar & High-Impact News Blackout Shield $\pm 30$m).
   - Penyelarasan assertion unit test `tests/test_dashboard_btc_xray.py` dari 7 gate ke 8 gate untuk memulihkan status **100% PASS**.
3. **Dokumentasi Riset Timing Diurnal & Saturation**:
   - Pencatatan Section 6 pada `docs/research/HASIL_INVESTIGASI_TIMING_CBSS_ZCE_MAKRO.md` mengenai implementasi `evaluate_session_confluence_timing()`, Gate BSSI $\ge 70\%$, dan pembekuan Tokyo Midday Lull $< 25\text{ pips}$.

---

### Solusi Perbaikan Kode & Konfigurasi:
1. **`.env`**:
   - Mengubah `MT5_ACCOUNT_MODE=live`.
   - Mengubah `WEEKDAY_SYMBOL=GBPUSD-ECNc`, `WEEKEND_SYMBOL=BTCUSD.c`.
   - Mengubah seluruh 26 simbol di `SCANNER_SYMBOLS` ke format cent broker live (`-ECNc`).
2. **`tests/test_dashboard_btc_xray.py`**:
   - Memperbarui pengujian `test_symbol_detail_and_7_gate_xray_for_btc` untuk memverifikasi tepat 8 gate (G1: Session/Spread, G2: Economic Calendar News Blackout, G3: Basket Lock, G5: CSM Flow, G7: Pure Quant, G8: Risk Floor).
3. **`docs/research/HASIL_INVESTIGASI_TIMING_CBSS_ZCE_MAKRO.md`**:
   - Menambahkan Section 6 yang mendokumentasikan implementasi dan metrik pemantauan live.
4. **`AGENTS.md`**:
   - Memperbarui ringkasan akun aktif pada branch `quant-trade-noAI` ke Live Cent `VTMarkets-Live 3` (`27556325`).

---

## 84. Perubahan 10 September 2026 (Siang/Sore) — Confluence Timing, Basket Saturation (BSSI), Midday Retracement Guard (65% Rule) & Pre-News Shield

### Latar Belakang & Identifikasi Masalah:
1. **Fenomena Retracement Pagi & Asimetri Keranjang Terbuka**:
   - Teramati pada 6 posisi terbuka MT5 (`AUDCHF, AUDCAD, CADJPY, USDJPY, EURNZD, NZDUSD`): floating profit sempat mencapai $+\$250$, lalu mengalami penarikan nafas (*retracement*) ke $\approx +\$100$ di fase lull tengah hari (10:45–11:15 WIB), sebelum menguat kembali ke $+\$215.14$ di awal sesi Eropa.
   - Tanpa dasar kuantitatif, panic-closing saat profit turun ke $+\$100$ akan memotong profit secara prematur, sedangkan menahan posisi tanpa batas saat struktur rusak dapat berujung drawdown.
2. **Temuan Empiris 130.000 Candle H1 (208 Hari Trading MT5)**:
   - Riset mendalam membuktikan 80.8% dorongan pagi di 17 pair AUD/JPY/NZD mengalami retracement $\ge 40\%$ di jam 11:00–13:00 WIB.
   - **The 65% Pullback Boundary**:
     * Retracement normal $\le 65\%$ dari range pagi: **81.6% probabilitas London memecahkan high/low pagi dan melanjutkan tren**.
     * Retracement dalam $> 65\%$: **Gagal dan berbalik arah sebesar 53.4%** (risiko kegagalan struktural).
3. **Kebutuhan Seleksi Laggard Relatif & Pre-News Stand-Off**:
   - Jika lead pair menabrak benteng G3, sistem membutuhkan seleksi terpadu untuk memilih laggard terbaik dengan sisa runway $\ge 0.85\times\text{ATR}$ dan dorongan $\Delta\text{CSM}$.
   - Menjelang rilis berita Tier-1 (ECB Rate Decision 19:15 WIB, US PPI 19:30 WIB), likuiditas institusional ditahan, mewajibkan proteksi darurat modal 30 menit sebelum event.

---

### Solusi Perbaikan Kode:
1. **`src/analytics/basket_sync_engine.py`**:
   - **`calculate_basket_saturation_index(currency, direction, macro_cache)`**: Menghitung **BSSI (Basket Structural Saturation Index)**. Jika BSSI $\ge 70\%$, keranjang jenuh dan setup kelanjutan dibekukan.
   - **`select_basket_champion(currency, direction, macro_cache, candidate_pairs, min_runway_atr=0.85, hour_wib)`**: Seleksi laggard terbaik berbasis composite ranking:
     $$\text{Score} = (\text{Runway ATR} \times 0.45) + (\text{Net CSM Delta} \times 0.35) + (\text{Readiness} \times 0.20)$$
2. **`src/analytics/macro_strategic_engine.py`**:
   - **`evaluate_session_confluence_timing(symbol, hour_wib, macro_cache, has_tier1_news)`**: Memetakan 4 fase sirkadian (Tokyo Expansion, Tokyo Midday Lull, London Core, NY Peak Velocity) dan direktif target (`GRADE_B_C1` vs `GRADE_A_PLUS_C2`).
3. **`src/analytics/market_scanner.py`**:
   - Gate terpadu BSSI di `_is_direction_allowed()`: BSSI $\ge 0.70$ mengunci kelanjutan, namun tetap membuka pintu untuk M1 Universal Liquidity Sweep (SFP).
   - Freeze order kelanjutan baru di jendela 10:30–13:00 WIB jika sprint pagi $< 25\text{ pips}$.
4. **`src/analytics/position_manager.py`**:
   - **`_check_midday_retracement_guard()`**: Pada jam 11:00–13:00 WIB, jika posisi dibuka pagi hari dan retracement $> 65\%$ dari Peak MFE, otomatis mengunci Defensive BEP (+komisi round-trip). Jika retracement $\le 65\%$, posisi dibiarkan bernafas ($0.75\times\text{ATR}$).
   - **`_check_pre_news_emergency_shield()`**: Pada jam 18:45 WIB (30 menit sebelum Tier-1 news), posisi dengan floating tipis ($< +0.20R$) ditutup bersih di pasar (Pre-News Flat); posisi profit sehat ($\ge +0.20R$) dikunci BEP rapat.
   - Helper deterministik `_force_move_to_bep()`.
5. **`config.py` & `.env`**:
   - Penyelarasan parameter konfigurasi: `MIDDAY_RETRACEMENT_GUARD_ENABLED`, `MIDDAY_RETRACEMENT_MAX_PULLBACK_PCT=0.65`, `CBSS_SATURATION_THRESHOLD=0.70`, `PRE_NEWS_EMERGENCY_SHIELD_ENABLED`, `PRE_NEWS_EMERGENCY_MIN_R=0.20`.
6. **`dashboard.py` & `dashboard_assets.py`**:
   - Integrasi metrik BSSI Saturation (Long/Short) dan Top 1 Champion ke dalam drawer CBSS.
   - Header stat bar menampilkan badge `Timing Phase` real-time.
7. **`src/core/cli_theme.py`**:
   - Menampilkan status `Timing Phase` & rekomendasi target mode di Tile 3 Bento Box terminal HUD.
8. **`tests/test_confluence_timing_and_laggard.py`**:
   - Suite unit test 8 pengujian mencakup BSSI, Champion Selector, Confluence Timing, Midday 65% Guard, dan Pre-News Shield (**100% PASS**).

---

## 83. Perubahan 10 September 2026 (Siang) — CBSS Basket Saturation Direct-to-Paper Trade Routing (`SKIPPED_CBSS_BASKET_CAP`)

### Latar Belakang & Identifikasi Masalah:
1. **Peluang A+ Terbuang Saat Kuota Keranjang MT5 Penuh**:
   - Aturan CBSS (Currency Basket Structural Synchronization) membatasi maksimal 2 posisi aktif per mata uang dalam arah yang sama (`CBSS_MAX_BASKET_CONCURRENCY=2`).
   - Sebelumnya, pengecekan ini di `market_scanner.py` (`_is_direction_allowed`) mengembalikan `False, "HARD_BLOCK", cap_msg` saat keranjang jenuh.
   - Dampaknya, peluang setup A+ pada pair ke-3 atau ke-4 di keranjang tersebut langsung dibuang di Stage 1 Radar dan tidak pernah diteruskan ke `main.py`, sehingga Paper Trade (`shadow_tracker`) menganggur dan tidak memantau kinerja teknikal peluang tersebut.

---

### Solusi Perbaikan Kode:
1. **`src/analytics/market_scanner.py`**:
   - Pengecekan `check_basket_concurrency_cap` di `_is_direction_allowed()` tidak lagi menolak setup secara fatal jika setup teknikal lainnya valid.
   - Mengembalikan `True, "CBSS_CAP_BLOCKED", cap_msg`, meloloskan kandidat dengan metadata `cbss_cap_blocked=True`.
2. **`main.py`**:
   - `run_scanner_trading_cycle()` mendeteksi flag `CBSS_CAP_BLOCKED` dan melakukan re-verifikasi kuota live MT5.
   - Mengalihkan eksekusi langsung ke `shadow_tracker.register_candidate()` dengan disposisi `SKIPPED_CBSS_BASKET_CAP`.
   - Menghasilkan 0 token API LLM, 0 risiko modal MT5, dan 100% data tracking aktif di Paper Trade (termasuk trailing stop, BEP, dan winrate tracking).
3. **`src/analytics/shadow_tracker.py` & `src/analytics/shadow_report.py`**:
   - Menambahkan disposisi `SKIPPED_CBSS_BASKET_CAP` ke dalam aggregation stats dan tabel visual HTML.
4. **`tests/test_cbss_and_risk_shields.py`**:
   - Menambahkan unit test `test_cbss_basket_full_routes_to_paper_trade` (22/22 unit tests PASS 100%).

---

## 82. Perubahan 10 September 2026 (Pagi III) — ZCE Self-Adaptive ATR-Aware Separation, Macro Fortress Supremacy & Low-Beta Pair Wall Restoration

### Latar Belakang & Identifikasi Masalah:
1. **Jebakan Floor Flat `15.0 * pip_val` Membutakan 17 Simbol FX**:
   - Pasca commit `06189ac`, batas pemisah layer statis `min_sep = max(0.50 * atr_h1, 15.0 * pip_val)` menetapkan floor kaku 15 pips.
   - Pada pair low-beta (AUDCHF ATR 6.5p, EURGBP ATR 3.9p, EURUSD ATR 8.4p), 15 pips bernilai $1.8\times - 3.8\times\text{ ATR H1}$. Akibatnya, benteng makro D1/W1 berbobot raksasa (`GRADE_3_MACRO`, skor 10–26) yang berjarak $0.5\times - 1.2\times\text{ ATR}$ dari harga live dibuang total dari daftar layer.
   - Pada AUDCHF, Benteng Makro D1/W1 `0.58567` (Skor 15.49) di-drop karena berjarak 14.1 pips (< 15 pips) dari C1 `0.58426`, memicu lonjakan semu 32 pips ke level minor `0.58750` (Skor 0.40).
2. **Kelemahan Greedy Selection (Level Minor G1 Menyingkirkan Benteng Makro G3)**:
   - Algoritma greedy memilih kandidat murni berdasarkan jarak fisik terdekat. Saat kandidat pertama adalah level minor G1 (2 pips dari harga), benteng makro G3 di belakangnya (jarak 8-12 pips) langsung tereliminasi karena dianggap "terlalu rapat".

---

### Solusi Perbaikan Kode:
1. **`src/analytics/zone_confluence_engine.py`**:
   - **Skalasi Toleransi Peleburan Dinamis (`_merge_primitives`)**:
     * `tol_pip = min(8.0 * pip_val, 0.40 * atr_h1)`
     * `tol = max(self.merge_atr_mult * atr_h1, tol_pip)`
     * Mencegah peleburan primitif lintas 8 pips pada low-beta pair, sementara tetap mempertahankan floor 8 pips pada pair bervolatilitas tinggi.
   - **Skalasi Pemisahan Layer Adaptif (`_pick_layers`)**:
     * `pip_sep = min(15.0 * pip_val, 0.75 * atr_h1)`
     * `min_sep = max(0.35 * atr_h1, pip_sep)`
     * `min_ch = max(0.50 * atr_h1, pip_sep)`
     * Pada AUDCHF `min_sep` menjadi 4.9 pips, EURGBP menjadi 2.9 pips, dan pair volatile/JPY tetap di-clamp pada 15 pips.
   - **Macro Fortress Supremacy & Spatial Conflict Resolution**:
     * Mengimplementasikan resolusi hierarkis berbasis grade (`GRADE_3_MACRO > GRADE_2_INTERMEDIATE > GRADE_1_MICRO`) dan skor konfluensi.
     * Jika ada kandidat berjarak $< \text{min\_sep}$ namun memiliki bobot/grade lebih tinggi, kandidat berkekuatan benteng makro secara otomatis memenangkan slot stasiun dan menggantikan kandidat minor.
     * Pengurutan sekuensial strictly monotonic outward (`k[0]` untuk ceiling, `-k[0]` untuk floor).
2. **`dashboard.py`**:
   - Menyelaraskan `proximity_thr` pada `_consolidate_zce_zones` dan chart display ladder election menggunakan formula adaptif yang sama (`pip_thr = min(15.0 * pip_val, 0.75 * atr_val)` dan `max(0.35 * atr_val, pip_thr)`).
   - **Eliminasi Pseudo-Floor Midpoint (`_consolidate_zce_zones`)**: Menyelaraskan penentuan tipe cluster mentah dengan aturan fisik ZCE (hanya sah RBS floor jika $cur\_price \ge band\_high + probe\_tol$). Mengeliminasi anomali di mana midpoint resistance D1 GBPUSD (`1.35569`) dibajak menjadi F1 saat harga menusuk di dalam zona. F1 GBPUSD di dashboard kini bersih di `1.35368` dan C1 di `1.35736`.
   - Menjamin visualisasi dashboard dan engine analitik ZCE 100% kongruen.
3. **Hasil Verifikasi Kuantitatif**:
   - **Unit Tests**: 242/242 unit tests **100% PASS** dalam 38.65 detik.
   - **Live Audit 26 Pasang Mata Uang**:
     * AUDCHF memulihkan C2 `0.58567` (Skor 15.49, G3 Macro) dan F3 `0.58241` (Skor 10.91, G3 Macro).
     * EURUSD memulihkan C1 `1.16412` (Skor 11.38, G3 Macro).
     * GBPUSD memulihkan C1 `1.35736` (Skor 13.88, G3 Macro) dan F3 `1.35130` (Skor 17.60, G3 Macro).
     * EURGBP memulihkan 4 stasiun sekuensial rapat (C1–C4 dan F1–F4) yang selaras dengan ATR 3.9p.

---

## 81. Perubahan 10 September 2026 (Pagi II) — Restorasi Proven ZCE Baseline, Hierarchical Confluence Melting (Pip-Aware Spacing) & Pure Sequential 4-Station Natural Ladder

### Latar Belakang & Identifikasi Masalah:
1. **Runway Tercekik (*Choked Runway*) Akibat Banjir Micro-Noise**:
   - Setelah integrasi multi-basket (CBSS), commit sebelumnya menginjeksi seluruh structural swings LuxSMC (`bullish_structures` dan `bearish_structures`) dari timeframe M30/H1 tanpa kurasi, memicu banjir primitif di ZCE.
   - Ambang toleransi peleburan yang hanya berbasis $0.25\times\text{ATR}$ tanpa batas pip minimal menyebabkan selisih $2.3\text{ pips}$ di EURUSD tidak melebur, melainkan membelah area yang sama menjadi 39 klaster kerdil terpisah.
   - Akibatnya, plafon C1, C2, C3 berderet tiap $6-8\text{ pips}$, memotong runway riil dan membuat radar mendeteksi benturan dinding semu.
2. **Pemaksaan Kuota 8 Layer & Pembajakan Slot G3 (Lompatan 400 Pips)**:
   - Pemaksaan pengirisan hingga 8 level (`[:8]`) memenuhi chart visual dengan garis rapat seperti jeruji, padahal secara alami struktur pasar hanya memiliki 2–4 zona benteng utama di sekitar harga live.
   - Mekanisme pembajakan slot terakhir oleh benteng makro G3 ekstrem menyebabkan lompatan artifisial 400–500 pips (misal C3 ke C4 GBPJPY melonjak ke 213.30, F3 ke F4 GBPNZD melonjak ke 2.2836).

---

### Solusi Perbaikan Kode:
1. **`src/analytics/zone_confluence_engine.py`**:
   - **Restorasi Primitif Proven 3-Hari**:
     * Menghapus injeksi uncurated micro-swings M30/H1. Struktur ekstrem tetap dijaga akurat oleh `LAST_HIGH`/`LAST_LOW` per horizon, `OB_BULL`/`OB_BEAR`, `FVG`, `EQH`/`EQL`, `FRVP` (POC/VAH/VAL), dan Stasiun Psikologis Atlas DNA (`PSYCH_MAJOR`/`PSYCH_SUB`).
   - **Peleburan Spasial Pip-Aware (`_merge_primitives`)**:
     * Ambang toleransi peleburan dinaikkan dengan batas pengaman pip: `tol = max(self.merge_atr_mult * atr_h1, 8.0 * pip_val)`. Primitif yang berdekatan dalam satu neighborhood dilebur menjadi SATU Zona Benteng Terpadu (`band_low = min`, `band_high = max`, skor konfluensi saling melipatgandakan).
   - **Pemisahan Layer Sehat & Natural Limit (`_pick_layers`)**:
     * Batas pemisah antar layer dinaikkan: `min_sep = max(0.50 * atr_h1, 15.0 * pip_val)`.
     * Batas layer dinormalkan ke **4 stasiun utama** (`limit = 4`: F1..F4 dan C1..C4) tanpa pemaksaan padding jika hanya ada 2 atau 3 zona sejati (misal AUDUSD F4/C2, AUDCAD F4/C1).
     * Memulihkan tinggi chamber minimum: `min_ch = max(0.60 * atr_h1, 15.0 * pip_val)`.
     * Menghapus pembajakan slot G3 ekstrem sehingga progresi layer 100% murni sekuensial menjauh dari harga live.
2. **`dashboard.py`**:
   - Menyelaraskan `proximity_thr` menjadi `max(0.40 * atr_val * tf_scale, 15.0 * pip_val)`.
   - Menyelaraskan seleksi tangga display menjadi 4 stasiun sekuensial murni (`limit = 4`), menghapus pembajakan slot G3 ekstrem yang melompati zona riil 400 pips.
   - Chart TradingView visual kembali bersih, lega, dan menampilkan runway stasiun yang riil.
3. **Hasil Verifikasi Kuantitatif**:
   - **Unit Tests**: `pytest tests/ -q` $\rightarrow$ **242 PASSED (100% PASS)** dalam 26.34 detik.
   - **Live MT5 Audit 26 Pasang Mata Uang**:
     * **0 ANOMALI INVERSI (100% VALID)**. Seluruh pasangan memenuhi $F_1 \le cur\_price \le C_1$.
     * Runway terbebas dari jeratan micro-noise: EURUSD C1 $+25.6\text{p}$, GBPUSD F1 $-19.4\text{p}$ / C1 $+17.4\text{p}$, GBPJPY F1 $-5.6\text{p}$ / C1 $+143.0\text{p}$.
     * Distribusi layer natural: AUDUSD (F4/C2), AUDCAD (F4/C1), EURCHF (F4/C2).

---

## 80. Perubahan 10 September 2026 (Pagi) — ZCE Strict Physical Partitioning (Floor < Price < Ceiling), Eliminasi Anomali Inversi & Penyelarasan Native H1 (300 Bar Expanded)

### Latar Belakang & Identifikasi Masalah:
1. **Anomali Inversi Dinding ZCE (Physical Inversion Bug)**:
   - Audit langsung pada 26 simbol universe di MT5 mendeteksi 8 anomali aktif di mana level dinding tertukar polaritas fisiknya:
     * `USDCAD-ECN`: Lantai `F1 (1.38050)` berada di atas harga live `1.38028` (+2.2 pips).
     * `EURGBP-ECN`: Lantai `F1 (0.85848)` berada di atas harga live `0.85842` (+0.6 pips).
     * `AUDCHF-ECN`: Plafon `C1 (0.58459)` berada di bawah harga live `0.58466` (-0.7 pips).
     * `AUDCAD-ECN`: Plafon `C1 (0.99651)` berada di bawah harga live `0.99669` (-1.8 pips).
2. **Akar Masalah pada `_elect_walls()`**:
   - Upaya sebelumnya untuk mencegah mutasi state dinamis saat penetrasi tipis (< 0.30 ATR) menyebabkan level plafon yang sudah tertembus ke atas (`cur_price > band_high`) tetap dimasukkan ke dalam `ceil_cands`, dan level lantai yang sudah tertembus ke bawah (`cur_price < band_low`) tetap dimasukkan ke dalam `floor_cands`.
3. **Distorsi Tampilan & Mismatch Kognitif Timeframe H4**:
   - Tombol H4 pada dashboard sebelumnya merusak keteraturan visual karena melebarkan proksimitas secara artifisial ($tf\_scale = 2.2$) dan melompati level-level plafon terdekat demi mencari benteng makro jauh hingga 1,000 pips ke atas (C8 = 218.494 pada GBPJPY). Sementara bot trading beroperasi 100% pada timeframe native H1.

---

### Solusi Perbaikan Kode:
1. **`src/analytics/zone_confluence_engine.py`**:
   - **Strict Physical Partitioning**:
     * Zona di bawah harga (`band_high < cur_price`): HANYA masuk `floor_cands` (RBS sah jika tembus $\ge probe\_tol$; tembus tipis ditahan dan DILARANG masuk `ceil_cands`).
     * Zona di atas harga (`band_low > cur_price`): HANYA masuk `ceil_cands` (SBR sah jika tembus $\ge probe\_tol$; tembus tipis ditahan dan DILARANG masuk `floor_cands`).
     * Zona di dalam rentang: Batas atas `band_high` ($> cur\_price$) sebagai plafon, batas bawah `band_low` ($< cur\_price$) sebagai lantai.
   - **Presisi Pembulatan Float (`digits`)**: Mengeliminasi distorsi epsilon floating-point saat harga menyentuh persis batas zona.
2. **`dashboard.py` & `dashboard_assets.py`**:
   - **Eliminasi Tombol H4**: Menghapus tombol H4 dari visual chart selector agar trader 100% selaras dengan timeframe eksekusi bot (H1 Unified).
   - **Ekspansi Candlestick History H1 ke 300 Bar**:
     * H1: diperlebar dari 150 bar ke **300 bar** ($\approx 12.5$ hari perdagangan / 2.5 minggu pasar). Chart menjadi luas dan seluruh struktur swing 2 minggu tampak jelas tanpa distorsi.
     * M30: diperlebar ke **180 bar** ($\approx 3.75$ hari).
     * M5: diperlebar ke **60 bar** ($\approx 5$ jam).
   - **Tangga Level Sekuensial Kontinu (Anti-Lompat)**:
     * Menghilangkan loncatan kosong 1,000 pips pada plafon. Slot C1..C7 dan F1..F7 kini bergerak sekuensial kontinu menjauh dari harga live.
     * Slot C8 dan F8 difungsikan secara elegan sebagai penambat benteng makro terluar (`GRADE_3_MACRO`).
3. **`tests/test_zce_chamber_clearance.py`**:
   - Menyelaraskan pengujian probe zone untuk memverifikasi proteksi role invariance di dalam rentang band serta memastikan tidak ada dinding terbalik saat level ditusuk tipis.
4. **Hasil Audit & Verifikasi**:
   - Audit live 26 universe symbols di MT5: **0 ANOMALI (100% INVARIANT PHYSICAL CLEARANCE TERPENUHI)**.
   - Full test suite: **242 unit tests 100% PASS** dalam 38.42 detik.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 10 September 2026 (Subuh) — Timeframe H4 Macro, Timeframe-Adaptive Macro Ladder (Anti-Clustering Barcode), Gradasi Opacity C1..C8 / F1..F8 (C8 = 50%), Spasial 3-Kolom Watchlist & Bilateral C1/F1 Projection

### Latar Belakang & Identifikasi Masalah:
1. **Penumpukan Barcode Garis di Tengah pada Timeframe H4 (Scale Mismatch)**:
   - Pada chart H4 dengan rentang lilin 100 bar mencakup 500–800 pips, pemotongan kuota tangga (`merged_ceils[:8]` dan `merged_floors[:8]`) berdasarkan jarak pemisah H1 (~15 pips) menyebabkan seluruh garis C1..C8 dan F1..F8 habis terpakai dalam rentang sempit $\pm 100\text{ pips}$ di dekat harga live.
   - Puncak tertinggi H4 (Swing High $+350\text{p}$) dan lembah terendah H4 (Swing Low $-400\text{p}$) yang merupakan Benteng Makro G3 (D1/W1) terpotong dan tidak tergambar sama sekali di layar.
2. **Ketiadaan Pembeda Kedalaman Visual (Visual Hierarchy) pada Tangga 8-Tier**:
   - Garis-garis luar yang jauh (C4..C8 dan F4..F8) digambar dengan kontras tinggi yang sama, membuat chart padat dan mengaburkan candlestick aksi harga live.
3. **Redundansi Informasi & Ketiadaan Konteks Atap pada Kartu Watchlist**:
   - Pengulangan kata arah secara berlebihan di baris yang sama (`[M1+M2 BEAR]` berdampingan dengan `[HTF: BEAR]`).
   - Angka jarak pips trigger dan jarak runway (`12.8p (0.40x ATR)` dan `→F1: +53p`) diletakkan berdampingan tanpa identitas pembeda antara jarak entry vs jarak target.
   - Hanya menampilkan target bawah (`→F1`), sehingga trader kehilangan referensi jarak atap pembatas atas (`C1`).
4. **Ketiadaan Timeframe H4 di Dashboard**:
   - Selector timeframe hanya memuat H1, M30 (dengan label usang `M30 JPY`), dan M5.

---

### Solusi Perbaikan Kode (Checklist File):
1. **`dashboard.py`**:
   - **Timeframe H4 Support**: Menambahkan pemetaan MT5 `"H4": config.mt5.TIMEFRAME_H4`, fetching 100 bar, dan `tf_hours = 4.0` untuk komputasi wave regime H4.
   - **Timeframe-Adaptive Macro Ladder (`tf_scale = 2.2`)**: Jarak pemisah konsolidasi `proximity_thr` diskalakan otomatis mengikuti timeframe ($2.2\times$ di H4, sekitar $35 - 50\text{ pips}$).
   - **Macro Anchor Reservation Architecture (`_elect_display_ladder`)**: Mengunci $C_1, C_2$ dan $F_1, F_2$ sebagai dinding reaksi terdekat, lalu memindai seluruh bentang layar H4 untuk memprioritaskan dan mengangkat seluruh **Benteng Grade 3 Makro (D1/W1/H4 Swings)** ke dalam slot $C_3..C_8$ dan $F_3..F_8$. Mengeliminasi tumpukan barcode sempit di H4.
   - **Bilateral C1 & F1 Projection**: Menghitung jarak fisik dan label teks untuk atap C1 (`c1_text`, `c1_pips`) dan lantai F1 (`f1_text`, `f1_pips`) secara simultan pada `get_watchlist_overview()`.
   - **Auto-Reload Asset Template**: Menyuntikkan `importlib.reload(dashboard_assets)` dan header anti-cache HTTP pada endpoint root `/`.
2. **`dashboard_assets.py`**:
   - **Timeframe Controls**: Menambahkan tombol `<button class="tf-btn" data-tf="H4">H4 Macro</button>`, merapikan label menjadi `M30 Swing` dan `M5 Micro`.
   - **Spasial Grid 3-Kolom Watchlist (0% Emoji / Non-Emoticon Standard)**:
     * Baris 2 Tengah: `C1: XXp` (Warm Amber `#fbbf24`) — atap batas atas.
     * Baris 3 Tengah: `F1: XXp` (Sky Blue `#38bdf8`) — lantai target bawah, bertumpuk vertikal tepat di bawah C1.
     * Baris 3 Kiri: `Trig: XX.Xp (X.XXx)` — label eksplisit jarak entry trigger.
     * Setup Pill: Diringkas menjadi `[M1+M2]` (menghilangkan duplikasi kata `BEAR`/`BULL`).
     * Basing Box Pill: Diganti dari `RETEST` menjadi `BOX` / `BRK` agar tidak rancu dengan M2/M3 pullback.
   - **Gradasi Opacity Garis Chart C1..C8 & F1..F8**:
     * Tier 1–3: $100\%$ ($1.00$) solid/kontras.
     * Tier 4: $90\%$ ($0.90$), Tier 5: $80\%$ ($0.80$), Tier 6: $70\%$ ($0.70$), Tier 7: $60\%$ ($0.60$), **Tier 8: $50\%$ ($0.50$)**.
   - **Sinkronisasi Filter 1-1 & Ladder Preset**: Memperbaiki fallback mode custom agar tidak mendrop level C3..C8 dan F3..F8 saat filter arah diubah.
3. **Verifikasi Test Suite**:
   - Menjalankan test suite unit dan integrasi: **242 passed (100%)** dalam 47.12s.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 10 September 2026 (Dini Hari) — Dashboard Institutional Contrast (Sky Blue / Warm Amber / Neon M1..M4), ZCE-Exclusive Left Margin, Dynamic Zone Consolidation & Multi-Horizon Spacing

### Latar Belakang & Identifikasi Masalah:
1. **Visual Contrast Clashing pada Candlestick vs Levels**:
   - Candlestick menggunakan warna merah/hijau klasik. Penggunaan warna merah/hijau pada level ceiling dan floor membuat chart membingungkan karena garis resistansi/support bertubrukan secara visual dengan warna candle.
   - Garis `GRADE_3_MACRO` setebal 2.0px terlalu dominan dan menutupi pergerakan candlestick mikro.
2. **Tabrakan Warna Mekanisme Radar (M1..M4) dengan Level ZCE**:
   - Garis trajectory dan marker M2 (pullback) sebelumnya menggunakan warna biru muda yang bertubrukan dengan Sky Blue ZCE Floor (`#38bdf8`).
   - Trajectory M4 (flow) sebelumnya menggunakan warna amber/kuning yang bertubrukan dengan Warm Amber ZCE Ceiling (`#fbbf24`).
3. **Kepadatan Garis Berdekatan & Hilangnya Benteng Makro Jauh**:
   - Pada pair dengan klaster swing padat (seperti GBPJPY), level yang hanya berjarak 8–12 pips digambar menumpuk, memenuhi batas 8-tier sehingga benteng makro W1 di 205.250–205.760 terpotong.
4. **Clutter Sisi Kiri Chart Antara Label ZCE vs Radar Standby (M1..M4)**:
   - Objek radar standby M1A, M1B, M2, M3, M4 sebelumnya dimasukkan ke dalam antrean label sisi kiri (`activeRenderedLevels`), menciptakan tumpukan badge teks di margin kiri chart yang berebut ruang dengan label benteng ZCE.
5. **Python HTTPServer Bytecode Caching**:
   - Edit frontend pada `dashboard_assets.py` tertahan di memori `ThreadingHTTPServer` proses terminal running (`py dashboard.py --serve`) sehingga browser terus menerima aset lama.

---

### Solusi Perbaikan Kode (Checklist File):
1. **`dashboard_assets.py`**:
   - **Palet Kontras ZCE Institusional**: Mengubah **Ceilings** menjadi **Warm Amber / Gold (`#fbbf24`)** dan **Floors** menjadi **Sky Blue / Cyan (`#38bdf8`)**, sepenuhnya terpisah dari warna merah/hijau candle.
   - **Institutional Contrast Palette untuk Radar (M1..M4)**:
     * **M1 (Macro Sweep & SFP)**: Neon Orange (`#fb923c`)
     * **M1B (Trend Induced Sweep)**: Hot Pink (`#ec4899`)
     * **M2 (Trend-Aligned Pullback)**: Indigo / Periwinkle (`#818cf8`) — 100% bebas bentrok dari Sky Blue Floor
     * **M3 (Multi-Touch Breakout Retest)**: Royal Purple (`#c084fc`)
     * **M4 (Systemic Flow Continuation)**: Neon Mint / Emerald (`#34d399`) — 100% bebas bentrok dari Warm Amber Ceiling
     * Tersinkronisasi pada in-chart price lines, temporal markers panah/lingkaran, trajectory vectors, bento box telemetry cards, dan performance breakdown tables.
   - **Hairline Precision**: Menurunkan ketebalan garis G3 dari 2.0px ke **1.2px solid**, G2 ke **1.0px dashed (75% opacity)**, dan G1 ke **1.0px dotted (45% opacity)**.
   - **ZCE-Exclusive Left Margin**: Menghilangkan penyisipan label M1..M4 ke `activeRenderedLevels` dengan hard filter `item.kind !== 'radar'`. Seluruh margin kiri chart dikhususkan 100% untuk label benteng ZCE (C1..C8, F1..F8).
2. **`dashboard.py`**:
   - **Dynamic Assets Reloading & Anti-Cache Headers**: Menyuntikkan `importlib.reload(dashboard_assets)` pada endpoint handler `/` dan `/assets/dashboard.js` serta menambahkan header HTTP `Cache-Control: no-cache, no-store, must-revalidate` untuk pembaruan instan tanpa perlu mematikan/menghidupkan ulang server terminal.
   - **Dynamic Consolidation**: Menaikkan ambang peleburan level proksimitas ke `max(0.35 * atr_val, 8.0 * pip_val)`. Level-level yang berdekatan otomatis dilebur menjadi 1 pita band solid dengan skor gabungan.
3. **`src/analytics/zone_confluence_engine.py`**:
   - **Tier Spacing & Macro G3 Reservation**: Pada `_pick_layers()`, dipasang jarak minimum `min_sep = max(0.35 * atr_h1, 6.0 * pip_val)` dan **Macro G3 Reservation Guarantee** sehingga benteng makro G3 selalu mendapatkan slot representasi di chart.
4. **`src/analytics/position_manager.py` & `tests/`**:
   - **Floating-Point Precision Guard**: Mengubah perbandingan rasio R:R pada *Vacuum Extension* menjadi `round(tp_points / init_sl_pts, 2) > 2.0` guna mencegah distorsi presisi floating-point yang memicu aktivasi BEP 35% pada setup standar 1:2.0.
5. **`main.py` & `src/core/cli_theme.py` (CLI Terminal & Bento Box Modernization)**:
   - **Eliminasi Bug Kritis `NameError`**: Menambahkan instansiasi `logger = logging.getLogger("trading_bot")` di header `main.py` sehingga exception handler pada shadow tracker registration dan deal telemetry close tidak mengalami crash runtime.
   - **Sinkronisasi Warna Bento Box & Level Makro**: Mengubah pewarnaan Sub-Floor / RBS / F1 dari hijau menjadi **Sky Blue / Cyan (`UI.CYAN`)** dan Sub-Ceiling / SBR / C1 dari merah menjadi **Warm Amber / Yellow (`UI.YELLOW`)**, mengeliminasi tabrakan visual dengan warna candle.
   - **Tile 4 Bento Box Adaptif**: Menyesuaikan Tile 4 secara otomatis saat `ENABLE_LLM_JURY=False` untuk menampilkan `Pure Quant Direct Execution (0-Token API)` dan `Direct Institutional MT5 Dispatch`.
   - **Pembaruan SL Rules & Unified H1**: Menyelaraskan teks SL Anchor ke `ZCE Dynamic Runway (Max 3.5xATR) | Segmented Floors | R:R >= 0.75+Friksi` dan memperbarui seluruh label timeframe ke `26 FX Pairs (Unified H1 Native)`.
   - **Dynamic Clock Line & Zero-Emoji Terminal**: Menstandarkan dynamic status clock line ke format `[POOL 26 PAIRS (H1) | HH:MM:SS]` dan mengganti emoji diskon/premium dengan badge teks institusional `[DISCOUNT]` dan `[PREMIUM]` guna mencegah column width jitter di terminal Windows.
   - **Verifikasi Test Suite**: Seluruh 242 unit tests bot trading lulus **100% PASS** dalam 45.26s.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 9 September 2026 (Larut Malam) — ZCE True Zonal Bands (Wick-to-Body), Anti-Snowball Chaining, Physical Boundary Clearance & Universe-Wide Calibration (26 FX + BTC)

### Latar Belakang & Identifikasi Masalah:
1. **Titik Garis Statis (Zero-Thickness Points) vs Zona Riil Pasar**:
   - Primitif struktur swing (`SWING_HIGH`, `SWING_LOW`, `EQH`, `EQL`, `LAST_HIGH`, `LAST_LOW`) di ZCE sebelumnya dikonstruksi sebagai titik garis berketebalan nol `(p, p)`. Padahal dalam dinamika harga institusional, level struktur adalah **zona likuiditas (zonal band)** antara ekor candle (wick) dan tubuh penutupan (body).
2. **Snowball Chaining pada Penggabungan Klaster (Clustering Drift)**:
   - Penggabungan single-linkage `_merge_primitives()` berisiko merantai (*chain*) zona-zona berdekatan secara beruntun sehingga membengkak menjadi satu mega-klaster yang melenceng dan menghapus diskriminasi antara support/resistance terdekat.
3. **Pembalikan Polaritas Dinding pada Boundary Probe Zone**:
   - Saat harga live sedang menguji atau melakukan penetrasi wick ke dalam zona dinding ($band\_low \le cur\_price \le band\_high$), penentuan batas fisik dapat tertukar (F1 tergeser di atas harga atau C1 di bawah harga), memicu anomali inverted walls.
4. **Evaluasi Scale Conflict pada Pemilihan Metode**:
   - Pengecekan konflik skala di `_suggest_method()` mengecek substring `"SCALE_CONFLICT"` yang tidak cocok dengan nilai aktual `ladder.conflict_flag` (`LOCAL_DISCOUNT_MACRO_PREMIUM` / `LOCAL_PREMIUM_MACRO_DISCOUNT`), sehingga trade tidak diblokir saat terjadi distorsi skala makro.

---

### Solusi Perbaikan Kode (Checklist File):
1. **`src/analytics/zone_confluence_engine.py`**:
   - **True Zonal Bands Wick-to-Body**: Mengonstruksi primitif swing dari relasi wick-to-body bar pivot dengan batas adaptif ketebalan $0.05\times\text{ATR}_{\text{TF}} \le \text{width} \le 0.35\times\text{ATR}_{\text{TF}}$.
   - **Anti-Snowball Chaining Envelope**: Membatasi ekspansi pelebaran klaster maksimum $\le 0.75\times\text{ATR}_{\text{H1}}$ (`ZCE_MAX_CLUSTER_WIDTH_ATR`), mencegah akumulasi rantai klaster tanpa batas.
   - **Physical Boundary & Inherent Role Guarantee**: Menjamin integritas fisik mutlak: Floor selalu $\le cur\_price$ dan Ceiling selalu $\ge cur\_price$. Pada zona penetrasi, role intrinsik level dipertahankan tanpa pembalikan polaritas fisik.
   - **Scale Conflict Guard**: Menyelaraskan filter `danger = bool(ladder.conflict_flag and ladder.conflict_flag != "NONE")` sehingga melarang metode eksekusi saat terjadi disparitas skala makro vs lokal.
2. **`config.py` & `.env`**:
   - Menambahkan parameter konfigurasi tersinkronisasi `ZCE_MAX_IMM_ATR=5.5` dan `ZCE_MAX_CLUSTER_WIDTH_ATR=0.75`.
3. **Hasil Audit Universe (26 FX Pairs + BTCUSD.c)**:
   - 27/27 simbol terverifikasi live di MT5: 100% menghasilkan benteng F1 dan C1 yang valid, 0 level terbalik (inverted), dan dinding makro G3 teridentifikasi presisi.
4. **Verifikasi Test Suite**:
   - Seluruh 239 unit tests pada test suite bot lulus **100% PASS** dalam 24.04 detik.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 9 September 2026 (Tengah Malam) — ZCE Multi-Horizon Structural Swing Confluence & Dashboard 8-Tier Viewport Expansion

### Latar Belakang & Identifikasi Masalah:
1. **Blind Spot Swing Low HTF pada ZCE Primitive Collection**:
   - Analisis pada chart W1 `GBPJPY` mengungkap anomali: swing low W1 terkonfirmasi pada minggu 15 Februari 2026 di level `207.233` dan swing high 2024 di `208.109` (broken into RBS) tidak dikenali sebagai benteng makro oleh ZCE. Level `207.098` hanya mendapat skor 4.17 (`GRADE_2_INTERMEDIATE`), dan area `205.00–205.50` hanya mendapat skor 2.86 (`GRADE_1_MICRO`).
   - Akar masalah: Metode `_collect_primitives()` di `zone_confluence_engine.py` sebelumnya HANYA mengoleksi `w["high"].max()` dan `w["low"].min()` per window horizon. ZCE sama sekali tidak mengoleksi pivot struktur swing (`sig.bullish_structures` dan `sig.bearish_structures` dari LuxSMC). Karena titik terendah absolut 50/100 bar W1 adalah 197.488 / 184.378, swing low penting 207.233 di tengah rentang terlewati begitu saja.
2. **Truncation & Viewport Drop pada Dashboard Surveillance**:
   - Di `dashboard.py`, tampilan tangga lantai dan plafon dibatasi kaku ke `merged_floors[:4]`. Ketika terdapat level mikro intraday di dekat harga running (207.86, 207.72, 207.50, 207.395), level kunci `207.098` tergeser ke urutan ke-5 dan terpotong (truncated) dari tabel dashboard.
   - Selain itu, filter visual viewport `v_lo = c_min_lo - vp_margin` hanya memberi buffer 80 pips, sehingga benteng makro W1/D1 di bawah 206.29 disingkirkan dari daftar kandidat.

---

### Solusi Perbaikan Kode (Checklist File):
1. **`src/analytics/zone_confluence_engine.py`**:
   - Menambahkan bobot tipe `SWING_HIGH: 0.85` dan `SWING_LOW: 0.85` pada `ZCE_W_KIND`.
   - Mengintegrasikan ekstraksi seluruh confirmed structural swings (`sig.bullish_structures` dan `sig.bearish_structures` dari LuxSMC) ke dalam primitif ZCE per timeframe (`SWING_HIGH` & `SWING_LOW`).
   - Hasil kalibrasi GBPJPY:
     * Level `207.098` terangkat dari skor 4.17 (G2) menjadi **skor 7.65 (`GRADE_3_MACRO` Fortress Wall)** berkat konfluensi W1+D1+H4+H1!
     * Level `205.00–205.50` terangkat dari skor 2.86 (G1) menjadi **skor 10.82 (`GRADE_3_MACRO` Fortress Wall)**.
2. **`dashboard.py`**:
   - Seluruh dinding terpilih ZCE (`zm.floors` dan `zm.ceilings`) dijamin 100% selalu dipreservasi ke daftar kandidat tanpa terpotong batas viewport.
   - Viewport margin diperlebar ke `max(3.5 * atr_val, 250.0 * pip_val)`.
   - Batas tier lantai dan plafon diperluas dari `[:4]` menjadi `[:8]` (F1..F8 dan C1..C8), memberikan pemetaan holistik zona mikro hingga benteng makro.
3. **`src/analytics/market_scanner.py`**:
   - Deklarasi waktu `_wib_h = datetime.now(WIB).hour` secara eksplisit di dalam `_is_direction_allowed()` guna mengeliminasi potensi `NameError`.
4. **`tests/test_market_scanner.py`**:
   - Patch `ENABLE_NIGHT_FREEZE = False` pada fixture unit test `test_m1a_sweep_ceiling_trap_awareness_and_hysteresis_reversal` agar deterministik di seluruh jam operasional.
   - Seluruh 239 unit test dipastikan **100% PASS** dalam 22.85 detik.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 9 September 2026 (Malam) — 4-Pilar Perbaikan Sistemik (CBSS Engine Non-Redundant, Economic News Blackout Window, Night Freeze & NY Sizing, Real-Time Profit Lock 7%) & Reformasi CSM Bailout

### Latar Belakang & Identifikasi Masalah:
1. **Redundansi & Jebakan Blokir Buta Keranjang (The EURAUD Dilemma)**:
   - Evaluasi kuantitatif terhadap usulan awal CBSS (Currency Basket Structural Synchronization) membuktikan bahwa memblokir buta seluruh keranjang saat 1 pair menabrak benteng makro adalah kesalahan fatal (*over-constrained false veto*). Jika `EURAUD` menempel lantai makro G3 ($dist \le 0.35\times\text{ATR}$), institusi memang sedang berebut likuiditas di sana, tetapi pair EUR lainnya seperti `EURCAD` atau `EURNZD` yang memiliki runway lapang ($\ge 1.2\times\text{ATR}$) justru merupakan *golden trade* yang wajib dieksekusi.
   - Deteksi konsolidasi dan exhaustion juga sudah ditangani secara native oleh MSE (`WATCH_ONLY`), M4 Basing Box ($\le 0.35\times\text{ATR}$), dan Wave Regime sehingga tidak boleh diduplikasi.
2. **Volatilitas Berita High-Impact & Night Slip Risk**:
   - Berita US High-Impact (CPI, PPI, NFP, ADP, FOMC) mendistorsi likuiditas global dan memicu slippage spread di seluruh 26 pair FX. Di sisi lain, pembukaan posisi FX larut malam (23:00–07:00 WIB) rentan terhadap pelebaran spread rollover (04:00 WIB) dan likuiditas tipis.
3. **Premature Cutting pada CSM Dynamic Bailout**:
   - Implementasi awal CSM Bailout (8 Sep) memotong posisi terlalu dini pada floating loss kecil ($-0.25R$ s/d $-0.30R$) hanya berdasarkan 1 bar M15, sehingga tarikan wick normal 4–5 pips memicu exit prematur sesaat sebelum harga berbalik ke TP.
4. **Giveback Risk Akumulasi Profit Harian**:
   - Tanpa mekanisme penguncian profit harian berbasis *Real-Time Net Equity Gain*, keuntungan akun yang telah mencapai $\ge +7.0\%$ berisiko tergerus kembali oleh transaksi overtrading di penutupan sesi New York.

---

### Solusi Perbaikan Kode (Checklist 8 File Wajib):
1. **`src/analytics/basket_sync_engine.py` (Modul Baru Pure Quant 0-Token)**:
   - **Bilateral Runway ZCE per-Pair**: Menghitung jarak mid-price menuju benteng $C_1/F_1$ dan stasiun $C_2/F_2$ dalam kelipatan ATR H1.
   - **Local Pair G3 Wall Veto (The EURAUD Law)**: Hanya memblokir pair yang sedang menempel benteng G3 lawan ($dist \le 0.35\times\text{ATR}$). Pair sekeranjang lainnya yang memiliki runway $\ge 1.2\times\text{ATR}$ tetap 100% diizinkan.
   - **Basket Concurrency Cap**: Membatasi maksimal 2 pair aktif per mata uang dalam arah yang sama (mencegah over-exposure risiko keranjang).
   - **Juara Keranjang (Top Runway Selector)**: Mengurutkan kandidat sekeranjang berdasarkan Runway ZCE terpanjang.
2. **`src/analytics/market_scanner.py`**:
   - Integrasi CBSS ke filter arah terpadu `_is_direction_allowed()`:
     - Validasi `is_pair_blocked_by_g3_wall()`: Tolak pair penabrak benteng G3 dengan reason `[CBSS VETO] Pair at G3 Macro Wall (dist <= 0.35x ATR)`.
     - Validasi Runway ZCE $\ge 1.2\times\text{ATR}$ (atau Grade B Wall Scalp di sesi NY).
     - Validasi Concurrency Cap $\le 2$ posisi aktif per keranjang searah.
3. **`src/analytics/economic_calendar.py` & `src/core/risk_engine.py`**:
   - **News Volatility Blackout Window ($\pm 30$ Menit)**:
     - Berita US High-Impact membekukan pembukaan trade baru di seluruh 26 pair FX.
     - Berita High-Impact non-USD hanya membekukan pair konstituen mata uang terkait.
   - **Night Freeze Cutoff Gate**:
     - Membekukan pembukaan posisi baru untuk FX dari jam 23:00 hingga 07:00 WIB (BTC 24/7 dikecualikan).
   - **Sesi NY 18:00–00:00 WIB Lot Multiplier**:
     - Menerapkan lot multiplier flat `0.50x` (diturunkan dari 0.80x) untuk mengawal sesi New York yang bergejolak.
   - **Real-Time Daily Profit Target Lockout (+7.0%)**:
     - Menghitung `(Current Equity - Start Day Balance) / Start Day Balance >= 7.0%`.
     - Begitu tercapai, mengunci `_daily_profit_locked = True`, membekukan order baru hingga 04:00 WIB besok (posisi terbuka tetap dikawal trailing/BEP).
4. **`src/analytics/position_manager.py` (Reformasi CSM Dynamic Bailout)**:
   - Ambang rugi dinaikkan ke `curr_r <= -0.50R` (eliminasi false-cut pada wick tipis).
   - Wajib konfirmasi nilai CSM Net Delta berbalik berlawanan arah selama **minimal 2 bar M15 berturut-turut**.
   - Post-Bailout Lockout: Mengunci simbol di scanner selama 90 menit (`POST_BAILOUT_COOLDOWN_SECONDS = 5400`) guna mencegah *infinite re-entry loop*.
5. **`config.py` & `.env`**:
   - Konfigurasi sinkron: `ENABLE_CBSS=True`, `CBSS_MAX_BASKET_CONCURRENCY=2`, `CBSS_MIN_RUNWAY_ATR=1.20`, `CBSS_G3_BARRIER_THRESHOLD_ATR=0.35`, `NEWS_BLACKOUT_MINUTES_BEFORE=30`, `NEWS_BLACKOUT_MINUTES_AFTER=30`, `ENABLE_NIGHT_FREEZE=True`, `NIGHT_FREEZE_START_HOUR_WIB=23`, `DAILY_PROFIT_TARGET_PERCENT=7.0`, `SESSION_NY_LOT_MULT=0.50`, `CSM_BAILOUT_MIN_LOSS_R=-0.50`, `CSM_BAILOUT_PERSISTENCE_BARS_M15=2`, `POST_BAILOUT_COOLDOWN_SECONDS=5400`.
   - Pembersihan duplikasi baris `.env` pada `DAILY_PROFIT_TARGET_PERCENT`.
6. **`main.py`**:
   - Penambahan deklarasi alias global `WIB = _WIB` (memperbaiki bug `NameError: name 'WIB' is not defined`).
   - Tampilan status clock line terminal HUD dengan badge `[TARGET +7.0% LOCKED]` dan `[NIGHT FREEZE]`.
7. **`tests/test_cbss_and_risk_shields.py` & `tests/test_sep8_enhancements.py`**:
   - Penambahan test suite komprehensif 10 unit test (`test_cbss_and_risk_shields.py`).
   - Penyelarasan skenario CSM bailout di `test_sep8_enhancements.py` ke aturan $-0.50R$ + 2 bar M15.
   - Seluruh test suite (239 unit tests) dipastikan **100% PASS** dalam 27.72 detik.
8. **`docs/CHANGELOG_SEPTEMBER_2026.md` & `AGENTS.md`**:
   - Sinkronisasi arsitektur sistem dan pencatatan komprehensif.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 9 September 2026 (Pagi II) — Pemurnian M4 ke DBD / RBR Breakout Continuation & Pemisahan Penuh SFC Layer 0 Directional Regime

### Latar Belakang & Identifikasi Masalah:
1. **Redundansi Peran M4 vs M3**:
   - Sebelumnya, M4 (`SYSTEMIC_FLOW_CONTINUATION`) memiliki fallback `M4_ALLOW_DEEP_RETEST = True` yang menembus ke level tembusan klasik (retest dalam). Hal ini bertabrakan secara fungsional dengan M3 (`BREAKOUT_RETEST`) yang secara khusus menangani retest SBR/RBS dengan konfirmasi M5 rejection wick.
2. **Pemisahan Peran SFC (Systemic Flow Catalyst) di Layer 0**:
   - Audit membuktikan bahwa fungsi penentu arah tren jangka pendek sudah ditangani secara mandiri di Layer 0 oleh `get_systemic_flow_regime()` (SFC/SFR), yang memberikan Veto Lock terhadap arah berlawanan dan *Supreme Precedence* (`FULL_ALLOW`) pada arah yang searah.
   - Oleh karena itu, M4 dapat dimurnikan 100% menjadi eksekutor pola formasi konsolidasi lanjutan di luar batas tembusan (*High-Tight Basing* $\le 0.35\times\text{ATR}$ M15/M30), yaitu Drop-Base-Drop (DBD) untuk SELL dan Rally-Base-Rally (RBR) untuk BUY.

---

### Solusi Perbaikan Kode (Checklist 8 File Wajib):
1. **`config.py` & `.env`**:
   - Mengubah `M4_SETUP_TYPE = "DBD_RBR_BREAKOUT_CONTINUATION"`.
   - Mengubah `M4_ALLOW_DEEP_RETEST = False` (mematikan fallback retest dalam).
2. **`src/analytics/market_scanner.py`**:
   - Mengubah standby label telemetry menjadi `M4 SELL DBD BASING` dan `M4 BUY RBR BASING`.
   - Menyelaraskan fallback default `M4_ALLOW_DEEP_RETEST` menjadi `False`.
   - Menambahkan fallback `mt5_connector.get_closed_bars` pada `_m4_pending_ready` untuk konsistensi data feed.
3. **`src/core/consensus.py`**:
   - Menyelaraskan filter M4 (`_apply_sltp_rules`, Pure Quant Grade S Elevation, anchor broken check) agar mengenali `DBD_RBR_BREAKOUT_CONTINUATION` dengan backward-compatibility penuh terhadap `SYSTEMIC_FLOW_CONTINUATION`.
4. **`src/analytics/position_manager.py` & `main.py`**:
   - Menyelaraskan identifikasi posisi M4 (`is_m4` dan `is_m4_order`) agar mengenali kata kunci komentar `DBD`, `RBR`, `M4`, dan `SYSTEM`.
   - Menyelaraskan batasan 1 tiket murni (`_m4_single`) di `main.py`.
5. **`src/analytics/shadow_tracker.py`**:
   - Memperbaiki pengelompokan `m_key` pada statistik kuantitatif agar setup M4 berlabel `DBD` atau `RBR` dipetakan ke `"M4"` (bukan tertukar ke `"M3"` akibat kata `BREAKOUT`).
   - Menyelaraskan rekonsiliasi komentar tiket MT5 (`DBD` / `RBR`).
6. **`src/core/llm_client.py`**:
   - Menyelaraskan string prompt dossier Stage 2 untuk merefleksikan `M4 DBD / RBR BREAKOUT CONTINUATION`.
7. **`tests/test_m4_flow_continuation.py` & Test Suite**:
   - Menambahkan unit test `test_m4_dbd_high_tight_basing_ready` dan `test_m4_deep_retest_blocked_by_default`.
   - Seluruh test suite (203 tests) dipastikan **100% PASS**.
8. **`docs/CHANGELOG_SEPTEMBER_2026.md` & `AGENTS.md`**:
   - Pencatatan detail perubahan dan pembaruan terminologi arsitektur sistem.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 9 September 2026 (Pagi I) — Quant Shadow Executive Audit Engine, Interactive Standalone Dashboard, dan Pengetatan Deduplikasi Shadow Tracker

### Latar Belakang & Identifikasi Masalah:
1. **Bias Amplifikasi Tiket Duplikat pada Shadow Paper Tracker**:
   - Audit telemetri menemukan bahwa pada gelombang tren yang panjang (seperti reli JPY tadi malam), re-trigger radar Stage 1 setiap 30 menit menghasilkan multi-tiket pada simbol dan arah yang sama (misalnya 4 tiket `CHFJPY SELL` aktif beriringan).
   - Akibatnya, data paper shadow tampak mencatat puluhan posisi menang berturut-turut untuk satu pergerakan tren yang sama, mendistorsi rasio winrate dan R:R secara artifisial.
2. **Kebutuhan Evaluasi Kuantitatif Opportunity Cost & Efisiensi Risk Gate**:
   - Pengguna membutuhkan pembuktian data empiris apakah gate-gate pembatas bot (`MAX_OPEN_POSITIONS = 6`, `ANCHOR_TOO_WIDE`, filter risk) menyelamatkan modal (*Capital Saved*) atau membuang potensi keuntungan (*Lost Opportunity*).
   - Diperlukan alat analitik CLI dan dashboard interaktif mandiri yang dapat membedah performa per mekanisme (M1–M4), Tier (`GRADE_S` s/d `GRADE_B`), ekskursi intra-trade (MFE vs MAE), dan efisiensi proteksi Break-Even (BEP).

---

### Solusi Perbaikan Kode:
1. **Engine Analitik Kuantitatif Mandiri (`src/analytics/shadow_audit_engine.py`)**:
   - Membaca `data/quant_shadow_trades.jsonl`, `data/quant_shadow_state.json`, dan histori deal MT5 langsung dari broker.
   - **Dual-Mode De-biasing**:
     - *Mode De-biased Legs (Default)*: Mengonsolidasikan tiket-tiket overlap pada pair dan arah yang sama menjadi 1 *Trade Leg Episode*, mengeliminasi distorsi multi-tiket.
     - *Mode Raw Signals*: Menghitung setiap baris sinyal radar apa adanya untuk audit frekuensi trigger.
   - **Metrik Kuantitatif Rigor**:
     - *Wilson Score 95% Confidence Interval* untuk evaluasi winrate tanpa overclaim.
     - *Counterfactual Opportunity Cost Delta ($\Delta R$)*: Menghitung selisih laba/rugi posisi yang di-skip (`SKIPPED_MAX_POSITIONS`, `SKIPPED_ANCHOR_TOO_WIDE`).
     - *Edge Attribution*: Ranking winrate, profit factor, dan net R per mekanisme M1–M4 dan Tier Grade.
     - *Excursion Dynamics*: Menghitung distribusi MFE dan MAE untuk memvalidasi batas Stop Loss dan titik pantul.
     - *BEP Efficiency Index*: Mengukur persentase trade `SAVED_BY_BEP` vs `STOLEN_RUNNER`.
2. **Root CLI Command (`shadow_audit.py`)**:
   - Menghasilkan ringkasan ANSI box formatting tingkat institusional di terminal (`py shadow_audit.py [--open] [--days <N>]`).
   - Otomatis mengompilasi dan meluncurkan dashboard HTML ke browser default.
3. **Interactive Standalone Executive Dashboard (`docs/shadow_executive_audit.html`)**:
   - Single-file self-contained HTML bertema *institutional dark mode* (`#080b11`), tipografi `Inter` + `JetBrains Mono`, 0% emoji.
   - Dilengkapi *Dual-Mode Toggle Switch* instan (De-biased vs Raw), 5 kartu KPI eksekutif, comparative cumulative equity curve, gate disposition breakdown, scatter plot MFE vs MAE, dan interactive trade table dengan live search & sorting.
4. **Pengetatan Deduplikasi Live di `src/analytics/shadow_tracker.py`**:
   - Memperbaiki `register_trigger`: Menolak pembukaan tiket shadow baru jika pair & arah yang sama sudah memiliki posisi aktif atau pending (`existing.status in ("ACTIVE", "PENDING")`). Mencegah 100% tiket duplikat di masa depan.
5. **Unit Test Suite Lengkap (`tests/test_shadow_audit_engine.py`)**:
   - 4 unit test mandiri (ingestion, de-biasing, metrics, HTML generator) dengan hasil **100% PASS**.

---

### Hasil Pengujian & Verifikasi:
- **CLI Execution (`py shadow_audit.py`)**:
  - Sample De-biased: 102 Resolved Legs (dari 169 Raw Triggers).
  - MT5 Real Deals (48h): 59 Deals, Winrate 69.5%, Net Profit +$285.48, Profit Factor 1.22.
  - Opportunity Cost: Lost Profit +2.51R vs Saved Drawdown +3.60R (Netto proteksi modal positif).
  - Top Edge Mech: M3 Breakout Retest (Winrate 67.9%, +8.17R, PF 2.38).
  - BEP Efficiency: 100.0% Saved (2 trade terselamatkan BEP dari SL penuh).
- **Test Suite**: 201/201 tests passed (100% OK).

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Malam X) — Integrasi ZCE Station Runway Delivery, Fortress Shielding SL, dan Shadow Tracking untuk Aborted Trades

### Latar Belakang & Identifikasi Masalah:
1. **Kekakuan Batas Dealing Range Persentase (M1..M4 False Blocks)**:
   - Evaluasi kuantitatif membuktikan bahwa filter Dealing Range kaku (misal melarang BUY di >50% atau SELL di <50%) memblokir setup tren valid saat harga sedang berada dalam fase ekspansi menuju dinding ZCE berikutnya.
2. **Ketiadaan Tracking untuk Trade yang Dibatalkan oleh SL/TP Rules (`ANCHOR_TOO_WIDE`)**:
   - Trade valid yang dibatalkan oleh filter runway ZCE (seperti NZDUSD 143 pts < 193 pts floor) tidak tercatat di mana pun, sehingga pengguna tidak dapat mengukur *opportunity cost* dari aturan SL/TP tersebut.
3. **Konkurensi File Locking di Windows (`shadow_tracker_state.json`)**:
   - `dashboard.py` yang membaca status shadow tracker secara bersamaan dengan `main.py` terkadang memicu `[WinError 5] Access is denied` saat `_save_state()` mencoba me-replace file atomic.

---

### Solusi Perbaikan Kode:
1. **ZCE Station Runway Delivery & Eliminasi Batas Kaku DR**:
   - Menggantikan batas Dealing Range kaku dengan validasi kapasitas runway ZCE ($\text{Runway} \ge 0.50\times\text{ATR}$ atau $\ge 0.75R$) dan proteksi anti-knife Wave Regime.
   - Memberikan kelonggaran bagi setup M1..M4 untuk beroperasi selama tersedia ruang pergerakan leluasa menuju stasiun $C_1/F_1$ atau $C_2/F_2$.
2. **Dynamic Fortress SL Shielding & Absorption di MSE**:
   - Menempatkan jangkar Stop Loss di balik dinding ZCE terdekat dengan bantalan pelindung (*cushion*).
   - Mode `ASCENDING_ABSORPTION` menuju $C_2$ untuk bias HTF Bullish, dan `DESCENDING_ABSORPTION` menuju $F_2$ untuk bias HTF Bearish.
3. **Pencatatan Otomatis Shadow Paper Tracker untuk Aborted Trades**:
   - Proposal order yang dibatalkan oleh aturan SL/TP atau kapasitas runway ZCE otomatis didaftarkan ke `shadow_tracker` dengan disposisi `"SKIPPED_ANCHOR_TOO_WIDE"` (ditandai dengan badge ungu `PAPER (ANCHOR_TOO_WIDE)` di dashboard).
4. **Resiliensi File Locking Windows pada `shadow_tracker._save_state()`**:
   - Menambahkan mekanisme retry hingga 5 kali dengan jeda exponential backoff dan fallback penulisan langsung untuk mengeliminasi error akses konkuren.
5. **Indikator ZCE Runway Target di Dashboard**:
   - Mengganti teks statis `DR: 50%` pada baris ke-3 kartu watchlist dashboard dengan badge cyan dinamis (misal `→C1: +28p`, `→F1: +42p`) beserta tooltip rasio ATR.
   - Memperlebar clamp viewport grafik lilin menjadi $1.25\times\text{ATR}$ (minimal 80 pips) agar dinding $F_1/F_2$ dan $C_1/C_2$ selalu terlihat jelas.

---

### Hasil Pengujian & Verifikasi:
- **Unit Test Suite**: 197/197 tests passed (100% OK).
- **Live Verifikasi**: Cockpit dashboard menampilkan badge runway dinamis dan pencatatan shadow tracker berjalan mulus tanpa error locking.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Malam IX) — Pelepasan Batas Konsentrasi Keranjang Valas di .env dan Debouncing Soft Timing Hold pada SLTP Abort

### Latar Belakang & Identifikasi Masalah:
1. **Penyelarasan Batas Konsentrasi Mata Uang (`MAX_CURRENCY_BASKET_EXPOSURE`)**:
   - Pada sesi 7 September 2026, batas konsentrasi mata uang disepakati untuk dilepas (`MAX_CURRENCY_BASKET_EXPOSURE=99`) guna mengumpulkan data forward test tanpa hambatan kuota artifisial, karena trade yang melebihi kapasitas akan otomatis dicatat ke *Shadow Paper Tracker*.
   - Namun, variabel tersebut belum terdefinisi di `.env`, menyebabkan sistem runtime jatuh ke nilai default kaku `3`. Akibatnya, trade valid seperti `NZDUSD` dan 8 kali sinyal `USDJPY` dibatalkan paksa oleh Risk Engine.
2. **Spamming Loop pada Penolakan SL/TP Rules (`ANCHOR_TOO_WIDE`)**:
   - Ketika proposal order dibatalkan oleh `_apply_sltp_rules` (seperti `EURGBP` dengan realized R:R $0.27:1 < 0.75R$), `main.py` langsung mereturn `False` tanpa mencatat jeda timing.
   - Akibatnya, radar memindai ulang dan mencetak proposal yang sama berulang-ulang setiap siklus 60 detik.

---

### Solusi Perbaikan Kode:
1. **Pelepasan Konsentrasi Valas di `.env` & `config.py`**:
   - Menambahkan `MAX_CURRENCY_BASKET_EXPOSURE=99` ke dalam `.env`.
   - Mengubah nilai default fallback di `config.py` menjadi `99`.
   - Menambahkan *fast-bypass* pada `src/core/risk_engine.py` saat `MAX_CURRENCY_BASKET_EXPOSURE >= 90`.
2. **Debouncing Soft Timing Hold pada Abort SL/TP Rules (`main.py`)**:
   - Pada blok `if not sltp_ok:`, memanggil `scanner_inst.record_soft_timing_hold(sym, cand_type, dir_str)` sehingga instrumen dijeda bernapas 3 menit tanpa mengunci mekanisme permanen.

---

### Hasil Pengujian & Verifikasi:
1. **Unit Test Suite**:
   - `tests/test_risk_engine_magic_filter.py`, `tests/test_dashboard.py`, `tests/test_market_scanner.py`: **46/46 PASSED (100%)**.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Malam VIII) — Perluasan Toleransi Wall Proximity Anti-Bull/Anti-Bear Veto dan Stabilisasi Resensi Standby M1

### Latar Belakang & Identifikasi Masalah:
1. **False Rejection Veto Anti-Trend pada M1A Sweep Menabrak Dinding Makro G3 (`GBPUSD`)**:
   - Pada instrumen `GBPUSD` H1, harga membentuk *Universal Liquidity Sweep & SFP* di atap Asian High (1.35498) dan menabrak plafon makro $C_1$ (1.35525, `GRADE_3_MACRO`) dengan high menembus ke 1.35620. Mandat MSE mengeluarkan diagnosis `CEILING_REJECTION`.
   - Namun, radar terus menerus menolak eksekusi sell dengan log:
     `[SWEEP SELL ANTI-BULL VETO] GBPUSD-ECN SKIP: Fading bullish trend is forbidden unless hitting G3 Macro Fortress Wall or C1 Rejection (Current: GRADE_3_MACRO)`.
   - Investigasi mendalam menemukan bahwa variabel `is_macro_wall` mengevaluasi `abs(ref_top - c1_struct) <= SWEEP_WALL_MATCH_ATR_MULT * atr` dengan `SWEEP_WALL_MATCH_ATR_MULT = 0.15` ($\approx 1.87\text{ pips}$). Karena selisih antara `ref_top` (1.35498) dan `c1_struct` (1.35525) adalah $2.7\text{ pips}$, `is_macro_wall` bernilai `False` kendati wick candle nyata menembus kedua level tersebut hingga 1.35620! Selain itu, `is_anti_bull_veto` tidak memberikan override bagi mandat penolakan MSE jika `is_macro_wall_g2_g3` bernilai False.
2. **Flipping Prematur Indikator Standby M1 pada Cockpit Dashboard**:
   - Pada fungsi `get_radar_standbys()`, penentuan arah `m1_dir` didasarkan pada `is_near_floor` vs `is_near_ceiling`.
   - Begitu harga GBPUSD mulai merosot turun sesuai arah Bearish Sweep menuju target lantai $F_1$, harga memasuki ambang $0.50\times\text{ATR}$ dari $F_1$, yang memicu `is_near_floor = True` dan membalik arah `m1_dir` menjadi +1 (Bullish Sweep).
   - Akibatnya, indikator trajektori dan marker Bearish Sweep di puncak atap tiba-tiba hilang dan berganti menampilkan sapuan lantai dari 4 bar yang lalu (`bot_bar_age = 4`).

---

### Solusi Perbaikan Kode:
1. **Perluasan Toleransi Wall Proximity & Symmetrical Hit Detection (`src/analytics/market_scanner.py`)**:
   - Memasukkan level $C_1$ langsung ke dalam `valid_tops` dan $F_1$ ke `valid_bots`.
   - Memperluas toleransi jarak dinding `wall_tol` menjadi $\max(\text{SWEEP\_WALL\_MATCH\_ATR\_MULT}, 0.50) \times \text{ATR}$ ($\approx 6.2\text{ pips}$).
   - Memvalidasi kedekatan dinding dari titik penetrasi fisik nyata:
     `is_macro_wall_g3 = (c1_grade == "GRADE_3_MACRO") and (is_macro_wall or (c1_struct > 0 and abs(live_h - c1_struct) <= wall_tol))`.
   - Override mandat langsung dari MSE:
     `if is_mse_sell_mandate and (is_macro_wall_g3 or is_macro_wall_g2_g3 or dr_pos_val >= 0.65): is_anti_bull_veto = False` (serta simetris untuk Bullish Sweep / Floor Rejection).
2. **Stabilisasi Resensi Standby M1 Berbasis Event Lifecycle (`src/analytics/market_scanner.py`)**:
   - Memisahkan evaluasi resensi sapuan atas (`top_bar_age`) dan sapuan bawah (`bot_bar_age`).
   - Menerapkan aturan histeresis resensi: jika salah satu sisi memiliki sapuan segar (`bar_age <= 3`) dan sisi lainnya tidak (`bar_age > 3`), arah $M_1$ dikunci pada sapuan segar tersebut.
   - Mengeliminasi 100% bug flipping prematur: trajektori Bearish Sweep tetap terkunci pada Asian High hingga siklus pergerakan harga selesai terkirim ke target.

---

### Hasil Pengujian & Verifikasi:
1. **Unit Test Suite**:
   - `tests/test_dashboard.py`, `tests/test_m2_pullback_and_corridor.py`, `tests/test_m3_discount_guard_and_leapfrog.py`, `tests/test_market_scanner.py`: **56/56 PASSED (100%)**.
2. **Integritas Runtime**:
   - Zero syntax/import errors, anti-trend veto beroperasi secara presisi dengan perlindungan dinding makro G3.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Malam VII) — Integrasi Trajektori Visual M1A Sweep Reclaim dan Penyelarasan Directional Lock Gate 4 CSM

### Latar Belakang & Identifikasi Masalah:
1. **Ketiadaan Garis Trajektori Visual Proyeksi M1A Sweep Reclaim**:
   - Pada chart Lightweight Cockpit (`dashboard.py` / `dashboard_assets.py`), mekanisme M1B, M2, M3, dan M4 memiliki garis proyeksi trajektori panah putus-putus lengkap dari titik *origin/retest* menuju target *TP1* dan *TP2 Macro Expansion*.
   - Sebaliknya, mekanisme M1A (*Universal Liquidity Sweep*) belum membangun dictionary `"trajectory"` di dalam `get_radar_standbys()`. Akibatnya, saat M1A aktif (misal `[M1A SELL MACRO SWEEP] Waiting Close Reclaim`), chart tidak menggambar vektor panah turun ke floor F1, melainkan hanya menampilkan trajektori milik setup lain (seperti M2 Bullish Pullback ke atas) sehingga membingungkan operator visual.
2. **Diskoneksi Evaluasi Arah Gate 4 CSM vs Gate 3 Directional Lock**:
   - Pada panel audit 7-Gate di Cockpit Dashboard, Gate 3 mengunci instrumen ke `Lock: SELL ONLY` (berdasarkan inisialisasi mandat makro MSE `CEILING_REJECTION` dengan score `-0.80`).
   - Namun, Gate 4 (Boitoki CSM Flow Alignment) menentukan arah evaluasi secara naif berdasarkan `target_dir = 1 if macro.get("is_bull") else -1`. Karena tren D1/H1 GBPUSD bernilai bullish, Gate 4 menguji CSM terhadap arah BUY: `"Net Delta +0.89 selaras atau netral dengan BUY momentum arah"`.
   - Hal ini menimbulkan paradoks visual: G3 mengunci SELL ONLY, tetapi G4 mengevaluasi terhadap BUY.

---

### Solusi Perbaikan Kode:
1. **Pembangunan Objek Trajektori Dual-Tier M1A (`src/analytics/market_scanner.py`)**:
   - Pada fungsi `get_radar_standbys()`, blok M1A kini menyusun dictionary `"trajectory"` lengkap:
     * `origin_price`: Titik ekstrem wick sapuan likuiditas ($p_{\text{sweep}} + 0.35\times\text{ATR}$ untuk short, $p_{\text{sweep}} - 0.35\times\text{ATR}$ untuk long).
     * `retest_price`: Level struktural yang disapu (`m1_price`, e.g. Asian High / PDH / C1).
     * `target_tp1`: Target pantulan equilibrium atau floor/ceiling pertama ($F_1$ untuk short, $C_1$ untuk long).
     * `target_tp2`: Target makro ekspansi lanjutan ($F_2$ deep floor untuk short, $C_2$ deep ceiling untuk long).
     * `direction`: Arah eksekusi sweep (`m1_dir`).
     * `phase`: Status konfirmasi (`m1_status`, e.g. `WAITING_CLOSE_RECLAIM` atau `RECLAIMED_FADING`).
2. **Dukungan Visual Styling M1 Sweep di Chart (`dashboard_assets.py`)**:
   - Menambahkan warna tema oranye istitusional (`rgba(251, 146, 60, 0.95)`) untuk trajektori M1/M1B.
   - Menambahkan penanda teks pill khusus: `1. Sweep High / Sweep Low` pada origin, dan `2. Sweep Reclaim` pada titik retest.
3. **Penyelarasan Hierarki `target_dir` Gate Evaluator (`dashboard.py`)**:
   - Menyelaraskan evaluasi arah Gate 2–4 dengan hierarki prioritas:
     1. `m4_dir_override`: Arah episode Systemic Flow Regime M4 (jika aktif).
     2. `dir_val`: Directional Lock Hysteresis State (`BUY ONLY` / `SELL ONLY` jika aktif).
     3. Fallback ke tren struktural makro `is_bull` / `is_bear`.
   - Gate 4 CSM kini mengevaluasi terhadap arah yang dikunci oleh G3 (`SELL [Lock Dir]`), menghilangkan 100% kontradiksi visual.

---

### Hasil Pengujian & Verifikasi:
1. **Unit Test Suite**:
   - `tests/test_dashboard.py` (`test_m1_standbys_trajectory` & `test_gate4_directional_lock_alignment`): **7/7 PASSED (100%)**.
2. **Visual Cockpit Runtime**:
   - GBPUSD menampilkan G3 `Lock: SELL ONLY` dan G4 mengevaluasi terhadap arah `SELL` secara konsisten.
   - M1A standbys mengekspor trajektori lengkap menuju $F_1$ (1.35402).

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Malam VI) — Penyelarasan Contextual Limit Trap Awareness M1A Sweep, Propagasi Entry Price, dan Perbaikan Directional Hysteresis Reversal

### Latar Belakang & Identifikasi Masalah:
1. **False Positive Trap Veto pada M1A Sweep di Atap Ceiling C1 (`GBPUSD`)**:
   - Pada instrumen `GBPUSD` (H1), harga menyapu likuiditas di atas *distal ceiling* $C_1$ (1.35578 D1_VAH) hingga mencapai puncak 1.35620 (Dealing Range 91.0%), membentuk pola *Universal Liquidity Sweep & SFP*.
   - Setup ini diidentifikasi oleh radar sebagai `M1A Universal Liquidity Sweep (BEARISH_SWEEP)`. Namun, saat melewati gate `_is_direction_allowed(-1, "BEARISH_SWEEP")`, order langsung ditolak oleh *Forbidden Trap Rule*:
     `"Do NOT short into confirmed RBS support at 1.35400 (dist 17.8p < 25.0p)"`.
   - Hal ini merupakan *false positive* fatal: short order dieksekusi di langit-langit $C_1$ (1.35578–1.35620), berjarak leluasa $\sim 20$ pips di atas support floor $F_1$ (1.35400). Pengecekan trap support seharusnya hanya memblokir *market chase* saat harga berada di dasar floor, bukan saat *fade rejection* di ceiling.
2. **Ketiadaan Propagasi `entry_price` pada M1A Radar**:
   - Panggilan `_is_direction_allowed` pada M1A Bearish Sweep dan Bullish Sweep di `src/analytics/market_scanner.py` tidak menyertakan parameter `entry_price`. Akibatnya, logika *Contextual Limit Awareness*:
     `entry_price >= c1_lvl - 0.35 * atr_val` atau `entry_price >= f1_lvl + 0.40 * atr_val`
     gagal aktif dan jatuh ke evaluasi harga pasar live (`current_price`), serta variabel `is_limit_setup` tidak mengenali kata kunci `"SWEEP"`.
3. **Mismatch String Matching Directional Hysteresis**:
   - Pada gate Hysteresis koridor makro, kondisi pembatalan bias/reversal extreme dealing range (`dr_pos >= 0.80` untuk SELL) hanya memeriksa string `"UNIVERSAL_LIQUIDITY_SWEEP"` pada `setup_label`.
   - Namun, M1A radar mengoper label berformat `"BEARISH_SWEEP"` atau `"BULLISH_SWEEP"`, sehingga setup sweep di ekstrem Dealing Range gagal memicu pengecualian hysteresis dan diblokir secara keliru oleh directional lock.

---

### Solusi Perbaikan Kode (`src/analytics/market_scanner.py`):
1. **Propagasi Parameter `entry_price` pada M1A Sweep**:
   - Pada blok `is_bearish_sweep`: mengoper `entry_price=ref_top` ke fungsi `_is_direction_allowed(-1, "BEARISH_SWEEP", entry_price=ref_top)`.
   - Pada blok `is_bullish_sweep`: mengoper `entry_price=ref_bot` ke fungsi `_is_direction_allowed(1, "BULLISH_SWEEP", entry_price=ref_bot)`.
2. **Perluasan Pengenalan Limit Setup & Boundary Tolerance**:
   - Menambahkan string `"SWEEP"` ke dalam `is_limit_retest` di `_is_direction_allowed`, sehingga seluruh setup sweep diperlakukan sebagai limit order yang sadar konteks level batas.
   - Pengecekan Mid-Chamber Trap melonggarkan filter jika setup sweep berada di batas chamber:
     * SELL diperbolehkan jika `dr_pos >= 0.55` atau `entry_price >= c1_lvl - 0.35 * atr_val`.
     * BUY diperbolehkan jika `dr_pos <= 0.45` atau `entry_price <= f1_lvl + 0.35 * atr_val`.
   - Trap support/resistance membebaskan order limit jika harga entri berada di sisi aman level yang berlawanan (`entry_price >= f1_lvl + 0.40 * atr_val` untuk short atap $C_1$).
3. **Harmonisasi String Matching Directional Hysteresis**:
   - Memperbarui `is_m1a_sweep` pada evaluasi `sweep_reversal` agar mencakup `"UNIVERSAL_LIQUIDITY_SWEEP"`, `"BEARISH_SWEEP"`, dan `"BULLISH_SWEEP"`, seraya tetap mengecualikan varian M1B (`"M1B"` atau `"INDUCED"`).
4. **Definisi Eksplisit Variabel Enclosing Scope `atr_val`**:
   - Mendeklarasikan `atr_val = atr_pts * pt` sebelum pemanggilan `_is_direction_allowed` guna mencegah `UnboundLocalError`.

---

### Hasil Pengujian & Verifikasi:
1. **Unit Test Spesifik**:
   - `tests/test_market_scanner.py` (`test_m1a_sweep_ceiling_trap_awareness_and_hysteresis_reversal`): **1/1 PASS (0.24s)**, memvalidasi lolosnya SELL M1A di ceiling $C_1$ tanpa terblokir trap support $F_1$, serta aktivasi `sweep_reversal` pada DR 91%.
2. **Full Test Suites**:
   - `tests/test_market_scanner.py`: **35/35 PASSED (100%)**.
   - `tests/test_symbol_rotation.py`: **4/4 PASSED (100%)**.
   - `tests/test_m1b_sweep.py`, `tests/test_fresh_breakout_and_net_rr.py`, `tests/test_macro_strategic_engine.py`: **20/20 PASSED (100%)**.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Malam V) — Perbaikan Monotonik Proximity Tiering F1/F2 dan C1/C2 pada Dashboard Visual

### Latar Belakang & Identifikasi Masalah:
1. **Inversi Visual Label F1/F2 dan C1/C2 di Cockpit Chart (`dashboard.py`)**:
   - Pada grafik instrumen yang mengalami tren ekspansi kuat (seperti `CADJPY` yang melakukan *waterfall drop* 500 pips dari 116 ke 111), visualisasi chart menampilkan anomali di mana:
     * Label `C1 [G1]` melompat jauh ke level 115.077 (SMC H1 Order Block di puncak), melewati level resistance MSE di 111.861 dan 112.028.
     * Level resistance yang lebih dekat ke harga (`112.028`) malah dilabeli sebagai `C2 [MSE] (Deep Resistance)`, sehingga di chart $C_2$ berada di bawah $C_1$.
     * Begitu pula di sisi support: level floor yang paling dekat dengan harga (`111.258`) dilabeli sebagai `F2 [MSE] (Deep Support)`, sedangkan level floor yang jauh di dasar (`109.982`) dilabeli sebagai `F1 [G1]`, sehingga $F_2$ berada di atas $F_1$ (tertukar secara visual).
2. **Akar Masalah di Logika Fallback `dashboard.py`**:
   - Pada fungsi `get_symbol_detail`, klaster ZCE dan level fallback MSE disatukan tanpa pengurutan ulang berdasarkan kedekatan jarak fisik (*physical distance*) ke harga live.
   - Pengecekan `has_f1` menghasilkan `True` karena ZCE menyumbang satu floor di 109.982 (berlabel `F1`), sehingga MSE $F_1$ terdekat diabaikan. Namun `has_f2` menghasilkan `False`, sehingga MSE $F_2$ (111.258) disisipkan sebagai slot `F2`, menghasilkan inversi visual.
   - Di sisi engine eksekusi MT5 (`MarketScanner`), radar sebenarnya menggunakan level yang benar ($F_1 = 111.399, C_1 = 111.861$) karena ZCE yang jaraknya $> 2.0\times\text{ATR}$ (`imm_cap`) otomatis di-reject dan di-fallback ke MSE. Kesalahan murni berada pada perakitan visual dashboard.

---

### Solusi Perbaikan Kode (`dashboard.py`):
1. **Penggabungan Menyeluruh & Deduplikasi Proksimitas**:
   - Mengumpulkan seluruh kandidat floor ($p < \text{mid}$) dan ceiling ($p > \text{mid}$) dari ZCE ladder maupun MSE baseline.
   - Mengeliminasi duplikasi zona dalam radius toleransi `proximity_thr = max(0.20 * atr_val, 4.0 * pip_val)` dengan mempertahankan skor bobot tertinggi.
2. **Penetapan Tier Monotonik Berdasarkan Kedekatan Jarak ke Harga**:
   - **Floors**: Diurutkan secara *strictly descending* ($p_0 > p_1 > p_2$). Level paling dekat ke harga ($p_0$) **mutlak ditetapkan sebagai F1**, level berikutnya ($p_1$) sebagai **F2**, dan level lebih dalam sebagai **F3/F4**.
   - **Ceilings**: Diurutkan secara *strictly ascending* ($p_0 < p_1 < p_2$). Level paling dekat ke harga ($p_0$) **mutlak ditetapkan sebagai C1**, level berikutnya ($p_1$) sebagai **C2**, dan level lebih tinggi sebagai **C3/C4**.
   - Menjamin 100% konsistensi matematis:
     $$\text{C4} > \text{C3} > \text{C2} > \text{C1} > \text{Price} > \text{F1} > \text{F2} > \text{F3}$$
   - Label dinding mempertahankan atribut sumbernya (misal `F1 [MSE] 111.399 (Support Wall)` dan `F2 [G1] 109.982 (3.1 • H1 • SMC)`).

---

### Hasil Pengujian & Verifikasi:
1. **Verifikasi Runtime CADJPY**:
   * $F_1 = 111.399$ (`F1 [MSE] Support Wall` — support terdekat di bawah harga).
   * $F_2 = 109.982$ (`F2 [G1] SMC` — deep support di dasar).
   * $C_1 = 111.856$ (`C1 [MSE] Resistance Wall` — resistance terdekat di atas harga).
   * $C_2 = 112.026$ (`C2 [MSE] Deep Resistance` — resistance di atas C1).
   * $C_3 = 115.077$ (`C3 [G1] SMC` — macro ceiling).
   * $C_4 = 115.251$ (`C4 [G1] OB` — macro ceiling).
2. **Unit Test Suite**:
   * `tests/test_dashboard_btc_xray.py`: **2/2 PASS**.
   * `tests/test_market_scanner.py`: **100% PASS**.

---

## 0.0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Malam IV) — Session-Aware NY Pacific Cross Lock (Opsi 2): Eliminasi Choppy Crosses AUD/NZD di Sesi New York

### Latar Belakang & Identifikasi Masalah:
1. **Audit Empiris Kinerja Sesi AUD/NZD (14 Hari MT5 Deals & 118 Shadow Trades)**:
   - Evaluasi kuantitatif menunjukkan disparitas performa ekstrem pada pair ber-driver Pasifik (AUD & NZD) antar-sesi:
     * **Sesi Asia (07:00–14:00 WIB)**: AUD/NZD Crosses mencatat Win Rate **85.7%** (+$250.82) di deal riil MT5 dan Avg MFE **0.71R** (+6.15R) di shadow trades.
     * **Sesi London (14:00–19:00 WIB)**: AUD/NZD Crosses mencatat Win Rate **71.4%** (+$326.32) di MT5 dan Avg MFE **0.51R** (+3.70R).
     * **Sesi New York & Overlap (19:00–24:00 WIB)**: AUD/NZD Crosses anjlok menjadi sumber kerugian utama di MT5 (**-$148.04**, rugi di `EURNZD` -$140.67 dan `GBPAUD` -$19.35), Win Rate shadow runtuh ke **11.8%**, dan **Peak MFE ambruk dari 0.71R ke 0.38R**.
2. **Karakter Mikrostruktur Pasar Sesi NY**:
   - Pasar domestik Sydney dan Wellington telah tutup sejak pukul 14:00 WIB. Di sesi NY, cross non-USD (`EURNZD`, `GBPAUD`, `GBPNZD`, `AUDNZD`, `AUDCAD`, `NZDCAD`, `AUDCHF`, `NZDCHF`, `AUDJPY`, `NZDJPY`) kehilangan katalisator order flow primer dan terjebak dalam *choppy micro-range*.
   - Rata-rata ekspansi harga (MFE 0.38R) tidak mampu mencapai trigger TP1 (0.45R–0.50R), mengakibatkan posisi menggantung sideways hingga tersapu time-decay atau lonjakan spread menjelang rollover subuh.
   - Sebaliknya, **JPY Crosses** (`USDJPY`, `EURJPY`, `GBPJPY`) tetap likuid dan mencetak tren bersih di NY berkat korelasi kuat terhadap imbal hasil obligasi AS (US Treasury Yields) dan sentimen ekuitas Wall Street.
   - Pasangan USD Majors (`AUDUSD` dan `NZDUSD`) tetap digerakkan oleh arus makro USD.

---

### Komponen & Solusi Utama (Opsi 2: Exotic/Cross-Only Lock):
1. **Konfigurasi Parameter Sesi Baru (`.env` & `config.py`)**:
   - `NY_SESSION_START_HOUR_WIB = 19`: Batas awal transisi menuju Sesi New York (19:00 WIB).
   - `NY_LOCK_PACIFIC_CROSSES = true`: Flag perizinan penguncian cross AUD/NZD non-USD pada sesi NY.
2. **Helper Klasifikasi Cross Pasifik `is_pacific_cross(symbol: str) -> bool` (`config.py`)**:
   - Mengembalikan `True` untuk cross pair yang mengandung `AUD` atau `NZD`, tetapi secara eksplisit mengecualikan pasangan USD (`AUDUSD` dan `NZDUSD`) serta instrumen Crypto (`BTCUSD.c`).
3. **Penyelarasan Gate Sesi Radar (`src/analytics/market_scanner.py`)**:
   - Memperbarui fungsi `is_symbol_allowed_for_session(symbol: str, hour_wib: int) -> bool`:
     * **07:00–14:00 WIB (Asia)**: Hanya pair ber-driver Pasifik/Asia (`JPY`, `AUD`, `NZD`) yang aktif.
     * **14:00–19:00 WIB (London Core)**: Seluruh 26 simbol FX aktif secara leluasa.
     * **19:00–23:59 WIB (New York & Overlap)**:
       - Cross AUD/NZD non-USD (`EURNZD`, `GBPAUD`, `GBPNZD`, `AUDNZD`, `AUDCAD`, `NZDCAD`, `AUDCHF`, `NZDCHF`, `AUDJPY`, `NZDJPY`) **di-lock 100% dari pemindaian**.
       - `AUDUSD`, `NZDUSD`, seluruh `JPY Crosses`, serta seluruh *European/American majors & crosses* (`EURUSD`, `GBPUSD`, `USDCAD`, `USDCHF`, `EURGBP`, `EURCHF`, `GBPCHF`, `EURCAD`, `GBPCAD`) **tetap aktif**.
     * **00:00–07:00 WIB (Dead Zone)**: Seluruh instrumen FX terkunci total. Crypto `BTCUSD` aktif 24/7.
   - Menyatukan filter session-aware router di loop teratas `scan_fast_radar` agar tidak membuang resource CPU membaca tick dari simbol yang terkunci sesi.

---

### Hasil Pengujian & Verifikasi:
1. **Unit Test Suite**:
   - `tests/test_market_scanner.py` (`test_session_aware_pair_filtering`): **1/1 PASSED (100%)**, memvalidasi blokir Pacific Crosses di jam 20:00 WIB dan kelolosan `AUDUSD`, `NZDUSD`, `USDJPY`, `EURUSD`.
   - `tests/test_symbol_rotation.py`, `test_m2_pullback_and_corridor.py`, `test_m3_discount_guard_and_leapfrog.py`, `test_sep8_enhancements.py`: **27/27 PASSED (100%)**.
   - Zero regression, zero missing imports.

---

## 0.0.0.0.0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Malam III) — Rekalibrasi Presisi Dealing Range M2/M3, Pembersihan Anti-Sweep SFP Veto, Perbaikan Control Flow Fall-Through M4, dan M4 Basing Symbol Resolver

### Latar Belakang & Identifikasi Masalah:
1. **Penurunan Frekuensi Eksekusi Pasca-Guard M3 & Corridor M2**:
   - Pasca commit `0169c59` yang memperkenalkan batas kaku Dealing Range (M3 BUY max 0.60, M3 SELL min 0.40, M2 BUY max 0.55, M2 SELL min 0.45), bot mengalami fenomena "jarang buka posisi" di sesi sore hingga malam.
   - Di terminal CLI teramati dominasi status `WATCH` (22 pair) dengan hanya sedikit pair yang mencapai `GO` atau `ARM`, kendati pasar sedang bergerak dalam tren ekspansi sehat.
2. **Audit Empiris 17 Pair Terblokir (16:00–18:00 WIB vs 20:00 WIB Live)**:
   - Evaluasi kuantitatif terhadap 17 sinyal yang diblokir oleh radar menghasilkan temuan asimetri tajam:
     * **Bad Blocks (8 Pair, +152.7 Pips Profit Terlewat)**: Pasangan mata uang major/cross dengan momentum tren kuat (USD, EUR, GBP) diblokir oleh batas kaku Dealing Range di 60%/40% padahal tren berlanjut menghasilkan runner besar:
       - `GBPUSD` BUY (+29.0 pips)
       - `USDJPY` SELL (+33.7 pips)
       - `EURJPY` SELL (+25.5 pips)
       - `AUDUSD` BUY (+13.7 pips)
       - `USDCAD` SELL (+11.7 pips)
       - `EURGBP` SELL (+11.7 pips)
       - `AUDCAD` BUY (+10.7 pips)
       - `EURUSD` BUY (+8.7 pips)
     * **Good Blocks (4 Pair, -55.9 Pips Adverse Excursion Terselamatkan)**: Pasangan cross NZD yang sedang mengalami koreksi tajam berhasil diselamatkan dari kerugian berkat guard DR:
       - `EURNZD` BUY (-31.8 pips adverse drop terselamatkan)
       - `NZDCAD` SELL (+12.5 pips adverse bounce terselamatkan)
       - `AUDNZD` BUY (-5.9 pips adverse drop terselamatkan)
       - `GBPNZD` BUY (-5.7 pips adverse drop terselamatkan)
     * **Neutral (5 Pair, +0.4 Pips)**: `EURCAD` (+1.3p), `GBPJPY` (+0.7p), `GBPCHF` (+0.9p), `AUDCHF` (-1.0p), `NZDCHF` (-1.5p).
   - **Kesimpulan Kuantitatif**: Dealing Range kaku 60%/40% bekerja sangat baik menahan false breakdown pada pair yang exhaust (cross NZD), namun **terlalu restriktif** untuk pair dengan momentum katalisator institusional kuat (USD/EUR/GBP flow).
3. **Penemuan Dua Bug Arsitektur Kritis di Kode**:
   - **The `continue` Control Flow Starvation Bug (`market_scanner.py`)**:
     * Di dalam loop utama `for sym in symbols:`, cabang kegagalan filter pada M2 (baris 3745, 3870) dan M3 (baris 4054, 4060, 4073, 4079, 4085, 4259, 4264, 4278, 4284, 4290) mengeksekusi statement `continue`.
     * Hal ini menyebabkan jika sebuah simbol gagal pada filter M2 atau M3 (misal retest window atau DR guard), iterasi simbol tersebut langsung dihentikan dan **tidak pernah jatuh ke evaluasi M4 (Systemic Flow Continuation)** di baris 4401!
   - **M4 Mode B Basing Symbol Resolution Bug (`market_scanner.py`)**:
     * Pada helper `_m4_pending_ready`, pemanggilan `config.mt5.copy_rates_from_pos` menggunakan `sym_clean` (misal `"GBPNZD"` tanpa broker suffix `"-ECN"`), menyebabkan MT5 mengembalikan `None`.
     * Blok fallback memanggil `mt5_connector.get_closed_bars`, yang sebenarnya tidak ada di `mt5_connector` (`AttributeError`).
   - **Noise Veto pada Anti-Sweep SFP (`_detect_recent_sfp_absorption`)**:
     * Logika SFP memeriksa `nearest_psych = round(b_lo / sub_step) * sub_step` (kelipatan 25 pips) dengan syarat wick hanya 28%. Akibatnya, noise wicking candle intraday biasa pada level psikologis minor memicu SFP rejection palsu.

---

### Solusi Rekalibrasi & Pembenahan Arsitektur:
1. **Rekalibrasi Dealing Range Dual-Threshold M3 (`.env` & `config.py`)**:
   - Menggeser batas absolut ekstrem sejati:
     * `M3_MAX_DR_BUY` dinaikkan dari `0.60` ke `0.80` (hanya memblokir BUY di pucuk ekstrim $>80\%$).
     * `M3_MIN_DR_SELL` diturunkan dari `0.40` ke `0.20` (hanya memblokir SELL di dasar jurang ekstrim $<20\%$).
   - Menambahkan mekanisme syarat katalisator bersyarat di zona ekspansi:
     * `M3_CATALYST_DR_BUY_THRESHOLD = 0.60`: BUY dengan DR antara 60%–80% wajib didukung katalisator flow institusional (CSM Net Delta $\ge 1.0$ atau SFR Pro-Flow aktif).
     * `M3_CATALYST_DR_SELL_THRESHOLD = 0.40`: SELL dengan DR antara 20%–40% wajib didukung katalisator flow institusional (CSM Net Delta $\le -1.0$ atau SFR Pro-Flow aktif).
2. **Pelebaran Koridor M2 Pullback (`.env` & `config.py`)**:
   - `M2_MAX_DR_BUY` dinaikkan dari `0.55` ke `0.68` (hingga `0.75` jika didukung katalisator SFR/CSM).
   - `M2_MIN_DR_SELL` diturunkan dari `0.45` ke `0.32` (hingga `0.25` jika didukung katalisator SFR/CSM).
3. **Pembersihan Anti-Sweep SFP Veto (`market_scanner.py`)**:
   - Menghapus pemeriksaan `nearest_psych` (kelipatan 25 pips) sepenuhnya dari deteksi SFP. SFP kini murni hanya mengaudit level makro sejati institusional: $F_1, C_1, \text{PWL}, \text{PWH}, \text{PDL}, \text{PDH}$.
   - Menaikkan threshold rejection wick dari `0.28` (28%) menjadi `0.42` (42%) agar fluktuasi candle biasa tidak memicu false veto.
4. **Perbaikan Control Flow Fall-Through M4 (`market_scanner.py`)**:
   - Mengeliminasi seluruh statement `continue` abortif di cabang kegagalan validasi M2 dan M3.
   - Mengonversi evaluasi M3 menjadi branching bersih dengan flag `m3_buy_candidate_ok` dan `m3_sell_candidate_ok`.
   - Simbol yang tidak memenuhi kriteria retest atau filter M2/M3 kini secara mulus jatuh ke evaluasi M4 Systemic Flow Continuation.
5. **Perbaikan M4 Basing Broker Symbol Resolution (`market_scanner.py`)**:
   - Memastikan helper `_m4_pending_ready` memanggil `mt5_connector.get_valid_trade_symbol(sym_clean)` sehingga broker suffix (seperti `-ECN`) terpasang dengan benar.
   - Memperbaiki pengecekan rates MT5 dengan penanganan null yang aman.
6. **Penyelarasan Penuh `.env` dan `config.py`**:
   - Menyelaraskan seluruh variabel konfigurasi baru di kedua file sesuai Rule 2.

---

### Hasil Pengujian & Verifikasi:
1. **Unit Test Suite**:
   - `tests/test_m2_pullback_and_corridor.py`: **10/10 PASSED**.
   - `tests/test_m3_discount_guard_and_leapfrog.py`: **8/8 PASSED**.
   - `tests/test_sep8_enhancements.py`: **5/5 PASSED**.
   - `tests/test_m1b_sweep.py`: **5/5 PASSED**.
   - `tests/test_m4_flow_continuation.py`: **5/5 PASSED**.
   - `tests/test_basing_box_and_csm_bailout.py`: **7/7 PASSED**.
   - `tests/test_market_scanner.py`: **34/34 PASSED**.
   - `tests/test_symbol_rotation.py`, `test_macro.py`, `test_time_decay_and_vol_regime.py`: **8/8 PASSED**.
   - Total test terverifikasi: **100% PASS (Zero Failure, Zero Missing Imports)**.
2. **Verifikasi Live Radar MT5**:
   - Uji radar langsung pada akun live MT5 mendeteksi setup `AUDCAD-ECN TREND_ALIGNED_PULLBACK BUY @ 0.99601` dengan Dealing Range 63.2% dan Net RR 1.32R yang sebelumnya terblokir oleh guard kaku 55%.

---

## 0.0.0.0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Malam II) — Posisi Setup Grade Badges di CLI dan Standardisasi ANSI Box Direct Execution

### Latar Belakang & Identifikasi Masalah:
1. **Visibilitas Setup Grade pada Posisi Terbuka di CLI**:
   - Status bar posisi (`pos:`) di loop 3 detik `main.py` dan Tile 2 Bento HUD `cli_theme.py` sebelumnya hanya menampilkan simbol dan P/L (misal: `AUDUSD: +$14.47 [BEP]`).
   - Operator tidak dapat melihat secara langsung grade risiko/kualitas eksekusi (`GRADE_S`, `GRADE_A_PLUS`, `GRADE_A`, `GRADE_B`) tiap tiket yang sedang berjalan tanpa membaca file JSON state.
2. **Distorsi Tampilan Border Kotak Eksekusi Pure Quant**:
   - Blok alert terminal `[PURE QUANT DIRECT EXECUTION]` di `main.py` menggunakan format string dengan spasi manual hardcoded (`╔══...══╗`, `║ ... ║`).
   - Ketika nama simbol, nilai harga, angka SL/TP, atau label fill berubah panjang karakternya, border kanan kotak bergeser dan berantakan.

---

### Komponen & Solusi Utama:
1. **Integrasi Helper Grade Tiket (`src/analytics/position_manager.py`)**:
   - Menambahkan fungsi helper `get_ticket_setup_grade(ticket: int) -> str` untuk mengambil status grade tiket dari state tersimpan `_ticket_setup_grades`.
2. **Display Setup Grade Badges di CLI (`main.py` & `src/core/cli_theme.py`)**:
   - Menambahkan badge warna grade setup langsung di samping nama pair pada baris `pos:` dan Bento HUD Tile 2:
     * `[S]` (Bold Hijau `#22c55e`): `GRADE_S` (Macro Expansion Runner).
     * `[A+]` (Hijau `#10b981`): `GRADE_A_PLUS` / `GRADE_A+`.
     * `[A]` (Cyan `#06b6d4`): `GRADE_A` (Standard Intraday).
     * `[B]` (Kuning `#eab308`): `GRADE_B` (Wall Scalp).
   - Format tampilan: `pos: AUDUSD[S]: +$14.47 [BEP] | AUDCHF[B]: +$5.20 [TRAIL]`.
3. **Standardisasi Kotak Eksekusi dengan `UI.make_box` (`main.py`)**:
   - Mengganti border hardcoded manual dengan `UI.make_box()` (`width=76`, `border_color=UI.CYAN`).
   - Menghitung visual display width secara dinamis dan ANSI-safe sehingga border kotak selalu presisi dan simetris di seluruh platform terminal.

---

## 0.0.0.0.0.0.0.0.0.0. Audit & Riset 8 September 2026 (Sore–Malam) — Asimetri Aliran London, CSM Opposed Bypass, dan Cacat Self-Hedging / Kanibalisasi Internal Keranjang Mata Uang

### Latar Belakang & Hasil Audit Akun (Sesi London):
1. **Asimetri & Kanibalisasi Posisi CAD (Internal Self-Hedging)**:
   - Pada sesi London (pukul 15:45 WIB), akun membuka 6 posisi di mana terjadi konflik arah mata uang yang saling meniadakan (*self-hedging*):
     * `USDCAD-ECN` SELL ($0.84\text{ lot}$) dan `EURCAD-ECN` SELL ($1.29\text{ lot}$) mengakumulasi eksposur **$+2.13\text{ lot}$ LONG CAD**.
     * Secara simultan, radar mengeksekusi `AUDCAD-ECN` BUY ($2.03\text{ lot}$) yang setara dengan **$-2.03\text{ lot}$ SHORT CAD**.
     * Hasil agregasi: Net eksposur CAD portofolio tergerus menjadi $+0.10\text{ lot}$ (kanibalisasi $95\%$). Di saat CAD menjadi mata uang terkuat kedua di pasar ($+28.32$ Boitoki CSM H1), reli CAD di USDCAD & EURCAD terhapus oleh kerugian di AUDCAD, membebani akun dengan biaya dobel komisi dan spread.
2. **Celah Logika Bypass CSM oleh Stale Macro Bias di Radar (`market_scanner.py`)**:
   - Di `market_scanner.py` fungsi `_is_direction_allowed()`, aturan pengecekan CSM berbunyi:
     `if is_csm_opposed and not is_aligned and not is_sfr_pro:`
   - Ketika Macro Bias D1/H4 bernilai $\ge +0.35$ (`is_aligned = True`), filter `is_csm_opposed` **di-bypass 100%**.
   - Macro Bias bersifat *lagging* (mengikuti struktur multi-hari), sedangkan Boitoki CSM merefleksikan pergeseran likuiditas riil harian/intraday. Akibatnya, sinyal BUY AUDCAD tetap lolos ke Stage 2 kendati CSM Delta AUDCAD berada di level ekstrem $-3.02$ (AUD lemah vs CAD melonjak).
3. **Pending Order CSM Invalidation Tidak Aktif**:
   - Pada `position_manager.py`, parameter `ENABLE_PENDING_CSM_CANCEL` default-nya bernilai `False` dan belum dideklarasikan di `.env`.
   - Hal ini menyebabkan pending limit order (seperti BUY_LIMIT AUDCAD) yang dipasang sebelum rotasi mata uang tidak pernah dibatalkan secara otomatis saat arus CSM berbalik menentang arah order saat terjemput.
4. **Perbedaan Karakter Sesi Asia vs London**:
   - Pada Sesi Asia (07:00–14:00 WIB), universe dibatasi hanya untuk pair Pasifik/Asia (AUD, NZD, JPY) dengan penggerak tunggal yang bersih (contoh: dump ekstrem NZD $-62.27$ menghasilkan profit bersih pada `EURNZD` BUY dan `NZDCHF` SELL).
   - Saat seluruh 26 pair dibuka serentak pada Sesi London (14:00 WIB), ketiadaan *Cross-Pair Portfolio Currency Guard* menyebabkan radar memindai tiap pair secara terisolasi tanpa kesadaran atas akumulasi eksposur mata uang keranjang.

---

### Desain Arsitektur Solusi (Rencana Implementasi):
1. **Portfolio Currency Basket Anti-Cannibalization Guard (`market_scanner.py`)**:
   - Menambahkan audit eksposur portofolio riil sebelum tiket order diizinkan: jika akun telah memiliki eksposur netto dominan ($\ge 1.0\text{ lot}$) pada mata uang dasar/kutipan tertentu (misal Long CAD), radar memblokir keras order baru yang menjual mata uang tersebut (Short CAD) guna mencegah kanibalisasi internal.
2. **Strict CSM Precedence pada Setup Continuation (`market_scanner.py`)**:
   - Menghapus celah `not is_aligned` untuk setup continuation (M2, M3, M4): jika CSM Net Delta menentang keras ($|\Delta| \ge 1.50$), order mutlak di-`HARD_BLOCK` tanpa kompromi dari Macro Bias D1 yang basi.
   - Pengecualian hanya diberikan untuk setup M1 Universal Liquidity Sweep / SFP murni di batas Dealing Range ekstrem ($\le 0.15$ atau $\ge 0.85$) untuk scalp pantulan cepat ke TP1.
3. **Aktivasi Pending Order Thesis Invalidation di `.env`**:
   - Menambahkan `ENABLE_PENDING_CSM_CANCEL=true` ke `.env` dan `config.py` sehingga pending limit order yang arusnya berbalik secara sistemik langsung dibatalkan sebelum terisi secara merugikan.
4. **Kebijakan Testing Akun Demo**:
   - Seluruh posisi dan pending order aktif di akun DEMO tetap dibiarkan berjalan normal untuk memperkaya sampel data observasi kuantitatif sebelum patch dieksekusi ke produksi live.

---

## 0.0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Malam) — Dynamic ZCE + SMC Structural Anchor, Transisi SL Floor 80 Pts Quiet FX, dan Propagasi ATR Riil M4

### Latar Belakang & Identifikasi Masalah:
1. **SL Floor Statis 120 Pts Menimpa Invalidation Level Alami pada Quiet FX**:
   - Nilai konfigurasi `SL_FLOOR_QUIET_FX_PTS = 120` (12 pips) di `.env` dan `config.py` memaksa Stop Loss menjadi terlalu lebar ($1.46\times\text{ATR}$) pada pair dengan volatilitas tenang seperti AUDCAD (ATR H1 82 pts) dan EURCHF (ATR H1 70 pts).
   - Pada setup AUDCAD-ECN BUY M4, radar mendeteksi invalidasi struktural High-Tight Basing di `0.99417` (58 pts dari entry `0.99475`) dengan ZCE Floor $F_1$ di `0.99382` (93 pts dari entry). Namun `_apply_sltp_rules` di `consensus.py` memaksakan penyesuaian SL ke 120 pts (`0.99355`) dan TP ke 155 pts karena helper `config.get_sl_floor_points()` dipanggil dengan `spread_pts=0, atr_points=0`.
2. **Ketiadaan Integrasi Dinding ZCE $F_1/C_1$ pada Engine SL Intraday (`atlas_dna.py`)**:
   - Fungsi `calculate_intraday_sl_tp` hanya memeriksa `origin_level` dan `rbs`/`sbr` untuk pemilihan `sl_anchor`. Dinding institusional ZCE $F_1$ (untuk BUY) dan $C_1$ (untuk SELL) tidak dimanfaatkan sebagai invalidation floor/ceiling, melainkan langsung jatuh ke fallback ATR acak dengan penambahan buffer statis 120 pts.

---

### Komponen & Solusi Utama:
1. **Transisi Parameter SL Floor Quiet FX ke 80 Pts (`.env` & `config.py`)**:
   - Mengubah `SL_FLOOR_QUIET_FX_PTS` dari `120` menjadi `80` (8 pips).
   - `config.get_sl_floor_points(sym, spread_pts, atr_points)`:
     * Quiet FX: `max(spread_pts * 2 + 15, int(0.50 * atr_points) if atr_points > 0 else 80, 80)`.
     * Menjaga SL tetap bernapas proporsional pada pair ber-ATR rendah tanpa membuka risiko lot berlebih. High-Beta tetap 180 pts dan JPY tetap 250 pts (+20 pts NZD padding).
2. **Dynamic Structural ZCE $F_1/C_1$ Anchoring (`src/indicators/atlas_dna.py`)**:
   - BUY: Mengintegrasikan ZCE $F_1$ ke dalam hierarki `sl_anchor` jika `origin_level` tidak ada atau berada di atas entry. SL di-anchor di belakang $F_1$ dengan bantalan anti-wick `wall_cushion = max(15 pts, 0.15 ATR) + spread`.
   - SELL: Mengintegrasikan ZCE $C_1$ ke dalam hierarki `sl_anchor` jika `origin_level` tidak ada atau berada di bawah entry. SL di-anchor di belakang $C_1$ dengan `wall_cushion`.
   - Total jarak SL wajib memenuhi safety floor: $\ge 80\text{ pts}$ (Quiet FX), $\ge 180\text{ pts}$ (High-Beta), $\ge 250\text{ pts}$ (JPY), $+20\text{ pts}$ (NZD), dan dibatasi plafon `max(2.5 * atr_h1, min_sl_floor)`.
3. **Propagasi Spread & ATR Riil M4 ke Consensus (`src/core/consensus.py`)**:
   - Memperbaiki pemanggilan `config.get_sl_floor_points()` pada validasi M4 di baris 139 dengan meneruskan data riil kandidat: `cand_spread = candidate.current_spread_pts` dan `cand_atr = candidate.current_atr_pts`.
   - Mencegah fallback default `atr_points=0` yang memicu pemaksaan floor statis.
4. **ZCE Wall Anchoring pada Radar M4 (`src/analytics/market_scanner.py`)**:
   - Pada pembentukan tiket M4 di radar, jika terdapat dinding ZCE $F_1$ (BUY) atau $C_1$ (SELL) dalam jangkauan $1.5\times\text{ATR}$, SL di-anchor di belakang dinding tersebut dengan bantalan 15 pts + spread, dan di-clamp ke safety floor 80 pts sebelum diteruskan ke consensus.
5. **Verifikasi Test Suite**:
   - Menambahkan unit test suite baru `tests/test_zce_sltp_anchor.py` (4/4 PASS).
   - Menyelaraskan `tests/test_fresh_breakout_and_net_rr.py` ke floor 80 pts (EURCHF).
   - Seluruh test suite: **220/220 PASSED (100%)** dalam 58.91s.

---

## 0.0.0.0.0.0.0.0. Perubahan 8 September 2026 (Petang) — M3 Hard Dealing Range Guard, Anti-Sweep SFP Absorption Veto, Rigid Breached Wall Law, dan Audit Eksekusi GBPNZD M2

### Latar Belakang & Identifikasi Masalah:
1. **USDCAD-ECN SELL di Kedalaman Discount (13.5% Dealing Range)**:
   - Evaluasi radar M3 breakdown pada `market_scanner.py` memiliki celah logika pada filter runway: `(not has_downward_runway and dr_pos < 0.30)`. Karena runway ke bawah terbuka, syarat batas discount di-bypass sehingga bot mengeksekusi SELL tepat setelah harga melakukan sapuan likuiditas (sweep) 74.6% lower wick di bawah level psikologis `1.37800` dan F1 `1.37781`.
2. **NZDCHF-ECN Target Leapfrog Melompati Dinding Tebal F1/F2**:
   - Di `atlas_dna.py` fungsi `calculate_intraday_sl_tp()`, kondisi `elif (f1_breached or not f1_thick or not f1_valid) and f2:` mengevaluasi `not f1_valid = True` saat jarak ke F1 $< 0.75R$. Akibatnya, target melompati dinding F1 institusional (`GRADE_3_MACRO`) yang belum tertembus dan menetapkan TP di `0.47145` (28.5 pips) alih-alih tertahan di F1 (`0.47321`).
3. **GBPNZD-ECN BUY di Premium (66.6% Dealing Range) Jauh di Atas EMA**:
   - M2 Pullback mentoleransi range hingga `max_dr_buy = 0.80` saat ada katalisator SFR BULLISH_FLOW dan mengambil micro-FVG di `2.31387` sebagai anchor pullback terdekat, mengabaikan fakta bahwa harga berada jauh di atas EMA 20 (`2.3083`) dan EMA 50 (`2.3045`).

---

### Komponen & Solusi Utama:
1. **Hard Dealing Range Veto pada M3 (`src/analytics/market_scanner.py`)**:
   - M3 SELL: Wajib `dr_pos >= 0.40` (`M3_MIN_DR_SELL = 0.40`). Dilarang keras sell di area Discount.
   - M3 BUY: Wajib `dr_pos <= 0.60` (`M3_MAX_DR_BUY = 0.60`). Dilarang keras buy di area Premium.
   - Logika veto dipisahkan menjadi guard independen: `is_wall_collision_s or is_discount_sell_blocked or (not has_downward_runway)`.
2. **Anti-Sweep SFP Absorption Veto pada M3 (`src/analytics/market_scanner.py`)**:
   - Mengimplementasikan `_detect_recent_sfp_absorption()`: Jika dalam 4 bar H1 terakhir harga menyapu di bawah floor/psych level (SELL) atau di atas ceiling/psych level (BUY) dengan rejection wick $\ge 28\%$ (`M3_SFP_REJECTION_WICK = 0.28`) dan ditutup kembali ke dalam zona, sinyal M3 otomatis dibatalkan karena struktur berada dalam fase absorbsi likuiditas/rebound.
3. **Rigid Breached Wall Law (`src/indicators/atlas_dna.py`)**:
   - Menghapus syarat `not f1_valid` / `not c1_valid` dari pemicu lompatan target ke F2/C2.
   - Dinding tebal (`GRADE_2_INTERMEDIATE`, `GRADE_3_MACRO`) mutlak mengunci target di F1/C1 kecuali jika sudah ada konfirmasi fisik penutupan candle di luar batas distal (`breached == True`). Jika jarak $< 0.75R$, setup ditolak bersih oleh Runway Gate tanpa melompat liar.
4. **M2 Pullback Quarantine & EMA Corridor Confluence (`src/analytics/market_scanner.py`)**:
   - `M2_MAX_DR_BUY = 0.55`: Memblokir keras M2 BUY di area Premium (`dr_pos > 0.55`). Menghapus pelonggaran batas 0.80.
   - `M2_MIN_DR_SELL = 0.45`: Memblokir keras M2 SELL di area Discount (`dr_pos < 0.45`). Menghapus pelonggaran batas 0.20.
   - Menghapus bypass `and not has_m4_retest_b` / `and not has_m4_retest_s` dari guard koridor EMA M2 sehingga M2 wajib berada di koridor EMA yang sehat tanpa celah.
   - `find_ema_confluence_anchor()`: Menyaring seluruh kandidat struktural (OB, FVG, Psych) agar wajib berada dalam jarak $\le 0.35\times\text{ATR}$ dari koridor EMA 20/50 (`M2_EMA_CORRIDOR_TOLERANCE_ATR = 0.35`). Mengeliminasi anchor palsu pada micro-FVG yang melayang puluhan pips di atas EMA.
5. **Sinkronisasi Parameter `.env` & `config.py`**:
   - M3: `M3_MIN_DR_SELL=0.40`, `M3_MAX_DR_BUY=0.60`, `M3_SFP_REJECTION_WICK=0.28`, `M3_SFP_LOOKBACK_BARS=4`.
   - M2: `M2_MAX_DR_BUY=0.55`, `M2_MIN_DR_SELL=0.45`, `M2_EMA_CORRIDOR_TOLERANCE_ATR=0.35`.
6. **Verifikasi Test Suite**:
   - Menambahkan 9 unit test baru di `tests/test_m3_discount_guard_and_leapfrog.py` (9/9 PASS).
   - Menambahkan 5 unit test baru di `tests/test_m2_pullback_and_corridor.py` (5/5 PASS).
   - Memperbaiki isolasi tiket mock di `tests/test_basing_box_and_csm_bailout.py` dan status breach di `tests/test_m4_flow_continuation.py`.
   - Full test suite: **223/223 PASSED (100%)** dalam 37.49s.

---

## 0.0.0.0.0.0.0. Perubahan 8 September 2026 (Sore III) — Tri-State Differentiation M4 SFR Fresh Shock (|z| >= 1.50) vs Flow Continuation (0.75 <= |z| < 1.50)

### Latar Belakang & Identifikasi Masalah:
1. **Kerancuan Tampilan Status Shock saat Z-Score Melandai ($z = -1.10$)**:
   - Engine M4 memiliki dua ambang batas: `M4_TRIGGER_Z = 1.50` (memicu episode baru saat fresh shock) dan `M4_CONT_Z = 0.75` (mempertahankan episode hidup selama $|z| \ge 0.75$).
   - Di `dashboard.py`, kondisi `m4_has_shock` sebelumnya mencampur aduk antara adanya standby order aktif dengan fresh shock murni (`m4_active_standby is not None`).
   - Akibatnya, saat Z-score melandai (*decay*) ke $-1.10$, dashboard tetap merender badge kuning emas `⚡ SFR | z: -1.1` dan hero banner `SFR ACTIVE`, memberi kesan seolah-olah terjadi shock baru padahal nilai $z$ sudah di bawah $1.50$.

---

### Komponen & Solusi Utama:
1. **Klasifikasi Tri-State Kuantitatif (`dashboard.py`)**:
   - Menghitung `m4_flow_state` di `_build_overview_cache()` dan `get_symbol_detail()`:
     * **`SHOCK` (Kuning Emas `#facc15`)**: Hanya aktif jika $|z_{\text{base}}| \ge 1.50$ atau $|z_{\text{quote}}| \ge 1.50$ (*Fresh Institutional Shock*).
     * **`CONT` (Cyan / Biru `#38bdf8`)**: Aktif saat tidak ada fresh shock, namun episode M4 masih berjalan di scanner (`ep is not None` atau ada pending order) dengan $|z_{\text{dominant}}| \ge 0.75$.
     * **`NONE`**: Jika $|z| < 0.75$ atau tidak ada episode aktif.
   - Menghapus pengecekan usang `m4_st.get("bear", ...)` dan menyelaraskan dengan state machine riil `m4_st["SELL"]` & `m4_st["BUY"]`.
2. **Diferensiasi Visual Cockpit (`dashboard_assets.py`)**:
   - **CSS**: Menambahkan styling `.pair-row.m4-cont-row` dan `.m4-cont-pill` dengan aksen cyan `#38bdf8`.
   - **Watchlist Sidebar**:
     * `SHOCK` ($|z| \ge 1.50$): Border kuning emas + badge `⚡ SFR SHOCK | z: +/-X.X`.
     * `CONT` ($0.75 \le |z| < 1.50$): Border cyan + badge `trending_flat FLOW CONT | z: +/-X.X`.
     * `NONE`: Baris standar tanpa penanda.
   - **Hero Banner Chart**:
     * `SHOCK`: Emas `SYSTEMIC FLOW SHOCK (SFR) ACTIVE`.
     * `CONT`: Cyan `SYSTEMIC FLOW CONTINUATION`.
3. **Verifikasi Kuantitatif Live MT5 Data**:
   - **12 SHOCK Pairs ($|z| \ge 1.50$)**: `EURJPY` (-1.63), `EURNZD` (+2.06), `GBPJPY` (-1.63), `GBPNZD` (+2.06), `AUDJPY` (-1.63), `AUDNZD` (+2.06), `USDJPY` (-1.63), `CHFJPY` (-1.63), `CADJPY` (-1.63), `NZDUSD` (-2.06), `NZDCAD` (-2.06), `NZDCHF` (-2.06).
   - **7 CONT Pairs ($0.75 \le |z| < 1.50$)**: `EURUSD` (-1.10), `EURAUD` (-1.10), `EURCAD` (-1.10), `EURCHF` (-1.10), `EURGBP` (-1.10), `GBPCAD` (-0.92), `AUDCAD` (-0.92).
   - **8 NONE Pairs**: `GBPUSD`, `GBPAUD`, `GBPCHF`, `AUDUSD`, `AUDCHF`, `USDCAD`, `USDCHF`, `BTCUSD`.
4. **Verifikasi Test Suite**:
   - Full test suite: **209/209 PASSED (100%)** dalam 41.82s.

---

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

5. **Matriks Interaksi 2-Dimensi (Geometri Runway ZCE vs Konfluensi Makro MSE)**:
   - Evaluasi operasional saat status geometri bertemu dengan tier makro:

| Parameter Eksekusi | Grade A+ (Reduced Confidence) | Grade B (Reduced Confidence) | Grade A (Full Allow) |
|---|---|---|---|
| **Dimensi Geometri (ZCE)** | Runway lapang $\ge 1.80R$ ($2.34R$) | Runway sempit pantulan dinding ($0.75R - 1.25R$) | Runway standar menuju $C_1/F_1$ ($1.25R - 1.80R$) |
| **Dimensi Makro (MSE)** | Tren moderat (`REDUCED_CONFIDENCE`) | Tren moderat (`REDUCED_CONFIDENCE`) | Tren searah ekspansif (`FULL_ALLOW`) |
| **Lot Multiplier** | **$0.75\times$** (Defensive Single-Layer) | **$0.75\times$** (Defensive Single-Layer) | **$1.00\times$** (Full Base Lot) |
| **Struktur Tiket** | 1 atau 2 tiket (jika Unanimous $\ge 80\%$) | **Wajib 1 Tiket Murni** (Split Dilarang) | 1 atau 2 tiket (jika Unanimous $\ge 80\%$) |
| **Plafon Target TP** | **Dipangkas ke $\le 2.00R$** (MSE Cap) | **Terkunci di $0.75R - 1.25R$** | Standar $1.25R - 1.80R$ |
| **Partial Close** | Aktif 50% di 50% TP | **Bypass 100%** | Aktif 50% di 50% TP |
| **Trigger BEP** | **Dipercepat ke 35% TP** | **Dipercepat ke 35% TP** | 50% TP |
| **Stagnation Exit** | 4 jam jika MFE $< 0.30R$ | 4 jam jika MFE $< 0.30R$ | 4 jam jika MFE $< 0.30R$ |

6. **Verifikasi Kuantitatif Penuh**:
   - Unit test suite: `tests/test_sep8_enhancements.py` mencakup test spesifik `test_risk_engine_defensive_grade_b_with_neutral_multiplier`.
   - Seluruh test suite unit test: **199/199 tests PASSED (100% OK)**.

---

## 99. 11 September 2026 — Systemic Flow Shock (SFR) Z-Score Threshold Elevation to 2.0 Sigma & Multiplier Shield

### 🎯 Rasional Kuantitatif & Problem Statement:
- **Diagnosa Masalah**: Ambang batas Z-score untuk Layer 0 Systemic Flow Regime (SFR) Shock sebelumnya ditetapkan pada $|z| \ge 1.50$. Dalam distribusi normal kurva $Z$, $|Z| \ge 1.50$ merepresentasikan peluang ekor $13.36\%$. Pada universe 26 simbol FX yang tersusun dari 8 keranjang mata uang (di mana 1 mata uang menyusun 6-7 pair), kehadiran 2 mata uang saja dengan $|z| \ge 1.50$ (misalnya AUD $z = -2.27$ dan USD $z = +1.75$) memicu *Basket Multiplier Effect* yang menyebabkan 13 dari 26 pair (50% dashboard) langsung berstatus `⚡ SFR SHOCK`, memicu *alarm fatigue* dan mengaburkan perbedaan antara guncangan anomali ekstrim sejati vs momentum ekspansi teratur.
- **Penyelarasan Kuantitatif ke $2.0\sigma$ ($|Z| \ge 2.00$)**:
  - Ambang batas trigger shock dinaikkan ke $2.00$ ($2\sigma$, peluang ekor ekstrim $4.5\%$).
  - Pasangan mata uang dengan $1.50 \le |z| < 2.00$ (seperti USD) diklasifikasikan dengan benar sebagai `FLOW CONT` (biru langit).
  - Status `⚡ SFR SHOCK` (kuning emas) dikhususkan hanya untuk anomali ekstrim sejati (seperti AUD $z = -2.27$), memangkas alarm visual dashboard dari 13 pair (50%) menjadi hanya 7 pair konstituen AUD (27%).

### 🛠️ File yang Diselaraskan:
1. `.env`: Menambahkan konfigurasi eksplisit `M4_TRIGGER_Z=2.0` dan `M4_CONT_Z=0.75`.
2. `config.py`: Memperbarui default fallback `M4_TRIGGER_Z = _getenv_float("M4_TRIGGER_Z", 2.0)`.
3. `dashboard.py`: Menghapus hardcoded `1.50` di baris 785 dan 1395, diselaraskan menggunakan `float(getattr(config, "M4_TRIGGER_Z", 2.0))`.
4. `dashboard_assets.py`: Menyelaraskan tooltip dan label UI dari `(|z| >= 1.50)` / `(Req >=1.5)` menjadi `(|z| >= 2.00)` dan `(Req >=2.0)`.

---

## 100. 11 September 2026 — Rekonsiliasi Kuantitatif: Tesis Chamber vs Data Telemetri Empiris
- **Temuan Kuantitatif Kohort (DeepSeek Review)**:
  - M2 Anchor Boundary vs Mid-Chamber: $N=96$ vs $78$, median return $+0.73R$ vs $+0.71R$, $p=0.039$ (permutasi), namun hard-SL identik ($21.9\%$ vs $24.4\%$, $p=0.699$).
  - Perbedaan return disebabkan oleh run-up (+1.88R), bukan kebocoran catastropic mid-chamber.
  - Tesis "kebocoran mid-chamber parah" ditolak secara kuantitatif. Solusi data-driven diadopsi: Soft-gate M2 pada benteng G1 Micro ke `GRADE_B` alih-alih hard block.
- **Audit Logging ZCE (`main.py`)**:
  - Memperbaiki pencetakan log `[ZCE-AUDIT]`: `ZCE_F1` dan `ZCE_C1` kini membaca level zona ZCE riil dari metadata kandidat alih-alih nilai Stop Loss.
- **Persistensi Telemetri Tingkat Dinding (`shadow_tracker.py` & `position_manager.py`)**:
  - Menambahkan persistensi field `wall_grade`, `f1_reaction_grade`, `c1_reaction_grade`, `zce_f1`, dan `zce_c1` ke dalam database `quant_shadow_trades.jsonl` dan `trade_lifecycle_telemetry.json` untuk pengujian counterfactual bersih di masa mendatang.

---

## 101. 11 September 2026 — Ekstraksi Modular M2 Wall Quality, Lazy M5 Micro-Rejection, & Optimasi Startup MT5
- **Ekstraksi Produksi Murni `_evaluate_m2_wall_quality` (`market_scanner.py`)**:
  - Memindahkan logika evaluasi kualitas dinding, anti-marubozu waterfall guard, dan G1 soft-gate dari inline block M2 BUY / M2 SELL ke method produksi mandiri `_evaluate_m2_wall_quality`.
  - Mengintegrasikan pengecekan lazy M5: `_verify_m5_rejection_wick` hanya dipanggil jika H1 belum memiliki konfirmasi rejection wick yang memadai, memangkas ~85% panggilan MT5 rate copy pada loop radar.
- **Konfigurasi Threshold Anti-Hardcode (`config.py` & `.env`)**:
  - `ENABLE_M2_WALL_QUALITY=true`
  - `M2_MARUBOZU_BODY_RATIO=0.55`
  - `M2_MARUBOZU_MAX_WICK_RATIO=0.20`
  - `M2_G1_MIN_WICK_RATIO=0.25`
  - `M2_G1_PROXIMITY_ATR=0.35`
  - Menghapus entri usang `ZCE_GRADE_G2=3.5` / `ZCE_GRADE_G3=6.5` dan duplikat `M4_TRIGGER_Z=1.5` di `.env`.
- **Optimasi Latensi Booting MT5 (`mt5_connector.py` & `main.py`)**:
  - `init_mt5`: Memeriksa akun aktif terminal desktop sebelum memanggil `mt5.login()`. Jika sudah terhubung ke akun live yang sama, handshake redundan dilewati (memangkas waktu inisialisasi dari 15-20 detik menjadi 3.5 detik).
  - `main.py`: Menambahkan pesan progres `[RADAR BOOT] Memuat konteks makro 26 simbol universe (H1/H4/D1/W1)... Mohon tunggu ~25 detik` agar terminal tidak terkesan membeku saat inisialisasi awal.
- **Validasi Unit Test Suite**:
  - `tests/test_m2_wall_quality_and_exhaustion.py`: 6/6 tests PASSED secara langsung memanggil method produksi.
  - Seluruh suite unit test terverifikasi 100% PASS.

---

## 102. 11 September 2026 — Implementasi Penuh BEP 35% Grade B, Idempotensi Resolver, & Standardisasi Telemetri
- **Implementasi Nyata BEP 35% TP Grade B (`position_manager.py` & `shadow_tracker.py`)**:
  - `position_manager.py`: Memperbaiki jalur `tp_points > 0` dengan menambahkan cabang `elif "GRADE_B" in grade or "REDUCED" in grade or is_vacuum_or_stretched:` untuk mengaktifkan BEP di **35% TP** (`GRADE_B_BREAK_EVEN_TRIGGER_TP_PCT=0.35`).
  - `shadow_tracker.py`: Menyelaraskan evaluasi virtual BEP BUY/SELL agar membaca `setup_grade` atau `action_tier`, memicu BEP di 35% TP untuk Grade B alih-alih tertahan di 60% TP.
  - `config.py` & `.env`: Menambahkan parameter resmi `GRADE_B_BREAK_EVEN_TRIGGER_TP_PCT=0.35`.
- **Idempotensi `_record_resolved` (`shadow_tracker.py`)**:
  - Menambahkan set `self._resolved_ids` guna mencegah *double-counting* statistik in-memory jika terjadi trigger resolusi berulang pada order yang sama.
- **Koreksi Label Disposisi MT5 & Preservasi Outcome (`shadow_tracker.py`)**:
  - Tiket MT5 yang tertutup oleh TP/SL kini dicatat secara akurat sebagai `EXECUTED_MT5_RESOLVED` (bukan ditimpa `SKIPPED_EXPIRED`).
  - Klasifikasi outcome `TRAILING_SL_HIT` vs `BEP_HIT` disempurnakan dengan syarat `realized_r >= 0.20` untuk trailing dan range `[-0.05R, +0.20R]` untuk BEP guna mencegah distorsi statistik retroaktif.
- **Dokumentasi Git Resmi**:
  - Dibuat [`docs/WALKTHROUGH_SEPTEMBER_2026.md`](file:///c:/Vibe/tradingpartner/docs/WALKTHROUGH_SEPTEMBER_2026.md) langsung di root repository sehingga terlacak penuh dalam `git status`.
- **Hasil Pengujian**:
  - `tests/test_shadow_tracker.py`: 13/13 tests PASSED (termasuk verifikasi BEP 35% Grade B dan idempotensi).
  - `tests/test_time_decay_and_vol_regime.py`: 8/8 tests PASSED (termasuk verifikasi BEP 35% Grade B live MT5).
  - Suite lengkap 5 file: 31/31 tests PASSED (100% OK).

---

## 103. 11 September 2026 — Eliminasi Inversi Palsu MSE pada Uji Lantai/Plafon HTF, Penyelarasan CSM Sebagai Directional Tailwind, & Pembukaan M3 NY Live
- **Eliminasi Inversi Palsu di Uji Lantai & Plafon (`macro_strategic_engine.py`)**:
  - **Diagnosa Masalah (Kasus EURJPY BUY vs GBPJPY SELL)**: Ketika harga menguji lantai $F_1$ dalam tren D1/H4 Bearish, jika jarak ke $F_2$ sempit ($< 35\text{ pips}$ pada JPY), kode jatuh ke blok `else` yang membalikkan bias secara keliru menjadi `BULLISH_PULLBACK` (+0.85) dan memasang trap `Do NOT short into confirmed RBS support`.
  - **Perbaikan Kode**:
    * Uji Lantai ($F_1$): Jika tren HTF Bearish (`is_h4_bear or last_d1_bear`), status diatur ke `BEARISH_EXPANSION` (-0.65) jika runway terbuka, atau `RANGE_BOUND` / `WAIT_BREAKDOWN_OR_ROTATION` (-0.35) jika runway sempit. Dilarang membalikkan bias menjadi Bullish BUY atau memasang trap larangan short.
    * Uji Plafon ($C_1$): Symmetrically, jika tren HTF Bullish (`is_h4_bull or last_d1_bull`), status diatur ke `BULLISH_EXPANSION` (+0.65) jika runway terbuka, atau `RANGE_BOUND` / `WAIT_BREAKOUT_OR_ROTATION` (+0.35) jika runway sempit. Dilarang membalikkan bias menjadi Bearish SELL atau memasang trap larangan buy.
- **Penyelarasan CSM Delta Sebagai Directional Tailwind Murni (`market_scanner.py`, `config.py`, `.env`)**:
  - `ENABLE_CSM_FLOW_FILTER = false` dipertahankan: CSM Delta tidak pernah menjadi Hard Gate yang memblokir trade.
  - Sesuai prinsip kuantitatif: Struktur Makro HTF adalah jangkar primer, CSM Delta bertindak sebagai penguat probabilitas dan penentu bobot kandidat intra-simbol (`1.5 * micro_score`).
  - Target jauh TP $\ge 2.50\times\text{ATR}$ (`_apply_conditional_far_target`) tetap tunduk pada rezim struktural (Tokyo session + $|\Delta| \ge 2.00$ atau konfirmasi penembusan fisik dinding).
- **Pemulihan M3 Breakout Retest NY ke Live MT5 & Nonaktifkan Filter Sesi Restriktif**:
  - `ENABLE_NY_M3_PAPER_ROUTE = false` (M3 NY kembali dieksekusi langsung ke live MT5).
  - `ENABLE_LDN_DEFENSIVE_WINDOW = false` (Larangan sell limit awal London dinonaktifkan).
  - `ENABLE_TOKYO_LULL_FREEZE = false` (Pembekuan Tokyo midday dinonaktifkan).
- **Hasil Verifikasi Kuantitatif Lengkap**:
  - Simulasi spesifik EURJPY narrow runway: terbukti lolos tanpa inversi palsu (`daily_macro_bias: RANGE_BOUND`, score `-0.35`, forbidden traps kosong).
  - Full Unit Test Suite: **265/265 tests PASSED (100% OK, 0 Error, 0 Failure)**.

---

## 104. 11 September 2026 (Malam III) — Pembangunan Macro Dynamic Envelope & Pattern Recognition Engine (Decoupled Dual-Track)
- **Pembersihan Modul Usang**:
  - Menghapus modul usang micro-whisper `src/analytics/pattern_detector.py` dan database lama `src/analytics/whisper_registry.json`.
- **Pembangunan Engine Kuantitatif Mandiri `src/analytics/pattern_engine.py`**:
  - **Arsitektur Decoupled Dual-Track**:
    * **Track A (Causal Decision Engine — 100% Anti-Repaint)**: Menggunakan konfirmasi pivot kausal $N=3$ bar H4 (bar $t \in [97, 99]$ dilabeli `PROVISIONAL_PENDING`). Memetakan tren struktural ($\text{HH/HL}$ Bullish Expansion, $\text{LH/LL}$ Bearish Expansion, $\text{LH/HL}$ Compression, $\text{HH/LL}$ Broadening).
    * **Wick-to-Body Rejection & Absorption Density Matrix**: Menghitung ketebalan ekor relatif $\rho_{\text{reject}}$ dan $\rho_{\text{absorb}}$ ternormalisasi ATR. Akumulasi 10-bar menghasilkan `net_wick_delta` sebagai sinyal aktif tekanan likuiditas institusional.
    * **Pembersihan Outlier & Rollover Clamping**: Algoritma MAD & ATR-relative winsorizing untuk membuang lonjakan spread spike palsu pada jendela rollover (03:55–04:15 WIB), khususnya pada pair CHF.
    * **Track B (Visual Manifold Ribbon)**: Rolling extremum filter ($U_{\text{raw}}, L_{\text{raw}}$ window 3) dihaluskan menggunakan polinomial Savitzky-Golay analitis murni di NumPy (0 dependency ke scipy, eksekusi $< 4\text{ ms}$). Menghasilkan koordinat kurva halus $U(t)$ dan $L(t)$ serta batas pita ekor $U_{\text{wick}}(t)$ dan $L_{\text{wick}}(t)$.
- **Integrasi ke Macro Strategic Engine & Zone Confluence Engine**:
  - `macro_strategic_engine.py`: Mengintegrasikan `MacroEnvelopeResult` di `compute_directive`, menyalurkan data envelope ke `MacroStrategicDirective`, dan mengekspos payload visual di `raw_payload`.
  - `zone_confluence_engine.py`: Mengoleksi zona batas atas `ENVELOPE_CEIL` dan zona batas bawah `ENVELOPE_FLOOR` pada timeframe H4 ke dalam matriks konfluensi ZCE dengan bobot 0.35.
- **Porting Visual ke Dashboard Cockpit (`dashboard.py` & `dashboard_assets.py`)**:
  - `dashboard.py`: Menambahkan field `envelope_visual` dan `macro_envelope` pada endpoint get symbol data.
  - `dashboard_assets.py`: Menambahkan layer visual ke-5 pada canvas overlay Lightweight Charts: rendering area pita transparan halus (*translucent institutional cyan wash*), garis batas body (amber ceiling & sky blue floor), serta awan ekor luar (*wick outer contour*).
- **Hasil Pengujian Komprehensif**:
  - `tests/test_pattern_engine.py`: 6/6 tests PASSED (bobot SG murni, outlier clamping CHF, invariansi kausal anti-repainting, densitas ekor, format visual, performa 3.93 ms).
  - Regression Test Suite (38 tests lintas ZCE, MSE, Trade Geometry, dan Pure Quant): **38/38 PASSED (100% OK)**.






