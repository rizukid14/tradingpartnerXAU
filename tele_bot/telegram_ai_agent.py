"""
telegram_ai_agent.py

Natural-language AI agent for controlling/querying your trading bot via Telegram.
Instead of button menus, you just type things like:
    "gimana performa hari ini?"
    "turunin risk BTC jadi 2%"
    "ganti ke preset v3"
    "pause trading, aku mau tidur"

The model (GPT via OpenAI API) reads your message, decides whether it needs to
call one of your bot's real HTTP endpoints to answer or make a change, calls it,
then replies to you in natural language.

All actual bot data and config live on YOUR bot's own API server - this file
is just the natural-language front end that translates chat into HTTP calls.
"""

import os
import sys
import time
import logging
from pathlib import Path

# Ensure project root directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import json
import requests
import config
from openai import OpenAI

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO
)

MODEL = os.getenv("TELEGRAM_AI_MODEL", "gpt-5.4-mini")
API_BASE_URL = getattr(config, "API_BASE_URL", "http://localhost:8765").rstrip("/")
API_TOKEN = getattr(config, "API_TOKEN", "")
API_TIMEOUT = 15  # seconds


def get_openai_client():
    api_key = getattr(config, "OPENAI_API_KEY", "") or os.getenv("OPENAI_API_KEY", "")
    api_base = os.getenv("OPENAI_API_BASE", "").strip() or getattr(config, "OPENAI_API_BASE", "").strip()
    if api_base:
        return OpenAI(api_key=api_key, base_url=api_base)
    return OpenAI(api_key=api_key)

# ---------------------------------------------------------------------------
# 1. HTTP HELPERS - every tool goes through one of these, hitting YOUR bot's API
# ---------------------------------------------------------------------------

def _headers():
    return {"Authorization": f"Bearer {API_TOKEN}"}


