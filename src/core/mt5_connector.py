import time
import pandas as pd
import sys
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
if sys.platform == 'win32':
    import MetaTrader5 as mt5
else:
    try:
        import importlib
        mt5 = importlib.import_module("mt5linux").MetaTrader5
    except ImportError:
        import MetaTrader5 as mt5
from ta.trend import EMAIndicator
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
import config

WIB = ZoneInfo("Asia/Jakarta")


def server_utc_offset_hours():
    """
    Dynamically calculates the MT5 server timezone offset in hours from UTC.
    Uses BTCUSD.c first (since crypto trades 24/7 and ticks even on weekends),
    falling back to the active config symbol, and finally to 3 (GMT+3).
    """
    try:
        # 1. Try BTCUSD.c first for 24/7 active ticks
        tick = mt5.symbol_info_tick("BTCUSD.c")
        if tick is not None and tick.time > 0:
            diff_seconds = tick.time - time.time()
            return round(diff_seconds / 3600.0)
            
        # 2. Fallback to active symbol
        tick = mt5.symbol_info_tick(config.SYMBOL)
        if tick is not None and tick.time > 0:
            diff_seconds = tick.time - time.time()
            return round(diff_seconds / 3600.0)
    except Exception as e:
        print(f"[MT5 CONNECTOR WARNING] Gagal menghitung server offset dinamis: {e}")
    return 3


def server_to_wib(server_ts):
    """
    Converts an MT5 server epoch timestamp to an aware WIB datetime.
    MT5 timestamps are in the broker server timezone (e.g. GMT+3); this
    shifts them into Asia/Jakarta so candle times match wall-clock WIB.
    """
    offset_hours = server_utc_offset_hours()
    # Convert server epoch to UTC epoch by subtracting the server's offset
    utc_ts = int(server_ts) - (offset_hours * 3600)
    # Convert UTC epoch to WIB datetime
    return datetime.fromtimestamp(utc_ts, tz=timezone.utc).astimezone(WIB)

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
    # Convert server epoch -> aware WIB so candle times match wall-clock WIB
    df['time'] = df['time'].apply(server_to_wib)
    
    # Calculate indicators using ta library
    df['ema_20'] = EMAIndicator(close=df['close'], window=20).ema_indicator()
    df['ema_50'] = EMAIndicator(close=df['close'], window=50).ema_indicator()
    df['rsi_14'] = RSIIndicator(close=df['close'], window=14).rsi()
    df['atr_14'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
    
    return df

def get_last_m1_candles(symbol, num_candles=3):
    """
    Fetches the last N completed M1 candles (micro price action context).
    Returns a list of dicts (time WIB, open, high, low, close, volume).
    Returns [] on failure.
    """
    try:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, num_candles)
        if rates is None or len(rates) == 0:
            return []
        out = []
        for r in rates:
            out.append({
                "time": server_to_wib(int(r['time'])).strftime('%H:%M'),
                "open": r['open'],
                "high": r['high'],
                "low": r['low'],
                "close": r['close'],
                "volume": r['tick_volume'],
            })
        return out
    except Exception:
        return []

def get_current_tick(symbol):
    """Gets the latest bid/ask tick data."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        print(f"[MT5 ERROR] Gagal mendapatkan tick untuk {symbol}.")
        return None
    si = mt5.symbol_info(symbol)
    if si is None:
        print(f"[MT5 ERROR] Gagal mendapatkan symbol info untuk {symbol}.")
        return None
    spread_usd = tick.ask - tick.bid
    point_val = si.point if (si and si.point) else 0.0
    spread_pts = round(spread_usd / point_val, 1) if point_val > 0 else 0.0
    usd_per_pt = (si.trade_tick_value * config.lot_size_for(symbol) * (si.point / si.trade_tick_size)) if (si and si.trade_tick_size and si.point) else 0.0
    return {
        "bid": tick.bid,
        "ask": tick.ask,
        "spread": spread_pts,
        "spread_usd": spread_usd,
        "point": si.point,
        "usd_per_point": usd_per_pt,
    }

def get_open_positions(symbol):
    """Checks if there are any open positions for the symbol (bot-managed only)."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [
        {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": p.volume,
            "price_open": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "profit": p.profit,
            "swap": p.swap,
            "time": p.time
        }
        for p in positions
        if p.magic == config.MAGIC_NUMBER
    ]


def get_all_open_positions():
    """Returns ALL open bot-managed positions across every symbol."""
    positions = mt5.positions_get()
    if positions is None:
        return []
    return [
        {
            "ticket": p.ticket,
            "symbol": p.symbol,
            "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": p.volume,
            "price_open": p.price_open,
            "sl": p.sl,
            "tp": p.tp,
            "profit": p.profit,
            "swap": p.swap,
            "time": p.time
        }
        for p in positions
        if p.magic == config.MAGIC_NUMBER
    ]

