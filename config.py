import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo
try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:
    def load_dotenv(dotenv_path=None, override=False):
        if dotenv_path and os.path.exists(dotenv_path):
            with open(dotenv_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if override or k not in os.environ:
                            os.environ[k] = v

# --- PATH & DIRECTORY SETUP ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Add modular package search paths
for path in [BASE_DIR, os.path.join(BASE_DIR, "src"), os.path.join(BASE_DIR, "src", "core"), os.path.join(BASE_DIR, "src", "analytics")]:
    if path not in sys.path:
        sys.path.insert(0, path)

# Load environmental variables from .env file
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

# --- ENV PARSING HELPERS ---
def _getenv_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")

def _getenv_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default

def _getenv_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default

# --- MT5 HOST & PORT CONFIG ---
MT5_HOST = os.getenv("MT5_HOST", "localhost")
MT5_PORT = _getenv_int("MT5_PORT", 18812)

class DummyMT5:
    """Fallback MT5 object when MT5 is not available or disconnected."""
    TIMEFRAME_M1 = 1
    TIMEFRAME_M5 = 5
    TIMEFRAME_M15 = 15
    TIMEFRAME_M30 = 30
    TIMEFRAME_H1 = 16385
    TIMEFRAME_H4 = 16388
    TIMEFRAME_D1 = 16408

    def initialize(self, *args, **kwargs):
        return False

    def shutdown(self):
        pass

    def symbol_info_tick(self, *args, **kwargs):
        return None

    def symbol_info(self, *args, **kwargs):
        return None

    def copy_rates_from_pos(self, *args, **kwargs):
        return None

    def last_error(self):
        return (-1, "MT5 not connected")

if sys.platform == 'win32':
    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError:
        mt5 = DummyMT5()
else:
    mt5_obj = None
    try:
        import importlib
        rpyc = importlib.import_module("rpyc")
        conn = rpyc.classic.connect(MT5_HOST, MT5_PORT)
        mt5_obj = conn.modules.MetaTrader5
    except Exception as e1:
        try:
            import importlib
            mt5linux = importlib.import_module("mt5linux")
            mt5_obj = mt5linux.MetaTrader5(host=MT5_HOST, port=MT5_PORT)
        except Exception as e2:
            print(f"[CONFIG WARNING] Could not initialize remote MT5 connection ({e1}; {e2})")
    
    mt5 = mt5_obj if mt5_obj is not None else DummyMT5()


# --- API KEYS ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# --- TELEGRAM & BOT API CONFIG ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_TOKEN = TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_ENABLED = _getenv_bool("TELEGRAM_ENABLED", True)
TELEGRAM_USE_PROXY = _getenv_bool("TELEGRAM_USE_PROXY", False)
TELEGRAM_PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "https://tg-proxy-vercel-eight.vercel.app")
if TELEGRAM_USE_PROXY:
    TELEGRAM_API_BASE = os.getenv("TELEGRAM_PROXY_URL", "https://tg-proxy-vercel-eight.vercel.app")
else:
    TELEGRAM_API_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8765")
API_TOKEN = os.getenv("API_TOKEN", "")

# --- API BASE URLS ---
OPENAI_API_BASE = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")


# --- MODEL NAMES & FALLBACKS ---
# NOTE (18 Agu): claude-3-5-haiku-20241022 sudah dihapus dari API Anthropic (404).
# Default = haiku-4-5 (valid). Kalau mau DeepSeek di slot ini, set "deepseek/deepseek-v4-flash".
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
CLAUDE_FALLBACK_MODEL = os.getenv("CLAUDE_FALLBACK_MODEL", "deepseek/deepseek-v4-flash")

DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_FALLBACK_MODEL = os.getenv("DEEPSEEK_FALLBACK_MODEL", "gemini-2.5-flash-lite")

# DeepSeek reasoning effort: "high" | "medium" | "low" | "none" (default "none" for ultra-fast response)
DEEPSEEK_REASONING_EFFORT = os.getenv("DEEPSEEK_REASONING_EFFORT", "none")

# OpenAI reasoning effort: "high" | "medium" | "low" | "none" (default "low" for CoT reasoning)
OPENAI_REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "low")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
GEMINI_THINKING_BUDGET = _getenv_int("GEMINI_THINKING_BUDGET", 1024)  # 1024 token thinking budget (respons ~2.3s)

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "o4-mini")
OPENAI_DEFAULT_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", "o4-mini")
OPENAI_FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "o3-mini")  # fallback error (lambat/timeout)


def _parse_windows_wib(raw):
    """Parse "15:00-19:30" / "15:00-19:30,21:00-23:00" -> list[(start_min, end_min)]."""
    out = []
    for part in (raw or "").split(","):
        part = part.strip()
        if ":" in part and "-" in part:
            try:
                s, e = part.split("-")
                sh, sm = s.split(":")
                eh, em = e.split(":")
                out.append((int(sh) * 60 + int(sm), int(eh) * 60 + int(em)))
            except Exception:
                pass
    return out


# gpt-5.2 (free tier model besar 250k token/hari, SHARED semua model besar)
# dipakai HANYA di window ini (WIB) biar kuota tidak cepet habis; di luar window
# OpenAI langsung pakai fallback gpt-4o-mini (2.5M token/hari, cukup full day).
OPENAI_PRIMARY_WINDOW_WIB = _parse_windows_wib(os.getenv("OPENAI_PRIMARY_WINDOW_WIB", "15:00-19:30"))

LLM_TIMEOUT_SECONDS = _getenv_float("LLM_TIMEOUT_SECONDS", 35.0)

# Forecast Engine: primary & fallback models
FORECAST_MODEL = os.getenv("FORECAST_MODEL", "gpt-5.4")
FORECAST_FALLBACK_MODEL = os.getenv("FORECAST_FALLBACK_MODEL", "gemini-3.5-flash")


# --- TRADING PARAMETERS ---
# Symbol rotation: XAUUSD on weekdays, BTCUSD on weekends (crypto 24/7 while FX closed)
# Default = nama broker LIVE (suffix -ECNc). Auto-correct cuma arah demo (XAUUSD-ECNc -> XAUUSD-ECN).
WEEKDAY_SYMBOL = os.getenv("WEEKDAY_SYMBOL", "GBPUSD-ECNc")
WEEKEND_SYMBOL = os.getenv("WEEKEND_SYMBOL", "BTCUSD.c")
CRYPTO_SYMBOLS = {"BTCUSD.c", "BTCUSD", "BTCUSD.ecn", "BTCUSD.m", "BTCUSD.MT5", "BTCUSD.pro"}
ENABLE_BTC_ROTATION = _getenv_bool("ENABLE_BTC_ROTATION", False)
SYMBOL = os.getenv("SYMBOL", WEEKDAY_SYMBOL)

# --- TRADING MODE: "scanner" (2-Stage 22-Pair Quant Funnel) | "pairs" | "xau" | "xau_pairs" ---
TRADING_MODE = os.getenv("TRADING_MODE", "scanner").strip().lower()
SCANNER_MODE = _getenv_bool("SCANNER_MODE", True)

# Universe 22 Simbol Terkurasi (21 Pasangan FX + Gold)
ALL_SCANNER_SYMBOLS = [
    "EURUSD-ECNc", "GBPUSD-ECNc", "USDJPY-ECNc", "USDCHF-ECNc", "USDCAD-ECNc", "AUDUSD-ECNc",
    "EURGBP-ECNc", "EURJPY-ECNc", "EURCHF-ECNc", "EURAUD-ECNc", "EURCAD-ECNc",
    "GBPJPY-ECNc", "GBPCHF-ECNc", "GBPAUD-ECNc", "GBPCAD-ECNc",
    "AUDJPY-ECNc", "AUDCHF-ECNc", "AUDCAD-ECNc",
    "CADJPY-ECNc", "CHFJPY-ECNc", "NZDCAD-ECNc",
    "XAUUSD-ECNc"
]

SCANNER_SYMBOLS = [
    s.strip()
    for s in os.getenv("SCANNER_SYMBOLS", ",".join(ALL_SCANNER_SYMBOLS)).split(",")
    if s.strip()
]

# Fast Execution Radar interval (detik) & Rejection Wick Floor
RADAR_SCAN_INTERVAL_SECONDS = _getenv_int("RADAR_SCAN_INTERVAL_SECONDS", 60)
RADAR_MIN_WICK_RATIO = _getenv_float("RADAR_MIN_WICK_RATIO", 0.30)
ENABLE_HOURLY_RADAR_RECAP = _getenv_bool("ENABLE_HOURLY_RADAR_RECAP", True)