def _api_get(path: str, params: dict = None):
    for attempt in range(2):
        try:
            resp = requests.get(f"{API_BASE_URL}{path}", headers=_headers(), params=params or {}, timeout=API_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return {"error": f"GET {path} failed: {e}"}


def _api_post(path: str, body: dict = None):
    try:
        resp = requests.post(f"{API_BASE_URL}{path}", headers=_headers(), json=body or {}, timeout=API_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"POST {path} failed: {e}"}

# ---------------------------------------------------------------------------
# 2. TOOL IMPLEMENTATIONS - mapped 1:1 to bot API with direct module fallback
# ---------------------------------------------------------------------------

def get_summary() -> dict:
    """GET /api/summary - P/L, win rate, total trades, balance, active symbol, recovery status, etc."""
    res = _api_get("/api/summary")
    if not res.get("error"):
        return res
    # Fallback to direct Python calculation
    try:
        from src.core import mt5_connector
        acc = mt5_connector.get_account_info() or {}
        pos = mt5_connector.get_all_open_positions() or []
        deals = mt5_connector.get_closed_positions_today() or []
        today_pnl = sum(float(d.get("profit", 0.0)) for d in deals)
        floating = sum(float(p.get("profit", 0.0)) for p in pos)
        return {
            "balance": acc.get("balance", 0.0),
            "equity": acc.get("equity", 0.0),
            "margin_free": acc.get("margin_free", 0.0),
            "open_positions_count": len(pos),
            "floating_pnl": floating,
            "today_closed_trades_count": len(deals),
            "today_pnl": today_pnl,
            "active_symbol": getattr(config, "SYMBOL", "XAUUSD-ECNc"),
            "trading_mode": getattr(config, "TRADING_MODE", "pairs"),
            "trading_paused": getattr(config, "TRADING_PAUSED", False),
        }
    except Exception as e:
        return {"error": f"Failed to get summary: {e}"}


def get_open_positions() -> dict:
    """GET /api/open-positions - ticket, symbol, type, volume, SL/TP, floating P/L."""
    res = _api_get("/api/open-positions")
    if not res.get("error"):
        return res
    try:
        from src.core import mt5_connector
        raw_pos = mt5_connector.get_all_open_positions() or []
        positions = []
        for p in raw_pos:
            positions.append({
                "ticket": p.get("ticket"),
                "symbol": p.get("symbol"),
                "type": "BUY" if p.get("type") == 0 else "SELL",
                "volume": p.get("volume"),
                "price_open": p.get("price_open"),
                "sl": p.get("sl"),
                "tp": p.get("tp"),
                "profit": p.get("profit", 0.0),
            })
        return {"status": "success", "count": len(positions), "positions": positions}
    except Exception as e:
        return {"error": f"Failed to get open positions: {e}"}


def get_recent_trades(limit: int = 10) -> dict:
    """GET /api/recent-trades?limit=N - closed trade history."""
    res = _api_get("/api/recent-trades", params={"limit": limit})
    if not res.get("error"):
        return res
    try:
        from src.core import mt5_connector
        deals = mt5_connector.get_closed_positions_today() or []
        return {"status": "success", "count": len(deals[-limit:]), "trades": deals[-limit:]}
    except Exception as e:
        return {"error": f"Failed to get recent trades: {e}"}


def get_config() -> dict:
    """GET /api/config - active bot config."""
    res = _api_get("/api/config")
    if not res.get("error"):
        return res
    return {
        "DRY_RUN": getattr(config, "DRY_RUN", False),
        "TRADING_PAUSED": getattr(config, "TRADING_PAUSED", False),
        "SYMBOL": getattr(config, "SYMBOL", "XAUUSD-ECNc"),
        "TRADING_MODE": getattr(config, "TRADING_MODE", "pairs"),
        "RISK_PERCENT_FX": getattr(config, "RISK_PERCENT_FX", 1.0),
        "RISK_PERCENT_BTC": getattr(config, "RISK_PERCENT_BTC", 1.5),
        "RISK_PERCENT_XAU": getattr(config, "RISK_PERCENT_XAU", 1.0),
        "MAX_OPEN_POSITIONS": getattr(config, "MAX_OPEN_POSITIONS", 6),
    }


def update_config(updates: dict) -> dict:
    """POST /api/config - change one or more config fields."""
    res = _api_post("/api/config", body=updates)
    if not res.get("error"):
        return res
    updated = []
    for k, v in updates.items():
        if hasattr(config, k):
            setattr(config, k, v)
            updated.append(k)
    return {"status": "success", "message": f"Updated config directly: {updated}", "updated_keys": updated}


def set_strategy_preset(preset: str) -> dict:
    """POST /api/preset - {'preset': 'v3'}."""
    return _api_post("/api/preset", body={"preset": preset})


def pause_trading() -> dict:
    """POST /api/pause - TRADING_PAUSED = True."""
    res = _api_post("/api/pause")
    if not res.get("error"):
        return res
    config.TRADING_PAUSED = True
    return {"status": "success", "message": "Trading paused successfully", "trading_paused": True}


def resume_trading() -> dict:
    """POST /api/resume - TRADING_PAUSED = False."""
    res = _api_post("/api/resume")
    if not res.get("error"):
        return res
    config.TRADING_PAUSED = False
    return {"status": "success", "message": "Trading resumed successfully", "trading_paused": False}


def retrigger_cycle() -> dict:
    """POST /api/retrigger_cycle — Force/retrigger an immediate market analysis cycle."""
    return _api_post("/api/retrigger_cycle")


TOOL_FUNCTIONS = {
    "get_summary": get_summary,
    "get_open_positions": get_open_positions,
    "get_recent_trades": get_recent_trades,
    "get_config": get_config,
    "update_config": update_config,
    "set_strategy_preset": set_strategy_preset,
    "pause_trading": pause_trading,
    "resume_trading": resume_trading,
    "retrigger_cycle": retrigger_cycle,
}

# ---------------------------------------------------------------------------
# 3. TOOL SCHEMAS (OpenAI function-calling format)
# ---------------------------------------------------------------------------

def _tool(name, description, properties=None, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
        },
    }


TOOLS = [
    _tool("get_summary", "Get overall performance summary: P/L, win rate, total trades, balance, active symbol, recovery status."),
    _tool("get_open_positions", "List currently open positions: ticket, symbol, type, volume, SL/TP, floating P/L."),
    _tool(
        "get_recent_trades", "Get recent closed trade history.",
        {"limit": {"type": "integer", "description": "How many recent trades to fetch (default 10)"}},
    ),
    _tool("get_config", "Read the bot's active configuration: DRY_RUN, risk %, thresholds, active preset, etc."),
    _tool(
        "update_config",
        "Change one or more config fields on the live bot. Pass only the fields being changed, "
        "e.g. {'RISK_PERCENT_BTC': 2.0, 'DRY_RUN': false}. Field names must match the bot's actual "
        "config keys - call get_config first if unsure of exact key names or current values.",
        {
            "updates": {
                "type": "object",
                "description": "Dictionary of config field(s) to change, matching the bot's config key names exactly.",
            }
        },
        required=["updates"],
    ),
    _tool(
        "set_strategy_preset", "Apply a strategy preset (e.g. v1, v2, v3).",
        {"preset": {"type": "string", "description": "Preset name, e.g. 'v1', 'v2', 'v3'"}},
        required=["preset"],
    ),
    _tool("pause_trading", "Pause the bot — stop opening new trades. Existing open positions are untouched."),
    _tool("resume_trading", "Resume the bot — allow new trades to open again."),
    _tool("retrigger_cycle", "Force or retrigger an immediate market analysis cycle (run LLM consensus & risk check now without waiting for next candle)."),
]

