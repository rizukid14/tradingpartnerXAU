"""
config.py — Configuration module for sol_dex (Solana On-Chain Whale Copy-Trading Engine).
Loads environment variables with fallback defaults.
Follows GMT+7 (WIB) standard timezone.
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
LOG_FILE = LOG_DIR / "sol_dex.log"

# --- Solana Network & Execution Mode ---
SOL_RPC_URL: str = os.getenv("SOL_RPC_URL", "https://api.mainnet-beta.solana.com")
SOL_WS_URL: str = os.getenv("SOL_WS_URL", "wss://api.mainnet-beta.solana.com")
SOL_DRY_RUN: bool = os.getenv("SOL_DRY_RUN", "True").strip().lower() in ("true", "1", "yes")

# --- Wallet & API Keys ---
SOL_PRIVATE_KEY: str = os.getenv("SOL_PRIVATE_KEY", "")
SOL_WALLET_ADDRESS: str = os.getenv("SOL_WALLET_ADDRESS", "")
BIRDEYE_API_KEY: str = os.getenv("BIRDEYE_API_KEY", "")
JUPITER_QUOTE_API: str = os.getenv("JUPITER_QUOTE_API", "https://quote-api.jup.ag/v6")

# --- Risk & Position Sizing ---
SOL_RISK_PERCENT: float = float(os.getenv("SOL_RISK_PERCENT", "1.0"))
SOL_MAX_POSITION_USD: float = float(os.getenv("SOL_MAX_POSITION_USD", "10.0"))  # Stage 1 max $10 / swap
SOL_SLIPPAGE_BPS: int = int(os.getenv("SOL_SLIPPAGE_BPS", "100"))               # 1.0% slippage (100 bps)
MAX_OPEN_POSITIONS: int = int(os.getenv("SOL_MAX_OPEN_POSITIONS", "3"))

# --- Anti-Rugpull Safety Filter Thresholds (<500ms, 0 LLM) ---
MIN_TOKEN_AGE_HOURS: float = float(os.getenv("SOL_MIN_TOKEN_AGE_HOURS", "2.0"))
MAX_TOP10_HOLDER_PERCENT: float = float(os.getenv("SOL_MAX_TOP10_PERCENT", "20.0"))
MIN_LP_BURNED_PERCENT: float = float(os.getenv("SOL_MIN_LP_BURNED", "90.0"))
MAX_PRICE_IMPACT_PERCENT: float = float(os.getenv("SOL_MAX_PRICE_IMPACT", "3.0"))

# --- Whale Profiling & Discovery Thresholds ---
MIN_WHALE_PROFIT_FACTOR: float = float(os.getenv("SOL_MIN_WHALE_PF", "1.8"))
MIN_WHALE_WIN_RATE: float = float(os.getenv("SOL_MIN_WHALE_WR", "35.0"))
MAX_WHALE_WIN_RATE: float = float(os.getenv("SOL_MAX_WHALE_WR", "65.0"))
MIN_WHALE_TXS: int = int(os.getenv("SOL_MIN_WHALE_TXS", "30"))
MAX_TRACKED_WHALES: int = int(os.getenv("SOL_MAX_TRACKED_WHALES", "50"))

# --- Position Management (TP/SL/Stagnation) ---
HARD_SL_PERCENT: float = float(os.getenv("SOL_HARD_SL_PERCENT", "50.0"))         # -50% Hard Stop
STAGE1_TP_GAIN_PERCENT: float = float(os.getenv("SOL_STAGE1_TP", "100.0"))        # +100% (2x) take 50% profit
STAGNATION_TIMEOUT_MINUTES: float = float(os.getenv("SOL_STAGNATION_MINUTES", "30.0"))

# --- Unified Controller Webhook ---
CONTROLLER_WEBHOOK: str = os.getenv("CONTROLLER_WEBHOOK", "http://127.0.0.1:8080/event")
