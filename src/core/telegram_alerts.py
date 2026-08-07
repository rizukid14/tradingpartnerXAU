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


def alert_trade_result(signal, ticket, comment):
    """Send trade execution result."""
    text = (
        f"📋 *Hasil Eksekusi*\n"
        f"• Signal: `{signal}`\n"
        f"• Ticket: `#{ticket}`\n"
        f"• Status: `{comment}`"
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


def alert_symbol_switch(from_symbol, to_symbol):
    """Send notification when the bot rotates symbols (XAUUSD weekday -> BTCUSD weekend)."""
    text = (
        f"🔄 *Symbol Switch*\n"
        f"• Dari: `{from_symbol}`\n"
        f"• Ke: `{to_symbol}`\n"
        f"• Trade berlanjut di simbol baru."
    )
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
