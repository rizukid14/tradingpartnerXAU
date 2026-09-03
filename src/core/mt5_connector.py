import time
import atexit
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
from ta.trend import EMAIndicator  # type: ignore
from ta.trend import ADXIndicator  # type: ignore
from ta.momentum import RSIIndicator  # type: ignore
from ta.volatility import AverageTrueRange  # type: ignore

import config
from config import mt5
from src.core.cli_theme import UI
from src.core import telegram_alerts

# Indonesian Western Standard Time (WIB) = UTC+7 (Asia/Jakarta)
WIB = ZoneInfo("Asia/Jakarta")

# =============================================================================
# Cache query MT5 (hot path = loop utama 5 detik)
# =============================================================================
_bot_opened_cache = {"ts": 0.0, "value": None}
_BOT_OPENED_CACHE_TTL = 60.0

_closed_today_cache = {"ts": 0.0, "key": None, "value": None}
_CLOSED_TODAY_CACHE_TTL = 4.0

# point per symbol buat klasifikasi SL (trailing/BEP) - cache ringan per-symbol
_point_cache = {}

_broker_offset_cache = {"ts": 0.0, "value": 0.0}

def get_broker_offset_seconds(symbol="XAUUSD-ECN"):
    """
    Returns the broker's offset from UTC in seconds.
    E.g. if broker is UTC+3 (GMT+3), returns 10800. Cached for 1 hour.
    """
    import time as _t
    now = _t.time()
    if now - _broker_offset_cache["ts"] < 3600 and _broker_offset_cache["value"] != 0.0:
        return _broker_offset_cache["value"]
        
    from datetime import datetime, timezone
    
    # 1. Current UTC time
    now_utc = datetime.now(timezone.utc)
    
    # 2. Current MT5 tick time
    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        # If terminal not connected or symbol invalid, return 0 (no offset adjustment)
        return 0.0
        
    tick_time_utc = datetime.fromtimestamp(tick.time, timezone.utc)
    
    # Broker offset from UTC (e.g. +3 hours)
    broker_offset = tick_time_utc - now_utc
    val = broker_offset.total_seconds()
    _broker_offset_cache["ts"] = now
    _broker_offset_cache["value"] = val
    return val

# get_all_open_positions: dipanggil tiap loop untuk status line CLI.
_open_positions_cache = {"ts": 0.0, "value": None}
_OPEN_POSITIONS_CACHE_TTL = 3.0


def invalidate_deals_cache():
    """Panggil saat order sukses dikirim / posisi ditutup - data deals berubah."""
    _bot_opened_cache["ts"] = 0.0
    _closed_today_cache["ts"] = 0.0


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


def server_to_wib(dt_or_ts):
    """
    Converts an MT5 server epoch timestamp or datetime to an aware WIB (Asia/Jakarta) datetime.
    MT5 timestamps are in the broker server timezone (e.g. GMT+3); this
    shifts them into Asia/Jakarta so candle times match wall-clock WIB.
    """
    if isinstance(dt_or_ts, (int, float)):
        server_ts = float(dt_or_ts)
    elif isinstance(dt_or_ts, datetime):
        if dt_or_ts.tzinfo is not None:
            return dt_or_ts.astimezone(WIB)
        server_ts = dt_or_ts.timestamp()
    else:
        try:
            server_ts = float(dt_or_ts)
        except (ValueError, TypeError):
            return dt_or_ts

    offset_hours = server_utc_offset_hours()
    # Convert server epoch to UTC epoch by subtracting the server's offset
    utc_ts = int(server_ts) - (offset_hours * 3600)
    # Convert UTC epoch to WIB datetime
    return datetime.fromtimestamp(utc_ts, tz=timezone.utc).astimezone(WIB)
_mt5_atexit_registered = False


def _safe_mt5_shutdown():
    """Tutup koneksi MT5 terminal secara bersih saat proses Python berakhir, mencegah zombie headless."""
    try:
        if hasattr(mt5, "shutdown") and callable(mt5.shutdown):
            mt5.shutdown()
    except Exception:
        pass


def _register_mt5_atexit():
    global _mt5_atexit_registered
    if not _mt5_atexit_registered:
        atexit.register(_safe_mt5_shutdown)
        _mt5_atexit_registered = True


def init_mt5():
    """Initializes connection to MT5 terminal and verifies account & symbol availability."""
    if config.DRY_RUN:
        print(f" {UI.YELLOW}[DRY RUN MODE]{UI.RST} Membaca data live MT5 untuk simulasi (eksekusi order riil dinonaktifkan).")

    sym_count = len(getattr(config, "SCANNER_SYMBOLS", [])) if getattr(config, "SCANNER_MODE", False) else 1
    if getattr(config, "SCANNER_MODE", False) and sym_count > 1:
        print(f"[MT5] Connecting to MT5 Terminal for {sym_count} Scanner Universe Symbols...")
    else:
        print(f"[MT5] Connecting to MT5 Terminal for symbol {config.SYMBOL}...")

    # Reset cache nama simbol - koneksi baru = broker/akun baru, suffix bisa beda.
    _valid_symbol_cache.clear()

    if hasattr(mt5, "initialize") and callable(mt5.initialize):
        if not mt5.initialize():
            last_err = mt5.last_error() if hasattr(mt5, "last_error") else "Unknown"
            print(f"[MT5 ERROR] Could not initialize MetaTrader 5 terminal: {last_err}")
            return False
        _register_mt5_atexit()

    if config.MT5_LOGIN and config.MT5_PASSWORD:
        if not mt5.login(int(config.MT5_LOGIN), password=str(config.MT5_PASSWORD), server=str(config.MT5_SERVER)):
            last_err = mt5.last_error() if hasattr(mt5, "last_error") else "Unknown"
            print(f"[MT5 ERROR] Could not login to MT5 account #{config.MT5_LOGIN} on server {config.MT5_SERVER}: {last_err}")
            return False

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

    # Verifikasi apakah tombol Algo Trading di MT5 aktif
    if hasattr(mt5, "terminal_info"):
        term_info = mt5.terminal_info()
        if term_info is not None and hasattr(term_info, "trade_allowed") and not term_info.trade_allowed:
            print(f" {UI.tag('MT5 WARNING', UI.YELLOW)} ⚠️ Algo Trading dinonaktifkan di MetaTrader 5!")
            print("                Aktifkan tombol 'Algo Trading' di toolbar MT5 agar order dapat dieksekusi.")

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
    # ATR (unlike EMA/RSI in the `ta` version used) hard-crashes when the
    # input is shorter than its window (atr[window-1] on a smaller array).
    # Guard so short data requests (e.g. D1 key levels) degrade to NaN.
    if len(df) >= 14:
        df['atr_14'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
    else:
        df['atr_14'] = float('nan')
    # ADX(14) - trend strength filter (20 Agustus, paket anti-FOMC).
    # ADX >= 25 = strong trend (do NOT counter-trend), ADX < 20 = ranging.
    if len(df) >= 30:
        df['adx_14'] = ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=14).adx()
    else:
        df['adx_14'] = float('nan')
    # EMA200 - institutional regime filter (H4/D1 macro context). Valid
    # HANYA kalau data >= 200 bar (fetch 260 di macro_analyst). Short data
    # requests (103 bar prompt utama) degrade to NaN - tidak dipakai di sana.
    if len(df) >= 200:
        df['ema_200'] = EMAIndicator(close=df['close'], window=200).ema_indicator()
    else:
        df['ema_200'] = float('nan')
    
    return df

