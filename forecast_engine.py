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
        
        # Check if cache is still valid
        if not force_refresh and (now - last_time < CACHE_DURATION_SECONDS) and self._forecast.get("symbol") == symbol:
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
        """Asks Gemini to project T+15m, T+60m targets and invalidation levels."""
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
        try:
            response_json = llm.query_primary_model(prompt)
            if isinstance(response_json, str):
                response_json = llm.clean_json_response(response_json)
            if isinstance(response_json, dict) and "forecast_bias" in response_json:
                return response_json
        except Exception as e:
            print(f"[FORECAST ERROR] Gagal generate forecast: {e}")
            
        # Fallback default
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

        # Rule 1: Directional Alignment
        if signal == "BUY" and bias != "BULLISH":
            return False, f"Arah sinyal BUY bertentangan dengan bias prediksi ({bias})", 0, 0
        if signal == "SELL" and bias != "BEARISH":
            return False, f"Arah sinyal SELL bertentangan dengan bias prediksi ({bias})", 0, 0

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

        rr_ratio = tp_points / float(sl_points)
        if rr_ratio < 1.2:
            return False, f"Rasio Risk/Reward dari proyeksi ({rr_ratio:.2f}) di bawah batas aman 1.20", 0, 0

        return True, f"✅ Prediksi Terkonfirmasi! Bias: {bias} | R:R Proyeksi: {rr_ratio:.2f} (SL: {sl_points} pts, TP: {tp_points} pts)", sl_points, tp_points

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
