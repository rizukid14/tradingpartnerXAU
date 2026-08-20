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
from src.core.cli_theme import UI, render_banner
from src.analytics import position_manager, trade_evaluator, dynamic_config, forecast_engine, decision_memory
from src.analytics.macro_analyst import MacroAnalyst

import re
import shutil
import unicodedata

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


def _detect_filled_pending():
    """
    Deteksi pending order yang sudah ter-fill -> jadi posisi. Dicatat sebagai
    event 'filled' di state (AI proven: level entry tercapai). Dipanggil tiap
    cycle dari run_trading_cycle.

    Cara deteksi yang BENAR (fix 18 Agustus): di MT5, ticket pending order
    (order id) BEDA dengan ticket posisi saat ter-fill. Saat pending ter-fill,
    broker buat deal IN (entry) dengan field `order` = ticket pending asal dan
    `position_id` = ticket posisi baru. Jadi cocokkan lewat HISTORY DEALS:
    cari deal IN dengan order == ticket pending -> posisi baru terisi.
    (Sebelumnya: cocokkan ticket pending == ticket posisi -> TIDAK PERNAH cocok,
    jadi status filled tidak pernah terdeteksi walau posisi sudah kebuka.)
    """
    if not getattr(config, "PENDING_ORDERS_ENABLED", False):
        return
    try:
        state = _load_pending_state()
        events = state.get("pending", [])
        if not events:
            return
        # Pending yang tercatat 'placed' dan belum punya status terminal
        # (filled/expired/cancelled) - fix 18 Agustus: filter tiket yang sudah
        # punya event terminal biar tidak terdeteksi filled BERULANG tiap cycle.
        terminal_tickets = {
            e.get("ticket") for e in events
            if e.get("event") in ("filled", "expired", "cancelled_cap", "cancelled_contra") and e.get("ticket")
        }
        active_placed = {}
        for e in events:
            if e.get("event") == "placed" and e.get("ticket") and e["ticket"] not in terminal_tickets:
                active_placed[e["ticket"]] = e
        if not active_placed:
            return
        # Pending yang masih hidup di broker
        pendings = connector.get_pending_orders()
        live_tickets = {p["ticket"] for p in pendings}

        # Cari deal IN (entry) dalam 7 hari terakhir yang order-nya == pending ticket.
        # Pakai history_deals_get(range) biar dapat field `order` (ticket pending asal).
        from datetime import datetime, timedelta
        now_dt = datetime.now()
        from_epoch = int((now_dt - timedelta(days=7)).timestamp())
        to_epoch = int(now_dt.timestamp()) + 86400
        deals = mt5.history_deals_get(from_epoch, to_epoch) or []
        deal_order_to_pos = {}
        for d in deals:
            # deal IN dari pending order: entry == IN, dan field order != 0
            if d.entry == mt5.DEAL_ENTRY_IN and getattr(d, "order", 0):
                deal_order_to_pos.setdefault(d.order, d.position_id)

        changed = False
        for ticket, ev in list(active_placed.items()):
            if ticket in live_tickets:
                continue  # masih pending
            pos_id = deal_order_to_pos.get(ticket)
            if pos_id:
                # Pending hilang + ada deal IN dengan order == ticket -> FILLED
                ev2 = dict(ev)
                ev2["event"] = "filled"
                ev2["position_id"] = pos_id
                ev2["fill_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                events.append(ev2)
                changed = True
                print(f" {UI.tag('PENDING', UI.GREEN)} Pending #{ticket} {ev.get('type')} {ev.get('symbol')} "
                      f"@ {ev.get('price')} TER-FILL -> posisi #{pos_id}. (AI proven: level entry tercapai)")
            # kalau pending hilang tapi tidak ada deal IN = expired/cancelled manual
            # (sudah dicatat oleh MT5/expired handler, skip)
        if changed:
            state["pending"] = events[-500:]
            _save_pending_state(state)
    except Exception as e:
        print(f"[PENDING FILL DETECT ERROR] {e}")


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
        cancelled = [e for e in events if e.get("event") == "cancelled_contra"]
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
            parts.append(f"{m_name} {sig} {conf:.0f}%")
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
    """Kirim recap HOLD gabungan (satu pesan) kalau ada isi. Reset buffer."""
    global _hold_recap_lines
    if not _hold_recap_lines:
        return
    try:
        tg.alert_hold_recap(list(_hold_recap_lines))
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
                   help="Aturan SL/TP: 'ATR-Based' (gate per AI mode: single 1.25x/2.5x, dual 1.5x/3.0x, triple 1.75x/3.5x ATR, R:R 2:1) atau 'LLM' (bebas sesuai model, floor XAU/FX berbasis ATR: 1.1x/1.3x + R:R min 1.25)")
    p.add_argument("--pending-orders", choices=["on", "off"],
                   help="Pending order (LIMIT/STOP dari AI) on/off - default dari .env PENDING_ORDERS_ENABLED")
    p.add_argument("--account", choices=["live", "demo"],
                   help="Pilih akun MT5: 'live' (real money) atau 'demo' (virtual)")
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
    if args.pending_orders is not None:
        config.PENDING_ORDERS_ENABLED = (args.pending_orders == "on")
        applied.append(f"PENDING_ORDERS_ENABLED={config.PENDING_ORDERS_ENABLED}")
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
            return _scan_mode_label() if v == "xau_pairs" else "FX Pairs Only"
        if v is True:
            return "ON"
        if v is False:
            return "OFF"
        s = str(v)
        if attr == "config.TP_SL_RULES":
            s += (" (gate ATR per mode: 1.25/2.5, 1.5/3.0, 1.75/3.5)" if v == "ATR-Based" else f" (bebas, floor FX {config.LLM_FX_FLOOR_ATR_MULT}xATR H1, R:R min {config.LLM_MIN_RR_RATIO})" if v == "LLM" else "")
        return s


    def _scan_mode_label():
        """Label dinamis scan pool (8 simbol FX pairs)."""
        try:
            pool = config.get_rotation_pool()
            if len(pool) <= 1:
                base = f"FX Pairs -> {pool[0]}" if pool else "FX Pairs Only"
                return base
            return f"FX Pairs ({len(pool)} simbol)"
        except Exception:
            return "FX Pairs (8 simbol)"


    # (grup, label, attr, val) - dikelompokkan biar enak dibaca
    settings = [
        ("MODE & RISK", "Akun MT5", "config.MT5_ACCOUNT_MODE", _account_label()),
        ("MODE & RISK", "Mode", "config.DRY_RUN", "DRY RUN (sinyal saja)" if config.DRY_RUN else "LIVE (kirim order)"),
        ("MODE & RISK", "Scan Mode", "config.TRADING_MODE", _scan_mode_label() if config.TRADING_MODE == "xau_pairs" else "FX Pairs Only"),
        ("MODE & RISK", "Risk BTC (% equity)", "config.RISK_PERCENT_BTC", str(config.RISK_PERCENT_BTC)),
        ("MODE & RISK", "Risk FX (% equity)", "config.RISK_PERCENT_FX", str(config.RISK_PERCENT_FX)),
        ("LIMIT & FILTER", "Max Daily Loss ($)", "config.MAX_DAILY_LOSS_USD", str(config.MAX_DAILY_LOSS_USD)),
        ("LIMIT & FILTER", "Max Posisi", "config.MAX_OPEN_POSITIONS", str(config.MAX_OPEN_POSITIONS)),
        ("LIMIT & FILTER", "Cooldown (detik)", "config.TRADE_COOLDOWN_SECONDS", str(config.TRADE_COOLDOWN_SECONDS)),
        ("LIMIT & FILTER", "Spread Max BTC (pts)", "config.MAX_SPREAD_POINTS_BTC", str(config.MAX_SPREAD_POINTS_BTC)),
        ("KONSENSUS & AI", "Threshold BTC", "config.CONFIDENCE_CONSENSUS_THRESHOLD_BTC", str(config.CONFIDENCE_CONSENSUS_THRESHOLD_BTC)),
        ("KONSENSUS & AI", "OpenAI Model (24/7)", "config.OPENAI_MODEL", str(config.OPENAI_MODEL) + " (Full 24/7 All Sessions)"),
        ("KONSENSUS & AI", "Model Claude Slot", "config.CLAUDE_MODEL", str(config.CLAUDE_MODEL)),
        ("KONSENSUS & AI", "TP/SL Rules", "config.TP_SL_RULES",
         f"FX: LLM (floor {config.LLM_FX_FLOOR_ATR_MULT}xATR H1, R:R {config.LLM_MIN_RR_RATIO}) | BTC: ATR-Based (fix)" if config.TP_SL_RULES == "LLM"
         else str(config.TP_SL_RULES) + " (force semua, gate ATR per mode: 1.25/2.5, 1.5/3.0, 1.75/3.5)"),
        ("KONSENSUS & AI", "Quant (Hurst/MC)", "config.QUANT_ANALYSIS_ENABLED", "ON" if config.QUANT_ANALYSIS_ENABLED else "OFF"),
        ("KONSENSUS & AI", "Dynamic Config", "config.DYNAMIC_CONFIG_ENABLED", "ON" if config.DYNAMIC_CONFIG_ENABLED else "OFF"),
        ("KONSENSUS & AI", "Forecast Engine", "config.FORECAST_ENABLED", "ON" if config.FORECAST_ENABLED else "OFF"),
        ("KONSENSUS & AI", "AI Mode Policy", "config.AI_MODE_POLICY", str(config.AI_MODE_POLICY)),
        ("KONSENSUS & AI", "Memory (lessons/dec)", "config.MEMORY_CONTEXT_ENABLED", "ON" if config.MEMORY_CONTEXT_ENABLED else "OFF"),
        ("KONSENSUS & AI", "Pending Order (AI)", "config.PENDING_ORDERS_ENABLED", "ON" if config.PENDING_ORDERS_ENABLED else "OFF"),
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
        ("ANALISIS & NOTIF", "News Filter (Kalender)", "config.ECONOMIC_NEWS_ENABLED",
         "ON (fetch 6 jam, high-impact)" if config.ECONOMIC_NEWS_ENABLED else "OFF"),
        ("ANALISIS & NOTIF", "Telegram", "config.TELEGRAM_ENABLED", "ON" if config.TELEGRAM_ENABLED else "OFF"),
    ]

    while True:
        try:
            print("-" * 60)
            last_group = None
            for i, (group, label, attr, val) in enumerate(settings, 1):
                if group != last_group:
                    print(f" -- {group} --")
                    last_group = group
                print(f" {i:2d}. {label:<26} : {val}")
            print("-" * 60)
            print(" Ketik nomor utk ubah | 'start'/Enter = mulai | 'q' = batal")
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


