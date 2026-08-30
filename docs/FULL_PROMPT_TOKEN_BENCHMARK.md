# Full Production Dossier Prompt & Token Benchmark — Prompt Architecture V2 (August 2026)

> **Dokumen Resmi Acuan Prompt & Konsumsi Token AI — Prompt Architecture V2 (Cache-Optimized)**.
> Berisi cetakan verbatim *Static System Directives Prefix* (di-cache di server AI), *Full High-Density Dossier Prompt* (Pass 1 Dynamic), dan *Devil's Advocate CRO Cross-Examination Prompt* (Pass 2) mencakup seluruh modul kuantitatif terbaru (MSE 6-TF, Symmetrical Wave State, Boitoki CSM, Apex Paragon Macro Fundamental 40%, LuxSMC, FRVP, dan 24 Candle M5).

---

## 📊 1. Ringkasan Metrik & Estimasi Biaya Token

| Komponen Evaluasi | Karakter | Kata | Token (o200k: OpenAI o4-mini) | Token (cl100k: DeepSeek/Claude) | Estimasi Biaya API |
|---|---|---|---|---|---|
| **Pass 1 Dossier (OpenAI)** | 8,163 | 1,110 | **2,148** | 2,206 | ~$0.0006 |
| **Pass 1 Dossier (Gemini)** | 8,163 | 1,110 | **2,148** | 2,206 | ~$0.0001 |
| **Pass 2 Devil's CRO (DeepSeek)** | 10,220 | 1,387 | 2,689 | **2,762** | ~$0.0003 |
| **🏆 TOTAL PER SETUP A+ (3-AI JURY)** | **26,546** | **3,607** | **~6,985 Token Total** | **~7,174 Token Total** | **~$0.0010 per Setup** |

### 📉 Perbandingan V1 vs V2

| Metrik | Prompt V1 | Prompt V2 | Penghematan |
|---|---|---|---|
| Pass 1 Tokens (o200k) | 3,036 | **2,148** | **-29.3%** |
| Pass 2 Tokens (o200k) | 3,577 | **2,689** | **-24.8%** |
| Total Token per Setup | 9,649 | **6,985** | **-27.6%** |
| Informasi Data Hilang | — | **0% (Zero Loss)** | — |

> [!NOTE]
> Karena arsitektur **2-Stage Quant Funnel** kita hanya memicu Stage 2 pada **8–15 setup A+ per hari** (sisanya disaring radar lokal 0 token), maka total biaya API harian adalah **~$0.015 / hari (kurang dari Rp 250,- per hari)**!

> [!TIP]
> **Static System Directives Prefix** (`get_static_jury_system_prompt()`) berisi 7 Master Risk Veto, 4-Grade Quality Matrix, dan Front-Running Pad Formula. Block ini bersifat tetap dan dapat di-cache otomatis oleh server OpenAI/DeepSeek — potensi diskon tambahan 50% biaya input prefix di masa depan.

---

## 📜 2. Static System Directives Prefix (get_static_jury_system_prompt)

```text
You are the Chief Investment Officer (CIO) and Chief Risk Officer (CRO) of an institutional quantitative hedge fund.
Your mission is to evaluate candidate setups proposed by the Python Quantitative Engine with zero emotional bias.

### 1. CORE OPERATIONAL DIRECTIVES:
1. Strict Unanimous Consensus: All active models must agree on direction (BUY or SELL). If split or uncertain, default to HOLD/REJECT.
2. Mandatory R:R Gate: Minimum R:R >= 1.25. Anchor SL behind physical structural barriers (MSE SBR/RBS, SMC Order Block, or Atlas DNA station + 0.35x ATR anti-wick buffer).
3. Hybrid Targeting & Front-Running Pad:
   - TP_BUY  = Station - (0.15 x ATR + Spread)
   - TP_SELL = Station + (0.15 x ATR + Spread)
4. Symmetrical Wave State Permission:
   - BUY: DEMAND_REACTION_GO / DISCOUNT_RELOAD_ARMED. Never catch falling knives (WATERFALL_LOCK).
   - SELL: SUPPLY_REACTION_GO / PREMIUM_RELOAD_ARMED. Never adang rocket spikes (VERTICAL_SPIKE_LOCK).
5. 4-Grade Quality Matrix:
   - GRADE_S    (God-Tier,    1.0x Lot, 3.0x ATR TP — Multi-Day Hold, Stagnation Immune)
   - GRADE_A_PLUS (High Conviction, 1.0x Lot, 2.0x ATR TP)
   - GRADE_A    (Standard,    1.0x Lot, 1.5x ATR TP)
   - GRADE_B    (Defensive,   0.50x Lot, 1.25x ATR — Scalp TP1 Only, BEP at 35% TP)

### 2. MASTER INSTITUTIONAL HARD RISK VETO FLAGS:
If any of these conditions are present, you MUST reject the trade (Verdict: REJECT or Signal: HOLD):
- COUNTER_TREND_MOMENTUM: Counter-trend against H4/D1 trend or unmitigated falling knife.
- LIQUIDITY_TRAP: Entry directly in front of Equal Highs/Lows (EQH/EQL) or structural ceiling.
- IMPULSE_CHASE: FOMO chase of extended candle without basing -> select REVISE to Pending Limit.
- SYSTEMIC_CURRENCY_DUMP: Base currency collapsing across 8-currency Boitoki CSM.
- HIGH_IMPACT_NEWS: Active The Storm window (+/- 15-30 min of Tier-1 release).
- SEVERE_CURRENCY_CONFLICT: Both currencies have extreme magnitude scores (|S| >= 0.50) with Net Delta < 0.15.
- MACRO_HEADWIND: Carry spread >= 3.0% against technical direction during catalyst window.
```

