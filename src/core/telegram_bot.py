"""
Interactive Telegram Bot Controller (2-Way AI Trading Assistant)

Clean & Institutional Interface (Zero Emoticons / Minimalist Terminal Style).

Enables bidirectional control via Telegram:
- Interactive Menu & Inline Keyboards (/menu, /start)
- On-Demand Multi-LLM Analysis (/analisa <symbol>) triggering 3 AI models in parallel
- One-Click Trade Execution directly from Telegram buttons
- Real-time Position Management & Emergency Close (/posisi, /close, /closeall)
- Account & Risk Engine Status (/status, /rekap, /scan)

Runs as a lightweight background daemon thread using long-polling.
Zero additional dependencies (pure standard requests).
Whitelisted to TELEGRAM_CHAT_ID for security.
"""

import threading
import time
import json
import re
import requests
import config
from src.core import mt5_connector as connector
from src.core.risk_engine import RiskEngine
from src.core import llm_client
from src.core import consensus
from src.analytics import macro_analyst

_risk_engine = RiskEngine()


_listener_thread = None
_stop_event = threading.Event()
_last_update_id = 0
_cached_analyses = {}  # { token: { symbol, signal, lot, sl_points, tp_points, sl_price, tp_price, ... } }


def _get_api_url(method):
    api_base = getattr(config, "TELEGRAM_API_BASE", "https://api.telegram.org")
    return f"{api_base}/bot{config.TELEGRAM_BOT_TOKEN}/{method}"


