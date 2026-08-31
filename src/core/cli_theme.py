"""
CLI Theme & Styling Helper for Trading Bot Terminal
Provides ANSI colors, sleek box-drawing borders, badges, and progress bars.
Fully compatible with Windows 10/11 Terminal & Linux/macOS.
"""

import sys
import shutil
import unicodedata
import textwrap
from datetime import datetime
from zoneinfo import ZoneInfo

# Ensure stdout uses UTF-8 on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


class UI:
    # Styles
    RST = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDER = "\033[4m"

    # Foreground Colors
    BLACK = "\033[30m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    PURPLE = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    # Background Colors
    BG_RED = "\033[41m\033[97m\033[1m"
    BG_GREEN = "\033[42m\033[97m\033[1m"
    BG_YELLOW = "\033[43m\033[30m\033[1m"
    BG_BLUE = "\033[44m\033[97m\033[1m"
    BG_MAGENTA = "\033[45m\033[97m\033[1m"
    BG_PURPLE = "\033[45m\033[97m\033[1m"
    BG_CYAN = "\033[46m\033[97m\033[1m"
    BG_DARK = "\033[100m\033[97m\033[1m"

    @classmethod
    def badge_live(cls):
        return f"{cls.BG_GREEN} LIVE {cls.RST}"

    @classmethod
    def badge_dry(cls):
        return f"{cls.BG_YELLOW} DRY RUN {cls.RST}"

    @classmethod
    def badge_signal(cls, sig):
        sig = str(sig).upper()
        if sig == "BUY":
            return f"{cls.BG_GREEN} BUY {cls.RST}"
        elif sig == "SELL":
            return f"{cls.BG_RED} SELL {cls.RST}"
        else:
            return f"{cls.BG_DARK} HOLD {cls.RST}"

    @classmethod
    def badge_verdict(cls, verdict):
        v = str(verdict or "").upper()
        if v == "APPROVE":
            return f"{cls.GREEN}[APPROVE]{cls.RST}"
        elif v == "REVISE":
            return f"{cls.YELLOW}[REVISE]{cls.RST}"
        elif v == "REJECT":
            return f"{cls.RED}[REJECT]{cls.RST}"
        elif v:
            return f"{cls.CYAN}[{v}]{cls.RST}"
        return ""

    @classmethod
    def badge_pnl(cls, pnl):
        if pnl > 0.04:
            return f"{cls.GREEN}+${pnl:.2f}{cls.RST}"
        elif pnl < -0.04:
            return f"{cls.RED}-${abs(pnl):.2f}{cls.RST}"
        else:
            return f"{cls.GRAY}${pnl:.2f} (BEP){cls.RST}"

    @classmethod
    def make_bar(cls, val, max_val=1.0, width=10):
        """Create a progress bar for confidence or score."""
        val = max(0.0, min(float(val), float(max_val)))
        ratio = val / float(max_val) if max_val > 0 else 0.0
        filled = int(round(ratio * width))
        filled = max(0, min(width, filled))
        bar = "█" * filled + "░" * (width - filled)
        pct = f"{ratio * 100:.1f}%"
        if ratio >= 0.75:
            return f"{cls.GREEN}{bar}{cls.RST} {cls.BOLD}{pct}{cls.RST}"
        elif ratio >= 0.50:
            return f"{cls.YELLOW}{bar}{cls.RST} {pct}"
        else:
            return f"{cls.GRAY}{bar}{cls.RST} {pct}"

    @classmethod
    def clear_line(cls):
        """ANSI sequence to clear line and return cursor to column 0."""
        return "\x1b[2K\r"

    @classmethod
    def tag(cls, name, color=CYAN):
        """Format consistent bracket tag e.g. [RISK] [MT5] [SIZING]."""
        return f"{color}[{name}]{cls.RST}"


    @classmethod
    def disp_width(cls, s):
        """Visual display width of string in terminal without ANSI codes."""
        import re
        import unicodedata
        plain = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', str(s))
        return sum(
            2 if ord(ch) > 0xFFFF or unicodedata.east_asian_width(ch) in ("W", "F") else 1
            for ch in plain
        )

    @classmethod
    def pad_line(cls, s, target_w):
        """Pads string `s` to visual width `target_w` cleanly without breaking ANSI codes."""
        import re
        import unicodedata
        w = cls.disp_width(s)
        if w < target_w:
            return str(s) + " " * (target_w - w)
        elif w > target_w:
            ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
            tokens = re.split(r'(\x1b\[[0-9;]*[a-zA-Z])', str(s))
            out = []
            cur_w = 0
            limit = max(1, target_w - 3)
            for token in tokens:
                if not token:
                    continue
                if ansi_re.fullmatch(token):
                    out.append(token)
                else:
                    for ch in token:
                        cw = 2 if ord(ch) > 0xFFFF or unicodedata.east_asian_width(ch) in ("W", "F") else 1
                        if cur_w + cw > limit:
                            out.append(f"...{cls.RST}")
                            w_final = cls.disp_width("".join(out))
                            if w_final < target_w:
                                out.append(" " * (target_w - w_final))
                            return "".join(out)
                        out.append(ch)
                        cur_w += cw
            out.append(cls.RST)
            w_final = cls.disp_width("".join(out))
            if w_final < target_w:
                out.append(" " * (target_w - w_final))
            return "".join(out)
        return str(s)

    @classmethod
    def wrap_text_line(cls, label, text, target_w):
        """Wraps labelled text into multiple lines if visual width exceeds target_w."""
        prefix_w = cls.disp_width(label)
        avail_w = target_w - prefix_w
        if avail_w <= 15:
            prefix_w = 4
            avail_w = max(20, target_w - 4)
            
        words = str(text).split()
        lines = []
        cur_line = []
        cur_w = 0
        
        for w in words:
            ww = cls.disp_width(w)
            if cur_w + (1 if cur_line else 0) + ww <= avail_w:
                cur_line.append(w)
                cur_w += (1 if len(cur_line) > 1 else 0) + ww
            else:
                if cur_line:
                    lines.append(" ".join(cur_line))
                cur_line = [w]
                cur_w = ww
        if cur_line:
            lines.append(" ".join(cur_line))
            
        res = []
        for i, line_str in enumerate(lines):
            if i == 0:
                res.append(f"{label}{line_str}")
            else:
                res.append(f"{' ' * prefix_w}{line_str}")
        return res

    @classmethod
    def make_box(cls, title, items, width=74, border_color=CYAN):
        """Builds a perfectly aligned, ANSI-safe ASCII box panel.
        
        `items` can contain:
          - string: single line inside panel
          - tuple (label, text): auto-wrapped line with indented second line if long
          - "---": divider line inside panel
        """
        inner_w = max(20, width - 4)
        out = []
        
        # Top border
        if title:
            prefix = f"+-- [ {cls.BOLD}{cls.WHITE}{title}{cls.RST}{border_color} ] "
            title_plain = f"+-- [ {title} ] "
            dashes = max(0, width - cls.disp_width(title_plain) - 1)
            out.append(f"{border_color}{prefix}{'-' * dashes}+{cls.RST}")
        else:
            out.append(f"{border_color}+{'-' * (width - 2)}+{cls.RST}")
            
        # Body
        for item in items:
            if item == "---":
                out.append(f"{border_color}+{'-' * (width - 2)}+{cls.RST}")
            elif isinstance(item, tuple) and len(item) == 2:
                label, text = item
                wrapped_lines = cls.wrap_text_line(label, text, inner_w)
                for wl in wrapped_lines:
                    padded = cls.pad_line(wl, inner_w)
                    out.append(f"{border_color}|{cls.RST} {padded} {border_color}|{cls.RST}")
            else:
                padded = cls.pad_line(str(item), inner_w)
                out.append(f"{border_color}|{cls.RST} {padded} {border_color}|{cls.RST}")
                
        # Bottom border
        out.append(f"{border_color}+{'-' * (width - 2)}+{cls.RST}")
        return "\n".join(out)


