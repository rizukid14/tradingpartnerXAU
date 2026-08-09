"""
MTF Analyst untuk bot Binance — analisis struktur timeframe lebih tinggi (H1/H4).

Berbeda dari bot MT5 (yang pakai LLM untuk analisis MTF), di sini analisis
dihitung dari INDIKATOR murni (EMA20/EMA50, RSI, ATR, price position) —
cepat, gratis, dan deterministik. Hasilnya di-inject ke prompt proposer.

Cache per timeframe + symbol (refresh tiap N menit) biar tidak hitung ulang
terus-terusan.
"""
import logging
import os
import time

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

import config
from src.core import ccxt_connector as connector

log = logging.getLogger("binance_bot")

# Timeframe MTF yang dianalisis (di luar timeframe utama M5)
# M30 = konteks intraday terdekat, H1 = arah lebih besar — cukup utk scalping M5
MTF_TIMEFRAMES = ["30m", "1h"]
CACHE_TTL_SECONDS = 900  # 15 menit


def _add_indicators(df):
    """Tambah RSI(14), EMA20, EMA50, ATR(14) ke DataFrame."""
    if df is None or len(df) < 30:
        return df
    df = df.copy()
    df["rsi_14"] = RSIIndicator(close=df["close"], window=14).rsi()
    df["ema_20"] = EMAIndicator(close=df["close"], window=20).ema_indicator()
    df["ema_50"] = EMAIndicator(close=df["close"], window=50).ema_indicator()
    df["atr_14"] = AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=14
    ).average_true_range()
    return df


def analyze_timeframe(symbol, tf):
    """
    Analisis struktur satu timeframe (H1/H4) dari indikator.
    Return string ringkas utk prompt, atau "" kalau gagal.
    """
    df = connector.get_klines(symbol, tf, 100)
    if df is None or len(df) < 20:
        return ""
    df = _add_indicators(df)
    latest = df.iloc[-1]
    price = latest["close"]

    ema20 = latest.get("ema_20")
    ema50 = latest.get("ema_50")
    rsi = latest.get("rsi_14")
    atr = latest.get("atr_14")

    parts = [f"{tf.upper()}:"]
    if ema20 is not None and not pd.isna(ema20):
        if ema50 is not None and not pd.isna(ema50):
            if price > ema20 > ema50:
                trend = "BULLISH"
            elif price < ema20 < ema50:
                trend = "BEARISH"
            else:
                trend = "MIXED/RANGE"
            parts.append(f"trend={trend}")
            parts.append(f"price vs EMA20={price - ema20:+.2f} vs EMA50={price - ema50:+.2f}")
        else:
            # Data pendek (testnet): trend dari EMA20 saja
            trend = "BULLISH" if price > ema20 else ("BEARISH" if price < ema20 else "RANGE")
            parts.append(f"trend={trend} (EMA20 only)")
            parts.append(f"price vs EMA20={price - ema20:+.2f}")
    if rsi is not None and not pd.isna(rsi):
        parts.append(f"RSI={rsi:.1f}")
    if atr is not None and not pd.isna(atr):
        parts.append(f"ATR={atr:.2f}")
    # Support/resistance sederhana: low/high candle terakhir (min 20)
    recent = df.tail(20)
    parts.append(f"support={recent['low'].min():.2f}")
    parts.append(f"resistance={recent['high'].max():.2f}")
    return " | ".join(parts)


_cache = {}


def get_mtf_context(symbol):
    """
    Return MTF context untuk prompt (cache 15 menit per timeframe).
    Contoh output:
      "### MTF CONTEXT (M30/H1)
       M30: trend=BEARISH | price vs EMA20=-85.5 vs EMA50=-320.1 | RSI=42.3 | ATR=210.5 | support=64300 | resistance=65200
       H1: trend=BULLISH | ..."
    """
    global _cache
    now = time.time()
    lines = []
    for tf in MTF_TIMEFRAMES:
        key = f"{symbol}:{tf}"
        cached = _cache.get(key)
        if cached and (now - cached[0]) < CACHE_TTL_SECONDS:
            lines.append(cached[1])
            continue
        try:
            result = analyze_timeframe(symbol, tf)
            if result:
                _cache[key] = (now, result)
                lines.append(result)
        except Exception as e:
            log.warning(f"[MTF] Gagal analisis {tf}: {e}")

    if not lines:
        return ""
    label = "/".join(tf.upper() for tf in MTF_TIMEFRAMES)
    return f"\n### MTF CONTEXT ({label})\n" + "\n".join(lines) + "\n"
