"""
Telegram Alerts - Comprehensive notification module.

Combines:
- XAU-60: Clean trade/close/daily summary formatting
- xaubot-ai: Market condition context, recovery mode status, session info

Sends formatted alerts via Telegram Bot API.
Gracefully disabled if not configured.
"""
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import config


def _clean_md(val):
    """Escapes or cleans Markdown v1 special characters from dynamic AI/user strings."""
    if not val:
        return ""
    s = str(val).replace("\\", "")
    return s.replace("_", "\\_").replace("*", "\\*")


def send_message(text):
    """Send a message via Telegram Bot API with automatic plain text fallback."""
    if not config.TELEGRAM_ENABLED:
        return False

    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False

    try:
        api_base = getattr(config, "TELEGRAM_API_BASE", "https://api.telegram.org")
        url = f"{api_base}/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=5)
        if resp.status_code == 200:
            return True

        # Fallback: jika parsing Markdown ditolak Telegram (400), kirim ulang sebagai Plain Text
        plain_payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
        }
        resp2 = requests.post(url, json=plain_payload, timeout=5)
        return resp2.status_code == 200
    except Exception:
        # Gracefully handle network blocking without throwing noise
        return False



def alert_trade_opened(signal, lot, sl_points, tp_points, recovery_mode=False, session_multiplier=1.0, symbol=None,
                       ticket=None, entry_price=None, sl_price=None, tp_price=None, models="", confidence=0.0,
                       setup="", reason="", invalidation="", setup_grade=""):
    """Send trade entry alert with full technical, fundamental grade, and AI context."""
    emoji = "🟢" if signal == "BUY" else "🔴"
    mode_tag = " RECOVERY" if recovery_mode else (" DRY RUN" if config.DRY_RUN else " LIVE")
    sym = symbol or config.SYMBOL

    rr_str = ""
    if sl_points and sl_points > 0 and tp_points:
        rr_str = f" | R:R {tp_points/sl_points:.2f}:1"

    sl_str = f"`{sl_price}` ({sl_points} pts)" if sl_price else f"`{sl_points} pts`"
    tp_str = f"`{tp_price}` ({tp_points} pts{rr_str})" if tp_price else f"`{tp_points} pts`"

    # Evaluate Fundamental Setup Grade if not passed explicitly
    grade_line = ""
    try:
        from src.analytics.apex_fundamental_engine import apex_fundamental_engine
        fund_eval = apex_fundamental_engine.evaluate_pair(sym)
        if fund_eval and fund_eval.base:
            g_name = setup_grade or fund_eval.setup_grade
            g_icon = "👑" if "GRADE_S" in g_name else ("💎" if "GRADE_A_PLUS" in g_name else "🎯")
            grade_line = f"• *Setup Grade*: `{g_name}` {g_icon} (Delta `{fund_eval.fundamental_delta:+.2f}` │ Carry `{fund_eval.carry_spread:+.2f}%`)"
    except Exception:
        if setup_grade:
            grade_line = f"• *Setup Grade*: `{setup_grade}`"

    lines = [
        f"{emoji} *Trade {signal} Dibuka (Market Order)*",
        f"• *Symbol*: `{sym}`",
    ]
    if ticket:
        lines.append(f"• *Ticket*: `#{ticket}`")
    if entry_price:
        lines.append(f"• *Entry Price*: `{entry_price}`")
    lines.append(f"• *Lot Size*: `{lot}` (session x{session_multiplier})")
    lines.append(f"• *Stop Loss*: {sl_str}")
    lines.append(f"• *Take Profit*: {tp_str}")
    if grade_line:
        lines.append(grade_line)
    lines.append(f"• *Mode*: `{mode_tag}`")

    if models:
        conf_str = f" (Avg Conf: {confidence*100:.1f}%)" if confidence > 0 else ""
        lines.append(f"• *Model Sepakat*: `{_clean_md(models)}{conf_str}`")
    if setup:
        lines.append(f"• *Setup*: `{_clean_md(setup)}`")
    if reason:
        lines.append(f"• *Reason*: {_clean_md(reason)}")
    if invalidation:
        lines.append(f"• *Invalidation*: {_clean_md(invalidation)}")

    send_message("\n".join(lines))


