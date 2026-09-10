# Design Spec: ZCE Multi-Timeframe × Multi-Horizon Layered Structural Map

**Date**: 2026-09-10
**Status**: Draft → untuk persetujuan
**Branch**: `quant-trade-noAI`
**Komponen**: `src/analytics/zone_confluence_engine.py`, `config.py`, `.env`, `dashboard.py`, `tests/`

---

## 1. Prinsip Inti

ZCE adalah **peta zona struktural berlapis**:

> Setiap kombinasi **(timeframe × horizon)** menghasilkan calon level struktural sendiri.
> Level-level dari sel berbeda yang **berdekatan secara harga** membentuk satu **NODE**.
> Kekuatan node = **confluence lintas-sel** (berapa banyak sumber independen setuju).
> Node di-**GRADE** (G1/G2/G3). Node diurutkan jadi tangga `C1..Cn` / `F1..Fn`.

**Pemisahan konsep yang sekarang hilang:**
- **GEOMETRI** = di mana node berada (jarak harga) → ditentukan oleh *edge* primitif.
- **SKOR** = seberapa kuat node (confluence) → ditentukan oleh *semua* primitif di sekitarnya.

Bug saat ini: keduanya dipaksa masuk satu proses `_merge_primitives` yang memakai *band overlap*.
Akibatnya primitif lebar (mis. `OB_BEAR D1` selebar 55 pips) menjembatani semua level →
terbentuk mega-blob 6.9× ATR → skor & grade jadi palsu.

---

## 2. Bukti (grounded)

### 2.1 EURCAD, live 1.60664
Node confluence lintas-sel di atas harga:

| Edge | Jarak | Skor | Grade | Confluence |
|---|---|---|---|---|
| 1.60894 | +23.0p | **11.91** | **GRADE_3_MACRO** | EQH@D1, EQH@H4, EQL@H1, FVG_BEAR@H1, FVG_BEAR@W1, LAST_HIGH@H1 |
| 1.61311 | +64.7p | 7.12 | GRADE_3_MACRO | EQH@D1, EQH@H4, LAST_HIGH@H1, LAST_HIGH@H4 |
| 1.60807 | +14.3p | 4.84 | GRADE_2_INTERMEDIATE | EQL@H1, FVG_BEAR@W1, LAST_HIGH@M30 |
| 1.60975 | +31.1p | 5.71 | GRADE_2_INTERMEDIATE | EQH@H4, EQL@H1, FVG_BEAR@H1, LAST_HIGH@H1 |

Kode sekarang: **C1 = 1.61099** (tepi blob) — 6 level G3 di 1.60894 **tidak terlihat**.

### 2.2 Peta per-sel (37 node di atas harga)
Hampir semuanya `GRADE_1_MICRO`, termasuk `D1 EQH` (2.53) & `W1 FVG` (2.24) — karena
skor dihitung dari anggota klaster sendiri, bukan confluence lintas-sel.

### 2.3 Dampak lintas universe
26/26 pair punya klaster >2× ATR (maks 53× ATR). 21/26 pair harga terkurung di dalam blob.

---

## 3. Desain

### 3.1 Perluasan Grid (config)

```python
ZCE_GRID = {
    "M1":  [50, 100],              # opsional (micro-scalp) — flag
    "M30": [50, 150],
    "H1":  [50, 100, 150, 250, 350, 500],
    "H4":  [50, 100, 150, 250],
    "D1":  [50, 100, 150, 250, 350, 500],
    "W1":  [50, 100, 150],
    "MN1": [50, 100],
}
```
Tambahan: horizon **350 & 500** di H1/D1, **250** di H4, **150** di W1, **100** di MN1.

### 3.2 Clamp Lebar Primitif (anti-jembatan)

Saat koleksi, lebar tiap primitif dibatasi:
```
max_prim_width = ZCE_MAX_PRIM_WIDTH_ATR * ATR_tf   # default 0.15
```
Primitif lebih lebar dipotong simetris terhadap titik tengahnya.
Ini mencegah satu OB/FVG raksasa menjembatani semua level.
*(Prototipe: median runway 11.6p, 0/26 pair tercekik — aman.)*

### 3.3 Pembentukan NODE (bukan blob)

