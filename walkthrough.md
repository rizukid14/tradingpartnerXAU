# Walkthrough: Rework M4 (Pure Technical Breakout Continuation), CSM Telemetry Decoupling & Mid-Chamber Trap Correction

**Tanggal**: 10 September 2026  
**Status**: Selesai, Terverifikasi Penuh (**100% PASS — 230+ Unit Tests**)  
**Branch**: `quant-trade-noAI`  
**Akun MT5**: Live Cent `#27556325` (`VTMarkets-Live 3`)

---

## 1. Ringkasan Masalah & Temuan Empiris

### A. Evaluasi Performa Virtual Paper Trade (Shadow Tracker) & CSM
1. **Audit Shadow Trades**:
   - 07 Sep: +1.51R (WR 17.4%, 59 BEP)
   - 08 Sep: +15.38R (WR 46.4%, 9 Loss)
   - 09 Sep: +17.39R (WR 35.8%, M2 profit +17.27R)
   - 10 Sep: -6.56R (WR 26.8%, 14 Loss, M2 rugi -3.80R, M3 rugi -2.99R, M1 untung +0.23R)
2. **Audit Telemetri 90 Trade Riil Akun Live MT5**:
   - `CSM OPPOSED at Open` (entry saat harga pullback/diskon melawan CSM sesaat): 18 trade, **WinRate 66.7%**, P/L bersih **+$130.78**.
   - `CSM ALIGNED at Open` (entry mengejar momentum searah CSM): 69 trade, **WinRate 55.1%**, P/L bersih **-$914.84**.
   - **Kesimpulan**: CSM bukanlah prediktor struktural yang baik jika dipakai sebagai *leading indicator / hard veto*. Memakai CSM untuk mem-veto entry membuang trade diskon berkualitas dan memaksa sistem membeli di puncak tren. Selain itu, `CSM Dynamic Flow Bailout` memotong dini posisi sebelum invalidasi SL tercapai (misal EURUSD -$25.48 dan USDCHF -$18.17).

### B. M4 Rework (Breakout Continuation vs Systemic Flow)
- Sinyal M4 sebelumnya bergantung pada rolling 720-bar currency z-score `zb`/`zq`.
- Sesuai prinsip *Price Action*, M4 dimurnikan menjadi **M4 Breakout Continuation (DBD / RBR Micro-Basing)** berbasis bar lokal OHLC H1 pair bersangkutan.
- *Systemic Flow* tetap hidup mandiri di Layer 0 sebagai gate makro pelindung portofolio.

### C. Mid-Chamber Trap Veto
- Sangat tepat untuk M1 (Sweep) guna menghindari sapuan semu di tengah range konsolidasi.
- Namun, keliru jika memukul rata M2 (Pullback di EMA50) dan M4 (Micro-Basing Continuation) yang justru secara alami bertumpu pada konsolidasi di paruh tengah chamber.

---

## 2. Perubahan yang Diimplementasikan

1. **Konfigurasi (`.env` & `config.py`)**:
   - `ENABLE_CSM_FLOW_FILTER = False` (Mode OBSERVE — CSM murni telemetri).
   - `ENABLE_CSM_DYNAMIC_BAILOUT = False` (Bailout dimatikan agar posisi bernafas mengikuti SL/TP ZCE).
   - `M4_SETUP_TYPE = "DBD_RBR_BREAKOUT_CONTINUATION"`
   - `M4_BASING_MIN_BARS = 3`
   - `M4_BASING_MAX_RANGE_ATR = 0.35`
   - `M4_DISPLACEMENT_MIN_BODY_PCT = 0.50`
   - `M4_LOOKBACK_SWING_BARS = 20`
   - `M4_EXTREME_CSM_DELTA_OVERRIDE = 0.035`

