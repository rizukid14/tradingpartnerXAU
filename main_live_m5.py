"""
Trading Partner - M5 Live Cent Fast Execution Runner
Direct pure quant M5 fast-in fast-out trading on Live Cent Account (#27556325).
Baseline: Clean quant-trade-m5demolab architecture.
Features: Single Ticket, Native 15m MT5 Expiration, BEP 80% TP, Pre-Rollover Shield, Runaway TP Guard.
"""

import os
import sys
import time
import logging
from typing import Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

# 1. Pastikan memuat .env (LIVE Cent), bukan .env.demo
os.environ["ENV_FILE"] = ".env"

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
logger = logging.getLogger("main_live_m5")

# Track active pending orders for lifecycle management & 15m cancel cooldown
_active_pending_orders: Dict[int, Dict[str, Any]] = {}


def is_pre_rollover_window(now_dt: datetime) -> bool:
    """Jendela bahaya spread rollover MT5 (03:50 - 04:15 WIB = 23:50 - 00:15 server)."""
    h, m = now_dt.hour, now_dt.minute
    if h == 3 and m >= 50:
        return True
    if h == 4 and m <= 15:
        return True
    return False


def sync_pending_orders(scanner: MarketScannerM5):
    """
    Monitors tracked pending orders:
    1. Runaway TP Guard: If market price reaches/crosses TP before limit fill -> Cancel immediately!
    2. Lifecycle Sync:
       - If filled -> Logged as SUCCESS fill.
       - If expired/cancelled -> Triggers 15-minute cooldown (900s) on that symbol.
    """
    global _active_pending_orders

    try:
        current_orders = config.mt5.orders_get() or []
        current_order_tickets = {o.ticket for o in current_orders}

        # Auto-adopt any pending orders from MT5 that are not yet tracked
        for o in current_orders:
            if o.ticket not in _active_pending_orders:
                _active_pending_orders[o.ticket] = {
                    "symbol": o.symbol,
                    "type": "buy_limit" if o.type == config.mt5.ORDER_TYPE_BUY_LIMIT else ("sell_limit" if o.type == config.mt5.ORDER_TYPE_SELL_LIMIT else "pending"),
                    "placed_at": time.time(),
                    "price": o.price_open,
                    "sl": o.sl,
                    "tp": o.tp,
                    "direction": 1 if o.type in (config.mt5.ORDER_TYPE_BUY_LIMIT, config.mt5.ORDER_TYPE_BUY_STOP) else -1
                }

        # 1. Runaway TP Guard: Cancel pending order if market price already reached TP
        for o in current_orders:
            t = o.ticket
            info = _active_pending_orders.get(t)
            if not info or not info.get("tp"):
                continue
            sym = info["symbol"]
            tp_price = float(info["tp"])
            direction = info.get("direction", 0)
            if tp_price <= 0:
                continue

            tick = connector.get_current_tick(sym)
            if not tick:
                continue
            ask = tick.get("ask", 0.0)
            bid = tick.get("bid", 0.0)

            runaway = (direction == 1 and ask >= tp_price) or (direction == -1 and bid <= tp_price)
            if runaway:
                print(f" {UI.RED}[RUNAWAY TP CANCEL]{UI.RST} Pending order #{t} {sym} dibatalkan: Harga pasar sudah mencapai target TP ({tp_price:.5f}) sebelum terjemput!")
                connector.cancel_pending_order(t)
                _active_pending_orders.pop(t, None)
                if scanner is not None and hasattr(scanner, "mark_symbol_cancelled"):
                    scanner.mark_symbol_cancelled(sym, cooldown_seconds=900)
                continue

        # 2. Check disappeared orders (filled vs expired/cancelled)
        open_positions = connector.get_all_open_positions()
        open_tickets = {p.get("ticket") for p in open_positions}
        open_pos_ids = {getattr(p, "position_id", None) or p.get("position_id") for p in open_positions}

        disappeared = [t for t in list(_active_pending_orders.keys()) if t not in current_order_tickets]
        for t in disappeared:
            info = _active_pending_orders.pop(t, None)
            if not info:
                continue
            sym = info["symbol"]
            ptype = info.get("type", "pending")
            # Filled
            if t in open_tickets or t in open_pos_ids:
                print(f" {UI.GREEN}[PENDING FILLED]{UI.RST} Order #{t} {sym} ({ptype}) ter-fill menjadi posisi aktif!")
            else:
                # Cancelled or expired -> Apply 15-minute cooldown
                print(f" {UI.YELLOW}[PENDING CANCELLED/EXPIRED]{UI.RST} Order #{t} {sym} ({ptype}) expired/dibatalkan. Mengaktifkan cooldown 15 menit.")
                if scanner is not None and hasattr(scanner, "mark_symbol_cancelled"):
                    scanner.mark_symbol_cancelled(sym, cooldown_seconds=900)
    except Exception as e:
        logger.debug(f"[PENDING SYNC ERROR] {e}")


