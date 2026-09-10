# Rekonsiliasi: Session De-Risk Sizing vs. Session-Adaptive Decoupling & ZCE Restoration

**Tanggal**: 2026-09-10
**Status**: Dokumen rekonsiliasi — untuk dibaca lintas-agent
**Branch**: `quant-trade-noAI`

> **Tujuan dokumen ini.** Dua dokumen desain lahir di hari yang sama dan terlihat bersaing: satu *Implementation Plan* (de-risk sizing per sesi) dan satu *Design Specification* (session-adaptive decoupling + ZCE restoration). Dokumen ini memverifikasi keduanya terhadap data asli, memetakan mana yang bertentangan, dan menyusun urutan kerja tunggal yang tidak saling menabrak. **Baca dokumen ini sebelum mengeksekusi salah satu dari keduanya.**

---

## 0. Ringkasan Keputusan (TL;DR)

| Item | Verdict |
|---|---|
| Angka empiris di Design Spec | ✅ **Akurat** — terverifikasi identik dengan telemetry |
| Diagnosis ZCE chamber shrinkage + CBSS runway deadlock | ✅ **Benar**, akar masalah nyata |
| Veto mutlak M3 di NY | ⚠️ **Tunda** — bersandar pada n=5 (badan bukti terlalu tipis) |
| Gate CSM untuk M3 London | ❌ **Salah sasaran** — London bukan masalah win rate, tapi **asimetri besar loss** |
| Restorasi `min_ch` ke 15p kaku | ❌ **Regresi** — mengulang bug yang diperbaiki di #82 |
| Runway decoupling CBSS (M2/M3 = 0.60×) | ✅ **Ambil** |
| Dashboard visibility sync | ✅ **Ambil** |
| Session lot multiplier (NY 0.5× / London 0.75×) | ✅ **Ambil — prioritas tertinggi**, tidak ada di spec |

**Kesimpulan:** kedua dokumen **tidak bersaing**. Spec menangani paruh **supply** (gate entry — siapa yang boleh masuk). Plan menangani paruh **size** (berapa besar risiko per trade). Data menunjukkan paruh **size** yang lebih langsung menjelaskan kerugian London & NY.

---

## 1. Definisi Dokumen yang Direkonsiliasi

1. **PLAN-SIZING** — `~/.commandcode/plans/session-derisk-sizing.md`
   Session-aware de-risk sizing. Mekanisme `effective = min(volatility_multiplier, session_cap)`.
   Cap: Asia 1.2 / London 0.75 / NY 0.50. Sudah **approved**.

2. **SPEC-DECOUPLE** — `docs/superpowers/specs/2026-09-10-session-adaptive-decoupling-and-zce-restoration-design.md`
   Session-Adaptive Mechanism Matrix + ZCE Natural Chamber Restoration + dashboard sync. Status: Approved (brainstorming).

---

## 2. Data Terverifikasi (Sumber Tunggal Kebenaran)

Sumber: `data/trade_lifecycle_telemetry.json`, status `CLOSED`, bucketing jam berdasarkan `open_time` (fallback `close_time`).

**Catatan kejujuran data:** sampel kecil dan mencampur era demo/live. **Indikatif, bukan definitif.** Jangan tarik klaim edge statistis dari sini.

### 2.1 Per Sesi

| Sesi | N | WinRate | Net PnL | Avg/trade |
|---|---|---|---|---|
| ASIA (07–14) | 30 | 70.0% | **+$460.98** | +$15.37 |
| LONDON (14–18) | 32 | 56.2% | **−$757.80** | −$23.68 |
| NY (18–24) | 19 | 52.6% | **−$292.32** | −$15.39 |

### 2.2 Per Sesi × Mekanisme (terverifikasi identik dengan SPEC §1.1)