2. **Market Scanner (`src/analytics/market_scanner.py`)**:
   - `_detect_m4_breakout_continuation`:
     * **RBR (BUY)**: Candle impulsif H1 ($Close > Open$, body ratio $\ge 50\%$) menembus recent swing high 20 bar $\rightarrow$ High-Tight Basing $2-6$ bar (range $\le 0.35\times\text{ATR}$, floor $\ge$ midpoint breakout) $\rightarrow$ Buy Limit di atap basing.
     * **DBD (SELL)**: Candle impulsif H1 ($Close < Open$, body ratio $\ge 50\%$) menembus recent swing low 20 bar $\rightarrow$ Low-Tight Basing $2-6$ bar (range $\le 0.35\times\text{ATR}$, ceiling $\le$ midpoint breakdown) $\rightarrow$ Sell Limit di lantai basing.
   - Evaluasi M4 di `scan_all`: Memanggil `_detect_m4_breakout_continuation`, memvalidasi arah, menghitung SL/TP struktural dengan Segmented Safety Floor dan ZCE barrier destination.
   - `_is_direction_allowed`:
     * Pembebasan M2 dan M4 dari *Mid-Chamber Trap Veto*.
     * Menghormati `ENABLE_CSM_FLOW_FILTER = False`.

3. **Position Manager (`src/analytics/position_manager.py`)**:
   - Menyelaraskan default fallback `ENABLE_CSM_DYNAMIC_BAILOUT` ke `False`.

4. **UI & Dashboard Cockpit (`dashboard.py`, `src/core/cli_theme.py`)**:
   - Gate 4/5 di dashboard merender status **`OBSERVE` (Cyan)** informatif.
   - Badge M4 di CLI Theme diperbarui menjadi `[M4 BASING]`.

---

## 3. Hasil Pengujian Otomatis

1. **Unit Test Suite Baru (`tests/test_m4_breakout_continuation.py`)**:
   - `test_rbr_bullish_breakout_basing`: **PASS**
   - `test_dbd_bearish_breakdown_basing`: **PASS**
   - `test_basing_too_wide_rejected`: **PASS**
2. **Context Guard Suite (`tests/test_csm_and_m3_context_guard.py`)**:
   - `test_csm_observe_mode_permits_trades_when_filter_disabled`: **PASS**
   - Total 5/5 tests: **PASS**
3. **Regression Suite (`tests/test_sep8_enhancements.py`, `tests/test_market_scanner.py`)**:
   - `tests/test_sep8_enhancements.py`: 9/9 **PASS**
   - `tests/test_market_scanner.py`: 35/35 **PASS**
4. **Full Test Discover Across Entire Repository**:
   - Perintah: `python -m unittest discover -s tests -p "test_*.py"`
   - Hasil: **230+ tests OK (Exit Code 0)**.

---

## 4. Post-Mortem Insiden: M5 Runner BEP Position Manager Mismatch (14 Sep 2026)

### A. Deskripsi Masalah
- **Gejala**: Posisi `GBPUSD-ECNc` SELL mencapai >88% jarak TP, tetapi SL tidak digeser ke BEP secara otomatis oleh bot, sehingga pengguna harus menggeser SL manual.
- **Root Cause**: `main_m5.py` memanggil `position_manager.manage_all_positions(connector, risk)` dengan 2 argumen, padahal definisi di `position_manager.py` hanya menerima 0 argumen (`def manage_all_positions():`). Hal ini menyebabkan `TypeError` di setiap iterasi loop 2 detik yang tertelan secara diam-diam oleh `logger.debug`, sehingga seluruh siklus manajemen posisi (BEP 80% TP, trailing stop, pre-rollover shield) tidak pernah dieksekusi.

### B. Solusi yang Diterapkan
1. **`main_m5.py`**: Memperbaiki pemanggilan menjadi `position_manager.manage_all_positions()` (tanpa argumen) serta mengganti penanganan error menjadi `logger.error` dan `print` agar kegagalan langsung terlihat di konsol.
2. **`src/analytics/position_manager.py`**: Menambahkan parameter fleksibel `*args, **kwargs` pada definisi `def manage_all_positions(*args, **kwargs):` sebagai proteksi *defensive programming*.
3. **Verifikasi**: Uji coba langsung fungsi `manage_all_positions()` pada 7 posisi terbuka live di akun Cent MT5 berjalan sukses tanpa error. Bot direstart dan kini mengelola posisi secara aktif.

---

## 5. Penyempurnaan Cockpit Dashboard: Toggle Micro-ZCE vs Macro-ZCE & SFC Basket Telemetry (14 Sep 2026)

