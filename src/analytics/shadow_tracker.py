"""
Quant Shadow Tracker (Unconstrained Data Collector)
Merekam, melacak, dan menganalisis 100% peluang kuantitatif Stage 1 Fast Radar (M1, M2, M3, M4)
di seluruh 26 FX pair + BTC secara paralel tanpa terhalang batasan slot MT5 (MAX_OPEN_POSITIONS).

Menyimpan data telemetri ke:
1. data/quant_shadow_trades.jsonl (Append-only completed/resolved trades)
2. data/quant_shadow_state.json (Active & pending orders state, persistent across restarts)
"""

import os
import json
import time
import logging
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any

import config

logger = logging.getLogger("shadow_tracker")
WIB = ZoneInfo("Asia/Jakarta")

SHADOW_STATE_FILE = os.path.join(config.DATA_DIR, "quant_shadow_state.json")
SHADOW_TRADES_LOG = os.path.join(config.DATA_DIR, "quant_shadow_trades.jsonl")


@dataclass
class ShadowTrade:
    shadow_id: str
    symbol: str
    setup_type: str                  # M1_SWEEP, M2_PULLBACK, M3_BREAKOUT_RETEST, M4_SYSTEMIC_FLOW
    direction: str                   # BUY or SELL
    entry_type: str                  # market, buy_limit, sell_limit
    entry_price: float
    sl_price: float
    tp_price: float
    sl_points: int
    tp_points: int
    risk_reward: float
    created_at: str                  # ISO 8601 WIB string
    status: str = "PENDING"          # PENDING, ACTIVE, RESOLVED
    outcome: Optional[str] = None    # TP_HIT, SL_HIT, EXPIRED_NO_FILL, EXPIRED_TIMEOUT, TIME_DECAY_EXIT
    fill_time: Optional[str] = None
    resolved_time: Optional[str] = None
    exit_price: Optional[float] = None
    net_r: Optional[float] = None
    peak_mfe_r: float = 0.0          # Max Favorable Excursion in R
    max_mae_r: float = 0.0           # Max Adverse Excursion in R
    bars_held: int = 0
    mt5_disposition: str = "EXECUTED_MT5"  # EXECUTED_MT5, SKIPPED_SLOT_FULL, SKIPPED_RISK_BLOCK, SKIPPED_VETO
    mt5_ticket: Optional[int] = None
    action_tier: str = "FULL_ALLOW"
    current_price: Optional[float] = None
    floating_points: Optional[int] = None
    floating_r: Optional[float] = None
    current_sl: Optional[float] = None
    bep_activated: bool = False
    trailing_activated: bool = False
    invalidation_dist: Optional[float] = None
    sl_effective: Optional[int] = None
    sl_atr_ratio: Optional[float] = None
    tp_atr_ratio: Optional[float] = None
    friction_ratio: Optional[float] = None
    session_window: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShadowTrade":
        fields = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in fields}
        return cls(**filtered)


