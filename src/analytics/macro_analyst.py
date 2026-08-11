import os
import time
import json
from datetime import datetime
import config
from config import mt5
from src.core import mt5_connector as connector, llm_client as llm
from src.core.risk_engine import WIB






CACHE_FILE = os.path.join(config.DATA_DIR, "analysis_cache.json")


class MacroAnalyst:
    """
    Manages background multi-timeframe (MTF) analysis and fundamental macro analysis.
    Runs on timeframe candle openings and session changes, caching results to disk.
    """
    def __init__(self):
        self.cache = {}
        self._load_cache()

    def _load_cache(self):
        """Loads the cached analysis from a local JSON file."""
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            else:
                self.cache = {
                    "symbol": config.SYMBOL,
                    "last_fundamental_session": "",
                    "last_fundamental_time": 0.0,
                    "fundamental_outlook": "",
                    "timeframe_analysis": {}
                }
        except Exception as e:
            print(f"[MACRO WARNING] Gagal memuat analisa cache: {e}")
            self.cache = {
                "symbol": config.SYMBOL,
                "last_fundamental_session": "",
                "last_fundamental_time": 0.0,
                "fundamental_outlook": "",
                "timeframe_analysis": {}
            }

    def _save_cache(self):
        """Saves the current cache state to a local JSON file."""
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[MACRO WARNING] Gagal menyimpan analisa cache: {e}")

    def get_current_session(self):
        """
        Determines the current active session name matching WIB configuration.
        When sessions overlap (e.g. London 15:00-23:59 vs London-NY 20:00-23:59),
        returns the most SPECIFIC / most recent one (shortest window, latest start)
        so the fundamental analysis label follows the actual active phase.
        Returns 'None' if no session is active.
        """
        if not config.SESSION_FILTER_ENABLED:
            return "Global"

        now_wib = datetime.now(WIB)
        current_minutes = now_wib.hour * 60 + now_wib.minute

        matches = []
        for session in config.ALLOWED_SESSIONS_WIB:
            start = session["start"][0] * 60 + session["start"][1]
            end = session["end"][0] * 60 + session["end"][1]

            # Handle overnight sessions (e.g., NY 20:00 - 05:00)
            if start > end:
                in_session = current_minutes >= start or current_minutes < end
            else:
                in_session = start <= current_minutes < end

            if in_session:
                # Duration (handle overnight): minutes from start to end
                duration = (end - start) % (24 * 60)
                matches.append((session["name"], start, duration))

        if not matches:
            return "None"

        # Pick most specific: shortest duration, then latest start
        matches.sort(key=lambda m: (m[2], -m[1]))
        return matches[0][0]

    def check_and_update_analysis(self, force=False):
        """
        Checks if higher timeframe candles or trading session have updated.
        If they have, triggers LLM analysis and updates cache.
        If force=True, runs analysis immediately regardless of last candle/session times.
        """
        updated = False

        # Cache is per-symbol: if the active symbol changed (XAUUSD -> BTCUSD),
        # reset the cached analyses so stale gold data is never injected into BTC prompts.
        cached_symbol = self.cache.get("symbol", "")
        if cached_symbol != config.SYMBOL:
            self.cache = {
                "symbol": config.SYMBOL,
                "last_fundamental_session": "",
                "last_fundamental_time": 0.0,
                "fundamental_outlook": "",
                "timeframe_analysis": {}
            }
            print(f"🔄 [MACRO] Simbol berubah ({cached_symbol or 'none'} -> {config.SYMBOL}). Cache analisa direset.")
            force = True

        # 1. Check Multi-Timeframe Analysis
        if getattr(config, "MTF_ANALYSIS_ENABLED", True):
            if "timeframe_analysis" not in self.cache:
                self.cache["timeframe_analysis"] = {}

            for tf_name, tf_const in config.get_higher_timeframes(config.SYMBOL).items():
                rates = mt5.copy_rates_from_pos(config.SYMBOL, tf_const, 0, 2)
                if rates is not None and len(rates) > 0:
                    current_candle_time = int(rates[-1]['time'])
                    cached_candle_time = self.cache["timeframe_analysis"].get(tf_name, {}).get("last_candle_time", 0)

                    if force or current_candle_time > cached_candle_time:
                        print(f"🔄 [MTF] Menjalankan analisa struktur untuk timeframe {tf_name}...")
                        analysis = self._run_timeframe_analysis(tf_name, tf_const)
                        if analysis:
                            self.cache["timeframe_analysis"][tf_name] = {
                                "last_candle_time": current_candle_time,
                                "analysis": analysis,
                                "updated_at": time.time()
                            }
                            updated = True
                else:
                    print(f"⚠️ [MTF WARNING] Gagal membaca data MT5 untuk timeframe {tf_name}.")

        # 2. Check Fundamental Analysis
        if getattr(config, "FUNDAMENTAL_ANALYSIS_ENABLED", True):
            current_session = self.get_current_session()
            cached_session = self.cache.get("last_fundamental_session", "")

            # Trigger if session changes and is valid, or if force run
            if force or (current_session != "None" and current_session != cached_session):
                print(f"🔄 [FUNDAMENTAL] Menjalankan analisa fundamental untuk sesi '{current_session}'...")
                outlook = self._run_fundamental_analysis()
                if outlook:
                    self.cache["last_fundamental_session"] = current_session
                    self.cache["last_fundamental_time"] = time.time()
                    self.cache["fundamental_outlook"] = outlook
                    updated = True

        if updated:
            self._save_cache()
            print("💾 [MACRO] Analisa cache diperbarui dan disimpan.")

    def _run_timeframe_analysis(self, tf_name, tf_const):
        """
        Computes higher-timeframe trend structure DIRECTLY from MT5 indicators —
        NO LLM call. EMA20/50, RSI, ATR dan swing high/low dihitung dari df M30
        (XAU) / H1-H4 (BTC). Output teks faktual, bukan opini LLM.
        """
        df = connector.get_market_data(config.SYMBOL, tf_const, num_candles=50)
        if df is None or len(df) < 30:
            print(f"❌ [MTF ERROR] Gagal mendapatkan data untuk timeframe {tf_name}.")
            return None

        latest = df.iloc[-1]
        close = float(latest["close"])
        ema20 = float(latest["ema_20"])
        ema50 = float(latest["ema_50"])
        rsi = float(latest["rsi_14"])
        atr = float(latest["atr_14"])

        # Trend direction dari hubungan harga vs EMA20 vs EMA50
        if close > ema20 > ema50:
            trend = "UPTREND"
        elif close < ema20 < ema50:
            trend = "DOWNTREND"
        elif close > ema20:
            trend = "BULLISH BIAS (harga di atas EMA20, EMA50 masih mendatar)"
        elif close < ema20:
            trend = "BEARISH BIAS (harga di bawah EMA20, EMA50 masih mendatar)"
        else:
            trend = "RANGING"

        # Swing high/low dari 30 candle terakhir (level support/resistance)
        window = df.tail(30)
        swing_high = float(window["high"].max())
        swing_low = float(window["low"].min())
        swing_high_dist = (swing_high - close) / (atr if atr > 0 else 1.0)
        swing_low_dist = (close - swing_low) / (atr if atr > 0 else 1.0)

        # RSI label
        if rsi >= 70:
            rsi_label = "overbought (potensi pullback)"
        elif rsi <= 30:
            rsi_label = "oversold (potensi rebound)"
        else:
            rsi_label = "netral"

        # Jarak harga ke swing (dalam satuan ATR) biar LLM tahu seberapa dekat level
        support_line = f"support terdekat {swing_low:.2f} (~{swing_low_dist:.1f}x ATR di bawah)" if swing_low_dist <= 2.0 else f"support jauh {swing_low:.2f} (~{swing_low_dist:.1f}x ATR)"
        resistance_line = f"resistance terdekat {swing_high:.2f} (~{swing_high_dist:.1f}x ATR di atas)" if swing_high_dist <= 2.0 else f"resistance jauh {swing_high:.2f} (~{swing_high_dist:.1f}x ATR)"

        return (
            f"trend {trend} | close {close:.2f}, EMA20 {ema20:.2f}, EMA50 {ema50:.2f} "
            f"(gap EMA {abs(ema20 - ema50):.2f}), RSI {rsi:.1f} ({rsi_label}), ATR {atr:.2f} | "
            f"swing 30-candle: high {swing_high:.2f} ({resistance_line}), low {swing_low:.2f} ({support_line})"
        )

    def _run_fundamental_analysis(self):
        """Queries Gemini with Search Grounding to generate fundamental outlook."""
        return llm.analyze_fundamentals(config.SYMBOL)

    def get_macro_context(self):
        """Formats the cached macro & MTF analyses into a unified context block."""
        context = []

        # 1. Add Multi-Timeframe Analysis
        if getattr(config, "MTF_ANALYSIS_ENABLED", True):
            tf_analyses = []
            tf_cache = self.cache.get("timeframe_analysis", {})
            for tf_name in config.get_higher_timeframes(config.SYMBOL).keys():
                tf_data = tf_cache.get(tf_name)
                if tf_data and tf_data.get("analysis"):
                    tf_analyses.append(f"- **{tf_name} Timeframe**: {tf_data['analysis']}")
            if tf_analyses:
                context.append("### MULTI-TIMEFRAME ANALYSIS (Struktur Trend)\n" + "\n".join(tf_analyses))

        # 2. Add Fundamental Analysis (only if enabled AND there's cached content)
        if getattr(config, "FUNDAMENTAL_ANALYSIS_ENABLED", True):
            fund_outlook = self.cache.get("fundamental_outlook", "")
            if fund_outlook and fund_outlook.strip():
                session = self.cache.get("last_fundamental_session", "")
                header = "### FUNDAMENTAL ANALYSIS (Macro Sentiment)"
                if session:
                    header += f" - diambil saat sesi {session}"
                context.append(header + "\n" + fund_outlook)

        if not context:
            return ""

        return "\n\n".join(context)
