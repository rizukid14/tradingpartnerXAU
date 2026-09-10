# Design Specification: Session-Adaptive Mechanism Decoupling, ZCE Natural Chamber Restoration, and Dashboard Visibility Sync

**Date**: 2026-09-10  
**Status**: Approved (Brainstorming Phase Completed)  
**Target Branch**: `quant-trade-noAI` / `quant-trade`  
**Related Components**: `zone_confluence_engine.py`, `market_scanner.py`, `basket_sync_engine.py`, `dashboard.py`, `dashboard_assets.py`

---

## 1. Executive Summary & Empirical Problem Statement

### 1.1 Empirical Findings from Live Telemetry (`data/trade_lifecycle_telemetry.json`)
Analysis of 101 recorded trades revealed a sharp discrepancy across market sessions:

- **Asia Session (07:00–14:00 WIB)**: 29 closed trades, **Win Rate 69.0%**, **Net Profit +$459.58**.
  - M3 Breakout Retest: 14 trades, 11 W - 3 L, **WR 78.6%**, Net +$318.46.
  - M2 Trend-Aligned Pullback: 11 trades, 7 W - 4 L, **WR 63.6%**, Net +$134.34.
  - M1 Universal Liquidity Sweep: 3 trades, 2 W - 1 L, **WR 66.7%**, Net +$43.93.
- **London Session (14:00–18:00 WIB)**: 30 closed trades, **Win Rate 53.3%**, **Net Loss -$823.00**.
  - M3 Breakout Retest: 13 trades, 8 W - 5 L, WR 61.5%, but **Net -$359.76** due to asymmetric loss payouts (-$136 to -$153) during volatility spikes vs small winners (+$15 to +$25).
  - M2 Trend-Aligned Pullback: 14 trades, 6 W - 8 L, **WR 42.9%**, Net -$424.83 from deep opening stop runs.
- **New York Session (18:00–24:00 WIB)**: 19 closed trades, **Win Rate 52.6%**, **Net Loss -$292.32**.
  - M3 Breakout Retest: 5 trades, 1 W - 4 L, **WR 20.0%**, **Net -$233.62**. Late-session breakouts in NY are late-cycle distribution/exhaustion moves that trap breakout entries.
  - M2 Trend-Aligned Pullback: 9 trades, 7 W - 2 L, **WR 77.8%**, Net +$59.09.
  - M1 Universal Liquidity Sweep: 4 trades, 2 W - 2 L, Net -$95.48.

