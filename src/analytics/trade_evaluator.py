"""
Trade Evaluator & Lessons Memory System (Post-Mortem Engine).

Analyzes closed trades using the primary Gemini LLM to generate actionable
lessons learned, persisting them in memory_lessons.json and feeding them back
into future 5-minute scalping prompts for continuous in-context learning.
"""
import os
import json
import time
import config
from src.core import mt5_connector as connector, llm_client as llm





MEMORY_FILE = os.path.join(config.DATA_DIR, "memory_lessons.json")

MAX_LESSONS = 15

asset_desc = llm.asset_desc

# Theme keywords used to diversify the summary so it does not skew to one bias.
_THEME_KEYWORDS = {
    "entry":      ["entry", "entries", "enter", "zone", "pullback", "breakout", "momentum", "follow-through"],
    "risk":       ["stop", "loss", "sl", "risk", "drawdown", "exposure", "size", "lot"],
    "timing":     ["news", "release", "session", "time", "schedule", "calendar", "open", "close market"],
    "psychology": ["patience", "fear", "greed", "discipline", "revenge", "fomo", "hesitation", "hold"],
}


def _extract_theme(lesson_text):
    """
    Lightweight keyword-based theme tagger so the summary rotation can
    surface lessons from multiple themes rather than letting one topic
    (e.g. resistance) dominate every prompt forever.

    Override rules: news/release/calendar keywords always win on "timing";
    patience/discipline/revenge always win on "psychology"; stop/loss/risk
    always win on "risk". Otherwise the highest-scoring theme wins.
    """
    text = (lesson_text or "").lower()
    scores = {theme: 0 for theme in _THEME_KEYWORDS}
    for theme, kws in _THEME_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                scores[theme] += 1

    # Hard overrides for unambiguous signals
    timing_markers = ["news", "release", "calendar", "nfp", "fomc"]
    if any(m in text for m in timing_markers):
        return "timing"
    psych_markers = ["patience", "discipline", "revenge", "fomo", "hesitation"]
    if any(m in text for m in psych_markers):
        return "psychology"
    risk_markers = ["stop loss", "drawdown", "exposure", "lot size"]
    if any(m in text for m in risk_markers):
        return "risk"

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "entry"

