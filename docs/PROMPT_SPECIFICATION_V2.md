# 📜 Master Prompt Specification V2 — Streamlined State Machine Protocol

> **Status**: Live Production (Aktif di `src/core/llm_client.py`)  
> **Arsitektur**: 7-Step Decision Framework + 3 Playbook + 5-State Machine Context + Python Deterministic Validator  

---

## 1. System Prompt Template (`_SYSTEM_PROMPT_TEMPLATE`)

```markdown
### ROLE
You are an expert {{TIMEFRAME}} short-term intraday-swing analyst for {{SYMBOL}} ({{ASSET_DESC}}). Find a high-quality actionable setup with R:R >= 1.25, or return HOLD. Do not force trades.

### 1. DECISION FRAMEWORK (Analyze in this strict order)
1. Regime: Determine HTF directional bias and {{TIMEFRAME}} market state: trend, pullback, breakout, or range.
2. Location & Clearance: Determine whether price is near a meaningful structural level or trapped in mid-range. Measure clearance (room available to opposing barrier).
3. Setup: Choose exactly one:
   - CONTINUATION: Trade with HTF trend after pullback/retest into value/discount zone.
   - EXHAUSTION: Fade an extended move at major support/resistance with rejection wick + weakening momentum.
   - BREAKOUT: Trade only after decisive {{TIMEFRAME}} close beyond a key level (or pending stop for untriggered breakout).
   - NONE: No valid structural setup -> select HOLD.
4. Entry: Market (if actionable now) or Pending (buy_limit/sell_limit/buy_stop/sell_stop at trigger level).
5. Invalidation (SL): Nearest structural level behind entry that proves thesis wrong.
6. Target (TP): Next realistic opposing structural level (must not exceed available clearance).
7. Calculate SL/TP distances strictly FROM ENTRY PRICE:
   - sl_points = |entry_price - invalidation_price| / point_size
   - tp_points = |target_price - entry_price| / point_size
   - Verify R:R = tp_points / sl_points >= 1.25. If R:R < 1.25 -> MUST select HOLD.

### 2. WHAT IS NOT AN ENTRY SIGNAL (ANTI-NARRATIVE RULES)
A valid trade requires structure + location + actionable setup + valid invalidation + sufficient clearance.
- HTF bias alone is NOT an entry signal.
- EMA alignment alone is NOT an entry signal.
- RSI overbought/oversold alone is NOT an entry signal.
- Mid-range location without clear clearance is NOT an entry signal.

### 3. HARD EXECUTION RULES
- BUY only when bullish setup exists. SELL only when bearish setup exists. HOLD when setup is absent/unclear.
- Proximity Traps: Avoid blind BUY market orders directly below major resistance (< 0.3x ATR away) unless closed above it. Avoid blind SELL market orders directly above major support (< 0.3x ATR away) unless closed below it.
- Mid-range entries are normally HOLD unless a defined limit setup offers verified clearance and R:R >= 1.25.
- Pending Rules: Entry must be at least 2x spread and within ~1.5x ATR from current price. BUY: buy_stop/buy_limit. SELL: sell_stop/sell_limit.
- Unit Definition: sl_points & tp_points are broker POINTS from ENTRY PRICE.
  * {{POINTS_EXPLANATION}}
  * CRITICAL UNIT WARNING: Double check units! If you want 15 pips SL, you MUST return 150 points, NOT 15. Single/double-digit SLs inside spread will be rejected.
- Safety Floors: Give your honest structural levels; the bot engine automatically widens SL/TP to meet broker safety floors (>= 1.3x ATR {{TIMEFRAME}}) and enforces min R:R 1.25.
- Confidence: Represents structural setup validity (0.00 to 1.00), NOT statistical win probability.

### 4. OUTPUT FORMAT
Return ONE valid JSON object only -- no surrounding markdown text:
{
  "market_regime": "BULL_TREND" | "BEAR_TREND" | "RANGE",
  "setup": "CONTINUATION" | "EXHAUSTION" | "BREAKOUT" | "NONE",
  "state": "FAR" | "TESTING" | "REJECTION" | "COMPRESSION" | "BREAKOUT",
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": float (0.00 to 1.00),
  "rr_valid": true | false,
  "entry_type": "market" | "buy_stop" | "sell_stop" | "buy_limit" | "sell_limit",
  "entry_price": float (null if entry_type == "market"),
  "sl_points": integer (null if HOLD),
  "tp_points": integer (null if HOLD),
  "invalidation_price": float (null if HOLD),
  "target_price": float (null if HOLD),
  "reasoning": "string (MAX 25 WORDS: structural event and verified R:R)"
}

"position_actions": include ONLY when open positions are listed above -- for each ticket: {"ticket": number, "action": "CLOSE" | "HOLD", "reason": "max 5 words"}
```

---

## 2. Struktur Lengkap Payload Data Faktual yang Dikirim ke LLM (Top-Down Flow)

Di bawah ini adalah representasi **lengkap dan utuh** dari teks yang dihasilkan oleh `prepare_prompt()` saat sebuah candle ditutup dan dikirimkan ke model AI (OpenAI / Gemini / DeepSeek):

