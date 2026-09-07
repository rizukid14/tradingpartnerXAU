"""
main.py — Main Execution Coordinator for btc_perp (BTC Perpetual Whale Follower Engine).
Orchestrates:
  - 5-Second Real-Time Position Manager (BEP, Trailing Stop, Stagnation)
  - 60-Second Stage 1 Fast Execution Radar (M1/M2/M3 Quant Signals)
  - 3-LLM Consensus Jury & Hard Risk Veto
  - Institutional Risk Engine & Exchange Router (Hyperliquid / Binance)
"""

import os
import sys
import time
import signal
import logging
from datetime import datetime

# Adjust path for internal module imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    from crypto_bot.btc_perp import config
    from crypto_bot.btc_perp.src.core.exchange_router import ExchangeRouter
    from crypto_bot.btc_perp.src.core.whale_tracker import WhaleTracker
    from crypto_bot.btc_perp.src.core.risk_engine import BTCRiskEngine
    from crypto_bot.btc_perp.src.core.consensus import BTCConsensusJury
    from crypto_bot.btc_perp.src.core.position_manager import BTCPositionManager
    from crypto_bot.btc_perp.src.analytics.btc_scanner import BTCScanner
except ImportError:
    import config
    from src.core.exchange_router import ExchangeRouter
    from src.core.whale_tracker import WhaleTracker
    from src.core.risk_engine import BTCRiskEngine
    from src.core.consensus import BTCConsensusJury
    from src.core.position_manager import BTCPositionManager
    from src.analytics.btc_scanner import BTCScanner

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("btc_perp.main")


class BTCPerpEngine:
    """Core Coordinator for BTC Perpetual Engine."""

    def __init__(self):
        self.running = True
        logger.info("Initializing BTC Perpetual Engine...")
        
        self.router = ExchangeRouter()
        self.whale_tracker = WhaleTracker(cache_ttl_sec=120)
        self.risk_engine = BTCRiskEngine()
        self.consensus_jury = BTCConsensusJury()
        self.scanner = BTCScanner(self.router)
        self.position_manager = BTCPositionManager(self.router)
        
        self.last_scan_time: float = 0.0
        self.last_pm_time: float = 0.0
        self.current_atr: float = 800.0

    def print_banner(self) -> None:
        """Displays engine startup banner with WIB time."""
        now_wib = datetime.now(config.TIMEZONE_WIB).strftime("%Y-%m-%d %H:%M:%S WIB")
        equity = self.router.get_equity()
        mode_str = "DRY_RUN (SIMULATED)" if config.BTC_DRY_RUN else "LIVE TRADING"
        banner = f"""
======================================================================
  BTC PERPETUAL WHALE FOLLOWER ENGINE (btc_perp)
  Timestamp: {now_wib}
  Mode:      {mode_str} | Primary Exchange: {self.router.get_active_exchange_name().upper()}
  Equity:    ${equity:,.2f} USDC | Max Leverage: {config.BTC_LEVERAGE}x
  Risk/Pos:  {config.BTC_RISK_PERCENT}% | Daily Loss Limit: {config.DAILY_LOSS_PERCENT}%
======================================================================
"""
        print(banner)

    def run_cycle(self) -> None:
        """Main non-blocking execution loop."""
        now = time.time()

        # Loop 1: Position Management every 5 seconds
        if now - self.last_pm_time >= config.POSITION_MANAGER_INTERVAL_SEC:
            try:
                self.position_manager.manage_positions(atr_h1=self.current_atr)
            except Exception as e:
                logger.error(f"Error in Position Manager: {e}")
            self.last_pm_time = now

        # Loop 2: Quant Radar Scan every 60 seconds
        if now - self.last_scan_time >= config.SCANNER_INTERVAL_SEC:
            try:
                self._run_scanner_cycle()
            except Exception as e:
                logger.error(f"Error in Scanner Cycle: {e}")
            self.last_scan_time = now

    def _run_scanner_cycle(self) -> None:
        """Runs the 2-Stage Quant Funnel for BTC."""
        # 1. Stage 1 Radar (0 Token)
        setup = self.scanner.scan()
        self.current_atr = setup.get("atr_h1", 800.0)
        direction = setup.get("direction", "HOLD")

        if direction == "HOLD":
            logger.info(f"Radar Scan: No setup (ATR: ${self.current_atr:,.1f})")
            return

        logger.info(f"[RADAR HIT] {setup['mechanism']} -> Signal: {direction} (Score: {setup['score']})")

        # 2. Fetch Whale Positioning Context
        whale_data = self.whale_tracker.get_whale_positioning(config.BTC_SYMBOL)
        mkt_data = self.router.get_market_data(config.BTC_SYMBOL)

        # 3. Stage 2: 3-LLM Consensus Jury
        consensus = self.consensus_jury.evaluate(
            radar_setup=setup,
            market_data=mkt_data,
            whale_data=whale_data,
            atr_h1=self.current_atr,
        )

        final_signal = consensus.get("signal", "HOLD")
        if final_signal == "HOLD":
            logger.info(f"Consensus Result: HOLD ({consensus.get('reasoning')})")
            return

        # 4. Institutional Risk Engine Validation
        equity = self.router.get_equity()
        positions = self.router.get_positions()
        entry_px = consensus.get("entry_price", mkt_data["mid_price"])
        sl_px = consensus.get("sl", 0.0)
        tp_px = consensus.get("tp", 0.0)

        approved, btc_size, reason = self.risk_engine.validate_new_trade(
            equity=equity,
            current_positions=positions,
            entry_price=entry_px,
            sl_price=sl_px,
        )

        if not approved:
            logger.warning(f"Trade Rejected by Risk Engine: {reason}")
            return

        # 5. Order Execution via Exchange Router
        is_buy = (final_signal == "BUY")
        logger.info(
            f"[EXECUTING TRADE] {final_signal} {btc_size} BTC @ ${entry_px:,.2f} | "
            f"SL: ${sl_px:,.2f} | TP: ${tp_px:,.2f} | Conf: {consensus.get('confidence')}%"
        )

        order_res = self.router.place_order(
            coin=config.BTC_SYMBOL,
            is_buy=is_buy,
            sz=btc_size,
            px=entry_px,
            sl_px=sl_px,
            tp_px=tp_px,
            is_market=True,
        )
        logger.info(f"Order Result: {order_res}")

    def shutdown(self, signum=None, frame=None) -> None:
        """Graceful shutdown handler."""
        logger.info("Shutdown signal received. Stopping BTC Perp Engine...")
        self.running = False


def main():
    engine = BTCPerpEngine()
    engine.print_banner()

    signal.signal(signal.SIGINT, engine.shutdown)
    signal.signal(signal.SIGTERM, engine.shutdown)

    while engine.running:
        engine.run_cycle()
        time.sleep(1)


if __name__ == "__main__":
    main()