class QuantShadowTracker:
    """
    Virtual Shadow Order Engine that runs passively in parallel with live execution.
    Tracks entry triggers, MAE/MFE excursions, and outcome resolutions (TP/SL/Expiration).
    """

    _instance: Optional["QuantShadowTracker"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(QuantShadowTracker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._lock = threading.RLock()
        self._last_state_mtime: float = 0.0
        self.active_trades: List[ShadowTrade] = []
        self._stats = {
            "total_recorded": 0,
            "total_resolved": 0,
            "tp_hits": 0,
            "sl_hits": 0,
            "expired_count": 0,
            "cumulative_net_r": 0.0
        }
        self._recent_resolved: List[Dict[str, Any]] = []
        self._resolved_ids: set = set()
        self._load_state()
        self._initialized = True
        logger.info(f"[SHADOW TRACKER] Initialized with {len(self.active_trades)} active/pending shadow trades.")

    def _load_state(self):
        """Loads existing state from quant_shadow_state.json if available."""
        with self._lock:
            try:
                if os.path.exists(SHADOW_STATE_FILE):
                    self._last_state_mtime = os.path.getmtime(SHADOW_STATE_FILE)
                    with open(SHADOW_STATE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.active_trades = [ShadowTrade.from_dict(t) for t in data.get("active_trades", [])]
                    self._stats = data.get("stats", self._stats)
                    self._recent_resolved = data.get("recent_resolved", [])
                    self._resolved_ids = {r.get("shadow_id") for r in self._recent_resolved if r.get("shadow_id")}
            except Exception as e:
                logger.error(f"[SHADOW TRACKER LOAD ERROR] {e}")
                self.active_trades = []

    def reload_state_if_modified(self) -> bool:
        """
        Reloads state from disk if file was modified by another process (e.g. main.py vs dashboard.py).
        Returns True if state was reloaded, False otherwise.
        """
        with self._lock:
            try:
                if os.path.exists(SHADOW_STATE_FILE):
                    mtime = os.path.getmtime(SHADOW_STATE_FILE)
                    if mtime > self._last_state_mtime:
                        self._load_state()
                        return True
            except Exception as e:
                logger.debug(f"[SHADOW RELOAD CHECK ERROR] {e}")
            return False

    def get_active_trades_enriched(self) -> List[Dict[str, Any]]:
        """
        Returns active trades enriched with real-time MT5 current_price, floating_points, and floating_r.
        Safely callable from dashboard.py, reporting scripts, or CLI.
        """
        with self._lock:
            self.reload_state_if_modified()
            enriched = []

            # Proactively gather live MT5 open positions
            raw_pos = []
            try:
                if hasattr(config, "mt5") and hasattr(config.mt5, "positions_get"):
                    raw_pos = config.mt5.positions_get() or []
            except Exception:
                pass

            state_needs_save = False
            # 1. Detach tickets if MT5 comment conflicts with setup_type
            for t in self.active_trades:
                if t.mt5_ticket:
                    matched_p = next((p for p in raw_pos if p.ticket == t.mt5_ticket), None)
                    if matched_p:
                        p_comment = str(getattr(matched_p, "comment", "")).upper()
                        if any(k in p_comment for k in ("TREND", "MULTI", "UNIVER", "FLOW", "DBD", "RBR")):
                            matches = ("TREND" in p_comment and "TREND" in t.setup_type) or \
                                      ("MULTI" in p_comment and "MULTI" in t.setup_type) or \
                                      ("UNIVER" in p_comment and "UNIVER" in t.setup_type) or \
                                      ("FLOW" in p_comment and "FLOW" in t.setup_type) or \
                                      (("DBD" in p_comment or "RBR" in p_comment) and ("DBD" in t.setup_type or "RBR" in t.setup_type))
                            if not matches:
                                logger.info(f"[SHADOW DETACH] Detaching mismatched ticket #{t.mt5_ticket} from {t.shadow_id} ({t.setup_type} != {p_comment})")
                                t.mt5_ticket = None
                                t.mt5_disposition = "SKIPPED_MAX_POSITIONS"
                                state_needs_save = True
                    else:
                        # Tiket tidak ada di posisi open MT5: cek apakah deal closed atau pending order cancelled/expired
                        is_resolved = False
                        outcome_tag = "EXPIRED_MT5"
                        exit_price = t.entry_price
                        net_r = 0.0
                        if hasattr(config, "mt5"):
                            try:
                                if hasattr(config.mt5, "history_deals_get"):
                                    deals = config.mt5.history_deals_get(position=t.mt5_ticket)
                                    if deals:
                                        for d in deals:
                                            entry_val = getattr(d, "entry", -1)
                                            if entry_val == 1:  # DEAL_ENTRY_OUT
                                                is_resolved = True
                                                exit_price = float(getattr(d, "price", t.entry_price))
                                                p_usd = float(getattr(d, "profit", 0.0))
                                                risk_dist = abs(t.entry_price - t.sl_price)
                                                if risk_dist > 0:
                                                    realized_pts = (exit_price - t.entry_price) if t.direction == "BUY" else (t.entry_price - exit_price)
                                                    net_r = round(realized_pts / risk_dist, 2)
                                                outcome_tag = "TP_HIT" if p_usd > 0 else ("SL_HIT" if p_usd < 0 else "RESOLVED_CLOSED")
                                                break
                                if not is_resolved and hasattr(config.mt5, "history_orders_get"):
                                    h_orders = config.mt5.history_orders_get(ticket=t.mt5_ticket)
                                    if h_orders:
                                        ord_state = getattr(h_orders[0], "state", 0)
                                        pos_id = getattr(h_orders[0], "position_id", 0)
                                        if ord_state in (2, 5, 6) and pos_id == 0:
                                            is_resolved = True
                                            outcome_tag = "EXPIRED_MT5"
                                            net_r = 0.0
                            except Exception:
                                pass

                        if is_resolved:
                            logger.info(f"[SHADOW DETACH RESOLVED] Resolving inactive MT5 ticket #{t.mt5_ticket} from {t.shadow_id} ({outcome_tag})")
                            t.status = "RESOLVED"
                            t.outcome = outcome_tag
                            t.resolved_time = datetime.now(WIB).isoformat()
                            t.exit_price = exit_price
                            t.net_r = net_r
                            t.mt5_ticket = None
                            if outcome_tag in ("TP_HIT", "SL_HIT", "RESOLVED_CLOSED"):
                                t.mt5_disposition = "EXECUTED_MT5_RESOLVED"
                            elif outcome_tag == "EXPIRED_MT5":
                                t.mt5_disposition = "MT5_ORDER_CANCELLED"
                            else:
                                t.mt5_disposition = "SKIPPED_EXPIRED"
                            state_needs_save = True

            # 2. Match unclaimed MT5 open positions
            claimed_tickets = {t.mt5_ticket for t in self.active_trades if t.mt5_ticket}
            for t in self.active_trades:
                if not t.mt5_ticket or t.mt5_disposition != "EXECUTED_MT5":
                    clean_sym = t.symbol.split("-")[0].split(".")[0]
                    for p in raw_pos:
                        if p.ticket in claimed_tickets:
                            continue
                        p_dir = "BUY" if getattr(p, "type", 0) == 0 else "SELL"
                        p_clean = getattr(p, "symbol", "").split("-")[0].split(".")[0]
                        if (p.symbol == t.symbol or p_clean == clean_sym) and p_dir == t.direction:
                            p_comment = str(getattr(p, "comment", "")).upper()
                            matches = True
                            if any(k in p_comment for k in ("TREND", "MULTI", "UNIVER", "FLOW", "DBD", "RBR")):
                                matches = ("TREND" in p_comment and "TREND" in t.setup_type) or \
                                          ("MULTI" in p_comment and "MULTI" in t.setup_type) or \
                                          ("UNIVER" in p_comment and "UNIVER" in t.setup_type) or \
                                          ("FLOW" in p_comment and "FLOW" in t.setup_type) or \
                                          (("DBD" in p_comment or "RBR" in p_comment) and ("DBD" in t.setup_type or "RBR" in t.setup_type))
                            if matches:
                                t.mt5_ticket = p.ticket
                                t.mt5_disposition = "EXECUTED_MT5"
                                claimed_tickets.add(p.ticket)
                                state_needs_save = True
                                break

                d = t.to_dict()
                try:
                    sym = d.get("symbol", "")
                    if hasattr(config, "mt5") and hasattr(config.mt5, "symbol_info_tick"):
                        si = config.mt5.symbol_info_tick(sym)
                        if si and si.bid > 0 and si.ask > 0:
                            mid = (si.bid + si.ask) / 2.0
                            s_info = config.mt5.symbol_info(sym)
                            pt = getattr(s_info, "point", 0.00001) or 0.00001
                            digits = getattr(s_info, "digits", 5)
                            entry = float(d.get("entry_price", 0.0))
                            sl = float(d.get("sl_price", 0.0))
                            risk = abs(entry - sl)
                            direction = d.get("direction", "BUY")

                            d["current_price"] = round(mid, digits)
                            if d.get("status") == "ACTIVE" and risk > 0:
                                curr_r = (mid - entry) / risk if direction == "BUY" else (entry - mid) / risk
                                curr_pts = int(round((mid - entry) / pt)) if direction == "BUY" else int(round((entry - mid) / pt))
                                d["floating_r"] = round(curr_r, 2)
                                d["floating_points"] = curr_pts
                            elif d.get("status") == "PENDING":
                                dist_pts = int(round((entry - si.ask) / pt)) if direction == "BUY" else int(round((si.bid - entry) / pt))
                                d["floating_points"] = dist_pts
                                d["floating_r"] = 0.0
                except Exception:
                    pass
                enriched.append(d)

            if state_needs_save:
                resolved_now = [t for t in self.active_trades if t.status == "RESOLVED"]
                for r in resolved_now:
                    self._record_resolved(r)
                self.active_trades = [t for t in self.active_trades if t.status in ("ACTIVE", "PENDING")]
                self._save_state()

            return [d for d in enriched if d.get("status") in ("ACTIVE", "PENDING")]

    def _save_state(self):
        """Persists active state to quant_shadow_state.json atomically."""
        with self._lock:
            try:
                data = {
                    "updated_at": datetime.now(WIB).isoformat(),
                    "active_trades": [t.to_dict() for t in self.active_trades],
                    "stats": self._stats,
                    "recent_resolved": self._recent_resolved[-30:]
                }
                tmp_path = SHADOW_STATE_FILE + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                # Retry replace up to 5 times to handle Windows file locking from concurrent readers (e.g. dashboard.py)
                saved = False
                for attempt in range(5):
                    try:
                        if os.path.exists(SHADOW_STATE_FILE):
                            os.replace(tmp_path, SHADOW_STATE_FILE)
                        else:
                            os.rename(tmp_path, SHADOW_STATE_FILE)
                        saved = True
                        break
                    except (PermissionError, OSError):
                        time.sleep(0.05 * (attempt + 1))

                if not saved:
                    # Fallback direct write if os.replace is held by Windows reader
                    with open(SHADOW_STATE_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass

                if os.path.exists(SHADOW_STATE_FILE):
                    self._last_state_mtime = os.path.getmtime(SHADOW_STATE_FILE)
            except Exception as e:
                logger.error(f"[SHADOW TRACKER SAVE ERROR] {e}")

    def _append_resolved_log(self, trade: ShadowTrade):
        """Appends resolved shadow trade to JSON Lines log."""
        try:
            line = json.dumps(trade.to_dict(), ensure_ascii=False)
            with open(SHADOW_TRADES_LOG, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            logger.error(f"[SHADOW TRACKER LOG ERROR] {e}")

    def register_candidate(
        self,
        candidate: Any,
        entry_type: str,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        sl_points: int,
        tp_points: int,
        mt5_disposition: str = "EXECUTED_MT5",
        mt5_ticket: Optional[int] = None
    ) -> Optional[ShadowTrade]:
        """
        Registers a Stage 1 candidate setup into the Virtual Shadow Order Book.
        Includes deduplication guard to prevent duplicate registration within 30 minutes.
        """
        with self._lock:
            sym = getattr(candidate, "symbol", "")
            setup_type = getattr(candidate, "setup_type", "UNKNOWN")
            dir_int = getattr(candidate, "direction", 1)
            dir_str = "BUY" if dir_int == 1 else "SELL"
            action_tier = getattr(candidate, "action_tier", "FULL_ALLOW")

            now_dt = datetime.now(WIB)
            now_iso = now_dt.isoformat()

            # Deduplication check: Do not duplicate if active or pending trade exists on same symbol & direction
            for existing in self.active_trades:
                if existing.symbol == sym and existing.direction == dir_str:
                    if existing.status in ("ACTIVE", "PENDING"):
                        logger.info(
                            f"[SHADOW DEDUPLICATED] {sym} {dir_str} sudah memiliki posisi {existing.status} di Paper Trade "
                            f"(ID: {existing.shadow_id}, setup: {existing.setup_type}). Menolak pembukaan tiket concurrent duplikat."
                        )
                        return None

            rr = round(tp_points / sl_points, 2) if sl_points > 0 else 1.5

            shadow_id = f"SHADOW_{now_dt.strftime('%Y%m%d_%H%M%S')}_{sym.replace('-ECNc','').replace('.c','').replace('-ECN','')}_{setup_type[:6]}"

            initial_status = "ACTIVE" if entry_type == "market" else "PENDING"
            fill_time = now_iso if initial_status == "ACTIVE" else None

            c_meta = getattr(candidate, "metadata", {}) or {}
            f1_grade = c_meta.get("f1_grade") or getattr(candidate, "f1_reaction_grade", None) or "UNKNOWN"
            c1_grade = c_meta.get("c1_grade") or getattr(candidate, "c1_reaction_grade", None) or "UNKNOWN"
            wall_grade = f1_grade if dir_str == "BUY" else c1_grade
            z_f1 = c_meta.get("zce_f1") or c_meta.get("zce_f1_price") or getattr(candidate, "floor_f1", None) or getattr(candidate, "f1", None)
            z_c1 = c_meta.get("zce_c1") or c_meta.get("zce_c1_price") or getattr(candidate, "ceiling_c1", None) or getattr(candidate, "c1", None)

            # 6 Telemetry Fields (11 Sep 2026 - Pilar 0 Telemetry Engine)
            cand_atr = float(getattr(candidate, "current_atr_pts", 0.0) or 0.0)
            cand_spr = int(getattr(candidate, "current_spread_pts", 0) or 0)
            sl_eff = int(sl_points)
            sl_atr_r = round(sl_eff / cand_atr, 2) if cand_atr > 0 else None
            tp_atr_r = round(int(tp_points) / cand_atr, 2) if cand_atr > 0 else None
            comm_pts = 6
            fric_r = round((cand_spr + comm_pts) / max(sl_eff, 1), 4) if sl_eff > 0 else None
            now_h = now_dt.hour
            sess_win = "Tokyo" if 7 <= now_h < 14 else ("London" if 14 <= now_h < 18 else ("NY" if 18 <= now_h < 24 else "DeadZone"))
            inv_dist = c_meta.get("invalidation_dist") or getattr(candidate, "invalidation_dist", None)
            if inv_dist is None:
                orig = c_meta.get("anchor_level") or (getattr(candidate, "key_support", None) if dir_str == "BUY" else getattr(candidate, "key_resistance", None))
                if orig and isinstance(orig, (int, float)) and orig > 0:
                    inv_dist = round(abs(entry_price - orig), 5)

            trade = ShadowTrade(
                shadow_id=shadow_id,
                symbol=sym,
                setup_type=setup_type,
                direction=dir_str,
                entry_type=entry_type,
                entry_price=entry_price,
                sl_price=sl_price,
                tp_price=tp_price,
                sl_points=sl_points,
                tp_points=tp_points,
                risk_reward=rr,
                created_at=now_iso,
                status=initial_status,
                fill_time=fill_time,
                mt5_disposition=mt5_disposition,
                mt5_ticket=mt5_ticket,
                action_tier=action_tier,
                current_sl=sl_price,
                bep_activated=False,
                trailing_activated=False,
                invalidation_dist=inv_dist,
                sl_effective=sl_eff,
                sl_atr_ratio=sl_atr_r,
                tp_atr_ratio=tp_atr_r,
                friction_ratio=fric_r,
                session_window=sess_win,
                metadata={
                    "setup_grade": getattr(candidate, "setup_grade", "GRADE_A"),
                    "wall_grade": str(wall_grade),
                    "f1_reaction_grade": str(f1_grade),
                    "c1_reaction_grade": str(c1_grade),
                    "zce_f1": float(z_f1) if isinstance(z_f1, (int, float)) and z_f1 > 0 else None,
                    "zce_c1": float(z_c1) if isinstance(z_c1, (int, float)) and z_c1 > 0 else None,
                    "current_atr_pts": getattr(candidate, "current_atr_pts", 0.0),
                    "current_spread_pts": getattr(candidate, "current_spread_pts", 0),
                    "dealing_range_pos": getattr(candidate, "dealing_range_pos", 0.5),
                    "csm_delta_open": float(getattr(candidate, "csm_delta", 0.0)),
                    "csm_opposed_open": bool((dir_str == "BUY" and getattr(candidate, "csm_delta", 0.0) <= -float(getattr(config, "CSM_FLOW_OPPOSED_THRESHOLD", 1.50))) or (dir_str == "SELL" and getattr(candidate, "csm_delta", 0.0) >= float(getattr(config, "CSM_FLOW_OPPOSED_THRESHOLD", 1.50)))),
                    "invalidation_dist": inv_dist,
                    "sl_effective": sl_eff,
                    "sl_atr_ratio": sl_atr_r,
                    "tp_atr_ratio": tp_atr_r,
                    "friction_ratio": fric_r,
                    "session_window": sess_win,
                }
            )

            self.active_trades.append(trade)
            self._stats["total_recorded"] += 1
            self._save_state()

            logger.info(
                f"[SHADOW REGISTERED] {trade.shadow_id} | {sym} {trade.direction} ({trade.setup_type}) "
                f"Entry: {entry_price} | SL: {sl_price} | TP: {tp_price} ({trade.risk_reward}R) | Status: {initial_status} | Disp: {mt5_disposition}"
            )
            return trade

    def get_active_shadow_for(self, symbol: str, direction: str, setup_type: str) -> Optional[ShadowTrade]:
        """Mengambil trade aktif/pending yang cocok untuk pelaporan status CLI."""
        with self._lock:
            for t in self.active_trades:
                if t.symbol == symbol and t.direction == direction and t.setup_type == setup_type:
                    return t
        return None

    def update_shadow_orders(self, connector: Any) -> List[ShadowTrade]:
        """
        Updates status of all active and pending shadow orders against live ticks.
        Detects:
        0. MT5 Deal Reconciliation (resolves closed MT5 tickets directly from broker history).
        1. Pending Fill (limit order triggered by market price).
        2. Target Proximity Invalidation (>=75% move toward TP without fill).
        3. Timeout Expiration (pending > 120 minutes).
        4. Excursion Tracking (MFE & MAE accumulation).
        5. Live Price & Floating P/L Tracking (current_price, floating_points, floating_r).
        6. TP Hit (+R) and SL Hit (-1.0R).
        7. Time Decay Stagnation Exit (> 24 hours).
        """
        with self._lock:
            if not self.active_trades:
                return []

            now_dt = datetime.now(WIB)
            now_iso = now_dt.isoformat()
            newly_resolved: List[ShadowTrade] = []
            remaining: List[ShadowTrade] = []

            # -------------------------------------------------------------
            # 0. MT5 OPEN POSITIONS QUERY (Single Batch Query)
            # -------------------------------------------------------------
            open_mt5_tickets = set()
            mt5_open_by_symbol = {}
            raw_mt5_pos = []
            try:
                if hasattr(config, "mt5") and hasattr(config.mt5, "positions_get"):
                    raw = config.mt5.positions_get()
                    if raw:
                        raw_mt5_pos = list(raw)
                        open_mt5_tickets = {p.ticket for p in raw_mt5_pos}
                        for p in raw_mt5_pos:
                            p_dir = "BUY" if getattr(p, "type", 0) == 0 else "SELL"
                            p_sym = getattr(p, "symbol", "")
                            mt5_open_by_symbol[(p_sym, p_dir)] = p
                            clean_sym = p_sym.split("-")[0].split(".")[0]
                            mt5_open_by_symbol[(clean_sym, p_dir)] = p
            except Exception:
                raw_mt5_pos = []

            be_tickets = set()
            trail_tickets = set()
            pm_file = os.path.join(config.DATA_DIR, "position_manager_state.json")
            if os.path.exists(pm_file):
                try:
                    with open(pm_file, "r") as f:
                        pm_data = json.load(f)
                        be_tickets = set(pm_data.get("break_even_tickets", []))
                        trail_tickets = set(pm_data.get("trailing_active_tickets", []))
                except Exception:
                    pass

            # Pre-pass: Detach mismatched tickets from open MT5 positions
            claimed_open_tickets = set()
            for trade in self.active_trades:
                if trade.mt5_ticket and raw_mt5_pos:
                    matched_p = next((p for p in raw_mt5_pos if p.ticket == trade.mt5_ticket), None)
                    if matched_p:
                        p_comment = str(getattr(matched_p, "comment", "")).upper()
                        if any(k in p_comment for k in ("TREND", "MULTI", "UNIVER", "FLOW", "DBD", "RBR")):
                            matches = ("TREND" in p_comment and "TREND" in trade.setup_type) or \
                                      ("MULTI" in p_comment and "MULTI" in trade.setup_type) or \
                                      ("UNIVER" in p_comment and "UNIVER" in trade.setup_type) or \
                                      ("FLOW" in p_comment and "FLOW" in trade.setup_type) or \
                                      (("DBD" in p_comment or "RBR" in p_comment) and ("DBD" in trade.setup_type or "RBR" in trade.setup_type))
                            if not matches:
                                logger.info(f"[SHADOW DETACH] Detaching mismatched ticket #{trade.mt5_ticket} from {trade.shadow_id} ({trade.setup_type} != {p_comment})")
                                trade.mt5_ticket = None
                                trade.mt5_disposition = "SKIPPED_MAX_POSITIONS"
                        if trade.mt5_ticket:
                            p_sl = getattr(matched_p, "sl", 0.0)
                            if p_sl and p_sl > 0:
                                trade.current_sl = p_sl
                            p_tp = getattr(matched_p, "tp", 0.0)
                            if p_tp and p_tp > 0:
                                trade.tp_price = p_tp
                            trade.bep_activated = (trade.mt5_ticket in be_tickets)
                            trade.trailing_activated = (trade.mt5_ticket in trail_tickets)
                    if trade.mt5_ticket:
                        claimed_open_tickets.add(trade.mt5_ticket)

            for trade in self.active_trades:
                try:
                    # ---------------------------------------------------------
                    # 0a. CHECK EXPIRED / CANCELLED PENDING ORDERS IN MT5
                    # ---------------------------------------------------------
                    if trade.status == "PENDING" and trade.mt5_ticket:
                        try:
                            if hasattr(config, "mt5") and hasattr(config.mt5, "history_orders_get"):
                                h_orders = config.mt5.history_orders_get(ticket=trade.mt5_ticket)
                                if h_orders:
                                    h_ord = h_orders[0]
                                    ord_state = getattr(h_ord, "state", 0)
                                    pos_id = getattr(h_ord, "position_id", 0)
                                    if ord_state in (2, 5, 6) and pos_id == 0:  # 2=CANCELED, 5=REJECTED, 6=EXPIRED
                                        trade.status = "RESOLVED"
                                        trade.outcome = "EXPIRED_MT5"
                                        trade.resolved_time = now_iso
                                        trade.net_r = 0.0
                                        trade.exit_price = trade.entry_price
                                        trade.mt5_disposition = "SKIPPED_EXPIRED"
                                        logger.info(f"[SHADOW EXPIRED SYNC] {trade.shadow_id} (Ticket #{trade.mt5_ticket}) resolved EXPIRED_MT5 (state={ord_state})")
                                        newly_resolved.append(trade)
                                        self._record_resolved(trade)
                                        continue
                        except Exception as e:
                            logger.debug(f"[SHADOW PENDING EXPIRED CHECK ERROR] {trade.shadow_id}: {e}")

                    # ---------------------------------------------------------
                    # 0b. PROACTIVE LIVE MT5 POSITION RECONCILIATION
                    # ---------------------------------------------------------
                    if not trade.mt5_ticket or trade.mt5_disposition != "EXECUTED_MT5":
                        clean_tr_sym = trade.symbol.split("-")[0].split(".")[0]
                        for p in (raw_mt5_pos or []):
                            if p.ticket in claimed_open_tickets:
                                continue
                            p_dir = "BUY" if getattr(p, "type", 0) == 0 else "SELL"
                            p_clean = getattr(p, "symbol", "").split("-")[0].split(".")[0]
                            if (p.symbol == trade.symbol or p_clean == clean_tr_sym) and p_dir == trade.direction:
                                p_comment = str(getattr(p, "comment", "")).upper()
                                matches = True
                                if any(k in p_comment for k in ("TREND", "MULTI", "UNIVER", "FLOW", "DBD", "RBR")):
                                    matches = ("TREND" in p_comment and "TREND" in trade.setup_type) or \
                                              ("MULTI" in p_comment and "MULTI" in trade.setup_type) or \
                                              ("UNIVER" in p_comment and "UNIVER" in trade.setup_type) or \
                                              ("FLOW" in p_comment and "FLOW" in trade.setup_type) or \
                                              (("DBD" in p_comment or "RBR" in p_comment) and ("DBD" in trade.setup_type or "RBR" in trade.setup_type))
                                if matches:
                                    trade.mt5_ticket = p.ticket
                                    trade.mt5_disposition = "EXECUTED_MT5"
                                    claimed_open_tickets.add(p.ticket)
                                    logger.info(f"[SHADOW RECONCILE] Proactively matched open MT5 position #{p.ticket} ({p.symbol} {trade.direction}) to {trade.shadow_id}")
                                    break

                    # ---------------------------------------------------------
                    # 0c. MT5 TICKET RECONCILIATION (From History Deals)
                    # ---------------------------------------------------------
                    # Auto-recover missing mt5_ticket for EXECUTED_MT5 trades from history deals
                    if not trade.mt5_ticket and trade.mt5_disposition == "EXECUTED_MT5" and trade.status in ("ACTIVE", "PENDING"):
                        try:
                            if hasattr(config, "mt5") and hasattr(config.mt5, "history_deals_get"):
                                c_time = datetime.fromisoformat(trade.created_at)
                                from_ep = int(c_time.timestamp()) - 300
                                to_ep = int(now_dt.timestamp()) + 60
                                deals_search = config.mt5.history_deals_get(from_ep, to_ep)
                                if deals_search:
                                    for d in deals_search:
                                        d_sym = getattr(d, "symbol", "")
                                        d_entry = getattr(d, "entry", -1)
                                        d_pos = getattr(d, "position_id", 0)
                                        if d_entry == 0 and d_pos > 0 and (trade.symbol in d_sym or d_sym in trade.symbol):
                                            trade.mt5_ticket = d_pos
                                            trade.mt5_disposition = "EXECUTED_MT5"
                                            logger.info(f"[SHADOW RECONCILE] Recovered missing mt5_ticket #{d_pos} for {trade.shadow_id} ({trade.symbol})")
                                            break
                        except Exception as e:
                            logger.debug(f"[SHADOW RECONCILE ERROR] {e}")

                    if trade.mt5_ticket and trade.status in ("ACTIVE", "PENDING"):
                        if trade.mt5_ticket not in open_mt5_tickets:
                            try:
                                if hasattr(config, "mt5") and hasattr(config.mt5, "history_deals_get"):
                                    deals = config.mt5.history_deals_get(position=trade.mt5_ticket)
                                    if deals:
                                        close_deal = None
                                        for d in deals:
                                            d_dict = d._asdict() if hasattr(d, "_asdict") else (d if isinstance(d, dict) else {})
                                            entry_val = d_dict.get("entry", getattr(d, "entry", -1))
                                            if entry_val == 1:  # DEAL_ENTRY_OUT
                                                close_deal = d_dict or {
                                                    "price": getattr(d, "price", 0.0),
                                                    "profit": getattr(d, "profit", 0.0),
                                                    "comment": getattr(d, "comment", "")
                                                }
                                                break
                                        if close_deal:
                                            exit_p = float(close_deal.get("price", 0.0))
                                            profit_usd = float(close_deal.get("profit", 0.0))
                                            comment = str(close_deal.get("comment", "")).lower()

                                            trade.status = "RESOLVED"
                                            trade.resolved_time = now_iso
                                            trade.exit_price = exit_p if exit_p > 0 else trade.entry_price

                                            risk_dist = abs(trade.entry_price - trade.sl_price)
                                            if risk_dist > 0:
                                                realized_pts = (trade.exit_price - trade.entry_price) if trade.direction == "BUY" else (trade.entry_price - trade.exit_price)
                                                trade.net_r = round(realized_pts / risk_dist, 2)
                                            else:
                                                trade.net_r = 0.0

                                            if "tp" in comment or profit_usd > 0:
                                                trade.outcome = "TP_HIT"
                                            elif "sl" in comment or profit_usd < 0:
                                                trade.outcome = "SL_HIT"
                                            else:
                                                trade.outcome = "RESOLVED_CLOSED"

                                            logger.info(f"[SHADOW MT5 SYNC] {trade.shadow_id} (Ticket #{trade.mt5_ticket}) resolved via MT5 deal: {trade.outcome} @ {trade.exit_price} ({trade.net_r:+.2f}R, ${profit_usd:+.2f})")
                                            newly_resolved.append(trade)
                                            self._record_resolved(trade)
                                            continue

                                    # Jika tidak ada deal penutupan, periksa apakah pending order MT5 aslinya batal/expired
                                    if hasattr(config.mt5, "history_orders_get"):
                                        h_orders = config.mt5.history_orders_get(ticket=trade.mt5_ticket)
                                        if h_orders:
                                            h_ord = h_orders[0]
                                            ord_state = getattr(h_ord, "state", 0)
                                            pos_id = getattr(h_ord, "position_id", 0)
                                            if ord_state in (2, 5, 6) and pos_id == 0:  # 2=CANCELED, 5=REJECTED, 6=EXPIRED
                                                trade.status = "RESOLVED"
                                                trade.outcome = "EXPIRED_MT5"
                                                trade.resolved_time = now_iso
                                                trade.net_r = 0.0
                                                trade.exit_price = trade.entry_price
                                                trade.mt5_disposition = "SKIPPED_EXPIRED"
                                                logger.info(f"[SHADOW ACTIVE EXPIRED SYNC] {trade.shadow_id} (Ticket #{trade.mt5_ticket}) resolved EXPIRED_MT5 (order cancelled in MT5, state={ord_state})")
                                                newly_resolved.append(trade)
                                                self._record_resolved(trade)
                                                continue
                            except Exception as e:
                                logger.debug(f"[SHADOW MT5 RECONCILE ERROR] {trade.shadow_id}: {e}")

                    tick = connector.get_current_tick(trade.symbol)
                    if not tick:
                        remaining.append(trade)
                        continue

                    ask = float(tick.get("ask", 0.0))
                    bid = float(tick.get("bid", 0.0))
                    point = float(tick.get("point", 0.00001))
                    digits = int(tick.get("digits", 5))
                    if point <= 0:
                        point = 0.00001 if "JPY" not in trade.symbol else 0.001

                    if ask <= 0 or bid <= 0:
                        remaining.append(trade)
                        continue
                    mid = (ask + bid) / 2.0
                    trade.current_price = round(mid, digits)

                    # -------------------------------------------------------------
                    # 1. PENDING ORDER EVALUATION
                    # -------------------------------------------------------------
                    if trade.status == "PENDING":
                        # Distance to entry fill in points
                        if trade.direction == "BUY":
                            dist_pts = int(round((trade.entry_price - ask) / point))
                        else:
                            dist_pts = int(round((bid - trade.entry_price) / point))
                        trade.floating_points = dist_pts
                        trade.floating_r = 0.0

                        # Check fill
                        is_filled = False
                        if trade.direction == "BUY":
                            if ask <= trade.entry_price or bid <= trade.entry_price:
                                is_filled = True
                        elif trade.direction == "SELL":
                            if bid >= trade.entry_price or ask >= trade.entry_price:
                                is_filled = True

                        if is_filled:
                            trade.status = "ACTIVE"
                            trade.fill_time = now_iso
                            trade.current_sl = trade.sl_price
                            trade.bep_activated = False
                            trade.trailing_activated = False
                            trade.peak_mfe_r = 0.0
                            trade.max_mae_r = 0.0
                            trade.floating_points = 0
                            trade.floating_r = 0.0
                            logger.info(f"[SHADOW FILLED] {trade.shadow_id} | {trade.symbol} {trade.direction} filled @ {trade.entry_price}")
                            remaining.append(trade)
                            continue

                        # Check Target Proximity Expiration (>=75% to TP without fill)
                        if getattr(config, "ENABLE_SHADOW_PROXIMITY_CANCEL", True):
                            tp_dist = abs(trade.tp_price - trade.entry_price)
                            if tp_dist > 0:
                                if trade.direction == "BUY":
                                    progress = (mid - trade.entry_price) / tp_dist
                                else:
                                    progress = (trade.entry_price - mid) / tp_dist

                                if progress >= 0.75:
                                    trade.status = "RESOLVED"
                                    trade.outcome = "EXPIRED_NO_FILL"
                                    trade.resolved_time = now_iso
                                    trade.exit_price = mid
                                    trade.net_r = 0.0
                                    newly_resolved.append(trade)
                                    self._record_resolved(trade)
                                    continue

                        # Check Timeout (120 minutes)
                        try:
                            c_time = datetime.fromisoformat(trade.created_at)
                            elapsed_mins = (now_dt - c_time).total_seconds() / 60.0
                            if elapsed_mins >= 120.0:
                                trade.status = "RESOLVED"
                                trade.outcome = "EXPIRED_TIMEOUT"
                                trade.resolved_time = now_iso
                                trade.exit_price = mid
                                trade.net_r = 0.0
                                newly_resolved.append(trade)
                                self._record_resolved(trade)
                                continue
                        except Exception:
                            pass

                        remaining.append(trade)
                        continue

                    # -------------------------------------------------------------
                    # 2. ACTIVE POSITION EVALUATION
                    # -------------------------------------------------------------
                    if trade.status == "ACTIVE":
                        risk_amount = abs(trade.entry_price - trade.sl_price)
                        if risk_amount <= 0:
                            risk_amount = (trade.sl_points * point) if trade.sl_points > 0 else (100 * point)
                        if trade.current_sl is None:
                            trade.current_sl = trade.sl_price

                        # Excursion tracking & floating P/L
                        if trade.direction == "BUY":
                            curr_r = (mid - trade.entry_price) / risk_amount
                            pts = int(round((mid - trade.entry_price) / point))
                            trade.floating_points = pts
                            trade.floating_r = round(curr_r, 2)
                            trade.peak_mfe_r = max(trade.peak_mfe_r, round(curr_r, 2))
                            trade.max_mae_r = min(trade.max_mae_r, round(curr_r, 2))

                            # Dynamic Grade-Aware BEP Threshold (11 Sep 2026)
                            tp_dist = abs(trade.tp_price - trade.entry_price)
                            tp_progress = ((mid - trade.entry_price) / tp_dist) if tp_dist > 0 else 0.0
                            sg = str(trade.metadata.get("setup_grade") or trade.action_tier or "GRADE_A").upper()
                            if "GRADE_S" in sg:
                                bep_tp_ratio = 0.65
                            elif "M4" in str(trade.setup_type):
                                bep_tp_ratio = getattr(config, "M4_BREAK_EVEN_TRIGGER_TP_PCT", 0.70)
                            elif "GRADE_B" in sg or "REDUCED" in sg:
                                bep_tp_ratio = getattr(config, "GRADE_B_BREAK_EVEN_TRIGGER_TP_PCT", 0.35)
                            else:
                                bep_tp_ratio = getattr(config, "BREAK_EVEN_TRIGGER_TP_PCT", 0.60)

                            # 1. Virtual Break-Even (BEP) Trigger
                            if tp_progress >= bep_tp_ratio and not trade.bep_activated:
                                b_sl = round(trade.entry_price + (15 * point), digits)
                                if trade.current_sl < b_sl:
                                    trade.current_sl = b_sl
                                trade.bep_activated = True
                                logger.info(f"[SHADOW BEP] {trade.shadow_id} | {trade.symbol} BUY moved SL to BEP @ {trade.current_sl} (+15 pts, trigger: {bep_tp_ratio*100:.0f}% TP)")

                            # 2. Virtual Dynamic Trailing Stop Trigger: 3-Tier Progressive Ladder
                            tier1_trig = getattr(config, "TRAILING_TIER_1_TRIGGER_PCT", 0.75)
                            tier1_lock = getattr(config, "TRAILING_TIER_1_LOCK_PCT", 0.50)
                            tier2_trig = getattr(config, "TRAILING_TIER_2_TRIGGER_PCT", 0.90)
                            tier2_lock = getattr(config, "TRAILING_TIER_2_LOCK_PCT", 0.80)
                            tier3_trig = getattr(config, "TRAILING_TIER_3_TRIGGER_PCT", 0.95)
                            tier3_lock = getattr(config, "TRAILING_TIER_3_LOCK_PCT", 0.90)

                            ladder_floor = None
                            if tp_dist > 0:
                                if tp_progress >= tier3_trig:
                                    ladder_floor = round(trade.entry_price + (tier3_lock * tp_dist), digits)
                                elif tp_progress >= tier2_trig:
                                    ladder_floor = round(trade.entry_price + (tier2_lock * tp_dist), digits)
                                elif tp_progress >= tier1_trig:
                                    ladder_floor = round(trade.entry_price + (tier1_lock * tp_dist), digits)
                            elif curr_r >= 0.80:
                                ladder_floor = round(trade.entry_price + ((curr_r - 0.40) * risk_amount), digits)

                            if ladder_floor is not None and trade.current_sl < ladder_floor:
                                trade.current_sl = ladder_floor
                                trade.trailing_activated = True
                                logger.debug(f"[SHADOW TRAILING] {trade.shadow_id} | {trade.symbol} BUY trailed SL to @ {trade.current_sl}")

                            is_live_mt5 = bool(trade.mt5_ticket and trade.mt5_ticket in open_mt5_tickets)

                            # Check TP Hit
                            if bid >= trade.tp_price:
                                if not is_live_mt5:
                                    trade.status = "RESOLVED"
                                    trade.outcome = "TP_HIT"
                                    trade.resolved_time = now_iso
                                    trade.exit_price = trade.tp_price
                                    trade.net_r = round(trade.risk_reward, 2)
                                    newly_resolved.append(trade)
                                    self._record_resolved(trade)
                                    continue

                            # Check SL Hit (Evaluated against trade.current_sl)
                            active_sl = trade.current_sl if trade.current_sl is not None else trade.sl_price
                            if ask <= active_sl:
                                if not is_live_mt5:
                                    trade.status = "RESOLVED"
                                    trade.resolved_time = now_iso
                                    trade.exit_price = active_sl
                                    realized_r = round((active_sl - trade.entry_price) / risk_amount, 2)
                                    if trade.trailing_activated and realized_r >= 0.20:
                                        trade.net_r = max(0.0, realized_r)
                                        trade.outcome = "TRAILING_SL_HIT"
                                    elif trade.bep_activated or realized_r >= -0.05:
                                        trade.net_r = max(0.0, realized_r)
                                        trade.outcome = "BEP_HIT"
                                    else:
                                        trade.outcome = "SL_HIT"
                                        trade.net_r = -1.0
                                    newly_resolved.append(trade)
                                    self._record_resolved(trade)
                                    continue

                        elif trade.direction == "SELL":
                            curr_r = (trade.entry_price - mid) / risk_amount
                            pts = int(round((trade.entry_price - mid) / point))
                            trade.floating_points = pts
                            trade.floating_r = round(curr_r, 2)
                            trade.peak_mfe_r = max(trade.peak_mfe_r, round(curr_r, 2))
                            trade.max_mae_r = min(trade.max_mae_r, round(curr_r, 2))

                            # Dynamic Grade-Aware BEP Threshold (11 Sep 2026)
                            tp_dist = abs(trade.tp_price - trade.entry_price)
                            tp_progress = ((trade.entry_price - mid) / tp_dist) if tp_dist > 0 else 0.0
                            sg = str(trade.metadata.get("setup_grade") or trade.action_tier or "GRADE_A").upper()
                            if "GRADE_S" in sg:
                                bep_tp_ratio = 0.65
                            elif "M4" in str(trade.setup_type):
                                bep_tp_ratio = getattr(config, "M4_BREAK_EVEN_TRIGGER_TP_PCT", 0.70)
                            elif "GRADE_B" in sg or "REDUCED" in sg:
                                bep_tp_ratio = getattr(config, "GRADE_B_BREAK_EVEN_TRIGGER_TP_PCT", 0.35)
                            else:
                                bep_tp_ratio = getattr(config, "BREAK_EVEN_TRIGGER_TP_PCT", 0.60)

                            # 1. Virtual Break-Even (BEP) Trigger
                            if tp_progress >= bep_tp_ratio and not trade.bep_activated:
                                b_sl = round(trade.entry_price - (15 * point), digits)
                                if trade.current_sl > b_sl:
                                    trade.current_sl = b_sl
                                trade.bep_activated = True
                                logger.info(f"[SHADOW BEP] {trade.shadow_id} | {trade.symbol} SELL moved SL to BEP @ {trade.current_sl} (+15 pts, trigger: {bep_tp_ratio*100:.0f}% TP)")

                            # 2. Virtual Dynamic Trailing Stop Trigger: 3-Tier Progressive Ladder
                            tier1_trig = getattr(config, "TRAILING_TIER_1_TRIGGER_PCT", 0.75)
                            tier1_lock = getattr(config, "TRAILING_TIER_1_LOCK_PCT", 0.50)
                            tier2_trig = getattr(config, "TRAILING_TIER_2_TRIGGER_PCT", 0.90)
                            tier2_lock = getattr(config, "TRAILING_TIER_2_LOCK_PCT", 0.80)
                            tier3_trig = getattr(config, "TRAILING_TIER_3_TRIGGER_PCT", 0.95)
                            tier3_lock = getattr(config, "TRAILING_TIER_3_LOCK_PCT", 0.90)

                            ladder_ceil = None
                            if tp_dist > 0:
                                if tp_progress >= tier3_trig:
                                    ladder_ceil = round(trade.entry_price - (tier3_lock * tp_dist), digits)
                                elif tp_progress >= tier2_trig:
                                    ladder_ceil = round(trade.entry_price - (tier2_lock * tp_dist), digits)
                                elif tp_progress >= tier1_trig:
                                    ladder_ceil = round(trade.entry_price - (tier1_lock * tp_dist), digits)
                            elif curr_r >= 0.80:
                                ladder_ceil = round(trade.entry_price - ((curr_r - 0.40) * risk_amount), digits)

                            if ladder_ceil is not None and trade.current_sl > ladder_ceil:
                                trade.current_sl = ladder_ceil
                                trade.trailing_activated = True
                                logger.debug(f"[SHADOW TRAILING] {trade.shadow_id} | {trade.symbol} SELL trailed SL to @ {trade.current_sl}")

                            is_live_mt5 = bool(trade.mt5_ticket and trade.mt5_ticket in open_mt5_tickets)

                            # Check TP Hit
                            if ask <= trade.tp_price:
                                if not is_live_mt5:
                                    trade.status = "RESOLVED"
                                    trade.outcome = "TP_HIT"
                                    trade.resolved_time = now_iso
                                    trade.exit_price = trade.tp_price
                                    trade.net_r = round(trade.risk_reward, 2)
                                    newly_resolved.append(trade)
                                    self._record_resolved(trade)
                                    continue

                            # Check SL Hit (Evaluated against trade.current_sl)
                            active_sl = trade.current_sl if trade.current_sl is not None else trade.sl_price
                            if bid >= active_sl:
                                if not is_live_mt5:
                                    trade.status = "RESOLVED"
                                    trade.resolved_time = now_iso
                                    trade.exit_price = active_sl
                                    realized_r = round((trade.entry_price - active_sl) / risk_amount, 2)
                                    if trade.trailing_activated and realized_r >= 0.20:
                                        trade.net_r = max(0.0, realized_r)
                                        trade.outcome = "TRAILING_SL_HIT"
                                    elif trade.bep_activated or realized_r >= -0.05:
                                        trade.net_r = max(0.0, realized_r)
                                        trade.outcome = "BEP_HIT"
                                    else:
                                        trade.outcome = "SL_HIT"
                                        trade.net_r = -1.0
                                    newly_resolved.append(trade)
                                    self._record_resolved(trade)
                                    continue

                        # Check Peak-Aware Time-Decay Stagnation Exit (Only for unlinked shadow paper trades)
                        try:
                            if not is_live_mt5:
                                f_time_str = trade.fill_time or trade.created_at
                                f_time = datetime.fromisoformat(f_time_str)
                                hold_hours = (now_dt - f_time).total_seconds() / 3600.0
                                if hold_hours >= 4.0 and trade.peak_mfe_r < 0.30 and (-0.20 <= curr_r <= 0.20):
                                    trade.status = "RESOLVED"
                                    trade.outcome = "TIME_DECAY_EXIT"
                                    trade.resolved_time = now_iso
                                    trade.exit_price = mid
                                    trade.net_r = round(curr_r, 2)
                                    newly_resolved.append(trade)
                                    self._record_resolved(trade)
                                    continue
                                elif hold_hours >= 24.0:
                                    trade.status = "RESOLVED"
                                    trade.outcome = "TIME_DECAY_EXIT"
                                    trade.resolved_time = now_iso
                                    trade.exit_price = mid
                                    trade.net_r = round(curr_r, 2)
                                    newly_resolved.append(trade)
                                    self._record_resolved(trade)
                                    continue
                        except Exception:
                            pass

                        remaining.append(trade)

                except Exception as e:
                    logger.error(f"[SHADOW UPDATE ERROR] {trade.shadow_id}: {e}")
                    remaining.append(trade)

            # Post-pass: Auto-reconstitute active trade for any unrepresented open MT5 position
            for p in (raw_mt5_pos or []):
                if p.ticket not in claimed_open_tickets:
                    recovered = next((r for r in self._recent_resolved if getattr(r, "mt5_ticket", None) == p.ticket), None)
                    if not recovered:
                        try:
                            if os.path.exists(SHADOW_TRADES_LOG):
                                with open(SHADOW_TRADES_LOG, "r", encoding="utf-8") as f:
                                    for line in f:
                                        t_dict = json.loads(line)
                                        if t_dict.get("mt5_ticket") == p.ticket:
                                            recovered = ShadowTrade(
                                                shadow_id=t_dict["shadow_id"],
                                                symbol=t_dict["symbol"],
                                                setup_type=t_dict["setup_type"],
                                                direction=t_dict["direction"],
                                                entry_type=t_dict.get("entry_type", "market"),
                                                entry_price=t_dict["entry_price"],
                                                sl_price=t_dict["sl_price"],
                                                tp_price=t_dict["tp_price"],
                                                sl_points=t_dict["sl_points"],
                                                tp_points=t_dict["tp_points"],
                                                risk_reward=t_dict["risk_reward"],
                                                created_at=t_dict["created_at"],
                                                action_tier=t_dict.get("action_tier", "FULL_ALLOW"),
                                                mt5_ticket=p.ticket,
                                                mt5_disposition="EXECUTED_MT5",
                                            )
                                            break
                        except Exception as e:
                            logger.debug(f"[SHADOW RECOVER READ ERROR] {e}")

                    if recovered:
                        recovered.status = "ACTIVE"
                        recovered.outcome = None
                        recovered.resolved_time = None
                        recovered.exit_price = None
                        recovered.net_r = None
                        recovered.current_sl = getattr(p, "sl", recovered.sl_price)
                        recovered.tp_price = getattr(p, "tp", recovered.tp_price)
                        recovered.bep_activated = (p.ticket in be_tickets)
                        recovered.trailing_activated = (p.ticket in trail_tickets)
                        remaining.append(recovered)
                        claimed_open_tickets.add(p.ticket)
                        logger.info(f"[SHADOW RECOVER] Re-activated open MT5 position #{p.ticket} ({p.symbol}) into active shadow trades")

            self.active_trades = remaining
            if newly_resolved or len(remaining) > 0:
                self._save_state()

            return newly_resolved

    def _record_resolved(self, trade: ShadowTrade):
        """Updates stats and appends to persistent trade log (idempotent)."""
        if not hasattr(self, "_resolved_ids"):
            self._resolved_ids = set()
        if trade.shadow_id in self._resolved_ids:
            logger.debug(f"[SHADOW TRACKER] Trade {trade.shadow_id} already resolved, skipping duplicate record.")
            return
        self._resolved_ids.add(trade.shadow_id)

        try:
            from src.analytics.currency_strength import get_csm_delta_for_symbol
            csm_close = get_csm_delta_for_symbol(trade.symbol)
            trade.metadata["csm_delta_close"] = float(csm_close)
            csm_open = trade.metadata.get("csm_delta_open")
            if csm_open is not None:
                trade.metadata["csm_delta_shift"] = round(float(csm_close) - float(csm_open), 2)
        except Exception:
            pass

        self._stats["total_resolved"] += 1
        if trade.outcome == "TP_HIT":
            self._stats["tp_hits"] += 1
            self._stats["cumulative_net_r"] = round(self._stats["cumulative_net_r"] + (trade.net_r or 0.0), 2)
        elif trade.outcome == "SL_HIT":
            self._stats["sl_hits"] += 1
            self._stats["cumulative_net_r"] = round(self._stats["cumulative_net_r"] - 1.0, 2)
        elif trade.outcome in ("BEP_HIT", "TRAILING_SL_HIT", "TIME_DECAY_EXIT", "RESOLVED_CLOSED"):
            r_val = trade.net_r or 0.0
            if r_val > 0.05:
                self._stats["tp_hits"] += 1
            elif r_val < -0.05:
                self._stats["sl_hits"] += 1
            self._stats["cumulative_net_r"] = round(self._stats["cumulative_net_r"] + r_val, 2)
        elif trade.outcome in ("EXPIRED_NO_FILL", "EXPIRED_TIMEOUT"):
            self._stats["expired_count"] += 1

        self._recent_resolved.append(trade.to_dict())
        self._recent_resolved = self._recent_resolved[-30:]
        self._append_resolved_log(trade)

        csm_open_val = trade.metadata.get("csm_delta_open")
        csm_close_val = trade.metadata.get("csm_delta_close")
        csm_log_str = f" | CSM Open: {csm_open_val:+.2f} -> Close: {csm_close_val:+.2f}" if (csm_open_val is not None and csm_close_val is not None) else ""
        logger.info(
            f"[SHADOW RESOLVED] {trade.shadow_id} | {trade.symbol} {trade.direction} -> {trade.outcome} "
            f"(Net R: {trade.net_r:+.2f}R | MFE: {trade.peak_mfe_r:+.2f}R | MAE: {trade.max_mae_r:+.2f}R{csm_log_str})"
        )

    def get_performance_summary(self) -> Dict[str, Any]:
        """Returns structured performance analytics for Cockpit Dashboard and CLI."""
        with self._lock:
            # Read full history from JSONL with deduplication (keyed by shadow_id)
            all_resolved = {}
            try:
                if os.path.exists(SHADOW_TRADES_LOG):
                    with open(SHADOW_TRADES_LOG, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    t_obj = json.loads(line)
                                    sid = t_obj.get("shadow_id")
                                    if sid:
                                        all_resolved[sid] = t_obj
                                except Exception:
                                    pass
            except Exception as e:
                logger.error(f"[SHADOW READ STATS ERROR] {e}")

            # Fallback if log empty
            if not all_resolved and self._recent_resolved:
                for t_obj in self._recent_resolved:
                    sid = t_obj.get("shadow_id")
                    if sid:
                        all_resolved[sid] = t_obj

            mech_stats = {
                "M1": {"total": 0, "tp": 0, "sl": 0, "bep": 0, "net_r": 0.0},
                "M2": {"total": 0, "tp": 0, "sl": 0, "bep": 0, "net_r": 0.0},
                "M3": {"total": 0, "tp": 0, "sl": 0, "bep": 0, "net_r": 0.0},
                "M4": {"total": 0, "tp": 0, "sl": 0, "bep": 0, "net_r": 0.0}
            }

            tp_hits = 0
            sl_hits = 0
            bep_hits = 0
            time_decay_hits = 0
            cum_net_r = 0.0
            expired_count = 0
            gross_profit_r = 0.0
            gross_loss_r = 0.0

            for sid, t in all_resolved.items():
                st = t.get("setup_type", "")
                m_key = "M4" if any(k in st for k in ("DBD", "RBR", "FLOW", "M4")) else ("M1" if "SWEEP" in st else ("M2" if "PULLBACK" in st else ("M3" if "BREAKOUT" in st else "M1")))
                out = str(t.get("outcome", ""))
                nr = float(t.get("net_r") or 0.0)

                if m_key in mech_stats:
                    mech_stats[m_key]["total"] += 1
                    mech_stats[m_key]["net_r"] = round(mech_stats[m_key]["net_r"] + nr, 2)

                cum_net_r = round(cum_net_r + nr, 2)
                if nr > 0:
                    gross_profit_r += nr
                elif nr < 0:
                    gross_loss_r += abs(nr)

                # Classify TP vs SL vs BEP vs Time-Decay vs Expired
                if out == "TP_HIT" or (out == "TRAILING_SL_HIT" and nr >= 0.20):
                    tp_hits += 1
                    if m_key in mech_stats:
                        mech_stats[m_key]["tp"] += 1
                elif out == "SL_HIT" or (out == "TRAILING_SL_HIT" and nr < -0.05):
                    sl_hits += 1
                    if m_key in mech_stats:
                        mech_stats[m_key]["sl"] += 1
                elif "BEP" in out:
                    bep_hits += 1
                    if m_key in mech_stats:
                        mech_stats[m_key]["bep"] += 1
                elif "TIME_DECAY" in out:
                    time_decay_hits += 1
                elif "EXPIRED" in out:
                    expired_count += 1

            total_resolved = len(all_resolved)
            filled_trades = total_resolved - expired_count
            decisive_trades = tp_hits + sl_hits
            winrate = (tp_hits / decisive_trades * 100.0) if decisive_trades > 0 else 0.0
            preservation_rate = ((tp_hits + bep_hits) / filled_trades * 100.0) if filled_trades > 0 else 0.0
            profit_factor = (gross_profit_r / gross_loss_r) if gross_loss_r > 0 else (99.0 if gross_profit_r > 0 else 0.0)
            ev = (cum_net_r / total_resolved) if total_resolved > 0 else 0.0

            # Outcome Breakdown with individual percentages
            def _pct(cnt: int, base: int) -> float:
                return round((cnt / base * 100.0), 1) if base > 0 else 0.0

            outcome_breakdown = {
                "tp": {
                    "count": tp_hits,
                    "pct_total": _pct(tp_hits, total_resolved),
                    "pct_filled": _pct(tp_hits, filled_trades)
                },
                "bep": {
                    "count": bep_hits,
                    "pct_total": _pct(bep_hits, total_resolved),
                    "pct_filled": _pct(bep_hits, filled_trades)
                },
                "sl": {
                    "count": sl_hits,
                    "pct_total": _pct(sl_hits, total_resolved),
                    "pct_filled": _pct(sl_hits, filled_trades)
                },
                "time_decay": {
                    "count": time_decay_hits,
                    "pct_total": _pct(time_decay_hits, total_resolved),
                    "pct_filled": _pct(time_decay_hits, filled_trades)
                },
                "expired": {
                    "count": expired_count,
                    "pct_total": _pct(expired_count, total_resolved),
                    "pct_filled": 0.0
                },
                "filled_trades": filled_trades,
                "preservation_rate": round(preservation_rate, 1),
                "profit_factor": round(profit_factor, 2),
                "gross_profit_r": round(gross_profit_r, 2),
                "gross_loss_r": round(gross_loss_r, 2)
            }

            # Update cached _stats
            self._stats["total_resolved"] = total_resolved
            self._stats["tp_hits"] = tp_hits
            self._stats["sl_hits"] = sl_hits
            self._stats["expired_count"] = expired_count
            self._stats["cumulative_net_r"] = cum_net_r

            # MT5 Execution vs Skipped breakdown
            disp_stats = {
                "EXECUTED_MT5": 0,
                "SKIPPED_MAX_POSITIONS": 0,
                "SKIPPED_CBSS_BASKET_CAP": 0,
                "SKIPPED_NY_M3_PAPER": 0,
                "SKIPPED_RISK_BASKET": 0,
                "SKIPPED_RISK_BLOCK": 0,
                "SKIPPED_LLM_VETO": 0,
                "OTHER": 0
            }
            sample_trades = [t.to_dict() for t in self.active_trades] + list(all_resolved.values())
            for t_dict in sample_trades:
                disp = str(t_dict.get("mt5_disposition", "OTHER") or "OTHER").upper()
                if "EXECUTED" in disp:
                    disp_stats["EXECUTED_MT5"] += 1
                elif "CBSS" in disp:
                    disp_stats["SKIPPED_CBSS_BASKET_CAP"] += 1
                elif "NY_M3" in disp:
                    disp_stats["SKIPPED_NY_M3_PAPER"] += 1
                elif "MAX_POSITIONS" in disp or "SLOT" in disp:
                    disp_stats["SKIPPED_MAX_POSITIONS"] += 1
                elif "BASKET" in disp or "KONSENTRASI" in disp:
                    disp_stats["SKIPPED_RISK_BASKET"] += 1
                elif "RISK" in disp:
                    disp_stats["SKIPPED_RISK_BLOCK"] += 1
                elif "VETO" in disp:
                    disp_stats["SKIPPED_LLM_VETO"] += 1
                else:
                    disp_stats["OTHER"] += 1

            return {
                "total_recorded": len(sample_trades),
                "active_count": len([t for t in self.active_trades if t.status == "ACTIVE"]),
                "pending_count": len([t for t in self.active_trades if t.status == "PENDING"]),
                "total_resolved": total_resolved,
                "tp_hits": tp_hits,
                "sl_hits": sl_hits,
                "bep_hits": bep_hits,
                "time_decay_hits": time_decay_hits,
                "expired_count": expired_count,
                "decisive_trades": decisive_trades,
                "filled_trades": filled_trades,
                "winrate_pct": round(winrate, 1),
                "preservation_rate": round(preservation_rate, 1),
                "profit_factor": round(profit_factor, 2),
                "gross_profit_r": round(gross_profit_r, 2),
                "gross_loss_r": round(gross_loss_r, 2),
                "cumulative_net_r": round(cum_net_r, 2),
                "expected_value_r": round(ev, 2),
                "outcome_breakdown": outcome_breakdown,
                "mechanisms": mech_stats,
                "disposition_breakdown": disp_stats,
                "recent_resolved": list(all_resolved.values())[-20:],
                "active_trades": [t.to_dict() for t in self.active_trades[:25]]
            }

    def get_all_resolved_trades(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Reads historical resolved shadow trades from JSONL log with deduplication by shadow_id, newest first."""
        trades_dict = {}
        try:
            if os.path.exists(SHADOW_TRADES_LOG):
                with open(SHADOW_TRADES_LOG, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                obj = json.loads(line)
                                sid = obj.get("shadow_id")
                                if sid:
                                    trades_dict[sid] = obj
                            except Exception:
                                pass
        except Exception as e:
            logger.error(f"[SHADOW READ LOG ERROR] {e}")

        if trades_dict:
            trades = list(trades_dict.values())
            trades.sort(key=lambda t: t.get("resolved_time") or t.get("created_at") or "", reverse=True)
            return trades[:limit]
        return list(reversed(self._recent_resolved[-limit:]))


# Global Singleton Instance
shadow_tracker = QuantShadowTracker()
