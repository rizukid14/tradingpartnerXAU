import time
from datetime import datetime, timezone, timedelta
import pandas as pd
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange

import config
from config import mt5

# Server Broker Timezone configuration (VT Markets = EET / UTC+2 standard, UTC+3 DST)
# Indonesian Western Standard Time (WIB) = UTC+7
WIB_OFFSET = timedelta(hours=7)

def server_to_wib(dt_or_ts):
    """Converts a server timestamp or naive datetime to a timezone-aware WIB datetime."""
    if isinstance(dt_or_ts, (int, float)):
        # Server timestamp is UNIX epoch in seconds
        utc_dt = datetime.fromtimestamp(dt_or_ts, tz=timezone.utc)
    elif isinstance(dt_or_ts, datetime):
        if dt_or_ts.tzinfo is None:
            # Assume naive datetime is UTC from server epoch
            utc_dt = dt_or_ts.replace(tzinfo=timezone.utc)
        else:
            utc_dt = dt_or_ts.astimezone(timezone.utc)
    else:
        return dt_or_ts

    wib_tz = timezone(WIB_OFFSET)
    return utc_dt.astimezone(wib_tz)

def init_mt5():
    """Initializes connection to MT5 terminal and verifies account & symbol availability."""
    if config.DRY_RUN:
        print("[DRY RUN MODE] MetaTrader 5 live order execution disabled.")
        return True

    print(f"[MT5] Connecting to MT5 Terminal for symbol {config.SYMBOL}...")
    
    # Refresh symbol to ensure valid active symbol
    config.SYMBOL = get_valid_trade_symbol(config.SYMBOL)
    symbol_info = mt5.symbol_info(config.SYMBOL)
    if symbol_info is None:
        print(f"[MT5 ERROR] Symbol {config.SYMBOL} not found on broker.")
        mt5.shutdown()
        return False
        
    if not symbol_info.visible:
        print(f"[MT5] Symbol {config.SYMBOL} not visible in Market Watch. Enabling...")
        if not mt5.symbol_select(config.SYMBOL, True):
            print(f"[MT5 ERROR] Could not select symbol {config.SYMBOL}")
            mt5.shutdown()
            return False
            
    return True

initialize_mt5 = init_mt5

