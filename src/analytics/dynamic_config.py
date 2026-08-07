"""
Adaptive Dynamic Config System (Self-Tuning Guardrails).

Monitors performance metrics (win rate over recent trades) and safely adapts
trading parameters (consensus threshold, risk multipliers) within strict
pre-approved Python safety boundaries.
"""
import os
import json
import time

DYNAMIC_CONFIG_FILE = os.path.join(config.DATA_DIR, "dynamic_rules.json")


# Strict Python Min/Max Guardrails (Safety Bounds)
MIN_CONSENSUS_THRESHOLD = 2
MAX_CONSENSUS_THRESHOLD = 3
MIN_SL_MULTIPLIER = 1.2
MAX_SL_MULTIPLIER = 2.5

class DynamicConfig:
    def __init__(self):
        self.consensus_threshold = 2
        self.sl_multiplier = 1.5
        self.tp_multiplier = 3.0
        self.status_message = "Normal Risk Regime"
        self._load_rules()

    def _load_rules(self):
        """Load dynamic rules from disk."""
        try:
            if os.path.exists(DYNAMIC_CONFIG_FILE):
                with open(DYNAMIC_CONFIG_FILE, "r") as f:
                    data = json.load(f)
                self.consensus_threshold = int(data.get("consensus_threshold", 2))
                self.sl_multiplier = float(data.get("sl_multiplier", 1.5))
                self.tp_multiplier = float(data.get("tp_multiplier", 3.0))
                self.status_message = data.get("status_message", "Loaded from disk")
        except Exception as e:
            print(f"[DYNAMIC CONFIG WARNING] Gagal memuat dynamic_rules.json: {e}")

    def _save_rules(self):
        """Persist dynamic rules to disk."""
        try:
            with open(DYNAMIC_CONFIG_FILE, "w") as f:
                json.dump({
                    "consensus_threshold": self.consensus_threshold,
                    "sl_multiplier": self.sl_multiplier,
                    "tp_multiplier": self.tp_multiplier,
                    "status_message": self.status_message,
                    "last_updated": time.time()
                }, f, indent=4)
        except Exception as e:
            print(f"[DYNAMIC CONFIG WARNING] Gagal menyimpan dynamic_rules.json: {e}")

    def adapt_from_performance(self, closed_deals):
        """
        Calculates recent win rate from closed deals and dynamically adjusts rules.
        """
        if not closed_deals or len(closed_deals) < 3:
            return

        wins = sum(1 for d in closed_deals if d.get("profit", 0) >= 0)
        total = len(closed_deals)
        win_rate = (wins / total) * 100.0

        if win_rate < 40.0:
            # Low win rate regime -> Tighten risk (require 3/3 consensus)
            self.consensus_threshold = 3
            self.sl_multiplier = 1.2
            self.status_message = f"🛡️ Defensif (Win Rate {win_rate:.0f}%: Membutuhkan Konsensus 3/3)"
        elif win_rate > 70.0:
            # High win rate regime -> Standard optimal parameters
            self.consensus_threshold = 2
            self.sl_multiplier = 1.5
            self.status_message = f"🚀 Optimal (Win Rate {win_rate:.1f}%: Standar 2/3 Konsensus)"
        else:
            self.consensus_threshold = 2
            self.sl_multiplier = 1.5
            self.status_message = f"⚖️ Stabil (Win Rate {win_rate:.1f}%)"

        # Apply strict safety bounds
        self.consensus_threshold = max(MIN_CONSENSUS_THRESHOLD, min(MAX_CONSENSUS_THRESHOLD, self.consensus_threshold))
        self.sl_multiplier = max(MIN_SL_MULTIPLIER, min(MAX_SL_MULTIPLIER, self.sl_multiplier))

        self._save_rules()
        print(f"⚙️ [DYNAMIC CONFIG] Adaptasi Parameter: {self.status_message}")

# Singleton instance
dynamic_rules = DynamicConfig()
