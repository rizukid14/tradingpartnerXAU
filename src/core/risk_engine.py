"""
Risk Engine - Comprehensive trade gating system.

Combines the best from:
- XAU-60: Circuit breaker, daily loss halt, spread filter
- xaubot-ai: Recovery mode, session-aware lot multipliers, danger zones,
             weekend protection, cooldown, consecutive loss tracking

Checks before every trade cycle:
1. Daily P/L limit
2. Consecutive loss streak -> pause + recovery mode
3. Spread too wide -> skip
4. Session filter with lot multiplier (WIB timezone)
5. Danger zone detection (rollover/dead zone)
6. Weekend proximity -> close profitable positions
7. Cooldown between trades
8. Max open positions
"""
import time
import os
import json
import math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import config
from config import mt5
from src.core import mt5_connector as connector
from src.core.cli_theme import UI


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
        self._atr_h1_pts = None             # ATR H1 dalam points, di-update tiap cycle
        self._load_state()
        self.sync_closed_positions()

    def update_atr_h1(self, atr_pts):
        """Update ATR H1 (dalam points). Dipanggil dari main loop setelah df tersedia.
        Dipakai oleh _check_spread() untuk ATR-based spread cap pada FX pairs."""
        if atr_pts and atr_pts > 0:
            self._atr_h1_pts = float(atr_pts)

    def get_remaining_pause(self):
        """Returns the remaining pause duration in seconds, or 0 if not paused."""
        if time.time() < self._paused_until:
            return int(self._paused_until - time.time())
        return 0

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

    def sync_closed_positions(self):
        """
        Detect positions closed by MT5 (SL/TP/manual) that the bot never saw close.
        Returns the list of NEWLY detected closed deals (each: ticket, symbol,
        profit, reason, comment, type) so callers can react immediately
        (Telegram alert, dashboard update) instead of waiting for the next cycle.

        Updates loss streak / daily P/L / recovery mode in real time.
        Called at startup, every can_trade(), and every 5s in the main loop.
        """
        # Use a 24-hour lookback to cover time-boundary gaps (e.g. midnight WIB)
        # and self-heal any deals closed while the bot was offline.
        closed = connector.get_closed_positions_today(symbol=None, lookback_hours=24)
        if not closed:
            return []

        # If starting up for the first time without prior cached state: seed
        # the known set (no alerts - these are historical, not new closes).
        if not self._known_closed:
            for c in closed:
                self._known_closed.add(c["ticket"])
            losses = 0
            for c in reversed(closed):
                # BEP tolerance dinamis: kalah cuma sebesar komisi ? loss.
                tol = config.bep_tolerance_for(c)
                if c["profit"] < -tol:
                    losses += 1
                else:
                    break
            self._consecutive_losses = losses
            self._save_state()
            return []

        new_deals = []
        for c in closed:
            if c["ticket"] in self._known_closed:
                continue
            self._known_closed.add(c["ticket"])
            self._record_result(c["profit"], c.get("commission", 0.0))
            new_deals.append(c)

        if new_deals:
            self._save_state()
        return new_deals

    # =========================================================================
    #  MASTER GATE
    # =========================================================================
    def can_trade(self):
        """
        Master gate. Returns (bool, reason_string).
        Call this before entering any new trade.
        """
        # 0. Check manual trading pause flag
        if getattr(config, "TRADING_PAUSED", False):
            return False, " Trading dipause secara manual via API/Tool."

        # 0. Detect trades closed by MT5 since last check (SL/TP/manual)
        self.sync_closed_positions()
        # 1. Check if we're in a pause cooldown (consecutive losses)
        if time.time() < self._paused_until:
            remaining = int(self._paused_until - time.time())
            return False, f" Pause setelah {config.MAX_CONSECUTIVE_LOSSES} loss berturut-turut. Sisa: {remaining}s"

        # 2. Check daily loss limit
        daily_ok, daily_msg = self._check_daily_loss()
        if not daily_ok:
            return False, daily_msg

        # 2b. Check daily profit target (stop trade setelah profit harian tercapai)
        profit_ok, profit_msg = self._check_daily_profit_target()
        if not profit_ok:
            return False, profit_msg

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

        return True, " Semua pengecekan risiko lolos."

    # =========================================================================
    #  TRADE RESULT TRACKING
    # =========================================================================
    def record_trade_result(self, profit, commission=0.0):
        """Call after a trade closes to track consecutive losses and recovery mode."""
        self._record_result(profit, commission)
        self._save_state()

    def record_position_closed(self, ticket, profit, commission=0.0):
        """
        Call when the bot itself closes a position (e.g., weekend close).
        Records the result AND marks the ticket so the deal-history sync
        does not double-count it.
        """
        self._known_closed.add(ticket)
        self.record_trade_result(profit, commission)

    def _record_result(self, profit, commission=0.0):
        """Update loss streak / recovery mode from a single realized result."""
        self._last_trade_time = time.time()

        # BEP tolerance DINAMIS per trade: minimal BREAK_EVEN_TOLERANCE_USD
        # (0.04), tapi naik mengikuti komisi aktual trade - 0.01 lot kena 0.06,
        # 0.10 lot kena 0.60, 0.26 lot kena 1.56. Trade yang kalah cuma
        # sebesar biaya komisi (arahnya BEP) tidak boleh nambah loss streak.
        tol = config.bep_tolerance_for({"commission": commission})
        if abs(profit) <= tol:
            print(f" [RISK] Trade BEP ({profit:+.2f} USD, tol {tol:.2f} USD). Streak dipertahankan ({self._consecutive_losses}).")
            return

        if profit < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
                pause_seconds = config.PAUSE_AFTER_LOSSES_MINUTES * 60
                self._paused_until = time.time() + pause_seconds
                self._in_recovery_mode = True
                print(f" [RISK] {self._consecutive_losses} loss berturut-turut! "
                      f"Pause {config.PAUSE_AFTER_LOSSES_MINUTES} menit + Recovery Mode aktif.")
        else:
            if self._consecutive_losses > 0:
                print(f" [RISK] Win setelah {self._consecutive_losses} loss. Streak direset.")
            self._consecutive_losses = 0
            # Batalkan pause kalau masih aktif - alasan pause (5 loss beruntun)
            # sudah tidak berlaku karena ada win yang menandakan market recovery.
            # Sebelumnya pause tetap jalan sampai timer habis + pesan "5 loss
            # berturut-turut" terus muncul padahal streak sudah nol (bug 15 Agustus).
            if time.time() < self._paused_until:
                self._paused_until = 0
                print(" [RISK] Pause dibatalkan setelah win (streak sudah reset).")
            # Exit recovery mode only after a win that clears the minimum
            # profit threshold - a tiny win should not instantly reset the
            # reduced-lot protection after a losing streak.
            if self._in_recovery_mode:
                exit_profit = getattr(config, "RECOVERY_EXIT_PROFIT_USD", 0.10)
                if profit >= exit_profit:
                    self._in_recovery_mode = False
                    print(f" [RISK] Recovery mode dinonaktifkan setelah win {profit:+.2f} USD (>= ${exit_profit:.2f}).")
                else:
                    print(f" [RISK] Win kecil ({profit:+.2f} USD) < ${exit_profit:.2f}. Recovery mode dipertahankan.")

    def record_trade_opened(self):
        """Record that a trade was just opened (for cooldown tracking)."""
        self._last_trade_time = time.time()

    # =========================================================================
    #  LOT SIZE CALCULATION (risk-based)
    # =========================================================================
    def get_effective_lot_size(self, sl_points=None, split_count=1):
        """
        Risk-based lot sizing: lot = risk_usd / (sl_distance_usd per 1.0 lot),
        so each trade risks RISK_PERCENT_BTC/XAU of the account balance.

        split_count: kalau sinyal membuka N posisi sekaligus (misal 3/3
        unanimous -> 2 posisi), risk dibagi N supaya TOTAL risk per sinyal
        tetap risk_pct, bukan N x risk_pct.

        Order of operations (important):
          1. Compute risk-based lot from the (already floored) SL distance,
             dibagi split_count.
          2. Apply risk multipliers (recovery x0.5, session x1.0/1.2).
          3. Clamp to broker volume_min/max and round DOWN to volume_step
             LAST (floor, bukan round - round() bisa naikkan lot MELEBIHI
             risk target), so multipliers are not distorted by rounding.
        Falls back to config.lot_size_for() when SL is unknown.
        """
        symbol = config.SYMBOL
        risk_pct = config.risk_percent_for(symbol)
        try:
            account = mt5.account_info()
            equity = float(account.equity) if account else 0.0
        except Exception:
            equity = 0.0

        si = mt5.symbol_info(symbol)
        if not sl_points or sl_points <= 0 or equity <= 0 or si is None:
            # No SL given -> fall back to the static per-symbol lot
            lot = config.lot_size_for(symbol)
            return self._apply_lot_multipliers(lot, symbol)

        # USD value of a 1-point move for 1.0 lot
        usd_per_pt_1lot = si.trade_tick_value * 1.0 * (si.point / si.trade_tick_size) if si.trade_tick_size else 0.0
        if usd_per_pt_1lot <= 0:
            lot = config.lot_size_for(symbol)
            return self._apply_lot_multipliers(lot, symbol)

        split_count = max(1, int(split_count))
        risk_usd_total = equity * risk_pct / 100.0
        risk_usd = risk_usd_total / split_count  # per posisi
        sl_usd_per_lot = sl_points * usd_per_pt_1lot  # USD loss per 1.0 lot at this SL
        if sl_usd_per_lot <= 0:
            lot = config.lot_size_for(symbol)
            return self._apply_lot_multipliers(lot, symbol)

        lot_raw = risk_usd / sl_usd_per_lot
        print(f" {UI.tag('SIZING', UI.CYAN)} {symbol}: equity ${equity:.2f}, risk {risk_pct}% = ${risk_usd_total:.2f}"
              + (f" ({split_count} posisi -> ${risk_usd:.2f}/posisi)" if split_count > 1 else "")
              + f", SL {sl_points} pts = ${sl_usd_per_lot:.2f}/lot -> raw lot {lot_raw:.4f}")

        # Apply recovery/session multipliers BEFORE clamping so rounding cannot
        # erase the intended reduction.
        lot = self._apply_lot_multipliers(lot_raw, symbol)

        # Clamp to broker volume bounds and round DOWN to step (floor - jangan
        # pakai round(), itu bisa NAIKKAN lot di atas risk target).
        volume_min = getattr(si, "volume_min", 0.01)
        volume_max = getattr(si, "volume_max", 100.0)
        volume_step = getattr(si, "volume_step", 0.01)
        lot = max(volume_min, min(volume_max, lot))
        lot = math.floor(lot / volume_step + 1e-9) * volume_step
        lot = max(volume_min, lot)  # jangan jatuh di bawah volume_min broker
        lot = round(lot, 2)

        # Margin safety net: never let the order exceed available free margin
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is not None:
                margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, lot, tick.ask)
                free_margin = float(account.margin_free) if account else 0.0
                if margin and margin > free_margin * 0.5:  # keep 50% buffer
                    print(f" {UI.tag('SIZING', UI.YELLOW)} Margin {margin:.2f} > 50% free ({free_margin:.2f}). Lot diturunkan.")
                    # Halve until it fits
                    while lot > volume_min and margin > free_margin * 0.5:
                        lot = round((lot - volume_step), 2)
                        margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, lot, tick.ask)
                        if not margin:
                            break
        except Exception:
            pass

        return lot

    def get_volatility_regime_and_multiplier(self, symbol):
        """
        Ide 4: Dynamic Volatility Scaling berbasis ATR Percentile.
        Membandingkan ATR H1 saat ini dengan rata-rata historis (baseline).
        Returns: (regime_name: 'LOW'|'NORMAL'|'HIGH', multiplier: float, vol_ratio: float)
        """
        if not getattr(config, "VOL_REGIME_SCALING_ENABLED", True) or config.is_crypto(symbol):
            return "NORMAL", 1.0, 1.0

        current_atr_pts = self._atr_h1_pts
        if not current_atr_pts or current_atr_pts <= 0:
            return "NORMAL", self._session_lot_multiplier, 1.0

        # Hitung baseline ATR H1 dari 120 candle H1 terakhir (~5 hari trading aktif)
        baseline_atr_pts = None
        try:
            r = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 1, 120)
            if r is not None and len(r) >= 30:
                info = mt5.symbol_info(symbol)
                pt = info.point if info and info.point > 0 else 0.00001
                trs = [max(r[i]['high'] - r[i]['low'],
                           abs(r[i]['high'] - r[i-1]['close']),
                           abs(r[i]['low'] - r[i-1]['close']))
                       for i in range(1, len(r))]
                if trs:
                    baseline_atr_pts = (sum(trs) / len(trs)) / pt
        except Exception:
            pass

        if not baseline_atr_pts or baseline_atr_pts <= 0:
            return "NORMAL", 1.0, 1.0

        vol_ratio = current_atr_pts / baseline_atr_pts
        low_th = getattr(config, "VOL_REGIME_LOW_THRESHOLD", 0.70)
        high_th = getattr(config, "VOL_REGIME_HIGH_THRESHOLD", 1.20)

        if vol_ratio < low_th:
            mult = getattr(config, "VOL_REGIME_LOW_MULTIPLIER", 0.75)
            return "LOW", mult, vol_ratio
        elif vol_ratio > high_th:
            mult = getattr(config, "VOL_REGIME_HIGH_MULTIPLIER", 1.15)
            return "HIGH", mult, vol_ratio
        else:
            mult = getattr(config, "VOL_REGIME_NORMAL_MULTIPLIER", 1.00)
            return "NORMAL", mult, vol_ratio

    def _apply_lot_multipliers(self, lot, symbol):
        """Apply recovery (x0.5) and dynamic volatility/session lot multipliers."""
        if self._in_recovery_mode and config.RECOVERY_MODE_ENABLED:
            lot *= config.RECOVERY_LOT_MULTIPLIER
            print(f" {UI.tag('RECOVERY', UI.YELLOW)} Lot dikurangi: x{config.RECOVERY_LOT_MULTIPLIER}")

        # Ide 4: Ganti jam dinding statis dengan Dynamic Volatility Sizing (ATR Percentile)
        if getattr(config, "VOL_REGIME_SCALING_ENABLED", True) and not config.is_crypto(symbol):
            regime, vol_mult, ratio = self.get_volatility_regime_and_multiplier(symbol)
            lot *= vol_mult
            if vol_mult != 1.0:
                print(f" {UI.tag('VOL REGIME', UI.CYAN)} {symbol}: Volatility {regime} (Ratio {ratio:.2f}x baseline) -> Dynamic Sizing Mult x{vol_mult}")
        else:
            lot *= self._session_lot_multiplier

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
        """Check today's realized P/L from bot-closed positions in MT5 deal history against dynamic % equity limit."""
        try:
            closed = connector.get_closed_positions_today()
            if getattr(config, "DAILY_LOSS_OPENED_TODAY_ONLY", True):
                closed_for_loss = [c for c in closed if c.get("opened_today", True)]
            else:
                closed_for_loss = closed

            daily_pnl = sum(c["profit"] for c in closed_for_loss)

            account = mt5.account_info()
            equity = float(account.equity) if account else (float(account.balance) if account else 0.0)
            loss_pct = getattr(config, "MAX_DAILY_LOSS_PERCENT", 4.0)

            if loss_pct > 0 and equity > 0:
                max_loss_usd = equity * loss_pct / 100.0
                limit_desc = f"-{loss_pct:.1f}% (-${max_loss_usd:.2f})"
            else:
                max_loss_usd = getattr(config, "MAX_DAILY_LOSS_USD", 250.0)
                limit_desc = f"-${max_loss_usd:.2f}"

            if daily_pnl <= -max_loss_usd:
                return False, (f" [RISK] Batas kerugian harian tercapai! "
                               f"P/L: ${daily_pnl:.2f} (Batas: {limit_desc})")
            return True, ""

        except Exception as e:
            print(f"[RISK WARNING] Gagal memeriksa P/L harian: {e}")
            return True, ""

    def _check_daily_profit_target(self):
        """
        Daily profit target (14 Agustus): begitu net profit harian (WIB-midnight,
        dari get_closed_positions_today) mencapai DAILY_PROFIT_TARGET_PERCENT % dari
        equity/balance MT5, bot BERHENTI membuka posisi baru sampai tengah malam WIB
        berikutnya (reset otomatis karena window P/L harian = midnight WIB).
        Nilai 0.0 / negatif = fitur dimatikan.
        """
        try:
            target_pct = getattr(config, "DAILY_PROFIT_TARGET_PERCENT", 0.0)
            if target_pct <= 0:
                return True, ""  # fitur dimatikan

            closed = connector.get_closed_positions_today()
            daily_pnl = sum(c["profit"] for c in closed)  # profit sudah NET (termasuk swap+komisi)

            account = mt5.account_info()
            equity = float(account.equity) if account else (float(account.balance) if account else 0.0)
            # Kalau equity/balance tidak terbaca (MT5 disconnected / None), jangan blokir
            # trade karena target tidak bisa dihitung - biarkan gate lain yang kerja.
            if equity <= 0:
                return True, ""
            target_usd = equity * target_pct / 100.0

            if daily_pnl >= target_usd:
                return False, (f" [RISK] Target Profit Harian Tercapai! P/L: +${daily_pnl:.2f} "
                               f"(Target: +{target_pct:.1f}% / +${target_usd:.2f}). "
                               f"Trading dihentikan sampai besok!")
            return True, ""

        except Exception as e:
            print(f"[RISK WARNING] Gagal memeriksa target profit harian: {e}")
            return True, ""

    def _check_max_positions(self):
        """Check if max open positions (of this bot) reached - aggregated across ALL
        symbols (XAU + FX pairs + BTC), since rotation mode trades multiple symbols."""
        positions = mt5.positions_get()
        bot_positions = [p for p in (positions or []) if p.magic == config.MAGIC_NUMBER]
        max_positions = config.get_max_open_positions(self._in_recovery_mode)
        if len(bot_positions) >= max_positions:
            return False, f" [RISK] Posisi terbuka sudah {len(bot_positions)}/{max_positions} (semua simbol)."
        return True, ""

    def _check_cooldown(self):
        """Check minimum time between trades."""
        if config.TRADE_COOLDOWN_SECONDS <= 0:
            return True, ""
        elapsed = time.time() - self._last_trade_time
        if elapsed < config.TRADE_COOLDOWN_SECONDS:
            remaining = int(config.TRADE_COOLDOWN_SECONDS - elapsed)
            return False, f" [RISK] Cooldown antar-trade. Tunggu {remaining}s lagi."
        return True, ""

    def _check_spread(self):
        """Check if current spread is acceptable."""
        tick = mt5.symbol_info_tick(config.SYMBOL)
        symbol_info = mt5.symbol_info(config.SYMBOL)
        if tick is None or symbol_info is None or not symbol_info.point or symbol_info.point <= 0:
            return False, " [RISK] Tidak bisa memverifikasi spread (MT5 data/point unavailable). Menunggu..."

        if tick.ask <= 0 or tick.bid <= 0:
            return False, " [RISK] Quote tidak valid (harga Ask/Bid 0). Menunggu..."

        spread_points = round((tick.ask - tick.bid) / symbol_info.point, 1)

        # FX: ATR-based cap (15% ATR H1, floor 20 pts).
        # XAU/BTC: flat cap dari config.
        max_spread = config.max_spread_points_for(config.SYMBOL, atr_h1_pts=self._atr_h1_pts)
        if spread_points > max_spread:
            return False, (f" [RISK] Spread terlalu tinggi: {spread_points} pts "
                           f"(Maks: {max_spread} pts). Menunggu...")
        return True, ""

    def _check_danger_zones(self, now_wib=None):
        """Check if current time falls in any predefined danger zones."""
        # Crypto (BTCUSD) trades 24/7 - no FX danger zones
        if config.is_crypto(config.SYMBOL):
            return True, ""

        now_wib = now_wib or datetime.now(WIB)
        current_minutes = now_wib.hour * 60 + now_wib.minute

        for zone in config.DANGER_ZONES_WIB:
            start = zone["start"][0] * 60 + zone["start"][1]
            end = zone["end"][0] * 60 + zone["end"][1]
            if start > end:
                in_zone = current_minutes >= start or current_minutes < end
            else:
                in_zone = start <= current_minutes < end
            if in_zone:
                return False, f" [RISK] Zona bahaya '{zone['name']}': {zone['reason']}"
        return True, ""

    def _check_weekend_entry(self):
        """
        Block new trade entries during the weekend (Friday >= 22:00 WIB through
        Monday 00:00 WIB) when WEEKEND_TRADING_ENABLED is False. This applies to
        ALL symbols - including crypto/BTC, which would otherwise trade 24/7.

        Existing open positions are NOT affected (still managed by the 5s loop);
        only new entries are blocked.
        """
        if config.WEEKEND_TRADING_ENABLED:
            return True, ""
        now_wib = datetime.now(WIB)
        if now_wib.weekday() == 4 and now_wib.hour >= 22:  # Friday night
            return False, " [RISK] Weekend entry blocked: Jumat >= 22:00 WIB. Menunggu Senin 00:00 WIB."
        if now_wib.weekday() in (5, 6):  # Saturday or Sunday
            return False, " [RISK] Weekend - trading dimatikan (WEEKEND_TRADING_ENABLED=False). Tidak membuka posisi baru."
        return True, ""

    def _check_session(self, now_wib=None):
        """Check if current time falls within allowed trading sessions. Sets lot multiplier."""
        # Crypto (BTCUSD) trades 24/7 - no FX session windows
        if config.is_crypto(config.SYMBOL):
            self._session_lot_multiplier = 1.0
            return True, ""

        if not config.SESSION_FILTER_ENABLED:
            self._session_lot_multiplier = 1.0
            return True, ""

        now_wib = now_wib or datetime.now(WIB)
        current_minutes = now_wib.hour * 60 + now_wib.minute

        # Pick the HIGHEST multiplier among all matching sessions so overlapping
        # windows (e.g. London 1.0x inside London-NY 1.2x) apply the best one.
        best_multiplier = None
        for session in config.ALLOWED_SESSIONS_WIB:
            start = session["start"][0] * 60 + session["start"][1]
            end = session["end"][0] * 60 + session["end"][1]

            # Handle overnight sessions (e.g., NY 20:00 - 05:00)
            if start > end:
                in_session = current_minutes >= start or current_minutes < end
            else:
                in_session = start <= current_minutes < end

            if in_session:
                mult = session.get("lot_multiplier", 1.0)
                if best_multiplier is None or mult > best_multiplier:
                    best_multiplier = mult

        if best_multiplier is not None:
            self._session_lot_multiplier = best_multiplier
            return True, ""

        self._session_lot_multiplier = 1.0
        return False, f" [RISK] Di luar sesi trading (WIB {now_wib.strftime('%H:%M')}). Menunggu..."

    # =========================================================================
    #  WEEKEND POSITION MANAGEMENT (from xaubot-ai position_manager.py)
    # =========================================================================
    def check_weekend_positions(self):
        """
        Check if we should close profitable positions before weekend.
        FX only - crypto (BTCUSD) trades through the weekend.
        Returns list of tickets to close with reasons.
        """
        if not config.WEEKEND_CLOSE_ENABLED:
            return []

        # Do NOT close crypto positions before weekend - BTC trades all weekend
        if config.is_crypto(config.SYMBOL):
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
                    "reason": f" Weekend close: mengambil profit ${profit:.2f} sebelum gap weekend "
                              f"({hours_to_close:.1f}h ke penutupan)"
                })
            elif profit < 0 and abs(profit) > config.WEEKEND_MAX_LOSS_TO_HOLD_USD:
                actions.append({
                    "ticket": pos.ticket,
                    "reason": f" Weekend close: cut loss ${profit:.2f} terlalu besar untuk "
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
            if getattr(config, "DAILY_LOSS_OPENED_TODAY_ONLY", True):
                closed_for_loss = [c for c in closed if c.get("opened_today", True)]
            else:
                closed_for_loss = closed
            return sum(c["profit"] for c in closed_for_loss)
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
