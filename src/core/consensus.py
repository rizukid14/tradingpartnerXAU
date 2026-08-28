import json
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


def _apply_sltp_rules(sl_points, tp_points, symbol=None):
    """
    SL/TP final sesuai config.TP_SL_RULES.
    Returns: (sl_points, tp_points, ok: bool, reason: str)
    """
    global _last_sltp_adjustments
    _last_sltp_adjustments = []

    sym = symbol or config.SYMBOL

    if not sl_points or sl_points <= 0:
        sl_points = config.default_sl_points_for(sym)
    if not tp_points or tp_points <= 0:
        tp_points = config.default_tp_points_for(sym)

    spread_pts = 0
    atr_points = 0
    try:
        from config import mt5
        import pandas as pd
        from ta.volatility import AverageTrueRange
        tick = mt5.symbol_info_tick(sym)
        si = mt5.symbol_info(sym)
        if tick is not None and si is not None and si.point:
            spread_pts = int(round((tick.ask - tick.bid) / si.point))
            rates = mt5.copy_rates_from_pos(sym, config.get_timeframe(sym), 0, 50)
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

    mode = config.sltp_mode_for(sym)

    if mode == "LLM":
        is_xau = "XAU" in sym.upper() or "GOLD" in sym.upper()

        if is_xau:
            if atr_points > 0:
                min_sl = max(spread_pts * 2, int(config.LLM_XAU_FLOOR_ATR_MULT * atr_points))
            else:
                min_sl = max(spread_pts * 2, config.LLM_SAFETY_FLOOR_XAU_PTS)
        else:
            if atr_points > 0:
                min_sl = max(spread_pts * 2, int(config.LLM_FX_FLOOR_ATR_MULT * atr_points))
            else:
                min_sl = max(spread_pts * 2, config.LLM_SAFETY_FLOOR_FX_PTS)
            
        if sl_points < min_sl:
            _last_sltp_adjustments.append(f"SL {sl_points} pts di bawah safety floor. Menyesuaikan SL ke {min_sl} pts.")
            sl_points = min_sl

        # Anti-wick padding untuk pair silang (misal NZD +20 pts)
        nzd_padding = config.sl_padding_for(config.SYMBOL)
        if nzd_padding > 0:
            sl_points += nzd_padding
            _last_sltp_adjustments.append(f"Anti-wick buffer +{nzd_padding} pts untuk {config.SYMBOL} (SL -> {sl_points} pts).")

        if tp_points <= 0:
            tp_points = config.default_tp_points_for(config.SYMBOL)

        min_rr = config.LLM_MIN_RR_RATIO
        max_rr = getattr(config, "LLM_MAX_RR_RATIO", 3.0)
        min_tp = int(sl_points * min_rr)
        max_tp = int(sl_points * max_rr)
        if tp_points < min_tp:
            _last_sltp_adjustments.append(f"TP {tp_points} pts < {min_rr}x SL. Menyesuaikan TP ke {min_tp} pts (R:R {min_rr}:1).")
            tp_points = min_tp
        elif tp_points > max_tp:
            _last_sltp_adjustments.append(f"TP {tp_points} pts > {max_rr}x SL. Membatasi TP ke {max_tp} pts (R:R {max_rr}:1).")
            tp_points = max_tp

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
        v_drop_str = f"{v_drop:.0f}" if isinstance(v_drop, float) and v_drop.is_integer() else str(v_drop)
        note = f"Outlier {label} dibuang (median {median:.0f}): {v_drop_str}"
        filtered = [v for v in values if v != v_drop]
        return filtered, note
    return values, None


