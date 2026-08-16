"""
pattern_detector.py — Runtime Pattern Edge Detector & Whisper Generator

Mendeteksi pola candlestick bearish/bullish di candle terakhir (sudah close) dan
mencocokkannya dengan registry EDGE tervalidasi (dari riset `scratch/pattern_research.py`).

Hanya menghasilkan "whisper" (statistik historis) — INFORMATIONAL ONLY, bukan
directive. Kalau tidak ada pola yang match registry -> return None (tanpa biaya).

Logika deteksi MIRROR PERSIS `scratch/pattern_research.py` (definisi pin bar,
engulfing, inside bar, sweep, sesi WIB, S/R proximity, multi-pattern) supaya
statistik yang dibisiki benar-benar berlaku di runtime.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

WIB = ZoneInfo("Asia/Jakarta")

# Definisi pola (sama dengan scratch/pattern_research.py)
SWING_WINDOW = 20
ATR_PERIOD = 14
PROXIMITY_ATR_MULT = 0.5   # dekat S/R = jarak <= 0.5 ATR
MULTI_PATTERN_BARS = 3     # 2+ pola searah dalam 3 bar

# Kondisi sesi WIB (sama dengan riset pattern_research.py: ny menang di 20-24
# karena di-set terakhir setelah london)
def _session_wib(ts) -> str:
    hour = ts.hour
    if hour >= 20 or hour < 5:
        return "ny"
    if 7 <= hour < 16:
        return "asia"
    if 15 <= hour < 24:
        return "london"
    return "other"


# ---------------- Deteksi pola (vectorized, sama dengan riset) ----------------

def _detect_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Tambah kolom boolean pola (sama persis definisi pattern_research.py)."""
    rng = df["high"] - df["low"]
    body = (df["close"] - df["open"]).abs()
    upper_shadow = df["high"] - df[["open", "close"]].max(axis=1)
    lower_shadow = df[["open", "close"]].min(axis=1) - df["low"]

    df["bullish_pinbar"] = (lower_shadow >= 0.6 * rng) & (body <= 0.25 * rng) & (rng > 0)
    df["bearish_pinbar"] = (upper_shadow >= 0.6 * rng) & (body <= 0.25 * rng) & (rng > 0)

    body_prev = df["close"].shift(1) - df["open"].shift(1)
    body_curr = df["close"] - df["open"]
    df["bullish_engulfing"] = (body_prev < 0) & (body_curr > 0) & (df["open"] <= df["close"].shift(1)) & (df["close"] >= df["open"].shift(1))
    df["bearish_engulfing"] = (body_prev > 0) & (body_curr < 0) & (df["open"] >= df["close"].shift(1)) & (df["close"] <= df["open"].shift(1))

    inside = (df["high"] < df["high"].shift(1)) & (df["low"] > df["low"].shift(1))
    mid_prev = (df["high"].shift(1) + df["low"].shift(1)) / 2
    df["inside_bull"] = inside & (df["close"] > mid_prev)
    df["inside_bear"] = inside & (df["close"] <= mid_prev)

    # Swing high/low 20 (shift 1 — tanpa look-ahead)
    df["swing_high_20"] = df["high"].shift(1).rolling(SWING_WINDOW).max()
    df["swing_low_20"] = df["low"].shift(1).rolling(SWING_WINDOW).min()
    df["bullish_sweep"] = (df["low"] < df["swing_low_20"]) & (df["close"] > df["swing_low_20"])
    df["bearish_sweep"] = (df["high"] > df["swing_high_20"]) & (df["close"] < df["swing_high_20"])

    # ATR 14
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift(1)).abs(),
        (df["low"] - df["close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()

    return df


def _multi_pattern(df: pd.DataFrame, is_bull: bool) -> bool:
    """2+ pola searah dalam 3 bar terakhir (termasuk bar ini)."""
    bull_cols = ["bullish_pinbar", "bullish_engulfing", "bullish_sweep", "inside_bull"]
    bear_cols = ["bearish_pinbar", "bearish_engulfing", "bearish_sweep", "inside_bear"]
    cols = bull_cols if is_bull else bear_cols
    tail = df[cols].tail(MULTI_PATTERN_BARS)
    return int(tail.sum().sum()) >= 2


# ---------------- Registry ----------------

class WhisperRegistry:
    """Database EDGE tervalidasi. Key: (symbol, pattern_label, condition)."""

    def __init__(self, data: list[dict]):
        self._entries = []
        self._by_key = {}
        for e in data:
            key = (e["symbol"], e["pattern"], e["condition"])
            self._by_key[key] = e
            self._entries.append(e)

    @classmethod
    def from_json(cls, path: str) -> "WhisperRegistry":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def lookup(self, symbol: str, pattern_label: str, condition: str) -> dict | None:
        return self._by_key.get((symbol, pattern_label, condition))

    def __len__(self):
        return len(self._entries)


# Registry di-load dari file JSON (di samping modul ini)
_REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "whisper_registry.json")
_registry: WhisperRegistry | None = None


def get_registry() -> WhisperRegistry | None:
    global _registry
    if _registry is None:
        try:
            _registry = WhisperRegistry.from_json(_REGISTRY_PATH)
        except Exception:
            _registry = None
    return _registry


# ---------------- Whisper builder ----------------

def detect_and_whisper(df: pd.DataFrame, symbol: str) -> str | None:
    """Deteksi pola di candle terakhir & match registry. Return whisper_str atau None.

    df: 50 candle terakhir (SUDAH close), kolom open/high/low/close + index waktu.
    """
    if df is None or len(df) < SWING_WINDOW + 5:
        return None

    registry = get_registry()
    if registry is None or len(registry) == 0:
        return None

    # Hitung pola (copy biar nggak mutasi df pemanggil)
    d = _detect_candle_patterns(df.copy())

    last = d.iloc[-1]
    atr = last["atr"]
    if pd.isna(atr) or atr <= 0:
        return None

    ts = d.index[-1]
    session = _session_wib(ts)
    near_res = abs(last["close"] - last["swing_high_20"]) <= PROXIMITY_ATR_MULT * atr if not pd.isna(last["swing_high_20"]) else False
    near_sup = abs(last["close"] - last["swing_low_20"]) <= PROXIMITY_ATR_MULT * atr if not pd.isna(last["swing_low_20"]) else False

    # Kandidat kondisi (urutan prioritas: kondisi paling spesifik dulu)
    pattern_candidates = []

    # Hanya pola yang ADA di registry yang dicek (hemat)
    for label, col, is_bull in [
        ("Bearish Sweep", "bearish_sweep", False),
        ("Bullish Sweep", "bullish_sweep", True),
        ("Bearish Engulfing", "bearish_engulfing", False),
        ("Bullish Engulfing", "bullish_engulfing", True),
        ("Inside Bar (Bear)", "inside_bear", False),
        ("Inside Bar (Bull)", "inside_bull", True),
        ("Bearish Pin Bar", "bearish_pinbar", False),
        ("Bullish Pin Bar", "bullish_pinbar", True),
    ]:
        if bool(last[col]):
            conds = {}
            if session != "other":
                conds[f"session={session}"] = True
            conds["ALL"] = True
            if near_res:
                conds["near_resistance"] = True
            if near_sup:
                conds["near_support"] = True
            if _multi_pattern(d, is_bull):
                conds["multi_pattern"] = True
            pattern_candidates.append((label, is_bull, conds))

    # Match ke registry: coba kondisi paling kuat dulu (riset: NY EV tertinggi)
    for label, is_bull, conds in pattern_candidates:
        # Prioritas: session NY/London (edge terkuat) > near S/R > multi > ALL
        session_cond = f"session={session}" if session != "other" else None
        for cond in ([session_cond] if session_cond else []) + \
                    ["near_resistance", "near_support", "multi_pattern", "ALL"]:
            if cond in conds:
                entry = registry.lookup(symbol, label, cond)
                if entry:
                    return _format_whisper(entry)

    return None


def _format_whisper(e: dict) -> str:
    """Format blok prompt dari entry registry."""
    cond_label = e["condition"]
    cond_map = {
        "session=ny": "New York session",
        "session=london": "London session",
        "session=asia": "Asia session",
        "near_resistance": "near resistance",
        "near_support": "near support",
        "multi_pattern": "multi-pattern confluence",
        "ALL": "all conditions",
    }
    cond_txt = cond_map.get(cond_label, cond_label)
    rr = float(e["rr"])
    return (
        f"### PATTERN RESEARCH STATS (HISTORICAL BACKTEST DATA)\n"
        f"Detected: {e['pattern']} on {e['symbol']} during {cond_txt}.\n"
        f"Validated backtest (n={e['n']}, 2yr): Win rate {e['wr']*100:.1f}% at R:R 1:{rr:.0f}, "
        f"EV +{e['ev']:.2f} (95% CI [{e['ev_ci_low']:.2f}, {e['ev_ci_high']:.2f}]).\n"
        f"(Historical probability context only - NOT a directive, NOT a rule. "
        f"Do not anchor to it blindly; the final decision is yours.)\n"
    )
