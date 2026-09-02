# Changelog September 2026 — Trading Bot Multi-LLM Consensus

> Dokumen ini mencatat seluruh perubahan arsitektur, fitur baru, dan riset kuantitatif sistem bot trading MetaTrader 5 periode September 2026.

---

## 1. Perubahan 2 September 2026 — Dual-Basket Confluence & Dispersion Matrix Engine

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

