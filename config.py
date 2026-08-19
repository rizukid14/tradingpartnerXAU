import os
import sys
if sys.platform == 'win32':
    import MetaTrader5 as mt5
else:
    try:
        from mt5linux import MetaTrader5 as mt5
    except ImportError:
        import MetaTrader5 as mt5
from dotenv import load_dotenv

# --- PATH & DIRECTORY SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Add modular package search paths
for path in [BASE_DIR, os.path.join(BASE_DIR, "src"), os.path.join(BASE_DIR, "src", "core"), os.path.join(BASE_DIR, "src", "analytics")]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Load environmental variables from .env file
load_dotenv(os.path.join(BASE_DIR, ".env"))


# --- API KEYS ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# --- API BASE URLS ---
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")

# --- MODEL NAMES & FALLBACKS ---
# DeepSeek Model & Fallback (Official production endpoint)
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_FALLBACK_MODEL = "deepseek-v4-flash"


# Gemini Model & Fallback
GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_FALLBACK_MODEL = "gemini-3.1-flash-lite"

# OpenAI Model & Fallback
OPENAI_MODEL = "gpt-5.4-mini"
OPENAI_FALLBACK_MODEL = "gpt-4o-mini"

# Maximum time (seconds) per model before triggering fallback
LLM_TIMEOUT_SECONDS = 24.0



# --- TRADING PARAMETERS ---
# Symbol to trade (e.g., "XAUUSD" for Gold, "EURUSD" for Forex)
SYMBOL = "XAUUSD-ECNc"

# Timeframe for Scalping: 5 Minutes
TIMEFRAME = mt5.TIMEFRAME_M5

# Default trade size (0.01 is micro-lot)
LOT_SIZE = 0.01

# Deviation (slippage tolerance in points)
DEVIATION = 20

# Risk Management: SL/TP settings (calculated dynamically in Python based on ATR)
DEFAULT_SL_POINTS = 300
DEFAULT_TP_POINTS = 600
SL_ATR_MULTIPLIER = 1.5   # Stop Loss = 1.5x ATR
TP_ATR_MULTIPLIER = 3.0   # Take Profit = 3.0x ATR (Risk-to-Reward 1:2)


# --- CONSENSUS SETTINGS ---
# Mode: DRY_RUN = True means signals are generated and logged, but no orders are sent to MT5.
# Set to False to enable live trading on MT5.
DRY_RUN = False




# Minimum number of models that must agree (e.g., 2 out of 3)
CONSENSUS_THRESHOLD = 2

# ============================================================================
#                     PROTECTION & EXECUTION LAYER
#           (Inspired by XAU-60 execution engine & xaubot-ai risk system)
# ============================================================================

# --- TRAILING STOP (from XAU-60 trade_executor.py) ---
# Automatically trails stop loss behind price to lock in profits
TRAILING_STOP_ENABLED = True
TRAILING_ACTIVATION_POINTS = 200   # Activate trailing after 200 pts profit (~$2.00 on Gold)
TRAILING_DISTANCE_POINTS = 150     # Trail SL 150 pts behind current price

# --- BREAK-EVEN (from XAU-60 trade_executor.py) ---
# Moves stop loss to entry price once trade reaches profit threshold
BREAK_EVEN_ENABLED = True
BREAK_EVEN_TRIGGER_POINTS = 300    # Move SL to entry after 300 pts profit (~$3.00)
BREAK_EVEN_PADDING_POINTS = 10     # Pad SL 10 pts above entry for safety

# --- PARTIAL CLOSE (from XAU-60 trade_executor.py) ---
# Close portion of position at first target, let the rest ride with trailing stop
PARTIAL_CLOSE_ENABLED = True
PARTIAL_CLOSE_PERCENT = 50         # Close 50% of position at TP1
PARTIAL_CLOSE_TP1_POINTS = 400     # TP1 trigger: 400 pts profit (~$4.00)

