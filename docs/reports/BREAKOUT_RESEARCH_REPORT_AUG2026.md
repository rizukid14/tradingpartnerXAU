# Breakout & Liquidity Sweep Research Report
**Tanggal**: 27 Agustus 2026
**Dataset**: FBS MT5 — 22 simbol, H1 10.7 tahun (66k bar/pair)
**Metodologi**: Exact limit fill, spread included, D1 EMA200 gate, R:R 2.5:1

---

## 1. Latar Belakang & Motivasi

Tiga kasus gagal live (GU, XAU, EU) terjadi akibat misidentifikasi antara:
- **Liquidity Sweep** (price sengaja menembus zone untuk flush stop, lalu reversal)
- **Genuine Breakout** (price benar-benar keluar zona dengan momentum continuation)

Riset ini membangun framework sistematis untuk membedakan keduanya, menguji secara empiris di 10.7 tahun data, dan menghasilkan spesifikasi konteks yang harus dikirim ke LLM Veto setelah sinyal awal muncul.

---

## 2. Framework 5 Dimensi Klasifikasi Breakout

| Dimensi | Indikator | File |
|---|---|---|
| **Kualitas Candle** | Body ratio, wick ratio, velocity ATR, engulfing | `candle_quality.py` |
| **Umur Zona** | Bars since most-recent extreme (range_age_bars) | `wave_regime.py` |
| **Tipe Break** | CHoCH vs BOS | `lux_smc.py` |
| **Timing Retest** | Berapa bar sejak break sampai retest | `sweep_detector.py` |
| **Konteks H4/D1** | OB, FVG, EQH/EQL, EMA50 H4, EMA200 D1 | `lux_smc.py` + `macro_analyst.py` |

---

## 3. Multi-Strategy Framework (4 Strategi Aktif)

### 3.1 Strategy A — MULTI-TOUCH Breakout + Retest (Primary)

Zone ditest 2+ kali dalam 40 bar terakhir. Ketika tembus, pasang LIMIT di level zone (jangan chase). Retest datang dalam 3-4 bar rata-rata.

**Zone Definition terbaik**: H1 Cluster Zone (median wicks clustering dalam +/-0.5 ATR)

**Hasil Backtest**:

| Metric | Nilai |
|---|---|
| Total Trades | 23,173 |
| PF Agregat | **1.11** |
| Net R | **+2,474R** |
| Pair Profitable | **21/22** |
| AvgRetest | 3-4 bar |

**Pair terbaik**:

| Pair | WR% | PF | NetR |
|---|:---:|:---:|:---:|
| CADJPY | 34.3% | 1.35 | +246R |
| EURJPY | 33.0% | 1.29 | +202.5R |
| USDJPY | 32.9% | 1.29 | +199R |
| CHFJPY | 32.9% | 1.29 | +205.5R |
| XAUUSD | 30.3% | 1.11 | +73.5R |
| EURGBP | 30.7% | 1.15 | +102R |

**Pair yang GAGAL** (PF < 1.0): EURCHF saja (SNB intervention anomaly).

```
Entry Type : SELL/BUY LIMIT di level zone
SL         : di luar zone boundary + 0.65 x ATR1
TP         : 2.5 x |entry - SL|
Max Wait   : 15 bar (batalkan jika retest tidak datang)
Gate       : D1 EMA200 trend harus aligned
```

---

### 3.2 Strategy B — CHoCH Squeeze Retest (Trend-Following)

Squeeze >= 5 bar berturut selesai, momentum candle break Swing H/L, wait retest ke breaker. D1 gate wajib.

| Metric | Nilai |
|---|---|
| Total Trades | 3,784 |
| PF Agregat | 0.96 |
| Pair Profitable | 8/22 |

Pair profitable: AUDJPY, CADJPY, EURCHF, EURGBP, EURJPY, EURUSD, USDCAD, USDJPY

**Catatan**: Gunakan sebagai konfirmasi momentum ke Strategy A, bukan sinyal primer.

---

### 3.3 Strategy C — Liquidity Sweep Counter (Mean Reversion)

Candle wick >= 40% dari range menembus H4 EMA50, lalu close kembali dalam zone (CHoCH). Counter trade di arah reversal.

| Metric | Nilai |
|---|---|
| Total Trades | 30,216 |
| PF Agregat | 0.91 |
| Pair Profitable | 3/22 |

Hanya valid di: AUDJPY (PF 1.04), EURJPY (PF 1.00), USDCAD (PF 1.02)

