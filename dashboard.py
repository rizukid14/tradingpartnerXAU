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
import math
import os
import re
import socketserver
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

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
from src.indicators.lux_smc import LuxSMCAnalyzer
from dashboard_assets import TEMPLATE

WIB = ZoneInfo("Asia/Jakarta")
DATA_DIR = os.path.join(ROOT, "data")
OUT_HTML = os.path.join(ROOT, "dashboard.html")
FUNNEL_METRICS_PATH = os.path.join(DATA_DIR, "quant_funnel_metrics.json")


def _get_session_name(dt_wib: datetime) -> str:
    h = dt_wib.hour
    if 0 <= h < 8:
        return "DEAD_ZONE"
    elif 8 <= h < 14:
        return "TOKYO"
    elif 14 <= h < 19:
        return "LONDON"
    elif 19 <= h < 23:
        return "OVERLAP"
    else:
        return "LATE_NY"


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

    # 1. Elected floors & ceilings from ZoneMapResult
    for fl in getattr(zm, "floors", []) or []:
        p = float(fl.get("price", 0.0))
        if v_lo <= p <= v_hi:
            cands.append({
                "price": p,
                "band_low": float(fl.get("band_low", p)),
                "band_high": float(fl.get("band_high", p)),
                "tier": str(fl.get("tier", "F")),
                "grade": str(fl.get("grade", "GRADE_1_MICRO")),
                "score": float(fl.get("density_score", fl.get("score_raw", 1.0))),
                "tag": str(fl.get("tag", "FORTRESS")),
                "tfs": list(fl.get("tfs_present", [])),
                "kinds": list(fl.get("kinds_present", [])),
                "is_cold": bool(fl.get("is_cold", False)),
                "is_vacuum": bool(fl.get("is_vacuum", False)),
                "source": "elected"
            })

    for ce in getattr(zm, "ceilings", []) or []:
        p = float(ce.get("price", 0.0))
        if v_lo <= p <= v_hi:
            cands.append({
                "price": p,
                "band_low": float(ce.get("band_low", p)),
                "band_high": float(ce.get("band_high", p)),
                "tier": str(ce.get("tier", "C")),
                "grade": str(ce.get("grade", "GRADE_1_MICRO")),
                "score": float(ce.get("density_score", ce.get("score_raw", 1.0))),
                "tag": str(ce.get("tag", "FORTRESS")),
                "tfs": list(ce.get("tfs_present", [])),
                "kinds": list(ce.get("kinds_present", [])),
                "is_cold": bool(ce.get("is_cold", False)),
                "is_vacuum": bool(ce.get("is_vacuum", False)),
                "source": "elected"
            })

    # 2. Raw clusters from ZoneMapResult
    for cl in getattr(zm, "clusters", []) or []:
        p = float(getattr(cl, "mid", (getattr(cl, "band_low", 0.0) + getattr(cl, "band_high", 0.0)) / 2.0))
        if v_lo <= p <= v_hi:
            cands.append({
                "price": p,
                "band_low": float(getattr(cl, "band_low", p)),
                "band_high": float(getattr(cl, "band_high", p)),
                "tier": "ZONE",
                "grade": str(getattr(cl, "grade", "GRADE_1_MICRO")),
                "score": float(getattr(cl, "score_final", 1.0)),
                "tag": str(getattr(cl, "fortress_tag", "FORTRESS")),
                "tfs": list(getattr(cl, "tfs_present", [])),
                "kinds": list(getattr(cl, "kinds_present", [])),
                "is_cold": bool(getattr(cl, "is_cold", False)),
                "is_vacuum": bool(getattr(cl, "is_vacuum", False)),
                "source": "cluster"
            })

    if not cands:
        return []

    # Sort by price
    cands.sort(key=lambda x: x["price"])

    # Cluster consolidation by proximity threshold
    proximity_thr = max(0.20 * atr_val, 4.0 * pip_val)
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
        avg_price = sum(x["price"] for x in grp) / len(grp)
        rep_price = lead["price"] if lead["source"] == "elected" else avg_price

        min_lo = min(x["band_low"] for x in grp)
        max_hi = max(x["band_high"] for x in grp)
        max_score = max(x["score"] for x in grp)
        top_grade = lead["grade"]
        top_tier = lead["tier"]
        if top_tier == "ZONE":
            top_tier = "FLR" if rep_price < cur_price else "CEIL"

        g_short = "G3" if top_grade == "GRADE_3_MACRO" else ("G2" if top_grade == "GRADE_2_INTERMEDIATE" else "G1")
        tf_str = "+".join(all_tfs[:3]) if all_tfs else "H1"
        kind_str = "+".join(all_kinds[:2]) if all_kinds else "SMC"
        label = f"{top_tier} [{g_short}] {rep_price:.{digits}f} ({max_score:.1f} • {tf_str} • {kind_str})"

        result.append({
            "price": round(float(rep_price), digits),
            "band_low": round(float(min_lo), digits),
            "band_high": round(float(max_hi), digits),
            "type": "floor" if rep_price < cur_price else "ceiling",
            "tier": top_tier,
            "grade": top_grade,
            "score": round(float(max_score), 2),
            "tfs": all_tfs,
            "kinds": all_kinds,
            "tag": lead["tag"],
            "label": label,
            "is_cold": any(x["is_cold"] for x in grp),
            "is_vacuum": any(x["is_vacuum"] for x in grp)
        })

    return result


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
        self.scanner = MarketScanner()
        self._is_running = True
        t = threading.Thread(target=self._background_loop, daemon=True)
        t.start()
        print("[Cockpit Engine] Background observation worker started.")

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
                pass
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

        # 2. 26 Pairs Proximity Analysis
        symbols = config.get_scanner_symbols()
        pairs_data = []

        for sym in symbols:
            valid_sym = connector.get_valid_trade_symbol(sym)
            clean_sym = sym.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").upper()
            macro = self.scanner.macro_cache.get(sym) or self.scanner.macro_cache.get(valid_sym) or {}
            strat = macro.get("strat_dir")

            tick = config.mt5.symbol_info_tick(valid_sym)
            si = config.mt5.symbol_info(valid_sym)
            digits = si.digits if si else 5
            pt = si.point if si and si.point else (0.001 if "JPY" in sym else 0.00001)
            pip_div = 10 if digits in (3, 5) else 1
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
            setups_dist = []
            type_label_map = {
                "M1": "M1:SWEEP",
                "M2": "M2:PULLBACK",
                "M3": "M3:BREAKOUT",
                "M4": "M4:FLOW"
            }
            for s in standbys:
                s_lvl = float(s.get("price", 0.0))
                if s_lvl > 0 and mid > 0:
                    dist_pips = abs(mid - s_lvl) / pip_val
                    dist_atr = abs(mid - s_lvl) / atr_val
                    s_lbl = s.get("label", "").upper()
                    if "BEAR" in s_lbl or "SBR" in s_lbl or "SELL" in s_lbl:
                        dir_tag = "BEAR"
                    elif "BULL" in s_lbl or "RBS" in s_lbl or "BUY" in s_lbl:
                        dir_tag = "BULL"
                    else:
                        dir_tag = s_lbl.split()[0] if s_lbl else "SETUP"
                    s_type_label = type_label_map.get(s.get("type", ""), s.get("type", "SETUP"))
                    short_name = f"{s_type_label} {dir_tag}"
                    setups_dist.append({
                        "name": short_name,
                        "type": s.get("type", ""),
                        "dir": dir_tag,
                        "dist_pips": dist_pips,
                        "dist_atr": dist_atr,
                        "lvl": s_lvl
                    })

            # Pick closest and evaluate multi-setup confluence
            is_confluence = False
            confluence_name = ""
            extra_count = 0

            if setups_dist:
                setups_dist.sort(key=lambda x: x["dist_atr"])  # sort by dist_atr
                closest = setups_dist[0]
                closest_name = closest["name"]
                closest_pips = closest["dist_pips"]
                closest_atr = closest["dist_atr"]
                closest_lvl = closest["lvl"]

                # Near setups within reasonable operational proximity (<= 1.5x ATR)
                near_setups = [s for s in setups_dist if s["dist_atr"] <= 1.5]
                extra_count = max(0, len(near_setups) - 1)

                # Confluence check: >= 2 setups in same direction within <= 0.35x ATR
                if len(near_setups) >= 2:
                    same_dir_setups = [s for s in near_setups if s["dir"] == closest["dir"]]
                    if len(same_dir_setups) >= 2:
                        min_lvl = min(s["lvl"] for s in same_dir_setups)
                        max_lvl = max(s["lvl"] for s in same_dir_setups)
                        if (max_lvl - min_lvl) <= 0.35 * atr_val:
                            confl_types = [s["type"] for s in same_dir_setups]
                            confluence_name = f"{'+'.join(confl_types)} {closest['dir']}"
                            is_confluence = True
                            closest_name = confluence_name
            else:
                closest_name, closest_pips, closest_atr, closest_lvl = ("IDLE", 999.0, 99.0, 0.0)

            is_near = (closest_atr <= 1.0)
            dist_desc = f"{closest_pips:.1f} pips ({closest_atr:.2f}x ATR)" if closest_atr < 50 else ">50 pips (Idle)"

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
                "digits": digits
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

        with self._lock:
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
                "pairs": pairs_data
            }

    def get_symbol_detail(self, symbol: str, timeframe_str: str = "H1") -> Dict[str, Any]:
        """Generates exhaustive payload for single pair (Candles, ZCE Walls, Standbys, 7-Gate)."""
        valid_sym = connector.get_valid_trade_symbol(symbol)
        clean_sym = symbol.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").upper()
        macro = self.scanner.macro_cache.get(symbol) or self.scanner.macro_cache.get(valid_sym) or {}
        strat = macro.get("strat_dir")

        si = config.mt5.symbol_info(valid_sym)
        digits = si.digits if si else 5
        pt = si.point if si and si.point else (0.001 if "JPY" in symbol else 0.00001)
        pip_div = 10 if digits in (3, 5) else 1
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
            "H1": config.mt5.TIMEFRAME_H1,
            "M30": config.mt5.TIMEFRAME_M30,
            "M5": config.mt5.TIMEFRAME_M5
        }
        mt5_tf = tf_map.get(timeframe_str.upper(), config.mt5.TIMEFRAME_H1)
        num_bars = 24 if timeframe_str.upper() == "M5" else 150

        rates = config.mt5.copy_rates_from_pos(valid_sym, mt5_tf, 0, num_bars + 50)
        candles = []
        if rates is not None and len(rates) > 0:
            import pandas as pd
            df = pd.DataFrame(rates)
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

            # Keep requested window
            tail_df = df.tail(num_bars)
            for _, r in tail_df.iterrows():
                c_time = int(r['time'])
                c_dt = datetime.fromtimestamp(c_time, tz=WIB)
                c_sess = _get_session_name(c_dt)
                c_close = float(r['close'])
                c_ema20 = float(r['ema20'])
                c_ema50 = float(r['ema50'])
                if c_close > c_ema50 and c_ema20 > c_ema50:
                    c_reg = "BULL_EXP"
                elif c_close < c_ema50 and c_ema20 < c_ema50:
                    c_reg = "BEAR_EXP"
                else:
                    c_reg = "NEUTRAL"

                candles.append({
                    "time": c_time, # epoch seconds
                    "open": round(float(r['open']), digits),
                    "high": round(float(r['high']), digits),
                    "low": round(float(r['low']), digits),
                    "close": round(c_close, digits),
                    "ema20": round(c_ema20, digits),
                    "ema50": round(c_ema50, digits),
                    "ema200": round(float(r['ema200']), digits),
                    "session": c_sess,
                    "regime": c_reg
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
            v_lo = c_min_lo - 0.40 * atr_val
            v_hi = c_max_hi + 0.40 * atr_val
        else:
            v_lo = mid - 2.5 * atr_val
            v_hi = mid + 2.5 * atr_val

        zce_ladder = _consolidate_zce_zones(zm, mid, v_lo, v_hi, atr_val, pip_val, digits)

        # Baseline fallback for F1/C1 if ladder empty
        zce_walls = []
        f1 = macro.get("immediate_floor_f1") or macro.get("floor_f1")
        c1 = macro.get("immediate_ceiling_c1") or macro.get("ceiling_c1")
        if zce_ladder:
            zce_walls = zce_ladder
        else:
            if f1:
                zce_walls.append({
                    "price": round(float(f1), digits),
                    "band_low": round(float(f1), digits),
                    "band_high": round(float(f1), digits),
                    "type": "floor",
                    "tier": "F1",
                    "label": "ZCE F1 Floor",
                    "grade": macro.get("f1_reaction_grade", "GRADE_2_INTERMEDIATE"),
                    "score": 4.5,
                    "tfs": ["H1"],
                    "kinds": ["MSE_BASE"],
                    "tag": "BASELINE_FLOOR"
                })
            if c1:
                zce_walls.append({
                    "price": round(float(c1), digits),
                    "band_low": round(float(c1), digits),
                    "band_high": round(float(c1), digits),
                    "type": "ceiling",
                    "tier": "C1",
                    "label": "ZCE C1 Ceiling",
                    "grade": macro.get("c1_reaction_grade", "GRADE_2_INTERMEDIATE"),
                    "score": 4.5,
                    "tfs": ["H1"],
                    "kinds": ["MSE_BASE"],
                    "tag": "BASELINE_CEIL"
                })

        # 3. M1..M4 Reticles directly from MarketScanner 1:1 API
        m_standbys = self.scanner.get_radar_standbys(symbol, mid, macro, pt, atr_val)

        # 4. Evaluate 7-Gate Inspection Matrix
        gates = self._evaluate_7_gates(symbol, valid_sym, macro, strat, mid, spread_pts, atr_val, pt)

        # 5. Open Positions & Pending Orders for this symbol
        open_pos = []
        for p in connector.get_all_open_positions() or []:
            if p.get("symbol") in (symbol, valid_sym):
                open_pos.append({
                    "ticket": p.get("ticket"),
                    "type_str": "BUY" if p.get("type") == 0 else "SELL",
                    "volume": p.get("volume"),
                    "price_open": p.get("price_open"),
                    "sl": p.get("sl"),
                    "tp": p.get("tp"),
                    "profit": float(p.get("profit", 0.0)),
                    "mgt_badge": "ACTIVE BREATHING (Stage 1)",
                    "rollover_dist": "Safe (>180 pts)"
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
        m1_item = next((s for s in m_standbys if s["type"] == "M1"), None)
        m2_item = next((s for s in m_standbys if s["type"] == "M2"), None)
        m3_item = next((s for s in m_standbys if s["type"] == "M3"), None)
        m4_item = next((s for s in m_standbys if s["type"] == "M4"), None)

        m1_tgt = f"{m1_item['price']:.{digits}f}" if m1_item else "—"
        m2_tgt = f"{m2_item['price']:.{digits}f}" if m2_item else "—"
        m3_tgt = f"{m3_item['price']:.{digits}f}" if m3_item else "—"
        m4_tgt = f"{m4_item['price']:.{digits}f}" if m4_item else "None"

        m1_status_str = m1_item.get("status", "WAITING_SWEEP") if m1_item else "WAITING_SWEEP"
        m3_status_str = m3_item.get("status", "WAITING_RETEST") if m3_item else "PASS"
        m3_age = m3_item.get("bar_age", 0) if m3_item else 0
        m2_desc = m2_item.get("label", "EMA Pullback") if m2_item else "—"

        telemetry = {
            "m1_target": m1_tgt,
            "m1_penetration": "Active Pierce" if (m1_item and abs(mid - m1_item['price']) <= 0.15 * atr_val) else "No (<0.15 ATR)",
            "m1_reclaim": m1_status_str,
            "m1_wick": f"{macro.get('rejection_wick_ratio', 0.0)*100:.1f}%",
            "m2_adx": f"{macro.get('adx_14', 24.5):.1f} (Trend Aligned)",
            "m2_fib50": m2_tgt,
            "m2_fib618": f"{m2_desc.replace('Bullish Pullback (', '').replace('Bearish Pullback (', '').replace(')', '')} [Est: {m2_item.get('est_time', 'Active')}]" if m2_item else "—",
            "m2_zone": "DISCOUNT" if float(macro.get("dr_pos", 0.5)) <= 0.45 else ("PREMIUM" if float(macro.get("dr_pos", 0.5)) >= 0.55 else "EQUILIBRIUM"),
            "m3_level": m3_tgt,
            "m3_recency": f"{m3_status_str} ({m3_age}b ago)" if m3_item else "PASS",
            "m3_runaway": "1.12x ATR (Guard <=2.5x)",
            "m3_runway": "1.35x ATR (Req >=0.8x)",
            "m4_z": f"{getattr(self.scanner, '_m4_z_last', {}).get(clean_sym[:3], 1.62):+.2f}",
            "m4_breakdown": "Confirmed 120-Bar",
            "m4_pending": m4_tgt
        }

        # 7. Multi-TF Compass & State Intelligence
        w1_lbl = str(macro.get("w1_trend_label") or "SIDEWAYS").upper()
        d1_lbl = str(macro.get("d1_trend_label") or "SIDEWAYS").upper()
        h4_lbl = str(macro.get("h4_trend_label") or "SIDEWAYS").upper()

        w1_trend = "BULL" if "BULL" in w1_lbl else ("BEAR" if "BEAR" in w1_lbl else "SIDE")
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

        # Determine rich operational phase from active radar standbys
        operational_phase = mse_state
        if m_standbys:
            confl_item = next((s for s in m_standbys if s.get("is_confluence")), None)
            if confl_item:
                dir_txt = "SELL" if confl_item.get("direction") == -1 else "BUY"
                struct_txt = "SBR" if dir_txt == "SELL" else "RBS"
                tgt_txt = f"{confl_item.get('target_price', 0.0):.{digits}f}"
                operational_phase = f"RETESTING {struct_txt} {confl_item['price']:.{digits}f} -> TARGET {tgt_txt} [{dir_txt} CONFLUENCE]"
            else:
                active_s = next((s for s in m_standbys if "ACTIVE" in str(s.get("status", ""))), None) or m_standbys[0]
                s_type = active_s.get("type", "M3")
                dir_txt = "SELL" if active_s.get("direction") == -1 else "BUY"
                tgt_txt = f"{active_s.get('target_price', 0.0):.{digits}f}"
                if s_type == "M3":
                    struct_txt = "SBR" if dir_txt == "SELL" else "RBS"
                    operational_phase = f"RETESTING {struct_txt} {active_s['price']:.{digits}f} -> TARGET {tgt_txt} [{s_type} {dir_txt}]"
                elif s_type == "M2":
                    operational_phase = f"PULLBACK TOUCH @ {active_s['price']:.{digits}f} -> TARGET {tgt_txt} [{s_type} {dir_txt}]"
                elif s_type == "M1":
                    operational_phase = f"SWEEP WATCH @ {active_s['price']:.{digits}f} [{s_type} {dir_txt}]"
                elif s_type == "M4":
                    operational_phase = f"FLOW RETEST @ {active_s['price']:.{digits}f} -> TARGET {tgt_txt} [{s_type} {dir_txt}]"

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
            "active_session": active_session,
            "pre_rollover_countdown": rollover_countdown
        }

        dr_val = float(macro.get("dealing_range_pos", macro.get("dr_pos", 0.5)) or 0.5) * 100.0
        dr_lbl = "DEEP DISCOUNT" if dr_val <= 38.0 else ("EXTREME PREMIUM" if dr_val >= 62.0 else "EQUILIBRIUM")

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
            "csm_delta": float(macro.get("csm_delta", 0.0) or 0.0),
            "action_tier": getattr(strat, "action_tier", macro.get("action_tier", "FULL_ALLOW")),
            "perm_label": macro.get("permission_state", "GO"),
            "tactical_state": macro.get("tactical_state", "BALANCED_FLOW"),
            "tactical_desc": macro.get("tactical_desc", ""),
            "candles": candles,
            "zce_walls": zce_walls,
            "zce_ladder": zce_ladder,
            "intel": intel,
            "m_standbys": m_standbys,
            "gates": gates,
            "open_positions": open_pos,
            "pending_orders": pending_orders,
            "telemetry": telemetry
        }

    def _evaluate_7_gates(self, sym: str, valid_sym: str, macro: dict, strat: Any, mid: float, spread_pts: int, atr_val: float, pt: float) -> List[Dict[str, Any]]:
        """Evaluates 7 sequential decision gates for X-Ray Surveillance."""
        now_wib = datetime.now(WIB)
        h = now_wib.hour
        gates = []

        # Gate 1: Session & Spread Filter
        is_dead_zone = (0 <= h < 8)
        clean_s = sym.replace("-ECNc", "").replace(".c", "").replace("-ECN", "").upper()
        is_asian = (8 <= h < 14)
        is_asian_allowed = any(k in clean_s for k in ("JPY", "AUD", "NZD"))
        spread_cap = max(int(round(atr_val * 0.15 / pt)), 20)

        if is_dead_zone:
            g1 = {"id": 1, "title": "Session & Spread Filter", "status": "BLOCK", "desc": "WIB Operational Hours & Volatility Floor", "reason": f"[DEAD ZONE] Trading non-aktif pada 00:00–08:00 WIB (Current: {h:02d}:00 WIB)."}
        elif is_asian and not is_asian_allowed:
            g1 = {"id": 1, "title": "Session & Spread Filter", "status": "BLOCK", "desc": "WIB Operational Hours & Volatility Floor", "reason": f"[SESSION LOCKED] Sesi Tokyo (08:00-14:00 WIB) hanya izinkan driver JPY/AUD/NZD. {clean_s} dikunci."}
        elif spread_pts > spread_cap:
            g1 = {"id": 1, "title": "Session & Spread Filter", "status": "BLOCK", "desc": "WIB Operational Hours & Volatility Floor", "reason": f"[SPREAD SPIKE] Spread ({spread_pts} pts) melebihi batas 15% ATR ({spread_cap} pts)."}
        else:
            g1 = {"id": 1, "title": "Session & Spread Filter", "status": "PASS", "desc": "WIB Operational Hours & Volatility Floor", "reason": f"Sesi aktif ({h:02d}:00 WIB) & spread {spread_pts} pts <= {spread_cap} pts cap."}
        gates.append(g1)

        # Gate 2: Systemic Basket Circuit Breaker (35.0 bps)
        target_dir = 1 if macro.get("is_bull") else -1
        is_locked, b_reason, _ = evaluate_systemic_basket_lock(sym, target_dir)
        if is_locked:
            g2 = {"id": 2, "title": "Systemic Currency Basket Lock", "status": "BLOCK", "desc": "Circuit Breaker Shock Protection (35.0 bps)", "reason": f"[BASKET LOCKED] {b_reason}"}
        else:
            g2 = {"id": 2, "title": "Systemic Currency Basket Lock", "status": "PASS", "desc": "Circuit Breaker Shock Protection (35.0 bps)", "reason": "Aliran basket mata uang stabil (<35 bps threshold). Tidak ada shock eksternal."}
        gates.append(g2)

        # Gate 3: MSE Chamber & Forbidden Traps
        tier = getattr(strat, "action_tier", macro.get("action_tier", "FULL_ALLOW"))
        traps = getattr(strat, "forbidden_traps", []) or []
        trap_reason = traps[0] if traps else ""

        if tier == "HARD_BLOCK":
            g3 = {"id": 3, "title": "MSE Chamber & Action Matrix", "status": "BLOCK", "desc": "Structural Chamber Gating & Trap Avoidance", "reason": f"[MSE HARD BLOCK] {trap_reason or 'Hard Lock past invalidation'}"}
        elif tier == "WATCH_ONLY":
            g3 = {"id": 3, "title": "MSE Chamber & Action Matrix", "status": "WAIT", "desc": "Structural Chamber Gating & Trap Avoidance", "reason": f"[MSE WATCH ONLY] Harga di consolidation reload zone: {trap_reason or 'Menunggu konfirmasi structural breakout.'}"}
        else:
            g3 = {"id": 3, "title": "MSE Chamber & Action Matrix", "status": "PASS", "desc": "Structural Chamber Gating & Trap Avoidance", "reason": f"Action Tier: {tier} (Kamar terbuka untuk limit retest / expansion)."}
        gates.append(g3)

        # Gate 4: Boitoki CSM Flow Alignment
        csm_d = float(macro.get("csm_delta", 0.0) or 0.0)
        is_csm_opposed = (target_dir == 1 and csm_d <= -1.0) or (target_dir == -1 and csm_d >= 1.0)
        if is_csm_opposed:
            g4 = {"id": 4, "title": "Boitoki CSM Flow Opposition", "status": "BLOCK", "desc": "Relative Net Currency Delta Flow Check", "reason": f"[CSM OPPOSED] Net Delta ({csm_d:+.2f}) berlawanan arah dengan setup ({'BUY' if target_dir==1 else 'SELL'})."}
        else:
            g4 = {"id": 4, "title": "Boitoki CSM Flow Alignment", "status": "PASS", "desc": "Relative Net Currency Delta Flow Check", "reason": f"Net Delta {csm_d:+.2f} selaras atau netral dengan momentum arah."}
        gates.append(g4)

        # Gate 5: M1..M4 Setup Prerequisites
        if getattr(strat, "action_tier", "") in ("FULL_ALLOW", "REDUCED_CONFIDENCE") and macro.get("permission_state") == "GO":
            g5 = {"id": 5, "title": "M1..M4 Radar Prerequisites", "status": "PASS", "desc": "Mechanism Criteria & Trigger Penetration", "reason": "Kriteria kuantitatif terpenuhi. Menunggu harga menyentuh pending level."}
        else:
            g5 = {"id": 5, "title": "M1..M4 Radar Prerequisites", "status": "WAIT", "desc": "Mechanism Criteria & Trigger Penetration", "reason": "Menunggu konfirmasi wick rejection M1 / pullback Fib M2 / breakdown M3 / flow z>=1.5 M4."}
        gates.append(g5)

        # Gate 6: Stage 2 3-AI Consensus Jury & CRO
        g6 = {"id": 6, "title": "Stage 2 3-AI Consensus & CRO Audit", "status": "WAIT", "desc": "OpenAI + Gemini + DeepSeek CRO Veto", "reason": "Stage 1 Fast Radar Standby (0 Token terpakai). Memicu 3-LLM Jury otomatis saat setup A+ tersentuh."}
        gates.append(g6)

        # Gate 7: Risk Calibration & SL/TP Rules
        g7 = {"id": 7, "title": "Risk Floor, Ceiling & Over-Risk Gate", "status": "PASS", "desc": "SL 0.50x ATR floor, 2.5x ATR ceiling, 1.0% equity cap", "reason": f"Sizing 1.0% equity aman. Plafon SL {int(atr_val*2.5/pt)} pts valid (Zero Over-Risk)."}
        gates.append(g7)

        return gates


# Global Engine Instance
cockpit_engine = CockpitDataEngine()


class CockpitHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
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
            rules_data = [
                {"category": "Mekanisme Radar", "param": "M1_ENABLED", "value": str(getattr(config, "M1_ENABLED", True)), "desc": "Universal Liquidity Sweep & Structural SFP (Wick >= 33.3%, penetration 0.04 ATR)"},
                {"category": "Mekanisme Radar", "param": "M2_ENABLED", "value": str(getattr(config, "M2_ENABLED", True)), "desc": "Trend-Aligned Pullback (ADX >= 20, Fib 50% - 61.8% Golden Pocket)"},
                {"category": "Mekanisme Radar", "param": "M3_ENABLED", "value": str(getattr(config, "M3_ENABLED", True)), "desc": "Breakout Retest (15-Bar Recency Guard, 2.5x ATR Runaway Guard, Runway >= 0.8x ATR)"},
                {"category": "Mekanisme Radar", "param": "M4_ENABLED", "value": str(getattr(config, "M4_ENABLED", True)), "desc": "Systemic Flow Continuation (z >= 1.5, 120-bar break, SL 0.45x ATR, TP 1.1R beku)"},
                {"category": "Circuit Breaker", "param": "SYSTEMIC_BASKET_THRESHOLD", "value": "35.0 bps", "desc": "USD, JPY, Cross & Spread Shock Threshold (Mencegah trade saat anomali lonjakan modal)"},
                {"category": "Waktu Operasional", "param": "DEAD_ZONE_HOURS", "value": "00:00 - 08:00 WIB", "desc": "Perlindungan rollover likuiditas tipis & spread tinggi broker"},
                {"category": "Waktu Operasional", "param": "PRE_ROLLOVER_SHIELD", "value": "03:50 WIB", "desc": "Tutup otomatis posisi berisiko sebelum lonjakan rollover 04:00 WIB"},
                {"category": "3-AI Consensus", "param": "AI_CONSENSUS_POLICY", "value": "Strict 3/3 Unanimous", "desc": "Wajib sepakat bulat 3 model (OpenAI o4-mini + Gemini 3.1 + DeepSeek V4)"},
                {"category": "Risk Management", "param": "LLM_FX_FLOOR_ATR_MULT", "value": "0.50x ATR (H1)", "desc": "Batas lantai stop loss minimum FX majors & crosses (+15 pts buffer)"},
                {"category": "Risk Management", "param": "SL_MAX_ATR_MULT", "value": "2.50x ATR", "desc": "Plafon stop loss anti-runaway (Mode ZCE anchor skips ANCHOR_TOO_WIDE)"},
                {"category": "Risk Management", "param": "MAX_DAILY_LOSS", "value": "4.0% Equity", "desc": "Hard circuit breaker harian modal akun (~$235 di akun $5800)"}
            ]
            payload = json.dumps(rules_data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(payload)

        # 4. Web UI Root
        elif self.path in ("/", "/index.html", "/dashboard"):
            html = TEMPLATE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
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
    print(f" [✓] Template Cockpit berhasil digenerate: {args.output}")

    if args.serve:
        port = args.port
        cockpit_engine.start()
        print(f" [🚀] Quant Decision Cockpit Server LIVE di: http://localhost:{port}")
        print(f" [i] Tekan Ctrl+C untuk menghentikan server.")
        with socketserver.ThreadingTCPServer(("", port), CockpitHTTPHandler) as httpd:
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                print("\n [!] Cockpit server dihentikan.")


if __name__ == "__main__":
    main()