def _prompt_startup_scan_mode(skip_prompt=False):
    """FASE 6 - CLI prompt mode scan startup:
    [1] Scan semua simbol sekarang (scan all now)
    [2] Scan sesuai timeframe masing-masing (default) - tunggu candle close tiap aset
    Non-interactive / timeout 10 detik -> default "timeframe".
    """
    global _STARTUP_SCAN_MODE
    if skip_prompt or not sys.stdin.isatty():
        return  # non-interactive (scheduler/redirect) -> default
    try:
        import msvcrt
    except ImportError:
        return
    print(f"\n{UI.CYAN}+-- [PILIHAN STARTUP SCAN MODE] -----------------------------------------+{UI.RST}")
    print(f"| {UI.BOLD}[1]{UI.RST} Scan Semua 8 Simbol Sekarang (Immediate Full Market Scan)            |")
    print(f"| {UI.BOLD}[2]{UI.RST} Scan Sesuai Timeframe (Smart Rotation: H1 / M30 - Default)           |")
    print(f"{UI.CYAN}+------------------------------------------------------------------------+{UI.RST}")
    sys.stdout.write(f"  {UI.YELLOW}Pilihan [2]{UI.RST} (10 detik timeout, Enter = default): ")
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
    mode_txt = "SCAN ALL 8 SYMBOLS NOW" if _STARTUP_SCAN_MODE == "all" else "SMART ROTATION (Tunggu Candle Close Tiap Aset)"
    print(f" {UI.GREEN}[+] Mode Terpilih:{UI.RST} {UI.BOLD}{mode_txt}{UI.RST}\n")