def render_scanner_banner(account_info=None, is_live=True, total_symbols=26):
    """Renders a sleek ASCII banner for Multi-Pair Quant Screener & Multi-LLM Jury."""
    badge_mode = UI.badge_live() if is_live else UI.badge_dry()
    acc_text = f"Live Account #{account_info}" if account_info else "Trading Terminal"
    
    title_line = f"{UI.BOLD}{UI.WHITE}RIZUKID QUANT FUNNEL & MULTI-LLM JURY{UI.RST} {UI.PURPLE}[{total_symbols}-PAIR PRO]{UI.RST}"
    status_line = f"Status: {badge_mode} | Account: {UI.WHITE}{acc_text}{UI.RST} | Universe: {UI.YELLOW}{total_symbols} Pairs (H1+D1){UI.RST} | Mode: {UI.CYAN}2-STAGE FUNNEL{UI.RST}"
    
    items = [
        title_line,
        "---",
        status_line
    ]
    return UI.make_box("2-STAGE QUANT FUNNEL TERMINAL", items, width=76, border_color=UI.CYAN)


def render_candidate_alert_box(candidate):
    """Renders an institutional ASCII panel when Fast Radar detects a candidate."""
    direction_color = UI.GREEN if candidate.direction == 1 else UI.RED
    dir_str = "BUY" if candidate.direction == 1 else "SELL"
    tf_str = getattr(candidate, "timeframe", "H1")
    t_wib = getattr(candidate, "timestamp_wib", "") or datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%H:%M:%S WIB")
    
    zone_name = "Discount Zone (Cheap)" if candidate.dealing_range_pos <= 0.38 else (
        "Premium Zone (Expensive)" if candidate.dealing_range_pos >= 0.62 else "Equilibrium (Mid-Range)"
    )
    
    meta = getattr(candidate, 'metadata', {}) or {}
    prop_type = meta.get('entry_type', 'market').upper()
    prop_price = meta.get('entry_price', candidate.trigger_price)
    entry_label = f"{UI.YELLOW}{prop_type} @ {prop_price}{UI.RST}" if "LIMIT" in prop_type or "STOP" in prop_type else f"{UI.GREEN}INSTANT MARKET ORDER{UI.RST}"

    wick_side = "Upper Wick" if candidate.direction == -1 else "Lower Wick"
    
    items = [
        f"{UI.BOLD}{direction_color}[RADAR TRIGGER] {candidate.symbol} [{dir_str}] [{tf_str}]{UI.RST}",
        "---",
        (f"• Trigger Time : ", f"{UI.CYAN}{t_wib}{UI.RST}"),
        (f"• Setup Type   : ", f"{UI.WHITE}{candidate.setup_type} ({tf_str}){UI.RST}"),
        (f"• Proposed Entry: ", f"{entry_label}"),
        (f"• Live Price   : ", f"{UI.BOLD}{UI.WHITE}{candidate.trigger_price:.5f}{UI.RST} | Macro: {UI.CYAN}{candidate.macro_compass}{UI.RST}"),
        (f"• SMC Location : ", f"{UI.YELLOW}{candidate.dealing_range_pos*100:.1f}% Range ({zone_name}){UI.RST} (M15 {wick_side} {candidate.rejection_wick_ratio*100:.0f}%)"),
        (f"• Proposed SLTP: ", f"SL: {UI.RED}{candidate.suggested_sl}{UI.RST} | TP: {UI.GREEN}{candidate.suggested_tp}{UI.RST} (R:R {candidate.risk_reward_ratio:.2f}:1)"),
        (f"• Market Stats : ", f"Spread: {candidate.current_spread_pts} pts | ATR(14): {candidate.current_atr_pts:.1f} pts"),
    ]

    # Fetch Real-time Apex Fundamental Evaluation
    try:
        from src.analytics.apex_fundamental_engine import apex_fundamental_engine
        fund_eval = apex_fundamental_engine.evaluate_pair(candidate.symbol)
        if fund_eval and fund_eval.base:
            badge_c = UI.GREEN if "ALIGNED" in fund_eval.status_badge else (UI.RED if "CONFLICT" in fund_eval.status_badge else UI.YELLOW)
            items.append((f"• Apex FE Bias : ", f"{badge_c}{fund_eval.status_badge}{UI.RST} (Delta: {fund_eval.fundamental_delta:+.2f})"))
            grade_c = UI.GREEN if "GRADE_S" in fund_eval.setup_grade or "GRADE_A_PLUS" in fund_eval.setup_grade else UI.CYAN
            items.append((f"• Setup Grade  : ", f"{UI.BOLD}{grade_c}{fund_eval.setup_grade}{UI.RST} (Carry: {fund_eval.carry_spread:+.2f}% | Sizing: {fund_eval.sizing_modifier}x)"))
            if fund_eval.hard_veto_flag:
                items.append((f"• Veto Alert   : ", f"{UI.BG_RED} {fund_eval.hard_veto_flag} {UI.RST} ({fund_eval.hard_veto_reason})"))
    except Exception:
        pass

    return UI.make_box(f"QUANT SETUP DETECTED: {candidate.symbol} [{tf_str} | {t_wib}]", items, width=76, border_color=UI.PURPLE)