def get_market_data(symbol, timeframe, num_candles=50):
    """
    Fetches historical candles from MT5 and calculates technical indicators.
    Returns a pandas DataFrame with indicators.
    """
    symbol = get_valid_trade_symbol(symbol)
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_candles)
    if rates is None or len(rates) == 0:
        print(f"[MT5 ERROR] Could not fetch rates for {symbol}.")
        return None
        
    df = pd.DataFrame(rates)
    df['time'] = df['time'].apply(server_to_wib)
    
    # Calculate indicators using ta library
    df['ema_20'] = EMAIndicator(close=df['close'], window=20).ema_indicator()
    df['ema_50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
    df['rsi_14'] = RSIIndicator(close=df['close'], window=14).rsi()
    df['atr_14'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
    
    return df

def get_last_m1_candles(symbol, num_candles=3):
    """
    Fetches the last N M1 candles for micro-momentum analysis.
    Returns a list of dicts: [{'time': ..., 'open': ..., 'close': ..., 'direction': 'BULLISH'/'BEARISH'}, ...]
    """
    symbol = get_valid_trade_symbol(symbol)
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, num_candles)
    if rates is None or len(rates) == 0:
        return []
    
    candles = []
    for r in rates:
        wib_time = server_to_wib(r['time'])
        direction = "BULLISH" if r['close'] >= r['open'] else "BEARISH"
        candles.append({
            "time": wib_time.strftime("%H:%M"),
            "open": round(r['open'], 2),
            "high": round(r['high'], 2),
            "low": round(r['low'], 2),
            "close": round(r['close'], 2),
            "volume": int(r['tick_volume']),
            "direction": direction,
            "body_pts": int(abs(r['close'] - r['open']) * 100)
        })
    return candles

def get_account_info():
    """
    Fetches current live account equity, balance, margin, and free margin.
    Returns a dict with balance info, or fallback dummy data in DRY RUN.
    """
    if config.DRY_RUN:
        return {
            "balance": config.STARTING_BALANCE,
            "equity": config.STARTING_BALANCE,
            "margin": 0.0,
            "free_margin": config.STARTING_BALANCE,
            "leverage": 100,
            "profit": 0.0
        }
        
    acc = mt5.account_info()
    if acc is None:
        print("[MT5 ERROR] Could not fetch account info.")
        return None
        
    return {
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.margin_free,
        "leverage": acc.leverage,
        "profit": acc.profit
    }

def get_open_positions(symbol=None, magic=None):
    """
    Fetches currently open positions for the given symbol and magic number.
    Returns a list of dicts.
    """
    if config.DRY_RUN:
        return []
        
    if symbol:
        symbol = get_valid_trade_symbol(symbol)
        positions = mt5.positions_get(symbol=symbol)
    else:
        positions = mt5.positions_get()

    if positions is None:
        return []
        
    res = []
    target_magic = magic if magic is not None else getattr(config, "MAGIC_NUMBER", None)
    for p in positions:
        if target_magic is not None and getattr(p, "magic", None) != target_magic:
            continue
        res.append({
            "ticket": p.ticket,
            "symbol": p.symbol,
            "direction": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "type": p.type,
            "volume": p.volume,
            "entry_price": p.price_open,
            "price_open": p.price_open,
            "current_price": p.price_current,
            "sl": p.sl,
            "tp": p.tp,
            "pnl": p.profit,
            "profit": p.profit,
            "magic": p.magic,
            "time": p.time
        })
    return res

def get_all_open_positions(magic=None):
    """Fetches all open positions managed by this bot across ALL symbols."""
    return get_open_positions(symbol=None, magic=magic)

def get_closed_positions_today(magic=None, symbol=None):
    """
    Fetches closed positions for today (midnight WIB to now).
    Returns list of dicts with ticket, symbol, direction, profit, etc.
    """
    if config.DRY_RUN:
        return []

    wib_tz = timezone(WIB_OFFSET)
    now_wib = datetime.now(wib_tz)
    start_wib = now_wib.replace(hour=0, minute=0, second=0, microsecond=0)
    
    from_date = datetime.fromtimestamp(start_wib.timestamp(), tz=timezone.utc)
    to_date = datetime.now(timezone.utc) + timedelta(minutes=5)
    
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None or len(deals) == 0:
        return []

    target_magic = magic if magic is not None else getattr(config, "MAGIC_NUMBER", None)
    
    bot_tickets = set()
    for d in deals:
        if d.entry == mt5.DEAL_ENTRY_IN:
            if target_magic is None or d.magic == target_magic:
                bot_tickets.add(d.position_id)

    closed_trades = []
    for d in deals:
        if d.entry != mt5.DEAL_ENTRY_OUT:
            continue
        
        if d.position_id not in bot_tickets:
            continue
            
        if symbol and d.symbol != symbol:
            continue

        direction = "BUY" if d.type == mt5.DEAL_TYPE_SELL else "SELL"
        closed_trades.append({
            "ticket": d.position_id,
            "deal_id": d.ticket,
            "symbol": d.symbol,
            "direction": direction,
            "volume": d.volume,
            "price": d.price,
            "profit": d.profit + d.commission + d.swap,
            "raw_profit": d.profit,
            "comment": d.comment,
            "time": server_to_wib(d.time),
            "reason": d.reason
        })
        
    return closed_trades

def get_trade_details(ticket):
    """
    Fetches entry price, exit price, volume, duration, and profit for a closed trade ticket.
    Returns a dict or None if not found.
    """
    if config.DRY_RUN:
        return None
    try:
        deals = mt5.history_deals_get(position=ticket)
        if not deals:
            return None

        in_deal = None
        out_deal = None
        for d in deals:
            if d.entry == mt5.DEAL_ENTRY_IN:
                in_deal = d
            elif d.entry == mt5.DEAL_ENTRY_OUT:
                out_deal = d

        if not in_deal or not out_deal:
            return None

        pos_type = "BUY" if in_deal.type == mt5.DEAL_TYPE_BUY else "SELL"
        entry_price = in_deal.price
        exit_price = out_deal.price
        volume = in_deal.volume
        symbol = in_deal.symbol

        t_in = datetime.fromtimestamp(in_deal.time)
        t_out = datetime.fromtimestamp(out_deal.time)
        duration_sec = max(0, out_deal.time - in_deal.time)

        profit = out_deal.profit + out_deal.commission + out_deal.swap

        return {
            "ticket": ticket,
            "symbol": symbol,
            "direction": pos_type,
            "volume": volume,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "entry_time": server_to_wib(in_deal.time),
            "exit_time": server_to_wib(out_deal.time),
            "duration_seconds": duration_sec,
            "profit": profit,
            "raw_profit": out_deal.profit,
            "comment": out_deal.comment,
            "reason": out_deal.reason,
        }
    except Exception as e:
        print(f"[MT5 CONNECTOR WARNING] Could not fetch trade details #{ticket}: {e}")
        return None

# Retcodes that mean "broker wants a fresh price/wider deviation" — worth a retry.
_RETRYABLE_RETCODES = {
    getattr(mt5, "TRADE_RETCODE_PRICE_CHANGED", 10020),
    getattr(mt5, "TRADE_RETCODE_PRICE_OFF", 10021),
    getattr(mt5, "TRADE_RETCODE_REQUOTE", 10004),
    getattr(mt5, "TRADE_RETCODE_REJECT", 10013),
}

_MAX_RETRIES = 2

def _get_exec_mode(info):
    if not info:
        return "N/A"
    for attr in ("trade_exemode", "trade_execution_mode", "execution_mode", "exemode"):
        val = getattr(info, attr, None)
        if val is not None:
            return val
    return "N/A"

def get_valid_trade_symbol(symbol):
    """
    Returns the exact tradeable symbol name on the connected MT5 broker.
    Handles broker suffix variations (e.g. XAUUSD-ECN -> XAUUSD-ECNc, BTCUSD -> BTCUSD.c).
    """
    if not symbol:
        return symbol
    info = mt5.symbol_info(symbol)
    if info is not None and getattr(info, "trade_mode", 0) in (mt5.SYMBOL_TRADE_MODE_FULL, 4):
        return symbol

    candidates = [
        symbol + "c",
        symbol + ".c",
        symbol + ".ecn",
        symbol + "c.ecn",
        symbol[:-1] if symbol.endswith("c") else symbol,
    ]
    for cand in candidates:
        if cand == symbol:
            continue
        cand_info = mt5.symbol_info(cand)
        if cand_info is not None and getattr(cand_info, "trade_mode", 0) in (mt5.SYMBOL_TRADE_MODE_FULL, 4):
            print(f"[MT5 AUTO-CORRECT] Symbol '{symbol}' auto-corrected to broker symbol: '{cand}'")
            return cand

    return symbol

def get_filling_policy(symbol):
    """
    Determines the supported filling policy for a symbol dynamically.
    Returns mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, or mt5.ORDER_FILLING_RETURN.
    """
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_FOK

    # Bitmask of filling modes:
    # 1: SYMBOL_FILLING_FOK
    # 2: SYMBOL_FILLING_IOC
    fm = getattr(info, "filling_mode", 0)
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    elif fm & 2:
        return mt5.ORDER_FILLING_IOC
    else:
        return mt5.ORDER_FILLING_RETURN

def _safe_order_send(request):
    """Sends order request safely supporting both native MT5 and mt5linux RPC bridge."""
    try:
        res = mt5.order_send(request)
        if res is not None:
            return res
    except Exception:
        pass
    try:
        return mt5.order_send(request=request)
    except Exception:
        return None

def _send_with_retry(build_request, symbol, label):
    """Send a request via mt5.order_send with retries and fill-policy fallback."""
    policy = get_filling_policy(symbol)

    req = build_request(config.DEVIATION, policy)
    result = _safe_order_send(req)

    for attempt in range(_MAX_RETRIES):
        if not result or result.retcode not in _RETRYABLE_RETCODES:
            break
        widen = config.DEVIATION + (5 * (attempt + 1))
        print(f"[MT5] {label} retry {attempt + 1}/{_MAX_RETRIES}: retcode={result.retcode}, widening deviation to {widen} pts")
        req = build_request(widen, policy)
        result = _safe_order_send(req)

    if result and result.retcode == getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030) and policy != mt5.ORDER_FILLING_RETURN:
        print(f"[MT5] {label} fallback to ORDER_FILLING_RETURN (retcode was {result.retcode})")
        req = build_request(config.DEVIATION, mt5.ORDER_FILLING_RETURN)
        result = _safe_order_send(req)

    return result

