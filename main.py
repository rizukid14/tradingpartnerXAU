import os
import time
import sys
import json
import threading
# Force UTF-8 encoding for standard output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

import config
from config import mt5
from src.core import mt5_connector as connector, llm_client as llm, consensus, telegram_alerts as tg
from src.core.risk_engine import RiskEngine
from src.core.cli_theme import UI, render_banner, render_scanner_banner, render_candidate_alert_box, render_hacker_bento_hud
from src.analytics import position_manager
from src.analytics.market_scanner import MarketScanner, CandidateSetup

import re
import shutil
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_WIB = ZoneInfo("Asia/Jakarta")

# --- Status line terminal (Windows) ---
_VT_OK = False
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
_ANSI_TOKEN_RE = re.compile(r'(\x1b\[[0-9;]*[a-zA-Z])')


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


def _tf_to_seconds(tf):
    """Konversi timeframe MT5 -> detik (buat label range candle open-close)."""
    mapping = {
        mt5.TIMEFRAME_M1: 60,
        mt5.TIMEFRAME_M5: 300,
        mt5.TIMEFRAME_M15: 900,
        mt5.TIMEFRAME_M30: 1800,
        mt5.TIMEFRAME_H1: 3600,
        mt5.TIMEFRAME_H4: 14400,
        mt5.TIMEFRAME_D1: 86400,
    }
    return mapping.get(tf, 3600)


# --- PENDING ORDER LIFECYCLE ---
_pending_state_cache = None
_pending_state_mtime = 0

# Buffer recap HOLD per cycle (18 Agu): HOLD tidak dikirim per-symbol,
# dikumpulkan & dikirim SATU pesan gabungan di akhir run_trading_cycle.
_hold_recap_lines = []


def _load_pending_state():
    """Load riwayat pending order dari file JSON (persist antar restart)."""
    global _pending_state_cache, _pending_state_mtime
    path = config.PENDING_ORDERS_STATE_FILE
    try:
        mtime = os.path.getmtime(path)
        if _pending_state_cache is not None and mtime == _pending_state_mtime:
            return _pending_state_cache
        with open(path, "r", encoding="utf-8") as f:
            _pending_state_cache = json.load(f)
        _pending_state_mtime = mtime
    except FileNotFoundError:
        _pending_state_cache = {"pending": []}
        _pending_state_mtime = 0
    except Exception:
        if _pending_state_cache is None:
            _pending_state_cache = {"pending": []}
    return _pending_state_cache