def render_hacker_bento_hud(macro_cache=None, account_info=None, daily_pnl=0.0, open_positions=None, active_models=None):
    """
    Renders an Ultra-Clean Cyberpunk Hacker-Style 2x2 Bento Box Terminal HUD.
    Features adaptive rendering:
    - Weekend (BTC Mode): Tile 1 renders full Top-Down MSE Directive Card, Tile 3 renders BTC Technical Pulse.
    - Weekday (26 FX Pairs): Tile 1 renders full 26-Pair Heat Matrix (9 rows), Tile 3 renders CSM + Top MSE Directives.
    """
    c_cyan = UI.CYAN
    c_purp = UI.PURPLE
    c_rst = UI.RST
    
    lw = 68  # Left column inner width (139 total cols)
    rw = 68  # Right column inner width
    
    import config
    scanner_syms = config.get_scanner_symbols() if hasattr(config, "get_scanner_symbols") else []
    all_symbols = [
        s.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "")
        for s in scanner_syms
    ] or ["BTCUSD"]
    
    hot_pairs = []
    in_zone_pairs = []
    
    # ── TILE 1 & TILE 3 ADAPTIVE LOGIC ──
    is_single_asset_mode = len(all_symbols) <= 2
    
    if is_single_asset_mode:
        # ══ WEEKEND / SINGLE ASSET MODE: DIRECT TOP-DOWN MSE EMBEDDING ══
        active_sym = all_symbols[0] if all_symbols else "BTCUSD"
        h1_title_text = f"TOP-DOWN MACRO STRATEGIC DIRECTIVE: {active_sym}"
        
        # Try fetching real MSE directive
        t1_lines = []
        try:
            from src.analytics.macro_strategic_engine import macro_strategic_engine
            from src.core import mt5_connector as connector
            valid_s = connector.get_valid_trade_symbol(active_sym)
            d = macro_strategic_engine.get_directive(valid_s, mt5_connector=connector)
            
            b_color = UI.GREEN if "BULL" in d.daily_macro_bias else (UI.RED if "BEAR" in d.daily_macro_bias else UI.YELLOW)
            e_color = UI.GREEN if "BUY" in d.primary_execution_directive else (UI.RED if "SELL" in d.primary_execution_directive else UI.YELLOW)
            
            is_btc = "BTC" in active_sym
            fmt = "{:,.2f}" if is_btc else "{:.5f}"
            
            t1_lines = [
                f" Mandat Makro : {b_color}{UI.BOLD}{d.daily_macro_bias}{UI.RST} (Stage: {UI.PURPLE}{d.structural_stage[:22]}{UI.RST})",
                f" Eksekusi     : {e_color}{UI.BOLD}{d.primary_execution_directive}{UI.RST}",
                f" • Macro D1   : RBS {UI.GREEN}${fmt.format(d.macro_rbs_d1)}{UI.RST} | SBR {UI.RED}${fmt.format(d.macro_sbr_d1)}{UI.RST}",
                f" • Inter H4   : RBS {UI.GREEN}${fmt.format(d.inter_rbs_h4)}{UI.RST} | SBR {UI.RED}${fmt.format(d.inter_sbr_h4)}{UI.RST}",
                f" • Micro H1   : RBS {UI.GREEN}${fmt.format(d.micro_rbs_h1)}{UI.RST} | SBR {UI.RED}${fmt.format(d.micro_sbr_h1)}{UI.RST}",
                f" • Stations   : Sub-Floor {UI.GREEN}${fmt.format(d.sub_floor_50)}{UI.RST} | Sub-Ceil {UI.RED}${fmt.format(d.sub_ceiling_50)}{UI.RST}",
                f" • Reload Zone : {UI.YELLOW}${fmt.format(d.entry_limit_anchor)}{UI.RST} | SL {UI.RED}${fmt.format(d.intraday_sl_price)}{UI.RST} (SL {f'${d.intraday_sl_pips:.0f}' if is_btc else f'{d.intraday_sl_pips:.0f}p'})",
                f" • Targets    : TP1 {UI.GREEN}${fmt.format(d.tp1_price)}{UI.RST} (50%) | TP2 {UI.GREEN}${fmt.format(d.tp2_price)}{UI.RST} (R:R {d.risk_reward_ratio:.2f}:1)",
                f" • Pantangan  : {UI.YELLOW}{d.forbidden_traps[0] if d.forbidden_traps else 'None'}{UI.RST}"
            ]
        except Exception:
            t1_lines = [
                f" Mandat Makro : {UI.RED}{UI.BOLD}BEARISH_PULLBACK{UI.RST} (Stage: {UI.PURPLE}FRONTIER_EXHAUSTION{UI.RST})",
                f" Eksekusi     : {UI.YELLOW}{UI.BOLD}HUNT_SELL_PULLBACK{UI.RST}",
                f" • Macro D1   : RBS {UI.GREEN}$67,289.78{UI.RST} | SBR {UI.RED}$78,150.47{UI.RST}",
                f" • Inter H4   : RBS {UI.GREEN}$67,289.78{UI.RST} | SBR {UI.RED}$78,150.47{UI.RST}",
                f" • Micro H1   : RBS {UI.GREEN}$77,943.79{UI.RST} | SBR {UI.RED}$78,993.88{UI.RST}",
                f" • Stations   : Sub-Floor {UI.GREEN}$78,150.46{UI.RST} | Sub-Ceil {UI.RED}$78,150.47{UI.RST}",
                f" • Reload Zone : {UI.YELLOW}$78,993.88{UI.RST} | SL {UI.RED}$78,995.48{UI.RST}",
                f" • Targets    : TP1 $78,150.46 | TP2 $67,289.78 (R:R 7.31:1)",
                f" • Pantangan  : {UI.YELLOW}Do NOT BUY above $78,494 (Ceiling Trap into ATH){UI.RST}"
            ]
            
        m1_title_text = "BITCOIN TECHNICAL PULSE & NEWS TICKER"
        news_str = "Quiet (No High-Impact News in 24h)"
        try:
            from src.analytics import economic_calendar
            cal_obj = getattr(economic_calendar, "calendar", None)
            if cal_obj:
                now_wib = datetime.now(ZoneInfo("Asia/Jakarta"))
                upcoming = cal_obj.get_upcoming(now_wib, hours_ahead=24)
                if upcoming:
                    ne = upcoming[0]
                    hrs = (ne["dt"] - now_wib).total_seconds() / 3600
                    cntry = ne.get("country", "US").strip()
                    news_str = f"[{cntry}] {ne['name']} in {hrs:.1f}h ({ne['dt'].strftime('%H:%M WIB')})"
        except Exception:
            pass

        w_state_str = "MATURE_BASING"
        w_perm_str = f"{UI.CYAN}◆ ARMED (Menunggu Sentuh Reload Zone){UI.RST}"
        if macro_cache:
            for k, v in macro_cache.items():
                if active_sym in k:
                    w_st = v.get('wave_state', 'MATURE_BASING')
                    w_pm = v.get('permission_state', 'ARM')
                    if w_pm == "GO":
                        w_perm_str = f"{UI.GREEN}● GO (Pelatuk Aktif / Reclaim Confirmed){UI.RST}"
                    elif w_pm == "ARM":
                        w_perm_str = f"{UI.CYAN}◆ ARMED (Menunggu Sentuh Reload Zone){UI.RST}"
                    elif w_pm == "WAIT":
                        w_perm_str = f"{UI.GRAY}○ WAIT (Anti-FOMO / Di Pucuk Ekspansi){UI.RST}"
                    elif w_pm == "LOCK":
                        w_perm_str = f"{UI.RED}■ LOCK (Anti-Falling Knife){UI.RST}"
                    w_state_str = w_st
                    break

        t3_lines = [
            f" Sesi Trading : {UI.CYAN}Weekend 24/7 Dedicated Crypto Rotation{UI.RST}",
            f" Wave State   : {UI.GREEN}{w_state_str}{UI.RST}",
            f" Permission   : {w_perm_str}",
            f" Risk Profile : {UI.YELLOW}0.50% Equity ($29.10 Max Loss | Max 2 Posisi){UI.RST}",
            f" News Ticker  : {UI.YELLOW if 'in ' in news_str else UI.GREEN}{news_str}{UI.RST}"
        ]
    else:
        # ══ WEEKDAY MODE: FULL 26-PAIR QUANT RADAR MATRIX ══
        h1_title_text = f"{len(all_symbols)}-PAIR LIVE QUANT RADAR MATRIX"
        t1_lines = []
        if macro_cache:
            def _format_cell(sym_prefix):
                for k, v in macro_cache.items():
                    if k.startswith(sym_prefix):
                        adx = v.get('adx', 0.0)
                        pos = v.get('dealing_range_pos', 0.5)
                        is_bull = v.get('is_bull', False)
                        is_bear = v.get('is_bear', False)
                        wave_st = v.get('wave_state', '')
                        perm_st = v.get('permission_state', 'WAIT')
                        
                        if "IMPULSE" in wave_st or "CHASE" in wave_st:
                            badge = f"{UI.PURPLE}▶{UI.RST}"
                        elif "LOCK" in wave_st or perm_st == "LOCK":
                            badge = f"{UI.RED}■{UI.RST}"
                        elif "RECLAIM" in wave_st or "GO" in wave_st or perm_st == "GO":
                            badge = f"{UI.GREEN}●{UI.RST}"
                            in_zone_pairs.append(f"{sym_prefix} ●")
                        elif "ARMED" in wave_st or "RELOAD" in wave_st or "MATURE" in wave_st or perm_st == "ARM":
                            badge = f"{UI.CYAN}◆{UI.RST}"
                            in_zone_pairs.append(f"{sym_prefix} ◆")
                        elif perm_st == "WATCH":
                            badge = f"{UI.YELLOW}▲{UI.RST}"
                        elif "WAIT" in perm_st or "EXPANSION" in wave_st:
                            badge = f"{UI.GRAY}○{UI.RST}"
                        else:
                            badge = f"{UI.GRAY}○{UI.RST}"
                            
                        if is_bull:
                            arrow = f"{UI.GREEN}▲{UI.RST}"
                        elif is_bear:
                            arrow = f"{UI.RED}▼{UI.RST}"
                        else:
                            arrow = f"{UI.GRAY}·{UI.RST}"
                            
                        pos_str = f"{int(pos*100):02d}%"
                        return f"{sym_prefix} {arrow}{pos_str} {badge}"
                return f"{sym_prefix} {UI.GRAY}·--%{UI.RST}  "

            # Render 3 pairs per row (9 rows for 26 pairs)
            for r in range(0, len(all_symbols), 3):
                p1 = all_symbols[r]
                p2 = all_symbols[r+1] if r+1 < len(all_symbols) else None
                p3 = all_symbols[r+2] if r+2 < len(all_symbols) else None
                
                c1 = UI.pad_line(_format_cell(p1), 20)
                c2 = UI.pad_line(_format_cell(p2) if p2 else "", 20)
                c3 = UI.pad_line(_format_cell(p3) if p3 else "", 20)
                t1_lines.append(f" {c1} │ {c2} │ {c3}")
                
            t1_lines.append(f" {UI.DIM}───────────────────────────────────────────────────────────────────{UI.RST}")
            legend_parts = [
                f"{UI.GREEN}▲{UI.RST}/{UI.RED}▼{UI.WHITE}Trend{UI.RST}",
                f"{UI.GREEN}0%FL{UI.RST}~{UI.RED}100%CE{UI.RST}",
                f"{UI.GREEN}●GO{UI.RST}",
                f"{UI.CYAN}◆ARM{UI.RST}",
                f"{UI.RED}■LOCK{UI.RST}",
                f"{UI.YELLOW}▲WATCH{UI.RST}",
                f"{UI.GRAY}○WAIT{UI.RST}"
            ]
            t1_lines.append(" " + f" {UI.DIM}│{UI.RST} ".join(legend_parts))
        else:
            t1_lines = [
                f" {UI.YELLOW}● Inisialisasi {len(all_symbols)}-Pair Macro Compass...{UI.RST}",
                f" {UI.DIM}Memindai D1/H4 dealing ranges & level Asia...{UI.RST}",
                f" {UI.DIM}Fast Radar bersiap untuk sweep 60 detik.{UI.RST}",
                f" {UI.DIM}Monitoring {len(all_symbols)} Pasangan FX Terkurasi 24/5.{UI.RST}"
            ]

        m1_title_text = "DUAL-HORIZON BOITOKI CSM RADAR & TOP DIRECTIVES"
        t3_lines = []
        try:
            from src.analytics.currency_strength import calculate_boitoki_csm
            scores_h1, _ = calculate_boitoki_csm(config.mt5.TIMEFRAME_H1, lookback_bars=24)
            scores_m15, _ = calculate_boitoki_csm(config.mt5.TIMEFRAME_M15, lookback_bars=16)
            
            sorted_h1 = sorted(scores_h1.items(), key=lambda x: x[1], reverse=True) if scores_h1 else []
            sorted_m15 = sorted(scores_m15.items(), key=lambda x: x[1], reverse=True) if scores_m15 else []
            
            h1_str = " > ".join([f"{c}" for c, s in sorted_h1]) if sorted_h1 else "--"
            m15_str = " > ".join([f"{c}" for c, s in sorted_m15]) if sorted_m15 else "--"
            
            news_str = "Quiet (No High-Impact News in 24h)"
            try:
                from src.analytics import economic_calendar
                cal_obj = getattr(economic_calendar, "calendar", None)
                if cal_obj:
                    now_wib = datetime.now(ZoneInfo("Asia/Jakarta"))
                    upcoming = cal_obj.get_upcoming(now_wib, hours_ahead=24)
                    if upcoming:
                        ne = upcoming[0]
                        hrs = (ne["dt"] - now_wib).total_seconds() / 3600
                        cntry = ne.get("country", "US").strip()
                        news_str = f"[{cntry}] {ne['name']} in {hrs:.1f}h ({ne['dt'].strftime('%H:%M WIB')})"
            except Exception:
                pass
            
            try:
                from src.analytics.apex_fundamental_engine import apex_fundamental_engine
                f_scores = apex_fundamental_engine.compute_scores()
                if f_scores:
                    sorted_fund = sorted(f_scores.items(), key=lambda x: x[1].composite_fundamental_score, reverse=True)
                    fund_str = " > ".join([f"{c}" for c, sc in sorted_fund])
                    top_s = sorted_fund[0][0]
                    top_w = sorted_fund[-1][0]
                    delta_val = sorted_fund[0][1].composite_fundamental_score - sorted_fund[-1][1].composite_fundamental_score
                    t3_lines.append(f" Apex Fund Rank   : {UI.RED}{fund_str}{UI.RST}")
                    t3_lines.append(f" Top Convergent   : {UI.GREEN}{top_s}{top_w}{UI.RST} (Delta {UI.BOLD}{delta_val:+.2f}{UI.RST} -> Grade S/A+)")
            except Exception:
                pass

            t3_lines.append(f" CSM Macro (H1)   : {UI.CYAN}{h1_str}{UI.RST}")
            t3_lines.append(f" CSM Session (M15): {UI.BOLD}{UI.YELLOW}{m15_str}{UI.RST}")
            t3_lines.append(f" Macro Compass    : {UI.GREEN}26 FX Majors & Crosses (H1/M30 Native){UI.RST}")
            t3_lines.append(f" News Ticker      : {UI.YELLOW if 'in ' in news_str else UI.GREEN}{news_str}{UI.RST}")
        except Exception:
            t3_lines = [
                f" Sesi     : {UI.WHITE}Dynamic Session-Adaptive (Tokyo H1 / LDN-NY M30){UI.RST}",
                f" Judas    : {UI.YELLOW}14:00 - 18:00 WIB{UI.RST} (Asian Liquidity Sweep Active)",
                f" Structure: {UI.CYAN}100-bar H1 (Disc <=38% | Prem >=62%){UI.RST}",
                f" News     : {UI.GREEN}ACTIVE (TradingView News Window Shield){UI.RST}"
            ]

    # ── TILE 2: LIVE ACCOUNT & RISK INTELLIGENCE HUD (Top Right) ──
    acc = account_info or {}
    srv = acc.get("server", "VTMarkets-Live 3")
    login_id = acc.get("login", "27556325")
    eq = acc.get("equity", 5819.29)
    bal = acc.get("balance", 5819.29)
    
    positions = config.mt5.positions_get() if hasattr(config.mt5, "positions_get") else []
    orders = config.mt5.orders_get() if hasattr(config.mt5, "orders_get") else []
    total_active = len(positions or []) + len(orders or [])
    max_positions = config.get_max_open_positions()

    max_loss_dlr = eq * (getattr(config, "MAX_DAILY_LOSS_PERCENT", 4.0) / 100.0)
    
    t2_lines = [
        f" Server     : {UI.WHITE}{srv}{UI.RST} (Login #{login_id})",
        f" Equity     : {UI.BOLD}{UI.WHITE}${eq:,.2f}{UI.RST} | Balance: ${bal:,.2f}",
        f" Capacity   : {UI.BOLD}{UI.CYAN}{total_active}/{max_positions} Active{UI.RST} ({'Weekend Crypto Pool' if is_single_asset_mode else '26-Pair Basket Pool'})",
        f" Daily P/L  : {UI.badge_pnl(daily_pnl)} | Max Loss Cap: {UI.RED}{config.MAX_DAILY_LOSS_PERCENT}% (${max_loss_dlr:.0f}){UI.RST}",
        f" MSE Sockets: {UI.GREEN}6-TF Native (MN1/W1/D1/H4/H1){UI.RST} | {UI.CYAN}0 Token (<50ms){UI.RST}",
    ]
    if open_positions:
        pos_strs = []
        for p in open_positions[:3]:
            s_clean = p.get("symbol", "").replace("-ECNc", "").replace(".c", "")
            pos_strs.append(f"{s_clean}: {UI.badge_pnl(p.get('profit', 0.0))}")
        t2_lines.append(f" Positions  : {' | '.join(pos_strs)}")
    elif orders:
        ord_strs = []
        for o in orders[:3]:
            s_clean = o.symbol.replace("-ECNc", "").replace(".c", "")
            ord_strs.append(f"{s_clean} (Pend)")
        t2_lines.append(f" Positions  : {UI.YELLOW}{' | '.join(ord_strs)}{UI.RST}")
    else:
        t2_lines.append(f" Positions  : {UI.GRAY}No active positions (Flat / Ready){UI.RST}")
        
    hot_str = ", ".join(hot_pairs[:4]) if hot_pairs else ("BTCUSD (27% Disc) [HOT]" if is_single_asset_mode else "None (Normal Vol)")
    in_zone_str = ", ".join(in_zone_pairs[:4]) if in_zone_pairs else ("BTCUSD ◆" if is_single_asset_mode else "None (Mid-Range)")
    
    t2_lines.append(f" Top Hot    : {UI.YELLOW}{hot_str}{UI.RST}")
    t2_lines.append(f" Wave Armed : {UI.GREEN}{in_zone_str}{UI.RST}")
    t2_lines.append(f" Fast Radar : {UI.CYAN}{len(all_symbols)} Pairs Swept Every 60s (0 Tokens / Background){UI.RST}")
    t2_lines.append(f" Proteksi   : {UI.DIM}BEP 45% + Trailing 65-90% + 4h Time Decay Stagnation{UI.RST}")
        
    # ── TILE 4: 2-PASS SEQUENTIAL 3-LLM JURY PROTOCOL (Bottom Right) ──
    t4_lines = [
        f" Pass 1 (~3s) : {UI.WHITE}OpenAI o4-mini{UI.RST} (Structure) + {UI.WHITE}Gemini 3.1-Flash{UI.RST} (Speed)",
        f" Pass 2 (~1.5s): {UI.PURPLE}DeepSeek V4-Flash{UI.RST} (Chief Risk Officer & Hard Risk Veto)",
        f" Hard Veto    : {UI.RED}QUALIFIED HARD VETO ARMED{UI.RST} (Anti-Falling Knife Guard)",
        f" News Shield  : {UI.GREEN}ForexFactory + TV Dual-Source (±6h Gate){UI.RST}",
        f" Apex Confluence : {UI.CYAN}Institutional 8-Currency Regime Filter (Active){UI.RST}"
    ]
    
    # ── ASSEMBLE 2x2 BENTO BOX ──
    out = []
    
    # Top Header
    h1_title = f"+-- [ {UI.BG_CYAN} {h1_title_text} {UI.RST}{c_cyan} ] "
    d1 = max(0, lw - UI.disp_width(h1_title) + 1)
    h1_bar = f"{c_cyan}{h1_title}{'-' * d1}+{c_rst}"
    
    h2_title = f"-- [ {UI.BG_GREEN} LIVE ACCOUNT & RISK INTELLIGENCE {UI.RST}{c_cyan} ] "
    d2 = max(0, rw - UI.disp_width(h2_title) + 1)
    h2_bar = f"{c_cyan}{h2_title}{'-' * d2}+{c_rst}"
    
    out.append(f"{h1_bar}{h2_bar}")
    
    # Top Rows (Tiles 1 & 2)
    max_top_rows = max(len(t1_lines), len(t2_lines), 7)
    for i in range(max_top_rows):
        l_txt = t1_lines[i] if i < len(t1_lines) else ""
        r_txt = t2_lines[i] if i < len(t2_lines) else ""
        l_pad = UI.pad_line(l_txt, lw)
        r_pad = UI.pad_line(r_txt, rw)
        out.append(f"{c_cyan}|{c_rst}{l_pad}{c_cyan}|{c_rst}{r_pad}{c_cyan}|{c_rst}")
        
    # Middle Divider
    m1_title = f"+-- [ {UI.BG_PURPLE} {m1_title_text} {UI.RST}{c_cyan} ] "
    md1 = max(0, lw - UI.disp_width(m1_title) + 1)
    m1_bar = f"{c_cyan}{m1_title}{'-' * md1}+{c_rst}"
    
    m2_title = f"-- [ {UI.BG_BLUE} 2-PASS SEQUENTIAL 3-LLM JURY PROTOCOL {UI.RST}{c_cyan} ] "
    md2 = max(0, rw - UI.disp_width(m2_title) + 1)
    m2_bar = f"{c_cyan}{m2_title}{'-' * md2}+{c_rst}"
    
    out.append(f"{m1_bar}{m2_bar}")
    
    # Bottom Rows (Tiles 3 & 4)
    max_bot_rows = max(len(t3_lines), len(t4_lines), 4)
    for i in range(max_bot_rows):
        l_txt = t3_lines[i] if i < len(t3_lines) else ""
        r_txt = t4_lines[i] if i < len(t4_lines) else ""
        l_pad = UI.pad_line(l_txt, lw)
        r_pad = UI.pad_line(r_txt, rw)
        out.append(f"{c_cyan}|{c_rst}{l_pad}{c_cyan}|{c_rst}{r_pad}{c_cyan}|{c_rst}")
        
    # Bottom Border
    b1_bar = f"{c_cyan}+{'-' * lw}+{c_rst}"
    b2_bar = f"{c_cyan}{'-' * rw}+{c_rst}"
    out.append(f"{b1_bar}{b2_bar}")
    
    return "\n".join(out)


