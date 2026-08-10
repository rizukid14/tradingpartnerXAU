import json
import re
import time
import concurrent.futures
from openai import OpenAI
from google import genai
import config

# Initialize clients if keys are present
openai_client = None
if config.OPENAI_API_KEY:
    openai_client = OpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_API_BASE
    )

# DeepSeek is OpenAI-compatible — same SDK, different base URL. Used when
# CLAUDE_MODEL starts with "deepseek/" (cheap default; switch back to Claude
# by setting CLAUDE_MODEL to "claude-...").
deepseek_client = None
if config.DEEPSEEK_API_KEY:
    try:
        deepseek_client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_API_BASE
        )
    except Exception as e:
        print(f"[LLM WARNING] Gagal init DeepSeek client: {e}")

claude_client = None
if config.ANTHROPIC_API_KEY:
    try:
        from anthropic import Anthropic
        claude_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    except Exception as e:
        print(f"[LLM WARNING] Gagal init Anthropic client: {e}")

gemini_client = None
if config.GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)


def asset_desc(symbol):
    """Human-readable asset description for prompts (Gold vs Bitcoin)."""
    if config.is_crypto(symbol):
        return "Bitcoin (BTCUSD) — crypto, trades 24/7 including weekends"
    return "Gold (XAUUSD) — Forex/commodity"


def claude_slot_label():
    """Display label for the 'Claude slot' model. Shows DeepSeek when the
    configured model is deepseek/..., otherwise Claude."""
    return "DeepSeek" if config.CLAUDE_MODEL.startswith("deepseek/") else "Claude"


def query_primary_model(prompt, search_grounding=False):
    """
    Queries a single model for background analysis (post-mortem, MTF, lessons
    summary). Primary = OpenAI gpt-5.4-mini (free tier), then Gemini, then
    Claude. Search grounding (Google Search) is only supported on Gemini,
    so it forces the Gemini branch when enabled.
    """
    # 1. Try OpenAI (primary — gpt-5.4-mini, free tier)
    if openai_client and config.OPENAI_API_KEY:
        try:
            response = openai_client.chat.completions.create(
                model=config.PRIMARY_ANALYSIS_MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional financial trading assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                timeout=30
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[PRIMARY MODEL ERROR - OPENAI] {e}")

    # 2. Try Gemini (fallback; required for search grounding)
    if gemini_client and config.GEMINI_API_KEY:
        try:
            from google.genai import types

            gen_config = None
            if search_grounding:
                gen_config = types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )

            response = gemini_client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=gen_config
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"[PRIMARY MODEL ERROR - GEMINI] {e}")

    # 3. Try Claude slot (Anthropic, or DeepSeek if CLAUDE_MODEL is deepseek/)
    if config.CLAUDE_MODEL.startswith("deepseek/"):
        if deepseek_client and config.DEEPSEEK_API_KEY:
            try:
                res = _execute_deepseek_single(config.CLAUDE_MODEL, prompt, 30)
                if isinstance(res, str):
                    return res.strip()
                return json.dumps(res)
            except Exception as e:
                print(f"[PRIMARY MODEL ERROR - DEEPSEEK] {e}")
    elif claude_client and config.ANTHROPIC_API_KEY:
        try:
            response = claude_client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=1000,
                system=[
                    {
                        "type": "text",
                        "text": "You are a professional financial trading assistant.",
                        "cache_control": {"type": "ephemeral"}
                    }
                ],
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            }
                        ]
                    }
                ],
                extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
                timeout=30
            )
            return "".join(b.text for b in response.content if b.type == "text").strip()
        except Exception as e:
            try:
                response = claude_client.messages.create(
                    model=config.CLAUDE_MODEL,
                    max_tokens=1000,
                    system="You are a professional financial trading assistant.",
                    messages=[{"role": "user", "content": prompt}],
                    timeout=30
                )
                return "".join(b.text for b in response.content if b.type == "text").strip()
            except Exception as e2:
                print(f"[PRIMARY MODEL ERROR - CLAUDE] {e2}")

    return None


def analyze_timeframe(symbol, timeframe_name, df):
    """
    Queries the primary model to analyze structural bias, trend, 
    and support/resistance for a higher timeframe.
    """
    # Take the last 10 candles for context
    recent_candles = df.tail(10).to_dict(orient="records")
    candles_str = ""
    for c in recent_candles:
        candles_str += f"- Time: {c['time']}, O: {c['open']}, H: {c['high']}, L: {c['low']}, C: {c['close']}, Vol: {c['tick_volume']}, RSI: {c['rsi_14']:.2f}, EMA20: {c['ema_20']:.2f}, EMA50: {c['ema_50']:.2f}\n"

    latest = df.iloc[-1]

    execution_style = "30-minute intraday (M30) swing" if config.is_crypto(symbol) else "5-minute (M5) scalping"
    
    prompt = f"""
You are an expert financial market analyst.
Analyze the following market data for {symbol} on timeframe {timeframe_name} to identify the structural bias and key levels.

### MARKET DATA CONTEXT
Symbol: {symbol}
Timeframe: {timeframe_name}

### RECENT CANDLES (Last 10 candles):
{candles_str}

### CURRENT INDICATORS SUMMARY
- Close: {latest['close']}
- RSI (14): {latest['rsi_14']:.2f}
- EMA (20): {latest['ema_20']:.2f}
- EMA (50): {latest['ema_50']:.2f}
- ATR (14): {latest['atr_14']:.2f}

Provide a concise structural market analysis. Include:
1. Overall Trend (Bullish / Bearish / Range) and structural strength.
2. Key Support and Resistance zones.
3. Relevant price action patterns or signals.

Your response must be extremely brief (maximum 2-3 sentences) as it will be used as background context for a {execution_style} execution model.
"""
    return query_primary_model(prompt, search_grounding=False)


