import time
import pandas as pd
import sys
if sys.platform == 'win32':
    import MetaTrader5 as mt5
else:
    try:
        from mt5linux import MetaTrader5 as mt5
    except ImportError:
        import MetaTrader5 as mt5
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import config

def get_valid_trade_symbol(symbol):
    """Auto-resolves symbol name based on broker's exact symbol naming (e.g. XAUUSD-ECNc vs XAUUSD-ECN vs XAUUSD)."""
    if mt5.symbol_info(symbol) is not None:
        return symbol

    base = symbol.split("-")[0].split(".")[0].upper()
    candidates = [
        symbol,
        f"{base}-ECN",
        f"{base}-ECNc",
        base,
        f"{base}.c",
        f"{base}.ecn",
        f"{base}.m",
        f"{base}.pro",
        f"{base}.MT5",
    ]
    for cand in candidates:
        info = mt5.symbol_info(cand)
        if info is not None:
            mt5.symbol_select(cand, True)
            print(f"[MT5] Auto-resolved symbol '{symbol}' -> '{cand}' di broker {config.MT5_SERVER}")
            return cand
    return symbol


def initialize_mt5():
    """Initializes connection to MT5 terminal."""
    if not mt5.initialize():
        print("[MT5 ERROR] Inisialisasi MT5 gagal. Pastikan aplikasi MT5 terinstal dan aktif.")
        return False
    
    # If account credentials are provided in config, attempt login
    if config.MT5_LOGIN and config.MT5_PASSWORD:
        print(f"[MT5] Mencoba masuk ke akun {config.MT5_LOGIN} pada server {config.MT5_SERVER}...")
        authorized = mt5.login(
            login=config.MT5_LOGIN,
            password=config.MT5_PASSWORD,
            server=config.MT5_SERVER
        )
        if not authorized:
            print(f"[MT5 ERROR] Login gagal: {mt5.last_error()}")
            mt5.shutdown()
            return False
        print("[MT5] Login berhasil!")
    else:
        print("[MT5] Terhubung ke terminal MT5 yang sedang aktif.")
        
    # Auto-resolve symbol for Demo vs Live broker naming differences
    resolved_sym = get_valid_trade_symbol(config.SYMBOL)
    config.SYMBOL = resolved_sym

    # Check if the symbol is available and visible
    symbol_info = mt5.symbol_info(config.SYMBOL)
    if symbol_info is None:
        print(f"[MT5 ERROR] Simbol {config.SYMBOL} tidak ditemukan.")
        mt5.shutdown()
        return False
        
    if not symbol_info.visible:
        print(f"[MT5] Simbol {config.SYMBOL} tidak terlihat di Market Watch. Mencoba mengaktifkan...")
        if not mt5.symbol_select(config.SYMBOL, True):
            print(f"[MT5 ERROR] Gagal memilih simbol {config.SYMBOL}")
            mt5.shutdown()
            return False
            
    return True