def get_closed_positions_today(symbol=None):
    """
    Returns deals that closed (entry OUT) positions opened by this bot today.
    Used for daily P/L, consecutive-loss tracking, and recovery mode.
    Pass symbol= to count only one instrument (per-symbol loss streak);
    omit it to aggregate across all symbols (daily loss cap).
    """
    # history_deals_get(from, to) takes datetimes in the MT5 terminal's local
    # wall-clock time. We use a WIB-midnight -> next-midnight window so "today"
    # means the current trading day (bot's own closes), not a rolling 24h that
    # would drag in the previous day's P/L. Epochs are passed as ints so the
    # boundaries match exactly what datetime.now() produced.
    from datetime import datetime, timedelta
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    tomorrow = today_start + timedelta(days=1)
    from_epoch = int(today_start.timestamp())
    to_epoch = int(tomorrow.timestamp())

    deals = mt5.history_deals_get(from_epoch, to_epoch)
    if deals is None:
        return []

    # Positions opened by THIS bot (entry IN with bot magic) in the window.
    # Used to accept manual closes: MT5 mobile/web manual close of a bot position
    # produces an OUT deal with magic=0 (magic is not forwarded), so filtering
    # strictly on magic would silently drop those closes.
    # IMPORTANT: query a WIDE window (7 days) for bot_opened — a position opened
    # yesterday (IN deal outside today's midnight-WIB window) closed manually
    # today would otherwise fail is_manual_of_bot and be silently dropped.
    wide_from_epoch = int((today_start - timedelta(days=7)).timestamp())
    wide_deals = mt5.history_deals_get(wide_from_epoch, to_epoch)
    if wide_deals is None:
        wide_deals = []
    bot_opened = {
        d.position_id for d in wide_deals
        if d.magic == config.MAGIC_NUMBER and d.entry == mt5.DEAL_ENTRY_IN
    }

    closed = []
    for deal in deals:
        if deal.entry != mt5.DEAL_ENTRY_OUT:
            continue
        if symbol is not None and deal.symbol != symbol:
            continue
        # Accept bot-magic closes; also accept magic=0 (external manual close)
        # but only for positions this bot actually opened.
        is_bot_close = deal.magic == config.MAGIC_NUMBER
        is_manual_of_bot = deal.magic == 0 and deal.position_id in bot_opened
        if not (is_bot_close or is_manual_of_bot):
            continue
        # DEAL_ENTRY_OUT: deal.type == 0 (BUY deal) closes a SELL position, deal.type == 1 (SELL deal) closes a BUY position
        pos_type = "SELL" if deal.type == 0 else "BUY"

        # Reason label. MT5 mobile manual close often leaves deal.reason empty
        # (or magic=0), so infer "manual" from magic=0 on a bot-opened position
        # instead of showing "unknown".
        deal_reason = getattr(deal, "reason", None)
        if is_manual_of_bot or not deal_reason:
            reason = "manual"
        else:
            reason = {
                mt5.DEAL_REASON_SL: "SL",
                mt5.DEAL_REASON_TP: "TP",
                mt5.DEAL_REASON_MOBILE: "manual (mobile)",
                mt5.DEAL_REASON_WEB: "manual (web)",
                mt5.DEAL_REASON_CLIENT: "manual",
                mt5.DEAL_REASON_EXPERT: "bot",
                mt5.DEAL_REASON_ROLLOVER: "rollover",
                mt5.DEAL_REASON_SO: "stop-out",
                mt5.DEAL_REASON_VMARGIN: "margin",
                mt5.DEAL_REASON_SPLIT: "split",
            }.get(deal_reason, f"code-{deal_reason}")

        closed.append({
            "ticket": deal.position_id,
            "symbol": deal.symbol,
            "profit": deal.profit + deal.swap + deal.commission,
            "reason": reason,
            "comment": getattr(deal, "comment", ""),
            "type": pos_type,
            "time": deal.time,
        })
    return closed


