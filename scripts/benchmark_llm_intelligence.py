"""
LLM Market Intelligence Diagnostic Benchmark
Queries OpenAI o4-mini, Gemini 3.1 Flash Lite, Claude Haiku, and DeepSeek V4 Flash
in parallel with a structured diagnostic questionnaire on live MT5 market data.
"""

import os
import sys
import time
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo

# Add workspace root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from config import mt5
from src.core import mt5_connector as connector, llm_client as llm
from src.analytics.macro_analyst import analyst

WIB = ZoneInfo("Asia/Jakarta")

BENCHMARK_PROMPT_TEMPLATE = """You are acting as an elite Chief Quantitative Market Analyst. 
Analyze the real-time market data provided below for {SYMBOL} and answer the structured diagnostic questionnaire with rigorous, objective reasoning.

CRITICAL INSTRUCTION:
Do NOT output a simple JSON dictionary. You are explicitly REQUIRED to answer ALL 6 sections of the DIAGNOSTIC QUESTIONNAIRE below in full, detailed Markdown text format. Explain your calculations, cite exact prices/points, and provide your full analytical reasoning.

{MARKET_DATA_BLOCK}

================================================================================
DIAGNOSTIC QUESTIONNAIRE (ANSWER ALL 6 SECTIONS IN FULL MARKDOWN):
================================================================================

1. [TREND & STRUCTURE CLASSIFICATION]:
   - Macro (100-bar/HTF) trend direction & Intraday (50-bar) structure.
   - Are prices currently expanding in a trend or consolidating/compressing in a range?

2. [MICRO-VELOCITY & MOMENTUM DIAGNOSTIC]:
   - How did the latest price movement unfold in the last 15 minutes (M5 micro action) vs the active candle?
   - Is it an aggressive high-velocity impulse (shock/falling knife) or a slow orderly retracement? Cite the specific numbers/points from the data.

3. [INTERMARKET & COMMODITY CONFLUENCE]:
   - How do current Oil, Copper, and Equities regimes affect this currency pair? Is there macro tailwind or headwind?

4. [STRUCTURAL INVALIDATION LEVEL]:
   - Exact price level where a BUY thesis is mathematically invalidated (broken support behind entry).
   - Exact price level where a SELL thesis is mathematically invalidated (broken resistance behind entry).

5. [DECISION, FORWARD PREDICTION & CONFIDENCE]:
   - Actionable Signal: **BUY** | **SELL** | **HOLD** (Wait for key level confirmation)
   - Confidence Score: (0.0 to 1.0)
   - Suggested SL & TP Distances (in broker points)
   - Forward 2-4 Candle Prediction: What do you anticipate price will do next?

6. [STEP-BY-STEP ANALYTICAL REASONING]:
   - Provide your complete chain-of-thought explaining WHY you arrived at this decision, addressing potential traps and risks.

IMPORTANT REMINDER: Answer all 6 sections above in full text. Do NOT wrap your whole response into a single JSON object.
"""


def _query_model_safe(name, caller_fn, prompt):
    """Executes a single model query with latency measurement."""
    t0 = time.time()
    try:
        res = caller_fn(prompt)
        elapsed = time.time() - t0
        return {
            "model": name,
            "success": True,
            "latency": elapsed,
            "response": res if isinstance(res, str) else json.dumps(res, indent=2)
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "model": name,
            "success": False,
            "latency": elapsed,
            "error": str(e),
            "response": f"[ERROR] Failed to query {name}: {e}"
        }


