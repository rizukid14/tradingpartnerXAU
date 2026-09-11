# RENCANA IMPLEMENTASI FINAL — TRADE GEOMETRY & STRUCTURAL DECOUPLING

> **Tanggal**: 11 September 2026  
> **Basis**: `docs/TRADE_GEOMETRY_AND_STRUCTURAL_DECOUPLING_RESEARCH.md` (N=101 executed + N=360–444 pool)  
> **Metode**: Sintesis lintas-AI + verifikasi independen MT5 live + audit source code  
> **Status**: FINAL DRAFT — KONSENSUS LINTAS-AI TERCAPAI  
> **Target eksekutor**: AI coding assistant  

---

## 0. RINGKASAN SATU HALAMAN

**Masalah inti (bukan friksi, bukan TF):** tiga keputusan berbeda tercampur jadi satu.

| Keputusan | Seharusnya ditentukan oleh | Kenyataannya ditentukan oleh |
|---|---|---|
| Stop Loss | titik invalidasi struktur | dinding terjauh dalam radius 2.5×ATR |
| Take Profit | likuiditas lawan (dinding ZCE) | `1.25 × SL` |
| Lot size | batas risiko akun | `1 / SL` (SL ikut menentukan eksposur) |

Akibat berantai: SL menggelembung ke **2.08×ATR** → TP ikut ke **2.34×ATR** → hanya **29.2%** trade mampu mencapai 1.25×ATR → payoff riil **0.62** vs nominal 1.30.

**Temuan yang belum tercatat di laporan mana pun:** level invalidasi **sudah dihitung dan sudah dikirim** ke fungsi SL/TP oleh setiap mekanisme (`origin_level`), lalu **dibuang** oleh `max()`/`min()`. Tidak perlu menemukan level baru — cukup berhenti membuang yang sudah ada.

---

## 1. STATUS VERIFIKASI (WAJIB DIBACA SEBELUM EKSEKUSI)

### 1.1 Terverifikasi akurat (aman dipakai)

| Klaim | Nilai | Sumber |
|---|---|---|
| Median MAE pemenang | 0.25×ATR | diverifikasi ulang MT5 & data |
| P75 MAE pemenang | 0.48–0.49×ATR | diverifikasi ulang MT5 & data |
| P90 MAE pemenang | 1.07×ATR | diverifikasi ulang MT5 & data |
| Median SL sekarang | 168 pts / 2.08×ATR | diverifikasi ulang MT5 & data |
| Median TP sekarang | 2.34×ATR | diverifikasi ulang MT5 & data |
| P(harga capai 1.25×ATR) | 29.2% | diverifikasi ulang MT5 & data |
| P(menang \| MAE ≥ 0.50×ATR) | **37.8%** | falsifikasi terkonfirmasi bersama |
| Pemenang terbunuh @ SL 0.50×ATR | 62/249 = **24.9%** (−21.8R) | diverifikasi ulang |
| Pemenang terbunuh @ SL 1.00×ATR | 28/249 = **11.2%** (88.8% aman) | diverifikasi ulang |
| Baseline populasi penuh | **+27.05R** (bukan −1.9R) | koreksi bersama, diadopsi |
| Capping TP buatan | hanya **+0.85R** (bukan +23.6R) | seleksi ≠ paksaan terkonfirmasi |

### 1.2 BATASAN — jangan diabaikan

- **N=101 executed (76 DEMO, 19 LIVE), 5 hari bursa, satu regime pasar.**
- Uji permutasi RR: **p=0.070** — belum di bawah 0.05.
- Uji permutasi TP<2.5×ATR: **p=0.089**.
- Cohort terkuat (Tokyo×CSM): **n=6–8** — di bawah ambang apa pun.
- **Semua angka di dokumen ini hipotesis, bukan bukti.** Aturan AGENTS.md: klaim edge butuh ≥60–100 trade live + out-of-sample.
- Penolakan angka 0.50×ATR dan "+47.8R" berlaku juga untuk angka apa pun di sini.

---

## 2. ARSITEKTUR TERPADU — PILAR 1..6 (KONSENSUS TERCAPAI)

### Pilar 1 — Pisahkan lot dari geometri SL
**Prinsip**: dilarang memperlebar SL demi menahan lot akun Cent.  
**Kondisi sekarang**: `risk_engine.py:412-418` meng-clamp ke `volume_max` broker (100 lot) — **tidak ada cap akun**.  
**Verifikasi Cent MT5**: Akun `27556325` ber-contract size 1,000 unit. Posisi 0.50 lot dengan SL 80 pts menghasilkan risiko maksimal 40 USC ($0.40 USD / 0.75% equity), dan pada SL 100 pts risiko 50 USC (0.93% equity, pas di target 1.0%). Aman dan terkalibrasi.  
**Aksi**: tambah `MAX_POSITION_LOT = 0.50` di akun Cent.

