"""
Benchmark comparison: Format A (Full Sentence Analyst) vs Format B (High-Density Enum Analyst)
Evaluates latency, token length, signal quality, confidence, and analysis paralysis across
OpenAI o4-mini, Gemini 3.1 Flash Lite, and DeepSeek V4 Flash on all 6 Pool pairs + Gold.
"""

import os
import sys
import time
import json
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from src.core import mt5_connector as mt5_conn
from src.core import llm_client as llm
from src.analytics.macro_analyst import analyst

WIB = ZoneInfo("Asia/Jakarta")

SYMBOLS = [
    "GBPUSD-ECNc",
    "EURCHF-ECNc",
    "GBPCHF-ECNc",
    "EURNZD-ECNc",
    "NZDCAD-ECNc",
    "AUDCAD-ECNc",
    "XAUUSD-ECNc"
]

FORMAT_A_SCHEMA = """### OUTPUT FORMAT (ANALYST GRADE - MANDATORY EXECUTION PROTOCOL)
Respond ONLY with a valid JSON object matching this exact schema:
{
  "step_1_macro_trend_eval": "1 concise sentence evaluating whether H4/D1 trend supports or opposes an entry.",
  "step_2_velocity_and_session": "1 concise sentence evaluating if M5/H1 candle speed and session timing are safe from anomalies.",
  "step_3_key_level_proximity": "1 concise sentence stating the exact distance to nearest Support and Resistance levels.",
  "step_4_risk_reward_verdict": "1 concise sentence evaluating if available runway to target justifies the SL distance (>= 1.25 R:R).",
  "final_signal": "BUY" | "SELL" | "HOLD",
  "confidence_score": 0.0 to 1.0,
  "entry_type": "market" | "buy_stop" | "sell_stop" | "buy_limit" | "sell_limit",
  "entry_price": 1.23456 | null,
  "sl_points": 250,
  "tp_points": 350,
  "invalidation_price": 1.23000 | null,
  "target_price": 1.24000 | null,
  "one_sentence_summary": "1 concise sentence summarizing the structural trade thesis."
}"""

FORMAT_B_SCHEMA = """### OUTPUT FORMAT (HIGH-DENSITY ANALYST PROTOCOL)
Respond ONLY with a valid JSON object matching this exact schema:
{
  "step_1_macro_trend": "BULLISH" | "BEARISH" | "RANGING",
  "step_2_micro_velocity": "HIGH_IMPULSE" | "MODERATE" | "SLOW_ORDERLY",
  "step_3_key_level_proximity": "CLEAR_SPACE" | "NEAR_SUPPORT_TRAP" | "NEAR_RESISTANCE_TRAP",
  "step_4_risk_reward_verdict": "FAVORABLE_GT_1_25" | "POOR_RR",
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0 to 1.0,
  "entry_type": "market" | "buy_stop" | "sell_stop" | "buy_limit" | "sell_limit",
  "entry_price": 1.23456 | null,
  "sl_points": 250,
  "tp_points": 350,
  "invalidation_price": 1.23000 | null,
  "target_price": 1.24000 | null,
  "reasoning": "1 concise sentence explaining the structural thesis."
}"""

def build_prompt_with_schema(raw_prompt, new_schema):
    if "### OUTPUT FORMAT" in raw_prompt and "### MARKET DATA CONTEXT" in raw_prompt:
        start_idx = raw_prompt.find("### OUTPUT FORMAT")
        end_idx = raw_prompt.find("### MARKET DATA CONTEXT")
        return raw_prompt[:start_idx] + new_schema + "\n\n" + raw_prompt[end_idx:]
    return raw_prompt + "\n\n" + new_schema

from openai import OpenAI
from google import genai
from google.genai import types

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
    api_key = getattr(config, "DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY"))
    base_url = getattr(config, "DEEPSEEK_API_BASE", os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com"))
    model = getattr(config, "DEEPSEEK_MODEL", "deepseek-chat")
    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a professional financial trading assistant. Respond strictly with valid JSON."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        timeout=55
    )
    return json.loads(resp.choices[0].message.content.strip())