def get_current_tick(symbol):
    """
    Fetches current Ask, Bid, Spread, Point, Digits for a symbol.
    Returns a dict or None if unavailable.
    """
    symbol = get_valid_trade_symbol(symbol)
    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)

    if tick is None or symbol_info is None:
        return None

    spread = int(round((tick.ask - tick.bid) / symbol_info.point)) if symbol_info.point > 0 else 0

    return {
        "ask": tick.ask,
        "bid": tick.bid,
        "last": getattr(tick, "last", tick.ask),
        "volume": getattr(tick, "volume", 0),
        "time": server_to_wib(tick.time),
        "spread": spread,
        "point": symbol_info.point,
        "digits": symbol_info.digits
    }


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


def get_usd_per_point(symbol, volume=1.0):
    """Menghitung nilai USD per 1 point untuk volume tertentu."""
    try:
        si = mt5.symbol_info(symbol)
        if si and si.trade_tick_size and si.point and si.trade_tick_value:
            return float(si.trade_tick_value * volume * (si.point / si.trade_tick_size))
    except Exception:
        pass
    # Fallback kasar jika MT5 disconnected
    if config.is_fx(symbol):
        return 1.0 * volume
    elif config.is_crypto(symbol):
        return 0.01 * volume
    return 1.0 * volume


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
            "type": "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL",
            "volume": p.volume,
            "entry_price": p.price_open,
            "price_open": p.price_open,
            "current_price": getattr(p, "price_current", p.price_open),
            "sl": p.sl,
            "tp": p.tp,
            "pnl": p.profit,
            "profit": p.profit,
            "swap": getattr(p, "swap", 0.0),
            "magic": p.magic,
            "time": p.time
        })
    return res


def get_all_open_positions(magic=None):
    """Returns ALL open bot-managed positions across every symbol."""
    import time as _t
    now = _t.time()
    target_magic = magic if magic is not None else getattr(config, "MAGIC_NUMBER", None)

    if magic is None and (now - _open_positions_cache["ts"] < _OPEN_POSITIONS_CACHE_TTL):
        if _open_positions_cache["value"] is not None:
            return _open_positions_cache["value"]

    positions = get_open_positions(symbol=None, magic=target_magic)

    if magic is None:
        _open_positions_cache["ts"] = now
        _open_positions_cache["value"] = positions

    return positions


