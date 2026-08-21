# Implementation Plan — Pattern Edge Detector & Whisper Injection ke Bot

> Berdasarkan riset `scratch/pattern_research.py` (210 EDGE dari 8908 kombinasi).
> Tujuan: bot mendeteksi pola bearish di sesi NY / dekat resistance / multi-pattern secara
> real-time, lalu "membisiki" LLM dengan statistik edge yang TERVALIDASI (n>=100, p<0.05, EV CI>0).

## Ringkasan Temuan (dari riset)

- **Edge terkuat & paling konsisten**: pola bearish (Sweep / Engulfing / Inside Bar / Pin Bar)
  di **sesi New York (21:00-05:00 WIB)** — 48 EDGE, berlaku di hampir semua FX pair.
- **Penambah edge kedua**: dekat **resistance** (bearish) — Bearish Pin Bar GBPCHF WR 69% EV 0.37.
- **Multi-pattern (2+ pola searah dalam 3 bar)**: 20 EDGE — konfirmasi, EV kecil (0.08-0.20).
- **MTF alignment (searah tren HTF) LEMAH** — hanya 2 EDGE. JANGAN dipakai sebagai filter.
- **XAUUSD M15: 0 EDGE** — jangan inject bisikan untuk XAU (kecuali nanti ada riset lanjutan).
- **Harmonic patterns: TIDAK punya edge** (1067 NO-EDGE dari 1068) — jangan diinject.

## Arsitektur

```
main.py (_run_cycle_for_current_symbol)
   │
   ├─ 2.5 baru: pattern_detector.detect_and_whisper(df, symbol, tick)
   │      → deteksi pola di 50 candle terakhir (candle TERAKHIR = bar sinyal)
   │      → cocokkan dengan daftar EDGE tervalidasi (whispers_registry)
   │      → return whisper_str (None kalau tidak ada)
   │
   └─ prepare_prompt(..., whisper_str=whisper_str)   [llm_client.py]
         → inject blok "### PATTERN EDGE RESEARCH (validated statistics)"
         → posisi: setelah macro_str, sebelum lessons_str (informational)
```

## File yang Diubah / Dibuat

### 1. `src/analytics/pattern_detector.py` (BARU)
Detektor pola + matcher bisikan. Mirip logika `scratch/pattern_research.py` tapi versi runtime.

```python
# Fungsi utama
def detect_and_whisper(df, symbol, point_size=0.01) -> str | None:
    """
    df: 50 candle terakhir (sudah close), kolom open/high/low/close
    Return: string bisikan (None kalau tidak ada pola yang match EDGE registry)
    """

# Komponen
def _detect_candle_patterns(df) -> dict[str, bool]:
    """Deteksi pin bar, engulfing, inside bar, sweep (sama seperti riset)."""
    # Pin bar: ekor >= 60% range, body <= 25%
    # Engulfing: body prev berlawanan + menelan
    # Inside bar: high < prev high & low > prev low
    # Sweep: low < swing_low_20 & close > swing_low_20 (bullish), dll

def _session_wib(ts) -> str:
    """'asia' | 'london' | 'ny' | 'other' (sama seperti riset)."""

def _near_resistance(df, atr) -> bool:
    """close dalam 0.5 ATR dari swing_high_20 (shift 1)."""

def _multi_pattern(df, is_bull) -> bool:
    """2+ pola searah dalam 3 bar terakhir."""
```

**Sumber statistik**: hardcode registry dari `scratch/results/whispers_valid.csv`
(atau file JSON terpisah `src/analytics/whisper_registry.json`) — hanya EDGE tervalidasi.
Format per entry:
```json
{
  "symbol": "GBPCHF-ECNc",
  "pattern": "Bearish Sweep",
  "condition": "session=ny",
  "rr": 2.0,
  "wr": 0.555,
  "ev": 0.65,
  "n": 254,
  "p": 0.039
}
```

### 2. `src/core/llm_client.py` (MODIFIKASI)
- Tambah parameter `whisper_str=None` di `prepare_prompt()`
- Inject blok setelah `macro_str`, sebelum `lessons_str`:
```
### PATTERN EDGE RESEARCH (validated statistics - informational, not a rule)
Detected: Bearish Sweep on GBPCHF-ECNc during New York session.
Backtest (n=254, 2yr): Win rate 55.5% at R:R 1:2, EV +0.65 (95% CI [0.48, 0.84]).
This is informational context only - NOT a mandatory trade signal.
```

### 3. `main.py` (MODIFIKASI)
- Di `_run_cycle_for_current_symbol()`, setelah ambil `df` (step 1) & tick (step 2),
  panggil:
```python
whisper_str = None
if getattr(config, "PATTERN_WHISPER_ENABLED", True):
    try:
        from src.analytics.pattern_detector import detect_and_whisper
        whisper_str = detect_and_whisper(df, config.SYMBOL)
        if whisper_str:
            print(f" {UI.tag('PATTERN WHISPER', UI.MAGENTA)} {whisper_str.split(chr(10))[0]}")
    except Exception as e:
        print(f"[PATTERN WHISPER ERROR] {e}")
```
- Teruskan ke `prepare_prompt(..., whisper_str=whisper_str)` di pemanggilan LLM.

