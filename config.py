import os
import sys
if sys.platform == 'win32':
    import MetaTrader5 as mt5
else:
    try:
        import importlib
        mt5 = importlib.import_module("mt5linux").MetaTrader5
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
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# --- API BASE URLS ---
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")

# --- MODEL NAMES & FALLBACKS ---
# Claude Model & Fallback (Anthropic)
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_FALLBACK_MODEL = "claude-haiku-4-5-20251001"


# Gemini Model & Fallback
GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_FALLBACK_MODEL = "gemini-3.5-flash-lite"

# OpenAI Model & Fallback (Tetap)
OPENAI_MODEL = "gpt-5.4-mini"
OPENAI_FALLBACK_MODEL = "gpt-5.4-mini"

# Maximum time (seconds) per model before triggering fallback
LLM_TIMEOUT_SECONDS = 24.0



# --- TRADING PARAMETERS ---
# Symbol rotation: XAUUSD on weekdays, BTCUSD on weekends (crypto 24/7 while FX closed)
WEEKDAY_SYMBOL = "XAUUSD-ECNc"
WEEKEND_SYMBOL = "BTCUSD.c"
CRYPTO_SYMBOLS = {"BTCUSD.c", "BTCUSD", "BTCUSD.ecn", "BTCUSD.m", "BTCUSD.MT5", "BTCUSD.pro"}
SYMBOL = WEEKDAY_SYMBOL            # active symbol; updated at runtime by refresh_active_symbol()

# Timeframe for Scalping: 5 Minutes (XAU)
TIMEFRAME = mt5.TIMEFRAME_M5
# BTC/crypto trades on M30 (spread ~$17 too large for M5 scalping, but fine vs M30 ATR)
H1_TIMEFRAME = mt5.TIMEFRAME_H1

# Default trade size (0.01 is micro-lot)
LOT_SIZE = 0.01
LOT_SIZE_XAU = LOT_SIZE
LOT_SIZE_BTC = 0.01

# Risk-based lot sizing: lot is computed from account balance so each trade
# risks this % of equity. Per-symbol because BTC (M30 swing, few positions)
# can take more risk per trade than XAU (M5 scalping, up to 6 concurrent
# positions — 6 x 0.5% = 3% aggregate is the ceiling we accept).
RISK_PERCENT_BTC = 1.5   # ~$16/trade at $1065 balance -> lot ~0.05
RISK_PERCENT_XAU = 0.5   # ~$5.3/trade -> lot ~0.02 (x6 positions = ~3% max)

# Deviation (slippage tolerance in points)
DEVIATION = 20

# Risk Management: SL/TP settings (calculated dynamically in Python based on ATR)
DEFAULT_SL_POINTS = 300
DEFAULT_TP_POINTS = 600
SL_ATR_MULTIPLIER = 1.5   # Stop Loss = 1.5x ATR
TP_ATR_MULTIPLIER = 3.0   # Take Profit = 3.0x ATR (Risk-to-Reward 1:2)

# Per-symbol defaults (fallback when LLM gives no SL/TP)
DEFAULT_SL_POINTS_XAU = DEFAULT_SL_POINTS
DEFAULT_TP_POINTS_XAU = DEFAULT_TP_POINTS
# BTC: scaled for ~$10/trade target on 0.01 lot (~$0.0001/pt).
# SL 50000 pts = $500 move = ~$5 risk (0.5% of $1000); TP 100000 = $10 target.
DEFAULT_SL_POINTS_BTC = 50000
DEFAULT_TP_POINTS_BTC = 100000


# --- CONSENSUS SETTINGS ---
# Mode: DRY_RUN = True means signals are generated and logged, but no orders are sent to MT5.
# Set to False to enable live trading on MT5.
DRY_RUN = False




# Minimum number of models that must agree (e.g., 2 out of 3)
CONSENSUS_THRESHOLD = 2

# Weighted-confidence consensus: a BUY/SELL signal wins when the SUM of
# confidence from models voting that direction meets the per-symbol threshold
# AND at least 2 models voted that direction (prevents one strong model
# dragging along a coincidental weak vote). Below it -> HOLD.
# XAU (M5 scalping, 12 cycles/hour): 1.0 = two models at ~50% — fluid.
# BTC (M30 swing, 1 cycle/30min): 1.2 = two models at ~60% — precise.
CONFIDENCE_CONSENSUS_THRESHOLD_XAU = 1.0
CONFIDENCE_CONSENSUS_THRESHOLD_BTC = 1.2
MIN_CONSENSUS_MODELS = 2  # minimum models voting the same direction