| Sesi | Mek | N | W | L | WR% | Net $ |
|---|---|---|---|---|---|---|
| ASIA | M1 | 3 | 2 | 1 | 66.7 | +43.93 |
| ASIA | M2 | 11 | 7 | 4 | 63.6 | +134.34 |
| ASIA | M3 | 14 | 11 | 3 | 78.6 | +318.46 |
| LONDON | M1 | 2 | 1 | 1 | 50.0 | −65.94 |
| LONDON | M2 | 14 | 6 | 8 | **42.9** | **−424.83** |
| LONDON | M3 | 13 | 8 | 5 | **61.5** | **−359.76** |
| NY | M1 | 4 | 2 | 2 | 50.0 | −95.48 |
| NY | M2 | 9 | 7 | 2 | 77.8 | +59.09 |
| NY | M3 | 5 | 1 | 4 | **20.0** | **−233.62** |

> SPEC §1.1 dinyatakan **lolos verifikasi**: seluruh angka (termasuk ASIA M3 78.6%/+$318.46, London M2 42.9%/−$424.83, NY M3 20.0%/−$233.62) cocok persis. Kredit untuk akurasi pengambilan data.

### 2.3 Distribusi Payout London (temuan kunci, tidak ada di SPEC)

London: 18 win, 14 loss.

```
Win  (n=18): +136.0, +86.9, +68.5, +54.9, +49.0, +47.0, +30.1, +27.5, +26.7,
             +17.2, +12.3, +10.8, +10.3, +10.2, +6.0, +4.4, +4.3, +1.7
             → rata-rata +$33.5

Loss (n=14): −0.65, −40.7, −49.3, −52.2, −55.4, −72.6, −112.6, −114.9,
             −121.7, −136.5, −147.4, −151.9, −152.1, −153.6
             → rata-rata −$97.3
```

**Rasio rata-rata loss : win ≈ 2.9 : 1.** Enam loss terbesar berada di band −$112 s/d −$153.

**Implikasi:** London M3 punya WR **positif (61.5%)** namun net **negatif (−$359.76)**. Penyebabnya bukan kualitas entry, melainkan **ukuran loss yang membengkak**. Gate CSM tidak menyentuh variabel ini; **sizing menyentuh langsung.**

NY M3: 5 trade (1W-4L). Wilson 95% CI untuk 1/5 ≈ [3.6%, 62.5%] — **tidak cukup untuk memisahkan dari WR yang sehat.**

---

## 3. Adjudikasi Poin-per-Poin terhadap SPEC-DECOUPLE

### 3.1 ✅ DITERIMA — ZCE Chamber Shrinkage sebagai akar masalah

SPEC §1.2 poin 1 benar. Rework #82 mengubah `min_ch` dari `max(0.60*ATR, 15p)` → `max(0.50*ATR, min(15p, 0.75*ATR))`. Chamber menyempit (AUDCHF ~5p, EURGBP ~3p, EURUSD ~6–15p). Efek berantai ke 4 besaran CBSS (runway_atr ⬇, is_at_wall_g3 ⬆, is_tight_chamber ⬆, BSSI ⬆) — lihat §4.

### 3.2 ✅ DITERIMA — CBSS Runway Deadlock (4.285 baris block)

Terverifikasi: `[CBSS RUNWAY]` = 4.285 kemunculan di `data/gate_debug.log`. Chamber 0.8× ATR secara matematis tidak bisa memenuhi runway 1.20× ATR → deadlock struktural. Nyata.

### 3.3 ✅ DITERIMA (dengan syarat) — Runway Decoupling CBSS

SPEC §3.3: M4 tetap 1.20× ATR; M2/M3 turun ke 0.60× ATR. **Setuju dengan arahnya.** Chamber sempit wajar untuk mean-reversion intraday; memaksa 1.20× ATR memang salah untuk M2/M3.
**Syarat:** satukan ambangnya dengan relax-NY yang sudah ada (`market_scanner.py:3171`, 0.75× ATR) — jangan tambah angka ketiga yang berbeda. Pilih **satu** ambang untuk M2/M3 dan hapus yang redundant.

### 3.4 ❌ DITOLAK — Veto mutlak M3 di NY

