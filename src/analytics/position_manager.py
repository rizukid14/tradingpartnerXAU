"""
Position Manager - Active position management after entry.

Combines the best from:
- XAU-60: Trailing stop with activation, break-even with padding
- xaubot-ai: Partial close at TP1, weekend close handler

Runs every tick cycle (every 5 seconds), NOT just on new candles.

State persistence: tracks which tickets have already been partially-closed
or moved to break-even so a bot restart cannot re-trigger those actions.
"""
import os
import json
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
import config
from config import mt5
from src.core.cli_theme import UI
from src.core.mt5_connector import is_order_success, get_usd_per_point
from src.core import telegram_alerts as tg

logger = logging.getLogger("trading_bot")
WIB = ZoneInfo("Asia/Jakarta")

STATE_FILE = os.path.join(config.DATA_DIR, "position_manager_state.json")
TELEMETRY_FILE = os.path.join(config.DATA_DIR, "trade_lifecycle_telemetry.json")


def _load_telemetry() -> dict:
    """Load persisted trade lifecycle telemetry (CSM Open/Close & Thesis Invalidation)."""
    try:
        if os.path.exists(TELEMETRY_FILE):
            with open(TELEMETRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"[TELEMETRY LOAD WARNING] {e}")
    return {"trades": {}, "thesis_observer_events": []}


def _save_telemetry(data: dict):
    """Persist trade lifecycle telemetry atomically."""
    try:
        tmp_path = TELEMETRY_FILE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if os.path.exists(TELEMETRY_FILE):
            os.replace(tmp_path, TELEMETRY_FILE)
        else:
            os.rename(tmp_path, TELEMETRY_FILE)
    except Exception as e:
        logger.error(f"[TELEMETRY SAVE ERROR] {e}")


def record_trade_open_telemetry(ticket: int, symbol: str, direction: str, entry_price: float, csm_delta: float, setup_type: str = ""):
    """Catat snapshot nilai CSM dan atribut entry saat posisi/pending order dibuka."""
    t_int = int(ticket)
    data = _load_telemetry()
    now_iso = datetime.now(WIB).isoformat()

    is_opposed = (direction == "BUY" and csm_delta <= -0.35) or (direction == "SELL" and csm_delta >= 0.35)

    data["trades"][str(t_int)] = {
        "ticket": t_int,
        "symbol": symbol,
        "direction": direction,
        "setup_type": setup_type,
        "entry_price": float(entry_price),
        "csm_delta_open": float(csm_delta),
        "csm_opposed_open": bool(is_opposed),
        "open_time": now_iso,
        "status": "OPEN",
        "would_be_cancelled": False,
        "cancellation_reason": None,
        "close_time": None,
        "csm_delta_close": None,
        "csm_delta_shift": None,
        "profit": None,
        "close_reason": None
    }
    _save_telemetry(data)
    opp_str = " (CSM OPPOSED)" if is_opposed else " (CSM ALIGNED/NEUTRAL)"
    print(f" {UI.CYAN}[CSM TELEMETRY OPEN]{UI.RST} Ticket #{t_int} | {symbol} {direction} | Entry: {entry_price} | CSM Delta Open: {csm_delta:+.2f}{opp_str}")
    logger.info(f"[CSM TELEMETRY OPEN] Ticket #{t_int} | {symbol} {direction} | CSM Delta Open: {csm_delta:+.2f}{opp_str}")


def record_thesis_observer_event(ticket: int, symbol: str, reason: str):
    """Catat event observer thesis invalidation saat order seharusnya dibatalkan."""
    t_int = int(ticket)
    data = _load_telemetry()
    now_iso = datetime.now(WIB).isoformat()

    if str(t_int) in data["trades"]:
        data["trades"][str(t_int)]["would_be_cancelled"] = True
        data["trades"][str(t_int)]["cancellation_reason"] = reason

    data["thesis_observer_events"].append({
        "time": now_iso,
        "ticket": t_int,
        "symbol": symbol,
        "reason": reason
    })
    data["thesis_observer_events"] = data["thesis_observer_events"][-100:]
    _save_telemetry(data)


def record_trade_close_telemetry(ticket: int, symbol: str, profit: float, reason: str, csm_delta_close: float, exit_price: float = 0.0):
    """Catat snapshot nilai CSM saat posisi ditutup dan hitung pergeseran delta."""
    t_int = int(ticket)
    data = _load_telemetry()
    now_iso = datetime.now(WIB).isoformat()

    rec = data["trades"].get(str(t_int))
    csm_open = rec.get("csm_delta_open", 0.0) if rec else 0.0
    csm_shift = round(float(csm_delta_close) - float(csm_open), 2) if (rec and rec.get("csm_delta_open") is not None) else 0.0
    direction = rec.get("direction", "TRADE") if rec else "TRADE"
    would_cancel = rec.get("would_be_cancelled", False) if rec else False

    if rec:
        rec["status"] = "CLOSED"
        rec["close_time"] = now_iso
        rec["exit_price"] = float(exit_price)
        rec["profit"] = float(profit)
        rec["close_reason"] = str(reason)
        rec["csm_delta_close"] = float(csm_delta_close)
        rec["csm_delta_shift"] = csm_shift
    else:
        data["trades"][str(t_int)] = {
            "ticket": t_int,
            "symbol": symbol,
            "direction": direction,
            "setup_type": "UNKNOWN",
            "entry_price": 0.0,
            "csm_delta_open": None,
            "csm_opposed_open": None,
            "open_time": None,
            "status": "CLOSED",
            "would_be_cancelled": False,
            "cancellation_reason": None,
            "close_time": now_iso,
            "csm_delta_close": float(csm_delta_close),
            "csm_delta_shift": None,
            "profit": float(profit),
            "close_reason": str(reason)
        }
    _save_telemetry(data)

    obs_tag = f" {UI.YELLOW}[OBSERVER: WOULD BE CANCELLED]{UI.RST}" if would_cancel else ""
    csm_open_str = f"{csm_open:+.2f}" if (rec and rec.get("csm_delta_open") is not None) else "N/A"
    print(f" {UI.CYAN}[CSM TELEMETRY CLOSE]{UI.RST} Ticket #{t_int} | {symbol} {direction} | P/L: ${profit:+.2f} ({reason}){obs_tag} | CSM Open: {csm_open_str} -> Close: {csm_delta_close:+.2f} (Shift: {csm_shift:+.2f})")
    logger.info(f"[CSM TELEMETRY CLOSE] Ticket #{t_int} | {symbol} {direction} | P/L: ${profit:+.2f} ({reason}) | CSM Open: {csm_open_str} -> Close: {csm_delta_close:+.2f} (Shift: {csm_shift:+.2f})")



