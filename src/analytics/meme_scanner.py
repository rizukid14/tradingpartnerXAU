"""
meme_scanner.py

Automated Meme Coin & Crypto Scanner using a 2-Stage Approach:
Stage 1: Pure Python Math Filter ($0 token cost) - Scores symbols on Spread/ATR ratio,
         ATR volatility %, EMA trend slope, volume change, and RSI.
Stage 2: (Optional) Multi-LLM Consensus evaluation for top 1-2 candidates.

Generates recommendations saved to data/meme_scan_results.json, sent via Telegram alerts,
and served to the Web Dashboard.
"""

import os
import time
import json
import threading
from datetime import datetime

import requests
import pandas as pd
import numpy as np

import config
from config import mt5
from src.core import mt5_connector as connector

RESULTS_FILE = os.path.join(config.DATA_DIR, "meme_scan_results.json")
_scan_lock = threading.Lock()
_last_scan_time = 0.0


def fetch_dexscreener_trending(limit=10):
    """
    Fetches top trending token boosts from DexScreener API ($0 cost, no API key required).
    Returns list of dicts with token details.
    """
    try:
        url = "https://api.dexscreener.com/token-boosts/top/v1"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            items = resp.json()
            results = []
            if isinstance(items, list):
                for item in items[:limit]:
                    results.append({
                        "url": item.get("url", ""),
                        "chainId": item.get("chainId", ""),
                        "tokenAddress": item.get("tokenAddress", ""),
                        "amount": item.get("amount", 0),
                        "totalAmount": item.get("totalAmount", 0),
                        "icon": item.get("icon", ""),
                        "header": item.get("header", ""),
                        "description": item.get("description", "")
                    })
            return results
    except Exception as e:
        print(f"[DEXSCREENER WARNING] Gagal mengambil data DexScreener: {e}")
    return []


def discover_tokocrypto_symbols():
    """
    Fetches active trading pairs on Tokocrypto and maps base assets (e.g. PEPE, DOGE, SHIB)
    to Tokocrypto symbol strings (e.g. PEPE_USDT, DOGE_USDT).
    Returns dict {base_asset_upper: tokocrypto_symbol}.
    """
    try:
        from src.core import tokocrypto_connector as toko
        raw_list = toko.get_common_symbols()
        result = {}
        for item in raw_list:
            sym = item.get("symbol", "")
            base = item.get("baseAsset", "").upper()
            quote = item.get("quoteAsset", "").upper()
            if quote in ("USDT", "BIDR", "BUSD"):
                # Prioritize USDT quote currency if available
                if base not in result or quote == "USDT":
                    result[base] = sym
        return result
    except Exception as e:
        print(f"[TOKOCRYPTO DISCOVERY WARNING] Gagal mengambil simbol Tokocrypto: {e}")
    return {}


