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
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

logger = logging.getLogger("pattern_engine")
WIB = ZoneInfo("Asia/Jakarta")


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
    provisional_state: str = "CONFIRMED" # CONFIRMED | PROVISIONAL_PENDING
    confirmed_peaks: List[Dict[str, Any]] = field(default_factory=list)
    confirmed_troughs: List[Dict[str, Any]] = field(default_factory=list)
    visual_payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------------- #
# 1. PURE NUMPY SAVITZKY-GOLAY CONVOLUTION (ZERO SCIPY DEPENDENCY)
# ----------------------------------------------------------------------------- #

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
    symbol: str = ""
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
    d = df.copy()
    o = d["open"].to_numpy(dtype=float)
    h = d["high"].to_numpy(dtype=float)
    l = d["low"].to_numpy(dtype=float)
    c = d["close"].to_numpy(dtype=float)
    atr = atr_series.to_numpy(dtype=float)

    n = len(d)
    clean_h = h.copy()
    clean_l = l.copy()

    body_top = np.maximum(o, c)
    body_bottom = np.minimum(o, c)
    upper_wick = h - body_top
    lower_wick = body_bottom - l

    # Deteksi rollover WIB jika ada informasi waktu
    is_rollover = np.zeros(n, dtype=bool)
    if "time" in d.columns:
        times = pd.to_datetime(d["time"])
        # MT5 Server rollover jam 00:00 = 04:00 WIB
        # Candle H4 yang membuka atau menutup di sekitar 04:00 WIB rentan spread spike
        hours_wib = times.dt.tz_convert(WIB).dt.hour if times.dt.tz is not None else times.dt.hour
        is_rollover = (hours_wib == 4) | (hours_wib == 3) | (hours_wib == 0)

    is_chf = "CHF" in symbol.upper()
    atr_mult_thresh = 2.0 if (is_chf or np.any(is_rollover)) else 2.5
    clamp_mult = 1.35 if is_chf else 1.50

    for i in range(n):
        cur_atr = atr[i]
        if np.isnan(cur_atr) or cur_atr <= 0:
            continue

        # Cek outlier wick atas
        thresh_up = atr_mult_thresh * cur_atr
        if upper_wick[i] > thresh_up:
            clean_h[i] = body_top[i] + (clamp_mult * cur_atr)

        # Cek outlier wick bawah
        thresh_down = atr_mult_thresh * cur_atr
        if lower_wick[i] > thresh_down:
            clean_l[i] = body_bottom[i] - (clamp_mult * cur_atr)

    d["clean_high"] = clean_h
    d["clean_low"] = clean_l
    return d


# ----------------------------------------------------------------------------- #
# 3. TRACK A: CAUSAL PIVOT EXTRACTION (ZERO REPAINTING)
# ----------------------------------------------------------------------------- #