def _load_state():
    """Load persisted tickets from disk. Returns (partial_set, be_set, extremes, original_sl, trail_active, peak_mfe, setup_grades)."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            partial = set(int(t) for t in data.get("partial_closed_tickets", []))
            be = set(int(t) for t in data.get("break_even_tickets", []))
            trail_active = set(int(t) for t in data.get("trailing_active_tickets", []))
            extremes = {int(k): float(v) for k, v in data.get("trailing_extremes", {}).items()}
            original_sl = {int(k): float(v) for k, v in data.get("original_sl_points", {}).items()}
            peak_mfe = {int(k): float(v) for k, v in data.get("peak_mfe_points", {}).items()}
            setup_grades = {int(k): str(v) for k, v in data.get("ticket_setup_grades", {}).items()}
            return partial, be, extremes, original_sl, trail_active, peak_mfe, setup_grades
    except Exception as e:
        print(f"[POS MANAGER WARNING] Gagal memuat position_manager_state.json: {e}")
    return set(), set(), {}, {}, set(), {}, {}


def _save_state(partial_set, be_set, extremes, original_sl=None, trail_active=None, peak_mfe=None, setup_grades=None):
    """Persist tickets to disk so restart can recover state."""
    if original_sl is None:
        original_sl = _original_sl
    if trail_active is None:
        trail_active = _trailing_active_tickets
    if peak_mfe is None:
        peak_mfe = _peak_mfe_points
    if setup_grades is None:
        setup_grades = _ticket_setup_grades
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "partial_closed_tickets": sorted(int(t) for t in partial_set),
                "break_even_tickets": sorted(int(t) for t in be_set),
                "trailing_active_tickets": sorted(int(t) for t in trail_active),
                "trailing_extremes": {str(k): v for k, v in extremes.items()},
                "original_sl_points": {str(k): v for k, v in original_sl.items()},
                "peak_mfe_points": {str(k): v for k, v in peak_mfe.items()},
                "ticket_setup_grades": {str(k): v for k, v in setup_grades.items()},
            }, f)
    except Exception as e:
        print(f"[POS MANAGER WARNING] Gagal menyimpan position_manager_state.json: {e}")


# Module-level state, loaded once at import (survives within a process)
_partial_closed_tickets, _break_even_tickets, _trailing_extremes, _original_sl, _trailing_active_tickets, _peak_mfe_points, _ticket_setup_grades = _load_state()


def set_ticket_setup_grade(ticket: int, setup_grade: str):
    """Sets and persists the setup grade for an open ticket."""
    _ticket_setup_grades[int(ticket)] = str(setup_grade).upper()
    _save_state(_partial_closed_tickets, _break_even_tickets, _trailing_extremes)


def get_peak_mfe_info(ticket, point=0.00001, volume=0.01, symbol=""):
    """Mengembalikan data peak profit historis untuk injeksi prompt AI Re-evaluator."""
    t_int = int(ticket)
    peak_pts = _peak_mfe_points.get(t_int, 0.0)
    init_sl = _original_sl.get(t_int, 0.0)
    peak_r = (peak_pts / init_sl) if (init_sl and init_sl > 0) else 0.0
    return peak_pts, peak_r


def get_ticket_status_badge(ticket):
    """Mengembalikan badge status manajemen posisi (BEP / TRAIL / PARTIAL) untuk display CLI."""
    tags = []
    t_int = int(ticket)
    if t_int in _partial_closed_tickets:
        tags.append(f"{UI.MAGENTA}PARTIAL{UI.RST}")
    if t_int in _trailing_active_tickets:
        tags.append(f"{UI.CYAN}TRAIL{UI.RST}")
    elif t_int in _break_even_tickets:
        tags.append(f"{UI.GREEN}BEP{UI.RST}")
    if tags:
        return f" [{'/'.join(tags)}]"
    return ""


def manage_all_positions():
    """
    Iterates ALL open bot positions (any symbol - XAU or BTC) and applies:
    1. Partial close at TP1 (close 50% of position at first target)
    2. Break-even (move SL to entry once threshold hit)
    3. Trailing stop (continuously advance SL behind price)

    Call this every tick cycle (every 5 seconds).
    Manages every symbol so a leftover position is still protected, but skips
    symbols whose market is closed (no fresh tick within the last N seconds -
    e.g. XAU over the weekend). BTC ticks 24/7 so it keeps being managed
    across weekday/weekend rotation.
    """
    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        return

    max_age = config.POSITION_MANAGER_MAX_TICK_AGE_SECONDS
    now = time.time()

    for pos in positions:
        # Only manage positions opened by our bot
        if pos.magic != config.MAGIC_NUMBER:
            continue

        symbol = pos.symbol
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            continue

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            continue

        # Skip symbols whose market is closed or that have no fresh ticks
        # (e.g. XAU over the weekend). Nothing to manage without live price.
        if now - tick.time > max_age:
            continue

        point = symbol_info.point

        # Rekam jarak SL ORIGINAL saat posisi pertama kali terlihat (sebelum
        # BE/trailing menggesernya). Dipakai sebagai referensi BEP/trailing
        # SL-based di mode LLM biar stabil - tidak ikut mengecil tiap SL digeser.
        if pos.ticket not in _original_sl and pos.sl:
            _original_sl[pos.ticket] = abs(pos.sl - pos.price_open) / point

        # Calculate current profit in points
        if pos.type == mt5.ORDER_TYPE_BUY:
            current_price = tick.bid
            profit_points = (current_price - pos.price_open) / point
        else:  # SELL
            current_price = tick.ask
            profit_points = (pos.price_open - current_price) / point

        # Track Peak MFE (Maximum Favorable Excursion)
        if pos.ticket not in _peak_mfe_points or profit_points > _peak_mfe_points[pos.ticket]:
            _peak_mfe_points[pos.ticket] = max(0.0, float(profit_points))

        # --- 1. TIME-DECAY STAGNATION EXIT (Ide 1) ---
        if getattr(config, "TIME_DECAY_STAGNATION_ENABLED", True):
            if _check_time_decay_stagnation(pos, symbol, profit_points, point, symbol_info, now):
                continue  # Posisi ditutup, lanjut ke tiket berikutnya

        # --- 2. PRE-ROLLOVER SHIELD (03:00 - 04:55 WIB) ---
        if getattr(config, "PRE_ROLLOVER_SHIELD_ENABLED", True):
            if _check_pre_rollover_shield(pos, symbol, profit_points, point, symbol_info, now):
                continue  # Posisi ditutup, lanjut ke tiket berikutnya

        # --- 2B. CSM DYNAMIC FLOW BAILOUT ---
        if getattr(config, "ENABLE_CSM_DYNAMIC_BAILOUT", True):
            if _check_csm_dynamic_bailout(pos, symbol, profit_points, point, symbol_info, now):
                continue  # Posisi ditutup via bailout, lanjut ke tiket berikutnya

        # M4 (SYSTEMIC_FLOW_CONTINUATION): Momentum Shock Continuation
        # - Bypass Partial Close & Trailing Stop agar volume penuh menuju TP 1.1R dan tidak terkena cut noise wicking.
        # - Break-Even Check (BEP) AKTIF di 70% TP untuk mengamankan profit (+ komisi round-trip + pocket profit 1.5 pips).
        # - Pre-Rollover Shield dan Time-Decay Stagnation di atas TETAP AKTIF melindungi modal.
        is_m4 = "SYSTEM" in (getattr(pos, "comment", "") or "").upper()
        grade = str(_ticket_setup_grades.get(pos.ticket, "GRADE_A")).upper()
        is_grade_b = "GRADE_B" in grade or "SCALP" in grade

        # --- 3. PARTIAL CLOSE at TP1 ---
        if not is_m4 and not is_grade_b and config.PARTIAL_CLOSE_ENABLED:
            _check_partial_close(pos, symbol, profit_points, symbol_info)

        # --- 4. BREAK-EVEN CHECK ---
        if config.BREAK_EVEN_ENABLED and (not is_m4 or getattr(config, "M4_BREAK_EVEN_ENABLED", True)):
            _check_break_even(pos, symbol, profit_points, point, symbol_info)

        # --- 5. TRAILING STOP CHECK ---
        if not is_m4 and config.TRAILING_STOP_ENABLED:
            _check_trailing_stop(pos, symbol, profit_points, current_price, point, symbol_info)

    # Bersihkan state posisi yang sudah tidak open (biar dict/set gak numpuk)
    open_tickets = {p.ticket for p in positions}
    changed = False
    for k in list(_trailing_extremes):
        if k not in open_tickets:
            del _trailing_extremes[k]
            changed = True
    for k in list(_original_sl):
        if k not in open_tickets:
            del _original_sl[k]
            changed = True
    for k in list(_trailing_active_tickets):
        if k not in open_tickets:
            _trailing_active_tickets.discard(k)
            changed = True
    for k in list(_peak_mfe_points):
        if k not in open_tickets:
            del _peak_mfe_points[k]
            changed = True
    if changed:
        _save_state(_partial_closed_tickets, _break_even_tickets, _trailing_extremes)

    # --- 6. REAL-TIME THESIS FAILURE AUDIT FOR PENDING ORDERS ---
    audit_pending_orders_thesis()


# =============================================================================
#  PARTIAL CLOSE (from XAU-60 trade_executor.py)
# =============================================================================


def _check_partial_close(pos, symbol, profit_points, symbol_info):
    """Close a portion of the position at TP1 to lock in some profit."""
    if pos.ticket in _partial_closed_tickets:
        return  # Already partially closed

    # 0.01 lot (volume_min) can't be split: 50% of 0.01 rounds to 0, and
    # forcing volume_min would close the entire position. Skip partial close.
    if pos.volume <= symbol_info.volume_min:
        return

    # Skip partial close for Grade B Wall Scalps and M4 (Single sprint target, avoid wasting quota to broker commissions)
    grade = str(_ticket_setup_grades.get(pos.ticket, "")).upper()
    is_m4 = "SYSTEM" in (getattr(pos, "comment", "") or "").upper()
    if "GRADE_B" in grade or is_m4:
        return

    # Calculate actual TP distance if set (dynamic LLM/ATR target)
    tp_points = 0
    if pos.tp:
        point = symbol_info.point
        if pos.type == mt5.ORDER_TYPE_BUY:
            tp_points = (pos.tp - pos.price_open) / point
        else:
            tp_points = (pos.price_open - pos.tp) / point

    # TP-Adaptive Partial Close (55% of actual TP target if exists, otherwise fallback)
    if tp_points > 0:
        pct = getattr(config, "PARTIAL_CLOSE_TRIGGER_TP_PCT", 0.55)
        tp1_points = int(tp_points * pct)
        min_tp1 = 40 if config.is_fx(symbol) else 120
        tp1_points = max(min_tp1, tp1_points)
    else:
        tp1_points = config.partial_close_tp1_for(symbol)

    if profit_points < tp1_points:
        return

    # Calculate volume to close
    close_volume = round(pos.volume * (config.PARTIAL_CLOSE_PERCENT / 100.0), 2)
    close_volume = max(symbol_info.volume_min, close_volume)

    # Make sure we don't close more than we have
    if close_volume >= pos.volume:
        return  # Would close entire position, skip

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return

    if pos.type == mt5.ORDER_TYPE_BUY:
        close_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        close_type = mt5.ORDER_TYPE_BUY
        price = tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": close_volume,
        "type": close_type,
        "position": pos.ticket,
        "price": price,
        "deviation": config.DEVIATION,
        "magic": config.MAGIC_NUMBER,
        "comment": "Partial TP1",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if is_order_success(result):
        _partial_closed_tickets.add(pos.ticket)
        _save_state(_partial_closed_tickets, _break_even_tickets, _trailing_extremes)
        remaining = round(pos.volume - close_volume, 2)
        print(f"\r\x1b[2K{UI.MAGENTA}[PARTIAL CLOSE]{UI.RST} Ticket #{pos.ticket} ({symbol}): Ditutup {close_volume} lot "
              f"(profit +{profit_points:.0f} pts). Sisa: {remaining} lot - trailing sisanya.")
        try:
            tg.alert_partial_close(pos.ticket, symbol, close_volume, remaining, profit_points)
        except Exception:
            pass
    else:
        comment = result.comment if result else "Unknown error"
        print(f"\r\x1b[2K[PARTIAL CLOSE ERROR] Gagal menutup sebagian #{pos.ticket}: {comment}")


# =============================================================================
#  TIME-DECAY STAGNATION & PRE-ROLLOVER SHIELD (Ide 1)
# =============================================================================


def _close_position_by_ticket(pos, symbol, reason_tag, comment=""):
    """Menutup posisi secara instan di market (misal Time-Decay / Pre-Rollover Shield)."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False
    close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": pos.volume,
        "type": close_type,
        "position": pos.ticket,
        "price": price,
        "deviation": config.DEVIATION,
        "magic": config.MAGIC_NUMBER,
        "comment": comment[:25] if comment else "Pos Manager",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if is_order_success(result):
        print(f"\r\x1b[2K{UI.YELLOW}{reason_tag}{UI.RST} Ticket #{pos.ticket} ({symbol}) {pos.volume} lot berhasil ditutup! Alasan: {comment}")
        try:
            tg.send_message(f"🛡️ <b>{reason_tag}</b>\nTicket: <code>#{pos.ticket}</code> ({symbol})\nAlasan: {comment}")
        except Exception:
            pass
        return True
    else:
        err = result.comment if result else "Unknown error"
        print(f"\r\x1b[2K[POS MANAGER ERROR] Gagal menutup #{pos.ticket} ({reason_tag}): {err}")
        return False


