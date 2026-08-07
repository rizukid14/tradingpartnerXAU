import json
import re
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
{macro_str}
### STRATEGY CONSTRAINTS (5-minute Scalping)
- Look for quick entries and exits.
- Trades should be high probability. If market is sideways, unclear, or spread is too high relative to ATR, prefer 'HOLD'.
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
        
    try:
        # Check if the model is a reasoning model (which does not support temperature/system message)
        is_reasoning = "gpt-5" in config.OPENAI_MODEL.lower() or "o1" in config.OPENAI_MODEL.lower() or "o3" in config.OPENAI_MODEL.lower()
        
        if is_reasoning:
            response = openai_client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {"role": "user", "content": "System: You are a professional financial trading assistant.\n\n" + prompt}
                ],
                response_format={"type": "json_object"},
                timeout=30
            )
        else:
            response = openai_client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are a professional financial trading assistant."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                timeout=30
            )
        content = response.choices[0].message.content
        return clean_json_response(content)
    except Exception as e:
        print(f"[OPENAI ERROR] {e}")
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"OpenAI Error: {str(e)}"}


def query_gemini(prompt):
    """Queries Gemini API using the new google-genai SDK."""
    if not gemini_client:
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "Gemini API Key tidak diset."}
        
    try:
        from google.genai import types
        response = gemini_client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        content = response.text
        return clean_json_response(content)
    except Exception as e:
        print(f"[GEMINI ERROR] {e}")
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Gemini Error: {str(e)}"}


def query_deepseek(prompt):
    """Queries DeepSeek API using OpenAI compatible SDK."""
    if not deepseek_client:
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "DeepSeek API Key tidak diset."}
        
    try:
        # Deepseek supports json mode as well
        response = deepseek_client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional financial trading assistant."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=30
        )
        content = response.choices[0].message.content
        return clean_json_response(content)
    except Exception as e:
        print(f"[DEEPSEEK ERROR] {e}")
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"DeepSeek Error: {str(e)}"}


def get_multi_llm_decisions(symbol, df, current_tick, macro_context=None):
    """
    Sends the prompt to OpenAI, Gemini, and DeepSeek in parallel threads
    to minimize latency.
    """
    prompt = prepare_prompt(symbol, df, current_tick, macro_context)
    
    results = {}
    
    # Run in parallel using thread pool
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_to_model = {
            executor.submit(query_openai, prompt): "OpenAI",
            executor.submit(query_gemini, prompt): "Gemini",
            executor.submit(query_deepseek, prompt): "DeepSeek"
        }
        
        for future in concurrent.futures.as_completed(future_to_model):
            model_name = future_to_model[future]
            try:
                data = future.result()
                results[model_name] = data
            except Exception as exc:
                print(f"[LLM CLIENT ERROR] Model {model_name} generated an exception: {exc}")
                results[model_name] = {"signal": "HOLD", "confidence": 0.0, "reasoning": str(exc)}
                
    return results
