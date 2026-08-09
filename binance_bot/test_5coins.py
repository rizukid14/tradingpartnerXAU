"""
Test 5 koin teratas (PUMP, CRV, PYTH, TAO, PEPE) — jalankan cycle tiap 5 menit
sampai dapat BUY (dry-run). Ganti config.SYMBOL per koin, pakai run_trading_cycle.

Jalankan: py test_5coins.py  (dari binance_bot/)
"""
import logging
import sys
import time
from datetime import datetime

sys.path.insert(0, ".")

import config
from src.core import ccxt_connector as connector
from src.core.risk_engine import RiskEngine
from main import run_trading_cycle

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
for noisy in ("openai", "google.genai", "httpx", "urllib3", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("binance_bot")

# 5 koin teratas dari scan (ATR M5 tertinggi, spread tipis) + UNI/AAVE
COINS = ["PUMPUSDT", "CRVUSDT", "PYTHUSDT", "TAOUSDT", "UNIUSDT", "AAVEUSDT"]

risk = RiskEngine()
last_candle = None
buy_logged = set()

print(f"🎯 Test 5 koin: {', '.join(COINS)} — cari BUY pertama (dry-run)")
print(f"Mode: DRY_RUN={config.DRY_RUN} | Timeframe: {config.TIMEFRAME}\n")

while True:
    try:
        # Cek candle baru (5m) — satu candle = satu round untuk semua koin
        df = connector.get_klines(COINS[0], config.TIMEFRAME, 2)
        if df is not None and len(df) > 0:
            cur = df.iloc[-1]["time"]
            cur_ts = cur.timestamp() if hasattr(cur, "timestamp") else 0
            if cur_ts != last_candle:
                last_candle = cur_ts
                print(f"\n{'='*60}\n⏰ Round baru: {datetime.now().strftime('%H:%M:%S')} (candle {cur})\n{'='*60}")
                for coin in COINS:
                    if coin in buy_logged:
                        continue
                    config.SYMBOL = coin
                    print(f"\n--- {coin} ---")
                    run_trading_cycle(risk)
                    # Deteksi BUY dari log? run_trading_cycle return None — cek posisi terbuka
                    if risk.get_open_positions(coin):
                        buy_logged.add(coin)
                        print(f"✅✅✅ BUY TERCATAT untuk {coin}!")
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n👋 Dihentikan.")
        break
    except Exception as e:
        log.error(f"[TEST] {e}")
        time.sleep(5)