def _check_time_decay_stagnation(pos, symbol, profit_points, point, symbol_info, now):
    """
    Ide 1: Active-Session Peak-Aware Time-Decay Stagnation Exit.
    Jika posisi sudah berumur >= 4 jam (4 candle H1 aktif), dan floating berada di [-0.2R, +0.2R]
    DAN peak MFE tidak pernah melebihi +0.30R (posisi memang mati/tidak ada momentum),
    tutup posisi otomatis.
    """
    if not getattr(config, "TIME_DECAY_STAGNATION_ENABLED", True):
        return False

    now_wib = datetime.now(WIB)
    start_session = getattr(config, "TIME_DECAY_START_HOUR_WIB", 14)
    # Hanya evaluasi time-decay pada jam aktif London - NY (14:00 - 00:00 WIB)
    # Di luar jam ini (misal sesi Tokyo/Asia yang sepi), pergerakan sideways adalah wajar
    if not (start_session <= now_wib.hour <= 23):
        return False

    pos_open_time = getattr(pos, "time", 0)
    if not pos_open_time or pos_open_time <= 0:
        return False

    grade = _ticket_setup_grades.get(pos.ticket, "GRADE_A")
    if "GRADE_S" in grade:
        return False  # Grade S swing positions are immune from 4h time-decay exit

    holding_hours = max(0.0, (now - pos_open_time) / 3600.0)
    max_hold_hours = getattr(config, "TIME_DECAY_HOURS", 4.0)
    if holding_hours < max_hold_hours:
        return False

    init_sl_pts = _original_sl.get(pos.ticket, 0.0) or (abs(pos.sl - pos.price_open) / point if pos.sl else 0.0)
    if init_sl_pts <= 0:
        return False

    curr_r = profit_points / init_sl_pts
    peak_pts = _peak_mfe_points.get(pos.ticket, 0.0)
    peak_r = peak_pts / init_sl_pts

    min_r = getattr(config, "TIME_DECAY_MIN_R", -0.20)
    max_r = getattr(config, "TIME_DECAY_MAX_R", 0.20)
    max_peak_r = getattr(config, "TIME_DECAY_MAX_PEAK_R", 0.30)

    # Hanya tutup jika floating saat ini di rentang [-0.2R, +0.2R] DAN peak historis < +0.3R
    if (min_r <= curr_r <= max_r) and (peak_r < max_peak_r):
        reason = f"Stagnan {holding_hours:.1f}h (floating {curr_r:+.2f}R, peak {peak_r:+.2f}R)"
        return _close_position_by_ticket(pos, symbol, "[TIME-DECAY EXIT]", comment=reason)

    return False


