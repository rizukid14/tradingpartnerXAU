"""
LLM Client untuk bot Binance — arsitektur 2 proposer + 1 approver.

Proposer: OpenAI (GPT) + Gemini — vote BUY/SELL/HOLD + confidence + SL/TP.
Approver: Claude — hanya dipanggil saat 2 proposer sepakat (hemat biaya);
  approve/reject signal + bisa koreksi SL/TP.

Spot limitation: hanya BUY (long). Signal SELL tanpa posisi = hold (tidak trade).
"""
import concurrent.futures
import json
import logging
import re
import time

import config

log = logging.getLogger("binance_bot")

# Inisialisasi client (mirip bot MT5)
from openai import OpenAI
from google import genai

openai_client = OpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None
gemini_client = genai.Client(api_key=config.GEMINI_API_KEY) if config.GEMINI_API_KEY else None

try:
    from anthropic import Anthropic
    claude_client = Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None
except Exception:
    claude_client = None


def _clean_json(text):
    """Parse JSON dari respons LLM (handle markdown wrapper & truncation)."""
    try:
        text = text.strip()
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            text = m.group(1)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                text = text[start:end + 1]
        return json.loads(text)
    except json.JSONDecodeError:
        # Truncated recovery
        parsed = {}
        for line in text.splitlines():
            mm = re.match(r'\s*"(\w+)":\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|null|true|false)', line)
            if mm:
                try:
                    parsed[mm.group(1)] = json.loads(mm.group(2))
                except json.JSONDecodeError:
                    parsed[mm.group(1)] = mm.group(2).strip('"')
        return parsed
    except Exception:
        return {}


def _validate_decision(parsed):
    """Pastikan dict decision punya field wajib."""
    signal = str(parsed.get("signal", "HOLD")).upper()
    if signal not in ("BUY", "SELL", "HOLD"):
        signal = "HOLD"
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return {
        "signal": signal,
        "confidence": confidence,
        "sl_pct": parsed.get("sl_pct"),
        "tp_pct": parsed.get("tp_pct"),
        "reasoning": str(parsed.get("reasoning", ""))[:300],
    }


# ---------------------------------------------------------------------------
# PROMPT
# ---------------------------------------------------------------------------
def _build_market_context(symbol, df, ticker, balance_usdt, open_position=None):
    """Data pasar mentah — dipakai proposer (GPT/Gemini) DAN approver (Claude).

    Biar approver bisa analisis INDEPENDEN (bukan cuma setuju/tidak dengan
    proposer), dia dapat konteks yang sama: 40 candle, indikator, MTF,
    market structure, money scale.
    """
    latest = df.iloc[-1]
    candles = df.tail(40).to_string()

    ind_str = ""
    try:
        from ta.momentum import RSIIndicator
        from ta.trend import EMAIndicator
        from ta.volatility import AverageTrueRange
        rsi = RSIIndicator(close=df["close"], window=14).rsi().iloc[-1]
        ema20 = EMAIndicator(close=df["close"], window=20).ema_indicator().iloc[-1]
        ema50 = EMAIndicator(close=df["close"], window=50).ema_indicator().iloc[-1]
        atr = AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], window=14).average_true_range().iloc[-1]
        ind_str = (f"- RSI(14): {rsi:.1f} | EMA20: {ema20:.2f} | EMA50: {ema50:.2f} | "
                   f"ATR(14): {atr:.2f}\n")
    except Exception:
        pass

    mtf_str = ""
    try:
        from src.analytics import mtf_analyst
        mtf_str = mtf_analyst.get_mtf_context(symbol)
    except Exception:
        pass

    ms_str = ""
    try:
        from src.analytics.market_structure import get_market_structure
        ms_str = get_market_structure(df, candle_count=40)
    except Exception:
        pass

    tick_size = 0.01
    try:
        from src.core import ccxt_connector as conn
        info = conn.get_symbol_info(symbol)
        if info:
            ts = info.get("filters", {}).get("tick_size") or 0.01
            tick_size = float(ts)
    except Exception:
        pass
    usd_per_tick = tick_size * latest["close"]
    money_str = (f"- Tick size: {tick_size} | 1 tick ≈ ${usd_per_tick:.6f} per unit | "
                 f"Spread {ticker['spread_usd']:.4f} USD\n")

    pos_str = ""
    if open_position:
        pos_str = (
            f"\n### OPEN POSITION\n"
            f"- {open_position.get('side', 'BUY')} {open_position.get('qty', '?')} {symbol} "
            f"@ {open_position.get('entry_price', '?')} | "
            f"SL: {open_position.get('sl', 'N/A')} | TP: {open_position.get('tp', 'N/A')}\n"
        )

    return f"""
### MARKET DATA
- Current price: {ticker['price']} (bid {ticker['bid']}, ask {ticker['ask']})
- Spread: {ticker['spread_usd']:.2f} USD ({ticker['spread_pct']:.3f}%)
- Equity (USDT): {balance_usdt:.2f}
- Last close: {latest['close']}

### INDICATORS ({config.TIMEFRAME})
{ind_str}{money_str}
### LAST 40 CANDLES ({config.TIMEFRAME}):
{candles}
{mtf_str}{ms_str}{pos_str}"""