def alert_pending_order_placed(symbol, entry_type, ticket, entry_price, lot, sl_points, tp_points,
                               sl_price=None, tp_price=None, models="", confidence=0.0,
                               setup="", reason="", invalidation="", expiration_minutes=120, setup_grade=""):
    """Send rich notification when a pending order (buy_stop, sell_stop, buy_limit, sell_limit) is placed."""
    emoji = "⏳"
    etype_upper = (entry_type or "pending").upper()
    sym = symbol or config.SYMBOL

    rr_str = ""
    if sl_points and sl_points > 0 and tp_points:
        rr_str = f" | R:R {tp_points/sl_points:.2f}:1"

    sl_str = f"`{sl_price}` ({sl_points} pts)" if sl_price else f"`{sl_points} pts`"
    tp_str = f"`{tp_price}` ({tp_points} pts{rr_str})" if tp_price else f"`{tp_points} pts`"

    grade_line = ""
    try:
        from src.analytics.apex_fundamental_engine import apex_fundamental_engine
        fund_eval = apex_fundamental_engine.evaluate_pair(sym)
        if fund_eval and fund_eval.base:
            g_name = setup_grade or fund_eval.setup_grade
            g_icon = "👑" if "GRADE_S" in g_name else ("💎" if "GRADE_A_PLUS" in g_name else "🎯")
            grade_line = f"• *Setup Grade*: `{g_name}` {g_icon} (Delta `{fund_eval.fundamental_delta:+.2f}` │ Carry `{fund_eval.carry_spread:+.2f}%`)"
    except Exception:
        if setup_grade:
            grade_line = f"• *Setup Grade*: `{setup_grade}`"

    lines = [
        f"{emoji} *Pending Order Terpasang: {etype_upper}*",
        f"• *Symbol*: `{sym}`",
        f"• *Ticket*: `#{ticket}`",
        f"• *Entry Price*: `{entry_price}`",
        f"• *Lot Size*: `{lot}`",
        f"• *Stop Loss*: {sl_str}",
        f"• *Take Profit*: {tp_str}",
    ]
    if grade_line:
        lines.append(grade_line)

    if models:
        conf_str = f" (Avg Conf: {confidence*100:.1f}%)" if confidence > 0 else ""
        lines.append(f"• *Model Sepakat*: `{_clean_md(models)}{conf_str}`")
    if setup:
        lines.append(f"• *Setup*: `{_clean_md(setup)}`")
    if reason:
        lines.append(f"• *Reason*: {_clean_md(reason)}")
    if invalidation:
        lines.append(f"• *Invalidation*: {_clean_md(invalidation)}")
    if expiration_minutes:
        lines.append(f"• *Expire*: `{expiration_minutes} Menit`")

    send_message("\n".join(lines))


def alert_pending_order_filled(ticket, symbol, pos_type, price, pos_id=None, sl_price=None, tp_price=None):
    """Send notification when a pending order is filled by broker (AI Proven)."""
    sym = symbol or config.SYMBOL
    ptype_upper = str(pos_type or "").upper()
    lines = [
        f"🎯 *Pending Order TER-FILL -> Posisi Aktif* (AI Proven)",
        f"• *Symbol*: `{sym}`",
        f"• *Order*: `{ptype_upper}`",
        f"• *Ticket Posisi*: `#{pos_id or ticket}`",
        f"• *Execution Price*: `{price}`",
    ]
    if sl_price or tp_price:
        lines.append(f"• *SL / TP*: `SL {sl_price or '-'} | TP {tp_price or '-'}`")
    lines.append("• *Status*: _Level entry tercapai. Posisi kini aktif & dikawal oleh Position Manager._")
    send_message("\n".join(lines))


def alert_pending_order_cancelled(ticket, symbol, pos_type, price, reason="Expired / Sinyal Berlawanan"):
    """Send notification when a pending order is cancelled or expired."""
    sym = symbol or config.SYMBOL
    ptype_upper = str(pos_type or "").upper()
    lines = [
        f"🗑️ *Pending Order Dibatalkan / Expired*",
        f"• *Symbol*: `{sym}`",
        f"• *Order*: `{ptype_upper}` @ `{price}`",
        f"• *Ticket*: `#{ticket}`",
        f"• *Alasan*: _{reason}_",
    ]
    send_message("\n".join(lines))



from datetime import datetime
from zoneinfo import ZoneInfo

WIB = ZoneInfo("Asia/Jakarta")
_failed_orders_recap = []


def buffer_failed_order(symbol, action, lot, sl_points, tp_points, sl_price=None, tp_price=None, req_price=None, retcode="N/A", comment="Unknown error", thesis="", entry_type=None):
    """Buffer a failed order details entry for batch recap Telegram dispatch."""
    _failed_orders_recap.append({
        "symbol": symbol or config.SYMBOL,
        "action": action,
        "lot": lot,
        "sl_points": sl_points,
        "tp_points": tp_points,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "req_price": req_price,
        "retcode": retcode,
        "comment": comment,
        "thesis": thesis,
        "entry_type": entry_type or "market",
        "timestamp": datetime.now(WIB).strftime("%H:%M:%S WIB")
    })