# Multi-Agent Debate Round 2 (extra LLM calls when Round 1 lacks consensus)
# DISABLED: log analysis showed it never produced a trade (always reinforced HOLD)
# and just burned tokens/latency. Round 1 consensus alone decides.
DEBATE_ENABLED = False

# ============================================================================
#  FEATURE TOGGLES (untuk A/B test & balik ke titik stable era lama)
# ============================================================================
# Quant analysis: Hurst Exponent + fat-tail kurtosis + Monte Carlo probability.
# Ditambahkan di era modern (commit 259708d). Legacy (profit 100% dulu) TANPA ini.
QUANT_ANALYSIS_ENABLED = True

# Multi-Horizon Forecast Engine (T+15m/T+60m XAU, T+4h/T+D1 BTC) — informational.
# Sudah ada sejak era legacy (commit 949ce14), tapi bisa di-off untuk A/B test.
FORECAST_ENABLED = True

# Memory/state context yang di-inject ke prompt LLM. Kalau OFF, prompt LLM
# murni dari data pasar (candle + indikator) — TANPA bias dari trade sebelumnya:
#   - lessons post-mortem (memory_lessons.json)
#   - decision memory 6 keputusan terakhir (decision_memory.json)
#   - forecast context (forecast_cache.json)
# Ini bikin LLM lebih independen (tidak anchoring ke keputusan/lesson lama),
# tapi kehilangan pembelajaran dari trade sebelumnya.
MEMORY_CONTEXT_ENABLED = True

# Preset era — untuk balik cepat ke konfigurasi yang mirip era tertentu.
# Dipakai oleh interactive_setup (menu sebelum run) & --era CLI.
#   "v1": era profit 100% (legacy) — DeepSeek, consensus 2/3, lot statis, NO quant
#   "v2": = v1 + state/test telegram (fungsional sama dengan v1)
#   "v3": era sekarang (modern) — Claude, weighted consensus, risk-based lot, quant ON
# CATATAN: preset hanya mengubah flag yang masih ada di kode (quant/forecast/
# debate/threshold). Model (DeepSeek→Claude) & mekanisme consensus (2/3→weighted)
# sudah tertanam di kode dan tidak bisa di-revert via config.
ERA_PRESETS = {
    "v1": {
        "label": "V1 — era profit 100% (legacy)",
        "QUANT_ANALYSIS_ENABLED": False,
        "FORECAST_ENABLED": True,
        "DEBATE_ENABLED": True,
        "CONFIDENCE_CONSENSUS_THRESHOLD_XAU": 1.0,
        "CONFIDENCE_CONSENSUS_THRESHOLD_BTC": 1.2,
    },
    "v2": {
        "label": "V2 — legacy-2 (= v1 + state)",
        "QUANT_ANALYSIS_ENABLED": False,
        "FORECAST_ENABLED": True,
        "DEBATE_ENABLED": True,
        "CONFIDENCE_CONSENSUS_THRESHOLD_XAU": 1.0,
        "CONFIDENCE_CONSENSUS_THRESHOLD_BTC": 1.2,
    },
    "v3": {
        "label": "V3 — modern (Claude + quant, sekarang)",
        "QUANT_ANALYSIS_ENABLED": True,
        "FORECAST_ENABLED": True,
        "DEBATE_ENABLED": False,
        "CONFIDENCE_CONSENSUS_THRESHOLD_XAU": 1.0,
        "CONFIDENCE_CONSENSUS_THRESHOLD_BTC": 1.2,
    },
}

# ============================================================================
#                     PROTECTION & EXECUTION LAYER
#           (Inspired by XAU-60 execution engine & xaubot-ai risk system)
# ============================================================================

# --- TRAILING STOP (from XAU-60 trade_executor.py) ---
# Automatically trails stop loss behind price to lock in profits
TRAILING_STOP_ENABLED = True
TRAILING_ACTIVATION_POINTS = 200   # Activate trailing after 200 pts profit (~$2.00 on Gold)
TRAILING_DISTANCE_POINTS = 150     # Trail SL 150 pts behind current price

