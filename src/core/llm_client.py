import json
import re
import time
import sys
import threading
import concurrent.futures
from openai import OpenAI
from google import genai
import config
from src.core.cli_theme import UI

# Regex untuk menghapus emoji dari prompt yang dikirim ke LLM.
# User requirement: prompt LLM harus bebas emoji (UI/CLI boleh).
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F000-\U0001F02F"   # Mahjong tiles
    "\U0001F0A0-\U0001F0FF"   # Playing cards
    "\U0001F100-\U0001F64F"   # Enclosed alnum + emoticons
    "\U0001F680-\U0001F6FF"   # Transport & map symbols
    "\U0001F900-\U0001F9FF"   # Supplemental symbols & pictographs
    "\U0001FA70-\U0001FAFF"   # Symbols & pictographs extended-A
    "\U00002600-\U000027BF"   # Misc symbols + dingbats
    "\U00002B00-\U00002BFF"   # Misc symbols & arrows
    "\U0000FE0F"              # Variation selector-16 (emoji presentation)
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    """Remove all emoji characters from a string (used on LLM prompt content)."""
    if not text:
        return text
    return _EMOJI_PATTERN.sub("", text)


# Initialize clients if keys are present
openai_client = None
if config.OPENAI_API_KEY:
    openai_client = OpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_API_BASE
    )

# DeepSeek is OpenAI-compatible - same SDK, different base URL. Used when
# CLAUDE_MODEL starts with "deepseek/" (cheap default; switch back to Claude
# by setting CLAUDE_MODEL to "claude-...").
deepseek_client = None
if config.DEEPSEEK_API_KEY:
    try:
        deepseek_client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_API_BASE,
            max_retries=0,
            timeout=getattr(config, "LLM_TIMEOUT_SECONDS", 25.0)
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
    """Human-readable asset description for prompts (Gold vs Bitcoin vs FX)."""
    if config.is_crypto(symbol):
        return "Bitcoin (BTCUSD) - crypto, trades 24/7 including weekends"
    elif "XAU" in (symbol or "").upper():
        return "Gold (XAUUSD) - spot metal / commodity"
    else:
        return f"Forex Currency Pair ({symbol})"


def claude_slot_label():
    """Display label for the 'Claude slot' model. Delegates to config
    (single source of truth)."""
    return config.claude_slot_label()


def query_primary_model(prompt, search_grounding=False):
    """
    Queries a single model for background analysis (post-mortem, MTF, lessons
    summary). Primary = OpenAI gpt-5.4-mini (free tier), then Gemini, then
    Claude. Search grounding (Google Search) is only supported on Gemini,
    so it forces the Gemini branch when enabled.
    """
    # 1. Try OpenAI (primary - gpt-5.4-mini, free tier)
    if openai_client and config.OPENAI_API_KEY and not search_grounding:
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


def analyze_fundamentals(symbol):
    """
    Queries Gemini using Google Search Grounding to summarize the latest
    macroeconomic SENTIMENT affecting the asset (news, outlook, positioning).
    Event SCHEDULING is handled deterministically by economic_calendar.py -
    search grounding is only a qualitative complement, never the schedule source.
    """
    if config.is_crypto(symbol):
        execution_style = "30-minute intraday (M30) swing"
    elif "XAU" not in symbol.upper():
        execution_style = "1-hour (H1) swing"
    else:
        execution_style = "30-minute (M30) swing"
    prompt = f"""
What is the latest macroeconomic news and market sentiment affecting {symbol} ({asset_desc(symbol)}) prices right now?
Summarize the main themes, current market sentiment, and any notable macro drivers (central bank policy expectations, geopolitical risk, dollar/yield moves, commodity flows, or crypto-specific factors like ETF flows or regulatory news).

Your response must be extremely brief (maximum 3-4 sentences) as it will be used as background context for a {execution_style} execution model. Focus on DIRECTIONAL macro bias, not event schedules.
"""
    # Force search grounding tool
    return query_primary_model(prompt, search_grounding=True)


# ================================================================
# SYSTEM PROMPT TEMPLATE (docs/prompt_claude.md)
# "We set guardrails, the LLM sets strategy."
# Static per-bot constitution - build once per instance, reuse across
# cycles so provider-side prompt/context caching stays effective.
# ================================================================
_SYSTEM_PROMPT_TEMPLATE = """### ROLE
You are an expert {{TIMEFRAME}} short-term intraday-swing analyst for {{SYMBOL}} -- {{ASSET_DESC}}. Your job is to find a high-quality short-term trading opportunity directly from the market data given each cycle, or to conclude that no valid opportunity currently exists.

### EXECUTION CONTEXT
{{EXECUTION_NOTE}}
Please ensure your setup is actionable either at the current price (Market Order) OR at a specified trigger level (Pending Order: buy_stop/sell_stop/buy_limit/sell_limit with entry_price). If your thesis relies on a breakout or pullback trigger that has not triggered yet, use the appropriate pending order entry_type and entry_price, or select HOLD if conviction is low.

### ANALYSIS FREEDOM
You are NOT required to follow a single predefined trading strategy. You may use any market interpretation you judge relevant, including but not limited to: trend following, momentum, breakout, pullback, mean reversion, reversal/exhaustion, support/resistance, price action, volatility, or indicator confluence -- alone or combined.

Pick the interpretation you believe currently has the strongest expected edge. State what creates that edge and what would invalidate it. Do not force a trade into a fixed template just to produce a signal.

Do not treat any single indicator (RSI, EMA, Fibonacci, ATR) as a mandatory trigger or a mandatory block. They are inputs for your own judgment, not rules you must obey.

### DATA INTEGRITY
Only use indicators and values explicitly provided below. Do not reference or estimate data that isn't given (for example: if no VWAP is provided, do not assume or invent one).

The MULTI-TIMEFRAME ANALYSIS note is COMPUTED from actual higher-timeframe candles (EMA20/50, RSI, ATR, swing levels) -- use it to judge whether the current move is a pullback within a larger trend or a reversal. If its numbers conflict with the visible candles, prefer the visible candles. Any news/fundamental note is advisory only -- disregard if generic or stale.

The "recent outcomes" note, if present, is win/loss history for your risk awareness only -- not a directional signal to stay consistent with.

### RISK CONSTRAINTS (apply regardless of chosen strategy)
Read the market data first and form your thesis from structure. Then validate that thesis against the constraints below -- do not start from the constraints and reverse-engineer a thesis to fit them.
Any BUY or SELL must satisfy all of the following:
- A concrete, statable entry thesis (why this direction, why now)
- A clear invalidation condition: the nearest opposing swing structure behind your entry (for BUY: the last relevant swing low below; for SELL: the last relevant swing high above) -- not the latest candle's extreme, not the furthest swing of the entire window. The level where the thesis is broken.
{{SLTP_RULES_BLOCK}}

HOLD is correct whenever no structure offers an SL at/behind a real invalidation level that also satisfies the SL/TP floors above -- do not force a trade to avoid it.

{{POINTS_EXPLANATION}}

### OUTPUT FORMAT
Respond with a single valid JSON object ONLY -- no text before or after it.

HOLD:
{
  "signal": "HOLD",
  "reasoning": "string (MAX 20 WORDS: single key technical reason why no setup exists)"
}

BUY or SELL:
{
  "signal": "BUY" | "SELL",
  "confidence": float (0.50 to 1.00),
  "setup": "string (short label for setup type)",
  "reasoning": "string (MAX 40 WORDS: core entry thesis & edge for this new entry)",
  "invalidation": "string (key technical condition that invalidates this thesis)",
  "sl_points": integer (Stop Loss distance in broker POINTS from current price),
  "tp_points": integer (Take Profit distance in broker POINTS from current price),
  "invalidation_price": float (OPTIONAL: reference price level for invalidation),
  "target_price": float (OPTIONAL: reference price level for target),
{{PENDING_FIELDS}}
}

"position_actions": include ONLY when positions are listed above -- for each ticket: {"ticket": number, "action": "CLOSE" | "HOLD", "reason": "max 5 words"}, ... -- one entry per listed ticket.

CONFIDENCE guide: 0.70+ = strong, well-supported thesis | 0.50-0.70 = moderate, reasonable but not fully clean | 0.30-0.50 = weak, default to HOLD unless you have a concrete reason to act | below 0.30 = no real edge, HOLD.

{{PENDING_RULES_BLOCK}}"""


def _fmt_price(x, point_size=None):
    """Format harga ke desimal presisi sesuai point_size (XAU 2 des, EURJPY 3 des, FX 5 des)."""
    if x is None:
        return ""
    if point_size and point_size > 0:
        decimals = max(0, int(round(-__import__("math").log10(point_size))))
        return f"{x:.{decimals}f}"
    return f"{x:.10f}".rstrip("0").rstrip(".")


