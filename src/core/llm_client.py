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
- Mid-range entries are normally HOLD unless a defined limit setup offers verified clearance and R:R >= 1.25.
- Pending Rules: Entry must be at least 2x spread and within ~1.5x ATR from current price. BUY: buy_stop/buy_limit. SELL: sell_stop/sell_limit.
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

    structure_str = _structure_block(df, current_tick, atr_points, tf_label=tf_label)
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
    # Fix 21 Agustus: tambah M15/M5 MOMENTUM SUMMARY (murni data, dihitung
    # lokal) di bawah blok M5 — biar AI bisa lihat kontras momentum micro vs
    # ADX timeframe aktif yang lagging. M5 FX tetap 24 (2 jam = 2 candle H1).
    micro_candles_str = ""
    momentum_summary_str = ""
    try:
        from src.core import mt5_connector
        micro_tf = mt5_connector.mt5.TIMEFRAME_M5
        micro_tf_name = "M5"
        if tf_label == "H1":
            num_micro_send = 24  # 24 candle M5 = 120 menit (2 jam = 2 candle H1)
            duration_label = "2h"
        else:
            num_micro_send = 12  # 12 candle M5 = 60 menit (1 jam = 2 candle M30)
            duration_label = "1h"

        # Fetch enough candles so ta indicators (window 14) don't raise IndexError
        num_fetch = max(35, num_micro_send + 15)
        micro_df = mt5_connector.get_market_data(symbol, micro_tf, num_candles=num_fetch)
        if micro_df is not None and len(micro_df) > 0:
            micro_delta = _delta_candle_lines(micro_df, n=num_micro_send, point_size=point_size)
            if micro_delta:
                micro_candles_str = (
                    f"\n### LAST {len(micro_delta)} {micro_tf_name} CANDLES (intra-period {duration_label}, "
                    f"OHLC absolute prices)\n" + "\n".join(micro_delta) + "\n"
                )
        # ---- M5 MOMENTUM SUMMARY (computed locally) ----
        if micro_df is not None and len(micro_df) >= 10:
            momentum_summary_str = _momentum_summary(
                micro_df, df, point_size, "M5", tf_label
            )
            if momentum_summary_str:
                momentum_summary_str = "\n" + momentum_summary_str.strip() + "\n"
    except Exception as e:
        pass

    atr_points = int(latest["atr_14"] / point_size) if point_size > 0 else 0

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

    csm_context_str = ""
    try:
        from src.analytics import currency_strength
        csm_payload = currency_strength.get_csm_prompt_payload(symbol)
        if csm_payload:
            csm_context_str = "\n" + csm_payload.strip() + "\n"
    except Exception:
        pass

    m3_compass_str = ""
    if not macro_context:
        try:
            from src.indicators.atlas_dna import calculate_dynamic_stations, get_symbol_step
            from src.indicators.wave_state import evaluate_macro_compass_corridor
            
            cur_price = float(df["close"].iloc[-1])
            st_info = calculate_dynamic_stations(symbol, cur_price)
            step_val = st_info["step"]
            
            roll_h = float(df["high"].tail(50).max())
            roll_l = float(df["low"].tail(50).min())
            pwh_val = float(df["high"].tail(120).max()) if len(df) >= 120 else roll_h
            pwl_val = float(df["low"].tail(120).min()) if len(df) >= 120 else roll_l
            
            last_h = float(df["high"].iloc[-1])
            last_l = float(df["low"].iloc[-1])
            last_o = float(df["open"].iloc[-1])
            last_c = float(df["close"].iloc[-1])
            
            m_corr, target_st, psych_step, is_ceil_rej, is_flr_rej = evaluate_macro_compass_corridor(
                symbol=symbol, current_price=cur_price, pwh=pwh_val, pwl=pwl_val,
                macro_high=roll_h, macro_low=roll_l, cur_atr=atr_points * point_size,
                last_high=last_h, last_low=last_l, last_open=last_o, last_close=last_c
            )
            
            rng_50 = max(roll_h - roll_l, 1e-5)
            dr_pct = round(((cur_price - roll_l) / rng_50) * 100, 1)
            dr_label = "DISCOUNT ZONE (Favorable for BUY)" if dr_pct <= 38.2 else ("PREMIUM ZONE (Favorable for SELL)" if dr_pct >= 61.8 else "EQUILIBRIUM (Middle Range)")
            
            pt = point_size or 0.00001
            step_pts = int(round(step_val / pt))
            
            m3_compass_str = (
                "\n### M3 MACRO COMPASS & ATLAS DNA DYNAMIC STATIONS\n"
                f"- Active Macro Corridor: {m_corr} (Target Estafet: {_fmt_price(target_st, pt)})\n"
                f"- Calibrated Step DNA: {_fmt_price(step_val, pt)} ({step_pts} pts / {step_pts//10} pips)\n"
                f"- Immediate Dynamic Stations:\n"
                f"  * Upper Station (+1 Step): {_fmt_price(st_info['upper_station'], pt)}\n"
                f"  * Base Station (Nearest) : {_fmt_price(st_info['base_station'], pt)}\n"
                f"  * Lower Station (-1 Step): {_fmt_price(st_info['lower_station'], pt)}\n"
                f"- 50-Bar Dealing Range: {_fmt_price(roll_l, pt)} <-> {_fmt_price(roll_h, pt)} (Position: {dr_pct}% - {dr_label})\n"
            )
        except Exception:
            pass

    usd_context = ""

    macro_str = ""
    if macro_context:
        macro_str = f"\n{macro_context.strip()}\n"

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

    calendar_str = ""
    news_guard_str = ""
    try:
        from src.analytics import economic_calendar
        # Filter per-pair (20 Agustus): FOMC/NFP/Powell/Trump = semua symbol;
        # event negara lain (ECB/BoJ/RBA/SNB/CPI GB/Unemployment US, dst) hanya
        # untuk pair yang mengandung mata uang negara tsb.
        calendar_str = economic_calendar.calendar.get_context(symbol=symbol)
        if calendar_str:
            # Conditional News Anti-Fade Rule (20 Agustus): hanya muncul saat ada
            # high-impact event imminent/recently-released. Hari tenang = prompt
            # identik dengan sebelumnya (tidak mengubah perilaku normal).
            news_guard_str = (
                "\nNEWS WINDOW GUARD (high-impact event imminent or just released):\n"
                "A major scheduled news event (FOMC/CPI/NFP/etc) is within the warning "
                "window. DO NOT fade breakout momentum or attempt counter-trend "
                "mean-reversion during/after it. Ignore RSI oversold/overbought as an "
                "entry trigger during news windows. Wait for post-news volatility to "
                f"settle and a confirmed {tf_label} candle close before entering.\n"
            )
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

            # Peak MFE & Current R calculation (Ide 1 & Enhanced Re-evaluator)
            peak_str = ""
            r_str = ""
            try:
                from src.analytics import position_manager
                pt_val = point_size if point_size > 0 else 0.00001
                peak_pts, peak_r = position_manager.get_peak_mfe_info(p_ticket, point=pt_val)
                if peak_pts > 0 and peak_r > 0:
                    peak_str = f" | Peak: +{peak_r:.2f}R (+{peak_pts:.0f} pts)"

                if p_sl and p_open and pt_val > 0:
                    init_sl_dist = abs(p_open - p_sl) / pt_val
                    if init_sl_dist > 0:
                        bid_px = current_tick.get('bid', p_open)
                        ask_px = current_tick.get('ask', p_open)
                        curr_pts = ((bid_px - p_open) / pt_val) if p_type == 'BUY' else ((p_open - ask_px) / pt_val)
                        curr_r = curr_pts / init_sl_dist
                        r_str = f" ({curr_r:+.2f}R)"
            except Exception:
                pass

            pos_lines.append(f"- Ticket #{p_ticket}: {p_type} {p_vol} lot @ {p_open}{sl_tp_str}{time_str}{peak_str}{swap_str} | Floating P/L: ${p_profit:.2f} USD{r_str}")
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
Spread note: Spread is normal (passed risk gate). Do NOT use spread as a reason to reject a trade or select HOLD.
{csm_context_str}{m3_compass_str}{macro_str}
{key_levels_str}
{structure_str}
{delta_main_str}
{micro_candles_str}
{momentum_summary_str}
{atr_gate_str}
{whisper_str}{lessons_str}{recent_outcomes_str}{news_guard_str}{calendar_str}{global_portfolio_str}{positions_str}{separation_note}
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
        # Validate keys (including Streamlined V2 schema keys)
        for key in [
            "signal", "confidence", "sl_points", "tp_points", "invalidation_price", "target_price",
            "reasoning", "setup", "state", "market_regime", "entry_type", "entry_price",
            "rr_valid", "trend", "velocity", "position_actions"
        ]:
            if key not in parsed:
                parsed[key] = None

        # Fallback: jika model menghasilkan "direction" alih-alih "signal"
        if not parsed.get("signal") and parsed.get("direction"):
            parsed["signal"] = parsed["direction"]

        # Ensure signal is upper case
        if parsed.get("signal"):
            parsed["signal"] = str(parsed["signal"]).upper()
            if parsed["signal"] not in ["BUY", "SELL", "HOLD"]:
                parsed["signal"] = "HOLD"
        else:
            parsed["signal"] = "HOLD"

        # Ensure setup & state & market_regime are upper case strings if present
        for str_key in ["setup", "state", "market_regime", "trend", "velocity"]:
            if parsed.get(str_key):
                parsed[str_key] = str(parsed[str_key]).upper()

        # Ensure confidence is float
        try:
            if parsed.get("confidence") is not None:
                parsed["confidence"] = float(parsed["confidence"])
            else:
                parsed["confidence"] = 0.0 if parsed["signal"] == "HOLD" else 0.5
        except (ValueError, TypeError):
            parsed["confidence"] = 0.0 if parsed["signal"] == "HOLD" else 0.5

        # Ensure points are int if present
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
            "invalidation_price": None,
            "target_price": None,
            "trend": None,
            "velocity": None,
            "rr_valid": None,
            "reasoning": f"Gagal memparsing respon: {str(e)}"
        }


