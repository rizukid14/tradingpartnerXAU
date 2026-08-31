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
from datetime import datetime
from zoneinfo import ZoneInfo
import config
from src.core import mt5_connector as connector
from src.core.risk_engine import RiskEngine
from src.core import llm_client
from src.core import consensus
from src.analytics.macro_strategic_engine import macro_strategic_engine

_risk_engine = RiskEngine()
WIB = ZoneInfo("Asia/Jakarta")


_listener_thread = None
_stop_event = threading.Event()
_last_update_id = 0
_cached_analyses = {}  # { token: { symbol, signal, lot, sl_points, tp_points, sl_price, tp_price, ... } }


def _get_api_url(method):
    api_base = getattr(config, "TELEGRAM_API_BASE", "https://api.telegram.org")
    return f"{api_base}/bot{config.TELEGRAM_BOT_TOKEN}/{method}"


def _sanitize_tg_markdown(text: str) -> str:
    """
    Converts standard GitHub markdown (**bold**, __italic__, snake_case_words)
    into clean Telegram Legacy Markdown compatible format so Telegram parser never fails.
    """
    if not text:
        return text
    
    # 1. Convert Markdown headers (### Header) to bold
    text = re.sub(r'^#{1,6}\s*(.+)$', r'*\1*', text, flags=re.MULTILINE)
    
    # 2. Convert double asterisks **bold** to single asterisk *bold*
    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
    
    # 3. Replace snake_case underscores inside uppercase words (e.g. BULLISH_EXPANSION -> BULLISH EXPANSION)
    # so they don't break Telegram italics
    text = re.sub(r'\b[A-Z0-9]+_[A-Z0-9_]+\b', lambda m: m.group(0).replace('_', ' '), text)

    return text


