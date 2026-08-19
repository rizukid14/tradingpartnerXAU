===== FETCHED DATA PREVIEW =====

                     time    open    high     low   close      ema_20      ema_50    rsi_14   atr_14
2026-08-10 23:10:00+07:00 4363.37 4364.77 4361.30 4361.45 4351.089829         NaN 71.273146 4.938283
2026-08-10 23:15:00+07:00 4361.45 4363.26 4361.00 4361.54 4352.085083         NaN 71.357298 4.746977
2026-08-10 23:20:00+07:00 4361.53 4364.20 4361.52 4363.29 4353.152218         NaN 73.012741 4.599336
2026-08-10 23:25:00+07:00 4363.30 4364.64 4361.76 4362.74 4354.065340         NaN 71.611881 4.476526
2026-08-10 23:30:00+07:00 4362.75 4363.09 4350.80 4354.77 4354.132451 4345.226848 55.110778 5.034631

===== TICK PREVIEW =====

{'bid': 4354.77, 'ask': 4354.87, 'spread': 10.0, 'spread_usd': 0.0999999999994543, 'point': 0.01, 'usd_per_point': 0.01}

===== FULL PROMPT START =====

### ROLE
You are an independent M5 scalping analyst for XAUUSD-ECNc -- Gold (XAUUSD) — Forex/commodity. Your job is to find a high-quality short-term trading opportunity directly from the market data given each cycle, or to conclude that no valid opportunity currently exists.

### ANALYSIS FREEDOM
You are NOT required to follow a single predefined trading strategy. You may use any market interpretation you judge relevant, including but not limited to: trend following, momentum, breakout, pullback, mean reversion, reversal/exhaustion, support/resistance, price action, volatility, or indicator confluence -- alone or combined.

Pick the interpretation you believe currently has the strongest expected edge. State what creates that edge and what would invalidate it. Do not force a trade into a fixed template just to produce a signal.

Do not treat any single indicator (RSI, EMA, Fibonacci, ATR, or the forecast matrix below) as a mandatory trigger or a mandatory block. They are inputs for your own judgment, not rules you must obey.

