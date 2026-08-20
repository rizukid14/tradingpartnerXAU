# GoldSnD MT5 Expert Advisor (XAUUSD)

A professional price-action based trading robot for MetaTrader 5, specializing in XAUUSD (Gold).

## 📊 Strategy Overview
The EA implements a disciplined **Supply & Demand + Liquidity Pool + False Break** strategy. It focuses on institutional footprints rather than lagging indicators.

- **Layer 1 (SnD Engine)**: Identifies fresh supply/demand zones based on impulse candles and base structure.
- **Layer 2 (Liquidity Pool)**: Scans for equal highs/lows where retail stop losses cluster.
- **Layer 3 (False Break)**: Triggers entries only after a liquidity sweep and strong rejection within a valid zone.
- **Layer 4 (Bias)**: Only trades in alignment with H4 and D1 market structure.
- **Layer 5 (Risk)**: Conservative 1.5% risk per trade, partial closes at 1.5R, and dynamic ATR-based trailing.

## 🚀 Setup Instructions
1. **Copy Files**: Place the `GoldSnD_EA.mq5` file in your `MQL5/Experts` folder and the `Include/` folder content into `MQL5/Include/GSnD/` (update include paths if necessary).
2. **Chart Setting**: Open a **XAUUSD H1** chart.
3. **Enable Algo Trading**: Click the "Algo Trading" button in the MT5 toolbar.
4. **Economic Calendar**: Ensure your MT5 has access to the Economic Calendar (usually default).
5. **Attach EA**: Drag `GoldSnD_EA` onto the chart.

## ⚙️ Key Parameters
| Parameter | Default | Description |
|-----------|---------|-------------|
| `InpRiskPercent` | 1.5% | Risk based on account equity per trade. |
| `InpMaxDailyLoss` | 5.0% | Circuit breaker level to pause the EA for the day. |
| `InpImpulseATRMult` | 2.5 | Minimum size of the impulse move (x ATR). |
| `InpEqualTolPips` | 5.0 | Pip tolerance for "equal" highs or lows. |
| `InpFBMinPips` | 5.0 | Minimum sweep depth before reversal is considered. |

## 🛡️ Risk Management
- **Partial Close**: 50% of the position is closed at 1.5R profit.
- **Trailing Stop**: Activated only after TP1 is hit, trailing by 1x ATR.
- **Daily Loss Limit**: EA stops trading if equity drops 5% below the start of the day balance.
- **Max Trades**: Maximum 2 simultaneous positions to avoid over-exposure.

## ⚠️ Disclaimer
Trading Gold involves significant risk. This EA is a tool to automate a specific strategy. Always test on a Demo account before using live funds.
