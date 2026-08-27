"""
Currency Strength Matrix Engine (Boitoki CSM Porting 1:1)
Calculates logarithmic relative strength for 8 major currencies (EUR, USD, JPY, CHF, GBP, AUD, CAD, NZD)
using 7 USD Majors in MetaTrader 5.
"""

import time
import math
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

import config
from config import mt5

WIB = ZoneInfo("Asia/Jakarta")
CURRENCIES = ["EUR", "USD", "JPY", "CHF", "GBP", "AUD", "CAD", "NZD"]
MAJORS_7 = ["EURUSD", "USDJPY", "USDCHF", "GBPUSD", "AUDUSD", "USDCAD", "NZDUSD"]

_csm_cache = {
    "locks": threading.Lock(),
    "entries": {}
}
_CACHE_TTL = 30.0  # 30 detik cache per timeframe agar efisien dan 0 beban MT5

def _get_valid_symbol(pair):
    """Cari format simbol yang valid di broker MT5."""
    candidates = [f"{pair}-ECNc", f"{pair}.c", f"{pair}-ECN", pair, f"{pair}_i"]
    for c in candidates:
        info = mt5.symbol_info(c)
        if info is not None:
            return c
    return None

def calculate_boitoki_csm(timeframe=None, lookback_bars=24):
    """
    Menghitung Relative Currency Strength untuk 8 mata uang utama
    berdasarkan log return dari 7 USD Majors (Algoritma boitoki csm.txt).
    """
    global _csm_cache
    now = time.time()
    tf = timeframe if timeframe is not None else mt5.TIMEFRAME_H1
    cache_key = f"{tf}_{lookback_bars}"

    with _csm_cache["locks"]:
        cached = _csm_cache["entries"].get(cache_key)
        if cached and (now - cached["ts"] < _CACHE_TTL):
            return cached["scores"], cached["ranks"]

        data_v1 = {}
        data_v2 = {}

        for pair in MAJORS_7:
            sym = _get_valid_symbol(pair)
            if not sym:
                return {}, {}

            rates = mt5.copy_rates_from_pos(sym, tf, 0, lookback_bars + 2)
            if rates is None or len(rates) < lookback_bars:
                return {}, {}

            data_v1[pair] = float(rates[-1]['close'])
            data_v2[pair] = float(rates[-lookback_bars]['open'])

        val = {}
        for p in MAJORS_7:
            p1 = data_v1.get(p, 0.0)
            p2 = data_v2.get(p, 0.0)
            if p1 > 0 and p2 > 0:
                val[p] = math.log(p1 / p2) * 10000.0
            else:
                val[p] = 0.0

        scores = {}
        scores["EUR"] = val.get("EURUSD", 0.0)
        scores["JPY"] = -val.get("USDJPY", 0.0)
        scores["CHF"] = -val.get("USDCHF", 0.0)
        scores["GBP"] = val.get("GBPUSD", 0.0)
        scores["AUD"] = val.get("AUDUSD", 0.0)
        scores["CAD"] = -val.get("USDCAD", 0.0)
        scores["NZD"] = val.get("NZDUSD", 0.0)
        scores["USD"] = 0.0

        total_score = sum(scores.values())
        avg_score = total_score / 8.0

        for c in CURRENCIES:
            scores[c] = round(scores[c] - avg_score, 2)

        sorted_curr = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        ranks = {curr: rank + 1 for rank, (curr, _) in enumerate(sorted_curr)}

        _csm_cache["entries"][cache_key] = {
            "ts": now,
            "scores": scores,
            "ranks": ranks
        }

        return scores, ranks

