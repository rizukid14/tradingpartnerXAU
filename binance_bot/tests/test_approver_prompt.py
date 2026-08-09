"""Verifikasi build_approval_prompt — approver dapat data mentah + instruksi independen."""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.ERROR)

import pandas as pd
import numpy as np

from src.core import llm_client

# Data dummy
np.random.seed(1)
n = 50
idx = pd.date_range("2026-08-09 00:00", periods=n, freq="5min")
df = pd.DataFrame({
    "time": idx, "open": np.random.rand(n) * 0.0001 + 0.0026,
    "high": np.random.rand(n) * 0.0001 + 0.0027, "low": np.random.rand(n) * 0.0001 + 0.0025,
    "close": np.random.rand(n) * 0.0001 + 0.0026, "volume": np.random.rand(n) * 1000,
})
ticker = {"price": 0.00268, "bid": 0.002679, "ask": 0.002681,
          "spread_usd": 0.000002, "spread_pct": 0.037}
pa = {"signal": "BUY", "confidence": 0.65, "sl_pct": 1.0, "tp_pct": 2.0, "reasoning": "sweep support"}
pb = {"signal": "HOLD", "confidence": 0.73, "sl_pct": 0.5, "tp_pct": 0.9, "reasoning": "below EMA"}

prompt = llm_client.build_approval_prompt("PUMPUSDT", df, ticker, 2.76, pa, pb)

checks = [
    ("Ada 40 candle", "LAST 40 CANDLES" in prompt),
    ("Ada indikator", "RSI" in prompt),
    ("Ada MTF", "HIGHER" in prompt or "15M" in prompt or "H1" in prompt),
    ("Ada market structure", "LIQUIDITY" in prompt.upper() or "SWEEP" in prompt.upper() or "SUPPORT" in prompt.upper()),
    ("Instruksi independen", "analyze the raw market data" in prompt.lower()),
    ("Proposal hanya referensi", "PROPOSAL A" in prompt),
    ("Instruksi jangan cuma setuju", "merely agree or disagree" in prompt.lower()),
]
ok = True
for name, cond in checks:
    print(("OK " if cond else "FAIL ") + name)
    ok = ok and cond

# Estimasi token
print(f"\nTotal prompt: {len(prompt)} chars (~{len(prompt)//4} token)")
print("SEMUA PASS" if ok else "ADA FAIL")
sys.exit(0 if ok else 1)
