"""Verifikasi ambang hold-streak 0.60."""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.ERROR)

from src.core import consensus

# Skenario nyata dari log: streak 18, Gemini BUY 0.65, OpenAI HOLD
p = {"OpenAI": {"signal": "HOLD", "confidence": 0.73},
     "Gemini": {"signal": "BUY", "confidence": 0.65, "sl_pct": 1.0, "tp_pct": 2.0}}
d = consensus.calculate_consensus(p, hold_streak=18)
print(f"TAO/AAVE case (streak 18, BUY 0.65): approved={d['approved']} signal={d['signal']}")
print(f"  reasoning: {d['reasoning'][:100]}")
assert d["approved"] and d["signal"] == "BUY", "harus approve sekarang"

# BUY 0.55 masih harus HOLD (di bawah 0.60)
p2 = {"OpenAI": {"signal": "HOLD", "confidence": 0.73},
      "Gemini": {"signal": "BUY", "confidence": 0.55, "sl_pct": 1.0, "tp_pct": 2.0}}
d2 = consensus.calculate_consensus(p2, hold_streak=18)
print(f"BUY 0.55 case: approved={d2['approved']} (harus False)")
assert not d2["approved"], "0.55 harus tetap HOLD"

print("OK")