def _check_pre_rollover_shield(pos, symbol, profit_points, point, symbol_info, now):
    """
    RFC 9: Pre-Rollover Precision Distance-to-SL Shield (03:50 - 04:15 WIB).
    Mengecek sisa jarak fisik harga ke level SL. Jika sisa jarak ke SL <= threshold lonjakan
    spread rollover simbol tersebut, tutup posisi bersih di jam 03:50 WIB sebelum lonjakan
    spread jam 04:00 WIB terjadi untuk mencegah gap down & slippage 2x SL.
    """
    if not getattr(config, "PRE_ROLLOVER_SHIELD_ENABLED", False):
        return False

    now_wib = datetime.now(WIB)
    exit_h = getattr(config, "PRE_ROLLOVER_EXIT_HOUR_WIB", 3)
    exit_m = getattr(config, "PRE_ROLLOVER_EXIT_MINUTE_WIB", 50)

    # Hanya aktif di jendela 03:50 s/d 04:15 WIB (00:00 MT5 server rollover)
    curr_min = now_wib.hour * 60 + now_wib.minute
    target_start_min = exit_h * 60 + exit_m   # 03:50 -> 230
    target_end_min = 4 * 60 + 15            # 04:15 -> 255

    if not (target_start_min <= curr_min <= target_end_min):
        return False

    # Crypto trades 24/7 tanpa rollover spread spike yang sama seperti FX
    if config.is_crypto(symbol):
        return False

    # Posisi tanpa SL tidak dievaluasi
    if not pos.sl or pos.sl <= 0:
        return False

    # Hitung sisa jarak fisik harga saat ini ke level SL
    close_price = getattr(pos, "price_current", 0.0) or getattr(pos, "price_open", 0.0)
    dist_sl_pts = abs(close_price - pos.sl) / point

    # Dapatkan threshold bahaya lonjakan per-simbol
    threshold_pts = config.get_pre_rollover_slippage_threshold(symbol)

    # HANYA TUTUP jika sisa jarak fisik ke SL <= threshold lonjakan rollover
    if dist_sl_pts <= threshold_pts:
        pips_scale = 10.0
        reason = (f"SL mepet pre-rollover ({now_wib.strftime('%H:%M')} WIB, "
                  f"sisa SL {dist_sl_pts/pips_scale:.1f}p <= spike {threshold_pts/pips_scale:.1f}p)")
        return _close_position_by_ticket(pos, symbol, "[PRE-ROLLOVER SHIELD]", comment=reason)

    return False


