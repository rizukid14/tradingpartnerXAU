"""
Master Atlas DNA & Dynamic Station Calculator.
Contains calibrated step sizes, multi-timeframe baseline anchors, and dynamic station target helpers.
"""

# Symbol-specific step size DNA calibrated from 16.2-year MetaQuotes dataset
# Source: docs/research/MASTER_ATLAS_DNA_AND_DUAL_REACTION_REPORT.md (29 Simbol)
# These are PSYCHOLOGICAL PRICE levels — the big round numbers where institutional
# orders cluster (e.g., 1.3400, 1.3500, 1.3600 for GBPUSD).
# NOT the micro-estafet intraday sub-steps from the backtest.
ATLAS_STEP_DNA = {
    # Bitcoin ($1,000 psychological levels: $78k, $79k, $80k)
    'BTCUSD': 1000.0,
    
    # Gold ($50 psychological levels: $4400, $4450, $4500, $4550)
    'XAUUSD': 50.0,
    
    # Core JPY Pairs (100 pips = 1.00 JPY: 158, 159, 160 / 200 pips for High-ADR)
    'USDJPY': 1.000,
    'EURJPY': 1.000,
    'CADJPY': 1.000,
    'AUDJPY': 1.000,
    'NZDJPY': 1.000,
    'GBPJPY': 2.000,
    'CHFJPY': 2.000,
    
    # FX Majors — 100 pips (0.0100) psychological levels (1.3400, 1.3500, 1.3600)
    'EURUSD': 0.0100,
    'GBPUSD': 0.0100,
    'USDCAD': 0.0100,
    'USDCHF': 0.0100,
    
    # AUD/NZD vs USD — 50 pips (0.0050) psychological levels (0.6550, 0.6600, 0.6650)
    'AUDUSD': 0.0050,
    'NZDUSD': 0.0050,
    
    # Medium-ADR FX Crosses (50 pips)
    'AUDNZD': 0.0050,
    'EURAUD': 0.0050,
    'GBPCAD': 0.0050,
    
    # High-ADR FX Crosses (200 pips / 100 pips)
    'GBPAUD': 0.0200,
    'GBPNZD': 0.0100,
    'EURNZD': 0.0100,
    
    # Medium crosses with strong psych levels (50 pips)
    'GBPCHF': 0.0050,
    'EURCAD': 0.0050,
    
    # Low-ADR & Pacific Crosses (25 pips — tight range, finer psych grid)
    'NZDCAD': 0.0025,
    'AUDCAD': 0.0025,
    'EURGBP': 0.0025,
    'AUDCHF': 0.0025,
    'CADCHF': 0.0025,
    'NZDCHF': 0.0025,
    'EURCHF': 0.0025,
}



def get_symbol_step(symbol: str) -> float:
    """
    Returns the calibrated step size for the given symbol.
    Handles broker symbol suffixes like -ECNc, -ECN, .c, etc.
    """
    clean_sym = symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("_SB", "").upper()
    return ATLAS_STEP_DNA.get(clean_sym, 0.0100)


def calculate_dynamic_stations(symbol: str, current_price: float) -> dict:
    """
    Calculates the immediate upper, current base, and lower dynamic stations
    around the live price based on the symbol's step size DNA.
    """
    step = get_symbol_step(symbol)
    digits = 2 if 'XAU' in symbol else (3 if 'JPY' in symbol else 5)
    base_station = round(round(current_price / step) * step, digits)
    upper_station = round(base_station + step, digits)
    lower_station = round(base_station - step, digits)
    
    return {
        "step": step,
        "base_station": base_station,
        "upper_station": upper_station,
        "lower_station": lower_station
    }


def calculate_dual_grid_stations(symbol: str, current_price: float) -> dict:
    """
    Calculates both Macro (100-pip / step) and Micro Sub-Stations (50-pip / half-step)
    for intraday estafet corridor delivery.
    """
    macro_stations = calculate_dynamic_stations(symbol, current_price)
    digits = 2 if 'XAU' in symbol else (3 if 'JPY' in symbol else 5)
    
    # Micro Sub-Station Step (50 pips for JPY/FX, $25 for Gold)
    micro_step = 0.500 if 'JPY' in symbol else (25.0 if 'XAU' in symbol else 0.0050)
    micro_base = round(round(current_price / micro_step) * micro_step, digits)
    
    if current_price >= micro_base:
        sub_floor = micro_base
        sub_ceiling = round(micro_base + micro_step, digits)
    else:
        sub_floor = round(micro_base - micro_step, digits)
        sub_ceiling = micro_base
        
    return {
        "macro_floor": macro_stations["lower_station"],
        "macro_base": macro_stations["base_station"],
        "macro_ceiling": macro_stations["upper_station"],
        "macro_step": macro_stations["step"],
        "sub_floor_50": sub_floor,
        "sub_ceiling_50": sub_ceiling,
        "micro_step_50": micro_step
    }