def analyze_fundamentals(symbol):
    """
    Queries Gemini using Google Search Grounding to summarize the latest
    macroeconomic SENTIMENT affecting the asset (news, outlook, positioning).
    Event SCHEDULING is handled deterministically by economic_calendar.py —
    search grounding is only a qualitative complement, never the schedule source.
    """
    execution_style = "30-minute intraday (M30) swing" if config.is_crypto(symbol) else "5-minute (M5) scalping"
    prompt = f"""
What is the latest macroeconomic news and market sentiment affecting {symbol} ({asset_desc(symbol)}) prices right now?
Summarize the main themes, current market sentiment, and any notable macro drivers (central bank policy expectations, geopolitical risk, dollar/yield moves, commodity flows, or crypto-specific factors like ETF flows or regulatory news).

Your response must be extremely brief (maximum 3-4 sentences) as it will be used as background context for a {execution_style} execution model. Focus on DIRECTIONAL macro bias, not event schedules.
"""
    # Force search grounding tool
    return query_primary_model(prompt, search_grounding=True)


def prepare_prompt(symbol, df, current_tick, macro_context=None, open_positions=None):
    """
    Constructs a rich prompt for LLM models containing price action,
    multi-timeframe technical indicators, MTF macro analysis, and active open positions.
    """

    # Create recent candles string (last 7 candles)
    recent_candles = df.tail(7)
    candles_str = ""
    for idx, row in recent_candles.iterrows():
        time_str = row['time'].strftime('%H:%M') if hasattr(row['time'], 'strftime') else str(row['time'])
        candles_str += f"- [{time_str}] O:{row['open']}, H:{row['high']}, L:{row['low']}, C:{row['close']}, V:{row['tick_volume']}\n"

    # Micro price action: last 5 M30 candles (BTC M30) or last 5 M1 candles (XAU M5)
    micro_candles_str = ""
    try:
        from src.core import mt5_connector
        is_crypto_asset = config.is_crypto(symbol)
        micro_tf = mt5_connector.mt5.TIMEFRAME_M5 if is_crypto_asset else mt5_connector.mt5.TIMEFRAME_M1
        micro_tf_name = "M5" if is_crypto_asset else "M1"
        # Fetch 20 candles so ATR(14) indicator in get_market_data doesn't raise IndexError
        micro_df = mt5_connector.get_market_data(symbol, micro_tf, num_candles=20)
        if micro_df is not None and len(micro_df) > 0:
            micro_tail = micro_df.tail(5)
            micro_lines = []
            for _, r in micro_tail.iterrows():
                t_s = r['time'].strftime('%H:%M') if hasattr(r['time'], 'strftime') else str(r['time'])
                micro_lines.append(f"- [{t_s}] O:{r['open']}, H:{r['high']}, L:{r['low']}, C:{r['close']}, Vol:{r['tick_volume']}")
            micro_candles_str = f"\n### LAST 5 {micro_tf_name} CANDLES (intra-period price action)\n" + "\n".join(micro_lines) + "\n"
    except Exception as e:
        pass

    latest = df.iloc[-1]
    point_size = current_tick.get("point", 0.01)
    atr_points = int(latest["atr_14"] / point_size) if point_size > 0 else 0

    # Market Randomness & Micro Fat-Tail Analysis (Hurst, Kurtosis, Skewness)
    randomness_str = ""
    if getattr(config, "QUANT_ANALYSIS_ENABLED", False):
        try:
            from src.analytics import market_randomness
            rand_info = market_randomness.analyze_market_randomness(df, symbol=symbol)
            ft = rand_info.get('fat_tail', {})
            tf_micro = ft.get('tf', 'M5' if config.is_crypto(symbol) else 'M1')
            randomness_str = (
                f"- Hurst Exponent (H): {rand_info['hurst']:.2f} ({rand_info['regime']})\n"
                f"- Excess Kurtosis ({tf_micro} Fat Tails): {ft.get('kurtosis', 0.0):+.2f} ({ft.get('label', 'NORMAL')}) | Skewness ({tf_micro}): {ft.get('skewness', 0.0):+.2f}\n"
            )
        except Exception:
            pass

    quant_prob_str = ""
    if getattr(config, "MONTE_CARLO_ENABLED", False):
        try:
            from src.analytics import quant_probability
            tf_mins = 30 if config.is_crypto(symbol) else 5
            q_res = quant_probability.calculate_quant_probabilities(df, timeframe_minutes=tf_mins)
            quant_prob_str = (
                f"- Quant Monte Carlo Probabilities (1,000 paths): "
                f"UP: {q_res['prob_up_pct']}% (Target: ${q_res['expected_target_up']}) | "
                f"DOWN: {q_res['prob_down_pct']}% (Target: ${q_res['expected_target_down']}) | "
                f"Est. Time: {q_res['estimated_time_str']}\n"
            )
        except Exception:
            pass

    # For crypto (BTC) the df is already M30 (config.get_timeframe) so the ATR
    # reflects real 30-minute volatility. XAU df is M5 and its ATR matches the
    # scalping scale. No flooring here — the LLM picks SL/TP from this range
    # and consensus only enforces a 2x-spread safety floor.

    # ATR-based range (pure, no default floor):
    min_sl = int(atr_points * 1.5)
    max_sl = int(atr_points * 2.0)
    min_tp = int(min_sl * 1.5)
    max_tp = int(max_sl * 2.0)

    # USD value of 1 point for the default bot lot — tells the LLM the real
    # money scale of the SL/TP distances it proposes (critical for BTC, where
    # 1 pt = $0.0001 and the LLM otherwise proposes absurdly tight stops).
    usd_per_point = current_tick.get("usd_per_point", 0.0)
    if usd_per_point > 0:
        pts_per_usd = 1.0 / usd_per_point
        usd_context = (
            f"Money scale: 1 point = ${usd_per_point:.4f} USD with the default "
            f"{config.lot_size_for(symbol)} lot. So {int(pts_per_usd * 10)} pts = ~$10, "
            f"{int(pts_per_usd * 5)} pts = ~$5, and 100000 pts = ~${100000 * usd_per_point:.2f}.\n"
            f"Current spread is {current_tick.get('spread', '?')} pts "
            f"(≈ ${current_tick.get('spread_usd', 0.0):.2f} USD) — NEVER set SL closer than "
            f"{int(current_tick.get('spread', 0) * 2)} pts (2x spread); the broker will reject it.\n"
        )
    else:
        usd_context = ""

    macro_str = ""
    if macro_context:
        macro_str = f"\n### HIGHER-LEVEL MACRO & TIMEFRAME CONTEXT\n{macro_context}\n"

    lessons_str = ""
    if getattr(config, "MEMORY_CONTEXT_ENABLED", True):
        try:
            from src.analytics import trade_evaluator
            lessons_str = trade_evaluator.evaluator.get_lessons_context()
        except Exception:
            pass

    decision_memory_str = ""
    if getattr(config, "MEMORY_CONTEXT_ENABLED", True):
        try:
            from src.analytics import decision_memory
            decision_memory_str = decision_memory.memory.get_context(symbol)
        except Exception:
            pass

    forecast_str = ""
    if getattr(config, "FORECAST_ENABLED", True) and getattr(config, "MEMORY_CONTEXT_ENABLED", True):
        try:
            from src.analytics import forecast_engine
            forecast_str = forecast_engine.forecaster.get_forecast_context()
        except Exception:
            pass

    calendar_str = ""
    try:
        from src.analytics import economic_calendar
        calendar_str = economic_calendar.calendar.get_context()
    except Exception:
        pass

    positions_str = ""
    if open_positions and len(open_positions) > 0:
        pos_lines = []
        now_ts = time.time()
        for pos in open_positions:
            p_ticket = pos.get('ticket')
            p_type = pos.get('type')
            p_vol = pos.get('volume')
            p_open = pos.get('price_open')
            p_sl = pos.get('sl', 0.0)
            p_tp = pos.get('tp', 0.0)
            p_swap = pos.get('swap', 0.0)
            p_profit = pos.get('profit', 0.0)
            p_time = pos.get('time')

            time_str = ""
            if p_time and p_time > 0:
                try:
                    from src.core import mt5_connector
                    wib_dt = mt5_connector.server_to_wib(p_time)
                    hours_held = max(0.0, (now_ts - wib_dt.timestamp()) / 3600.0)
                    time_str = f" | Opened: {wib_dt.strftime('%Y-%m-%d %H:%M')} WIB (held for {hours_held:.1f}h)"
                except Exception:
                    pass

            swap_str = f" | Swap: ${p_swap:.2f} USD" if p_swap != 0.0 else ""
            sl_tp_str = f" (SL: {p_sl}, TP: {p_tp})" if (p_sl or p_tp) else ""
            pos_lines.append(f"- Ticket #{p_ticket}: {p_type} {p_vol} lot @ {p_open}{sl_tp_str}{time_str}{swap_str} | Floating P/L: ${p_profit:.2f} USD")
        positions_str = (
            "\n### ACTIVE OPEN POSITIONS TO EVALUATE (DECISION REQUIRED)\n" +
            "\n".join(pos_lines) + "\n" +
            "For EACH open position above, make an explicit decision:\n" +
            "- 'CLOSE' if the trade thesis is broken (price rejected the forecast target, trend reversed, or the position is stale with no momentum) or if a hard risk limit is at risk.\n" +
            "- 'HOLD' if the thesis remains intact and the position is progressing toward target.\n" +
            "Provide a concrete quantitative reason (e.g., 'CLOSE: price rejected target with RSI diverging', or 'HOLD: price still above EMA20, +1.5R to target'). Never leave a ticket without an action.\n"
        )

    # Explicitly separate the two decisions so the LLM does not mix them:
    # "signal" = NEW ENTRY only. "position_actions" = EXISTING positions only.
    if open_positions and len(open_positions) > 0:
        separation_note = (
            "\nIMPORTANT — TWO SEPARATE DECISIONS:\n"
            "1. The 'signal' field above is ONLY about opening a NEW trade. "
            "It must be BUY/SELL/HOLD based purely on whether a NEW entry is attractive now.\n"
            "2. The 'position_actions' list is ONLY about the EXISTING positions listed above. "
            "Do NOT let your opinion about existing positions change your 'signal', and do NOT "
            "let your entry bias change your position_actions. Evaluate each independently.\n"
        )
    else:
        separation_note = ""

    # Timeframe label per symbol: BTC trades M30 (intraday), XAU trades M5 (scalp)
    is_crypto_sym = config.is_crypto(symbol)
    tf_label = "M30" if is_crypto_sym else "M5"
    tf_full = "30 Minute (M30) intraday" if is_crypto_sym else "5 Minute (M5) scalping"
    strategy_header = "M30 Intraday Strategy" if is_crypto_sym else "M5 Scalping Strategy"
    strategy_line = (
        "M30: enter on clear 30-minute structure — follow-through after a decisive "
        "M30 breakout or a clean pullback to support/resistance."
        if is_crypto_sym else
        "Scalp M5: quick entries/exits, high probability setups only. Decide from "
        "the data provided — do not wait for hypothetical pullbacks/breakouts."
    )
    momentum_line = (
        "Follow the dominant H1 price action and momentum (H1 candles); a clear "
        "impulse with structure break is a valid entry even against the H4/D1 bias."
        if is_crypto_sym else
        "BUY and SELL are equally valid. Follow the dominant M5 price action and "
        "momentum (M1/M5 candles); a clear impulse with structure break is a valid "
        "entry even against a higher-timeframe bias."
    )

    # 50-bar Swing High, Swing Low, and Fibonacci Retracement Levels
    swing_high = float(df['high'].max())
    swing_low = float(df['low'].min())
    diff = swing_high - swing_low
    fib_382 = round(swing_high - 0.382 * diff, 2)
    fib_500 = round(swing_high - 0.500 * diff, 2)
    fib_618 = round(swing_high - 0.618 * diff, 2)
    fib_str = (
        f"- 50-Bar Swing High: {swing_high:.2f} | Swing Low: {swing_low:.2f}\n"
        f"- Fibonacci Retracement Levels: Fib 38.2%: {fib_382:.2f} | Fib 50.0%: {fib_500:.2f} | Fib 61.8%: {fib_618:.2f}"
    )

    # ================================================================
    # PROMPT — 2 blok:
    #   Blok 1 (STATIS, prefix): instruksi + format. Di-cache via
    #     cache_control (lihat _execute_claude_single). Harus >= 1024
    #     token biar Anthropic benar-benar meng-cache.
    #   Blok 2 (DINAMIS): data pasar yang berubah tiap cycle.
    # ================================================================
    # Bagian yang BERUBAH per cycle (candle, tick, posisi, forecast, dll)
    print(f"[LLM PROMPT PREVIEW] symbol={symbol} tf={tf_label} bid={current_tick['bid']} ask={current_tick['ask']} spread={current_tick['spread']}pt point={current_tick['point']}")
    print(f"[LLM PROMPT PREVIEW] close={latest['close']} rsi={latest['rsi_14']:.2f} ema20={latest['ema_20']:.2f} ema50={latest['ema_50']:.2f} atr={latest['atr_14']:.2f} atr_points={atr_points}")
    print(f"[LLM PROMPT PREVIEW] fib382={fib_382:.2f} fib500={fib_500:.2f} fib618={fib_618:.2f} swing_high={swing_high:.2f} swing_low={swing_low:.2f}")
    print(f"[LLM PROMPT PREVIEW] recent_candles=7 micro_candles={'yes' if micro_candles_str else 'no'} forecast={'yes' if forecast_str else 'no'} positions={'yes' if positions_str else 'no'}")

    market_data_block = f"""### MARKET DATA CONTEXT
Symbol: {symbol}
Timeframe: {tf_label}
Current Bid: {current_tick['bid']}
Current Ask: {current_tick['ask']}
Spread: {current_tick['spread']} points (point size = {current_tick['point']})

### RECENT CANDLES (Last 7 candles, {tf_label}):
{candles_str}
{micro_candles_str}
### CURRENT INDICATORS & FIBONACCI SUMMARY
- Current Close: {latest['close']}
- RSI (14): {latest['rsi_14']:.2f}
- EMA (20): {latest['ema_20']:.2f}
- EMA (50): {latest['ema_50']:.2f}
- ATR (14): {latest['atr_14']:.2f} (which is {atr_points} points)
{fib_str}
{randomness_str}{quant_prob_str}{macro_str}{lessons_str}{decision_memory_str}{forecast_str}{calendar_str}{positions_str}{separation_note}
{usd_context}"""

    # Bagian yang RELATIF STATIS antar cycle (instruksi + format output).
    # Sl/TP range ikut ATR (berubah pelan) — tetap di blok statis biar
    # prefix panjang (>= 1024 token) dan cache berguna. LLM tetap lihat
    # ATR aktual di blok dinamis.
    static_block = f"""You are an expert algorithmic trading system specializing in {tf_full} on {symbol} — {asset_desc(symbol)}.
Analyze the current market condition and determine the next trading decision.

### READING THE DATA
- RSI: >70 overbought, <30 oversold; divergence = warning.
- EMA20/50: above both bullish, below both bearish; EMA20 cross = momentum shift.
- Fibonacci: Fib 38.2%/50.0%/61.8% levels act as natural pullback targets & support/resistance zones.
- ATR: SL outside 1.5-2x ATR; TP >= 1.5x SL.
- Candles: impulse + follow-through > single wick; rejection wicks = reversal signal.
- Spread: large fraction of SL/TP → not viable.
- Calendar: HIGH-impact events spike volatility; avoid 15-30 min before/after. No event = trade normally.

### STRATEGY ({strategy_header})
- {strategy_line}
- {momentum_line}
- Counter-trend / Pullback Scalps: Allowed during strong trends IF price is overextended near Swing High/Low (RSI > 70 or < 30), price is stretched away from EMA20/EMA50, and the entry targets a Fibonacci retracement (Fib 38.2% / 50.0% / 61.8%) or EMA20 with a tight SL beyond the swing extremum and R:R >= 1.5.
- Forecast Alignment: Prefer trading with the forecast bias, but retracement/pullback scalps to Fibonacci levels are valid counter-trend entries when the move is extended and the pullback target is explicit. Forecast is a preference, NOT a hard block, unless the setup is a pure momentum chase with no retracement structure.
- IMPORTANT: A bullish forecast does NOT forbid SELL, and a bearish forecast does NOT forbid BUY, if the trade is a clean Fibonacci retracement / exhaustion reversal with a tight SL and valid R:R.
- SL/TP in POINTS. ATR {atr_points} pts: SL {min_sl}-{max_sl} pts; TP >= 1.5x SL. BTC: tiny SL/TP (< 5000 pts) are worth cents.
- No clear edge → HOLD. Do not force a trade.
- If bias is bullish but price is at/near Swing High and showing exhaustion, SELL retracement is allowed if TP is Fib 38.2% / 50.0% / 61.8% or EMA20 and SL is tight beyond the swing high.
- If bias is bearish but price is at/near Swing Low and showing exhaustion, BUY retracement is allowed if TP is Fib 38.2% / 50.0% / 61.8% or EMA20 and SL is tight beyond the swing low.

### DECISION ORDER
Trend → Momentum → Location (S/R vs mid-range vs Fib levels) → R:R (SL beyond S/R, TP >= 1.5x SL, R:R < 1.5 skip) → Spread (> ~20% SL skip) → Forecast (prefer aligned, allow Fib pullback if R:R >= 1.5).
Any step fails → HOLD.

### CONFIDENCE
0.70+ strong | 0.50-0.70 moderate | 0.30-0.50 weak → HOLD unless concrete reason | < 0.30 no edge → HOLD.
HOLD with high confidence is normal and preferred when there is no clear entry.

### RESPONSE FORMAT
You MUST respond with a valid JSON object ONLY. Do not include any text before or after the JSON.

- HOLD (include signal & 1-sentence reasoning):
{{
  "signal": "HOLD",
  "reasoning": "Concise reasoning (EXACTLY 1 short sentence) explaining why holding / no clear entry setup."
}}
- BUY/SELL (full format required):
{{
  "signal": "BUY" | "SELL",
  "confidence": 0.0 to 1.0,
  "sl_points": number (distance in points for Stop Loss, e.g., {int((min_sl+max_sl)/2)}),
  "tp_points": number (distance in points for Take Profit, e.g., {int((min_tp+max_tp)/2)}),
  "reasoning": "Concise reasoning (MAXIMUM 1-2 short sentences) explaining the NEW ENTRY decision based on price action/indicators — NOT based on existing positions (those go in position_actions)."
}}
Example HOLD: {{"signal": "HOLD", "reasoning": "Price is consolidating near EMA20 with RSI neutral, showing no clear breakout setup."}}
Example BUY: {{"signal": "BUY", "confidence": 0.72, "sl_points": {int((min_sl+max_sl)/2)}, "tp_points": {int((min_tp+max_tp)/2)}, "reasoning": "Impulse breakout above H1 resistance with RSI momentum."}}
"position_actions": include ONLY when positions are listed above — for each ticket: {{"ticket": number, "action": "CLOSE" | "HOLD", "reason": "Reason (max 5 words)"}}"""

    # Gabung: statis dulu (cache), lalu data (dinamis)
    prompt = static_block + "\n\n" + market_data_block + "\n"
    return prompt


