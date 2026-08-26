"""
LuxAlgo Smart Money Concepts (SMC) - Signal Engine.

Pure-Python, self-contained module. Tidak bergantung ke modul lain di project.
Di pakai untuk menghasilkan sinyal struktural harga ke LLM prompt / risk engine.

Fitur:
  - Bullish / Bearish Structure (Higher High, Lower Low, dsb.)
  - Order Blocks (bullish & bearish)
  - Equal Highs / Equal Lows (liquidity pools)
  - Premium & Discount Zones (session range)
  - Break of Structure (BOS)
  - Change of Character (CHoCH)
  - Strong High / Low (swing dikonfirmasi volume)

Input  : pandas.DataFrame dengan kolom time|open|high|low|close [,tick_volume]
Output : SMCSignal (dataclass) — semua field berisi list of dict atau float.

Author : @commandcode
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple

import pandas as pd
import numpy as np


# ------------------------------------------------------------------ #
#  Data container                                                     #
# ------------------------------------------------------------------ #
@dataclass
class SMCStructure:
    price: float
    index: int
    direction: str  # "higher_high" | "lower_high" | "higher_low" | "lower_low"
    time: Optional[Any] = None


@dataclass
class SMCOrderBlock:
    top: float
    bottom: float
    close_price: float        # harga tutup candle OB
    index: int
    direction: str           # "bullish" | "bearish"
    time: Optional[Any] = None


@dataclass
class SMCLevelCluster:
    price: float
    indices: List[int]
    time: Optional[Any] = None


@dataclass
class SMBOS:
    direction: str           # "bullish" | "bearish" | "none"
    level: float
    index: Optional[int] = None


@dataclass
class SMCStrongLevel:
    price: float
    index: int              # lokasi candle swing
    is_high: bool
    strength: float         # tick_volume relatif (0..1)


@dataclass
class SMCSignal:
    bullish_structures:    List[Dict[str, Any]] = field(default_factory=list)
    bearish_structures:    List[Dict[str, Any]] = field(default_factory=list)
    order_blocks_bullish:  List[Dict[str, Any]] = field(default_factory=list)
    order_blocks_bearish:  List[Dict[str, Any]] = field(default_factory=list)
    equal_highs:           List[Dict[str, Any]] = field(default_factory=list)
    equal_lows:            List[Dict[str, Any]] = field(default_factory=list)
    premium_zone:          float  = 0.0   # session upper-mid
    discount_zone:         float  = 0.0   # session lower-mid
    bos:                   Dict[str, Any] = field(default_factory=lambda: {"direction": "none", "level": 0.0, "index": None})
    choch:                 Dict[str, Any] = field(default_factory=lambda: {"direction": "none", "level": 0.0, "index": None})
    strong_high:           float  = 0.0
    strong_low:            float  = 0.0


# ------------------------------------------------------------------ #
#  Helper internal                                                    #
# ------------------------------------------------------------------ #
def _swing_points(series: pd.Series, left: int = 3, right: int = 3) -> np.ndarray:
    """Kembalikan array boolean: True bila candle ke-i swing high/low."""
    n = len(series)
    highs = np.zeros(n, dtype=bool)
    lows  = np.zeros(n, dtype=bool)
    for i in range(left, n - right):
        window = series[i - left: i + right + 1]
        mid = series[i]
        idx = series.index[i]
        if mid == window.max() and (window == mid).sum() == 1:
            highs[i] = True
        if mid == window.min() and (window == mid).sum() == 1:
            lows[i] = True
    return highs, lows


# ------------------------------------------------------------------ #
#  Main analyzer                                                     #
# ------------------------------------------------------------------ #
class LuxSMCAnalyzer:
    """
    Parameters
    ----------
    tol_pips : float
        Toleransi pip agar dua harga dianggap *equal* (default 3 pip).
    ob_lookback : int
        Berapa candle ke-belakang untuk mencari order block (default 20).
    eq_cluster : int
        Berapa banyak swing points berhimpitan minimum agar jadi equal high/low.
    swing_left / swing_right : int
        Lebar jendela swing detection (left bars, right bars).
    """

    def __init__(
        self,
        tol_pips: float = 3,
        ob_lookback: int = 20,
        eq_cluster: int = 3,
        swing_left: int = 3,
        swing_right: int = 3,
    ):
        self.tol_pips   = tol_pips
        self.ob_lookback = ob_lookback
        self.eq_cluster  = eq_cluster
        self.swing_left  = swing_left
        self.swing_right = swing_right

    # -------------------------------------------------------------- #
    def analyze(self, df: pd.DataFrame, point_size: float = 0.0001) -> SMCSignal:
        """
        df  : DataFrame OHLC dengan kolom [time, open, high, low, close, tick_volume?]
              Index bebas — fungsi ini memakai `.reset_index(drop=True)` internal.
        point_size : pip-per-point (FX major = 0.0001, JPY = 0.01, XAU = 0.1, dst).
        """
        df = df.copy().reset_index(drop=True)
        n = len(df)
        sig = SMCSignal()

        if n < 10:
            return sig

        highs   = df["high"].to_numpy()
        lows    = df["low"].to_numpy()
        closes  = df["close"].to_numpy()
        opens   = df["open"].to_numpy()
        vols    = df["tick_volume"].to_numpy() if "tick_volume" in df.columns else np.ones(n)

        # Tolerance dalam harga (bukan pip)
        tol_price = self.tol_pips * point_size

        # ---------------------------------------------------------- #
        # 1. Swing points
        # ---------------------------------------------------------- #
        is_high, is_low = _swing_points(df["high"], self.swing_left, self.swing_right)
        is_low2, _      = _swing_points(df["low"],  self.swing_left, self.swing_right)
        swing_idx_high = np.where(is_high)[0]
        swing_idx_low  = np.where(is_low)[0]

        # ---------------------------------------------------------- #
        # 2. Structures (HH, LH bullish / HL, LL bearish) — versi
        #    sederhana: bandingkan tiap swing berturut-turut.
        # ---------------------------------------------------------- #
        def _build_structures(idx_arr: np.ndarray, vals: np.ndarray, is_highs: bool):
            structs = []
            if len(idx_arr) < 3:
                return structs
            for i in range(1, len(idx_arr) - 1):
                prev_v, cur_v, next_v = vals[idx_arr[i-1]], vals[idx_arr[i]], vals[idx_arr[i+1]]
                if is_highs:
                    if cur_v > prev_v and cur_v > next_v:
                        d = "higher_high"
                    elif cur_v < prev_v and cur_v < next_v:
                        d = "lower_high"
                    else:
                        continue
                else:
                    if cur_v > prev_v and cur_v > next_v:
                        d = "higher_low"
                    elif cur_v < prev_v and cur_v < next_v:
                        d = "lower_low"
                    else:
                        continue
                structs.append({
                    "price": round(float(cur_v), 5),
                    "index": int(idx_arr[i]),
                    "direction": d,
                    "time": df["time"].iloc[int(idx_arr[i])].strftime("%H:%M") if "time" in df.columns else None
                })
            return structs

        sig.bullish_structures = _build_structures(swing_idx_high, highs, True)
        sig.bearish_structures = _build_structures(swing_idx_low,  lows,  False)

        # ---------------------------------------------------------- #
        # 3. Premium / Discount zone (session 24h lookback)
        # ---------------------------------------------------------- #
        lookback = min(200, n)
        sess_high = float(np.max(highs[-lookback:]))
        sess_low  = float(np.min(lows[-lookback:]))
        sess_range = sess_high - sess_low if sess_high != sess_low else 1e-9
        sig.premium_zone   = round(sess_low + sess_range * 0.25, 5)
        sig.discount_zone  = round(sess_low + sess_range * 0.75, 5)

        # ---------------------------------------------------------- #
        # 4. Order blocks  (bearish engulf candle setelah bullish candle
        #    berada di bawah OB atau sebaliknya)
        # ---------------------------------------------------------- #
        def _find_ob(direction: str):
            obs = []
            end = min(n - self.swing_right - 1, n - 1)
            for i in range(self.swing_left, end):
                oi = opens[i]
                ci = closes[i]
                hi = highs[i]
                lo = lows[i]
                body = abs(ci - oi)
                avg_body = np.mean(np.abs(closes[max(0, i-5):i+1] - opens[max(0, i-5):i+1]))
                if avg_body == 0:
                    avg_body = 1e-9
                # Candle besar (body > 2x rata) → impulsive
                if body > 2 * avg_body:
                    if direction == "bullish":
                        # candle bullish engulfing → OB di bawah (candle sebelumnya biasanya bearish)
                        for j in range(i - 1, i - self.ob_lookback, -1):
                            if j < self.swing_left:
                                continue
                            if opens[j] > closes[j]:  # bearish candle → jadi OB bearish → sebaliknya
                                continue
                            if closes[j] <= lo:
                                obs.append({
                                    "top": round(float(hi), 5),
                                    "bottom": round(float(lo), 5),
                                    "close_price": round(float(ci), 5),
                                    "index": int(i),
                                    "direction": "bullish",
                                    "time": df["time"].iloc[i].strftime("%H:%M") if "time" in df.columns else None
                                })
                                break
                    else:  # bearish OB
                        for j in range(i - 1, i - self.ob_lookback, -1):
                            if j < self.swing_left:
                                continue
                            if opens[j] < closes[j]:  # bullish candle → bukan OB bearish
                                continue
                            if closes[j] >= hi:
                                obs.append({
                                    "top": round(float(hi), 5),
                                    "bottom": round(float(lo), 5),
                                    "close_price": round(float(ci), 5),
                                    "index": int(i),
                                    "direction": "bearish",
                                    "time": df["time"].iloc[i].strftime("%H:%M") if "time" in df.columns else None
                                })
                                break
            return obs

        sig.order_blocks_bullish = _find_ob("bullish")
        sig.order_blocks_bearish = _find_ob("bearish")

        # ---------------------------------------------------------- #
        # 5. Equal Highs / Lows  (cluster sederhana)
        # ---------------------------------------------------------- #
        def _equal_levels(values: np.ndarray, is_highs: bool, cluster=True):
            levels = []
            sorted_idx = np.argsort(values)
            for idx_pos, i in enumerate(sorted_idx):
                # Cari neighbour dalam toleransi harga
                same_zone = [j for j in sorted_idx[idx_pos:idx_pos + self.eq_cluster]
                             if abs(values[j] - values[i]) <= tol_price]
                if len(same_zone) >= self.eq_cluster and len(values) - idx_pos >= self.eq_cluster:
                    group_values = values[same_zone]
                    avg_price = group_values.mean()
                    # Pastikan indeks relatif dekat (bukan candle jauh jauh)
                    idx_arr_local = sorted(same_zone)
                    time_diffs = np.diff([df["time"].iloc[k].timestamp() if hasattr(df["time"].iloc[k], 'timestamp') else k for k in idx_arr_local])
                    if np.mean(time_diffs) > 0:
                        first_idx = int(idx_arr_local[0])
                        levels.append({
                            "price": round(float(avg_price), 5),
                            "indices": [int(x) for x in idx_arr_local[:self.eq_cluster]],
                            "direction": "equal_high" if is_highs else "equal_low",
                            "time": df["time"].iloc[first_idx].strftime("%H:%M") if "time" in df.columns else None
                        })
                    if not cluster:
                        cluster = False  # hanya butuh loop sekali
                    del sorted_idx[idx_pos:idx_pos + self.eq_cluster]
                    break
            return levels

        sig.equal_highs = _equal_levels(highs, True)
        sig.equal_lows  = _equal_levels(lows,  False)

        # ---------------------------------------------------------- #
        # 6. BOS & CHoCH  (break of structure / change of character)
        # ---------------------------------------------------------- #
        bos_level, bos_dir, bos_idx = 0.0, "none", None
        choch_level, choch_dir, choch_idx = 0.0, "none", None

        last_close = closes[-1]
        # Sederhana: cari swing high/low terakhir, lalu cek close break
        if len(swing_idx_high) > 0 and len(swing_idx_low) > 0:
            last_swing_high = highs[swing_idx_high[-1]]
            last_swing_low  = lows[swing_idx_low[-1]]

            # BOS = penembusan swing terakhir dengan konfirmasi candle menutup
            if last_close > last_swing_high:
                bos_dir = "bullish"
                bos_level = round(float(last_swing_high), 5)
                bos_idx = int(swing_idx_high[-1])
            elif last_close < last_swing_low:
                bos_dir = "bearish"
                bos_level = round(float(last_swing_low), 5)
                bos_idx = int(swing_idx_low[-1])

            # CHoCH = perubahan karakter — swing low terakhir jadi swing high baru (atau sebaliknya)
            # versi sederhana: close break ke arah berlawanan dari arah terakhir
            if len(swing_idx_low) >= 2:
                prev_swing_low = lows[swing_idx_low[-2]]
                if last_close > last_swing_high and closes[-2] < prev_swing_low:
                    choch_dir = "bullish"
                    choch_level = round(float(last_swing_high), 5)
                    choch_idx = int(swing_idx_high[-1])
            if len(swing_idx_high) >= 2:
                prev_swing_high = highs[swing_idx_high[-2]]
                if last_close < last_swing_low and closes[-2] > prev_swing_high:
                    choch_dir = "bearish"
                    choch_level = round(float(last_swing_low), 5)
                    choch_idx = int(swing_idx_low[-1])

        sig.bos = {"direction": bos_dir, "level": bos_level, "index": bos_idx}
        sig.choch = {"direction": choch_dir, "level": choch_level, "index": choch_idx}

        # ---------------------------------------------------------- #
        # 7. Strong High / Low  (swing dikonfirmasi volume tinggi)
        # ---------------------------------------------------------- #
        vol_max = float(np.max(vols)) if np.max(vols) > 0 else 1e-9
        strong_hi, strong_lo = 0.0, 0.0
        hi_strength, lo_strength = 0.0, 0.0
        if len(swing_idx_high) > 0:
            hi_vols = vols[swing_idx_high]
            max_v_pos = np.argmax(hi_vols)
            if hi_vols[max_v_pos] / vol_max >= 0.6:  # volume relatif tinggi
                idx = int(swing_idx_high[max_v_pos])
                strong_hi = round(float(highs[idx]), 5)
                hi_strength = round(float(hi_vols[max_v_pos] / vol_max), 3)
        if len(swing_idx_low) > 0:
            lo_vols = vols[swing_idx_low]
            max_v_pos = np.argmax(lo_vols)
            if lo_vols[max_v_pos] / vol_max >= 0.6:
                idx = int(swing_idx_low[max_v_pos])
                strong_lo = round(float(lows[idx]), 5)
                lo_strength = round(float(lo_vols[max_v_pos] / vol_max), 3)
        sig.strong_high = strong_hi
        sig.strong_low  = strong_lo

        return sig

    # -------------------------------------------------------------- #
    def to_dict(self, sig: SMCSignal) -> Dict[str, Any]:
        return asdict(sig)

    def to_json(self, sig: SMCSignal) -> str:
        import json
        return json.dumps(asdict(sig), default=str, ensure_ascii=False)