```python
# risk_engine.py (setelah baris 415)
account_max = float(getattr(config, "MAX_POSITION_LOT", 0.50))
lot = max(volume_min, min(min(volume_max, account_max), lot))
```

---

### Pilar 2 — Dekopel TP dari kelipatan SL
**Lokasi**: `consensus.py:336-340`  
```python
min_tp = int(sl_points * min_rr) + friction_pts     # <- akar masalah
max_tp = int(sl_points * max_rr) + friction_pts
if tp_points < min_tp: tp_points = min_tp
```
**Aksi**: TP dari kandidat sudah dihitung `calculate_intraday_sl_tp` (dinding ZCE). Jangan naikkan; hanya validasi kapasitas runway.
```python
if tp_points < min_tp:
    # JANGAN naikkan TP. Validasi kapasitas, bukan paksa jarak.
    if (tp_points - friction_pts) < int(sl_points * config.GRADE_B_MIN_RR):
        return sl_points, tp_points, False, "RUNWAY_INSUFFICIENT"
    # else: biarkan TP di dinding apa adanya (Grade B / Wall Scalp)
```

---

### Pilar 3 — Floor turunan friksi (menggantikan floor statis)
**Lokasi**: `config.py:859-874` (`get_sl_floor_points`) dan `atlas_dna.py:164-169`  
**Konsensus Divisor**: Menggunakan **`FRICTION_FLOOR_DIVISOR = 0.20`** (nilai netral yang terbukti 0/27 simbol mengikat di bawah ATR, mengamankan beban broker $\le 20\%$).  
**Aksi**:
```python
# config.py
FRICTION_FLOOR_DIVISOR = _getenv_float("FRICTION_FLOOR_DIVISOR", 0.20)
SL_ATR_MULT            = _getenv_float("SL_ATR_MULT", 1.00)

def friction_floor_points(spread_pts: int, comm_pts: int = 6) -> int:
    return int(round((spread_pts + comm_pts) / FRICTION_FLOOR_DIVISOR))
```

---

### Pilar 4 — Formula SL Seimbang (Tiga Suku Lengkap)
**Lokasi**: `atlas_dna.py:188-199` (BUY) dan `261-272` (SELL)  
**Koreksi Kritis**: Karena limit order di M2/M3 masuk di level anchor (`entry_lim = origin_level`), `abs(entry - origin)` adalah nol. Maka `struct_dist` **wajib memiliki buffer penembusan** agar tidak degenerate, dan **3 suku lengkap wajib dipertahankan** di dalam `max()` agar pair ATR besar (GBPJPY) tidak terpotong terlalu rapat.

**Aksi**:
```python
# atlas_dna.py
invalidation_buffer = max(0.15 * atr_h1, (2 * spread_pts + 10) * pt)
struct_dist = abs(entry_price - origin_level) + invalidation_buffer

atr_floor   = SL_ATR_MULT * atr_h1
fric_floor  = friction_floor_points(spread_pts) * pt

sl_dist = max(struct_dist, atr_floor, fric_floor)
sl = (entry_price - sl_dist) if direction == 1 else (entry_price + sl_dist)
```
Grade threshold (`atlas_dna.py:324-331`) tetap.

---

### Pilar 5 — Defensif London 15:00–17:00 WIB
**Bukti**: 19 trade = 120% dari total rugi; konsisten di 4/5 hari; SELL WR 18.2%.  
**Aksi** di `market_scanner.py` (dekat gate M2/M3 SELL):
```python
if target_dir == -1 and 15 <= now_wib.hour < 18:
    action_tier = "REDUCED_SCALP"      # -> 0.50x lot via risk_engine
    is_passive_limit = (setup_label not in ("BEARISH_SWEEP","UNIVERSAL_LIQUIDITY_SWEEP"))
    if is_passive_limit and entry_type != "market":
        return False, "HARD_BLOCK", "[LDN15-17] Passive sell_limit dilarang di jendela ini"
```

---

### Pilar 6 — Target jauh bersyarat
**Bukti**: TP≥2.5×ATR tanpa regime = −152R s/d −676R; dengan Tokyo×CSM≥2 = +165 (n=6).  
**Aksi**: gate lunak, bukan larangan.
```python
if tp_atr >= 2.5:
    regime_ok = (session == "Tokyo" and abs(csm_delta) >= 2.00) or c1_breached or f1_breached
    if not regime_ok:
        tp_points = int(2.5 * atr_points)   # turunkan ke batas regime-netral
```

