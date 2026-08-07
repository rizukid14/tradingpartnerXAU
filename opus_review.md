# Opus Review — Multi-LLM Consensus Trading Bot (Protected Edition)

> Complete guide for setup, configuration, and operation.
> Reviewed & written by Claude Opus 4.6 on 2026-08-07.

---

## Table of Contents

1. [What This Bot Does](#what-this-bot-does)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Step-by-Step Setup](#step-by-step-setup)
5. [Configuration Reference](#configuration-reference)
6. [How the Bot Works](#how-the-bot-works)
7. [Protection Features Explained](#protection-features-explained)
8. [Telegram Setup (Optional)](#telegram-setup-optional)
9. [Running the Bot](#running-the-bot)
10. [Tuning Guide](#tuning-guide)
11. [Troubleshooting](#troubleshooting)
12. [Feature Origins](#feature-origins)

---

## What This Bot Does

This is an **AI-powered scalping bot** for **XAUUSD (Gold)** on **MetaTrader 5**.

**Signal Generation:**
- Sends the latest M5 (5-minute) market data + technical indicators (RSI, EMA, ATR) to **3 LLMs in parallel**: OpenAI, Google Gemini, and DeepSeek
- Each LLM returns a JSON decision: `BUY`, `SELL`, or `HOLD` with confidence, SL/TP suggestions, and reasoning
- A **consensus engine** requires 2 out of 3 models to agree before executing any trade

**Execution & Protection:**
- After entry, positions are actively managed with trailing stops, break-even, and partial closes
- A comprehensive risk engine gates every trade with 8 checks: daily loss, spread, session, danger zones, weekend, cooldown, consecutive losses, and max positions

---

## Project Structure

```
tradingpartner/
├── main.py               # Main loop — runs everything
├── config.py             # All settings (trading, risk, sessions, alerts)
├── .env                  # API keys & MT5 credentials (PRIVATE - never share!)
├── .env.example          # Template for .env
│
├── llm_client.py         # Calls OpenAI, Gemini, DeepSeek in parallel
├── consensus.py          # 2-of-3 voting engine
├── mt5_connector.py      # MT5 connection, data fetch, order execution
│
├── risk_engine.py        # Trade gating: daily loss, session, spread, recovery
├── position_manager.py   # Trailing stop, break-even, partial close
├── telegram_alerts.py    # Telegram notifications (optional)
│
├── test_apis.py          # Test if your API keys work
└── requirements.txt      # Python dependencies
```

---

## Prerequisites

| Requirement | Details |
|:------------|:--------|
| **OS** | Windows (MT5 library is Windows-only) |
| **Python** | 3.8 – 3.11 recommended |
| **MetaTrader 5** | Installed & logged into your broker account (demo or live) |
| **API Keys** | OpenAI, Google Gemini, and DeepSeek API keys with active credit |

---

## Step-by-Step Setup

### 1. Install Python Dependencies

Open PowerShell in the project folder and run:

```bash
pip install -r requirements.txt
```

This installs:
- `MetaTrader5` — MT5 API bridge
- `pandas`, `numpy` — data processing
- `ta` — technical indicators (RSI, EMA, ATR)
- `openai` — OpenAI & DeepSeek API client
- `google-generativeai` — Gemini API client
- `python-dotenv` — .env file loading
- `requests` — Telegram API calls

### 2. Configure Your `.env` File

Copy the template:

```bash
copy .env.example .env
```

Then open `.env` and fill in your keys:

```env
# API Keys — ALL 3 REQUIRED
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxx
GEMINI_API_KEY=AIzaSyxxxxxxxxxx
DEEPSEEK_API_KEY=sk-xxxxxxxxxx

# API Base URLs (usually leave as default)
OPENAI_API_BASE=https://api.openai.com/v1
DEEPSEEK_API_BASE=https://api.deepseek.com/v1

# MT5 Account (optional — leave blank to use the currently open MT5 terminal)
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=VTMarkets-Server

# Telegram (optional — set to true and fill in to receive alerts)
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

> ⚠️ **NEVER commit `.env` to git or share it. It contains your API keys and MT5 password.**

### 3. Test Your API Keys

```bash
python test_apis.py
```

This will call each API with a simple prompt and confirm they respond. Fix any failures before proceeding.

### 4. Open MetaTrader 5

- Launch MT5 and log into your **demo account** (strongly recommended for first tests)
- Make sure `XAUUSD` is visible in your Market Watch
- Keep MT5 running — the bot needs it open

### 5. Run the Bot

```bash
python main.py
```

The bot starts in **DRY RUN mode** by default — it generates signals and logs them but does NOT place real orders.

---

## Configuration Reference

All settings are in `config.py`. Here's every parameter:

### Core Trading

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `SYMBOL` | `"XAUUSD"` | Trading instrument |
| `TIMEFRAME` | `mt5.TIMEFRAME_M5` | 5-minute candles |
| `LOT_SIZE` | `0.01` | Base lot size (micro-lot) |
| `DEVIATION` | `20` | Slippage tolerance in points |
| `DEFAULT_SL_POINTS` | `300` | Fallback stop loss (300 pts = $3.00) |
| `DEFAULT_TP_POINTS` | `600` | Fallback take profit (600 pts = $6.00) |
| `DRY_RUN` | `True` | `True` = signal only, `False` = live trading |
| `CONSENSUS_THRESHOLD` | `2` | Models that must agree (2 of 3) |

### AI Models

| Setting | Default | Notes |
|:--------|:--------|:------|
| `OPENAI_MODEL` | `"5-nano"` | Change to any OpenAI model name |
| `GEMINI_MODEL` | `"gemini-2.5-flash"` | Change to any Gemini model |
| `DEEPSEEK_MODEL` | `"v4-pro"` | Change to any DeepSeek model |

### Trailing Stop

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `TRAILING_STOP_ENABLED` | `True` | Enable/disable |
| `TRAILING_ACTIVATION_POINTS` | `200` | Start trailing after 200 pts profit |
| `TRAILING_DISTANCE_POINTS` | `150` | Keep SL 150 pts behind price |

### Break-Even

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `BREAK_EVEN_ENABLED` | `True` | Enable/disable |
| `BREAK_EVEN_TRIGGER_POINTS` | `300` | Move SL to entry after 300 pts |
| `BREAK_EVEN_PADDING_POINTS` | `10` | Pad SL 10 pts above entry |

### Partial Close

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `PARTIAL_CLOSE_ENABLED` | `True` | Enable/disable |
| `PARTIAL_CLOSE_PERCENT` | `50` | Close 50% of position |
| `PARTIAL_CLOSE_TP1_POINTS` | `400` | Trigger at 400 pts profit |

### Daily Risk Limits

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `MAX_DAILY_LOSS_USD` | `50.0` | Stop trading after $50 loss today |
| `MAX_CONSECUTIVE_LOSSES` | `3` | Pause after 3 losses in a row |
| `PAUSE_AFTER_LOSSES_MINUTES` | `30` | Pause duration |
| `MAX_OPEN_POSITIONS` | `1` | Max simultaneous trades |

### Recovery Mode

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `RECOVERY_MODE_ENABLED` | `True` | Activate after consecutive losses |
| `RECOVERY_LOT_MULTIPLIER` | `0.5` | Use 50% of normal lot during recovery |

### Cooldown

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `TRADE_COOLDOWN_SECONDS` | `60` | Wait 60s between new trades |

### Spread Filter

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `MAX_SPREAD_POINTS` | `50` | Block trades above 50 pts spread |

### Session Filter (WIB Timezone)

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `SESSION_FILTER_ENABLED` | `True` | Enable/disable |
| `ALLOWED_SESSIONS_WIB` | See below | Sessions with lot multipliers |

**Allowed Sessions:**

| Session | WIB Hours | Lot Multiplier |
|:--------|:----------|:---------------|
| Tokyo | 07:00 – 16:00 | x0.7 (reduced) |
| London | 15:00 – 23:59 | x1.0 (normal) |
| London-NY Overlap 🔥 | 20:00 – 23:59 | x1.2 (boosted) |
| NY | 20:00 – 05:00 | x1.0 (normal) |

**Danger Zones (always blocked):**

| Zone | WIB Hours | Reason |
|:-----|:----------|:-------|
| Rollover | 04:00 – 06:00 | Spread extremely wide |
| Dead Zone | 00:00 – 04:00 | Very low liquidity |

### Weekend Protection

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `WEEKEND_CLOSE_ENABLED` | `True` | Auto-manage positions before weekend |
| `WEEKEND_CLOSE_PROFIT_MIN_USD` | `1.0` | Take profit if ≥ $1 near close |
| `WEEKEND_CLOSE_HOURS_BEFORE` | `2.0` | Check 2 hours before Friday close |
| `WEEKEND_MAX_LOSS_TO_HOLD_USD` | `20.0` | Cut loss if > $20 before weekend |

### Telegram

| Setting | Default | What It Does |
|:--------|:--------|:-------------|
| `TELEGRAM_ENABLED` | `false` (in .env) | Set to `true` to enable |
| `TELEGRAM_BOT_TOKEN` | (in .env) | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | (in .env) | Your chat/group ID |

---

## How the Bot Works

### Main Loop (every 5 seconds)

```
┌─────────────────────────────────────────────────────┐
│                    EVERY 5 SECONDS                   │
│                                                      │
│  1. position_manager.manage_all_positions()          │
│     ├─ Partial Close: sell 50% at TP1 (400 pts)     │
│     ├─ Break-Even: move SL to entry at 300 pts      │
│     └─ Trailing Stop: trail SL 150 pts at 200+ pts  │
│                                                      │
│  2. risk.check_weekend_positions()                   │
│     └─ Friday: close profits, cut large losses       │
│                                                      │
│  3. IF new M5 candle detected:                       │
│     ├─ Display daily P/L, recovery status            │
│     ├─ risk.can_trade() ← 8 checks:                 │
│     │   ├─ Consecutive loss pause                    │
│     │   ├─ Daily loss limit ($50)                    │
│     │   ├─ Max open positions (1)                    │
│     │   ├─ Trade cooldown (60s)                      │
│     │   ├─ Spread filter (50 pts)                    │
│     │   ├─ Danger zone (rollover/dead)               │
│     │   ├─ Weekend block (Fri 22:00+)                │
│     │   └─ Session filter → set lot multiplier       │
│     │                                                │
│     ├─ IF all checks pass:                           │
│     │   ├─ Fetch 50 M5 candles + indicators          │
│     │   ├─ Send to OpenAI + Gemini + DeepSeek        │
│     │   ├─ 2-of-3 consensus check                    │
│     │   ├─ Calculate dynamic lot size:               │
│     │   │   ├─ Base lot × recovery multiplier        │
│     │   │   └─ × session multiplier                  │
│     │   └─ Execute trade via MT5                     │
│     │                                                │
│     └─ IF any check fails:                           │
│         └─ Log reason, skip cycle                    │
└─────────────────────────────────────────────────────┘
```

### Trade Lifecycle Example

```
1. Entry: BUY XAUUSD @ 2650.00 (SL: 2647.00, TP: 2656.00)
   └─ Lot: 0.01 × session x1.2 = 0.01

2. Price hits 2652.00 (+200 pts) → Trailing Stop ACTIVATED
   └─ SL moved from 2647.00 → 2650.50 (150 pts behind)

3. Price hits 2653.00 (+300 pts) → Break-Even TRIGGERED
   └─ SL moved to 2650.10 (entry + 10 pts padding)
   └─ (Trailing already moved SL higher, so this is a no-op)

4. Price hits 2654.00 (+400 pts) → Partial Close TP1
   └─ 50% of position closed at profit
   └─ Remaining 50% continues with trailing stop

5. Price reaches 2656.00 (+600 pts) → TP hit on remaining
   └─ Full position closed
```

---

## Protection Features Explained

### 1. Trailing Stop
Once profit exceeds the activation threshold (200 pts), the stop loss follows price at a fixed distance (150 pts). It only moves in the profitable direction — never backwards. This locks in gains without cutting winners short.

### 2. Break-Even
Once profit exceeds 300 pts, stop loss moves to entry price + 10 pts. This guarantees you can't lose money on this trade (worst case: +$0.10).

### 3. Partial Close
At 400 pts profit, 50% of the position is closed to secure profit. The remaining 50% continues with trailing stop, giving the trade room to run further.

### 4. Daily Loss Limit
If today's total realized losses exceed $50, the bot halts all new trades for the rest of the day. Prevents revenge trading.

### 5. Recovery Mode
After 3 consecutive losses, the bot:
- Pauses for 30 minutes
- Switches to recovery mode: lot size × 0.5
- Recovery mode ends after 1 winning trade

### 6. Session Filter (WIB)
Only opens trades during liquid market sessions. Adjusts lot size per session:
- Tokyo (07-16 WIB): lot × 0.7 (less volatile, smaller position)
- London (15-24 WIB): lot × 1.0
- London-NY Overlap (20-24 WIB): lot × 1.2 (best XAUUSD hours)

### 7. Danger Zone Block
Never opens trades during:
- 00:00 – 04:00 WIB (dead zone, no liquidity)
- 04:00 – 06:00 WIB (rollover, spreads spike 10x+)

### 8. Weekend Protection
On Friday nights:
- Closes profitable positions (≥ $1) to avoid weekend gap risk
- Cuts losses exceeding $20 (too risky to hold over 2-day gap)
- Blocks all new entries after 22:00 WIB Friday

### 9. Spread Filter
Skips trade if current spread > 50 pts. High spread = bad fill price + increased risk.

### 10. Cooldown
Waits at least 60 seconds between new trades. Prevents rapid-fire entries from consecutive candle signals.

### 11. Telegram Alerts
Optional notifications for:
- Bot startup (full config)
- Trade opened (signal, lot, SL/TP)
- Risk halts (with reason)
- Weekend closes
- Daily summary on shutdown

---

## Telegram Setup (Optional)

### Step 1: Create a Bot

1. Open Telegram, search for `@BotFather`
2. Send `/newbot`
3. Choose a name (e.g., "My Trading Bot")
4. Choose a username (e.g., `my_xauusd_bot`)
5. Copy the **bot token** (looks like `123456789:ABCdefGHIjklmNOPqrstUVWxyz`)

### Step 2: Get Your Chat ID

1. Start a chat with your new bot (send any message)
2. Open this URL in your browser (replace `YOUR_TOKEN`):
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
3. Find `"chat":{"id":123456789}` — that number is your Chat ID

### Step 3: Configure `.env`

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklmNOPqrstUVWxyz
TELEGRAM_CHAT_ID=123456789
```

---

## Running the Bot

### Dry Run (Safe — No Real Trades)

```bash
python main.py
```

Default `DRY_RUN = True` in `config.py`. The bot:
- Connects to MT5
- Fetches real market data
- Queries all 3 AI models
- Shows consensus decisions
- Simulates order placement (no real money)

### Live Trading

1. **Switch to live** in `config.py`:
   ```python
   DRY_RUN = False
   ```
2. **Use a DEMO account first!**
3. Run: `python main.py`
4. Press `Ctrl+C` to stop the bot gracefully

---

## Tuning Guide

### For Conservative Trading (Lower Risk)

```python
LOT_SIZE = 0.01
MAX_DAILY_LOSS_USD = 25.0
MAX_CONSECUTIVE_LOSSES = 2
TRAILING_ACTIVATION_POINTS = 150
PARTIAL_CLOSE_TP1_POINTS = 300
RECOVERY_LOT_MULTIPLIER = 0.3
```

### For Aggressive Trading (Higher Risk)

```python
LOT_SIZE = 0.05
MAX_DAILY_LOSS_USD = 100.0
MAX_CONSECUTIVE_LOSSES = 5
TRAILING_ACTIVATION_POINTS = 300
TRAILING_DISTANCE_POINTS = 200
PARTIAL_CLOSE_ENABLED = False  # Let full position ride
```

### To Disable Any Feature

Set its `_ENABLED` flag to `False` in `config.py`:

```python
TRAILING_STOP_ENABLED = False
BREAK_EVEN_ENABLED = False
PARTIAL_CLOSE_ENABLED = False
SESSION_FILTER_ENABLED = False
WEEKEND_CLOSE_ENABLED = False
RECOVERY_MODE_ENABLED = False
```

---

## Troubleshooting

| Problem | Solution |
|:--------|:---------|
| `MT5 Inisialisasi gagal` | Make sure MT5 app is open and logged in |
| `Simbol XAUUSD tidak ditemukan` | Add XAUUSD to your Market Watch in MT5 |
| `OpenAI Error` / `Gemini Error` | Check API key validity and credit balance |
| `Spread terlalu tinggi` | Normal during rollover (04-06 WIB). Wait for London session |
| `Di luar sesi trading` | Bot is waiting for allowed session. Check `ALLOWED_SESSIONS_WIB` |
| `Batas kerugian harian tercapai` | Bot halted for today. Will resume tomorrow |
| `Pause setelah loss berturut-turut` | Wait 30 min or restart bot (streak resets) |
| Bot does nothing | Check: is DRY_RUN True? Is MT5 open? Are API keys valid? |
| Telegram not sending | Check `TELEGRAM_ENABLED=true` in .env (not config.py) |

---

## Feature Origins

Every protection feature was extracted from two open-source trading bots:

| Feature | Source Repository | Original File |
|:--------|:-----------------|:-------------|
| Trailing Stop | [XAU-60](https://github.com/lordgaruda/XAU-60) | `core/trade_executor.py` |
| Break-Even | [XAU-60](https://github.com/lordgaruda/XAU-60) | `core/trade_executor.py` |
| Partial Close | [XAU-60](https://github.com/lordgaruda/XAU-60) | `core/trade_executor.py` |
| Daily Loss Halt | Both repos | `core/risk_manager.py` / `src/smart_risk_manager.py` |
| Consecutive Loss Pause | [XAU-60](https://github.com/lordgaruda/XAU-60) | `core/risk_manager.py` |
| Recovery Mode | [xaubot-ai](https://github.com/GifariKemal/xaubot-ai) | `src/smart_risk_manager.py` |
| Session Filter + Lot Multiplier | [xaubot-ai](https://github.com/GifariKemal/xaubot-ai) | `src/session_filter.py` |
| Danger Zones | [xaubot-ai](https://github.com/GifariKemal/xaubot-ai) | `src/session_filter.py` |
| Weekend Close | [xaubot-ai](https://github.com/GifariKemal/xaubot-ai) | `src/position_manager.py` |
| Cooldown | [xaubot-ai](https://github.com/GifariKemal/xaubot-ai) | `src/smart_risk_manager.py` |
| Spread Filter | Both repos | Multiple files |
| Telegram Alerts | Both repos | `alerts/telegram_bot.py` / `src/telegram_notifier.py` |

---

## ⚠️ Disclaimer

Trading Forex and Gold carries a very high level of risk. This bot is a technological tool — not financial advice. Always test on a demo account first. Past performance of AI models does not guarantee future results. You are fully responsible for any trades placed by this bot.
