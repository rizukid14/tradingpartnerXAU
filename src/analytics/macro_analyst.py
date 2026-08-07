import os
import time
import json
from datetime import datetime
import MetaTrader5 as mt5
import config
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
                    "last_fundamental_session": "",
                    "last_fundamental_time": 0.0,
                    "fundamental_outlook": "",
                    "timeframe_analysis": {}
                }
        except Exception as e:
            print(f"[MACRO WARNING] Gagal memuat analisa cache: {e}")
            self.cache = {
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
        Returns 'None' if no session is active.
        """
        if not config.SESSION_FILTER_ENABLED:
            return "Global"

        now_wib = datetime.now(WIB)
        current_minutes = now_wib.hour * 60 + now_wib.minute

        for session in config.ALLOWED_SESSIONS_WIB:
            start = session["start"][0] * 60 + session["start"][1]
            end = session["end"][0] * 60 + session["end"][1]

            # Handle overnight sessions (e.g., NY 20:00 - 05:00)
            if start > end:
                in_session = current_minutes >= start or current_minutes < end
            else:
                in_session = start <= current_minutes < end

            if in_session:
                return session["name"]
        return "None"

    def check_and_update_analysis(self, force=False):
        """
        Checks if higher timeframe candles or trading session have updated.
        If they have, triggers LLM analysis and updates cache.
        If force=True, runs analysis immediately regardless of last candle/session times.
        """
        updated = False

        # 1. Check Multi-Timeframe Analysis
        if getattr(config, "MTF_ANALYSIS_ENABLED", True):
            if "timeframe_analysis" not in self.cache:
                self.cache["timeframe_analysis"] = {}

            for tf_name, tf_const in config.HIGHER_TIMEFRAMES.items():
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
        """Fetches higher timeframe historical rates and queries LLM for structural bias."""
        # Fetch 30 candles of higher timeframe to get trend structure
        df = connector.get_market_data(config.SYMBOL, tf_const, num_candles=30)
        if df is None or len(df) == 0:
            print(f"❌ [MTF ERROR] Gagal mendapatkan data untuk timeframe {tf_name}.")
            return None
        return llm.analyze_timeframe(config.SYMBOL, tf_name, df)

    def _run_fundamental_analysis(self):
        """Queries Gemini with Search Grounding to generate fundamental outlook."""
        return llm.analyze_fundamentals(config.SYMBOL)

    def get_macro_context(self):
        """Formats the cached macro & MTF analyses into a unified context block."""
        context = []

        # 1. Add Fundamental Outlook
        if getattr(config, "FUNDAMENTAL_ANALYSIS_ENABLED", True):
            outlook = self.cache.get("fundamental_outlook")
            session = self.cache.get("last_fundamental_session", "None")
            if outlook:
                context.append(f"### FUNDAMENTAL OUTLOOK (Sesi: {session})\n{outlook}")

        # 2. Add Multi-Timeframe Analysis
        if getattr(config, "MTF_ANALYSIS_ENABLED", True):
            tf_analyses = []
            tf_cache = self.cache.get("timeframe_analysis", {})
            for tf_name in config.HIGHER_TIMEFRAMES.keys():
                tf_data = tf_cache.get(tf_name)
                if tf_data and tf_data.get("analysis"):
                    tf_analyses.append(f"- **{tf_name} Timeframe**: {tf_data['analysis']}")
            if tf_analyses:
                context.append("### MULTI-TIMEFRAME ANALYSIS (Struktur Trend)\n" + "\n".join(tf_analyses))

        if not context:
            return ""

        return "\n\n".join(context)
