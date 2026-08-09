"""Test logika consensus HOLD-streak. Jalankan dari binance_bot: py tests/test_hold_streak.py"""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.ERROR)

from src.core import consensus

passes = 0
fails = 0

def check(name, cond, detail=""):
    global passes, fails
    if cond:
        passes += 1
        print(f"  ✅ {name} {detail}")
    else:
        fails += 1
        print(f"  ❌ {name} {detail}")

# --- Skenario 1: 2/2 BUY normal (tanpa hold streak) ---
print("Skenario 1: 2/2 BUY normal, streak 0")
p = {"OpenAI": {"signal": "BUY", "confidence": 0.6, "sl_pct": 1.0, "tp_pct": 2.0},
     "Gemini": {"signal": "BUY", "confidence": 0.65, "sl_pct": 1.2, "tp_pct": 2.2}}
d = consensus.calculate_consensus(p, hold_streak=0)
check("2/2 BUY approve", d["approved"] and d["signal"] == "BUY", f"(score {d['score']})")

# --- Skenario 2: HOLD streak 5 + 1 BUY kuat (0.70) → approve ---
print("Skenario 2: hold streak 5, 1 BUY conf 0.70")
p = {"OpenAI": {"signal": "BUY", "confidence": 0.70, "sl_pct": 1.0, "tp_pct": 2.0},
     "Gemini": {"signal": "HOLD", "confidence": 0.45}}
d = consensus.calculate_consensus(p, hold_streak=5)
check("1 BUY kuat saat streak approve", d["approved"] and d["signal"] == "BUY",
      f"(reason: {d['reasoning'][:60]})")

# --- Skenario 3: HOLD streak 5, BUY 0.64 — lolos (ambang sekarang 0.60) ---
print("Skenario 3: hold streak 5, 1 BUY conf 0.64 (>= 0.60, lolos)")
p = {"OpenAI": {"signal": "BUY", "confidence": 0.64, "sl_pct": 1.0, "tp_pct": 2.0},
     "Gemini": {"signal": "HOLD", "confidence": 0.45}}
d = consensus.calculate_consensus(p, hold_streak=5)
check("BUY 0.64 lolos", d["approved"] and d["signal"] == "BUY", f"(score {d['score']})")

# --- Skenario 3b: HOLD streak 5, BUY 0.55 (< 0.60) → tetap HOLD ---
print("Skenario 3b: hold streak 5, 1 BUY conf 0.55 (< 0.60)")
p = {"OpenAI": {"signal": "BUY", "confidence": 0.55, "sl_pct": 1.0, "tp_pct": 2.0},
     "Gemini": {"signal": "HOLD", "confidence": 0.45}}
d = consensus.calculate_consensus(p, hold_streak=5)
check("BUY 0.55 tetap HOLD", not d["approved"], f"(score {d['score']})")

# --- Skenario 4: HOLD streak 5 tapi 2/2 HOLD → HOLD ---
print("Skenario 4: hold streak 5, 2/2 HOLD")
p = {"OpenAI": {"signal": "HOLD", "confidence": 0.8},
     "Gemini": {"signal": "HOLD", "confidence": 0.45}}
d = consensus.calculate_consensus(p, hold_streak=5)
check("2/2 HOLD tetap HOLD", not d["approved"])

# --- Skenario 5: hold streak 4 (belum 5) + 1 BUY kuat → tetap HOLD ---
print("Skenario 5: hold streak 4, 1 BUY conf 0.70 (belum aktif)")
p = {"OpenAI": {"signal": "BUY", "confidence": 0.70, "sl_pct": 1.0, "tp_pct": 2.0},
     "Gemini": {"signal": "HOLD", "confidence": 0.45}}
d = consensus.calculate_consensus(p, hold_streak=4)
check("streak 4 belum aktif → HOLD", not d["approved"])

# --- Skenario 6: hold streak 5, 1 BUY 0.80 → approve + SL/TP dari proposer BUY ---
print("Skenario 6: hold streak 5, BUY 0.80 — SL/TP diambil dari proposer BUY")
p = {"OpenAI": {"signal": "BUY", "confidence": 0.80, "sl_pct": 1.5, "tp_pct": 3.0},
     "Gemini": {"signal": "HOLD", "confidence": 0.45}}
d = consensus.calculate_consensus(p, hold_streak=5)
check("approve + SL/TP benar", d["approved"] and d["sl_pct"] == 1.5 and d["tp_pct"] == 3.0,
      f"(SL {d['sl_pct']} TP {d['tp_pct']})")

print(f"\nHasil: {passes} pass, {fails} fail")
sys.exit(1 if fails else 0)
