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
import mt5_connector as connector
import llm_client as llm
import consensus
from risk_engine import RiskEngine
import position_manager
import telegram_alerts as tg

# Initialize risk engine
risk = RiskEngine()

# Initialize macro analyst
from macro_analyst import MacroAnalyst
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


def run_trading_cycle():
    """Performs one full cycle of fetching data, querying LLMs, and checking consensus."""
    print(f"\n⚡ [CYCLE START] Memulai analisa market pada {time.strftime('%Y-%m-%d %H:%M:%S')}...")
    
    # 0. Risk gate — check all conditions before trading
    can_trade, reason = risk.can_trade()
    if not can_trade:
        print(reason)
        return True  # Not an error, just skipping
    
    # 1. Fetch market data (50 candles of M5)
    df = connector.get_market_data(config.SYMBOL, config.TIMEFRAME, num_candles=50)
    if df is None or len(df) == 0:
        print("❌ Gagal mendapatkan market data. Melewatkan siklus ini.")
        return False
        
    # 2. Fetch current tick (Bid/Ask)
    tick = connector.get_current_tick(config.SYMBOL)
    if tick is None:
        print("❌ Gagal mendapatkan tick data terbaru. Melewatkan siklus ini.")
        return False
        
    print(f"📈 Harga saat ini {config.SYMBOL} - Bid: {tick['bid']}, Ask: {tick['ask']}, Spread: {tick['spread']} pts")
    
    # 2.5 Post-Mortem Trade Evaluation & Dynamic Config Adaptation
    try:
        import trade_evaluator
        import dynamic_config
        trade_evaluator.evaluator.check_and_evaluate_closed_trades()
        closed_deals = connector.get_closed_positions_today()
        dynamic_config.dynamic_rules.adapt_from_performance(closed_deals)
    except Exception as e:
        print(f"[EVALUATOR WARNING] {e}")

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
    decisions = llm.get_multi_llm_decisions(config.SYMBOL, df, tick, macro_context)
    
    # 5. Calculate consensus
    result = consensus.calculate_consensus(decisions)

    # 5.5 Validate Forecast Trigger Conditions ("Jika X dan Y sesuai prediksi maka execute")
    if result["signal"] in ["BUY", "SELL"]:
        try:
            import forecast_engine
            is_valid, f_reason, f_sl_pts, f_tp_pts = forecast_engine.forecaster.validate_forecast_trigger(
                config.SYMBOL, tick, result, df
            )
            if not is_valid:
                print(f"⚠️ [FORECAST BLOCK] Order {result['signal']} dibatalkan: {f_reason}")
                return True
            else:
                print(f"🔮 [FORECAST CONFIRMED] {f_reason}")
                if f_sl_pts > 0 and f_tp_pts > 0:
                    result["sl_points"] = f_sl_pts
                    result["tp_points"] = f_tp_pts
        except Exception as e:
            print(f"[FORECAST GUARD WARNING] {e}")

    # 6. Execute trade if consensus signal is BUY or SELL
    trade_signal = result["signal"]
    if trade_signal in ["BUY", "SELL"]:
        sl_points = result["sl_points"]
        tp_points = result["tp_points"]
        
        # Get effective lot size (recovery mode + session multiplier)
        effective_lot = risk.get_effective_lot_size()
        
        # Execute order
        order_res = connector.send_trade_order(
            symbol=config.SYMBOL,
            action=trade_signal,
            lot=effective_lot,
            sl_points=sl_points,
            tp_points=tp_points
        )
        if order_res["status"] == "SUCCESS":
            print(f"🎉 Sukses menempatkan order: {trade_signal} (Ticket: {order_res['ticket']}, Lot: {effective_lot})")
            risk.record_trade_opened()
            tg.alert_trade_opened(
                trade_signal, effective_lot, sl_points, tp_points,
                recovery_mode=risk.is_recovery_mode,
                session_multiplier=risk.session_lot_multiplier
            )
        else:
            print(f"❌ Gagal menempatkan order: {order_res['comment']}")
    else:
        print("☕ Tidak ada keputusan BUY/SELL yang disetujui. Menunggu candle berikutnya.")
        
    return True


def main():
    # Setup TeeLogger to save all terminal logs
    if getattr(config, "LOG_FILE", None):
        tee_logger = TeeLogger(config.LOG_FILE)
        sys.stdout = tee_logger
        sys.stderr = tee_logger
        print(f"📝 Logging aktif. Semua output akan disimpan di: {config.LOG_FILE}")

    print("=" * 60)
    print("    BOT TRADING MULTI-LLM CONSENSUS - PROTECTED EXECUTION    ")
    print("=" * 60)
    print(f"Mode: {'⚠️ DRY RUN (Hanya Sinyal)' if config.DRY_RUN else '🔥 LIVE EXECUTION (Duit Asli/Demo)'}")
    print(f"Simbol: {config.SYMBOL} | Timeframe: M5 (5 Menit) | Lot Size: {config.LOT_SIZE}")
    print(f"Models: OpenAI ({config.OPENAI_MODEL}), Gemini ({config.GEMINI_MODEL}), DeepSeek ({config.DEEPSEEK_MODEL})")
    print("-" * 60)
    print("🛡️ PROTEKSI AKTIF:")
    print(f"   Trailing Stop:   {'ON' if config.TRAILING_STOP_ENABLED else 'OFF'} "
          f"(aktivasi {config.TRAILING_ACTIVATION_POINTS} pts, jarak {config.TRAILING_DISTANCE_POINTS} pts)")
    print(f"   Break-Even:      {'ON' if config.BREAK_EVEN_ENABLED else 'OFF'} "
          f"(trigger {config.BREAK_EVEN_TRIGGER_POINTS} pts)")
    print(f"   Partial Close:   {'ON' if config.PARTIAL_CLOSE_ENABLED else 'OFF'} "
          f"({config.PARTIAL_CLOSE_PERCENT}% @ {config.PARTIAL_CLOSE_TP1_POINTS} pts)")
    print(f"   Max Daily Loss:  ${config.MAX_DAILY_LOSS_USD}")
    print(f"   Recovery Mode:   {'ON' if config.RECOVERY_MODE_ENABLED else 'OFF'} "
          f"(x{config.RECOVERY_LOT_MULTIPLIER} setelah {config.MAX_CONSECUTIVE_LOSSES} loss)")
    print(f"   Cooldown:        {config.TRADE_COOLDOWN_SECONDS}s antar trade")
    print(f"   Spread Filter:   {config.MAX_SPREAD_POINTS} pts maks")
    print(f"   Session Filter:  {'ON' if config.SESSION_FILTER_ENABLED else 'OFF'} (WIB)")
    print(f"   Weekend Close:   {'ON' if config.WEEKEND_CLOSE_ENABLED else 'OFF'}")
    print(f"   Telegram:        {'ON' if config.TELEGRAM_ENABLED else 'OFF'}")
    print("=" * 60)

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
