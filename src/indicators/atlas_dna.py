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
                             origin_level: float, atr_h1: float, pwl: float = None, pwh: float = None) -> dict:
    """
    Calculates precise intraday Stop Loss and Take Profit:
    - SL: Anchored behind origin level + Anti-Wick Buffer (0.35x ATR H1) capped by Safety Ceiling
    - TP: Target at immediate next sub-station / station with minimum R:R >= 1.25:1
    """
    step = get_symbol_step(symbol)
    digits = 2 if 'XAU' in symbol else (3 if 'JPY' in symbol else 5)
    stations = calculate_dynamic_stations(symbol, entry_price)
    
    # Maximum SL Safety Ceiling (160 pts FX, 2.5x ATR Gold)
    pt = 0.001 if 'JPY' in symbol else (0.01 if 'XAU' in symbol or 'BTC' in symbol else 0.00001)
    max_sl_dist = min(2.0 * atr_h1, 160 * pt) if 'XAU' not in symbol else (2.5 * atr_h1)
    
    if direction == 1: # BUY
        # SL behind support origin level
        sl_anchor = origin_level if origin_level and origin_level < entry_price else (entry_price - 1.2 * atr_h1)
        sl = sl_anchor - (0.35 * atr_h1)
        
        # Apply Safety Ceiling
        if (entry_price - sl) > max_sl_dist:
            sl = entry_price - max_sl_dist
        risk = max(abs(entry_price - sl), 0.5 * atr_h1)
        
        # Candidate TP: Next upper station or 50% weekly equilibrium
        target_station = stations["upper_station"] if stations["upper_station"] > entry_price else (entry_price + step)
        if pwh and pwl and pwh > pwl:
            weekly_50 = pwl + 0.50 * (pwh - pwl)
            if weekly_50 > entry_price and abs(weekly_50 - entry_price) >= 1.25 * risk:
                target_station = weekly_50
                
        tp_dist = max(risk * 1.5, abs(target_station - entry_price))
        tp = entry_price + tp_dist
            
    else: # SELL
        # SL behind resistance origin level
        sl_anchor = origin_level if origin_level and origin_level > entry_price else (entry_price + 1.2 * atr_h1)
        sl = sl_anchor + (0.35 * atr_h1)
        
        # Apply Safety Ceiling
        if (sl - entry_price) > max_sl_dist:
            sl = entry_price + max_sl_dist
        risk = max(abs(sl - entry_price), 0.5 * atr_h1)
        
        # Candidate TP: Next lower station or 50% weekly equilibrium
        target_station = stations["lower_station"] if stations["lower_station"] < entry_price else (entry_price - step)
        if pwh and pwl and pwh > pwl:
            weekly_50 = pwl + 0.50 * (pwh - pwl)
            if weekly_50 < entry_price and abs(entry_price - weekly_50) >= 1.25 * risk:
                target_station = weekly_50
                
        tp_dist = max(risk * 1.5, abs(entry_price - target_station))
        tp = entry_price - tp_dist
            
    rr = abs(tp - entry_price) / max(risk, 1e-5)
    
    return {
        "sl": round(sl, digits),
        "tp": round(tp, digits),
        "risk": risk,
        "risk_reward": round(rr, 2),
        "target_station": round(target_station, digits)
    }
