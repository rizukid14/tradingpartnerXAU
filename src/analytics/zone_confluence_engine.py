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

from src.indicators.lux_smc import LuxSMCAnalyzer
from src.indicators.volume_profile import compute_fixed_range_volume_profile
from src.indicators.atlas_dna import calculate_dual_grid_stations

# ----------------------------------------------------------------------------- #
#  Konstanta grid & bobot (default RFC 11; override via params dict / config)
# ----------------------------------------------------------------------------- #
ZCE_GRID: Dict[str, List[int]] = {
    "M30": [50, 150],
    "H1": [50, 100, 150, 250],
    "H4": [50, 100, 150],
    "D1": [50, 100, 150, 250],
    "W1": [50, 100],
    "MN1": [50],
}
ZCE_LADDER_H1: List[int] = [50, 100, 150, 250, 500]
ZCE_FRVP_TFS = ("M30", "H1", "H4")          # FRVP hanya tf dengan tick_volume valid
ZCE_SWING_LENGTH = {"M30": 3, "H1": 5, "H4": 5, "D1": 3, "W1": 3, "MN1": 3}

ZCE_W_TF: Dict[str, float] = {"M30": 0.55, "H1": 1.00, "H4": 1.60, "D1": 2.20, "W1": 2.80, "MN1": 3.20}
ZCE_W_KIND: Dict[str, float] = {
    "EQH": 1.15, "EQL": 1.15, "MACRO_EXTREME": 1.20, "OB": 1.00,
    "FVG": 0.80, "FRVP_POC": 1.00, "FRVP_VAH": 0.85, "FRVP_VAL": 0.85,
    "LAST_HIGH": 0.60, "LAST_LOW": 0.60, "PSYCH_MAJOR": 0.80, "PSYCH_SUB": 0.50,
    "EMA_BAND": 0.45,
}
ZCE_HORIZON_BOOST: List[tuple] = [(100, 1.00), (150, 1.10), (250, 1.20), (10_000, 1.30)]


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
        self.w_kind = p.get("w_kind", ZCE_W_KIND)
        self.grade_g2 = p.get("grade_g2", 3.5)
        self.grade_g3 = p.get("grade_g3", 6.5)
        self.merge_atr_mult = p.get("merge_atr_mult", 0.25)
        self.cold_days = p.get("cold_days", 21)
        self.vacuum_days = p.get("vacuum_days", 60)
        self.conflict_gap = p.get("conflict_gap", 0.45)
        self.tp_reach_atr = p.get("tp_reach_atr", 3.0)
        self.frvp_tfs = p.get("frvp_tfs", ZCE_FRVP_TFS)
        self.swing_length = p.get("swing_length", ZCE_SWING_LENGTH)
        # Cap jarak dinding immediate (dalam satuan ATR_H1): jika zona terdekat
        # lebih jauh dari cap, ZCE menyerahkan sisi tsb ke MSE baseline (fallback).
        # Spesifikasi verifikasi INV-2 menuntut <= 2.0x ATR_H1 (bug "level kabur jauh").
        self.max_imm_atr = p.get("max_imm_atr", 2.0)

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
                out.append(ZonePrimitive("OB", tf, h, float(ob["top"]), float(ob["bottom"]),
                                         index_age=int(ob.get("index", 0)) + idx0))
            for ob in getattr(sig, "order_blocks_bearish", []) or []:
                out.append(ZonePrimitive("OB", tf, h, float(ob["top"]), float(ob["bottom"]),
                                         index_age=int(ob.get("index", 0)) + idx0))
            # FVG
            for fv in getattr(sig, "fvg_bullish", []) or []:
                out.append(ZonePrimitive("FVG", tf, h, float(fv["top"]), float(fv["bottom"]),
                                         index_age=int(fv.get("index", 0)) + idx0))
            for fv in getattr(sig, "fvg_bearish", []) or []:
                out.append(ZonePrimitive("FVG", tf, h, float(fv["top"]), float(fv["bottom"]),
                                         index_age=int(fv.get("index", 0)) + idx0))
            # EQH / EQL
            for e in getattr(sig, "equal_highs", []) or []:
                p = float(e["price"])
                out.append(ZonePrimitive("EQH", tf, h, p, p, index_age=0))
            for e in getattr(sig, "equal_lows", []) or []:
                p = float(e["price"])
                out.append(ZonePrimitive("EQL", tf, h, p, p, index_age=0))
            # Last swing extreme per horizon (Last High / Last Low)
            out.append(ZonePrimitive("LAST_HIGH", tf, h, float(w["high"].max()), float(w["high"].max())))
            out.append(ZonePrimitive("LAST_LOW", tf, h, float(w["low"].min()), float(w["low"].min())))
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
                            out.append(ZonePrimitive("FRVP_VAH", tf, h, float(vah), float(vah)))
                        if val is not None:
                            out.append(ZonePrimitive("FRVP_VAL", tf, h, float(val), float(val)))
                        if poc is not None:
                            out.append(ZonePrimitive("FRVP_POC", tf, h, float(poc), float(poc)))
                        for n in (getattr(frvp, "hvn_nodes", None) or [])[:3]:
                            out.append(ZonePrimitive("FRVP_POC", tf, h, float(n), float(n)))
                except Exception:
                    pass
        return out

    # ------------------------------------------------------------------ #
    # 2. Merge spasial primitif -> klaster
    # ------------------------------------------------------------------ #
    def _merge_primitives(
        self, prims: List[ZonePrimitive], atr_h1: float, point_size: float
    ) -> List[ZoneCluster]:
        if not prims:
            return []
        tol = max(self.merge_atr_mult * atr_h1, 6.0 * point_size)
        # urutkan dari bobot terbesar agar seed kuat
        def _w(p: ZonePrimitive) -> float:
            return self.w_kind.get(p.kind, 0.5) * self.w_tf.get(p.tf, 0.5)

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
                    # overlap / gap <= tol
                    if (pr.top >= b_lo - tol) and (pr.bottom <= b_hi + tol):
                        members.append(pr)
                        used[j] = True
                        b_lo = min(b_lo, pr.bottom)
                        b_hi = max(b_hi, pr.top)
                        changed = True
            if (b_hi - b_lo) > 3.5 * atr_h1 and len(members) > 1:
                # klaster terlalu lebar -> buang outlier terjauh iteratif sampai masuk amplop
                while (b_hi - b_lo) > 3.5 * atr_h1 and len(members) > 1:
                    mids = np.array([m.mid for m in members])
                    ctr = float(np.median(mids))
                    far = int(np.argmax(np.abs(mids - ctr)))
                    members.pop(far)
                    b_lo = min(m.bottom for m in members)
                    b_hi = max(m.top for m in members)
            clusters.append(self._finalize_cluster(cid, members, b_lo, b_hi, atr_h1, point_size))
            cid += 1
        return clusters

    def _finalize_cluster(
        self, cid: int, members: List[ZonePrimitive], b_lo: float, b_hi: float,
        atr_h1: float, point_size: float,
    ) -> ZoneCluster:
        # J1: score_raw = penjumlahan atas pasangan (kind, tf) UNIK — horizon tidak jadi saksi.
        pairs = {}
        hmax = 0
        for m in members:
            key = (m.kind, m.tf)
            if key not in pairs:
                pairs[key] = self.w_kind.get(m.kind, 0.5) * self.w_tf.get(m.tf, 0.5)
            hmax = max(hmax, m.horizon)
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
        if c.score_final >= self.grade_g3:
            c.grade = "GRADE_3_MACRO"
        elif c.score_final >= self.grade_g2:
            c.grade = "GRADE_2_INTERMEDIATE"
        else:
            c.grade = "GRADE_1_MICRO"
        tfmax = max((m.tf for m in members), key=lambda t: self.w_tf.get(t, 0))
        c.fortress_tag = f"{'+'.join(c.kinds_present)}@{tfmax}"
        return c

    # ------------------------------------------------------------------ #
    # 3. Freshness: sentuhan terakhir dari tape H1
    # ------------------------------------------------------------------ #
    def _stamp_freshness(
        self, clusters: List[ZoneCluster], h1_df: pd.DataFrame, cur_price: float, atr_h1: float
    ) -> None:
        if h1_df is None or len(h1_df) < 2:
            return
        low = h1_df["low"].to_numpy(dtype=float)
        high = h1_df["high"].to_numpy(dtype=float)
        n = len(h1_df)
        bars_cold = max(1, int(self.cold_days * 24))
        bars_vac = max(1, int(self.vacuum_days * 24))
        for c in clusters:
            c.touch_count = int(np.sum((low <= c.band_high) & (high >= c.band_low)))
            hits = np.where((low <= c.band_high) & (high >= c.band_low))[0]
            if len(hits):
                c.last_touch_h1_bars_ago = int(n - 1 - hits[-1])
            else:
                c.last_touch_h1_bars_ago = n
            c.is_cold = c.last_touch_h1_bars_ago > bars_cold
            c.is_vacuum = (
                c.is_cold
                and c.last_touch_h1_bars_ago > bars_vac
                and abs(c.mid - cur_price) > 1.0 * atr_h1
            )

    # ------------------------------------------------------------------ #
    # 4. Elekt dinding F1..Fn / C1..Cm
    # ------------------------------------------------------------------ #
    def _elect_walls(
        self, clusters: List[ZoneCluster], cur_price: float, atr_h1: float, digits: int
    ) -> dict:
        eps = 0.05 * atr_h1
        # Kandidat dinding dibangun dari DUA sumber:
        #  (a) zona murni di bawah/atas harga  -> sisi zona yang menghadap harga
        #      (band_high untuk floor, band_low untuk ceiling) — perilaku lama.
        #  (b) zona yang MERENTANGI harga (band_low <= harga <= band_high):
        #      TIDAK boleh dibuang (bug INV-2 lama: level "kabur jauh" 3-8x ATR).
        #      Zona tsb menyumbang DUA dinding: band_low sebagai floor-edge
        #      dan band_high sebagai ceiling-edge.
        floor_cands: List[tuple] = []  # (price, cluster)
        ceil_cands: List[tuple] = []   # (price, cluster)
        for c in clusters:
            if c.band_high < cur_price - eps:
                floor_cands.append((c.band_high, c))
            elif c.band_low < cur_price - eps:
                # zona merentangi harga: tepi bawah masih di bawah harga
                floor_cands.append((c.band_low, c))
            if c.band_low > cur_price + eps:
                ceil_cands.append((c.band_low, c))
            elif c.band_high > cur_price + eps:
                # zona merentangi harga: tepi atas masih di atas harga
                ceil_cands.append((c.band_high, c))
        floor_cands.sort(key=lambda k: -k[0])  # terdekat dari bawah dulu (harga terbesar)
        ceil_cands.sort(key=lambda k: k[0])    # terdekat dari atas dulu (harga terkecil)

        def _pick_layers(items: List[tuple], limit: int = 6) -> List[dict]:
            layers = []
            for price, c in items:
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
                })
                if len(layers) >= limit:
                    break
            return layers

        floor_layers = _pick_layers(floor_cands)
        ceil_layers = _pick_layers(ceil_cands)
        for i, l in enumerate(floor_layers):
            l["tier"] = f"F{i + 1}"
        for i, l in enumerate(ceil_layers):
            l["tier"] = f"C{i + 1}"

        # Pilih F1 & C1 dengan pemisahan chamber (min_chamber_height)
        # 8 pips dalam satuan harga: 5-digit -> 0.0008 ; JPY 3-digit -> 0.08
        min_ch = max(0.60 * atr_h1, 8.0 * 10 ** (-digits + 1))
        f1 = floor_layers[0]["price"] if floor_layers else None
        c1 = ceil_layers[0]["price"] if ceil_layers else None
        if f1 is not None and c1 is not None and (c1 - f1) < min_ch:
            # dinding terlalu dekat: buang yang jaraknya ke harga lebih besar
            if (cur_price - f1) <= (c1 - cur_price):
                c1 = ceil_layers[1]["price"] if len(ceil_layers) > 1 else None
            else:
                f1 = floor_layers[1]["price"] if len(floor_layers) > 1 else None
        if f1 is not None and c1 is not None and (c1 - f1) < min_ch:
            f1 = None  # chamber tidak valid -> serahkan ke MSE fallback

        # ── Cap jarak immediate (INV-2 spec: <= 2.0x ATR_H1) ─────────────
        # Zona terdekat yang masih > cap = pasar kosong di sisi itu (atau zona
        # makro G3 yang memang jauh). Dinding > cap TIDAK layak dipakai sebagai
        # immediate F1/C1 untuk SL/TP intraday -> sisi tsb di-None-kan sehingga
        # guard pemakaian (F1 & C1 keduanya non-None) otomatis menyerahkan
        # seluruh override ke MSE baseline yang selalu punya FALLBACK_PSYCH dekat.
        imm_cap = self.max_imm_atr * atr_h1
        if f1 is not None and (cur_price - f1) > imm_cap:
            f1 = None
        if c1 is not None and (c1 - cur_price) > imm_cap:
            c1 = None

        # Deep layer F2/C2 = layer pertama dengan jarak >= 0.5x ATR_H1 dari
        # F1/C1 (INV-3 spec) — bukan sekadar index [1] yang bisa nempel terlalu
        # dekat ke immediate (kasus GBPCHF F1 EQH M30 3.0p & C1 FVG H1 6.1p).
        def _first_deep(layers: List[dict], ref: Optional[float], above: bool) -> Optional[float]:
            if ref is None:
                return None
            min_gap = 0.5 * atr_h1
            for l in layers[1:]:
                gap = (l["price"] - ref) if above else (ref - l["price"])
                if gap >= min_gap:
                    return l["price"]
            return None

        deep_f2 = _first_deep(floor_layers, f1, above=False)
        deep_c2 = _first_deep(ceil_layers, c1, above=True)

        return {
            "floors": floor_layers,
            "ceilings": ceil_layers,
            "imm_floor_f1": f1,
            "imm_ceiling_c1": c1,
            "deep_floor_f2": deep_f2,
            "deep_ceiling_c2": deep_c2,
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
        danger = "SCALE_CONFLICT" in (ladder.conflict_flag or "")
        if danger:
            return "NONE", "conflict skala makro vs lokal belum ter-resolve"
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

        clusters = self._merge_primitives(prims, atr_h1, point_size)
        self._stamp_freshness(clusters, h1, cur_price, atr_h1)
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