# Wave State Machine (Trade Permission Engine: Phase 1/2 Lock, Phase 3/4 Enable)
ENABLE_WAVE_STATE_PERMISSION = _getenv_bool("ENABLE_WAVE_STATE_PERMISSION", True)
WAVE_STATE_LOCK_PHASE2 = _getenv_bool("WAVE_STATE_LOCK_PHASE2", True)
CSM_ANTI_DUMP_THRESHOLD = _getenv_float("CSM_ANTI_DUMP_THRESHOLD", -2.0)




FX_PAIR_SYMBOLS = [
    s.strip()
    for s in os.getenv(
        "FX_PAIR_SYMBOLS",
        # Pool FX 4 simbol M30 Intraday (25 Agustus 2026):
        # GBPUSD, GBPCHF, USDJPY, AUDCAD.
        # Net Exposure: GBP×2, USD×2, CAD×1, CHF×1, AUD×1, JPY×1 (keseimbangan optimal).
        "GBPUSD-ECNc,GBPCHF-ECNc,USDJPY-ECNc,AUDCAD-ECNc",
    ).split(",")
    if s.strip()
]
MAX_ROTATION_SYMBOLS = _getenv_int("MAX_ROTATION_SYMBOLS", 22 if SCANNER_MODE else 4)  # max symbols in rotation pool

TIMEFRAME_STR = os.getenv("TIMEFRAME", "H1").upper()
TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}
TIMEFRAME = TIMEFRAME_MAP.get(TIMEFRAME_STR, mt5.TIMEFRAME_M30)
H1_TIMEFRAME = mt5.TIMEFRAME_H1

# Dynamic Session Timeframe: H1 saat Sesi Tokyo (08:00 - 14:00 WIB), M30 saat London/NY (14:00 - 00:00 WIB)
DYNAMIC_SESSION_TIMEFRAME = _getenv_bool("DYNAMIC_SESSION_TIMEFRAME", True)
ASIA_TIMEFRAME = os.getenv("ASIA_TIMEFRAME", "H1").upper()
LONDON_NY_TIMEFRAME = os.getenv("LONDON_NY_TIMEFRAME", "M30").upper()
DYNAMIC_TF_SWITCH_HOUR_WIB = _getenv_int("DYNAMIC_TF_SWITCH_HOUR_WIB", 14)

STARTING_BALANCE = _getenv_float("STARTING_BALANCE", 1000.0)

LOT_SIZE = _getenv_float("LOT_SIZE", 0.01)
LOT_SIZE_XAU = _getenv_float("LOT_SIZE_XAU", LOT_SIZE)
LOT_SIZE_BTC = _getenv_float("LOT_SIZE_BTC", 0.01)

RISK_PERCENT_BTC = _getenv_float("RISK_PERCENT_BTC", 1.5)
RISK_PERCENT_XAU = _getenv_float("RISK_PERCENT_XAU", 1.0)
RISK_PERCENT_FX = _getenv_float("RISK_PERCENT_FX", 1.0)
DEVIATION = _getenv_int("DEVIATION", 30)
DEVIATION_XAU = _getenv_int("DEVIATION_XAU", 60)  # 60 pts ($0.60) - sweet spot 50-75 pts
DEVIATION_BTC = _getenv_int("DEVIATION_BTC", 1000)


def deviation_for(symbol):
    """Slippage deviation tolerance in points per asset category.
    XAU: 60 pts ($0.60) - sweet spot 50-75 pts.
    BTC: 1000 pts ($10.00).
    FX: 30 pts (3 pips).
    """
    if is_crypto(symbol):
        return DEVIATION_BTC
    if "XAU" in (symbol or "").upper() or "GOLD" in (symbol or "").upper():
        return DEVIATION_XAU
    return DEVIATION

# TP_SL_RULES default "LLM" (13 Agustus): SL/TP bebas sesuai thesis LLM (invalidation/target
# price), safety floor per-kategori (14 Agustus: XAU 400 pts, FX 250 pts) + R:R min 1.25:1.
# Mode "ATR-Based" tetap tersedia via .env/menu/--tpsl-rules - gate ATR R:R 2:1
# (single 1.25/2.5, dual 1.5/3.0, triple 1.75/3.5).
#
# PER-KATEGORI (13 Agustus, pisah logic biar enak debug):
# - XAUUSD: LLM (13 Agustus - soft floor 400-1000, gate over-risk; max lot cap
#   dihapus 14 Agustus - lot murni risk-based sesuai volume_max broker).
# - BTC: SELALU ATR-Based (fix) - anti-scalping; gate ATR R:R 2:1.
#   SL >= SL_MULT x ATR, TP >= TP_MULT x ATR; floor 400 pts cuma 0.49x ATR M15
#   (ATR M15 XAU ~819 pts) -> terlalu scalping utk swing M15.
# - FX pairs: LLM (bebas struktur, safety floor dinamis max(2x spread, 1.5x ATR H1)
#   via LLM_FX_FLOOR_ATR_MULT, fallback 250 pts kalau ATR gagal; R:R min 1.25:1) - cocok utk H1 swing.
# - Kalau TP_SL_RULES di-set eksplisit ke "ATR-Based" (CLI --tpsl-rules / .env),
#   SEMUA kategori ikut ATR-Based (force). Default "LLM" = per-kategori di atas.
TP_SL_RULES = os.getenv("TP_SL_RULES", "LLM")

DEFAULT_SL_POINTS = _getenv_int("DEFAULT_SL_POINTS", 300)
DEFAULT_TP_POINTS = _getenv_int("DEFAULT_TP_POINTS", 600)
SL_ATR_MULTIPLIER = _getenv_float("SL_ATR_MULTIPLIER", 1.5)
TP_ATR_MULTIPLIER = _getenv_float("TP_ATR_MULTIPLIER", 3.0)

DEFAULT_SL_POINTS_XAU = _getenv_int("DEFAULT_SL_POINTS_XAU", 500)
DEFAULT_TP_POINTS_XAU = _getenv_int("DEFAULT_TP_POINTS_XAU", 1000)
DEFAULT_SL_POINTS_BTC = _getenv_int("DEFAULT_SL_POINTS_BTC", 50000)
DEFAULT_TP_POINTS_BTC = _getenv_int("DEFAULT_TP_POINTS_BTC", 100000)
# Default SL/TP FX (12 Agustus, FASE 1): FX trading H1 swing - default flat 100/200 pts
# (10/20 pips FX scale). Dulu per-pair 50/100 & 40/80 waktu FX masih M5 scalping;
# sejak pindah H1, ATR H1 jauh lebih besar jadi 100/200 lebih pas. Gate ATR-Based tetap
# menolak otomatis kalau proposal SL/TP < multiplier x ATR (lihat atr_sl_multiplier).

# --- LLM MODE SAFETY FLOOR & R:R GATE (14 Agustus) ---
# Mode LLM (XAU & FX): SL/TP bebas struktur LLM, tapi dibatasi safety floor minimal
# (mencegah SL mikro 5 pips yang membengkakkan lot) + gate R:R minimum.
# Safety floor SL/TP mode LLM (14 Agustus):
#   - FX pairs: floor berbasis ATR aktif (default 1.5x ATR H1, `LLM_FX_FLOOR_ATR_MULT`).
#     Fallback statis 250 pts (25 pips) dipakai kalau ATR gagal dihitung.
#     Alasan (14 Agustus lanjutan): floor statis 250 pts = 2.5-2.8x ATR H1 FX
#     (~90-100 pts) -> semua SL struktural asli (60-200 pts) di-floor paksa +
#     TP 312 (3.2x ATR) jarang kesampean. ATR-based menyesuaikan volatilitas.
#   - XAUUSD:   floor berbasis ATR aktif (default 1.2x ATR M15, `LLM_XAU_FLOOR_ATR_MULT`,
#     15 Agustus - user minta "floor 1x atr secara lunak", final 1.2x; SL tipis 0.8x ATR
#     dari o4-mini di-floor ke 1.2x ATR). Fallback statis 400 pts kalau ATR gagal.
#   - R:R minimum 1.25 : 1 (TP >= 1.25 x SL)
LLM_FX_FLOOR_ATR_MULT = _getenv_float("LLM_FX_FLOOR_ATR_MULT", 1.3)
LLM_XAU_FLOOR_ATR_MULT = _getenv_float("LLM_XAU_FLOOR_ATR_MULT", 1.8)  # 1.8x ATR buffer agar kebal dari spike hunting di sesi NY
LLM_SAFETY_FLOOR_FX_PTS = _getenv_int("LLM_SAFETY_FLOOR_FX_PTS", 250)   # fallback kalau ATR gagal
LLM_SAFETY_FLOOR_XAU_PTS = _getenv_int("LLM_SAFETY_FLOOR_XAU_PTS", 600)  # fallback kalau ATR gagal (6 USD)
LLM_MIN_RR_RATIO = _getenv_float("LLM_MIN_RR_RATIO", 1.25)
SL_PADDING_NZD_POINTS = _getenv_int("SL_PADDING_NZD_POINTS", 20)  # +20 pts (2.0 pips) anti-wick padding untuk pair silang NZD

