import os
import sys
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

# --- ENV PARSING HELPERS ---
def _getenv_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")

def _getenv_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default

def _getenv_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default

# --- MT5 HOST & PORT CONFIG ---
MT5_HOST = os.getenv("MT5_HOST", "localhost")
MT5_PORT = _getenv_int("MT5_PORT", 18812)

class DummyMT5:
    """Fallback MT5 object when MT5 is not available or disconnected."""
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408

    def initialize(self, *args, **kwargs):
        return False

    def shutdown(self):
        pass

    def symbol_info_tick(self, *args, **kwargs):
        return None

    def symbol_info(self, *args, **kwargs):
        return None

    def copy_rates_from_pos(self, *args, **kwargs):
        return None

    def last_error(self):
        return (-1, "MT5 not connected")

if sys.platform == 'win32':
    try:
        import MetaTrader5 as mt5
    except ImportError:
        mt5 = DummyMT5()
else:
    mt5_obj = None
    try:
        import rpyc
        conn = rpyc.classic.connect(MT5_HOST, MT5_PORT)
        mt5_obj = conn.modules.MetaTrader5
    except Exception as e1:
        try:
            from mt5linux import MetaTrader5
            mt5_obj = MetaTrader5(host=MT5_HOST, port=MT5_PORT)
        except Exception as e2:
            print(f"[CONFIG WARNING] Could not initialize remote MT5 connection ({e1}; {e2})")
    
    mt5 = mt5_obj if mt5_obj is not None else DummyMT5()


# --- API KEYS ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# --- TELEGRAM & BOT API CONFIG ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8765")
API_TOKEN = os.getenv("API_TOKEN", "")

# --- API BASE URLS ---
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")


# --- MODEL NAMES & FALLBACKS ---
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "deepseek/deepseek-v4-flash")
CLAUDE_FALLBACK_MODEL = os.getenv("CLAUDE_FALLBACK_MODEL", "claude-haiku-4-5-20251001")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-5.4-mini")

LLM_TIMEOUT_SECONDS = _getenv_float("LLM_TIMEOUT_SECONDS", 24.0)

# Forecast Engine: primary & fallback models
FORECAST_MODEL = os.getenv("FORECAST_MODEL", "gpt-5.4")
FORECAST_FALLBACK_MODEL = os.getenv("FORECAST_FALLBACK_MODEL", "gemini-3.5-flash")


# --- TRADING PARAMETERS ---
# Symbol rotation: XAUUSD on weekdays, BTCUSD on weekends (crypto 24/7 while FX closed)
WEEKDAY_SYMBOL = os.getenv("WEEKDAY_SYMBOL", "XAUUSD-ECN")  # base name; get_valid_trade_symbol auto-corrects suffix (live -> XAUUSD-ECNc, demo -> XAUUSD-ECN)
WEEKEND_SYMBOL = os.getenv("WEEKEND_SYMBOL", "BTCUSD.c")
CRYPTO_SYMBOLS = {"BTCUSD.c", "BTCUSD", "BTCUSD.ecn", "BTCUSD.m", "BTCUSD.MT5", "BTCUSD.pro"}
ENABLE_BTC_ROTATION = _getenv_bool("ENABLE_BTC_ROTATION", False)
SYMBOL = os.getenv("SYMBOL", WEEKDAY_SYMBOL)

# --- TRADING MODE: "xau" (default, XAU only) | "xau_pairs" (XAU + FX cross pairs, round-robin per candle) ---
# FX cross pairs (non-USD => low correlation with XAUUSD). Base names — get_valid_trade_symbol
# auto-corrects broker suffix at runtime (live -> -ECNc, demo -> -ECN).
TRADING_MODE = os.getenv("TRADING_MODE", "xau").strip().lower()
FX_PAIR_SYMBOLS = [
    s.strip()
    for s in os.getenv(
        "FX_PAIR_SYMBOLS",
        "EURGBP-ECN,EURJPY-ECN,EURCAD-ECN,GBPJPY-ECN",
    ).split(",")
    if s.strip()
]
MAX_ROTATION_SYMBOLS = _getenv_int("MAX_ROTATION_SYMBOLS", 5)  # max symbols in the rotation pool

TIMEFRAME_STR = os.getenv("TIMEFRAME", "M5").upper()
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}
TIMEFRAME = TIMEFRAME_MAP.get(TIMEFRAME_STR, mt5.TIMEFRAME_M5)
H1_TIMEFRAME = mt5.TIMEFRAME_H1