def build_proposal_prompt(symbol, df, ticker, balance_usdt, open_position=None):
    """Prompt untuk proposer (GPT/Gemini) — murni entry baru (BUY/HOLD)."""
    ctx = _build_market_context(symbol, df, ticker, balance_usdt, open_position)
    return f"""
You are an expert algorithmic trader for Binance SPOT {symbol} ({config.TIMEFRAME} timeframe).
SPOT RULE: You can only BUY (long). You CANNOT short. If there is no open position,
SELL is NOT possible — the only valid decisions are BUY or HOLD.
{ctx}
### RESPONSE (JSON only)
{{
  "signal": "BUY" | "HOLD",
  "confidence": 0.0 to 1.0,
  "sl_pct": <stop loss as % of price, e.g. 1.0 = 1%>,
  "tp_pct": <take profit as % of price, e.g. 2.0 = 2%>,
  "reasoning": "1-2 sentences"
}}
Consider R:R (tp >= 1.5x sl), volatility, and the spread. Respond JSON only.
"""


def build_approval_prompt(symbol, df, ticker, balance_usdt, proposal_a, proposal_b, open_position=None):
    """Prompt untuk Claude approver — ANALISIS INDEPENDEN.

    Claude dapat data pasar mentah yang sama dengan proposer (40 candle,
    indikator, MTF, market structure) — bukan cuma ringkasan proposal.
    Tugasnya: nilai setup sendiri, lalu approve/reject + koreksi SL/TP.
    Proposal proposer hanya sebagai referensi, BUKAN dasar keputusan.
    """
    ctx = _build_market_context(symbol, df, ticker, balance_usdt, open_position)
    return f"""
You are the final risk approver for a Binance SPOT trading bot on {symbol}.
You MUST analyze the raw market data below YOURSELF (candles, indicators,
support/resistance, sweeps, multi-timeframe) — do NOT merely agree or disagree
with the proposers. They are advisory only; a wrong or biased proposal must be
rejected, and a good setup must be approved even if one proposer hesitated.
{ctx}
### PROPOSAL A (GPT): {json.dumps(proposal_a, ensure_ascii=False)}
### PROPOSAL B (Gemini): {json.dumps(proposal_b, ensure_ascii=False)}

### YOUR DECISION
Approve only if the setup is genuinely high-probability based on YOUR OWN read
of the data: clear momentum/trend, R:R >= 1.5, SL outside noise (>= 2x spread),
and no major news risk. Reject if it is marginal, unclear, or risky.

### RESPONSE (JSON only)
{{
  "approved": true | false,
  "sl_pct": <final SL % or null to keep proposal>,
  "tp_pct": <final TP % or null to keep proposal>,
  "reasoning": "1-2 sentences — reference the actual price action/levels you saw"
}}
Respond JSON only.
"""


