# Riset Backtest Agustus 2026 — Trend-Following Gagal, Horn Bottoms/Tops Menang

> Tanggal: 20 Agustus 2026
> Data: broker VTMarkets (live), maksimal **~3 tahun** (Mei 2022 – Agustus 2026) — 5 tahun & 4 tahun TIDAK tersedia di server broker
> Metodologi umum: n≥100, WR>50%, p<0.05 (z-test), EV>0, CI95% batas bawah >0, **spread broker dipotong** dari tiap trade, entry di open bar berikutnya (no lookahead)
> Skrip sumber: `scratch/trend_following_backtest.py`, `scratch/pyramiding_h4_backtest.py`, `scratch/notebooklm_strategies_backtest.py`, `scratch/s9_retest_backtest.py`, `scratch/s9_filters_backtest.py`, `scratch/xau_tf_compare.py`, `scratch/verify_notebooklm_edges.py`

---

# ⚠️ ERRATUM PENTING (20 Agustus, sore) — S9 BUKAN EDGE, Backtest Buku Cacat

**Setelah audit lanjutan, ditemukan BUG PENGUKURAN EV di seluruh backtest strategi buku (NotebookLM):**
`simulate_exit()` di `scratch/notebooklm_strategies_backtest.py` mengembalikan **`+1.0R` tetap** setiap kali TP hit —
tanpa menghitung jarak TP aktual. Ini asumsi benar untuk strategi **R:R tetap** (TP = entry ± rr×SL), tapi **SALAH
total untuk strategi fixed-TP seperti S9** (TP = leher + tinggi pola).

**Kenapa fatal untuk S9:** entry terjadi SETELAH breakout kuat (open bar berikutnya sudah di atas leher),
jadi jarak entry→TP aktual cuma **~0.22×SL** (diukur dari distribusi R:R aktual, median 0.24). WR 79% itu
"banyak menang kecil" — dikalahkan sekali kalah besar (SL 1×ATR penuh). Backtest lama menghitung menang kecil
itu sebagai +1.0R → EV +0.58 palsu.

**Hasil ulang dengan R aktual (semua strategi, semua pair, spread dipotong):**

| Strategi | EV lama (bug) | EV aktual | CI95% low | Verdict |
|---|---|---|---|---|
| **S9 Horn** | +0.505 | **−0.016** | −0.030 | ❌ BUKAN edge |
| S2 Break-Hook-Go | +0.159 | +0.005 | −0.037 | ❌ bukan edge |
| S3 Buildup | +0.150 | +0.060 | −0.063 | ❌ bukan edge |
| S5 Liquidity FBO | −0.410 | +0.005 | −0.031 | ⚠️ nol, bukan anti-edge |
| S1/S4/S6/S10 | negatif | ~0 | <0 | ❌ tetap bukan edge |

**Kesimpulan erratum: SEMUA 10 strategi buku = NO EDGE** (CI95% bawah < 0). Semua angka S9 di dokumen
di bawah ini (WR 75-79%, EV +0.5, filter strong_close, XAU H1 comparison) **TIDAK VALID** — hasil artefak bug.
Jangan dipakai untuk integrasi bot. **Detector S9 + whisper sudah DIHAPUS** dari `pattern_detector.py`.

**Yang TETAP VALID dari riset ini:**
- Backtest 1 (trend-following) & Backtest 2 (pyramiding) — memakai R:R tetap, tidak kena bug → kesimpulan "gagal" tetap benar.
- Riset FX bearish NY (16-18 Agustus, `whisper_registry.json`) — EV dihitung matematis `WR×rr−(1−WR)−spread` per R:R tetap → **valid**.
- XAU Donchian BUY NY (17 Agustus) — R:R 1:1 → **valid**.

---

# 🔄 UPDATE 20 Agustus (malam) — S9 + HTF Structural Target = EDGE VALID (GBPUSD saja)

