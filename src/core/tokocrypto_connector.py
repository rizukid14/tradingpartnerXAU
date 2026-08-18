"""
tokocrypto_connector.py

Tokocrypto Spot Exchange API Connector.
Provides public market data (symbols, 24h tickers, klines) and private trading operations
(account balance, spot orders, cancel order) using HMAC-SHA256 signature authentication.
"""

import time
import hmac
import hashlib
import urllib.parse
import requests
import config

BASE_URL = getattr(config, "TOKOCRYPTO_BASE_URL", "https://www.tokocrypto.com").rstrip("/")


def _headers():
    """Returns headers required for Tokocrypto API requests."""
    api_key = getattr(config, "TOKOCRYPTO_API_KEY", "")
    return {
        "X-MBX-APIKEY": api_key,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (TradingBot MT5+Tokocrypto)"
    }


def _generate_signature(params: dict, secret_key: str) -> str:
    """Generates HMAC-SHA256 signature for signed Tokocrypto endpoints."""
    # Convert dict to query string
    query_str = urllib.parse.urlencode(params)
    signature = hmac.new(
        secret_key.encode("utf-8"),
        query_str.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return signature


def is_configured():
    """True if Tokocrypto API credentials are non-empty and enabled."""
    enabled = getattr(config, "TOKOCRYPTO_ENABLED", False)
    api_key = getattr(config, "TOKOCRYPTO_API_KEY", "")
    secret_key = getattr(config, "TOKOCRYPTO_SECRET_KEY", "")
    return bool(enabled and api_key and secret_key)


def get_common_symbols():
    """
    Fetches all trading symbols available on Tokocrypto (Public endpoint).
    Returns list of symbol info dicts or empty list on failure.
    """
    url = f"{BASE_URL}/open/v1/common/symbols"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("list", [])
    except Exception as e:
        print(f"[TOKOCRYPTO WARNING] Gagal mengambil daftar simbol: {e}")
    return []


def get_ticker_24hr(symbol: str = None):
    """
    Fetches 24-hour price change and volume statistics (Public endpoint).
    """
    url = f"{BASE_URL}/open/v1/market/ticker/24hr"
    params = {}
    if symbol:
        params["symbol"] = symbol
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", [])
    except Exception as e:
        print(f"[TOKOCRYPTO WARNING] Gagal mengambil ticker 24hr: {e}")
    return []


def get_account_balances():
    """
    Fetches account balances for all assets (Private signed endpoint).
    Returns list of balance dicts or None on failure.
    """
    if not is_configured():
        return None

    secret_key = getattr(config, "TOKOCRYPTO_SECRET_KEY", "")
    url = f"{BASE_URL}/open/v1/account"
    
    params = {
        "timestamp": int(time.time() * 1000),
        "recvWindow": 5000
    }
    params["signature"] = _generate_signature(params, secret_key)

    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=6)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("balances", [])
            else:
                print(f"[TOKOCRYPTO ERROR] Account response code {data.get('code')}: {data.get('msg')}")
    except Exception as e:
        print(f"[TOKOCRYPTO ERROR] Gagal mengambil saldo akun: {e}")
    return None


def create_order(symbol: str, side, order_type, quantity: float, price: float = None):
    """
    Places a spot order on Tokocrypto (Private signed endpoint).
    
    Parameters:
      symbol: Trading pair e.g. "PEPE_USDT", "DOGE_USDT", "BTC_USDT" (with underscore)
      side: "BUY" / 0 or "SELL" / 1
      order_type: "LIMIT" / 1 or "MARKET" / 2
      quantity: Asset quantity to buy/sell
      price: Price for limit orders (optional for market orders)

    Returns dict with order confirmation or error details.
    """
    if not is_configured():
        return {"status": "error", "message": "Tokocrypto API tidak diaktifkan atau API Key belum diisi di .env"}

    # Format symbol: ensure underscore e.g. PEPEUSDT -> PEPE_USDT
    sym = symbol.upper()
    if "_" not in sym:
        for quote in ["USDT", "BIDR", "BUSD", "BTC", "ETH"]:
            if sym.endswith(quote):
                base = sym[:-len(quote)]
                sym = f"{base}_{quote}"
                break

    # Side mapping: 0 = BUY, 1 = SELL
    if isinstance(side, str):
        side_val = 0 if side.upper() == "BUY" else 1
    else:
        side_val = int(side)

    # Order type mapping: 1 = LIMIT, 2 = MARKET
    if isinstance(order_type, str):
        type_val = 1 if order_type.upper() == "LIMIT" else 2
    else:
        type_val = int(order_type)

    params = {
        "symbol": sym,
        "side": side_val,
        "type": type_val,
        "quantity": str(quantity),
        "timestamp": int(time.time() * 1000),
        "recvWindow": 5000
    }

    if type_val == 1 and price is not None:
        params["price"] = str(price)

    secret_key = getattr(config, "TOKOCRYPTO_SECRET_KEY", "")
    params["signature"] = _generate_signature(params, secret_key)

    url = f"{BASE_URL}/open/v1/orders"

    try:
        resp = requests.post(url, headers=_headers(), data=params, timeout=8)
        if resp.status_code == 200:
            res_data = resp.json()
            if res_data.get("code") == 0:
                print(f"[TOKOCRYPTO ORDER SUCCESS] Order #{res_data.get('data', {}).get('orderId')} {sym} {side}")
                return {"status": "success", "order": res_data.get("data")}
            else:
                msg = f"API Code {res_data.get('code')}: {res_data.get('msg')}"
                print(f"[TOKOCRYPTO ORDER ERROR] {msg}")
                return {"status": "error", "message": msg}
        else:
            return {"status": "error", "message": f"HTTP {resp.status_code}: {resp.text}"}
    except Exception as e:
        print(f"[TOKOCRYPTO ORDER ERROR] Gagal mengirim order: {e}")
        return {"status": "error", "message": str(e)}