# Gate OVER-RISK di consensus: SL yang gak muat di min lot (risk aktual > budget
# per-trade) TIDAK otomatis ditolak di risk_pct — masih diterima selama risk aktual
# di min lot <= OVER_RISK_MAX_PERCENT (14 Agustus malam: user minta SL >1000 pts
# boleh jalan asal gate maks 2%; lot tetap risk-based 1%, cuma gate ceiling-nya ini).
OVER_RISK_MAX_PERCENT = _getenv_float("OVER_RISK_MAX_PERCENT", 2.0)



# --- CONSENSUS SETTINGS ---
DRY_RUN = _getenv_bool("DRY_RUN", False)
TRADING_PAUSED = _getenv_bool("TRADING_PAUSED", False)

ERA_PRESETS = {
    "v1": {
        "label": "V1 - era profit 100% (legacy)",
        "DRY_RUN": True,
        "RISK_PERCENT_XAU": 1.0,
        "RISK_PERCENT_BTC": 1.0,
        "CONFIDENCE_CONSENSUS_THRESHOLD_XAU": 1.2,
        "CONFIDENCE_CONSENSUS_THRESHOLD_BTC": 1.2
    },
    "v2": {
        "label": "V2 - legacy-2 (= v1 + state)",
        "DRY_RUN": True,
        "RISK_PERCENT_XAU": 1.0,
        "RISK_PERCENT_BTC": 1.0,
        "CONFIDENCE_CONSENSUS_THRESHOLD_XAU": 1.2,
        "CONFIDENCE_CONSENSUS_THRESHOLD_BTC": 1.2
    },
    "v3": {
        "label": "V3 - modern (Claude + quant, sekarang)",
        "DRY_RUN": False,
        "RISK_PERCENT_XAU": 1.0,
        "RISK_PERCENT_BTC": 1.5,
        "CONFIDENCE_CONSENSUS_THRESHOLD_XAU": 1.2,
        "CONFIDENCE_CONSENSUS_THRESHOLD_BTC": 1.2
    }
}

CONSENSUS_THRESHOLD = _getenv_int("CONSENSUS_THRESHOLD", 2)
DYNAMIC_CONFIG_ENABLED = _getenv_bool("DYNAMIC_CONFIG_ENABLED", False)

CONFIDENCE_CONSENSUS_THRESHOLD_XAU = _getenv_float("CONFIDENCE_CONSENSUS_THRESHOLD_XAU", 1.2)
CONFIDENCE_CONSENSUS_THRESHOLD_BTC = _getenv_float("CONFIDENCE_CONSENSUS_THRESHOLD_BTC", 1.2)
MIN_CONSENSUS_MODELS = _getenv_int("MIN_CONSENSUS_MODELS", 2)

# --- TIME-BASED AI MODE SCHEDULE (WIB) ---
# Format: (start_hour, start_minute, end_hour, end_minute, mode)
# Mode values: "single" | "single_gemini" | "dual" | "triple"
AI_MODE_POLICY = os.getenv("AI_MODE_POLICY", "fixed").strip().lower()  # schedule | fixed
AI_FIXED_MODE = os.getenv("AI_FIXED_MODE", "triple").strip().lower()
# Jadwal WIB (Single Mode DIHAPUS TOTAL demi keamanan - minimal 2 model sepakat):
#   - dual   (OpenAI o4-mini + Gemini 3.1-flash-lite): 00:00–18:59 (Asia & London session; 00:00-09:00 Dead Zone risk gate)
#   - triple (OpenAI + Gemini + Claude/DeepSeek): 19:00–22:00 (London-NY overlap, puncak volatilitas — 4x call H1 pada jam 19, 20, 21, dan 22 WIB)
#   - dual   (OpenAI o4-mini + Gemini 3.1-flash-lite): 22:01–23:59 (Late NY session)
AI_MODE_SCHEDULE = [
    (0, 0, 18, 59, "dual"),
    (19, 0, 22, 0, "triple"),
    (22, 1, 23, 59, "dual"),
]

# Model pengisi slot kedua di mode "dual". Default "Gemini" (o4-mini + gemini-3.1-flash-lite).
AI_DUAL_SECOND_MODEL = os.getenv("AI_DUAL_SECOND_MODEL", "Gemini")

FORCE_ACTIVE_ENTRY = _getenv_bool("FORCE_ACTIVE_ENTRY", False)
QUANT_ANALYSIS_ENABLED = _getenv_bool("QUANT_ANALYSIS_ENABLED", False)
MONTE_CARLO_ENABLED = _getenv_bool("MONTE_CARLO_ENABLED", False)
FORECAST_ENABLED = _getenv_bool("FORECAST_ENABLED", False)
MEMORY_CONTEXT_ENABLED = _getenv_bool("MEMORY_CONTEXT_ENABLED", False)  # OFF: lesson learned & recent outcomes TIDAK di-inject ke prompt LLM (lesson M5-scalp toxic, bikin HOLD terus). Kode tetap ada, tinggal set True kalau mau aktif lagi.

# --- ECONOMIC NEWS (kalender ekonomi, 20 Agustus) ---
# Fetch high-impact events dari TradingView API (data Investing.com) tiap N jam,
# di-inject ke prompt LLM sebagai NEWS WINDOW GUARD. Event global (FOMC/NFP/
# Powell/Trump speech) masuk ke SEMUA symbol; event negara lain hanya masuk ke
# pair yang mengandung mata uang negara tsb (mis. ECB -> EURJPY/EURCHF saja).
ECONOMIC_NEWS_ENABLED = _getenv_bool("ECONOMIC_NEWS_ENABLED", True)
ECONOMIC_NEWS_TTL_HOURS = _getenv_int("ECONOMIC_NEWS_TTL_HOURS", 6)  # fetch tiap 6 jam
ECONOMIC_NEWS_COUNTRIES = [
    c.strip().upper() for c in os.getenv("ECONOMIC_NEWS_COUNTRIES", "US,GB,EU,CH,JP,AU,CA").split(",") if c.strip()
]
ECONOMIC_NEWS_GLOBAL_KEYWORDS = (
    "FOMC", "NFP", "Non Farm", "Payroll", "Payrolls", "Powell", "Trump",
    "Warsh", "Fed Chair", "Fed Chairman", "Fed Rate", "Benchmark Payrolls"
)
# Event US lain (CPI, PCE, Retail Sales, Unemployment, GDP US, ISM, dst) =
# pair-specific USD -> hanya GBPUSD yang kena.

# POST_MORTEM_ENABLED = False (default): mesin post-mortem (trade_evaluator) DIMATIKAN.
# Hasilnya (lessons) sudah tidak dipakai karena MEMORY_CONTEXT_ENABLED=False, tapi
# mesinnya masih manggil LLM per trade close = buang biaya + nulis lesson toxic/salah
# simbol. Kode tetap ada, tinggal set True kalau mau aktif lagi.
POST_MORTEM_ENABLED = _getenv_bool("POST_MORTEM_ENABLED", False)

# --- TRAILING STOP ---
TRAILING_STOP_ENABLED = _getenv_bool("TRAILING_STOP_ENABLED", True)
TRAILING_ACTIVATION_POINTS = _getenv_int("TRAILING_ACTIVATION_POINTS", 200)
TRAILING_DISTANCE_POINTS = _getenv_int("TRAILING_DISTANCE_POINTS", 150)

