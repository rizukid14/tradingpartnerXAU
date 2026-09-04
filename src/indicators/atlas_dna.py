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


def calculate_intraday_sl_tp(symbol: str, entry_price: float, direction: int, 
                             origin_level: float, atr_h1: float, pwl: float = None, pwh: float = None,
                             rbs: float = None, sbr: float = None, spread_pts: float = 0.0,
                             c1: float = None, f1: float = None,
                             c2: float = None, f2: float = None,
                             c1_grade: str = None, f1_grade: str = None,
                             c1_is_vacuum: bool = False, f1_is_vacuum: bool = False) -> dict:
    """
    Calculates precise intraday Stop Loss and Take Profit anchored to Physical Stations:
    1. Primary Target Station: Next Structural Barrier (C1 for BUY, F1 for SELL if >= 1.25R and significant)
    2. Deep Target Station: Next Strong Barrier (C2 for BUY, F2 for SELL if C1/F1 too close or vacuum)
    3. Structural SBR/RBS
    4. Psychological Price (50-pip Sub-Station / 100-pip Big Round Number)
    - Front-running pad: [Spread + 0.15x ATR] deducted from target station
    - Realistic Intraday R:R: Min 1.25:1 to Max 2.5:1
    """
    step = get_symbol_step(symbol)
    sub_step = step * 0.50 # 50-pip Sub-Station
    digits = 2 if 'XAU' in symbol else (3 if 'JPY' in symbol else 5)
    stations = calculate_dynamic_stations(symbol, entry_price)
    
    pt = 0.001 if 'JPY' in symbol else (0.01 if 'XAU' in symbol or 'BTC' in symbol else 0.00001)
    max_sl_dist = 2.5 * atr_h1 if atr_h1 > 0 else (160 * pt)
    front_pad = (0.15 * atr_h1) + (spread_pts * pt)
    # Segmented Minimum SL Buffer (3 Sep 2026):
    # JPY: 200 pts, High-Beta: 180 pts, Quiet/Standard FX: 120 pts
    is_jpy = 'JPY' in symbol
    is_high_beta = any(k in symbol for k in ('GBPAUD', 'GBPNZD', 'EURNZD', 'GBPCHF'))
    min_sl_buffer = (200 * pt) if is_jpy else ((180 * pt) if is_high_beta else (120 * pt))
    sl_buffer = max(0.55 * atr_h1, min_sl_buffer)
    
    # Friction padding for Net R:R (Spread + ~5 pts Commission)
    comm_pts = 5
    friction_pad = (spread_pts + comm_pts) * pt
    
    if direction == 1: # BUY
        # SL behind support origin level / RBS with calibrated buffer
        sl_anchor = origin_level if origin_level and origin_level < entry_price else (
            rbs if rbs and rbs < entry_price else (entry_price - 1.2 * atr_h1)
        )
        sl = sl_anchor - sl_buffer
        
        # Apply Safety Ceiling
        if (entry_price - sl) > max_sl_dist:
            sl = entry_price - max_sl_dist
        risk = max(abs(entry_price - sl), 0.55 * atr_h1 if atr_h1 > 0 else min_sl_buffer)
        
        # TARGET HIERARCHY: 1. Next Structure C1 -> 2. Deep Ceiling C2 -> 3. SBR Ceiling -> 4. Psychological Sub-Station
        target_station = None
        c1_valid = bool(c1 and c1 > entry_price + 1.25 * risk and (c1 - entry_price) <= 3.5 * risk)
        c1_thick = bool(c1_grade in ("GRADE_2_INTERMEDIATE", "GRADE_3_MACRO") and not c1_is_vacuum) if c1_grade else True
        if c1_valid and c1_thick:
            target_station = c1
        elif c2 and c2 > entry_price + 1.25 * risk and (c2 - entry_price) <= 3.5 * risk:
            target_station = c2
        elif sbr and sbr > entry_price + 1.15 * risk and (sbr - entry_price) <= 3.5 * risk:
            target_station = sbr
        elif pwh and pwl and pwh > pwl:
            weekly_50 = pwl + 0.50 * (pwh - pwl)
            if weekly_50 > entry_price + 1.15 * risk and (weekly_50 - entry_price) <= 3.5 * risk:
                target_station = weekly_50
                
        if target_station is None:
            # Nearest 50-pip Psychological Sub-Station
            nearest_psych = round((entry_price + 1.35 * risk) / sub_step) * sub_step
            if nearest_psych <= entry_price + 1.15 * risk:
                nearest_psych = round((entry_price + 1.80 * risk) / sub_step) * sub_step
            target_station = nearest_psych
            
        tp_target = target_station - front_pad
        # Enforce realistic intraday clamp with Net R:R friction compensation
        min_tp = entry_price + (1.25 * risk) + friction_pad
        max_tp = entry_price + max(2.50 * risk, min(1.80 * atr_h1, 40 * pt * 10)) + friction_pad
        tp = max(min_tp, min(tp_target, max_tp))
            
    else: # SELL
        # SL behind resistance origin level / SBR with calibrated buffer
        sl_anchor = origin_level if origin_level and origin_level > entry_price else (
            sbr if sbr and sbr > entry_price else (entry_price + 1.2 * atr_h1)
        )
        sl = sl_anchor + sl_buffer
        
        # Apply Safety Ceiling
        if (sl - entry_price) > max_sl_dist:
            sl = entry_price + max_sl_dist
        risk = max(abs(sl - entry_price), 0.55 * atr_h1 if atr_h1 > 0 else min_sl_buffer)
        
        # TARGET HIERARCHY: 1. Next Structure F1 -> 2. Deep Floor F2 -> 3. RBS Floor -> 4. Psychological Sub-Station
        target_station = None
        f1_valid = bool(f1 and f1 < entry_price - 1.25 * risk and (entry_price - f1) <= 3.5 * risk)
        f1_thick = bool(f1_grade in ("GRADE_2_INTERMEDIATE", "GRADE_3_MACRO") and not f1_is_vacuum) if f1_grade else True
        if f1_valid and f1_thick:
            target_station = f1
        elif f2 and f2 < entry_price - 1.25 * risk and (entry_price - f2) <= 3.5 * risk:
            target_station = f2
        elif rbs and rbs < entry_price - 1.15 * risk and (entry_price - rbs) <= 3.5 * risk:
            target_station = rbs
        elif pwh and pwl and pwh > pwl:
            weekly_50 = pwl + 0.50 * (pwh - pwl)
            if weekly_50 < entry_price - 1.15 * risk and (entry_price - weekly_50) <= 3.5 * risk:
                target_station = weekly_50
                
        if target_station is None:
            # Nearest 50-pip Psychological Sub-Station
            nearest_psych = round((entry_price - 1.35 * risk) / sub_step) * sub_step
            if nearest_psych >= entry_price - 1.15 * risk:
                nearest_psych = round((entry_price - 1.80 * risk) / sub_step) * sub_step
            target_station = nearest_psych
            
        tp_target = target_station + front_pad
        # Enforce realistic intraday clamp with Net R:R friction compensation
        min_tp = entry_price - (1.25 * risk) - friction_pad
        max_tp = entry_price - max(2.50 * risk, min(1.80 * atr_h1, 40 * pt * 10)) - friction_pad
        tp = min(min_tp, max(tp_target, max_tp))
            
    rr = abs(tp - entry_price) / max(risk, 1e-5)
    
    return {
        "sl": round(sl, digits),
        "tp": round(tp, digits),
        "risk": risk,
        "risk_reward": round(rr, 2),
        "target_station": round(target_station, digits)
    }