STARTING_BALANCE = _getenv_float("STARTING_BALANCE", 1000.0)

LOT_SIZE = _getenv_float("LOT_SIZE", 0.01)
LOT_SIZE_XAU = _getenv_float("LOT_SIZE_XAU", LOT_SIZE)
LOT_SIZE_BTC = _getenv_float("LOT_SIZE_BTC", 0.01)

RISK_PERCENT_BTC = _getenv_float("RISK_PERCENT_BTC", 1.5)
RISK_PERCENT_XAU = _getenv_float("RISK_PERCENT_XAU", 0.5)

DEVIATION = _getenv_int("DEVIATION", 20)

TP_SL_RULES = os.getenv("TP_SL_RULES", "ATR-Based")

DEFAULT_SL_POINTS = _getenv_int("DEFAULT_SL_POINTS", 300)
DEFAULT_TP_POINTS = _getenv_int("DEFAULT_TP_POINTS", 600)
SL_ATR_MULTIPLIER = _getenv_float("SL_ATR_MULTIPLIER", 1.5)
TP_ATR_MULTIPLIER = _getenv_float("TP_ATR_MULTIPLIER", 3.0)

DEFAULT_SL_POINTS_XAU = _getenv_int("DEFAULT_SL_POINTS_XAU", DEFAULT_SL_POINTS)
DEFAULT_TP_POINTS_XAU = _getenv_int("DEFAULT_TP_POINTS_XAU", DEFAULT_TP_POINTS)
DEFAULT_SL_POINTS_BTC = _getenv_int("DEFAULT_SL_POINTS_BTC", 50000)
DEFAULT_TP_POINTS_BTC = _getenv_int("DEFAULT_TP_POINTS_BTC", 100000)


# --- CONSENSUS SETTINGS ---
DRY_RUN = _getenv_bool("DRY_RUN", False)
TRADING_PAUSED = _getenv_bool("TRADING_PAUSED", False)

ERA_PRESETS = {
    "v1": {
        "label": "V1 — era profit 100% (legacy)",
        "DRY_RUN": True,
        "RISK_PERCENT_XAU": 0.5,
        "RISK_PERCENT_BTC": 1.0,
        "CONFIDENCE_CONSENSUS_THRESHOLD_XAU": 1.0,
        "CONFIDENCE_CONSENSUS_THRESHOLD_BTC": 1.2
    },
    "v2": {
        "label": "V2 — legacy-2 (= v1 + state)",
        "DRY_RUN": True,
        "RISK_PERCENT_XAU": 0.5,
        "RISK_PERCENT_BTC": 1.0,
        "CONFIDENCE_CONSENSUS_THRESHOLD_XAU": 1.0,
        "CONFIDENCE_CONSENSUS_THRESHOLD_BTC": 1.2
    },
    "v3": {
        "label": "V3 — modern (Claude + quant, sekarang)",
        "DRY_RUN": False,
        "RISK_PERCENT_XAU": 0.5,
        "RISK_PERCENT_BTC": 1.5,
        "CONFIDENCE_CONSENSUS_THRESHOLD_XAU": 1.0,
        "CONFIDENCE_CONSENSUS_THRESHOLD_BTC": 1.2
    }
}

CONSENSUS_THRESHOLD = _getenv_int("CONSENSUS_THRESHOLD", 2)
DYNAMIC_CONFIG_ENABLED = _getenv_bool("DYNAMIC_CONFIG_ENABLED", False)

CONFIDENCE_CONSENSUS_THRESHOLD_XAU = _getenv_float("CONFIDENCE_CONSENSUS_THRESHOLD_XAU", 1.0)
CONFIDENCE_CONSENSUS_THRESHOLD_BTC = _getenv_float("CONFIDENCE_CONSENSUS_THRESHOLD_BTC", 1.2)
MIN_CONSENSUS_MODELS = _getenv_int("MIN_CONSENSUS_MODELS", 2)

# --- TIME-BASED AI MODE SCHEDULE (WIB) ---
# Format: (start_hour, start_minute, end_hour, end_minute, mode)
# Mode values: "single" | "dual" | "triple"
AI_MODE_POLICY = os.getenv("AI_MODE_POLICY", "schedule").strip().lower()  # schedule | fixed
AI_FIXED_MODE = os.getenv("AI_FIXED_MODE", "triple").strip().lower()
AI_MODE_SCHEDULE = [
    (0, 1, 8, 59, "single"),
    (9, 0, 13, 0, "dual"),
    (13, 1, 18, 59, "single"),
    (19, 0, 23, 0, "triple"),
]