def get_closed_positions_today(symbol=None, lookback_hours=0, magic=None):
    """
    Returns deals that closed (entry OUT) positions opened by this bot today.
    Used for daily P/L, consecutive-loss tracking, and recovery mode.
    Pass symbol= to count only one instrument (per-symbol loss streak);
    omit it to aggregate across all symbols (daily loss cap).
    lookback_hours: include deals closed up to lookback_hours before today_start
    to prevent time-boundary gaps (e.g. at midnight) and sync missed offline closes.
    """
    if config.DRY_RUN:
        return []

    import time as _t
    target_magic = magic if magic is not None else getattr(config, "MAGIC_NUMBER", None)
    cache_key = (symbol, lookback_hours, target_magic)
    now = _t.time()
    if _closed_today_cache["key"] == cache_key and (now - _closed_today_cache["ts"]) < _CLOSED_TODAY_CACHE_TTL:
        return _closed_today_cache["value"]

    # Calculate broker timezone offset from UTC
    broker_offset = get_broker_offset_seconds(symbol or config.SYMBOL)

    from datetime import datetime, timedelta
    now_dt = datetime.now()
    today_start = datetime(now_dt.year, now_dt.month, now_dt.day)
    tomorrow = today_start + timedelta(days=1)
    from_epoch = int((today_start - timedelta(hours=lookback_hours)).timestamp() + broker_offset)
    to_epoch = int(tomorrow.timestamp() + broker_offset)

    deals = mt5.history_deals_get(from_epoch, to_epoch)
    if deals is None:
        return []

    if _bot_opened_cache["value"] is not None and (now - _bot_opened_cache["ts"]) < _BOT_OPENED_CACHE_TTL:
        bot_opened, comm_by_pos, entry_price_by_pos, entry_time_by_pos = _bot_opened_cache["value"]
    else:
        wide_from_epoch = int((today_start - timedelta(days=7)).timestamp() + broker_offset)
        wide_deals = mt5.history_deals_get(wide_from_epoch, to_epoch)
        if wide_deals is None:
            wide_deals = []
        bot_opened = {
            d.position_id for d in wide_deals
            if (target_magic is None or d.magic == target_magic) and d.entry == mt5.DEAL_ENTRY_IN
        }
        # Harga entry dan waktu entry per posisi (dari deal IN)
        entry_price_by_pos = {}
        entry_time_by_pos = {}
        for d in wide_deals:
            if d.entry == mt5.DEAL_ENTRY_IN:
                entry_price_by_pos.setdefault(d.position_id, d.price)
                entry_time_by_pos.setdefault(d.position_id, int(d.time - broker_offset))
        # Biaya per posisi = komisi (IN + OUT) + admin fee swap-free.
        # position.profit dari MT5 TIDAK include komisi/fee - net profit dikurangi semua biaya.
        comm_by_pos = {}
        for d in wide_deals:
            c = getattr(d, "commission", 0.0) or 0.0
            f = getattr(d, "fee", 0.0) or 0.0
            total_cost = c + f
            if total_cost != 0.0:
                comm_by_pos[d.position_id] = comm_by_pos.get(d.position_id, 0.0) + total_cost
        _bot_opened_cache["ts"] = now
        _bot_opened_cache["value"] = (bot_opened, comm_by_pos, entry_price_by_pos, entry_time_by_pos)

    closed = []
    for deal in deals:
        if deal.entry != mt5.DEAL_ENTRY_OUT:
            continue
        if symbol is not None and deal.symbol != symbol:
            continue
        is_bot_close = target_magic is None or deal.magic == target_magic
        is_manual_of_bot = deal.magic == 0 and deal.position_id in bot_opened
        if not (is_bot_close or is_manual_of_bot):
            continue
        pos_type = "SELL" if deal.type == 0 else "BUY"

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

            # Bedakan SL awal vs trailing-stop vs break-even dari HARGA SL yang
            # ke-trigger (deal.price = harga eksekusi) vs harga entry:
            #   - BUY:  SL > entry  -> SL sudah digeser ke atas = trailing/BEP
            #   - SELL: SL < entry  -> SL sudah digeser ke bawah = trailing/BEP
            # Klasifikasi "SL-BEP" (hampir pas di entry, cuma selisih spread) vs
            # "SL-trailing" (jauh melewati entry, profit terkunci).
            if reason == "SL":
                entry_px = entry_price_by_pos.get(deal.position_id)
                if entry_px is not None:
                    exit_px = deal.price
                    point = _point_cache.get(deal.symbol)
                    if point is None:
                        si = mt5.symbol_info(deal.symbol)
                        point = si.point if si else 0.0
                        _point_cache[deal.symbol] = point
                    bep_tol_px = max(5 * point, point)  # tolerance ~5 pts (spread/slippage)
                    if pos_type == "BUY":
                        if exit_px > entry_px:
                            reason = "SL-BEP" if exit_px - entry_px <= bep_tol_px else "SL-trailing"
                    else:  # SELL
                        if exit_px < entry_px:
                            reason = "SL-BEP" if entry_px - exit_px <= bep_tol_px else "SL-trailing"

        # Net profit REAL = profit + swap - komisi total (IN + OUT).
        # comm_by_pos berisi nilai NEGATIF (komisi di-charge) -> ditambahkan langsung.
        net_comm = comm_by_pos.get(deal.position_id, 0.0) or 0.0
        open_time = entry_time_by_pos.get(deal.position_id, int(deal.time - broker_offset))
        opened_today = open_time >= int(today_start.timestamp())

        closed.append({
            "deal_ticket": deal.ticket,
            "ticket": deal.position_id,
            "position_id": deal.position_id,
            "symbol": deal.symbol,
            "direction": pos_type,
            "profit": round(deal.profit + deal.swap + net_comm, 2),
            "commission": round(net_comm, 2),  # NEGATIF; dipakai BEP tolerance dinamis
            "reason": reason,
            "comment": getattr(deal, "comment", ""),
            "type": pos_type,
            "time": int(deal.time - broker_offset),  # Convert to local epoch
            "open_time": open_time,
            "opened_today": opened_today,
        })
    _closed_today_cache["ts"] = now
    _closed_today_cache["key"] = cache_key
    _closed_today_cache["value"] = closed
    return closed


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
        "login": getattr(acc, "login", config.MT5_LOGIN),
        "server": getattr(acc, "server", config.MT5_SERVER),
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.margin_free,
        "leverage": acc.leverage,
        "profit": acc.profit
    }

def get_position_net_profit(position_id):
    """
    Net profit real untuk posisi yang sudah CLOSE - termasuk komisi IN & OUT + admin fee (swap-free).
    MT5 position.profit TIDAK termasuk komisi; komisi di-charge di deal IN (buka)
    dan deal OUT (tutup), masing-masing. Akun swap-free: swap = 0, tapi broker
    charge ADMIN FEE di field `fee` kalau posisi di-hold lewat rollover.
    Profit bersih = profit + swap + comm_IN + comm_OUT + fee.
    Returns None kalau posisi belum punya deal OUT (masih terbuka / data belum sync).
    """
    if config.DRY_RUN:
        return 0.0
    try:
        deals = mt5.history_deals_get(position=position_id)
        if not deals:
            return None
        total_profit = 0.0
        total_swap = 0.0
        total_comm = 0.0
        total_fee = 0.0
        has_out = False
        for d in deals:
            if d.entry == mt5.DEAL_ENTRY_OUT:
                has_out = True
            total_profit += getattr(d, "profit", 0.0) or 0.0
            total_swap += getattr(d, "swap", 0.0) or 0.0
            total_comm += getattr(d, "commission", 0.0) or 0.0
            total_fee += getattr(d, "fee", 0.0) or 0.0
        if not has_out:
            return None
        return round(total_profit + total_swap + total_comm + total_fee, 2)
    except Exception as e:
        print(f"[MT5 CONNECTOR WARNING] get_position_net_profit #{position_id}: {e}")
        return None


