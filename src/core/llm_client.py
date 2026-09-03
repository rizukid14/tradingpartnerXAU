import json
import re
import time
import sys
import threading
import concurrent.futures
from datetime import datetime
from zoneinfo import ZoneInfo
from openai import OpenAI
from google import genai
import config
from src.core.cli_theme import UI

_WIB = ZoneInfo("Asia/Jakarta")

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
    _http_opts = {}
    if getattr(config, "GEMINI_API_BASE", None):
        _http_opts["api_endpoint"] = config.GEMINI_API_BASE
    if _http_opts:
        gemini_client = genai.Client(api_key=config.GEMINI_API_KEY, http_options=_http_opts)
    else:
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


# ================================================================
# SYSTEM PROMPT TEMPLATE (docs/prompt_claude.md)
# "We set guardrails, the LLM sets strategy."
# Static per-bot constitution - build once per instance, reuse across
# cycles so provider-side prompt/context caching stays effective.
# ================================================================
_SYSTEM_PROMPT_TEMPLATE = """### ROLE
You are an expert {{TIMEFRAME}} short-term intraday-swing analyst for {{SYMBOL}} ({{ASSET_DESC}}). Find a high-quality actionable setup with R:R >= 1.25, or return HOLD. Do not force trades.

### 1. DECISION FRAMEWORK (Analyze in this strict order)
1. Regime: Determine HTF directional bias and {{TIMEFRAME}} market state: trend, pullback, breakout, or range.
2. Location & Clearance: Determine whether price is near a meaningful structural level or trapped in mid-range. Measure clearance (room available to opposing barrier).
3. Setup: Choose exactly one:
   - CONTINUATION: Trade with HTF trend after pullback/retest into value/discount zone.
   - EXHAUSTION: Fade an extended move at major support/resistance with rejection wick + weakening momentum.
   - BREAKOUT: Trade only after decisive {{TIMEFRAME}} close beyond a key level (or pending stop for untriggered breakout).
   - NONE: No valid structural setup -> select HOLD.
4. Entry: Market (if actionable now) or Pending (buy_limit/sell_limit/buy_stop/sell_stop at trigger level).
5. Invalidation (SL): Nearest structural level behind entry that proves thesis wrong.
6. Target (TP): Next realistic opposing structural level (must not exceed available clearance).
7. Calculate SL/TP distances strictly FROM ENTRY PRICE:
   - sl_points = |entry_price - invalidation_price| / point_size
   - tp_points = |target_price - entry_price| / point_size
   - Verify R:R = tp_points / sl_points >= 1.25. If R:R < 1.25 -> MUST select HOLD.

### 2. WHAT IS NOT AN ENTRY SIGNAL (ANTI-NARRATIVE RULES)
A valid trade requires structure + location + actionable setup + valid invalidation + sufficient clearance.
- DATA INTEGRITY: Use ONLY exact prices, levels, and indicators provided in the payload -- NEVER hallucinate unlisted data.
- HTF bias alone is NOT an entry signal.
- EMA alignment alone is NOT an entry signal.
- RSI overbought/oversold alone is NOT an entry signal.
- Mid-range location without clear clearance is NOT an entry signal.
- Past outcomes / win-loss history (if present) do NOT dictate current directional signal.

### 3. HARD EXECUTION RULES
- Independent Roles: `signal` is strictly for NEW entries; `position_actions` is strictly for managing existing open tickets (`signal: HOLD` does NOT force close open positions).
- BUY only when bullish setup exists. SELL only when bearish setup exists. HOLD when setup is absent/unclear.
- Proximity Traps: Avoid blind BUY market orders directly below major resistance (< 0.3x ATR away) unless closed above it. Avoid blind SELL market orders directly above major support (< 0.3x ATR away) unless closed below it.
- Execution Choice (Independent Discretion): Decide independently between "market" (instant execution at live price) and pending limit ("buy_limit"/"sell_limit" at optimal anchor) based on current momentum, candle wicks, and Risk:Reward. If price is already reacting strongly or at the optimal level, market execution captures the move immediately. If price has not reached the optimal discount/premium level and waiting for a pullback provides superior R:R, use a pending limit order. Pending entry must be at least 2x spread and within ~1.5x ATR from current price. BUY: market/buy_stop/buy_limit. SELL: market/sell_stop/sell_limit.
- Unit Definition: sl_points & tp_points are broker POINTS from ENTRY PRICE.
  * {{POINTS_EXPLANATION}}
- Safety Floors: Give your honest structural levels; the bot engine automatically widens SL/TP to meet broker safety floors (>= 1.3x ATR {{TIMEFRAME}}) and enforces min R:R 1.25.
- Confidence: Represents structural setup validity (0.00 to 1.00), NOT statistical win probability.

### 4. OUTPUT FORMAT
Return ONE valid JSON object only -- no surrounding markdown text:
{
  "market_regime": "BULL_TREND" | "BEAR_TREND" | "RANGE",
  "setup": "CONTINUATION" | "EXHAUSTION" | "BREAKOUT" | "NONE",
  "state": "FAR" | "TESTING" | "REJECTION" | "COMPRESSION" | "BREAKOUT",
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": float (0.00 to 1.00),
  "rr_valid": true | false,
  "entry_type": "market" | "buy_stop" | "sell_stop" | "buy_limit" | "sell_limit",
  "entry_price": float (null if entry_type == "market"),
  "sl_points": integer (null if HOLD),
  "tp_points": integer (null if HOLD),
  "invalidation_price": float (null if HOLD),
  "target_price": float (null if HOLD),
  "reasoning": "string (MAX 25 WORDS: structural event and verified R:R)"
}

"position_actions": include ONLY when open positions are listed above -- for each ticket: {"ticket": number, "action": "CLOSE" | "HOLD", "reason": "max 5 words"}"""


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


def _structure_block(df, current_tick, atr_points=0, tf_label="M30"):
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

    # 1. Active Timeframe Indicators
    ind_lines = []
    ema20 = float(df["ema_20"].iloc[-1]) if "ema_20" in df.columns else None
    ema50 = float(df["ema_50"].iloc[-1]) if "ema_50" in df.columns else None
    if ema20 is not None and ema50 is not None:
        gap = (ema20 - ema50) / point
        rel_ema20 = (close - ema20) / point
        pos = "ABOVE" if rel_ema20 > 0 else "BELOW"
        ind_lines.append(f"- EMA20 {_fmt_price(ema20, point)} | EMA50 {_fmt_price(ema50, point)} (gap {int(abs(gap))} pts) | close is {int(abs(rel_ema20))} pts {pos} EMA20")
    if "ema_200" in df.columns and len(df) >= 200:
        ema200 = float(df["ema_200"].iloc[-1])
        rel200 = (close - ema200) / point
        regime = "BULLISH regime" if rel200 > 0 else "BEARISH regime"
        ind_lines.append(f"- EMA200 {_fmt_price(ema200, point)} (close {int(abs(rel200))} pts {'ABOVE' if rel200 > 0 else 'BELOW'}, {regime})")
    if atr_points and atr_points > 0:
        ind_lines.append(f"- ATR14 {_fmt_price(float(df['atr_14'].iloc[-1]), point)} (= {atr_points} pts)")

    if ind_lines:
        lines.append(f"### TECHNICAL INDICATORS ({tf_label} Active Timeframe)")
        lines.extend(ind_lines)
        lines.append("")

    # 2. 50-bar Short-Term Window
    df_50 = df.tail(min(50, len(df)))
    h50, l50 = float(df_50["high"].max()), float(df_50["low"].min())
    diff50 = h50 - l50 if h50 != l50 else point
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
    loc_pct = round(((close - l50) / diff50) * 100.0, 1)
    if loc_pct >= 75.0:
        loc_desc = "Near High / Resistance Zone"
    elif loc_pct <= 25.0:
        loc_desc = "Near Low / Support Zone"
    else:
        loc_desc = "Mid-Range / Value Zone"

    lines.append(f"### INTRADAY STRUCTURE (50-bar {tf_label} Window)")
    lines.append(f"- 50-bar {tf_label} Swing: High {_fmt_price(h50, point)} | Low {_fmt_price(l50, point)} | Range: {int(diff50/point)} pts")
    lines.append(f"- Location in 50-bar Range: {loc_pct:.1f}% ({loc_desc})")
    lines.append(f"- Clearance: {int(to_h50)} pts to Resistance High ({_fmt_price(h50, point)}) | {int(to_l50)} pts to Support Low ({_fmt_price(l50, point)})")
    lines.append(f"- 50-bar {tf_label} Fib ({label50}): 38.2% {_fmt_price(f382_50, point)} | 50% {_fmt_price(f500_50, point)} | 61.8% {_fmt_price(f618_50, point)}")

    # 3. 100-bar Macro Multi-Day Window
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

        lines.append(f"\n### MACRO STRUCTURE (100-bar {tf_label} Window)")
        lines.append(f"- 100-bar {tf_label} Swing: High {_fmt_price(h100, point)} | Low {_fmt_price(l100, point)} | Range: {int(diff100/point)} pts")
        lines.append(f"- 100-bar {tf_label} Fib ({label100}): 38.2% {_fmt_price(f382_100, point)} | 50% {_fmt_price(f500_100, point)} | 61.8% {_fmt_price(f618_100, point)}")

    return "\n".join(lines)