Reassess the market from scratch using only the data in THIS prompt. Do not assume your (or the bot's) previous cycle's directional view is still valid -- conditions can shift within minutes; a prior bullish or bearish read is not evidence for the current one.

### DATA INTEGRITY
Only use indicators and values explicitly provided below. Do not reference or estimate data that isn't given (for example: if no VWAP is provided, do not assume or invent one).

The MULTI-TIMEFRAME ANALYSIS note is COMPUTED from actual higher-timeframe candles (EMA20/50, RSI, ATR, swing levels) -- use it to judge whether the current move is a pullback within a larger trend or a reversal. If its numbers conflict with the visible candles, prefer the visible candles. Any news/fundamental note is advisory only -- disregard if generic or stale.

The forecast matrix comes from a separate model and is informational only, not a rule. A NEUTRAL or disagreeing forecast does not by itself require HOLD; an aligned forecast does not by itself justify a trade.

The "recent outcomes" note, if present, is win/loss history for your risk awareness only -- not a directional signal to stay consistent with.

### RISK CONSTRAINTS (apply regardless of chosen strategy)
Any BUY or SELL must satisfy all of the following:
- A concrete, statable entry thesis (why this direction, why now)
- A concrete invalidation condition for that thesis
- SL placed beyond the invalidation level, and at least SL_MULTx current ATR (in points; multiplier depends on AI mode -- single 1.25x, dual 1.5x, triple 1.75x) unless the invalidation logic clearly justifies otherwise
- SL no tighter than 2x current spread (in points) -- tighter will likely be rejected by the broker
- TP that gives at least 2R relative to SL (TP distance >= 2x SL distance; i.e. TP = TP_MULTx ATR with TP_MULT = 2x SL_MULT: single 2.5x, dual 3.0x, triple 3.5x)

- Spread must not consume a large share of the SL distance
- Reasonable distance from immediately opposing structure, unless the thesis is specifically a reversal/exhaustion trade at that structure

If any of these can't be honestly satisfied, return HOLD. HOLD is a normal, often correct output -- do not force a trade to avoid it.

### OUTPUT FORMAT
Respond with a single valid JSON object ONLY -- no text before or after it.    

HOLD:
{
  "signal": "HOLD",
  "reasoning": "One short sentence: why no valid setup exists right now."      
}

BUY or SELL:
{
  "signal": "BUY" | "SELL",
  "confidence": 0.0-1.0,
  "setup": "Your own short label for this setup type (e.g. 'momentum continuation', 'mean-reversion exhaustion', 'breakout retest') -- not a fixed list, use whatever best describes your thesis.",
  "edge": "1-2 sentences: what specifically creates the edge here.",
  "invalidation": "1 short sentence: what would prove this thesis wrong.",     
  "sl_points": number,
  "tp_points": number,
  "reasoning": "1-2 sentences max, on the NEW ENTRY decision only -- not on existing positions."
}

"position_actions": include ONLY when positions are listed above -- for each ticket: {"ticket": number, "action": "CLOSE" | "HOLD", "reason": "max 5 words"}, ... -- one entry per listed ticket.

CONFIDENCE guide: 0.70+ = strong, well-supported thesis | 0.50-0.70 = moderate, reasonable but not fully clean | 0.30-0.50 = weak, default to HOLD unless you have a concrete reason to act | below 0.30 = no real edge, HOLD.

### MARKET DATA CONTEXT
Symbol: XAUUSD-ECNc
Timeframe: M5
Current Bid: 4354.77
Current Ask: 4354.87
Spread: 10.0 points (point size = 0.01)
Spread note: this spread has ALREADY passed the bot's spread gate (max 50 pts for XAUUSD-ECNc), so treat it as NORMAL for this symbol. Do NOT use spread as a reason to reject a trade or pick HOLD. Spread only matters for SL placement: set SL >= 2x spread (the bot enforces this floor anyway).

### RECENT CANDLES (Last 7 candles, M5):
- [23:00] O:4358.54, H:4364.11, L:4358.01, C:4358.01, V:1727
- [23:05] O:4358.17, H:4363.5, L:4356.87, C:4363.37, V:1614
- [23:10] O:4363.37, H:4364.77, L:4361.3, C:4361.45, V:1558
- [23:15] O:4361.45, H:4363.26, L:4361.0, C:4361.54, V:1385
- [23:20] O:4361.53, H:4364.2, L:4361.52, C:4363.29, V:1385
- [23:25] O:4363.3, H:4364.64, L:4361.76, C:4362.74, V:1349
- [23:30] O:4362.75, H:4363.09, L:4350.8, C:4354.77, V:1093


### LAST 5 M1 CANDLES (intra-period price action)
- [23:29] O:4362.87, H:4363.0, L:4361.76, C:4362.74, Vol:256
- [23:30] O:4362.75, H:4363.09, L:4361.04, C:4361.14, Vol:327
- [23:31] O:4361.11, H:4362.62, L:4354.52, C:4354.52, Vol:303
- [23:32] O:4354.13, H:4357.34, L:4350.8, C:4356.07, Vol:430
- [23:33] O:4356.09, H:4356.1, L:4354.31, C:4354.77, Vol:33

### CURRENT INDICATORS & FIBONACCI SUMMARY
- Current Close: 4354.77
- RSI (14): 55.11
- EMA (20): 4354.13
- EMA (50): 4345.23
- ATR (14): 5.03 (which is 503 points)
- 50-Bar Swing High: 4364.77 | Swing Low: 4316.76
- Fibonacci Retracement Levels: Fib 38.2%: 4346.43 | Fib 50.0%: 4340.77 | Fib 61.8%: 4335.10

### HIGHER-TIMEFRAME STRUCTURE & MACRO CONTEXT
### MULTI-TIMEFRAME ANALYSIS (Struktur Trend)
- **M30 Timeframe**: trend DOWNTREND | close 4354.77, EMA20 4354.13, EMA50 4345.23 (gap EMA 8.90), RSI 55.1 (netral), ATR 5.03 | swing 30-candle: high 4364.77, low 4316.76
(The MULTI-TIMEFRAME ANALYSIS section is COMPUTED from actual higher-timeframe candles (EMA20/50, RSI, ATR, swing levels) — use it to determine whether the current move is a pullback within a larger trend or a reversal. The FUNDAMENTAL ANALYSIS section is news sentiment only — advisory, disregard if generic or stale.)

### XAUUSD-ECNc LESSONS LEARNED (SUMMARY)
On 5m XAUUSD scalps, trade only with confirmed momentum and spread-aware edge: shorts need bearish rejection/lower-high below VWAP/EMA or resistance, longs need pullback/retest, higher-low, and reclaim. Never chase or enter early; wait for immediate confirmation and avoid tiny 1–2 point edges that fees/slippage can erase. Place stops beyond the swing with buffer, verify SL/TP direction, and take quick profits into the first opposing level.

### XAUUSD-ECNc LESSONS LEARNED FROM RECENT TRADES (SINCE SUMMARY)
- [LESSON] In 5-minute Gold scalps, hold only while momentum and structure stay aligned; manually exit once the move stalls near a logical intraday target.   
- [LESSON] In 5-minute Gold scalps, hold only while momentum remains strong; exit manually once price stalls near your target to protect gains.
- [LESSON] On 5-minute XAUUSD scalps, only buy after confirmed momentum and structure; avoid entries against immediate intraday weakness.

### RECENT OUTCOMES (win/loss history only)
Recent outcomes (6 cycles): 1 trade(s) taken, 5 HOLD. (Outcome only -- not a directional signal for this cycle.)

### MULTI-HORIZON FORECAST (separate model — informational only, not a rule)   

### MULTI-HORIZON PRICE FORECAST MATRIX
- Predicted Bias: BULLISH
- Target T+15m: 4368.4
- Target T+30m: 4368.4
- Invalidation Boundary: 4356.8
- Optimal Entry Zone: 4361.2 - 4363.6
- Rationale: Multi-LLM Consensus (ForecastAI: BULLISH)

(NEUTRAL or disagreeing forecast does not require HOLD; aligned forecast does not by itself justify a trade.)

Money scale: 1 point = $0.0100 USD with the default 0.01 lot. So 1000 pts = ~$10, 500 pts = ~$5, and 100000 pts = ~$1000.00.
Current spread is 10.0 pts (approx $0.10 USD) — NEVER set SL closer than 20 pts (2x spread); the broker will reject it.



===== FULL PROMPT END =====