def discover_mt5_crypto_symbols():
    """
    Discovers all tradeable crypto and meme coin symbols available on MT5 terminal.
    Filters symbols based on crypto patterns or MT5 symbol path/currency.
    Returns a sorted list of symbol strings.
    """
    if not mt5:
        return []

    symbols = mt5.symbols_get()
    if not symbols:
        return []

    crypto_symbols = set()
    
    # 1. Add symbols from config CRYPTO_SYMBOLS if valid on broker
    for sym in config.CRYPTO_SYMBOLS:
        info = mt5.symbol_info(sym)
        if info is not None:
            mt5.symbol_select(sym, True)
            crypto_symbols.add(sym)

    # 2. Scan MT5 symbol tree for crypto/meme matches
    for s in symbols:
        name = s.name
        upper_name = name.upper()
        path = getattr(s, "path", "").upper()
        currency_margin = getattr(s, "currency_margin", "").upper()

        is_crypto_pair = (
            "CRYPTO" in path or 
            "CRYPTO" in currency_margin or
            any(pat in upper_name for pat in config.MEME_COIN_PATTERNS) or
            any(coin in upper_name for coin in ["BTC", "ETH", "DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "SOL", "XRP", "ADA", "AVAX", "LINK", "DOT", "LTC", "NEAR", "SUI", "APT"])
        )

        # Exclude Forex cross pairs like EURUSD, GBPUSD that happen to contain 'USD'
        if is_crypto_pair and not upper_name.startswith(("EUR", "GBP", "AUD", "NZD", "CAD", "CHF", "JPY", "XAU", "XAG")):
            # Enable symbol in market watch if not visible
            if not s.visible:
                mt5.symbol_select(name, True)
            crypto_symbols.add(name)

    return sorted(list(crypto_symbols))


def score_symbol(symbol, timeframe=mt5.TIMEFRAME_M30, num_candles=50):
    """
    Stage 1: Scores a crypto/meme coin symbol using pure Python technical math ($0 token cost).
    
    Filters & Scoring:
    - Rejects if spread > MEME_MAX_SPREAD_ATR_RATIO * ATR (untradeable spread noise).
    - Rejects if ATR % < MEME_MIN_ATR_PERCENT (dead market).
    - Scores trend slope (EMA20 vs EMA50), volume ratio, and ATR expansion.

    Returns dict with metrics and composite score (0-100), or None if rejected.
    """
    df = connector.get_market_data(symbol, timeframe=timeframe, num_candles=num_candles)
    if df is None or len(df) < 20:
        return None

    tick = mt5.symbol_info_tick(symbol)
    info = mt5.symbol_info(symbol)
    if tick is None or info is None:
        return None

    current_price = float(df['close'].iloc[-1])
    if current_price <= 0:
        return None

    point = info.point if info.point > 0 else 0.0001
    spread_pts = (tick.ask - tick.bid) / point
    spread_usd = tick.ask - tick.bid

    atr = float(df['atr_14'].iloc[-1]) if 'atr_14' in df.columns else 0.0
    if atr <= 0:
        return None

    atr_pts = atr / point
    atr_pct = (atr / current_price) * 100.0
    spread_atr_ratio = spread_pts / atr_pts if atr_pts > 0 else 999.0

    # Gate 1: Spread-to-ATR check (Reject if spread eats > 30% of average candle movement)
    max_allowed_ratio = getattr(config, "MEME_MAX_SPREAD_ATR_RATIO", 0.30)
    if spread_atr_ratio > max_allowed_ratio:
        return {
            "symbol": symbol,
            "price": current_price,
            "status": "REJECTED",
            "reason": f"Spread/ATR ratio {spread_atr_ratio*100:.1f}% > max {max_allowed_ratio*100:.0f}%",
            "spread_pts": round(spread_pts, 1),
            "atr_pts": round(atr_pts, 1),
            "score": 0.0
        }

    # Gate 2: Minimum volatility check (Reject dead markets)
    min_atr_pct = getattr(config, "MEME_MIN_ATR_PERCENT", 1.0)
    if atr_pct < min_atr_pct:
        return {
            "symbol": symbol,
            "price": current_price,
            "status": "REJECTED",
            "reason": f"ATR {atr_pct:.2f}% < min {min_atr_pct:.1f}%",
            "spread_pts": round(spread_pts, 1),
            "atr_pts": round(atr_pts, 1),
            "score": 0.0
        }

    # --- Math Scoring Breakdown (0 to 100) ---
    
    # 1. Spread Efficiency Score (max 30 pts)
    # Lower spread/ATR ratio = higher score
    spread_efficiency_score = max(0.0, min(30.0, (1.0 - (spread_atr_ratio / max_allowed_ratio)) * 30.0))

    # 2. Volatility Health Score (max 25 pts)
    # Sweet spot: ATR 2.0% - 6.0%
    if atr_pct < 2.0:
        vol_score = (atr_pct / 2.0) * 15.0
    elif atr_pct <= 6.0:
        vol_score = 25.0
    else:
        vol_score = max(10.0, 25.0 - (atr_pct - 6.0) * 2.0)

    # 3. Trend Alignment & Strength (max 25 pts)
    ema20 = float(df['ema_20'].iloc[-1]) if 'ema_20' in df.columns else float(df['close'].iloc[-20:].mean())
    ema50 = float(df['ema_50'].iloc[-1]) if 'ema_50' in df.columns else float(df['close'].iloc[-50:].mean())
    trend_slope = ((ema20 - ema50) / ema50) * 100.0 if ema50 > 0 else 0.0

    if ema20 > ema50:
        trend_dir = "BULLISH"
    elif ema20 < ema50:
        trend_dir = "BEARISH"
    else:
        trend_dir = "SIDEWAYS"

    trend_score = min(25.0, abs(trend_slope) * 10.0)

    # 4. Volume Momentum Score (max 20 pts)
    vol_col = 'real_volume' if 'real_volume' in df.columns and df['real_volume'].sum() > 0 else 'tick_volume'
    recent_vol = float(df[vol_col].iloc[-5:].mean())
    avg_vol = float(df[vol_col].iloc[-20:].mean())
    vol_ratio = (recent_vol / avg_vol) if avg_vol > 0 else 1.0
    volume_score = max(0.0, min(20.0, (vol_ratio - 0.5) * 15.0))

    rsi = float(df['rsi_14'].iloc[-1]) if 'rsi_14' in df.columns else 50.0

    composite_score = round(spread_efficiency_score + vol_score + trend_score + volume_score, 1)

    return {
        "symbol": symbol,
        "price": current_price,
        "score": composite_score,
        "spread_pts": round(spread_pts, 1),
        "spread_usd": round(spread_usd, 6),
        "atr_pts": round(atr_pts, 1),
        "atr_pct": round(atr_pct, 2),
        "spread_atr_ratio_pct": round(spread_atr_ratio * 100.0, 1),
        "trend": trend_dir,
        "trend_slope": round(trend_slope, 2),
        "rsi": round(rsi, 1),
        "vol_ratio": round(vol_ratio, 2),
        "is_meme": config.is_meme_coin(symbol),
        "status": "QUALIFIED"
    }


def score_tokocrypto_fallback_symbols(top_n=5):
    """
    Fallback Scoring Engine: If meme coins are not available on MT5 broker,
    this function scans 24h ticker price & volume data from Tokocrypto API ($0 cost).
    Returns list of scored fallback candidate dicts.
    """
    try:
        from src.core import tokocrypto_connector as toko
        tickers = toko.get_ticker_24hr()
        if not tickers:
            return []

        results = []
        for t in tickers:
            sym = t.get("symbol", "")
            if not sym.endswith("_USDT"):
                continue

            base = sym.replace("_USDT", "").upper()
            if not (config.is_meme_coin(base) or base in ["DOGE", "SHIB", "PEPE", "BONK", "FLOKI", "WIF", "SOL", "POPCAT", "MYRO", "MOG", "BRETT", "MEME", "TRUMP"]):
                continue

            try:
                last_price = float(t.get("lastPrice", 0))
                high_price = float(t.get("highPrice", 0))
                low_price = float(t.get("lowPrice", 0))
                vol_usdt = float(t.get("quoteVolume", 0))
                price_chg_pct = float(t.get("priceChangePercent", 0))
            except Exception:
                continue

            if last_price <= 0 or vol_usdt < 10000:  # Min $10k 24h volume
                continue

            range_pct = ((high_price - low_price) / last_price) * 100.0 if last_price > 0 else 0.0

            # Score breakdown (0-100)
            volatility_score = min(30.0, range_pct * 3.0)
            momentum_score = min(40.0, abs(price_chg_pct) * 2.0)
            volume_score = min(30.0, (vol_usdt / 100000.0) * 10.0)

            composite_score = round(volatility_score + momentum_score + volume_score, 1)

            results.append({
                "symbol": f"{base}_USDT",
                "price": last_price,
                "score": composite_score,
                "spread_pts": 0.0,
                "spread_usd": 0.0,
                "atr_pts": 0.0,
                "atr_pct": round(range_pct, 2),
                "spread_atr_ratio_pct": 0.0,
                "trend": "BULLISH" if price_chg_pct > 0 else "BEARISH",
                "trend_slope": round(price_chg_pct, 2),
                "rsi": 50.0,
                "vol_ratio": round(vol_usdt / 100000.0, 2),
                "is_meme": True,
                "status": "QUALIFIED (Tokocrypto Fallback)",
                "source": "Tokocrypto Spot API",
                "tokocrypto_symbol": sym,
                "tokocrypto_available": True
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_n]
    except Exception as e:
        print(f"[TOKOCRYPTO FALLBACK WARNING] Gagal menghitung skor fallback Tokocrypto: {e}")
    return []


def scan_and_rank(top_n=None):
    """
    Main scanner orchestration function.
    Discovers symbols -> Stage 1 Math Scoring -> Tokocrypto Fallback -> Stage 2 LLM (optional) -> Saves JSON.
    Returns complete scan payload dictionary.
    """
    if top_n is None:
        top_n = getattr(config, "MEME_SCAN_TOP_N", 3)

    symbols = discover_mt5_crypto_symbols()
    scored_results = []
    rejected_results = []

    if symbols:
        for sym in symbols:
            res = score_symbol(sym)
            if not res:
                continue
            if res["status"] == "QUALIFIED":
                scored_results.append(res)
            else:
                rejected_results.append(res)

    # Sort MT5 qualified candidates by composite score descending
    scored_results.sort(key=lambda x: x["score"], reverse=True)
    top_picks = list(scored_results[:top_n])

    # --- Tokocrypto Fallback Pool ---
    # If MT5 has fewer qualified meme picks than top_n, add Tokocrypto candidates
    toko_fallback_picks = score_tokocrypto_fallback_symbols(top_n=top_n)
    mt5_bases = {p["symbol"].upper().replace("-ECNC","").replace("-ECN","").replace(".C","").replace(".ECN","").replace("USD","").replace("USDT","") for p in top_picks}
    
    for tf_pick in toko_fallback_picks:
        tf_base = tf_pick["symbol"].upper().replace("_USDT","").replace("USDT","")
        if tf_base not in mt5_bases and len(top_picks) < top_n:
            top_picks.append(tf_pick)
            scored_results.append(tf_pick)

    # --- Tokocrypto Cross-Reference ---
    tokocrypto_map = discover_tokocrypto_symbols()
    for pick in top_picks:
        sym_upper = pick["symbol"].upper()
        # Extract base coin symbol (e.g. PEPEUSD.c -> PEPE, DOGEUSD -> DOGE)
        clean = sym_upper.replace("-ECNC", "").replace("-ECN", "").replace(".C", "").replace(".ECN", "").replace(".PRO", "").replace(".M", "")
        base = clean.replace("USD", "").replace("USDT", "")
        
        if base in tokocrypto_map:
            pick["tokocrypto_symbol"] = tokocrypto_map[base]
            pick["tokocrypto_available"] = True
        else:
            # Fallback check e.g. PEPE -> PEPE_USDT
            if f"{base}_USDT" in tokocrypto_map.values():
                pick["tokocrypto_symbol"] = f"{base}_USDT"
                pick["tokocrypto_available"] = True
            else:
                pick["tokocrypto_available"] = False

    # --- Stage 2: Multi-LLM Consensus for Top Candidates (Optional) ---
    if getattr(config, "MEME_SCAN_LLM_ENABLED", False) and top_picks:
        for pick in top_picks:
            try:
                sym = pick["symbol"]
                # Query LLMs using existing multi_llm pipeline
                decisions, cons_result, latencies = llm.get_multi_llm_decisions(sym)
                if cons_result:
                    pick["ai_signal"] = cons_result.get("signal", "HOLD")
                    pick["ai_confidence"] = cons_result.get("confidence", 0.0)
                    pick["ai_sl_points"] = cons_result.get("sl_points", 0)
                    pick["ai_tp_points"] = cons_result.get("tp_points", 0)
                    pick["ai_reasoning"] = cons_result.get("details", "")

                    # Auto-trade on Tokocrypto if enabled & BUY signal
                    if getattr(config, "TOKOCRYPTO_ENABLED", False) and getattr(config, "MEME_SCAN_AUTO_TRADE", False):
                        if pick.get("tokocrypto_available") and pick.get("ai_signal") == "BUY":
                            try:
                                from src.core import tokocrypto_connector as toko
                                # Default quantity / trade size (e.g. 10 USDT equivalent)
                                t_sym = pick.get("tokocrypto_symbol")
                                order_res = toko.create_order(symbol=t_sym, side="BUY", order_type="MARKET", quantity=10)
                                pick["tokocrypto_order_result"] = order_res
                            except Exception as te:
                                pick["tokocrypto_order_error"] = str(te)
            except Exception as e:
                pick["ai_error"] = str(e)

    # Fetch global DEX trending tokens from DexScreener API ($0 cost)
    dex_trending = fetch_dexscreener_trending()

    payload = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB"),
        "total_scanned": len(symbols),
        "qualified_count": len(scored_results),
        "rejected_count": len(rejected_results),
        "top_picks": top_picks,
        "all_qualified": scored_results,
        "rejected_samples": rejected_results[:5],
        "dexscreener_trending": dex_trending
    }

    # Save payload to data/meme_scan_results.json
    save_scan_results(payload)

    return payload


def save_scan_results(payload):
    """Saves scan payload to JSON cache file."""
    try:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        with open(RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[MEME SCANNER WARNING] Gagal menyimpan hasil scan: {e}")


def get_latest_scan_results():
    """Reads and returns the latest cached scan payload from JSON file."""
    if os.path.exists(RESULTS_FILE):
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def run_meme_scan_async():
    """Triggers scan in a background thread so main trading loop is never blocked."""
    global _last_scan_time
    now = time.time()
    
    with _scan_lock:
        interval_sec = getattr(config, "MEME_SCAN_INTERVAL_MINUTES", 30) * 60
        if now - _last_scan_time < interval_sec:
            return  # Cooldown not elapsed
        _last_scan_time = now

    def _worker():
        try:
            print("[MEME SCANNER] Memulai pemindaian koin meme & crypto...")
            payload = scan_and_rank()
            print(f"[MEME SCANNER] Scan selesai. Ditemukan {payload.get('qualified_count', 0)} koin layak dari {payload.get('total_scanned', 0)} simbol.")
            
            # Telegram notification
            if getattr(config, "TELEGRAM_ENABLED", False):
                from src.core import telegram_alerts
                telegram_alerts.alert_meme_scan_result(payload.get("top_picks", []))
        except Exception as e:
            print(f"[MEME SCANNER ERROR] Thread scan gagal: {e}")

    threading.Thread(target=_worker, daemon=True).start()