def run_trading_cycle():
    """Performs one full cycle: post-mortem (1x, aggregate all symbols) + full cycle
    per symbol in the rotation pool. Mode "xau": pool=[XAU]. Mode "xau_pairs": pool
    = [XAU, EURJPY, GBPCHF] - all symbols scanned ONLY when their specific timeframe
    forms a new candle (e.g., XAU every 5 mins, FX Pairs every 1 hour).
    """
    _reset_status_lines()
    sys.stdout.write(UI.clear_line())
    sys.stdout.flush()


    box_items = []
    # 2.5 Post-Mortem Trade Evaluation & Daily WinRate Summary (Run before any early exits)
    try:
        trade_evaluator.evaluator.check_and_evaluate_closed_trades()
        closed_deals = connector.get_closed_positions_today()
        if getattr(config, "DYNAMIC_CONFIG_ENABLED", False):
            dynamic_config.dynamic_rules.adapt_from_performance(closed_deals)

        # Display Daily WinRate Summary Log (aggregate + per-symbol breakdown)
        if closed_deals and len(closed_deals) > 0:
            dec = [d for d in closed_deals if abs(d.get("profit", 0)) > config.bep_tolerance_for(d)]
            bep_n = len(closed_deals) - len(dec)
            total_t = len(dec)
            wins_t = sum(1 for d in dec if d.get("profit", 0) > 0)
            loss_t = total_t - wins_t
            wr = (wins_t / total_t) * 100.0 if total_t else 0.0
            pnl_t = sum(d.get("profit", 0) for d in closed_deals)
            bep_str = f" | {bep_n} BEP" if bep_n else ""
            box_items.append((f"{UI.BOLD}Performa Harian:{UI.RST} ", f"{total_t} Trade ({wins_t}W - {loss_t}L | WR {wr:.1f}%{bep_str}) | Net PnL: {UI.badge_pnl(pnl_t)}"))

            # Per-symbol breakdown
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
                box_items.append("---")
                box_items.append(f"{UI.DIM}Breakdown Per Simbol:{UI.RST}")
                for sym, b in sorted(by_symbol.items()):
                    sym_t = b["n"] - b["bep"]
                    sym_wr = (b["wins"] / sym_t) * 100.0 if sym_t else 0.0
                    sym_loss = sym_t - b["wins"]
                    bep_note = f" | {b['bep']} BEP" if b["bep"] else ""
                    box_items.append(f"  • {UI.BOLD}{sym:<13}{UI.RST}: {sym_t}T ({b['wins']}W - {sym_loss}L | WR {sym_wr:.0f}%{bep_note}) Net: {UI.badge_pnl(b['pnl'])}")
        else:
            box_items.append(f"{UI.DIM}Performa Harian: Belum ada trade tertutup hari ini (0 Trade | WR: 0.0%){UI.RST}")
    except Exception as e:
        box_items.append(f"{UI.YELLOW}[EVALUATOR WARNING] {e}{UI.RST}")

    title_str = f"CYCLE START - {time.strftime('%Y-%m-%d %H:%M:%S')} WIB"
    print("\n" + UI.make_box(title_str, box_items, width=74, border_color=UI.CYAN))

    # -- Multi-symbol parallel scan ----------------------------------------------
    global _symbol_last_candle
    valid_pool = _resolve_valid_pool()
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
            
            # Log indikator candle baru untuk pair selain pair utama
            if last_time is not None and sym != valid_pool[0]:
                tf_label = "H1" if tf == mt5.TIMEFRAME_H1 else ("M30" if tf == mt5.TIMEFRAME_M30 else ("M15" if tf == mt5.TIMEFRAME_M15 else "M5"))
                print(f"\n {UI.GREEN}[+] Candle {tf_label} baru CLOSE untuk {sym}!{UI.RST} Range: {_candle_range_label(closed_time, tf)}")
                
            try:
                _run_cycle_for_current_symbol()
            except Exception as e:
                print(f" {UI.RED}[CYCLE ERROR {sym}] {e}{UI.RST}")
        else:
            pass
            
    config.SYMBOL = valid_pool[0] if valid_pool else config.SYMBOL

    # Statistik pending order (AI proven) - tampil tiap cycle kalau enabled
    _detect_filled_pending()
    _report_pending_stats()
    # Recap HOLD gabungan (satu pesan Telegram untuk semua simbol cycle ini)
    _send_hold_recap()
    return True


