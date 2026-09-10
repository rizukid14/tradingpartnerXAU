# Session-Adaptive Trade Management & Anti-Sweep Cushion - Design Specification
**Date:** 2026-09-09  
**Branch:** quant-trade-noAI  
**Status:** Approved for Implementation Plan  
**Author:** Pair Programming (User & Antigravity)

---

## 1. Executive Summary & Root Cause Analysis

Audit performa trade minggu ini (7-9 September 2026) pada akun VTMarkets MT5 membuktikan adanya perbedaan performa tajam antara sesi Asia dan sesi Barat:
- Sesi Tokyo (07:00-14:00 WIB): Konsisten mencetak profit masif +,289.18 dengan Win Rate 78.1% (24 Win / 7 Loss).
- Sesi London & New York (14:00-24:00 WIB): Mengalami defisit akumulatif -.43 (di luar posisi floating malam ini).

### Analisis Kuantitatif Lapangan (18.720 Bar H1 & 72 Trade Riil):
1. Volatilitas & Jarum Sweep Sesi Barat Jauh Lebih Lebar:
   - Sesi New York memiliki rata-rata bar range 17.7 pips (+51.3% lebih lebar dari Tokyo: 11.7 pips).
   - Rata-rata ukuran wick (jarum sweep) di New York mencapai 8.9 pips (+43.5% lebih panjang dari Tokyo: 6.2 pips).
2. Kelemahan Fatal Trailing Stop M30 di Terminal Stage (Penyebab Hanya 4.1% Trade Sampai TP):
   - Dari 72 trade yang ditutup, hanya 3 trade (4.1%) yang berhasil menyentuh TP Penuh.
   - Sebanyak 28 trade (38.8%) tersapu oleh SL-trailing dengan rata-rata profit hanya +.53.
   - Simulasi bar M5 membuktikan bahwa 52.6% trade yang terkena SL-trailing di London/NY justru berbalik terbang >= 15 pips ke arah TP aslinya.
   - Root Cause: Penggunaan 0.50x ATR M30 di Stage 2 Terminal Lock terlalu kaku. ATR M30 FX sering kali hanya bernilai 6-10 pips, sehingga jarak trailing 0.50x ATR M30 hanya berjarak 3-5 pips di belakang harga tertinggi! Setiap noise 5-menit langsung membunuh posisi di 90% TP sebelum menyentuh garis finish.
3. Efek Gunting Partial Close 45% TP:
   - Mencairkan 50% lot di 45% TP dan menarik sisa lot ke BEP menyebabkan sisa volume tersapu di harga impas akibat retracement normal gelombang H1, menghancurkan rasio payoff akun ke 0.51 (rata-rata menang  vs rata-rata kalah ).

---

## 2. Architecture: 2-Session Temporal Management Matrix

Sistem membagi eksekusi manajemen posisi secara otomatis berdasarkan jam WIB (GMT+7):

### Matriks Parameter Terkalibrasi

| Parameter Manajemen | Sesi Tokyo (07:00-14:00 WIB) | Sesi London & NY (14:00-24:00 WIB) |
|---|:---:|:---:|
| Break-Even (BEP Trigger) | 45% - 50% TP | 55% TP (Mencegah mati di BEP sebelum TP1) |
| Partial Close (TP1 Trigger) | 50% TP (Cairkan 50% lot) | 60% TP (Cairkan 50% lot) |
| Trailing Stop Activation | 65% TP | 75% TP (Memberi ruang napas ekspansi gelombang H1) |
| Stage 1 Trailing Distance (Breathing) | 0.75x ATR H1 (Floor min 80 pts / 8 pips) | 1.00x ATR H1 (Floor min 150 pts / 15 pips) |
| Stage 2 Trailing Distance (Terminal) | 0.50x ATR H1 (Floor min 60 pts / 6 pips) | 0.50x ATR H1 (Floor min 80 pts / 8 pips) |
| Terminal Lock Trigger | >= 90% TP | >= 90% TP |
| Timeframe Dasar Terminal Lock | H1 (M30 dihapus permanen) | H1 (M30 dihapus permanen) |

---

## 3. Aturan Khusus & Invariant Preservations

1. Grade B Wall Scalp:
   - Tetap di-bypass 100% dari partial close (fokus single target sprint).
   - BEP dipercepat di 35% TP.
2. M4 Systemic Flow Continuation:
   - Tetap di-bypass 100% dari partial close.
   - BEP di 70% TP untuk mengakomodasi fluktuasi shock sistemik.
3. Grade S Macro Super-Shock:
   - BEP di 65% TP, Trailing Stop di 75% TP dengan 1.25x ATR H1.
4. GBPNZD & EURNZD (Ultra-Beta Crosses):
   - Tunduk pada kapasitas ZCE Runway alami tanpa pembatasan statis kaku.
5. Night Freeze (23:00-07:00 WIB):
   - Pembukaan order baru tetap dibekukan; posisi terbuka yang aktif tetap dikawal oleh aturan manajemen sesi London/NY sampai selesai.

---

## 4. Rencana Implementasi File

1. config.py & .env:
   - Deklarasi parameter sesi:
     - PARTIAL_CLOSE_TRIGGER_TP_PCT_LONDON_NY = 0.60
     - BREAK_EVEN_TRIGGER_TP_PCT_LONDON_NY = 0.55
     - TRAILING_ACTIVATION_TP_PCT_LONDON_NY = 0.75
     - TRAILING_DISTANCE_ATR_MULT_H1_LONDON_NY = 1.00
     - TRAILING_DISTANCE_MIN_POINTS_FX_LONDON_NY = 150
     - TRAILING_TERMINAL_ATR_MULT_H1 = 0.50
     - TRAILING_TERMINAL_MIN_POINTS_FX_TOKYO = 60
     - TRAILING_TERMINAL_MIN_POINTS_FX_LONDON_NY = 80
2. src/analytics/position_manager.py:
   - Injeksi helper is_london_ny_active(now_wib) untuk memilih threshold adaptif.
   - Mengubah kalkulasi Stage 2 Terminal Lock dari mt5.TIMEFRAME_M30 menjadi mt5.TIMEFRAME_H1.
3. tests/test_time_decay_and_vol_regime.py:
   - Unit test untuk menguji transisi otomatis parameter saat jam berpindah antara Tokyo (10:00 WIB) dan London/NY (16:00 WIB).
