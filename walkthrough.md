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