try:
    import config
    GRADE_S_MIN_RR = getattr(config, "GRADE_S_MIN_RR", 2.50)
    GRADE_A_PLUS_MIN_RR = getattr(config, "GRADE_A_PLUS_MIN_RR", 1.80)
    GRADE_A_MIN_RR = getattr(config, "GRADE_A_MIN_RR", 1.25)
    GRADE_B_MIN_RR = getattr(config, "GRADE_B_MIN_RR", 0.75)
    GRADE_S_MAX_RR = getattr(config, "GRADE_S_MAX_RR", 3.50)
except Exception:
    GRADE_S_MIN_RR = 2.50
    GRADE_A_PLUS_MIN_RR = 1.80
    GRADE_A_MIN_RR = 1.25
    GRADE_B_MIN_RR = 0.75
    GRADE_S_MAX_RR = 3.50


def calculate_intraday_sl_tp(symbol: str, entry_price: float, direction: int, 
                             origin_level: float, atr_h1: float, pwl: float = None, pwh: float = None,
                             rbs: float = None, sbr: float = None, spread_pts: float = 0.0,
                             c1: float = None, f1: float = None,
                             c2: float = None, f2: float = None,
                             c1_grade: str = None, f1_grade: str = None,
                             c1_is_vacuum: bool = False, f1_is_vacuum: bool = False,
                             c1_breached: bool = False, f1_breached: bool = False) -> dict:
    """
    Calculates precise intraday Stop Loss and Take Profit anchored to Physical Stations:
    1. Primary Target Station: Next Structural Barrier (C1 for BUY, F1 for SELL if >= 0.75R + friction)
    2. Deep Target Station: Next Strong Barrier (C2 for BUY, F2 for SELL only if C1/F1 legitimately breached or vacuum)
    3. Structural SBR/RBS
    4. Psychological Price (50-pip Sub-Station / 100-pip Big Round Number)
    - Front-running pad: [Spread + 0.15x ATR] deducted from target station
    - Realistic Intraday R:R: Min 0.75:1 (Grade B Wall Scalp) to Max 3.5:1 (Grade S Super-Shock)
    - Rigid Breached Wall Law: C2/F2 can ONLY be targeted if C1/F1 was legitimately breached with H1 close confirmation.
    """
    step = get_symbol_step(symbol)
    sub_step = step * 0.50 # 50-pip Sub-Station
    digits = 2 if 'XAU' in symbol else (3 if 'JPY' in symbol else 5)
    stations = calculate_dynamic_stations(symbol, entry_price)
    
    pt = 0.001 if 'JPY' in symbol else (0.01 if 'XAU' in symbol or 'BTC' in symbol else 0.00001)
    is_jpy = 'JPY' in symbol
    is_high_beta = any(k in symbol for k in ('GBPAUD', 'GBPNZD', 'EURNZD', 'GBPCHF'))
    # Segmented Minimum SL Floor (8 Sep 2026 Dynamic Floor):
    # JPY: 250 pts, High-Beta: 180 pts, Quiet/Standard FX: 80 pts (+20 pts NZD padding)
    min_sl_floor = (250 * pt) if is_jpy else ((180 * pt) if is_high_beta else (80 * pt))
    if 'NZD' in symbol:
        min_sl_floor += (20 * pt)
    min_sl_buffer = (200 * pt) if is_jpy else ((180 * pt) if is_high_beta else (120 * pt))
    sl_buffer = max(0.55 * atr_h1, min_sl_buffer)
    max_sl_dist = max(getattr(config, "SL_MAX_ATR_MULT", 2.5) * atr_h1, 1.5 * atr_h1) if atr_h1 > 0 else (160 * pt)
    front_pad = (0.15 * atr_h1) + (spread_pts * pt)
    wall_cushion = max(15 * pt, 0.15 * atr_h1) + (spread_pts * pt)
    
    # Friction padding for Net R:R (Spread + ~5 pts Commission)
    comm_pts = 5
    friction_pad = (spread_pts + comm_pts) * pt
    
    if direction == 1: # BUY
        # --- PILAR 4: BALANCED 3-TERM SL FORMULA (11 Sep 2026) ---
        invalidation_buffer = max(0.15 * atr_h1, (2 * spread_pts + 10) * pt)
        origin = origin_level if (origin_level is not None and origin_level > 0) else (f1 if (f1 is not None and f1 > 0) else (rbs if (rbs is not None and rbs > 0) else entry_price))
        struct_dist = abs(entry_price - origin) + invalidation_buffer

        atr_floor = getattr(config, "SL_ATR_MULT", 1.00) * atr_h1 if atr_h1 > 0 else (100 * pt)
        if hasattr(config, "friction_floor_points"):
            fric_floor = config.friction_floor_points(int(spread_pts)) * pt
        else:
            fric_floor = int(round((spread_pts + 6) / 0.20)) * pt

        sl_dist = max(struct_dist, atr_floor, fric_floor)
        if max_sl_dist and max_sl_dist > 0:
            sl_dist = min(sl_dist, max_sl_dist)

        sl = entry_price - sl_dist
        risk = sl_dist
        
        # TARGET HIERARCHY: 1. Next Structure C1 -> 2. Deep Ceiling C2 -> 3. SBR Ceiling -> 4. Psychological Sub-Station
        target_station = None
        min_wall_dist = (GRADE_B_MIN_RR * risk) + friction_pad
        c1_thick = bool(c1_grade in ("GRADE_2_INTERMEDIATE", "GRADE_3_MACRO") and not c1_is_vacuum) if c1_grade else True
        
        # Rigid Breached Wall Law:
        # C2/SBR can ONLY be targeted if C1 was legitimately breached or flimsy (GRADE_1_MICRO) or vacuum
        can_advance_to_c2 = c1_breached or not c1_thick or c1_is_vacuum
        if c1 and c1 > entry_price:
            if not can_advance_to_c2 and (c1 - entry_price) >= min_wall_dist:
                target_station = c1
            elif can_advance_to_c2:
                if c2 and c2 > entry_price + GRADE_A_MIN_RR * risk:
                    target_station = c2
                elif sbr and sbr > entry_price + 1.15 * risk:
                    target_station = sbr
                elif pwh and pwl and pwh > pwl:
                    weekly_50 = pwl + 0.50 * (pwh - pwl)
                    if weekly_50 > entry_price + 1.15 * risk:
                        target_station = weekly_50
                else:
                    target_station = c2 if c2 else c1
        elif c2 and c2 > entry_price + GRADE_A_MIN_RR * risk:
            target_station = c2
        elif sbr and sbr > entry_price + 1.15 * risk:
            target_station = sbr
        elif pwh and pwl and pwh > pwl:
            weekly_50 = pwl + 0.50 * (pwh - pwl)
            if weekly_50 > entry_price + 1.15 * risk:
                target_station = weekly_50
                
        if target_station is None:
            # Nearest 50-pip Psychological Sub-Station
            nearest_psych = round((entry_price + 1.35 * risk) / sub_step) * sub_step
            if nearest_psych <= entry_price + 1.15 * risk:
                nearest_psych = round((entry_price + 1.80 * risk) / sub_step) * sub_step
            target_station = nearest_psych
            
        tp_target = target_station - front_pad
        is_wall_scalp = bool(target_station and c1 and abs(target_station - c1) < 1e-5 and (c1 - entry_price) < (GRADE_A_MIN_RR * risk + friction_pad))
        min_tp = entry_price + (min_wall_dist if is_wall_scalp else (GRADE_A_MIN_RR * risk + friction_pad))
        max_tp = entry_price + (GRADE_S_MAX_RR * risk) + friction_pad
        if target_station and c1 and abs(target_station - c1) < 1e-5:
            # Wall Target C1: TP must not overshoot C1
            tp = min(max(tp_target, min_tp), c1)
        else:
            tp = max(min_tp, min(tp_target, max_tp))
            
    else: # SELL
        # --- PILAR 4: BALANCED 3-TERM SL FORMULA (11 Sep 2026) ---
        invalidation_buffer = max(0.15 * atr_h1, (2 * spread_pts + 10) * pt)
        origin = origin_level if (origin_level is not None and origin_level > 0) else (c1 if (c1 is not None and c1 > 0) else (sbr if (sbr is not None and sbr > 0) else entry_price))
        struct_dist = abs(entry_price - origin) + invalidation_buffer

        atr_floor = getattr(config, "SL_ATR_MULT", 1.00) * atr_h1 if atr_h1 > 0 else (100 * pt)
        if hasattr(config, "friction_floor_points"):
            fric_floor = config.friction_floor_points(int(spread_pts)) * pt
        else:
            fric_floor = int(round((spread_pts + 6) / 0.20)) * pt

        sl_dist = max(struct_dist, atr_floor, fric_floor)
        if max_sl_dist and max_sl_dist > 0:
            sl_dist = min(sl_dist, max_sl_dist)

        sl = entry_price + sl_dist
        risk = sl_dist
        
        # TARGET HIERARCHY: 1. Next Structure F1 -> 2. Deep Floor F2 -> 3. RBS Floor -> 4. Psychological Sub-Station
        target_station = None
        min_wall_dist = (GRADE_B_MIN_RR * risk) + friction_pad
        f1_thick = bool(f1_grade in ("GRADE_2_INTERMEDIATE", "GRADE_3_MACRO") and not f1_is_vacuum) if f1_grade else True
        
        # Rigid Breached Wall Law:
        # F2/RBS can ONLY be targeted if F1 was legitimately breached or flimsy (GRADE_1_MICRO) or vacuum
        can_advance_to_f2 = f1_breached or not f1_thick or f1_is_vacuum
        if f1 and f1 < entry_price:
            if not can_advance_to_f2 and (entry_price - f1) >= min_wall_dist:
                target_station = f1
            elif can_advance_to_f2:
                if f2 and f2 < entry_price - GRADE_A_MIN_RR * risk:
                    target_station = f2
                elif rbs and rbs < entry_price - 1.15 * risk:
                    target_station = rbs
                elif pwh and pwl and pwh > pwl:
                    weekly_50 = pwl + 0.50 * (pwh - pwl)
                    if weekly_50 < entry_price - 1.15 * risk:
                        target_station = weekly_50
                else:
                    target_station = f2 if f2 else f1
        elif f2 and f2 < entry_price - GRADE_A_MIN_RR * risk:
            target_station = f2
        elif rbs and rbs < entry_price - 1.15 * risk:
            target_station = rbs
        elif pwh and pwl and pwh > pwl:
            weekly_50 = pwl + 0.50 * (pwh - pwl)
            if weekly_50 < entry_price - 1.15 * risk:
                target_station = weekly_50
                
        if target_station is None:
            # Nearest 50-pip Psychological Sub-Station
            nearest_psych = round((entry_price - 1.35 * risk) / sub_step) * sub_step
            if nearest_psych >= entry_price - 1.15 * risk:
                nearest_psych = round((entry_price - 1.80 * risk) / sub_step) * sub_step
            target_station = nearest_psych
            
        tp_target = target_station + front_pad
        is_wall_scalp = bool(target_station and f1 and abs(target_station - f1) < 1e-5 and (entry_price - f1) < (GRADE_A_MIN_RR * risk + friction_pad))
        min_tp = entry_price - (min_wall_dist if is_wall_scalp else (GRADE_A_MIN_RR * risk + friction_pad))
        max_tp = entry_price - (GRADE_S_MAX_RR * risk) - friction_pad
        if target_station and f1 and abs(target_station - f1) < 1e-5:
            # Wall Target F1: TP must not overshoot F1 downwards
            tp = max(min(tp_target, min_tp), f1)
        else:
            tp = min(min_tp, max(tp_target, max_tp))
            
    rr = abs(tp - entry_price) / max(risk, 1e-5)
    if rr >= GRADE_S_MIN_RR:
        setup_grade = "GRADE_S"
    elif rr >= GRADE_A_PLUS_MIN_RR:
        setup_grade = "GRADE_A_PLUS"
    elif rr >= GRADE_A_MIN_RR and not is_wall_scalp:
        setup_grade = "GRADE_A"
    elif rr >= 0.50:
        setup_grade = "GRADE_B"
    else:
        setup_grade = "INVALID_RR"
    
    return {
        "sl": round(sl, digits),
        "tp": round(tp, digits),
        "risk": risk,
        "risk_reward": round(rr, 2),
        "target_station": round(target_station, digits),
        "setup_grade": setup_grade,
        "is_wall_scalp": is_wall_scalp,
        "invalidation_dist": round(struct_dist, digits),
        "sl_dist_points": int(round(sl_dist / pt))
    }
