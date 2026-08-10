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

def _safe_print(text):
    """Prints text safely without throwing UnicodeEncodeError on Windows terminals."""
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass


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

    def _load_memory(self, symbol):
        """Loads memory from memory_lessons.json and returns a dict for the specific symbol."""
        try:
            if os.path.exists(MEMORY_FILE):
                with open(MEMORY_FILE, "r") as f:
                    data = json.load(f)
                
                # Check for legacy format (lessons directly at the root)
                if "lessons" in data:
                    print("🔄 [MIGRATION] Mengonversi memory_lessons.json ke format multi-simbol...")
                    legacy_lessons = data.get("lessons", [])
                    legacy_summary = data.get("lessons_summary", "")
                    legacy_tickets = list(data.get("evaluated_tickets", []))
                    
                    migrated_lessons = {}
                    for item in legacy_lessons:
                        sym = item.get("symbol", "XAUUSD-ECNc") if isinstance(item, dict) else "XAUUSD-ECNc"
                        # Normalise string lessons to dict format
                        if isinstance(item, str):
                            item = {"symbol": "XAUUSD-ECNc", "lesson": item, "theme": _extract_theme(item)}
                        migrated_lessons.setdefault(sym, []).append(item)
                        
                    data = {
                        "XAUUSD-ECNc": {
                            "lessons": migrated_lessons.get("XAUUSD-ECNc", []),
                            "lessons_summary": legacy_summary,
                            "evaluated_tickets": legacy_tickets
                        },
                        "BTCUSD.c": {
                            "lessons": migrated_lessons.get("BTCUSD.c", []),
                            "lessons_summary": "",
                            "evaluated_tickets": legacy_tickets
                        }
                    }
                    # Save migrated structure back immediately
                    with open(MEMORY_FILE, "w") as fw:
                        json.dump(data, fw, indent=4)
                
                # Retrieve symbol data, initialize if missing
                if symbol not in data:
                    data[symbol] = {
                        "lessons": [],
                        "lessons_summary": "",
                        "evaluated_tickets": []
                    }
                
                return {
                    "lessons": data[symbol].get("lessons", []),
                    "lessons_summary": data[symbol].get("lessons_summary", ""),
                    "evaluated_tickets": set(data[symbol].get("evaluated_tickets", []))
                }
        except Exception as e:
            print(f"[EVALUATOR WARNING] Gagal memuat memory_lessons.json: {e}")
            
        return {"lessons": [], "lessons_summary": "", "evaluated_tickets": set()}

    def _save_memory(self, symbol, lessons, summary, evaluated_tickets):
        """Save lessons, summary, and evaluated tickets for a specific symbol to memory_lessons.json."""
        try:
            data = {}
            if os.path.exists(MEMORY_FILE):
                with open(MEMORY_FILE, "r") as f:
                    try:
                        data = json.load(f)
                        # If legacy file is loaded, force it to dict before updating
                        if "lessons" in data:
                            data = {}
                    except Exception:
                        data = {}
            
            # Update symbol data
            data[symbol] = {
                "lessons": lessons[-MAX_LESSONS:],
                "lessons_summary": summary,
                "evaluated_tickets": list(evaluated_tickets)
            }
            
            # Save back to disk
            with open(MEMORY_FILE, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[EVALUATOR WARNING] Gagal menyimpan memory_lessons.json: {e}")

    def _summarize_and_reset(self, symbol, lessons, evaluated_tickets):
        """
        When lessons reach MAX_LESSONS, ask gpt-5.4-mini to condense ALL lessons
        into one summary, store it, and reset lessons to empty.
        """
        # Group lessons by theme (default "entry" if missing for legacy entries)
        by_theme = {}
        for l in lessons:
            theme = l.get("theme") if isinstance(l, dict) else None
            lesson_text = l.get("lesson", "") if isinstance(l, dict) else str(l)
            theme = theme or _extract_theme(lesson_text)
            by_theme.setdefault(theme, []).append(lesson_text)

        theme_summary = ", ".join(f"{t}:{len(items)}" for t, items in by_theme.items())
        _safe_print(f"📚 [LESSONS COMPOSITION] {len(lessons)} entries across themes for {symbol} - {theme_summary}")

        # Build a balanced prompt
        theme_blocks = []
        for theme, items in sorted(by_theme.items()):
            bullets = "\n".join(f"- {it}" for it in items)
            theme_blocks.append(f"## {theme.upper()}\n{bullets}")

        lessons_text = "\n\n".join(theme_blocks)
        prompt = f"""
You are an expert trading post-mortem analyst. Below are the last {len(lessons)} lessons learned from scalping trades on {symbol} ({asset_desc(symbol)}), grouped by theme.

{lessons_text}

Task: Summarize ALL of these into ONE concise, actionable block of trading wisdom (maximum 60 words). Preserve coverage of EACH theme (entries, risk, timing, psychology) when applicable — do not let one theme dominate. Output ONLY the summary text — no intro, no bullets numbering.
"""
        try:
            summary = llm.query_primary_model(prompt)
            if summary:
                summary = summary.strip()
                _safe_print(f"📋 [LESSONS SUMMARY FOR {symbol}] {summary}")
                self._save_memory(symbol, [], summary, evaluated_tickets)
        except Exception as e:
            print(f"[LESSONS SUMMARY ERROR] Gagal meringkas lessons untuk {symbol}: {e}")

    def check_and_evaluate_closed_trades(self, deals=None):
        """
        Evaluates closed positions that haven't been processed yet.
        Pass `deals` (list of newly-closed deals from risk.sync_closed_positions)
        to evaluate immediately on close; otherwise fetches today's closed
        positions from MT5 deal history (used at candle cycle for stragglers).
        Re-evaluation after a restart is prevented by the persisted
        evaluated_tickets set in memory_lessons.json.
        """
        closed_deals = deals if deals is not None else connector.get_closed_positions_today()
        if not closed_deals:
            return

        # Cache memories we load so we don't reload multiple times in the same loop
        loaded_memories = {}

        for deal in closed_deals:
            ticket = deal["ticket"]
            profit = deal["profit"]
            deal_symbol = deal.get("symbol", config.SYMBOL)

            if deal_symbol not in loaded_memories:
                loaded_memories[deal_symbol] = self._load_memory(deal_symbol)

            mem = loaded_memories[deal_symbol]

            if ticket in mem["evaluated_tickets"]:
                continue

            # Mark ticket as processed
            mem["evaluated_tickets"].add(ticket)
            self._save_memory(deal_symbol, mem["lessons"], mem["lessons_summary"], mem["evaluated_tickets"])

            # NOTE: Telegram alert for closed trades is now sent in real time by
            # the main loop (risk.sync_closed_positions, every 5s) — not here.
            # This method only does the post-mortem lesson generation.

            # Fetch rich trade details from MT5 (entry/exit prices, duration, reason closed, points)
            trade_details = connector.get_trade_details(ticket)
            if not trade_details:
                trade_details = {
                    "ticket": ticket,
                    "symbol": deal_symbol,
                    "profit": profit,
                    "type": deal.get("type", "UNKNOWN"),
                    "reason": deal.get("reason", "unknown"),
                }

            # Generate post-mortem lesson via LLM with rich execution context
            pos_type_label = trade_details.get("type", "")
            _safe_print(f"\n🔍 [POST-MORTEM] Menganalisis hasil trade tiket #{ticket} ({deal_symbol}, {pos_type_label}, P/L: ${profit:.2f})...")
            lesson = self._analyze_trade_with_llm(ticket, profit, deal_symbol, trade_details)
            if lesson:
                theme = _extract_theme(lesson)
                _safe_print(f"💡 [PELAJARAN BARU DITERIMA] [{theme}] {lesson}")
                mem["lessons"].append({"symbol": deal_symbol, "lesson": lesson, "theme": theme})
                
                if len(mem["lessons"]) >= MAX_LESSONS:
                    self._summarize_and_reset(deal_symbol, mem["lessons"], mem["evaluated_tickets"])
                    # Reload memory after reset to get the empty list & updated summary
                    loaded_memories[deal_symbol] = self._load_memory(deal_symbol)
                else:
                    self._save_memory(deal_symbol, mem["lessons"], mem["lessons_summary"], mem["evaluated_tickets"])

    def _analyze_trade_with_llm(self, ticket, profit, trade_symbol=None, trade_details=None):
        """Asks the primary LLM (Gemini/OpenAI) to evaluate the trade outcome with rich context."""
        outcome_str = f"PROFIT (+${profit:.2f})" if profit >= 0 else f"LOSS (-${abs(profit):.2f})"
        trade_symbol = trade_symbol or config.SYMBOL
        tf_str = "30-minute intraday" if config.is_crypto(trade_symbol) else "5-minute scalping"
        
        # Build rich execution details block
        if trade_details and isinstance(trade_details, dict):
            pos_type = trade_details.get("type", "UNKNOWN")
            volume = trade_details.get("volume", "")
            volume_str = f" ({volume} lot)" if volume else ""
            entry_p = trade_details.get("entry_price")
            exit_p = trade_details.get("exit_price")
            entry_t = trade_details.get("entry_time", "")
            exit_t = trade_details.get("exit_time", "")
            dur_min = trade_details.get("duration_min")
            reason_closed = trade_details.get("reason", "unknown")
            pts_pnl = trade_details.get("points_pnl")

            pts_str = f" ({pts_pnl:+} pts)" if pts_pnl is not None else ""
            price_str = f"Entry: {entry_p} -> Exit: {exit_p}" if (entry_p and exit_p) else ""
            dur_str = f"{dur_min} minutes" if dur_min is not None else "N/A"

            exec_context = f"""Trade Execution Details:
- Ticket: #{ticket}
- Position Type: {pos_type}{volume_str}
- Execution: {price_str}
- Opened At: {entry_t} | Closed At: {exit_t} (Duration: {dur_str})
- Outcome: {outcome_str}{pts_str}
- Close Trigger: {reason_closed} (e.g., SL, TP, manual, AI Re-evaluator)"""
        else:
            exec_context = f"""Trade Summary:
- Position Ticket: #{ticket}
- Outcome: {outcome_str}"""

        prompt = f"""
You are an expert trading post-mortem analyst evaluating a closed position on {trade_symbol} ({asset_desc(trade_symbol)}).

{exec_context}

Task:
Analyze this exact trade result in the context of {tf_str} rules on {asset_desc(trade_symbol)}.
Examine WHY the trade entered at {trade_details.get('entry_price', 'entry') if trade_details else 'entry'} resulted in {outcome_str} when exiting at {trade_details.get('exit_price', 'exit') if trade_details else 'exit'} via {trade_details.get('reason', 'close trigger') if trade_details else 'trigger'}.
Provide ONE single, highly actionable, concise lesson learned (maximum 25 words).
The lesson MUST start with '[LESSON]' and provide a concrete rule for future setups (e.g., avoiding buys directly into overhead resistance, enforcing pullbacks near EMA, or adjusting SL buffer).

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
        symbol = config.SYMBOL
        mem = self._load_memory(symbol)
        
        context = ""
        summary = mem.get("lessons_summary", "")
        lessons = mem.get("lessons", [])
        
        if summary:
            context += f"\n### {symbol} LESSONS LEARNED (SUMMARY)\n{summary}\n"

        relevant = [
            item if isinstance(item, str) else item.get("lesson", "")
            for item in lessons
            if isinstance(item, str) or item.get("symbol", "") == symbol
        ]
        if relevant:
            recent = relevant[-3:]  # Take last 3 lessons
            bullets = "\n".join([f"- {item}" for item in recent])
            header = f"### {symbol} LESSONS LEARNED FROM RECENT TRADES (SINCE SUMMARY)" if summary else f"### {symbol} LESSONS LEARNED FROM RECENT TRADES"
            context += f"\n{header}\n{bullets}\n"

        return context

# Global singleton instance
evaluator = TradeEvaluator()
