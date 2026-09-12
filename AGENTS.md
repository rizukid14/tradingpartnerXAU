# AGENTS.md — Konteks Proyek & Aturan Operasional AI

> **Panduan Ringkas, Cepat, dan Esensial untuk Setiap Sesi AI Coding.**  
> Dokumentasi teknis lengkap tersedia di [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).  
> Panduan proyek dan quick start tersedia di [`README.md`](README.md).

---

## ATURAN WAJIB AI AGENT (MANDATORY AGENT RULES)

1. **SELALU MINTA KONFIRMASI SEBELUM MENGUBAH KODE (ALWAYS ASK BEFORE EDITING CODE)**:
   - Sebelum melakukan edit/perubahan file kode apa pun, AI WAJIB menjelaskan masalah dan menampilkan rencana/perubahan yang diusulkan.
   - AI DILARANG mengeksekusi tool edit file (`replace_file_content`, `write_to_file`) sebelum pengguna memberikan persetujuan/konfirmasi eksplisit.

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
     1. **`config.py` & `.env`**: Parameter konfigurasi, default fallback, helpers per-simbol (`get_timeframe`, `lot_size_for`, `risk_percent_for`, `get_higher_timeframes`).
     2. **`src/core/llm_client.py`**: Prompt AI, deteksi label timeframe, jumlah candle intra-period, format JSON output, dan variabel lokal candle.
     3. **`src/core/cli_theme.py` & `main.py`**: Banner utama terminal, dynamic status clock line, dan log range candle.
     4. **`src/core/telegram_bot.py` & `telegram_alerts.py`**: Menu keyboard, command on-demand (`/analisa`, `/scan`, `/status`), dan pesan alert.
     5. **`src/analytics/macro_strategic_engine.py`**: Pure Quant 6-TF Native Sockets (`MN1/W1/D1/H4/H1/M30`), SBR/RBS zone hierarchy, dan 5-Tier Action Matrix.
     6. **`src/core/risk_engine.py` & `position_manager.py`**: Filter spread, dead zone, ATR safety floor, progressive trailing, dan pre-rollover shield.
     7. **`tests/test_*.py`**: Unit test suite (`test_pattern_engine.py`, `test_macro.py`, `test_market_scanner.py`) wajib **100% PASS**.
     8. **`docs/CHANGELOG_SEPTEMBER_2026.md` & `AGENTS.md`**: Pencatatan changelog detail dan sinkronisasi ringkasan arsitektur.

5. **GAYA KOMUNIKASI & ZERO FLATTERY / ZERO OVERCLAIM**:
   - Dilarang membuka respon dengan frasa validasi basi atau persetujuan emosional (*"Kamu benar 100%"*, *"Sangat tepat"*, *"Penemuan brilian"*).
   - Dilarang membuat klaim statistik absolut (*"Reversal 94%"*, *"Pasti membalik"*, *"100% terbukti"*) tanpa menyajikan uji *Conditional Probability* dan *Confidence Interval*.
   - Lewati kalimat basa-basi. Langsung jawab substansi teknikal dan data faktual terlebih dahulu.
   - Jika asumsi pengguna atau AI sebelumnya keliru/mengandung bias, katakan langsung apa adanya secara lugas, dingin, dan objektif tanpa melembutkan dengan pujian.

