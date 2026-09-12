"""
dashboard.py — Institutional Standalone Quant Decision Surveillance Cockpit.
Terminal-grade HTTP server providing real-time data from MT5, ZCE, MSE, and 4-Mechanism Radar.

Usage:
    python dashboard.py                 # Generates static HTML
    python dashboard.py --serve         # Runs real-time local server at http://localhost:8765
    python dashboard.py --port 8080     # Custom port
"""

import argparse
import http.server
import json
import logging
import math
import os
import re
import socketserver
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger("dashboard")

# Windows terminal UTF-8 encoding fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

import config
from src.core import mt5_connector as connector
from src.analytics.market_scanner import MarketScanner, evaluate_systemic_basket_lock
from src.analytics.currency_strength import calculate_boitoki_csm, get_csm_delta_for_symbol
from src.analytics.basket_sync_engine import (
    BASKETS,
    CURRENCIES,
    get_pair_currencies,
    calculate_pair_runway,
    is_pair_blocked_by_g3_wall,
    check_basket_concurrency_cap,
    check_basket_directional_conflict,
    rank_basket_candidates_by_runway,
    is_symbol_allowed_for_session,
    calculate_basket_saturation_index,
    select_basket_champion,
    clean_symbol as cbss_clean_symbol
)
from src.analytics.macro_strategic_engine import evaluate_session_confluence_timing
from src.analytics.zone_confluence_engine import ZCE_W_TF
from src.indicators.lux_smc import LuxSMCAnalyzer
from src.analytics.pattern_engine import MacroEnvelopeEngine
from src.analytics.shadow_report import render_shadow_report_html, generate_and_save_shadow_report
from dashboard_assets import TEMPLATE

WIB = ZoneInfo("Asia/Jakarta")
DATA_DIR = os.path.join(ROOT, "data")
OUT_HTML = os.path.join(ROOT, "dashboard.html")
FUNNEL_METRICS_PATH = os.path.join(DATA_DIR, "quant_funnel_metrics.json")


def _get_session_info(dt_wib: datetime, symbol: str = "") -> Dict[str, Any]:
    """
    Evaluates context-aware operational session & execution permission 1:1 with engine rules.
    Identifies:
    - CRYPTO_247: Bitcoin / Crypto 24/7 active (Bebas Dead Zone & Asian Lock)
    - FRIDAY_LOCK: Jumat >= 23:00 WIB s/d Minggu (Weekend market closed)
    - DEAD_ZONE: 00:00 - 08:00 WIB (Rollover 03:55-04:15 & Pre-rollover 03:50)
    - ASIAN_ACTIVE: 08:00 - 14:00 WIB untuk driver JPY/AUD/NZD
    - ASIAN_LOCKED: 08:00 - 14:00 WIB untuk non-Asian pairs (EURUSD, GBPUSD, dll)
    - LONDON_EXPANSION: 14:00 - 19:00 WIB (High-volume London open)
    - NY_OVERLAP: 19:00 - 23:00 WIB (Peak liquidity)
    - LATE_NY: 23:00 - 02:00 WIB (Max 2 positions cap)
    """
    clean = (symbol or "").replace("-ECNc", "").replace("-ECN", "").replace(".c", "").upper()
    is_crypto = config.is_crypto(symbol) if hasattr(config, "is_crypto") else ("BTC" in clean)

    if is_crypto:
        return {
            "type": "CRYPTO_247",
            "status": "PERMITTED",
            "label": "24/7 Crypto Execution Active",
            "color": "rgba(59, 130, 246, 0.07)",
            "border_color": "rgba(59, 130, 246, 0.40)",
            "name": "CRYPTO"
        }

    h = dt_wib.hour

    if clean:
        weekday = dt_wib.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        if (weekday == 4 and h >= 23) or weekday in (5, 6):
            return {
                "type": "FRIDAY_LOCK",
                "status": "BLOCKED",
                "label": "Weekend / Friday Lock (Market Closed)",
                "color": "rgba(239, 68, 68, 0.08)",
                "border_color": "rgba(239, 68, 68, 0.45)",
                "name": "CLOSED"
            }

    if 0 <= h < 7:
        if (h == 3 and dt_wib.minute >= 50) or (h == 4 and dt_wib.minute <= 15):
            lbl = "Rollover Spread Spike (03:50–04:15 WIB)"
        else:
            lbl = "Dead Zone: Rollover & Thin Liquidity (00:00–07:00 WIB)"
        return {
            "type": "DEAD_ZONE",
            "status": "BLOCKED",
            "label": lbl,
            "color": "rgba(239, 68, 68, 0.07)",
            "border_color": "rgba(239, 68, 68, 0.40)",
            "name": "DEAD_ZONE"
        }
    elif 7 <= h < 14:
        is_asian_allowed = (not clean) or any(k in clean for k in ("JPY", "AUD", "NZD"))
        if is_asian_allowed:
            lbl = f"Tokyo Active Driver ({clean} Permitted)" if clean else "Tokyo Active Session"
            return {
                "type": "ASIAN_ACTIVE",
                "status": "PERMITTED",
                "label": lbl,
                "color": "rgba(16, 185, 129, 0.06)",
                "border_color": "rgba(16, 185, 129, 0.40)",
                "name": "TOKYO"
            }
        else:
            return {
                "type": "ASIAN_LOCKED",
                "status": "BLOCKED",
                "label": f"Session Locked: Non-Asian Driver ({clean} Locked)",
                "color": "rgba(245, 158, 11, 0.07)",
                "border_color": "rgba(245, 158, 11, 0.40)",
                "name": "TOKYO_LOCK"
            }
    elif 14 <= h < 19:
        return {
            "type": "LONDON_EXPANSION",
            "status": "PERMITTED",
            "label": "London Open Expansion (High Volume)",
            "color": "rgba(14, 165, 233, 0.06)",
            "border_color": "rgba(14, 165, 233, 0.35)",
            "name": "LONDON"
        }
    elif 19 <= h < 23:
        return {
            "type": "NY_OVERLAP",
            "status": "PERMITTED",
            "label": "London / NY Overlap (Peak Liquidity)",
            "color": "rgba(168, 85, 247, 0.07)",
            "border_color": "rgba(168, 85, 247, 0.35)",
            "name": "OVERLAP"
        }
    else:
        return {
            "type": "LATE_NY",
            "status": "PERMITTED",
            "label": "Late NY Window (Max 2 Positions Cap)",
            "color": "rgba(99, 102, 241, 0.05)",
            "border_color": "rgba(99, 102, 241, 0.35)",
            "name": "LATE_NY"
        }


def _get_session_name(dt_wib: datetime, symbol: str = "") -> str:
    return _get_session_info(dt_wib, symbol)["name"]


def _get_countdown_to_rollover(now_wib: datetime) -> str:
    target = now_wib.replace(hour=3, minute=50, second=0, microsecond=0)
    if now_wib >= target:
        target += timedelta(days=1)
    diff = target - now_wib
    total_secs = int(diff.total_seconds())
    hours, rem = divmod(total_secs, 3600)
    mins = rem // 60
    return f"{hours}h {mins:02d}m"


def _consolidate_zce_zones(
    zm: Any,
    cur_price: float,
    v_lo: float,
    v_hi: float,
    atr_val: float,
    pip_val: float,
    digits: int
) -> List[Dict[str, Any]]:
    """
    Extracts all ZCE multi-horizon layers and performs Cluster Consolidation & Proximity Clamp.
    Merges zones within <= max(0.20*ATR, 4 pips) to prevent chart overlap clutter.
    """
    if zm is None:
        return []

    cands: List[Dict[str, Any]] = []

    # 1. Elected floors & ceilings from ZoneMapResult (Preserve all elected structural walls)
    for fl in getattr(zm, "floors", []) or []:
        p = float(fl.get("price", 0.0))
        fl_sources = list(fl.get("sources", []))
        fl_tfs = list(fl.get("tfs_present", []))
        fl_kinds = list(fl.get("kinds_present", []))
        cands.append({
            "price": p,
            "band_low": float(fl.get("band_low", p)),
            "band_high": float(fl.get("band_high", p)),
            "tier": str(fl.get("tier", "F")),
            "grade": str(fl.get("grade", "GRADE_1_MICRO")),
            "score": float(fl.get("density_score", fl.get("score_raw", 1.0))),
            "tag": str(fl.get("tag", "FORTRESS")),
            "tfs": fl_tfs,
            "kinds": fl_kinds,
            "sources": fl_sources,
            "is_cold": bool(fl.get("is_cold", False)),
            "is_vacuum": bool(fl.get("is_vacuum", False)),
            "confluence": int(fl.get("confluence", len(fl_sources))),
            "tf_max": str(fl.get("tf_max", "")),
            "horizon_max": int(fl.get("horizon_max", 0)),
            "at_price": bool(fl.get("at_price", False)),
            "source": "elected",
            "type": "floor"
        })

    for ce in getattr(zm, "ceilings", []) or []:
        p = float(ce.get("price", 0.0))
        ce_sources = list(ce.get("sources", []))
        ce_tfs = list(ce.get("tfs_present", []))
        ce_kinds = list(ce.get("kinds_present", []))
        cands.append({
            "price": p,
            "band_low": float(ce.get("band_low", p)),
            "band_high": float(ce.get("band_high", p)),
            "tier": str(ce.get("tier", "C")),
            "grade": str(ce.get("grade", "GRADE_1_MICRO")),
            "score": float(ce.get("density_score", ce.get("score_raw", 1.0))),
            "tag": str(ce.get("tag", "FORTRESS")),
            "tfs": ce_tfs,
            "kinds": ce_kinds,
            "sources": ce_sources,
            "is_cold": bool(ce.get("is_cold", False)),
            "is_vacuum": bool(ce.get("is_vacuum", False)),
            "confluence": int(ce.get("confluence", len(ce_sources))),
            "tf_max": str(ce.get("tf_max", "")),
            "horizon_max": int(ce.get("horizon_max", 0)),
            "at_price": bool(ce.get("at_price", False)),
            "source": "elected",
            "type": "ceiling"
        })

    # 2. Raw clusters from ZoneMapResult (Strict Physical Role-Aware Assignment)
    probe_tol = float(getattr(config, "ZCE_CHAMBER_CLEARANCE_ATR_MULT", 0.30)) * atr_val
    for cl in getattr(zm, "clusters", []) or []:
        role = getattr(cl, "inherent_role", "")
        if not role:
            role = "CEILING" if cl.fortress_tag.startswith("C_") else ("FLOOR" if cl.fortress_tag.startswith("F_") else "NEUTRAL")

        b_lo = float(getattr(cl, "band_low", 0.0))
        b_hi = float(getattr(cl, "band_high", 0.0))

        if b_hi < cur_price:
            if role == "CEILING" and cur_price < b_hi + probe_tol:
                # Belum sah tembus bersih ke atas (belum sah RBS floor)
                continue
            p = b_hi
            cl_type = "floor"
        elif b_lo > cur_price:
            if role == "FLOOR" and cur_price > b_lo - probe_tol:
                # Belum sah tembus bersih ke bawah (belum sah SBR ceiling)
                continue
            p = b_lo
            cl_type = "ceiling"
        else:
            # Harga live berada di dalam rentang band (b_lo <= cur_price <= b_hi)
            if role == "CEILING":
                p = b_hi
                cl_type = "ceiling"
            elif role == "FLOOR":
                p = b_lo
                cl_type = "floor"
            else:
                p = b_hi if (b_hi - cur_price) < (cur_price - b_lo) else b_lo
                cl_type = "ceiling" if p > cur_price else "floor"

        if v_lo <= p <= v_hi:
            cl_sources = []
            for m in getattr(cl, "members", []) or []:
                s_name = f"{m.kind} ({m.tf})" if getattr(m, "tf", None) else str(m.kind)
                if s_name not in cl_sources:
                    cl_sources.append(s_name)

            cands.append({
                "price": p,
                "band_low": b_lo,
                "band_high": b_hi,
                "tier": "ZONE",
                "grade": str(getattr(cl, "grade", "GRADE_1_MICRO")),
                "score": float(getattr(cl, "score_final", 1.0)),
                "tag": str(getattr(cl, "fortress_tag", "FORTRESS")),
                "tfs": list(getattr(cl, "tfs_present", [])),
                "kinds": list(getattr(cl, "kinds_present", [])),
                "sources": cl_sources,
                "is_cold": bool(getattr(cl, "is_cold", False)),
                "is_vacuum": bool(getattr(cl, "is_vacuum", False)),
                "confluence": int(getattr(cl, "confluence", len(cl_sources))),
                "tf_max": (max(getattr(cl, "tfs_present", []), key=lambda t: ZCE_W_TF.get(t, 0.0)) if getattr(cl, "tfs_present", None) else ""),
                "horizon_max": int(getattr(cl, "horizon_max", 0)),
                "at_price": False,
                "source": "cluster",
                "type": cl_type
            })

    if not cands:
        return []

    # Sort by price
    cands.sort(key=lambda x: x["price"])

    # Cluster consolidation by proximity threshold (pip-aware self-adaptive)
    pip_thr = min(15.0 * pip_val, 0.75 * atr_val)
    proximity_thr = max(0.35 * atr_val, pip_thr)
    grade_rank = {"GRADE_3_MACRO": 3, "GRADE_2_INTERMEDIATE": 2, "GRADE_1_MICRO": 1}

    merged_groups: List[List[Dict[str, Any]]] = []
    curr_group: List[Dict[str, Any]] = [cands[0]]

    for item in cands[1:]:
        prev_price = curr_group[-1]["price"]
        if abs(item["price"] - prev_price) <= proximity_thr:
            curr_group.append(item)
        else:
            merged_groups.append(curr_group)
            curr_group = [item]
    if curr_group:
        merged_groups.append(curr_group)

    result = []
    for grp in merged_groups:
        grp.sort(key=lambda x: (
            1 if x["source"] == "elected" else 0,
            grade_rank.get(x["grade"], 1),
            x["score"]
        ), reverse=True)
        lead = grp[0]

        all_tfs = sorted(list(set(tf for x in grp for tf in x.get("tfs", []))))
        all_kinds = sorted(list(set(k for x in grp for k in x.get("kinds", []))))
        all_sources = []
        for x in grp:
            for s in x.get("sources", []):
                if s not in all_sources:
                    all_sources.append(s)

        avg_price = sum(x["price"] for x in grp) / len(grp)
        rep_price = lead["price"] if lead["source"] == "elected" else avg_price

        min_lo = min(x["band_low"] for x in grp)
        max_hi = max(x["band_high"] for x in grp)
        max_score = max(x["score"] for x in grp)
        max_confl = max(x.get("confluence", len(x.get("sources", []))) for x in grp)
        effective_confl = max(max_confl, len(all_sources))
        top_grade = lead["grade"]
        top_tier = lead["tier"]
        lead_type = lead.get("type") or ("floor" if rep_price < cur_price else "ceiling")
        if top_tier == "ZONE":
            top_tier = "FLR" if lead_type == "floor" else "CEIL"

        g_short = "G3" if top_grade == "GRADE_3_MACRO" else ("G2" if top_grade == "GRADE_2_INTERMEDIATE" else "G1")
        tf_str = "+".join(all_tfs[:3]) if all_tfs else "H1"
        kind_str = "+".join(all_kinds[:2]) if all_kinds else "SMC"
        confl_tag = f" • {effective_confl}src" if effective_confl > 0 else ""
        at_tag = "~" if lead.get("at_price") else ""
        label = f"{at_tag}{top_tier} [{g_short}] {rep_price:.{digits}f} ({max_score:.1f} • {tf_str} • {kind_str}{confl_tag})"

        confluences_desc = " • ".join(all_sources[:4]) if all_sources else (" + ".join(all_kinds[:3]) if all_kinds else "Structural S/R Anchor")

        result.append({
            "price": round(float(rep_price), digits),
            "band_low": round(float(min_lo), digits),
            "band_high": round(float(max_hi), digits),
            "type": lead_type,
            "tier": top_tier,
            "grade": top_grade,
            "score": round(float(max_score), 2),
            "tfs": all_tfs,
            "kinds": all_kinds,
            "sources": all_sources,
            "num_sources": effective_confl,
            "confluences": confluences_desc,
            "timeframes": "+".join(all_tfs) if all_tfs else "H1",
            "tag": lead["tag"],
            "label": label,
            "is_cold": any(x["is_cold"] for x in grp),
            "is_vacuum": any(x["is_vacuum"] for x in grp),
            "confluence": effective_confl,
            "tf_max": str(lead.get("tf_max", "")),
            "horizon_max": int(lead.get("horizon_max", 0)),
            "at_price": bool(lead.get("at_price", False)),
        })

    return result