def get_position_total_cost(position_id):
    """
    Total BIAYA (komisi IN+OUT + admin fee) untuk satu posisi - nilai ABSOLUT positif.
    Dipakai buat BEP tolerance dinamis: trade 0.01 lot kena komisi 0.06,
    0.10 lot kena 0.60, 0.26 lot kena 1.56 -> tolerance BEP trade itu harus
    lebih besar dari biaya aktualnya (bukan statis 0.04).
    Returns 0.0 kalau tidak ada data (safe fallback -> tolerance statis).
    """
    if config.DRY_RUN:
        return 0.0
    try:
        deals = mt5.history_deals_get(position=position_id)
        if not deals:
            return 0.0
        total_cost = 0.0
        for d in deals:
            total_cost += abs(getattr(d, "commission", 0.0) or 0.0)
            total_cost += abs(getattr(d, "fee", 0.0) or 0.0)
        return round(total_cost, 2)
    except Exception as e:
        print(f"[MT5 CONNECTOR WARNING] get_position_total_cost #{position_id}: {e}")
        return 0.0


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

        # Time formatting (adjust broker time using offset to local WIB)
        broker_offset = get_broker_offset_seconds(symbol)
        t_in = datetime.fromtimestamp(in_deal.time - broker_offset)
        t_out = datetime.fromtimestamp(out_deal.time - broker_offset)
        duration_sec = max(0, out_deal.time - in_deal.time)

        # Net profit REAL = profit + swap + komisi IN + OUT + admin fee (swap-free).
        # Deal IN punya commission (komisi buka), deal OUT punya commission (komisi tutup),
        # admin fee muncul di field `fee` kalau posisi di-hold lewat rollover.
        total_comm = sum(
            (getattr(d, "commission", 0.0) or 0.0) + (getattr(d, "fee", 0.0) or 0.0)
            for d in deals
        )
        profit = out_deal.profit + out_deal.swap + total_comm

        # Reason close yang terbaca (SL/TP/manual/bot/dll) - konsisten dengan
        # get_closed_positions_today. SL dibedakan lagi:
        #   - SL           : SL awal kena (harga SL di sisi loss dari entry)
        #   - SL-BEP       : SL digeser ke break-even (approx entry, selisih spread)
        #   - SL-trailing  : SL digeser melewati entry (profit terkunci)
        deal_reason = getattr(out_deal, "reason", None)
        reason_label = {
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
        }.get(deal_reason, f"code-{deal_reason}" if deal_reason else "manual")
        if reason_label == "SL":
            point = _point_cache.get(symbol)
            if point is None:
                si = mt5.symbol_info(symbol)
                point = si.point if si else 0.0
                _point_cache[symbol] = point
            bep_tol_px = max(5 * point, point)
            if pos_type == "BUY":
                if exit_price > entry_price:
                    reason_label = "SL-BEP" if exit_price - entry_price <= bep_tol_px else "SL-trailing"
            else:  # SELL
                if exit_price < entry_price:
                    reason_label = "SL-BEP" if entry_price - exit_price <= bep_tol_px else "SL-trailing"

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
            "reason": reason_label,
        }
    except Exception as e:
        print(f"[MT5 CONNECTOR WARNING] Could not fetch trade details #{ticket}: {e}")
        return None

# Retcodes that mean "broker wants a fresh price/wider deviation" - worth a retry.
# 10013 (TRADE_RETCODE_INVALID) dimasukkan karena broker ECN (VTMarkets) kadang
# membalas 10013 transien saat market bergerak cepat (bukan requote 10004) -
# request yang sama persis sukses beberapa detik kemudian (terbukti via
# mt5.order_check). Retry dibatasi (_MAX_RETRIES) & build_request selalu refetch
# tick fresh, jadi aman & tidak menutupi bug request yang beneran invalid.
_RETRYABLE_RETCODES = {
    getattr(mt5, "TRADE_RETCODE_PRICE_CHANGED", 10020),
    getattr(mt5, "TRADE_RETCODE_PRICE_OFF", 10021),
    getattr(mt5, "TRADE_RETCODE_REQUOTE", 10004),
    getattr(mt5, "TRADE_RETCODE_REJECT", 10006),
    getattr(mt5, "TRADE_RETCODE_INVALID", 10013),
}

_SUCCESS_RETCODES = {
    getattr(mt5, "TRADE_RETCODE_DONE", 10009),
    getattr(mt5, "TRADE_RETCODE_PLACED", 10008),
    getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
    0,  # Retcode 0 = Standard MT5 OK / Done
    1,  # RES_S_OK
}

def _is_order_success(result):
    """Checks if an order_send result represents successful placement/execution."""
    if result is None:
        return False
    retcode = getattr(result, "retcode", None)
    if retcode in _SUCCESS_RETCODES:
        return True
    comment = str(getattr(result, "comment", "")).strip().lower()
    if comment in ("done", "request executed", "order placed", "success", "placed"):
        return True
    return False

is_order_success = _is_order_success

_MAX_RETRIES = 3
_RETRY_SLEEP_SECONDS = 0.4
# Jeda retry bertahap untuk 10013 transien (broker ECN VTMarkets tolak sesaat,
# pulih dalam hitungan MENIT - terbukti: request identik yang gagal 10013 sukses
# total beberapa menit kemudian, lot 0.01 & 0.04 dua-duanya jalan). Retry 10013:
# 6s -> 15s -> 30s (total block ~51s, bounded). Kalau masih gagal setelah 3x,
# skip bersih - sinyal bisa muncul lagi di cycle berikutnya. Retcode lain tetap
# jeda cepat 0.4s.
_RETRY_SLEEP_10013 = (6.0, 15.0, 30.0)

def _get_exec_mode(info):
    if not info:
        return "N/A"
    for attr in ("trade_exemode", "trade_execution_mode", "execution_mode", "exemode"):
        val = getattr(info, attr, None)
        if val is not None:
            return val
    return "N/A"

_valid_symbol_cache = {}

def get_valid_trade_symbol(symbol):
    """
    Returns the exact tradeable symbol name on the connected MT5 broker.
    Handles broker suffix variations (e.g. XAUUSD-ECN -> XAUUSD-ECNc, BTCUSD -> BTCUSD.c).
    Result di-cache per sesi - resolve & print auto-correct CUKUP SEKALI (bukan tiap dipanggil).
    """
    if not symbol:
        return symbol
    if symbol in _valid_symbol_cache:
        return _valid_symbol_cache[symbol]
    info = mt5.symbol_info(symbol)
    if info is not None and getattr(info, "trade_mode", 0) in (getattr(mt5, "SYMBOL_TRADE_MODE_FULL", 4), 4):
        _valid_symbol_cache[symbol] = symbol
        return symbol

    clean_sym = symbol.strip().upper()
    if clean_sym in ("GOLD", "XAU"):
        clean_sym = "XAUUSD"
    elif clean_sym in ("BTC", "BITCOIN"):
        clean_sym = "BTCUSD"

    candidates = [
        clean_sym + "-ECNc",
        clean_sym + "-ECN",
        clean_sym + ".c",
        clean_sym + "c",
        clean_sym,
        clean_sym + ".ecn",
        clean_sym + "c.ecn",
        clean_sym[:-1] if clean_sym.endswith("C") else clean_sym,
    ]
    for cand in candidates:
        cand_info = mt5.symbol_info(cand)
        if cand_info is not None and getattr(cand_info, "trade_mode", 0) in (getattr(mt5, "SYMBOL_TRADE_MODE_FULL", 4), 4):
            if cand != symbol:
                print(f"[MT5 AUTO-CORRECT] Symbol '{symbol}' auto-corrected to broker symbol: '{cand}'")
            _valid_symbol_cache[symbol] = cand
            return cand

    _valid_symbol_cache[symbol] = symbol
    return symbol

