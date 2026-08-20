# Trading Dashboard — Design Spec

**Tanggal:** 2026-08-09
**Status:** Approved (user)
**Scope:** Dashboard statistik kualitas trade, kualitas sinyal LLM, dan statistik standar dari log trading bot MT5.

## 1. Tujuan

Memberikan tampilan web lokal (satu file HTML) yang menampilkan:
- Kualitas trade (performa standar, efektivitas SL/TP, riwayat per-trade, lessons & post-mortem)
- Kualitas sinyal/LLM (statistik keputusan & agreement, akurasi prediksi per model, kalibrasi confidence)
- Statistik standar (win rate, expectancy, max drawdown, equity curve, dll)

Sumber data: **hanya `logs/trading_bot.log` + `data/*.json`** (tanpa query MT5 langsung). Refresh **on-demand** — generate ulang dashboard tiap halaman dibuka.

## 2. Sumber Data

| File | Isi |
|---|---|
| `logs/trading_bot.log` | Log bot: banner (era/akun/model), cycle, keputusan model, konsensus, order, latency, trailing/BE, post-mortem |
| `data/risk_state.json` | `known_closed` (tiket closed), `consecutive_losses`, `recovery_mode`, `last_trade_time` |
| `data/memory_lessons.json` | Lessons per symbol + `evaluated_tickets` |
| `data/decision_memory.json` | Keputusan terakhir per symbol + timestamp + reasoning |
| `data/dynamic_rules.json` | Mode konsensus (defensif/optimal) |
| `data/forecast_cache.json` | Bias forecast aktif (informational) |

## 3. Arsitektur

```
dashboard.py                 # Builder (root) — jalankan: python dashboard.py
dashboard.html               # Hasil generate (artifact, git-ignored)
tests/test_dashboard.py      # Test parser & metrics
```

`dashboard.py` berisi 3 komponen terpisah agar bisa di-test:

1. **`parse_log(path)`** → list event terstruktur:
   - `session` (akun login, era model dari banner)
   - `cycle` (timestamp, symbol, harga bid)
   - `model_decision` (model, signal, confidence, sl_points, tp_points)
   - `consensus` (approved/rejected, skor, threshold, model setuju)
   - `order` (ticket, symbol, side, lot, entry, sl, tp)
   - `trade_close` (ticket, symbol, pnl — dari `[POST-MORTEM]`)
   - `latency` (per model)
   - `trailing` / `break_even` / `partial_close` (aktivasi)
   - `forecast` (bias, invalidation)
   - `fallback` / `error`

2. **`compute_metrics(events, state)`** → dict besar berisi semua KPI (murni kalkulasi).

3. **`render_html(metrics)`** → string `dashboard.html` (template + data JSON embedded).

## 4. Strategi Parsing

- **Sesi campur**: log berisi sesi demo (`1157958`, ticket `568xxx`) + live (`27556325`, ticket `1159xxx`), era DeepSeek + era Claude. Parser menandai tiap cycle dengan **era + akun** dari banner (`Models: ...`) dan line `Mencoba masuk ke akun X`. Default menampilkan **era aktif** = era dari banner **terakhir** di log (era yang sedang berjalan saat ini), dengan toggle untuk menampilkan semua era.
- **Timestamp jarang**: hanya `[CYCLE START]` yang punya datetime. Event dalam blok cycle **mewarisi timestamp cycle-nya**. Event di luar cycle (trailing/BE) dikelompokkan ke cycle terdekat atau `unknown_time`.
- **Trade outcome**: entry (`[MT5] Mengirim order...` → ticket, symbol, side, lot, entry, sl, tp) ↔ close (`[POST-MORTEM]` → ticket, pnl) ↔ `risk_state.known_closed`, dicocokkan per ticket.
- **Keterbatasan jujur**:
  - Tanpa timestamp per baris, time-series & durasi trade hanya seakurat urutan cycle.
  - Exit price & "kena SL/TP" tidak bisa dipastikan dari log — hanya statistik jarak SL/TP.

## 5. Metrik (KPI)

### A. Ringkasan Umum (header)
- Akun (live/demo), simbol aktif, era model, rentang waktu data, total cycle, total order, total P/L.

### B. Kualitas Trade
- Total trade, win/loss/BEP (BEP = |P/L| ≤ $0.04), win rate (BEP excluded), profit faktor, expectancy ($/trade), average win, average loss, max drawdown, per-symbol breakdown, equity curve (P/L kumulatif + balance awal).

### C. Efektivitas SL/TP
- Distribusi jarak SL (bucket), win rate per bucket jarak SL, distribusi R:R (TP/SL), jumlah aktivasi trailing/break-even/partial close, SL/TP vs ATR floor (2× spread, 1× ATR) — dihitung **hanya untuk cycle yang punya data spread/ATR**, sisanya ditandai N/A.

### D. Kualitas Sinyal & LLM
- Distribusi keputusan BUY/SELL/HOLD per model + gabungan.
- Agreement rate antar model (≥2 searah, 3/3).
- Akurasi per model: signal arah vs outcome trade (HOLD saat trade = "miss").
- Kalibrasi confidence: rata-rata confidence saat win vs loss, korelasi confidence vs hasil, distribusi confidence per model.
- Hit rate konsensus: approve → trade, reject → HOLD.

### E. Lessons & Post-Mortem
- Lessons per symbol (`memory_lessons.json`), win/loss per lesson theme, ticket ter-evaluasi.

### F. Tabel per-trade
- Kolom: ticket, symbol, side, lot, entry, SL, TP, exit (jika ada), P/L, durasi (jika ada), era, status (open/closed). Sortable.

## 6. Rendering & Interaktivitas

- Satu file `dashboard.html`: data JSON embedded (script tag), Chart.js dari CDN, CSS + JS inline, tema gelap.
- Layout: header ringkas → grid kartu KPI → chart (equity, distribusi keputusan, akurasi model, kalibrasi confidence) → tabel per-trade (sortable) → lessons.
- Filter murni JS (tanpa server): era (semua/aktif), symbol (XAU/BTC/semua), rentang waktu (7d/30d/semua) — memicu re-render chart + tabel.

## 7. Error Handling

- `dashboard.py` read-only terhadap log; `errors='replace'`; tetap jalan walau log sedang ditulis bot.
- JSON rusak/partial (bot sedang menulis) → parse defensif + warning di dashboard.
- Generate gagal → pesan error jelas di terminal, exit code non-zero.

## 8. Testing

- `tests/test_dashboard.py` (mengikuti test runner proyek — cek pytest/unittest saat implementasi):
  - Parser: fixture log kecil → event benar.
  - Metrics: fixture events → KPI benar.
  - Renderer: output HTML valid, berisi id penting.

## 9. Integrasi

- Tidak menyentuh `main.py` / bot (read-only).
- README: tambah command `python dashboard.py` → buka `dashboard.html`.
- (Opsional, nanti) bisa di-cron tiap jam.
