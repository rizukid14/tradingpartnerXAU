"""
DeepSeek V4 Flash 13-Pair Universe Test
Evaluates DeepSeek's decisiveness across 13 symbols (6 in-pool, 6 out-of-pool, and Gold)
using Structured JSON Chain-of-Thought (macro_trend -> micro_velocity -> signal -> confidence).
"""

import os
import sys
import time
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from zoneinfo import ZoneInfo
from openai import OpenAI

# Add workspace root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from config import mt5
from src.core import mt5_connector as connector, llm_client as llm
from src.analytics.macro_analyst import analyst

WIB = ZoneInfo("Asia/Jakarta")

TEST_SYMBOLS = [
    # 6 In-Pool FX Pairs
    "GBPUSD-ECNc",
    "EURCHF-ECNc",
    "GBPCHF-ECNc",
    "EURNZD-ECNc",
    "NZDCAD-ECNc",
    "AUDCAD-ECNc",
    # 6 Outside-Pool FX Pairs
    "EURUSD-ECNc",
    "USDJPY-ECNc",
    "AUDUSD-ECNc",
    "GBPAUD-ECNc",
    "EURJPY-ECNc",
    "USDCAD-ECNc",
    # Gold
    "XAUUSD-ECNc"
]

STRUCTURED_COT_PROMPT_TEMPLATE = """{MARKET_DATA_BLOCK}

### REQUIRED JSON OUTPUT SCHEMA:
You MUST respond ONLY with a valid JSON object following this exact order of fields:
```json
{{
  "macro_trend": "BULLISH" | "BEARISH" | "RANGING",
  "micro_velocity": "HIGH_IMPULSE" | "MODERATE" | "SLOW_ORDERLY",
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0 to 1.0,
  "sl_points": integer,
  "tp_points": integer,
  "invalidation_price": float,
  "target_price": float,
  "reasoning": "Concise step-by-step logic from macro trend to micro velocity to execution"
}}
```
"""


def evaluate_single_symbol(symbol):
    t0 = time.time()
    trade_sym = connector.get_valid_trade_symbol(symbol)
    tf = config.get_timeframe(trade_sym)
    
    # 1. Fetch Market Data
    df = connector.get_market_data(trade_sym, tf, num_candles=100)
    if df is None or len(df) < 50:
        return {"symbol": symbol, "success": False, "error": "Market data fetch failed"}

    tick = mt5.symbol_info_tick(trade_sym)
    if not tick:
        return {"symbol": symbol, "success": False, "error": "Tick fetch failed"}

    s_info = mt5.symbol_info(trade_sym)
    point_size = s_info.point if s_info else 0.00001
    spread_pts = round((tick.ask - tick.bid) / point_size) if point_size > 0 else 0
    
    # 2. Macro context
    macro_ctx = analyst.get_macro_context(trade_sym)
    
    # 3. Build Prompt Payload
    prompt_payload = llm.prepare_prompt(
        symbol=trade_sym,
        df=df,
        current_tick={"bid": tick.bid, "ask": tick.ask, "point": point_size, "spread": spread_pts, "time": tick.time},
        macro_context=macro_ctx
    )
    
    # Strip any old output format
    if "### OUTPUT FORMAT" in prompt_payload:
        prompt_payload = prompt_payload.split("### OUTPUT FORMAT")[0]

    full_prompt = STRUCTURED_COT_PROMPT_TEMPLATE.format(MARKET_DATA_BLOCK=prompt_payload)

    # 4. Query DeepSeek V4 Flash
    try:
        client = OpenAI(api_key=config.DEEPSEEK_API_KEY, base_url=config.DEEPSEEK_API_BASE)
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a professional quantitative financial analyst. Always output strictly valid JSON matching the requested schema."},
                {"role": "user", "content": full_prompt}
            ],
            response_format={"type": "json_object"},
            timeout=50
        )
        content = resp.choices[0].message.content.strip()
        parsed = json.loads(content)
        elapsed = time.time() - t0
        return {
            "symbol": symbol,
            "success": True,
            "latency": elapsed,
            "data": parsed,
            "raw": content
        }
    except Exception as e:
        elapsed = time.time() - t0
        return {
            "symbol": symbol,
            "success": False,
            "latency": elapsed,
            "error": str(e)
        }


