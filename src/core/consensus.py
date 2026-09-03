import json
import statistics
import config
from src.core.cli_theme import UI


def _effective_consensus_threshold():
    """Returns the active consensus threshold (from config)."""
    return config.CONSENSUS_THRESHOLD


_last_sltp_adjustments = []


def calculate_2d_confluence_tier(quant_grade: str, decisions: dict, candidate=None) -> dict:
    """
    Computes the 2D Confluence Matrix combining Stage 1 Quant Engine Grade (S, A, B)
    with Stage 2 3-AI Specialized Score:
      Composite Score S = 0.35 * S_OpenAI + 0.35 * S_Gemini + 0.30 * S_DeepSeek
    
    Tiers:
      - APEX_SUPER_CONVICTION (Quant S + AI >= 80%): 1.25x lot (Split 2 tickets), Multi-Day TP2
      - HIGH_CONVICTION (Quant S + AI 70-79% or Quant A + AI >= 80%): 1.00x lot, Standard TP1+TP2
      - STANDARD_TRADE (Quant A + AI 70-79%): 1.00x lot, Standard TP1+BEP
      - REDUCED_SCALP (Quant B or AI 60-69%): 0.50x lot, Tight TP1 Only Scalp (1.0 - 1.25x ATR)
      - SKIP_VETO (Quant B + AI 60-69% or AI < 60% or Any Reject/Veto): 0.0x (HOLD)
    """
    w_openai = 0.35
    w_gemini = 0.35
    w_deepseek = 0.30

    o_dec = decisions.get("OpenAI", {})
    g_dec = decisions.get("Gemini", {})
    d_dec = decisions.get("DeepSeek", {})

    o_conf = float(o_dec.get("confidence", 0.70))
    g_conf = float(g_dec.get("confidence", 0.70))
    d_conf = float(d_dec.get("confidence", 0.70))

    o_verdict = str(o_dec.get("verdict", "PASS")).upper()
    g_verdict = str(g_dec.get("verdict", "PASS")).upper()
    d_verdict = str(d_dec.get("verdict", "APPROVE")).upper()
    d_risk = str(d_dec.get("risk_verdict", "CLEARED")).upper()

    if o_conf > 1.0: o_conf /= 100.0
    if g_conf > 1.0: g_conf /= 100.0
    if d_conf > 1.0: d_conf /= 100.0

    composite_score = (w_openai * o_conf) + (w_gemini * g_conf) + (w_deepseek * d_conf)

    q_grade = str(quant_grade or getattr(candidate, 'setup_grade', None) or getattr(candidate, 'action_tier', 'GRADE_A')).upper()
    is_quant_s = ("GRADE_S" in q_grade or "APEX" in q_grade)
    is_quant_b = ("GRADE_B" in q_grade or "MICRO" in q_grade or "TP1_ONLY" in str(getattr(candidate, 'action_tier', '')))
    is_quant_a = not is_quant_s and not is_quant_b

    has_hard_reject = (o_verdict == "REJECT" or g_verdict == "REJECT" or d_verdict == "REJECT" or d_risk == "HARD_VETO")

    if has_hard_reject or composite_score < 0.60:
        return {
            "tier": "SKIP_VETO",
            "sizing_multiplier": 0.0,
            "composite_score": composite_score,
            "tp_mode": "NONE",
            "is_split_ticket": False,
            "status": "VETO"
        }

    if is_quant_b and composite_score < 0.70:
        return {
            "tier": "SKIP_NOISE",
            "sizing_multiplier": 0.0,
            "composite_score": composite_score,
            "tp_mode": "NONE",
            "is_split_ticket": False,
            "status": "VETO_NOISE"
        }

    if is_quant_s and composite_score >= 0.80 and o_verdict in ("PASS", "APPROVE") and g_verdict in ("PASS", "APPROVE"):
        return {
            "tier": "APEX_SUPER_CONVICTION",
            "sizing_multiplier": 1.25,
            "composite_score": composite_score,
            "tp_mode": "EXTENDED_RUNNER",
            "is_split_ticket": True,
            "status": "EXECUTE"
        }
    elif (is_quant_s and composite_score >= 0.70) or (is_quant_a and composite_score >= 0.80):
        return {
            "tier": "HIGH_CONVICTION",
            "sizing_multiplier": 1.00,
            "composite_score": composite_score,
            "tp_mode": "STANDARD_TP1_TP2",
            "is_split_ticket": False,
            "status": "EXECUTE"
        }
    elif is_quant_a and composite_score >= 0.70:
        return {
            "tier": "STANDARD_TRADE",
            "sizing_multiplier": 1.00,
            "composite_score": composite_score,
            "tp_mode": "STANDARD_TP1_BEP",
            "is_split_ticket": False,
            "status": "EXECUTE"
        }
    else:
        return {
            "tier": "REDUCED_SCALP",
            "sizing_multiplier": 0.50,
            "composite_score": composite_score,
            "tp_mode": "TIGHT_TP1_ONLY",
            "is_split_ticket": False,
            "status": "EXECUTE"
        }