def _momentum_summary(df_micro, df_main, point_size=0.01, micro_tf_label="M5", main_tf_label="H1"):
    """Momentum summary di timeframe micro (M15 utk FX / M5 utk BTC-XAU),
    dihitung LOKAL. Murni data/angka, TANPA verdict atau interpretasi apa pun
    (user: "harus informatif") — AI yang menilai sendiri.

    Isi: ADX micro + delta 5 bar, arah (+DI/-DI), harga vs EMA20 micro, dan
    kontras ADX micro vs ADX timeframe aktif.
    Fix 21 Agustus.
    """
    try:
        if df_micro is None or len(df_micro) < 10:
            return ""
        if df_main is None or "adx_14" not in df_main.columns:
            return ""
        if not point_size or point_size <= 0:
            point_size = 0.01

        # ---- ADX micro + delta (5 bar lalu) ----
        if "adx_14" not in df_micro.columns:
            return ""
        adx_now = float(df_micro["adx_14"].iloc[-1])
        adx_prev = float(df_micro["adx_14"].iloc[-6]) if len(df_micro) >= 6 else adx_now
        if adx_now != adx_now or adx_prev != adx_prev:  # NaN guard
            return ""
        delta_adx = adx_now - adx_prev
        if delta_adx >= 2.0:
            mom_label = "EXPANDING"
        elif delta_adx <= -2.0:
            mom_label = "WEAKENING"
        else:
            mom_label = "STABLE"

        # ---- Arah: +DI / -DI (ADX buta arah) ----
        di_str = ""
        try:
            from ta.trend import ADXIndicator
            di = ADXIndicator(high=df_micro["high"], low=df_micro["low"],
                              close=df_micro["close"], window=14)
            di_pos = float(di.adx_pos().iloc[-1])
            di_neg = float(di.adx_neg().iloc[-1])
            if di_pos == di_pos and di_neg == di_neg:
                di_str = (f" | +DI {di_pos:.1f} {'>' if di_pos > di_neg else '<'} "
                          f"-DI {di_neg:.1f}")
        except Exception:
            pass

        # ---- Harga vs EMA20 micro (cross-check) ----
        ema20_str = ""
        if "ema_20" in df_micro.columns:
            ema20 = float(df_micro["ema_20"].iloc[-1])
            close = float(df_micro["close"].iloc[-1])
            if ema20 == ema20:
                rel = int((close - ema20) / point_size)
                side = "ABOVE" if rel > 0 else "BELOW"
                ema20_str = f"\n- Harga {abs(rel)} pts {side} EMA20 {micro_tf_label}"

        # ---- Kontras vs ADX timeframe aktif (murni data, tanpa interpretasi) ----
        adx_main = float(df_main["adx_14"].iloc[-1])
        contrast_str = ""
        if adx_main == adx_main:
            if mom_label == "WEAKENING":
                contrast_str = (f"\n- ADX {main_tf_label} {adx_main:.1f} vs ADX {micro_tf_label} "
                                f"{adx_now:.1f} (turun {abs(delta_adx):.1f} dalam 5 bar)")
            elif mom_label == "EXPANDING":
                contrast_str = (f"\n- ADX {main_tf_label} {adx_main:.1f} vs ADX {micro_tf_label} "
                                f"{adx_now:.1f} (naik {abs(delta_adx):.1f} dalam 5 bar)")
            else:
                contrast_str = (f"\n- ADX {main_tf_label} {adx_main:.1f} vs ADX {micro_tf_label} "
                                f"{adx_now:.1f} (stabil dalam 5 bar)")

        return (
            f"### {micro_tf_label} MOMENTUM SUMMARY (computed locally)\n"
            f"- ADX {micro_tf_label}: {adx_now:.1f} (vs {adx_prev:.1f} 5 bar lalu, delta {delta_adx:+.1f})"
            f"{di_str}{ema20_str}{contrast_str}"
        )
    except Exception:
        return ""



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
                         "rules in the RISK CONSTRAINTS section above")
        pips_val = round(lo_pts / 10.0, 1)
        pips_int = int(round(lo_pts / 10.0))
        return (
            f"### CRITICAL UNIT DEFINITION: POINTS vs PIPS vs PRICE MOVEMENT\n"
            f"You MUST calculate and return Stop Loss and Take Profit in broker **POINTS** (integer), NOT pips, NOT USD price.\n"
            f"For {symbol} (with broker point size = {pt_str}):\n"
            f"- 1 point = {pt_str} price units.\n"
            f"- 10 points = 1 pip = {pip_str} price movement.\n"
            f"- 100 points = 10 pips = {_fmt_price(point_size * 100) if point_size else '1.00'} price movement.\n"
            f"- Typical Stop Loss distance for {symbol} is usually {lo_pts} to {hi_pts} points{gate_note}.\n\n"
            f"CRITICAL WARNING:\n"
            f"Double-check your units! If you want a Stop Loss of {pips_val} pips (~{lo_pts} points), you MUST return {lo_pts} points. "
            f"If you accidentally return {pips_int}, it sets a Stop Loss of just {pips_int} points "
            f"({pips_int/10:.1f} pips / {_fmt_price(pips_int * (point_size or 0.01))} price movement), "
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
        from config import mt5 as _mt5
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
    from config import mt5 as _mt5
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
        if is_xau:
            xau_floor = config.LLM_SAFETY_FLOOR_XAU_PTS
            atr_pts_xau = _atr_points_for(symbol, config.get_timeframe(symbol))
            if atr_pts_xau and atr_pts_xau > 0:
                xau_floor = max(20, int(config.LLM_XAU_FLOOR_ATR_MULT * atr_pts_xau))
            lo_pts = xau_floor
            hi_pts = max(1000, int(lo_pts * 2.5))
            return (
                f"- Calculate 'sl_points' and 'tp_points' strictly from your ENTRY PRICE (in broker POINTS): sl_points = |entry_price - invalidation_price| / point_size, tp_points = |target_price - entry_price| / point_size.\n"
                f"- The bot enforces minimum floors automatically: SL >= {lo_pts} pts (~{config.LLM_XAU_FLOOR_ATR_MULT}x ATR M30) and TP >= {min_rr}x SL. Give your honest structural levels; the bot handles the safety floors.\n"
            )
        elif is_btc:
            return (
                f"- Calculate 'sl_points' and 'tp_points' strictly from your ENTRY PRICE in broker POINTS (typically 20000 to 60000 points / $200-$600): sl_points = |entry_price - invalidation_price| / point_size, tp_points = |target_price - entry_price| / point_size.\n"
                f"- The bot enforces minimum floors automatically: SL >= 2x current spread and TP >= {min_rr}x SL.\n"
            )
        else:
            tf_str = str(timeframe or "M30")
            tf_mt5 = config.TIMEFRAME_MAP.get(tf_str, config.mt5.TIMEFRAME_M30)
            fx_floor = config.LLM_SAFETY_FLOOR_FX_PTS
            atr_pts_fx = _atr_points_for(symbol, tf_mt5)
            if atr_pts_fx and atr_pts_fx > 0:
                fx_floor = max(20, int(config.LLM_FX_FLOOR_ATR_MULT * atr_pts_fx))
            return (
                f"- Calculate 'sl_points' and 'tp_points' strictly from your ENTRY PRICE (in broker POINTS): sl_points = |entry_price - invalidation_price| / point_size, tp_points = |target_price - entry_price| / point_size.\n"
                f"- The bot enforces minimum safety floors automatically: SL >= max(2x spread, ~{fx_floor} pts = {config.LLM_FX_FLOOR_ATR_MULT}x ATR {tf_str}) and TP >= {min_rr}x SL. Give your honest structural levels; the bot handles the floors.\n"
            )

    # Mode ATR-Based: ATR HARD GATE (non-negotiable) berlaku untuk mode ATR
    sl_mult = config.atr_sl_multiplier()
    tp_mult = config.atr_tp_multiplier()
    return (
        f"- Calculate 'sl_points' and 'tp_points' strictly from your ENTRY PRICE (in broker POINTS): sl_points = |entry_price - invalidation_price| / point_size, tp_points = |target_price - entry_price| / point_size.\n"
        f"- HARD GATE (non-negotiable): SL >= {sl_mult}x ATR and TP >= {tp_mult}x ATR (minimum R:R 2:1). If structural levels cannot meet the gate, select HOLD.\n"
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
            mt5_connector.get_valid_trade_symbol(symbol), config.mt5.TIMEFRAME_D1, 0, 15
        )
        if rates is None or len(rates) < 2:
            return ""
        prev = rates[-2]  # previous day
        today = rates[-1]  # today
        pdh = float(prev['high'])
        pdl = float(prev['low'])
        today_open = float(today['open'])
        today_high = float(today['high'])
        today_low = float(today['low'])

        # Hitung D1 ADR 14-hari dan sisa ruang pergerakan harian
        point = None
        si = mt5_connector.mt5.symbol_info(mt5_connector.get_valid_trade_symbol(symbol))
        if si:
            point = si.point
        if not point or point <= 0:
            point = 0.00001

        daily_used_pts = int((today_high - today_low) / point)
        if len(rates) >= 15:
            ranges = [(float(r['high']) - float(r['low'])) / point for r in rates[:-1]]
            adr_d1_pts = int(sum(ranges[-14:]) / len(ranges[-14:]))
        else:
            adr_d1_pts = max(1, int(daily_used_pts * 1.5))
        remaining_adr_pts = max(0, adr_d1_pts - daily_used_pts)
        pct_used = int((daily_used_pts / adr_d1_pts * 100)) if adr_d1_pts > 0 else 0

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
            f"### KEY LEVELS & DAILY RANGE\n"
            f"- Previous Day High: {_fmt_price(pdh, point)} | Previous Day Low: {_fmt_price(pdl, point)}\n"
            f"- Today Open: {_fmt_price(today_open, point)}\n"
            f"- Daily ADR (14D): {daily_used_pts} pts used / {adr_d1_pts} pts ADR ({pct_used}%) | Remaining Expected: ~{remaining_adr_pts} pts\n"
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
            "for when to use each. The bot supports both.\n"
            "Please ensure your setup is actionable either at the current price (Market Order) "
            "OR at a specified trigger level (Pending Order: buy_stop/sell_stop/buy_limit/sell_limit "
            "with entry_price). If your thesis relies on a breakout or pullback trigger that has not "
            "triggered yet, use the appropriate pending order entry_type and entry_price, or select "
            "HOLD if conviction is low."
        )
        pending_rules_block = (
            "\n### ORDER TYPE SELECTION (Independent Discretion)\n"
            "You have full analytical autonomy to select 'market' for immediate execution or 'buy_limit'/'sell_limit' for a pending order:\n"
            "- Evaluate live price action, candle wicks, micro momentum, and the quantitative distance to optimal entry.\n"
            "- Choose 'market' if the setup is actively moving and waiting for a deeper pullback risks missing the move.\n"
            "- Choose 'buy_limit' or 'sell_limit' if price is extended from the optimal structural anchor and waiting for a discount pullback offers superior Risk:Reward.\n"
            "- PENDING STOP RULE: Thesis is a BREAKOUT / momentum continuation beyond a level: use buy_stop (BUY) or sell_stop (SELL). entry_price = the breakout level (beyond current price).\n"
            "- Direction consistency is mandatory: BUY -> market/buy_stop/buy_limit only; SELL -> market/sell_stop/sell_limit only.\n"
            "- entry_price must be at least 2x current spread away from the current price, and no further than ~1.5x ATR from it. If your level is outside this band, the bot rejects the pending order (or falls back to market).\n"
            "- An executed pending order becomes a normal position with your sl_points/tp_points -- same risk rules apply.\n"
            "- If you are not confident the level will trigger or pullback will reach, output 'market' or HOLD instead."
        )
        pending_fields = (
            '  "entry_type": "market" | "buy_stop" | "sell_stop" | "buy_limit" | "sell_limit",\n'
            '  "entry_price": float (REQUIRED if entry_type != "market"),\n'
        )
    else:
        execution_note = (
            "Any BUY or SELL signal you output will be executed immediately at the current "
            "market price (Market Order). The bot does not support pending orders.\n"
            "Please ensure your setup is actionable at the current market price. If your thesis "
            "relies on a trigger that has not happened yet (e.g. waiting for a breakout close), "
            "select HOLD to wait for that confirmation."
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

def clean_json_response(text):
    """Cleans markdown JSON wrappers (```json ... ```) and parses the JSON."""
    try:
        text_clean = text.strip()
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text_clean, re.DOTALL)
        if match:
            text_clean = match.group(1)
        else:
            start = text_clean.find('{')
            end = text_clean.rfind('}')
            if start != -1 and end != -1:
                text_clean = text_clean[start:end+1]
        
        try:
            parsed = json.loads(text_clean)
        except json.JSONDecodeError:
            parsed = {}
            for line in text_clean.splitlines():
                m = re.match(r'\s*"(\w+)":\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|null|true|false)', line)
                if m:
                    key, val = m.group(1), m.group(2)
                    try:
                        parsed[key] = json.loads(val)
                    except json.JSONDecodeError:
                        parsed[key] = val.strip('"')

        for key in [
            "signal", "confidence", "sl_points", "tp_points", "invalidation_price", "target_price",
            "reasoning", "setup", "state", "market_regime", "entry_type", "entry_price",
            "rr_valid", "trend", "velocity", "position_actions", "verdict", "risk_flag", "veto_reason"
        ]:
            if key not in parsed:
                parsed[key] = None

        if not parsed.get("signal") and parsed.get("direction"):
            parsed["signal"] = parsed["direction"]

        if parsed.get("signal"):
            parsed["signal"] = str(parsed["signal"]).upper()
            if parsed["signal"] not in ["BUY", "SELL", "HOLD"]:
                parsed["signal"] = "HOLD"
        else:
            parsed["signal"] = "HOLD"

        for str_key in ["setup", "state", "market_regime", "trend", "velocity", "verdict", "risk_flag"]:
            if parsed.get(str_key):
                parsed[str_key] = str(parsed[str_key]).upper()

        try:
            if parsed.get("confidence") is not None:
                parsed["confidence"] = float(parsed["confidence"])
            else:
                parsed["confidence"] = 0.0 if parsed["signal"] == "HOLD" else 0.5
        except (ValueError, TypeError):
            parsed["confidence"] = 0.0 if parsed["signal"] == "HOLD" else 0.5

        for pt_key in ["sl_points", "tp_points"]:
            if parsed.get(pt_key) is not None:
                try:
                    parsed[pt_key] = int(round(float(parsed[pt_key])))
                except (ValueError, TypeError):
                    pass

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
            "verdict": "REJECT",
            "reasoning": f"Gagal memparsing respon: {str(e)}"
        }


def _execute_openai_single(model_name, prompt, timeout_sec):
    is_reasoning = "gpt-5" in model_name.lower() or "o1" in model_name.lower() or "o3" in model_name.lower() or "o4" in model_name.lower()
    effort = (getattr(config, "OPENAI_REASONING_EFFORT", "low") or "").strip().lower()
    if is_reasoning:
        kwargs = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": "System: You are a professional financial trading assistant. Always respond with valid JSON only.\n\n" + prompt}
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
                {"role": "system", "content": "You are a professional financial trading assistant. Respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=timeout_sec
        )
    content = response.choices[0].message.content
    return clean_json_response(content)


def query_openai(prompt):
    """Queries OpenAI API with timeout and fallback support."""
    primary_model = getattr(config, "OPENAI_MODEL", "o4-mini")
    fallback_model = getattr(config, "OPENAI_FALLBACK_MODEL", "o3-mini")
    timeout_sec = getattr(config, "LLM_TIMEOUT_SECONDS", 35.0)

    if not openai_client:
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "OpenAI API Key tidak diset."}

    try:
        return _execute_openai_single(primary_model, prompt, timeout_sec)
    except Exception as e:
        if fallback_model and fallback_model != primary_model:
            print(f" [OPENAI FALLBACK] Model {primary_model} error ({e}). Switching ke fallback ({fallback_model})...")
            try:
                return _execute_openai_single(fallback_model, prompt, timeout_sec)
            except Exception as fb_err:
                print(f"[OPENAI FALLBACK ERROR] {fb_err}")
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"OpenAI Error: {str(fb_err)}"}
        else:
            print(f"[OPENAI ERROR] {e}")
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"OpenAI Error: {str(e)}"}


def _execute_gemini_single(model_name, prompt, timeout_sec, thinking_budget=None):
    from google.genai import types

    if thinking_budget is None:
        thinking_budget = getattr(config, "GEMINI_THINKING_BUDGET", 1024)

    def _call(mod):
        cfg_kwargs = dict(
            response_mime_type="application/json",
            temperature=0.2,
        )
        if thinking_budget and thinking_budget > 0:
            cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking_budget)

        cfg = types.GenerateContentConfig(**cfg_kwargs)
        return gemini_client.models.generate_content(
            model=mod,
            contents=prompt,
            config=cfg
        )

    try:
        res = _call(model_name)
    except Exception as e_tb:
        if "thinking_config" in str(e_tb).lower() or "budget" in str(e_tb).lower() or "unsupported" in str(e_tb).lower():
            cfg_fb = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2)
            res = gemini_client.models.generate_content(model=model_name, contents=prompt, config=cfg_fb)
        else:
            raise e_tb

    if res and res.text:
        return clean_json_response(res.text)
    return {"signal": "HOLD", "confidence": 0.0, "reasoning": "Respon kosong dari Gemini"}


