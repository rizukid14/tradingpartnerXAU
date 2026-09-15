"""
Trading Partner — M5 Fast Quant Scalping Runner (Live Cent Dedicated)
=====================================================================
Dedicated fast-in fast-out Pure Quant scalper for Live Cent Account (#27556325).
- Derived from the proven main_demo.py architecture: compact, robust, zero LLM overhead.
- Direct execution via Micro-ZCE (M5/M15/H1) and calibrated tight M5 SL/TP geometry.
- Connects directly to the default active MT5 Terminal (no portable path overrides).
- Enforces Cent lot cap (MAX_POSITION_LOT = 0.50), BEP at 80% TP, and Pre-Rollover Shield.
- Quarantines XAUUSD-ECNc and BTCUSD.c to Virtual Paper Trade (0 MT5 Risk).
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# 1. Force UTF-8 encoding for standard output on Windows
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
from src.analytics.shadow_tracker import shadow_tracker
from src.core import telegram_alerts as tg

WIB = ZoneInfo("Asia/Jakarta")
logger = logging.getLogger("main_m5")


def is_pre_rollover_window(now_dt: datetime) -> bool:
    """
    Detects daily server rollover dangerous spread spike window (03:50 - 04:15 WIB).
    VTMarkets-Live 3 rollover is at 00:00 server (04:00 WIB).
    During this 25-minute window, opening new M5 scalping orders is frozen.
    """
    h = now_dt.hour
    m = now_dt.minute
    if h == 3 and m >= 50:
        return True
    if h == 4 and m <= 15:
        return True
    return False


def run_m5_execution_cycle(cand, risk: RiskEngine) -> bool:
    """
    Direct M5 Pure Quant Execution Cycle:
    - Quarantines XAUUSD-ECNc and BTCUSD.c to Virtual Paper Trade (Shadow Tracker).
    - Checks Risk Engine Capacity and Pre-Rollover Shield.
    - Directly executes Limit Order or Market Order onto MT5 Live Cent.
    - Preserves tight M5 SL/TP geometry directly from Micro-ZCE without H1 clamping.
    """
    sym = cand.symbol
    direction = cand.direction
    c_dir = "BUY" if direction == 1 else "SELL"
    now_dt = datetime.now(WIB)

    # 1. Pre-Rollover Shield: freeze new entries during 03:50 - 04:15 WIB spread spike window
    if is_pre_rollover_window(now_dt):
        print(f" {UI.YELLOW}[PRE-ROLLOVER SHIELD] {sym} [{cand.timeframe}] dibatalkan: Jendela bahaya spread rollover (03:50-04:15 WIB).{UI.RST}")
        return False

    # 2. XAU & BTC Quarantine: Route strictly to Virtual Paper Trade (Shadow Tracker)
    if config.is_paper_only(sym):
        t_live = connector.get_current_tick(sym)
        pt = t_live.get("point", 0.00001) if t_live else 0.00001
        mkt_ref = (t_live.get("ask", 0.0) if direction == 1 else t_live.get("bid", 0.0)) if t_live else cand.trigger_price
        c_sl_pts = int(round(abs(cand.trigger_price - cand.suggested_sl) / pt)) if pt > 0 else 80
        c_tp_pts = int(round(abs(cand.suggested_tp - cand.trigger_price) / pt)) if pt > 0 else 140
        shadow_trade = shadow_tracker.register_candidate(
            candidate=cand,
            entry_type="market",
            entry_price=cand.trigger_price or mkt_ref,
            sl_price=cand.suggested_sl,
            tp_price=cand.suggested_tp,
            sl_points=c_sl_pts,
            tp_points=c_tp_pts,
            mt5_disposition="PAPER_TRADE_ONLY"
        )
        if shadow_trade:
            print(f" {UI.MAGENTA}[SHADOW RADAR REGISTERED] {sym} ({cand.setup_type}) dicatat ke Paper Trade (PAPER_TRADE_ONLY).{UI.RST}")
        return False

    # 3. Pre-check: Risk Engine Capacity
    can_trade_ok, risk_msg = risk.can_trade(sym, action=direction)
    if not can_trade_ok:
        print(f" {UI.YELLOW}[RISK GATE] {sym} [{cand.timeframe}] ditolak: {risk_msg}{UI.RST}")
        return False

    # 3b. Hard R:R Floor Gate: Absolute minimum 1.20:1 net R:R
    rr = getattr(cand, "risk_reward_ratio", 0.0)
    if rr < 1.20:
        print(f" {UI.RED}[R:R HARD GATE] {sym} [{cand.timeframe}] dibatalkan: Net R:R {rr:.2f}:1 < 1.20:1 minimum floor.{UI.RST}")
        return False

    _st_mech_map = {
        "UNIVERSAL_LIQUIDITY_SWEEP": "M1",
        "TREND_ALIGNED_PULLBACK": "M2",
        "MULTI_TOUCH_BREAKOUT_RETEST": "M3",
        "SYSTEMIC_FLOW_CONTINUATION": "M4",
        "DBD_RBR_BREAKOUT_CONTINUATION": "M4",
    }
    m_code = _st_mech_map.get(cand.setup_type, "M?")

    print("\n" + render_candidate_alert_box(cand))
    print(f" {UI.CYAN}[M5 LIVE RADAR]{UI.RST} {sym} [[{m_code}] {cand.setup_type}] | Entry: {cand.trigger_price} | SL: {cand.suggested_sl} | TP: {cand.suggested_tp} (R:R {cand.risk_reward_ratio:.2f}:1)")

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

    # 5. Sizing lot calculation (enforcing Cent lot cap <= 0.50)
    sl_pts = int(round(abs(trig_p - cand.suggested_sl) / pt)) if pt > 0 else 80
    lot_size = risk.get_effective_lot_size(sl_pts, symbol=sym)
    cent_cap = float(getattr(config, "MAX_POSITION_LOT", 0.50))
    lot_size = min(lot_size, cent_cap)

    entry_type = "market"
    entry_price = mkt_ref

    # 6. Mechanism-Aware Execution: M1 Sweep -> Instant Market, M2/M3 -> Delayed Limit at ZCE Anchor
    setup_type = getattr(cand, "setup_type", "")
    is_sweep_m1 = "UNIVERSAL" in setup_type or "SWEEP" in setup_type

    if is_sweep_m1:
        # M1 Universal Liquidity Sweep: Rejection wick confirmed, execute Market Order directly
        entry_type = "market"
        entry_price = mkt_ref
    elif getattr(config, "PENDING_ORDERS_ENABLED", True) and trig_p > 0:
        # M2 Pullback / M3 Retest: Delayed Limit Retest unless price is already at the station (< min_dist_pts)
        spread_pts = tick_live.get("spread", 0)
        min_dist_pts = max(spread_pts * 2, 15)

        if direction == 1 and (ask - trig_p) >= (min_dist_pts * pt):
            entry_type = "buy_limit"
            entry_price = trig_p
        elif direction == -1 and (trig_p - bid) >= (min_dist_pts * pt):
            entry_type = "sell_limit"
            entry_price = trig_p
        else:
            # Price is already right at ZCE station (< min_dist_pts): execute Market Order directly
            entry_type = "market"
            entry_price = mkt_ref

    # Slippage Protection for Market Order execution: ensure minimum TP distance is maintained from live fill
    if entry_type == "market":
        min_tp_dist = sl_pts * pt * 1.20
        digits = 5 if pt < 0.01 else (3 if "JPY" in sym.upper() else 2)
        if direction == 1 and (cand.suggested_tp - entry_price) < min_tp_dist:
            cand.suggested_tp = round(entry_price + min_tp_dist, digits)
            tp1_pts = int(round(abs(cand.suggested_tp - entry_price) / pt))
        elif direction == -1 and (entry_price - cand.suggested_tp) < min_tp_dist:
            cand.suggested_tp = round(entry_price - min_tp_dist, digits)
            tp1_pts = int(round(abs(cand.suggested_tp - entry_price) / pt))

    # 7. Single Ticket Scalp Order Dispatch (Fast-In Fast-Out)
    setup_tag = (cand.setup_type or "UNIV")[:6]
    comment_s1 = f"{m_code}_{setup_tag}"
    pending_exp = int(getattr(config, "M5_PENDING_EXPIRATION_MINUTES", 30))
    tp_pts = int(round(abs(cand.suggested_tp - entry_price) / pt)) if pt > 0 else 80

    actual_sl_dist = abs(entry_price - cand.suggested_sl)
    actual_tp_dist = abs(cand.suggested_tp - entry_price)
    if actual_sl_dist > 0:
        actual_rr = round(actual_tp_dist / actual_sl_dist, 2)
        cand.risk_reward_ratio = actual_rr
        if actual_rr < 1.20:
            print(f" {UI.RED}[R:R HARD GATE] {sym} dibatalkan: Live fill R:R {actual_rr:.2f}:1 < 1.20:1.{UI.RST}")
            return False

    print(f" {UI.GREEN}[M5 ORDER DISPATCH]{UI.RST} Mengirim Single Order {c_dir} ({entry_type.upper()} @ {entry_price:.5f}) Lot: {lot_size} | SL: {cand.suggested_sl:.5f} | TP: {cand.suggested_tp:.5f} (R:R {cand.risk_reward_ratio:.2f}:1)...")

    if entry_type in ("buy_limit", "sell_limit", "buy_stop", "sell_stop"):
        order_res = connector.send_pending_order(
            symbol=sym, entry_type=entry_type, entry_price=entry_price, lot=lot_size,
            sl_price=cand.suggested_sl, tp_price=cand.suggested_tp,
            comment=comment_s1, expiration_minutes=pending_exp
        )
    else:
        order_res = connector.send_trade_order(
            symbol=sym, action=c_dir, lot=lot_size,
            sl_price=cand.suggested_sl, tp_price=cand.suggested_tp, comment=comment_s1
        )

    if order_res and order_res.get("status") == "SUCCESS":
        ticket = order_res.get("ticket", "OK")
        print(f" {UI.GREEN}{UI.BOLD}[M5 LIVE SUCCESS]{UI.RST} Order {entry_type.upper()} {c_dir} #{ticket} terpasang untuk {sym} (Lot {lot_size})!\n")
        risk.record_trade_opened()
        try:
            tg.alert_trade_opened(
                symbol=sym, signal=c_dir, lot=lot_size, entry_price=entry_price,
                sl_price=cand.suggested_sl, tp_price=cand.suggested_tp, sl_points=sl_pts,
                tp_points=tp_pts, risk_usd=risk.equity * (config.risk_percent_for(sym) / 100.0),
                setup=f"[{m_code}] {cand.setup_type} (M5 Scalp)",
                models="Pure Quant Direct (M5 Micro-ZCE)", confidence=0.88,
                reason=f"M5 Micro-ZCE scalping execution, R:R {cand.risk_reward_ratio:.2f}:1"
            )
        except Exception:
            pass
        return True
    else:
        err_msg = order_res.get("comment", "Unknown error") if isinstance(order_res, dict) else str(order_res)
        print(f" {UI.RED}[M5 LIVE ERROR]{UI.RST} Gagal memasang order {sym}: {err_msg}\n")
        return False


_known_pending_orders = {}


def _sync_pending_orders(scanner):
    """
    Tracks pending orders lifecycle in M5 bot:
    - If a pending order is filled into an active position -> send alert_pending_order_filled.
    - If a pending order disappears without becoming an open position (cancelled manually by user or expired) ->
      apply 10-minute cancel cooldown on the symbol in scanner and send Telegram notification.
    """
    global _known_pending_orders
    try:
        mt = getattr(config, "mt5", None)
        if mt is None:
            return
        orders = mt.orders_get() or []
        cur_order_map = {}

        for o in orders:
            t = getattr(o, "ticket", None)
            if t is not None:
                cur_order_map[t] = {
                    "ticket": t,
                    "symbol": getattr(o, "symbol", ""),
                    "type": getattr(o, "type", 0),
                    "price": getattr(o, "price_open", 0.0),
                    "sl": getattr(o, "sl", 0.0),
                    "tp": getattr(o, "tp", 0.0),
                }

        # 1. Register newly observed pending orders
        for t, o in cur_order_map.items():
            if t not in _known_pending_orders:
                _known_pending_orders[t] = o

        # 2. Detect disappearing orders
        disappeared = [t for t in _known_pending_orders if t not in cur_order_map]
        if not disappeared:
            return

        open_positions = connector.get_all_open_positions() if hasattr(connector, 'get_all_open_positions') else []
        open_tickets = {p.get("ticket") for p in open_positions}

        deal_order_to_pos = {}
        try:
            now_dt = datetime.now()
            from_epoch = int((now_dt - timedelta(hours=2)).timestamp())
            to_epoch = int(now_dt.timestamp()) + 86400
            deals = mt.history_deals_get(from_epoch, to_epoch) or []
            for d in deals:
                if getattr(d, "entry", None) == getattr(mt, "DEAL_ENTRY_IN", 0) and getattr(d, "order", 0):
                    deal_order_to_pos.setdefault(d.order, getattr(d, "position_id", d.order))
        except Exception as ed:
            logger.debug(f"[M5 PENDING DEAL LOOKUP] {ed}")

        cd_sec = int(getattr(config, "PENDING_ORDER_CANCEL_COOLDOWN_SECONDS", 600))
        for t in disappeared:
            info = _known_pending_orders.pop(t, {})
            sym = info.get("symbol", "")
            price = info.get("price", 0.0)
            ptype = "BUY_LIMIT" if info.get("type") in (2, getattr(mt, "ORDER_TYPE_BUY_LIMIT", 2)) else "SELL_LIMIT"
            pos_id = deal_order_to_pos.get(t)

            if pos_id or t in open_tickets:
                res_pos = pos_id or t
                print(f" {UI.GREEN}[PENDING FILLED]{UI.RST} Pending #{t} {sym} ter-fill menjadi posisi aktif #{res_pos}!")
                try:
                    tg.alert_pending_order_filled(t, sym, ptype, price, pos_id=res_pos, sl_price=info.get("sl"), tp_price=info.get("tp"))
                except Exception:
                    pass
            else:
                print(f" {UI.YELLOW}[PENDING CANCELLED/EXPIRED]{UI.RST} Pending #{t} {sym} ({ptype}) dibatalkan / expired. Mengaktifkan cooldown {cd_sec // 60}m.")
                if scanner and hasattr(scanner, "mark_symbol_cancelled"):
                    scanner.mark_symbol_cancelled(sym, cooldown_seconds=cd_sec, reason="Cancelled / Expired")
                try:
                    tg.alert_pending_order_cancelled(t, sym, ptype, price, reason=f"Dibatalkan User / Expired (Cooldown {cd_sec // 60}m Aktif)")
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"[M5 PENDING SYNC ERROR] {e}")


_session_consecutive_wins = 0
_winstreak_cooldown_until = 0.0
_last_closed_deal_ticket = 0


def _audit_winstreak_deals():
    """
    Tracks consecutive closed wins in the live session.
    If consecutive wins >= M5_WINSTREAK_COOLDOWN_COUNT (default 10),
    triggers a cooldown for M5_WINSTREAK_COOLDOWN_MINUTES (default 30 mins).
    """
    global _session_consecutive_wins, _winstreak_cooldown_until, _last_closed_deal_ticket
    mt = getattr(config, "mt5", None)
    if mt is None:
        return

    try:
        now_dt = datetime.now()
        from_epoch = int((now_dt - timedelta(days=1)).timestamp())
        to_epoch = int(now_dt.timestamp()) + 86400
        deals = mt.history_deals_get(from_epoch, to_epoch) or []
        out_deals = [d for d in deals if getattr(d, "entry", 0) == getattr(mt, "DEAL_ENTRY_OUT", 1)]
        if not out_deals:
            return

        out_deals.sort(key=lambda d: getattr(d, "time_msc", getattr(d, "time", 0)))
        max_ticket = max(getattr(d, "ticket", 0) for d in out_deals)

        if _last_closed_deal_ticket == 0:
            _last_closed_deal_ticket = max_ticket
            return

        if max_ticket <= _last_closed_deal_ticket:
            return

        new_deals = [d for d in out_deals if getattr(d, "ticket", 0) > _last_closed_deal_ticket]
        _last_closed_deal_ticket = max_ticket

        target_streak = int(os.getenv("M5_WINSTREAK_COOLDOWN_COUNT", str(getattr(config, "M5_WINSTREAK_COOLDOWN_COUNT", 0))))
        if target_streak <= 0:
            return

        cooldown_mins = int(os.getenv("M5_WINSTREAK_COOLDOWN_MINUTES", "30"))

        for d in new_deals:
            pnl = getattr(d, "profit", 0.0) + getattr(d, "commission", 0.0) + getattr(d, "swap", 0.0)
            if pnl > 0.01:
                _session_consecutive_wins += 1
                logger.info(f"[WINSTREAK AUDIT] Win (+${pnl:.2f}). Streak: {_session_consecutive_wins}/{target_streak}")
                if _session_consecutive_wins >= target_streak:
                    _winstreak_cooldown_until = time.time() + (cooldown_mins * 60)
                    _session_consecutive_wins = 0
                    print(f"\n {UI.YELLOW}{UI.BOLD}[WINSTREAK {target_streak}X REACHED]{UI.RST} Tercapai {target_streak} win beruntun! Mengaktifkan pendingin sistem selama {cooldown_mins} menit...\n")
                    logger.warning(f"[WINSTREAK COOLING] {target_streak} consecutive wins hit. Cooling active for {cooldown_mins}m.")
                    try:
                        tg.send_message(f"🏆 *Winstreak Circuit Breaker*: Terdeteksi {target_streak} win beruntun! Mendinginkan sistem selama {cooldown_mins} menit untuk meredam mean-reversion risk.")
                    except Exception:
                        pass
            elif pnl < -0.05:  # actual loss
                if _session_consecutive_wins > 0:
                    logger.info(f"[WINSTREAK AUDIT] Loss (${pnl:.2f}). Streak reset from {_session_consecutive_wins} to 0.")
                _session_consecutive_wins = 0
    except Exception as e:
        logger.debug(f"[WINSTREAK ERROR] {e}")


def main():
    print(f"""
{UI.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗
║        TRADING PARTNER — M5 PURE QUANT SCALPING RUNNER (LIVE CENT)           ║
║  Account  : Live Cent VTMarkets (#27556325) | Timeframe: M5 (10s Loop)       ║
║  Strategy : Micro-ZCE (M5/M15/H1) | Single Ticket Scalp (SL < TP, R:R >=1.25)║
║  Execution: Pure Quant Direct (0 Tokens) | Single Scalp | BEP 80% | Cap: 0.50 ║
╚══════════════════════════════════════════════════════════════════════════════╝{UI.RST}
""")

    # 1. Connect to active MT5 Terminal (standard path from .env, no portable override)
    if not connector.initialize_mt5():
        print(f" {UI.RED}[FATAL]{UI.RST} Gagal menginisialisasi MT5 Terminal. Pastikan MetaTrader 5 berjalan.")
        sys.exit(1)

    acc = connector.get_account_info()
    acc_num = acc.get('login') if acc else "Unknown"
    acc_srv = acc.get('server') if acc else "Unknown"
    acc_bal = acc.get('balance', 0.0) if acc else 0.0
    acc_eq = acc.get('equity', 0.0) if acc else 0.0
    print(f" {UI.GREEN}[CONNECTED]{UI.RST} Akun MT5: #{acc_num} ({acc_srv}) | Balance: ${acc_bal:,.2f} | Equity: ${acc_eq:,.2f}")

    # 2. Enforce M5 Live Cent configurations
    config.MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "50"))
    config.MAX_ABSOLUTE_OPEN_POSITIONS = int(os.getenv("MAX_ABSOLUTE_OPEN_POSITIONS", "50"))
    config.MAX_POSITION_LOT = float(os.getenv("MAX_POSITION_LOT", "0.50"))
    config.M5_TWIN_TICKET_ENABLED = False
    config.BREAK_EVEN_TRIGGER_TP_PCT = 0.80
    config.BREAK_EVEN_ENABLED = True
    config.TRAILING_STOP_ENABLED = False
    config.PARTIAL_CLOSE_ENABLED = False

    risk = RiskEngine()
    scanner = MarketScannerM5()

    print(f" {UI.CYAN}[PREHEAT]{UI.RST} Memuat Micro-ZCE & Macro Context untuk {len(scanner.symbols)} simbol universe... Mohon tunggu ~10 detik.")
    scanner.update_macro_context(connector, force=True)
    print(f" {UI.GREEN}[READY]{UI.RST} Micro-ZCE aktif. Memulai pemindaian live M5 Fast Radar (10s loop)...\n")

    _last_radar_scan = 0.0
    _scan_interval = int(getattr(config, "RADAR_SCAN_INTERVAL_SECONDS", 10) or 10)

    try:
        while True:
            now_epoch = time.time()

            # A. Manage Active Positions & Pending Order Lifecycle every 2 seconds
            try:
                position_manager.manage_all_positions()
                _sync_pending_orders(scanner)
            except Exception as e:
                logger.error(f"[POSITION/PENDING MANAGER ERROR] {e}")
                print(f" {UI.RED}[POSITION/PENDING MANAGER ERROR]{UI.RST} {e}")

            # B. Check Winstreak Cooldown (Bypassed if M5_WINSTREAK_COOLDOWN_COUNT <= 0)
            target_streak = int(os.getenv("M5_WINSTREAK_COOLDOWN_COUNT", str(getattr(config, "M5_WINSTREAK_COOLDOWN_COUNT", 0))))
            if target_streak > 0:
                _audit_winstreak_deals()
                if now_epoch < _winstreak_cooldown_until:
                    rem_sec = int(_winstreak_cooldown_until - now_epoch)
                    t_str = time.strftime("%H:%M:%S")
                    print(f" \r{UI.YELLOW}[{t_str} WINSTREAK COOLING]{UI.RST} Pendingin sistem aktif: sisa {rem_sec // 60}m {rem_sec % 60}s... (posisi tetap dikawal)", end="", flush=True)
                    time.sleep(2)
                    continue

            # C. Check Night Freeze (22:00 - 06:00 WIB)
            now_wib = datetime.now(WIB)
            freeze_start = int(os.getenv("NIGHT_FREEZE_START_HOUR_WIB", "22"))
            freeze_end = int(os.getenv("NIGHT_FREEZE_END_HOUR_WIB", "6"))
            is_frozen = (now_wib.hour >= freeze_start or now_wib.hour < freeze_end) if freeze_start > freeze_end else (freeze_start <= now_wib.hour < freeze_end)
            if is_frozen:
                t_str = time.strftime("%H:%M:%S")
                print(f" \r{UI.YELLOW}[{t_str} NIGHT FREEZE]{UI.RST} Pembukaan order baru dibekukan ({freeze_start}:00 - {freeze_end:00} WIB). Posisi tetap dikawal.", end="", flush=True)
                time.sleep(2)
                continue

            # D. Fast Radar Scan every 10-15 seconds
            if now_epoch - _last_radar_scan >= _scan_interval:
                _last_radar_scan = now_epoch
                t_str = time.strftime("%H:%M:%S")
                try:
                    candidates = scanner.scan_all(connector)
                    if candidates:
                        print(f"\n {UI.GREEN}[{t_str} M5 RADAR]{UI.RST} {len(candidates)} SETUP TERDETEKSI! Mengeksekusi order riil ke MT5 Cent...")
                        for cand in candidates:
                            run_m5_execution_cycle(cand, risk)
                    else:
                        open_cnt = len(connector.get_all_open_positions())
                        pending_cnt = len(config.mt5.orders_get() or []) if hasattr(config.mt5, "orders_get") else 0
                        print(f" {UI.DIM}[{t_str} M5 RADAR]{UI.RST} 28 pairs dipindai (M5): 0 trigger baru | Posisi Aktif Cent: {open_cnt} | Pending: {pending_cnt}/50")
                except Exception as e:
                    print(f" [M5 RADAR ERROR] {e}")

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n [M5 BOT STOPPED] Dimatikan secara manual oleh pengguna.")
    finally:
        connector._safe_mt5_shutdown()
        print(" [SHUTDOWN] Koneksi MT5 ditutup bersih. Selesai.")


if __name__ == "__main__":
    main()