### 4. `config.py` (MODIFIKASI)
- Tambah: `PATTERN_WHISPER_ENABLED = _getenv_bool("PATTERN_WHISPER_ENABLED", True)`
- Tambah: `PATTERN_WHISPER_SYMBOLS = os.getenv("PATTERN_WHISPER_SYMBOLS", "")` — filter simbol
  (kosong = semua). Untuk mode XAU only, set `""` otomatis (XAU tidak punya edge).

## Detail Deteksi (harus mirror riset EXACTLY)

| Pola | Definisi (sama dgn `scratch/pattern_research.py`) |
|---|---|
| Pin bar (bull/bear) | ekor >= 0.6×range, body <= 0.25×range, range > 0 |
| Engulfing (bull/bear) | body prev berlawanan, body curr menelan body prev |
| Inside bar (bull/bear) | high < prev high & low > prev low; arah = close vs mid prev |
| Sweep (bull/bear) | low < swing_low_20 & close > swing_low_20 (bull) / high > swing_high_20 & close < swing_high_20 (bear) |

**Kondisi runtime** (harus match riset):
- Sesi WIB: `ny` = hour >= 20 atau hour < 5; `london` = 15-23; `asia` = 7-15
- Near resistance: `abs(close - swing_high_20) <= 0.5 × ATR14` (swing_high_20 = shift(1) rolling 20)
- Multi-pattern: 2+ pola searah dalam 3 bar (termasuk bar ini)

## Alur Deteksi per Cycle

1. Ambil 50 candle close (sudah ada di `df` dari step 1)
2. Hitung ATR14, swing_high/low_20 (dari df)
3. Deteksi 8 pola (pinbar/engulfing/inside/sweep × bull/bear) di **bar terakhir** (df.iloc[-1])
4. Tentukan kondisi bar terakhir: session WIB, near_resistance, multi_pattern
5. Match (symbol, pattern, condition) ke registry EDGE
6. Kalau match → build whisper_str; kalau tidak → None (tidak ada biaya)

## Framing & Guardrails (anti-anchor, sesuai preferensi user)

- **Informational only**: blok bisikan selalu diawali "(informational context - NOT a mandatory
  trade signal, NOT a rule)". LLM bebas HOLD meskipun ada bisikan.
- **Bukan perintah**: tidak pernah bilang "you MUST sell". Hanya statistik.
- **Hanya pola valid**: registry hanya berisi EDGE tervalidasi. CANDIDATE TIDAK dimasukkan.
- **XAU & harmonic TIDAK diinject** (0 edge) — hemat token, hindari anchor palsu.
- **Bisikan dihitung dari candle terakhir yang SUDAH CLOSE** — tidak ada look-ahead.

## Testing (sebelum live)

1. **Unit test detektor** (`tests/test_pattern_detector.py`): buat df sintetis dengan pola
   tertentu, pastikan deteksi benar (pin bar, engulfing, sweep, inside bar).
2. **Golden test registry**: pastikan semua entry registry punya n>=100, p<0.05, EV CI>0
   (validasi silang dengan `scratch/results/results.csv`).
3. **Dry-run**: jalankan bot mode dry-run, pastikan whisper muncul di log & prompt,
   dan tidak ada error.
4. **Kontrol**: `PATTERN_WHISPER_ENABLED=False` → tidak ada perubahan perilaku.

## Risiko & Mitigasi

| Risiko | Mitigasi |
|---|---|
| Overfit historis (edge hilang di live) | Whisper cuma konteks, LLM tetap bebas; bisa dimatikan via config |
| Anchor LLM ke bisikan | Framing "informational only" + bukan perintah |
| Deteksi beda dari riset (mismatch) | Mirror definisi EXACT dari pattern_research.py + unit test |
| Token tambahan | Bisikan cuma 2-4 baris, hanya saat pola match (jarang: beberapa kali/hari/simbol) |
| Bot utama error | Seluruh blok di-try/except; gagal = skip bisikan, bot tetap jalan |

## Estimasi Effort (per file)

| File | Perubahan | Ukuran |
|---|---|---|
| `src/analytics/pattern_detector.py` | Baru | ~150 baris |
| `src/analytics/whisper_registry.json` | Baru (data) | ~30 entry |
| `src/core/llm_client.py` | +10 baris (param + inject) | kecil |
| `main.py` | +15 baris (panggil detektor) | kecil |
| `config.py` | +3 baris (2 config) | kecil |
| `tests/test_pattern_detector.py` | Baru | ~100 baris |

## Urutan Implementasi

1. Buat `src/analytics/pattern_detector.py` (deteksi + matcher) + unit test
2. Generate `whisper_registry.json` dari `scratch/results/results.csv` (filter EDGE)
3. Integrasi `llm_client.py` (param + inject)
4. Integrasi `main.py` (panggil detektor + teruskan)
5. `config.py` (toggle)
6. Dry-run & validasi (whisper muncul, bot normal)
7. Commit ke `dev` (setelah user review plan ini)
