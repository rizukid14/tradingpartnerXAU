"""
Multi-Horizon Forecasting Engine & Conditional Execution Guard.

Generates multi-horizon price projections (T+15m, T+60m, invalidation boundary)
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
    XAU (M5 scalping): 15 minutes.
    BTC (H1 swing, H4/D1 context): 1 hour — the T+4h/T+D1 forecast does not
    change meaningfully every 15 minutes, so refresh once per H1 candle.
    """
    return 3600 if config.is_crypto(symbol) else CACHE_DURATION_SECONDS

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

    def _kick_background_refresh(self, symbol, df, current_tick, macro_context):
        """Spawn a daemon thread to refresh the forecast without blocking the caller."""
        with self._refresh_lock:
            if self._refresh_in_progress:
                return  # already running — don't stack threads
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
        now = time.time()
        print(f"🔮 [FORECAST ENGINE] Memperbarui proyeksi harga Multi-Horizon untuk {symbol}...")
        new_forecast = self._generate_forecast_with_llm(symbol, df, current_tick, macro_context)
        if new_forecast:
            new_forecast["symbol"] = symbol
            new_forecast["timestamp"] = now
            self._forecast = new_forecast
            self._save_cache()
            print(f"✅ [FORECAST ENGINE] Proyeksi Baru: Bias {new_forecast.get('forecast_bias')} | {new_forecast.get('horizon_label', 'T+15m/T+60m')} Target: {new_forecast.get('target_t15m')} | Invalidation: {new_forecast.get('invalidation_level')}")
        return self._forecast

    def _generate_forecast_with_llm(self, symbol, df, current_tick, macro_context):
        """Queries OpenAI, Gemini, and Claude in parallel to form a Multi-LLM Consensus Forecast."""
        latest = df.iloc[-1]

        # Per-symbol forecast horizon: XAU scalps on M5 (15m/60m ahead);
        # BTC swings on H1 (next 4 hours / next day — 15m targets are noise
        # relative to H1 swings and the ~$17 spread).
        if config.is_crypto(symbol):
            tf_label = "H1"
            horizon_short = "next 4 hours (T+4h)"
            horizon_long = "next 1 day (T+D1)"
            horizon_short_key = "target_t4h"
            horizon_long_key = "target_t1d"
        else:
            tf_label = "M5"
            horizon_short = "next 15 minutes (T+15m)"
            horizon_long = "next 60 minutes (T+60m)"
            horizon_short_key = "target_t15m"
            horizon_long_key = "target_t60m"

        prompt = f"""
You are a quantitative financial forecasting engine specializing in multi-horizon price projections for {symbol}.

Current Market Data:
- Current Bid: {current_tick['bid']}, Ask: {current_tick['ask']}
- {tf_label} Close: {latest['close']}, RSI(14): {latest['rsi_14']:.2f}, EMA20: {latest['ema_20']:.2f}, EMA50: {latest['ema_50']:.2f}, ATR14: {latest['atr_14']:.2f}
- Macro/Timeframe Context: {macro_context or f'Standard {tf_label} trading'}

Task:
Generate a multi-horizon price forecast projection for {horizon_short} and {horizon_long}.

Respond in STRICT JSON format ONLY with the following keys:
{{
    "forecast_bias": "BULLISH" | "BEARISH" | "NEUTRAL",
    "{horizon_short_key}": <numeric price target for {horizon_short}>,
    "{horizon_long_key}": <numeric price target for {horizon_long}>,
    "invalidation_level": <numeric price boundary where forecast becomes completely invalid>,
    "optimal_entry_min": <numeric minimum price boundary for optimal entry zone>,
    "optimal_entry_max": <numeric maximum price boundary for optimal entry zone>,
    "forecast_reasoning": "<concise 1-sentence explanation of predicted price trajectory>"
}}
"""
        results = {}
        import concurrent.futures
        
        def _get_single(fn):
            try:
                res = fn(prompt)
                if isinstance(res, str):
                    res = llm.clean_json_response(res)
                if isinstance(res, dict) and "forecast_bias" in res:
                    return res
            except Exception:
                pass
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                executor.submit(_get_single, llm.query_openai): "OpenAI",
                executor.submit(_get_single, llm.query_gemini): "Gemini",
                executor.submit(_get_single, llm.query_claude): "Claude"
            }
            for fut in concurrent.futures.as_completed(futures):
                m_name = futures[fut]
                f_data = fut.result()
                if f_data:
                    results[m_name] = f_data

        if not results:
            curr = current_tick['bid']
            atr = latest['atr_14']
            if config.is_crypto(symbol):
                # H1: scale fallback targets by ~4h / ~1d of H1 ATR
                return {
                    "forecast_bias": "NEUTRAL",
                    "target_t4h": round(curr + (2 * atr), 2),
                    "target_t1d": round(curr + (4 * atr), 2),
                    "invalidation_level": round(curr - (1.5 * atr), 2),
                    "optimal_entry_min": round(curr - (0.5 * atr), 2),
                    "optimal_entry_max": round(curr + (0.5 * atr), 2),
                    "forecast_reasoning": "Fallback default projection (H1 horizon)"
                }
            return {
                "forecast_bias": "NEUTRAL",
                "target_t15m": round(curr + atr, 2),
                "target_t60m": round(curr + (2 * atr), 2),
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

        # Per-symbol target keys (fallback: tolerate both old & new keys)
        short_key = horizon_short_key
        long_key = horizon_long_key
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

        avg_short = _avg(short_key, ("target_t15m", "target_t60m"))
        avg_long = _avg(long_key, ("target_t15m", "target_t60m"))
        avg_inv = _avg("invalidation_level")
        avg_emin = _avg("optimal_entry_min")
        avg_emax = _avg("optimal_entry_max")

        models_summary = ", ".join([f"{m}: {d.get('forecast_bias')}" for m, d in results.items()])
        print(f"🔮 [MULTI-LLM FORECAST CONSENSUS] Bias: {consensus_bias} ({models_summary})")

        out = {
            "forecast_bias": consensus_bias,
            "invalidation_level": round(avg_inv, 2),
            "optimal_entry_min": round(avg_emin, 2),
            "optimal_entry_max": round(avg_emax, 2),
            "forecast_reasoning": f"Multi-LLM Consensus ({models_summary})",
            "horizon_label": "T+4h/T+D1" if config.is_crypto(symbol) else "T+15m/T+60m",
        }
        out[short_key] = round(avg_short, 2)
        out[long_key] = round(avg_long, 2)
        # Keep legacy keys too so consumers reading target_t15m still work
        out["target_t15m"] = round(avg_short, 2)
        out["target_t60m"] = round(avg_long, 2)
        return out

    def validate_forecast_trigger(self, symbol, current_tick, consensus_result, df):
        """
        Validates 4 conditional trigger rules before trade execution:
        Rule 1: Consensus signal matches forecast_bias.
        Rule 2: Current price respects invalidation_level.
        Rule 3: Price is within acceptable entry range.
        Rule 4: Risk/Reward ratio to target_t15m relative to invalidation_level >= 1.2.
        """
        signal = consensus_result.get("signal", "HOLD")
        if signal not in ["BUY", "SELL"]:
            return False, "Sinyal HOLD tidak diproses", 0, 0

        # Ensure active forecast is loaded
        forecast = self.get_active_forecast(symbol, df, current_tick)
        bias = forecast.get("forecast_bias", "NEUTRAL")
        target_short = float(forecast.get("target_t15m", 0.0))  # legacy key holds short-horizon target
        invalidation = float(forecast.get("invalidation_level", 0.0))
        entry_min = float(forecast.get("optimal_entry_min", 0.0))
        entry_max = float(forecast.get("optimal_entry_max", 0.0))
        point_size = current_tick.get("point", 0.01)
        horizon_label = forecast.get("horizon_label", "T+15m")

        bid = current_tick["bid"]
        ask = current_tick["ask"]

        # Rule 1: Directional Alignment (Only block on DIRECT contradiction: BUY vs BEARISH or SELL vs BULLISH)
        if signal == "BUY" and bias == "BEARISH":
            return False, f"Arah sinyal BUY bertentangan langsung dengan bias prediksi ({bias})", 0, 0
        if signal == "SELL" and bias == "BULLISH":
            return False, f"Arah sinyal SELL bertentangan langsung dengan bias prediksi ({bias})", 0, 0


        # Rule 2: Invalidation Guard
        if signal == "BUY" and ask <= invalidation:
            return False, f"Harga saat ini ({ask}) telah menembus batas invalidasi prediksi BUY ({invalidation})", 0, 0
        if signal == "SELL" and bid >= invalidation:
            return False, f"Harga saat ini ({bid}) telah menembus batas invalidasi prediksi SELL ({invalidation})", 0, 0

        # Rule 3: Entry Range & Risk/Reward Calculation
        if signal == "BUY":
            sl_points = int(round((ask - invalidation) / point_size))
            tp_points = int(round((target_short - ask) / point_size))
        else:
            sl_points = int(round((invalidation - bid) / point_size))
            tp_points = int(round((bid - target_short) / point_size))

        if sl_points <= 0 or tp_points <= 0:
            return False, "Batas TP/SL dari proyeksi prediksi bernilai negatif atau 0", 0, 0

        rr_ratio = tp_points / float(sl_points) if sl_points > 0 else 1.0
        return True, f"Bias: {bias} | Proyeksi R:R ({horizon_label}): {rr_ratio:.2f} (Target: {target_short}, Invalidation: {invalidation})", sl_points, tp_points


    def get_forecast_context(self):
        """Returns formatted forecast matrix markdown block for prompt injection."""
        if not self._forecast or "forecast_bias" not in self._forecast:
            return ""

        f = self._forecast
        horizon = f.get("horizon_label", "T+15m/T+60m")
        short_label, long_label = horizon.split("/") if "/" in horizon else (horizon, horizon)
        short_target = f.get("target_t15m", f.get("target_t4h"))
        long_target = f.get("target_t60m", f.get("target_t1d"))
        return (
            f"\n### MULTI-HORIZON PRICE FORECAST MATRIX\n"
            f"- Predicted Bias: {f.get('forecast_bias')}\n"
            f"- Target {short_label}: {short_target}\n"
            f"- Target {long_label}: {long_target}\n"
            f"- Invalidation Boundary: {f.get('invalidation_level')}\n"
            f"- Optimal Entry Zone: {f.get('optimal_entry_min')} - {f.get('optimal_entry_max')}\n"
            f"- Rationale: {f.get('forecast_reasoning')}\n"
        )

# Singleton instance
forecaster = ForecastEngine()