TRAILING_ACTIVATION_POINTS_XAU = _getenv_int("TRAILING_ACTIVATION_POINTS_XAU", TRAILING_ACTIVATION_POINTS)
TRAILING_DISTANCE_POINTS_XAU = _getenv_int("TRAILING_DISTANCE_POINTS_XAU", TRAILING_DISTANCE_POINTS)
TRAILING_ACTIVATION_POINTS_BTC = _getenv_int("TRAILING_ACTIVATION_POINTS_BTC", 17000)
TRAILING_DISTANCE_POINTS_BTC = _getenv_int("TRAILING_DISTANCE_POINTS_BTC", 12500)

TRAILING_ACTIVATION_ATR_MULT_BTC = _getenv_float("TRAILING_ACTIVATION_ATR_MULT_BTC", 1.0)
TRAILING_DISTANCE_ATR_MULT_BTC = _getenv_float("TRAILING_DISTANCE_ATR_MULT_BTC", 0.5)
TRAILING_ACTIVATION_ATR_MULT_XAU = _getenv_float("TRAILING_ACTIVATION_ATR_MULT_XAU", 1.2)
TRAILING_DISTANCE_ATR_MULT_XAU = _getenv_float("TRAILING_DISTANCE_ATR_MULT_XAU", 0.5)
TRAILING_ACTIVATION_MAX_POINTS_BTC = _getenv_int("TRAILING_ACTIVATION_MAX_POINTS_BTC", 40000)
TRAILING_ACTIVATION_MAX_POINTS_XAU = _getenv_int("TRAILING_ACTIVATION_MAX_POINTS_XAU", 600)
# Distance trailing GLOBAL: KONSTAN 0.5x ATR(14) dari harga ekstrem (20 Agustus malam).
# Hasil backtest S9 GBPUSD (n=174): act70 + atr0.5 = EV +0.272 (terbaik, nyaris baseline
# +0.302); progressive SL +0.197, adaptif +0.041, fixed pips +0.128-0.180 (inferior).
TRAILING_DISTANCE_ATR_MULT_FX = _getenv_float("TRAILING_DISTANCE_ATR_MULT_FX", 0.5)

# --- GLOBAL BEP & TRAILING (20 Agustus malam, refactor global single-path) ---
# Percabangan mode LLM vs ATR-Based DIHAPUS -> satu jalur global per simbol.
# Hasil backtest matrix (scratch/bep_trail_matrix.py, S9 BUY GBPUSD n=174):
#   - BEP 35% +0.158 | 50% +0.205 | 65% +0.222  (BEP lebih telat = lebih baik;
#     user memilih 58%: "aktif di 58% TP jangan telat banget")
#   - TRAIL act70 + dist 0.5x ATR = +0.272 (terbaik, nyaris setara baseline +0.302)
#   - progressive SL +0.197 | adaptif/range +0.041 | fixed pips +0.128-0.180 (inferior)
# Konstanta SL_MULT di bawah = FALLBACK untuk posisi tanpa TP.
BREAK_EVEN_TRIGGER_TP_PCT = _getenv_float("BREAK_EVEN_TRIGGER_TP_PCT", 0.45)  # BEP aktif saat profit >= 45% TP (padding komisi tetap dipertahankan)
TRAILING_ACTIVATION_TP_PCT = _getenv_float("TRAILING_ACTIVATION_TP_PCT", 0.65)  # trailing aktif saat profit >= 65% TP
TRAILING_TERMINAL_TP_PCT = _getenv_float("TRAILING_TERMINAL_TP_PCT", 0.90)      # Terminal tightening aktif saat profit >= 90% TP (ATR M30 lock)
TRAILING_DISTANCE_ATR_MULT_H1 = _getenv_float("TRAILING_DISTANCE_ATR_MULT_H1", 0.75)  # Multiplier ATR H1 untuk normal swing trailing
TRAILING_BREAK_EVEN_SL_MULT = _getenv_float("BREAK_EVEN_TRIGGER_SL_MULT", 0.6)  # fallback tanpa TP: BEP di 0.6x SL
TRAILING_ACTIVATION_SL_MULT = _getenv_float("TRAILING_ACTIVATION_SL_MULT", 1.0)  # fallback tanpa TP: activation 1.0x SL
TRAILING_DISTANCE_MIN_POINTS_FX = _getenv_int("TRAILING_DISTANCE_MIN_POINTS_FX", 80)    # Floor absolut jarak normal trailing FX (8 pips)
TRAILING_DISTANCE_MIN_POINTS_TERMINAL_FX = _getenv_int("TRAILING_DISTANCE_MIN_POINTS_TERMINAL_FX", 30)  # Floor absolut terminal trailing (3 pips)
TRAILING_DISTANCE_MIN_POINTS_XAU = _getenv_int("TRAILING_DISTANCE_MIN_POINTS_XAU", 100)  # Floor absolut jarak trailing XAU (pts)


# --- BREAK-EVEN ---
BREAK_EVEN_ENABLED = _getenv_bool("BREAK_EVEN_ENABLED", True)
BREAK_EVEN_TRIGGER_POINTS = _getenv_int("BREAK_EVEN_TRIGGER_POINTS", 300)
BREAK_EVEN_PADDING_POINTS = _getenv_int("BREAK_EVEN_PADDING_POINTS", 10)

BREAK_EVEN_TRIGGER_POINTS_XAU = _getenv_int("BREAK_EVEN_TRIGGER_POINTS_XAU", BREAK_EVEN_TRIGGER_POINTS)
BREAK_EVEN_PADDING_POINTS_XAU = _getenv_int("BREAK_EVEN_PADDING_POINTS_XAU", BREAK_EVEN_PADDING_POINTS)
BREAK_EVEN_TRIGGER_POINTS_BTC = _getenv_int("BREAK_EVEN_TRIGGER_POINTS_BTC", 33500)
BREAK_EVEN_PADDING_POINTS_BTC = _getenv_int("BREAK_EVEN_PADDING_POINTS_BTC", 1000)

# --- PARTIAL CLOSE ---
PARTIAL_CLOSE_ENABLED = _getenv_bool("PARTIAL_CLOSE_ENABLED", True)
PARTIAL_CLOSE_PERCENT = _getenv_float("PARTIAL_CLOSE_PERCENT", 50.0)
PARTIAL_CLOSE_TRIGGER_TP_PCT = _getenv_float("PARTIAL_CLOSE_TRIGGER_TP_PCT", 0.45)  # Partial close aktif di 45% TP
PARTIAL_CLOSE_TP1_POINTS = _getenv_int("PARTIAL_CLOSE_TP1_POINTS", 400)

PARTIAL_CLOSE_TP1_POINTS_XAU = _getenv_int("PARTIAL_CLOSE_TP1_POINTS_XAU", PARTIAL_CLOSE_TP1_POINTS)
PARTIAL_CLOSE_TP1_POINTS_BTC = _getenv_int("PARTIAL_CLOSE_TP1_POINTS_BTC", 44500)

# --- DAILY RISK LIMITS ---
MAX_DAILY_LOSS_PERCENT = _getenv_float("MAX_DAILY_LOSS_PERCENT", 4.0)
MAX_DAILY_LOSS_USD = _getenv_float("MAX_DAILY_LOSS_USD", 50.0)
MAX_CONSECUTIVE_LOSSES = _getenv_int("MAX_CONSECUTIVE_LOSSES", 5)
PAUSE_AFTER_LOSSES_MINUTES = _getenv_int("PAUSE_AFTER_LOSSES_MINUTES", 15)
MAX_OPEN_POSITIONS = _getenv_int("MAX_OPEN_POSITIONS", 6)
BREAK_EVEN_TOLERANCE_USD = _getenv_float("BREAK_EVEN_TOLERANCE_USD", 0.04)
MAX_OPEN_POSITIONS_RECOVERY = _getenv_int("MAX_OPEN_POSITIONS_RECOVERY", 3)
MAX_OPEN_POSITIONS_LATE_NY = _getenv_int("MAX_OPEN_POSITIONS_LATE_NY", 2)  # 23:00 - 02:00 WIB max 2 posisi


