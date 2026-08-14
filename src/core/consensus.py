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


def _apply_sltp_rules(sl_points, tp_points):
    """
    SL/TP final sesuai config.TP_SL_RULES:
      "ATR-Based" (default): GATE - proposal AI DIPAKAI apa adanya (setelah
        outlier filter + average), tapi trade HANYA dieksekusi kalau:
          SL >= max(2x spread, SL_MULTx ATR) DAN TP >= max(2x spread, TP_MULTx ATR)
        SL_MULT/TP_MULT dinamis per AI mode (R:R 2:1 selalu):
        single 1.25/2.5, dual 1.5/3.0, triple 1.75/3.5.
        Kalau jarak proposal kurang dari itu -> trade DIBATALKAN (return
        ok=False), BUKAN dinaikkan. Filosofi: cari setup yang secara alamiah
        bisa kasih R:R 2:1 terhadap volatilitas; memaksa SL/TP lebih jauh dari
        invalidation model = mengubah setup tanpa persetujuan model.
      "LLM": SL/TP bebas sesuai konsensus, dibatasi safety floor per-kategori
        (14 Agustus: XAU 400 pts, FX 250 pts / 25 pips) + R:R minimum 1.25:1
        (TP di-floor ke 1.25x SL kalau kurang - bukan tolak). Lot size
        dikalkulasi dari SL tsb via risk-based sizing.
    Returns: (sl_points, tp_points, ok: bool, reason: str)
    """
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
            # ATR from the active timeframe (M30 for BTC) - volatility floor
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

    mode = config.sltp_mode_for(config.SYMBOL)  # per-kategori: XAU LLM, BTC ATR-Based, FX LLM

    if mode == "LLM":
        # Mode LLM (Bebas sesuai thesis struktur AI, tapi dengan safety floor dan R:R gate)
        is_xau = "XAU" in config.SYMBOL.upper() or "GOLD" in config.SYMBOL.upper()

        if is_xau:
            # Gold: safety floor minimal 400 pts untuk mencegah SL super sempit
            min_sl = max(spread_pts * 2, config.LLM_SAFETY_FLOOR_XAU_PTS)
        else:
            # FX pairs: floor minimal 250 pts (25 pips) - mencegah SL mikro 5 pips
            min_sl = max(spread_pts * 2, config.LLM_SAFETY_FLOOR_FX_PTS)
            
        if sl_points < min_sl:
            print(f"   [!] SL {sl_points} pts di bawah safety floor. Menyesuaikan SL ke {min_sl} pts.")
            sl_points = min_sl

        if tp_points <= 0:
            tp_points = config.default_tp_points_for(config.SYMBOL)

        # R:R minimum 1.25:1 (14 Agustus) - TP dinaikkan ke minimal 1.25x SL
        min_rr = config.LLM_MIN_RR_RATIO
        min_tp = int(sl_points * min_rr)
        if tp_points < min_tp:
            print(f"   [!] TP {tp_points} pts < {min_rr}x SL. Menyesuaikan TP ke {min_tp} pts (R:R {min_rr}:1).")
            tp_points = min_tp

        # GATE OVER-RISK (13 Agustus): kalau risk minimum yang bisa diwakili
        # (volume_min x SL) sudah MELEBIHI budget risk -> trade DITOLAK.
        # Contoh XAU: equity $1079, risk 1.0% = $10.79, min lot 0.01, usd/pt $1
        #   -> max SL = 1079 pts. SL 1736 pts -> risk aktual $17.36 (1.6%) -> TOLAK.
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
            if equity > 0 and usd_pt > 0 and vol_min > 0:
                max_sl = (equity * risk_pct / 100.0) / (vol_min * usd_pt)
                if sl_points > max_sl:
                    risk_actual = sl_points * vol_min * usd_pt
                    return sl_points, tp_points, False, (
                        f"OVER-RISK: SL {sl_points} pts > max {max_sl:.0f} pts "
                        f"(risk {risk_pct}% = ${equity*risk_pct/100:.2f} gak muat di min lot {vol_min}: "
                        f"risk aktual ${risk_actual:.2f} = {risk_actual/equity*100:.2f}%)"
                    )
        except Exception:
            pass

        return sl_points, tp_points, True, ""

    # Mode ATR-Based: GATE LAYAK/TIDAK (Non-negotiable).
    # Jika mode "ATR-Based" dipilih, ATR Hard Gate BERLAKU untuk semua aset.
    # Proposal AI dipakai apa adanya kalau lolos, DITOLAK kalau kurang.
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

    # ATR gagal dihitung: fallback ke floor 2x spread, tetap izinkan
    if sl_points < spread_pts * 2:
        sl_points = spread_pts * 2
    if tp_points < sl_points:
        tp_points = sl_points
    return sl_points, tp_points, True, "ATR unavailable, fallback 2x spread"


