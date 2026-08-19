"""
CLI Theme & Styling - Legacy Gold & Crisp White Edition

Special Theme Palette: Premium Gold & Pure White (Branch Legacy Identifier)
"""
import sys

# ANSI Color Codes
class UI:
    RST = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Core Theme Palette: Gold + Crisp White
    GOLD = "\033[38;5;220m"        # Bright Vivid Gold
    AMBER = "\033[38;5;214m"       # Deep Warm Gold
    WHITE = "\033[97m"            # Crisp White
    WHITE_BOLD = "\033[97m\033[1m" # Pure Bold White
    GRAY = "\033[90m"             # Soft Gray
    GREEN = "\033[92m"            # Emerald Green
    RED = "\033[91m"              # Rose Red

    # Background Badges
    BG_GOLD = "\033[48;5;220m\033[30m\033[1m"
    BG_WHITE = "\033[47m\033[30m\033[1m"

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


def render_banner(account_info=None, symbol="XAUUSD-ECN", tf="M5", mode="xau", is_live=True):
    """Renders an elegant Gold & Pure White banner identifying the M1 Micro SuperScalper branch."""
    mode_str = f"{UI.RED}{UI.BOLD}LIVE EXECUTION{UI.RST}" if is_live else f"{UI.GOLD}{UI.BOLD}DRY RUN{UI.RST}"
    acc_str = f" {UI.GRAY}|{UI.RST} Account: {UI.WHITE_BOLD}{account_info}{UI.RST}" if account_info else ""
    
    banner = f"""
{UI.GOLD}========================================================================{UI.RST}
{UI.GOLD}{UI.BOLD}   + BOT TRADING MULTI-LLM  --  M1 MICRO SUPERSCALPER +          {UI.RST}
{UI.GOLD}========================================================================{UI.RST}
 {UI.GOLD}> Branch:{UI.RST}       {UI.BG_GOLD} M1 MICRO SUPERSCALPER {UI.RST}{acc_str}
 {UI.GOLD}> Target Asset:{UI.RST} {UI.WHITE_BOLD}{symbol}{UI.RST} {UI.GRAY}({tf}/M1 Mega-Tight Scalping){UI.RST}
 {UI.GOLD}> Execution:{UI.RST}    {mode_str} {UI.GRAY}(Dynamic 1.5% Equity Risk Sizing - Mega Lot Jumbo){UI.RST}
 {UI.GOLD}> AI Models:{UI.RST}    {UI.WHITE}OpenAI{UI.RST} {UI.GRAY}(gpt-5.4-mini){UI.RST} {UI.GOLD}* {UI.WHITE}Gemini{UI.RST} {UI.GRAY}(2.5-flash-lite){UI.RST} {UI.GOLD}* {UI.WHITE}DeepSeek{UI.RST} {UI.GRAY}(v4-flash){UI.RST}
 {UI.GOLD}> Speed Mode:{UI.RST}   {UI.WHITE_BOLD}Single-Pass Ultra-Fast (~1.0s){UI.RST} {UI.GRAY}[No Debates/MTF Delay]{UI.RST}
{UI.GOLD}------------------------------------------------------------------------{UI.RST}
"""
    return banner