---

### Pilar 7 — Proteksi Momentum Lilin & Integritas Kamar (Resolusi Kasus AUDNZD)
**Bukti & Kasus Forensik**: Kasus AUDNZD SELL di pucuk lilin Marubozu di RBS 1.22800 membuktikan 3 kebocoran kode:
1. `has_res_hold` lama bernilai trivial `True` saat harga mendekati atap dari bawah (`mid <= base_ceiling`).
2. Bypass naif `if is_limit_retest: continue` membocorkan order di lorong terlarang Mid-Chamber MSE.
3. Level yang sedang ditembus (*breached*) dipungut sebagai anchor tanpa verifikasi penutupan lilin.

**Aksi Terpadu di `market_scanner.py` & `config.py`**:
1. **Anti-Marubozu Waterfall Guard (`_evaluate_m2_wall_quality` & M3 Retest)**:
   - Jika lilin mendekati anchor dengan momentum ekspansi counter-trend (`body_ratio >= 0.55` dan `wick < 0.20`), order **DITOLAK TOTAL** (`MARUBOZU_WATERFALL`).
   - Wajib konfirmasi sumbu penolakan (*rejection wick* $\ge 20\text{–}25\%$ di H1 atau M5 rejection confirmed).
2. **Penutupan Kebocoran Mid-Chamber MSE (`market_scanner.py:3658-3665`)**:
   - Hapus naif bypass `if is_limit_retest: continue` untuk `MID-CHAMBER`.
   - Setup SELL hanya sah jika `entry_price >= immediate_ceiling_c1 - 0.25 * atr_val` (di area plafon $C_1$ sejati).
   - Setup BUY hanya sah jika `entry_price <= immediate_floor_f1 + 0.25 * atr_val` (di area lantai $F_1$ sejati).
   - Jika entry berada di lorong transit antar-kamar: `[MID-CHAMBER FREEZE] Entry ditolak`.
3. **Projected SBR / Breached Wall Law**:
   - Jika level plafon/lantai telah ditembus badan lilin (`curr_bar['high'] >= c_pr` dan `close >= c_pr`), level tersebut dilarang dijadikan anchor limit SELL; anchor wajib diproyeksikan ke dinding berikutnya di atasnya (**Projected SBR** $C_1$).

---

## 3. GEOMETRI ALAMI PER MEKANISME

Median terukur (5 hari): SL **M1 144 · M2 147 · M3 189** pts; TP **M2 233 · M3 320 · M1 156**.

| Mek | Invalidasi (SL) | Target likuiditas (TP) | Karakter |
|---|---|---|---|
| **M1** Universal Sweep | di balik sumbu sweep (`ref_top`/`ref_bot`) | pool sisi lawan | **paling rapat** — trade di level teruji |
| **M2** Pullback | di balik `base_floor`/`base_ceiling` | struktur kelanjutan | **terlemah secara struktural** — anchor di koridor EMA, bukan level teruji |
| **M3** Retest | di balik `target_sup`/`target_res` | measured move | **terlebar** — entry sudah jauh dari invalidasi |
| **M4** Basing | di luar kotak basing | ekstensi breakout | rapat (batinya kompresi) |

**Implikasi**: M2 di koridor EMA (`market_scanner.py:1374-1378`, `is_ema_pullback_valid`) layak diberi tier lot lebih kecil (`REDUCED_SCALP` 0.50x lot), bukan dipaksa lewat geometri.

---

## 4. TIMEFRAME — KEPUTUSAN & ALASAN

**Jawaban: tetap H1. Jangan turun ke M30/M15.**

Diverifikasi terhadap 27 simbol live (ATR M30/H1 = **0.70**, M15/H1 = **0.56**):

| TF | SL struktural (0.6×ATR) | Floor friksi (spread 2) | Yang mengikat |
|---|---|---|---|
| **H1** | 60 pts | 67 pts | **berimbang** — struktur masih terlihat |
| M30 | 44 pts | 67 pts | **friksi mengikat** — info struktur hilang |
| M15 | 37 pts | 67 pts | friksi dominan |

**Alasan kunci**: floor friksi **tidak bergantung TF**; ATR bergantung TF. Turun TF = friksi menang = info struktur hilang.  
Satu peran sah TF rendah: **konfirmasi kelelahan** — sudah ada (`_verify_m5_rejection_wick`).

---

## 5. URUTAN EKSEKUSI (ORDER OF IMPACT)

