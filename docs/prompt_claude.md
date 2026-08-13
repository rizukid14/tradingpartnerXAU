"""
Multi-LLM trading prompt template -- "we set guardrails, the LLM sets strategy".

Replaces the old rule-heavy STRATEGY / DECISION ORDER / COUNTER-TREND /
FORECAST ALIGNMENT sections with:
  - a free-form analysis mandate (no predefined trend/pullback/reversal tree
    baked into the prompt -- each of the 3 models picks its own approach)
  - a small, non-negotiable set of RISK constraints (execution safety only)
  - a fixed OUTPUT schema that now includes "setup" and "edge", so you can
    later analyze which setup label each model's calls actually win with

Two fixes for bugs found in the previous prompt are baked into the static
system prompt itself, as a safety net:

  1. The old "macro context" line was sometimes a static/stale string
     (e.g. "Bullish macro context sample") that could anchor the model to
     a wrong bias for hours. That dummy string is gone; macro context is now
     generated from real MT5 data (MTF analysis EMA/RSI/ATR/swing), and the
     model is told the MULTI-TIMEFRAME ANALYSIS section is computed from
     actual HTF candles while news/fundamental notes are advisory only.
     (Historical safety-net note: the prompt-level instruction to disregard
     generic/stale notes remains as a fallback, not a substitute for real data.)

  2. The old "recent decisions" block echoed past directional calls back
     into every new prompt, which can anchor the model to its own prior
     narrative instead of reading the market fresh each cycle.
     summarize_recent_outcomes() strips that down to win/loss counts only.

Usage:
    system_prompt = build_system_prompt("XAUUSD-ECNc", "M5", "Gold (XAUUSD), Forex/commodity")
    # build once per bot instance, reuse unchanged every cycle -- this is
    # the part that benefits from provider-side prompt/context caching

    dynamic_prompt = build_dynamic_prompt(...)   # rebuild every cycle
    full_prompt = system_prompt + "\n\n" + dynamic_prompt
"""

from typing import Optional, List, Dict, Any


_SYSTEM_PROMPT_TEMPLATE = """### ROLE
You are an independent {{TIMEFRAME}} scalping analyst for {{SYMBOL}} -- {{ASSET_DESC}}. Your job is to find a high-quality short-term trading opportunity directly from the market data given each cycle, or to conclude that no valid opportunity currently exists.

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
- SL placed beyond the invalidation level, and at least SL_MULTx current ATR (in points; multiplier depends on the AI mode listed in the prompt -- single 1.25x, dual 1.5x, triple 1.75x) unless the invalidation logic clearly justifies otherwise
- SL no tighter than 2x current spread (in points) -- tighter will likely be rejected by the broker
- TP that gives at least 2R relative to SL (TP distance >= 2x SL distance; i.e. TP = TP_MULTx ATR with TP_MULT = 2x SL_MULT: single 2.5x, dual 3.0x, triple 3.5x)
- Spread must not consume a large share of the SL distance
- Reasonable distance from immediately opposing structure, unless the thesis is specifically a reversal/exhaustion trade at that structure

If any of these can't be honestly satisfied, return HOLD. HOLD is a normal, often correct output -- do not force a trade to avoid it.

{{POINTS_EXPLANATION}}

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
  "invalidation_price": number, // The exact price level where this trade setup becomes invalid (structure broken, e.g. 4422.50). MUST correspond to price structural data provided (swing high/low, Fibonacci retracements, PDH/PDL, EMA). Do NOT make up random points.
  "target_price": number, // The exact price level representing your profit target (e.g. 4426.20). MUST correspond to price structural data provided.
  "sl_points": number, // (Fallback) Stop Loss distance in broker POINTS (integer). Read the CRITICAL UNIT DEFINITION below!
  "tp_points": number, // (Fallback) Take Profit distance in broker POINTS (integer). Read the CRITICAL UNIT DEFINITION below!
  "reasoning": "1-2 sentences max, on the NEW ENTRY decision only -- not on existing positions."
}

"position_actions": include ONLY when positions are listed above -- for each ticket: {"ticket": number, "action": "CLOSE" | "HOLD", "reason": "max 5 words"}, ... -- one entry per listed ticket.

CONFIDENCE guide: 0.70+ = strong, well-supported thesis | 0.50-0.70 = moderate, reasonable but not fully clean | 0.30-0.50 = weak, default to HOLD unless you have a concrete reason to act | below 0.30 = no real edge, HOLD."""