def send_telegram_msg(text, reply_markup=None, chat_id=None):
    """Send message to Telegram with optional inline keyboard."""
    if not config.TELEGRAM_ENABLED or not config.TELEGRAM_BOT_TOKEN:
        return False
    target_chat = chat_id or config.TELEGRAM_CHAT_ID
    if not target_chat:
        return False

    payload = {
        "chat_id": target_chat,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        url = _get_api_url("sendMessage")
        resp = requests.post(url, json=payload, timeout=8)
        if resp.status_code != 200:
            print(f"[TG BOT SEND ERROR] Status {resp.status_code}: {resp.text[:120]}")
            # Fallback to plain text if Markdown format failed
            payload.pop("parse_mode", None)
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code != 200:
                print(f"[TG BOT SEND RETRY ERROR] Status {resp.status_code}: {resp.text[:120]}")
        return resp.status_code == 200
    except Exception as e:
        print(f"[TG BOT ERROR] send_telegram_msg failed: {e}")
        return False


def answer_callback_query(callback_query_id, text=None, show_alert=False):
    """Acknowledge a callback button press."""
    try:
        url = _get_api_url("answerCallbackQuery")
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass


def _build_main_menu_keyboard():
    """Builds clean institutional inline keyboard for main menu."""
    return {
        "inline_keyboard": [
            [
                {"text": "GBPUSD H1", "callback_data": "analyze:GBPUSD-ECNc"},
                {"text": "USDJPY H1", "callback_data": "analyze:USDJPY-ECNc"},
            ],
            [
                {"text": "GBPJPY H1", "callback_data": "analyze:GBPJPY-ECNc"},
                {"text": "XAUUSD H1", "callback_data": "analyze:XAUUSD-ECNc"},
            ],
            [
                {"text": "📡 [ SMC Radar 22 Pairs ]", "callback_data": "cmd:radar"},
            ],
            [
                {"text": "[ Active Positions ]", "callback_data": "cmd:positions"},
                {"text": "[ Daily Summary ]", "callback_data": "cmd:rekap"},
            ],
            [
                {"text": "[ Account Status ]", "callback_data": "cmd:status"},
            ]
        ]
    }


def handle_radar_command(chat_id):
    """Sends the 22-pair Market Structure & SMC Radar report."""
    try:
        from src.analytics.market_scanner import MarketScanner
        scanner = MarketScanner()
        scanner.update_macro_context(connector, force=False)
        report = scanner.get_market_structure_report()
        kb = {
            "inline_keyboard": [
                [{"text": "[ 🔄 Refresh Radar ]", "callback_data": "cmd:radar"}],
                [{"text": "[ Back to Menu ]", "callback_data": "cmd:menu"}]
            ]
        }
        send_telegram_msg(report, reply_markup=kb, chat_id=chat_id)
    except Exception as e:
        print(f"[TG BOT ERROR] handle_radar_command: {e}")
        send_telegram_msg(f"Error fetching radar: `{e}`", chat_id=chat_id)


def _build_main_menu_keyboard():
    """Builds the clean institutional inline keyboard for /menu."""
    return {
        "inline_keyboard": [
            [
                {"text": "GBPUSD H1", "callback_data": "analyze:GBPUSD_H1"},
                {"text": "USDJPY H1", "callback_data": "analyze:USDJPY_H1"}
            ],
            [
                {"text": "EURUSD H1", "callback_data": "analyze:EURUSD_H1"},
                {"text": "GBPJPY H1", "callback_data": "analyze:GBPJPY_H1"}
            ],
            [
                {"text": "XAUUSD H1 (Gold)", "callback_data": "analyze:XAUUSD_H1"},
                {"text": "BTCUSD M30", "callback_data": "analyze:BTCUSD_M30"}
            ],
            [
                {"text": "📡 [ SMC Radar 22 Pairs ]", "callback_data": "cmd:radar"}
            ],
            [
                {"text": "📊 [ Open Positions ]", "callback_data": "cmd:positions"},
                {"text": "🛡️ [ Account Status ]", "callback_data": "cmd:status"}
            ]
        ]
    }


def handle_menu_command(chat_id):
    """Sends the clean institutional control panel."""
    text = (
        "*CONTROL PANEL — 2-STAGE QUANT TRADING BOT*\n"
        "_Select an instrument for on-demand 3-AI consensus or view 22-Pair SMC Radar:_"
    )
    send_telegram_msg(text, reply_markup=_build_main_menu_keyboard(), chat_id=chat_id)


def handle_status_command(chat_id):
    """Sends current account equity, balance, daily P/L and risk status."""
    try:
        acc = connector.get_account_info()
        if not acc:
            send_telegram_msg("Error: Gagal terhubung ke MT5 untuk mengambil data akun.", chat_id=chat_id)
            return

        closed_deals = connector.get_closed_positions_today()
        pnl_today = sum(d.get("profit", 0.0) for d in closed_deals) if closed_deals else 0.0
        open_pos = connector.get_open_positions()
        total_floating = sum(p.get("profit", 0.0) for p in open_pos)
        mode_name = config.TRADING_MODE.upper()

        text = (
            "*ACCOUNT & 2-STAGE QUANT STATUS*\n"
            f"• *Server*: `{acc.get('server', 'N/A')}` (Login `#{acc.get('login', 'N/A')}`)\n"
            f"• *Balance*: `${acc.get('balance', 0.0):,.2f}`\n"
            f"• *Equity*: `${acc.get('equity', 0.0):,.2f}`\n"
            f"• *Free Margin*: `${acc.get('free_margin', 0.0):,.2f}`\n"
            f"• *Daily Realized P/L*: `${pnl_today:+.2f}`\n"
            f"• *Net Floating P/L*: `${total_floating:+.2f}` ({len(open_pos)} positions)\n"
            f"• *Architecture*: `2-Stage Quant Funnel (22 Pairs H1/D1)`\n"
            f"• *Fast Radar*: `60s Sweep Active (0 Token)`\n"
            f"• *3-AI Jury*: `Full 3-AI (OpenAI + Gemini + DeepSeek)`\n"
            f"• *Risk per Trade*: `{config.RISK_PERCENT_FX}%` (Max Pos: `{config.MAX_OPEN_POSITIONS}`)\n"
            f"• *Max Daily Loss*: `{getattr(config, 'MAX_DAILY_LOSS_PERCENT', 4.0)}%` | *Target*: `{config.DAILY_PROFIT_TARGET_PERCENT}%`"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "📡 [ SMC Radar 22 Pairs ]", "callback_data": "cmd:radar"}],
                [{"text": "[ Back to Menu ]", "callback_data": "cmd:menu"}]
            ]
        }
        send_telegram_msg(text, reply_markup=kb, chat_id=chat_id)
    except Exception as e:
        print(f" [TELEGRAM BOT ERROR] handle_status_command: {e}")
        send_telegram_msg(f"Error fetching status: `{e}`", chat_id=chat_id)


