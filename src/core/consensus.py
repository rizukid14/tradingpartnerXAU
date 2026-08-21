import config
from src.analytics import dynamic_config
from src.core.cli_theme import UI


def _effective_consensus_threshold():
    """Returns the active consensus threshold. Dynamic rules only apply when
    DYNAMIC_CONFIG_ENABLED; otherwise fall back to static config (2/3)."""
    if not getattr(config, "DYNAMIC_CONFIG_ENABLED", False):
        return config.CONSENSUS_THRESHOLD
    try:
        return int(dynamic_config.dynamic_rules.consensus_threshold)
    except Exception:
        return config.CONSENSUS_THRESHOLD


_last_sltp_adjustments = []


def _apply_sltp_rules(sl_points, tp_points):
    """
    SL/TP final sesuai config.TP_SL_RULES.
    Returns: (sl_points, tp_points, ok: bool, reason: str)
    """
    global _last_sltp_adjustments
    _last_sltp_adjustments = []

    if not sl_points or sl_points <= 0:
        sl_points = config.default_sl_points_for(config.SYMBOL)
    if not tp_points or tp_points <= 0:
        tp_points = config.default_tp_points_for(config.SYMBOL)

    spread_pts = 0
    atr_points = 0
    try:
        from config import mt5
        import pandas as pd
        from ta.volatility import AverageTrueRange
        tick = mt5.symbol_info_tick(config.SYMBOL)
        si = mt5.symbol_info(config.SYMBOL)
        if tick is not None and si is not None and si.point:
            spread_pts = int(round((tick.ask - tick.bid) / si.point))
            rates = mt5.copy_rates_from_pos(config.SYMBOL, config.get_timeframe(config.SYMBOL), 0, 50)
            if rates is not None and len(rates) > 0:
                df = pd.DataFrame(rates)
                df['atr'] = AverageTrueRange(
                    high=df['high'], low=df['low'], close=df['close'], window=14
                ).average_true_range()
                atr_val = df.iloc[-1]['atr'] if 'atr' in df.columns else None
                if pd.notna(atr_val) and si.point and si.point > 0:
                    atr_points = int(atr_val / si.point)
    except Exception:
        pass

    mode = config.sltp_mode_for(config.SYMBOL)

    if mode == "LLM":
        is_xau = "XAU" in config.SYMBOL.upper() or "GOLD" in config.SYMBOL.upper()

        if is_xau:
            xau_mult = getattr(config, "LLM_XAU_FLOOR_ATR_MULT", 1.2)
            if atr_points > 0:
                min_sl = max(spread_pts * 2, int(xau_mult * atr_points))
            else:
                min_sl = max(spread_pts * 2, config.LLM_SAFETY_FLOOR_XAU_PTS)
        else:
            fx_mult = getattr(config, "LLM_FX_FLOOR_ATR_MULT", 1.5)
            if atr_points > 0:
                min_sl = max(spread_pts * 2, int(fx_mult * atr_points))
            else:
                min_sl = max(spread_pts * 2, config.LLM_SAFETY_FLOOR_FX_PTS)
            
        if sl_points < min_sl:
            _last_sltp_adjustments.append(f"SL {sl_points} pts di bawah safety floor. Menyesuaikan SL ke {min_sl} pts.")
            sl_points = min_sl

        if tp_points <= 0:
            tp_points = config.default_tp_points_for(config.SYMBOL)

        min_rr = config.LLM_MIN_RR_RATIO
        min_tp = int(sl_points * min_rr)
        if tp_points < min_tp:
            _last_sltp_adjustments.append(f"TP {tp_points} pts < {min_rr}x SL. Menyesuaikan TP ke {min_tp} pts (R:R {min_rr}:1).")
            tp_points = min_tp

        try:
            account = mt5.account_info() if 'mt5' in dir() else None
            if account is None:
                from config import mt5 as _mt5
                account = _mt5.account_info()
            equity = float(account.equity) if account else 0.0
            si = mt5.symbol_info(config.SYMBOL) if 'mt5' in dir() else None
            if si is None:
                from config import mt5 as _mt5
                si = _mt5.symbol_info(config.SYMBOL)
            vol_min = getattr(si, "volume_min", 0.01) if si else 0.01
            usd_pt = (si.trade_tick_value * (si.point / si.trade_tick_size)) if si and si.trade_tick_size else 0.0
            risk_pct = config.risk_percent_for(config.SYMBOL)
            gate_pct = max(risk_pct, float(config.OVER_RISK_MAX_PERCENT))
            if equity > 0 and usd_pt > 0 and vol_min > 0:
                max_sl = (equity * gate_pct / 100.0) / (vol_min * usd_pt)
                if sl_points > max_sl:
                    risk_actual = sl_points * vol_min * usd_pt
                    return sl_points, tp_points, False, (
                        f"OVER-RISK: SL {sl_points} pts > max {max_sl:.0f} pts "
                        f"(risk {risk_pct}% = ${equity*risk_pct/100:.2f} gak muat di min lot {vol_min}: "
                        f"risk aktual ${risk_actual:.2f} = {risk_actual/equity*100:.2f}% > gate {gate_pct}%)"
                    )
        except Exception:
            pass

        return sl_points, tp_points, True, ""

    if atr_points > 0:
        ai_mode = config.get_ai_mode()
        sl_mult = config.atr_sl_multiplier()
        tp_mult = config.atr_tp_multiplier()
        min_sl = max(spread_pts * 2, int(atr_points * sl_mult))
        min_tp = max(spread_pts * 2, int(atr_points * tp_mult))
        if sl_points < min_sl or tp_points < min_tp:
            return sl_points, tp_points, False, (
                f"SL {sl_points} < {sl_mult}x ATR ({min_sl}) atau "
                f"TP {tp_points} < {tp_mult}x ATR ({min_tp}) (ATR {atr_points} pts, mode {ai_mode})"
            )
        return sl_points, tp_points, True, ""

    if sl_points < spread_pts * 2:
        sl_points = spread_pts * 2
    if tp_points < sl_points:
        tp_points = sl_points
    return sl_points, tp_points, True, "ATR unavailable, fallback 2x spread"


