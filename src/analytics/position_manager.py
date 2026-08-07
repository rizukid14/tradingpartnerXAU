"""
Position Manager - Active position management after entry.

Combines the best from:
- XAU-60: Trailing stop with activation, break-even with padding
- xaubot-ai: Partial close at TP1, weekend close handler

Runs every tick cycle (every 5 seconds), NOT just on new candles.
"""
import sys
if sys.platform == 'win32':
    import MetaTrader5 as mt5
else:
    try:
        from mt5linux import MetaTrader5 as mt5
    except ImportError:
        import MetaTrader5 as mt5
import config



def manage_all_positions():
    """
    Iterates all open positions for our symbol and applies:
    1. Partial close at TP1 (close 50% of position at first target)
    2. Break-even (move SL to entry once threshold hit)
    3. Trailing stop (continuously advance SL behind price)

    Call this every tick cycle (every 5 seconds).
    """
    positions = mt5.positions_get(symbol=config.SYMBOL)
    if positions is None or len(positions) == 0:
        return

    symbol_info = mt5.symbol_info(config.SYMBOL)
    if symbol_info is None:
        return

    point = symbol_info.point

    for pos in positions:
        # Only manage positions opened by our bot
        if pos.magic != config.MAGIC_NUMBER:
            continue

        tick = mt5.symbol_info_tick(config.SYMBOL)
        if tick is None:
            continue

        # Calculate current profit in points
        if pos.type == mt5.ORDER_TYPE_BUY:
            current_price = tick.bid
            profit_points = (current_price - pos.price_open) / point
        else:  # SELL
            current_price = tick.ask
            profit_points = (pos.price_open - current_price) / point

        # --- PARTIAL CLOSE at TP1 ---
        if config.PARTIAL_CLOSE_ENABLED:
            _check_partial_close(pos, profit_points, symbol_info)

        # --- BREAK-EVEN CHECK ---
        if config.BREAK_EVEN_ENABLED:
            _check_break_even(pos, profit_points, point, symbol_info)

        # --- TRAILING STOP CHECK ---
        if config.TRAILING_STOP_ENABLED:
            _check_trailing_stop(pos, profit_points, current_price, point, symbol_info)


# =============================================================================
#  PARTIAL CLOSE (from XAU-60 trade_executor.py)
# =============================================================================
_partial_closed_tickets = set()  # Track which tickets already had partial close


def _check_partial_close(pos, profit_points, symbol_info):
    """Close a portion of the position at TP1 to lock in some profit."""
    global _partial_closed_tickets

    if pos.ticket in _partial_closed_tickets:
        return  # Already partially closed

    tp1_points = config.PARTIAL_CLOSE_TP1_POINTS_BTC if config.is_crypto(config.SYMBOL) else config.PARTIAL_CLOSE_TP1_POINTS_XAU
    if profit_points < tp1_points:
        return

    # Calculate volume to close
    close_volume = round(pos.volume * (config.PARTIAL_CLOSE_PERCENT / 100.0), 2)
    close_volume = max(symbol_info.volume_min, close_volume)

    # Make sure we don't close more than we have
    if close_volume >= pos.volume:
        return  # Would close entire position, skip

    tick = mt5.symbol_info_tick(config.SYMBOL)
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
        "symbol": config.SYMBOL,
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
        remaining = round(pos.volume - close_volume, 2)
        print(f"💰 [PARTIAL CLOSE] Ticket #{pos.ticket}: Ditutup {close_volume} lot "
              f"(profit {profit_points:.0f} pts). Sisa: {remaining} lot — trailing sisanya.")
    else:
        comment = result.comment if result else "Unknown error"
        print(f"[PARTIAL CLOSE ERROR] Gagal menutup sebagian #{pos.ticket}: {comment}")


# =============================================================================
#  BREAK-EVEN (from XAU-60 trade_executor.py)
# =============================================================================
_break_even_tickets = set()  # Track which tickets already moved to break-even


def _check_break_even(pos, profit_points, point, symbol_info):
    """Move SL to entry price + padding once profit threshold is reached."""
    global _break_even_tickets

    if pos.ticket in _break_even_tickets:
        return  # Already at break-even

    be_trigger = config.BREAK_EVEN_TRIGGER_POINTS_BTC if config.is_crypto(config.SYMBOL) else config.BREAK_EVEN_TRIGGER_POINTS_XAU
    be_padding = config.BREAK_EVEN_PADDING_POINTS_BTC if config.is_crypto(config.SYMBOL) else config.BREAK_EVEN_PADDING_POINTS_XAU
    if profit_points < be_trigger:
        return

    if pos.type == mt5.ORDER_TYPE_BUY:
        be_price = pos.price_open + (be_padding * point)
        # Only move if current SL is below break-even level
        if pos.sl >= be_price:
            _break_even_tickets.add(pos.ticket)
            return
    else:  # SELL
        be_price = pos.price_open - (be_padding * point)
        if pos.sl != 0 and pos.sl <= be_price:
            _break_even_tickets.add(pos.ticket)
            return

    be_price = round(be_price, symbol_info.digits)

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": config.SYMBOL,
        "position": pos.ticket,
        "sl": be_price,
        "tp": pos.tp,
        "magic": config.MAGIC_NUMBER,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        _break_even_tickets.add(pos.ticket)
        print(f"🔒 [BREAK-EVEN] Ticket #{pos.ticket}: SL dipindahkan ke entry {be_price}")
    else:
        comment = result.comment if result else "Unknown error"
        print(f"[BE ERROR] Gagal memindahkan SL ke break-even #{pos.ticket}: {comment}")


# =============================================================================
#  TRAILING STOP (from XAU-60 trade_executor.py)
# =============================================================================
def _check_trailing_stop(pos, profit_points, current_price, point, symbol_info):
    """Trail stop loss behind price once activation threshold is reached."""
    if config.is_crypto(config.SYMBOL):
        activation = config.TRAILING_ACTIVATION_POINTS_BTC
        distance = config.TRAILING_DISTANCE_POINTS_BTC
    else:
        activation = config.TRAILING_ACTIVATION_POINTS_XAU
        distance = config.TRAILING_DISTANCE_POINTS_XAU

    if profit_points < activation:
        return

    trail_distance = distance * point

    if pos.type == mt5.ORDER_TYPE_BUY:
        new_sl = current_price - trail_distance
        new_sl = round(new_sl, symbol_info.digits)
        # Only move SL up, never down
        if pos.sl >= new_sl:
            return
    else:  # SELL
        new_sl = current_price + trail_distance
        new_sl = round(new_sl, symbol_info.digits)
        # Only move SL down, never up
        if pos.sl != 0 and pos.sl <= new_sl:
            return

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": config.SYMBOL,
        "position": pos.ticket,
        "sl": new_sl,
        "tp": pos.tp,
        "magic": config.MAGIC_NUMBER,
    }

    result = mt5.order_send(request)
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"📈 [TRAILING] Ticket #{pos.ticket}: SL digeser ke {new_sl} (profit: {profit_points:.0f} pts)")
    else:
        comment = result.comment if result else "Unknown error"
        print(f"[TRAIL ERROR] Gagal menggeser SL #{pos.ticket}: {comment}")