**Revisi SEBAGIAN dari erratum di atas.** Erratum menyatakan S9 bukan edge — itu benar untuk **exit rule buku**
(TP = neckline + height, yang menghasilkan R aktual ~0.22). Tapi setelah exit rule diganti sesuai ajaran buku
**Maximum Price Objective** (target level struktural, bukan tinggi pola), S9 **terbukti edge di GBPUSD**.

## Verifikasi & reproduksi

- Sumber klaim: `scratch/test_s9_htf_targets.py` (laporan revisi audit user) — **angka direproduksi 100% identik**
  (GBPUSD `htf_structural` n=314, WR 42%, EV +0.187; `rr_2.0` n=306, EV +0.176; XAU `rr_2.0` n=402, EV +0.037).
- **Audit metodologi script lama** (`scratch/verify_s9_htf.py`): 2 kelemahan ditemukan —
  (1) trade timeout 200 bar DIBUANG (bias seleksi), (2) `h4_high` rolling50 include high bar entry (win instan).
  **Setelah kedua-nya diperbaiki** (timeout dihitung pnl aktual, TP pakai rolling50 shift(1) = level yang sudah
  terbentuk sebelum entry), edge GBPUSD **tidak hilang, malah naik tipis**: EV **+0.196**, CI95% low **+0.034** ✅.

## Hasil final verifikasi (R aktual, timeout dihitung, spread dipotong)

| Simbol | n | WR | EV | CI95% low | Verdict |
|---|---|---|---|---|---|
| **GBPUSD-ECNc** | 322 | 42.9% | **+0.196** | **+0.034** | 🟢 **EDGE (signifikan)** |
| XAUUSD-ECNc | 416 | 38.9% | +0.023 | −0.102 | ❌ bukan edge |
| 7 pair cross (CADCHF, AUDCAD, dll) | — | — | negatif | <0 | ❌ eksklusi benar |

**Stabilitas tahunan GBPUSD: 5/5 tahun positif** — 2022 +0.564 (CI_low +0.089 ✅), 2023 +0.072, 2024 +0.137,
2025 +0.166, 2026 +0.098. XAU: 3/5 tahun negatif (2022 −0.071, 2023 −0.155, 2024 −0.018) → klaim "XAU profitable"
di laporan user = **noise, jangan dipakai**.

**Catatan teknis**: label "H4 swing high/low" di script lama keliru — implementasinya `rolling(50).max()` **bar H1**
(≈2 hari), bukan data H4. Hasil tetap valid sebagai "target level resistance 2-hari + floor R:R 1.5".

## Backtest trailing & BEP versi buku — SEMUA GAGAL (scratch/s9_trailing_backtest.py)

Aturan buku (Edianto Ong / Rayner Teo: "let profits run" via 20 EMA trailing / higher low + 1×ATR buffer)
diuji bar-by-bar pada GBPUSD S9. **Fixed TP structural tetap juara; semua proteksi posisi memangkas edge:**

| Exit rule | SL% | Trail/BEP% | TP% | WR | EV | CI95% low | Avg win |
|---|---|---|---|---|---|---|---|
| **Fixed TP structural** (floor R:R 1.5) | 57% | — | 41% | 42.9% | **+0.196** | +0.034 | +1.78R |
| BEP @35% TP | 90% | — | 10% | 9.9% | +0.066 | −0.133 | +4.19R |
| BEP @65% TP | 86% | — | 14% | 13.0% | +0.027 | −0.185 | +3.88R |
| Trail EMA20 (close < EMA20) | 7% | 93% | — | 31.1% | −0.045 | −0.132 | +0.81R |
| TP min → lalu trail EMA20 | 50% | 50% | — | 35.7% | −0.022 | −0.118 | +0.83R |
| Trail structure + 1×ATR | 100% | — | — | 35.7% | +0.033 | −0.098 | +1.12R |
| Trail EMA20 + TP structural | 26% | 60% | 14% | 30.1% | −0.004 | −0.085 | +0.93R |