FORCE_ACTIVE_ENTRY = _getenv_bool("FORCE_ACTIVE_ENTRY", False)
QUANT_ANALYSIS_ENABLED = _getenv_bool("QUANT_ANALYSIS_ENABLED", False)
MONTE_CARLO_ENABLED = _getenv_bool("MONTE_CARLO_ENABLED", False)
FORECAST_ENABLED = _getenv_bool("FORECAST_ENABLED", False)
MEMORY_CONTEXT_ENABLED = _getenv_bool("MEMORY_CONTEXT_ENABLED", False)  # OFF: lesson learned & recent outcomes TIDAK di-inject ke prompt LLM (lesson M5-scalp toxic, bikin HOLD terus). Kode tetap ada, tinggal set True kalau mau aktif lagi.

# --- TRAILING STOP ---
TRAILING_STOP_ENABLED = _getenv_bool("TRAILING_STOP_ENABLED", True)
TRAILING_ACTIVATION_POINTS = _getenv_int("TRAILING_ACTIVATION_POINTS", 200)
TRAILING_DISTANCE_POINTS = _getenv_int("TRAILING_DISTANCE_POINTS", 150)

TRAILING_ACTIVATION_POINTS_XAU = _getenv_int("TRAILING_ACTIVATION_POINTS_XAU", TRAILING_ACTIVATION_POINTS)
TRAILING_DISTANCE_POINTS_XAU = _getenv_int("TRAILING_DISTANCE_POINTS_XAU", TRAILING_DISTANCE_POINTS)
TRAILING_ACTIVATION_POINTS_BTC = _getenv_int("TRAILING_ACTIVATION_POINTS_BTC", 17000)
TRAILING_DISTANCE_POINTS_BTC = _getenv_int("TRAILING_DISTANCE_POINTS_BTC", 12500)

TRAILING_ACTIVATION_ATR_MULT_BTC = _getenv_float("TRAILING_ACTIVATION_ATR_MULT_BTC", 1.0)
TRAILING_DISTANCE_ATR_MULT_BTC = _getenv_float("TRAILING_DISTANCE_ATR_MULT_BTC", 0.5)
TRAILING_ACTIVATION_ATR_MULT_XAU = _getenv_float("TRAILING_ACTIVATION_ATR_MULT_XAU", 1.0)
TRAILING_DISTANCE_ATR_MULT_XAU = _getenv_float("TRAILING_DISTANCE_ATR_MULT_XAU", 0.5)
TRAILING_ACTIVATION_MAX_POINTS_BTC = _getenv_int("TRAILING_ACTIVATION_MAX_POINTS_BTC", 40000)
TRAILING_ACTIVATION_MAX_POINTS_XAU = _getenv_int("TRAILING_ACTIVATION_MAX_POINTS_XAU", 500)

# --- BREAK-EVEN ---
BREAK_EVEN_ENABLED = _getenv_bool("BREAK_EVEN_ENABLED", True)
BREAK_EVEN_TRIGGER_POINTS = _getenv_int("BREAK_EVEN_TRIGGER_POINTS", 300)
BREAK_EVEN_PADDING_POINTS = _getenv_int("BREAK_EVEN_PADDING_POINTS", 10)

BREAK_EVEN_TRIGGER_POINTS_XAU = _getenv_int("BREAK_EVEN_TRIGGER_POINTS_XAU", BREAK_EVEN_TRIGGER_POINTS)
BREAK_EVEN_PADDING_POINTS_XAU = _getenv_int("BREAK_EVEN_PADDING_POINTS_XAU", BREAK_EVEN_PADDING_POINTS)
BREAK_EVEN_TRIGGER_POINTS_BTC = _getenv_int("BREAK_EVEN_TRIGGER_POINTS_BTC", 33500)
BREAK_EVEN_PADDING_POINTS_BTC = _getenv_int("BREAK_EVEN_PADDING_POINTS_BTC", 1000)