def get_max_open_positions(in_recovery_mode=False, now=None):
    """Maksimum open posisi agregat (semua simbol):
    - Normal (11:00 - 23:00 WIB): MAX_OPEN_POSITIONS (6)
    - Recovery Mode: MAX_OPEN_POSITIONS_RECOVERY (3)
    - Late NY (23:00 - 02:00 WIB): MAX_OPEN_POSITIONS_LATE_NY (2)
      (kalau recovery mode aktif di jam late NY, tetap min(2, 3) = 2).
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
    now = now or datetime.now(WIB)
    cur_min = now.hour * 60 + now.minute

    # 23:00 s.d. 02:00 WIB
    is_late_ny = (cur_min >= 23 * 60) or (cur_min < 2 * 60)
    if is_late_ny:
        base = MAX_OPEN_POSITIONS_LATE_NY
    elif in_recovery_mode:
        base = MAX_OPEN_POSITIONS_RECOVERY
    else:
        base = MAX_OPEN_POSITIONS

    if in_recovery_mode:
        return min(base, MAX_OPEN_POSITIONS_RECOVERY)
    return base
# --- DAILY PROFIT TARGET (14 Agustus) ---
# Begitu net profit harian (WIB-midnight, dari get_closed_positions_today) mencapai
# X% dari balance MT5, bot STOP membuka posisi baru sampai tengah malam WIB berikutnya
# (reset otomatis karena window P/L harian = tengah malam WIB -> next-midnight).
DAILY_PROFIT_TARGET_PERCENT = _getenv_float("DAILY_PROFIT_TARGET_PERCENT", 6.0)
MAX_DAILY_LOSS_PERCENT      = _getenv_float("MAX_DAILY_LOSS_PERCENT", 4.0)
MAX_DAILY_LOSS_USD          = _getenv_float("MAX_DAILY_LOSS_USD", 250.0)
DAILY_LOSS_OPENED_TODAY_ONLY = _getenv_bool("DAILY_LOSS_OPENED_TODAY_ONLY", True)


def bep_tolerance_for(deal):
    """
    BEP tolerance DINAMIS per trade (bukan statis 0.04).

    Trade di akun ECN kena komisi per lot: $6/lot round-trip ->
    0.01 lot = -0.06, 0.10 lot = -0.60, 0.26 lot = -1.56. Kalau tolerance
    statis 0.04, trade kecil yang cuma "kalah sebesar komisi" malah dihitung
    loss (nambah streak / nurunin win rate), padahal secara arah dia BEP -
    rugi cuma dari biaya, bukan dari pergerakan harga.

    Aturan: tolerance = max(BREAK_EVEN_TOLERANCE_USD, komisi aktual trade).
    Trade dengan |net profit| <= tolerance dianggap BEP.

    `deal` menerima dict hasil `get_closed_positions_today` (punya field
    "commission" = komisi+fee netto, negatif) atau dict sederhana
    {"commission": X}. Kalau field tidak ada -> fallback ke tolerance statis.
    """
    tol = BREAK_EVEN_TOLERANCE_USD
    comm = 0.0
    if isinstance(deal, dict):
        comm = abs(float(deal.get("commission", 0.0) or 0.0))
    else:
        comm = abs(float(getattr(deal, "commission", 0.0) or 0.0))
    return max(tol, comm)

# --- RECOVERY MODE ---
RECOVERY_MODE_ENABLED = _getenv_bool("RECOVERY_MODE_ENABLED", True)
RECOVERY_LOT_MULTIPLIER = _getenv_float("RECOVERY_LOT_MULTIPLIER", 0.5)
RECOVERY_EXIT_PROFIT_USD = _getenv_float("RECOVERY_EXIT_PROFIT_USD", 0.10)
TRADE_COOLDOWN_SECONDS = _getenv_int("TRADE_COOLDOWN_SECONDS", 0)

# --- SPREAD FILTER ---
MAX_SPREAD_POINTS = _getenv_int("MAX_SPREAD_POINTS", 50)
MAX_SPREAD_POINTS_XAU = _getenv_int("MAX_SPREAD_POINTS_XAU", MAX_SPREAD_POINTS)
MAX_SPREAD_POINTS_BTC = _getenv_int("MAX_SPREAD_POINTS_BTC", 2400)
# FX spread cap: ATR-based = max(SPREAD_ATR_RATIO × ATR_H1_pts, SPREAD_ATR_FLOOR_PTS)
# Lebih adil antar-pair: pair volatile (EURNZD, GBPJPY) dapat toleransi lebih besar,
# pair slow-mover (EURCHF) tidak langsung kena flat-cap 50 pts yang terlalu longgar.
SPREAD_ATR_RATIO     = float(os.getenv("SPREAD_ATR_RATIO", "0.15"))   # 15% ATR H1
SPREAD_ATR_FLOOR_PTS = _getenv_int("SPREAD_ATR_FLOOR_PTS", 20)        # floor minimum FX (pts)

# --- SESSION FILTER ---
# Trade Zone: 09:00 - 00:00 WIB (00:00 - 09:00 WIB Dead Zone Rollover & Sepi Likuiditas)
SESSION_FILTER_ENABLED = _getenv_bool("SESSION_FILTER_ENABLED", True)
ALLOWED_SESSIONS_WIB = [
    {"name": "Tokyo / Asia Pagi", "start": (8, 0),  "end": (16, 0),  "lot_multiplier": 0.7},
    {"name": "London",            "start": (15, 0), "end": (23, 0),  "lot_multiplier": 1.0},
    {"name": "London-NY Overlap", "start": (19, 0), "end": (21, 0),  "lot_multiplier": 1.2},
    {"name": "New York",          "start": (20, 0), "end": (0, 0),   "lot_multiplier": 1.0},
]

# Danger zones (Dead Zone subuh & rollover 00:00 - 08:00 WIB). Berlaku XAU & FX; BTC 24/7.
DANGER_ZONES_WIB = [
    {"name": "Overnight Rollover Dead Zone (00:00 - 08:00 WIB)", "start": (0, 0), "end": (8, 0),
     "reason": "Dead Zone rollover & sepi likuiditas (00:00 - 08:00 WIB)"},
]

# --- WEEKEND PROTECTION ---
WEEKEND_CLOSE_ENABLED = _getenv_bool("WEEKEND_CLOSE_ENABLED", True)
WEEKEND_CLOSE_PROFIT_MIN_USD = _getenv_float("WEEKEND_CLOSE_PROFIT_MIN_USD", 1.0)
WEEKEND_CLOSE_HOURS_BEFORE = _getenv_float("WEEKEND_CLOSE_HOURS_BEFORE", 2.0)
WEEKEND_MAX_LOSS_TO_HOLD_USD = _getenv_float("WEEKEND_MAX_LOSS_TO_HOLD_USD", 20.0)
WEEKEND_TRADING_ENABLED = _getenv_bool("WEEKEND_TRADING_ENABLED", False)

# --- TIME-DECAY STAGNATION & PRE-ROLLOVER SHIELD (Ide 1) ---
TIME_DECAY_STAGNATION_ENABLED = _getenv_bool("TIME_DECAY_STAGNATION_ENABLED", True)
TIME_DECAY_HOURS              = _getenv_float("TIME_DECAY_HOURS", 4.0)          # Max hold 4 jam jika stagnan (8 bar M30)
TIME_DECAY_MIN_R              = _getenv_float("TIME_DECAY_MIN_R", -0.20)         # Floating min boundary
TIME_DECAY_MAX_R              = _getenv_float("TIME_DECAY_MAX_R", 0.20)          # Floating max boundary
TIME_DECAY_MAX_PEAK_R         = _getenv_float("TIME_DECAY_MAX_PEAK_R", 0.30)    # Hanya close jika peak < +0.30R
TIME_DECAY_START_HOUR_WIB     = _getenv_int("TIME_DECAY_START_HOUR_WIB", 14)    # Hanya aktif di sesi London-NY (14:00 WIB)
TIME_DECAY_END_HOUR_WIB       = _getenv_int("TIME_DECAY_END_HOUR_WIB", 0)       # s/d 00:00 WIB midnight

PRE_ROLLOVER_SHIELD_ENABLED   = _getenv_bool("PRE_ROLLOVER_SHIELD_ENABLED", True)
PRE_ROLLOVER_EXIT_HOUR_WIB    = _getenv_int("PRE_ROLLOVER_EXIT_HOUR_WIB", 3)      # 03:00 WIB
PRE_ROLLOVER_EXIT_MINUTE_WIB  = _getenv_int("PRE_ROLLOVER_EXIT_MINUTE_WIB", 50)  # 03:50 WIB
PRE_ROLLOVER_SLIPPAGE_EURCHF_PTS = _getenv_float("PRE_ROLLOVER_SLIPPAGE_EURCHF_PTS", 240.0)
PRE_ROLLOVER_SLIPPAGE_GBPCHF_PTS = _getenv_float("PRE_ROLLOVER_SLIPPAGE_GBPCHF_PTS", 210.0)
PRE_ROLLOVER_SLIPPAGE_EURNZD_PTS = _getenv_float("PRE_ROLLOVER_SLIPPAGE_EURNZD_PTS", 240.0)
PRE_ROLLOVER_SLIPPAGE_GBPUSD_PTS = _getenv_float("PRE_ROLLOVER_SLIPPAGE_GBPUSD_PTS", 180.0)
PRE_ROLLOVER_SLIPPAGE_USDJPY_PTS = _getenv_float("PRE_ROLLOVER_SLIPPAGE_USDJPY_PTS", 150.0)
PRE_ROLLOVER_SLIPPAGE_NZDCAD_PTS = _getenv_float("PRE_ROLLOVER_SLIPPAGE_NZDCAD_PTS", 140.0)
PRE_ROLLOVER_SLIPPAGE_AUDCAD_PTS = _getenv_float("PRE_ROLLOVER_SLIPPAGE_AUDCAD_PTS", 130.0)
PRE_ROLLOVER_SLIPPAGE_DEFAULT_PTS = _getenv_float("PRE_ROLLOVER_SLIPPAGE_DEFAULT_PTS", 200.0)


def get_pre_rollover_slippage_threshold(symbol: str) -> float:
    """Mengembalikan threshold jarak SL kritis (points) saat jendela pre-rollover 03:50 WIB."""
    s_clean = (symbol or "").replace("-ECNc", "").replace(".c", "").upper()
    if "EURCHF" in s_clean:
        return PRE_ROLLOVER_SLIPPAGE_EURCHF_PTS
    elif "GBPCHF" in s_clean:
        return PRE_ROLLOVER_SLIPPAGE_GBPCHF_PTS
    elif "EURNZD" in s_clean:
        return PRE_ROLLOVER_SLIPPAGE_EURNZD_PTS
    elif "GBPUSD" in s_clean:
        return PRE_ROLLOVER_SLIPPAGE_GBPUSD_PTS
    elif "USDJPY" in s_clean:
        return PRE_ROLLOVER_SLIPPAGE_USDJPY_PTS
    elif "NZDCAD" in s_clean:
        return PRE_ROLLOVER_SLIPPAGE_NZDCAD_PTS
    elif "AUDCAD" in s_clean:
        return PRE_ROLLOVER_SLIPPAGE_AUDCAD_PTS
    return PRE_ROLLOVER_SLIPPAGE_DEFAULT_PTS

# --- DYNAMIC VOLATILITY SCALING (Ide 4) ---
VOL_REGIME_SCALING_ENABLED    = _getenv_bool("VOL_REGIME_SCALING_ENABLED", True)
VOL_REGIME_LOW_THRESHOLD      = _getenv_float("VOL_REGIME_LOW_THRESHOLD", 0.70)   # < 0.70x baseline
VOL_REGIME_HIGH_THRESHOLD     = _getenv_float("VOL_REGIME_HIGH_THRESHOLD", 1.20)  # > 1.20x baseline
VOL_REGIME_LOW_MULTIPLIER     = _getenv_float("VOL_REGIME_LOW_MULTIPLIER", 0.75)  # 0.75x sizing
VOL_REGIME_NORMAL_MULTIPLIER  = _getenv_float("VOL_REGIME_NORMAL_MULTIPLIER", 1.00)
VOL_REGIME_HIGH_MULTIPLIER    = _getenv_float("VOL_REGIME_HIGH_MULTIPLIER", 1.15) # 1.15x sizing
VOL_REGIME_LOW_BEP_RATIO      = _getenv_float("VOL_REGIME_LOW_BEP_RATIO", 0.45)   # 45% TP saat low vol

# --- PATTERN EDGE WHISPER (16 Agustus, dev-backtest) ---
# Inject statistik pola tervalidasi (dari riset pattern_research.py) ke prompt LLM
# kalau pola di candle terakhir match registry EDGE. Informational only.
PATTERN_WHISPER_ENABLED = _getenv_bool("PATTERN_WHISPER_ENABLED", True)

POSITION_MANAGER_MAX_TICK_AGE_SECONDS = _getenv_int("POSITION_MANAGER_MAX_TICK_AGE_SECONDS", 300)

# --- PENDING ORDER (LIMIT/STOP) ---
# Default OFF - fitur baru, JANGAN nyalakan di akun LIVE sebelum tervalidasi
# di demo/dry-run. Saat aktif, LLM boleh kasih entry_type (market/buy_stop/
# sell_stop/buy_limit/sell_limit) + entry_price. Pending punya expiration,
# tereksekusi -> posisi normal (SL/TP + BEP + trailing).
PENDING_ORDERS_ENABLED = _getenv_bool("PENDING_ORDERS_ENABLED", True)
PENDING_ORDER_EXPIRY_MINUTES = _getenv_int("PENDING_ORDER_EXPIRY_MINUTES", 60)
PENDING_ORDER_EXPIRY_MINUTES_ASIA = _getenv_int("PENDING_ORDER_EXPIRY_MINUTES_ASIA", 120)  # Sesi Tokyo / Asia (08:00–14:00 WIB)
PENDING_ORDER_EXPIRY_MINUTES_LDN_NY = _getenv_int("PENDING_ORDER_EXPIRY_MINUTES_LDN_NY", 60) # Sesi London / NY (14:00–00:00 WIB)
PENDING_ORDER_MAX_ACTIVE = _getenv_int("PENDING_ORDER_MAX_ACTIVE", 4)


def get_pending_order_expiry_minutes(now=None):
    """Expiry pending order adaptif sesi:
    - Sesi Tokyo / Asia (08:00 - 14:00 WIB): 120 Menit (2 jam)
    - Sesi London / NY (14:00 - 00:00 WIB): 60 Menit (1 jam)
    - Di luar jam di atas / Late NY: 60 Menit
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
    now_wib = now or datetime.now(WIB)
    cur_hour = now_wib.hour
    if 8 <= cur_hour < 14:
        return PENDING_ORDER_EXPIRY_MINUTES_ASIA
    return PENDING_ORDER_EXPIRY_MINUTES_LDN_NY