def handle_positions_command(chat_id):
    """Sends list of open positions with option to close individual or all."""
    open_pos = connector.get_open_positions()
    if not open_pos:
        text = "*ACTIVE OPEN POSITIONS (0)*\n_Current Account State: Flat / Cash._"
        kb = {"inline_keyboard": [[{"text": "[ Back to Menu ]", "callback_data": "cmd:menu"}]]}
        send_telegram_msg(text, reply_markup=kb, chat_id=chat_id)
        return

    total_floating = sum(p.get("profit", 0.0) for p in open_pos)
    lines = [f"*ACTIVE OPEN POSITIONS ({len(open_pos)})* | Net: `${total_floating:+.2f}` USD\n"]

    kb_rows = []
    for i, pos in enumerate(open_pos, 1):
        sym = pos.get("symbol")
        ticket = pos.get("ticket")
        ptype = (pos.get("type") or "").upper()
        vol = pos.get("volume")
        price = pos.get("price_open")
        profit = pos.get("profit", 0.0)
        sl = pos.get("sl", 0.0)
        tp = pos.get("tp", 0.0)

        p_str = f"+${profit:.2f}" if profit >= 0 else f"-${abs(profit):.2f}"
        lines.append(
            f"*{i}. {sym}* `#{ticket}`\n"
            f"• *Type*: `{ptype} {vol} lot` @ `{price}`\n"
            f"• *Floating*: `{p_str}`\n"
            f"• *SL / TP*: `SL {sl} | TP {tp}`"
        )
        kb_rows.append([{"text": f"[ Close #{ticket} ({sym} {p_str}) ]", "callback_data": f"close:{ticket}"}])

    kb_rows.append([{"text": "[ CLOSE ALL POSITIONS (EMERGENCY) ]", "callback_data": "closeall"}])
    kb_rows.append([{"text": "[ Back to Menu ]", "callback_data": "cmd:menu"}])

    msg_text = "\n\n".join(lines)
    send_telegram_msg(msg_text, reply_markup={"inline_keyboard": kb_rows}, chat_id=chat_id)


def handle_close_ticket(ticket, chat_id):
    """Closes a specific ticket."""
    try:
        t_int = int(ticket)
        res = connector.close_position(t_int)
        if res and res.get("status") == "SUCCESS":
            send_telegram_msg(f"*Position #{t_int} Closed Successfully.*", chat_id=chat_id)
        else:
            err = res.get("comment") if res else "Unknown error"
            send_telegram_msg(f"*Failed to Close #{t_int}*: `{err}`", chat_id=chat_id)
    except Exception as e:
        send_telegram_msg(f"Error close ticket: `{e}`", chat_id=chat_id)


def handle_close_all(chat_id):
    """Emergency close all positions."""
    open_pos = connector.get_open_positions()
    if not open_pos:
        send_telegram_msg("No active positions to close.", chat_id=chat_id)
        return

    closed = 0
    failed = 0
    for pos in open_pos:
        t = pos.get("ticket")
        res = connector.close_position(t)
        if res and res.get("status") == "SUCCESS":
            closed += 1
        else:
            failed += 1

    send_telegram_msg(
        f"*EMERGENCY CLOSE ALL COMPLETED*\n"
        f"• Closed: `{closed}` positions\n"
        f"• Failed: `{failed}` positions",
        chat_id=chat_id
    )


def _normalize_timeframe(tf_str):
    """Normalizes various timeframe representations (e.g. 1H -> H1, 15M -> M15, 1D -> D1)."""
    if not tf_str:
        return None
    t = tf_str.strip().upper()
    mapping = {
        "M1": "M1", "1M": "M1",
        "M5": "M5", "5M": "M5",
        "M15": "M15", "15M": "M15",
        "M30": "M30", "30M": "M30",
        "H1": "H1", "1H": "H1",
        "H4": "H4", "4H": "H4",
        "D1": "D1", "1D": "D1"
    }
    return mapping.get(t, t)