# --- PARTIAL CLOSE ---
PARTIAL_CLOSE_ENABLED = _getenv_bool("PARTIAL_CLOSE_ENABLED", True)
PARTIAL_CLOSE_PERCENT = _getenv_float("PARTIAL_CLOSE_PERCENT", 50.0)
PARTIAL_CLOSE_TP1_POINTS = _getenv_int("PARTIAL_CLOSE_TP1_POINTS", 400)

PARTIAL_CLOSE_TP1_POINTS_XAU = _getenv_int("PARTIAL_CLOSE_TP1_POINTS_XAU", PARTIAL_CLOSE_TP1_POINTS)
PARTIAL_CLOSE_TP1_POINTS_BTC = _getenv_int("PARTIAL_CLOSE_TP1_POINTS_BTC", 44500)

# --- DAILY RISK LIMITS ---
MAX_DAILY_LOSS_USD = _getenv_float("MAX_DAILY_LOSS_USD", 50.0)
MAX_CONSECUTIVE_LOSSES = _getenv_int("MAX_CONSECUTIVE_LOSSES", 5)
PAUSE_AFTER_LOSSES_MINUTES = _getenv_int("PAUSE_AFTER_LOSSES_MINUTES", 15)
MAX_OPEN_POSITIONS = _getenv_int("MAX_OPEN_POSITIONS", 6)
BREAK_EVEN_TOLERANCE_USD = _getenv_float("BREAK_EVEN_TOLERANCE_USD", 0.04)
MAX_OPEN_POSITIONS_RECOVERY = _getenv_int("MAX_OPEN_POSITIONS_RECOVERY", 4)

# --- RECOVERY MODE ---
RECOVERY_MODE_ENABLED = _getenv_bool("RECOVERY_MODE_ENABLED", True)
RECOVERY_LOT_MULTIPLIER = _getenv_float("RECOVERY_LOT_MULTIPLIER", 0.5)
RECOVERY_EXIT_PROFIT_USD = _getenv_float("RECOVERY_EXIT_PROFIT_USD", 0.10)
TRADE_COOLDOWN_SECONDS = _getenv_int("TRADE_COOLDOWN_SECONDS", 0)

# --- SPREAD FILTER ---
MAX_SPREAD_POINTS = _getenv_int("MAX_SPREAD_POINTS", 50)
MAX_SPREAD_POINTS_XAU = _getenv_int("MAX_SPREAD_POINTS_XAU", MAX_SPREAD_POINTS)
MAX_SPREAD_POINTS_BTC = _getenv_int("MAX_SPREAD_POINTS_BTC", 2400)

# --- SESSION FILTER ---
SESSION_FILTER_ENABLED = _getenv_bool("SESSION_FILTER_ENABLED", True)
ALLOWED_SESSIONS_WIB = [
    {"name": "Asia Dawn",      "start": (5, 0),  "end": (7, 0),   "lot_multiplier": 0.7},
    {"name": "Tokyo",          "start": (7, 0),  "end": (16, 0),  "lot_multiplier": 0.7},
    {"name": "London",         "start": (15, 0), "end": (23, 59), "lot_multiplier": 1.0},
    {"name": "London-NY (🔥)", "start": (20, 0), "end": (23, 59), "lot_multiplier": 1.2},
    {"name": "NY",             "start": (20, 0), "end": (5, 0),   "lot_multiplier": 1.0},
]

# Danger zones DINONAKTIFKAN (permintaan user 11-08: full trade 24 jam,
# tengah malam-pagi juga trade). Kalau mau aktifkan lagi, isi list-nya:
#   {"name": "Rollover",  "start": (4, 0), "end": (6, 0), "reason": "Spread melebar saat rollover"},
#   {"name": "Dead Zone", "start": (0, 0), "end": (4, 0), "reason": "Likuiditas rendah"},
DANGER_ZONES_WIB = []

# --- WEEKEND PROTECTION ---
WEEKEND_CLOSE_ENABLED = _getenv_bool("WEEKEND_CLOSE_ENABLED", True)
WEEKEND_CLOSE_PROFIT_MIN_USD = _getenv_float("WEEKEND_CLOSE_PROFIT_MIN_USD", 1.0)
WEEKEND_CLOSE_HOURS_BEFORE = _getenv_float("WEEKEND_CLOSE_HOURS_BEFORE", 2.0)
WEEKEND_MAX_LOSS_TO_HOLD_USD = _getenv_float("WEEKEND_MAX_LOSS_TO_HOLD_USD", 20.0)
WEEKEND_TRADING_ENABLED = _getenv_bool("WEEKEND_TRADING_ENABLED", False)