# Jarak entry pending dari harga sekarang: minimal 2x spread, maksimal 1.5x ATR
PENDING_ENTRY_MIN_SPREAD_MULT = _getenv_float("PENDING_ENTRY_MIN_SPREAD_MULT", 2.0)
PENDING_ENTRY_MAX_ATR_MULT = _getenv_float("PENDING_ENTRY_MAX_ATR_MULT", 1.5)
# File statistik "AI proven" - riwayat pending order + outcome (persist)
PENDING_ORDERS_STATE_FILE = os.path.join(DATA_DIR, "pending_orders_state.json")

# --- TELEGRAM ALERTS ---
TELEGRAM_NOTIFY_HOLD = _getenv_bool("TELEGRAM_NOTIFY_HOLD", False)

# --- MT5 CONNECTION ---
MT5_ACCOUNT_MODE = os.getenv("MT5_ACCOUNT_MODE", "live").lower()  # "live" | "demo"
MT5_LOGIN = ""
MT5_PASSWORD = ""
MT5_SERVER = ""
MAGIC_NUMBER = _getenv_int("MAGIC_NUMBER", 20260625)

def refresh_mt5_credentials():
    """Reloads MT5 login credentials from current MT5_ACCOUNT_MODE."""
    global MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
    if MT5_ACCOUNT_MODE == "demo":
        MT5_LOGIN = os.getenv("MT5_DEMO_LOGIN", "")
        MT5_PASSWORD = os.getenv("MT5_DEMO_PASSWORD", "")
        MT5_SERVER = os.getenv("MT5_DEMO_SERVER", "")
    else:
        MT5_LOGIN = os.getenv("MT5_LIVE_LOGIN", os.getenv("MT5_LOGIN", ""))
        MT5_PASSWORD = os.getenv("MT5_LIVE_PASSWORD", os.getenv("MT5_PASSWORD", ""))
        MT5_SERVER = os.getenv("MT5_LIVE_SERVER", os.getenv("MT5_SERVER", ""))
    
    if MT5_LOGIN:
        try:
            MT5_LOGIN = int(MT5_LOGIN)
        except ValueError:
            pass

# Initialize credentials
refresh_mt5_credentials()