Ganti `_merge_primitives` (all-or-nothing snowball) dengan:
```
_edges(prims) -> titik edge:  ceiling -> p.bottom ; floor -> p.top
_build_nodes(edges, tol = max(ZCE_NODE_TOL_ATR*ATR_H1, pip_floor))
    klaster titik edge yang berjarak <= tol  (single-linkage TAPI hanya antar-EDGE,
    bukan antar-band)  -> node = {edge_ref (median), members}
```
Kunci: clustering dilakukan pada **titik edge**, bukan band. Band lebar tidak lagi
menjembatani dua node yang sebenarnya berjauhan.

### 3.4 Skor NODE (confluence lintas-sel)

```
for node in nodes:
    pairs = {}   # unique (kind, tf) -> bobot
    hmax  = 0
    for p in prims:                                  # SEMUA primitif, semua sel
        if abs(edge(p) - node.edge) <= SCORE_RADIUS:
            pairs[(p.kind, p.tf)] = kind_w * tf_w
            hmax = max(hmax, p.horizon)
    node.score = sum(pairs.values()) * horizon_boost(hmax)
    node.confluence = len(pairs)
```
`SCORE_RADIUS` = `max(ZCE_SCORE_RADIUS_ATR * ATR_H1, 2 * pip_floor)`.

### 3.5 Grade Node

```
score >= ZCE_GRADE_G3 (6.5) -> GRADE_3_MACRO
score >= ZCE_GRADE_G2 (3.5) -> GRADE_2_INTERMEDIATE
else                        -> GRADE_1_MICRO
```

### 3.6 Aturan "Harga Di Dalam Band"

Node yang edge-nya jatuh dalam `±NODE_PRICE_BAND` (default 2×min_sep) dari harga
dianggap **"harga sedang DI zona"** — BUKAN kandidat dinding. Dicatat sebagai status
`inside_zone` (untuk telemetri/LLM), tidak dipakai sebagai C1/F1.
Ini mencegah C1 menempel di harga (prototipe: 9/23 pair runway ≈ 0 tanpa aturan ini).

### 3.7 Tangga Berlapis

Node diurutkan jarak dari harga → `C1..Cn` (atas) dan `F1..Fn` (bawah).
Tiap layer membawa: `price`, `grade`, `score`, `confluence`, `kinds`, `tf_max`, `horizon_max`.
**Lapis yang sama sekali tidak boleh di-skip** — kalau C1 dan C2 sama-sama ada, dua-duanya tampil.
G3 diprioritaskan mengisi slot bila terjadi tabrakan jarak (`min_sep`).

### 3.8 Kontrak Keluaran

`to_wall_override()` **tidak berubah** (backward compatible). Ditambah field opsional:
`c1_confluence`, `f1_confluence`, `inside_zone`, `layer_count`.

---

## 4. Rencana Implementasi Bertahap

| Fase | Isi | Risiko | Verifikasi |
|---|---|---|---|
| **P1 ✅** | Perluas `ZCE_GRID` (350/500) + clamp lebar primitif | Rendah | probe 26 pair: 0 pair <1p; test suite hijau |
| **P2 ✅** | `_build_nodes` (edge-based) + skor confluence lintas-sel | Sedang | EURCAD: C1 ≈ 1.60894 G3; 26 pair: 0 pair <1p |
| **P3 ✅** | Grade per node + tangga berlapis + aturan inside-zone | Sedang | tangga C1..C4 punya grade; test baru |
| **P4 ✅** | Dashboard sync + telemetri layer + doc | Rendah | visual cek; `/api/symbol` memuat layer |

### Hasil P1 (2026-09-10)

**Perubahan:**
- `ZCE_GRID`: H1 `[50,100,150,250,350,500]`, D1 `[50,100,150,250,350,500]`, H4 +250, W1 +150, MN1 +100.
- `ZCE_HORIZON_BOOST`: tambah tier `(350,1.30),(600,1.35)` — nilai horizon existing tidak berubah.
- `ZCE_MAX_PRIM_WIDTH_ATR=0.15` — clamp simetris lebar primitif per-TF (config.py + .env, dua blok).
- `market_scanner.tf_cfg`: D1 fetch 350 → **550** bar (agar horizon 500 punya data).

**Hasil terukur (26 pair live):**

| Metrik | Sebelum | Sesudah |
|---|---|---|
| Blob maksimum | 53.19× ATR | **7.12× ATR** |
| EURCAD C1 jarak | 42.3 pips | **7.7 pips** |
| EURCAD lebar cluster maks | 6.5× ATR | 6.19× ATR |
| Pair dengan harga terkurung | 21/26 | 16/26 |