def get_filling_policy(symbol):
    """
    Determines the supported filling policy for a symbol dynamically.
    Returns mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, or mt5.ORDER_FILLING_RETURN.
    """
    symbol = get_valid_trade_symbol(symbol)
    info = mt5.symbol_info(symbol)
    if info is None:
        return mt5.ORDER_FILLING_IOC

    # Bitmask of filling modes:
    # 1: SYMBOL_FILLING_FOK
    # 2: SYMBOL_FILLING_IOC
    fm = getattr(info, "filling_mode", 0)
    if fm & 2:
        return mt5.ORDER_FILLING_IOC
    elif fm & 1:
        return mt5.ORDER_FILLING_FOK
    else:
        return mt5.ORDER_FILLING_IOC

def _safe_order_send(request):
    """Sends order request safely supporting both native MT5 and mt5linux RPC bridge."""
    if getattr(config, "DRY_RUN", False):
        print(f" [DRY RUN HARD SHIELD] order_send dicegah karena DRY_RUN=True.")
        return None
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

def _safe_order_check(request):
    """Pre-checks trade request using mt5.order_check before sending to trade server."""
    try:
        res = mt5.order_check(request)
        if res is not None:
            return res
    except Exception:
        pass
    try:
        return mt5.order_check(request=request)
    except Exception:
        return None

def _send_with_retry(build_request, symbol, label):
    """Send a request via mt5.order_send with retries and fill-policy fallback."""
    policy = get_filling_policy(symbol)
    base_dev = getattr(config, "deviation_for", lambda s: config.DEVIATION)(symbol)

    req = build_request(base_dev, policy)
    if req is None:
        return None  # quote degenerate/stale — dibatalkan bersih (bukan spam retry 10013)

    # Pre-check via MT5 OrderCheck() untuk mendeteksi error margin/filling/autotrading lokal secara instan
    check_res = _safe_order_check(req)
    if check_res is not None:
        check_code = getattr(check_res, "retcode", 0)
        # Structural errors (no money, autotrading disabled, invalid volume, unsupported filling mode)
        if check_code not in (0, getattr(mt5, "TRADE_RETCODE_DONE", 10009)) and check_code in (10019, 10027, 10014, 10030):
            print(f" {UI.tag('MT5 CHECK ERROR', UI.RED)} OrderCheck ditolak terminal! Code {check_code}: {check_res.comment}")
            return check_res

    result = _safe_order_send(req)

    for attempt in range(_MAX_RETRIES):
        if _is_order_success(result) or not result or result.retcode not in _RETRYABLE_RETCODES:
            break
        widen_step = 15 if "XAU" in (symbol or "").upper() else 5
        widen = base_dev + (widen_step * (attempt + 1))
        # 10013 transien (broker ECN): jeda bertahap 6s -> 15s biar liquidity pulih,
        # bukan 0.4s yang cuma spam (terbukti: request identik sukses ~1 menit kemudian).
        if result.retcode == getattr(mt5, "TRADE_RETCODE_INVALID", 10013):
            sleep_sec = _RETRY_SLEEP_10013[attempt] if attempt < len(_RETRY_SLEEP_10013) else _RETRY_SLEEP_10013[-1]
        else:
            sleep_sec = _RETRY_SLEEP_SECONDS
        print(f"[MT5] {label} retry {attempt + 1}/{_MAX_RETRIES}: retcode={result.retcode}, "
              f"widening deviation to {widen} pts (tunggu {sleep_sec:.0f}s sebelum retry)")
        time.sleep(sleep_sec)  # jeda biar broker settle (transient 10013/requote)
        req = build_request(widen, policy)
        if req is None:
            return None
        result = _safe_order_send(req)

    # Fallback fill policy TIDAK dilakukan lagi untuk 10013/10030: bukti empiris
    # order_check - simbol ECN cuma support IOC (filling_mode=2), FOK/RETURN
    # ditolak 10030 "Unsupported filling mode". Mencoba keduanya = 2 request
    # ekstra yang pasti gagal + spam log. Kalau IOC ditolak, ganti policy tidak
    # akan menolong - masalahnya market tipis / request invalid, bukan fill mode.

    return result

