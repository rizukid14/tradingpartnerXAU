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
import mt5_connector as connector
import llm_client as llm

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory_lessons.json")
MAX_LESSONS = 15

class TradeEvaluator:
    def __init__(self):
        self._evaluated_tickets = set()
        self._lessons = []
        self._load_memory()

    def _load_memory(self):
        """Load lessons from disk."""
        try:
            if os.path.exists(MEMORY_FILE):
                with open(MEMORY_FILE, "r") as f:
                    data = json.load(f)
                self._lessons = data.get("lessons", [])
                self._evaluated_tickets = set(data.get("evaluated_tickets", []))
        except Exception as e:
            print(f"[EVALUATOR WARNING] Gagal memuat memory_lessons.json: {e}")

    def _save_memory(self):
        """Save lessons and evaluated tickets to disk."""
        try:
            # Keep only the most recent MAX_LESSONS
            trimmed_lessons = self._lessons[-MAX_LESSONS:]
            with open(MEMORY_FILE, "w") as f:
                json.dump({
                    "lessons": trimmed_lessons,
                    "evaluated_tickets": list(self._evaluated_tickets),
                    "last_updated": time.time()
                }, f, indent=4)
        except Exception as e:
            print(f"[EVALUATOR WARNING] Gagal menyimpan memory_lessons.json: {e}")

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

            if ticket in self._evaluated_tickets:
                continue

            # Mark ticket as processed
            self._evaluated_tickets.add(ticket)
            self._save_memory()

            # Generate post-mortem lesson via Gemini
            print(f"\n🔍 [POST-MORTEM] Menganalisis hasil trade tiket #{ticket} (P/L: ${profit:.2f})...")
            lesson = self._analyze_trade_with_llm(ticket, profit)
            if lesson:
                print(f"💡 [PELAJARAN BARU DITERIMA] {lesson}")
                self._lessons.append(lesson)
                self._save_memory()

    def _analyze_trade_with_llm(self, ticket, profit):
        """Asks the primary LLM (Gemini) to evaluate the trade outcome."""
        outcome_str = f"PROFIT (+${profit:.2f})" if profit >= 0 else f"LOSS (-${abs(profit):.2f})"
        
        prompt = f"""
You are an expert trading post-mortem analyst evaluating a closed scalping position on {config.SYMBOL}.

Trade Summary:
- Position Ticket: {ticket}
- Outcome: {outcome_str}

Task:
Analyze this trade result in the context of 5-minute scalping rules on Gold/Forex.
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
        """Returns formatted lessons markdown block for prompt injection."""
        if not self._lessons:
            return ""
        
        recent = self._lessons[-5:] # Take last 5 lessons
        bullets = "\n".join([f"- {item}" for item in recent])
        return f"\n### LESSONS LEARNED FROM RECENT TRADES\n{bullets}\n"

# Global singleton instance
evaluator = TradeEvaluator()