6. **STANDAR BERPIKIR KUANTITATIF RIGOROUS (ANTI-GAMBLER'S FALLACY & SCIENTIFIC HYPOTHESIS TESTING)**:
   - **Pembedaan Mutlak Marginal vs Conditional**: Wajib membedakan *Distribusi Marginal (Base Rate/Panjang Deret)* dari *Distribusi Bersyarat P(A|B) (Transisi Bar Berikutnya)* guna mencegah jebakan *Gambler's Fallacy*.
   - **Uji Null Hypothesis ($H_0$) Sebelum Mengklaim Edge**: Setiap klaim prediktif wajib diuji terhadap model *Memoryless / Random Walk* menggunakan *Wilson Score Confidence Interval 95%* dan *Chi-Square Test*.
   - **Pemisahan Konteks Struktur vs Candle Count**: Jangan mengatribusikan edge ke hitungan lilin murni jika efeknya hanya muncul saat menabrak *HTF Structure / Liquidity Key Levels*.
   - **Syarat Validitas Backtest & Verifikasi**: Minimal sample size untuk klaim edge statistik adalah $\ge 60 - 100+$ trade dengan *Out-of-Sample Holdout* atau *Walk-Forward Validation*.

7. **ATURAN TERMINOLOGI WAJIB (UNIVERSAL LIQUIDITY SWEEP)**:
   - DILARANG menggunakan istilah *"Judas Sweep"*, *"London Judas Sweep"*, atau istilah turunan Judas di seluruh codebase, prompt LLM, alert Telegram, dan percakapan.
   - Gunakan selalu terminologi kuantitatif resmi: **"Universal Liquidity Sweep"**, **"Universal Sweep"**, atau **`UNIVERSAL_LIQUIDITY_SWEEP`**.

8. **KEBEBASAN KRITIK & ZERO YES-MAN (DUTY TO CHALLENGE USER THINKING)**:
   - **DILARANG MENJADI YES-MAN**: AI dilarang keras sekadar mengiyakan, memvalidasi secara buta, atau menuruti instruksi/asumsi pengguna yang secara teknikal, matematis, atau logika kuantitatif keliru atau berpotensi merusak arsitektur trading bot.
   - **KEWAJIBAN MENGUJI & MENGKRITIK PEMIKIRAN PENGGUNA**: Jika pengguna mengusulkan perubahan yang salah kaprah, bias kognitif, atau bertentangan dengan prinsip kuantitatif (*first principles*), AI WAJIB menyajikan kritik lugas, dingin, dan objektif, menjelaskan konsekuensi destruktifnya, serta menyajikan solusi yang benar secara statistik sebelum menjalankan instruksi apa pun.
   - **KEDAULATAN ARSITEKTUR KUANTITATIF**: Integritas data, probabilitas bersyarat, dan proteksi modal institusional berdiri di atas kenyamanan sesaat atau bias emosional siapa pun.

---

## OPERATIONAL QUICK CHEAT SHEET

- **Trading Mode**: `TRADING_MODE = "scanner"` (Default). Universe 26 simbol FX dipindai paralel tiap 60 detik di timeframe H1.
- **Akun Broker**: **LIVE Cent** `VTMarkets-Live 3` (login `27556325`), magic `20260625`, Waktu WIB (GMT+7).
- **Risk & Lot**: Risk per trade 1.0%, Plafon lot maksimal `MAX_POSITION_LOT = 0.50` (kunci mutlak akun Cent).
- **Mode AI**: `AI_MODE_POLICY = "fixed"`, `AI_FIXED_MODE = "triple"` (OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4-Flash).
- **Cara Menjalankan**:
  ```bash
  # Bot Trading
  py -3 main.py

  # Cockpit Dashboard (Port 8765)
  py -3 dashboard.py
  ```
- **Dry Run Flag**: `config.DRY_RUN = False` $ightarrow$ LIVE trading (order riil dikirim). Dilarang ubah tanpa izin pengguna.
- **LuxAlgo MCP**: Terdaftar di `~/.gemini/config/mcp_config.json` (`https://mcp.luxalgo.com/mcp`). 42 tools kuantitatif instan. Source code resmi Pine Script v6 di [`src/indicators/lux_smc_official.pine`](src/indicators/lux_smc_official.pine).

---

## DAFTAR FILE INTI (CORE COMPONENT ROSTER)

| File | Peran & Tanggung Jawab Utama |
|---|---|
| `main.py` | Event loop: Stage 1 radar (60s) + Stage 2 LLM saat ada sinyal A+ + position manager (3s) |
| `config.py` & `.env` | Parameter konfigurasi global, sizing, timeframe helpers, dan universe 26 pairs |
| `src/analytics/market_scanner.py` | **Stage 1 Fast Radar**: Mekanisme M1..M4, filter permission MSE, directional gating |
| `src/analytics/pattern_engine.py` | **SMC Active Dealing Range**: Origin impulse anchor, dynamic envelope, hierarchical swing labeling |
| `src/indicators/lux_smc.py` | Porting Python LuxAlgo SMC (OB, FVG, EQH/EQL, Liquidity levels) |
| `src/indicators/lux_smc_official.pine` | **Source code resmi Pine Script v6 LuxAlgo SMC** (49.8 KB) sebagai acuan formula |
| `src/analytics/macro_strategic_engine.py` | **MSE 6-TF Sockets** (`MN1..M30`), pemetaan stasiun $C_1..C_4$ / $F_1..F_4$, 5-Tier Action Matrix |
| `src/analytics/zone_confluence_engine.py` | **ZCE**: True Zonal Bands, Dynamic EMA Bands 20/50/100/200, Special G3 Protocol |
| `src/analytics/basket_sync_engine.py` | **CBSS Engine**: Analisis keranjang mata uang, local G3 wall veto, basket concurrency cap |
| `src/core/llm_client.py` | **Stage 2 3-LLM Jury**: High-density dossier prompt, 24 M5 tape audit pass 2 |
| `src/core/consensus.py` | Strict 3/3 consensus aggregator, ATR safety floor, friction-aware Net R:R |
| `src/core/risk_engine.py` | Risk lot sizing, daily loss 4%, profit lockout 7%, recovery multiplier |
| `src/analytics/position_manager.py` | 3-Tier trailing stop, BEP 60%, Midday guard, Pre-Rollover & Pre-News emergency shield |
| `dashboard.py` & `dashboard_assets.py` | Web cockpit monitor: 300-bar H1 Lightweight Charts, 8-Gate X-Ray, radar telemetry |

---

## HARD EXECUTION GATES (RINGKASAN EKSEKUSI)

1. **Strict Unanimous 3/3 Consensus**: Wajib 100% kesepakatan bulat 3 model aktif (3/3 BUY atau 3/3 SELL). Jika ada split vote atau HOLD $ightarrow$ otomatis **HOLD**.
2. **Dealing Range Boundary Integrity**:
   - **M1 Sweep SELL** wajib di area Deep Premium ($dr\_pos \ge 0.618$); **M1 Sweep BUY** wajib di area Deep Discount ($dr\_pos \le 0.382$).
   - **M2 Pullback Collision Guard**: Veto BUY jika $dr\_pos \ge 0.80$ & jarak ke $C_1 < 0.40	imes	ext{ATR}$; Veto SELL jika $dr\_pos \le 0.20$ & jarak ke $F_1 < 0.40	imes	ext{ATR}$.
   - **M3 Exhaustion Retest Guard**: Veto BUY jika $dr\_pos \ge 0.85$ tanpa physical breach $C_1$; Veto SELL jika $dr\_pos \le 0.15$ tanpa physical breach $F_1$.
3. **Plafon Lot Maksimal Akun Cent**: Lot terkunci $\le 0.50$ lot pada akun Cent (`MAX_POSITION_LOT = 0.50`).
4. **Friction-Aware Safety Floor**:
   - Quiet/Standard FX $\ge 120	ext{ pts}$ ($12	ext{ pips}$), High-Beta FX $\ge 180	ext{ pts}$ ($18	ext{ pips}$), JPY Crosses $\ge 250	ext{ pts}$ ($25	ext{ pips}$).
   - Total friksi spread + komisi $\le 20\%$ dari jarak Stop Loss.
5. **Basket Concurrency Cap**: Maksimal 2 posisi aktif per keranjang mata uang searah. Setup ke-3 diarahkan ke Virtual Paper Trade (`SKIPPED_CBSS_BASKET_CAP`).
6. **Dead Zone & Sesi Operasional (WIB)**:
   - Dead Zone 00:00–07:00 WIB (FX/Gold skip).
   - Night Freeze 23:00–07:00 WIB (pembukaan order baru dibekukan).
   - Pre-Rollover Shield 03:50–04:15 WIB (tutup bersih posisi dalam jarak bahaya SL jelang 04:00 WIB rollover).
   - Pre-News Emergency Shield ($\pm 30$ menit berita High-Impact US/konstituen).
7. **Circuit Breaker Harian**:
   - Max Daily Loss: 4% equity harian.
   - Daily Profit Target Lockout: 7% equity bersih (bekukan order baru sampai rollover 04:00 WIB).
   - Aggregate open positions cap: 6 total + 4 pending orders.

---

## REFERENSI DOKUMENTASI TERKAIT

- Detail arsitektur teknis, rumus matematika, dan derivasi ZCE/CBSS/SMC: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Log pembaruan historis lengkap: [`docs/CHANGELOG_SEPTEMBER_2026.md`](docs/CHANGELOG_SEPTEMBER_2026.md)
- Panduan proyek & setup lingkungan: [`README.md`](README.md)
