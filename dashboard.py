"""
Trading Dashboard Builder.

Membaca trading_bot.log + data/*.json, menghitung metrik kualitas trade,
kualitas sinyal LLM, dan statistik standar, lalu menghasilkan satu file
dashboard.html (Chart.js, tema gelap, filter JS) yang bisa dibuka di browser.

Usage:
    python dashboard.py                 # generate dashboard.html (static)
    python dashboard.py --serve --port 8765  # server live (baca log fresh, no reload)
    python dashboard.py -o out.html

Read-only terhadap file bot. Tidak menyentuh main.py / MT5.
"""
import argparse
import base64
import json
import math
import os
import re
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
from datetime import datetime

from dashboard_assets import TEMPLATE

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
LOG_PATH = os.path.join(DATA_DIR, "trading_bot.log")
if not os.path.exists(LOG_PATH):
    LOG_PATH = os.path.join(ROOT, "trading_bot.log")
if not os.path.exists(LOG_PATH):
    LOG_PATH = os.path.join(ROOT, "logs", "trading_bot.log")
OUT_HTML = os.path.join(ROOT, "dashboard.html")

BEP_TOLERANCE_USD = 0.04
STARTING_BALANCE = 1000.0

MODEL_ORDER = ["OpenAI", "Gemini", "Claude", "DeepSeek"]

# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------
RE_BANNER_MODELS = re.compile(r"Models:\s*(.+)")
RE_LOGIN = re.compile(r"\[MT5\] Mencoba masuk ke akun (\d+)")
RE_CYCLE = re.compile(r"\[CYCLE START\] Memulai analisa market pada (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
RE_PRICE = re.compile(r"[PRICE]  Harga saat ini (\S+) - Bid: ([\d.]+), Ask: ([\d.]+), Spread: ([\d.]+) pts")
RE_QUANT_MATH = re.compile(r"\[QUANT MATH\]")
RE_QUANT_PROB = re.compile(r"\[QUANT PROB\]")
RE_DYNAMIC = re.compile(r"\[DYNAMIC CONFIG\]")
RE_PERF = re.compile(r"\[PERFORMA HARIAN\]")
RE_LATENCY = re.compile(r"\[LATENSI MODEL \(Ronde 1\)\]\s*(.*)")
RE_DECISION = re.compile(
    r"\[(Gemini|OpenAI|DeepSeek|Claude)\] Decision: (BUY|SELL|HOLD) \(Conf: ([\d.]+)%\)"
)
RE_SL_TP = re.compile(r"SL:\s*([\d.]+)\s*pts?,?\s*TP:\s*([\d.]+)")
RE_REASON = re.compile(r"Reason:\s*(.*)")
RE_CONS_OK = re.compile(r"\[KONSENSUS DISETUJUI\] Sinyal: (BUY|SELL) \(skor ([\d.]+) >= threshold ([\d.]+)\)")
RE_CONS_OK_BACKUP = re.compile(r"\[KONSENSUS DISETUJUI\] Sinyal: (BUY|SELL)")
RE_CONS_FAIL = re.compile(r"\[KONSENSUS GAGAL\]")
RE_CONS_MODELS = re.compile(r"Model yang sepakat:\s*(.+)")
RE_CONS_AVG = re.compile(r"Rata-rata Keyakinan:\s*([\d.]+)%")
RE_UNANIMOUS = re.compile(r"\[UNANIMOUS")
RE_ORDER = re.compile(
    r"\[MT5\] Mengirim order: (BUY|SELL) (\S+) ([\d.]+) lot pada harga ([\d.]+) \(SL: ([\d.]+), TP: ([\d.]+)\)"
)
RE_ORDER_OK = re.compile(r"\[MT5\] Order BERHASIL! Ticket: (\d+)")
RE_POSTMORTEM = re.compile(r"\[POST-MORTEM\]\s*Menganalisis hasil trade tiket #(\d+)\s*\((\S+),\s*P/L:\s*\$?([+-]?[\d.]+)\)")
RE_POSTMORTEM_ALT = re.compile(r"\[POST-MORTEM\].*?tiket #(\d+).*?P/L:\s*\$?([+-]?[\d.]+)", re.IGNORECASE)
RE_LESSON = re.compile(r"\[PELAJARAN BARU DITERIMA\]")
RE_BE = re.compile(r"\[BREAK-EVEN\]")
RE_TRAIL = re.compile(r"\[TRAILING\]")
RE_PARTIAL = re.compile(r"\[PARTIAL CLOSE\]")
RE_FORECAST_INFO = re.compile(r"\[FORECAST INFO\]\s*(.*)")
RE_FORECAST_BIAS = re.compile(r"Bias:\s*(BULLISH|BEARISH|NEUTRAL)")
RE_MTF = re.compile(r"\[MTF\]")
RE_FUND = re.compile(r"\[FUNDAMENTAL\]")
RE_SWITCH = re.compile(r"\[SYMBOL SWITCH\]")
RE_SLOT = re.compile(r"Sisa slot:")


def _to_ts(dt_str):
    try:
        return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return None


def _norm_era(banner_models):
    return banner_models.strip() if banner_models else None


# ---------------------------------------------------------------------------
# 1. PARSER
# ---------------------------------------------------------------------------
def parse_log(path=LOG_PATH):
    events = []
    current_era = None
    current_account = None
    current_cycle_ts = None
    current_symbol = None
    pending_order = None

    if not os.path.exists(path):
        return events

    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for ln, line in enumerate(lines, 1):
        line_s = line.strip()
        if not line_s:
            continue

        m = RE_LOGIN.search(line)
        if m:
            current_account = int(m.group(1))
            events.append({"type": "session", "account": current_account, "era": current_era, "line": ln})
            continue

        m = RE_BANNER_MODELS.search(line)
        if m:
            current_era = _norm_era(m.group(1))
            continue

        m = RE_CYCLE.search(line)
        if m:
            current_cycle_ts = _to_ts(m.group(1))
            events.append({"type": "cycle", "ts": current_cycle_ts, "symbol": current_symbol, "era": current_era})
            continue

        m = RE_PRICE.search(line)
        if m:
            current_symbol = m.group(1)
            try:
                bid = float(m.group(2))
                spread = float(m.group(4))
            except ValueError:
                bid, spread = None, None
            if current_cycle_ts:
                events.append({"type": "price", "ts": current_cycle_ts, "symbol": current_symbol,
                               "bid": bid, "spread": spread, "era": current_era})
            continue

        if RE_QUANT_MATH.search(line) or RE_QUANT_PROB.search(line):
            if current_cycle_ts:
                events.append({"type": "quant", "ts": current_cycle_ts, "era": current_era})
            continue

        if RE_DYNAMIC.search(line):
            if current_cycle_ts:
                events.append({"type": "dynamic", "ts": current_cycle_ts, "era": current_era,
                               "status": line_s})
            continue

        m = RE_LATENCY.search(line)
        if m:
            payload = m.group(1)
            per_model = {}
            for mm in re.finditer(r"(\w+): ([\d.]+)s", payload):
                per_model[mm.group(1)] = float(mm.group(2))
            total_m = re.search(r"Total: ([\d.]+)s", payload)
            events.append({"type": "latency", "per_model": per_model,
                           "total": float(total_m.group(1)) if total_m else None,
                           "ts": current_cycle_ts, "era": current_era})
            continue

        m = RE_DECISION.search(line)
        if m:
            model = m.group(1)
            signal = m.group(2)
            conf = float(m.group(3)) / 100.0
            sl_m = RE_SL_TP.search(line)
            sl = float(sl_m.group(1)) if sl_m else None
            tp = float(sl_m.group(2)) if sl_m else None
            reas_m = RE_REASON.search(line)
            reasoning = reas_m.group(1).strip() if reas_m else ""
            events.append({"type": "model_decision", "model": model, "signal": signal,
                           "confidence": conf, "sl_points": sl, "tp_points": tp,
                           "reasoning": reasoning, "ts": current_cycle_ts, "era": current_era})
            continue

        m = RE_CONS_OK.search(line)
        if not m:
            m = RE_CONS_OK_BACKUP.search(line)
        if m:
            signal = m.group(1)
            try:
                score = float(m.group(2))
                threshold = float(m.group(3))
            except (ValueError, IndexError):
                score = threshold = None
            models = None
            avg_conf = None
            j = ln
            while j < len(lines):
                nxt = lines[j].strip()
                mm = RE_CONS_MODELS.search(nxt)
                if mm:
                    models = [x.strip() for x in mm.group(1).split(",") if x.strip()]
                ma = RE_CONS_AVG.search(nxt)
                if ma:
                    avg_conf = float(ma.group(1)) / 100.0
                if RE_ORDER.search(nxt) or RE_UNANIMOUS.search(nxt):
                    break
                j += 1
            events.append({"type": "consensus", "approved": True, "signal": signal,
                           "score": score, "threshold": threshold, "models": models,
                           "avg_conf": avg_conf, "ts": current_cycle_ts, "era": current_era})
            continue

        if RE_CONS_FAIL.search(line):
            m2 = re.search(r"Posisi:\s*(HOLD|BUY|SELL)", line)
            events.append({"type": "consensus", "approved": False, "signal": m2.group(1) if m2 else "HOLD",
                           "score": None, "threshold": None, "models": None, "avg_conf": None,
                           "ts": current_cycle_ts, "era": current_era})
            continue

        if RE_UNANIMOUS.search(line):
            if current_cycle_ts:
                events.append({"type": "unanimous", "ts": current_cycle_ts, "era": current_era})
            continue

        m = RE_ORDER.search(line)
        if m:
            side, symbol, lot, entry, sl, tp = m.groups()
            try:
                lot_f = float(lot)
                entry_f = float(entry)
                sl_f = float(sl)
                tp_f = float(tp)
            except ValueError:
                lot_f = entry_f = sl_f = tp_f = None
            pending_order = {"type": "order", "ticket": None, "symbol": symbol, "side": side,
                             "lot": lot_f, "entry": entry_f, "sl": sl_f, "tp": tp_f,
                             "ts": current_cycle_ts, "era": current_era}
            continue

        m = RE_ORDER_OK.search(line)
        if m and pending_order is not None:
            pending_order["ticket"] = int(m.group(1))
            events.append(pending_order)
            pending_order = None
            continue

        m = RE_POSTMORTEM.search(line)
        if m:
            events.append({"type": "trade_close", "ticket": int(m.group(1)),
                           "symbol": m.group(2), "pnl": float(m.group(3))})
            continue
        m = RE_POSTMORTEM_ALT.search(line)
        if m:
            events.append({"type": "trade_close", "ticket": int(m.group(1)),
                           "symbol": current_symbol, "pnl": float(m.group(2))})
            continue

        if RE_LESSON.search(line):
            events.append({"type": "lesson", "ts": current_cycle_ts, "era": current_era})
            continue

        for tag, typ in ((RE_BE, "break_even"), (RE_TRAIL, "trailing"), (RE_PARTIAL, "partial_close")):
            if tag.search(line):
                t_m = re.search(r"#(\d+)", line)
                events.append({"type": typ, "ticket": int(t_m.group(1)) if t_m else None,
                               "ts": current_cycle_ts, "era": current_era})
                break

        m = RE_FORECAST_INFO.search(line)
        if m:
            fb = RE_FORECAST_BIAS.search(line)
            events.append({"type": "forecast", "bias": fb.group(1) if fb else None,
                           "ts": current_cycle_ts, "era": current_era})
            continue

        if RE_SWITCH.search(line):
            events.append({"type": "symbol_switch", "ts": current_cycle_ts, "era": current_era})
            continue

    return events


# ---------------------------------------------------------------------------
# 2. METRICS
# ---------------------------------------------------------------------------
def _load_json(name):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _is_bep(pnl):
    return abs(pnl) <= BEP_TOLERANCE_USD


def compute_metrics(events, state=None):
    state = state or {}
    risk = state.get("risk_state") or {}
    lessons_mem = state.get("memory_lessons") or {}
    dec_mem = state.get("decision_memory") or {}
    dyn = state.get("dynamic_rules") or {}
    fc = state.get("forecast_cache") or {}

    if not risk.get("known_closed"):
        risk["known_closed"] = [
            o["ticket"] for o in events
            if o["type"] == "order" and o.get("ticket") is not None
        ]

    sessions = [e for e in events if e["type"] == "session"]
    eras = []
    for e in sessions:
        era = e.get("era")
        if era and era not in eras:
            eras.append(era)
    active_era = eras[-1] if eras else None

    cycles = [e for e in events if e["type"] == "cycle"]
    orders = [e for e in events if e["type"] == "order"]
    closes = [e for e in events if e["type"] == "trade_close"]
    decisions = [e for e in events if e["type"] == "model_decision"]
    consensuses = [e for e in events if e["type"] == "consensus"]
    latencies = [e for e in events if e["type"] == "latency"]
    forecasts = [e for e in events if e["type"] == "forecast"]
    bes = [e for e in events if e["type"] == "break_even"]
    trails = [e for e in events if e["type"] == "trailing"]
    partials = [e for e in events if e["type"] == "partial_close"]

    ts_list = [e.get("ts") for e in cycles if e.get("ts")]
    first_ts = min(ts_list) if ts_list else None
    last_ts = max(ts_list) if ts_list else None

    close_by_ticket = {c["ticket"]: c for c in closes}
    known_closed = set(risk.get("known_closed") or [])
    
    mt5_open_tickets = None
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            positions = mt5.positions_get()
            mt5_open_tickets = {p.ticket for p in (positions or [])}
            mt5.shutdown()
    except Exception:
        mt5_open_tickets = None

    trades = []
    for o in orders:
        tick = o.get("ticket")
        close = close_by_ticket.get(tick)
        if mt5_open_tickets is not None:
            status = "open" if tick in mt5_open_tickets else "closed"
        else:
            status = "closed" if (close is not None or tick in known_closed) else "open"
        pnl = close["pnl"] if close else None
        trades.append({
            "ticket": tick, "symbol": o["symbol"], "side": o["side"], "lot": o.get("lot"),
            "entry": o.get("entry"), "sl": o.get("sl"), "tp": o.get("tp"),
            "ts": o.get("ts"), "era": o.get("era"), "pnl": pnl, "status": status,
        })

    closed = [t for t in trades if t["status"] == "closed" and t["pnl"] is not None]
    wins = [t for t in closed if t["pnl"] > BEP_TOLERANCE_USD]
    losses = [t for t in closed if t["pnl"] < -BEP_TOLERANCE_USD]
    n_win, n_loss, n_bep = len(wins), len(losses), len([t for t in closed if _is_bep(t["pnl"])])
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    net_pnl = sum(t["pnl"] for t in closed)
    win_rate = n_win / (n_win + n_loss) if (n_win + n_loss) else None
    profit_factor = gross_win / gross_loss if gross_loss > 0 else (gross_win if gross_win > 0 else None)
    expectancy = net_pnl / len(closed) if closed else None
    avg_win = gross_win / n_win if n_win else None
    avg_loss = sum(t["pnl"] for t in losses) / n_loss if n_loss else None

    ordered = sorted(closed, key=lambda t: (t.get("ts") or 0, t.get("ticket") or 0))
    equity = []
    bal = STARTING_BALANCE
    peak = bal
    max_dd = 0.0
    for t in ordered:
        bal += t["pnl"]
        equity.append({"ts": t.get("ts"), "balance": bal, "pnl": t["pnl"], "ticket": t.get("ticket")})
        if bal > peak:
            peak = bal
        dd = peak - bal
        if dd > max_dd:
            max_dd = dd
    final_balance = bal if ordered else None

    sym_stats = {}
    for t in closed:
        s = t["symbol"]
        d = sym_stats.setdefault(s, {"n": 0, "win": 0, "loss": 0, "bep": 0, "pnl": 0.0})
        d["n"] += 1
        d["pnl"] += t["pnl"]
        if t["pnl"] > BEP_TOLERANCE_USD:
            d["win"] += 1
        elif t["pnl"] < -BEP_TOLERANCE_USD:
            d["loss"] += 1
        else:
            d["bep"] += 1
        d["win_rate"] = d["win"] / (d["win"] + d["loss"]) if (d["win"] + d["loss"]) else None

    sl_buckets = {}
    rr_buckets = {}
    sl_atr_ok = {"below_floor": 0, "above_floor": 0, "unknown": 0}
    for t in trades:
        sl, tp = t.get("sl"), t.get("tp")
        if sl is None or sl <= 0:
            sl_atr_ok["unknown"] += 1
            continue
        bucket = 10 ** int(math.log10(sl))
        b = sl_buckets.setdefault(bucket, {"n": 0, "win": 0, "loss": 0})
        b["n"] += 1
        if t["pnl"] is not None:
            if t["pnl"] > BEP_TOLERANCE_USD:
                b["win"] += 1
            elif t["pnl"] < -BEP_TOLERANCE_USD:
                b["loss"] += 1
        if tp and tp > 0:
            rr = tp / sl
            rr_buckets[round(rr, 1)] = rr_buckets.get(round(rr, 1), 0) + 1

    model_stats = {}
    for d in decisions:
        m = d["model"]
        st = model_stats.setdefault(m, {"n": 0, "BUY": 0, "SELL": 0, "HOLD": 0,
                                        "conf_sum": 0.0, "conf_sq": 0.0, "win": 0, "loss": 0,
                                        "conf_win_sum": 0.0, "conf_loss_sum": 0.0})
        st["n"] += 1
        st[d["signal"]] += 1
        c = d.get("confidence") or 0.0
        st["conf_sum"] += c
        st["conf_sq"] += c * c

    trades_by_ts = {}
    for t in ordered:
        if t.get("ts"):
            trades_by_ts.setdefault(t["ts"], []).append(t)
    for d in decisions:
        ts = d.get("ts")
        if ts is None:
            continue
        for t in trades_by_ts.get(ts, []):
            if t["pnl"] is None:
                continue
            st = model_stats.get(d["model"])
            if not st:
                continue
            if d["signal"] in ("BUY", "SELL"):
                if (d["signal"] == t["side"]) == (t["pnl"] > 0):
                    st["win"] += 1
                else:
                    st["loss"] += 1
                if t["pnl"] > BEP_TOLERANCE_USD:
                    st["conf_win_sum"] += d.get("confidence") or 0.0
                elif t["pnl"] < -BEP_TOLERANCE_USD:
                    st["conf_loss_sum"] += d.get("confidence") or 0.0
    for m, st in model_stats.items():
        st["avg_conf"] = st["conf_sum"] / st["n"] if st["n"] else None
        st["acc"] = st["win"] / (st["win"] + st["loss"]) if (st["win"] + st["loss"]) else None
        st["avg_conf_win"] = st["conf_win_sum"] / st["win"] if st["win"] else None
        st["avg_conf_loss"] = st["conf_loss_sum"] / st["loss"] if st["loss"] else None

    agree_stats = {"cycles": 0, "ge2": 0, "all3": 0, "split": 0, "conf_agree_sum": 0.0, "conf_disagree_sum": 0.0}
    by_cycle = {}
    for d in decisions:
        if d.get("ts") is None:
            continue
        by_cycle.setdefault(d["ts"], []).append(d)
    for ts, ds in by_cycle.items():
        agree_stats["cycles"] += 1
        sigs = [d["signal"] for d in ds if d["signal"] in ("BUY", "SELL")]
        if len(sigs) >= 2 and len(set(sigs)) == 1:
            agree_stats["ge2"] += 1
            if len(sigs) == 3:
                agree_stats["all3"] += 1
            agree_stats["conf_agree_sum"] += sum(d.get("confidence") or 0.0 for d in ds)
        elif len(sigs) == 0:
            pass
        else:
            agree_stats["split"] += 1
            agree_stats["conf_disagree_sum"] += sum(d.get("confidence") or 0.0 for d in ds)

    cons_ok = [c for c in consensuses if c["approved"]]
    cons_fail = [c for c in consensuses if not c["approved"]]

    lat_stats = {}
    for ev in latencies:
        for m, sec in (ev.get("per_model") or {}).items():
            ls = lat_stats.setdefault(m, {"n": 0, "sum": 0.0, "max": 0.0})
            ls["n"] += 1
            ls["sum"] += sec
            if sec > ls["max"]:
                ls["max"] = sec
    for m, ls in lat_stats.items():
        ls["avg"] = ls["sum"] / ls["n"] if ls["n"] else None

    fbias = {}
    for f in forecasts:
        if f.get("bias"):
            fbias[f["bias"]] = fbias.get(f["bias"], 0) + 1

    daily_pnl = {}
    for t in closed:
        if not t.get("ts"):
            continue
        dt_str = datetime.fromtimestamp(t["ts"]).strftime("%Y-%m-%d")
        d = daily_pnl.setdefault(dt_str, {"pnl": 0.0, "count": 0, "win": 0, "loss": 0, "bep": 0})
        pnl = t["pnl"]
        d["pnl"] += pnl
        d["count"] += 1
        if pnl > BEP_TOLERANCE_USD:
            d["win"] += 1
        elif pnl < -BEP_TOLERANCE_USD:
            d["loss"] += 1
        else:
            d["bep"] += 1

    lessons_list = []
    for sym, mem in lessons_mem.items():
        for les in mem.get("lessons", []):
            lessons_list.append({"symbol": sym, "lesson": les.get("lesson", ""),
                                 "theme": les.get("theme", "")})
        if mem.get("lessons_summary"):
            lessons_list.append({"symbol": sym, "lesson": f"[SUMMARY] {mem['lessons_summary']}",
                                 "theme": "summary"})

    metrics = {
        "meta": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "log_path": LOG_PATH,
            "active_era": active_era,
            "eras": eras,
            "first_ts": first_ts,
            "last_ts": last_ts,
            "accounts": sorted({e.get("account") for e in sessions if e.get("account")}),
            "symbols": sorted({o["symbol"] for o in orders} | {o["symbol"] for o in trades}),
        },
        "summary": {
            "total_cycles": len(cycles),
            "total_orders": len(orders),
            "total_closed": len(closed),
            "total_open": len([t for t in trades if t["status"] == "open"]),
            "net_pnl": net_pnl,
            "final_balance": final_balance,
            "max_drawdown": max_dd,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "consensus_approved": len(cons_ok),
            "consensus_failed": len(cons_fail),
            "bep_count": n_bep,
        },
        "trades": trades,
        "daily_pnl": daily_pnl,
        "equity_curve": equity,
        "per_symbol": sym_stats,
        "sl_buckets": {str(k): v for k, v in sorted(sl_buckets.items())},
        "rr_buckets": {str(k): v for k, v in sorted(rr_buckets.items())},
        "sltp_floor": sl_atr_ok,
        "model_stats": model_stats,
        "agreement": agree_stats,
        "latency": lat_stats,
        "forecast_bias": fbias,
        "lessons": lessons_list,
        "position_manager": {
            "break_even": len(bes),
            "trailing": len(trails),
            "partial_close": len(partials),
        },
        "dynamic_rules": dyn,
        "risk_state": {k: risk.get(k) for k in ("consecutive_losses", "recovery_mode") if k in risk},
        "decision_memory": dec_mem,
        "forecast_cache": fc,
        "starting_balance": STARTING_BALANCE,
        "bep_tolerance": BEP_TOLERANCE_USD,
    }
    return metrics