SPEC §3.2 poin 1: blokir total M3 saat `hour >= 18`.
**Alasan tolak:** bersandar pada n=5. Memenuhi syarat untuk *prior*, tidak untuk *absolute veto*. AGENTS.md rule #6 menetapkan klaim edge minimal 60–100 trade.
**Ganti dengan:** route M3 NY ke **paper trade** (mekanisme `SKIPPED_*` yang sudah ada) sambil mengumpulkan sampel. Jika setelah ≥60 trade WR tetap ≤30%, baru naikkan jadi veto keras. Ini mempertahankan data-collection tanpa mempertaruhkan modal.

### 3.5 ❌ DITOLAK — Gate CSM untuk M3 London

SPEC §3.2 poin 2: M3 London wajib `|CSM Delta| >= 1.50`.
**Alasan tolak:** didiagnosis dari variabel yang salah. London M3 WR = 61.5% (sehat). Yang rusak adalah **ukuran loss** (§2.3). Menambah filter CSM akan mengurangi jumlah entry, tidak memperkecil loss per entry — bahkan bisa memperparah dengan memblokir sebagian winner (+$54.9 s/d +$136).
**Ganti dengan:** de-risk sizing London (PLAN-SIZING). Jika tetap ingin guard, guard berbasis **risiko**, bukan momentum.

### 3.6 ❌ DITOLAK — Restorasi `min_ch` / `min_sep` ke 15p kaku

SPEC §3.1: `min_ch = max(0.60*ATR, 15p)`, `min_sep = max(0.50*ATR, 15p)`.
**Alasan tolak:** mengulang bug yang diperbaiki #82. Floor 15p kaku = 2.3× ATR pada AUDCHF, membuang benteng makro di 17 simbol low-beta. Tambalan "inject psychological station" (SPEC §3.1) = padding sintetis yang justru dihapus di #81.
**Ganti dengan:** pertahankan formula adaptif #82, tapi tambahkan **floor ATR-relative** yang tidak membuang benteng makro — mis. floor absolut kecil (5–8p) PLUS jaminan bahwa kandidat bergrade `GRADE_3_MACRO` tidak boleh di-drop oleh aturan jarak.

### 3.7 ✅ DITERIMA — Dynamic Tokyo Midday Lull Threshold

SPEC §3.2 poin 3: `lull_min_pips = max(0.40 * atr_pips, 12.0)` menggantikan 25p statis. Arahnya benar — 25p statis memblokir pair tenang. **Sekalian:** keluarkan Lull dari blok CBSS (`market_scanner.py:3186`) karena itu logika sesi, bukan logika basket.

### 3.8 ✅ DITERIMA — Dashboard Visibility Sync

SPEC §3.4 (pinning F1/C1 ke `macro_cache`, chamber height, bilateral runway, badge sesi, konsistensi Gate 3). Berguna dan tidak konflik.

### 3.9 ⚠️ TIDAK DAPAT DIVERIFIKASI — `measure_all_runways.py`

SPEC §4.2 merujuk skrip ini. **File tidak ditemukan di repo** (`**/measure_all_runways.py` → tidak ada). Harap buat dulu sebelum dipakai sebagai kriteria verifikasi.

---

## 4. Rantai Coupling CBSS ↔ ZCE (konteks untuk keduanya)

Terverifikasi di source: `basket_sync_engine.py` **read-only** terhadap `macro_cache`/MSE/ZCE (tidak ada satu pun assignment balik; import hanya `config` + `logging`). Alirannya **satu arah**:

```
ZCE (geometri chamber) → MSE directive → macro_cache → CBSS (semua threshold)
```

Empat besaran CBSS yang diturunkan langsung dari geometri chamber:

| Besaran CBSS | Rumus | Efek chamber sempit |
|---|---|---|
| `runway_atr` | `dist ÷ ATR` | ⬇ kecil → kena gate `CBSS_MIN_RUNWAY_ATR` |
| `is_at_wall_g3` | `dist ÷ ATR ≤ 0.35` | ⬆ lebih sering → G3 veto |
| `is_tight_chamber` | `(C1−F1) ÷ ATR < 1.00` | ⬆ → bobot champion score dipotong |
| BSSI saturation | proporsi pair `runway ≤ 0.35×ATR` | ⬆ ≥0.70 → hard-block continuation |

