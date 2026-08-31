import sys
import os
# Force UTF-8 encoding for standard output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
import config
from src.core import mt5_connector as connector
from src.analytics.macro_strategic_engine import macro_strategic_engine


def main():
    print("=" * 60)
    print("       TEST RUN: PURE QUANT MACRO STRATEGIC ENGINE (MSE)   ")
    print("=" * 60)
    
    # Initialize connection to MT5
    if not connector.initialize_mt5():
        print("[X]  Gagal terhubung ke MetaTrader 5 terminal.")
        sys.exit(1)
        
    print("[OK]  Terhubung ke MT5.")
    
    try:
        sym = "GBPUSD"
        print(f"\n--- 1. Calculate MSE 6-TF Directive for {sym} ---")
        strat_dir = macro_strategic_engine.get_directive(sym)
        if strat_dir:
            print(f"[OK] Directive calculated: {strat_dir.daily_macro_bias} ({strat_dir.macro_bias_score:+.2f})")
            print(f"Action Tier: {strat_dir.action_tier} | Circuit Breaker: {strat_dir.hard_circuit_breaker}")
            print(f"SBR/RBS: D1 SBR {strat_dir.macro_sbr_d1} / RBS {strat_dir.macro_rbs_d1}")
            print(f"Stations: Floor {strat_dir.sub_floor_50} / Ceil {strat_dir.sub_ceiling_50}")
            print(f"TP1: {strat_dir.tp1_price} | TP2: {strat_dir.tp2_price} | SL: {strat_dir.intraday_sl_price}")
        else:
            print("[WARN] Directive returned None")
            
    except Exception as e:
        print(f"[X]  Terjadi error selama pengujian: {e}")
        
    finally:
        mt5.shutdown()
        print("\n[PLUG]  MT5 connection shutdown.")
        print("=" * 60)

if __name__ == "__main__":
    main()
