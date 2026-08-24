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
                       setup="", reason="", invalidation=""):
    """Send trade entry alert with full technical and AI context."""
    emoji = "🟢" if signal == "BUY" else "🔴"
    mode_tag = " RECOVERY" if recovery_mode else (" DRY RUN" if config.DRY_RUN else " LIVE")
    sym = symbol or config.SYMBOL

    rr_str = ""
    if sl_points and sl_points > 0 and tp_points:
        rr_str = f" | R:R {tp_points/sl_points:.2f}:1"

    sl_str = f"`{sl_price}` ({sl_points} pts)" if sl_price else f"`{sl_points} pts`"
    tp_str = f"`{tp_price}` ({tp_points} pts{rr_str})" if tp_price else f"`{tp_points} pts`"

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
                               setup="", reason="", invalidation="", expiration_minutes=120):
    """Send rich notification when a pending order (buy_stop, sell_stop, buy_limit, sell_limit) is placed."""
    emoji = "⏳"
    etype_upper = (entry_type or "pending").upper()
    sym = symbol or config.SYMBOL

    rr_str = ""
    if sl_points and sl_points > 0 and tp_points:
        rr_str = f" | R:R {tp_points/sl_points:.2f}:1"

    sl_str = f"`{sl_price}` ({sl_points} pts)" if sl_price else f"`{sl_points} pts`"
    tp_str = f"`{tp_price}` ({tp_points} pts{rr_str})" if tp_price else f"`{tp_points} pts`"

    lines = [
        f"{emoji} *Pending Order Terpasang: {etype_upper}*",
        f"• *Symbol*: `{sym}`",
        f"• *Ticket*: `#{ticket}`",
        f"• *Entry Price*: `{entry_price}`",
        f"• *Lot Size*: `{lot}`",
        f"• *Stop Loss*: {sl_str}",
        f"• *Take Profit*: {tp_str}",
    ]

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
    ptype_upper = (pos_type or "").upper()
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
    ptype_upper = (pos_type or "").upper()
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
    """Send bot startup notification with full config."""
    mode = "DRY RUN" if config.DRY_RUN else "LIVE"
    trading_mode = getattr(config, "TRADING_MODE", "xau")
    if trading_mode in ("xau_pairs", "pairs", "fx_pairs") and hasattr(config, "get_rotation_pool"):
        try:
            pool_syms = config.get_rotation_pool()
            sym_line = f"- Mode: `pairs` (Pool: `{', '.join(pool_syms)}`)\n"
        except Exception:
            sym_line = f"- Symbol: `{config.SYMBOL}`\n"
    else:
        sym_line = f"- Symbol: `{config.SYMBOL}`\n"

    # Dynamic trailing stop & BEP formatting
    if config.TRAILING_STOP_ENABLED:
        trail_act = int(getattr(config, "TRAILING_ACTIVATION_TP_PCT", 0.70) * 100)
        trail_dist = getattr(config, "TRAILING_DISTANCE_ATR_MULT_FX", 0.5)
        trail_floor = getattr(config, "TRAILING_DISTANCE_MIN_POINTS_FX", 60)
        trail_str = f"ON (aktif @ {trail_act}% TP | Dist: {trail_dist}x ATR, floor {trail_floor} pts)"
    else:
        trail_str = "OFF"

    if config.BREAK_EVEN_ENABLED:
        bep_trig = int(getattr(config, "BREAK_EVEN_TRIGGER_TP_PCT", 0.58) * 100)
        bep_str = f"ON (trigger @ {bep_trig}% TP)"
    else:
        bep_str = "OFF"

    if config.PARTIAL_CLOSE_ENABLED:
        partial_str = f"ON ({config.PARTIAL_CLOSE_PERCENT}% @ {config.PARTIAL_CLOSE_TP1_POINTS} pts)"
    else:
        partial_str = "OFF"

    pending_max = getattr(config, "PENDING_ORDER_MAX_ACTIVE", 2)
    pending_exp = getattr(config, "PENDING_ORDER_EXPIRY_MINUTES", 120)
    pending_str = f"ON (Limit/Stop AI, max {pending_max} aktif, exp {pending_exp}m)" if getattr(config, "PENDING_ORDERS_ENABLED", False) else "OFF"
    rec_str = "ON" if getattr(config, "RECOVERY_MODE_ENABLED", False) else "OFF"
    wk_str = "ON" if getattr(config, "WEEKEND_CLOSE_ENABLED", False) else "OFF"
    sess_str = "ON" if getattr(config, "SESSION_FILTER_ENABLED", False) else "OFF"

    text = (
        "🚀 *Bot Trading Multi-LLM Dimulai*\n"
        f"{sym_line}"
        f"- Lot: `{config.LOT_SIZE}` (Risk FX: `{config.RISK_PERCENT_FX}%`, Max Posisi: `{config.MAX_OPEN_POSITIONS}`)\n"
        f"- Mode Eksekusi: `{mode}`\n"
        "-----------------\n"
        "🛡️ *Proteksi Aktif:*\n"
        f"- Trailing Stop: `{trail_str}`\n"
        f"- Break-Even: `{bep_str}`\n"
        f"- Partial Close: `{partial_str}`\n"
        f"- Pending Orders: `{pending_str}`\n"
        f"- Max Daily Loss: `{getattr(config, 'MAX_DAILY_LOSS_PERCENT', 4.0)}%`\n"
        f"- Target Profit Harian: `{getattr(config, 'DAILY_PROFIT_TARGET_PERCENT', 6.0)}%`\n"
        f"- Recovery Mode: `{rec_str}`\n"
        f"- Weekend Close: `{wk_str}`\n"
        f"- Session Filter: `{sess_str}`"
    )
    return send_message(text)