SYSTEM_PROMPT = """You are the AI assistant for a multi-LLM consensus trading bot (XAUUSD, BTC, and FX pairs).
You talk to the bot's owner over Telegram in whatever language they use (usually Indonesian).

You can answer questions about performance, open positions, trade history, and config by calling
the relevant tool - never guess numbers, always call a tool to get real data.

When reporting summary performance (when user asks for summary, /summary, status, performa, or performance), ALWAYS call get_summary tool first and format your response in a rich, structured, executive style like this:

📊 **LAPORAN PERFORMA TRADING BOT**
━━━━━━━━━━━━━━━━━━━━━━━━━━
💼 **Informasi Akun MT5**:
• Balance: $... | Equity: $...
• Floating P/L: $... (... posisi terbuka)
• Free Margin: $...

📈 **Statistik Performa Trading**:
• Total Siklus: ... | Total Order: ...
• Trade Tertutup: ... posisi
• **Net P/L**: **+$... USD** 🟢 (atau 🔴 jika loss)
• **Win Rate**: **...%** (... Menang / ... Kalah / ... BEP)
• Profit Factor: ... (Gross Win: +$... | Gross Loss: -$... )

💵 **Breakdown Per Pasangan Simbol**:
(rincikan data per_symbol dari JSON summary: Win Rate, Total Trade, Net P/L)

⚙️ **Status Sistem**:
• Mode Trading: ...
• Mode AI: ...
• Loss Streak: ... | Recovery Mode: ...

Before calling update_config, if you're not certain of the exact config key name or its current
value, call get_config first to check - field names must match exactly or the change will be
rejected by the bot.

For any change (config, preset, pause/resume, retrigger cycle), confirm clearly and briefly what you changed or executed after
the tool call succeeds — mention the old and new value if you have them. If a tool call returns an
error, tell the user plainly what failed; don't pretend it worked.

If the user asks to start or run an analysis cycle, trigger or retrigger a cycle, or check the market immediately (e.g. "/start", "/trigger", "/retrigger", "/cycle", "start cycle", "start", "mulai cycle", "jalankan cycle", "analisa sekarang", "cek market"), ALWAYS call retrigger_cycle to start a market analysis cycle right away.
"""


# ---------------------------------------------------------------------------
# 4. AGENT LOOP
# ---------------------------------------------------------------------------

def _sanitize_history(history: list) -> list:
    """
    Sanitizes conversation history to prevent OpenAI API 400 Invalid Parameter errors.
    Ensures that only clean user-assistant dialog text turns are stored in long-term
    history, filtering out intermediate tool calls that might lose their matching pairs.
    """
    sanitized = []
    for msg in history:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role in ("user", "assistant"):
            content = msg.get("content")
            if content and isinstance(content, str) and not msg.get("tool_calls"):
                sanitized.append({"role": role, "content": content})
    return sanitized[-20:]  # Keep last 20 clean dialog turns