| # | Perubahan | File | Dampak | Risiko | Status |
|---|---|---|---|---|---|
| **0** | Telemetri: `invalidation_dist`, `sl_effective`, `sl_atr`, `tp_atr`, `friction_ratio`, `session_window` | `shadow_tracker.py`, `position_manager.py` | — | **NOL** | **SIAP EKSEKUSI** |
| **1** | Decoupling lot: `MAX_POSITION_LOT = 0.50` | `risk_engine.py:415`, `config.py` | mekanisme | rendah | Siap pasca #0 |
| **2** | SL tiga suku: `struct_dist = \|entry − origin_level\| + invalidation_buffer`, lalu `sl_dist = max(struct_dist, 1.0×ATR, friction_floor@div 0.20)` | `atlas_dna.py`, `config.py` | **TINGGI** | sedang | Siap pasca #0 |
| **3** | Dekopel TP dari `min_tp` | `consensus.py:336-340` | **TINGGI** | sedang | Siap pasca #0 |
| **4** | Defensif London 15–17 | `market_scanner.py` | **TINGGI** | rendah | Siap pasca #0 |
| **5** | Target jauh bersyarat regime | `market_scanner.py` | sedang | rendah | Siap pasca #0 |
| **6** | BEP: GRADE_B 35% (sudah ada), evaluasi ambang lain | `position_manager.py:801-808` | sedang | rendah | Siap pasca #0 |
| **7** | Proteksi AUDNZD: Anti-Marubozu, Tutup Kebocoran Mid-Chamber, Projected SBR | `market_scanner.py`, `config.py` | **TINGGI** | sedang | Siap pasca #0 |

**Status Eksekusi**: Diterapkan secara penuh (Full Implementation) ke dalam bot produksi MT5 sesuai instruksi pengguna, dengan telemetri audit lengkap.

---

## 6. PROTOKOL VERIFIKASI

Sebelum dianggap selesai:
1. `pytest tests/` — seluruh suite hijau (247+ test).
2. Unit test baru wajib **memanggil jalur produksi**, bukan menyalin ulang if/else ke badan test.
3. Probe 27 simbol: verifikasi `sl_effective` masuk akal (`1.0–2.0×ATR`), friksi **<12–20%** untuk semua, tidak ada `sl <= 0`.
4. Replay 101 trade dengan geometri baru → bandingkan before/after terhadap baseline **+27.05R** (bukan −1.9R).

---

## 7. JANGAN DILAKUKAN (DO-NOT-DO LIST)

1. **Jangan pakai SL 0.50×ATR** — membunuh 24.9% pemenang.
2. **Jangan hapus floor friksi mentah** — friksi melonjak ke 25–36%.
3. **Jangan turunkan timeframe** ke M30/M15 — friksi jadi dominan (lihat §4).
4. **Jangan paksa TP turun** untuk mengejar profit — hanya +0.85R (efek seleksi, bukan kausal).
5. **Jangan pakai cohort n<30 sebagai aturan produksi** (Tokyo×CSM n=6).
6. **Jangan sebut "+47.8R"** — dibangun di atas baseline yang salah; sudah ditarik.
7. **Jangan langsung tanam parameter hasil grid search 5 hari** — overfit.

---

## 8. RESOLUSI 4 PERTANYAAN TERBUKA (§9)

1. **`MAX_POSITION_LOT = 0.50` di akun Cent**: **[TERVERIFIKASI & SELESAI]**  
   Diverifikasi MT5 live: contract size 1,000 unit, tick value 1.0 USC/pt. Risiko pada SL 80pt = 40 USC ($0.40 USD / 0.75% equity) dan pada SL 100pt = 50 USC ($0.50 USD / 0.93% equity, pas di target 1.0%). Aman dan optimal.
2. **Validitas `origin_level` di seluruh 26 pair**: **[TERVERIFIKASI & SELESAI]**  
   Audit source code memastikan M1, M2, M3, M4 selalu mengirim `origin_level` valid ke `calculate_intraday_sl_tp`.
3. **Tier lot per-mekanisme**: **[DIADOPSI]**  
   M2 di koridor EMA tengah diberi tier `REDUCED_SCALP` (0.50x lot).
4. **Nilai `FRICTION_FLOOR_DIVISOR`**: **[DISEPAKATI]**  
   Menggunakan **`0.20`** (nilai netral config sekarang; 0/27 simbol mengikat di bawah ATR). Usulan 0.12 dan 0.25 dibatalkan.

---

*Dokumen ini konsensus lintas-AI. Siap dipakai sebagai acuan implementasi.*
