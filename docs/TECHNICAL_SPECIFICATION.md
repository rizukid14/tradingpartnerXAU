# MASTER TECHNICAL SPECIFICATION DOCUMENT
## 2-Stage Quant Funnel Multi-LLM Consensus Autonomous Trading System (Strict Unanimous 3/3 & Dual-Directional Equivalence)

**Target Platform**: MetaTrader 5 (`VTMarkets-Live 3`, Account `27556325`, Raw ECN, Magic `20260625`)  
**Trading Universe**: 27 Simbol Paralel (21 FX Crosses, 6 NZD Alpha, Gold `XAUUSD-ECNc`)  
**Consensus Protocol**: Strict Unanimous 3/3 Rule (Wajib 3/3 Model Searah; 2/3 atau Split = HOLD Otomatis)  
**Symmetry Architecture**: Dual-Directional Equivalence (100% Simetris BUY & SELL Logic Gates, SBR/RBS, CSM Matrix)  
**AI Mode**: `AI_FIXED_MODE = "triple"` (OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4-Flash CRO)  
**Zona Waktu**: Asia/Jakarta (WIB = GMT+7, MT5 Server GMT+3 + 4 Jam, Rollover 04:00 WIB)  
**Branch**: `quant-trade`

---

## Daftar Isi
1. [Bab 1: Executive Architecture & High-Level Design](#bab-1-executive-architecture--high-level-design)
2. [Bab 2: Fractal Multi-Timeframe Hierarchy & Symbol Universe](#bab-2-fractal-multi-timeframe-hierarchy--symbol-universe)
3. [Bab 3: Stage 1 Radar — Trio Mekanisme Presisi (M1, M2, M3)](#bab-3-stage-1-radar--trio-mekanisme-presisi-m1-m2-m3)
4. [Bab 4: 4-Dimensional Market State Engine (wave_state.py)](#bab-4-4-dimensional-market-state-engine-wave_statepy)
5. [Bab 5: Universal 8-Currency Basket Circuit Breaker (currency_strength.py)](#bab-5-universal-8-currency-basket-circuit-breaker-currency_strengthpy)
6. [Bab 6: Macro Strategic Engine (MSE) & Zonal SBR/RBS](#bab-6-macro-strategic-engine-mse--zonal-sbrrbs)
7. [Bab 7: LuxAlgo SMC, Liquidity Map & FRVP Confluence](#bab-7-luxalgo-smc-liquidity-map--frvp-confluence)
8. [Bab 8: Stage 2 Multi-LLM Consensus Jury & Strict 3/3 Protocol](#bab-8-stage-2-multi-llm-consensus-jury--strict-33-protocol)
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
|  [M1: Judas Sweep]    [M2: Pullback Retest]    [M3: Multi-Touch Breakout Retest]  |
|  [BUY: Diskon + RBS]  [SELL: Premium + SBR]    [CSM 8-Basket Dual-Horizon Flow]   |
+-----------------------------------------+-----------------------------------------+
                                          | (Hanya 8-15 Setup A+ / hari lolos)
                                          v
+-----------------------------------------------------------------------------------+
|               STAGE 2: 3-LLM CONSENSUS JURY (Kognitif Paralel & Audit • ~5.5s)    |
|  PASS 1 (~3.0s): OpenAI o4-mini (Struktur Makro) + Gemini 3.1-Flash (Momentum/Wick)|
|  PASS 2 (~1.5s): DeepSeek V4-Flash CRO (Devil's Advocate Audit + 24 Candle M5)    |
|  VETO GATES: 11 Bendera Risiko (Anti-Falling Knife BUY / Anti-Rocket FOMO SELL)   |
|  KONSENSUS : STRICT UNANIMOUS 3/3 (Wajib 3/3 Searah; Split = HOLD)                |
|  SPLIT BOOST: Unanimous 3/3 + Confidence >= 75% -> 2 Tiket Posisi (+25% Boost)    |
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

## Bab 3: Stage 1 Radar — Trio Mekanisme Presisi (M1, M2, M3)

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

### 3.3 Mekanisme 3: Multi-Touch Cluster Breakout & Delayed Retest (M3)

| Parameter / Kriteria | Skenario BUY (Bullish Breakout Retest) | Skenario SELL (Bearish Breakdown Retest) |
|---|---|---|
| **Cluster Touch Count** | Cluster Resistance telah diuji $\ge 2\text{ kali}$ (`touches_resistance >= 2`). | Cluster Support telah diuji $\ge 2\text{ kali}$ (`touches_support >= 2`). |
| **Breakout Validation** | Harga menembus di atas resistance cluster $\ge 0.10\times\text{ATR}$. | Harga menembus di bawah support cluster $\ge 0.10\times\text{ATR}$. |
| **Delayed Retest Entry** | Buy Limit dipasang tepat di level `cluster_resistance - 0.5 * spread`. | Sell Limit dipasang tepat di level `cluster_support + 0.5 * spread`. |
| **Macro Corridor Gate** | Macro Corridor wajib BULLISH (Dilarang trade di Bearish Corridor). | Macro Corridor wajib BEARISH (Dilarang trade di Bullish Corridor). |
| **Structural Invalidation** | SL di balik Support RBS $+ 0.35\times\text{ATR} + \text{Spread}$ ($\le 160\text{ pts}$). | SL di balik Resistance SBR $+ 0.35\times\text{ATR} + \text{Spread}$ ($\le 160\text{ pts}$). |

---

## Bab 8: Stage 2 Multi-LLM Consensus Jury & Strict 3/3 Protocol

1. **Syarat Eksekusi Mutlak (Zero Tolerance Split)**:
   - Wajib 3 dari 3 model aktif (`OpenAI o4-mini`, `Gemini 3.1-Flash`, `DeepSeek V4-Flash CRO`) memilih arah yang sama persis (**3/3 BUY** atau **3/3 SELL**).
   - Jika ada 1 model yang memilih HOLD, REJECT, atau arah berlawanan (hasil 2/3 atau split vote) $\rightarrow$ **OTOMATIS DIBATALKAN (HOLD)**.
   - Sistem *Weighted-Confidence 1.20* lama sudah di-DROP 100% dari `consensus.py`.

2. **Eksekusi Unanimous 3/3 High Confidence Split (+25% Boost)**:
   - Jika ketiga model sepakat bulat dan rata-rata Confidence $\ge 75\%$ serta terdapat $\ge 2$ slot MT5 kosong:
   - Bot membuka 2 tiket posisi sekaligus @ $0.625\times\text{Base Lot}$ (Total $1.25\times$ bobot):
     * **Posisi #1**: Menargetkan TP1 Standar (Stasiun terdekat) dengan trailing stop agresif.
     * **Posisi #2**: Menargetkan TP2 Extended Target (Stasiun makro besar) dengan trailing swing bernafas.