def send_trade_order(symbol, action, lot, sl_points=None, tp_points=None, comment=None, sl_price=None, tp_price=None, atr_h1_pts=None):
    """
    Sends a buy/sell trade order to MT5.
    action: "BUY" or "SELL"
    sl_points / tp_points: distance in points for Stop Loss and Take Profit
    comment: label transaksi (default "Multi-LLM Bot"; caller bisa kirim
             per-jenis-LLM, misal "GPT+DeepSeek" / "GPT+Gemini+DeepSeek")
    sl_price / tp_price: absolute price levels for Stop Loss and Take Profit (preferred over points)
    """
    if config.DRY_RUN:
        sl_info = f"{sl_price:.2f}" if sl_price else (f"{sl_points} pts" if sl_points else "none")
        tp_info = f"{tp_price:.2f}" if tp_price else (f"{tp_points} pts" if tp_points else "none")
        print(f"[DRY RUN] Simulasi {action} order untuk {symbol} sebanyak {lot} lot (SL: {sl_info}, TP: {tp_info}).")
        return {"status": "SUCCESS", "comment": "Dry Run Mode Active", "ticket": 0}

    symbol = get_valid_trade_symbol(symbol)
    mt5.symbol_select(symbol, True)

    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)

    if tick is None or symbol_info is None:
        return {"status": "ERROR", "comment": "Symbol info unavailable"}

    point = symbol_info.point

    # Quote-health check (update 15 Agustus): spread 0 (bid==ask) itu NORMAL di akun
    # ECN - order tetap valid & bisa dieksekusi (harga bid==ask saat itu). Yang beneran
    # berbahaya: tick None (quote hilang), tick stale (feed beku - harga basi), spread
    # spike (quote burst).
    if tick is None:
        return {"status": "ERROR", "comment": "Tidak ada quote (tick None) — order dibatalkan"}
    if tick.ask <= 0 or tick.bid <= 0:
        return {"status": "ERROR", "comment": "Quote tidak valid (ask/bid 0) — order dibatalkan"}
    spread_now = (tick.ask - tick.bid) / point if point else 0.0
    tick_age = -1
    if getattr(tick, "time", 0):
        # tick.time itu SERVER time (GMT+3), time.time() = UTC -> kompensasi offset
        # broker dulu (bug 15 Agustus: tanpa ini tick_age selalu -3 jam, stale check
        # nggak pernah trigger - feed beku 3 jam malah ke-deteksi sebagai 'spread 0')
        broker_offset = get_broker_offset_seconds(symbol)
        tick_age = time.time() - (tick.time - broker_offset)
    if tick_age > 10:
        return {"status": "ERROR", "comment": f"Tick stale {tick_age:.0f}s — order dibatalkan"}
    max_spread = config.max_spread_points_for(symbol, atr_h1_pts=atr_h1_pts)
    if spread_now > max_spread:
        return {"status": "ERROR", "comment": (f"Spread spike: {spread_now:.0f} pts > maks {max_spread} pts "
                                               f"— order dibatalkan (hindari entry pas quote burst)")}

    if action == "BUY":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        sl = sl_price if sl_price else (price - (sl_points * point) if sl_points else 0.0)
        tp = tp_price if tp_price else (price + (tp_points * point) if tp_points else 0.0)
    elif action == "SELL":
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        sl = sl_price if sl_price else (price + (sl_points * point) if sl_points else 0.0)
        tp = tp_price if tp_price else (price - (tp_points * point) if tp_points else 0.0)
    else:
        return {"status": "ERROR", "comment": "Invalid action type"}

    default_sl = config.default_sl_points_for(symbol)
    default_tp = config.default_tp_points_for(symbol)
    if not sl and default_sl:
        sl = price - (default_sl * point) if action == "BUY" else price + (default_sl * point)
    if not tp and default_tp:
        tp = price + (default_tp * point) if action == "BUY" else price - (default_tp * point)

    # Simpan request terakhir yang dikirim untuk diagnostik 10013
    last_req = {}

    def _build(deviation, fill_policy):
        nonlocal last_req
        live_tick = mt5.symbol_info_tick(symbol)
        if live_tick is not None:
            live_price = live_tick.ask if action == "BUY" else live_tick.bid
        else:
            live_price = price
        # Guard per-attempt: tick None -> skip retry (feed hilang total)
        if live_tick is None:
            return None
        if action == "BUY":
            live_sl = (live_price - (sl_points * point)) if (sl_points and sl_points > 0) else (sl_price if sl_price else (live_price - (default_sl * point) if default_sl else 0.0))
            live_tp = (live_price + (tp_points * point)) if (tp_points and tp_points > 0) else (tp_price if tp_price else (live_price + (default_tp * point) if default_tp else 0.0))
        else:
            live_sl = (live_price + (sl_points * point)) if (sl_points and sl_points > 0) else (sl_price if sl_price else (live_price + (default_sl * point) if default_sl else 0.0))
            live_tp = (live_price - (tp_points * point)) if (tp_points and tp_points > 0) else (tp_price if tp_price else (live_price - (default_tp * point) if default_tp else 0.0))

        # Validate SL/TP safety distances (anti-10013):
        # - spread dihitung dari ask-bid (atribut live_tick.spread TIDAK ADA di build MT5 ini,
        #   hasattr selalu False -> 2x spread nggak pernah kehitung sebelumnya)
        # - sisi acuan yang benar: SELL ditutup via BUY (trigger di ASK), jadi
        #   SELL: SL >= ask + min_dist, TP <= bid - min_dist
        #   BUY : SL <= bid - min_dist, TP >= ask + min_dist
        spread_pts = ((live_tick.ask - live_tick.bid) / point) if (live_tick and point) else 0.0
        stops_level_pts = getattr(symbol_info, "trade_stops_level", 0) or 0
        min_dist_pts = max(2 * spread_pts, 20, stops_level_pts)
        min_dist = min_dist_pts * point
        ask = live_tick.ask if live_tick else live_price
        bid = live_tick.bid if live_tick else live_price
        if action == "BUY":
            if live_sl > 0 and live_sl >= (bid - min_dist):
                live_sl = bid - min_dist
            if live_tp > 0 and live_tp <= (ask + min_dist):
                live_tp = ask + min_dist
        else:
            if live_sl > 0 and live_sl <= (ask + min_dist):
                live_sl = ask + min_dist
            if live_tp > 0 and live_tp >= (bid - min_dist):
                live_tp = bid - min_dist

        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": round(live_price, symbol_info.digits),
            "sl": round(live_sl, symbol_info.digits),
            "tp": round(live_tp, symbol_info.digits),
            "deviation": deviation,
            "magic": config.MAGIC_NUMBER,
            "comment": (str(comment)[:25].strip() if comment else "Multi-LLM Bot"),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": fill_policy,
        }
        last_req = req
        return req

    print(f" {UI.tag('MT5', UI.BLUE)} Mengirim order: {action} {symbol} {lot} lot pada harga {round(price, symbol_info.digits)} (SL: {round(sl, symbol_info.digits)}, TP: {round(tp, symbol_info.digits)})...")
    result = _send_with_retry(_build, symbol, f"Order {action} {symbol}")

    if result is None:
        # _build return None = tick None saat kirim (feed hilang total)
        telegram_alerts.alert_order_error(symbol, action, lot, sl_points, tp_points, "N/A", "Tick hilang / feed off saat kirim", price=price, sl_price=sl_price, tp_price=tp_price, thesis=comment)
        return {"status": "ERROR", "comment": "Tick hilang saat kirim (feed off) — order dibatalkan"}

    if not _is_order_success(result):
        retcode = getattr(result, "retcode", "N/A") if result else "N/A"
        err_msg = getattr(result, "comment", "No result") if result else "No result"
        print(f" {UI.tag('MT5 ERROR', UI.RED)} Order gagal! Retcode: {retcode}, Pesan: {err_msg}")
        # Buffer untuk Telegram recap gabungan
        req_p = last_req.get("price") if last_req else price
        req_sl = last_req.get("sl") if last_req else sl_price
        req_tp = last_req.get("tp") if last_req else tp_price
        telegram_alerts.alert_order_error(
            symbol=symbol,
            signal=action,
            lot=lot,
            sl_points=sl_points,
            tp_points=tp_points,
            retcode=retcode,
            comment=err_msg,
            price=req_p,
            sl_price=req_sl,
            tp_price=req_tp,
            thesis=comment or "Consensus LLM Trade",
        )
        # Diagnostik 10013: print detail request terakhir + kondisi quote biar bisa
        # dibedakan "request invalid beneran" vs "market tipis/spread 0 transien".
        if retcode == getattr(mt5, "TRADE_RETCODE_INVALID", 10013) and last_req:
            try:
                dbg_tick = mt5.symbol_info_tick(symbol)
                dbg_spread = ((dbg_tick.ask - dbg_tick.bid) / point) if (dbg_tick and point) else -1
                dbg_bid = dbg_tick.bid if dbg_tick else -1
                dbg_ask = dbg_tick.ask if dbg_tick else -1
                print(f"  [DIAG 10013] spread={dbg_spread:.1f} pts | bid={dbg_bid} ask={dbg_ask} | "
                      f"req price={last_req.get('price')} sl={last_req.get('sl')} tp={last_req.get('tp')} "
                      f"dev={last_req.get('deviation')} fill={last_req.get('type_filling')} lot={last_req.get('volume')}")
                # Jarak SL/TP dihitung sesuai arah order (SELL: SL di atas entry, TP di bawah)
                req_type = last_req.get("type")
                if req_type == mt5.ORDER_TYPE_SELL:
                    sl_dist = (last_req.get('sl', 0) - last_req.get('price', 0)) / point if point else 0
                    tp_dist = (last_req.get('price', 0) - last_req.get('tp', 0)) / point if point else 0
                else:
                    sl_dist = (last_req.get('price', 0) - last_req.get('sl', 0)) / point if point else 0
                    tp_dist = (last_req.get('tp', 0) - last_req.get('price', 0)) / point if point else 0
                print(f"  [DIAG 10013] SL jarak {sl_dist:.0f} pts | TP jarak {tp_dist:.0f} pts | "
                      f"stops_level={getattr(symbol_info, 'trade_stops_level', 0)} pts")
            except Exception as diag_e:
                print(f"  [DIAG 10013] gagal ambil detail: {diag_e}")
        if retcode == 10027:
            print("                 💡 Solusi: Aktifkan tombol 'Algo Trading' (icon play/robot) di toolbar atas MetaTrader 5.")
        return {"status": "ERROR", "comment": comment, "code": retcode}

    ticket_no = getattr(result, "order", 0) or getattr(result, "deal", 0)
    print(f" {UI.tag('MT5', UI.GREEN)} Order BERHASIL! Ticket: {ticket_no}")
    invalidate_deals_cache()  # posisi baru dibuka -> bot_opened & closed_today berubah
    return {"status": "SUCCESS", "ticket": ticket_no, "comment": result.comment}

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

    print(f" {UI.tag('MT5', UI.BLUE)} Menutup posisi #{ticket}...")
    result = _send_with_retry(_build, symbol, f"Close #{ticket}")

    if not _is_order_success(result):
        comment = getattr(result, "comment", "No result") if result else "No result"
        print(f" {UI.tag('MT5 ERROR', UI.RED)} Gagal menutup posisi: {comment}")
        return False
    print(f" {UI.tag('MT5', UI.GREEN)} Posisi #{ticket} berhasil ditutup.")
    invalidate_deals_cache()  # deal OUT baru -> closed_today berubah
    return True


