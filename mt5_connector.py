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
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)

    deals = mt5.history_deals_get(today_start, now)
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

def send_trade_order(symbol, action, lot, sl_points=None, tp_points=None):
    """
    Sends a buy/sell trade order to MT5.
    action: "BUY" or "SELL"
    sl_points / tp_points: distance in points for Stop Loss and Take Profit
    """
    if config.DRY_RUN:
        print(f"[DRY RUN] Simulasi {action} order untuk {symbol} sebanyak {lot} lot (SL: {sl_points} pts, TP: {tp_points} pts).")
        return {"status": "SUCCESS", "comment": "Dry Run Mode Active", "ticket": 0}

    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)
    
    if tick is None or symbol_info is None:
        return {"status": "ERROR", "comment": "Symbol info unavailable"}

    point = symbol_info.point
    
    if action == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        # Calculate SL/TP
        sl = price - (sl_points * point) if sl_points else 0.0
        tp = price + (tp_points * point) if tp_points else 0.0
    elif action == "SELL":
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        # Calculate SL/TP
        sl = price + (sl_points * point) if sl_points else 0.0
        tp = price - (tp_points * point) if tp_points else 0.0
    else:
        return {"status": "ERROR", "comment": "Invalid action type"}

    # Set default SL/TP from config if not specified by AI
    if not sl and config.DEFAULT_SL_POINTS:
        sl = price - (config.DEFAULT_SL_POINTS * point) if action == "BUY" else price + (config.DEFAULT_SL_POINTS * point)
    if not tp and config.DEFAULT_TP_POINTS:
        tp = price + (config.DEFAULT_TP_POINTS * point) if action == "BUY" else price - (config.DEFAULT_TP_POINTS * point)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": round(sl, symbol_info.digits),
        "tp": round(tp, symbol_info.digits),
        "deviation": config.DEVIATION,
        "magic": config.MAGIC_NUMBER,  # Unique ID for our bot trades
        "comment": "Multi-LLM Bot",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    print(f"[MT5] Mengirim order: {action} {symbol} {lot} lot pada harga {price} (SL: {request['sl']}, TP: {request['tp']})...")
    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[MT5 ERROR] Order gagal! Retcode: {result.retcode}, Pesan: {result.comment}")
        return {"status": "ERROR", "comment": result.comment, "code": result.retcode}
        
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
