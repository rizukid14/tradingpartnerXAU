import os
import time
import sys
import threading
# Force UTF-8 encoding for standard output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import config
from config import mt5
from src.core import mt5_connector as connector, llm_client as llm, consensus, telegram_alerts as tg
from src.core.risk_engine import RiskEngine
from src.analytics import position_manager, trade_evaluator, dynamic_config, forecast_engine, decision_memory
from src.analytics.macro_analyst import MacroAnalyst

import shutil
import unicodedata

# --- Status line terminal (Windows) ---
_VT_OK = False


def _enable_windows_vt():
    """Aktifkan ANSI/VT processing di Windows 10+ supaya \x1b[2K (erase line) jalan."""
    global _VT_OK
    if os.name != "nt":
        _VT_OK = True  # POSIX terminal dukung ANSI native
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h, ctypes.byref(mode)):
            kernel32.SetConsoleMode(h, mode.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            _VT_OK = True
    except Exception:
        _VT_OK = False


_enable_windows_vt()


def _disp_width(s):
    """Lebar tampilan karakter di terminal: emoji/wide char = 2 kolom, sisanya 1."""
    return sum(
        2 if ord(ch) > 0xFFFF or unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in s
    )


def _truncate_disp(s, max_w):
    """Potong string agar lebar tampilan <= max_w (cegah wrap yang merusak refresh)."""
    if _disp_width(s) <= max_w:
        return s
    out, w = [], 0
    for ch in s:
        cw = 2 if ord(ch) > 0xFFFF or unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w + cw > max_w - 3:
            out.append("...")
            break
        out.append(ch)
        w += cw
    return "".join(out)


# Initialize risk engine
risk = RiskEngine()

# Initialize macro analyst
macro = MacroAnalyst()


def _tpsl_rules_arg(value):
    """Parser argparse untuk --tpsl-rules: terima 'ATR-Based'/'LLM' (case-insensitive)."""
    v = value.strip().lower()
    if v in ("atr-based", "atr", "default", "safe"):
        return "ATR-Based"
    if v in ("llm", "free", "bebas"):
        return "LLM"
    # argparse menangkap ValueError dari type function jadi pesan error
    raise ValueError("pilih 'ATR-Based' atau 'LLM'")


def parse_cli_overrides(argv=None):
    """
    Parse CLI flags untuk override config sebelum bot jalan (sesi saja, tidak disimpan).

    Contoh:
      python main.py --dry-run --risk-percent-btc 1.0 --max-daily-loss 30
      python main.py --live --weekend-trading off --threshold-btc 1.0

    Return dict {config_attr: value} yang sudah di-set ke config.
    """
    import argparse
    p = argparse.ArgumentParser(description="Trading bot MT5 - override config via CLI (sesi saja).")
    p.add_argument("--dry-run", action="store_true", help="Mode dry-run (sinyal saja, tanpa order)")
    p.add_argument("--live", action="store_true", help="Mode live (kirim order beneran)")
    p.add_argument("--risk-percent-btc", type=float, help="Risk pct equity per trade BTC (mis. 1.5)")
    p.add_argument("--risk-percent-xau", type=float, help="Risk pct equity per trade XAU (mis. 0.5)")
    p.add_argument("--max-daily-loss", type=float, help="Batas kerugian harian USD (mis. 50)")
    p.add_argument("--max-positions", type=int, help="Max posisi open (mis. 6)")
    p.add_argument("--weekend-trading", choices=["on", "off"], help="Trading di weekend on/off")
    p.add_argument("--threshold-btc", type=float, help="Confidence threshold BTC (mis. 1.2)")
    p.add_argument("--threshold-xau", type=float, help="Confidence threshold XAU (mis. 1.0)")
    p.add_argument("--spread-max-btc", type=float, help="Spread filter max BTC (pts)")
    p.add_argument("--spread-max-xau", type=float, help="Spread filter max XAU (pts)")
    p.add_argument("--cooldown", type=int, help="Cooldown antar trade (detik)")
    p.add_argument("--telegram", choices=["on", "off"], help="Telegram notifikasi on/off")
    p.add_argument("--memory", choices=["on", "off"],
                   help="Memory context (lessons/decision memory/forecast) on/off - OFF = LLM independen")
    p.add_argument("--quant", choices=["on", "off"], help="Quant analysis (Hurst/Monte Carlo) on/off")
    p.add_argument("--dynamic", choices=["on", "off"],
                   help="Dynamic self-tuning config on/off (win-rate adaptive consensus threshold)")
    p.add_argument("--claude-model", type=str,
                   help="Model slot Claude: 'deepseek/deepseek-v4-flash' (murah) atau 'claude-sonnet-4-6'")
    p.add_argument("--tpsl-rules", type=_tpsl_rules_arg, metavar="{ATR-Based,LLM}",
                   help="Aturan SL/TP: 'ATR-Based' (gate per AI mode: single 1.25x/2.5x, dual 1.5x/3.0x, triple 1.75x/3.5x ATR, R:R 2:1) atau 'LLM' (bebas sesuai model, floor 2x spread aja)")
    p.add_argument("--yes", "-y", action="store_true",
                   help="Lewati konfirmasi interaktif (langsung jalan dengan setting saat ini)")
    p.add_argument("--era", choices=list(getattr(config, "ERA_PRESETS", {}).keys()),
                   help="Pakai preset era (v1 / v2 / v3)")
    p.add_argument("--account", choices=["live", "demo"],
                   help="Pilih akun MT5: 'live' (real money) atau 'demo' (virtual)")
    args = p.parse_args(argv)

    applied = []

    if args.dry_run and args.live:
        print("[CLI] Tidak bisa --dry-run dan --live bersamaan.")
        sys.exit(1)

    # Preset era dulu (paling awal), lalu flag eksplisit menimpa
    if getattr(args, "era", None):
        preset = getattr(config, "ERA_PRESETS", {}).get(args.era)
        if preset:
            for attr, val in preset.items():
                if attr == "label":
                    continue
                if hasattr(config, attr):
                    setattr(config, attr, val)
            applied.append(f"ERA={args.era}")

    if args.dry_run:
        config.DRY_RUN = True
        applied.append("DRY_RUN=True")
    elif args.live:
        config.DRY_RUN = False
        applied.append("DRY_RUN=False")

    if args.risk_percent_btc is not None:
        config.RISK_PERCENT_BTC = args.risk_percent_btc
        applied.append(f"RISK_PERCENT_BTC={args.risk_percent_btc}")
    if args.claude_model is not None:
        v = args.claude_model.lower().strip()
        if v in ("deepseek", "flash", "v4-flash", "deepseek-flash", "1"):
            config.CLAUDE_MODEL = "deepseek/deepseek-v4-flash"
        elif v in ("claude", "sonnet", "2"):
            config.CLAUDE_MODEL = "claude-sonnet-4-6"
        elif v in ("haiku", "3"):
            config.CLAUDE_MODEL = "claude-haiku-4-5-20251001"
        else:
            config.CLAUDE_MODEL = args.claude_model
        applied.append(f"CLAUDE_MODEL={config.CLAUDE_MODEL}")
    if args.tpsl_rules is not None:
        config.TP_SL_RULES = args.tpsl_rules
        applied.append(f"TP_SL_RULES={config.TP_SL_RULES}")
    if args.risk_percent_xau is not None:
        config.RISK_PERCENT_XAU = args.risk_percent_xau
        applied.append(f"RISK_PERCENT_XAU={args.risk_percent_xau}")
    if args.max_daily_loss is not None:
        config.MAX_DAILY_LOSS_USD = args.max_daily_loss
        applied.append(f"MAX_DAILY_LOSS_USD={args.max_daily_loss}")
    if args.max_positions is not None:
        config.MAX_OPEN_POSITIONS = args.max_positions
        applied.append(f"MAX_OPEN_POSITIONS={args.max_positions}")
    if args.weekend_trading:
        config.WEEKEND_TRADING_ENABLED = (args.weekend_trading == "on")
        applied.append(f"WEEKEND_TRADING_ENABLED={config.WEEKEND_TRADING_ENABLED}")
    if args.threshold_btc is not None:
        config.CONFIDENCE_CONSENSUS_THRESHOLD_BTC = args.threshold_btc
        applied.append(f"CONFIDENCE_CONSENSUS_THRESHOLD_BTC={args.threshold_btc}")
    if args.threshold_xau is not None:
        config.CONFIDENCE_CONSENSUS_THRESHOLD_XAU = args.threshold_xau
        applied.append(f"CONFIDENCE_CONSENSUS_THRESHOLD_XAU={args.threshold_xau}")
    if args.spread_max_btc is not None:
        config.MAX_SPREAD_POINTS_BTC = args.spread_max_btc
        applied.append(f"MAX_SPREAD_POINTS_BTC={args.spread_max_btc}")
    if args.spread_max_xau is not None:
        config.MAX_SPREAD_POINTS_XAU = args.spread_max_xau
        applied.append(f"MAX_SPREAD_POINTS_XAU={args.spread_max_xau}")
    if args.cooldown is not None:
        config.TRADE_COOLDOWN_SECONDS = args.cooldown
        applied.append(f"TRADE_COOLDOWN_SECONDS={args.cooldown}")
    if args.telegram:
        config.TELEGRAM_ENABLED = (args.telegram == "on")
        applied.append(f"TELEGRAM_ENABLED={config.TELEGRAM_ENABLED}")
    if getattr(args, "memory", None):
        config.MEMORY_CONTEXT_ENABLED = (args.memory == "on")
        applied.append(f"MEMORY_CONTEXT_ENABLED={config.MEMORY_CONTEXT_ENABLED}")
    if getattr(args, "quant", None):
        config.QUANT_ANALYSIS_ENABLED = (args.quant == "on")
        applied.append(f"QUANT_ANALYSIS_ENABLED={config.QUANT_ANALYSIS_ENABLED}")
    if getattr(args, "dynamic", None):
        config.DYNAMIC_CONFIG_ENABLED = (args.dynamic == "on")
        applied.append(f"DYNAMIC_CONFIG_ENABLED={config.DYNAMIC_CONFIG_ENABLED}")
    if getattr(args, "account", None):
        config.MT5_ACCOUNT_MODE = args.account
        config.refresh_mt5_credentials()
        applied.append(f"MT5_ACCOUNT_MODE={config.MT5_ACCOUNT_MODE}")

    return applied, getattr(args, "yes", False)


def interactive_setup():
    """
    Tampilkan setting aktif + izinkan user mengubah sebelum bot jalan.
    Dipanggil di main() sebelum koneksi MT5. User bisa:
      - ketik nomor untuk mengubah setting
      - 'start' / enter kosong untuk mulai
      - 'q' untuk batal
    """
    print()
    print("=" * 60)
    print("   SETTING BOT SEBELUM JALAN (sesi ini saja)")
    print("=" * 60)

    def _account_label():
        mode = config.MT5_ACCOUNT_MODE.upper()
        login = config.MT5_LOGIN or "?"
        server = config.MT5_SERVER or "?"
        return f"{mode} ({login} @ {server})"

    def _fmt_val(attr, v):
        if attr == "config.DRY_RUN":
            return "LIVE (kirim order)" if v else "DRY RUN (sinyal saja)"
        if attr == "config.TRADING_MODE":
            return _scan_mode_label() if v == "xau_pairs" else "XAU Only"
        if v is True:
            return "ON"
        if v is False:
            return "OFF"
        s = str(v)
        if attr == "config.TP_SL_RULES":
            s += (" (gate ATR per mode: 1.25/2.5, 1.5/3.0, 1.75/3.5)" if v == "ATR-Based" else " (bebas, 2x spread)" if v == "LLM" else "")
        return s


    def _scan_mode_label():
        """Label dinamis scan pool - ikut get_rotation_pool() biar jumlah
        simbol selalu akurat (3 simbol: XAU+EURJPY+GBPCHF; weekend: FX tutup
        -> pool jatuh ke XAU/BTC saja)."""
        try:
            pool = config.get_rotation_pool()
            if len(pool) <= 1:
                base = f"XAU + Pairs -> {pool[0]} (weekend/FX tutup)" if pool else "XAU Only"
                return base
            return f"XAU + Pairs ({len(pool)} simbol)"
        except Exception:
            return "XAU + Pairs"


    # (grup, label, attr, val) - dikelompokkan biar enak dibaca
    settings = [
        ("MODE & RISK", "Akun MT5", "config.MT5_ACCOUNT_MODE", _account_label()),
        ("MODE & RISK", "Mode", "config.DRY_RUN", "DRY RUN (sinyal saja)" if config.DRY_RUN else "LIVE (kirim order)"),
        ("MODE & RISK", "Scan Mode", "config.TRADING_MODE", _scan_mode_label() if config.TRADING_MODE == "xau_pairs" else "XAU Only"),
        ("MODE & RISK", "Risk BTC (% equity)", "config.RISK_PERCENT_BTC", str(config.RISK_PERCENT_BTC)),
        ("MODE & RISK", "Risk XAU (% equity)", "config.RISK_PERCENT_XAU", str(config.RISK_PERCENT_XAU)),
        ("LIMIT & FILTER", "Max Daily Loss ($)", "config.MAX_DAILY_LOSS_USD", str(config.MAX_DAILY_LOSS_USD)),
        ("LIMIT & FILTER", "Max Posisi", "config.MAX_OPEN_POSITIONS", str(config.MAX_OPEN_POSITIONS)),
        ("LIMIT & FILTER", "Cooldown (detik)", "config.TRADE_COOLDOWN_SECONDS", str(config.TRADE_COOLDOWN_SECONDS)),
        ("LIMIT & FILTER", "Spread Max BTC (pts)", "config.MAX_SPREAD_POINTS_BTC", str(config.MAX_SPREAD_POINTS_BTC)),
        ("LIMIT & FILTER", "Spread Max XAU (pts)", "config.MAX_SPREAD_POINTS_XAU", str(config.MAX_SPREAD_POINTS_XAU)),
        ("KONSENSUS & AI", "Threshold BTC", "config.CONFIDENCE_CONSENSUS_THRESHOLD_BTC", str(config.CONFIDENCE_CONSENSUS_THRESHOLD_BTC)),
        ("KONSENSUS & AI", "Threshold XAU", "config.CONFIDENCE_CONSENSUS_THRESHOLD_XAU", str(config.CONFIDENCE_CONSENSUS_THRESHOLD_XAU)),
        ("KONSENSUS & AI", "Model Claude Slot", "config.CLAUDE_MODEL", str(config.CLAUDE_MODEL)),
        ("KONSENSUS & AI", "TP/SL Rules", "config.TP_SL_RULES",
         str(config.TP_SL_RULES) + (" (gate ATR per mode: 1.25/2.5, 1.5/3.0, 1.75/3.5)" if config.TP_SL_RULES == "ATR-Based" else " (bebas, 2x spread)")),
        ("KONSENSUS & AI", "Quant (Hurst/MC)", "config.QUANT_ANALYSIS_ENABLED", "ON" if config.QUANT_ANALYSIS_ENABLED else "OFF"),
        ("KONSENSUS & AI", "Dynamic Config", "config.DYNAMIC_CONFIG_ENABLED", "ON" if config.DYNAMIC_CONFIG_ENABLED else "OFF"),
        ("KONSENSUS & AI", "Forecast Engine", "config.FORECAST_ENABLED", "ON" if config.FORECAST_ENABLED else "OFF"),
        ("KONSENSUS & AI", "AI Mode Policy", "config.AI_MODE_POLICY", str(config.AI_MODE_POLICY)),
        ("KONSENSUS & AI", "Memory (lessons/dec)", "config.MEMORY_CONTEXT_ENABLED", "ON" if config.MEMORY_CONTEXT_ENABLED else "OFF"),
        ("PROTEKSI", "Trailing Stop", "config.TRAILING_STOP_ENABLED", "ON" if config.TRAILING_STOP_ENABLED else "OFF"),
        ("PROTEKSI", "Break-Even", "config.BREAK_EVEN_ENABLED", "ON" if config.BREAK_EVEN_ENABLED else "OFF"),
        ("PROTEKSI", "Partial Close", "config.PARTIAL_CLOSE_ENABLED", "ON" if config.PARTIAL_CLOSE_ENABLED else "OFF"),
        ("PROTEKSI", "Recovery Mode", "config.RECOVERY_MODE_ENABLED", "ON" if config.RECOVERY_MODE_ENABLED else "OFF"),
        ("PROTEKSI", "Max Consec. Loss", "config.MAX_CONSECUTIVE_LOSSES", str(config.MAX_CONSECUTIVE_LOSSES)),
        ("PROTEKSI", "Pause Setelah Loss (mnt)", "config.PAUSE_AFTER_LOSSES_MINUTES", str(config.PAUSE_AFTER_LOSSES_MINUTES)),
        ("PROTEKSI", "Recovery Lot Mult", "config.RECOVERY_LOT_MULTIPLIER", str(config.RECOVERY_LOT_MULTIPLIER)),
        ("PROTEKSI", "Session Filter", "config.SESSION_FILTER_ENABLED", "ON" if config.SESSION_FILTER_ENABLED else "OFF"),
        ("PROTEKSI", "Weekend Close", "config.WEEKEND_CLOSE_ENABLED", "ON" if config.WEEKEND_CLOSE_ENABLED else "OFF"),
        ("PROTEKSI", "Weekend Trading", "config.WEEKEND_TRADING_ENABLED", "ON" if config.WEEKEND_TRADING_ENABLED else "OFF"),
        ("ANALISIS & NOTIF", "MTF Analysis", "config.MTF_ANALYSIS_ENABLED", "ON" if config.MTF_ANALYSIS_ENABLED else "OFF"),
        ("ANALISIS & NOTIF", "Fundamental", "config.FUNDAMENTAL_ANALYSIS_ENABLED", "ON" if config.FUNDAMENTAL_ANALYSIS_ENABLED else "OFF"),
        ("ANALISIS & NOTIF", "Telegram", "config.TELEGRAM_ENABLED", "ON" if config.TELEGRAM_ENABLED else "OFF"),
    ]

    # Daftar preset era (dari config.ERA_PRESETS)
    presets = getattr(config, "ERA_PRESETS", {})

    while True:
        try:
            print("-" * 60)
            last_group = None
            for i, (group, label, attr, val) in enumerate(settings, 1):
                if group != last_group:
                    print(f" -- {group} --")
                    last_group = group
                print(f" {i:2d}. {label:<26} : {val}")
            if presets:
                print("-" * 60)
                print(" PRESET ERA:")
                for name, p in presets.items():
                    print(f"    [{name}] {p.get('label', name)}")
            print("-" * 60)
            print(" Ketik nomor utk ubah | [nama-preset] utk pakai preset | 'start'/Enter = mulai | 'q' = batal")
            choice = input("  > ").strip().lower()
        except EOFError:
            print("[NON-INTERACTIVE] Terminal non-interaktif terdeteksi (Docker/Daemon). Memulai bot dengan setting default...")
            break
        except KeyboardInterrupt:
            print("\n Dibatalkan. Bot tidak dijalankan.")
            sys.exit(0)



        if choice in ("q", "quit", "exit"):
            print("Dibatalkan. Bot tidak dijalankan.")
            sys.exit(0)
        if choice in ("", "start", "s", "y"):
            break

        # Preset era
        if presets and choice in presets:
            preset = presets[choice]
            print(f"   Menerapkan preset '{choice}' ({preset.get('label', '')})...")
            for attr, val in preset.items():
                if attr == "label":
                    continue
                if hasattr(config, attr):
                    setattr(config, attr, val)
            # refresh tampilan
            for i, (group, label, attr, _) in enumerate(settings):
                v = getattr(config, attr.split(".")[1], None)
                settings[i] = (group, label, attr, _fmt_val(attr, v))
            print("  Preset diterapkan.")
            continue

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(settings):
                group, label, attr, _ = settings[idx]
                new_val = input(f"  {label} baru (kosong = batal): ").strip()
                if not new_val:
                    continue
                try:
                    if "MT5_ACCOUNT_MODE" in attr:
                        v = new_val.strip().lower()
                        if v not in ("live", "demo"):
                            print("  Pilih 'live' atau 'demo'.")
                            continue
                        config.MT5_ACCOUNT_MODE = v
                        config.refresh_mt5_credentials()
                        settings[idx] = (group, label, attr, _account_label())
                        print(f"  Akun MT5 diubah ke {v.upper()} (login: {config.MT5_LOGIN} @ {config.MT5_SERVER}).")
                        continue
                    elif "DRY_RUN" in attr:
                        config.DRY_RUN = new_val.lower() in ("1", "true", "yes", "live", "on")
                    elif "ENABLED" in attr:
                        setattr(config, attr.split(".")[1], new_val.lower() in ("1", "true", "yes", "on"))
                    elif "THRESHOLD" in attr or "RISK" in attr or "LOSS" in attr or "SPREAD" in attr:
                        setattr(config, attr.split(".")[1], float(new_val))
                    elif "MODEL" in attr:
                        v = new_val.lower().strip()
                        if v in ("deepseek", "flash", "v4-flash", "deepseek-flash", "1"):
                            new_val = "deepseek/deepseek-v4-flash"
                        elif v in ("claude", "sonnet", "2"):
                            new_val = "claude-sonnet-4-6"
                        elif v in ("haiku", "3"):
                            new_val = "claude-haiku-4-5-20251001"
                        setattr(config, attr.split(".")[1], new_val)
                    elif "RULES" in attr:
                        v = new_val.strip().lower()
                        if v in ("1", "atr", "atr-based", "default", "safe"):
                            new_val = "ATR-Based"
                        elif v in ("2", "llm", "free", "bebas"):
                            new_val = "LLM"
                        else:
                            print("  Pilih 'ATR-Based' (1) atau 'LLM' (2).")
                            continue
                        setattr(config, attr.split(".")[1], new_val)
                    elif "TRADING_MODE" in attr:
                        v = new_val.strip().lower()
                        if v in ("1", "xau", "only", "xau-only", "gold"):
                            new_val = "xau"
                        elif v in ("2", "pairs", "xau_pairs", "xau-pairs", "all"):
                            new_val = "xau_pairs"
                        else:
                            print("  Pilih 'xau' (1) atau 'xau_pairs' (2).")
                            continue
                        setattr(config, attr.split(".")[1], new_val)
                    elif "AI_MODE_POLICY" in attr:
                        v = new_val.strip().lower()
                        if v in ("schedule", "jadwal", "auto", "1"):
                            new_val = "schedule"
                        elif v in ("fixed", "paksa", "manual", "2"):
                            new_val = "fixed"
                        else:
                            print("  Pilih 'schedule' (1) atau 'fixed' (2).")
                            continue
                        setattr(config, attr.split(".")[1], new_val)
                    else:
                        setattr(config, attr.split(".")[1], int(new_val))
                    # refresh tampilan
                    v = getattr(config, attr.split('.')[1], None)
                    settings[idx] = (group, label, attr, _fmt_val(attr, v))
                    print(f"  {label} diubah.")
                except ValueError:
                    print("  Nilai tidak valid.")
                continue
            print("  Nomor tidak valid.")
        else:
            print("  Pilihan tidak dikenali.")



class TeeLogger(object):
    """Redirects stdout and stderr to both the console and a log file with auto-size rotation."""
    def __init__(self, filepath, max_bytes=2000000):
        self.terminal = sys.stdout
        self.filepath = filepath
        # Rotate log if size exceeds max_bytes (keep last 5000 lines)
        if os.path.exists(filepath) and os.path.getsize(filepath) > max_bytes:
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                keep_lines = lines[-5000:]
                with open(filepath, "w", encoding="utf-8") as f:
                    f.writelines(keep_lines)
            except Exception:
                pass
        self.log = open(filepath, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        # Skip carriage return live clock lines from spamming log file
        if "\r" not in message:
            # Filter verbose noise patterns to save space and focus the logs
            skip_patterns = (
                "Menyertakan analisa Multi-Timeframe",
                "Menyertakan Lesson Learned",
                "Mengirim data ke OpenAI",
                "[LATENSI MODEL",
                "ANALISIS KONSENSUS MULTI-LLM",
                "==================================================",
                "--------------------------------------------------"
            )
            if any(p in message for p in skip_patterns):
                return
            self.log.write(message)
            self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()


_symbol_last_candle = {}
_symbol_last_candle_seeded = False
_STARTUP_SCAN_MODE = "timeframe"  # FASE 6: "all" (scan semua sekarang) | "timeframe" (default, tunggu candle close)


def _resolve_valid_pool():
    """FASE 6 - Resolve base names -> nama broker valid (auto-correct suffix, mis. XAUUSD-ECN -> XAUUSD-ECNc)
    + symbol_select biar tick/rates tersedia untuk semua pair di pool (FX pair baru sering belum visible).
    """
    pool = config.get_rotation_pool()
    valid_pool = []
    for sym in pool:
        vsym = connector.get_valid_trade_symbol(sym)
        if vsym != sym:
            print(f"[MT5 AUTO-CORRECT] Pool '{sym}' -> '{vsym}' (broker live)")
        mt5.symbol_select(vsym, True)
        valid_pool.append(vsym)
    return valid_pool


def _seed_startup_scan(valid_pool):
    """FASE 6 - startup scan mode:
    - "all": biarkan _symbol_last_candle kosong -> semua simbol langsung di-scan di cycle pertama.
    - "timeframe" (default): seed open-time candle terakhir yang SUDAH CLOSE -> tiap simbol
      baru di-scan pas candle close BERIKUTNYA (sesuai timeframe masing-masing).
    """
    global _symbol_last_candle, _symbol_last_candle_seeded
    if _symbol_last_candle_seeded:
        return
    _symbol_last_candle_seeded = True
    if _STARTUP_SCAN_MODE != "timeframe":
        return
    for sym in valid_pool:
        if sym in _symbol_last_candle:
            continue
        tf = config.get_timeframe(sym)
        r = mt5.copy_rates_from_pos(sym, tf, 0, 2)
        if r is not None and len(r) >= 2:
            _symbol_last_candle[sym] = int(r[-2]['time'])


def _prompt_startup_scan_mode():
    """FASE 6 - CLI prompt mode scan startup:
    [1] Scan semua simbol sekarang (scan all now)
    [2] Scan sesuai timeframe masing-masing (default) - tunggu candle close tiap aset
    Non-interactive / timeout 10 detik -> default "timeframe".
    """
    global _STARTUP_SCAN_MODE
    if not sys.stdin.isatty():
        return  # non-interactive (scheduler/redirect) -> default
    try:
        import msvcrt
    except ImportError:
        return
    print("\n" + "=" * 58)
    print(" STARTUP SCAN MODE")
    print(" [1] Scan semua simbol sekarang (scan all now)")
    print(" [2] Scan sesuai timeframe masing-masing (default)")
    print("=" * 58)
    sys.stdout.write("  Pilihan [2] (10 detik, Enter = default): ")
    sys.stdout.flush()
    buf = ""
    deadline = time.time() + 10
    while time.time() < deadline:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                break
            if ch == "\x03":  # Ctrl+C
                raise KeyboardInterrupt
            if ch == "\b":
                buf = buf[:-1]
                sys.stdout.write("\b \b")
                sys.stdout.flush()
            elif ch.isdigit():
                buf += ch
                sys.stdout.write(ch)
                sys.stdout.flush()
    sys.stdout.write("\n")
    sys.stdout.flush()
    _STARTUP_SCAN_MODE = "all" if buf.strip() == "1" else "timeframe"
    mode_txt = "SCAN ALL NOW (semua simbol langsung)" if _STARTUP_SCAN_MODE == "all" else "SESUAI TIMEFRAME (tunggu candle close tiap aset)"
    print(f" -> Scan mode: {mode_txt}\n")


def run_trading_cycle():
    """Performs one full cycle: post-mortem (1x, aggregate all symbols) + full cycle
    per symbol in the rotation pool. Mode "xau": pool=[XAU]. Mode "xau_pairs": pool
    = [XAU, EURJPY, GBPCHF] - all symbols scanned ONLY when their specific timeframe
    forms a new candle (e.g., XAU every 5 mins, FX Pairs every 1 hour).
    """
    print(f"\n [CYCLE START] Memulai analisa market pada {time.strftime('%Y-%m-%d %H:%M:%S')}...")
    
    # 2.5 Post-Mortem Trade Evaluation & Daily WinRate Summary (Run before any early exits)
    try:
        trade_evaluator.evaluator.check_and_evaluate_closed_trades()
        closed_deals = connector.get_closed_positions_today()
        if getattr(config, "DYNAMIC_CONFIG_ENABLED", False):
            dynamic_config.dynamic_rules.adapt_from_performance(closed_deals)

        # Display Daily WinRate Summary Log (aggregate + per-symbol breakdown)
        if closed_deals and len(closed_deals) > 0:
            # Break-even trades excluded from win-rate. Tolerance DINAMIS per trade:
            # minimal BREAK_EVEN_TOLERANCE_USD, tapi naik mengikuti komisi aktual
            # trade (0.01 lot = 0.06, 0.10 lot = 0.60, 0.26 lot = 1.56 USD).
            dec = [d for d in closed_deals if abs(d.get("profit", 0)) > config.bep_tolerance_for(d)]
            bep_n = len(closed_deals) - len(dec)
            total_t = len(dec)
            wins_t = sum(1 for d in dec if d.get("profit", 0) > 0)
            loss_t = total_t - wins_t
            wr = (wins_t / total_t) * 100.0 if total_t else 0.0
            pnl_t = sum(d.get("profit", 0) for d in closed_deals)
            bep_str = f" | {bep_n} BEP" if bep_n else ""
            print(f"[PERFORMA HARIAN] {total_t} Trade | {wins_t} Win - {loss_t} Loss (WinRate: {wr:.1f}%){bep_str} | Net PnL: ${pnl_t:+.2f} USD")

            # Per-symbol breakdown so weekend BTC P/L does not mask weekday XAU performance
            by_symbol = {}
            for d in closed_deals:
                sym = d.get("symbol", "UNKNOWN")
                bucket = by_symbol.setdefault(sym, {"n": 0, "wins": 0, "pnl": 0.0, "bep": 0})
                bucket["n"] += 1
                bucket["pnl"] += d.get("profit", 0)
                if abs(d.get("profit", 0)) <= config.bep_tolerance_for(d):
                    bucket["bep"] += 1
                elif d.get("profit", 0) > 0:
                    bucket["wins"] += 1
            if len(by_symbol) > 1:
                parts = []
                for sym, b in sorted(by_symbol.items()):
                    sym_t = b["n"] - b["bep"]
                    sym_wr = (b["wins"] / sym_t) * 100.0 if sym_t else 0.0
                    sym_loss = sym_t - b["wins"]
                    bep_note = f" | {b['bep']} BEP" if b["bep"] else ""
                    parts.append(f"{sym}: {sym_t}T {b['wins']}W-{sym_loss}L WR {sym_wr:.0f}%{bep_note} ${b['pnl']:+.2f}")
                print(f"[PERFORMA PER SIMBOL] " + " | ".join(parts))
        else:
            print("[PERFORMA HARIAN] Belum ada trade tertutup hari ini (0 Trade | WinRate: 0.0%).")
    except Exception as e:
        print(f"[EVALUATOR WARNING] {e}")

    # -- Multi-symbol parallel scan ----------------------------------------------
    # Mode "xau": pool = [XAU] (1 cycle per candle, seperti sebelumnya).
    # Mode "xau_pairs": pool = [XAU] + FX_PAIR_SYMBOLS.
    global _symbol_last_candle
    valid_pool = _resolve_valid_pool()
    # NOTE: seed startup scan TIDAK di sini - sudah dilakukan di main loop startup
    # (lihat blok startup_run). Kalau seed di sini, cycle pertama yang trigger
    # candle baru close -> closed_time == seeded_time -> SEMUA symbol ke-skip.
    for sym in valid_pool:
        config.SYMBOL = sym
        
        # Smart Timeframe Rotation: Hanya memanggil AI jika candle untuk timeframe pair INI SUDAH CLOSE
        tf = config.get_timeframe(sym)
        rates = mt5.copy_rates_from_pos(sym, tf, 0, 2)
        if rates is None or len(rates) < 2:
            continue
            
        closed_time = int(rates[-2]['time'])
        last_time = _symbol_last_candle.get(sym)
        
        # Eksekusi siklus LLM jika belum pernah di-scan (startup mode "all") ATAU candle baru sudah close
        if last_time is None or closed_time > last_time:
            _symbol_last_candle[sym] = closed_time
            
            # Log indikator candle baru untuk pair selain pair utama (yang log-nya sudah ada di main loop)
            if last_time is not None and sym != valid_pool[0]:
                candle_wib = connector.server_to_wib(closed_time)
                tf_label = "H1" if tf == mt5.TIMEFRAME_H1 else ("M30" if tf == mt5.TIMEFRAME_M30 else "M5")
                print(f"\n Candle {tf_label} baru CLOSE untuk {sym}! Waktu: {candle_wib.strftime('%Y-%m-%d %H:%M:%S')} WIB")
                
            try:
                _run_cycle_for_current_symbol()
            except Exception as e:
                print(f"[CYCLE ERROR {sym}] {e}")
        else:
            # Candle belum ada yang close baru (masih di rentang candle yang sama), skip LLM call untuk pair ini
            pass
            
    # Restore ke simbol utama pool (valid, sudah auto-correct) - biar status line
    # & candle check berikutnya konsisten memakai simbol utama, bukan yang terakhir.
    config.SYMBOL = valid_pool[0] if valid_pool else config.SYMBOL
    return True


def _run_cycle_for_current_symbol():
    """Full cycle untuk satu simbol aktif (config.SYMBOL): risk gate -> data -> LLM
    -> consensus -> eksekusi. Dipanggil per simbol dalam pool (mode xau_pairs).
    """
    # 0. Risk gate - check all conditions before trading
    can_trade, reason = risk.can_trade()
    if not can_trade:
        print(reason)
        return True  # Not an error, just skipping
    
    # 1. Fetch market data (51 bar, buang bar aktif -> 50 candle SUDAH CLOSE. M5 XAU / H1 FX / M30 BTC)
    df = connector.get_market_data(config.SYMBOL, config.get_timeframe(config.SYMBOL), num_candles=51)
    if df is None or len(df) == 0:
        print("Gagal mendapatkan market data. Melewatkan siklus ini.")
        return False
    if len(df) > 50:
        # Bar terakhir = candle aktif (masih berjalan, belum close). Buang -> LLM scan
        # data candle yang SUDAH CLOSE (lengkap), bukan candle kosong yang baru terbentuk.
        df = df.iloc[-50:-1].reset_index(drop=True)
        
    # 2. Fetch current tick (Bid/Ask)
    tick = connector.get_current_tick(config.SYMBOL)
    if tick is None:
        print("Gagal mendapatkan tick data terbaru. Melewatkan siklus ini.")
        return False
        
    print(f"Harga saat ini {config.SYMBOL} - Bid: {tick['bid']}, Ask: {tick['ask']}, Spread: {tick['spread']} pts")

    # 2.1 Calculate Market Randomness & Micro Fat Tails (Hurst M30/M5, Kurtosis M30/M1)
    if getattr(config, "QUANT_ANALYSIS_ENABLED", True):
        try:
            from src.analytics import market_randomness
            rand_info = market_randomness.analyze_market_randomness(df, symbol=config.SYMBOL)
            ft = rand_info.get('fat_tail', {})
            tf_micro = ft.get('tf', 'M5' if config.is_crypto(config.SYMBOL) else 'M1')
            print(f"[QUANT MATH] Hurst: {rand_info['hurst']:.2f} ({rand_info['regime']}) | "
                  f"Kurtosis({tf_micro}): {ft.get('kurtosis', 0.0):+.2f} ({ft.get('label', 'NORMAL')}) | "
                  f"Skew({tf_micro}): {ft.get('skewness', 0.0):+.2f} | "
                  f"Status: {' BLOCKED (Pure Random Walk)' if rand_info['is_random'] else ' PASSED'}")
        except Exception as e:
            print(f"[QUANT MATH ERROR] {e}")

    # 2.2 Calculate Quant Monte Carlo Probabilities & Time Horizon
    if getattr(config, "MONTE_CARLO_ENABLED", False):
        try:
            from src.analytics import quant_probability
            tf_mins = 60 if config.is_crypto(config.SYMBOL) else 5
            q_res = quant_probability.calculate_quant_probabilities(df, timeframe_minutes=tf_mins)
            print(f"[QUANT PROB] Monte Carlo (1000 paths): "
                  f" UP {q_res['prob_up_pct']}% (${q_res['expected_target_up']}) | "
                  f" DOWN {q_res['prob_down_pct']}% (${q_res['expected_target_down']}) | "
                  f"Est. Horizon: {q_res['estimated_time_str']}")
        except Exception as e:
            print(f"[QUANT PROB ERROR] {e}")
    



    # 3. Check for existing open positions
    open_positions = connector.get_open_positions(config.SYMBOL)


    # 4. Query AI models in parallel (including active open_positions for 5-min AI re-evaluation!)

    # MTF/fundamental analysis per-symbol - cache di macro_analyst per-symbol,
    # jadi simbol non-aktif (EURJPY, GBPCHF, dst.) di-populate di sini juga,
    # bukan cuma XAU dari loop utama.
    if config.MTF_ANALYSIS_ENABLED or config.FUNDAMENTAL_ANALYSIS_ENABLED:
        try:
            macro.check_and_update_analysis()
        except Exception as e:
            print(f"[MACRO UPDATE ERROR {config.SYMBOL}] {e}")

    macro_context = macro.get_macro_context()
    if macro_context:
        print(f"Menyertakan analisa Multi-Timeframe & Fundamental ({config.SYMBOL}) untuk LLM...")

    if getattr(config, "MEMORY_CONTEXT_ENABLED", True):
        lessons_ctx = trade_evaluator.evaluator.get_lessons_context()
        if lessons_ctx:
            print("Menyertakan Lesson Learned & Memori Trading untuk LLM...")

    # Pre-warm forecast: synchronous refresh ONLY if cache is stale (15 min XAU /
    # 30 min BTC). Kalau cache masih fresh, langsung return tanpa nge-block.
    # Hasil forecast di-print SEBELUM "Mengirim data..." biar urutan log rapi.
    if getattr(config, "FORECAST_ENABLED", True):
        try:
            forecast_engine.forecaster.refresh_if_stale(config.SYMBOL, df, tick, macro_context)
        except Exception as e:
            print(f"[FORECAST WARNING] {e}")

    ai_mode = config.get_ai_mode()
    active_models = config.active_ai_model_names()
    print(f"[AI MODE {ai_mode.upper()}] Mengirim data ke {', '.join(active_models)}...")
    decisions = llm.get_multi_llm_decisions(config.SYMBOL, df, tick, macro_context, open_positions)
    
    # 5. Calculate consensus
    result = consensus.calculate_consensus(decisions)

    # 5.1 Execute AI Position Re-Evaluator Close Actions
    tickets_to_close = result.get("tickets_to_close", [])
    for close_req in tickets_to_close:
        t_ticket = close_req["ticket"]
        t_reason = close_req["reason"]
        t_models = close_req.get("models", "AI Consensus")
        print(f"[AI RE-EVALUATOR] {t_models} sepakat CLOSE order #{t_ticket}: {t_reason}")
        # Capture pre-close profit so daily P/L + loss streak stay accurate.
        # Net profit = profit + swap + komisi IN+OUT (query deals lengkap, bukan position.profit
        # yang TIDAK include komisi - akun ECN charge $3/sisi, XAU 0.01 lot = -$0.06 round-trip).
        pre_profit = 0.0
        try:
            pos_pre = mt5.positions_get(ticket=t_ticket)
            if pos_pre and len(pos_pre) > 0:
                pre_profit = pos_pre[0].profit + pos_pre[0].swap + pos_pre[0].commission
        except Exception:
            pass
        close_res = connector.close_position(t_ticket)
        if close_res:
            # Setelah close, deal OUT sudah ada di history - hitung netto komisi IN+OUT.
            net_profit = connector.get_position_net_profit(t_ticket)
            if net_profit is not None:
                pre_profit = net_profit
            print(f"Sukses menutup posisi #{t_ticket} berdasarkan rekomendasi AI Re-Evaluator!")
            # Komisi aktual trade (IN+OUT) buat BEP tolerance dinamis - trade yang
            # kalah cuma sebesar komisi (0.06 utk 0.01 lot, 0.60 utk 0.10 lot)
            # dianggap BEP, bukan loss.
            trade_cost = connector.get_position_total_cost(t_ticket)
            risk.record_position_closed(t_ticket, pre_profit, trade_cost)

    # 5.5 Multi-Horizon Forecast Context - INFORMATIONAL ONLY (tidak memblokir eksekusi).
    # Forecast bias/target di-inject ke prompt LLM oleh llm_client; tidak ada gate
    # counter-trend di sini. Konsensus LLM yang menentukan entry.

    # Check if max open positions reached for NEW trades (recovery mode: tighter cap)
    max_positions = config.MAX_OPEN_POSITIONS_RECOVERY if risk.is_recovery_mode else config.MAX_OPEN_POSITIONS
    if len(open_positions) >= max_positions:
        print(f"Posisi terbuka terdeteksi untuk {config.SYMBOL}:")
        for pos in open_positions:
            print(f"  - Ticket #{pos['ticket']}: {pos['type']} {pos['volume']} lot | Profit: {pos['profit']} USD")
        print(f"-> Melewatkan pembukaan posisi baru karena sudah mencapai batas maks ({max_positions}).")
        return True




    # 6. Execute trade if consensus signal is BUY or SELL
    trade_signal = result["signal"]
    if trade_signal in ["BUY", "SELL"]:
        sl_points = result["sl_points"]
        tp_points = result["tp_points"]
        agreeing_count = result.get("agreeing_count", 0)
        
        # Check remaining capacity slots before max positions (recovery mode: tighter cap)
        remaining_slots = max(0, max_positions - len(open_positions))
        desired_positions = 2 if agreeing_count >= 3 else 1
        num_positions = min(desired_positions, remaining_slots)

        # Get effective lot size from risk-based sizing (uses floored SL).
        # split_count: kalau 3/3 unanimous buka 2 posisi, lot per posisi dibagi
        # 2 supaya TOTAL risk per sinyal tetap risk_pct (bukan 2x lipat).
        effective_lot = risk.get_effective_lot_size(sl_points, split_count=num_positions)

        if num_positions > 1:
            print(f"[UNANIMOUS 3/3 HIGH CONFIDENCE] Ketiga AI sepakat {trade_signal}! Membuka {num_positions} posisi sekaligus (Sisa slot: {remaining_slots})...")
        elif num_positions == 1 and desired_positions > 1:
            print(f"[UNANIMOUS 3/3 HIGH CONFIDENCE] Ketiga AI sepakat {trade_signal}! Membuka 1 posisi (Dibatasi sisa slot max: {remaining_slots})...")


        order_executed = False  # flag: ada order yang sukses cycle ini (untuk decision memory)
        for i in range(num_positions):
            # Posisi 2 gets 1.2x TP for capturing extended trend
            pos_tp = int(tp_points * 1.2) if i == 1 else tp_points

            # Comment transaksi = jenis LLM yang sepakat (bukan "Multi-LLM Bot").
            # Contoh: "GPT" / "GPT+Gemini" / "GPT+Gemini+DeepSeek".
            model_labels = {
                "OpenAI": "GPT",
                "Gemini": "Gemini",
                "DeepSeek": "DeepSeek",
                "Claude": "Claude",
            }
            agree_models = result.get("agreeing_models") or []
            order_comment = "+".join(
                model_labels.get(m, m) for m in agree_models
            ) or "Multi-LLM Bot"

            order_res = connector.send_trade_order(
                symbol=config.SYMBOL,
                action=trade_signal,
                lot=effective_lot,
                sl_points=sl_points,
                tp_points=pos_tp,
                comment=order_comment
            )
            if order_res["status"] == "SUCCESS":
                order_executed = True
                print(f"Sukses menempatkan order #{i+1}: {trade_signal} (Ticket: {order_res['ticket']}, Lot: {effective_lot})")
                risk.record_trade_opened()
                tg.alert_trade_opened(
                    trade_signal, effective_lot, sl_points, pos_tp,
                    recovery_mode=risk.is_recovery_mode,
                    session_multiplier=risk.session_lot_multiplier
                )
            else:
                print(f"Gagal menempatkan order #{i+1}: {order_res['comment']}")
    else:
        print("Tidak ada keputusan BUY/SELL yang disetujui. Menunggu candle berikutnya.")

    # Record this cycle's final decision for Recent Decision Memory
    # (so the LLM next cycle can see if it has been HOLDing too long).
    # result: "OPEN" kalau trade dieksekusi cycle ini (hasil di-set pas close),
    #         "N/A" kalau HOLD / gagal gate.
    try:
        decision_memory.memory.record(
            config.SYMBOL,
            signal=result.get("signal", "HOLD"),
            confidence=result.get("confidence", 0.0),
            reasoning=result.get("details", ""),
            result="OPEN" if (result.get("signal") in ("BUY", "SELL") and order_executed) else "N/A",
        )
    except Exception as e:
        print(f"[DECISION MEMORY WARNING] {e}")

    return True


def main():
    # Apply CLI overrides (sesi saja) sebelum bot jalan
    cli_applied, skip_prompt = parse_cli_overrides()

    # Setup TeeLogger to save all terminal logs
    if getattr(config, "LOG_FILE", None):
        tee_logger = TeeLogger(config.LOG_FILE)
        sys.stdout = tee_logger
        sys.stderr = tee_logger
        print(f"Logging aktif. Semua output akan disimpan di: {config.LOG_FILE}")

    print("=" * 60)
    print("   BOT TRADING MULTI-LLM CONSENSUS - PROTECTED EXECUTION    ")
    print("=" * 60)

    # Tampilkan override CLI kalau ada
    if cli_applied:
        print(" [CLI OVERRIDE] " + " | ".join(cli_applied))
        print("-" * 60)

    # Prompt interaktif setting - kecuali --yes atau non-TTY / Docker mode (langsung jalan)
    if not skip_prompt and sys.stdin.isatty():
        interactive_setup()


    # Set active symbol now so the banner shows the symbol that will be traded
    config.refresh_active_symbol()

    print(f"Mode: {'DRY RUN (Hanya Sinyal)' if config.DRY_RUN else 'LIVE EXECUTION (Duit Asli/Demo)'}")
    _tf_map = {mt5.TIMEFRAME_M5: "M5", mt5.TIMEFRAME_M15: "M15", mt5.TIMEFRAME_M30: "M30", mt5.TIMEFRAME_H1: "H1"}
    tf_name = _tf_map.get(config.get_timeframe(config.SYMBOL), "?")
    print(f"Simbol: {config.SYMBOL} | Timeframe: {tf_name} | Lot Size: {config.lot_size_for(config.SYMBOL)}")
    if config.TRADING_MODE == "xau_pairs":
        pool = config.get_rotation_pool()
        print(f"Trading Mode: XAU + PAIRS | Scan Pool ({len(pool)} simbol): {' -> '.join(pool)}")
        print(f" Scan sesuai timeframe masing-masing (XAU M5 / FX H1 / BTC M30) - Smart Rotation (FASE 5)")
    else:
        print(f"Trading Mode: XAU ONLY")
    print(f"Models: OpenAI ({config.OPENAI_MODEL}), Gemini ({config.GEMINI_MODEL}), {llm.claude_slot_label()} ({config.CLAUDE_MODEL})")
    if config.AI_MODE_POLICY == "schedule":
        desc = " | ".join([f"{sh:02d}:{sm:02d}-{eh:02d}:{em:02d} {mode.upper()}" for sh, sm, eh, em, mode in config.AI_MODE_SCHEDULE])
        print(f" AI Mode Schedule: {desc} (WIB)")
    else:
        print(f" AI Mode: FIXED = {config.AI_FIXED_MODE.upper()}")
    print("-" * 60)
    print("PROTEKSI AKTIF:")
    print(f"  Trailing Stop:   {'ON' if config.TRAILING_STOP_ENABLED else 'OFF'} "
          f"(aktivasi {config.TRAILING_ACTIVATION_POINTS} pts, jarak {config.TRAILING_DISTANCE_POINTS} pts)")
    print(f"  Break-Even:      {'ON' if config.BREAK_EVEN_ENABLED else 'OFF'} "
          f"(trigger {config.BREAK_EVEN_TRIGGER_POINTS} pts)")
    print(f"  Partial Close:   {'ON' if config.PARTIAL_CLOSE_ENABLED else 'OFF'} "
          f"({config.PARTIAL_CLOSE_PERCENT}% @ {config.PARTIAL_CLOSE_TP1_POINTS} pts)")
    print(f"  Max Daily Loss:  ${config.MAX_DAILY_LOSS_USD}")
    print(f"  Recovery Mode:   {'ON' if config.RECOVERY_MODE_ENABLED else 'OFF'} "
          f"(x{config.RECOVERY_LOT_MULTIPLIER} setelah {config.MAX_CONSECUTIVE_LOSSES} loss)")
    print(f"  Cooldown:        {config.TRADE_COOLDOWN_SECONDS}s antar trade")
    print(f"  Spread Filter:   {config.max_spread_points_for(config.SYMBOL)} pts maks ({config.SYMBOL})")
    print(f"  Session Filter:  {'ON' if config.SESSION_FILTER_ENABLED else 'OFF'} (WIB)")
    if config.SESSION_FILTER_ENABLED:
        for s in config.ALLOWED_SESSIONS_WIB:
            start = f"{s['start'][0]:02d}:{s['start'][1]:02d}"
            end = f"{s['end'][0]:02d}:{s['end'][1]:02d}"
            mult = s.get("lot_multiplier", 1.0)
            print(f"                   - {s['name']}: {start}-{end} WIB (lot x{mult})")
    print(f"  Weekend Close:   {'ON' if config.WEEKEND_CLOSE_ENABLED else 'OFF'}")
    print(f"  Telegram:        {'ON' if config.TELEGRAM_ENABLED else 'OFF'}")
    print("=" * 60)

    # Validate API keys before connecting to MT5
    missing_keys = []
    if not config.OPENAI_API_KEY: missing_keys.append("OPENAI_API_KEY")
    if not config.GEMINI_API_KEY: missing_keys.append("GEMINI_API_KEY")
    if not config.ANTHROPIC_API_KEY: missing_keys.append("ANTHROPIC_API_KEY")
    
    if missing_keys:
        print(f"ERROR: Kunci API berikut tidak ditemukan di file .env: {', '.join(missing_keys)}")
        print("Silakan salin .env.example menjadi .env dan masukkan API Key Anda.")
        sys.exit(1)

    # Initialize MT5 (validate the symbol that is active right now)
    if not connector.initialize_mt5():
        print("Gagal terhubung ke MetaTrader 5 terminal. Pastikan MT5 Anda aktif.")
        sys.exit(1)
        
    print("\n Terhubung ke MT5 dengan sukses!")
    
    # One-time startup check to evaluate any trades closed while offline
    try:
        print("[STARTUP] Memeriksa tiket terlewat untuk evaluasi post-mortem...")
        trade_evaluator.evaluator.check_and_evaluate_closed_trades()
    except Exception as e:
        print(f"[STARTUP EVALUATOR WARNING] {e}")
        
    # FASE 6 - pilihan mode scan startup (CLI professional, default sesuai timeframe, timeout 10 detik)
    _prompt_startup_scan_mode()

    print("Bot berjalan... Menunggu penutupan candle berikutnya.\n")
    
    # Send startup alert
    tg.alert_bot_started()
    
    # Run initial macro and MTF analysis (forced on startup to ensure we have data immediately)
    if config.MTF_ANALYSIS_ENABLED or config.FUNDAMENTAL_ANALYSIS_ENABLED:
        print("\n [STARTUP] Menjalankan analisa Multi-Timeframe & Fundamental awal...")
        try:
            macro.check_and_update_analysis(force=True)
            print("Analisa Multi-Timeframe & Fundamental awal selesai.\n")
        except Exception as e:
            print(f"[STARTUP ERROR] Gagal menjalankan analisa awal: {e}\n")
            
    last_candle_time = None
    startup_run = True
    last_symbol = config.SYMBOL

    try:
        while True:
            # =================================================================
            #  EVERY TICK (5s): Manage open positions + weekend check
            # =================================================================
            try:
                # Symbol rotation: XAUUSD weekdays, BTCUSD weekends
                active_symbol, changed = config.refresh_active_symbol()
                if changed:
                    print(f"[SYMBOL SWITCH] {last_symbol} -> {active_symbol}")
                    tg.alert_symbol_switch(last_symbol, active_symbol)
                    last_symbol = active_symbol

                # Trailing stop + break-even + partial close
                position_manager.manage_all_positions()

                # Detect positions closed by MT5 (SL/TP/manual) in real time.
                # Returns newly closed deals -> alert Telegram immediately,
                # instead of waiting for the next candle cycle.
                try:
                    new_closed = risk.sync_closed_positions()
                    for deal in new_closed:
                        d_ticket = deal.get("ticket")
                        d_symbol = deal.get("symbol", config.SYMBOL)
                        d_profit = deal.get("profit", 0.0)
                        d_reason = deal.get("reason")
                        d_comment = deal.get("comment", "")
                        d_type = deal.get("type", "")
                        print(f"[CLOSE DETECTED] #{d_ticket} {d_symbol} {d_type} "
                              f"ditutup (P/L: {d_profit:+.2f}, reason: {d_reason or 'unknown'})")
                        try:
                            tg.alert_trade_closed(
                                ticket=d_ticket,
                                symbol=d_symbol,
                                profit=d_profit,
                                reason_code=d_reason,
                                comment=d_comment,
                                pos_type=d_type,
                                commission=deal.get("commission", 0.0),
                            )
                        except Exception as e:
                            print(f"[TELEGRAM WARNING] Gagal kirim alert close: {e}")
                        # Update decision memory dengan hasil trade (biar
                        # summarize_recent_outcomes punya count win/loss AKURAT).
                        try:
                            decision_memory.memory.update_result(
                                d_symbol,
                                result=d_reason or "N/A",
                                profit=d_profit,
                                commission=deal.get("commission", 0.0),
                            )
                        except Exception as e:
                            print(f"[DECISION MEMORY WARNING] update_result: {e}")

                    # Post-mortem langsung untuk tiket yang baru saja ditutup,
                    # jalan di background thread biar loop 5 detik nggak ke-block
                    # sama LLM call post-mortem.
                    if new_closed:
                        try:
                            _pm_deals = list(new_closed)
                            threading.Thread(
                                target=trade_evaluator.evaluator.check_and_evaluate_closed_trades,
                                args=(_pm_deals,),
                                daemon=True,
                            ).start()
                        except Exception as e:
                            print(f"[POST-MORTEM ERROR] Gagal evaluasi tiket baru: {e}")
                except Exception as e:
                    print(f"[CLOSE SYNC ERROR] {e}")
                
                # Weekend position management
                weekend_actions = risk.check_weekend_positions()
                for action in weekend_actions:
                    ticket = action["ticket"]
                    reason = action["reason"]
                    print(f"{reason}")
                    
                    # Get position profit before closing (include swap+commission
                    # so the recorded result matches what MT5 deal history reports)
                    positions = mt5.positions_get(ticket=ticket)
                    profit = 0.0
                    if positions and len(positions) > 0:
                        profit = positions[0].profit + positions[0].swap + positions[0].commission
                    
                    success = connector.close_position(ticket)
                    if success:
                        print(f"Posisi #{ticket} ditutup untuk weekend.")
                        # Net profit REAL = profit + swap + komisi IN+OUT (query deals lengkap).
                        net_profit = connector.get_position_net_profit(ticket)
                        if net_profit is not None:
                            profit = net_profit
                        # Komisi aktual trade buat BEP tolerance dinamis (lihat di atas).
                        trade_cost = connector.get_position_total_cost(ticket)
                        risk.record_position_closed(ticket, profit, trade_cost)
                        tg.alert_weekend_close(ticket, profit, reason)

            except Exception as e:
                print(f"[POS MANAGER ERROR] {e}")
            
            # =================================================================
            #  ON NEW CANDLE: Run full trading cycle
            # Check and update multi-timeframe and macro analysis
            if config.MTF_ANALYSIS_ENABLED or config.FUNDAMENTAL_ANALYSIS_ENABLED:
                try:
                    macro.check_and_update_analysis()
                except Exception as e:
                    print(f"[MACRO UPDATE ERROR] {e}")

            rates = mt5.copy_rates_from_pos(config.SYMBOL, config.get_timeframe(config.SYMBOL), 0, 2)
            if rates is not None and len(rates) > 0:
                # FASE 6: scan pas candle CLOSE - rates[-1] = candle aktif (belum close),
                # rates[-2] = candle terakhir yang SUDAH close. Trigger pakai open-time candle close.
                if len(rates) >= 2:
                    current_candle_time = int(rates[-2]['time'])
                else:
                    current_candle_time = int(rates[-1]['time'])
                
                if startup_run or (last_candle_time is not None and current_candle_time > last_candle_time):
                    skip_cycle = False
                    if startup_run:
                        startup_run = False
                        if _STARTUP_SCAN_MODE == "timeframe":
                            # Seed SEKARANG (di startup): _symbol_last_candle[sym] = open-time
                            # candle terakhir yang SUDAH close. Cycle pertama menyusul pas candle
                            # close BERIKUTNYA (closed_time > seeded_time -> LOLOS).
                            # JANGAN seed di dalam run_trading_cycle: cycle pertama yang trigger
                            # candle baru close -> closed_time == seeded_time -> SEMUA symbol skip.
                            try:
                                _seed_startup_scan(_resolve_valid_pool())
                            except Exception as e:
                                print(f"[SEED WARNING] {e}")
                            skip_cycle = True
                            print("Startup scan mode: sesuai timeframe - menunggu candle close berikutnya...")
                        else:
                            print("Menjalankan siklus analisa pertama saat startup (scan all now)...")
                    else:
                        candle_wib = connector.server_to_wib(int(current_candle_time))
                        print(f"\n Candle baru terdeteksi! Waktu: {candle_wib.strftime('%Y-%m-%d %H:%M:%S')} WIB")
                    
                    last_candle_time = current_candle_time
                    
                    # Show daily P/L and risk status
                    daily_pnl = risk.get_daily_pnl()
                    status = risk.get_status_summary()
                    print(f"P/L Hari Ini: ${daily_pnl:.2f} | "
                          f"Loss Streak: {status['consecutive_losses']} | "
                          f"Recovery: {' Ya' if status['recovery_mode'] else 'Tidak'} | "
                          f"Session Lot: x{status['session_lot_multiplier']}")
                    
                    if not skip_cycle:
                        # Run trading cycle
                        run_trading_cycle()
            else:
                print("Gagal mengecek status candle di MT5. Mencoba kembali...")
            
            # Show live status clock line in CLI every loop iteration
            now_str = time.strftime('%H:%M:%S')
            remaining_pause = risk.get_remaining_pause()
            pause_str = f" (PAUSED: sisa {remaining_pause}s)" if remaining_pause > 0 else ""
            # Show any running (open) bot positions across ALL symbols
            open_pos = connector.get_all_open_positions()
            if open_pos:
                by_sym = {}
                for p in open_pos:
                    by_sym.setdefault(p.get("symbol", "?"), []).append(p)
                pos_parts = []
                for sym, plist in sorted(by_sym.items()):
                    float_s = sum(x.get("profit", 0.0) for x in plist)
                    pos_parts.append(f"{sym}: {len(plist)} pos ${float_s:+.2f}")
                pos_str = " | " + " | ".join(pos_parts)
            else:
                pos_str = ""
            status_line = f"[{config.SYMBOL} | {now_str}]{pause_str}{pos_str}"
            # Potong berdasarkan LEBAR TAMPILAN terminal aktual (emoji = 2 kolom), bukan
            # jumlah karakter - kalau baris wrap, \r tidak balik ke awal baris dan status
            # jadi nge-print ke bawah (bukan refresh). Sisakan margin 4 kolom biar aman.
            try:
                cols = shutil.get_terminal_size((120, 24)).columns
            except Exception:
                cols = 120
            max_w = max(60, cols - 4)
            status_line = _truncate_disp(status_line, max_w)
            if _VT_OK:
                # Hapus isi baris dulu biar sisa status sebelumnya (yang lebih panjang) hilang
                sys.stdout.write(f"\x1b[2K\r{status_line}")
            else:
                sys.stdout.write(f"\r{status_line:<{max_w}}")
            sys.stdout.flush()

            # Sleep 5 seconds between checks
            time.sleep(3)  # loop utama - cache query MT5 sudah kurangi beban, 3 detik aman

            
    except KeyboardInterrupt:
        print("\n Bot dimatikan secara manual oleh user.")
    finally:
        # Send daily summary before shutdown
        daily_pnl = risk.get_daily_pnl()
        tg.alert_daily_summary(daily_pnl, 0, risk.get_status_summary())
        mt5.shutdown()
        print("Koneksi MT5 diputus. Sampai jumpa!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n Bot dimatikan secara manual oleh user.")
        try:
            mt5.shutdown()
        except Exception:
            pass
        print("Koneksi MT5 diputus. Sampai jumpa!")