def _delta_candle_lines(df, n=15, point_size=0.01):
    """Format n candle terakhir sebagai OHLC HARGA ABSOLUT (semua angka nyata):
    '- [HH:MM] O/H/L/C' (format harga sesuai point_size: XAU 2 des, FX 5 des).
    LLM baca harga langsung tanpa kalkulasi/rekonstruksi (nol drift), dan bisa
    verifikasi silang (H >= max(O,C), L <= min(O,C)). Tetap hemat token
    karena cuma n baris pendek, bukan 50 baris OHLC penuh.
    Fix 18 Agustus: delta-only berantai -> LLM harus jumlah kumulatif (rawan
    drift); lalu C absolut + delta O/H/L (masih ada kalkulasi kecil); akhirnya
    semua absolut (paling aman, selisih token kecil utk XAU/FX)."""
    if df is None or len(df) == 0:
        return []
    if not point_size or point_size <= 0:
        point_size = 0.01
    tail = df.tail(n)
    lines = []
    for idx, row in tail.iterrows():
        t_s = row["time"].strftime("%H:%M") if hasattr(row["time"], "strftime") else str(row["time"])
        o = _fmt_price(float(row["open"]), point_size)
        h = _fmt_price(float(row["high"]), point_size)
        l = _fmt_price(float(row["low"]), point_size)
        c = _fmt_price(float(row["close"]), point_size)
        lines.append(f"- [{t_s}] {o}/{h}/{l}/{c}")
    return lines


def _structure_block(df, current_tick, atr_points=0):
    """Ringkas struktur 50-bar (short-term) & 100-bar (macro) window:
    swing/Fib (trend-aware)/posisi harga relatif level.
    """
    if df is None or len(df) == 0:
        return ""

    close = float(df["close"].iloc[-1])
    point = current_tick.get("point", 0.01) if current_tick else 0.01
    if not point or point <= 0:
        point = 0.01

    lines = []

    # 1. 50-bar Short-Term Window
    df_50 = df.tail(min(50, len(df)))
    h50, l50 = float(df_50["high"].max()), float(df_50["low"].min())
    diff50 = h50 - l50
    is_down50 = float(df_50["close"].iloc[0]) > close
    if is_down50:
        f382_50 = round(l50 + 0.382 * diff50, 6)
        f500_50 = round(l50 + 0.500 * diff50, 6)
        f618_50 = round(l50 + 0.618 * diff50, 6)
        label50 = "Downtrend Bounce"
    else:
        f382_50 = round(h50 - 0.382 * diff50, 6)
        f500_50 = round(h50 - 0.500 * diff50, 6)
        f618_50 = round(h50 - 0.618 * diff50, 6)
        label50 = "Uptrend Pullback"

    to_h50 = (h50 - close) / point
    to_l50 = (close - l50) / point

    lines.append("### STRUCTURE (50-bar & 100-bar Window)")
    lines.append(f"- 50-bar Swing: High {_fmt_price(h50, point)} | Low {_fmt_price(l50, point)} | Range: {int(diff50/point)} pts")
    lines.append(f"- 50-bar Fib ({label50}): 38.2% {_fmt_price(f382_50, point)} | 50% {_fmt_price(f500_50, point)} | 61.8% {_fmt_price(f618_50, point)}")
    lines.append(f"- Close {_fmt_price(close, point)}: {int(to_l50)} pts above 50-bar low | {int(to_h50)} pts below 50-bar high")

    # 2. 100-bar Macro Multi-Day Window
    if len(df) >= 70:
        h100, l100 = float(df["high"].max()), float(df["low"].min())
        diff100 = h100 - l100
        is_down100 = float(df["close"].iloc[0]) > close
        if is_down100:
            f382_100 = round(l100 + 0.382 * diff100, 6)
            f500_100 = round(l100 + 0.500 * diff100, 6)
            f618_100 = round(l100 + 0.618 * diff100, 6)
            label100 = "Downtrend Bounce"
        else:
            f382_100 = round(h100 - 0.382 * diff100, 6)
            f500_100 = round(h100 - 0.500 * diff100, 6)
            f618_100 = round(h100 - 0.618 * diff100, 6)
            label100 = "Uptrend Pullback"

        lines.append(f"- 100-bar Swing: High {_fmt_price(h100, point)} | Low {_fmt_price(l100, point)} | Range: {int(diff100/point)} pts")
        lines.append(f"- 100-bar Fib ({label100}): 38.2% {_fmt_price(f382_100, point)} | 50% {_fmt_price(f500_100, point)} | 61.8% {_fmt_price(f618_100, point)}")

    # 3. Indicators
    ema20 = float(df["ema_20"].iloc[-1]) if "ema_20" in df.columns else None
    ema50 = float(df["ema_50"].iloc[-1]) if "ema_50" in df.columns else None
    if ema20 is not None and ema50 is not None:
        gap = (ema20 - ema50) / point
        rel_ema20 = (close - ema20) / point
        pos = "ABOVE" if rel_ema20 > 0 else "BELOW"
        lines.append(f"- EMA20 {_fmt_price(ema20, point)} | EMA50 {_fmt_price(ema50, point)} (gap {int(abs(gap))} pts) | close is {int(abs(rel_ema20))} pts {pos} EMA20")
    if "rsi_14" in df.columns:
        rsi = float(df["rsi_14"].iloc[-1])
        lines.append(f"- RSI14 {rsi:.2f}")
    if atr_points and atr_points > 0:
        lines.append(f"- ATR14 {_fmt_price(float(df['atr_14'].iloc[-1]), point)} (= {atr_points} pts)")

    return "\n".join(lines)



def _build_points_explanation(symbol, point_size):
    """
    Generate a highly explicit explanation of broker points vs pips/price-units
    to avoid LLMs mixing them up (e.g. OpenAI/DeepSeek outputting pips instead of points).
    """
    is_btc = config.is_crypto(symbol)
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
            f"- Typical Stop Loss distance is 20000 to 60000 points ($200.00 to $600.00 USD price change), and ALWAYS check the 'ATR HARD GATE' in the Market Data context below for the exact dynamic minimum required for this specific trade.\n\n"
            f"CRITICAL WARNING:\n"
            f"Double-check your numbers. If you want a Stop Loss of $400 USD of BTC price movement, you MUST return 40000. "
            f"If you return 400, it sets a Stop Loss of just 400 points ($4.00 USD price change), which is inside the spread and will cause an instant loss or broker rejection!"
        )
    else:
        # Gold / Forex - konversi dihitung dari point_size aktual per symbol
        # (bukan hardcode asumsi XAU). Semua pair ini 1 pip = 10 points:
        # XAU (0.01 -> pip 0.10), EURJPY (0.001 -> pip 0.01), GBPCHF (0.00001 -> 0.0001).
        pt_str = _fmt_price(point_size) if point_size else "0.01"
        pip_str = _fmt_price(point_size * 10) if point_size else "0.10"
        # Typical SL range dari default per-symbol (XAU 500/1000, FX 300 ->
        # 150-450) - dijadikan range SL yang wajar (0.5x-1.5x default SL).
        # Khusus XAU mode LLM: di-sinkronkan ke floor ATR aktif (1.2x ATR M15,
        # 15 Agustus) biar konsisten dengan SL/TP rules block (sebelumnya 400-1000
        # statis, sekarang dinamis - SL tipis 0.8x ATR dari o4-mini di-floor ke
        # 1.2x ATR; fix konsistensi range 13 Agustus tetap berlaku).
        d_sl = config.default_sl_points_for(symbol)
        lo_pts = max(10, int(d_sl * 0.5))
        hi_pts = max(20, int(d_sl * 1.5))
        is_gold = "XAU" in (symbol or "").upper()
        if is_gold and config.sltp_mode_for(symbol) == "LLM":
            atr_pts_xau = _atr_points_for(symbol, config.get_timeframe(symbol))
            if atr_pts_xau and atr_pts_xau > 0:
                xau_floor = max(20, int(config.LLM_XAU_FLOOR_ATR_MULT * atr_pts_xau))
            else:
                xau_floor = config.LLM_SAFETY_FLOOR_XAU_PTS
            lo_pts = max(lo_pts, xau_floor)
            hi_pts = max(hi_pts, int(xau_floor * 2.5))
        # FX mode LLM: sinkronkan ke floor ATR aktif (1.5x ATR H1) supaya unit
        # definition tidak kontradiksi dengan floor di blok SL/TP rules
        # (fix 14 Agustus lanjutan: floor statis 250 -> ATR-based, fallback 250).
        if not is_gold and not is_btc and config.sltp_mode_for(symbol) == "LLM":
            atr_pts_fx = _fx_atr_h1_points(symbol)
            if atr_pts_fx and atr_pts_fx > 0:
                fx_floor = max(20, int(config.LLM_FX_FLOOR_ATR_MULT * atr_pts_fx))
            else:
                fx_floor = config.LLM_SAFETY_FLOOR_FX_PTS
            lo_pts = max(lo_pts, fx_floor)
            hi_pts = max(hi_pts, int(fx_floor * 2.5))
        if is_gold:
            typical_note = (
                f"${round(lo_pts * (point_size or 0.01), 2)} to "
                f"${round(hi_pts * (point_size or 0.01), 2)} price move"
            )
        else:
            typical_note = "price units"
        # Referensi "ATR HARD GATE" cuma relevan kalau mode ATR-Based (BTC /
        # force override) - section itu cuma ada di Market Data kalau mode
        # ATR-Based. Mode LLM (XAU/FX) nggak punya section itu -> referensi
        # gantung (dangling) bikin bingung (fix 13 Agustus).
        if config.sltp_mode_for(symbol) == "ATR-Based":
            gate_note = (", and ALWAYS check the 'ATR HARD GATE' in the Market Data "
                         "context below for the exact dynamic minimum required for this specific trade")
        else:
            gate_note = (" -- for the exact floor relevant to this symbol, see the SL/TP "
                         "rules in the RISK CONSTRAINTS section below")
        return (
            f"### CRITICAL UNIT DEFINITION: POINTS vs PIPS vs PRICE MOVEMENT\n"
            f"You MUST calculate and return Stop Loss and Take Profit in broker **POINTS** (integer), NOT pips, NOT USD price.\n"
            f"For {symbol} (with broker point size = {pt_str}):\n"
            f"- 1 point = {pt_str} price units.\n"
            f"- 10 points = 1 pip = {pip_str} price movement.\n"
            f"- 100 points = 10 pips = {_fmt_price(point_size * 100) if point_size else '1.00'} price movement.\n"
            f"- Typical Stop Loss distance for {symbol} is usually {lo_pts} to {hi_pts} points{gate_note}.\n\n"
            f"CRITICAL WARNING:\n"
            f"Double-check your numbers. If you want a Stop Loss of {lo_pts // 10} pips, you MUST return {lo_pts} points. "
            f"If you return {lo_pts // 10}, it sets a Stop Loss of just {lo_pts // 10} points "
            f"({max(1, lo_pts // 100)} pip / {_fmt_price((lo_pts // 10) * (point_size or 0.01))} price movement), "
            f"which is inside the spread and will cause an instant loss or broker rejection!"
        )