def _save_pending_state(state):
    """Simpan riwayat pending order ke file JSON."""
    global _pending_state_cache, _pending_state_mtime
    _pending_state_cache = state
    try:
        with open(config.PENDING_ORDERS_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        _pending_state_mtime = os.path.getmtime(config.PENDING_ORDERS_STATE_FILE)
    except Exception as e:
        print(f"[PENDING STATE ERROR] {e}")


def _record_pending_event(event):
    """Catat event pending (placed/filled/expired/cancelled) ke state file."""
    state = _load_pending_state()
    state.setdefault("pending", []).append(event)
    # Simpan maks 500 event terakhir biar file tidak membengkak
    state["pending"] = state["pending"][-500:]
    _save_pending_state(state)


def _manage_pending_orders():
    """
    Lifecycle pending order tiap cycle:
    1. Hapus pending yang sudah expired (MT5 biasanya auto-hapus, tapi catat)
    2. Cancel pending yang arahnya kontra dengan konsensus baru (tesis mati)
    3. Cap maks pending aktif
    Dipanggil di awal _run_cycle_for_current_symbol (setelah risk gate).
    """
    if not getattr(config, "PENDING_ORDERS_ENABLED", False):
        return
    try:
        pendings = connector.get_pending_orders()
        if not pendings:
            return
        now_server = int(time.time())  # pending expiration pakai server time offset
        # 1. Expired / hampir expired
        for p in pendings:
            if p.get("expiration") and p["expiration"] > 0 and p["expiration"] < now_server + 30:
                connector.cancel_pending_order(p["ticket"])
                _record_pending_event({
                    "event": "expired",
                    "ticket": p["ticket"],
                    "symbol": p["symbol"],
                    "type": p.get("type_str"),
                    "price": p.get("price"),
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
        # 2. Cap: kalau masih lebih dari max, cancel yang paling lama (expiration terkecil)
        pendings = connector.get_pending_orders()
        max_active = getattr(config, "PENDING_ORDER_MAX_ACTIVE", 3)
        if len(pendings) > max_active:
            pendings_sorted = sorted(pendings, key=lambda p: p.get("expiration") or 0)
            for p in pendings_sorted[: len(pendings) - max_active]:
                connector.cancel_pending_order(p["ticket"])
                _record_pending_event({
                    "event": "cancelled_cap",
                    "ticket": p["ticket"],
                    "symbol": p["symbol"],
                    "type": p.get("type_str"),
                    "price": p.get("price"),
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
    except Exception as e:
        print(f"[PENDING MANAGE ERROR] {e}")


def _cancel_pending_contra(new_signal, symbol=None):
    """
    Cancel semua pending order yang arahnya berlawanan dengan sinyal baru untuk simbol tertentu.
    Konsensus baru = tesis lama sudah mati -> pending kontra tidak relevan.
    """
    if not getattr(config, "PENDING_ORDERS_ENABLED", False):
        return
    try:
        pendings = connector.get_pending_orders()
        if not pendings or new_signal not in ("BUY", "SELL"):
            return
        target_symbol = symbol or getattr(config, "SYMBOL", None)
        for p in pendings:
            if target_symbol and p.get("symbol") != target_symbol:
                continue
            ptype = p.get("type_str", "")
            is_buy_pending = ptype in ("buy_stop", "buy_limit")
            is_sell_pending = ptype in ("sell_stop", "sell_limit")
            if (new_signal == "BUY" and is_sell_pending) or (new_signal == "SELL" and is_buy_pending):
                connector.cancel_pending_order(p["ticket"])
                _record_pending_event({
                    "event": "cancelled_contra",
                    "ticket": p["ticket"],
                    "symbol": p["symbol"],
                    "type": ptype,
                    "price": p.get("price"),
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
    except Exception as e:
        print(f"[PENDING CONTRA ERROR] {e}")


def _report_pending_stats():
    """Print ringkasan statistik pending order (AI proven) ke CLI."""
    if not getattr(config, "PENDING_ORDERS_ENABLED", False):
        return
    try:
        state = _load_pending_state()
        events = state.get("pending", [])
        if not events:
            return
        placed = [e for e in events if e.get("event") in ("placed",)]
        filled = [e for e in events if e.get("event") == "filled"]
        expired = [e for e in events if e.get("event") == "expired"]
        cancelled = [e for e in events if e.get("event") in ("cancelled_contra", "cancelled_cap", "cancelled_manual")]
        print(f" {UI.tag('PENDING STATS', UI.MAGENTA)} placed={len(placed)} filled={len(filled)} "
              f"expired={len(expired)} cancelled={len(cancelled)}")
    except Exception as e:
        print(f"[PENDING STATS ERROR] {e}")


def _hold_recap_line(result):
    """Buat 1 baris ringkasan HOLD untuk 1 simbol (buat recap Telegram).
    Return None kalau pure_hold (semua model HOLD) — tidak perlu direkap.
    """
    hold_type = result.get("hold_type")
    if not hold_type or hold_type == "pure_hold":
        return None
    sym = config.SYMBOL
    decisions = result.get("decisions", {})
    # Ringkas: model + arah + confidence (buat yang bukan HOLD)
    parts = []
    for m_name, dec in decisions.items():
        sig = dec.get("signal") or "HOLD"
        if sig in ("BUY", "SELL"):
            conf = (dec.get("confidence") or 0.0) * 100
            et = (dec.get("entry_type") or "market").strip().lower()
            ep = dec.get("entry_price")
            if et != "market" and ep:
                parts.append(f"{m_name} {sig} {conf:.0f}% ({et} @ {ep})")
            else:
                parts.append(f"{m_name} {sig} {conf:.0f}% ({et})")
        else:
            parts.append(f"{m_name} HOLD")
    vote_str = ", ".join(parts)
    if hold_type == "atr_gate":
        reason = (result.get("sltp_reason") or result.get("details") or "").strip()
        return f"• `{sym}`: Trade batal (gate ATR) — {reason[:60]}"
    if hold_type == "low_confidence":
        return f"• `{sym}`: HOLD (conf rendah) — {vote_str}"
    if hold_type == "split_vote":
        return f"• `{sym}`: Beda pendapat — {vote_str}"
    return None


def _send_hold_recap():
    """Kirim recap HOLD + News Alert gabungan (satu pesan) kalau ada isi. Reset buffer."""
    global _hold_recap_lines
    try:
        from src.analytics.economic_calendar import calendar as econ_cal
        active_news = econ_cal.get_context()
        if _hold_recap_lines or active_news:
            tg.alert_hold_recap(list(_hold_recap_lines), news_context=active_news)
    except Exception as e:
        print(f"[HOLD RECAP ERROR] {e}")
    _hold_recap_lines = []


def _candle_range_label(open_ts, tf):
    """Label candle non-ambigu: '15:00-16:00 WIB' (open-close). open_ts = open-time candle."""
    from datetime import timedelta
    open_wib = connector.server_to_wib(int(open_ts))
    close_wib = open_wib + timedelta(seconds=_tf_to_seconds(tf))
    return f"{open_wib.strftime('%H:%M')}-{close_wib.strftime('%H:%M')} WIB"


def _disp_width(s):
    """Lebar tampilan visual di terminal tanpa menghitung kode ANSI: emoji/wide char = 2 kolom, sisanya 1."""
    plain = _ANSI_RE.sub('', s)
    return sum(
        2 if ord(ch) > 0xFFFF or unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in plain
    )


def _truncate_disp(s, max_w):
    """Potong string agar lebar visual <= max_w tanpa merusak sequence ANSI / memotong di tengah kode warna."""
    if _disp_width(s) <= max_w:
        return s
    tokens = _ANSI_TOKEN_RE.split(s)
    out = []
    w = 0
    target_w = max_w - 3  # sisakan ruang untuk '...'
    for token in tokens:
        if not token:
            continue
        if _ANSI_RE.fullmatch(token):
            out.append(token)
        else:
            for ch in token:
                cw = 2 if ord(ch) > 0xFFFF or unicodedata.east_asian_width(ch) in ("W", "F") else 1
                if w + cw > target_w:
                    out.append(f"...{UI.RST}")
                    return "".join(out)
                out.append(ch)
                w += cw
    out.append(UI.RST)
    return "".join(out)


def _wrap_positions(parts, max_w, indent):
    """Wrap daftar posisi (string ANSI) ke beberapa baris — tiap baris di-indent, TIDAK ada posisi yang dipotong.
    Diisi maks 3 posisi per baris dengan pemisah ' | ', baris berikutnya rata sejajar.
    """
    lines = []
    first_indent = indent
    subseq_indent = UI.GRAY + "       " + UI.RST
    
    cur_line = []
    cur_w = _disp_width(first_indent)
    cur_indent = first_indent
    
    for part in parts:
        pw = _disp_width(part)
        sep_w = 3 if cur_line else 0
        if cur_line and (cur_w + sep_w + pw > max_w or len(cur_line) >= 3):
            lines.append(cur_indent + " | ".join(cur_line))
            cur_line = [part]
            cur_indent = subseq_indent
            cur_w = _disp_width(subseq_indent) + pw
        else:
            cur_line.append(part)
            cur_w += sep_w + pw
            
    if cur_line:
        lines.append(cur_indent + " | ".join(cur_line))
        
    return lines


_status_render_count = 0  # jumlah baris status live yang sedang tampil (di-update tiap render)


def _reset_status_lines():
    """Hapus SEMUA baris status loop live (bisa multi-baris) sebelum mencetak event/log baru
    agar tidak bertumpuk. Cursor-up ke baris pertama status, lalu erase tiap baris ke bawah.
    """
    global _status_render_count
    n = _status_render_count
    _status_render_count = 0
    if n <= 0:
        sys.stdout.write("\r")
        sys.stdout.flush()
        return
    if _VT_OK:
        if n > 1:
            sys.stdout.write(f"\x1b[{n - 1}A")  # naik ke baris pertama status
        for i in range(n):
            sys.stdout.write("\x1b[2K")  # hapus isi baris
            if i < n - 1:
                sys.stdout.write("\x1b[B")  # turun ke baris berikutnya
        if n > 1:
            sys.stdout.write(f"\x1b[{n - 1}A")  # kembalikan kursor ke baris pertama agar 0 baris kosong
        sys.stdout.write("\r")
    else:
        sys.stdout.write("\r")
    sys.stdout.flush()


def _render_status_lines(lines, vt_ok=True):
    """Tulis status live multi-baris: hapus baris lama (cursor-up + erase per baris) lalu
    tulis yang baru, supaya auto-scroll terminal tidak merusak refresh in-place.
    lines = daftar baris (masing-masing boleh berisi ANSI).
    """
    global _status_render_count
    n_old = _status_render_count
    n_new = len(lines)
    _status_render_count = n_new
    if not vt_ok:
        return "\r" + lines[0] + "".join(f"\n{l}" for l in lines[1:])
    out = ["\r"]
    if n_old > 1:
        out.append(f"\x1b[{n_old - 1}A")  # naik ke baris pertama status lama
    max_rows = max(n_old, n_new)
    for i in range(max_rows):
        out.append("\x1b[2K")  # hapus isi baris (sisa lama atau baris baru)
        if i < n_new:
            out.append(lines[i])
        if i < max_rows - 1:
            out.append("\n")
    return "".join(out)



# Initialize risk engine
risk = RiskEngine()


class TeeLogger:
    """Duplicate stdout/stderr output to terminal and a log file."""
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log_file = open(filename, "a", encoding="utf-8", buffering=1)

    def write(self, message):
        global _status_render_count
        # Cek apakah message ini adalah render status bar 3 detik (dimulai dengan \r)
        is_status_render = message.startswith("\r")
        if not is_status_render and _status_render_count > 0:
            # Ada output teks log/print saat status bar live sedang aktif di terminal.
            # Hapus status bar dari layar terlebih dahulu agar pesan tercetak bersih dan masuk scroll buffer.
            _reset_status_lines()
            _status_render_count = 0

        self.terminal.write(message)
        try:
            # Tulis ke file log (hindari spamming baris refresh in-place 3 detik ke file log)
            if not is_status_render:
                clean_msg = _ANSI_RE.sub("", message)
                self.log_file.write(clean_msg)
        except Exception:
            pass

    def flush(self):
        self.terminal.flush()
        try:
            self.log_file.flush()
        except Exception:
            pass


def _tpsl_rules_arg(value):
    """Parser argparse untuk --tpsl-rules: terima 'ATR-Based'/'LLM' (case-insensitive)."""
    v = value.strip().lower()
    if v in ("atr-based", "atr", "default", "safe"):
        return "ATR-Based"
    if v in ("llm", "free", "bebas"):
        return "LLM"
    raise ValueError("pilih 'ATR-Based' atau 'LLM'")


def parse_cli_overrides(argv=None):
    """
    Parse CLI flags untuk override config sebelum bot jalan (sesi saja, tidak disimpan).
    """
    import argparse
    p = argparse.ArgumentParser(description="Trading bot MT5 - override config via CLI (sesi saja).")
    p.add_argument("--dry-run", action="store_true", help="Mode dry-run (sinyal saja, tanpa order)")
    p.add_argument("--live", action="store_true", help="Mode live (kirim order beneran)")
    p.add_argument("--risk-percent-btc", type=float, help="Risk pct equity per trade BTC (mis. 0.5)")
    p.add_argument("--risk-percent-fx", type=float, help="Risk pct equity per trade FX (mis. 1.0)")
    p.add_argument("--max-daily-loss", type=float, help="Batas kerugian harian USD (mis. 250)")
    p.add_argument("--max-positions", type=int, help="Max posisi open (mis. 6)")
    p.add_argument("--spread-max-btc", type=float, help="Spread filter max BTC (pts)")
    p.add_argument("--cooldown", type=int, help="Cooldown antar trade (detik)")
    p.add_argument("--telegram", choices=["on", "off"], help="Telegram notifikasi on/off")
    p.add_argument("--claude-model", type=str,
                   help="Model slot Claude: 'deepseek/deepseek-v4-flash' atau 'claude-haiku-4-5-20251001'")
    p.add_argument("--tpsl-rules", type=_tpsl_rules_arg, metavar="{ATR-Based,LLM}",
                   help="Aturan SL/TP: 'ATR-Based' atau 'LLM'")
    p.add_argument("--pending-orders", choices=["on", "off"],
                   help="Pending order (LIMIT/STOP dari AI) on/off")
    p.add_argument("--account", choices=["live", "demo"],
                   help="Pilih akun MT5: 'live' (real money) atau 'demo' (virtual)")
    p.add_argument("--macro", type=str, nargs="?", const="all",
                   help="Tampilkan Top-Down Macro Strategic Directive (MSE) di CLI untuk simbol tertentu atau 'all'")
    p.add_argument("--yes", "-y", action="store_true",
                   help="Lewati prompt interaktif saat startup (cocok untuk Docker/non-interactive)")
    args = p.parse_args(argv)

    applied = []

    if args.dry_run and args.live:
        print("[CLI] Tidak bisa --dry-run dan --live bersamaan.")
        sys.exit(1)

    if args.dry_run:
        config.DRY_RUN = True
        applied.append("DRY_RUN=True")
    elif args.live:
        config.DRY_RUN = False
        applied.append("DRY_RUN=False")

    if args.risk_percent_btc is not None:
        config.RISK_PERCENT_BTC = args.risk_percent_btc
        applied.append(f"RISK_PERCENT_BTC={args.risk_percent_btc}")
    if getattr(args, "risk_percent_fx", None) is not None:
        config.RISK_PERCENT_FX = args.risk_percent_fx
        applied.append(f"RISK_PERCENT_FX={args.risk_percent_fx}")
    if args.claude_model is not None:
        v = args.claude_model.lower().strip()
        if v in ("deepseek", "flash", "v4-flash", "deepseek-flash", "1"):
            config.CLAUDE_MODEL = "deepseek/deepseek-v4-flash"
        elif v in ("haiku", "3"):
            config.CLAUDE_MODEL = "claude-haiku-4-5-20251001"
        else:
            config.CLAUDE_MODEL = args.claude_model
        applied.append(f"CLAUDE_MODEL={config.CLAUDE_MODEL}")
    if args.tpsl_rules is not None:
        config.TP_SL_RULES = args.tpsl_rules
        applied.append(f"TP_SL_RULES={config.TP_SL_RULES}")
    if args.pending_orders is not None:
        config.PENDING_ORDERS_ENABLED = (args.pending_orders == "on")
        applied.append(f"PENDING_ORDERS_ENABLED={config.PENDING_ORDERS_ENABLED}")
    if args.max_daily_loss is not None:
        config.MAX_DAILY_LOSS_USD = args.max_daily_loss
        applied.append(f"MAX_DAILY_LOSS_USD={args.max_daily_loss}")
    if args.max_positions is not None:
        config.MAX_OPEN_POSITIONS = args.max_positions
        applied.append(f"MAX_OPEN_POSITIONS={args.max_positions}")
    if args.spread_max_btc is not None:
        config.MAX_SPREAD_POINTS_BTC = args.spread_max_btc
        applied.append(f"MAX_SPREAD_POINTS_BTC={args.spread_max_btc}")
    if args.cooldown is not None:
        config.TRADE_COOLDOWN_SECONDS = args.cooldown
        applied.append(f"TRADE_COOLDOWN_SECONDS={args.cooldown}")
    if args.telegram:
        config.TELEGRAM_ENABLED = (args.telegram == "on")
        applied.append(f"TELEGRAM_ENABLED={config.TELEGRAM_ENABLED}")
    if getattr(args, "account", None):
        config.MT5_ACCOUNT_MODE = args.account
        config.refresh_mt5_credentials()
        applied.append(f"MT5_ACCOUNT_MODE={config.MT5_ACCOUNT_MODE}")
    if getattr(args, "macro", None) is not None:
        setattr(config, "CLI_MACRO_ARG", args.macro)
        applied.append(f"MACRO_INSPECT={args.macro}")

    return applied, getattr(args, "yes", False)




def record_funnel_event(event_type: str, sym: str = "", setup: str = "", details: dict = None):
    """Tracks Stage 1, Pass 1, Pass 2 Veto, and Execution conversion rates."""
    metrics_file = os.path.join(config.DATA_DIR, "quant_funnel_metrics.json")
    try:
        data = {}
        if os.path.exists(metrics_file):
            try:
                with open(metrics_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {}
        
        counts = data.setdefault("counts", {
            "stage1_detected": 0,
            "pass1_approved": 0,
            "pass2_vetoed": 0,
            "executed": 0
        })
        
        if event_type in counts:
            counts[event_type] += 1
            
        logs = data.setdefault("recent_events", [])
        now_str = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%Y-%m-%d %H:%M:%S WIB")
        logs.append({
            "time": now_str,
            "event": event_type,
            "symbol": sym,
            "setup": setup,
            "details": details or {}
        })
        data["recent_events"] = logs[-100:]
        
        s1 = counts["stage1_detected"]
        p1 = counts["pass1_approved"]
        v2 = counts["pass2_vetoed"]
        ex = counts["executed"]
        data["veto_rate_pct"] = round((v2 / p1 * 100) if p1 > 0 else 0.0, 2)
        data["execution_rate_pct"] = round((ex / s1 * 100) if s1 > 0 else 0.0, 2)
        
        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        pass


_known_pending_orders = {}  # ticket -> {"symbol": sym, "type": ptype, "price": price, "sl": sl, "tp": tp}
_recent_trihourly_opened = []  # List of dicts: {"time", "symbol", "signal", "lot", "entry_type"}
_recent_trihourly_vetoed = []  # List of dicts: {"time", "symbol", "setup", "veto_by", "reason"}

def _detect_filled_pending(scanner=None):
    """
    Tracks pending orders lifecycle:
    - If a tracked pending order converts to an open position -> trigger alert_pending_order_filled.
    - If a tracked pending order disappears without becoming an open position -> CANCELLED/EXPIRED:
      applies a 30-minute cooldown on the symbol in market scanner and sends Telegram notification.
    """
    global _known_pending_orders
    try:
        current_orders = connector.get_pending_orders() if hasattr(connector, 'get_pending_orders') else []
        cur_order_map = {o["ticket"]: o for o in current_orders}
        
        # 1. Register newly observed pending orders
        for t, o in cur_order_map.items():
            if t not in _known_pending_orders:
                _known_pending_orders[t] = {
                    "symbol": o.get("symbol", config.SYMBOL),
                    "type": o.get("type_str") or str(o.get("type", "pending")),
                    "price": o.get("price", 0.0),
                    "sl": o.get("sl", 0.0),
                    "tp": o.get("tp", 0.0),
                }

        # 2. Check disappearing orders
        disappeared_tickets = [t for t in _known_pending_orders if t not in cur_order_map]
        if not disappeared_tickets:
            return

        open_positions = connector.get_all_open_positions() if hasattr(connector, 'get_all_open_positions') else []
        open_tickets = {p["ticket"] for p in open_positions}
        
        # Check deals to see if disappeared tickets were filled into positions (MT5 deal IN maps order -> position_id)
        deal_order_to_pos = {}
        try:
            now_dt = datetime.now()
            from_epoch = int((now_dt - timedelta(days=2)).timestamp())
            to_epoch = int(now_dt.timestamp()) + 86400
            deals = mt5.history_deals_get(from_epoch, to_epoch) or []
            for d in deals:
                if d.entry == mt5.DEAL_ENTRY_IN and getattr(d, "order", 0):
                    deal_order_to_pos.setdefault(d.order, d.position_id)
        except Exception as ed:
            print(f"[PENDING DEAL LOOKUP WARNING] {ed}")

        for t in disappeared_tickets:
            info = _known_pending_orders.pop(t, {})
            sym = info.get("symbol", config.SYMBOL)
            ptype = str(info.get("type", "pending"))
            price = info.get("price", 0.0)
            pos_id = deal_order_to_pos.get(t)

            # Check if this ticket exists in open positions or was filled via broker deal
            if pos_id or t in open_tickets:
                resolved_pos_id = pos_id or t
                print(f" {UI.GREEN}[PENDING FILLED] Pending order #{t} {sym} ({ptype}) ter-fill menjadi posisi aktif #{resolved_pos_id}!{UI.RST}")
                try:
                    tg.alert_pending_order_filled(t, sym, ptype, price, pos_id=resolved_pos_id, sl_price=info.get("sl"), tp_price=info.get("tp"))
                except Exception as e:
                    print(f"[PENDING ALERT ERROR] {e}")
            else:
                # Cancelled or expired -> Apply 30-minute cooldown
                print(f" {UI.YELLOW}[PENDING CANCELLED/EXPIRED] Pending order #{t} {sym} ({ptype}) dibatalkan / expired. Mengaktifkan cooldown 30 menit.{UI.RST}")
                if scanner is not None and hasattr(scanner, "mark_symbol_cancelled"):
                    scanner.mark_symbol_cancelled(sym, cooldown_seconds=1800)
                try:
                    tg.alert_pending_order_cancelled(t, sym, ptype, price, reason="Expired / Dibatalkan User (Cooldown 30m Aktif)")
                except Exception as e:
                    print(f"[PENDING ALERT ERROR] {e}")
    except Exception as e:
        print(f"[PENDING SYNC ERROR] {e}")


def run_scanner_trading_cycle(cand, risk):
    """
    Stage 2 Funnel Execution:
    Triggered when Stage 1 Python Quant Scanner identifies an A+ setup on one of 22 pairs.
    Fetches live candles, runs 2-Pass Cross-Examination Jury, evaluates consensus, and dispatches MT5 order.
    """
    sym = cand.symbol
    tf_str = getattr(cand, "timeframe", "H1")
    print("\n" + render_candidate_alert_box(cand))
    record_funnel_event("stage1_detected", sym=sym, setup=cand.setup_type)
    
    # 1. Check risk gates for candidate symbol
    can_trade_ok, risk_msg = risk.can_trade(sym)
    if not can_trade_ok:
        print(f" {UI.YELLOW}[RISK GATE] Trade untuk {sym} [{tf_str}] tidak diizinkan oleh Risk Engine ({risk_msg}).{UI.RST}")
        return False
    
    # 2. Fetch live candles (M15 & M5 Micro Microscope) from MT5
    try:
        from config import mt5
        rates_m15 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M15, 0, 17) # 16 completed bars (~4 hours)
        rates_m5 = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 25)   # 24 completed bars (~2 hours)
        
        def _fmt(rates):
            if rates is None or len(rates) == 0:
                return None
            lines = []
            for r in rates:
                t_s = connector.format_time(r["time"]) if hasattr(connector, "format_time") else str(r["time"])
                lines.append(f"- [{t_s}] Open: {r['open']:.5f} | High: {r['high']:.5f} | Low: {r['low']:.5f} | Close: {r['close']:.5f}")
            return "\n".join(lines)
            
        m15_str = _fmt(rates_m15[:-1]) if rates_m15 is not None and len(rates_m15) > 1 else None
        m5_str = _fmt(rates_m5[:-1]) if rates_m5 is not None and len(rates_m5) > 1 else None
    except Exception as e:
        m15_str, m5_str = None, None
        
    # 3. Call 2-Pass Sequential Cross-Examination Jury
    old_sym = config.SYMBOL
    config.SYMBOL = sym
    try:
        decisions = llm.get_multi_llm_decisions_for_candidate(
            cand,
            recent_m15_str=m15_str,
            recent_m5_str=m5_str
        )
        result = consensus.calculate_consensus(decisions, candidate=cand)
        
        trade_signal = result.get("signal", "HOLD")
        
        # Check if Pass 1 approved vs Pass 2 vetoed
        if decisions.get("OpenAI", {}).get("signal") in ("BUY", "SELL") or decisions.get("Gemini", {}).get("signal") in ("BUY", "SELL"):
            record_funnel_event("pass1_approved", sym=sym, setup=cand.setup_type)
            
        if trade_signal == "HOLD" and (decisions.get("DeepSeek", {}).get("veto") or "VETO" in (result.get("reason") or "")):
            record_funnel_event("pass2_vetoed", sym=sym, setup=cand.setup_type, details={"reason": result.get("reason")})
            _recent_trihourly_vetoed.append({
                "time": datetime.now(_WIB).strftime("%H:%M"),
                "symbol": sym,
                "setup": cand.setup_type,
                "veto_by": "Devil's Advocate (DeepSeek)" if decisions.get("DeepSeek", {}).get("veto") else "Hard Risk Veto",
                "reason": result.get("reason", "Critical Risk Detected")
            })
            print(f" {UI.RED}[PASS 2 VETO] Trade {sym} di-veto oleh DeepSeek Devil's Advocate: {result.get('reason')}{UI.RST}")
            
            # CEGAH TOKEN BLEEDING: Cooldown 15 menit agar tidak di-scan berulang
            try:
                from src.analytics.market_scanner import MarketScanner
                scanner_inst = getattr(MarketScanner, '_instance', None)
                if scanner_inst:
                    scanner_inst.mark_symbol_cancelled(sym, cooldown_seconds=900)
                    print(f" {UI.YELLOW}[COOLDOWN] {sym} diistirahatkan 15 menit setelah VETO.{UI.RST}")
            except Exception:
                pass
            
            return False
            
        elif trade_signal == "HOLD":
            # CEGAH TOKEN BLEEDING: Cooldown 15 menit untuk normal HOLD / Split vote
            try:
                from src.analytics.market_scanner import MarketScanner
                scanner_inst = getattr(MarketScanner, '_instance', None)
                if scanner_inst:
                    scanner_inst.mark_symbol_cancelled(sym, cooldown_seconds=900)
                    print(f" {UI.YELLOW}[COOLDOWN] {sym} diistirahatkan 15 menit setelah HOLD.{UI.RST}")
            except Exception:
                pass
            
            return False

        if trade_signal in ("BUY", "SELL"):
            # Execute trade order on MT5 (pending or market)
            sl_points = result.get("sl_points")
            tp_points = result.get("tp_points")
            entry_type = result.get("entry_type") or "market"
            entry_price = result.get("entry_price")
            
            tick_live = connector.get_current_tick(sym)
            if not tick_live:
                return False
                
            point = tick_live.get("point", 0.00001)
            ref_price = tick_live["ask"] if trade_signal == "BUY" else tick_live["bid"]
            
            # Stale price protection (~8s multi-LLM jury latency guard)
            # A5 FIX: baseline drift = harga pasar saat setup di-scan (bukan anchor limit trigger_price)
            drift_ref = getattr(cand, "scan_mid", 0.0) or cand.trigger_price
            price_diff_pts = abs(ref_price - drift_ref) / point if point > 0 else 0
            max_allowed_drift = (cand.current_atr_pts or 100) * 0.20
            if entry_type == "market" and price_diff_pts > max_allowed_drift:
                agree_models = result.get("agreeing_models_str") or ", ".join(result.get("agreeing_models") or [])
                print(f"\n {UI.YELLOW}{UI.BOLD}╔═══════════════════════════════════════════════════════════════════════════════════════╗{UI.RST}")
                print(f" {UI.YELLOW}{UI.BOLD}  ║ [STALE PRICE GUARD] EKSEKUSI MARKET {sym} {trade_signal.upper()} DIBATALKAN!          ║{UI.RST}")
                print(f" {UI.YELLOW}{UI.BOLD}  ║ • Pergeseran Harga : {price_diff_pts:.1f} pts (Batas Toleransi: {max_allowed_drift:.1f} pts max drift)║{UI.RST}")
                print(f" {UI.YELLOW}{UI.BOLD}  ║ • Alasan           : Harga telah bergeser saat AI berdiskusi. Batalkan agar tidak chase harga!║{UI.RST}")
                print(f" {UI.YELLOW}{UI.BOLD}  ╚═══════════════════════════════════════════════════════════════════════════════════════╝{UI.RST}\n")
                tg.alert_trade_aborted(
                    symbol=sym,
                    signal=trade_signal,
                    reason_code="STALE_PRICE_DRIFT",
                    details=f"Harga bergeser {price_diff_pts:.1f} pts melebihi toleransi {max_allowed_drift:.1f} pts saat 3 AI berdiskusi.",
                    price_drift_pts=price_diff_pts,
                    max_drift_pts=max_allowed_drift,
                    confidence=result.get("confidence", 0.0),
                    models=agree_models
                )
                return False
            
            action_tier_val = getattr(cand, "action_tier", "FULL_ALLOW")
            setup_grade_val = getattr(cand, "setup_grade", "GRADE_A")
            sl_points, tp_points, sltp_ok, sltp_reason = consensus._apply_sltp_rules(
                sl_points, tp_points, symbol=sym, action_tier=action_tier_val, setup_grade=setup_grade_val, candidate=cand
            )
            if not sltp_ok:
                print(f" {UI.RED}[!] Trade {sym} Dibatalkan (SL/TP Rules): {sltp_reason}{UI.RST}")
                tg.alert_trade_aborted(
                    symbol=sym,
                    signal=trade_signal,
                    reason_code="SLTP_RULES_INVALID",
                    details=sltp_reason,
                    confidence=result.get("confidence", 0.0),
                    models=result.get("agreeing_models_str") or ", ".join(result.get("agreeing_models") or [])
                )
                return False
                
            # High Confidence Multi-Position sizing:
            # If 3/3 AI agree and confidence >= 0.80 and at least 2 slots remaining in MT5 capacity -> Open 2 positions (+25% boost per pos)
            # CRITICAL: If action_tier == "TP1_ONLY_SCALP", enforce single position only (no 2nd extended runner against macro)
            positions = config.mt5.positions_get() if hasattr(config.mt5, "positions_get") else []
            orders = config.mt5.orders_get() if hasattr(config.mt5, "orders_get") else []
            total_active = len(positions or []) + len(orders or [])
            max_positions = config.get_max_open_positions()
            remaining_slots = max(0, max_positions - total_active)
            
            agreeing_count = result.get("agreeing_count", 0)
            avg_conf = result.get("confidence", 0.0)
            confluence_tier = result.get("confluence_tier", "STANDARD_TRADE")
            sizing_mult = result.get("sizing_multiplier", 1.0)
            is_split_tix = result.get("is_split_ticket", False)
            tp_mode = result.get("tp_mode", "STANDARD_TP1_TP2")

            num_positions = 2 if (is_split_tix and remaining_slots >= 2 and action_tier_val not in ("TP1_ONLY_SCALP", "REDUCED_SCALP")) else 1
            
            base_lot = risk.get_effective_lot_size(sl_points, split_count=1, symbol=sym, action_tier=action_tier_val, sizing_multiplier=sizing_mult)
            if num_positions == 2:
                effective_lot = round(base_lot * 0.625, 2)
                si = config.mt5.symbol_info(sym) if hasattr(config.mt5, "symbol_info") else None
                min_v = getattr(si, "volume_min", 0.01) if si else 0.01
                effective_lot = max(effective_lot, min_v)
                print(f" {UI.GREEN}[2D CONFLUENCE: {confluence_tier}] 3 AI sepakat {trade_signal} (Score {avg_conf*100:.1f}%)! Membuka 2 posisi ({effective_lot} lot each, +25% boost per pos) [Mode: {tp_mode}]!{UI.RST}")
            else:
                effective_lot = base_lot
                print(f" {UI.GREEN}[2D CONFLUENCE: {confluence_tier}] Trade {trade_signal} ({effective_lot} lot, multiplier x{sizing_mult:.2f}) [Mode: {tp_mode}]!{UI.RST}")
            
            # Final Pre-Dispatch Risk Check (guards against positions opened while LLM was reasoning)
            can_trade_ok, risk_msg = risk.can_trade(sym)
            if not can_trade_ok:
                print(f" {UI.YELLOW}[PRE-DISPATCH BLOCKED] Trade {sym} dibatalkan: {risk_msg}{UI.RST}")
                tg.alert_trade_aborted(
                    symbol=sym,
                    signal=trade_signal,
                    reason_code="PRE_DISPATCH_RISK_BLOCKED",
                    details=risk_msg,
                    confidence=result.get("confidence", 0.0),
                    models=result.get("agreeing_models_str") or ", ".join(result.get("agreeing_models") or [])
                )
                return False

            # If pending order
            if getattr(config, "PENDING_ORDERS_ENABLED", False) and entry_type != "market" and entry_price:
                for i in range(num_positions):
                    pos_tp_pts = int(tp_points * 1.20) if i == 1 else tp_points
                    p_sl_price = entry_price - (sl_points * point) if trade_signal == "BUY" else entry_price + (sl_points * point)
                    p_tp_price = (entry_price + (pos_tp_pts * point)) if trade_signal == "BUY" else (entry_price - (pos_tp_pts * point))
                    
                    pending_res = connector.send_pending_order(
                        symbol=sym,
                        entry_type=entry_type,
                        entry_price=entry_price,
                        lot=effective_lot,
                        sl_points=sl_points,
                        tp_points=pos_tp_pts,
                        comment=f"JURY {cand.setup_type[:6]} P{i+1}",
                        sl_price=p_sl_price,
                        tp_price=p_tp_price,
                        expiration_minutes=config.get_pending_order_expiry_minutes()
                    )
                    if pending_res.get("status") == "SUCCESS":
                        if config.DRY_RUN:
                            print(f" {UI.YELLOW}[STAGE 2 JURY DRY RUN] Simulasi Pending #{i+1} {entry_type.upper()} @ {entry_price} tercatat untuk {sym} (TIDAK kirim order ke MT5)!{UI.RST}")
                        else:
                            print(f" {UI.GREEN}[STAGE 2 JURY SUCCESS] Pending #{i+1} {entry_type.upper()} @ {entry_price} terpasang untuk {sym} (Ticket #{pending_res.get('ticket')})!{UI.RST}")
                        print(f" [ZCE-AUDIT] Ticket #{pending_res.get('ticket')} | {sym} {entry_type.upper()} | Entry={entry_price} SL={p_sl_price} ({sl_points}pts) TP={p_tp_price} ({pos_tp_pts}pts) | ATR={cand.current_atr_pts:.1f}pts | F1={getattr(cand, 'key_support', 0.0)} C1={getattr(cand, 'key_resistance', 0.0)}")
                        risk.record_trade_opened()
                        record_funnel_event("executed", sym=sym, setup=cand.setup_type, details={"ticket": pending_res.get("ticket"), "type": entry_type})
                        _recent_trihourly_opened.append({
                            "time": datetime.now(_WIB).strftime("%H:%M"),
                            "symbol": sym,
                            "signal": trade_signal,
                            "lot": effective_lot,
                            "entry_type": entry_type
                        })
                        tg.alert_pending_order_placed(
                            symbol=sym,
                            entry_type=entry_type,
                            ticket=pending_res.get("ticket"),
                            entry_price=entry_price,
                            lot=effective_lot,
                            sl_points=sl_points,
                            tp_points=pos_tp_pts,
                            sl_price=p_sl_price,
                            tp_price=p_tp_price,
                            models=result.get("agreeing_models_str") or ", ".join(result.get("agreeing_models") or []),
                            confidence=result.get("confidence", 0.0),
                            setup=f"{cand.setup_type} ({cand.timeframe}) [Pos #{i+1}]",
                            reason=result.get("reason", ""),
                            invalidation=f"SL: {p_sl_price}",
                            expiration_minutes=config.get_pending_order_expiry_minutes(),
                        )
                return True
            
            # Otherwise Market Order
            for i in range(num_positions):
                pos_tp_pts = int(tp_points * 1.20) if i == 1 else tp_points
                sl_price = ref_price - (sl_points * point) if trade_signal == "BUY" else ref_price + (sl_points * point)
                tp_price = (ref_price + (pos_tp_pts * point)) if trade_signal == "BUY" else (ref_price - (pos_tp_pts * point))
                
                order_res = connector.send_trade_order(
                    symbol=sym,
                    action=trade_signal,
                    lot=effective_lot,
                    sl_points=sl_points,
                    tp_points=pos_tp_pts,
                    comment=f"JURY {cand.setup_type[:6]} P{i+1}",
                    sl_price=sl_price,
                    tp_price=tp_price,
                    atr_h1_pts=cand.current_atr_pts,
                )
                if order_res.get("status") == "SUCCESS":
                    if config.DRY_RUN:
                        print(f" {UI.YELLOW}[STAGE 2 JURY DRY RUN] Simulasi Market #{i+1} {trade_signal} tercatat untuk {sym} (Lot: {effective_lot}, TIDAK kirim order ke MT5)!{UI.RST}")
                    else:
                        print(f" {UI.GREEN}[STAGE 2 JURY SUCCESS] Market #{i+1} {trade_signal} dieksekusi untuk {sym} (Ticket #{order_res.get('ticket')}, Lot: {effective_lot})!{UI.RST}")
                    print(f" [ZCE-AUDIT] Ticket #{order_res.get('ticket')} | {sym} {trade_signal} | Entry={ref_price} SL={sl_price} ({sl_points}pts) TP={tp_price} ({pos_tp_pts}pts) | ATR={cand.current_atr_pts:.1f}pts | F1={getattr(cand, 'key_support', 0.0)} C1={getattr(cand, 'key_resistance', 0.0)}")
                    risk.record_trade_opened()
                    record_funnel_event("executed", sym=sym, setup=cand.setup_type, details={"ticket": order_res.get("ticket"), "type": "market"})
                    _recent_trihourly_opened.append({
                        "time": datetime.now(_WIB).strftime("%H:%M"),
                        "symbol": sym,
                        "signal": trade_signal,
                        "lot": effective_lot,
                        "entry_type": "market"
                    })
                    tg.alert_trade_opened(
                        trade_signal, effective_lot, sl_points, pos_tp_pts,
                        recovery_mode=risk.is_recovery_mode,
                        reason=result.get("reason", ""),
                        ticket=order_res.get("ticket"),
                        entry_price=ref_price,
                        symbol=sym,
                        setup=f"{cand.setup_type} ({cand.timeframe}) [Pos #{i+1}]",
                        sl_price=sl_price,
                        tp_price=tp_price,
                        models=result.get("agreeing_models_str") or ", ".join(result.get("agreeing_models") or []),
                        confidence=result.get("confidence", 0.0),
                    )
            return True
        else:
            print(f" {UI.DIM}[STAGE 2 JURY] Setup {cand.setup_type} pada {sym} DITOLAK/HOLD oleh sidang konsensus.{UI.RST}")
            return False
    finally:
        config.SYMBOL = old_sym


def execute_cli_macro_command(symbol_arg: str):
    """
    Kalkulasi dan tampilkan Top-Down Macro Strategic Directive di CLI Terminal.
    Jika symbol_arg == 'all', tampilkan tabel ringkasan 26 simbol FX + BTC.
    Jika symbol_arg == specific symbol, tampilkan kartu detail bergaya ANSI Cyberpunk.
    """
    from src.analytics.macro_strategic_engine import macro_strategic_engine
    from src.core.cli_theme import render_macro_directive_card, render_macro_summary_table
    
    print(f"\n {UI.CYAN}[MT5 CONNECT]{UI.RST} Menginisialisasi koneksi MT5 untuk kalkulasi Macro Strategic Engine...")
    if not connector.initialize_mt5():
        print(f" {UI.RED}[ERROR]{UI.RST} Gagal terhubung ke terminal MT5.")
        return
    
    sym_clean = (symbol_arg or "all").strip().upper()
    if sym_clean == "ALL":
        symbols = config.get_scanner_symbols()
        if "BTCUSD.c" not in symbols and "BTCUSD" not in symbols:
            symbols = symbols + ["BTCUSD.c"]
        print(f" {UI.GREEN}[CALCULATING]{UI.RST} Menghitung 6-TF Native Directive untuk {len(symbols)} simbol...\n")
        directives = []
        for s in symbols:
            valid_s = connector.get_valid_trade_symbol(s)
            d = macro_strategic_engine.get_directive(valid_s, mt5_connector=connector)
            directives.append(d)
        print(render_macro_summary_table(directives))
    else:
        valid_s = connector.get_valid_trade_symbol(sym_clean)
        print(f" {UI.GREEN}[CALCULATING]{UI.RST} Menghitung 6-TF Native Directive untuk {valid_s}...\n")
        d = macro_strategic_engine.get_directive(valid_s, mt5_connector=connector)
        print(render_macro_directive_card(d))
    print("")


def main():
    # Apply CLI overrides (sesi saja) sebelum bot jalan
    cli_applied, skip_prompt = parse_cli_overrides()

    # Eksekusi on-demand CLI Macro Inspector jika diminta flag --macro
    macro_arg = getattr(config, "CLI_MACRO_ARG", None)
    if macro_arg is not None:
        execute_cli_macro_command(macro_arg)
        return


    # Set active symbol now so the banner shows the symbol that will be traded
    config.refresh_active_symbol()


    # Setup TeeLogger to save all terminal logs from here on (clean logs, no interactive menus)
    if getattr(config, "LOG_FILE", None):
        tee_logger = TeeLogger(config.LOG_FILE)
        sys.stdout = tee_logger
        sys.stderr = tee_logger
        print(f"Logging aktif. Semua output akan disimpan di: {config.LOG_FILE}")

    # Tampilkan override CLI kalau ada
    if cli_applied:
        print(f" {UI.YELLOW}[CLI OVERRIDE]{UI.RST} " + " | ".join(cli_applied))
        print(f"{UI.DIM}------------------------------------------------------------------------{UI.RST}")

    _tf_map = {mt5.TIMEFRAME_M5: "M5", mt5.TIMEFRAME_M15: "M15", mt5.TIMEFRAME_M30: "M30", mt5.TIMEFRAME_H1: "H1"}
    tf_name = _tf_map.get(config.get_timeframe(config.SYMBOL), "?")

    if config.SCANNER_MODE:
        print(render_scanner_banner(
            account_info=getattr(config, "MT5_LOGIN", None),
            is_live=not config.DRY_RUN,
            total_symbols=len(config.get_scanner_symbols()),
            account_mode=getattr(config, "MT5_ACCOUNT_MODE", "live")
        ))
        print(f"  {UI.BOLD}Architecture:{UI.RST} {UI.PURPLE}2-STAGE QUANT FUNNEL{UI.RST} (Stage 1: Fast Radar 60s | Stage 2: 3-LLM Jury)")
        print(f"  {UI.BOLD}Universe    :{UI.RST} {UI.CYAN}{len(config.get_scanner_symbols())} Simbol (26 Pasangan FX Terkurasi | Weekend: BTCUSD H1 {config.RISK_PERCENT_BTC}% Risk){UI.RST}")
    else:
        print(render_banner(
            account_info=getattr(config, "MT5_LOGIN", None),
            symbol=config.SYMBOL,
            tf=tf_name,
            mode=config.TRADING_MODE,
            is_live=not config.DRY_RUN
        ))

        # Info Trading Mode
        if config.TRADING_MODE in ("xau_pairs", "pairs", "fx_pairs"):
            pool = config.get_rotation_pool()
            print(f"  {UI.BOLD}Pool Scan   :{UI.RST} {UI.CYAN}{' -> '.join(pool)}{UI.RST} ({len(pool)} simbol)")
            if getattr(config, "DYNAMIC_SESSION_TIMEFRAME", False):
                print(f"  {UI.BOLD}Timeframe   :{UI.RST} FX Pairs: Dynamic ({config.ASIA_TIMEFRAME} Tokyo / {config.LONDON_NY_TIMEFRAME} London-NY) | BTC (H1 Weekend) - Smart Rotation")
            else:
                print(f"  {UI.BOLD}Timeframe   :{UI.RST} FX Pairs ({config.TIMEFRAME}) | BTC (H1 Weekend) - Smart Rotation")
        else:
            print(f"  {UI.BOLD}Trading Mode:{UI.RST} {UI.CYAN}SINGLE SYMBOL ONLY{UI.RST}")

    if config.TP_SL_RULES != "LLM":
        sltp_desc = f"{config.TP_SL_RULES} (force semua)"
    else:
        sltp_desc = f"FX: LLM Structure (floor {config.LLM_FX_FLOOR_ATR_MULT}xATR, min R:R {config.LLM_MIN_RR_RATIO}) | BTC: Dynamic ATR (H1)"

    loss_desc = f"{getattr(config, 'MAX_DAILY_LOSS_PERCENT', 4.0)}%"
    print(f"  {UI.BOLD}Risk & Rules:{UI.RST} FX Risk {config.RISK_PERCENT_FX}% | BTC Weekend Risk {config.RISK_PERCENT_BTC}% (Max 2 Pos) | SL/TP: {sltp_desc} | Max Daily Loss: {loss_desc} | Target Profit: {config.DAILY_PROFIT_TARGET_PERCENT}%")
    print(f"  {UI.BOLD}Proteksi    :{UI.RST} Trailing [{'ON' if config.TRAILING_STOP_ENABLED else 'OFF'} ({int(config.TRAILING_ACTIVATION_TP_PCT*100)}% TP)], BEP [{'ON' if config.BREAK_EVEN_ENABLED else 'OFF'} ({int(config.BREAK_EVEN_TRIGGER_TP_PCT*100)}% TP)], Partial [{'ON' if config.PARTIAL_CLOSE_ENABLED else 'OFF'} ({int(config.PARTIAL_CLOSE_TRIGGER_TP_PCT*100)}% TP)], Recovery [{'ON' if config.RECOVERY_MODE_ENABLED else 'OFF'}]")
    print(f"{UI.DIM}------------------------------------------------------------------------{UI.RST}")

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
        
    acc_info = connector.get_account_info()
    acc_mode_str = f" [{config.MT5_ACCOUNT_MODE.upper()}]" if hasattr(config, "MT5_ACCOUNT_MODE") else ""
    acc_num = (acc_info.get("login") if acc_info else None) or getattr(config, "MT5_LOGIN", "")
    acc_login = f"Login #{acc_num}{acc_mode_str}" if acc_num else "Connected"
    print(f"\n {UI.GREEN}[OK]{UI.RST} Terhubung ke MT5 Terminal ({acc_login})")

    
    # Send startup alert (in background thread so terminal boots instantly)
    import threading
    threading.Thread(target=tg.alert_bot_started, daemon=True).start()

    # Start 2-Way Interactive Telegram Bot Controller (Long-Polling Listener)
    try:
        from src.core import telegram_bot
        telegram_bot.start_telegram_listener()
    except Exception as e:
        print(f" [TELEGRAM BOT LISTENER ERROR] {e}")
    
    # Initialize 2-Stage Quant Funnel Market Scanner if enabled
    scanner = None
    _last_radar_scan = 0.0
    _last_radar_log_time = 0.0
    _last_radar_state_signature = ""
    _RADAR_LOG_HEARTBEAT_SEC = 900.0  # Heartbeat scroll buffer tiap 15 menit jika status statis
    _last_radar_status = "Standby (60s loop)"
    _radar_anim_idx = 0
    _last_hourly_recap_hour = datetime.now(_WIB).hour
    if config.SCANNER_MODE:
        try:
            scanner = MarketScanner()
            scanner.update_macro_context(connector, force=True)
            acc_info = connector.get_account_info()
            open_pos = connector.get_all_open_positions()
            print("\n" + render_hacker_bento_hud(
                macro_cache=scanner.macro_cache,
                account_info=acc_info,
                daily_pnl=risk.get_daily_pnl(),
                open_positions=open_pos,
                active_models=config.active_ai_model_names()
            ) + "\n")
        except Exception as e:
            print(f"[STARTUP SCANNER WARNING] {e}\n")

    _last_known_macro_states = {}
    if config.SCANNER_MODE and scanner is not None and scanner.macro_cache:
        for sym_k, m_v in scanner.macro_cache.items():
            p_st = m_v.get('permission_state', 'WAIT')
            w_st = m_v.get('wave_state', '')
            s_dir = m_v.get('strat_dir')
            b_st = s_dir.primary_execution_directive if s_dir else ("BULLISH" if m_v.get('is_bull') else ("BEARISH" if m_v.get('is_bear') else "NEUTRAL"))
            _last_known_macro_states[sym_k] = (p_st, w_st, b_st)

    last_candle_time = None
    startup_run = True
    last_symbol = config.SYMBOL
    _last_day = None  # deteksi ganti hari (WIB) -> kirim ringkasan harian otomatis

    try:
        while True:
            # =================================================================
            #  EVERY TICK (3s): Manage open positions + weekend check
            # =================================================================
            try:
                # Day-change detection: kalau tanggal WIB berubah, kirim ringkasan
                # harian (rich) sebelum reset, biar laporan tiap hari lengkap.
                try:
                    wib_now = datetime.now(_WIB)
                    today_str = wib_now.strftime("%Y-%m-%d")
                    if _last_day is None:
                        _last_day = today_str
                    elif today_str != _last_day:
                        print(f"\n[DAY CHANGE] {_last_day} -> {today_str}. Kirim ringkasan harian...")
                        daily_pnl = risk.get_daily_pnl()
                        closed_deals = connector.get_closed_positions_today()
                        open_pos = connector.get_all_open_positions()
                        tg.alert_daily_summary(
                            daily_pnl, len(closed_deals), risk.get_status_summary(),
                            closed_deals=closed_deals, open_positions=open_pos,
                            reason="Ganti Hari",
                        )
                        _last_day = today_str
                except Exception as e:
                    print(f"[DAY CHANGE ERROR] {e}")

                # Trailing stop + break-even + partial close + stagnation
                position_manager.manage_all_positions()

                # Sync siklus pending order
                try:
                    _detect_filled_pending(scanner=scanner)
                except Exception as e:
                    print(f"[PENDING SYNC ERROR] {e}")

                # Detect positions closed by MT5 in real time
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
                except Exception as e:
                    print(f"[SYNC CLOSED POSITIONS ERROR] {e}")
            except Exception as e:
                print(f"[LOOP 3S ERROR] {e}")

            # =================================================================
            #  EVERY 60s: Fast Execution Radar Scan (Stage 1 -> Stage 2)
            # =================================================================
            now_epoch = time.time()
            if config.SCANNER_MODE and scanner is not None:
                if now_epoch - _last_radar_scan >= config.RADAR_SCAN_INTERVAL_SECONDS:
                    _last_radar_scan = now_epoch
                    try:
                        candidates = scanner.scan_all(connector)
                        if candidates:
                            for cand in candidates:
                                run_scanner_trading_cycle(cand, risk)
                        _last_radar_status = f"Scanned {len(scanner.macro_cache)} pairs ({len(candidates)} setups)"

                        # Print informative scan summary to terminal scroll buffer on state change, setup trigger, or 15m heartbeat
                        if scanner.macro_cache:
                            _go_s = [s.replace("-ECNc", "").replace(".c", "") for s, m in scanner.macro_cache.items() if m.get('permission_state') == 'GO']
                            _arm_s = [(s.replace("-ECNc", "").replace(".c", ""), m.get('dealing_range_pos', 0.5)) for s, m in scanner.macro_cache.items() if m.get('permission_state') == 'ARM']
                            _lock_cnt = sum(1 for m in scanner.macro_cache.values() if m.get('permission_state') == 'LOCK')
                            _watch_cnt = sum(1 for m in scanner.macro_cache.values() if m.get('permission_state') in ('WATCH', 'WAIT'))

                            _arm_s.sort(key=lambda x: min(x[1], 1.0 - x[1]))
                            _top_siaga = [f"{s}({int(dr*100)}%)" for s, dr in _arm_s[:4]]
                            _siaga_str = f" │ Top Siaga: {', '.join(_top_siaga)}" if _top_siaga else ""

                            _curr_signature = f"{len(_go_s)}_{len(_arm_s)}_{_watch_cnt}_{_lock_cnt}_{','.join(_top_siaga)}"
                            _state_changed = (_curr_signature != _last_radar_state_signature)
                            _time_for_heartbeat = (now_epoch - _last_radar_log_time >= _RADAR_LOG_HEARTBEAT_SEC)

                            t_now_str = time.strftime('%H:%M:%S')
                            if candidates:
                                print(f" {UI.GREEN}[{t_now_str} RADAR]{UI.RST} {len(candidates)} SETUP TERDETEKSI! Diteruskan ke 3-LLM Jury.")
                                _last_radar_log_time = now_epoch
                                _last_radar_state_signature = _curr_signature
                            elif _state_changed or _time_for_heartbeat:
                                print(f" {UI.DIM}[{t_now_str} RADAR]{UI.RST} 26 pairs dipindai: 0 setup lolos filter ({UI.GREEN}{len(_go_s)} GO{UI.RST}, {UI.CYAN}{len(_arm_s)} ARM{UI.RST}, {UI.YELLOW}{_watch_cnt} WATCH{UI.RST}, {UI.RED}{_lock_cnt} LOCK{UI.RST}){_siaga_str}")
                                _last_radar_log_time = now_epoch
                                _last_radar_state_signature = _curr_signature
                    except Exception as e:
                        _last_radar_status = f"Radar error: {e}"
                        print(f" [RADAR ERROR] {e}")

                # Tri-Hourly Radar & Market Pulse Telegram Digest (00, 03, 06, 09, 12, 15, 18, 21 WIB)
                cur_hour_wib = datetime.now(_WIB).hour
                if config.ENABLE_HOURLY_RADAR_RECAP and (cur_hour_wib % 3 == 0) and cur_hour_wib != _last_hourly_recap_hour:
                    _last_hourly_recap_hour = cur_hour_wib
                    try:
                        acc_info = connector.get_account_info()
                        open_pos = connector.get_all_open_positions()
                        daily_pnl = risk.get_daily_pnl()
                        tg.alert_hourly_radar_recap(
                            scanner=scanner,
                            open_positions=open_pos,
                            today_pnl=daily_pnl,
                            risk=risk,
                            recent_opened=_recent_trihourly_opened,
                            recent_vetoed=_recent_trihourly_vetoed
                        )
                        _recent_trihourly_opened.clear()
                        _recent_trihourly_vetoed.clear()
                    except Exception as e:
                        print(f" [TRIHOURLY RECAP ERROR] {e}")

            # Show live status clock line in CLI every loop iteration
            now_str = time.strftime('%H:%M:%S')
            remaining_pause = risk.get_remaining_pause()
            pause_str = f" {UI.RED}[PAUSED: {remaining_pause}s]{UI.RST}" if remaining_pause > 0 else ""
            daily_pnl = risk.get_daily_pnl()
            pnl_str = UI.badge_pnl(daily_pnl)
            
            open_pos = connector.get_all_open_positions()
            pos_parts = []
            if open_pos:
                by_sym = {}
                for p in open_pos:
                    by_sym.setdefault(p.get("symbol", "?"), []).append(p)
                for sym, plist in sorted(by_sym.items()):
                    float_s = sum(x.get("profit", 0.0) for x in plist)
                    sym_clean = sym.replace("-ECNc", "").replace(".c", "")
                    count_str = f"({len(plist)})" if len(plist) > 1 else ""
                    badges = "".join(position_manager.get_ticket_status_badge(x.get("ticket")) for x in plist)
                    pos_parts.append(f"{sym_clean}{count_str}: {UI.badge_pnl(float_s)}{badges}")
                pos_str = f" | {UI.GRAY}pos:{UI.RST} " + " | ".join(pos_parts)
            else:
                pos_str = f" | {UI.GRAY}pos: No active pos{UI.RST}"

            _radar_frames = ["[RADAR] ◌", "[RADAR] ◔", "[RADAR] ◑", "[RADAR] ◕", "[RADAR] ●"]
            _radar_anim_idx = (_radar_anim_idx + 1) % len(_radar_frames)
            anim_icon = _radar_frames[_radar_anim_idx]
            n_active = len(scanner.macro_cache) if (scanner and scanner.macro_cache) else len(config.get_scanner_symbols())
            label_hdr = f"QUANT RADAR {anim_icon} ({n_active} Pairs)"
            
            # Live Radar States & Watchlist AoV Line
            radar_state_line = ""
            radar_watch_line = ""
            if config.SCANNER_MODE and scanner and scanner.macro_cache:
                _go_cnt = 0
                _arm_list = []
                _lock_cnt = 0
                _watch_cnt = 0
                _disc_list = []
                _prem_list = []

                for sym_k, m_v in scanner.macro_cache.items():
                    perm = m_v.get('permission_state', 'WATCH')
                    clean_k = sym_k.replace("-ECNc", "").replace("-ECN", "").replace(".c", "")
                    dr_val = m_v.get('dealing_range_pos', 0.5)

                    if perm == "GO":
                        _go_cnt += 1
                    elif perm == "ARM":
                        _arm_list.append((clean_k, dr_val))
                    elif perm == "LOCK":
                        _lock_cnt += 1
                    else:
                        _watch_cnt += 1

                    if dr_val <= 0.30:
                        _disc_list.append((clean_k, dr_val))
                    elif dr_val >= 0.70:
                        _prem_list.append((clean_k, dr_val))

                radar_state_line = (
                    f"  ├─ {UI.GRAY}Status Radar:{UI.RST} "
                    f"{UI.GREEN}● {_go_cnt} GO{UI.RST} │ "
                    f"{UI.CYAN}◆ {len(_arm_list)} ARM{UI.RST} │ "
                    f"{UI.YELLOW}▲ {_watch_cnt} WATCH{UI.RST} │ "
                    f"{UI.RED}■ {_lock_cnt} LOCK{UI.RST} "
                    f"{UI.DIM}(Stage 1 Quant Funnel){UI.RST}"
                )

                _disc_list.sort(key=lambda x: x[1])
                _prem_list.sort(key=lambda x: -x[1])
                disc_str = ", ".join([f"{s}({int(dr*100)}%)" for s, dr in _disc_list[:3]]) if _disc_list else "None"
                prem_str = ", ".join([f"{s}({int(dr*100)}%)" for s, dr in _prem_list[:3]]) if _prem_list else "None"

                radar_watch_line = (
                    f"  ├─ {UI.GRAY}Radar Siaga :{UI.RST} "
                    f"🛒 Diskon: {UI.GREEN}{disc_str}{UI.RST} │ "
                    f"🏷️ Premium: {UI.RED}{prem_str}{UI.RST}"
                )

            csm_m15_line = ""
            try:
                from src.analytics.currency_strength import calculate_boitoki_csm
                _sc_m15, _ = calculate_boitoki_csm(config.mt5.TIMEFRAME_M15, lookback_bars=16)
                if _sc_m15:
                    _sorted_m15 = sorted(_sc_m15.items(), key=lambda x: x[1], reverse=True)
                    _m15_str = " > ".join([f"{c}({s:+.1f})" for c, s in _sorted_m15])
                    csm_m15_line = f"  ├─ {UI.GRAY}Arus CSM M15:{UI.RST} {UI.YELLOW}{_m15_str}{UI.RST}"
            except Exception:
                pass

            header_part = f"[{UI.BOLD}{label_hdr}{UI.RST} | {UI.CYAN}{now_str}{UI.RST}]{pause_str} | {UI.GREEN}{_last_radar_status}{UI.RST} | P/L Today: {pnl_str}"

            # Wrap daftar posisi ke baris terpisah
            try:
                cols = shutil.get_terminal_size((120, 24)).columns
            except Exception:
                cols = 120
            max_w = max(40, cols - 2)
            status_lines = [header_part]
            if radar_state_line:
                status_lines.append(radar_state_line)
            if radar_watch_line:
                status_lines.append(radar_watch_line)
            if csm_m15_line:
                status_lines.append(csm_m15_line)
            if open_pos:
                pos_wrapped = _wrap_positions(pos_parts, max_w, indent=f"  └─ {UI.GRAY}pos:{UI.RST} ")
                status_lines.extend(pos_wrapped)
            else:
                status_lines.append(f"  └─ {UI.GRAY}pos: No active pos (Flat / Ready){UI.RST}")

            sys.stdout.write(_render_status_lines(status_lines, _VT_OK))
            sys.stdout.flush()

            # Sleep 3 seconds between checks
            time.sleep(3)

    except KeyboardInterrupt:
        print("\n Bot dimatikan secara manual oleh user.")
    finally:
        daily_pnl = risk.get_daily_pnl()
        closed_deals = connector.get_closed_positions_today()
        open_pos = connector.get_all_open_positions()
        try:
            tg.alert_daily_summary(
                daily_pnl, len(closed_deals), risk.get_status_summary(),
                closed_deals=closed_deals, open_positions=open_pos,
                reason="Bot Mati",
            )
        except Exception:
            pass
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