def send_telegram_msg(text, reply_markup=None, chat_id=None):
    """Send message to Telegram with optional inline keyboard."""
    if not config.TELEGRAM_ENABLED or not config.TELEGRAM_BOT_TOKEN:
        return False
    target_chat = chat_id or config.TELEGRAM_CHAT_ID
    if not target_chat:
        return False

    sanitized_text = _sanitize_tg_markdown(text)
    payload = {
        "chat_id": target_chat,
        "text": sanitized_text,
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


def send_chat_action(action="typing", chat_id=None):
    """Send chat action (e.g. typing) to Telegram."""
    if not config.TELEGRAM_ENABLED or not config.TELEGRAM_BOT_TOKEN:
        return
    target_chat = chat_id or config.TELEGRAM_CHAT_ID
    if not target_chat:
        return
    try:
        url = _get_api_url("sendChatAction")
        requests.post(url, json={"chat_id": target_chat, "action": action}, timeout=5)
    except Exception:
        pass


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


def handle_csm_command(chat_id):
    """Sends the Dual-Horizon Boitoki CSM & Flow Velocity report."""
    try:
        from src.analytics.currency_strength import calculate_boitoki_csm
        scores_h1, _ = calculate_boitoki_csm(config.mt5.TIMEFRAME_H1, lookback_bars=24)
        scores_m15, _ = calculate_boitoki_csm(config.mt5.TIMEFRAME_M15, lookback_bars=16)

        if not scores_h1:
            send_telegram_msg("⚠️ CSM Engine initializing... Please try again in 5 seconds.", chat_id=chat_id)
            return

        sorted_h1 = sorted(scores_h1.items(), key=lambda x: x[1], reverse=True)
        sorted_m15 = sorted(scores_m15.items(), key=lambda x: x[1], reverse=True) if scores_m15 else []

        raw_syms = getattr(config, "SCANNER_SYMBOLS", [])
        majors_26 = [s.replace("-ECNc", "").replace("-ECN", "").replace(".c", "") for s in raw_syms]
        deltas = []
        for p in majors_26:
            base, quote = p[:3], p[3:6]
            b_s = scores_m15.get(base, 0.0) if scores_m15 else 0.0
            q_s = scores_m15.get(quote, 0.0) if scores_m15 else 0.0
            deltas.append((p, b_s - q_s))

        sorted_deltas = sorted(deltas, key=lambda x: x[1], reverse=True)
        top_in = sorted_deltas[:3]
        top_out = sorted_deltas[-3:]

        in_str = "\n".join([f"• *{p}*: `+{d:.1f} pts` (Bullish Inflow)" for p, d in top_in if d > 0]) or "• None"
        out_str = "\n".join([f"• *{p}*: `{d:.1f} pts` (Bearish Outflow)" for p, d in reversed(top_out) if d < 0]) or "• None"

        msg = (
            f"🌐 *DUAL-HORIZON BOITOKI CSM RADAR*\n"
            f"Timestamp: `{time.strftime('%H:%M:%S WIB')}` | Horizon: `24h Macro vs 4h Session`\n\n"
            f"📊 *24-Hour Macro Flow (H1)*:\n"
            f"{' | '.join([f'`{c} {s:+.1f}`' for c, s in sorted_h1])}\n\n"
            f"⚡ *4-Hour Session Velocity (M15)*:\n"
            f"{' | '.join([f'`{c} {s:+.1f}`' for c, s in sorted_m15])}\n\n"
            f"🚀 *Top Inflow Pairs (M15)*:\n{in_str}\n\n"
            f"🔻 *Top Outflow Pairs (M15)*:\n{out_str}\n"
        )

        kb = {
            "inline_keyboard": [
                [{"text": "🔄 Refresh CSM", "callback_data": "cmd:csm"}],
                [{"text": "📡 [ SMC Radar 26 Pairs ]", "callback_data": "cmd:radar"}],
                [{"text": "« Back to Menu", "callback_data": "cmd:menu"}]
            ]
        }
        send_telegram_msg(msg, reply_markup=kb, chat_id=chat_id)
    except Exception as e:
        print(f"[TG BOT ERROR] handle_csm_command: {e}")
        send_telegram_msg(f"Error fetching CSM: `{e}`", chat_id=chat_id)


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


def handle_indicators_command(chat_id, symbol_input=None):
    """Sends exact price levels for Dealing Range (High, Low, Equilibrium), Discount/Premium Zones, and SMC Order Blocks."""
    try:
        from src.analytics.market_scanner import MarketScanner
        sym = connector.get_valid_trade_symbol(symbol_input or config.SYMBOL)
        clean_sym = sym.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "")
        
        scanner = MarketScanner()
        scanner.update_macro_context(connector, force=False)
        smc = scanner.get_symbol_smc_levels(clean_sym)
        
        tick = connector.get_current_tick(sym)
        cur_price = tick.get("bid", 0.0) if tick else 0.0
        pt = tick.get("point", 1e-5) if tick else 1e-5
        dec = 2 if pt >= 0.01 else 5
        cur_price_str = f"{cur_price:.{dec}f}" if cur_price > 0 else "-"
        
        if not smc:
            send_telegram_msg(f"⚠️ Data level SMC untuk *{sym}* belum termuat. Coba jalankan `/radar` terlebih dahulu.", chat_id=chat_id)
            return

        lines = [
            f"🏛️ *SMC & CLUSTER STRUCTURE: {clean_sym} (H1)*",
            f"🕒 `{datetime.now(WIB).strftime('%H:%M:%S WIB')}` | Kompas: `{smc.get('trend_label', '-')}`\n",
            "📊 *DEALING RANGE 100-BAR (H1)*:",
            f"• 🔼 *100% Range High*: `{smc['range_high_100']}`",
            f"• 🔴 *Premium Zone (Sell)*: `{smc['premium_zone_start']}` - `{smc['range_high_100']}`",
            f"• ⚪ *50% Equilibrium*: `{smc['equilibrium_50']}`",
            f"• 🟢 *Discount Zone (Buy)*: `{smc['range_low_0']}` - `{smc['discount_zone_end']}`",
            f"• 🔽 *0% Range Low*: `{smc['range_low_0']}`\n",
            f"📍 *Harga Live*: `{cur_price_str}` ({smc['pos_pct']}% — *{smc['pos_label']}*)\n",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🧱 *STRUCTURAL CLUSTERS & COMPRESSION*:",
            f"• 🔴 *Resist Cluster*: `{smc.get('cluster_resistance', '-')}` (Sentuh: *{smc.get('touches_resistance', 0)}x*)",
            f"• 🟢 *Support Cluster*: `{smc.get('cluster_support', '-')}` (Sentuh: *{smc.get('touches_support', 0)}x*)",
            f"• 🌊 *Regime*: `{smc.get('wave_regime', 'NORMAL')}` (Umur: `{smc.get('range_age_hours', 24.0)}h`)\n",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🎯 *LUXALGO SMC & LIQUIDITY LEVELS*:",
            f"• 🛡️ *Strong High*: `{smc['strong_high']}`",
            f"• 🛡️ *Strong Low*: `{smc['strong_low']}`",
            f"• 🌅 *Asian Range*: `{smc['asian_low']}` - `{smc['asian_high']}`",
            f"• 🟩 *Bullish OB*: `{smc['bullish_ob']}`",
            f"• 🟥 *Bearish OB*: `{smc['bearish_ob']}`",
            f"• ⚡ *FVG*: `{smc['fvg']}`"
        ]

        kb = {
            "inline_keyboard": [
                [{"text": f"[ 🧠 AI Analisa {clean_sym} ]", "callback_data": f"analyze:{clean_sym}_H1"}],
                [{"text": "[ 📡 26-Pair SMC Radar ]", "callback_data": "cmd:radar"}, {"text": "[ ☰ Menu ]", "callback_data": "cmd:menu"}]
            ]
        }

        send_telegram_msg("\n".join(lines), reply_markup=kb, chat_id=chat_id)
    except Exception as e:
        print(f"[TG BOT ERROR] handle_indicators_command: {e}")
        send_telegram_msg(f"Error fetching indicators for `{symbol_input}`: `{e}`", chat_id=chat_id)