def query_gemini(prompt):
    """Queries Gemini API with timeout and fallback support."""
    if not gemini_client:
        return {"signal": "HOLD", "confidence": 0.0, "reasoning": "Gemini API Key tidak diset."}

    primary_model = config.GEMINI_MODEL
    fallback_model = getattr(config, "GEMINI_FALLBACK_MODEL", None)
    timeout_sec = getattr(config, "LLM_TIMEOUT_SECONDS", 25.0)

    try:
        return _execute_gemini_single(primary_model, prompt, timeout_sec)
    except Exception as e:
        if fallback_model and fallback_model != primary_model:
            print(f" [GEMINI FALLBACK] Model {primary_model} error ({e}). Switching ke fallback ({fallback_model})...")
            try:
                return _execute_gemini_single(fallback_model, prompt, timeout_sec)
            except Exception as fb_err:
                print(f"[GEMINI FALLBACK ERROR] {fb_err}")
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Gemini Error: {str(fb_err)}"}
        else:
            print(f"[GEMINI ERROR] {e}")
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Gemini Error: {str(e)}"}


def _execute_claude_single(model_name, prompt, timeout_sec):
    system_text = "You are a professional financial trading assistant. Always respond with valid JSON only."
    try:
        response = claude_client.messages.create(
            model=model_name,
            max_tokens=2000,
            system=system_text,
            messages=[{"role": "user", "content": prompt}],
            timeout=timeout_sec
        )
        content = "".join(b.text for b in response.content if b.type == "text")
        return clean_json_response(content)
    except Exception as e:
        raise e


def _execute_deepseek_single(model_name, prompt, timeout_sec, reasoning_effort=None):
    """Query DeepSeek / CMC / OpenRouter (OpenAI-compatible API).
    model_name is passed intact without stripping provider prefixes (e.g. 'cmc/deepseek/deepseek-v4-flash').
    reasoning_effort: "low"/"medium"/"high" -> thinking mode; None/"" -> fast mode tanpa reasoning.
    """
    raw_model = model_name
    if reasoning_effort is None:
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
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

    response = deepseek_client.chat.completions.create(**kwargs)
    return clean_json_response(response.choices[0].message.content)


def query_deepseek(prompt):
    """Queries DeepSeek API (e.g. deepseek-v4-flash) with timeout and fallback support."""
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
            print(f" [DEEPSEEK FALLBACK] Model {primary_model} error ({e}). Switching ke fallback ({fallback_model})...")
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
    """Queries Anthropic Claude API with timeout and fallback support."""
    primary_model = getattr(config, "CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    fallback_model = getattr(config, "CLAUDE_FALLBACK_MODEL", "deepseek/deepseek-v4-flash")
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
            print(f" [CLAUDE FALLBACK] Model {primary_model} error ({e}). Switching ke fallback ({fallback_model})...")
            try:
                if fallback_model.startswith("deepseek/"):
                    return _execute_deepseek_single(fallback_model, prompt, timeout_sec, reasoning_effort="none")
                return _execute_claude_single(fallback_model, prompt, timeout_sec)
            except Exception as fb_err:
                print(f"[CLAUDE FALLBACK ERROR] {fb_err}")
                return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Claude Error: {str(fb_err)}"}
        else:
            print(f"[CLAUDE ERROR] {e}")
            return {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Claude Error: {str(e)}"}


def query_all_models_parallel(prompt, models=("OpenAI", "Gemini", "DeepSeek")):
    """Queries specified LLM models in parallel and returns dict of decisions."""
    model_fns = {
        "OpenAI": query_openai,
        "Gemini": query_gemini,
        "DeepSeek": query_deepseek,
        "Claude": query_claude,
    }
    selected = {name: model_fns[name] for name in models if name in model_fns}
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(selected))) as executor:
        futs = {executor.submit(fn, prompt): name for name, fn in selected.items()}
        for fut in concurrent.futures.as_completed(futs):
            name = futs[fut]
            try:
                results[name] = fut.result()
            except Exception as e:
                results[name] = {"signal": "HOLD", "confidence": 0.0, "reasoning": f"Error: {e}"}
    return results


def compute_micro_objective_frames(symbol, point=None):
    """
    Computes pure deterministic quantitative metrics for M30 (50-bar / 24h)
    and M15 (32-bar / 8h) windows directly from MT5.
    Returns formatted multi-line string.
    """
    try:
        import pandas as pd
        from config import mt5
        from ta.trend import EMAIndicator, ADXIndicator
        from ta.momentum import RSIIndicator
        from ta.volatility import AverageTrueRange

        if point is None or point <= 0:
            si = mt5.symbol_info(symbol)
            point = si.point if si and si.point > 0 else 0.00001

        lines = []

        # 1. M30 (50-bar / 24h Window)
        rates_m30 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 70)
        if rates_m30 is not None and len(rates_m30) >= 50:
            df30 = pd.DataFrame(rates_m30)
            c30 = df30['close']
            h30 = df30['high']
            l30 = df30['low']

            w50_h = float(h30.iloc[-50:].max())
            w50_l = float(l30.iloc[-50:].min())
            curr_px = float(c30.iloc[-1])
            rng50 = w50_h - w50_l
            pos50_pct = ((curr_px - w50_l) / rng50 * 100.0) if rng50 > 0 else 50.0

            ema20 = float(EMAIndicator(c30, window=20).ema_indicator().iloc[-1])
            ema50 = float(EMAIndicator(c30, window=50).ema_indicator().iloc[-1])
            ema200 = float(EMAIndicator(c30, window=min(200, len(c30))).ema_indicator().iloc[-1]) if len(c30) >= 60 else ema50

            atr30_pts = float(AverageTrueRange(h30, l30, c30, window=14).average_true_range().iloc[-1] / point)

            # Dynamic precision
            s_u = symbol.upper()
            dp = 3 if any(x in s_u for x in ("JPY", "HUF", "DKK", "NOK", "SEK", "CZK", "HKD")) else (2 if any(x in s_u for x in ("XAU", "GOLD", "BTC", "ETH")) else 5)
            f_px = lambda x: f"{x:.{dp}f}"

            if ema20 > ema50 > ema200:
                align30 = "EMA20 > EMA50 > EMA200 (Bullish Alignment)"
            elif ema20 < ema50 < ema200:
                align30 = "EMA20 < EMA50 < EMA200 (Bearish Alignment)"
            else:
                align30 = f"EMA20={f_px(ema20)}, EMA50={f_px(ema50)}, EMA200={f_px(ema200)}"

            lines.append("- M30 Structural Frame (50-bar / 24h Window):")
            lines.append(f"  * 50-Bar High: {f_px(w50_h)} | 50-Bar Low: {f_px(w50_l)} | Position: {pos50_pct:.1f}% of Range")
            lines.append(f"  * Moving Averages: EMA20 = {f_px(ema20)} | EMA50 = {f_px(ema50)} | EMA200 = {f_px(ema200)} ({align30})")
            lines.append(f"  * Volatility Meter: ATR(14) = {atr30_pts:.1f} pts")

        # 2. M15 (32-bar / 8h Window)
        rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 50)
        if rates_m15 is not None and len(rates_m15) >= 32:
            df15 = pd.DataFrame(rates_m15)
            c15 = df15['close']
            h15 = df15['high']
            l15 = df15['low']

            w32_h = float(h15.iloc[-32:].max())
            w32_l = float(l15.iloc[-32:].min())
            curr_px15 = float(c15.iloc[-1])
            rng32 = w32_h - w32_l
            pos32_pct = ((curr_px15 - w32_l) / rng32 * 100.0) if rng32 > 0 else 50.0

            ema9 = float(EMAIndicator(c15, window=9).ema_indicator().iloc[-1])
            ema21 = float(EMAIndicator(c15, window=21).ema_indicator().iloc[-1])
            ema50_15 = float(EMAIndicator(c15, window=min(50, len(c15))).ema_indicator().iloc[-1])

            atr15_pts = float(AverageTrueRange(h15, l15, c15, window=14).average_true_range().iloc[-1] / point)

            last3_bodies = [abs(float(df15['close'].iloc[-i]) - float(df15['open'].iloc[-i])) / point for i in range(1, 4)]
            avg_body_pts = sum(last3_bodies) / 3.0
            body_atr_ratio = (avg_body_pts / atr15_pts) if atr15_pts > 0 else 0.0

            if ema9 > ema21 > ema50_15:
                align15 = "EMA9 > EMA21 > EMA50 (Bullish Momentum Stack)"
            elif ema9 < ema21 < ema50_15:
                align15 = "EMA9 < EMA21 < EMA50 (Bearish Momentum Stack)"
            else:
                align15 = f"EMA9={f_px(ema9)}, EMA21={f_px(ema21)}, EMA50={f_px(ema50_15)}"

            lines.append("- M15 Micro Flow Frame (32-bar / 8h Session Window):")
            lines.append(f"  * 32-Bar High: {f_px(w32_h)} | 32-Bar Low: {f_px(w32_l)} | Position: {pos32_pct:.1f}% of Range")
            lines.append(f"  * Moving Averages: EMA9 = {f_px(ema9)} | EMA21 = {f_px(ema21)} | EMA50 = {f_px(ema50_15)} ({align15})")
            lines.append(f"  * Volatility Meter: ATR(14) = {atr15_pts:.1f} pts")
            lines.append(f"  * Micro Velocity: Last 3 bars avg candle body = {avg_body_pts:.1f} pts ({body_atr_ratio:.2f}x ATR M15)")

        return "\n".join(lines) if lines else ""
    except Exception:
        return ""