def alert_order_error(symbol, signal, lot, sl_points, tp_points, retcode, comment, price=None, entry_type=None, sl_price=None, tp_price=None, thesis=""):
    """Buffer order error for cycle recap (and flush if standalone)."""
    buffer_failed_order(
        symbol=symbol,
        action=signal,
        lot=lot,
        sl_points=sl_points,
        tp_points=tp_points,
        sl_price=sl_price,
        tp_price=tp_price,
        req_price=price,
        retcode=retcode,
        comment=comment,
        thesis=thesis,
        entry_type=entry_type,
    )


def flush_failed_orders_recap():
    """Send a SINGLE combined recap message via Telegram for all failed orders in the cycle."""
    global _failed_orders_recap
    if not _failed_orders_recap:
        return False

    count = len(_failed_orders_recap)
    lines = [f"⚠️ *REKAP KEGAGALAN EKSEKUSI BOT ({count} Order)*"]
    lines.append("_Order gagal dieksekusi otomatis oleh MT5. Berikut detail parameter lengkap untuk order manual:_\n")

    for i, item in enumerate(_failed_orders_recap, 1):
        sym = item["symbol"]
        act = item["action"]
        lot = item["lot"]
        sl_pts = item["sl_points"] or 0
        tp_pts = item["tp_points"] or 0
        sl_p = item["sl_price"]
        tp_p = item["tp_price"]
        req_p = item["req_price"]
        code = item["retcode"]
        err = item["comment"]
        thesis = item["thesis"] or "Sinyal Consensus AI"
        etype = item["entry_type"]
        ts = item["timestamp"]

        # Calculate R:R Ratio
        rr_ratio = (tp_pts / sl_pts) if (sl_pts and sl_pts > 0 and tp_pts) else 0.0
        rr_str = f"{rr_ratio:.2f}:1" if rr_ratio > 0 else "N/A"

        kind_str = f"Pending {etype.upper()}" if etype != "market" else f"Market {act}"
        price_str = f"`{req_p}`" if req_p else "`Harga Market Live`"

        sl_str = f"`{sl_p}` ({sl_pts} pts)" if sl_p else f"`{sl_pts} pts`"
        tp_str = f"`{tp_p}` ({tp_pts} pts)" if tp_p else f"`{tp_pts} pts`"

        lines.append(
            f"*{i}. {sym} — {kind_str}*\n"
            f"• *Entry Price*: {price_str}\n"
            f"• *Lot Size*: `{lot} lot`\n"
            f"• *Stop Loss (SL)*: {sl_str}\n"
            f"• *Take Profit (TP)*: {tp_str} (R:R {rr_str})\n"
            f"• *Penyebab Gagal*: `Code {code}: {err}`\n"
            f"• *Tesis AI*: _{thesis}_\n"
            f"• *Waktu*: `{ts}`"
        )

    lines.append("\n👉 *Gunakan parameter di atas untuk membuka posisi secara manual di MT5 jika setup teknikal masih valid.*")

    msg_text = "\n\n".join(lines)
    result = send_message(msg_text)
    _failed_orders_recap.clear()
    return result


def alert_trade_result(signal, ticket, comment):
    """Send trade execution result."""
    text = (
        f" *Hasil Eksekusi*\n"
        f"- Signal: `{signal}`\n"
        f"- Ticket: `#{ticket}`\n"
        f"- Status: `{comment}`"
    )
    send_message(text)


def alert_risk_halt(reason):
    """Send risk halt notification."""
    text = f" *Trading Dihentikan*\n{reason}"
    send_message(text)


def alert_weekend_close(ticket, profit, reason):
    """Send weekend close notification."""
    emoji = "" if profit >= 0 else ""
    text = (
        f"{emoji} *Weekend Close*\n"
        f"- Ticket: `#{ticket}`\n"
        f"- Profit: `${profit:.2f}`\n"
        f"- Alasan: {reason}"
    )
    send_message(text)


def alert_partial_close(ticket, closed_lot, remaining_lot, profit_points):
    """Send partial close notification."""
    text = (
        f" *Partial Close (TP1)*\n"
        f"- Ticket: `#{ticket}`\n"
        f"- Ditutup: `{closed_lot}` lot\n"
        f"- Sisa: `{remaining_lot}` lot (trailing)\n"
        f"- Profit: `{profit_points:.0f}` pts"
    )
    send_message(text)


