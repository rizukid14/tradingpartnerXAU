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
        self._load_state()
        self._initialized = True
        logger.info(f"[SHADOW TRACKER] Initialized with {len(self.active_trades)} active/pending shadow trades.")

    def _load_state(self):
        """Loads existing state from quant_shadow_state.json if available."""
        with self._lock:
            try:
                if os.path.exists(SHADOW_STATE_FILE):
                    with open(SHADOW_STATE_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.active_trades = [ShadowTrade.from_dict(t) for t in data.get("active_trades", [])]
                    self._stats = data.get("stats", self._stats)
                    self._recent_resolved = data.get("recent_resolved", [])
            except Exception as e:
                logger.error(f"[SHADOW TRACKER LOAD ERROR] {e}")
                self.active_trades = []

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
                if os.path.exists(SHADOW_STATE_FILE):
                    os.replace(tmp_path, SHADOW_STATE_FILE)
                else:
                    os.rename(tmp_path, SHADOW_STATE_FILE)
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

            # Deduplication check: Do not duplicate if identical active/pending trade exists
            for existing in self.active_trades:
                if existing.symbol == sym and existing.direction == dir_str and existing.setup_type == setup_type:
                    # Check if created within last 30 minutes
                    try:
                        ex_time = datetime.fromisoformat(existing.created_at)
                        if (now_dt - ex_time).total_seconds() < 1800:
                            return None
                    except Exception:
                        pass

            rr = round(tp_points / sl_points, 2) if sl_points > 0 else 1.5

            shadow_id = f"SHADOW_{now_dt.strftime('%Y%m%d_%H%M%S')}_{sym.replace('-ECNc','').replace('.c','').replace('-ECN','')}_{setup_type[:6]}"

            initial_status = "ACTIVE" if entry_type == "market" else "PENDING"
            fill_time = now_iso if initial_status == "ACTIVE" else None

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
                metadata={
                    "current_atr_pts": getattr(candidate, "current_atr_pts", 0.0),
                    "current_spread_pts": getattr(candidate, "current_spread_pts", 0),
                    "dealing_range_pos": getattr(candidate, "dealing_range_pos", 0.5)
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

    def update_shadow_orders(self, connector: Any) -> List[ShadowTrade]:
        """
        Evaluates and advances the state of all pending and active shadow orders using live ticks.
        Detects:
        1. Pending Fill (limit order triggered by market price).
        2. Target Proximity Invalidation (>=75% move toward TP without fill).
        3. Timeout Expiration (pending > 120 minutes).
        4. Excursion Tracking (MFE & MAE accumulation).
        5. TP Hit (+R) and SL Hit (-1.0R).
        6. Time Decay Stagnation Exit (> 24 hours).
        """
        with self._lock:
            if not self.active_trades:
                return []

            now_dt = datetime.now(WIB)
            now_iso = now_dt.isoformat()
            newly_resolved: List[ShadowTrade] = []
            remaining: List[ShadowTrade] = []

            for trade in self.active_trades:
                try:
                    tick = connector.get_current_tick(trade.symbol)
                    if not tick:
                        remaining.append(trade)
                        continue

                    ask = float(tick.get("ask", 0.0))
                    bid = float(tick.get("bid", 0.0))
                    if ask <= 0 or bid <= 0:
                        remaining.append(trade)
                        continue
                    mid = (ask + bid) / 2.0

                    # -------------------------------------------------------------
                    # 1. PENDING ORDER EVALUATION
                    # -------------------------------------------------------------
                    if trade.status == "PENDING":
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
                            trade.peak_mfe_r = 0.0
                            trade.max_mae_r = 0.0
                            logger.info(f"[SHADOW FILLED] {trade.shadow_id} | {trade.symbol} {trade.direction} filled @ {trade.entry_price}")
                            remaining.append(trade)
                            continue

                        # Check Target Proximity Expiration (>=75% to TP without fill)
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
                            remaining.append(trade)
                            continue

                        # Excursion tracking
                        if trade.direction == "BUY":
                            curr_r = (mid - trade.entry_price) / risk_amount
                            trade.peak_mfe_r = max(trade.peak_mfe_r, round(curr_r, 2))
                            trade.max_mae_r = min(trade.max_mae_r, round(curr_r, 2))

                            # Check TP Hit
                            if bid >= trade.tp_price:
                                trade.status = "RESOLVED"
                                trade.outcome = "TP_HIT"
                                trade.resolved_time = now_iso
                                trade.exit_price = trade.tp_price
                                trade.net_r = round(trade.risk_reward, 2)
                                newly_resolved.append(trade)
                                self._record_resolved(trade)
                                continue

                            # Check SL Hit
                            elif ask <= trade.sl_price:
                                trade.status = "RESOLVED"
                                trade.outcome = "SL_HIT"
                                trade.resolved_time = now_iso
                                trade.exit_price = trade.sl_price
                                trade.net_r = -1.0
                                newly_resolved.append(trade)
                                self._record_resolved(trade)
                                continue

                        elif trade.direction == "SELL":
                            curr_r = (trade.entry_price - mid) / risk_amount
                            trade.peak_mfe_r = max(trade.peak_mfe_r, round(curr_r, 2))
                            trade.max_mae_r = min(trade.max_mae_r, round(curr_r, 2))

                            # Check TP Hit
                            if ask <= trade.tp_price:
                                trade.status = "RESOLVED"
                                trade.outcome = "TP_HIT"
                                trade.resolved_time = now_iso
                                trade.exit_price = trade.tp_price
                                trade.net_r = round(trade.risk_reward, 2)
                                newly_resolved.append(trade)
                                self._record_resolved(trade)
                                continue

                            # Check SL Hit
                            elif bid >= trade.sl_price:
                                trade.status = "RESOLVED"
                                trade.outcome = "SL_HIT"
                                trade.resolved_time = now_iso
                                trade.exit_price = trade.sl_price
                                trade.net_r = -1.0
                                newly_resolved.append(trade)
                                self._record_resolved(trade)
                                continue

                        # Check Time-Decay Stagnation Exit (24 hours hold)
                        try:
                            f_time_str = trade.fill_time or trade.created_at
                            f_time = datetime.fromisoformat(f_time_str)
                            hold_hours = (now_dt - f_time).total_seconds() / 3600.0
                            if hold_hours >= 24.0:
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

            self.active_trades = remaining
            if newly_resolved:
                self._save_state()

            return newly_resolved

    def _record_resolved(self, trade: ShadowTrade):
        """Updates stats and appends to persistent trade log."""
        self._stats["total_resolved"] += 1
        if trade.outcome == "TP_HIT":
            self._stats["tp_hits"] += 1
            self._stats["cumulative_net_r"] = round(self._stats["cumulative_net_r"] + (trade.net_r or 0.0), 2)
        elif trade.outcome == "SL_HIT":
            self._stats["sl_hits"] += 1
            self._stats["cumulative_net_r"] = round(self._stats["cumulative_net_r"] - 1.0, 2)
        elif trade.outcome == "TIME_DECAY_EXIT":
            self._stats["cumulative_net_r"] = round(self._stats["cumulative_net_r"] + (trade.net_r or 0.0), 2)
        elif trade.outcome in ("EXPIRED_NO_FILL", "EXPIRED_TIMEOUT"):
            self._stats["expired_count"] += 1

        self._recent_resolved.append(trade.to_dict())
        self._recent_resolved = self._recent_resolved[-30:]
        self._append_resolved_log(trade)

        logger.info(
            f"[SHADOW RESOLVED] {trade.shadow_id} | {trade.symbol} {trade.direction} -> {trade.outcome} "
            f"(Net R: {trade.net_r:+.2f}R | MFE: {trade.peak_mfe_r:+.2f}R | MAE: {trade.max_mae_r:+.2f}R)"
        )

    def get_performance_summary(self) -> Dict[str, Any]:
        """Returns structured performance analytics for Cockpit Dashboard and CLI."""
        with self._lock:
            total_resolved = self._stats.get("total_resolved", 0)
            tp_hits = self._stats.get("tp_hits", 0)
            sl_hits = self._stats.get("sl_hits", 0)
            decisive_trades = tp_hits + sl_hits
            winrate = (tp_hits / decisive_trades * 100.0) if decisive_trades > 0 else 0.0
            cum_net_r = self._stats.get("cumulative_net_r", 0.0)
            ev = (cum_net_r / decisive_trades) if decisive_trades > 0 else 0.0

            # Mechanism breakdown from recent resolved
            mech_stats = {
                "M1": {"total": 0, "tp": 0, "sl": 0, "net_r": 0.0},
                "M2": {"total": 0, "tp": 0, "sl": 0, "net_r": 0.0},
                "M3": {"total": 0, "tp": 0, "sl": 0, "net_r": 0.0},
                "M4": {"total": 0, "tp": 0, "sl": 0, "net_r": 0.0}
            }

            for t in self._recent_resolved:
                st = t.get("setup_type", "")
                m_key = "M1" if "SWEEP" in st else ("M2" if "PULLBACK" in st else ("M3" if "BREAKOUT" in st else ("M4" if "FLOW" in st else "M1")))
                if m_key in mech_stats:
                    mech_stats[m_key]["total"] += 1
                    if t.get("outcome") == "TP_HIT":
                        mech_stats[m_key]["tp"] += 1
                    elif t.get("outcome") == "SL_HIT":
                        mech_stats[m_key]["sl"] += 1
                    mech_stats[m_key]["net_r"] = round(mech_stats[m_key]["net_r"] + (t.get("net_r") or 0.0), 2)

            return {
                "total_recorded": self._stats.get("total_recorded", 0),
                "active_count": len([t for t in self.active_trades if t.status == "ACTIVE"]),
                "pending_count": len([t for t in self.active_trades if t.status == "PENDING"]),
                "total_resolved": total_resolved,
                "tp_hits": tp_hits,
                "sl_hits": sl_hits,
                "expired_count": self._stats.get("expired_count", 0),
                "decisive_trades": decisive_trades,
                "winrate_pct": round(winrate, 1),
                "cumulative_net_r": round(cum_net_r, 2),
                "expected_value_r": round(ev, 2),
                "mechanisms": mech_stats,
                "recent_resolved": self._recent_resolved[-10:],
                "active_trades": [t.to_dict() for t in self.active_trades[:15]]
            }


# Global Singleton Instance
shadow_tracker = QuantShadowTracker()
