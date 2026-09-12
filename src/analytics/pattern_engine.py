"""
src/analytics/pattern_engine.py — Macro Dynamic Envelope & Pattern Recognition Engine

Arsitektur: Decoupled Dual-Track Architecture
- Track A (Causal Quant Decision): Anti-repainting ATR-pivot extraction (N=3 confirmation),
  provisional state tagging, wick-to-body rejection/absorption density matrix,
  dan clearance runway calculation untuk MSE & ZCE.
- Track B (Visual Manifold Ribbon): Rolling extremum envelope + Savitzky-Golay smoothing
  (pure NumPy polynomial convolution) untuk visualisasi kurva lentur di Lightweight Charts Dashboard.

Fitur:
- Outlier & Rollover Clamping: Mengeliminasi false spike rollover (03:55-04:15 WIB / MT5 00:00),
  khususnya pada pair CHF, via MAD & ATR-relative winsorizing.
- Zero Token & Sub-Milidetik: Dijalankan tiap bar H4 baru (atau saat refresh cache HTF Stage 1A)
  dalam < 2 milidetik per simbol tanpa ketergantungan library scipy.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

logger = logging.getLogger("pattern_engine")
WIB = ZoneInfo("Asia/Jakarta")


@dataclass
class GeometricPattern:
    """
    Representasi pola geometri diskret (Double Top/Bottom, H&S, Triangles, Wedges, Flags).
    Diadopsi dari MarkitTick TradingView dengan konversi kausal anti-repaint & ATR-confluence.
    """
    name: str = "NONE"                     # DOUBLE_TOP | DOUBLE_BOTTOM | HEAD_AND_SHOULDERS | INV_HEAD_AND_SHOULDERS | SYMMETRICAL_TRIANGLE | ASCENDING_TRIANGLE | DESCENDING_TRIANGLE | RISING_WEDGE | FALLING_WEDGE | BULL_FLAG | BEAR_FLAG | RECTANGLE | NONE
    bias: str = "NEUTRAL"                  # BULLISH | BEARISH | NEUTRAL
    status: str = "NONE"                   # FORMING | TESTING_BREAKOUT | CONFIRMED_BREAKOUT | NONE
    height_pips: float = 0.0               # Tinggi formasi H dalam pips
    neckline_price: float = 0.0            # Level garis leher atau batas breakout
    breakout_threshold: float = 0.0        # Level konfirmasi breakout (neckline +/- k*ATR)
    target_geom_price: float = 0.0         # Proyeksi Measured Move Target (Neckline +/- H)
    target_pips: float = 0.0               # Jarak target dari harga live (pips)
    confidence_score: float = 0.0          # Kualitas pola (0.0 - 1.0)
    description: str = ""                  # Penjelasan pola satu baris

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MacroEnvelopeResult:
    """
    Hasil evaluasi topologi dan geometri envelope makro H4.
    Digunakan oleh MSE, ZCE, dan visualisasi Dashboard Cockpit.
    """
    symbol: str
    timeframe: str = "H4"
    structural_trend: str = "RANGING"  # BULLISH_EXPANSION | BEARISH_EXPANSION | COMPRESSION | EXPANSION_BROADENING | RANGING
    instantaneous_slope: float = 0.0   # Turunan pertama dS/dt (pips per bar H4)
    curvature: float = 0.0             # Turunan kedua d2S/dt2 (akselerasi/deselerasi)
    channel_position_tau: float = 0.5  # Posisi internal kurva: 0.0 (lantai) -> 1.0 (plafon)
    net_wick_delta: float = 0.0        # Akumulasi 10-bar: positif = buyer absorption, negatif = seller rejection
    recent_rejection_score: float = 0.0 # Total densitas ekor atas 10-bar
    recent_absorption_score: float = 0.0 # Total densitas ekor bawah 10-bar
    clearance_up_pips: float = 0.0     # Sisa ruang ke plafon body envelope (pips)
    clearance_down_pips: float = 0.0   # Sisa ruang ke lantai body envelope (pips)
    envelope_upper: float = 0.0        # Nilai harga kurva body atas saat ini
    envelope_lower: float = 0.0        # Nilai harga kurva body bawah saat ini
    envelope_wick_upper: float = 0.0   # Nilai harga kurva wick atas saat ini
    envelope_wick_lower: float = 0.0   # Nilai harga kurva wick bawah saat ini
    upper_slope: float = 0.0           # Kemiringan garis swing high taktis dekat (pips per bar H4)
    lower_slope: float = 0.0           # Kemiringan garis swing low taktis dekat (pips per bar H4)
    macro_upper_slope: float = 0.0     # Kemiringan garis swing high makro jauh (pips per bar H4)
    macro_lower_slope: float = 0.0     # Kemiringan garis swing low makro jauh (pips per bar H4)
    provisional_state: str = "CONFIRMED" # CONFIRMED | PROVISIONAL_PENDING
    confirmed_peaks: List[Dict[str, Any]] = field(default_factory=list)
    confirmed_troughs: List[Dict[str, Any]] = field(default_factory=list)
    geometric_pattern: Optional[Dict[str, Any]] = None
    macro_pattern: Optional[Dict[str, Any]] = None
    pattern_display_label: str = ""
    measured_target_pips: float = 0.0
    dealing_range: Dict[str, Any] = field(default_factory=dict)
    order_flow: Dict[str, Any] = field(default_factory=dict)
    draw_on_liquidity: Dict[str, Any] = field(default_factory=dict)
    visual_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------------- #
# 1. PURE NUMPY SAVITZKY-GOLAY CONVOLUTION (ZERO SCIPY DEPENDENCY)
# ----------------------------------------------------------------------------- #

@lru_cache(maxsize=32)
def _compute_savgol_weights(window_length: int = 7, polyorder: int = 2, deriv: int = 0) -> np.ndarray:
    """
    Menghitung bobot konvolusi Savitzky-Golay secara analitis menggunakan
    Metode Kuadrat Terkecil (Least Squares) polinomial di NumPy murni.
    """
    if window_length % 2 == 0 or window_length < 3:
        raise ValueError("window_length harus ganjil dan >= 3")
    if polyorder >= window_length:
        raise ValueError("polyorder harus lebih kecil dari window_length")

    half_window = window_length // 2
    x = np.arange(-half_window, half_window + 1, dtype=float)
    # Matriks Vandermonde terbalik untuk basis polinomial [x^0, x^1, ..., x^polyorder]
    A = np.vander(x, polyorder + 1)[:, ::-1]
    pinv_A = np.linalg.pinv(A)
    # Turunan ke-deriv dikalikan faktorial (deriv!)
    from math import factorial
    weights = pinv_A[deriv] * factorial(deriv)
    return weights


def savgol_smooth(
    signal: np.ndarray,
    window_length: int = 7,
    polyorder: int = 2,
    deriv: int = 0
) -> np.ndarray:
    """
    Penerapan Savitzky-Golay filter pada array 1D dengan boundary mode 'edge'.
    Menghasilkan turunan ke-0 (smoothing), ke-1 (slope), atau ke-2 (curvature).
    """
    n = len(signal)
    if n < window_length:
        # Jika panjang bar lebih pendek dari window, fallback ke window terkecil yang valid
        window_length = n if n % 2 != 0 else n - 1
        if window_length < 3:
            return signal.copy()
        if polyorder >= window_length:
            polyorder = max(1, window_length - 1)

    weights = _compute_savgol_weights(window_length, polyorder, deriv)
    half_window = window_length // 2
    padded = np.pad(signal, half_window, mode="edge")
    # Konvolusi 1D (weights dibalik untuk korelasi diskrit)
    convolved = np.convolve(padded, weights[::-1], mode="valid")
    return convolved


# ----------------------------------------------------------------------------- #
# 2. OUTLIER & ROLLOVER CLAMPING (MAD & ATR-WINSORIZING)
# ----------------------------------------------------------------------------- #

def clean_outliers_and_rollover(
    df: pd.DataFrame,
    atr_series: pd.Series,
    symbol: str = "",
    o: Optional[np.ndarray] = None,
    h: Optional[np.ndarray] = None,
    l: Optional[np.ndarray] = None,
    c: Optional[np.ndarray] = None
) -> pd.DataFrame:
    """
    Menyaring lonjakan spread/ekor palsu pada jam rollover (03:55-04:15 WIB / 00:00 MT5 server)
    dan flash wicks abnormal (terutama pair CHF).

    Prinsip:
    - Jika ekor atas (High - max(Open, Close)) > 2.5x ATR, cek apakah outlier lokal.
    - Jika outlier, di-winsorize menjadi max(Open, Close) + 1.5x ATR.
    - Demikian pula untuk ekor bawah.
    - Menghasilkan kolom 'clean_high' dan 'clean_low'.
    """
    d = df.copy(deep=False)
    o = o if o is not None else d["open"].to_numpy(dtype=float)
    h = h if h is not None else d["high"].to_numpy(dtype=float)
    l = l if l is not None else d["low"].to_numpy(dtype=float)
    c = c if c is not None else d["close"].to_numpy(dtype=float)
    atr = atr_series.to_numpy(dtype=float) if hasattr(atr_series, "to_numpy") else np.asarray(atr_series, dtype=float)

    n = len(d)
    clean_h = h.copy()
    clean_l = l.copy()

    body_top = np.maximum(o, c)
    body_bottom = np.minimum(o, c)
    upper_wick = h - body_top
    lower_wick = body_bottom - l

    # Deteksi rollover WIB secara cepat tanpa pd.to_datetime overhead
    is_rollover = np.zeros(n, dtype=bool)
    if "time" in d.columns:
        t_col = d["time"]
        if hasattr(t_col, "dt"):
            h_arr = t_col.dt.hour.to_numpy()
            is_rollover = (h_arr == 4) | (h_arr == 3) | (h_arr == 0)
        elif hasattr(t_col, "values") and str(t_col.dtype).startswith("datetime64"):
            try:
                h_arr = t_col.values.astype('datetime64[h]').astype(int) % 24
                is_rollover = (h_arr == 4) | (h_arr == 3) | (h_arr == 0)
            except Exception:
                pass
        elif len(t_col) > 0 and hasattr(t_col.iloc[0], "hour"):
            h_arr = np.array([t.hour for t in t_col])
            is_rollover = (h_arr == 4) | (h_arr == 3) | (h_arr == 0)
    elif isinstance(d.index, pd.DatetimeIndex):
        try:
            h_arr = d.index.hour.to_numpy()
            is_rollover = (h_arr == 4) | (h_arr == 3) | (h_arr == 0)
        except Exception:
            h_arr = d.index.values.astype('datetime64[h]').astype(int) % 24
            is_rollover = (h_arr == 4) | (h_arr == 3) | (h_arr == 0)

    is_chf = "CHF" in symbol.upper()
    atr_mult_thresh = 2.0 if (is_chf or np.any(is_rollover)) else 2.5
    clamp_mult = 1.35 if is_chf else 1.50

    valid_atr = (atr > 0) & (~np.isnan(atr))
    thresh_up = atr_mult_thresh * atr
    thresh_down = atr_mult_thresh * atr

    mask_up = valid_atr & (upper_wick > thresh_up)
    clean_h[mask_up] = body_top[mask_up] + (clamp_mult * atr[mask_up])

    mask_down = valid_atr & (lower_wick > thresh_down)
    clean_l[mask_down] = body_bottom[mask_down] - (clamp_mult * atr[mask_down])

    d["clean_high"] = clean_h
    d["clean_low"] = clean_l
    return d


# ----------------------------------------------------------------------------- #
# 3. TRACK A: CAUSAL PIVOT EXTRACTION (ZERO REPAINTING)
# ----------------------------------------------------------------------------- #

def extract_causal_pivots(
    highs: np.ndarray,
    lows: np.ndarray,
    n_confirm: int = 3,
    time_vals: Optional[List[int]] = None,
    cur_atr: float = 0.0
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """
    Ekstraksi titik balik puncak (peaks) dan lembah (troughs) secara 100% kausal
    dengan pelabelan SMC Structural Hierarchy (External vs Internal Structure):
    - Mencegah false HH pada minor bounce lokal di dalam downtrend.
    - True HH hanya jika melampaui active structural high (+ ATR noise buffer).
    - True LL hanya jika menembus active structural low (- ATR noise buffer).
    """
    n = len(highs)
    peaks = []
    troughs = []
    has_provisional_extreme = False

    if n < (2 * n_confirm + 1):
        return peaks, troughs, has_provisional_extreme

    # 1. Ekstraksi seluruh kandidat pivot puncak dan lembah kausal (k <= n - 1 - n_confirm)
    max_confirmed_idx = n - 1 - n_confirm
    raw_peaks = []
    raw_troughs = []

    for k in range(n_confirm, max_confirmed_idx + 1):
        hk = highs[k]
        is_peak = True
        for j in range(k - n_confirm, k + n_confirm + 1):
            if j != k and highs[j] > hk:
                is_peak = False
                break
        if is_peak:
            raw_peaks.append({
                "index": int(k),
                "time": time_vals[k] if (time_vals and k < len(time_vals)) else 0,
                "price": float(hk),
                "type": "PEAK",
                "bar_age": int(n - 1 - k)
            })

        # Trough test: k adalah nilai terendah
        lk = lows[k]
        is_trough = True
        for j in range(k - n_confirm, k + n_confirm + 1):
            if j != k and lows[j] < lk:
                is_trough = False
                break
        if is_trough:
            raw_troughs.append({
                "index": int(k),
                "time": time_vals[k] if (time_vals and k < len(time_vals)) else 0,
                "price": float(lk),
                "type": "TROUGH",
                "bar_age": int(n - 1 - k)
            })

    # 2. Sequential SMC Structural Hierarchy Labeling
    noise_buffer = 0.15 * cur_atr if cur_atr > 0 else 1e-5
    active_major_high = None
    active_major_low = None
    last_peak_candidate = None
    last_trough_candidate = None

    all_pivots = []
    for p in raw_peaks:
        all_pivots.append(p)
    for t in raw_troughs:
        all_pivots.append(t)
    all_pivots.sort(key=lambda x: x["index"])

    for piv in all_pivots:
        if piv["type"] == "PEAK":
            price = piv["price"]
            if active_major_high is None:
                lbl = "H"
                active_major_high = piv
            elif price > active_major_high["price"] + noise_buffer:
                lbl = "HH"  # True External Higher High
                active_major_high = piv
                if last_trough_candidate is not None:
                    active_major_low = last_trough_candidate
            elif abs(price - active_major_high["price"]) <= noise_buffer:
                lbl = "EH"
            else:
                lbl = "LH"  # Lower High relative to active structural high
            piv["label"] = lbl
            last_peak_candidate = piv
            peaks.append(piv)
        else:  # TROUGH
            price = piv["price"]
            if active_major_low is None:
                lbl = "L"
                active_major_low = piv
            elif price < active_major_low["price"] - noise_buffer:
                lbl = "LL"  # True External Lower Low
                active_major_low = piv
                if last_peak_candidate is not None:
                    active_major_high = last_peak_candidate
            elif abs(price - active_major_low["price"]) <= noise_buffer:
                lbl = "EL"
            else:
                lbl = "HL"  # Higher Low relative to active structural low
            piv["label"] = lbl
            last_trough_candidate = piv
            troughs.append(piv)

    # 3. Cek apakah ada calon ekstrem di bar provisional [max_confirmed_idx + 1 .. n - 1]
    recent_highs = highs[max_confirmed_idx + 1:]
    recent_lows = lows[max_confirmed_idx + 1:]
    if len(peaks) > 0 and len(recent_highs) > 0 and np.max(recent_highs) > peaks[-1]["price"]:
        has_provisional_extreme = True
    if len(troughs) > 0 and len(recent_lows) > 0 and np.min(recent_lows) < troughs[-1]["price"]:
        has_provisional_extreme = True

    return peaks, troughs, has_provisional_extreme


def classify_structural_trend(
    peaks: List[Dict[str, Any]],
    troughs: List[Dict[str, Any]]
) -> str:
    """
    Mengklasifikasikan struktur tren dari deret puncak dan lembah yang telah terkonfirmasi:
    - HH + HL -> BULLISH_EXPANSION
    - LH + LL -> BEARISH_EXPANSION
    - LH + HL -> COMPRESSION (Symmetrical/Wedge)
    - HH + LL -> EXPANSION_BROADENING
    - Lainnya -> RANGING
    """
    if len(peaks) < 2 or len(troughs) < 2:
        return "RANGING"

    p_curr = peaks[-1]["price"]
    p_prev = peaks[-2]["price"]
    v_curr = troughs[-1]["price"]
    v_prev = troughs[-2]["price"]

    is_hh = p_curr > p_prev
    is_lh = p_curr < p_prev
    is_hl = v_curr > v_prev
    is_ll = v_curr < v_prev

    if is_hh and is_hl:
        return "BULLISH_EXPANSION"
    elif is_lh and is_ll:
        return "BEARISH_EXPANSION"
    elif is_lh and is_hl:
        return "COMPRESSION"
    elif is_hh and is_ll:
        return "EXPANSION_BROADENING"
    else:
        return "RANGING"


# ----------------------------------------------------------------------------- #
# 4. TRACK D: GEOMETRIC PATTERN CLASSIFIER (ADAPTED FROM MARKITTICK)
# ----------------------------------------------------------------------------- #

def detect_geometric_patterns(
    peaks: List[Dict[str, Any]],
    troughs: List[Dict[str, Any]],
    upper_slope: float,
    lower_slope: float,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    cur_atr: float,
    pip_size: float = 0.0001,
    structural_trend: str = "RANGING"
) -> GeometricPattern:
    """
    Mendeteksi pola geometris spesifik klasik (Double Top/Bottom, Triangles, Wedges, Flags, Rectangles)
    menggunakan deret pivot kausal terkonfirmasi (N=3) dan kalibrasi multi-slope pips/bar presisi.
    Head & Shoulders ditiadakan total sesuai karakteristik zigzag pasar FX.

    Spesifikasi Ambang Batas Multi-Slope:
    - Symmetrical Triangle: m_u < -0.10 dan m_l > +0.10 (mengerucut simetris)
    - Ascending Triangle: |m_u| <= 0.10 (plafon horizontal) dan m_l > +0.10 (lantai naik -> bias bullish)
    - Descending Triangle: m_u < -0.10 (plafon turun) dan |m_l| <= 0.10 (lantai horizontal -> bias bearish)
    - Falling Wedge: m_u < 0 dan m_l < 0, dengan |m_l| > |m_u| (lantai turun lebih tajam -> reversal buy)
    - Rising Wedge: m_u > 0 dan m_l > 0, dengan m_l > m_u (lantai naik lebih tajam -> reversal sell)
    - Rectangle / Box: |m_u| <= 0.10 dan |m_l| <= 0.10
    - Bull / Bear Flag: Tiang impuls >= 3.0 * ATR (15-25 bar), kanal paralel |m_u - m_l| <= 0.20
    - Double Top / Bottom: |m_u| <= 0.10 (Top) / |m_l| <= 0.10 (Bottom) dengan diff <= 0.18 * ATR
    - Fallback: structural_trend
    """
    if len(peaks) < 1 or len(troughs) < 1:
        return GeometricPattern(name=structural_trend, bias="NEUTRAL", status="FORMING")

    last_close = float(closes[-1])
    breakout_margin = 0.15 * cur_atr
    flat_thresh = 0.10  # Batas kemiringan slope pips/bar untuk level horizontal (plafon/lantai)

    p_curr = peaks[-1] if len(peaks) >= 1 else None
    p_prev = peaks[-2] if len(peaks) >= 2 else p_curr
    v_curr = troughs[-1] if len(troughs) >= 1 else None
    v_prev = troughs[-2] if len(troughs) >= 2 else v_curr

    # -------------------------------------------------------------
    # 1. BULL / BEAR FLAG (POLE >= 3.0 * ATR + PARALLEL CHANNEL <= 0.20)
    # -------------------------------------------------------------
    n_bars = len(closes)
    if n_bars >= 25 and p_curr is not None and v_curr is not None:
        pole_start = max(0, n_bars - 30)
        pole_end = max(1, n_bars - 8)
        prior_high = float(np.max(highs[pole_start:pole_end]))
        prior_low = float(np.min(lows[pole_start:pole_end]))
        pole_height = prior_high - prior_low
        if pole_height >= 3.0 * cur_atr:
            slope_diff = abs(upper_slope - lower_slope)
            if slope_diff <= 0.20:
                # Bull Flag: Impuls naik, kanal konsolidasi miring turun (upper & lower < -0.10)
                if upper_slope < -0.10 and lower_slope < -0.10:
                    neckline = float(p_curr["price"])
                    target = round(neckline + pole_height, 5)
                    h_pips = round(pole_height / max(pip_size, 1e-6), 1)
                    target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
                    brk_thresh = round(neckline + breakout_margin, 5)
                    status = "CONFIRMED_BREAKOUT" if last_close > brk_thresh else ("TESTING_BREAKOUT" if last_close > neckline else "FORMING")
                    return GeometricPattern(
                        name="BULL_FLAG",
                        bias="BULLISH",
                        status=status,
                        height_pips=h_pips,
                        neckline_price=round(neckline, 5),
                        breakout_threshold=brk_thresh,
                        target_geom_price=target,
                        target_pips=target_dist,
                        confidence_score=0.80,
                        description=f"Bull Flag Continuation, Resistance: {neckline:.5f}, Target: {target:.5f}"
                    )
                # Bear Flag: Impuls turun, kanal konsolidasi miring naik (upper & lower > +0.10)
                elif upper_slope > +0.10 and lower_slope > +0.10:
                    neckline = float(v_curr["price"])
                    target = round(neckline - pole_height, 5)
                    h_pips = round(pole_height / max(pip_size, 1e-6), 1)
                    target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
                    brk_thresh = round(neckline - breakout_margin, 5)
                    status = "CONFIRMED_BREAKOUT" if last_close < brk_thresh else ("TESTING_BREAKOUT" if last_close < neckline else "FORMING")
                    return GeometricPattern(
                        name="BEAR_FLAG",
                        bias="BEARISH",
                        status=status,
                        height_pips=h_pips,
                        neckline_price=round(neckline, 5),
                        breakout_threshold=brk_thresh,
                        target_geom_price=target,
                        target_pips=target_dist,
                        confidence_score=0.80,
                        description=f"Bear Flag Continuation, Support: {neckline:.5f}, Target: {target:.5f}"
                    )

    # -------------------------------------------------------------
    # 2. DOUBLE TOP & DOUBLE BOTTOM (HORIZONTAL PIVOTS)
    # -------------------------------------------------------------
    if len(peaks) >= 2 and len(troughs) >= 1:
        p_c = peaks[-1]
        p_p = peaks[-2]
        mid_tr = [t for t in troughs if p_p["index"] < t["index"] < p_c["index"]]
        if len(mid_tr) > 0:
            v_mid = min(mid_tr, key=lambda x: x["price"])
            peak_diff = abs(p_c["price"] - p_p["price"])
            # Hanya Double Top jika atap horizontal (|upper_slope| <= 0.10) dan lantai tidak naik tajam (lower_slope <= 0.10)
            if peak_diff <= (0.18 * cur_atr) and abs(upper_slope) <= flat_thresh and lower_slope <= flat_thresh:
                neckline = float(v_mid["price"])
                avg_top = (p_c["price"] + p_p["price"]) / 2.0
                h_val = float(avg_top - neckline)
                if h_val >= 0.75 * cur_atr:
                    h_pips = round(h_val / max(pip_size, 1e-6), 1)
                    target = round(neckline - h_val, 5)
                    target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
                    brk_thresh = round(neckline - breakout_margin, 5)
                    status = "CONFIRMED_BREAKOUT" if last_close < brk_thresh else ("TESTING_BREAKOUT" if last_close < neckline else "FORMING")
                    return GeometricPattern(
                        name="DOUBLE_TOP",
                        bias="BEARISH",
                        status=status,
                        height_pips=h_pips,
                        neckline_price=round(neckline, 5),
                        breakout_threshold=brk_thresh,
                        target_geom_price=target,
                        target_pips=target_dist,
                        confidence_score=0.80,
                        description=f"Double Top Bearish, Neckline: {neckline:.5f}, Target: {target:.5f}"
                    )

    if len(troughs) >= 2 and len(peaks) >= 1:
        v_c = troughs[-1]
        v_p = troughs[-2]
        mid_pk = [p for p in peaks if v_p["index"] < p["index"] < v_c["index"]]
        if len(mid_pk) > 0:
            p_mid = max(mid_pk, key=lambda x: x["price"])
            trough_diff = abs(v_c["price"] - v_p["price"])
            # Hanya Double Bottom jika lantai horizontal (|lower_slope| <= 0.10) dan atap tidak turun tajam (upper_slope >= -0.10)
            if trough_diff <= (0.18 * cur_atr) and abs(lower_slope) <= flat_thresh and upper_slope >= -flat_thresh:
                neckline = float(p_mid["price"])
                avg_bot = (v_c["price"] + v_p["price"]) / 2.0
                h_val = float(neckline - avg_bot)
                if h_val >= 0.75 * cur_atr:
                    h_pips = round(h_val / max(pip_size, 1e-6), 1)
                    target = round(neckline + h_val, 5)
                    target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
                    brk_thresh = round(neckline + breakout_margin, 5)
                    status = "CONFIRMED_BREAKOUT" if last_close > brk_thresh else ("TESTING_BREAKOUT" if last_close > neckline else "FORMING")
                    return GeometricPattern(
                        name="DOUBLE_BOTTOM",
                        bias="BULLISH",
                        status=status,
                        height_pips=h_pips,
                        neckline_price=round(neckline, 5),
                        breakout_threshold=brk_thresh,
                        target_geom_price=target,
                        target_pips=target_dist,
                        confidence_score=0.80,
                        description=f"Double Bottom Bullish, Neckline: {neckline:.5f}, Target: {target:.5f}"
                    )

    # -------------------------------------------------------------
    # 3. WEDGES (RISING WEDGE / FALLING WEDGE)
    # -------------------------------------------------------------
    # Falling Wedge: m_u < -flat_thresh dan m_l < -flat_thresh, di mana |m_l| > |m_u| (keduanya turun, lantai jatuh lebih curam)
    if upper_slope < -flat_thresh and lower_slope < -flat_thresh and abs(lower_slope) > abs(upper_slope):
        if p_prev is not None and v_prev is not None:
            h_val = float(abs(p_prev["price"] - v_prev["price"]))
        elif p_curr is not None and v_curr is not None:
            h_val = float(abs(p_curr["price"] - v_curr["price"]))
        else:
            h_val = float(1.5 * cur_atr)
        h_pips = round(h_val / max(pip_size, 1e-6), 1)
        neckline = float(p_curr["price"]) if p_curr else last_close
        target = round(neckline + h_val, 5)
        target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
        brk_thresh = round(neckline + breakout_margin, 5)
        status = "CONFIRMED_BREAKOUT" if last_close > brk_thresh else ("TESTING_BREAKOUT" if last_close > neckline else "FORMING")
        return GeometricPattern(
            name="FALLING_WEDGE",
            bias="BULLISH",
            status=status,
            height_pips=h_pips,
            neckline_price=round(neckline, 5),
            breakout_threshold=brk_thresh,
            target_geom_price=target,
            target_pips=target_dist,
            confidence_score=0.80,
            description=f"Falling Wedge Reversal, Resistance: {neckline:.5f}, Target: {target:.5f}"
        )

    # Rising Wedge: m_u > flat_thresh dan m_l > flat_thresh, di mana m_l > m_u (keduanya naik, lantai menanjak lebih curam)
    if upper_slope > flat_thresh and lower_slope > flat_thresh and lower_slope > upper_slope:
        if p_prev is not None and v_prev is not None:
            h_val = float(abs(p_prev["price"] - v_prev["price"]))
        elif p_curr is not None and v_curr is not None:
            h_val = float(abs(p_curr["price"] - v_curr["price"]))
        else:
            h_val = float(1.5 * cur_atr)
        h_pips = round(h_val / max(pip_size, 1e-6), 1)
        neckline = float(v_curr["price"]) if v_curr else last_close
        target = round(neckline - h_val, 5)
        target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
        brk_thresh = round(neckline - breakout_margin, 5)
        status = "CONFIRMED_BREAKOUT" if last_close < brk_thresh else ("TESTING_BREAKOUT" if last_close < neckline else "FORMING")
        return GeometricPattern(
            name="RISING_WEDGE",
            bias="BEARISH",
            status=status,
            height_pips=h_pips,
            neckline_price=round(neckline, 5),
            breakout_threshold=brk_thresh,
            target_geom_price=target,
            target_pips=target_dist,
            confidence_score=0.80,
            description=f"Rising Wedge Reversal, Support: {neckline:.5f}, Target: {target:.5f}"
        )

    # -------------------------------------------------------------
    # 4. TRIANGLES (ASCENDING, DESCENDING, SYMMETRICAL)
    # -------------------------------------------------------------
    # Ascending Triangle: |m_u| <= 0.10 dan m_l > +0.10 (plafon horizontal, lantai naik)
    if abs(upper_slope) <= flat_thresh and lower_slope > flat_thresh and p_curr is not None:
        neckline = float(p_curr["price"])
        h_val = float(abs(neckline - (v_prev["price"] if v_prev else v_curr["price"]))) if (v_prev or v_curr) else float(1.2 * cur_atr)
        h_pips = round(h_val / max(pip_size, 1e-6), 1)
        target = round(neckline + h_val, 5)
        target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
        brk_thresh = round(neckline + breakout_margin, 5)
        status = "CONFIRMED_BREAKOUT" if last_close > brk_thresh else ("TESTING_BREAKOUT" if last_close > neckline else "FORMING")
        return GeometricPattern(
            name="ASCENDING_TRIANGLE",
            bias="BULLISH",
            status=status,
            height_pips=h_pips,
            neckline_price=round(neckline, 5),
            breakout_threshold=brk_thresh,
            target_geom_price=target,
            target_pips=target_dist,
            confidence_score=0.80,
            description=f"Ascending Triangle Bullish, Resistance: {neckline:.5f}, Target: {target:.5f}"
        )

    # Descending Triangle: m_u < -0.10 dan |m_l| <= 0.10 (plafon turun, lantai horizontal)
    if upper_slope < -flat_thresh and abs(lower_slope) <= flat_thresh and v_curr is not None:
        neckline = float(v_curr["price"])
        h_val = float(abs((p_prev["price"] if p_prev else p_curr["price"]) - neckline)) if (p_prev or p_curr) else float(1.2 * cur_atr)
        h_pips = round(h_val / max(pip_size, 1e-6), 1)
        target = round(neckline - h_val, 5)
        target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
        brk_thresh = round(neckline - breakout_margin, 5)
        status = "CONFIRMED_BREAKOUT" if last_close < brk_thresh else ("TESTING_BREAKOUT" if last_close < neckline else "FORMING")
        return GeometricPattern(
            name="DESCENDING_TRIANGLE",
            bias="BEARISH",
            status=status,
            height_pips=h_pips,
            neckline_price=round(neckline, 5),
            breakout_threshold=brk_thresh,
            target_geom_price=target,
            target_pips=target_dist,
            confidence_score=0.80,
            description=f"Descending Triangle Bearish, Support: {neckline:.5f}, Target: {target:.5f}"
        )

    # Symmetrical Triangle: m_u < -0.10 dan m_l > +0.10 (mengerucut simetris)
    if upper_slope < -flat_thresh and lower_slope > flat_thresh:
        if p_prev is not None and v_prev is not None:
            h_val = float(abs(p_prev["price"] - v_prev["price"]))
        elif p_curr is not None and v_curr is not None:
            h_val = float(abs(p_curr["price"] - v_curr["price"]))
        else:
            h_val = float(1.5 * cur_atr)
        h_pips = round(h_val / max(pip_size, 1e-6), 1)
        p_ref = p_curr["price"] if p_curr else last_close
        v_ref = v_curr["price"] if v_curr else last_close
        is_bull_break = last_close > p_ref
        neckline = float(p_ref if is_bull_break else v_ref)
        target = round(neckline + (h_val if is_bull_break else -h_val), 5)
        target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
        brk_thresh = round(p_ref + breakout_margin if is_bull_break else v_ref - breakout_margin, 5)
        status = "CONFIRMED_BREAKOUT" if (last_close > p_ref + breakout_margin or last_close < v_ref - breakout_margin) else "FORMING"
        return GeometricPattern(
            name="SYMMETRICAL_TRIANGLE",
            bias="BULLISH" if is_bull_break else ("BEARISH" if last_close < v_ref else "NEUTRAL"),
            status=status,
            height_pips=h_pips,
            neckline_price=round(neckline, 5),
            breakout_threshold=brk_thresh,
            target_geom_price=target,
            target_pips=target_dist,
            confidence_score=0.75,
            description=f"Symmetrical Triangle, Apex Converging, Target: {target:.5f}"
        )

    # -------------------------------------------------------------
    # 4b. PARALLEL CHANNELS (ASCENDING CHANNEL / DESCENDING CHANNEL)
    # -------------------------------------------------------------
    slope_diff = abs(upper_slope - lower_slope)
    par_thresh = max(0.40 * (cur_atr / max(pip_size, 1e-6)), 0.40)
    # Ascending Channel: Keduanya miring ke atas (m_u > +flat_thresh & m_l > +flat_thresh)
    if upper_slope > flat_thresh and lower_slope > flat_thresh and slope_diff <= par_thresh:
        p_ref = p_curr["price"] if p_curr else last_close
        v_ref = v_curr["price"] if v_curr else last_close
        h_val = float(max(abs(p_ref - v_ref), 0.75 * cur_atr))
        h_pips = round(h_val / max(pip_size, 1e-6), 1)
        is_bull_break = last_close > p_ref + breakout_margin
        is_bear_break = last_close < v_ref - breakout_margin
        status = "CONFIRMED_BREAKOUT" if (is_bull_break or is_bear_break) else ("TESTING_BREAKOUT" if (last_close > p_ref or last_close < v_ref) else "FORMING")
        target = round(p_ref + h_val if is_bull_break else (v_ref - h_val if is_bear_break else p_ref), 5)
        target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
        return GeometricPattern(
            name="ASCENDING_CHANNEL",
            bias="BULLISH" if not is_bear_break else "BEARISH",
            status=status,
            height_pips=h_pips,
            neckline_price=round(p_ref if not is_bear_break else v_ref, 5),
            breakout_threshold=round(p_ref + breakout_margin if not is_bear_break else v_ref - breakout_margin, 5),
            target_geom_price=target,
            target_pips=target_dist,
            confidence_score=0.80,
            description=f"Ascending Channel Bullish (+{upper_slope:.1f}/+{lower_slope:.1f} p/b, {h_pips} pips)"
        )

    # Descending Channel: Keduanya miring ke bawah (m_u < -flat_thresh & m_l < -flat_thresh)
    if upper_slope < -flat_thresh and lower_slope < -flat_thresh and slope_diff <= par_thresh:
        p_ref = p_curr["price"] if p_curr else last_close
        v_ref = v_curr["price"] if v_curr else last_close
        h_val = float(max(abs(p_ref - v_ref), 0.75 * cur_atr))
        h_pips = round(h_val / max(pip_size, 1e-6), 1)
        is_bull_break = last_close > p_ref + breakout_margin
        is_bear_break = last_close < v_ref - breakout_margin
        status = "CONFIRMED_BREAKOUT" if (is_bull_break or is_bear_break) else ("TESTING_BREAKOUT" if (last_close > p_ref or last_close < v_ref) else "FORMING")
        target = round(p_ref + h_val if is_bull_break else (v_ref - h_val if is_bear_break else v_ref), 5)
        target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
        return GeometricPattern(
            name="DESCENDING_CHANNEL",
            bias="BEARISH" if not is_bull_break else "BULLISH",
            status=status,
            height_pips=h_pips,
            neckline_price=round(v_ref if not is_bull_break else p_ref, 5),
            breakout_threshold=round(v_ref - breakout_margin if not is_bull_break else p_ref + breakout_margin, 5),
            target_geom_price=target,
            target_pips=target_dist,
            confidence_score=0.80,
            description=f"Descending Channel Bearish ({upper_slope:.1f}/{lower_slope:.1f} p/b, {h_pips} pips)"
        )

    # -------------------------------------------------------------
    # 5. RECTANGLE / HORIZONTAL CHANNEL (|m_u| <= 0.10 & |m_l| <= 0.10)
    # -------------------------------------------------------------
    if abs(upper_slope) <= flat_thresh and abs(lower_slope) <= flat_thresh:
        p_ref = p_curr["price"] if p_curr else last_close
        v_ref = v_curr["price"] if v_curr else last_close
        h_val = float(max(abs(p_ref - v_ref), 0.5 * cur_atr))
        h_pips = round(h_val / max(pip_size, 1e-6), 1)
        is_bull_break = last_close > p_ref
        is_bear_break = last_close < v_ref
        status = "CONFIRMED_BREAKOUT" if (last_close > p_ref + breakout_margin or last_close < v_ref - breakout_margin) else "FORMING"
        target = round(p_ref + h_val if is_bull_break else (v_ref - h_val if is_bear_break else p_ref), 5)
        target_dist = round((target - last_close) / max(pip_size, 1e-6), 1)
        return GeometricPattern(
            name="RECTANGLE",
            bias="BULLISH" if is_bull_break else ("BEARISH" if is_bear_break else "NEUTRAL"),
            status=status,
            height_pips=h_pips,
            neckline_price=round(p_ref if is_bull_break else v_ref, 5),
            breakout_threshold=round(p_ref + breakout_margin if is_bull_break else v_ref - breakout_margin, 5),
            target_geom_price=target,
            target_pips=target_dist,
            confidence_score=0.65,
            description=f"Rectangle Range Channel ({h_pips} pips)"
        )

    # -------------------------------------------------------------
    # 6. DEFAULT / FALLBACK: STRUCTURAL TREND
    # -------------------------------------------------------------
    return GeometricPattern(
        name=structural_trend,
        bias="BULLISH" if "BULLISH" in structural_trend else ("BEARISH" if "BEARISH" in structural_trend else "NEUTRAL"),
        status="FORMING",
        height_pips=0.0,
        neckline_price=0.0,
        breakout_threshold=0.0,
        target_geom_price=0.0,
        target_pips=0.0,
        confidence_score=0.50,
        description=f"Macro {structural_trend}"
    )


def _extract_macro_trendlines(
    peaks: List[Dict[str, Any]],
    troughs: List[Dict[str, Any]],
    n_bars: int,
    pip_size: float,
    time_vals: List[int],
    highs: Optional[np.ndarray] = None,
    lows: Optional[np.ndarray] = None,
    cur_atr: float = 0.0020
) -> Tuple[Dict[str, Any], float, Dict[str, Any], float]:
    """
    Ekstraksi garis tren makro horizon jauh (40-100 bar) berbasis Multi-Scale Macro Swings
    dan Enclosing Wide-Span Alignment.
    Menghasilkan pasangan channel makro (Upper dan Lower) yang seimbang temporal dan spasial.
    """
    macro_upper_line = {}
    macro_upper_slope = 0.0
    macro_lower_line = {}
    macro_lower_slope = 0.0

    # 1. Multi-Scale Macro Pivots (n_confirm=6, fallback 4, fallback peaks/troughs)
    p_use = peaks
    t_use = troughs
    if highs is not None and lows is not None and len(highs) >= 30:
        p_m, t_m, _ = extract_causal_pivots(highs, lows, n_confirm=6, time_vals=time_vals)
        if len(p_m) < 2 or len(t_m) < 2:
            p_m, t_m, _ = extract_causal_pivots(highs, lows, n_confirm=4, time_vals=time_vals)
        if len(p_m) >= 2:
            p_use = p_m
        if len(t_m) >= 2:
            t_use = t_m

    max_slope_pips = max((1.5 * cur_atr) / max(pip_size, 1e-6), 15.0)

    # 2. Ekstraksi Macro Upper Line (cari pasangan swing high dengan span lebar >= 12 bar)
    best_u = None
    if len(p_use) >= 2:
        candidates_u = []
        for i in range(len(p_use)):
            for j in range(i + 1, len(p_use)):
                dx = p_use[j]["index"] - p_use[i]["index"]
                if dx >= 12:
                    dy = p_use[j]["price"] - p_use[i]["price"]
                    sl = float(dy / (dx * max(pip_size, 1e-6)))
                    if abs(sl) <= max_slope_pips:
                        score = dx * 100.0 + (p_use[i]["price"] + p_use[j]["price"])
                        candidates_u.append((score, dx, p_use[i], p_use[j], sl))
        if candidates_u:
            candidates_u.sort(key=lambda x: x[0], reverse=True)
            best_u = candidates_u[0]
        elif len(p_use) >= 2:
            p1, p2 = p_use[0], p_use[-1]
            dx = max(p2["index"] - p1["index"], 1)
            dy = p2["price"] - p1["price"]
            sl = float(dy / (dx * max(pip_size, 1e-6)))
            best_u = (dx * 100.0, dx, p1, p2, sl)

    # 3. Ekstraksi Macro Lower Line (cari pasangan swing low dengan span lebar >= 12 bar)
    best_l = None
    if len(t_use) >= 2:
        candidates_l = []
        for i in range(len(t_use)):
            for j in range(i + 1, len(t_use)):
                dx = t_use[j]["index"] - t_use[i]["index"]
                if dx >= 12:
                    dy = t_use[j]["price"] - t_use[i]["price"]
                    sl = float(dy / (dx * max(pip_size, 1e-6)))
                    if abs(sl) <= max_slope_pips:
                        score = dx * 100.0 - (t_use[i]["price"] + t_use[j]["price"])
                        candidates_l.append((score, dx, t_use[i], t_use[j], sl))
        if candidates_l:
            candidates_l.sort(key=lambda x: x[0], reverse=True)
            best_l = candidates_l[0]
        elif len(t_use) >= 2:
            v1, v2 = t_use[0], t_use[-1]
            dx = max(v2["index"] - v1["index"], 1)
            dy = v2["price"] - v1["price"]
            sl = float(dy / (dx * max(pip_size, 1e-6)))
            best_l = (dx * 100.0, dx, v1, v2, sl)

    # 4. Enclosing Parallel Fallback (Jika salah satu sisi ada, tapi sisi lain kosong/kurang span)
    if best_u and not best_l and len(t_use) >= 1:
        v_ext = min(t_use, key=lambda x: x["price"])
        u_p1, u_p2, u_sl = best_u[2], best_u[3], best_u[4]
        v_sec_idx = min(n_bars - 1, v_ext["index"] + max(12, best_u[1]))
        v_sec_price = v_ext["price"] + (u_sl * max(pip_size, 1e-6)) * (v_sec_idx - v_ext["index"])
        v_sec_time = time_vals[v_sec_idx] if v_sec_idx < len(time_vals) else (time_vals[-1] if time_vals else 0)
        v_sec_fake = {"index": v_sec_idx, "price": round(v_sec_price, 5), "time": v_sec_time, "label": "L_par"}
        best_l = (best_u[0], v_sec_idx - v_ext["index"], v_ext, v_sec_fake, u_sl)

    elif best_l and not best_u and len(p_use) >= 1:
        p_ext = max(p_use, key=lambda x: x["price"])
        l_v1, l_v2, l_sl = best_l[2], best_l[3], best_l[4]
        p_sec_idx = min(n_bars - 1, p_ext["index"] + max(12, best_l[1]))
        p_sec_price = p_ext["price"] + (l_sl * max(pip_size, 1e-6)) * (p_sec_idx - p_ext["index"])
        p_sec_time = time_vals[p_sec_idx] if p_sec_idx < len(time_vals) else (time_vals[-1] if time_vals else 0)
        p_sec_fake = {"index": p_sec_idx, "price": round(p_sec_price, 5), "time": p_sec_time, "label": "H_par"}
        best_u = (best_l[0], p_sec_idx - p_ext["index"], p_ext, p_sec_fake, l_sl)

    # 5. Konstruksi Dict Payload
    if best_u:
        _, dx, p1, p2, macro_upper_slope = best_u
        proj_bars = (n_bars - 1) - p2["index"]
        dy_per_bar = (macro_upper_slope * max(pip_size, 1e-6))
        macro_proj_price = p2["price"] + dy_per_bar * proj_bars
        macro_upper_line = {
            "p1": p1,
            "p2": p2,
            "slope_pips": round(macro_upper_slope, 2),
            "proj_price": round(float(macro_proj_price), 5),
            "proj_time": time_vals[-1] if len(time_vals) > 0 else 0,
            "label": f"Macro Upper: {macro_upper_slope:+.1f} p/b ({p1.get('label', 'H')}->{p2.get('label', 'H')})"
        }

    if best_l:
        _, dx, v1, v2, macro_lower_slope = best_l
        proj_bars = (n_bars - 1) - v2["index"]
        dy_per_bar = (macro_lower_slope * max(pip_size, 1e-6))
        macro_proj_price = v2["price"] + dy_per_bar * proj_bars
        macro_lower_line = {
            "p1": v1,
            "p2": v2,
            "slope_pips": round(macro_lower_slope, 2),
            "proj_price": round(float(macro_proj_price), 5),
            "proj_time": time_vals[-1] if len(time_vals) > 0 else 0,
            "label": f"Macro Lower: {macro_lower_slope:+.1f} p/b ({v1.get('label', 'L')}->{v2.get('label', 'L')})"
        }

    # Criss-Cross Ray Guard (Eliminasi garis yang berpotongan menyilang membentuk huruf X)
    if macro_upper_line and macro_lower_line:
        u_p1 = macro_upper_line["p1"]["price"]
        l_p1 = macro_lower_line["p1"]["price"]
        u_proj = macro_upper_line["proj_price"]
        l_proj = macro_lower_line["proj_price"]
        # Plafon makro harus selalu berada di atas lantai makro
        if u_p1 <= l_p1 or u_proj <= l_proj:
            macro_upper_line = {}
            macro_upper_slope = 0.0
            macro_lower_line = {}
            macro_lower_slope = 0.0

    return macro_upper_line, macro_upper_slope, macro_lower_line, macro_lower_slope


def compute_inducement_dealing_range(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    peaks: List[Dict[str, Any]],
    troughs: List[Dict[str, Any]],
    time_vals: List[int],
    cur_atr: float,
    pip_size: float = 0.0001
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """
    Menghitung Dealing Range Sejati berbasis Inducement (HTF SMC) dan
    Order Flow Backbone Trajectory sesuai 'Trade Liquidity Like the Pros':
    
    1. Order Flow Trajectory: Urutan kronologis zigzag dari seluruh swing terkonfirmasi (HH/HL/LH/LL).
    2. Dealing Range:
       - Range High (Buy-Side Liquidity / BSL)
       - Range Low (Sell-Side Liquidity / SSL)
       - 50% Equilibrium (EQ)
       - Discount Zone (< 50%) vs Premium Zone (> 50%)
       - Inducement status: apakah Range High/Low telah terkonfirmasi oleh sapuan internal swing.
    3. Draw on Liquidity (DOL): Target likuiditas eksternal terdekat yang sedang dikejar harga.
    """
    n = len(closes)
    last_close = float(closes[-1]) if n > 0 else 0.0

    # 1. Bangun Urutan Kronologis Zigzag (Order Flow Backbone)
    all_swings = []
    for p in peaks:
        all_swings.append({
            "type": "PEAK",
            "index": p["index"],
            "price": p["price"],
            "time": p.get("time", 0),
            "label": p.get("label", "H")
        })
    for t in troughs:
        all_swings.append({
            "type": "TROUGH",
            "index": t["index"],
            "price": t["price"],
            "time": t.get("time", 0),
            "label": t.get("label", "L")
        })
    all_swings.sort(key=lambda x: x["index"])

    order_flow_segments = []
    for i in range(len(all_swings) - 1):
        s1 = all_swings[i]
        s2 = all_swings[i + 1]
        is_bull_leg = s2["price"] >= s1["price"]
        order_flow_segments.append({
            "from_node": s1,
            "to_node": s2,
            "direction": "BULLISH" if is_bull_leg else "BEARISH",
            "delta_pips": round(float(abs(s2["price"] - s1["price"]) / max(pip_size, 1e-6)), 1)
        })

    # Klasifikasi Rezim Order Flow (dari 2-4 swing terakhir)
    order_flow_regime = "NEUTRAL_FLOW"
    if len(all_swings) >= 3:
        recent_labels = [s["label"] for s in all_swings[-4:]]
        lh_ll_count = sum(1 for l in recent_labels if l in ("LH", "LL"))
        hh_hl_count = sum(1 for l in recent_labels if l in ("HH", "HL"))
        if lh_ll_count >= 2 and lh_ll_count > hh_hl_count:
            order_flow_regime = "BEARISH_ORDER_FLOW"
        elif hh_hl_count >= 2 and hh_hl_count > lh_ll_count:
            order_flow_regime = "BULLISH_ORDER_FLOW"

    # 2. Active SMC Dealing Range Calculation
    # Sesuai ComLucro 'Trade Liquidity Like the Pros':
    # Dealing range diikat pada origin impulse expansion leg yang menghasilkan BOS aktif
    raw_high = None
    raw_low = None
    raw_max_idx = None
    raw_min_idx = None

    if order_flow_regime == "BEARISH_ORDER_FLOW" and troughs:
        recent_lls = [t for t in troughs if t.get("label") == "LL"]
        active_ll = recent_lls[-1] if recent_lls else troughs[-1]
        raw_low = float(active_ll["price"])
        raw_min_idx = int(active_ll["index"])

        prior_peaks = [p for p in peaks if p["index"] < active_ll["index"]]
        if prior_peaks:
            lookback_peaks = [p for p in prior_peaks if p["index"] >= active_ll["index"] - 40]
            active_origin_high = max(lookback_peaks, key=lambda x: x["price"]) if lookback_peaks else prior_peaks[-1]
            raw_high = float(active_origin_high["price"])
            raw_max_idx = int(active_origin_high["index"])

    elif order_flow_regime == "BULLISH_ORDER_FLOW" and peaks:
        recent_hhs = [p for p in peaks if p.get("label") == "HH"]
        active_hh = recent_hhs[-1] if recent_hhs else peaks[-1]
        raw_high = float(active_hh["price"])
        raw_max_idx = int(active_hh["index"])

        prior_troughs = [t for t in troughs if t["index"] < active_hh["index"]]
        if prior_troughs:
            lookback_troughs = [t for t in prior_troughs if t["index"] >= active_hh["index"] - 40]
            active_origin_low = min(lookback_troughs, key=lambda x: x["price"]) if lookback_troughs else prior_troughs[-1]
            raw_low = float(active_origin_low["price"])
            raw_min_idx = int(active_origin_low["index"])

    # Fallback jika belum terisi atau amplitude terlalu sempit (< 0.8 * ATR)
    if raw_high is None or raw_low is None or (raw_high - raw_low) < (0.8 * cur_atr):
        active_window = min(n, 60)
        w_highs = highs[-active_window:] if n > 0 else np.array([last_close * 1.01])
        w_lows = lows[-active_window:] if n > 0 else np.array([last_close * 0.99])
        w_offset = max(0, n - active_window)
        raw_max_idx = int(w_offset + np.argmax(w_highs))
        raw_min_idx = int(w_offset + np.argmin(w_lows))
        raw_high = float(highs[raw_max_idx]) if n > 0 else last_close * 1.01
        raw_low = float(lows[raw_min_idx]) if n > 0 else last_close * 0.99

    # Konfirmasi Inducement Sweep
    high_confirmed = False
    subsequent_troughs = [t for t in troughs if t["index"] > raw_max_idx]
    if len(subsequent_troughs) >= 1:
        high_confirmed = True

    low_confirmed = False
    subsequent_peaks = [p for p in peaks if p["index"] > raw_min_idx]
    if len(subsequent_peaks) >= 1:
        low_confirmed = True

    range_span = max(raw_high - raw_low, 1e-6)
    eq_50 = round((raw_high + raw_low) / 2.0, 5)
    fib_382 = round(raw_low + 0.382 * range_span, 5)
    fib_618 = round(raw_low + 0.618 * range_span, 5)
    dr_pos = float(np.clip((last_close - raw_low) / range_span, 0.0, 1.0))
    dr_pos_pct = round(dr_pos * 100.0, 1)

    # 5-Tier SMC Zone Classification (ComLucro SMC Standard)
    if dr_pos <= 0.382:
        zone_status = "DEEP_DISCOUNT"
    elif dr_pos < 0.500:
        zone_status = "SHALLOW_DISCOUNT_INDUCEMENT"
    elif np.isclose(dr_pos, 0.500, atol=0.01):
        zone_status = "EQUILIBRIUM"
    elif dr_pos < 0.618:
        zone_status = "SHALLOW_PREMIUM_INDUCEMENT"
    else:
        zone_status = "DEEP_PREMIUM"

    # Verifikasi Validitas Range Sesuai Aturan Video:
    # 1. Impulse leg harus memiliki retracement minimal 50% (Equilibrium test)
    # 2. Batas eksternal dikonfirmasi oleh sweep internal inducement
    retraced_to_50 = False
    if len(lows) > 0 and len(highs) > 0:
        if raw_max_idx > raw_min_idx and raw_max_idx < len(lows):
            # Bullish expansion leg: cek apakah setelah puncak ada pullback mencapai <= 50% EQ
            if np.any(lows[raw_max_idx:] <= eq_50):
                retraced_to_50 = True
        elif raw_min_idx > raw_max_idx and raw_min_idx < len(highs):
            # Bearish expansion leg: cek apakah setelah lembah ada pullback mencapai >= 50% EQ
            if np.any(highs[raw_min_idx:] >= eq_50):
                retraced_to_50 = True
        else:
            retraced_to_50 = True

    is_valid_range = bool((high_confirmed or low_confirmed) and retraced_to_50)

    # 3. Draw on Liquidity (DOL)
    if order_flow_regime == "BEARISH_ORDER_FLOW":
        dol_target_price = raw_low
        dol_pool = "SELL_SIDE_LIQUIDITY (SSL)"
        dol_pips = round((last_close - raw_low) / max(pip_size, 1e-6), 1)
        dol_direction = "SEEKING_SSL"
    elif order_flow_regime == "BULLISH_ORDER_FLOW":
        dol_target_price = raw_high
        dol_pool = "BUY_SIDE_LIQUIDITY (BSL)"
        dol_pips = round((raw_high - last_close) / max(pip_size, 1e-6), 1)
        dol_direction = "SEEKING_BSL"
    else:
        if dr_pos > 0.50:
            dol_target_price = raw_low
            dol_pool = "SELL_SIDE_LIQUIDITY (SSL)"
            dol_pips = round((last_close - raw_low) / max(pip_size, 1e-6), 1)
            dol_direction = "ROTATING_TO_SSL"
        else:
            dol_target_price = raw_high
            dol_pool = "BUY_SIDE_LIQUIDITY (BSL)"
            dol_pips = round((raw_high - last_close) / max(pip_size, 1e-6), 1)
            dol_direction = "ROTATING_TO_BSL"

    dealing_range_dict = {
        "range_high": round(raw_high, 5),
        "range_low": round(raw_low, 5),
        "equilibrium_50": eq_50,
        "fib_382": fib_382,
        "fib_618": fib_618,
        "range_span_pips": round(range_span / max(pip_size, 1e-6), 1),
        "dr_position_pct": dr_pos_pct,
        "zone_status": zone_status,
        "high_confirmed": high_confirmed,
        "low_confirmed": low_confirmed,
        "is_valid_range": is_valid_range,
        "high_time": time_vals[raw_max_idx] if raw_max_idx < len(time_vals) else (time_vals[-1] if time_vals else 0),
        "low_time": time_vals[raw_min_idx] if raw_min_idx < len(time_vals) else (time_vals[-1] if time_vals else 0),
    }

    order_flow_dict = {
        "regime": order_flow_regime,
        "swings_count": len(all_swings),
        "recent_swings": all_swings[-5:] if len(all_swings) >= 5 else all_swings,
    }

    draw_on_liquidity_dict = {
        "pool": dol_pool,
        "target_price": round(dol_target_price, 5),
        "distance_pips": dol_pips,
        "direction": dol_direction
    }

    return dealing_range_dict, order_flow_dict, draw_on_liquidity_dict, order_flow_segments


# ----------------------------------------------------------------------------- #
# 5. ENGINE UTAMA: MACRO DYNAMIC ENVELOPE (DUAL-TRACK PIPELINE)
# ----------------------------------------------------------------------------- #

class MacroEnvelopeEngine:
    """
    Engine terpadu untuk evaluasi Dynamic Envelope H4 dan pengenalan pola makro.
    """

    def __init__(
        self,
        window_bars: int = 100,
        savgol_window: int = 7,
        savgol_poly: int = 2,
        confirm_window: int = 3
    ):
        self.window_bars = window_bars
        self.savgol_window = savgol_window
        self.savgol_poly = savgol_poly
        self.confirm_window = confirm_window

    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        point_size: float = 0.0001,
        pip_size: float = 0.0001
    ) -> MacroEnvelopeResult:
        """
        Menjalankan analisis lengkap Decoupled Dual-Track pada DataFrame H4 (100 bar).
        """
        if df is None or len(df) < 25:
            return MacroEnvelopeResult(symbol=symbol)

        # Potong window ke 100 bar terakhir (atau sebanyak data yang ada)
        w = df.iloc[-self.window_bars:].copy()
        n = len(w)

        # 0. Timestamp extraction (100% Vectorized & Timezone-Safe)
        if isinstance(w.index, pd.DatetimeIndex):
            time_vals = (w.index.values.astype('datetime64[s]').astype('int64')).tolist()
        elif "time" in w.columns:
            t_col = w["time"]
            try:
                time_vals = (pd.to_datetime(t_col).values.astype('datetime64[s]').astype('int64')).tolist()
            except Exception:
                if len(t_col) > 0 and isinstance(t_col.iloc[0], (int, float, np.integer, np.floating)):
                    time_vals = [int(x) if x > 1e6 else int(x * 1000) for x in t_col]
                else:
                    time_vals = [0] * n
        else:
            base_ts = int(datetime.now(WIB).timestamp()) - (n * 14400)
            time_vals = [base_ts + (i * 14400) for i in range(n)]

        # 1. Kalkulasi ATR 14 (Pure NumPy cumsum for sub-millisecond execution)
        h_arr = w["high"].to_numpy(dtype=float)
        l_arr = w["low"].to_numpy(dtype=float)
        c_arr = w["close"].to_numpy(dtype=float)
        o_arr = w["open"].to_numpy(dtype=float)

        tr = np.maximum(
            h_arr[1:] - l_arr[1:],
            np.maximum(np.abs(h_arr[1:] - c_arr[:-1]), np.abs(l_arr[1:] - c_arr[:-1]))
        )
        tr_full = np.insert(tr, 0, tr[0] if len(tr) > 0 else 0.002)
        if len(tr_full) >= 14:
            cs = np.cumsum(tr_full)
            atr_vals = np.zeros(n, dtype=float)
            atr_vals[:14] = cs[:14] / np.arange(1, 15)
            atr_vals[14:] = (cs[14:] - cs[:-14]) / 14.0
        else:
            atr_vals = np.full(n, 25.0 * point_size, dtype=float)

        w_clean = clean_outliers_and_rollover(w, atr_vals, symbol=symbol, o=o_arr, h=h_arr, l=l_arr, c=c_arr)

        o = o_arr
        h_clean = w_clean["clean_high"].to_numpy(dtype=float)
        l_clean = w_clean["clean_low"].to_numpy(dtype=float)
        c = c_arr
        body_top = np.maximum(o, c)
        body_bot = np.minimum(o, c)

        last_price = float(c[-1])
        cur_atr = float(atr_vals[-1]) if atr_vals[-1] > 0 else (20.0 * point_size)

        # ------------------------------------------------------------- #
        # TRACK A: CAUSAL QUANT DECISION ENGINE (100% Anti-Repaint)
        # ------------------------------------------------------------- #
        peaks, troughs, has_provisional = extract_causal_pivots(
            h_clean, l_clean, n_confirm=self.confirm_window, time_vals=time_vals, cur_atr=cur_atr
        )
        structural_trend = classify_structural_trend(peaks, troughs)
        provisional_state = "PROVISIONAL_PENDING" if has_provisional else "CONFIRMED"

        # Wick Rejection / Absorption Matrix (10-bar accumulation)
        upper_wicks = h_clean - body_top
        lower_wicks = body_bot - l_clean
        rho_reject = upper_wicks / np.maximum(atr_vals, 1e-6)
        rho_absorb = lower_wicks / np.maximum(atr_vals, 1e-6)

        window_wick = min(10, n)
        recent_reject = float(np.sum(rho_reject[-window_wick:]))
        recent_absorb = float(np.sum(rho_absorb[-window_wick:]))
        net_wick_delta = recent_absorb - recent_reject

        # ------------------------------------------------------------- #
        # TRACK B: VISUAL MANIFOLD & STRUCTURAL SWING RAYS
        # ------------------------------------------------------------- #
        # Pure NumPy rolling extremum filter (window 3)
        top_lag1 = np.insert(body_top[:-1], 0, body_top[0])
        top_lag2 = np.insert(body_top[:-2], 0, [body_top[0], body_top[0]])
        u_body_raw = np.maximum(body_top, np.maximum(top_lag1, top_lag2))

        bot_lag1 = np.insert(body_bot[:-1], 0, body_bot[0])
        bot_lag2 = np.insert(body_bot[:-2], 0, [body_bot[0], body_bot[0]])
        l_body_raw = np.minimum(body_bot, np.minimum(bot_lag1, bot_lag2))

        h_lag1 = np.insert(h_clean[:-1], 0, h_clean[0])
        h_lag2 = np.insert(h_clean[:-2], 0, [h_clean[0], h_clean[0]])
        u_wick_raw = np.maximum(h_clean, np.maximum(h_lag1, h_lag2))

        l_lag1 = np.insert(l_clean[:-1], 0, l_clean[0])
        l_lag2 = np.insert(l_clean[:-2], 0, [l_clean[0], l_clean[0]])
        l_wick_raw = np.minimum(l_clean, np.minimum(l_lag1, l_lag2))

        # Savitzky-Golay Smoothing
        u_body_smooth = savgol_smooth(u_body_raw, self.savgol_window, self.savgol_poly, deriv=0)
        l_body_smooth = savgol_smooth(l_body_raw, self.savgol_window, self.savgol_poly, deriv=0)
        u_wick_smooth = savgol_smooth(u_wick_raw, self.savgol_window, self.savgol_poly, deriv=0)
        l_wick_smooth = savgol_smooth(l_wick_raw, self.savgol_window, self.savgol_poly, deriv=0)

        # Pastikan batas envelope konsisten
        u_body_smooth = np.maximum(u_body_smooth, l_body_smooth + (0.05 * cur_atr))
        u_wick_smooth = np.maximum(u_wick_smooth, u_body_smooth)
        l_wick_smooth = np.minimum(l_wick_smooth, l_body_smooth)

        # Hitung slope & curvature pada midline envelope
        midline = (u_body_smooth + l_body_smooth) / 2.0
        slope_raw = savgol_smooth(midline, self.savgol_window, self.savgol_poly, deriv=1)
        curvature_raw = savgol_smooth(midline, self.savgol_window, self.savgol_poly, deriv=2)

        inst_slope = float(slope_raw[-1] / max(pip_size, 1e-6))
        curvature = float(curvature_raw[-1] / max(pip_size, 1e-6))

        # Posisi internal tau (0.0 s.d. 1.0)
        env_top = float(u_body_smooth[-1])
        env_bot = float(l_body_smooth[-1])
        env_width = max(env_top - env_bot, 1e-6)
        tau = float(np.clip((last_price - env_bot) / env_width, 0.0, 1.0))

        # Clearance runway
        clearance_up = float(max(0.0, (env_top - last_price) / max(pip_size, 1e-6)))
        clearance_down = float(max(0.0, (last_price - env_bot) / max(pip_size, 1e-6)))

        # ------------------------------------------------------------- #
        # TRACK C: STRUCTURAL SWING TRENDLINES & SLOPE TELEMETRY
        # ------------------------------------------------------------- #
        upper_line = {}
        upper_slope = 0.0
        if len(peaks) >= 2:
            p1 = peaks[-2]
            p2 = peaks[-1]
            dx_bars = max(p2["index"] - p1["index"], 1)
            dy_price = p2["price"] - p1["price"]
            upper_slope = float(dy_price / (dx_bars * max(pip_size, 1e-6)))
            proj_bars = (n - 1) - p2["index"]
            upper_proj_price = p2["price"] + (dy_price / dx_bars) * proj_bars
            upper_line = {
                "p1": p1,
                "p2": p2,
                "slope_pips": round(upper_slope, 2),
                "proj_price": round(float(upper_proj_price), 5),
                "proj_time": time_vals[-1] if len(time_vals) > 0 else 0,
                "label": f"Upper Slope: {upper_slope:+.1f} p/b ({p2.get('label', 'H')})"
            }

        lower_line = {}
        lower_slope = 0.0
        if len(troughs) >= 2:
            v1 = troughs[-2]
            v2 = troughs[-1]
            dx_bars = max(v2["index"] - v1["index"], 1)
            dy_price = v2["price"] - v1["price"]
            lower_slope = float(dy_price / (dx_bars * max(pip_size, 1e-6)))
            proj_bars = (n - 1) - v2["index"]
            lower_proj_price = v2["price"] + (dy_price / dx_bars) * proj_bars
            lower_line = {
                "p1": v1,
                "p2": v2,
                "slope_pips": round(lower_slope, 2),
                "proj_price": round(float(lower_proj_price), 5),
                "proj_time": time_vals[-1] if len(time_vals) > 0 else 0,
                "label": f"Lower Slope: {lower_slope:+.1f} p/b ({v2.get('label', 'L')})"
            }

        # Ekstraksi Garis Tren Makro Horizon Jauh (Multi-Scale Macro Swings & Enclosing Alignment)
        macro_upper_line, macro_upper_slope, macro_lower_line, macro_lower_slope = _extract_macro_trendlines(
            peaks=peaks,
            troughs=troughs,
            n_bars=n,
            pip_size=pip_size,
            time_vals=time_vals,
            highs=h_clean,
            lows=l_clean,
            cur_atr=cur_atr
        )

        all_upper_segments = []
        for i in range(len(peaks) - 1):
            pk1 = peaks[i]
            pk2 = peaks[i+1]
            db = max(pk2["index"] - pk1["index"], 1)
            sl = float((pk2["price"] - pk1["price"]) / (db * max(pip_size, 1e-6)))
            all_upper_segments.append({
                "p1": pk1,
                "p2": pk2,
                "slope_pips": round(sl, 2)
            })

        all_lower_segments = []
        for i in range(len(troughs) - 1):
            tr1 = troughs[i]
            tr2 = troughs[i+1]
            db = max(tr2["index"] - tr1["index"], 1)
            sl = float((tr2["price"] - tr1["price"]) / (db * max(pip_size, 1e-6)))
            all_lower_segments.append({
                "p1": tr1,
                "p2": tr2,
                "slope_pips": round(sl, 2)
            })

        # ------------------------------------------------------------- #
        # TRACK D: GEOMETRIC PATTERN CLASSIFIER & MEASURED MOVE TARGET
        # ------------------------------------------------------------- #
        # Horizon Dekat (Tactical Span 15-30 Bar)
        geom_pat = detect_geometric_patterns(
            peaks=peaks,
            troughs=troughs,
            upper_slope=upper_slope,
            lower_slope=lower_slope,
            highs=h_clean,
            lows=l_clean,
            closes=c,
            cur_atr=cur_atr,
            pip_size=pip_size,
            structural_trend=structural_trend
        )
        pattern_display_label = f"{geom_pat.name} [{geom_pat.status}]" if geom_pat.name != "NONE" else structural_trend
        measured_target_pips = geom_pat.target_pips

        # Horizon Jauh (Macro Span 40-100 Bar)
        macro_geom_pat = detect_geometric_patterns(
            peaks=peaks,
            troughs=troughs,
            upper_slope=macro_upper_slope,
            lower_slope=macro_lower_slope,
            highs=h_clean,
            lows=l_clean,
            closes=c,
            cur_atr=cur_atr,
            pip_size=pip_size,
            structural_trend=structural_trend
        )

        u_body_round = np.round(u_body_smooth, 5).tolist()
        l_body_round = np.round(l_body_smooth, 5).tolist()
        u_wick_round = np.round(u_wick_smooth, 5).tolist()
        l_wick_round = np.round(l_wick_smooth, 5).tolist()

        # ------------------------------------------------------------- #
        # TRACK E: HTF INDUCEMENT DEALING RANGE & ORDER FLOW BACKBONE
        # ------------------------------------------------------------- #
        dr_dict, of_dict, dol_dict, of_segments = compute_inducement_dealing_range(
            highs=h_clean,
            lows=l_clean,
            closes=c,
            peaks=peaks,
            troughs=troughs,
            time_vals=time_vals,
            cur_atr=cur_atr,
            pip_size=pip_size
        )

        visual_payload = {
            "upper_body": [{"time": t, "value": v} for t, v in zip(time_vals, u_body_round)],
            "lower_body": [{"time": t, "value": v} for t, v in zip(time_vals, l_body_round)],
            "upper_wick": [{"time": t, "value": v} for t, v in zip(time_vals, u_wick_round)],
            "lower_wick": [{"time": t, "value": v} for t, v in zip(time_vals, l_wick_round)],
            "dealing_range": dr_dict,
            "order_flow": of_dict,
            "draw_on_liquidity": dol_dict,
            "order_flow_segments": of_segments,
            "swing_structure": {
                "peaks": peaks,
                "troughs": troughs,
                "upper_line": upper_line,
                "lower_line": lower_line,
                "macro_upper_line": macro_upper_line,
                "macro_lower_line": macro_lower_line,
                "all_upper_segments": all_upper_segments,
                "all_lower_segments": all_lower_segments,
                "order_flow_segments": of_segments,
                "dealing_range": dr_dict,
                "order_flow": of_dict,
                "draw_on_liquidity": dol_dict,
                "pattern_name": structural_trend,
                "geometric_pattern": geom_pat.to_dict(),
                "macro_pattern": macro_geom_pat.to_dict(),
                "pattern_display_label": pattern_display_label,
                "measured_target_pips": measured_target_pips,
                "upper_slope": round(upper_slope, 2),
                "lower_slope": round(lower_slope, 2),
                "macro_upper_slope": round(macro_upper_slope, 2),
                "macro_lower_slope": round(macro_lower_slope, 2),
            }
        }

        return MacroEnvelopeResult(
            symbol=symbol,
            timeframe="H4",
            structural_trend=structural_trend,
            instantaneous_slope=round(inst_slope, 2),
            curvature=round(curvature, 4),
            channel_position_tau=round(tau, 3),
            net_wick_delta=round(net_wick_delta, 2),
            recent_rejection_score=round(recent_reject, 2),
            recent_absorption_score=round(recent_absorb, 2),
            clearance_up_pips=round(clearance_up, 1),
            clearance_down_pips=round(clearance_down, 1),
            envelope_upper=round(env_top, 5),
            envelope_lower=round(env_bot, 5),
            envelope_wick_upper=round(float(u_wick_smooth[-1]), 5),
            envelope_wick_lower=round(float(l_wick_smooth[-1]), 5),
            upper_slope=round(upper_slope, 2),
            lower_slope=round(lower_slope, 2),
            macro_upper_slope=round(macro_upper_slope, 2),
            macro_lower_slope=round(macro_lower_slope, 2),
            provisional_state=provisional_state,
            confirmed_peaks=peaks,
            confirmed_troughs=troughs,
            geometric_pattern=geom_pat.to_dict(),
            macro_pattern=macro_geom_pat.to_dict(),
            pattern_display_label=pattern_display_label,
            measured_target_pips=measured_target_pips,
            dealing_range=dr_dict,
            order_flow=of_dict,
            draw_on_liquidity=dol_dict,
            visual_payload=visual_payload
        )

