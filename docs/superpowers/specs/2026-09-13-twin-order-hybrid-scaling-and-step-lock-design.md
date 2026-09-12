# Design Spec: Twin-Order Hybrid Scaling & Discrete Milestone Step-Lock Architecture

- **Date**: 2026-09-13
- **Author**: Antigravity & Quantitative Architecture Team
- **Topic**: H1 Trade Management Expectancy Optimization (Premature BEP vs Swing Breathing Room)
- **Status**: DRAFT / APPROVED FOR DESIGN

---

## 1. Executive Summary & Problem Formulation

### 1.1 The Core Quantitative Dilemma
On the H1 timeframe, currency pairs exhibit structural retracements and secondary liquidity tests (e.g. SBR/RBS retests) after establishing initial displacement. 
Under existing single-order trade management:
1. **Premature Break-Even (BEP)**: Shifting the Stop Loss directly to entry at 50%-60% of the TP distance prematurely suffocates trades during healthy retests, stopping out positions right before the market resumes its primary impulse toward final targets.
2. **All-or-Nothing Full Risk**: Leaving the entire position open without any partial profit extraction subjects the portfolio to severe profit givebacks (-1.0R loss from significant unrealized gains) whenever institutional exhaustion occurs at intermediate liquidity stations.
3. **Sub-0.50R Choke Fallacy**: Moving Stop Loss to 50% risk when price only moves +0.30R is statistically invalid; +0.30R (~6-9 pips in FX) resides entirely within the Brownian noise band of an H1 candle, degrading system expectancy by over 90% through premature stoppages.

### 1.2 The Architectural Solution: Twin-Order Hybrid Scaler
To decouple quick risk elimination from long-term trend capture, the execution engine transitions to an asymmetric **Twin-Order Architecture** governed by a **Discrete Milestone Step-Lock State Machine**:
- **Ticket A (50% lot)**: Hard Take Profit placed natively at **TP1 (Station 1)** on the broker server.
- **Ticket B (50% lot)**: Hard Take Profit placed natively at **TP3 (Station 3)** on the broker server.
- **Milestone Protection**:
  - Once Ticket A fills at TP1, Ticket B SL moves to **Break-Even (Entry + commission padding)**.
  - While price traverses between TP1 and TP2, Ticket B SL **remains strictly at Break-Even**, absorbing all retests at TP1 without interference.
  - When price touches **TP2 (Station 2)**, Ticket B SL is elevated to **TP1**, locking in minimum baseline profit.
  - When price reaches 80% progress toward **TP3**, Ticket B SL is elevated to **TP2**.

---

## 2. Mathematical Models & Order Dispatching

### 2.1 Sizing & Lot Distribution
Let $V_{total}$ be the total calculated volume from `risk_engine.calculate_lot_size(symbol, sl_points)`:
- Constrained by `MAX_POSITION_LOT = 0.50` (Cent account strict ceiling).
- Constrained by broker `volume_step = 0.01` and `volume_min = 0.01`.

#### Lot Allocation Rules:
1. **Case $V_{total} \le 0.01$ (Fail-safe Single Order)**:
   - Volume: $V_{total} = 0.01$
   - Target: Single Order targeting **TP1** directly.
   - SL: Initial Stop Loss ($SL_{initial}$).
   - Rationale: Avoids overleveraging beyond the 1.0% risk limit on small account balances or high-SL assets (e.g. Gold).
2. **Case $V_{total} \ge 0.02$ (Twin-Order Split)**:
   $$V_A = \text{floor\_to\_step}(V_{total} \times 0.50)$$
   $$V_B = \text{round\_to\_step}(V_{total} - V_A)$$
   *(Example: For 0.05 lot, $V_A = 0.02$ lot and $V_B = 0.03$ lot).*

### 2.2 Order Specifications
At entry execution, the bot sends two simultaneous orders with unique tracking comments and unified magic number (`20260625`):

| Order Parameter | Ticket A (Harvest Engine) | Ticket B (Runner Engine) |
|---|---|---|
| **Volume** | $V_A$ | $V_B$ |
| **Order Type** | BUY_LIMIT / SELL_LIMIT or BUY / SELL | Identical to Ticket A |
| **Price** | Signal Entry Price | Signal Entry Price |
| **Stop Loss** | $SL_{initial}$ | $SL_{initial}$ |
| **Take Profit** | $TP_1$ (Native Limit on Broker) | $TP_3$ (Native Limit on Broker) |
| **Comment** | `SYS:TWIN_A:TP1` | `SYS:TWIN_B:RUNNER` |

---

## 3. Discrete Milestone Step-Lock State Machine

### 3.1 State Transitions

```
               [ INITIATED: TWIN OPEN ]
              /                        \
             /                          \
(Price hits SL_initial)         (Broker fills Ticket A at TP1)
           /                              \
          v                                v
  [ STOPPED_OUT ]             [ TP1_HARVESTED_BEP_ACTIVE ]
  (-1.0R Net Loss)            - Ticket A closed with profit
                              - Ticket B SL -> BEP (Entry + padding)
                              - SL remains stationary at BEP between TP1..TP2
                                      /                   \
                                     /                     \
                      (Retest hits BEP)          (Market price reaches TP2)
                            /                                \
                           v                                  v
                  [ RUNNER_BEP_EXIT ]             [ TP2_REACHED_LOCK_TP1 ]
                  (Net Positive Gain)             - Ticket B SL elevated to TP1
                                                  - Profit >= TP1 distance locked
                                                          /               \
                                                         /                 \
                                          (Retest hits TP1)      (Price >= 80% to TP3)
                                                /                            \
                                               v                              v
                                      [ EXIT_AT_TP1 ]             [ TP3_APPROACH_LOCK_TP2 ]
                                      (Solid Profit)              - Ticket B SL -> TP2
                                                                              \
                                                                               \
                                                                    (Broker fills Ticket B at TP3)
                                                                                 \
                                                                                  v
                                                                      [ FULL_TP3_HARVESTED ]
                                                                      (Maximum Structural R:R)
```

