# RFC 11: Zone Confluence Engine (ZCE) — Peta Zona Multi-TF × Multi-Horizon

> Status: **Diusulkan** (2 September 2026) — menunggu review sebelum implementasi.
> Branch target: `quant-trade`. Gaya: Pure Quant deterministik, 0 token untuk pemetaan.

---

## 1. Latar Belakang & Masalah

Sistem saat ini mengirim ratusan OHLC mentah ke 3-LLM dan memetakan level struktural secara **ad-hoc di banyak tempat dengan window berbeda-beda**:

| Lokasi | Window yang dipakai | Fungsi |
|---|---|---|
| `market_scanner.py:607` | DR H1 **100-bar** (`sess_h/sess_l`) | `pos_in_range`, Gate B anti-delivery |
| Dual-Basket Engine (changelog #1, 2 Sep) | DR H1 **50-bar** | `pos_i` per basket |
| MSE `macro_strategic_engine.py` | LuxSMC **full-frame** per TF + FRVP window tetap | elekt C1/F1, lapisan F/C |
| MSE soket 6-TF | satu horizon tetap per TF (MN1 50, W1 100, D1 350, H4 400, H1 250, M30 200) | state engine |

Tidak ada satu sumber kebenaran yang menjawab pertanyaan **"di titik harga mana pasar meninggalkan jejak institusional, di semua skala sekaligus, seberapa kuat, sesegar apa"**. Akibatnya konflik skala (contoh: murah di window 50-bar tetapi premium di window 150-bar) tidak pernah dideteksi eksplisit — hanya ditebak lewat heuristik `recent_ceiling_touch` (8 bar H4 ≈ 32 jam).

### Apa yang sudah ada (fondasi, 2 Sep 2026)
- `LuxSMCAnalyzer` (OB, FVG, EQH/EQL, swing) — window-agnostic.
- FRVP NumPy vectorized (`volume_profile.py`, 43ms) + merge toleransi 0.25×ATR (changelog #7).
- `_cluster_merge_orthogonal` + `_get_fortress_tag` + dual-grid psikologis `atlas_dna`.
- Stacked fortress bands F1..F10/C1..C10 di `macro_dashboard.html` (visualisasi).
- Kalibrasi skor institusional PWL/PWH/PDL/PDH = 4.0–4.5; `min_chamber_height`, `delta_tol` berbasis ATR.

---

## 2. Tujuan & Kebutuhan (konteks trading: H1, selesai intraday)

1. **Kapan masuk** → meminimalkan drawdown.
2. **Di mana SL dan seberapa jauh TP** — tidak terlalu dekat, tidak terlalu jauh.
3. **Apakah target menabrak dinding rapuh intraday, atau benteng berskor besar** yang ternyata dingin/ruang hampa (mis. psych + FVG intraday + W1 OB 3 bulan lalu, terisolasi dilihat dari H1).
4. **Metode M1/M2/M3** ditentukan dari posisi di peta.
5. **Pair mana yang sedang ideal** — scan tiap 60 detik (pasar FX asimetris kecuali news/dump besar).

---

## 3. Pembagian Peran: ZCE vs MSE (hasil verifikasi kode)

### Pindah ke ZCE — seluruh lapisan "peta & penggaris" (`macro_strategic_engine.py`):
| Blok | Baris aktual | Isi |
|---|---|---|
| SBR/RBS swing-anchored (W1/D1/H4/H1) | 514–537 | primitif |
| DBD/RBR | 539–541 | primitif (hari ini H1 saja → di-grid-kan) |
| EQH/EQL pool | 543–571 | primitif (D1 → diperluas) |
| LuxSMC OB (H1/H4/D1/W1) | 573–610 | primitif (+ **FVG** — hari ini tidak dipakai MSE) |
| Psych dual-grid + perakitan kandidat | 497–512, 756–882 | primitif |
| EMA-as-barrier + macro extremes + FRVP | 669–754 | primitif |
| Cluster merge & elekt C1/F1/C2/F2 | 884–956 | klasterisasi |
| Lapisan dinamis F1..Fn / C1..Cm + grade | 961–1077 | klasterisasi |

### Tetap di MSE — mesin arah, izin, dan eksekusi:
- Interaction sequence tracker (1096–1114), state machine Location×Event×Trajectory + `derive_semantic_state` (1116–1224).
- Branch eksekusi per state → `macro_bias`, `action_tier`, direktif, SL/TP/entry anchor, `forbidden_traps` (1226–1463).
- Regime stability, fundamental engine, contingency graph, packaging `MacroStrategicDirective` (1485–1632).

### Kontrak
`MacroStrategicDirective` (baris 142–225) **tidak berubah bentuk**. MSE membaca dinding/lapisan dari output ZCE. `market_scanner.py` dan `llm_client.py` tidak tersentuh di sisi konsumsi field.

---

## 4. Grid TF × Horizon & Pipeline

### Grid default (konfigurabel)
| TF | Horizon (bar TF tsb) | Catatan |
|---|---|---|
| M30 | 50, 150 | fetch 600 |
| H1 | 50, 100, 150, 250 | fetch 500 |
| H4 | 50, 100, 150 | fetch 400 |
| D1 | 50, 100, 150, 250 | fetch 350 |
| W1 | 50, 100 | fetch 200 |
| MN1 | 50 | fetch 100 (konteks ekstrem) |

Fetch **sekali per TF** per refresh (cache `(symbol, tf, bar_time)`), lalu slice horizon in-memory — **tidak ada fetch MT5 berulang**. Cache + rotasi 5–6 simbol per siklus 60 detik → tiap simbol segar ≤ 5 menit.

### Pipeline per simbol
1. Fetch rates (6 TF) → slice horizon.
2. Per sel `(tf, horizon)` → primitif: LuxSMC (OB+FVG+EQH/EQL), swing S/R, DBD/RBR, FRVP (**hanya tf ≤ H4**, tick_volume valid), psych (level, tidak bergantung horizon), macro extremes (W1/MN1/D1).
3. **Merge spasial** seluruh elemen semua sel → klaster (toleransi merge `0.25×ATR_H1` analog changelog #7; dalam ZCE `cluster_merge_atr_mult`).
4. Skoring & klasifikasi per klaster (bagian 6–7).
5. Elekt dinding aktif + lapisan F/C (bagian 9).
6. Scale ladder posisi + flag konflik (bagian 8).
7. Penyusunan output `ZoneMapResult`.

---

## 5. Model Data

```python
@dataclass
class ZonePrimitive:
    kind: str            # OB | FVG | SBR_SWING | RBS_SWING | DBD | RBR | EQH | EQL |
                         # FRVP_POC | FRVP_VAH | FRVP_VAL | PSYCH_MAJOR | PSYCH_SUB |
                         # EMA_BAND | MACRO_EXTREME
    tf: str
    horizon: int          # 0 untuk level non-window (psych, macro extreme)
    proximal: float       # tepi dekat harga
    distal: float         # tepi jauh harga (level → prox == distal ± epsilon)
    formation_time: float # waktu formasi (unix) — 0 jika tidak relevan

@dataclass
class ZoneCluster:
    cluster_id: int
    proximal: float
    distal: float
    members: List[ZonePrimitive]
    score_raw: float
    horizon_boost: float
    freshness_mult: float
    score_final: float
    grade: str              # GRADE_1_MICRO | GRADE_2_INTERMEDIATE | GRADE_3_MACRO
    fortress_tag: str
    tfs_present: List[str]
    kinds_present: List[str]
    horizon_max: int
    width_atr: float        # (distal-prox) / ATR_H1
    is_cold: bool           # last touch > ZCE_COLD_DAYS
    is_vacuum: bool         # dingin + tidak ada aktivitas H1 di sekitarnya
    last_touch_time: float
    touch_count: int

@dataclass
class ScaleLadder:
    symbol: str
    pos_by_horizon: Dict[int, float]   # H1: {50:…, 100:…, 150:…, 250:…, 500:…}
    conflict_flag: str                 # NONE | LOCAL_DISCOUNT_MACRO_PREMIUM | LOCAL_PREMIUM_MACRO_DISCOUNT

@dataclass
class ZoneMapResult:
    symbol: str
    ts: float
    clusters: List[ZoneCluster]        # ranking menurun (score_final)
    floors: List[dict]                 # F1..Fn elected, format = legacy layered_floors
    ceilings: List[dict]               # C1..Cm elected
    immediate_floor_f1: float
    immediate_ceiling_c1: float
    deep_floor_f2: float
    deep_ceiling_c2: float
    ladder: ScaleLadder
    suggested_method: str              # M1 | M2 | M3 | NONE (bagian 11)
    readiness_score: float             # 0..100 (bagian 12)
```

---

## 6. Skoring (keputusan J1 & J2)

**J1 (terkunci):** Horizon = **penguat bobot**, bukan saksi konfluensi independen. Konfluensi sejati = primitif berbeda × TF berbeda. Elemen dari sel berbeda yang jatuh di klaster yang sama hanya menyumbang horizon maksimum-nya.

**J2 (terkunci):** Bobot default teoretis → kalibrasi lewat forward test.

```
element_score   = w_kind × w_tf
cluster_score_raw = Σ element_score atas semua member di band klaster
score_final     = cluster_score_raw × horizon_boost × freshness_mult
```

Bobot default (`config.py`, override `.env`):
| w_tf | nilai | | w_kind | nilai |
|---|---|---|---|---|
| M30 | 0.55 | | EQH/EQL | 1.15 |
| H1 | 1.00 | | MACRO_EXTREME | 1.20 |
| H4 | 1.60 | | OB / DBD / RBR | 1.00 |
| D1 | 2.20 | | SBR/RBS swing | 0.90 |
| W1 | 2.80 | | FRVP POC / VAH / VAL | 1.00 / 0.85 / 0.85 |
| MN1 | 3.20 | | PSYCH_MAJOR / SUB | 0.80 / 0.50 |
| | | | EMA_BAND | 0.45 |

```
horizon_boost:  H_max < 100 → 1.00 ; 100–149 → 1.10 ; 150–249 → 1.20 ; ≥ 250 → 1.30  (cap 1.35)
freshness_mult: f = clamp(1.05 − 0.015 × days_since_last_touch, 0.50, 1.05)
                touch dalam 24 jam terakhir → +0.05 (cap 1.05)
```

Ambang grade & fortress dipertahankan identik dengan MSE hari ini (`_get_fortress_tag`): **G3 ≥ 6.5, G2 ≥ 3.5, G1 < 3.5** + tag overrides, supaya parity test (Fase 1) valid.

---

## 7. Freshness, COLD, VACUUM, Reachability (kebutuhan #2 & #3)

- **`COLD`** — `days_since_last_touch > ZCE_COLD_DAYS` (default 21). Skor sudah terpenalti via `freshness_mult`; flag untuk keputusan eksplisit.
- **`VACUUM`** — COLD **dan** `days_since_last_touch ≥ ZCE_VACUUM_DAYS` (default 60 ≈ 3 bulan) **dan** tidak ada bar H1 dalam `±1.0×ATR_H1` band pada 250 bar H1 terakhir. Contoh user: W1 OB 3-bulan-lalu tanpa aktivitas H1 = benteng statis, **bukan** benteng aktif.
- **Aturan penggunaan VACUUM**:
  1. Tidak boleh dipakai alasan menolak setup intraday (anti-bear veto tidak boleh berdalih padanya).
  2. Momentum intraday cenderung **menembus** → TP boleh melampaui-nya menuju dinding aktif berikutnya.
  3. Tetap dicatat di peta sebagai konteks makro.
- **Reachability (intraday)** — karena target selesai hari itu juga: kandidat TP1 hanya klaster dalam `jarak ≤ ZCE_TP_REACH_ATR_MULT × ATR_H1` (default 3.0). Di luarnya → konteks / TP2 runner / M3 expansion.

---

## 8. Scale Ladder & SCALE_CONFLICT (menjawab konflik 50 vs 150 bar)

- `pos_h` dihitung persis seperti scanner (rolling high/low window H1) untuk `h ∈ {50, 100, 150, 250, 500}`.
- **Konflik** = ada pasangan horizon dengan `|pos_a − pos_b| ≥ ZCE_CONFLICT_GAP` (0.45) **dan** salah satu sisi di kuintil ekstrem (≤ 0.20 atau ≥ 0.80):
  - `LOCAL_DISCOUNT_MACRO_PREMIUM`: `pos_50 ≤ 0.20` dan `pos_250 ≥ 0.65` → BUY lokal berbahaya (breakdown makro).
  - `LOCAL_PREMIUM_MACRO_DISCOUNT`: simetris untuk SELL.
  - `NONE`: konsisten.
- **Konsumsi**: mengganti input Gate B `dealing_range_pos` & `recent_ceiling_touch` di `market_scanner.py` (logika gate tidak diubah; inputnya yang multi-horizon).

---

## 9. Elekt Dinding & Lapisan F/C (parity dengan MSE)

- Mode **legacy single-horizon** (Fase 1–2) menggunakan window persis MSE hari ini → elekt `immediate_floor_f1/ceiling_c1/deep_f2/c2` + `layered_floors/ceilings` **identik** dengan output MSE (diverifikasi parity test).
- Mode **full** (Fase 3): elekt dari klaster ber-ranking hasil grid; lapisan berformat sama sehingga konsumen tidak berubah.
- Ambang kualifikasi (pindah sebagai param ZCE, nilai sama dengan MSE hari ini):
  - `delta_tol = max(0.35×ATR_H1, 0.04×psych_step, 3 pip)` — merge level.
  - `min_chamber_height = max(0.60×ATR_H1, 8 pips)`.
  - `structural_validity_threshold = 2.5`; `cluster_merge_atr_mult = 0.25×ATR_H1` (band).

---

## 10. Aturan TP/SL Intraday (kebutuhan #2)

- **SL**: belakang `distal` klaster entry terpilih + anti-wick buffer (0.35×ATR + spread, tetap). Floor ATR & ceiling 160 pts di `consensus._apply_sltp_rules` **tidak diubah**.
- **TP1**: tepi **proximal** klaster qualified berikutnya di arah target dalam reachability, dikurangi front-run pad `(0.15×ATR_H1 + spread)`. Klasifikasi dinding TP:
  - `FRESH_FORTRESS` (skor tinggi, tidak COLD) → TP berhenti **di depan**-nya.
  - `COLD_VACUUM` → TP **melampaui**-nya ke dinding aktif berikutnya.
  - `FRAGILE_WALL` (G1, 1–2 primitif) → TP1 sah di sana (quick bank intraday), bukan alasan TP terlalu dekat.
- **TP2 / runner**: hanya klaster makro di luar reachability (konteks).

---

## 11. Pemilihan Metode M1/M2/M3 (kebutuhan #4)

| Posisi di peta | Metode |
|---|---|
| Ekstrem chamber (`pos_100 ≤ 0.15` / `≥ 0.85`), baru sweep dinding C1/F1/EQH-EQL + reclaim | **M1 Universal Sweep** (fade) |
| Reload zone antara F1 & equilibrium, searah tren H4/D1, menunggu retest F1 | **M2 Trend-Aligned Pullback** |
| Tembus C1 dengan runway ke klaster berikutnya, menunggu retest sisi luar | **M3 HTF Wall Retest/Breakout** |

`suggested_method` di `ZoneMapResult` = masukan untuk gate M1/M2/M3 di scanner (anchor level + konfirmasi diambil dari klaster ZCE, termasuk info COLD_VACUUM agar Gate C anti-expansion tidak salah blokir).

---

## 12. Readiness Score untuk Scan 60 Detik (kebutuhan #5)

```
R = 100 × ( 0.30×P_perm + 0.25×P_grade + 0.20×P_pos + 0.15×P_scale + 0.10×P_news )

P_perm : GO=1.0 | ARM=0.7 | WAIT=0.25 | LOCK=0
P_grade: grade klaster terbaik dalam jarak 1.0×ATR_H1: G3=1.0 | G2=0.7 | G1=0.4 | none=0
P_pos  : pos_100 di discount(≤0.35)/premium(≥0.65) sesuai arah = 1.0 | mid = 0.5 | salah sisi = 0
P_scale: konflik skala = 0.5 (hanya jika ter-resolve oleh arah makro) | NONE = 1.0
P_news : high-impact ≤ 60 menit = 0 | lainnya = 1.0
```

Fungsi: **pengurutan** 26 simbol pada scan 60 detik + funnel Stage 2 (bukan pemicu order).

---

## 13. Payload LLM (keputusan J3)

- **Zone table** (semua model): top ≤ 15 klaster/simbol — band prox/distal, jenis primitif, TF, horizon max, grade, umur (jam), touch count, `width_atr`, `COLD/VACUUM` + scale ladder + flag konflik.
- **OpenAI (Macro)**: zone table + tape D1 5 + H4 8 (raw OHLC sedikit — makro sudah dirangkum).
- **Gemini (Price Action)**: zone table ringkas + raw OHLC banyak: **M1 30, M5 48, M15 24, M30 12** (H1 raw dihapus).
- **DeepSeek (CRO)**: zone table lengkap + H1 6 + M5 24 (H4 raw dihapus).
- Prompt verbatim tetap diekspor ke `docs/prompt/`.

---

## 14. Konfigurasi (config.py + .env)

| Key | Default |
|---|---|
| `ZCE_ENABLED` | `False` (shadow dulu) |
| `ZCE_MODE` | `legacy` \| `full` \| `shadow` |
| `ZCE_REFRESH_ROTATION` | `6` (simbol per siklus 60s) |
| `ZCE_H1_LADDER` | `[50,100,150,250,500]` |
| `ZCE_TP_REACH_ATR_MULT` | `3.0` |
| `ZCE_COLD_DAYS` | `21` |
| `ZCE_VACUUM_DAYS` | `60` |
| `ZCE_CONFLICT_GAP` | `0.45` |
| `ZCE_CLUSTER_MERGE_ATR_MULT` | `0.25` |
| `ZCE_W_TF_M30…MN1`, `ZCE_W_KIND_*` | tabel bagian 6 |
| `ZCE_GRADE_G3/G2` | `6.5 / 3.5` |

> `.env` adalah single source of truth; setiap key baru ditambahkan di `.env` bersama `config.py`.

---

## 15. Validasi Forward & Respect Ledger

- **Respect ledger**: tiap setup tereksekusi di-tag `(pair, cluster_grade, width_atr, arah, COLD/VACUUM)` → dihitung respect rate & PF per bucket **setelah ≥ 60–100 sampel** per pair/bucket (aturan validitas AGENTS.md). Tidak ada multiplier per-pair yang di-hardcode dari sampel kecil.
- **Shadow mode**: ZCE jalan paralel, log perbedaan keputusan vs MSE, tanpa efek eksekusi.
- Kalibrasi bobot hanya lewat forward test (keputusan J2).

---

## 16. Risiko & Keputusan Terbuka

1. **Parity risk** — jika Fase 1 gagal identik di simbol mana pun, berhenti & selidiki (kemungkinan asumsi window).
2. **Komputasi** — grid 18+ sel/simbol; target < 120 ms/simbol (LuxSMC+FRVP NumPy); rotasi 6 simbol/siklus → 720 ms budget per siklus aman. Ukur dulu di Fase 1.
3. **Double fetch** — ZCE menjadi pemilik rate cache 6-TF; MSE & scanner membaca darinya (hapus fetch duplikat).
4. **FVG** adalah primitif baru yang hari ini tidak dipakai MSE → perlu validasi kontribusinya di forward test.
5. **Arah multi-horizon untuk MSE** (upgrade state machine) sengaja **di luar lingkup** RFC ini — fase terpisah dengan parity test sendiri.

---

## 17. Referensi Kode

- `src/analytics/macro_strategic_engine.py` baris 142–225 (dataclass), 235–437 (helpers), 438–1632 (`compute_directive`).
- `src/indicators/lux_smc.py`, `src/indicators/volume_profile.py`, `src/indicators/atlas_dna.py`.
- `src/analytics/market_scanner.py` baris 596–610 (DR 100-bar), 714–721 (recent_ceiling_touch), Gate B (57–72), anti-bear veto (1261–1264).
- Changelog September 2026: #1 dual-basket (DR 50-bar), #6 barrier cluster calibration, #7 stacked fortress bands.