_fx_atr_cache = {}  # (symbol, timeframe) -> (timestamp, atr_points)


def _atr_points_for(symbol, timeframe):
    """ATR(14) dari timeframe tertentu dalam poin broker (cache 60s per
    (symbol, timeframe)) — dipakai untuk floor dinamis & typical SL range di
    prompt. Return None kalau gagal. 15 Agustus: digeneralisasi dari helper
    FX-only supaya XAU (M15) bisa pakai floor ATR juga. 18 Agustus: pindah ke
    ATR(14) true-range (ta.volatility.AverageTrueRange) supaya angka floor
    KONSISTEN dengan ATR yang dikirim ke model di prompt (sebelumnya pakai
    mean(high-low) yang menghasilkan angka beda -> prompt bilang 949, floor
    bilang 1179, kontradiksi)."""
    import time as _t
    key = (symbol, timeframe)
    now = _t.time()
    hit = _fx_atr_cache.get(key)
    if hit and now - hit[0] < 60:
        return hit[1]
    try:
        import MetaTrader5 as _mt5
        si = _mt5.symbol_info(symbol)
        point = si.point if si else None
        if not point:
            return None
        rates = _mt5.copy_rates_from_pos(symbol, timeframe, 0, 50)
        if rates is None or len(rates) == 0:
            return None
        import pandas as _pd
        from ta.volatility import AverageTrueRange
        _df = _pd.DataFrame(rates)
        _df['atr'] = AverageTrueRange(high=_df['high'], low=_df['low'], close=_df['close'], window=14).average_true_range()
        atr_val = _df.iloc[-1]['atr']
        if _pd.isna(atr_val):
            return None
        out = max(1, int(round(float(atr_val) / point)))
        _fx_atr_cache[key] = (now, out)
        return out
    except Exception:
        return None


def _fx_atr_h1_points(symbol):
    """ATR(14) H1 FX dalam poin broker (cache 60s) — dipakai untuk
    floor dinamis & typical SL range di prompt. Return None kalau gagal."""
    import MetaTrader5 as _mt5
    return _atr_points_for(symbol, _mt5.TIMEFRAME_H1)