def get_trade_details(ticket):
    """
    Retrieves full execution details for a closed position ticket from MT5 deal history.
    Returns a dict with entry_price, exit_price, pos_type, volume, entry_time, exit_time,
    duration_min, profit, reason, and points_pnl.
    """
    terminal_info = mt5.terminal_info()
    if terminal_info is None or not getattr(terminal_info, "connected", False):
        if not initialize_mt5():
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

        # Time formatting
        t_in = datetime.fromtimestamp(in_deal.time)
        t_out = datetime.fromtimestamp(out_deal.time)
        duration_sec = max(0, out_deal.time - in_deal.time)
        duration_min = round(duration_sec / 60.0, 1)

        # Net profit
        net_profit = sum(d.profit + d.swap + d.commission for d in deals)

        # Reason
        deal_reason = getattr(out_deal, "reason", None)
        if out_deal.magic == 0:
            reason = "manual"
        else:
            reason = {
                mt5.DEAL_REASON_SL: "SL",
                mt5.DEAL_REASON_TP: "TP",
                mt5.DEAL_REASON_MOBILE: "manual (mobile)",
                mt5.DEAL_REASON_WEB: "manual (web)",
                mt5.DEAL_REASON_CLIENT: "manual",
                mt5.DEAL_REASON_EXPERT: "bot",
                mt5.DEAL_REASON_ROLLOVER: "rollover",
                mt5.DEAL_REASON_SO: "stop-out",
                mt5.DEAL_REASON_VMARGIN: "margin",
                mt5.DEAL_REASON_SPLIT: "split",
            }.get(deal_reason, "manual" if not deal_reason else f"code-{deal_reason}")

        # Calculate PnL in points
        sym_info = mt5.symbol_info(symbol)
        point_size = sym_info.point if sym_info else 0.01
        if pos_type == "BUY":
            price_diff = exit_price - entry_price
        else:
            price_diff = entry_price - exit_price

        points_pnl = round(price_diff / point_size) if point_size else 0

        return {
            "ticket": ticket,
            "symbol": symbol,
            "type": pos_type,
            "volume": volume,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "entry_time": t_in.strftime("%Y-%m-%d %H:%M:%S"),
            "exit_time": t_out.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_min": duration_min,
            "profit": net_profit,
            "reason": reason,
            "points_pnl": points_pnl,
        }
    except Exception as e:
        print(f"[MT5 CONNECTOR WARNING] Gagal mengambil detail trade #{ticket}: {e}")
        return None

# Retcodes that mean "broker wants a fresh price/wider deviation" — worth a retry.
_RETRYABLE_RETCODES = {
    getattr(mt5, "TRADE_RETCODE_PRICE_CHANGED", 10020),
    getattr(mt5, "TRADE_RETCODE_PRICE_OFF", 10021),
    getattr(mt5, "TRADE_RETCODE_REQUOTE", 10004),
    getattr(mt5, "TRADE_RETCODE_REJECT", 10013),
}

_MAX_RETRIES = 2  # up to 2 retries before falling back to ORDER_FILLING_RETURN

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
    fm = info.filling_mode
    if fm & 1:
        return mt5.ORDER_FILLING_FOK
    elif fm & 2:
        return mt5.ORDER_FILLING_IOC
    else:
        return mt5.ORDER_FILLING_RETURN


def _send_with_retry(build_request, symbol, label):
    """
    Send a request via mt5.order_send with retries and fill-policy fallback.

    `build_request(deviation, fill_policy)` must return the dict to send.
    Returns the raw mt5.order_send result (caller inspects retcode).
    """
    policy = get_filling_policy(symbol)

    # Attempt 1: detected policy at base deviation
    req = build_request(config.DEVIATION, policy)
    result = mt5.order_send(req)

    # If broker said price changed/off/requote, retry with fresh tick + widened deviation
    for attempt in range(_MAX_RETRIES):
        if not result or result.retcode not in _RETRYABLE_RETCODES:
            break
        widen = config.DEVIATION + (5 * (attempt + 1))
        print(f"[MT5] {label} retry {attempt + 1}/{_MAX_RETRIES}: retcode={result.retcode}, "
              f"widening deviation to {widen} pts")
        req = build_request(widen, policy)
        result = mt5.order_send(req)

    # Fall back to RETURN ONLY if original filling policy was not RETURN, and broker complains about invalid filling mode (10030)
    if result and result.retcode == getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030) and policy != mt5.ORDER_FILLING_RETURN:
        print(f"[MT5] {label} fallback to ORDER_FILLING_RETURN (retcode was {result.retcode})")
        req = build_request(config.DEVIATION, mt5.ORDER_FILLING_RETURN)
        result = mt5.order_send(req)

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

    # Set default SL/TP from config if not specified by AI (per-symbol defaults)
    default_sl = config.default_sl_points_for(symbol)
    default_tp = config.default_tp_points_for(symbol)
    if not sl and default_sl:
        sl = price - (default_sl * point) if action == "BUY" else price + (default_sl * point)
    if not tp and default_tp:
        tp = price + (default_tp * point) if action == "BUY" else price - (default_tp * point)

    def _build(deviation, fill_policy):
        # Refresh tick so each retry uses current price
        live_tick = mt5.symbol_info_tick(symbol)
        if live_tick is not None:
            live_price = live_tick.ask if action == "BUY" else live_tick.bid
        else:
            live_price = price
        if action == "BUY":
            live_sl = live_price - (sl_points * point) if sl_points else (live_price - (default_sl * point) if default_sl else 0.0)
            live_tp = live_price + (tp_points * point) if tp_points else (live_price + (default_tp * point) if default_tp else 0.0)
        else: # SELL
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
            "magic": config.MAGIC_NUMBER,  # Unique ID for our bot trades
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
