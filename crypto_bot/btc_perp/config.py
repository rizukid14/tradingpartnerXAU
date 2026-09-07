"""
config.py — Configuration module for btc_perp (BTC Perpetual Whale Follower Engine).
Loads environment variables from .env with fallback defaults.
Follows GMT+7 (WIB) standard timezone.
"""

import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load .env from root repo or local directory
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_PATH = REPO_ROOT / ".env"
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

# --- Timezone & Logging ---
TIMEZONE_WIB = ZoneInfo("Asia/Jakarta")
LOG_DIR = REPO_ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "btc_perp.log"

# --- Exchange & Execution Mode ---
EXCHANGE_PRIMARY: str = os.getenv("EXCHANGE_PRIMARY", "hyperliquid").lower()
BTC_SYMBOL: str = os.getenv("BTC_SYMBOL", "BTC").upper()
BTC_DRY_RUN: bool = os.getenv("BTC_DRY_RUN", "True").strip().lower() in ("true", "1", "yes")

# --- Risk & Sizing Parameters ---
BTC_LEVERAGE: int = int(os.getenv("BTC_LEVERAGE", "2"))
BTC_RISK_PERCENT: float = float(os.getenv("BTC_RISK_PERCENT", "1.0"))
DAILY_LOSS_PERCENT: float = float(os.getenv("BTC_DAILY_LOSS_PERCENT", "5.0"))
MAX_OPEN_POSITIONS: int = int(os.getenv("BTC_MAX_OPEN_POSITIONS", "1"))

# --- Stop Loss & Take Profit Rules (BTC Perp) ---
BTC_SL_ATR_MULT: float = float(os.getenv("BTC_SL_ATR_MULT", "1.25"))
BTC_TP_ATR_MULT: float = float(os.getenv("BTC_TP_ATR_MULT", "2.5"))
BTC_MIN_SL_POINTS: float = float(os.getenv("BTC_MIN_SL_POINTS", "300.0"))   # Minimum $300 SL buffer
BTC_MAX_SL_POINTS: float = float(os.getenv("BTC_MAX_SL_POINTS", "2500.0")) # Maximum $2500 safety floor

# --- Trailing Stop & Stagnation ---
BEP_TRIGGER_RATIO: float = float(os.getenv("BTC_BEP_TRIGGER_RATIO", "0.50"))     # BEP at 50% TP
TRAILING_STAGE1_RATIO: float = float(os.getenv("BTC_TRAILING_STAGE1", "0.65"))  # 65% TP -> 0.75x ATR
TRAILING_STAGE2_RATIO: float = float(os.getenv("BTC_TRAILING_STAGE2", "0.90"))  # 90% TP -> 0.50x ATR
STAGNATION_TIMEOUT_HOURS: float = float(os.getenv("BTC_STAGNATION_HOURS", "4.0"))

# --- Hyperliquid Credentials ---
HL_PRIVATE_KEY: str = os.getenv("HL_PRIVATE_KEY", "")
HL_WALLET_ADDRESS: str = os.getenv("HL_WALLET_ADDRESS", "")
HL_TESTNET: bool = os.getenv("HL_TESTNET", "False").strip().lower() in ("true", "1", "yes")

# --- Binance Fallback Credentials ---
BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "True").strip().lower() in ("true", "1", "yes")

# --- AI Models / LLM Jury Credentials ---
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

# --- Unified Controller Webhook ---
CONTROLLER_WEBHOOK: str = os.getenv("CONTROLLER_WEBHOOK", "http://127.0.0.1:8080/event")

# --- Quant Radar & Scanner Intervals ---
SCANNER_INTERVAL_SEC: int = int(os.getenv("BTC_SCANNER_INTERVAL_SEC", "60"))
POSITION_MANAGER_INTERVAL_SEC: int = int(os.getenv("BTC_PM_INTERVAL_SEC", "5"))