def build_high_density_dossier_prompt(candidate, recent_d1_str=None, recent_h4_str=None, recent_h1_str=None, recent_m15_str=None, recent_m5_str=None):
    """
    Builds the High-Density Institutional Dossier Prompt for 3-LLM Consensus Jury.
    Injected when Stage 1 Fast Execution Radar flags a candidate setup.
    Includes live M15 and M5 micro candlestick price action microscope for unbiased objective verification.
    """
    sym = candidate.symbol
    direction_str = "BUY" if candidate.direction == 1 else "SELL"
    meta = getattr(candidate, 'metadata', {}) or {}
    
    candles_block = ""
    if recent_m15_str:
        candles_block += f"\n- M15 Micro Intraday Context (Last 16 bars OHLC):\n{recent_m15_str}\n"
    if recent_m5_str:
        candles_block += f"\n- M5 Micro Flow & Wick Microscope (Last 24 bars OHLC):\n{recent_m5_str}\n"
    if not recent_m15_str and (recent_d1_str or recent_h4_str or recent_h1_str):
        if recent_d1_str:
            candles_block += f"\n- D1 Daily Context (Last 3 days OHLC):\n{recent_d1_str}\n"
        if recent_h4_str:
            candles_block += f"\n- H4 Structural (Last 6 bars OHLC):\n{recent_h4_str}\n"
        if recent_h1_str:
            candles_block += f"\n- H1 Execution (Last 12 bars OHLC):\n{recent_h1_str}\n"
    
    meta_lines = []
    if meta.get("entry_type"):
        meta_lines.append(f"- Proposed Execution Method: {meta.get('entry_type').upper()} @ {meta.get('entry_price')}")
    if meta.get("zone_touches"):
        meta_lines.append(f"- Structural Zone Touch Count: {meta.get('zone_touches')} touches in last 40 bars")
    if meta.get("range_age_hours"):
        meta_lines.append(f"- Compression Duration / Range Age: {meta.get('range_age_hours')} hours ({meta.get('wave_regime', 'YOUNG_OSCILLATION')})")
    meta_block = "\n".join(meta_lines) if meta_lines else "- Execution Method: Standard structural assessment"

    pdh_val = getattr(candidate, 'pdh', 0.0)
    pdl_val = getattr(candidate, 'pdl', 0.0)
    pwh_val = getattr(candidate, 'pwh', 0.0)
    pwl_val = getattr(candidate, 'pwl', 0.0)
    do_val = getattr(candidate, 'daily_open', 0.0)
    adr_used_val = getattr(candidate, 'adr_used_pct', 0.0)
    h4_status = getattr(candidate, 'h4_trend', '') or 'Aligned with Macro'
    d1_50_str = getattr(candidate, 'd1_50_range', '') or 'N/A'
    d1_100_str = getattr(candidate, 'd1_100_range', '') or 'N/A'
    h4_m_str = getattr(candidate, 'h4_monthly_range', '') or 'N/A'
    
    # Compute deterministic micro objective frames (M30 50-bar + M15 32-bar)
    micro_frames_block = compute_micro_objective_frames(sym)
    if micro_frames_block:
        micro_frames_block = f"\n{micro_frames_block}\n"

    csm_block = ""
    try:
        from src.analytics import currency_strength
        csm_payload = currency_strength.get_csm_prompt_payload(sym)
        if csm_payload:
            csm_block = f"\n{csm_payload.strip()}\n"
    except Exception:
        csm_block = ""

    # === SYMBOL DECIMAL PRECISION & PIPS/POINTS HELPERS ===
    def _sym_dec(s):
        """Returns correct decimal places for a symbol's price display."""
        s_upper = s.upper()
        if any(x in s_upper for x in ("JPY", "HUF", "DKK", "NOK", "SEK", "CZK", "HKD")):
            return 3
        if any(x in s_upper for x in ("XAU", "GOLD", "BTC", "ETH")):
            return 2
        return 5

    def _format_step_label(s, step_val):
        """Formats calibrated psychological step size correctly in pips and points."""
        s_u = s.upper()
        if "BTC" in s_u:
            return f"${step_val:,.0f} ({int(step_val * 100):,} pts)"
        if "XAU" in s_u or "GOLD" in s_u:
            return f"${step_val:.0f} ({int(step_val * 100):,} pts)"
        if "JPY" in s_u:
            pips = int(round(step_val * 100))
            pts = int(round(step_val * 1000))
            return f"{step_val:.0f} JPY ({pips} pips / {pts:,} pts)"
        # Standard Forex (5-digit): 0.0100 = 100 pips = 1,000 pts
        pips = int(round(step_val * 10000))
        pts = int(round(step_val * 100000))
        return f"{pips} pips ({pts:,} pts)"

    sym_dec = _sym_dec(sym)
    P = sym_dec  # shorthand

    def fp(x):
        """Format price with correct decimal precision for this symbol."""
        if x is None:
            return "N/A"
        try:
            return f"{float(x):.{P}f}"
        except (ValueError, TypeError):
            return str(x)

    # Format ADR used safely (handles both 0.685 ratio and 68.5% percent)
    adr_display_pct = adr_used_val * 100.0 if (0.0 <= adr_used_val <= 1.5) else adr_used_val

    # === ATLAS DNA DYNAMIC STATION CALCULATION ===
    atlas_dna_block = ""
    atlas_tp_ref = None      # Atlas DNA-anchored TP reference price
    atlas_sl_ref = None      # Atlas DNA-anchored SL reference price
    formula_desc = ""
    try:
        from src.indicators.atlas_dna import calculate_dynamic_stations
        trigger_px = float(candidate.trigger_price)
        stations = calculate_dynamic_stations(sym, trigger_px)
        step_val = stations['step']
        base_st = stations['base_station']
        upper_st = stations['upper_station']
        lower_st = stations['lower_station']
        upper_2 = round(upper_st + step_val, P)
        lower_2 = round(lower_st - step_val, P)

        dist_to_upper = abs(upper_st - trigger_px)
        dist_to_lower = abs(trigger_px - lower_st)
        dist_to_base = abs(trigger_px - base_st)

        step_label = _format_step_label(sym, step_val)

        station_range = upper_st - lower_st
        position_in_range = ((trigger_px - lower_st) / station_range * 100) if station_range > 0 else 50.0

        # Determine exact immediate structural ceiling (above price) and floor (below price)
        if trigger_px < base_st:
            ceiling_st = base_st
            floor_st = lower_st
        elif trigger_px > base_st:
            ceiling_st = upper_st
            floor_st = base_st
        else:  # exactly at base_st
            ceiling_st = upper_st
            floor_st = lower_st

        # Convert ATR and Spread points to absolute price difference
        atr_px = candidate.current_atr_pts * (10 ** -P) if candidate.current_atr_pts > 0 else 0.0
        spread_px = candidate.current_spread_pts * (10 ** -P) if candidate.current_spread_pts > 0 else 0.0
        pad = 0.15 * atr_px + spread_px
        anti_wick = 0.35 * atr_px + spread_px

        if candidate.direction == 1:  # BUY
            atlas_tp_ref = round(ceiling_st - pad, P)
            atlas_sl_ref = round(floor_st - anti_wick, P)
            formula_desc = f"TP = Ceiling [{fp(ceiling_st)}] - [0.15xATR+Spread], SL = Floor [{fp(floor_st)}] - [0.35xATR+Spread]"
        else:  # SELL
            atlas_tp_ref = round(floor_st + pad, P)
            atlas_sl_ref = round(ceiling_st + anti_wick, P)
            formula_desc = f"TP = Floor [{fp(floor_st)}] + [0.15xATR+Spread], SL = Ceiling [{fp(ceiling_st)}] + [0.35xATR+Spread]"

        atlas_dna_block = f"""
### Atlas DNA Psychological Station Map (16.2-Year Calibrated Grid)
- Step Grid: {step_label} per station | Position in Range: {position_in_range:.1f}%
- Station Ladder: ... {fp(lower_2)} -> [{fp(lower_st)}] -> [{fp(base_st)}] <CURRENT {fp(trigger_px)}> -> [{fp(upper_st)}] -> {fp(upper_2)} ...
- Distances: to Lower {fp(dist_to_lower)} | to Base {fp(dist_to_base)} | to Upper {fp(dist_to_upper)}
- DNA-Anchored Reference ({direction_str}): TP = {fp(atlas_tp_ref)} | SL = {fp(atlas_sl_ref)} ({formula_desc})
"""
    except Exception:
        atlas_dna_block = ""

    # === DETERMINISTIC ATR-BASED PROXIMITY & EXECUTION HINT COMPUTATION ===
    trigger_px = float(candidate.trigger_price)
    proposed_entry = float(meta.get("entry_price") or trigger_px)
    atr_pts = candidate.current_atr_pts if candidate.current_atr_pts > 0 else 100.0
    pt_size = 10 ** -sym_dec
    
    # Distance in price, points, pips, and ATR multiple
    dist_price = abs(trigger_px - proposed_entry)
    dist_pts = int(round(dist_price / pt_size)) if pt_size > 0 else 0
    pip_div = 10 if sym_dec in (3, 5) else 1
    dist_pips = dist_pts / pip_div
    atr_pips = atr_pts / pip_div
    atr_mult = dist_pts / atr_pts if atr_pts > 0 else 0.0
    if dist_pts == 0:
        proximity_label = "0.00x ATR H1 (Current Live Price IS the Entry — Instant Market Execution)"
    else:
        proximity_label = f"{atr_mult:.2f}x ATR H1 from proposed pending limit anchor ({dist_pips:.1f} pips away)"
    # === TOP-DOWN MACRO STRATEGIC LANDSCAPE INJECTION (PROBABILISTIC & OBJECTIVE) ===
    strat_block = ""
    try:
        from src.analytics.macro_strategic_engine import macro_strategic_engine
        strat_dir = macro_strategic_engine.get_directive(sym)
        if strat_dir:
            f1_tags = strat_dir.raw_payload.get("f1_structure_tags", "STRUCTURAL")
            c1_tags = strat_dir.raw_payload.get("c1_structure_tags", "STRUCTURAL")
            seq_str = " -> ".join(strat_dir.interaction_sequence[-4:]) if strat_dir.interaction_sequence else "Initial Observation"
            traps_str = " | ".join(strat_dir.forbidden_traps) if strat_dir.forbidden_traps else "None"
            
            f_layers_str = " | ".join([f"{f['tier']}:{f['price']} ({f.get('reaction_grade','G1').replace('GRADE_','G')}, {f['fortress_tag']})" for f in getattr(strat_dir, 'layered_floors', [])[:5]]) if getattr(strat_dir, 'layered_floors', []) else f"F1:{strat_dir.immediate_floor_f1}"
            c_layers_str = " | ".join([f"{c['tier']}:{c['price']} ({c.get('reaction_grade','G1').replace('GRADE_','G')}, {c['fortress_tag']})" for c in getattr(strat_dir, 'layered_ceilings', [])[:5]]) if getattr(strat_dir, 'layered_ceilings', []) else f"C1:{strat_dir.immediate_ceiling_c1}"

            strat_block = f"""
- MSE Market State: [{strat_dir.market_state}] (Chamber Range: {strat_dir.chamber_position_pct:.0%}) | Stability: {strat_dir.regime_stability}
- Macro Bias & Directive: {strat_dir.daily_macro_bias} ({strat_dir.macro_bias_score:+.2f}) -> {strat_dir.primary_execution_directive} (Confidence: {strat_dir.confidence_score}%)
- Action Tier: {getattr(candidate, 'action_tier', strat_dir.action_tier)} | Circuit Breaker: {'ACTIVE (BLOCKED)' if strat_dir.hard_circuit_breaker else 'CLEAR'}
- Barrier Chamber Multi-Scale Matrix (Confluence-Graded Floors & Ceilings):
  * Floor Hierarchy: {f_layers_str}
  * Ceiling Hierarchy: {c_layers_str}
  * Immediate Bounds: F1={strat_dir.immediate_floor_f1} ({strat_dir.f1_fortress_tag}) | C1={strat_dir.immediate_ceiling_c1} ({strat_dir.c1_fortress_tag})
  * Deep Extension Target Bounds: F_deep={strat_dir.deep_target_floor_f2} | C_deep={strat_dir.deep_target_ceiling_c2}
- Interaction Sequence (8-Bar Path): {seq_str}
- SBR/RBS Hierarchy: W1 SBR={strat_dir.macro_sbr_w1} / RBS={strat_dir.macro_rbs_w1} | D1 SBR={strat_dir.macro_sbr_d1} / RBS={strat_dir.macro_rbs_d1} | H4 SBR={strat_dir.inter_sbr_h4} / RBS={strat_dir.inter_rbs_h4}
- Target Landscape: TP1 (Proximal Retest) = {strat_dir.tp1_price} | TP2 (Deep Macro Station) = {strat_dir.tp2_price}
- Execution Anchor & Protection: Reload Limit = {strat_dir.entry_limit_anchor} | Intraday SL = {strat_dir.intraday_sl_price} ({strat_dir.intraday_sl_pips:.1f} pips) | Invalidation = {strat_dir.invalidation_stop_price}
- Mandate Thesis: {strat_dir.daily_mandate_thesis}
- Forbidden Traps: {traps_str}\n"""
    except Exception:
        strat_block = ""

    calendar_block = getattr(candidate, 'economic_context', '')
    if not calendar_block:
        try:
            from src.analytics import economic_calendar
            calendar_block = economic_calendar.calendar.get_context(symbol=sym)
        except Exception:
            calendar_block = ""
    calendar_text = calendar_block.strip() if calendar_block else "No High-Impact News releases within +/- 6 hours"

    # === APEX PARAGON MACRO FUNDAMENTAL SCORECARD ===
    fund_block = ""
    try:
        from src.analytics.apex_fundamental_engine import apex_fundamental_engine
        fund_block = apex_fundamental_engine.generate_llm_dossier_block(sym)
        if fund_block:
            fund_block = f"\n{fund_block.strip()}\n"
    except Exception:
        fund_block = ""

    wick_ratio_val = float(candidate.rejection_wick_ratio or 0.0) * 100.0
    if direction_str == "SELL":
        wick_desc = f"Upper Rejection Wick = {wick_ratio_val:.1f}% of M15 range (Bearish rejection pressure defending the ceiling/resistance)"
    else:
        wick_desc = f"Lower Rejection Wick = {wick_ratio_val:.1f}% of M15 range (Bullish rejection pressure defending the floor/support)"

    prompt = f"""# INSTITUTIONAL TRADING JURY: CANDIDATE VERIFICATION & ORDER OPTIMIZER DOSSIER

Python Quantitative Engine has detected a potential quantitative setup ({candidate.setup_type}) on {sym} ({candidate.timeframe}).

## 1. INSTITUTIONAL BATTLEFIELD & CONFLUENCE
- Symbol: {sym} | Asset: {asset_desc(sym)}
- Setup Type: {candidate.setup_type} | Proposed Direction: {direction_str} | Current Price: {fp(float(candidate.trigger_price))}
- Macro Compass: {candidate.macro_compass or 'N/A'} | H4 Status: {h4_status or 'N/A'}
- MSE Action Tier: {getattr(candidate, 'action_tier', 'FULL_ALLOW')} | Permission: {getattr(candidate, 'permission_state', 'ARM')} — {getattr(candidate, 'wave_summary', '') or 'Chamber Active'}
- Intraday Dealing Range: {candidate.dealing_range_pos*100:.1f}% ({'DEEP DISCOUNT' if candidate.dealing_range_pos <= 0.38 else ('EXTREME PREMIUM' if candidate.dealing_range_pos >= 0.62 else 'EQUILIBRIUM')})
- Key Levels: PDH={fp(pdh_val)} | PDL={fp(pdl_val)} | PWH={fp(pwh_val)} | PWL={fp(pwl_val)} | DO={fp(do_val)} | ADR Used: {adr_display_pct:.1f}%
- Volatility: ATR(14)={candidate.current_atr_pts:.1f} pts | Current Spread={candidate.current_spread_pts} pts
- Micro Rejection Wick (M15 Frame): {wick_desc}
{meta_block}

## 2. APEX PARAGON MACRO FUNDAMENTAL & ECONOMIC CONTEXT (40% Weight — Read Before Evaluating Technicals)
{fund_block}
- Economic Calendar Context: {calendar_text}

## 3. CURRENCY FLOW & MULTI-TIMEFRAME CONFIRMATION
{micro_frames_block}
{csm_block}
## 4. PURE QUANT 6-TF MACRO STRATEGIC DIRECTIVE (MSE) & ATLAS DNA STATIONS
{atlas_dna_block}
{strat_block}
## 5. SMART MONEY CONCEPTS (SMC) & FRVP LIQUIDITY MAP
- Structural Floor (Strong Low): {fp(candidate.strong_low) if candidate.strong_low else fp(candidate.key_support)} | Ceiling (Strong High): {fp(candidate.strong_high) if candidate.strong_high else fp(candidate.key_resistance)}
- Nearest Bullish OB: {getattr(candidate, 'bullish_ob_zone', '') or 'None nearby'} | Nearest Bearish OB: {getattr(candidate, 'bearish_ob_zone', '') or 'None nearby'}
- Nearest Fair Value Gap (FVG Magnet): {getattr(candidate, 'fvg_zone', '') or 'None nearby'}
- Liquidity Pools: {getattr(candidate, 'liquidity_pools', '') or 'Clear of immediate EQH/EQL traps'}
- Fixed Range Volume Profile (FRVP): {getattr(candidate, 'frvp_confluence', '') or 'Standard Institutional Liquidity'}

## 6. PROPOSED EXECUTION & QUANTITATIVE ATR PROXIMITY METRICS
- Live Market Price: {fp(trigger_px)} | Proposed Entry: {fp(proposed_entry)} ({'INSTANT MARKET' if dist_pts == 0 else f'PENDING LIMIT {dist_pips:.1f} pips away'})
- Quant Distance to Anchor: {dist_pips:.1f} pips ({dist_pts:,} pts) | ATR(14) H1: {atr_pips:.1f} pips ({int(atr_pts):,} pts)
- Proximity Status: {proximity_label}
- Scanner Raw SL: {fp(float(candidate.suggested_sl))} | Scanner Raw TP: {fp(float(candidate.suggested_tp))} | R:R: {candidate.risk_reward_ratio:.2f}:1
- Atlas DNA-Anchored Reference: SL = {fp(atlas_sl_ref) if atlas_sl_ref else 'N/A'} | TP = {fp(atlas_tp_ref) if atlas_tp_ref else 'N/A'}
  ({formula_desc if formula_desc else 'Station-anchored calculation'})
{candles_block}

## 7. EVALUATION & JURY OUTPUT INSTRUCTIONS
- Analytical Autonomy: You have full analytical discretion to evaluate this setup. The Quant Engine proposes baseline SL at {candidate.suggested_sl} and TP at {candidate.suggested_tp} anchored to the next structural barrier.
- Bounded Micro-Precision Refinement (Market Orders): For immediate market entry, you may fine-tune SL and TP by at most +/- 3 to 5 pips (max 0.25x ATR or 30 pts) to snap onto micro M5/M15 wicks. Runaway market deviations will be clamped back to the Quant Anchor.
- Deeper Price Optimization via Limit Orders: If entering at current market price offers cramped R:R or you desire a more favorable fill, select a PENDING LIMIT ORDER ("buy_limit" / "sell_limit" at your optimal structural entry_price) rather than forcing an off-market price.
- If setup is solid and actionable now -> select "APPROVE"
- If direction is sound but waiting for a retest limit is safer -> select "REVISE" with optimal entry_price / entry_type
- If market is plunging/surging with strong opposing momentum or trapped in chop -> select "REJECT" with risk_flag

Respond strictly in valid JSON:
{{
  "verdict": "APPROVE" | "REVISE" | "REJECT",
  "confidence": float (0.00 to 1.00) — MUST be >= 0.60 if signal is BUY/SELL, else output HOLD,
  "execution": {{
    "entry_type": "market" | "buy_limit" | "sell_limit" | "buy_stop" | "sell_stop",
    "entry_price": float (null if market, required if pending),
    "sl_price": float (exact absolute price, {P} decimal places),
    "tp_price": float (exact absolute price, {P} decimal places)
  }},
  "veto_reason": null | string (max 15 words if REJECT),
  "risk_flag": "NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "SYSTEMIC_CURRENCY_DUMP" | "HIGH_IMPACT_NEWS" | "CURRENCY_CONFLICT" | "MACRO_HEADWIND",
  "reasoning": "2-3 concise sentences justifying macro alignment, OB/station confluence, M5 micro flow, and exact SL/TP."
}}
"""
    return _strip_emoji(prompt)