def run_live_execution_cycle(cand, risk: RiskEngine) -> bool:
    """
    Direct MT5 Live Cent Execution Cycle:
    - Checks Pre-Rollover Shield (03:50 - 04:15 WIB).
    - Enforces Paper Quarantine for XAU/BTC.
    - Rejects setup if live market price already touched/passed target TP.
    - Capped at MAX_POSITION_LOT (0.50 lot for Cent Account).
    - Uses native MT5 15-minute pending order expiration.
    """
    global _active_pending_orders
    sym = cand.symbol
    direction = cand.direction
    c_dir = "BUY" if direction == 1 else "SELL"
    now_wib = datetime.now(WIB)

    # 1. Pre-Rollover Shield: Bekukan order baru saat pergantian hari MT5
    if is_pre_rollover_window(now_wib):
        print(f" {UI.YELLOW}[ROLLOVER SHIELD] Order {sym} dibekukan selama jendela rollover (03:50-04:15 WIB).{UI.RST}")
        return False

    # 2. Quarantine Guard: XAU & BTC dialihkan ke Virtual Paper (0 risiko modal cent)
    if config.is_paper_only(sym):
        print(f" {UI.MAGENTA}[PAPER QUARANTINE] {sym} berstatus Paper Only. Dilewati dari eksekusi MT5 Live.{UI.RST}")
        return False

    # 3. Risk Engine Capacity Check
    can_trade_ok, risk_msg = risk.can_trade(sym, action=direction)
    if not can_trade_ok:
        print(f" {UI.YELLOW}[RISK GATE] {sym} [{cand.timeframe}] ditolak: {risk_msg}{UI.RST}")
        return False

    # 4. Fetch live tick for execution
    tick_live = connector.get_current_tick(sym)
    if not tick_live:
        print(f" {UI.RED}[ERROR] Gagal membaca live tick {sym}.{UI.RST}")
        return False

    pt = tick_live.get("point", 0.00001) or 0.00001
    ask = tick_live.get("ask", 0.0)
    bid = tick_live.get("bid", 0.0)
    mkt_ref = ask if direction == 1 else bid
    trig_p = getattr(cand, "trigger_price", 0.0) or mkt_ref

    # 5. Pre-Execution Target Reach Guard: Tolak order jika harga live sudah menyentuh / melewati target TP
    if direction == 1 and cand.suggested_tp and ask >= cand.suggested_tp:
        print(f" {UI.YELLOW}[RADAR SKIP]{UI.RST} {sym} BUY dibatalkan: Harga live ask ({ask:.5f}) sudah menyentuh/melebihi target TP ({cand.suggested_tp:.5f}).")
        return False
    elif direction == -1 and cand.suggested_tp and bid <= cand.suggested_tp:
        print(f" {UI.YELLOW}[RADAR SKIP]{UI.RST} {sym} SELL dibatalkan: Harga live bid ({bid:.5f}) sudah menyentuh/melebihi target TP ({cand.suggested_tp:.5f}).")
        return False

    print("\n" + render_candidate_alert_box(cand))
    print(f" {UI.CYAN}[M5 LIVE RADAR]{UI.RST} {sym} [{cand.setup_type}] | Entry: {cand.trigger_price} | SL: {cand.suggested_sl} | TP: {cand.suggested_tp} (R:R {cand.risk_reward_ratio:.2f}:1)")

    # 6. Sizing lot dengan Hard Cap Akun Cent (MAX_POSITION_LOT = 0.50)
    sl_pts = int(round(abs(trig_p - cand.suggested_sl) / pt)) if pt > 0 else 80
    lot_size = risk.get_effective_lot_size(sl_pts, symbol=sym)
    max_lot_cap = float(getattr(config, "MAX_POSITION_LOT", 0.50))
    lot_size = min(lot_size, max_lot_cap)

    entry_type = "market"
    entry_price = mkt_ref

    # 7. Deteksi Pending Limit Order
    if getattr(config, "PENDING_ORDERS_ENABLED", True) and trig_p > 0:
        spread_pts = tick_live.get("spread", 0)
        min_dist_pts = max(spread_pts * 2, 15)
        if direction == 1 and (ask - trig_p) >= (min_dist_pts * pt):
            entry_type = "buy_limit"
            entry_price = trig_p
        elif direction == -1 and (trig_p - bid) >= (min_dist_pts * pt):
            entry_type = "sell_limit"
            entry_price = trig_p

    expiry_mins = int(getattr(config, "M5_PENDING_EXPIRATION_MINUTES", 15))
    print(f" {UI.GREEN}[LIVE ORDER DISPATCH]{UI.RST} Mengirim order {c_dir} ({entry_type.upper()} @ {entry_price:.5f}) Lot: {lot_size} | SL: {cand.suggested_sl:.5f} | TP: {cand.suggested_tp:.5f} (Expiry: {expiry_mins}m)...")

    # 8. Eksekusi MT5 Live Order
    if entry_type in ("buy_limit", "sell_limit", "buy_stop", "sell_stop"):
        order_res = connector.send_pending_order(
            symbol=sym,
            entry_type=entry_type,
            entry_price=entry_price,
            lot=lot_size,
            sl_price=cand.suggested_sl,
            tp_price=cand.suggested_tp,
            comment=f"M5_{cand.setup_type[:6]}",
            expiration_minutes=expiry_mins
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
        if entry_type in ("buy_limit", "sell_limit", "buy_stop", "sell_stop") and isinstance(ticket, int):
            _active_pending_orders[ticket] = {
                "symbol": sym,
                "type": entry_type,
                "placed_at": time.time(),
                "price": entry_price,
                "sl": cand.suggested_sl,
                "tp": cand.suggested_tp,
                "direction": direction
            }
        print(f" {UI.GREEN}{UI.BOLD}[STAGE 2 LIVE SUCCESS]{UI.RST} Order {entry_type.upper()} {c_dir} #{ticket} terpasang untuk {sym} (Lot {lot_size})!\n")
        return True
    else:
        err_msg = order_res.get("comment", "Unknown error") if isinstance(order_res, dict) else str(order_res)
        print(f" {UI.RED}[STAGE 2 LIVE ERROR]{UI.RST} Gagal memasang order {sym}: {err_msg}\n")
        return False


def main():
    print(f"""
{UI.GREEN}╔══════════════════════════════════════════════════════════════════════════════╗
║        TRADING PARTNER — M5 FAST-IN FAST-OUT LIVE CENT                       ║
║  Account  : VTMarkets-Live 3 (#27556325) | Timeframe: M5 (Scan Loop: 15s)   ║
║  Strategy : Micro-ZCE (M5/M15/H1) | Pure Quant (0 Token API)                 ║
║  Safety   : Hard Lot Cap <= 0.50 | Native MT5 Expiry: 15m | BEP 80% TP       ║
╚══════════════════════════════════════════════════════════════════════════════╝{UI.RST}
""")

    # Initialize MT5 Live Terminal
    if not connector.init_mt5():
        print(f" {UI.RED}[FATAL]{UI.RST} Gagal menginisialisasi MT5 Live terminal. Pastikan terminal desktop aktif.")
        sys.exit(1)

    acc = connector.get_account_info()
    print(f" {UI.GREEN}[CONNECTED]{UI.RST} Akun Live: #{acc.get('login')} ({acc.get('server')}) | Balance: ${acc.get('balance'):,.2f} | Equity: ${acc.get('equity'):,.2f}")

    risk = RiskEngine()
    scanner = MarketScannerM5()

    print(f" {UI.CYAN}[PREHEAT]{UI.RST} Memuat Micro-ZCE & Macro Context untuk {len(scanner.symbols)} simbol universe... Mohon tunggu ~20 detik.")
    scanner.update_macro_context(connector, force=True)
    print(f" {UI.GREEN}[READY]{UI.RST} Micro-ZCE aktif. Memulai pemindaian live M5 Fast Radar (15s loop)...\n")

    _last_radar_scan = 0.0
    _scan_interval = getattr(config, "RADAR_SCAN_INTERVAL_SECONDS", 15)

    try:
        while True:
            now_epoch = time.time()

            # 1. Kelola posisi terbuka tiap 2 detik (BEP 80% TP)
            try:
                position_manager.manage_all_positions(connector, risk)
            except Exception as e:
                logger.debug(f"[POSITION MANAGER] {e}")

            # 2. Sinkronisasi Pending Orders & Cooldown 15m saat Expired/Cancelled/Runaway TP
            try:
                sync_pending_orders(scanner)
            except Exception as e:
                logger.debug(f"[PENDING SYNC] {e}")

            # 3. Fast Radar Scan tiap 15 detik
            if now_epoch - _last_radar_scan >= _scan_interval:
                _last_radar_scan = now_epoch
                t_str = time.strftime("%H:%M:%S")
                try:
                    candidates = scanner.scan_all(connector)
                    if candidates:
                        print(f" {UI.GREEN}[{t_str} M5 RADAR]{UI.RST} {len(candidates)} SETUP TERDETEKSI! Mengeksekusi order riil ke MT5 Live...")
                        for cand in candidates:
                            run_live_execution_cycle(cand, risk)
                    else:
                        open_cnt = len(connector.get_all_open_positions())
                        pending_cnt = len(config.mt5.orders_get() or []) if hasattr(config.mt5, "orders_get") else 0
                        print(f" {UI.DIM}[{t_str} M5 RADAR]{UI.RST} 28 pairs dipindai (M5): 0 trigger baru | Posisi Aktif: {open_cnt} | Pending: {pending_cnt}")
                except Exception as e:
                    print(f" [M5 RADAR ERROR] {e}")

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n [BOT STOPPED] Dimatikan secara manual oleh pengguna.")
    finally:
        connector._safe_mt5_shutdown()
        print(" [SHUTDOWN] Koneksi MT5 Live ditutup bersih. Selesai.")


if __name__ == "__main__":
    main()
