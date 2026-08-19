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



def alert_trade_opened(signal, lot, sl_points, tp_points, recovery_mode=False, session_multiplier=1.0, symbol=None):
    """Send trade entry alert with full context."""
    emoji = "🟢" if signal == "BUY" else "🔴"
    mode_tag = " RECOVERY" if recovery_mode else (" DRY RUN" if config.DRY_RUN else " LIVE")
    sym = symbol or config.SYMBOL
    text = (
        f"{emoji} *Trade {signal} Dibuka*\n"
        f"- Symbol: `{sym}`\n"
        f"- Lot: `{lot}` (session x{session_multiplier})\n"
        f"- SL: `{sl_points}` pts | TP: `{tp_points}` pts\n"
        f"- Mode: `{mode_tag}`\n"
        f"- Partial Close: `{'ON' if config.PARTIAL_CLOSE_ENABLED else 'OFF'}` "
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
    mode = "DRY RUN" if config.DRY_RUN else " LIVE"
    trading_mode = getattr(config, "TRADING_MODE", "xau")
    if trading_mode == "xau_pairs" and hasattr(config, "get_rotation_pool"):
        try:
            pool_syms = config.get_rotation_pool()
            sym_line = f"- Mode: `xau_pairs` (Pool: `{', '.join(pool_syms)}`)\n"
        except Exception:
            sym_line = f"- Symbol: `{config.SYMBOL}`\n"
    else:
        sym_line = f"- Symbol: `{config.SYMBOL}`\n"

    text = (
        f"🚀 *Bot Trading Multi-LLM Dimulai*\n"
        f"{sym_line}"
        f"- Lot: `{config.LOT_SIZE}`\n"
        f"- Mode Eksekusi: `{mode}`\n"
        f"-----------------\n"
        f"🛡️ *Proteksi Aktif:*\n"
        f"- Trailing Stop: `{'ON' if config.TRAILING_STOP_ENABLED else 'OFF'}` "
        f"(aktivasi {config.TRAILING_ACTIVATION_POINTS} pts)\n"
        f"- Break-Even: `{'ON' if config.BREAK_EVEN_ENABLED else 'OFF'}` "
        f"(trigger {config.BREAK_EVEN_TRIGGER_POINTS} pts)\n"
        f"- Partial Close: `{'ON' if config.PARTIAL_CLOSE_ENABLED else 'OFF'}` "
        f"({config.PARTIAL_CLOSE_PERCENT}% @ {config.PARTIAL_CLOSE_TP1_POINTS} pts)\n"
        f"- Max Daily Loss: `${config.MAX_DAILY_LOSS_USD}`\n"
        f"- Recovery Mode: `{'ON' if config.RECOVERY_MODE_ENABLED else 'OFF'}`\n"
        f"- Weekend Close: `{'ON' if config.WEEKEND_CLOSE_ENABLED else 'OFF'}`\n"
        f"- Session Filter: `{'ON' if config.SESSION_FILTER_ENABLED else 'OFF'}`"
    )
    send_message(text)


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


def alert_hold_recap(hold_lines):
    """
    Kirim SATU pesan recap HOLD untuk semua simbol dalam satu cycle.
    hold_lines: list str, tiap baris = ringkasan 1 simbol (misal
    "GBPCHF: HOLD (OpenAI SELL 60%, Gemini HOLD)").
    Dipanggil dari main.py di akhir run_trading_cycle — HOLD tidak lagi
    dikirim per-symbol (anti-spam, 18 Agu).
    """
    if not config.TELEGRAM_ENABLED:
        return False
    if not getattr(config, "TELEGRAM_NOTIFY_HOLD", True):
        return False
    if not hold_lines:
        return False

    # Batasi panjang: max 12 simbol per pesan
    body = "\n".join(hold_lines[:12])
    if len(hold_lines) > 12:
        body += f"\n  ... dan {len(hold_lines) - 12} simbol lainnya"
    text = (
        f"⏸️ *Recap HOLD ({len(hold_lines)} simbol)*\n"
        f"{body}\n"
        f"_Tidak ada entry baru — menunggu setup searah._"
    )
    return send_message(text)

