# GoldSnD Optimization & Backtesting Guide

To get the best performance from this Expert Advisor, follow this structured optimization process.

## 1. Environment Configuration
- **Symbol**: XAUUSD
- **Timeframe**: H1
- **Modeling**: "Every tick based on real ticks" (Crucial for False Break logic).
- **History**: At least 1-2 years of data.

## 2. Optimization Workflow

### Phase 1: Risk & Reward (Low Overfit Risk)
Optimize these first to find the most stable R:R for Gold.
- `InpTP1_RR`: [1.0 to 2.0, step 0.2]
- `InpTP3_RR`: [2.5 to 5.0, step 0.5]
- `InpSLBufferATR`: [0.3 to 1.0, step 0.1]

### Phase 2: Signal Sensitivity (Medium Overfit Risk)
Refine how the EA identifies zones and sweeps.
- `InpImpulseATRMult`: [2.0 to 3.5, step 0.25]
- `InpFBMinPips`: [3.0 to 10.0, step 1.0]
- `InpEqualTolPips`: [3.0 to 8.0, step 1.0]

### Phase 3: Freshness & Age
- `InpZoneMaxAge`: [30 to 80, step 10]

## 3. Avoiding Overfitting (Curve Fitting)
- **Walk-Forward Analysis**: Use the 70/30 rule. Optimize on 70% of data (In-Sample) and validate on the remaining 30% (Out-of-Sample).
- **Trade Count**: Ensure the result has at least 100+ trades per year. Results with < 20 trades are statistically insignificant.
- **Profit Factor**: Look for a Profit Factor between **1.4 and 2.2**. Higher values often indicate overfitting to specific historical spikes.

## 4. XAUUSD Calibration Notes
Gold is highly volatile. If the EA skips too many trades:
1. Decrease `InpImpulseATRMult` (makes zones easier to find).
2. Decrease `InpFBMinPips` (requires smaller sweeps).
3. Increase `InpEqualTolPips` (wider definition of "equal" highs).

If the EA loses too often on "Fakeouts":
1. Increase `InpFBWickBodyRatio` (requires stronger rejection candles).
2. Increase `InpFBMinPips` (requires deeper sweeps before reversal).
