"""
Multi-Horizon Forecasting Engine & Conditional Execution Guard.

Generates multi-horizon price projections (per-symbol: XAU T+15m/T+30m,
BTC T+30m/T+1h/T+4h, plus invalidation boundary)
using the primary LLM (Gemini) and enforces strict conditional trigger rules
("Jika X dan Y sesuai prediksi maka execute") before order submission.
"""
import os
import json
import time
import threading
import config
from src.core import llm_client as llm




CACHE_FILE = os.path.join(config.DATA_DIR, "forecast_cache.json")

CACHE_DURATION_SECONDS = 900  # XAU M5 forecast validity (15 min)

# How close to expiry (in seconds) before we pre-warm in the background.
PRE_WARM_WINDOW_SECONDS = 60


def _cache_duration_seconds(symbol):
    """Forecast cache validity per symbol:
    XAU (M15): 30 minutes (1800 seconds).
    BTC (M30): 1 hour (3600 seconds).
    FX (H1): 2 hours (7200 seconds).
    """
    if config.is_crypto(symbol):
        return 3600
    if "XAU" not in symbol.upper():
        return 7200
    return 1800

class ForecastEngine:
    def __init__(self):
        self._forecast = {}
        self._refresh_lock = threading.Lock()
        self._refresh_in_progress = False
        self._load_cache()

    def _load_cache(self):
        """Load active forecast from disk."""
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r") as f:
                    self._forecast = json.load(f)
        except Exception as e:
            print(f"[FORECAST WARNING] Gagal memuat forecast_cache.json: {e}")

    def _save_cache(self):
        """Save forecast to disk."""
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(self._forecast, f, indent=4)
        except Exception as e:
            print(f"[FORECAST WARNING] Gagal menyimpan forecast_cache.json: {e}")

    def get_active_forecast(self, symbol, df, current_tick, macro_context=None, force_refresh=False):
        """
        Retrieves active forecast matrix.

        - If cache is fresh AND for this symbol: returns immediately.
        - If cache is stale or missing: kicks off a background refresh
          and returns whatever is currently cached (may be empty on first
          call). The caller does NOT block on the refresh.
        - If force_refresh=True: refreshes synchronously (legacy callers).
        """
        now = time.time()
        last_time = float(self._forecast.get("timestamp", 0))
        cache_valid = (
            self._forecast.get("symbol") == symbol
            and (now - last_time) < _cache_duration_seconds(symbol)
        )

        if cache_valid:
            return self._forecast

        if force_refresh:
            return self._do_refresh(symbol, df, current_tick, macro_context)

        # Pre-warm: trigger background refresh, return stale cache immediately
        self._kick_background_refresh(symbol, df, current_tick, macro_context)
        return self._forecast

    def refresh_if_stale(self, symbol, df, current_tick, macro_context=None):
        """
        Synchronous refresh ONLY if cache is stale/missing. Returns the forecast
        dict. Used by main.py pre-warm so the prompt gets fresh data and log
        order stays correct (forecast result prints BEFORE 'Mengirim data').
        Refresh is rare (15 min XAU / 30 min BTC), so blocking here is fine.
        """
        now = time.time()
        last_time = float(self._forecast.get("timestamp", 0))
        cache_valid = (
            self._forecast.get("symbol") == symbol
            and (now - last_time) < _cache_duration_seconds(symbol)
        )
        if cache_valid:
            return self._forecast
        return self._do_refresh(symbol, df, current_tick, macro_context)

    def _kick_background_refresh(self, symbol, df, current_tick, macro_context):
        """Spawn a daemon thread to refresh the forecast without blocking the caller."""
        with self._refresh_lock:
            if self._refresh_in_progress:
                return  # already running - don't stack threads
            self._refresh_in_progress = True

        def _runner():
            try:
                self._do_refresh(symbol, df, current_tick, macro_context)
            except Exception as e:
                print(f"[FORECAST WARNING] Background refresh gagal: {e}")
            finally:
                with self._refresh_lock:
                    self._refresh_in_progress = False

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()

    def _do_refresh(self, symbol, df, current_tick, macro_context):
        """Actual refresh logic (synchronous). Updates cache + disk."""
        print(f" [FORECAST ENGINE] Memperbarui proyeksi harga Multi-Horizon untuk {symbol}...")
        now = time.time()
        new_forecast = self._generate_forecast_with_llm(symbol, df, current_tick, macro_context)
        if new_forecast:
            new_forecast["symbol"] = symbol
            new_forecast["timestamp"] = now
            self._forecast = new_forecast
            self._save_cache()
            h_lbl = new_forecast.get('horizon_label', 'T+30m/T+1h/T+4h' if config.is_crypto(symbol) else 'T+15m/T+30m')
            t_val = 'N/A'
            for k in ['target_t1h', 'target_t30m', 'target_t15m', 'target_t45m', 'target_t4h', 'target_t2h', 'target_t12h']:
                if k in new_forecast:
                    t_val = f"{new_forecast[k]} ({k})"
                    break
            print(f" [FORECAST ENGINE] Proyeksi Baru: Bias {new_forecast.get('forecast_bias')} | {h_lbl} Target: {t_val} | Invalidation: {new_forecast.get('invalidation_level')}")
        return self._forecast

    def _generate_forecast_with_llm(self, symbol, df, current_tick, macro_context):
        """Queries OpenAI, Gemini, and Claude in parallel to form a Multi-LLM Consensus Forecast."""
        latest = df.iloc[-1]

        # Resolve dynamic timeframe label
        tf_val = config.get_timeframe(symbol)
        tf_map_rev = {v: k for k, v in config.TIMEFRAME_MAP.items()}
        tf_label = tf_map_rev.get(tf_val, "M30" if "XAU" in symbol.upper() else "M5")

        if config.is_crypto(symbol) or "XAU" in symbol.upper():
            # M30 main (BTC & XAU) -> M30 horizons
            horizon_5m = "next 30 minutes (T+30m)"
            horizon_short = "next 1 hour (T+1h)"
            horizon_long = "next 4 hours (T+4h)"
            horizon_5m_key = "target_t30m"
            horizon_short_key = "target_t1h"
            horizon_long_key = "target_t4h"
            horizon_label = "T+30m/T+1h/T+4h"
        else:
            # FX main is H1 -> H1 horizons
            horizon_5m = "next 1 hour (T+1h)"
            horizon_short = "next 4 hours (T+4h)"
            horizon_long = "next 12 hours (T+12h)"
            horizon_5m_key = "target_t1h"
            horizon_short_key = "target_t4h"
            horizon_long_key = "target_t12h"
            horizon_label = "T+1h/T+4h/T+12h"

        # Schema JSON: hindari key duplikat (XAU punya 2 horizon saja)
        targets_schema = (
            f'    "{horizon_5m_key}": <numeric price target for {horizon_5m}>,\n'
            f'    "{horizon_short_key}": <numeric price target for {horizon_short}>,\n'
        )
        if horizon_long_key != horizon_short_key:
            targets_schema += f'    "{horizon_long_key}": <numeric price target for {horizon_long}>,\n'

        prompt = f"""
You are a quantitative financial forecasting engine specializing in multi-horizon price projections for {symbol}.

Current Market Data:
- Current Bid: {current_tick['bid']}, Ask: {current_tick['ask']}
- {tf_label} Close: {latest['close']}, RSI(14): {latest['rsi_14']:.2f}, EMA20: {latest['ema_20']:.2f}, EMA50: {latest['ema_50']:.2f}, ATR14: {latest['atr_14']:.2f}
- Macro/Timeframe Context: {macro_context or f'Standard {tf_label} trading'}

Task:
Analyze the price action structure, momentum, and timeframe indicators to project the market trajectory.

Generate a JSON object strictly matching this schema:
{{
    "forecast_bias": "BULLISH" | "BEARISH" | "NEUTRAL",
{targets_schema}    "invalidation_level": <numeric price boundary where forecast becomes completely invalid>,
    "optimal_entry_min": <numeric minimum price boundary for optimal entry zone>,
    "optimal_entry_max": <numeric maximum price boundary for optimal entry zone>,
    "forecast_reasoning": "<concise 1-sentence explanation of predicted price trajectory>"
}}
"""
        results = {}
        # Forecast: 1 AI saja (gpt-5.4 primary, gemini-3.5-flash fallback) -
        # bukan lagi 3-LLM consensus (echo chamber: model yang sama dengan decision).
        f_data = llm.query_forecast(prompt)
        if isinstance(f_data, dict) and "forecast_bias" in f_data:
            results["ForecastAI"] = f_data

        if not results:
            curr = current_tick['bid']
            atr = latest['atr_14']
            if config.is_crypto(symbol):
                return {
                    "forecast_bias": "NEUTRAL",
                    "target_t30m": round(curr + (0.5 * atr), 2),
                    "target_t1h": round(curr + atr, 2),
                    "target_t4h": round(curr + (2 * atr), 2),
                    "invalidation_level": round(curr - (1.5 * atr), 2),
                    "optimal_entry_min": round(curr - (0.5 * atr), 2),
                    "optimal_entry_max": round(curr + (0.5 * atr), 2),
                    "forecast_reasoning": "Fallback default projection (M30 horizon)"
                }
            return {
                "forecast_bias": "NEUTRAL",
                "target_t15m": round(curr + (0.5 * atr), 2),
                "target_t30m": round(curr + atr, 2),
                "invalidation_level": round(curr - (1.5 * atr), 2),
                "optimal_entry_min": round(curr - (0.5 * atr), 2),
                "optimal_entry_max": round(curr + (0.5 * atr), 2),
                "forecast_reasoning": "Fallback default projection"
            }

        # Determine consensus bias
        bias_counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
        for m, data in results.items():
            b = data.get("forecast_bias", "NEUTRAL").upper()
            bias_counts[b] = bias_counts.get(b, 0) + 1

        consensus_bias = "NEUTRAL"
        if bias_counts["BULLISH"] >= 2:
            consensus_bias = "BULLISH"
        elif bias_counts["BEARISH"] >= 2:
            consensus_bias = "BEARISH"
        else:
            consensus_bias = max(bias_counts, key=bias_counts.get)

        # Average numeric targets from models matching consensus_bias (or all if neutral)
        matching_models = [d for d in results.values() if d.get("forecast_bias", "NEUTRAL").upper() == consensus_bias]
        if not matching_models:
            matching_models = list(results.values())

        # Per-symbol target keys: XAU horizon = T+15m/T+30m, BTC = T+30m/T+1h/T+4h
        def _avg(key, alt_keys=()):
            vals = []
            for m in matching_models:
                v = m.get(key)
                if v is None:
                    for alt in alt_keys:
                        v = m.get(alt)
                        if v is not None:
                            break
                if v is not None:
                    vals.append(float(v))
            return sum(vals) / len(vals) if vals else 0.0

        avg_5m = _avg(horizon_5m_key, ("target_t5m", "target_t30m"))
        avg_short = _avg(horizon_short_key, ("target_t15m", "target_t1h"))
        avg_long = _avg(horizon_long_key, ("target_t60m", "target_t4h"))
        avg_inv = _avg("invalidation_level")
        avg_emin = _avg("optimal_entry_min")
        avg_emax = _avg("optimal_entry_max")

        models_summary = ", ".join([f"{m}: {d.get('forecast_bias')}" for m, d in results.items()])
        print(f" [FORECAST] Bias: {consensus_bias} ({models_summary})")

        out = {
            "forecast_bias": consensus_bias,
            "invalidation_level": round(avg_inv, 2),
            "optimal_entry_min": round(avg_emin, 2),
            "optimal_entry_max": round(avg_emax, 2),
            "forecast_reasoning": f"Multi-LLM Consensus ({models_summary})",
            "horizon_label": horizon_label,
        }
        out[horizon_5m_key] = round(avg_5m, 2)
        out[horizon_short_key] = round(avg_short, 2)
        if horizon_long_key != horizon_short_key:
            out[horizon_long_key] = round(avg_long, 2)
        # Legacy aliases (XAU: t5m/t60m tetap diisi tapi tidak dipakai lagi)
        out["target_t5m"] = round(avg_5m, 2)
        out["target_t15m"] = round(avg_short, 2)
        out["target_t60m"] = round(avg_long, 2)
        return out

    def get_forecast_context(self):
        """Returns formatted forecast matrix markdown block for prompt injection."""
        if not self._forecast or "forecast_bias" not in self._forecast:
            return ""

        f = self._forecast
        horizon = f.get("horizon_label", "T+15m/T+30m")
        label_key_map = {
            "T+15m": "target_t15m",
            "T+30m": "target_t30m",
            "T+45m": "target_t45m",
            "T+1h": "target_t1h",
            "T+2h": "target_t2h",
            "T+4h": "target_t4h",
            "T+12h": "target_t12h",
            "T+60m": "target_t60m",
        }
        target_lines = []
        for label in [lbl.strip() for lbl in horizon.split("/")]:
            key = label_key_map.get(label)
            if key and f.get(key) is not None:
                target_lines.append(f"- Target {label}: {f.get(key)}\n")
        if not target_lines:
            target_lines = [f"- Target T+15m: {f.get('target_t15m')}\n"]

        return (
            f"\n### MULTI-HORIZON PRICE FORECAST MATRIX\n"
            f"- Predicted Bias: {f.get('forecast_bias')}\n"
            + "".join(target_lines) +
            f"- Invalidation Boundary: {f.get('invalidation_level')}\n"
            f"- Optimal Entry Zone: {f.get('optimal_entry_min')} - {f.get('optimal_entry_max')}\n"
            f"- Rationale: {f.get('forecast_reasoning')}\n"
        )

# Singleton instance
forecaster = ForecastEngine()