def handle_macro_command(chat_id, symbol_input=None):
    """Sends pure quant 6-timeframe strategic directive directly without LLM overhead (0 token, instant)."""
    try:
        from src.analytics.macro_strategic_engine import macro_strategic_engine
        sym = connector.get_valid_trade_symbol(symbol_input or config.SYMBOL)
        clean_sym = sym.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "")
        
        directive = macro_strategic_engine.get_directive(sym, mt5_connector=connector)
        
        is_crypto_or_gold = ("BTC" in clean_sym or "XAU" in clean_sym)
        pip_unit = "USD" if is_crypto_or_gold else "pips"
        
        # Calculate reload zone difference in pips
        prox_val = directive.entry_zone_proximal if hasattr(directive, 'entry_zone_proximal') and directive.entry_zone_proximal > 0 else 0.0
        if prox_val > 0:
            zone_diff = abs(directive.entry_limit_anchor - prox_val)
            diff_pips = round(zone_diff, 1) if is_crypto_or_gold else round(zone_diff / (0.01 if "JPY" in clean_sym else 0.0001), 1)
            reload_str = f"`{directive.entry_zone_proximal}` ➔ `{directive.entry_limit_anchor}` (~{diff_pips:.1f} {pip_unit})"
        else:
            reload_str = f"`{directive.entry_limit_anchor}`"

        traps_list = "\n".join([f"• {t}" for t in directive.forbidden_traps]) if directive.forbidden_traps else "• Tidak ada jebakan ekstrem."
        circuit_str = " 🚨 *CIRCUIT BREAKER*" if getattr(directive, 'hard_circuit_breaker', False) else ""

        lines = [
            f"🧭 *TOP-DOWN MACRO: {clean_sym}*",
            f"🎯 *Mandat*: `{directive.daily_macro_bias}` ({directive.macro_bias_score:+.2f}) │ *Tier*: `{directive.action_tier}`{circuit_str}",
            f"⚡ *Aksi*: `{directive.primary_execution_directive}` (Conf: {directive.confidence_score}%)\n",
            f"💡 *Gameplan*:\n_{directive.daily_mandate_thesis}_\n",
            "🎯 *Eksekusi Taktis*:",
            f"• 📍 *Reload Zone*: {reload_str}",
            f"• 🛡️ *Intraday SL*: `{directive.intraday_sl_price}` ({directive.intraday_sl_pips:.1f} {pip_unit})",
            f"• 🎁 *TP1 (50% + BEP)*: `{directive.tp1_price}` (+{directive.tp1_pips:.1f} {pip_unit} │ 1.50:1 R:R)",
            f"• 🏆 *TP2 (Target)*: `{directive.tp2_price}` (+{directive.tp2_pips:.1f} {pip_unit} │ {directive.risk_reward_ratio:.2f}:1 R:R)",
            f"• 🚫 *Invalidasi*: `{directive.invalidation_stop_price}`\n",
            f"⚠️ *Pantangan*:\n{traps_list}\n",
            f"🕒 `{datetime.now(WIB).strftime('%H:%M:%S WIB')}` │ Komputasi: `{directive.calculation_time_ms:.1f} ms` (0 Token)"
        ]
        msg_text = "\n".join(lines)

        kb = {
            "inline_keyboard": [
                [{"text": f"[ 🧠 AI Analisa {clean_sym} ]", "callback_data": f"analyze:{clean_sym}_H1"}],
                [{"text": "[ 📊 Level SMC ]", "callback_data": f"cmd:levels_{clean_sym}"}, {"text": "[ ☰ Menu ]", "callback_data": "cmd:menu"}]
            ]
        }

        send_telegram_msg(msg_text, reply_markup=kb, chat_id=chat_id)
    except Exception as e:
        print(f"[TG BOT ERROR] handle_macro_command: {e}")
        send_telegram_msg(f"Error computing macro directive for `{symbol_input}`: `{e}`", chat_id=chat_id)


def handle_help_command(chat_id):
    """Sends the complete interactive command reference guide."""
    lines = [
        "📖 *PANDUAN LENGKAP COMMAND BOT TRADING*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🧭 *ANALISIS & STRATEGI MAKRO:*",
        "• `/analisa <pair> [tf]` ➔ Analisis On-Demand 3-AI (o4-mini + Gemini + DeepSeek)",
        "  _Contoh_: `/analisa GBPUSD H1` atau `/analisa USDJPY M30`",
        "• `/macro [pair]` ➔ 6-TF Top-Down Macro Strategic Engine (Mandat, SBR/RBS, Target, Pantangan)",
        "  _Contoh_: `/macro GBPUSD` (atau `/macro` untuk menu picker)",
        "• `/fundamental [pair]` ➔ 8-Currency Composite Fundamental Scorecard & Conflict Matrix (Apex Paragon)",
        "  _Contoh_: `/fund GBPUSD` atau `/fundamental`",
        "• `/radar` ➔ Fast Radar Live Heatmap 26 Pairs (M1/M2/M3 A+ setups)",
        "• `/csm` ➔ Boitoki Currency Strength Matrix & Net Basket Delta",
        "• `/levels <pair>` ➔ Level teknikal LuxAlgo SMC, FRVP POC/VAL/VAH",
        "",
        "📰 *BERITA & SENTIMEN:*",
        "• `/news` ➔ Kalender Berita Ekonomi & Bank Holiday (ForexFactory Dual-Source)",
        "",
        "💼 *MANAJEMEN AKUN & EKSEKUSI:*",
        "• `/status` ➔ Status Akun Live MT5 (Equity, Balance, Daily P/L, Margin)",
        "• `/posisi` ➔ Daftar Posisi Terbuka & Floating P/L",
        "• `/close <ticket>` ➔ Tutup manual 1 tiket posisi tertentu",
        "• `/closeall` ➔ 🚨 Tutup Darurat SEMUA posisi terbuka",
        "• `/menu` ➔ Tampilkan Control Panel Utama",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "💡 _Bot beroperasi di Mode Scanner (26 FX Pairs | Weekend BTC)._"
    ]
    kb = {
        "inline_keyboard": [
            [
                {"text": "📡 [ SMC Radar ]", "callback_data": "cmd:radar"},
                {"text": "🧭 [ MSE Macro ]", "callback_data": "cmd:macro_menu"}
            ],
            [
                {"text": "🏛️ [ Fundamental ]", "callback_data": "cmd:fund"},
                {"text": "📰 [ Berita ]", "callback_data": "cmd:news"}
            ],
            [
                {"text": "« [ Menu ]", "callback_data": "cmd:menu"}
            ]
        ]
    }
    send_telegram_msg("\n".join(lines), reply_markup=kb, chat_id=chat_id)