def _check_csm_dynamic_bailout(pos, symbol, profit_points, point, symbol_info, now):
    """
    CSM Dynamic Flow Bailout:
    Menutup dini posisi terbuka jika arus mata uang sistemik (Boitoki CSM Net Delta)
    berbalik tajam melawan arah trade DAN posisi sedang mengalami floating rugi.
    
    Dual Gate:
    1. Finansial: Posisi sedang floating rugi (curr_r <= -0.25R).
    2. Arus Sistemik Ekstrim:
       - BUY: csm_delta <= -2.0 ATAU csm_delta_shift <= -2.5
       - SELL: csm_delta >= +2.0 ATAU csm_delta_shift >= +2.5
    """
    if not getattr(config, "ENABLE_CSM_DYNAMIC_BAILOUT", True):
        return False
    if config.is_crypto(symbol):
        return False

    init_sl_pts = _original_sl.get(pos.ticket, 0.0) or (abs(pos.sl - pos.price_open) / point if pos.sl else 0.0)
    if init_sl_pts <= 0:
        return False

    curr_r = profit_points / init_sl_pts
    min_loss_r = getattr(config, "CSM_BAILOUT_MIN_LOSS_R", -0.25)
    # Hanya aktif jika sedang floating rugi di bawah threshold (misal <= -0.25R)
    if curr_r > min_loss_r:
        return False

    try:
        from src.analytics.currency_strength import get_csm_delta_for_symbol
        csm_delta = get_csm_delta_for_symbol(symbol)
    except Exception as e:
        logger.debug(f"[CSM BAILOUT] Gagal fetch CSM delta untuk {symbol}: {e}")
        return False

    # Ambil snapshot CSM saat posisi pertama kali dibuka dari telemetry (jika ada)
    telemetry = _load_telemetry()
    rec = telemetry.get("trades", {}).get(str(pos.ticket), {})
    csm_open = rec.get("csm_delta_open")
    csm_shift = round(float(csm_delta) - float(csm_open), 2) if (csm_open is not None) else 0.0

    shift_thresh = float(getattr(config, "CSM_BAILOUT_SHIFT_THRESH", 2.5))
    abs_opposed_thresh = float(getattr(config, "CSM_BAILOUT_ABS_THRESH", 2.0))

    should_bailout = False
    bail_reason = ""

    if pos.type == mt5.ORDER_TYPE_BUY:
        if csm_delta <= -abs_opposed_thresh:
            should_bailout = True
            bail_reason = f"CSM Net Delta {csm_delta:+.2f} heavily opposed BUY"
        elif csm_open is not None and csm_shift <= -shift_thresh:
            should_bailout = True
            bail_reason = f"CSM Net Delta shifted {csm_shift:+.2f} against BUY (open: {csm_open:+.2f})"
    else:  # SELL
        if csm_delta >= abs_opposed_thresh:
            should_bailout = True
            bail_reason = f"CSM Net Delta {csm_delta:+.2f} heavily opposed SELL"
        elif csm_open is not None and csm_shift >= shift_thresh:
            should_bailout = True
            bail_reason = f"CSM Net Delta shifted {csm_shift:+.2f} against SELL (open: {csm_open:+.2f})"

    if should_bailout:
        reason = f"CSM Flow Inversion ({bail_reason}, float {curr_r:+.2f}R)"
        return _close_position_by_ticket(pos, symbol, "[CSM BAILOUT EXIT]", comment=reason)

    return False


# =============================================================================
#  BREAK-EVEN (from XAU-60 trade_executor.py)
# =============================================================================


def _get_entry_fill_price(pos, symbol):
    """
    Returns the ACTUAL fill price of the entry deal for a position.
    `positions_get().price_open` can differ from the real fill by slippage
    (order request price vs executed deal price) - using it for break-even
    puts the SL slightly inside the losing side and gets stopped out for a
    tiny loss instead of a true break-even. The deal history is the source
    of truth for the executed price.
    Falls back to pos.price_open if the deal history is unavailable.
    """
    try:
        deals = mt5.history_deals_get(position=pos.ticket)
        if deals:
            for d in deals:
                if d.entry == mt5.DEAL_ENTRY_IN and d.symbol == symbol:
                    return float(d.price)
    except Exception:
        pass
    return float(pos.price_open)


