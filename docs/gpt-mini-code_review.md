# GPT-Mini Code Review & Integration Plan

Purpose
- Consolidate everything needed to integrate xaubot-ai (ML + advanced exits) with XAU-60 (execution, account management, UI) into a single actionable plan and artifact list.
- Provide signal API, adapters, tests, deployment options, and a prioritized checklist so you (and a developer) can move from POC → demo → live safely.

Context & Decision
- Short: integrate xaubot-ai signals and advanced exit logic into XAU-60’s execution surface, keeping XAU-60 as the primary execution and RiskManager authority. Use xaubot-ai as a signal & advanced-exit provider during POC/paper-phase.
- Rationale: combines proven alpha (xaubot-ai) with robust execution and operational safety (XAU-60).

Goals
1. Non-invasive POC: xaubot-ai publishes signals; XAU-60 consumes them and simulates orders (dry-run). No live trading until validated.
2. Reproduce backtests & metrics for both codebases and compare.
3. Harden RiskManager & ensure single source of truth for trade sizing and safety.
4. Gradual migration: extract stable modules as shared libs, centralize, test, then deploy to demo/live.

High-level architecture (POC)
- xaubot-ai (producer): runs ML + detectors, writes signals to a JSON L2 file or Redis pub/sub.
- XAU-60 (consumer): polls JSON/Redis, validates signals against RiskManager, places simulated orders via mt5_mock / dry-run API.
- Shared: RiskManager interface implemented in XAU-60; xaubot-ai suggestions are advisory only until validated.

Signal JSON schema (signals.json / Redis message)
- Each message is a single-line JSON object. Example array or newline-delimited JSON allowed. Fields:
  {
    "timestamp": "2026-08-07T12:34:56Z",
    "symbol": "XAUUSD",
    "side": "buy",             // buy|sell|none
    "confidence": 0.87,         // 0.0-1.0
    "tp_atr_mult": 3.0,         // target as ATR multiple
    "sl_atr_mult": 1.5,         // stop as ATR multiple
    "suggested_risk_pct": 0.5,  // percent of account risk (0-100)
    "suggested_lots": null,     // optional explicit lots (broker-specific)
    "regime": "bull",         // text tag from HMM detector
    "notes": "trajectory_conf=0.8;reason=momentum+news"
  }

Producer: minimal adapter (xaubot-ai)
- Location suggestion: external_repos/xaubot-ai/adapters/producer_to_x60.py
- Responsibilities: load model loop, format signal JSON, write to signals file or push to Redis.

Example (pseudo-Python producer using file):

import json
from pathlib import Path

OUT = Path("/tmp/xaubot_signals.jsonl")  # or repo shared folder

def publish_signal(signal: dict):
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(signal, ensure_ascii=False) + "\n")

# when model emits a signal:
signal = {
    "timestamp": "2026-08-07T12:34:56Z",
    "symbol": "XAUUSD",
    "side": "buy",
    "confidence": 0.87,
    "tp_atr_mult": 3.0,
    "sl_atr_mult": 1.5,
    "suggested_risk_pct": 0.5,
    "regime": "bull",
    "notes": "auto"
}
publish_signal(signal)

Consumer: minimal adapter (XAU-60)
- Location suggestion: external_repos/XAU-60/adapters/consume_xaubot_signal.py
- Responsibilities: poll signals file (or subscribe Redis), parse JSON lines, dedupe by timestamp+symbol, validate via RiskManager, convert ATR-multipliers → SL/TP pips using XAU-60 ATR calc, compute lots (prefer XAU-60 position sizing), and call trade_executor.place_order(...) in dry-run mode.

Example (pseudo-Python consumer):

import json
from pathlib import Path
from datetime import datetime

IN = Path("/tmp/xaubot_signals.jsonl")
seen = set()

def load_new_signals():
    if not IN.exists():
        return []
    out = []
    for line in IN.read_text(encoding='utf-8').splitlines():
        try:
            s = json.loads(line)
            key = (s.get("timestamp"), s.get("symbol"))
            if key in seen:
                continue
            seen.add(key)
            out.append(s)
        except Exception:
            continue
    return out

# For each signal: compute sl/tp using ATR, call risk manager, call place_order(dry_run=True)

RiskManager (single source of truth)
- Location suggestion: external_repos/XAU-60/core/risk_manager.py (primary)
- Interface methods:
  - can_open_position(symbol, side, suggested_risk_pct, suggested_lots) -> (bool, reason)
  - compute_lots_from_risk(account_balance, sl_pips_or_usd, max_risk_pct) -> lots
  - register_open_position(ticket, metadata)
  - register_close_position(ticket, metadata)
  - check_daily_limits() -> (bool, message)
  - emergency_disable_all("reason")

- Implementation notes:
  - Use XAU-60's existing logic for correlation limits, daily loss cap, max concurrent positions.
  - During POC: enforce very conservative caps (max_risk_per_trade=0.5%, max_positions=1-2).