def render_banner(account_info=None, symbol="GBPUSD-ECNc", tf=None, mode="pairs", is_live=True):
    """Renders a modern clean ASCII banner for FX Pairs Trading Terminal."""
    if tf is None:
        try:
            import config
            tf = config.get_timeframe_str(symbol)
        except Exception:
            tf = "M30"
    badge_mode = UI.badge_live() if is_live else UI.badge_dry()
    acc_text = f"Live Account #{account_info}" if account_info else "Trading Terminal"
    
    title_line = f"{UI.BOLD}{UI.WHITE}RIZUKID MULTI-LLM CONSENSUS TRADING BOT{UI.RST} {UI.CYAN}[FX PAIRS PRO]{UI.RST}"
    items = [
        title_line,
        "---",
        status_line
    ]
    return UI.make_box("FX PAIRS TRADING TERMINAL PRO", items, width=76, border_color=UI.CYAN)


def render_macro_directive_card(directive, width=95):
    """
    Renders a comprehensive Top-Down Macro Strategic Directive (MSE) terminal card.
    Displays 6-TF native socket levels, bar counts, SBR/RBS hierarchy, dual-grid stations, and intraday delivery.
    """
    clean_sym = directive.symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "").upper()
    c_cyan = UI.CYAN
    c_rst = UI.RST
    c_white = UI.WHITE
    c_bold = UI.BOLD
    c_yellow = UI.YELLOW
    c_green = UI.GREEN
    c_red = UI.RED
    c_gray = UI.GRAY
    c_purple = UI.PURPLE

    bias_color = c_green if "BULL" in directive.daily_macro_bias else (c_red if "BEAR" in directive.daily_macro_bias else c_yellow)
    exec_color = c_green if "BUY" in directive.primary_execution_directive else (c_red if "SELL" in directive.primary_execution_directive else c_yellow)

    # Format price strings based on asset type
    is_jpy = "JPY" in clean_sym
    is_crypto_or_gold = "BTC" in clean_sym or "XAU" in clean_sym or "GOLD" in clean_sym
    fmt = "{:.2f}" if is_crypto_or_gold else ("{:.3f}" if is_jpy else "{:.5f}")

    rbs_d1_s = fmt.format(directive.macro_rbs_d1) if directive.macro_rbs_d1 > 0 else "N/A"
    sbr_d1_s = fmt.format(directive.macro_sbr_d1) if directive.macro_sbr_d1 > 0 else "N/A"
    rbs_h4_s = fmt.format(directive.inter_rbs_h4) if directive.inter_rbs_h4 > 0 else "N/A"
    sbr_h4_s = fmt.format(directive.inter_sbr_h4) if directive.inter_sbr_h4 > 0 else "N/A"
    rbs_h1_s = fmt.format(directive.micro_rbs_h1) if directive.micro_rbs_h1 > 0 else "N/A"
    sbr_h1_s = fmt.format(directive.micro_sbr_h1) if directive.micro_sbr_h1 > 0 else "N/A"
    
    sub_c_s = fmt.format(directive.sub_ceiling_50) if directive.sub_ceiling_50 > 0 else "N/A"
    sub_f_s = fmt.format(directive.sub_floor_50) if directive.sub_floor_50 > 0 else "N/A"

    anchor_s = fmt.format(directive.entry_limit_anchor) if directive.entry_limit_anchor > 0 else "N/A"
    sl_s = fmt.format(directive.intraday_sl_price) if directive.intraday_sl_price > 0 else "N/A"
    tp1_s = fmt.format(directive.tp1_price) if directive.tp1_price > 0 else "N/A"
    tp2_s = fmt.format(directive.tp2_price) if directive.tp2_price > 0 else "N/A"
    inv_s = fmt.format(directive.invalidation_stop_price) if directive.invalidation_stop_price > 0 else "N/A"
    contingency_s = fmt.format(directive.contingency_target) if getattr(directive, 'contingency_target', 0.0) > 0 else "N/A"

    lines = []
    
    # ── Top Section: Mandat & Execution ──
    total_bars_str = f"{directive.total_bars_computed:,}" if getattr(directive, "total_bars_computed", 0) > 0 else "1,350"
    bias_score = getattr(directive, 'macro_bias_score', 0.0)
    stability = getattr(directive, 'regime_stability', 'STABLE')
    action_tier = getattr(directive, 'action_tier', 'FULL_ALLOW')
    circuit_breaker = getattr(directive, 'hard_circuit_breaker', False)
    tier_color = c_green if action_tier == "FULL_ALLOW" else (c_yellow if action_tier == "REDUCED_CONFIDENCE" else (c_purple if action_tier == "TP1_ONLY_SCALP" else c_red))

    bid_val = getattr(directive, 'current_bid', 0.0)
    ask_val = getattr(directive, 'current_ask', 0.0)
    bid_s = fmt.format(bid_val) if bid_val > 0 else "N/A"
    ask_s = fmt.format(ask_val) if ask_val > 0 else "N/A"
    spread_pips_val = (directive.current_spread_pts / 10.0) if ("JPY" in clean_sym or is_jpy or not is_crypto_or_gold) else directive.current_spread_pts
    spread_s = f"{spread_pips_val:.1f}p" if not is_crypto_or_gold else f"{directive.current_spread_pts}pts"
    
    price_info = f"Bid: {c_green}{c_bold}{bid_s}{c_rst} │ Ask: {c_red}{c_bold}{ask_s}{c_rst} ({c_yellow}Spr: {spread_s}{c_rst})" if bid_val > 0 else f"0 Token"

    lines.append(f" {c_bold}{c_white}SYMBOL{c_rst}       : {c_yellow}{c_bold}{clean_sym}{c_rst} │ {price_info} │ Komp: {c_cyan}{directive.calculation_time_ms:.1f}ms{c_rst} (0 Token)")
    lines.append(f" {c_bold}{c_white}SOCKETS 6-TF{c_rst} : {c_cyan}MN1: 50b (4.1y) │ W1: 100b (1.9y) │ D1: 350b (1.4y) │ H4: 400b │ H1: 250b │ Total: {total_bars_str}b{c_rst}")
    lines.append(f" {c_bold}{c_white}MACRO BIAS{c_rst}   : {bias_color}{c_bold}{directive.daily_macro_bias}{c_rst} ({bias_score:+.2f}) | Stability: {c_purple}{stability}{c_rst} | Tier: {tier_color}{c_bold}{action_tier}{c_rst}")
    if circuit_breaker:
        lines.append(f" {c_bold}{c_red}[!] HARD CIRCUIT BREAKER ACTIVE (Extreme Trap / Structure Invalidation){c_rst}")
    lines.append(f" {c_bold}{c_white}DIRECTIVE{c_rst}    : {exec_color}{c_bold}{directive.primary_execution_directive}{c_rst} (Confidence: {directive.confidence_score}%)")
    lines.append("---")
    
    # ── Section 1: Multi-Year Envelope & Liquidity Map (MN1 & W1) ──
    narrative = directive.raw_payload.get("NARRATIVE_STORYTELLING", {}) if isinstance(directive.raw_payload, dict) else {}
    ann_corr = narrative.get("macro_annual_corridor", "")
    w1_anchor = narrative.get("w1_major_anchor", "")
    sweeps = narrative.get("discovered_liquidity_sweeps", "")
    
    lines.append(f" {c_bold}{c_cyan}[+] MULTI-YEAR ENVELOPE & LIQUIDITY MAP (MN1 & W1){c_rst}")
    if ann_corr:
        for wline in textwrap.wrap(f"• 4-Year MN1: {ann_corr}", width=width - 6):
            lines.append(f"  {c_yellow}{wline}{c_rst}")
    if w1_anchor:
        for wline in textwrap.wrap(f"• {w1_anchor}", width=width - 6):
            lines.append(f"  {c_cyan}{wline}{c_rst}")
    if sweeps:
        for wline in textwrap.wrap(f"• Liquidity Pool: {sweeps}", width=width - 6):
            lines.append(f"  {c_green}{wline}{c_rst}")
    lines.append("---")

    # ── Section 2: Structural Zones SBR & RBS (D1 / H4 / H1) ──
    lines.append(f" {c_bold}{c_cyan}[+] HIRARKI ZONA STRUKTURAL SBR & RBS (D1 / H4 / H1){c_rst}")
    lines.append(f"  • {c_white}Macro D1 (350 bars / 1.4y){c_rst}    : RBS {c_green}{rbs_d1_s}{c_rst} │ SBR {c_red}{sbr_d1_s}{c_rst}")
    lines.append(f"  • {c_white}Inter H4 (400 bars / 66 days){c_rst} : RBS {c_green}{rbs_h4_s}{c_rst} │ SBR {c_red}{sbr_h4_s}{c_rst}")
    lines.append(f"  • {c_white}Micro H1 (250 bars / 10 days){c_rst} : RBS {c_green}{rbs_h1_s}{c_rst} │ SBR {c_red}{sbr_h1_s}{c_rst}")
    lines.append("---")
    
    # ── Section 3: Dual Grid Stations ──
    lines.append(f" {c_bold}{c_cyan}[+] DUAL-GRID PSYCHOLOGICAL STATIONS & CORRIDOR (50/100 Pips){c_rst}")
    lines.append(f"  • {c_white}Sub-Ceiling (Upper Wall){c_rst}      : {c_red}{sub_c_s}{c_rst} (Major Resistance Corridor)")
    lines.append(f"  • {c_white}Sub-Floor (Lower Base){c_rst}        : {c_green}{sub_f_s}{c_rst} (Major Support Corridor)")
    station_label = "Target Macro Station Ceiling" if ("BUY" in directive.primary_execution_directive or "BULLISH" in directive.daily_macro_bias) else "Target Macro Station Floor"
    lines.append(f"  • {c_white}{station_label}{c_rst}   : {c_green}{fmt.format(directive.target_station_price)}{c_rst} (Equilibrium Target)")
    lines.append("---")
    
    # ── Section 3B: Barrier Chamber & State Machine Path ──
    m_state = getattr(directive, 'market_state', 'NEUTRAL_CHAMBER')
    f1_val = getattr(directive, 'immediate_floor_f1', 0.0)
    c1_val = getattr(directive, 'immediate_ceiling_c1', 0.0)
    f2_val = getattr(directive, 'deep_target_floor_f2', 0.0)
    c2_val = getattr(directive, 'deep_target_ceiling_c2', 0.0)
    ch_pos = getattr(directive, 'chamber_position_pct', 0.50)
    seq_list = getattr(directive, 'interaction_sequence', [])
    seq_str = " -> ".join(seq_list[-4:]) if seq_list else "None (Initial Observation)"

    state_color = c_green if "FLOOR" in m_state else (c_red if "CEILING" in m_state or "BREAKDOWN" in m_state else (c_yellow if "BREAKOUT" in m_state else c_purple))
    lines.append(f" {c_bold}{c_cyan}[+] BARRIER CHAMBER & STATE MACHINE PATHWAY{c_rst}")
    lines.append(f"  • {c_white}Active Market State{c_rst}        : {state_color}{c_bold}[{m_state}]{c_rst} (Chamber Range: {c_yellow}{ch_pos:.0%}{c_rst})")
    lines.append(f"  • {c_white}Dealing Chamber Bounds{c_rst}     : F1 {c_green}{fmt.format(f1_val)}{c_rst} <---> C1 {c_red}{fmt.format(c1_val)}{c_rst}")
    lines.append(f"  • {c_white}Deep Target Boundaries{c_rst}     : F2 {c_gray}{fmt.format(f2_val)}{c_rst} │ C2 {c_gray}{fmt.format(c2_val)}{c_rst}")
    lines.append(f"  • {c_white}Interaction Sequence{c_rst}       : {c_cyan}{seq_str}{c_rst}")
    lines.append("---")
    
    # ── Section 4: Intraday Execution Delivery ──
    pip_unit = "USD" if is_crypto_or_gold else "pips"
    lines.append(f" {c_bold}{c_cyan}[+] INTRADAY REFINED DELIVERY ROADMAP (Execution Plan){c_rst}")
    
    prox_val = directive.entry_zone_proximal if hasattr(directive, 'entry_zone_proximal') and directive.entry_zone_proximal > 0 else 0.0
    if prox_val > 0:
        prox_s = fmt.format(prox_val)
        zone_diff = abs(directive.entry_limit_anchor - prox_val)
        diff_pips = round(zone_diff, 1) if is_crypto_or_gold else round(zone_diff / (0.01 if "JPY" in clean_sym else 0.0001), 1)
        if "BUY" in directive.primary_execution_directive:
            zone_detail = f"{anchor_s} -> {prox_s} (~{diff_pips:.1f} {pip_unit} Front-Run)"
        else:
            zone_detail = f"{prox_s} -> {anchor_s} (~{diff_pips:.1f} {pip_unit} Front-Run)"
    else:
        zone_detail = f"{anchor_s}"
    lines.append(f"  • {c_white}Reload Zone (Front-Run ~ Core){c_rst} : {c_yellow}{zone_detail}{c_rst}")
    lines.append(f"  • {c_white}Intraday SL (Anti-Hunt){c_rst}        : {c_red}{sl_s}{c_rst} ({directive.intraday_sl_pips:.1f} {pip_unit})")
    lines.append(f"  • {c_white}TP1 (Partial 50% + BEP Lock){c_rst}   : {c_green}{tp1_s}{c_rst} (+{directive.tp1_pips:.1f} {pip_unit} │ 1.50:1 R:R)")
    tp2_label = "TP2 (Major Macro Station Ceiling)" if ("BUY" in directive.primary_execution_directive or "BULLISH" in directive.daily_macro_bias) else "TP2 (Major Macro Station Floor)"
    lines.append(f"  • {c_white}{tp2_label}{c_rst}: {c_green}{tp2_s}{c_rst} (+{directive.tp2_pips:.1f} {pip_unit} │ R:R {directive.risk_reward_ratio:.2f}:1)")
    lines.append(f"  • {c_white}Macro Invalidation Point{c_rst}       : {c_gray}{inv_s}{c_rst}")
    lines.append("---")
    
    # ── Section 5: Thesis, Pantangan & Future Roadmap ──
    lines.append(f" {c_bold}{c_white}THESIS & INSTITUTIONAL NARRATIVE{c_rst}:")
    for wline in textwrap.wrap(directive.daily_mandate_thesis, width=width - 6):
        lines.append(f"  {c_gray}{wline}{c_rst}")
    
    lines.append(f" {c_bold}{c_red}PANTANGAN (FORBIDDEN TRAPS){c_rst}:")
    traps = directive.forbidden_traps if directive.forbidden_traps else ["None"]
    for trap in traps:
        for wline in textwrap.wrap(f"• {trap}", width=width - 6):
            lines.append(f"  {c_yellow}{wline}{c_rst}")
            
    if directive.future_macro_roadmap:
        lines.append(f" {c_bold}{c_cyan}FUTURE MACRO ROADMAP{c_rst}:")
        for sub_r in str(directive.future_macro_roadmap).split("\n"):
            sub_r = sub_r.strip()
            if not sub_r:
                continue
            for wline in textwrap.wrap(sub_r, width=width - 6):
                lines.append(f"  {c_white}{wline}{c_rst}")

    title = f"TOP-DOWN MACRO STRATEGIC DIRECTIVE: {clean_sym}"
    return UI.make_box(title, lines, width=width, border_color=c_cyan)