**Temuan kritis**: Di EUR/GBP crosses, wick di H4 EMA50 lebih sering continuation. Jangan diperluas ke semua pair.

---

### 3.4 Strategy D — Super Compression Direct Chase (Rare Setup)

Range age > 72 jam (SUPER compression) + break candle kuat (body >= 55%, wick <= 30%). Entry chase next bar open.

| Metric | Nilai |
|---|---|
| Total Trades | 998 (~45/pair/10yr) |
| PF Agregat | 0.96 |
| Pair Profitable | 8/22 |

Pair yang profit di SUPER tapi GAGAL di YOUNG:

| Pair | YOUNG PF | SUPER PF |
|---|:---:|:---:|
| EURCHF | 0.71 | **1.52** |
| GBPCAD | 0.80 | **1.52** |
| CHFJPY | 0.85 | **1.39** |
| EURCAD | 0.85 | **1.30** |

Frekuensi: 4-5 trade/tahun/pair. Gunakan sebagai high-conviction rare setup saja.

---

### 3.5 Matriks 5 Core Market Archetypes (M1–M5 Full Integration)

| Kode | Model / Arketipe | Tipe Setup | Mekanisme & Trigger |
|:---:|---|---|---|
| **M1** | **London/Asian Judas Sweep** | *Liquidity Sweep Reversal* | Sweep wick pada Asian High/Low atau key level saat open London/Tokyo lalu reversal kembali ke range (CHoCH). |
| **M2** | **Trend-Aligned Pullback** *(Master Strategy)* | *Trend-Following Mean Reversion* | Membeli di harga **diskon** H1/M30 (pullback ke EMA50/FVG) yang **searah** dengan arus ekspansi D1/H4 EMA200. *(Hukum Fraktal: Macro Expands vs Micro Mean-Reverts).* |
| **M3** | **NY ADR Exhaustion** | *Extreme Mean Reversion* | Pergerakan harga ekstrem $\ge 100\%\text{--}120\%$ ADR harian di overlap Sesi London-NY, target snapback ke median Dealing Range. |
| **M4** | **SMC Displacement & OB Mitigation** | *Smart Money Concepts* | Terjadi *Change of Character* (CHoCH) dengan displacement candle kencang meninggalkan Unmitigated Order Block (OB) & Fair Value Gap (FVG), entry saat mitigasi retest. |
| **M5** | **Multi-Touch Cluster Breakout & Delayed Retest** *(Temuan Baru)* | *Structural Breakout Continuation* | Zona support/resistance cluster yang dites $\ge 2\times$, ditembus candle momentum $(\ge 55\%\text{ body})$, lalu eksekusi **Limit Order saat retest** (rata-rata 3–4 bar). *(PF 1.11, 21/22 pair profitable)*. |

---

## 4. Perbandingan Antar Strategy

| Strategy | PF Agg | Pair Prof | Freq/Pair/Yr | Penggunaan |
|---|:---:|:---:|:---:|---|
| A: Multi-Touch (M5) | 1.11 | 21/22 | ~215/yr | Primary signal |
| B: CHoCH Squeeze | 0.96 | 8/22 | ~35/yr | Momentum confirmation |
| C: Liquidity Sweep (M1) | 0.91 | 3/22 | ~281/yr | JPY/CAD pairs only |
| D: Super Compress | 0.96 | 8/22 | ~5/yr | High-conviction rare |

**Kesimpulan**: Strategy A (M5) adalah satu-satunya dengan edge positif agregat + sample size proper.

---

## 5. Temuan Kritis: "Instant Retest Law" di FX

Dari 10.7 tahun data H1:
- Setelah break dari zona yang ditest 2+ kali -> price SELALU kembali ke zone dalam 3-4 bar H1
- Berlaku konsisten di 21 dari 22 pair

Implikasi:
1. Setelah melihat multi-touch break -> langsung pasang limit di zone level
2. Jika setelah 15 bar tidak terisi -> batalkan (bukan multi-touch genuine)

---

## 6. Spesifikasi Konteks untuk LLM Veto System

