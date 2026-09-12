"""
Twin-Order Hybrid Scaling & Discrete Milestone Step-Lock Manager.

Architecture:
- Splits orders into Ticket A (TP1 Harvest) and Ticket B (Runner).
- The Cushion Lock: When Ticket A fills at TP1, Ticket B SL moves to Below TP1 and Above BEP:
  SL = max(BEP, TP1 - 0.35 * ATR) for BUY.
  SL = min(BEP, TP1 + 0.35 * ATR) for SELL.
- Milestone Step-Lock:
  - TP2 Hit: SL moves to TP1.
  - TP3 Approach (>=80%): SL moves to TP2.
- Grading-Aware Target Mapping:
  - GRADE_B: Single Order (TP1 only).
  - GRADE_A: Twin Order (Ticket A -> TP1, Ticket B -> TP2).
  - GRADE_A+ / GRADE_S: Twin Order (Ticket A -> TP1, Ticket B -> TP3).
"""

import os
import json
import math
import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
WIB = ZoneInfo("Asia/Jakarta")

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
TWIN_STATE_FILE = os.path.join(DATA_DIR, "active_twin_trades.json")


def calculate_twin_lot(
    total_lot: float,
    lot_min: float = 0.01,
    lot_step: float = 0.01,
    setup_grade: str = "GRADE_A"
) -> Tuple[float, float, bool]:
    """
    Calculates lot allocation for Twin Orders.
    Returns (lot_a, lot_b, is_twin).
    If total_lot <= lot_min or setup_grade == 'GRADE_B', returns single order (lot_a, 0.0, False).
    """
    total_lot = round(float(total_lot), 2)
    lot_min = round(float(lot_min), 2)
    lot_step = round(float(lot_step), 2)
    grade = str(setup_grade or "GRADE_A").upper()

    if total_lot <= lot_min or "GRADE_B" in grade:
        return total_lot, 0.0, False

    half_units = math.floor((total_lot * 0.5) / lot_step)
    lot_a = round(half_units * lot_step, 2)
    lot_a = max(lot_min, lot_a)
    lot_b = round(total_lot - lot_a, 2)

    if lot_b < lot_min:
        return total_lot, 0.0, False

    return lot_a, lot_b, True


def calculate_cushion_sl(
    direction: int,
    entry_price: float,
    tp1_price: float,
    atr_val: float,
    point: float = 0.00001,
    commission_pad_pts: int = 15,
    cushion_atr_mult: float = 0.35,
    digits: int = 5
) -> float:
    """
    Calculates The Cushion Lock SL (Below TP1 & Above BEP).
    For BUY: SL = max(entry + padding, tp1 - (cushion_atr_mult * atr))
    For SELL: SL = min(entry - padding, tp1 + (cushion_atr_mult * atr))
    """
    pad_dist = commission_pad_pts * point
    if direction == 1:
        be_price = entry_price + pad_dist
        cushion_raw = tp1_price - (cushion_atr_mult * atr_val)
        chosen_sl = max(be_price, cushion_raw)
    else:
        be_price = entry_price - pad_dist
        cushion_raw = tp1_price + (cushion_atr_mult * atr_val)
        chosen_sl = min(be_price, cushion_raw)

    return round(chosen_sl, digits)


