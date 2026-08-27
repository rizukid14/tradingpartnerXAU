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
    "ts": 0.0,
    "timeframe": None,
    "ranks": {},
    "scores": {},
    "lock": threading.Lock()
}
_CACHE_TTL = 30.0  # 30 detik cache agar efisien dan 0 beban MT5

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
    tf = timeframe or mt5.TIMEFRAME_H1

    with _csm_cache["lock"]:
        if _csm_cache["scores"] and (now - _csm_cache["ts"] < _CACHE_TTL) and (_csm_cache["timeframe"] == tf):
            return _csm_cache["scores"], _csm_cache["ranks"]

        data_v1 = {}
        data_v2 = {}

        for pair in MAJORS_7:
            sym = _get_valid_symbol(pair)
            if not sym:
                continue
            mt5.symbol_select(sym, True)
            rates = mt5.copy_rates_from_pos(sym, tf, 0, lookback_bars + 1)
            if rates is None or len(rates) < lookback_bars:
                continue
            data_v1[pair] = rates[-1]['close']
            data_v2[pair] = rates[0]['close']

        # Fallback jika data tidak lengkap
        if len(data_v1) < 6:
            return _csm_cache.get("scores", {}), _csm_cache.get("ranks", {})

        def get_val(v1, v2):
            if v2 == 0: return 0.0
            return math.log(v1 / v2) * 10000.0

        def get_val_m(v1, v2, v3, v4):
            val1 = v1 * v3
            val2 = v2 * v4
            if val2 == 0: return 0.0
            return math.log(val1 / val2) * 10000.0

        def get_val_d(v1, v2, v3, v4):
            if v3 == 0 or v4 == 0: return 0.0
            val1 = v1 / v3
            val2 = v2 / v4
            if val2 == 0: return 0.0
            return math.log(val1 / val2) * 10000.0

        EURUSD = get_val(data_v1.get('EURUSD', 1.0), data_v2.get('EURUSD', 1.0))
        USDJPY = get_val(data_v1.get('USDJPY', 1.0), data_v2.get('USDJPY', 1.0))
        USDCHF = get_val(data_v1.get('USDCHF', 1.0), data_v2.get('USDCHF', 1.0))
        GBPUSD = get_val(data_v1.get('GBPUSD', 1.0), data_v2.get('GBPUSD', 1.0))
        AUDUSD = get_val(data_v1.get('AUDUSD', 1.0), data_v2.get('AUDUSD', 1.0))
        USDCAD = get_val(data_v1.get('USDCAD', 1.0), data_v2.get('USDCAD', 1.0))
        NZDUSD = get_val(data_v1.get('NZDUSD', 1.0), data_v2.get('NZDUSD', 1.0))

        EURJPY = get_val_m(data_v1.get('EURUSD', 1.0), data_v2.get('EURUSD', 1.0), data_v1.get('USDJPY', 1.0), data_v2.get('USDJPY', 1.0))
        EURCHF = get_val_m(data_v1.get('EURUSD', 1.0), data_v2.get('EURUSD', 1.0), data_v1.get('USDCHF', 1.0), data_v2.get('USDCHF', 1.0))
        EURGBP = get_val_d(data_v1.get('EURUSD', 1.0), data_v2.get('EURUSD', 1.0), data_v1.get('GBPUSD', 1.0), data_v2.get('GBPUSD', 1.0))
        EURCAD = get_val_m(data_v1.get('EURUSD', 1.0), data_v2.get('EURUSD', 1.0), data_v1.get('USDCAD', 1.0), data_v2.get('USDCAD', 1.0))
        EURAUD = get_val_d(data_v1.get('EURUSD', 1.0), data_v2.get('EURUSD', 1.0), data_v1.get('AUDUSD', 1.0), data_v2.get('AUDUSD', 1.0))
        EURNZD = get_val_d(data_v1.get('EURUSD', 1.0), data_v2.get('EURUSD', 1.0), data_v1.get('NZDUSD', 1.0), data_v2.get('NZDUSD', 1.0))

        GBPCHF = get_val_m(data_v1.get('GBPUSD', 1.0), data_v2.get('GBPUSD', 1.0), data_v1.get('USDCHF', 1.0), data_v2.get('USDCHF', 1.0))
        GBPJPY = get_val_m(data_v1.get('GBPUSD', 1.0), data_v2.get('GBPUSD', 1.0), data_v1.get('USDJPY', 1.0), data_v2.get('USDJPY', 1.0))
        GBPCAD = get_val_m(data_v1.get('GBPUSD', 1.0), data_v2.get('GBPUSD', 1.0), data_v1.get('USDCAD', 1.0), data_v2.get('USDCAD', 1.0))
        GBPAUD = get_val_d(data_v1.get('GBPUSD', 1.0), data_v2.get('GBPUSD', 1.0), data_v1.get('AUDUSD', 1.0), data_v2.get('AUDUSD', 1.0))
        GBPNZD = get_val_d(data_v1.get('GBPUSD', 1.0), data_v2.get('GBPUSD', 1.0), data_v1.get('NZDUSD', 1.0), data_v2.get('NZDUSD', 1.0))

        AUDCHF = get_val_m(data_v1.get('AUDUSD', 1.0), data_v2.get('AUDUSD', 1.0), data_v1.get('USDCHF', 1.0), data_v2.get('USDCHF', 1.0))
        AUDJPY = get_val_m(data_v1.get('AUDUSD', 1.0), data_v2.get('AUDUSD', 1.0), data_v1.get('USDJPY', 1.0), data_v2.get('USDJPY', 1.0))
        AUDCAD = get_val_m(data_v1.get('AUDUSD', 1.0), data_v2.get('AUDUSD', 1.0), data_v1.get('USDCAD', 1.0), data_v2.get('USDCAD', 1.0))
        AUDNZD = get_val_d(data_v1.get('AUDUSD', 1.0), data_v2.get('AUDUSD', 1.0), data_v1.get('NZDUSD', 1.0), data_v2.get('NZDUSD', 1.0))

        NZDCAD = get_val_m(data_v1.get('NZDUSD', 1.0), data_v2.get('NZDUSD', 1.0), data_v1.get('USDCAD', 1.0), data_v2.get('USDCAD', 1.0))
        NZDCHF = get_val_m(data_v1.get('NZDUSD', 1.0), data_v2.get('NZDUSD', 1.0), data_v1.get('USDCHF', 1.0), data_v2.get('USDCHF', 1.0))
        NZDJPY = get_val_m(data_v1.get('NZDUSD', 1.0), data_v2.get('NZDUSD', 1.0), data_v1.get('USDJPY', 1.0), data_v2.get('USDJPY', 1.0))

        CADJPY = get_val_d(data_v1.get('USDJPY', 1.0), data_v2.get('USDJPY', 1.0), data_v1.get('USDCAD', 1.0), data_v2.get('USDCAD', 1.0))
        CADCHF = get_val_d(data_v1.get('USDCHF', 1.0), data_v2.get('USDCHF', 1.0), data_v1.get('USDCAD', 1.0), data_v2.get('USDCAD', 1.0))
        CHFJPY = get_val_d(data_v1.get('USDJPY', 1.0), data_v2.get('USDJPY', 1.0), data_v1.get('USDCHF', 1.0), data_v2.get('USDCHF', 1.0))

        # Akumulasi 8 Currencies (Boitoki Formula)
        EUR = (EURUSD + EURJPY + EURCHF + EURGBP + EURAUD + EURCAD + EURNZD) / 7.0
        USD = (-EURUSD + USDJPY + USDCHF - GBPUSD - AUDUSD + USDCAD - NZDUSD) / 7.0
        JPY = (-EURJPY - USDJPY - CHFJPY - GBPJPY - AUDJPY - CADJPY - NZDJPY) / 7.0
        CHF = (-EURCHF - USDCHF + CHFJPY - GBPCHF - AUDCHF - CADCHF - NZDCHF) / 7.0
        GBP = (-EURGBP + GBPUSD + GBPCHF + GBPJPY + GBPAUD + GBPCAD + GBPNZD) / 7.0
        AUD = (-EURAUD + AUDUSD + AUDJPY + AUDCHF - GBPAUD + AUDCAD + AUDNZD) / 7.0
        CAD = (-EURCAD - USDCAD + CADJPY + CADCHF - GBPCAD - AUDCAD - NZDCAD) / 7.0
        NZD = (-EURNZD + NZDUSD + NZDJPY + NZDCHF - GBPNZD + NZDCAD - AUDNZD) / 7.0

        scores = {
            "EUR": round(EUR, 2), "USD": round(USD, 2), "JPY": round(JPY, 2),
            "CHF": round(CHF, 2), "GBP": round(GBP, 2), "AUD": round(AUD, 2),
            "CAD": round(CAD, 2), "NZD": round(NZD, 2)
        }

        sorted_ranks = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        ranks = {c: i + 1 for i, (c, _) in enumerate(sorted_ranks)}

        _csm_cache["ts"] = now
        _csm_cache["timeframe"] = tf
        _csm_cache["scores"] = scores
        _csm_cache["ranks"] = ranks

        return scores, ranks