def handle_fundamental_command(chat_id, symbol_input=None):
    """Sends the 8-Currency Composite Fundamental Scorecard & Pair Alignment."""
    try:
        from src.analytics.apex_fundamental_engine import apex_fundamental_engine

        if symbol_input:
            ev = apex_fundamental_engine.evaluate_pair(symbol_input)
            if not ev.base:
                send_telegram_msg(f"⚠️ Simbol `{symbol_input}` tidak valid atau tidak memiliki data fundamental.", chat_id=chat_id)
                return

            cat_lines = "\n".join([f"  {c}" for c in ev.recent_catalysts[:3]]) if ev.recent_catalysts else "  • Baseline Flat (Tidak ada kejutan baru)"
            veto_line = f"\n🚨 *VETO AKTIF*: `{ev.hard_veto_flag}` ({ev.hard_veto_reason})" if ev.hard_veto_flag else ""

            lines = [
                f"🏛️ *APEX PARAGON FUNDAMENTAL: {ev.symbol}*",
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"• *Base ({ev.base})* : Skor `{ev.base_score:+.2f}` │ Fase: `{ev.base_phase}`",
                f"• *Quote ({ev.quote})*: Skor `{ev.quote_score:+.2f}` │ Fase: `{ev.quote_phase}`",
                f"• *Net Delta*: `{ev.fundamental_delta:+.2f}` │ *Carry Spread*: `{ev.carry_spread:+.2f}%`",
                f"• *Status*: {ev.status_badge}",
                f"• *Setup Grade*: `{ev.setup_grade}` (Sizing: `{ev.sizing_modifier}x` lot)",
                f"• *Mandat*: `{ev.action_directive}`{veto_line}",
                "",
                "📊 *Katalis & Peluruhan Terkini*:",
                cat_lines,
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
                f"🕒 `{datetime.now(WIB).strftime('%H:%M:%S WIB')}` │ Framework: `Apex Paragon 4-Tier`"
            ]
            kb = {
                "inline_keyboard": [
                    [{"text": f"[ 🧠 AI Analisa {ev.symbol} ]", "callback_data": f"analyze:{ev.symbol}_H1"}],
                    [{"text": "🌐 [ Scorecard 8 Mata Uang ]", "callback_data": "cmd:fund"}, {"text": "« [ Menu ]", "callback_data": "cmd:menu"}]
                ]
            }
            send_telegram_msg("\n".join(lines), reply_markup=kb, chat_id=chat_id)
            return

        # Overall 8-Currency Scoreboard
        scores = apex_fundamental_engine.compute_scores()
        lines = [
            "🏛️ *APEX PARAGON 8-CURRENCY FUNDAMENTAL SCORECARD*",
            f"🕒 `{datetime.now(WIB).strftime('%H:%M:%S WIB')}` │ Bobot: `Regime-Aware`\n",
            "📊 *Peringkat Fundamental Mata Uang:*"
        ]
        sorted_scores = sorted(scores.items(), key=lambda x: x[1].composite_fundamental_score, reverse=True)
        for curr, sc in sorted_scores:
            icon = "🟢" if sc.composite_fundamental_score > 0.15 else ("🔴" if sc.composite_fundamental_score < -0.15 else "⚪")
            hol_str = " 🏖️" if sc.is_bank_holiday else ""
            phase_str = f" `[{sc.reaction_phase}]`" if sc.reaction_phase != "PRICED_IN_EQUILIBRIUM" else ""
            lines.append(f"• {icon} *{curr}*: `{sc.composite_fundamental_score:+.2f}` (Bunga `{sc.central_bank_rate}%` {sc.central_bank_cycle}){hol_str}{phase_str}")

        lines.append("\n🎯 *Rekomendasi Pair Konvergen (Grade S & A+):*")
        top_strong = sorted_scores[0][0]
        top_weak = sorted_scores[-1][0]
        lines.append(f"• 👑 *Top Long*: `{top_strong}{top_weak}` (Delta `{sorted_scores[0][1].composite_fundamental_score - sorted_scores[-1][1].composite_fundamental_score:+.2f}`) ➔ Kuat vs Lemah")

        lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("💡 _Ketik `/fund <pair>` (misal `/fund GBPUSD`) untuk evaluasi mendalam per-pair._")

        kb = {
            "inline_keyboard": [
                [
                    {"text": "GBPUSD", "callback_data": "cmd:fund_GBPUSD"},
                    {"text": "EURUSD", "callback_data": "cmd:fund_EURUSD"},
                    {"text": "USDJPY", "callback_data": "cmd:fund_USDJPY"}
                ],
                [
                    {"text": "GBPJPY", "callback_data": "cmd:fund_GBPJPY"},
                    {"text": "EURJPY", "callback_data": "cmd:fund_EURJPY"},
                    {"text": "AUDUSD", "callback_data": "cmd:fund_AUDUSD"}
                ],
                [
                    {"text": "🔄 [ Refresh ]", "callback_data": "cmd:fund"},
                    {"text": "« [ Menu ]", "callback_data": "cmd:menu"}
                ]
            ]
        }
        send_telegram_msg("\n".join(lines), reply_markup=kb, chat_id=chat_id)
    except Exception as e:
        print(f"[TG BOT ERROR] handle_fundamental_command: {e}")
        send_telegram_msg(f"Error computing fundamental scorecard: `{e}`", chat_id=chat_id)


