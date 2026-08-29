# MASTER TECHNICAL SPECIFICATION DOCUMENT
## 2-Stage Quant Funnel Multi-LLM Consensus Autonomous Trading System (Dual-Directional BUY & SELL Specification)

**Target Platform**: MetaTrader 5 (`VTMarkets-Live 3`, Account `27556325`, Raw ECN, Magic `20260625`)  
**Trading Universe**: 27 Simbol Paralel (21 FX Crosses, 6 NZD Alpha, Gold `XAUUSD-ECNc`)  
**Symmetry Architecture**: Dual-Directional Equivalence (100% Simetris BUY & SELL Logic Gates, SBR/RBS, CSM Matrix)  
**AI Mode**: `AI_FIXED_MODE = "triple"` (OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4-Flash CRO)  
**Zona Waktu**: Asia/Jakarta (WIB = GMT+7, MT5 Server GMT+3 + 4 Jam, Rollover 04:00 WIB)  
**Branch**: `quant-trade`

---

## Daftar Isi
1. [Bab 1: Executive Architecture & High-Level Design](#bab-1-executive-architecture--high-level-design)
2. [Bab 2: Fractal Multi-Timeframe Hierarchy & Symbol Universe](#bab-2-fractal-multi-timeframe-hierarchy--symbol-universe)
3. [Bab 3: Stage 1 Radar — Spesifikasi Presisi BUY vs SELL](#bab-3-stage-1-radar--spesifikasi-presisi-buy-vs-sell)
4. [Bab 4: 4-Dimensional Market State Engine (wave_state.py)](#bab-4-4-dimensional-market-state-engine-wave_statepy)
5. [Bab 5: Universal 8-Currency Basket Circuit Breaker (currency_strength.py)](#bab-5-universal-8-currency-basket-circuit-breaker-currency_strengthpy)
6. [Bab 6: Macro Strategic Engine (MSE) & Zonal SBR/RBS](#bab-6-macro-strategic-engine-mse--zonal-sbrrbs)
7. [Bab 7: LuxAlgo SMC, Liquidity Map & FRVP Confluence](#bab-7-luxalgo-smc-liquidity-map--frvp-confluence)
8. [Bab 8: Stage 2 Multi-LLM Consensus Jury & 2-Pass Audit Protocol](#bab-8-stage-2-multi-llm-consensus-jury--2-pass-audit-protocol)
9. [Bab 9: Risk Engine & Account Safeguards (risk_engine.py)](#bab-9-risk-engine--account-safeguards-risk_enginepy)
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
|  [BUY: Diskon + RBS]  [SELL: Premium + SBR]    [CSM 8-Basket Dual-Horizon Flow]   |
+-----------------------------------------+-----------------------------------------+
                                          | (Hanya 8-15 Setup A+ / hari lolos)
                                          v
+-----------------------------------------------------------------------------------+
|               STAGE 2: 3-LLM CONSENSUS JURY (Kognitif Paralel & Audit • ~5.5s)    |
|  PASS 1 (~3.0s): OpenAI o4-mini (Struktur Makro) + Gemini 3.1-Flash (Momentum/Wick)|
|  PASS 2 (~1.5s): DeepSeek V4-Flash CRO (Devil's Advocate Audit + 24 Candle M5)    |
|  VETO GATES: 11 Bendera Risiko (Anti-Falling Knife BUY / Anti-Rocket FOMO SELL)   |
|  KONSENSUS : Skor Confidence >= 1.20 | Unanimous 3/3 Split 2 Posisi (+25% Boost)  |
+-----------------------------------------+-----------------------------------------+
                                          | (Order Disetujui)
                                          v
+-----------------------------------------------------------------------------------+
|               STAGE 3: RISK ENGINE & REAL-TIME POSITION MANAGER (Loop 3 Detik)    |
|  Sizing: Risk 1.0% Equity | Floor SL: 1.3x ATR H1 (FX) / 1.8x ATR M30 (Gold)      |
|  BUY: Trailing naik kunci Floor | SELL: Trailing turun kunci Ceiling              |
|  Dynamic BEP (+15 pts Pocket) | Partial Close 50% TP1 | Pre-Rollover Shield       |
+-----------------------------------------------------------------------------------+
```

---

## Bab 3: Stage 1 Radar — Spesifikasi Presisi BUY vs SELL

### 3.1 Mekanisme 1: London Judas Swing Failure (M1)

| Parameter / Kriteria | Skenario BUY (Bullish Reversal) | Skenario SELL (Bearish Reversal) |
|---|---|---|
| **Level yang Disapu** | Asian Low, Previous Day Low (PDL), atau PWL Floor. | Asian High, Previous Day High (PDH), atau PWH Ceiling. |
| **Jarak Penembusan (Sweep)** | Low menembus level sebesar $\ge 0.15\times\text{ATR}(14)$. | High menembus level sebesar $\ge 0.15\times\text{ATR}(14)$. |
| **Reclaim Window** | Harga ditutup kembali di ATAS level dalam $\le 3\text{ candle}$. | Harga ditutup kembali di BAWAH level dalam $\le 3\text{ candle}$. |
| **Morfologi Candlestick** | Lower Rejection Wick $\ge 25\%$ dari total range candle. | Upper Rejection Wick $\ge 25\%$ dari total range candle. |
| **Anti-Momentum Gate** | Anti-Waterfall: Dilarang BUY jika candle merah marubozu solid tanpa sumbu bawah. | Anti-Skyrocket: Dilarang SELL jika candle hijau marubozu solid tanpa sumbu atas. |

### 3.2 Mekanisme 2: Trend-Aligned Pullback & Delayed Limit Retest (M2)

| Parameter / Kriteria | Skenario BUY (Trend-Following Long) | Skenario SELL (Trend-Following Short) |
|---|---|---|
| **Macro Trend Alignment** | D1 Macro Bias BULLISH + H4 EMA50 Slope Positif ($> +0.5$). | D1 Macro Bias BEARISH + H4 EMA50 Slope Negatif ($< -0.5$). |
| **Dealing Range Location** | Zona Diskon: Dealing Range $\le 0.65$ (Optimal $\le 0.382$). | Zona Premium: Dealing Range $\ge 0.35$ (Optimal $\ge 0.618$). |
| **Mean Proximity (EMA20)** | Harga berada di atas EMA20 dengan jarak $\le 0.45\times\text{ATR}$. | Harga berada di bawah EMA20 dengan jarak $\le 0.45\times\text{ATR}$. |
| **Delayed Limit Entry** | $\text{Buy Limit Anchor} = \text{Trigger Price} - (0.20\times\text{ATR})$. | $\text{Sell Limit Anchor} = \text{Trigger Price} + (0.20\times\text{ATR})$. |
| **SL Structural Anchor** | $\text{SL} = \text{Support RBS Fisik} - (0.35\times\text{ATR}) - \text{Spread}$. | $\text{SL} = \text{Resistance SBR Fisik} + (0.35\times\text{ATR}) + \text{Spread}$. |
| **Safety Ceiling & Floor** | SL Distance: Min $1.3\times\text{ATR}_{\text{H1}}$ s/d Max $\le 160\text{ pts}$ (16 pips FX). | SL Distance: Min $1.3\times\text{ATR}_{\text{H1}}$ s/d Max $\le 160\text{ pts}$ (16 pips FX). |
| **Target Profit (TP)** | $\text{TP} = \text{Nearest Resistance Station}$ (R:R $\ge 1.25\times$ s/d $3.0\times\text{SL}$). | $\text{TP} = \text{Nearest Support Station}$ (R:R $\ge 1.25\times$ s/d $3.0\times\text{SL}$). |

### 3.3 Mekanisme 3: HTF Weekly Wall Reversal & Foothold Targeting (M3)

| Parameter / Kriteria | Skenario BUY (Bounce from Floor) | Skenario SELL (Rejection from Ceiling) |
|---|---|---|
| **Macro Wall Collision** | Harga menguji PWL Floor atau Sub-Floor Station 100-pip. | Harga menguji PWH Ceiling atau Sub-Ceiling Station 100-pip. |
| **Foothold Confirmation** | Lilin H1 ditutup di atas level support stasiun. | Lilin H1 ditutup di bawah level resistance stasiun. |
| **Target Koridor Estafet** | Target TP = 50% Equilibrium Dealing Range & Next Station. | Target TP = 50% Equilibrium Dealing Range & Lower Station. |
| **Invalidation SL** | SL diletakkan di bawah titik terendah swing (PWL) + Buffer. | SL diletakkan di atas titik tertinggi swing (PWH) + Buffer. |

---

## Bab 4: 4-Dimensional Market State Engine (`wave_state.py`)

| Fase Siklus Wave | Kondisi Pasar BULLISH (Arah BUY) | Kondisi Pasar BEARISH (Arah SELL) |
|---|---|---|
| **Phase 1: Impulse (WAIT)** | Harga melonjak tajam menjauhi EMA20. Permission = WAIT (Dilarang mengejar BUY di pucuk). | Harga anjlok tajam menjauhi EMA20. Permission = WAIT (Dilarang mengejar SELL di dasar). |
| **Phase 2: Waterfall (LOCK)** | Harga mengalami koreksi tajam beruntun. Permission = LOCK (Dilarang menangkap pisau jatuh). | Harga mengalami rebound tajam beruntun. Permission = LOCK (Dilarang menghadang roket). |
| **Phase 3: Mature Basing (ARM)** | Pelemahan momentum koreksi di zona diskon ($\le 0.50$). Permission = ARM (Siap pasang Buy Limit). | Pelemahan momentum rebound di zona premium ($\ge 0.50$). Permission = ARM (Siap pasang Sell Limit). |
| **Phase 4: Base Reclaim (GO)** | Konfirmasi reclaim level support + sumbu bawah. Permission = GO (Eksekusi BUY Aktif). | Konfirmasi reclaim level resistance + sumbu atas. Permission = GO (Eksekusi SELL Aktif). |

---

## Bab 5: Universal 8-Currency Basket Circuit Breaker (`currency_strength.py`)

| Kondisi Arus Modal | Dampak pada Order BUY | Dampak pada Order SELL |
|---|---|---|
| **Base Currency DUMP ($\le -20.0$)** | **HARD LOCK BUY** (Dilarang beli mata uang yang sedang crash). | **OPEN SELL ENABLED** (Arus searah dengan pelemahan). |
| **Base Currency SURGE ($\ge +20.0$)** | **OPEN BUY ENABLED** (Arus searah dengan penguatan). | **HARD LOCK SELL** (Dilarang short mata uang yang sedang rally). |
| **Quote Currency SURGE ($\ge +20.0$)** | **HARD LOCK BUY** (Quote terlalu kuat, pair akan tertekan turun). | **OPEN SELL ENABLED** (Short diuntungkan oleh quote kuat). |
| **Quote Currency DUMP ($\le -20.0$)** | **OPEN BUY ENABLED** (Long diuntungkan oleh quote lemah). | **HARD LOCK SELL** (Dilarang short saat quote sedang crash). |
| **Relative Delta Spread ($|\Delta| \ge 18.0$)** | Jika Net Delta $\le -18.0 \rightarrow$ **HARD LOCK BUY**. | Jika Net Delta $\ge +18.0 \rightarrow$ **HARD LOCK SELL**. |

---

## Bab 10: Real-Time Position Management Lifecycle (`position_manager.py`)

| Fitur Proteksi | Aksi pada Posisi BUY (Long) | Aksi pada Posisi SELL (Short) |
|---|---|---|
| **Pocket Profit BEP (45-55% TP)** | SL dinaikkan ke: $\text{Entry} + \text{Komisi} + 15\text{ pts}$ (1.5 pips). | SL diturunkan ke: $\text{Entry} - \text{Komisi} - 15\text{ pts}$ (1.5 pips). |
| **Partial Close (TP1)** | Cairkan 50% lot saat harga mencapai 50% jarak TP. | Cairkan 50% lot saat harga mencapai 50% jarak TP. |
| **Trailing Stage 1 (65-90% TP)** | SL mengikuti di bawah harga tertinggi sebesar $0.75\times\text{ATR}_{\text{H1}}$. | SL mengikuti di atas harga terendah sebesar $0.75\times\text{ATR}_{\text{H1}}$. |
| **Trailing Stage 2 ($\ge 90\%$ TP)** | Kunci profit ketat di bawah harga sebesar $0.50\times\text{ATR}_{\text{M30}}$. | Kunci profit ketat di atas harga sebesar $0.50\times\text{ATR}_{\text{M30}}$. |
| **Time-Decay Stagnation Exit** | Tutup otomatis jika $\ge 4\text{ jam}$ di $[-0.2R, +0.2R]$ & Peak $< +0.3R$. | Tutup otomatis jika $\ge 4\text{ jam}$ di $[-0.2R, +0.2R]$ & Peak $< +0.3R$. |
| **Pre-Rollover Shield (03:50 WIB)** | Tutup otomatis jika jarak ke SL $\le\text{threshold per pair}$. | Tutup otomatis jika jarak ke SL $\le\text{threshold per pair}$. |
