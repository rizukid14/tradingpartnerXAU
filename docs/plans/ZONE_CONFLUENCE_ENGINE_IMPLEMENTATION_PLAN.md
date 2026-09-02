# Implementation Plan — Zone Confluence Engine (ZCE)

> Melengkapi [RFC 11: ZONE_CONFLUENCE_ENGINE_SPEC.md](./ZONE_CONFLUENCE_ENGINE_SPEC.md).
> Prinsip: **parity-first, feature-flag, zero consumer break**, uji 100% PASS di tiap fase, rollback via `.env`.

---

## Ringkasan Fase

| Fase | Isi | Output utama | Kriteria selesai |
|---|---|---|---|
| 0 | Dokumen & desain | RFC + plan ini | ✅ selesai (2 Sep 2026) |
| 1 | **ZCE standalone + parity test (mode legacy)** | `zone_confluence_engine.py`, `tests/test_zone_confluence_engine.py` | Parity C1/F1/C2/F2/layered **identik** dengan MSE pada fixture; test suite lama tetap 100% PASS |
| 2 | **MSE konsumsi ZCE** (flag `.env`) | refactor Blok A/B MSE | Output MSE pre/post refactor identik (regression fixture); suite lama PASS |
| 3 | **Aktifkan grid multi-horizon + integrasi eksekusi** | scale ladder, SCALE_CONFLICT → Gate B; method selector; readiness; payload LLM | Shadow live N hari; setup tereksekusi dilengkapi tag respect ledger |
| 4 | (Opsional, terpisah) Arah multi-horizon MSE | — | RFC baru |

---

## Fase 1 — ZCE Standalone (mode legacy) + Parity Test

### File
- **Baru**: `src/analytics/zone_confluence_engine.py` — `ZoneConfluenceEngine`, dataclass `ZoneCluster/ScaleLadder/ZoneMapResult` (RFC bagian 5).
- **Baru**: `tests/test_zone_confluence_engine.py`.
- **Edit**: `config.py` + `.env` (tambah key `ZCE_*` RFC bagian 14; semua default off `ZCE_ENABLED=False`).
- **Edit**: `docs/CHANGELOG_SEPTEMBER_2026.md` & `AGENTS.md` (dicatat setelah lolos test).

### Tugas
1. Ekstrak helper MSE menjadi fungsi modul bersama **tanpa mengubah perilaku**:
   - `_cluster_merge_orthogonal`, `_get_fortress_tag`, `_find_swings`, `_detect_drop_base_drop`, `_detect_rally_base_rally` — biarkan tetap method di kelas; ZCE **mengimpor** dari MSE (ekstraksi fisik menyusul Fase 3 agar diff kecil & mudah revert).
2. Implementasi pipeline mode `legacy` — reproduksi persis input MSE hari ini:
   - Satu horizon per TF (MN1 50 / W1 100 / D1 350 / H4 400 / H1 250 / M30 200), FRVP window tetap (D1 tail-60, H4 tail-100), tanpa FVG, skor elemen identik (PWL/PWH/PDL/PDH = 4.0–4.5 dst).
   - Elekt C1/F1/C2/F2 + `layered_floors/ceilings` identik (RFC bagian 9).
3. **Parity test** (inti Fase 1): fixture snapshot output `MacroStrategicDirective` dari MSE untuk 3–5 simbol (EURUSD, GBPUSD, USDJPY, EURJPY, GBPCHF) pada data live MT5 saat test dijalankan → bandingkan field `immediate_floor_f1, immediate_ceiling_c1, deep_floor_f2, deep_ceiling_c2, layered_floors, layered_ceilings, c1_reaction_grade, f1_reaction_grade, chamber_position_pct` dari MSE vs ZCE. Toleransi = 1 point (rounding).
4. Unit test sintetik (tanpa MT5):
   - merge spasial dua elemen berdekatan → 1 klaster; toleransi terhormat.
   - dedupe horizon (J1): 2 sel horizon berbeda yang menghasilkan band sama → `horizon_max` = maks, skor tidak dihitung dobel.
   - normalisasi `width_atr`; klaster `width_atr > 2.0` → flag `TOO_WIDE`.
   - ladder & `SCALE_CONFLICT`: sintetik rally 150-bar lalu pullback → `LOCAL_DISCOUNT_MACRO_PREMIUM` terdeteksi.
   - freshness: klaster 0 hari vs 30 hari → multiplier benar.