def clean_json_response(text):
    """Cleans markdown JSON wrappers (```json ... ```) and parses the JSON."""
    try:
        # Search for content between ```json and ``` or ``` and ```
        text_clean = text.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text_clean, re.DOTALL)
        if match:
            text_clean = match.group(1)
        else:
            # Fallback: find the first '{' and last '}'
            start = text_clean.find('{')
            end = text_clean.rfind('}')
            if start != -1 and end != -1:
                text_clean = text_clean[start:end+1]
        
        try:
            parsed = json.loads(text_clean)
        except json.JSONDecodeError:
            # Truncated/incomplete JSON (Claude sometimes cuts mid-string).
            # Recover whatever fields were already emitted line by line.
            parsed = {}
            for line in text_clean.splitlines():
                m = re.match(r'\s*"(\w+)":\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|null|true|false)', line)
                if m:
                    key, val = m.group(1), m.group(2)
                    try:
                        parsed[key] = json.loads(val)
                    except json.JSONDecodeError:
                        parsed[key] = val.strip('"')
        # Validate keys
        for key in ["signal", "confidence", "sl_points", "tp_points", "reasoning"]:
            if key not in parsed:
                parsed[key] = None
        # Ensure signal is upper case
        if parsed.get("signal"):
            parsed["signal"] = str(parsed["signal"]).upper()
            if parsed["signal"] not in ["BUY", "SELL", "HOLD"]:
                parsed["signal"] = "HOLD"
        else:
            parsed["signal"] = "HOLD"

        if parsed["signal"] == "HOLD":
            if parsed.get("confidence") is None:
                parsed["confidence"] = 0.0
            if parsed.get("reasoning") is None:
                parsed["reasoning"] = "HOLD — No entry setup"

        return parsed
    except Exception as e:
        print(f"[LLM PARSE ERROR] Gagal memparsing JSON: {e}. Raw response: {text[:150]}")
        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "sl_points": None,
            "tp_points": None,
            "reasoning": f"Gagal memparsing respon: {str(e)}"
        }


