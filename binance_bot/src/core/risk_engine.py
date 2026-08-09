"""
Risk Engine untuk bot Binance spot.

- Daily loss limit (dari realisasi P/L)
- Cooldown antar trade
- Max posisi open (spot: aset yang dimiliki)
- Risk-based sizing: qty = risk_usd / sl_distance
- Min notional validasi
- State persist ke data/risk_state.json
"""
import json
import logging
import os
import time

import config
from src.core import binance_connector as connector

log = logging.getLogger("binance_bot")

STATE_FILE = os.path.join(config.DATA_DIR, "risk_state.json")


class RiskEngine:
    def __init__(self):
        self._consecutive_losses = 0
        self._paused_until = 0
        self._last_trade_time = 0
        self._known_closed = set()
        self._load_state()

    # ------------------------------------------------------------------
    # STATE
    # ------------------------------------------------------------------
    def _load_state(self):
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                self._consecutive_losses = int(data.get("consecutive_losses", 0))
                self._paused_until = float(data.get("paused_until", 0))
                self._last_trade_time = float(data.get("last_trade_time", 0))
                self._known_closed = set(data.get("known_closed", []))
        except Exception as e:
            log.warning(f"[RISK] Gagal load state: {e}")

    def _save_state(self):
        try:
            os.makedirs(config.DATA_DIR, exist_ok=True)
            with open(STATE_FILE, "w") as f:
                json.dump({
                    "consecutive_losses": self._consecutive_losses,
                    "paused_until": self._paused_until,
                    "last_trade_time": self._last_trade_time,
                    "known_closed": list(self._known_closed),
                }, f)
        except Exception as e:
            log.warning(f"[RISK] Gagal save state: {e}")

    # ------------------------------------------------------------------
    # DAILY P/L (dari myTrades — sell fills = realisasi)
    # ------------------------------------------------------------------
    def get_daily_pnl(self):
        try:
            closed = connector.get_closed_positions_today()
            return sum(c["profit"] for c in closed)
        except Exception:
            return 0.0

    def _check_daily_loss(self):
        daily = self.get_daily_pnl()
        if daily <= -config.MAX_DAILY_LOSS_USD:
            return False, f"🚫 [RISK] Batas kerugian harian! P/L: ${daily:.2f} (batas -${config.MAX_DAILY_LOSS_USD:.2f})"
        return True, ""

    # ------------------------------------------------------------------
    # OPEN POSITIONS (spot: aset yang dimiliki)
    # ------------------------------------------------------------------
    def get_open_positions(self, symbol=None):
        """Posisi spot = aset base (BTC) yang dimiliki. Return list atau []."""
        sym = symbol or config.SYMBOL
        qty = connector.get_asset_balance(sym)
        if qty <= 0:
            return []
        ticker = connector.get_ticker(sym)
        price = ticker["price"] if ticker else 0
        return [{
            "symbol": sym,
            "asset": sym.replace("USDT", ""),
            "qty": qty,
            "entry_price": price,  # spot tidak simpan entry di exchange — estimasi dari ticker
            "side": "BUY",
        }]

    def _check_max_positions(self):
        positions = self.get_open_positions()
        if len(positions) >= config.MAX_OPEN_POSITIONS:
            return False, f"📊 [RISK] Posisi {len(positions)}/{config.MAX_OPEN_POSITIONS} tercapai."
        return True, ""

    # ------------------------------------------------------------------
    # COOLDOWN & SPREAD
    # ------------------------------------------------------------------
    def _check_cooldown(self):
        elapsed = time.time() - self._last_trade_time
        if elapsed < config.TRADE_COOLDOWN_SECONDS:
            remaining = int(config.TRADE_COOLDOWN_SECONDS - elapsed)
            return False, f"⏳ [RISK] Cooldown. Tunggu {remaining}s."
        return True, ""

    def _check_spread(self):
        ticker = connector.get_ticker(config.SYMBOL)
        if not ticker:
            return False, "[RISK] Gagal dapat ticker (spread check)."
        if ticker["spread_pct"] > config.MAX_SPREAD_PCT:
            return False, (f"🚫 [RISK] Spread terlalu lebar: {ticker['spread_pct']:.3f}% "
                           f"(max {config.MAX_SPREAD_PCT}%).")
        return True, ""

    # ------------------------------------------------------------------
    # MASTER GATE
    # ------------------------------------------------------------------
    def can_trade(self):
        """Gate entry baru. Return (bool, reason)."""
        for check in (self._check_daily_loss, self._check_max_positions,
                      self._check_cooldown, self._check_spread):
            ok, reason = check()
            if not ok:
                return False, reason
        return True, "✅ Semua gate lolos."

    # ------------------------------------------------------------------
    # SIZING
    # ------------------------------------------------------------------
    def get_effective_qty(self, price, sl_pct):
        """
        Hitung qty dari risk% equity:
          risk_usd = equity * RISK_PERCENT / 100
          sl_distance_usd = price * sl_pct / 100
          qty = risk_usd / sl_distance_usd
        Clamp ke step size + validasi min notional.
        """
        equity = connector.get_account_balance_usdt()
        if equity <= 0:
            return None, "Equity USDT 0 atau gagal didapat."
        risk_usd = equity * config.RISK_PERCENT / 100.0
        if sl_pct is None or sl_pct <= 0:
            sl_pct = config.DEFAULT_SL_PCT
        sl_distance = price * sl_pct / 100.0
        if sl_distance <= 0:
            return None, "SL distance tidak valid."
        qty = risk_usd / sl_distance

        qty = connector.round_qty(config.SYMBOL, qty)
        ok, reason = connector.validate_order(config.SYMBOL, qty, price)
        if not ok:
            return None, f"Sizing gagal: {reason} (qty {qty}, equity ${equity:.2f})"
        notional = qty * price
        if notional < config.MIN_NOTIONAL_USD:
            return None, (f"Notional ${notional:.2f} < min ${config.MIN_NOTIONAL_USD} "
                          f"— modal terlalu kecil untuk risk {config.RISK_PERCENT}%.")
        return qty, f"qty {qty} (risk ${risk_usd:.2f}, SL {sl_pct}%)"

    # ------------------------------------------------------------------
    # RESULT TRACKING
    # ------------------------------------------------------------------
    def record_trade_result(self, profit):
        self._last_trade_time = time.time()
        if profit < 0:
            self._consecutive_losses += 1
            log.info(f"[RISK] Loss {profit:+.2f} — streak {self._consecutive_losses}")
        else:
            self._consecutive_losses = 0
            log.info(f"[RISK] Win {profit:+.2f} — streak reset")
        self._save_state()

    def record_trade_opened(self):
        self._last_trade_time = time.time()
        self._save_state()