def _check_break_even(pos, symbol, profit_points, point, symbol_info):
    """Move SL to entry price + padding once profit threshold is reached."""
    if pos.ticket in _break_even_tickets:
        return  # Already at break-even

    # Calculate actual TP distance if set (dynamic LLM/ATR target)
    tp_points = 0
    if pos.tp:
        if pos.type == mt5.ORDER_TYPE_BUY:
            tp_points = (pos.tp - pos.price_open) / point
        else:
            tp_points = (pos.price_open - pos.tp) / point

    min_trigger = 30 if config.is_fx(symbol) else 100

    # Break-even trigger: Grade-Aware Dynamic Threshold
    # M4: 70% TP (Memberi ruang nafas fluktuasi shock, mengunci profit bila mencapai 70% target)
    # Grade S: 65% TP (Give breathing room to swing)
    # Grade B / Defensive / Vacuum Extension (>= 2.0R): 35% TP (Fast defensive lock)
    # Grade A+/A: 50% TP (Standard)
    is_m4 = "SYSTEM" in (getattr(pos, "comment", "") or "").upper()
    grade = str(_ticket_setup_grades.get(pos.ticket, "GRADE_A")).upper()

    # Hitung SL points awal untuk evaluasi R:R aktual
    init_sl_pts = _original_sl.get(pos.ticket, 0) or (abs(pos.sl - pos.price_open) / point if pos.sl else 0)
    # Deteksi apakah target TP terdorong jauh ke area kehampaan (Vacuum / Stretched TP >= 2.0R)
    is_vacuum_or_stretched = bool(tp_points > 0 and init_sl_pts > 0 and (tp_points / init_sl_pts) >= 2.0)

    if "GRADE_S" in grade:
        bep_tp_ratio = 0.65
    elif "GRADE_B" in grade or "REDUCED" in grade or is_vacuum_or_stretched:
        bep_tp_ratio = 0.35
    elif is_m4:
        bep_tp_ratio = getattr(config, "M4_BREAK_EVEN_TRIGGER_TP_PCT", 0.70)
    else:
        bep_tp_ratio = config.BREAK_EVEN_TRIGGER_TP_PCT

    if tp_points > 0:
        be_trigger = max(min_trigger, int(tp_points * bep_tp_ratio))
    else:
        sl_points = init_sl_pts
        if sl_points > 0:
            be_mult = 0.35 if ("GRADE_B" in grade or "REDUCED" in grade or is_vacuum_or_stretched) else config.BREAK_EVEN_TRIGGER_SL_MULT
            be_trigger = max(int(sl_points * be_mult), min_trigger)
        else:
            be_trigger = config.break_even_trigger_for(symbol)

    # Hitung padding dinamis yang menutupi komisi round-trip broker (deal IN + deal OUT)
    # agar saat terkena BEP, net profit setelah dikurangi komisi broker benar-benar >= +$0.00 USD.
    comm_pad_pts = 0
    try:
        usd_per_pt = get_usd_per_point(symbol, pos.volume)
        deals = mt5.history_deals_get(position=pos.ticket)
        total_comm = 0.0
        if deals:
            for d in deals:
                if d.entry == mt5.DEAL_ENTRY_IN:
                    # Ambil komisi deal IN lalu kalikan 2 untuk estimasi total round-trip
                    total_comm = abs(getattr(d, "commission", 0.0) or 0.0) * 2.0
                    break
        if total_comm <= 0.0:
            total_comm = 6.0 * pos.volume  # Fallback standar ECN: $6/lot round-trip

        # Buffer cuan tambahan di atas komisi (Pocket Profit agar BEP tetap menghasilkan untung hijau)
        if config.is_crypto(symbol):
            extra_cuan_pts = 800
        elif config.is_fx(symbol):
            extra_cuan_pts = 15  # ~1.5 pips cuan bersih di atas komisi
        else:
            extra_cuan_pts = 35  # ~35 pts ($0.35) cuan bersih di XAU

        if usd_per_pt > 0:
            import math
            comm_pad_pts = int(math.ceil(total_comm / usd_per_pt)) + extra_cuan_pts
        else:
            comm_pad_pts = extra_cuan_pts
    except Exception:
        comm_pad_pts = 15

    be_padding = max(config.break_even_padding_for(symbol), comm_pad_pts)
    if profit_points < be_trigger:
        return

    entry_price = _get_entry_fill_price(pos, symbol)

    if pos.type == mt5.ORDER_TYPE_BUY:
        be_price = entry_price + (be_padding * point)
        # Only move if current SL is below break-even level
        if pos.sl >= be_price:
            _break_even_tickets.add(pos.ticket)
            _save_state(_partial_closed_tickets, _break_even_tickets, _trailing_extremes)
            return
    else:  # SELL
        be_price = entry_price - (be_padding * point)
        if pos.sl != 0 and pos.sl <= be_price:
            _break_even_tickets.add(pos.ticket)
            _save_state(_partial_closed_tickets, _break_even_tickets, _trailing_extremes)
            return

    be_price = round(be_price, symbol_info.digits)

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": pos.ticket,
        "sl": be_price,
        "tp": pos.tp,
        "magic": config.MAGIC_NUMBER,
    }

    result = mt5.order_send(request)
    if is_order_success(result):
        _break_even_tickets.add(pos.ticket)
        _save_state(_partial_closed_tickets, _break_even_tickets, _trailing_extremes)
        print(f"\r\x1b[2K{UI.GREEN}[BREAK-EVEN]{UI.RST} Ticket #{pos.ticket} ({symbol}): SL dipindahkan ke entry {be_price} (padding: +{be_padding} pts)")
        try:
            tg.alert_break_even(pos.ticket, symbol, be_price)
        except Exception:
            pass
    else:
        comment = result.comment if result else "Unknown error"
        print(f"\r\x1b[2K[BE ERROR] Gagal memindahkan SL ke break-even #{pos.ticket}: {comment}")



def _get_atr_points_tf(symbol, timeframe, point):
    """
    Computes real-time ATR(14) in points for a specific timeframe (H1 vs M30).
    """
    try:
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 20)
        if rates is not None and len(rates) >= 15:
            import pandas as pd
            from ta.volatility import AverageTrueRange
            df = pd.DataFrame(rates)
            atr_series = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
            atr_val = atr_series.iloc[-1]
            if not pd.isna(atr_val) and atr_val > 0 and point > 0:
                return int(atr_val / point)
    except Exception:
        pass
    return 0


def _get_dynamic_atr_points(symbol, point):
    """Fallback active timeframe ATR."""
    tf = config.get_timeframe(symbol)
    return _get_atr_points_tf(symbol, tf, point)