---

## 📜 3. Full Verbatim Prompt: Pass 1 High-Density Dossier Prompt (Dynamic User Prompt)

```text
# INSTITUTIONAL TRADING JURY: CANDIDATE VERIFICATION & ORDER OPTIMIZER DOSSIER

Python Quantitative Engine has detected a potential quantitative setup (TREND_ALIGNED_PULLBACK) on EURUSD (H1).

## 1. INSTITUTIONAL BATTLEFIELD & CONFLUENCE
- Symbol: EURUSD | Asset: Forex Currency Pair (EURUSD)
- Setup Type: TREND_ALIGNED_PULLBACK | Proposed Direction: SELL | Current Price: 1.088
- Macro Compass:  | H4 Status: BEARISH (-1)
- H1 Wave State:  ()
- Intraday Dealing Range: 50.0% (EQUILIBRIUM)
- Key Levels: PDH=1.0945 | PDL=1.082 | PWH=1.099 | PWL=1.078 | DO=1.0865 | ADR Used: 6850.0%
- Volatility: ATR(14)=0.0 pts | Current Spread=20 pts | Rejection Wick: 0.0%
- Proposed Execution Method: MARKET @ 1.088
- Structural Zone Touch Count: 3 touches in last 40 bars
- Compression Duration / Range Age: 18 hours (MATURE_COMPRESSION_ARMED)

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


## ATLAS DNA PSYCHOLOGICAL STATION MAP (16.2-Year Calibrated Grid)
- Calibrated Step Grid: 100 pips per station (backtest-proven from MetaQuotes 2010-2026)
- Station Ladder: ... 1.07 → [1.08] → [1.09] ← CURRENT → [1.1] → 1.11 ...
- Current Price: 1.088 | Position in Range: 40.0% (0% = at Lower Station, 100% = at Upper Station)
- Distance to Lower [1.08]: 0.00800 | Distance to Base [1.09]: 0.00200 | Distance to Upper [1.1]: 0.01200
- CRITICAL: These psychological stations are natural magnets/barriers where institutional orders cluster. Use them to INDEPENDENTLY determine your TP (next station in YOUR assessed trend direction) and SL (behind the opposing station + 0.35x ATR anti-wick buffer). Do NOT blindly follow the proposed direction.


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

## 2. SMART MONEY CONCEPTS (SMC) & LIQUIDITY MAP
- Structural Floor (Strong Low): 0.0 | Ceiling (Strong High): 0.0
- Nearest Bullish OB: None nearby | Nearest Bearish OB: None nearby
- Nearest Fair Value Gap (FVG Magnet): None nearby
- Liquidity Pools: Clear of immediate EQH/EQL traps
- Fixed Range Volume Profile (FRVP): Standard Institutional Liquidity

## 3. PROPOSED EXECUTION & STATION-ANCHORED LEVELS
- Proposed Technical SL: 1.091 (Anchor behind structural station/OB + 0.35x ATR anti-wick buffer)
- Proposed Technical TP: 1.082 (Target: nearest station in SELL direction)
- Risk:Reward Ratio: 2.00:1 (Mandatory >= 1.25)

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

## 4. APEX PARAGON MACRO FUNDAMENTAL & ECONOMIC CONTEXT

### APEX PARAGON MACRO FUNDAMENTAL BRIEFING (40% Weight)
• Base Currency (EUR)   : Score +0.00 | CB Rate: 3.75% (CUT_CYCLE) | Phase: PRICED_IN_EQUILIBRIUM
• Quote Currency (USD)  : Score -0.40 | CB Rate: 5.5% (HOLD / CUT_WATCH) | Phase: PRICED_IN_EQUILIBRIUM
• Fundamental Net Delta  : +0.40 | Net Carry Spread: -1.75%
• Currency Conflict Gate : 🟢 VALID CONVERGENCE (FAVOR BUY)
• Setup Classification   : GRADE_A_PLUS (Sizing: 1.0x)
• Macro Directive        : FAVOR_BUY (EUR Strong vs USD Weak | Net Delta +0.40)
• Recent Catalysts/Decay :
• [Reuters] Europe's central bankers fear more turbulence in testy U.S. relations (0.0h ago)
• [Binance News] Dollar Rises After Fed Chair Warsh Remarks as Markets Await U.S. Jobs Data (0.0h ago)

- Economic Calendar Context: No High-Impact News releases within +/- 6 hours

## 5. EVALUATION & JURY OUTPUT INSTRUCTIONS
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
    "sl_price": float (exact absolute price),
    "tp_price": float (exact absolute price)
  },
  "veto_reason": null | string (max 15 words if REJECT),
  "risk_flag": "NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "SYSTEMIC_CURRENCY_DUMP" | "HIGH_IMPACT_NEWS" | "CURRENCY_CONFLICT" | "MACRO_HEADWIND",
  "reasoning": "2-3 concise sentences justifying macro alignment, OB/station confluence, M5 micro flow, and exact SL/TP."
}

```

