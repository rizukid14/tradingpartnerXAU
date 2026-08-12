import config
from src.analytics import dynamic_config


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
      "LLM": SL/TP sebebas-bebasnya sesuai konsensus - cuma floor 2x spread
        (biar broker nggak nolak INVALID_STOPS). Lot size dikalkulasi dari SL
        tsb via risk-based sizing, jadi SL kecil = lot gede (risk tetap sama).
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

    mode = getattr(config, "TP_SL_RULES", "ATR-Based")
    if mode == "LLM":
        # Bebas sesuai konsensus, cuma dibatasi floor 2x spread (biar broker nggak nolak)
        min_sl = spread_pts * 2
        if sl_points < min_sl:
            sl_points = min_sl
        # TP minimal harus default, dan dipaksa minimal sama dengan SL (TP >= 1.0x SL) untuk mencegah R:R negatif
        if tp_points <= 0:
            tp_points = config.default_tp_points_for(config.SYMBOL)
        if tp_points < sl_points:
            tp_points = sl_points
        return sl_points, tp_points, True, ""

    # ATR-Based: GATE layak/tidak. Proposal AI dipakai kalau lolos.
    # Multiplier per AI mode (config.atr_sl_multiplier / atr_tp_multiplier):
    # single 1.25/2.5, dual 1.5/3.0, triple 1.75/3.5 (R:R 2:1 selalu).
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

    # ATR gagal dihitung: fallback ke floor 2x spread, tetap izinkan (jangan
    # stop trading karena data hiccup).
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
    print("\n" + "="*50)
    print("          ANALISIS KONSENSUS MULTI-LLM           ")
    print("="*50)
    
    # Print details for each model
    for model_name, dec in decisions.items():
        sig = dec.get("signal") or "HOLD"
        conf = dec.get("confidence") if dec.get("confidence") is not None else 0.0
        reason = dec.get("reasoning") or "Tidak ada alasan."
        sl = dec.get("sl_points")
        tp = dec.get("tp_points")
        
        print(f" [{model_name}] Decision: {sig} (Conf: {conf*100:.1f}%)")
        print(f"   SL: {sl} pts, TP: {tp} pts")
        print(f"   Reason: {reason}")
        print("-" * 50)
        
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
        print(f" [KONSENSUS GAGAL] Skor arah: BUY={direction_scores['BUY']:.2f}, "
              f"SELL={direction_scores['SELL']:.2f} (threshold {threshold}). Posisi: HOLD.")
        print("=" * 50 + "\n")
        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "sl_points": config.default_sl_points_for(config.SYMBOL),
            "tp_points": config.default_tp_points_for(config.SYMBOL),
            "agreeing_count": 0,
            "agreeing_models": [],
            "tickets_to_close": tickets_to_close,
            "details": f"Consensus failed (BUY={direction_scores['BUY']:.2f}, SELL={direction_scores['SELL']:.2f})"
        }

    # Calculate average SL, TP and Confidence of agreeing models
    sl_list = []
    tp_list = []
    conf_list = []
    for name in agreeing_models:
        dec = decisions[name]
        conf_list.append(dec.get("confidence", 0.5))
        sl_val = dec.get("sl_points")
        if isinstance(sl_val, (int, float)) and sl_val > 0:
            sl_list.append(sl_val)
        tp_val = dec.get("tp_points")
        if isinstance(tp_val, (int, float)) and tp_val > 0:
            tp_list.append(tp_val)

    # Filter outlier SL/TP: buang nilai yang "beda sendiri" sebelum di-average.
    # Aturan user (mode LLM):
    #   - 2/3 model sepakat -> yang nggak sepakat dibuang, 2 yang sepakat di-average
    #   - 3/3 model beda semua -> yang paling jauh dari median dibuang (1 aja),
    #     2 sisanya di-average
    # Contoh: OpenAI kasih SL 30 pts saat Gemini 400 & DeepSeek 305 - SL 30
    # cuma 10% ATR, menyeret rata-rata ke bawah & bikin lot membengkak.
    # Median lebih robust daripada mean untuk deteksi anomali.
    sl_list = _drop_standalone_outlier(sl_list, "SL")
    tp_list = _drop_standalone_outlier(tp_list, "TP")

    avg_confidence = float(sum(conf_list) / len(conf_list))
    final_sl = int(sum(sl_list) / len(sl_list)) if sl_list else config.default_sl_points_for(config.SYMBOL)
    final_tp = int(sum(tp_list) / len(tp_list)) if tp_list else config.default_tp_points_for(config.SYMBOL)

    # Apply SL/TP rules (mode-aware):
    #   ATR-Based -> GATE: trade hanya layak kalau SL >= SL_MULTx ATR DAN
    #                TP >= TP_MULTx ATR. Multiplier dinamis per AI mode
    #                (single 1.25/2.5, dual 1.5/3.0, triple 1.75/3.5).
    #                Kalau jarak proposal kurang -> trade DIBATALKAN (bukan dinaikkan).
    #   LLM       -> bebas, cuma floor 2x spread.
    final_sl, final_tp, sltp_ok, sltp_reason = _apply_sltp_rules(final_sl, final_tp)

    if not sltp_ok:
        print(f" [TRADE DIBATALKAN] Sinyal {consensus_signal} tidak dieksekusi: {sltp_reason}")
        print("  Model sepakat arah, tapi SL/TP proposal tidak memenuhi rules ATR "
              "(R:R 2:1 terhadap volatilitas). Cari setup lain.")
        print("=" * 50 + "\n")
        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "sl_points": final_sl,
            "tp_points": final_tp,
            "agreeing_count": len(agreeing_models),
            "agreeing_models": list(agreeing_models),
            "tickets_to_close": tickets_to_close,
            "details": f"SL/TP gate ATR gagal: {sltp_reason}"
        }

    print(f" [KONSENSUS DISETUJUI] Sinyal: {consensus_signal} "
          f"(skor {best_score:.2f} >= threshold {threshold})")
    print(f"   Model yang sepakat: {', '.join(agreeing_models)}")
    print(f"   Rata-rata Keyakinan: {avg_confidence*100:.1f}%")
    print(f"   Final SL: {final_sl} points | Final TP: {final_tp} points")
    print("=" * 50 + "\n")

    return {
        "signal": consensus_signal,
        "confidence": avg_confidence,
        "sl_points": final_sl,
        "tp_points": final_tp,
        "agreeing_count": len(agreeing_models),
        "agreeing_models": list(agreeing_models),  # nama model yang sepakat (buat comment order)
        "tickets_to_close": tickets_to_close,
        "details": f"Consensus by: {agreeing_models}"
    }