# Per-symbol trailing thresholds (Static fallback)
TRAILING_ACTIVATION_POINTS_XAU = TRAILING_ACTIVATION_POINTS
TRAILING_DISTANCE_POINTS_XAU = TRAILING_DISTANCE_POINTS
TRAILING_ACTIVATION_POINTS_BTC = 17000
TRAILING_DISTANCE_POINTS_BTC = 12500

# Dynamic ATR Trailing Multipliers (Computed in real-time from live ATR14)
# BTC: 2.0x ATR M30 activation, 1.5x ATR M30 distance
# XAU: 2.0x ATR M5 activation (~$2.00 @ $1.00 ATR), 1.5x ATR M5 distance (~$1.50 @ $1.00 ATR)
TRAILING_ACTIVATION_ATR_MULT_BTC = 2.0
TRAILING_DISTANCE_ATR_MULT_BTC = 1.5
TRAILING_ACTIVATION_ATR_MULT_XAU = 2.0
TRAILING_DISTANCE_ATR_MULT_XAU = 1.5

# --- BREAK-EVEN (from XAU-60 trade_executor.py) ---
# Moves stop loss to entry price once trade reaches profit threshold
BREAK_EVEN_ENABLED = True
BREAK_EVEN_TRIGGER_POINTS = 300    # Move SL to entry after 300 pts profit (~$3.00)
BREAK_EVEN_PADDING_POINTS = 10     # Pad SL 10 pts above entry for safety

# Per-symbol break-even thresholds
BREAK_EVEN_TRIGGER_POINTS_XAU = BREAK_EVEN_TRIGGER_POINTS
BREAK_EVEN_PADDING_POINTS_XAU = BREAK_EVEN_PADDING_POINTS
# BTC: BE at 33500 pts profit (100% of M30 SL); padding 1000 pts ($10.00).
BREAK_EVEN_TRIGGER_POINTS_BTC = 33500
BREAK_EVEN_PADDING_POINTS_BTC = 1000

# --- PARTIAL CLOSE (from XAU-60 trade_executor.py) ---
# Close portion of position at first target, let the rest ride with trailing stop
PARTIAL_CLOSE_ENABLED = True
PARTIAL_CLOSE_PERCENT = 50         # Close 50% of position at TP1
PARTIAL_CLOSE_TP1_POINTS = 400     # TP1 trigger: 400 pts profit (~$4.00)

# Per-symbol partial-close thresholds
PARTIAL_CLOSE_TP1_POINTS_XAU = PARTIAL_CLOSE_TP1_POINTS
# BTC: TP1 at 44500 pts profit (133% of M30 SL).
PARTIAL_CLOSE_TP1_POINTS_BTC = 44500

# --- DAILY RISK LIMITS (from xaubot-ai smart_risk_manager.py) ---
MAX_DAILY_LOSS_USD = 50.0          # Halt all trading after losing $50 today
MAX_CONSECUTIVE_LOSSES = 3         # Pause trading after 3 consecutive losses
PAUSE_AFTER_LOSSES_MINUTES = 30    # Pause duration after consecutive losses
MAX_OPEN_POSITIONS = 6             # Max simultaneous positions (fits 3x layering cycles of 2 positions)

# --- BREAK-EVEN PROFIT TOLERANCE ---
# A closed trade with |profit| <= BREAK_EVEN_TOLERANCE_USD is treated as
# break-even: it does NOT increment the loss streak, but also does NOT reset it
# Defensive live setting: trades with |profit| <= $0.04 are treated as BEP
BREAK_EVEN_TOLERANCE_USD = 0.04

# --- RECOVERY MODE POSITION LIMIT ---
# During recovery mode, cap new open positions lower than normal
MAX_OPEN_POSITIONS_RECOVERY = 4    # Max simultaneous positions while in recovery mode



# --- RECOVERY MODE (from xaubot-ai smart_risk_manager.py) ---
# After hitting daily loss or consecutive losses, reduce lot size
RECOVERY_MODE_ENABLED = True
RECOVERY_LOT_MULTIPLIER = 0.5     # Use 50% of normal lot size during recovery

# A win must clear this much profit before recovery mode is deactivated,
# so a tiny $0.01 win cannot instantly reset a 3+ loss streak.
RECOVERY_EXIT_PROFIT_USD = 0.10

# --- COOLDOWN (from xaubot-ai smart_risk_manager.py) ---
# Set to 0 because main loop already runs every 5 minutes on candle closures
TRADE_COOLDOWN_SECONDS = 0


