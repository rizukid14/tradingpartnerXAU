"""
shadow_audit.py — Root CLI Command for Quant Shadow Executive Audit & Interactive Dashboard.

Usage:
    py shadow_audit.py
    py shadow_audit.py --open
    py shadow_audit.py --days 3
    py shadow_audit.py --out docs/custom_audit.html
"""

import os
import sys
import argparse
import webbrowser
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)

from src.core import mt5_connector as connector
from src.analytics.shadow_audit_engine import ShadowAuditEngine, DEFAULT_HTML_OUTPUT

WIB = ZoneInfo("Asia/Jakarta")


def parse_args():
    parser = argparse.ArgumentParser(description="Quant Shadow Executive Audit & Interactive Dashboard")
    parser.add_argument("--days", type=int, default=None, help="Lookback window in days (default: all history)")
    parser.add_argument("--out", type=str, default=DEFAULT_HTML_OUTPUT, help="Path for HTML dashboard output")
    parser.add_argument("--no-open", action="store_true", help="Do not open HTML in browser automatically")
    parser.add_argument("--json", action="store_true", help="Print summary JSON to stdout")
    return parser.parse_args()


def print_ansi_summary(audit_res: dict, html_path: str):
    deb = audit_res.get("debiased", {})
    raw = audit_res.get("raw", {})
    mt5 = audit_res.get("mt5_summary", {})
    ts = audit_res.get("timestamp", datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"))

    # ANSI Colors
    C_CYAN = "\033[96m"
    C_GREEN = "\033[92m"
    C_RED = "\033[91m"
    C_AMBER = "\033[93m"
    C_PURPLE = "\033[95m"
    C_BOLD = "\033[1m"
    C_RESET = "\033[0m"

    print(f"\n{C_CYAN}{C_BOLD}+-- [ QUANT SHADOW EXECUTIVE AUDIT ] ------------------------------------+{C_RESET}")
    print(f"{C_CYAN}|{C_RESET} Waktu Snapshot : {ts} │ Lookback: {audit_res.get('lookback_days')}                     ")
    print(f"{C_CYAN}+------------------------------------------------------------------------+{C_RESET}")
    
    # 1. Dual Mode Comparison
    print(f"{C_CYAN}|{C_RESET} • {C_BOLD}Sample Size{C_RESET}   : {C_GREEN}{deb.get('total_resolved', 0)} Resolved Legs{C_RESET} (De-biased) vs {raw.get('total_resolved', 0)} Raw Triggers")
    print(f"{C_CYAN}|{C_RESET} • {C_BOLD}Active Open{C_RESET}   : {deb.get('active_count', 0)} Active Floating ({deb.get('pending_count', 0)} Pending Limits)")
    
    # 2. Real MT5 Performance
    mt5_net = mt5.get("net_profit_usd", 0.0)
    mt5_col = C_GREEN if mt5_net >= 0 else C_RED
    print(f"{C_CYAN}|{C_RESET} • {C_BOLD}Live MT5 Deals{C_RESET}: {mt5.get('total_deals', 0)} Deals │ Win: {mt5.get('winrate_pct', 0.0)}% │ Net: {mt5_col}${mt5_net:+.2f}{C_RESET} (PF {mt5.get('profit_factor', 0.0)})")

    # 3. Opportunity Cost
    lost_r = deb.get("lost_profit_r", 0.0)
    saved_r = deb.get("capital_saved_r", 0.0)
    print(f"{C_CYAN}|{C_RESET} • {C_BOLD}Opportunity{C_RESET}   : {C_PURPLE}Lost Profit: {lost_r:+.2f}R{C_RESET} │ {C_GREEN}Saved Drawdown: +{saved_r:.2f}R{C_RESET}")

    # 4. Mechanism Top Edge
    mechs = deb.get("mechanism_stats", {})
    sorted_mechs = sorted(mechs.items(), key=lambda x: x[1].get("net_r", 0.0), reverse=True)
    if sorted_mechs:
        top_m_name, top_m = sorted_mechs[0]
        print(f"{C_CYAN}|{C_RESET} • {C_BOLD}Top Edge Mech{C_RESET} : {top_m_name} ({top_m.get('winrate', 0.0)}% Winrate │ {C_GREEN}{top_m.get('net_r'):+.2f}R{C_RESET} │ PF {top_m.get('profit_factor')})")

    # 5. BEP Efficiency
    bep_pct = deb.get("bep_efficiency_pct", 0.0)
    bep_saved = deb.get("bep_saved_count", 0)
    bep_stolen = deb.get("bep_stolen_count", 0)
    print(f"{C_CYAN}|{C_RESET} • {C_BOLD}BEP Efficiency{C_RESET}: {C_AMBER}{bep_pct}% Saved{C_RESET} ({bep_saved} Saved vs {bep_stolen} Premature Exit)")

    print(f"{C_CYAN}+------------------------------------------------------------------------+{C_RESET}")
    print(f" {C_GREEN}[OK]{C_RESET} Standalone Executive Dashboard: {C_BOLD}{html_path}{C_RESET}")


def main():
    args = parse_args()

    # Safely connect MT5 if available (offline-safe)
    try:
        connector.initialize_mt5()
    except Exception:
        pass

    engine = ShadowAuditEngine(lookback_days=args.days)
    engine.load_data(mt5_connector=connector)

    audit_res = engine.generate_executive_audit()
    html_path = engine.render_html_dashboard(output_path=args.out)

    if args.json:
        import json
        print(json.dumps(audit_res, indent=2))
    else:
        print_ansi_summary(audit_res, html_path)

    if not args.no_open:
        try:
            print(f" [BROWSER] Auto-launching dashboard in default web browser...")
            webbrowser.open(os.path.abspath(html_path))
        except Exception:
            pass


if __name__ == "__main__":
    main()
