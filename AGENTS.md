# AGENTS.md — Konteks Proyek Trading Bot

> Ringkasan cepat untuk sesi coding. Baca ini dulu sebelum ngapa-ngapain.

## ATURAN WAJIB AI AGENT (MANDATORY AGENT RULES)
 
1. **SELALU MINTA KONFIRMASI SEBELUM MENGUBAH KODE (ALWAYS ASK BEFORE EDITING CODE)**:
   - Sebelum melakukan edit/perubahan file kode apa pun, AI WAJIB menjelaskan masalah dan menampilkan rencana/perubahan yang diusulkan.
   - AI DILARANG mengeksekusi tool edit file (`replace_file_content`, `write_to_file`, `multi_replace_file_content`) sebelum pengguna memberikan persetujuan/konfirmasi eksplisit.

2. **`.env` ADALAH SINGLE SOURCE OF TRUTH UNTUK KONFIGURASI (CONFIGURATION OVERRIDE)**:
   - File `.env` SELALU me-*override* nilai default di `config.py` via `load_dotenv()`.
   - Jika mengubah parameter konfigurasi/fitur (enable/disable fitur, jam operasi, threshold, risk), AI WAJIB mengecek dan mengubah langsung file `.env` di samping `config.py`. Mengubah `config.py` saja tanpa menyelaraskan `.env` adalah KESALAHAN FATAL karena `.env` yang akan dimuat saat bot berjalan.

3. **KONVERSI WAKTU SERVER MT5 KE WIB (SERVER TIME + 4 JAM = WIB)**:
   - Server MT5 (`VTMarkets-Live 3`) beroperasi di zona **GMT+3**.
   - **Waktu WIB (GMT+7) = Jam Server MT5 + 4 Jam**.
   - **Pergantian Hari / Daily Rollover (00:00 Server) = TEPAT JAM 04:00 WIB**.
   - Jendela bahaya lonjakan spread rollover dan *liquidity gap* terjadi di **03:55 – 04:15 WIB** (00:00 server). AI DILARANG keras salah menghitung waktu rollover sebagai jam 05:00 atau jam 07:00.

4. **ANALISIS DAMPAK HOLISTIK & PENYELARASAN MENYELURUH (ZERO HALF-BAKED CHANGES)**:
   - Setiap kali melakukan perubahan besar (timeframe, rotasi pool pair, jam sesi, SL/TP rules, model AI, atau risk gate), AI WAJIB memikirkan dan memeriksa SEMUA file yang terdampak secara holistik dalam 1 kali jalan tanpa menunggu diminta satu per satu.
   - **INTEGRITAS IMPORT & SINTAKS (ZERO MISSING IMPORTS / ZERO NAME_ERROR)**:
     - AI WAJIB memastikan semua library (`datetime`, `ZoneInfo`, `os`, `sys`, `json`, dll), konstanta, dan helper module internal ter-import dengan sempurna di bagian atas file yang diedit.
     - DILARANG menggunakan variabel/konstanta tanpa deklarasi atau import eksplisit (mencegah `NameError` saat runtime).
   - **Daftar Checklist 8 File Wajib Diperiksa & Diselaraskan Setiap Ada Perubahan**:
     1. **`config.py` & `.env`**: Parameter konfigurasi, default fallback, helpers per-simbol (`get_timeframe`, `lot_size_for`, `risk_percent_for`, `get_higher_timeframes`), dan import `ZoneInfo`/`datetime`.
     2. **`src/core/llm_client.py`**: Prompt AI, deteksi label timeframe (`tf_label`), jumlah candle intra-period (`num_micro_send`), format JSON output, ringkasan momentum mikro, dan variabel lokal candle.
     3. **`src/core/cli_theme.py` & `main.py`**: Banner utama terminal, dynamic status clock line (`[POOL 4 PAIRS (H1) | HH:MM:SS]`), dan log range candle.
     4. **`src/core/telegram_bot.py` & `telegram_alerts.py`**: Label tombol menu keyboard (`GBPUSD H1/M30`), command on-demand (`/analisa`, `/scan`, `/status`), dan pesan alert.
     5. **`src/analytics/macro_strategic_engine.py`**: Pure Quant 6-TF Native Sockets (`MN1/W1/D1/H4/H1/M30`), SBR/RBS zone hierarchy, 5-Tier Operational Action Matrix, dan zero-token on-demand context injection.
     6. **`src/core/risk_engine.py` & `position_manager.py`**: Filter spread, dead zone, ATR-based safety floor, time-decay stagnation, dan pre-rollover shield.
     7. **`tests/test_*.py`**: Unit test suite (`test_symbol_rotation.py`, `test_time_decay_and_vol_regime.py`, `test_macro.py`) wajib diupdate dan dipastikan **100% PASS**.
     8. **`docs/CHANGELOG_SEPTEMBER_2026.md` & `AGENTS.md`**: Pencatatan changelog detail dan sinkronisasi ringkasan arsitektur.
5. **GAYA KOMUNIKASI & ZERO FLATTERY / ZERO OVERCLAIM**:
   - Dilarang membuka respon dengan frasa validasi basi atau persetujuan emosional (*"Kamu benar 100%"*, *"Sangat tepat"*, *"Penemuan brilian"*, dll).
   - Dilarang membuat klaim statistik absolut (*"Reversal 94%"*, *"Pasti membalik"*, *"100% terbukti"*) tanpa menyajikan uji *Conditional Probability* dan *Confidence Interval*.
   - Lewati kalimat basa-basi. Langsung jawab substansi teknikal dan data faktual terlebih dahulu.
   - Jika asumsi pengguna atau AI sebelumnya keliru/mengandung bias, katakan langsung apa adanya secara lugas, dingin, dan objektif tanpa melembutkan dengan pujian.

