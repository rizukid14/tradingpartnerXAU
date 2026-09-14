"""
Trading Partner - M5 Demo Fast Execution Runner
Dedicated isolated environment for M5 fast-in fast-out trading on MT5 Demo (#1157958).
Runs concurrently with Live bot (main.py) without process collisions or IPC timeouts.
Uses MarketScannerM5 with Micro-ZCE and scaled M5 SL/TP geometry. Zero Shadow Paper.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

# 1. Force DEMO environment configuration file BEFORE importing config
os.environ["ENV_FILE"] = ".env.demo"

# 2. Force UTF-8 encoding for standard output on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
        sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)
    except Exception:
        pass

import config
from config import mt5
from src.core import mt5_connector as connector
from src.core.risk_engine import RiskEngine
from src.core.cli_theme import UI, render_candidate_alert_box
from src.analytics import position_manager
from src.analytics.market_scanner_m5 import MarketScannerM5

WIB = ZoneInfo("Asia/Jakarta")
logger = logging.getLogger("main_demo")


def run_demo_execution_cycle(cand, risk: RiskEngine) -> bool:
    """
    Direct MT5 Demo Execution Cycle:
    - Bypasses Shadow Paper Trade completely.
    - Directly executes Limit Order or Market Order onto MT5 Demo (#1157958).
    """
    sym = cand.symbol
    direction = cand.direction
    c_dir = "BUY" if direction == 1 else "SELL"

    # Pre-check: Risk Engine Capacity (unconstrained up to MAX_POSITIONS_TOTAL=50)
    can_trade_ok, risk_msg = risk.can_trade(sym, action=direction)
    if not can_trade_ok:
        print(f" {UI.YELLOW}[RISK GATE] {sym} [{cand.timeframe}] ditolak: {risk_msg}{UI.RST}")
        return False

    print("\n" + render_candidate_alert_box(cand))
    print(f" {UI.CYAN}[M5 DEMO RADAR]{UI.RST} {sym} [{cand.setup_type}] | Entry: {cand.trigger_price} | SL: {cand.suggested_sl} | TP: {cand.suggested_tp} (R:R {cand.risk_reward_ratio:.2f}:1)")

    # Fetch live tick for execution
    tick_live = connector.get_current_tick(sym)
    if not tick_live:
        print(f" {UI.RED}[ERROR] Gagal membaca live tick {sym}.{UI.RST}")
        return False

    pt = tick_live.get("point", 0.00001) or 0.00001
    ask = tick_live.get("ask", 0.0)
    bid = tick_live.get("bid", 0.0)
    mkt_ref = ask if direction == 1 else bid
    trig_p = getattr(cand, "trigger_price", 0.0) or mkt_ref

    # Sizing lot calculation
    sl_pts = int(round(abs(trig_p - cand.suggested_sl) / pt)) if pt > 0 else 80
    lot_size = risk.get_effective_lot_size(sl_pts, symbol=sym)
    lot_size = min(lot_size, getattr(config, "MAX_POSITION_LOT", 1.00))

    entry_type = "market"
    entry_price = mkt_ref

    # Check for Limit Order condition if enabled
    if getattr(config, "PENDING_ORDERS_ENABLED", True) and trig_p > 0:
        spread_pts = tick_live.get("spread", 0)
        min_dist_pts = max(spread_pts * 2, 15)
        if direction == 1 and (ask - trig_p) >= (min_dist_pts * pt):
            entry_type = "buy_limit"
            entry_price = trig_p
        elif direction == -1 and (trig_p - bid) >= (min_dist_pts * pt):
            entry_type = "sell_limit"
            entry_price = trig_p

    print(f" {UI.GREEN}[DEMO ORDER DISPATCH]{UI.RST} Mengirim order {c_dir} ({entry_type.upper()} @ {entry_price:.5f}) Lot: {lot_size} | SL: {cand.suggested_sl:.5f} | TP: {cand.suggested_tp:.5f}...")

    # Execute MT5 order
    if entry_type in ("buy_limit", "sell_limit", "buy_stop", "sell_stop"):
        order_res = connector.send_pending_order(
            symbol=sym,
            entry_type=entry_type,
            entry_price=entry_price,
            lot=lot_size,
            sl_price=cand.suggested_sl,
            tp_price=cand.suggested_tp,
            comment=f"M5_{cand.setup_type[:6]}"
        )
    else:
        order_res = connector.send_trade_order(
            symbol=sym,
            action=c_dir,
            lot=lot_size,
            sl_price=cand.suggested_sl,
            tp_price=cand.suggested_tp,
            comment=f"M5_{cand.setup_type[:6]}"
        )

    if order_res and order_res.get("status") == "SUCCESS":
        ticket = order_res.get("ticket", "OK")
        print(f" {UI.GREEN}{UI.BOLD}[STAGE 2 DEMO SUCCESS]{UI.RST} Order {entry_type.upper()} {c_dir} #{ticket} terpasang untuk {sym} (Lot {lot_size})!\n")
        return True
    else:
        err_msg = order_res.get("comment", "Unknown error") if isinstance(order_res, dict) else str(order_res)
        print(f" {UI.RED}[STAGE 2 DEMO ERROR]{UI.RST} Gagal memasang order {sym}: {err_msg}\n")
        return False


def main():
    print(f"""
{UI.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗
║        TRADING PARTNER — M5 FAST-IN FAST-OUT DEMO LAB (ISOLATED)             ║
║  Terminal : C:/Users/Daffa/MT5_Demo/terminal64.exe (/portable)               ║
║  Account  : VTMarkets-Demo (#1157958) | Timeframe: M5 (Scan Loop: 10s)       ║
║  Strategy : Micro-ZCE (M5/M15/H1) | Scaled SL/TP: 8-16p SL / 15-28p TP       ║
║  Execution: Pure Quant Direct (0 Tokens) | Unconstrained (Max Pos: 50)       ║
╚══════════════════════════════════════════════════════════════════════════════╝{UI.RST}
""")

    # Initialize MT5 Demo Terminal
    if not connector.init_mt5():
        print(f" {UI.RED}[FATAL]{UI.RST} Gagal menginisialisasi MT5 Demo terminal. Pastikan portable terminal berjalan.")
        sys.exit(1)

    acc = connector.get_account_info()
    print(f" {UI.GREEN}[CONNECTED]{UI.RST} Akun Demo: #{acc.get('login')} ({acc.get('server')}) | Balance: ${acc.get('balance'):,.2f} | Equity: ${acc.get('equity'):,.2f}")

    risk = RiskEngine()
    scanner = MarketScannerM5()

    print(f" {UI.CYAN}[PREHEAT]{UI.RST} Memuat Micro-ZCE & Macro Context untuk {len(scanner.symbols)} simbol universe... Mohon tunggu ~20 detik.")
    scanner.update_macro_context(connector, force=True)
    print(f" {UI.GREEN}[READY]{UI.RST} Micro-ZCE aktif. Memulai pemindaian live M5 Fast Radar (10s loop)...\n")

    _last_radar_scan = 0.0
    _scan_interval = getattr(config, "RADAR_SCAN_INTERVAL_SECONDS", 10)

    try:
        while True:
            now_epoch = time.time()

            # 1. Manage Active Positions every 2 seconds (Trailing Stop & BEP)
            try:
                position_manager.manage_all_positions(connector, risk)
            except Exception as e:
                logger.debug(f"[POSITION MANAGER] {e}")

            # 2. Fast Radar Scan every 10-15 seconds
            if now_epoch - _last_radar_scan >= _scan_interval:
                _last_radar_scan = now_epoch
                t_str = time.strftime("%H:%M:%S")
                try:
                    candidates = scanner.scan_all(connector)
                    if candidates:
                        print(f" {UI.GREEN}[{t_str} M5 RADAR]{UI.RST} {len(candidates)} SETUP TERDETEKSI! Mengeksekusi order riil ke MT5 Demo...")
                        for cand in candidates:
                            run_demo_execution_cycle(cand, risk)
                    else:
                        open_cnt = len(connector.get_all_open_positions())
                        pending_cnt = len(config.mt5.orders_get() or []) if hasattr(config.mt5, "orders_get") else 0
                        print(f" {UI.DIM}[{t_str} M5 RADAR]{UI.RST} 28 pairs dipindai (M5): 0 trigger baru | Posisi Aktif Demo: {open_cnt} | Pending: {pending_cnt}/50")
                except Exception as e:
                    print(f" [M5 RADAR ERROR] {e}")

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n [DEMO BOT STOPPED] Dimatikan secara manual oleh pengguna.")
    finally:
        connector._safe_mt5_shutdown()
        print(" [SHUTDOWN] Koneksi MT5 Demo ditutup bersih. Selesai.")


if __name__ == "__main__":
    main()