# =============================================================================
#  TRAILING STOP (2-Stage Dynamic: H1 Breathing vs M30 Terminal Lock)
# =============================================================================
def _check_trailing_stop(pos, symbol, profit_points, current_price, point, symbol_info):
    """Trail stop loss behind price using 2-Stage Dynamic Distance:
    - Stage 1 (Swing Breathing: 65% s/d < 90% TP): Jarak 0.75x ATR H1 (Floor FX 80 pts / 8 pips)
      untuk memberikan ruang nafas luas agar trade tidak mudah ter-wick keluar menuju TP2.
    - Stage 2 (Terminal Lock: >= 90% TP): Jarak 0.50x ATR M30 (Floor FX 30 pts / 3 pips)
      untuk mengunci cuan 90% secara ketat di pucuk sebelum reversal mendadak.
    """
    # Jarak target TP posisi (jika ada) untuk aktivasi % TP
    tp_points = 0
    if pos.tp:
        if pos.type == mt5.ORDER_TYPE_BUY:
            tp_points = (pos.tp - pos.price_open) / point
        else:
            tp_points = (pos.price_open - pos.tp) / point

    # Jarak SL posisi (fallback tanpa TP). Pakai SL ORIGINAL
    if pos.sl:
        sl_points = _original_sl.get(pos.ticket, 0) or (abs(pos.sl - pos.price_open) / point)
    else:
        sl_points = 0

    min_act = 30 if config.is_fx(symbol) else 100

    grade = _ticket_setup_grades.get(pos.ticket, "GRADE_A")
    if "GRADE_S" in grade:
        act_tp_pct = 0.75
    elif "GRADE_B" in grade:
        act_tp_pct = 0.50
    else:
        act_tp_pct = config.TRAILING_ACTIVATION_TP_PCT

    # Activation GLOBAL % TP (fallback SL-based kalau posisi tanpa TP)
    if tp_points > 0:
        activation = max(int(tp_points * act_tp_pct), min_act)
        tp_progress = profit_points / tp_points if tp_points > 0 else 0.0
    elif sl_points > 0:
        activation = max(int(sl_points * config.TRAILING_ACTIVATION_SL_MULT), min_act)
        tp_progress = profit_points / (sl_points * 2.0) if sl_points > 0 else 0.0
    else:
        activation = min_act
        tp_progress = 0.0

    # Evaluasi 2-Stage Dynamic Trailing Distance:
    is_terminal = (tp_progress >= getattr(config, "TRAILING_TERMINAL_TP_PCT", 0.90))

    if config.is_fx(symbol):
        if "GRADE_S" in grade:
            if is_terminal:
                atr_tf = mt5.TIMEFRAME_M30
                atr_pts = _get_atr_points_tf(symbol, atr_tf, point)
                dist_mult = 0.75
                min_dist_pts = 60
                stage_label = "GRADE-S-TERMINAL"
            else:
                atr_tf = mt5.TIMEFRAME_H1
                atr_pts = _get_atr_points_tf(symbol, atr_tf, point)
                dist_mult = 1.25
                min_dist_pts = 120  # 12 pips FX floor
                stage_label = "GRADE-S-BREATHING"
        elif "GRADE_B" in grade:
            atr_tf = mt5.TIMEFRAME_M30
            atr_pts = _get_atr_points_tf(symbol, atr_tf, point)
            dist_mult = 0.40
            min_dist_pts = 30
            stage_label = "GRADE-B-TIGHT"
        else:
            if is_terminal:
                # Stage 2: Terminal Tightening (ATR M30 lock)
                atr_tf = mt5.TIMEFRAME_M30
                atr_pts = _get_atr_points_tf(symbol, atr_tf, point)
                dist_mult = 0.50
                min_dist_pts = getattr(config, "TRAILING_DISTANCE_MIN_POINTS_TERMINAL_FX", 30)
                stage_label = "TERMINAL-M30"
            else:
                # Stage 1: Swing Breathing (ATR H1 breathing)
                atr_tf = mt5.TIMEFRAME_H1
                atr_pts = _get_atr_points_tf(symbol, atr_tf, point)
                dist_mult = getattr(config, "TRAILING_DISTANCE_ATR_MULT_H1", 0.75)
                min_dist_pts = getattr(config, "TRAILING_DISTANCE_MIN_POINTS_FX", 80)
                stage_label = "SWING-H1"
    elif config.is_crypto(symbol):
        atr_pts = _get_dynamic_atr_points(symbol, point)
        dist_mult = getattr(config, "TRAILING_DISTANCE_ATR_MULT_BTC", 0.5)
        min_dist_pts = 0
        stage_label = "CRYPTO"
    else:  # Gold (XAU)
        atr_pts = _get_dynamic_atr_points(symbol, point)
        dist_mult = getattr(config, "TRAILING_DISTANCE_ATR_MULT_XAU", 0.5)
        min_dist_pts = getattr(config, "TRAILING_DISTANCE_MIN_POINTS_XAU", 100)
        stage_label = "XAU"

    if atr_pts > 0:
        trail_distance = max(int(atr_pts * dist_mult), 1) * point
    else:
        _, _, _, fallback_dist, _ = config.trailing_activation_params_for(symbol)
        trail_distance = fallback_dist * point

    # Floor absolut jarak trailing
    min_dist_price = min_dist_pts * point
    if not config.is_crypto(symbol):
        trail_distance = max(trail_distance, min_dist_price)

    # Track the extreme price seen since entry.
    ticket = pos.ticket
    if pos.type == mt5.ORDER_TYPE_BUY:
        extreme = max(_trailing_extremes.get(ticket, pos.price_open), current_price)
        trail_ref = extreme
    else:  # SELL
        extreme = min(_trailing_extremes.get(ticket, pos.price_open), current_price)
        trail_ref = extreme

    if extreme != _trailing_extremes.get(ticket):
        _trailing_extremes[ticket] = extreme
        _save_state(_partial_closed_tickets, _break_even_tickets, _trailing_extremes)

    if profit_points < activation:
        return

    if pos.type == mt5.ORDER_TYPE_BUY:
        new_sl = trail_ref - trail_distance
        new_sl = round(new_sl, symbol_info.digits)
        # Only move SL up, never down
        if pos.sl >= new_sl:
            return
    else:  # SELL
        new_sl = trail_ref + trail_distance
        new_sl = round(new_sl, symbol_info.digits)
        # Only move SL down, never up
        if pos.sl != 0 and pos.sl <= new_sl:
            return

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": symbol,
        "position": pos.ticket,
        "sl": new_sl,
        "tp": pos.tp,
        "magic": config.MAGIC_NUMBER,
    }

    result = mt5.order_send(request)
    if is_order_success(result):
        _trailing_active_tickets.add(pos.ticket)
        _save_state(_partial_closed_tickets, _break_even_tickets, _trailing_extremes)
        dist_pts = int(trail_distance / point) if point > 0 else 0
        print(f"\r\x1b[2K{UI.GREEN}[TRAILING STOP | {stage_label}]{UI.RST} Ticket #{pos.ticket} ({symbol}): SL digeser ke {new_sl} (profit: +{profit_points:.0f} pts, dist: {dist_pts} pts ATR)")
    else:
        comment = result.comment if result else "Unknown error"
        print(f"\r\x1b[2K[TRAIL ERROR] Gagal menggeser SL #{pos.ticket}: {comment}")


# =============================================================================
#  REAL-TIME THESIS FAILURE INVALIDATION ENGINE (Pending Orders Auto-Cancel)
# =============================================================================

