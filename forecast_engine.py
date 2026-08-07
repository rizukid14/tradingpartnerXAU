"""
Multi-Horizon Forecasting Engine & Conditional Execution Guard.

Generates multi-horizon price projections (T+15m, T+60m, invalidation boundary)
using the primary LLM (Gemini) and enforces strict conditional trigger rules
("Jika X dan Y sesuai prediksi maka execute") before order submission.
"""
import os
import json
import time
import config
import llm_client as llm

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forecast_cache.json")
CACHE_DURATION_SECONDS = 900  # 15 minutes forecast validity

class ForecastEngine:
    def __init__(self):
        self._forecast = {}
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
        Retrieves active forecast matrix. Generates new projection via Gemini
        if cache is expired (>15 mins) or invalidation level was breached.
        """
        now = time.time()
        last_time = float(self._forecast.get("timestamp", 0))
        
        # Check if cache is still valid or if price breached invalidation level
        if not force_refresh and (now - last_time < CACHE_DURATION_SECONDS) and self._forecast.get("symbol") == symbol:
            inv = float(self._forecast.get("invalidation_level", 0.0))
            bias = self._forecast.get("forecast_bias", "NEUTRAL").upper()
            curr_bid = current_tick.get("bid", 0.0)
            curr_ask = current_tick.get("ask", 0.0)

            if inv > 0:
                if (bias == "BULLISH" and curr_ask <= inv) or (bias == "BEARISH" and curr_bid >= inv):
                    print(f"🔄 [FORECAST AUTO-REFRESH] Harga ({curr_bid}) telah menembus batas invalidasi lama ({inv}). Membuat proyeksi baru real-time...")
                    force_refresh = True
                else:
                    return self._forecast
            else:
                return self._forecast


        print(f"🔮 [FORECAST ENGINE] Memperbarui proyeksi harga Multi-Horizon untuk {symbol}...")
        new_forecast = self._generate_forecast_with_llm(symbol, df, current_tick, macro_context)
        if new_forecast:
            new_forecast["symbol"] = symbol
            new_forecast["timestamp"] = now
            self._forecast = new_forecast
            self._save_cache()
            print(f"✅ [FORECAST ENGINE] Proyeksi Baru: Bias {new_forecast.get('forecast_bias')} | Target T+15m: {new_forecast.get('target_t15m')} | Invalidation: {new_forecast.get('invalidation_level')}")
        
        return self._forecast

    def _generate_forecast_with_llm(self, symbol, df, current_tick, macro_context):
        """Queries OpenAI, Gemini, and DeepSeek in parallel to form a Multi-LLM Consensus Forecast."""
        latest = df.iloc[-1]
        
        prompt = f"""
You are a quantitative financial forecasting engine specializing in multi-horizon price projections for {symbol}.

Current Market Data:
- Current Bid: {current_tick['bid']}, Ask: {current_tick['ask']}
- M5 Close: {latest['close']}, RSI(14): {latest['rsi_14']:.2f}, EMA20: {latest['ema_20']:.2f}, EMA50: {latest['ema_50']:.2f}, ATR14: {latest['atr_14']:.2f}
- Macro/Timeframe Context: {macro_context or 'Standard M5 Scalping'}

Task:
Generate a multi-horizon price forecast projection for the next 15 minutes (T+15m) and 60 minutes (T+60m).