Setelah sinyal Stage 1 muncul, LLM Veto (DeepSeek sebagai Devil's Advocate) harus menerima:

### 6.1 Identitas Setup
```json
{
  "setup_type": "MULTI_TOUCH | CHoCH_SQUEEZE | LIQUIDITY_SWEEP | SUPER_COMPRESSION",
  "symbol": "GBPUSD-ECNc",
  "timeframe_exec": "H1",
  "direction": "BUY | SELL",
  "entry_price": 1.27450,
  "sl_price": 1.27280,
  "tp_price": 1.27875
}
```

### 6.2 Zone Quality Metrics
```json
{
  "zone_level": 1.27450,
  "zone_top": 1.27480,
  "zone_bottom": 1.27420,
  "zone_prior_touches": 3,
  "zone_touch_timespan_bars": 28,
  "zone_definition": "H1_CLUSTER | H1_EXACT",
  "zone_body_or_wick": "WICK_DOMINANT | BODY_DOMINANT"
}
```

### 6.3 Candle Quality (Break Candle)
```json
{
  "body_ratio": 0.72,
  "upper_wick_pct": 0.15,
  "lower_wick_pct": 0.13,
  "velocity_atr": 0.95,
  "is_engulfing": false,
  "verdict": "STRONG_BREAK | WEAK_BREAK | SUSPECT_SWEEP | INDECISION",
  "sweep_side": "top | bottom | null"
}
```

### 6.4 Kompresi & Umur Zona
```json
{
  "range_age_bars": 48,
  "range_age_hours": 48.0,
  "range_age_class": "SUPER | MATURE | YOUNG",
  "squeeze_bars_before_break": 12,
  "effective_sqz_bars": 12,
  "wave_regime": "SUPER_COMPRESSION_THRUST | MATURE_SQUEEZE | YOUNG_OSCILLATION"
}
```

### 6.5 Timing Retest
```json
{
  "bars_since_break": 2,
  "retest_type": "INSTANT | QUICK | DELAYED | NONE",
  "limit_fill_probability": "HIGH | MEDIUM | LOW"
}
```

> INSTANT retest (< 2 bar) = VETO flag "kemungkinan sweep bukan breakout"

### 6.6 Konteks Struktural H4/D1
```json
{
  "h4_ema50": 1.27300,
  "h4_ema50_bias": "PRICE_ABOVE | PRICE_BELOW",
  "d1_ema200": 1.26800,
  "d1_trend": "BULLISH | BEARISH | SIDEWAYS",
  "h4_ob_type": "BULLISH | BEARISH | NONE",
  "h4_ob_top": 1.27500,
  "h4_ob_bottom": 1.27350,
  "h4_fvg_present": true,
  "h4_fvg_top": 1.27420,
  "h4_fvg_bottom": 1.27380,
  "h4_eqh": 1.27600,
  "h4_eql": null,
  "near_htf_magnet": "EQH | EQL | OB | FVG | NONE"
}
```

### 6.7 Skor Konsensus Awal (Stage 1 Scanner Output)
```json
{
  "score_breakout": 65,
  "score_sweep": 20,
  "preliminary_verdict": "BREAKOUT | SWEEP | AMBIGUOUS",
  "confidence_pct": 76,
  "evidence": [
    "SUPER_COMPRESSION sqz=12b -> strong breakout bias",
    "3 prior zone touches in 28 bars",
    "D1 EMA200 macro trend aligned",
    "STRONG_BREAK candle body=0.72 vel=0.95x ATR"
  ]
}
```

### 6.8 Konteks Pasar & Risiko
```json
{
  "current_spread_pts": 15,
  "atr_h1_pts": 85,
  "spread_to_atr_ratio": 0.176,
  "spread_acceptable": true,
  "session": "LONDON | NY | TOKYO | OVERLAP",
  "wib_time": "16:30",
  "hours_to_rollover": 11.5,
  "high_impact_news_window": false,
  "news_event": null,
  "daily_realized_pnl_r": 1.5,
  "daily_loss_limit_hit": false,
  "open_positions_count": 2
}
```

### 6.9 Memory & Pattern History
```json
{
  "last_6_decisions": ["WIN", "WIN", "LOSS", "WIN", "LOSS", "WIN"],
  "win_rate_7d": 0.67,
  "pair_recent_performance": "GBPUSD last 5: +2.5R, -1R, +2.5R, 0R, +2.5R",
  "similar_setup_historical_wr": 0.305,
  "similar_setup_pf": 1.13
}
```

### 6.10 Hard Veto Flags (LLM Veto WAJIB periksa)

| Flag | Kondisi | Aksi |
|---|---|---|
| `COUNTER_TREND_MOMENTUM` | Close melawan D1 EMA200 + wick besar | VETO |
| `LIQUIDITY_TRAP` | Zone terlalu obvious, kemungkinan staged sweep | VETO |
| `HIGH_IMPACT_NEWS` | Dalam window 6 jam berita US/GB/EU/JP | VETO |
| `SPREAD_SPIKE` | Spread > 30% ATR H1 | VETO |
| `INSTANT_RETEST` | Retest < 2 bar dari break = sweep signal | VETO |
| `NEAR_EQH_EQL` | Price mendekati H4 Equal High/Low (target sweep) | WARN |
| `ROLLOVER_WINDOW` | 03:50-04:15 WIB + jarak SL < threshold pair | VETO |

### 6.11 25 Candle M5 Terakhir (untuk DeepSeek Risk Audit)

Khusus DeepSeek Devil's Advocate: kirim 25 candle M5 terbaru untuk deteksi:
- Falling knife / parabolic move sebelum entry
- M5 structure reversal yang belum terlihat di H1
- Liquidity trap (fake break di M5 sebelum H1 candle close)

---

## 7. Decision Tree Live Bot

```
[Stage 1: Fast Scanner - tiap pergantian H1/M30 candle]
    |
    v
Detect multi-touch zone (cluster zone, 2+ touches dalam 40 bar)
    |
    v
classify_breakout_sequence() -> DIRECT | CONSOL | SWEEP | NONE
    |
    v
sweep_detector.detect() -> score_sweep vs score_breakout
    |
    v-- confidence < 55% --> SKIP
    |
    v-- confidence >= 55% -->
    |
[Stage 2: LLM Veto Jury (~5 detik)]
    |
    +-- OpenAI o4-mini (Structure Analyst):
    |     "Zona valid? Umur zona? H4 OB/FVG alignment?"
    |
    +-- Gemini Flash (Momentum Analyst):
    |     "Candle velocity? Engulfing? Squeeze? Session timing?"
    |
    +-- DeepSeek V4 (Devil's Advocate + Risk Veto):
          Menerima: semua konteks + 25 candle M5
          "Ada falling knife? Liquidity trap? Hard veto?"
    |
    v
Consensus (2/3 minimum, 3/3 = high confidence = double position):
    - BREAKOUT -> Entry LIMIT di zone (max 15 bar wait)
    - SWEEP    -> Counter entry ATAU skip tergantung pair
    - VETO     -> Skip + log flag + send Telegram alert
```

---

## 8. Pair Priority Matrix

| Tier | Pairs | PF Range | Justifikasi |
|---|---|:---:|---|
| **Tier 1** | CADJPY, EURJPY, USDJPY, CHFJPY | 1.29-1.35 | Konsisten, N besar, WR tinggi |
| **Tier 2** | EURGBP, GBPJPY, GBPUSD, GBPCAD | 1.13-1.20 | Edge solid, spread terkontrol |
| **Tier 3** | AUDCHF, AUDUSD, EURUSD, XAUUSD | 1.11-1.23 | Valid, diversifikasi |
| **Tier 4** | Sisanya | 1.00-1.15 | Monitor, filter ketat |
| **SKIP** | EURCHF | < 1.00 | SNB intervention anomaly |

---

## 9. Limitasi & Catatan Penting

1. Backtest tidak memodelkan slippage — limit order di live bisa tidak terisi jika price gap
2. Sample SUPER compression: 45 trade/pair/10yr = 4-5/tahun. Jangan over-rely
3. Strategy B (CHoCH Squeeze) standalone PF < 1.0 — hanya sebagai konfirmasi
4. Strategy C (Liquidity Sweep) hanya 3 pair — jangan expand ke semua pair
5. Zone definition: SELALU gunakan H1 Cluster (median wicks ±0.5 ATR)

---

## 10. File Referensi

| File | Fungsi |
|---|---|
| `src/indicators/candle_quality.py` | Klasifikasi kualitas candle |
| `src/indicators/sweep_detector.py` | 5-dimensi SWEEP vs BREAKOUT detector |
| `src/indicators/wave_regime.py` | Kompresi + range age |
| `src/indicators/lux_smc.py` | SMC: OB, FVG, BOS/CHoCH, EQH/EQL |
| `scratch/backtest_v6b_breakout_types.py` | Direct vs Multi-Touch |
| `scratch/backtest_v6c_direct_by_age.py` | Direct Chase by range age |
| `scratch/backtest_v6d_zone_quality.py` | Zone definition comparison A/B/C |
| `scratch/backtest_v5_sweep.py` | Mode B + Mode S |

---

*Report dibuat: 27 Agustus 2026. Update setelah live forward testing.*