def _execute_openai_single(model_name, prompt, timeout_sec):
    is_reasoning = "gpt-5" in model_name.lower() or "o1" in model_name.lower() or "o3" in model_name.lower() or "o4" in model_name.lower()
    effort = (getattr(config, "OPENAI_REASONING_EFFORT", "low") or "").strip().lower()
    if is_reasoning:
        kwargs = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": "System: You are a professional financial trading assistant. Reasoning: 2-3 sentences (max 60 words for BUY/SELL); if HOLD, keep it to 1 short sentence (max 20 words) citing the single key level/indicator. Never enumerate.\n\n" + prompt}
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
                {"role": "system", "content": "You are a professional financial trading assistant. Reasoning: 2-3 sentences (max 60 words for BUY/SELL); if HOLD, keep it to 1 short sentence (max 20 words) citing the single key level/indicator. Never enumerate."},
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
        "Always respond with valid JSON only. Reasoning: 2-3 sentences (max 60 words for BUY/SELL); "
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
            print(f" [CLAUDE FALLBACK] Model {primary_model} lambat/error ({e}). Switching ke fallback ({fallback_model})...")
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


def build_high_density_dossier_prompt(candidate, recent_d1_str=None, recent_h4_str=None, recent_h1_str=None, recent_m5_str=None):
    """
    Builds the High-Density Institutional Dossier Prompt for 3-LLM Consensus Jury.
    Injected when Stage 1 Fast Execution Radar flags a candidate setup.
    Includes live D1, H4, H1, and M5 candlestick price action for unbiased objective verification.
    """
    sym = candidate.symbol
    direction_str = "BUY" if candidate.direction == 1 else "SELL"
    meta = getattr(candidate, 'metadata', {}) or {}
    
    candles_block = ""
    if recent_d1_str:
        candles_block += f"\n- D1 Daily Context (Last 3 days OHLC):\n{recent_d1_str}\n"
    if recent_h4_str:
        candles_block += f"\n- H4 Structural (Last 6 bars OHLC):\n{recent_h4_str}\n"
    if recent_h1_str:
        candles_block += f"\n- H1 Execution (Last 12 bars OHLC):\n{recent_h1_str}\n"
    if recent_m5_str:
        candles_block += f"\n- M5 Micro Flow (Last 24 bars OHLC):\n{recent_m5_str}\n"
    
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

    # === TOP-DOWN MACRO STRATEGIC LANDSCAPE INJECTION (PROBABILISTIC & OBJECTIVE) ===
    strat_block = ""
    try:
        from src.analytics.macro_strategic_engine import macro_strategic_engine
        strat_dir = macro_strategic_engine.get_directive(sym)
        if strat_dir:
            strat_block = f"""
- MSE Macro Bias: {strat_dir.macro_bias_score:+.2f} ({strat_dir.daily_macro_bias}) | Stability: {strat_dir.regime_stability} | Phase: {strat_dir.structural_stage}
- Action Tier: {getattr(candidate, 'action_tier', 'FULL_ALLOW')} | Circuit Breaker: {'ACTIVE' if strat_dir.hard_circuit_breaker else 'CLEAR'}
- SBR/RBS Hierarchy:
  * D1 Scale: Major SBR = {strat_dir.macro_sbr_d1} | Major RBS = {strat_dir.macro_rbs_d1}
  * H4 Scale: SBR = {strat_dir.inter_sbr_h4} | RBS = {strat_dir.inter_rbs_h4}
  * H1 Scale: SBR = {strat_dir.micro_sbr_h1} | RBS = {strat_dir.micro_rbs_h1}
- 50-Pip Sub-Stations: Sub-Floor [{strat_dir.sub_floor_50}] <---> Sub-Ceiling [{strat_dir.sub_ceiling_50}]
- Target Landscape: TP1 (Proximal Station) = {strat_dir.tp1_price} | TP2 (Macro Target) = {strat_dir.tp2_price}
- Baseline Floor SL: {strat_dir.intraday_sl_price} | Macro Invalidation: {strat_dir.invalidation_stop_price}\n"""
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

    prompt = f"""# INSTITUTIONAL TRADING JURY: CANDIDATE VERIFICATION & ORDER OPTIMIZER DOSSIER

Python Quantitative Engine has detected a potential quantitative setup ({candidate.setup_type}) on {sym} ({candidate.timeframe}).

## 1. INSTITUTIONAL BATTLEFIELD & CONFLUENCE
- Symbol: {sym} | Asset: {asset_desc(sym)}
- Setup Type: {candidate.setup_type} | Proposed Direction: {direction_str} | Current Price: {fp(float(candidate.trigger_price))}
- Macro Compass: {candidate.macro_compass or 'N/A'} | H4 Status: {h4_status or 'N/A'}
- H1 Wave State: {getattr(candidate, 'wave_state', '') or 'UNCLASSIFIED'} — {getattr(candidate, 'wave_summary', '') or 'No wave summary available'}
- Intraday Dealing Range: {candidate.dealing_range_pos*100:.1f}% ({'DEEP DISCOUNT' if candidate.dealing_range_pos <= 0.38 else ('EXTREME PREMIUM' if candidate.dealing_range_pos >= 0.62 else 'EQUILIBRIUM')})
- Key Levels: PDH={fp(pdh_val)} | PDL={fp(pdl_val)} | PWH={fp(pwh_val)} | PWL={fp(pwl_val)} | DO={fp(do_val)} | ADR Used: {adr_display_pct:.1f}%
- Volatility: ATR(14)={candidate.current_atr_pts:.1f} pts | Current Spread={candidate.current_spread_pts} pts | Rejection Wick: {candidate.rejection_wick_ratio*100:.1f}%
{meta_block}

## 2. APEX PARAGON MACRO FUNDAMENTAL & ECONOMIC CONTEXT (40% Weight — Read Before Evaluating Technicals)
{fund_block}
- Economic Calendar Context: {calendar_text}

## 3. CURRENCY FLOW & WAVE STATE CONFIRMATION
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

## 6. PROPOSED EXECUTION & STATION-ANCHORED LEVELS
- Scanner Raw SL: {fp(float(candidate.suggested_sl))} | Scanner Raw TP: {fp(float(candidate.suggested_tp))} | R:R: {candidate.risk_reward_ratio:.2f}:1
- Atlas DNA-Anchored Reference: SL = {fp(atlas_sl_ref) if atlas_sl_ref else 'N/A'} | TP = {fp(atlas_tp_ref) if atlas_tp_ref else 'N/A'}
  ({formula_desc if formula_desc else 'Station-anchored calculation'})
{candles_block}
## 7. EVALUATION & JURY OUTPUT INSTRUCTIONS
- If setup is solid and actionable now -> select "APPROVE"
- If direction is sound but waiting for a retest limit is safer -> select "REVISE" with optimal entry_price / entry_type
- If market is plunging/surging with strong opposing momentum or trapped in chop -> select "REJECT" with risk_flag

Respond strictly in valid JSON:
{{
  "verdict": "APPROVE" | "REVISE" | "REJECT",
  "confidence": float (0.00 to 1.00),
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
2. Mandatory R:R Gate: Minimum R:R >= 1.25. Anchor SL behind physical structural barriers (MSE SBR/RBS, SMC Order Block, or Atlas DNA station + 0.35x ATR anti-wick buffer).
3. Hybrid Targeting & Front-Running Pad: TP must snap to the nearest physical station/SBR/RBS minus front-running pad (TP = Station - [0.15x ATR + Spread] for BUY; Station + [0.15x ATR + Spread] for SELL).
4. Symmetrical Wave State Permission:
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
- MACRO_HEADWIND: Carry spread >= 3.0% against technical direction during catalyst window."""


