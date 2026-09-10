# Mechanism Review — Week of 2026-09-07 (VTMarkets-Demo #1157958)

> **Review scope (validated in brainstorming):** Stat-first scorecard of all 4 mechanisms, verdict by R/trade with 95% Wilson CI, on this week's live trades joined with shadow records. Standardized outcome classification: win = TP_HIT + TRAILING_SL_HIT, loss = SL_HIT, BEP = BEP_HIT; expired/time-decay excluded from W/L.
>
> **Data caveat:** The shadow R-tracker double-counts some real tickets (e.g. GBPCHF ticket `672317358` appears 3×). All real-USD figures below are computed from unique tickets in `trade_lifecycle_telemetry.json` (46 unique closed trades) joined to shadow records.

---

## 1. Executive Verdict

| Mechanism | Trades* | R/trade | 95% CI (R/trade) | Real USD (unique tickets) | Verdict |
|---|---|---|---|---|---|
| M1 Universal Liquidity Sweep | 12 | +0.138 | [−0.21, +0.46] | **+$154.16** | ✅ MARGINAL — only one in the green |
| M2 Trend-Aligned Pullback | 81 | +0.061 | [−0.04, +0.17] | **−$384.66** | ❌ INVALID — worst real P&L |
| M3 Breakout Retest Guard | 72 | +0.127 | [−0.00, +0.25] | −$2.80 | ⚠️ MARGINAL — breakeven after friction |
| M4 Systemic Flow Continuation | 7 | +0.243 | [−0.06, +0.65] | −$31.93 | ⚠️ MARGINAL — best R/trade but tiny sample |

\* Trades = shadow records for that mechanism; real USD uses only unique closed tickets from telemetry (M2: 12, M3: 25, M4: 3, M1: 3).

**Bottom line:** Not one mechanism's edge is statistically distinguishable from the random-walk null at 95% confidence. Every CI brackets zero. The whole system shows **+0.10 R/trade on paper but −$198.63 in real money** — the R-tracker and the account disagree, and the account is the truth.

---

## 2. Scorecard (win-rate CI)

| Mechanism | W | L | BEP | WR | WR CI (95%) |
|---|---|---|---|---|---|
| M1 Universal Liquidity Sweep | 5 | 2 | 4 | 71.4% | [35.9%, 91.8%] |
| M2 Trend-Aligned Pullback | 20 | 9 | 24 | 69.0% | [50.8%, 82.7%] |
| M3 Breakout Retest Guard | 22 | 12 | 14 | 64.7% | [47.9%, 78.5%] |
| M4 Systemic Flow Continuation | 3 | 2 | 0 | 60.0% | [23.1%, 88.2%] |

Win rates look strong (60–71%), but that's the trap: **the payoff ratio is 0.49** (avg win +$36.43 vs avg loss −$73.83). You need >67% win rate just to break even at that payoff. These CIs are wide enough that M1, M3, M4 all "fit" a system with no real edge.

---

## 3. Data-Quality Issues Found

1. **Shadow tracker overstates results.** It reports +9.26R / 55.7% WR, but real unique-ticket P&L is −$198.63 / 63% WR. The tracker: (a) double-counts tickets, (b) prices R on raw trigger prices, ignoring spread + commission + slippage on actual fills, (c) counts BE/trailing locks as "wins."
2. **M1 has 5 neutral/expired records out of 12** — 41% of its signals never resolve into a trade. Its +$154 figure rests on only 7 real outcomes.
3. **M4 has 7 trades total, 2 of which are expired** — statistically meaningless as a standalone verdict.

---

## 4. Findings

### 4.1 M1 Universal Liquidity Sweep — the only mechanism making money
- Real USD **+$154.16** is entirely driven by 3 winning sweep trades (NZDUSD, GBPUSD, AUDUSD) that exited via trailing SL with +$41–64 each.
- Genuinely strongest, but sample is tiny and 41% of signals expire. **Claim: best edge; unproven at scale.**

### 4.2 M2 Trend-Aligned Pullback — the liability
- **−$384.66** real P&L = 194% of the week's total loss (longs alone −$270), from 12 unique executed tickets of 81 shadow records.
- Drill-down:
  - Direction: SELL (+0.105 R/trade) beats BUY (+0.021) — longs drift to breakeven and bleed.
  - Entry type: **buy_limit +0.171** vs **sell_limit −0.036** vs market +0.053. Your limit-buy pullbacks are the only sub-slice that works; limit-sell pullbacks lose.
  - Action tier: REDUCED_CONFIDENCE (+0.063) ≈ FULL_ALLOW (+0.057) — no tier-based edge difference.