def handle_news_command(chat_id):
    """Sends the Upcoming High-Impact Economic Events & Bank Holidays (ForexFactory Dual-Source)."""
    try:
        from src.analytics import economic_calendar
        cal_obj = getattr(economic_calendar, "calendar", None)
        if not cal_obj:
            send_telegram_msg("⚠️ Kalender berita belum terinisialisasi.", chat_id=chat_id)
            return

        now = datetime.now(WIB)
        all_events = cal_obj.get_events(now)
        today_date = now.date()

        active_holidays = [
            e for e in all_events
            if e.get("impact") == "HOLIDAY" and e["dt"].date() == today_date
        ]
        recent_news = [
            e for e in all_events
            if e.get("impact") != "HOLIDAY" and (now - timedelta(hours=6)) <= e["dt"] < now
        ]
        upcoming_news = [
            e for e in all_events
            if e.get("impact") != "HOLIDAY" and now <= e["dt"] <= (now + timedelta(hours=48))
        ]

        lines = [
            "📰 *KALENDER BERITA & BANK HOLIDAY (ForexFactory Dual-Source)*",
            f"🕒 `{now.strftime('%H:%M:%S WIB')}` │ Horizon: `±48 Jam`\n"
        ]

        if active_holidays:
            lines.append("🏖️ *HARI LIBUR BANK AKTIF HARI INI:*")
            for h in active_holidays:
                lines.append(f"• 🏖️ *[{h.get('country')}]* `{h['name']}` ➔ _Likuiditas tipis & spread melebar!_")
            lines.append("")

        if recent_news:
            lines.append("⚡ *Baru Saja Dirilis (6 Jam Terakhir):*")
            for ne in recent_news[:5]:
                dt_str = ne['dt'].strftime('%H:%M WIB')
                hours_ago = (now - ne['dt']).total_seconds() / 3600
                country = ne.get('country', 'US').strip()
                imp = ne.get('impact', 'HIGH')
                icon = "🔴" if imp == "HIGH" else "🟠"
                lines.append(f"• `[{dt_str}]` {icon} *[{country}]* `{ne['name']}` _({hours_ago:.1f}h lalu)_")
            lines.append("")

        if upcoming_news:
            lines.append("⏳ *Jadwal Rilis Mendatang (Next 48 Jam):*")
            for ne in upcoming_news[:10]:
                dt_str = ne['dt'].strftime('%a %d %b %H:%M WIB')
                hours_in = (ne['dt'] - now).total_seconds() / 3600
                country = ne.get('country', 'US').strip()
                imp = ne.get('impact', 'HIGH')
                icon = "🔴" if imp == "HIGH" else "🟠"
                fore_str = f" _(Fore: {ne['forecast']})_" if ne.get('forecast') else ""
                prev_str = f" _(Prev: {ne['previous']})_" if ne.get('previous') else ""
                lines.append(f"• `[{ne['dt'].strftime('%H:%M WIB')}]` {icon} *[{country}]* `{ne['name']}`{fore_str}{prev_str}\n   ↳ _{dt_str} (dalam {hours_in:.1f} jam)_ `[{imp}]`")
        else:
            lines.append("🟢 *Status Pasar Tenang:*\n_Tidak ada rilis berita High/Medium-Impact dalam 48 jam ke depan._")

        lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🛡️ *News Guard*: _Stage 2 Jury otomatis menolak trade jika rilis High-Impact ≤ 6 jam terdeteksi._")

        kb = {
            "inline_keyboard": [
                [
                    {"text": "🔄 [ Refresh News ]", "callback_data": "cmd:news"},
                    {"text": "🌐 [ Boitoki CSM ]", "callback_data": "cmd:csm"}
                ],
                [
                    {"text": "📡 [ SMC Radar 26 Pairs ]", "callback_data": "cmd:radar"},
                    {"text": "« [ Menu ]", "callback_data": "cmd:menu"}
                ]
            ]
        }
        send_telegram_msg("\n".join(lines), reply_markup=kb, chat_id=chat_id)
    except Exception as e:
        print(f"[TG BOT ERROR] handle_news_command: {e}")
        send_telegram_msg(f"Error fetching economic calendar: `{e}`", chat_id=chat_id)


