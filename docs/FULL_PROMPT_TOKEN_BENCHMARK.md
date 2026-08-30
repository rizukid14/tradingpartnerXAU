# Full Production Dossier Prompt & Token Benchmark (August 2026)

> **Dokumen Resmi Acuan Prompt & Konsumsi Token AI**.  
> Berisi cetakan verbatim *Full High-Density Dossier Prompt* (Pass 1) dan *Devil's Advocate CRO Cross-Examination Prompt* (Pass 2) mencakup seluruh modul kuantitatif terbaru (MSE 6-TF, Symmetrical Wave State, Boitoki CSM, Apex Paragon Macro Fundamental 40%, LuxSMC, FRVP, dan 24 Candle M5).

---

## 📊 1. Ringkasan Metrik & Estimasi Biaya Token

| Komponen Evaluasi | Karakter | Kata | Token (o200k: OpenAI o4-mini) | Token (cl100k: DeepSeek/Claude) | Estimasi Biaya API |
|---|---|---|---|---|---|
| **Pass 1 Dossier (OpenAI)** | 8,321 | 1,137 | **2,189** | 2,248 | ~$0.0006 |
| **Pass 1 Dossier (Gemini)** | 8,321 | 1,137 | **2,189** | 2,248 | ~$0.0001 |
| **Pass 2 Devil's CRO (DeepSeek)** | 10,378 | 1,414 | 2,731 | **2,804** | ~$0.0003 |
| **🏆 TOTAL PER SETUP A+ (3-AI JURY)** | **27,020** | **3,688** | **~7,109 Token Total** | **~7,300 Token Total** | **~$0.0010 per Setup** |

> [!NOTE]
> Karena arsitektur **2-Stage Quant Funnel** kita hanya memicu Stage 2 pada **8–15 setup A+ per hari** (sisanya disaring radar lokal 0 token), maka total biaya API harian adalah **~$0.015 / hari (kurang dari Rp 250,- per hari)**!

---

## 📜 2. Full Verbatim Prompt: Pass 1 High-Density Dossier Prompt

