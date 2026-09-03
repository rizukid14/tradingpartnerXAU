# OpenAI Prompt Dossier (o4-mini — Chief Quantitative Macro Strategist)

> **Timestamp**: `2026-09-02 18:16:19 WIB` | **Asset**: `EURCAD-ECNc` | **Timeframe**: `H1` | **Architecture**: `Stage 2 Pass 1`

```markdown
# ROLE: CHIEF QUANTITATIVE MACRO STRATEGIST (OPENAI o4-mini)
You are the Chief Quantitative Macro Strategist of an institutional hedge fund.
Your SOLE RESPONSIBILITY is to evaluate the HTF Structural Dealing Range, Macro Corridor Alignment, and Multi-Day Trend Regime for EURCAD-ECNc.
You DO NOT evaluate micro candlestick wicks.

## 1. STRATEGIC CONTEXT & CANDLESTICK TAPES:
- Symbol: EURCAD-ECNc | Proposed Direction: BUY | Live Price: 1.61240
- Macro Compass: D1_BULLISH_EXPANSION | H4_RANGING_FLAG_BOX | FADE_CORRIDOR_EXTREMES | H4 Status: H4_RANGING_FLAG_BOX
- Wave State: MSE_WATCH_ONLY — [NEUTRAL | MSE: WATCH_ONLY | CSM +2.05] -> WATCH
- Intraday Dealing Range Position: 46.2% (EQUILIBRIUM)
- Volatility: ATR(14) H1 = 96.0 pts | Spread = 2 pts

### [TIMEFRAME D1] Multi-Day Macro Context (Last 5 Daily Bars):
  [07:00] BEAR | O:1.61612 H:1.61855 L:1.61340 C:1.61426 | Body:18.6p WickU:24.3p WickL:8.6p
  [07:00] BEAR | O:1.61384 H:1.61452 L:1.61008 C:1.61059 | Body:32.5p WickU:6.8p WickL:5.1p
  [07:00] BEAR | O:1.61011 H:1.61225 L:1.60869 C:1.60941 | Body:7.0p WickU:21.4p WickL:7.2p
  [07:00] BULL | O:1.60930 H:1.61247 L:1.60754 C:1.61093 | Body:16.3p WickU:15.4p WickL:17.6p
  [07:00] BULL | O:1.61073 H:1.61368 L:1.60917 C:1.61236 | Body:16.3p WickU:13.2p WickL:15.6p

### [TIMEFRAME H4] Structural Trend & Expansion Wave (Last 8 H4 Bars):
  [15:00] BEAR | O:1.60925 H:1.60969 L:1.60754 C:1.60815 | Body:11.0p WickU:4.4p WickL:6.1p
  [19:00] BULL | O:1.60815 H:1.60966 L:1.60774 C:1.60944 | Body:12.9p WickU:2.2p WickL:4.1p
  [23:00] BULL | O:1.60943 H:1.61247 L:1.60899 C:1.61090 | Body:14.7p WickU:15.7p WickL:4.4p
  [03:00] BULL | O:1.61090 H:1.61194 L:1.61019 C:1.61093 | Body:0.3p WickU:10.1p WickL:7.1p
  [07:00] BEAR | O:1.61073 H:1.61137 L:1.60928 C:1.60990 | Body:8.3p WickU:6.4p WickL:6.2p
  [11:00] BULL | O:1.60990 H:1.61153 L:1.60917 C:1.61150 | Body:16.0p WickU:0.3p WickL:7.3p
  [15:00] BULL | O:1.61150 H:1.61368 L:1.61038 C:1.61280 | Body:13.0p WickU:8.8p WickL:11.2p
  [19:00] BEAR | O:1.61280 H:1.61330 L:1.61158 C:1.61236 | Body:4.4p WickU:5.0p WickL:7.8p

### Pure Quant 6-TF Macro Strategic Directive (MSE)
- Dealing Chamber: Floor F1=1.61172 │ Ceiling C1=1.61334 │ Chamber Pos: 44.0%
- Structural Stage: CHAMBER_CONSOLIDATION_[1.61172-1.61334] | Market State: NEUTRAL_CHAMBER
- Macro Bias: RANGE_BOUND (+0.00) -> FADE_CORRIDOR_EXTREMES
- Layered Resistance Ceilings (C1-C4):
  * C1: 1.61294 (H4_VAH, Score: 3.5)
  * C2: 1.61334 (BEAR_OB+H1_SBR, Score: 2.5)
  * C3: 1.61380 (BEAR_OB+D1_SBR+H4_SBR, Score: 5.17)
  * C4: 1.61489 (BEAR_OB+D1_EQH_POOL+PSYCH_100+W1_SUPPLY, Score: 7.5)
- Layered Support Floors (F1-F4):
  * F1: 1.61172 (H1_EMA200+H4_EMA200+H4_EMA50, Score: 3.45)
  * F2: 1.61133 (BULL_OB+D1_EMA20+D1_EMA50+H4_HVN, Score: 4.5)
  * F3: 1.61094 (H1_EMA50, Score: 2.0)
  * F4: 1.61039 (H4_HVN, Score: 3.0)
- Mandate Thesis: EURCAD-ECNc is consolidating inside dealing chamber (Range: 44%). Discipline requires waiting for extreme boundary touch at 1.61172 or 1.61334.
- Forbidden Traps: Do NOT execute market orders in mid-chamber consolidation zone (Range: 44%)



### Global Currency Strength Matrix (CSM)
### GLOBAL CURRENCY STRENGTH MATRIX (Dual-Horizon Flow)
- 24-Hour Macro Flow (H1): [JPY: +51.5, USD: +33.2, AUD: +21.0, EUR: +18.1, CAD: -2.4, GBP: -3.1, CHF: -25.4, NZD: -92.8]
- 4-Hour Session Velocity (M15): [EUR: +10.8, USD: +8.6, CAD: +6.4, AUD: +1.3, JPY: +0.1, GBP: -2.8, CHF: -10.1, NZD: -14.3]
- Cross-Currency Relative Velocity (EURCAD-ECNc):
  * Base (EUR): 24h = +18.06 (Rank #4/8) | 4h Session = +10.81 (Rank #1/8)
  * Quote (CAD): 24h = -2.43 (Rank #5/8) | 4h Session = +6.41 (Rank #3/8)
  * Net 4-Hour Session Delta (EUR minus CAD): +4.40 (BALANCED / SESSION COMPRESSION) | Net 24h Delta: +20.49

### RESEARCH SHADOW METRIC — CAPITAL ROTATION & DUAL-BASKET CONFLUENCE
(Note: Exploratory shadow metric for supplementary context only — do NOT override core technical structure)
- Dual-Basket Classification (EURCAD-ECNc): [PURE_CATCHUP_LEAD_LAG]
- Base (EUR) Basket Status: 1 ARRIVED (EURCHF), 5 EN_ROUTE, 1 ON_HOLD (EURCAD) | Leader: EURCHF (98% pos, 0.00x ATR to wall)
- Quote (CAD) Basket Status: 0 ARRIVED (None), 4 EN_ROUTE, 2 ON_HOLD (EURCAD,AUDCAD) | Leader: USDCAD (10% pos, 0.00x ATR to wall)
- Analytical Confluence Directive: Base EUR Leader (EURCHF (98% pos, 0.00x ATR to wall)) hit wall while EURCAD-ECNc is lagging at 46% range. High-probability catch-up candidate.

### Apex Paragon Macro Fundamental Scorecard
### APEX PARAGON MACRO FUNDAMENTAL BRIEFING (40% Weight)
• Base Currency (EUR)   : Score -0.04 | CB Rate: 3.75% (CUT_CYCLE) | Phase: THE_CALM
• Quote Currency (CAD)  : Score -0.08 | CB Rate: 4.5% (CUT_CYCLE) | Phase: PRICED_IN_EQUILIBRIUM
• Fundamental Net Delta  : +0.04 | Net Carry Spread: -0.75%
• Currency Conflict Gate :  NO SIGNAL (FLAT MACRO)
• Setup Classification   : GRADE_A (Sizing: 1.0x)
• Macro Directive        : PURE_TECHNICAL_MODE (Macro is neutral - Trade MSE Sockets & SMC)
• Recent Catalysts/Decay :
• [Dow Jones Newswires] Euro Falls, Deemed Vulnerable Due to High Energy Prices — Market Talk (0.0h ago)
• [Reuters] Canadian dollar weakens ahead of BoC rate decision, 10-year yield hits a 2-year high (0.0h ago)
- Economic Calendar: ### UPCOMING HIGH-IMPACT ECONOMIC EVENTS (next 6h)
- [CAD] BOC Rate Statement in 2.5h (Wed 02 Sep 20:45 WIB) [HIGH]
- [CAD] Overnight Rate in 2.5h (Wed 02 Sep 20:45 WIB) [HIGH]
- [CAD] BOC Press Conference in 3.2h (Wed 02 Sep 21:30 WIB) [HIGH]
### RECENTLY RELEASED HIGH-IMPACT EVENTS (last 6h) -- volatility may persist, do not fade the move
- [EUR] Spanish Unemployment Change 4.3h ago (Wed 02 Sep 14:00 WIB) [MEDIUM]

## 2. STRATEGIC MANDATE & DECISION LOGIC:
1. Classify the Market Regime: Is this TRUE EXPANSION (Trend Continuation / Absorption), ACCUMULATION / COMPRESSION, or RANGE MEAN-REVERSION (Chamber Bounce)?
2. Corridor Delivery: Has the price established structural acceptance above the base station to deliver price to the next macro target?
3. STRICT ANTI-FOMO EXECUTION: If price is breaking out in Extreme Territory (Dealing Range >= 85% for BUY or <= 15% for SELL), you are FORBIDDEN from choosing 'market' entry. You MUST choose 'buy_limit' / 'sell_limit' at the broken SBR/RBS level, or select 'REJECT' / 'HOLD' if the move is over-extended without a resting anchor.
4. Decide whether the macro environment warrants "APPROVE" (immediate/trend aligned), "REVISE" (wait for pullback/retest limit), or "REJECT" (counter-trend/structural trap).

Respond strictly in valid JSON:
{
  "verdict": "APPROVE" | "REVISE" | "REJECT",
  "signal": "BUY" | "HOLD",
  "confidence": float (0.00 to 1.00),
  "role": "STRATEGIC_STRUCTURE",
  "regime": "EXPANSION_TREND" | "ABSORPTION_PRE_BREAKOUT" | "RANGE_BOUND" | "EXHAUSTION_REVERSAL",
  "station_corridor": "string describing delivery path e.g. 1.09500 -> 1.10020",
  "execution": {
    "entry_type": "market" | "buy_limit" | "sell_limit",
    "entry_price": float (null if market, exact price if pending),
    "sl_price": float (exact price behind structural invalidation, 5 decimals),
    "tp_price": float (exact price at next macro station/barrier, 5 decimals)
  },
  "risk_flag": "NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "SYSTEMIC_CURRENCY_DUMP" | "HIGH_IMPACT_NEWS",
  "reasoning": "2-3 concise sentences justifying HTF structural corridor alignment, dealing chamber state, and station targets."
}
```