def alert_daily_summary(pnl, trades_count, risk_status=None, closed_deals=None, open_positions=None, reason="Harian"):
    """Send rich end-of-day / shutdown / day-change summary to Telegram.
    - pnl: net P/L hari ini (realized)
    - trades_count: jumlah trade tertutup hari ini
    - closed_deals: list dict dari get_closed_positions_today (untuk breakdown
      per simbol, win/loss/BEP, dsb) - kalau None, diambil otomatis di sini
    - open_positions: daftar posisi masih terbuka (opsional)
    - reason: label konteks ("Harian", "Bot Mati", "Ganti Hari")
    """
    emoji = "🟢" if pnl >= 0 else "🔴"
    text = (
        f"{emoji} *Ringkasan {reason}*\n"
        f"- P/L Hari Ini: `${pnl:.2f}`\n"
        f"- Trade Tertutup: `{trades_count}`"
    )

    # Breakdown per simbol + win/loss/BEP (dari closed deals)
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
                # BEP tolerance dinamis dari komisi
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

            text += f"\n- Win/Loss: `{total_win}W - {total_loss}L`"
            if total_bep:
                text += f" (+`{total_bep}` BEP)"

            lines = []
            for sym, b in sorted(by_symbol.items(), key=lambda kv: -abs(kv[1]["pnl"])):
                wr = (b["wins"] / (b["n"] - b["bep"])) * 100 if (b["n"] - b["bep"]) > 0 else 0.0
                lines.append(
                    f"  • `{sym}`: {b['n']}T ({b['wins']}W-{b['losses']}L"
                    + (f", {b['bep']}BEP" if b["bep"] else "")
                    + f" | WR {wr:.0f}%) Net `${b['pnl']:+.2f}`"
                )
            text += "\n" + "\n".join(lines)
    except Exception:
        pass

    # Posisi masih terbuka (floating)
    if open_positions:
        try:
            total_float = sum(p.get("profit", 0.0) for p in open_positions)
            lines = [f"  • `{p.get('symbol')}` {p.get('type')} {p.get('volume')} lot "
                     f"${p.get('profit', 0.0):+.2f}" for p in open_positions[:8]]
            text += (
                f"\n-----------------\n"
                f"📌 *Posisi Terbuka ({len(open_positions)}):*\n"
                + "\n".join(lines)
                + f"\n  Floating P/L: `${total_float:+.2f}`"
            )
        except Exception:
            pass

    # Risk status
    if risk_status:
        text += (
            f"\n-----------------\n"
            f"- Recovery Mode: `{'Ya' if risk_status.get('recovery_mode') else 'Tidak'}`\n"
            f"- Loss Berturut: `{risk_status.get('consecutive_losses', 0)}`"
        )
    send_message(text)