def _build_main_menu_keyboard():
    """Builds the clean institutional inline keyboard for /menu."""
    return {
        "inline_keyboard": [
            [
                {"text": "🧭 [ 6-TF MSE Macro Strategy ]", "callback_data": "cmd:macro_menu"}
            ],
            [
                {"text": "GBPUSD H1", "callback_data": "analyze:GBPUSD_H1"},
                {"text": "USDJPY M30", "callback_data": "analyze:USDJPY_M30"}
            ],
            [
                {"text": "EURUSD H1", "callback_data": "analyze:EURUSD_H1"},
                {"text": "GBPJPY M30", "callback_data": "analyze:GBPJPY_M30"}
            ],
            [
                {"text": "EURJPY M30", "callback_data": "analyze:EURJPY_M30"},
                {"text": "CADJPY M30", "callback_data": "analyze:CADJPY_M30"}
            ],
            [
                {"text": "📡 [ SMC Radar 26 Pairs ]", "callback_data": "cmd:radar"},
                {"text": "🌐 [ Boitoki CSM Flow ]", "callback_data": "cmd:csm"}
            ],
            [
                {"text": "📰 [ News & Holiday ]", "callback_data": "cmd:news"},
                {"text": "🏛️ [ Apex Fundamental ]", "callback_data": "cmd:fund"}
            ],
            [
                {"text": "💼 [ Active Positions ]", "callback_data": "cmd:positions"},
                {"text": "📊 [ Account Status ]", "callback_data": "cmd:status"}
            ],
            [
                {"text": "📖 [ Help / Panduan ]", "callback_data": "cmd:help"}
            ]
        ]
    }


def handle_macro_picker_menu(chat_id):
    """Sends clean symbol picker for 6-TF Macro Strategic Engine directives."""
    text = (
        "🧭 *TOP-DOWN MACRO STRATEGIC DIRECTIVES (6-TF)*\n"
        "_Select an instrument to view 6-TF native mandate, SBR/RBS sockets, reload zones, and intraday targets (<100ms, 0 Token):_"
    )
    kb = {
        "inline_keyboard": [
            [
                {"text": "GBPUSD", "callback_data": "cmd:macro_GBPUSD"},
                {"text": "USDJPY", "callback_data": "cmd:macro_USDJPY"},
                {"text": "EURUSD", "callback_data": "cmd:macro_EURUSD"},
            ],
            [
                {"text": "GBPJPY", "callback_data": "cmd:macro_GBPJPY"},
                {"text": "EURJPY", "callback_data": "cmd:macro_EURJPY"},
                {"text": "CADJPY", "callback_data": "cmd:macro_CADJPY"},
            ],
            [
                {"text": "AUDUSD", "callback_data": "cmd:macro_AUDUSD"},
                {"text": "USDCAD", "callback_data": "cmd:macro_USDCAD"},
                {"text": "BTCUSD", "callback_data": "cmd:macro_BTCUSD"},
            ],
            [
                {"text": "« [ Back to Menu ]", "callback_data": "cmd:menu"}
            ]
        ]
    }
    send_telegram_msg(text, reply_markup=kb, chat_id=chat_id)