**Insight kunci (kontra-intuitif):**
- **"BEP/trailing lebih sering daripada SL" TIDAK menjamin untung.** Trail EMA20: SL cuma 7% (93% exit trailing)
  tapi EV tetap negatif — trailing exit dini memotong avg win 1.78R → 0.81R (hold 12 jam vs 42 jam).
- **Fixed TP justru "sering kena SL" (57%) tapi EV +0.196** — yang menentukan expectancy
  (`WR×avg_win − (1−WR)×avg_loss`), bukan frekuensi SL.
- **BEP paling merusak**: mengubah win 1.78R menjadi 0R → WR sejati 42.9% → 9.9%, EV +0.196 → +0.066 (35%).
  Karena avg win > avg loss, memotong win lebih mahal daripada menahan loss.

**Koreksi bug internal**: hasil awal `trail_struct_atr` −1.000 WR 0% itu artefak script saya sendiri
(SL hit di-hardcode `r=-1.0`, padahal SL trailing yang sudah naik melewati entry harus dihitung profit).
Setelah diperbaiki: +0.033 (tetap tidak signifikan).

## Backtest matrix BEP/trailing — keputusan final (scratch/bep_trail_matrix.py, S9 BUY GBPUSD n=174)

Jawaban atas "berapa jarak trailing yang paling cocok, 10 pips? 20 pips? tergantung pair?" — baseline
(tanpa BEP/trailing) = +0.302. SEMUA kombinasi menurunkan EV, tapi ada yang jauh lebih hemat dari yang lain:

| Konfigurasi | EV | CI95% low | Catatan |
|---|---|---|---|
| **Baseline (tanpa BEP/trailing)** | **+0.302** | +0.079 | acuan |
| BEP 35% TP | +0.158 | −0.040 | paling merusak |
| BEP 50% TP | +0.205 | — | |
| BEP 65% TP | +0.222 | — | lebih telat lebih baik |
| **TRAIL act70 + 0.5×ATR** | **+0.272** | +0.076 | 🏆 terbaik, nyaris setara baseline |
| TRAIL act58 + 0.5×ATR | +0.197 | — | activation 58% kurang optimal dari 70% |
| TRAIL act58 + 10 pips | +0.180 | — | fixed pips inferior dari ATR |
| TRAIL act58 + 20 pips | +0.128 | — | |
| ADAPTIVE range (ide user) | +0.041 | — | paling merusak — data bilang kebalikannya |
| BEP35 + TRAIL58 atr1.0 (≈ setting bot lama) | +0.092 | — | jelek |

**Keputusan user (20 Agustus):** BEP **58% TP** (kompromi "jangan telat banget", padding komisi round-trip
dipertahankan) + trailing activation **70% TP** dengan distance **KONSTAN 0.5×ATR(14)** dari harga ekstrem
(bukan SL-progressive). **Diimplementasikan & teruji 15/15 PASS** (`scratch/test_bep_trail_global.py`) —
detail di AGENTS.md "Perubahan 20 Agustus (lanjutan malam) — Refactor GLOBAL BEP/Trailing".

## Status

- **S9-GBPUSD (entry horn breakout + TP structural, floor R:R 1.5) = kandidat edge terverifikasi**
  (EV +0.196, CI_low +0.034, 5/5 tahun positif, profil risiko sehat: avg win 1.78R / avg loss 1.0R, bukan lotere).
- **SUDAH diintegrasikan ke bot** sebagai whisper di `pattern_detector.py` (`_check_s9_structural_breakout`,
  commit `38ec5bf`, 20 Agu malam). Definisi mirror persis backtest (valley flat 0.25×ATR, neckline = high
  antar-valley, jarak ≤ 10 bar, gap-up + close > neckline + strong close 20%, SL = min(L1,L2) − 1.0×ATR).
  Hanya **GBPUSD BUY-only** (SELL EV +0.071 tidak signifikan, tidak di-whisper). Tanpa filter session
  (konsisten backtest: 5/5 tahun positif di semua jam). Whisper pakai angka BUY-only dari
  `bep_trail_matrix.py` baseline: **n=174, WR 45.4%, EV +0.302, CI_low +0.067** (angka n=322/EV +0.196
  di tabel verifikasi = BUY+SELL gabungan). Teks whisper menyatakan eksplisit
  *"Historical probability context only — NOT a directive"* — tetap guardrail di prompt, LLM pegang keputusan.