```text
# INSTITUTIONAL TRADING JURY: CANDIDATE VERIFICATION & ORDER OPTIMIZER DOSSIER

Python Quantitative Engine has detected a potential quantitative setup (TREND_ALIGNED_PULLBACK) on EURUSD (H1).

## 1. INSTITUTIONAL BATTLEFIELD & CONFLUENCE
- Symbol: EURUSD | Asset: Forex Currency Pair (EURUSD)
- Setup Type: TREND_ALIGNED_PULLBACK | Proposed Direction: SELL | Current Price: 1.08800
- Macro Compass: D1_BEARISH_TREND | H4 Status: BEARISH (-1)
- H1 Wave State: PREMIUM_RELOAD_ARMED — H1 supply reload at 72% DR; Direction SELL enabled
- Intraday Dealing Range: 72.0% (EXTREME PREMIUM)
- Key Levels: PDH=1.09450 | PDL=1.08200 | PWH=1.09900 | PWL=1.07800 | DO=1.08650 | ADR Used: 6850.0%
- Volatility: ATR(14)=82.0 pts | Current Spread=20 pts | Rejection Wick: 45.0%
- Proposed Execution Method: MARKET @ 1.088
- Structural Zone Touch Count: 3 touches in last 40 bars
- Compression Duration / Range Age: 18 hours (MATURE_COMPRESSION_ARMED)

## 2. APEX PARAGON MACRO FUNDAMENTAL & ECONOMIC CONTEXT (40% Weight — Read Before Evaluating Technicals)

### APEX PARAGON MACRO FUNDAMENTAL BRIEFING (40% Weight)
• Base Currency (EUR)   : Score +0.00 | CB Rate: 3.75% (CUT_CYCLE) | Phase: PRICED_IN_EQUILIBRIUM
• Quote Currency (USD)  : Score -0.40 | CB Rate: 5.5% (HOLD / CUT_WATCH) | Phase: PRICED_IN_EQUILIBRIUM
• Fundamental Net Delta  : +0.40 | Net Carry Spread: -1.75%
• Currency Conflict Gate : 🟢 VALID CONVERGENCE (FAVOR BUY)
• Setup Classification   : GRADE_A_PLUS (Sizing: 1.0x)
• Macro Directive        : FAVOR_BUY (EUR Strong vs USD Weak | Net Delta +0.40)
• Recent Catalysts/Decay :
• [Trading Economics] Euro Slips as Hawkish Fed Tone Supports Dollar (0.0h ago)
• [Binance News] Dollar Rises After Fed Chair Warsh Remarks as Markets Await U.S. Jobs Data (0.0h ago)

- Economic Calendar Context: No High-Impact News releases within +/- 6 hours

## 3. CURRENCY FLOW & WAVE STATE CONFIRMATION

- M30 Structural Frame (50-bar / 24h Window):
  * 50-Bar High: 1.16594 | 50-Bar Low: 1.15779 | Position: 4.2% of Range
  * Moving Averages: EMA20 = 1.16015 | EMA50 = 1.16218 | EMA200 = 1.16277 (EMA20 < EMA50 < EMA200 (Bearish Alignment))
  * Volatility Meter: ATR(14) = 82.5 pts
- M15 Micro Flow Frame (32-bar / 8h Session Window):
  * 32-Bar High: 1.16594 | 32-Bar Low: 1.15779 | Position: 4.2% of Range
  * Moving Averages: EMA9 = 1.15836 | EMA21 = 1.15894 | EMA50 = 1.16060 (EMA9 < EMA21 < EMA50 (Bearish Momentum Stack))
  * Volatility Meter: ATR(14) = 52.3 pts
  * Micro Velocity: Last 3 bars avg candle body = 14.7 pts (0.28x ATR M15)


### GLOBAL CURRENCY STRENGTH MATRIX (Dual-Horizon Flow)
- 24-Hour Macro Flow (H1): [USD: +44.8, CAD: +6.4, JPY: +1.1, GBP: +0.1, AUD: -0.7, EUR: -16.0, CHF: -17.1, NZD: -18.6]
- 4-Hour Session Velocity (M15): [JPY: +6.8, NZD: +4.4, CHF: +2.2, USD: -0.0, AUD: -0.6, GBP: -3.9, CAD: -4.0, EUR: -4.8]
- Cross-Currency Relative Velocity (EURUSD):
  * Base (EUR): 24h = -16.01 (Rank #6/8) | 4h Session = -4.77 (Rank #8/8)
  * Quote (USD): 24h = +44.76 (Rank #1/8) | 4h Session = -0.02 (Rank #4/8)
  * Net 4-Hour Session Delta (EUR minus USD): -4.75 (BALANCED / SESSION COMPRESSION) | Net 24h Delta: -60.77

## 4. PURE QUANT 6-TF MACRO STRATEGIC DIRECTIVE (MSE) & ATLAS DNA STATIONS

## ATLAS DNA PSYCHOLOGICAL STATION MAP (16.2-Year Calibrated Grid)
- Step Grid: 1000 pips per station | Position in Range: 40.0%
- Station Ladder: ... 1.07000 -> [1.08000] -> [1.09000] <CURRENT 1.08800> -> [1.10000] -> 1.11000 ...
- Distances: to Lower 0.00800 | to Base 0.00200 | to Upper 0.01200
- Atlas DNA-Anchored Reference (Front-Running Pad TP = Station +/- [0.15xATR + Spread], SL = Opposing Station +/- [0.35xATR + Spread]):
  * Reference TP (SELL): 1.08032 | Reference SL: 1.10049


## 4. PURE QUANT 6-TF MACRO STRATEGIC DIRECTIVE (MSE)
- Macro Bias: -0.85 (BEARISH_PULLBACK) | Stability: HIGH_VOLATILITY | Phase: FRONTIER_EXHAUSTION_AT_1.16000
- Action Tier: FULL_ALLOW | Circuit Breaker: CLEAR
- SBR/RBS Hierarchy:
  * D1 Scale: Major SBR = 1.16552 | Major RBS = 1.14826
  * H4 Scale: SBR = 1.16366 | RBS = 1.14826
  * H1 Scale: SBR = 1.16366 | RBS = 1.14826
- 50-Pip Sub-Stations: Sub-Floor [1.155] <---> Sub-Ceiling [1.16]
- Target Landscape: TP1 (Proximal Station) = 1.15942 | TP2 (Macro Target) = 1.15026
- Baseline Floor SL: 1.16666 | Macro Invalidation: 1.17207

## 5. SMART MONEY CONCEPTS (SMC) & FRVP LIQUIDITY MAP
- Structural Floor (Strong Low): 1.08120 | Ceiling (Strong High): 1.09480
- Nearest Bullish OB: 1.08000–1.08200 | Nearest Bearish OB: 1.09300–1.09500
- Nearest Fair Value Gap (FVG Magnet): 1.08650–1.08800 (bearish FVG, unmitigated)
- Liquidity Pools: EQH cluster at 1.09450; EQL at 1.08050
- Fixed Range Volume Profile (FRVP): FRVP POC: 1.08870 | VAH: 1.09210 | VAL: 1.08540 (price at VAH — supply zone)

## 6. PROPOSED EXECUTION & STATION-ANCHORED LEVELS
- Scanner Raw SL: 1.09100 | Scanner Raw TP: 1.08200 | R:R: 2.00:1
- Atlas DNA-Anchored Reference: SL = 1.10049 | TP = 1.08032
  (TP snapped to nearest Station +[0.15xATR+Spread]; SL anchored behind opposing Station - [0.35xATR+Spread])

- D1 Daily Context (Last 3 days OHLC):
- [04:00] 1.16728/1.16770/1.16420/1.16534
- [04:00] 1.16463/1.16599/1.16366/1.16513
- [04:00] 1.16519/1.16593/1.15779/1.15813

- H4 Structural (Last 6 bars OHLC):
- [04:00] 1.16519/1.16549/1.16464/1.16533
- [08:00] 1.16532/1.16555/1.16451/1.16455
- [12:00] 1.16455/1.16492/1.16418/1.16445
- [16:00] 1.16445/1.16505/1.16394/1.16491
- [20:00] 1.16489/1.16593/1.15847/1.15868
- [00:00] 1.15868/1.15891/1.15779/1.15813

- H1 Execution (Last 12 bars OHLC):
- [13:00] 1.16446/1.16492/1.16431/1.16483
- [14:00] 1.16483/1.16488/1.16418/1.16465
- [15:00] 1.16466/1.16488/1.16420/1.16445
- [16:00] 1.16445/1.16451/1.16397/1.16398
- [17:00] 1.16399/1.16492/1.16394/1.16491
- [18:00] 1.16491/1.16495/1.16446/1.16452
- [19:00] 1.16451/1.16505/1.16394/1.16491
- [20:00] 1.16489/1.16500/1.16381/1.16386
- [21:00] 1.16382/1.16593/1.15947/1.16174
- [22:00] 1.16174/1.16206/1.15964/1.15977
- [23:00] 1.15977/1.15982/1.15847/1.15868
- [00:00] 1.15868/1.15891/1.15779/1.15808
- [01:00] 1.15809/1.15845/1.15779/1.15804
- [02:00] 1.15804/1.15876/1.15798/1.15860
- [03:00] 1.15859/1.15867/1.15793/1.15813

- M5 Micro Flow (Last 24 bars OHLC):
- [02:00] 1.15804/1.15820/1.15798/1.15803
- [02:05] 1.15803/1.15821/1.15800/1.15820
- [02:10] 1.15819/1.15831/1.15817/1.15818
- [02:15] 1.15819/1.15826/1.15810/1.15824
- [02:20] 1.15824/1.15850/1.15824/1.15848
- [02:25] 1.15848/1.15864/1.15848/1.15860
- [02:30] 1.15860/1.15867/1.15850/1.15860
- [02:35] 1.15860/1.15867/1.15850/1.15867
- [02:40] 1.15867/1.15872/1.15860/1.15865
- [02:45] 1.15865/1.15868/1.15853/1.15859
- [02:50] 1.15859/1.15871/1.15855/1.15864
- [02:55] 1.15865/1.15876/1.15860/1.15860
- [03:00] 1.15859/1.15867/1.15855/1.15855
- [03:05] 1.15855/1.15858/1.15839/1.15840
- [03:10] 1.15839/1.15856/1.15835/1.15856
- [03:15] 1.15856/1.15860/1.15844/1.15846
- [03:20] 1.15845/1.15849/1.15834/1.15838
- [03:25] 1.15840/1.15849/1.15834/1.15848
- [03:30] 1.15848/1.15850/1.15824/1.15826
- [03:35] 1.15826/1.15832/1.15807/1.15808
- [03:40] 1.15806/1.15814/1.15793/1.15812
- [03:45] 1.15813/1.15815/1.15806/1.15812
- [03:50] 1.15813/1.15828/1.15813/1.15819
- [03:55] 1.15819/1.15823/1.15806/1.15813

## 7. EVALUATION & JURY OUTPUT INSTRUCTIONS
- If setup is solid and actionable now -> select "APPROVE"
- If direction is sound but waiting for a retest limit is safer -> select "REVISE" with optimal entry_price / entry_type
- If market is plunging/surging with strong opposing momentum or trapped in chop -> select "REJECT" with risk_flag

Respond strictly in valid JSON:
{
  "verdict": "APPROVE" | "REVISE" | "REJECT",
  "confidence": float (0.00 to 1.00),
  "execution": {
    "entry_type": "market" | "buy_limit" | "sell_limit" | "buy_stop" | "sell_stop",
    "entry_price": float (null if market, required if pending),
    "sl_price": float (exact absolute price, 5 decimal places),
    "tp_price": float (exact absolute price, 5 decimal places)
  },
  "veto_reason": null | string (max 15 words if REJECT),
  "risk_flag": "NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "SYSTEMIC_CURRENCY_DUMP" | "HIGH_IMPACT_NEWS" | "CURRENCY_CONFLICT" | "MACRO_HEADWIND",
  "reasoning": "2-3 concise sentences justifying macro alignment, OB/station confluence, M5 micro flow, and exact SL/TP."
}

```