def run_ondemand_analysis(symbol_input, chat_id, timeframe_input=None):
    """
    Runs on-demand parallel analysis using 3 AI models (OpenAI, Gemini, DeepSeek).
    Supports optional custom timeframe request (e.g. /analisa GBPUSD M15, /analisa XAUUSD H4).
    Sends clean consensus response + one-click execution buttons.
    """
    sym = connector.get_valid_trade_symbol(symbol_input)
    norm_tf = _normalize_timeframe(timeframe_input)
    tf_label = norm_tf or config.get_timeframe_str(sym)

    send_telegram_msg(f"*Starting On-Demand 3-AI Analysis for `{sym}` ({tf_label})...*\n_Fetching live candle data, indicators, and H4/D1 macro structure..._", chat_id=chat_id)

    def _worker():
        try:
            if norm_tf and norm_tf in getattr(config, "TIMEFRAME_MAP", {}):
                tf = config.TIMEFRAME_MAP[norm_tf]
            else:
                tf = config.get_timeframe(sym)

            df = connector.get_market_data(sym, tf, num_candles=100)
            if df is None or len(df) < 50:
                send_telegram_msg(f"Error: Gagal mengambil market data `{sym}` ({tf_label}) dari MT5.", chat_id=chat_id)
                return

            tick_live = connector.get_current_tick(sym)
            if not tick_live:
                send_telegram_msg(f"Error: Feed harga live `{sym}` tidak tersedia.", chat_id=chat_id)
                return

            macro_ctx = macro_analyst.analyst.get_macro_context(sym)
            open_pos = connector.get_open_positions(symbol=sym)
            all_open_pos = connector.get_open_positions()

            prompt = llm_client.prepare_prompt(
                sym, df, tick_live,
                macro_context=macro_ctx,
                open_positions=open_pos,
                all_open_positions=all_open_pos
            )

            # Parallel query with 3 models: OpenAI + Gemini + DeepSeek
            decisions = llm_client.query_all_models_parallel(
                prompt,
                models=["OpenAI", "Gemini", "DeepSeek"]
            )

            # Consensus computation
            result = consensus.calculate_consensus(decisions)

            sig = result.get("signal", "HOLD")
            conf = result.get("confidence", 0.0)
            score = result.get("best_score", 0.0)
            thresh = result.get("threshold", 1.0)
            agree_models = result.get("agreeing_models", [])
            setup = result.get("setup", "N/A")
            reason = result.get("reason", "N/A")
            inv_text = result.get("invalidation_text", "")
            sl_pts = result.get("sl_points") or 0
            tp_pts = result.get("tp_points") or 0
            inv_price = result.get("invalidation_price")
            tgt_price = result.get("target_price")
            entry_type = result.get("entry_type") or "market"
            entry_price = result.get("entry_price")

            # Build model votes text (Clean format, no emoji)
            model_votes = []
            for m_name in ["OpenAI", "Gemini", "DeepSeek"]:
                dec = decisions.get(m_name, {})
                m_sig = dec.get("signal", "HOLD")
                m_conf = (dec.get("confidence") or 0.0) * 100
                m_reason = (dec.get("reasoning") or dec.get("edge") or "-")
                m_reason_clean = " ".join(m_reason.replace("\n", " ").split())
                model_votes.append(f"• *{m_name} ({m_conf:.0f}%)*: `{m_sig}` — _{m_reason_clean}_")

            votes_str = "\n".join(model_votes)

            # Calculate lot sizing preview
            effective_lot = _risk_engine.get_effective_lot_size(sl_pts, split_count=1, symbol=sym) if sl_pts > 0 else config.lot_size_for(sym)

            rr_str = f"{tp_pts/sl_pts:.2f}:1" if (sl_pts and sl_pts > 0 and tp_pts) else "N/A"

            lines = [
                f"*ON-DEMAND ANALYSIS: {sym} ({tf_label})*",
                f"Timestamp: `{time.strftime('%H:%M:%S WIB')}` | Engine: `Triple AI (OpenAI + Gemini + DeepSeek)`\n",
                f"*MODEL SIGNALS*:\n{votes_str}\n",
                f"----------------------------------------",
                f"*CONSENSUS DECISION: {sig}*",
            ]

            if sig in ("BUY", "SELL"):
                lines.append(f"• *Models Agreed*: `{', '.join(agree_models)}` (Avg Conf: `{conf*100:.1f}%` | Score `{score:.2f}/{thresh:.2f}`)")
                lines.append(f"• *Setup*: `{setup}`")
                lines.append(f"• *Primary Reason*: _{reason}_")
                if inv_text:
                    lines.append(f"• *Invalidation*: _{inv_text}_")

                sl_str = f"`{inv_price}` ({sl_pts} pts)" if inv_price else f"`{sl_pts} pts`"
                tp_str = f"`{tgt_price}` ({tp_pts} pts | R:R {rr_str})" if tgt_price else f"`{tp_pts} pts`"
                lines.append(f"• *Stop Loss*: {sl_str}")
                lines.append(f"• *Take Profit*: {tp_str}")
                lines.append(f"• *Lot Sizing (Risk {config.risk_percent_for(sym)}%)*: `{effective_lot} lot`")
            else:
                lines.append(f"• *Status*: _Consensus threshold not met or market ranging. Recommended action: HOLD._")

            # Store cache token for button callbacks
            token = f"{sym[:3]}_{int(time.time())}"
            _cached_analyses[token] = {
                "symbol": sym,
                "signal": sig,
                "lot": effective_lot,
                "sl_points": sl_pts,
                "tp_points": tp_pts,
                "sl_price": inv_price,
                "tp_price": tgt_price,
                "entry_type": entry_type,
                "entry_price": entry_price,
                "reason": setup or reason,
            }

            kb_buttons = []
            if sig in ("BUY", "SELL"):
                kb_buttons.append([
                    {"text": f"[ Execute Market {sig} ({effective_lot} lot) ]", "callback_data": f"exec_m:{token}"},
                ])
                if entry_type != "market" and entry_price:
                    kb_buttons.append([
                        {"text": f"[ Place {entry_type.upper()} @ {entry_price} ]", "callback_data": f"exec_p:{token}"},
                    ])

            kb_buttons.append([
                {"text": "[ Re-Analyze ]", "callback_data": f"analyze:{sym}"},
                {"text": "[ Main Menu ]", "callback_data": "cmd:menu"}
            ])

            msg_text = "\n".join(lines)
            send_telegram_msg(msg_text, reply_markup={"inline_keyboard": kb_buttons}, chat_id=chat_id)
        except Exception as e:
            send_telegram_msg(f"Error on-demand analysis: `{e}`", chat_id=chat_id)

    threading.Thread(target=_worker, daemon=True).start()


