"""
Telegram Alerts - Comprehensive notification module.

Combines:
- XAU-60: Clean trade/close/daily summary formatting
- xaubot-ai: Market condition context, recovery mode status, session info

Sends formatted alerts via Telegram Bot API.
Gracefully disabled if not configured.
"""
import requests
import config


def send_message(text):
    """Send a message via Telegram Bot API. Fails silently if disabled."""
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
        return resp.status_code == 200
    except Exception:
        # Gracefully handle network blocking (e.g. office firewall / ISP block) without throwing noise
        return False



def alert_trade_opened(signal, lot, sl_points, tp_points, recovery_mode=False, session_multiplier=1.0):
    """Send trade entry alert with full context."""
    emoji = "🟢" if signal == "BUY" else "🔴"
    mode_tag = "🔄 RECOVERY" if recovery_mode else ("⚠️ DRY RUN" if config.DRY_RUN else "🔥 LIVE")
    text = (
        f"{emoji} *Trade {signal} Dibuka*\n"
        f"• Symbol: `{config.SYMBOL}`\n"
        f"• Lot: `{lot}` (session x{session_multiplier})\n"
        f"• SL: `{sl_points}` pts | TP: `{tp_points}` pts\n"
        f"• Mode: `{mode_tag}`\n"
        f"• Partial Close: `{'ON' if config.PARTIAL_CLOSE_ENABLED else 'OFF'}` "
        f"({config.PARTIAL_CLOSE_PERCENT}% @ {config.PARTIAL_CLOSE_TP1_POINTS} pts)"
    )
    send_message(text)


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
    """Buffer order error for cycle recap."""
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
        f"📋 *Hasil Eksekusi*\n"
        f"• Signal: `{signal}`\n"
        f"• Ticket: `#{ticket}`\n"
        f"• Status: `{comment}`"
    )
    send_message(text)


def alert_trade_closed(pos_type, ticket, profit_usd, comment=""):
    """Send alert when a trade closes (Hit TP or Hit SL)."""
    is_win = profit_usd >= 0
    icon = "🎯 *[TAKE PROFIT HIT]*" if is_win else "🛑 *[STOP LOSS HIT]*"
    profit_str = f"+${profit_usd:.2f} USD" if is_win else f"-${abs(profit_usd):.2f} USD"

    text = (
        f"{icon}\n"
        f"• Ticket: `#{ticket}`\n"
        f"• Tipe: `{pos_type}`\n"
        f"• Profit/Loss: *{profit_str}*\n"
        f"• Status: `{comment[:30] if comment else 'Closed'}`"
    )
    send_message(text)


def alert_risk_halt(reason):
    """Send risk halt notification."""
    text = f"🚨 *Trading Dihentikan*\n{reason}"
    send_message(text)


def alert_weekend_close(ticket, profit, reason):
    """Send weekend close notification."""
    emoji = "💰" if profit >= 0 else "📉"
    text = (
        f"{emoji} *Weekend Close*\n"
        f"• Ticket: `#{ticket}`\n"
        f"• Profit: `${profit:.2f}`\n"
        f"• Alasan: {reason}"
    )
    send_message(text)


def alert_partial_close(ticket, closed_lot, remaining_lot, profit_points):
    """Send partial close notification."""
    text = (
        f"💰 *Partial Close (TP1)*\n"
        f"• Ticket: `#{ticket}`\n"
        f"• Ditutup: `{closed_lot}` lot\n"
        f"• Sisa: `{remaining_lot}` lot (trailing)\n"
        f"• Profit: `{profit_points:.0f}` pts"
    )
    send_message(text)


def alert_recovery_mode(active, consecutive_losses):
    """Send recovery mode toggle notification."""
    if active:
        text = (
            f"🔄 *Recovery Mode Aktif*\n"
            f"• Lot dikurangi: x{config.RECOVERY_LOT_MULTIPLIER}\n"
            f"• Loss berturut-turut: `{consecutive_losses}`\n"
            f"• Akan normal setelah 1 win"
        )
    else:
        text = "✅ *Recovery Mode Dinonaktifkan* — kembali ke lot normal."
    send_message(text)


def alert_bot_started():
    """Send bot startup notification with full config."""
    mode = "DRY RUN" if config.DRY_RUN else "🔥 LIVE"
    text = (
        f"🤖 *Bot Trading Multi-LLM Dimulai*\n"
        f"• Symbol: `{config.SYMBOL}`\n"
        f"• Lot: `{config.LOT_SIZE}`\n"
        f"• Mode: `{mode}`\n"
        f"─────────────────\n"
        f"📊 *Proteksi Aktif:*\n"
        f"• Trailing Stop: `{'ON' if config.TRAILING_STOP_ENABLED else 'OFF'}` "
        f"(aktivasi {config.TRAILING_ACTIVATION_POINTS} pts)\n"
        f"• Break-Even: `{'ON' if config.BREAK_EVEN_ENABLED else 'OFF'}` "
        f"(trigger {config.BREAK_EVEN_TRIGGER_POINTS} pts)\n"
        f"• Partial Close: `{'ON' if config.PARTIAL_CLOSE_ENABLED else 'OFF'}` "
        f"({config.PARTIAL_CLOSE_PERCENT}% @ {config.PARTIAL_CLOSE_TP1_POINTS} pts)\n"
        f"• Max Daily Loss: `${config.MAX_DAILY_LOSS_USD}`\n"
        f"• Recovery Mode: `{'ON' if config.RECOVERY_MODE_ENABLED else 'OFF'}`\n"
        f"• Weekend Close: `{'ON' if config.WEEKEND_CLOSE_ENABLED else 'OFF'}`\n"
        f"• Session Filter: `{'ON' if config.SESSION_FILTER_ENABLED else 'OFF'}`"
    )
    send_message(text)


def alert_daily_summary(pnl, trades_count, risk_status=None):
    """Send end-of-day summary with risk status."""
    emoji = "💰" if pnl >= 0 else "📉"
    text = (
        f"{emoji} *Ringkasan Harian*\n"
        f"• P/L Hari Ini: `${pnl:.2f}`\n"
        f"• Jumlah Trade: `{trades_count}`"
    )
    if risk_status:
        text += (
            f"\n─────────────────\n"
            f"• Recovery Mode: `{'Ya' if risk_status.get('recovery_mode') else 'Tidak'}`\n"
            f"• Loss Berturut: `{risk_status.get('consecutive_losses', 0)}`"
        )
    send_message(text)