def main():
    print("=" * 100)
    print(f"  DEEPSEEK V4 FLASH 13-PAIR UNIVERSE TEST ({datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB')})")
    print("=" * 100)

    if not connector.init_mt5():
        print("[ERROR] MT5 init failed!")
        return

    print(f"[*] Starting parallel evaluation for {len(TEST_SYMBOLS)} symbols on DeepSeek V4 Flash...")
    
    results = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_to_sym = {executor.submit(evaluate_single_symbol, sym): sym for sym in TEST_SYMBOLS}
        for future in as_completed(future_to_sym):
            res = future.result()
            sym = res["symbol"]
            results[sym] = res
            if res["success"]:
                d = res["data"]
                sig = d.get("signal", "N/A")
                conf = d.get("confidence", 0.0)
                macro = d.get("macro_trend", "N/A")
                vel = d.get("micro_velocity", "N/A")
                print(f"  [+] {sym:<15} | Macro: {macro:<8} | Vel: {vel:<13} | Signal: {sig:<5} (Conf: {conf:.2f}) | {res['latency']:.2f}s")
            else:
                print(f"  [-] {sym:<15} | FAILED: {res.get('error')}")

    # Format Markdown Report
    report_file = os.path.join(config.DATA_DIR, f"deepseek_13_pairs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md")
    
    report_md = f"# 🚀 DeepSeek V4 Flash 13-Pair Universe Test Report\n\n"
    report_md += f"- **Time**: `{datetime.now(WIB).strftime('%Y-%m-%d %H:%M:%S WIB')}`\n"
    report_md += f"- **Model**: `deepseek-chat (V4 Flash)`\n"
    report_md += f"- **Prompt Innovation**: `Structured JSON Chain-of-Thought + Anti-Paralysis Directive`\n\n"
    
    report_md += "## 📊 Summary Table\n\n"
    report_md += "| No | Symbol | Pool Status | Macro Trend | Micro Velocity | Signal | Conf | SL (pts) | TP (pts) | R:R | Latency |\n"
    report_md += "|:--:|:-------|:-----------:|:-----------:|:--------------:|:------:|:----:|:--------:|:--------:|:---:|:-------:|\n"

    buy_count, sell_count, hold_count = 0, 0, 0

    for idx, sym in enumerate(TEST_SYMBOLS, 1):
        r = results.get(sym, {})
        pool_status = "In-Pool" if idx <= 6 else ("Gold" if sym.startswith("XAU") else "Out-Pool")
        if r.get("success"):
            d = r["data"]
            sig = d.get("signal", "N/A")
            if sig == "BUY": buy_count += 1
            elif sig == "SELL": sell_count += 1
            elif sig == "HOLD": hold_count += 1
            
            conf = d.get("confidence", 0.0)
            macro = d.get("macro_trend", "N/A")
            vel = d.get("micro_velocity", "N/A")
            sl = d.get("sl_points", 0)
            tp = d.get("tp_points", 0)
            rr = f"{tp/sl:.2f}" if sl and sl > 0 and tp else "N/A"
            lat = f"{r.get('latency', 0.0):.1f}s"
            
            sig_badge = f"**BUY**" if sig == "BUY" else (f"**SELL**" if sig == "SELL" else "HOLD")
            report_md += f"| {idx} | `{sym}` | {pool_status} | {macro} | {vel} | {sig_badge} | {conf:.2f} | {sl} | {tp} | {rr} | {lat} |\n"
        else:
            report_md += f"| {idx} | `{sym}` | {pool_status} | ERROR | ERROR | FAILED | - | - | - | - | - |\n"

    report_md += f"\n**Total Decisions**: 🟢 BUY: {buy_count} | 🔴 SELL: {sell_count} | ⚪ HOLD: {hold_count}\n\n"
    report_md += "---\n\n## 📝 Detailed Model Reasoning per Symbol\n\n"

    for sym in TEST_SYMBOLS:
        r = results.get(sym, {})
        if r.get("success"):
            d = r["data"]
            report_md += f"### 📌 {sym}\n"
            report_md += f"- **Decision**: `{d.get('signal')}` (Confidence: `{d.get('confidence')}`)\n"
            report_md += f"- **Macro Trend**: `{d.get('macro_trend')}` | **Micro Velocity**: `{d.get('micro_velocity')}`\n"
            report_md += f"- **Invalidation (SL)**: `{d.get('sl_points')} pts` (`{d.get('invalidation_price')}`) | **Target (TP)**: `{d.get('tp_points')} pts` (`{d.get('target_price')}`)\n"
            report_md += f"- **Reasoning**: {d.get('reasoning')}\n\n"

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_md)

    print("\n" + "=" * 100)
    print(f"[*] Benchmark Complete! Results saved to: {report_file}")
    print(f"[*] Summary: BUY: {buy_count} | SELL: {sell_count} | HOLD: {hold_count}")
    print("=" * 100)


if __name__ == "__main__":
    main()
