"""
CCXT Connector untuk bot Binance/TokoCrypto (exchange universal).

Menggantikan binance_connector.py — pakai library ccxt yang handle signature,
endpoint, rate limit, dan perbedaan exchange secara otomatis.

Exchange dipilih via config.EXCHANGE: "tokocrypto" (default) atau "binance".
Interface SAMA dengan binance_connector.py — jadi main/risk/consensus tidak berubah.
"""
import logging
import time

import ccxt
import pandas as pd

import config

log = logging.getLogger("binance_bot")

_exchange = None


def get_exchange():
    """Lazy-init ccxt exchange (tokocrypto/binance)."""
    global _exchange
    if _exchange is not None:
        return _exchange

    name = getattr(config, "EXCHANGE", "tokocrypto").lower()
    if name == "binance":
        cls = ccxt.binance
    else:
        cls = ccxt.tokocrypto

    kwargs = {
        "enableRateLimit": True,
        "timeout": 15000,
        "options": {"defaultType": "spot"},
    }
    if config.BINANCE_API_KEY and config.BINANCE_SECRET:
        kwargs["apiKey"] = config.BINANCE_API_KEY
        kwargs["secret"] = config.BINANCE_SECRET

    # Testnet Binance pakai sandbox mode
    if name == "binance" and getattr(config, "TESTNET", False):
        kwargs["sandbox"] = True

    _exchange = cls(kwargs)

    # TokoCrypto: market data (/api/v3/*) ada di www.tokocrypto.site (bukan
    # api.binance.com yang diblokir ISP Indonesia). Order/account di .com.
    if name == "tokocrypto":
        try:
            _exchange.urls["api"]["rest"]["binance"] = "https://www.tokocrypto.site/api/v3"
        except Exception:
            pass

    # Load markets SEKARANG (setelah URL override) — wajib karena ex.market()
    # dipakai di get_symbol_info dan tidak auto-load setelah URL diubah.
    try:
        _exchange.load_markets()
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal load_markets: {e}")

    log.info(f"[EXCHANGE] {_exchange.name} ({'testnet' if getattr(config,'TESTNET',False) else 'live'})")
    return _exchange


def _to_symbol(symbol):
    """'BTCUSDT' -> 'BTC/USDT' (format ccxt)."""
    if "/" in symbol:
        return symbol
    # split di posisi quote: USDT, USDC, IDR, BTC, ETH...
    for quote in ("USDT", "USDC", "IDR", "BUSD"):
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return f"{symbol[:-len(quote)]}/{quote}"
    return symbol


# ---------------------------------------------------------------------------
# MARKET DATA
# ---------------------------------------------------------------------------
def get_klines(symbol, interval, limit=50):
    """Kline (candle) → DataFrame time/open/high/low/close/volume."""
    ex = get_exchange()
    try:
        data = ex.fetch_ohlcv(_to_symbol(symbol), timeframe=interval, limit=limit)
        if not data:
            return None
        rows = []
        for k in data:
            rows.append({
                "time": pd.Timestamp(k[0], unit="ms").to_pydatetime(),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "tick_volume": float(k[5]),
            })
        return pd.DataFrame(rows)
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal get_klines {symbol}: {e}")
        return None


def get_ticker(symbol):
    """Best bid/ask + price + spread."""
    ex = get_exchange()
    try:
        t = ex.fetch_ticker(_to_symbol(symbol))
        bid = t.get("bid") or 0
        ask = t.get("ask") or 0
        if bid <= 0 or ask <= 0:
            return None
        price = (bid + ask) / 2
        return {
            "bid": bid,
            "ask": ask,
            "price": price,
            "spread_usd": ask - bid,
            "spread_pct": (ask - bid) / price * 100,
            "point": 0.01,
        }
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal get_ticker {symbol}: {e}")
        return None


# ---------------------------------------------------------------------------
# SYMBOL INFO (filters: step_size, min_notional, tick_size)
# ---------------------------------------------------------------------------
_symbol_info_cache = {}