def alert_trade_closed(ticket, symbol, profit, reason_code=None, comment="", pos_type=None, commission=0.0):
    """Send trade close notification (TP, SL+, SL, BE, or AI/Manual exit)."""
    # BEP tolerance dinamis: minimal BREAK_EVEN_TOLERANCE_USD, tapi naik
    # mengikuti komisi aktual trade (0.01 lot = 0.06, 0.10 lot = 0.60 USD).
    tol = config.bep_tolerance_for({"commission": commission})
    comment_lower = (comment or "").lower()

    # Classify exit type (reason can be MT5 numeric code OR our string label)
    reason_str = str(reason_code).lower() if reason_code is not None else ""
    is_tp = reason_code == 5 or reason_str == "tp"
    # "sl", "sl-bep", "sl-trailing", "stop-out", dll - semua varian SL
    is_sl = reason_code == 4 or reason_str in ("sl", "sl-bep", "sl-trailing", "stop-out", "margin", "rollover", "split") or reason_str.startswith("sl")
    if is_tp or "[tp" in comment_lower:
        title = " *Trade Selesai: TAKE PROFIT (TP)*"
        status = "Target TP Max Tercapai! "
    elif is_sl or "[sl" in comment_lower:
        # Reason sudah dipisah: SL-BEP = break-even, SL-trailing = profit terkunci
        if reason_str in ("sl-trailing", "sl-bep"):
            if reason_str == "sl-trailing":
                title = " *Trade Selesai: TRAILING STOP HIT*"
                status = "Trailing SL Hit (Profit Terkunci) "
            else:
                title = " *Trade Selesai: BREAK-EVEN (BE)*"
                status = "Break-Even Hit "
        elif profit > tol:
            title = " *Trade Selesai: STOP LOSS IN PROFIT (SL+)*"
            status = "Trailing SL / Break-Even Hit (Profit Terkunci) "
        elif abs(profit) <= tol:
            title = " *Trade Selesai: BREAK-EVEN (BE)*"
            status = "Break-Even Hit "
        else:
            title = " *Trade Selesai: STOP LOSS (SL)*"
            status = "Stop Loss Hit "
    else:
        if profit > tol:
            title = " *Trade Selesai: PROFIT (AI / Manual)*"
            status = "Ditutup AI / Manual dengan Profit "
        elif profit < -tol:
            title = " *Trade Selesai: LOSS (AI / Manual)*"
            status = "Ditutup AI / Manual dengan Loss "
        else:
            title = " *Trade Selesai: BREAK-EVEN (AI / Manual)*"
            status = "Ditutup AI / Manual di Break-Even "

    pnl_str = f"+${profit:.2f}" if profit >= 0 else f"-${abs(profit):.2f}"
    pos_str = f"- Arah: `{pos_type}`\n" if pos_type else ""

    text = (
        f"{title}\n"
        f"- Symbol: `{symbol}`\n"
        f"- Ticket: `#{ticket}`\n"
        f"{pos_str}"
        f"- Hasil P/L: `{pnl_str}`\n"
        f"- Detail: {status}"
    )
    send_message(text)



def alert_recovery_mode(active, consecutive_losses):
    """Send recovery mode toggle notification."""
    if active:
        text = (
            f" *Recovery Mode Aktif*\n"
            f"- Lot dikurangi: x{config.RECOVERY_LOT_MULTIPLIER}\n"
            f"- Loss berturut-turut: `{consecutive_losses}`\n"
            f"- Akan normal setelah 1 win"
        )
    else:
        text = " *Recovery Mode Dinonaktifkan* - kembali ke lot normal."
    send_message(text)


def alert_symbol_switch(from_symbol, to_symbol):
    """Send notification when the bot rotates symbols (XAUUSD weekday -> BTCUSD weekend)."""
    text = (
        f" *Symbol Switch*\n"
        f"- Dari: `{from_symbol}`\n"
        f"- Ke: `{to_symbol}`\n"
        f"- Trade berlanjut di simbol baru."
    )
    send_message(text)


def alert_trailing_stop(ticket, symbol, new_sl, profit_points, distance_pts=0):
    """Trailing stop updates are suppressed from Telegram to prevent spam."""
    return False


def alert_break_even(ticket, symbol, be_price):
    """Send notification when Break-Even moves SL to entry."""
    text = (
        f"🛡️ *Break-Even Activated*\n"
        f"- Symbol: `{symbol}`\n"
        f"- Ticket: `#{ticket}`\n"
        f"- SL Baru: `{be_price}` (Entry + Padding Komisi)\n"
        f"- Status: Risiko trade terkunci ke profit hijau/aman."
    )
    send_message(text)


def alert_partial_close(ticket, symbol, closed_vol, remaining_vol, profit_points):
    """Send notification when partial close locks profit at TP1."""
    text = (
        f"💰 *Partial Close (TP1)*\n"
        f"- Symbol: `{symbol}`\n"
        f"- Ticket: `#{ticket}`\n"
        f"- Ditutup: `{closed_vol} lot` (+{profit_points:.0f} pts)\n"
        f"- Sisa: `{remaining_vol} lot` (Trailing sisa posisi)"
    )
    send_message(text)