def get_csm_prompt_payload(symbol):
    """
    Menghasilkan blok teks kuantitatif bersih untuk diinjeksi ke Prompt LLM.
    Murni data/angka, tanpa kata direktif perintah agar LLM menalar sendiri.
    """
    clean_sym = symbol.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").replace("_i", "").upper()
    if len(clean_sym) < 6 and not ("XAU" in clean_sym or "GOLD" in clean_sym):
        return ""
    if "BTC" in clean_sym:
        return ""

    scores, ranks = calculate_boitoki_csm(mt5.TIMEFRAME_H1, lookback_bars=24)
    if not scores or not ranks:
        return ""

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    rank_str = ", ".join([f"{c}: {s:+.1f}" for c, s in sorted_scores])

    # Khusus Gold (XAUUSD) -> Evaluasi Macro Dollar Flow
    if "XAU" in clean_sym or "GOLD" in clean_sym:
        usd_score = scores.get("USD", 0.0)
        usd_rank = ranks.get("USD", 4)
        if usd_score >= 10.0:
            usd_impact = "STRONG DOLLAR (Macro Bearish Headwind for Gold)"
        elif usd_score >= 5.0:
            usd_impact = "MODERATE DOLLAR STRENGTH (Mild Headwind for Gold)"
        elif usd_score <= -10.0:
            usd_impact = "WEAK DOLLAR DUMPING (Macro Bullish Fuel/Tailwind for Gold)"
        elif usd_score <= -5.0:
            usd_impact = "MILD DOLLAR WEAKNESS (Supportive Tailwind for Gold)"
        else:
            usd_impact = "BALANCED / NEUTRAL DOLLAR FLOW"

        lines = [
            "### GLOBAL CURRENCY STRENGTH MATRIX (Live Boitoki CSM H1)",
            f"- 8-Currency Strength Ranking: [{rank_str}]",
            f"- Macro Dollar Flow for Gold ({symbol}):",
            f"  * Quote Currency (USD): {usd_score:+.2f} (Rank #{usd_rank}/8)",
            f"  * Macro Dollar Impact: {usd_impact}"
        ]
        return "\n".join(lines)

    base = clean_sym[:3]
    quote = clean_sym[3:6]

    if base not in CURRENCIES or quote not in CURRENCIES:
        return ""

    base_score = scores.get(base, 0.0)
    base_rank = ranks.get(base, 4)
    quote_score = scores.get(quote, 0.0)
    quote_rank = ranks.get(quote, 4)
    delta = round(base_score - quote_score, 2)

    if delta >= 20.0:
        flow_status = "STRONG BULLISH FLOW"
    elif delta >= 10.0:
        flow_status = "MODERATE BULLISH FLOW"
    elif delta <= -20.0:
        flow_status = "CRITICAL BEARISH FLOW / SEVERE OUTFLOW"
    elif delta <= -10.0:
        flow_status = "MODERATE BEARISH FLOW"
    else:
        flow_status = "BALANCED / COMPRESSION"

    lines = [
        "### GLOBAL CURRENCY STRENGTH MATRIX (Live Boitoki CSM H1)",
        f"- 8-Currency Strength Ranking: [{rank_str}]",
        f"- Cross-Currency Relative Flow ({symbol}):",
        f"  * Base ({base}): {base_score:+.2f} (Rank #{base_rank}/8)",
        f"  * Quote ({quote}): {quote_score:+.2f} (Rank #{quote_rank}/8)",
        f"  * Net Currency Delta ({base} minus {quote}): {delta:+.2f} ({flow_status})"
    ]

    return "\n".join(lines)
