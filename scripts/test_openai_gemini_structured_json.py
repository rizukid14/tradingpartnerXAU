"""
OpenAI & Gemini Structured JSON Benchmark
Evaluates whether replacing the JSON output schema with Structured JSON Chain-of-Thought
(macro_trend -> micro_velocity -> signal -> confidence) changes or improves the behavior
of OpenAI o4-mini and Gemini 3.1 Flash Lite across the 6 Pool Pairs + Gold.
"""

import os
import sys
import time
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo
from openai import OpenAI
from google import genai
from google.genai import types

# Add workspace root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from config import mt5
from src.core import mt5_connector as connector, llm_client as llm
from src.analytics.macro_analyst import analyst

WIB = ZoneInfo("Asia/Jakarta")

TEST_SYMBOLS = [
    "GBPUSD-ECNc",
    "EURCHF-ECNc",
    "GBPCHF-ECNc",
    "EURNZD-ECNc",
    "NZDCAD-ECNc",
    "AUDCAD-ECNc",
    "XAUUSD-ECNc"
]

STRUCTURED_JSON_SCHEMA = """
### REQUIRED JSON OUTPUT SCHEMA:
You MUST respond ONLY with a valid JSON object following this exact order of fields:
```json
{
  "macro_trend": "BULLISH" | "BEARISH" | "RANGING",
  "micro_velocity": "HIGH_IMPULSE" | "MODERATE" | "SLOW_ORDERLY",
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0 to 1.0,
  "sl_points": integer,
  "tp_points": integer,
  "invalidation_price": float,
  "target_price": float,
  "reasoning": "Concise step-by-step logic from macro trend to micro velocity to execution"
}
```
"""


def _query_openai(prompt):
    client = OpenAI(api_key=config.OPENAI_API_KEY, base_url=config.OPENAI_API_BASE)
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": "You are a professional financial trading assistant. Respond strictly with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        timeout=55
    )
    return json.loads(resp.choices[0].message.content.strip())


def _query_gemini(prompt):
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    resp = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_budget=1024)
        )
    )
    return json.loads(resp.text.strip())


