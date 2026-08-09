"""
Konfigurasi Bot Binance Spot (terpisah dari bot MT5).

AMAN default: TESTNET=True + DRY_RUN=True.
Untuk live: TESTNET=False + DRY_RUN=False — jangan ubah tanpa diskusi.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# BINANCE API
# ---------------------------------------------------------------------------
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")

# Testnet = uang virtual (testnet.binance.vision). False = live (uang asli).
TESTNET = os.getenv("TESTNET", "true").lower() == "true"

# REST base URL — path endpoint sudah include /api/v3/* (jangan tambah /api lagi)
REST_BASE = ("https://testnet.binance.vision" if TESTNET
             else "https://api.binance.com")

# DRY_RUN = True → sinyal dihitung, order TIDAK dikirim. False = order beneran.
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# ---------------------------------------------------------------------------
# TRADING PARAMS
# ---------------------------------------------------------------------------
SYMBOL = os.getenv("BINANCE_SYMBOL", "BTCUSDT")
TIMEFRAME = "30m"            # M30 (kline interval Binance)
CANDLE_COUNT = 50            # candle untuk analisis

RISK_PERCENT = 1.5           # risk per trade dari equity USDT
MAX_DAILY_LOSS_USD = 3.0     # ~25% dari $12 — ketat (naikkan kalau modal naik)
MAX_OPEN_POSITIONS = 2
TRADE_COOLDOWN_SECONDS = 300
MIN_NOTIONAL_USD = 5.0       # validasi order min (Binance tolak < min notional)
MAX_SPREAD_PCT = 0.05        # max spread (% dari harga) — mis. 0.05% = $32 di BTC $65k

# ---------------------------------------------------------------------------
# CONSENSUS 2 PROPOSER + 1 APPROVER
# ---------------------------------------------------------------------------
CONFIDENCE_THRESHOLD = 1.2   # skor gabungan 2 proposer (2 x 60%)
CLAUDE_APPROVER_ENABLED = True

# ---------------------------------------------------------------------------
# SL/TP (dalam persen harga — bot menghitung harga SL/TP dari entry)
# ---------------------------------------------------------------------------
DEFAULT_SL_PCT = 1.0         # SL 1% dari entry
DEFAULT_TP_PCT = 2.0         # TP 2% dari entry (R:R 1:2)
SL_ATR_MULTIPLIER = 1.5      # SL = 1.5x ATR (kalau ATR tersedia)
TP_ATR_MULTIPLIER = 3.0      # TP = 3x ATR

# ---------------------------------------------------------------------------
# LLM MODELS (reuse dari bot MT5)
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

OPENAI_MODEL = "gpt-5.4-mini"
GEMINI_MODEL = "gemini-3.5-flash-lite"
CLAUDE_MODEL = "claude-sonnet-4-6"

LLM_TIMEOUT_SECONDS = 24.0

# ---------------------------------------------------------------------------
# STATE & LOG
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_FILE = os.path.join(BASE_DIR, "binance_bot.log")

# ---------------------------------------------------------------------------
# TELEGRAM (fase 2 — default off)
# ---------------------------------------------------------------------------
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
