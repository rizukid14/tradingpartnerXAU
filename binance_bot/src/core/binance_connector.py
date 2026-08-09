"""
Binance Spot REST Connector.

Menggantikan mt5_connector untuk bot Binance. Semua request via REST /api/v3/*
(per changelog Binance 2026: /api/v1/* sudah retire). Signed request pakai
HMAC-SHA256 dengan percent-encode payload SEBELUM signing (wajib sejak 2026-01-15).

Fungsi utama:
  get_klines(symbol, interval, limit)   -> DataFrame candle (open/high/low/close/volume/time)
  get_ticker(symbol)                    -> {bid, ask, price, spread_pct}
  get_account_balance_usdt()            -> equity USDT (free + locked)
  get_asset_balance(symbol)             -> qty aset (BTC/ETH) yang dimiliki
  get_symbol_info(symbol)               -> step_size, min_notional, tick_size, dll (dari exchangeInfo)
  place_market_order(symbol, side, qty) -> order market BUY/SELL
  place_oco_order(symbol, side, qty, stop_price, sl_price, tp_price) -> OCO (SL stop-limit + TP limit)
  cancel_oco_order(symbol, order_list_id)
  get_open_orders(symbol)               -> order aktif (OCO)
  get_my_trades(symbol)                 -> history trade (untuk P/L)
  get_balance_and_positions()           -> posisi spot (aset) + USDT

Semua fungsi return dict/list, tidak pernah raise — log error & return None/[].
"""
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime

import pandas as pd

import config

log = logging.getLogger("binance_bot")


def _http_get(path, params=None, signed=False):
    """GET request ke Binance REST. Return parsed JSON, atau None kalau error."""
    url = config.REST_BASE + path
    if params is None:
        params = {}

    # Signed: tambah timestamp + recvWindow, percent-encode, HMAC signature
    if signed:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 10000
        query = urllib.parse.urlencode(params)  # percent-encode otomatis
        signature = hmac.new(
            config.BINANCE_SECRET.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        query += f"&signature={signature}"
        url += "?" + query
        req = urllib.request.Request(url, headers={"X-MBX-APIKEY": config.BINANCE_API_KEY})
    else:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)

    # Retry dengan backoff (rate limit / network)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429 or e.code == 418:  # rate limited
                wait = 2 ** attempt * 2
                log.warning(f"[BINANCE] Rate limited ({e.code}), retry in {wait}s: {body}")
                time.sleep(wait)
                continue
            if e.code == 401 or e.code == 403:
                log.error(f"[BINANCE] Auth error ({e.code}): {body} — cek API key/permission")
                return None
            log.error(f"[BINANCE] HTTP {e.code}: {body}")
            return None
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            log.error(f"[BINANCE] Request error {path}: {e}")
            return None
    return None


