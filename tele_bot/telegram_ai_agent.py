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

All actual bot data and config live on YOUR bot's own API server — this file
is just the natural-language front end that translates chat into HTTP calls.

Requires:
    pip install openai python-telegram-bot requests

Needs in config.py:
    TELEGRAM_TOKEN
    TELEGRAM_CHAT_ID
    OPENAI_API_KEY
    API_BASE_URL      # e.g. "http://localhost:9000"
    API_TOKEN         # Bearer token your bot's API expects

Wire this up in your main script (or run standalone):
    import threading
    from telegram_ai_agent import run_ai_agent
    threading.Thread(target=run_ai_agent, daemon=True).start()
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
MODEL = "gpt-5.6-luna"  # balanced cost/intelligence. Use "gpt-5.6-luna" for a cheaper/lighter option.

# ---------------------------------------------------------------------------
# 0. MULTI-ACCOUNT REGISTRY
# ---------------------------------------------------------------------------
# Set this in config.py, one entry per account/broker, e.g.:
#
#   ACCOUNTS = {
#       "akun1": {"base_url": "http://localhost:9000", "token": "token-akun1"},
#       "akun2": {"base_url": "http://localhost:9001", "token": "token-akun2"},
#   }
#
# Each entry's API server is the FastAPI/Flask app you already built, running
# against that account's own MT5 bridge port.

ACCOUNTS = config.ACCOUNTS
ACCOUNT_NAMES = list(ACCOUNTS.keys())
API_TIMEOUT = 8  # seconds

# ---------------------------------------------------------------------------
# 1. HTTP HELPERS — every tool goes through one of these, hitting the chosen
#    account's API server
# ---------------------------------------------------------------------------

def _account_or_error(account: str):
    if account not in ACCOUNTS:
        return None, {"error": f"Unknown account '{account}'. Valid accounts: {ACCOUNT_NAMES}"}
    return ACCOUNTS[account], None


def _api_get(account: str, path: str, params: dict = None):
    acc, err = _account_or_error(account)
    if err:
        return err
    try:
        resp = requests.get(
            f"{acc['base_url'].rstrip('/')}{path}",
            headers={"Authorization": f"Bearer {acc['token']}"},
            params=params or {},
            timeout=API_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"GET {path} for {account} failed: {e}"}