### 1.2 The Systemic Deadlock in Working Code
To mitigate NY losses, recent updates introduced tight filters that inadvertently caused a systemic blockage:
1. **ZCE Chamber Shrinkage (Commit 06189ac / #82)**:
   - Formula `min_ch = max(0.50 * atr_h1, min(15p, 0.75 * atr_h1))` collapsed chamber heights to 5–15 pips (e.g., AUDCHF 5.2p, EURGBP 3.1p, EURUSD 6–15p).
2. **CBSS Runway Deadlock**:
   - `market_scanner.py` enforced `Runway >= 1.20x ATR` globally on all continuation setups.
   - When the chamber width is only 0.8x ATR, internal runway to the opposing wall is mathematically capped at <= 0.8x ATR < 1.20x ATR.
   - Result: 4,285 lines of `[CBSS RUNWAY] Insufficient Runway` in `gate_debug.log`, blocking 55.8% of all 26 pairs.
3. **Tokyo Midday Lull Static Lock**:
   - `morning range < 25p` froze all continuation trades from 10:30 to 13:00 WIB, even on quiet pairs where 15–20 pips is a full session range.
4. **Adverse Selection**:
   - Natural Asia winners were blocked, while distorted entries (e.g., AUDNZD BUY at 82% Dealing Range) slipped through and took maximum stop loss (-$60).

---

## 2. Architectural Design

```
                     +-----------------------------------------------+
                     |          Market Scanner Loop (60s)            |
                     +-----------------------+-----------------------+
                                             |
                       +---------------------+---------------------+
                       |                                           |
                       v                                           v
         +---------------------------+               +---------------------------+
         | Zone Confluence Engine    |               | Session-Adaptive Matrix   |
         | (Natural Chamber >= 15p)  |               | (Asia / London / NY Mode) |
         +-------------+-------------+               +-------------+-------------+
                       |                                           |
                       |  F1/C1 >= max(0.6*ATR, 15p)               |  NY: M3 VETO (WR 20%)
                       |  min_sep >= max(0.5*ATR, 15p)             |  London: M3 CSM >= 1.50
                       |                                           |  Asia: M1/M2/M3 Unlocked
                       +---------------------+---------------------+  Lull: Dynamic 0.4*ATR
                                             |
                                             v
                       +-------------------------------------------+
                       | Basket Sync Engine (Runway Decoupling)    |
                       | - M4 Systemic Flow : Runway >= 1.20x ATR  |
                       | - M2/M3 Chamber    : Runway >= 0.60x ATR  |
                       |                      (Grade B Scalp Pass) |
                       +---------------------+---------------------+
                                             |
                                             v
                       +-------------------------------------------+
                       | Dashboard Cockpit & 8-Gate X-Ray Sync     |
                       | - Chart F1/C1 pinned to Engine Macro      |
                       | - Live Chamber Height & Bilateral Runway  |
                       | - Session Mode Badges (Asia/London/NY)    |
                       +-------------------------------------------+
```

---

## 3. Detailed Component Specifications

### 3.1 Component 1: Zone Confluence Engine (`src/analytics/zone_confluence_engine.py`)
- **Minimum Chamber Height (`min_ch`)**:
  Restore strict physical floor:
  `min_ch = max(0.60 * atr_h1, 15.0 * pip_val)`
  where `pip_val = 0.00010` for 5-digit pairs and `0.010` for 3-digit JPY pairs.
- **Layer Separation (`min_sep`)**:
  `min_sep = max(0.50 * atr_h1, 15.0 * pip_val)`
  Eliminate micro-clustering where 3-pip wicks or minor imbalances create false intermediate layers.
- **Chamber Clearance Fallback Guarantee**:
  If candidate layers are closer than `min_ch`, advance outward to `ceil_layers[1:]` or `floor_layers[1:]`. If all market layers are exhausted within `min_ch`, inject nearest psychological dual-grid station so chamber height is guaranteed >= min_ch.

### 3.2 Component 2: Session-Adaptive Mechanism Matrix (`src/analytics/market_scanner.py`)
In `_is_direction_allowed()`:
1. **New York Session (18:00–24:00 WIB)**:
   - Absolute Veto on M3 Breakout Retest:
     If `now_wib.hour >= 18` and `BREAKOUT` in `setup_label`: block with `[NY SESSION VETO] M3 Breakout Retest forbidden in late-session distribution (Empirical WR 20%). Only M1 Sweep and M2 Pullback allowed.`
   - M1 Universal Liquidity Sweep and M2 Trend-Aligned Pullback remain active.
2. **London Session (14:00–18:00 WIB)**:
   - M3 Breakout Retest requires Boitoki CSM Net Momentum confirmation:
     Breakout direction must match CSM sign and `|CSM Delta| >= 1.50`.
     If violated: block with `[LONDON M3 CSM VETO] Breakout lacks institutional momentum (|CSM| < 1.50 or opposed)`.
   - M2 Pullback guarded by Dealing Range boundaries:
     - BUY rejected if Dealing Range Position > 0.65 (premium).
     - SELL rejected if Dealing Range Position < 0.35 (discount).
3. **Tokyo Midday Lull (10:30–13:00 WIB)**:
   - Dynamic ATR-based threshold replaces static 25 pips:
     `lull_min_pips = max(0.40 * atr_pips, 12.0)`
     Permits active trading on calm pairs (e.g., AUDNZD, AUDCHF) whose morning range is >= 12 pips.

### 3.3 Component 3: Basket Sync Engine Runway Decoupling (`src/analytics/basket_sync_engine.py`)
- **Key Resolution Fallback**:
  `calculate_pair_runway` extracts `imm_ceiling_c1`, `ceiling_c1`, `c1`, and `zce_walls` with deterministic fallback.
- **Runway Threshold Decoupling**:
  - **M4 Systemic Flow (`is_sfr_pro` / `SYSTEMIC_FLOW`)**: Retains strict `min_runway = 1.20x ATR`.
  - **M2 Pullback & M3 Retest (Internal Chamber Trades)**:
    `min_runway = max(0.60 * atr_h1, 0.75 * sl_distance)`
    If runway >= 0.60x ATR and satisfies net R:R >= 0.75R, setup is designated as **Grade B Wall Scalp** or **Grade A Standard** and permitted to execute.
    Setup is only blocked if runway < 0.50x ATR (`WALL_EXHAUSTED`).

### 3.4 Component 4: Dashboard Cockpit & X-Ray Visibility Sync (`dashboard.py` & `dashboard_assets.py`)
1. **Chart Proximity Threshold Alignment (`dashboard.py:1010`)**:
   Align `pip_thr` and `proximity_thr` with the ZCE restoration formula (>= 0.50x ATR and >= 15 pips).
2. **Deterministic Level Pinning**:
   Ensure F1 and C1 displayed on chart match `macro_cache[sym]['immediate_floor_f1']` and `macro_cache[sym]['immediate_ceiling_c1']`.
3. **Telemetry Metrics on Watchlist & Detail View**:
   - Display Chamber Height in pips and xATR (`Chamber: 28.5p | 1.85x ATR`).
   - Display Bilateral Runway targets (`BUY RUN C1: 1.45x`, `SELL RUN F1: 0.95x`).
   - Highlight amber `[WALL EXHAUSTED]` when runway < 0.50x ATR.
4. **Session-Mechanism Status Badges**:
   - Asia: `[ASIA ACTIVE: M1, M2, M3 FULLY ARMED]` (Green)
   - London: `[LONDON CORE: M3 CSM-GATED (|Delta| >= 1.50)]` (Blue)
   - New York: `[NY EXPANSION: M3 VETOED - M1 & M2 ARMED]` (Purple)
5. **Gate 3 Consistency**:
   Gate 3 in 8-Gate X-Ray reflects the decoupled runway evaluation so that Grade B Scalps show `PASS` with clear runway context.

---

## 4. Verification & Testing Plan

1. **Automated Unit Tests**:
   - `tests/test_zce_chamber_clearance.py`: Verify chamber height is strictly >= 15 pips across quiet and high-beta assets.
   - `tests/test_session_adaptive_matrix.py`:
     * Verify NY session blocks M3 Breakouts but allows M1 Sweep and M2 Pullback.
     * Verify London session requires |CSM Delta| >= 1.50 for M3.
     * Verify Tokyo Midday Lull permits continuation when morning range >= 0.40x ATR.
   - `tests/test_basket_relay.py`: Verify Grade B chamber trades pass runway check when runway >= 0.60x ATR.
2. **Empirical Regression Run**:
   - Run `measure_all_runways.py` across all 26 FX pairs and confirm false block rate drops from 55.8% to < 15% (only truly wall-exhausted pairs blocked).
3. **Dashboard Real-Time Telemetry Audit**:
   - Verify dashboard API output (`/api/overview`, `/api/symbol/<sym>`) reflects the exact ZCE boundaries from engine `macro_cache`.
