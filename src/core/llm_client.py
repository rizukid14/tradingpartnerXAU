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

deepseek_client = None
if config.DEEPSEEK_API_KEY:
    deepseek_client = OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_API_BASE
    )

gemini_client = None
if config.GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)


def query_primary_model(prompt, search_grounding=False):
    """
    Queries a single model (prefers Gemini, then OpenAI, then DeepSeek)
    for background macro/fundamental or timeframe analysis.
    If search_grounding is True, it enables Google Search tools on Gemini.
    """
    # 1. Try Gemini
    if gemini_client and config.GEMINI_API_KEY:
        try:
            from google.genai import types
            
            gen_config = None
            if search_grounding:
                gen_config = types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
                
            response = gemini_client.models.generate_content(
                model=config.PRIMARY_ANALYSIS_MODEL,
                contents=prompt,
                config=gen_config
            )
            if response and response.text:
                return response.text.strip()
        except Exception as e:
            print(f"[PRIMARY MODEL ERROR - GEMINI] {e}")

    # 2. Try OpenAI (does not support Google Search grounding out-of-the-box in SDK)
    if openai_client and config.OPENAI_API_KEY:
        try:
            response = openai_client.chat.completions.create(
                model=config.OPENAI_MODEL,
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

    # 3. Try DeepSeek
    if deepseek_client and config.DEEPSEEK_API_KEY:
        try:
            response = deepseek_client.chat.completions.create(
                model=config.DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional financial trading assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                timeout=30
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[PRIMARY MODEL ERROR - DEEPSEEK] {e}")

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

Your response must be extremely brief (maximum 2-3 sentences) as it will be used as background context for a 5-minute scalping execution model.
"""
    return query_primary_model(prompt, search_grounding=False)


def analyze_fundamentals(symbol):
    """
    Queries Gemini using Google Search Grounding to summarize the latest 
    macroeconomic sentiment and news affecting Gold/Forex.
    """
    prompt = f"""
What is the latest macroeconomic news affecting {symbol} (Gold/Forex) prices today? 
Summarize the main themes, current market sentiment, and any high-impact economic news releases (like NFP, CPI, or central bank decisions).

Your response must be extremely brief (maximum 3-4 sentences) as it will be used as background context for a 5-minute scalping execution model.
"""
    # Force search grounding tool
    return query_primary_model(prompt, search_grounding=True)


def prepare_prompt(symbol, df, current_tick, macro_context=None):
    """
    Constructs a highly structured trading prompt with market context
    and requests a standard JSON response.
    """
    # Take the last 10 candles for context
    recent_candles = df.tail(10).to_dict(orient="records")
    
    # Format candle list for readability in prompt
    candles_str = ""
    for c in recent_candles:
        candles_str += f"- Time: {c['time']}, O: {c['open']}, H: {c['high']}, L: {c['low']}, C: {c['close']}, Vol: {c['tick_volume']}, RSI: {c['rsi_14']:.2f}, EMA20: {c['ema_20']:.2f}, EMA50: {c['ema_50']:.2f}\n"

    latest = df.iloc[-1]
    point_size = current_tick.get("point", 0.01)
    atr_points = int(latest["atr_14"] / point_size) if point_size > 0 else 0
    min_sl = int(atr_points * 1.5)
    max_sl = int(atr_points * 2.0)
    min_tp = int(min_sl * 1.5)
    max_tp = int(max_sl * 2.0)

    macro_str = ""
    if macro_context:
        macro_str = f"\n### HIGHER-LEVEL MACRO & TIMEFRAME CONTEXT\n{macro_context}\n"

    lessons_str = ""
    try:
        from src.analytics import trade_evaluator
        lessons_str = trade_evaluator.evaluator.get_lessons_context()
    except Exception:
        pass

    forecast_str = ""
    try:
        from src.analytics import forecast_engine
        forecast_str = forecast_engine.forecaster.get_forecast_context()
    except Exception:
        pass


    prompt = f"""
You are an expert algorithmic trading system specializing in 5-minute (M5) scalping on {symbol} (Gold/Forex).
Analyze the current market condition and determine the next trading decision.

### MARKET DATA CONTEXT
Symbol: {symbol}
Timeframe: M5 (5 Minutes)
Current Bid: {current_tick['bid']}
Current Ask: {current_tick['ask']}
Spread: {current_tick['spread']} points (1 point = {current_tick['point']})

### RECENT CANDLES (Last 10 candles, M5):
{candles_str}

### CURRENT INDICATORS SUMMARY
- Current Close: {latest['close']}
- RSI (14): {latest['rsi_14']:.2f}
- EMA (20): {latest['ema_20']:.2f}
- EMA (50): {latest['ema_50']:.2f}
- ATR (14): {latest['atr_14']:.2f} (which is {atr_points} points)
{macro_str}{lessons_str}{forecast_str}
### STRATEGY CONSTRAINTS (5-minute Scalping)
- Look for quick entries and exits.
- Trades should be high probability. If market is sideways, unclear, or spread is too high relative to ATR, prefer 'HOLD'.
- HIGH-IMPACT NEWS TIMING RULE: High-impact economic news (such as NFP, CPI, or FOMC) ONLY restricts trading during the 15-30 minutes IMMEDIATELY preceding or following the actual release time. If the news event is hours away in a future session (e.g. NFP in NY session while currently in Tokyo/London session), DO NOT hold back high-probability 5-minute scalping setups during current session!
- OPTIMAL ENTRY RANGE & R:R RULE: If the current market price is heavily extended far away from Support/Invalidation Level (e.g., projection R:R T+15m < 0.50), DO NOT chase entries at extreme highs/lows! You MUST select 'HOLD' or provide lower confidence to wait for a healthy price pullback into the Optimal Entry Zone near Support/Resistance before issuing a BUY or SELL signal.



- Suggested Stop Loss (SL) and Take Profit (TP) must be specified in POINTS (where 1 Gold point = 0.01 USD, e.g., 300 points = $3.00 movement).
- Based on the current ATR of {atr_points} points:
  - Your Stop Loss (SL) MUST be between {min_sl} and {max_sl} points (1.5x to 2x the ATR).
  - Your Take Profit (TP) MUST be at least 1.5x of your suggested SL (e.g., between {min_tp} and {max_tp} points).

### RESPONSE FORMAT
You MUST respond with a valid JSON object ONLY. Do not include any text before or after the JSON.
JSON schema:
{{
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0 to 1.0,
  "sl_points": number (distance in points for Stop Loss, e.g., {int((min_sl+max_sl)/2)}),
  "tp_points": number (distance in points for Take Profit, e.g., {int((min_tp+max_tp)/2)}),
  "reasoning": "A concise sentence explaining the decision based on RSI, EMAs, and price action."
}}

"""
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
        
        parsed = json.loads(text_clean)
        # Validate keys
        for key in ["signal", "confidence", "sl_points", "tp_points", "reasoning"]:
            if key not in parsed:
                parsed[key] = None
        # Ensure signal is upper case
        if parsed["signal"]:
            parsed["signal"] = parsed["signal"].upper()
            if parsed["signal"] not in ["BUY", "SELL", "HOLD"]:
                parsed["signal"] = "HOLD"
        else:
            parsed["signal"] = "HOLD"
            
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


def query_openai(prompt):
    """Queries OpenAI API."""
    if not openai_client:
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "OpenAI API Key tidak diset."}
def _execute_openai_single(model_name, prompt, timeout_sec):
    is_reasoning = "gpt-5" in model_name.lower() or "o1" in model_name.lower() or "o3" in model_name.lower()
    if is_reasoning:
        response = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": "System: You are a professional financial trading assistant.\n\n" + prompt}
            ],
            response_format={"type": "json_object"},
            timeout=timeout_sec
        )
    else:
        response = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a professional financial trading assistant."},
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


def _execute_deepseek_single(model_name, prompt, timeout_sec):
    response = deepseek_client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": "You are a professional financial trading assistant."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        timeout=timeout_sec
    )
    content = response.choices[0].message.content
    return clean_json_response(content)


def query_deepseek(prompt):
    """Queries DeepSeek API with timeout and fallback model support."""
    if not deepseek_client:
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "DeepSeek API Key tidak diset."}

    primary_model = config.DEEPSEEK_MODEL
    fallback_model = getattr(config, "DEEPSEEK_FALLBACK_MODEL", None)
    timeout_sec = getattr(config, "LLM_TIMEOUT_SECONDS", 5.0)

    try:
        return _execute_deepseek_single(primary_model, prompt, timeout_sec)
    except Exception as e:
        if fallback_model and fallback_model != primary_model:
            print(f"⚠️ [DEEPSEEK FALLBACK] Model {primary_model} lambat/error ({e}). Switching ke fallback ({fallback_model})...")
            try:
                return _execute_deepseek_single(fallback_model, prompt, timeout_sec)
            except Exception as fb_err:
                print(f"[DEEPSEEK FALLBACK ERROR] {fb_err}")
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"DeepSeek Error: {str(fb_err)}"}
        else:
            print(f"[DEEPSEEK ERROR] {e}")
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"DeepSeek Error: {str(e)}"}



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


def get_multi_llm_decisions(symbol, df, current_tick, macro_context=None):
    """
    Sends the prompt to OpenAI, Gemini, and DeepSeek in parallel threads
    to minimize latency. If Round 1 lacks consensus, triggers Multi-Agent Debate Round 2.
    """
    prompt = prepare_prompt(symbol, df, current_tick, macro_context)
    
    results = {}
    latencies = {}
    start_total = time.time()
    
    def _query_timed(query_fn, p):
        t0 = time.time()
        res = query_fn(p)
        elapsed = time.time() - t0
        return res, elapsed

    # Run in parallel using thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_model = {
            executor.submit(_query_timed, query_openai, prompt): "OpenAI",
            executor.submit(_query_timed, query_gemini, prompt): "Gemini",
            executor.submit(_query_timed, query_deepseek, prompt): "DeepSeek"
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
    lat_str = " | ".join([f"{m}: {latencies.get(m, 0.0):.2f}s" for m in ["OpenAI", "Gemini", "DeepSeek"] if m in latencies])
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
                executor.submit(_query_timed, query_deepseek, debate_prompt): "DeepSeek"
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
        d_str = " | ".join([f"{m}: {round2_latencies.get(m, 0.0):.2f}s" for m in ["OpenAI", "Gemini", "DeepSeek"] if m in round2_latencies])
        print(f"💬 [DEBATE SELESAI] {d_str} (Total Debate: {total_d:.2f}s)")
        return round2_results

    return results