def _apply_sltp_rules(sl_points, tp_points, symbol=None, action_tier=None, setup_grade=None, candidate=None):
    """
    SL/TP final sesuai config.TP_SL_RULES, 5-Tier Action Matrix, dan Setup Quality Grade.
    Returns: (sl_points, tp_points, ok: bool, reason: str)
    """
    global _last_sltp_adjustments
    _last_sltp_adjustments = []

    # ── M4 SYSTEMIC FLOW CONTINUATION: SL/TP STRUKTURAL BEKU (studi #1/#1b mirror) ──
    # SL = M4_SL_ATR_MULT × ATR(H1) dari level (0.45), TP = M4_TP_R_MULT × R (1.1R).
    # Divalidasi studi (scratch/study_surge_retest.py & study_mirror_flow.py) → bypass total
    # floor/ceiling/grade/RR default karena nilai tsb BUKAN thesis LLM, melainkan anchor mekanis.
    # M4: Systemic Flow Continuation (3 Sep 2026)
    # SL = M4_SL_ATR_MULT × ATR(H1) dari level (0.45), TP = M4_TP_R_MULT × R (1.1R).
    # Catatan 3 Sep: M4 kini TIDAK LAGI bypass safety floor total agar tidak membuka
    # SL mikro (misal 29 pts pada EURCHF) yang memicu lot raksasa > 1.0 lot.
    # Nilai M4 di-clamp ke Segmented Safety Floor dan Net R:R (menutup komisi + spread).
    if candidate is not None and getattr(candidate, "setup_type", "") == getattr(config, "M4_SETUP_TYPE", "SYSTEMIC_FLOW_CONTINUATION"):
        _md = getattr(candidate, "metadata", None) or {}
        _m4_sl = int(_md.get("m4_sl_pts") or 0)
        _m4_tp = int(_md.get("m4_tp_pts") or 0)
        if _m4_sl > 0 and _m4_tp > 0:
            sym_m4 = symbol or config.SYMBOL
            min_sl_m4 = config.get_sl_floor_points(sym_m4, spread_pts=0, atr_points=0)
            if _m4_sl < min_sl_m4:
                _last_sltp_adjustments.append(f"M4 SL {_m4_sl} pts < safety floor ({min_sl_m4} pts). Menyesuaikan ke {min_sl_m4} pts.")
                _m4_sl = min_sl_m4
            
            comm_pts = 5
            min_tp_m4 = int(_m4_sl * config.LLM_MIN_RR_RATIO) + comm_pts
            if _m4_tp < min_tp_m4:
                _last_sltp_adjustments.append(f"M4 TP {_m4_tp} pts < Net R:R ({config.LLM_MIN_RR_RATIO}x + {comm_pts} pts comm). Menyesuaikan ke {min_tp_m4} pts.")
                _m4_tp = min_tp_m4

            _last_sltp_adjustments.append(
                f"M4 struktural: SL {_m4_sl} pts, TP {_m4_tp} pts — anchor floored (Net R:R)."
            )
            return _m4_sl, _m4_tp, True, "M4_STRUCTURAL_FLOORED"

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
        is_xau = ("XAU" in sym.upper())
        is_btc = config.is_crypto(sym)
        is_jpy = ("JPY" in sym.upper())

        if is_btc:
            min_sl = max(spread_pts * 2, int(1.20 * atr_points), 30000) if atr_points > 0 else 30000
        elif is_xau:
            min_sl = max(spread_pts * 2, int(config.LLM_SAFETY_FLOOR_ATR_MULT * atr_points)) if atr_points > 0 else config.LLM_SAFETY_FLOOR_STATIC_PTS
        else:
            # Segmented Safety Floors (3 Sep 2026): Low-Beta (120 pts), High-Beta (180 pts), JPY (200 pts / 1.00x ATR)
            min_sl = config.get_sl_floor_points(sym, spread_pts=spread_pts, atr_points=atr_points)
            
        if sl_points < min_sl:
            _last_sltp_adjustments.append(f"SL {sl_points} pts di bawah safety floor ({min_sl} pts). Menyesuaikan SL ke {min_sl} pts.")
            sl_points = min_sl

        # Hard Intraday Ceiling Cap (mencegah SL runaway / swing level)
        # ZCE anchor mode: ceiling = batas VALIDITAS anchor struktural (bukan alat clamp).
        # Jika SL anchor > ceiling -> SKIP ANCHOR_TOO_WIDE (clamp akan memarkir SL di
        # tengah struktur = stop prematur). Hanya aktif saat ZCE supply walls ke MSE
        # (mode legacy/full); saat shadow/off perilaku clamp lama dipertahankan 1:1.
        zce_wall_mode = bool(getattr(config, "ZCE_ENABLED", False)) and str(
            getattr(config, "ZCE_MODE", "shadow")).lower() in ("legacy", "full")
        sl_max_mult = float(getattr(config, "SL_MAX_ATR_MULT", 2.5))

        if is_btc:
            max_sl = min(int(atr_points * 1.80), 45000) if atr_points > 0 else 45000
            if sl_points > max_sl:
                _last_sltp_adjustments.append(f"SL {sl_points} pts melebihi plafon BTC ($450 USD). Menyesuaikan SL ke {max_sl} pts.")
                sl_points = max_sl
        else:
            # Aset non-BTC (FX/JPY/Gold): ceiling berbasis ATR (default SL_MAX_ATR_MULT=2.5x)
            static_fallback = 800 if is_xau else 350
            if atr_points <= 0:
                if zce_wall_mode:
                    note = "ATR_UNAVAILABLE: data ATR MT5 gagal dimuat (mode ZCE anchor). REJECT tanpa fallback statis."
                    _last_sltp_adjustments.append(note)
                    return sl_points, tp_points, False, note
                max_sl = static_fallback
            else:
                max_sl = int(atr_points * sl_max_mult)
            if sl_points > max_sl:
                if zce_wall_mode:
                    note = (f"ANCHOR_TOO_WIDE: SL anchor {sl_points} pts > ceiling {max_sl} pts "
                            f"({sl_max_mult}x ATR). SKIP trade — clamp akan memarkir SL di tengah struktur.")
                    _last_sltp_adjustments.append(note)
                    return sl_points, tp_points, False, note
                label = "Gold" if is_xau else ("JPY" if is_jpy else "FX")
                _last_sltp_adjustments.append(f"SL {sl_points} pts melebihi plafon {label} ({sl_max_mult}x ATR). Menyesuaikan SL ke {max_sl} pts.")
                sl_points = max_sl

        if tp_points <= 0:
            tp_points = config.default_tp_points_for(sym)

        min_rr = config.LLM_MIN_RR_RATIO
        max_rr = getattr(config, "LLM_MAX_RR_RATIO", 3.0)

        # Dynamic Grade-Aware Multipliers
        grade_str = str(setup_grade or "").upper()
        act_str = str(action_tier or "").upper()
        if "GRADE_S" in grade_str:
            max_rr = 3.50
        elif "GRADE_B" in grade_str or "REDUCED_SCALP" in grade_str or "REDUCED_SCALP" in act_str:
            max_rr = 1.25
        elif "GRADE_A_PLUS" in grade_str:
            max_rr = 2.50

        # 5-Tier Action Matrix R:R constraints
        if action_tier in ("TP1_ONLY_SCALP", "REDUCED_SCALP") or "REDUCED_SCALP" in grade_str or "TP1_ONLY" in act_str:
            max_rr = min(max_rr, 1.25)
            min_rr = min(min_rr, 1.00)
        elif action_tier == "REDUCED_CONFIDENCE":
            max_rr = min(max_rr, 2.00)

        # Net R:R Commission & Spread Compensation (3 Sep 2026):
        # Biaya transaksi (Spread + Round-Turn Komisi) dihitung ke dalam target TP minimal
        # agar Net R:R setelah potongan broker tetap murni >= min_rr : 1.
        usd_per_pt_1lot = 0.0
        if si is not None and getattr(si, 'trade_tick_size', 0) and getattr(si, 'point', 0):
            usd_per_pt_1lot = si.trade_tick_value * 1.0 * (si.point / si.trade_tick_size)
        
        comm_usd_round = getattr(config, "COMMISSION_USD_PER_LOT_ROUND", 6.0)
        comm_pts = int(round(comm_usd_round / usd_per_pt_1lot)) if usd_per_pt_1lot > 0 else 5
        friction_pts = spread_pts + comm_pts

        min_tp = int(sl_points * min_rr) + friction_pts
        max_tp = int(sl_points * max_rr) + friction_pts
        if tp_points < min_tp:
            _last_sltp_adjustments.append(f"TP {tp_points} pts < Net R:R ({min_rr}x SL + {friction_pts} pts friksi). Menyesuaikan TP ke {min_tp} pts.")
            tp_points = min_tp
        elif tp_points > max_tp:
            tier_msg = f" [{setup_grade or action_tier} Cap]" if (setup_grade or action_tier) else ""
            
            # Fallback ke Quant Station TP asli jika tersedia dan berada dalam batas wajar
            cand_tp_pts = getattr(candidate, 'suggested_tp_pts', 0) if candidate else 0
            if not cand_tp_pts and candidate and getattr(candidate, 'suggested_tp', 0.0) and getattr(candidate, 'trigger_price', 0.0):
                try:
                    pt_val = si.point if si and si.point else (0.001 if "JPY" in str(sym) else (0.01 if "XAU" in str(sym) or "BTC" in str(sym) else 0.00001))
                    cand_tp_pts = int(round(abs(candidate.suggested_tp - candidate.trigger_price) / pt_val))
                except Exception:
                    cand_tp_pts = 0
            
            if cand_tp_pts > 0 and min_tp <= cand_tp_pts <= int(max_tp * 1.20):
                _last_sltp_adjustments.append(f"TP {tp_points} pts melebihi batas. Fallback ke Quant Station TP ({cand_tp_pts} pts | R:R {cand_tp_pts/sl_points:.2f}:1).")
                tp_points = cand_tp_pts
            else:
                _last_sltp_adjustments.append(f"TP {tp_points} pts > {max_rr}x SL{tier_msg}. Membatasi TP ke {max_tp} pts (R:R {max_rr}:1).")
                tp_points = max_tp

        try:
            account = mt5.account_info() if 'mt5' in dir() else None
            if account is None:
                from config import mt5 as _mt5
                account = _mt5.account_info()
            equity = float(account.equity) if account else 0.0
            si = mt5.symbol_info(sym) if 'mt5' in dir() else None
            if si is None:
                from config import mt5 as _mt5
                si = _mt5.symbol_info(sym)
            vol_min = getattr(si, "volume_min", 0.01) if si else 0.01
            usd_pt = (si.trade_tick_value * (si.point / si.trade_tick_size)) if si and si.trade_tick_size else 0.0
            risk_pct = config.risk_percent_for(sym)
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