def _build_sltp_rules_block(symbol, timeframe):
    """
    Build the SL/TP constraint lines for the system prompt based on
    config.TP_SL_RULES:
      "ATR-Based": SL >= SL_MULTx ATR, TP >= TP_MULTx ATR (R:R 2:1) - HARD GATE.
        Multiplier dinamis per AI mode (config.atr_sl_multiplier/atr_tp_multiplier):
        single 1.25/2.5, dual 1.5/3.0, triple 1.75/3.5.
        Trade yang SL/TP-nya di bawah requirement DITOLAK bot (bukan
        dinaikkan), jadi prompt ini harus tegas biar AI gak buang cycle.
        Angka minimum konkret (dalam points) di-inject dinamis di market
        data block (atr_gate_str) - sinkron dengan consensus gate.
      "LLM": SL/TP bebas sesuai thesis LLM; dibatasi safety floor per-kategori
      (XAU 400 pts statis / FX berbasis ATR aktif 1.5x ATR H1, fallback 250)
      + R:R minimum 1.25:1 (config.LLM_*). Bot TIDAK ngomongin sizing/ATR di
      prompt mode ini - SL/TP model di-average di consensus.py (outlier dibuang),
      lot size dikalkulasi dari SL di main.py.
    """
    mode = config.sltp_mode_for(symbol)  # per-kategori: XAU LLM, BTC ATR-Based, FX LLM
    is_xau = "XAU" in symbol.upper() or "GOLD" in symbol.upper()
    is_btc = config.is_crypto(symbol)
    min_rr = config.LLM_MIN_RR_RATIO

    if mode == "LLM":
        # Mode LLM: Bebas sesuai thesis/struktur pasar, tapi bot yang enforce floor.
        # Filosofi (14 Agustus): model kasih level struktural JUJUR (berapa pun
        # jaraknya); bot yang menaikkan SL/TP ke floor minimum (SL >= floor, TP >=
        # 1.25x SL). Model TIDAK perlu stretch level ke angka tertentu - itu justru
        # bikin model HOLD terus ("no clean 400+ invalidation").
        if is_xau:
            # 15 Agustus: floor XAU dinamis = 1.2x ATR M15 (LLM_XAU_FLOOR_ATR_MULT),
            # fallback 400 statis kalau ATR gagal. SL tipis 0.8x ATR (o4-mini) di-floor
            # otomatis ke 1.2x ATR supaya swing M15 gak kena noise duluan.
            xau_floor = config.LLM_SAFETY_FLOOR_XAU_PTS
            atr_pts_xau = _atr_points_for(symbol, config.get_timeframe(symbol))
            if atr_pts_xau and atr_pts_xau > 0:
                xau_floor = max(20, int(config.LLM_XAU_FLOOR_ATR_MULT * atr_pts_xau))
            lo_pts = xau_floor
            hi_pts = max(1000, int(lo_pts * 2.5))
            # 14 Agustus malam: gate OVER-RISK dilonggarkan ke 2% (config
            # OVER_RISK_MAX_PERCENT) - SL >1000 pts TETAP BISA diterima selama risk
            # aktual di min lot <= 2%. Guidance ini cuma preferensi, bukan batas keras.
            return (
                f"- Define 'sl_points' and 'tp_points' as DISTANCES from the current price in broker POINTS, measured to your structural levels: sl_points = distance to your invalidation (the nearest opposing swing structure behind the entry), tp_points = distance to your structural target (swing/Fib/PDH-PDL level). These are what the bot actually uses for the order.\n"
                f"- 'invalidation_price'/'target_price' are OPTIONAL reference levels used only to describe your thesis & probability reasoning -- the bot does NOT use them to place SL/TP. Do not stress about their exact values.\n"
                f"- The bot enforces minimum floors automatically: SL >= {lo_pts} pts (approx {config.LLM_XAU_FLOOR_ATR_MULT}x ATR M30) and TP >= {min_rr}x SL. If your honest structural distance is tighter than the floor, the bot widens SL (and TP to keep R:R) -- give your real structural levels; the bot handles the floors.\n"
                f"- For risk sizing with min lot 0.01, an SL in the ~{lo_pts}-{hi_pts} pts range is most efficient. Wider SLs (e.g. 1000-1900 pts) are still ACCEPTED as long as actual risk at min lot stays within the OVER-RISK gate (max ~2% of equity at current balance) -- prefer structural levels in the ~{lo_pts}-{hi_pts} range when available, but give your real structural invalidation either way.\n"
            )
        elif is_btc:
            return (
                f"- Define 'sl_points' and 'tp_points' as DISTANCES from the current price in broker POINTS (typically 20000 to 60000 points / $200-$600), measured to your structural levels: sl_points = distance to your invalidation (the nearest opposing swing structure), tp_points = distance to your structural target. These are what the bot actually uses for the order.\n"
                f"- 'invalidation_price'/'target_price' are OPTIONAL reference levels used only to describe your thesis & probability reasoning -- the bot does NOT use them to place SL/TP. Do not stress about their exact values.\n"
                f"- The bot enforces minimum floors automatically: SL >= 2x current spread and TP >= {min_rr}x SL. Give your real structural levels; the bot handles the floors.\n"
            )
        else:
            # FX Pairs H1: bebas mengikuti struktur harga, tapi floor SL & Proximity/Breakout
            # berbasis ATR aktif H1 real-time.
            fx_floor = config.LLM_SAFETY_FLOOR_FX_PTS
            atr_pts_fx = _fx_atr_h1_points(symbol)
            if atr_pts_fx and atr_pts_fx > 0:
                fx_floor = max(20, int(config.LLM_FX_FLOOR_ATR_MULT * atr_pts_fx))
                prox_pts = int(0.5 * atr_pts_fx)
                stop_pts = max(10, int(0.2 * atr_pts_fx))
                room_pts = int(1.0 * atr_pts_fx)
            else:
                prox_pts = 45
                stop_pts = 18
                room_pts = 90
            if getattr(config, "PENDING_ORDERS_ENABLED", False):
                breakout_rule = (
                    f"- MOMENTUM & BREAKOUT EXECUTION: If price is approaching a key level with momentum (e.g. 2+ consecutive same-direction H1 closes or expanding candle bodies) but has not closed beyond it yet, do not chase with an immediate market order. Instead:\n"
                    f"  (a) Use buy_stop/sell_stop placed ~0.2x-0.3x ATR H1 (~{stop_pts}-{int(1.5*stop_pts)} pts) beyond the key level to filter false breaks and catch a genuine breakout wave.\n"
                    f"  (b) Use buy_limit/sell_limit at or near the key level to enter on a pullback/retest.\n"
                    f"  (c) Use a market order ONLY if a candle has already closed beyond the level and there is at least 1.0x ATR H1 (~{room_pts} pts) room remaining to your structural target."
                )
            else:
                breakout_rule = (
                    f"- MOMENTUM & BREAKOUT EXECUTION: If price is approaching a key level with momentum but has not closed beyond it yet, do not chase with a market order -- wait for a confirmed candle close beyond the level with at least 1.0x ATR H1 (~{room_pts} pts) room remaining to your target, or select HOLD."
                )

            return (
                f"- Define 'sl_points' and 'tp_points' as DISTANCES from the current price in broker POINTS, measured to your structural levels: sl_points = distance to your invalidation (the nearest opposing swing structure behind the entry), tp_points = distance to your structural target (swing/support-resistance/EMA). These are what the bot actually uses for the order.\n"
                f"- 'invalidation_price'/'target_price' are OPTIONAL reference levels used only to describe your thesis & probability reasoning -- the bot does NOT use them to place SL/TP. Do not stress about their exact values.\n"
                f"- The bot enforces minimum floors automatically: SL >= max(2x spread, ~{fx_floor} pts = {config.LLM_FX_FLOOR_ATR_MULT}x ATR H1) and TP >= {min_rr}x SL. If your honest structural distance is tighter than the floor, the bot widens SL (and TP to keep R:R) -- give your real structural levels; the bot handles the floors.\n"
                f"- PROXIMITY & TRAP AVOIDANCE: Do not enter BUY market orders when price is within 0.5x ATR H1 (~{prox_pts} pts) below major resistance (50-bar swing high, PDH, or key HTF resistance) unless price has already closed beyond that level. Mirror this for SELL within 0.5x ATR H1 (~{prox_pts} pts) above major support. Ensure the distance from entry to your target is at least 1.25x the distance to the opposing structure.\n"
                f"{breakout_rule}"
            )

    # Mode ATR-Based: ATR HARD GATE (non-negotiable) berlaku untuk semua simbol
    sl_mult = config.atr_sl_multiplier()
    tp_mult = config.atr_tp_multiplier()
    return (
        f"- Define 'sl_points' and 'tp_points' as DISTANCES from the current price in broker POINTS, measured to your structural levels: sl_points = distance to your invalidation (nearest opposing swing), tp_points = distance to your structural target. These are what the bot actually uses for the order.\n"
        f"- 'invalidation_price'/'target_price' are OPTIONAL reference levels used only to describe your thesis & probability reasoning -- the bot does NOT use them to place SL/TP.\n"
        f"- HARD GATE (non-negotiable, enforced by the bot): if the resulting SL < {sl_mult}x current ATR or TP < {tp_mult}x current ATR, the bot REJECTS the trade -- no order is sent. Give your real structural levels; if they cannot meet the gate, HOLD is the correct call.\n"
        f"- These minimums guarantee R:R 2:1 (SL {sl_mult}x ATR -> TP {tp_mult}x ATR). The exact minimum price distances required for current ATR are listed in the MARKET DATA section (ATR HARD GATE line).\n"
    )


_key_levels_cache = {}  # symbol -> (timestamp, str)


def _get_key_levels_str(symbol, current_bid):
    """
    Key levels from D1 (previous day high/low, today open) + nearest round
    number + current WIB session. Cached 5 minutes (D1 only changes once/day,
    session label changes slowly). Falls back to empty string on any error.
    """
    import time as _time
    now = _time.time()
    cached = _key_levels_cache.get(symbol)
    if cached and now - cached[0] < 300:
        return cached[1]

    try:
        from src.core import mt5_connector
        # Fetch raw D1 rates directly -- key levels only need OHLC. Avoid
        # get_market_data() here: it computes indicators with window=14+ and
        # crashes (ATR) when given fewer candles (e.g. num_candles=3).
        rates = mt5_connector.mt5.copy_rates_from_pos(
            mt5_connector.get_valid_trade_symbol(symbol), config.mt5.TIMEFRAME_D1, 0, 3
        )
        if rates is None or len(rates) < 2:
            return ""
        prev = rates[-2]  # previous day
        today = rates[-1]  # today
        pdh = float(prev['high'])
        pdl = float(prev['low'])
        today_open = float(today['open'])

        # Round number: nearest 1000 untuk BTC, nearest 2-desimal (pip-level)
        # untuk FX (harga < 100, mis. EURJPY 151.23 / GBPCHF 1.10), nearest
        # integer untuk XAU (harga ~1000-5000). Fix 14 Agustus: FX 5-desimal
        # sebelumnya di-round ke 1 (round(1.09815) = 1) -> "1.00" yang nyasar.
        if current_bid and current_bid > 10000:
            round_num = round(current_bid / 1000.0) * 1000
        elif current_bid and current_bid < 100:
            round_num = round(current_bid, 2)
        elif current_bid:
            round_num = round(current_bid)
        else:
            round_num = None
        round_str = f"{round_num:,.2f}" if round_num is not None else "n/a"

        # Active WIB session label from config.ALLOWED_SESSIONS_WIB
        from datetime import datetime
        from zoneinfo import ZoneInfo
        wib_now = datetime.now(ZoneInfo("Asia/Jakarta"))
        cur_min = wib_now.hour * 60 + wib_now.minute
        session_names = []
        for s in getattr(config, "ALLOWED_SESSIONS_WIB", []):
            sh, sm = s["start"]; eh, em = s["end"]
            start_min = sh * 60 + sm
            end_min = eh * 60 + em
            if start_min <= end_min:
                active = start_min <= cur_min <= end_min
            else:  # overnight session (e.g. NY 20:00 -> 05:00)
                active = cur_min >= start_min or cur_min <= end_min
            if active:
                session_names.append(s["name"])
        session_str = ", ".join(session_names) if session_names else "no session"

        out = (
            f"### KEY LEVELS\n"
            f"- Previous Day High: {_fmt_price(pdh)} | Previous Day Low: {_fmt_price(pdl)}\n"
            f"- Today Open: {_fmt_price(today_open)}\n"
            f"- Nearest Psychological Round Number: {round_str}\n"
            f"- Active Session (WIB): {session_str}\n"
        )
        _key_levels_cache[symbol] = (now, out)
        return out
    except Exception as exc:
        print(f"[KEY LEVELS ERROR] {exc}")
        return ""