def render_macro_summary_table(directives, width=105):
    """
    Renders a multi-pair tabular summary of Top-Down Macro Strategic Directives.
    """
    c_cyan = UI.CYAN
    c_rst = UI.RST
    c_white = UI.WHITE
    c_bold = UI.BOLD
    c_yellow = UI.YELLOW
    c_green = UI.GREEN
    c_red = UI.RED
    c_gray = UI.GRAY

    hdr = f"+{'-' * (width - 2)}+"
    title_text = f"TOP-DOWN MACRO STRATEGIC COMPASS ({len(directives)} SIMBOL)"
    title_bar = f"| {c_bold}{c_white}{title_text}{c_rst}"
    title_bar = UI.pad_line(title_bar, width - 1) + "|"
    
    cols = (
        f"| {c_bold}{c_cyan}{'SYMBOL':<10}{c_rst} | "
        f"{c_bold}{c_cyan}{'MACRO BIAS':<18}{c_rst} | "
        f"{c_bold}{c_cyan}{'DIRECTIVE':<22}{c_rst} | "
        f"{c_bold}{c_cyan}{'SUB-FLOOR':<10}{c_rst} | "
        f"{c_bold}{c_cyan}{'SUB-CEIL':<10}{c_rst} | "
        f"{c_bold}{c_cyan}{'SL(p)':<6}{c_rst} | "
        f"{c_bold}{c_cyan}{'R:R':<5}{c_rst} |"
    )
    
    div = f"+{'-'*12}+{'-'*20}+{'-'*24}+{'-'*12}+{'-'*12}+{'-'*8}+{'-'*7}+"
    
    out = [hdr, title_bar, div, cols, div]
    
    for d in directives:
        sym_c = d.symbol.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "").replace("_", "")
        b_color = c_green if "BULL" in d.daily_macro_bias else (c_red if "BEAR" in d.daily_macro_bias else c_yellow)
        e_color = c_green if "BUY" in d.primary_execution_directive else (c_red if "SELL" in d.primary_execution_directive else c_yellow)
        
        is_jpy = "JPY" in sym_c
        is_crypto_or_gold = "BTC" in sym_c or "XAU" in sym_c
        fmt = "{:.1f}" if is_crypto_or_gold else ("{:.3f}" if is_jpy else "{:.5f}")
        
        sf_str = fmt.format(d.sub_floor_50) if d.sub_floor_50 > 0 else "-"
        sc_str = fmt.format(d.sub_ceiling_50) if d.sub_ceiling_50 > 0 else "-"
        
        bias_short = d.daily_macro_bias.replace("BULLISH_", "BULL_").replace("BEARISH_", "BEAR_")
        exec_short = d.primary_execution_directive.replace("HUNT_", "")
        
        line = (
            f"| {c_white}{sym_c:<10}{c_rst} | "
            f"{b_color}{bias_short:<18}{c_rst} | "
            f"{e_color}{exec_short:<22}{c_rst} | "
            f"{c_green}{sf_str:<10}{c_rst} | "
            f"{c_red}{sc_str:<10}{c_rst} | "
            f"{c_yellow}{d.intraday_sl_pips:<6.1f}{c_rst} | "
            f"{c_green}{d.risk_reward_ratio:<5.2f}{c_rst} |"
        )
        out.append(line)
        
    out.append(div)
    return "\n".join(out)





