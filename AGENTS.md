# AGENTS.md — Konteks Proyek Trading Bot

> Ringkasan cepat untuk sesi coding. Baca ini dulu sebelum ngapa-ngapain.

## ⚠️ ATURAN WAJIB AI AGENT (MANDATORY AGENT RULES)
 
1. **SELALU MINTA KONFIRMASI SEBELUM MENGUBAH KODE (ALWAYS ASK BEFORE EDITING CODE)**:
   - Sebelum melakukan edit/perubahan file kode apa pun, AI WAJIB menjelaskan masalah dan menampilkan rencana/perubahan yang diusulkan.
   - AI DILARANG mengeksekusi tool edit file (`replace_file_content`, `write_to_file`, `multi_replace_file_content`) sebelum pengguna memberikan persetujuan/konfirmasi eksplisit.

---

## Apa ini

Bot trading **multi-LLM consensus** (OpenAI + Gemini + Claude/DeepSeek) yang berjalan di **MetaTrader 5**.
- **TRADING_MODE = "xau_pairs" (Default)**: **Pool 7 simbol FX paralel**: `WEEKDAY_SYMBOL = "GBPUSD-ECNc"` + 6 FX pairs (`EURJPY-ECNc`, `GBPAUD-ECNc`, `AUDCAD-ECNc`, `EURCHF-ECNc`, `AUDCHF-ECNc`, `CADCHF-ECNc`). Timeframe FX: **H1 swing**, risk per trade: **1.25%**.
- **BTCUSD.c (Bitcoin)**: Intraday **M30**, risk: **1.5%**, aktif di weekend + setelah jam 22:00 Jumat WIB (`ENABLE_BTC_ROTATION`). Bebas swap overnight.
- **XAUUSD-ECNc (Gold)**: Intraday **M30**, risk: **1.0%** (aktif saat mode `xau`).
- **Smart Timeframe Rotation**: AI dipanggil per-simbol HANYA pas candle timeframe simbol itu berganti (`_symbol_last_candle` di `main.py`) — FX tiap 1 jam, BTC/XAU tiap 30 menit (hemat token drastis ~90%).
- **Akun**: **LIVE** `VTMarkets-Live 3` (login `27556325`), Balance ~$1065, Waktu **WIB** (Asia/Jakarta).

---

## Cara jalanin

```bash
python main.py
```
- `config.DRY_RUN = False` $\rightarrow$ **LIVE trading** (order beneran dikirim). Jangan ubah tanpa izin user.
- **Ganti mode trading**: `.env` `TRADING_MODE=xau` / `TRADING_MODE=xau_pairs`, atau via UI dashboard $\rightarrow$ restart bot biar apply.
- Log: `data/trading_bot.log` (auto-rotate 2MB, keep 5000 baris). Log ini campur sesi demo lama + live baru; verifikasi akurat dilakukan dengan query MT5 langsung.

---

## Arsitektur file

| File | Fungsi |
|---|---|
| `main.py` | Loop utama: manage posisi tiap 3 detik, full cycle tiap candle per-simbol dengan **Smart Timeframe Rotation** |
| `config.py` | Parameter konfigurasi global + helper per-simbol (`lot_size_for`, `risk_percent_for`, `default_sl/tp`, dll) |
| `src/core/llm_client.py` | Build prompt dinamis per-simbol + pemanggilan LLM paralel sesuai jadwal **Time-Based AI Mode** |
| `src/core/consensus.py` | **Weighted confidence consensus** (skor $\ge$ threshold, min 2 model) + filter safety floor + AI re-evaluator CLOSE |
| `src/core/risk_engine.py` | Filter spread, daily loss ($50), daily profit target 6%, dead zone 02:00-06:00 WIB, recovery mode, risk lot sizing |
| `src/core/mt5_connector.py` | Order send/close, history deals, market data MT5, magic filter |
| `src/core/economic_calendar.py` | Dynamic fetch kalender ekonomi (TradingView/Investing.com) + anti-FOMC/news context |
| `src/core/telegram_bot.py` | 2-Way Interactive Telegram Controller (On-demand 3-AI analysis, position manager, status command via POST fast-polling) |
| `src/analytics/position_manager.py` | Global Break-Even (58% TP + komisi), Trailing Stop (70% TP, konstan 0.5×ATR), evaluasi posisi |
| `src/analytics/macro_analyst.py` | Fundamental + MTF context per-simbol (H4/D1, EMA200, slope EMA50), cache berlaci per-simbol |
| `src/analytics/trade_evaluator.py` | Post-mortem evaluasi trade tertutup $\rightarrow$ lessons (`data/memory_lessons.json`) |
| `src/analytics/decision_memory.py` | Tracking hasil & 6 keputusan terakhir per-simbol |