POSITION_MANAGER_MAX_TICK_AGE_SECONDS = _getenv_int("POSITION_MANAGER_MAX_TICK_AGE_SECONDS", 300)

# --- TELEGRAM ALERTS ---
TELEGRAM_ENABLED = _getenv_bool("TELEGRAM_ENABLED", False)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")

# --- MT5 CONNECTION ---
MT5_ACCOUNT_MODE = os.getenv("MT5_ACCOUNT_MODE", "live").lower()  # "live" | "demo"
MT5_LOGIN = ""
MT5_PASSWORD = ""
MT5_SERVER = ""
MAGIC_NUMBER = _getenv_int("MAGIC_NUMBER", 20260625)

def refresh_mt5_credentials():
    """Reloads MT5 login credentials from current MT5_ACCOUNT_MODE."""
    global MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
    if MT5_ACCOUNT_MODE == "demo":
        MT5_LOGIN = os.getenv("MT5_DEMO_LOGIN", "")
        MT5_PASSWORD = os.getenv("MT5_DEMO_PASSWORD", "")
        MT5_SERVER = os.getenv("MT5_DEMO_SERVER", "")
    else:
        MT5_LOGIN = os.getenv("MT5_LIVE_LOGIN", os.getenv("MT5_LOGIN", ""))
        MT5_PASSWORD = os.getenv("MT5_LIVE_PASSWORD", os.getenv("MT5_PASSWORD", ""))
        MT5_SERVER = os.getenv("MT5_LIVE_SERVER", os.getenv("MT5_SERVER", ""))
    
    if MT5_LOGIN:
        try:
            MT5_LOGIN = int(MT5_LOGIN)
        except ValueError:
            pass

# Initialize credentials
refresh_mt5_credentials()

# --- MULTI-TIMEFRAME & FUNDAMENTAL SETTINGS ---
MTF_ANALYSIS_ENABLED = _getenv_bool("MTF_ANALYSIS_ENABLED", True)
HIGHER_TIMEFRAMES = {
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30
}
HIGHER_TIMEFRAMES_CRYPTO = {
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4
}

def get_higher_timeframes(symbol):
    """Returns the MTF context timeframes for a symbol (crypto -> H1/H4)."""
    return HIGHER_TIMEFRAMES_CRYPTO if is_crypto(symbol) else HIGHER_TIMEFRAMES

FUNDAMENTAL_ANALYSIS_ENABLED = _getenv_bool("FUNDAMENTAL_ANALYSIS_ENABLED", False)
PRIMARY_ANALYSIS_MODEL = os.getenv("PRIMARY_ANALYSIS_MODEL", "gpt-5.4-mini")

# --- LOGGING SETTINGS ---
LOG_FILE = os.path.join(DATA_DIR, "trading_bot.log")


# ============================================================================
#  SYMBOL ROTATION HELPERS (weekday XAUUSD, weekend BTCUSD)
# ============================================================================
def is_crypto(symbol):
    """True if the given symbol is a crypto pair (weekend trading)."""
    return symbol in CRYPTO_SYMBOLS