def get_static_jury_system_prompt():
    """
    Returns the Static System Directives for 3-LLM Jury.
    Cached across all setup calls in OpenAI/DeepSeek prefix cache.
    """
    return """You are the Chief Investment Officer (CIO) and Chief Risk Officer (CRO) of an institutional quantitative hedge fund.
Your mission is to evaluate candidate setups proposed by the Python Quantitative Engine with zero emotional bias.

### 1. CORE OPERATIONAL DIRECTIVES:
1. Strict Unanimous Consensus: All active models must agree on direction (BUY or SELL). If split or uncertain, default to HOLD/REJECT.
2. Mandatory R:R Gate & Intraday Structure Floor: Minimum R:R >= 1.25. Anchor SL behind physical intraday structural barriers (Scanner Raw SL, nearest H1 Order Block, or SBR/RBS + anti-wick buffer). SL MUST remain tightly bounded to intraday structure (0.50x to 1.00x ATR H1). FORBIDDEN: DO NOT inflate SL into deep multi-day macro invalidation stops (e.g. > 1.2x ATR) or deep TP2 macro stations for intraday candidates.
3. Hybrid Targeting & Front-Running Pad: TP must snap to the nearest physical station/SBR/RBS minus front-running pad (TP = Station - [0.15x ATR + Spread] for BUY; Station + [0.15x ATR + Spread] for SELL).
4. Symmetrical 5-Tier Action Matrix Permission:
   - BUY permitted ONLY during mature reload in Discount (<= 50% Dealing Range) with DEMAND_REACTION_GO or DISCOUNT_RELOAD_ARMED. Never catch falling knives (WATERFALL_LOCK).
   - SELL permitted ONLY during mature reload in Premium (>= 50% Dealing Range) with SUPPLY_REACTION_GO or PREMIUM_RELOAD_ARMED. Never adang rocket spikes (VERTICAL_SPIKE_LOCK).
5. 4-Grade Quality Matrix:
   - GRADE_S (God-Tier, 1.0x Lot, 3.0x ATR TP) | GRADE_A_PLUS (High Conviction, 1.0x Lot, 2.0x ATR TP)
   - GRADE_A (Standard, 1.0x Lot, 1.5x ATR TP) | GRADE_B (Defensive Scalp TP1 Only, 0.50x Lot, 1.25x ATR TP).

### 2. MASTER INSTITUTIONAL HARD RISK VETO FLAGS:
If any of these conditions are present, you MUST reject the trade (Verdict: REJECT or Signal: HOLD):
- COUNTER_TREND_MOMENTUM: Counter-trend against H4/D1 trend or unmitigated falling knife.
- LIQUIDITY_TRAP: Entry directly in front of Equal Highs/Lows (EQH/EQL) or structural ceiling.
- IMPULSE_CHASE: FOMO chase of extended candle without basing -> select REVISE to Pending Limit.
- SYSTEMIC_CURRENCY_DUMP: Base currency collapsing across 8-currency Boitoki CSM.
- HIGH_IMPACT_NEWS: Active The Storm window (+/- 15-30 min of Tier-1 release).
- SEVERE_CURRENCY_CONFLICT: Both currencies have extreme magnitude scores (|S| >= 0.50) with Net Delta < 0.15.
- MACRO_HEADWIND: Carry spread >= 3.0% against technical direction during catalyst window.

### 3. CONFIDENCE CALIBRATION MANDATE (CRITICAL):
- Your confidence score represents your TRUE conviction in this exact setup at this exact moment.
- HARD FLOOR GATE (>= 0.60): If your conviction is below 60% (0.60), or if you identify risk flags like IMPULSE_CHASE, COUNTER_TREND_MOMENTUM, or unmitigated opposing pressure, YOU ARE STRICTLY FORBIDDEN FROM OUTPUTTING A DIRECTIONAL BUY/SELL SIGNAL.
- In all uncertain or sub-threshold cases (< 0.60 conviction or unconfirmed displacement), you MUST output signal: "HOLD" and verdict: "REJECT" (confidence <= 0.40).
- Permitted directional confidence tiers (BUY/SELL only):
  * 0.60 - 0.69: Marginal / Borderline (prefer REVISE to Pending Limit Order)
  * 0.70 - 0.79: High Conviction (APPROVE)
  * 0.80 - 1.00: Institutional God-Tier (APPROVE)
- FORBIDDEN: Outputting signal BUY or SELL with confidence < 0.60 (e.g. 0.40-0.59). If you are that uncertain, you MUST set signal to "HOLD"."""


def format_micro_tape(symbol: str, timeframe, count: int = 15) -> str:
    """
    Formats micro candlestick tape into clean, high-density OHLC lines with body & wick metrics.
    """
    try:
        from config import mt5
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None or len(rates) == 0:
            return "  * No candle data available."
        si = mt5.symbol_info(symbol)
        pt = si.point if si and si.point > 0 else 0.00001
        p_div = 10 if (si and getattr(si, 'digits', 5) in (3, 5)) else 1
        P = getattr(si, 'digits', 5) if si else 5

        lines = []
        for r in rates:
            dt_wib = datetime.fromtimestamp(r['time'], tz=_WIB)
            t_str = dt_wib.strftime("%H:%M")
            o, h, l, c = float(r['open']), float(r['high']), float(r['low']), float(r['close'])
            body_p = abs(c - o) / (pt * p_div)
            wick_u = (h - max(o, c)) / (pt * p_div)
            wick_l = (min(o, c) - l) / (pt * p_div)
            c_tag = "BULL" if c >= o else "BEAR"
            lines.append(f"  [{t_str}] {c_tag:<4} | O:{o:.{P}f} H:{h:.{P}f} L:{l:.{P}f} C:{c:.{P}f} | Body:{body_p:.1f}p WickU:{wick_u:.1f}p WickL:{wick_l:.1f}p")
        return "\n".join(lines)
    except Exception as e:
        return f"  * Tape error: {e}"


def _get_symbol_news_context(sym: str, candidate=None) -> str:
    """
    Fetches real-time economic calendar schedule for the given symbol (US/GB/EU/CH/JP/AU/CA/NZ).
    Falls back gracefully if no calendar releases are found.
    """
    ctx = getattr(candidate, 'economic_context', '') if candidate else ''
    if not ctx or "No High-Impact News releases" in ctx:
        try:
            from src.analytics import economic_calendar
            cal_obj = getattr(economic_calendar, "calendar", None)
            if cal_obj:
                live_ctx = cal_obj.get_context(symbol=sym)
                if live_ctx and live_ctx.strip():
                    return live_ctx.strip()
        except Exception:
            pass
    return ctx.strip() if ctx and ctx.strip() else "No High-Impact News releases within +/- 6 hours"