def run_agent_turn(user_text: str, history: list) -> str:
    client = get_openai_client()
    clean_history = _sanitize_history(history)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + clean_history + [{"role": "user", "content": user_text}]

    while True:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                tools=TOOLS,
                messages=messages,
                reasoning_effort="none",
            )
        except Exception as e:
            err_str = str(e)
            if "reasoning_effort" in err_str:
                try:
                    response = client.chat.completions.create(
                        model=MODEL,
                        tools=TOOLS,
                        messages=messages,
                        extra_body={"reasoning_effort": "none"},
                    )
                except Exception:
                    response = client.chat.completions.create(
                        model=MODEL,
                        tools=TOOLS,
                        messages=messages,
                    )
            else:
                raise e

        msg = response.choices[0].message

        if not msg.tool_calls:
            final_reply = (msg.content or "").strip() or "(tidak ada respon)"
            # Persist clean user prompt and final assistant response in history
            history.clear()
            history.extend(clean_history)
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": final_reply})
            return final_reply

        messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})
        for tool_call in msg.tool_calls:
            func = TOOL_FUNCTIONS.get(tool_call.function.name)
            try:
                args = json.loads(tool_call.function.arguments or "{}")
                print(f" 🛠️ [TELEGRAM TOOL] Executing tool {tool_call.function.name}({args})...")
                result = func(**args) if func else {"error": f"Unknown tool {tool_call.function.name}"}
            except Exception as e:
                print(f" [TELEGRAM TOOL ERROR] {tool_call.function.name}: {e}")
                result = {"error": str(e)}
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, default=str),
            })


# ---------------------------------------------------------------------------
# 5. TELEGRAM WIRING (Optional standalone runner)
# ---------------------------------------------------------------------------

CONVERSATION_HISTORY = []


def is_authorized(update) -> bool:
    if not config.TELEGRAM_CHAT_ID:
        return True  # If no TELEGRAM_CHAT_ID restricted, allow chat
    return str(update.effective_chat.id) == str(config.TELEGRAM_CHAT_ID)


async def on_message(update, context):
    user_name = update.effective_user.username or update.effective_user.first_name if update.effective_user else "Unknown"
    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip()

    if text.lower() in ("/reset", "/clear", "reset", "clear"):
        CONVERSATION_HISTORY.clear()
        print(f" 🧹 [TELEGRAM RESET] Chat #{chat_id} reset conversation history.")
        await update.message.reply_text("🧹 Riwayat percakapan telah direset. Silakan kirim pesan baru!")
        return

    print(f" 📩 [TELEGRAM RECV] Chat #{chat_id} (@{user_name}): '{text}'")

    if not is_authorized(update):
        print(f" ⛔ [TELEGRAM UNAUTHORIZED] Chat #{chat_id} (@{user_name}) is not authorized! Allowed: {config.TELEGRAM_CHAT_ID}")
        await update.message.reply_text("⛔ Anda tidak memiliki akses ke Telegram AI Agent ini.")
        return

    await update.message.chat.send_action("typing")
    try:
        reply = run_agent_turn(text, CONVERSATION_HISTORY)
    except Exception as e:
        print(f" [TELEGRAM AGENT ERROR] {e}")
        CONVERSATION_HISTORY.clear()  # Auto-clear broken state on error
        reply = f"⚠️ Terjadi kesalahan: {e}\n\n*(Riwayat percakapan telah direset otomatis agar bot dapat membalas kembali)*"

    print(f" 📤 [TELEGRAM SENT] Reply to Chat #{chat_id}: '{reply[:80]}...'")
    await update.message.reply_text(reply)


def run_ai_agent():
    try:
        from telegram import Update
        from telegram.ext import Application, MessageHandler, ContextTypes, filters
    except ImportError:
        print(" [TELEGRAM ERROR] python-telegram-bot is not installed. To run standalone agent: pip install python-telegram-bot")
        return

    token = getattr(config, "TELEGRAM_TOKEN", None) or os.getenv("TELEGRAM_BOT_TOKEN", "") or os.getenv("TELEGRAM_TOKEN", "")
    if not token:
        print(" [TELEGRAM ERROR] TELEGRAM_TOKEN or TELEGRAM_BOT_TOKEN is missing in environment/.env!")
        print("   Please set TELEGRAM_BOT_TOKEN=your_token in your .env file to enable Telegram AI Agent.")
        return

    chat_id = getattr(config, "TELEGRAM_CHAT_ID", "")
    print("=" * 60)
    print(f" 🤖 Starting Telegram AI Agent (Target API: {API_BASE_URL})...")
    print(f" 🔒 Authorized Chat ID: {chat_id if chat_id else 'ANY (Unrestricted)'}")
    print(" ⚡ Polling for Telegram messages...")
    print("=" * 60)

    api_base = getattr(config, "TELEGRAM_API_BASE", "").rstrip("/")
    builder = Application.builder().token(token)
    if api_base and api_base != "https://api.telegram.org":
        builder = builder.base_url(f"{api_base}/bot")
    app = builder.build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling()


if __name__ == "__main__":
    run_ai_agent()