def get_multi_llm_decisions_for_candidate(candidate, recent_d1_str=None, recent_h4_str=None, recent_h1_str=None, recent_m5_str=None):
    """
    Evaluates a candidate setup from Stage 1 using 2-Pass Sequential Cross-Examination 3-LLM Jury:
    - Pass 1 (Parallel Investigation): OpenAI (Structure) + Gemini (Momentum) evaluate candidate dossier.
    - Pass 2 (Cross-Examination Audit): DeepSeek (Devil's Advocate) audits Pass 1 arguments against raw D1/H4/H1/M5 data.
    """
    prompt_base = build_high_density_dossier_prompt(candidate, recent_d1_str=recent_d1_str, recent_h4_str=recent_h4_str, recent_h1_str=recent_h1_str, recent_m5_str=recent_m5_str)
    direction_str = "BUY" if candidate.direction == 1 else "SELL"
    active_models = config.active_ai_model_names()

    results = {}
    latencies = {}
    start_total = time.time()

    # ─────────────────────────────────────────────────────────────
    # PASS 1: PARALLEL INVESTIGATION (OPENAI & GEMINI)
    # ─────────────────────────────────────────────────────────────
    pass1_targets = [m for m in ("OpenAI", "Gemini") if m in active_models]
    model_fns = {
        "OpenAI": query_openai,
        "Gemini": query_gemini,
        "DeepSeek": query_deepseek,
        "Claude": query_claude,
    }

    if pass1_targets:
        start_pass1 = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(pass1_targets)) as executor:
            futs = {executor.submit(model_fns[m], prompt_base): m for m in pass1_targets}
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
    # PASS 2: DEVIL'S ADVOCATE CROSS-EXAMINATION AUDIT (DEEPSEEK / CLAUDE)
    # ─────────────────────────────────────────────────────────────
    auditor_model = "DeepSeek" if "DeepSeek" in active_models else ("Claude" if "Claude" in active_models else None)
    if auditor_model and auditor_model in model_fns:
        pass1_summary_lines = []
        for name in pass1_targets:
            if name in results:
                r = results[name]
                pass1_summary_lines.append(
                    f"- Model [{name}]: Verdict = {r.get('verdict')} (Conf {r.get('confidence', 0.0):.2f})\n"
                    f"  Proposed Execution: {r.get('execution')}\n"
                    f"  Thesis / Rationale: \"{r.get('reasoning')}\""
                )
        pass1_text = "\n".join(pass1_summary_lines) if pass1_summary_lines else "No previous findings available."

        prompt_pass2 = f"""{prompt_base}

## 7. PREVIOUS JURY PROPOSALS (TARGET OF YOUR CROSS-EXAMINATION)
The first-round panel members have analyzed this setup and submitted the following findings:
{pass1_text}

## 8. DEVIL'S ADVOCATE AUDIT DIRECTIVE
You are the Chief Risk Officer & Devil's Advocate. Your mission is to scrutinize their arguments against the raw M5/H1 candle data:
1. Examine if their thesis ignores recent counter-trend momentum, lack of rejection wicks, or structural traps.
2. If you find a critical flaw, liquidity trap, or news risk -> VETO by selecting "REJECT" with an explicit veto_reason and risk_flag.
3. If their thesis is mathematically solid and accounts for risks (e.g. valid pending limit) -> select "APPROVE" or "REVISE".

Respond strictly in the same JSON format:
{{
  "verdict": "APPROVE" | "REVISE" | "REJECT",
  "confidence": float (0.00 to 1.00),
  "execution": {{
    "entry_type": "market" | "buy_limit" | "sell_limit" | "buy_stop" | "sell_stop",
    "entry_price": float (null if market, required if pending),
    "sl_price": float (exact absolute price),
    "tp_price": float (exact absolute price)
  }},
  "veto_reason": null | string (max 15 words if REJECT),
  "risk_flag": "NONE" | "COUNTER_TREND_MOMENTUM" | "LIQUIDITY_TRAP" | "IMPULSE_CHASE" | "SYSTEMIC_CURRENCY_DUMP" | "HIGH_IMPACT_NEWS" | "CURRENCY_CONFLICT" | "MACRO_HEADWIND",
  "reasoning": "2-3 concise sentences explaining whether you accept or tear down their arguments."
}}
"""
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