5. **Benchmark**: ukur ms/simbol mode legacy; target acuan untuk Fase 3 (< 120 ms/simbol mode full).
6. Command `python -m pytest tests/ -q` → seluruh suite (lama + baru) 100% PASS.

### Rollback
Hapus baris `ZCE_ENABLED` di `.env` (atau set False) — ZCE tidak tersambung ke eksekusi sama sekali di Fase 1.

---

## Fase 2 — MSE Konsumsi ZCE (flag)

### File
- **Edit**: `src/analytics/macro_strategic_engine.py` — Blok A/B (baris 464–1077) dilewati saat `ZCE_ENABLED=True & ZCE_MODE=legacy`; MSE membaca `ZoneMapResult` (floors/ceilings/elected walls). Blok C/D (state machine → eksekusi) **tidak berubah**.
- **Edit**: `config.py`/`.env`.
- **Edit**: `tests/test_macro.py` (+ regression fixture MSE pre/post).

### Tugas
1. Suntik `ZoneMapResult` sebagai pengganti hasil Blok A/B internal (hanya saat flag aktif).
2. `MacroStrategicDirective` tetap diisi dari nilai yang sama (kontrak RFC bagian 3).
3. Regression: fixture `directive` MSE lama vs baru → identik (toleransi 1 point).
4. Suites lama PASS: `test_macro.py`, `test_symbol_rotation.py`, `test_time_decay_and_vol_regime.py`, `test_zone_confluence_engine.py`.

### Rollback
Set `ZCE_ENABLED=False` → MSE kembali ke jalur internal Blok A/B (kode lama tidak dihapus di Fase 2, hanya di-shadow oleh flag).

---

## Fase 3 — Grid Multi-Horizon + Integrasi Eksekusi

### File
- **Edit**: `src/analytics/zone_confluence_engine.py` (mode `full`).
- **Edit**: `src/analytics/market_scanner.py`:
  - Input Gate B (`evaluate_universal_sweep_gates`) & anti-bear veto (1261–1264) memakai `ScaleLadder` + klaster ZCE (`recent_ceiling_touch` = sentuhan klaster C1 ber-grade ≥ G2 non-COLD; `dealing_range_pos` = pos_100 & pos_250; anchor M1/M2/M3 dari klaster).
  - `suggested_method` & `readiness_score` untuk pengurutan scan 60 detik.