def _execute_openai_single(model_name, prompt, timeout_sec):
    is_reasoning = "gpt-5" in model_name.lower() or "o1" in model_name.lower() or "o3" in model_name.lower()
    if is_reasoning:
        response = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": "System: You are a professional financial trading assistant. Keep reasoning extremely concise (max 1-2 sentences).\n\n" + prompt}
            ],
            response_format={"type": "json_object"},
            timeout=timeout_sec
        )
    else:
        response = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a professional financial trading assistant. Keep reasoning extremely concise (max 1-2 sentences)."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=timeout_sec
        )
    content = response.choices[0].message.content
    return clean_json_response(content)


def query_openai(prompt):
    """Queries OpenAI API with timeout and fallback model support."""
    if not openai_client:
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "OpenAI API Key tidak diset."}

    primary_model = config.OPENAI_MODEL
    fallback_model = getattr(config, "OPENAI_FALLBACK_MODEL", None)
    timeout_sec = getattr(config, "LLM_TIMEOUT_SECONDS", 5.0)

    try:
        return _execute_openai_single(primary_model, prompt, timeout_sec)
    except Exception as e:
        if fallback_model and fallback_model != primary_model:
            print(f"⚠️ [OPENAI FALLBACK] Model {primary_model} lambat/error ({e}). Switching ke fallback ({fallback_model})...")
            try:
                return _execute_openai_single(fallback_model, prompt, timeout_sec)
            except Exception as fb_err:
                print(f"[OPENAI FALLBACK ERROR] {fb_err}")
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"OpenAI Error: {str(fb_err)}"}
        else:
            print(f"[OPENAI ERROR] {e}")
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"OpenAI Error: {str(e)}"}


