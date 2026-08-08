import config
from src.analytics import dynamic_config


def _effective_consensus_threshold():
    """Returns the active consensus threshold (dynamic rules win over static config)."""
    try:
        return int(dynamic_config.dynamic_rules.consensus_threshold)
    except Exception:
        return config.CONSENSUS_THRESHOLD


def _apply_sltp_floors(sl_points, tp_points):
    """
    Enforce minimum SL/TP so the LLM cannot propose stops inside the spread
    (which the broker would reject with INVALID_STOPS) or tiny distances that
    are worth only cents. Floors:
      - SL >= default SL for the symbol (per-symbol safe risk distance)
      - SL >= 2x current spread (never inside the spread)
      - TP >= 1.5x final SL (keep R:R sane)
    """
    if not sl_points or sl_points <= 0:
        sl_points = config.default_sl_points_for(config.SYMBOL)
    if not tp_points or tp_points <= 0:
        tp_points = config.default_tp_points_for(config.SYMBOL)

    # 2x spread floor (if we can read the tick)
    spread_pts = 0
    try:
        import MetaTrader5 as mt5
        tick = mt5.symbol_info_tick(config.SYMBOL)
        if tick is not None:
            si = mt5.symbol_info(config.SYMBOL)
            if si is not None and si.point:
                spread_pts = int(round((tick.ask - tick.bid) / si.point))
    except Exception:
        pass

    min_sl = max(config.default_sl_points_for(config.SYMBOL), spread_pts * 2)
    if sl_points < min_sl:
        sl_points = min_sl

    if tp_points < sl_points * 1.5:
        tp_points = int(sl_points * 1.5)

    return sl_points, tp_points


def calculate_consensus(decisions):
    """
    Analyzes decisions from all 3 LLMs and determines if consensus is met.
    The threshold is read from DynamicConfig (self-tuning); falls back to
    config.CONSENSUS_THRESHOLD if dynamic_rules is unavailable.
    decisions: dict of model decisions, e.g.:
      {
        "OpenAI": {"signal": "BUY", "confidence": 0.8, "sl_points": 300, "tp_points": 600, "reasoning": "..."},
        "Gemini": {"signal": "BUY", "confidence": 0.9, "sl_points": 250, "tp_points": 500, "reasoning": "..."},
        "DeepSeek": {"signal": "HOLD", "confidence": 0.0, "sl_points": None, "tp_points": None, "reasoning": "..."}
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
    print("           ANALISIS KONSENSUS MULTI-LLM           ")
    print("="*50)
    
    signals_count = {"BUY": 0, "SELL": 0, "HOLD": 0}
    agreeing_models = []
    
    # Print details for each model
    for model_name, dec in decisions.items():
        sig = dec.get("signal", "HOLD")
        conf = dec.get("confidence", 0.0)
        reason = dec.get("reasoning", "Tidak ada alasan.")
        sl = dec.get("sl_points")
        tp = dec.get("tp_points")
        
        signals_count[sig] += 1
        print(f"🤖 [{model_name}] Decision: {sig} (Conf: {conf*100:.1f}%)")
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
    for model_name, dec in decisions.items():
        pos_actions = dec.get("position_actions", [])
        if isinstance(pos_actions, list):
            for item in pos_actions:
                if isinstance(item, dict) and item.get("action") == "CLOSE":
                    ticket = item.get("ticket")
                    if ticket:
                        if ticket not in close_votes:
                            close_votes[ticket] = []
                        close_votes[ticket].append((model_name, item.get("reason", "Proyeksi sideways/risiko balik arah")))

    tickets_to_close = []
    consensus_threshold = _effective_consensus_threshold()
    for ticket, votes in close_votes.items():
        if len(votes) >= consensus_threshold:
            models_str = ", ".join([v[0] for v in votes])
            reason_sample = votes[0][1]
            tickets_to_close.append({
                "ticket": ticket,
                "models": models_str,
                "reason": reason_sample
            })
            print(f"⚡ [AI RE-EVALUATOR] {len(votes)}/3 AI ({models_str}) sepakat CLOSE order #{ticket}: {reason_sample}")

    for sig in ["BUY", "SELL"]:
        if signals_count[sig] >= consensus_threshold:
            consensus_signal = sig
            # Find models that agreed
            agreeing_models = [name for name, dec in decisions.items() if dec.get("signal") == sig]
            
            # Calculate average SL, TP and Confidence of agreeing models
            sl_list = []
            tp_list = []
            conf_list = []
            
            for name in agreeing_models:
                dec = decisions[name]
                conf_list.append(dec.get("confidence", 0.5))
                
                # Extract SL/TP and handle nulls
                sl_val = dec.get("sl_points")
                if isinstance(sl_val, (int, float)) and sl_val > 0:
                    sl_list.append(sl_val)
                    
                tp_val = dec.get("tp_points")
                if isinstance(tp_val, (int, float)) and tp_val > 0:
                    tp_list.append(tp_val)
                    
            # Averages
            avg_confidence = float(sum(conf_list) / len(conf_list))
            final_sl = int(sum(sl_list) / len(sl_list)) if sl_list else config.default_sl_points_for(config.SYMBOL)
            final_tp = int(sum(tp_list) / len(tp_list)) if tp_list else config.default_tp_points_for(config.SYMBOL)

            # Enforce minimum SL/TP (never inside spread, never absurdly tight)
            final_sl, final_tp = _apply_sltp_floors(final_sl, final_tp)
            
            print(f"🚀 [KONSENSUS DISETUJUI] Sinyal: {consensus_signal}")
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
                "tickets_to_close": tickets_to_close,
                "details": f"Consensus by: {agreeing_models}"
            }
            
    print(f"🚨 [KONSENSUS GAGAL] Tidak memenuhi threshold konsensus ({consensus_threshold} model). Posisi: HOLD.")
    print("=" * 50 + "\n")
    
    return {
        "signal": "HOLD",
        "confidence": 0.0,
        "sl_points": config.default_sl_points_for(config.SYMBOL),
        "tp_points": config.default_tp_points_for(config.SYMBOL),
        "agreeing_count": 0,
        "tickets_to_close": tickets_to_close,
        "details": "Consensus failed"
    }