class TradeEvaluator:
    def __init__(self):
        self._evaluated_tickets = set()
        self._lessons = []
        self._lessons_summary = ""
        self._load_memory()

    def _load_memory(self):
        """Load lessons from disk."""
        try:
            if os.path.exists(MEMORY_FILE):
                with open(MEMORY_FILE, "r") as f:
                    data = json.load(f)
                self._lessons = data.get("lessons", [])
                self._lessons_summary = data.get("lessons_summary", "")
                self._evaluated_tickets = set(data.get("evaluated_tickets", []))
        except Exception as e:
            print(f"[EVALUATOR WARNING] Gagal memuat memory_lessons.json: {e}")

    def _save_memory(self):
        """Save lessons, summary, and evaluated tickets to disk."""
        try:
            with open(MEMORY_FILE, "w") as f:
                json.dump({
                    "lessons": self._lessons[-MAX_LESSONS:],
                    "lessons_summary": self._lessons_summary,
                    "evaluated_tickets": list(self._evaluated_tickets),
                    "last_updated": time.time()
                }, f, indent=4)
        except Exception as e:
            print(f"[EVALUATOR WARNING] Gagal menyimpan memory_lessons.json: {e}")

    def _summarize_and_reset(self):
        """
        When lessons reach MAX_LESSONS, ask gpt-5.4-mini to condense ALL lessons
        into one summary, store it, and reset lessons to empty. The prompt then
        only reads the summary (compact, token-light, still actionable).

        Diversification: sample up to 4 themes to keep the summary balanced
        instead of letting one topic dominate. Themes with no representation
        are simply omitted from the prompt.
        """
        # Group lessons by theme (default "entry" if missing for legacy entries)
        by_theme = {}
        for l in self._lessons:
            theme = l.get("theme") if isinstance(l, dict) else None
            lesson_text = l.get("lesson", "") if isinstance(l, dict) else str(l)
            theme = theme or _extract_theme(lesson_text)
            by_theme.setdefault(theme, []).append(lesson_text)

        # Show count of themes represented
        theme_summary = ", ".join(f"{t}:{len(items)}" for t, items in by_theme.items())
        print(f"📚 [LESSONS COMPOSITION] {len(self._lessons)} entries across themes — {theme_summary}")

        # Build a balanced prompt with up to 4 themes represented
        theme_blocks = []
        for theme, items in sorted(by_theme.items()):
            bullets = "\n".join(f"- {it}" for it in items)
            theme_blocks.append(f"## {theme.upper()}\n{bullets}")

        lessons_text = "\n\n".join(theme_blocks)
        prompt = f"""
You are an expert trading post-mortem analyst. Below are the last {len(self._lessons)} lessons learned from scalping trades, grouped by theme.

{lessons_text}

Task: Summarize ALL of these into ONE concise, actionable block of trading wisdom (maximum 60 words). Preserve coverage of EACH theme (entries, risk, timing, psychology) when applicable — do not let one theme dominate. Output ONLY the summary text — no intro, no bullets numbering.
"""
        try:
            summary = llm.query_primary_model(prompt)
            if summary:
                summary = summary.strip()
                # Fallback model override: use gpt-5.4-mini for the summarizer
                self._lessons_summary = summary
                print(f"📋 [LESSONS SUMMARY] {summary}")
                self._lessons = []
                self._save_memory()
        except Exception as e:
            print(f"[LESSONS SUMMARY ERROR] Gagal meringkas lessons: {e}")

    def check_and_evaluate_closed_trades(self):
        """
        Fetches today's closed positions from MT5 deal history and evaluates
        any newly closed positions that haven't been processed yet.
        """
        closed_deals = connector.get_closed_positions_today()
        if not closed_deals:
            return

        for deal in closed_deals:
            ticket = deal["ticket"]
            profit = deal["profit"]
            deal_symbol = deal.get("symbol", config.SYMBOL)

            if ticket in self._evaluated_tickets:
                continue

            # Mark ticket as processed
            self._evaluated_tickets.add(ticket)
            self._save_memory()

            # Generate post-mortem lesson via Gemini
            print(f"\n🔍 [POST-MORTEM] Menganalisis hasil trade tiket #{ticket} ({deal_symbol}, P/L: ${profit:.2f})...")
            lesson = self._analyze_trade_with_llm(ticket, profit, deal_symbol)
            if lesson:
                theme = _extract_theme(lesson)
                print(f"💡 [PELAJARAN BARU DITERIMA] [{theme}] {lesson}")
                self._lessons.append({"symbol": deal_symbol, "lesson": lesson, "theme": theme})
                # When lessons reach MAX_LESSONS, summarize & reset (AI reads summary only)
                if len(self._lessons) >= MAX_LESSONS:
                    self._summarize_and_reset()
                else:
                    self._save_memory()

    def _analyze_trade_with_llm(self, ticket, profit, trade_symbol=None):
        """Asks the primary LLM (Gemini) to evaluate the trade outcome."""
        outcome_str = f"PROFIT (+${profit:.2f})" if profit >= 0 else f"LOSS (-${abs(profit):.2f})"
        trade_symbol = trade_symbol or config.SYMBOL
        
        prompt = f"""
You are an expert trading post-mortem analyst evaluating a closed scalping position on {trade_symbol} ({asset_desc(trade_symbol)}).

Trade Summary:
- Position Ticket: {ticket}
- Outcome: {outcome_str}

Task:
Analyze this trade result in the context of 5-minute scalping rules on {asset_desc(trade_symbol)}.
Provide ONE single, highly actionable, concise lesson learned (maximum 20 words).
The lesson MUST start with '[LESSON]' and offer a concrete tip for future trading setups (e.g. caution during overbought RSI, avoiding entries near resistance ahead of news, or respecting dynamic EMA support).

Respond with the lesson text ONLY. Do not include introductory conversational filler.
"""
        try:
            response_text = llm.query_primary_model(prompt)
            if response_text:
                clean_lesson = response_text.strip()
                if not clean_lesson.startswith("[LESSON]"):
                    clean_lesson = f"[LESSON] {clean_lesson}"
                return clean_lesson
        except Exception as e:
            print(f"[POST-MORTEM ERROR] Gagal mengevaluasi trade: {e}")
        return None

    def get_lessons_context(self):
        """Returns formatted lessons markdown block for prompt injection.
        Uses the condensed SUMMARY when available (token-light), plus the most
        recent raw lessons until the next summary reset. Per-symbol isolated."""
        context = ""
        if self._lessons_summary:
            context += f"\n### LESSONS LEARNED (SUMMARY)\n{self._lessons_summary}\n"

        # Handle both old (plain string) and new (dict with symbol) lesson formats
        relevant = [
            item if isinstance(item, str) else item.get("lesson", "")
            for item in self._lessons
            if isinstance(item, str) or item.get("symbol", "") == config.SYMBOL
        ]
        if relevant:
            recent = relevant[-5:]  # Take last 5 lessons
            bullets = "\n".join([f"- {item}" for item in recent])
            header = "### LESSONS LEARNED FROM RECENT TRADES (SINCE SUMMARY)" if self._lessons_summary else "### LESSONS LEARNED FROM RECENT TRADES"
            context += f"\n{header}\n{bullets}\n"

        return context

# Global singleton instance
evaluator = TradeEvaluator()