def query_gemini(prompt):
    """Queries Gemini API with timeout and fallback model support."""
    if not gemini_client:
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "Gemini API Key tidak diset."}

    primary_model = config.GEMINI_MODEL
    fallback_model = getattr(config, "GEMINI_FALLBACK_MODEL", None)
    timeout_sec = getattr(config, "LLM_TIMEOUT_SECONDS", 5.0)

    def _call(mod):
        from google.genai import types
        res = gemini_client.models.generate_content(
            model=mod,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return clean_json_response(res.text)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_call, primary_model)
            return fut.result(timeout=timeout_sec)
    except Exception as e:
        if fallback_model and fallback_model != primary_model:
            print(f"⚠️ [GEMINI FALLBACK] Model {primary_model} lambat/error ({e}). Switching ke fallback ({fallback_model})...")
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut = ex.submit(_call, fallback_model)
                    return fut.result(timeout=timeout_sec)
            except Exception as fb_err:
                print(f"[GEMINI FALLBACK ERROR] {fb_err}")
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Gemini Error: {str(fb_err)}"}
        else:
            print(f"[GEMINI ERROR] {e}")
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Gemini Error: {str(e)}"}


def _execute_claude_single(model_name, prompt, timeout_sec):
    system_text = (
        "You are a professional financial trading assistant. "
        "Always respond with valid JSON only. Keep reasoning extremely concise (max 1-2 short sentences)."
    )
    # Prompt caching: pecah prompt jadi blok statis (instruksi, DI DEPAN) +
    # dinamis (data pasar, DI BELAKANG). cache_control ditaruh di AKHIR blok
    # statis — prefix yang identik antar request. System terlalu pendek
    # (< 1024 token) untuk di-cache, jadi breakpoint di user block.
    split_marker = "### MARKET DATA CONTEXT"
    if split_marker in prompt:
        static_part, dynamic_part = prompt.split(split_marker, 1)
        dynamic_part = split_marker + dynamic_part
        user_blocks = [
            {"type": "text", "text": static_part,
             "cache_control": {"type": "ephemeral"}},
            {"type": "text", "text": dynamic_part},
        ]
    else:
        # Tidak ketemu marker — fallback: cache seluruh prompt (kalau statis)
        user_blocks = [{"type": "text", "text": prompt,
                        "cache_control": {"type": "ephemeral"}}]
    # Enable Anthropic Prompt Caching via cache_control and prompt-caching header
    try:
        response = claude_client.messages.create(
            model=model_name,
            max_tokens=2000,
            system=[
                {
                    "type": "text",
                    "text": system_text,
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": user_blocks,
                }
            ],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
            timeout=timeout_sec
        )
    except Exception:
        # Fallback for standard call if prompt caching header or structure is not supported
        response = claude_client.messages.create(
            model=model_name,
            max_tokens=2000,
            system=system_text,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout_sec
        )
    content = "".join(b.text for b in response.content if b.type == "text")
    return clean_json_response(content)