def _api_post(account: str, path: str, body: dict = None):
    acc, err = _account_or_error(account)
    if err:
        return err
    try:
        resp = requests.post(
            f"{acc['base_url'].rstrip('/')}{path}",
            headers={"Authorization": f"Bearer {acc['token']}"},
            json=body or {},
            timeout=API_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        return {"error": f"POST {path} for {account} failed: {e}"}

# ---------------------------------------------------------------------------
# 2. TOOL IMPLEMENTATIONS — every tool now takes `account` as first argument
# ---------------------------------------------------------------------------

def get_summary(account: str) -> dict:
    """GET /api/summary — P/L, win rate, total trades, balance, active symbol, recovery status, etc."""
    return _api_get(account, "/api/summary")


def get_open_positions(account: str) -> dict:
    """GET /api/open-positions — ticket, symbol, type, volume, SL/TP, floating P/L."""
    return _api_get(account, "/api/open-positions")


def get_recent_trades(account: str, limit: int = 10) -> dict:
    """GET /api/recent-trades?limit=N — closed trade history."""
    return _api_get(account, "/api/recent-trades", params={"limit": limit})


def get_config(account: str) -> dict:
    """GET /api/config — active bot config (DRY_RUN, risk %, threshold, preset, etc.)."""
    return _api_get(account, "/api/config")


def update_config(account: str, updates: dict) -> dict:
    """POST /api/config — change one or more config fields, e.g. {'RISK_PERCENT_BTC': 2.0}."""
    return _api_post(account, "/api/config", body=updates)


def set_strategy_preset(account: str, preset: str) -> dict:
    """POST /api/preset — {'preset': 'v3'}."""
    return _api_post(account, "/api/preset", body={"preset": preset})


def pause_trading(account: str) -> dict:
    """POST /api/pause — TRADING_PAUSED = True."""
    return _api_post(account, "/api/pause")


def resume_trading(account: str) -> dict:
    """POST /api/resume — TRADING_PAUSED = False."""
    return _api_post(account, "/api/resume")


def list_accounts() -> dict:
    """Returns the account names this agent knows about, so the model can ask/confirm which one to use."""
    return {"accounts": ACCOUNT_NAMES}


TOOL_FUNCTIONS = {
    "get_summary": get_summary,
    "get_open_positions": get_open_positions,
    "get_recent_trades": get_recent_trades,
    "get_config": get_config,
    "update_config": update_config,
    "set_strategy_preset": set_strategy_preset,
    "pause_trading": pause_trading,
    "resume_trading": resume_trading,
    "list_accounts": list_accounts,
}

# ---------------------------------------------------------------------------
# 3. TOOL SCHEMAS (OpenAI function-calling format) — `account` added everywhere
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


_ACCOUNT_PROP = {
    "account": {
        "type": "string",
        "enum": ACCOUNT_NAMES,
        "description": "Which trading account this applies to.",
    }
}


def _with_account(extra_props=None):
    props = dict(_ACCOUNT_PROP)
    props.update(extra_props or {})
    return props


TOOLS = [
    _tool("list_accounts", "List the trading accounts this agent can manage. Call this if the user's account name is unclear or you want to confirm valid options."),
    _tool(
        "get_summary", "Get overall performance summary for one account: P/L, win rate, total trades, balance, active symbol, recovery status.",
        _with_account(), required=["account"],
    ),
    _tool(
        "get_open_positions", "List currently open positions for one account: ticket, symbol, type, volume, SL/TP, floating P/L.",
        _with_account(), required=["account"],
    ),
    _tool(
        "get_recent_trades", "Get recent closed trade history for one account.",
        _with_account({"limit": {"type": "integer", "description": "How many recent trades to fetch (default 10)"}}),
        required=["account"],
    ),
    _tool(
        "get_config", "Read one account's active bot configuration: DRY_RUN, risk %, thresholds, active preset, etc.",
        _with_account(), required=["account"],
    ),
    _tool(
        "update_config",
        "Change one or more config fields on one account's live bot. Pass only the fields being "
        "changed, e.g. {'RISK_PERCENT_BTC': 2.0, 'DRY_RUN': false}. Field names must match the bot's "
        "actual config keys — call get_config first if unsure of exact key names or current values.",
        _with_account({
            "updates": {
                "type": "object",
                "description": "Dictionary of config field(s) to change, matching the bot's config key names exactly.",
            }
        }),
        required=["account", "updates"],
    ),
    _tool(
        "set_strategy_preset", "Apply a strategy preset (e.g. v1, v2, v3) to one account.",
        _with_account({"preset": {"type": "string", "description": "Preset name, e.g. 'v1', 'v2', 'v3'"}}),
        required=["account", "preset"],
    ),
    _tool("pause_trading", "Pause one account — stop opening new trades there. Existing open positions are untouched.", _with_account(), required=["account"]),
    _tool("resume_trading", "Resume one account — allow new trades to open again there.", _with_account(), required=["account"]),
]

SYSTEM_PROMPT = f"""You are the AI assistant for multi-LLM consensus trading bots running on
multiple accounts: {ACCOUNT_NAMES}. You talk to the owner over Telegram in whatever language
they use (usually Indonesian).

Every action/query needs to know WHICH account it applies to. If the user doesn't specify an
account and there is more than one configured, ask ONE clarifying question naming the valid
account options — do not guess or default to one silently, especially for anything that changes
config, pauses/resumes trading, or sends money-relevant instructions.

If the user says "semua akun" / "all accounts" / "both", call the relevant tool once per account
and summarize combined results.

You can answer questions about performance, open positions, trade history, and config by calling
the relevant tool — never guess numbers, always call a tool to get real data.

Before calling update_config, if you're not certain of the exact config key name or its current
value, call get_config first to check — field names must match exactly or the change will be
rejected by the bot.

For any change (config, preset, pause/resume), confirm clearly and briefly what you changed after
the tool call succeeds, including which account — mention the old and new value if you have them.
If a tool call returns an error, tell the user plainly what failed; don't pretend it worked.

Be concise — this is a phone chat, not a report. Use bullet points only for actual lists (like open
positions or trade history), and label which account each item belongs to when discussing more
than one account.
"""

# ---------------------------------------------------------------------------
# 4. AGENT LOOP
# ---------------------------------------------------------------------------

def run_agent_turn(user_text: str, history: list) -> str:
    if not history:
        history.append({"role": "system", "content": SYSTEM_PROMPT})
    messages = history + [{"role": "user", "content": user_text}]

    while True:
        response = client.chat.completions.create(model=MODEL, tools=TOOLS, messages=messages)
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
        reply = f"⚠️ Error: {e}"
    await update.message.reply_text(reply)


def run_ai_agent():
    app = Application.builder().token(config.TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.run_polling()


if __name__ == "__main__":
    run_ai_agent()