# --- DAILY RISK LIMITS (from xaubot-ai smart_risk_manager.py) ---
MAX_DAILY_LOSS_USD = 50.0          # Halt all trading after losing $50 today
MAX_CONSECUTIVE_LOSSES = 3         # Pause trading after 3 consecutive losses
PAUSE_AFTER_LOSSES_MINUTES = 30    # Pause duration after consecutive losses
MAX_OPEN_POSITIONS = 6             # Max simultaneous positions (fits 3x layering cycles of 2 positions)



# --- RECOVERY MODE (from xaubot-ai smart_risk_manager.py) ---
# After hitting daily loss or consecutive losses, reduce lot size
RECOVERY_MODE_ENABLED = True
RECOVERY_LOT_MULTIPLIER = 0.5     # Use 50% of normal lot size during recovery

# --- COOLDOWN (from xaubot-ai smart_risk_manager.py) ---
# Set to 0 because main loop already runs every 5 minutes on candle closures
TRADE_COOLDOWN_SECONDS = 0


# --- SPREAD FILTER (from both repos) ---
# Skip trade entry if spread is too wide (common during news/low liquidity)
MAX_SPREAD_POINTS = 50             # Max allowed spread in points (50 pts = ~$0.50 on Gold)

# --- SESSION FILTER (from xaubot-ai session_filter.py) ---
# Only allow new trades during high-liquidity market sessions
# Times in WIB (GMT+7) to match your timezone (Jakarta/Batam)
SESSION_FILTER_ENABLED = True
ALLOWED_SESSIONS_WIB = [
    {"name": "Tokyo",          "start": (7, 0),  "end": (16, 0),  "lot_multiplier": 0.7},
    {"name": "London",         "start": (15, 0), "end": (23, 59), "lot_multiplier": 1.0},
    {"name": "London-NY (🔥)", "start": (20, 0), "end": (23, 59), "lot_multiplier": 1.2},
    {"name": "NY",             "start": (20, 0), "end": (5, 0),   "lot_multiplier": 1.0},
]

# Danger zones — never trade during these hours (WIB)
DANGER_ZONES_WIB = [
    {"name": "Rollover",  "start": (4, 0), "end": (6, 0), "reason": "Spread melebar saat rollover"},
    {"name": "Dead Zone", "start": (0, 0), "end": (4, 0), "reason": "Likuiditas rendah"},
]

# --- WEEKEND PROTECTION (from xaubot-ai position_manager.py) ---
# Close profitable positions before weekend to avoid gap risk
WEEKEND_CLOSE_ENABLED = True
WEEKEND_CLOSE_PROFIT_MIN_USD = 1.0   # Close if profit >= $1 and near weekend close
WEEKEND_CLOSE_HOURS_BEFORE = 2.0     # Start checking 2 hours before Friday close
WEEKEND_MAX_LOSS_TO_HOLD_USD = 20.0  # Max loss $ to hold over weekend (larger = cut loss)

# --- TELEGRAM ALERTS (from both repos) ---
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")


# --- MT5 CONNECTION ---
# Leave empty to connect to the currently running MT5 terminal instance
MT5_LOGIN = os.getenv("MT5_LOGIN", "")
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER = os.getenv("MT5_SERVER", "")

# Unique ID for orders placed by this bot (only bot positions are managed/risked)
MAGIC_NUMBER = 20260625

if MT5_LOGIN:
    MT5_LOGIN = int(MT5_LOGIN)

# --- MULTI-TIMEFRAME & FUNDAMENTAL SETTINGS ---
MTF_ANALYSIS_ENABLED = True
# Dict of timeframe labels to MT5 timeframe constants
# For Gold scalping, we analyze 30-minute and 1-hour timeframes
HIGHER_TIMEFRAMES = {
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1
}

FUNDAMENTAL_ANALYSIS_ENABLED = True
# Model that performs background macro/fundamental analysis
PRIMARY_ANALYSIS_MODEL = GEMINI_MODEL

# --- LOGGING SETTINGS ---
LOG_FILE = "trading_bot.log"