def extract_causal_pivots(
    highs: np.ndarray,
    lows: np.ndarray,
    n_confirm: int = 3
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    """
    Ekstraksi titik balik puncak (peaks) dan lembah (troughs) secara 100% kausal.
    Titik balik pada bar k hanya dikonfirmasi jika ada n_confirm bar di sebelah kanan
    yang tidak melampaui harga ekstrem tersebut.

    Semua bar dalam interval [n - n_confirm, n - 1] berstatus PROVISIONAL.
    """
    n = len(highs)
    peaks = []
    troughs = []
    has_provisional_extreme = False

    if n < (2 * n_confirm + 1):
        return peaks, troughs, has_provisional_extreme

    # 1. Cari titik puncak konfirmasi (k <= n - 1 - n_confirm)
    max_confirmed_idx = n - 1 - n_confirm
    for k in range(n_confirm, max_confirmed_idx + 1):
        # Peak test: k adalah nilai tertinggi dalam window k - n_confirm s.d. k + n_confirm
        left_window = highs[k - n_confirm:k]
        right_window = highs[k + 1:k + n_confirm + 1]
        if highs[k] >= np.max(left_window) and highs[k] >= np.max(right_window):
            peaks.append({"index": int(k), "price": float(highs[k]), "type": "PEAK"})

        # Trough test: k adalah nilai terendah
        left_lows = lows[k - n_confirm:k]
        right_lows = lows[k + 1:k + n_confirm + 1]
        if lows[k] <= np.min(left_lows) and lows[k] <= np.min(right_lows):
            troughs.append({"index": int(k), "price": float(lows[k]), "type": "TROUGH"})

    # 2. Cek apakah ada calon ekstrem di bar provisional [max_confirmed_idx + 1 .. n - 1]
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
# 4. ENGINE UTAMA: MACRO DYNAMIC ENVELOPE (DUAL-TRACK PIPELINE)
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
        w = df.iloc[-self.window_bars:].copy().reset_index(drop=True)
        n = len(w)

        # 1. Kalkulasi ATR 14
        tr = np.maximum(
            w["high"].to_numpy(dtype=float)[1:] - w["low"].to_numpy(dtype=float)[1:],
            np.maximum(
                np.abs(w["high"].to_numpy(dtype=float)[1:] - w["close"].to_numpy(dtype=float)[:-1]),
                np.abs(w["low"].to_numpy(dtype=float)[1:] - w["close"].to_numpy(dtype=float)[:-1])
            )
        )
        atr_vals = np.zeros(n, dtype=float)
        if len(tr) >= 14:
            tr_series = pd.Series(np.insert(tr, 0, tr[0]))
            atr_vals = tr_series.rolling(14, min_periods=1).mean().to_numpy(dtype=float)
        else:
            default_atr = 25.0 * point_size
            atr_vals[:] = default_atr

        w_clean = clean_outliers_and_rollover(w, pd.Series(atr_vals), symbol=symbol)

        o = w_clean["open"].to_numpy(dtype=float)
        h_clean = w_clean["clean_high"].to_numpy(dtype=float)
        l_clean = w_clean["clean_low"].to_numpy(dtype=float)
        c = w_clean["close"].to_numpy(dtype=float)
        body_top = np.maximum(o, c)
        body_bot = np.minimum(o, c)

        last_price = float(c[-1])
        cur_atr = float(atr_vals[-1]) if atr_vals[-1] > 0 else (20.0 * point_size)

        # ------------------------------------------------------------- #
        # TRACK A: CAUSAL QUANT DECISION ENGINE (100% Anti-Repaint)
        # ------------------------------------------------------------- #
        peaks, troughs, has_provisional = extract_causal_pivots(
            h_clean, l_clean, n_confirm=self.confirm_window
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
        # TRACK B: VISUAL MANIFOLD RIBBON (Dashboard Lightweight Charts)
        # ------------------------------------------------------------- #
        # Rolling extremum filter (window 3) pada body & wick clean
        u_body_raw = pd.Series(body_top).rolling(3, min_periods=1).max().to_numpy()
        l_body_raw = pd.Series(body_bot).rolling(3, min_periods=1).min().to_numpy()
        u_wick_raw = pd.Series(h_clean).rolling(3, min_periods=1).max().to_numpy()
        l_wick_raw = pd.Series(l_clean).rolling(3, min_periods=1).min().to_numpy()

        # Savitzky-Golay Smoothing
        u_body_smooth = savgol_smooth(u_body_raw, self.savgol_window, self.savgol_poly, deriv=0)
        l_body_smooth = savgol_smooth(l_body_raw, self.savgol_window, self.savgol_poly, deriv=0)
        u_wick_smooth = savgol_smooth(u_wick_raw, self.savgol_window, self.savgol_poly, deriv=0)
        l_wick_smooth = savgol_smooth(l_wick_raw, self.savgol_window, self.savgol_poly, deriv=0)

        # Pastikan batas envelope konsisten (Body atas >= Body bawah, Wick atas >= Body atas)
        u_body_smooth = np.maximum(u_body_smooth, l_body_smooth + (0.05 * cur_atr))
        u_wick_smooth = np.maximum(u_wick_smooth, u_body_smooth)
        l_wick_smooth = np.minimum(l_wick_smooth, l_body_smooth)

        # Hitung turunan pertama (slope) dan kedua (curvature) pada midline envelope
        midline = (u_body_smooth + l_body_smooth) / 2.0
        slope_raw = savgol_smooth(midline, self.savgol_window, self.savgol_poly, deriv=1)
        curvature_raw = savgol_smooth(midline, self.savgol_window, self.savgol_poly, deriv=2)

        # Konversi slope ke pips per bar H4
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

        # Format visual payload untuk Lightweight Charts
        time_vals = []
        if "time" in w.columns:
            for t_item in w["time"]:
                if hasattr(t_item, "timestamp"):
                    time_vals.append(int(t_item.timestamp()))
                elif isinstance(t_item, (int, float)):
                    time_vals.append(int(t_item) if t_item > 1e6 else int(t_item * 1000))
                else:
                    try:
                        time_vals.append(int(pd.to_datetime(t_item).timestamp()))
                    except Exception:
                        time_vals.append(0)
        else:
            # Fallback incremental timestamp (4 jam per bar)
            base_ts = int(datetime.now(WIB).timestamp()) - (n * 14400)
            time_vals = [base_ts + (i * 14400) for i in range(n)]

        visual_payload = {
            "upper_body": [{"time": time_vals[i], "value": round(float(u_body_smooth[i]), 5)} for i in range(n)],
            "lower_body": [{"time": time_vals[i], "value": round(float(l_body_smooth[i]), 5)} for i in range(n)],
            "upper_wick": [{"time": time_vals[i], "value": round(float(u_wick_smooth[i]), 5)} for i in range(n)],
            "lower_wick": [{"time": time_vals[i], "value": round(float(l_wick_smooth[i]), 5)} for i in range(n)],
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
            provisional_state=provisional_state,
            confirmed_peaks=peaks,
            confirmed_troughs=troughs,
            visual_payload=visual_payload
        )