def get_symbol_info(symbol):
    """Ambil step_size, min_qty, min_notional, tick_size dari market ccxt."""
    if symbol in _symbol_info_cache:
        return _symbol_info_cache[symbol]
    ex = get_exchange()
    try:
        m = ex.market(_to_symbol(symbol))
        limits = m.get("limits", {})
        info = {
            "symbol": symbol,
            "status": "TRADING",
            "filters": {
                "step_size": (limits.get("amount") or {}).get("min") or 0.00001,
                "min_qty": (limits.get("amount") or {}).get("min") or 0.00001,
                # cost.min sering None di TokoCrypto — biarkan 0, validate_order
                # pakai config.MIN_NOTIONAL_USD sebagai acuan.
                "min_notional": (limits.get("cost") or {}).get("min") or 0.0,
                "tick_size": (limits.get("price") or {}).get("min") or 0.01,
            },
        }
        _symbol_info_cache[symbol] = info
        return info
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal get_symbol_info {symbol}: {e}")
        return None


def round_qty(symbol, qty):
    """Round kuantitas ke step size symbol (floor)."""
    info = get_symbol_info(symbol)
    if not info:
        return qty
    step = info["filters"].get("step_size", 0.00001)
    if step <= 0:
        return qty
    rounded = int(qty / step) * step
    step_str = f"{step:.10f}".rstrip("0")
    decimals = len(step_str.split(".")[-1]) if "." in step_str else 0
    return round(rounded, decimals)


def validate_order(symbol, qty, price=None, sl_pct=None):
    """Validasi min qty + min notional (dengan stoploss reserve)."""
    info = get_symbol_info(symbol)
    if not info:
        return True, ""
    min_qty = info["filters"].get("min_qty", 0)
    # Min notional: pakai config.MIN_NOTIONAL_USD kalau lebih tinggi dari exchange
    min_notional = max(
        info["filters"].get("min_notional", 0),
        getattr(config, "MIN_NOTIONAL_USD", 0) or 0,
    )
    if min_qty and qty < min_qty:
        return False, f"qty {qty} < min_qty {min_qty}"
    if price and min_notional:
        reserve = 1.0
        if sl_pct and abs(sl_pct) < 1.0:
            reserve = 1.0 / (1.0 - abs(sl_pct) / 100.0)
            reserve = max(min(reserve, 1.5), 1.0)
        if qty * price * reserve < min_notional:
            return False, (f"notional {qty*price:.2f} x reserve {reserve:.2f} "
                           f"< min_notional {min_notional} (SL {sl_pct}%)")
    return True, ""


# ---------------------------------------------------------------------------
# ACCOUNT & BALANCE
# ---------------------------------------------------------------------------
def get_account_balance_usdt():
    """Total equity USDT (free + used)."""
    ex = get_exchange()
    try:
        bal = ex.fetch_balance()
        usdt = bal.get("USDT", {})
        return float(usdt.get("free", 0)) + float(usdt.get("used", 0))
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal get_balance: {e}")
        return 0.0


def get_free_usdt():
    """USDT free (tersedia untuk beli)."""
    ex = get_exchange()
    try:
        bal = ex.fetch_balance()
        usdt = bal.get("USDT", {})
        return float(usdt.get("free", 0))
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal get_free_balance: {e}")
        return 0.0


def get_asset_balance(symbol):
    """Qty aset base (mis. BTC) yang dimiliki."""
    ex = get_exchange()
    try:
        base = _to_symbol(symbol).split("/")[0]
        bal = ex.fetch_balance()
        asset = bal.get(base, {})
        return float(asset.get("free", 0)) + float(asset.get("used", 0))
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal get_asset_balance {symbol}: {e}")
        return 0.0