def alert_bot_started():
    """Send modern bot startup notification reflecting 2-Stage Quant Funnel architecture."""
    mode = "DRY RUN" if config.DRY_RUN else "LIVE"
    acc_id = getattr(config, "MT5_LOGIN", "27556325")
    server = getattr(config, "MT5_SERVER", "VTMarkets-Live 3")

    if config.SCANNER_MODE:
        n_pairs = len(config.get_scanner_symbols()) if hasattr(config, "get_scanner_symbols") else 22
        arch_line = (
            "🚀 *2-STAGE QUANT TRADING BOT ACTIVE*\n"
            f"• *Architecture*: `2-Stage Quant Funnel (Fast Radar 60s + 3-AI Jury)`\n"
            f"• *Universe*: `{n_pairs} Pairs (21 FX Crosses + Gold H1/D1)`\n"
            f"• *AI Jury Engine*: `Full 3-AI All-Day (OpenAI + Gemini + DeepSeek)`\n"
            f"• *Jury Protocol*: `Jury Verdict Protocol (APPROVE / REJECT)`\n"
            f"• *Risk Sizing*: `Risk {config.RISK_PERCENT_FX}% per trade | Max {config.MAX_OPEN_POSITIONS} Positions`\n"
            f"• *Account*: `{mode} ({server} #{acc_id})`\n"
            "----------------------------------------\n"
            "🛡️ *Proteksi & Filter Otomatis:*\n"
            "• *Stage 1 Radar*: `60s Sweep on SMC Levels & Dealing Range`\n"
            "• *5 Core Archetypes*: `M1 Judas + M2 Trend Pullback + M3 ADR + M4 SMC + M5 Retest`\n"
            "• *Dealing Range*: `100-bar H1 (Discount <=38% | Premium >=62%)`\n"
            "• *News Shield*: `TradingView News Window Guard Active (±6h)`\n"
            "• *Trailing Stop*: `ON (75% TP | Dist: 0.5x ATR, floor 60 pts)`\n"
            "• *Break-Even*: `ON (55% TP + Pocket Profit 1.5 pips)`\n"
            "• *Partial Close*: `ON (TP1 50% Lot liquidasi @ 55% TP)`\n"
            "• *Pre-Rollover*: `Precision Distance-to-SL Shield (03:50 WIB)`\n"
            f"• *Daily Guard*: `Max Loss {getattr(config, 'MAX_DAILY_LOSS_PERCENT', 4.0)}% | Target {getattr(config, 'DAILY_PROFIT_TARGET_PERCENT', 6.0)}%`"
        )
        return send_message(arch_line)

    # Legacy Fallback
    trading_mode = getattr(config, "TRADING_MODE", "pairs")
    pool_syms = config.get_rotation_pool() if hasattr(config, "get_rotation_pool") else [config.SYMBOL]
    
    text = (
        "🚀 *Bot Trading Multi-LLM Dimulai*\n"
        f"• *Mode*: `{trading_mode.upper()}` (Pool: `{', '.join(pool_syms)}`)\n"
        f"• *Risk*: `{config.RISK_PERCENT_FX}%` | Max Posisi: `{config.MAX_OPEN_POSITIONS}`\n"
        f"• *Eksekusi*: `{mode} ({server} #{acc_id})`\n"
        "----------------------------------------\n"
        "🛡️ *Proteksi Aktif:*\n"
        "• *Trailing Stop*: `ON (75% TP | Dist 0.5x ATR)`\n"
        "• *Break-Even*: `ON (55% TP)`\n"
        "• *Partial Close*: `ON (TP1 50% Lot @ 55% TP)`\n"
        "• *Pre-Rollover Shield*: `ON (03:50 WIB)`\n"
        f"• *Daily Guard*: `Max Loss {getattr(config, 'MAX_DAILY_LOSS_PERCENT', 4.0)}% | Target {getattr(config, 'DAILY_PROFIT_TARGET_PERCENT', 6.0)}%`"
    )
    return send_message(text)