def build_system_prompt(symbol, timeframe, asset_description, point_size=0.01):
    """
    Static per-bot 'constitution'. Build once per bot instance (e.g. once
    for XAU M15, once for BTC M30) and reuse unchanged across cycles -- this
    is the part that benefits from provider-side prompt/context caching,
    since only the dynamic market data below changes every call.
    """
    points_explanation = _build_points_explanation(symbol, point_size)
    # EXECUTION NOTE dinamis: kalau pending order ON, bilang bot dukung pending
    # (STOP/LIMIT + entry_price); kalau OFF, teks lama (market order only).
    if getattr(config, "PENDING_ORDERS_ENABLED", False):
        execution_note = (
            "Any BUY or SELL signal you output is executed either as a Market Order "
            "(immediate, at the current price) or as a PENDING order (buy_stop/sell_stop/"
            "buy_limit/sell_limit with entry_price) -- see the PENDING ORDER RULES below "
            "for when to use each. The bot supports both."
        )
        pending_rules_block = (
            "\n### PENDING ORDER RULES (the bot has pending orders enabled)\n"
            "Your thesis determines the entry type -- do not pick one arbitrarily:\n"
            "- Thesis is a BREAKOUT / momentum continuation beyond a level: use buy_stop (BUY) or sell_stop (SELL). entry_price = the breakout level (beyond current price).\n"
            "- Thesis is a RETEST / pullback to a level: use buy_limit (BUY) or sell_limit (SELL). entry_price = the retest level (below current price for BUY, above for SELL).\n"
            "- Thesis is valid at the CURRENT price: use \"market\" (default) -- no entry_price needed.\n"
            "- Direction consistency is mandatory: BUY -> buy_stop/buy_limit only; SELL -> sell_stop/sell_limit only.\n"
            "- entry_price must be at least 2x current spread away from the current price, and no further than ~1.5x ATR from it. If your level is outside this band, the bot rejects the pending order (or falls back to market).\n"
            "- An executed pending order becomes a normal position with your sl_points/tp_points -- same risk rules apply.\n"
            "- If you are not confident the level will trigger, output \"market\" or HOLD instead."
        )
        pending_fields = (
            '  "entry_type": "market" | "buy_stop" | "sell_stop" | "buy_limit" | "sell_limit",\n'
            '  "entry_price": float (REQUIRED if entry_type != "market")'
        )
    else:
        execution_note = (
            "Any BUY or SELL signal you output will be executed immediately at the current "
            "market price (Market Order). The bot does not support pending orders."
        )
        pending_rules_block = ""
        pending_fields = ""
    prompt = (
        _SYSTEM_PROMPT_TEMPLATE
        .replace("{{SYMBOL}}", symbol)
        .replace("{{TIMEFRAME}}", timeframe)
        .replace("{{ASSET_DESC}}", asset_description)
        .replace("{{SLTP_RULES_BLOCK}}", _build_sltp_rules_block(symbol, timeframe))
        .replace("{{POINTS_EXPLANATION}}", points_explanation)
        .replace("{{EXECUTION_NOTE}}", execution_note)
        .replace("{{PENDING_RULES_BLOCK}}", pending_rules_block)
        .replace("{{PENDING_FIELDS}}", pending_fields)
    )

    if getattr(config, "FORCE_ACTIVE_ENTRY", False):
        prompt += (
            "\n\n### FORCE ACTIVE ENTRY MODE (ACTIVE)\n"
            "CRITICAL DIRECTIVE: You are explicitly required to identify and take an active directional trading position (BUY or SELL) based on the strongest available edge in current price action and technical indicators. "
            "Do NOT default to HOLD unless market data is completely corrupt or unreadable. Actively weigh BUY vs SELL and select the direction with higher probability edge!"
        )

    return prompt


def format_candles(candles):
    """candles: list of dicts with keys time, open, high, low, close, volume."""
    lines = []
    for c in candles:
        lines.append(
            f"- [{c['time']}] O:{c['open']}, H:{c['high']}, L:{c['low']}, "
            f"C:{c['close']}, V:{c['volume']}"
        )
    return "\n".join(lines)


def format_positions(positions):
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


def summarize_recent_outcomes(decisions, n=6):
    """
    Strip directional narrative out of decision history, keep outcome
    stats only -- so the current cycle isn't anchored to the previous
    cycle's directional story (this was likely a contributor to the bot
    holding a stale bullish read for hours during a correction).

    decisions: list of dicts, most recent last, e.g.
        {"signal": "BUY", "result": "TP" | "SL" | "SL-BEP" | "SL-trailing" | "OPEN" | "N/A",
         "profit": float (NET, sudah termasuk komisi) | None, "commission": float}
    Klasifikasi win/loss pakai PROFIT NET kalau ada (paling akurat - BEP
    tolerance dinamis dari komisi aktual), fallback ke label result.
    """
    recent = decisions[-n:]
    if not recent:
        return "No recent decision history for this symbol."

    hold_count = sum(1 for d in recent if d["signal"] == "HOLD")
    trade_count = len(recent) - hold_count
    win_count = 0
    loss_count = 0
    bep_count = 0
    open_count = 0
    for d in recent:
        if d["signal"] == "HOLD":
            continue
        result = d.get("result", "N/A")
        if result == "OPEN":
            open_count += 1
            continue
        profit = d.get("profit")
        if profit is not None:
            tol = config.bep_tolerance_for({"commission": d.get("commission", 0.0)})
            if profit > tol:
                win_count += 1
            elif profit < -tol:
                loss_count += 1
            else:
                bep_count += 1
        else:
            # Fallback label (tanpa profit): SL-trailing = profit terkunci = win
            if result in ("TP", "SL-trailing"):
                win_count += 1
            elif result == "SL":
                loss_count += 1
            else:  # SL-BEP, manual, N/A
                bep_count += 1

    stats = f"{trade_count} trade(s) taken ({win_count} win, {loss_count} loss, {bep_count} BEP)"
    if open_count:
        stats += f", {open_count} still open"
    return (
        f"Recent outcomes ({len(recent)} cycles): {stats}, {hold_count} HOLD. "
        f"(Outcome only -- not a directional signal for this cycle.)"
    )