def build_openai_structure_dossier_prompt(candidate, recent_d1_str=None, recent_h4_str=None, recent_h1_str=None) -> str:
    """
    Builds the Strategic Structure & Macro Corridor Dossier for OpenAI (o4-mini).
    Focuses 100% on: 6-TF Macro Sockets, C1/C2/F1/F2 Barrier Chamber, Atlas DNA Station Corridor,
    EMA Alignment, Boitoki CSM, and Apex Paragon Fundamentals.
    """
    sym = candidate.symbol
    direction_str = "BUY" if candidate.direction == 1 else "SELL"
    P = 3 if "JPY" in sym.upper() else (2 if any(x in sym.upper() for x in ("XAU", "GOLD", "BTC")) else 5)
    fp = lambda x: f"{float(x):.{P}f}" if x is not None else "N/A"

    # Fetch Pure Quant MSE Directive
    strat_block = ""
    try:
        from src.analytics.macro_strategic_engine import macro_strategic_engine
        strat_dir = macro_strategic_engine.get_directive(sym)
        c_lines = [f"  * {c.get('tier')}: {fp(c.get('price'))} ({c.get('tag_str')}, Score: {c.get('density_score')})" for c in getattr(strat_dir, 'layered_ceilings', [])[:4]]
        f_lines = [f"  * {f.get('tier')}: {fp(f.get('price'))} ({f.get('tag_str')}, Score: {f.get('density_score')})" for f in getattr(strat_dir, 'layered_floors', [])[:4]]
        traps_str = ", ".join(strat_dir.forbidden_traps) if strat_dir.forbidden_traps else "None"
        strat_block = f"""### Pure Quant 6-TF Macro Strategic Directive (MSE)
- Dealing Chamber: Floor F1={fp(strat_dir.immediate_floor_f1)} │ Ceiling C1={fp(strat_dir.immediate_ceiling_c1)} │ Chamber Pos: {strat_dir.chamber_position_pct*100:.1f}%
- Structural Stage: {strat_dir.structural_stage} | Market State: {strat_dir.market_state}
- Macro Bias: {strat_dir.daily_macro_bias} ({strat_dir.macro_bias_score:+.2f}) -> {strat_dir.primary_execution_directive}
- Layered Resistance Ceilings (C1-C4):\n{chr(10).join(c_lines)}
- Layered Support Floors (F1-F4):\n{chr(10).join(f_lines)}
- Mandate Thesis: {strat_dir.daily_mandate_thesis}
- Forbidden Traps: {traps_str}"""
    except Exception:
        strat_block = ""

    # Atlas DNA Station Calculation
    atlas_block = ""
    try:
        from src.indicators.atlas_dna import calculate_dynamic_stations
        trig = float(candidate.trigger_price)
        st = calculate_dynamic_stations(sym, trig)
        atlas_block = f"""### Atlas DNA Psychological Station Corridor
- Current Station Anchor: Base [{fp(st['base_station'])}] -> Next Upper Target [{fp(st['upper_station'])}] │ Next Lower Floor [{fp(st['lower_station'])}]
- Corridor Step Size: {st['step']} ({st['step_points']} pts) | Live Price: {fp(trig)}"""
    except Exception:
        atlas_block = ""

    # CSM Currency Strength
    csm_block = ""
    try:
        from src.analytics import currency_strength
        csm_payload = currency_strength.get_csm_prompt_payload(sym)
        if csm_payload: csm_block = f"### Global Currency Strength Matrix (CSM)\n{csm_payload.strip()}"
    except Exception:
        csm_block = ""

    # Fundamental & News
    fund_block = ""
    try:
        from src.analytics.apex_fundamental_engine import apex_fundamental_engine
        fb = apex_fundamental_engine.generate_llm_dossier_block(sym)
        if fb: fund_block = f"### Apex Paragon Macro Fundamental Scorecard\n{fb.strip()}"
    except Exception:
        fund_block = ""

    calendar_text = _get_symbol_news_context(sym, candidate)

    from config import mt5
    d1_tape = recent_d1_str or format_micro_tape(sym, mt5.TIMEFRAME_D1, count=5)
    h4_tape = recent_h4_str or format_micro_tape(sym, mt5.TIMEFRAME_H4, count=8)

    w_state = getattr(candidate, 'wave_state', '') or 'ARM'
    w_sum = getattr(candidate, 'wave_summary', '') or 'Trading Chamber Active'
    h4_st = getattr(candidate, 'h4_trend', '') or 'Aligned with Macro'
    tier_st = getattr(candidate, 'action_tier', 'FULL_ALLOW')

    prompt = f"""# ROLE: CHIEF QUANTITATIVE MACRO STRATEGIST (OPENAI o4-mini)
## MISSION BRIEF
You are the Chief Quantitative Macro Strategist of an elite institutional hedge fund.
Your SOLE RESPONSIBILITY: Evaluate HTF Structural Dealing Range, 6-TF Macro Corridor Alignment, and Multi-Day Trend Regime for {sym}.
You analyze D1/H4 macro delivery. You DO NOT touch micro M5/M1 wicks — that is Gemini's domain.

---
## 1. ASSET CONTEXT & MACRO POSITIONING
- Symbol: {sym} | Proposed Direction: {direction_str} | Live Price: {fp(candidate.trigger_price)}
- Macro Compass: {candidate.macro_compass or 'N/A'} | H4 Status: {h4_st}
- MSE Action Tier: {tier_st} | Regime Stability: {getattr(candidate, 'regime_stability', 'STABLE')}
- Intraday Chamber Position: {candidate.dealing_range_pos*100:.1f}% ({'🟢 DISCOUNT — Buy Zone' if candidate.dealing_range_pos <= 0.35 else ('🟡 LOWER DISCOUNT' if candidate.dealing_range_pos <= 0.45 else ('⚪ EQUILIBRIUM — Avoid Market Orders' if candidate.dealing_range_pos <= 0.55 else ('🟠 UPPER PREMIUM' if candidate.dealing_range_pos <= 0.65 else '🔴 PREMIUM — Sell Zone')))})
- Volatility Regime: ATR(14) H1 = {candidate.current_atr_pts:.1f} pts | Spread = {candidate.current_spread_pts} pts | Spread/ATR Ratio = {candidate.current_spread_pts / max(candidate.current_atr_pts, 1) * 100:.1f}%
- Setup Type Proposed: {candidate.setup_type} | Baseline R:R: {candidate.risk_reward_ratio:.2f}:1

---
## 2. HTF MULTI-TIMEFRAME CANDLESTICK TAPE

### [D1] Multi-Day Macro Delivery Context (Last 5 Daily Bars):
{d1_tape}
KEY: Are daily candles trending with expanding bodies (expansion) or compressing (accumulation/exhaustion)?

### [H4] Structural Trend & Wave Context (Last 8 H4 Bars):
{h4_tape}
KEY: Identify the dominant H4 wave — Is it an impulse leg, a correction pullback, or a ranging channel?

---
## 3. PURE QUANT 6-TF MACRO ENGINE & CONFLUENCE
{strat_block}

{atlas_block}

{csm_block}

{fund_block}

---
## 4. ECONOMIC MACRO CALENDAR
{calendar_text}
RULE: If a Tier-1 release (Rate Decision, NFP, CPI) is within 90 minutes — default to REVISE/REJECT unless setup is structurally pristine with wide SL.

---
## 5. REGIME CLASSIFICATION FRAMEWORK
Classify the current market structure into ONE of:
- **EXPANSION_TREND**: Price is delivering from one station to the next in a clean impulsive wave with H4 body dominance > 60% of candle range. Continuation trades are HIGH conviction.
- **ABSORPTION_PRE_BREAKOUT**: Price is compressing tightly above/below a key level (OB/RBS/SBR) — range contracting, spread declining — institutional accumulation before directional move.
- **RANGE_BOUND**: Price oscillating between defined S/R with no H4 directional commitment. Mean-reversion trades only at chamber extremes (< 20% or > 80% range).
- **EXHAUSTION_REVERSAL**: Price has run > 1.5x ATR in one direction, H4 wicks expanding, body momentum collapsing — fade the extension with a REVISE limit order at structural retest.

---
## 6. STRATEGIC EXECUTION MANDATE
1. **Corridor Delivery**: Has price shown structural acceptance ABOVE base station (BUY) or BELOW resistance station (SELL)? Station-to-Station delivery requires a clear close, not just a wick touch.
2. **Anti-FOMO Gate**: Dealing Range >= 85% (BUY) or <= 15% (SELL) → FORBIDDEN market order. MUST use 'buy_limit'/'sell_limit' at retest level, or REJECT if no retest anchor exists.
3. **Macro Headwind Check**: If D1 trend direction opposes proposed trade, and H4 lacks a clear CHoCH structure flip — output REJECT with COUNTER_TREND_MOMENTUM flag.
4. **Confidence Calibration (Hard Floor >= 0.60)**: Only APPROVE if you have >= 70% conviction in macro alignment. If 60-69% conviction → REVISE with Pending Limit. If conviction is < 60% OR if opposing macro momentum is present, you are STRICTLY FORBIDDEN from issuing a BUY/SELL signal — you MUST output signal: "HOLD" and verdict: "REJECT" (confidence <= 0.40).

Respond strictly in valid JSON:
{{
  "verdict": "APPROVE" | "REVISE" | "REJECT",
  "signal": "{direction_str}" | "HOLD" — MUST be "HOLD" if confidence < 0.60,
  "confidence": float (0.00 to 1.00) — STRICT: BUY/SELL requires >= 0.60. If conviction < 0.60, set signal to "HOLD",
  "role": "STRATEGIC_STRUCTURE",
  "regime": "EXPANSION_TREND" | "ABSORPTION_PRE_BREAKOUT" | "RANGE_BOUND" | "EXHAUSTION_REVERSAL",
  "station_corridor": "e.g. '1.09500 -> 1.10020 (Base Station -> C1 Ceiling)' describing price delivery path",
  "macro_alignment": "ALIGNED" | "PARTIAL" | "COUNTER_TREND",
  "execution": {{
    "entry_type": "market" | "buy_limit" | "sell_limit",
    "entry_price": float (null if market, exact price if pending),
    "sl_price": float (exact price behind structural invalidation, {P} decimals),
    "tp_price": float (exact price at next macro station/barrier, {P} decimals)
  }},
  "risk_flag": "NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "SYSTEMIC_CURRENCY_DUMP" | "HIGH_IMPACT_NEWS" | "MACRO_HEADWIND",
  "reasoning": "3-4 sentences: (1) HTF regime classification with evidence, (2) dealing chamber position verdict, (3) station corridor delivery logic, (4) exact SL/TP structural anchoring."
}}"""
    return _strip_emoji(prompt)


def build_gemini_price_action_dossier_prompt(candidate, recent_m1_str=None, recent_m5_str=None, recent_m15_str=None, recent_h1_str=None) -> str:
    """
    Builds the Dedicated Price Action & Retest Execution Dossier for Gemini (3.1-Flash).
    Focuses 100% on: Candlestick Anatomy (M1, M5, M15, H1), SBR/RBS Flip Validation,
    Order Flow Displacement, Wick Absorption, and SMC Order Blocks / FVG.
    """
    sym = candidate.symbol
    direction_str = "BUY" if candidate.direction == 1 else "SELL"
    P = 3 if "JPY" in sym.upper() else (2 if any(x in sym.upper() for x in ("XAU", "GOLD", "BTC")) else 5)
    fp = lambda x: f"{float(x):.{P}f}" if x is not None else "N/A"

    from config import mt5
    # Auto-fetch live candlestick tapes if not supplied
    m1_tape = recent_m1_str or format_micro_tape(sym, mt5.TIMEFRAME_M1, count=15)
    m5_tape = recent_m5_str or format_micro_tape(sym, mt5.TIMEFRAME_M5, count=24)
    m15_tape = recent_m15_str or format_micro_tape(sym, mt5.TIMEFRAME_M15, count=12)
    h1_tape = recent_h1_str or format_micro_tape(sym, mt5.TIMEFRAME_H1, count=6)

    wick_ratio_val = float(candidate.rejection_wick_ratio or 0.0) * 100.0
    wick_desc = f"Upper Wick = {wick_ratio_val:.1f}% (Bearish defense/wick)" if direction_str == "SELL" else f"Lower Wick = {wick_ratio_val:.1f}% (Bullish defense/absorption)"

    calendar_text = _get_symbol_news_context(sym, candidate)

    s_low = candidate.strong_low or candidate.key_support or candidate.suggested_sl
    s_high = candidate.strong_high or candidate.key_resistance or candidate.suggested_tp
    s_low_str = fp(s_low) if s_low and float(s_low) > 0 else "None"
    s_high_str = fp(s_high) if s_high and float(s_high) > 0 else "None"

    prompt = f"""# ROLE: MASTER PRICE ACTION & RETEST TACTICIAN (GEMINI 3.1-Flash)
## MISSION BRIEF
You are the Lead Price Action and Order Flow Tactician of an elite institutional quantitative hedge fund.
Your SOLE RESPONSIBILITY: Candlestick Anatomy, SBR/RBS Flip Validation, OB/FVG Absorption, and Micro Order Flow for {sym}.
You DO NOT analyze D1/H4 macro economics — that is OpenAI's domain. You own the M1, M5, M15, H1 tape.

---
## 1. LIVE PRICE ACTION BATTLEFIELD

### Context:
- Symbol: {sym} | Setup: {candidate.setup_type} | Direction: {direction_str} | Live Price: {fp(candidate.trigger_price)}
- Quant Baseline: SL = {fp(candidate.suggested_sl)} | TP = {fp(candidate.suggested_tp)} | R:R = {candidate.risk_reward_ratio:.2f}:1
- Dealing Range Position: {candidate.dealing_range_pos*100:.1f}% ({'🟢 DISCOUNT' if candidate.dealing_range_pos <= 0.35 else ('🟡 LOWER DISCOUNT' if candidate.dealing_range_pos <= 0.45 else ('⚪ EQUILIBRIUM' if candidate.dealing_range_pos <= 0.55 else ('🟠 UPPER PREMIUM' if candidate.dealing_range_pos <= 0.65 else '🔴 PREMIUM')))})
- ATR(14) H1 = {candidate.current_atr_pts:.1f} pts | Spread = {candidate.current_spread_pts} pts
- Rejection Wick Metric: {wick_desc}

### [M1] Live Micro Scalp Tape — Last 15 Bars (Execution-Level Flow):
{m1_tape}
KEY: Look for absorption sequences — small-body bars with long lower wicks at support = institutional demand. Wide-body bars closing above midpoint = displacement momentum.

### [M5] Live Execution Flow Tape — Last 24 Bars (Entry Confirmation Window):
{m5_tape}
KEY: Classify candle anatomy per bar:
  - DISPLACEMENT: body > 60% of candle range, wicks < 20% — strong conviction directional move
  - INDECISION: body < 30% of range, long wicks both sides — institutional contention / chop
  - REJECTION_WICK: lower wick (BUY) or upper wick (SELL) > 40% of candle range — institutional defense at level

### [M15] Intraday Session Context — Last 12 Bars (Structural Intermediate):
{m15_tape}
KEY: Identify SBR/RBS flip zones. Valid SBR→Support: prior resistance broken with a M15 close above → pullback retest forms a higher low without closing back below the broken level.

### [H1] Structural Close Context — Last 6 Bars (Setup Validation):
{h1_tape}
KEY: H1 close confirms direction. Valid bullish H1 setup: last 2+ H1 bars close ABOVE the structural base, not just wick through it. Single-wick touches are NOT structural acceptance.

---
## 2. SMART MONEY CONCEPTS (SMC) & ORDER FLOW LEVELS
- Structural Strong Low: {s_low_str} │ Strong High: {s_high_str}
- Nearest Bullish OB: {getattr(candidate, 'bullish_ob_zone', '') or 'None'} │ Nearest Bearish OB: {getattr(candidate, 'bearish_ob_zone', '') or 'None'}
- Nearest Fair Value Gap (FVG): {getattr(candidate, 'fvg_zone', '') or 'None'}
- FRVP Volume Profile: {getattr(candidate, 'frvp_confluence', '') or 'Normal'}

**OB Absorption Validation Rules:**
- BUY: Price must touch or re-enter Bullish OB zone and show ≥2 M5 bars with lower wicks (rejection). Single wick-touch without body absorption = potential stop-run, NOT valid entry.
- SELL: Price must touch Bearish OB zone and show ≥2 M5 bars with upper wicks. Body close THROUGH OB = OB invalidated — do NOT enter.
- FVG Targeting: An opposing FVG between entry and TP is a natural price magnet. Set TP just before the FVG or acknowledge the obstacle in reasoning.

---
## 3. RETEST QUALITY CLASSIFICATION
Evaluate and classify the current retest into exactly ONE:
- **PRISTINE_RETEST**: Price returned to SBR/RBS level precisely, formed tight-bodied bars with directional wicks, then resumed trend. Ideal entry.
- **LIQUIDITY_ABSORPTION**: Price swept slightly below (BUY) or above (SELL) a key level printing a displacement candle in return direction — stop-run liquidity grab. Entry on return bar.
- **DIRTY_SWEEP**: Price crossed well through structure level with large-body close, then reversed. Higher-risk — require second confirmation bar.
- **FAILED_BREAKOUT**: Price broke level convincingly but immediately reversed back through with momentum. → REJECT with COUNTER_TREND_MOMENTUM flag.

---
## 4. ECONOMIC NEWS SCHEDULE
{calendar_text}
RULE: HIGH-impact event within 30 minutes → output HOLD/REJECT. Wicks and spreads spike violently — no intraday entry within 30 min pre/post news.

---
## 5. TACTICAL EXECUTION MANDATE
1. **Displacement Test**: Count consecutive M5 bars closing in trade direction. ≥3 = displacement (market order viable). Alternating bull/bear = chop → prefer limit at OB/retest.
2. **Anti-FOMO Gate**: Dealing Range ≥85% (BUY) or ≤15% (SELL) → FORBIDDEN market order. Use pending limit at SBR/RBS retest anchor or output HOLD.
3. **SL Anchoring**:
   - BUY: SL below the last unmitigated Bullish OB lower boundary + 0.3x ATR anti-wick buffer
   - SELL: SL above the last unmitigated Bearish OB upper boundary + 0.3x ATR anti-wick buffer
5. **Confidence Floor (Hard Floor >= 0.60)**: APPROVE only if absorption confirmed by ≥2 M5 bars (conviction ≥ 70%). REVISE if pending limit at FVG/OB is viable (conviction 60–69%). If conviction is < 60% OR if you detect IMPULSE_CHASE / opposing momentum without rejection wicks, you are STRICTLY FORBIDDEN from issuing a BUY/SELL signal — you MUST output signal: "HOLD" and verdict: "REJECT" (confidence <= 0.40).

Respond strictly in valid JSON:
{{
  "verdict": "APPROVE" | "REVISE" | "REJECT",
  "signal": "{direction_str}" | "HOLD" — MUST be "HOLD" if confidence < 0.60 or if IMPULSE_CHASE detected,
  "confidence": float (0.00 to 1.00) — STRICT: BUY/SELL requires >= 0.60. If conviction < 0.60, set signal to "HOLD",
  "role": "PRICE_ACTION_TACTICIAN",
  "retest_quality": "PRISTINE_RETEST" | "LIQUIDITY_ABSORPTION" | "DIRTY_SWEEP" | "FAILED_BREAKOUT",
  "order_flow_energy": "BULLISH_DISPLACEMENT" | "BEARISH_DISPLACEMENT" | "INDECISION_DOJI" | "REJECTION_WICK" | "CHOP_ZONE",
  "candle_anatomy": "DISPLACEMENT" | "INDECISION" | "REJECTION_WICK" | "MARUBOZU",
  "execution": {{
    "entry_type": "market" | "buy_limit" | "sell_limit",
    "entry_price": float (null if market, exact price if pending),
    "sl_price": float (exact price behind physical OB boundary + anti-wick buffer, {P} decimals),
    "tp_price": float (exact price at nearest opposing structural level - front-run pad, {P} decimals)
  }},
  "risk_flag": "NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "HIGH_IMPACT_NEWS",
  "reasoning": "3-4 sentences: (1) M5/M15 candle anatomy classification with bar count evidence, (2) OB/FVG absorption quality verdict, (3) retest quality classification with specific price evidence, (4) exact SL/TP structural anchoring logic."
}}"""
    return _strip_emoji(prompt)