def evaluate_model_sync(model_family, prompt, symbol):
    start_t = time.time()
    try:
        if model_family == "openai":
            res = _query_openai(prompt)
        elif model_family == "gemini":
            res = _query_gemini(prompt)
        elif model_family == "deepseek":
            res = _query_deepseek(prompt)
        else:
            res = {"signal": "HOLD", "confidence": 0.0, "reasoning": "Unknown model"}
            
        elapsed = time.time() - start_t
        
        # Normalize fields for Format A vs B
        signal = res.get("signal") or res.get("final_signal") or "HOLD"
        conf = res.get("confidence") if "confidence" in res else res.get("confidence_score", 0.0)
        sl = res.get("sl_points")
        tp = res.get("tp_points")
        reasoning = res.get("reasoning") or res.get("one_sentence_summary") or ""
        
        return {
            "signal": signal,
            "confidence": float(conf) if conf is not None else 0.0,
            "sl_points": sl,
            "tp_points": tp,
            "elapsed_seconds": round(elapsed, 2),
            "reasoning": reasoning,
            "raw_response": res
        }
    except Exception as e:
        elapsed = time.time() - start_t
        return {
            "signal": "ERROR",
            "confidence": 0.0,
            "sl_points": None,
            "tp_points": None,
            "elapsed_seconds": round(elapsed, 2),
            "reasoning": f"Exception: {str(e)}",
            "raw_response": {}
        }

