"""Test sizing: mode alokasi vs risk-based + clamp saldo free."""
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
logging.basicConfig(level=logging.ERROR)

import config
from unittest.mock import patch
import src.core.risk_engine as re_mod
from src.core.risk_engine import RiskEngine

fails = 0

def check(name, cond, detail=""):
    global fails
    if cond:
        print(f"  OK {name} {detail}")
    else:
        fails += 1
        print(f"  FAIL {name} {detail}")

# --- Skenario A: free $2.76, risk-based → qty 1286 (notional $3.45) harus CLAMP ---
print("A: free $2.76 — notional $3.45 > saldo → clamp")
with patch.object(re_mod.connector, "get_account_balance_usdt", lambda: 2.76), \
     patch.object(re_mod.connector, "get_free_usdt", lambda: 2.76), \
     patch.object(re_mod.connector, "round_qty", lambda s, q: round(q, 0)), \
     patch.object(re_mod.connector, "validate_order", lambda s, q, p, sl_pct=None: (True, "ok")):
    config.POSITION_ALLOCATION_PCT = 0
    qty, msg = RiskEngine().get_effective_qty(0.0026785, 1.2)
    notional = qty * 0.0026785
    print(f"   qty={qty} notional=${notional:.4f} | {msg}")
    check("notional <= free (2.76)", notional <= 2.76, f"({notional:.3f})")
    check("clamp ter-trigger", "clamp" in msg)

# --- Skenario B: free $15, alokasi 50% → $7.5 tidak perlu clamp ---
print("B: free $15, alokasi 50% — $7.5 < saldo → no clamp")
with patch.object(re_mod.connector, "get_account_balance_usdt", lambda: 15.0), \
     patch.object(re_mod.connector, "get_free_usdt", lambda: 15.0), \
     patch.object(re_mod.connector, "round_qty", lambda s, q: round(q, 0)), \
     patch.object(re_mod.connector, "validate_order", lambda s, q, p, sl_pct=None: (True, "ok")):
    config.POSITION_ALLOCATION_PCT = 50
    qty, msg = RiskEngine().get_effective_qty(0.0027, 1.2)
    notional = qty * 0.0027
    print(f"   qty={qty} notional=${notional:.2f} | {msg}")
    check("notional ~ 7.5", abs(notional - 7.5) < 0.1, f"({notional:.2f})")
    check("no clamp", "clamp" not in msg)

# --- Skenario C: free $2.76, alokasi 50% → $1.38 tidak perlu clamp ---
print("C: free $2.76, alokasi 50% — $1.38 < saldo → no clamp")
with patch.object(re_mod.connector, "get_account_balance_usdt", lambda: 2.76), \
     patch.object(re_mod.connector, "get_free_usdt", lambda: 2.76), \
     patch.object(re_mod.connector, "round_qty", lambda s, q: round(q, 0)), \
     patch.object(re_mod.connector, "validate_order", lambda s, q, p, sl_pct=None: (True, "ok")):
    config.POSITION_ALLOCATION_PCT = 50
    qty, msg = RiskEngine().get_effective_qty(0.0027, 1.2)
    notional = qty * 0.0027
    print(f"   qty={qty} notional=${notional:.2f} | {msg}")
    check("notional ~ 1.38", abs(notional - 1.38) < 0.05, f"({notional:.2f})")
    check("no clamp", "clamp" not in msg)

config.POSITION_ALLOCATION_PCT = 0
print("\n" + ("SEMUA PASS" if fails == 0 else f"{fails} FAIL"))
sys.exit(1 if fails else 0)
