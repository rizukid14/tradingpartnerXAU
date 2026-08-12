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
from pathlib import Path

# Ensure project root directory is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import json
import requests
import config
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, MessageHandler, ContextTypes, filters

client = OpenAI(api_key=config.OPENAI_API_KEY)
MODEL = "gpt-5.6-luna"  # balanced cost/intelligence

API_BASE_URL = getattr(config, "API_BASE_URL", "http://localhost:8765").rstrip("/")
API_TOKEN = getattr(config, "API_TOKEN", "")
API_TIMEOUT = 8  # seconds

# ---------------------------------------------------------------------------
# 1. HTTP HELPERS - every tool goes through one of these, hitting YOUR bot's API
# ---------------------------------------------------------------------------

def _headers():
    return {"Authorization": f"Bearer {API_TOKEN}"}


def _api_get(path: str, params: dict = None):
    try:
        resp = requests.get(f"{API_BASE_URL}{path}", headers=_headers(), params=params or {}, timeout=API_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"GET {path} failed: {e}"}


def _api_post(path: str, body: dict = None):
    try:
        resp = requests.post(f"{API_BASE_URL}{path}", headers=_headers(), json=body or {}, timeout=API_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"POST {path} failed: {e}"}

# ---------------------------------------------------------------------------
# 2. TOOL IMPLEMENTATIONS - mapped 1:1 to your bot's real API
# ---------------------------------------------------------------------------

def get_summary() -> dict:
    """GET /api/summary - P/L, win rate, total trades, balance, active symbol, recovery status, etc."""
    return _api_get("/api/summary")


def get_open_positions() -> dict:
    """GET /api/open-positions - ticket, symbol, type, volume, SL/TP, floating P/L."""
    return _api_get("/api/open-positions")


def get_recent_trades(limit: int = 10) -> dict:
    """GET /api/recent-trades?limit=N - closed trade history."""
    return _api_get("/api/recent-trades", params={"limit": limit})


def get_config() -> dict:
    """GET /api/config - active bot config (DRY_RUN, risk %, threshold, preset, etc.)."""
    return _api_get("/api/config")


def update_config(updates: dict) -> dict:
    """POST /api/config - change one or more config fields, e.g. {'RISK_PERCENT_BTC': 2.0}."""
    return _api_post("/api/config", body=updates)


def set_strategy_preset(preset: str) -> dict:
    """POST /api/preset - {'preset': 'v3'}."""
    return _api_post("/api/preset", body={"preset": preset})


def pause_trading() -> dict:
    """POST /api/pause - TRADING_PAUSED = True."""
    return _api_post("/api/pause")


def resume_trading() -> dict:
    """POST /api/resume - TRADING_PAUSED = False."""
    return _api_post("/api/resume")


TOOL_FUNCTIONS = {
    "get_summary": get_summary,
    "get_open_positions": get_open_positions,
    "get_recent_trades": get_recent_trades,
    "get_config": get_config,
    "update_config": update_config,
    "set_strategy_preset": set_strategy_preset,
    "pause_trading": pause_trading,
    "resume_trading": resume_trading,
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
    _tool("pause_trading", "Pause the bot - stop opening new trades. Existing open positions are untouched."),
    _tool("resume_trading", "Resume the bot - allow new trades to open again."),
]

SYSTEM_PROMPT = """You are the AI assistant for a multi-LLM consensus trading bot (BTC and XAU/gold).
You talk to the bot's owner over Telegram in whatever language they use (usually Indonesian).

You can answer questions about performance, open positions, trade history, and config by calling
the relevant tool - never guess numbers, always call a tool to get real data.

Before calling update_config, if you're not certain of the exact config key name or its current
value, call get_config first to check - field names must match exactly or the change will be
rejected by the bot.

For any change (config, preset, pause/resume), confirm clearly and briefly what you changed after
the tool call succeeds - mention the old and new value if you have them. If a tool call returns an
error, tell the user plainly what failed; don't pretend it worked.

Be concise - this is a phone chat, not a report. Use bullet points only for actual lists (like open
positions or trade history).

If the user's request is ambiguous (e.g. "make it safer" without specifics), ask ONE clarifying
question rather than guessing at config values - an unwanted change to a live trading bot can cost
real money.
"""

# ---------------------------------------------------------------------------
# 4. AGENT LOOP
# ---------------------------------------------------------------------------

def run_agent_turn(user_text: str, history: list) -> str:
    if not history:
        history.append({"role": "system", "content": SYSTEM_PROMPT})
    messages = history + [{"role": "user", "content": user_text}]

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
            messages.append({"role": "assistant", "content": msg.content})
            history.clear()
            history.extend(messages[-20:])
            return (msg.content or "").strip() or "(tidak ada respon)"

        messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})
        for tool_call in msg.tool_calls:
            func = TOOL_FUNCTIONS.get(tool_call.function.name)
            try:
                args = json.loads(tool_call.function.arguments or "{}")
                result = func(**args) if func else {"error": f"Unknown tool {tool_call.function.name}"}
            except Exception as e:
                result = {"error": str(e)}
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, default=str),
            })

# ---------------------------------------------------------------------------
# 5. TELEGRAM WIRING
# ---------------------------------------------------------------------------

CONVERSATION_HISTORY = []


def is_authorized(update: Update) -> bool:
    return str(update.effective_chat.id) == str(config.TELEGRAM_CHAT_ID)


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    await update.message.chat.send_action("typing")
    try:
        reply = run_agent_turn(update.message.text, CONVERSATION_HISTORY)
    except Exception as e:
        reply = f"[WARN]  Error: {e}"
    await update.message.reply_text(reply)


def run_ai_agent():
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling()


if __name__ == "__main__":
    run_ai_agent()