def get_market_data(symbol, timeframe, num_candles=50):
    """
    Fetches historical candles from MT5 and calculates technical indicators.
    Returns a pandas DataFrame with indicators.
    """
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_candles)
    if rates is None or len(rates) == 0:
        print(f"[MT5 ERROR] Gagal mengambil data rates untuk {symbol}.")
        return None
        
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    
    # Calculate indicators using ta library
    df['ema_20'] = EMAIndicator(close=df['close'], window=20).ema_indicator()
    df['ema_50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
    df['rsi_14'] = RSIIndicator(close=df['close'], window=14).rsi()
    df['atr_14'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
    
    return df

def get_current_tick(symbol):
    """Gets the latest bid/ask tick data."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[MT5 ERROR] Gagal mendapatkan tick untuk {symbol}.")
        return None
    return {
        "bid": tick.bid,
        "ask": tick.ask,
        "spread": round((tick.ask - tick.bid) / mt5.symbol_info(symbol).point, 1),
        "point": mt5.symbol_info(symbol).point
    }

def get_open_positions(symbol):
    """Checks if there are any open positions for the symbol."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [
        {
            "ticket": p.ticket,
            "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": p.volume,
            "price_open": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "profit": p.profit
        }
        for p in positions
    ]

def get_closed_positions_today():
    """
    Returns deals that closed (entry OUT) positions opened by this bot today.
    Used for daily P/L, consecutive-loss tracking, and recovery mode.
    """
    from datetime import datetime, timedelta

    # Use local PC time (naive) which matches terminal/server timezone behavior in MT5
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    # Query until tomorrow to prevent timezone / broker server offset cutoffs
    tomorrow = today_start + timedelta(days=1)

    deals = mt5.history_deals_get(today_start, tomorrow)
    if deals is None:
        return []

    closed = []
    for deal in deals:
        # Only count bot trades and closed positions (entry OUT)
        if deal.magic != config.MAGIC_NUMBER:
            continue
        if deal.entry != mt5.DEAL_ENTRY_OUT:
            continue
        closed.append({
            "ticket": deal.position_id,
            "profit": deal.profit + deal.swap + deal.commission,
            "time": deal.time,
        })
    return closed

def send_trade_order(symbol, action, lot, sl_points=None, tp_points=None, comment=None):
    """
    Sends a buy/sell trade order to MT5.
    action: "BUY" or "SELL"
    sl_points / tp_points: distance in points for Stop Loss and Take Profit
    """
    from src.core import telegram_alerts

    if config.DRY_RUN:
        print(f"[DRY RUN] Simulasi {action} order untuk {symbol} sebanyak {lot} lot (SL: {sl_points} pts, TP: {tp_points} pts).")
        return {"status": "SUCCESS", "comment": "Dry Run Mode Active", "ticket": 0}

    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)

    if tick is None or symbol_info is None:
        telegram_alerts.alert_order_error(symbol, action, lot, sl_points, tp_points, "N/A", "Symbol info unavailable")
        return {"status": "ERROR", "comment": "Symbol info unavailable"}

    point = symbol_info.point
    digits = symbol_info.digits

    if action == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = round(tick.ask, digits)
        sl = (price - (sl_points * point)) if sl_points else 0.0
        tp = (price + (tp_points * point)) if tp_points else 0.0
    elif action == "SELL":
        order_type = mt5.ORDER_TYPE_SELL
        price = round(tick.bid, digits)
        sl = (price + (sl_points * point)) if sl_points else 0.0
        tp = (price - (tp_points * point)) if tp_points else 0.0
    else:
        return {"status": "ERROR", "comment": "Invalid action type"}

    # Set default SL/TP from config if not specified by AI
    if not sl and config.DEFAULT_SL_POINTS:
        sl = price - (config.DEFAULT_SL_POINTS * point) if action == "BUY" else price + (config.DEFAULT_SL_POINTS * point)
    if not tp and config.DEFAULT_TP_POINTS:
        tp = price + (config.DEFAULT_TP_POINTS * point) if action == "BUY" else price - (config.DEFAULT_TP_POINTS * point)

    sl_price = round(sl, digits) if sl else 0.0
    tp_price = round(tp, digits) if tp else 0.0
    comm_str = (str(comment)[:25].strip() if comment else "Multi-LLM Bot")

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl_price,
        "tp": tp_price,
        "deviation": config.DEVIATION,
        "magic": config.MAGIC_NUMBER,
        "comment": comm_str,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    print(f"[MT5] Mengirim order: {action} {symbol} {lot} lot pada harga {price} (SL: {sl_price}, TP: {tp_price})...")
    result = mt5.order_send(request)

    if not result or result.retcode != mt5.TRADE_RETCODE_DONE:
        retcode = getattr(result, "retcode", "N/A") if result else "N/A"
        err_msg = getattr(result, "comment", "No result") if result else "No result"
        print(f"[MT5 ERROR] Order gagal! Retcode: {retcode}, Pesan: {err_msg}")
        telegram_alerts.alert_order_error(
            symbol=symbol,
            signal=action,
            lot=lot,
            sl_points=sl_points,
            tp_points=tp_points,
            retcode=retcode,
            comment=err_msg,
            price=price,
            sl_price=sl_price,
            tp_price=tp_price,
            thesis=comment or "Multi-LLM Bot",
        )
        return {"status": "ERROR", "comment": err_msg, "code": retcode}

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
    
    tick = mt5.symbol_info_tick(symbol)
    if pos_type == mt5.ORDER_TYPE_BUY:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": config.DEVIATION,
        "magic": config.MAGIC_NUMBER,
        "comment": "Close Position",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    print(f"[MT5] Menutup posisi #{ticket}...")
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[MT5 ERROR] Gagal menutup posisi: {result.comment}")
        return False
    print(f"[MT5] Posisi #{ticket} berhasil ditutup.")
    return True

def get_closed_positions_today():
    """Fetches deals executed today for history tracking and Telegram alerts."""
    import datetime
    now = datetime.datetime.now()
    from_date = datetime.datetime(now.year, now.month, now.day)
    to_date = now + datetime.timedelta(days=1)
    
    deals = mt5.history_deals_get(from_date, to_date)
    if deals is None:
        return []
        
    closed = []
    for d in deals:
        if d.magic == config.MAGIC_NUMBER and d.entry == 1:  # DEAL_ENTRY_OUT
            closed.append({
                "ticket": d.position_id,
                "deal_id": d.ticket,
                "symbol": d.symbol,
                "type": "BUY" if d.type == mt5.ORDER_TYPE_SELL else "SELL",
                "volume": d.volume,
                "profit": d.profit + d.swap + d.commission,
                "comment": d.comment
            })
    return closed