### 3.2 Quantitative Activation Triggers

1. **State `TP1_HARVESTED_BEP_ACTIVE`**:
   - **Trigger**: `ticket_a` is closed in MT5 position pool AND `ticket_a` deal exit reason or profit is positive.
   - **Action**: Call `modify_position(ticket_b, sl=be_price)`.
   - **Calculation of `be_price`**:
     - For BUY: $\text{entry\_fill\_price} + (\text{be\_padding} \times \text{point})$
     - For SELL: $\text{entry\_fill\_price} - (\text{be\_padding} \times \text{point})$
     - $\text{be\_padding} = \max(\text{commission\_padding}, 15\text{ pts})$.
   - **Breathing Invariant**: Under no circumstances shall Ticket B SL move higher during the interval between TP1 and TP2.

2. **State `TP2_REACHED_LOCK_TP1`**:
   - **Trigger**:
     - BUY: $\text{current\_bid} \ge TP_2$
     - SELL: $\text{current\_ask} \le TP_2$
   - **Action**: Call `modify_position(ticket_b, sl=tp1_lock_price)`.
   - **Calculation of `tp1_lock_price`**:
     - For BUY: $TP_1 + (\text{padding} \times \text{point})$
     - For SELL: $TP_1 - (\text{padding} \times \text{point})$

3. **State `TP3_APPROACH_LOCK_TP2`**:
   - **Trigger**: Progress ratio $P \ge 0.80$ where:
     $$P = \frac{|\text{current\_price} - TP_2|}{|TP_3 - TP_2|}$$
   - **Action**: Call `modify_position(ticket_b, sl=tp2_lock_price)`.

4. **State `FULL_TP3_HARVESTED`**:
   - **Trigger**: Native broker execution of Take Profit limit on Ticket B.

---

## 4. Telemetry, Runtime Persistence & Dashboard Integration

### 4.1 Local Persistence (`data/active_twin_trades.json`)
To survive unexpected bot restarts or internet disconnections, the active twin state is saved atomically:
```json
{
  "AUDUSD_20260913_001": {
    "pair_id": "AUDUSD_20260913_001",
    "symbol": "AUDUSD-ECNc",
    "direction": "BUY",
    "ticket_a": 100101,
    "ticket_b": 100102,
    "volume_a": 0.05,
    "volume_b": 0.05,
    "entry_price": 0.72000,
    "sl_initial": 0.71800,
    "tp1": 0.72150,
    "tp2": 0.72250,
    "tp3": 0.72350,
    "state": "TP1_HARVESTED_BEP_ACTIVE",
    "created_at": "2026-09-13T00:15:00+07:00",
    "updated_at": "2026-09-13T01:30:00+07:00"
  }
}
```

### 4.2 Boot Synchronization (Catch-Up Logic)
When `position_manager.py` initializes:
1. Load `data/active_twin_trades.json`.
2. Inspect MT5 live positions:
   - If `ticket_a` is absent and `ticket_b` is present: inspect MT5 deal history for `ticket_a`. If closed with profit, instantly ensure `ticket_b` SL is at or above BEP.
   - If both `ticket_a` and `ticket_b` are closed: mark `pair_id` as archived in JSON.

### 4.3 Cockpit Dashboard (Port 8765) Telemetry
1. **Paired Ticket Aggregation**:
   - The open positions table displays paired tickets as a single consolidated row with dual sub-badges:
     - `AUDUSD BUY | Ticket #100101 [TP1 HARVESTED +$12.50] / Ticket #100102 [RUNNER: SL @ BEP]`
2. **Flight Path Visual Progress**:
   - Interactive milestone progress tracker in the right margin and bottom drawer:
     `[ENTRY 0.72000] -> [TP1 0.72150 (DONE)] -> [TP2 0.72250 (PENDING)] -> [TP3 0.72350]`

---

## 5. Risk Safeguards & Non-Negotiable Hard Gates

1. **Akun Cent Plafon Compliance**:
   - Each individual ticket and cumulative exposure respects `MAX_POSITION_LOT = 0.50`.
2. **Emergency Circuit Breakers**:
   - All twin positions are immediately closed by the existing:
     - **Pre-Rollover Shield** (03:50–04:15 WIB if floating near SL).
     - **Pre-News Emergency Shield** (High impact US/constituent releases).
     - **Max Daily Loss Breaker** (4.0% daily equity drawdown).
3. **Execution Robustness**:
   - Retry order modifications up to 3 times with 500ms delay on broker requotes or temporary freeze errors.

---

## 6. Verification Plan

### 6.1 Automated Unit Tests
- `test_twin_sizing`: Verify lot allocation for 0.01, 0.02, 0.03, 0.05, and 0.50 lot inputs.
- `test_twin_state_transitions`: Mock price movement through TP1 -> Retest -> TP2 -> TP3, verifying exact SL adjustments.
- `test_twin_catchup_recovery`: Simulate bot restart with Ticket A closed and verify Ticket B SL moves to BEP immediately.
- `test_full_suite`: Full test suite run (`py -3 -m unittest discover -s tests -p "test_*.py"`) maintaining 100% pass rate.

### 6.2 Manual Staging Verification
- Verify payload and visual display on `http://127.0.0.1:8765`.