def alert_daily_summary(pnl, trades_count, risk_status=None, closed_deals=None, open_positions=None, reason="Harian"):
    """Send rich end-of-day / shutdown / day-change summary to Telegram."""
    now_str = datetime.now(WIB).strftime("%H:%M WIB")
    pnl_emoji = "🟢" if pnl >= 0 else "🔴"
    
    header_title = "🛑 *SYSTEM SHUTDOWN REPORT — QUANT BOT*" if ("Mati" in reason or "Shutdown" in reason) else f"📊 *RINGKASAN SESI {reason.upper()} — QUANT BOT*"
    status_sub = "Selesai (Bot Offline)" if ("Mati" in reason or "Shutdown" in reason) else "Pergantian Hari / Selesai Sesi"

    lines = [
        header_title,
        f"• *Waktu*: `{now_str}` │ Sesi: `{status_sub}`",
        f"• *Realized Net P/L*: {pnl_emoji} *${pnl:+.2f}*",
        f"• *Total Eksekusi*: `{trades_count} Trades`",
        "----------------------------------------",
    ]

    try:
        if closed_deals is None:
            from src.core import mt5_connector
            closed_deals = mt5_connector.get_closed_positions_today()
        if closed_deals:
            by_symbol = {}
            total_win = total_loss = total_bep = 0
            for d in closed_deals:
                sym = d.get("symbol", "UNKNOWN")
                profit = d.get("profit", 0.0)
                bucket = by_symbol.setdefault(sym, {"n": 0, "wins": 0, "losses": 0, "bep": 0, "pnl": 0.0})
                bucket["n"] += 1
                bucket["pnl"] += profit
                tol = config.bep_tolerance_for(d) if hasattr(config, "bep_tolerance_for") else 0.04
                if abs(profit) <= tol:
                    bucket["bep"] += 1
                    total_bep += 1
                elif profit > 0:
                    bucket["wins"] += 1
                    total_win += 1
                else:
                    bucket["losses"] += 1
                    total_loss += 1

            wr_total = (total_win / (trades_count - total_bep)) * 100 if (trades_count - total_bep) > 0 else 0.0
            lines[3] = f"• *Total Eksekusi*: `{trades_count} Trades` ({total_win}W - {total_loss}L │ WR {wr_total:.0f}%)" + (f" (+{total_bep} BEP)" if total_bep else "")

            sym_lines = []
            for sym, b in sorted(by_symbol.items(), key=lambda kv: -abs(kv[1]["pnl"])):
                wr = (b["wins"] / (b["n"] - b["bep"])) * 100 if (b["n"] - b["bep"]) > 0 else 0.0
                sym_clean = sym.replace("-ECNc", "").replace("-ECN", "").replace(".c", "")
                sym_lines.append(
                    f"• `{sym_clean}`: {b['n']}T ({b['wins']}W-{b['losses']}L"
                    + (f", {b['bep']}BEP" if b["bep"] else "")
                    + f" │ WR {wr:.0f}%) Net `${b['pnl']:+.2f}`"
                )
            if sym_lines:
                lines.append("📊 *Breakdown Instrumen:*")
                lines.extend(sym_lines)
                lines.append("----------------------------------------")
    except Exception:
        pass

    # Status Posisi Terakhir
    lines.append("📌 *Status Posisi Terakhir:*")
    if open_positions:
        try:
            total_float = sum(p.get("profit", 0.0) for p in open_positions)
            f_emoji = "🟢" if total_float >= 0 else "🔴"
            lines.append(f"• *Posisi Terbuka*: `{len(open_positions)} Tiket` │ Floating: {f_emoji} `${total_float:+.2f}`")
            for p in open_positions[:6]:
                sym_clean = p.get('symbol', '').replace("-ECNc", "").replace("-ECN", "").replace(".c", "")
                lines.append(f"  └─ `{sym_clean}` {p.get('type')} {p.get('volume')} lot `${p.get('profit', 0.0):+.2f}`")
        except Exception:
            pass
    else:
        lines.append("• *Posisi Terbuka*: `Nihil (Semua Tiket Bersih / Flat)`")

    # Risk Status
    lines.append("----------------------------------------")
    lines.append("🛡️ *Keamanan & Modal:*")
    rec_mode = "Aktif" if risk_status and risk_status.get('recovery_mode') else "Tidak Aktif"
    streak = risk_status.get('consecutive_losses', 0) if risk_status else 0
    lines.append(f"• *Max Daily Loss*: `{getattr(config, 'MAX_DAILY_LOSS_PERCENT', 4.0)}%` (Terjaga)")
    lines.append(f"• *Loss Streak*: `{streak}` (Recovery: `{rec_mode}`)")
    lines.append(f"• *MT5 Status*: Magic `{getattr(config, 'MAGIC_NUMBER', 20260625)}` Offline")
    lines.append("----------------------------------------")
    lines.append("_Sistem berhenti dengan aman. Posisi & modal terlindungi._")

    return send_message("\n".join(lines))


def alert_consensus_hold(result, symbol=None):
    """Send smart 'Close Call' HOLD alert to Telegram."""
    if not config.TELEGRAM_ENABLED:
        return False
    return True