---

## 📜 4. Full Verbatim Prompt: Pass 2 Devil's Advocate CRO Prompt (Cross-Examination)

```text
# INSTITUTIONAL TRADING JURY: CANDIDATE VERIFICATION & ORDER OPTIMIZER DOSSIER

Python Quantitative Engine has detected a potential quantitative setup (TREND_ALIGNED_PULLBACK) on EURUSD (H1).

## 1. INSTITUTIONAL BATTLEFIELD & CONFLUENCE
- Symbol: EURUSD | Asset: Forex Currency Pair (EURUSD)
- Setup Type: TREND_ALIGNED_PULLBACK | Proposed Direction: SELL | Current Price: 1.088
- Macro Compass:  | H4 Status: BEARISH (-1)
- H1 Wave State:  ()
- Intraday Dealing Range: 50.0% (EQUILIBRIUM)
- Key Levels: PDH=1.0945 | PDL=1.082 | PWH=1.099 | PWL=1.078 | DO=1.0865 | ADR Used: 6850.0%
- Volatility: ATR(14)=0.0 pts | Current Spread=20 pts | Rejection Wick: 0.0%
- Proposed Execution Method: MARKET @ 1.088
- Structural Zone Touch Count: 3 touches in last 40 bars
- Compression Duration / Range Age: 18 hours (MATURE_COMPRESSION_ARMED)

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


## ATLAS DNA PSYCHOLOGICAL STATION MAP (16.2-Year Calibrated Grid)
- Calibrated Step Grid: 100 pips per station (backtest-proven from MetaQuotes 2010-2026)
- Station Ladder: ... 1.07 → [1.08] → [1.09] ← CURRENT → [1.1] → 1.11 ...
- Current Price: 1.088 | Position in Range: 40.0% (0% = at Lower Station, 100% = at Upper Station)
- Distance to Lower [1.08]: 0.00800 | Distance to Base [1.09]: 0.00200 | Distance to Upper [1.1]: 0.01200
- CRITICAL: These psychological stations are natural magnets/barriers where institutional orders cluster. Use them to INDEPENDENTLY determine your TP (next station in YOUR assessed trend direction) and SL (behind the opposing station + 0.35x ATR anti-wick buffer). Do NOT blindly follow the proposed direction.


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

## 2. SMART MONEY CONCEPTS (SMC) & LIQUIDITY MAP
- Structural Floor (Strong Low): 0.0 | Ceiling (Strong High): 0.0
- Nearest Bullish OB: None nearby | Nearest Bearish OB: None nearby
- Nearest Fair Value Gap (FVG Magnet): None nearby
- Liquidity Pools: Clear of immediate EQH/EQL traps
- Fixed Range Volume Profile (FRVP): Standard Institutional Liquidity

## 3. PROPOSED EXECUTION & STATION-ANCHORED LEVELS
- Proposed Technical SL: 1.091 (Anchor behind structural station/OB + 0.35x ATR anti-wick buffer)
- Proposed Technical TP: 1.082 (Target: nearest station in SELL direction)
- Risk:Reward Ratio: 2.00:1 (Mandatory >= 1.25)

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

## 4. APEX PARAGON MACRO FUNDAMENTAL & ECONOMIC CONTEXT

### APEX PARAGON MACRO FUNDAMENTAL BRIEFING (40% Weight)
• Base Currency (EUR)   : Score +0.00 | CB Rate: 3.75% (CUT_CYCLE) | Phase: PRICED_IN_EQUILIBRIUM
• Quote Currency (USD)  : Score -0.40 | CB Rate: 5.5% (HOLD / CUT_WATCH) | Phase: PRICED_IN_EQUILIBRIUM
• Fundamental Net Delta  : +0.40 | Net Carry Spread: -1.75%
• Currency Conflict Gate : 🟢 VALID CONVERGENCE (FAVOR BUY)
• Setup Classification   : GRADE_A_PLUS (Sizing: 1.0x)
• Macro Directive        : FAVOR_BUY (EUR Strong vs USD Weak | Net Delta +0.40)
• Recent Catalysts/Decay :
• [Reuters] Europe's central bankers fear more turbulence in testy U.S. relations (0.0h ago)
• [Binance News] Dollar Rises After Fed Chair Warsh Remarks as Markets Await U.S. Jobs Data (0.0h ago)

- Economic Calendar Context: No High-Impact News releases within +/- 6 hours

## 5. EVALUATION & JURY OUTPUT INSTRUCTIONS
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
    "sl_price": float (exact absolute price),
    "tp_price": float (exact absolute price)
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