class TwinTradeManager:
    """Manages runtime state, persistence, and milestone step-lock lifecycle for twin positions."""

    def __init__(self, state_file: str = TWIN_STATE_FILE):
        self.state_file = state_file
        self.trades: Dict[str, Dict[str, Any]] = self._load_state()

    def _load_state(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.state_file):
            return {}
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"[TWIN MANAGER] Failed to load {self.state_file}: {e}")
            return {}

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self.trades, f, indent=2)
        except Exception as e:
            logger.error(f"[TWIN MANAGER] Failed to save {self.state_file}: {e}")

    def register_pair(
        self,
        pair_id: str,
        symbol: str,
        direction: int,
        ticket_a: int,
        ticket_b: Optional[int],
        volume_a: float,
        volume_b: float,
        entry_price: float,
        sl_initial: float,
        tp1: float,
        tp2: float,
        tp3: float,
        setup_grade: str = "GRADE_A"
    ):
        """Registers a new twin trade pair in memory and persists to disk."""
        now_iso = datetime.now(WIB).isoformat()
        self.trades[pair_id] = {
            "pair_id": pair_id,
            "symbol": symbol,
            "direction": direction,
            "ticket_a": int(ticket_a),
            "ticket_b": int(ticket_b) if ticket_b else None,
            "volume_a": float(volume_a),
            "volume_b": float(volume_b),
            "entry_price": float(entry_price),
            "sl_initial": float(sl_initial),
            "tp1": float(tp1),
            "tp2": float(tp2) if tp2 else None,
            "tp3": float(tp3) if tp3 else None,
            "setup_grade": str(setup_grade).upper(),
            "state": "OPEN",
            "created_at": now_iso,
            "updated_at": now_iso
        }
        self._save_state()
        logger.info(f"[TWIN REGISTER] Pair {pair_id} registered: #{ticket_a} (TP1: {tp1}) + #{ticket_b} (TP2/3: {tp2}/{tp3})")

    def get_active_twins(self) -> List[Dict[str, Any]]:
        """Returns all open or active twin trade records."""
        return [t for t in self.trades.values() if t.get("state") not in ("CLOSED", "ARCHIVED")]

    def get_twin_by_ticket(self, ticket: int) -> Optional[Dict[str, Any]]:
        """Finds twin trade record containing the specified ticket."""
        t_int = int(ticket)
        for t in self.trades.values():
            if t.get("ticket_a") == t_int or t.get("ticket_b") == t_int:
                return t
        return None

    def audit_cycle(
        self,
        open_positions: Dict[int, Any],
        get_deals_fn,
        modify_sl_fn,
        symbol_info_provider,
        tick_provider,
        atr_provider
    ) -> List[Dict[str, Any]]:
        """
        Executes one audit cycle across all active twin trades.
        Detects TP1 fills, applies Cushion Lock, and advances milestones (TP2, TP3).
        """
        updates = []
        now_iso = datetime.now(WIB).isoformat()

        for pair_id, twin in list(self.trades.items()):
            state = twin.get("state", "OPEN")
            if state in ("CLOSED", "ARCHIVED"):
                continue

            ticket_a = twin.get("ticket_a")
            ticket_b = twin.get("ticket_b")
            symbol = twin.get("symbol")
            direction = twin.get("direction", 1)
            entry_p = twin.get("entry_price", 0.0)
            tp1 = twin.get("tp1", 0.0)
            tp2 = twin.get("tp2")
            tp3 = twin.get("tp3")

            pos_a = open_positions.get(ticket_a)
            pos_b = open_positions.get(ticket_b) if ticket_b else None

            # Case 1: If ticket_b is None, it's a single order trade
            if not ticket_b:
                if not pos_a:
                    twin["state"] = "CLOSED"
                    twin["updated_at"] = now_iso
                    updates.append({"pair_id": pair_id, "action": "CLOSED_SINGLE"})
                continue

            # Case 2: Both positions closed
            if not pos_a and not pos_b:
                twin["state"] = "CLOSED"
                twin["updated_at"] = now_iso
                updates.append({"pair_id": pair_id, "action": "CLOSED_BOTH"})
                continue

            # Case 3: Ticket A closed, Ticket B still open
            if not pos_a and pos_b:
                sym_info = symbol_info_provider(symbol)
                point = getattr(sym_info, "point", 0.00001) if sym_info else 0.00001
                digits = getattr(sym_info, "digits", 5) if sym_info else 5
                c_atr = atr_provider(symbol)

                # 3A: If state was OPEN, Ticket A was just closed -> Apply Cushion Lock
                if state == "OPEN":
                    deals = get_deals_fn(ticket_a)
                    has_profit = any(getattr(d, "profit", 0.0) > 0 for d in deals) if deals else True

                    if has_profit:
                        cushion_sl = calculate_cushion_sl(
                            direction=direction,
                            entry_price=entry_p,
                            tp1_price=tp1,
                            atr_val=c_atr,
                            point=point,
                            digits=digits
                        )
                        curr_sl = getattr(pos_b, "sl", 0.0) or 0.0
                        should_modify = (direction == 1 and curr_sl < cushion_sl) or (direction == -1 and (curr_sl == 0.0 or curr_sl > cushion_sl))

                        if should_modify:
                            ok = modify_sl_fn(ticket_b, cushion_sl)
                            if ok:
                                twin["state"] = "TP1_HARVESTED_CUSHION_LOCKED"
                                twin["updated_at"] = now_iso
                                updates.append({
                                    "pair_id": pair_id,
                                    "action": "CUSHION_LOCKED",
                                    "ticket": ticket_b,
                                    "sl": cushion_sl
                                })
                                logger.info(f"[TWIN CUSHION LOCK] Ticket #{ticket_b} ({symbol}): SL moved to {cushion_sl} (Below TP1 {tp1} & Above BEP)")

                # 3B: If in CUSHION_LOCKED state, check for TP2 Milestone
                if twin.get("state") == "TP1_HARVESTED_CUSHION_LOCKED" and tp2:
                    tick = tick_provider(symbol)
                    if tick:
                        tp2_hit = (direction == 1 and tick.bid >= tp2) or (direction == -1 and tick.ask <= tp2)
                        if tp2_hit:
                            # Advance SL to TP1
                            curr_sl = getattr(pos_b, "sl", 0.0) or 0.0
                            should_modify = (direction == 1 and curr_sl < tp1) or (direction == -1 and (curr_sl == 0.0 or curr_sl > tp1))
                            if should_modify:
                                ok = modify_sl_fn(ticket_b, round(tp1, digits))
                                if ok:
                                    twin["state"] = "TP2_REACHED_LOCK_TP1"
                                    twin["updated_at"] = now_iso
                                    updates.append({
                                        "pair_id": pair_id,
                                        "action": "LOCKED_AT_TP1",
                                        "ticket": ticket_b,
                                        "sl": tp1
                                    })
                                    logger.info(f"[TWIN MILESTONE TP2] Ticket #{ticket_b} ({symbol}): TP2 reached ({tp2}) -> SL locked at TP1 ({tp1})")

                # 3C: If in TP2_REACHED_LOCK_TP1 state, check for TP3 80% Approach
                if twin.get("state") == "TP2_REACHED_LOCK_TP1" and tp2 and tp3:
                    tick = tick_provider(symbol)
                    if tick:
                        if direction == 1:
                            dist_tot = tp3 - tp2
                            dist_curr = tick.bid - tp2
                            progress = (dist_curr / dist_tot) if dist_tot > 0 else 0.0
                        else:
                            dist_tot = tp2 - tp3
                            dist_curr = tp2 - tick.ask
                            progress = (dist_curr / dist_tot) if dist_tot > 0 else 0.0

                        if progress >= 0.80:
                            curr_sl = getattr(pos_b, "sl", 0.0) or 0.0
                            should_modify = (direction == 1 and curr_sl < tp2) or (direction == -1 and (curr_sl == 0.0 or curr_sl > tp2))
                            if should_modify:
                                ok = modify_sl_fn(ticket_b, round(tp2, digits))
                                if ok:
                                    twin["state"] = "TP3_APPROACH_LOCK_TP2"
                                    twin["updated_at"] = now_iso
                                    updates.append({
                                        "pair_id": pair_id,
                                        "action": "LOCKED_AT_TP2",
                                        "ticket": ticket_b,
                                        "sl": tp2
                                    })
                                    logger.info(f"[TWIN MILESTONE TP3 APPROACH] Ticket #{ticket_b} ({symbol}): Progress {progress*100:.1f}% -> SL locked at TP2 ({tp2})")

        if updates:
            self._save_state()

        return updates


# Global singleton instance
twin_manager = TwinTradeManager()
