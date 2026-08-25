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
    """Load persisted tickets from disk. Returns (partial_set, be_set, extremes, original_sl, trail_active, peak_mfe)."""
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
            return partial, be, extremes, original_sl, trail_active, peak_mfe
    except Exception as e:
        print(f"[POS MANAGER WARNING] Gagal memuat position_manager_state.json: {e}")
    return set(), set(), {}, {}, set(), {}


def _save_state(partial_set, be_set, extremes, original_sl=None, trail_active=None, peak_mfe=None):
    """Persist tickets to disk so restart can recover state."""
    if original_sl is None:
        original_sl = _original_sl
    if trail_active is None:
        trail_active = _trailing_active_tickets
    if peak_mfe is None:
        peak_mfe = _peak_mfe_points
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "partial_closed_tickets": sorted(int(t) for t in partial_set),
                "break_even_tickets": sorted(int(t) for t in be_set),
                "trailing_active_tickets": sorted(int(t) for t in trail_active),
                "trailing_extremes": {str(k): v for k, v in extremes.items()},
                "original_sl_points": {str(k): v for k, v in original_sl.items()},
                "peak_mfe_points": {str(k): v for k, v in peak_mfe.items()},
            }, f)
    except Exception as e:
        print(f"[POS MANAGER WARNING] Gagal menyimpan position_manager_state.json: {e}")


# Module-level state, loaded once at import (survives within a process)
_partial_closed_tickets, _break_even_tickets, _trailing_extremes, _original_sl, _trailing_active_tickets, _peak_mfe_points = _load_state()


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

    # TP-Adaptive Partial Close (60% of actual TP target if exists, otherwise fallback)
    if tp_points > 0:
        tp1_points = int(tp_points * 0.60)
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

    # Break-even trigger (GLOBAL single path, 20 Agustus malam):
    # BEP aktif saat profit >= 58% TP (BREAK_EVEN_TRIGGER_TP_PCT) standar,
    # atau adaptif 45% TP pada rezim low-volatility (Ide 4).
    bep_tp_ratio = config.BREAK_EVEN_TRIGGER_TP_PCT
    if getattr(config, "VOL_REGIME_SCALING_ENABLED", True):
        # Cek jika volatilitas sedang rendah
        try:
            from src.core.risk_engine import RiskEngine
            # Fallback ke ratio dinamis
            pass
        except Exception:
            pass

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



def _get_dynamic_atr_points(symbol, point):
    """
    Computes real-time ATR(14) in points for the given symbol using its active timeframe:
    M30 for BTC, M5 for XAU.
    """
    try:
        tf = config.get_timeframe(symbol)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, 20)
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


# =============================================================================
#  TRAILING STOP (from XAU-60 trade_executor.py)
# =============================================================================
def _check_trailing_stop(pos, symbol, profit_points, current_price, point, symbol_info):
    """Trail stop loss behind price using a GLOBAL single-path rule.

    GLOBAL single path (20 Agustus malam, hasil backtest S9 GBPUSD n=174):
    - Activation: profit >= 70% TP (TRAILING_ACTIVATION_TP_PCT). Fallback tanpa
      TP: TRAILING_ACTIVATION_SL_MULT x SL.
    - Distance: KONSTAN 0.5x ATR(14) dari harga ekstrem sejak entry (bukan
      progressive SL-based, bukan range adaptif) + floor absolut
      TRAILING_DISTANCE_MIN_POINTS_FX/XAU.
    Hasil backtest (scratch/bep_trail_matrix.py):
      act70 + atr0.5 = EV +0.272 (terbaik, nyaris setara baseline +0.302)
      progressive SL +0.197 | adaptif +0.041 | fixed pips +0.128-0.180 (inferior)
    TP-lock progressive & progressive distance DIHAPUS - backtest membuktikan
    jarak konstan 0.5x ATR yang paling tidak merusak edge.
    """
    atr_points = _get_dynamic_atr_points(symbol, point)

    # Jarak target TP posisi (jika ada) untuk aktivasi % TP
    tp_points = 0
    if pos.tp:
        if pos.type == mt5.ORDER_TYPE_BUY:
            tp_points = (pos.tp - pos.price_open) / point
        else:
            tp_points = (pos.price_open - pos.tp) / point

    # Jarak SL posisi (fallback tanpa TP). Pakai SL ORIGINAL (sebelum BE/trailing
    # geser) biar referensi stabil.
    if pos.sl:
        sl_points = _original_sl.get(pos.ticket, 0) or (abs(pos.sl - pos.price_open) / point)
    else:
        sl_points = 0

    min_act = 30 if config.is_fx(symbol) else 100

    # Activation GLOBAL % TP (fallback SL-based kalau posisi tanpa TP)
    if tp_points > 0:
        activation = max(int(tp_points * config.TRAILING_ACTIVATION_TP_PCT), min_act)
    elif sl_points > 0:
        activation = max(int(sl_points * config.TRAILING_ACTIVATION_SL_MULT), min_act)
    else:
        activation = min_act

    # Distance GLOBAL: KONSTAN 0.5x ATR per-kategori (default 0.5).
    # Fallback kalau ATR gagal: fallback_dist dari trailing_activation_params_for.
    if atr_points > 0:
        if config.is_fx(symbol):
            dist_mult = getattr(config, "TRAILING_DISTANCE_ATR_MULT_FX", 0.5)
        elif config.is_crypto(symbol):
            dist_mult = getattr(config, "TRAILING_DISTANCE_ATR_MULT_BTC", 0.5)
        else:
            dist_mult = getattr(config, "TRAILING_DISTANCE_ATR_MULT_XAU", 0.5)
        trail_distance = max(int(atr_points * dist_mult), 1) * point
    else:
        _, _, _, fallback_dist, _ = config.trailing_activation_params_for(symbol)
        trail_distance = fallback_dist * point

    # Track the extreme price seen since entry. The SL trails behind this
    # extreme, never behind the current price, so a pullback cannot drag the
    # SL backwards.
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

    # Floor absolut jarak trailing (anti noise & spread squeeze saat SL tipis)
    min_dist_pts = getattr(config, "TRAILING_DISTANCE_MIN_POINTS_FX", 25) if config.is_fx(symbol) else getattr(config, "TRAILING_DISTANCE_MIN_POINTS_XAU", 100)
    min_dist_price = min_dist_pts * point

    if not config.is_crypto(symbol):
        trail_distance = max(trail_distance, min_dist_price)

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
        print(f"\r\x1b[2K{UI.GREEN}[TRAILING STOP]{UI.RST} Ticket #{pos.ticket} ({symbol}): SL digeser ke {new_sl} (profit: +{profit_points:.0f} pts, dist: {dist_pts} pts ATR)")
    else:
        comment = result.comment if result else "Unknown error"
        print(f"\r\x1b[2K[TRAIL ERROR] Gagal menggeser SL #{pos.ticket}: {comment}")