- Loss anatomy (the $-killers): every −1.00R loser came on a **BUY that entered with strongly positive CSM delta (≥ +1.1) that flipped to ≤ −1.2 by exit** (EURCAD ×4, EURGBP ×1). These are crowded-long exhaustion setups — the CSM sign flip is detectable at entry-adjacent time and is the single most predictive failure feature.
- **Fix direction:** the losers aren't random — they're CSM-alignment reversals. Entry confirms a strong-flow buy, then the flow dumps. Filter buys to `csm_delta_open > 0` AND require no prior same-side flow exhaustion (e.g., delta ≥ +2.5 at entry), or flip these to counter-flow fade entries.

### 4.3 M3 Breakout Retest Guard — breakeven after friction
- +9.13R on shadow, but **−$2.80 real** (25 unique tickets). R/trade +0.127 with CI kissing zero.
- Pending (limit) variants win (+$57 over 8 tks); market variants lose (−$60 over 17). Same pattern as M2: **the limit-entry versions of a setup are the ones that pay; market-chase versions give it back.**
- **Fix direction:** prefer/require limit entries; treat the market-execution flavor as the weak sub-model.

### 4.4 M4 Systemic Flow Continuation — best R/trade, worst data
- +0.243 R/trade is the highest of the four, but on **7 trades with 2 expired** and −$31.93 real. Cannot be validated or dismissed on this sample.

---

## 5. Cross-Mechanism Conditions (strongest signals in the data)

1. **Limit entries beat market entries in every mechanism where both exist** (M2 limit +0.17 vs market +0.05; M3 limit +0.14 vs market −0.02 aggregate). The system's own `PENDING_ORDERS_ENABLED` path is validated; the market-chase path is the drag.
2. **Trailing-SL exits are the only consistently profitable exit** — +$736.69 across 18 trades (avg +$40.93). TP exits +$150, manual +$85. Meanwhile "bot"-forced exits cost −$719 (avg −$51/trade) and raw SL exits −$451 on 3 trades (avg −$150).
3. **The overall payoff asymmetry is the core defect.** At 0.49 payoff you need a 68% win rate to break even; you have 63%. Improve either limb of the equation — cut avg loss or extend avg win — and the system flips positive.

---

## 6. Prioritized Recommendations

| # | Action | Target | Expected impact |
|---|---|---|---|
| 1 | **Fix the exit payoff asymmetry** — stop locking winners at +0.1–0.2R. Let grade-aware targets run (your 1.4–2.5R intended RR is fine; the executions exit at ~0.3R). Review `position_manager.py` BEP/trailing activation thresholds. | all mechanisms | Turns 0.49 payoff toward ≥1.0; biggest single lever |
| 2 | **Filter M2 BUY entries on CSM alignment sign** — reject BUY when `csm_delta_open ≥ +2.5` (post-exhaustion) or when CSM is opposed. This specifically removes the −1.0R EURCAD/EURGBP cluster. | M2 (and optionally M3) | Removes the largest loss concentration |
| 3 | **Default to limit entries; de-rate market-chase versions** — require `PENDING_ORDERS_ENABLED`; for M2/M3, skip the market-entry flavor or halve risk there. | M2, M3 | Converts two breakeven/negative mechanisms to positive |
| 4 | **Re-test the "bot" close path** (`-719` over 14) — identify which rule in `position_manager.py` is firing; it is closing more money than it saves. | all | ~−$720/quarter of avoidable bleed |
| 5 | **Collect more data before trusting M1/M4** — 12 and 7 trades respectively. These are the two best-per-trade mechanisms; protect them by not over-tuning, and gather ≥60 trades (per your AGENTS.md validity rule) before scaling size. | M1, M4 | Confirms the real edge |
| 6 | **De-duplicate the shadow tracker** (ticket-keyed) and compute R on filled price including friction — so the R-tracker and account stop disagreeing. | telemetry | Data integrity for all future reviews |

---

## 7. Against Your Stated Rules (AGENTS.md)

- **Anti-gambler's fallacy:** Respects marginal vs conditional separation — the CSM-shift finding (§4.2) is a conditional analysis (P(loss | delta flips)) vs the base-rate win %. ✔
- **Statistical validity:** Uses Wilson CI on the null; **no mechanism survives the test on this week's 46-trade sample** — this is explicitly flagged rather than overclaimed. ✔
- **No overclaim:** No "reversal 94%" style claims; all CIs stated. ✔
- **Sample-size honesty:** M1/M4 called "unproven" at 12 and 7 trades. ✔

---

## 8. Suggested Next Steps (post-approval)

1. Implement #1 and #2 in `position_manager.py` / `market_scanner.py` — highest value, lowest risk.
2. Implement #3 (limit-default) in `main.py` entry dispatch.
3. Fix shadow-tracker dedup (#6) so the next weekly review reconciles.
4. Re-run this scorecard after the fixes on the next batch of trades.