**Grade kini berfungsi** (sebelumnya hampir semua G1). Contoh EURCAD:
```
C1 1.60660 (+0.9p)  GRADE_2  score 4.23
C2 1.60821 (+17.0p) GRADE_3  score 11.29  ← node G3 nyata (sebelumnya tak terlihat)
C4 1.61327 (+67.6p) GRADE_3  score 7.71
F1 1.60611 (+4.0p)  GRADE_3  score 11.84
F4 1.60086 (+56.5p) GRADE_3  score 6.93
```

**Catatan untuk P3:** tangga masih memuat layer di `+0.9 pips` dari harga (praktis *di* harga).
Aturan "inside zone" (spec §3.6) belum diimplementasi — itu pekerjaan P3.

**Test suite:** 272 passed, 0 failed.

### Hasil P3 (2026-09-10)

**Perubahan:**
- `ZoneCluster.confluence` — jumlah pasangan unik `(kind, tf)` penyusun skor (diisi di `_finalize_cluster`).
- Layer dict kini membawa `confluence`, `tf_max`, `horizon_max`, `at_price`.
- **Aturan "harga di dalam zona"**: `inside_band = ZCE_NODE_PRICE_BAND_MULT × min_sep` (default 1.0).
  Layer dengan `|price − cur| < inside_band` ditandai `at_price` dan **di-skip** dari pemilihan
  `immediate_ceiling_c1` / `immediate_floor_f1` (fallback ke layer terdekat bila semua menempel).
  Layer tersebut **tetap tampil di tangga** (peta tetap lengkap).
- Output baru: `c1_confluence`, `f1_confluence`, `inside_zone`, `layer_count` (semua opsional,
  `to_wall_override()` backward-compatible).
- Test baru `tests/test_zce_node_layers.py` (3 test).

**Hasil terukur (26 pair live):**

| Metrik | Nilai |
|---|---|
| C1 dist | min 10.3p / med 17.7p / max 36.6p — **0 pair < 5 pips** |
| F1 dist | min 8.5p / med 17.9p / max 69.5p — **0 pair < 5 pips** |
| `inside_zone` aktif | 21/24 pair |
| confluence terisi | mis. AUDNZD C1 = 14 sumber, GBPAUD F1 = 18 sumber |

EURCAD sebelum → sesudah P3: `C1 1.60660 (+0.9p)` → **`C1 1.60821 (+19p, GRADE_3, 5 sumber)`**.
Node yang menempel harga tidak lagi dipakai sebagai dinding tradeable.

**Test suite:** 275 passed, 0 failed.

### Hasil P4 (2026-09-10) — Dashboard Sync

**Masalah yang ditemukan:** `_consolidate_zce_zones` **membuang** field kekuatan layer.
Dict dibangun ulang di tiga tempat (elected floors/ceilings, cluster-derived, dan
`result.append` akhir) — dan `result.append` menghapus `confluence/tf_max/horizon_max/at_price`.
Akibatnya UI tidak pernah menerima info confluence meski engine sudah menghitungnya.

**Perubahan (`dashboard.py`):**
- Import `ZCE_W_TF` di level modul.
- Ketiga situs append (`elected` floors, `elected` ceilings, `cluster`) meneruskan
  `confluence`, `tf_max`, `horizon_max`, `at_price`.
- Dua blok merge proximity (floors & ceilings di `get_symbol_detail`) ikut membawa field
  tersebut saat layer pemenang menggantikan.
- `result.append` akhir (blok konsolidasi) meneruskan field dari `lead` — ini yang tadi menghapus.
- Payload `/api/symbol` bertambah: `c1_grade`, `f1_grade`, `c1_confluence`, `f1_confluence`,
  `inside_zone`, `inside_tiers`, `layer_count`.
- Test baru `tests/test_dashboard_zce_sync.py` (2 test: passthrough + backward-compat layer lama).

**Backward-compat:** layer tanpa field P3 → default aman (`confluence=0`, `tf_max=""`,
`horizon_max=0`, `at_price=False`). Tidak ada perubahan label/format yang diparse frontend.

**Test suite:** 277 passed, 0 failed.

### Hasil P2 (2026-09-10) — Edge-based Node Engine