def _http_post(path, params):
    """POST signed request (order placement)."""
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 10000
    query = urllib.parse.urlencode(params)
    signature = hmac.new(
        config.BINANCE_SECRET.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    query += f"&signature={signature}"
    url = config.REST_BASE + path + "?" + query

    req = urllib.request.Request(url, method="POST",
                                 headers={"X-MBX-APIKEY": config.BINANCE_API_KEY})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code in (429, 418):
                wait = 2 ** attempt * 2
                log.warning(f"[BINANCE] Rate limited POST ({e.code}), retry in {wait}s: {body}")
                time.sleep(wait)
                continue
            log.error(f"[BINANCE] POST {path} HTTP {e.code}: {body}")
            return None
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            log.error(f"[BINANCE] POST {path} error: {e}")
            return None
    return None


# ---------------------------------------------------------------------------
# MARKET DATA
# ---------------------------------------------------------------------------
def get_klines(symbol, interval, limit=50):
    """Kline (candle) → DataFrame dengan kolom time/open/high/low/close/volume."""
    data = _http_get("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    if not data:
        return None
    rows = []
    for k in data:
        rows.append({
            "time": datetime.fromtimestamp(k[0] / 1000),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "tick_volume": float(k[5]),
        })
    df = pd.DataFrame(rows)
    return df


def get_ticker(symbol):
    """Best bid/ask + last price + spread %."""
    # bookTicker = best bid/ask (murah, weight 2)
    bt = _http_get("/api/v3/ticker/bookTicker", {"symbol": symbol})
    if not bt:
        return None
    bid = float(bt.get("bidPrice", 0))
    ask = float(bt.get("askPrice", 0))
    if bid <= 0 or ask <= 0:
        return None
    price = (bid + ask) / 2
    return {
        "bid": bid,
        "ask": ask,
        "price": price,
        "spread_usd": ask - bid,
        "spread_pct": (ask - bid) / price * 100,
        "point": 0.01,  # tick size BTCUSDT (perbaiki via get_symbol_info)
    }


# ---------------------------------------------------------------------------
# SYMBOL INFO (filters: step_size, min_notional, tick_size)
# ---------------------------------------------------------------------------
_symbol_info_cache = {}


def get_symbol_info(symbol):
    """Ambil filters LOT_SIZE (stepSize, minQty) + MIN_NOTIONAL + PRICE_FILTER (tickSize) dari exchangeInfo."""
    if symbol in _symbol_info_cache:
        return _symbol_info_cache[symbol]
    data = _http_get("/api/v3/exchangeInfo", {"symbol": symbol})
    if not data or "symbols" not in data or not data["symbols"]:
        return None
    s = data["symbols"][0]
    info = {"symbol": symbol, "status": s.get("status"), "filters": {}}
    for f in s.get("filters", []):
        ftype = f.get("filterType")
        if ftype == "LOT_SIZE":
            info["filters"]["step_size"] = float(f.get("stepSize", 0.00001))
            info["filters"]["min_qty"] = float(f.get("minQty", 0.00001))
        elif ftype == "MIN_NOTIONAL":
            info["filters"]["min_notional"] = float(f.get("notional", 0))
        elif ftype == "PRICE_FILTER":
            info["filters"]["tick_size"] = float(f.get("tickSize", 0.01))
    _symbol_info_cache[symbol] = info
    return info


def round_qty(symbol, qty):
    """Round kuantitas ke step size symbol (floor ke kelipatan step)."""
    info = get_symbol_info(symbol)
    if not info:
        return qty
    step = info["filters"].get("step_size", 0.00001)
    if step <= 0:
        return qty
    # floor ke kelipatan step
    rounded = int(qty / step) * step
    # presisi = jumlah desimal step (mis. step 0.00001 → 5 desimal)
    step_str = f"{step:.10f}".rstrip("0")
    decimals = len(step_str.split(".")[-1]) if "." in step_str else 0
    return round(rounded, decimals)


def validate_order(symbol, qty, price=None):
    """Validasi order sebelum kirim: min notional + min qty. Return (ok, reason)."""
    info = get_symbol_info(symbol)
    if not info:
        return True, ""
    min_notional = info["filters"].get("min_notional", 0)
    min_qty = info["filters"].get("min_qty", 0)
    if min_qty and qty < min_qty:
        return False, f"qty {qty} < min_qty {min_qty}"
    if price and min_notional and qty * price < min_notional:
        return False, f"notional {qty*price:.2f} < min_notional {min_notional}"
    return True, ""


# ---------------------------------------------------------------------------
# ACCOUNT & BALANCE
# ---------------------------------------------------------------------------
def get_account():
    """Full account info (balances)."""
    return _http_get("/api/v3/account", signed=True)


def get_account_balance_usdt():
    """Total equity USDT (free + locked semua aset yang bukan USDT dihitung? tidak — hanya USDT)."""
    acc = get_account()
    if not acc:
        return 0.0
    for b in acc.get("balances", []):
        if b["asset"] == "USDT":
            return float(b["free"]) + float(b["locked"])
    return 0.0


def get_asset_balance(symbol):
    """Qty aset base (mis. BTC) yang dimiliki. symbol='BTCUSDT' → asset 'BTC'."""
    acc = get_account()
    if not acc:
        return 0.0
    base = symbol.replace("USDT", "")
    for b in acc.get("balances", []):
        if b["asset"] == base:
            return float(b["free"]) + float(b["locked"])
    return 0.0


# ---------------------------------------------------------------------------
# ORDERS
# ---------------------------------------------------------------------------
def place_market_order(symbol, side, qty):
    """Market order BUY/SELL. Return dict hasil atau None."""
    if config.DRY_RUN:
        log.info(f"[DRY RUN] Market {side} {qty} {symbol}")
        return {"status": "SUCCESS", "dry_run": True, "symbol": symbol, "side": side, "qty": qty}
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quantity": f"{qty:.8f}",
        "newOrderRespType": "FULL",
    }
    return _http_post("/api/v3/order", params)


def place_oco_order(symbol, side, qty, stop_price, sl_price, tp_price):
    """
    OCO order: TP limit + SL stop-limit sekaligus (one-cancels-other).
    side: BUY/SELL. stop_price = harga pemicu SL, sl_price = harga limit SL,
    tp_price = harga limit TP. Berlaku untuk posisi yang SUDAH ada.
    """
    if config.DRY_RUN:
        log.info(f"[DRY RUN] OCO {side} {qty} {symbol} (SL@{sl_price}, TP@{tp_price})")
        return {"status": "SUCCESS", "dry_run": True}
    params = {
        "symbol": symbol,
        "side": side,
        "quantity": f"{qty:.8f}",
        "price": f"{tp_price:.2f}",          # limit price (TP)
        "stopPrice": f"{stop_price:.2f}",    # trigger SL
        "stopLimitPrice": f"{sl_price:.2f}", # SL limit price
        "stopLimitTimeInForce": "GTC",
        "newOrderRespType": "FULL",
    }
    return _http_post("/api/v3/orderList/oco", params)


def cancel_order(symbol, order_id):
    """Cancel satu order. Return dict atau None."""
    return _http_post("/api/v3/order", {"symbol": symbol, "orderId": order_id})


def cancel_all_open_orders(symbol):
    """Cancel semua order aktif symbol (mis. OCO yang tersisa)."""
    return _http_post("/api/v3/openOrders", {"symbol": symbol})


def get_open_orders(symbol):
    """Order aktif (termasuk OCO). Return list."""
    data = _http_get("/api/v3/openOrders", {"symbol": symbol}, signed=True)
    return data or []


def get_my_trades(symbol, limit=100):
    """Trade history (fills) — untuk P/L & deteksi close. Return list."""
    data = _http_get("/api/v3/myTrades", {"symbol": symbol, "limit": limit}, signed=True)
    return data or []


def get_closed_positions_today(symbol=None):
    """
    Deteksi posisi yang closed (dari myTrades). Karena spot tidak punya konsep
    'position close' seperti MT5, ini menghitung SEMUA sell fills hari ini
    (realisasi P/L). Return list deal: {ticket, symbol, profit, time, side}.
    """
    data = get_my_trades(symbol or config.SYMBOL, limit=100)
    if not data:
        return []
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
    deals = []
    for t in data:
        if t.get("time", 0) < today_start:
            continue
        # SELL fill = realisasi (exit). BUY fill = entry.
        side = t.get("side", "")
        if side != "SELL":
            continue
        deals.append({
            "ticket": t.get("orderId"),
            "symbol": t.get("symbol"),
            "profit": float(t.get("quoteQty", 0)) - float(t.get("commission", 0)),
            "side": "SELL",
            "time": t.get("time"),
        })
    return deals


def get_balance_and_positions():
    """Return (balance_usdt, positions) — positions = aset non-USDT yang dimiliki."""
    acc = get_account()
    if not acc:
        return 0.0, []
    balance = 0.0
    positions = []
    for b in acc.get("balances", []):
        total = float(b["free"]) + float(b["locked"])
        if b["asset"] == "USDT":
            balance = total
        elif total > 0:
            positions.append({"asset": b["asset"], "qty": total})
    return balance, positions


def server_time():
    """Cek koneksi + server time."""
    data = _http_get("/api/v3/time")
    return data.get("serverTime") if data else None
