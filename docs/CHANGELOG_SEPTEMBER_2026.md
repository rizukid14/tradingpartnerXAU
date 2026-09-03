# Changelog September 2026 — Trading Bot Multi-LLM Consensus

> Dokumen ini mencatat seluruh perubahan arsitektur, fitur baru, dan riset kuantitatif sistem bot trading MetaTrader 5 periode September 2026.

---

## 1. Perubahan 3 September 2026 (Malam) — M3 Fresh Breakout Law, Retest Debounce, Segmented SL Floor & Net R:R Commission Engine

### 🎯 Latar Belakang & Identifikasi Flaw:
1. **Pemicu Beruntun M3 Radar (75 Setup / 5 Jam)**:
   - Audit mendapati mekanisme M3 (Multi-Touch Breakout Retest) menyumbang 68 dari 75 setup (90.7%) yang dikirim ke 3-LLM Jury.
   - Pemicunya adalah kombinasi bug scoping variabel `df` di `scan_all` (menyebabkan filter 16-bar recency selalu fallback ke `True`) dan `Retest Hovering Trap` di mana pair berkonsolidasi di pita sempit 2-3 pips selama 4 jam berturut-turut sementara cooldown hanya 15 menit.
2. **Friksi Komisi pada Lot Sizing Mikro**:
   - Pair dengan volatilitas rendah (seperti EURCHF dengan ATR H1 72 pts) menghasilkan SL ultra-sempit (29 pts) akibat M4 bypass total terhadap safety floor.
   - Akibatnya lot membengkak ke 1.60 lot, dan komisi broker round-turn ($9.60) memakan hingga 15-60% dari target TP kotor atau memperbesar risiko rugi melampaui 1% equity.

---

### ✨ Komponen & Solusi Utama:

1. **M3 Fresh Breakout Law & Displacement Guard (`market_scanner.py`)**:
   - `M3_BREAKOUT_RECENCY_BARS = 4`: Breakout wajib terjadi dalam rentang 3–4 candle H1 terakhir (bukan level purba 16-120 bar).
   - `M3_MIN_DISPLACEMENT_BODY = 0.55`: Candle yang menembus level wajib merupakan candle momentum dengan rasio bodi $\ge 55\%$ (mengeliminasi penetrasi sumbu / doji palsu).
   - Scoping DataFrame `df` di-pass secara presisi dari macro cache per-simbol.

2. **1 Episode Retest = 1 Evaluasi LLM (Debounce Memory)**:
   - Method `record_retest_rejection()` dan `is_retest_locked()` di `MarketScanner`: Ketika 3-LLM Jury memberikan keputusan REJECT atau HOLD pada suatu level, level tersebut di-lock total.
   - Un-lock hanya terjadi jika harga mengalami perpindahan struktural $> 0.50\times\text{ATR}$ dari level tersebut ATAU telah berlalu minimal 2 jam (2 candle H1).

3. **Segmented Absolute SL Floor (`config.py`, `.env`, `consensus.py`)**:
   - Formula: $\text{SL Floor} = \max(2\times\text{Spread} + \text{Padding}, \quad \text{Floor Absolut Kategori}, \quad \text{Multiplier}\times\text{ATR})$.
   - **Quiet/Standard FX**: Floor absolut **120 pts (12 pips)**. Membatasi lot sizing pada akun \$5.8k ke $\le 0.40 - 0.45$ lot.
   - **High-Beta Crosses** (`GBPAUD`, `GBPNZD`, `EURNZD`, `GBPCHF`): Floor absolut **180 pts (18 pips)**.
   - **JPY Crosses** (M30): Multiplier $1.00\times\text{ATR M30}$ dengan floor absolut **200 pts (20 pips)**.
   - **M4 Systemic Flow**: Dihapuskannya bypass total anchor beku. Usulan M4 tetap tunduk pada Segmented Safety Floor dan Net R:R (`M4_STRUCTURAL_FLOORED`).

4. **Friction-Aware Net R:R Engine (`consensus.py`, `atlas_dna.py`, `risk_engine.py`)**:
   - Formula TP Minimum Bersih:
     $$\text{min\_tp\_pts} = \text{int}(\text{sl\_points} \times \text{min\_rr}) + \text{spread\_pts} + \text{comm\_pts}$$
   - Round-turn komisi dihitung dinamis dari `COMMISSION_USD_PER_LOT_ROUND = 6.0`.
   - `risk_engine.py` mengaudit rasio friksi: memperingatkan jika friksi transaksi melampaui `MAX_FRICTION_TO_SL_RATIO = 0.20` (20% dari SL fisik).

---

## 2. Perubahan 2 September 2026 — Dual-Basket Confluence & Dispersion Matrix Engine

### 🎯 Latar Belakang & Identifikasi Flaw Single-Basket:
- Analisis kuantitatif mengungkap bahwa menilai posisi pair $P = X/Y$ (misal `GBPCHF`) hanya dari satu basket mata uang (misal basket `CHF`) adalah *Single-Basket Fallacy*.
- Pasangan mata uang $P = X/Y$ berada pada **persimpangan dua basket sekaligus** (Base Currency $X$ dan Quote Currency $Y$).
- Ketika `AUDCHF` menyentuh level support struktural bawah dan melambat, `GBPCHF` bergerak naik bukan hanya karena rotasi CHF, tetapi karena komponen **GBP mengalami penguatan independen** (terbukti dari `GBPAUD` yang ikut naik di saat bersamaan).

---

### ✨ Komponen & Arsitektur Utama (Commit `58510bc` pada branch `quant-trade`):

1. **Normalized Structural Position ($pos_i \in [0.0, 1.0]$)**:
   - Dihitung dari posisi harga relatif terhadap Dealing Range 50-bar H1.
   - $pos_i = 0.0$ merepresentasikan Floor/Discount, dan $pos_i = 1.0$ merepresentasikan Ceiling/Premium.

2. **Basket Dispersion Metric ($\sigma_C$)**:
   - Dihitung deviasi standarnya pada seluruh 26 simbol FX terkurasi ($N \ge 6$ pair per basket):
     $$\sigma_C = \sqrt{\frac{1}{N_C} \sum_{i=1}^{N_C} (pos_{C, i} - \bar{pos}_C)^2}$$
   - $\sigma_C \ge 0.22$: **High Dispersion** (terdapat ketimpangan Leader vs Laggard).
   - $\sigma_C < 0.10$: **Low Dispersion / Systemic Cohesion** (pergerakan serentak).

3. **Explicit Leader Hit Wall Condition**:
   - Menghubungkan skala relatif $[0.0, 1.0]$ dengan jarak fisik ATR secara presisi via kondisi `AND`:
     $$\text{Leader\_Hit\_Wall}(C) = (pos \ge 0.90 \text{ or } pos \le 0.10) \quad \mathbf{AND} \quad (\text{Physical Distance} \le 0.35 \times \text{ATR}_{H1})$$

4. **Deterministic Decision Hierarchy (Mutual Exclusive Order)**:
   - **Tier 1 — `SURGE_OVERRIDE_Y` / `SURGE_OVERRIDE_X`**: Lonjakan kecepatan 4-bar $|\Delta Y| \ge 12.0$ atau $|\Delta X| \ge 12.0$ meng-override basket lawan (pair $X/Y$ mengikuti dorongan mata uang yang mengalami surge).
   - **Tier 2 — `SYSTEMIC_EXPANSION`**: $\sigma_X < 0.10 \text{ AND } \sigma_Y < 0.10$ (kedua basket bergerak serentak, lead-lag catchup dimatikan).
   - **Tier 3 — `PURE_CATCHUP_LEAD_LAG`**: $\sigma_X \ge 0.22 \text{ AND } \text{Leader\_Hit\_Wall} \text{ AND } pos_{X/Y} \in [0.20, 0.80]$ (pair $X/Y$ terkonfirmasi sebagai laggard ber-probabilitas tinggi untuk catch-up).
   - **Tier 4 — `NEUTRAL_ROTATION`**: Rotasi teknis standar.