def prepare_prompt(symbol, df, current_tick, macro_context=None, open_positions=None,
                   whisper_str=None, all_open_positions=None):
    """
    Constructs a rich prompt for LLM models containing price action,
    multi-timeframe technical indicators, MTF macro analysis, and active open positions.
    whisper_str: optional pattern research stats (validated edge) — informational only.
    all_open_positions: all open bot positions across all symbols for cross-portfolio awareness.
    """

    # Dynamic timeframe label resolved from dataframe or fallback to config
    tf_label = None
    if len(df) >= 2:
        try:
            diff_sec = int(abs((df['time'].iloc[-1] - df['time'].iloc[-2]).total_seconds()))
            sec_to_tf = {300: "M5", 900: "M15", 1800: "M30", 3600: "H1", 14400: "H4", 86400: "D1"}
            tf_label = sec_to_tf.get(diff_sec)
        except Exception:
            pass
    if not tf_label:
        tf_val = config.get_timeframe(symbol)
        tf_map_rev = {v: k for k, v in config.TIMEFRAME_MAP.items()}
        tf_label = tf_map_rev.get(tf_val, "M30" if "XAU" in symbol.upper() else "M5")

    # Compact price action: STRUCTURE block (level terhitung) + delta candles
    # (shape). Ganti 50 candle OHLC mentah (~560 token) -> STRUCTURE + 15 delta
    # (~200 token). Shape price action tetap kebaca (body/wick/urutan), semua
    # level absolut tetap ada sebagai angka di STRUCTURE.
    latest = df.iloc[-1]
    point_size = current_tick.get("point", 0.01) or 0.01
    atr_points = int(latest["atr_14"] / point_size) if point_size > 0 else 0

    structure_str = _structure_block(df, current_tick, atr_points)
    delta_main = _delta_candle_lines(df, n=15, point_size=point_size)
    delta_main_str = ""
    if delta_main:
        delta_main_str = (
            f"\n### RECENT PRICE ACTION (last {len(delta_main)} {tf_label} candles, "
            f"OHLC absolute prices)\n" + "\n".join(delta_main) + "\n"
        )

    # Micro price action: M5, delta juga. XAU/BTC 18 (1.5 jam), FX 24 (2 jam).
    # Micro M5 adalah satu-satunya price action granular intra-period utk
    # timeframe lambat (M30/H1) - TIDAK dihapus, cuma dikompres.
    micro_candles_str = ""
    try:
        from src.core import mt5_connector
        is_crypto_asset = config.is_crypto(symbol)

        if is_crypto_asset or "XAU" in symbol.upper():
            micro_tf = mt5_connector.mt5.TIMEFRAME_M5
            micro_tf_name = "M5"
            num_micro_send = 18
        else:
            # FX main is H1 -> micro M5 24 (2 jam) intra-period
            micro_tf = mt5_connector.mt5.TIMEFRAME_M5
            micro_tf_name = "M5"
            num_micro_send = 24

        # Fetch enough candles so ta.volatility.AverageTrueRange (window 14) doesn't raise IndexError
        num_fetch = max(35, num_micro_send + 15)
        micro_df = mt5_connector.get_market_data(symbol, micro_tf, num_candles=num_fetch)
        if micro_df is not None and len(micro_df) > 0:
            micro_delta = _delta_candle_lines(micro_df, n=num_micro_send, point_size=point_size)
            if micro_delta:
                micro_candles_str = (
                    f"\n### LAST {len(micro_delta)} {micro_tf_name} CANDLES (intra-period, "
                    f"OHLC absolute prices)\n" + "\n".join(micro_delta) + "\n"
                )
    except Exception as e:
        pass

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
    # reflects real 30-minute volatility. XAU df is M15 (swing) - ATR M15 ~819 pts.

    # ATR-based HARD GATE (mode ATR-Based): angka minimum konkret di-inject ke
    # market data biar LLM gak perlu kalikan ATR x 1.25 / x 2.5 manual (LLM
    # jelek di aritmetika). Kalau proposal SL/TP di bawah angka ini,
    # consensus.py MENOLAK trade (bukan dinaikkan) - jadi prompt harus jelas
    # biar AI gak buang cycle buat sinyal yang pasti ditolak.
    atr_gate_str = ""
    # Inject ATR Gate information ONLY if the symbol's mode is ATR-Based
    # (BTC fix ATR-Based; XAU/FX ikut mode LLM kecuali TP_SL_RULES di-force ATR-Based)
    if atr_points > 0 and config.sltp_mode_for(symbol) == "ATR-Based":
        ai_mode = config.get_ai_mode()
        sl_mult = config.atr_sl_multiplier()
        tp_mult = config.atr_tp_multiplier()
        min_sl_pts = int(atr_points * sl_mult)
        min_tp_pts = int(atr_points * tp_mult)
        atr_gate_str = (
            f"ATR HARD GATE (non-negotiable, AI mode: {ai_mode}): minimum SL = {min_sl_pts} pts "
            f"({sl_mult}x ATR) and minimum TP = {min_tp_pts} pts ({tp_mult}x ATR). "
            f"If your proposed SL or TP is below these, the bot REJECTS the trade -- no order is sent.\n"
        )

    usd_context = ""

    macro_str = ""
    if macro_context:
        macro_str = (
            "\n### HIGHER-TIMEFRAME STRUCTURE & MACRO CONTEXT\n"
            f"{macro_context}\n"
            "(The MULTI-TIMEFRAME ANALYSIS section is COMPUTED from actual higher-timeframe "
            "candles (EMA20/50, RSI, ATR, swing levels) - use it to determine whether the "
            "current move is a pullback within a larger trend or a reversal. The FUNDAMENTAL "
            "ANALYSIS section is news sentiment only - advisory, disregard if generic or stale. "
            "NOTE: HTF close/EMA values reflect the last CLOSED higher-timeframe bar (H1/H4) "
            "and may lag the current price slightly -- the live Bid/Ask and the active-timeframe "
            "candles are the current reference.)\n"
        )

    whisper_str = whisper_str or ""

    lessons_str = ""
    if getattr(config, "MEMORY_CONTEXT_ENABLED", True):
        try:
            from src.analytics import trade_evaluator
            lessons_str = trade_evaluator.evaluator.get_lessons_context()
        except Exception:
            pass

    recent_outcomes_str = ""
    if getattr(config, "MEMORY_CONTEXT_ENABLED", True):
        try:
            from src.analytics import decision_memory
            # Convert stored decisions into {signal, result, profit, commission}
            # for summarize_recent_outcomes. result di-set pas close (TP/SL/
            # SL-BEP/SL-trailing/manual), profit NET (sudah termasuk komisi) -
            # biar win/loss count AKURAT, bukan selalu "N/A".
            entries = decision_memory.memory._decisions.get(symbol, [])
            decisions = [{
                "signal": e.get("signal", "HOLD"),
                "result": e.get("result", "N/A"),
                "profit": e.get("profit"),
                "commission": e.get("commission", 0.0),
            } for e in entries]
            recent_outcomes_str = summarize_recent_outcomes(decisions)
            if recent_outcomes_str:
                recent_outcomes_str = f"\n### RECENT OUTCOMES (win/loss history only)\n{recent_outcomes_str}\n"
        except Exception:
            pass

    forecast_str = ""
    if getattr(config, "FORECAST_ENABLED", False) and getattr(config, "MEMORY_CONTEXT_ENABLED", True):
        try:
            from src.analytics import forecast_engine
            forecast_str = forecast_engine.forecaster.get_forecast_context()
        except Exception:
            pass
    if forecast_str:
        forecast_str = (
            "\n### MULTI-HORIZON FORECAST (separate model - informational only, not a rule)\n"
            f"{forecast_str}\n"
            "(NEUTRAL or disagreeing forecast does not require HOLD; aligned forecast "
            "does not by itself justify a trade.)\n"
        )

    calendar_str = ""
    try:
        from src.analytics import economic_calendar
        calendar_str = economic_calendar.calendar.get_context()
    except Exception:
        pass

    # Global portfolio context across all symbols
    global_portfolio_str = ""
    if all_open_positions and len(all_open_positions) > 0:
        gp_lines = []
        total_pnl = sum(p.get('profit', 0.0) for p in all_open_positions)
        for ap in all_open_positions:
            s_name = ap.get('symbol', '?')
            gp_lines.append(f"- {s_name}: {ap.get('type')} {ap.get('volume')} lot @ {ap.get('price_open')} (Floating P/L: ${ap.get('profit', 0.0):+.2f} USD)")
        global_portfolio_str = (
            "\n### GLOBAL PORTFOLIO CONTEXT (All active bot positions across symbols)\n"
            f"Total Active Positions: {len(all_open_positions)} | Net Floating P/L: ${total_pnl:+.2f} USD\n"
            + "\n".join(gp_lines) + "\n"
            "(Use this cross-asset awareness to detect conflicting currency exposures -- e.g. opposing CHF/EUR/GBP trades -- and take profit or cut exposure accordingly.)\n"
        )

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
            f"- 'CLOSE' if:\n" +
            f"  (a) INVALIDATION / THESIS BROKEN: The technical invalidation level is breached, a clear counter-trend reversal structure formed on {tf_label}, or momentum is failing.\n" +
            f"  (b) EARLY PROFIT TAKE / EXHAUSTION: The trade has captured substantial profit (e.g. >= 1R or near major opposing swing structure), is showing momentum exhaustion/divergence, OR conflicts with a stronger broad-market currency trend.\n" +
            f"- 'HOLD' if the thesis remains intact, the move is within normal healthy {tf_label} fluctuations, and has clear room to reach the full target.\n" +
            f"Do NOT recommend CLOSE for minor healthy pullbacks when the underlying trend structure is still fully intact.\n" +
            "Provide a concrete quantitative reason (e.g., 'CLOSE: Invalidation breached at 1.0965', 'CLOSE: Secure +$10 profit near H1 resistance with momentum divergence', or 'HOLD: Healthy pullback, thesis intact'). Never leave a ticket without an action.\n"
        )

    # Explicitly separate the two decisions so the LLM does not mix them:
    # "signal" = NEW ENTRY only. "position_actions" = EXISTING positions only.
    separation_note = ""
    if open_positions and len(open_positions) > 0:
        separation_note = (
            "\nIMPORTANT - TWO SEPARATE DECISIONS:\n"
            "1. The 'signal' field above is ONLY about opening a NEW trade. "
            "It must be BUY/SELL/HOLD based purely on whether a NEW entry is attractive now.\n"
            "2. The 'position_actions' list is ONLY about the EXISTING positions listed above. "
            "Do NOT let your opinion about existing positions change your 'signal', and do NOT "
            "let your entry bias change your position_actions. Evaluate each independently.\n"
        )

    # Key levels: PDH/PDL, today open, nearest round number, active WIB session.
    # Cached 5 min (D1 berubah sekali sehari) - murah, nggak nambah lag cycle.
    key_levels_str = _get_key_levels_str(symbol, current_tick.get('bid'))

    # ================================================================
    # PROMPT - 2 blok:
    #   Blok 1 (STATIS, prefix): instruksi + format. Di-cache via
    #     cache_control (lihat _execute_claude_single). Harus >= 1024
    #     token biar Anthropic benar-benar meng-cache.
    #   Blok 2 (DINAMIS): data pasar yang berubah tiap cycle.
    # ================================================================
    # Bagian yang BERUBAH per cycle (candle, tick, posisi, forecast, dll)
    market_data_block = f"""### MARKET DATA CONTEXT
Symbol: {symbol}
Timeframe: {tf_label}
Current Bid: {_fmt_price(current_tick['bid'], point_size)}
Current Ask: {_fmt_price(current_tick['ask'], point_size)}
Spread: {current_tick['spread']} points (point size = {_fmt_price(current_tick['point'])})
Spread note: this spread has ALREADY passed the bot's spread gate (max {config.max_spread_points_for(symbol)} pts for {symbol}), so treat it as NORMAL for this symbol. Do NOT use spread as a reason to reject a trade or pick HOLD. Spread only matters for SL placement: set SL >= 2x spread (the bot enforces this floor anyway).
{macro_str}
{key_levels_str}
{structure_str}
{delta_main_str}
{micro_candles_str}
{atr_gate_str}
{randomness_str}{quant_prob_str}{whisper_str}{lessons_str}{recent_outcomes_str}{forecast_str}{calendar_str}{global_portfolio_str}{positions_str}{separation_note}
{usd_context}"""

    # Bagian yang RELATIF STATIS antar cycle (instruksi + format output).
    # Dipakai dari template docs/prompt_claude.md (ANALYSIS FREEDOM +
    # RISK CONSTRAINTS). Statis = bisa di-cache provider (>= 1024 token).
    static_block = build_system_prompt(symbol, tf_label, asset_desc(symbol), point_size)

    # Gabung: statis dulu (cache), lalu data (dinamis)
    prompt = static_block + "\n\n" + market_data_block + "\n"
    # User requirement: prompt LLM bebas emoji (UI/CLI boleh). Strip semua
    # emoji dari sumber mana pun (macro, forecast, lessons, calendar, dll).
    return _strip_emoji(prompt)


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
        # Validate keys (setup/edge/invalidation are optional new fields -
        # model may omit them; HOLD responses won't have them)
        for key in ["signal", "confidence", "sl_points", "tp_points", "invalidation_price", "target_price", "reasoning", "setup", "edge", "invalidation", "entry_type", "entry_price"]:
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
                parsed["reasoning"] = "HOLD - No entry setup"

        return parsed
    except Exception as e:
        print(f"[LLM PARSE ERROR] Gagal memparsing JSON: {e}. Raw response: {text[:150]}")
        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "sl_points": None,
            "tp_points": None,
            "invalidation_price": None,
            "target_price": None,
            "reasoning": f"Gagal memparsing respon: {str(e)}"
        }