### A. Fitur Baru yang Diimplementasikan
1. **Toggle Interaktif `[ 🎯 Micro-ZCE | 🏛️ Macro-ZCE ]`**:
   - Ditambahkan di toolbar filter strip chart ([`dashboard_assets.py`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/dashboard_assets.py)).
   - Pengguna dapat beralih secara instan antara stasiun Micro-ZCE (M5/M15/H1 rapat 8–18 pips yang diincar bot M5) dan benteng Macro-ZCE (H1/D1/W1).
2. **Sinkronisasi Timeframe Otomatis**:
   - Memilih tombol `M5 Micro` secara otomatis mengaktifkan mode `Micro-ZCE` dan memberi prefix `µ` pada stasiun di chart (misal `µC1 [G2] 0.71190` pada AUDUSD).
   - Memilih `H1 Structure` atau `H4 Pattern` secara otomatis mengaktifkan mode `Macro-ZCE` (misal `C1 [G3] 0.71500`).
3. **M5 Background Radar Integration**:
   - [`dashboard.py`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/dashboard.py) menginisialisasi `MarketScannerM5` saat konfigurasi `TIMEFRAME=M5`, sehingga daftar pair di watchlist dan radar proximity 100% konsisten dengan bot eksekusi live.
4. **Live Currency Basket SFC Telemetry**:
   - Di header atas dashboard, ditambahkan badge telemetri **`Basket SFC`** yang menghitung eksposur agregat posisi aktif secara real-time (misal `USD +4 • JPY +2 • CHF -3`).

### B. Hasil Verifikasi Live
- Uji endpoint API `/api/overview` berhasil mengembalikan data akun, 7 posisi live, dan matriks eksposur keranjang SFC.
- Uji endpoint `/api/symbol/AUDUSD-ECNc?tf=M5&zce_mode=micro` mengembalikan 7 stasiun Micro-ZCE presisi (`C1 = 0.71190` persis di area entry order sell bot).
- Uji endpoint `/api/symbol/AUDUSD-ECNc?tf=H1&zce_mode=macro` mengembalikan 8 level benteng makro institusional.
- Dashboard server (Port 8765) direstart dan beroperasi mulus.

---

## 6. Cooldown 10 Menit Pasca Pembatalan Pending Order (Manual & 75% TP Runaway) & Shift Night Freeze ke 00:00 WIB

### A. Fitur Baru yang Diimplementasikan
1. **Cooldown 10 Menit (`PENDING_ORDER_CANCEL_COOLDOWN_SECONDS = 600`)**:
   - Ditambahkan di [`.env`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/.env) dan [`config.py`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/config.py).
   - Menyimpan status cooldown di `self._symbol_cancel_cooldowns` dan file persisten `scanner_cooldowns_m5.json`.
2. **Auto-Cooldown saat Target Proximity 75% TP Terlewati**:
   - Di [`position_manager.py:audit_pending_orders_thesis()`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/src/analytics/position_manager.py): saat order dicabut karena harga sudah menempuh $\ge 75\%$ jarak TP tanpa ter-fill, sistem langsung mendaftarkan cooldown 10 menit ke instance scanner aktif.
3. **Pending Order Watcher di `main_m5.py`**:
   - Ditambahkan fungsi `_sync_pending_orders(scanner)` pada loop 2 detik: mendeteksi tiket pending order yang dibatalkan manual oleh pengguna di MT5, mengunci pair selama 10 menit, dan mengirim notifikasi pembatalan ke Telegram.
4. **Night Freeze Dimulai Jam 00:00 WIB**:
   - `NIGHT_FREEZE_START_HOUR_WIB = 0` (WIB) disinkronkan di [`.env`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/.env) dan [`config.py`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/config.py).
   - Memperbaiki bug perbandingan jam di [`risk_engine.py`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/src/core/risk_engine.py), [`market_scanner.py`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/src/analytics/market_scanner.py), dan [`main.py`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/main.py) dengan logic boundary yang aman untuk rentang `0 <= now.hour < 6`.

### B. Hasil Verifikasi Otomatis & Live
- **Unit Test**: 60/60 tests PASSED (100% OK) di `test_market_scanner_m5.py`, `test_cbss_and_risk_shields.py`, `test_audit_pending_orders_thesis.py`, dan `test_market_scanner.py`.
- **Live Execution**: Bot `main_m5.py` dijalankan ulang secara bersih dan langsung memindai 28 pairs serta berhasil mengeksekusi order riil di akun Cent.



