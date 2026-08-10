===== FETCHED DATA PREVIEW =====

                     time    open    high     low   close      ema_20      ema_50    rsi_14   atr_14
2026-08-10 17:25:00+07:00 4343.21 4343.75 4341.89 4343.65 4344.490352         NaN 43.530963 2.928009
2026-08-10 17:30:00+07:00 4343.67 4344.15 4340.49 4342.08 4344.260795         NaN 39.616704 2.980294
2026-08-10 17:35:00+07:00 4342.10 4342.32 4338.40 4339.68 4343.824529         NaN 34.508445 3.047416
2026-08-10 17:40:00+07:00 4339.69 4340.15 4337.85 4337.94 4343.264097         NaN 31.352103 2.994029
2026-08-10 17:45:00+07:00 4337.94 4339.48 4337.62 4338.34 4342.795136 4347.165211 32.872149 2.913027

===== TICK PREVIEW =====

{'bid': 4338.27, 'ask': 4338.37, 'spread': 10.0, 'spread_usd': 0.0999999999994543, 'point': 0.01, 'usd_per_point': 0.01}
[LLM PROMPT PREVIEW] symbol=XAUUSD-ECNc tf=M5 bid=4338.27 ask=4338.37 spread=10.0pt point=0.01
[LLM PROMPT PREVIEW] close=4338.34 rsi=32.87 ema20=4342.80 ema50=4347.17 atr=2.91 atr_points=291
[LLM PROMPT PREVIEW] fib382=4352.71 fib500=4349.82 fib618=4346.94 swing_high=4362.03 swing_low=4337.62
[LLM PROMPT PREVIEW] recent_candles=7 micro_candles=yes forecast=yes positions=no

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

Any "macro/HTF context" note is background only, not a ground-truth signal -- if it reads as generic, stale, or inconsistent with the actual candles/indicators shown, disregard it in favor of the concrete data.

The forecast matrix comes from a separate model and is informational only, not a rule. A NEUTRAL or disagreeing forecast does not by itself require HOLD; an aligned forecast does not by itself justify a trade.

The "recent outcomes" note, if present, is win/loss history for your risk awareness only -- not a directional signal to stay consistent with.

### RISK CONSTRAINTS (apply regardless of chosen strategy)
Any BUY or SELL must satisfy all of the following:
- A concrete, statable entry thesis (why this direction, why now)
- A concrete invalidation condition for that thesis
- SL placed beyond the invalidation level, and roughly within 1.5-2x current ATR (in points) unless the invalidation logic clearly justifies otherwise
- SL no tighter than 2x current spread (in points) -- tighter will likely be rejected by the broker
- TP that gives at least 1.5R relative to SL (TP distance >= 1.5x SL distance)
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
Current Bid: 4338.27
Current Ask: 4338.37
Spread: 10.0 points (point size = 0.01)

### RECENT CANDLES (Last 7 candles, M5):
- [17:15] O:4340.76, H:4341.61, L:4339.37, C:4341.45, V:1003
- [17:20] O:4341.48, H:4344.16, L:4341.11, C:4343.2, V:1025
- [17:25] O:4343.21, H:4343.75, L:4341.89, C:4343.65, V:793
- [17:30] O:4343.67, H:4344.15, L:4340.49, C:4342.08, V:992
- [17:35] O:4342.1, H:4342.32, L:4338.4, C:4339.68, V:1052
- [17:40] O:4339.69, H:4340.15, L:4337.85, C:4337.94, V:931
- [17:45] O:4337.94, H:4339.48, L:4337.62, C:4338.34, V:675


### LAST 5 M1 CANDLES (intra-period price action)
- [17:44] O:4337.99, H:4338.55, L:4337.85, C:4337.94, Vol:186
- [17:45] O:4337.94, H:4338.54, L:4337.84, C:4337.93, Vol:213
- [17:46] O:4337.93, H:4339.18, L:4337.62, C:4339.11, Vol:201
- [17:47] O:4339.11, H:4339.48, L:4338.22, C:4338.24, Vol:174
- [17:48] O:4338.21, H:4338.45, L:4338.02, C:4338.27, Vol:88

### CURRENT INDICATORS & FIBONACCI SUMMARY
- Current Close: 4338.34
- RSI (14): 32.87
- EMA (20): 4342.80
- EMA (50): 4347.17
- ATR (14): 2.91 (which is 291 points)
- 50-Bar Swing High: 4362.03 | Swing Low: 4337.62
- Fibonacci Retracement Levels: Fib 38.2%: 4352.71 | Fib 50.0%: 4349.82 | Fib 61.8%: 4346.94

### HIGHER-LEVEL MACRO & TIMEFRAME CONTEXT (background only)
Bullish macro context sample.
(Advisory only — if this reads generic/stale or conflicts with the actual candles/indicators, disregard it in favor of the concrete data.)

### XAUUSD-ECNc LESSONS LEARNED (SUMMARY)
On 5m XAUUSD scalps, trade only with confirmed momentum: shorts need a lower-high/bearish rejection below VWAP/EMA or resistance, and longs need a pullback/retest, higher-low, and reclaim of EMA/resistance. Never chase into strong momentum or nearby resistance/support. Place stops beyond the relevant swing high/low with spread buffer, use preplanned invalidation, and take profits quickly into the first opposing level while staying patient and selective.

### RECENT OUTCOMES (win/loss history only)
Recent outcomes (6 cycles): 0 trade(s) taken, 6 HOLD. (Outcome only -- not a directional signal for this cycle.)     

### MULTI-HORIZON FORECAST (separate model — informational only, not a rule)

### MULTI-HORIZON PRICE FORECAST MATRIX
- Predicted Bias: NEUTRAL
- Target T+5m (next candle): 4341.68
- Target T+15m: 4342.07
- Target T+60m: 4349.47
- Invalidation Boundary: 4334.93
- Optimal Entry Zone: 4338.67 - 4341.5
- Rationale: Multi-LLM Consensus (Gemini: NEUTRAL, DeepSeek: NEUTRAL, OpenAI: NEUTRAL)

(NEUTRAL or disagreeing forecast does not require HOLD; aligned forecast does not by itself justify a trade.)        

Money scale: 1 point = $0.0100 USD with the default 0.01 lot. So 1000 pts = ~$10, 500 pts = ~$5, and 100000 pts = ~$1000.00.
Current spread is 10.0 pts (approx $0.10 USD) — NEVER set SL closer than 20 pts (2x spread); the broker will reject it.



===== FULL PROMPT END =====