# ---------------------------------------------------------------------------
# 3. RENDERER
# ---------------------------------------------------------------------------
def render_html(metrics):
    """Render template + embed data awal (static). Live mode: JS fetch /api/data."""
    data_json = json.dumps(metrics, ensure_ascii=False)
    html = TEMPLATE.replace(
        '<script>\n"use strict";',
        '<script>\nwindow.__INITIAL_DATA__ = ' + data_json + ';\n"use strict";'
    )
    return html


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def _build_metrics():
    events = parse_log(LOG_PATH)
    state = {
        "risk_state": _load_json("risk_state.json"),
        "memory_lessons": _load_json("memory_lessons.json"),
        "decision_memory": _load_json("decision_memory.json"),
        "dynamic_rules": _load_json("dynamic_rules.json"),
        "forecast_cache": _load_json("forecast_cache.json"),
    }
    return events, compute_metrics(events, state)


def _print_summary(events, metrics):
    print(f"   Events parsed: {len(events)} | Cycles: {metrics['summary']['total_cycles']} | "
          f"Orders: {metrics['summary']['total_orders']} | Closed: {metrics['summary']['total_closed']}")
    wr = metrics['summary']['win_rate']
    if wr is not None:
        print(f"   Net P/L: ${metrics['summary']['net_pnl']:+.2f} | Win rate: {wr*100:.1f}%")


