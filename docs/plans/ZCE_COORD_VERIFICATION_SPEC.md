# ZCE/MSE Coordinate Verification — Lapis 1–3 Execution Spec

> Status: READY FOR EXECUTION — ditulis 2 September 2026 oleh planner.
> Tujuan: membuktikan (atau membantah) bahwa MSE & ZCE membaca koordinat
> (F1/C1/F2/C2) dengan benar dan konsisten antar-horizon, di akun LIVE.
> Bukan mengubah logika produksi — murni script verifikasi sekali pakai di `scratch/`.

## Konvensi unit (WAJIB — jangan hardcode)

Sumber kebenaran konversi = `atlas_dna.py` + pola MSE baris 457–459:

```python
pt = info.point  # EURUSD 0.00001, JPY 0.001, XAU/BTC 0.01
digits = info.digits  # FX 5, JPY 3, XAU/BTC 2
pip_div = (10 if digits in (3, 5) else 1)  # 100 poin = 10 pips di 5-digit
pips = abs(a - b) / pt / pip_div
step_psych = get_symbol_step(symbol)  # EURUSD -> 0.0100 (100 pips)
```

Cara ambil `info`: `config.mt5.symbol_info(sym)` (sudah connected via terminal default —
jangan `mt5.initialize(login=...)`, pakai `mt5.initialize()` polos seperti `_zce_parity.py`).

## Simbol uji (8, mewakili semua kelas)

`EURUSD, GBPUSD, USDJPY, EURJPY, AUDUSD, EURGBP, GBPCHF, NZDUSD`

## File yang dibuat agent

1. `scratch/verify_zce_coords.py` — script utama (Lapis 1 + 2 + 3 dalam satu run).
2. Output: `scratch/verify_zce_coords_report.md` — laporan yang bisa dibaca manual.
3. `scratch/` di-.gitignore → hapus kedua file setelah verifikasi selesai.

## Alur script

### 0. Setup (koneksi + import)

```python
import config  # memuat .env: ZCE_ENABLED=true, ZCE_MODE=full
from src.analytics.macro_strategic_engine import MacroStrategicEngine
from src.analytics.zone_confluence_engine import ZoneConfluenceEngine
from src.indicators.atlas_dna import get_symbol_step
import mt5_connector dari config  # config.mt5 sudah ter-initialize oleh main? — jika tidak:
config.mt5.initialize()  # polos, tanpa credential (terminal sudah login)
```

Catatan: kalau `config.mt5` belum ter-init saat import, panggil `config.mt5.initialize()`.
Jangan panggil dua kali — guard dengan `config.mt5.terminal_info() is None`.

### 1. Fetch data multi-TF per simbol (sama persis dengan `_refresh_zce_rotation` baris 900–905)

```python
tf_cfg = [("MN1", TIMEFRAME_MN1, 100), ("W1", TIMEFRAME_W1, 200),
          ("D1", TIMEFRAME_D1, 350), ("H4", TIMEFRAME_H4, 400),
          ("H1", TIMEFRAME_H1, 520), ("M30", TIMEFRAME_M30, 600)]
# via config.mt5.copy_rates_from_pos(sym, tfid, 0, cnt) -> pd.DataFrame
```

Wajib `config.mt5.symbol_select(sym, True)` dulu. Skip simbol yang H1 < 60 bar.

### 2. Panggil engine — JANGAN ubah state engine global

Pola aman (hindari side-effect ke cache internal instance bersama):

```python
# ZCE: instance fresh per simbol (komputasi murni dari dfs, tidak ada cache lintas-simbol yang wajib)
zce = ZoneConfluenceEngine()
zmap = zce.compute_zone_map(sym, dfs, point_size=pt, digits=digits)  # ZoneMapResult

# MSE baseline (TANPA zce_walls) — compute_directive langsung, bukan get_directive (hindari cache):
mse_base = MacroStrategicEngine().compute_directive(sym, mt5_connector=conn, zce_walls=None)

# MSE + override ZCE (simulasi jalur produksi): bangun zce_walls dari zmap
zce_walls = {"enable": bool(zmap.imm_floor_f1 and zmap.imm_ceiling_c1),
             "imm_ceiling_c1": zmap.imm_ceiling_c1,
             "imm_floor_f1": zmap.imm_floor_f1,
             "deep_ceiling_c2": zmap.deep_ceiling_c2,
             "deep_floor_f2": zmap.deep_floor_f2}
mse_zce = MacroStrategicEngine().compute_directive(sym, mt5_connector=conn, zce_walls=zce_walls)
```

Catatan agent: sesuaikan nama field dengan dataclass aktual `ZoneMapResult` dan
`MacroStrategicDirective` (sudah diverifikasi ada: `imm_floor_f1`, `imm_ceiling_c1`,
`deep_ceiling_c2`, `deep_floor_f2`, `action_tier`/tier, `macro_bias_score`). Baca definisi
dataclass dulu sebelum akses field — jangan menebak.

## Lapis 1 — Parity vs level fisik (deteksi "diam-diam salah")

Untuk tiap simbol, output baris per engine:

```
SYMBOL  EURUSD  bid=1.16123  ATR_H1=0.00065 (6.5 pips)  step=0.0100 (100 pips)
  MSE-base : F1=1.15780 (34.3p)  C1=1.16153 (3.0p)  C2=...  tier=...
  ZCE-map  : F1=1.15780 (34.3p)  C1=1.16108 (1.5p)  C2=...  grade=...
  MSE+ZCE  : F1=... C1=... tier=...   <- harus == ZCE-map jika override aktif
```

Jarak dalam pips = `abs(harga - level)/pt/pip_div`.

**Cara verifikasi manual (10 menit/simbol di chart MT5):**
1. Buka EURUSD H1, pastikan C1/F1 yang dilaporkan = dinding fisik terdekat yang TAMPAK
   (swing high/low, OB D1/W1, angka psikologis). Kalau level jatuh di tengah "hutan"
   candle tanpa makna struktural → koordinat SALAH.
2. Periksa `grade` ZCE: C1/F1 yang dipilih harusnya grade >= G2 kalau ada dinding G2/G3
   di dekat harga. Grade G1 diabaikan padahal ada G2 lebih dekat → indikasi bug prioritas.
3. Cek ZCE `conflict_flag` (ScaleLadder): kalau `LOCAL_DISCOUNT_MACRO_PREMIUM` ter-set,
   catat — itu kondisi eksklusi yang sah, bukan bug.

## Lapis 2 — Invariant otomatis (HARD ASSERT, 0 toleransi, fail = BUG)

Untuk tiap simbol, pada ZCE-map DAN MSE (base & +zce):

```
INV-1  F2 < F1 < harga < C1 < C2                  (ladder tidak inverted / tidak None di tengah)
INV-2  harga - F1 <= 2.0*ATR_H1  DAN  C1 - harga <= 2.0*ATR_H1
       -> level "kabur" jauh = curiga (bug tipe 800-pips lama pasti tertangkap di sini)
INV-3  C2 - C1 >= 0.5*ATR_H1  DAN  F1 - F2 >= 0.5*ATR_H1   (deep layer punya jarak bermakna)
INV-4  kalau zce_walls.enable: MSE+ZCE.F1/C1 == ZCE-map.F1/C1  (override benar-benar applied)
INV-5  action_tier konsisten: F1/C1 valid -> tier != "HARD_BLOCK" tanpa alasan forbidden trap
```

Format: tiap invariant PASS/FAIL per simbol. FAIL berapa pun = script exit code 1 +
laporan menandai `[BUG]`.

## Lapis 3 — Multi-horizon ordering (hierarki TF)

Gunakan `ScaleLadder.pos_by_horizon` ZCE (posisi harga 0..1 per horizon H1
[50,100,150,250] dsb — baca dataclass aktual) + klaster per TF dari ZCE:

```
INV-H1  Tidak ada "loncat horizon": C1/F1 terpilih harus berasal dari horizon yang
        TIDAK lebih jauh dari alternatif horizon lebih rendah yang valid dalam 0.5*ATR.
INV-H2  level M30/H1 (mikro) berada DI DALAM kisaran D1/W1/MN1 (makro) dengan toleransi
        overlap 0.5*ATR_H1 — bukti hierarki, bukan 6 TF saling tabrak.
```

Catatan agent: kalau dataclass ZCE tidak mengekspos horizon asal tiap klaster terpilih
(`ZoneCluster.horizon_max` ada — pakai itu), derive INV-H1/H2 dari `clusters` mentah:
cocokkan F1/C1 terpilih dengan klaster yang `band_low <= level <= band_high`, baca
`horizon_max`-nya. Kalau horizon_max klaster F1 = 250 padahal ada klaster horizon 50
dalam 0.5*ATR → catat sebagai WARN (bukan FAIL) — bisa jadi valid (skor density lebih
tinggi), tapi harus terlihat manual di laporan.

## Output laporan (`verify_zce_coords_report.md`)

```
# ZCE/MSE Coordinate Verification — <tanggal> <jam WIB>
Simbol uji: 8 | ZCE_MODE=full | spread & ATR dari live

## Ringkasan
INV-1..5 : 8/8 PASS (atau FAIL di mana)
INV-H1/H2: X PASS, Y WARN, Z FAIL
Total [BUG]: N   -> kalau N>0: jangan live-trade penuh sampai koordinat dibenahi

## Detail per simbol
<blok Lapis 1 untuk tiap simbol, termasuk grade & conflict_flag>

## Level yang perlu dicek manual di chart
| Simbol | level | jarak(pips) | tag/grade | dicek? |
```

## Kriteria lolos

- **LOLOS**: INV-1..5 100% PASS + INV-H1/H2 tanpa FAIL (WARN boleh) + manual spot-check
  3 dari 8 simbol mengonfirmasi C1/F1 = dinding fisik nyata.
- **TIDAK LOLOS**: satu saja INV FAIL, atau manual spot-check menemukan level
  non-struktural. Stop — lapor ke planner, jangan lanjut ke validasi eksekusi (Lapis 4).

## Larangan

- DILARANG mengubah file produksi (`src/`, `config.py`, `.env`) dari script ini.
- DILARANG mengirim order MT5 apa pun (read-only: copy_rates/symbol_info/symbol_select).
- DILARANG hardcode level/konversi — selalu dari `symbol_info` + `atlas_dna`.
- Hapus `scratch/verify_zce_coords.py` & report setelah selesai (folder di-gitignore).