def calculate_consensus(decisions, candidate=None):
    box_items = []

    # FIX 29 Agu: ai_mode harus di-set di awal karena dipakai di multiple return paths
    # (HOLD branch + consensus accepted branch). Sebelumnya di-set inline di loop
    # weighted-confidence yang sudah di-drop.
    ai_mode = getattr(config, "get_ai_mode", lambda: "triple")()

    # Simbol aktif: di scanner mode, SEMUA 26 simbol setara (tidak ada default pair).
    # Ambil langsung dari candidate.symbol, fallback ke config.SYMBOL hanya jika None.
    cand_sym = getattr(candidate, 'symbol', None) or config.SYMBOL

    point = 0.00001
    ref_price = 0.0
    try:
        from config import mt5
        si = mt5.symbol_info(cand_sym)
        tick = mt5.symbol_info_tick(cand_sym)
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

    # FIX 29 Agu: Simplified 3-LLM consensus.
    # Rule baru: entry HANYA kalau SEMUA model yang aktif searah (3/3 BUY atau 3/3 SELL).
    # 2/3 atau split → HOLD. Weighted-confidence scoring + threshold 1.2 + min_models di-drop.
    # Hard Risk Veto (di bawah) tetap berlaku sebagai safety override.
    # Avg confidence (line 464) dihitung hanya dari model yang searah (loop di agreeing_models).
    n_decisions = len(decisions)
    buy_voters = [m for m, d in decisions.items() if (d.get("signal") or "HOLD") == "BUY"]
    sell_voters = [m for m, d in decisions.items() if (d.get("signal") or "HOLD") == "SELL"]

    consensus_signal = "HOLD"
    agreeing_models = []
    if buy_voters and len(buy_voters) == n_decisions and n_decisions >= 3:
        consensus_signal = "BUY"
        agreeing_models = buy_voters
    elif sell_voters and len(sell_voters) == n_decisions and n_decisions >= 3:
        consensus_signal = "SELL"
        agreeing_models = sell_voters
    # else: split atau <3 model → HOLD, agreeing_models tetap []

    # Qualified Hard Risk Veto Engine (Preserves Capital against Critical Traps)
    hard_veto_models = []
    VALID_HARD_VETO_FLAGS = (
        "COUNTER_TREND_MOMENTUM", "LIQUIDITY_TRAP", "IMPULSE_CHASE",
        "SYSTEMIC_CURRENCY_DUMP", "HIGH_IMPACT_NEWS", "CURRENCY_CONFLICT", "MACRO_HEADWIND"
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

    # Per-Model Minimum Confidence Floor (60%) — jika ada 1 model < 0.60 → HOLD
    if consensus_signal in ("BUY", "SELL"):
        low_conf_models = [
            (m, float(decisions[m].get("confidence", 0.0)))
            for m in agreeing_models
            if float(decisions[m].get("confidence", 0.0)) < 0.60
        ]
        if low_conf_models:
            names_str = ", ".join([f"{m} ({c*100:.0f}%)" for m, c in low_conf_models])
            box_items.append("---")
            box_items.append(f"{UI.YELLOW}{UI.BOLD}[⚠ CONFIDENCE FLOOR GATE] HOLD — {names_str} di bawah minimum 60%{UI.RST}")
            box_items.append((f"  {UI.DIM}Rule{UI.RST} : ", "Semua model wajib >= 60% confidence. Trade dibatalkan."))
            consensus_signal = "HOLD"
            agreeing_models = []

    if consensus_signal == "HOLD":
        box_items.append("---")
        box_items.append(f"{UI.YELLOW}[*] HASIL: TIDAK ADA KONSENSUS (HOLD){UI.RST}")
        box_items.append((f"  {UI.DIM}Voting:{UI.RST} ", f"BUY={len(buy_voters)}/{n_decisions}, SELL={len(sell_voters)}/{n_decisions} (Rule: perlu 3/3 searah)"))
        print("\n" + UI.make_box("ANALISIS KONSENSUS MULTI-LLM", box_items, width=100, border_color=UI.CYAN) + "\n")

        return {
            "signal": "HOLD",
            "confidence": 0.0,
            "sl_points": config.default_sl_points_for(cand_sym),
            "tp_points": config.default_tp_points_for(cand_sym),
            "agreeing_count": 0,
            "agreeing_models": [],
            "tickets_to_close": tickets_to_close,
            "hold_type": "split_vote" if n_decisions >= 3 else "low_confidence",
            "buy_voters": len(buy_voters),
            "sell_voters": len(sell_voters),
            "decisions": decisions,
            "ai_mode": ai_mode,
            "details": f"3/3 rule failed: BUY={len(buy_voters)}/{n_decisions}, SELL={len(sell_voters)}/{n_decisions}"
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

    # 1. Prioritaskan keputusan eksekusi DeepSeek CRO (Master Arbiter) jika aktif dan setuju
    ds_dec = decisions.get("DeepSeek") or decisions.get("deepseek")
    ds_exec = (ds_dec.get("execution") or {}) if ds_dec else {}
    ds_entry_type = (ds_exec.get("entry_type") or ds_dec.get("entry_type", "")).strip().lower() if ds_dec else ""
    ds_ep = ds_exec.get("entry_price") or (ds_dec.get("entry_price") if ds_dec else None)

    if ds_entry_type in ("buy_limit", "sell_limit", "market", "buy_stop", "sell_stop") and "DeepSeek" in agreeing_models:
        final_entry_type = ds_entry_type
        final_entry_price = float(ds_ep) if (isinstance(ds_ep, (int, float)) and ds_ep > 0) else (float(statistics.median(entry_price_list)) if entry_price_list else None)
    else:
        # entry_type: mayoritas dari model yang setuju arah; seri -> market
        final_entry_type = "market"
        if entry_type_votes:
            top_type, top_count = max(entry_type_votes.items(), key=lambda kv: kv[1])
            if top_count >= max(1, len(agreeing_models) // 2):
                final_entry_type = top_type
        final_entry_price = float(statistics.median(entry_price_list)) if entry_price_list else None

    # 2. Hard Anti-FOMO Intercept: Pada Breakout Retest di Range Ekstrem (>=85% BUY / <=15% SELL), wajib Limit Order di Anchor Retest
    if candidate is not None:
        c_st = getattr(candidate, 'setup_type', '')
        dr_pos = getattr(candidate, 'dealing_range_pos', 0.5)
        c_trig = getattr(candidate, 'trigger_price', 0.0)
        
        if c_st == "MULTI_TOUCH_BREAKOUT_RETEST" or "BREAKOUT" in c_st:
            if consensus_signal == "BUY" and dr_pos >= 0.85 and final_entry_type == "market":
                final_entry_type = "buy_limit"
                final_entry_price = float(c_trig) if (c_trig > 0) else final_entry_price
                outlier_notes.append(f"Anti-FOMO Guard: Breakout di {dr_pos*100:.1f}% Range dikonversi dari Market ke BUY_LIMIT @ {final_entry_price}")
            elif consensus_signal == "SELL" and dr_pos <= 0.15 and final_entry_type == "market":
                final_entry_type = "sell_limit"
                final_entry_price = float(c_trig) if (c_trig > 0) else final_entry_price
                outlier_notes.append(f"Anti-FOMO Guard: Breakdown di {dr_pos*100:.1f}% Range dikonversi dari Market ke SELL_LIMIT @ {final_entry_price}")

    # Konsistensi arah: BUY -> buy_stop/buy_limit, SELL -> sell_stop/sell_limit
    if consensus_signal == "BUY" and final_entry_type not in ("buy_stop", "buy_limit"):
        final_entry_type = "market"
    if consensus_signal == "SELL" and final_entry_type not in ("sell_stop", "sell_limit"):
        final_entry_type = "market"
    if final_entry_type != "market" and not final_entry_price:
        final_entry_type = "market"

    avg_confidence = float(sum(conf_list) / len(conf_list)) if conf_list else 0.0
    
    # ── 2D CONFLUENCE MATRIX EVALUATION (QUANT GRADE × AI COMPOSITE SCORE) ──
    quant_grade = getattr(candidate, 'setup_grade', None) or getattr(candidate, 'action_tier', 'GRADE_A')
    confluence = calculate_2d_confluence_tier(quant_grade, decisions, candidate=candidate)
    
    if confluence.get("status") in ("VETO", "VETO_NOISE"):
        box_items.append("---")
        box_items.append(f"{UI.RED}[⛔ 2D CONFLUENCE VETO] Trade {consensus_signal} Dibatalkan: {confluence.get('tier')} (Score: {confluence.get('composite_score', 0.0)*100:.1f}%){UI.RST}")
        print("\n" + UI.make_box("ANALISIS KONSENSUS MULTI-LLM", box_items, width=100, border_color=UI.CYAN) + "\n")
        return {
            "signal": "HOLD",
            "confidence": confluence.get("composite_score", 0.0),
            "sl_points": config.default_sl_points_for(cand_sym),
            "tp_points": config.default_tp_points_for(cand_sym),
            "agreeing_count": len(agreeing_models),
            "agreeing_models": list(agreeing_models),
            "tickets_to_close": tickets_to_close,
            "hold_type": "confluence_veto",
            "confluence_tier": confluence.get("tier"),
            "decisions": decisions,
            "ai_mode": ai_mode,
            "details": f"2D Confluence VETO ({confluence.get('tier')})"
        }

    avg_confidence = confluence.get("composite_score", avg_confidence)
    final_inv = statistics.median(inv_list) if inv_list else None
    final_tgt = statistics.median(tgt_list) if tgt_list else None

    # ── BOUNDED MICRO-PRECISION REFINEMENT (QUANT ANCHOR + LLM M5/M15 MICRO-TWEAK) ──
    cand_sym = getattr(candidate, 'symbol', config.SYMBOL)
    cand_pip_div = 10 if ("JPY" in cand_sym or point < 0.001) else 1
    if candidate and getattr(candidate, 'suggested_sl', 0.0) and getattr(candidate, 'suggested_tp', 0.0):
        prop_sl = float(candidate.suggested_sl)
        prop_tp = float(candidate.suggested_tp)
        cand_atr_pts = float(getattr(candidate, 'current_atr_pts', 0.0) or 0.0)
        atr_p = (cand_atr_pts * point) if cand_atr_pts > 0 else (15 * point * cand_pip_div)
        micro_bound = max(0.25 * atr_p, 30 * point) # e.g. ~3 to 5 pips

        # 1. Invalidation / SL Validation
        if final_inv is not None and abs(final_inv - prop_sl) <= micro_bound:
            # LLM refined within allowed micro bound -> ACCEPTED
            diff_pts = abs(final_inv - prop_sl) / point if point > 0 else 0
            outlier_notes.append(f"SL Micro-Refined by LLM M5/M15 wicks: {prop_sl} -> {final_inv} (Δ {diff_pts:.1f} pts)")
        else:
            if final_inv is not None:
                outlier_notes.append(f"LLM SL ({final_inv}) deviated > {micro_bound/point:.0f} pts from Quant Anchor ({prop_sl}) -> Clamped to Quant Anchor")
            final_inv = prop_sl

        # 2. Target / TP Validation (Permits structural expansion into FVG / Key Stations within 1.25x - 3.0x RR)
        tp_micro_bound = max(micro_bound * 1.5, 0.65 * atr_p)
        is_valid_dir_tp = (consensus_signal == "BUY" and final_tgt > ref_price) or (consensus_signal == "SELL" and final_tgt < ref_price) if (final_tgt and ref_price) else False
        curr_cand_risk = abs(ref_price - final_inv) if (ref_price and final_inv) else 0.0
        llm_rr = (abs(final_tgt - ref_price) / curr_cand_risk) if (curr_cand_risk > 0 and final_tgt and ref_price) else 0.0

        if final_tgt is not None and is_valid_dir_tp and (abs(final_tgt - prop_tp) <= tp_micro_bound or (1.25 <= llm_rr <= 3.0)):
            diff_tp_pts = abs(final_tgt - prop_tp) / point if point > 0 else 0
            outlier_notes.append(f"TP Refined to Structural Station/FVG: {prop_tp} -> {final_tgt} (Δ {diff_tp_pts:.1f} pts, R:R {llm_rr:.2f}:1)")
        else:
            if final_tgt is not None:
                outlier_notes.append(f"LLM TP ({final_tgt}) deviated > Quant Anchor ({prop_tp}) -> Clamped to Quant Anchor")
            final_tgt = prop_tp

        # Recalculate precise points from validated price coordinates
        base_calc_p = final_entry_price if (final_entry_type != "market" and final_entry_price) else ref_price
        if base_calc_p > 0 and point > 0:
            final_sl = int(round(abs(base_calc_p - final_inv) / point))
            final_tp = int(round(abs(final_tgt - base_calc_p) / point))
        else:
            final_sl = int(round(statistics.median(sl_list))) if sl_list else config.default_sl_points_for(cand_sym)
            final_tp = int(round(statistics.median(tp_list))) if tp_list else config.default_tp_points_for(cand_sym)
    else:
        final_sl = int(round(statistics.median(sl_list))) if sl_list else config.default_sl_points_for(cand_sym)
        final_tp = int(round(statistics.median(tp_list))) if tp_list else config.default_tp_points_for(cand_sym)

    final_sl, final_tp, sltp_ok, sltp_reason = _apply_sltp_rules(
        final_sl, final_tp,
        symbol=cand_sym,
        action_tier=getattr(candidate, 'action_tier', None),
        setup_grade=getattr(candidate, 'setup_grade', None),
        candidate=candidate
    )

    # ── M4: anchor limit sudah terlewati market → BATAL (no market conversion; jangan fade struktur jebol) ──
    _m4_anchor_broken = False
    _m4_anchor_reason = ""
    if candidate is not None and getattr(candidate, "setup_type", "") == getattr(config, "M4_SETUP_TYPE", "SYSTEMIC_FLOW_CONTINUATION"):
        try:
            from config import mt5
            tick = mt5.symbol_info_tick(cand_sym)
            si = mt5.symbol_info(cand_sym)
            point = si.point if si else 0.00001
            if tick and si and point and consensus_signal in ("BUY", "SELL") and final_entry_type != "market" and final_entry_price:
                ref_price = tick.ask if consensus_signal == "BUY" else tick.bid
                if (consensus_signal == "BUY" and final_entry_price >= ref_price) or \
                   (consensus_signal == "SELL" and final_entry_price <= ref_price):
                    _m4_anchor_broken = True
                    _m4_anchor_reason = (f"M4 anchor limit {final_entry_price} vs market {ref_price:.5f}: "
                                         f"harga sudah menembus anchor -> setup batal (no chase).")
        except Exception:
            pass

    # Guardrail entry pending (Filosofi: Percayakan pada LLM, No Trade is Better)
    if not _m4_anchor_broken and final_entry_type != "market" and final_entry_price is not None:
        try:
            from config import mt5
            tick = mt5.symbol_info_tick(cand_sym)
            si = mt5.symbol_info(cand_sym)
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

    if _m4_anchor_broken and sltp_ok:
        sltp_ok = False
        sltp_reason = _m4_anchor_reason

    try:
        from config import mt5
        tick = mt5.symbol_info_tick(cand_sym)
        si = mt5.symbol_info(cand_sym)
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
    box_items.append(f"{UI.GREEN}[+] KONSENSUS DISETUJUI:{UI.RST} {badge} {UI.BOLD}(3/3 rule: {len(agreeing_models)}/{n_decisions} model searah){UI.RST}")
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
        "confluence_tier": confluence.get("tier", "STANDARD_TRADE"),
        "sizing_multiplier": confluence.get("sizing_multiplier", 1.0),
        "is_split_ticket": confluence.get("is_split_ticket", False),
        "tp_mode": confluence.get("tp_mode", "STANDARD_TP1_TP2"),
        "composite_score": avg_confidence,
        "setup": best_setup,
        "state": best_state,
        "reason": best_reason,
        "invalidation_text": best_invalidation,
        "tickets_to_close": tickets_to_close,
        "details": f"Consensus by: {agreeing_models} [{confluence.get('tier')}]"
    }