- Skrip: `scratch/test_s9_htf_targets.py` (sumber klaim), `scratch/verify_s9_htf.py` (audit),
  `scratch/s9_trailing_backtest.py` (trailing/BEP), `scratch/bep_trail_matrix.py` (sumber angka BUY-only),
  `scratch/debug_trail_struct.py`.

---

1. **Trend-following murni TIDAK punya edge di FX H1** — 10 strategi (Donchian, EMA cross, ADX, Supertrend, NR7, Inside Bar) semua EV negatif (WR 44–49%).
2. **Pyramiding H4 juga gagal** — 0 dari 18 varian lolos; pyramiding justru memperbesar loss vs posisi tunggal.
3. ~~**S9 Horn Bottoms/Tops = edge terkuat**~~ → **DIBATALKAN oleh erratum** (lihat di atas): EV aktual −0.016, semua 10 strategi buku NO EDGE.
4. ~~**Filter strong_close**~~ → ikut gugur (bagian dari S9).
5. **S5 Liquidity False Breakout** — ternyata juga nol dengan R aktual (+0.005), bukan anti-edge. Tetap jangan dipakai (nol = buang-buang spread).
6. **XAU H1 vs M30** — perbandingan S9 tidak relevan lagi (edge-nya tidak ada); keputusan timeframe XAU kembali ke riset lain yang valid.

---

## Ketersediaan Data

| Symbol | TF | Tahun | Bars | Spread (pts) |
|---|---|---|---|---|
| GBPUSD-ECNc | H1 | 3.01 | 26.402 | 2 |
| USDCAD-ECNc | H1 | 3.01 | 26.401 | 0 |
| EURJPY-ECNc | H1 | 3.01 | 26.401 | 1 |
| GBPAUD-ECNc | H1 | 3.01 | 26.401 | 5 |
| AUDCAD-ECNc | H1 | 3.01 | 26.402 | 3 |
| EURCHF-ECNc | H1 | 3.01 | 26.401 | 0 |
| AUDCHF-ECNc | H1 | 3.01 | 26.402 | 0 |
| CADCHF-ECNc | H1 | 3.01 | 26.402 | 1 |
| XAUUSD-ECNc | M30/H1/H4 | 2.86 | 50.161 / 25.094 / 6.568 | 10–11 |

**Catatan penting:** broker cuma menyimpan ~3 tahun H1 (sama seperti XAU M30 yang mulai Mei 2022). Permintaan 5/4 tahun → fallback otomatis ke 3 tahun. `copy_rates_from_pos` di atas 50.000 bar bisa return None (batas request).

---

## Backtest 1 — Trend-Following FX H1 (10 strategi)

`scratch/trend_following_backtest.py` — SL = 1×ATR14, R:R 1:1/1.5/2, max hold 300 bar.

### Hasil agregat (R:R 1:1, semua filter)

| Strategy | Total trades | WR% | Avg EV |
|---|---|---|---|
| ADX≥25 + EMA50 Dir | 350.868 | 48.8% | −0.037 |
| Donchian20 Breakout | 85.245 | 45.6% | −0.100 |
| Donchian100 Breakout | 36.008 | 45.5% | −0.100 |
| Donchian50 Breakout | 51.309 | 45.4% | −0.105 |
| EMA20/50 Cross | 14.961 | 47.8% | −0.053 |
| EMA50/200 Cross | 1.577 | 46.6% | −0.079 |
| NR7 Breakout | 64.272 | 44.4% | −0.110 |
| Inside Bar Breakout | 56.106 | 46.8% | −0.071 |
| Supertrend 10/3 | 19.721 | 47.3% | −0.066 |
| Supertrend 21/2 | 36.073 | 46.8% | −0.075 |

