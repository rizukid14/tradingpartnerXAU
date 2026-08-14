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
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    GRAY = "\033[90m"

    # Background Colors
    BG_RED = "\033[41m\033[97m\033[1m"
    BG_GREEN = "\033[42m\033[97m\033[1m"
    BG_YELLOW = "\033[43m\033[30m\033[1m"
    BG_BLUE = "\033[44m\033[97m\033[1m"
    BG_MAGENTA = "\033[45m\033[97m\033[1m"
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


def render_banner(account_info=None, symbol="XAUUSD-ECNc", tf="M5", mode="xau", is_live=True):
    """Renders a modern clean ASCII banner without any emojis."""
    badge_mode = UI.badge_live() if is_live else UI.badge_dry()
    acc_text = f"Live Account #{account_info}" if account_info else "Trading Terminal"
    
    title_line = f"{UI.BOLD}{UI.WHITE}RIZUKID MULTI LLM CONSENSUS TRADING BOT{UI.RST} {UI.YELLOW}PRO MAX{UI.RST}"
    status_line = f"Status: {badge_mode} | Account: {UI.WHITE}{acc_text}{UI.RST} | Symbol: {UI.YELLOW}{symbol} ({tf}){UI.RST} | Mode: {UI.CYAN}{mode.upper()}{UI.RST}"
    
    items = [
        title_line,
        "---",
        status_line
    ]
    return UI.make_box("TRADING TERMINAL", items, width=74, border_color=UI.CYAN)

