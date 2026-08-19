"""
CLI Theme & Styling - Legacy Gold Branch Edition

Special Theme Color: GOLD / AMBER / YELLOW (Signature identifier for Legacy Gold M5 Scalper branch).
Provides ANSI color constants, tags, badges, status clock rendering, and banner layout.
"""
import sys
import shutil

# ANSI Color Codes
class UI:
    RST = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Core Theme Palette (Gold / Amber Theme for Legacy Branch)
    GOLD = "\033[38;5;214m"       # Gold / Vivid Amber
    AMBER = "\033[38;5;208m"      # Deep Gold/Orange
    YELLOW = "\033[93m"           # Bright Yellow
    CYAN = "\033[96m"             # Bright Cyan
    BLUE = "\033[94m"             # Blue
    GREEN = "\033[92m"            # Green
    RED = "\033[91m"              # Red
    MAGENTA = "\033[95m"          # Magenta
    GRAY = "\033[90m"             # Dim Gray

    # Backgrounds
    BG_GOLD = "\033[48;5;214m\033[30m\033[1m"
    BG_GREEN = "\033[42m\033[30m\033[1m"
    BG_RED = "\033[41m\033[97m\033[1m"

    @classmethod
    def tag(cls, label, color=None):
        c = color or cls.GOLD
        return f"{c}[{label}]{cls.RST}"

    @classmethod
    def badge_pnl(cls, pnl):
        if pnl > 0:
            return f"{cls.GREEN}+${pnl:.2f}{cls.RST}"
        elif pnl < 0:
            return f"{cls.RED}-${abs(pnl):.2f}{cls.RST}"
        else:
            return f"{cls.GRAY}$0.00{cls.RST}"


def render_banner(account_info=None, symbol="XAUUSD-ECNc", tf="M5", mode="xau", is_live=True):
    """Renders a gold-themed banner identifying the Legacy Gold M5 Scalper branch."""
    mode_str = f"{UI.RED}{UI.BOLD}LIVE EXECUTION{UI.RST}" if is_live else f"{UI.YELLOW}{UI.BOLD}DRY RUN{UI.RST}"
    acc_str = f" | Account: {account_info}" if account_info else ""
    
    banner = f"""
{UI.GOLD}{UI.BOLD}========================================================================{UI.RST}
{UI.GOLD}{UI.BOLD}   [GOLD] BOT TRADING MULTI-LLM - BRANCH LEGACY (GOLD M5 SCALPER)     {UI.RST}
{UI.GOLD}{UI.BOLD}========================================================================{UI.RST}
 {UI.GOLD}> Branch:{UI.RST} {UI.BG_GOLD} LEGACY GOLD (M5) {UI.RST}{acc_str}
 {UI.GOLD}> Target Asset:{UI.RST} {UI.BOLD}{symbol}{UI.RST} ({tf} Scalping)
 {UI.GOLD}> Mode:{UI.RST} {mode_str}
 {UI.GOLD}> AI Models:{UI.RST} OpenAI (gpt-5.4-mini) | Gemini (2.5-flash-lite) | DeepSeek (v4-flash)
{UI.GOLD}{UI.BOLD}------------------------------------------------------------------------{UI.RST}
"""
    return banner