def calculate_consensus(decisions):
    box_items = []
    
    point = 0.00001
    ref_price = 0.0
    try:
        from config import mt5
        si = mt5.symbol_info(config.SYMBOL)
        tick = mt5.symbol_info_tick(config.SYMBOL)
        if si and si.point:
            point = si.point
        if tick:
            ref_price = tick.bid
    except Exception:
        pass

    # Print details for each model
    for model_name, dec in decisions.items():
        sig = dec.get("signal") or "HOLD"
        conf = dec.get("confidence") if dec.get("confidence") is not None else 0.0
        reason = dec.get("reasoning") or "Tidak ada alasan."
        if len(reason) > 380:
            reason = reason[:377] + "..."

        exec_block = dec.get("execution") or {}
        entry_type = (exec_block.get("entry_type") or dec.get("entry_type") or "market").strip().lower()
        entry_price = exec_block.get("entry_price") or dec.get("entry_price")
        sl_price = exec_block.get("sl_price") or dec.get("invalidation_price")
        tp_price = exec_block.get("tp_price") or dec.get("target_price")

        base_ref = entry_price if (entry_type != "market" and isinstance(entry_price, (int, float)) and entry_price > 0) else ref_price

        sl = dec.get("sl_points")
        tp = dec.get("tp_points")
        if (sl is None or sl <= 0) and sl_price and point > 0 and base_ref > 0:
            sl = int(round(abs(base_ref - float(sl_price)) / point))
        if (tp is None or tp <= 0) and tp_price and point > 0 and base_ref > 0:
            tp = int(round(abs(base_ref - float(tp_price)) / point))

        setup_label = dec.get("setup")
        
        badge = UI.badge_signal(sig)
        bar = UI.make_bar(conf, 1.0, width=8)
        
        # Format info eksekusi (Market vs Pending Order)
        if sig in ("BUY", "SELL"):
            if entry_type != "market" and entry_price:
                exec_str = f"{entry_type.upper()} @ {entry_price}"
            else:
                exec_str = "MARKET"
            sltp_info = f"{exec_str} | SL: {sl} pts, TP: {tp} pts"
        else:
            sltp_info = "SL/TP: -"
        
        verdict_str = f" {UI.badge_verdict(dec.get('verdict'))}" if dec.get("verdict") else ""
        box_items.append(f"{UI.BOLD}{model_name:<10}{UI.RST}: {badge} {bar}{verdict_str} | {UI.DIM}{sltp_info}{UI.RST}")
        
        # 1. State / Decision Framework Context (Regime, Setup, State, RR Valid, Risk Flag)
        regime_val = dec.get("market_regime") or dec.get("trend")
        state_val = dec.get("state")
        rr_val = dec.get("rr_valid")
        risk_flag = dec.get("risk_flag")
        ctx_parts = []
        if regime_val:
            ctx_parts.append(f"Regime: {regime_val}")
        if setup_label:
            ctx_parts.append(f"Setup: {setup_label}")
        if state_val:
            ctx_parts.append(f"State: {state_val}")
        if risk_flag and risk_flag != "NONE":
            ctx_parts.append(f"Risk: {risk_flag}")
        if rr_val is not None:
            rr_str = "✓" if rr_val else "✗"
            ctx_parts.append(f"RR: {rr_str}")
        elif dec.get("velocity"):
            ctx_parts.append(f"Velocity: {dec.get('velocity')}")
        if ctx_parts:
            box_items.append((f"  {UI.CYAN}Context{UI.RST} : ", " | ".join(ctx_parts)))
        
        # 2. Tampilkan level teknikal (Inval & Target) jika tersedia di JSON
        levels_info = []
        if sl_price:
            levels_info.append(f"SL Price: {sl_price}")
        if tp_price:
            levels_info.append(f"TP Price: {tp_price}")
        if levels_info:
            box_items.append((f"  {UI.RED}Levels{UI.RST} : ", " | ".join(levels_info)))

        # 3. Reason / Veto Reason
        if dec.get("veto_reason"):
            box_items.append((f"  {UI.RED}Veto{UI.RST}   : ", dec.get("veto_reason")))
        box_items.append((f"  {UI.GRAY}Reason{UI.RST} : ", reason))

        
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

    # Qualified Hard Risk Veto Engine (Preserves Capital against Critical Traps)
    hard_veto_models = []
    VALID_HARD_VETO_FLAGS = (
        "COUNTER_TREND_MOMENTUM", "HIGH_IMPACT_NEWS", "LIQUIDITY_TRAP",
        "SPREAD_SPIKE", "INSTANT_RETEST", "NEAR_EQH_EQL", "ROLLOVER_WINDOW",
        "FALLING_KNIFE_WATERFALL", "UNMITIGATED_IMPULSE_CHASE", "SYSTEMIC_CURRENCY_DUMP"
    )
    for model_name, dec in decisions.items():
        rf = dec.get("risk_flag")
        vd = dec.get("verdict")
        if (vd == "REJECT" or dec.get("veto_reason")) and rf in VALID_HARD_VETO_FLAGS:
            hard_veto_models.append((model_name, rf, dec.get("veto_reason") or dec.get("reasoning") or "Critical Risk Detected"))

    if hard_veto_models and consensus_signal in ("BUY", "SELL"):
        veto_names = ", ".join([v[0] for v in hard_veto_models])
        veto_reasons = " | ".join([f"{v[0]}: {v[1]} ({v[2]})" for v in hard_veto_models])
        box_items.append("---")
        box_items.append(f"{UI.RED}{UI.BOLD}[⛔ HARD RISK VETO AKTIF] Trade {consensus_signal} Dibatalkan oleh {veto_names}!{UI.RST}")
        box_items.append((f"  {UI.RED}Alasan Veto{UI.RST} : ", veto_reasons))
        consensus_signal = "HOLD"
        agreeing_models = []

    if consensus_signal == "HOLD":
        box_items.append("---")
        box_items.append(f"{UI.YELLOW}[*] HASIL: TIDAK ADA KONSENSUS (HOLD){UI.RST}")
        box_items.append((f"  {UI.DIM}Skor Arah:{UI.RST} ", f"BUY={direction_scores['BUY']:.2f}, SELL={direction_scores['SELL']:.2f} (Threshold: {threshold:.2f})"))
        print("\n" + UI.make_box("ANALISIS KONSENSUS MULTI-LLM", box_items, width=100, border_color=UI.CYAN) + "\n")
        
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
        
        exec_block = dec.get("execution") or {}
        entry_type = (exec_block.get("entry_type") or dec.get("entry_type") or "market").strip().lower()
        ep = exec_block.get("entry_price") or dec.get("entry_price")
        base_ref = ep if (entry_type != "market" and isinstance(ep, (int, float)) and ep > 0) else ref_price

        inv_val = exec_block.get("sl_price") or dec.get("invalidation_price")
        if isinstance(inv_val, (int, float)) and inv_val > 0:
            inv_list.append(inv_val)
        
        tgt_val = exec_block.get("tp_price") or dec.get("target_price")
        if isinstance(tgt_val, (int, float)) and tgt_val > 0:
            tgt_list.append(tgt_val)
        
        sl_val = dec.get("sl_points")
        if (sl_val is None or sl_val <= 0) and inv_val and point > 0 and base_ref > 0:
            sl_val = int(round(abs(base_ref - float(inv_val)) / point))
        if isinstance(sl_val, (int, float)) and sl_val > 0:
            sl_list.append(sl_val)
        
        tp_val = dec.get("tp_points")
        if (tp_val is None or tp_val <= 0) and tgt_val and point > 0 and base_ref > 0:
            tp_val = int(round(abs(base_ref - float(tgt_val)) / point))
        if isinstance(tp_val, (int, float)) and tp_val > 0:
            tp_list.append(tp_val)
        
        if entry_type not in ("market", "buy_stop", "sell_stop", "buy_limit", "sell_limit"):
            entry_type = "market"
        entry_type_votes[entry_type] = entry_type_votes.get(entry_type, 0) + 1
        
        if isinstance(ep, (int, float)) and ep > 0:
            entry_price_list.append(ep)

    outlier_notes = []

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

    # Guardrail entry pending (Filosofi: Percayakan pada LLM, No Trade is Better)
    if final_entry_type != "market" and final_entry_price is not None:
        try:
            from config import mt5
            tick = mt5.symbol_info_tick(config.SYMBOL)
            si = mt5.symbol_info(config.SYMBOL)
            point = si.point if si else 0.00001
            ref_price = tick.ask if consensus_signal == "BUY" else tick.bid
            dist_pts = abs(final_entry_price - ref_price) / point if (point and ref_price) else None
            spread_pts = int(round((tick.ask - tick.bid) / point)) if (tick and point) else 0

            min_dist = spread_pts * float(getattr(config, "PENDING_ENTRY_MIN_SPREAD_MULT", 2.0))

            # Jika harga limit terlalu mepet (< 2x spread) -> eksekusi langsung di market
            if dist_pts is not None and dist_pts < min_dist:
                outlier_notes.append(f"Entry limit {final_entry_price} sangat dekat (< {min_dist:.0f} pts) -> eksekusi Market")
                final_entry_type = "market"
                final_entry_price = None
            else:
                # Verifikasi arah limit valid (Buy Limit di bawah ask, Sell Limit di atas bid)
                if consensus_signal == "BUY" and final_entry_type == "buy_limit" and final_entry_price >= ref_price:
                    outlier_notes.append(f"Buy Limit {final_entry_price} di atas harga pasar -> disesuaikan ke Market")
                    final_entry_type = "market"
                    final_entry_price = None
                elif consensus_signal == "SELL" and final_entry_type == "sell_limit" and final_entry_price <= ref_price:
                    outlier_notes.append(f"Sell Limit {final_entry_price} di bawah harga pasar -> disesuaikan ke Market")
                    final_entry_type = "market"
                    final_entry_price = None
        except Exception:
            pass

    try:
        from config import mt5
        tick = mt5.symbol_info_tick(config.SYMBOL)
        si = mt5.symbol_info(config.SYMBOL)
        point = si.point if si else 0.00001
        if tick and si and point:
            exec_ref = final_entry_price if (final_entry_type != "market" and final_entry_price) else (tick.ask if consensus_signal == "BUY" else tick.bid)
            if exec_ref > 0:
                if consensus_signal == "BUY":
                    final_inv = exec_ref - (final_sl * point)
                    final_tgt = exec_ref + (final_tp * point)
                else:
                    final_inv = exec_ref + (final_sl * point)
                    final_tgt = exec_ref - (final_tp * point)
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
        print("\n" + UI.make_box("ANALISIS KONSENSUS MULTI-LLM", box_items, width=100, border_color=UI.CYAN) + "\n")
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
    best_state = ""
    best_reason = ""
    best_invalidation = ""
    sorted_agreeing = sorted(agreeing_models, key=lambda m: decisions.get(m, {}).get("confidence", 0.0), reverse=True)
    for m in sorted_agreeing:
        dec = decisions.get(m, {})
        s_candidate = (dec.get("setup") or "").strip()
        st_candidate = (dec.get("state") or "").strip()
        r_candidate = (dec.get("reasoning") or dec.get("edge") or "").strip()
        i_candidate = (dec.get("invalidation") or "").strip()
        if s_candidate and not best_setup:
            best_setup = " ".join(s_candidate.replace("\n", " ").replace("\r", " ").split())
        if st_candidate and not best_state:
            best_state = " ".join(st_candidate.replace("\n", " ").replace("\r", " ").split())
        if r_candidate and not best_reason:
            best_reason = " ".join(r_candidate.replace("\n", " ").replace("\r", " ").split())
        if i_candidate and not best_invalidation:
            best_invalidation = " ".join(i_candidate.replace("\n", " ").replace("\r", " ").split())
        elif not best_invalidation and dec.get("invalidation_price"):
            best_invalidation = f"Level {dec.get('invalidation_price')}"
        if best_setup and best_reason and best_invalidation:
            break

    agreeing_details = []
    for m in agreeing_models:
        d = decisions.get(m, {})
        exec_block = d.get("execution", {}) if isinstance(d.get("execution"), dict) else {}
        et = (exec_block.get("entry_type") or d.get("entry_type") or "market").strip().lower()
        ep = exec_block.get("entry_price") or d.get("entry_price")
        if et != "market" and ep:
            agreeing_details.append(f"{m} ({et} @ {ep})")
        else:
            agreeing_details.append(f"{m} ({et})")
    agreeing_models_str = ", ".join(agreeing_details)

    badge = UI.badge_signal(consensus_signal)
    box_items.append(f"{UI.GREEN}[+] KONSENSUS DISETUJUI:{UI.RST} {badge} {UI.BOLD}(Skor {best_score:.2f} >= {threshold:.2f}){UI.RST}")
    box_items.append((f"  {UI.BOLD}Model Sepakat :{UI.RST} ", f"{agreeing_models_str} (Avg Conf: {avg_confidence*100:.1f}%)"))
    
    setup_state_str = f"[{best_setup} | {best_state}]" if (best_setup and best_state) else (best_setup or best_state or "")
    if setup_state_str:
        box_items.append((f"  {UI.CYAN}Setup / State :{UI.RST} ", setup_state_str))
    if best_reason:
        box_items.append((f"  {UI.CYAN}Reason        :{UI.RST} ", best_reason))
    price_decimals = 5 if (point and point < 0.001) else 2
    price_info = f" | Price SL {final_inv:.{price_decimals}f} / TP {final_tgt:.{price_decimals}f}" if final_inv else ""
    box_items.append((f"  {UI.BOLD}Final SL / TP :{UI.RST} ", f"{UI.RED}SL {final_sl} pts{UI.RST} | {UI.GREEN}TP {final_tp} pts{UI.RST}{price_info}"))

    print("\n" + UI.make_box("ANALISIS KONSENSUS MULTI-LLM", box_items, width=100, border_color=UI.CYAN) + "\n")

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
        "agreeing_models_str": agreeing_models_str,
        "setup": best_setup,
        "state": best_state,
        "reason": best_reason,
        "invalidation_text": best_invalidation,
        "tickets_to_close": tickets_to_close,
        "details": f"Consensus by: {agreeing_models}"
    }