def _execute_openai_single(model_name, prompt, timeout_sec):
    is_reasoning = "gpt-5" in model_name.lower() or "o1" in model_name.lower() or "o3" in model_name.lower() or "o4" in model_name.lower()
    effort = (getattr(config, "OPENAI_REASONING_EFFORT", "low") or "").strip().lower()
    if is_reasoning:
        kwargs = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": "System: You are a professional financial trading assistant. Reasoning: 1-2 sentences (max 40 words); if HOLD, keep it to 1 short sentence (max 20 words) citing the single key level/indicator. Never enumerate.\n\n" + prompt}
            ],
            "response_format": {"type": "json_object"},
            "timeout": timeout_sec
        }
        if effort and effort != "none":
            try:
                response = openai_client.chat.completions.create(reasoning_effort=effort, **kwargs)
            except Exception as e_re:
                if "reasoning_effort" in str(e_re) or "unrecognized" in str(e_re).lower() or "unsupported" in str(e_re).lower():
                    response = openai_client.chat.completions.create(**kwargs)
                else:
                    raise e_re
        else:
            response = openai_client.chat.completions.create(**kwargs)
    else:
        response = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a professional financial trading assistant. Reasoning: 1-2 sentences (max 40 words); if HOLD, keep it to 1 short sentence (max 20 words) citing the single key level/indicator. Never enumerate."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=timeout_sec
        )
    content = response.choices[0].message.content
    return clean_json_response(content)