---

## Alur cycle (`main.py` $\rightarrow$ `run_trading_cycle`)

0. **Time-Based AI Mode (WIB)**: 
   - **00:00–18:59 = Dual** (OpenAI o4-mini + Gemini 3.1-flash-lite — Dead Zone 02:00-06:00 auto-skip).
   - **19:00–22:00 = Triple** (OpenAI o4-mini + Gemini 3.1-flash-lite + DeepSeek V4 Flash / Claude — overlap London-NY).
   - **22:01–23:59 = Dual** (OpenAI o4-mini + Gemini 3.1-flash-lite — Late NY).
1. `risk.can_trade()` — filter spread/sesi/daily loss/profit target. Gagal $\rightarrow$ skip (0 token).
2. Ambil data 100 closed bars + tick live + indikator ADX(14), ATR, EMA, Fib 50/100-bar.
3. Sinkronisasi deal tertutup + update post-mortem lessons.
4. **Panggil LLM paralel sesuai Time-Based AI Mode**.
5. **Weighted Consensus Engine**: skor $\Sigma$ confidence $\ge$ threshold (FX 1.0, BTC 1.2; defensif $\times 1.5$) + eksekusi rekomendasi CLOSE dari AI Re-evaluator.
6. Forecast context (bias/target) bersifat murni *informational* (tidak memblokir eksekusi).
7. **Risk-based lot sizing**: lot dihitung dari equity & SL (FX 1.25%, BTC 1.5%, XAU 1.0%).
8. Cek kapasitas max posisi (aggregate pool 6 posisi), lalu eksekusi order MT5.

---

## Gate eksekusi aktif (Hard Rules)

- **Weighted Consensus**: $\ge 2$ model searah, skor confidence > threshold per-simbol (FX 1.0 / BTC 1.2).
- **Aturan SL/TP (`config.sltp_mode_for(symbol)`)**:
  - **FX Pairs = Mode LLM**: SL/TP murni struktur teknikal LLM, dibatasi **Safety Floor** $\max(2\times \text{spread}, 50\text{ pts})$ + **Gate R:R minimum 1.25:1** (TP dinaikkan otomatis jika R:R < 1.25).
  - **BTC & XAU = Mode ATR-Based**: Gate ATR non-negotiable (R:R 2:1 fix).
- **Spread Filter**: Spread $\le 50$ pts (FX & XAU) / $\le 2400$ pts (BTC).
- **Dead Zone**: 02:00–06:00 WIB (hanya untuk FX & XAU; BTC tetap aktif 24/7).
- **Proteksi Akun**: Max daily loss $50, max 3 consecutive loss, daily profit target 6%, max 6 total posisi bot.
- **Proteksi Posisi Real-Time (`position_manager.py`)**:
  - **Break-Even (BEP)**: Aktif di **58% TP** + padding komisi round-trip + Pocket Profit 1.5 pips (15 pts).
  - **Trailing Stop**: Aktif di **70% TP**, jarak **konstan 0.5× ATR(14)** dari harga ekstrem, floor absolut 60 pts (6 pips).

---

## Status Terkini Sistem (Live Production — Agustus 2026)

1. **FX Pairs 7-Symbol Pool (H1)**: Parallel scan 7 simbol (`GBPUSD`, `EURJPY`, `GBPAUD`, `AUDCAD`, `EURCHF`, `AUDCHF`, `CADCHF`).
2. **Trend-Aware Dual-Window Fibonacci**: Window 50-bar Intraday + 100-bar Macro Multi-Day dengan formula sadar arah tren.
3. **Dynamic Pending Orders Prompt**: Jika `PENDING_ORDERS_ENABLED = False`, blok pending rules dan field `entry_type`/`entry_price` dihilangkan 100% dari prompt (menghemat ~459 token).
4. **Paket Anti-FOMC & High-Impact News (Dynamic TradingView API)**:
   - Dynamic fetch kalender TradingView/Investing.com (cache 6 jam, filter US, GB, EU, CH, JP, AU, CA).
   - Window 6 jam sebelum & 6 jam sesudah rilis berita.
   - Conditional prompt rule: larang keras fade momentum breakout / mean-reversion counter-trend saat ada event berita.
