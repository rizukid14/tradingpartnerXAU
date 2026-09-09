"""
shadow_audit_engine.py — Quant Shadow Executive Audit & Interactive Dashboard Engine.

Menganalisis performa 100% peluang Stage 1 Fast Radar (Paper Shadow) vs Eksekusi Riil MT5:
1. Ingestion: data/quant_shadow_trades.jsonl, data/quant_shadow_state.json, dan histori deal MT5.
2. Dual-Mode De-biasing: Raw Signals vs De-biased Unique Trade Legs.
3. Kuantitatif Rigor: Wilson Score 95% CI, Opportunity Cost Delta (Lost vs Saved),
   M1-M4 Edge Attribution, MFE/MAE Excursion Distributions, dan Efisiensi Proteksi BEP.
4. Single-File Self-Contained Interactive Dashboard: docs/shadow_executive_audit.html.
"""

from __future__ import annotations

import os
import sys
import json
import math
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Any, Optional, Tuple

import config

logger = logging.getLogger("shadow_audit")
WIB = ZoneInfo("Asia/Jakarta")

SHADOW_STATE_FILE = os.path.join(config.DATA_DIR, "quant_shadow_state.json")
SHADOW_TRADES_LOG = os.path.join(config.DATA_DIR, "quant_shadow_trades.jsonl")
DOCS_DIR = os.path.join(getattr(config, "BASE_DIR", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "docs")
DEFAULT_HTML_OUTPUT = os.path.join(DOCS_DIR, "shadow_executive_audit.html")


def compute_wilson_ci(wins: int, total: int, z: float = 1.96) -> Tuple[float, float, float]:
    """
    Menghitung Wilson Score 95% Confidence Interval untuk winrate.
    Mengembalikan: (p_pct, lower_pct, upper_pct)
    """
    if total <= 0:
        return 0.0, 0.0, 0.0
    p = wins / total
    denom = 1.0 + (z ** 2) / total
    center = (p + (z ** 2) / (2.0 * total)) / denom
    margin = (z * math.sqrt((p * (1.0 - p) + (z ** 2) / (4.0 * total)) / total)) / denom
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return round(p * 100.0, 1), round(lower * 100.0, 1), round(upper * 100.0, 1)


class ShadowAuditEngine:
    """
    Engine analitik kuantitatif mandiri untuk evaluasi komparasi Shadow Tracker vs Real MT5.
    """

    def __init__(
        self,
        trades_log_path: str = SHADOW_TRADES_LOG,
        state_file_path: str = SHADOW_STATE_FILE,
        lookback_days: Optional[int] = None
    ):
        self.trades_log_path = trades_log_path
        self.state_file_path = state_file_path
        self.lookback_days = lookback_days
        self.cutoff_iso: Optional[str] = None
        if lookback_days is not None and lookback_days > 0:
            cutoff_dt = datetime.now(WIB) - timedelta(days=lookback_days)
            self.cutoff_iso = cutoff_dt.isoformat()

        self.raw_resolved: List[Dict[str, Any]] = []
        self.raw_active: List[Dict[str, Any]] = []
        self.raw_pending: List[Dict[str, Any]] = []
        self.mt5_deals: List[Dict[str, Any]] = []

    def load_data(self, mt5_connector: Any = None) -> ShadowAuditEngine:
        """Memuat seluruh rekaman trades dari JSONL, state JSON, dan MT5 closed deals."""
        self.raw_resolved = []
        if os.path.exists(self.trades_log_path):
            try:
                with open(self.trades_log_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            if self.cutoff_iso and item.get("created_at", "") < self.cutoff_iso:
                                continue
                            self.raw_resolved.append(item)
                        except Exception:
                            continue
            except Exception as e:
                logger.error(f"Gagal membaca shadow trades log: {e}")

        self.raw_active = []
        self.raw_pending = []
        if os.path.exists(self.state_file_path):
            try:
                with open(self.state_file_path, "r", encoding="utf-8") as f:
                    st = json.load(f)
                for t in st.get("active_trades", []):
                    if self.cutoff_iso and t.get("created_at", "") < self.cutoff_iso:
                        continue
                    if t.get("status") == "PENDING":
                        self.raw_pending.append(t)
                    else:
                        self.raw_active.append(t)
            except Exception as e:
                logger.error(f"Gagal membaca shadow state file: {e}")

        # Ingest MT5 deals history
        self.mt5_deals = []
        if mt5_connector is not None and hasattr(mt5_connector, "get_closed_positions_today"):
            try:
                hours = (self.lookback_days * 24) if self.lookback_days else 168
                self.mt5_deals = mt5_connector.get_closed_positions_today(lookback_hours=hours) or []
            except Exception as e:
                logger.warning(f"Tidak dapat mengambil histori MT5: {e}")

        return self

    def consolidate_debiased_legs(self, trades_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Mengelompokkan tiket yang overlap pada pair & arah yang sama menjadi 1 Trade Leg Episode.
        Menghilangkan bias amplifikasi tiket duplikat pada tren panjang.
        """
        if not trades_list:
            return []

        # Sort kronologis ascending berdasarkan created_at
        sorted_trades = sorted(trades_list, key=lambda x: str(x.get("created_at", "")))

        # Kelompokkan per (symbol, direction)
        by_pair_dir: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for t in sorted_trades:
            sym = t.get("symbol", "")
            d = t.get("direction", "BUY")
            by_pair_dir.setdefault((sym, d), []).append(t)

        consolidated_legs: List[Dict[str, Any]] = []

        for (sym, d), group in by_pair_dir.items():
            current_cluster: List[Dict[str, Any]] = []
            cluster_end_time: str = ""

            for item in group:
                c_at = str(item.get("created_at", ""))
                r_at = str(item.get("resolved_time") or "")
                status = item.get("status", "RESOLVED")

                # Jika trade masih ACTIVE, asumsikan rentang berakhir jauh di masa depan
                effective_end = r_at if status == "RESOLVED" and r_at else "9999-99-99"

                if not current_cluster:
                    current_cluster.append(item)
                    cluster_end_time = effective_end
                else:
                    # Cek overlap: jika tiket baru dibuat sebelum klaster sebelumnya selesai
                    if c_at <= cluster_end_time:
                        current_cluster.append(item)
                        if effective_end > cluster_end_time:
                            cluster_end_time = effective_end
                    else:
                        # Tutup klaster sebelumnya dan buat klaster baru
                        consolidated_legs.append(self._reduce_cluster_to_leg(current_cluster))
                        current_cluster = [item]
                        cluster_end_time = effective_end

            if current_cluster:
                consolidated_legs.append(self._reduce_cluster_to_leg(current_cluster))

        # Sort hasil konsolidasi kronologis
        consolidated_legs.sort(key=lambda x: str(x.get("created_at", "")))
        return consolidated_legs

    def _reduce_cluster_to_leg(self, cluster: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merangkum sekelompok tiket overlap menjadi 1 Trade Leg."""
        lead = cluster[0]
        count = len(cluster)
        if count == 1:
            res = dict(lead)
            res["ticket_count"] = 1
            return res

        # Kumpulkan nilai representatif
        filled = [t for t in cluster if t.get("status") in ("ACTIVE", "RESOLVED") and t.get("outcome") != "EXPIRED_NO_FILL"]
        net_r_vals = [float(t.get("net_r", 0.0) or 0.0) for t in cluster if t.get("net_r") is not None]
        avg_net_r = round(sum(net_r_vals) / len(net_r_vals), 2) if net_r_vals else (float(lead.get("net_r", 0.0) or 0.0))

        # Peak MFE & MAE
        mfes = [float(t.get("peak_mfe_r", 0.0) or 0.0) for t in cluster]
        maes = [float(t.get("max_mae_r", 0.0) or 0.0) for t in cluster]
        max_mfe = max(mfes) if mfes else 0.0
        min_mae = min(maes) if maes else 0.0

        # Outcome representatif
        outcomes = [t.get("outcome") for t in cluster if t.get("outcome")]
        if "TP_HIT" in outcomes:
            rep_outcome = "TP_HIT"
        elif "TRAILING_SL_HIT" in outcomes:
            rep_outcome = "TRAILING_SL_HIT"
        elif "BEP_HIT" in outcomes:
            rep_outcome = "BEP_HIT"
        elif "SL_HIT" in outcomes:
            rep_outcome = "SL_HIT"
        elif "TIME_DECAY_EXIT" in outcomes:
            rep_outcome = "TIME_DECAY_EXIT"
        elif outcomes:
            rep_outcome = outcomes[0]
        else:
            rep_outcome = lead.get("outcome")

        # Disposition: utamakan EXECUTED_MT5 jika salah satu dieksekusi
        disps = [t.get("mt5_disposition") for t in cluster]
        rep_disp = "EXECUTED_MT5" if "EXECUTED_MT5" in disps else lead.get("mt5_disposition", "SKIPPED_MAX_POSITIONS")

        # Status
        statuses = [t.get("status") for t in cluster]
        rep_status = "ACTIVE" if "ACTIVE" in statuses else ("PENDING" if "PENDING" in statuses else "RESOLVED")

        # Waktu resolved
        res_times = [t.get("resolved_time") for t in cluster if t.get("resolved_time")]
        latest_res = max(res_times) if res_times else lead.get("resolved_time")

        leg = dict(lead)
        leg["shadow_id"] = f"{lead['shadow_id']}_LEGx{count}"
        leg["status"] = rep_status
        leg["outcome"] = rep_outcome
        leg["net_r"] = avg_net_r
        leg["peak_mfe_r"] = round(max_mfe, 2)
        leg["max_mae_r"] = round(min_mae, 2)
        leg["mt5_disposition"] = rep_disp
        leg["resolved_time"] = latest_res
        leg["ticket_count"] = count
        leg["raw_tickets"] = [t["shadow_id"] for t in cluster]
        return leg

    def compute_analytics(self, trades_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Menghitung metrik kuantitatif lengkap dari daftar trade yang diberikan."""
        total_tracked = len(trades_list)
        resolved = [t for t in trades_list if t.get("status") == "RESOLVED"]
        active = [t for t in trades_list if t.get("status") == "ACTIVE"]
        pending = [t for t in trades_list if t.get("status") == "PENDING"]

        tp_trades = [t for t in resolved if t.get("outcome") == "TP_HIT"]
        sl_trades = [t for t in resolved if t.get("outcome") == "SL_HIT"]
        bep_trades = [t for t in resolved if t.get("outcome") in ("BEP_HIT", "TRAILING_SL_HIT")]
        td_trades = [t for t in resolved if t.get("outcome") == "TIME_DECAY_EXIT"]
        exp_trades = [t for t in resolved if str(t.get("outcome", "")).startswith("EXPIRED")]

        decisive = len(tp_trades) + len(sl_trades)
        tp_count = len(tp_trades)
        sl_count = len(sl_trades)
        bep_count = len(bep_trades)

        wr_pct, wr_lower, wr_upper = compute_wilson_ci(tp_count, decisive)

        # R-Multiple aggregation
        net_r_vals = [float(t.get("net_r", 0.0) or 0.0) for t in resolved if t.get("net_r") is not None]
        wins_r = [r for r in net_r_vals if r > 0]
        loss_r = [abs(r) for r in net_r_vals if r < 0]

        gross_win_r = round(sum(wins_r), 2)
        gross_loss_r = round(sum(loss_r), 2)
        cum_net_r = round(gross_win_r - gross_loss_r, 2)
        pf = round(gross_win_r / gross_loss_r, 2) if gross_loss_r > 0 else (99.0 if gross_win_r > 0 else 0.0)
        ev_r = round(cum_net_r / len(resolved), 2) if resolved else 0.0
        avg_win_r = round(gross_win_r / len(wins_r), 2) if wins_r else 0.0
        avg_loss_r = round(gross_loss_r / len(loss_r), 2) if loss_r else 0.0

        # Max Drawdown R
        running_r = 0.0
        peak_r = 0.0
        max_dd_r = 0.0
        for r in net_r_vals:
            running_r += r
            if running_r > peak_r:
                peak_r = running_r
            dd = peak_r - running_r
            if dd > max_dd_r:
                max_dd_r = dd
        max_dd_r = round(max_dd_r, 2)

        # -------------------------------------------------------------
        # 1. COUNTERFACTUAL OPPORTUNITY COST (Per Gate Disposition)
        # -------------------------------------------------------------
        disp_map: Dict[str, Dict[str, Any]] = {}
        for t in trades_list:
            disp = str(t.get("mt5_disposition", "OTHER") or "OTHER")
            if disp not in disp_map:
                disp_map[disp] = {
                    "count": 0, "resolved": 0, "tp": 0, "sl": 0, "bep": 0,
                    "net_r": 0.0, "gross_win_r": 0.0, "gross_loss_r": 0.0
                }
            dm = disp_map[disp]
            dm["count"] += 1
            if t.get("status") == "RESOLVED":
                dm["resolved"] += 1
                nr = float(t.get("net_r", 0.0) or 0.0)
                dm["net_r"] += nr
                if nr > 0: dm["gross_win_r"] += nr
                elif nr < 0: dm["gross_loss_r"] += abs(nr)
                out = t.get("outcome")
                if out == "TP_HIT": dm["tp"] += 1
                elif out == "SL_HIT": dm["sl"] += 1
                elif out in ("BEP_HIT", "TRAILING_SL_HIT"): dm["bep"] += 1

        for k, v in disp_map.items():
            v["net_r"] = round(v["net_r"], 2)
            v["gross_win_r"] = round(v["gross_win_r"], 2)
            v["gross_loss_r"] = round(v["gross_loss_r"], 2)
            dec = v["tp"] + v["sl"]
            v["winrate"] = round(v["tp"] / dec * 100.0, 1) if dec > 0 else 0.0
            v["profit_factor"] = round(v["gross_win_r"] / v["gross_loss_r"], 2) if v["gross_loss_r"] > 0 else 99.0

        # Opportunity cost metrics
        real_mt5 = disp_map.get("EXECUTED_MT5", {})
        skipped_max = disp_map.get("SKIPPED_MAX_POSITIONS", {})
        skipped_anchor = disp_map.get("SKIPPED_ANCHOR_TOO_WIDE", {})

        lost_profit_r = round(skipped_max.get("net_r", 0.0) + skipped_anchor.get("net_r", 0.0), 2)
        capital_saved_r = round(skipped_max.get("gross_loss_r", 0.0) + skipped_anchor.get("gross_loss_r", 0.0), 2)

        # -------------------------------------------------------------
        # 2. EDGE ATTRIBUTION (Mekanisme M1..M4 & Tier)
        # -------------------------------------------------------------
        mech_map: Dict[str, Dict[str, Any]] = {
            "M1": {"label": "M1 Universal Liquidity Sweep", "count": 0, "tp": 0, "sl": 0, "bep": 0, "net_r": 0.0, "gross_win": 0.0, "gross_loss": 0.0},
            "M2": {"label": "M2 Trend-Aligned Pullback", "count": 0, "tp": 0, "sl": 0, "bep": 0, "net_r": 0.0, "gross_win": 0.0, "gross_loss": 0.0},
            "M3": {"label": "M3 Breakout Retest", "count": 0, "tp": 0, "sl": 0, "bep": 0, "net_r": 0.0, "gross_win": 0.0, "gross_loss": 0.0},
            "M4": {"label": "M4 Systemic Flow Continuation", "count": 0, "tp": 0, "sl": 0, "bep": 0, "net_r": 0.0, "gross_win": 0.0, "gross_loss": 0.0},
        }

        tier_map: Dict[str, Dict[str, Any]] = {
            "GRADE_S": {"label": "Grade S (Macro Shock >=2.5R)", "count": 0, "tp": 0, "sl": 0, "net_r": 0.0},
            "GRADE_A_PLUS": {"label": "Grade A+ (Breached Wall 1.8-2.5R)", "count": 0, "tp": 0, "sl": 0, "net_r": 0.0},
            "GRADE_A": {"label": "Grade A (Standard 1.25-1.8R)", "count": 0, "tp": 0, "sl": 0, "net_r": 0.0},
            "GRADE_B": {"label": "Grade B (Wall Scalp 0.75-1.25R)", "count": 0, "tp": 0, "sl": 0, "net_r": 0.0},
        }

        for t in resolved:
            stype = str(t.get("setup_type", ""))
            key = "M1" if "UNIVER" in stype or "SWEEP" in stype else (
                "M2" if "PULLBACK" in stype or "TREND" in stype else (
                    "M3" if "BREAK" in stype or "MULTI" in stype else (
                        "M4" if "FLOW" in stype or "SYSTEM" in stype else "OTHER"
                    )
                )
            )
            if key in mech_map:
                m = mech_map[key]
                m["count"] += 1
                nr = float(t.get("net_r", 0.0) or 0.0)
                m["net_r"] += nr
                if nr > 0: m["gross_win"] += nr
                elif nr < 0: m["gross_loss"] += abs(nr)
                out = t.get("outcome")
                if out == "TP_HIT": m["tp"] += 1
                elif out == "SL_HIT": m["sl"] += 1
                elif out in ("BEP_HIT", "TRAILING_SL_HIT"): m["bep"] += 1

            meta = t.get("metadata", {}) or {}
            g_grade = str(meta.get("setup_grade") or t.get("setup_grade") or "GRADE_A")
            if g_grade in tier_map:
                tm = tier_map[g_grade]
                tm["count"] += 1
                tm["net_r"] += float(t.get("net_r", 0.0) or 0.0)
                out = t.get("outcome")
                if out == "TP_HIT": tm["tp"] += 1
                elif out == "SL_HIT": tm["sl"] += 1

        for k, v in mech_map.items():
            v["net_r"] = round(v["net_r"], 2)
            v["gross_win"] = round(v["gross_win"], 2)
            v["gross_loss"] = round(v["gross_loss"], 2)
            dec = v["tp"] + v["sl"]
            v["winrate"], v["wr_low"], v["wr_high"] = compute_wilson_ci(v["tp"], dec)
            v["profit_factor"] = round(v["gross_win"] / v["gross_loss"], 2) if v["gross_loss"] > 0 else 99.0

        for k, v in tier_map.items():
            v["net_r"] = round(v["net_r"], 2)
            dec = v["tp"] + v["sl"]
            v["winrate"] = round(v["tp"] / dec * 100.0, 1) if dec > 0 else 0.0

        # -------------------------------------------------------------
        # 3. BEP EFFICIENCY & EXCURSION DYNAMICS
        # -------------------------------------------------------------
        bep_saved = 0
        bep_stolen = 0
        bep_neutral = 0

        for t in bep_trades:
            mae = float(t.get("max_mae_r", 0.0) or 0.0)
            mfe = float(t.get("peak_mfe_r", 0.0) or 0.0)
            target_r = float(t.get("risk_reward", 1.5) or 1.5)
            # Jika MAE mendekati atau melampaui -0.9R, posisi ini selamat berkat BEP
            if mae <= -0.85:
                bep_saved += 1
            # Jika Peak MFE mencapai target TP penuh setelah kena BEP (stolen runner)
            elif mfe >= target_r * 0.95:
                bep_stolen += 1
            else:
                bep_neutral += 1

        total_bep_evaluated = bep_saved + bep_stolen
        bep_efficiency_pct = round(bep_saved / total_bep_evaluated * 100.0, 1) if total_bep_evaluated > 0 else 75.0

        # Equity Curve Points
        equity_curve: List[Dict[str, Any]] = []
        cum_r = 0.0
        cum_mt5_r = 0.0
        cum_skip_r = 0.0

        for idx, t in enumerate(resolved):
            nr = float(t.get("net_r", 0.0) or 0.0)
            cum_r += nr
            disp = str(t.get("mt5_disposition", ""))
            if "EXECUTED" in disp:
                cum_mt5_r += nr
            else:
                cum_skip_r += nr

            equity_curve.append({
                "index": idx + 1,
                "shadow_id": t.get("shadow_id", ""),
                "symbol": t.get("symbol", ""),
                "time": str(t.get("resolved_time") or t.get("created_at") or "")[:19],
                "trade_r": nr,
                "cum_total_r": round(cum_r, 2),
                "cum_mt5_r": round(cum_mt5_r, 2),
                "cum_skipped_r": round(cum_skip_r, 2)
            })

        # MFE vs MAE Scatter Points
        scatter_points: List[Dict[str, Any]] = []
        for t in resolved:
            scatter_points.append({
                "id": t.get("shadow_id", ""),
                "symbol": t.get("symbol", ""),
                "outcome": t.get("outcome", "RESOLVED"),
                "net_r": float(t.get("net_r", 0.0) or 0.0),
                "mae": float(t.get("max_mae_r", 0.0) or 0.0),
                "mfe": float(t.get("peak_mfe_r", 0.0) or 0.0),
                "setup_type": t.get("setup_type", ""),
                "disposition": t.get("mt5_disposition", "")
            })

        return {
            "total_tracked": total_tracked,
            "total_resolved": len(resolved),
            "active_count": len(active),
            "pending_count": len(pending),
            "tp_count": tp_count,
            "sl_count": sl_count,
            "bep_count": bep_count,
            "time_decay_count": len(td_trades),
            "expired_count": len(exp_trades),
            "decisive_count": decisive,
            "winrate_pct": wr_pct,
            "winrate_ci_lower": wr_lower,
            "winrate_ci_upper": wr_upper,
            "gross_win_r": gross_win_r,
            "gross_loss_r": gross_loss_r,
            "cumulative_net_r": cum_net_r,
            "profit_factor": pf,
            "expected_value_r": ev_r,
            "avg_win_r": avg_win_r,
            "avg_loss_r": avg_loss_r,
            "max_drawdown_r": max_dd_r,
            "disposition_stats": disp_map,
            "lost_profit_r": lost_profit_r,
            "capital_saved_r": capital_saved_r,
            "bep_saved_count": bep_saved,
            "bep_stolen_count": bep_stolen,
            "bep_neutral_count": bep_neutral,
            "bep_efficiency_pct": bep_efficiency_pct,
            "mechanism_stats": mech_map,
            "tier_stats": tier_map,
            "equity_curve": equity_curve,
            "scatter_points": scatter_points,
            "trades_table": trades_list
        }

    def generate_executive_audit(self) -> Dict[str, Any]:
        """Menghasilkan dataset lengkap untuk mode Raw Signals dan De-biased Legs."""
        # Kombinasikan resolved + active + pending untuk kedua mode
        all_raw = self.raw_resolved + self.raw_active + self.raw_pending
        all_debiased = self.consolidate_debiased_legs(all_raw)

        raw_metrics = self.compute_analytics(all_raw)
        debiased_metrics = self.compute_analytics(all_debiased)

        # Hitung ringkasan MT5
        mt5_wins = [d for d in self.mt5_deals if float(d.get("profit", 0.0) or 0.0) > 0]
        mt5_loss = [d for d in self.mt5_deals if float(d.get("profit", 0.0) or 0.0) < 0]
        mt5_tot_profit = sum(float(d.get("profit", 0.0) or 0.0) for d in self.mt5_deals)
        mt5_gross_win = sum(float(d.get("profit", 0.0) or 0.0) for d in mt5_wins)
        mt5_gross_loss = abs(sum(float(d.get("profit", 0.0) or 0.0) for d in mt5_loss))
        mt5_pf = round(mt5_gross_win / mt5_gross_loss, 2) if mt5_gross_loss > 0 else 99.0
        mt5_wr = round(len(mt5_wins) / len(self.mt5_deals) * 100.0, 1) if self.mt5_deals else 0.0

        mt5_summary = {
            "total_deals": len(self.mt5_deals),
            "wins": len(mt5_wins),
            "losses": len(mt5_loss),
            "winrate_pct": mt5_wr,
            "net_profit_usd": round(mt5_tot_profit, 2),
            "gross_win_usd": round(mt5_gross_win, 2),
            "gross_loss_usd": round(mt5_gross_loss, 2),
            "profit_factor": mt5_pf
        }

        return {
            "timestamp": datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB"),
            "lookback_days": self.lookback_days or "All History",
            "mt5_summary": mt5_summary,
            "debiased": debiased_metrics,
            "raw": raw_metrics
        }

    def render_html_dashboard(self, output_path: str = DEFAULT_HTML_OUTPUT) -> str:
        """Merender Single-File Self-Contained HTML Executive Dashboard."""
        payload = self.generate_executive_audit()
        payload_json = json.dumps(payload, ensure_ascii=False)

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        html_content = f"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quant Shadow Executive Audit | Dual-Mode Performance Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" />
<!-- Chart.js v4.4.1 Standalone CDN -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
:root {{
  --bg-base: #080b11;
  --bg-surface: #0f1523;
  --bg-card: #131b2c;
  --bg-card-hover: #18233a;
  --border: #1a2333;
  --border-strong: #26354d;
  
  --text-main: #f1f5f9;
  --text-muted: #94a3b8;
  --text-dim: #64748b;
  
  --green: #00e676;
  --green-glow: rgba(0, 230, 118, 0.15);
  --red: #ff5252;
  --red-glow: rgba(255, 82, 82, 0.15);
  --cyan: #38bdf8;
  --cyan-glow: rgba(56, 189, 248, 0.15);
  --amber: #ffd740;
  --purple: #b388ff;
  --blue: #60a5fa;

  --font-ui: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-mono: 'JetBrains Mono', monospace;
}}

* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  background: var(--bg-base);
  color: var(--text-main);
  font-family: var(--font-ui);
  min-height: 100vh;
  padding: 24px;
  line-height: 1.5;
}}

.material-symbols-outlined {{
  font-family: 'Material Symbols Outlined';
  font-weight: normal;
  font-size: 16px;
  vertical-align: middle;
}}

.dashboard-container {{
  max-width: 1480px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}}

/* Top Header Bar */
.top-nav {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  padding: 16px 24px;
  border-radius: 12px;
}}
.nav-left {{
  display: flex;
  align-items: center;
  gap: 14px;
}}
.brand-badge {{
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(179, 136, 255, 0.2));
  border: 1px solid var(--cyan);
  padding: 6px 12px;
  border-radius: 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
  color: var(--cyan);
  letter-spacing: 0.5px;
}}
.nav-title h1 {{
  font-size: 18px;
  font-weight: 700;
  color: var(--text-main);
  letter-spacing: -0.3px;
}}
.nav-title p {{
  font-size: 12px;
  color: var(--text-dim);
  font-family: var(--font-mono);
}}

.nav-right {{
  display: flex;
  align-items: center;
  gap: 16px;
}}

/* Dual Mode Toggle Button Group */
.toggle-group {{
  display: flex;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 3px;
}}
.toggle-btn {{
  background: transparent;
  border: none;
  color: var(--text-muted);
  font-family: var(--font-ui);
  font-size: 12px;
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s;
}}
.toggle-btn.active {{
  background: var(--bg-card);
  color: var(--cyan);
  border: 1px solid var(--border-strong);
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}}

/* Row 1: KPI Cards Grid */
.kpi-grid {{
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 16px;
}}
.kpi-card {{
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
  position: relative;
  overflow: hidden;
}}
.kpi-card::before {{
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0; height: 2px;
  background: var(--cyan);
}}
.kpi-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}}
.kpi-value {{
  font-family: var(--font-mono);
  font-size: 26px;
  font-weight: 700;
  color: var(--text-main);
  line-height: 1.2;
}}
.kpi-subtext {{
  font-size: 11px;
  color: var(--text-dim);
  font-family: var(--font-mono);
  display: flex;
  align-items: center;
  gap: 6px;
}}
.badge-pill {{
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
}}
.badge-green {{ background: var(--green-glow); color: var(--green); border: 1px solid rgba(0,230,118,0.3); }}
.badge-red {{ background: var(--red-glow); color: var(--red); border: 1px solid rgba(255,82,82,0.3); }}
.badge-cyan {{ background: var(--cyan-glow); color: var(--cyan); border: 1px solid rgba(56,189,248,0.3); }}

/* Dual Charts Row */
.chart-row {{
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
}}
.chart-card {{
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}}
.chart-title {{
  font-size: 14px;
  font-weight: 700;
  color: var(--text-main);
  display: flex;
  align-items: center;
  justify-content: space-between;
}}
.chart-canvas-container {{
  position: relative;
  width: 100%;
  height: 280px;
}}

/* Row 3: Mechanism & Scatter Grid */
.deep-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}}

/* Interactive Table Card */
.table-card {{
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}}
.table-toolbar {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}}
.search-input {{
  background: var(--bg-base);
  border: 1px solid var(--border);
  color: var(--text-main);
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 8px 14px;
  border-radius: 6px;
  width: 320px;
  outline: none;
}}
.search-input:focus {{
  border-color: var(--cyan);
}}

.table-responsive {{
  overflow-x: auto;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  text-align: left;
}}
th {{
  background: var(--bg-card);
  color: var(--text-muted);
  font-weight: 600;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-strong);
  font-family: var(--font-mono);
  font-size: 11px;
  text-transform: uppercase;
  cursor: pointer;
}}
th:hover {{
  color: var(--cyan);
}}
td {{
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  font-family: var(--font-mono);
  color: var(--text-main);
}}
tr:hover td {{
  background: var(--bg-card-hover);
}}
.tag-pill {{
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10.5px;
  font-weight: 600;
}}

@media (max-width: 1200px) {{
  .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
  .chart-row {{ grid-template-columns: 1fr; }}
  .deep-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>

<div class="dashboard-container">

  <!-- Top Navigation & Controls -->
  <header class="top-nav">
    <div class="nav-left">
      <div class="brand-badge">STAGE 1 RADAR</div>
      <div class="nav-title">
        <h1>Quant Shadow Executive Audit</h1>
        <p id="snapshot-time">Snapshot: {payload["timestamp"]} │ MT5 Connected</p>
      </div>
    </div>
    <div class="nav-right">
      <div class="toggle-group">
        <button class="toggle-btn active" id="btn-debiased" onclick="switchMode('debiased')">
          <span class="material-symbols-outlined">filter_alt</span> De-biased Legs (Unique)
        </button>
        <button class="toggle-btn" id="btn-raw" onclick="switchMode('raw')">
          <span class="material-symbols-outlined">reorder</span> Raw Signals (All Triggers)
        </button>
      </div>
    </div>
  </header>

  <!-- Row 1: Executive KPI Cards -->
  <section class="kpi-grid">
    <!-- Card 1: MT5 Real Deals -->
    <div class="kpi-card" style="--cyan: var(--green);">
      <div class="kpi-header">
        <span>Real MT5 Profit</span>
        <span class="material-symbols-outlined" style="color:var(--green);">account_balance_wallet</span>
      </div>
      <div class="kpi-value" id="kpi-mt5-profit" style="color:var(--green);">$0.00</div>
      <div class="kpi-subtext" id="kpi-mt5-subtext">59 Deals • Win: 69.5% (PF 1.22)</div>
    </div>

    <!-- Card 2: Decisive Winrate with Wilson CI -->
    <div class="kpi-card">
      <div class="kpi-header">
        <span>Decisive Win Rate</span>
        <span class="material-symbols-outlined" style="color:var(--cyan);">insights</span>
      </div>
      <div class="kpi-value" id="kpi-winrate">0.0%</div>
      <div class="kpi-subtext" id="kpi-winrate-ci">
        <span class="badge-pill badge-cyan" id="badge-ci">95% CI: [—]</span>
      </div>
    </div>

    <!-- Card 3: Profit Factor & Expected Value -->
    <div class="kpi-card">
      <div class="kpi-header">
        <span>Profit Factor / EV</span>
        <span class="material-symbols-outlined" style="color:var(--amber);">query_stats</span>
      </div>
      <div class="kpi-value" id="kpi-pf">0.00</div>
      <div class="kpi-subtext" id="kpi-ev">EV: +0.00R/trade • Cum: +0.00R</div>
    </div>

    <!-- Card 4: Opportunity Cost Delta -->
    <div class="kpi-card" style="--cyan: var(--purple);">
      <div class="kpi-header">
        <span>Opportunity Cost Delta</span>
        <span class="material-symbols-outlined" style="color:var(--purple);">swap_horiz</span>
      </div>
      <div class="kpi-value" id="kpi-opp-cost" style="color:var(--purple);">+0.00R</div>
      <div class="kpi-subtext" id="kpi-opp-subtext">Lost Profit vs Saved Capital</div>
    </div>

    <!-- Card 5: BEP Protection Ratio -->
    <div class="kpi-card" style="--cyan: var(--amber);">
      <div class="kpi-header">
        <span>BEP Protection Ratio</span>
        <span class="material-symbols-outlined" style="color:var(--amber);">verified_user</span>
      </div>
      <div class="kpi-value" id="kpi-bep-ratio">0.0%</div>
      <div class="kpi-subtext" id="kpi-bep-subtext">Saved: 0 • Stolen Runner: 0</div>
    </div>
  </section>

  <!-- Row 2: Dual Charts (Equity Curves & Gate Matrix) -->
  <section class="chart-row">
    <!-- Chart A: Comparative Cumulative Equity Curve -->
    <div class="chart-card">
      <div class="chart-title">
        <span>Comparative Cumulative Equity Curve (R-Multiple)</span>
        <span class="badge-pill badge-cyan">Chronological Progression</span>
      </div>
      <div class="chart-canvas-container">
        <canvas id="chart-equity"></canvas>
      </div>
    </div>

    <!-- Chart B: Gate Disposition Breakdown -->
    <div class="chart-card">
      <div class="chart-title">
        <span>Gate Disposition Net R</span>
        <span class="badge-pill badge-cyan">Opportunity Delta</span>
      </div>
      <div class="chart-canvas-container">
        <canvas id="chart-gates"></canvas>
      </div>
    </div>
  </section>

  <!-- Row 3: Deep-Dive Edge & Scatter Grid -->
  <section class="deep-grid">
    <!-- Chart C: Mechanism Performance -->
    <div class="chart-card">
      <div class="chart-title">
        <span>Mechanism Edge Attribution (M1 - M4)</span>
        <span class="badge-pill badge-cyan">Net R & Win Rate</span>
      </div>
      <div class="chart-canvas-container">
        <canvas id="chart-mechanisms"></canvas>
      </div>
    </div>

    <!-- Chart D: MFE vs MAE Scatter Plot -->
    <div class="chart-card">
      <div class="chart-title">
        <span>Excursion Dynamics (Peak MFE vs Max MAE)</span>
        <span class="badge-pill badge-cyan">Safety Floor Validation</span>
      </div>
      <div class="chart-canvas-container">
        <canvas id="chart-scatter"></canvas>
      </div>
    </div>
  </section>

  <!-- Row 4: Interactive Trade Explorer Table -->
  <section class="table-card">
    <div class="table-toolbar">
      <div class="chart-title" style="margin-bottom:0;">
        <span>Interactive Trade Explorer</span>
        <span class="badge-pill badge-cyan" id="table-count-badge">0 Trades</span>
      </div>
      <input type="text" class="search-input" id="table-search" placeholder="Search symbol, mechanism, outcome, or disposition..." onkeyup="filterTable()">
    </div>
    <div class="table-responsive">
      <table id="trades-table">
        <thead>
          <tr>
            <th onclick="sortTable(0)">ID / Symbol</th>
            <th onclick="sortTable(1)">Side</th>
            <th onclick="sortTable(2)">Mechanism</th>
            <th onclick="sortTable(3)">Grade</th>
            <th onclick="sortTable(4)">Entry / SL / TP</th>
            <th onclick="sortTable(5)">Disposition</th>
            <th onclick="sortTable(6)">Outcome</th>
            <th onclick="sortTable(7)">Net R</th>
            <th onclick="sortTable(8)">MFE / MAE</th>
            <th onclick="sortTable(9)">Created Time</th>
          </tr>
        </thead>
        <tbody id="table-body">
          <!-- Populated by JavaScript -->
        </tbody>
      </table>
    </div>
  </section>

</div>

<script>
// Embedded Data Payload
const AUDIT_DATA = {payload_json};

let currentMode = "debiased";
let chartEquityInstance = null;
let chartGatesInstance = null;
let chartMechInstance = null;
let chartScatterInstance = null;

// Mode Switcher
function switchMode(mode) {{
  currentMode = mode;
  document.getElementById("btn-debiased").classList.toggle("active", mode === "debiased");
  document.getElementById("btn-raw").classList.toggle("active", mode === "raw");
  renderAll();
}}

function renderAll() {{
  const data = AUDIT_DATA[currentMode];
  const mt5 = AUDIT_DATA.mt5_summary;

  // 1. KPI Cards Update
  document.getElementById("kpi-mt5-profit").innerText = `${{mt5.net_profit_usd >= 0 ? '+' : ''}}$${{mt5.net_profit_usd.toFixed(2)}}`;
  document.getElementById("kpi-mt5-subtext").innerText = `${{mt5.total_deals}} Deals • Win: ${{mt5.winrate_pct}}% (PF ${{mt5.profit_factor}})`;

  document.getElementById("kpi-winrate").innerText = `${{data.winrate_pct}}%`;
  document.getElementById("badge-ci").innerText = `95% CI: [${{data.winrate_ci_lower}}% - ${{data.winrate_ci_upper}}%] (${{data.decisive_count}} Decisive)`;

  document.getElementById("kpi-pf").innerText = `${{data.profit_factor}}`;
  document.getElementById("kpi-ev").innerText = `EV: ${{data.expected_value_r >= 0 ? '+' : ''}}${{data.expected_value_r}}R/t • Cum: ${{data.cumulative_net_r >= 0 ? '+' : ''}}${{data.cumulative_net_r}}R`;

  const oppSign = data.lost_profit_r >= 0 ? "+" : "";
  document.getElementById("kpi-opp-cost").innerText = `${{oppSign}}${{data.lost_profit_r}}R`;
  document.getElementById("kpi-opp-subtext").innerText = `Lost: ${{oppSign}}${{data.lost_profit_r}}R │ Saved: +${{data.capital_saved_r}}R`;

  document.getElementById("kpi-bep-ratio").innerText = `${{data.bep_efficiency_pct}}%`;
  document.getElementById("kpi-bep-subtext").innerText = `Saved: ${{data.bep_saved_count}} • Stolen: ${{data.bep_stolen_count}}`;

  // 2. Charts Rendering
  renderEquityChart(data.equity_curve);
  renderGatesChart(data.disposition_stats);
  renderMechanismChart(data.mechanism_stats);
  renderScatterChart(data.scatter_points);

  // 3. Table Rendering
  renderTable(data.trades_table);
}}

function renderEquityChart(curveData) {{
  const ctx = document.getElementById("chart-equity").getContext("2d");
  if (chartEquityInstance) chartEquityInstance.destroy();

  const labels = curveData.map(d => `#${{d.index}} ${{d.symbol}}`);
  const totalR = curveData.map(d => d.cum_total_r);
  const mt5R = curveData.map(d => d.cum_mt5_r);
  const skipR = curveData.map(d => d.cum_skipped_r);

  chartEquityInstance = new Chart(ctx, {{
    type: "line",
    data: {{
      labels: labels,
      datasets: [
        {{
          label: "Total Unconstrained Radar (R)",
          data: totalR,
          borderColor: "#38bdf8",
          backgroundColor: "rgba(56, 189, 248, 0.08)",
          fill: true,
          tension: 0.2,
          borderWidth: 2
        }},
        {{
          label: "Live MT5 Executed (R)",
          data: mt5R,
          borderColor: "#00e676",
          borderWidth: 2,
          tension: 0.2
        }},
        {{
          label: "Skipped Filter Counterfactual (R)",
          data: skipR,
          borderColor: "#b388ff",
          borderWidth: 1.8,
          borderDash: [5, 5],
          tension: 0.2
        }}
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ labels: {{ color: "#94a3b8", font: {{ family: "'JetBrains Mono'" }} }} }}
      }},
      scales: {{
        x: {{ display: false }},
        y: {{
          grid: {{ color: "#1a2333" }},
          ticks: {{ color: "#94a3b8", font: {{ family: "'JetBrains Mono'" }} }}
        }}
      }}
    }}
  }});
}}

function renderGatesChart(dispStats) {{
  const ctx = document.getElementById("chart-gates").getContext("2d");
  if (chartGatesInstance) chartGatesInstance.destroy();

  const labels = Object.keys(dispStats).map(k => k.replace("SKIPPED_", ""));
  const netR = Object.values(dispStats).map(v => v.net_r);
  const colors = netR.map(r => r >= 0 ? "#00e676" : "#ff5252");

  chartGatesInstance = new Chart(ctx, {{
    type: "bar",
    data: {{
      labels: labels,
      datasets: [{{
        label: "Net Realized R",
        data: netR,
        backgroundColor: colors,
        borderRadius: 6
      }}]
    }},
    options: {{
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }}
      }},
      scales: {{
        x: {{
          grid: {{ color: "#1a2333" }},
          ticks: {{ color: "#94a3b8", font: {{ family: "'JetBrains Mono'" }} }}
        }},
        y: {{
          grid: {{ display: false }},
          ticks: {{ color: "#f1f5f9", font: {{ family: "'JetBrains Mono'", size: 11 }} }}
        }}
      }}
    }}
  }});
}}

function renderMechanismChart(mechStats) {{
  const ctx = document.getElementById("chart-mechanisms").getContext("2d");
  if (chartMechInstance) chartMechInstance.destroy();

  const labels = Object.keys(mechStats);
  const netR = Object.values(mechStats).map(v => v.net_r);
  const wr = Object.values(mechStats).map(v => v.winrate);

  chartMechInstance = new Chart(ctx, {{
    type: "bar",
    data: {{
      labels: labels,
      datasets: [
        {{
          label: "Net R",
          data: netR,
          backgroundColor: "#38bdf8",
          borderRadius: 6,
          yAxisID: "y"
        }},
        {{
          label: "Win Rate %",
          data: wr,
          type: "line",
          borderColor: "#ffd740",
          backgroundColor: "#ffd740",
          borderWidth: 2,
          yAxisID: "y1"
        }}
      ]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      scales: {{
        x: {{ grid: {{ color: "#1a2333" }}, ticks: {{ color: "#f1f5f9" }} }},
        y: {{ type: "linear", position: "left", grid: {{ color: "#1a2333" }}, ticks: {{ color: "#38bdf8" }} }},
        y1: {{ type: "linear", position: "right", grid: {{ display: false }}, ticks: {{ color: "#ffd740" }}, min: 0, max: 100 }}
      }}
    }}
  }});
}}

function renderScatterChart(points) {{
  const ctx = document.getElementById("chart-scatter").getContext("2d");
  if (chartScatterInstance) chartScatterInstance.destroy();

  const scatterData = points.map(p => ({{
    x: p.mae,
    y: p.mfe,
    title: `${{p.symbol}} (${{p.outcome}}): Net ${{p.net_r >= 0 ? '+' : ''}}${{p.net_r}}R`
  }}));

  chartScatterInstance = new Chart(ctx, {{
    type: "scatter",
    data: {{
      datasets: [{{
        label: "Trade Excursions",
        data: scatterData,
        backgroundColor: points.map(p => p.net_r > 0 ? "rgba(0, 230, 118, 0.7)" : "rgba(255, 82, 82, 0.7)"),
        pointRadius: 5
      }}]
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      scales: {{
        x: {{
          title: {{ display: true, text: "Max Adverse Excursion (Drawdown in R)", color: "#94a3b8" }},
          grid: {{ color: "#1a2333" }},
          ticks: {{ color: "#94a3b8" }}
        }},
        y: {{
          title: {{ display: true, text: "Peak MFE (Favorable in R)", color: "#94a3b8" }},
          grid: {{ color: "#1a2333" }},
          ticks: {{ color: "#94a3b8" }}
        }}
      }},
      plugins: {{
        tooltip: {{
          callbacks: {{
            label: function(ctx) {{ return ctx.raw.title; }}
          }}
        }}
      }}
    }}
  }});
}}

function renderTable(trades) {{
  const tbody = document.getElementById("table-body");
  tbody.innerHTML = "";
  document.getElementById("table-count-badge").innerText = `${{trades.length}} Trades`;

  trades.forEach(t => {{
    const tr = document.createElement("tr");
    const netR = t.net_r !== null && t.net_r !== undefined ? `${{t.net_r >= 0 ? '+' : ''}}${{t.net_r.toFixed(2)}}R` : "—";
    const netCol = (t.net_r || 0) > 0 ? "var(--green)" : ((t.net_r || 0) < 0 ? "var(--red)" : "var(--text-dim)");
    
    let outBadge = "badge-cyan";
    if (t.outcome === "TP_HIT") outBadge = "badge-green";
    else if (t.outcome === "SL_HIT") outBadge = "badge-red";
    else if (t.outcome === "BEP_HIT" || t.outcome === "TRAILING_SL_HIT") outBadge = "badge-cyan";

    const dispClean = (t.mt5_disposition || "OTHER").replace("SKIPPED_", "");
    const createdStr = (t.created_at || "").replace("T", " ").substring(0, 19);

    tr.innerHTML = `
      <td><strong>${{t.symbol}}</strong><br><span style="font-size:10px;color:var(--text-dim);">${{t.shadow_id}}</span></td>
      <td><span class="tag-pill ${{t.direction === 'BUY' ? 'badge-green' : 'badge-red'}}">${{t.direction}}</span></td>
      <td>${{t.setup_type}}</td>
      <td>${{t.action_tier || 'GRADE_A'}}</td>
      <td>${{t.entry_price}} / ${{t.sl_price}} / ${{t.tp_price}}</td>
      <td><span class="tag-pill badge-cyan">${{dispClean}}</span></td>
      <td><span class="tag-pill ${{outBadge}}">${{t.outcome || t.status}}</span></td>
      <td style="color:${{netCol}};font-weight:700;">${{netR}}</td>
      <td>MFE: +${{(t.peak_mfe_r||0).toFixed(2)}}R<br>MAE: ${{(t.max_mae_r||0).toFixed(2)}}R</td>
      <td style="font-size:11px;color:var(--text-dim);">${{createdStr}}</td>
    `;
    tbody.appendChild(tr);
  }});
}}

function filterTable() {{
  const query = document.getElementById("table-search").value.toLowerCase();
  const rows = document.getElementById("table-body").getElementsByTagName("tr");
  for (let r of rows) {{
    const text = r.innerText.toLowerCase();
    r.style.display = text.includes(query) ? "" : "none";
  }}
}}

function sortTable(n) {{
  const table = document.getElementById("trades-table");
  let rows = Array.from(table.rows).slice(1);
  let asc = table.getAttribute("data-sort-dir") !== "asc";
  table.setAttribute("data-sort-dir", asc ? "asc" : "desc");

  rows.sort((a, b) => {{
    let valA = a.cells[n].innerText.trim();
    let valB = b.cells[n].innerText.trim();
    return asc ? valA.localeCompare(valB, undefined, {{numeric: true}}) : valB.localeCompare(valA, undefined, {{numeric: true}});
  }});

  const tbody = document.getElementById("table-body");
  rows.forEach(r => tbody.appendChild(r));
}}

// Initial load
window.addEventListener("DOMContentLoaded", () => {{
  renderAll();
}});
</script>

</body>
</html>
"""
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"Dashboard HTML successfully written to: {output_path}")
        return output_path
