"""
Currency Basket Structural Synchronization (CBSS) Engine
=========================================================
Pure Quant, zero-token structural synchronization layer across 8 major currencies
(EUR, USD, GBP, JPY, AUD, CAD, NZD, CHF) and 26 curated FX pairs.

Core Responsibilities:
1. Currency Basket Mapping: Maps any of the 26 symbols to its Base and Quote baskets.
2. Pair-Specific ZCE Runway Analysis: Calculates physical distance to C1/F1 and C2/F2
   normalized by ATR_H1 (bilateral chamber analysis).
3. Local Wall Veto (The EURAUD Law): Blocks continuation trades ONLY on the specific
   pair that is currently colliding with a D1/W1/H4 Grade 3 Fortress Wall (dist <= 0.35x ATR).
   Other pairs in the same currency basket with ample runway (>= 1.2x ATR) remain permitted.
4. Selective Pair Ranking: Ranks candidate pairs within the same currency basket by ZCE runway
   to prioritize the cleanest, longest-runway setups (Laggard Catch-Up).
5. Basket Concurrency Cap: Enforces a strict aggregate cap (default: max 2 active trades
   per currency in the same directional exposure) to prevent portfolio clustering.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple, Any

import config

logger = logging.getLogger("basket_sync_engine")

CURRENCIES = ["EUR", "USD", "JPY", "CHF", "GBP", "AUD", "CAD", "NZD"]

# 26 Curated Universe Baskets (Constituents)
BASKETS: Dict[str, List[str]] = {
    "EUR": ["EURUSD", "EURGBP", "EURJPY", "EURCHF", "EURAUD", "EURCAD", "EURNZD"],
    "USD": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD"],
    "GBP": ["GBPUSD", "EURGBP", "GBPJPY", "GBPCHF", "GBPAUD", "GBPCAD", "GBPNZD"],
    "JPY": ["USDJPY", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "NZDJPY"],
    "AUD": ["AUDUSD", "EURAUD", "GBPAUD", "AUDJPY", "AUDCAD", "AUDCHF", "AUDNZD"],
    "CAD": ["USDCAD", "EURCAD", "GBPCAD", "CADJPY", "AUDCAD", "NZDCAD"],
    "NZD": ["NZDUSD", "EURNZD", "GBPNZD", "NZDJPY", "AUDNZD", "NZDCAD"],
    "CHF": ["USDCHF", "EURCHF", "GBPCHF", "CHFJPY", "AUDCHF"],
}


def clean_symbol(symbol: str) -> str:
    """Normalize broker symbol suffix (e.g. 'EURUSD-ECN', 'EURUSD.c' -> 'EURUSD')."""
    return (
        (symbol or "")
        .replace("-ECNc", "")
        .replace(".c", "")
        .replace("-ECN", "")
        .replace("_i", "")
        .replace("m", "")
        .upper()
    )


def get_currency_basket_pairs(currency: str) -> List[str]:
    """Mengembalikan daftar pasangan dalam universe yang memuat mata uang tertentu."""
    return BASKETS.get(currency.upper(), [])


def get_pair_currencies(symbol: str) -> Tuple[str, str]:
    """Mengembalikan tuple (base_currency, quote_currency)."""
    csym = clean_symbol(symbol)
    if len(csym) >= 6 and not ("XAU" in csym or "BTC" in csym):
        return csym[:3], csym[3:6]
    return "", ""


def get_pair_role_in_currency(symbol: str, currency: str) -> int:
    """
    Mengembalikan orientasi mata uang dalam pair:
    +1 jika currency adalah Base (e.g. EUR di EURUSD -> Long EUR = Buy EURUSD)
    -1 jika currency adalah Quote (e.g. EUR di EURGBP? -> Base=EUR; tapi USD di EURUSD -> Quote=USD, Long USD = Sell EURUSD)
    0 jika tidak berhubungan
    """
    base, quote = get_pair_currencies(symbol)
    c = currency.upper()
    if c == base:
        return 1
    if c == quote:
        return -1
    return 0


def calculate_pair_runway(sym: str, direction: int, macro_cache: dict) -> dict:
    """
    Menghitung ZCE Runway bilateral (Immediate C1/F1 dan Deep C2/F2) yang dinormalisasi ATR H1.
    direction: +1 (BUY) atau -1 (SELL).
    
    Returns:
        dict dengan metrik:
        - runway_atr: float (kelipatan ATR H1 ke target wall terdekat)
        - runway_deep_atr: float (kelipatan ATR H1 ke target deep wall C2/F2)
        - target_wall_price: float
        - target_wall_grade: str ('GRADE_3_MACRO', 'GRADE_2_INTERMEDIATE', 'GRADE_1_MICRO')
        - is_at_wall_g3: bool (True jika saat ini menempel benteng G3 lawan <= 0.35x ATR)
        - chamber_width_atr: float
        - is_tight_chamber: bool
    """
    csym = clean_symbol(sym)
    m = (
        macro_cache.get(sym)
        or macro_cache.get(csym)
        or macro_cache.get(f"{csym}-ECN")
        or macro_cache.get(f"{csym}-ECNc")
        or macro_cache.get(f"{csym}.c")
        or {}
    )

    mid = float(m.get("current_mid") or m.get("current_price") or m.get("mid_price") or 0.0)
    atr = float(m.get("current_atr") or m.get("atr_val") or m.get("atr_h1") or 0.0)
    if atr <= 0:
        atr_pts = float(m.get("current_atr_pts") or m.get("atr_pts") or 0.0)
        point = float(m.get("point") or 0.00001)
        if atr_pts > 0 and point > 0:
            atr = atr_pts * point
        else:
            atr = 0.0010

    z_walls = m.get("zce_walls") or {}
    c1 = float(m.get("immediate_ceiling_c1") or m.get("ceiling_c1") or m.get("imm_ceiling_c1") or m.get("c1_level") or m.get("cluster_resistance") or z_walls.get("c1") or 0.0)
    f1 = float(m.get("immediate_floor_f1") or m.get("floor_f1") or m.get("imm_floor_f1") or m.get("f1_level") or m.get("cluster_support") or z_walls.get("f1") or 0.0)
    c2 = float(m.get("ceiling_c2") or m.get("deep_target_ceiling_c2") or m.get("deep_ceiling_c2") or m.get("c2_level") or z_walls.get("c2") or c1)
    f2 = float(m.get("floor_f2") or m.get("deep_target_floor_f2") or m.get("deep_floor_f2") or m.get("f2_level") or z_walls.get("f2") or f1)

    c1_grade = str(m.get("c1_reaction_grade") or m.get("imm_ceiling_c1_grade") or m.get("zce_c1_grade") or z_walls.get("c1_grade") or "GRADE_1_MICRO")
    f1_grade = str(m.get("f1_reaction_grade") or m.get("imm_floor_f1_grade") or m.get("zce_f1_grade") or z_walls.get("f1_grade") or "GRADE_1_MICRO")
    c2_grade = str(m.get("c2_reaction_grade") or m.get("deep_ceiling_c2_grade") or m.get("zce_c2_grade") or z_walls.get("c2_grade") or "GRADE_2_INTERMEDIATE")
    f2_grade = str(m.get("f2_reaction_grade") or m.get("deep_floor_f2_grade") or m.get("zce_f2_grade") or z_walls.get("f2_grade") or "GRADE_2_INTERMEDIATE")

    threshold_g3 = float(getattr(config, "CBSS_G3_BARRIER_THRESHOLD_ATR", 0.35))

    chamber_width = (c1 - f1) if (c1 > 0 and f1 > 0 and c1 > f1) else (2.0 * atr)
    chamber_width_atr = chamber_width / atr
    is_tight_chamber = chamber_width_atr < 1.00

    if direction == 1:  # BUY
        # Target ke atas adalah C1 (atau C2 jika C1 sudah tertembus)
        dist_c1 = (c1 - mid) if (c1 > mid) else 0.0
        dist_c2 = (c2 - mid) if (c2 > mid) else dist_c1

        runway_atr = dist_c1 / atr if c1 > 0 else 2.0
        runway_deep_atr = dist_c2 / atr if c2 > 0 else runway_atr
        target_wall = c1 if c1 > mid else c2
        target_grade = c1_grade if c1 > mid else c2_grade

        # Benteng penahan lawan di depan BUY adalah C1
        dist_to_opp_wall = (c1 - mid) if (c1 > mid) else 99.0 * atr
        is_at_wall_g3 = (dist_to_opp_wall / atr <= threshold_g3) and ("3" in c1_grade or "MACRO" in c1_grade)
        opp_wall_price = c1
        opp_wall_grade = c1_grade

    else:  # SELL
        # Target ke bawah adalah F1 (atau F2 jika F1 sudah tertembus)
        dist_f1 = (mid - f1) if (f1 > 0 and mid > f1) else 0.0
        dist_f2 = (mid - f2) if (f2 > 0 and mid > f2) else dist_f1

        runway_atr = dist_f1 / atr if f1 > 0 else 2.0
        runway_deep_atr = dist_f2 / atr if f2 > 0 else runway_atr
        target_wall = f1 if (f1 > 0 and mid > f1) else f2
        target_grade = f1_grade if (f1 > 0 and mid > f1) else f2_grade

        # Benteng penahan lawan di depan SELL adalah F1
        dist_to_opp_wall = (mid - f1) if (f1 > 0 and mid > f1) else 99.0 * atr
        is_at_wall_g3 = (dist_to_opp_wall / atr <= threshold_g3) and ("3" in f1_grade or "MACRO" in f1_grade)
        opp_wall_price = f1
        opp_wall_grade = f1_grade

    return {
        "symbol": sym,
        "clean_symbol": csym,
        "direction": direction,
        "mid": mid,
        "atr_h1": atr,
        "runway_atr": round(runway_atr, 2),
        "runway_deep_atr": round(runway_deep_atr, 2),
        "target_wall_price": target_wall,
        "target_wall_grade": target_grade,
        "opp_wall_price": opp_wall_price,
        "opp_wall_grade": opp_wall_grade,
        "is_at_wall_g3": bool(is_at_wall_g3),
        "chamber_width_atr": round(chamber_width_atr, 2),
        "is_tight_chamber": is_tight_chamber,
    }


def is_pair_blocked_by_g3_wall(sym: str, direction: int, macro_cache: dict) -> Tuple[bool, str]:
    """
    LOCAL PAIR VETO (The EURAUD Law):
    Memeriksa apakah pair ini sendiri sedang menabrak dinding penahan makro G3 lawan
    dalam jarak <= 0.35x ATR.
    
    Jika ya -> Veto trade kelanjutan (Continuation) pada pair ini saja.
    Pair sekeranjang lainnya yang memiliki runway lapang TETAP DIPERBOLEHKAN.
    """
    if not getattr(config, "ENABLE_CBSS", True):
        return False, "CBSS_DISABLED"

    csym = clean_symbol(sym)
    if "BTC" in csym or "XAU" in csym:
        return False, "NON_FX_EXEMPT"

    res = calculate_pair_runway(sym, direction, macro_cache)
    if res["is_at_wall_g3"]:
        side = "BUY" if direction == 1 else "SELL"
        wall_name = "C1 Ceiling" if direction == 1 else "F1 Floor"
        return True, (
            f"[CBSS VETO] Local G3 Wall Collision: {csym} {side} is within "
            f"{res['opp_wall_price']:.5f} ({res['opp_wall_grade']}) <= {getattr(config, 'CBSS_G3_BARRIER_THRESHOLD_ATR', 0.35)}x ATR. "
            f"Continuation blocked on {csym} (Wait for SFP Reclaim or Breached Wall)."
        )

    return False, "CLEAR"


def is_symbol_allowed_for_session(symbol: str, hour_wib: int) -> bool:
    """
    Session-aware symbol filter:
    - Tokyo (07:00 - 14:00 WIB): Any symbol containing JPY, AUD, NZD.
    - London Core (14:00 - 19:00 WIB): All configured pairs.
    - New York (19:00 - 23:59 WIB): Locks Pacific crosses if NY_LOCK_PACIFIC_CROSSES is True.
    - Dead Zone (00:00 - 07:00 WIB): FX locked, Crypto 24/7.
    """
    csym = clean_symbol(symbol)
    if "BTC" in csym:
        return True

    asia_start = getattr(config, "ASIA_SESSION_START_HOUR_WIB", 7)
    asia_end = getattr(config, "ASIA_SESSION_END_HOUR_WIB", 14)
    ny_start = getattr(config, "NY_SESSION_START_HOUR_WIB", 19)
    lock_pacific_cross = getattr(config, "NY_LOCK_PACIFIC_CROSSES", True)

    if asia_start <= hour_wib < asia_end:
        return any(c in csym for c in ("JPY", "AUD", "NZD"))
    elif asia_end <= hour_wib < ny_start:
        return True
    elif ny_start <= hour_wib <= 23:
        if lock_pacific_cross and hasattr(config, "is_pacific_cross") and config.is_pacific_cross(symbol):
            return False
        return True
    return False


def rank_basket_candidates_by_runway(
    pairs: List[str],
    direction: int,
    macro_cache: dict,
    hour_wib: Optional[int] = None
) -> List[dict]:
    """
    Mengurutkan kandidat sekeranjang berdasarkan:
    1. Kelayakan Sesi Aktif (Session-Aware: pair yang PERMITTED di jam ini diutamakan).
    2. Kebersihan Benteng (Bebas Local G3 Wall Veto).
    3. Runway ZCE Terpanjang (runway_atr).
    """
    ranked = []
    for p in pairs:
        info = calculate_pair_runway(p, direction, macro_cache)
        is_g3_blocked, veto_reason = is_pair_blocked_by_g3_wall(p, direction, macro_cache)
        info["is_g3_blocked"] = is_g3_blocked
        info["veto_reason"] = veto_reason

        # Evaluasi session eligibility
        if hour_wib is not None and getattr(config, "SESSION_AWARE_ROUTING_ENABLED", True):
            is_sess_ok = is_symbol_allowed_for_session(p, hour_wib)
        else:
            is_sess_ok = True
        info["is_session_allowed"] = is_sess_ok

        ranked.append(info)

    # Multi-Tier Sorting:
    # 1: is_session_allowed (True first -> 1, False -> 0)
    # 2: not is_g3_blocked (True first -> 1, False -> 0)
    # 3: runway_atr (Descending)
    ranked.sort(
        key=lambda x: (
            1 if x.get("is_session_allowed", True) else 0,
            0 if x.get("is_g3_blocked", False) else 1,
            x.get("runway_atr", 0.0)
        ),
        reverse=True
    )
    return ranked


def check_basket_concurrency_cap(
    symbol: str,
    direction: int,
    active_positions: list,
    active_orders: list
) -> Tuple[bool, str]:
    """
    Memastikan pembukaan trade tidak melebihi batas maksimal konkurensi mata uang
    (default: max 2 posisi per mata uang dalam arah eksposur yang sama).
    """
    if not getattr(config, "ENABLE_CBSS", True):
        return True, ""

    csym = clean_symbol(symbol)
    if "BTC" in csym or "XAU" in csym:
        return True, ""

    base, quote = get_pair_currencies(csym)
    if not base or not quote:
        return True, ""

    max_cap = int(getattr(config, "CBSS_MAX_BASKET_CONCURRENCY", 2))

    # Kumpulkan semua open positions + active orders
    all_tickets = []
    if active_positions:
        all_tickets.extend(active_positions)
    if active_orders:
        all_tickets.extend(active_orders)

    base_count = 0
    quote_count = 0

    for item in all_tickets:
        p_sym = getattr(item, "symbol", "") or ""
        p_csym = clean_symbol(p_sym)
        if p_csym == csym:
            continue  # Pair itu sendiri dievaluasi terpisah oleh max 1 pos per simbol

        p_base, p_quote = get_pair_currencies(p_csym)
        p_type = getattr(item, "type", None)
        # Order type 0 = BUY, 1 = SELL (MT5 convention)
        is_buy = (p_type == 0) or ("BUY" in str(p_type).upper())
        item_dir = 1 if is_buy else -1

        # Cek eksposur Base currency
        if p_base == base and item_dir == direction:
            base_count += 1
        elif p_quote == base and item_dir != direction:
            base_count += 1

        # Cek eksposur Quote currency
        if p_quote == quote and item_dir == direction:
            quote_count += 1
        elif p_base == quote and item_dir != direction:
            quote_count += 1

    if base_count >= max_cap:
        return False, f"[CBSS CAP] Basket {base} sudah memiliki {base_count}/{max_cap} trade aktif searah."

    if quote_count >= max_cap:
        return False, f"[CBSS CAP] Basket {quote} sudah memiliki {quote_count}/{max_cap} trade aktif searah."

    return True, ""


def calculate_basket_saturation_index(
    currency: str,
    direction: int,
    macro_cache: dict
) -> Tuple[float, int, int]:
    """
    Menghitung Basket Structural Saturation Index (BSSI):
    Rasio pair dalam satu keranjang yang secara bersamaan menabrak benteng lawan
    (dist <= 0.35x ATR atau is_at_wall_g3 == True).
    
    Returns:
        (bssi_ratio: float, colliding_count: int, total_pairs: int)
    """
    c = currency.upper()
    pairs = BASKETS.get(c, [])
    if not pairs:
        return 0.0, 0, 0

    colliding = 0
    total = 0

    threshold_atr = float(getattr(config, "CBSS_G3_BARRIER_THRESHOLD_ATR", 0.35))

    for p in pairs:
        base, quote = get_pair_currencies(p)
        if not base or not quote:
            continue

        # Orientasi arah pair sesuai eksposur currency
        if base == c:
            pair_dir = direction
        elif quote == c:
            pair_dir = -direction
        else:
            continue

        runway = calculate_pair_runway(p, pair_dir, macro_cache)
        r_atr = runway.get("runway_atr", 2.0)
        is_g3 = runway.get("is_at_wall_g3", False)

        total += 1
        if is_g3 or r_atr <= threshold_atr:
            colliding += 1

    ratio = (colliding / total) if total > 0 else 0.0
    return round(ratio, 2), colliding, total


def select_basket_champion(
    currency: str,
    direction: int,
    macro_cache: dict,
    candidate_pairs: Optional[List[str]] = None,
    min_runway_atr: float = 0.85,
    hour_wib: Optional[int] = None
) -> Optional[dict]:
    """
    Bilateral Composite Champion Selector:
    Memilih kandidat laggard terbaik dalam satu keranjang mata uang berdasarkan:
    1. Sesi aktif (is_session_allowed).
    2. Kebersihan benteng (tidak menabrak dinding G3 lawan).
    3. Sisa Runway ZCE (minimal min_runway_atr, default 0.85x ATR).
    4. Kelemahan Quote Currency / Kekuatan Net CSM Delta.
    
    Returns:
        dict info pair pemenang, atau None jika tidak ada yang memenuhi syarat.
    """
    c = currency.upper()
    all_basket_pairs = BASKETS.get(c, [])
    if candidate_pairs is not None:
        target_pool = [p for p in all_basket_pairs if clean_symbol(p) in [clean_symbol(x) for x in candidate_pairs]]
    else:
        target_pool = all_basket_pairs

    if not target_pool:
        return None

    # Lazy import CSM delta to avoid circular import
    try:
        from src.analytics.currency_strength import get_csm_delta_for_symbol
    except Exception:
        get_csm_delta_for_symbol = lambda s: 0.0

    scored_candidates = []

    for p in target_pool:
        base, quote = get_pair_currencies(p)
        if not base or not quote:
            continue

        pair_dir = direction if base == c else -direction
        info = calculate_pair_runway(p, pair_dir, macro_cache)
        is_g3_blocked, veto_reason = is_pair_blocked_by_g3_wall(p, pair_dir, macro_cache)

        if is_g3_blocked:
            continue

        r_atr = info.get("runway_atr", 0.0)
        if r_atr < min_runway_atr:
            continue

        # Session filtering
        if hour_wib is not None and getattr(config, "SESSION_AWARE_ROUTING_ENABLED", True):
            if not is_symbol_allowed_for_session(p, hour_wib):
                continue

        csm_delta = get_csm_delta_for_symbol(p)
        # Evaluasi apakah CSM mendukung arah trade
        csm_alignment = (csm_delta * pair_dir)

        composite_score = (r_atr * 0.45) + (max(0.0, csm_alignment) * 0.35) + (1.0 if not info.get("is_tight_chamber") else 0.5) * 0.20

        info["pair"] = p
        info["pair_direction"] = pair_dir
        info["csm_delta"] = csm_delta
        info["csm_alignment"] = csm_alignment
        info["composite_score"] = round(composite_score, 3)
        scored_candidates.append(info)

    if not scored_candidates:
        return None

    scored_candidates.sort(key=lambda x: x["composite_score"], reverse=True)
    return scored_candidates[0]