6. **STANDAR BERPIKIR KUANTITATIF RIGOROUS (ANTI-GAMBLER'S FALLACY & SCIENTIFIC HYPOTHESIS TESTING)**:
   - **Pembedaan Mutlak Marginal vs Conditional**:
     * Wajib membedakan *Distribusi Marginal (Base Rate/Panjang Deret)* dari *Distribusi Bersyarat P(A|B) (Transisi Bar Berikutnya)* guna mencegah jebakan *Gambler's Fallacy*.
   - **Uji Null Hypothesis ($H_0$) Sebelum Mengklaim Edge**:
     * Setiap klaim prediktif wajib diuji terhadap model *Memoryless / Random Walk* menggunakan *Wilson Score Confidence Interval 95%* dan *Chi-Square Test*.
   - **Pemisahan Konteks Struktur vs Candle Count**:
     * Jangan mengatribusikan edge ke hitungan lilin murni jika efeknya hanya muncul saat menabrak *HTF Structure / Liquidity Key Levels*.
     * Struktur HTF (PWH/PWL, Dealing Range Origin Anchor, Order Blocks) adalah fondasi primer, bukan jumlah bar.
    - **Syarat Validitas Backtest & Verifikasi**:
      * Dilarang mengklaim sistem baru "valid/superior" hanya berdasarkan $\le 20$ trade dalam rentang waktu sempit ($\le 7$ hari).
      * Minimal sample size untuk klaim edge statistik adalah $\ge 60 - 100+$ trade dengan *Out-of-Sample Holdout* atau *Walk-Forward Validation*, dilengkapi evaluasi Max Drawdown, Profit Factor, Sharpe Ratio, dan Slippage-Adjusted Return.

7. **ATURAN TERMINOLOGI WAJIB (UNIVERSAL LIQUIDITY SWEEP)**:
   - DILARANG menggunakan istilah *"Judas Sweep"*, *"London Judas Sweep"*, atau istilah turunan Judas di seluruh codebase, file dokumentasi, prompt LLM, alert Telegram, dan percakapan.
   - Gunakan selalu terminologi kuantitatif resmi: **"Universal Liquidity Sweep"**, **"Universal Sweep"**, atau **`UNIVERSAL_LIQUIDITY_SWEEP`**.
---

## Apa ini

Bot trading **multi-LLM consensus** (OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4 Flash) yang berjalan di **MetaTrader 5** dengan arsitektur **2-Stage Quant Funnel** (branch `quant-trade` dan branch `quant-trade-noAI` untuk Pure Quant No-LLM).

- **`TRADING_MODE = "scanner"` (Default)**: Universe **26 simbol FX Terkurasi** dipindai paralel tiap 60 detik oleh **Stage 1 Fast Radar** (`market_scanner.py`) — mekanisme M1 (Universal Liquidity Sweep & SFP), M2 (Trend-Aligned Pullback), M3 (Multi-Touch Breakout Retest), M4 (Systemic Flow Continuation) — dengan timeframe struktural **H1 untuk seluruh 26 FX pair (termasuk JPY Crosses pasca unifikasi 4 Sep 2026)**. Hanya **8–15 setup A+ per hari** yang lolos ke **Stage 2 (3-LLM Consensus Jury)**. Hemat ~85% token API vs full-cycle scan.
- **BTCUSD.c (Bitcoin)**: Rotasi akhir pekan 24/7. Mode `ENABLE_BTC_ROTATION=True` dan `WEEKEND_TRADING_ENABLED=True` mengaktifkan `BTCUSD.c` pada hari Sabtu–Minggu (M1, M2, M3 aktif, M4 off; max 2 posisi, risk 0.50%).
- **Pure Quant Direct Execution (`quant-trade-noAI`)**: Mode `ENABLE_LLM_JURY=False` mengeksekusi setup quant langsung ke MT5 (0 token API) dengan institutional safety check (`MT5_ACCOUNT_MODE=demo`).
- **XAUUSD-ECNc (Gold)**: **DIMATIKAN TOTAL PERMANEN** (30 Agustus 2026). Audit membuktikan Gold menyebabkan $-\$1,067.79$ drawdown akun live sementara portofolio 26 FX membukukan net profit $+\$387.08$. Gold dihapus dari universe scanner `.env` dan `config.py`.
- **HTF Macro Cache (Stage 1A)**: Struktur D1 + H4 + W1 di-fetch sekali per refresh window (~$60$ detik) lalu dipakai semua simbol → **0 token LLM**. CSM (Boitoki Currency Strength Matrix) dihitung sub-detik.
- **Mode AI**: `AI_MODE_POLICY = "fixed"` + `AI_FIXED_MODE = "triple"` → **selalu 3-LLM jury** (OpenAI + Gemini + DeepSeek) saat `ENABLE_LLM_JURY=True`.
- **Akun**: **DEMO** `VTMarkets-Demo` (login `1157958`) di branch `quant-trade-noAI` / **LIVE** `VTMarkets-Live 3` (login `27556325`) di branch `quant-trade`, magic `20260625`, Waktu **WIB** (Asia/Jakarta).

> **Tidak ada konsep "default pair" di scanner mode**. Semua 26 simbol FX setara, diproses paralel oleh radar.

---

## Cara jalanin

```bash
python main.py
```
- `config.DRY_RUN = False` $\rightarrow$ **LIVE trading** (order beneran dikirim). Jangan ubah tanpa izin user.
- Log: `data/trading_bot.log` (auto-rotate 2MB, keep 5000 baris). Untuk verifikasi akurat profit, query MT5 langsung via `scratch/` script (hapus setelah dipakai).
- Mode scanner = bot **tidak** memilih 1 simbol aktif. Semua 26 simbol FX di-pindai paralel. Stage 2 hanya panggil 3-LLM saat setup A+ lolos filter Stage 1.

---

## Arsitektur file

| File | Fungsi |
|---|---|
| `main.py` | Looping: trigger Stage 1 radar tiap 60 detik + Stage 2 LLM saat ada setup A+ lolos + manage posisi tiap 3 detik (BEP/trailing/partial) |
| `config.py` | Parameter konfigurasi global + helper per-simbol + universe `SCANNER_SYMBOLS` |
| `src/analytics/market_scanner.py` | **Stage 1 Radar** — 4 mekanisme (M1 Universal Liquidity Sweep, M2 Pullback, M3 HTF Weekly Wall, M4 Systemic Flow Continuation) + HTF cache (D1/H4/W1) + feed currency-z M4 (rolling 24-bar H1, warm 720, 1×/jam) + **`permission_state` dihitung di sini** (mapping langsung dari MSE action tier: `FULL_ALLOW→GO/ARM`, `TP1_ONLY_SCALP/REDUCED_CONFIDENCE→ARM`, `WATCH_ONLY→WATCH`, `HARD_BLOCK→LOCK`) + gate arah terpadu `_is_direction_allowed()` (Macro Bias + CSM Flow Opposition + Systemic Basket Lock) + meneruskan `zce_walls` ZCE ke MSE |
| `src/indicators/wave_regime.py` | Wave Regime & compression/range age (pengganti `wave_state.py` yang sudah dihapus) — `evaluate_wave_regime()` |
| `src/indicators/lux_smc.py` | LuxAlgo Smart Money Concepts (OB/FVG/Strong Low/PWH-PWL) + FRVP confluence |
| `src/indicators/atlas_dna.py` | Symbol-specific psychological step (50/100/200 pips) + dynamic stations calculator |
| `src/analytics/currency_strength.py` | Boitoki CSM — modul mandiri, 8 mata uang dari 7 USD majors, Net Currency Delta; dibaca market_scanner (gate arah), llm_client (payload prompt), cli_theme/telegram (display). **Tidak hidup di MSE/ZCE** |
| `src/analytics/zone_confluence_engine.py` | **ZCE (RFC 11)** — peta zona 6-TF × multi-horizon, klaster/skor J1, wall elect F1/C1; hook `zce_walls` → MSE (`ZCE_ENABLED=true`, `ZCE_MODE=full` sejak 2 Sep 2026, test akun live cent) |
| `src/core/llm_client.py` | High-Density Dossier Prompt (Stage 2) + 24 candle M5 untuk Pass 2 audit |
| `src/core/consensus.py` | Weighted-confidence consensus (skor $\ge$ threshold) + `_apply_sltp_rules` floor ATR + AI re-evaluator CLOSE + Hard Risk Veto |
| `src/core/risk_engine.py` | Filter spread, daily loss 4% equity, profit target 6%, dead zone 02:00-06:00 WIB, recovery mode, risk lot sizing |
| `src/core/mt5_connector.py` | Order send/close, history deals, market data MT5, magic filter |
| `src/core/economic_calendar.py` | Dynamic fetch kalender ekonomi (TradingView/Investing.com) + anti-FOMC/news context |
| `src/core/telegram_bot.py` | 2-Way Interactive Telegram Controller + on-demand 3-AI analysis + `/radar` `/levels` `/smc` |
| `src/analytics/position_manager.py` | 2-Stage Trailing (H1 Breathing 65-90% TP, M30 Terminal Lock $\ge$90% TP), BEP 45-55%, partial close 50%, time-decay stagnation, pre-rollover shield |
| `src/analytics/macro_strategic_engine.py` | **Barrier Chamber State Machine** (6-TF Native `MN1/W1/D1/H4/H1/M30`), Density Cluster Scoring ($C_1, C_2, F_1, F_2$), Interaction Sequence Tracking (`['F1_SWEEP', 'C1_SWEEP']`), 7-State Engine, Pair-Calibrated SL Floor (35p Crosses) |

---

## Alur cycle (scanner mode)

1. **HTF Macro Cache Refresh** (tiap ~60 detik, 0 token): fetch D1+H4+W1 untuk 26 simbol FX → simpan `macro_cache`.
2. **Fast Execution Radar** (`market_scanner.scan_all`, tiap 60 detik, 0 token): 4 mekanisme scan semua simbol di timeframe struktural (H1 untuk seluruh 26 FX pair pasca unifikasi 4 Sep 2026) → cek `permission_state` hasil mapping MSE action tier (`FULL_ALLOW→GO/ARM` only — lihat tabel arsitektur; `HARD_BLOCK`/`WATCH_ONLY` = 0 token) + gate arah terpadu `_is_direction_allowed()` → kalau ada setup A+ lolos → **Stage 2 trigger**.
3. **Stage 2 — 3-LLM Consensus Jury** (per setup A+, ~5.5 detik):
   - **Pass 1** (paralel, ~3.0s): OpenAI o4-mini + Gemini 3.1-Flash menganalisis dossier independen.
   - **Pass 2** (cross-examination, ~1.5s): DeepSeek V4-Flash (Devil's Advocate CRO) mengaudit proposal + 24 candle M5 micro.
   - **Hard Risk Veto**: reject otomatis kalau flag `COUNTER_TREND_MOMENTUM/LIQUIDITY_TRAP/HIGH_IMPACT_NEWS/SPREAD_SPIKE/FALLING_KNIFE_WATERFALL`.
4. **Strict Unanimous 3/3 Consensus**: Wajib 100% kesepakatan bulat 3 model aktif (3/3 BUY atau 3/3 SELL). Jika ada 1 model saja yang HOLD/REJECT atau split vote → otomatis **HOLD** (Zero Tolerance Split). Unanimous + Confidence $\ge 80\%$ memicu split 2 posisi (+25% boost).
5. **`_apply_sltp_rules` floor & ceiling** (realita kode `consensus.py:155-206`, 4 Sep 2026):
   - JPY Crosses (H1): floor SL = $\max(2 \times \text{spread} + 20\text{ pts}, 0.50 \times \text{ATR H1}, 250\text{ pts})$; fallback 250 pts kalau ATR gagal.
   - FX Majors & Crosses (H1): floor SL = $\max(2 \times \text{spread} + 15\text{ pts}, 0.50 \times \text{ATR H1})$ (`LLM_FX_FLOOR_ATR_MULT` di `.env`); fallback 250 pts kalau ATR gagal.
   - NZD Alpha: $+20\text{ pts}$ anti-wick padding.
   - Ceiling (anti-runaway, **bukan** 160 pts statis): FX/JPY/Gold = $2.5 \times \text{ATR}$ (fallback 350 pts FX/JPY, 800 Gold); BTC = $1.8 \times \text{ATR}$ (fallback 45000). Hardcode di `consensus.py:186-206`.
   - TP $\ge 1.25 \times$ SL, $\le 3.0 \times$ SL (gate R:R; cap grade-aware di `consensus.py:214-253`).
6. **Risk-based lot sizing**: lot = `(equity × risk%) / (SL_pts × usd_per_point)`. FX 1.0%, BTC 1.5%, XAU 1.0%.
7. **Eksekusi MT5**: aggregate cap 6 posisi total + 4 pending aktif (shared pool). Late NY 23:00-02:00 WIB max 2 posisi. Recovery mode (≥5 loss streak) max 3 posisi.

---

## Gate eksekusi aktif (Hard Rules)

- **Strict Unanimous 3/3 Consensus**: 3/3 model wajib searah (3/3 BUY atau 3/3 SELL). 2/3 atau split vote otomatis HOLD. Unanimous $\ge 80\%$ confidence $\rightarrow$ eksekusi 2 tiket @ $0.625\times$ base lot (+25% boost).
- **Lantai & Plafon SL/TP (`_apply_sltp_rules` di `consensus.py` — realita 4 Sep 2026)**:
  - **Segmented Safety Floors (3 Sep 2026 / 4 Sep Unified H1)**:
    * **Quiet & Standard FX**: $\max(2 \times \text{spread} + 15\text{ pts}, 0.50 \times \text{ATR H1}, 120\text{ pts floor / 12 pips})$. Mengunci lot akun $5.8k $\le 0.40 - 0.45$ lot (eliminasi lot 1.27 / 1.60).
    * **High-Beta FX** (`GBPAUD`, `GBPNZD`, `EURNZD`, `GBPCHF`): $\max(2 \times \text{spread} + 20\text{ pts}, 0.50 \times \text{ATR H1}, 180\text{ pts floor / 18 pips})$.
    * **JPY Crosses** (H1): $\max(2 \times \text{spread} + 20\text{ pts}, 0.50 \times \text{ATR H1}, 250\text{ pts floor / 25 pips})$; ceiling $2.5 \times \text{ATR}$ (fallback 350 pts).
    * **NZD Crosses**: Tambahan $+20\text{ pts}$ anti-wick padding.
    * **M4 Systemic Flow**: Tunduk pada segmented safety floor & Net R:R (`M4_STRUCTURAL_FLOORED`).
  - **Friction-Aware Net R:R**: Target $\text{TP} = (\text{SL} \times R) + \text{Spread} + \text{Round-turn Commission}$ (memastikan net profit riil $\ge 1.25R$ bersih).
  - **M3 Fresh Breakout Law & Debounce**: Breakout recency $\le 4$ bar H1, displacement body $\ge 55\%$. Rejection di-lock 2 jam / sampai displacement $>0.50\times\text{ATR}$.
  - **Ceiling (anti-runaway)**: FX/JPY/Gold = $2.5 \times \text{ATR}$ (fallback 350 pts FX/JPY, 800 Gold); BTC = $1.8 \times \text{ATR}$ (fallback 45000).
  - **R:R**: Net TP $\in [1.25\times, 3.0\times]$ SL + friction (grade-aware). Pada setup `REDUCED_SCALP` / `TP1_ONLY_SCALP`, R:R dibatasi ke $[1.00\times, 1.25\times]$ guna mencegah pembengkakan TP makro pada scalp intraday.
- **Spread Filter**: FX = ATR-based $\max(15\% \times \text{ATR H1}, 20\text{ pts floor})$; XAU $\le 50$ pts; BTC $\le 2400$ pts.
- **Dead Zone**: 00:00–08:00 WIB (FX & XAU skip; BTC 24/7 di legacy mode).
- **Proteksi Akun**: Max daily loss **4% equity** (≈ $240 di $6k, BUKAN $50 statis), max 5 consecutive loss → recovery mode (lot ×0.5, max 3 posisi), daily profit target 6%, max 6 total open posisi (shared pool), max 4 active pending orders, **Friday Pre-Weekend Lock (freeze new orders mulai 23:00 WIB Jumat)**.
- **Proteksi Posisi Real-Time (`position_manager.py`)**:
  - **Break-Even (BEP)**: aktif di **45%–55% TP** + padding komisi round-trip + Pocket Profit 15 pts (1.5 pips).
  - **Partial Close (TP1)**: aktif di **45%–55% TP**, cairkan 50% lot + geser sisa ke Risk-Free BEP.
  - **2-Stage Dynamic Trailing Stop**:
    * **Stage 1 (Swing Breathing: 65% s/d < 90% TP)**: $0.75\times\text{ATR H1}$ dengan floor absolut 80 pts FX (8 pips).
    * **Stage 2 (Terminal Lock: $\ge$ 90% TP)**: $0.50\times\text{ATR M30}$ dengan floor 30 pts FX (3 pips).
  - **Peak-Aware Time-Decay Stagnation Exit**: posisi $\ge$4 jam hold di rentang $[-0.20R, +0.20R]$ ditutup jika Peak MFE $< +0.30R$.
  - **Pending Order Target Proximity Invalidation**: batalkan otomatis pending limit order jika harga live telah bergerak $\ge 75\%$ menuju TP tanpa terjemput (mencegah late adverse fill pada late reverse).
  - **Pending Order Harmonisasi Invalidation CSM**: pembatalan pending limit order diselaraskan dengan scanner threshold ($|\text{csm\_delta}| \ge 1.0$, `PENDING_CSM_OPPOSED_THRESHOLD`), mencegah auto-cancel prematur pada order valid.
  - **Pre-Rollover Shield (03:50–04:15 WIB)**: tutup bersih di 03:50 WIB JIKA jarak fisik ke SL $\le$ threshold per-simbol (EURCHF/EURNZD 240 pts, GBPCHF 210 pts, GBPUSD 180 pts, USDJPY 150 pts, NZDCAD 140 pts, AUDCAD 130 pts). Posisi SL aman / profit tebal dibiarkan jalan.

---

## Status Terkini Sistem (Live Production — Agustus 2026)

1. **2-Stage Quant Funnel (Branch `quant-trade` — 26 Agustus 2026)**: Universe 27 simbol paralel. Stage 1 radar 60-detik (0 token) + Stage 2 3-LLM jury hanya saat setup A+. Hemat ~85% biaya API vs full-cycle. Telegram `/radar` `/levels` `/smc` tampilkan live heat-table.
2. **4 Mekanisme Eksekusi Stage 1 Radar**:
   - **M1: Universal Liquidity Sweep & SFP (M15/M30/H1)** — sapuan likuiditas di level makro + reclaim → fade trap.
   - **M2: Trend-Aligned Pullback + Delayed Limit Retest ($0.20\times\text{ATR}$)** — pullback di zona diskon H1 + entry limit tertunda.
   - **M3: Multi-Touch Breakout Retest + M5 Micro-Rejection Filter (H1/M30)** — break level struktural + konfirmasi M5 rejection wick $\ge 25\%$ pada retest (mengeliminasi 75.7% waterfall penetration).
   - **M4: Systemic Flow Continuation (H1/M30 — 4 Sep 2026)** — currency z ≥1.5 (rolling 24-bar warm 720) → breakdown swing 120-bar → limit retest di level (horizon 48 bar / 2 hari bursa) ATAU M15/M30 High-Tight Basing (`/\/\/\/` kompresi $\le 0.35\times\text{ATR}$). SL struktural 0.45×ATR, TP 1.1R (`M4_STRUCTURAL_FLOORED`). Forward test akun live cent.
3. **Trend-Aware Dual-Window Fibonacci**: Window 50-bar Intraday + 100-bar Macro Multi-Day dengan formula sadar arah tren.
4. **Dynamic Pending Orders Prompt**: Jika `PENDING_ORDERS_ENABLED = False`, blok pending rules dan field `entry_type`/`entry_price` dihilangkan 100% dari prompt (hemat ~459 token).
5. **Paket Anti-FOMC & High-Impact News (TradingView API)**: Fetch kalender dinamis (cache 6 jam, filter US/GB/EU/CH/JP/AU/CA). Window 6 jam sebelum/sesudah rilis. Conditional rule: larang keras fade momentum breakout saat ada event.
6. **Indikator ADX(14) & Slope EMA50**: deteksi kekuatan tren real-time + Critical Trend Filter anti counter-tren.
7. **Top-Down Attention Flow Prompt**: Macro H4/D1 $\rightarrow$ Key Levels $\rightarrow$ Tech Indicators $\rightarrow$ Structure 50/100-bar $\rightarrow$ Recent Candles $\rightarrow$ Execution Directives.
8. **Telegram 2-Way Interactive Controller**: Menu institusional `[ Menu ]` + on-demand 3-AI analysis (`/analisa <symbol>`) + `/status` `/posisi` `/scan` `/closeall` `/news`. Fast POST polling via Vercel proxy.
9. **Peak-Aware Time-Decay Stagnation Exit + Pre-Rollover Shield**: Perlindungan modal dari time-decay & lonjakan spread rollover.
10. **Dynamic Volatility Scaling (ATR Percentile)**: Low `0.75x` / Normal `1.00x` / High `1.15x` sizing. Injeksi Peak MFE ke AI Re-evaluator.
11. **Ultra-Compact Chain-of-Thought JSON Protocol**: Locked CoT sequence `trend $\rightarrow$ velocity $\rightarrow$ rr_valid $\rightarrow$ signal $\rightarrow$ confidence`. Output ~35 token, respons <5 detik/simbol.
12. **Multi-Year FBS Historical Dataset & SMC Validation**: 88 file (3.788.000+ bar, 22 simbol). Validasi 396.183 trade: H1 > M30 (+22.8% PF). Mean Reversion + SMC CHoCH/Displacement dominan intraday; Breakout toksik (PF 0.20).
13. **Multi-Decade H4 & D1 Macro Expansion**: XAU H4 PF 1.64 (+$36.8k, 30.5 thn), D1 PF 2.50 (+$29.5k, 16.6 thn). Hukum fraktal: **Macro Expands (Breakout) vs Micro Mean-Reverts**.
14. **Master Quant Dossier HTML (Book-Grade)**: `docs/report.html` & `docs/technical_specification.html` (Buku putih 15 Bab + visual 2-stage screener + atlas DNA 22 simbol).
15. **2-Pass Sequential Cross-Examination 3-LLM Jury + Hard Risk Veto**: Pass 1 paralel OpenAI (Chief Quantitative Macro Strategist) + Gemini (Master Price Action Tactician) (~3s). Pass 2 DeepSeek CRO Master Arbiter (~1.5s) mengaudit M5 micro-tape (anti-waterfall/anti-spike) + arbitrase paket utuh (Atomic Package Integrity Rule anti-frankenstein R:R). Total <5.5s. Veto flags: `COUNTER_TREND_MOMENTUM`, `HIGH_IMPACT_NEWS`, `LIQUIDITY_TRAP`, `SPREAD_SPIKE`, `FALLING_KNIFE_WATERFALL`, `UNMITIGATED_IMPULSE_CHASE`, `SYSTEMIC_CURRENCY_DUMP`.
16. **LuxAlgo SMC + Liquidity Map** (`src/indicators/lux_smc.py`): Porting 1:1 LuxAlgo Pine v5 → Python. Unmitigated OB, FVG, Strong Low/High, EQH/EQL. Injeksi ke dossier prompt agar SL presisi di belakang OB, TP di FVG/Weak High.
17. **Hourly SMC Radar & Market Pulse Telegram Digest**: Recap tiap jam (pergantian jam WIB) — Market Compass 26 pair FX (BULL/BEAR/SIDEWAYS), Dealing Range SMC (Top Discount/Premium watch), portofolio MT5 (floating/realized P/L).
18. **Strict HTF Execution Hierarchy (H1 & M30 only)**: Stage 1 Radar HANYA scan H1 & M30. M5 DILARANG trigger eksekusi langsung (anti overtrading + fee churn).
19. **M5 Candlestick Micro-Microscope** (Pass 2 audit eksklusif): 25 candle M5 live → DeepSeek CRO deteksi falling knife.
20. **Unanimous 3/3 High Confidence Split (+25% Boost)**: 3 AI sepakat $\ge 75\%$ confidence + $\ge 2$ slot MT5 → eksekusi 2 posisi @ $0.625\times$ base lot (Pos #1 target standar, Pos #2 target extended 1.2× TP2 + trailing).
21. **Multi-Touch Cluster Breakout & Delayed Retest** (M5 — 27 Agustus): Level cluster disentuh $\ge 2 \times$ + tembus candle momentum $\ge 55\%$ body → Pending Limit Order saat retest (delay 3–4 bar). Anti False Sweep. Validasi 10.7 tahun FBS (23.173 trade, PF 1.11).
22. **Boitoki CSM + Prompt Relative Flow** (H1 — 27 Agustus): Porting 1:1 algoritma 7 USD Majors. Eliminasi Macro Bias Trap. Injeksi blok `GLOBAL CURRENCY STRENGTH MATRIX` (8-currency ranking, Net Delta). Validasi 31.161 trade: $-7.333\text{R} \rightarrow +7.333\text{R}$ (+92% loss dipangkas).
23. **2-Stage Dynamic Trailing Stop**: Stage 1 (Swing Breathing 65–90% TP) $0.75\times\text{ATR H1}$ floor 80 pts. Stage 2 (Terminal Lock $\ge$90% TP) $0.50\times\text{ATR M30}$ floor 30 pts.
24. **Fixed Range Volume Profile (FRVP) + Institutional Confluence** (28 Agustus): SMC + FRVP sinergi memangkas 59.2% trade noise + EV +104% R. Pair bintang: EURCHF PF 1.79, GBPCHF PF 1.53.
25. **Wave State Machine + 4-Layer Permission Engine** (H1 — 28 Agustus): Pemisahan Direction (D1+H4) vs Trade Permission (H1 Wave + CSM + Event). Eliminasi Impulse Chase (PF 0.52) + Falling Knife (PF 0.97). Hanya `MATURE_BASING` (PF 1.30) + `BASE_RECLAIM` (PF 1.42) di zona diskon ($\le 0.50$, Golden Pocket $\le 0.382$) yang boleh trade. *— Model FSM Wave State lama ini sejak 1 September telah dilebur ke MSE Barrier State Machine + mapping action tier 5-Tier (`FULL_ALLOW→GO/ARM` dst., lihat entri 40 & 48). Tidak ada modul `wave_state.py` terpisah di kode aktif; permission dihitung di `market_scanner.py` dari action tier MSE.*
26. **Anti-Wick Buffer + Structural SL Anchoring** (M30 — 28 Agustus): SL jangkar di balik support/OB fisik + Anti-Wick Buffer $0.35\times\text{ATR} + \text{Spread}$. Win Rate Trend-Aligned Retest naik ke 57.2–58.1% (PF 1.17–1.23).
27. **Real Candlestick Wick Measurement + Anti-Waterfall Universal Sweep** (28 Agustus): Ganti static `rejection_wick_ratio` dengan real `classify_candle`. Filter Anti-Breakdown Waterfall di `UNIVERSAL_LIQUIDITY_SWEEP` — larang BUY jika marubozu merah tanpa sumbu bawah.
28. **Dynamic MT5 Point Resolution + Live Economic News + FRVP Injection** (28 Agustus): `_get_point(sym)` ambil dari `symbol_info.point` MT5 (fallback JPY 0.001, XAU/BTC 0.01, FX 0.00001). Live fetch berita TradingView/Investing.com di `build_high_density_dossier_prompt`. FRVP POC/VAL/VAH diinjeksi ke 8 kandidat radar.
29. **Telegram Interactive `/news` + Cyberpunk Bento HUD News Ticker** (28 Agustus): Command `/news` (alias `/kalender`, `/berita`, `/event`) + live ticker di Bento HUD Tile 3 & 4 dengan countdown rilis.
30. **Intraday Entry-Anchored SL/TP + Anti-Wick Padding + Safety Ceiling** (28 Agustus): SL/TP intraday berbasis harga entri + Anti-Wick Padding +15 pts (1.5 pips). Hard Intraday Ceiling di `_apply_sltp_rules` (FX max SL = $\min(2.0\times\text{ATR}, 160\text{ pts})$; Gold max SL = $2.5\times\text{ATR}$).
31. **4-Layer Trend-Aligned Permission Engine + NZD Alpha Expansion** (28 Agustus): Direction FSM (D1+H4) → Phase FSM (H1 Wave) → CSM Gauge → Permission Matrix. Prinsip `BUY LOCKED != SELL ENABLED`. Delayed Limit Retest $0.20\times\text{ATR}$ + SL anchor $0.35\times\text{ATR} + \text{Spread}$. Universe 26 simbol FX dengan 6 NZD pair (PF 1.34). 93.3% hari ada peluang.
32. **Mechanism 3 (M6) HTF Weekly Wall Reversal & Foothold Targeting** (28 Agustus): Ganti NY ADR Reversal (-3.637,3R) dengan HTF_WEEKLY_WALL_REVERSAL (tabrak dinding H4/D1/W1 → foothold 50% Equilibrium). Validasi 16.011 trade, Net +$586,1R.
33. **Quant Research V3: 4-Dimensional Adaptive Market State + Conditional Timing** (29 Agustus): Hapus mitos 4-candle exhaustion ($P(\text{Rev}|n=4)=53.19\%$, hanya +2.3% koin acak). Dim 1 Direction Identity (False Flip 70.86% → 12.61%, persistence 41.3 bar). Dim 2 Anatomy Type A vs Type B. Dim 3 CSM Pressure (aligned +68.44% continuation, opposed 64.04% fail). Dim 4 Event Layer (Displacement $P(\text{Cont})=75.22\%$, EV +0.166R/trade, PF 1.14).
34. **Macro Psychological Levels + Station-to-Station Corridor Delivery Engine** (29 Agustus): 3 Trigger Fisik Zona Dinamis ($\pm 0.35\times\text{ATR}$): angka bulat psikologis (1.2000, 160.00, $2500), sapuan EQH/EQL, Fib 50–61.8% Golden Pocket. M3 Compass Navigator (GPS koridor) + Trio H1 Executor (M1 Sweep, M2 Pullback, M4 Retest). 7 pair bintang: EURJPY +371R, EURUSD +297.8R, AUDUSD +233.9R, USDJPY +218.3R, XAUUSD +165.9R, EURAUD +64.1R, GBPUSD +27.3R. Total +$1.378,3R Net Profit.
35. **Pure Quant Hierarchical Top-Down Macro Strategic Engine (6-TF Native Sockets)** (29 Agustus): Integrasi komputasi kuantitatif 6 timeframe asli MT5 (`MN1` 50 bar/4.1 thn, `W1` 100 bar, `D1` 350 bar, `H4` 400 bar, `H1` 250 bar, `M30` 200 bar) dengan Dual-Grid Psychological Stations (Major 100-pip vs Sub-Stations 50-pip), Anatomi ZONA struktural (Proximal/Distal Bands untuk SBR/RBS/DBD/RBR), Station Collision & Dual-Reaction Protocols (Skenario A Reversal Fade vs Skenario B Breakout Upgrade), dan Wyckoff Stop-Hunt Dip Delivery (SL ketat 12–25 pips $\le 160\text{ pts}$ + TP1 50% & TP2 Macro Target). Komputasi $<50\text{ ms per pair}$, 0 Token API. Telegram on-demand `/macro <symbol>`.
36. **Universal 8-Currency Basket Circuit Breaker & Calibrated Flow Gates** (29 Agustus): Dual-Horizon Basket Flow weighting (H1 40% + M15 60%) mencakup seluruh 8 mata uang utama (USD, EUR, GBP, JPY, CHF, AUD, CAD, NZD) dengan kalibrasi threshold empiris $\pm 20.0$ (Surge/Dump Systemic) dan $\pm 18.0$ (Relative Delta Spread $|\Delta|$). Otomatis hard lock mutlak posisi counter-trend saat Base/Quote mengalami systemic dump/surge serta lock posisi saat Relative Delta Spread $|\Delta| \ge 18.0$. Sinergi MSE Hard Stage 1 Gate memblokir setup berlawanan arah koridor makro (`strat_dir.primary_execution_directive` & `strat_dir.forbidden_traps`) sebelum pemanggilan Stage 2 LLM Jury.
37. **End-to-End Live Multi-LLM Replay Validation (27–28 Agustus 2026)** (29 Agustus): Validasi live audit 3-LLM Jury (OpenAI o4-mini, Gemini 3.1-Flash, DeepSeek V4-Flash CRO) pada data historis 11 pair akun nyata. Hasil: GBPUSD berbalik dari rugi -$82.69 di akun riil menjadi **+$135.00 (+2.25 R, 3/3 Win)**, EURUSD +2.00 R, GBPCHF +2.15 R, EURCHF +0.30 R. Total net return terverifikasi **+2.85 R (+$171.00 pada equity $6,000)** dengan Win Rate 58.8% dan profit bersih melonjak +135% vs riwayat live akun riil.
38. **Hierarchical W1 + D1 Multi-Timeframe Order Blocks & Dynamic Contingency Roadmap** (30 Agustus): Integrasi ekstraksi LuxSMC multi-timeframe D1 & W1 (`smc_w1` + `smc_d1`) dengan kalkulasi titik tengah (*Core Midpoint Equilibrium / FRVP POC*). Penyusunan *Contingency Macro Roadmap* logis seberang titik invalidasi: jika breakdown maka memburu lantai Demand D1/W1 terdekat (e.g. USDCAD `1.37043`, GBPCHF `1.08882`), jika breakout memburu atap Supply D1/W1 terdekat (e.g. EURUSD `1.17261`, GBPUSD `1.37000`). Eliminasi anomali directional target inversion dan loncatan target multi-ratusan pips.
39. **Audit Live Spread Weekend 26 Simbol & Kalibrasi Reload Zone ($0.55\times\text{ATR H1}$)** (30 Agustus): Audit komparatif spread penutupan pasar weekend di akun live MT5 (lonjakan 1.0x s/d 10.1x pada GBPNZD 18.3p, CHFJPY 13.8p, EURNZD 12.3p vs EURUSD/USDCAD 0.7-0.9p). Rekalibrasi matematis lebar *Reload Zone* menjadi $0.55\times\text{ATR H1}$ dengan safety floor per-aset (min 6p FX, 10p JPY, $120 BTC) guna menjamin ruang tangkap limit order optimal pada hari kerja normal.
40. **Probabilistic Macro Strategic Engine & 5-Tier Operational Action Matrix** (30 Agustus):
    - **Pemisahan Peran Arsitektural**: MSE = Kompas Arah, Koridor, Invalidation, & Macro Bias Continuous Score ($\in [-1.0, +1.0]$); SMC = Trigger SFP, Liquidity Sweep, & Structure Event; FRVP = Disambiguator Lelang (`ACCEPTANCE` vs `REJECTION`) + *Thin-Volume Danger* filter (cap rating di Grade B jika berada di Low Volume Node / vacuum).
    - **5-Tier Operational Action Matrix & End-to-End Risk Modifiers**:
      1. `FULL_ALLOW`: Setup searah makro ($|\text{score}| \ge 0.35$), ukuran penuh $100\%$ lot, target koridor penuh TP1 + TP2 runner (+25% boost multi-position jika 3 AI unanimous $\ge 75\%$).
      2. `REDUCED_CONFIDENCE`: Setup valid saat makro netral/moderat ($-0.25 \le \text{score} \le +0.35$), **pengali risiko numerik $0.75\times$ lot size** di `risk_engine.py`, dan pembatasan $\text{TP} \le 2.00 \times \text{SL}$ di `consensus.py`.
      3. `TP1_ONLY_SCALP`: Setup counter-trend berkualitas tinggi (M1 Universal Liquidity Sweep / SFP) melawan makro moderat ($|\text{score}| \le 0.70$). Wajib sweep bersih + reclaim + wick $\ge 35\%$ + ruang ke TP1 $\ge 1.25\times\text{SL}$ + zero hard trap. Pembatasan $\text{TP} \le 1.50 \times \text{SL}$ dan **larangan keras 2-posisi split** di `main.py` (**100% posisi ditutup di TP1 tunggal**).
      4. `WATCH_ONLY`: Harga di dalam Reload Zone namun trigger belum terkonfirmasi $\rightarrow$ monitor saja, 0 order MT5.
      5. `HARD_BLOCK`: Tabrak hard trap (jarak ke atap/lantai $< 1.0\times\text{ATR H1}$), jebol invalidasi makro, atau waterfall 25-candle M5 $\rightarrow$ hard lock mutlak (0 token LLM).
    - **Smart 60-Second TTL Cache & Direct Fast Telegram**: Cache memori sub-detik untuk komputasi intraday $\le\text{H4}$ serta pengiriman format quant instan (<100ms, 0 token) di Telegram `/macro`.
41. **Real-Time State Transition Hook & Smart High-Impact Telegram Alert Gate** (30 Agustus):
    - **Live State Change Tracker**: Di setiap siklus scan 60 detik (`main.py`), sistem membandingkan status Permission (`ARM/WAIT/GO/LOCK`) dan Mandat Makro tiap simbol terhadap state sebelumnya.
    - **Auto Re-render Bento Box Terminal**: Jika terjadi transisi state pada pair apa pun (misal: `WAIT -> ARMED` atau `BEARISH_PULLBACK -> BULLISH_EXPANSION`), terminal langsung mencetak log transisi `[STATE TRANSITION DETECTED]` dan me-render ulang Bento Box HUD seketika tanpa menunggu pergantian jam.
    - **Smart High-Impact Telegram Gate**: Menghindari spam 26 pair di HP dengan HANYA mengirim notifikasi Telegram pada status kritis **`Permission GO`** (`alert_radar_go_transition` saat reclaim valid terkonfirmasi).
42. **Full MSE On-Demand Integration & Single OpenAI o4-mini Dedicated Engine** (30 Agustus):
    - **Total Deletion of `macro_analyst.py`**: Modul usang `src/analytics/macro_analyst.py` dihapus total dari arsitektur.
    - **Single OpenAI o4-mini On-Demand Engine**: Mode On-Demand Telegram (`/analisa <symbol>`) menggunakan model tunggal OpenAI `o4-mini` yang diperkaya konteks kuantitatif MSE 6-TF lengkap (hemat 66% token API dan respon super cepat <1.5s).
    - **Prompt Redundancy Elimination**: Menghapus duplikasi level stasiun (`m3_compass_str` saat MSE aktif), menghapus teks narasi penjelasan macro lama, dan menyatukan peringatan unit broker poin di `llm_client.py` $\rightarrow$ menghemat ~220 token per cycle & memangkas latensi respon ~1 detik.
43. **Codebase Streamlining & Indicator Consolidation** (30 Agustus):
    - **Dead Code Cleanup**: Menghapus `analyze_fundamentals()` dari `llm_client.py`.
    - **Indicator Consolidation**: Menggabungkan `squeeze_momentum.py` langsung ke dalam `wave_regime.py` dan memindahkan file catatan referensi PineScript (`.txt`) ke `docs/archive/` sehingga direktori `src/indicators/` murni berisi 7 file Python aktif.
44. **Apex Paragon Macro Fundamental Engine & MSE Sockets Convergence** (30 Agustus):
    - **Dual-Source Provider**: ForexFactory Official JSON CDN (Primary) + TradingView API (Fallback) + Deteksi Hari Libur Bank (*Bank Holiday Guard*).
    - **Tiered Half-Life Exponential Decay Engine**: Peluruhan eksponensial dampak katalis ekonomi ($4\text{h} / 12\text{h} / 36\text{h}$) tanpa batasan *cliff* biner artifisial.
    - **8-Currency Composite Fundamental Scorecard**: Skor dinamis $[-1.00, +1.00]$ dan divergensi *Carry Spread* untuk 8 mata uang utama global.
    - **4-Tier Setup Quality & Dynamic Sizing System**: GRADE S (Super Convergence), GRADE A+ (High Conviction), GRADE A (Pure Technical Flat), GRADE B (Defensive $0.50\times$ lot).
    - **7 Master Institutional Hard Risk Veto Flags**: `COUNTER_TREND_MOMENTUM`, `LIQUIDITY_TRAP`, `IMPULSE_CHASE`, `SYSTEMIC_CURRENCY_DUMP`, `HIGH_IMPACT_NEWS`, `CURRENCY_CONFLICT` (Grade B), `MACRO_HEADWIND` (Grade B).
    - **Telegram 2-Way Interactive Controller**: Fitur `/fundamental` & `/fund <pair>` menampilkan heatmap 8 mata uang dan rincian katalis.
221:45. **Hybrid Confluence Framework, Symmetrical Wave State & Risk-Weighted Slot Allocation** (30 Agustus):
    - **Symmetrical Dual-Directional Wave State Engine**: Menghapus total bias long-only/istilah basi ritel. BUY beroperasi di Lantai Diskon (`EXPANSION_WAIT_BULL` -> `WATERFALL_LOCK` -> `DISCOUNT_RELOAD_ARMED` -> `DEMAND_REACTION_GO`); SELL beroperasi di Atap SBR (`EXPANSION_WAIT_BEAR` -> `VERTICAL_SPIKE_LOCK` -> `PREMIUM_RELOAD_ARMED` -> `SUPPLY_REACTION_GO`). *— Iterasi FSM simetris ini adalah bagian dari model Wave State lama yang kemudian dilebur ke MSE action tier 5-Tier (lihat anotasi entri 25 + entri 48).*
    - **Kuantifikasi Konflik**: Severe Conflict ($|S| \ge 0.50$ di kedua sisi / Carry Headwind $\ge 3.0\%$) memicu `REJECT_VETO` (Hard Veto); Mild Conflict ($|S| < 0.50$) memicu `GRADE_B` ($0.50\times$ Lot / TP1 Scalp).
    - **Hybrid Confluence Targeting**: Target TP selalu *snapped* ke level stasiun fisik MSE terdekat di dalam amplop ATR Grade + *Front-Running Pad ($0.15\times\text{ATR} + \text{Spread}$)*.
    - **Milestone-Driven Data-Backed BEP & Trailing**: BEP Grade S ditunda ke 65-70% TP + Trailing lebar $1.25\times\text{ATR H1}$ (floor 120 pts FX) + Imun dari Time-Decay Stagnation 4 jam; Grade B BEP cepat 35-40% TP + Trailing $0.40\times\text{ATR M30}$.
    - **Risk-Weighted Slot Allocation dengan 5 Lapisan Kontrol Portofolio**:
      1. Kuota At-Risk $\le 6$ posisi ($SL < Entry$).
      2. Free Runner (TP1 + BEP / Risk $\$0.00$) bebas kuota risk.
      3. Plafon Absolut Akun MT5 $\le 8$ total tiket terbuka.
      4. Free Margin Buffer $\ge 60\%$.
      5. Konsentrasi Keranjang Valas $\le 3$ posisi per mata uang (USD, EUR, JPY, dll).
      6. Strict 1-Trade per Symbol.
46. **Stage 1 Mechanical Action Zone Gating & Pure Physical Level Anchoring** (31 Agustus):
    - **Mechanical `WATCH_ONLY` Hard Gate**: Simbol yang berstatus `WATCH_ONLY` dari MSE (misal di area Mid-Chamber 30–70% Dealing Range tanpa konfluensi batas) langsung di-drop total (`HARD_BLOCK` di `_is_direction_allowed()`) pada Stage 1 Fast Radar (0 token).
    - **Eliminasi Total Formula Sintetis `mid - 0.20*ATR`**: Menghapus seluruh formula floating/buatan di M1 dan M2.
    - **M2 Physical Action Zone Requirement**: M2 (`TREND_ALIGNED_PULLBACK`) wajib memvalidasi sentuhan fisik Action Zone $F_1$ Floor (BUY) atau $C_1$ Ceiling (SELL) dengan toleransi $\le 0.20\times\text{ATR}$ + konfirmasi penahanan support/rejection wick. Penempatan entry limit dijangkarkan 100% pada level fisik struktural ($F_1/C_1/\text{RBS}/\text{SBR}$).
    - **M1 Pure Swept Level Retest Anchor**: Entry limit M1 (`UNIVERSAL_LIQUIDITY_SWEEP`) dijangkarkan murni pada level fisik yang baru saja disapu (`ref_bot` / `ref_top`), tanpa rumus jarak sintetis.
47. **H4 SMC Dynamic Consolidation Flag Gating & Mid-Chamber Protection** (31 Agustus 2026):
    - **120-Bar H4 LuxSMC Engine**: Evaluasi dinamis 120 bar H4 mendeteksi pola konvergensi flag/triangle (`is_triangle_compression` via Lower Highs + Higher Lows) dan stationary ranging box (`is_ranging_box` via $\le 1$ BOS atau dealing range pos $30\% - 70\%$).
    - **Hard Block M2 di Pasar Ranging**: M2 (`TREND_ALIGNED_PULLBACK`) dikunci total (**0 token, otomatis dilewati**) saat simbol berstatus `is_h4_ranging` atau `is_h4_flag_triangle` guna mencegah open posisi ceroboh di area konsolidasi (kasus EURGBP).
    - **Mid-Chamber Inaction Zone Protection ($25\% - 75\%$)**: Area tengah $25\% - 75\%$ dealing range H4 dipaksa berstatus `WATCH_ONLY` di MSE dan diblokir dari seluruh entry pullback.
    - **Strict Active Zone Enforcements**: M2 Pullback BUY hanya diizinkan di $\le 45\%$ (Discount) dan SELL di $\ge 55\%$ (Premium) pada tren ekspansi; M1 Universal Sweep diperketat hanya di Extreme Active Zone ($\le 25\%$ BUY / $\ge 75\%$ SELL).
48. **Unified Stage 1 Macro Direction & CSM Flow Gate Refactoring** (1 September 2026):
    - **Konsolidasi Pengecekan Arah Makro**: Menyatukan pengecekan *Macro Bias Alignment*, *CSM Flow Opposition* (Net Delta $\le -1.0$ BUY / $\ge +1.0$ SELL), dan *Systemic Basket Lock* ke dalam satu gerbang terpadu `_is_direction_allowed()`.
    - **Eliminasi Redundansi Gate C M1 Sweep**: Menghapus `Gate C (Macro Asymmetry)` dari `evaluate_universal_sweep_gates()`, memfokuskan M1 murni pada *Gate A (Area of Value Anchor)* dan *Gate B (Anti-Ceiling/Floor Vector Memory)* dengan zero-conflict log.
49. **Adaptive Multi-Scale Reaction Engine & Dynamic Variable-Length Layer Matrix** (1 September 2026):
    - **Dynamic Variable-Length Layers ($N \ge 1$, Zero Artificial Padding)**: Menghapus batas kaku 4-tier dan padding level boneka (`MACRO_EXT_FALLBACK`). Seluruh lapisan support ($F_1 \dots F_N$) dan resistance ($C_1 \dots C_M$) diekstrak murni dinamis berdasarkan formasi fisik pasar via toleransi adaptif $\Delta_{\text{tol}} = \max(0.30 \times \text{ATR}_{\text{H1}}, 0.25 \times \text{Step}_{\text{Atlas}}, 5 \times \text{Point})$.
    - **3-Grade Reaction Scaling**: Setiap barrier diklasifikasikan secara matematis ke dalam `GRADE_1_MICRO` (Asian/Intraday, $S < 3.5$), `GRADE_2_INTERMEDIATE` (H4/FRVP/Psych, $3.5 \le S < 7.0$), atau `GRADE_3_MACRO` (D1/W1 SBR-RBS, Weekly Wall, Annual Extremes, $S \ge 7.0$).
    - **Calibrated Breakout & Sweep Tolerances**: Toleransi penembusan momentum ($\Delta_{\text{disp}} = 0.15 / 0.35 / 0.60 \times \text{ATR}_{\text{H1}}$) dan toleransi sumbu M1 Sweep ($\text{Wick Band} = 0.20 / 0.35 / 0.50 \times \text{ATR}_{\text{H1}}$) diatur proporsional sesuai grade barrier.
    - **Target Scaling**: Grade 1 Sweep menargetkan quick mean-reversion ke 50% Intraday Eq / H1 EMA20 ($1.25R$); Grade 3 Macro Sweep/Breakout menargetkan ekspansi koridor penuh menuju $C_{\text{deep}} / F_{\text{deep}}$ ($2.5 - 3.5R+$).
    - **Multi-Scale Context Injection di LLM**: Prompt High-Density Dossier Stage 2 menyuntikkan matriks hierarki lantai dan plafon berjenjang lengkap dengan grade reaksi, memperkuat validasi 3-LLM Consensus Jury.
50. **Hierarchical Synergy, Next-Structure Anchoring ($C_1/F_1$) & Bounded Micro-Precision Refinement** (1 September 2026):
    - **Decoupled Architecture**: Pemisahan peran fundamental antara pure quant engine dan multi-LLM jury. Pure Quant MSE mengunci koordinat baseline SL, TP, dan volume lot sizing, sementara 3 LLM (OpenAI, Gemini, DeepSeek) difokuskan pada Price Action M15/M5 Microscope, timing eksekusi, deteksi news trap, dan veto risiko (CRO).
    - **Next-Structure TP Anchoring ($C_1$ / $F_1$)**: Mengunci TP1 persis di depan dinding fisik terdekat ($C_1$ untuk BUY, $F_1$ untuk SELL) dikurangi *front-running pad* ($0.15\times\text{ATR} + \text{Spread}$). Mengeliminasi fenomena klasik TP kejauhan yang berakhir pada penutupan prematur oleh trailing stop / BEP.
    - **Bounded Micro-Precision Refinement (Market Orders)**: LLM diberikan kewenangan untuk menyempurnakan level SL dan TP pada order market berdasarkan sumbu mikro M5/M15 sebesar maksimal $\Delta_{\text{micro\_bound}} = \max(0.25 \times \text{ATR}_{\text{H1}}, 30\text{ pts})$ ($\approx \pm 3 - 5\text{ pips}$). Deviasi di luar batas ini otomatis di-clamp kembali ke jangkar fisik MSE (`Quant Structural Anchor`).
    - **Non-Coercive Limit Order Optimization**: Jika LLM mengamati R:R ke struktur berikutnya terlalu sempit di harga pasar saat ini atau menginginkan harga yang lebih optimal, prompt memandu LLM secara non-koersif untuk memilih **Pending Limit Order** (`buy_limit` / `sell_limit`) di level diskon/retest pilihan daripada memaksakan entry market.
51. **80% Confidence Split Elevation & M2 Inaction Dead Zone Alignment** (1 September 2026):
    - **Penaikan Ambang Batas Split 2 Posisi ke 80%**: Mengubah parameter ambang batas pembukaan 2 posisi (+25% boost) dari $75\%$ menjadi $\ge 80\%$ di `.env`, `config.py`, dan `main.py`, memastikan eksposur ganda hanya terpicu saat konsensus 3 AI benar-benar bulat dan berada pada tingkat keyakinan institusional prima.
    - **Penyelarasan Mid-Chamber Dead Zone M2**: Mengoreksi `is_in_mid_chamber` pada `market_scanner.py` menjadi $0.45 \le \text{pos} \le 0.55$ (area netral equilibrium sejati). Menghilangkan pemblokiran tidak sengaja pada area diskon sehat $25\% - 45\%$ untuk M2 BUY dan area premium $55\% - 75\%$ untuk M2 SELL.
52. **M15/M5 Micro Candlestick Microscope & Macro Token Streamlining** (1 September 2026):
    - **Eliminasi Candle Redundan D1/H4/H1**: Deretan teks OHLC mentah D1, H4, dan H1 dihapus dari prompt karena seluruh struktur makro telah dirangkum matang oleh Pure Quant MSE di Section 4 (hemat $\approx 500$ token).
    - **Mikroskop M15 & M5 Murni**: Umpan candle live difokuskan pada 16 bar M15 ($\approx 4\text{ jam}$) untuk dinamika intrahari dan 24 bar M5 ($\approx 2\text{ jam}$) untuk mikroskop sumbu presisi eksekusi, menghasilkan prompt yang lebih ramping, cepat (<3s), dan tajam.
53. **GATE C: Anti-Expansion Momentum Vector in Universal Sweep** (1 September 2026):
    - **Penyelarasan Jarak Dinding Makro Sejati ($C_1 / F_1$)**: Menggantikan penghitungan jarak atap/lantai statis PWH/PWL menjadi dinding fisik sejati $C_1$ (`macro.get('immediate_ceiling_c1')`) dan $F_1$ (`macro.get('immediate_floor_f1')`).
    - **Larangan Menghadang Kereta Cepat**: Pada fungsi `evaluate_universal_sweep_gates()`, jika tren makro H4/D1 berstatus `BULLISH_EXPANSION` dan jarak menuju plafon makro $C_1$ masih terbuka lebar ($> 0.35\times\text{ATR}_{\text{H1}}$), sistem **100% MEMBLOKIR entri SELL** pada sapuan PDH/Asian High. Sapuan tersebut secara kuantitatif diklasifikasikan sebagai *Breakout Continuation*, bukan *reversal*. Symmetrically, larangan BUY diaktifkan saat tren `BEARISH_EXPANSION` menuju lantai $F_1$.
54. **Overhaul & Penyelarasan Konfluensi Trio Eksekusi (M1, M2, M3)** (1 September 2026):
    - **M1 Wall Rank Gate & Strict Reclaim**: Di pasar yang sedang trending, sapuan intrahari (Asian High/PDH) **hanya boleh di-fade jika bertabrakan langsung dengan Dinding Makro Sejati $C_1/F_1$ ber-Grade $\ge G_2$ (Intermediate / Macro Fortress)**; level $G_1$ (Micro) 100% diblokir. Harga live wajib sudah reclaim ke dalam (`mid < ref_top` / `mid > ref_bot`).
    - **M2 Dynamic EMA Corridor**: Variabel `ema20` dan `ema50` H1 diaktifkan sebagai koridor nilai dinamis. Pullback BUY wajib bertahan di atas $\text{EMA50} - 0.15\times\text{ATR}$ dan tidak mengejar harga di atas $\text{EMA20} + 0.25\times\text{ATR}$. Pullback SELL wajib bertahan di bawah $\text{EMA50} + 0.15\times\text{ATR}$ dan di atas $\text{EMA20} - 0.25\times\text{ATR}$.
    - **M3 Confirmed Closed Bar Outside**: Retest pada dinding $C_1/F_1$ hanya disiapkan jika **candle sebelumnya terkonfirmasi close di luar dinding** dengan impuls body $\ge 40\%$, membuktikan dinding telah resmi jebol sebelum di-retest dari sisi luar (New RBS/SBR).
55. **Dual-Basket Confluence & Dispersion Matrix Engine** (2 September 2026):
    - **Dual-Basket Structural Mapping**: Mengukur deviasi standar posisi relatif ($\sigma_X$ dan $\sigma_Y$) yang dinormalisasi ke skala $[0.0, 1.0]$ pada 26 simbol FX terkurasi ($N \ge 6$ pair per basket).
    - **Deterministic Decision Hierarchy**: Matriks keputusan 4-Tier mutual exclusive (`SURGE_OVERRIDE_Y/X`, `SYSTEMIC_EXPANSION`, `PURE_CATCHUP_LEAD_LAG`, `NEUTRAL_ROTATION`).
    - **Strict Leader Wall Hit Anchoring**: `(pos >= 0.90 or pos <= 0.10) AND (dist <= 0.35 ATR)`.
    - **Zero-Risk Informational Ingestion**: Mode shadow metric diinjeksi ke Stage 2 LLM Dossier prompt (`llm_client.py`), Stage 1 Radar hard gating (`market_scanner.py`) 100% tidak disentuh.
56. **Multi-Timeframe Candlestick Spectrum Distribution Across 3-LLM Jury** (2 September 2026):
    - **OpenAI o4-mini (Macro)**: Injeksi Tape D1 (5 bar) dan Tape H4 (8 bar).
    - **Gemini 3.1-Flash (Price Action)**: Injeksi Tape M1 (15 bar), M5 (24 bar), M15 (12 bar), dan H1 (6 bar).
    - **DeepSeek V4-Flash (CRO Arbiter)**: Injeksi Tape H4 (6 bar), H1 (6 bar), dan M5 (24 bar).
57. **Anti-FOMO Execution Directive & Hard Pending Limit Intercept** (2 September 2026):
    - Penembusan Breakout di area ekstrem (Dealing Range $\ge 85\%$ BUY / $\le 15\%$ SELL) **dilarang keras** dieksekusi via Market Order; wajib menggunakan `buy_limit` / `sell_limit` di jangkar retest sejati ($F_1 / RBS$ atau $C_1 / SBR$).
    - `consensus.py` otomatis mengonversi order market menjadi pending limit order jika kandidat berada di area ekstrem.
58. **Dynamic Real-Time Economic Calendar Ingestion & Exported Markdown Dossiers** (2 September 2026):
    - Integrasi otomatis `_get_symbol_news_context()` untuk menarik live event berdampak tinggi (BOC Rate Statement, FOMC, ECB, NFP) ke seluruh 3 model AI.
    - Ekspor verbatim prompt lengkap ke `docs/prompt/` (`openai_prompt.md`, `gemini_prompt.md`, `deepseek_prompt.md`).
59. **Zone Confluence Engine (ZCE) — RFC 11, Fase 1–2 + Task #7** (2 September 2026):
    - **Engine baru `src/analytics/zone_confluence_engine.py`** (default `ZCE_ENABLED=false`, `ZCE_MODE=shadow`): peta zona 6-TF × multi-horizon (M30 50/150, H1 50/100/150/250, H4 50/100/150, D1 50/100/150/250, W1 50/100, MN1 50), skor J1 = bobot (kind × tf) unik × boost horizon (1.0–1.35) × freshness, grade G3 ≥6.5 / G2 ≥3.5, klaster COLD (>21 hari) & VACUUM (>60 hari, >1.0×ATR), wall elect F1/C1 (chamber ≥ 0.60×ATR / 8 pips), scale ladder + `SCALE_CONFLICT`, readiness score, method suggestion.
    - **Hook MSE zero-break**: `compute_directive(..., zce_walls=...)` menimpa C1/F1/deep/layered SEBELUM Chamber Metrics; tanpa `zce_walls` → perilaku MSE identik. Parity live EURUSD: override applied = True.
    - **Task #7 SL/TP** (`consensus.py`, flag-gated): `SL_MAX_ATR_MULT` configurable (default 2.5) menggantikan hardcode ceiling 2.5×ATR; mode legacy/full → SL anchor > ceiling di-**skip** (`ANCHOR_TOO_WIDE`) bukan clamp, ATR gagal di-**reject** (`ATR_UNAVAILABLE`) bukan fallback statis. Floor ATR & R:R invariant.
    - **Bug fix**: konversi pips `8×10^(-digits+3)` → `8×10^(-digits+1)` (5-digit 0.0008 = 8 pips, bukan 800 pips). Test: `test_zone_confluence_engine.py` 10/10 + `test_zce_sltp_anchor.py` 4/4.
60. **Aktivasi ZCE Mode FULL (Test Akun Live Cent)** (2 September 2026):
    - `.env`: `ZCE_ENABLED=true`, `ZCE_MODE=full` — dinding C1/F1 dari peta zona 6-TF menggantikan dinding internal MSE (bukan shadow). Berlaku untuk test di akun live cent; logika produksi akun live utama tidak diubah.
    - Jalur ZCE di `consensus.py` kini aktif: SL anchor > ceiling → `ANCHOR_TOO_WIDE` (skip), ATR gagal → `ATR_UNAVAILABLE` (reject), fallback statis nonaktif.
    - Test legacy yang menguji jalur non-ZCE di-patch `ZCE_ENABLED=False`/`ZCE_MODE=shadow` agar deterministik (`test_confluence...` & `test_market_scanner...`). Suite: 86 passed, 6 failed pre-existing.
61. **Fix Koneksi ZCE→Radar: Stale Cache + Resync Deep Target** (2 September 2026):
    - **Patch #1 Stale Cache Disconnect** (`market_scanner.py` + `config.py` + `.env`): `update_macro_context` ganti hour-gate → **elapsed-gate** `_zce_refresh_due_seconds()` (900s saat ZCE legacy/full, `MACRO_STRATEGIC_REFRESH_SECONDS` default). `_build_single_macro_context` kini **compute inline peta ZCE** bila belum ada di `_zce_maps` → macro_cache TIDAK PERNAH dibangun tanpa dinding ZCE (cold start / boot force / Senin pagi). `_refresh_zce_rotation` di-refactor ke helper `_compute_zce_map_for()` + mode `full_sweep=True` (refresh SEMUA simbol) yang dipanggil SEBELUM rebuild → dinding ZCE tidak pernah basi lintas weekend/dead zone; umur peta ≤15 mnt. Parameter baru `ZCE_REFRESH_INTERVAL_SECONDS` (default 900).
    - **Patch #2 Resync Deep Target vs F1/C1 Override** (`macro_strategic_engine.py` 1151-1184): bila `deep_floor_f2 >= floor_f1` / `deep_ceiling_c2 <= ceiling_c1` (ter-inversi saat ZCE F1 override dalam & ZCE deep F2 kosong) → resync ulang memakai formula baseline + snap cluster, lalu pulihkan `floor_f2`/`ceiling_c2` yang sempat di-None-kan enforcement monotonik.
63. **Dual-Timeframe Microscope: M3 M5-Rejection & M4 M15/M30 Basing Engine** (4 September 2026): Filter retest M3 (`MULTI_TOUCH_BREAKOUT_RETEST`) dengan M5 Rejection Wick $\ge 25\%$ (mengeliminasi 75.7% waterfall penetration, Win Rate naik dari 4.8% ke 71.7%). M4 horizon retest dipangkas ke 48 bar H1 (2 hari bursa) + M15/M30 High-Tight Basing Engine (`/\/\/\/` kompresi $\le 0.35\times\text{ATR}$). Granular Per-Mechanism Cooldown (lockout 45m spesifik per `(symbol, setup_type, direction)` + jeda bernapas 3m).
64. **Penyelarasan Paradigma AI Dossier, Limit Order Priority & Fix Re-Evaluator Pending Order** (4 September 2026):
    - **Pemisahan Paradigma Setup pada System Directives**: Aturan #4 sistem prompt memisahkan tegas Mean-Reversion (M1/M2 wajib patuh 50% Dealing Range) vs Breakout Retest & Continuation (M3/M4 dibebaskan dari batasan 50% Dealing Range).
    - **Limit Order Priority**: Jika arah dan zona struktural valid namun harga belum di titik optimal, LLM diinstruksikan memilih `REVISE` (Pending Limit Order) alih-alih hard `REJECT`.
    - **Edukasi Tape M5**: Bar counter-trend saat mendekati anchor didefinisikan sebagai retracement normal (bukan waterfall) selama ada wick $\ge 25\%$; feeder `main.py` di-upgrade menggunakan `llm.format_micro_tape()` (menyajikan pips Body/Wick eksplisit); injeksi 3-point trajectory (`origin -> retest -> target`).
    - **Fix Re-Evaluator Pending Order (`audit_pending_orders_thesis()`)**: Mengeliminasi bug ambigu `"REJECTION" in m_state` (yang sebelumnya membatalkan SELL saat `CEILING_REJECTION` dan BUY saat `FLOOR_REJECTION`). Menerapkan evaluasi struktural ketat: pembatalan hanya jika M15 close menembus SL/anchor $> 0.50\times\text{ATR}$ atau CSM Net Delta berbalik tajam ($|delta| > 0.35$). Test suite 100% PASS.
65. **Bifurkasi Rejection Cooldown (Soft Timing HOLD vs Hard VETO) & Penyelarasan Mandate Thesis MSE** (4 September 2026):
    - **Pemisahan Rejection di `main.py`**: Penolakan AI dipisahkan menjadi dua kelas:
      * *Hard Risk VETO (45m lockout)*: Dipicu jika terdapat fatal risk flag (`COUNTER_TREND_MOMENTUM`, `FALLING_KNIFE_WATERFALL`, `SYSTEMIC_CURRENCY_DUMP`, dll).
      * *Soft Timing HOLD (3m breathing cooldown SAJA)*: Jika penolakan murni karena timing atau harga belum menyentuh level boundary (`risk_flag == 'NONE'`). Tidak mengunci mekanisme 45 menit, sehingga saat harga menyentuh boundary 5-10 menit kemudian, radar langsung memprosesnya.
    - **Penyelarasan Semantik Mandate Thesis MSE (`macro_strategic_engine.py`)**: Pada state `CHAMBER_CONSOLIDATION` (20-80% chamber), larangan tegas dibatasi untuk *market chase order*, sedangkan *Pending Limit Orders* di Floor F1 / Ceiling C1 atau retest anchor ditegaskan sah dan direkomendasikan (`REVISE`).
    - **Prompt Dossier Alignment (`llm_client.py`)**: Rule #4 OpenAI & Gemini menegaskan resolusi mid-chamber via Pending Limit Order di boundary.
    - **API Baru `record_soft_timing_hold()` (`market_scanner.py`)**: Mengatur jeda bernapas tanpa mengunci mekanisme. Test suite 120/120 PASS.

---

## Konvensi & Catatan Operasional

- **Komunikasi**: Bahasa Indonesia (santai, lugas, teknikal).
- **Risk-Averse**: Prioritas utama adalah perlindungan modal.
- **Magic Number**: `20260625`. Bot hanya mengelola tiket dengan magic ini.
- **Git Workflow**: Branch `quant-trade` = branch aktif produksi scanner. Branch `main`/`dev` = legacy development.
- **File Disk**: Folder `data/` dan `scratch/` di-`.gitignore`. File script sementara di `scratch/` dibersihkan berkala.

---

## Indeks Dokumentasi & Riset Lengkap

Dokumentasi lengkap telah dikelompokkan ke dalam direktori tematik di [docs/README.md](file:///c:/Vibe/tradingpartner/docs/README.md):

| Kategori | Dokumen | Deskripsi Isi |
|---|---|---|
| **Research** | **[docs/research/APEX_PARAGON_MACRO_FUNDAMENTAL_SPEC.md](file:///c:/Vibe/tradingpartner/docs/research/APEX_PARAGON_MACRO_FUNDAMENTAL_SPEC.md)** | **Spesifikasi Lengkap Apex Paragon Macro Fundamental Engine (40% Weight)**: Kalender Dual-Source (ForexFactory + TV), Peluruhan Eksponensial Half-Life (4h/12h/36h), 8-Currency Composite Scorecard, Matriks Konflik 4-Tingkat, 4-Grade Quality System (Grade S/A+/A/B), dan 7 Master Risk Veto Flags. |
| **Research** | **[docs/research/WEEKEND_AND_ROLLOVER_SPREAD_AUDIT.md](file:///c:/Vibe/tradingpartner/docs/research/WEEKEND_AND_ROLLOVER_SPREAD_AUDIT.md)** | **Audit Live Spread Weekend & Daily Rollover (26 FX + BTC)**: Data empiris akun live VTMarkets, rasio pelebaran spread (1.0x-10.1x), implikasi Pre-Rollover Shield, Dead Zone, dan kalibrasi lebar Reload Zone. |
| **Research** | **[docs/research/MACRO_PSYCH_LEVELS_AND_DELIVERY_ENGINE_REPORT.md](file:///c:/Vibe/tradingpartner/docs/research/MACRO_PSYCH_LEVELS_AND_DELIVERY_ENGINE_REPORT.md)** | **Laporan Riset Macro Psych Levels & Delivery Engine**: Eliminasi Lagging CHoCH, Dynamic ATR Zonal Bands (+-0.35 ATR), M3 Compass Navigator + Trio H1 (M1 Sweep, M2 Pullback, M4 Retest), dan Validasi Multi-Tahun 29 Simbol (+1.378R). |
| **Research** | **[docs/research/MASTER_ATLAS_DNA_AND_DUAL_REACTION_REPORT.md](file:///c:/Vibe/tradingpartner/docs/research/MASTER_ATLAS_DNA_AND_DUAL_REACTION_REPORT.md)** | **Laporan Riset Master Atlas DNA & Dual-Reaction Protocols**: Klasifikasi 22 Simbol MT5, Major 100-pip vs Sub-Stations 50-pip, Skenario A Reversal Fade vs Skenario B Breakout Upgrade, dan Formula Intraday SL/TP Anchoring. |
| **Research** | **[docs/research/QUANT_RESEARCH_V3_MARKET_STATE_ENGINE.md](file:///c:/Vibe/tradingpartner/docs/research/QUANT_RESEARCH_V3_MARKET_STATE_ENGINE.md)** | **Master Quant Dossier V3 (10 Juta Candle / 29 Simbol)**: 4-Dimensional Adaptive Market State, Causal Direction Persistence (41.3 bar), Correction Anatomy Type A Waterfall vs Type B Coil, Conditional CSM Pressure, dan Event Reclaim Layer. |
| **Research** | **[docs/research/METAQUOTES_16YEAR_MASTER_BACKTEST_REPORT.md](file:///c:/Vibe/tradingpartner/docs/research/METAQUOTES_16YEAR_MASTER_BACKTEST_REPORT.md)** | **Master Quant Dossier 16.2 Tahun (Dataset MetaQuotes 2010–2026)**: Validasi 723k Bar H1 / 29 Simbol, 4-Layer Permission FSM, Eliminasi NY ADR Reversal, Integrasi M3 HTF Weekly Wall Reversal (+586.1R), dan Atlas DNA 29 Simbol. |
| **Research** | **[docs/report.html](file:///c:/Vibe/tradingpartner/docs/report.html)** | **Master Quant Dossier (HTML Book Report 15 Bab)**: Laporan buku putih interaktif 15 Bab dalam 4 Bagian: Riset dataset FBS 3.78M bar, 4 Arketipe, Boitoki CSM & Basket Gate, LuxSMC + FRVP, 4D Wave State, Pure Quant MSE 6-TF, Atlas DNA 22 Simbol, 3-LLM Jury, dan Validasi Live Replay. |
| **Technical Spec** | **[docs/technical_specification.html](file:///c:/Vibe/tradingpartner/docs/technical_specification.html)** | **Master Technical Specification Document (HTML 14 Bab)**: Dokumen spesifikasi teknis lengkap 14 Bab mencakup arsitektur 2-stage funnel, 6-TF MSE, 4D Wave State, Apex Fundamental Engine (40%), dan 5 Lapisan Kontrol Portofolio. |
| **Research** | **[docs/research/INTRADAY_CSM_AND_DAILY_CYCLE_SPEC.md](file:///c:/Vibe/tradingpartner/docs/research/INTRADAY_CSM_AND_DAILY_CYCLE_SPEC.md)** | **Spesifikasi Intraday Market Cycle & Boitoki CSM**: Dokumen arsitektur lengkap 3 pilar: Macro Anchor D1, Boitoki CSM 7 USD Majors, Intraday Phase & 2 Exception Rules (Flow Shock & Retracement to D1 Support). |
| **Research** | **[docs/research/MULTIYEAR_FBS_BACKTEST_2026.md](file:///c:/Vibe/tradingpartner/docs/research/MULTIYEAR_FBS_BACKTEST_2026.md)** | **Hasil Riset & Backtest Multi-Tahun (Dataset FBS MT5)**: Validasi 396.183 trade (10.7 thn H1, 55.6 thn H4, 16.6 thn D1). Komparasi head-to-head, evaluasi 4 arketipe, validasi SMC CHoCH/Order Block, dan ranking 22 simbol. |
| **Plans & RFC** | **[docs/plans/IDEAS_AND_PLANS.md](file:///c:/Vibe/tradingpartner/docs/plans/IDEAS_AND_PLANS.md)** | **Daftar Ide & RFC Fitur Baru**: One-Shot Emergency Drawdown Re-Evaluator (80% SL + High-Density Prompt), Refaktor Pending Consensus, Parabolic Filter, Anti-Hedge Gate, **RFC 10: Asymmetric 3-LLM Specialized Roles (Structure Analyst vs Price Action Validator vs Devil's Advocate)**. |
| **Plans & RFC** | **[docs/plans/GLM_CRITICAL_REVIEW.md](file:///c:/Vibe/tradingpartner/docs/plans/GLM_CRITICAL_REVIEW.md)** | **GLM Critical Review — Structural Holes & Research Priorities**: 6 temuan kritis (korelasi eksposur currency, spread-to-ATR ratio, asimetri Dual/Triple consensus, swap cost, validasi momentum feature, session multiplier). Priority stack + action table. |
| **Research** | **[docs/research/QUANT_RESEARCH_EDGES.md](file:///c:/Vibe/tradingpartner/docs/research/QUANT_RESEARCH_EDGES.md)** | **Riset Statistik Bebas Bias (3–4 Tahun)**: Temuan 112 Edge Pola Bearish NY, Ranking Pair Forex, Riset CAD/EUR/GBP & JPY, Riset Donchian XAU BUY NY, Confluence. |
| **Research** | **[docs/research/DAILY_RANGE_VOLATILITY.md](file:///c:/Vibe/tradingpartner/docs/research/DAILY_RANGE_VOLATILITY.md)** | **Riset Volatilitas Harian D1 (365 hari, 29 pair)**: Mean & Median daily range pips untuk semua Major + Minor/Cross + XAUUSD. Ranking volatilitas, analisis CHF crosses di pool bot, kandidat upgrade pair. |
| **Research** | **[docs/research/backtest_augustus_2026.md](file:///c:/Vibe/tradingpartner/docs/research/backtest_augustus_2026.md)** | **Hasil Backtest Agustus 2026**: Evaluasi 10 strategi buku (NotebookLM), Erratum S9 Horn, Verifikasi S9 + Target Struktural GBPUSD. |
| **Architecture** | **[docs/architecture/LLM_COST_ESTIMATION.md](file:///c:/Vibe/tradingpartner/docs/architecture/LLM_COST_ESTIMATION.md)** | **Estimasi Frekuensi & Biaya LLM**: Simulasi kuota token, perbandingan opsi DeepSeek vs Claude Sonnet per bulan. |
| **Architecture** | **[docs/architecture/PROMPT_COMPARISON.md](file:///c:/Vibe/tradingpartner/docs/architecture/PROMPT_COMPARISON.md)** | Perbandingan skema prompt antar iterasi versi bot. |
| **Deployment** | **[docs/deployment/vps_deployment.md](file:///c:/Vibe/tradingpartner/docs/deployment/vps_deployment.md)** | Panduan deployment production bot ke VPS. |
| **Architecture** | **[docs/architecture/BROKER_INFRASTRUCTURE_AND_SAFETY.md](file:///c:/Vibe/tradingpartner/docs/architecture/BROKER_INFRASTRUCTURE_AND_SAFETY.md)** | **Analisis Broker & Keamanan Dana**: Bedah VT Markets (Mauritius FSC, LD4 ECN), A-Book vs B-Book Algo, Roadmap Broker Multi-Tier (Swissquote, IBKR, Bappebti). |
| **Archive** | **[docs/archive/CHANGELOG_AUGUST_2026.md](file:///c:/Vibe/tradingpartner/docs/archive/CHANGELOG_AUGUST_2026.md)** | **Arsip Changelog Detail (8–15 Agustus 2026)**: FASE 1–7, pemisahan mode SL/TP, evolusi lot sizing, dan perbaikan historis. |
| **Master Index** | **[docs/README.md](file:///c:/Vibe/tradingpartner/docs/README.md)** | Indeks lengkap seluruh file dokumentasi, buku trading (PDF), dan spesifikasi. |