def send_trade_order(symbol, action, lot, sl_points=None, tp_points=None):
    """
    Sends a buy/sell trade order to MT5.
    action: "BUY" or "SELL"
    sl_points / tp_points: distance in points for Stop Loss and Take Profit
    """
    if config.DRY_RUN:
        print(f"[DRY RUN] Simulasi {action} order untuk {symbol} sebanyak {lot} lot (SL: {sl_points} pts, TP: {tp_points} pts).")
        return {"status": "SUCCESS", "comment": "Dry Run Mode Active", "ticket": 0}

    symbol = get_valid_trade_symbol(symbol)
    mt5.symbol_select(symbol, True)

    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)

    if tick is None or symbol_info is None:
        return {"status": "ERROR", "comment": "Symbol info unavailable"}

    point = symbol_info.point

    if action == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        sl = price - (sl_points * point) if sl_points else 0.0
        tp = price + (tp_points * point) if tp_points else 0.0
    elif action == "SELL":
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        sl = price + (sl_points * point) if sl_points else 0.0
        tp = price - (tp_points * point) if tp_points else 0.0
    else:
        return {"status": "ERROR", "comment": "Invalid action type"}

    default_sl = config.default_sl_points_for(symbol)
    default_tp = config.default_tp_points_for(symbol)
    if not sl and default_sl:
        sl = price - (default_sl * point) if action == "BUY" else price + (default_sl * point)
    if not tp and default_tp:
        tp = price + (default_tp * point) if action == "BUY" else price - (default_tp * point)

    def _build(deviation, fill_policy):
        live_tick = mt5.symbol_info_tick(symbol)
        if live_tick is not None:
            live_price = live_tick.ask if action == "BUY" else live_tick.bid
        else:
            live_price = price
        if action == "BUY":
            live_sl = live_price - (sl_points * point) if sl_points else (live_price - (default_sl * point) if default_sl else 0.0)
            live_tp = live_price + (tp_points * point) if tp_points else (live_price + (default_tp * point) if default_tp else 0.0)
        else:
            live_sl = live_price + (sl_points * point) if sl_points else (live_price + (default_sl * point) if default_sl else 0.0)
            live_tp = live_price - (tp_points * point) if tp_points else (live_price - (default_tp * point) if default_tp else 0.0)
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": live_price,
            "sl": round(live_sl, symbol_info.digits),
            "tp": round(live_tp, symbol_info.digits),
            "deviation": deviation,
            "magic": config.MAGIC_NUMBER,
            "comment": "Multi-LLM Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": fill_policy,
        }

    print(f"[MT5] Mengirim order: {action} {symbol} {lot} lot pada harga {price} (SL: {round(sl, symbol_info.digits)}, TP: {round(tp, symbol_info.digits)})...")
    result = _send_with_retry(_build, symbol, f"Order {action} {symbol}")

    if result is None or result.retcode not in (
        mt5.TRADE_RETCODE_DONE,
        getattr(mt5, "TRADE_RETCODE_PLACED", 10008),
    ):
        retcode = getattr(result, "retcode", "N/A") if result else "N/A"
        comment = getattr(result, "comment", "No result") if result else "No result"
        print(f"[MT5 ERROR] Order gagal! Retcode: {retcode}, Pesan: {comment}")
        return {"status": "ERROR", "comment": comment, "code": retcode}

    print(f"[MT5] Order BERHASIL! Ticket: {result.order}")
    return {"status": "SUCCESS", "ticket": result.order, "comment": result.comment}

def close_position(ticket):
    """Closes an open position by its ticket number."""
    positions = mt5.positions_get(ticket=ticket)
    if positions is None or len(positions) == 0:
        return False

    position = positions[0]
    symbol = position.symbol
    lot = position.volume
    pos_type = position.type

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return False

    def _build(deviation, fill_policy):
        live_tick = mt5.symbol_info_tick(symbol)
        if pos_type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = live_tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = live_tick.ask
        return {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "position": ticket,
            "price": price,
            "deviation": deviation,
            "magic": config.MAGIC_NUMBER,
            "comment": "Close Position",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": fill_policy,
        }

    print(f"[MT5] Menutup posisi #{ticket}...")
    result = _send_with_retry(_build, symbol, f"Close #{ticket}")

    if result is None or result.retcode not in (
        mt5.TRADE_RETCODE_DONE,
        getattr(mt5, "TRADE_RETCODE_PLACED", 10008),
    ):
        comment = getattr(result, "comment", "No result") if result else "No result"
        print(f"[MT5 ERROR] Gagal menutup posisi: {comment}")
        return False
    print(f"[MT5] Posisi #{ticket} berhasil ditutup.")
    return True
