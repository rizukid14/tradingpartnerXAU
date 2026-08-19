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
import config
from config import mt5
from src.core.cli_theme import UI
from src.core.mt5_connector import is_order_success, get_usd_per_point
from src.core import telegram_alerts as tg


STATE_FILE = os.path.join(config.DATA_DIR, "position_manager_state.json")


def _load_state():
    """Load persisted tickets from disk. Returns (partial_set, be_set, extremes, original_sl, trail_active)."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            partial = set(int(t) for t in data.get("partial_closed_tickets", []))
            be = set(int(t) for t in data.get("break_even_tickets", []))
            trail_active = set(int(t) for t in data.get("trailing_active_tickets", []))
            extremes = {int(k): float(v) for k, v in data.get("trailing_extremes", {}).items()}
            original_sl = {int(k): float(v) for k, v in data.get("original_sl_points", {}).items()}
            return partial, be, extremes, original_sl, trail_active
    except Exception as e:
        print(f"[POS MANAGER WARNING] Gagal memuat position_manager_state.json: {e}")
    return set(), set(), {}, {}, set()


def _save_state(partial_set, be_set, extremes, original_sl=None, trail_active=None):
    """Persist tickets to disk so restart can recover state."""
    if original_sl is None:
        original_sl = _original_sl  # module global, di-resolve saat dipanggil
    if trail_active is None:
        trail_active = _trailing_active_tickets
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "partial_closed_tickets": sorted(int(t) for t in partial_set),
                "break_even_tickets": sorted(int(t) for t in be_set),
                "trailing_active_tickets": sorted(int(t) for t in trail_active),
                "trailing_extremes": {str(k): v for k, v in extremes.items()},
                "original_sl_points": {str(k): v for k, v in original_sl.items()},
            }, f)
    except Exception as e:
        print(f"[POS MANAGER WARNING] Gagal menyimpan position_manager_state.json: {e}")


# Module-level state, loaded once at import (survives within a process)
_partial_closed_tickets, _break_even_tickets, _trailing_extremes, _original_sl, _trailing_active_tickets = _load_state()


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

        # --- PARTIAL CLOSE at TP1 ---
        if config.PARTIAL_CLOSE_ENABLED:
            _check_partial_close(pos, symbol, profit_points, symbol_info)

        # --- BREAK-EVEN CHECK ---
        if config.BREAK_EVEN_ENABLED:
            _check_break_even(pos, symbol, profit_points, point, symbol_info)

        # --- TRAILING STOP CHECK ---
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

    # Break-even trigger (mode-aware, 15 Agustus - pindah ke PURE % TP):
    # - LLM mode: BEP aktif saat profit >= 65% TP (BREAK_EVEN_TRIGGER_TP_PCT).
    #   Alasan pindah dari SL-based (1x SL): SL-based cacat di dua ujung untuk trade
    #   R:R rendah (1.25-1.5, gate R:R min 1.25) - 1x SL untuk R:R 1.25 = 80% TP
    #   (kecepetan) dan cap 50% TP untuk R:R 3:1 = 1.5x SL (telat). Pure % TP selalu
    #   proporsional: R:R 2:1 -> 1.3x SL, R:R 1.25 -> 0.81x SL (pas, bukan kecepetan).
    #   Posisi tanpa TP -> fallback SL-based (1x SL) biar tetap ada proteksi.
    # - ATR-Based mode: 50% TP aktual (di mode ini TP = 2x SL, jadi 50% TP = 1x SL).
    if config.sltp_mode_for(symbol) == "LLM":
        if tp_points > 0:
            be_trigger = max(min_trigger, int(tp_points * config.BREAK_EVEN_TRIGGER_TP_PCT))
        else:
            sl_points = _original_sl.get(pos.ticket, 0) or (abs(pos.sl - pos.price_open) / point)
            if sl_points > 0:
                be_trigger = max(int(sl_points * config.BREAK_EVEN_TRIGGER_SL_MULT), min_trigger)
            else:
                be_trigger = config.break_even_trigger_for(symbol)
    elif tp_points > 0:
        be_trigger = max(min_trigger, int(tp_points * 0.50))
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


def _calculate_progressive_tp_lock_points(profit_points, tp_points):
    """
    Progressive Dynamic Trailing Stop Lock Curve:
    - 50% TP profit -> kunci 25% TP (langsung melampaui level BEP)
    - 60% TP profit -> kunci 40% TP
    - 70% TP profit -> kunci 55% TP
    - 80% TP profit -> kunci 70% TP
    - >=90% TP profit -> kunci 85% TP (ketat mendekati TP)
    Interpolasi mulus antar tingkat.
    """
    if tp_points <= 0 or profit_points < (tp_points * 0.50):
        return 0.0

    ratio = profit_points / tp_points
    if ratio >= 0.90:
        lock_pct = 0.85 + min(ratio - 0.90, 0.08)  # 90% profit -> 85% lock, 95% -> 90% lock
    elif ratio >= 0.80:
        # Interpolasi 70% -> 85% saat profit 80% -> 90%
        lock_pct = 0.70 + ((ratio - 0.80) / 0.10) * 0.15
    elif ratio >= 0.70:
        # Interpolasi 55% -> 70% saat profit 70% -> 80%
        lock_pct = 0.55 + ((ratio - 0.70) / 0.10) * 0.15
    elif ratio >= 0.60:
        # Interpolasi 40% -> 55% saat profit 60% -> 70%
        lock_pct = 0.40 + ((ratio - 0.60) / 0.10) * 0.15
    else:  # 0.50 <= ratio < 0.60
        # Interpolasi 25% -> 40% saat profit 50% -> 60%
        lock_pct = 0.25 + ((ratio - 0.50) / 0.10) * 0.15

    return lock_pct * tp_points


# =============================================================================
#  TRAILING STOP (from XAU-60 trade_executor.py)
# =============================================================================
def _check_trailing_stop(pos, symbol, profit_points, current_price, point, symbol_info):
    """Trail stop loss behind price using dynamic mode-aware multipliers.

    Referensi multiplier (13 Agustus):
    - LLM mode: jarak SL posisi (thesis-relative, nyambung sama struktur SL LLM)
    - ATR-Based mode: ATR (konsisten, karena SL/TP ATR mode juga turunan ATR)
    """
    atr_points = _get_dynamic_atr_points(symbol, point)

    # Hitung jarak target TP posisi (jika ada) untuk aktivasi adaptif & progress calculation
    tp_points = 0
    if pos.tp:
        if pos.type == mt5.ORDER_TYPE_BUY:
            tp_points = (pos.tp - pos.price_open) / point
        else:
            tp_points = (pos.price_open - pos.tp) / point

    # Jarak SL posisi (struktur LLM di mode LLM, atau hasil gate ATR di mode ATR-Based).
    # Mode LLM: pakai SL ORIGINAL (sebelum BE/trailing geser) biar referensi stabil.
    if pos.sl:
        sl_points = _original_sl.get(pos.ticket, 0) or (abs(pos.sl - pos.price_open) / point)
    else:
        sl_points = 0

    act_mult, dist_mult, fallback_act, fallback_dist, act_cap = config.trailing_activation_params_for(symbol)

    if atr_points > 0:
        activation = min(int(atr_points * act_mult), act_cap)
        distance = int(atr_points * dist_mult)
    else:
        activation = fallback_act
        distance = fallback_dist

    min_act = 30 if config.is_fx(symbol) else 100

    # Mode-aware activation:
    # - LLM mode: trailing aktif saat profit >= 58% TP (TRAILING_ACTIVATION_TP_PCT)
    # - ATR-Based mode: TP-adaptive 60% TP
    if config.sltp_mode_for(symbol) == "LLM":
        if tp_points > 0:
            activation = max(int(tp_points * config.TRAILING_ACTIVATION_TP_PCT), min_act)
        elif sl_points > 0:
            activation = max(int(sl_points * config.TRAILING_ACTIVATION_SL_MULT), min_act)
    elif tp_points > 0 and not config.is_crypto(symbol):
        activation = int(tp_points * 0.60)

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

    # ---- Progressive distance ----
    # Distance mengecil linear dari START (longgar saat baru aktivasi) ke END
    # (ketat saat mendekati TP). Progress dihitung dari posisi profit terhadap
    # TP posisi (atau fallback: 2x activation).
    # Referensi multiplier (13 Agustus):
    # - LLM mode: SL posisi (thesis-relative, nyambung sama struktur LLM)
    # - ATR-Based mode: ATR (konsisten dengan SL/TP ATR mode)
    # Fix bug progress_ref: pakai tp_points langsung (bukan max(tp, 2x activation)
    # yang selalu 1.2x TP) supaya distance beneran mencapai end_mult tepat di TP.
    llm_mode = config.sltp_mode_for(symbol) == "LLM"

    if llm_mode and sl_points > 0:
        # LLM mode: interpolasi 1.2 -> 0.4 x SL (floor 0.3). Selalu progressive
        # (termasuk BTC) karena struktur SL LLM memang thesis-based. Dilonggarkan
        # 15 Agustus (dari 0.8 -> 0.3): distance awal 1.2x SL bikin pullback normal
        # gak langsung kena trailing; baru ketat mendekati TP.
        start_mult = config.TRAILING_DISTANCE_START_SL_MULT
        end_mult = config.TRAILING_DISTANCE_END_SL_MULT
        min_mult = config.TRAILING_DISTANCE_MIN_SL_MULT
        progress_ref = tp_points if tp_points > 0 else activation * 2
        progress = min(max((profit_points - activation) / (progress_ref - activation), 0.0), 1.0) if progress_ref > activation else 0.0
        dynamic_mult = max(start_mult - (start_mult - end_mult) * progress, min_mult)
        trail_distance = sl_points * dynamic_mult * point
    elif config.is_crypto(symbol):
        trail_distance = distance * point
    else:
        if config.is_fx(symbol):
            start_mult = getattr(config, "TRAILING_DISTANCE_START_ATR_MULT_FX", 0.8)
            end_mult = getattr(config, "TRAILING_DISTANCE_END_ATR_MULT_FX", 0.3)
            min_mult = getattr(config, "TRAILING_DISTANCE_MIN_ATR_MULT_FX", 0.2)
        else:
            start_mult = getattr(config, "TRAILING_DISTANCE_START_ATR_MULT_XAU", 1.2)
            end_mult = getattr(config, "TRAILING_DISTANCE_END_ATR_MULT_XAU", 0.4)
            min_mult = getattr(config, "TRAILING_DISTANCE_MIN_ATR_MULT_XAU", 0.3)

        progress_ref = tp_points if tp_points > 0 else activation * 2
        progress = min(max((profit_points - activation) / (progress_ref - activation), 0.0), 1.0) if progress_ref > activation else 0.0

        # Interpolasi linear start_mult -> end_mult, lalu floor ke min_mult
        dynamic_mult = start_mult - (start_mult - end_mult) * progress
        dynamic_mult = max(dynamic_mult, min_mult)

    # Floor absolut jarak trailing (anti noise & spread squeeze saat SL tipis / TP lock mepet)
    min_dist_pts = getattr(config, "TRAILING_DISTANCE_MIN_POINTS_FX", 25) if config.is_fx(symbol) else getattr(config, "TRAILING_DISTANCE_MIN_POINTS_XAU", 100)
    min_dist_price = min_dist_pts * point

    if not config.is_crypto(symbol):
        trail_distance = max(trail_distance, min_dist_price)

    if pos.type == mt5.ORDER_TYPE_BUY:
        new_sl = trail_ref - trail_distance
        # Progressive TP-lock: pastikan SL setidaknya mengunci target % TP sesuai progress
        if tp_points > 0:
            tp_locked_pts = _calculate_progressive_tp_lock_points(profit_points, tp_points)
            if tp_locked_pts > 0:
                tp_lock_sl = pos.price_open + (tp_locked_pts * point)
                # Cap tp_lock_sl agar tetap menyisakan breathing room min_dist_pts dari extreme price
                if not config.is_crypto(symbol):
                    tp_lock_sl = min(tp_lock_sl, trail_ref - min_dist_price)
                new_sl = max(new_sl, tp_lock_sl)
        new_sl = round(new_sl, symbol_info.digits)
        # Only move SL up, never down
        if pos.sl >= new_sl:
            return
    else:  # SELL
        new_sl = trail_ref + trail_distance
        # Progressive TP-lock: pastikan SL setidaknya mengunci target % TP sesuai progress
        if tp_points > 0:
            tp_locked_pts = _calculate_progressive_tp_lock_points(profit_points, tp_points)
            if tp_locked_pts > 0:
                tp_lock_sl = pos.price_open - (tp_locked_pts * point)
                # Cap tp_lock_sl agar tetap menyisakan breathing room min_dist_pts dari extreme price
                if not config.is_crypto(symbol):
                    tp_lock_sl = max(tp_lock_sl, trail_ref + min_dist_price)
                new_sl = min(new_sl, tp_lock_sl)
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
        if config.is_crypto(symbol) and not (config.sltp_mode_for(symbol) == "LLM" and sl_points > 0):
            print(f"\r\x1b[2K{UI.GREEN}[TRAILING STOP]{UI.RST} Ticket #{pos.ticket} ({symbol}): SL digeser ke {new_sl} (profit: +{profit_points:.0f} pts, dist: {distance} pts)")
        else:
            ref_label = "SL" if (config.sltp_mode_for(symbol) == "LLM" and sl_points > 0) else "ATR"
            print(f"\r\x1b[2K{UI.GREEN}[TRAILING STOP]{UI.RST} Ticket #{pos.ticket} ({symbol}): SL digeser ke {new_sl} (profit: +{profit_points:.0f} pts, dist: {dist_pts} pts, {dynamic_mult:.2f}x {ref_label})")
    else:
        comment = result.comment if result else "Unknown error"
        print(f"\r\x1b[2K[TRAIL ERROR] Gagal menggeser SL #{pos.ticket}: {comment}")