def execute_cached_trade(token, execution_kind, chat_id):
    """Executes a trade approved via Telegram inline button."""
    item = _cached_analyses.get(token)
    if not item:
        send_telegram_msg("Error: Order token expired. Please run analysis again.", chat_id=chat_id)
        return

    sym = item["symbol"]
    sig = item["signal"]
    lot = item["lot"]
    sl_pts = item["sl_points"]
    tp_pts = item["tp_points"]
    sl_p = item["sl_price"]
    tp_p = item["tp_price"]
    etype = item.get("entry_type", "market")
    eprice = item.get("entry_price")
    comment = (item.get("reason") or "TG Manual Exec")[:25]

    if execution_kind == "market":
        send_telegram_msg(f"Sending Market Order {sig} {sym} ({lot} lot) to MT5...", chat_id=chat_id)
        res = connector.send_trade_order(
            symbol=sym,
            action=sig,
            lot=lot,
            sl_points=sl_pts,
            tp_points=tp_pts,
            comment=comment,
            sl_price=sl_p,
            tp_price=tp_p
        )
        if res and res.get("status") == "SUCCESS":
            t = res.get("ticket")
            send_telegram_msg(
                f"*MARKET ORDER EXECUTED SUCCESSFULLY*\n"
                f"• *Ticket*: `#{t}`\n"
                f"• *Symbol*: `{sym}` ({sig})\n"
                f"• *Lot*: `{lot} lot`\n"
                f"• *SL / TP*: `SL {sl_p or sl_pts} | TP {tp_p or tp_pts}`\n"
                f"• *Status*: Monitored by Position Manager (BEP & Trailing Stop).",
                chat_id=chat_id
            )
        else:
            err = res.get("comment") if res else "Unknown error"
            send_telegram_msg(f"Execution Failed: `{err}`", chat_id=chat_id)

    elif execution_kind == "pending":
        send_telegram_msg(f"Placing Pending Order {etype.upper()} {sym} @ {eprice}...", chat_id=chat_id)
        res = connector.send_pending_order(
            symbol=sym,
            entry_type=etype,
            entry_price=eprice,
            lot=lot,
            sl_points=sl_pts,
            tp_points=tp_pts,
            comment=comment,
            sl_price=sl_p,
            tp_price=tp_p,
            expiration_minutes=config.PENDING_ORDER_EXPIRY_MINUTES
        )
        if res and res.get("status") == "SUCCESS":
            t = res.get("ticket")
            send_telegram_msg(
                f"*PENDING ORDER PLACED SUCCESSFULLY*\n"
                f"• *Ticket*: `#{t}`\n"
                f"• *Symbol*: `{sym}` ({etype.upper()})\n"
                f"• *Entry Price*: `{eprice}`\n"
                f"• *Lot*: `{lot} lot`\n"
                f"• *SL / TP*: `SL {sl_p or sl_pts} | TP {tp_p or tp_pts}`",
                chat_id=chat_id
            )
        else:
            err = res.get("comment") if res else "Unknown error"
            send_telegram_msg(f"Pending Order Failed: `{err}`", chat_id=chat_id)


