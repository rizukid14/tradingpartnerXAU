import os
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
from src.analytics import position_manager, trade_evaluator, dynamic_config, forecast_engine, decision_memory
from src.analytics.macro_analyst import MacroAnalyst



# Initialize risk engine
risk = RiskEngine()

# Initialize macro analyst
macro = MacroAnalyst()



class TeeLogger(object):
    """Redirects stdout and stderr to both the console and a log file with auto-size rotation."""
    def __init__(self, filepath, max_bytes=2000000):
        self.terminal = sys.stdout
        self.filepath = filepath
        # Rotate log if size exceeds max_bytes (keep last 5000 lines)
        if os.path.exists(filepath) and os.path.getsize(filepath) > max_bytes:
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                keep_lines = lines[-5000:]
                with open(filepath, "w", encoding="utf-8") as f:
                    f.writelines(keep_lines)
            except Exception:
                pass
        self.log = open(filepath, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        # Skip carriage return live clock lines from spamming log file
        if "\r" not in message:
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
    
    # 2.5 Post-Mortem Trade Evaluation & Daily WinRate Summary
    try:
        trade_evaluator.evaluator.check_and_evaluate_closed_trades()
        closed_deals = connector.get_closed_positions_today()
        dynamic_config.dynamic_rules.adapt_from_performance(closed_deals)

        # Display Daily WinRate Summary Log (aggregate + per-symbol breakdown)
        if closed_deals and len(closed_deals) > 0:
            total_t = len(closed_deals)
            wins_t = sum(1 for d in closed_deals if d.get("profit", 0) >= 0)
            loss_t = total_t - wins_t
            wr = (wins_t / total_t) * 100.0
            pnl_t = sum(d.get("profit", 0) for d in closed_deals)
            print(f"📊 [PERFORMA HARIAN] {total_t} Trade | {wins_t} Win - {loss_t} Loss (WinRate: {wr:.1f}%) | Net PnL: ${pnl_t:+.2f} USD")

            # Per-symbol breakdown so weekend BTC P/L does not mask weekday XAU performance
            by_symbol = {}
            for d in closed_deals:
                sym = d.get("symbol", "UNKNOWN")
                bucket = by_symbol.setdefault(sym, {"n": 0, "wins": 0, "pnl": 0.0})
                bucket["n"] += 1
                bucket["pnl"] += d.get("profit", 0)
                if d.get("profit", 0) >= 0:
                    bucket["wins"] += 1
            if len(by_symbol) > 1:
                parts = []
                for sym, b in sorted(by_symbol.items()):
                    sym_wr = (b["wins"] / b["n"]) * 100.0 if b["n"] else 0.0
                    parts.append(f"{sym}: {b['n']}T {b['wins']}W WR {sym_wr:.0f}% ${b['pnl']:+.2f}")
                print(f"📊 [PERFORMA PER SIMBOL] " + " | ".join(parts))
        else:
            print("📊 [PERFORMA HARIAN] Belum ada trade tertutup hari ini (0 Trade | WinRate: 0.0%).")
    except Exception as e:
        print(f"[EVALUATOR WARNING] {e}")


    # 3. Check for existing open positions
    open_positions = connector.get_open_positions(config.SYMBOL)


    # 4. Query AI models in parallel (including active open_positions for 5-min AI re-evaluation!)

    macro_context = macro.get_macro_context()
    if macro_context:
        print("📊 Menyertakan analisa Multi-Timeframe & Fundamental untuk LLM...")

    # Pre-warm forecast: ensure cache is fresh for the active symbol before LLM call.
    # Non-blocking — if cache is stale, a background thread refreshes it; the prompt
    # will receive the (possibly stale) cache now and the next cycle gets the new one.
    try:
        forecast_engine.forecaster.get_active_forecast(config.SYMBOL, df, tick, macro_context)
    except Exception as e:
        print(f"[FORECAST WARNING] {e}")

    print("🧠 Mengirim data ke OpenAI, Gemini, dan DeepSeek...")
    decisions = llm.get_multi_llm_decisions(config.SYMBOL, df, tick, macro_context, open_positions)
    
    # 5. Calculate consensus
    result = consensus.calculate_consensus(decisions)

    # 5.1 Execute AI Position Re-Evaluator Close Actions
    tickets_to_close = result.get("tickets_to_close", [])
    for close_req in tickets_to_close:
        t_ticket = close_req["ticket"]
        t_reason = close_req["reason"]
        t_models = close_req.get("models", "AI Consensus")
        print(f"⚡ [AI RE-EVALUATOR] {t_models} sepakat CLOSE order #{t_ticket}: {t_reason}")
        # Capture pre-close profit so daily P/L + loss streak stay accurate
        pre_profit = 0.0
        try:
            pos_pre = mt5.positions_get(ticket=t_ticket)
            if pos_pre and len(pos_pre) > 0:
                pre_profit = pos_pre[0].profit + pos_pre[0].swap + pos_pre[0].commission
        except Exception:
            pass
        close_res = connector.close_position(t_ticket)
        if close_res:
            print(f"✅ Sukses menutup posisi #{t_ticket} berdasarkan rekomendasi AI Re-Evaluator!")
            risk.record_position_closed(t_ticket, pre_profit)

    # 5.5 Multi-Horizon Forecast Context (Informational Only)
    try:
        is_valid, f_reason, _, _ = forecast_engine.forecaster.validate_forecast_trigger(
            config.SYMBOL, tick, result, df
        )
        print(f"🔮 [FORECAST INFO] {f_reason}")
    except Exception as e:
        print(f"[FORECAST INFO WARNING] {e}")

    # Check if max open positions reached for NEW trades (recovery mode: tighter cap)
    max_positions = config.MAX_OPEN_POSITIONS_RECOVERY if risk.is_recovery_mode else config.MAX_OPEN_POSITIONS
    if len(open_positions) >= max_positions:
        print(f"ℹ️ Posisi terbuka terdeteksi untuk {config.SYMBOL}:")
        for pos in open_positions:
            print(f"   - Ticket #{pos['ticket']}: {pos['type']} {pos['volume']} lot | Profit: {pos['profit']} USD")
        print(f"➡️ Melewatkan pembukaan posisi baru karena sudah mencapai batas maks ({max_positions}).")
        return True




    # 6. Execute trade if consensus signal is BUY or SELL
    trade_signal = result["signal"]
    if trade_signal in ["BUY", "SELL"]:
        sl_points = result["sl_points"]
        tp_points = result["tp_points"]
        agreeing_count = result.get("agreeing_count", 0)
        
        # Get effective lot size (recovery mode + session multiplier)
        effective_lot = risk.get_effective_lot_size()
        
        # Check remaining capacity slots before max positions (recovery mode: tighter cap)
        remaining_slots = max(0, max_positions - len(open_positions))
        desired_positions = 2 if agreeing_count >= 3 else 1
        num_positions = min(desired_positions, remaining_slots)

        if num_positions > 1:
            print(f"🔥 [UNANIMOUS 3/3 HIGH CONFIDENCE] Ketiga AI sepakat {trade_signal}! Membuka {num_positions} posisi sekaligus (Sisa slot: {remaining_slots})...")
        elif num_positions == 1 and desired_positions > 1:
            print(f"🔥 [UNANIMOUS 3/3 HIGH CONFIDENCE] Ketiga AI sepakat {trade_signal}! Membuka 1 posisi (Dibatasi sisa slot max: {remaining_slots})...")


        for i in range(num_positions):
            # Posisi 2 gets 1.2x TP for capturing extended trend
            pos_tp = int(tp_points * 1.2) if i == 1 else tp_points
            
            order_res = connector.send_trade_order(
                symbol=config.SYMBOL,
                action=trade_signal,
                lot=effective_lot,
                sl_points=sl_points,
                tp_points=pos_tp
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

    # Record this cycle's final decision for Recent Decision Memory
    # (so the LLM next cycle can see if it has been HOLDing too long).
    try:
        decision_memory.memory.record(
            config.SYMBOL,
            signal=result.get("signal", "HOLD"),
            confidence=result.get("confidence", 0.0),
            reasoning=result.get("details", ""),
        )
    except Exception as e:
        print(f"[DECISION MEMORY WARNING] {e}")

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

    # Set active symbol now so the banner shows the symbol that will be traded
    config.refresh_active_symbol()

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

    # Initialize MT5 (validate the symbol that is active right now)
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
    last_symbol = config.SYMBOL

    try:
        while True:
            # =================================================================
            #  EVERY TICK (5s): Manage open positions + weekend check
            # =================================================================
            try:
                # Symbol rotation: XAUUSD weekdays, BTCUSD weekends
                active_symbol, changed = config.refresh_active_symbol()
                if changed:
                    print(f"🔄 [SYMBOL SWITCH] {last_symbol} -> {active_symbol}")
                    tg.alert_symbol_switch(last_symbol, active_symbol)
                    last_symbol = active_symbol

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
                        candle_wib = connector.server_to_wib(int(current_candle_time))
                        print(f"\n🆕 Candle baru terdeteksi! Waktu: {candle_wib.strftime('%Y-%m-%d %H:%M:%S')} WIB")
                    
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
            sys.stdout.write(f"\r🕒 [{config.SYMBOL} | {now_str}] ⏳ Waiting for next tick / M5 candle...")
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