def _build_points_explanation(symbol: str, point_size: float) -> str:
    """
    Generate a highly explicit explanation of broker points vs pips/price-units
    to avoid LLMs mixing them up (e.g. OpenAI/DeepSeek outputting pips instead of points).
    """
    is_btc = symbol.startswith("BTC")  # simple check for documentation script
    pt_str = f"{point_size:.4f}" if point_size else "0.01"
    
    if is_btc:
        return (
            f"### CRITICAL UNIT DEFINITION: POINTS vs USD MOVEMENT\n"
            f"You MUST calculate and return Stop Loss and Take Profit in broker **POINTS** (integer), NOT USD price, NOT percentages.\n"
            f"For {symbol} (with broker point size = {pt_str}):\n"
            f"- 1 point = ${pt_str} USD price change.\n"
            f"- 100 points = $1.00 USD price change (e.g., BTC moving from 60000.00 to 60001.00)\n"
            f"- 10,000 points = $100.00 USD price change (e.g., BTC moving from 60000.00 to 60100.00)\n"
            f"- 50,000 points = $500.00 USD price change (e.g., BTC moving from 60000.00 to 60500.00)\n"
            f"- Typical Stop Loss distance is 20000 to 60000 points ($200.00 to $600.00 USD price change).\n\n"
            f"CRITICAL WARNING:\n"
            f"Double-check your numbers. If you want a Stop Loss of $400 USD of BTC price movement, you MUST return 40000. "
            f"If you return 400, it sets a Stop Loss of just 400 points ($4.00 USD price change), which is inside the spread and will cause an instant loss or broker rejection!"
        )
    else:
        # Gold / Forex
        pt_str = f"{point_size:.2f}" if point_size else "0.01"
        return (
            f"### CRITICAL UNIT DEFINITION: POINTS vs PIPS vs USD MOVEMENT\n"
            f"You MUST calculate and return Stop Loss and Take Profit in broker **POINTS** (integer), NOT pips, NOT USD price.\n"
            f"For {symbol} (with broker point size = {pt_str}):\n"
            f"- 1 point = ${pt_str} USD price change.\n"
            f"- 10 points = 1 pip = $0.10 USD price change.\n"
            f"- 100 points = 10 pips = $1.00 USD price change (e.g., Gold moving from 2400.00 to 2401.00)\n"
            f"- Typical Stop Loss distance is 100 to 350 points (10 to 35 pips / $1.00 to $3.50 USD gold movement).\n\n"
            f"CRITICAL WARNING:\n"
            f"Double-check your numbers. If you want a Stop Loss of 20 pips (which is $2.00 USD of price movement), you MUST return 200. "
            f"If you return 20, it sets a Stop Loss of just 20 points (2 pips / $0.20 USD price change), which is inside the spread and will cause an instant loss or broker rejection!"
        )


def build_system_prompt(symbol: str, timeframe: str, asset_description: str, point_size: float = 0.01) -> str:
    """
    Static per-bot 'constitution'. Build once per bot instance (e.g. once
    for XAU M5, once for BTC H1) and reuse unchanged across cycles -- this
    is the part that benefits from provider-side prompt/context caching,
    since only the dynamic market data below changes every call.
    """
    points_explanation = _build_points_explanation(symbol, point_size)
    return (
        _SYSTEM_PROMPT_TEMPLATE
        .replace("{{SYMBOL}}", symbol)
        .replace("{{TIMEFRAME}}", timeframe)
        .replace("{{ASSET_DESC}}", asset_description)
        .replace("{{POINTS_EXPLANATION}}", points_explanation)
    )


def format_candles(candles: List[Dict[str, Any]]) -> str:
    """candles: list of dicts with keys time, open, high, low, close, volume."""
    lines = []
    for c in candles:
        lines.append(
            f"- [{c['time']}] O:{c['open']}, H:{c['high']}, L:{c['low']}, "
            f"C:{c['close']}, V:{c['volume']}"
        )
    return "\n".join(lines)


def format_positions(positions: Optional[List[Dict[str, Any]]]) -> str:
    if not positions:
        return ""
    lines = ["Open positions on this symbol:"]
    for p in positions:
        lines.append(
            f"- Ticket {p['ticket']}: {p['direction']} {p['volume']} lot @ "
            f"{p['entry_price']}, P/L: {p['pnl']}, SL: {p.get('sl', 'none')}, "
            f"TP: {p.get('tp', 'none')}"
        )
    return "\n".join(lines)


def summarize_recent_outcomes(decisions: List[Dict[str, Any]], n: int = 6) -> str:
    """
    Strip directional narrative out of decision history, keep outcome
    stats only -- so the current cycle isn't anchored to the previous
    cycle's directional story (this was likely a contributor to the bot
    holding a stale bullish read for hours during a correction).

    decisions: list of dicts, most recent last, e.g.
        {"signal": "BUY", "result": "TP" | "SL" | "OPEN" | "N/A"}
    """
    recent = decisions[-n:]
    if not recent:
        return "No recent decision history for this symbol."

    hold_count = sum(1 for d in recent if d["signal"] == "HOLD")
    tp_count = sum(1 for d in recent if d.get("result") == "TP")
    sl_count = sum(1 for d in recent if d.get("result") == "SL")
    trade_count = len(recent) - hold_count

    return (
        f"Recent outcomes ({len(recent)} cycles): {trade_count} trade(s) taken "
        f"({tp_count} hit TP, {sl_count} hit SL), {hold_count} HOLD. "
        f"(Outcome only -- not a directional signal for this cycle.)"
    )