def send_pending_order(symbol, entry_type, entry_price, lot, sl_points=None, tp_points=None,
                       comment=None, sl_price=None, tp_price=None, expiration_minutes=None):
    """
    Sends a pending order (BUY_STOP/SELL_STOP/BUY_LIMIT/SELL_LIMIT) to MT5 with
    expiration. When the pending order fills, it becomes a normal position with
    the given SL/TP -- position manager (BEP/trailing) applies as usual.
    entry_type: "buy_stop" | "sell_stop" | "buy_limit" | "sell_limit"
    Returns {"status": "SUCCESS", "ticket": n} or {"status": "ERROR", "comment": ...}
    """
    # resolve order type after symbol lookup
    order_type_map = {
        "buy_stop": mt5.ORDER_TYPE_BUY_STOP,
        "sell_stop": mt5.ORDER_TYPE_SELL_STOP,
        "buy_limit": mt5.ORDER_TYPE_BUY_LIMIT,
        "sell_limit": mt5.ORDER_TYPE_SELL_LIMIT,
    }
    if entry_type not in order_type_map:
        return {"status": "ERROR", "comment": f"Invalid entry_type: {entry_type}"}

    if config.DRY_RUN:
        print(f"[DRY RUN] Simulasi pending {entry_type} untuk {symbol} @ {entry_price} sebanyak {lot} lot "
              f"(SL: {sl_points} pts, TP: {tp_points} pts, expiry {expiration_minutes} menit).")
        return {"status": "SUCCESS", "ticket": 0, "comment": "Dry Run Mode Active"}

    symbol = get_valid_trade_symbol(symbol)
    mt5.symbol_select(symbol, True)

    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)
    if tick is None or symbol_info is None:
        return {"status": "ERROR", "comment": "Symbol info unavailable"}
    point = symbol_info.point

    # Quote-health: pending order perlu harga valid saat pasang (bukan saat eksekusi)
    if tick is None:
        return {"status": "ERROR", "comment": "Tidak ada quote (tick None) — pending dibatalkan"}

    # Expiration: server time (GMT+3). Pakai offset broker biar akurat.
    if not expiration_minutes:
        expiration_minutes = config.get_pending_order_expiry_minutes()
    now_server = datetime.now(timezone.utc) + timedelta(seconds=get_broker_offset_seconds(symbol))
    expiration = int(now_server.timestamp()) + int(expiration_minutes * 60)

    digits = symbol_info.digits
    entry_price = round(float(entry_price), digits)

    # SL/TP absolute dari points (relatif ke entry_price, bukan harga sekarang)
    if sl_points and sl_points > 0:
        sl_price = sl_price if sl_price else (entry_price - (sl_points * point) if entry_type in ("buy_stop", "buy_limit") else entry_price + (sl_points * point))
    if tp_points and tp_points > 0:
        tp_price = tp_price if tp_price else (entry_price + (tp_points * point) if entry_type in ("buy_stop", "buy_limit") else entry_price - (tp_points * point))

    sl_price = round(float(sl_price), digits) if sl_price else 0.0
    tp_price = round(float(tp_price), digits) if tp_price else 0.0

    order_type = order_type_map[entry_type]
    last_req = {}

    def _build(deviation, fill_policy):
        nonlocal last_req
        live_tick = mt5.symbol_info_tick(symbol)
        if live_tick is None:
            return None

        ask = live_tick.ask
        bid = live_tick.bid
        stops_level_pts = getattr(symbol_info, "trade_stops_level", 0) or 0
        min_dist_pts = max(2 * ((ask - bid) / point if point else 0), 20, stops_level_pts)
        min_dist = min_dist_pts * point

        adj_entry = entry_price
        if order_type == mt5.ORDER_TYPE_BUY_STOP and adj_entry <= (ask + min_dist):
            adj_entry = round(ask + min_dist, digits)
        elif order_type == mt5.ORDER_TYPE_SELL_STOP and adj_entry >= (bid - min_dist):
            adj_entry = round(bid - min_dist, digits)
        elif order_type == mt5.ORDER_TYPE_BUY_LIMIT and adj_entry >= (ask - min_dist):
            adj_entry = round(ask - min_dist, digits)
        elif order_type == mt5.ORDER_TYPE_SELL_LIMIT and adj_entry <= (bid + min_dist):
            adj_entry = round(bid + min_dist, digits)

        req = {
            "action": mt5.TRADE_ACTION_PENDING,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": adj_entry,
            "sl": sl_price,
            "tp": tp_price,
            "deviation": deviation,
            "magic": config.MAGIC_NUMBER,
            "comment": (str(comment)[:25].strip() if comment else "Pending"),
            "type_time": mt5.ORDER_TIME_SPECIFIED,
            "expiration": expiration,
            "type_filling": fill_policy,
        }
        last_req = req
        return req

    print(f" {UI.tag('MT5', UI.BLUE)} Pasang pending {entry_type} {symbol} @ {entry_price} "
          f"(exp {expiration_minutes} menit, SL {sl_price}, TP {tp_price})...")
    result = _send_with_retry(_build, symbol, f"Pending {entry_type}")

    if result is None:
        telegram_alerts.alert_order_error(symbol, "PENDING", lot, sl_points, tp_points, "N/A", "Tick hilang saat pasang", price=entry_price, entry_type=entry_type, sl_price=sl_price, tp_price=tp_price, thesis=comment)
        return {"status": "ERROR", "comment": "Tick hilang saat pasang (feed off) — pending dibatalkan"}
    if not _is_order_success(result):
        retcode = getattr(result, "retcode", "N/A") if result else "N/A"
        err_msg = getattr(result, "comment", "No result") if result else "No result"
        print(f" {UI.tag('MT5 ERROR', UI.RED)} Pending gagal! Retcode: {retcode}, Pesan: {err_msg}")
        req_p = last_req.get("price") if last_req else entry_price
        telegram_alerts.alert_order_error(
            symbol=symbol,
            signal="PENDING",
            lot=lot,
            sl_points=sl_points,
            tp_points=tp_points,
            retcode=retcode,
            comment=err_msg,
            price=req_p,
            entry_type=entry_type,
            sl_price=sl_price,
            tp_price=tp_price,
            thesis=comment or f"Pending {entry_type}",
        )
        return {"status": "ERROR", "comment": err_msg, "code": retcode}

    ticket_no = getattr(result, "order", 0) or getattr(result, "deal", 0)
    print(f" {UI.tag('MT5', UI.GREEN)} Pending BERHASIL! Ticket: {ticket_no}")
    return {"status": "SUCCESS", "ticket": ticket_no, "comment": result.comment}