def run_test():
    print("=" * 100)
    print(f"  OPENAI & GEMINI STRUCTURED JSON BENCHMARK ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB')})")
    print("=" * 100)

    if not connector.init_mt5():
        print("[ERROR] MT5 init failed!")
        return

    # Prepare market data and prompts for all symbols
    symbol_data = {}
    print("[*] Fetching MT5 market data & constructing prompts...")
    for sym in TEST_SYMBOLS:
        trade_sym = connector.get_valid_trade_symbol(sym)
        tf = config.get_timeframe(trade_sym)
        df = connector.get_market_data(trade_sym, tf, num_candles=100)
        tick = mt5.symbol_info_tick(trade_sym)
        s_info = mt5.symbol_info(trade_sym)
        point_size = s_info.point if s_info else 0.00001
        spread_pts = round((tick.ask - tick.bid) / point_size) if point_size > 0 else 0
        macro_ctx = analyst.get_macro_context(trade_sym)
        
        raw_prompt = llm.prepare_prompt(
            symbol=trade_sym,
            df=df,
            current_tick={"bid": tick.bid, "ask": tick.ask, "point": point_size, "spread": spread_pts, "time": tick.time},
            macro_context=macro_ctx
        )
        
        # Replace the default JSON output schema with Structured JSON schema cleanly
        if "### OUTPUT FORMAT" in raw_prompt and "### MARKET DATA CONTEXT" in raw_prompt:
            start_idx = raw_prompt.find("### OUTPUT FORMAT")
            end_idx = raw_prompt.find("### MARKET DATA CONTEXT")
            struct_prompt = raw_prompt[:start_idx] + STRUCTURED_JSON_SCHEMA + "\n\n" + raw_prompt[end_idx:]
        else:
            struct_prompt = raw_prompt + "\n\n" + STRUCTURED_JSON_SCHEMA

        symbol_data[sym] = {
            "trade_sym": trade_sym,
            "raw_prompt": raw_prompt,
            "struct_prompt": struct_prompt
        }

    # 4 Evaluator Configurations:
    # 1. OpenAI (Original Prompt)
    # 2. OpenAI (Structured JSON - No Directive)
    # 3. Gemini (Original Prompt)
    # 4. Gemini (Structured JSON - No Directive)
    eval_configs = [
        {"id": "openai_orig", "name": "OpenAI (Original)", "fn": _query_openai, "prompt_key": "raw_prompt"},
        {"id": "openai_struct", "name": "OpenAI (Structured JSON)", "fn": _query_openai, "prompt_key": "struct_prompt"},
        {"id": "gemini_orig", "name": "Gemini (Original)", "fn": _query_gemini, "prompt_key": "raw_prompt"},
        {"id": "gemini_struct", "name": "Gemini (Structured JSON)", "fn": _query_gemini, "prompt_key": "struct_prompt"},
    ]

    results = {sym: {} for sym in TEST_SYMBOLS}
    tasks = []

    def _eval(sym, cfg):
        t0 = time.time()
        p = symbol_data[sym][cfg["prompt_key"]]
        try:
            res = cfg["fn"](p)
            elapsed = time.time() - t0
            return (sym, cfg["id"], True, elapsed, res)
        except Exception as e:
            elapsed = time.time() - t0
            return (sym, cfg["id"], False, elapsed, str(e))

    print(f"[*] Executing 28 evaluations (7 symbols x 4 configs) in parallel...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        for sym in TEST_SYMBOLS:
            for cfg in eval_configs:
                tasks.append(executor.submit(_eval, sym, cfg))

        for fut in as_completed(tasks):
            sym, cid, ok, el, res = fut.result()
            results[sym][cid] = {"success": ok, "latency": el, "data": res}
            sig = res.get("signal", "ERR") if ok and isinstance(res, dict) else "FAIL"
            conf = res.get("confidence", 0.0) if ok and isinstance(res, dict) else 0.0
            print(f"  [+] {sym:<12} | {cid:<22} -> {sig:<5} (Conf: {conf:.2f}, {el:.1f}s)")

    # Generate Markdown Report
    report_file = os.path.join(config.DATA_DIR, f"openai_gemini_struct_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
    
    md = f"# 🧪 OpenAI & Gemini: Original vs Structured JSON Benchmark\n\n"
    md += f"- **Time**: `{datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB')}`\n"
    md += f"- **Objective**: Determine if Structured JSON Chain-of-Thought (without directive) improves or alters decision quality for OpenAI o4-mini and Gemini 3.1 Flash Lite.\n\n"

    md += "## 📊 Comparative Summary Table\n\n"
    md += "| Symbol | OpenAI (Original) | OpenAI (Structured JSON) | Gemini (Original) | Gemini (Structured JSON) |\n"
    md += "|:-------|:-----------------:|:------------------------:|:-----------------:|:------------------------:|\n"

    def _fmt_cell(cell):
        if not cell.get("success"):
            return "❌ FAIL"
        d = cell["data"]
        sig = d.get("signal", "N/A")
        conf = d.get("confidence", 0.0)
        sl = d.get("sl_points", 0)
        tp = d.get("tp_points", 0)
        
        if sig == "BUY":
            badge = f"🟢 **BUY** ({conf:.2f})"
        elif sig == "SELL":
            badge = f"🔴 **SELL** ({conf:.2f})"
        else:
            badge = f"⚪ HOLD ({conf:.2f})"
            
        if sig in ("BUY", "SELL") and sl and tp:
            badge += f"<br><small>SL:{sl} TP:{tp} (R:R {tp/sl:.2f})</small>"
        return badge

    for sym in TEST_SYMBOLS:
        row = results[sym]
        c1 = _fmt_cell(row.get("openai_orig", {}))
        c2 = _fmt_cell(row.get("openai_struct", {}))
        c3 = _fmt_cell(row.get("gemini_orig", {}))
        c4 = _fmt_cell(row.get("gemini_struct", {}))
        md += f"| `{sym}` | {c1} | {c2} | {c3} | {c4} |\n"

    md += "\n---\n\n## 📝 Detailed Reasoning per Symbol\n\n"
    for sym in TEST_SYMBOLS:
        md += f"### 📌 `{sym}`\n\n"
        for cfg in eval_configs:
            cid = cfg["id"]
            cell = results[sym].get(cid, {})
            md += f"#### 🔹 {cfg['name']} ({cell.get('latency', 0):.1f}s)\n"
            if cell.get("success"):
                d = cell["data"]
                md += f"- **Signal**: `{d.get('signal')}` | **Confidence**: `{d.get('confidence')}`\n"
                if "macro_trend" in d:
                    md += f"- **Macro Trend**: `{d.get('macro_trend')}` | **Micro Velocity**: `{d.get('micro_velocity')}`\n"
                md += f"- **Reasoning**: {d.get('reasoning')}\n\n"
            else:
                md += f"- **Error**: `{cell.get('data')}`\n\n"

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(md)

    print("\n" + "=" * 100)
    print(f"[*] Benchmark Complete! Results saved to: {report_file}")
    print("=" * 100)


if __name__ == "__main__":
    run_test()
