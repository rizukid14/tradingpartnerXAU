"""
CLI Theme & Styling Helper for Trading Bot Terminal
Provides ANSI colors, sleek box-drawing borders, badges, and progress bars.
Fully compatible with Windows 10/11 Terminal & Linux/macOS.
"""

import sys
import shutil
import unicodedata

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
    BG_CYAN = "\033[46m\033[30m\033[1m"
    BG_DARK = "\033[100m\033[97m"

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


def render_scanner_banner(account_info=None, is_live=True, total_symbols=22):
    """Renders a sleek ASCII banner for 22-Pair Quant Screener & Multi-LLM Jury."""
    badge_mode = UI.badge_live() if is_live else UI.badge_dry()
    acc_text = f"Live Account #{account_info}" if account_info else "Trading Terminal"
    
    title_line = f"{UI.BOLD}{UI.WHITE}RIZUKID QUANT FUNNEL & MULTI-LLM JURY{UI.RST} {UI.PURPLE}[22-PAIR PRO]{UI.RST}"
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
    
    items = [
        f"{UI.BOLD}{direction_color}⚡ STAGE 1 QUANT RADAR TRIGGER: {candidate.symbol} [{dir_str}]{UI.RST}",
        "---",
        f"• Setup Type  : {UI.WHITE}{candidate.setup_type}{UI.RST}",
        f"• Macro Trend : {UI.CYAN}{candidate.macro_compass}{UI.RST}",
        f"• Location    : {UI.YELLOW}{candidate.dealing_range_pos*100:.1f}% Dealing Range (Wick {candidate.rejection_wick_ratio*100:.0f}%){UI.RST}",
        f"• Proposal    : Entry={candidate.trigger_price} | SL={candidate.suggested_sl} | TP={candidate.suggested_tp} (R:R {candidate.risk_reward_ratio:.1f}:1)",
        f"• Friction    : Spread={candidate.current_spread_pts} pts | ATR={candidate.current_atr_pts:.1f} pts"
    ]
    return UI.make_box(f"QUANT SETUP DETECTED: {candidate.symbol}", items, width=76, border_color=UI.PURPLE)