**Semua EV negatif.** Spread cuma ~1–2% dari jarak SL (bukan penyebab); penyebabnya WR < 50% murni.

### Edge tipis yang lolos (semua R:R 1:1 saja, EV kecil)

| Symbol | Strategy | R:R | Filter | n | WR% | EV | CI_low |
|---|---|---|---|---|---|---|---|
| GBPAUD | Donchian100 | 1.0 | regime=ranging | 183 | 59.0 | +0.161 | 0.018 |
| USDCAD | ADX≥25+EMA50 | 1.0 | session=asia | 5.051 | 53.8 | +0.076 | 0.048 |
| CADCHF | ADX≥25+EMA50 | 1.0 | htf=down | 7.466 | 52.3 | +0.046 | 0.024 |
| EURCHF | ADX≥25+EMA50 | 1.0 | htf=down | 8.083 | 51.9 | +0.039 | 0.017 |

Tidak ada yang bertahan di R:R 1.5/2.0. Kesimpulan: trend-following murni tidak viable di FX H1.

---

## Backtest 2 — Pyramiding H4 (8 FX + XAU, 18 varian)

`scratch/pyramiding_h4_backtest.py` — entry tiap swing fractal 2-bar, exit semua saat EMA50 cross, SL di swing, max posisi paralel 1/3/unlimited, TP none/1.0/2.0, ADX on/off.

### Hasil: **0 dari 18 varian lolos** — semua EV negatif

| max_pos | TP | ADX | Total trades | Avg EV | #PASS |
|---|---|---|---|---|---|
| 1 | 1.0 | off | 8.308 | −0.136 | 0 |
| 1 | 2.0 | off | 6.170 | −0.376 | 0 |
| 1 | none | off | 3.916 | −0.162 | 0 |
| 3 | 1.0 | off | 13.648 | −0.173 | 0 |
| 3 | 2.0 | off | 12.496 | −0.436 | 0 |
| unlimited | 1.0 | off | 13.855 | −0.175 | 0 |
| unlimited | 2.0 | off | 13.855 | −0.443 | 0 |

Pola: pyramiding memperbesar loss (exit bareng saat reversal menghanguskan profit), TP 2.0 paling parah (jarang kesampean sebelum tren balik), ADX filter tidak menyelamatkan.

---

## Backtest 3 — 10 Strategi Buku (NotebookLM) — FX H1 + XAU M30