def query_forecast(prompt):
    """Queries forecast engine with 1 AI: gpt-5.4 (bukan mini) primary,
    fallback gemini-3.5-flash (bukan lite). Returns parsed JSON dict or None."""
    timeout_sec = getattr(config, "LLM_TIMEOUT_SECONDS", 5.0)
    primary_model = getattr(config, "FORECAST_MODEL", None) or config.OPENAI_MODEL
    fallback_model = getattr(config, "FORECAST_FALLBACK_MODEL", None) or config.GEMINI_MODEL

    # 1. Primary: OpenAI gpt-5.4
    if openai_client:
        try:
            res = _execute_openai_single(primary_model, prompt, timeout_sec)
            if isinstance(res, dict) and "forecast_bias" in res:
                return res
            print(f"[FORECAST WARNING] Response {primary_model} tidak punya forecast_bias: {str(res)[:120]}")
        except Exception as e:
            print(f" [FORECAST FALLBACK] {primary_model} error ({e}). Switching ke {fallback_model}...")

    # 2. Fallback: Gemini gemini-3.5-flash
    if gemini_client:
        try:
            from google.genai import types
            res = gemini_client.models.generate_content(
                model=fallback_model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            if res and res.text:
                parsed = clean_json_response(res.text)
                if isinstance(parsed, dict) and "forecast_bias" in parsed:
                    return parsed
        except Exception as e:
            print(f"[FORECAST FALLBACK ERROR] {e}")

    return None


def _resolve_openai_primary():
    """gpt-5.2 (kuota free 250k/hari) dipakai HANYA di OPENAI_PRIMARY_WINDOW_WIB
    (default 15:00-19:30 WIB, London session single mode); di luar window pakai
    OPENAI_DEFAULT_MODEL (gpt-4o-mini) biar kuota besar tidak habis di jam sepi
    (14 Agustus). OPENAI_FALLBACK_MODEL (o3-mini) = fallback error, dipisah."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    wib_now = datetime.now(ZoneInfo("Asia/Jakarta"))
    cur_min = wib_now.hour * 60 + wib_now.minute
    windows = getattr(config, "OPENAI_PRIMARY_WINDOW_WIB", []) or []
    for start_min, end_min in windows:
        if start_min <= end_min:
            if start_min <= cur_min < end_min:
                return config.OPENAI_MODEL
        else:  # window lintas tengah malam (mis. 21:00-02:00)
            if cur_min >= start_min or cur_min < end_min:
                return config.OPENAI_MODEL
    return config.OPENAI_DEFAULT_MODEL


def query_openai(prompt):
    """Queries OpenAI API with timeout and fallback model support."""
    if not openai_client:
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "OpenAI API Key tidak diset."}

    primary_model = _resolve_openai_primary()
    fallback_model = getattr(config, "OPENAI_FALLBACK_MODEL", None)  # o3-mini (fallback error)
    timeout_sec = getattr(config, "LLM_TIMEOUT_SECONDS", 25.0)

    try:
        return _execute_openai_single(primary_model, prompt, timeout_sec)
    except Exception as e:
        if fallback_model and fallback_model != primary_model:
            print(f" [OPENAI FALLBACK] Model {primary_model} lambat/error ({e}). Switching ke fallback ({fallback_model})...")
            try:
                return _execute_openai_single(fallback_model, prompt, timeout_sec)
            except Exception as fb_err:
                print(f"[OPENAI FALLBACK ERROR] {fb_err}")
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"OpenAI Error: {str(fb_err)}"}
        else:
            print(f"[OPENAI ERROR] {e}")
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"OpenAI Error: {str(e)}"}


def _execute_gemini_single(model_name, prompt, timeout_sec, thinking_budget=None):
    """Execute a single Gemini call with strict JSON and thinking budget."""
    if not gemini_client:
        raise RuntimeError("Gemini client is not initialized.")
    from google.genai import types
    if thinking_budget is None:
        thinking_budget = getattr(config, "GEMINI_THINKING_BUDGET", 1024)
    cfg_kwargs = dict(response_mime_type="application/json")
    if thinking_budget and thinking_budget > 0:
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)

    def _call(mod):
        res = gemini_client.models.generate_content(
            model=mod,
            contents=prompt,
            config=types.GenerateContentConfig(**cfg_kwargs)
        )
        return clean_json_response(res.text)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_call, model_name)
        return fut.result(timeout=timeout_sec)


def query_gemini(prompt):
    """Queries Gemini API with timeout and fallback model support."""
    if not gemini_client:
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "Gemini API Key tidak diset."}

    primary_model = config.GEMINI_MODEL
    fallback_model = getattr(config, "GEMINI_FALLBACK_MODEL", None)
    timeout_sec = getattr(config, "LLM_TIMEOUT_SECONDS", 25.0)

    try:
        return _execute_gemini_single(primary_model, prompt, timeout_sec)
    except Exception as e:
        if fallback_model and fallback_model != primary_model:
            print(f" [GEMINI FALLBACK] Model {primary_model} lambat/error ({e}). Switching ke fallback ({fallback_model})...")
            try:
                return _execute_gemini_single(fallback_model, prompt, timeout_sec)
            except Exception as fb_err:
                print(f"[GEMINI FALLBACK ERROR] {fb_err}")
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Gemini Error: {str(fb_err)}"}
        else:
            print(f"[GEMINI ERROR] {e}")
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Gemini Error: {str(e)}"}


def _execute_claude_single(model_name, prompt, timeout_sec):
    system_text = (
        "You are a professional financial trading assistant. "
        "Always respond with valid JSON only. Reasoning: 1-2 sentences (max 40 words); "
        "if HOLD, keep it to 1 short sentence (max 20 words) citing the single key "
        "level/indicator. Never enumerate."
    )
    # Prompt caching: pecah prompt jadi blok statis (instruksi, DI DEPAN) +
    # dinamis (data pasar, DI BELAKANG). cache_control ditaruh di AKHIR blok
    # statis - prefix yang identik antar request. System terlalu pendek
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
        # Tidak ketemu marker - fallback: cache seluruh prompt (kalau statis)
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


def _execute_deepseek_single(model_name, prompt, timeout_sec, reasoning_effort=None):
    """Query DeepSeek (OpenAI-compatible API). model_name passed WITHOUT the
    'deepseek/' prefix (e.g. 'deepseek-v4-flash').
    reasoning_effort: "low"/"medium"/"high" -> thinking mode; None/"" -> fast mode tanpa reasoning (deepseek-chat, 2-3s)."""
    raw_model = model_name.split("/", 1)[1] if "/" in model_name else model_name
    if reasoning_effort is None:
        if "chat" in raw_model.lower():
            reasoning_effort = ""
        else:
            reasoning_effort = (getattr(config, "DEEPSEEK_REASONING_EFFORT", "none") or "").strip()

    kwargs = dict(
        model=raw_model,
        messages=[
            {"role": "system", "content": "You are a professional financial trading assistant. Respond with valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        response_format={"type": "json_object"},
        timeout=timeout_sec,
    )
    if reasoning_effort and reasoning_effort.lower() not in ("none", "off", "false", "", "disabled"):
        kwargs["reasoning_effort"] = reasoning_effort
        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
    else:
        kwargs["temperature"] = 0.2
        # DeepSeek API format to completely disable reasoning thinking CoT
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    response = deepseek_client.chat.completions.create(**kwargs)
    return clean_json_response(response.choices[0].message.content)


def query_deepseek(prompt):
    """Queries DeepSeek API (e.g. deepseek-v4-flash) with timeout and fallback support (e.g. Gemini 2.5 Flash Lite)."""
    primary_model = getattr(config, "DEEPSEEK_MODEL", "deepseek-v4-flash")
    fallback_model = getattr(config, "DEEPSEEK_FALLBACK_MODEL", "gemini-2.5-flash-lite")
    timeout_sec = getattr(config, "LLM_TIMEOUT_SECONDS", 35.0)

    if not deepseek_client:
        if gemini_client and "gemini" in fallback_model.lower():
            return _execute_gemini_single(fallback_model, prompt, timeout_sec)
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "DeepSeek API Key tidak diset."}

    try:
        return _execute_deepseek_single(primary_model, prompt, timeout_sec)
    except Exception as e:
        if fallback_model and fallback_model != primary_model:
            print(f" [DEEPSEEK FALLBACK] Model {primary_model} lambat/error ({e}). Switching ke fallback ({fallback_model})...")
            try:
                if "gemini" in fallback_model.lower():
                    return _execute_gemini_single(fallback_model, prompt, timeout_sec, thinking_budget=1024)
                else:
                    return _execute_deepseek_single(fallback_model, prompt, timeout_sec, reasoning_effort="")
            except Exception as fb_err:
                print(f"[DEEPSEEK FALLBACK ERROR] {fb_err}")
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"DeepSeek Fallback Error: {str(fb_err)}"}
        else:
            print(f"[DEEPSEEK ERROR] {e}")
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"DeepSeek Error: {str(e)}"}


def query_claude(prompt):
    """Queries Anthropic Claude API (claude-sonnet-4-6) with timeout and fallback support."""
    primary_model = getattr(config, "CLAUDE_MODEL", "claude-sonnet-4-6")
    fallback_model = getattr(config, "CLAUDE_FALLBACK_MODEL", "claude-haiku-4-5-20251001")
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
            print(f" [CLAUDE FALLBACK] Model {primary_model} lambat/error ({e}). Switching ke fallback ({fallback_model})...")
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



def get_multi_llm_decisions(symbol, df, current_tick, macro_context=None, open_positions=None,
                            whisper_str=None, all_open_positions=None):
    """
    Query only the AI slots active for the current WIB time window.
    mode = single        -> OpenAI only (00:00-14:59 / 21:31-23:59)
    mode = dual          -> OpenAI + DeepSeek (15:00-19:29, London Session)
    mode = triple        -> OpenAI + Gemini + Claude (19:30-21:30, London-NY overlap)
    """
    prompt = prepare_prompt(symbol, df, current_tick, macro_context, open_positions, whisper_str, all_open_positions=all_open_positions)

    active_models = config.active_ai_model_names()
    model_fns = {
        "OpenAI": query_openai,
        "Gemini": query_gemini,
        "DeepSeek": query_deepseek,
        "Claude": query_claude,
    }
    selected = {name: model_fns[name] for name in active_models if name in model_fns}

    results = {}
    latencies = {}
    start_total = time.time()
    pending_models = set(selected.keys())
    stop_spinner = threading.Event()

    def _spinner_task():
        spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        idx = 0
        while not stop_spinner.is_set():
            elapsed = time.time() - start_total
            waiting_for = ", ".join(sorted(pending_models)) if pending_models else "finalizing..."
            spin = spinner_chars[idx % len(spinner_chars)]
            sys.stdout.write(f"\r  {UI.CYAN}{spin}{UI.RST} {UI.DIM}Menunggu respon AI ({elapsed:.1f}s) -> [Menunggu: {waiting_for}]...{UI.RST}   ")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.1)
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

    spinner_thread = threading.Thread(target=_spinner_task, daemon=True)
    spinner_thread.start()

    def _query_timed(query_fn, p):
        t0 = time.time()
        res = query_fn(p)
        elapsed = time.time() - t0
        return res, elapsed

    # Run in parallel using thread pool (sized to active model count)
    max_workers = max(1, len(selected))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_model = {
            executor.submit(_query_timed, fn, prompt): name for name, fn in selected.items()
        }

        for future in concurrent.futures.as_completed(future_to_model):
            model_name = future_to_model[future]
            try:
                data, elapsed = future.result()
                results[model_name] = data
                latencies[model_name] = elapsed
                pending_models.discard(model_name)
                sys.stdout.write(f"\r{UI.clear_line()}  {UI.GREEN}✓{UI.RST} {UI.BOLD}{model_name}{UI.RST} selesai dalam {elapsed:.2f}s\n")
                sys.stdout.flush()
            except Exception as exc:
                print(f"\r{UI.clear_line()}[LLM CLIENT ERROR] Model {model_name} generated an exception: {exc}")
                results[model_name] = {"signal": "HOLD", "confidence": 0.0, "reasoning": str(exc)}
                latencies[model_name] = 0.0
                pending_models.discard(model_name)

    stop_spinner.set()
    spinner_thread.join(timeout=0.5)

    total_elapsed = time.time() - start_total
    mode = config.get_ai_mode()
    lat_str = " | ".join([f"{m}: {latencies.get(m, 0.0):.2f}s" for m in active_models if m in latencies])
    print(f" {UI.tag('AI LATENCY', UI.CYAN)} mode={mode} ({len(results)} model) | {lat_str} (Total: {total_elapsed:.2f}s)")
    return results