def render_hacker_bento_hud(macro_cache=None, account_info=None, daily_pnl=0.0, open_positions=None, active_models=None):
    """
    Renders an Ultra-Clean Cyberpunk Hacker-Style 2x2 Bento Box Terminal HUD.
    Features a FULL 22-Pair Live Heat Matrix with dynamic volatility & SMC badges.
    """
    c_cyan = UI.CYAN
    c_purp = UI.PURPLE
    c_rst = UI.RST
    
    lw = 58  # Left column inner width (119 total cols)
    rw = 58  # Right column inner width
    
    # ── TILE 1: FULL 22-PAIR QUANT RADAR HEAT MATRIX (Top Left) ──
    t1_lines = []
    
    import config
    scanner_syms = config.get_scanner_symbols() if hasattr(config, "get_scanner_symbols") else []
    all_symbols = [
        s.replace("-ECNc", "").replace("-ECN", "").replace(".c", "").replace("m", "")
        for s in scanner_syms
    ] or [
        "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "GBPJPY", "EURJPY",
        "AUDUSD", "USDCAD", "USDCHF", "CADJPY", "EURGBP", "EURCHF",
        "EURAUD", "EURCAD", "CHFJPY", "GBPAUD", "GBPCAD", "GBPCHF",
        "NZDCAD", "AUDCAD", "AUDCHF", "AUDJPY"
    ]
    
    hot_pairs = []
    in_zone_pairs = []
    
    if macro_cache:
        def _format_cell(sym_prefix):
            for k, v in macro_cache.items():
                if k.startswith(sym_prefix):
                    adx = v.get('adx', 0.0)
                    pos = v.get('dealing_range_pos', 0.5)
                    is_bull = v.get('is_bull', False)
                    is_bear = v.get('is_bear', False)
                    
                    # Determine Badge
                    if adx >= 28:
                        badge = f"{UI.YELLOW}🔥{UI.RST}"
                        hot_pairs.append(f"{sym_prefix} ({adx:.0f})")
                    elif pos <= 0.38 or pos >= 0.62:
                        badge = f"{UI.GREEN}🎯{UI.RST}"
                        zone_lbl = "Disc" if pos <= 0.38 else "Prem"
                        in_zone_pairs.append(f"{sym_prefix} ({pos*100:.0f}% {zone_lbl})")
                    elif adx < 18:
                        badge = f"{UI.CYAN}🧊{UI.RST}"
                    else:
                        badge = f"{UI.GRAY}●{UI.RST}"
                        
                    # Direction Arrow
                    if is_bull:
                        arrow = f"{UI.GREEN}▲{UI.RST}"
                    elif is_bear:
                        arrow = f"{UI.RED}▼{UI.RST}"
                    else:
                        arrow = f"{UI.GRAY}●{UI.RST}"
                        
                    adx_str = f"{adx:.0f}" if adx > 0 else "--"
                    return f"{sym_prefix} {arrow}{adx_str} {badge}"
            return f"{sym_prefix} {UI.GRAY}●--{UI.RST}  "

        # Render 3 pairs per row (7-8 rows)
        for r in range(0, len(all_symbols), 3):
            p1 = all_symbols[r]
            p2 = all_symbols[r+1] if r+1 < len(all_symbols) else None
            p3 = all_symbols[r+2] if r+2 < len(all_symbols) else None
            
            c1 = UI.pad_line(_format_cell(p1), 16)
            c2 = UI.pad_line(_format_cell(p2) if p2 else "", 16)
            c3 = UI.pad_line(_format_cell(p3) if p3 else "", 16)
            
            t1_lines.append(f" {c1} │ {c2} │ {c3}")
    else:
        t1_lines = [
            f" {UI.YELLOW}● Inisialisasi 22-Pair Macro Compass...{UI.RST}",
            f" {UI.DIM}Memindai D1/H4 dealing ranges & level Asia...{UI.RST}",
            f" {UI.DIM}Fast Radar bersiap untuk sweep 60 detik.{UI.RST}",
            f" {UI.DIM}Monitoring 21 FX Crosses + Gold 24/5.{UI.RST}"
        ]
    
    # ── TILE 2: LIVE ACCOUNT & RISK INTELLIGENCE HUD (Top Right) ──
    acc = account_info or {}
    srv = acc.get("server", "VTMarkets-Live 3")
    login_id = acc.get("login", "27556325")
    eq = acc.get("equity", 6005.04)
    bal = acc.get("balance", 6034.87)
    
    t2_lines = [
        f" Server    : {UI.WHITE}{srv}{UI.RST} (Login #{login_id})",
        f" Equity    : {UI.BOLD}{UI.WHITE}${eq:,.2f}{UI.RST} | Balance: ${bal:,.2f}",
        f" Daily P/L : {UI.badge_pnl(daily_pnl)} | Max Loss Cap: {UI.RED}4.0%{UI.RST}",
    ]
    if open_positions:
        pos_strs = []
        for p in open_positions[:3]:
            s_clean = p.get("symbol", "").replace("-ECNc", "").replace(".c", "")
            pos_strs.append(f"{s_clean}: {UI.badge_pnl(p.get('profit', 0.0))}")
        t2_lines.append(f" Posisi    : {' | '.join(pos_strs)}")
    else:
        t2_lines.append(f" Posisi    : {UI.GRAY}No active positions (Flat / Cash){UI.RST}")
        
    hot_str = ", ".join(hot_pairs[:3]) if hot_pairs else "None (Normal Vol)"
    in_zone_str = ", ".join(in_zone_pairs[:3]) if in_zone_pairs else "None (Mid-Range)"
    
    t2_lines.append(f" Top Hot   : {UI.YELLOW}{hot_str}{UI.RST} 🔥")
    t2_lines.append(f" In-Zone   : {UI.GREEN}{in_zone_str}{UI.RST} 🎯")
    t2_lines.append(f" Radar     : {UI.CYAN}22 Pairs Swept Every 60s (0 Tokens){UI.RST}")
    t2_lines.append(f" Risk Gate : {UI.DIM}Safety Floor 1.3x ATR | Spread Shield{UI.RST}")
        
    # ── TILE 3: SMC LIQUIDITY & TIMEFRAME (Bottom Left) ──
    t3_lines = [
        f" Sesi     : {UI.WHITE}Dynamic Session-Adaptive (Tokyo H1 / LDN-NY M30){UI.RST}",
        f" Judas    : {UI.YELLOW}14:00 - 18:00 WIB{UI.RST} (Asian Liquidity Sweep Active)",
        f" Structure: {UI.CYAN}100-bar H1 (Disc <=38% | Prem >=62%){UI.RST}",
        f" News     : {UI.GREEN}ACTIVE (TradingView News Window Shield){UI.RST}"
    ]
    
    # ── TILE 4: 3-LLM JURY PROTOCOL (Bottom Right) ──
    models = active_models or ["OpenAI", "Gemini", "DeepSeek"]
    t4_lines = [
        f" Protocol : {UI.PURPLE}3-Way Asymmetric Jury (APPROVE / REJECT){UI.RST}",
        f" Model 1  : {UI.WHITE}OpenAI o4-mini{UI.RST} (Structure Validator)",
        f" Model 2  : {UI.WHITE}Gemini 3.1-Flash-Lite{UI.RST} (Speed Screener)",
        f" Model 3  : {UI.WHITE}DeepSeek V4-Flash{UI.RST} (Devil's Advocate)"
    ]
    
    # ── ASSEMBLE 2x2 BENTO BOX ──
    out = []
    
    # Top Header
    h1_title = f"+-- [ {UI.BOLD}{UI.WHITE}22-PAIR LIVE QUANT RADAR MATRIX{UI.RST}{c_cyan} ] "
    d1 = max(0, lw - UI.disp_width(h1_title) + 1)
    h1_bar = f"{c_cyan}{h1_title}{'-' * d1}+{c_rst}"
    
    h2_title = f"-- [ {UI.BOLD}{UI.WHITE}LIVE ACCOUNT & RISK INTELLIGENCE{UI.RST}{c_cyan} ] "
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
    m1_title = f"+-- [ {UI.BOLD}{UI.WHITE}SMC LIQUIDITY & MARKET REGIME{UI.RST}{c_cyan} ] "
    md1 = max(0, lw - UI.disp_width(m1_title) + 1)
    m1_bar = f"{c_cyan}{m1_title}{'-' * md1}+{c_rst}"
    
    m2_title = f"-- [ {UI.BOLD}{UI.WHITE}3-LLM CONSENSUS JURY HUD{UI.RST}{c_cyan} ] "
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
    status_line = f"Status: {badge_mode} | Account: {UI.WHITE}{acc_text}{UI.RST} | Active: {UI.YELLOW}{symbol} ({tf}){UI.RST} | Mode: {UI.CYAN}{mode.upper()}{UI.RST}"
    
    items = [
        title_line,
        "---",
        status_line
    ]
    return UI.make_box("FX PAIRS TRADING TERMINAL PRO", items, width=76, border_color=UI.CYAN)