Respond in STRICT JSON format ONLY with the following keys:
{{
    "forecast_bias": "BULLISH" | "BEARISH" | "NEUTRAL",
    "target_t15m": <numeric price target for next 15 minutes>,
    "target_t60m": <numeric price target for next 60 minutes>,
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
                executor.submit(_get_single, llm.query_deepseek): "DeepSeek"
            }
            for fut in concurrent.futures.as_completed(futures):
                m_name = futures[fut]
                f_data = fut.result()
                if f_data:
                    results[m_name] = f_data

        if not results:
            curr = current_tick['bid']
            atr = latest['atr_14']
            return {
                "forecast_bias": "NEUTRAL",
                "target_t15m": round(curr + atr, 2),
                "target_t60m": round(curr + (2 * atr), 2),
                "invalidation_level": round(curr - (1.5 * atr), 2),
                "optimal_entry_min": round(curr - (0.5 * atr), 2),
                "optimal_entry_max": round(curr + (0.5 * atr), 2),
                "forecast_reasoning": "Fallback default projection"
            }

        # Calculate consensus bias and average numeric targets
        bias_counts = {"BULLISH": 0, "BEARISH": 0, "NEUTRAL": 0}
        for m, data in results.items():
            b = data.get("forecast_bias", "NEUTRAL").upper()
            bias_counts[b] = bias_counts.get(b, 0) + 1

        # Determine consensus bias
        consensus_bias = "NEUTRAL"
        if bias_counts["BULLISH"] >= 2:
            consensus_bias = "BULLISH"
        elif bias_counts["BEARISH"] >= 2:
            consensus_bias = "BEARISH"
        else:
            # Pick bias of model with most specific forecast or majority
            consensus_bias = max(bias_counts, key=bias_counts.get)

        # Average numeric targets from models matching consensus_bias (or all if neutral)
        matching_models = [d for d in results.values() if d.get("forecast_bias", "NEUTRAL").upper() == consensus_bias]
        if not matching_models:
            matching_models = list(results.values())

        avg_t15 = sum(float(m.get("target_t15m", 0)) for m in matching_models) / len(matching_models)
        avg_t60 = sum(float(m.get("target_t60m", 0)) for m in matching_models) / len(matching_models)
        avg_inv = sum(float(m.get("invalidation_level", 0)) for m in matching_models) / len(matching_models)
        avg_emin = sum(float(m.get("optimal_entry_min", 0)) for m in matching_models) / len(matching_models)
        avg_emax = sum(float(m.get("optimal_entry_max", 0)) for m in matching_models) / len(matching_models)

        models_summary = ", ".join([f"{m}: {d.get('forecast_bias')}" for m, d in results.items()])
        print(f"🔮 [MULTI-LLM FORECAST CONSENSUS] Bias: {consensus_bias} ({models_summary})")

        return {
            "forecast_bias": consensus_bias,
            "target_t15m": round(avg_t15, 2),
            "target_t60m": round(avg_t60, 2),
            "invalidation_level": round(avg_inv, 2),
            "optimal_entry_min": round(avg_emin, 2),
            "optimal_entry_max": round(avg_emax, 2),
            "forecast_reasoning": f"Multi-LLM Consensus ({models_summary})"
        }

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
        target_t15m = float(forecast.get("target_t15m", 0.0))
        invalidation = float(forecast.get("invalidation_level", 0.0))
        entry_min = float(forecast.get("optimal_entry_min", 0.0))
        entry_max = float(forecast.get("optimal_entry_max", 0.0))
        point_size = current_tick.get("point", 0.01)

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
            tp_points = int(round((target_t15m - ask) / point_size))
        else:
            sl_points = int(round((invalidation - bid) / point_size))
            tp_points = int(round((bid - target_t15m) / point_size))

        if sl_points <= 0 or tp_points <= 0:
            return False, "Batas TP/SL dari proyeksi prediksi bernilai negatif atau 0", 0, 0

        rr_ratio = tp_points / float(sl_points) if sl_points > 0 else 1.0
        return True, f"Bias: {bias} | Proyeksi R:R (T+15m): {rr_ratio:.2f} (Target T+15m: {target_t15m}, Invalidation: {invalidation})", sl_points, tp_points


    def get_forecast_context(self):
        """Returns formatted forecast matrix markdown block for prompt injection."""
        if not self._forecast or "forecast_bias" not in self._forecast:
            return ""
        
        f = self._forecast
        return (
            f"\n### MULTI-HORIZON PRICE FORECAST MATRIX\n"
            f"- Predicted Bias: {f.get('forecast_bias')}\n"
            f"- Target T+15m (3 candles): {f.get('target_t15m')}\n"
            f"- Target T+60m (1 hour): {f.get('target_t60m')}\n"
            f"- Invalidation Boundary: {f.get('invalidation_level')}\n"
            f"- Optimal Entry Zone: {f.get('optimal_entry_min')} - {f.get('optimal_entry_max')}\n"
            f"- Rationale: {f.get('forecast_reasoning')}\n"
        )

# Singleton instance
forecaster = ForecastEngine()
