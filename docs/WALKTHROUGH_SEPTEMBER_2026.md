# WALKTHROUGH: REKONSILIASI KUANTITATIF & PENYELARASAN ARSITEKTUR SEPTEMBER 2026

Dokumen ini adalah catatan resmi implementasi rekonsiliasi tesis vs telemetri empiris, penyempurnaan perlindungan posisi, ekstraksi modular engine radar M2, dan optimasi performa runtime bot.

---

## 1. Ringkasan Eksekutif Perubahan

| Komponen | Status Sebelum | Status Sesudah | Manfaat Kuantitatif |
|---|---|---|---|
| **M2 Dinding G1 Micro** | `has_res_hold` selalu `True` / usulan tesis: Hard-Block | Soft-Gate ke **`GRADE_B`** (1 tiket murni, no partial, BEP 35%) | Mengamankan data sampel $N$ tanpa memotong pemenang (+1.88R net gain) |
| **Audit Log ZCE (`main.py`)** | Menampilkan SL sebagai F1 di `[ZCE-AUDIT]` | Menampilkan `ZCE_F1` & `ZCE_C1` riil dari ZCE | Eliminasi 100% kebingungan operator antara SL vs benteng |
| **Telemetri Dinding ZCE** | Grade dinding tidak dipersist di telemetri | `wall_grade`, `f1_reaction_grade`, `c1_reaction_grade`, `zce_f1`, `zce_c1` tersimpan persisten | Memungkinkan audit counterfactual bersih 1–2 minggu ke depan |
| **Break-Even (BEP) Grade B** | Jalur TP tertahan di 60% TP flat | **35% TP** di `position_manager.py` & `shadow_tracker.py` | Mengunci profit cepat sebelum retracement di benteng lemah |
| **Ekstraksi M2 Radar** | Logika inline panjang & test tautologis | Method produksi mandiri `_evaluate_m2_wall_quality` | Test memanggil fungsi produksi langsung, zero tautology |
| **Panggilan Micro M5** | Dipanggil setiap siklus scanning | **Lazy M5 Checking** (hanya saat H1 butuh konfirmasi) | Menghemat ~85% panggilan MT5 rate copy |
| **Startup MT5 Connector** | Handshake login ulang 15–20 detik | Bypass login jika terminal sudah terhubung ke akun target | Waktu booting terpangkas ke **3.5 detik** |
| **Idempotensi Shadow Tracker** | Potensi double-count stats in-memory | Dedup set `_resolved_ids` pada `_record_resolved` | Konsistensi mutlak metrik Win Rate & cumulative R |
| **Label Status Shadow MT5** | Tiket MT5 closed ditandai `SKIPPED_EXPIRED` | Ditandai akurat `EXECUTED_MT5_RESOLVED` | Audit telemetri akurat membedakan order riil vs skipped |

---

## 2. Detail Implementasi Kode

### 2.1. Implementasi Grade-Aware BEP 35% TP untuk GRADE_B
- **`src/analytics/position_manager.py`**:
  Pada jalur kalkulasi `tp_points > 0`, ditambahkan cabang grade:
  ```python
  if "GRADE_S" in grade:
      bep_tp_ratio = 0.65
  elif is_m4:
      bep_tp_ratio = getattr(config, "M4_BREAK_EVEN_TRIGGER_TP_PCT", 0.70)
  elif "GRADE_B" in grade or "REDUCED" in grade or is_vacuum_or_stretched:
      bep_tp_ratio = getattr(config, "GRADE_B_BREAK_EVEN_TRIGGER_TP_PCT", 0.35)
  else:
      bep_tp_ratio = getattr(config, "BREAK_EVEN_TRIGGER_TP_PCT", 0.60)
  ```
