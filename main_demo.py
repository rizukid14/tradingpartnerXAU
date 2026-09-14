"""
Trading Partner - M5 Demo Testing Runner
Runs concurrently with the Live bot without process collisions or IPC timeouts.
Uses the isolated portable MT5 terminal at C:/Users/Daffa/MT5_Demo/terminal64.exe.
"""
import os
import sys

# 1. Force DEMO environment configuration file BEFORE importing config
os.environ["ENV_FILE"] = ".env.demo"

# 2. Force UTF-8 encoding for standard output on Windows
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

if __name__ == "__main__":
    print("================================================================================")
    print("  TRADING PARTNER - DEMO M5 INSTANCE RUNNER")
    print("  Target Terminal: C:/Users/Daffa/MT5_Demo/terminal64.exe (/portable)")
    print("  Account        : VTMarkets-Demo (#1157958)")
    print("  Timeframe      : M5 Fast Scanner")
    print("================================================================================")
    
    import main
    main.main()