def alert_hold_recap(hold_lines, news_context=None):
    """Kirim SATU pesan recap HOLD dan Economic News Alert untuk semua simbol dalam satu cycle."""
    if not config.TELEGRAM_ENABLED:
        return False
    if not getattr(config, "TELEGRAM_NOTIFY_HOLD", True):
        return False
    if not hold_lines and not news_context:
        return False

    news_header = ""
    if news_context and news_context.strip():
        news_header = "📰 *High-Impact News Alert (6h Window)*:\n" + news_context.strip() + "\n\n"

    n = len(hold_lines) if hold_lines else 0
    body = "\n".join(hold_lines[:12]) if hold_lines else "• _Semua simbol aman_"
    if hold_lines and len(hold_lines) > 12:
        body += f"\n  ... dan {len(hold_lines) - 12} simbol lainnya"
    text = (
        news_header
        + f"⏸️ *Recap Scan ({n} Simbol)*\n"
        + body + "\n\n"
        + "_Manajemen posisi dan proteksi risiko berjalan 24/7._"
    )
    return send_message(text)


def alert_hourly_radar_recap(scanner=None, open_positions=None, today_pnl=0.0, risk=None, recent_opened=None, recent_vetoed=None):
    """
    Send comprehensive 3-Hourly SMC Radar & Portfolio Pulse Digest to Telegram.
    """
    if not config.TELEGRAM_ENABLED:
        return False
    if not getattr(config, "ENABLE_HOURLY_RADAR_RECAP", True):
        return False

    now = datetime.now(WIB)
    time_str = now.strftime("%H:%M WIB")

    lines = [
        "📊 *QUANT PULSE 3H — EXECUTIVE DIGEST*",
        f"🕒 `{time_str}` │ Server: `VTMarkets-Live 3 (#27556325)`",
        "━" * 28,
        "",
        "💼 *PORTOFOLIO & EKSEKUSI*",
    ]

    total_float = sum(p.get("profit", 0.0) for p in (open_positions or []))
    pnl_emoji = "🟢" if today_pnl >= 0 else "🔴"
    float_emoji = "🟢" if total_float >= 0 else "🔴"
    lines.append(f"• Realized Today : {pnl_emoji} *${today_pnl:+.2f}* │ Floating: {float_emoji} *${total_float:+.2f}*")

    if open_positions:
        pos_strs = []
        for p in open_positions[:4]:
            sym_c = p.get("symbol", "?").replace("-ECNc", "").replace("-ECN", "").replace(".c", "")
            pos_strs.append(f"`{sym_c}` {p.get('type')} {p.get('volume')}l (`${p.get('profit', 0.0):+.2f}`)")
        lines.append(f"• Posisi Aktif   : {len(open_positions)}/6 ({', '.join(pos_strs)})")
    else:
        lines.append("• Posisi Aktif   : `0/6 (Flat / Ready)`")

    if recent_opened:
        op_list = []
        for o in recent_opened[-3:]:
            sym_c = o.get('symbol', '').replace("-ECNc", "").replace("-ECN", "").replace(".c", "")
            op_list.append(f"`{sym_c}` {o.get('signal')} ({o.get('lot')}l)")
        lines.append(f"• Order Baru (3h): {', '.join(op_list)}")
    else:
        lines.append("• Order Baru (3h): `Nihil (Semua syarat terfilter aman)`")

    if recent_vetoed:
        vt_list = []
        for v in recent_vetoed[-2:]:
            sym_c = v.get('symbol', '').replace("-ECNc", "").replace("-ECN", "").replace(".c", "")
            vt_list.append(f"`{sym_c}` ({v.get('reason', 'Risk')[:20]})")
        lines.append(f"• Veto CRO (3h)  : {', '.join(vt_list)}")
    else:
        lines.append("• Veto CRO (3h)  : `Nihil (Zero false signal)`")

    # Boitoki Currency Strength Matrix
    try:
        from src.analytics import currency_strength
        scores, ranks = currency_strength.calculate_boitoki_csm()
        if scores:
            sorted_cur = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            top2 = [f"*{c}* (`{s:+.1f}`)" for c, s in sorted_cur[:2]]
            bot2 = [f"*{c}* (`{s:+.1f}`)" for c, s in sorted_cur[-2:]]
            lead_c, lead_s = sorted_cur[0]
            lagg_c, lagg_s = sorted_cur[-1]
            disp = round(lead_s - lagg_s, 1)

            lines.append("")
            lines.append("🌐 *ARUS MATA UANG (Boitoki CSM H1)*")
            lines.append(f"• 🟢 Top Inflow  : {', '.join(top2)}")
            lines.append(f"• 🔴 Top Outflow : {', '.join(bot2)}")
            lines.append(f"• ⚡ Max Spread  : `{lead_c}/{lagg_c}` (Δ `{disp:+.1f}`)")
    except Exception:
        pass

    # Macro Compass & Dealing Range
    if scanner is not None and getattr(scanner, "macro_cache", None):
        bull_c = sum(1 for m in scanner.macro_cache.values() if m.get('is_bull'))
        bear_c = sum(1 for m in scanner.macro_cache.values() if m.get('is_bear'))
        range_c = len(scanner.macro_cache) - bull_c - bear_c

        disc_pairs = []
        prem_pairs = []
        for sym, m in scanner.macro_cache.items():
            clean = sym.replace("-ECNc", "").replace("-ECN", "").replace(".c", "")
            pos = m.get('dealing_range_pos', 0.5)
            if pos <= 0.382:
                disc_pairs.append((clean, pos))
            elif pos >= 0.618:
                prem_pairs.append((clean, pos))

        disc_pairs.sort(key=lambda x: x[1])
        prem_pairs.sort(key=lambda x: -x[1])

        lines.append("")
        lines.append(f"🧭 *KOMPAS MAKRO & DEALING RANGE ({len(scanner.macro_cache)} Pairs)*")
        lines.append(f"• Struktur Tren  : 🟢 Bull ({bull_c}) │ 🔴 Bear ({bear_c}) │ ⚪ Range ({range_c})")
        if disc_pairs:
            disc_str = ", ".join([f"`{s}` ({int(p*100)}%)" for s, p in disc_pairs[:3]])
            lines.append(f"• 🛒 Top Diskon  : {disc_str} ➔ _Siaga BUY_")
        else:
            lines.append("• 🛒 Top Diskon  : _Semua pair di harga normal_")

        if prem_pairs:
            prem_str = ", ".join([f"`{s}` ({int(p*100)}%)" for s, p in prem_pairs[:3]])
            lines.append(f"• 🏷️ Top Premium : {prem_str} ➔ _Siaga SELL_")
        else:
            lines.append("• 🏷️ Top Premium : _Semua pair di harga normal_")

    # High-Impact News Context
    try:
        from src.analytics import economic_calendar
        cal_obj = getattr(economic_calendar, "calendar", None)
        if cal_obj:
            all_events = cal_obj.get_events(now)
            upcoming_news = [e for e in all_events if now <= e["dt"] <= (now + timedelta(hours=12))]
            lines.append("")
            lines.append("📰 *JADWAL BERITA HIGH-IMPACT (±12 Jam)*")
            if upcoming_news:
                for ne in upcoming_news[:3]:
                    t_rel = ne['dt'].strftime('%H:%M WIB')
                    flag = ne.get('country', 'US')
                    lines.append(f"• `[{t_rel}]` *{flag}*: `{ne['name']}`")
            else:
                lines.append("• _Tenang (Tidak ada rilis berita High-Impact terdekat)_")
    except Exception:
        pass

    lines.append("━" * 28)

    kb = {
        "inline_keyboard": [
            [
                {"text": "📡 [ Live Radar ]", "callback_data": "cmd:radar"},
                {"text": "🧭 [ MSE Strategy ]", "callback_data": "cmd:macro_menu"},
                {"text": "☰ [ Menu ]", "callback_data": "cmd:menu"}
            ]
        ]
    }

    return send_message("\n".join(lines), reply_markup=kb)


