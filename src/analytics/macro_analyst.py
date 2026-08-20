import os
import time
import json
from datetime import datetime
import config
from config import mt5
from src.core import mt5_connector as connector, llm_client as llm
from src.core.risk_engine import WIB






CACHE_FILE = os.path.join(config.DATA_DIR, "analysis_cache.json")


def _fmt(x):
    """Format harga ke desimal bersih (1.09815, 151.234, 4318.15) - fix 14
    Agustus: `.2f` meratakan harga FX 5-desimal jadi 1.10 / 0.00."""
    return f"{x:.10f}".rstrip("0").rstrip(".")


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
                if "symbol" in self.cache:
                    # Migrate old flat cache format
                    self.cache = {}
            else:
                self.cache = {}
        except Exception as e:
            print(f"[MACRO WARNING] Gagal memuat analisa cache: {e}")
            self.cache = {}

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
        sym = config.SYMBOL

        if sym not in self.cache:
            self.cache[sym] = {
                "last_fundamental_session": "",
                "last_fundamental_time": 0.0,
                "fundamental_outlook": "",
                "timeframe_analysis": {}
            }
            print(f" [MACRO] Menginisialisasi cache analisa untuk simbol {sym}.")
            force = True

        sym_cache = self.cache[sym]

        # 1. Check Multi-Timeframe Analysis
        if getattr(config, "MTF_ANALYSIS_ENABLED", True):
            if "timeframe_analysis" not in sym_cache:
                sym_cache["timeframe_analysis"] = {}

            for tf_name, tf_const in config.get_higher_timeframes(sym).items():
                rates = mt5.copy_rates_from_pos(sym, tf_const, 0, 2)
                if rates is not None and len(rates) > 0:
                    current_candle_time = int(rates[-1]['time'])
                    cached_candle_time = sym_cache["timeframe_analysis"].get(tf_name, {}).get("last_candle_time", 0)

                    if force or current_candle_time > cached_candle_time:
                        print(f" [MTF] Menjalankan analisa struktur untuk timeframe {tf_name} ({sym})...")
                        analysis = self._run_timeframe_analysis(tf_name, tf_const)
                        if analysis:
                            sym_cache["timeframe_analysis"][tf_name] = {
                                "last_candle_time": current_candle_time,
                                "analysis": analysis,
                                "updated_at": time.time()
                            }
                            updated = True
                else:
                    print(f" [MTF WARNING] Gagal membaca data MT5 untuk timeframe {tf_name} ({sym}).")

        # 2. Check Fundamental Analysis
        if getattr(config, "FUNDAMENTAL_ANALYSIS_ENABLED", True):
            current_session = self.get_current_session()
            cached_session = sym_cache.get("last_fundamental_session", "")

            # Trigger if session changes and is valid, or if force run
            if force or (current_session != "None" and current_session != cached_session):
                print(f" [FUNDAMENTAL] Menjalankan analisa fundamental untuk sesi '{current_session}' ({sym})...")
                outlook = self._run_fundamental_analysis()
                if outlook:
                    sym_cache["last_fundamental_session"] = current_session
                    sym_cache["last_fundamental_time"] = time.time()
                    sym_cache["fundamental_outlook"] = outlook
                    updated = True

        if updated:
            self._save_cache()
            print(f" [MACRO] Analisa cache diperbarui dan disimpan ({sym}).")

    def _run_timeframe_analysis(self, tf_name, tf_const):
        """
        Computes higher-timeframe trend structure DIRECTLY from MT5 indicators -
        NO LLM call. EMA20/50, RSI, ATR dan swing high/low dihitung dari df M30
        (XAU) / H1-H4 (BTC). Output teks faktual, bukan opini LLM.
        """
        if tf_name == "M15":
            window_size = 48
        elif tf_name == "M30":
            window_size = 72
        elif tf_name == "H1":
            window_size = 72
        elif tf_name == "H4":
            window_size = 30
        elif tf_name == "D1":
            window_size = 30
        else:
            window_size = 30

        # EMA200 H4/D1 butuh >= 200 bar utk valid (institutional regime filter,
        # 20 Agustus, paket anti-FOMC). H4/D1 fetch 260 bar (sekali per
        # pergantian candle HTF, cache per-symbol sudah ada - murah).
        fetch_candles = 260 if tf_name in ("H4", "D1") else max(50, window_size + 20)
        df = connector.get_market_data(config.SYMBOL, tf_const, num_candles=fetch_candles)
        if df is None or len(df) < 30:
            print(f" [MTF ERROR] Gagal mendapatkan data untuk timeframe {tf_name}.")
            return None

        latest = df.iloc[-1]
        close = float(latest["close"])
        ema20 = float(latest["ema_20"])
        ema50 = float(latest["ema_50"])
        rsi = float(latest["rsi_14"])
        atr = float(latest["atr_14"])

        # EMA50 slope (20 Agustus, paket anti-FOMC): tren ekspansi yang SEDANG
        # terjadi ditandai slope EMA50 searah. Slope dihitung dari pergeseran
        # EMA50 bar terakhir vs bar sebelumnya (naik/turun).
        ema50_prev = float(df["ema_50"].iloc[-2]) if len(df) >= 2 else ema50
        ema50_slope = "rising" if ema50 > ema50_prev else ("falling" if ema50 < ema50_prev else "flat")

        # Trend direction dari hubungan harga vs EMA20 vs EMA50
        if close > ema20 > ema50:
            trend = "UPTREND"
        elif close < ema20 < ema50:
            trend = "DOWNTREND"
        elif close > ema20:
            trend = "BULLISH BIAS (price above EMA20, EMA50 still flat)"
        elif close < ema20:
            trend = "BEARISH BIAS (price below EMA20, EMA50 still flat)"
        else:
            trend = "RANGING"

        # Swing high/low dari window_size candle terakhir (level support/resistance)
        window = df.tail(window_size)
        swing_high = float(window["high"].max())
        swing_low = float(window["low"].min())
        swing_high_dist = (swing_high - close) / (atr if atr > 0 else 1.0)
        swing_low_dist = (close - swing_low) / (atr if atr > 0 else 1.0)

        # RSI label
        if rsi >= 70:
            rsi_label = "overbought (potential pullback)"
        elif rsi <= 30:
            rsi_label = "oversold (potential rebound)"
        else:
            rsi_label = "neutral"

        # EMA200 regime (institutional benchmark). Hanya valid kalau data >= 200 bar
        # (fetch 260 di atas). NaN kalau data pendek -> skip baris EMA200.
        ema200_str = ""
        if "ema_200" in df.columns and len(df) >= 200:
            ema200 = float(df["ema_200"].iloc[-1])
            if ema200 == ema200:  # NaN guard
                above = close >= ema200
                dist200 = (close - ema200) / (atr if atr > 0 else 1.0)
                regime = "BULLISH regime (institutions long)" if above else "BEARISH regime (institutions short)"
                ema200_str = (
                    f" | EMA200 {_fmt(ema200)} (close {'ABOVE' if above else 'BELOW'}, "
                    f"{abs(dist200):.1f}x ATR -> {regime})"
                )

        # Jarak harga ke swing (dalam satuan ATR) biar LLM tahu seberapa dekat level
        support_line = f"nearest support {_fmt(swing_low)} (~{swing_low_dist:.1f}x ATR below)" if swing_low_dist <= 2.0 else f"support far {_fmt(swing_low)} (~{swing_low_dist:.1f}x ATR)"
        resistance_line = f"nearest resistance {_fmt(swing_high)} (~{swing_high_dist:.1f}x ATR above)" if swing_high_dist <= 2.0 else f"resistance far {_fmt(swing_high)} (~{swing_high_dist:.1f}x ATR)"

        return (
            f"trend {trend} | close {_fmt(close)}, EMA20 {_fmt(ema20)}, EMA50 {_fmt(ema50)} "
            f"(gap EMA {_fmt(abs(ema20 - ema50))}, slope EMA50 {ema50_slope}), RSI {rsi:.1f} ({rsi_label}), ATR {_fmt(atr)}{ema200_str} | "
            f"swing {window_size}-candle: high {_fmt(swing_high)} ({resistance_line}), low {_fmt(swing_low)} ({support_line})"
        )

    def _run_fundamental_analysis(self):
        """Queries Gemini with Search Grounding to generate fundamental outlook."""
        return llm.analyze_fundamentals(config.SYMBOL)

    def get_macro_context(self):
        """Formats the cached macro & MTF analyses into a unified context block."""
        context = []
        sym = config.SYMBOL
        sym_cache = self.cache.get(sym, {})

        # 1. Add Multi-Timeframe Analysis
        if getattr(config, "MTF_ANALYSIS_ENABLED", True):
            tf_analyses = []
            tf_cache = sym_cache.get("timeframe_analysis", {})
            for tf_name in config.get_higher_timeframes(sym).keys():
                tf_data = tf_cache.get(tf_name)
                if tf_data and tf_data.get("analysis"):
                    tf_analyses.append(f"- **{tf_name} Timeframe**: {tf_data['analysis']}")
            if tf_analyses:
                context.append("### MULTI-TIMEFRAME ANALYSIS (Trend Structure)\n" + "\n".join(tf_analyses))

        # 2. Add Fundamental Analysis (only if enabled AND there's cached content)
        if getattr(config, "FUNDAMENTAL_ANALYSIS_ENABLED", True):
            outlook = sym_cache.get("fundamental_outlook")
            if outlook:
                # Tambah session label ke context text
                sess = sym_cache.get("last_fundamental_session", "Unknown")
                context.append(f"### FUNDAMENTAL ANALYSIS & SENTIMENT ({sess} Session)\n{outlook}")

        if not context:
            return ""

        return "\n\n".join(context)