**Konsekuensi desain:** satu perubahan ZCE mengubah **empat gate CBSS sekaligus**. Ini bukan bug CBSS — ini sifat arsitektur. Setiap perubahan ZCE harus dinilai dampaknya ke keempat besaran ini.

### 4.1 Cacat tambahan yang ditemukan (bukan di kedua dokumen)

- **`filter_and_rank_batch_candidates` session-blind.** Menerima `hour_wib` (`basket_sync_engine.py:613`) tapi **tidak pernah dipakai** di body, padahal `market_scanner.py:4776` mengirimnya.
- **Inkonsistensi ambang.** Relax NY di `market_scanner.py:3171` = 0.75× ATR, tetapi CBSS tetap 1.20× ATR. Dua lapisan memakai angka berbeda di jam yang sama.

---

## 5. Urutan Kerja Tunggal (tidak saling menabrak)

**FASE 1 — Size (PLAN-SIZING), prioritas tertinggi.**
Alasan: bug terverifikasi, dampak langsung ke London & NY, perubahan terkecil, tidak menyentuh geometri ZCE.
- `risk_engine.py`: `effective = min(vol_mult, session_cap)`; perbaiki fallback bocor (baris 443); overlap → ambil **terendah** (baris 889–908).
- `config.py` + `.env`: `SESSION_LONDON_LOT_MULT = 0.75` (dua file, AGENTS rule #2).
- `dashboard.py:1500-1501` + test. Detail lengkap: `~/.commandcode/plans/session-derisk-sizing.md`.

**FASE 2 — Runway decoupling (SPEC §3.3), setelah Fase 1 stabil.**
- Samakan ambang M2/M3 pada **satu** nilai (0.60× ATR), hapus/konsolidasikan relax-NY 0.75×.
- Implementasikan `hour_wib` yang mati di `filter_and_rank_batch_candidates`.
- Keluarkan Tokyo Lull dari blok CBSS → ke layer sesi.

**FASE 3 — Dynamic Lull + dashboard sync (SPEC §3.2 poin 3, §3.4).**

**FASE 4 — NY M3 sebagai paper-only (bukan veto), kumpulkan sampel.**
- Route ke `SKIPPED_*` paper trade; evaluasi ulang setelah ≥60 trade.

**JANGAN DILAKUKAN (tanpa data baru ≥60 trade):**
- Veto mutlak M3 NY (SPEC §3.2 poin 1).
- CSM gate untuk M3 London (SPEC §3.2 poin 2).
- Restorasi `min_ch`/`min_sep` ke 15p kaku (SPEC §3.1).
- Revert rework #82.

---

## 6. Item Terbuka / Butuh Data

1. Uji Conditional Probability sesi (Newcombe/Wilson) dengan sampel ≥60 trade per sesi sebelum klaim edge apa pun.
2. Kuantifikasi apakah narrowing #82 benar-benar menambah blokir nyata vs sebelum `06189ac` (hitung skip-rate `CBSS RUNWAY` per commit dari `gate_debug.log`).
3. Apakah clamp `volume_min` (0.01 lot) menelan efek de-risking pada akun berukuran sekarang — perlu diukur, bukan diasumsikan.
4. Buat `measure_all_runways.py` sebelum dipakai sebagai gate verifikasi.

---

## 7. Aturan Main untuk Agent yang Mengeksekusi

1. `.env` adalah single source of truth — setiap perubahan config **wajib** dua tempat (`config.py` + `.env`).
2. Jangan ubah parameter risiko yang sudah mapan tanpa bukti (lot minimum, magic, SL/TP per-simbol).
3. Setiap klaim edge wajib uji terhadap model memoryless (Wilson CI + Chi-Square) — n=5 bukan bukti.
4. Verifikasi dulu (grep source), jangan mengandalkan ringkasan dokumen ini.
5. Setelah setiap fase: jalankan full test suite dan pastikan tetap hijau.