def audit_pending_orders_thesis():
    """
    Real-Time Thesis Failure Invalidation Engine for Active Pending Orders.
    Monitors all pending orders in MT5. An order is cancelled ONLY if:
      (1) Price has severely penetrated past the structural invalidation level:
          - BUY: M15 close < (order_sl if order_sl > 0 else anchor - 0.50x ATR)
          - SELL: M15 close > (order_sl if order_sl > 0 else anchor + 0.50x ATR)
      (2) Systemic CSM currency flow inverts violently against the order (|delta| > 0.35 opposing)
      (3) Confirmed Structural Stage Breakdown/Breakout in MSE:
          - BUY: 'FLOOR_BREAKDOWN' in market_state
          - SELL: 'CEILING_BREAKOUT' in market_state
    NOTE: Minor MSE bias fluctuations or normal retest wicks/rejections (FLOOR_REJECTION / CEILING_REJECTION)
    MUST NOT cancel pending orders (fixes bug where CEILING_REJECTION cancelled SELL limit orders).
    """
    try:
        orders = mt5.orders_get()
        if not orders:
            return

        for ord_item in orders:
            # Only manage bot's own orders
            if ord_item.magic != config.MAGIC_NUMBER:
                continue

            # Check if pending order
            if ord_item.type not in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT,
                                     mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP):
                continue

            sym = ord_item.symbol
            si = mt5.symbol_info(sym)
            if not si or not si.point:
                continue
            pt = si.point

            # 1. Fetch MSE directive
            from src.analytics.macro_strategic_engine import macro_strategic_engine
            strat_dir = macro_strategic_engine.get_directive(sym)
            if not strat_dir:
                continue

            m_state = strat_dir.market_state or ""

            # 2. Fetch latest M15 rates
            rates_m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 3)
            last_m15_close = rates_m15[-1]['close'] if (rates_m15 is not None and len(rates_m15) > 0) else ord_item.price_open
            atr_pts = _get_dynamic_atr_points(sym, pt)
            atr_val = (atr_pts * pt) if atr_pts > 0 else (20 * pt)

            # 3. Fetch CSM Net Delta
            csm_delta = 0.0
            try:
                from src.analytics.currency_strength import get_csm_delta_for_symbol
                csm_delta = get_csm_delta_for_symbol(sym)
            except Exception:
                csm_delta = 0.0

            cancel_reason = None
            # Helper to extract numeric values safely from live MT5 struct or test mocks
            def _safe_num(val, default=0.0):
                if val is None:
                    return default
                if isinstance(val, (int, float)):
                    return float(val)
                if 'Mock' in type(val).__name__:
                    return default
                try:
                    return float(val)
                except Exception:
                    return default

            is_m4_order = "SYSTEM" in (getattr(ord_item, "comment", "") or "").upper()
            open_px = _safe_num(ord_item.price_open, 0.0)
            sl_px = _safe_num(getattr(ord_item, 'sl', None), 0.0)
            tp_px = _safe_num(getattr(ord_item, 'tp', None), 0.0)
            curr_market_px = _safe_num(getattr(si, 'bid', None) if ord_item.type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP) else getattr(si, 'ask', None), 0.0)
            if curr_market_px <= 0.0:
                curr_market_px = _safe_num(last_m15_close, open_px)

            # Macro bias alignment check (aligned macro overrides moderate CSM opposition)
            bias_score = _safe_num(getattr(strat_dir, 'macro_bias_score', 0.0), 0.0)
            is_macro_aligned_buy = (bias_score >= 0.35)
            is_macro_aligned_sell = (bias_score <= -0.35)

            # 4. Check Thesis Invalidation for BUY Pending Orders
            csm_opposed_thresh = getattr(config, "PENDING_CSM_OPPOSED_THRESHOLD", 1.0)
            enable_csm_cancel = getattr(config, "ENABLE_PENDING_CSM_CANCEL", False)
            if ord_item.type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP):
                # Structural Invalidation Floor: use SL if defined, else anchor - 0.50x ATR
                inv_floor = sl_px if (sl_px > 0 and sl_px < open_px) else (open_px - (0.50 * atr_val))
                if last_m15_close < inv_floor:
                    cancel_reason = f"M15 close ({last_m15_close:.5f}) penetrated invalidation floor ({inv_floor:.5f})"
                elif ord_item.type == mt5.ORDER_TYPE_BUY_LIMIT and tp_px > open_px and curr_market_px >= (open_px + 0.75 * (tp_px - open_px)):
                    cancel_reason = f"Target proximity expiration: market ({curr_market_px:.5f}) reached >=75% of TP ({tp_px:.5f}) without fill"
                elif enable_csm_cancel and not is_m4_order and csm_delta <= -csm_opposed_thresh and not is_macro_aligned_buy:
                    cancel_reason = f"Systemic CSM Flow reversed strongly to Bearish ({csm_delta:+.2f} <= -{csm_opposed_thresh:.2f})"
                elif not is_m4_order and "FLOOR_BREAKDOWN" in m_state:
                    cancel_reason = f"MSE Structural Floor Breakdown ({m_state})"

            # 5. Check Thesis Invalidation for SELL Pending Orders
            elif ord_item.type in (mt5.ORDER_TYPE_SELL_LIMIT, mt5.ORDER_TYPE_SELL_STOP):
                # Structural Invalidation Ceiling: use SL if defined, else anchor + 0.50x ATR
                inv_ceiling = sl_px if (sl_px > 0 and sl_px > open_px) else (open_px + (0.50 * atr_val))
                if last_m15_close > inv_ceiling:
                    cancel_reason = f"M15 close ({last_m15_close:.5f}) penetrated invalidation ceiling ({inv_ceiling:.5f})"
                elif ord_item.type == mt5.ORDER_TYPE_SELL_LIMIT and tp_px > 0 and tp_px < open_px and curr_market_px <= (open_px - 0.75 * (open_px - tp_px)):
                    cancel_reason = f"Target proximity expiration: market ({curr_market_px:.5f}) reached >=75% of TP ({tp_px:.5f}) without fill"
                elif enable_csm_cancel and not is_m4_order and csm_delta >= +csm_opposed_thresh and not is_macro_aligned_sell:
                    cancel_reason = f"Systemic CSM Flow reversed strongly to Bullish ({csm_delta:+.2f} >= +{csm_opposed_thresh:.2f})"
                elif not is_m4_order and "CEILING_BREAKOUT" in m_state:
                    cancel_reason = f"MSE Structural Ceiling Breakout ({m_state})"

            # 6. Cancel order if thesis failed
            if cancel_reason:
                if not getattr(config, "ENABLE_PENDING_THESIS_AUDIT", True):
                    print(f"\n{UI.YELLOW}[THESIS SHADOW OBSERVER]{UI.RST} Pending Order #{ord_item.ticket} ({sym}) SEHARUSNYA DIBATALKAN: {cancel_reason} (Bypass Aktif -> Order Dibiarkan)")
                    logger.info(f"[THESIS SHADOW OBSERVER] Pending Order #{ord_item.ticket} ({sym}) SEHARUSNYA DIBATALKAN: {cancel_reason} (Bypass Aktif -> Order Dibiarkan)")
                    record_thesis_observer_event(ord_item.ticket, sym, cancel_reason)
                    continue

                req = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": ord_item.ticket,
                    "magic": config.MAGIC_NUMBER,
                    "comment": "Thesis Failure Cancel"
                }
                res = mt5.order_send(req)
                if is_order_success(res):
                    print(f"\n{UI.RED}[THESIS FAILURE CANCEL]{UI.RST} Pending Order #{ord_item.ticket} ({sym}) Dibatalkan: {cancel_reason}")
                    logger.info(f"[THESIS FAILURE CANCEL] Pending Order #{ord_item.ticket} ({sym}) Dibatalkan: {cancel_reason}")
                    try:
                        tg.alert_trade_aborted(
                            symbol=sym,
                            signal="BUY" if ord_item.type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP) else "SELL",
                            reason_code="THESIS_FAILURE_INVALIDATED",
                            details=cancel_reason,
                            confidence=0.0,
                            models="Thesis Failure Engine"
                        )
                    except Exception:
                        pass
    except Exception as e:
        pass