def build_deepseek_cro_arbiter_prompt(candidate, openai_res, gemini_res, recent_m5_str=None, calendar_text=None, recent_h4_str=None, recent_h1_str=None) -> str:
    """
    Builds the Devil's Advocate & Chief Risk Officer Arbiter Prompt for DeepSeek (V4-Flash).
    Cross-examines OpenAI's Macro Structure Thesis + Gemini's Price Action Verdict against
    the live 24-bar M5 tape, news calendar, spread spikes, and R:R floors to produce the final VETO or CLEARANCE.
    """
    sym = candidate.symbol
    direction_str = "BUY" if candidate.direction == 1 else "SELL"
    P = 3 if "JPY" in sym.upper() else (2 if any(x in sym.upper() for x in ("XAU", "GOLD", "BTC")) else 5)
    fp = lambda x: f"{float(x):.{P}f}" if x is not None else "N/A"

    from config import mt5
    h4_tape = recent_h4_str or format_micro_tape(sym, mt5.TIMEFRAME_H4, count=6)
    h1_tape = recent_h1_str or format_micro_tape(sym, mt5.TIMEFRAME_H1, count=6)
    m5_tape = recent_m5_str or format_micro_tape(sym, mt5.TIMEFRAME_M5, count=24)
    cal_str = calendar_text or _get_symbol_news_context(sym, candidate)

    # Format OpenAI and Gemini findings
    o_v = openai_res.get("verdict", "HOLD") if openai_res else "N/A"
    o_c = openai_res.get("confidence", 0.0) if openai_res else 0.0
    o_reg = openai_res.get("regime", "N/A") if openai_res else "N/A"
    o_thesis = openai_res.get("reasoning", "") if openai_res else "No thesis provided"
    o_exec = openai_res.get("execution", {}) if openai_res else {}

    # Format Gemini findings (Pass 1)
    g_v = gemini_res.get("verdict", "HOLD") if gemini_res else "N/A"
    g_c = gemini_res.get("confidence", 0.0) if gemini_res else 0.0
    g_ret = gemini_res.get("retest_quality", "N/A") if gemini_res else "N/A"
    g_notes = gemini_res.get("reasoning", "") if gemini_res else "No notes provided"
    g_exec = gemini_res.get("execution", {}) if gemini_res else {}

    # Fetch Pure Quant MSE Directive for DeepSeek Master Arbiter
    strat_block = ""
    try:
        from src.analytics.macro_strategic_engine import macro_strategic_engine
        strat_dir = macro_strategic_engine.get_directive(sym)
        c_lines = [f"  * {c.get('tier')}: {fp(c.get('price'))} ({c.get('tag_str')}, Score: {c.get('density_score')})" for c in getattr(strat_dir, 'layered_ceilings', [])[:4]]
        f_lines = [f"  * {f.get('tier')}: {fp(f.get('price'))} ({f.get('tag_str')}, Score: {f.get('density_score')})" for f in getattr(strat_dir, 'layered_floors', [])[:4]]
        traps_str = ", ".join(strat_dir.forbidden_traps) if strat_dir.forbidden_traps else "None"
        strat_block = f"""### Pure Quant 6-TF Macro Strategic Directive (MSE)
- Dealing Chamber: Floor F1={fp(strat_dir.immediate_floor_f1)} │ Ceiling C1={fp(strat_dir.immediate_ceiling_c1)} │ Chamber Pos: {strat_dir.chamber_position_pct*100:.1f}%
- Structural Stage: {strat_dir.structural_stage} | Market State: {strat_dir.market_state}
- Layered Resistance Ceilings (C1-C4):\n{chr(10).join(c_lines)}
- Layered Support Floors (F1-F4):\n{chr(10).join(f_lines)}
- Forbidden Traps: {traps_str}"""
    except Exception:
        strat_block = ""

    # CSM Currency Strength
    csm_block = ""
    try:
        from src.analytics import currency_strength
        csm_payload = currency_strength.get_csm_prompt_payload(sym)
        if csm_payload: csm_block = f"### Global Currency Strength Matrix (CSM)\n{csm_payload.strip()}"
    except Exception:
        csm_block = ""

    # SMC Order Flow
    s_low = candidate.strong_low or candidate.key_support or candidate.suggested_sl
    s_high = candidate.strong_high or candidate.key_resistance or candidate.suggested_tp
    s_low_str = fp(s_low) if s_low and float(s_low) > 0 else "None"
    s_high_str = fp(s_high) if s_high and float(s_high) > 0 else "None"
    smc_block = f"""### Smart Money Concepts (SMC) & Volume Profile
- Structural Strong Low: {s_low_str} │ Strong High: {s_high_str}
- Nearest Bullish OB: {getattr(candidate, 'bullish_ob_zone', '') or 'None'} │ Nearest Bearish OB: {getattr(candidate, 'bearish_ob_zone', '') or 'None'}
- Nearest Fair Value Gap (FVG): {getattr(candidate, 'fvg_zone', '') or 'None'} │ FRVP: {getattr(candidate, 'frvp_confluence', '') or 'Normal'}"""

    prompt = f"""# ROLE: CHIEF RISK OFFICER & MASTER VETO ARBITER (DEEPSEEK V4-Flash)
## MISSION BRIEF
You hold ABSOLUTE MASTER VETO POWER over this trade proposal. You are the final gatekeeper.
You have received Pass 1 findings from two specialists:
  - OpenAI o4-mini → Chief Quantitative MACRO Strategist (D1/H4 structure)
  - Gemini 3.1-Flash → Master PRICE ACTION Tactician (M1/M5/M15/H1 micro flow)
Your mission: Cross-examine their claims with cold mathematical rigor. Verify against ALL ground truth data.
Synthesize the optimal execution or issue a HARD VETO with clear mathematical justification.

---
## 1. CANDIDATE PROPOSAL & PASS 1 JURY DOSSIER

### Trade Specification:
- Asset: {sym} | Setup: {candidate.setup_type} | Direction: {direction_str}
- Live Price: {fp(candidate.trigger_price)} | ATR(14) H1: {candidate.current_atr_pts:.1f} pts | Spread: {candidate.current_spread_pts} pts
- Dealing Range: {candidate.dealing_range_pos*100:.1f}% ({'⛔ EXTREME_PREMIUM — Chase Risk!' if candidate.dealing_range_pos >= 0.85 else ('✅ EXTREME_DISCOUNT — Reload Zone' if candidate.dealing_range_pos <= 0.15 else ('🟢 DISCOUNT' if candidate.dealing_range_pos <= 0.45 else ('🔴 PREMIUM' if candidate.dealing_range_pos >= 0.55 else '⚪ EQUILIBRIUM')))})
- Quant Baseline: SL = {fp(candidate.suggested_sl)} | TP = {fp(candidate.suggested_tp)} | R:R = {candidate.risk_reward_ratio:.2f}:1
- Spread/ATR Ratio: {candidate.current_spread_pts / max(candidate.current_atr_pts, 1) * 100:.1f}% (Alert if > 20%)

### OPENAI FINDINGS — Strategic Structure & Macro Corridor:
- Verdict: **{o_v}** | Confidence: {o_c:.0%} | Regime: {o_reg}
- Proposed Execution: {o_exec}
- Macro Thesis: "{o_thesis}"

### GEMINI FINDINGS — Price Action & Retest Tactician:
- Verdict: **{g_v}** | Confidence: {g_c:.0%} | Retest Quality: {g_ret}
- Proposed Execution: {g_exec}
- Price Action Summary: "{g_notes}"

### JURY AGREEMENT SUMMARY:
- Direction Agreement: {'✅ UNANIMOUS — Both say ' + direction_str if o_v != 'REJECT' and g_v != 'REJECT' else '⛔ DISAGREEMENT — Check for structural conflict'}
- Confidence Gap: {abs(o_c - g_c) * 100:.1f}% gap between OpenAI and Gemini {'(Large gap — investigate divergence)' if abs(o_c - g_c) > 0.20 else '(Normal)'}
- Entry Type Conflict: {'⚠ DIFFERENT ENTRY TYPES — Arbiter required' if (o_exec.get('entry_type','') if isinstance(o_exec, dict) else '') != (g_exec.get('entry_type','') if isinstance(g_exec, dict) else '') else '✅ Entry type aligned'}

---
## 2. GROUND TRUTH: STRUCTURAL MSE, CSM & SMC DATA

{strat_block}

{csm_block}

{smc_block}

---
## 3. MULTI-TIMEFRAME GROUND TRUTH TAPES

### [H4] Structural Wave & Macro Trend Context (Last 6 Bars):
{h4_tape}
AUDIT: Does the H4 wave confirm the direction OpenAI proposed? Count bull vs bear bodies. Dominant direction = structural alignment.

### [H1] Intermediate Session Context (Last 6 Bars):
{h1_tape}
AUDIT: Is H1 basing cleanly above the structural floor (BUY) or below resistance (SELL)? Or is it stalling in chop?

### [M5] Micro Execution Flow Tape — Last 24 Bars (Anti-Waterfall / Anti-Spike Detector):
{m5_tape}
AUDIT: Scan for:
  - WATERFALL: ≥4 consecutive BEAR bars with expanding bodies and no lower wicks → FALLING_KNIFE_WATERFALL flag → force HOLD
  - VERTICAL_SPIKE: ≥4 consecutive BULL bars closing near highs → IMPULSE_CHASE flag → force Limit Order
  - ABSORPTION: alternating bars with wicks at key level → clean basing → potential APPROVE
  - CHOP: small bodies alternating randomly → insufficient conviction → REVISE to Limit

---
## 4. RISK CONSTRAINTS & ECONOMIC CALENDAR

### Economic News Window:
{cal_str}
RULES:
  - Tier-1 event (Rate Decision, NFP, CPI) within 60 min → HARD VETO unless SL > 1.5x ATR
  - Tier-2 event within 30 min → REVISE to Limit Order minimum
  - Spread/ATR > 25% → REJECT (cost too high relative to volatility)

### R:R Audit (Hard Floor):
- Minimum R:R = 1.25:1. If proposed SL/TP deliver R:R < 1.25 → issue POOR_RR_RATIO flag and REJECT.
- Optimal SL for {direction_str}: Place behind last OB boundary + 0.3x ATR anti-wick buffer.
- Optimal TP for {direction_str}: Next structural station/resistance minus 0.15x ATR front-run pad.

---
## 5. MASTER VETO AUDIT FRAMEWORK

### Step 1 — Contradiction Analysis:
Are OpenAI and Gemini contradicting each other on a critical point?
- If OpenAI says REJECT + Gemini says APPROVE → HARD VETO (structural conflict)
- If confidence gap > 25% → investigate the divergence before synthesizing
- If entry types differ (Market vs Limit) → determine optimal; do NOT veto for style alone

### Step 2 — Trap & Fallacy Detection:
- LIQUIDITY_TRAP: Is price entering directly in front of Equal Highs/Lows or a structural ceiling? → REJECT
- IMPULSE_CHASE: Is price extending > 1.0x ATR from the last base? → Convert to Limit or REJECT
- FALLING_KNIFE_WATERFALL: ≥4 consecutive momentum bars in opposite direction? → REJECT
- COUNTER_TREND: D1/H4 trend directly opposes the proposed direction without a CHoCH flip? → REJECT

### Step 3 — Final Synthesis:
If no HARD VETO is warranted:
1. Determine the single best entry_type (Market or Limit) based on current price vs level proximity
2. Set SL behind the most conservative physical structural barrier (OpenAI or Gemini's choice, whichever is safer)
3. Set TP at the nearest confirmed opposing structural station (OpenAI's macro target or Gemini's micro FVG, whichever is closer)
4. Verify final R:R >= 1.25:1. If not, widen TP to next structural level or REJECT.
5. Confidence Calibration (Hard Floor >= 0.60): Output directional BUY/SELL only if synthesized conviction >= 60%. If conviction < 60% OR if any unmitigated risk flag remains, you MUST output signal: "HOLD" and verdict: "REJECT" (confidence <= 0.40).

Respond strictly in valid JSON:
{{
  "verdict": "APPROVE" | "REVISE" | "REJECT",
  "signal": "{direction_str}" | "HOLD" — MUST be "HOLD" if confidence < 0.60,
  "confidence": float (0.00 to 1.00) — STRICT: BUY/SELL requires >= 0.60. If conviction < 0.60, set signal to "HOLD",
  "role": "CHIEF_RISK_OFFICER",
  "risk_verdict": "CLEARED" | "REVISE_ENTRY_SL" | "HARD_VETO",
  "jury_synthesis": "UNANIMOUS_ALIGNED" | "ENTRY_ARBITER_REQUIRED" | "CONFIDENCE_GAP_RESOLVED" | "CONTRADICTION_VETOED",
  "veto_flags": ["NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "FALLING_KNIFE_WATERFALL" | "SYSTEMIC_CURRENCY_DUMP" | "HIGH_IMPACT_NEWS" | "POOR_RR_RATIO"],
  "execution": {{
    "entry_type": "market" | "buy_limit" | "sell_limit",
    "entry_price": float (null if market, exact price if pending),
    "sl_price": float (exact price behind safest physical structural barrier, {P} decimals),
    "tp_price": float (exact price at nearest confirmed opposing structural target, {P} decimals)
  }},
  "risk_flag": "NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "FALLING_KNIFE_WATERFALL" | "SYSTEMIC_CURRENCY_DUMP" | "HIGH_IMPACT_NEWS",
  "veto_reason": null | string (max 20 words if REJECT — cite specific price evidence),
  "reasoning": "4-5 sentences: (1) Jury agreement/conflict summary, (2) M5 tape anti-waterfall/spike audit result, (3) R:R verification with numbers, (4) entry synthesis justification or veto trigger, (5) final SL/TP structural anchor explanation."
}}"""
    return _strip_emoji(prompt)


