# GLM Critical Review — Structural Holes & Research Priorities
# 🔴 GLM Critical Review — Structural Holes & Research Priorities

> **Sumber**: Analisis kritis dari GLM (eksternal AI review) — 24 Agustus 2026  
> **Konteks**: Review pool 6-simbol paralel FX H1 swing setelah launch branch xau_pairs

---

## Priority Stack (Urut Penting)

### 🔴 #1 — Risiko Korelasi Antar-Pair *(HOLE STRUKTURAL TERBESAR)*

**Masalah**:
Pool saat ini share eksposur mata uang besar:
- AUD: GBPAUD + AUDCAD + AUDCHF
- CHF: EURCHF + AUDCHF + CADCHF
- GBP: GBPUSD + GBPAUD

Kalau 3–4 pair fire arah yang sama dalam satu jam → bukan 4 trade independen, itu **satu bet besar yang disamarkan sebagai 4 posisi**. Cap "max 6 posisi" tidak melihat ini sama sekali.

**Yang perlu di-research**:
- Hard gate eksposur net per-currency (contoh: max 2 posisi searah per mata uang yang sama)
- Correlation matrix antar pair di pool (rolling, bukan statis)
- Net currency exposure tracker real-time sebelum order dikirim

**Verdict GLM**: Ini risiko nyata, bukan optimasi kosmetik. Paling prioritas.

---

### 🟠 #2 — Spread Cap Flat 50 pts Tidak Adil Antar-Pair

**Masalah**:
EURCHF/CADCHF volatilitas rendah (mean range 40–48 pips/hari). Spread 50 pts di sana proporsinya **jauh lebih berat** dibanding di GBPAUD (134 pips/hari). Filter flat ini mendiskriminasi pair slow-mover.

**Yang perlu di-research**:
- Ganti spread cap flat dengan **spread-to-ATR ratio** per pair
- Contoh threshold: tolak kalau spread > 15% ATR_H1
- Data ATR sudah tersedia di pipeline, tinggal hitung

**Verdict GLM**: Data sudah ada, zero engineering cost.

---

### 🟡 #3 — Asimetri Konsensus Dual vs Triple Mode

**Masalah**:
- **Dual mode** (00:00–18:59 & 22:01–23:59): score ≥1.0 → praktis butuh kedua model sepakat (bar tinggi)
- **Triple mode** (19:00–22:00): 2 dari 3 cukup → bar lebih rendah

Kualitas/keketatan entry berbeda tergantung jam, dan **belum pernah diukur** mana yang lebih profitable.

**Yang perlu di-research**:
- Pisahkan winrate/PnL trade berdasarkan window lahirnya (Dual vs Triple)
- Data sudah ada di data/trading_bot.log + deal history MT5
- Zero cost, bisa dikerjain sekarang

**Verdict GLM**: Quick win. Bisa dikerjain sambil nunggu data.

---

### 🟡 #4 — Swap Cost Belum Diperhitungkan di H1 Swing

**Masalah**:
Bot sadar swap hanya untuk BTC ("bebas swap overnight"). Tapi 6 pair FX H1 swing **akan sering hold lewat midnight** → kena swap long/short. CHF pairs terkenal swap negatif besar di sisi tertentu.

Edge 24–37 "EDGE" per pair di riset itu **gross** — belum dikurangi biaya carry.

**Yang perlu di-research**:
- Query swap rate per pair dari MT5 (symbol_info.swap_long, swap_short)
- Estimasi rata-rata hold duration dari deal history
- Masukkan carry cost ke kriteria seleksi pair

---

### 🟡 #5 — Validasi Impact Fitur Momentum Summary

**Masalah**:
Blok momentum summary di prompt belum terbukti mengubah keputusan ke arah lebih baik — bisa jadi cuma nambah token tanpa value nyata.

**Yang perlu di-research**:
- Setelah 1–2 hari jalan, cek log: apakah blok ini benar-benar mengubah keputusan?
- Bandingkan trade dengan/tanpa blok tersebut aktif
- Prinsip: jangan terima fitur begitu saja tanpa audit decision-impact

---

### 🔵 #6 — Session Lot Multiplier Perlu Kalibrasi Ulang

**Masalah**:
Multiplier Tokyo ×0.7 / Overlap ×1.2 didesain untuk mode M5 scalping XAU. Sekarang FX H1 swing — entry cluster di candle close, **dinamika sesinya beda**.

**Yang perlu di-research**:
- Verifikasi apakah multiplier masih relevan untuk H1
- Atau kalibrasi ulang dari data actual hold time + PnL per sesi

---

## Tidak Perlu Ditambah (GLM Verdict)

- ❌ Timeframe ekstra di MTF — sudah pernah dibahas, tetap stand
- ❌ Quant math tambahan — sudah OFF dengan alasan kuat
- ❌ API kalender berbayar — tidak sepadan

---

## Rekomendasi Aksi

| Priority | Item | Effort | Status |
|----------|------|--------|--------|
| 🔴 Kritis | Currency exposure gate (#1) | Medium | [ ] To-do |
| 🟠 Tinggi | Spread-to-ATR ratio gate (#2) | Low | [ ] To-do |
| 🟡 Medium | Dual vs Triple winrate split (#3) | Low | [ ] To-do |
| 🟡 Medium | Swap cost analysis (#4) | Low | [ ] To-do |
| 🟡 Medium | Momentum feature audit (#5) | Low | [ ] Ongoing |
| 🔵 Rendah | Session multiplier recalibration (#6) | Medium | [ ] Backlog |

---

*Catatan: Review ini dari GLM sebagai critic eksternal. Tidak semua point harus langsung diimplementasi — tapi #1 dan #2 adalah structural risk nyata yang layak diprioritaskan.*