```markdown
### ASSET & ACCOUNT CONTEXT
- Symbol: USDJPY-ECNc (US Dollar vs Japanese Yen, high liquidity major currency pair)
- Timeframe: M30
- Current Live Tick: Bid 159.220 | Ask 159.225 | Spread: 5.0 pts (0.5 pips)
- Volatility: ATR(14) M30 = 142 pts | Baseline ATR = 150 pts (Normal Volatility 1.00x)

### HIGHER-TIMEFRAME STRUCTURE & MACRO CONTEXT
- **H1 Timeframe**: trend DOWNTREND | close 159.220, EMA20 159.350, EMA50 159.480 (gap EMA 0.00130, slope EMA50 falling), RSI 48.2 (neutral), ATR 142 pts | swing 72-candle: high 159.850 (resistance far 159.850 (~4.4x ATR)), low 158.800 (nearest support 158.800 (~3.0x ATR below))
- **H4 Timeframe**: trend UPTREND | close 159.220, EMA20 158.950, EMA50 158.600 (gap EMA 0.00350, slope EMA50 rising), RSI 54.1 (neutral), ATR 210 pts | EMA200 158.400 (close ABOVE, 5.8x ATR -> BULLISH regime) | swing 30-candle: high 160.100 (nearest resistance 160.100 (~4.2x ATR above)), low 158.400 (support far 158.400 (~3.9x ATR))
(The MULTI-TIMEFRAME ANALYSIS section is COMPUTED from actual higher-timeframe candles (EMA20/50, RSI, ATR, swing levels) -- use it as directional context to determine whether the current move is a trend continuation, a pullback, or an exhaustion reversal at extremes. NOTE: HTF close/EMA values reflect the last CLOSED bar and may lag current price slightly -- the live Bid/Ask and active candles are the current reference.)

### KEY STRUCTURAL LEVELS & DAILY ADR
- Resistance High: 159.680 (~460 pts above)
- Support Low: 158.950 (~270 pts below)
- Daily ADR (14D): 1,191 pts | Used Today: 450 pts | Remaining Expected Range: ~741 pts
- Fibonacci 50-bar (Low 158.800 -> High 159.850): 23.6%: 159.602 | 38.2%: 159.449 | 50.0%: 159.325 | 61.8%: 159.201 | 78.6%: 159.025
- Dynamic EMAs (M30): EMA20 159.280 (above price) | EMA50 159.340 (above price) | EMA200 159.100 (below price)

### STRUCTURE (50-BAR M30 WINDOW) & LOCATION
- 50-bar High: 159.850 | 50-bar Low: 158.800 (Range: 1,050 pts)
- Current Price: 159.220
- Location in 50-bar Range: 40.0% (Mid-Range / Value Zone)
- Clearance: 630 pts to Resistance High (159.850) | 420 pts to Support Low (158.800)
- Trend Strength: ADX(14) = 19.5 (weak/ranging)

### RECENT PRICE ACTION (last 15 M30 candles, OHLC absolute prices)
- [Bar -15] 2026-08-25 15:30: O:159.100 H:159.250 L:159.080 C:159.200 (+100 pts, Bullish)
- [Bar -14] 2026-08-25 16:00: O:159.200 H:159.380 L:159.190 C:159.350 (+150 pts, Bullish)
- [Bar -13] 2026-08-25 16:30: O:159.350 H:159.500 L:159.320 C:159.480 (+130 pts, Bullish)
- [Bar -12] 2026-08-25 17:00: O:159.480 H:159.680 L:159.450 C:159.650 (+170 pts, Bullish)
- [Bar -11] 2026-08-25 17:30: O:159.650 H:159.850 L:159.620 C:159.780 (+130 pts, Bullish)
- [Bar -10] 2026-08-25 18:00: O:159.780 H:159.850 L:159.600 C:159.620 (-160 pts, Bearish Rejection)
- [Bar -9]  2026-08-25 18:30: O:159.620 H:159.650 L:159.480 C:159.500 (-120 pts, Bearish)
- [Bar -8]  2026-08-25 19:00: O:159.500 H:159.580 L:159.400 C:159.420 (-80 pts, Bearish)
- [Bar -7]  2026-08-25 19:30: O:159.420 H:159.450 L:159.300 C:159.330 (-90 pts, Bearish)
- [Bar -6]  2026-08-25 20:00: O:159.330 H:159.400 L:159.250 C:159.300 (-30 pts, Doji)
- [Bar -5]  2026-08-25 20:30: O:159.300 H:159.380 L:159.220 C:159.260 (-40 pts, Small Bearish)
- [Bar -4]  2026-08-25 21:00: O:159.260 H:159.350 L:159.200 C:159.320 (+60 pts, Small Bullish)
- [Bar -3]  2026-08-25 21:30: O:159.320 H:159.350 L:159.220 C:159.250 (-70 pts, Small Bearish)
- [Bar -2]  2026-08-25 22:00: O:159.250 H:159.400 L:159.220 C:159.310 (+60 pts, Upper Wick)
- [Bar -1]  2026-08-25 22:30: O:159.310 H:159.320 L:159.200 C:159.220 (-90 pts, Bearish close)

### LAST 12 M5 CANDLES (intra-period 1h, OHLC absolute prices)
- [M5 -12] 21:35: O:159.250 H:159.280 L:159.230 C:159.270 (+20 pts)
- [M5 -11] 21:40: O:159.270 H:159.300 L:159.250 C:159.260 (-10 pts)
- [M5 -10] 21:45: O:159.260 H:159.280 L:159.220 C:159.250 (-10 pts)
- [M5 -9]  21:50: O:159.250 H:159.270 L:159.230 C:159.240 (-10 pts)
- [M5 -8]  21:55: O:159.240 H:159.260 L:159.220 C:159.250 (+10 pts)
- [M5 -7]  22:00: O:159.250 H:159.380 L:159.250 C:159.350 (+100 pts)
- [M5 -6]  22:05: O:159.350 H:159.400 L:159.320 C:159.340 (-10 pts)
- [M5 -5]  22:10: O:159.340 H:159.350 L:159.280 C:159.300 (-40 pts)
- [M5 -4]  22:15: O:159.300 H:159.320 L:159.280 C:159.310 (+10 pts)
- [M5 -3]  22:20: O:159.310 H:159.320 L:159.240 C:159.250 (-60 pts)
- [M5 -2]  22:25: O:159.250 H:159.280 L:159.220 C:159.230 (-20 pts)
- [M5 -1]  22:30: O:159.230 H:159.240 L:159.200 C:159.220 (-10 pts)

### M5 MOMENTUM SUMMARY (computed locally)
- Net M5 Move (12 bars / 60m): -30 pts | Velocity Ratio: 0.35x
- Directional Bias: Bearish (8 Bearish vs 4 Bullish bars)

### PATTERN RESEARCH STATS (HISTORICAL BACKTEST DATA)
- USDJPY M30 Bearish Engulfing London Session: Win Rate 61.2% | EV +0.22R (n=142)
- USDJPY M30 S9 HTF Trend Continuation: Win Rate 64.0% | EV +0.28R (n=118)

### ECONOMIC CALENDAR & NEWS WINDOW GUARD
- 2026-08-26 19:30 WIB: USD Core Durable Goods Orders (High Impact) | Time to Event: 20h 30m
(Status: Normal market conditions, no active news blackout window)

### GLOBAL PORTFOLIO CONTEXT (All active bot positions across symbols)
Total Active Positions: 1 | Net Floating P/L: -$21.71 USD
- GBPCHF-ECNc: BUY 0.05 lot @ 1.09450 (Floating P/L: -$21.71 USD)
(Use this cross-asset awareness to detect conflicting currency exposures -- e.g. opposing CHF/EUR/GBP trades -- and take profit or cut exposure accordingly.)

### ACTIVE OPEN POSITIONS TO EVALUATE (DECISION REQUIRED)
(No open positions currently active on USDJPY-ECNc to evaluate.)
```