def _run_cycle_for_current_symbol():
    """Full cycle untuk satu simbol aktif (config.SYMBOL): risk gate -> data -> LLM
    -> consensus -> eksekusi. Dipanggil per simbol dalam pool (mode xau_pairs).
    """
    # 0. Risk gate - check all conditions before trading
    can_trade, reason = risk.can_trade()
    entry_blocked = False  # True = posisi sudah max: re-evaluator tetap jalan, entry ditahan
    if not can_trade:
        # Kasus khusus: posisi sudah MAX (aggregate semua simbol). Jangan skip cycle —
        # lanjut ambil data + LLM + consensus + AI RE-EVALUATOR (bisa rekomendasi CLOSE
        # posisi lemah buat buka slot). Hanya entry baru yang ditahan (entry_blocked).
        # Simbol yang TIDAK punya posisi terbuka di-skip: re-evaluator gak ada kerjaan,
        # entry juga diblokir -> LLM call sia-sia.
        max_pos_now = config.get_max_open_positions(risk.is_recovery_mode)
        if len(connector.get_all_open_positions()) >= max_pos_now:
            if not connector.get_open_positions(config.SYMBOL):
                print(f" {UI.tag('RISK GATE', UI.YELLOW)} Max posisi {max_pos_now} tercapai & {config.SYMBOL} tanpa posisi terbuka — skip (re-evaluator kosong).")
                return True
            entry_blocked = True
            print(f" {UI.tag('RISK GATE', UI.YELLOW)} Max posisi {max_pos_now} tercapai — lanjut AI re-evaluator utk {config.SYMBOL} (entry ditahan).")
        else:
            clean_reason = reason.strip()
            if clean_reason.startswith("[RISK]"):
                clean_reason = clean_reason[6:].strip()
            print(f" {UI.tag('RISK GATE', UI.YELLOW)} {clean_reason}")
            return True  # Not an error, just skipping
    
    # 0.5 Pending order lifecycle: expired/cap/contra cleanup (hanya kalau enabled)
    _manage_pending_orders()    
    # 1. Fetch market data (103 bar, buang bar aktif -> 100 candle SUDAH CLOSE. M15 XAU / H1 FX / M30 BTC)
    df = connector.get_market_data(config.SYMBOL, config.get_timeframe(config.SYMBOL), num_candles=103)
    if df is None or len(df) == 0:
        print(f" {UI.tag('DATA ERROR', UI.RED)} Gagal mendapatkan market data untuk {config.SYMBOL}. Melewatkan siklus.")
        return False
    if len(df) > 102:
        df = df.iloc[-102:-1].reset_index(drop=True)
        
    # 2. Fetch current tick (Bid/Ask)
    tick = connector.get_current_tick(config.SYMBOL)
    if tick is None:
        print(f" {UI.tag('DATA ERROR', UI.RED)} Gagal mendapatkan tick data {config.SYMBOL}. Melewatkan siklus.")
        return False
        
    _tf_map = {mt5.TIMEFRAME_M5: "M5", mt5.TIMEFRAME_M15: "M15", mt5.TIMEFRAME_M30: "M30", mt5.TIMEFRAME_H1: "H1"}
    tf_name = _tf_map.get(config.get_timeframe(config.SYMBOL), "?")
    print(f"\n{UI.tag('SCAN ASSET', UI.CYAN)} {UI.BOLD}{config.SYMBOL}{UI.RST} ({tf_name}) | Bid: {tick['bid']:.2f} | Ask: {tick['ask']:.2f} | Spread: {tick['spread']} pts")


    # 2.1 Calculate Market Randomness & Micro Fat Tails
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
            tf_mins = 30 if config.is_crypto(config.SYMBOL) else (60 if "XAU" not in config.SYMBOL.upper() else 15)
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

    # Pattern edge whisper: deteksi pola di candle terakhir & inject statistik
    # tervalidasi kalau match registry (informational only, bukan directive).
    whisper_str = None
    if getattr(config, "PATTERN_WHISPER_ENABLED", True):
        try:
            from src.analytics.pattern_detector import detect_and_whisper
            whisper_str = detect_and_whisper(df, config.SYMBOL)
            if whisper_str:
                first_line = whisper_str.strip().split("\n")[0]
                print(f" {UI.tag('WHISPER', UI.MAGENTA)} {first_line}")
        except Exception as e:
            print(f"[WHISPER ERROR {config.SYMBOL}] {e}")

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
    print(f" {UI.tag('AI', UI.CYAN)} Mode {ai_mode.upper()} ({len(active_models)} model: {', '.join(active_models)}) | Mengirim data ke LLM...")
    all_open_positions = connector.get_all_open_positions()
    decisions = llm.get_multi_llm_decisions(config.SYMBOL, df, tick, macro_context, open_positions,
                                            whisper_str, all_open_positions=all_open_positions)

    
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

    # Check if max open positions reached for NEW trades (recovery mode: tighter cap; late NY: max 2)
    max_positions = config.get_max_open_positions(risk.is_recovery_mode)
    if entry_blocked or len(open_positions) >= max_positions:
        if entry_blocked:
            print(f"-> Entry ditahan: posisi bot sudah {max_positions} (aggregate semua simbol). Re-evaluator tetap jalan.")
        else:
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
        invalidation_price = result.get("invalidation_price")
        target_price = result.get("target_price")
        agreeing_count = result.get("agreeing_count", 0)

        # Obtain latest execution tick to size lot and get absolute SL/TP prices
        tick_live = connector.get_current_tick(config.SYMBOL)
        sl_price = None
        tp_price = None
        tp_price_2 = None
        gate_blocked = False  # re-check SL/TP eksekusi gagal -> trade dibatalkan

        if tick_live and sl_points and sl_points > 0:
            point = tick_live["point"]
            execution_price = tick_live["ask"] if trade_signal == "BUY" else tick_live["bid"]
            if execution_price > 0 and point > 0:
                # SL/TP murni dari sl_points/tp_points model (sudah di-floor di
                # consensus.py). invalidation_price/target_price TIDAK dipakai
                # untuk SL/TP — cuma referensi probability (fix 14 Agustus).
                sl_points = max(tick_live["spread"] * 2, sl_points)

                if tp_points and tp_points > 0:
                    tp_points = max(tick_live["spread"] * 2, tp_points)
                    # Position 2 gets 1.2x TP for extended trend capture
                    tp_points_2 = int(tp_points * 1.2)
                else:
                    tp_points_2 = None

                # RE-CHECK gate SL/TP pakai tick terkini (spread/equity bisa
                # geser antara consensus dan eksekusi). Kalau gagal gate (R:R <
                # 1.25 / OVER-RISK) -> batalkan trade, jangan kirim order.
                sl_points, tp_points, sltp_ok, sltp_reason = consensus._apply_sltp_rules(sl_points, tp_points)
                if not sltp_ok:
                    gate_blocked = True
                    print(f"   [!] TRADE DIBATALKAN (re-check SL/TP eksekusi): {sltp_reason}")
                else:
                    # Re-sync harga absolut setelah gate (safety floor bisa menaikkan SL)
                    tp_points_2 = int(tp_points * 1.2)
                    if trade_signal == "BUY":
                        sl_price = execution_price - (sl_points * point)
                        tp_price = execution_price + (tp_points * point)
                        tp_price_2 = execution_price + (tp_points_2 * point)
                    else:
                        sl_price = execution_price + (sl_points * point)
                        tp_price = execution_price - (tp_points * point)
                        tp_price_2 = execution_price - (tp_points_2 * point)

        # Check remaining capacity slots before max positions (recovery mode: tighter cap)
        # gate_blocked = re-check SL/TP eksekusi gagal -> tidak ada slot, trade batal
        remaining_slots = 0 if gate_blocked else max(0, max_positions - len(open_positions))
        desired_positions = 2 if agreeing_count >= 3 else 1
        num_positions = min(desired_positions, remaining_slots)

        # Get effective lot size from risk-based sizing (uses execution SL points)
        effective_lot = risk.get_effective_lot_size(sl_points, split_count=num_positions)

        # PENDING ORDER: kalau consensus memilih entry_type non-market dan
        # pending order diaktifkan -> pasang pending order (bukan market order).
        # Tereksekusi -> posisi normal (SL/TP + BEP + trailing).
        entry_type = result.get("entry_type") or "market"
        entry_price = result.get("entry_price")
        if (getattr(config, "PENDING_ORDERS_ENABLED", False)
                and entry_type != "market"
                and entry_price is not None
                and not gate_blocked
                and num_positions > 0):
            try:
                pendings_now = connector.get_pending_orders()
                pendings_same_symbol = [p for p in pendings_now if p.get("symbol") == config.SYMBOL]
                max_active = getattr(config, "PENDING_ORDER_MAX_ACTIVE", 3)
                if len(pendings_now) >= max_active:
                    print(f" {UI.tag('PENDING', UI.YELLOW)} Cap pending {max_active} tercapai — skip pasang pending baru untuk {config.SYMBOL}.")
                elif pendings_same_symbol:
                    print(f" {UI.tag('PENDING', UI.YELLOW)} Sudah ada pending untuk {config.SYMBOL} — skip duplikat.")
                else:
                    # Cancel pending kontra dulu (tesis baru = arah baru)
                    _cancel_pending_contra(trade_signal, symbol=config.SYMBOL)
                    # SL/TP absolute dihitung relatif ke entry_price pending
                    p_point = tick_live["point"] if tick_live else 0.01
                    p_sl_price = None
                    p_tp_price = None
                    if sl_points and sl_points > 0:
                        if entry_type in ("buy_stop", "buy_limit"):
                            p_sl_price = entry_price - (sl_points * p_point)
                            p_tp_price = (entry_price + (tp_points * p_point)) if tp_points else None
                        else:
                            p_sl_price = entry_price + (sl_points * p_point)
                            p_tp_price = (entry_price - (tp_points * p_point)) if tp_points else None
                    order_comment_pending = (result.get("reason") or "").strip()[:31] or f"PEND {entry_type}"
                    pending_res = connector.send_pending_order(
                        symbol=config.SYMBOL,
                        entry_type=entry_type,
                        entry_price=entry_price,
                        lot=effective_lot,
                        sl_points=sl_points,
                        tp_points=tp_points,
                        comment=order_comment_pending,
                        sl_price=p_sl_price,
                        tp_price=p_tp_price,
                        expiration_minutes=config.PENDING_ORDER_EXPIRY_MINUTES,
                    )
                    if pending_res["status"] == "SUCCESS":
                        _record_pending_event({
                            "event": "placed",
                            "ticket": pending_res["ticket"],
                            "symbol": config.SYMBOL,
                            "type": entry_type,
                            "price": entry_price,
                            "sl_points": sl_points,
                            "tp_points": tp_points,
                            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        })
                        print(f" {UI.tag('PENDING', UI.GREEN)} Pending {entry_type} @ {entry_price} terpasang (ticket {pending_res['ticket']}).")
                    else:
                        print(f" {UI.tag('PENDING', UI.RED)} Gagal pasang pending: {pending_res.get('comment')}")
                    return True  # pending sudah dipasang, tidak lanjut ke market order
            except Exception as e:
                print(f"[PENDING EXEC ERROR] {e}")
            # kalau gagal/exception -> fall through ke market order

        if num_positions > 1:
            print(f"[UNANIMOUS 3/3 HIGH CONFIDENCE] Ketiga AI sepakat {trade_signal}! Membuka {num_positions} posisi sekaligus (Sisa slot: {remaining_slots})...")
        elif num_positions == 1 and desired_positions > 1:
            print(f"[UNANIMOUS 3/3 HIGH CONFIDENCE] Ketiga AI sepakat {trade_signal}! Membuka 1 posisi (Dibatasi sisa slot max: {remaining_slots})...")

        order_executed = False  # flag: ada order yang sukses cycle ini (untuk decision memory)
        for i in range(num_positions):
            # Posisi 2 gets 1.2x TP for capturing extended trend
            pos_tp = int(tp_points * 1.2) if i == 1 else tp_points
            pos_tp_price = tp_price_2 if (i == 1 and tp_price_2) else tp_price

            # Comment transaksi: prioritaskan reason/setup analisa AI (maks 31 karakter MT5)
            open_reason = (result.get("reason") or "").strip()
            if not open_reason:
                model_labels = {
                    "OpenAI": "GPT",
                    "Gemini": "Gemini",
                    "DeepSeek": "DeepSeek",
                    "Claude": "Claude",
                }
                agree_models = result.get("agreeing_models") or []
                open_reason = "+".join(
                    model_labels.get(m, m) for m in agree_models
                ) or "Multi-LLM Bot"

            # Bersihkan whitespace/karakter khusus dan potong maksimal 25 karakter
            import re
            order_comment = re.sub(r'[\r\n\t]+', ' ', open_reason).strip()[:25].strip()

            order_res = connector.send_trade_order(
                symbol=config.SYMBOL,
                action=trade_signal,
                lot=effective_lot,
                sl_points=sl_points,
                tp_points=pos_tp,
                comment=order_comment,
                sl_price=sl_price,
                tp_price=pos_tp_price
            )
            if order_res["status"] == "SUCCESS":
                order_executed = True
                print(f"Sukses menempatkan order #{i+1}: {trade_signal} (Ticket: {order_res['ticket']}, Lot: {effective_lot})")
                risk.record_trade_opened()
                tg.alert_trade_opened(
                    trade_signal, effective_lot, sl_points, pos_tp,
                    recovery_mode=risk.is_recovery_mode,
                    session_multiplier=risk.session_lot_multiplier,
                    symbol=config.SYMBOL
                )
            else:
                print(f"Gagal menempatkan order #{i+1}: {order_res['comment']}")
    else:
        print("Tidak ada keputusan BUY/SELL yang disetujui. Menunggu candle berikutnya.")
        # HOLD: kumpulkan ke buffer recap (bukan kirim per-symbol) — dikirim
        # SATU pesan gabungan di akhir run_trading_cycle via _send_hold_recap().
        global _hold_recap_lines
        line = _hold_recap_line(result)
        if line:
            _hold_recap_lines.append(line)

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

    # Tampilkan override CLI kalau ada
    if cli_applied:
        print(f" {UI.YELLOW}[CLI OVERRIDE]{UI.RST} " + " | ".join(cli_applied))
        print(f"{UI.DIM}------------------------------------------------------------------------{UI.RST}")

    # Prompt interaktif setting - kecuali --yes atau non-TTY / Docker mode (langsung jalan)
    if not skip_prompt and sys.stdin.isatty():
        interactive_setup()

    # Set active symbol now so the banner shows the symbol that will be traded
    config.refresh_active_symbol()

    _tf_map = {mt5.TIMEFRAME_M5: "M5", mt5.TIMEFRAME_M15: "M15", mt5.TIMEFRAME_M30: "M30", mt5.TIMEFRAME_H1: "H1"}
    tf_name = _tf_map.get(config.get_timeframe(config.SYMBOL), "?")

    print(render_banner(
        account_info=getattr(config, "MT5_LOGIN", None),
        symbol=config.SYMBOL,
        tf=tf_name,
        mode=config.TRADING_MODE,
        is_live=not config.DRY_RUN
    ))

    # Info Trading Mode
    if config.TRADING_MODE == "xau_pairs":
        pool = config.get_rotation_pool()
        print(f"  {UI.BOLD}Pool Scan   :{UI.RST} {UI.CYAN}{' -> '.join(pool)}{UI.RST} ({len(pool)} simbol)")
        print(f"  {UI.BOLD}Timeframe   :{UI.RST} FX Pairs (H1 Expert Intraday-Swing) | BTC (M30 Intraday) - Smart Rotation")
    else:
        print(f"  {UI.BOLD}Trading Mode:{UI.RST} {UI.CYAN}FX PAIRS ONLY{UI.RST} (H1 Expert Intraday-Swing)")

    if config.TP_SL_RULES != "LLM":
        sltp_desc = f"{config.TP_SL_RULES} (force semua)"
    elif config.TRADING_MODE == "xau_pairs":
        sltp_desc = f"FX: LLM Structure (floor {config.LLM_FX_FLOOR_ATR_MULT}xATR H1) | BTC: ATR-Based (fix)"
    else:
        sltp_desc = f"XAU: LLM Structure (floor {config.LLM_SAFETY_FLOOR_XAU_PTS} pts) | BTC: ATR-Based (fix)"

    print(f"  {UI.BOLD}Risk & Rules:{UI.RST} Risk {config.risk_percent_for(config.SYMBOL)}% | SL/TP: {sltp_desc} | Max Daily Loss: ${config.MAX_DAILY_LOSS_USD} | Target Profit: {config.DAILY_PROFIT_TARGET_PERCENT}%")
    print(f"  {UI.BOLD}Proteksi    :{UI.RST} Trailing Stop [{'ON' if config.TRAILING_STOP_ENABLED else 'OFF'}], BEP [{'ON' if config.BREAK_EVEN_ENABLED else 'OFF'}], Recovery [{'ON' if config.RECOVERY_MODE_ENABLED else 'OFF'}]")
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
        
    print("\n Terhubung ke MT5 dengan sukses!")
    
    # One-time startup check to evaluate any trades closed while offline
    try:
        print("[STARTUP] Memeriksa tiket terlewat untuk evaluasi post-mortem...")
        trade_evaluator.evaluator.check_and_evaluate_closed_trades()
    except Exception as e:
        print(f"[STARTUP EVALUATOR WARNING] {e}")
        
    # FASE 6 - pilihan mode scan startup (CLI professional, default sesuai timeframe, timeout 10 detik)
    _prompt_startup_scan_mode(skip_prompt)

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
    _last_day = None  # deteksi ganti hari (WIB) -> kirim ringkasan harian otomatis

    try:
        while True:
            # =================================================================
            #  EVERY TICK (5s): Manage open positions + weekend check
            # =================================================================
            try:
                # Day-change detection: kalau tanggal WIB berubah, kirim ringkasan
                # harian (rich) sebelum reset, biar laporan tiap hari lengkap.
                try:
                    from datetime import datetime
                    from zoneinfo import ZoneInfo
                    wib_now = datetime.now(ZoneInfo("Asia/Jakarta"))
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
                            _reset_status_lines()
                            print("Startup scan mode: sesuai timeframe - menunggu candle close berikutnya...")
                        else:
                            _reset_status_lines()
                            print("Menjalankan siklus analisa pertama saat startup (scan all now)...")
                    else:
                        candle_wib = connector.server_to_wib(int(current_candle_time))
                        tf_main = config.get_timeframe(config.SYMBOL)
                        _reset_status_lines()
                        print(f"\n {UI.GREEN}[+] Candle baru terdeteksi!{UI.RST} Range: {_candle_range_label(current_candle_time, tf_main)}")
                    
                    last_candle_time = current_candle_time
                    
                    # Show daily P/L and risk status
                    daily_pnl = risk.get_daily_pnl()
                    status = risk.get_status_summary()
                    _reset_status_lines()
                    print(f" {UI.CYAN}[STATUS]{UI.RST} P/L Hari Ini: {UI.badge_pnl(daily_pnl)} | "
                          f"Loss Streak: {status['consecutive_losses']} | "
                          f"Recovery: {'Ya' if status['recovery_mode'] else 'Tidak'} | "
                          f"Session Lot: x{status['session_lot_multiplier']}")
                    
                    if not skip_cycle:
                        # Run trading cycle
                        run_trading_cycle()
                        tg.flush_failed_orders_recap()
            else:
                print("Gagal mengecek status candle di MT5. Mencoba kembali...")
            
            # Show live status clock line in CLI every loop iteration (clean ANSI, zero emojis)
            now_str = time.strftime('%H:%M:%S')
            remaining_pause = risk.get_remaining_pause()
            pause_str = f" {UI.RED}[PAUSED: {remaining_pause}s]{UI.RST}" if remaining_pause > 0 else ""
            daily_pnl = risk.get_daily_pnl()
            pnl_str = UI.badge_pnl(daily_pnl)
            
            # Show any running (open) bot positions across ALL symbols in a single line refresh
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

            main_sym = config.SYMBOL.replace("-ECNc", "").replace(".c", "")
            header_part = f"[{UI.BOLD}{main_sym}{UI.RST} | {UI.CYAN}{now_str}{UI.RST}]{pause_str} | P/L Today: {pnl_str}"
            
            # Wrap daftar posisi ke baris terpisah (SEMUA posisi tampil, tidak ada truncate paksa)
            # supaya auto-scroll terminal tidak merusak refresh in-place multi-baris.
            try:
                cols = shutil.get_terminal_size((120, 24)).columns
            except Exception:
                cols = 120
            max_w = max(40, cols - 2)
            if open_pos:
                status_lines = _wrap_positions(pos_parts, max_w, indent=header_part + f" | {UI.GRAY}pos:{UI.RST} ")
            else:
                status_lines = [header_part + pos_str]

            sys.stdout.write(_render_status_lines(status_lines, _VT_OK))
            sys.stdout.flush()

            # Sleep 3 seconds between checks
            time.sleep(3)  # loop utama - cache query MT5 sudah kurangi beban, 3 detik aman

            
    except KeyboardInterrupt:
        print("\n Bot dimatikan secara manual oleh user.")
    finally:
        # Send rich daily summary before shutdown (P/L, breakdown per simbol,
        # win/loss, posisi terbuka)
        daily_pnl = risk.get_daily_pnl()
        closed_deals = connector.get_closed_positions_today()
        open_pos = connector.get_all_open_positions()
        tg.alert_daily_summary(
            daily_pnl, len(closed_deals), risk.get_status_summary(),
            closed_deals=closed_deals, open_positions=open_pos,
            reason="Bot Mati",
        )
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