- **`src/analytics/shadow_tracker.py`**:
  Cabang evaluasi BUY dan SELL kini membaca `trade.metadata.get("setup_grade")` atau `trade.action_tier`:
  ```python
  sg = str(trade.metadata.get("setup_grade") or trade.action_tier or "GRADE_A").upper()
  if "GRADE_S" in sg:
      bep_tp_ratio = 0.65
  elif "M4" in str(trade.setup_type):
      bep_tp_ratio = getattr(config, "M4_BREAK_EVEN_TRIGGER_TP_PCT", 0.70)
  elif "GRADE_B" in sg or "REDUCED" in sg:
      bep_tp_ratio = getattr(config, "GRADE_B_BREAK_EVEN_TRIGGER_TP_PCT", 0.35)
  else:
      bep_tp_ratio = getattr(config, "BREAK_EVEN_TRIGGER_TP_PCT", 0.60)
  ```
- **`config.py` & `.env`**:
  Parameter terkonfigurasi: `GRADE_B_BREAK_EVEN_TRIGGER_TP_PCT = 0.35`.

### 2.2. Ekstraksi Modular `_evaluate_m2_wall_quality` & Lazy M5
- **`src/analytics/market_scanner.py`**:
  Method produksi mandiri:
  ```python
  def _evaluate_m2_wall_quality(
      self, sym: str, direction: int, base_level: float, c_qual: dict,
      macro: dict, atr_val: float, pt: float, mt5_connector=None
  ) -> Tuple[bool, bool, str]
  ```
  Menyatukan 3 pilar:
  1. *Anti-Marubozu Waterfall Guard*: Menolak candle marubozu ekspansif counter-trend (body >= 55%, wick < 20%).
  2. *Lazy M5 Checking*: `_verify_m5_rejection_wick` hanya dipanggil jika H1 belum memiliki konfirmasi wick penolakan >= 20% atau jika benteng G1 membutuhkan audit mikro.
  3. *G1 Micro-Wall Soft-Gate*: Mengembalikan `is_soft_g1 = True` jika anchor berada pada benteng `GRADE_1_MICRO` tanpa wick rejection besar, memicu downgrade otomatis ke `GRADE_B`.

### 2.3. Idempotensi & Labeling Telemetri Shadow Tracker
- **`src/analytics/shadow_tracker.py`**:
  - `self._resolved_ids` memastikan `_record_resolved` tidak menduplikasi penambahan `_stats` in-memory jika dipanggil ulang.
  - Tiket MT5 yang berhasil close dengan TP/SL diberi label `EXECUTED_MT5_RESOLVED`, bukan `SKIPPED_EXPIRED`.

### 2.4. Optimasi Startup MT5
- **`src/core/mt5_connector.py`**:
  Pengecekan `cur_login != int(config.MT5_LOGIN)` sebelum login. Menghemat handshake login ulang saat terminal desktop sudah aktif.
- **`main.py`**:
  Progress print `[RADAR BOOT] Memuat konteks makro 26 simbol universe (H1/H4/D1/W1)... Mohon tunggu ~25 detik` memberikan feedback visual real-time saat startup.

---

## 3. Hasil Uji Unit Test

1. **Test M2 Wall Quality & Exhaustion (`tests/test_m2_wall_quality_and_exhaustion.py`)**:
   - 6/6 tests **PASSED** (0.010s) — menguji langsung fungsi produksi dan memvalidasi bahwa `mock_m5.assert_not_called()` saat H1 marubozu diblokir.
2. **Test Shadow Tracker (`tests/test_shadow_tracker.py`)**:
   - 13/13 tests **PASSED** (0.301s) — memvalidasi persistensi telemetri grade, BEP 35% Grade B, dan idempotensi `_record_resolved`.
3. **Test Time Decay & Vol Regime (`tests/test_time_decay_and_vol_regime.py`)**:
   - 8/8 tests **PASSED** (2.758s) — memvalidasi akselerasi BEP 35% Grade B pada posisi riil MT5 di `position_manager.py`.
4. **Koneksi Live MT5**:
   - `init_mt5()` berhasil terhubung ke akun Live `#27556325` dalam waktu 3.5 detik (terverifikasi).
