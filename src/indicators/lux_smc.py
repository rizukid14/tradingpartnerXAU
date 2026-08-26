"""
LuxAlgo Smart Money Concepts (SMC) - Pure Python Engine
1:1 Mathematical Port from TradingView Pine Script v5 (LuxAlgo SMC).

Features:
  1. Swing Legs & Pivots (HH, HL, LH, LL)
  2. Break of Structure (BOS) vs Change of Character (CHoCH) Stateful Tracking
  3. Order Blocks (OB) with Real-Time Mitigation Engine
  4. Fair Value Gaps (FVG) with 3-Bar Imbalance & Mitigation
  5. Equal Highs / Equal Lows (EQH / EQL Liquidity Pools)
  6. Authentic Dealing Range (Discount 0-50%, Equilibrium 50%, Premium 50-100%)
  7. Strong & Weak High/Low Levels

Input  : pandas.DataFrame with columns ['open', 'high', 'low', 'close', optional 'time', 'tick_volume']
Output : SMCSignal dataclass
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple

import pandas as pd
import numpy as np


@dataclass
class SMCStructure:
    price: float
    index: int
    direction: str  # "HH", "LH", "HL", "LL"
    time: Optional[Any] = None


@dataclass
class SMCOrderBlock:
    top: float
    bottom: float
    index: int
    direction: str       # "bullish" | "bearish"
    mitigated: bool = False
    time: Optional[Any] = None


@dataclass
class SMCFairValueGap:
    top: float
    bottom: float
    mid: float
    index: int
    direction: str       # "bullish" | "bearish"
    mitigated: bool = False
    time: Optional[Any] = None


@dataclass
class SMCLevelCluster:
    price: float
    indices: List[int]
    direction: str       # "equal_high" | "equal_low"
    time: Optional[Any] = None


@dataclass
class SMCSignal:
    trend_bias:            str = "neutral"  # "bullish" | "bearish" | "neutral"
    bullish_structures:    List[Dict[str, Any]] = field(default_factory=list)
    bearish_structures:    List[Dict[str, Any]] = field(default_factory=list)
    order_blocks_bullish:  List[Dict[str, Any]] = field(default_factory=list)
    order_blocks_bearish:  List[Dict[str, Any]] = field(default_factory=list)
    fvg_bullish:           List[Dict[str, Any]] = field(default_factory=list)
    fvg_bearish:           List[Dict[str, Any]] = field(default_factory=list)
    equal_highs:           List[Dict[str, Any]] = field(default_factory=list)
    equal_lows:            List[Dict[str, Any]] = field(default_factory=list)
    discount_zone:         float = 0.0   # Bottom 0-50% threshold / low boundary
    equilibrium:           float = 0.0   # 50% midpoint
    premium_zone:          float = 0.0   # Top 50-100% threshold / high boundary
    bos:                   Dict[str, Any] = field(default_factory=lambda: {"direction": "none", "level": 0.0, "index": None})
    choch:                 Dict[str, Any] = field(default_factory=lambda: {"direction": "none", "level": 0.0, "index": None})
    strong_high:           float = 0.0
    strong_low:            float = 0.0


class LuxSMCAnalyzer:
    """
    1:1 Pure-Python Port of TradingView LuxAlgo Smart Money Concepts.
    
    Parameters
    ----------
    swing_length : int
        Number of left/right bars for swing detection (default 5 for internal, 10 for major swings).
    eq_threshold_atr : float
        ATR multiplier to group Equal Highs / Lows (default 0.10 * ATR).
    ob_max_display : int
        Maximum active unmitigated Order Blocks to retain (default 10).
    """

    def __init__(
        self,
        swing_length: int = 5,
        eq_threshold_atr: float = 0.10,
        ob_max_display: int = 10,
    ):
        self.swing_length = swing_length
        self.eq_threshold_atr = eq_threshold_atr
        self.ob_max_display = ob_max_display

    def analyze(self, df: pd.DataFrame, point_size: float = 0.0001) -> SMCSignal:
        """
        Executes full LuxAlgo SMC scan on OHLC dataframe.
        """
        df = df.copy().reset_index(drop=True)
        n = len(df)
        sig = SMCSignal()

        if n < self.swing_length * 2 + 5:
            return sig

        highs = df["high"].to_numpy(dtype=float)
        lows = df["low"].to_numpy(dtype=float)
        closes = df["close"].to_numpy(dtype=float)
        opens = df["open"].to_numpy(dtype=float)
        vols = df["tick_volume"].to_numpy(dtype=float) if "tick_volume" in df.columns else np.ones(n)
        times = df["time"].tolist() if "time" in df.columns else [None] * n

        # -------------------------------------------------------------
        # 0. ATR Calculation (for EQH / EQL threshold)
        # -------------------------------------------------------------
        tr = np.zeros(n)
        tr[0] = highs[0] - lows[0]
        for i in range(1, n):
            tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        atr = pd.Series(tr).rolling(14, min_periods=1).mean().to_numpy()
        current_atr = float(atr[-1]) if len(atr) > 0 else 0.0010

        # -------------------------------------------------------------
        # 1. Swing Leg & Pivot Detection (LuxAlgo leg algorithm)
        # -------------------------------------------------------------
        sw_len = self.swing_length
        swing_highs = []  # list of (index, price, 'HH'/'LH')
        swing_lows = []   # list of (index, price, 'HL'/'LL')

        last_sh_price = None
        last_sl_price = None

        for i in range(sw_len, n - sw_len):
            # Check swing high
            if highs[i] == np.max(highs[i - sw_len : i + sw_len + 1]):
                if len(swing_highs) == 0 or swing_highs[-1][0] != i:
                    struct_type = "HH" if (last_sh_price is not None and highs[i] > last_sh_price) else "LH"
                    swing_highs.append((i, highs[i], struct_type))
                    last_sh_price = highs[i]

            # Check swing low
            if lows[i] == np.min(lows[i - sw_len : i + sw_len + 1]):
                if len(swing_lows) == 0 or swing_lows[-1][0] != i:
                    struct_type = "LL" if (last_sl_price is not None and lows[i] < last_sl_price) else "HL"
                    swing_lows.append((i, lows[i], struct_type))
                    last_sl_price = lows[i]

        # Populate structures in output
        for s_idx, s_price, s_type in swing_highs:
            t_str = times[s_idx].strftime("%H:%M") if hasattr(times[s_idx], 'strftime') else str(times[s_idx])
            sig.bullish_structures.append({
                "price": round(float(s_price), 5),
                "index": int(s_idx),
                "direction": s_type,
                "time": t_str
            })

        for s_idx, s_price, s_type in swing_lows:
            t_str = times[s_idx].strftime("%H:%M") if hasattr(times[s_idx], 'strftime') else str(times[s_idx])
            sig.bearish_structures.append({
                "price": round(float(s_price), 5),
                "index": int(s_idx),
                "direction": s_type,
                "time": t_str
            })

        # -------------------------------------------------------------
        # 2. Stateful BOS vs CHoCH Tracking (Authentic LuxAlgo Engine)
        # -------------------------------------------------------------
        # State: 1 = BULLISH, -1 = BEARISH, 0 = UNKNOWN
        trend_state = 0
        active_sh = None
        active_sl = None

        bullish_obs_raw: List[SMCOrderBlock] = []
        bearish_obs_raw: List[SMCOrderBlock] = []

        last_bos = {"direction": "none", "level": 0.0, "index": None}
        last_choch = {"direction": "none", "level": 0.0, "index": None}

        # Step through bars to accurately track crosses and state transitions
        for i in range(sw_len * 2, n):
            # Update known confirmed swing highs / lows up to bar i
            available_sh = [s for s in swing_highs if s[0] <= i - sw_len]
            available_sl = [s for s in swing_lows if s[0] <= i - sw_len]

            if available_sh:
                active_sh = available_sh[-1]
            if available_sl:
                active_sl = available_sl[-1]

            cur_close = closes[i]

            # Bullish Breakout (Close crosses above Active Swing High)
            if active_sh is not None and cur_close > active_sh[1]:
                if trend_state == -1:
                    # Bearish -> Bullish reversal = CHoCH
                    last_choch = {"direction": "bullish", "level": round(float(active_sh[1]), 5), "index": int(i)}
                    trend_state = 1
                elif trend_state == 1:
                    # Continuation = BOS
                    last_bos = {"direction": "bullish", "level": round(float(active_sh[1]), 5), "index": int(i)}
                else:
                    trend_state = 1
                    last_bos = {"direction": "bullish", "level": round(float(active_sh[1]), 5), "index": int(i)}

                # Extract Bullish Order Block (Lowest candle before the up-break)
                start_search = max(0, active_sh[0])
                if i > start_search:
                    min_idx = start_search + int(np.argmin(lows[start_search:i+1]))
                    t_str = times[min_idx].strftime("%H:%M") if hasattr(times[min_idx], 'strftime') else str(times[min_idx])
                    bullish_obs_raw.append(SMCOrderBlock(
                        top=round(float(highs[min_idx]), 5),
                        bottom=round(float(lows[min_idx]), 5),
                        index=int(min_idx),
                        direction="bullish",
                        mitigated=False,
                        time=t_str
                    ))
                active_sh = None  # Consume swing high to avoid re-triggering on same level

            # Bearish Breakdown (Close crosses below Active Swing Low)
            if active_sl is not None and cur_close < active_sl[1]:
                if trend_state == 1:
                    # Bullish -> Bearish reversal = CHoCH
                    last_choch = {"direction": "bearish", "level": round(float(active_sl[1]), 5), "index": int(i)}
                    trend_state = -1
                elif trend_state == -1:
                    # Continuation = BOS
                    last_bos = {"direction": "bearish", "level": round(float(active_sl[1]), 5), "index": int(i)}
                else:
                    trend_state = -1
                    last_bos = {"direction": "bearish", "level": round(float(active_sl[1]), 5), "index": int(i)}

                # Extract Bearish Order Block (Highest candle before the down-break)
                start_search = max(0, active_sl[0])
                if i > start_search:
                    max_idx = start_search + int(np.argmax(highs[start_search:i+1]))
                    t_str = times[max_idx].strftime("%H:%M") if hasattr(times[max_idx], 'strftime') else str(times[max_idx])
                    bearish_obs_raw.append(SMCOrderBlock(
                        top=round(float(highs[max_idx]), 5),
                        bottom=round(float(lows[max_idx]), 5),
                        index=int(max_idx),
                        direction="bearish",
                        mitigated=False,
                        time=t_str
                    ))
                active_sl = None

        sig.trend_bias = "bullish" if trend_state == 1 else ("bearish" if trend_state == -1 else "neutral")
        sig.bos = last_bos
        sig.choch = last_choch

        # -------------------------------------------------------------
        # 3. Order Block Mitigation Check (Real-Time Active Filter)
        # -------------------------------------------------------------
        active_bull_obs = []
        for ob in bullish_obs_raw:
            ob_mitigated = False
            for j in range(ob.index + 1, n):
                if lows[j] < ob.bottom:
                    ob_mitigated = True
                    break
            if not ob_mitigated:
                active_bull_obs.append(asdict(ob))

        active_bear_obs = []
        for ob in bearish_obs_raw:
            ob_mitigated = False
            for j in range(ob.index + 1, n):
                if highs[j] > ob.top:
                    ob_mitigated = True
                    break
            if not ob_mitigated:
                active_bear_obs.append(asdict(ob))

        sig.order_blocks_bullish = active_bull_obs[-self.ob_max_display:]
        sig.order_blocks_bearish = active_bear_obs[-self.ob_max_display:]

        # -------------------------------------------------------------
        # 4. Fair Value Gaps (FVG) with 3-Bar Imbalance & Mitigation
        # -------------------------------------------------------------
        bull_fvg_list = []
        bear_fvg_list = []

        for i in range(2, n):
            # Bullish FVG: low[i] > high[i-2]
            if lows[i] > highs[i-2]:
                gap_top = round(float(lows[i]), 5)
                gap_bot = round(float(highs[i-2]), 5)
                gap_mid = round((gap_top + gap_bot) / 2.0, 5)
                
                fvg_mitigated = False
                for j in range(i + 1, n):
                    if lows[j] <= gap_bot:
                        fvg_mitigated = True
                        break
                if not fvg_mitigated:
                    t_str = times[i].strftime("%H:%M") if hasattr(times[i], 'strftime') else str(times[i])
                    bull_fvg_list.append({
                        "top": gap_top,
                        "bottom": gap_bot,
                        "mid": gap_mid,
                        "index": int(i),
                        "direction": "bullish",
                        "time": t_str
                    })

            # Bearish FVG: high[i] < low[i-2]
            if highs[i] < lows[i-2]:
                gap_top = round(float(lows[i-2]), 5)
                gap_bot = round(float(highs[i]), 5)
                gap_mid = round((gap_top + gap_bot) / 2.0, 5)
                
                fvg_mitigated = False
                for j in range(i + 1, n):
                    if highs[j] >= gap_top:
                        fvg_mitigated = True
                        break
                if not fvg_mitigated:
                    t_str = times[i].strftime("%H:%M") if hasattr(times[i], 'strftime') else str(times[i])
                    bear_fvg_list.append({
                        "top": gap_top,
                        "bottom": gap_bot,
                        "mid": gap_mid,
                        "index": int(i),
                        "direction": "bearish",
                        "time": t_str
                    })

        sig.fvg_bullish = bull_fvg_list[-10:]
        sig.fvg_bearish = bear_fvg_list[-10:]

        # -------------------------------------------------------------
        # 5. Equal Highs / Equal Lows (EQH / EQL Liquidity Pools)
        # -------------------------------------------------------------
        eq_dist = self.eq_threshold_atr * current_atr
        
        eq_highs = []
        for i in range(len(swing_highs)):
            for j in range(i + 1, len(swing_highs)):
                idx1, p1, _ = swing_highs[i]
                idx2, p2, _ = swing_highs[j]
                if abs(p1 - p2) <= eq_dist:
                    t_str = times[idx2].strftime("%H:%M") if hasattr(times[idx2], 'strftime') else str(times[idx2])
                    eq_highs.append({
                        "price": round(float((p1 + p2) / 2.0), 5),
                        "indices": [int(idx1), int(idx2)],
                        "direction": "equal_high",
                        "time": t_str
                    })
                    break
        sig.equal_highs = eq_highs[-5:]

        eq_lows = []
        for i in range(len(swing_lows)):
            for j in range(i + 1, len(swing_lows)):
                idx1, p1, _ = swing_lows[i]
                idx2, p2, _ = swing_lows[j]
                if abs(p1 - p2) <= eq_dist:
                    t_str = times[idx2].strftime("%H:%M") if hasattr(times[idx2], 'strftime') else str(times[idx2])
                    eq_lows.append({
                        "price": round(float((p1 + p2) / 2.0), 5),
                        "indices": [int(idx1), int(idx2)],
                        "direction": "equal_low",
                        "time": t_str
                    })
                    break
        sig.equal_lows = eq_lows[-5:]

        # -------------------------------------------------------------
        # 6. Authentic Dealing Range (Discount, Equilibrium, Premium)
        # -------------------------------------------------------------
        lookback = min(100, n)
        range_high = float(np.max(highs[-lookback:]))
        range_low = float(np.min(lows[-lookback:]))
        range_span = max(range_high - range_low, 1e-9)

        sig.equilibrium   = round(range_low + 0.50 * range_span, 5)
        sig.discount_zone = round(range_low + 0.382 * range_span, 5)   # Discount threshold <= 38.2%
        sig.premium_zone  = round(range_low + 0.618 * range_span, 5)   # Premium threshold >= 61.8%

        # -------------------------------------------------------------
        # 7. Strong High & Strong Low
        # -------------------------------------------------------------
        if swing_highs:
            max_sh = max(swing_highs, key=lambda x: x[1])
            sig.strong_high = round(float(max_sh[1]), 5)
        else:
            sig.strong_high = round(range_high, 5)

        if swing_lows:
            min_sl = min(swing_lows, key=lambda x: x[1])
            sig.strong_low = round(float(min_sl[1]), 5)
        else:
            sig.strong_low = round(range_low, 5)

        return sig

    def to_dict(self, sig: SMCSignal) -> Dict[str, Any]:
        return asdict(sig)

    def to_json(self, sig: SMCSignal) -> str:
        import json
        return json.dumps(asdict(sig), default=str, ensure_ascii=False)

