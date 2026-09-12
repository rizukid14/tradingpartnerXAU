"""
Zone Confluence Engine (ZCE) — RFC 11: docs/plans/ZONE_CONFLUENCE_ENGINE_SPEC.md
=================================================================================
Peta zona multi-TF x multi-horizon (OB/FVG/EQH/EQL/FRVP/psych/last-swing/EMA)
+ skoring konfluensi (J1: horizon = penguat bobot, bukan saksi independen)
+ freshness COLD/VACUUM + reachability + scale ladder 50..500 + SCALE_CONFLICT
+ elekt dinding F1..Fn / C1..Cm + suggested method + readiness score.

Pure Quant deterministik, 0 token LLM. MT5-agnostic: input = dict DataFrame per TF.
Keputusan desain & bobot default: RFC 11 bagian 6-8 (kalibrasi via forward test).

Integrasi:
  - Phase 2 (MSE consumption): zce_walls dict -> MacroStrategicEngine.compute_directive()
  - Phase 3 (scanner): komputasi saat macro cache refresh, flag ZCE_ENABLED.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import config
from src.indicators.lux_smc import LuxSMCAnalyzer
from src.indicators.volume_profile import compute_fixed_range_volume_profile
from src.indicators.atlas_dna import calculate_dual_grid_stations

# ----------------------------------------------------------------------------- #
#  Konstanta grid & bobot (default RFC 11; override via params dict / config)
# ----------------------------------------------------------------------------- #
ZCE_GRID: Dict[str, List[int]] = {
    "M30": [50, 150],
    "H1": [50, 100, 150, 250, 350, 500],
    "H4": [50, 100, 150, 250],
    "D1": [50, 100, 150, 250, 350, 500],
    "W1": [50, 100, 150],
    "MN1": [50, 100],
}
ZCE_LADDER_H1: List[int] = [50, 100, 150, 250, 500]
ZCE_FRVP_TFS = ("M30", "H1", "H4")          # FRVP hanya tf dengan tick_volume valid
ZCE_SWING_LENGTH = {"M30": 3, "H1": 5, "H4": 5, "D1": 3, "W1": 3, "MN1": 3}

ZCE_W_TF: Dict[str, float] = {"M30": 0.55, "H1": 1.00, "H4": 1.60, "D1": 2.20, "W1": 2.80, "MN1": 3.20}
ZCE_W_KIND: Dict[str, float] = {
    "EQH": 1.15, "EQL": 1.15, "MACRO_EXTREME": 1.20, "OB": 1.00,
    "FVG": 0.80, "FRVP_POC": 1.00, "FRVP_VAH": 0.85, "FRVP_VAL": 0.85,
    "SWING_HIGH": 0.85, "SWING_LOW": 0.85,
    "LAST_HIGH": 0.60, "LAST_LOW": 0.60, "PSYCH_MAJOR": 0.80, "PSYCH_SUB": 0.50,
    "EMA_BAND": 0.25,
}
ZCE_HORIZON_BOOST: List[tuple] = [(100, 1.00), (150, 1.10), (250, 1.20), (350, 1.30), (600, 1.35)]

CEIL_KINDS = {"SWING_HIGH", "EQH", "LAST_HIGH", "FRVP_VAH", "OB_BEAR", "FVG_BEAR", "C_ASIAN_HIGH", "C_PDH", "C_PWH"}
FLOOR_KINDS = {"SWING_LOW", "EQL", "LAST_LOW", "FRVP_VAL", "OB_BULL", "FVG_BULL", "F_ASIAN_LOW", "F_PDL", "F_PWL"}


def _horizon_boost(h: int, cap: float = 1.35) -> float:
    for limit, boost in ZCE_HORIZON_BOOST:
        if h < limit:
            return min(boost, cap)
    return min(1.30, cap)


def atr_from_df(df: pd.DataFrame, period: int = 14) -> float:
    """Wilder ATR sederhana pada kolom high/low/close."""
    h = df["high"].to_numpy(dtype=float)
    lo = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    n = len(df)
    if n < 2:
        return float(h[-1] - lo[-1]) if n else 1.0
    pc = np.empty(n)
    pc[0] = c[0]
    pc[1:] = c[:-1]
    tr = np.maximum.reduce([h - lo, np.abs(h - pc), np.abs(lo - pc)])
    if n < period:
        return float(np.mean(tr))
    # Wilder smoothing via ewm
    s = pd.Series(tr).ewm(alpha=1.0 / period, adjust=False).mean()
    return float(s.iloc[-1])


# ----------------------------------------------------------------------------- #
#  Model data (RFC 11 bagian 5)
# ----------------------------------------------------------------------------- #
@dataclass
class ZonePrimitive:
    kind: str
    tf: str
    horizon: int                 # 0 = level non-window (psych)
    top: float                   # tepi atas band
    bottom: float                # tepi bawah band
    index_age: int = 0           # umur (bar tf) relatif akhir window
    time: Optional[float] = None

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) * 0.5

    @property
    def width(self) -> float:
        return max(self.top - self.bottom, 0.0)


@dataclass
class ZoneCluster:
    cluster_id: int
    band_low: float
    band_high: float
    members: List[ZonePrimitive] = field(default_factory=list)
    score_final: float = 0.0
    score_raw: float = 0.0
    grade: str = "GRADE_1_MICRO"
    fortress_tag: str = ""
    horizon_max: int = 0
    tfs_present: List[str] = field(default_factory=list)
    kinds_present: List[str] = field(default_factory=list)
    width_atr: float = 0.0
    is_cold: bool = False
    is_vacuum: bool = False
    touch_count: int = 0
    last_touch_h1_bars_ago: Optional[int] = None
    inherent_role: str = ""
    confluence: int = 0          # jumlah pasangan unik (kind, tf) penyusun skor
    freshness_state: str = "FRESH_VIRGIN"  # 'FRESH_VIRGIN', 'TESTED_VALID', 'ABSORPTION_COIL', 'EXHAUSTED'
    freshness_label: str = "0x FRESH (Virgin)"
    compression_type: str = "NONE"          # 'HIGHER_LOWS', 'LOWER_HIGHS', 'FLAT', 'NONE'
    touch_nodes: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def mid(self) -> float:
        return (self.band_low + self.band_high) * 0.5


@dataclass
class ScaleLadder:
    symbol: str = ""
    pos_by_horizon: Dict[int, float] = field(default_factory=dict)
    conflict_flag: str = "NONE"
    conflict_detail: List[str] = field(default_factory=list)


@dataclass
class ZoneMapResult:
    symbol: str
    ts: float
    clusters: List[ZoneCluster] = field(default_factory=list)
    floors: List[dict] = field(default_factory=list)     # F1..Fn (dict tier/index/price/tag/...)
    ceilings: List[dict] = field(default_factory=list)   # C1..Cm
    immediate_floor_f1: Optional[float] = None
    immediate_ceiling_c1: Optional[float] = None
    deep_floor_f2: Optional[float] = None
    deep_ceiling_c2: Optional[float] = None
    immediate_floor_f1_grade: Optional[str] = None
    immediate_ceiling_c1_grade: Optional[str] = None
    immediate_floor_f1_score: float = 0.0
    immediate_ceiling_c1_score: float = 0.0
    deep_floor_f2_grade: Optional[str] = None
    deep_ceiling_c2_grade: Optional[str] = None
    deep_floor_f2_score: float = 0.0
    deep_ceiling_c2_score: float = 0.0
    immediate_floor_f1_confluence: int = 0
    immediate_ceiling_c1_confluence: int = 0
    c1_freshness_state: str = "FRESH_VIRGIN"
    c1_freshness_label: str = "0x FRESH (Virgin)"
    c1_touch_count: int = 0
    c1_compression_type: str = "NONE"
    f1_freshness_state: str = "FRESH_VIRGIN"
    f1_freshness_label: str = "0x FRESH (Virgin)"
    f1_touch_count: int = 0
    f1_compression_type: str = "NONE"
    inside_zone: bool = False
    inside_tiers: List[str] = field(default_factory=list)
    layer_count: int = 0
    ladder: ScaleLadder = field(default_factory=ScaleLadder)
    suggested_method: str = "NONE"
    method_reason: str = ""
    readiness_score: float = 0.0
    atr_h1: float = 0.0
    cur_price: float = 0.0
    wall_override: Dict[str, object] = field(default_factory=dict)

    def to_wall_override(self) -> Dict[str, object]:
        """Kontrak Phase-2: dict yang disuntikkan ke MSE (dinding ZCE)."""
        return {
            "enable": True,
            "imm_ceiling_c1": self.immediate_ceiling_c1,
            "imm_floor_f1": self.immediate_floor_f1,
            "deep_ceiling_c2": self.deep_ceiling_c2,
            "deep_floor_f2": self.deep_floor_f2,
            "imm_ceiling_c1_grade": self.immediate_ceiling_c1_grade,
            "imm_ceiling_c1_score": self.immediate_ceiling_c1_score,
            "imm_floor_f1_grade": self.immediate_floor_f1_grade,
            "imm_floor_f1_score": self.immediate_floor_f1_score,
            "deep_ceiling_c2_grade": self.deep_ceiling_c2_grade,
            "deep_ceiling_c2_score": self.deep_ceiling_c2_score,
            "deep_floor_f2_grade": self.deep_floor_f2_grade,
            "deep_floor_f2_score": self.deep_floor_f2_score,
            "c1_grade": self.immediate_ceiling_c1_grade,
            "f1_grade": self.immediate_floor_f1_grade,
            "c2_grade": self.deep_ceiling_c2_grade,
            "f2_grade": self.deep_floor_f2_grade,
            "c1_score": self.immediate_ceiling_c1_score,
            "f1_score": self.immediate_floor_f1_score,
            # P3 (backward-compatible, opsional): kekuatan confluence & status harga-di-dalam-zona
            "c1_confluence": self.immediate_ceiling_c1_confluence,
            "f1_confluence": self.immediate_floor_f1_confluence,
            "c1_freshness_state": self.c1_freshness_state,
            "c1_freshness_label": self.c1_freshness_label,
            "c1_touch_count": self.c1_touch_count,
            "c1_compression_type": self.c1_compression_type,
            "f1_freshness_state": self.f1_freshness_state,
            "f1_freshness_label": self.f1_freshness_label,
            "f1_touch_count": self.f1_touch_count,
            "f1_compression_type": self.f1_compression_type,
            "inside_zone": self.inside_zone,
            "layer_count": self.layer_count,
            "symbol": self.symbol,
            "zone_count": len(self.clusters),
        }


# ----------------------------------------------------------------------------- #
#  Engine
# ----------------------------------------------------------------------------- #
class ZoneConfluenceEngine:
    def __init__(self, params: Optional[dict] = None):
        p = params or {}
        self.grid = p.get("grid", ZCE_GRID)
        self.w_tf = p.get("w_tf", ZCE_W_TF)
        self.w_kind = dict(p.get("w_kind", ZCE_W_KIND))
        self.w_kind["EMA_BAND"] = float(p.get("ema_weight", getattr(config, "ZCE_EMA_WEIGHT", 0.25)))
        self.w_kind["ENVELOPE_CEIL"] = float(p.get("envelope_weight", 0.35))
        self.w_kind["ENVELOPE_FLOOR"] = float(p.get("envelope_weight", 0.35))
        self.grade_g2 = float(p.get("grade_g2", getattr(config, "ZCE_GRADE_G2_THRESHOLD", 5.0)))
        self.grade_g3 = float(p.get("grade_g3", getattr(config, "ZCE_GRADE_G3_THRESHOLD", 8.5)))
        self.merge_atr_mult = p.get("merge_atr_mult", 0.25)
        self.cold_days = p.get("cold_days", float(getattr(config, "ZCE_COLD_DAYS", 5.0)))
        self.vacuum_days = p.get("vacuum_days", 60)
        self.conflict_gap = p.get("conflict_gap", 0.45)
        self.tp_reach_atr = p.get("tp_reach_atr", 3.0)
        self.frvp_tfs = p.get("frvp_tfs", ZCE_FRVP_TFS)
        self.swing_length = p.get("swing_length", ZCE_SWING_LENGTH)
        self.max_imm_atr = p.get("max_imm_atr", float(getattr(config, "ZCE_MAX_IMM_ATR", 4.0)))
        self.max_cluster_width_atr = p.get("max_cluster_width_atr", float(getattr(config, "ZCE_MAX_CLUSTER_WIDTH_ATR", 1.0)))
        self.max_prim_width_atr = p.get("max_prim_width_atr", float(getattr(config, "ZCE_MAX_PRIM_WIDTH_ATR", 0.15)))

    def _get_kind_weight(self, kind: str) -> float:
        if kind in self.w_kind:
            return self.w_kind[kind]
        base_kind = kind.split("_")[0]
        return self.w_kind.get(base_kind, 0.5)

    # ------------------------------------------------------------------ #
    # 1. Koleksi primitif per sel (tf, horizon)
    # ------------------------------------------------------------------ #
    def _collect_primitives(
        self, tf: str, df: pd.DataFrame, point_size: float
    ) -> List[ZonePrimitive]:
        out: List[ZonePrimitive] = []
        if df is None or len(df) < 30:
            return out
        swing = self.swing_length.get(tf, 5)
        horizons = [h for h in self.grid.get(tf, []) if h <= len(df)]

        # Kalkulasi ATR timeframe lokal untuk ketebalan realistis wick-to-body
        tr = np.maximum(
            df["high"].to_numpy(dtype=float)[1:] - df["low"].to_numpy(dtype=float)[1:],
            np.maximum(
                np.abs(df["high"].to_numpy(dtype=float)[1:] - df["close"].to_numpy(dtype=float)[:-1]),
                np.abs(df["low"].to_numpy(dtype=float)[1:] - df["close"].to_numpy(dtype=float)[:-1])
            )
        )
        atr_tf = float(np.mean(tr[-20:])) if len(tr) >= 20 else (float(np.mean(tr)) if len(tr) > 0 else 10.0 * point_size)

        for h in horizons:
            w = df.iloc[-h:]
            try:
                sig = LuxSMCAnalyzer(
                    swing_length=min(swing, max(2, h // 25)),
                    compute_frvp=False,
                ).analyze(w, point_size=point_size)
            except Exception:
                continue
            idx0 = len(df) - h  # offset global bar
            # Order blocks (bullish = demand/support, bearish = supply/resistance)
            for ob in getattr(sig, "order_blocks_bullish", []) or []:
                out.append(ZonePrimitive("OB_BULL", tf, h, float(ob["top"]), float(ob["bottom"]),
                                         index_age=int(ob.get("index", 0)) + idx0))
            for ob in getattr(sig, "order_blocks_bearish", []) or []:
                out.append(ZonePrimitive("OB_BEAR", tf, h, float(ob["top"]), float(ob["bottom"]),
                                         index_age=int(ob.get("index", 0)) + idx0))
            # FVG
            for fv in getattr(sig, "fvg_bullish", []) or []:
                out.append(ZonePrimitive("FVG_BULL", tf, h, float(fv["top"]), float(fv["bottom"]),
                                         index_age=int(fv.get("index", 0)) + idx0))
            for fv in getattr(sig, "fvg_bearish", []) or []:
                out.append(ZonePrimitive("FVG_BEAR", tf, h, float(fv["top"]), float(fv["bottom"]),
                                         index_age=int(fv.get("index", 0)) + idx0))

            # EQH / EQL Liquidity Pools sebagai Zonal Bands
            for e in getattr(sig, "equal_highs", []) or []:
                indices = e.get("indices", [])
                if len(indices) == 2 and 0 <= indices[0] < len(w) and 0 <= indices[1] < len(w):
                    h1 = float(w.iloc[indices[0]]["high"])
                    h2 = float(w.iloc[indices[1]]["high"])
                    top = max(h1, h2)
                    bot = min(h1, h2) - 0.05 * atr_tf
                    out.append(ZonePrimitive("EQH", tf, h, top, bot, index_age=0))
                else:
                    p = float(e["price"])
                    out.append(ZonePrimitive("EQH", tf, h, p + 0.05 * atr_tf, p - 0.05 * atr_tf, index_age=0))

            for e in getattr(sig, "equal_lows", []) or []:
                indices = e.get("indices", [])
                if len(indices) == 2 and 0 <= indices[0] < len(w) and 0 <= indices[1] < len(w):
                    l1 = float(w.iloc[indices[0]]["low"])
                    l2 = float(w.iloc[indices[1]]["low"])
                    bot = min(l1, l2)
                    top = max(l1, l2) + 0.05 * atr_tf
                    out.append(ZonePrimitive("EQL", tf, h, top, bot, index_age=0))
                else:
                    p = float(e["price"])
                    out.append(ZonePrimitive("EQL", tf, h, p + 0.05 * atr_tf, p - 0.05 * atr_tf, index_age=0))

            # Last swing extreme per horizon (Last High / Last Low) sebagai Wick-to-Body Bands
            try:
                i_max = int(w["high"].argmax())
                bar_max = w.iloc[i_max]
                h_max = float(bar_max["high"])
                h_body = max(float(bar_max["open"]), float(bar_max["close"]))
                thick_h = max(0.05 * atr_tf, min(0.35 * atr_tf, h_max - h_body))
                out.append(ZonePrimitive("LAST_HIGH", tf, h, h_max, h_max - thick_h))

                i_min = int(w["low"].argmin())
                bar_min = w.iloc[i_min]
                l_min = float(bar_min["low"])
                l_body = min(float(bar_min["open"]), float(bar_min["close"]))
                thick_l = max(0.05 * atr_tf, min(0.35 * atr_tf, l_body - l_min))
                out.append(ZonePrimitive("LAST_LOW", tf, h, l_min + thick_l, l_min))
            except Exception:
                pass

            # FRVP (tf <= H4)
            if tf in self.frvp_tfs and "tick_volume" in w.columns and w["tick_volume"].sum() > 0:
                try:
                    vol = w["tick_volume"].to_numpy(dtype=float)
                    frvp = compute_fixed_range_volume_profile(
                        w["high"].to_numpy(dtype=float),
                        w["low"].to_numpy(dtype=float),
                        w["close"].to_numpy(dtype=float),
                        vol,
                        start=0, end=len(w) - 1, bins=60,
                    )
                    if frvp is not None:
                        vah = getattr(frvp, "value_area_high", None)
                        val = getattr(frvp, "value_area_low", None)
                        poc = getattr(frvp, "poc", None)
                        if vah is not None:
                            out.append(ZonePrimitive("FRVP_VAH", tf, h, float(vah), float(vah) - 0.05 * atr_tf))
                        if val is not None:
                            out.append(ZonePrimitive("FRVP_VAL", tf, h, float(val) + 0.05 * atr_tf, float(val)))
                        if poc is not None:
                            out.append(ZonePrimitive("FRVP_POC", tf, h, float(poc) + 0.025 * atr_tf, float(poc) - 0.025 * atr_tf))
                        for n in (getattr(frvp, "hvn_nodes", None) or [])[:3]:
                            out.append(ZonePrimitive("FRVP_POC", tf, h, float(n) + 0.025 * atr_tf, float(n) - 0.025 * atr_tf))
                except Exception:
                    pass

        # Dynamic EMA Bands (20, 50, 100, 200) untuk H1, H4, D1
        if tf in ("H1", "H4", "D1"):
            for span in (20, 50, 100, 200):
                if len(df) >= span:
                    try:
                        ema_val = float(df["close"].ewm(span=span, adjust=False).mean().iloc[-1])
                        half_thick = 0.03 * atr_tf
                        out.append(ZonePrimitive(
                            kind="EMA_BAND",
                            tf=tf,
                            horizon=span,
                            top=ema_val + half_thick,
                            bottom=ema_val - half_thick,
                            index_age=0
                        ))
                    except Exception:
                        pass

        # Macro Dynamic Envelope Bands (H4)
        if tf == "H4" and len(df) >= 25:
            try:
                from src.analytics.pattern_engine import MacroEnvelopeEngine
                pip_val = 10.0 * point_size if point_size < 0.01 else point_size
                env_res = MacroEnvelopeEngine().analyze(df, symbol="", point_size=point_size, pip_size=pip_val)
                if env_res.envelope_upper > 0:
                    half_thick = 0.04 * atr_tf
                    out.append(ZonePrimitive(
                        kind="ENVELOPE_CEIL",
                        tf="H4",
                        horizon=100,
                        top=env_res.envelope_upper + half_thick,
                        bottom=env_res.envelope_upper - half_thick,
                        index_age=0
                    ))
                if env_res.envelope_lower > 0:
                    half_thick = 0.04 * atr_tf
                    out.append(ZonePrimitive(
                        kind="ENVELOPE_FLOOR",
                        tf="H4",
                        horizon=100,
                        top=env_res.envelope_lower + half_thick,
                        bottom=env_res.envelope_lower - half_thick,
                        index_age=0
                    ))
            except Exception:
                pass

        # Clamp lebar primitif (anti-jembatan): OB/FVG raksasa dipotong simetris terhadap mid
        # agar tidak menjembatani dua node struktural yang sebenarnya berjauhan.
        max_w = float(getattr(self, "max_prim_width_atr", 0.15)) * atr_tf
        if max_w > 0:
            half = max_w * 0.5
            for p in out:
                if (p.top - p.bottom) > max_w:
                    mid = (p.top + p.bottom) * 0.5
                    p.top = mid + half
                    p.bottom = mid - half
        return out

    # ------------------------------------------------------------------ #
    # 2. Merge spasial primitif -> klaster
    # ------------------------------------------------------------------ #
    def _merge_primitives(
        self, prims: List[ZonePrimitive], atr_h1: float, point_size: float
    ) -> List[ZoneCluster]:
        if not prims:
            return []
        pip_val = 10.0 * point_size if point_size < 0.01 else point_size
        tol_pip = min(8.0 * pip_val, 0.40 * atr_h1)
        tol = max(self.merge_atr_mult * atr_h1, tol_pip)
        max_width = self.max_cluster_width_atr * atr_h1

        # urutkan dari bobot terbesar agar seed kuat
        def _w(p: ZonePrimitive) -> float:
            return self._get_kind_weight(p.kind) * self.w_tf.get(p.tf, 0.5)

        used = [False] * len(prims)
        clusters: List[ZoneCluster] = []
        order = sorted(range(len(prims)), key=lambda i: -_w(prims[i]))
        cid = 0
        for i in order:
            if used[i]:
                continue
            members = [prims[i]]
            used[i] = True
            b_lo, b_hi = prims[i].bottom, prims[i].top
            changed = True
            while changed:
                changed = False
                for j in range(len(prims)):
                    if used[j]:
                        continue
                    pr = prims[j]
                    cand_lo = min(b_lo, pr.bottom)
                    cand_hi = max(b_hi, pr.top)
                    # overlap / gap <= tol DAN candidate width <= max_width (Anti-Snowball Chaining)
                    if (pr.top >= b_lo - tol) and (pr.bottom <= b_hi + tol):
                        if (cand_hi - cand_lo) <= max(b_hi - b_lo, max(pr.top - pr.bottom, max_width)):
                            members.append(pr)
                            used[j] = True
                            b_lo, b_hi = cand_lo, cand_hi
                            changed = True

            clusters.append(self._finalize_cluster(cid, members, b_lo, b_hi, atr_h1, point_size))
            cid += 1
        return clusters

    # ------------------------------------------------------------------ #
    # 2b. P2: Edge-based NODE engine (pengganti snowball band-merge)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _prim_edge(p: ZonePrimitive) -> float:
        """Titik acuan struktural: ceiling -> bottom, floor -> top, netral -> mid."""
        if p.kind in CEIL_KINDS:
            return p.bottom
        if p.kind in FLOOR_KINDS:
            return p.top
        return (p.top + p.bottom) * 0.5

    def _build_nodes(
        self, prims: List[ZonePrimitive], atr_h1: float, point_size: float
    ) -> List[ZoneCluster]:
        """Bentuk NODE dari titik edge (bukan band), lalu skor via confluence lintas-sel.

        Kunci perbedaan dari `_merge_primitives`:
        - Pengelompokan memakai TITIK EDGE, sehingga primitif lebar tak bisa menjembatani.
        - Sweep berbasis ANCHOR (bukan single-linkage) -> tidak ada chaining/snowball.
        - Skor = confluence SEMUA primitif dalam `score_radius` dari anchor (lintas sel TF x horizon).
        """
        if not prims:
            return []
        pip_val = 10.0 * point_size if point_size < 0.01 else point_size
        pip_floor = 8.0 * pip_val
        node_tol = max(float(getattr(config, "ZCE_NODE_TOL_ATR", 0.35)) * atr_h1, pip_floor)
        score_radius = max(float(getattr(config, "ZCE_SCORE_RADIUS_ATR", 0.50)) * atr_h1, pip_floor)

        edges = sorted(((self._prim_edge(p), p) for p in prims), key=lambda x: x[0])

        # Sweep berbasis anchor: hindari chaining (tiap node hanya menerima edge
        # yang jaraknya <= node_tol dari edge pertama/anchor node itu).
        groups: List[tuple] = []
        i = 0
        n = len(edges)
        while i < n:
            anchor = edges[i][0]
            grp = [edges[i]]
            j = i + 1
            while j < n and (edges[j][0] - anchor) <= node_tol:
                grp.append(edges[j])
                j += 1
            groups.append((anchor, grp))
            i = j

        nodes: List[ZoneCluster] = []
        for cid, (anchor, grp) in enumerate(groups):
            members = [p for _, p in grp]

            # --- Skor confluence LINTAS-SEL: semua primitif (semua TF x horizon) dalam radius ---
            pairs: Dict[tuple, float] = {}
            ceil_w = 0.0
            floor_w = 0.0
            hmax = 0
            for p in prims:
                if abs(self._prim_edge(p) - anchor) <= score_radius:
                    k = (p.kind, p.tf)
                    if k not in pairs:
                        w = self._get_kind_weight(p.kind) * self.w_tf.get(p.tf, 0.5)
                        pairs[k] = w
                        if p.kind in CEIL_KINDS:
                            ceil_w += w
                        elif p.kind in FLOOR_KINDS:
                            floor_w += w
                    hmax = max(hmax, p.horizon)

            score_raw = float(sum(pairs.values()))
            score_final = round(score_raw * _horizon_boost(hmax), 3)

            # --- Band node: mengikuti anchor (titik edge), di-clamp agar tetap sempit ---
            b_lo = min(anchor, min(p.bottom for p in members))
            b_hi = max(anchor, max(p.top for p in members))
            if (b_hi - b_lo) > (2.0 * node_tol):
                b_lo, b_hi = anchor - node_tol, anchor + node_tol

            role = "CEILING" if ceil_w >= floor_w else "FLOOR"
            kinds_present = sorted({p.kind for p in members})
            tfs_present = sorted({p.tf for p in members})
            tfmax = max(tfs_present, key=lambda t: self.w_tf.get(t, 0)) if tfs_present else "H1"
            c = ZoneCluster(
                cluster_id=cid,
                band_low=b_lo,
                band_high=b_hi,
                members=members,
                score_raw=score_raw,
                score_final=score_final,
                horizon_max=hmax,
                tfs_present=tfs_present,
                kinds_present=kinds_present,
                width_atr=round((b_hi - b_lo) / max(atr_h1, 1e-9), 3),
                inherent_role=role,
                confluence=len(pairs),
            )
            c.fortress_tag = f"{'C_' if role == 'CEILING' else 'F_'}{'+'.join(kinds_present)}@{tfmax}"
            # Special G3 Protocol: evaluasi seluruh primitif yang berkontribusi ke skor node
            active_prims = members + [p for p in prims if abs(self._prim_edge(p) - anchor) <= score_radius]
            c.grade = self._assign_cluster_grade(c, active_prims)
            nodes.append(c)
        return nodes

    def _assign_cluster_grade(self, cluster: ZoneCluster, prims_list: List[ZonePrimitive]) -> str:
        """
        Special G3 Protocol (11 Sep 2026):
        - Syarat GRADE_3_MACRO: score_final >= self.grade_g3 (8.5) DAN wajib memiliki
          jangkar makro sejati:
            1. Primitive LAST_LOW / LAST_HIGH / SWING_LOW / SWING_HIGH / EQL / EQH / OB_BULL / OB_BEAR
               pada timeframe makro D1, W1, atau MN1.
            2. Primitive LAST_LOW / LAST_HIGH pada H4 dengan horizon deep (horizon >= 100).
            3. Primitive PSYCH_MAJOR (level bulat utama, e.g. 1.60000, 1.61000).
        - Jika score_final >= self.grade_g3 tapi TIDAK punya jangkar makro sejati,
          grade di-cap maksimal ke GRADE_2_INTERMEDIATE (mencegah inflasi skor dari tumpukan mikro).
        - GRADE_2_INTERMEDIATE: score_final >= self.grade_g2 (5.0).
        - Sisanya: GRADE_1_MICRO.
        """
        score = cluster.score_final
        if score >= self.grade_g3:
            has_macro_anchor = any(
                (
                    p.tf in ("D1", "W1", "MN1")
                    and p.kind in ("LAST_LOW", "LAST_HIGH", "SWING_LOW", "SWING_HIGH", "EQL", "EQH", "OB_BULL", "OB_BEAR")
                )
                or (
                    p.tf == "H4"
                    and p.kind in ("LAST_LOW", "LAST_HIGH")
                    and getattr(p, "horizon", 0) >= 100
                )
                or (p.kind == "PSYCH_MAJOR")
                for p in prims_list
            )
            if has_macro_anchor:
                return "GRADE_3_MACRO"
            return "GRADE_2_INTERMEDIATE"
        elif score >= self.grade_g2:
            return "GRADE_2_INTERMEDIATE"
        return "GRADE_1_MICRO"

    def _finalize_cluster(
        self, cid: int, members: List[ZonePrimitive], b_lo: float, b_hi: float,
        atr_h1: float, point_size: float,
    ) -> ZoneCluster:
        # J1: score_raw = penjumlahan atas pasangan (kind, tf) UNIK — horizon tidak jadi saksi.
        pairs = {}
        hmax = 0
        ceil_w = 0.0
        floor_w = 0.0
        for m in members:
            key = (m.kind, m.tf)
            w_val = self._get_kind_weight(m.kind) * self.w_tf.get(m.tf, 0.5)
            if key not in pairs:
                pairs[key] = w_val
            hmax = max(hmax, m.horizon)
            if m.kind in CEIL_KINDS:
                ceil_w += w_val
            elif m.kind in FLOOR_KINDS:
                floor_w += w_val

        score_raw = float(sum(pairs.values()))
        boost = _horizon_boost(hmax)
        c = ZoneCluster(
            cluster_id=cid,
            band_low=b_lo,
            band_high=b_hi,
            members=members,
            score_raw=score_raw,
            score_final=round(score_raw * boost, 3),
            horizon_max=hmax,
            tfs_present=sorted({m.tf for m in members}),
            kinds_present=sorted({m.kind for m in members}),
            width_atr=round((b_hi - b_lo) / max(atr_h1, 1e-9), 3),
        )
        c.grade = self._assign_cluster_grade(c, members)
        tfmax = max((m.tf for m in members), key=lambda t: self.w_tf.get(t, 0))
        prefix = "C_" if ceil_w >= floor_w else "F_"
        c.fortress_tag = f"{prefix}{'+'.join(c.kinds_present)}@{tfmax}"
        c.inherent_role = "CEILING" if ceil_w >= floor_w else "FLOOR"
        c.confluence = len(pairs)
        return c

    # ------------------------------------------------------------------ #
    # 3. Freshness: sentuhan terakhir dari tape H1 & Analisis Kompresi
    # ------------------------------------------------------------------ #
    def _stamp_freshness(
        self, clusters: List[ZoneCluster], h1_df: pd.DataFrame, cur_price: float, atr_h1: float, digits: int = 5
    ) -> None:
        if h1_df is None or len(h1_df) < 2:
            return

        lookback_bars = int(getattr(config, "ZCE_TOUCH_LOOKBACK_BARS", 120))
        eval_df = h1_df.tail(lookback_bars).reset_index(drop=True)
        highs = eval_df["high"].to_numpy(dtype=float)
        lows = eval_df["low"].to_numpy(dtype=float)
        closes = eval_df["close"].to_numpy(dtype=float)
        times = eval_df["time"].to_numpy() if "time" in eval_df.columns else np.arange(len(eval_df))
        n_eval = len(eval_df)
        n_total = len(h1_df)

        bars_cold = max(1, int(self.cold_days * 24))
        bars_vac = max(1, int(self.vacuum_days * 24))

        touch_tol = 0.25 * atr_h1
        penetration_max = 0.45 * atr_h1

        all_low = h1_df["low"].to_numpy(dtype=float)
        all_high = h1_df["high"].to_numpy(dtype=float)

        for c in clusters:
            # Anchor level_price to the physical barrier edge that price interacts with:
            # If the cluster is below current price, it acts as a Floor -> barrier is c.band_high
            # If the cluster is above current price, it acts as a Ceiling -> barrier is c.band_low
            level_price = c.band_high if c.mid < cur_price else c.band_low

            touch_nodes: List[Dict[str, Any]] = []
            t_indices: List[int] = []
            state = "DEPARTED"
            min_dep_pips = 6.0 * (10 ** (-digits) * 10 if digits in (3, 5) else 10 ** (-digits))
            dep_dist = max(0.50 * atr_h1, min_dep_pips)

            for k in range(n_eval):
                h_k = highs[k]
                l_k = lows[k]
                c_k = closes[k]

                dist_high = abs(h_k - level_price)
                dist_low = abs(l_k - level_price)

                is_touch = False
                is_sweep = False
                is_breach = False
                touch_price = h_k
                is_high_closer = (dist_high <= dist_low)

                # Menentukan ujung candle yang paling dekat dengan level ZCE
                if is_high_closer:
                    # Ujung atas (high wick) paling dekat ke level ZCE (pengujian dari bawah atau tusukan ke atas)
                    touch_price = h_k
                    if (level_price - touch_tol <= h_k <= level_price + penetration_max) and (l_k <= level_price + 0.15 * atr_h1):
                        is_touch = True
                        if h_k >= level_price and c_k < level_price:
                            is_sweep = True
                        elif c_k >= level_price:
                            is_breach = True
                else:
                    # Ujung bawah (low wick) paling dekat ke level ZCE (pengujian dari atas atau tusukan ke bawah)
                    touch_price = l_k
                    if (level_price - penetration_max <= l_k <= level_price + touch_tol) and (h_k >= level_price - 0.15 * atr_h1):
                        is_touch = True
                        if l_k <= level_price and c_k > level_price:
                            is_sweep = True
                        elif c_k <= level_price:
                            is_breach = True

                if is_touch:
                    t_val = times[k]
                    t_int = int(t_val) if isinstance(t_val, (int, np.integer)) else (int(t_val.timestamp()) if hasattr(t_val, "timestamp") else k)

                    if state == "DEPARTED":
                        # Membuka siklus sentuhan baru dari gelombang ayunan yang terbukti independen
                        touch_nodes.append({
                            "touch_num": len(touch_nodes) + 1,
                            "bar_index": k,
                            "time": t_int,
                            "price": round(float(touch_price), digits),
                            "is_sweep_wick": is_sweep,
                            "is_breach": is_breach,
                            "level": round(float(level_price), digits),
                            "level_type": "ceiling" if is_high_closer else "floor",
                        })
                        t_indices.append(k)
                        state = "IN_TOUCH"
                    else:
                        # Masih dalam gelombang interaksi yang sama (sideways/multiple candle di level yang sama)
                        # DILARANG menambah nomor sentuhan: lebur dan update ke ekor yang paling ekstrem
                        if is_high_closer:
                            if touch_price > touch_nodes[-1]["price"]:
                                touch_nodes[-1]["price"] = round(float(touch_price), digits)
                                touch_nodes[-1]["bar_index"] = k
                                touch_nodes[-1]["time"] = t_int
                                touch_nodes[-1]["is_sweep_wick"] = is_sweep or touch_nodes[-1]["is_sweep_wick"]
                                touch_nodes[-1]["is_breach"] = is_breach or touch_nodes[-1]["is_breach"]
                                t_indices[-1] = k
                        else:
                            if touch_price < touch_nodes[-1]["price"]:
                                touch_nodes[-1]["price"] = round(float(touch_price), digits)
                                touch_nodes[-1]["bar_index"] = k
                                touch_nodes[-1]["time"] = t_int
                                touch_nodes[-1]["is_sweep_wick"] = is_sweep or touch_nodes[-1]["is_sweep_wick"]
                                touch_nodes[-1]["is_breach"] = is_breach or touch_nodes[-1]["is_breach"]
                                t_indices[-1] = k
                else:
                    # Lilin tidak menyentuh level: periksa apakah harga sudah benar-benar menjauh (Departure)
                    if is_high_closer:
                        if h_k <= level_price - dep_dist or l_k >= level_price + dep_dist:
                            state = "DEPARTED"
                    else:
                        if l_k >= level_price + dep_dist or h_k <= level_price - dep_dist:
                            state = "DEPARTED"

            c.touch_nodes = touch_nodes
            c.touch_count = len(touch_nodes)

            # Cold / vacuum backward compatibility check
            hits = np.where((all_low <= c.band_high) & (all_high >= c.band_low))[0]
            if len(hits):
                c.last_touch_h1_bars_ago = int(n_total - 1 - hits[-1])
            else:
                c.last_touch_h1_bars_ago = n_total
            c.is_cold = c.last_touch_h1_bars_ago > bars_cold
            c.is_vacuum = (
                c.is_cold
                and c.last_touch_h1_bars_ago > bars_vac
                and abs(c.mid - cur_price) > 1.0 * atr_h1
            )

            # Freshness State & Compression
            if c.touch_count == 0:
                c.freshness_state = "FRESH_VIRGIN"
                c.freshness_label = "0x FRESH (Virgin)"
                c.compression_type = "NONE"
            elif c.touch_count in (1, 2):
                c.freshness_state = "TESTED_VALID"
                c.freshness_label = f"{c.touch_count}x TESTED"
                c.compression_type = "NONE"
            else:
                is_level_above = (level_price >= cur_price)
                if is_level_above:
                    troughs = []
                    for idx_i in range(len(t_indices) - 1):
                        s_i = t_indices[idx_i]
                        e_i = t_indices[idx_i + 1]
                        if e_i > s_i + 1:
                            troughs.append(float(np.min(lows[s_i + 1:e_i])))
                    is_hl = False
                    if len(troughs) >= 2 and (troughs[-1] > troughs[0] + 0.08 * atr_h1):
                        is_hl = True
                    elif len(troughs) == 1 and (lows[t_indices[-1]] > troughs[0] + 0.08 * atr_h1):
                        is_hl = True

                    if is_hl:
                        c.freshness_state = "ABSORPTION_COIL"
                        c.freshness_label = f"{c.touch_count}x COIL [HL]"
                        c.compression_type = "HIGHER_LOWS"
                    else:
                        c.freshness_state = "EXHAUSTED"
                        c.freshness_label = f"{c.touch_count}x EXHAUSTED"
                        c.compression_type = "FLAT"
                else:
                    peaks = []
                    for idx_i in range(len(t_indices) - 1):
                        s_i = t_indices[idx_i]
                        e_i = t_indices[idx_i + 1]
                        if e_i > s_i + 1:
                            peaks.append(float(np.max(highs[s_i + 1:e_i])))
                    is_lh = False
                    if len(peaks) >= 2 and (peaks[-1] < peaks[0] - 0.08 * atr_h1):
                        is_lh = True
                    elif len(peaks) == 1 and (highs[t_indices[-1]] < peaks[0] - 0.08 * atr_h1):
                        is_lh = True

                    if is_lh:
                        c.freshness_state = "ABSORPTION_COIL"
                        c.freshness_label = f"{c.touch_count}x SQUEEZE [LH]"
                        c.compression_type = "LOWER_HIGHS"
                    else:
                        c.freshness_state = "EXHAUSTED"
                        c.freshness_label = f"{c.touch_count}x EXHAUSTED"
                        c.compression_type = "FLAT"

    # ------------------------------------------------------------------ #
    # 4. Elekt dinding F1..Fn / C1..Cm
    # ------------------------------------------------------------------ #
    def _elect_walls(
        self, clusters: List[ZoneCluster], cur_price: float, atr_h1: float, digits: int
    ) -> dict:
        # RFC 11 Phase-2 & Chamber Clearance Role-Aware Architecture (Strict Physical Partitioning):
        # Menjamin hukum invarian fisik mutlak: Floor < cur_price < Ceiling.
        # Level Plafon (C1) DILARANG melompat menjadi Floor hanya karena harga menusuk tipis (< probe_tol) di atasnya,
        # DAN DILARANG menjadi Plafon terbalik (C1 < cur_price).
        # Begitu pula Floor (F1) DILARANG melompat menjadi Ceiling saat ditusuk tipis (< probe_tol) ke bawah,
        # DAN DILARANG menjadi Floor terbalik (F1 > cur_price).
        probe_tol = float(getattr(config, "ZCE_CHAMBER_CLEARANCE_ATR_MULT", 0.30)) * atr_h1
        cur_p_rnd = round(cur_price, digits)
        floor_cands: List[tuple] = []  # (price, cluster)
        ceil_cands: List[tuple] = []   # (price, cluster)

        for c in clusters:
            role = getattr(c, "inherent_role", "")
            if not role:
                role = "CEILING" if c.fortress_tag.startswith("C_") else ("FLOOR" if c.fortress_tag.startswith("F_") else "NEUTRAL")

            b_high_rnd = round(c.band_high, digits)
            b_low_rnd = round(c.band_low, digits)

            # 1. Seluruh zona berada di bawah harga live (c.band_high < cur_price):
            # Secara fisik zona ini hanya bisa menjadi kandidat FLOOR (Support / RBS).
            if b_high_rnd < cur_p_rnd:
                if role == "CEILING":
                    # Ceiling hanya sah menjadi RBS Floor jika ditembus bersih (>= probe_tol)
                    if cur_price >= c.band_high + probe_tol:
                        floor_cands.append((c.band_high, c))
                    # Jika tembus tipis (< probe_tol), level sedang di-probe/sweep (belum sah RBS floor)
                    # Dan DILARANG masuk ceil_cands karena posisinya secara fisik sudah di bawah harga!
                else:
                    floor_cands.append((c.band_high, c))

            # 2. Seluruh zona berada di atas harga live (c.band_low > cur_price):
            # Secara fisik zona ini hanya bisa menjadi kandidat CEILING (Resistance / SBR).
            elif b_low_rnd > cur_p_rnd:
                if role == "FLOOR":
                    # Floor hanya sah menjadi SBR Ceiling jika ditembus bersih (>= probe_tol)
                    if cur_price <= c.band_low - probe_tol:
                        ceil_cands.append((c.band_low, c))
                    # Jika tembus tipis (< probe_tol), level sedang di-probe/sweep (belum sah SBR ceiling)
                    # Dan DILARANG masuk floor_cands karena posisinya secara fisik sudah di atas harga!
                else:
                    ceil_cands.append((c.band_low, c))

            # 3. Harga live berada di dalam rentang zona / tepat di batas (b_low <= cur_price <= b_high):
            else:
                if role == "CEILING":
                    # Menusuk di dalam resistance: batas atas (c.band_high) bertindak sebagai penahan di atas harga
                    if b_high_rnd > cur_p_rnd:
                        ceil_cands.append((c.band_high, c))
                elif role == "FLOOR":
                    # Menusuk di dalam support: batas bawah (c.band_low) bertindak sebagai penahan di bawah harga
                    if b_low_rnd < cur_p_rnd:
                        floor_cands.append((c.band_low, c))
                else:
                    if b_low_rnd < cur_p_rnd:
                        floor_cands.append((c.band_low, c))
                    if b_high_rnd > cur_p_rnd:
                        ceil_cands.append((c.band_high, c))

        floor_cands.sort(key=lambda k: -k[0])  # terdekat dari bawah dulu (harga terbesar)
        ceil_cands.sort(key=lambda k: k[0])    # terdekat dari atas dulu (harga terkecil)

        pip_val = 10.0 * 10 ** (-digits) if digits in (3, 5) else 10 ** (-digits)
        grade_rank = {"GRADE_3_MACRO": 3, "GRADE_2_INTERMEDIATE": 2, "GRADE_1_MICRO": 1}
        # Floor absolut kecil (8 pips) + adaptive ATR fraction (Reconciliation 10 Sep 2026)
        pip_floor = 8.0 * pip_val
        pip_sep = max(pip_floor, min(15.0 * pip_val, 0.75 * atr_h1))
        min_sep = max(0.35 * atr_h1, pip_sep)

        def _pick_layers(items: List[tuple], is_ceil: bool, limit: int = 4) -> List[dict]:
            if not items:
                return []
            chosen: List[tuple] = []
            for price, c in items:
                matched_idx = None
                for idx, (prev_p, prev_c) in enumerate(chosen):
                    if abs(price - prev_p) < min_sep:
                        matched_idx = idx
                        break

                if matched_idx is None:
                    if len(chosen) < limit:
                        chosen.append((price, c))
                else:
                    # Spatial conflict resolution: Macro Supremacy & score upgrade
                    prev_p, prev_c = chosen[matched_idx]
                    r_new = grade_rank.get(c.grade, 1)
                    r_prev = grade_rank.get(prev_c.grade, 1)
                    if r_new > r_prev or (r_new == r_prev and c.score_final > prev_c.score_final):
                        chosen[matched_idx] = (price, c)

            chosen.sort(key=lambda k: k[0] if is_ceil else -k[0])

            layers = []
            for price, c in chosen:
                # Gather unique human-readable source primitives
                sources_list = []
                for p in getattr(c, "members", []) or []:
                    src_str = f"{p.kind} ({p.tf})" if getattr(p, "tf", None) else str(p.kind)
                    if src_str not in sources_list:
                        sources_list.append(src_str)
                if not sources_list:
                    for k in getattr(c, "kinds_present", []) or []:
                        tf_lbl = c.tfs_present[0] if getattr(c, "tfs_present", None) else "H1"
                        sources_list.append(f"{k} ({tf_lbl})")

                layers.append({
                    "tier": "",
                    "index": len(layers) + 1,
                    "price": round(float(price), digits),
                    "band_low": round(float(c.band_low), digits),
                    "band_high": round(float(c.band_high), digits),
                    "tag": c.fortress_tag,
                    "density_score": round(c.score_final, 2),
                    "grade": c.grade,
                    "width_atr": c.width_atr,
                    "is_cold": c.is_cold,
                    "is_vacuum": c.is_vacuum,
                    "score_raw": c.score_raw,
                    "confluence": int(getattr(c, "confluence", len(sources_list))),
                    "tf_max": (max(c.tfs_present, key=lambda t: self.w_tf.get(t, 0.0)) if c.tfs_present else ""),
                    "horizon_max": int(c.horizon_max),
                    "tfs_present": list(getattr(c, "tfs_present", [])),
                    "kinds_present": list(getattr(c, "kinds_present", [])),
                    "sources": sources_list,
                    "touch_count": int(getattr(c, "touch_count", 0)),
                    "freshness_state": str(getattr(c, "freshness_state", "FRESH_VIRGIN")),
                    "freshness_label": str(getattr(c, "freshness_label", "0x FRESH (Virgin)")),
                    "compression_type": str(getattr(c, "compression_type", "NONE")),
                    "touch_nodes": list(getattr(c, "touch_nodes", [])),
                })
            return layers

        floor_layers = _pick_layers(floor_cands, is_ceil=False)
        ceil_layers = _pick_layers(ceil_cands, is_ceil=True)
        for i, l in enumerate(floor_layers):
            l["tier"] = f"F{i + 1}"
        for i, l in enumerate(ceil_layers):
            l["tier"] = f"C{i + 1}"

        # Pilih F1 & C1 dengan pemisahan chamber (min_chamber_height)
        min_ch = max(0.50 * atr_h1, pip_sep)
        # Aturan "harga di dalam zona" (P3 metadata): layer yang menempel harga ditandai at_price
        inside_band = max(float(getattr(config, "ZCE_NODE_PRICE_BAND_MULT", 0.5)) * min_sep, 0.0)
        for _l in floor_layers + ceil_layers:
            _l["at_price"] = bool(abs(_l["price"] - cur_price) < inside_band)

        # F1 dan C1 mutlak mengambil layer pertama terdekat (Strict Physical Ladder & Zero Blind-Spot)
        f1 = floor_layers[0]["price"] if floor_layers else None
        c1 = ceil_layers[0]["price"] if ceil_layers else None

        # Jika chamber terlalu sempit (< min_ch), cari layer berikutnya yang memberikan pemisahan sehat
        if f1 is not None and c1 is not None and (c1 - f1) < min_ch:
            found_expanded = False
            for c_cand in ceil_layers[1:]:
                if (c_cand["price"] - f1) >= min_ch:
                    c1 = c_cand["price"]
                    found_expanded = True
                    break
            if not found_expanded:
                for f_cand in floor_layers[1:]:
                    if (c1 - f_cand["price"]) >= min_ch:
                        f1 = f_cand["price"]
                        found_expanded = True
                        break
            # Jika tetap belum mencukupi min_ch, PERTAHANKAN f1 dan c1 terdekat asli (dilarang membutakan radar dengan f1=None)

        # ── Cap jarak immediate (ZCE_MAX_IMM_ATR: default 4.0x ATR_H1) ─────────────
        imm_cap = self.max_imm_atr * atr_h1
        if f1 is not None and (cur_price - f1) > imm_cap:
            f1 = None
        if c1 is not None and (c1 - cur_price) > imm_cap:
            c1 = None

        # Deep layer F2/C2 = layer berikutnya dalam tangga fisik (menjamin C1 != C2 dan F1 != F2)
        def _get_deep_station(layers: List[dict], immediate_ref: Optional[float], above: bool) -> Optional[float]:
            if not layers or immediate_ref is None:
                return None
            for l in layers:
                if above and l["price"] > immediate_ref:
                    return l["price"]
                elif not above and l["price"] < immediate_ref:
                    return l["price"]
            return None

        deep_f2 = _get_deep_station(floor_layers, f1, above=False)
        deep_c2 = _get_deep_station(ceil_layers, c1, above=True)

        def _get_layer_meta(layers: List[dict], price: Optional[float]):
            if price is None:
                return None, 0.0
            for l in layers:
                if abs(l["price"] - price) < 1e-6:
                    return l.get("grade"), float(l.get("density_score", 0.0))
            return None, 0.0

        f1_grade, f1_score = _get_layer_meta(floor_layers, f1)
        c1_grade, c1_score = _get_layer_meta(ceil_layers, c1)
        f2_grade, f2_score = _get_layer_meta(floor_layers, deep_f2)
        c2_grade, c2_score = _get_layer_meta(ceil_layers, deep_c2)

        def _get_layer_confluence(layers: List[dict], price: Optional[float]) -> int:
            if price is None:
                return 0
            for l in layers:
                if abs(l["price"] - price) < 1e-6:
                    return int(l.get("confluence", 0))
            return 0

        def _get_layer_freshness(layers: List[dict], price: Optional[float]):
            if price is None:
                return "FRESH_VIRGIN", "0x FRESH (Virgin)", 0, "NONE"
            for l in layers:
                if abs(l["price"] - price) < 1e-6:
                    return (
                        l.get("freshness_state", "FRESH_VIRGIN"),
                        l.get("freshness_label", "0x FRESH (Virgin)"),
                        int(l.get("touch_count", 0)),
                        l.get("compression_type", "NONE")
                    )
            return "FRESH_VIRGIN", "0x FRESH (Virgin)", 0, "NONE"

        f1_fresh_st, f1_fresh_lbl, f1_touch_cnt, f1_comp = _get_layer_freshness(floor_layers, f1)
        c1_fresh_st, c1_fresh_lbl, c1_touch_cnt, c1_comp = _get_layer_freshness(ceil_layers, c1)

        inside_tiers = [l["tier"] for l in (floor_layers + ceil_layers) if l.get("at_price")]

        return {
            "floors": floor_layers,
            "ceilings": ceil_layers,
            "imm_floor_f1": f1,
            "imm_ceiling_c1": c1,
            "deep_floor_f2": deep_f2,
            "deep_ceiling_c2": deep_c2,
            "imm_floor_f1_grade": f1_grade,
            "imm_floor_f1_score": f1_score,
            "imm_ceiling_c1_grade": c1_grade,
            "imm_ceiling_c1_score": c1_score,
            "deep_floor_f2_grade": f2_grade,
            "deep_floor_f2_score": f2_score,
            "deep_ceiling_c2_grade": c2_grade,
            "deep_ceiling_c2_score": c2_score,
            "imm_floor_f1_confluence": _get_layer_confluence(floor_layers, f1),
            "imm_ceiling_c1_confluence": _get_layer_confluence(ceil_layers, c1),
            "c1_freshness_state": c1_fresh_st,
            "c1_freshness_label": c1_fresh_lbl,
            "c1_touch_count": c1_touch_cnt,
            "c1_compression_type": c1_comp,
            "f1_freshness_state": f1_fresh_st,
            "f1_freshness_label": f1_fresh_lbl,
            "f1_touch_count": f1_touch_cnt,
            "f1_compression_type": f1_comp,
            "inside_zone": bool(inside_tiers),
            "inside_tiers": inside_tiers,
            "layer_count": len(floor_layers) + len(ceil_layers),
        }

    # ------------------------------------------------------------------ #
    # 5. Scale ladder & SCALE_CONFLICT (H1)
    # ------------------------------------------------------------------ #
    def _scale_ladder(self, h1_df: pd.DataFrame, cur_price: float) -> ScaleLadder:
        lad = ScaleLadder()
        n = len(h1_df)
        for h in ZCE_LADDER_H1:
            if n < h:
                continue
            w = h1_df.iloc[-h:]
            hi = float(w["high"].max())
            lo = float(w["low"].min())
            rng = max(hi - lo, 1e-12)
            lad.pos_by_horizon[h] = float(np.clip((cur_price - lo) / rng, 0.0, 1.0))
        detail: List[str] = []
        pos = lad.pos_by_horizon
        keys = sorted(pos)
        for a, b in zip(keys, keys[1:]):
            if b - a <= 0:
                continue
            if abs(pos[a] - pos[b]) >= self.conflict_gap:
                near, far = (pos[a], pos[b]) if a < b else (pos[b], pos[a])
                if near <= 0.20 and far >= 0.65:
                    flag = "LOCAL_DISCOUNT_MACRO_PREMIUM" if a < b else "LOCAL_PREMIUM_MACRO_DISCOUNT"
                    detail.append(f"{flag} (h{a}={pos[a]:.2f} vs h{b}={pos[b]:.2f})")
        if detail:
            lad.conflict_flag = "LOCAL_DISCOUNT_MACRO_PREMIUM" if any("DISCOUNT_MACRO" in d for d in detail) else "LOCAL_PREMIUM_MACRO_DISCOUNT"
        lad.conflict_detail = detail
        return lad

    # ------------------------------------------------------------------ #
    # 6. Suggested method & readiness
    # ------------------------------------------------------------------ #
    def _suggest_method(
        self, walls: dict, ladder: ScaleLadder, h1_df: pd.DataFrame,
        cur_price: float, atr_h1: float,
    ) -> tuple:
        f1 = walls.get("imm_floor_f1")
        c1 = walls.get("imm_ceiling_c1")
        pos = ladder.pos_by_horizon
        pos100 = pos.get(100, 0.5)
        danger = bool(ladder.conflict_flag and ladder.conflict_flag != "NONE")
        if danger:
            return "NONE", f"conflict skala makro vs lokal belum ter-resolve ({ladder.conflict_flag})"
        if f1 is None or c1 is None:
            return "NONE", "dinding F1/C1 tidak ter-elekt"
        tail = h1_df.tail(24) if h1_df is not None else None
        if tail is not None:
            swept_f1 = bool((tail["low"] <= f1 + 0.15 * atr_h1).any()) and cur_price > f1
            swept_c1 = bool((tail["high"] >= c1 - 0.15 * atr_h1).any()) and cur_price < c1
        else:
            swept_f1 = swept_c1 = False
        if pos100 <= 0.15 and swept_f1:
            return "M1", "Universal Sweep: sweep F1 + reclaim di ekstrem discount"
        if pos100 >= 0.85 and swept_c1:
            return "M1", "Universal Sweep: sweep C1 + reclaim di ekstrem premium"
        mid = (f1 + c1) * 0.5
        if cur_price <= mid:
            return "M2", "reload zone antara F1 dan equilibrium"
        if pos100 >= 0.85:
            return "M3", "tekanan menembus C1 menuju klaster berikutnya"
        return "NONE", "belum ada kondisi trigger mekanisme"

    def _readiness(self, method: str, ladder: ScaleLadder, walls: dict,
                   permission: str, news_ok: bool = True) -> float:
        p_perm = {"GO": 1.0, "ARM": 0.7, "WAIT": 0.25}.get(permission, 0.0) if permission != "LOCK" else 0.0
        grade_best = 0.0
        for lyr in walls.get("floors", [])[:1] + walls.get("ceilings", [])[:1]:
            if lyr["grade"] == "GRADE_3_MACRO":
                grade_best = max(grade_best, 1.0)
            elif lyr["grade"] == "GRADE_2_INTERMEDIATE":
                grade_best = max(grade_best, 0.7)
            else:
                grade_best = max(grade_best, 0.4)
        p_scale = 0.5 if ladder.conflict_flag != "NONE" else 1.0
        p_news = 0.0 if not news_ok else 1.0
        p_pos = 0.5
        return round(100.0 * (0.30 * p_perm + 0.25 * grade_best + 0.20 * p_pos + 0.15 * p_scale + 0.10 * p_news), 1)

    # ------------------------------------------------------------------ #
    # 7. API utama
    # ------------------------------------------------------------------ #
    def compute_zone_map(
        self,
        symbol: str,
        dfs: Dict[str, pd.DataFrame],
        point_size: float = 0.00001,
        digits: int = 5,
        atr_h1: Optional[float] = None,
        cur_price: Optional[float] = None,
        permission: str = "ARM",
        news_ok: bool = True,
        ts: Optional[float] = None,
    ) -> ZoneMapResult:
        import time as _t
        ts = ts if ts is not None else _t.time()
        h1 = dfs.get("H1")
        if h1 is None or len(h1) < 60:
            raise ValueError(f"ZCE: butuh df H1 >= 60 bar untuk {symbol}")
        cur_price = float(cur_price if cur_price is not None else h1["close"].iloc[-1])
        atr_h1 = atr_h1 if atr_h1 else atr_from_df(h1)

        prims: List[ZonePrimitive] = []
        for tf, df in dfs.items():
            if df is None or len(df) < 30:
                continue
            prims.extend(self._collect_primitives(tf, df, point_size))
        # Psych stations (level, TF-independent) — sekali per simbol
        try:
            st = calculate_dual_grid_stations(symbol, cur_price)
            for k, kind in (("macro_floor", "PSYCH_MAJOR"), ("macro_ceiling", "PSYCH_MAJOR"),
                            ("sub_floor_50", "PSYCH_SUB"), ("sub_ceiling_50", "PSYCH_SUB")):
                v = st.get(k)
                if v is not None:
                    prims.append(ZonePrimitive(kind, "PSY", 0, float(v), float(v)))
        except Exception:
            pass

        # P2: pilih mesin pembentuk zona — node berbasis edge (baru) atau band-merge (lama).
        if bool(getattr(config, "ZCE_NODE_ENGINE_ENABLED", True)):
            clusters = self._build_nodes(prims, atr_h1, point_size)
        else:
            clusters = self._merge_primitives(prims, atr_h1, point_size)
        self._stamp_freshness(clusters, h1, cur_price, atr_h1, digits=digits)
        clusters.sort(key=lambda c: -c.score_final)

        walls = self._elect_walls(clusters, cur_price, atr_h1, digits)
        ladder = self._scale_ladder(h1, cur_price)
        method, reason = self._suggest_method(walls, ladder, h1, cur_price, atr_h1)
        readiness = self._readiness(method, ladder, walls, permission, news_ok)

        res = ZoneMapResult(
            symbol=symbol,
            ts=ts,
            clusters=clusters[:40],
            floors=walls["floors"],
            ceilings=walls["ceilings"],
            immediate_floor_f1=walls["imm_floor_f1"],
            immediate_ceiling_c1=walls["imm_ceiling_c1"],
            deep_floor_f2=walls["deep_floor_f2"],
            deep_ceiling_c2=walls["deep_ceiling_c2"],
            immediate_floor_f1_grade=walls.get("imm_floor_f1_grade"),
            immediate_ceiling_c1_grade=walls.get("imm_ceiling_c1_grade"),
            immediate_floor_f1_score=walls.get("imm_floor_f1_score", 0.0),
            immediate_ceiling_c1_score=walls.get("imm_ceiling_c1_score", 0.0),
            deep_floor_f2_grade=walls.get("deep_floor_f2_grade"),
            deep_ceiling_c2_grade=walls.get("deep_ceiling_c2_grade"),
            deep_floor_f2_score=walls.get("deep_floor_f2_score", 0.0),
            deep_ceiling_c2_score=walls.get("deep_ceiling_c2_score", 0.0),
            immediate_floor_f1_confluence=walls.get("imm_floor_f1_confluence", 0),
            immediate_ceiling_c1_confluence=walls.get("imm_ceiling_c1_confluence", 0),
            c1_freshness_state=walls.get("c1_freshness_state", "FRESH_VIRGIN"),
            c1_freshness_label=walls.get("c1_freshness_label", "0x FRESH (Virgin)"),
            c1_touch_count=walls.get("c1_touch_count", 0),
            c1_compression_type=walls.get("c1_compression_type", "NONE"),
            f1_freshness_state=walls.get("f1_freshness_state", "FRESH_VIRGIN"),
            f1_freshness_label=walls.get("f1_freshness_label", "0x FRESH (Virgin)"),
            f1_touch_count=walls.get("f1_touch_count", 0),
            f1_compression_type=walls.get("f1_compression_type", "NONE"),
            inside_zone=bool(walls.get("inside_zone", False)),
            inside_tiers=walls.get("inside_tiers", []) or [],
            layer_count=int(walls.get("layer_count", 0)),
            ladder=ladder,
            suggested_method=method,
            method_reason=reason,
            readiness_score=readiness,
            atr_h1=round(atr_h1, digits),
            cur_price=round(cur_price, digits),
        )
        res.wall_override = res.to_wall_override()
        return res

    # ------------------------------------------------------------------ #
    # 8. Zone table untuk payload LLM (RFC 13)
    # ------------------------------------------------------------------ #
    def build_zone_table_text(self, res: ZoneMapResult, limit: int = 15) -> str:
        lines = [
            f"ZONE MAP {res.symbol} @ {res.cur_price} | ATR_H1={res.atr_h1} | "
            f"method={res.suggested_method} | readiness={res.readiness_score}"
        ]
        lines.append(f"SCALE_LADDER(H1) { {h: round(p, 2) for h, p in res.ladder.pos_by_horizon.items()} } conflict={res.ladder.conflict_flag}")
        for lyr in res.ceilings[:4]:
            lines.append(f"  CEIL {lyr['tier']} {lyr['price']} [{lyr['tag']}] score={lyr['density_score']} "
                         f"grade={lyr['grade']} w_atr={lyr['width_atr']} vac={lyr['is_vacuum']}")
        for lyr in res.floors[:4]:
            lines.append(f"  FLOOR {lyr['tier']} {lyr['price']} [{lyr['tag']}] score={lyr['density_score']} "
                         f"grade={lyr['grade']} w_atr={lyr['width_atr']} vac={lyr['is_vacuum']}")
        for c in res.clusters[:limit]:
            lines.append(f"  ZONE {c.band_low:.{5}f}-{c.band_high:.{5}f} {c.fortress_tag} "
                         f"score={c.score_final} hmax={c.horizon_max} cold={c.is_cold} vac={c.is_vacuum} hits={c.touch_count}")
        return "\n".join(lines)


def merge_primitives_public(
    prims: List[ZonePrimitive], atr_h1: float, point_size: float = 1e-5,
    merge_atr_mult: float = 0.25,
) -> List[ZoneCluster]:
    """Helper testable (tanpa instance) untuk merge spasial."""
    eng = ZoneConfluenceEngine(params={"merge_atr_mult": merge_atr_mult})
    return eng._merge_primitives(prims, atr_h1, point_size)