def run_benchmark(symbol="EURNZD-ECNc"):
    print("=" * 90)
    print(f"  LLM MARKET INTELLIGENCE BENCHMARK - {symbol} ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB')})")
    print("=" * 90)

    if not connector.init_mt5():
        print("[ERROR] MT5 Initialization failed!")
        return

    trade_sym = connector.get_valid_trade_symbol(symbol)
    tf = config.get_timeframe(trade_sym)
    
    # 1. Fetch Market Data & Indicators
    df = connector.get_market_data(trade_sym, tf, num_candles=100)
    if df is None or len(df) < 50:
        print(f"[ERROR] Failed to fetch market data for {trade_sym}")
        return

    tick = mt5.symbol_info_tick(trade_sym)
    s_info = mt5.symbol_info(trade_sym)
    point_size = s_info.point if s_info else 0.00001
    spread_pts = round((tick.ask - tick.bid) / point_size) if point_size > 0 else 0
    
    # 2. Get Macro Context
    macro_ctx = analyst.get_macro_context(trade_sym)
    
    # 3. Build Rich Prompt
    prompt_payload = llm.prepare_prompt(
        symbol=trade_sym,
        df=df,
        current_tick={"bid": tick.bid, "ask": tick.ask, "point": point_size, "spread": spread_pts, "time": tick.time},
        macro_context=macro_ctx
    )

    full_benchmark_prompt = f"""{prompt_payload}

================================================================================
DIAGNOSTIC QUESTIONNAIRE (OVERRIDE: ANSWER ALL 6 SECTIONS IN FULL MARKDOWN):
================================================================================
You are acting as an elite Chief Quantitative Market Analyst.
Analyze the real-time market data provided above for {trade_sym} and answer the structured diagnostic questionnaire with rigorous, objective reasoning.

CRITICAL INSTRUCTION:
Do NOT output a simple JSON dictionary. You are explicitly REQUIRED to answer ALL 6 sections below in full, detailed Markdown text format. Explain your calculations, cite exact prices/points from the data above, and provide your full analytical reasoning.

1. [TREND & STRUCTURE CLASSIFICATION]:
   - Macro (100-bar/HTF) trend direction & Intraday (50-bar) structure.
   - Are prices currently expanding in a trend or consolidating/compressing in a range?

2. [MICRO-VELOCITY & MOMENTUM DIAGNOSTIC]:
   - How did the latest price movement unfold in the last 15 minutes (M5 micro action) vs the active candle?
   - Is it an aggressive high-velocity impulse (shock/falling knife) or a slow orderly retracement? Cite the specific numbers/points from the data above.

3. [INTERMARKET & COMMODITY CONFLUENCE]:
   - How do current Oil, Copper, and Equities regimes affect this currency pair? Is there macro tailwind or headwind?

4. [STRUCTURAL INVALIDATION LEVEL]:
   - Exact price level where a BUY thesis is mathematically invalidated (broken support behind entry).
   - Exact price level where a SELL thesis is mathematically invalidated (broken resistance behind entry).

5. [DECISION, FORWARD PREDICTION & CONFIDENCE]:
   - Actionable Signal: **BUY** | **SELL** | **HOLD** (Wait for key level confirmation)
   - Confidence Score: (0.0 to 1.0)
   - Suggested SL & TP Distances (in broker points)
   - Forward 2-4 Candle Prediction: What do you anticipate price will do next?

6. [STEP-BY-STEP ANALYTICAL REASONING]:
   - Provide your complete chain-of-thought explaining WHY you arrived at this decision, addressing potential traps and risks.

IMPORTANT REMINDER: Answer all 6 sections above in full text. Do NOT wrap your whole response into a single JSON object.
"""

    print(f"[*] Prompt constructed (~{len(full_benchmark_prompt.split())} words). Querying 4 LLMs in parallel...")

    # 4. Define Callers for All 4 Models
    model_callers = {}

    # Model 1: OpenAI o4-mini
    if config.OPENAI_API_KEY:
        def call_openai(p):
            from openai import OpenAI
            client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_API_BASE)
            resp = client.chat.completions.create(
                model=config.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "You are an elite quantitative financial analyst. Answer the diagnostic questionnaire in full markdown text format."},
                    {"role": "user", "content": p}
                ],
                max_completion_tokens=3000,
                timeout=55
            )
            choice = resp.choices[0]
            if choice.message.content:
                return choice.message.content.strip()
            return str(choice.message)
        model_callers["OpenAI o4-mini"] = call_openai

    # Model 2: Google Gemini 3.1 Flash Lite
    if config.GEMINI_API_KEY:
        def call_gemini(p):
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=config.GEMINI_API_KEY)
            resp = client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=p,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=1024)
                )
            )
            return resp.text.strip()
        model_callers["Gemini 3.1 Flash Lite"] = call_gemini

    # Model 3: Claude Haiku (or 3.5/3.7)
    if config.ANTHROPIC_API_KEY:
        def call_claude(p):
            from anthropic import Anthropic
            client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
            resp = client.messages.create(
                model=config.CLAUDE_MODEL if not config.CLAUDE_MODEL.startswith("deepseek/") else "claude-3-5-haiku-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": p}],
                timeout=45
            )
            return "".join(b.text for b in resp.content if b.type == "text").strip()
        model_callers["Claude Haiku"] = call_claude

    # Model 4: DeepSeek V4 Flash / Chat
    if config.DEEPSEEK_API_KEY:
        def call_deepseek(p):
            from openai import OpenAI
            client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_API_BASE)
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a professional quantitative financial analyst."},
                    {"role": "user", "content": p}
                ],
                timeout=45
            )
            return resp.choices[0].message.content.strip()
        model_callers["DeepSeek V4 Flash"] = call_deepseek

    # 5. Execute in Parallel
    results = {}
    with ThreadPoolExecutor(max_workers=len(model_callers)) as executor:
        future_to_model = {
            executor.submit(_query_model_safe, name, fn, full_benchmark_prompt): name
            for name, fn in model_callers.items()
        }
        for future in as_completed(future_to_model):
            res = future.result()
            results[res["model"]] = res
            status_icon = "SUCCESS" if res["success"] else "FAILED"
            print(f"  [+] {res['model']:<25} -> {status_icon} (Latency: {res['latency']:.2f}s)")

    # 6. Save Full Report to Markdown
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(config.DATA_DIR, f"benchmark_{trade_sym}_{timestamp_str}.md")
    
    report_md = f"# 🧠 LLM Market Intelligence Benchmark Report\n\n"
    report_md += f"- **Symbol**: `{trade_sym}`\n"
    report_md += f"- **Time**: `{datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB')}`\n"
    report_md += f"- **Current Price**: Bid `{tick.bid}` | Ask `{tick.ask}`\n\n"
    report_md += "---\n\n"

    for model_name, data in results.items():
        report_md += f"## 🤖 {model_name} (Latency: {data['latency']:.2f}s)\n\n"
        if data["success"]:
            report_md += f"{data['response']}\n\n"
        else:
            report_md += f"**ERROR**: `{data.get('error', 'Unknown')}`\n\n"
        report_md += "---\n\n"

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_md)

    print("\n" + "=" * 90)
    print(f"[*] Benchmark complete! Full detailed report saved to: {report_file}")
    print("=" * 90)

    # Print summary to terminal
    for model_name, data in results.items():
        print(f"\n{'#' * 40} {model_name.upper()} {'#' * 40}")
        if data["success"]:
            print(data["response"][:1500] + ("\n... [Truncated for terminal]" if len(data["response"]) > 1500 else ""))
        else:
            print(f"ERROR: {data.get('error')}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "EURNZD-ECNc"
    run_benchmark(target)