def alert_consensus_hold(result, symbol=None):
    """
    Send smart 'Close Call' HOLD alert to Telegram.
    - Suppresses 'pure_hold' (all models agree on HOLD / sideways) to prevent spam.
    - Sends alerts for 'atr_gate' (trade rejected by ATR volatility gate),
      'low_confidence' (single AI proposed entry but confidence < threshold),
      or 'split_vote' (multi-AI proposed entry but couldn't reach consensus).

    NOTE (18 Agu): fungsi ini TIDAK lagi dipanggil langsung per-symbol dari
    main.py. HOLD sekarang di-recap jadi SATU pesan per cycle via alert_hold_recap().
    Fungsi ini dipertahankan untuk kompatibilitas / pemanggil lain.
    """
    if not config.TELEGRAM_ENABLED:
        return False

    if not getattr(config, "TELEGRAM_NOTIFY_HOLD", True):
        return False

    hold_type = result.get("hold_type")
    if not hold_type or hold_type == "pure_hold":
        return False

    sym = symbol or config.SYMBOL
    decisions = result.get("decisions", {})

    if hold_type == "atr_gate":
        cand_sig = result.get("candidate_signal", "ENTRY")
        models_str = ", ".join(result.get("agreeing_models", [])) or "AI"
        reason = result.get("sltp_reason", result.get("details", ""))
        text = (
            f"⚠️ *Trade Dibatalkan (Gate ATR)*\n"
            f"- Symbol: `{sym}`\n"
            f"- Sinyal: `{cand_sig}` (Sepakat: `{models_str}`)\n"
            f"- Alasan: {reason}\n"
            f"- Catatan: Menjaga R:R 2:1 & menghindari noise pasar."
        )
        return send_message(text)

    elif hold_type == "low_confidence":
        for m_name, dec in decisions.items():
            sig = dec.get("signal")
            if sig in ("BUY", "SELL"):
                conf = (dec.get("confidence") or 0.0) * 100
                thresh = (result.get("threshold") or 0.6) * 100
                setup = (dec.get("setup") or dec.get("reasoning") or "Sinyal nanggung").strip()
                text = (
                    f"⏸️ *Konsensus HOLD (Low Confidence)*\n"
                    f"- Symbol: `{sym}`\n"
                    f"- Model: `{m_name}` usul *{sig}*\n"
                    f"- Keyakinan: `{conf:.1f}%` (Batas minimal `{thresh:.1f}%`)\n"
                    f"- Setup: _{setup}_\n"
                    f"- Status: Menunggu konfirmasi setup yang lebih solid."
                )
                return send_message(text)
        return False

    elif hold_type == "split_vote":
        lines = []
        for m_name, dec in decisions.items():
            sig = dec.get("signal") or "HOLD"
            conf = (dec.get("confidence") or 0.0) * 100
            lines.append(f"  • {m_name}: *{sig}* ({conf:.0f}%)")
        votes_str = "\n".join(lines)

        scores = result.get("direction_scores", {})
        buy_score = scores.get("BUY", 0.0)
        sell_score = scores.get("SELL", 0.0)
        thresh = result.get("threshold", 1.0)

        text = (
            f"⏸️ *Konsensus HOLD (Split Decision)*\n"
            f"- Symbol: `{sym}`\n"
            f"- Hasil Analisa AI:\n{votes_str}\n"
            f"- Skor: BUY `{buy_score:.2f}` | SELL `{sell_score:.2f}` (Min `{thresh:.2f}`)\n"
            f"- Status: Konsensus tidak tercapai, menunggu setup searah."
        )
        return send_message(text)

    return False




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