def _elect_primary_standby(
    standbys: List[Dict[str, Any]],
    macro: Dict[str, Any],
    mid: float,
    pt: float,
    atr_val: float,
    pip_val: float,
    dir_lock: int = 0
) -> Dict[str, Any]:
    """
    Unified 1:1 Primary Standby Selector.
    Synchronizes Watchlist active_setup, HUD operational_phase, and Canvas Trajectory.
    Prioritizes:
      1. Confluence setups (is_confluence == True).
      2. Active physical interaction (TOUCH_ACTIVE, RETEST_ACTIVE, ACTIVE_PIERCE)
         aligned with macro trend or Direction Lock.
      3. Pro-trend actionable setups closest to market (min dist_atr).
      4. Counter-trend / watch setups only if no pro-trend setup exists.
    """
    if not standbys or mid <= 0:
        return {
            "name": "IDLE",
            "type": "",
            "dir": "NEUTRAL",
            "dir_int": 0,
            "dist_pips": 999.0,
            "dist_atr": 99.0,
            "lvl": 0.0,
            "target": 0.0,
            "is_confluence": False,
            "confluence_name": "",
            "extra_count": 0,
            "standby": None
        }

    # Determine preferred institutional direction
    csm_delta = float(macro.get("csm_delta", 0.0) or 0.0)
    dr_pos = float(macro.get("dealing_range_pos", 0.5) or 0.5)

    if dir_lock in (1, -1):
        preferred_dir = dir_lock
    elif dr_pos >= 0.80 and (csm_delta <= -1.0 or macro.get("is_bear")):
        # At ceiling with bearish micro flow -> Fade ceiling
        preferred_dir = -1
    elif dr_pos <= 0.20 and (csm_delta >= 1.0 or macro.get("is_bull")):
        # At floor with bullish micro flow -> Fade floor
        preferred_dir = 1
    elif macro.get("is_bear") and not macro.get("is_bull"):
        preferred_dir = -1
    elif macro.get("is_bull") and not macro.get("is_bear"):
        preferred_dir = 1
    else:
        bias_lbl = str(macro.get("trend_label") or macro.get("trend_compass") or "").upper()
        if "BEAR" in bias_lbl and "BULL" not in bias_lbl:
            preferred_dir = -1
        elif "BULL" in bias_lbl and "BEAR" not in bias_lbl:
            preferred_dir = 1
        else:
            preferred_dir = 0

    type_label_map = {
        "M1": "M1:SWEEP",
        "M1B": "M1B:SWEEP",
        "M2": "M2:PULLBACK",
        "M3": "M3:BREAKOUT",
        "M4": "M4:BASING"
    }

    candidates = []
    for s in standbys:
        s_lvl = float(s.get("price", 0.0))
        if s_lvl <= 0:
            continue
        dist_pips = abs(mid - s_lvl) / pip_val if pip_val > 0 else 0.0
        dist_atr = abs(mid - s_lvl) / atr_val if atr_val > 0 else 99.0
        s_dir = int(s.get("direction", 0) or 0)
        s_lbl = str(s.get("label", "")).upper()

        if s_dir == 1 or "BULL" in s_lbl or "RBS" in s_lbl or "BUY" in s_lbl:
            dir_tag = "BULL"
            dir_int = 1
        elif s_dir == -1 or "BEAR" in s_lbl or "SBR" in s_lbl or "SELL" in s_lbl:
            dir_tag = "BEAR"
            dir_int = -1
        else:
            dir_tag = "SETUP"
            dir_int = 0

        is_watch = bool(s.get("is_breakdown_watch", False))
        s_type = s.get("type", "")
        if is_watch:
            s_type_label = "SFR:WATCH"
        elif s_type == "M4":
            s_type_label = "M4:BASING" if "BASING" in s_lbl else "M4:RETEST"
        else:
            s_type_label = type_label_map.get(s_type, s_type or "SETUP")

        short_name = f"{s_type_label} {dir_tag}"
        st_val = str(s.get("status", "")).upper()
        is_active = any(k in st_val for k in ("ACTIVE", "TOUCH", "RETEST", "RECLAIM"))
        is_pro_trend = (preferred_dir == 0) or (dir_int == preferred_dir)
        is_confl = bool(s.get("is_confluence", False))

        target_p = float(s.get("target_price", 0.0) or 0.0)
        runway_dist = abs(target_p - s_lvl) if target_p > 0 else (1.5 * atr_val)
        runway_atr = runway_dist / max(atr_val, 1e-5)
        has_healthy_runway = (runway_atr >= 0.25)

        candidates.append({
            "name": short_name,
            "type": s_type,
            "dir": dir_tag,
            "dir_int": dir_int,
            "dist_pips": dist_pips,
            "dist_atr": dist_atr,
            "lvl": s_lvl,
            "target": target_p,
            "runway_atr": runway_atr,
            "has_healthy_runway": has_healthy_runway,
            "is_watch": is_watch,
            "is_active": is_active,
            "is_pro_trend": is_pro_trend,
            "is_confluence": is_confl,
            "standby": s
        })

    if not candidates:
        return {
            "name": "IDLE",
            "type": "",
            "dir": "NEUTRAL",
            "dir_int": 0,
            "dist_pips": 999.0,
            "dist_atr": 99.0,
            "lvl": 0.0,
            "target": 0.0,
            "is_confluence": False,
            "confluence_name": "",
            "extra_count": 0,
            "standby": None
        }

    # Proximity count (<= 1.5x ATR)
    near_setups = [c for c in candidates if c["dist_atr"] <= 1.5]
    extra_count = max(0, len(near_setups) - 1)

    # Multi-Tier Institutional Sort:
    # 0: Confluence first
    # 1: Pro-trend / Preferred direction over Counter-trend (0 if is_pro_trend else 1)
    # 2: Active physical touch/retest over pending (0 if is_active else 1)
    # 3: Actionable over passive watch (0 if not is_watch else 1)
    # 4: Healthy runway over blocked runway (0 if has_healthy_runway else 1)
    # 5: Distance in ATR (closest first, imminent setups prioritized)
    candidates.sort(key=lambda c: (
        0 if c["is_confluence"] else 1,
        0 if c["is_pro_trend"] else 1,
        0 if c["is_active"] else 1,
        1 if c["is_watch"] else 0,
        0 if c["has_healthy_runway"] else 1,
        c["dist_atr"]
    ))

    elected = dict(candidates[0])

    # Confluence fusion: >= 2 setups in same direction within <= 0.35x ATR
    is_confluence = elected["is_confluence"]
    confluence_name = ""
    if len(near_setups) >= 2 and not is_confluence:
        same_dir = [c for c in near_setups if c["dir"] == elected["dir"]]
        if len(same_dir) >= 2:
            min_lvl = min(c["lvl"] for c in same_dir)
            max_lvl = max(c["lvl"] for c in same_dir)
            if (max_lvl - min_lvl) <= 0.35 * atr_val:
                c_types = [c["type"] for c in same_dir]
                confluence_name = f"{'+'.join(c_types)} {elected['dir']}"
                is_confluence = True
                elected["name"] = confluence_name

    elected["is_confluence"] = is_confluence
    elected["confluence_name"] = confluence_name
    elected["extra_count"] = extra_count
    return elected