# --- MULTI-TIMEFRAME & FUNDAMENTAL SETTINGS ---
MTF_ANALYSIS_ENABLED = _getenv_bool("MTF_ANALYSIS_ENABLED", True)
HIGHER_TIMEFRAMES = {
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4
}
HIGHER_TIMEFRAMES_CRYPTO = {
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4
}
HIGHER_TIMEFRAMES_H1_ACTIVE = {
    "H4": mt5.TIMEFRAME_H4,
}
HIGHER_TIMEFRAMES_M30_ACTIVE = {
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
}

def get_higher_timeframes(symbol):
    """Returns the MTF context timeframes for a symbol based on current active session timeframe."""
    if is_crypto(symbol):
        return HIGHER_TIMEFRAMES_CRYPTO
    tf_str = get_timeframe_str(symbol)
    if tf_str == "H1":
        return HIGHER_TIMEFRAMES_H1_ACTIVE
    return HIGHER_TIMEFRAMES_M30_ACTIVE

FUNDAMENTAL_ANALYSIS_ENABLED = _getenv_bool("FUNDAMENTAL_ANALYSIS_ENABLED", False)
PRIMARY_ANALYSIS_MODEL = os.getenv("PRIMARY_ANALYSIS_MODEL", "o4-mini")

# --- LOGGING SETTINGS ---
LOG_FILE = os.path.join(DATA_DIR, "trading_bot.log")


# ============================================================================
#  SYMBOL ROTATION HELPERS (weekday XAUUSD, weekend BTCUSD)
# ============================================================================
def is_gold(symbol):
    """True if the given symbol is Gold (XAUUSD)."""
    s = (symbol or "").upper()
    return "XAU" in s or "GOLD" in s

def is_crypto(symbol):
    """True if the given symbol is a crypto pair (weekend trading)."""
    return symbol in CRYPTO_SYMBOLS or "BTC" in (symbol or "").upper()

def is_forex(symbol):
    """True if the given symbol is a Forex currency pair (non-gold, non-crypto)."""
    return not is_gold(symbol) and not is_crypto(symbol)


def sltp_mode_for(symbol):
    """
    SL/TP mode per kategori aset (13 Agustus - pisah logic per simbol biar enak debug):
    - XAU: "LLM" (13 Agustus sore - pindah dari ATR-Based fix). Alasan: gate ATR
      (SL >= 1.25x ATR M15 ~1024 pts) bikin SL lebar yang TIDAK MUAT di min lot 0.01
      dengan risk 0.5% (over-risk 3.2x). Mode LLM + risk 1.0% = sweet spot SL ~539-1079
      pts di min lot. Tetap ada gate tolak kalau SL > max budget (risk > 1.25% dengan
      min lot) di consensus/main. Max lot cap (0.01) dihapus 14 Agustus - lot murni
      risk-based, volume_max broker yang membatasi.
    - BTC: fix "ATR-Based" (SELALU) - gate ATR R:R 2:1, anti-scalping.
    - FX pairs: "LLM" (bebas struktur, safety floor dinamis max(2x spread, 1.5x ATR H1)
      via LLM_FX_FLOOR_ATR_MULT, fallback 250 pts / 25 pips kalau ATR gagal; R:R min 1.25:1).
      Kalau config.TP_SL_RULES di-set eksplisit "ATR-Based" via CLI/.env, FX ikut ATR-Based.
    """
    s = (symbol or "").upper()
    if "XAU" in s or "GOLD" in s:
        return "LLM"  # 13 Agustus: XAU ikut LLM mode (bukan ATR-Based lagi)
    if is_crypto(symbol):
        return "ATR-Based"  # BTC fix, tidak bisa di-override ke LLM
    # FX pairs: default LLM, bisa di-force ATR-Based via config.TP_SL_RULES
    if TP_SL_RULES == "ATR-Based":
        return "ATR-Based"
    return "LLM"


def get_scanner_symbols():
    """Returns the curated universe of 22 symbols for 2-Stage Quant Screener."""
    return [s for s in SCANNER_SYMBOLS]


def get_rotation_pool(now=None):
    """
    Returns the ordered list of symbols currently in the rotation pool:
    - TRADING_MODE == "scanner" (2-Stage Quant Funnel): SCANNER_SYMBOLS (22 pairs)
    - TRADING_MODE == "xau" (default): [WEEKDAY_SYMBOL] (weekend -> WEEKEND if ENABLE_BTC_ROTATION)
    - TRADING_MODE == "xau_pairs" / "pairs": [WEEKDAY_SYMBOL] + FX_PAIR_SYMBOLS, truncated to MAX_ROTATION_SYMBOLS.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    WIB = ZoneInfo("Asia/Jakarta")
    now = now or datetime.now(WIB)
    is_weekend = (now.weekday() == 4 and now.hour >= 22) or now.weekday() in (5, 6)
    if is_weekend:
        # FX pairs market closed on weekend -> BTC or fallback
        if getattr(sys.modules[__name__], "ENABLE_BTC_ROTATION", False):
            return [WEEKEND_SYMBOL]
        return [WEEKDAY_SYMBOL]
    if TRADING_MODE == "scanner" or SCANNER_MODE:
        return [s for s in SCANNER_SYMBOLS]
    if TRADING_MODE in ("xau_pairs", "pairs", "fx_pairs"):
        pool = [WEEKDAY_SYMBOL] + [s for s in FX_PAIR_SYMBOLS if s != WEEKDAY_SYMBOL]
        return pool[:MAX_ROTATION_SYMBOLS]
    return [WEEKDAY_SYMBOL]


_rotation_index = {"i": 0}


def get_active_symbol(now=None):
    """Returns the symbol that should be traded right now (respects rotation index)."""
    pool = get_rotation_pool(now)
    return pool[_rotation_index["i"] % len(pool)]


_last_symbol = {"value": SYMBOL}


def refresh_active_symbol(now=None, advance=False):
    """
    Updates config.SYMBOL to the symbol that should be active now.
    Returns (new_symbol, changed: bool) - changed=True when the symbol just rotated.
    advance=True -> move rotation index forward (called once per new candle).
    """
    global SYMBOL
    if advance:
        pool = get_rotation_pool(now)
        _rotation_index["i"] = (_rotation_index["i"] + 1) % len(pool)
    target = get_active_symbol(now)
    # Auto-correct suffix ke nama broker valid (XAUUSD-ECN -> XAUUSD-ECNc di LIVE).
    # Lazy import untuk hindari circular (mt5_connector import config).
    try:
        from src.core.mt5_connector import get_valid_trade_symbol
        target = get_valid_trade_symbol(target)
    except Exception:
        pass
    changed = (target != _last_symbol["value"])
    SYMBOL = target
    _last_symbol["value"] = target
    return target, changed


def lot_size_for(symbol):
    return LOT_SIZE_BTC if is_crypto(symbol) else LOT_SIZE_XAU


def get_timeframe_str(symbol=None, now_wib=None):
    """Returns the active trading timeframe string ('H1' or 'M30') taking into account
    Dynamic Session Timeframe (H1 in Tokyo 08:00-14:00, M30 in London/NY 14:00-00:00).
    """
    if symbol and is_crypto(symbol):
        return "M30"
    if DYNAMIC_SESSION_TIMEFRAME:
        if now_wib is None:
            now_wib = datetime.now(ZoneInfo("Asia/Jakarta"))
        wib_hour = now_wib.hour
        # Sesi Tokyo / Asia: 08:00 - 14:00 WIB
        if 8 <= wib_hour < DYNAMIC_TF_SWITCH_HOUR_WIB:
            return ASIA_TIMEFRAME
        else:
            return LONDON_NY_TIMEFRAME
    return TIMEFRAME_STR


def get_timeframe(symbol=None, now_wib=None):
    """Returns the MT5 timeframe integer corresponding to the current active session."""
    tf_str = get_timeframe_str(symbol, now_wib)
    return TIMEFRAME_MAP.get(tf_str, TIMEFRAME)


def risk_percent_for(symbol):
    """Returns the risk per trade percentage for a symbol.
    BTC: RISK_PERCENT_BTC (1.5%)
    XAU: RISK_PERCENT_XAU (1.0%)
    FX: RISK_PERCENT_FX (1.0%)
    """
    if is_crypto(symbol):
        return RISK_PERCENT_BTC
    if is_gold(symbol):
        return RISK_PERCENT_XAU
    return RISK_PERCENT_FX


def default_sl_points_for(symbol):
    if is_crypto(symbol): return DEFAULT_SL_POINTS_BTC
    if "XAU" not in symbol.upper(): return 100
    return DEFAULT_SL_POINTS_XAU


def default_tp_points_for(symbol):
    if is_crypto(symbol): return DEFAULT_TP_POINTS_BTC
    if "XAU" not in symbol.upper(): return 200
    return DEFAULT_TP_POINTS_XAU


def max_spread_points_for(symbol, atr_h1_pts=None):
    """Return max spread in points for a symbol.
    - Crypto : flat BTC cap (2400 pts)
    - XAU    : flat XAU cap (50 pts)
    - FX     : max(15% × ATR_H1_pts, floor 20 pts).
                Fallback ke flat MAX_SPREAD_POINTS jika atr_h1_pts tidak tersedia.
    """
    if is_crypto(symbol):
        return MAX_SPREAD_POINTS_BTC
    if is_gold(symbol):
        return MAX_SPREAD_POINTS_XAU
    # FX: ATR-based dengan floor
    if atr_h1_pts and atr_h1_pts > 0:
        return max(int(atr_h1_pts * SPREAD_ATR_RATIO), SPREAD_ATR_FLOOR_PTS)
    return MAX_SPREAD_POINTS  # fallback flat jika ATR tidak tersedia


def sl_padding_for(symbol):
    """Returns extra anti-wick/spread buffer in points for specific pairs (e.g. +20 pts for NZD crosses)."""
    if "NZD" in (symbol or "").upper():
        return globals().get("SL_PADDING_NZD_POINTS", 20)
    return 0


def confidence_threshold_for(symbol):
    """Weighted-confidence consensus threshold per symbol.
    BTC (M30, moderate entries) needs higher conviction than XAU (M15, frequent).
    """
    return CONFIDENCE_CONSENSUS_THRESHOLD_BTC if is_crypto(symbol) else CONFIDENCE_CONSENSUS_THRESHOLD_XAU


def get_ai_mode(now=None):
    """Return active AI mode for WIB time.
    - schedule policy: use AI_MODE_SCHEDULE
    - fixed policy: use AI_FIXED_MODE
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    WIB = ZoneInfo("Asia/Jakarta")
    now = now or datetime.now(WIB)

    policy = getattr(sys.modules[__name__], "AI_MODE_POLICY", "schedule")
    if policy == "fixed":
        fixed = getattr(sys.modules[__name__], "AI_FIXED_MODE", "triple")
        return fixed if fixed in ("single", "single_gemini", "dual", "triple") else "triple"

    total_minutes = now.hour * 60 + now.minute
    for sh, sm, eh, em, mode in AI_MODE_SCHEDULE:
        start = sh * 60 + sm
        end = eh * 60 + em
        if start <= total_minutes <= end:
            return mode
    return "single"


