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
from datetime import datetime
from zoneinfo import ZoneInfo
import config
from config import mt5
from src.core.cli_theme import UI
from src.core.mt5_connector import is_order_success, get_usd_per_point
from src.core import telegram_alerts as tg

WIB = ZoneInfo("Asia/Jakarta")

STATE_FILE = os.path.join(config.DATA_DIR, "position_manager_state.json")


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

        # --- 3. PARTIAL CLOSE at TP1 ---
        if config.PARTIAL_CLOSE_ENABLED:
            _check_partial_close(pos, symbol, profit_points, symbol_info)

        # --- 4. BREAK-EVEN CHECK ---
        if config.BREAK_EVEN_ENABLED:
            _check_break_even(pos, symbol, profit_points, point, symbol_info)

        # --- 5. TRAILING STOP CHECK ---
        if config.TRAILING_STOP_ENABLED:
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
    # Grade S: 65% TP (Give breathing room to swing)
    # Grade B: 35% TP (Fast defensive lock)
    # Grade A+/A: 50% TP (Standard)
    grade = _ticket_setup_grades.get(pos.ticket, "GRADE_A")
    if "GRADE_S" in grade:
        bep_tp_ratio = 0.65
    elif "GRADE_B" in grade:
        bep_tp_ratio = 0.35
    else:
        bep_tp_ratio = config.BREAK_EVEN_TRIGGER_TP_PCT

    if tp_points > 0:
        be_trigger = max(min_trigger, int(tp_points * bep_tp_ratio))
    else:
        sl_points = _original_sl.get(pos.ticket, 0) or (abs(pos.sl - pos.price_open) / point)
        if sl_points > 0:
            be_trigger = max(int(sl_points * config.BREAK_EVEN_TRIGGER_SL_MULT), min_trigger)
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
    Monitors all pending orders in MT5. If the underlying market structure fails
    (e.g., M15 candle closes back inside the chamber across C1/F1, MSE state flips to REJECTION,
    or CSM inverts sharply), the pending order is cancelled immediately to prevent catching a falling knife.
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

            c1 = strat_dir.immediate_ceiling_c1
            f1 = strat_dir.immediate_floor_f1
            m_state = strat_dir.market_state
            prim_dir = strat_dir.primary_execution_directive
            bias_score = strat_dir.macro_bias_score

            # 2. Fetch latest M15 rates
            rates_m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 3)
            last_m15_close = rates_m15[-1]['close'] if (rates_m15 is not None and len(rates_m15) > 0) else ord_item.price_open
            atr_pts = _get_dynamic_atr_points(sym, pt)
            atr_val = (atr_pts * pt) if atr_pts > 0 else (20 * pt)

            cancel_reason = None

            # 3. Check Thesis Invalidation for BUY Pending Orders
            if ord_item.type in (mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP):
                # Condition A: Re-entry breakdown below C1 - 0.25x ATR (if it was a breakout retest above C1)
                if c1 > 0 and ord_item.price_open >= c1 - (0.15 * atr_val):
                    if last_m15_close < c1 - (0.25 * atr_val):
                        cancel_reason = f"M15 close ({last_m15_close:.5f}) broke back inside chamber below C1 ({c1:.5f})"
                # Condition B: MSE flipped to Bearish Pullback or Ceiling Rejection
                if bias_score <= -0.40 or "HUNT_SELL" in prim_dir or "REJECTION" in m_state:
                    cancel_reason = f"MSE flipped to Bearish ({m_state} / {prim_dir})"

            # 4. Check Thesis Invalidation for SELL Pending Orders
            elif ord_item.type in (mt5.ORDER_TYPE_SELL_LIMIT, mt5.ORDER_TYPE_SELL_STOP):
                # Condition A: Re-entry breakout above F1 + 0.25x ATR (if it was a breakdown retest below F1)
                if f1 > 0 and ord_item.price_open <= f1 + (0.15 * atr_val):
                    if last_m15_close > f1 + (0.25 * atr_val):
                        cancel_reason = f"M15 close ({last_m15_close:.5f}) broke back inside chamber above F1 ({f1:.5f})"
                # Condition B: MSE flipped to Bullish Expansion or Floor Rejection
                if bias_score >= 0.40 or "HUNT_BUY" in prim_dir or "REJECTION" in m_state:
                    cancel_reason = f"MSE flipped to Bullish ({m_state} / {prim_dir})"

            # 5. Cancel order if thesis failed
            if cancel_reason:
                req = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": ord_item.ticket,
                    "magic": config.MAGIC_NUMBER,
                    "comment": "Thesis Failure Cancel"
                }
                res = mt5.order_send(req)
                if is_order_success(res):
                    print(f"\r\x1b[2K{UI.RED}[THESIS FAILURE CANCEL]{UI.RST} Pending Order #{ord_item.ticket} ({sym}) Dibatalkan: {cancel_reason}")
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

