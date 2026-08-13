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


def render_banner(account_info=None, symbol="XAUUSD-ECNc", tf="M5", mode="xau", is_live=True):
    """Renders a modern clean ASCII banner without any emojis."""
    badge_mode = UI.badge_live() if is_live else UI.badge_dry()
    acc_text = f"Live Account #{account_info}" if account_info else "Trading Terminal"
    
    out = [
        f"{UI.CYAN}========================================================================{UI.RST}",
        f"{UI.CYAN}|{UI.RST}  {UI.BOLD}{UI.WHITE}RIZUKID MULTI LLM CONSENSUS TRADING BOT{UI.RST} {UI.YELLOW}PRO MAX{UI.RST}                    {UI.CYAN}|{UI.RST}",
        f"{UI.CYAN}========================================================================{UI.RST}",
        f"  {UI.BOLD}Status:{UI.RST} {badge_mode} | {UI.BOLD}Terminal:{UI.RST} {UI.WHITE}{acc_text}{UI.RST} | {UI.BOLD}Symbol:{UI.RST} {UI.YELLOW}{symbol} ({tf}){UI.RST}",
        f"{UI.DIM}------------------------------------------------------------------------{UI.RST}"
    ]
    return "\n".join(out)