def _drop_standalone_outlier(values, label):
    """
    Buang nilai yang "beda sendiri" sebelum di-average, sesuai aturan user:
      - 2/3 model sepakat -> nilai yang nggak sepakat (<50% atau >200% dari
        median) dibuang, 2 yang sepakat di-average.
      - 3/3 model beda semua -> yang paling jauh dari median dibuang (1 aja),
        2 sisanya di-average.
      - Semua nilai dalam band 0.5x-2x median -> nggak ada yang dibuang,
        semua di-average.
    Median lebih robust daripada mean buat deteksi anomali. Maksimal 1 nilai
    yang dibuang - nggak pernah buang semua.
    """
    if len(values) <= 2:
        return values
    s = sorted(values)
    n = len(s)
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0
    low = [v for v in s if v < 0.5 * median]
    high = [v for v in s if v > 2.0 * median]
    dropped = []
    if low and high:
        # Dua sisi anomali sekaligus - buang yang paling jauh dari median
        if median - min(low) >= max(high) - median:
            dropped = [min(low)]
        else:
            dropped = [max(high)]
    elif low:
        dropped = [min(low)]
    elif high:
        dropped = [max(high)]

    keep = [v for v in values if v not in dropped]
    if not keep:
        return values  # jangan buang semua kalau median-nya sendiri anomali
    if dropped:
        print(f"   [!] Outlier {label} dibuang (median {median:.0f}): "
              f"{', '.join(str(int(d)) for d in dropped)}")
    return keep


