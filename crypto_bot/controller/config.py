"""
config.py — Configuration module for Unified Crypto Controller.
Loads environment variables for Telegram Bot, Risk Pool, and Event Bridge.
"""

import os
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
LOG_FILE = LOG_DIR / "crypto_controller.log"
STATE_FILE = REPO_ROOT / "data" / "crypto_risk_state.json"

# --- Controller HTTP Server ---
CONTROLLER_HOST: str = os.getenv("CRYPTO_CONTROLLER_HOST", "0.0.0.0")
CONTROLLER_PORT: int = int(os.getenv("CRYPTO_CONTROLLER_PORT", "8080"))

# --- Risk Pool Thresholds ---
CRYPTO_DAILY_LOSS_PERCENT: float = float(os.getenv("CRYPTO_DAILY_LOSS_PERCENT", "5.0"))

# --- Telegram Bot Credentials ---
CRYPTO_TELEGRAM_TOKEN: str = os.getenv("CRYPTO_TELEGRAM_TOKEN", "")
CRYPTO_TELEGRAM_CHAT_ID: str = os.getenv("CRYPTO_TELEGRAM_CHAT_ID", "")

# --- Internal Worker Endpoints ---
BTC_WORKER_URL: str = os.getenv("BTC_WORKER_URL", "http://127.0.0.1:8001")
SOL_WORKER_URL: str = os.getenv("SOL_WORKER_URL", "http://127.0.0.1:8002")