def _execute_deepseek_single(model_name, prompt, timeout_sec):
    """Query DeepSeek (OpenAI-compatible API). model_name passed WITHOUT the
    'deepseek/' prefix (e.g. 'deepseek-v4-flash'). Explicitly disables thinking/reasoning
    mode for super-fast ~1.2s latency."""
    raw_model = model_name.split("/", 1)[1] if "/" in model_name else model_name
    try:
        try:
            # Explicitly disable thinking/reasoning mode for super-fast execution (~1.2s)
            response = deepseek_client.chat.completions.create(
                model=raw_model,
                messages=[
                    {"role": "system", "content": "You are a professional financial trading assistant. Respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                reasoning_effort="none",
                extra_body={"thinking": {"type": "disabled"}},
                timeout=timeout_sec
            )
        except Exception:
            # Fallback to standard call if API endpoint does not recognize reasoning params
            response = deepseek_client.chat.completions.create(
                model=raw_model,
                messages=[
                    {"role": "system", "content": "You are a professional financial trading assistant. Respond with valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                timeout=timeout_sec
            )
        return clean_json_response(response.choices[0].message.content)
    except Exception as e:
        raise e


def query_claude(prompt):
    """Queries the 'Claude slot' model with timeout and fallback support.
    Routes automatically: model starting with 'deepseek/' -> DeepSeek API
    (OpenAI-compatible, much cheaper); 'claude-...' -> Anthropic.
    Config: config.CLAUDE_MODEL / config.CLAUDE_FALLBACK_MODEL."""
    primary_model = config.CLAUDE_MODEL
    fallback_model = getattr(config, "CLAUDE_FALLBACK_MODEL", None)
    timeout_sec = getattr(config, "LLM_TIMEOUT_SECONDS", 24.0)

    is_deepseek = primary_model.startswith("deepseek/")

    try:
        if is_deepseek:
            if not deepseek_client:
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": "DeepSeek API Key tidak diset."}
            return _execute_deepseek_single(primary_model, prompt, timeout_sec)
        if not claude_client:
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": "Claude API Key tidak diset."}
        return _execute_claude_single(primary_model, prompt, timeout_sec)
    except Exception as e:
        if fallback_model and fallback_model != primary_model:
            print(f"⚠️ [CLAUDE FALLBACK] Model {primary_model} lambat/error ({e}). Switching ke fallback ({fallback_model})...")
            try:
                if fallback_model.startswith("deepseek/"):
                    return _execute_deepseek_single(fallback_model, prompt, timeout_sec)
                return _execute_claude_single(fallback_model, prompt, timeout_sec)
            except Exception as fb_err:
                print(f"[CLAUDE FALLBACK ERROR] {fb_err}")
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Claude Error: {str(fb_err)}"}
        else:
            print(f"[CLAUDE ERROR] {e}")
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Claude Error: {str(e)}"}



def prepare_debate_prompt(symbol, base_prompt, round1_results):
    """Constructs the Round 2 debate prompt showcasing all initial model decisions."""
    summary_lines = []
    for model_name, res in round1_results.items():
        sig = res.get("signal", "HOLD")
        conf = res.get("confidence", 0.0)
        reason = res.get("reasoning", "")
        summary_lines.append(f"- **{model_name}**: Decision = `{sig}` (Conf: {conf*100:.0f}%), Reasoning: \"{reason}\"")

    debate_context = "\n".join(summary_lines)

    debate_prompt = f"""{base_prompt}

### MULTI-AGENT DEBATE ROUND 2
In Round 1, the 3 AI models evaluated the market and produced conflicting decisions:
{debate_context}

Carefully review and critique the counter-arguments provided by the other models.
Consider if their observations regarding technical indicators, dynamic EMAs, support/resistance, or macro risk alter your assessment.
Re-evaluate your position and cast your REVISED final decision for Round 2.
"""
    return debate_prompt


def get_multi_llm_decisions(symbol, df, current_tick, macro_context=None, open_positions=None):
    """
    Sends the prompt to OpenAI, Gemini, and Claude in parallel threads
    to minimize latency. If Round 1 lacks consensus, triggers Multi-Agent Debate Round 2.
    Also evaluates active open positions for early close recommendations.
    """
    prompt = prepare_prompt(symbol, df, current_tick, macro_context, open_positions)

    
    results = {}
    latencies = {}
    start_total = time.time()
    
    def _query_timed(query_fn, p):
        t0 = time.time()
        res = query_fn(p)
        elapsed = time.time() - t0
        return res, elapsed

    # Run in parallel using thread pool
    slot_label = claude_slot_label()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_model = {
            executor.submit(_query_timed, query_openai, prompt): "OpenAI",
            executor.submit(_query_timed, query_gemini, prompt): "Gemini",
            executor.submit(_query_timed, query_claude, prompt): slot_label
        }
        
        for future in concurrent.futures.as_completed(future_to_model):
            model_name = future_to_model[future]
            try:
                data, elapsed = future.result()
                results[model_name] = data
                latencies[model_name] = elapsed
            except Exception as exc:
                print(f"[LLM CLIENT ERROR] Model {model_name} generated an exception: {exc}")
                results[model_name] = {"signal": "HOLD", "confidence": 0.0, "reasoning": str(exc)}
                latencies[model_name] = 0.0

    total_elapsed = time.time() - start_total
    lat_str = " | ".join([f"{m}: {latencies.get(m, 0.0):.2f}s" for m in ["OpenAI", "Gemini", slot_label] if m in latencies])
    print(f"⏱️ [LATENSI MODEL (Ronde 1)] {lat_str} (Total: {total_elapsed:.2f}s)")
    
    # Check consensus from Round 1
    signals_count = {"BUY": 0, "SELL": 0, "HOLD": 0}
    for m, res in results.items():
        sig = res.get("signal", "HOLD")
        signals_count[sig] = signals_count.get(sig, 0) + 1

    consensus_target = getattr(config, "CONSENSUS_THRESHOLD", 2)
    has_consensus = signals_count["BUY"] >= consensus_target or signals_count["SELL"] >= consensus_target

    debate_enabled = getattr(config, "DEBATE_ENABLED", True)
    if not has_consensus and debate_enabled:
        print("\n💬 [DEBATE TRIGGERED] Ronde 1 tidak mencapai konsensus. Memulai diskusi Multi-Agent Debate...")
        debate_prompt = prepare_debate_prompt(symbol, prompt, results)
        
        round2_results = {}
        round2_latencies = {}
        start_d = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_model = {
                executor.submit(_query_timed, query_openai, debate_prompt): "OpenAI",
                executor.submit(_query_timed, query_gemini, debate_prompt): "Gemini",
                executor.submit(_query_timed, query_claude, debate_prompt): slot_label
            }
            for future in concurrent.futures.as_completed(future_to_model):
                model_name = future_to_model[future]
                try:
                    data, elapsed = future.result()
                    round2_results[model_name] = data
                    round2_latencies[model_name] = elapsed
                except Exception as exc:
                    round2_results[model_name] = {"signal": "HOLD", "confidence": 0.0, "reasoning": str(exc)}
                    round2_latencies[model_name] = 0.0
                    
        total_d = time.time() - start_d
        d_str = " | ".join([f"{m}: {round2_latencies.get(m, 0.0):.2f}s" for m in ["OpenAI", "Gemini", slot_label] if m in round2_latencies])
        print(f"💬 [DEBATE SELESAI] {d_str} (Total Debate: {total_d:.2f}s)")
        return round2_results

    return results
