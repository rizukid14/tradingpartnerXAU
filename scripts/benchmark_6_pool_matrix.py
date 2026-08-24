"""
6-Pool Matrix Benchmark
Compares OpenAI (Original), Gemini (Original), and 4 DeepSeek Variants across the 6 Pool Pairs.
Variants:
1. OpenAI o4-mini (Prompt Original)
2. Gemini 3.1 Flash Lite (Prompt Original)
3. DeepSeek (Prompt Original)
4. DeepSeek (Directive + JSON Lama)
5. DeepSeek (Tanpa Directive + Structured JSON)
6. DeepSeek (Directive + Structured JSON)
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

POOL_SYMBOLS = [
    "GBPUSD-ECNc",
    "EURCHF-ECNc",
    "GBPCHF-ECNc",
    "EURNZD-ECNc",
    "NZDCAD-ECNc",
    "AUDCAD-ECNc"
]

ANTI_PARALYSIS_DIRECTIVE = """
================================================================================
CRITICAL EXECUTION & ANTI-PARALYSIS DIRECTIVE:
================================================================================
1. Probabilistic Edge over Perfection: In live financial markets, a 100% "perfect" textbook setup does not exist. Micro-timeframe pullbacks (M5/M15 noise) are a NATURAL part of healthy trends.
2. Dominant Flow Priority: When the Macro Trend (H4/D1) is clear and price is aligned with institutional structure (below/above EMA200), do NOT allow minor micro-consolidation to paralyze your decision into a passive HOLD.
3. Asymmetric R:R Mandate: If a clean structural invalidation level exists behind recent structure providing a favorable R:R >= 1.25:1 in the direction of the macro trend, take the actionable trade (BUY/SELL) with conviction.
4. Reserve HOLD Strictly for True Chop: Use HOLD ONLY when the market is genuinely trapped in an ambiguous multi-day range with no directional HTF slope, or when price is in an immediate trap zone (e.g., directly into major support without room).
"""

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

OLD_JSON_SCHEMA = """
### REQUIRED JSON OUTPUT SCHEMA:
Respond ONLY with a valid JSON object matching this schema:
```json
{
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0 to 1.0,
  "sl_points": integer,
  "tp_points": integer,
  "invalidation_price": float,
  "target_price": float,
  "reasoning": "Concise justification for your signal and key levels."
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


def _query_deepseek(prompt):
    client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_API_BASE)
    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "You are a professional financial trading assistant. Respond strictly with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        timeout=50
    )
    return json.loads(resp.choices[0].message.content.strip())


def run_benchmark_matrix():
    print("=" * 100)
    print(f"  6-POOL PAIR COMPREHENSIVE MATRIX BENCHMARK ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB')})")
    print("=" * 100)

    if not connector.init_mt5():
        print("[ERROR] MT5 init failed!")
        return

    # Prepare market data and base prompt for all 6 symbols
    symbol_data = {}
    print("[*] Fetching MT5 data & constructing prompts for 6 pool pairs...")
    for sym in POOL_SYMBOLS:
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
        
        base_clean = raw_prompt.split("### OUTPUT FORMAT")[0] if "### OUTPUT FORMAT" in raw_prompt else raw_prompt

        symbol_data[sym] = {
            "trade_sym": trade_sym,
            "raw_prompt": raw_prompt,
            "base_clean": base_clean
        }

    # Define the 6 Test Configurations
    configs = [
        {"id": "openai_orig", "name": "OpenAI o4-mini (Original)", "fn": _query_openai, "type": "orig"},
        {"id": "gemini_orig", "name": "Gemini 3.1-Flash (Original)", "fn": _query_gemini, "type": "orig"},
        {"id": "deepseek_orig", "name": "DeepSeek (Prompt Original)", "fn": _query_deepseek, "type": "orig"},
        {"id": "deepseek_dir_oldjson", "name": "DeepSeek (Directive + JSON Lama)", "fn": _query_deepseek, "type": "dir_oldjson"},
        {"id": "deepseek_nodir_structjson", "name": "DeepSeek (No Directive + Structured JSON)", "fn": _query_deepseek, "type": "nodir_structjson"},
        {"id": "deepseek_dir_structjson", "name": "DeepSeek (Directive + Structured JSON)", "fn": _query_deepseek, "type": "dir_structjson"},
    ]

    # Run tasks in parallel
    matrix_results = {sym: {} for sym in POOL_SYMBOLS}
    tasks = []

    def _eval(sym, cfg):
        t0 = time.time()
        sdata = symbol_data[sym]
        if cfg["type"] == "orig":
            p = sdata["raw_prompt"]
        elif cfg["type"] == "dir_oldjson":
            p = sdata["base_clean"] + "\n" + ANTI_PARALYSIS_DIRECTIVE + "\n" + OLD_JSON_SCHEMA
        elif cfg["type"] == "nodir_structjson":
            p = sdata["base_clean"] + "\n" + STRUCTURED_JSON_SCHEMA
        elif cfg["type"] == "dir_structjson":
            p = sdata["base_clean"] + "\n" + ANTI_PARALYSIS_DIRECTIVE + "\n" + STRUCTURED_JSON_SCHEMA

        try:
            res = cfg["fn"](p)
            elapsed = time.time() - t0
            return (sym, cfg["id"], True, elapsed, res)
        except Exception as e:
            elapsed = time.time() - t0
            return (sym, cfg["id"], False, elapsed, str(e))

    print(f"[*] Executing 36 evaluations (6 pairs x 6 configurations) in parallel...")
    with ThreadPoolExecutor(max_workers=12) as executor:
        for sym in POOL_SYMBOLS:
            for cfg in configs:
                tasks.append(executor.submit(_eval, sym, cfg))

        for fut in as_completed(tasks):
            sym, cid, ok, el, res = fut.result()
            matrix_results[sym][cid] = {"success": ok, "latency": el, "data": res}
            sig = res.get("signal", "ERR") if ok and isinstance(res, dict) else "FAIL"
            conf = res.get("confidence", 0.0) if ok and isinstance(res, dict) else 0.0
            print(f"  [+] {sym:<12} | {cid:<26} -> {sig:<5} (Conf: {conf:.2f}, {el:.1f}s)")

    # Save to Markdown Report
    report_file = os.path.join(config.DATA_DIR, f"matrix_benchmark_6_pool_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
    
    md = f"# 🧪 6-Pool Pair Comprehensive Matrix Benchmark Report\n\n"
    md += f"- **Time**: `{datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB')}`\n"
    md += f"- **Objective**: Compare OpenAI, Gemini, and 4 DeepSeek prompt variants on live market data.\n\n"

    md += "## 📊 Master Decision Matrix\n\n"
    md += "| Symbol | OpenAI (Orig) | Gemini (Orig) | DeepSeek (Orig) | DeepSeek (Dir + Old JSON) | DeepSeek (No Dir + Struct JSON) | DeepSeek (Dir + Struct JSON) |\n"
    md += "|:-------|:-------------:|:-------------:|:---------------:|:-------------------------:|:-------------------------------:|:----------------------------:|\n"

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

    for sym in POOL_SYMBOLS:
        row = matrix_results[sym]
        c1 = _fmt_cell(row.get("openai_orig", {}))
        c2 = _fmt_cell(row.get("gemini_orig", {}))
        c3 = _fmt_cell(row.get("deepseek_orig", {}))
        c4 = _fmt_cell(row.get("deepseek_dir_oldjson", {}))
        c5 = _fmt_cell(row.get("deepseek_nodir_structjson", {}))
        c6 = _fmt_cell(row.get("deepseek_dir_structjson", {}))
        md += f"| `{sym}` | {c1} | {c2} | {c3} | {c4} | {c5} | {c6} |\n"

    md += "\n---\n\n## 📝 Detailed Reasoning per Symbol & Configuration\n\n"
    for sym in POOL_SYMBOLS:
        md += f"### 📌 `{sym}`\n\n"
        for cfg in configs:
            cid = cfg["id"]
            cell = matrix_results[sym].get(cid, {})
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
    print(f"[*] Benchmark Complete! Master matrix saved to: {report_file}")
    print("=" * 100)


if __name__ == "__main__":
    run_benchmark_matrix()