**Perubahan (`zone_confluence_engine.py`):**
- `_prim_edge(p)`: titik acuan struktural — ceiling → `bottom`, floor → `top`, netral → `mid`.
- `_build_nodes(prims, atr_h1, point_size)`: pembentuk node baru.
  * **Pengelompokan pada TITIK EDGE**, bukan band → primitif lebar tak bisa menjembatani.
  * **Sweep berbasis ANCHOR**: edge hanya diterima bila `edge − anchor ≤ node_tol` →
    tidak ada chaining/snowball (single-linkage dihindari).
  * **Skor = confluence LINTAS-SEL**: semua primitif (semua TF × horizon) dalam `score_radius`
    dari anchor, dihitung sebagai `unique(kind, tf) × bobot × horizon_boost`.
  * Band node mengikuti anchor (di-clamp `2 × node_tol`) — bukan mid primitif raksasa.
- Flag `ZCE_NODE_ENGINE_ENABLED` (default True) memilih node engine vs `_merge_primitives`.
- Config + `.env`: `ZCE_NODE_ENGINE_ENABLED`, `ZCE_NODE_TOL_ATR=0.35`, `ZCE_SCORE_RADIUS_ATR=0.50`.
- Test baru `tests/test_zce_node_engine.py` (4 test: no-bridging, cross-cell scoring,
  anti-chaining, flag toggle).

**Hasil terukur (26 pair live):**

| Metrik | Nilai |
|---|---|
| C1 dist | min 7.5p / med 17.9p / max 32.8p — **0 pair < 5 pips** |
| F1 dist | min 8.3p / med 16.0p / max 39.0p — **0 pair < 5 pips** |
| Confluence C1 | 1–15 sumber (mis. NZDCHF 15, AUDCAD 11) |
| Grade | G3 dominan pada dinding struktural nyata |

EURCAD: `C1 1.60869 [G3, 6src]`, `F1 1.60611 [G3, 12src]` — node 1.608–1.609 yang
sebelumnya tak terlihat kini menjadi dinding G3 utama.

**Test suite:** 283 passed, 1 failed.
Failure yang tersisa **bukan** dari ZCE: `test_elect_primary_standby_pro_trend_priority`
di `tests/test_dashboard.py` (fungsi `_elect_primary_standby`, murni dict input, tidak
menyentuh ZCE). Test itu dibuat bersamaan dengan refactor konfluensi di `dashboard.py`
dan bertentangan dengan perilaku kodenya sendiri (`M2+M3 BULL` vs ekspektasi
`M2:PULLBACK BULL`). Perlu diputuskan pemilik perubahan tersebut.

### Hasil Render UI (P4 lanjutan)

- **Label tangga chart (left margin)**: kini `~F1 [G3] 1.60611 (19.9 • D1+H1+H4 • EQH+EQL • 12src)`.
  `~` = layer at-price (menempel harga, bukan dinding tradeable); `Nsrc` = jumlah sumber confluence.
- **Watchlist**: `C1: 20p •6x | F1: 21p •6x`.
- **Payload `/api/overview`**: `c1_confluence`, `f1_confluence`, `c1_grade`, `f1_grade`.
- **Payload `/api/symbol`**: `c1_grade`, `f1_grade`, `c1_confluence`, `f1_confluence`,
  `inside_zone`, `inside_tiers`, `layer_count`.
- Test `tests/test_dashboard_zce_sync.py` bertambah 1 (label memuat `6src` + penanda `~`).





Setiap fase: **test suite penuh harus hijau** sebelum lanjut. Semua parameter baru
di `config.py` **dan** `.env` (AGENTS rule #2).

---

## 5. Guardrail / Risiko

1. **Runway mengecil** → gate CBSS bisa lebih sering blok. Pantau `gate_debug.log` setelah P2.
2. **Clamp primitif** mengubah semua skor → grade bergeser. Threshold G2/G3 mungkin perlu rekalibrasi setelah P1.
3. **Performa**: grid lebih besar (≈ +8 sel) → hitung LuxSMC lebih banyak. Target tetap < 100 ms/pair.
4. **Backward compat**: `merge_primitives_public()` dipakai test lama — pertahankan atau perbarui test-nya.

## 6. Bukan Scope

- Opsi "A vs B" lama (anchor interior) — digantikan pendekatan node ini.
- Perubahan `min_ch`/`min_sep` — sudah diselesaikan AI lain di rekonsiliasi.
- Perubahan MSE/`consensus.py` — kontrak `to_wall_override` dipertahankan.
