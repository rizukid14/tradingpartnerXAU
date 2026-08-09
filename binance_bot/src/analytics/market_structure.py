"""
Market Structure Analyst untuk bot Binance — S/R zones, swing, liquidity sweep.

Deteksi deterministik dari candle (gratis, tanpa LLM):
1. Swing highs/lows — fractal sederhana (2 candle kiri/kanan lebih rendah/tinggi)
2. S/R zones — cluster swing yang berdekatan digabung jadi zona
3. Liquidity sweep — candle yang menembus level lama (swing/zone) lalu balik
   (tutup kembali ke dalam range) — sinyal "stoploss hunt" / false breakout

Digunakan untuk memperkaya prompt proposer (GPT/Gemini).
"""
import logging

import pandas as pd

log = logging.getLogger("binance_bot")


def find_swings(df, n=2):
    """Swing highs/lows: fractal. n=2 → 2 candle kiri/kanan.
    Return list of dict {type: 'high'|'low', price, time}."""
    if df is None or len(df) < 2 * n + 1:
        return []
    highs, lows = [], []
    for i in range(n, len(df) - n):
        window_h = df["high"].iloc[i - n:i + n + 1]
        window_l = df["low"].iloc[i - n:i + n + 1]
        if df["high"].iloc[i] == window_h.max() and (df["high"].iloc[i] > window_h.iloc[n - 1] or True):
            highs.append({"type": "high", "price": float(df["high"].iloc[i]),
                          "time": df["time"].iloc[i]})
        if df["low"].iloc[i] == window_l.min() and (df["low"].iloc[i] < window_l.iloc[n - 1] or True):
            lows.append({"type": "low", "price": float(df["low"].iloc[i]),
                         "time": df["time"].iloc[i]})
    return highs + lows


def build_zones(swings, tolerance_pct=0.15, min_hits=2):
    """Cluster swing yang berdekatan (dalam tolerance%) jadi S/R zone.
    Return list of {level, type, hits, strength}."""
    zones = []
    for s in swings:
        price = s["price"]
        if price <= 0:
            continue
        placed = False
        for z in zones:
            if abs(z["level"] - price) / price * 100 <= tolerance_pct:
                z["hits"] += 1
                z["level"] = (z["level"] * (z["hits"] - 1) + price) / z["hits"]
                z["type"] = s["type"]
                placed = True
                break
        if not placed:
            zones.append({"level": price, "type": s["type"], "hits": 1})
    # Hanya zona yang disentuh >= min_hits kali (lebih signifikan)
    strong = [z for z in zones if z["hits"] >= min_hits]
    strong.sort(key=lambda z: z["hits"], reverse=True)
    return strong


def detect_liquidity_sweeps(df, zones, lookback=20):
    """Deteksi liquidity sweep: candle menembus level S/R lama lalu tutup kembali.
    Return list of {level, type, swept_high, swept_low, time, bullish/bearish}."""
    if df is None or len(df) < 2:
        return []
    sweeps = []
    recent = df.tail(lookback)
    for _, row in recent.iterrows():
        for z in zones:
            level = z["level"]
            # Sweep bearish (ke atas → balik): high > level, close < level
            if row["high"] > level and row["close"] < level:
                sweeps.append({
                    "level": level, "type": z["type"], "direction": "bearish",
                    "time": row["time"], "price": float(row["close"]),
                })
            # Sweep bullish (ke bawah → balik): low < level, close > level
            if row["low"] < level and row["close"] > level:
                sweeps.append({
                    "level": level, "type": z["type"], "direction": "bullish",
                    "time": row["time"], "price": float(row["close"]),
                })
    # Unik per level+direction (ambil yang terakhir)
    seen = set()
    uniq = []
    for s in reversed(sweeps):
        key = (round(s["level"], 6), s["direction"])
        if key not in seen:
            seen.add(key)
            uniq.append(s)
    return list(reversed(uniq))[-3:]  # max 3 terakhir


def get_market_structure(df, candle_count=40):
    """
    Analisis struktur pasar dari candle aktif.
    Return string ringkas utk prompt, atau "" kalau data kurang.

    Output:
      ### MARKET STRUCTURE (M5)
      S/R zones: 0.00260 (R, 3x), 0.00275 (R, 2x), 0.00255 (S, 2x)
      Liquidity sweeps (20 candle): bullish @ 0.00255 (12:35), bearish @ 0.00275 (11:50)
    """
    if df is None or len(df) < 30:
        return ""
    df = df.tail(candle_count).reset_index(drop=True)

    # Swing fractal
    swings = find_swings(df, n=2)
    if not swings:
        return ""
    zones = build_zones(swings, tolerance_pct=0.15, min_hits=2)
    if not zones:
        return ""

    lines = []
    # S/R zones — 5 terkuat
    zone_str = []
    for z in zones[:5]:
        kind = z["type"][0].upper()  # R / S
        zone_str.append(f"{z['level']:.5g} ({kind}, {z['hits']}x)")
    lines.append("S/R zones: " + ", ".join(zone_str))

    # Liquidity sweeps
    sweeps = detect_liquidity_sweeps(df, zones, lookback=20)
    if sweeps:
        sweep_str = []
        for s in sweeps:
            t = pd.Timestamp(s["time"]).strftime("%H:%M") if hasattr(s["time"], "strftime") else ""
            sweep_str.append(f"{s['direction']} @ {s['level']:.5g} ({t})")
        lines.append("Liquidity sweeps (20c): " + ", ".join(sweep_str))
    else:
        lines.append("Liquidity sweeps: none recent")

    return "\n### MARKET STRUCTURE (M5)\n" + "\n".join(lines) + "\n"