async def run_benchmark():
    now_wib = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB")
    print("=" * 100)
    print(f"  FORMAT A (FULL SENTENCE) vs FORMAT B (HIGH-DENSITY ENUM) BENCHMARK ({now_wib})")
    print("=" * 100)

    if not mt5_conn.init_mt5():
        print("[ERROR] MT5 init failed!")
        return

    from config import mt5
    print("[*] Fetching MT5 market data & constructing prompts for all symbols...")
    symbol_data = {}
    for sym in SYMBOLS:
        trade_sym = mt5_conn.get_valid_trade_symbol(sym)
        tf = config.get_timeframe(trade_sym)
        df = mt5_conn.get_market_data(trade_sym, tf, num_candles=100)
        tick = mt5.symbol_info_tick(trade_sym)
        s_info = mt5.symbol_info(trade_sym)
        
        if tick is None or df is None or len(df) == 0:
            print(f"[-] Failed to fetch data for {trade_sym}")
            continue
            
        point_size = s_info.point if s_info else 0.00001
        spread_pts = int(round((tick.ask - tick.bid) / point_size)) if point_size > 0 else 0
        macro_ctx = analyst.get_macro_context(trade_sym)
        
        raw_prompt = llm.prepare_prompt(
            symbol=trade_sym,
            df=df,
            current_tick={"bid": tick.bid, "ask": tick.ask, "point": point_size, "spread": spread_pts, "time": tick.time},
            macro_context=macro_ctx
        )
        
        prompt_A = build_prompt_with_schema(raw_prompt, FORMAT_A_SCHEMA)
        prompt_B = build_prompt_with_schema(raw_prompt, FORMAT_B_SCHEMA)
        
        symbol_data[sym] = {
            "trade_sym": trade_sym,
            "prompt_A": prompt_A,
            "prompt_B": prompt_B
        }

    print(f"[*] Prepared prompts for {len(symbol_data)} symbols.")
    print("[*] Launching 42 parallel evaluations (7 symbols x 3 models x 2 formats)...")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    eval_jobs = []
    models = ["openai", "gemini", "deepseek"]
    formats = [("format_A", "prompt_A"), ("format_B", "prompt_B")]
    
    for sym, data in symbol_data.items():
        for mod in models:
            for fmt_name, prompt_key in formats:
                eval_jobs.append((sym, mod, fmt_name, data[prompt_key]))

    eval_matrix = {}
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_map = {
            executor.submit(evaluate_model_sync, mod, prompt, sym): (sym, mod, fmt_name)
            for sym, mod, fmt_name, prompt in eval_jobs
        }
        for fut in as_completed(future_map):
            sym, mod, fmt_name = future_map[fut]
            try:
                res = fut.result()
            except Exception as e:
                res = {"signal": "ERROR", "confidence": 0.0, "sl_points": None, "tp_points": None, "elapsed_seconds": 0.0, "reasoning": str(e), "raw_response": {}}
                
            if sym not in eval_matrix:
                eval_matrix[sym] = {}
            if mod not in eval_matrix[sym]:
                eval_matrix[sym][mod] = {}
            eval_matrix[sym][mod][fmt_name] = res
            
            sig_str = res["signal"].ljust(4)
            conf_str = f"{res['confidence']:.2f}"
            elap_str = f"{res['elapsed_seconds']:.1f}s"
            print(f"  [+] {sym:<12} | {mod:<8} | {fmt_name:<8} -> {sig_str} (Conf: {conf_str}, {elap_str})")

    # Generate Markdown Report
    timestamp_slug = datetime.now(WIB).strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(os.path.dirname(__file__), "..", "data", f"analyst_format_benchmark_{timestamp_slug}.md")
    
    lines = [
        "# 🧪 Benchmark: Format A (Full Sentence) vs Format B (High-Density Enum)",
        f"- **Waktu**: `{now_wib}`",
        "- **Tujuan**: Menguji apakah 4 kalimat evaluasi lengkap (Format A) memperkuat atau melumpuhkan keputusan dibanding 4 enum padat (Format B).",
        "",
        "## 📊 Tabel Komparasi Latensi & Keputusan",
        "",
        "| Simbol | Model | Format A (Full Sentence) | Latensi A | Format B (High-Density Enum) | Latensi B | Delta Waktu |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|"
    ]
    
    for sym in SYMBOLS:
        if sym not in eval_matrix:
            continue
        for mod in models:
            resA = eval_matrix[sym][mod]["format_A"]
            resB = eval_matrix[sym][mod]["format_B"]
            
            def fmt_cell(r):
                sig = r["signal"]
                conf = r["confidence"]
                sl = r.get("sl_points")
                tp = r.get("tp_points")
                if sig == "BUY":
                    badge = f"🟢 **BUY** ({conf:.2f})"
                elif sig == "SELL":
                    badge = f"🔴 **SELL** ({conf:.2f})"
                else:
                    badge = f"⚪ HOLD ({conf:.2f})"
                if sl and tp:
                    rr = round(tp / sl, 2) if sl > 0 else 0
                    badge += f"<br><small>SL:{sl} TP:{tp} (R:R {rr})</small>"
                return badge
                
            cellA = fmt_cell(resA)
            cellB = fmt_cell(resB)
            latA = f"{resA['elapsed_seconds']}s"
            latB = f"{resB['elapsed_seconds']}s"
            delta = f"{round(resA['elapsed_seconds'] - resB['elapsed_seconds'], 1):+0.1f}s"
            
            lines.append(f"| `{sym}` | **{mod.upper()}** | {cellA} | {latA} | {cellB} | {latB} | {delta} |")

    lines.append("\n---\n")
    lines.append("## 📝 Rincian Output & Reasoning per Simbol\n")
    
    for sym in SYMBOLS:
        if sym not in eval_matrix:
            continue
        lines.append(f"### 📌 `{sym}`\n")
        for mod in models:
            lines.append(f"#### 🔹 {mod.upper()}\n")
            resA = eval_matrix[sym][mod]["format_A"]
            resB = eval_matrix[sym][mod]["format_B"]
            
            lines.append(f"**Format A (Full Sentence)** ({resA['elapsed_seconds']}s):")
            lines.append(f"- **Signal**: `{resA['signal']}` | **Confidence**: `{resA['confidence']}`")
            lines.append(f"- **Raw Output**:\n```json\n{json.dumps(resA['raw_response'], indent=2)}\n```\n")
            
            lines.append(f"**Format B (High-Density Enum)** ({resB['elapsed_seconds']}s):")
            lines.append(f"- **Signal**: `{resB['signal']}` | **Confidence**: `{resB['confidence']}`")
            lines.append(f"- **Raw Output**:\n```json\n{json.dumps(resB['raw_response'], indent=2)}\n```\n")

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print("=" * 100)
    print(f"[*] Benchmark Complete! Results saved to: {report_path}")
    print("=" * 100)

if __name__ == "__main__":
    asyncio.run(run_benchmark())
