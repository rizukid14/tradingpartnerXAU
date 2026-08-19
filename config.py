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
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_FALLBACK_MODEL = "deepseek-v4-flash"

GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_FALLBACK_MODEL = "gemini-3.1-flash-lite"

OPENAI_MODEL = "gpt-5.4-mini"
OPENAI_FALLBACK_MODEL = "gpt-4o-mini"

# Maximum time (seconds) per model before triggering fallback
LLM_TIMEOUT_SECONDS = 24.0

# --- TRADING PARAMETERS ---
MT5_ACCOUNT_MODE = os.getenv("MT5_ACCOUNT_MODE", "demo").lower()
SYMBOL = os.getenv("SYMBOL", "XAUUSD-ECN" if MT5_ACCOUNT_MODE == "demo" else "XAUUSD-ECNc")
TIMEFRAME = mt5.TIMEFRAME_M5
LOT_SIZE = 0.01
DEVIATION = 20

# Risk Management: Mega-Tight SL/TP settings (Super-Tight SL -> Mega Lot Jumbo)
DEFAULT_SL_POINTS = 40
DEFAULT_TP_POINTS = 50
MIN_SL_POINTS = 30
MAX_SL_POINTS = 60
MIN_TP_POINTS = 40
MAX_TP_POINTS = 80

# --- CONSENSUS & FORECAST SETTINGS ---
DRY_RUN = False
CONSENSUS_THRESHOLD = 2
DEBATE_ENABLED = False
FORECAST_ENABLED = False

# --- TRAILING STOP (Disabled for Pure Fast TP/SL Execution) ---
TRAILING_STOP_ENABLED = False
TRAILING_ACTIVATION_PERCENT_TP = 50
TRAILING_ACTIVATION_POINTS = 500
TRAILING_DISTANCE_POINTS = 200

# --- BREAK-EVEN ---
BREAK_EVEN_ENABLED = True
BREAK_EVEN_TRIGGER_POINTS = 300    # Move SL to entry after 300 pts profit (~$3.00)
BREAK_EVEN_PADDING_POINTS = 10     # Pad SL 10 pts above entry for safety

# --- PARTIAL CLOSE ---
PARTIAL_CLOSE_ENABLED = True
PARTIAL_CLOSE_PERCENT = 50         # Close 50% of position at TP1
PARTIAL_CLOSE_TP1_POINTS = 400     # TP1 trigger: 400 pts profit (~$4.00)

# --- DAILY RISK LIMITS ---
MAX_DAILY_LOSS_USD = 99999.0       # Daily loss limit disabled
MAX_CONSECUTIVE_LOSSES = 999       # Pause after consecutive losses disabled
PAUSE_AFTER_LOSSES_MINUTES = 0     # Pause duration disabled
MAX_OPEN_POSITIONS = 6             # Max simultaneous positions

# --- RECOVERY MODE (Disabled) ---
RECOVERY_MODE_ENABLED = False
RECOVERY_LOT_MULTIPLIER = 1.0

# --- COOLDOWN ---
TRADE_COOLDOWN_SECONDS = 0

# --- SPREAD FILTER ---
MAX_SPREAD_POINTS = 50             # Max allowed spread in points (50 pts = ~$0.50 on Gold)

# --- SESSION FILTER ---
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

# --- WEEKEND PROTECTION ---
WEEKEND_CLOSE_ENABLED = True
WEEKEND_CLOSE_PROFIT_MIN_USD = 1.0
WEEKEND_CLOSE_HOURS_BEFORE = 2.0
WEEKEND_MAX_LOSS_TO_HOLD_USD = 20.0

# --- TELEGRAM ALERTS ---
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")

# --- RISK PERCENTAGE ---
RISK_PERCENT = float(os.getenv("RISK_PERCENT", "1.5"))

# --- MT5 CONNECTION ---
if MT5_ACCOUNT_MODE == "demo":
    MT5_LOGIN = os.getenv("MT5_DEMO_LOGIN", "")
    MT5_PASSWORD = os.getenv("MT5_DEMO_PASSWORD", "")
    MT5_SERVER = os.getenv("MT5_DEMO_SERVER", "")
else:
    MT5_LOGIN = os.getenv("MT5_LIVE_LOGIN", os.getenv("MT5_LOGIN", ""))
    MT5_PASSWORD = os.getenv("MT5_LIVE_PASSWORD", os.getenv("MT5_PASSWORD", ""))
    MT5_SERVER = os.getenv("MT5_LIVE_SERVER", os.getenv("MT5_SERVER", ""))

MAGIC_NUMBER = 20260625

if MT5_LOGIN:
    try:
        MT5_LOGIN = int(MT5_LOGIN)
    except Exception:
        pass

# --- MULTI-TIMEFRAME & FUNDAMENTAL SETTINGS ---
MTF_ANALYSIS_ENABLED = False
HIGHER_TIMEFRAMES = {
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1
}

FUNDAMENTAL_ANALYSIS_ENABLED = False
PRIMARY_ANALYSIS_MODEL = GEMINI_MODEL

# --- LOGGING SETTINGS ---
LOG_FILE = os.path.join(DATA_DIR, "trading_bot.log")