`scratch/notebooklm_strategies_backtest.py` — formulasi persis dari `docs/hasilnotebooklm.md` (koreksi bug #2 & #4), SL/TP sesuai buku, spread dipotong.

### Hasil agregat (semua simbol, semua filter)

| Strategy | Total trades | WR% | Avg EV | Verdict |
|---|---|---|---|---|
| **S9 Horn Bottoms/Tops** | 15.314 | **75.5%** | **+0.505** | ✅✅ EDGE |
| S2 Break-Hook-Go | 2.005 | 58.7% | +0.164 | ⚠️ lemah |
| S4 MA50+Bearish Engulfing | 40.044 | 41.1% | −0.188 | ❌ |
| S6 Inside Bar Fakey | 17.655 | 39.4% | −0.223 | ❌ |
| S10 21EMA Pullback+Pin | 4.587 | 39.5% | −0.225 | ❌ |
| S1 Supply&Demand Retest | 65.142 | 40.4% | −0.200 | ❌ |
| **S5 Liquidity False Breakout** | 19.760 | **29.5%** | **−0.411** | ❌❌ ANTI-EDGE |
| S7 Kennedy Gap | — | — | — | skip (butuh trendline) |
| S8 Dual Trendline Retest | — | — | — | skip (butuh trendline) |

### S9 Horn Bottoms/Tops — detail per simbol (ALL, tanpa filter)

| Symbol | TF | n | WR% | EV | CI_low |
|---|---|---|---|---|---|
| GBPUSD | H1 | 721 | 79.2 | +0.579 | 0.520 |
| USDCAD | H1 | 745 | 76.9 | +0.538 | 0.478 |
| EURJPY | H1 | 932 | 75.8 | +0.512 | 0.457 |
| GBPAUD | H1 | 831 | 75.0 | +0.493 | 0.434 |
| AUDCAD | H1 | 687 | 76.0 | +0.511 | 0.447 |
| EURCHF | H1 | 760 | 75.7 | +0.513 | 0.452 |
| AUDCHF | H1 | 705 | 71.5 | +0.430 | 0.363 |
| CADCHF | H1 | 690 | 71.7 | +0.430 | 0.363 |
| XAUUSD | M30 | 1.586 | 76.4 | +0.517 | 0.475 |

**Semua 9 aset lolos, semua sesi positif** (terbaik: London/NY). n total 7.657 dalam 3 tahun.

### Formulasi S9 Horn Bottoms (BUY) — yang diuji

```
1. Dua lembah sejajar: L1 & L2 (fractal 2-bar), jarak < 10 bar, |L1−L2| < 0.25×ATR
2. Ada puncak kecil di antara (leher / H_interim)
3. Konfirmasi: open gap-up  DAN  close > leher (breakout)
4. ENTRY: open bar berikutnya (breakout langsung, BUKAN retest)
5. SL = min(L1, L2) − 1×ATR
6. TP = leher + (leher − min(L1, L2))   [proyeksi setinggi pola]
```
Mirror untuk SELL (Horn Tops).

---

## Verifikasi Stabilitas Tahunan S9

`scratch/verify_notebooklm_edges.py` — edge wajib konsisten per tahun kalender, bukan numpuk 1 tahun.

**S9: konsisten di SEMUA 5 tahun (2022–2026) × 9 aset. Tidak ada satu tahun pun negatif.**

Contoh (WR% / EV per tahun):

| Symbol | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| GBPUSD | 84% / +0.68 | 78% / +0.56 | 79% / +0.58 | 76% / +0.52 | 81% / +0.62 |
| XAU M30 | 79% / +0.56 | 77% / +0.52 | 75% / +0.49 | 76% / +0.51 | 77% / +0.54 |
| CADCHF (terlemah) | 70% / +0.40 | 76% / +0.52 | 75% / +0.49 | 71% / +0.41 | 64% / +0.27 |

S2 BHG: positif mayoritas tahun tapi ada tahun negatif (EURCHF, GBPAUD) → belum layak.
S5: **anti-edge konsisten semua tahun** (EV −0.2 s/d −0.67).

---

## S9 Retest Version — TIDAK Lebih Baik

`scratch/s9_retest_backtest.py` — entry menunggu pullback ke area leher (±0.25 ATR, max 10 bar) alih-alih breakout langsung.

| Aset | Original WR/EV | Retest WR/EV | Sinyal |
|---|---|---|---|
| GBPUSD | 79.2% / +0.58 | 77.9% / +0.55 | 721 → 357 |
| EURCHF | 75.7% / +0.51 | 78.5% / +0.57 | 760 → 311 |
| GBPAUD | 75.0% / +0.49 | 78.3% / +0.56 | 831 → 387 |
| CADCHF | 71.7% / +0.44 | 76.0% / +0.52 | 690 → 271 |
| XAU M30 | 76.4% / +0.52 | 77.8% / +0.55 | 1.586 → 785 |

**Kesimpulan:** WR/EV hampir sama, tapi sinyal tinggal setengah (7.657 → 3.616). Edge ada di *pola* (double bottom/top), bukan cara entry. **Pakai original (breakout langsung).**

---

## S9 + Filter Buku — `strong_close` Pemenang

`scratch/s9_filters_backtest.py` — filter dari Rayner Teo (breakout guide) + Candlestick Bible, diterapkan pada S9.

| Filter | Total n | WR% | EV | Frekuensi | Verdict |
|---|---|---|---|---|---|
| baseline | 7.657 | 75.5% | +0.502 | ~150/bln | acuan |
| **strong_close** ✅ | 3.747 | **79.1%** | **+0.580** | ~74/bln | **BEST** |
| pin_L2 | 1.086 | 76.6% | +0.513 | ~21/bln | sedikit naik |
| engulf_L2 | 1.301 | 75.4% | +0.507 | ~26/bln | ~sama |
| not_overextended | 7.340 | 74.9% | +0.490 | ~144/bln | tidak membantu |
| buildup | 141 | 82.3% | +0.633 | ~3/bln | bagus tapi jarang |
| combo_rayner | 61 | 80.3% | +0.592 | ~1/bln | terlalu restriktif |
| combo_all | 0 | — | — | — | mati total |

**`strong_close`**: bar breakout harus close kuat (BUY: close di 20% area atas lilin / SELL: 20% area bawah) = "penolakan instan yang tegas". Semua 9 aset PASS. Konsisten dengan filosofi buku Horn.

Per simbol strong_close: EURCHF 81.2%, AUDCHF 80.9%, AUDCAD 80.4%, GBPUSD 83.2%, GBPAUD 79.2%, XAU 78.9%, USDCAD 79.5%, EURJPY 77.2%, CADCHF 72.5% (terlemah tapi positif).

---

## XAU: M30 vs H1 vs H4 — Edge TIDAK Berubah, Malah Naik Tipis

`scratch/xau_tf_compare.py` — menjawab pertanyaan "kalau XAU pindah H1, edgenya berubah?"

| TF | Varian | n | WR% | EV | Frekuensi/bulan |
|---|---|---|---|---|---|
| M30 | baseline | 1.586 | 76.4% | +0.517 | 31.2 |
| M30 | strong_close | 833 | 78.9% | +0.568 | 16.4 |
| **H1** | baseline | 815 | 77.9% | +0.552 | 16.0 |
| **H1** | **strong_close** | **416** | **80.0%** | **+0.595** | 8.2 |
| H4 | baseline | 183 | 78.1% | +0.560 | 3.6 |
| H4 | strong_close | 85 | 77.6% | +0.550 | 1.7 |

**Kesimpulan:** XAU H1 justru sedikit LEBIH BAGUS (WR 80.0% vs 78.9%, EV +0.595 vs +0.568) — edge tidak berubah, malah naik tipis. Trade-off: frekuensi turun setengah (16.4 → 8.2/bulan). H4 juga tetap positif tapi frekuensi terlalu jarang.

---

## Kesimpulan & Rekomendasi

1. **S9 Horn Bottoms/Tops + strong_close = edge terkuat yang pernah tervalidasi di proyek ini:**
   - WR ~79%, EV +0.58, konsisten 5 tahun × 9 aset, semua sesi
   - ~74 sinyal/bulan di seluruh pool (8 FX H1 + XAU) = ~3 sinyal/hari
   - Berlaku semua simbol — tidak tergantung sesi NY seperti whisper bearish
2. **XAU boleh pindah H1** tanpa kehilangan edge (frekuensi berkurang, kualitas naik tipis).
3. **Larangan baru:** S5 Liquidity False Breakout = anti-edge (WR 29.5%) — jangan pernah dijadikan sinyal/whisper.
4. Integrasi yang disarankan: detector S9+strong_close → whisper konteks LLM (guardrails-in-prompt, LLM tetap pegang keputusan), konsisten dengan filosofi paket anti-FOMC.

---

## Lampiran: File CSV mentah

- `scratch/results/trend_following_results.csv` (1.308 kombinasi)
- `scratch/results/pyramiding_h4_results.csv` (162 kombinasi)
- `scratch/results/notebooklm_strategies_results.csv`
- `scratch/results/s9_retest_results.csv`
- `scratch/results/s9_filter_results.csv`