def build_dynamic_prompt(
    symbol: str,
    timeframe: str,
    bid: float,
    ask: float,
    spread_points: float,
    point_size: float,
    usd_per_point: float,
    recent_candles: List[Dict[str, Any]],
    m1_candles: List[Dict[str, Any]],
    ema20: float,
    ema50: float,
    rsi: float,
    atr: float,
    atr_points: float,
    swing_high: float,
    swing_low: float,
    fib_382: float,
    fib_500: float,
    fib_618: float,
    macro_context: str,
    forecast: Dict[str, Any],
    recent_decisions: List[Dict[str, Any]],
    positions: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Rebuild every cycle -- this is the part that actually changes."""
    spread_usd = spread_points * usd_per_point

    block = f"""### MARKET DATA -- {symbol} ({timeframe})
Current Bid: {bid} | Ask: {ask} | Spread: {spread_points} pts (point size = {point_size})
Money scale: 1 point = ${usd_per_point:.4f}; current spread = ${spread_usd:.2f}.

Recent {len(recent_candles)} candles ({timeframe}):
{format_candles(recent_candles)}

Last {len(m1_candles)} M1 candles (intra-period detail):
{format_candles(m1_candles)}

Indicators (raw values -- interpret freely, per Analysis Freedom above):
- EMA20: {ema20} | EMA50: {ema50}
- RSI(14): {rsi}
- ATR(14): {atr} ({atr_points} points)
- 50-bar Swing High: {swing_high} | Swing Low: {swing_low}
- Fibonacci retracement levels: 38.2% {fib_382} | 50.0% {fib_500} | 61.8% {fib_618}

Higher-timeframe/macro note (advisory only -- see Data Integrity above): {macro_context}

Multi-horizon forecast (separate model, informational only -- not a rule):
- Bias: {forecast['bias']} | T+5m: {forecast['t5']} | T+15m: {forecast['t15']} | T+60m: {forecast['t60']}
- Invalidation boundary: {forecast['invalidation']} | Optimal entry zone: {forecast['entry_low']}-{forecast['entry_high']}
- Rationale: {forecast['rationale']}

{summarize_recent_outcomes(recent_decisions)}"""

    positions_block = format_positions(positions)
    if positions_block:
        block += f"\n\n{positions_block}"

    return block


if __name__ == "__main__":
    # sanity check -- combine static + dynamic exactly like a real cycle would
    system_prompt = build_system_prompt("XAUUSD-ECNc", "M5", "Gold (XAUUSD), Forex/commodity")

    dynamic_prompt = build_dynamic_prompt(
        symbol="XAUUSD-ECNc",
        timeframe="M5",
        bid=4340.3,
        ask=4340.4,
        spread_points=10.0,
        point_size=0.01,
        usd_per_point=0.01,
        recent_candles=[
            {"time": "17:05", "open": 4340.50, "high": 4341.52, "low": 4339.94, "close": 4340.40, "volume": 992},
            {"time": "17:10", "open": 4340.37, "high": 4340.73, "low": 4339.59, "close": 4340.30, "volume": 644},
        ],
        m1_candles=[
            {"time": "17:12", "open": 4340.05, "high": 4340.73, "low": 4339.59, "close": 4340.68, "volume": 179},
            {"time": "17:13", "open": 4340.64, "high": 4340.68, "low": 4340.23, "close": 4340.30, "volume": 80},
        ],
        ema20=4344.91,
        ema50=4347.63,
        rsi=33.30,
        atr=3.03,
        atr_points=302,
        swing_high=4362.03,
        swing_low=4339.25,
        fib_382=4353.33,
        fib_500=4350.64,
        fib_618=4347.95,
        macro_context=(
            "### MULTI-TIMEFRAME ANALYSIS (Struktur Trend)\n"
            "- **M30 Timeframe**: trend DOWNTREND | close 4354.77, EMA20 4354.13, "
            "EMA50 4345.23 (gap EMA 8.90), RSI 55.1 (netral), ATR 5.03 | swing "
            "30-candle: high 4364.77, low 4316.76"
        ),
        forecast={
            "bias": "NEUTRAL", "t5": 4340.83, "t15": 4340.47, "t60": 4348.47,
            "invalidation": 4330.87, "entry_low": 4338.57, "entry_high": 4341.5,
            "rationale": "Multi-LLM Consensus (Gemini: NEUTRAL, DeepSeek: NEUTRAL, OpenAI: NEUTRAL)",
        },
        recent_decisions=[
            {"signal": "HOLD"}, {"signal": "HOLD"}, {"signal": "HOLD"},
            {"signal": "HOLD"}, {"signal": "SELL", "result": "SL"}, {"signal": "HOLD"},
        ],
        positions=None,
    )

    print(system_prompt + "\n\n" + dynamic_prompt)
    print("\n\n--- OK: template rendered without errors ---")