def _persist_env(key, value):
    """Persist a key=value pair into .env (creates or updates the line)."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(key + "="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _send_json(handler, data, status_code=200):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def serve(host="0.0.0.0", port=8765):
    """Server lokal & REST API untuk bot/tools interaktif."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs
    import config

    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self):
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Token")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()

        def _check_auth(self):
            expected = getattr(config, "API_TOKEN", "").strip()
            if not expected:
                return True

            auth_header = self.headers.get("Authorization", "")
            token = ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            elif auth_header.startswith("Basic "):
                try:
                    b64_creds = auth_header[6:].strip()
                    decoded = base64.b64decode(b64_creds).decode("utf-8")
                    if ":" in decoded:
                        token = decoded.split(":", 1)[1]
                    else:
                        token = decoded
                except Exception:
                    token = ""
            elif "X-API-Token" in self.headers:
                token = self.headers.get("X-API-Token", "").strip()
            else:
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                if "token" in params:
                    token = params["token"][0]

            if token == expected:
                return True

            parsed_url = urlparse(self.path)
            path = parsed_url.path.rstrip("/")
            if path in ("", "/", "/index.html", "/dashboard.html"):
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="Trading Bot Dashboard"')
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>401 Unauthorized</h1><p>Access Denied: Invalid or missing API_TOKEN.</p>")
            else:
                _send_json(self, {"status": "error", "message": "Unauthorized: Invalid or missing API Token"}, status_code=401)
            return False

        def do_GET(self):
            parsed_url = urlparse(self.path)
            path = parsed_url.path.rstrip("/")
            if path == "":
                path = "/"
            query_params = parse_qs(parsed_url.query)

            if path in ("/", "/index.html", "/dashboard.html") or path.startswith("/api/"):
                if not self._check_auth():
                    return

            if path in ("/", "/index.html", "/dashboard.html"):
                _, metrics = _build_metrics()
                html = render_html(metrics)
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            elif path == "/api/data":
                _, metrics = _build_metrics()
                _send_json(self, metrics)

            elif path in ("/api/summary", "/api/get_summary"):
                _, metrics = _build_metrics()
                summary = dict(metrics.get("summary", {}))
                summary.update({
                    "active_symbol": getattr(config, "SYMBOL", "XAUUSD-ECN"),
                    "dry_run": getattr(config, "DRY_RUN", False),
                    "trading_paused": getattr(config, "TRADING_PAUSED", False),
                    "starting_balance": getattr(config, "STARTING_BALANCE", 1000.0),
                    "recovery_mode": metrics.get("risk_state", {}).get("recovery_mode", False),
                    "consecutive_losses": metrics.get("risk_state", {}).get("consecutive_losses", 0),
                })
                try:
                    import MetaTrader5 as mt5
                    if mt5.initialize():
                        acc = mt5.account_info()
                        if acc:
                            summary["balance"] = acc.balance
                            summary["equity"] = acc.equity
                            summary["floating_pnl"] = acc.profit
                            summary["margin_free"] = acc.margin_free
                            summary["login"] = acc.login
                            if summary.get("final_balance") is None:
                                summary["final_balance"] = acc.balance
                        mt5.shutdown()
                except Exception:
                    pass
                _send_json(self, {"status": "success", "summary": summary})

            elif path in ("/api/open-positions", "/api/get_open_positions"):
                positions = []
                try:
                    from src.core import mt5_connector as connector
                    open_pos = connector.get_all_open_positions(magic=getattr(config, "MAGIC_NUMBER", 20260625))
                    for p in open_pos:
                        positions.append({
                            "ticket": p.get("ticket"),
                            "symbol": p.get("symbol"),
                            "type": p.get("type"),
                            "volume": p.get("volume"),
                            "price_open": p.get("price_open"),
                            "sl": p.get("sl"),
                            "tp": p.get("tp"),
                            "profit": p.get("profit"),
                            "magic": p.get("magic", getattr(config, "MAGIC_NUMBER", 20260625)),
                        })
                except Exception as e:
                    _, metrics = _build_metrics()
                    trades = metrics.get("trades", [])
                    positions = [t for t in trades if t.get("status") == "open"]

                _send_json(self, {"status": "success", "count": len(positions), "positions": positions})

            elif path in ("/api/recent-trades", "/api/get_recent_trades"):
                limit = 10
                if "limit" in query_params:
                    try:
                        limit = int(query_params["limit"][0])
                    except ValueError:
                        pass
                _, metrics = _build_metrics()
                trades = metrics.get("trades", [])
                recent = trades[-limit:] if trades else []
                _send_json(self, {"status": "success", "count": len(recent), "trades": recent})

            elif path in ("/api/config", "/api/get_config"):
                config_data = {
                    "DRY_RUN": getattr(config, "DRY_RUN", False),
                    "TRADING_PAUSED": getattr(config, "TRADING_PAUSED", False),
                    "SYMBOL": getattr(config, "SYMBOL", "XAUUSD-ECN"),
                    "WEEKDAY_SYMBOL": getattr(config, "WEEKDAY_SYMBOL", "XAUUSD-ECN"),
                    "WEEKEND_SYMBOL": getattr(config, "WEEKEND_SYMBOL", "XAUUSD-ECN"),
                    "TRADING_MODE": getattr(config, "TRADING_MODE", "xau"),
                    "FX_PAIR_SYMBOLS": list(getattr(config, "FX_PAIR_SYMBOLS", [])),
                    "MAX_ROTATION_SYMBOLS": getattr(config, "MAX_ROTATION_SYMBOLS", 5),
                    "CLAUDE_MODEL": getattr(config, "CLAUDE_MODEL", "deepseek/deepseek-v4-flash"),
                    "GEMINI_MODEL": getattr(config, "GEMINI_MODEL", "gemini-3.1-flash-lite"),
                    "OPENAI_MODEL": getattr(config, "OPENAI_MODEL", "gpt-5.4-mini"),
                    "FORECAST_MODEL": getattr(config, "FORECAST_MODEL", "gpt-5.4"),
                    "RISK_PERCENT_BTC": getattr(config, "RISK_PERCENT_BTC", 1.5),
                    "RISK_PERCENT_XAU": getattr(config, "RISK_PERCENT_XAU", 0.5),
                    "LOT_SIZE_XAU": getattr(config, "LOT_SIZE_XAU", 0.01),
                    "LOT_SIZE_BTC": getattr(config, "LOT_SIZE_BTC", 0.01),
                    "MAX_DAILY_LOSS_USD": getattr(config, "MAX_DAILY_LOSS_USD", 50.0),
                    "MAX_CONSECUTIVE_LOSSES": getattr(config, "MAX_CONSECUTIVE_LOSSES", 5),
                    "MAX_OPEN_POSITIONS": getattr(config, "MAX_OPEN_POSITIONS", 6),
                    "MAX_OPEN_POSITIONS_RECOVERY": getattr(config, "MAX_OPEN_POSITIONS_RECOVERY", 4),
                    "TRADE_COOLDOWN_SECONDS": getattr(config, "TRADE_COOLDOWN_SECONDS", 0),
                    "MAX_SPREAD_POINTS_BTC": getattr(config, "MAX_SPREAD_POINTS_BTC", 2400),
                    "MAX_SPREAD_POINTS_XAU": getattr(config, "MAX_SPREAD_POINTS_XAU", 50),
                    "CONFIDENCE_CONSENSUS_THRESHOLD_BTC": getattr(config, "CONFIDENCE_CONSENSUS_THRESHOLD_BTC", 1.2),
                    "CONFIDENCE_CONSENSUS_THRESHOLD_XAU": getattr(config, "CONFIDENCE_CONSENSUS_THRESHOLD_XAU", 1.0),
                    "CONSENSUS_THRESHOLD": getattr(config, "CONSENSUS_THRESHOLD", 2),
                    "MIN_CONSENSUS_MODELS": getattr(config, "MIN_CONSENSUS_MODELS", 2),
                    "TP_SL_RULES": getattr(config, "TP_SL_RULES", "ATR-Based"),
                    "DEFAULT_SL_POINTS_XAU": getattr(config, "DEFAULT_SL_POINTS_XAU", 300),
                    "DEFAULT_TP_POINTS_XAU": getattr(config, "DEFAULT_TP_POINTS_XAU", 600),
                    "DEFAULT_SL_POINTS_BTC": getattr(config, "DEFAULT_SL_POINTS_BTC", 50000),
                    "DEFAULT_TP_POINTS_BTC": getattr(config, "DEFAULT_TP_POINTS_BTC", 100000),
                    "SL_ATR_MULTIPLIER": getattr(config, "SL_ATR_MULTIPLIER", 1.5),
                    "TP_ATR_MULTIPLIER": getattr(config, "TP_ATR_MULTIPLIER", 3.0),
                    "TRAILING_STOP_ENABLED": getattr(config, "TRAILING_STOP_ENABLED", True),
                    "BREAK_EVEN_ENABLED": getattr(config, "BREAK_EVEN_ENABLED", True),
                    "PARTIAL_CLOSE_ENABLED": getattr(config, "PARTIAL_CLOSE_ENABLED", True),
                    "RECOVERY_MODE_ENABLED": getattr(config, "RECOVERY_MODE_ENABLED", True),
                    "DYNAMIC_CONFIG_ENABLED": getattr(config, "DYNAMIC_CONFIG_ENABLED", False),
                    "FORCE_ACTIVE_ENTRY": getattr(config, "FORCE_ACTIVE_ENTRY", False),
                    "DEBATE_ENABLED": getattr(config, "DEBATE_ENABLED", False),
                    "QUANT_ANALYSIS_ENABLED": getattr(config, "QUANT_ANALYSIS_ENABLED", False),
                    "MONTE_CARLO_ENABLED": getattr(config, "MONTE_CARLO_ENABLED", False),
                    "FORECAST_ENABLED": getattr(config, "FORECAST_ENABLED", True),
                    "MEMORY_CONTEXT_ENABLED": getattr(config, "MEMORY_CONTEXT_ENABLED", True),
                    "SESSION_FILTER_ENABLED": getattr(config, "SESSION_FILTER_ENABLED", True),
                    "WEEKEND_CLOSE_ENABLED": getattr(config, "WEEKEND_CLOSE_ENABLED", True),
                    "WEEKEND_TRADING_ENABLED": getattr(config, "WEEKEND_TRADING_ENABLED", False),
                    "ENABLE_BTC_ROTATION": getattr(config, "ENABLE_BTC_ROTATION", False),
                    "available_presets": list(getattr(config, "ERA_PRESETS", {}).keys()),
                }
                _send_json(self, {"status": "success", "config": config_data})

            elif path in ("/api/retrigger_cycle", "/api/trigger_cycle"):
                if hasattr(config, "trigger_manual_cycle"):
                    config.trigger_manual_cycle()
                else:
                    config.TRIGGER_CYCLE_REQUESTED = True
                _send_json(self, {
                    "status": "success",
                    "message": "Trading cycle retrigger requested successfully",
                    "trigger_requested": True
                })

            else:
                _send_json(self, {"status": "error", "message": "Endpoint not found"}, status_code=404)

        def do_POST(self):
            parsed_url = urlparse(self.path)
            path = parsed_url.path.rstrip("/")

            if path.startswith("/api/") or True:
                if not self._check_auth():
                    return

            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b""
            try:
                payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
            except Exception:
                payload = {}

            if path in ("/api/config", "/api/update_config"):
                updated = []
                for k, v in payload.items():
                    if hasattr(config, k):
                        setattr(config, k, v)
                        updated.append(k)
                if updated and hasattr(config, "save_config_to_env"):
                    try:
                        config.save_config_to_env({k: getattr(config, k) for k in updated})
                    except Exception:
                        pass
                _send_json(self, {
                    "status": "success",
                    "message": f"Updated {len(updated)} config parameters" + (
                        " (TRADING_MODE persisted ke .env - restart bot untuk apply)" if "TRADING_MODE" in updated else ""
                    ),
                    "updated_keys": updated
                })

            elif path in ("/api/preset", "/api/set_strategy_preset"):
                preset_name = payload.get("preset") or payload.get("name") or payload.get("preset_name")
                presets = getattr(config, "ERA_PRESETS", {})
                if not preset_name or preset_name not in presets:
                    _send_json(self, {
                        "status": "error",
                        "message": f"Invalid preset '{preset_name}'. Available: {list(presets.keys())}"
                    }, status_code=400)
                    return

                preset_data = presets[preset_name]
                applied_keys = []
                for attr, val in preset_data.items():
                    if attr == "label":
                        continue
                    if hasattr(config, attr):
                        setattr(config, attr, val)
                        applied_keys.append(attr)

                _send_json(self, {
                    "status": "success",
                    "message": f"Applied preset '{preset_name}'",
                    "applied_preset": preset_name,
                    "applied_keys": applied_keys
                })

            elif path in ("/api/pause", "/api/pause_trading"):
                config.TRADING_PAUSED = True
                _send_json(self, {
                    "status": "success",
                    "message": "Trading paused successfully",
                    "trading_paused": True
                })

            elif path in ("/api/resume", "/api/resume_trading"):
                config.TRADING_PAUSED = False
                _send_json(self, {
                    "status": "success",
                    "message": "Trading resumed successfully",
                    "trading_paused": False
                })

            elif path in ("/api/retrigger_cycle", "/api/trigger_cycle"):
                if hasattr(config, "trigger_manual_cycle"):
                    config.trigger_manual_cycle()
                else:
                    config.TRIGGER_CYCLE_REQUESTED = True
                _send_json(self, {
                    "status": "success",
                    "message": "Trading cycle retrigger requested successfully",
                    "trigger_requested": True
                })

            else:
                _send_json(self, {"status": "error", "message": "Endpoint not found"}, status_code=404)

        def log_message(self, fmt, *args):
            pass

    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"🚀 API & Dashboard Server aktif di http://{host}:{port}/")
    print("   Endpoint REST API aktif: /api/summary, /api/open-positions, /api/recent-trades, /api/config, /api/pause, /api/resume, /api/preset, /api/retrigger_cycle")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP]  Server dihentikan.")
    finally:
        srv.server_close()



def main():
    parser = argparse.ArgumentParser(description="Trading dashboard (generate static atau serve live).")
    parser.add_argument("-o", "--output", default=OUT_HTML, help="Output HTML path (mode generate)")
    parser.add_argument("--all-eras", action="store_true", help="Include all eras in default view")
    parser.add_argument("--serve", action="store_true", help="Jalankan server lokal (live)")
    parser.add_argument("--port", type=int, default=8765, help="Port untuk --serve (default 8765)")
    args = parser.parse_args()

    if args.serve:
        serve(port=args.port)
        return 0

    events, metrics = _build_metrics()
    html = render_html(metrics)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[OK]  Dashboard generated: {args.output}")
    _print_summary(events, metrics)
    return 0


if __name__ == "__main__":
    sys.exit(main())