def atr_sl_multiplier(now=None):
    """SL floor multiplier per AI mode (R:R 2:1 dijaga):
    single / single_gemini 1.25x, dual 1.5x, triple 1.75x - makin banyak model setuju,
    makin yakin setupnya, SL/TP makin lebar (target lebih jauh).
    Dipakai di consensus gate ATR + prompt atr_gate_str - harus sinkron.
    """
    mode = get_ai_mode(now)
    if mode in ("single", "single_gemini"):
        return 1.25
    if mode == "dual":
        return 1.5
    return 1.75


def atr_tp_multiplier(now=None):
    """TP floor multiplier per AI mode = 2x SL multiplier (R:R 2:1 selalu):
    single / single_gemini 2.5x, dual 3.0x, triple 3.5x.
    """
    mode = get_ai_mode(now)
    if mode in ("single", "single_gemini"):
        return 2.5
    if mode == "dual":
        return 3.0
    return 3.5


def claude_slot_label():
    """Display label for Claude slot model."""
    return "Claude"


def active_ai_model_names(now=None):
    """Return the model slots to query for the active AI mode.
    - single: OpenAI (o4-mini)
    - single_gemini: Gemini (gemini-3.1-flash-lite)
    - dual: OpenAI (o4-mini) + Gemini (gemini-3.1-flash-lite)
    - triple: OpenAI (o4-mini) + Gemini (gemini-3.1-flash-lite) + DeepSeek (deepseek-v4-flash)
    """
    mode = get_ai_mode(now)
    if mode == "single_gemini":
        return ["Gemini"]
    if mode == "single":
        return ["OpenAI"]
    if mode == "dual":
        second = AI_DUAL_SECOND_MODEL.strip().lower()
        if second in ("gemini", "gem"):
            return ["OpenAI", "Gemini"]
        return ["OpenAI", "DeepSeek"]
    return ["OpenAI", "Gemini", "DeepSeek"]


def risk_percent_for(symbol):
    """Risk per trade (% of balance) for risk-based lot sizing.
    BTC (M30 swing, few concurrent positions): 1.5%.
    FX (H1): 1.25% (18 Agustus malam - diturunkan dari 1.5%: lot 0.18-0.22
    terlalu besar utk pair sepi & SL ATR H1; 1.25% = kompromi antara lot lebih
    besar vs risiko harian terkontrol).
    XAU (M30 swing, up to 6 concurrent): 1.0% (13 Agustus - dinaikkan dari 0.5%
    karena min lot 0.01 broker tidak bisa mewakili risk 0.5% dengan SL ATR/struktur
    yang lebar; 1.0% = max SL ~1079 pts di equity ~$1079, muat sweet spot).
    """
    if is_crypto(symbol): return RISK_PERCENT_BTC
    if "XAU" not in symbol.upper(): return RISK_PERCENT_FX
    return RISK_PERCENT_XAU


def is_fx(symbol):
    """True if the given symbol is a Forex currency pair."""
    upper = symbol.upper()
    return not is_crypto(symbol) and "XAU" not in upper


def break_even_trigger_for(symbol):
    """Returns break-even trigger point threshold per symbol."""
    if is_crypto(symbol):
        return BREAK_EVEN_TRIGGER_POINTS_BTC
    if is_fx(symbol):
        # FX H1: trigger BEP pada 100 pts (10 pips) - 50% dari default TP 200 pts
        return 100
    return BREAK_EVEN_TRIGGER_POINTS_XAU  # XAU (M15): 300 pts


def break_even_padding_for(symbol):
    """Returns break-even padding points per symbol."""
    if is_crypto(symbol):
        return BREAK_EVEN_PADDING_POINTS_BTC
    if is_fx(symbol):
        return 10  # 1 pip padding
    return BREAK_EVEN_PADDING_POINTS_XAU


def partial_close_tp1_for(symbol):
    """Returns TP1 partial close threshold points per symbol."""
    if is_crypto(symbol):
        return PARTIAL_CLOSE_TP1_POINTS_BTC
    if is_fx(symbol):
        # FX H1: partial close pada 120 pts (12 pips)
        return 120
    return PARTIAL_CLOSE_TP1_POINTS_XAU  # XAU (M15): 400 pts


def trailing_activation_params_for(symbol):
    """Returns (act_mult, dist_mult, fallback_act, fallback_dist, act_cap) per symbol."""
    if is_crypto(symbol):
        return (
            getattr(sys.modules[__name__], "TRAILING_ACTIVATION_ATR_MULT_BTC", 1.0),
            getattr(sys.modules[__name__], "TRAILING_DISTANCE_ATR_MULT_BTC", 0.5),
            getattr(sys.modules[__name__], "TRAILING_ACTIVATION_POINTS_BTC", 17000),
            getattr(sys.modules[__name__], "TRAILING_DISTANCE_POINTS_BTC", 12500),
            getattr(sys.modules[__name__], "TRAILING_ACTIVATION_MAX_POINTS_BTC", 40000)
        )
    elif is_fx(symbol):
        # FX H1: 1.0x ATR activation, 0.5x ATR distance, fallback 100/50 pts, cap 250 pts
        return (1.0, 0.5, 100, 50, 250)
    else:
        # XAU (M15)
        return (
            getattr(sys.modules[__name__], "TRAILING_ACTIVATION_ATR_MULT_XAU", 1.2),
            getattr(sys.modules[__name__], "TRAILING_DISTANCE_ATR_MULT_XAU", 0.6),
            getattr(sys.modules[__name__], "TRAILING_ACTIVATION_POINTS_XAU", 200),
            getattr(sys.modules[__name__], "TRAILING_DISTANCE_POINTS_XAU", 150),
            getattr(sys.modules[__name__], "TRAILING_ACTIVATION_MAX_POINTS_XAU", 600)
        )