def get_pending_orders(magic=None):
    """Returns list of active pending orders (TRADE_ACTION_PENDING) for the bot's
    magic number. Fields: ticket, symbol, type, price, sl, tp, expiration, comment."""
    try:
        orders = mt5.orders_get()
    except Exception:
        return []
    if orders is None:
        return []
    magic = config.MAGIC_NUMBER if magic is None else magic
    out = []
    for o in orders:
        if o.magic != magic:
            continue
        out.append({
            "ticket": o.ticket,
            "symbol": o.symbol,
            "type": o.type,
            "type_str": _order_type_str(o.type),
            "price": o.price_open,
            "sl": o.sl,
            "tp": o.tp,
            "expiration": o.time_expiration,
            "comment": o.comment,
        })
    return out


def _order_type_str(t):
    """Map MT5 order type int to readable string."""
    try:
        m = {
            mt5.ORDER_TYPE_BUY_STOP: "buy_stop",
            mt5.ORDER_TYPE_SELL_STOP: "sell_stop",
            mt5.ORDER_TYPE_BUY_LIMIT: "buy_limit",
            mt5.ORDER_TYPE_SELL_LIMIT: "sell_limit",
            mt5.ORDER_TYPE_BUY: "BUY",
            mt5.ORDER_TYPE_SELL: "SELL",
        }
        return m.get(t, str(t))
    except Exception:
        return str(t)


def cancel_pending_order(ticket):
    """Cancels a pending order by ticket. Returns bool."""
    if config.DRY_RUN:
        print(f"[DRY RUN] Simulasi cancel pending #{ticket}.")
        return True
    try:
        order = mt5.orders_get(ticket=ticket)
        if order is None or len(order) == 0:
            return False
        o = order[0]
        symbol = get_valid_trade_symbol(o.symbol)
        req = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "symbol": symbol,
            "order": ticket,
            "magic": config.MAGIC_NUMBER,
            "comment": "Cancel pending",
        }
        result = mt5.order_send(req)
        if result is None:
            return False
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f" {UI.tag('MT5 ERROR', UI.RED)} Gagal cancel pending #{ticket}: {result.comment}")
            return False
        print(f" {UI.tag('MT5', UI.GREEN)} Pending #{ticket} dibatalkan.")
        return True
    except Exception as e:
        print(f" [MT5] Error cancel pending #{ticket}: {e}")
        return False