def alert_trihourly_radar_recap(scanner=None, open_positions=None, today_pnl=0.0, risk=None, recent_opened=None, recent_vetoed=None):
    """Direct alias for 3-hour radar recap."""
    return alert_hourly_radar_recap(scanner, open_positions, today_pnl, risk, recent_opened, recent_vetoed)


def alert_radar_go_transition(symbol, setup_type="RECLAIM_CONFIRMED_GO", trigger_price=0.0, dr_pos=0.0, action_tier="FULL_ALLOW", bias_score=0.0):
    """
    Sends an instant high-priority Telegram alert when a symbol transitions to 'Permission GO'.
    Only triggered for confirmed reclaim setups (A+ opportunity) to prevent noise.
    """
    clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
    now_str = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%H:%M:%S WIB")
    
    tier_emoji = "🟢" if action_tier == "FULL_ALLOW" else ("🟡" if action_tier == "REDUCED_CONFIDENCE" else "🟠")
    
    lines = [
        f"🚀 *[RADAR GO ALERT] {clean_sym} AKTIF*",
        f"🕒 `{now_str}` | {tier_emoji} *Tier:* `{action_tier}`",
        "━" * 28,
        f"• 🎯 *Setup:* `{setup_type}`",
        f"• 📊 *Dealing Range:* `{int(dr_pos*100)}% (Zona Diskon)`",
        f"• 🧭 *Macro Bias:* `{bias_score:+.2f}`",
        f"• 📍 *Trigger Level:* `{trigger_price:.5f}`" if trigger_price > 0 else "",
        "━" * 28,
        "⚡ _Candle Reclaim terkonfirmasi. Stage 2 (3-LLM Jury) sedang memproses sinyal._"
    ]
    lines = [l for l in lines if l]
    return send_message("\n".join(lines))