def get_multi_llm_decisions_for_candidate(candidate, recent_d1_str=None, recent_h4_str=None, recent_h1_str=None, recent_m15_str=None, recent_m5_str=None):
    """
    Evaluates a candidate setup from Stage 1 using Specialized 2-Pass Institutional 3-LLM Jury:
    - Pass 1 (Parallel Specialized Investigation):
      * OpenAI (o4-mini) evaluates Strategic Structure & Macro Corridor
      * Gemini (3.1-Flash) evaluates Micro Price Action & Retest Dynamics (M1, M5, M15, H1)
    - Pass 2 (Cross-Examination & Master Veto Arbiter):
      * DeepSeek (V4-Flash) cross-examines Pass 1 results against live M5 tape and risk constraints.
    """
    direction_str = "BUY" if candidate.direction == 1 else "SELL"
    active_models = config.active_ai_model_names()

    results = {}
    latencies = {}
    start_total = time.time()

    model_fns = {
        "OpenAI": query_openai,
        "Gemini": query_gemini,
        "DeepSeek": query_deepseek,
        "Claude": query_claude,
    }

    # ─────────────────────────────────────────────────────────────
    # PASS 1: PARALLEL SPECIALIZED INVESTIGATION (OPENAI & GEMINI)
    # ─────────────────────────────────────────────────────────────
    prompt_openai = build_openai_structure_dossier_prompt(
        candidate,
        recent_d1_str=recent_d1_str,
        recent_h4_str=recent_h4_str,
        recent_h1_str=recent_h1_str
    )
    prompt_gemini = build_gemini_price_action_dossier_prompt(
        candidate,
        recent_m5_str=recent_m5_str,
        recent_m15_str=recent_m15_str,
        recent_h1_str=recent_h1_str
    )

    pass1_tasks = {}
    if "OpenAI" in active_models:
        pass1_tasks["OpenAI"] = prompt_openai
    if "Gemini" in active_models:
        pass1_tasks["Gemini"] = prompt_gemini

    if pass1_tasks:
        start_pass1 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(pass1_tasks)) as executor:
            futs = {executor.submit(model_fns[m], pass1_tasks[m]): m for m in pass1_tasks}
            for fut in concurrent.futures.as_completed(futs):
                model_name = futs[fut]
                try:
                    res = fut.result()
                    latencies[model_name] = time.time() - start_pass1
                    verdict = str(res.get("verdict") or res.get("signal") or "").strip().upper()
                    conf = float(res.get("confidence", 0.0) or 0.0)
                    if verdict in ("APPROVE", "REVISE", "ACCEPT", "YES", "VALID", "BUY", "SELL", direction_str):
                        res["signal"] = direction_str
                        res["confidence"] = conf if conf > 0 else 0.85
                        res["verdict"] = "REVISE" if verdict == "REVISE" else "APPROVE"
                    else:
                        res["signal"] = "HOLD"
                        res["confidence"] = 0.0
                        res["verdict"] = "REJECT"
                    results[model_name] = res
                except Exception as e:
                    results[model_name] = {"signal": "HOLD", "verdict": "REJECT", "confidence": 0.0, "reasoning": f"Error: {e}"}
                    latencies[model_name] = 0.0

    # ─────────────────────────────────────────────────────────────
    # PASS 2: MASTER CRO & DEVIL'S ADVOCATE ARBITER (DEEPSEEK / CLAUDE)
    # ─────────────────────────────────────────────────────────────
    auditor_model = "DeepSeek" if "DeepSeek" in active_models else ("Claude" if "Claude" in active_models else None)
    if auditor_model and auditor_model in model_fns:
        prompt_pass2 = build_deepseek_cro_arbiter_prompt(
            candidate,
            openai_res=results.get("OpenAI"),
            gemini_res=results.get("Gemini"),
            recent_m5_str=recent_m5_str,
            recent_h4_str=recent_h4_str,
            recent_h1_str=recent_h1_str
        )
        try:
            t0 = time.time()
            res_audit = model_fns[auditor_model](_strip_emoji(prompt_pass2))
            latencies[auditor_model] = time.time() - t0
            verdict_audit = str(res_audit.get("verdict") or res_audit.get("signal") or "").strip().upper()
            conf_audit = float(res_audit.get("confidence", 0.0) or 0.0)
            if verdict_audit in ("APPROVE", "REVISE", "ACCEPT", "YES", "VALID", "BUY", "SELL", direction_str):
                res_audit["signal"] = direction_str
                res_audit["confidence"] = conf_audit if conf_audit > 0 else 0.85
                res_audit["verdict"] = "REVISE" if verdict_audit == "REVISE" else "APPROVE"
            else:
                res_audit["signal"] = "HOLD"
                res_audit["confidence"] = 0.0
                res_audit["verdict"] = "REJECT"
            results[auditor_model] = res_audit
        except Exception as e:
            results[auditor_model] = {"signal": "HOLD", "verdict": "REJECT", "confidence": 0.0, "reasoning": f"Audit Error: {e}"}
            latencies[auditor_model] = 0.0

    total_elapsed = time.time() - start_total
    lat_str = " | ".join([f"{m}: {latencies.get(m, 0.0):.2f}s ({results.get(m, {}).get('verdict', 'HOLD')})" for m in active_models if m in latencies])
    print(f" {UI.tag('STAGE 2 JURY', UI.PURPLE)} {candidate.symbol} ({len(results)} model) | {lat_str} (Total: {total_elapsed:.2f}s)")
    return results


def get_multi_llm_decisions(symbol, df, current_tick, macro_context=None, open_positions=None,
                            whisper_str=None, all_open_positions=None):
    """
    Query only the AI slots active for the current WIB time window.
    mode = dual          -> OpenAI + Gemini (00:00-18:59 / 22:01-23:59)
    mode = triple        -> OpenAI + Gemini + Claude/DeepSeek (19:00-22:00, London-NY overlap, 4x call H1)
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


def generate_macro_narrative(directive) -> str:
    """
    Synthesizes pure quantitative MacroStrategicDirective into a rich, high-level
    institutional executive narrative for Telegram using OpenAI (gpt-4o-mini).
    """
    if not openai_client:
        return ""

    clean_sym = getattr(directive, 'symbol', 'UNKNOWN').replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "")
    
    prompt = f"""Anda adalah Kepala Strategis Makro (Head Macro Strategist) di Quantitative Hedge Fund Institusional.
Tuliskan memo briefing narasi pasar institusional (Market Story & Execution Narrative) dalam Bahasa Indonesia yang tajam, profesional, dan mengalir seperti memo trader Wall Street untuk Telegram.

[DATA KUANTITATIF KITA]
- Simbol: {clean_sym}
- Mandat Makro: {directive.daily_macro_bias} ({directive.primary_execution_directive}) | Kepercayaan: {directive.confidence_score}%
- Fase Struktur: {directive.structural_stage}
- Hirarki SBR/RBS: D1 [RBS {directive.macro_rbs_d1} | SBR {directive.macro_sbr_d1}], H4 [RBS {directive.inter_rbs_h4} | SBR {directive.inter_sbr_h4}], H1 [RBS {directive.micro_rbs_h1} | SBR {directive.micro_sbr_h1}]
- Sub-Stations (50p): Atap {directive.sub_ceiling_50} -> Lantai {directive.sub_floor_50} (Target Stasiun Akhir: {directive.target_station_price})
- Reload Zone (Limit): {directive.entry_zone_proximal} s/d {directive.entry_limit_anchor}
- Intraday SL (Anti-Hunt): {directive.intraday_sl_price} ({directive.intraday_sl_pips} pips di balik zona fisik)
- TP1 (Partial 50% + BEP Lock): {directive.tp1_price} (+{directive.tp1_pips} pips | R:R 1.50:1)
- TP2 (Milestone Target): {directive.tp2_price} (+{directive.tp2_pips} pips | R:R {directive.risk_reward_ratio}:1 ke Unmitigated OB/Stasiun)
- Invalidation Point: {directive.invalidation_stop_price}
- Thesis: {directive.daily_mandate_thesis}
- Pantangan: {', '.join(directive.forbidden_traps) if directive.forbidden_traps else '-'}
- Future Roadmap: {directive.future_macro_roadmap}

[INSTRUKSI PENULISAN WAJIB]
1. Header: [TOP-DOWN MACRO BRIEFING: {clean_sym}]
2. Tulis dalam bentuk **NARASI PARAGRAF CERITA PASAR YANG MENGALIR**, BUKAN sekadar mengulang daftar bullet points kaku!
3. Jelaskan secara mengalir:
   - **Konteks & Sentimen Pasar**: Mengapa harga terdorong ke arah ini dan bagaimana struktur institusi menekan/menopang harga.
   - **Taktik Reload & Perlindungan Modal**: Di mana kita menunggu peluru ditembakkan (**Reload Zone**), mengapa **SL** ditempatkan di level tersebut.
   - **Manajemen Cuan Bertahap**: Jelaskan aksi penguncian profit 50% di **TP1** + geser ke BEP, serta potensi lanjutan menuju **TP2**.
   - **Roadmap Kontingensi Bertingkat (Step-1 & Step-2)**: Jelaskan skenario jika skenario utama gagal secara bertahap (apa yang terjadi jika level D1 jebol lebih dulu ke Dealing Range Low, dan apa konsekuensinya jika level W1 sampai tertembus).
4. Di bagian akhir, buat sub-heading tegas:
   - [PANTANGAN & JEBAKAN MEMATIKAN]: Peringatan keras apa yang dilarang dilakukan trader agar tidak menjadi likuiditas bandar.
5. Gunakan format Markdown tebal pada angka-angka kunci agar mudah dibaca cepat. Tulis dalam Bahasa Indonesia institusional yang elegan, tajam, dan percaya diri."""

    try:
        model_name = getattr(config, "MACRO_NARRATIVE_MODEL", "gpt-4o-mini")
        resp = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "Anda adalah Lead Macro Strategist institusional. Tulis narasi pasar mengalir, tajam, dan actionable dalam Bahasa Indonesia."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.35,
            max_tokens=650,
            timeout=12.0
        )
        narrative = resp.choices[0].message.content.strip()
        return narrative
    except Exception as e:
        print(f"[LLM WARNING] generate_macro_narrative error: {e}")
        return ""