def handle_scan_all_pairs(chat_id):
    """Scans all active rotation pairs and displays summary status."""
    symbols = config.get_active_rotation_symbols()
    send_telegram_msg(f"Scanning {len(symbols)} active rotation pairs...\n_Computing ADX, EMA Trends, and Volatility..._", chat_id=chat_id)

    def _worker():
        lines = [f"*ACTIVE ROTATION SCAN ({len(symbols)} PAIRS)*\n"]
        for s in symbols:
            try:
                tf = config.get_timeframe(s)
                df = connector.get_market_data(s, tf, num_candles=50)
                if df is None or len(df) < 20:
                    lines.append(f"• `{s}`: _Insufficient data_")
                    continue
                latest = df.iloc[-1]
                adx = latest.get("adx_14", 0.0)
                rsi = latest.get("rsi_14", 50.0)
                ema20 = latest.get("ema_20", 0.0)
                ema50 = latest.get("ema_50", 0.0)
                close = latest.get("close", 0.0)

                trend = "BULLISH" if close > ema20 > ema50 else ("BEARISH" if close < ema20 < ema50 else "SIDEWAYS")
                adx_status = "Strong Trend" if adx >= 25 else "Weak Trend"

                lines.append(
                    f"• *{s}*: `{trend}`\n"
                    f"  ADX: `{adx:.1f}` ({adx_status}) | RSI: `{rsi:.1f}`"
                )
            except Exception:
                lines.append(f"• `{s}`: _Scan error_")

        lines.append("\n_Use the menu buttons to run full 3-AI analysis on a specific pair._")
        kb = {"inline_keyboard": [[{"text": "[ Back to Menu ]", "callback_data": "cmd:menu"}]]}
        send_telegram_msg("\n".join(lines), reply_markup=kb, chat_id=chat_id)

    threading.Thread(target=_worker, daemon=True).start()


def _is_user_authorized(from_id, chat_id):
    """Checks if the user ID or chat ID matches TELEGRAM_CHAT_ID (supports single ID or comma-separated)."""
    raw = getattr(config, "TELEGRAM_CHAT_ID", "")
    if not raw:
        return True
    allowed_ids = {str(item).strip() for item in str(raw).split(",") if str(item).strip()}
    return (str(from_id).strip() in allowed_ids) or (str(chat_id).strip() in allowed_ids)


