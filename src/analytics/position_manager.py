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


STATE_FILE = os.path.join(config.DATA_DIR, "position_manager_state.json")


def _load_state():
    """Load persisted tickets from disk. Returns (partial_set, be_set, extremes)."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            partial = set(int(t) for t in data.get("partial_closed_tickets", []))
            be = set(int(t) for t in data.get("break_even_tickets", []))
            extremes = {int(k): float(v) for k, v in data.get("trailing_extremes", {}).items()}
            return partial, be, extremes
    except Exception as e:
        print(f"[POS MANAGER WARNING] Gagal memuat position_manager_state.json: {e}")
    return set(), set(), {}


def _save_state(partial_set, be_set, extremes):
    """Persist tickets to disk so restart can recover state."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "partial_closed_tickets": sorted(int(t) for t in partial_set),
                "break_even_tickets": sorted(int(t) for t in be_set),
                "trailing_extremes": {str(k): v for k, v in extremes.items()},
            }, f)
    except Exception as e:
        print(f"[POS MANAGER WARNING] Gagal menyimpan position_manager_state.json: {e}")


# Module-level state, loaded once at import (survives within a process)
_partial_closed_tickets, _break_even_tickets, _trailing_extremes = _load_state()


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
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        _partial_closed_tickets.add(pos.ticket)
        _save_state(_partial_closed_tickets, _break_even_tickets, _trailing_extremes)
        remaining = round(pos.volume - close_volume, 2)
        print(f" [PARTIAL CLOSE] Ticket #{pos.ticket} ({symbol}): Ditutup {close_volume} lot "
              f"(profit {profit_points:.0f} pts). Sisa: {remaining} lot - trailing sisanya.")
    else:
        comment = result.comment if result else "Unknown error"
        print(f"[PARTIAL CLOSE ERROR] Gagal menutup sebagian #{pos.ticket}: {comment}")


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

    # TP-Adaptive Break-Even (50% of actual TP target if exists, otherwise fallback)
    if tp_points > 0:
        be_trigger = int(tp_points * 0.50)
        min_trigger = 30 if config.is_fx(symbol) else 100
        be_trigger = max(min_trigger, be_trigger)
    else:
        be_trigger = config.break_even_trigger_for(symbol)

    be_padding = config.break_even_padding_for(symbol)
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
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        _break_even_tickets.add(pos.ticket)
        _save_state(_partial_closed_tickets, _break_even_tickets, _trailing_extremes)
        print(f" [BREAK-EVEN] Ticket #{pos.ticket} ({symbol}): SL dipindahkan ke entry {be_price}")
    else:
        comment = result.comment if result else "Unknown error"
        print(f"[BE ERROR] Gagal memindahkan SL ke break-even #{pos.ticket}: {comment}")


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
    """Trail stop loss behind price using dynamic ATR multipliers (or static fallback)."""
    atr_points = _get_dynamic_atr_points(symbol, point)

    # Hitung jarak target TP posisi (jika ada) untuk aktivasi adaptif & progress calculation
    tp_points = 0
    if pos.tp:
        if pos.type == mt5.ORDER_TYPE_BUY:
            tp_points = (pos.tp - pos.price_open) / point
        else:
            tp_points = (pos.price_open - pos.tp) / point

    act_mult, dist_mult, fallback_act, fallback_dist, act_cap = config.trailing_activation_params_for(symbol)

    if atr_points > 0:
        activation = min(int(atr_points * act_mult), act_cap)
        distance = int(atr_points * dist_mult)
    else:
        activation = fallback_act
        distance = fallback_dist

    # TP-Adaptive Activation (% Jarak Target):
    # Jika posisi memiliki target TP yang terdefinisi (non-crypto), aktivasi menyala saat profit >= 60% TP.
    # Batas minimum (50 pts untuk FX, 150 pts untuk XAU) dan maksimum dibatasi 'activation' ATR.
    if tp_points > 0 and not config.is_crypto(symbol):
        tp_adaptive_act = int(tp_points * 0.60)
        if tp_adaptive_act > 0:
            min_floor = 50 if config.is_fx(symbol) else 150
            activation = max(min_floor, min(activation, tp_adaptive_act))

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

    # ---- Progressive distance (XAU only) ----
    # Distance mengecil linear dari START (longgar saat baru aktivasi) ke END
    # (ketat saat mendekati TP). Progress dihitung dari posisi profit terhadap
    # TP posisi (atau fallback: 2x activation). BTC tetap pakai distance statis.
    if config.is_crypto(symbol):
        trail_distance = distance * point
    else:
        start_mult = getattr(config, "TRAILING_DISTANCE_START_ATR_MULT_XAU", 1.2)
        end_mult = getattr(config, "TRAILING_DISTANCE_END_ATR_MULT_XAU", 0.4)
        min_mult = getattr(config, "TRAILING_DISTANCE_MIN_ATR_MULT_XAU", 0.3)

        progress_ref = max(tp_points, activation * 2) if tp_points > 0 else activation * 2
        progress = min(max((profit_points - activation) / (progress_ref - activation), 0.0), 1.0) if progress_ref > activation else 0.0

        # Interpolasi linear start_mult -> end_mult, lalu floor ke min_mult
        dynamic_mult = start_mult - (start_mult - end_mult) * progress
        dynamic_mult = max(dynamic_mult, min_mult)
        trail_distance = int(atr_points * dynamic_mult) * point if atr_points > 0 else distance * point

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
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        if config.is_crypto(symbol):
            print(f" [TRAILING] Ticket #{pos.ticket} ({symbol}): SL digeser ke {new_sl} (profit: {profit_points:.0f} pts, dist {distance} pts)")
        else:
            print(f" [TRAILING] Ticket #{pos.ticket} ({symbol}): SL digeser ke {new_sl} (profit: {profit_points:.0f} pts, dist {int(trail_distance/point)} pts, mult {dynamic_mult:.2f}x ATR)")
    else:
        comment = result.comment if result else "Unknown error"
        print(f"[TRAIL ERROR] Gagal menggeser SL #{pos.ticket}: {comment}")
