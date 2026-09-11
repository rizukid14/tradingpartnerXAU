# Rekonsiliasi Kuantitatif: Evaluasi Kritis Tesis Chamber-to-Chamber vs Telemetri Empiris

**Tanggal**: 11 September 2026  
**Dokumen Rujukan**: `docs/THESIS_CHAMBER_TO_CHAMBER_AND_MOMENTUM_CONFIRMATION.md`  
**Sumber Data Empiris**: 
- `data/quant_shadow_trades.jsonl` (219 trade shadow M2, 174 terisi, periode 7–11 Sep 2026)
- `data/trade_lifecycle_telemetry.json` (43 trade live MT5 M2 periode sama)
- `data/gate_debug.log` (740 event `[SWEEP ... WALL GRADE]` periode 10–11 Sep 2026)
- `data/trading_bot.log`, `src/analytics/market_scanner.py`, `src/analytics/shadow_tracker.py`, `main.py`  
**Status Eksekusi**: Selesai diimplementasikan & diverifikasi (Unit Test 6/6 PASS)

---

## 1. Ringkasan Eksekutif & Verdict

Dokumen `THESIS_CHAMBER_TO_CHAMBER_AND_MOMENTUM_CONFIRMATION.md` mengajukan hipotesis restrukturisasi besar-besaran terhadap arsitektur radar (M1..M4), mendalilkan bahwa bot mengalami kegagalan pada trade AUDUSD karena *"Mid-Chamber Trap"* dan menuntut penghapusan bypass `is_limit_retest`.

Setelah dilakukan audit kuantitatif mendalam berbasis bukti telemetri empiris penuh, ditarik kesimpulan ilmiah sebagai berikut:

| Aspek | Klaim Hipotesis Tesis | Fakta Empiris & Realita Kode | Status & Keputusan |
|---|---|---|---|
| **Penyebab Missed M1 BUY AUDUSD** | Menyalahkan toleransi sweep (`sweep_tol = 0.35x ATR`) dan Directional Hysteresis | AUDUSD M1 BUY diblokir oleh **`[SFR VETO]`** (Systemic Flow Regime Supreme Precedence di `market_scanner.py:3453`) akibat Systemic Basket Lock aktif pada EUR/USD. `sweep_tol` sama sekali tidak pernah dievaluasi. | **Klaim Tesis Tertolak (Salah Diagnosa)** |
| **Pilar Penghapusan Mid-Chamber Bypass** | Menuntut penghapusan `if is_limit_retest: continue` di baris 3576 karena dianggap "meloloskan trap" | Bypass baris 3576 adalah optimasi sadar (Changelog 10 Sep #92). Menghapusnya akan membunuh seluruh pending limit order diskon yang terbukti menghasilkan Win Rate 66.7% (vs 55.1% pada chasing entries). | **Klaim Tesis Ditolak Mutlak (Merusak Edge)** |
| **Akar Masalah M2 SELL AUDUSD @ 0.71723** | Menuduh bot SELL di "harga ngawur tengah chamber" karena logika cacat | Bot SELL tepat di **ZCE C1 (0.71724)**. Namun log `[ZCE-AUDIT]` salah mencetak SL sebagai F1. Masalah sejati adalah ketiadaan Wall Quality Gate pada M2 dan klausa `has_res_hold` yang selalu `True`. | **Tesis Divalidasi Parsial, Solusi Dibenarkan Secara Kuantitatif** |
| **Tindakan Terhadap Dinding G1 Micro** | Memblokir keras (*hard-block*) seluruh entry pada dinding G1 Micro | Kebocoran mid-chamber hanya **+1.88 R** (noise harian 7.96 R); hard-SL identik (21.9% vs 24.4%, $p=0.70$). Hard-block berisiko memotong pemenang. Solusi optimal: **Soft-gate ke `GRADE_B`** + persistensi telemetri grade. | **Soft-Gate Diadopsi (Sesuai Standar Data-Driven)** |

---

## 2. Bedah Kuantitatif Telemetri Empiris (DeepSeek Cohort Analysis)

### 2.1. Analisis Kohort: Boundary vs Mid-Chamber (Proxy `dealing_range_pos`)
Karena grade dinding historis sebelumnya belum dipersist secara eksplisit di `quant_shadow_trades.jsonl`, posisi relatif range (`dealing_range_pos`) digunakan sebagai proxy terdekat:
- **Boundary** ($\le 0.35$ atau $\ge 0.65$)
- **Mid-range** ($0.35 - 0.65$)

| Metrik Kuantitatif | Kohort Boundary ($\le 0.35 / \ge 0.65$) | Kohort Mid-Range ($0.35 - 0.65$) | Uji Statistik & Signifikansi |
|---|---|---|---|
| **Ukuran Sampel ($n$)** | 96 trade | 78 trade | Total 174 trade terisi |
| **Take Profit (TP Hit)** | **30.2%** | 20.5% | Chi-square $p = 0.166$ (*Tidak Signifikan*) |
| **Stop Loss (SL Hit)** | **21.9%** | **24.4%** | Chi-square $p = 0.699$ (**Praktis Identik!**) |
| **Cumulative Net R** | **+17.75 R** | **-1.88 R** | Gain jika mid dibuang: +1.88 R |
| **Profit Factor (PF)** | **1.98** | 0.90 | Edge boundary lebih tinggi |
| **Mean R / Trade** | **+0.185 R** | -0.024 R | Permutasi $p = 0.039$, Bootstrap 95% CI $[+0.014, +0.399]\text{R}$ |

### 2.2. Temuan Kunci Terhadap Mekanisme Tesis
1. **Mekanisme Tesis Terbantahkan**:
   Tesis mendalilkan bahwa order mid-chamber "diinjak pullback atau tersapu waterfall penetrasi". Jika hipotesis ini benar, tingkat penetrasi hard-SL pada kohort mid-range seharusnya melonjak drastis. Nyatanya, **tingkat hard-SL praktis identik (21.9% vs 24.4%, $p = 0.699$)**.
2. **Akar Perbedaan: Efisiensi Exit**:
   Perbedaan performa bukan karena harga menabrak SL, melainkan efisiensi exit: trade mid-range lebih sering terpotong di BEP atau trailing stop (51% vs 48%) akibat keterbatasan runway sebelum mencapai target distal.
3. **Besaran Ekonomi vs Noise Harian**:
   - Total Net R M2 selama 5 hari (paper): **+15.87 R**.
   - Jika kohort mid-range dibuang total: **+17.75 R** (hanya selisih **+1.88 R**).
   - Standar deviasi harian Net R M2: **7.96 R**.
   - Selisih +1.88 R hanya merepresentasikan **$0.24\times$ dari noise harian**. Memblokir ~36% setup secara kaku untuk mengejar +1.88 R adalah tindakan *overfitting* yang berisiko memotong pemenang dan mengeringkan volume sampel $N$.

### 2.3. Base Rate Distribusi Dinding (740 Event M1):
- **GRADE_3_MACRO**: 195 (26%)
- **GRADE_2_INTERMEDIATE**: 281 (38%)
- **GRADE_1_MICRO**: 264 (36%)

M1 menolak 36% percobaan karena dinding G1. M2 tanpa gate meloloskan setup G1 tersebut, namun kontribusi kerugian bersihnya sangat marjinal (-1.88 R).

---

## 3. Solusi Arsitektur yang Telah Diimplementasikan

### 3.1. Persistensi Telemetri Grade Dinding (Solusi Fundamental)
Ketiadaan data historis grade dinding yang selama ini menghalangi uji counterfactual telah diselesaikan:
1. **`src/analytics/shadow_tracker.py`**:
   - `register_candidate()` kini mengekstrak dan menyimpan:
     * `wall_grade`: Grade benteng aktif (`GRADE_1_MICRO`, `GRADE_2_INTERMEDIATE`, `GRADE_3_MACRO`)
     * `f1_reaction_grade` & `c1_reaction_grade`
     * `zce_f1` & `zce_c1`
     ke dalam objek `trade.metadata` pada `data/quant_shadow_trades.jsonl` dan `data/quant_shadow_state.json`.
2. **`src/analytics/position_manager.py` & `main.py`**:
   - `record_trade_open_telemetry()` diperluas untuk mencatat metadata benteng ZCE (`wall_grade`, `f1_reaction_grade`, `c1_reaction_grade`, `zce_f1`, `zce_c1`, `setup_grade`) ke dalam `data/trade_lifecycle_telemetry.json`.

Dengan penambahan ini, dalam 1–2 minggu (~60–100 trade), sistem akan memiliki dataset empiris bersih untuk mengevaluasi apakah hard-block pada G1 memang diperlukan atau tidak.

### 3.2. Soft-Gate M2 Dinding G1 ke `GRADE_B`
Daripada memblokir keras (`SKIP`) M2 yang menempel benteng G1 tanpa wick rejection besar, sistem menerapkan **Soft-Gate `GRADE_B`**:
- Setup tetap ditradingkan (mempertahankan kelengkapan sampel $N$).
- Mengunci volume ke **1 tiket murni** (tanpa boost ticket).
- **Partial close di-bypass 100%**.
- **Break-Even (BEP) dipercepat ke 35% TP** (mengamankan modal lebih dini pada benteng lemah sebelum terjadi pembalikan).
- Selaras 1:1 dengan arsitektur `GRADE_B` institusional yang sudah mapan di `config.py` dan `consensus.py`.

### 3.3. Marubozu Guard (Anti-Falling Knife)
Tetap dipertahankan sebagai filter momentum murni:
- Melarang keras pemasangan limit order menabrak candle Marubozu ekspansif (body $\ge 55\%$ dengan wick penolakan $< 20\%$) tanpa adanya tanda kelelahan momentum ($has\_res\_hold = False$).
- Memotong kluster kekalahan bertipe *blow-through* (MAE -0.96R s/d -1.05R).

### 3.4. Koreksi Log Audit ZCE (`main.py`)
Memperbaiki baris log `[ZCE-AUDIT]` agar mencetak nilai `ZCE_F1` dan `ZCE_C1` sejati dari metadata kandidat, mengeliminasi distorsi visual yang sebelumnya mencetak level Stop Loss sebagai F1.

---

## 4. Hasil Verifikasi Unit Test Suite

Pengujian dijalankan pada suite baru `tests/test_m2_wall_quality_and_exhaustion.py`:
- `test_m2_sell_soft_gates_grade1_micro_to_grade_b`: **PASSED** (Memvalidasi soft-gate G1 ke GRADE_B)
- `test_m2_sell_blocks_bullish_marubozu`: **PASSED** (Memvalidasi Marubozu Guard SELL)
- `test_m2_buy_blocks_bearish_marubozu`: **PASSED** (Memvalidasi Marubozu Guard BUY)
- `test_m2_sell_allows_healthy_rejection`: **PASSED** (Memvalidasi toleransi wick sehat)
- `test_zce_audit_telemetry_format`: **PASSED** (Memvalidasi format log ZCE-AUDIT)
- `test_shadow_tracker_persists_wall_grades`: **PASSED** (Memvalidasi persistensi telemetri grade)

**Hasil**: 6 passed dalam 1.54 detik (100% kelulusan).  
Suite `tests/test_shadow_tracker.py`: 11 passed dalam 1.79 detik (100% kelulusan).

---

## 5. Status Konfigurasi CBSS
Sesuai arahan eksplisit pengguna pada 11 September 2026:
- Parameter `ENABLE_CBSS` **tetap nonaktif** (`ENABLE_CBSS=false` di `.env` dan `False` di `config.py`).