def _process_update(update):
    """Processes a single incoming Telegram update (Message or Callback Query)."""
    global _last_update_id
    up_id = update.get("update_id", 0)
    if up_id > _last_update_id:
        _last_update_id = up_id

    whitelisted = str(config.TELEGRAM_CHAT_ID).strip()

    # 1. Handle Text Messages
    msg = update.get("message")
    if msg:
        msg_from_id = str(msg.get("from", {}).get("id", "")).strip()
        msg_chat_id = str(msg.get("chat", {}).get("id", "")).strip()
        target_chat = msg_chat_id or msg_from_id or whitelisted

        if not _is_user_authorized(msg_from_id, msg_chat_id):
            print(f" [TELEGRAM BOT] Ignored message from unauthorized chat {target_chat} (from: {msg_from_id})")
            return

        text = (msg.get("text") or "").strip()
        if not text:
            return

        print(f" [TELEGRAM BOT] Received command: '{text}' from {target_chat}")
        parts = text.split()
        cmd_raw = parts[0].lower()
        cmd = cmd_raw.split("@")[0]  # Remove @botname suffix
        args = parts[1:] if len(parts) > 1 else []

        if cmd in ("/start", "/menu", "/help"):
            handle_menu_command(target_chat)
        elif cmd in ("/radar", "/levels", "/smc"):
            handle_radar_command(target_chat)
        elif cmd in ("/status", "/akun"):
            handle_status_command(target_chat)
        elif cmd in ("/posisi", "/positions", "/open"):
            handle_positions_command(target_chat)
        elif cmd in ("/scan", "/scanner"):
            handle_radar_command(target_chat)
        elif cmd in ("/analisa", "/analyze", "/signal"):
            if len(args) >= 2:
                run_ondemand_analysis(args[0], target_chat, timeframe_input=args[1])
            elif len(args) == 1:
                parts_sym = args[0].replace("-", "_").split("_")
                if len(parts_sym) == 2 and _normalize_timeframe(parts_sym[1]) in getattr(config, "TIMEFRAME_MAP", {}):
                    run_ondemand_analysis(parts_sym[0], target_chat, timeframe_input=parts_sym[1])
                else:
                    run_ondemand_analysis(args[0], target_chat)
            else:
                send_telegram_msg(
                    "Usage: `/analisa <symbol> [timeframe]`\n\n"
                    "Examples:\n"
                    "• `/analisa GBPUSD` (Default Sesi)\n"
                    "• `/analisa XAUUSD M15`\n"
                    "• `/analisa GBPUSD M30`\n"
                    "• `/analisa USDJPY H4`\n"
                    "• `/analisa BTCUSD D1`",
                    chat_id=target_chat
                )
        elif cmd in ("/close", "/tutup"):
            if args:
                handle_close_ticket(args[0], target_chat)
            else:
                send_telegram_msg("Usage: `/close <ticket>`\nExample: `/close 1207464037`", chat_id=target_chat)
        elif cmd in ("/closeall", "/close_all", "/kill"):
            handle_close_all(target_chat)
        elif cmd in ("/rekap", "/profit"):
            handle_status_command(target_chat)
        elif any(p in cmd for p in ("gbpusd", "eurjpy", "gbpaud", "audcad", "eurchf", "audchf", "cadchf", "xauusd", "btcusd", "gold", "btc")):
            tf_custom = args[0] if args else None
            run_ondemand_analysis(parts[0], target_chat, timeframe_input=tf_custom)
        return

    # 2. Handle Inline Button Callbacks
    cb = update.get("callback_query")
    if cb:
        cb_id = cb.get("id")
        cb_from_id = str(cb.get("from", {}).get("id", "")).strip()
        cb_chat_id = str(cb.get("message", {}).get("chat", {}).get("id", "")).strip()
        target_chat = cb_chat_id or cb_from_id or whitelisted

        if not _is_user_authorized(cb_from_id, cb_chat_id):
            answer_callback_query(cb_id, "Access denied.")
            return

        data = cb.get("data", "")
        answer_callback_query(cb_id)
        print(f" [TELEGRAM BOT] Button clicked: '{data}' by {target_chat}")

        if data.startswith("analyze:"):
            payload_data = data.split(":", 1)[1]
            if "_" in payload_data:
                p_sym, p_tf = payload_data.split("_", 1)
                run_ondemand_analysis(p_sym, target_chat, timeframe_input=p_tf)
            else:
                run_ondemand_analysis(payload_data, target_chat)
        elif data.startswith("exec_m:"):
            token = data.split(":", 1)[1]
            execute_cached_trade(token, "market", target_chat)
        elif data.startswith("exec_p:"):
            token = data.split(":", 1)[1]
            execute_cached_trade(token, "pending", target_chat)
        elif data.startswith("close:"):
            ticket = data.split(":", 1)[1]
            handle_close_ticket(ticket, target_chat)
        elif data == "closeall":
            handle_close_all(target_chat)
        elif data == "cmd:menu":
            handle_menu_command(target_chat)
        elif data == "cmd:radar":
            handle_radar_command(target_chat)
        elif data == "cmd:positions":
            handle_positions_command(target_chat)
        elif data == "cmd:status":
            handle_status_command(target_chat)
        elif data == "cmd:scan":
            handle_radar_command(target_chat)
        elif data == "cmd:rekap":
            handle_status_command(target_chat)


