# Binance Spot Trading Bot — Design Spec

**Tanggal:** 2026-08-09
**Status:** Draft (menunggu review user)
**Scope:** Bot trading Binance spot terpisah dari bot MT5, untuk modal kecil (~$12 / Rp 200rb), deploy Linux.

## 1. Tujuan

Bot trading **Binance spot** (BTC/ETH/SOL) berbasis **2 proposer + 1 approver** (GPT + Gemini proposer, Claude approver), risk-averse, untuk memvalidasi sistem dengan modal kecil sebelum menaikkan modal. Berdiri sendiri di `binance_bot/`, tidak menyentuh bot MT5 yang berjalan.

## 2. Keputusan Kunci (dari diskusi)

| Keputusan | Pilihan |
|---|---|
| Mode | **Spot** (tanpa margin/futures) — nol risiko hutang, nol bunga, nol funding |
| Modal | Kecil (~$12 / Rp 200rb) — fokus validasi sistem, bukan profit |
| Lokasi kode | `binance_bot/` folder baru di repo ini |
| Strategi | **2 proposer (GPT + Gemini) + 1 approver (Claude)** — Claude hanya dipanggil saat 2/2 sepakat (hemat biaya) |
| Risk | 1-2% per trade dari equity, trading 24/7 (crypto), daily loss limit |
| API | HMAC API key + REST polling (`/api/v3/*`) — cukup untuk bot M30; WebSocket API (butuh Ed25519) ditunda |
| Deploy | Linux VPS, systemd, tanpa aplikasi tambahan |

## 3. Struktur File

```
binance_bot/
├── main.py                  # Loop utama (5 detik manage posisi, M30 cycle)
├── config.py                # Semua parameter + API keys (baca .env)
├── .env.example             # BINANCE_API_KEY, BINANCE_SECRET, LLM keys
├── requirements.txt         # python-binance / ccxt, openai, anthropic, google-genai, python-dotenv
├── src/
│   ├── core/
│   │   ├── binance_connector.py   # Market data, kline, order (OCO), balance, myTrades, exchangeInfo
│   │   ├── llm_client.py          # 2 proposer (GPT+Gemini) + approver (Claude), prompt M30
│   │   ├── consensus.py           # Weighted consensus 2 proposer + Claude approve
│   │   └── risk_engine.py         # Daily loss, cooldown, risk-based sizing (USDT), max posisi
│   └── analytics/
│       └── position_manager.py    # Trailing/break-even bot-side (spot tanpa SL/TP broker)
├── data/                    # State: risk_state.json, decision_memory.json, dll
└── tests/
    ├── test_binance_connector.py  # Mock API, parsing, qty rounding
    └── test_risk_engine.py        # Daily loss, sizing, min notional
```

## 4. Alur Kerja

**Loop utama (5 detik):**
1. Manage posisi open (trailing/BE bot-side, cek status OCO)
2. Deteksi posisi closed (`myTrades`/order status) → update P/L + notif
3. Cek daily loss + cooldown
4. Kalau candle M30 baru → full cycle

**Full cycle (tiap M30):**
1. Risk gate (`can_trade`): daily loss, cooldown, max posisi, min notional
2. Ambil 50 candle M30 + tick + balance USDT
3. **2 proposer paralel** (GPT + Gemini): signal + confidence + SL/TP proposal
4. Kalau 2/2 sepakat & skor ≥ threshold → **panggil Claude approver** (approve/reject + koreksi SL/TP)
5. Claude approve → hitung qty dari risk% → **OCO order** (entry market + SL stop-limit + TP limit)
6. Tidak → HOLD (Claude tidak dipanggil)

**Close posisi:** OCO order handle SL & TP di sisi exchange (one-cancels-other). Bot deteksi close via order status/myTrades tiap 5 detik.

**Batasan spot (penting):**
- Spot **tidak bisa short** — bot hanya bisa **BUY** (long) saat tidak punya posisi.
- Signal **SELL** saat tidak punya posisi → **tidak trade** (hold USDT), karena tidak ada aset untuk dijual.
- Signal **SELL** saat punya posisi BUY → dianggap **exit** (jual posisi, ambil profit/cut loss).

## 5. Parameter Config

```
BINANCE_API_KEY / SECRET      # dari .env
TESTNET = True                # default testnet, False = live
SYMBOL = "BTCUSDT"
TIMEFRAME = "30m"
DRY_RUN = True                # default dry-run
RISK_PERCENT = 1.5            # risk per trade dari equity USDT
MAX_DAILY_LOSS_USD = 3.0      # ~25% dari $12 — ketat
MAX_OPEN_POSITIONS = 2
TRADE_COOLDOWN_SECONDS = 300
MIN_NOTIONAL_USD = 5.0        # validasi order min
CONFIDENCE_THRESHOLD = 1.2    # 2 proposer: skor ≥ 1.2
CLAUDE_APPROVER_ENABLED = True
TELEGRAM_ENABLED = False      # fase 2
LOG_FILE = "binance_bot.log"
```

## 6. Perbedaan Utama vs Bot MT5

1. **`binance_connector`** ganti `mt5_connector` — REST `/api/v3/*`: klines, account, order (OCO), myTrades, exchangeInfo (step size + min notional).
2. **SL/TP via OCO order** — spot tanpa SL/TP broker; OCO = limit TP + stop-limit SL sekaligus, jalan di sisi exchange.
3. **Risk sizing** — `qty = risk_usd / sl_distance_usd_per_btc`, clamp ke step size (0.00001 BTC) + validasi min notional (~$5).
4. **Arsitektur 2+1** — GPT+Gemini proposer, Claude approver (hanya saat 2/2).

## 7. Error Handling

- **Rate limit / timeout** — retry dengan backoff; tangani `-1021` (timestamp skew) & `-2015` (invalid API key).
- **Network disconnect** — log + skip cycle, jangan crash.
- **Order ditolak** (min notional, precision) — validasi via exchangeInfo filters sebelum kirim, log jelas.
- **Restart** — state di-persist (risk_state.json), `sync_closed_positions` di startup (deteksi posisi closed saat bot mati).

## 8. Testing & Deploy

**Testing:**
- Testnet dulu (`TESTNET=True`, `testnet.binance.vision`) — validasi order flow, SL/TP, P/L tracking.
- `tests/test_binance_connector.py` — mock API, parsing, qty rounding.
- `tests/test_risk_engine.py` — daily loss, sizing, min notional.
- Dry-run (`DRY_RUN=True`) — sinyal dihitung, order tidak dikirim.

**Deploy Linux:**
```
pip install -r binance_bot/requirements.txt
# systemd service dengan Restart=always
```
- Murni Python + API, tanpa aplikasi tambahan.
- `.env` berisi API key (jangan di-commit).

## 9. Scope

**Fase 1 (dibangun sekarang):** connector + risk + consensus 2+1 + position manager + main loop + testnet test.
**Fase 2 (opsional):** Telegram alert, dashboard, post-mortem lessons.

## 10. Referensi API

- Changelog Binance Spot (2026): percent-encode sebelum signing, `/api/v1/*` di-retire (pakai `/api/v3/*`), `userDataStream` REST dihapus (pakai WebSocket API Ed25519 atau polling REST), OCO via `POST /api/v3/orderList/oco`, `exchangeInfo` untuk filters (LOT_SIZE, MIN_NOTIONAL), Ed25519 direkomendasikan.