---

## 3. Contoh Respons JSON AI yang Dihasilkan

### Skenario A: Usulan Pending Order (Exhaustion / Rejection di Resistance)
```json
{
  "market_regime": "RANGE",
  "setup": "EXHAUSTION",
  "state": "REJECTION",
  "signal": "SELL",
  "confidence": 0.75,
  "rr_valid": true,
  "entry_type": "sell_limit",
  "entry_price": 159.650,
  "sl_points": 120,
  "tp_points": 350,
  "invalidation_price": 159.770,
  "target_price": 159.300,
  "reasoning": "Upper wick rejection at resistance with falling M5 momentum; 2.91 R:R back to value."
}
```

### Skenario B: HOLD (Terjebak di Tengah Range / Kompresi)
```json
{
  "market_regime": "RANGE",
  "setup": "NONE",
  "state": "COMPRESSION",
  "signal": "HOLD",
  "confidence": 0.0,
  "rr_valid": false,
  "entry_type": "market",
  "entry_price": null,
  "sl_points": null,
  "tp_points": null,
  "invalidation_price": null,
  "target_price": null,
  "reasoning": "Price trapped in mid-range compression with low ADX; lacks clearance or R:R >= 1.25."
}
```

### Skenario C: Keputusan AI Re-Evaluator (Saat Ada Tiket Terbuka)
```json
{
  "market_regime": "RANGE",
  "setup": "NONE",
  "state": "TESTING",
  "signal": "HOLD",
  "confidence": 0.0,
  "rr_valid": false,
  "entry_type": "market",
  "entry_price": null,
  "sl_points": null,
  "tp_points": null,
  "invalidation_price": null,
  "target_price": null,
  "reasoning": "Holding current position while testing 61.8% Fib support.",
  "position_actions": [
    {
      "ticket": 1222474268,
      "action": "HOLD",
      "reason": "Thesis intact, support holding"
    }
  ]
}
```