def _poll_loop():
    """Continuous polling loop for incoming Telegram updates using POST."""
    global _last_update_id
    print(" [TELEGRAM CONTROLLER] Listener active (2-Way Interactive Bot running in background)...")

    while not _stop_event.is_set():
        if not config.TELEGRAM_ENABLED or not config.TELEGRAM_BOT_TOKEN:
            time.sleep(5)
            continue

        try:
            url = _get_api_url("getUpdates")
            payload = {
                "offset": _last_update_id + 1,
                "timeout": 2,
                "allowed_updates": ["message", "callback_query"]
            }
            resp = requests.post(url, json=payload, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        _process_update(update)
            elif resp.status_code in (401, 404):
                print(f" [TELEGRAM CONTROLLER] Auth error {resp.status_code}: {resp.text[:80]}")
                time.sleep(30)
            elif resp.status_code == 409:
                time.sleep(5)
            else:
                print(f" [TELEGRAM CONTROLLER] getUpdates status {resp.status_code}: {resp.text[:80]}")
                time.sleep(2)
        except Exception:
            time.sleep(2)
        time.sleep(1)


def register_bot_commands():
    """Auto-registers the Telegram command autocomplete list via setMyCommands API."""
    if not config.TELEGRAM_ENABLED or not config.TELEGRAM_BOT_TOKEN:
        return False
    commands = [
        {"command": "menu", "description": "Interactive Control Menu & Actions"},
        {"command": "analisa", "description": "3-AI Analysis (e.g. /analisa GBPUSD M15)"},
        {"command": "radar", "description": "22-Pair SMC Quant Scanner & Key Levels"},
        {"command": "posisi", "description": "View & Manage Open Positions"},
        {"command": "status", "description": "Account & Risk Intelligence Status"},
        {"command": "closeall", "description": "Emergency Close All Positions"}
    ]
    try:
        url = _get_api_url("setMyCommands")
        resp = requests.post(url, json={"commands": commands}, timeout=8)
        if resp.status_code == 200 and resp.json().get("ok"):
            print(" [TELEGRAM BOT] Clean command menu registered in Telegram API.")
            return True
    except Exception as e:
        print(f"[TG BOT ERROR] Failed to register setMyCommands: {e}")
    return False


def start_telegram_listener():
    """Starts the background Telegram listener thread."""
    global _listener_thread
    if not config.TELEGRAM_ENABLED:
        return
    register_bot_commands()
    if _listener_thread and _listener_thread.is_alive():
        return

    _stop_event.clear()
    _listener_thread = threading.Thread(target=_poll_loop, daemon=True, name="TelegramListener")
    _listener_thread.start()


def stop_telegram_listener():
    """Signals the Telegram listener thread to stop."""
    _stop_event.set()
