# MASTER TECHNICAL SPECIFICATION DOCUMENT
## 2-Stage Quant Funnel Multi-LLM Consensus Autonomous Trading System

**Target Platform**: MetaTrader 5 (`VTMarkets-Live 3`, Account `27556325`, Raw ECN, Magic `20260625`)  
**Trading Universe**: 27 Simbol Paralel (21 FX Crosses, 6 NZD Alpha, Gold `XAUUSD-ECNc`)  
**AI Mode**: `AI_FIXED_MODE = "triple"` (OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4-Flash CRO)  
**Zona Waktu**: Asia/Jakarta (WIB = GMT+7, MT5 Server GMT+3 + 4 Jam, Rollover 04:00 WIB)  
**Branch**: `quant-trade`

---

## Daftar Isi
1. [Bab 1: Executive Architecture & High-Level Design](#bab-1-executive-architecture--high-level-design)
2. [Bab 2: Fractal Multi-Timeframe Hierarchy & Symbol Universe](#bab-2-fractal-multi-timeframe-hierarchy--symbol-universe)
3. [Bab 3: Stage 1 Fast Quantitative Radar & Mathematical Logic Gates](#bab-3-stage-1-fast-quantitative-radar--mathematical-logic-gates)
4. [Bab 4: 4-Dimensional Market State Engine (wave_state.py)](#bab-4-4-dimensional-market-state-engine-wave_statepy)
5. [Bab 5: Universal 8-Currency Basket Circuit Breaker (currency_strength.py)](#bab-5-universal-8-currency-basket-circuit-breaker-currency_strengthpy)
6. [Bab 6: Pure Quant Macro Strategic Engine (MSE) & Station Delivery](#bab-6-pure-quant-macro-strategic-engine-mse--station-delivery)
7. [Bab 7: LuxAlgo SMC, Liquidity Map & FRVP Confluence](#bab-7-luxalgo-smc-liquidity-map--frvp-confluence)
8. [Bab 8: Stage 2 Multi-LLM Consensus Jury & 2-Pass Audit Protocol](#bab-8-stage-2-multi-llm-consensus-jury--2-pass-audit-protocol)
9. [Bab 9: Risk Engine & Mathematical Account Safeguards (risk_engine.py)](#bab-9-risk-engine--mathematical-account-safeguards-risk_enginepy)
10. [Bab 10: Real-Time Position Management Lifecycle (position_manager.py)](#bab-10-real-time-position-management-lifecycle-position_managerpy)
11. [Bab 11: Comprehensive Tokenomics, Latency & Cost Optimization](#bab-11-comprehensive-tokenomics-latency--cost-optimization)
12. [Bab 12: Telegram Interactive Controller & Operational Playbook](#bab-12-telegram-interactive-controller--operational-playbook)

---

## Bab 1: Executive Architecture & High-Level Design

```
+-----------------------------------------------------------------------------------+
|               STAGE 1: FAST QUANTITATIVE RADAR (Lokal di MT5 • 60 Detik • 0 Token)|
|  Universe: 27 Simbol Paralel | Sockets: MN1, W1, D1, H4, H1, M30                  |
|  [M1: Judas Sweep]    [M2: Pullback Retest]    [M3: Weekly Wall Reversal]         |
|  [4D Wave State FSM]  [Boitoki 8-Currency Matrix]  [Macro Strategic Engine (MSE)] |
+-----------------------------------------+-----------------------------------------+
                                          | (Hanya 8-15 Setup A+ / hari lolos)
                                          v
+-----------------------------------------------------------------------------------+
|               STAGE 2: 3-LLM CONSENSUS JURY (Kognitif Paralel & Audit • ~5.5s)    |
|  PASS 1 (~3.0s): OpenAI o4-mini (Struktur Makro) + Gemini 3.1-Flash (Momentum/Wick)|
|  PASS 2 (~1.5s): DeepSeek V4-Flash CRO (Devil's Advocate Audit + 24 Candle M5)    |
|  VETO GATES: 11 Bendera Risiko (Anti-Falling Knife, Systemic Dump, News Shield)   |
|  KONSENSUS : Skor Confidence >= 1.20 | Unanimous 3/3 Split 2 Posisi (+25% Boost)  |
+-----------------------------------------+-----------------------------------------+
                                          | (Order Disetujui)
                                          v
+-----------------------------------------------------------------------------------+
|               STAGE 3: RISK ENGINE & REAL-TIME POSITION MANAGER (Loop 3 Detik)    |
|  Sizing: Risk 1.0% Equity | Floor SL: 1.3x ATR H1 (FX) / 1.8x ATR M30 (Gold)      |
|  Dynamic BEP (+15 pts Pocket) | Partial Close 50% TP1 | 2-Stage Dynamic Trailing  |
|  Peak-Aware Time-Decay Stagnation Exit | Pre-Rollover Shield (03:50-04:15 WIB)    |
+-----------------------------------------------------------------------------------+
```

---

## Bab 2: Fractal Multi-Timeframe Hierarchy & Symbol Universe

| Timeframe | Kedalaman Data | Peran & Fungsi Kuantitatif | Eksekusi / Trigger |
|---|---|---|---|
| **MN1 (Monthly)** | 50 Bar (~4.1 Thn) | Penetapan tren multi-dekade dan plafon resistensi mayor absolut. | Macro Anchor (0 Token) |
| **W1 (Weekly)** | 100 Bar (~2.0 Thn) | Penentuan Dealing Range 100-bar, Previous Week High/Low (PWH/PWL). | Macro Wall Boundary |
| **D1 (Daily)** | 350 Bar (~1.4 Thn) | Daily Macro Bias, Previous Day High/Low (PDH/PDL), Daily Open (DO). | Direction Identity Anchor |
| **H4 (4-Hour)** | 400 Bar (~66 Hari) | Intermediate SBR/RBS levels, SuperTrend, EMA50 Slope Direction. | Intermediate Trend Filter |
| **H1 (1-Hour)** | 250 Bar (~10 Hari) | Primary Radar Execution Timeframe untuk 21 FX Majors & Crosses. | Fast Execution Trigger |
| **M30 (30-Min)** | 200 Bar (~4 Hari) | Primary Radar Execution Timeframe untuk XAUUSD-ECNc & JPY Crosses. | Gold/JPY Radar Trigger |
| **M5 (5-Min)** | 24 Bar (2 Jam) | Mikroskop Audit Pass 2 DeepSeek CRO (Rejection Wicks & Falling Knife). | Pass 2 CRO Audit Only |

---

## Bab 3: Stage 1 Fast Quantitative Radar & Mathematical Logic Gates

### 3.1 Mekanisme 1: London Judas Swing Failure (M1)
1. **Jarak Sapuan**: Harga menembus Asian High/Low, PDH, atau PDL sebesar $\ge 0.15\times\text{ATR}(14)$.
2. **Reclaim Window**: Harga wajib ditutup kembali (*reclaim*) ke dalam rentang dalam $\le 3\text{ candle}$.
3. **Rejection Wick**: Candle pembalikan wajib memiliki Rejection Wick $\ge 25\%$ dari total range candle.
4. **Anti-Waterfall Gate**: Dilarang BUY jika candle penembusan adalah Marubozu merah solid tanpa sumbu bawah.

### 3.2 Mekanisme 2: Trend-Aligned Pullback & Delayed Limit Retest (M2)
1. **Macro Alignment**: D1 SuperTrend + H4 EMA50 slope searah dengan arah setup.
2. **Dealing Range Location**: Posisi harga wajib berada di zona Diskon ($\le 0.65$) untuk BUY, atau Premium ($\ge 0.35$) untuk SELL.
3. **Mean Pullback Proximity**: Jarak harga ke EMA20 H1 wajib $\le 0.45\times\text{ATR}$.
4. **Delayed Limit Retest**: Order limit dipasang pada harga diskon $= \text{Trigger Price} - (0.20\times\text{ATR})$ untuk BUY.
5. **Structural SL Anchoring**: SL dipasang di balik Support SBR/RBS fisik $+ 0.35\times\text{ATR} + \text{Spread}$.
6. **Hard Safety Ceiling**: SL Forex dibatasi maksimal $\le 160\text{ pts}$ (16.0 pips).

### 3.3 Mekanisme 3: HTF Weekly Wall Reversal & Foothold Targeting (M3)
1. **Wall Collision**: Harga menabrak level dinding makro (PWH/PWL atau Stasiun 100-pip).
2. **Foothold Targeting**: Konfirmasi penolakan sumbu dan penutupan harga di atas/bawah 50% Equilibrium Dealing Range.
3. **Estafet Corridor Delivery**: Menargetkan koridor stasiun berikutnya dengan rasio Risk:Reward $\ge 1.5:1$.

---

## Bab 4: 4-Dimensional Market State Engine (`wave_state.py`)

- **Dimensi 1 (Direction FSM)**: D1 + H4 Trend State (`BULLISH_EXPANSION`, `BEARISH_PULLBACK`, `BULLISH_PULLBACK`, `RANGE_BOUND`). Memangkas False Flip dari 70.86% menjadi 12.61%.
- **Dimensi 2 (Anatomy FSM)**: Type A (Mean-Reverting Range) vs Type B (Impulse Expansion).
- **Dimensi 3 (CSM Velocity)**: Relative flow velocity 8 mata uang utama.
- **Dimensi 4 (Trade Permission Layer)**: `[WAIT, LOCK, WATCH, ARM, GO]`. Hanya `ARM` (Mature Basing) dan `GO` (Base Reclaim) di zona diskon yang diizinkan trade.

---

## Bab 5: Universal 8-Currency Basket Circuit Breaker (`currency_strength.py`)

$$\text{Score}(\text{Currency}) = \ln\left(\frac{P_{\text{Current}}}{P_{\text{Lookback}}}\right) \times 10000.0 - \text{Average}(8\text{ Currencies})$$

$$\mathbf{\text{Effective Score} = (0.40 \times \text{Score}_{\text{H1}} [24\text{ bar}]) + (0.60 \times \text{Score}_{\text{M15}} [16\text{ bar}])}$$

- **Systemic Dump ($\le -20.0$)**: Hard Lock BUY pada mata uang tersebut.
- **Systemic Surge ($\ge +20.0$)**: Hard Lock SELL pada mata uang tersebut.
- **Relative Delta Spread ($|\Delta| \ge 18.0$)**: Hard Lock arah berlawanan arus modal institusional.

---

## Bab 8: Stage 2 Multi-LLM Consensus Jury & 2-Pass Audit Protocol

- **Pass 1 Paralel (~3.0s)**: OpenAI o4-mini (Struktur Makro) + Gemini 3.1-Flash (Morfologi Lilin/Wicks).
- **Pass 2 Cross-Examination (~1.5s)**: DeepSeek V4-Flash CRO mengaudit proposal Pass 1 berbekal **24 Lilin M5 Live**.
- **11 Bendera Hard Risk Veto**: `COUNTER_TREND_MOMENTUM`, `FALLING_KNIFE_WATERFALL`, `SYSTEMIC_CURRENCY_DUMP`, `UNMITIGATED_IMPULSE_CHASE`, `HIGH_IMPACT_NEWS`, `LIQUIDITY_TRAP`, `SPREAD_SPIKE`, `INSTANT_RETEST`, `NEAR_EQH_EQL`, `ROLLOVER_WINDOW`, `NONE`.
- **Konsensus**: Skor bobot confidence $\ge 1.20$.
- **Unanimous 3/3 Split (+25% Boost)**: 3 AI sepakat $\ge 75\% \rightarrow$ Eksekusi 2 posisi @ $0.625\times\text{Base Lot}$ (Pos #1 TP Standar + Trailing, Pos #2 TP Extended Target).

---

## Bab 9: Risk Engine & Mathematical Account Safeguards

$$\mathbf{\text{Lot Size} = \frac{\text{Account Equity} \times \text{Risk Percent}}{\text{SL Points} \times \text{USD Per Point}}}$$

- **Risk per Trade**: Forex 1.0% Equity, Gold 1.0% Equity.
- **Floor SL**: XAU $\ge \max(2\times\text{Spread}, 1.8\times\text{ATR}_{\text{M30}})$; FX $\ge \max(2\times\text{Spread}, 1.3\times\text{ATR}_{\text{H1}})$.
- **Ceiling SL**: FX $\le 160\text{ pts}$ (16.0 pips).
- **Max Daily Loss**: 4.0% Equity (Hard Stop harian).
- **Daily Profit Target**: 6.0% Equity (Kunci profit).
- **Max Open Positions**: 6 posisi aktif + 4 pending limit order.
- **Recovery Mode**: 5 loss beruntun $\rightarrow$ Lot $\times 0.5$, max 3 posisi.

---

## Bab 10: Real-Time Position Management Lifecycle (`position_manager.py`)

- **Pocket Profit BEP**: Aktif di 45%–55% TP $\rightarrow$ SL digeser ke Entry + Komisi + Pocket Profit 15 pts (1.5 pips).
- **Partial Close (TP1)**: Mencairkan 50% lot di 45%–55% TP.
- **2-Stage Trailing Stop**:
  * Stage 1 (Swing Breathing 65% s/d <90% TP): $0.75\times\text{ATR}_{\text{H1}}$ (Floor 80 pts FX).
  * Stage 2 (Terminal Lock $\ge 90\%$ TP): $0.50\times\text{ATR}_{\text{M30}}$ (Floor 30 pts FX).
- **Peak-Aware Time-Decay Stagnation Exit**: Posisi $\ge 4\text{ jam}$ di $[-0.20R, +0.20R]$ ditutup jika Peak MFE $< +0.30R$.
- **Pre-Rollover Shield (03:50–04:15 WIB)**: Tutup otomatis posisi yang berjarak dekat SL pada 03:50 WIB.

---

## Bab 11: Comprehensive Tokenomics, Latency & Cost Optimization

| Metrik | Polling Lama (M5) | 2-Stage Quant Funnel | Penghematan |
|---|:---:|:---:|:---:|
| **Frekuensi Pemindaian** | 7.776 Siklus / Hari | 1.440 Siklus Radar / Hari | Lokal di MT5 (0 Token) |
| **Panggilan API per Hari** | 23.328 Calls / Hari | 75 - 135 Calls / Hari | **Pangkas 99.4% Calls** |
| **Konsumsi Token Harian** | ~35.000.000 Token | ~150.000 Token | **Hemat 99.5% Token** |
| **Estimasi Biaya Harian** | $15.00 - $35.00 | $0.10 - $0.25 | **Hemat Biaya ~99%** |
| **Estimasi Biaya Bulanan** | $450 - $1.000 / Bln | $3.00 - $7.50 / Bln | **Hemat $440+/Bulan** |

---

## Bab 12: Telegram Interactive Controller & Operational Playbook

- `/status`, `/posisi`, `/scan`, `/news`
- `/radar` (Live Heat-Table 27 Simbol)
- `/levels <symbol>` (Peta Stasiun Atlas DNA)
- `/smc <symbol>` (Peta Likuiditas Order Block & FVG)
- `/macro <symbol>` (Dossier 6-TF MSE)
- `/analisa <symbol>` (On-Demand 3-LLM Jury)
- `/closeall` (Emergency Exit)