- **Edit**: `src/core/llm_client.py` — payload per model (RFC bagian 13): zone table (≤ 15 klaster) + distribusi tape (Gemini M1 30/M5 48/M15 24/M30 12; OpenAI D1 5/H4 8; DeepSeek H1 6/M5 24).
- **Edit**: `src/core/consensus.py` — SL/TP anchor struktural ZCE + `SL_MAX_ATR_MULT` configurable (tugas #7).
- **Edit**: `src/analytics/position_manager.py`? — **tidak diubah**; hanya konsumen TP/SL dari konsensus. Verifikasi ulang saja.
- **Edit**: `config.py`/`.env`, `tests/`, `docs/prompt/` (ekspor verbatim tetap jalan), changelog & `AGENTS.md`.

### Tugas
1. Aktifkan grid (RFC bagian 4) + FRVP hanya tf ≤ H4 + primitif FVG (baru).
2. Rate cache 6-TF jadi milik ZCE; MSE & scanner macro cache membaca dari sana (hapus fetch duplikat).
3. Wire `SCALE_CONFLICT` ke Gate B; verifikasi tidak ada perubahan threshold gate.
4. Readiness & method selector → log di `/radar` + Bento HUD (opsional Tile 1).
5. **Shadow live** (ZCE_MODE=shadow): log semua perbedaan keputusan ZCE vs MSE + tag respect ledger `(pair, grade, width_atr, COLD/VACUUM)` per setup tereksekusi. Durasi minimal 7 hari atau ≥ 60 sampel per bucket sebelum kalibrasi bobot (aturan validitas).
6. Setelah shadow bersih (tidak ada regresi), `ZCE_MODE=full` untuk produksi.
7. **SL/TP berbasis anchor struktural ZCE** (`consensus.py`, flag-gated, validasi shadow):
   - SL diusulkan dari anchor struktural: belakang `distal` klaster entry + anti-wick buffer (via `candidate.sl`), bukan murni usulan LLM yang cuma di-floor/ceil.
   - `SL_MAX_ATR_MULT` configurable dari `.env` (default 2.5) menggantikan hardcode `atr_points * 2.5` di `consensus.py:186-206`.
   - Jika anchor > ceiling: **SKIP** dengan label `ANCHOR_TOO_WIDE` — bukan clamp pendekkan ke ceiling yang memarkir SL di tengah struktur (stop prematur).
   - Fallback statis 350/800/45000 saat ATR gagal → **reject** (ATR gagal = data MT5 bermasalah).
   - Floor ATR + R:R gate tetap sebagai safety net (invariant tidak diubah).

### Rollback
`ZCE_MODE=legacy` (kembali ke perilaku MSE hari ini) atau `ZCE_ENABLED=False`.

---

## Checklist Integrasi (8 file AGENTS.md)

| File | Terdampak? | Keterangan |
|---|---|---|
| `config.py` + `.env` | ✅ | Key `ZCE_*` (RFC bagian 14), selaras keduanya |
| `src/core/llm_client.py` | ✅ Fase 3 | Zone table + distribusi tape per peran |
| `src/core/cli_theme.py` & `main.py` | ⚪ opsional | readiness di HUD; rotasi refresh ZCE di loop utama (panggil tiap siklus 60s) |
| `src/core/telegram_bot.py` | ⚪ Fase 3 opsional | `/radar` menampilkan readiness + top klaster |
| `src/analytics/macro_strategic_engine.py` | ✅ Fase 2 | Konsumsi ZoneMapResult (Blok A/B) |
| `src/core/risk_engine.py` & `position_manager.py` | 🔍 verifikasi | Tidak berubah; pastikan TP/SL tetap lewat `consensus._apply_sltp_rules` |
| `tests/test_*.py` | ✅ | `test_zone_confluence_engine.py` + regression fixtures |
| `docs/CHANGELOG_SEPTEMBER_2026.md` & `AGENTS.md` | ✅ | Dicatat per fase setelah PASS |

> `market_scanner.py` (Stage 1) tidak masuk daftar 8 file AGENTS.md, tetapi merupakan file inti yang diubah di Fase 3 — ditambahkan eksplisit di sini.

---

## Risiko & Mitigasi

| Risiko | Mitigasi |
|---|---|
| Parity gagal (perilaku bergeser diam-diam) | Berhenti di Fase 1, selidiki asumsi window, jangan lanjut |
| Biaya komputasi grid (18+ sel/simbol) | Benchmark Fase 1; rotasi 6 simbol/siklus; FRVP NumPy; cache per `(sym, tf, bar_time)` |
| Double fetch MT5 | ZCE pemilik rate cache; MSE/scanner baca dari sana |
| FVG primitif baru tidak terbukti | Shadow mode: ukur kontribusi terpisah sebelum dipakai gate |
| Konsumen field `MacroStrategicDirective` rusak | Kontrak dataclass tidak berubah; konsumen field tidak tersentuh |

---

## Urutan Eksekusi yang Diminta ke User

Batch pertama (butuh persetujuan):
1. `config.py` + `.env`: tambah key `ZCE_*` (semua off).
2. `src/analytics/zone_confluence_engine.py` mode legacy.
3. `tests/test_zone_confluence_engine.py` (parity + sintetik).
4. Jalankan `python -m pytest tests/ -q` → lapor hasil.
