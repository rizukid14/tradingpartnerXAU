"""
Fixed Range Volume Profile (FRVP) & Liquidity Density Engine.
Pure Python / Numpy implementation for institutional order flow & auction market analysis.

Features:
  1. Fixed Range Volume Profile (FRVP) across user-specified or impulse bar ranges [start_idx, end_idx].
  2. Mathematical Point of Control (POC): Price bin with maximum accumulated traded volume.
  3. Value Area High (VAH) & Value Area Low (VAL): Exact price bounds enclosing target% (default 70%) of volume.
  4. High Volume Nodes (HVN) & Low Volume Nodes (LVN) extraction.
  5. Confluence calculation against SMC Order Blocks & Fair Value Gaps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple
import numpy as np
import pandas as pd


@dataclass
class VolumeProfileResult:
    poc: float = 0.0
    vah: float = 0.0
    val: float = 0.0
    range_high: float = 0.0
    range_low: float = 0.0
    total_volume: float = 0.0
    poc_volume: float = 0.0
    value_area_volume: float = 0.0
    value_area_pct: float = 0.70
    hvn_nodes: List[float] = field(default_factory=list)
    lvn_nodes: List[float] = field(default_factory=list)
    bin_edges: List[float] = field(default_factory=list)
    bin_volumes: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "poc": self.poc,
            "vah": self.vah,
            "val": self.val,
            "range_high": self.range_high,
            "range_low": self.range_low,
            "total_volume": self.total_volume,
            "poc_volume": self.poc_volume,
            "value_area_pct": self.value_area_pct,
            "hvn_nodes": self.hvn_nodes,
            "lvn_nodes": self.lvn_nodes
        }


def compute_fixed_range_volume_profile(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: Optional[np.ndarray] = None,
    volumes: Optional[np.ndarray] = None,
    start_idx: int = 0,
    end_idx: int = 0,
    num_bins: int = 60,
    value_area_pct: float = 0.70
) -> Optional[VolumeProfileResult]:
    """
    Computes Fixed Range Volume Profile for bars [start_idx : end_idx].
    
    Parameters
    ----------
    highs : np.ndarray
        Array of high prices.
    lows : np.ndarray
        Array of low prices.
    closes : np.ndarray, optional
        Array of close prices.
    volumes : np.ndarray, optional
        Array of tick or real volume. If None, uniform volume = 1.0 is assumed.
    start_idx : int
        Starting bar index (inclusive).
    end_idx : int
        Ending bar index (inclusive).
    num_bins : int
        Number of price discretization bins (default 60).
    value_area_pct : float
        Percentage of volume inside Value Area (default 0.70 / 70%).
        
    Returns
    -------
    Optional[VolumeProfileResult]
    """
    n = len(highs)
    if start_idx > end_idx or start_idx < 0 or end_idx >= n:
        return None
        
    slice_highs = highs[start_idx:end_idx + 1]
    slice_lows = lows[start_idx:end_idx + 1]
    
    if len(slice_highs) == 0:
        return None
        
    range_high = float(np.max(slice_highs))
    range_low = float(np.min(slice_lows))
    
    if range_high <= range_low:
        return None
        
    bin_edges = np.linspace(range_low, range_high, num_bins + 1)
    bin_volumes = np.zeros(num_bins, dtype=np.float64)
    
    for idx in range(start_idx, end_idx + 1):
        b_high = float(highs[idx])
        b_low = float(lows[idx])
        b_vol = float(volumes[idx]) if volumes is not None else 1.0
        
        if b_high <= b_low:
            b_idx = min(int((b_high - range_low) / (range_high - range_low) * num_bins), num_bins - 1)
            bin_volumes[b_idx] += b_vol
            continue
            
        bar_height = b_high - b_low
        for b in range(num_bins):
            edge_l = bin_edges[b]
            edge_h = bin_edges[b + 1]
            
            overlap_l = max(b_low, edge_l)
            overlap_h = min(b_high, edge_h)
            
            if overlap_h > overlap_l:
                fraction = (overlap_h - overlap_l) / bar_height
                bin_volumes[b] += b_vol * fraction
                
    total_vol = float(np.sum(bin_volumes))
    if total_vol <= 0:
        return None
        
    poc_bin = int(np.argmax(bin_volumes))
    poc_price = float((bin_edges[poc_bin] + bin_edges[poc_bin + 1]) / 2.0)
    poc_vol = float(bin_volumes[poc_bin])
    
    # Calculate Value Area (expanding outwards from POC until reaching value_area_pct)
    target_vol = total_vol * value_area_pct
    current_vol = poc_vol
    up_idx = poc_bin
    down_idx = poc_bin
    
    while current_vol < target_vol and (up_idx < num_bins - 1 or down_idx > 0):
        next_up_vol = float(bin_volumes[up_idx + 1]) if up_idx < num_bins - 1 else 0.0
        next_down_vol = float(bin_volumes[down_idx - 1]) if down_idx > 0 else 0.0
        
        if next_up_vol >= next_down_vol and up_idx < num_bins - 1:
            up_idx += 1
            current_vol += bin_volumes[up_idx]
        elif down_idx > 0:
            down_idx -= 1
            current_vol += bin_volumes[down_idx]
        elif up_idx < num_bins - 1:
            up_idx += 1
            current_vol += bin_volumes[up_idx]
        else:
            break
            
    val_price = float(bin_edges[down_idx])
    vah_price = float(bin_edges[up_idx + 1])
    
    # Extract HVN & LVN
    mean_vol = total_vol / num_bins
    hvn_nodes: List[float] = []
    lvn_nodes: List[float] = []
    
    for b in range(1, num_bins - 1):
        mid_p = (bin_edges[b] + bin_edges[b + 1]) / 2.0
        v = bin_volumes[b]
        # Peak detection for HVN
        if v > bin_volumes[b - 1] and v > bin_volumes[b + 1] and v >= 1.35 * mean_vol:
            hvn_nodes.append(round(float(mid_p), 5))
        # Trough detection for LVN
        elif v < bin_volumes[b - 1] and v < bin_volumes[b + 1] and v <= 0.65 * mean_vol:
            lvn_nodes.append(round(float(mid_p), 5))
            
    return VolumeProfileResult(
        poc=round(poc_price, 5),
        vah=round(vah_price, 5),
        val=round(val_price, 5),
        range_high=round(range_high, 5),
        range_low=round(range_low, 5),
        total_volume=round(total_vol, 2),
        poc_volume=round(poc_vol, 2),
        value_area_volume=round(current_vol, 2),
        value_area_pct=value_area_pct,
        hvn_nodes=hvn_nodes,
        lvn_nodes=lvn_nodes,
        bin_edges=[round(float(e), 5) for e in bin_edges],
        bin_volumes=[round(float(v), 2) for v in bin_volumes]
    )


def check_ob_frvp_confluence(
    ob_top: float,
    ob_bottom: float,
    ob_direction: str,
    frvp: VolumeProfileResult,
    atr: float
) -> Dict[str, Any]:
    """
    Evaluates whether an Order Block has high institutional confluence with the FRVP.
    
    Returns:
      {
        "poc_overlap": bool,
        "poc_distance": float,
        "va_discount": bool,
        "is_lvn": bool,
        "confluence_score": float (0.0 to 1.0),
        "rating": "A+" | "A" | "B" | "WEAK"
      }
    """
    ob_mid = (ob_top + ob_bottom) / 2.0
    poc = frvp.poc
    val = frvp.val
    vah = frvp.vah
    
    # 1. POC Overlap / Proximity
    poc_overlap = (min(ob_top, ob_bottom) <= poc <= max(ob_top, ob_bottom))
    poc_dist = abs(ob_mid - poc)
    poc_near = poc_dist <= (0.20 * atr) if atr > 0 else False
    
    # 2. Value Area Wholesale Discount / Premium
    va_discount = False
    if ob_direction.lower() in ["bullish", "buy"]:
        # Bullish OB should be at or below VAL (Wholesale Discount)
        va_discount = (ob_mid <= val) or (ob_top <= val + 0.10 * atr)
    else:
        # Bearish OB should be at or above VAH (Wholesale Premium)
        va_discount = (ob_mid >= vah) or (ob_bottom >= vah - 0.10 * atr)
        
    # 3. Check if OB sits in LVN (thin volume vacuum)
    is_lvn = any(abs(ob_mid - lvn) <= 0.10 * atr for lvn in frvp.lvn_nodes) if atr > 0 else False
    is_thin_volume_danger = bool(is_lvn or (poc_dist > 1.5 * atr and not va_discount))
    
    # 4. Auction Disambiguation (Acceptance vs Rejection)
    if va_discount or poc_overlap:
        auction_state = "ACCEPTANCE"
    elif is_lvn:
        auction_state = "REJECTION"
    else:
        auction_state = "NEUTRAL"
    
    # Compute composite score
    score = 0.40  # Base SMC score
    if poc_overlap:
        score += 0.35
    elif poc_near:
        score += 0.25
        
    if va_discount:
        score += 0.25
        
    if is_thin_volume_danger:
        score -= 0.25
        
    score = max(0.0, min(1.0, score))
    
    if score >= 0.85 and not is_thin_volume_danger:
        rating = "A+"
    elif score >= 0.65:
        rating = "A"
    elif score >= 0.45:
        rating = "B"
    else:
        rating = "WEAK"
        
    return {
        "poc_overlap": poc_overlap or poc_near,
        "poc_distance": round(poc_dist, 5),
        "va_discount": va_discount,
        "is_lvn": is_lvn,
        "is_thin_volume_danger": is_thin_volume_danger,
        "auction_state": auction_state,
        "confluence_score": round(score, 2),
        "rating": rating,
        "poc": poc,
        "val": val,
        "vah": vah
    }