---

### 🛡️ Zero-Risk Informational Ingestion Deployment:
- **Stage 1 Radar ([src/analytics/market_scanner.py](file:///c:/Vibe/tradingpartner/src/analytics/market_scanner.py))**: **100% UNTOUCHED / ZERO HARD GATING**. Filter eksekusi `Permission.GO/ARM/WATCH/LOCK` tetap berjalan tanpa perubahan threshold.
- **Stage 2 LLM Dossier ([src/core/llm_client.py](file:///c:/Vibe/tradingpartner/src/core/llm_client.py))**: Menyambungkan output `get_dual_basket_context()` ke dalam `get_csm_prompt_payload(symbol)`.
- **Informational Warning**:
  ```text
  ### RESEARCH SHADOW METRIC — EXPERIMENTAL DUAL-BASKET CONFLUENCE
  (Note: Exploratory shadow metric for supplementary context only — do NOT override core technical structure)
  - Dual-Basket Classification (GBPCHF): [NEUTRAL_ROTATION]
  - Base (GBP) Basket Dispersion: σ=0.29 (N=7 pairs) | Leader Status: GBPUSD (6% pos, 0.00x ATR to wall)
  - Quote (CHF) Basket Dispersion: σ=0.28 (N=6 pairs) | Leader Status: EURCHF (8% pos, 0.00x ATR to wall)
  - Analytical Confluence Directive: Balanced cross-basket dispersion (σ_GBP=0.29, σ_CHF=0.28). Standard technical rotation.
  ```

---

### 🧪 Verifikasi & Audit Live MT5:
- Script scratch `live_basket_audit.py` dan unit test `test_dual_basket.py` berhasil mengeksekusi audit live 26 FX pairs dari MT5 dengan **0 Error**.
- Hasil audit membuktikan keberadaan pola propagasi real-time (contoh: `AUDNZD` 100.0% Hit Wall vs `GBPNZD` 70.5% Lagging).

---

## 2. Perubahan 2 September 2026 — Startup Latency Optimization (50s -> 9.1s)

### ⚡ Komponen Optimasi Kinerja Startup:
1. **Vectorized NumPy FRVP (`volume_profile.py`)**:
   - Menggantikan iterasi loop bersarang $O(N \times M)$ dengan operasi *broadcasting* matriks 2D NumPy untuk seluruh *bins* secara simultan ($1.174\text{s} \rightarrow 0.043\text{s}$, **$27\times$ lebih cepat**).
2. **Fast Array Swings & Pattern Detection (`macro_strategic_engine.py`)**:
   - Mengonversi pencarian `.iloc` pandas Series di dalam loop *swings* ke akses array mentah NumPy `.values` (**$10\times$ lebih cepat**).
   - Menonaktifkan kalkulasi FRVP impuls yang redundan pada pemindaian struktur HTF ($H_4, D_1, W_1$), menyisakan kalkulasi FRVP aktif murni pada timeframe eksekusi ($H_1$).
3. **Parallel Macro Context Ingestion (`market_scanner.py`)**:
   - Memodifikasi `update_macro_context` untuk memproses seluruh 26 simbol universe secara paralel menggunakan `ThreadPoolExecutor(max_workers=6)`.
   - **Hasil**: Waktu ingest makro 26 simbol terpangkas dari **39.932s $\rightarrow$ 6.812s ($5.8\times$ speedup)**.
4. **Telegram Controller Lazy Loading (`telegram_bot.py`)**:
   - Memindahkan impor library berat AI SDK (`openai`, `google.genai`, `anthropic`) ke dalam pemanggilan *on-demand* perintah `/analisa`, serta memindahkan eksekusi `register_bot_commands()` ke dalam *daemon thread worker* asinkron.
   - **Hasil**: Waktu impor modul turun drastis dari **19.202s $\rightarrow$ 0.097s ($198\times$ lebih cepat)**.
   - **Total Waktu Startup Bot**: Turun dari **$50.0\text{s} \rightarrow 9.130\text{s}$ ($5.5\times$ akselerasi total)** sampai terminal Cyberpunk Bento HUD live.

---

## 3. Perubahan 2 September 2026 — Modernisasi Cyberpunk Bento Box HUD Tile 4 (`cli_theme.py`)

- Memodernisasi **Tile 4 (Kanan Bawah)** dengan intelijen eksekusi kuantitatif *real-time*:
  * **3-AI Jury & Unanimous Consensus**: Menampilkan model aktif (OpenAI o4-mini + Gemini 3.1-Flash + DeepSeek V4-Flash) dan aturan konsensus mutlak 3/3 (*Zero-Tolerance Split*).
  * **2D Confluence Sizing**: Multiplier dinamis (`Grade S 1.25x`, `Grade A 1.00x`, `Grade B 0.50x TP1 Scalp`).
  * **Thesis Sentinel**: Status penjaga M15 $C_1/F_1$ Reclaim & Invalidation Guard.
  * **Server & WIB Clock Sync**: Sinkronisasi jam server MT5 GMT+3 ke WIB dengan status hitung mundur *Pre-Rollover Spread Shield* (03:50 WIB).
  * **Safety Floors**: ATR SL Floor ($0.68\times H_1 / 1.00\times M_{30}$) + *Anti-Wick Padding* + batas atas maksimum $\le 160\text{ pips}$.

---

## 4. Perubahan 2 September 2026 — 2D Quant-AI Confluence Matrix & Dynamic Sizing Engine

- **Integrasi Matriks Konfluensi 2 Dimensi (`consensus.py` & `risk_engine.py`)**:
  - Menggabungkan Stage 1 Quant Grade (`GRADE_S`, `GRADE_A`, `GRADE_B`) dengan Skor Komposit 3-AI Stage 2:
    $$S = (0.35 \times S_{\text{OpenAI}}) + (0.35 \times S_{\text{Gemini}}) + (0.30 \times S_{\text{DeepSeek}})$$
  - **Tier 1 (`APEX_SUPER_CONVICTION`)**: Quant Grade S + AI $\ge 80\%$ $\rightarrow$ **$1.25\times$ Base Lot** (Split 2 Tiket @ $0.625\times$), $TP_2$ Extended Runner.
  - **Tier 2 (`HIGH_CONVICTION`)**: Quant Grade S + AI $70-79\%$ / Quant Grade A + AI $\ge 80\%$ $\rightarrow$ **$1.00\times$ Base Lot**, $TP_1 + TP_2$.
  - **Tier 3 (`STANDARD_TRADE`)**: Quant Grade A + AI $70-79\%$ $\rightarrow$ **$1.00\times$ Base Lot**, $TP_1 + \text{BEP}$.
  - **Tier 4 (`REDUCED_SCALP`)**: Quant Grade B atau AI $60-69\%$ $\rightarrow$ **$0.50\times$ Half Lot**, Target Ketat **$1.0\times - 1.25\times\text{ATR}$** (atau $1.10\times$ Jarak SL), **$100\%$ Full Exit di $TP_1$**.
  - **Tier 5 (`SKIP / VETO`)**: Quant Grade B + AI $60-69\%$ atau AI $<60\%$ atau Hard Reject $\rightarrow$ **$0.0\times$ Lot (`HOLD`)**.

---

## 5. Perubahan 2 September 2026 — Unifikasi Single-Source Trade Permission Engine

- **Eliminasi Inkonsistensi Dual-Permission**:
  - Menghapus fungsi *legacy* `resolve_permission` yang mengembalikan status `WAIT` keliru pada pair berkonsolidasi netral.
  - Menjadikan **Quant V3 `WaveStateEngine`** (`wave_res.permission` dan `wave_res.is_trade_permitted`) sebagai *Single Source of Truth* (SSOT).
  - Fast Radar kini mengizinkan pemindaian penuh pada pair berstatus **`ARM`** (siaga di area reload/diskon) dan **`GO`** (trigger aktif), sembari tetap mengunci ketat pergerakan kinetik bahaya **`LOCK`** (*Waterfall / Vertical Spike*).
  - Badge Grid Tile 1 CLI kini 100% konsisten: **`● GO`** (Hijau), **`◆ ARM`** (Cyan), **`■ LOCK`** (Merah), **`○ WAIT`** (Abu-abu).

---

## 6. Perubahan 2 September 2026 — Pure Quant Objective Barrier Cluster Calibration

- **Injeksi Level Ekstrim Institusional (`macro_strategic_engine.py`)**:
  - Memasukkan `PWL` (Previous Week Low), `PWH` (Previous Week High), `PDL` (Previous Day Low), dan `PDH` (Previous Day High) ke dalam array `macro_extremes` dengan bobot skor institusional $4.0 - 4.5$.
  - Menyelaraskan lantai Demand Base EURUSD di `PWL 1.15779` dan resisten Supply di `PDH 1.16245`.
- **Koreksi Toleransi Jarak (Skala ATR Murni)**:
  - Menghapus angka *hardcoded* $25\text{p}/40\text{p}$ (`0.25/0.40 * psych_step`) yang sebelumnya membuang semua level dalam radius 25 pips dari harga pasar.
  - `min_chamber_height` diselaraskan ke $\max(0.60 \times \text{ATR H1}, 8\text{ pips})$.
  - `delta_tol` diselaraskan ke $\max(0.35 \times \text{ATR H1}, 3\text{ pips})$.

---

## 7. Perubahan 2 September 2026 — Stacked Multi-Horizon Liquidity Pool Radar & Persistent Zoom Memory

- **Peleburan Kolam Bertumpuk (*Stacked Fortress Bands*) di `macro_dashboard.html`**:
  - Ketika $\ge 2$ level likuiditas saling berdekatan dalam toleransi $\Delta_{\text{merge}} \le 0.25\times\text{ATR}$, engine otomatis meleburnya menjadi **1 Pita Zona Terpadu (*Dense Fortress Band*)**.
  - Dilengkapi label rincian komponen gabungan dan skor kepadatan (misal `🏰 F1 [H4_EMA200 + D1_HVN + BULL_OB] (Score 8.5)`).
- **Jangkauan Multi-Horizon Penuh (Dekat s/d Jauh)**:
  - Memetakan seluruh rentang kolam likuiditas makro (dari $F_1 \dots F_{10}$ di bawah harga hingga $C_1 \dots C_{10}$ di atas harga), termasuk level psikologis, High/Low 2-Year, 52-Week, dan EQL/EQH Multi-Bulan.
- **Persistent Zoom Memory**:
  - Variabel `currentNumBars` disimpan secara persisten di frontend dashboard. Saat pengguna memilih **120 Bars**, rentang lilin tetap dipertahankan tanpa reset ke 350 bar saat berpindah pair di dropdown.
- **Generator Script Produksi**:
  - Menempatkan script generator resmi di **[`scripts/generate_macro_dashboard.py`](file:///c:/Vibe/tradingpartner/scripts/generate_macro_dashboard.py)** dan membuka *tracking* git untuk `macro_dashboard.html`.

---

## 8. Perubahan 2 September 2026 — Multi-TF Candle Tapes Distribution, Anti-FOMO Pending Limit Retest, M2 Pullback Optimization & Dynamic Economic News Schedule

### 🎯 Komponen & Arsitektur Utama:

1. **Distribusi Spektrum Candlestick Multi-Timeframe Independen (`llm_client.py`)**:
   - Menghilangkan *Candlestick Blindspot* antar model dengan mendistribusikan rekaman bar OHLC native MT5 secara spesifik:
     * **OpenAI o4-mini (Chief Macro Strategist)**: Diinjeksi **Tape D1 (5 Bar)** dan **Tape H4 (8 Bar)** untuk memverifikasi tren makro multi-hari.
     * **Gemini 3.1-Flash (Chief Price Action Tactician)**: Diinjeksi **Tape M1 (15 Bar), M5 (24 Bar), M15 (12 Bar), dan H1 (6 Bar)** untuk menganalisis anatomi sumbu, penolakan support/resisten, dan kualitas retest.
     * **DeepSeek V4-Flash (Chief Risk Officer & Arbiter)**: Diinjeksi **Tape H4 (6 Bar), H1 (6 Bar), dan M5 (24 Bar)** untuk audit independen silang (*Pass 2 Cross-Examination*).

2. **Mandat Eksekusi Anti-FOMO & Intersep Breakout Ekstrim (`consensus.py` & `llm_client.py`)**:
   - Menambahkan klausul aturan baku di seluruh prompt juri 3-AI: Jika harga mengalami penembusan (*breakout*) di area ekstrem (Dealing Range $\ge 85\%$ untuk BUY atau $\le 15\%$ untuk SELL), **DILARANG KERAS** menggunakan entri *Market Order*. Model wajib mengusulkan **`buy_limit` / `sell_limit` di garis retest struktural**, atau memilih **`HOLD`**.
   - **Hard Anti-FOMO Intercept (`consensus.py`)**: Jika kandidat berstatus Breakout di area ekstrem namun output AI menghasilkan *Market Order*, engine konsensus otomatis mengonversinya menjadi **`BUY_LIMIT` / `SELL_LIMIT`** pada level jangkar $F_1 / RBS$ atau $C_1 / SBR$.

3. **Optimalisasi Mekanisme 2 (Trend-Aligned Pullback & Delayed Retest) (`market_scanner.py`)**:
   - **Pembebasan Hambatan Equilibrium ($45\% - 55\%$)**: Menghapus pemblokiran kaku pada mid-chamber di M2 jika harga sedang menyentuh level struktural valid (Order Block, FVG, EMA50 Dinamis, atau Lantai MSE $F_1$). Mengizinkan setup M2 aktif di rentang diskon sehat ($\le 55\%$ untuk BUY, $\ge 45\%$ untuk SELL).
   - **Standardisasi Zona Aksi ($0.35\times\text{ATR}$)**: Memperluas toleransi zona aksi dari $0.20\times\text{ATR}$ menjadi $0.35\times\text{ATR}$ (selaras dengan M1 dan M3).

4. **Injeksi Kalender Berita Ekonomi Live Otomatis (`llm_client.py` & `market_scanner.py`)**:
   - Mengintegrasikan helper `_get_symbol_news_context(sym, candidate)` yang otomatis menarik rilis berita berdampak tinggi dari `economic_calendar.calendar.get_context(symbol=sym)` jika data di objek kandidat kosong.
   - Menyuntikkan jadwal berita ekonomi terkini secara real-time ke **ketiga model AI** (OpenAI, Gemini, DeepSeek), memastikan tidak ada lagi kebutaan model terhadap event suku bunga / NFP (seperti BoC Rate Statement).

5. **Ekspor Full Prompt Markdown (`docs/prompt/`)**:
   - Menyediakan dokumen prompt lengkap (verbatim) untuk setiap model di direktori `docs/prompt/`:
     * [`docs/prompt/openai_prompt.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/prompt/openai_prompt.md)
     * [`docs/prompt/gemini_prompt.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/prompt/gemini_prompt.md)
     * [`docs/prompt/deepseek_prompt.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/prompt/deepseek_prompt.md)

## 9. Perubahan 2 September 2026 — Dokumentasi: Sinkronisasi Realita SL/TP + RFC 11 Zone Confluence Engine

### 📄 Dokumentasi (tanpa perubahan perilaku kode)

1. **Koreksi drift dokumentasi SL/TP** (`AGENTS.md` & komentar `config.py`):
   - AGENTS.md sebelumnya menuliskan ceiling statis "FX ≤ 160 pts / JPY ≤ 200 pts" dan floor FX "0.68×ATR H1" — **tidak cocok dengan kode aktual**.
   - Realita `consensus.py:155-206` (2 Sep 2026): floor FX = $\max(2\times\text{spread}+15, 0.50\times\text{ATR H1})$ (`LLM_FX_FLOOR_ATR_MULT=0.50`), floor JPY = $\max(2\times\text{spread}+20, 1.00\times\text{ATR M30})$, fallback 250 pts kalau ATR gagal; **ceiling dinamis anti-runaway** = $2.5\times\text{ATR}$ FX/JPY/Gold (fallback 350/350/800 pts) dan $1.8\times\text{ATR}$ BTC (fallback 45000) — hardcode, bukan dari `.env`.
   - Komentar `config.py` (3 lokasi) "1.5x ATR H1" → "0.50x ATR H1".
   - Verifikasi: tidak ditemukan sisa logika ceiling statis 160/200 pts di seluruh `src/` (`max_sl` hanya dari `atr × 2.5/1.8`).

2. **RFC 11: Zone Confluence Engine (ZCE)** — [`docs/plans/ZONE_CONFLUENCE_ENGINE_SPEC.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/plans/ZONE_CONFLUENCE_ENGINE_SPEC.md) & [`docs/plans/ZONE_CONFLUENCE_ENGINE_IMPLEMENTATION_PLAN.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/plans/ZONE_CONFLUENCE_ENGINE_IMPLEMENTATION_PLAN.md):
   - Peta zona multi-TF × multi-horizon (OB/FVG/SBR/RBS/DBD/RBR/EQH/EQL/FRVP/psych/macro extremes) + skoring konfluensi + scale ladder 50–500 + flag `SCALE_CONFLICT` + deteksi `COLD`/`VACUUM`.
   - Serah-terima dari MSE: Blok A/B (deteksi & pemilihan zona, baris 464–1077) → ZCE; MSE tetap pemilik state machine, arah, izin, eksekusi.
   - **Keputusan terkunci user**: J1 horizon = penguat bobot (bukan saksi konfluensi); J2 bobot default + forward test; payload LLM per peran (Gemini raw OHLC banyak M1–M30, OpenAI sedikit, DeepSeek zone table lengkap); refresh rotasi ≤ 5 menit.
   - Fase 3 rencana ditambah: SL/TP berbasis anchor struktural ZCE (`consensus.py`) — `SL_MAX_ATR_MULT` configurable, skip `ANCHOR_TOO_WIDE`, fallback statis → reject. Menunggu persetujuan batch pertama eksekusi.

---

## 10. 2 September 2026 — Eksekusi Fase 1-2 & Task #7 ZCE (Zone Confluence Engine)

> Implementasi engine ZCE + integrasi MSE + gate SL/TP anchor struktural. Seluruh perubahan **flag-gated**: `ZCE_ENABLED=false` + `ZCE_MODE=shadow` (default) → perilaku produksi identik (diverifikasi 86 test pass).

### Fase 1: Engine ZCE + Unit Test (10/10 PASS)
- `src/analytics/zone_confluence_engine.py` (BARU): grid 6-TF x multi-horizon, merge primitives (toleransi max(0.25xATR H1, 6x point)), finalize cluster (J1 greedy dedupe), freshness stamping (touch count, COLD > 21 hari), elect walls (F1/C1 chamber >= 0.60xATR / 8 pips), scale ladder (pos_50/pos_250), suggest method, readiness, build zone table text.
- `tests/test_zone_confluence_engine.py` (BARU): 10 test sintetik (merge, J1 no double-count, width/grade, ladder LOCAL_DISCOUNT_MACRO_PREMIUM, COLD flag, E2E) — 10/10 PASS.

### Bug Fix Parity: Eksponen Konversi Pips di `_elect_walls`
- Sebelum: `min_ch = max(0.60*ATR, 8.0*10^(-digits+3))` → untuk 5-digit menghasilkan **800 pips** (bukan 8) → SEMUA pasangan F1/C1 dianggap terlalu dekat → `F1=None` → wall override mati diam-diam.
- Sesudah: `8.0*10^(-digits+1)` → 5-digit = 0.0008 (8 pips), JPY 3-digit = 0.08. Parity live EURUSD kini menghasilkan F1/C1 valid.

### Fase 2: Hook MSE (Zero Consumer Break)
- `src/analytics/macro_strategic_engine.py`: parameter `zce_walls` di `compute_directive`/`get_directive`; blok override menimpa `immediate_ceiling_c1`/`immediate_floor_f1`/deep/layered SEBELUM Chamber Metrics → state machine & branch konsisten.
- Parity live EURUSD (read-only): ZCE C1=1.16108/F1=1.15780; MSE baseline C1=1.16153/F1=1.15845; MSE+ZCE C1/F1 = persis ZCE → override applied: True.
- `_refresh_zce_rotation` di `market_scanner.py` + `zce_walls` diteruskan ke `get_directive` saat mode legacy/full.

### Task #7: SL/TP Anchor Struktural ZCE (`consensus.py`) — flag-gated
- `SL_MAX_ATR_MULT` configurable dari `.env` (default 2.5) menggantikan hardcode `atr_points * 2.5` di ceiling XAU/JPY/FX. BTC tetap 1.80/45000.
- Mode ZCE legacy/full: SL anchor > ceiling → SKIP `ANCHOR_TOO_WIDE` (bukan clamp yang memarkir SL di tengah struktur); ATR gagal → REJECT `ATR_UNAVAILABLE` (bukan fallback statis 350/800).
- Floor ATR + R:R gate invariant (tidak diubah).
- `tests/test_zce_sltp_anchor.py` (BARU): 4 test sintetik (clamp lama di mode off; ANCHOR_TOO_WIDE; ATR_UNAVAILABLE; fallback statis mode off) — 4/4 PASS.

### Verifikasi
- `compileall config.py src main.py` → OK.
- `pytest tests/ -q` → **86 passed, 6 failed (pre-existing, bukan dari ZCE)**. Enam kegagalan (test_dashboard x4, test_prompt_v2 x2) diverifikasi pre-existing via worktree HEAD bersih `0ecf652` — modul `dashboard` lama & ekspektasi voting 2/3 vs aturan unanimouse 3/3 (sengaja tidak disentuh sesuai instruksi).

---

## 11. 2 September 2026 — Aktivasi ZCE Mode FULL untuk Test Live Cent

Perintah user: aktifkan ZCE tanpa shadow agar bisa langsung ditest di akun **live cent** (bukan akun live utama).

- `.env`: `ZCE_ENABLED=true`, `ZCE_MODE=full` (sebelumnya `false`/`shadow`).
- Definisi mode (dari RFC): `legacy` = window single-horizon identik MSE (parity); `full` = elekt dinding dari klaster grid multi-horizon (ZCE sesungguhnya). Tidak ada kode yang membedakan keduanya saat ini — `market_scanner.py` meneruskan `zce_walls` ke `get_directive` di kedua mode bila `ZCE_ENABLED`.
- Konsekuensi aktif (dihitung & diuji): dinding C1/F1 ZCE menggantikan dinding internal MSE → state machine & SL/TP mengikuti peta zona 6-TF; `_apply_sltp_rules` di jalur ZCE menolak SL > ceiling (`ANCHOR_TOO_WIDE`) dan menolak saat ATR gagal (`ATR_UNAVAILABLE`) tanpa fallback statis.
- **Regresi test yang diperbaiki**: `ZCE_ENABLED=true` global membuat 2 test legacy (yang menguji jalur SL/TP non-ZCE tanpa data MT5 live) gagal. Solusi: patch `config.ZCE_ENABLED=False` + `ZCE_MODE=shadow` di `test_confluence_and_thesis_invalidation.py::test_tight_sltp_rules_for_reduced_scalp` dan `test_market_scanner.py::test_consensus_apply_sltp_symbol_specific` — test tetap menguji jalur legacy deterministik, logika produksi tidak disentuh.
- Verifikasi live read-only (akun terhubung, tanpa order):
  - Parity EURUSD mode full: override applied=True, state MSE ikut dinding ZCE.
  - `_refresh_zce_rotation` 6 simbol: 2.5s; 4 simbol: 0.3s → 26 simbol penuh ~2-11s per rotasi, aman untuk siklus 60 detik.
  - `scan_all` 4 simbol: 1.3s, 0 exception, 0 kandidat (normal — setup A+ tidak muncul tiap cycle).
- Suite: `pytest tests/ -q` → **86 passed, 6 failed pre-existing** (sama seperti sebelum aktivasi, tidak ada regresi baru).
- **Catatan keselamatan**: bot tetap membaca akun dari `.env` (login live). Untuk test di akun live cent, pastikan `.env`/terminal MT5 diarahkan ke akun cent yang dimaksud + `DRY_RUN` tidak diubah tanpa persetujuan.

---

## 12. 2 September 2026 — Koreksi AGENTS.md (Referensi `wave_state.py`/CSM) + Spec Verifikasi Koordinat ZCE/MSE

### 🧹 Koreksi AGENTS.md (perintah: "perbaiki agents md")

Latar: AGENTS.md masih mereferensikan `src/indicators/wave_state.py` (file sudah dihapus) sebagai engine CSM/wave state — menyesatkan pembaca & agent baru.

1. **Tabel arsitektur**:
   - Baris `market_scanner.py` diperluas: `permission_state` dihitung DI SINI dari mapping MSE action tier (`FULL_ALLOW→GO/ARM`, `TP1_ONLY_SCALP→ARM`, `WATCH_ONLY→WATCH`, `HARD_BLOCK→LOCK`) + gate arah terpadu `_is_direction_allowed()` (Macro Bias + CSM Flow Opposition + Systemic Basket Lock) + meneruskan `zce_walls` ZCE ke MSE.
   - `wave_state.py` diganti `wave_regime.py` (regime & umur kompresi — pengganti resmi).
   - `currency_strength.py` diklarifikasi: **modul mandiri** (8 mata uang dari 7 USD majors, cache 30 detik), dibaca scanner/llm/UI — BUKAN bagian MSE/ZCE.
   - Ditambah row `zone_confluence_engine.py` (status `ZCE_ENABLED=true`, `ZCE_MODE=full`, test akun live cent).
2. **Alur cycle langkah 2**: "cek Wave State permission (`GO/ARM` only)" → "cek `permission_state` hasil mapping MSE action tier (`FULL_ALLOW→GO/ARM` only; `HARD_BLOCK`/`WATCH_ONLY` = 0 token) + gate arah terpadu `_is_direction_allowed()`".
3. **Entri changelog historis 25 & 45**: tidak dihapus (catatan kronologis tetap akurat), ditambah anotasi *italik* bahwa model FSM Wave State lama (state `EXPANSION_WAIT_BULL`/`WATERFALL_LOCK`/dst.) sejak 1 September telah dilebur ke MSE Barrier State Machine + action tier 5-Tier (lihat entri 40 & 48) — mencegah pembaca mencari modul yang sudah tidak ada di kode aktif.

### 🧭 Klarifikasi Arsitektur CSM vs MSE/ZCE (dari penelusuran kode)

- **Zero coupling**: `macro_strategic_engine.py` dan `zone_confluence_engine.py` TIDAK mengimpor `currency_strength`. `action_tier`, `macro_bias_score`, dinding C1/F1, dan SL/TP anchor **0% dipengaruhi CSM**.
- CSM hanya dikonsumsi di `market_scanner.py`: (a) baris 705 `csm_delta_val` → macro dict (info/prompt); (b) baris 1064 `evaluate_systemic_basket_lock` di dalam gate `_is_direction_allowed()` yang dipakai M1/M2/M3.
- **Hierarki keputusan aktual**: MSE = kompas & tier → ZCE override dinding (mengubah tier & SL/TP) → CSM = **veto eksternal di gate** (allow/block arah, TIDAK mengubah koordinat). Urutan veto gate: (1) Systemic Basket Lock CSM ±18–20 → `HARD_BLOCK` bahkan sebelum MSE dicek; (2) MSE tier gate; (3) circuit breaker + forbidden traps MSE; (4) CSM Flow Opposition (delta ≤ −1.0 lawan BUY / ≥ +1.0 lawan SELL) → block hanya jika tidak aligned MSE; (5) resolusi tier: aligned → `FULL_ALLOW`, counter → `TP1_ONLY_SCALP`, netral → `REDUCED_CONFIDENCE`.
- **Shadow yang masih hidup**: Dual-Basket Confluence & Dispersion Matrix di `currency_strength.py` — sengaja informational-only (hanya ke dossier LLM), tidak menyentuh hard gate Stage 1. Jalur promosi ke hard gate = titik yang sama (`_is_direction_allowed`), bukan MSE/ZCE.

### 📐 Spec Verifikasi Koordinat ZCE/MSE (Lapis 1–3) — `docs/plans/ZCE_COORD_VERIFICATION_SPEC.md`

Latar: bug eksponen pips (`8.0×10^(-digits+3)` = 800 pips, bukan 8 pips) yang baru diperbaiki membuktikan bahwa "baca koordinat" bisa salah DIAM-DIAM tanpa error — perlu verifikasi eksplisit level fisik, bukan asumsi.

- Spec siap-eksekusi untuk agent lain (bukan perubahan produksi): script `scratch/verify_zce_coords.py` read-only (0 order MT5), 8 simbol uji (major/JPY/cross/CHF/NZD).
- Konvensi unit WAJIB dari `atlas_dna.py` + `symbol_info` (EURUSD 5-digit: 100 poin = 10 pips, `pip_div = 10`) — tanpa hardcode.
- **Lapis 1 Parity**: dump F1/C1/F2/C2 (MSE-baseline vs ZCE-map vs MSE+ZCE) + jarak pips + grade → spot-check manual 3 simbol di chart MT5 (level harus = dinding fisik nyata).
- **Lapis 2 Invariant (hard assert, 0 toleransi)**: INV-1 `F2 < F1 < harga < C1 < C2`; INV-2 jarak ≤ 2.0×ATR_H1 (jebakan bug 800-pips); INV-3 deep layer ≥ 0.5×ATR_H1; INV-4 override benar-benar applied; INV-5 tier konsisten dengan dinding valid. 1 FAIL = BUG → stop, lapor planner.
- **Lapis 3 Hierarki TF**: horizon asal tiap klaster (`horizon_max`) — mikro (M30/H1) bersarang di dalam makro (D1/W1/MN1); loncat horizon = FAIL, konflik skor = WARN.
- Kriteria lolos: INV 100% + spot-check 3/8 valid → baru layak Lapis 4 (validasi eksekusi live cent ≥7 hari/≥60 sampel).
- Catatan agent di spec: panggil `compute_directive` langsung (bukan `get_directive`) agar tidak kena cache; baca definisi dataclass `ZoneMapResult`/`MacroStrategicDirective` sebelum akses field.

---

## 13. 2 September 2026 — Eksekusi Verifikasi Koordinat ZCE/MSE Lapis 1–3 + FIX BUG KRITIS Pemilihan Dinding (INV-2)

### 🚨 Hasil Uji Awal (eksekutor, sebelum fix)

Uji live 8 simbol di akun **VTMarkets-Live 3** → **TIDAK LOLOS, STOP sesuai spec**:

| Invariant | Hasil |
|---|---|
| INV-1 (Ladder `F2<F1<harga<C1<C2`) | 7/8 PASS |
| INV-2 (Proximity ≤ 2.0×ATR) | **1/8 PASS (7 FAIL)** 🚨 |
| INV-3 (Deep spacing ≥ 0.5×ATR) | 6/8 PASS |
| INV-4 (Override applied) | 8/8 ✅ |
| INV-5 (Tier konsisten) | 8/8 ✅ |
| INV-H1/H2 (Hierarki TF) | 8/8 ✅ |

Gejala: level "kabur jauh" — EURUSD C1=1.16494 (6.1×ATR), GBPUSD C1=1.35811 (6.2×ATR), USDJPY C1=160.266 (5.8×ATR), EURJPY F1=182.261 (7.9×ATR).

### 🔍 Akar Masalah 1 — `_elect_walls` membuang zona yang MERENTANGI harga

`zone_confluence_engine.py:378-381`:
```python
floors = [c for c in clusters if c.band_high < cur_price - eps]     # salah
ceilings = [c for c in clusters if c.band_low > cur_price + eps]
```
Klaster yang berisi harga (`band_low ≤ harga ≤ band_high`, contoh EURUSD cluster 1.15727–1.16000 berisi OB+FVG+EQL+Psych) gagal kedua kondisi → **dieliminasi total** → ZCE melompat ke klaster jauh berikutnya.

**Fix**: zona merentangi harga TIDAK dibuang — menyumbang DUA dinding: `band_low` sebagai floor-edge & `band_high` sebagai ceiling-edge. Sorting diubah dari `-band_high` → **jarak ke harga naik** (mencegah salah urut saat zona merentangi punya band_high di atas harga). Verifikasi awal setelah fix: F1 mayoritas dekat, tetapi pola baru muncul.

### 🔍 Akar Masalah 2 — Dinding immediate > cap jarak (INV-2)

Pola baru: **C1 melompat jauh saat ZCE tidak punya zona konfluensi dekat di sisi atas** (USDJPY psych 159.0 ada di MSE tapi tidak tertangkap ZCE; C1 ZCE terdekat = 160.266 = 5.9×ATR). Ini bukan bug filter lagi — memang gap zona.

**Fix**:
1. `_elect_walls`: parameter baru `max_imm_atr` (default **2.0×ATR_H1**, spec INV-2). Sisi immediate > cap → di-None-kan → tidak layak override.
2. Override ZCE→MSE (`macro_strategic_engine.py`) diubah dari guard **penuh** (`F1 & C1 keduanya non-None`) menjadi **override PER-SISI**: ZCE menimpa hanya sisi yang valid; sisi kosong TETAP memakai baseline MSE (`FALLBACK_PSYCH`/struktur internal). Sebelumnya fallback penuh justru memilih sisi MSE yang lebih jauh (kasus USDJPY: ZCE F1=158.5 / 1.3×ATR bagus dibuang, MSE F1=157.974 / 3.5×ATR yang dipakai).
3. Guard di `market_scanner.py`: terima `zce_walls` jika **minimal SATU sisi** non-None (sebelumnya harus dua-duanya).
4. Deep layer F2/C2: bukan lagi index `[1]` — dipilih layer pertama dengan jarak **≥ 0.5×ATR_H1** dari F1/C1 (INV-3, kasus GBPCHF F1/C1 nempel).

### ✅ Hasil Akhir (re-run live 8 simbol)

**INV PASS: 40/40 | BUGS: 0** — INV-1..5, INV-H1/H2 semua 100%. Dinding efektif kini campuran terbaik: contoh USDJPY `F1:ZCE 158.5 + C1:MSE 158.989` (1.2×/0.8×ATR), AUDUSD `F1:ZCE 0.71631 + C1:MSE 0.7175`. Laporan: `scratch/verify_zce_coords_report.md`.

**Catatan penting konversi (koreksi laporan eksekutor)**: jarak "setelah fix" di laporan awal salah konversi 10× — F1=1.15727 jarak sebenarnya **18.4 pips** (bukan 1.8) = 1.92×ATR (nyaris gagal INV-2), C1=1.16000 = **8.9 pips** (bukan 0.8). Klaim "100% PASS setelah fix 2 baris" TIDAK valid; fix sebenarnya butuh override per-sisi + cap jarak + deep-layer spacing, dan hanya terbukti lewat re-run verifikasi (bukan asumsi).

### 🧪 Regresi

- Unit test terkait: 22/22 PASS (`test_zone_confluence_engine`, `test_zce_sltp_anchor`, `test_macro`, `test_time_decay_and_vol_regime`, `test_symbol_rotation`).
- Full suite: **86 passed + 6 failed pre-existing** (test_dashboard ×4, test_prompt_v2 ×2) — identik baseline, tanpa regresi baru.
- File berubah: `src/analytics/zone_confluence_engine.py` (fix elect walls + cap + deep-layer), `src/analytics/macro_strategic_engine.py` (override per-sisi), `src/analytics/market_scanner.py` (guard 1-sisi), `scratch/verify_zce_coords.py` + report (update verifier dinding efektif).

### ⏭️ Langkah berikut
- **Lapis 4 (validasi eksekusi live cent ≥7 hari/≥60 sampel)** kini LAYAK dijalankan — syarat koordinat sudah terpenuhi.
- **Runbook Operasional Lapis 4**: Panduan observasi log-driven live cent tersedia di [`docs/plans/ZCE_LAPIS4_LIVE_VALIDATION_RUNBOOK.md`](file:///c:/Data%20(D)/Vibecoding/tradingpartnerXAU/docs/plans/ZCE_LAPIS4_LIVE_VALIDATION_RUNBOOK.md) dengan penanda audit per-trade `[ZCE-AUDIT]` di `main.py`.
- Kandidat follow-up: investigasi kenapa ZCE tidak menangkap psych station dekat (USDJPY 159.0) yang justru ditemukan MSE — berpotensi memperluas cakupan override ZCE di masa depan.

---

## 14. 2 September 2026 — Fix Koneksi ZCE→Radar: Stale Cache + Resync Deep Target (Patch #1 & #2)

**Konfirmasi independen 3 temuan Gemini** (sebelum eksekusi, verifikasi baca kode langsung):
1. **Stale Cache Disconnect** — BENAR: `macro_cache` hanya di-refresh saat kosong/`>3600s` dan `_refresh_zce_rotation` hanya menulis `self._zce_maps` (tidak pernah `macro_cache`); cold start/rebuild pertama setelah dead zone → seluruh cache dibangun tanpa `zce_walls` (ZCE mati total ±1 jam, basi ≤60 mnt di steady state).
2. **F2 inversion** — SEBAGIAN: jalur yang dikutip Gemini (`market_scanner.py:947`) sudah disembuhkan oleh enforcement monotonik 1146-1149 + eff-blend 837-840 (29ab6fb); sisa edge nyata hanya di `deep_target_floor_f2/deep_ceiling_c2` (raw) saat ZCE F1 override lebih dalam dari deep baseline & ZCE deep F2 kosong → deep target ter-inversi terhadap F1/C1.
3. **SCALE_CONFLICT → gate** — SUBSTANSI BENAR, detail salah: token `"SCALE_CONFLICT"` tidak pernah di-assign (nilai riil `LOCAL_DISCOUNT_MACRO_PREMIUM`/`LOCAL_PREMIUM_MACRO_DISCOUNT`); cek di `_suggest_method` adalah dead code. Tidak di-wire (keputusan: JANGAN di-wire ke gate sebelum tervalidasi).

**Patch #1 — Stale Cache Disconnect** (`market_scanner.py`, `config.py`, `.env`):
- `update_macro_context`: hour-gate → **elapsed-gate** `_zce_refresh_due_seconds()` (900s saat ZCE legacy/full; `MACRO_STRATEGIC_REFRESH_SECONDS`/3600s default).
- `_build_single_macro_context`: bila peta ZCE simbol belum ada di `_zce_maps` → **compute inline** (`_compute_zce_map_for`, engine lokal per thread) → cache TIDAK PERNAH dibangun tanpa dinding ZCE (cold start, boot `force`, Senin pagi).
- `_refresh_zce_rotation`: refactor ke helper `_compute_zce_map_for()` + parameter `full_sweep=True` → refresh SEMUA simbol tepat sebelum rebuild macro_cache (menggantikan peta basi lintas weekend/dead zone).
- `scan_fast_radar`: gate refresh dinamis — saat due: **full-sweep ZCE dulu, baru rebuild**.
- Konfigurasi baru: `ZCE_REFRESH_INTERVAL_SECONDS` (config.py default 900, `.env` = 900).

**Patch #2 — Resync Deep Target vs F1/C1 Override** (`macro_strategic_engine.py` 1151-1184):
- Setelah enforcement monotonik: bila `deep_floor_f2 >= floor_f1` (ter-inversi) → resync `deep_floor_f2 = F1 - max(psych_step_macro, 1.5×ATR)` + snap ke cluster struktural terdekat (mirror baseline 941-960); simetris untuk `deep_ceiling_c2`.
- Pulihkan `floor_f2`/`ceiling_c2` = None yang sempat ditetapkan enforcement karena deep lama ter-inversi → tangga retest tetap tersedia.

### 🧪 Regresi
- `py -m py_compile` ketiga file (scanner, MSE, config) hijau.
- Full suite: **86 passed + 6 failed pre-existing** (test_dashboard ×4, test_prompt_v2 ×2) — identik baseline, tanpa regresi baru.
- File berubah: `src/analytics/market_scanner.py`, `src/analytics/macro_strategic_engine.py`, `config.py`, `.env`, `AGENTS.md`.

### ⏭️ Langkah berikut
- #3 (wire konflik ZCE ke gate) sengaja TIDAK dieksekusi — sinyal belum pernah aktif & belum divalidasi; berisiko memangkas setup tanpa bukti edge.
- Observasi Lapis 4 live cent lanjut; pantau log `[ZCE]` + dinding override agar umur peta ≤15 mnt.

---

## 15. 3 September 2026 — M4 SYSTEMIC FLOW CONTINUATION + Circuit Breaker Calibration

### 🎯 Latar Belakang (Studi #1 & #1b Mirror)
- **Studi #1 & #1b**: Systemic currency flow (rolling 24-bar H1 log-return warm 720, z >= 1.5) -> breakdown swing 120-bar -> pending limit retest di level. Validasi empiris 15 tahun FBS (N=650, P(win) 59.4% vs 51.8% control, chi-sq=8.74). SL struktural 0.45xATR, TP 1.1R. Exclude USDJPY (48.1% < netral).

### 🔬 Implementasi & Penyelarasan Menyeluruh (/grill-me)
1. **Parameter M4**: `M4_ENABLED=True`, `M4_TRIGGER_Z=1.5`, `M4_CONT_Z=0.75`, `M4_FLOW_LOOKBACK_BARS=24`, `M4_LOOKBACK_BARS=120`, `M4_MIN_EPISODE_BARS=6`, `M4_MIN_GAP_BARS=240`, `M4_SL_ATR_MULT=0.45`, `M4_TP_R_MULT=1.1`, `M4_PENDING_EXPIRY_MINUTES=120`.
2. **All-or-Nothing Position Management**: Posisi M4 di `position_manager.py` dibebaskan dari Partial Close, BEP, dan Trailing Stop — menjaga integritas target struktural 1.1R, sembari mempertahankan Pre-Rollover Shield & Time-Decay Stagnation.
3. **Thesis Invalidation Bypass**: Pending M4 dikecualikan dari pembatalan bias MSE D1/H4 di `position_manager.py:audit_pending_orders_thesis()`.
4. **Fix Fatal Bug Symbol Collision**: `cand_sym = getattr(candidate, 'symbol', None) or config.SYMBOL` di seluruh alur konsensus multi-LLM, menghapus risiko pembatalan cross JPY/EUR akibat salah banding harga vs GBPUSD.
5. **Unifikasi Filter Sesi Tokyo (08:00 - 14:00 WIB)**: `TOKYO_PROVEN_SYMBOLS` usang dihapus. `is_symbol_allowed_for_session` diselaraskan 100% dengan `config.is_asian_session_pair(symbol)`. Semua pair ber-driver aktif Asia/Pasifik (mengandung JPY, AUD, atau NZD) diizinkan; pair tanpa JPY/AUD/NZD dikunci.
6. **Fix Silent TypeError di `_m4_refresh_z` (`market_scanner.py:414`)**:
   - Mengganti `part.mean(axis=1, min_periods=minp)` (di mana `DataFrame.mean()` tidak menerima parameter `min_periods`) dengan `part.mean(axis=1).where(part.count(axis=1) >= minp)`.
   - Memulihkan 27 episode flow aktif di scanner.
7. **Kalibrasi Threshold Systemic Currency Basket Circuit Breaker ke 35.0 bps**:
   - Menaikkan `SYSTEMIC_BASKET_USD_THRESHOLD`, `JPY_THRESHOLD`, `CROSS_THRESHOLD`, dan `SPREAD_THRESHOLD` dari 2.0 (20 bps) ke 3.5 (35 bps) di `config.py` dan `.env`.
   - Membebaskan pergerakan tren harian wajar (USD -33.4 bps dan EUR -21.8 bps) agar setup trend-following (seperti GBPUSD SELL M4) dapat dieksekusi, sembari tetap mengunci ketat counter-trend pada shock ekstrem (seperti JPY Surge +67.5 bps).
   - Seluruh unit test suite 75 tests lulus 100% PASS.
8. **Periodic Quant Funnel Snapshot Logger (5-Menit)**:
   - Menambahkan `_log_periodic_quant_snapshot()` di `market_scanner.py` yang mencatat ringkasan spasial 26 pair (`[ZCE F1/C1 | MSE State & Tier | Dealing Range Pos | M4 Standbys]`) tiap 300 detik ke `data/gate_debug.log` (<0.0005 detik, 0 token, 0 beban MT5).
9. **Graceful MT5 Shutdown (`atexit` Protection)**:
   - Menambahkan registrasi `atexit.register(_safe_mt5_shutdown)` di `src/core/mt5_connector.py`.
   - Menjamin bahwa saat proses Python dimatikan via `Ctrl+C` atau selesai, koneksi terminal MT5 ditutup secara bersih dan tidak pernah meninggalkan *zombie process headless* (`terminal64.exe` tanpa GUI window) yang mengunci file disk dan membuat laptop ngelag.
10. **Penyelarasan Menu & Command Telegram (`telegram_bot.py`)**:
    - `/macro [pair]`: Sekarang memprioritaskan pembacaan direktif dari `scanner.macro_cache` sehingga level lantai F1 dan plafon C1 di Telegram **100% sinkron dengan dinding konfluensi ZCE** yang digunakan oleh bot eksekusi live.
    - `/macro all`: Terhubung langsung ke cache scanner untuk menghasilkan ringkasan kompas 26 pair instan (<1ms).
    - Macro Picker Menu: Ditambahkan tombol inline `🧭 [ All 26 Pairs Compass ]` (memanggil `cmd:macro_ALL`), serta mengganti pair non-aktif `BTCUSD` dengan pair FX aktif (`EURCHF` dan `AUDCAD`).
    - `/levels` & `/smc`: Diperkaya dengan tampilan **🏰 ZCE FORTRESS WALLS** (F1 Lantai dan C1 Plafon multi-TF beserta Grade G2/G3 dan Fortress Tag).
11. **Eliminasi False-Positive Gate Stacking (M3 Runway & M4 Contextual Trap Veto)**:
    - **Diagnosa Masalah**: Audit `data/gate_debug.log` membuktikan bahwa filter kaku $dr\_pos < 0.28$ (disalin dari M2 Pullback) membunuh 100% setup M3 Breakdown Retest pada broken support (seperti EURCAD menembus support dan retest SBR di `1.60278` dengan target lantai Daily `1.60032`). Selain itu, trap MSE untuk harga pasar (`Do NOT short into support at F1`) memblokir membabi buta Limit Order M4 yang berada di plafon (seperti `CADJPY SELL_LIMIT @ 113.816` dengan target $F_1$ `113.302`).
    - **Perbaikan Kode (`market_scanner.py`)**:
      - `_is_direction_allowed(target_dir, setup_label, entry_price=None)`: Menambahkan *Contextual Limit Awareness*. Jika limit order sell berada $\ge 0.40\times\text{ATR}$ di atas support $F_1$, trap larangan short di support diabaikan karena $F_1$ adalah Take Profit target. Sebaliknya untuk buy limit di bawah resisten $C_1$.
      - **M3 Breakdown Retest Runway**: Mengganti filter kaku $dr\_pos < 0.28$ dengan perhitungan Runway ke lantai target: $\text{Runway to } F_1 = (target\_sup - \text{immediate\_floor\_f1}) \ge 0.80\times\text{ATR}_{H1}$. Peluang breakdown retest dengan ruang gerak lebar kini diizinkan.
12. **Perbaikan NameError `zce_meta` & Validasi Live Setup EURCAD (`market_scanner.py`)**:
    - **Diagnosa Masalah**: Setelah filter runway M3 membuka blokir pada EURCAD, kode eksekusi mencapai tahap pembentukan `CandidateSetup`. Di sana terjadi `NameError: name 'zce_meta' is not defined` karena dictionary `zce_meta` yang dibuat di `_build_macro_context()` lupa disimpan ke return dict `macro`, dan belum diinisialisasi di scope `scan_all()`.
    - **Perbaikan Kode**:
      - Menyimpan `'zce_meta': zce_meta` ke dalam dictionary hasil return `_build_macro_context()`.
      - Menginisialisasi `zce_meta = macro.get('zce_meta') or {...}` dengan fallback lengkap per-simbol di awal pemrosesan `scan_all()`.
13. **Penyelarasan Mid-Chamber Gate untuk Limit Order Retest (`market_scanner.py`)**:
    - **Diagnosa Masalah**: Trap MSE `Do NOT execute market orders in mid-chamber consolidation zone` menargetkan market order spekulatif di tengah kamar. Namun karena omisi kata kunci `"BREAKOUT"` di baris 1485 & 1507, Pending Limit Order M3 Breakout Retest (seperti pada CADJPY di range 73%) diblokir secara keliru padahal setup memiliki level SBR struktural dan runway ke lantai target.
    - **Perbaikan Kode**:
      - Menyatukan definisi `is_limit_retest = any(k in setup_label.upper() for k in ("PULLBACK", "SYSTEMIC", "BREAKOUT", "RETEST"))`.
      - Membebaskan seluruh limit order retest ber-runway dari pemblokiran `INACTION_ZONE` dan trap `MID-CHAMBER / CONSOLIDATION ZONE`. Market order liar tetap diblokir 100%.
    - **Verifikasi Kuantitatif Langsung**:
      - Radar mendeteksi **6 setup A+ terkurasi** dengan runway lebar dan arah selaras CSM:
        * `USDJPY-ECNc` SELL LIMIT @ 156.3505 (CSM Delta -22.41)
        * `EURAUD-ECNc` SELL LIMIT @ 1.61567 (CSM Delta -4.40)
        * `EURCAD-ECNc` SELL LIMIT @ 1.60281 (CSM Delta -5.82)
        * `GBPAUD-ECNc` SELL LIMIT @ 1.87932 (CSM Delta -6.26)
        * `AUDCHF-ECNc` BUY LIMIT @ 0.58142 (CSM Delta +0.39)
        * `AUDCAD-ECNc` SELL LIMIT @ 0.99216 (CSM Delta -1.42)
      - Full test suite: **75/75 tests PASSED (100% OK)** dalam 1.447s.
14. **Penyelarasan Konteks ZCE Retest Chamber pada Prompt Gemini (`llm_client.py`)**:
    - **Diagnosa Masalah**: Gemini 3.1-Flash (Lead Price Action Tactician) menolak setup EURCAD SELL LIMIT dengan flag `LIQUIDITY_TRAP` karena prompt hanya menyajikan `Dealing Range Position: 2.5% (DISCOUNT)`. Mengacu pada aturan baku SMC, melakukan short di area diskon 2.5% dianggap perangkap ritel. Padahal secara struktural, harga sedang melakukan retest di plafon kamar ZCE lokal ($C_1 = 1.60306$, posisi 89%) menuju lantai $F_1 = 1.60032$.
    - **Perbaikan Kode**:
      - Menginjeksi `- Local ZCE Execution Chamber: Floor F1 = ... │ Ceiling C1 = ... │ Local Position: ...%` ke dalam blok Context Gemini.
      - Memperjelas Anti-FOMO Gate (Aturan 2) bahwa untuk Limit Retest Order (M2, M3, M4), retest di broken support (SBR) pada plafon kamar lokal adalah kelanjutan tren yang sah, bukan jebakan diskon.
      - Menjaga spesialisasi 100% utuh: Gemini tetap fokus penuh mengaudit micro tape (M1/M5/M15/H1), wick rejection, dan displacement, sementara OpenAI fokus pada makroekonomi D1/H4.
    - **Verifikasi**:
      - `py_compile` bersih tanpa error.
      - Full test suite: **75/75 tests PASSED (100% OK)**.
15. **Implementasi 15-Bar Recency Guard & 2.5x ATR Flash Runaway Guard pada M3 (`market_scanner.py`)**:
    - **Diagnosa Masalah**: Mekanisme M3 Multi-Touch Breakout Retest berpotensi meloloskan level-level kadaluarsa jika harga telah menjauh berhari-hari lalu berbalik sebagai counter-trend rally atau flash crash rebound.
    - **Perbaikan Kode Kuantitatif (Berdasarkan Riset FBS 10.7 Tahun / 23.173 Trade)**:
      - *15-Bar Recency Guard*: Level support/resistance yang ditembus WAJIB pernah dilewati/disentuh dalam 15 bar H1 terakhir (`has_recent_break`). Jika level ditembus >15 bar lalu tanpa retest, setup dianggap stale/hangus.
      - *2.5x ATR Runaway Flash Crash Guard*: Pergerakan maksimal harga sejak breakout tidak boleh melebihi $2.50\times\text{ATR}$ (`max_push <= 2.50 * atr_val`). Ambang batas ini terbukti aman meloloskan pergerakan intraday normal (1.0x–1.92x ATR seperti GBPCAD yang sukses), namun secara tegas memfilter anomali flash crash / waterfall rebound.
      - Desain zero-deadlock: Jika riwayat lilin < 16 bar (cold start / test harness), pengaman gracefully default ke True.
    - **Verifikasi**:
      - `py_compile` 100% OK.
      - Full test suite: **75/75 tests PASSED (100% OK)** dalam 1.325s.