def detect_historical_triggers(
    df: Any,
    symbol: str,
    pip_size: float,
    point: float,
    lookback_bars: int = 200,
    macro: Optional[Dict[str, Any]] = None,
    c1: float = 0.0,
    f1: float = 0.0,
    atr_val: float = 0.0,
    zce_ladder: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Evaluates historical candlesticks to identify canonical 1:1 Engine Gate A+ triggers
    (M1A, M1B, M2, M3, M4) relative to Active Dealing Range, ZCE Runway, G3 Walls, and Net R:R Floor.
    Returns list of trigger markers with bar index, timestamp, price, strategy, direction, and gate telemetry.
    """
    if df is None or len(df) < 20:
        return []

    try:
        import numpy as np
        import pandas as pd
        from datetime import datetime
        from zoneinfo import ZoneInfo

        WIB_TZ = ZoneInfo("Asia/Jakarta")

        # Analyze using MacroEnvelopeEngine
        engine = MacroEnvelopeEngine()
        eval_df = df.tail(lookback_bars).copy().reset_index(drop=True)
        res = engine.analyze(eval_df, symbol=symbol, point_size=point, pip_size=pip_size)
        dr = res.visual_payload.get("dealing_range", {})
        ss = res.visual_payload.get("swing_structure", {})

        r_high = float(dr.get("range_high", 0.0) or 0.0)
        r_low = float(dr.get("range_low", 0.0) or 0.0)
        span = max(r_high - r_low, 1e-6)
        if r_high <= 0 or r_low <= 0 or span <= 1e-5:
            return []

        peaks = ss.get("peaks", [])
        troughs = ss.get("troughs", [])

        highs = eval_df["high"].values
        lows = eval_df["low"].values
        opens = eval_df["open"].values
        closes = eval_df["close"].values
        times = eval_df["time"].values
        n = len(closes)

        # EMA20, EMA50, ATR
        eval_df["ema20"] = eval_df["close"].ewm(span=20, adjust=False).mean()
        eval_df["ema50"] = eval_df["close"].ewm(span=50, adjust=False).mean()
        ema20 = eval_df["ema20"].values
        ema50 = eval_df["ema50"].values

        tr = np.maximum(highs[1:] - lows[1:], np.maximum(abs(highs[1:] - closes[:-1]), abs(lows[1:] - closes[:-1])))
        tr = np.insert(tr, 0, tr[0] if len(tr) > 0 else 0.002)
        atr_series = pd.Series(tr).rolling(14, min_periods=1).mean().values

        triggers: List[Dict[str, Any]] = []
        digits = 5 if point < 0.01 else 2

        # Effective macro boundaries
        eff_c1 = float(c1 or 0.0)
        eff_f1 = float(f1 or 0.0)
        ladder = zce_ladder or []

        # Determine inception timestamp of CURRENT Active Dealing Range
        # Only evaluate bars that formed strictly within the current dealing range lifecycle
        dr_start_time = int(dr.get("start_time", 0) or 0)
        if dr_start_time <= 0:
            t_hi = int(dr.get("high_time", 0) or 0)
            t_lo = int(dr.get("low_time", 0) or 0)
            if t_hi > 0 and t_lo > 0:
                dr_start_time = min(t_hi, t_lo)
            elif t_hi > 0:
                dr_start_time = t_hi
            elif t_lo > 0:
                dr_start_time = t_lo

        for i in range(15, n):
            c_time = int(times[i])

            # ── DEALING RANGE BOUNDARY FILTER: ONLY CURRENT ACTIVE DEALING RANGE ──
            if dr_start_time > 0 and c_time < dr_start_time:
                continue

            c_open = float(opens[i])
            c_high = float(highs[i])
            c_low = float(lows[i])
            c_close = float(closes[i])
            c_atr = max(float(atr_series[i]), 1e-6)
            c_rng = max(c_high - c_low, 1e-6)

            # ── GATE 1: SESSION WINDOW & DEAD ZONE GUARD ──
            dt = datetime.fromtimestamp(c_time, tz=WIB_TZ)
            h = dt.hour
            dow = dt.weekday()
            # Veto if weekend, Dead Zone (00:00-07:00 WIB), or Friday Night Freeze (>= 23:00 WIB)
            if dow in (5, 6) or (0 <= h < 7) or (dow == 4 and h >= 23):
                continue

            # Bar Dealing Range Position
            dr_pos = (c_close - r_low) / span
            dr_pos_pct = round(dr_pos * 100.0, 1)

            upper_wick = (c_high - max(c_open, c_close)) / c_rng
            lower_wick = (min(c_open, c_close) - c_low) / c_rng
            body_ratio = abs(c_close - c_open) / c_rng

            # Check prior peaks & troughs in preceding 25 bars
            prior_pks = [p["price"] for p in peaks if p.get("index", 0) < i and (i - p.get("index", 0)) <= 25]
            prior_trs = [t["price"] for t in troughs if t.get("index", 0) < i and (i - t.get("index", 0)) <= 25]

            cand_type = None
            cand_dir = 0
            entry_p = 0.0
            zone_name = ""
            reason_text = ""
            touches = 1

            # 1. M1A: UNIVERSAL LIQUIDITY SWEEP (Reversal at Range Extremes)
            if dr_pos >= 0.618 and upper_wick >= 0.30 and prior_pks:
                swept_pk = max(prior_pks)
                if c_high >= swept_pk and c_close < c_high:
                    cand_type = "M1A"
                    cand_dir = -1
                    entry_p = c_close
                    zone_name = "DEEP_PREMIUM"
                    reason_text = f"Swept High {swept_pk:.{digits}f} with {upper_wick*100:.0f}% Upper Wick at DR {dr_pos_pct}%"
            elif dr_pos <= 0.382 and lower_wick >= 0.30 and prior_trs:
                swept_tr = min(prior_trs)
                if c_low <= swept_tr and c_close > c_low:
                    cand_type = "M1A"
                    cand_dir = 1
                    entry_p = c_close
                    zone_name = "DEEP_DISCOUNT"
                    reason_text = f"Swept Low {swept_tr:.{digits}f} with {lower_wick*100:.0f}% Lower Wick at DR {dr_pos_pct}%"

            # 2. M1B: INTERNAL INDUCEMENT SWEEP (Mid-Range Trap)
            if not cand_type and 0.382 < dr_pos < 0.618 and (upper_wick >= 0.35 or lower_wick >= 0.35):
                if upper_wick >= 0.35 and prior_pks and c_high >= max(prior_pks):
                    swept_pk = max(prior_pks)
                    cand_type = "M1B"
                    cand_dir = -1
                    entry_p = c_close
                    zone_name = "SHALLOW_PREMIUM"
                    touches = sum(1 for j in range(max(0, i - 30), i + 1) if abs(highs[j] - swept_pk) <= 0.20 * c_atr)
                    reason_text = f"Internal Inducement Sweep High with {upper_wick*100:.0f}% Wick • Cluster {max(1, touches)}x at DR {dr_pos_pct}%"
                elif lower_wick >= 0.35 and prior_trs and c_low <= min(prior_trs):
                    swept_tr = min(prior_trs)
                    cand_type = "M1B"
                    cand_dir = 1
                    entry_p = c_close
                    zone_name = "SHALLOW_DISCOUNT"
                    touches = sum(1 for j in range(max(0, i - 30), i + 1) if abs(lows[j] - swept_tr) <= 0.20 * c_atr)
                    reason_text = f"Internal Inducement Sweep Low with {lower_wick*100:.0f}% Wick • Cluster {max(1, touches)}x at DR {dr_pos_pct}%"

            # 3. M2: TREND-ALIGNED PULLBACK (EMA Corridor Retest)
            if not cand_type:
                if dr_pos <= 0.500 and ema20[i] > ema50[i]:
                    ema_hi = max(ema20[i], ema50[i])
                    ema_lo = min(ema20[i], ema50[i])
                    if (c_low <= ema_hi + 0.15 * c_atr) and (c_close >= ema_lo - 0.20 * c_atr) and (lower_wick >= 0.20 or c_close > c_open):
                        cand_type = "M2"
                        cand_dir = 1
                        entry_p = c_close
                        zone_name = "DISCOUNT_CORRIDOR"
                        reason_text = f"Pullback Touch to EMA20/50 in Discount ({dr_pos_pct}%), Bullish Rebound"
                elif dr_pos >= 0.500 and ema20[i] < ema50[i]:
                    ema_hi = max(ema20[i], ema50[i])
                    ema_lo = min(ema20[i], ema50[i])
                    if (c_high >= ema_lo - 0.15 * c_atr) and (c_close <= ema_hi + 0.20 * c_atr) and (upper_wick >= 0.20 or c_close < c_open):
                        cand_type = "M2"
                        cand_dir = -1
                        entry_p = c_close
                        zone_name = "PREMIUM_CORRIDOR"
                        reason_text = f"Pullback Rally to EMA20/50 in Premium ({dr_pos_pct}%), Bearish Rejection"

            # 4. M3: BREAKOUT RETEST (Horizontal Key Level Retest)
            if not cand_type:
                for pk in prior_pks:
                    if abs(c_low - pk) <= 0.25 * c_atr and c_close > pk and (0.35 <= dr_pos <= 0.80):
                        cand_type = "M3"
                        cand_dir = 1
                        entry_p = pk
                        zone_name = "RBS_RETEST"
                        touches = sum(1 for j in range(max(0, i - 40), i + 1) if (abs(lows[j] - pk) <= 0.25 * c_atr or abs(highs[j] - pk) <= 0.25 * c_atr))
                        reason_text = f"Retest of Broken Resistance {pk:.{digits}f} (now RBS floor) • Touch #{max(1, touches)} at DR {dr_pos_pct}%"
                        break
                if not cand_type:
                    for tr_p in prior_trs:
                        if abs(c_high - tr_p) <= 0.25 * c_atr and c_close < tr_p and (0.20 <= dr_pos <= 0.65):
                            cand_type = "M3"
                            cand_dir = -1
                            entry_p = tr_p
                            zone_name = "SBR_RETEST"
                            touches = sum(1 for j in range(max(0, i - 40), i + 1) if (abs(highs[j] - tr_p) <= 0.25 * c_atr or abs(lows[j] - tr_p) <= 0.25 * c_atr))
                            reason_text = f"Retest of Broken Support {tr_p:.{digits}f} (now SBR ceiling) • Touch #{max(1, touches)} at DR {dr_pos_pct}%"
                            break

            # 5. M4: MOMENTUM EXPANSION SUPER-SHOCK
            if not cand_type and c_rng >= 1.4 * c_atr and body_ratio >= 0.65:
                if c_close > r_high and c_close > c_open:
                    cand_type = "M4"
                    cand_dir = 1
                    entry_p = c_close
                    zone_name = "RANGE_BREAKOUT"
                    reason_text = f"Super-Shock Momentum Expansion ({c_rng/c_atr:.1f}x ATR) above Range High {r_high:.{digits}f}"
                elif c_close < r_low and c_close < c_open:
                    cand_type = "M4"
                    cand_dir = -1
                    entry_p = c_close
                    zone_name = "RANGE_BREAKDOWN"
                    reason_text = f"Super-Shock Momentum Expansion ({c_rng/c_atr:.1f}x ATR) below Range Low {r_low:.{digits}f}"

            if not cand_type:
                continue

            # ── 1:1 ENGINE GATES VERIFICATION ──

            # Gate A: ZCE Fortress Runway Floor (>= 0.50x ATR to Opposing Wall)
            if cand_dir == 1:
                runway_target = eff_c1 if (eff_c1 > entry_p) else (entry_p + 1.5 * c_atr)
                runway_dist = (runway_target - entry_p) / c_atr
            else:
                runway_target = eff_f1 if (eff_f1 > 0 and eff_f1 < entry_p) else (entry_p - 1.5 * c_atr)
                runway_dist = (entry_p - runway_target) / c_atr

            if runway_dist < 0.50:
                continue  # Vetoed by Runway Deficit

            # Gate B: Collision Guard (M2) & Exhaustion Guard (M3)
            if cand_type == "M2":
                if cand_dir == 1 and (dr_pos >= 0.80 or (eff_c1 > 0 and (eff_c1 - entry_p) < 0.40 * c_atr)):
                    continue
                if cand_dir == -1 and (dr_pos <= 0.20 or (eff_f1 > 0 and (entry_p - eff_f1) < 0.40 * c_atr)):
                    continue
            elif cand_type == "M3":
                if cand_dir == 1 and dr_pos >= 0.85 and (eff_c1 > 0 and c_high <= eff_c1):
                    continue
                if cand_dir == -1 and dr_pos <= 0.15 and (eff_f1 > 0 and c_low >= eff_f1):
                    continue

            # Gate C: Local G3 Macro Wall Veto (The EURAUD Law)
            if ladder:
                collides_g3 = False
                for w in ladder:
                    w_price = float(w.get("price", 0.0) or 0.0)
                    tier_str = str(w.get("tier", "")).upper()
                    label_str = str(w.get("label", "")).upper()
                    is_g3 = ("G3" in tier_str) or ("G3" in label_str) or (w.get("is_macro_wall") is True)
                    if not is_g3:
                        continue
                    if cand_dir == 1 and w_price > entry_p and (w_price - entry_p) < 0.35 * c_atr:
                        collides_g3 = True
                        break
                    elif cand_dir == -1 and w_price < entry_p and (entry_p - w_price) < 0.35 * c_atr:
                        collides_g3 = True
                        break
                if collides_g3:
                    continue

            # Gate D: Risk & Net R:R Floor (SL >= 0.60x ATR, Net R:R >= 1.25)
            if cand_dir == 1:
                sl = entry_p - max(0.60 * c_atr, 15.0 * point)
                tp = runway_target
            else:
                sl = entry_p + max(0.60 * c_atr, 15.0 * point)
                tp = runway_target

            risk_dist = abs(entry_p - sl)
            reward_dist = abs(tp - entry_p)
            rr = reward_dist / max(risk_dist, 1e-5)

            if rr < 1.25:
                continue  # Vetoed by Net R:R Floor

            # Anti-clustering throttle: skip if same strategy & direction within past 3 bars
            direction_str = "BUY" if cand_dir == 1 else "SELL"
            recent_same = [t for t in triggers if t["type"] == cand_type and t["direction"] == direction_str and (i - t["bar_index"]) <= 3]
            if recent_same:
                continue

            bar_trigger = {
                "bar_index": i,
                "bar_age": n - 1 - i,
                "time": c_time,
                "price": round(entry_p, digits),
                "type": cand_type,
                "direction": direction_str,
                "dr_pos_pct": dr_pos_pct,
                "zone": zone_name,
                "label": cand_type,
                "touch_count": max(1, touches),
                "runway_atr": round(runway_dist, 2),
                "sl": round(sl, digits),
                "tp": round(tp, digits),
                "rr": round(rr, 2),
                "verdict": "8-GATE PASS [A+ VALID]",
                "reason": reason_text
            }
            triggers.append(bar_trigger)

        return triggers
    except Exception as e:
        logger.warning(f"[DASHBOARD] Error detecting historical triggers for {symbol}: {e}")
        return []


class CockpitDataEngine:
    """Singleton background engine that keeps real-time cache of MT5 & Quant Funnel."""

    def __init__(self):
        self._lock = threading.Lock()
        self.scanner: Optional[MarketScanner] = None
        self.macro_updated_ts: float = 0.0
        self.radar_scanned_ts: float = 0.0
        self.cached_overview: Dict[str, Any] = {}
        self.cached_symbol_data: Dict[str, Dict[str, Any]] = {}
        self._is_running = False

    def start(self):
        connector.initialize_mt5()
        dash_symbols = list(config.SCANNER_SYMBOLS)
        btc_cand = config._normalize_symbol_for_account(getattr(config, "WEEKEND_SYMBOL", "BTCUSD.c"))
        gold_cand = config._normalize_symbol_for_account(getattr(config, "GOLD_SYMBOL", "XAUUSD-ECNc"))
        clean_list = [s.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").upper() for s in dash_symbols]
        if "BTCUSD" not in clean_list:
            dash_symbols.append(btc_cand)
        if "XAUUSD" not in clean_list:
            dash_symbols.append(gold_cand)
        self.scanner = MarketScanner(symbols=dash_symbols)
        self._is_running = True
        t = threading.Thread(target=self._background_loop, daemon=True)
        t.start()
        print(f"[Cockpit Engine] Background observation worker started for {len(dash_symbols)} pairs (FX + BTCUSD + XAUUSD).")

    def _background_loop(self):
        """Refreshes MT5 macro context and 26-pair proximity every 5-8 seconds."""
        # Immediate fast seed for overview on startup
        try:
            self._build_overview_cache()
        except Exception:
            pass

        while self._is_running:
            try:
                now_ts = time.time()
                # Update macro context every 60s
                if (now_ts - self.macro_updated_ts) >= 60.0:
                    self.scanner.update_macro_context(mt5_connector=connector)
                    self.macro_updated_ts = now_ts

                # Fast radar scan every 8s
                if (now_ts - self.radar_scanned_ts) >= 8.0:
                    self.scanner.scan_fast_radar(mt5_connector=connector)
                    self.radar_scanned_ts = now_ts

                self._build_overview_cache()
            except Exception as e:
                logger.error(f"[Cockpit Engine Error] {e}", exc_info=True)
            time.sleep(2.5)

    def _build_overview_cache(self):
        """Builds proximity-sorted 26-pair overview and MT5 account stats."""
        now_wib = datetime.now(WIB)
        clock_str = now_wib.strftime("%H:%M:%S WIB • %d %b %Y")

        # 1. Account info
        acc = connector.get_account_info() or {}
        balance = float(acc.get("balance", 6000.0))
        equity = float(acc.get("equity", 6000.0))
        login = str(acc.get("login", "VTMarkets-Live 3"))

        # Open & closed positions
        open_pos = connector.get_all_open_positions() or []
        floating_pnl = sum(float(p.get("profit", 0.0)) for p in open_pos)
        closed_today = connector.get_closed_positions_today() or []
        daily_closed_pnl = sum(float(d.get("profit", 0.0)) for d in closed_today)

        open_symbols = set(p.get("symbol") for p in open_pos)

        # 2. Universe Proximity Analysis (26 Pairs + BTCUSD + XAUUSD)
        symbols = list(self.scanner.symbols) if (self.scanner and self.scanner.symbols) else list(config.SCANNER_SYMBOLS)
        btc_cand = config._normalize_symbol_for_account(getattr(config, "WEEKEND_SYMBOL", "BTCUSD.c"))
        gold_cand = config._normalize_symbol_for_account(getattr(config, "GOLD_SYMBOL", "XAUUSD-ECNc"))
        clean_list = [s.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").upper() for s in symbols]
        if "BTCUSD" not in clean_list:
            symbols.append(btc_cand)
        if "XAUUSD" not in clean_list:
            symbols.append(gold_cand)
        pairs_data = []

        for sym in symbols:
            valid_sym = connector.get_valid_trade_symbol(sym)
            clean_sym = sym.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").upper()
            macro = self.scanner.macro_cache.get(sym) or self.scanner.macro_cache.get(valid_sym) or {}
            strat = macro.get("strat_dir")

            tick = config.mt5.symbol_info_tick(valid_sym)
            si = config.mt5.symbol_info(valid_sym)
            digits = si.digits if si else (2 if ("BTC" in clean_sym or "XAU" in clean_sym) else 5)
            pt = si.point if si and si.point else (1.0 if "BTC" in clean_sym else (0.01 if "XAU" in clean_sym else (0.001 if "JPY" in clean_sym else 0.00001)))
            pip_div = 1 if ("BTC" in clean_sym or "XAU" in clean_sym) else (10 if digits in (3, 5) else 1)
            pip_val = pt * pip_div

            bid = float(tick.bid) if tick else 0.0
            ask = float(tick.ask) if tick else 0.0
            mid = (bid + ask) / 2.0 if (bid and ask) else 0.0

            atr_pts = float(macro.get("current_atr_pts") or macro.get("atr_pts") or 60.0)
            atr_val = atr_pts * pt if atr_pts > 0 else (60.0 * pt)

            # Extract Levels
            f1 = macro.get("immediate_floor_f1") or macro.get("floor_f1") or 0.0
            c1 = macro.get("immediate_ceiling_c1") or macro.get("ceiling_c1") or 0.0

            # Bias extraction: Explicit Higher-Timeframe Macro Trend (D1 + H4)
            if macro.get("is_bear") and not macro.get("is_bull"):
                bias = "HTF: BEAR"
            elif macro.get("is_bull") and not macro.get("is_bear"):
                bias = "HTF: BULL"
            else:
                bias_label = str(macro.get("trend_label") or macro.get("trend_compass") or "SIDEWAYS").upper()
                if "BEAR" in bias_label and "BULL" not in bias_label:
                    bias = "HTF: BEAR"
                elif "BULL" in bias_label and "BEAR" not in bias_label:
                    bias = "HTF: BULL"
                else:
                    bias = "HTF: FLAT"

            tactical_tag = str(macro.get("tactical_desc") or "")
            csm_delta = float(macro.get("csm_delta", 0.0) or 0.0)
            tier = getattr(strat, "action_tier", macro.get("action_tier", "FULL_ALLOW"))
            perm_label = macro.get("permission_state", "GO")

            # 1:1 Radar Standbys directly from MarketScanner
            standbys = self.scanner.get_radar_standbys(sym, mid, macro, pt, atr_val)

            dir_mem = getattr(self.scanner, "_symbol_directional_state", {}).get(clean_sym)
            dir_lock_val = int(dir_mem.get("dir", 0) or 0) if dir_mem else 0

            elected = _elect_primary_standby(
                standbys, macro, mid, pt, atr_val, pip_val, dir_lock=dir_lock_val
            )

            closest_name = elected["name"]
            closest_pips = elected["dist_pips"]
            closest_atr = elected["dist_atr"]
            closest_lvl = elected["lvl"]
            is_confluence = elected["is_confluence"]
            extra_count = elected["extra_count"]

            is_near = (closest_atr <= 1.0)
            dist_desc = f"{closest_pips:.1f} pips ({closest_atr:.2f}x ATR)" if closest_atr < 50 else ">50 pips (Idle)"

            # ZCE Station Runway Target Calculation
            c1_p = float(macro.get("immediate_ceiling_c1", macro.get("ceiling_c1", 0.0)) or 0.0)
            f1_p = float(macro.get("immediate_floor_f1", macro.get("floor_f1", 0.0)) or 0.0)
            c2_p = float(macro.get("ceiling_c2", 0.0) or 0.0)
            f2_p = float(macro.get("floor_f2", 0.0) or 0.0)
            struct_stage = str(macro.get("structural_stage") or "")

            c1_dist_pips = round((c1_p - mid) / pip_val) if (c1_p > 0 and mid > 0 and c1_p > mid) else None
            f1_dist_pips = round((mid - f1_p) / pip_val) if (f1_p > 0 and mid > 0 and mid > f1_p) else None

            # ZCE layer strength (P3/P4): jumlah sumber confluence di dinding immediate
            _zm = getattr(self.scanner, "_zce_maps", {}).get(valid_sym) or getattr(self.scanner, "_zce_maps", {}).get(sym)
            c1_confl = int(getattr(_zm, "immediate_ceiling_c1_confluence", 0) or 0)
            f1_confl = int(getattr(_zm, "immediate_floor_f1_confluence", 0) or 0)
            c1_grade = str(getattr(_zm, "immediate_ceiling_c1_grade", "") or "")
            f1_grade = str(getattr(_zm, "immediate_floor_f1_grade", "") or "")

            c1_text = f"C1: {c1_dist_pips}p" if c1_dist_pips is not None else "C1: —"
            f1_text = f"F1: {f1_dist_pips}p" if f1_dist_pips is not None else "F1: —"
            if c1_dist_pips is not None and c1_confl > 0:
                c1_text += f" •{c1_confl}x"
            if f1_dist_pips is not None and f1_confl > 0:
                f1_text += f" •{f1_confl}x"

            runway_station = "—"
            runway_pips = 0.0
            runway_atr = 0.0
            runway_badge = "RW: —"
            runway_text = "RW: —"

            if mid > 0 and pip_val > 0 and atr_val > 0:
                is_bull_orient = ("BULL" in bias) or (closest_name and ("BUY" in closest_name or "BULL" in closest_name))
                is_bear_orient = ("BEAR" in bias) or (closest_name and ("SELL" in closest_name or "BEAR" in closest_name))

                if is_bull_orient and not is_bear_orient:
                    target_wall = c2_p if ("ASCENDING_ABSORPTION" in struct_stage or (c1_p > 0 and mid >= c1_p and c2_p > c1_p)) else c1_p
                    wall_lbl = "C2" if target_wall == c2_p and c2_p > 0 else "C1"
                    if target_wall > 0:
                        runway_pips = (target_wall - mid) / pip_val
                        runway_atr = (target_wall - mid) / atr_val
                        runway_station = wall_lbl
                        runway_badge = f"→{wall_lbl}: {runway_pips:+.0f}p"
                        runway_text = f"→{wall_lbl} {runway_pips:+.1f}p ({runway_atr:.2f}x ATR)"
                elif is_bear_orient and not is_bull_orient:
                    target_wall = f2_p if ("DESCENDING_ABSORPTION" in struct_stage or (f1_p > 0 and mid <= f1_p and f2_p > 0 and f2_p < f1_p)) else f1_p
                    wall_lbl = "F2" if target_wall == f2_p and f2_p > 0 else "F1"
                    if target_wall > 0:
                        runway_pips = (mid - target_wall) / pip_val
                        runway_atr = (mid - target_wall) / atr_val
                        runway_station = wall_lbl
                        runway_badge = f"→{wall_lbl}: {runway_pips:+.0f}p"
                        runway_text = f"→{wall_lbl} {runway_pips:+.1f}p ({runway_atr:.2f}x ATR)"
                else:
                    dist_to_c1 = (c1_p - mid) if c1_p > 0 else 99999
                    dist_to_f1 = (mid - f1_p) if f1_p > 0 else 99999
                    if dist_to_c1 < dist_to_f1 and c1_p > 0:
                        runway_pips = dist_to_c1 / pip_val
                        runway_atr = dist_to_c1 / atr_val
                        runway_station = "C1"
                        runway_badge = f"C1: {runway_pips:.0f}p"
                        runway_text = f"C1 {runway_pips:.1f}p ({runway_atr:.2f}x ATR)"
                    elif f1_p > 0:
                        runway_pips = dist_to_f1 / pip_val
                        runway_atr = dist_to_f1 / atr_val
                        runway_station = "F1"
                        runway_badge = f"F1: {runway_pips:.0f}p"
                        runway_text = f"F1 {runway_pips:.1f}p ({runway_atr:.2f}x ATR)"

            # M4 Systemic Flow Shock & Dealing Range Extraction
            dr_pct = float(macro.get("dealing_range_pos", macro.get("dr_pos", 0.5)) or 0.5) * 100.0
            base_curr = clean_sym[:3]
            quote_curr = clean_sym[3:6]
            z_dict = getattr(self.scanner, "_m4_z_last", {})
            z_base = float(z_dict.get(base_curr, 0.0) or 0.0)
            z_quote = float(z_dict.get(quote_curr, 0.0) or 0.0)
            m4_st = getattr(self.scanner, "_m4_state", {}).get(clean_sym, {})
            m4_active_standby = next((s for s in standbys if s.get("type") == "M4"), None)
            m4_dominant_z = z_base if abs(z_base) >= abs(z_quote) else -z_quote
            m4_flow_dir = "BULL" if m4_dominant_z > 0 else "BEAR"

            # Layer 0 SFR Differentiation: Fresh Shock (>=config.M4_TRIGGER_Z) vs Flow Continuation (>=0.75)
            sfr_shock_z = float(getattr(config, "M4_TRIGGER_Z", 2.0))
            is_fresh_shock = (abs(z_base) >= sfr_shock_z or abs(z_quote) >= sfr_shock_z)
            has_active_ep = False
            if m4_st:
                for s_side in ("SELL", "BUY"):
                    s_d = m4_st.get(s_side, {})
                    if s_d.get("ep") is not None or s_d.get("pending") is not None:
                        has_active_ep = True
                        break
            is_continuation = (not is_fresh_shock) and (has_active_ep or m4_active_standby is not None) and (abs(m4_dominant_z) >= 0.75)
            m4_flow_state = "SHOCK" if is_fresh_shock else ("CONT" if is_continuation else "NONE")
            m4_has_shock = (m4_flow_state == "SHOCK")

            dir_mem = getattr(self.scanner, "_symbol_directional_state", {}).get(clean_sym)
            dir_locked = ("BUY" if dir_mem.get("dir", 0) == 1 else "SELL") if (dir_mem and dir_mem.get("dir", 0) != 0) else None
            b_box_info = macro.get("basing_box") or {}
            w_regime = macro.get("wave_regime_name") or "YOUNG_OSCILLATION"

            pairs_data.append({
                "symbol": sym,
                "clean_symbol": clean_sym,
                "active_setup": closest_name,
                "is_confluence": is_confluence,
                "extra_count": extra_count,
                "dist_pips": round(closest_pips, 1),
                "dist_atr": round(closest_atr, 2),
                "dist_desc": dist_desc,
                "is_near": is_near,
                "bias": bias,
                "tactical_tag": tactical_tag,
                "csm_delta": round(csm_delta, 2),
                "tier": tier,
                "perm_label": perm_label,
                "has_open_pos": (sym in open_symbols or valid_sym in open_symbols),
                "bid": bid,
                "ask": ask,
                "digits": digits,
                "m4_shock": m4_has_shock,
                "m4_flow_state": m4_flow_state,
                "m4_z": round(m4_dominant_z, 2),
                "m4_dir": m4_flow_dir,
                "dir_locked": dir_locked,
                "dr_pct": round(dr_pct, 1),
                "chamber_pips": round((c1_p - f1_p) / pip_val, 1) if (c1_p > 0 and f1_p > 0 and c1_p > f1_p) else 0.0,
                "chamber_atr": round((c1_p - f1_p) / atr_val, 2) if (c1_p > 0 and f1_p > 0 and c1_p > f1_p and atr_val > 0) else 0.0,
                "chamber_text": f"CH: {round((c1_p - f1_p) / pip_val, 1)}p ({round((c1_p - f1_p) / atr_val, 2)}x)" if (c1_p > 0 and f1_p > 0 and c1_p > f1_p and atr_val > 0) else "CH: —",
                "runway_badge": runway_badge,
                "runway_text": runway_text,
                "runway_station": runway_station,
                "runway_pips": round(runway_pips, 1),
                "runway_atr": round(runway_atr, 2),
                "c1_text": c1_text,
                "f1_text": f1_text,
                "c1_pips": c1_dist_pips,
                "f1_pips": f1_dist_pips,
                "c1_confluence": c1_confl,
                "f1_confluence": f1_confl,
                "c1_grade": c1_grade,
                "f1_grade": f1_grade,
                "basing_box": b_box_info,
                "wave_regime": w_regime,
                "is_paper_only": config.is_paper_only(sym),
                "w1_slope_ceiling": getattr(macro.get("strat_dir"), "w1_slope_ceiling", None),
                "w1_secular_regime": getattr(macro.get("strat_dir"), "w1_secular_regime", "SECULAR_RANGE"),
                "w1_intermediate_regime": getattr(macro.get("strat_dir"), "w1_intermediate_regime", "NEUTRAL_OSCILLATION"),
                "w1_horizon_conflict": getattr(macro.get("strat_dir"), "htf_horizon_conflict", False),
                "w1_lower_highs": getattr(macro.get("strat_dir"), "w1_lower_highs", [])
            })

        # Stable sorting by Base Currency Group: EUR, GBP, AUD, USD, CHF, CAD, NZD
        curr_order = ["EUR", "GBP", "AUD", "USD", "CHF", "CAD", "NZD"]
        def _get_pair_sort_key(p):
            clean = p.get("clean_symbol", "")
            base = clean[:3]
            quote = clean[3:6]
            try:
                base_idx = curr_order.index(base)
            except ValueError:
                base_idx = 99
            # Utamakan quote USD di depan masing-masing base group (misal EURUSD, GBPUSD)
            is_usd_quote = 0 if quote == "USD" else 1
            return (base_idx, is_usd_quote, clean)

        pairs_data.sort(key=_get_pair_sort_key)

        # 3. CBSS Currency Basket Exposure & Runway Leaderboard Calculation
        cbss_matrix = {}
        max_concurrency_cap = int(getattr(config, "CBSS_MAX_BASKET_CONCURRENCY", 2))
        pending_orders_all = connector.get_pending_orders() or []
        all_active_tickets = list(open_pos) + list(pending_orders_all)

        # A. Hitung eksposur terbuka per-mata uang (LONG / SHORT)
        currency_exposure = {c: {"long": 0, "short": 0, "pairs_long": [], "pairs_short": []} for c in CURRENCIES}
        for item in all_active_tickets:
            p_sym = getattr(item, "symbol", "") if hasattr(item, "symbol") else item.get("symbol", "")
            p_csym = cbss_clean_symbol(p_sym)
            if not p_csym or "BTC" in p_csym or "XAU" in p_csym:
                continue
            base, quote = get_pair_currencies(p_csym)
            if not base or not quote:
                continue

            p_type = getattr(item, "type", None) if hasattr(item, "type") else item.get("type", None)
            is_buy = (p_type == 0) or ("BUY" in str(p_type).upper())
            p_dir = 1 if is_buy else -1

            # Long Base / Short Quote
            if is_buy:
                if base in currency_exposure:
                    currency_exposure[base]["long"] += 1
                    currency_exposure[base]["pairs_long"].append(p_csym)
                if quote in currency_exposure:
                    currency_exposure[quote]["short"] += 1
                    currency_exposure[quote]["pairs_short"].append(p_csym)
            else:
                if base in currency_exposure:
                    currency_exposure[base]["short"] += 1
                    currency_exposure[base]["pairs_short"].append(p_csym)
                if quote in currency_exposure:
                    currency_exposure[quote]["long"] += 1
                    currency_exposure[quote]["pairs_long"].append(p_csym)

        # B. Hitung Runway Ranking dan G3 Veto per-mata uang
        m_cache = self.scanner.macro_cache if (self.scanner and hasattr(self.scanner, "macro_cache")) else {}
        baskets_summary = []
        for c in CURRENCIES:
            c_pairs = BASKETS.get(c, [])
            exp_info = currency_exposure.get(c, {"long": 0, "short": 0, "pairs_long": [], "pairs_short": []})
            is_long_saturated = (exp_info["long"] >= max_concurrency_cap)
            is_short_saturated = (exp_info["short"] >= max_concurrency_cap)

            # Evaluasi runway kandidat dengan Session-Aware Multi-Tier Ranking
            curr_h_wib = now_wib.hour
            candidates_eval = []
            for cp in c_pairs:
                base, quote = get_pair_currencies(cp)
                orient_dir = 1 if c == base else -1
                rw_info = calculate_pair_runway(cp, orient_dir, m_cache)
                is_g3_blocked, veto_reason = is_pair_blocked_by_g3_wall(cp, orient_dir, m_cache)
                is_sess_ok = is_symbol_allowed_for_session(cp, curr_h_wib)
                candidates_eval.append({
                    "pair": cp,
                    "direction": "BUY" if orient_dir == 1 else "SELL",
                    "runway_atr": rw_info.get("runway_atr", 0.0),
                    "target_wall": rw_info.get("target_wall_price", 0.0),
                    "target_grade": rw_info.get("target_wall_grade", "GRADE_1_MICRO"),
                    "is_g3_blocked": is_g3_blocked,
                    "veto_reason": veto_reason,
                    "is_session_allowed": is_sess_ok
                })

            # Multi-Tier Sorting: Session-Allowed > Clean Wall > Highest Runway
            candidates_eval.sort(
                key=lambda x: (
                    1 if x.get("is_session_allowed", True) else 0,
                    0 if x.get("is_g3_blocked", False) else 1,
                    x.get("runway_atr", 0.0)
                ),
                reverse=True
            )
            top_candidates = candidates_eval[:2]
            top_candidate = top_candidates[0] if top_candidates else None

            # BSSI Saturation calculation
            bssi_long, bssi_l_col, bssi_l_tot = calculate_basket_saturation_index(c, 1, m_cache)
            bssi_short, bssi_s_col, bssi_s_tot = calculate_basket_saturation_index(c, -1, m_cache)

            # Basket Champion selection (Bilateral Composite)
            champ_long = select_basket_champion(c, 1, m_cache, hour_wib=curr_h_wib)
            champ_short = select_basket_champion(c, -1, m_cache, hour_wib=curr_h_wib)

            baskets_summary.append({
                "currency": c,
                "exposure_long": exp_info["long"],
                "exposure_short": exp_info["short"],
                "pairs_long": exp_info["pairs_long"],
                "pairs_short": exp_info["pairs_short"],
                "is_long_saturated": is_long_saturated,
                "is_short_saturated": is_short_saturated,
                "bssi_long": bssi_long,
                "bssi_short": bssi_short,
                "champion_long": champ_long,
                "champion_short": champ_short,
                "max_cap": max_concurrency_cap,
                "top_candidate": top_candidate,
                "top_candidates": top_candidates,
                "all_candidates": candidates_eval
            })

        cbss_matrix = {
            "enabled": getattr(config, "ENABLE_CBSS", True),
            "max_concurrency_cap": max_concurrency_cap,
            "g3_threshold_atr": getattr(config, "CBSS_G3_BARRIER_THRESHOLD_ATR", 0.35),
            "saturation_threshold": getattr(config, "CBSS_SATURATION_THRESHOLD", 0.70),
            "baskets": baskets_summary
        }

        # Confluence Timing Directive
        timing_info = evaluate_session_confluence_timing("GBPUSD-ECN", now_wib.hour)

        with self._lock:
            try:
                from src.analytics.shadow_tracker import shadow_tracker
                shadow_data = shadow_tracker.get_performance_summary()
            except Exception:
                shadow_data = {}

            self.cached_overview = {
                "account": {
                    "login": login,
                    "balance": balance,
                    "equity": equity,
                    "floating_pnl": floating_pnl,
                    "daily_closed_pnl": daily_closed_pnl,
                    "open_count": len(open_pos),
                },
                "timestamp_wib": clock_str,
                "confluence_timing": timing_info,
                "pairs": pairs_data,
                "cbss_matrix": cbss_matrix,
                "shadow_radar": shadow_data
            }

    def get_symbol_detail(self, symbol: str, timeframe_str: str = "H1") -> Dict[str, Any]:
        """Generates exhaustive payload for single pair (Candles, ZCE Walls, Standbys, 7-Gate)."""
        valid_sym = connector.get_valid_trade_symbol(symbol)
        clean_sym = symbol.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").upper()
        macro = self.scanner.macro_cache.get(symbol) or self.scanner.macro_cache.get(valid_sym) or {}
        strat = macro.get("strat_dir")

        si = config.mt5.symbol_info(valid_sym)
        digits = si.digits if si else (2 if "BTC" in clean_sym else 5)
        pt = si.point if si and si.point else (1.0 if "BTC" in clean_sym else (0.001 if "JPY" in clean_sym else 0.00001))
        pip_div = 1 if "BTC" in clean_sym else (10 if digits in (3, 5) else 1)
        pip_val = pt * pip_div

        tick = config.mt5.symbol_info_tick(valid_sym)
        bid = float(tick.bid) if tick else 0.0
        ask = float(tick.ask) if tick else 0.0
        mid = (bid + ask) / 2.0 if (bid and ask) else 0.0
        spread_pts = int(round((ask - bid) / pt)) if pt > 0 else 20
        atr_pts = float(macro.get("current_atr_pts") or macro.get("atr_pts") or 60.0)
        atr_val = atr_pts * pt if atr_pts > 0 else (60.0 * pt)

        # 1. Fetch Candlesticks
        tf_map = {
            "H4": config.mt5.TIMEFRAME_H4,
            "H1": config.mt5.TIMEFRAME_H1,
            "M30": config.mt5.TIMEFRAME_M30,
            "M5": config.mt5.TIMEFRAME_M5
        }
        mt5_tf = tf_map.get(timeframe_str.upper(), config.mt5.TIMEFRAME_H1)
        num_bars = 60 if timeframe_str.upper() == "M5" else (180 if timeframe_str.upper() == "M30" else (120 if timeframe_str.upper() == "H4" else 450))

        rates = config.mt5.copy_rates_from_pos(valid_sym, mt5_tf, 0, num_bars + 50)
        candles = []
        strat_audit_markers = []
        if rates is not None and len(rates) > 0:
            import pandas as pd
            from src.indicators.wave_regime import classify_wave_regimes_series
            df = pd.DataFrame(rates)
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

            tf_hours = 4.0 if timeframe_str.upper() == "H4" else (1.0 if timeframe_str.upper() == "H1" else (0.5 if timeframe_str.upper() == "M30" else 5.0 / 60.0))
            wave_series = classify_wave_regimes_series(
                highs=df['high'].tolist(),
                lows=df['low'].tolist(),
                closes=df['close'].tolist(),
                timeframe_hours=tf_hours
            )

            # Keep requested window
            tail_df = df.tail(num_bars)
            tail_indices = tail_df.index.tolist()

            for orig_idx, (_, r) in zip(tail_indices, tail_df.iterrows()):
                c_time = int(r['time'])
                c_dt = datetime.fromtimestamp(c_time, tz=WIB)
                c_sess_info = _get_session_info(c_dt, symbol)
                c_w_info = wave_series[orig_idx] if orig_idx < len(wave_series) else {}

                c_close = float(r['close'])
                c_ema20 = float(r['ema20'])
                c_ema50 = float(r['ema50'])

                candles.append({
                    "time": c_time, # epoch seconds
                    "open": round(float(r['open']), digits),
                    "high": round(float(r['high']), digits),
                    "low": round(float(r['low']), digits),
                    "close": round(c_close, digits),
                    "ema20": round(c_ema20, digits),
                    "ema50": round(c_ema50, digits),
                    "ema200": round(float(r['ema200']), digits),
                    "session": c_sess_info["name"],
                    "session_type": c_sess_info["type"],
                    "session_status": c_sess_info["status"],
                    "session_label": c_sess_info["label"],
                    "session_color": c_sess_info["color"],
                    "session_border": c_sess_info["border_color"],
                    "regime": c_w_info.get("regime", "YOUNG_OSCILLATION"),
                    "range_age_hours": c_w_info.get("range_age_hours", 0.0),
                    "sqz_on": c_w_info.get("sqz_on", False),
                    "sqz_bars": c_w_info.get("sqz_bars", 0)
                })

        # 2. Multi-Horizon ZCE Fortress Ladder (Consolidated & Proximity-Clamped)
        zm = getattr(self.scanner, "_zce_maps", {}).get(valid_sym)
        if zm is None and hasattr(self.scanner, "_compute_zce_map_for"):
            try:
                zm = self.scanner._compute_zce_map_for(valid_sym, mt5_connector=connector)
            except Exception:
                zm = None

        if candles:
            c_min_lo = min(c["low"] for c in candles)
            c_max_hi = max(c["high"] for c in candles)
            # Expand viewport clamp to 3.5 * atr_val (min 250 pips) so macro W1/D1 fortresses remain visible
            vp_margin = max(3.5 * atr_val, 250.0 * pip_val)
            v_lo = c_min_lo - vp_margin
            v_hi = c_max_hi + vp_margin
        else:
            v_lo = mid - 5.0 * atr_val
            v_hi = mid + 5.0 * atr_val

        zce_ladder = _consolidate_zce_zones(zm, mid, v_lo, v_hi, atr_val, pip_val, digits)

        # Baseline fallback for F1/F2 and C1/C2: Asymmetric Per-Side Injection (RFC 11 & MSE Confluence)
        f1 = macro.get("immediate_floor_f1") or macro.get("floor_f1")
        c1 = macro.get("immediate_ceiling_c1") or macro.get("ceiling_c1")

        layered_flrs = getattr(strat, "layered_floors", []) or []
        layered_ceils = getattr(strat, "layered_ceilings", []) or []

        f2 = getattr(strat, "deep_floor_f2", None)
        if f2 is None and len(layered_flrs) > 1:
            f2 = layered_flrs[1].get("price") if isinstance(layered_flrs[1], dict) else layered_flrs[1]
        elif f2 is None and len(layered_flrs) == 1:
            f2 = layered_flrs[0].get("price") if isinstance(layered_flrs[0], dict) else layered_flrs[0]

        c2 = getattr(strat, "deep_ceiling_c2", None)
        if c2 is None and len(layered_ceils) > 1:
            c2 = layered_ceils[1].get("price") if isinstance(layered_ceils[1], dict) else layered_ceils[1]
        elif c2 is None and len(layered_ceils) == 1:
            c2 = layered_ceils[0].get("price") if isinstance(layered_ceils[0], dict) else layered_ceils[0]

        # Collect candidate floors from ZCE ladder and MSE baseline
        raw_floors = [dict(w) for w in (zce_ladder or []) if w.get("type") == "floor" and w.get("price", 0.0) < mid]
        if f1 and float(f1) < mid:
            raw_floors.append({
                "price": round(float(f1), digits),
                "band_low": round(float(f1), digits),
                "band_high": round(float(f1), digits),
                "type": "floor",
                "tier": "F1",
                "label": f"F1 [MSE] {float(f1):.{digits}f} (Support Wall)",
                "grade": macro.get("f1_reaction_grade", "GRADE_2_INTERMEDIATE"),
                "score": 4.5,
                "tfs": ["H1", "D1"],
                "kinds": ["MSE_BASE", "MACRO_SWING"],
                "sources": ["MSE Structural SBR/RBS (D1)", "Macro Swing Low (H1)"],
                "confluences": "MSE Structural SBR/RBS (D1) • Macro Swing Low (H1)",
                "timeframes": "H1+D1",
                "confluence": 2,
                "num_sources": 2,
                "tag": "BASELINE_FLOOR"
            })
        if f2 and float(f2) < mid:
            raw_floors.append({
                "price": round(float(f2), digits),
                "band_low": round(float(f2), digits),
                "band_high": round(float(f2), digits),
                "type": "floor",
                "tier": "F2",
                "label": f"F2 [MSE] {float(f2):.{digits}f} (Deep Support)",
                "grade": "GRADE_2_INTERMEDIATE",
                "score": 3.8,
                "tfs": ["D1"],
                "kinds": ["MSE_BASE"],
                "sources": ["MSE Structural SBR/RBS (D1)"],
                "confluences": "MSE Structural SBR/RBS (D1)",
                "timeframes": "D1",
                "confluence": 1,
                "num_sources": 1,
                "tag": "BASELINE_DEEP_FLOOR"
            })

        tf_upper = timeframe_str.upper()
        tf_scale = 0.8 if tf_upper == "M30" else (0.4 if tf_upper == "M5" else 1.0)
        pip_floor = 8.0 * pip_val
        pip_thr = max(pip_floor, min(15.0 * pip_val, 0.75 * atr_val))
        proximity_thr = max(0.35 * atr_val * tf_scale, pip_thr)

        def _elect_display_ladder(merged_items: List[Dict[str, Any]], is_ceil: bool, limit: int = 4) -> List[Dict[str, Any]]:
            if not merged_items:
                return []
            # 100% Pure sequential progression outward from live price
            return list(merged_items[:limit])

        # Sort floors strictly descending (highest price first, i.e. closest to mid first)
        raw_floors.sort(key=lambda x: -x["price"])
        merged_floors: List[Dict[str, Any]] = []
        for fl in raw_floors:
            matched = False
            for mf in merged_floors:
                if abs(fl["price"] - mf["price"]) <= proximity_thr:
                    matched = True
                    mf["band_low"] = min(mf.get("band_low", mf["price"]), fl.get("band_low", fl["price"]))
                    mf["band_high"] = max(mf.get("band_high", mf["price"]), fl.get("band_high", fl["price"]))
                    # Accumulate confluences & sources
                    if fl.get("sources"):
                        mf_src = mf.setdefault("sources", [])
                        for s in fl["sources"]:
                            if s not in mf_src:
                                mf_src.append(s)
                    if fl.get("tfs"):
                        mf_tfs = mf.setdefault("tfs", [])
                        for t in fl["tfs"]:
                            if t not in mf_tfs:
                                mf_tfs.append(t)
                    if fl.get("kinds"):
                        mf_kinds = mf.setdefault("kinds", [])
                        for k in fl["kinds"]:
                            if k not in mf_kinds:
                                mf_kinds.append(k)

                    eff_confl = max(mf.get("confluence", 0), fl.get("confluence", 0), len(mf.get("sources", [])))
                    mf["confluence"] = eff_confl
                    mf["num_sources"] = eff_confl
                    if mf.get("sources"):
                        mf["confluences"] = " • ".join(mf["sources"][:4])
                    if mf.get("tfs"):
                        mf["timeframes"] = "+".join(sorted(mf["tfs"]))

                    if fl.get("score", 0.0) > mf.get("score", 0.0) or (fl.get("grade") == "GRADE_3_MACRO" and mf.get("grade") != "GRADE_3_MACRO"):
                        mf["price"] = fl["price"]
                        mf["label"] = fl.get("label", mf.get("label"))
                        mf["grade"] = fl.get("grade", mf.get("grade"))
                        mf["score"] = max(mf.get("score", 0.0), fl.get("score", 0.0))
                        mf["tf_max"] = fl.get("tf_max", mf.get("tf_max", ""))
                        mf["horizon_max"] = int(fl.get("horizon_max", mf.get("horizon_max", 0)))
                        mf["at_price"] = bool(fl.get("at_price", mf.get("at_price", False)))
                    break
            if not matched:
                merged_floors.append(dict(fl))

        merged_floors.sort(key=lambda x: -x["price"])

        # Monotonically assign tiers F1, F2, F3... by distance to mid with macro reservation
        selected_floors = _elect_display_ladder(merged_floors, is_ceil=False, limit=4)
        zce_floors = []
        for idx, fl in enumerate(selected_floors):
            tier_name = f"F{idx + 1}"
            fl_copy = dict(fl)
            fl_copy["tier"] = tier_name
            orig_label = fl_copy.get("label", "")
            parts = orig_label.split(" ", 1)
            if len(parts) == 2 and (parts[0].startswith("F") or parts[0].startswith("FLR")):
                fl_copy["label"] = f"{tier_name} {parts[1]}"
            elif not orig_label:
                fl_copy["label"] = f"{tier_name} {fl_copy['price']:.{digits}f}"
            zce_floors.append(fl_copy)

        # Collect candidate ceilings from ZCE ladder and MSE baseline
        raw_ceils = [dict(w) for w in (zce_ladder or []) if w.get("type") == "ceiling" and w.get("price", 0.0) > mid]
        if c1 and float(c1) > mid:
            raw_ceils.append({
                "price": round(float(c1), digits),
                "band_low": round(float(c1), digits),
                "band_high": round(float(c1), digits),
                "type": "ceiling",
                "tier": "C1",
                "label": f"C1 [MSE] {float(c1):.{digits}f} (Resistance Wall)",
                "grade": macro.get("c1_reaction_grade", "GRADE_2_INTERMEDIATE"),
                "score": 4.5,
                "tfs": ["H1", "D1"],
                "kinds": ["MSE_BASE", "MACRO_SWING"],
                "sources": ["MSE Structural SBR/RBS (D1)", "Macro Swing High (H1)"],
                "confluences": "MSE Structural SBR/RBS (D1) • Macro Swing High (H1)",
                "timeframes": "H1+D1",
                "confluence": 2,
                "num_sources": 2,
                "tag": "BASELINE_CEIL"
            })
        if c2 and float(c2) > mid:
            raw_ceils.append({
                "price": round(float(c2), digits),
                "band_low": round(float(c2), digits),
                "band_high": round(float(c2), digits),
                "type": "ceiling",
                "tier": "C2",
                "label": f"C2 [MSE] {float(c2):.{digits}f} (Deep Resistance)",
                "grade": "GRADE_2_INTERMEDIATE",
                "score": 3.8,
                "tfs": ["D1"],
                "kinds": ["MSE_BASE"],
                "sources": ["MSE Structural SBR/RBS (D1)"],
                "confluences": "MSE Structural SBR/RBS (D1)",
                "timeframes": "D1",
                "confluence": 1,
                "num_sources": 1,
                "tag": "BASELINE_DEEP_CEIL"
            })

        # Sort ceilings strictly ascending (lowest price first, i.e. closest to mid first)
        raw_ceils.sort(key=lambda x: x["price"])
        merged_ceils: List[Dict[str, Any]] = []
        for ce in raw_ceils:
            matched = False
            for mc in merged_ceils:
                if abs(ce["price"] - mc["price"]) <= proximity_thr:
                    matched = True
                    mc["band_low"] = min(mc.get("band_low", mc["price"]), ce.get("band_low", ce["price"]))
                    mc["band_high"] = max(mc.get("band_high", mc["price"]), ce.get("band_high", ce["price"]))
                    # Accumulate confluences & sources
                    if ce.get("sources"):
                        mc_src = mc.setdefault("sources", [])
                        for s in ce["sources"]:
                            if s not in mc_src:
                                mc_src.append(s)
                    if ce.get("tfs"):
                        mc_tfs = mc.setdefault("tfs", [])
                        for t in ce["tfs"]:
                            if t not in mc_tfs:
                                mc_tfs.append(t)
                    if ce.get("kinds"):
                        mc_kinds = mc.setdefault("kinds", [])
                        for k in ce["kinds"]:
                            if k not in mc_kinds:
                                mc_kinds.append(k)

                    eff_confl = max(mc.get("confluence", 0), ce.get("confluence", 0), len(mc.get("sources", [])))
                    mc["confluence"] = eff_confl
                    mc["num_sources"] = eff_confl
                    if mc.get("sources"):
                        mc["confluences"] = " • ".join(mc["sources"][:4])
                    if mc.get("tfs"):
                        mc["timeframes"] = "+".join(sorted(mc["tfs"]))

                    if ce.get("score", 0.0) > mc.get("score", 0.0) or (ce.get("grade") == "GRADE_3_MACRO" and mc.get("grade") != "GRADE_3_MACRO"):
                        mc["price"] = ce["price"]
                        mc["label"] = ce.get("label", mc.get("label"))
                        mc["grade"] = ce.get("grade", mc.get("grade"))
                        mc["score"] = max(mc.get("score", 0.0), ce.get("score", 0.0))
                        mc["tf_max"] = ce.get("tf_max", mc.get("tf_max", ""))
                        mc["horizon_max"] = int(ce.get("horizon_max", mc.get("horizon_max", 0)))
                        mc["at_price"] = bool(ce.get("at_price", mc.get("at_price", False)))
                    break
            if not matched:
                merged_ceils.append(dict(ce))

        merged_ceils.sort(key=lambda x: x["price"])

        # Monotonically assign tiers C1, C2, C3... by distance to mid with macro reservation
        selected_ceils = _elect_display_ladder(merged_ceils, is_ceil=True, limit=4)
        zce_ceils = []
        for idx, ce in enumerate(selected_ceils):
            tier_name = f"C{idx + 1}"
            ce_copy = dict(ce)
            ce_copy["tier"] = tier_name
            orig_label = ce_copy.get("label", "")
            parts = orig_label.split(" ", 1)
            if len(parts) == 2 and (parts[0].startswith("C") or parts[0].startswith("CEIL")):
                ce_copy["label"] = f"{tier_name} {parts[1]}"
            elif not orig_label:
                ce_copy["label"] = f"{tier_name} {ce_copy['price']:.{digits}f}"
            zce_ceils.append(ce_copy)

        zce_walls = zce_floors + zce_ceils
        zce_walls.sort(key=lambda x: x["price"])
        zce_ladder = list(zce_walls)

        # Detect Historical Strategy Audit Triggers (M1..M4) with 1:1 Quantitative Engine Gates
        try:
            strat_audit_markers = detect_historical_triggers(
                df=tail_df,
                symbol=valid_sym,
                pip_size=pip_val,
                point=pt,
                lookback_bars=num_bars,
                macro=macro,
                c1=float(c1 or 0.0),
                f1=float(f1 or 0.0),
                atr_val=float(atr_val or 0.0),
                zce_ladder=zce_ladder
            )
        except Exception as e:
            logger.warning(f"[DASHBOARD] Gagal deteksi 1:1 historical triggers untuk {symbol}: {e}")

        # 3. M1..M4 Reticles directly from MarketScanner 1:1 API
        m_standbys = self.scanner.get_radar_standbys(symbol, mid, macro, pt, atr_val)

        # 4. Evaluate 8-Gate Inspection Matrix
        gates = self._evaluate_8_gates(symbol, valid_sym, macro, strat, mid, spread_pts, atr_val, pt)

        # 5. Open Positions & Pending Orders for this symbol
        open_pos = []
        pos_state_file = os.path.join(ROOT, "data", "position_manager_state.json")
        pos_state = {}
        if os.path.exists(pos_state_file):
            try:
                with open(pos_state_file, "r") as f:
                    pos_state = json.load(f)
            except Exception:
                pos_state = {}
        be_set = set(pos_state.get("break_even_tickets", []))
        partial_set = set(pos_state.get("partial_closed_tickets", []))
        trail_set = set(pos_state.get("trailing_active_tickets", []))

        for p in connector.get_all_open_positions() or []:
            if p.get("symbol") in (symbol, valid_sym):
                t_id = p.get("ticket")
                p_type = p.get("type")
                p_dir = p.get("direction")
                type_str = "BUY" if (p_type in (0, "BUY") or p_dir == "BUY") else "SELL"
                p_comm = (p.get("comment") or "").upper()
                is_m4_pos = "SYSTEM" in p_comm

                # Dynamic Management Badge
                if is_m4_pos:
                    if t_id in be_set:
                        mgt_badge = "M4 BEP LOCKED (+15 pts)"
                    else:
                        mgt_badge = "M4 FULL RUN (BEP @ 70% TP)"
                elif t_id in trail_set:
                    mgt_badge = "TRAILING ACTIVE (Stage 2)"
                elif t_id in be_set:
                    mgt_badge = "BEP LOCKED (+15 pts)"
                elif t_id in partial_set:
                    mgt_badge = "PARTIAL TP1 (50% Closed)"
                else:
                    mgt_badge = "ACTIVE BREATHING (Stage 1)"

                # Dynamic Pre-rollover distance
                sl_val = p.get("sl") or 0.0
                curr_price = p.get("current_price") or p.get("price_open") or 0.0
                if sl_val > 0 and curr_price > 0 and pt > 0:
                    dist_pts = int(abs(curr_price - sl_val) / pt)
                    roll_str = f"Risk ({dist_pts} pts)" if dist_pts <= 180 else f"Safe ({dist_pts} pts)"
                else:
                    roll_str = "Safe (>180 pts)"

                # Dynamic CSM shift telemetry for bailout audit
                csm_status = "—"
                try:
                    from src.analytics.currency_strength import get_csm_delta_for_symbol
                    from src.analytics.position_manager import _load_telemetry
                    csm_curr = get_csm_delta_for_symbol(symbol)
                    t_data = _load_telemetry()
                    t_rec = t_data.get("trades", {}).get(str(t_id), {})
                    csm_o = t_rec.get("csm_delta_open")
                    if csm_o is not None:
                        shift_v = round(csm_curr - csm_o, 2)
                        csm_status = f"{shift_v:+.2f} (Now: {csm_curr:+.2f})"
                        if abs(shift_v) >= 2.5:
                            csm_status += " [BAILOUT RISK]"
                    else:
                        csm_status = f"Now: {csm_curr:+.2f}"
                except Exception:
                    pass

                open_pos.append({
                    "ticket": t_id,
                    "type_str": type_str,
                    "volume": p.get("volume"),
                    "price_open": p.get("price_open"),
                    "sl": p.get("sl"),
                    "tp": p.get("tp"),
                    "profit": float(p.get("profit", 0.0)),
                    "mgt_badge": mgt_badge,
                    "rollover_dist": roll_str,
                    "csm_shift": csm_status
                })

        pending_orders = []
        for o in connector.get_pending_orders() or []:
            if o.get("symbol") in (symbol, valid_sym):
                o_type = o.get("type", 2)
                type_label = "BUY LIMIT" if o_type == 2 else ("SELL LIMIT" if o_type == 3 else "PENDING")
                pending_orders.append({
                    "ticket": o.get("ticket"),
                    "type_str": type_label,
                    "volume": o.get("volume_initial"),
                    "price_open": o.get("price_open"),
                    "sl": o.get("sl"),
                    "tp": o.get("tp")
                })

        # 6. Telemetry for Tab 2 (Extracted directly from 1:1 Radar Standbys)
        # Pre-compute M4 Systemic Flow Shock state for telemetry & payload
        base_curr = clean_sym[:3]
        quote_curr = clean_sym[3:6]
        z_dict = getattr(self.scanner, "_m4_z_last", {})
        z_base = float(z_dict.get(base_curr, 0.0) or 0.0)
        z_quote = float(z_dict.get(quote_curr, 0.0) or 0.0)
        m4_st = getattr(self.scanner, "_m4_state", {}).get(clean_sym, {})
        m4_active_standby = next((s for s in m_standbys if s.get("type") == "M4"), None)
        m4_dominant_z = z_base if abs(z_base) >= abs(z_quote) else -z_quote
        m4_flow_dir = "BULL" if m4_dominant_z > 0 else "BEAR"

        # Layer 0 SFR Differentiation: Fresh Shock (>=config.M4_TRIGGER_Z) vs Flow Continuation (>=0.75)
        sfr_shock_z = float(getattr(config, "M4_TRIGGER_Z", 2.0))
        is_fresh_shock = (abs(z_base) >= sfr_shock_z or abs(z_quote) >= sfr_shock_z)
        has_active_ep = False
        if m4_st:
            for s_side in ("SELL", "BUY"):
                s_d = m4_st.get(s_side, {})
                if s_d.get("ep") is not None or s_d.get("pending") is not None:
                    has_active_ep = True
                    break
        is_continuation = (not is_fresh_shock) and (has_active_ep or m4_active_standby is not None) and (abs(m4_dominant_z) >= 0.75)
        m4_flow_state = "SHOCK" if is_fresh_shock else ("CONT" if is_continuation else "NONE")
        m4_has_shock = (m4_flow_state == "SHOCK")

        # ZCE Station Runway Target Calculation (pre-computed for telemetry & payload)
        c1_p = float(c1 or 0.0)
        f1_p = float(f1 or 0.0)
        c2_p = float(c2 or 0.0)
        f2_p = float(f2 or 0.0)
        mid_p = (bid + ask) / 2.0
        pip_val = 0.01 if ("JPY" in symbol or "XAU" in symbol) else (1.0 if "BTC" in symbol else 0.0001)
        atr_val_pts = float(atr_pts or 300)
        _pt_mult = 1.0 if "BTC" in symbol else (0.01 if ("JPY" in symbol or "XAU" in symbol) else 0.0001)
        atr_price = (atr_val_pts * _pt_mult) if atr_val_pts > 0 else (300 * _pt_mult)
        struct_stage = str(macro.get("structural_stage") or "")
        d1_trend_str = str(macro.get("d1_trend_label") or "").upper()
        h4_trend_str = str(macro.get("h4_trend_label") or "").upper()

        runway_badge = "RW: —"
        runway_text = "—"
        runway_station = "—"
        runway_pips = 0.0
        runway_atr = 0.0

        if mid_p > 0 and pip_val > 0:
            is_bull = ("BULL" in d1_trend_str or "BULL" in h4_trend_str)
            is_bear = ("BEAR" in d1_trend_str or "BEAR" in h4_trend_str)

            if is_bull and not is_bear:
                target_wall = c2_p if ("ASCENDING_ABSORPTION" in struct_stage or (c1_p > 0 and mid_p >= c1_p and c2_p > c1_p)) else c1_p
                wall_lbl = "C2" if target_wall == c2_p and c2_p > 0 else "C1"
                if target_wall > 0:
                    runway_pips = (target_wall - mid_p) / pip_val
                    runway_atr = (target_wall - mid_p) / (atr_price if atr_price > 0 else 0.001)
                    runway_station = wall_lbl
                    runway_badge = f"→{wall_lbl}: {runway_pips:+.0f}p"
                    runway_text = f"→{wall_lbl} {runway_pips:+.1f}p ({runway_atr:.2f}x ATR)"
            elif is_bear and not is_bull:
                target_wall = f2_p if ("DESCENDING_ABSORPTION" in struct_stage or (f1_p > 0 and mid_p <= f1_p and f2_p > 0 and f2_p < f1_p)) else f1_p
                wall_lbl = "F2" if target_wall == f2_p and f2_p > 0 else "F1"
                if target_wall > 0:
                    runway_pips = (mid_p - target_wall) / pip_val
                    runway_atr = (mid_p - target_wall) / (atr_price if atr_price > 0 else 0.001)
                    runway_station = wall_lbl
                    runway_badge = f"→{wall_lbl}: {runway_pips:+.0f}p"
                    runway_text = f"→{wall_lbl} {runway_pips:+.1f}p ({runway_atr:.2f}x ATR)"
            else:
                dist_to_c1 = (c1_p - mid_p) if c1_p > 0 else 99999
                dist_to_f1 = (mid_p - f1_p) if f1_p > 0 else 99999
                if dist_to_c1 < dist_to_f1 and c1_p > 0:
                    runway_pips = dist_to_c1 / pip_val
                    runway_atr = dist_to_c1 / (atr_price if atr_price > 0 else 0.001)
                    runway_station = "C1"
                    runway_badge = f"C1: {runway_pips:.0f}p"
                    runway_text = f"C1 {runway_pips:.1f}p ({runway_atr:.2f}x ATR)"
                elif f1_p > 0:
                    runway_pips = dist_to_f1 / pip_val
                    runway_atr = dist_to_f1 / (atr_price if atr_price > 0 else 0.001)
                    runway_station = "F1"
                    runway_badge = f"F1: {runway_pips:.0f}p"
                    runway_text = f"F1 {runway_pips:.1f}p ({runway_atr:.2f}x ATR)"

        m1_item = next((s for s in m_standbys if s["type"] == "M1"), None)
        m1b_item = next((s for s in m_standbys if s["type"] == "M1B"), None)
        m2_item = next((s for s in m_standbys if s["type"] == "M2"), None)
        m3_item = next((s for s in m_standbys if s["type"] == "M3"), None)
        m4_item = next((s for s in m_standbys if s["type"] == "M4"), None)

        m1_tgt = f"{m1_item['price']:.{digits}f}" if m1_item else "—"
        m1b_tgt = f"{m1b_item['price']:.{digits}f}" if m1b_item else "—"
        m2_tgt = f"{m2_item['price']:.{digits}f}" if m2_item else "—"
        m3_tgt = f"{m3_item['price']:.{digits}f}" if m3_item else "—"
        m4_tgt = f"{m4_item['price']:.{digits}f}" if m4_item else "None"

        m1_status_str = m1_item.get("status", "WAITING_SWEEP") if m1_item else "WAITING_SWEEP"
        m1b_status_str = m1b_item.get("status", "WAITING_SWEEP") if m1b_item else "NO_ZCE_CONFLUENCE"
        m3_status_str = m3_item.get("status", "WAITING_RETEST") if m3_item else "PASS"
        m3_age = m3_item.get("bar_age", 0) if m3_item else 0
        m2_desc = m2_item.get("label", "EMA Pullback") if m2_item else "—"

        telemetry = {
            "m1_target": m1_tgt,
            "m1_penetration": "Active Pierce" if (m1_item and abs(mid - m1_item['price']) <= 0.15 * atr_val) else "No (<0.15 ATR)",
            "m1_reclaim": m1_status_str,
            "m1_wick": f"{macro.get('rejection_wick_ratio', 0.0)*100:.1f}%",
            "m1b_target": m1b_tgt,
            "m1b_status": m1b_status_str,
            "m1b_zce": m1b_item.get("label", "ZCE Anchor") if m1b_item else "—",
            "m1b_wick": f"{macro.get('rejection_wick_ratio', 0.0)*100:.1f}% (Req >=30%)",
            "m1b_eqh": f"{m1b_item.get('touches', 1)}x Touches ({'EQH' if m1b_item.get('direction', -1) == -1 else 'EQL'} Pool)" if (m1b_item and m1b_item.get("is_eqh")) else ("Single Anchor" if m1b_item else "—"),
            "m2_adx": f"{macro.get('adx_14', 24.5):.1f} (Trend Aligned)",
            "m2_fib50": m2_tgt,
            "m2_fib618": f"{m2_desc.replace('Bullish Pullback (', '').replace('Bearish Pullback (', '').replace(')', '')} [Est: {m2_item.get('est_time', 'Active')}]" if m2_item else "—",
            "m2_zone": "DISCOUNT" if float(macro.get("dr_pos", 0.5)) <= 0.382 else ("PREMIUM" if float(macro.get("dr_pos", 0.5)) >= 0.618 else "EQUILIBRIUM"),
            "m3_level": m3_tgt,
            "m3_recency": f"{m3_status_str} ({m3_age}b ago)" if m3_item else "PASS",
            "m3_runaway": f"{abs(mid - m3_item['price']) / atr_val:.2f}x ATR (Guard <=2.5x)" if (m3_item and atr_val > 0) else "0.00x ATR (Guard <=2.5x)",
            "m3_runway": f"{abs(m3_item.get('target_price', mid) - m3_item['price']) / atr_val:.2f}x ATR (Req >=0.8x)" if (m3_item and atr_val > 0) else f"{runway_atr:.2f}x ATR (Req >=0.8x)",
            "m3_basing": (
                f"BOX {macro.get('basing_box', {}).get('box_bars', 0)}b ({macro.get('basing_box', {}).get('range_atr', 0.0):.2f}x ATR)"
                if macro.get('basing_box', {}).get('is_compressing')
                else (
                    f"BROKEN ({macro.get('basing_box', {}).get('box_bars', 0)}b, {macro.get('basing_box', {}).get('broken_recency', 0)}b ago)"
                    if macro.get('basing_box', {}).get('is_broken')
                    else (
                        f"INACTIVE ({macro.get('basing_box', {}).get('current_range_atr', 0.0):.2f}x ATR, expanding)"
                        if macro.get('basing_box', {}).get('current_range_atr', 0.0) > 0
                        else "INACTIVE (expanding)"
                    )
                )
            ),
            "m4_z": f"{getattr(self.scanner, '_m4_z_last', {}).get(clean_sym[:3], 0.0):+.2f}",
            "m4_breakdown": f"Confirmed ({m4_flow_state})" if m4_flow_state != "NONE" else "Standby (Awaiting |z|>=1.5)",
            "m4_pending": m4_tgt
        }

        # 7. Multi-TF Compass & State Intelligence
        strat = macro.get("strat_dir")
        w1_inter = getattr(strat, "w1_intermediate_regime", None)
        if w1_inter and "BEAR" in w1_inter:
            w1_trend = "BEAR"
        elif w1_inter and "BULL" in w1_inter:
            w1_trend = "BULL"
        else:
            w1_lbl = str(macro.get("w1_trend_label") or "SIDEWAYS").upper()
            w1_trend = "BULL" if "BULL" in w1_lbl else ("BEAR" if "BEAR" in w1_lbl else "SIDE")
        d1_lbl = str(macro.get("d1_trend_label") or "SIDEWAYS").upper()
        h4_lbl = str(macro.get("h4_trend_label") or "SIDEWAYS").upper()

        d1_trend = "BULL" if "BULL" in d1_lbl else ("BEAR" if "BEAR" in d1_lbl else "SIDE")
        h4_trend = "BULL" if "BULL" in h4_lbl else ("BEAR" if "BEAR" in h4_lbl else "SIDE")

        if candles:
            last_c = candles[-1]
            if last_c["close"] > last_c["ema50"] and last_c["ema20"] > last_c["ema50"]:
                h1_trend = "BULL"
            elif last_c["close"] < last_c["ema50"] and last_c["ema20"] < last_c["ema50"]:
                h1_trend = "BEAR"
            else:
                h1_trend = "SIDE"
        else:
            h1_trend = "SIDE"

        now_wib = datetime.now(WIB)
        active_session = _get_session_name(now_wib)
        rollover_countdown = _get_countdown_to_rollover(now_wib)
        mse_state = str(getattr(strat, "current_state", macro.get("current_state", "CONSOLIDATION_RELOAD")) or "CONSOLIDATION_RELOAD")
        adx_val = float(macro.get("adx_14", 24.5) or 24.5)
        bias_score = float(getattr(strat, "macro_bias_score", macro.get("macro_bias_score", 0.0)) or 0.0)

        # Determine rich operational phase and primary setup using unified election helper
        dir_mem = getattr(self.scanner, "_symbol_directional_state", {}).get(clean_sym)
        dir_lock_val = int(dir_mem.get("dir", 0) or 0) if dir_mem else 0
        elected_primary = _elect_primary_standby(
            m_standbys, macro, mid, pt, atr_val, pip_val, dir_lock=dir_lock_val
        )

        operational_phase = mse_state
        if elected_primary and elected_primary.get("standby"):
            active_s = elected_primary["standby"]
            s_type = active_s.get("type", "M3")
            dir_txt = "SELL" if elected_primary.get("dir_int") == -1 else "BUY"
            tgt_txt = f"{elected_primary.get('target', 0.0):.{digits}f}"
            if elected_primary.get("is_confluence"):
                struct_txt = "SBR" if dir_txt == "SELL" else "RBS"
                operational_phase = f"RETESTING {struct_txt} {elected_primary['lvl']:.{digits}f} -> TARGET {tgt_txt} [{dir_txt} CONFLUENCE]"
            elif s_type == "M3":
                struct_txt = "SBR" if dir_txt == "SELL" else "RBS"
                operational_phase = f"RETESTING {struct_txt} {active_s['price']:.{digits}f} -> TARGET {tgt_txt} [{s_type} {dir_txt}]"
            elif s_type == "M2":
                operational_phase = f"PULLBACK TOUCH @ {active_s['price']:.{digits}f} -> TARGET {tgt_txt} [{s_type} {dir_txt}]"
            elif s_type == "M1":
                operational_phase = f"MACRO SWEEP @ {active_s['price']:.{digits}f} [M1A {dir_txt}]"
            elif s_type == "M1B":
                operational_phase = f"TREND SWEEP @ {active_s['price']:.{digits}f} [M1B {dir_txt}]"
            elif s_type == "M4":
                operational_phase = f"FLOW RETEST @ {active_s['price']:.{digits}f} -> TARGET {tgt_txt} [{s_type} {dir_txt}]"

        now_session_info = _get_session_info(now_wib, symbol)
        last_candle = candles[-1] if candles else {}
        intel = {
            "w1_trend": w1_trend,
            "d1_trend": d1_trend,
            "h4_trend": h4_trend,
            "h1_trend": h1_trend,
            "adx": round(adx_val, 1),
            "mse_state": mse_state,
            "operational_phase": operational_phase,
            "action_tier": getattr(strat, "action_tier", macro.get("action_tier", "FULL_ALLOW")),
            "bias_score": round(bias_score, 2),
            "active_session": now_session_info["label"],
            "active_session_type": now_session_info["type"],
            "active_session_status": now_session_info["status"],
            "pre_rollover_countdown": rollover_countdown,
            "wave_regime_summary": last_candle.get("regime", "YOUNG_OSCILLATION"),
            "range_age_hours": last_candle.get("range_age_hours", 0.0),
            "sqz_on": last_candle.get("sqz_on", False),
            "sqz_bars": last_candle.get("sqz_bars", 0),
            "basing_box": macro.get("basing_box") or {}
        }

        dr_val = float(macro.get("dealing_range_pos", macro.get("dr_pos", 0.5)) or 0.5) * 100.0
        dr_lbl = "DEEP DISCOUNT" if dr_val <= 38.0 else ("EXTREME PREMIUM" if dr_val >= 62.0 else "EQUILIBRIUM")

        now_h = datetime.now(WIB).hour
        if 7 <= now_h < 14:
            sess_badge = {"label": "ASIA ACTIVE", "desc": "M1, M2, M3 FULLY ARMED", "color": "#10b981"}
        elif 14 <= now_h < 18:
            sess_badge = {"label": "LONDON CORE", "desc": "M1, M2, M3 ARMED (0.75x DE-RISK SIZING)", "color": "#38bdf8"}
        elif now_h >= 18:
            sess_badge = {"label": "NY EXPANSION", "desc": "M3 PAPER ONLY • M1 & M2 ARMED (0.50x SIZING)", "color": "#a855f7"}
        else:
            sess_badge = {"label": "DEAD ZONE", "desc": "00:00-07:00 WIB • FX REST", "color": "#ef4444"}

        ch_h_pips = round((float(c1) - float(f1)) / pip_val, 1) if (c1 and f1 and float(c1) > float(f1) and pip_val > 0) else 0.0
        ch_h_atr = round((float(c1) - float(f1)) / atr_val, 2) if (c1 and f1 and float(c1) > float(f1) and atr_val > 0) else 0.0

        return {
            "symbol": symbol,
            "digits": digits,
            "timeframe": timeframe_str,
            "bid": bid,
            "ask": ask,
            "spread_pts": spread_pts,
            "atr_pts": int(atr_pts),
            "dr_pos": dr_val,
            "dr_label": dr_lbl,
            "chamber_pips": ch_h_pips,
            "chamber_atr": ch_h_atr,
            "session_badge": sess_badge,
            "runway_text": runway_text,
            "runway_badge": runway_badge,
            "runway_station": runway_station,
            "runway_pips": round(runway_pips, 1),
            "runway_atr": round(runway_atr, 2),
            "m4_shock": m4_has_shock,
            "m4_flow_state": m4_flow_state,
            "m4_z": round(m4_dominant_z, 2),
            "m4_dir": m4_flow_dir,
            "csm_delta": float(macro.get("csm_delta", 0.0) or 0.0),
            "action_tier": getattr(strat, "action_tier", macro.get("action_tier", "FULL_ALLOW")),
            "perm_label": macro.get("permission_state", "GO"),
            "tactical_state": macro.get("tactical_state", "BALANCED_FLOW"),
            "tactical_desc": macro.get("tactical_desc", ""),
            "f1": round(float(f1), digits) if f1 else None,
            "f2": round(float(f2), digits) if f2 else None,
            "c1": round(float(c1), digits) if c1 else None,
            "c2": round(float(c2), digits) if c2 else None,
            "c1_grade": getattr(zm, "immediate_ceiling_c1_grade", None),
            "f1_grade": getattr(zm, "immediate_floor_f1_grade", None),
            "c1_confluence": int(getattr(zm, "immediate_ceiling_c1_confluence", 0) or 0),
            "f1_confluence": int(getattr(zm, "immediate_floor_f1_confluence", 0) or 0),
            "inside_zone": bool(getattr(zm, "inside_zone", False)),
            "inside_tiers": list(getattr(zm, "inside_tiers", []) or []),
            "layer_count": int(getattr(zm, "layer_count", 0) or 0),
            "candles": candles,
            "strategy_audit_markers": strat_audit_markers,
            "envelope_visual": (getattr(strat, "macro_envelope", {}) or {}).get("visual_payload") or (getattr(strat, "raw_payload", {}).get("envelope_visual", {}) if hasattr(strat, "raw_payload") else {}),
            "macro_envelope": (getattr(strat, "macro_envelope", None) or (getattr(strat, "raw_payload", {}).get("macro_envelope") if hasattr(strat, "raw_payload") else None)),
            "zce_walls": zce_walls,
            "zce_ladder": zce_ladder,
            "intel": intel,
            "m_standbys": m_standbys,
            "primary_setup": {
                "type": elected_primary.get("type", ""),
                "name": elected_primary.get("name", ""),
                "direction": elected_primary.get("dir_int", 0),
                "price": elected_primary.get("lvl", 0.0),
                "target": elected_primary.get("target", 0.0),
                "is_confluence": elected_primary.get("is_confluence", False)
            } if elected_primary else None,
            "gates": gates,
            "open_positions": open_pos,
            "pending_orders": pending_orders,
            "direction_lock": getattr(self.scanner, "_symbol_directional_state", {}).get(
                symbol.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").upper(),
                {"dir": 0, "status": "FREE", "reason": "UNCONSTRAINED"}
            ),
            "telemetry": telemetry,
            "w1_slope_ceiling": getattr(strat, "w1_slope_ceiling", None),
            "w1_secular_regime": getattr(strat, "w1_secular_regime", "SECULAR_RANGE"),
            "w1_intermediate_regime": getattr(strat, "w1_intermediate_regime", "NEUTRAL_OSCILLATION"),
            "w1_horizon_conflict": getattr(strat, "htf_horizon_conflict", False),
            "w1_lower_highs": getattr(strat, "w1_lower_highs", [])
        }

    def _evaluate_8_gates(self, sym: str, valid_sym: str, macro: dict, strat: Any, mid: float, spread_pts: int, atr_val: float, pt: float) -> List[Dict[str, Any]]:
        """Evaluates 8 sequential decision gates for X-Ray Surveillance."""
        now_wib = datetime.now(WIB)
        h = now_wib.hour
        gates = []

        # Gate 1: Operational Session & Spread Filter
        is_crypto = config.is_crypto(sym)
        is_gold = config.is_gold(sym)
        is_dead_zone = (0 <= h < 7) and not is_crypto
        clean_s = sym.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").upper()
        is_asian = (7 <= h < 14) and not is_crypto
        is_asian_allowed = any(k in clean_s for k in ("JPY", "AUD", "NZD")) or is_crypto or is_gold
        spread_cap = config.max_spread_points_for(sym) if (is_crypto or is_gold) else max(int(round(atr_val * 0.15 / pt)), 20)

        # Dynamic Session Multiplier (Reconciliation 10 Sep 2026)
        ny_start_h = getattr(config, "NY_SESSION_START_HOUR_WIB", 18)
        sess_mult = getattr(config, "SESSION_ASIA_LOT_MULT", 1.20) if is_asian else (
            getattr(config, "SESSION_NY_LOT_MULT", 0.50) if (ny_start_h <= h or h == 0) else getattr(config, "SESSION_LONDON_LOT_MULT", 1.00)
        )

        if is_dead_zone:
            g1 = {"id": 1, "title": "Session & Spread Filter", "status": "BLOCK", "desc": f"WIB Operational Hours (Sess Mult: {sess_mult}x)", "reason": f"[DEAD ZONE] Trading non-aktif pada 00:00–07:00 WIB (Current: {h:02d}:00 WIB). Hanya manage posisi."}
        elif is_asian and not is_asian_allowed:
            g1 = {"id": 1, "title": "Session & Spread Filter", "status": "BLOCK", "desc": f"WIB Operational Hours (Sess Mult: {sess_mult}x)", "reason": f"[SESSION LOCKED] Sesi Tokyo (07:00-14:00 WIB) hanya izinkan driver JPY/AUD/NZD. {clean_s} dikunci."}
        elif spread_pts > spread_cap:
            g1 = {"id": 1, "title": "Session & Spread Filter", "status": "BLOCK", "desc": f"WIB Operational Hours (Sess Mult: {sess_mult}x)", "reason": f"[SPREAD SPIKE] Spread ({spread_pts} pts) melebihi batas ({spread_cap} pts)."}
        else:
            g1 = {"id": 1, "title": "Session & Spread Filter", "status": "PASS", "desc": f"WIB Operational Hours (Sess Mult: {sess_mult}x)", "reason": f"Sesi aktif ({h:02d}:00 WIB) & spread {spread_pts} pts <= {spread_cap} pts cap. Lot multiplier: {sess_mult}x."}
        gates.append(g1)

        # Gate 2: Economic News & Event Shield (±30m Tier-1 Window)
        from src.analytics.economic_calendar import calendar as econ_cal
        m_before = int(getattr(config, "NEWS_BLACKOUT_MINUTES_BEFORE", 30))
        m_after = int(getattr(config, "NEWS_BLACKOUT_MINUTES_AFTER", 30))
        is_news_blackout, news_reason = econ_cal.is_in_news_blackout(
            symbol=sym,
            now_wib=now_wib,
            minutes_before=m_before,
            minutes_after=m_after
        )
        is_holiday, holiday_desc = econ_cal.is_bank_holiday_today("ALL")
        
        # Next upcoming event context
        upcoming_events = econ_cal.get_events(now_wib, symbol=sym)
        next_event_str = "Tidak ada berita Tier-1 hari ini"
        for ev in upcoming_events:
            if str(ev.get("impact", "")).upper() in ("HIGH", "CRITICAL"):
                ev_dt = ev.get("dt")
                if ev_dt and ev_dt > now_wib:
                    diff_m = int((ev_dt - now_wib).total_seconds() / 60)
                    next_event_str = f"{ev.get('name')} dalam {diff_m}m ({ev_dt.strftime('%H:%M')} WIB)"
                    break

        if is_crypto:
            g2 = {
                "id": 2,
                "title": "Economic News & Event Shield",
                "status": "PASS",
                "desc": "Crypto 24/7 Independent Asset",
                "reason": "Bitcoin (BTCUSD) beroperasi 24/7 independen dari jadwal kalender berita fiat."
            }
        elif is_news_blackout:
            g2 = {
                "id": 2,
                "title": "Economic News & Event Shield",
                "status": "BLOCK",
                "desc": f"Tier-1 Blackout Window (±{m_before}m)",
                "reason": f"[NEWS BLACKOUT] {news_reason}. Pembukaan order baru dibekukan."
            }
        elif is_holiday and (20 <= h or h == 0) and not is_crypto:
            g2 = {
                "id": 2,
                "title": "Economic News & Event Shield",
                "status": "BLOCK",
                "desc": f"Bank Holiday ({holiday_desc})",
                "reason": f"[BANK HOLIDAY] {holiday_desc}. Pasar antarbank New York tutup."
            }
        else:
            g2 = {
                "id": 2,
                "title": "Economic News & Event Shield",
                "status": "PASS",
                "desc": f"Tier-1 News Clear (±{m_before}m)",
                "reason": f"Jendela rilis berita Tier-1 aman (±{m_before}m bebas blackout). Info event terdekat: {next_event_str}."
            }
        gates.append(g2)

        # Gate 3: Systemic Basket & CBSS Guard
        # Tentukan target_dir & Directional Lock:
        dir_state = getattr(self.scanner, "_symbol_directional_state", {}).get(clean_s, {})
        dir_val = dir_state.get("dir", 0)
        dir_label = "BUY ONLY" if dir_val == 1 else ("SELL ONLY" if dir_val == -1 else "FREE / DUAL")
        dir_desc = f" • Lock: {dir_label}"

        m4_dir_override = None
        try:
            m4_st = getattr(self.scanner, "_m4_state", {}).get(clean_s, {})
            m4_n  = len(getattr(self.scanner, "_m4_df", {}).get(clean_s, []) or [])
            for _side, _dir in (("BUY", 1), ("SELL", -1)):
                _s = m4_st.get(_side, {})
                _ep   = _s.get("ep")
                _pend = _s.get("pending")
                _ref  = _pend.get("break_pos") if _pend else _ep
                if _ref is not None:
                    _age = (m4_n - 1 - _ref) if m4_n > _ref else 0
                    if _age <= getattr(config, "M4_MAX_WAIT_BARS", 48):
                        m4_dir_override = _dir
                        break
        except Exception:
            pass

        if m4_dir_override is not None:
            target_dir = m4_dir_override
        elif dir_val != 0:
            target_dir = dir_val
        else:
            target_dir = 1 if macro.get("is_bull") else -1

        if is_crypto:
            g3 = {"id": 3, "title": "Systemic Basket & CBSS Guard", "status": "PASS", "desc": "Circuit Breaker & Concurrency Check", "reason": "Aset crypto (BTCUSD) beroperasi independen dari matriks basket shock fiat."}
        elif is_gold:
            g3 = {"id": 3, "title": "Systemic Basket & CBSS Guard", "status": "PASS", "desc": "Commodity Asset Basket Check", "reason": "Komoditas logam (XAUUSD) beroperasi independen dari matriks basket currency fiat."}
        else:
            is_locked, b_reason, _ = evaluate_systemic_basket_lock(sym, target_dir)
            m_cache = self.scanner.macro_cache if (self.scanner and hasattr(self.scanner, "macro_cache")) else {}
            is_g3_blocked, g3_reason = is_pair_blocked_by_g3_wall(sym, target_dir, m_cache)

            # Cek Basket Concurrency Cap & Runway Relay
            pos_all = connector.get_all_open_positions() or []
            pend_all = connector.get_pending_orders() or []
            conflict_ok, conflict_reason = check_basket_directional_conflict(sym, target_dir, pos_all, pend_all)
            cap_ok, cap_reason = check_basket_concurrency_cap(sym, target_dir, pos_all, pend_all)
            runway_info = calculate_pair_runway(sym, target_dir, m_cache)
            r_atr = runway_info.get("runway_atr", 2.0)
            opp_grade = runway_info.get("opp_wall_grade", "")
            is_opp_g3 = ("3" in opp_grade or "MACRO" in opp_grade)
            wall_th_g3 = float(getattr(config, "CBSS_WALL_EXHAUSTION_G3_ATR", 0.35))

            if is_locked:
                g3 = {"id": 3, "title": "Systemic Basket & CBSS Guard", "status": "BLOCK", "desc": "Circuit Breaker Shock Protection (35.0 bps)", "reason": f"[BASKET LOCKED] {b_reason}"}
            elif not conflict_ok:
                g3 = {"id": 3, "title": "Systemic Basket & CBSS Guard", "status": "BLOCK", "desc": "Anti-Internal Currency Hedge Veto", "reason": conflict_reason}
            elif is_g3_blocked:
                g3 = {"id": 3, "title": "Systemic Basket & CBSS Guard", "status": "BLOCK", "desc": "CBSS Local G3 Wall Veto (The EURAUD Law)", "reason": g3_reason}
            elif is_opp_g3 and r_atr < wall_th_g3:
                g3 = {"id": 3, "title": "Systemic Basket & CBSS Guard", "status": "WAIT", "desc": f"Relay Pause: Macro G3 Proximity ({r_atr:.2f}x ATR)", "reason": f"[WALL EXHAUSTED] Jarak ke benteng makro {opp_grade} {r_atr:.2f}x ATR < {wall_th_g3:.2f}x ATR. Estafet likuiditas dialihkan ke pair laggard sekeranjang."}
            elif not cap_ok:
                g3 = {"id": 3, "title": "Systemic Basket & CBSS Guard", "status": "PAPER", "desc": "CBSS Concurrency Saturated (Paper Route)", "reason": f"[CBSS SATURATED] {cap_reason} -> Dialihkan ke Virtual Paper Trade (0 Token, 0 Risiko MT5)."}
            else:
                base_c, quote_c = get_pair_currencies(clean_s)
                pen_note = f" ({opp_grade} Penetrable)" if (not is_opp_g3 and r_atr < 0.35) else ""
                g3 = {"id": 3, "title": "Systemic Basket & CBSS Guard", "status": "PASS", "desc": f"CBSS Cleared (Runway {r_atr:.2f}x ATR){pen_note}", "reason": f"Aliran basket {base_c}/{quote_c} stabil (<35 bps). Bebas tabrakan benteng G3 lawan & runway memadai ({r_atr:.2f}x ATR)."}
        gates.append(g3)

        # Gate 4: MSE Chamber & Forbidden Traps + Directional Hysteresis
        tier = getattr(strat, "action_tier", macro.get("action_tier", "FULL_ALLOW"))
        traps = getattr(strat, "forbidden_traps", []) or []
        trap_reason = traps[0] if traps else ""
        f1_lvl = float(macro.get("immediate_floor_f1", 0.0) or 0.0)
        c1_lvl = float(macro.get("immediate_ceiling_c1", 0.0) or 0.0)
        digits = 3 if ("JPY" in clean_s) else (2 if (is_crypto or is_gold) else 5)

        if tier == "HARD_BLOCK":
            g4 = {"id": 4, "title": "MSE Chamber & Directional Lock", "status": "BLOCK", "desc": f"Chamber Gating & Hysteresis{dir_desc}", "reason": f"[MSE HARD BLOCK] {trap_reason or 'Hard Lock past invalidation'}"}
        elif tier == "WATCH_ONLY":
            ch_desc = trap_reason if trap_reason else (f"Konsolidasi Kamar: Menunggu pendekatan benteng Floor F1 ({f1_lvl:.{digits}f}) atau Ceiling C1 ({c1_lvl:.{digits}f}). Setup limit & sweep tetap aktif dipindai." if (f1_lvl > 0 and c1_lvl > 0) else "Konsolidasi Kamar: Menunggu konfirmasi structural breakout.")
            g4 = {"id": 4, "title": "MSE Chamber & Directional Lock", "status": "WAIT", "desc": f"Chamber Gating & Hysteresis{dir_desc}", "reason": f"[MSE WATCH ONLY] {ch_desc}"}
        else:
            g4 = {"id": 4, "title": "MSE Chamber & Directional Lock", "status": "PASS", "desc": f"Chamber Gating & Hysteresis{dir_desc}", "reason": f"Action Tier: {tier} (Kamar terbuka untuk retest/expansion){dir_desc}."}
        gates.append(g4)

        # Gate 5: Boitoki CSM Flow Alignment
        if is_crypto or is_gold:
            g5 = {"id": 5, "title": "Boitoki CSM Flow Alignment", "status": "PASS", "desc": "Relative Net Currency Delta Flow Check", "reason": f"Aset non-fiat ({clean_s}) independen dari arus fiat CSM (Net Delta N/A)."}
        else:
            csm_d = float(macro.get("csm_delta", 0.0) or 0.0)
            csm_filter_enabled = getattr(config, "ENABLE_CSM_FLOW_FILTER", True)
            csm_opp_thresh = float(getattr(config, "CSM_FLOW_OPPOSED_THRESHOLD", 1.50))
            is_csm_opposed = (target_dir == 1 and csm_d <= -csm_opp_thresh) or (target_dir == -1 and csm_d >= csm_opp_thresh)
            dir_label_g5 = "BUY" if target_dir == 1 else "SELL"
            m4_tag = " [M4 Dir]" if m4_dir_override is not None else (" [Lock Dir]" if dir_val != 0 else "")

            if is_csm_opposed and csm_filter_enabled:
                g5 = {"id": 5, "title": "Boitoki CSM Flow Opposition", "status": "BLOCK",
                      "desc": "Relative Net Currency Delta Flow Check",
                      "reason": f"[CSM OPPOSED] Net Delta ({csm_d:+.2f}) berlawanan arah dengan setup ({dir_label_g5}{m4_tag})."}
            elif is_csm_opposed and not csm_filter_enabled:
                g5 = {"id": 5, "title": "Boitoki CSM Flow — OBSERVE MODE", "status": "OBSERVE",
                      "desc": "Relative Net Currency Delta Flow Check (Filter Dinonaktifkan)",
                      "reason": f"[FORWARD TEST] CSM Net Delta ({csm_d:+.2f}) berlawanan {dir_label_g5}{m4_tag} — dicatat sebagai telemetri, tidak memblokir eksekusi (ENABLE_CSM_FLOW_FILTER=false)."}
            else:
                g5 = {"id": 5, "title": "Boitoki CSM Flow Alignment", "status": "PASS",
                      "desc": "Relative Net Currency Delta Flow Check",
                      "reason": f"Net Delta {csm_d:+.2f} selaras atau netral dengan {dir_label_g5}{m4_tag} momentum arah."}
        gates.append(g5)

        # Gate 6: M1A/M1B..M4 Setup Prerequisites
        if getattr(strat, "action_tier", "") in ("FULL_ALLOW", "REDUCED_CONFIDENCE") and macro.get("permission_state") == "GO":
            g6 = {"id": 6, "title": "M1A/M1B..M4 Radar Prerequisites", "status": "PASS", "desc": "Mechanism Criteria & Trigger Penetration", "reason": "Kriteria kuantitatif terpenuhi. Menunggu harga menyentuh pending level."}
        else:
            g6 = {"id": 6, "title": "M1A/M1B..M4 Radar Prerequisites", "status": "WAIT", "desc": "Mechanism Criteria & Trigger Penetration", "reason": "Menunggu konfirmasi wick rejection M1A / trend sweep M1B / pullback Fib M2 / breakdown M3 / breakout basing M4."}
        gates.append(g6)

        # Gate 7: Stage 2 3-AI Consensus Jury & CRO
        if config.is_paper_only(sym):
            g7 = {"id": 7, "title": "Virtual Paper Trade Execution", "status": "PAPER", "desc": "Direct Virtual Shadow Tracking (0 Token, 0 MT5 Risk)", "reason": f"Simbol {clean_s} beroperasi khusus di Virtual Paper Trade (shadow_tracker). Order riil MT5 diisolasi (0 Risiko Modal)."}
        elif not getattr(config, "ENABLE_LLM_JURY", True):
            g7 = {"id": 7, "title": "Pure Quant Direct Execution (No-LLM)", "status": "PASS", "desc": "Direct Quant Radar Signal Dispatch (0 Token)", "reason": "Mode Pure Quant aktif (0 Token API). Sinyal kuantitatif dieksekusi langsung tanpa sidang LLM."}
        else:
            g7 = {"id": 7, "title": "Stage 2 3-AI Consensus & CRO Audit", "status": "WAIT", "desc": "OpenAI + Gemini + DeepSeek CRO Veto", "reason": "Stage 1 Fast Radar Standby (0 Token terpakai). Memicu 3-LLM Jury otomatis saat setup A+ tersentuh."}
        gates.append(g7)

        # Gate 8: Risk Calibration & SL/TP Rules
        if is_crypto:
            sl_floor = getattr(config, "DEFAULT_SL_POINTS_BTC", 30000)
            sl_ceil = 45000
            g8 = {"id": 8, "title": "Risk Floor, Ceiling & Over-Risk Gate", "status": "PASS", "desc": f"BTC floor {sl_floor} pts, ceiling {sl_ceil} pts, {config.RISK_PERCENT_BTC}% risk", "reason": f"Sizing {config.RISK_PERCENT_BTC}% equity aman. SL floor {sl_floor} pts ($300) & plafon {sl_ceil} pts ($450) terkalibrasi."}
        elif is_gold:
            sl_floor = getattr(config, "DEFAULT_SL_POINTS_XAU", 500)
            sl_ceil = 1500
            g8 = {"id": 8, "title": "Risk Floor, Ceiling & Over-Risk Gate", "status": "PASS", "desc": f"Gold floor {sl_floor} pts ($5.00), ceiling {sl_ceil} pts, {config.RISK_PERCENT_XAU}% risk", "reason": f"Sizing {config.RISK_PERCENT_XAU}% equity aman (Paper Mode). SL floor {sl_floor} pts & plafon {sl_ceil} pts valid."}
        else:
            g8 = {"id": 8, "title": "Risk Floor, Ceiling & Over-Risk Gate", "status": "PASS", "desc": "SL 0.50x ATR floor, 2.5x ATR ceiling, 1.0% equity cap", "reason": f"Sizing 1.0% equity aman. Plafon SL {int(atr_val*2.5/pt)} pts valid (Zero Over-Risk)."}
        gates.append(g8)

        return gates

    _evaluate_7_gates = _evaluate_8_gates


# Global Engine Instance
cockpit_engine = CockpitDataEngine()


class CockpitHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        try:
            self._handle_do_get()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            # Harmless client disconnect (browser closed/refreshed tab before stream completed)
            pass
        except Exception as e:
            logger.error(f"[DASHBOARD HTTP ERROR] {e}\n{traceback.format_exc()}")
            try:
                self.send_error(500, f"Internal Server Error: {e}")
            except Exception:
                pass

    def _handle_do_get(self):
        # 1. API: Overview 26-pair
        if self.path == "/api/overview":
            with cockpit_engine._lock:
                payload = json.dumps(cockpit_engine.cached_overview).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)

        # 2. API: Symbol Detail
        elif self.path.startswith("/api/symbol/"):
            path_part = self.path[len("/api/symbol/"):]
            sym = path_part.split("?")[0]
            tf = "H1"
            if "?tf=" in path_part:
                tf = path_part.split("?tf=")[1].split("&")[0]

            data = cockpit_engine.get_symbol_detail(sym, tf)
            payload = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)

        # 3. API: Active Rules Inventory
        elif self.path == "/api/rules":
            is_no_ai = not getattr(config, "ENABLE_LLM_JURY", True)
            jury_mode_str = "Pure Quant Direct (0 Token)" if is_no_ai else "Strict 3/3 Unanimous Jury"
            rules_data = [
                {"category": "Mekanisme Radar", "param": "M1_ENABLED", "value": str(getattr(config, "M1_ENABLED", True)), "desc": "Universal Liquidity Sweep & Structural SFP (Wick >= 33.3%, penetration 0.04 ATR)"},
                {"category": "Mekanisme Radar", "param": "M2_ENABLED", "value": str(getattr(config, "M2_ENABLED", True)), "desc": "Trend-Aligned Pullback (ADX >= 20, Fib 50% - 61.8% Golden Pocket)"},
                {"category": "Mekanisme Radar", "param": "M3_ENABLED", "value": str(getattr(config, "M3_ENABLED", True)), "desc": "Breakout Retest (15-Bar Recency Guard, 2.5x ATR Runaway Guard, Runway >= 0.8x ATR)"},
                {"category": "Mekanisme Radar", "param": "M4_ENABLED", "value": str(getattr(config, "M4_ENABLED", True)), "desc": "Systemic Flow Continuation (z >= 1.5, 120-bar break, M4_STRUCTURAL_FLOORED)"},
                {"category": "CBSS Synchronization", "param": "ENABLE_CBSS", "value": str(getattr(config, "ENABLE_CBSS", True)), "desc": "Currency Basket Structural Synchronization: ZCE Runway & Basket Concurrency Cap"},
                {"category": "CBSS Synchronization", "param": "CBSS_MAX_BASKET_CONCURRENCY", "value": str(getattr(config, "CBSS_MAX_BASKET_CONCURRENCY", 2)), "desc": "Maksimal 2 posisi aktif per mata uang dalam arah eksposur yang sama"},
                {"category": "CBSS Synchronization", "param": "CBSS_G3_BARRIER_THRESHOLD_ATR", "value": f"{getattr(config, 'CBSS_G3_BARRIER_THRESHOLD_ATR', 0.35)}x ATR", "desc": "Local Pair G3 Wall Veto (The EURAUD Law): blokir pair penabrak benteng lawan"},
                {"category": "Circuit Breaker", "param": "SYSTEMIC_BASKET_THRESHOLD", "value": "35.0 bps", "desc": "USD, JPY, Cross & Spread Shock Threshold (Mencegah trade saat lonjakan anomali)"},
                {"category": "Waktu Operasional", "param": "DEAD_ZONE_HOURS", "value": "00:00 - 07:00 WIB", "desc": "Perlindungan rollover likuiditas tipis & spread tinggi broker"},
                {"category": "Waktu Operasional", "param": "PRE_ROLLOVER_SHIELD", "value": "03:50 WIB", "desc": "Tutup otomatis posisi berisiko sebelum lonjakan rollover 04:00 WIB"},
                {"category": "Execution Mode", "param": "ENABLE_LLM_JURY", "value": str(getattr(config, "ENABLE_LLM_JURY", True)), "desc": f"Mode Eksekusi Aktif: {jury_mode_str}"},
                {"category": "Risk Management", "param": "LLM_FX_FLOOR_ATR_MULT", "value": "0.50x ATR (H1)", "desc": "Batas lantai stop loss minimum FX majors & crosses (+15 pts buffer)"},
                {"category": "Risk Management", "param": "DYNAMIC_ZCE_RUNWAY_CAP", "value": "max(3.5x ATR, 1.5x Floor)", "desc": "Plafon stop loss anti-runaway & validasi kapasitas runway ZCE C1/F1"},
                {"category": "Risk Management", "param": "MAX_DAILY_LOSS", "value": "4.0% Equity", "desc": "Hard circuit breaker harian modal akun (~$235 di akun $5800)"}
            ]
            payload = json.dumps(rules_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)

        # 4. API: Shadow Radar Analytics
        elif self.path == "/api/shadow":
            try:
                from src.analytics.shadow_tracker import shadow_tracker
                shadow_tracker.reload_state_if_modified()
                s_data = shadow_tracker.get_performance_summary()
                # Extend payload dengan full trade arrays & real-time live prices untuk JS table polling
                act = shadow_tracker.get_active_trades_enriched()
                resolved = shadow_tracker.get_all_resolved_trades(limit=500)
                s_data["active_trades_full"] = act
                s_data["resolved_trades_full"] = resolved
                s_data["all_trades_combined"] = act + resolved
            except Exception as e:
                s_data = {"error": str(e)}
            payload = json.dumps(s_data, default=str).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(payload)


        # 4b. Web UI: Quant Shadow Radar HTML Report
        elif self.path in ("/shadow", "/shadow.html", "/report/shadow"):
            html = render_shadow_report_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(html)

        # 5. Web UI Root
        elif self.path in ("/", "/index.html", "/dashboard", "/dashboard.html"):
            import importlib
            import dashboard_assets
            importlib.reload(dashboard_assets)
            html = dashboard_assets.TEMPLATE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(html)
        else:
            super().do_GET()

    def log_message(self, format, *args):
        pass  # Suppress HTTP spam in console


def main():
    parser = argparse.ArgumentParser(description="Institutional Quant Decision Surveillance Cockpit")
    parser.add_argument("--serve", action="store_true", help="Run real-time surveillance server")
    parser.add_argument("--port", type=int, default=8765, help="Server port (default 8765)")
    parser.add_argument("-o", "--output", type=str, default=OUT_HTML, help="Output HTML file path")
    args = parser.parse_args()

    # Always write static template
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(TEMPLATE)
    print(f" [OK] Template Cockpit berhasil digenerate: {args.output}")

    # Also generate static Quant Shadow report
    try:
        sh_path = generate_and_save_shadow_report()
        print(f" [OK] Static Quant Shadow Report berhasil digenerate: {sh_path}")
    except Exception as e:
        logger.warning(f"[DASHBOARD] Gagal generate shadow report statis: {e}")

    if args.serve:
        port = args.port
        cockpit_engine.start()
        print(f" [ONLINE] Quant Decision Cockpit Server LIVE di: http://localhost:{port}")
        print(f" [i] Tekan Ctrl+C untuk menghentikan server.")
        with socketserver.ThreadingTCPServer(("", port), CockpitHTTPHandler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n [!] Cockpit server dihentikan.")


if __name__ == "__main__":
    main()