def handle_menu_command(chat_id):
    """Sends the clean institutional control panel."""
    text = (
        "*CONTROL PANEL — 2-STAGE QUANT TRADING BOT*\n"
        "_Select an instrument for on-demand OpenAI analysis, MSE Macro Strategy, or view 26-Pair SMC Radar:_"
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
            f"• *Architecture*: `2-Stage Quant Funnel (26 Pairs FX | Weekend BTC H1)`\n"
            f"• *Fast Radar*: `60s Sweep Active (0 Token)`\n"
            f"• *3-AI Jury*: `Full 3-AI (OpenAI + Gemini + DeepSeek)`\n"
            f"• *Risk per Trade*: `FX {config.RISK_PERCENT_FX}% | BTC {config.RISK_PERCENT_BTC}%` (Max: Weekday `{config.MAX_OPEN_POSITIONS}` / Weekend `{config.MAX_OPEN_POSITIONS_BTC}`)\n"
            f"• *Max Daily Loss*: `{getattr(config, 'MAX_DAILY_LOSS_PERCENT', 4.0)}%` | *Target*: `{config.DAILY_PROFIT_TARGET_PERCENT}%`"
        )
        kb = {
            "inline_keyboard": [
                [{"text": "📡 [ SMC Radar 26 Pairs ]", "callback_data": "cmd:radar"}],
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

    send_telegram_msg(f"*Starting On-Demand Analysis for `{sym}` ({tf_label})...*\n_Querying OpenAI o4-mini with live MSE 6-TF structural data..._", chat_id=chat_id)

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
                info = connector.mt5.symbol_info(sym)
                pt = info.point if info else (0.001 if "JPY" in sym else (0.01 if "XAU" in sym or "BTC" in sym else 0.00001))
                last_c = float(df["close"].iloc[-1])
                tick_live = {"bid": last_c, "ask": last_c, "point": pt, "spread": 10}

            strat_dir = macro_strategic_engine.get_directive(sym)
            if strat_dir:
                macro_ctx = (
                    f"### TOP-DOWN MACRO STRATEGIC CONTEXT (MSE 6-TF NATIVE)\n"
                    f"- Macro Mandate: {strat_dir.daily_macro_bias} (Score: {strat_dir.macro_bias_score:+.2f}) | Stability: {strat_dir.regime_stability}\n"
                    f"- Operational Action Tier: {strat_dir.action_tier} | Circuit Breaker: {'ACTIVE' if strat_dir.hard_circuit_breaker else 'CLEAR'}\n"
                    f"- Structural Sockets:\n"
                    f"  * Macro D1 Scale  : Major SBR Resistance = {strat_dir.macro_sbr_d1} | Major RBS Support = {strat_dir.macro_rbs_d1}\n"
                    f"  * Intermediate H4 : SBR Resistance = {strat_dir.inter_sbr_h4} | RBS Support = {strat_dir.inter_rbs_h4}\n"
                    f"  * Micro H1 Scale  : SBR Resistance = {strat_dir.micro_sbr_h1} | RBS Support = {strat_dir.micro_rbs_h1}\n"
                    f"- Psychological Stations: Sub-Floor [{strat_dir.sub_floor_50}] <---> Sub-Ceiling [{strat_dir.sub_ceiling_50}]\n"
                    f"- Reload Zone Anchor   : {strat_dir.entry_limit_anchor} | Baseline Floor SL = {strat_dir.intraday_sl_price}\n"
                    f"- Station Targets      : TP1 = {strat_dir.tp1_price} | TP2 = {strat_dir.tp2_price}\n"
                    f"- Strategic Directive  : {strat_dir.primary_execution_directive}\n"
                    f"- Invalidation Point   : {strat_dir.invalidation_stop_price} | Contingency Target: {strat_dir.contingency_target}\n"
                    f"- Future Macro Roadmap :\n{strat_dir.future_macro_roadmap}\n"
                )
            else:
                macro_ctx = ""

            open_pos = connector.get_open_positions(symbol=sym)
            all_open_pos = connector.get_open_positions()

            prompt = llm_client.prepare_prompt(
                sym, df, tick_live,
                macro_context=macro_ctx,
                open_positions=open_pos,
                all_open_positions=all_open_pos
            )

            # Direct fast query with OpenAI o4-mini
            decision = llm_client.query_openai(prompt)
            if not decision:
                send_telegram_msg(f"Error: OpenAI o4-mini tidak mengembalikan respons untuk `{sym}`.", chat_id=chat_id)
                return

            sig = str(decision.get("signal") or "HOLD").upper()
            conf = float(decision.get("confidence") or 0.0)
            setup = decision.get("setup", "N/A")
            regime = decision.get("market_regime", "N/A")
            reason = decision.get("reasoning") or decision.get("edge") or "N/A"
            sl_pts = decision.get("sl_points") or 0
            tp_pts = decision.get("tp_points") or 0
            inv_price = decision.get("invalidation_price")
            tgt_price = decision.get("target_price")
            entry_type = decision.get("entry_type") or "market"
            entry_price = decision.get("entry_price")

            # Calculate lot sizing preview
            effective_lot = _risk_engine.get_effective_lot_size(sl_pts, split_count=1, symbol=sym) if sl_pts > 0 else config.lot_size_for(sym)
            rr_str = f"{tp_pts/sl_pts:.2f}:1" if (sl_pts and sl_pts > 0 and tp_pts) else "N/A"

            sig_emoji = "🟢" if sig == "BUY" else ("🔴" if sig == "SELL" else "🟡")

            lines = [
                f"🧠 *ON-DEMAND ANALYSIS: {sym} ({tf_label})*",
                f"🕒 `{time.strftime('%H:%M:%S WIB')}` | Engine: `OpenAI o4-mini (Quant MSE Context)`\n",
                f"📊 *Regime*: `{regime}` | *Setup*: `{setup}`",
                f"🎯 *Rekomendasi*: {sig_emoji} *`{sig}`* (Confidence: `{conf*100:.0f}%`)",
                f"━" * 28,
            ]

            if sig in ("BUY", "SELL"):
                if entry_type != "market" and entry_price:
                    lines.append(f"• *Entry*: `{entry_type.upper()} @ {entry_price}`")
                else:
                    lines.append(f"• *Entry*: `Market Execution @ {tick_live.get('ask' if sig=='BUY' else 'bid')}`")

                sl_str = f"`{inv_price}` ({sl_pts} pts)" if inv_price else f"`{sl_pts} pts`"
                tp_str = f"`{tgt_price}` ({tp_pts} pts | R:R {rr_str})" if tgt_price else f"`{tp_pts} pts`"
                lines.append(f"• *Stop Loss*: {sl_str}")
                lines.append(f"• *Take Profit*: {tp_str}")
                lines.append(f"• *Lot Sizing (Risk {config.risk_percent_for(sym)}%)*: `{effective_lot} lot`")
            else:
                lines.append(f"• *Status*: _Kondisi pasar saat ini belum optimal untuk entri. Disarankan HOLD & menunggu harga memasuki Reload Zone MSE._")

            lines.append(f"━" * 28)
            lines.append(f"📝 *Analisis*: _{reason}_")

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


def _handle_ai_agent_message(text: str, chat_id: str):
    """Processes natural language conversation via AI agent in a background daemon thread."""
    def _worker():
        send_chat_action("typing", chat_id=chat_id)
        try:
            from tele_bot.telegram_ai_agent import run_agent_turn, CONVERSATION_HISTORY
            reply = run_agent_turn(text, CONVERSATION_HISTORY)
            send_telegram_msg(reply, chat_id=chat_id)
        except Exception as e:
            print(f" [TG AI AGENT ERROR] {e}")
            send_telegram_msg(f"⚠️ Terjadi kendala saat memproses AI Agent: `{e}`", chat_id=chat_id)

    threading.Thread(target=_worker, daemon=True, name="TelegramAIAgentWorker").start()


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

        print(f" [TELEGRAM BOT] Received message: '{text}' from {target_chat}")
        parts = text.split()
        cmd_raw = parts[0].lower()
        cmd = cmd_raw.split("@")[0]  # Remove @botname suffix
        args = parts[1:] if len(parts) > 1 else []

        if cmd in ("/start", "/menu"):
            handle_menu_command(target_chat)
        elif cmd in ("/help", "/bantuan", "/command", "/commands"):
            handle_help_command(target_chat)
        elif cmd in ("/csm", "/strength", "/currency"):
            handle_csm_command(target_chat)
        elif cmd in ("/radar", "/scan", "/scanner"):
            handle_radar_command(target_chat)
        elif cmd in ("/indicators", "/indikator", "/levels", "/smc"):
            sym = args[0] if args else config.SYMBOL
            handle_indicators_command(target_chat, symbol_input=sym)
        elif cmd in ("/macro", "/directive", "/kompas"):
            if args:
                handle_macro_command(target_chat, symbol_input=args[0])
            else:
                handle_macro_picker_menu(target_chat)
        elif cmd in ("/status", "/akun"):
            handle_status_command(target_chat)
        elif cmd in ("/posisi", "/positions", "/open"):
            handle_positions_command(target_chat)
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
                    "• `/analisa EURUSD H1`\n"
                    "• `/analisa USDJPY M30`\n"
                    "• `/analisa GBPJPY H4`\n"
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
        elif cmd in ("/news", "/kalender", "/berita", "/calendar", "/event", "/events"):
            handle_news_command(target_chat)
        elif cmd in ("/fundamental", "/fund", "/makrofund", "/bias"):
            sym = args[0] if args else None
            handle_fundamental_command(target_chat, symbol_input=sym)
        elif any(p in cmd for p in ("gbpusd", "eurjpy", "gbpaud", "audcad", "eurchf", "audchf", "cadchf", "xauusd", "btcusd", "gold", "btc")):
            tf_custom = args[0] if args else None
            run_ondemand_analysis(parts[0], target_chat, timeframe_input=tf_custom)
        elif cmd in ("/reset", "/clear", "reset", "clear"):
            try:
                from tele_bot.telegram_ai_agent import CONVERSATION_HISTORY
                CONVERSATION_HISTORY.clear()
            except Exception:
                pass
            send_telegram_msg("🧹 Riwayat percakapan AI Agent telah direset. Silakan kirim pesan baru!", chat_id=target_chat)
        else:
            # Route natural language conversation to AI agent
            _handle_ai_agent_message(text, target_chat)
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
        elif data in ("cmd:help", "cmd:commands"):
            handle_help_command(target_chat)
        elif data in ("cmd:fund", "cmd:fundamental"):
            handle_fundamental_command(target_chat)
        elif data.startswith("cmd:fund_"):
            sym_req = data.split("cmd:fund_", 1)[1]
            handle_fundamental_command(target_chat, symbol_input=sym_req)
        elif data in ("cmd:macro", "cmd:macro_menu"):
            handle_macro_picker_menu(target_chat)
        elif data.startswith("cmd:macro_"):
            sym_req = data.split("cmd:macro_", 1)[1]
            handle_macro_command(target_chat, symbol_input=sym_req)
        elif data == "cmd:news":
            handle_news_command(target_chat)
        elif data == "cmd:csm":
            handle_csm_command(target_chat)
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
        {"command": "macro", "description": "Top-Down 6-TF Macro Strategy (e.g. /macro GBPUSD)"},
        {"command": "news", "description": "High-Impact News Calendar & Schedule"},
        {"command": "csm", "description": "Dual-Horizon Boitoki CSM Currency Strength"},
        {"command": "analisa", "description": "On-Demand Analysis (e.g. /analisa GBPUSD)"},
        {"command": "radar", "description": "26-Pair SMC Quant Scanner & Overview"},
        {"command": "indicators", "description": "High/Low, Zona Diskon, Premium, & SMC OB/FVG"},
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
