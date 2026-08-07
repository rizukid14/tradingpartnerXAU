import sys
import os
# Force UTF-8 encoding for standard output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
import MetaTrader5 as mt5
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
import config

import mt5_connector as connector
from macro_analyst import MacroAnalyst


def main():
    print("=" * 60)
    print("             TEST RUN: MACRO & TIMEFRAME ANALYST          ")
    print("=" * 60)
    
    # Initialize connection to MT5
    if not connector.initialize_mt5():
        print("❌ Gagal terhubung ke MetaTrader 5 terminal.")
        sys.exit(1)
        
    print("✅ Terhubung ke MT5.")
    
    try:
        # Instantiate MacroAnalyst
        analyst = MacroAnalyst()
        
        print("\n--- 1. Check Session ---")
        current_session = analyst.get_current_session()
        print(f"Sesi trading aktif saat ini (WIB): {current_session}")
        
        print("\n--- 2. Running forced macro analysis updates (queries LLMs) ---")
        # Run and force update cache
        analyst.check_and_update_analysis(force=True)
        
        print("\n--- 3. Check cached analysis outcomes ---")
        print(f"Cached session analyzed: {analyst.cache.get('last_fundamental_session')}")
        print("Timeframe analyses cache contents:")
        for tf_name, tf_data in analyst.cache.get("timeframe_analysis", {}).items():
            print(f"- {tf_name} (Last candle time: {tf_data.get('last_candle_time')}):")
            print(f"  Analysis: {tf_data.get('analysis')}")
            
        print("\n--- 4. Formatted Macro Context String for M5 Execution ---")
        context_str = analyst.get_macro_context()
        print(context_str if context_str else "⚠️ Macro context is empty!")
        
        print("\n--- 5. Verify caching persistency on disk ---")
        cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "analysis_cache.json")
        if os.path.exists(cache_path):
            print(f"✅ Cache file successfully written to disk at: {cache_path}")
            print(f"Cache file size: {os.path.getsize(cache_path)} bytes")
        else:
            print("❌ Cache file not found on disk!")
            
    except Exception as e:
        print(f"❌ Terjadi error selama pengujian: {e}")
        
    finally:
        mt5.shutdown()
        print("\n🔌 MT5 connection shutdown.")
        print("=" * 60)

if __name__ == "__main__":
    main()