# --- SPREAD FILTER (from both repos) ---
# Skip trade entry if spread is too wide (common during news/low liquidity)
MAX_SPREAD_POINTS = 50             # Max allowed spread in points (50 pts = ~$0.50 on Gold)
MAX_SPREAD_POINTS_XAU = MAX_SPREAD_POINTS
MAX_SPREAD_POINTS_BTC = 2400        # BTCUSD spread in its own point scale; raise if too tight

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
# NOTE: crypto (BTCUSD) bypasses danger zones — trades 24/7 (handled in risk_engine)

# --- WEEKEND PROTECTION (from xaubot-ai position_manager.py) ---
# Close profitable positions before weekend to avoid gap risk
WEEKEND_CLOSE_ENABLED = True
WEEKEND_CLOSE_PROFIT_MIN_USD = 1.0   # Close if profit >= $1 and near weekend close
WEEKEND_CLOSE_HOURS_BEFORE = 2.0     # Start checking 2 hours before Friday close
WEEKEND_MAX_LOSS_TO_HOLD_USD = 20.0  # Max loss $ to hold over weekend (larger = cut loss)

# --- WEEKEND TRADING (crypto/BTC) ---
# False = TIDAK membuka posisi baru di weekend sama sekali (BTC spread lebar,
# M30 terlalu lambat — weekend mending istirahat). Posisi yang sudah open
# tetap di-manage (trailing/BE/close) — hanya entry baru yang diblokir.
# Berlaku untuk SEMUA symbol selama weekend (Jumat >= 22:00 WIB - Senin 00:00 WIB).
WEEKEND_TRADING_ENABLED = False

# --- POSITION MANAGER TICK FRESHNESS ---
# A position whose symbol has not produced a fresh tick within this many
# seconds is skipped (market closed — e.g. XAU over the weekend — or MT5
# disconnected). BTC ticks 24/7 so it keeps being managed across rotation.
POSITION_MANAGER_MAX_TICK_AGE_SECONDS = 300

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
# XAU (M5 scalper): analyze M30 and H1 context
HIGHER_TIMEFRAMES = {
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1
}
# BTC (M30 intraday trader): analyze H1 and H4 context
HIGHER_TIMEFRAMES_CRYPTO = {
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4
}

def get_higher_timeframes(symbol):
    """Returns the MTF context timeframes for a symbol (crypto -> H1/H4)."""
    return HIGHER_TIMEFRAMES_CRYPTO if is_crypto(symbol) else HIGHER_TIMEFRAMES

FUNDAMENTAL_ANALYSIS_ENABLED = False
# Model that performs background macro/fundamental analysis
# gpt-5.4-mini (OpenAI free tier, 2.5M tokens/day) as primary; Gemini fallback.
PRIMARY_ANALYSIS_MODEL = "gpt-5.4-mini"

# --- LOGGING SETTINGS ---
LOG_FILE = "trading_bot.log"


# ============================================================================
#  SYMBOL ROTATION HELPERS (weekday XAUUSD, weekend BTCUSD)
# ============================================================================
def is_crypto(symbol):
    """True if the given symbol is a crypto pair (weekend trading)."""
    return symbol in CRYPTO_SYMBOLS


def get_active_symbol(now=None):
    """
    Returns the symbol that should be traded right now:
    - Friday >= 22:00 WIB or Saturday/Sunday -> WEEKEND_SYMBOL (BTCUSD)
    - Otherwise -> WEEKDAY_SYMBOL (XAUUSD)
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    WIB = ZoneInfo("Asia/Jakarta")
    now = now or datetime.now(WIB)
    if (now.weekday() == 4 and now.hour >= 22) or now.weekday() in (5, 6):
        return WEEKEND_SYMBOL
    return WEEKDAY_SYMBOL


_last_symbol = {"value": SYMBOL}


def refresh_active_symbol(now=None):
    """
    Updates config.SYMBOL to the symbol that should be active now.
    Returns (new_symbol, changed: bool) — changed=True when the symbol just rotated.
    """
    global SYMBOL
    target = get_active_symbol(now)
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


def risk_percent_for(symbol):
    """Risk per trade (% of balance) for risk-based lot sizing.
    BTC (M30 swing, few concurrent positions): 1.5%.
    XAU (M5 scalping, up to 6 concurrent): 0.5% — aggregate ~3% max.
    """
    return RISK_PERCENT_BTC if is_crypto(symbol) else RISK_PERCENT_XAU