---

## 📜 3. Full Verbatim Prompt: Pass 2 Devil's Advocate CRO Prompt

```text
# INSTITUTIONAL TRADING JURY: CANDIDATE VERIFICATION & ORDER OPTIMIZER DOSSIER

Python Quantitative Engine has detected a potential quantitative setup (TREND_ALIGNED_PULLBACK) on EURUSD (H1).

## 1. INSTITUTIONAL BATTLEFIELD & CONFLUENCE
- Symbol: EURUSD | Asset: Forex Currency Pair (EURUSD)
- Setup Type: TREND_ALIGNED_PULLBACK | Proposed Direction: SELL | Current Price: 1.08800
- Macro Compass: D1_BEARISH_TREND | H4 Status: BEARISH (-1)
- H1 Wave State: PREMIUM_RELOAD_ARMED — H1 supply reload at 72% DR; Direction SELL enabled
- Intraday Dealing Range: 72.0% (EXTREME PREMIUM)
- Key Levels: PDH=1.09450 | PDL=1.08200 | PWH=1.09900 | PWL=1.07800 | DO=1.08650 | ADR Used: 6850.0%
- Volatility: ATR(14)=82.0 pts | Current Spread=20 pts | Rejection Wick: 45.0%
- Proposed Execution Method: MARKET @ 1.088
- Structural Zone Touch Count: 3 touches in last 40 bars
- Compression Duration / Range Age: 18 hours (MATURE_COMPRESSION_ARMED)

## 2. APEX PARAGON MACRO FUNDAMENTAL & ECONOMIC CONTEXT (40% Weight — Read Before Evaluating Technicals)

### APEX PARAGON MACRO FUNDAMENTAL BRIEFING (40% Weight)
• Base Currency (EUR)   : Score +0.00 | CB Rate: 3.75% (CUT_CYCLE) | Phase: PRICED_IN_EQUILIBRIUM
• Quote Currency (USD)  : Score -0.40 | CB Rate: 5.5% (HOLD / CUT_WATCH) | Phase: PRICED_IN_EQUILIBRIUM
• Fundamental Net Delta  : +0.40 | Net Carry Spread: -1.75%
• Currency Conflict Gate : 🟢 VALID CONVERGENCE (FAVOR BUY)
• Setup Classification   : GRADE_A_PLUS (Sizing: 1.0x)
• Macro Directive        : FAVOR_BUY (EUR Strong vs USD Weak | Net Delta +0.40)
• Recent Catalysts/Decay :
• [Trading Economics] Euro Slips as Hawkish Fed Tone Supports Dollar (0.0h ago)
• [Binance News] Dollar Rises After Fed Chair Warsh Remarks as Markets Await U.S. Jobs Data (0.0h ago)

- Economic Calendar Context: No High-Impact News releases within +/- 6 hours

## 3. CURRENCY FLOW & WAVE STATE CONFIRMATION

- M30 Structural Frame (50-bar / 24h Window):
  * 50-Bar High: 1.16594 | 50-Bar Low: 1.15779 | Position: 4.2% of Range
  * Moving Averages: EMA20 = 1.16015 | EMA50 = 1.16218 | EMA200 = 1.16277 (EMA20 < EMA50 < EMA200 (Bearish Alignment))
  * Volatility Meter: ATR(14) = 82.5 pts
- M15 Micro Flow Frame (32-bar / 8h Session Window):
  * 32-Bar High: 1.16594 | 32-Bar Low: 1.15779 | Position: 4.2% of Range
  * Moving Averages: EMA9 = 1.15836 | EMA21 = 1.15894 | EMA50 = 1.16060 (EMA9 < EMA21 < EMA50 (Bearish Momentum Stack))
  * Volatility Meter: ATR(14) = 52.3 pts
  * Micro Velocity: Last 3 bars avg candle body = 14.7 pts (0.28x ATR M15)


### GLOBAL CURRENCY STRENGTH MATRIX (Dual-Horizon Flow)
- 24-Hour Macro Flow (H1): [USD: +44.8, CAD: +6.4, JPY: +1.1, GBP: +0.1, AUD: -0.7, EUR: -16.0, CHF: -17.1, NZD: -18.6]
- 4-Hour Session Velocity (M15): [JPY: +6.8, NZD: +4.4, CHF: +2.2, USD: -0.0, AUD: -0.6, GBP: -3.9, CAD: -4.0, EUR: -4.8]
- Cross-Currency Relative Velocity (EURUSD):
  * Base (EUR): 24h = -16.01 (Rank #6/8) | 4h Session = -4.77 (Rank #8/8)
  * Quote (USD): 24h = +44.76 (Rank #1/8) | 4h Session = -0.02 (Rank #4/8)
  * Net 4-Hour Session Delta (EUR minus USD): -4.75 (BALANCED / SESSION COMPRESSION) | Net 24h Delta: -60.77

## 4. PURE QUANT 6-TF MACRO STRATEGIC DIRECTIVE (MSE) & ATLAS DNA STATIONS

## ATLAS DNA PSYCHOLOGICAL STATION MAP (16.2-Year Calibrated Grid)
- Step Grid: 1000 pips per station | Position in Range: 40.0%
- Station Ladder: ... 1.07000 -> [1.08000] -> [1.09000] <CURRENT 1.08800> -> [1.10000] -> 1.11000 ...
- Distances: to Lower 0.00800 | to Base 0.00200 | to Upper 0.01200
- Atlas DNA-Anchored Reference (Front-Running Pad TP = Station +/- [0.15xATR + Spread], SL = Opposing Station +/- [0.35xATR + Spread]):
  * Reference TP (SELL): 1.08032 | Reference SL: 1.10049


## 4. PURE QUANT 6-TF MACRO STRATEGIC DIRECTIVE (MSE)
- Macro Bias: -0.85 (BEARISH_PULLBACK) | Stability: HIGH_VOLATILITY | Phase: FRONTIER_EXHAUSTION_AT_1.16000
- Action Tier: FULL_ALLOW | Circuit Breaker: CLEAR
- SBR/RBS Hierarchy:
  * D1 Scale: Major SBR = 1.16552 | Major RBS = 1.14826
  * H4 Scale: SBR = 1.16366 | RBS = 1.14826
  * H1 Scale: SBR = 1.16366 | RBS = 1.14826
- 50-Pip Sub-Stations: Sub-Floor [1.155] <---> Sub-Ceiling [1.16]
- Target Landscape: TP1 (Proximal Station) = 1.15942 | TP2 (Macro Target) = 1.15026
- Baseline Floor SL: 1.16666 | Macro Invalidation: 1.17207

## 5. SMART MONEY CONCEPTS (SMC) & FRVP LIQUIDITY MAP
- Structural Floor (Strong Low): 1.08120 | Ceiling (Strong High): 1.09480
- Nearest Bullish OB: 1.08000–1.08200 | Nearest Bearish OB: 1.09300–1.09500
- Nearest Fair Value Gap (FVG Magnet): 1.08650–1.08800 (bearish FVG, unmitigated)
- Liquidity Pools: EQH cluster at 1.09450; EQL at 1.08050
- Fixed Range Volume Profile (FRVP): FRVP POC: 1.08870 | VAH: 1.09210 | VAL: 1.08540 (price at VAH — supply zone)

## 6. PROPOSED EXECUTION & STATION-ANCHORED LEVELS
- Scanner Raw SL: 1.09100 | Scanner Raw TP: 1.08200 | R:R: 2.00:1
- Atlas DNA-Anchored Reference: SL = 1.10049 | TP = 1.08032
  (TP snapped to nearest Station +[0.15xATR+Spread]; SL anchored behind opposing Station - [0.35xATR+Spread])

- D1 Daily Context (Last 3 days OHLC):
- [04:00] 1.16728/1.16770/1.16420/1.16534
- [04:00] 1.16463/1.16599/1.16366/1.16513
- [04:00] 1.16519/1.16593/1.15779/1.15813

- H4 Structural (Last 6 bars OHLC):
- [04:00] 1.16519/1.16549/1.16464/1.16533
- [08:00] 1.16532/1.16555/1.16451/1.16455
- [12:00] 1.16455/1.16492/1.16418/1.16445
- [16:00] 1.16445/1.16505/1.16394/1.16491
- [20:00] 1.16489/1.16593/1.15847/1.15868
- [00:00] 1.15868/1.15891/1.15779/1.15813

- H1 Execution (Last 12 bars OHLC):
- [13:00] 1.16446/1.16492/1.16431/1.16483
- [14:00] 1.16483/1.16488/1.16418/1.16465
- [15:00] 1.16466/1.16488/1.16420/1.16445
- [16:00] 1.16445/1.16451/1.16397/1.16398
- [17:00] 1.16399/1.16492/1.16394/1.16491
- [18:00] 1.16491/1.16495/1.16446/1.16452
- [19:00] 1.16451/1.16505/1.16394/1.16491
- [20:00] 1.16489/1.16500/1.16381/1.16386
- [21:00] 1.16382/1.16593/1.15947/1.16174
- [22:00] 1.16174/1.16206/1.15964/1.15977
- [23:00] 1.15977/1.15982/1.15847/1.15868
- [00:00] 1.15868/1.15891/1.15779/1.15808
- [01:00] 1.15809/1.15845/1.15779/1.15804
- [02:00] 1.15804/1.15876/1.15798/1.15860
- [03:00] 1.15859/1.15867/1.15793/1.15813

- M5 Micro Flow (Last 24 bars OHLC):
- [02:00] 1.15804/1.15820/1.15798/1.15803
- [02:05] 1.15803/1.15821/1.15800/1.15820
- [02:10] 1.15819/1.15831/1.15817/1.15818
- [02:15] 1.15819/1.15826/1.15810/1.15824
- [02:20] 1.15824/1.15850/1.15824/1.15848
- [02:25] 1.15848/1.15864/1.15848/1.15860
- [02:30] 1.15860/1.15867/1.15850/1.15860
- [02:35] 1.15860/1.15867/1.15850/1.15867
- [02:40] 1.15867/1.15872/1.15860/1.15865
- [02:45] 1.15865/1.15868/1.15853/1.15859
- [02:50] 1.15859/1.15871/1.15855/1.15864
- [02:55] 1.15865/1.15876/1.15860/1.15860
- [03:00] 1.15859/1.15867/1.15855/1.15855
- [03:05] 1.15855/1.15858/1.15839/1.15840
- [03:10] 1.15839/1.15856/1.15835/1.15856
- [03:15] 1.15856/1.15860/1.15844/1.15846
- [03:20] 1.15845/1.15849/1.15834/1.15838
- [03:25] 1.15840/1.15849/1.15834/1.15848
- [03:30] 1.15848/1.15850/1.15824/1.15826
- [03:35] 1.15826/1.15832/1.15807/1.15808
- [03:40] 1.15806/1.15814/1.15793/1.15812
- [03:45] 1.15813/1.15815/1.15806/1.15812
- [03:50] 1.15813/1.15828/1.15813/1.15819
- [03:55] 1.15819/1.15823/1.15806/1.15813

## 7. EVALUATION & JURY OUTPUT INSTRUCTIONS
- If setup is solid and actionable now -> select "APPROVE"
- If direction is sound but waiting for a retest limit is safer -> select "REVISE" with optimal entry_price / entry_type
- If market is plunging/surging with strong opposing momentum or trapped in chop -> select "REJECT" with risk_flag

Respond strictly in valid JSON:
{
  "verdict": "APPROVE" | "REVISE" | "REJECT",
  "confidence": float (0.00 to 1.00),
  "execution": {
    "entry_type": "market" | "buy_limit" | "sell_limit" | "buy_stop" | "sell_stop",
    "entry_price": float (null if market, required if pending),
    "sl_price": float (exact absolute price, 5 decimal places),
    "tp_price": float (exact absolute price, 5 decimal places)
  },
  "veto_reason": null | string (max 15 words if REJECT),
  "risk_flag": "NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "SYSTEMIC_CURRENCY_DUMP" | "HIGH_IMPACT_NEWS" | "CURRENCY_CONFLICT" | "MACRO_HEADWIND",
  "reasoning": "2-3 concise sentences justifying macro alignment, OB/station confluence, M5 micro flow, and exact SL/TP."
}


## 7. PREVIOUS JURY PROPOSALS (TARGET OF YOUR CROSS-EXAMINATION)
The first-round panel members have analyzed this setup and submitted the following findings:
- Model [OpenAI]: Verdict = APPROVE (Conf 88.00)
  Proposed Execution: {'entry_type': 'market', 'entry_price': 1.088, 'sl_price': 1.091, 'tp_price': 1.082}
  Thesis / Rationale: "D1 SBR rejection at 1.0945 confirmed. Bearish pullback to 1.0880 offers high R:R short entry targeting D1 proximal floor 1.0820."
- Model [Gemini]: Verdict = APPROVE (Conf 85.00)
  Proposed Execution: {'entry_type': 'market', 'entry_price': 1.088, 'sl_price': 1.0915, 'tp_price': 1.0815}
  Thesis / Rationale: "Wave state shows PREMIUM_RELOAD_ARMED with confirmed supply reaction. Strong USD fundamental momentum and carry advantage support short."

## 8. DEVIL'S ADVOCATE AUDIT DIRECTIVE
You are the Chief Risk Officer & Devil's Advocate. Your mission is to scrutinize their arguments against the raw M5/H1 candle data:
1. Examine if their thesis ignores recent counter-trend momentum, lack of rejection wicks, or structural traps.
2. If you find a critical flaw, liquidity trap, or news risk -> VETO by selecting "REJECT" with an explicit veto_reason and risk_flag.
3. If their thesis is mathematically solid and accounts for risks (e.g. valid pending limit) -> select "APPROVE" or "REVISE".

Respond strictly in the same JSON format:
{
  "verdict": "APPROVE" | "REVISE" | "REJECT",
  "confidence": float (0.00 to 1.00),
  "execution": {
    "entry_type": "market" | "buy_limit" | "sell_limit" | "buy_stop" | "sell_stop",
    "entry_price": float (null if market, required if pending),
    "sl_price": float (exact absolute price),
    "tp_price": float (exact absolute price)
  },
  "veto_reason": null | string (max 15 words if REJECT),
  "risk_flag": "NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "SYSTEMIC_CURRENCY_DUMP" | "HIGH_IMPACT_NEWS" | "CURRENCY_CONFLICT" | "MACRO_HEADWIND",
  "reasoning": "2-3 concise sentences explaining whether you accept or tear down their arguments."
}

```

---
*Dokumen ini digenerate otomatis oleh sistem benchmark produksi trading bot branch `quant-trade`.*
