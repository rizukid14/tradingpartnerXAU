"""
Risk Engine - Comprehensive trade gating system.

Combines the best from:
- XAU-60: Circuit breaker, daily loss halt, spread filter
- xaubot-ai: Recovery mode, session-aware lot multipliers, danger zones,
             weekend protection, cooldown, consecutive loss tracking

Checks before every trade cycle:
1. Daily P/L limit
2. Consecutive loss streak → pause + recovery mode
3. Spread too wide → skip
4. Session filter with lot multiplier (WIB timezone)
5. Danger zone detection (rollover/dead zone)
6. Weekend proximity → close profitable positions
7. Cooldown between trades
8. Max open positions
"""
import time
import os
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import sys
if sys.platform == 'win32':
    import MetaTrader5 as mt5
else:
    try:
        from mt5linux import MetaTrader5 as mt5
    except ImportError:
        import MetaTrader5 as mt5
import config
from src.core import mt5_connector as connector


WIB = ZoneInfo("Asia/Jakarta")

STATE_FILE = os.path.join(config.DATA_DIR, "risk_state.json")



class RiskEngine:
    """Comprehensive risk engine that gates trade entry and manages trading state."""

    def __init__(self):
        self._consecutive_losses = 0
        self._paused_until = 0              # Unix timestamp when pause ends
        self._last_trade_time = 0           # Unix timestamp of last trade
        self._in_recovery_mode = False
        self._session_lot_multiplier = 1.0  # Adjusted per session
        self._known_closed = set()          # Position ids already accounted for
        self._load_state()
        self._sync_closed_positions()

    # =========================================================================
    #  STATE PERSISTENCE (survives restarts)
    # =========================================================================
    def _load_state(self):
        """Restore loss streak / pause / recovery / known closed from disk."""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                self._consecutive_losses = int(data.get("consecutive_losses", 0))
                self._paused_until = float(data.get("paused_until", 0))
                self._in_recovery_mode = bool(data.get("recovery_mode", False))
                self._last_trade_time = float(data.get("last_trade_time", 0))
                self._known_closed = set(data.get("known_closed", []))
        except Exception as e:
            print(f"[RISK WARNING] Gagal memuat state: {e}")

    def _save_state(self):
        """Persist loss streak / pause / recovery / known closed to disk."""
        try:
            with open(STATE_FILE, "w") as f:
                json.dump({
                    "consecutive_losses": self._consecutive_losses,
                    "paused_until": self._paused_until,
                    "recovery_mode": self._in_recovery_mode,
                    "last_trade_time": self._last_trade_time,
                    "known_closed": list(self._known_closed),
                }, f)
        except Exception as e:
            print(f"[RISK WARNING] Gagal menyimpan state: {e}")

    def _sync_closed_positions(self):
        """
        Detect positions closed by MT5 (SL/TP/manual) that the bot never saw close.
        Runs at startup and every can_trade() call so loss streak and daily
        P/L stay accurate even when trades are closed outside the bot.
        """
        closed = connector.get_closed_positions_today()
        if not closed:
            return

        # If starting up for the first time without prior cached state
        if not self._known_closed:
            for c in closed:
                self._known_closed.add(c["ticket"])
            # Calculate current loss streak looking back from the latest deal
            losses = 0
            for c in reversed(closed):
                if c["profit"] < 0:
                    losses += 1
                else:
                    break
            self._consecutive_losses = losses
            self._save_state()
            return

        any_updated = False
        for c in closed:
            if c["ticket"] in self._known_closed:
                continue
            self._known_closed.add(c["ticket"])
            self._record_result(c["profit"])
            any_updated = True

        if any_updated:
            self._save_state()

    # =========================================================================
    #  MASTER GATE
    # =========================================================================
    def can_trade(self):
        """
        Master gate. Returns (bool, reason_string).
        Call this before entering any new trade.
        """
        # 0. Detect trades closed by MT5 since last check (SL/TP/manual)
        self._sync_closed_positions()

        # 1. Check if we're in a pause cooldown (consecutive losses)
        if time.time() < self._paused_until:
            remaining = int(self._paused_until - time.time())
            return False, f"⏸️ Pause setelah {config.MAX_CONSECUTIVE_LOSSES} loss berturut-turut. Sisa: {remaining}s"

        # 2. Check daily loss limit
        daily_ok, daily_msg = self._check_daily_loss()
        if not daily_ok:
            return False, daily_msg

        # 3. Check max open positions
        pos_ok, pos_msg = self._check_max_positions()
        if not pos_ok:
            return False, pos_msg

        # 4. Check cooldown between trades
        cool_ok, cool_msg = self._check_cooldown()
        if not cool_ok:
            return False, cool_msg

        # 5. Check spread
        spread_ok, spread_msg = self._check_spread()
        if not spread_ok:
            return False, spread_msg

        # 6. Check danger zones (rollover/dead zone)
        danger_ok, danger_msg = self._check_danger_zones()
        if not danger_ok:
            return False, danger_msg

        # 7. Check weekend proximity (block new entries near weekend)
        weekend_ok, weekend_msg = self._check_weekend_entry()
        if not weekend_ok:
            return False, weekend_msg

        # 8. Check session filter (also sets lot multiplier)
        session_ok, session_msg = self._check_session()
        if not session_ok:
            return False, session_msg

        return True, "✅ Semua pengecekan risiko lolos."

    # =========================================================================
    #  TRADE RESULT TRACKING
    # =========================================================================
    def record_trade_result(self, profit):
        """Call after a trade closes to track consecutive losses and recovery mode."""
        self._record_result(profit)
        self._save_state()

    def record_position_closed(self, ticket, profit):
        """
        Call when the bot itself closes a position (e.g., weekend close).
        Records the result AND marks the ticket so the deal-history sync
        does not double-count it.
        """
        self._known_closed.add(ticket)
        self.record_trade_result(profit)

    def _record_result(self, profit):
        """Update loss streak / recovery mode from a single realized result."""
        self._last_trade_time = time.time()

        if profit < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
                pause_seconds = config.PAUSE_AFTER_LOSSES_MINUTES * 60
                self._paused_until = time.time() + pause_seconds
                self._in_recovery_mode = True
                print(f"🛑 [RISK] {self._consecutive_losses} loss berturut-turut! "
                      f"Pause {config.PAUSE_AFTER_LOSSES_MINUTES} menit + Recovery Mode aktif.")
        else:
            if self._consecutive_losses > 0:
                print(f"✅ [RISK] Win setelah {self._consecutive_losses} loss. Streak direset.")
            self._consecutive_losses = 0
            # Exit recovery mode after a win
            if self._in_recovery_mode:
                self._in_recovery_mode = False
                print("✅ [RISK] Recovery mode dinonaktifkan setelah win.")

    def record_trade_opened(self):
        """Record that a trade was just opened (for cooldown tracking)."""
        self._last_trade_time = time.time()

    # =========================================================================
    #  LOT SIZE CALCULATION
    # =========================================================================
    def get_effective_lot_size(self):
        """
        Returns adjusted lot size based on:
        - Recovery mode (from xaubot-ai: reduce lot after losses)
        - Session multiplier (from xaubot-ai: boost during London-NY overlap)
        """
        lot = config.LOT_SIZE

        # Recovery mode: reduce lot size
        if self._in_recovery_mode and config.RECOVERY_MODE_ENABLED:
            lot *= config.RECOVERY_LOT_MULTIPLIER
            print(f"🔄 [RECOVERY] Lot size dikurangi: {lot:.2f} (x{config.RECOVERY_LOT_MULTIPLIER})")

        # Session multiplier
        lot *= self._session_lot_multiplier

        # Ensure minimum lot
        lot = max(0.01, round(lot, 2))
        return lot

    @property
    def is_recovery_mode(self):
        return self._in_recovery_mode

    @property
    def session_lot_multiplier(self):
        return self._session_lot_multiplier

    # =========================================================================
    #  INDIVIDUAL CHECKS
    # =========================================================================
    def _check_daily_loss(self):
        """Check today's realized P/L from bot-closed positions in MT5 deal history."""
        try:
            closed = connector.get_closed_positions_today()
            daily_pnl = sum(c["profit"] for c in closed)

            if daily_pnl <= -config.MAX_DAILY_LOSS_USD:
                return False, (f"🚫 [RISK] Batas kerugian harian tercapai! "
                               f"P/L: ${daily_pnl:.2f} (Batas: -${config.MAX_DAILY_LOSS_USD:.2f})")
            return True, ""

        except Exception as e:
            print(f"[RISK WARNING] Gagal memeriksa P/L harian: {e}")
            return True, ""

    def _check_max_positions(self):
        """Check if max open positions (of this bot) reached."""
        positions = mt5.positions_get(symbol=config.SYMBOL)
        bot_positions = [p for p in (positions or []) if p.magic == config.MAGIC_NUMBER]
        max_positions = config.MAX_OPEN_POSITIONS_RECOVERY if self._in_recovery_mode else config.MAX_OPEN_POSITIONS
        if len(bot_positions) >= max_positions:
            return False, f"📊 [RISK] Posisi terbuka sudah {len(bot_positions)}/{max_positions}."
        return True, ""

    def _check_cooldown(self):
        """Check minimum time between trades."""
        if config.TRADE_COOLDOWN_SECONDS <= 0:
            return True, ""
        elapsed = time.time() - self._last_trade_time
        if elapsed < config.TRADE_COOLDOWN_SECONDS:
            remaining = int(config.TRADE_COOLDOWN_SECONDS - elapsed)
            return False, f"⏳ [RISK] Cooldown antar-trade. Tunggu {remaining}s lagi."
        return True, ""

    def _check_spread(self):
        """Check if current spread is acceptable."""
        tick = mt5.symbol_info_tick(config.SYMBOL)
        symbol_info = mt5.symbol_info(config.SYMBOL)
        if tick is None or symbol_info is None:
            return True, ""

        spread_points = round((tick.ask - tick.bid) / symbol_info.point, 1)
        if spread_points > config.MAX_SPREAD_POINTS:
            return False, (f"⚠️ [RISK] Spread terlalu tinggi: {spread_points} pts "
                           f"(Maks: {config.MAX_SPREAD_POINTS} pts). Menunggu...")
        return True, ""

    def _check_danger_zones(self):
        """Check if current time is in a danger zone (rollover/dead zone)."""
        now_wib = datetime.now(WIB)
        current_minutes = now_wib.hour * 60 + now_wib.minute

        for zone in config.DANGER_ZONES_WIB:
            start = zone["start"][0] * 60 + zone["start"][1]
            end = zone["end"][0] * 60 + zone["end"][1]
            if start <= current_minutes < end:
                return False, f"☠️ [RISK] Zona bahaya '{zone['name']}': {zone['reason']}"
        return True, ""

    def _check_weekend_entry(self):
        """Block new trade entry near weekend close."""
        now_wib = datetime.now(WIB)
        # Friday after 22:00 WIB or Saturday before 05:00 WIB → block new entries
        if now_wib.weekday() == 4 and now_wib.hour >= 22:  # Friday night
            return False, "🚫 [RISK] Mendekati penutupan Jumat — tidak membuka posisi baru."
        if now_wib.weekday() == 5:  # Saturday
            return False, "🚫 [RISK] Market tutup (weekend)."
        if now_wib.weekday() == 6:  # Sunday
            return False, "🚫 [RISK] Market tutup (weekend)."
        return True, ""

    def _check_session(self):
        """Check if current time falls within allowed trading sessions. Sets lot multiplier."""
        if not config.SESSION_FILTER_ENABLED:
            self._session_lot_multiplier = 1.0
            return True, ""

        now_wib = datetime.now(WIB)
        current_minutes = now_wib.hour * 60 + now_wib.minute

        for session in config.ALLOWED_SESSIONS_WIB:
            start = session["start"][0] * 60 + session["start"][1]
            end = session["end"][0] * 60 + session["end"][1]

            # Handle overnight sessions (e.g., NY 20:00 - 05:00)
            if start > end:
                in_session = current_minutes >= start or current_minutes < end
            else:
                in_session = start <= current_minutes < end

            if in_session:
                self._session_lot_multiplier = session.get("lot_multiplier", 1.0)
                return True, ""

        self._session_lot_multiplier = 1.0
        return False, f"💤 [RISK] Di luar sesi trading (WIB {now_wib.strftime('%H:%M')}). Menunggu..."

    # =========================================================================
    #  WEEKEND POSITION MANAGEMENT (from xaubot-ai position_manager.py)
    # =========================================================================
    def check_weekend_positions(self):
        """
        Check if we should close profitable positions before weekend.
        Returns list of tickets to close with reasons.
        """
        if not config.WEEKEND_CLOSE_ENABLED:
            return []

        now_wib = datetime.now(WIB)

        # Only check on Friday
        if now_wib.weekday() != 4:
            return []

        # Calculate hours until Saturday 05:00 WIB (market close)
        market_close = now_wib.replace(hour=5, minute=0, second=0) + timedelta(days=1)
        hours_to_close = (market_close - now_wib).total_seconds() / 3600

        if hours_to_close > config.WEEKEND_CLOSE_HOURS_BEFORE:
            return []

        positions = mt5.positions_get(symbol=config.SYMBOL)
        if positions is None or len(positions) == 0:
            return []

        actions = []
        for pos in positions:
            if pos.magic != config.MAGIC_NUMBER:
                continue

            profit = pos.profit + pos.swap + pos.commission

            if profit >= config.WEEKEND_CLOSE_PROFIT_MIN_USD:
                actions.append({
                    "ticket": pos.ticket,
                    "reason": f"📅 Weekend close: mengambil profit ${profit:.2f} sebelum gap weekend "
                              f"({hours_to_close:.1f}h ke penutupan)"
                })
            elif profit < 0 and abs(profit) > config.WEEKEND_MAX_LOSS_TO_HOLD_USD:
                actions.append({
                    "ticket": pos.ticket,
                    "reason": f"📅 Weekend close: cut loss ${profit:.2f} terlalu besar untuk "
                              f"ditahan melewati weekend"
                })

        return actions

    # =========================================================================
    #  DAILY P/L HELPER
    # =========================================================================
    def get_daily_pnl(self):
        """Returns today's realized P/L (bot trades only) for display purposes."""
        try:
            closed = connector.get_closed_positions_today()
            return sum(c["profit"] for c in closed)
        except Exception:
            return 0.0

    def get_status_summary(self):
        """Returns a dict with current risk engine status for display."""
        now_wib = datetime.now(WIB)
        return {
            "time_wib": now_wib.strftime("%H:%M:%S"),
            "day": now_wib.strftime("%A"),
            "recovery_mode": self._in_recovery_mode,
            "consecutive_losses": self._consecutive_losses,
            "session_lot_multiplier": self._session_lot_multiplier,
            "daily_pnl": self.get_daily_pnl(),
        }