# ---------------------------------------------------------------------------
# PROPOSERS
# ---------------------------------------------------------------------------
def _query_openai(prompt):
    if not openai_client:
        return None
    try:
        resp = openai_client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a professional crypto trader. Respond JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
        return _clean_json(resp.choices[0].message.content)
    except Exception as e:
        log.error(f"[OPENAI ERROR] {e}")
        return None


def _query_gemini(prompt):
    if not gemini_client:
        return None
    try:
        from google.genai import types
        resp = gemini_client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                # Matikan Automatic Function Calling — kita tidak pakai tools,
                # dan pesan "AFC is enabled" cuma noise di log.
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        return _clean_json(resp.text)
    except Exception as e:
        log.error(f"[GEMINI ERROR] {e}")
        return None


def _query_claude(prompt):
    if not claude_client:
        return None
    try:
        resp = claude_client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=500,
            system=[
                {
                    "type": "text",
                    "text": "You are a risk-averse crypto trading approver. Respond JSON only.",
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return _clean_json(text)
    except Exception as e:
        log.error(f"[CLAUDE ERROR] {e}")
        # Fallback tanpa prompt caching (kalau header/structure tidak didukung)
        try:
            resp = claude_client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=500,
                system="You are a risk-averse crypto trading approver. Respond JSON only.",
                messages=[{"role": "user", "content": prompt}],
                timeout=config.LLM_TIMEOUT_SECONDS,
            )
            text = "".join(b.text for b in resp.content if b.type == "text")
            return _clean_json(text)
        except Exception as e2:
            log.error(f"[CLAUDE ERROR] {e2}")
            return None


def get_proposals(symbol, df, ticker, balance_usdt, open_position=None):
    """Jalankan 2 proposer paralel. Return {model: decision}."""
    prompt = build_proposal_prompt(symbol, df, ticker, balance_usdt, open_position)
    results = {}

    def _run(name, fn):
        t0 = time.time()
        raw = fn(prompt)
        dt = time.time() - t0
        if raw:
            results[name] = _validate_decision(raw)
            results[name]["latency"] = round(dt, 2)
        else:
            results[name] = {"signal": "HOLD", "confidence": 0.0,
                             "sl_pct": None, "tp_pct": None,
                             "reasoning": f"{name} error", "latency": round(dt, 2)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = {ex.submit(_run, "OpenAI", _query_openai): "OpenAI",
                ex.submit(_run, "Gemini", _query_gemini): "Gemini"}
        for f in concurrent.futures.as_completed(futs):
            pass  # _run sudah isi results
    return results


def get_approval(symbol, df, ticker, balance_usdt, proposal_a, proposal_b, open_position=None):
    """Panggil Claude approver. Return dict {approved, sl_pct, tp_pct, reasoning} atau None."""
    if not config.CLAUDE_APPROVER_ENABLED:
        return {"approved": True, "sl_pct": None, "tp_pct": None, "reasoning": "Approver disabled"}
    prompt = build_approval_prompt(symbol, df, ticker, balance_usdt, proposal_a, proposal_b, open_position)
    raw = _query_claude(prompt)
    if not raw:
        log.warning("[CLAUDE APPROVER] Tidak ada respons — reject demi keamanan (fail-closed).")
        return {"approved": False, "sl_pct": None, "tp_pct": None, "reasoning": "Approver error (fail-closed)"}
    try:
        approved = bool(raw.get("approved", False))
        return {
            "approved": approved,
            "sl_pct": raw.get("sl_pct"),
            "tp_pct": raw.get("tp_pct"),
            "reasoning": str(raw.get("reasoning", ""))[:300],
        }
    except Exception:
        return {"approved": False, "sl_pct": None, "tp_pct": None, "reasoning": "Approver parse error"}