5. **Indikator ADX(14) & Slope EMA50**: Deteksi kekuatan tren real-time + Critical Trend Filter untuk mencegah melawan tren kuat.
6. **Top-Down Attention Flow Prompt**: Urutan prompt: Macro H4/D1 $\rightarrow$ Key Levels $\rightarrow$ Technical Indicators $\rightarrow$ Structure 50/100-bar $\rightarrow$ Recent Candles $\rightarrow$ Execution Directives.
7. **2-Way Interactive Telegram Bot Controller (`src/core/telegram_bot.py`)**:
   - Menu kontrol institusional `[ ☰ Menu ]` via `setMyCommands` & inline interactive keyboard.
   - On-demand 3-AI consensus analysis trigger (`/analisa <symbol>` atau klik button pair).
   - Pemantauan akun real-time (`/status`, `/posisi`, `/scan`, `/closeall`).
   - Fast POST polling via Vercel proxy (`https://tg-proxy-vercel-eight.vercel.app`).
   - *Status task fixing*: Perlu finalisasi stabilitas penerimaan input/command background listener saat berdampingan dengan main cycle MT5.

---

## Konvensi & Catatan Operasional

- **Komunikasi**: Bahasa Indonesia (santai, lugas, teknikal).
- **Risk-Averse**: Prioritas utama adalah perlindungan modal.
- **Magic Number**: `20260625`. Bot hanya mengelola tiket dengan magic ini.
- **Git Workflow**: Branch `dev` = branch aktif utama.
- **File Disk**: Folder `data/` dan `scratch/` di-`.gitignore`. File script sementara di `scratch/` dibersihkan berkala.

---

## 📚 Indeks Dokumentasi & Riset Lengkap

Dokumentasi lengkap telah dikelompokkan ke dalam direktori tematik di [docs/README.md](file:///c:/Vibe/tradingpartner/docs/README.md):

| Kategori | Dokumen | Deskripsi Isi |
|---|---|---|
| 💡 **Plans & RFC** | **[docs/plans/IDEAS_AND_PLANS.md](file:///c:/Vibe/tradingpartner/docs/plans/IDEAS_AND_PLANS.md)** | **Daftar Ide & RFC Fitur Baru**: One-Shot Emergency Drawdown Re-Evaluator (80% SL + High-Density Prompt), Refaktor Pending Consensus, Parabolic Filter, Anti-Hedge Gate. |
| 📊 **Research** | **[docs/research/QUANT_RESEARCH_EDGES.md](file:///c:/Vibe/tradingpartner/docs/research/QUANT_RESEARCH_EDGES.md)** | **Riset Statistik Bebas Bias (3–4 Tahun)**: Temuan 112 Edge Pola Bearish NY, Ranking Pair Forex, Riset CAD/EUR/GBP & JPY, Riset Donchian XAU BUY NY, Confluence. |
| 📈 **Research** | **[docs/research/backtest_augustus_2026.md](file:///c:/Vibe/tradingpartner/docs/research/backtest_augustus_2026.md)** | **Hasil Backtest Agustus 2026**: Evaluasi 10 strategi buku (NotebookLM), Erratum S9 Horn, Verifikasi S9 + Target Struktural GBPUSD. |
| 🏗️ **Architecture** | **[docs/architecture/LLM_COST_ESTIMATION.md](file:///c:/Vibe/tradingpartner/docs/architecture/LLM_COST_ESTIMATION.md)** | **Estimasi Frekuensi & Biaya LLM**: Simulasi kuota token, perbandingan opsi DeepSeek vs Claude Sonnet per bulan. |
| 🏗️ **Architecture** | **[docs/architecture/PROMPT_COMPARISON.md](file:///c:/Vibe/tradingpartner/docs/architecture/PROMPT_COMPARISON.md)** | Perbandingan skema prompt antar iterasi versi bot. |
| 🚀 **Deployment** | **[docs/deployment/vps_deployment.md](file:///c:/Vibe/tradingpartner/docs/deployment/vps_deployment.md)** | Panduan deployment production bot ke VPS. |
| 📜 **Archive** | **[docs/archive/CHANGELOG_AUGUST_2026.md](file:///c:/Vibe/tradingpartner/docs/archive/CHANGELOG_AUGUST_2026.md)** | **Arsip Changelog Detail (8–15 Agustus 2026)**: FASE 1–7, pemisahan mode SL/TP, evolusi lot sizing, dan perbaikan historis. |
| 🗂️ **Master Index** | **[docs/README.md](file:///c:/Vibe/tradingpartner/docs/README.md)** | Indeks lengkap seluruh file dokumentasi, buku trading (PDF), dan spesifikasi. |