def calculate_consensus(decisions):
    """
    Analyzes decisions from all 3 LLMs and determines if consensus is met.
    The threshold is read from DynamicConfig (self-tuning); falls back to
    config.CONSENSUS_THRESHOLD if dynamic_rules is unavailable.
    decisions: dict of model decisions, e.g.:
      {
        "OpenAI": {"signal": "BUY", "confidence": 0.8, "sl_points": 300, "tp_points": 600, "reasoning": "..."},
        "Gemini": {"signal": "BUY", "confidence": 0.9, "sl_points": 250, "tp_points": 500, "reasoning": "..."},
        "Claude": {"signal": "HOLD", "confidence": 0.0, "sl_points": None, "tp_points": None, "reasoning": "..."}
      }
    Returns:
      dict: {
        "signal": "BUY" | "SELL" | "HOLD",
        "confidence": float,
        "sl_points": int,
        "tp_points": int,
        "agreeing_count": int,
        "tickets_to_close": list,
        "details": str
      }
    """
    print(f"\n{UI.CYAN}+-- [ANALISIS KONSENSUS MULTI-LLM] --------------------------------+{UI.RST}")
    
    # Print details for each model
    for model_name, dec in decisions.items():
        sig = dec.get("signal") or "HOLD"
        conf = dec.get("confidence") if dec.get("confidence") is not None else 0.0
        reason = dec.get("reasoning") or "Tidak ada alasan."
        sl = dec.get("sl_points")
        tp = dec.get("tp_points")
        setup_label = dec.get("setup")
        
        badge = UI.badge_signal(sig)
        bar = UI.make_bar(conf, 1.0, width=8)
        sltp_info = f"SL: {sl} pts, TP: {tp} pts" if sig in ("BUY", "SELL") else "SL/TP: -"
        
        print(f"| {UI.BOLD}{model_name:<10}{UI.RST}: {badge} {bar} | {UI.DIM}{sltp_info}{UI.RST}")
        if setup_label:
            print(f"|   {UI.CYAN}Setup :{UI.RST} {setup_label}")
        print(f"|   {UI.GRAY}Reason:{UI.RST} {reason}")
        print(f"{UI.DIM}+------------------------------------------------------------------+{UI.RST}")
        
    # Check if we have a consensus for BUY or SELL
    consensus_signal = "HOLD"
    final_sl = config.default_sl_points_for(config.SYMBOL)
    final_tp = config.default_tp_points_for(config.SYMBOL)
    avg_confidence = 0.0
    
    # Evaluate consensus for active position early-close actions
    close_votes = {}  # ticket -> list of (model_name, reason)
    hold_reasons = {} # ticket -> list of (model_name, reason)
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
                            if ticket not in close_votes:
                                close_votes[ticket] = []
                            close_votes[ticket].append((model_name, reason_str))
                        else:
                            if ticket not in hold_reasons:
                                hold_reasons[ticket] = []
                            hold_reasons[ticket].append((model_name, reason_str))

    tickets_to_close = []
    consensus_threshold = _effective_consensus_threshold()
    n_models = len(decisions)
    # CLOSE votes adaptif: single-AI cukup 1 vote, dual 2/2, triple 2-3/3
    close_threshold = min(consensus_threshold, n_models)
    closed_ticket_ids = set()
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
            print(f" [AI RE-EVALUATOR] {len(votes)}/{n_models} AI ({models_str}) sepakat CLOSE order #{ticket}: {reason_sample}")

    for ticket in sorted(all_evaluated_tickets):
        if ticket not in closed_ticket_ids:
            reasons_list = hold_reasons.get(ticket, [])
            if reasons_list:
                m_str = ", ".join([r[0] for r in reasons_list])
                r_sample = reasons_list[0][1]
                print(f" [AI RE-EVALUATOR] Order #{ticket} dipertahankan (HOLD oleh {m_str}): {r_sample}")
            else:
                print(f" [AI RE-EVALUATOR] Order #{ticket} dipertahankan (HOLD) oleh konsensus AI.")

    # Dynamic weighted-confidence consensus: each model's confidence weights
    # its vote. A direction wins when BOTH:
    #   - at least min_models models voted that direction, and
    #   - the SUM of their confidence clears the per-symbol threshold
    #     (XAU 1.0, BTC 1.2, tightened to 1.8 in the 3/3 defensive regime).
    # Mode AI adaptif (time-based): single -> 1 model cukup (threshold diturunkan
    # karena skor max 1.0), dual -> 2/2, triple -> 2-3/3 seperti biasa.
    direction_scores = {"BUY": 0.0, "SELL": 0.0}
    direction_models = {"BUY": [], "SELL": []}
    for model_name, dec in decisions.items():
        sig = dec.get("signal") or "HOLD"
        conf = dec.get("confidence") if dec.get("confidence") is not None else 0.0
        if sig in direction_scores:
            direction_scores[sig] += conf
            direction_models[sig].append(model_name)

    # Per-symbol base threshold, scaled by the dynamic regime count
    # (2-model regime keeps the base; 3-model defensive regime -> *1.5 = 1.8 BTC)
    min_models = getattr(config, "MIN_CONSENSUS_MODELS", 2)
    base_threshold = config.confidence_threshold_for(config.SYMBOL)
    if getattr(config, "FORCE_ACTIVE_ENTRY", False):
        base_threshold *= 0.7

    ai_mode = getattr(config, "get_ai_mode", lambda: "triple")()
    if ai_mode == "single":
        # 1 model saja: skor max 1.0 -> threshold diturunkan (misal XAU 0.6 / BTC 0.72)
        min_models = 1
        threshold = base_threshold * 0.6
    else:
        min_models = min(min_models, len(decisions))
        eff_count = min(_effective_consensus_threshold(), len(decisions))
        threshold = base_threshold * (eff_count / min_models)

    # Pick the direction with the highest weighted score that clears threshold
    consensus_signal = "HOLD"
    agreeing_models = []
    best_score = threshold  # must strictly beat this
    for sig in ["BUY", "SELL"]:
        if len(direction_models[sig]) >= min_models and direction_scores[sig] > best_score:
            consensus_signal = sig
            agreeing_models = direction_models[sig]
            best_score = direction_scores[sig]

    if consensus_signal == "HOLD":
        print(f"| {UI.YELLOW}[*] HASIL: TIDAK ADA KONSENSUS (HOLD){UI.RST}")
        print(f"|   {UI.DIM}Skor Arah: BUY={direction_scores['BUY']:.2f}, SELL={direction_scores['SELL']:.2f} (Threshold: {threshold:.2f}){UI.RST}")
        print(f"{UI.CYAN}+------------------------------------------------------------------+{UI.RST}\n")
        
        # Klasifikasi tipe HOLD untuk smart close-call alert
        any_trade_intent = any(dec.get("signal") in ("BUY", "SELL") for dec in decisions.values())
        if not any_trade_intent:
            hold_type = "pure_hold"
        elif ai_mode == "single":
            hold_type = "low_confidence"
        else:
            hold_type = "split_vote"

        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "sl_points": config.default_sl_points_for(config.SYMBOL),
            "tp_points": config.default_tp_points_for(config.SYMBOL),
            "agreeing_count": 0,
            "agreeing_models": [],
            "tickets_to_close": tickets_to_close,
            "hold_type": hold_type,
            "threshold": threshold,
            "direction_scores": direction_scores,
            "decisions": decisions,
            "ai_mode": ai_mode,
            "details": f"Consensus failed (BUY={direction_scores['BUY']:.2f}, SELL={direction_scores['SELL']:.2f})"
        }

    # Calculate average SL, TP, Confidence and absolute prices of agreeing models
    inv_list = []
    tgt_list = []
    sl_list = []
    tp_list = []
    conf_list = []
    for name in agreeing_models:
        dec = decisions[name]
        conf_list.append(dec.get("confidence", 0.5))
        
        inv_val = dec.get("invalidation_price")
        if isinstance(inv_val, (int, float)) and inv_val > 0:
            inv_list.append(inv_val)
        tgt_val = dec.get("target_price")
        if isinstance(tgt_val, (int, float)) and tgt_val > 0:
            tgt_list.append(tgt_val)
            
        sl_val = dec.get("sl_points")
        if isinstance(sl_val, (int, float)) and sl_val > 0:
            sl_list.append(sl_val)
        tp_val = dec.get("tp_points")
        if isinstance(tp_val, (int, float)) and tp_val > 0:
            tp_list.append(tp_val)

    # Filter outliers: buang nilai yang "beda sendiri" sebelum di-average.
    inv_list = _drop_standalone_outlier(inv_list, "Invalidation Price")
    tgt_list = _drop_standalone_outlier(tgt_list, "Target Price")
    sl_list = _drop_standalone_outlier(sl_list, "SL Points")
    tp_list = _drop_standalone_outlier(tp_list, "TP Points")

    avg_confidence = float(sum(conf_list) / len(conf_list)) if conf_list else 0.0
    final_inv = sum(inv_list) / len(inv_list) if inv_list else None
    final_tgt = sum(tgt_list) / len(tgt_list) if tgt_list else None

    # Resolve points from absolute price levels if available, using the current tick
    resolved_sl_from_price = None
    resolved_tp_from_price = None

    try:
        from config import mt5
        tick = mt5.symbol_info_tick(config.SYMBOL)
        si = mt5.symbol_info(config.SYMBOL)
        point = si.point if si else 0.00001
    except Exception:
        tick, si, point = None, None, 0.00001

    if tick and si and point:
        entry_price = tick.ask if consensus_signal == "BUY" else tick.bid
        if entry_price > 0:
            if final_inv:
                resolved_sl_from_price = int(round(abs(entry_price - final_inv) / point))
            if final_tgt:
                resolved_tp_from_price = int(round(abs(final_tgt - entry_price) / point))

    # Determine final points (prefer resolved prices, fallback to point list/defaults)
    final_sl = resolved_sl_from_price if resolved_sl_from_price is not None else (
        int(sum(sl_list) / len(sl_list)) if sl_list else config.default_sl_points_for(config.SYMBOL)
    )
    final_tp = resolved_tp_from_price if resolved_tp_from_price is not None else (
        int(sum(tp_list) / len(tp_list)) if tp_list else config.default_tp_points_for(config.SYMBOL)
    )

    # Apply SL/TP rules (mode-aware ATR/spread gates)
    final_sl, final_tp, sltp_ok, sltp_reason = _apply_sltp_rules(final_sl, final_tp)

    # Sync absolute price levels with final clamped points to guarantee consistency
    if tick and si and point:
        entry_price = tick.ask if consensus_signal == "BUY" else tick.bid
        if entry_price > 0:
            if consensus_signal == "BUY":
                final_inv = entry_price - (final_sl * point)
                final_tgt = entry_price + (final_tp * point)
            else:
                final_inv = entry_price + (final_sl * point)
                final_tgt = entry_price - (final_tp * point)

    if not sltp_ok:
        print(f"| {UI.RED}[-] HASIL: TRADE DIBATALKAN OLEH GATE ATR{UI.RST}")
        print(f"|   {UI.RED}{sltp_reason}{UI.RST}")
        print(f"{UI.CYAN}+------------------------------------------------------------------+{UI.RST}\n")
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

    # Extract best open reason/setup from agreeing models for MT5 comment & logging
    best_reason = ""
    sorted_agreeing = sorted(
        agreeing_models,
        key=lambda m: decisions.get(m, {}).get("confidence", 0.0),
        reverse=True
    )
    for m in sorted_agreeing:
        dec = decisions.get(m, {})
        candidate = (dec.get("setup") or "").strip()
        if not candidate:
            candidate = (dec.get("reasoning") or dec.get("edge") or "").strip()
        if candidate:
            candidate = " ".join(candidate.replace("\n", " ").replace("\r", " ").split())
            best_reason = candidate
            break

    badge = UI.badge_signal(consensus_signal)
    print(f"| {UI.GREEN}[+] KONSENSUS DISETUJUI:{UI.RST} {badge} {UI.BOLD}(Skor {best_score:.2f} >= {threshold:.2f}){UI.RST}")
    print(f"|   {UI.BOLD}Model Sepakat :{UI.RST} {', '.join(agreeing_models)} (Avg Conf: {avg_confidence*100:.1f}%)")
    if best_reason:
        print(f"|   {UI.CYAN}Setup / Reason:{UI.RST} {best_reason}")
    price_info = f" | Price SL {final_inv:.2f} / TP {final_tgt:.2f}" if final_inv else ""
    print(f"|   {UI.BOLD}Final SL / TP :{UI.RST} {UI.RED}SL {final_sl} pts{UI.RST} | {UI.GREEN}TP {final_tp} pts{UI.RST}{price_info}")
    print(f"{UI.CYAN}+------------------------------------------------------------------+{UI.RST}\n")

    return {
        "signal": consensus_signal,
        "confidence": avg_confidence,
        "sl_points": final_sl,
        "tp_points": final_tp,
        "invalidation_price": final_inv,
        "target_price": final_tgt,
        "agreeing_count": len(agreeing_models),
        "agreeing_models": list(agreeing_models),  # nama model yang sepakat
        "reason": best_reason,                     # reason/setup untuk MT5 comment
        "tickets_to_close": tickets_to_close,
        "details": f"Consensus by: {agreeing_models}"
    }
