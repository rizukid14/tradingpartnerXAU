# Catatan Settingan Lokal — Setelah Pull Remote `dev`

**Tanggal:** 2026-08-09
**Commit:** `2e6553b` (feat(binance): approver independen + hold-streak + sizing clamp + M15) — sama dengan `origin/dev`.
**Branch:** `dev` (fast-forward dari `e7e1397`).

---

## 1. Ringkasan Kondisi

- **Pull `origin/dev` sukses** (fast-forward, tanpa konflik di file kode).
- **`data/*.json` runtime state** lokal yang sedang ter-modif sudah di-resolve ke versi remote (di-stash lalu di-drop) — data lama tidak dipertahankan, karena itu state runtime yang bakal ditulis ulang bot.
- **`scratch/`** masih berisi 1 file backup (`decision_memory.remote.json`) — bisa dihapus kalau sudah tidak perlu.

---

## 2. Settingan yang SEKARANG Berlaku di Lokal (setelah pull)

### A. Mode & Akun
| Setting | Nilai |
|---|---|
| `DRY_RUN` | `False` — **LIVE** |
| Akun | `VTMarkets-Live 3`, login `27556325` |
| Symbol weekday / weekend | `XAUUSD-ECNc` (M5) / `BTCUSD.c` (M30) — rotasi otomatis |

### B. Model & API
| Setting | Nilai |
|---|---|
| Model decision | OpenAI `gpt-5.4-mini`, Gemini `gemini-3.5-flash-lite`, **Claude `claude-sonnet-4-6`** (fallback `claude-haiku-4-5-20251001`) |
| `ANTHROPIC_API_KEY` | **⚠️ BELUM ADA di `.env` lokal** — perlu ditambahkan, kalau tidak Claude gagal init |
| API key lain | OpenAI, Gemini, DeepSeek, MT5, Telegram — sudah ada di `.env` |
| `TELEGRAM_ENABLED` | sudah di-set di `.env` (true/false sesuai isi) |

### C. Consensus & AI
| Setting | Nilai |
|---|---|
| Konsensus | **Weighted confidence** — Σ confidence per arah, ≥ 2 model searah, threshold XAU 1.0 / BTC 1.2; defensif 3/3 = ×1.5 |
| `DEBATE_ENABLED` | `False` |
| `QUANT_ANALYSIS_ENABLED` | `True` (Hurst + fat-tail + Monte Carlo) |
| `FORECAST_ENABLED` | `True` |
| `MEMORY_CONTEXT_ENABLED` | `True` |

### D. Risk & Eksekusi
| Setting | Nilai |
|---|---|
| `RISK_PERCENT_BTC` | `1.5` |
| `RISK_PERCENT_XAU` | `0.5` |
| Lot | **Risk-based**, tapi **final selalu di-clamp ke 0.01 minimum** (sesuai preferensi user — lot tidak pernah naik di atas 0.01) |
| `MAX_DAILY_LOSS_USD` | `50.0` |
| `MAX_CONSECUTIVE_LOSSES` | `3` (pause 30 menit) |
| `MAX_OPEN_POSITIONS` | `6` normal / `4` saat recovery |
| `BREAK_EVEN_TOLERANCE_USD` | `0.04` (BEP excluded dari win-rate & tidak reset streak) |
| `RECOVERY_EXIT_PROFIT_USD` | `0.10` |
| `WEEKEND_TRADING_ENABLED` | `False` — tidak buka posisi baru di weekend (spread lebar, tidak profitable), posisi lama tetap di-manage |

### E. Proteksi Posisi (per-symbol)
| Setting | XAU | BTC |
|---|---|---|
| Trailing activation / distance | 200 / 150 pts | 17000 / 12500 pts |
| Break-even trigger / padding | 100 / 10 pts | 33500 / 1000 pts |
| Partial close TP1 | 400 pts | 44500 pts |
| `POSITION_MANAGER_MAX_TICK_AGE_SECONDS` | 300 | 300 |

### F. Timeframe & MTF
| Setting | Nilai |
|---|---|
| Timeframe | XAU **M5**, BTC **M30** |
| MTF context | XAU M30/H1, BTC H1/H4 |
| Forecast horizon | XAU T+15m/T+60m (cache 15 mnt), BTC T+4h/T+D1 (cache 1 jam) |
| Spread filter | XAU ≤ 50 pts, BTC ≤ 2400 pts |

---

## 3. Fitur Baru yang Ikut Pull (sekarang aktif di lokal)

- **Interactive setup + CLI overrides** — `python main.py` akan muncul menu interaktif, atau lewati dengan `--yes`; ada `--era v1/v2/v3`, `--dry-run`, `--live`, `--risk-percent-*`, `--threshold-*`, `--quant on/off`, `--memory on/off`, dll.
- **Era presets** (`ERA_PRESETS` di config.py): v1 (legacy: quant OFF, debate ON), v2 (= v1 + state), v3 (modern: quant ON, debate OFF). **Preset hanya mengubah flag yang masih ada — model & consensus tidak bisa di-revert via preset.**
- **Bot Binance spot** (`binance_bot/`) — terpisah, testnet+dry-run default, tidak menyentuh bot MT5.
- **Dashboard** — `python dashboard.py` (static) atau `python dashboard.py --serve --port 8765` (live).
- **Telegram alerts** — `src/core/telegram_alerts.py`.
- **Real-time close detection** — `sync_closed_positions()` tiap 5 detik + alert Telegram.

---

## 4. Hal yang Perlu Diperhatikan

1. **`.env` belum punya `ANTHROPIC_API_KEY`** — Claude ganti DeepSeek di kode, tapi key-nya belum di-set lokal. Bot akan jalan dengan OpenAI + Gemini + (Claude fallback error → HOLD). Tambahkan key ini ke `.env` sebelum menjalankan bot.
2. **`data/*.json` sekarang versi remote** — state runtime lama sudah diganti (di-stash lalu di-drop). Bot akan regenerate saat jalan.
3. **`scratch/decision_memory.remote.json`** — backup sementara, hapus kalau sudah tidak perlu.
4. **`docs/remote-changes-2026-08-09.md`** — analisis sebelum pull (dokumen ini).
5. **Kalau mau commit + push**: `docs/` (catatan baru) saja yang perlu di-stage; `data/*.json` jangan (runtime state, konvensi AGENTS.md).
