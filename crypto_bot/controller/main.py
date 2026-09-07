"""
main.py — Main Entrypoint for Unified Crypto Controller.
Runs the FastAPI Event Bridge server and manages Telegram bot alerts.
"""

import os
import sys
import logging
import uvicorn
from datetime import datetime

# Adjust path for internal module imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    from crypto_bot.controller import config
    from crypto_bot.controller.src.risk_pool import SharedRiskPool
    from crypto_bot.controller.src.telegram_bot import CryptoTelegramController
    from crypto_bot.controller.src.event_bridge import create_app
except ImportError:
    import config
    from src.risk_pool import SharedRiskPool
    from src.telegram_bot import CryptoTelegramController
    from src.event_bridge import create_app

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("crypto_controller.main")

risk_pool = SharedRiskPool()
telegram = CryptoTelegramController(risk_pool)
app = create_app(risk_pool=risk_pool, telegram_notifier=telegram.send_message)


def print_banner():
    now_wib = datetime.now(config.TIMEZONE_WIB).strftime("%Y-%m-%d %H:%M:%S WIB")
    banner = f"""
======================================================================
  UNIFIED CRYPTO BOT CONTROLLER & RISK POOL
  Timestamp:       {now_wib}
  HTTP Server:     http://{config.CONTROLLER_HOST}:{config.CONTROLLER_PORT}
  Daily Loss Cap:  {config.CRYPTO_DAILY_LOSS_PERCENT}%
  Telegram Alerts: {'CONFIGURED' if config.CRYPTO_TELEGRAM_TOKEN else 'SIMULATED (Console)'}
======================================================================
"""
    print(banner)


if __name__ == "__main__":
    print_banner()
    logger.info(f"Starting controller bridge on port {config.CONTROLLER_PORT}...")
    uvicorn.run(app, host=config.CONTROLLER_HOST, port=config.CONTROLLER_PORT, log_level="info")
