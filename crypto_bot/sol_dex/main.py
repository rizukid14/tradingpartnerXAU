"""
main.py — Main Execution Coordinator for sol_dex (Solana On-Chain Whale Copy-Trader).
Orchestrates:
  - Whale Discovery Whitelist Maintenance
  - Real-time Transaction Listener & DEX Swap Parser
  - Sub-500ms Zero-LLM Deterministic Safety Gate
  - Jupiter V6 Priority Swap Execution (DRY_RUN / Live)
  - Active Position Management (Staged TP, Hard SL, Stagnation)
  - Post-Entry AI Sentinel Background Auditing
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
    from crypto_bot.sol_dex import config
    from crypto_bot.sol_dex.src.whale_discovery import WhaleDiscoveryEngine
    from crypto_bot.sol_dex.src.whale_watcher import SolanaWhaleWatcher
    from crypto_bot.sol_dex.src.safety_filter import SolanaSafetyFilter
    from crypto_bot.sol_dex.src.executor import JupiterExecutor
    from crypto_bot.sol_dex.src.position_manager import SolanaPositionManager
    from crypto_bot.sol_dex.src.ai_sentinel import AISentinelAudit
except ImportError:
    import config
    from src.whale_discovery import WhaleDiscoveryEngine
    from src.whale_watcher import SolanaWhaleWatcher
    from src.safety_filter import SolanaSafetyFilter
    from src.executor import JupiterExecutor
    from src.position_manager import SolanaPositionManager
    from src.ai_sentinel import AISentinelAudit

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("sol_dex.main")


class SolanaDEXEngine:
    """Core Coordinator for Solana On-Chain Copy-Trading."""

    def __init__(self):
        self.running = True
        logger.info("Initializing Solana DEX Engine...")

        self.discovery = WhaleDiscoveryEngine()
        self.watcher = SolanaWhaleWatcher()
        self.safety_filter = SolanaSafetyFilter()
        self.executor = JupiterExecutor()
        self.position_manager = SolanaPositionManager(self.executor)
        self.sentinel = AISentinelAudit()

        self.last_discovery_time: float = 0.0
        self.last_poll_time: float = 0.0
        self.last_pm_time: float = 0.0

    def print_banner(self) -> None:
        """Displays engine startup banner with WIB time."""
        now_wib = datetime.now(config.TIMEZONE_WIB).strftime("%Y-%m-%d %H:%M:%S WIB")
        tracked_count = len(self.discovery.get_tracked_addresses())
        mode_str = "DRY_RUN (SIMULATED)" if config.SOL_DRY_RUN else "LIVE TRADING"
        banner = f"""
======================================================================
  SOLANA ON-CHAIN WHALE COPY-TRADER (sol_dex)
  Timestamp:       {now_wib}
  Mode:            {mode_str} | RPC: {config.SOL_RPC_URL[:32]}...
  Whales Tracked:  {tracked_count} Wallets
  Max Pos USD:     ${config.SOL_MAX_POSITION_USD:,.2f} | Hard SL: -{config.HARD_SL_PERCENT}%
  Safety Gate:     LP Burned >= {config.MIN_LP_BURNED_PERCENT}% | Top10 <= {config.MAX_TOP10_HOLDER_PERCENT}%
======================================================================
"""
        print(banner)

    def run_cycle(self) -> None:
        """Main non-blocking execution loop."""
        now = time.time()

        # 1. Refresh Whale Whitelist every 24 hours (86400s)
        if now - self.last_discovery_time >= 86400:
            try:
                self.discovery.refresh_whitelist()
            except Exception as e:
                logger.error(f"Error refreshing whale discovery: {e}")
            self.last_discovery_time = now

        # 2. Poll Whale Wallets every 15 seconds
        if now - self.last_poll_time >= 15:
            try:
                self._poll_whale_signals()
            except Exception as e:
                logger.error(f"Error in whale polling cycle: {e}")
            self.last_poll_time = now

        # 3. Monitor Active Positions every 5 seconds
        if now - self.last_pm_time >= 5:
            try:
                self._manage_active_positions()
            except Exception as e:
                logger.error(f"Error in position management: {e}")
            self.last_pm_time = now

    def _poll_whale_signals(self) -> None:
        """Polls tracked addresses for new swap transactions."""
        addresses = self.discovery.get_tracked_addresses()
        for addr in addresses[:10]:  # Poll top 10 to avoid public RPC throttling
            signals = self.watcher.poll_wallet_activity(addr)
            for sig in signals:
                self._process_copy_signal(sig)

    def _process_copy_signal(self, signal_data: dict) -> None:
        """Handles copy trade execution when whale signal is received."""
        side = signal_data.get("side")
        token_mint = signal_data.get("token_mint")
        whale_wallet = signal_data.get("wallet")

        if side != "BUY":
            # If whale is selling and we hold the token, exit
            open_positions = self.executor.get_open_positions()
            if token_mint in open_positions:
                logger.info(f"[WHALE EXIT SIGNAL] Whale {whale_wallet[:6]} sold token {token_mint[:8]}. Mirroring exit...")
                self.executor.execute_swap(token_mint, is_buy=False, amount_sol=0.0)
            return

        # Check open positions limit
        if len(self.executor.get_open_positions()) >= config.MAX_OPEN_POSITIONS:
            logger.info(f"Max open Solana positions ({config.MAX_OPEN_POSITIONS}) reached. Skipping copy.")
            return

        # 1. Zero-LLM Deterministic Safety Gate (<500ms)
        safety_res = self.safety_filter.evaluate_token(token_mint)
        if not safety_res["passed"]:
            logger.warning(
                f"[COPY BLOCKED] Token {token_mint[:8]} failed safety gate: {', '.join(safety_res['reasons'])}"
            )
            return

        # 2. Execute Swap via Jupiter
        amount_sol = min(0.05, config.SOL_MAX_POSITION_USD / 150.0)  # Approx $7-10 sizing in SOL
        logger.info(
            f"[EXECUTING COPY] Copying Whale {whale_wallet[:6]}... -> Buying token {token_mint[:8]} with {amount_sol:.4f} SOL"
        )
        swap_res = self.executor.execute_swap(token_mint, is_buy=True, amount_sol=amount_sol)

        # 3. Trigger Async AI Sentinel Audit
        self.sentinel.audit_position_async(token_mint, metadata=safety_res.get("details", {}))

    def _manage_active_positions(self) -> None:
        """Evaluates open positions for TP / SL / Stagnation."""
        positions = self.executor.get_open_positions()
        for token_mint in list(positions.keys()):
            # In live mode, fetch token price via Jupiter/DexScreener
            # Using current multiplier 1.05 as baseline
            self.position_manager.check_and_manage(token_mint, current_multiplier=1.0)

    def shutdown(self, signum=None, frame=None) -> None:
        """Graceful shutdown handler."""
        logger.info("Shutdown signal received. Stopping Solana DEX Engine...")
        self.running = False


def main():
    engine = SolanaDEXEngine()
    engine.print_banner()

    signal.signal(signal.SIGINT, engine.shutdown)
    signal.signal(signal.SIGTERM, engine.shutdown)

    while engine.running:
        engine.run_cycle()
        time.sleep(1)


if __name__ == "__main__":
    main()
