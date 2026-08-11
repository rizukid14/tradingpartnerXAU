"""
Recent Decision Memory - tracks the bot's last N decisions per symbol.

Each call to record() appends one entry (signal, confidence, reasoning
excerpt) for the current symbol. The prompt injects the recent window
via get_context() so the LLM knows it has been HOLDing for X candles
in a row and can self-correct the perpetual-HOLD bias instead of being
a stateless fresh session every cycle.

Per-symbol isolation: gold decisions do not leak into BTC decisions.
Persists to data/decision_memory.json so restart does not erase memory.
"""
import os
import json
import time
import config


STATE_FILE = os.path.join(config.DATA_DIR, "decision_memory.json")

# How many recent decisions to keep per symbol (injected into prompt).
WINDOW_SIZE = 6


class DecisionMemory:
    def __init__(self):
        # { symbol: [ {signal, confidence, reasoning, timestamp}, ... ] }
        self._decisions = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    self._decisions = json.load(f) or {}
        except Exception as e:
            print(f"[DECISION MEMORY WARNING] Gagal memuat decision_memory.json: {e}")
            self._decisions = {}

    def _save(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self._decisions, f, indent=2)
        except Exception as e:
            print(f"[DECISION MEMORY WARNING] Gagal menyimpan decision_memory.json: {e}")

    def record(self, symbol, signal, confidence=None, reasoning=None, result="N/A"):
        """Append one decision for the given symbol. Keeps last WINDOW_SIZE entries.

        result: "OPEN" saat trade dieksekusi (belum close), "N/A" saat HOLD.
        Hasil akhir (TP/SL/BEP) di-set belakangan via update_result() pas posisi close.
        """
        if not symbol:
            return
        entries = self._decisions.setdefault(symbol, [])
        entries.append({
            "signal": signal,
            "confidence": float(confidence) if confidence is not None else None,
            "reasoning_excerpt": (reasoning or "")[:120],
            "result": result,
            "timestamp": time.time(),
        })
        # Trim per-symbol window
        if len(entries) > WINDOW_SIZE:
            self._decisions[symbol] = entries[-WINDOW_SIZE:]
        self._save()

    def update_result(self, symbol, result, profit=None, commission=0.0):
        """Set hasil trade (TP/SL/SL-BEP/manual) pada entry terakhir yang masih
        OPEN/N-A untuk symbol ini, plus profit NET (sudah termasuk komisi) biar
        summarize_recent_outcomes bisa hitung win/loss yang AKURAT.

        Dipanggil dari loop close detection — update entry trade yang baru ditutup.
        """
        if not symbol:
            return False
        entries = self._decisions.get(symbol, [])
        # Cari entry PALING TUA yang masih "OPEN"/"N/A" dengan signal != HOLD —
        # posisi yang dibuka lebih dulu biasanya kena SL/TP lebih dulu.
        for e in entries:
            if e.get("signal") == "HOLD":
                continue
            if e.get("result") in ("OPEN", "N/A", None):
                e["result"] = result or "N/A"
                if profit is not None:
                    e["profit"] = round(float(profit), 2)
                if commission:
                    e["commission"] = round(float(commission), 2)
                self._save()
                return True
        return False

    def get_context(self, symbol):
        """Return markdown block of recent decisions for prompt injection."""
        entries = self._decisions.get(symbol, [])
        if not entries:
            return ""

        # Count consecutive HOLD at the tail — useful cue for the LLM.
        consecutive_hold = 0
        for e in reversed(entries):
            if e.get("signal") == "HOLD":
                consecutive_hold += 1
            else:
                break

        lines = []
        for i, e in enumerate(entries, start=1):
            conf = e.get("confidence")
            conf_str = f" (conf {conf * 100:.0f}%)" if conf is not None else ""
            excerpt = e.get("reasoning_excerpt") or ""
            lines.append(f"{i}. {e.get('signal')}{conf_str} — {excerpt}")

        hold_note = ""
        if consecutive_hold >= 3:
            hold_note = (
                f"\nNote: last {consecutive_hold} cycles were HOLD for this symbol — "
                f"re-examine whether the threshold for entry is now too strict, "
                f"or whether price action genuinely lacks a setup."
            )

        return (
            f"\n### RECENT DECISIONS (this bot, last {len(entries)} cycles for {symbol})\n"
            + "\n".join(lines)
            + hold_note
            + "\n"
        )


# Singleton instance
memory = DecisionMemory()