def get_rotation_pool(now=None):
    """
    Returns the ordered list of symbols currently in the rotation pool:
    - TRADING_MODE == "xau" (default): [WEEKDAY_SYMBOL] (weekend -> WEEKEND if ENABLE_BTC_ROTATION)
    - TRADING_MODE == "xau_pairs": [WEEKDAY_SYMBOL] + FX_PAIR_SYMBOLS, truncated to MAX_ROTATION_SYMBOLS.
      Weekend: FX pairs market closed -> falls back to XAU (or BTC if ENABLE_BTC_ROTATION).
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
    now = now or datetime.now(WIB)
    is_weekend = (now.weekday() == 4 and now.hour >= 22) or now.weekday() in (5, 6)
    if is_weekend:
        # FX pairs market closed on weekend -> XAU or BTC only
        if getattr(sys.modules[__name__], "ENABLE_BTC_ROTATION", False):
            return [WEEKEND_SYMBOL]
        return [WEEKDAY_SYMBOL]
    if TRADING_MODE == "xau_pairs":
        pool = [WEEKDAY_SYMBOL] + [s for s in FX_PAIR_SYMBOLS if s != WEEKDAY_SYMBOL]
        return pool[:MAX_ROTATION_SYMBOLS]
    return [WEEKDAY_SYMBOL]


_rotation_index = {"i": 0}


def get_active_symbol(now=None):
    """Returns the symbol that should be traded right now (respects rotation index)."""
    pool = get_rotation_pool(now)
    return pool[_rotation_index["i"] % len(pool)]


_last_symbol = {"value": SYMBOL}


def refresh_active_symbol(now=None, advance=False):
    """
    Updates config.SYMBOL to the symbol that should be active now.
    Returns (new_symbol, changed: bool) — changed=True when the symbol just rotated.
    advance=True -> move rotation index forward (called once per new candle).
    """
    global SYMBOL
    if advance:
        pool = get_rotation_pool(now)
        _rotation_index["i"] = (_rotation_index["i"] + 1) % len(pool)
    target = get_active_symbol(now)
    # Auto-correct suffix ke nama broker valid (XAUUSD-ECN -> XAUUSD-ECNc di LIVE).
    # Lazy import untuk hindari circular (mt5_connector import config).
    try:
        from src.core.mt5_connector import get_valid_trade_symbol
        target = get_valid_trade_symbol(target)
    except Exception:
        pass
    changed = (target != _last_symbol["value"])
    SYMBOL = target
    _last_symbol["value"] = target
    return target, changed


def lot_size_for(symbol):
    return LOT_SIZE_BTC if is_crypto(symbol) else LOT_SIZE_XAU


def get_timeframe(symbol):
    """Returns the trading timeframe for a symbol.
    BTC/crypto trades on M30 (30-minute intraday) to avoid overnight swap charges.
    XAU keeps M5 scalping.
    """
    return mt5.TIMEFRAME_M30 if is_crypto(symbol) else TIMEFRAME


def default_sl_points_for(symbol):
    return DEFAULT_SL_POINTS_BTC if is_crypto(symbol) else DEFAULT_SL_POINTS_XAU


def default_tp_points_for(symbol):
    return DEFAULT_TP_POINTS_BTC if is_crypto(symbol) else DEFAULT_TP_POINTS_XAU


def max_spread_points_for(symbol):
    return MAX_SPREAD_POINTS_BTC if is_crypto(symbol) else MAX_SPREAD_POINTS_XAU


def confidence_threshold_for(symbol):
    """Weighted-confidence consensus threshold per symbol.
    BTC (M30, moderate entries) needs higher conviction than XAU (M5, frequent).
    """
    return CONFIDENCE_CONSENSUS_THRESHOLD_BTC if is_crypto(symbol) else CONFIDENCE_CONSENSUS_THRESHOLD_XAU


def get_ai_mode(now=None):
    """Return active AI mode for WIB time.
    - schedule policy: use AI_MODE_SCHEDULE
    - fixed policy: use AI_FIXED_MODE
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    WIB = ZoneInfo("Asia/Jakarta")
    now = now or datetime.now(WIB)

    policy = getattr(sys.modules[__name__], "AI_MODE_POLICY", "schedule")
    if policy == "fixed":
        fixed = getattr(sys.modules[__name__], "AI_FIXED_MODE", "triple")
        return fixed if fixed in ("single", "dual", "triple") else "triple"

    total_minutes = now.hour * 60 + now.minute
    for sh, sm, eh, em, mode in AI_MODE_SCHEDULE:
        start = sh * 60 + sm
        end = eh * 60 + em
        if start <= total_minutes <= end:
            return mode
    return "single"


def claude_slot_label():
    """Display label for the 'Claude slot' model. Shows DeepSeek when the
    configured model is deepseek/..., otherwise Claude. Single source of truth."""
    return "DeepSeek" if CLAUDE_MODEL.startswith("deepseek/") else "Claude"


def active_ai_model_names(now=None):
    """Return the model slots to query for the active AI mode."""
    mode = get_ai_mode(now)
    slot3 = claude_slot_label()
    if mode == "single":
        return ["OpenAI"]
    if mode == "dual":
        return ["OpenAI", slot3]
    return ["OpenAI", "Gemini", slot3]


def risk_percent_for(symbol):
    """Risk per trade (% of balance) for risk-based lot sizing.
    BTC (M30 swing, few concurrent positions): 1.5%.
    XAU (M5 scalping, up to 6 concurrent): 0.5% — aggregate ~3% max.
    """
    return RISK_PERCENT_BTC if is_crypto(symbol) else RISK_PERCENT_XAU
