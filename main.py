import time
import sys
# Force UTF-8 encoding for standard output on Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    import MetaTrader5 as mt5
else:
    try:
        from mt5linux import MetaTrader5 as mt5
    except ImportError:
        import MetaTrader5 as mt5
import config
from src.core import mt5_connector as connector, llm_client as llm, consensus, telegram_alerts as tg
from src.core.risk_engine import RiskEngine
from src.analytics import position_manager, trade_evaluator, dynamic_config, forecast_engine
from src.analytics.macro_analyst import MacroAnalyst



# Initialize risk engine
risk = RiskEngine()

# Initialize macro analyst
macro = MacroAnalyst()



class TeeLogger(object):
    """Redirects stdout and stderr to both the console and a log file."""
    def __init__(self, filepath):
        self.terminal = sys.stdout
        self.log = open(filepath, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()


_notified_closed_tickets = set()
_closed_tickets_initialized = False

def check_and_notify_closed_trades():
    """Checks for newly closed trades today, prints to CLI, and sends Telegram alert."""
    global _closed_tickets_initialized
    try:
        closed = connector.get_closed_positions_today()
        if not closed:
            _closed_tickets_initialized = True
            return

        # On startup: register existing closed deals silently so we don't re-alert old trades
        if not _closed_tickets_initialized:
            for deal in closed:
                t_id = deal.get("ticket")
                if t_id:
                    _notified_closed_tickets.add(t_id)
            _closed_tickets_initialized = True
            return

        # Real-time check for new closed trades
        for deal in closed:
            t_id = deal.get("ticket")
            if t_id and t_id not in _notified_closed_tickets:
                _notified_closed_tickets.add(t_id)
                profit_usd = deal.get("profit", 0.0)
                pos_type = deal.get("type", "TRADE")
                vol = deal.get("volume", 0.01)
                comment = deal.get("comment", "")

                is_win = profit_usd >= 0
                icon = "🎯 [CLOSED WIN - TAKE PROFIT]" if is_win else "🛑 [CLOSED LOSS - STOP LOSS]"
                pnl_str = f"+${profit_usd:.2f}" if is_win else f"-${abs(profit_usd):.2f}"

                # CLI Print
                print(f"{icon} Ticket #{t_id} ({pos_type} {vol} lot) | P/L: {pnl_str} USD | Info: {comment}")

                # Telegram Alert
                tg.alert_trade_closed(
                    pos_type=pos_type,
                    ticket=t_id,
                    profit_usd=profit_usd,
                    comment=comment
                )
    except Exception as e:
        print(f"[CLOSED TRADE TRACKER ERROR] {e}")


_last_hourly_recap_time = time.time()

def check_and_send_hourly_recap():
    """Sends an hourly summary recap to Telegram every 1 hour (3600s)."""
    global _last_hourly_recap_time
    now = time.time()
    if now - _last_hourly_recap_time >= 3600:
        _last_hourly_recap_time = now
        try:
            from datetime import datetime
            pnl = risk.get_daily_pnl()
            closed_today = connector.get_closed_positions_today()
            total_trades = len(closed_today)
            wins = sum(1 for c in closed_today if c.get("profit", 0) >= 0)
            losses = sum(1 for c in closed_today if c.get("profit", 0) < 0)
            win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0

            pnl_sign = "+$" if pnl >= 0 else "-$"
            text = (
                f"📊 *[REKAP PER 1 JAM - M1 SUPER SCALPER]*\n"
                f"• P/L Hari Ini: *{pnl_sign}{abs(pnl):.2f} USD*\n"
                f"• Total Trade Selesai: `{total_trades}` (Win: `{wins}`, Loss: `{losses}`)\n"
                f"• Win Rate: `{win_rate:.1f}%`\n"
                f"• Waktu: `{datetime.now().strftime('%H:%M:%S WIB')}`"
            )
            tg.send_message(text)
            print(f"📊 [HOURLY RECAP SENT] P/L: ${pnl:.2f} | Trades: {total_trades} | Win Rate: {win_rate:.1f}%")
        except Exception as e:
            print(f"[HOURLY RECAP ERROR] {e}")


def run_trading_cycle():
    """Performs one full cycle of fetching data, querying LLMs, and checking consensus."""
    # Always check for closed trades & hourly recap at cycle start
    check_and_notify_closed_trades()
    check_and_send_hourly_recap()

    print(f"\n⚡ [CYCLE START] Memulai analisa market pada {time.strftime('%Y-%m-%d %H:%M:%S')}...")
    
    # 0. Risk gate — check all conditions before trading
    can_trade, reason = risk.can_trade()
    if not can_trade:
        print(reason)
        return True  # Not an error, just skipping
    
    # 1. Fetch market data (50 candles of M5 + 20 candles of M1)
    df = connector.get_market_data(config.SYMBOL, config.TIMEFRAME, num_candles=50)
    if df is None or len(df) == 0:
        print("❌ Gagal mendapatkan market data. Melewatkan siklus ini.")
        return False

    df_m1 = connector.get_market_data(config.SYMBOL, mt5.TIMEFRAME_M1, num_candles=20)
        
    # 2. Fetch current tick (Bid/Ask)
    tick = connector.get_current_tick(config.SYMBOL)
    if tick is None:
        print("❌ Gagal mendapatkan tick data terbaru. Melewatkan siklus ini.")
        return False
        
    print(f"📈 Harga saat ini {config.SYMBOL} - Bid: {tick['bid']}, Ask: {tick['ask']}, Spread: {tick['spread']} pts")
    
    # 2.5 Post-Mortem Trade Evaluation & Dynamic Config Adaptation (Disabled for Fresh Scalping)


    # 3. Check for existing open positions
    open_positions = connector.get_open_positions(config.SYMBOL)
    if len(open_positions) >= config.MAX_OPEN_POSITIONS:
        print(f"ℹ️ Posisi terbuka terdeteksi untuk {config.SYMBOL}:")
        for pos in open_positions:
            print(f"   - Ticket #{pos['ticket']}: {pos['type']} {pos['volume']} lot | Profit: {pos['profit']} USD")
        print(f"➡️ Melewatkan pembukaan posisi baru karena sudah mencapai batas maks ({config.MAX_OPEN_POSITIONS}).")
        return True

    # 4. Query AI models in parallel
    macro_context = macro.get_macro_context()
    if macro_context:
        print("📊 Menyertakan analisa Multi-Timeframe & Fundamental untuk LLM...")
    print("🧠 Mengirim data ke OpenAI, Gemini, dan DeepSeek...")
    decisions = llm.get_multi_llm_decisions(config.SYMBOL, df, tick, macro_context, df_m1=df_m1)
    
    # 5. Calculate consensus
    result = consensus.calculate_consensus(decisions)

    # 5.5 Multi-Horizon Forecast Context (Disabled if FORECAST_ENABLED is False)
    if getattr(config, "FORECAST_ENABLED", False):
        try:
            is_valid, f_reason, _, _ = forecast_engine.forecaster.validate_forecast_trigger(
                config.SYMBOL, tick, result, df
            )
            print(f"🔮 [FORECAST INFO] {f_reason}")
        except Exception as e:
            print(f"[FORECAST INFO WARNING] {e}")



    # 6. Execute trade if consensus signal is BUY or SELL
    trade_signal = result["signal"]
    if trade_signal in ["BUY", "SELL"]:
        sl_points = result["sl_points"]
        tp_points = result["tp_points"]
        agreeing_count = result.get("agreeing_count", 0)
        
        # Get effective lot size (1.5% equity risk sizing + recovery mode + session multiplier)
        effective_lot = risk.get_effective_lot_size(sl_points=sl_points)
        
        # Check remaining capacity slots before MAX_OPEN_POSITIONS
        remaining_slots = max(0, config.MAX_OPEN_POSITIONS - len(open_positions))
        desired_positions = 2 if agreeing_count >= 3 else 1
        num_positions = min(desired_positions, remaining_slots)

        if num_positions > 1:
            print(f"🔥 [UNANIMOUS 3/3 HIGH CONFIDENCE] Ketiga AI sepakat {trade_signal}! Membuka {num_positions} posisi sekaligus (Sisa slot: {remaining_slots})...")
        elif num_positions == 1 and desired_positions > 1:
            print(f"🔥 [UNANIMOUS 3/3 HIGH CONFIDENCE] Ketiga AI sepakat {trade_signal}! Membuka 1 posisi (Dibatasi sisa slot max: {remaining_slots})...")


        for i in range(num_positions):
            # Posisi 2 gets 1.2x TP for capturing extended trend
            pos_tp = int(tp_points * 1.2) if i == 1 else tp_points
            open_reason = (result.get("reason") or "Multi-LLM Bot").strip()[:25]
            
            order_res = connector.send_trade_order(
                symbol=config.SYMBOL,
                action=trade_signal,
                lot=effective_lot,
                sl_points=sl_points,
                tp_points=pos_tp,
                comment=open_reason
            )
            if order_res["status"] == "SUCCESS":
                print(f"🎉 Sukses menempatkan order #{i+1}: {trade_signal} (Ticket: {order_res['ticket']}, Lot: {effective_lot})")
                risk.record_trade_opened()
                tg.alert_trade_opened(
                    trade_signal, effective_lot, sl_points, pos_tp,
                    recovery_mode=risk.is_recovery_mode,
                    session_multiplier=risk.session_lot_multiplier
                )
            else:
                print(f"❌ Gagal menempatkan order #{i+1}: {order_res['comment']}")
    else:
        print("☕ Tidak ada keputusan BUY/SELL yang disetujui. Menunggu candle berikutnya.")

    tg.flush_failed_orders_recap()
    return True


def main():
    # Setup TeeLogger to save all terminal logs
    if getattr(config, "LOG_FILE", None):
        tee_logger = TeeLogger(config.LOG_FILE)
        sys.stdout = tee_logger
        sys.stderr = tee_logger
        print(f"📝 Logging aktif. Semua output akan disimpan di: {config.LOG_FILE}")

    from src.core.cli_theme import UI, render_banner
    print(render_banner(
        account_info=getattr(config, "MT5_LOGIN", None),
        symbol=config.SYMBOL,
        tf="M5",
        mode="xau",
        is_live=not config.DRY_RUN
    ))

    # Validate API keys before connecting to MT5
    missing_keys = []
    if not config.OPENAI_API_KEY: missing_keys.append("OPENAI_API_KEY")
    if not config.GEMINI_API_KEY: missing_keys.append("GEMINI_API_KEY")
    if not config.DEEPSEEK_API_KEY: missing_keys.append("DEEPSEEK_API_KEY")
    
    if missing_keys:
        print(f"❌ ERROR: Kunci API berikut tidak ditemukan di file .env: {', '.join(missing_keys)}")
        print("Silakan salin .env.example menjadi .env dan masukkan API Key Anda.")
        sys.exit(1)

    # Initialize MT5
    if not connector.initialize_mt5():
        print("❌ Gagal terhubung ke MetaTrader 5 terminal. Pastikan MT5 Anda aktif.")
        sys.exit(1)
        
    print("\n✅ Terhubung ke MT5 dengan sukses!")
    print("🤖 Bot berjalan... Menunggu penutupan candle berikutnya.\n")
    
    # Send startup alert
    tg.alert_bot_started()
    
    # Run initial macro and MTF analysis (forced on startup to ensure we have data immediately)
    if config.MTF_ANALYSIS_ENABLED or config.FUNDAMENTAL_ANALYSIS_ENABLED:
        print("\n📊 [STARTUP] Menjalankan analisa Multi-Timeframe & Fundamental awal...")
        try:
            macro.check_and_update_analysis(force=True)
            print("✅ Analisa Multi-Timeframe & Fundamental awal selesai.\n")
        except Exception as e:
            print(f"❌ [STARTUP ERROR] Gagal menjalankan analisa awal: {e}\n")
            
    last_candle_time = None
    startup_run = True

    try:
        while True:
            # =================================================================
            #  EVERY TICK (5s): Manage open positions + weekend check
            # =================================================================
            try:
                # Trailing stop + break-even + partial close
                position_manager.manage_all_positions()
                
                # Real-time closed trade detection (Every 5 seconds!)
                check_and_notify_closed_trades()
                
                # Weekend position management
                weekend_actions = risk.check_weekend_positions()
                for action in weekend_actions:
                    ticket = action["ticket"]
                    reason = action["reason"]
                    print(f"📅 {reason}")
                    
                    # Get position profit before closing
                    positions = mt5.positions_get(ticket=ticket)
                    profit = 0.0
                    if positions and len(positions) > 0:
                        profit = positions[0].profit
                    
                    success = connector.close_position(ticket)
                    if success:
                        print(f"✅ Posisi #{ticket} ditutup untuk weekend.")
                        risk.record_position_closed(ticket, profit)
                        tg.alert_weekend_close(ticket, profit, reason)

            except Exception as e:
                print(f"[POS MANAGER ERROR] {e}")
            
            # =================================================================
            #  ON NEW CANDLE: Run full trading cycle
            # Check and update multi-timeframe and macro analysis
            if config.MTF_ANALYSIS_ENABLED or config.FUNDAMENTAL_ANALYSIS_ENABLED:
                try:
                    macro.check_and_update_analysis()
                except Exception as e:
                    print(f"[MACRO UPDATE ERROR] {e}")

            rates = mt5.copy_rates_from_pos(config.SYMBOL, config.TIMEFRAME, 0, 2)
            if rates is not None and len(rates) > 0:
                current_candle_time = rates[-1]['time']
                
                if startup_run or (last_candle_time is not None and current_candle_time > last_candle_time):
                    if startup_run:
                        print("▶️ Menjalankan siklus analisa pertama saat startup...")
                        startup_run = False
                    else:
                        print(f"\n🆕 Candle baru terdeteksi! Waktu: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_candle_time))}")
                    
                    last_candle_time = current_candle_time
                    
                    # Show daily P/L and risk status
                    daily_pnl = risk.get_daily_pnl()
                    status = risk.get_status_summary()
                    print(f"💰 P/L Hari Ini: ${daily_pnl:.2f} | "
                          f"Loss Streak: {status['consecutive_losses']} | "
                          f"Recovery: {'🔄 Ya' if status['recovery_mode'] else 'Tidak'} | "
                          f"Session Lot: x{status['session_lot_multiplier']}")
                    
                    # Run trading cycle
                    run_trading_cycle()
            else:
                print("⚠️ Gagal mengecek status candle di MT5. Mencoba kembali...")
            
            # Show live status clock line in CLI every loop iteration
            now_str = time.strftime('%H:%M:%S')
            sys.stdout.write(f"\r🕒 [LIVE CLOCK: {now_str}] ⏳ Waiting for next tick / M5 candle...")
            sys.stdout.flush()

            # Sleep 5 seconds between checks
            time.sleep(5)

            
    except KeyboardInterrupt:
        print("\n👋 Bot dimatikan secara manual oleh user.")
    finally:
        # Send daily summary before shutdown
        daily_pnl = risk.get_daily_pnl()
        tg.alert_daily_summary(daily_pnl, 0, risk.get_status_summary())
        mt5.shutdown()
        print("🔌 Koneksi MT5 diputus. Sampai jumpa!")


if __name__ == "__main__":
    main()