def _drop_standalone_outlier(values, label):
    """
    Buang nilai yang "beda sendiri" sebelum di-average.
    Returns: (filtered_values, dropped_note_or_None)
    """
    if len(values) <= 2:
        return values, None
    s = sorted(values)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0
    low = [v for v in s if v < 0.5 * median]
    high = [v for v in s if v > 2.0 * median]
    dropped = []
    if low and high:
        if median - min(low) >= max(high) - median:
            dropped = [min(low)]
        else:
            dropped = [max(high)]
    elif low:
        dropped = [min(low)]
    elif high:
        dropped = [max(high)]

    if dropped:
        v_drop = dropped[0]
        note = f"Outlier {label} dibuang (median {median:.0f}): {v_drop:.0f if isinstance(v_drop, float) and v_drop.is_integer() else v_drop}"
        filtered = [v for v in values if v != v_drop]
        return filtered, note
    return values, None


def calculate_consensus(decisions):
    box_items = []
    
    # Print details for each model
    for model_name, dec in decisions.items():
        sig = dec.get("signal") or "HOLD"
        conf = dec.get("confidence") if dec.get("confidence") is not None else 0.0
        reason = dec.get("reasoning") or "Tidak ada alasan."
        if len(reason) > 380:
            reason = reason[:377] + "..."

        sl = dec.get("sl_points")
        tp = dec.get("tp_points")
        setup_label = dec.get("setup")
        
        badge = UI.badge_signal(sig)
        bar = UI.make_bar(conf, 1.0, width=8)
        sltp_info = f"SL: {sl} pts, TP: {tp} pts" if sig in ("BUY", "SELL") else "SL/TP: -"
        
        box_items.append(f"{UI.BOLD}{model_name:<10}{UI.RST}: {badge} {bar} | {UI.DIM}{sltp_info}{UI.RST}")
        invalidation_text = (dec.get("invalidation") or "").strip()
        if setup_label:
            box_items.append((f"  {UI.CYAN}Setup{UI.RST}  : ", setup_label))
        box_items.append((f"  {UI.GRAY}Reason{UI.RST} : ", reason))
        if invalidation_text:
            box_items.append((f"  {UI.RED}Inval.{UI.RST}  : ", invalidation_text))

        
    # Evaluate consensus for active position early-close actions
    close_votes = {}
    hold_reasons = {}
    all_evaluated_tickets = set()
    for model_name, dec in decisions.items():
        pos_actions = dec.get("position_actions", [])
        if isinstance(pos_actions, list):
            for item in pos_actions:
                if isinstance(item, dict):
                    ticket = item.get("ticket")
                    if ticket:
                        all_evaluated_tickets.add(ticket)
                        act = item.get("action", "HOLD")
                        reason_str = item.get("reason", "Setup masih valid")
                        if act == "CLOSE":
                            close_votes.setdefault(ticket, []).append((model_name, reason_str))
                        else:
                            hold_reasons.setdefault(ticket, []).append((model_name, reason_str))

    tickets_to_close = []
    consensus_threshold = _effective_consensus_threshold()
    n_models = len(decisions)
    close_threshold = min(consensus_threshold, n_models)
    closed_ticket_ids = set()
    
    pos_re_eval_notes = []
    for ticket, votes in close_votes.items():
        if len(votes) >= close_threshold:
            models_str = ", ".join([v[0] for v in votes])
            reason_sample = votes[0][1]
            tickets_to_close.append({
                "ticket": ticket,
                "models": models_str,
                "reason": reason_sample
            })
            closed_ticket_ids.add(ticket)
            pos_re_eval_notes.append((f"  {UI.YELLOW}[AI RE-EVALUATOR]{UI.RST} ", f"{len(votes)}/{n_models} AI ({models_str}) sepakat CLOSE order #{ticket}: {reason_sample}"))

    for ticket in sorted(all_evaluated_tickets):
        if ticket not in closed_ticket_ids:
            reasons_list = hold_reasons.get(ticket, [])
            if reasons_list:
                m_str = ", ".join([r[0] for r in reasons_list])
                r_sample = reasons_list[0][1]
                pos_re_eval_notes.append((f"  {UI.DIM}[AI RE-EVALUATOR]{UI.RST} ", f"Order #{ticket} dipertahankan (HOLD oleh {m_str}): {r_sample}"))
            else:
                pos_re_eval_notes.append((f"  {UI.DIM}[AI RE-EVALUATOR]{UI.RST} ", f"Order #{ticket} dipertahankan (HOLD) oleh konsensus AI."))

    if pos_re_eval_notes:
        box_items.append("---")
        box_items.extend(pos_re_eval_notes)

    # Dynamic weighted-confidence consensus
    direction_scores = {"BUY": 0.0, "SELL": 0.0}
    direction_models = {"BUY": [], "SELL": []}
    for model_name, dec in decisions.items():
        sig = dec.get("signal") or "HOLD"
        conf = dec.get("confidence") if dec.get("confidence") is not None else 0.0
        if sig in direction_scores:
            direction_scores[sig] += conf
            direction_models[sig].append(model_name)

    min_models = getattr(config, "MIN_CONSENSUS_MODELS", 2)
    base_threshold = config.confidence_threshold_for(config.SYMBOL)
    if getattr(config, "FORCE_ACTIVE_ENTRY", False):
        base_threshold *= 0.7

    ai_mode = getattr(config, "get_ai_mode", lambda: "triple")()
    if ai_mode in ("single", "single_gemini") or n_models == 1:
        min_models = 1
        threshold = base_threshold * 0.6
    else:
        min_models = min(min_models, len(decisions))
        eff_count = min(_effective_consensus_threshold(), len(decisions))
        threshold = base_threshold * (eff_count / min_models)

    consensus_signal = "HOLD"
    agreeing_models = []
    best_score = threshold
    for sig in ["BUY", "SELL"]:
        if len(direction_models[sig]) >= min_models and direction_scores[sig] >= best_score:
            consensus_signal = sig
            agreeing_models = direction_models[sig]
            best_score = direction_scores[sig]

    if consensus_signal == "HOLD":
        box_items.append("---")
        box_items.append(f"{UI.YELLOW}[*] HASIL: TIDAK ADA KONSENSUS (HOLD){UI.RST}")
        box_items.append((f"  {UI.DIM}Skor Arah:{UI.RST} ", f"BUY={direction_scores['BUY']:.2f}, SELL={direction_scores['SELL']:.2f} (Threshold: {threshold:.2f})"))
        print("\n" + UI.make_box("ANALISIS KONSENSUS MULTI-LLM", box_items, width=74, border_color=UI.CYAN) + "\n")
        
        any_trade_intent = any(dec.get("signal") in ("BUY", "SELL") for dec in decisions.values())
        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "sl_points": config.default_sl_points_for(config.SYMBOL),
            "tp_points": config.default_tp_points_for(config.SYMBOL),
            "agreeing_count": 0,
            "agreeing_models": [],
            "tickets_to_close": tickets_to_close,
            "hold_type": "low_confidence" if ai_mode in ("single", "single_gemini") else "split_vote",
            "threshold": threshold,
            "direction_scores": direction_scores,
            "decisions": decisions,
            "ai_mode": ai_mode,
            "details": f"Consensus failed (BUY={direction_scores['BUY']:.2f}, SELL={direction_scores['SELL']:.2f})"
        }

    # Calculate average SL, TP, Confidence
    inv_list, tgt_list, sl_list, tp_list, conf_list = [], [], [], [], []
    entry_type_votes = {}
    entry_price_list = []
    for name in agreeing_models:
        dec = decisions[name]
        conf_list.append(dec.get("confidence", 0.5))
        
        inv_val = dec.get("invalidation_price")
        if isinstance(inv_val, (int, float)) and inv_val > 0: inv_list.append(inv_val)
        tgt_val = dec.get("target_price")
        if isinstance(tgt_val, (int, float)) and tgt_val > 0: tgt_list.append(tgt_val)
        sl_val = dec.get("sl_points")
        if isinstance(sl_val, (int, float)) and sl_val > 0: sl_list.append(sl_val)
        tp_val = dec.get("tp_points")
        if isinstance(tp_val, (int, float)) and tp_val > 0: tp_list.append(tp_val)
        et = (dec.get("entry_type") or "market").strip().lower()
        if et not in ("market", "buy_stop", "sell_stop", "buy_limit", "sell_limit"):
            et = "market"
        entry_type_votes[et] = entry_type_votes.get(et, 0) + 1
        ep = dec.get("entry_price")
        if isinstance(ep, (int, float)) and ep > 0:
            entry_price_list.append(ep)

    outlier_notes = []
    inv_list, note1 = _drop_standalone_outlier(inv_list, "Invalidation Price")
    if note1: outlier_notes.append(note1)
    tgt_list, note2 = _drop_standalone_outlier(tgt_list, "Target Price")
    if note2: outlier_notes.append(note2)
    sl_list, note3 = _drop_standalone_outlier(sl_list, "SL Points")
    if note3: outlier_notes.append(note3)
    tp_list, note4 = _drop_standalone_outlier(tp_list, "TP Points")
    if note4: outlier_notes.append(note4)
    entry_price_list, note5 = _drop_standalone_outlier(entry_price_list, "Entry Price")
    if note5: outlier_notes.append(note5)

    # entry_type: mayoritas dari model yang setuju arah; seri -> market
    final_entry_type = "market"
    if entry_type_votes:
        top_type, top_count = max(entry_type_votes.items(), key=lambda kv: kv[1])
        if top_count >= max(1, len(agreeing_models) // 2):
            final_entry_type = top_type
    # Konsistensi arah: BUY -> buy_stop/buy_limit, SELL -> sell_stop/sell_limit
    if consensus_signal == "BUY" and final_entry_type not in ("buy_stop", "buy_limit"):
        final_entry_type = "market"
    if consensus_signal == "SELL" and final_entry_type not in ("sell_stop", "sell_limit"):
        final_entry_type = "market"
    final_entry_price = float(sum(entry_price_list) / len(entry_price_list)) if entry_price_list else None
    if final_entry_type != "market" and not final_entry_price:
        final_entry_type = "market"

    avg_confidence = float(sum(conf_list) / len(conf_list)) if conf_list else 0.0
    final_inv = sum(inv_list) / len(inv_list) if inv_list else None
    final_tgt = sum(tgt_list) / len(tgt_list) if tgt_list else None

    final_sl = int(sum(sl_list) / len(sl_list)) if sl_list else config.default_sl_points_for(config.SYMBOL)
    final_tp = int(sum(tp_list) / len(tp_list)) if tp_list else config.default_tp_points_for(config.SYMBOL)

    final_sl, final_tp, sltp_ok, sltp_reason = _apply_sltp_rules(final_sl, final_tp)

    try:
        from config import mt5
        tick = mt5.symbol_info_tick(config.SYMBOL)
        si = mt5.symbol_info(config.SYMBOL)
        point = si.point if si else 0.00001
        if tick and si and point:
            entry_price = tick.ask if consensus_signal == "BUY" else tick.bid
            if entry_price > 0:
                if consensus_signal == "BUY":
                    final_inv = entry_price - (final_sl * point)
                    final_tgt = entry_price + (final_tp * point)
                else:
                    final_inv = entry_price + (final_sl * point)
                    final_tgt = entry_price - (final_tp * point)
    except Exception:
        pass

    # Guardrail entry pending: jarak dari harga harus dalam [2x spread, 1.5x ATR]
    # dari harga saat ini, dan arah konsisten dengan entry_type. Kalau tidak
    # valid -> downgrade ke market (perilaku lama) supaya sinyal tidak hilang.
    if final_entry_type != "market" and final_entry_price is not None:
        try:
            from config import mt5
            tick = mt5.symbol_info_tick(config.SYMBOL)
            si = mt5.symbol_info(config.SYMBOL)
            point = si.point if si else 0.00001
            ref_price = tick.ask if consensus_signal == "BUY" else tick.bid
            dist_pts = abs(final_entry_price - ref_price) / point if (point and ref_price) else None
            spread_pts = int(round((tick.ask - tick.bid) / point)) if (tick and point) else 0
            atr_pts = 0
            try:
                import pandas as pd
                from ta.volatility import AverageTrueRange
                rates = mt5.copy_rates_from_pos(config.SYMBOL, config.get_timeframe(config.SYMBOL), 0, 50)
                if rates is not None and len(rates) > 0:
                    df = pd.DataFrame(rates)
                    df['atr'] = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14).average_true_range()
                    atr_val = df.iloc[-1]['atr']
                    if pd.notna(atr_val) and point and point > 0:
                        atr_pts = int(atr_val / point)
            except Exception:
                atr_pts = 0
            min_dist = spread_pts * float(getattr(config, "PENDING_ENTRY_MIN_SPREAD_MULT", 2.0))
            max_dist = (atr_pts if atr_pts > 0 else int(config.default_sl_points_for(config.SYMBOL))) * float(getattr(config, "PENDING_ENTRY_MAX_ATR_MULT", 1.5))
            if dist_pts is None or dist_pts < min_dist or dist_pts > max_dist:
                outlier_notes.append(f"Entry pending {final_entry_price} (jarak {dist_pts:.0f} pts) di luar band [2x spread, 1.5x ATR] -> downgrade ke market")
                final_entry_type = "market"
                final_entry_price = None
        except Exception:
            pass

    all_notes = []
    for onote in outlier_notes:
        all_notes.append(f"  {UI.YELLOW}[!]{UI.RST} {onote}")
    for adj in _last_sltp_adjustments:
        all_notes.append(f"  {UI.YELLOW}[!]{UI.RST} {adj}")

    if all_notes:
        box_items.append("---")
        box_items.extend(all_notes)

    box_items.append("---")

    if not sltp_ok:
        box_items.append(f"{UI.RED}[-] HASIL: TRADE DIBATALKAN OLEH GATE ATR{UI.RST}")
        box_items.append((f"  {UI.RED}Alasan{UI.RST}    : ", sltp_reason))
        print("\n" + UI.make_box("ANALISIS KONSENSUS MULTI-LLM", box_items, width=74, border_color=UI.CYAN) + "\n")
        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "sl_points": final_sl,
            "tp_points": final_tp,
            "invalidation_price": final_inv,
            "target_price": final_tgt,
            "agreeing_count": len(agreeing_models),
            "agreeing_models": list(agreeing_models),
            "tickets_to_close": tickets_to_close,
            "hold_type": "atr_gate",
            "candidate_signal": consensus_signal,
            "sltp_reason": sltp_reason,
            "decisions": decisions,
            "ai_mode": ai_mode,
            "details": f"SL/TP gate ATR gagal: {sltp_reason}"
        }

    best_setup = ""
    best_reason = ""
    best_invalidation = ""
    sorted_agreeing = sorted(agreeing_models, key=lambda m: decisions.get(m, {}).get("confidence", 0.0), reverse=True)
    for m in sorted_agreeing:
        dec = decisions.get(m, {})
        s_candidate = (dec.get("setup") or "").strip()
        r_candidate = (dec.get("reasoning") or dec.get("edge") or "").strip()
        i_candidate = (dec.get("invalidation") or "").strip()
        if s_candidate and not best_setup:
            best_setup = " ".join(s_candidate.replace("\n", " ").replace("\r", " ").split())
        if r_candidate and not best_reason:
            best_reason = " ".join(r_candidate.replace("\n", " ").replace("\r", " ").split())
        if i_candidate and not best_invalidation:
            best_invalidation = " ".join(i_candidate.replace("\n", " ").replace("\r", " ").split())
        if best_setup and best_reason and best_invalidation:
            break

    badge = UI.badge_signal(consensus_signal)
    box_items.append(f"{UI.GREEN}[+] KONSENSUS DISETUJUI:{UI.RST} {badge} {UI.BOLD}(Skor {best_score:.2f} >= {threshold:.2f}){UI.RST}")
    box_items.append((f"  {UI.BOLD}Model Sepakat :{UI.RST} ", f"{', '.join(agreeing_models)} (Avg Conf: {avg_confidence*100:.1f}%)"))
    if best_setup:
        box_items.append((f"  {UI.CYAN}Setup{UI.RST}         : ", best_setup))
    if best_reason:
        box_items.append((f"  {UI.CYAN}Reason{UI.RST}        : ", best_reason))
    price_decimals = 5 if (point and point < 0.001) else 2
    price_info = f" | Price SL {final_inv:.{price_decimals}f} / TP {final_tgt:.{price_decimals}f}" if final_inv else ""
    box_items.append((f"  {UI.BOLD}Final SL / TP :{UI.RST} ", f"{UI.RED}SL {final_sl} pts{UI.RST} | {UI.GREEN}TP {final_tp} pts{UI.RST}{price_info}"))

    print("\n" + UI.make_box("ANALISIS KONSENSUS MULTI-LLM", box_items, width=74, border_color=UI.CYAN) + "\n")

    return {
        "signal": consensus_signal,
        "confidence": avg_confidence,
        "sl_points": final_sl,
        "tp_points": final_tp,
        "invalidation_price": final_inv,
        "target_price": final_tgt,
        "entry_type": final_entry_type,
        "entry_price": final_entry_price,
        "agreeing_count": len(agreeing_models),
        "agreeing_models": list(agreeing_models),
        "setup": best_setup,
        "reason": best_reason,
        "invalidation_text": best_invalidation,
        "tickets_to_close": tickets_to_close,
        "details": f"Consensus by: {agreeing_models}"
    }