Data harmonization checklist
- ATR window: agree on same ATR multiplier and period (e.g., M15 ATR 14 period). Add adapter to convert polars -> pandas if necessary.
- Timezone: ensure both use UTC or the same timezone when producing timestamps.
- Candle alignment: produce features from same bars (e.g., use MT5 M15 close aligned at 00:00). Add an adapter function to resample/align candles.

Backtest reproduction steps
1. For xaubot-ai: run the principal backtest script (example paths found in repo):
   - python backtests/backtest_01_smc_only.py
   - Confirm model files exist in models/*.pkl; if missing, locate or re-train using training scripts in docs/scripts or training pipeline.
2. For XAU-60: run its backtest module (look for backtest runner under core/backtest or cli):
   - python -m core.backtest --strategy <strategy_name> --symbol XAUUSD --from YYYY-MM-DD --to YYYY-MM-DD
3. Produce these metrics: Profit Factor, Net Profit, CAGR, Sharpe (ann), Win Rate, Avg Win/Loss, Max DD, Trades per period.
4. Reproduce on author dataset (if provided) and on an out-of-sample holdout.

Runnable commands (examples)
- Create virtualenv & install deps (do in each repo):
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt

- xaubot-ai backtest:
  cd external_repos\xaubot-ai
  python backtests/backtest_01_smc_only.py

- XAU-60 Streamlit UI (dry-run):
  cd external_repos\XAU-60
  streamlit run ui/app.py

- XAU-60 dry-run CLI (if exists):
  python main.py --dry-run --symbol XAUUSD --config config.yml

Environment variables (.env keys to check or create)
- For both repos, copy .env.example → .env and fill credentials for demo accounts.
- Keys typically: MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DATABASE_URL (for xaubot if using Postgres), REDIS_URL (if using Redis), LOG_LEVEL.

Testing & Validation checklist (must pass before live)
1. Backtest parity: reproduce reported PF on provided dataset.
2. Unit tests: run pytest for both repos (pip install -e . if needed).
3. Integration smoke: run producer and consumer in dry-run for 24-72 hours and log all actions.
4. Forward-demo: paper trade for 4–8 weeks; track per-trade telemetry.
5. Fault injection: simulate MT5 disconnects, emergency_close, and ensure system behaves.

Metrics to capture every trade
- timestamp, symbol, side, lots, entry_price, sl_price, tp_price, exit_price, entry_atr, exit_atr, pnl, duration_minutes, confidence, regime, trade_id, order_latency_ms
- Aggregate daily: net_profit, daily_drawdown, max_open_positions, trades_count

Monitoring & Alerts
- Telegram/Discord alerts on: emergency_close, daily loss threshold reached, model failure, too many rejects, reconnect failures.
- Health check endpoint (if using HTTP) returning JSON {status: ok, latest_signal_ts, model_ok, mt5_ok}

Deployment options (ranked)
- Quick POC: File bridge (JSONL) — fastest, low infra.
- Clean separation: Redis pub/sub or REST API — good for reliability and decoupling.
- Full microservices: Docker Compose for xaubot-ai (ML service) + XAU-60 container — production-ready.

Files to add (recommended)
- external_repos/xaubot-ai/adapters/producer_to_x60.py  (producer code)
- external_repos/XAU-60/adapters/consume_xaubot_signal.py (consumer code)
- external_repos/XAU-60/core/risk_manager.py (centralized RiskManager if missing)
- scripts/reproduce_backtests.sh or .ps1 (commands for reproducibility)
- docs/INTEGRATION_README.md (summary + runbook)
- gpt-mini-code_review.md (this file)

CI suggestions
- Add GitHub Actions workflow that:
  - Installs deps in parallel for both repos (separate jobs)
  - Runs unit tests and lint
  - Runs minimal integration smoke test (producer writes one sample, consumer reads & simulates)
  - Artifacts: backtest reports (CSV/JSON)

Timeline & rough effort estimate
- POC (file-bridge signals + consumer dry-run): 1–3 days
- Reproduce backtests + unit tests: 3–7 days
- Paper/demo run + monitoring: 4–8 weeks
- Harden & merge modules, CI, deploy to production: 4–8 weeks after successful demo

Immediate prioritized TODOs (start here)
1. Create signals JSONL bridge in xaubot-ai and a consumer in XAU-60 (POC). Priority: P0.
2. Reproduce main backtests for xaubot-ai. Priority: P0.
3. Implement RiskManager wrapper in XAU-60 and ensure it is consulted for every external signal. Priority: P0.
4. Configure Telegram alerts for emergency close & daily loss. Priority: P1.
5. Run integration smoke for 48–72 hours (dry-run). Priority: P0.

Assumptions
- You have access to the repo checkouts at external_repos/XAU-60 and external_repos/xaubot-ai inside this project (already cloned).
- You will run live money only after passing the validation checklist and paper-demo.

If you want I will:
- Create the producer and consumer adapter skeleton files (producer_to_x60.py and consume_xaubot_signal.py) in both repos and push them into external_repos/ now.
- Or start by reproducing the xaubot-ai backtest and packaging its output.

Pick one immediate action and I will implement it now and update this file with run outputs and next steps.