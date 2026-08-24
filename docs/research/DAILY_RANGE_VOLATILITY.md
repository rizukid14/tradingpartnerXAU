# Daily Range Volatility Research
# docs/research/DAILY_RANGE_VOLATILITY.md
# 📊 Riset Volatilitas Harian — Daily Range Mean & Median (D1)

> **Tanggal riset**: 24 Agustus 2026  
> **Sumber data**: MT5 VTMarkets-Live 3, live feed  
> **Periode**: 365 D1 bars terakhir (bar hari ini dilewati)  
> **Script**: scratch/adr_major_minor_xau.py  
> **Pair**: 7 Major + 21 Minor/Cross + XAUUSD (29 pair total)  
> **Pip convention**: Broker 5-digit — 1 pip = 10 pts. XAU: point=0.01, 1 pip = .10 (10 pts)

---

## Hasil Lengkap — Ranking by Mean Daily Range

| # | Pair | Kategori | Mean (pips) | Median (pips) | Selisih Mean-Med |
|---|------|----------|:-----------:|:-------------:|:----------------:|
| 1 | **XAUUSD** | Metal | **954.7** | 780.0 | +174.7 |
| 2 | GBPNZD | Minor/Cross | 153.7 | 137.3 | +16.4 |
| 3 | GBPJPY | Minor/Cross | 144.3 | 124.6 | +19.7 |
| 4 | EURNZD | Minor/Cross | 136.1 | 121.9 | +14.2 |
| 5 | GBPAUD | Minor/Cross | 133.9 | 121.0 | +12.9 |
| 6 | CHFJPY | Minor/Cross | 132.4 | 118.4 | +14.0 |
| 7 | EURAUD | Minor/Cross | 119.6 | 99.5 | +20.1 |
| 8 | **USDJPY** | **Major** | **119.1** | 103.4 | +15.7 |
| 9 | EURJPY | Minor/Cross | 112.8 | 100.5 | +12.3 |
| 10 | GBPCAD | Minor/Cross | 103.2 | 92.0 | +11.2 |
| 11 | AUDJPY | Minor/Cross | 96.5 | 84.2 | +12.3 |
| 12 | **GBPUSD** | **Major** | **89.0** | 81.5 | +7.5 |
| 13 | EURCAD | Minor/Cross | 84.3 | 72.1 | +12.2 |
| 14 | CADJPY | Minor/Cross | 82.6 | 73.9 | +8.7 |
| 15 | NZDJPY | Minor/Cross | 82.4 | 72.6 | +9.8 |
| 16 | **EURUSD** | **Major** | **74.4** | 63.3 | +11.1 |
| 17 | GBPCHF | Minor/Cross | 68.8 | 58.6 | +10.2 |
| 18 | **USDCHF** | **Major** | **64.9** | 57.8 | +7.1 |
| 19 | **USDCAD** | **Major** | **64.4** | 56.4 | +8.0 |
| 20 | AUDCAD | Minor/Cross | 64.2 | 55.8 | +8.4 |
| 21 | AUDNZD | Minor/Cross | 62.0 | 56.4 | +5.6 |
| 22 | NZDCAD | Minor/Cross | 60.5 | 55.0 | +5.5 |
| 23 | **AUDUSD** | **Major** | **59.4** | 53.1 | +6.3 |
| 24 | **NZDUSD** | **Major** | **55.0** | 48.9 | +6.1 |
| 25 | EURCHF | Minor/Cross | 48.1 | 42.5 | +5.6 |
| 26 | AUDCHF | Minor/Cross | 46.2 | 38.7 | +7.5 |
| 27 | CADCHF | Minor/Cross | 39.9 | 34.2 | +5.7 |
| 28 | NZDCHF | Minor/Cross | 39.5 | 34.8 | +4.7 |
| 29 | EURGBP | Minor/Cross | 37.3 | 32.1 | +5.2 |

---

## Analisis per Kategori

### 🏆 Top 5 Tertinggi (FX saja)
1. **GBPNZD** — 153.7 pips mean, 137.3 median. Range lebar, tapi spread bisa tebal.
2. **GBPJPY** — 144.3 pips mean. Sangat liquid, spread tipis di jam London-NY.
3. **EURNZD** — 136.1 pips mean. Besar tapi spread lebih lebar dari GBPJPY.
4. **GBPAUD** — 133.9 pips mean. **Sudah ada di pool bot** ✅
5. **CHFJPY** — 132.4 pips mean. Safe-haven double, volatile karena risk-on/off swings.

### Major Ranking by Volatilitas
| # | Major | Mean | Median |
|---|-------|:----:|:------:|
| 1 | USDJPY | 119.1 | 103.4 |
| 2 | GBPUSD | 89.0 | 81.5 |
| 3 | EURUSD | 74.4 | 63.3 |
| 4 | USDCHF | 64.9 | 57.8 |
| 5 | USDCAD | 64.4 | 56.4 |
| 6 | AUDUSD | 59.4 | 53.1 |
| 7 | NZDUSD | 55.0 | 48.9 |

### ⚠️ Pool Bot Saat Ini — Posisi Volatilitas
3 dari 6 pair aktif di bot ada di **bottom 5** semua pair:

| Pair | Mean | Rank | Catatan |
|------|:----:|:----:|---------|
| GBPUSD | 89.0 | #12 | ✅ Cukup baik |
| GBPAUD | 133.9 | #5 | ✅ Sangat baik |
| AUDCAD | 64.2 | #20 | ⚠️ Menengah |
| EURCHF | 48.1 | #25 | 🔴 Rendah |
| AUDCHF | 46.2 | #26 | 🔴 Rendah |
| CADCHF | 39.9 | #27 | 🔴 Rendah |

**Implikasi**: CHF crosses (EURCHF, AUDCHF, CADCHF) punya range sempit → cost komisi + spread jadi proporsi lebih besar dari total gerak harga → edge lebih tipis.

### Kandidat Upgrade (volatilitas lebih tinggi)
Jika ingin ganti 1-2 CHF crosses dengan pair lebih volatile:
- **GBPJPY** (144.3 pips) — liquid, spread tipis
- **EURJPY** (112.8 pips) — liquid, vol tinggi
- **GBPCAD** (103.2 pips) — medium spread, vol ok
- **EURCAD** (84.3 pips) — stabil, vol cukup
- **AUDJPY** (96.5 pips) — liquid, AUD-JPY dynamic

### Insight Statistik
- **Mean > Median** di semua pair → distribusi right-skewed (event spike FOMC/NFP/risk-off menarik mean ke atas)
- Gap mean-median terbesar: **XAUUSD** (+174.7), **EURAUD** (+20.1), **GBPJPY** (+19.7)
- Gap mean-median terkecil: **NZDCHF** (+4.7), **EURGBP** (+5.2), **NZDCAD** (+5.5) → distribusi lebih simetris

---

## Konvensi Pip

| Jenis | Point | 1 Pip | Keterangan |
|-------|-------|-------|------------|
| FX 5-digit non-JPY | 0.00001 | 10 pts | EURUSD, GBPUSD, dll |
| FX 5-digit JPY | 0.001 | 10 pts | USDJPY, EURJPY, dll |
| XAUUSD (Gold) | 0.01 | 10 pts | 1 pip = .10 per lot mini |

---

*Script query: scratch/adr_major_minor_xau.py (DAYS=365, skip bar hari ini)*
