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


def calculate_pair_runway(
    sym: str,
    direction: int,
    macro_cache: dict,
    current_mid: Optional[float] = None
) -> dict:
    """
    Menghitung sisa runway fisik ke C1/C2 (untuk BUY) atau F1/F2 (untuk SELL)
    dalam satuan jarak harga dan kelipatan ATR_H1.
    
    Returns:
        dict dengan key:
        - symbol: str
        - clean_symbol: str
        - direction: int
        - mid: float
        - atr_h1: float
        - runway_atr: float (sisa runway ke dinding pertama C1/F1 dalam x ATR)
        - runway_deep_atr: float (sisa runway ke dinding kedua C2/F2 dalam x ATR)
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

    mid = float(current_mid or m.get("current_mid") or m.get("current_price") or m.get("mid_price") or 0.0)
    atr = float(m.get("current_atr") or m.get("atr_val") or m.get("atr_h1") or m.get("atr") or 0.0)
    if atr <= 0:
        atr_pts = float(m.get("current_atr_pts") or m.get("atr_pts") or 0.0)
        point = float(m.get("point") or 0.00001)
        if atr_pts > 0 and point > 0:
            atr = atr_pts * point
        else:
            atr = 0.0010

    z_walls = m.get("zce_walls") or {}
    c1 = float(m.get("immediate_ceiling_c1") or m.get("ceiling_c1") or m.get("imm_ceiling_c1") or m.get("c1_level") or m.get("cluster_resistance") or z_walls.get("imm_ceiling_c1") or z_walls.get("c1") or z_walls.get("c1_price") or 0.0)
    f1 = float(m.get("immediate_floor_f1") or m.get("floor_f1") or m.get("imm_floor_f1") or m.get("f1_level") or m.get("cluster_support") or z_walls.get("imm_floor_f1") or z_walls.get("f1") or z_walls.get("f1_price") or 0.0)
    c2 = float(m.get("ceiling_c2") or m.get("deep_target_ceiling_c2") or m.get("deep_ceiling_c2") or m.get("c2_level") or z_walls.get("deep_ceiling_c2") or z_walls.get("c2") or z_walls.get("c2_price") or c1)
    f2 = float(m.get("floor_f2") or m.get("deep_target_floor_f2") or m.get("deep_floor_f2") or m.get("f2_level") or z_walls.get("deep_floor_f2") or z_walls.get("f2") or z_walls.get("f2_price") or f1)

    c1_grade = str(m.get("c1_reaction_grade") or m.get("imm_ceiling_c1_grade") or m.get("zce_c1_grade") or z_walls.get("imm_ceiling_c1_grade") or z_walls.get("c1_grade") or "GRADE_1_MICRO")
    f1_grade = str(m.get("f1_reaction_grade") or m.get("imm_floor_f1_grade") or m.get("zce_f1_grade") or z_walls.get("imm_floor_f1_grade") or z_walls.get("f1_grade") or "GRADE_1_MICRO")
    c2_grade = str(m.get("c2_reaction_grade") or m.get("deep_ceiling_c2_grade") or m.get("zce_c2_grade") or z_walls.get("deep_ceiling_c2_grade") or z_walls.get("c2_grade") or "GRADE_2_INTERMEDIATE")
    f2_grade = str(m.get("f2_reaction_grade") or m.get("deep_floor_f2_grade") or m.get("zce_f2_grade") or z_walls.get("deep_floor_f2_grade") or z_walls.get("f2_grade") or "GRADE_2_INTERMEDIATE")

    threshold_g3 = float(getattr(config, "CBSS_G3_BARRIER_THRESHOLD_ATR", 0.35))

    chamber_width = (c1 - f1) if (c1 > 0 and f1 > 0 and c1 > f1) else (2.0 * atr)
    chamber_width_atr = chamber_width / atr
    is_tight_chamber = chamber_width_atr < 1.00

    if direction == 1:  # BUY
        if c1 > mid:
            # Belum mencapai C1
            dist_c1 = c1 - mid
            runway_atr = dist_c1 / atr
            target_wall = c1
            target_grade = c1_grade
            # Benteng penahan lawan di depan BUY adalah C1
            dist_to_opp_wall = dist_c1
            is_at_wall_g3 = (dist_to_opp_wall / atr <= threshold_g3) and ("3" in c1_grade or "MACRO" in c1_grade)
            opp_wall_price = c1
            opp_wall_grade = c1_grade
        elif c2 > mid:
            # C1 sudah tertembus / di-retest dari atas, target berikutnya adalah C2
            dist_c2 = c2 - mid
            runway_atr = dist_c2 / atr
            target_wall = c2
            target_grade = c2_grade
            dist_to_opp_wall = dist_c2
            is_at_wall_g3 = (dist_to_opp_wall / atr <= threshold_g3) and ("3" in c2_grade or "MACRO" in c2_grade)
            opp_wall_price = c2
            opp_wall_grade = c2_grade
        else:
            # C1 dan C2 sudah tertembus (Blue Sky / Unconstrained Expansion)
            runway_atr = 2.5
            target_wall = c1 + (2.5 * atr) if c1 > 0 else mid + (2.5 * atr)
            target_grade = "UNCONSTRAINED_EXPANSION"
            dist_to_opp_wall = 99.0 * atr
            is_at_wall_g3 = False
            opp_wall_price = target_wall
            opp_wall_grade = target_grade

        dist_c2 = (c2 - mid) if (c2 > mid) else dist_to_opp_wall
        runway_deep_atr = dist_c2 / atr

    else:  # SELL
        if f1 > 0 and mid > f1:
            # Belum mencapai F1
            dist_f1 = mid - f1
            runway_atr = dist_f1 / atr
            target_wall = f1
            target_grade = f1_grade
            # Benteng penahan lawan di depan SELL adalah F1
            dist_to_opp_wall = dist_f1
            is_at_wall_g3 = (dist_to_opp_wall / atr <= threshold_g3) and ("3" in f1_grade or "MACRO" in f1_grade)
            opp_wall_price = f1
            opp_wall_grade = f1_grade
        elif f2 > 0 and mid > f2:
            # F1 sudah tertembus / di-retest dari bawah, target berikutnya adalah F2
            dist_f2 = mid - f2
            runway_atr = dist_f2 / atr
            target_wall = f2
            target_grade = f2_grade
            dist_to_opp_wall = dist_f2
            is_at_wall_g3 = (dist_to_opp_wall / atr <= threshold_g3) and ("3" in f2_grade or "MACRO" in f2_grade)
            opp_wall_price = f2
            opp_wall_grade = f2_grade
        else:
            # F1 dan F2 sudah tertembus (Waterfall / Unconstrained Breakdown)
            runway_atr = 2.5
            target_wall = max(0.0001, (f1 - (2.5 * atr)) if f1 > 0 else (mid - (2.5 * atr)))
            target_grade = "UNCONSTRAINED_EXPANSION"
            dist_to_opp_wall = 99.0 * atr
            is_at_wall_g3 = False
            opp_wall_price = target_wall
            opp_wall_grade = target_grade

        dist_f2 = (mid - f2) if (f2 > 0 and mid > f2) else dist_to_opp_wall
        runway_deep_atr = dist_f2 / atr

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


def is_pair_blocked_by_g3_wall(
    sym: str,
    direction: int,
    macro_cache: dict,
    current_mid: Optional[float] = None
) -> Tuple[bool, str]:
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

    res = calculate_pair_runway(sym, direction, macro_cache, current_mid=current_mid)
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


def check_basket_directional_conflict(
    symbol: str,
    direction: int,
    active_positions: list,
    active_orders: list
) -> Tuple[bool, str]:
    """
    Anti-Internal Currency Hedge Gate (10 Sep 2026):
    Memeriksa apakah pembukaan posisi/order baru akan menimbulkan eksposur berlawanan
    (hedging internal / self-cannibalization) pada mata uang yang sama terhadap posisi/order aktif.
    
    Contoh:
    Jika akun sudah memiliki posisi EURNZD BUY (Long EUR, Short NZD):
    - EURAUD SELL (Short EUR, Long AUD) -> DITOLAK (Opposing exposure on EUR).
    - AUDNZD BUY (Long AUD, Short NZD) -> DIIZINKAN (Tidak ada eksposur berlawanan).
    """
    if not getattr(config, "ENABLE_ANTI_INTERNAL_HEDGE", True):
        return True, ""

    csym = clean_symbol(symbol)
    if "BTC" in csym or "XAU" in csym:
        return True, ""

    cand_base, cand_quote = get_pair_currencies(csym)
    if not cand_base or not cand_quote:
        return True, ""

    # Direction: +1 = BUY (Long Base, Short Quote), -1 = SELL (Short Base, Long Quote)
    cand_exposures = {
        cand_base: 1 if direction == 1 else -1,
        cand_quote: -1 if direction == 1 else 1,
    }

    all_tickets = []
    if active_positions:
        all_tickets.extend(active_positions)
    if active_orders:
        all_tickets.extend(active_orders)

    for item in all_tickets:
        p_sym = getattr(item, "symbol", "") or ""
        p_csym = clean_symbol(p_sym)
        if p_csym == csym:
            continue  # Pair yang sama ditangani oleh aturan max 1 posisi per simbol

        p_base, p_quote = get_pair_currencies(p_csym)
        if not p_base or not p_quote:
            continue

        p_type = getattr(item, "type", None)
        is_buy = (p_type == 0) or ("BUY" in str(p_type).upper())
        p_dir = 1 if is_buy else -1

        p_exposures = {
            p_base: 1 if p_dir == 1 else -1,
            p_quote: -1 if p_dir == 1 else 1,
        }

        # Periksa apakah ada mata uang yang berlawanan tanda
        for curr, cand_sign in cand_exposures.items():
            if curr in p_exposures:
                p_sign = p_exposures[curr]
                if cand_sign * p_sign < 0:
                    cand_action = "LONG" if cand_sign > 0 else "SHORT"
                    p_action = "LONG" if p_sign > 0 else "SHORT"
                    return False, (
                        f"[CBSS ANTI-HEDGE] Konflik eksposur mata uang {curr}: "
                        f"Portofolio aktif sudah memegang {p_action} {curr} pada {p_sym}. "
                        f"Pembukaan {cand_action} {curr} pada {symbol} ditolak (Internal Cannibalization)."
                    )

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


def filter_and_rank_batch_candidates(
    candidates: List[Any],
    macro_cache: dict,
    active_positions: Optional[list] = None,
    active_orders: Optional[list] = None,
    csm_scores: Optional[dict] = None,
    hour_wib: Optional[int] = None
) -> List[Any]:
    """
    Lead-Lag Liquidity Relay & Zero-Opposing Basket Coordinator (10 Sep 2026):
    Memproses seluruh setup kandidat dalam satu siklus radar 60-detik secara batch:
    
    1. Pemisahan Aset Non-Fiat (BTC & XAU) yang lolos langsung.
    2. Anti-Internal Currency Hedge terhadap Portfolio MT5 (Zero Opposing Exposure).
    3. Physical ZCE Runway Check & Wall-Exhaustion Skip (< 0.50x ATR).
    4. Resolusi Konflik Intra-Batch via Composite Currency Vector (CSM Sign Arbiter).
    5. Seleksi Basket Champion (Estafet Likuiditas ke Laggard Ber-Runway Lapang).
    """
    if not candidates:
        return []

    active_pos_list = list(active_positions or [])
    active_ord_list = list(active_orders or [])

    # Ambil CSM scores jika tidak disediakan
    if csm_scores is None:
        try:
            from src.analytics.currency_strength import calculate_boitoki_csm
            csm_scores, _ = calculate_boitoki_csm()
        except Exception:
            csm_scores = {}
    if csm_scores is None:
        csm_scores = {}

    exempt_candidates = []
    fx_candidates = []

    for cand in candidates:
        sym = getattr(cand, "symbol", "") or ""
        csym = clean_symbol(sym)
        if "BTC" in csym or "XAU" in csym:
            exempt_candidates.append(cand)
        else:
            fx_candidates.append(cand)

    if not fx_candidates:
        return exempt_candidates

    # ── Tahap 2: Anti-Internal Currency Hedge terhadap Portfolio MT5 ──
    stage2_passed = []
    for cand in fx_candidates:
        sym = getattr(cand, "symbol", "")
        direction = getattr(cand, "direction", 0)
        is_safe, conflict_msg = check_basket_directional_conflict(
            symbol=sym,
            direction=direction,
            active_positions=active_pos_list,
            active_orders=active_ord_list
        )
        if not is_safe:
            logger.info(f"[CBSS BATCH DROP] {conflict_msg}")
            continue
        stage2_passed.append(cand)

    if not stage2_passed:
        return exempt_candidates

    # ── Tahap 3: Physical ZCE Runway Check & Wall-Exhaustion Skip ──
    stage3_passed = []
    for cand in stage2_passed:
        sym = getattr(cand, "symbol", "")
        direction = getattr(cand, "direction", 0)
        cand_mid = float(getattr(cand, "scan_mid", 0.0) or getattr(cand, "trigger_price", 0.0))
        runway_info = calculate_pair_runway(sym, direction, macro_cache, current_mid=cand_mid)
        is_g3_blocked, veto_reason = is_pair_blocked_by_g3_wall(sym, direction, macro_cache, current_mid=cand_mid)

        runway_atr = runway_info.get("runway_atr", 2.0)
        opp_grade = runway_info.get("opp_wall_grade", "")
        is_opp_g3 = ("3" in opp_grade or "MACRO" in opp_grade)
        wall_threshold_g3 = float(getattr(config, "CBSS_WALL_EXHAUSTION_G3_ATR", 0.35))

        # Eksklusif G3 Wall Exhaustion (11 Sep 2026):
        # HANYA benteng makro sejati G3 yang memicu Wall Exhaustion / Relay Pause.
        # Dinding G1 dan G2 adalah level minor/intermediate yang dapat ditembus (tidak memicu skip).
        if is_g3_blocked or (is_opp_g3 and runway_atr < wall_threshold_g3):
            logger.info(
                f"[CBSS WALL EXHAUSTED] {sym} ({'BUY' if direction == 1 else 'SELL'}) di-skip: "
                f"Runway {runway_atr:.2f}x ATR < {wall_threshold_g3:.2f}x ATR menabrak benteng makro G3 ({opp_grade}) "
                f"atau menabrak benteng ({veto_reason})."
            )
            continue
        if hasattr(cand, "metadata") and isinstance(cand.metadata, dict):
            cand.metadata["runway_atr"] = runway_atr
            cand.metadata["is_tight_chamber"] = runway_info.get("is_tight_chamber", False)
        stage3_passed.append(cand)

    if not stage3_passed:
        return exempt_candidates

    # ── Tahap 4: Resolusi Konflik Intra-Batch via Composite Currency Vector (CSM Sign) ──
    # Cek apakah dalam batch ini ada usulan yang saling bertentangan untuk mata uang yang sama
    def _get_cand_currency_dir(c_cand, target_curr: str) -> int:
        c_sym = getattr(c_cand, "symbol", "")
        base, quote = get_pair_currencies(c_sym)
        c_dir = getattr(c_cand, "direction", 0)
        if base == target_curr:
            return 1 if c_dir == 1 else -1
        elif quote == target_curr:
            return -1 if c_dir == 1 else 1
        return 0

    disqualified_indices = set()
    for curr in CURRENCIES:
        cands_with_curr = [
            (idx, c) for idx, c in enumerate(stage3_passed)
            if _get_cand_currency_dir(c, curr) != 0 and idx not in disqualified_indices
        ]
        if len(cands_with_curr) < 2:
            continue

        long_cands = [(idx, c) for idx, c in cands_with_curr if _get_cand_currency_dir(c, curr) > 0]
        short_cands = [(idx, c) for idx, c in cands_with_curr if _get_cand_currency_dir(c, curr) < 0]

        if long_cands and short_cands:
            csm_score = float(csm_scores.get(curr, 0.0))
            if csm_score > 0.0:
                # Arus mata uang Bullish -> Pertahankan LONG, gugurkan SHORT
                logger.info(
                    f"[CBSS BATCH CONFLICT] Mata uang {curr} memiliki usulan berlawanan dalam 1 batch scan. "
                    f"CSM {curr} ({csm_score:+.2f}) > 0 -> Menangkan proposal LONG, diskualifikasi proposal SHORT: "
                    f"{[getattr(x[1], 'symbol', '') for x in short_cands]}."
                )
                for idx, sc in short_cands:
                    disqualified_indices.add(idx)
            elif csm_score < 0.0:
                # Arus mata uang Bearish -> Pertahankan SHORT, gugurkan LONG
                logger.info(
                    f"[CBSS BATCH CONFLICT] Mata uang {curr} memiliki usulan berlawanan dalam 1 batch scan. "
                    f"CSM {curr} ({csm_score:+.2f}) < 0 -> Menangkan proposal SHORT, diskualifikasi proposal LONG: "
                    f"{[getattr(x[1], 'symbol', '') for x in long_cands]}."
                )
                for idx, lc in long_cands:
                    disqualified_indices.add(idx)
            else:
                # CSM netral: Gugurkan kandidat dengan runway lebih kecil
                avg_long_runway = sum((getattr(x[1], 'metadata', {}).get('runway_atr', 1.0)) for x in long_cands) / len(long_cands)
                avg_short_runway = sum((getattr(x[1], 'metadata', {}).get('runway_atr', 1.0)) for x in short_cands) / len(short_cands)
                if avg_long_runway >= avg_short_runway:
                    for idx, sc in short_cands:
                        disqualified_indices.add(idx)
                else:
                    for idx, lc in long_cands:
                        disqualified_indices.add(idx)

    stage4_passed = [c for idx, c in enumerate(stage3_passed) if idx not in disqualified_indices]
    if not stage4_passed:
        return exempt_candidates

    # ── Tahap 5: Seleksi Basket Champion (Estafet ke Laggard Ber-Runway Lapang) ──
    try:
        from src.analytics.currency_strength import get_csm_delta_for_symbol
    except Exception:
        get_csm_delta_for_symbol = lambda s: 0.0

    def _compute_candidate_score(cand_obj) -> float:
        sym_name = getattr(cand_obj, "symbol", "")
        dir_val = getattr(cand_obj, "direction", 0)
        r_val = (cand_obj.metadata.get("runway_atr", 1.0) if hasattr(cand_obj, "metadata") else 1.0)
        is_tight = (cand_obj.metadata.get("is_tight_chamber", False) if hasattr(cand_obj, "metadata") else False)
        
        delta_val = get_csm_delta_for_symbol(sym_name)
        alignment = max(0.0, delta_val * dir_val)
        score = (r_val * 0.45) + (alignment * 0.35) + ((1.0 if not is_tight else 0.5) * 0.20)

        # Session-Aware Driver Confluence (Reconciliation 10 Sep 2026)
        h = hour_wib
        if h is not None:
            base_c, quote_c = get_pair_currencies(sym_name)
            pair_currs = {base_c, quote_c}
            if 7 <= h < 14 and any(c in pair_currs for c in ("JPY", "AUD", "NZD")):
                score += 0.20
            elif 14 <= h < 18 and any(c in pair_currs for c in ("EUR", "GBP", "CHF")):
                score += 0.20
            elif h >= 18 and any(c in pair_currs for c in ("USD", "CAD")):
                score += 0.20

        return score

    # Urutkan kandidat berdasarkan skor tertinggi
    stage4_passed.sort(key=_compute_candidate_score, reverse=True)

    final_champions = []
    for cand in stage4_passed:
        # Cek konflik terhadap champion yang sudah terpilih di batch ini
        is_safe, conflict_msg = check_basket_directional_conflict(
            symbol=getattr(cand, "symbol", ""),
            direction=getattr(cand, "direction", 0),
            active_positions=final_champions,
            active_orders=[]
        )
        if not is_safe:
            logger.info(f"[CBSS BATCH DROP] {conflict_msg}")
            continue

        # Cek Concurrency Cap
        combined_existing = active_pos_list + final_champions
        cap_ok, cap_msg = check_basket_concurrency_cap(
            symbol=getattr(cand, "symbol", ""),
            direction=getattr(cand, "direction", 0),
            active_positions=combined_existing,
            active_orders=active_ord_list
        )
        if not cap_ok:
            logger.info(f"[CBSS CAP EXCEEDED] {cap_msg}")
            continue

        if hasattr(cand, "metadata") and isinstance(cand.metadata, dict):
            cand.metadata["cbss_champion"] = True
            cand.metadata["cbss_score"] = round(_compute_candidate_score(cand), 3)

        final_champions.append(cand)
        logger.info(
            f"🏆 [CBSS CHAMPION SELECTED] {getattr(cand, 'symbol', '')} "
            f"({'BUY' if getattr(cand, 'direction', 0) == 1 else 'SELL'}) "
            f"(Score: {_compute_candidate_score(cand):.2f}, "
            f"Runway: {cand.metadata.get('runway_atr', 0):.2f}x ATR)"
        )

    return exempt_candidates + final_champions