# ---------------------------------------------------------------------------
# ORDERS
# ---------------------------------------------------------------------------
def place_market_order(symbol, side, qty):
    """Market order BUY/SELL. Return dict hasil atau None. Dry-run: simulasi."""
    if config.DRY_RUN:
        ticker = get_ticker(symbol)
        price = ticker["price"] if ticker else 0.0
        slippage = 0.0005
        fill_price = price * (1 + slippage) if side == "BUY" else price * (1 - slippage)
        cost = qty * fill_price
        fee = cost * 0.001
        log.info(f"[DRY RUN] Market {side} {qty} {symbol} @ {fill_price:.2f} "
                 f"(cost ${cost:.2f}, fee ${fee:.4f})")
        return {
            "status": "SUCCESS", "dry_run": True, "symbol": symbol, "side": side,
            "qty": qty, "price": fill_price, "cost": cost, "fee": fee,
            "fills": [{"price": str(fill_price), "qty": str(qty), "commission": str(fee)}],
        }
    ex = get_exchange()
    try:
        order = ex.create_order(_to_symbol(symbol), "market", side.lower(), qty)
        fills = order.get("fills") or []
        price = float(fills[0].get("price", 0)) if fills else float(order.get("average", 0))
        return {
            "status": "SUCCESS", "dry_run": False, "symbol": symbol, "side": side.upper(),
            "qty": qty, "price": price, "order_id": order.get("id"),
            "fills": fills,
        }
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal place_market_order: {e}")
        return {"status": "ERROR", "comment": str(e)}


def place_oco_order(symbol, side, qty, stop_price, sl_price, tp_price):
    """
    OCO order: TP limit + SL stop-limit (one-cancels-other).
    ccxt create_order dengan params triggerPrice + stopLossPrice + takeProfitPrice
    (didukung TokoCrypto & Binance spot).
    """
    if config.DRY_RUN:
        log.info(f"[DRY RUN] OCO {side} {qty} {symbol} (SL@{sl_price:.2f}, TP@{tp_price:.2f})")
        return {"status": "SUCCESS", "dry_run": True, "symbol": symbol,
                "side": side, "qty": qty, "sl": sl_price, "tp": tp_price}
    ex = get_exchange()
    try:
        # Safety ratio: SL limit di sisi aman dari trigger
        if side == "SELL":
            safe_limit = stop_price * 0.99
        else:
            safe_limit = stop_price * 1.01
        order = ex.create_order(
            _to_symbol(symbol), "limit", side.lower(), qty, tp_price,
            params={
                "stopLossPrice": safe_limit,   # trigger SL
                "takeProfitPrice": tp_price,   # TP limit
            },
        )
        return {"status": "SUCCESS", "dry_run": False, "order_id": order.get("id"),
                "symbol": symbol, "side": side.upper(), "qty": qty}
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal place_oco_order: {e}")
        return {"status": "ERROR", "comment": str(e)}


def get_open_orders(symbol):
    """Order aktif (termasuk OCO). Return list."""
    ex = get_exchange()
    try:
        orders = ex.fetch_open_orders(_to_symbol(symbol))
        return [
            {
                "order_id": o.get("id"),
                "side": str(o.get("side", "")).upper(),
                "type": o.get("type"),
                "price": o.get("price"),
                "stop_price": o.get("stopPrice"),
                "status": o.get("status"),
                "symbol": o.get("symbol"),
            }
            for o in (orders or [])
        ]
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal get_open_orders: {e}")
        return []


def get_closed_positions_today(symbol=None):
    """Deal yang closed hari ini (SELL fills = realisasi)."""
    ex = get_exchange()
    try:
        sym = _to_symbol(symbol or config.SYMBOL)
        trades = ex.fetch_my_trades(sym, limit=100)
        if not trades:
            return []
        today_start = int(time.time() - time.time() % 86400) * 1000
        deals = []
        for t in trades:
            if (t.get("timestamp") or 0) < today_start:
                continue
            if str(t.get("side", "")).upper() != "SELL":
                continue
            fee = t.get("fee") or {}
            fee_cost = float(fee.get("cost", 0)) if fee else 0
            deals.append({
                "ticket": t.get("id") or t.get("order"),
                "symbol": symbol or config.SYMBOL,
                "profit": float(t.get("cost", 0)) - fee_cost,
                "side": "SELL",
                "time": t.get("timestamp"),
            })
        return deals
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal get_closed_positions_today: {e}")
        return []


def server_time():
    """Cek koneksi + server time (ms)."""
    ex = get_exchange()
    try:
        return ex.fetch_time()
    except Exception as e:
        log.error(f"[EXCHANGE] Gagal fetch_time: {e}")
        return None