def get_csm_prompt_payload(symbol):
    """
    Menghasilkan blok teks kuantitatif bersih untuk diinjeksi ke Prompt LLM.
    Mendukung Dual-Horizon Flow:
    1. 24-Hour Macro Flow (H1 24-bar) -> Akumulasi tren makro harian
    2. 4-Hour Session Velocity (M15 16-bar) -> Kecepatan rotasi modal sesi aktif
    """
    clean_sym = symbol.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").replace("_i", "").upper()
    if len(clean_sym) < 6 and not ("XAU" in clean_sym or "GOLD" in clean_sym):
        return ""
    if "BTC" in clean_sym:
        return ""

    scores_h1, ranks_h1 = calculate_boitoki_csm(mt5.TIMEFRAME_H1, lookback_bars=24)
    scores_m15, ranks_m15 = calculate_boitoki_csm(mt5.TIMEFRAME_M15, lookback_bars=16)

    if not scores_h1 or not ranks_h1:
        return ""

    sorted_h1 = sorted(scores_h1.items(), key=lambda x: x[1], reverse=True)
    rank_h1_str = ", ".join([f"{c}: {s:+.1f}" for c, s in sorted_h1])

    sorted_m15 = sorted(scores_m15.items(), key=lambda x: x[1], reverse=True) if scores_m15 else []
    rank_m15_str = ", ".join([f"{c}: {s:+.1f}" for c, s in sorted_m15]) if sorted_m15 else "N/A"

    # Khusus Gold (XAUUSD) -> Evaluasi Dual-Horizon Dollar Flow
    if "XAU" in clean_sym or "GOLD" in clean_sym:
        usd_h1 = scores_h1.get("USD", 0.0)
        usd_rank_h1 = ranks_h1.get("USD", 4)
        usd_m15 = scores_m15.get("USD", 0.0) if scores_m15 else usd_h1
        usd_rank_m15 = ranks_m15.get("USD", 4) if ranks_m15 else usd_rank_h1

        if usd_m15 >= 10.0:
            usd_session_impact = "STRONG DOLLAR SURGE (Session Bearish Headwind for Gold)"
        elif usd_m15 >= 5.0:
            usd_session_impact = "MODERATE DOLLAR INFLOW (Mild Headwind for Gold)"
        elif usd_m15 <= -10.0:
            usd_session_impact = "HEAVY DOLLAR OUTFLOW (Bullish Tailwind for Gold)"
        elif usd_m15 <= -5.0:
            usd_session_impact = "MILD DOLLAR WEAKNESS (Supportive for Gold)"
        else:
            usd_session_impact = "BALANCED / NEUTRAL DOLLAR FLOW"

        lines = [
            "### GLOBAL CURRENCY STRENGTH MATRIX (Dual-Horizon Flow)",
            f"- 24-Hour Macro Flow (H1): [{rank_h1_str}]",
            f"- 4-Hour Session Velocity (M15): [{rank_m15_str}]",
            f"- Relative Dollar Flow for Gold ({symbol}):",
            f"  * 24h Macro USD: {usd_h1:+.2f} (Rank #{usd_rank_h1}/8)",
            f"  * 4h Session USD: {usd_m15:+.2f} (Rank #{usd_rank_m15}/8)",
            f"  * Live Session Dollar Impact: {usd_session_impact}"
        ]
        return "\n".join(lines)

    base = clean_sym[:3]
    quote = clean_sym[3:6]

    if base not in CURRENCIES or quote not in CURRENCIES:
        return ""

    base_h1 = scores_h1.get(base, 0.0)
    base_rank_h1 = ranks_h1.get(base, 4)
    quote_h1 = scores_h1.get(quote, 0.0)
    quote_rank_h1 = ranks_h1.get(quote, 4)
    delta_h1 = round(base_h1 - quote_h1, 2)

    base_m15 = scores_m15.get(base, 0.0) if scores_m15 else base_h1
    base_rank_m15 = ranks_m15.get(base, 4) if scores_m15 else base_rank_h1
    quote_m15 = scores_m15.get(quote, 0.0) if scores_m15 else quote_h1
    quote_rank_m15 = ranks_m15.get(quote, 4) if scores_m15 else quote_rank_h1
    delta_m15 = round(base_m15 - quote_m15, 2) if scores_m15 else delta_h1

    if delta_m15 >= 20.0:
        session_flow = "STRONG BULLISH INFLOW"
    elif delta_m15 >= 10.0:
        session_flow = "MODERATE BULLISH INFLOW"
    elif delta_m15 <= -20.0:
        session_flow = "CRITICAL BEARISH OUTFLOW"
    elif delta_m15 <= -10.0:
        session_flow = "MODERATE BEARISH OUTFLOW"
    else:
        session_flow = "BALANCED / SESSION COMPRESSION"

    lines = [
        "### GLOBAL CURRENCY STRENGTH MATRIX (Dual-Horizon Flow)",
        f"- 24-Hour Macro Flow (H1): [{rank_h1_str}]",
        f"- 4-Hour Session Velocity (M15): [{rank_m15_str}]",
        f"- Cross-Currency Relative Velocity ({symbol}):",
        f"  * Base ({base}): 24h = {base_h1:+.2f} (Rank #{base_rank_h1}/8) | 4h Session = {base_m15:+.2f} (Rank #{base_rank_m15}/8)",
        f"  * Quote ({quote}): 24h = {quote_h1:+.2f} (Rank #{quote_rank_h1}/8) | 4h Session = {quote_m15:+.2f} (Rank #{quote_rank_m15}/8)",
        f"  * Net 4-Hour Session Delta ({base} minus {quote}): {delta_m15:+.2f} ({session_flow}) | Net 24h Delta: {delta_h1:+.2f}"
    ]

    return "\n".join(lines)
