"""
Main loop Bot Binance Spot — 2 proposer + 1 approver.

Loop 5 detik: manage posisi + deteksi close + cek daily loss.
Full cycle tiap candle M30: risk gate → 2 proposer (GPT+Gemini) →
Claude approver (kalau 2/2) → OCO order (entry market + SL + TP).

AMAN default: TESTNET=True + DRY_RUN=True (tidak kirim order).
"""
import logging
import sys
import time
from datetime import datetime

import config
from src.core import ccxt_connector as connector, llm_client, consensus
from src.core.risk_engine import RiskEngine
from src.analytics import position_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
# Sembunyikan log HTTP request dari SDK (openai, google-genai, dll) — biar bersih.
# Error tetap muncul (level WARNING ke atas).
for noisy in ("openai", "google.genai", "httpx", "urllib3", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
log = logging.getLogger("binance_bot")


def run_trading_cycle(risk):
    """Full cycle: risk gate → proposer → approver → eksekusi."""
    log.info(f"⚡ [CYCLE START] {config.SYMBOL} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Risk gate
    can, reason = risk.can_trade()
    if not can:
        log.info(reason)
        return
    log.info(reason)

    # 2. Data: kline + ticker + balance
    df = connector.get_klines(config.SYMBOL, config.TIMEFRAME, config.CANDLE_COUNT)
    if df is None or len(df) < 30:
        log.warning("[CYCLE] Data candle kurang — skip.")
        return
    ticker = connector.get_ticker(config.SYMBOL)
    if not ticker:
        log.warning("[CYCLE] Gagal dapat ticker — skip.")
        return
    balance = connector.get_account_balance_usdt()
    if balance <= 0:
        # Gagal fetch balance → jangan lanjut (equity $0 bikin proposer/approver
        # salah menilai "impossible"). Skip cycle, coba lagi candle berikutnya.
        log.warning("[CYCLE] Balance gagal didapat (0) — skip cycle.")
        return
    log.info(f"📈 {config.SYMBOL} price={ticker['price']} spread={ticker['spread_pct']:.3f}% equity=${balance:.2f}")

    # 3. Posisi open (spot: aset yang dimiliki)
    positions = risk.get_open_positions()
    open_pos = positions[0] if positions else None

    # 4. 2 proposer paralel (GPT + Gemini)
    log.info("🧠 2 proposer (GPT + Gemini)...")
    proposals = llm_client.get_proposals(config.SYMBOL, df, ticker, balance, open_pos)
    for name, p in proposals.items():
        log.info(f"🤖 [{name}] {p['signal']} (conf {p['confidence']:.0%}) "
                 f"SL {p.get('sl_pct')}% TP {p.get('tp_pct')}% | {p.get('reasoning','')[:200]}")

    # 5. Consensus 2/2 + Claude approver
    #    hold_streak: kalau sudah N cycle HOLD, 1 BUY kuat cukup → approver
    #    df & open_pos diteruskan supaya Claude bisa analisis independen
    decision, approval = consensus.run_consensus_with_approver(
        proposals, config.SYMBOL, df, ticker, balance, risk.hold_streak, open_pos)
    log.info(f"🚦 [CONSENSUS] {decision['signal']} (skor {decision['score']} >= {decision['threshold']}) — {decision['reasoning']}")

    if not decision["approved"] or decision["signal"] != "BUY":
        # Spot: SELL tanpa posisi = hold. Ada posisi & signal SELL = exit (fase 2).
        log.info("☕ HOLD — tidak ada trade.")
        risk.record_hold_cycle()
        return
    # Ada sinyal BUY valid → reset hold-streak (tidak peduli dieksekusi atau tidak)
    risk.reset_hold_streak()
    if open_pos:
        log.info(f"📊 Sudah ada posisi {open_pos['qty']} {open_pos['asset']} — max 1 posisi BUY.")
        return

    # 6. Sizing (qty dari risk%)
    sl_pct = decision.get("sl_pct") or config.DEFAULT_SL_PCT
    tp_pct = decision.get("tp_pct") or config.DEFAULT_TP_PCT
    qty, size_msg = risk.get_effective_qty(ticker["price"], sl_pct)
    if qty is None:
        log.warning(f"⚠️ [SIZING] {size_msg}")
        return
    log.info(f"📐 [SIZING] {size_msg}")

    # 7. Eksekusi: market BUY + OCO (SL stop-limit + TP limit)
    log.info(f"🔥 [EXECUTE] BUY {qty} {config.SYMBOL} @ market")
    buy_res = connector.place_market_order(config.SYMBOL, "BUY", qty)
    if not buy_res or buy_res.get("status") == "ERROR":
        log.error(f"❌ [ORDER] Gagal BUY: {buy_res}")
        return

    # Hitung harga SL/TP dari entry
    entry = float(buy_res.get("fills", [{}])[0].get("price", ticker["price"])) if not buy_res.get("dry_run") else ticker["price"]
    sl_price = entry * (1 - sl_pct / 100.0)
    tp_price = entry * (1 + tp_pct / 100.0)

    if config.DRY_RUN:
        log.info(f"🎯 [DRY RUN] SL @ {sl_price:.2f} ({sl_pct}%), TP @ {tp_price:.2f} ({tp_pct}%)")
        risk.record_position_opened(config.SYMBOL, qty, entry, sl_price, tp_price)
        risk.record_trade_opened()
        return

    # OCO: SELL leg (jual posisi) dengan SL stop-limit + TP limit
    log.info(f"🎯 [OCO] SELL {qty} {config.SYMBOL} | SL@{sl_price:.2f} (stop {sl_price:.2f}) TP@{tp_price:.2f}")
    oco_res = connector.place_oco_order(
        config.SYMBOL, "SELL", qty,
        stop_price=sl_price, sl_price=sl_price, tp_price=tp_price,
    )
    if not oco_res or "code" in oco_res:
        log.error(f"❌ [OCO] Gagal pasang SL/TP: {oco_res}")
        # Proteksi hilang — cancel posisi (jual) supaya tidak telantar
        connector.place_market_order(config.SYMBOL, "SELL", qty)
        risk.close_position(config.SYMBOL, qty)
        log.warning("⚠️ OCO gagal — posisi ditutup (jual) demi keamanan.")
        return

    risk.record_position_opened(config.SYMBOL, qty, entry, sl_price, tp_price)
    risk.record_trade_opened()
    log.info(f"✅ [DONE] BUY {qty} @ {entry:.2f} + OCO SL/TP terpasang.")


def main():
    log.info("=" * 50)
    log.info("  BOT BINANCE SPOT — 2 PROPOSER + 1 APPROVER")
    log.info("=" * 50)
    log.info(f"Mode: {'🟢 TESTNET' if config.TESTNET else '🔴 LIVE'} | "
             f"{'DRY-RUN (sinyal saja)' if config.DRY_RUN else 'EKSEKUSI'}")
    log.info(f"Symbol: {config.SYMBOL} | Timeframe: {config.TIMEFRAME} | "
             f"Risk: {config.RISK_PERCENT}%/trade | Daily loss: ${config.MAX_DAILY_LOSS_USD}")

    if not config.BINANCE_API_KEY or not config.BINANCE_SECRET:
        log.error("❌ BINANCE_API_KEY / BINANCE_SECRET kosong. Isi .env dulu.")
        sys.exit(1)

    # Cek koneksi
    st = connector.server_time()
    if st is None:
        log.error("❌ Gagal konek ke Binance API. Cek network / API key.")
        sys.exit(1)
    log.info(f"✅ Terhubung ke Binance (server time {datetime.fromtimestamp(st/1000)})")

    risk = RiskEngine()

    # Info symbol (step size, min notional)
    info = connector.get_symbol_info(config.SYMBOL)
    if info:
        log.info(f"ℹ️ {config.SYMBOL}: status={info.get('status')} filters={info.get('filters')}")

    last_candle_time = None
    startup_run = True
    last_status_log = 0.0

    try:
        while True:
            # ---- Tiap 5 detik: manage posisi + deteksi close ----
            try:
                position_manager.manage_all_positions(risk)
                # Status ringkas via log tiap 60 detik (bukan \r — biar rapi)
                if time.time() - last_status_log >= 60:
                    daily_pnl = risk.get_daily_pnl()
                    balance = connector.get_account_balance_usdt()
                    qty = connector.get_asset_balance(config.SYMBOL)
                    # Countdown ke candle berikutnya
                    tf_sec = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}.get(
                        config.TIMEFRAME, 300)
                    now = time.time()
                    next_candle = (int(now // tf_sec) + 1) * tf_sec
                    remain = int(next_candle - now)
                    cd = f"{remain // 60}m {remain % 60:02d}s"
                    log.info(f"🕒 Status: equity=${balance:.2f} | {config.SYMBOL} qty={qty} | "
                             f"P/L hari ini ${daily_pnl:+.2f} | loss streak {risk._consecutive_losses} | "
                             f"candle {config.TIMEFRAME} berikutnya dalam {cd}")
                    last_status_log = time.time()
            except Exception as e:
                log.error(f"[LOOP ERROR] {e}")

            # ---- Tiap candle baru (sesuai TIMEFRAME): full cycle ----
            df = connector.get_klines(config.SYMBOL, config.TIMEFRAME, 2)
            if df is not None and len(df) > 0:
                current_candle = df.iloc[-1]["time"]
                current_ts = current_candle.timestamp() if hasattr(current_candle, "timestamp") else 0
                if startup_run or (last_candle_time is not None and current_ts > last_candle_time):
                    if startup_run:
                        log.info("▶️ Cycle pertama saat startup...")
                        startup_run = False
                    else:
                        log.info(f"🆕 Candle {config.TIMEFRAME} baru: {current_candle}")
                    last_candle_time = current_ts
                    run_trading_cycle(risk)
                    # Countdown langsung setelah cycle — candle berikutnya dalam Xm Ys
                    tf_sec = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}.get(
                        config.TIMEFRAME, 300)
                    remain = int(((int(time.time() // tf_sec) + 1) * tf_sec) - time.time())
                    log.info(f"⏳ Candle {config.TIMEFRAME} berikutnya dalam {remain // 60}m {remain % 60:02d}s")
            else:
                log.warning("⚠️ Gagal cek candle.")

            time.sleep(5)
    except KeyboardInterrupt:
        log.info("\n👋 Bot dimatikan manual.")


if __name__ == "__main__":
    main()
