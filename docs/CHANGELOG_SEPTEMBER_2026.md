# Changelog September 2026 — Trading Bot Multi-LLM Consensus

> Dokumen ini mencatat seluruh perubahan arsitektur, fitur baru, dan riset kuantitatif sistem bot trading MetaTrader 5 periode September 2026.

## 0. Perubahan 4 September 2026 (Malam V) — Penyelarasan 2D Confluence Action Tier dengan Anti-Frankenstein Guard & Capping SL/TP

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Pelebaran Target TP Tidak Proporsional pada Setup Reduced Scalp (Kasus GBPCHF Live)**:
   - Pada posisi live GBPCHF (Ticket #1261997759: SELL 0.10 lot, SL 212 pts, TP 400 pts), engine 2D Confluence mengevaluasi tier `REDUCED_SCALP` sehingga lot dipotong 50% ($0.21 \rightarrow 0.10$ lot).
   - DeepSeek CRO di Pass 2 mengusulkan target scalp di F3 (1.09183 = 221 pts, R:R 1.00:1).
   - Namun Anti-Frankenstein Guard sebelumnya memiliki ambang batas kaku `if llm_rr < 1.25`, memperlakukan target 1.00:1 sebagai sub-par dan otomatis memperlebar TP ke Quant Target Station F1 (1.09012 = 392 pts, ~400 pts).
   - Selain itu, `_apply_sltp_rules` menerima `candidate.action_tier` (`FULL_ALLOW`) alih-alih `confluence["tier"]` (`REDUCED_SCALP`), sehingga aturan capping $1.25\times$ R:R tidak aktif.
2. **Karakteristik H1 Intraday Trading**:
   - Untuk pair GBPCHF dengan ATR H1 105 pts dan D1 ADR 531 pts, jarak TP 400 pts (3.8x ATR H1 / 75% ADR) terlalu jauh untuk setup scalp intraday, sementara order AUDCAD (BUY_LIMIT 0.66 lot, SL 120 pts, TP 207 pts, R:R 1.63x net setelah komisi & spread) sudah proporsional (2.3x ATR H1 / 49% ADR).

---

### ✨ Komponen & Solusi Utama:
1. **Penyelarasan Effective Action Tier di Konsensus (`consensus.py`)**:
   - Menghitung `eff_action_tier = confluence.get("tier") or getattr(candidate, 'action_tier', None)`.
   - Menyesuaikan Anti-Frankenstein Guard:
     * Jika `is_reduced_scalp`, `target_min_rr` diturunkan menjadi 1.00:1 (menghormati proposal scalp CRO).
     * Jika TP quant melebihi 1.25x R:R, TP dibatasi pada batas aman 1.25x risk (`max_scalp_dist = 1.25 * curr_cand_risk`).
   - Meneruskan `eff_action_tier` ke fungsi `_apply_sltp_rules(..., action_tier=eff_action_tier, ...)` sehingga aturan pembatasan `max_rr = 1.25` langsung aktif saat 2D Confluence memicu `REDUCED_SCALP`.
2. **Penguatan Ekstraksi Defensif Atribut Cand_TP (`consensus.py`)**:
   - Membungkus parsing `suggested_tp_pts` dengan `try/except` integer casting untuk mencegah `TypeError` saat berhadapan dengan mock/non-int objects pada pengujian.
3. **Unit Test Suite Lengkap (`tests/test_cro_package_arbitration.py`)**:
   - Menambahkan pengujian `test_anti_frankenstein_guard_reduced_scalp_capped` untuk memverifikasi bahwa setup reduced scalp tetap terikat pada rentang R:R $[1.00\times, 1.25\times + \text{friction}]$.
   - 100% full unit test suite PASS tanpa regresi.

---

## 0. Perubahan 4 September 2026 (Malam IV) — Netralisasi Direktif Verdict (APPROVE vs REVISE vs REJECT) & Pengecualian Limit Order Berita Besar

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Disonansi 'REVISE' vs Confidence Level pada Evaluasi EURCHF**:
   - Pada evaluasi live EURCHF, Gemini menyematkan `verdict: "REVISE"`, `signal: "BUY"`, tetapi memberikan `confidence: 55%` dan `risk_flag: "HIGH_IMPACT_NEWS"`.
   - Prompt sebelumnya secara keliru memetakan `REVISE` sebagai tingkat keyakinan kedua yang lebih rendah (*"If 60-69% conviction -> REVISE"*), sehingga saat model ragu karena event berita dalam 30 menit, ia memilih `REVISE` alih-alih `REJECT`.
   - Hal ini menimbulkan anomali di layar: Gemini tertera `[REVISE]` dan vote `BUY`, tetapi trade dibatalkan oleh `CONFIDENCE FLOOR GATE` (55% < 60%) dan dikunci 45 menit (`[HARD VETO LOCK]`) karena berita.
2. **Klarifikasi Esensi Verdict**:
   - `REVISE` bukanlah tingkat keyakinan rendah. `REVISE` adalah tindakan struktural di mana model **setuju dengan arah tren (BUY/SELL)** tetapi ingin **memodifikasi entry type (misal menjadi pending limit) atau menyesuaikan SL/TP**. Model dengan keyakinan 80%–90% sepenuhnya sah memilih `REVISE`.
   - `APPROVE` berarti model menyetujui arah dan menerima koordinat awal tanpa modifikasi.
   - `REJECT` adalah satu-satunya vonis sah ketika keyakinan model berada di bawah batas minimum 60% ($< 0.60$) atau jika terdapat risiko struktural fatal.
3. **Penyelarasan Kebijakan Berita Besar (`HIGH_IMPACT_NEWS`)**:
   - Menempatkan order pasar instan (`MARKET`) tepat sebelum rilis berita berisiko tinggi karena pelebaran spread dan slippage eksekusi.
   - Namun, menempatkan pending limit order (`REVISE`) jauh di stasiun makro yang kokoh (F1/F2 floor atau C1/C2 ceiling) untuk menyerap sumbu (*wick absorption*) berita adalah strategi yang sah dan tidak seharusnya memicu penguncian fatal 45 menit jika keyakinan model $\ge 60\%$.

---

### ✨ Komponen & Solusi Utama:

1. **Netralisasi Panduan Verdict pada Prompt 3 Model (`llm_client.py`)**:
   - Menghapus aturan distorsi *"60-69% -> REVISE"* dari seluruh prompt (OpenAI, Gemini, DeepSeek).
   - Menetapkan direktif netral:
     * **`APPROVE`**: Setuju dengan arah sinyal dan menerima koordinat awal apa adanya.
     * **`REVISE`**: Setuju dengan arah sinyal (BUY/SELL), tetapi memodifikasi entry menjadi pending limit order di F1/C1/OB atau menyesuaikan SL/TP. Keyakinan tinggi (70%, 80%, 90%) sepenuhnya valid.
     * **`REJECT`**: Wajib dipilih jika keyakinan $< 0.60$ ATAU terdapat risiko struktural fatal $\rightarrow$ sinyal wajib `HOLD` dan confidence $\le 0.40$.
2. **Pengecualian Pending Limit Order dari Hard Lockout Berita Besar (`main.py` & `consensus.py`)**:
   - Pada `consensus.py`: `HIGH_IMPACT_NEWS` hanya memveto order instan (`MARKET`). Pending limit order (`REVISE`) di stasiun makro dengan confidence $\ge 60\%$ diizinkan lolos.
   - Pada `main.py`: Jika model menyematkan `HIGH_IMPACT_NEWS` namun order berupa pending limit (`entry_type != "market"`) dengan confidence $\ge 60\%$, sistem tidak mengaktifkan 45-menit hard lockout, melainkan memberlakukan `SOFT_TIMING_HOLD` (3 menit jeda bernapas).
3. **Penyelarasan Dokumentasi Prompt (`docs/prompt/`)**:
   - Mengekspor ulang `openai_prompt.md` dan `gemini_prompt.md` secara utuh.
4. **Verifikasi Test Suite**:
   - Seluruh unit test suite lulus 100% PASS tanpa regresi.

---

## 0. Perubahan 4 September 2026 (Malam III) — Physical SBR/RBS Barrier Override, Proximity Expiration Auto-Cancel, dan Visualisasi Dual-Tier Trajectory (TP1 & TP2)

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Disonansi Multi-Level Konvinsi (EURCAD H1 Case)**:
   - Pada kasus EURCAD H1, radar mendeteksi 3 level terpisah dalam jarak berdekatan: M2 EMA Pullback @ 1.60500, M3 SBR C1 Wall @ 1.60561, dan HTF SBR @ 1.60754.
   - Karena algoritma `find_ema_confluence_anchor` sebelumnya mengurutkan kandidat murni berdasarkan jarak terdekat ke harga mid (`abs(x - mid)`), floating EMA/quarter psych level (1.60500) yang kebetulan lebih dekat 6 pips dipilih mengalahkan dinding fisik SBR C1 (1.60561) yang telah dikonfirmasi oleh aksi harga multi-hari.
   - Konsolidasi 2 hari membuat EMA20/50 mendatar (flat), sehingga menaruh order limit pada angka psikologis/EMA tanpa menempel pada rak resistensi fisik meningkatkan risiko slippage atau false fill.
2. **Jebakan Pending Order Tertinggal Saat Target Tercapai (*Runaway Target Trap*)**:
   - Jika pending limit order ditempatkan di 1.60560 sementara pasar terus meluncur turun mencapai $\ge 75\%$ dari target take profit tanpa pernah pullback menjemput order limit, setup tersebut sejatinya telah terealisasi (*the move already happened*).
   - Membiarkan pending order tetap aktif di pasar menimbulkan bahaya besar: jika harga kemudian berbalik naik menyentuh 1.60560, itu seringkali bukan pullback retest melainkan pembalikan momentum (reversal) berlawanan arah yang berisiko langsung menabrak Stop Loss.
3. **Keterbatasan Visual Trajectory Tunggal di Dashboard**:
   - Radar standbys dan grafik dashboard hanya merender 1 garis target (`target_price` / TP1), sehingga pengguna tidak dapat melihat proyeksi multi-horizon (TP1 di dinding terdekat F1/C1 vs TP2 Macro Expansion di F2/C2).

---

### ✨ Komponen & Solusi Utama:

1. **Physical SBR/RBS Barrier Override (`market_scanner.py`)**:
   - Algoritma `find_ema_confluence_anchor` kini menerapkan pengelompokan klaster institusional:
     * Menghitung jendela klaster terdekat $\text{min\_dist} + (0.35 \times \text{ATR})$.
     * Seluruh kandidat di dalam jendela ini dikelompokkan ke dalam tier struktural: **Physical Structural Barriers (OB = Tier 0, F1/C1 Structural Wall = Tier 0)** diberi prioritas mutlak di atas **FVG (Tier 1)** dan **Atlas Psych Levels / EMA (Tier 2)**.
     * Dalam tier fisik yang sama, sistem memilih barrier yang disentuh pertama kali oleh pullback (`abs(price - mid)` terkecil).
     * Hasil: Pada kasus EURCAD, order limit otomatis menempel presisi di rak resistensi fisik C1 (1.60561), bukan di garis psikologis arbitrer.
2. **Pending Order Target Proximity Invalidation (`position_manager.py`)**:
   - Mesin `audit_pending_orders_thesis()` dipersenjatai dengan penjaga kedaluwarsa target proaktif:
     * **BUY_LIMIT**: Jika harga live pasar $\ge \text{open\_px} + 0.75 \times (\text{tp\_px} - \text{open\_px})$, order pending dibatalkan otomatis dengan notifikasi `"Target proximity expiration: market reached >=75% of TP without fill"`.
     * **SELL_LIMIT**: Jika harga live pasar $\le \text{open\_px} - 0.75 \times (\text{open\_px} - \text{tp\_px})$, order pending dibatalkan otomatis.
     * Menggunakan parser numerik aman (`_safe_num`) guna mencegah konversi nilai mock bawaan (1.0) pada unit test suite.
3. **Eksportasi Dual-Tier TP Standby (`market_scanner.py`)**:
   - Di blok M2, M3, dan M4, `get_radar_standbys` kini menghitung dan mengekspor `target_tp1` (Immediate Floor F1 / Ceiling C1) dan `target_tp2` (Deep Macro Expansion F2 / C2) ke dalam kamus `trajectory`.
4. **Visualisasi Vektor Bercabang di Dashboard Chart (`dashboard_assets.py`)**:
   - Grafik Lightweight Charts kini menggambar 2 vektor proyeksi:
     * **Vector 2a (Solid/Dashed)**: Retest Touch $\rightarrow$ `3a. TP1 <price>` (warna hijau/merah).
     * **Vector 2b (Extended Projection)**: TP1 $\rightarrow$ `3b. TP2 Expansion <price>` jika target makro F2/C2 tersedia.
5. **Unit Test Suite Lengkap (`tests/`)**:
   - `test_audit_pending_orders_thesis.py`: Menambahkan 3 skenario uji target proximity (BUY limit cancelled at 76% TP, SELL limit cancelled at 77.5% TP, SELL limit preserved when only 27.5% progress).
   - `test_market_scanner.py`: Menambahkan uji `test_find_ema_confluence_anchor_physical_override` dan `test_radar_standbys_dual_tp_trajectories`.
   - Seluruh 38 unit test target dan 100% full test suite PASS tanpa regresi.

---

## 0. Perubahan 4 September 2026 (Malam II) — Arsitektur 2-Tier Master CRO Arbiter, Anti-Frankenstein Atomic Package Engine & Pemisahan Visual CLI Pass 1 vs Pass 2

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Jebakan Hibrida Frankenstein (*The Frankenstein Hybrid Trap*)**:
   - Pada evaluasi live AUDCHF: OpenAI mengusulkan paket makro `buy_limit @ 0.58147` (SL 0.58003 di balik Floor F2, TP 0.58314 di Ceiling C1, R:R 1.16:1). Gemini mengusulkan paket micro price action `buy_limit @ 0.58187` (SL 0.58057 di balik M5 OB, TP 0.58488 di Ceiling C2, R:R 2.31:1).
   - DeepSeek V4-Flash (Master CRO di Pass 2) khawatir order OpenAI di F1 tidak terjemput (*"may not fill"*), sehingga memilih **Entry Gemini (0.58187)**. Namun untuk TP, DeepSeek justru mengambil **TP konservatif OpenAI di C1 (0.58314)**!
   - Akibat mencampur entry dekat market dengan TP terpendek, reward terperas menjadi hanya $12.7\text{ pips}$ melawan risk $13.0\text{ pips}$ $\rightarrow$ **R:R runtuh menjadi 0.97:1 (sub-par / negatif EV)**.
2. **Disonansi Visual CLI Konsensus Multi-LLM**:
   - Tampilan terminal CLI sebelumnya mencampur ketiga model secara datar (*flat loop*), menyembunyikan hierarki evaluasi antara Pass 1 (Specialist Investigation) dan Pass 2 (Master CRO Arbitration).

---

### ✨ Komponen & Solusi Utama:

1. **Injeksi Stasiun Quant & Prompt Arbiter DeepSeek CRO (`llm_client.py`)**:
   - Prompt `build_deepseek_cro_arbiter_prompt` diperkaya dengan kalkulasi otomatis R:R dan jarak poin untuk kedua paket Pass 1 (`PACKAGE A — OpenAI` vs `PACKAGE B — Gemini`).
   - Koordinat dealing chamber kuantitatif disuntikkan secara presisi: Floor F1, Floor F2, Ceiling C1, Ceiling C2, serta baseline quant station.
   - **Hukum Integritas Paket Utuh (*The Atomic Package Integrity Law*)**: DeepSeek diwajibkan mengevaluasi proposal sebagai satu kesatuan struktural utuh. Dilarang keras mencampur entry tinggi dengan TP pendek yang menghasilkan R:R $< 1.25\times$.
   - Skema JSON DeepSeek CRO kini menyertakan blok `arbitration_decision` (`openai_eval`, `gemini_eval`, `chosen_package`, `arbitration_rationale`) dan `calculated_rr` di dalam blok `execution`.
2. **Adopsi Paket Utuh & Anti-Frankenstein Guard (`consensus.py`)**:
   - Jika DeepSeek memilih `PACKAGE_OPENAI` atau `PACKAGE_GEMINI`, sistem konsensus secara otomatis mengadopsi satu set koordinat utuh (Entry, SL, TP) dari paket spesialis yang terpilih, alih-alih menghitung median terpisah.
   - **Anti-Frankenstein R:R Guard**: Sistem secara otomatis memverifikasi $R:R = \text{Reward} / \text{Risk} \ge 1.25:1$ dari harga eksekusi riil (bukan harga market). Jika R:R $< 1.25\times$, sistem memperluas TP ke Quant Target Station (atau level minimum $1.25\times$), menjamin perlindungan matematis absolut.
3. **Pemisahan Visualisasi Terminal CLI (`consensus.py`)**:
   - Terminal kini menampilkan kartu terpisah yang terstruktur rapi:
     * **`[ PASS 1: SPECIALIST DOSSIER INVESTIGATION ]`**: Kartu OpenAI (Macro Strategist) dan Gemini (Price Action Tactician) dengan konteks setup, retest quality, dan level.
     * **`[ PASS 2: MASTER CRO & RISK ARBITER ]`**: Kartu DeepSeek (Master CRO Arbiter) menampilkan paket arbitrase yang dipilih (`PACKAGE_OPENAI` / `PACKAGE_GEMINI` / `REVISE_EXPANDED_TP`), kalkulasi R:R, justifikasi risiko, dan tape audit M5.
     * **`[ FINAL CONSENSUS & EXECUTION TICKET ]`**: Ringkasan kesepakatan 3/3 dan tiket order yang divalidasi.
4. **Unit Test Suite Lengkap (`tests/test_cro_package_arbitration.py`)**:
   - 3 test case baru yang memvalidasi injeksi prompt, adopsi paket utuh, dan intersepsi Anti-Frankenstein Guard.
   - Seluruh test suite (105/105 tests) PASS 100%.

---

## 0. Perubahan 4 September 2026 (Sore II) — Sinkronisasi SMC D1/H4 Macro Trend, HTF Wall Collision Gate (M3), & Unshackling M1 Universal Liquidity Sweep

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Jebakan Lagging 2-EMA D1/H4**:
   - `market_scanner.py` menggunakan `close >= ema20 and close >= ema50`. Pada GBPUSD yang sedang mengalami koreksi tajam dari 1.3675 ke 1.3474, pantulan tipis 5 pip di atas EMA20 (1.35336) secara keliru melabeli pasar sebagai `D1_BULLISH_EXPANSION` dan `is_bull = True`.
   - Di H4, pembalikan logika boolean membuat pantulan korektif di dalam tren turun (`h4_c > h4_ema20 and h4_ema20 <= h4_ema50`) dilabeli `h4_is_bull = True`, bertolak belakang dengan MSE 6-TF (`HUNT_SELL_PULLBACK`, `CEILING_REJECTION at 1.35383`).
2. **Pembunuhan Prematur M1 SELL Universal Liquidity Sweep**:
   - Aturan anti-trend `is_macro_bull` membaca `macro['is_bull'] == True`, langsung memicu `[SWEEP SELL ANTI-BULL VETO]`, sehingga peluang M1 SELL sweep di resistensi C1 terbuang meski MSE mengarahkan penjualan di plafon.
3. **M3 BUY Menabrak Plafon di Premium Zone**:
   - M3 BUY breakout mengukur runway plafon dari support lama yang tertinggal (`target_res`) alih-alih harga live (`mid`). Akibatnya radar meloloskan order BUY_LIMIT di 1.35403 tepat ke dinding plafon C1 di Premium (73.8% Range) yang ditolak 0/3 oleh AI Jury (`LIQUIDITY_TRAP`, `DIRTY_SWEEP`).
4. **Klarifikasi Istilah M2**:
   - Menstandarkan penamaan telemetry M2 sebagai `Touched` / `Retest EMA` (kata `Break` murni milik M3/M4).

---

### ✨ Komponen & Solusi Utama:

1. **Integrasi SMC Market Structure pada D1 & H4 (`market_scanner.py`)**:
   - D1 memadukan `d1_smc.trend_bias` (`LuxSMCAnalyzer(swing_length=3)`): jika struktur SMC bearish, pantulan di atas EMA20 diklasifikasikan sebagai `D1_BEARISH_PULLBACK` (`is_bear = True`, `is_bull = False`).
   - Koreksi pembalikan polaritas boolean H4: pantulan dalam tren turun (`h4_ema20 <= h4_ema50`) diklasifikasikan sebagai `H4_BEARISH_PULLBACK` (`h4_is_bear = True`, `h4_is_bull = False`).
   - Harmonisasi dengan MSE 6-TF: direktif strategis MSE (`HUNT_SELL_PULLBACK` / `HUNT_BUY_DIP`) disinkronkan langsung ke `combined_is_bull` / `combined_is_bear`.
2. **HTF Wall Collision & Runway Guard pada M3 Breakout (`market_scanner.py`)**:
   - Mengukur jarak fisik riil `dist_to_ceiling = target_ceiling - mid`.
   - Menolak keras (`[BREAKOUT BUY WALL COLLISION] SKIP` + `continue`) order BUY jika harga berada dalam radius $\le 0.35\times\text{ATR}$ dari plafon C1 atau berada di Premium Zone ($dr\_pos \ge 0.70$). Simetris untuk M3 SELL pada lantai F1 di Discount ($dr\_pos \le 0.30$).
3. **Unshackling M1 Universal Liquidity Sweep di Plafon/Lantai Ekstrem (`market_scanner.py`)**:
   - Anti-trend veto tidak lagi memblokir SELL sweep jika harga berada di Premium Zone ($dr\_pos \ge 0.65$) pada dinding validasi G2/G3 atau di bawah mandat MSE (`HUNT_SELL_PULLBACK`, `CEILING_REJECTION`, `FADE_CORRIDOR_EXTREMES`).
   - Tetap mempertahankan seluruh kualifikasi ketat M1 (penetrasi stop-hunt, reclaim penutupan di balik level, dan rejection wick).
4. **Penegakan Aturan Terminologi Resmi (Universal Liquidity Sweep)**:
   - Memastikan semua pemanggilan gate menggunakan `evaluate_universal_sweep_gates` sesuai Rule 7 AGENTS.md.
5. **Unit Test Suite (102/102 PASS — 100%)**:
   - Isolasi hermetis `setUp` dari file disk `scanner_cooldowns.json`.
   - Penambahan `test_d1_h4_smc_pullback_classification` dan `test_m3_htf_wall_collision_and_m1_unshackling`.

---

## 0. Perubahan 4 September 2026 (Malam) — Pemisahan Rejection (Soft Timing HOLD vs Hard VETO) & Penyelarasan Mandate Thesis MSE

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **Disonansi Semantik MSE vs Setup Retest/Limit (Mid-Chamber Trap)**:
   - Ketika harga berada di rentang 20%–80% dari dealing chamber (misalnya 28% atau 2.4 pips di atas Floor F1), MSE mencap kondisi tersebut sebagai `CHAMBER_CONSOLIDATION` dengan teks kaku:
     `Mandate Thesis: Discipline requires waiting for extreme boundary touch...`
     `Forbidden Traps: Do NOT execute market orders in mid-chamber consolidation zone`
   - LLM membaca teks ini sebagai larangan kuantitatif mutlak dari sistem internal, sehingga secara otomatis mengeluarkan `HOLD` / `REJECT`.
2. **Jebakan Hukuman Cooldown Kaku (*The 45-Minute Lockout Trap*)**:
   - Di `main.py`, setiap kali AI menjawab `HOLD`, sistem langsung memanggil `record_setup_rejection()`, mengunci `(symbol, setup_type, direction)` selama **45 menit** (dan level retest M3 selama **2 jam**).
   - Akibatnya: 5–10 menit kemudian harga menyentuh tepat di level boundary (Floor F1) dengan rejection wick 50% (sesuai yang ditunggu), namun Stage 1 Radar melewatinya (*skip*) karena masih tertahan lockout 45 menit. Peluang profit terlewat total.

---

### ✨ Komponen & Solusi Utama:

1. **Bifurkasi Klasifikasi Rejection di `main.py`**:
   - **Hard Risk VETO (45 Menit Lockout)**:
     Jika terdeteksi salah satu fatal risk flag (`COUNTER_TREND_MOMENTUM`, `FALLING_KNIFE_WATERFALL`, `SYSTEMIC_CURRENCY_DUMP`, `HIGH_IMPACT_NEWS`, `LIQUIDITY_TRAP`, `UNMITIGATED_IMPULSE_CHASE`). Kunci mekanisme 45m aktif secara protektif.
   - **Soft Timing HOLD (Hanya 3 Menit Breathing Cooldown)**:
     Jika `risk_flag` adalah `"NONE"` (penolakan murni karena timing atau harga belum menyentuh level). Sistem memanggil `scanner_inst.record_soft_timing_hold(sym)`, HANYA mengaktifkan jeda bernapas simbol 3 menit **TANPA mengunci mekanisme 45 menit**. Begitu harga menyentuh boundary level beberapa menit kemudian, Radar langsung siap memindai dan mengeksekusi kembali!
2. **Penyelarasan Semantik Mandate Thesis & Forbidden Traps (`macro_strategic_engine.py`)**:
   - Teks `thesis` dan `forbidden_traps` diperbarui untuk secara eksplisit membedakan *Market Chase Order* (dilarang mid-chamber) dari *Pending Limit Orders / Structural Retests* di boundary Floor F1 / Ceiling C1 (diizinkan & direkomendasikan via `REVISE`).
3. **Edukasi Resolusi Mid-Chamber pada Prompt Dossier (`llm_client.py`)**:
   - Rule #4 pada prompt OpenAI dan Gemini menegaskan bahwa jika harga berada di mid-chamber mendekati boundary, model diarahkan memilih `REVISE` dengan `buy_limit` / `sell_limit` di anchor level daripada melakukan hard `REJECT`.
4. **Metode Baru `record_soft_timing_hold()` (`market_scanner.py`)**:
   - Menyediakan API mandiri untuk jeda bernapas simbolik tanpa mengotori `_mechanism_rejection_cooldowns`.
5. **Unit Test Suite (120/120 PASS — 100%)**:
   - Test case baru `test_soft_timing_hold_vs_hard_veto_lockout` di `tests/test_market_scanner.py` memverifikasi presisi pemisahan cooldown.

---

## 1. Perubahan 4 September 2026 (Sore) — Penyelarasan Paradigma AI Dossier, Limit Order Priority & Fix Re-Evaluator Pending Order (Thesis Broken)

### 🎯 Latar Belakang & Identifikasi Masalah:
1. **False Rejection Akibat Benturan Paradigma (Audit 13:45–14:05 WIB)**:
   - 4 setup valid yang lolos Stage 1 Radar (AUDCAD BUY, GBPUSD BUY, EURCHF SELL, USDCHF SELL) ditolak bulat oleh Stage 2 LLM Jury.
   - Akar masalah: Prompt sistem multi-LLM mendiktekan bahwa *BUY HANYA diizinkan di Discount (≤ 50%)* dan *SELL HANYA diizinkan di Premium (≥ 50%)*. Ini aturan mean-reversion (M1/M2) yang bertentangan langsung dengan mekanisme breakout/continuation (M3/M4), di mana breakout resistance secara alamiah berada di Premium (> 50%) dan breakdown support berada di Discount (< 50%).
2. **Salah Tafsir Candlestick Tape M5 (Pullback Retest vs Waterfall)**:
   - Saat harga melakukan pullback retracement menuju level retest anchor, lilin M5 secara alami berlawanan arah (2–3 bar merah saat pullback ke support BUY). Model Gemini dan DeepSeek mencapnya sebagai `COUNTER_TREND_MOMENTUM` / `FALLING_KNIFE_WATERFALL`, padahal itu adalah proses pengujian level yang wajar.
   - Tape M5 di `main.py` sebelumnya hanya mengirim string OHLC mentah tanpa kalkulasi pips sumbu/body.
3. **Bug Kritis Re-Evaluator Pending Order (`audit_pending_orders_thesis()`)**:
   - Order limit yang sudah terpasang sering dibatalkan sepihak tiap 3 detik karena evaluasi ambigu `"REJECTION" in m_state`.
   - Akibatnya, `SELL_LIMIT` di ceiling justru dibatalkan saat terdeteksi `CEILING_REJECTION` (yang sebenarnya adalah sinyal jual valid), dan `BUY_LIMIT` dibatalkan saat `FLOOR_REJECTION`!

---

### ✨ Komponen & Solusi Utama:

1. **Pemisahan Paradigma Setup pada System Directives (`llm_client.py`)**:
   - Aturan #4 sistem prompt memisahkan tegas:
     * *Mean-Reversion / Reload (M1 & M2)*: Wajib patuh batas 50% Dealing Range HTF.
     * *Breakout Retest & Continuation (M3 & M4)*: Dibebaskan dari batasan 50% Dealing Range HTF. Evaluasi difokuskan pada kualitas retest level structural flip (RBS/SBR) dan runway stasiun target ZCE.
2. **Prioritaskan `REVISE -> Limit Order` daripada Hard `REJECT` (`llm_client.py`)**:
   - Jika arah dan zona level memiliki probabilitas institusional yang baik namun timing pasar saat ini belum optimal (sedang retracement atau mid-corridor), LLM diinstruksikan memilih `REVISE` dengan memasang Pending Limit Order di level anchor.
   - Status `REJECT` / Veto dicadangkan strictly untuk risiko fatal: Counter-trend mayor tanpa CHoCH, lonjakan berita Tier-1 aktual, atau candle waterfall yang menembus bablas level invalidasi.
3. **Edukasi Candlestick Tape M5 (`llm_client.py`) & Feeder `main.py`**:
   - Header konteks `[PULLBACK RETEST RETRACEMENT CHECK]` ditambahkan ke prompt.
   - Ditegaskan bahwa lilin counter-trend saat mendekati anchor adalah retracement normal, bukan waterfall, selama ada wick rejection $\ge 25\%$ atau deselerasi body.
   - Feeder `main.py` diperbarui menggunakan `llm.format_micro_tape()` sehingga tape M15, M5, H1, H4 menyajikan kalkulasi eksplisit pips `Body / WickU / WickL`.
   - Injeksi data 3-point trajectory (`origin_price`, `origin_age`, `target_price`) ke dossier prompt.
4. **Refactoring Re-Evaluator Pending Order (`position_manager.py`)**:
   - Menghapus pengecekan ambigu `"REJECTION" in m_state`.
   - Menerapkan **Evaluasi Struktural Ketat**:
     * BUY Pending Order HANYA dibatalkan jika M15 close menembus ke bawah SL atau anchor $> 0.50\times\text{ATR}$ (`last_close < anchor - 0.50*atr`), ATAU CSM Net Delta berbalik tajam ($<-0.35$), ATAU terkonfirmasi `FLOOR_BREAKDOWN`.
     * SELL Pending Order HANYA dibatalkan jika M15 close menembus ke atas SL atau anchor $> 0.50\times\text{ATR}$ (`last_close > anchor + 0.50*atr`), ATAU CSM Net Delta berbalik tajam ($>+0.35$), ATAU terkonfirmasi `CEILING_BREAKOUT`.
5. **Unit Test Suite 100% Pass (`tests/test_audit_pending_orders_thesis.py`)**:
   - 4 test case baru memvalidasi perbaikan bug `CEILING_REJECTION` dan `FLOOR_REJECTION`, serta memastikan pembatalan struktural bekerja presisi.

---

## 1. Perubahan 4 September 2026 (Siang) — Dual-Timeframe Microscope (M3 M5-Rejection & M4 M15/M30 Basing Engine)

### 🎯 Latar Belakang & Bukti Kuantitatif (100k Bar M5 + 11k H1 Swings):
1. **Kegagalan Fatal Blind Retest M3 (4.8% Win Rate)**:
   - Dari 6.826 sentuhan retest pada broken support/resistance level, **75.7% (5.166 kasus) adalah *Waterfall Penetration*** di mana lilin M5 menembus bablas tanpa penolakan (Win Rate hanya 0.8%).
   - Memfilter retest dengan **M5 Rejection Wick $\ge 25\%$** terbukti melipatgandakan Win Rate menjadi **71.7%** ($N=99, \chi^2 = 348.2, p < 10^{-10}$).
2. **Kekeliruan Asumsi Deep Retest M4 (10.1% Win Rate)**:
   - Data membuktikan paska penembusan swing 120-bar saat flow meledak ($|z| \ge 1.5$), jika harga sampai turun kembali ke level awal, momentum sering kali sudah mati (Win Rate 10.1%).
   - Sebaliknya, saat harga membentuk **High-Tight Basing M15/M30 (`/\/\/\/`)** di atas level pecahan ($\le 0.35\times\text{ATR}$), peluang kelanjutan tren naik **2.5x lipat (24.9% vs 10.1%)**.
3. **Memori Retest Basi 120 Bar**:
   - Menahan level breakdown selama 120 bar (5 hari bursa) membuat radar dipenuhi antrean M4 gantung yang sudah kehilangan relevansi flow.

---

### ✨ Komponen & Solusi Utama:

1. **M3 M5 Micro-Rejection Gate (`market_scanner.py`, `config.py`, `.env`)**:
   - `M3_M5_REJECTION_FILTER = True`, `M3_M5_MIN_WICK_RATIO = 0.25`:
     - Menarik 6 candle M5 via MT5 (<1ms, 0 token) saat harga memasuki zona retest $0.28\times\text{ATR}$.
     - Wajib mendeteksi sumbu penolakan fisik $\ge 25\%$ (upper wick untuk SELL SBR, lower wick untuk BUY RBS) atau pantulan close menjauh dari level.
     - Lilin marubozu waterfall yang menembus level $>0.15\times\text{ATR}$ tanpa sumbu di-blokir 100% di Stage 1 sebelum memanggil 3-LLM Jury.

2. **M4 Horizon Retest 48 Bar (2 Hari Bursa) (`config.py`, `.env`, `market_scanner.py`)**:
   - `M4_MAX_WAIT_BARS = 48` (dipangkas dari 120 bar ke 48 bar H1).
   - Menghapus antrean M4 basi yang tidak kunjung disentuh dalam 2 hari bursa.

3. **M4 M15/M30 High-Tight Basing Engine (`market_scanner.py`)**:
   - `M4_BASING_MIN_BARS = 4`, `M4_BASING_MAX_RANGE_ATR = 0.35`:
     - Selain Mode A (Deep Retest), sistem mendukung Mode B: Konsolidasi mendatar M15 (FX Majors) dan M30 (JPY Crosses).
     - Jika 4 bar M15/M30 berkonsolidasi ketat $\le 0.35\times\text{ATR}$ di atas level penembusan dan harga menguji batas base tersebut, order limit dipasang di boundary base dengan SL struktural $0.45\times\text{ATR}$ dan TP $1.1R$.

---

## 1. Perubahan 4 September 2026 (Pagi) — Granular Mechanism Cooldown, M4 Range Discipline & Multi-Confluence Architecture

### 🎯 Latar Belakang & Identifikasi Flaw:
1. **Cross-Mechanism Contamination Trap (AUDUSD Case Study)**:
   - Pada saat setup M4 (`SYSTEMIC_FLOW_CONTINUATION` BUY_LIMIT @ 0.7208) ditolak oleh 3-LLM Jury (Pass 2 CRO DeepSeek mendeteksi `IMPULSE_CHASE` di 89.5% Dealing Range), `main.py` memanggil `record_retest_rejection(sym, ...)`.
   - Di `market_scanner.py`, fungsi ini menetapkan `self._symbol_last_trigger[clean_sym] = now_ts + 1800`, yang memicu *blanket symbol lockout* selama 45 menit untuk pasangan tersebut.
   - Akibatnya, setup valid M1 (Universal Liquidity Sweep), M2 (Pullback), dan M3 (Multi-Touch Breakout Retest) yang berada di zona yang sama (0.72071 - 0.72085) ikut terbunuh dan diabaikan total selama 45 menit.
2. **Ketiadaan Filter Range Discipline di Hulu M4 (Stage 1 Radar)**:
   - Mekanisme M4 sebelumnya tidak mengecek Dealing Range sama sekali, sehingga memancarkan BUY di Extreme Premium (>70%) atau SELL di Extreme Discount (<30%), membakar token LLM hanya untuk di-veto oleh DeepSeek CRO.
3. **Ketiadaan Tagging Multi-Mekanisme Confluence**:
   - Ketika M1, M2, dan M3 aktif bersamaan pada rentang sempit ($\le 0.35\times\text{ATR}$), 3-LLM Jury tidak menerima sinyal bahwa level tersebut merupakan konvergensi dari berbagai mekanisme kuantitatif.

---

### ✨ Komponen & Solusi Utama:

1. **Granular Per-Mechanism & Per-Direction Cooldown Engine (`market_scanner.py`, `config.py`, `.env`)**:
   - `SCANNER_SYMBOL_BREATHING_COOLDOWN_SECONDS = 180` (Jeda bernapas simbol 3 menit untuk mencegah spam token beruntun).
   - `SCANNER_MECHANISM_REJECTION_COOLDOWN_SECONDS = 2700` (Lockout granular 45 menit terpisah per tuple `(symbol, setup_type, direction)`).
   - Penolakan M4 BUY hanya mengunci M4 BUY. M1 BUY/SELL, M2 BUY/SELL, dan M3 BUY/SELL pada simbol yang sama tetap dapat dievaluasi setelah jeda bernapas 3 menit.
   - Lockout level harga fisik di `_retest_rejected_levels` dikhususkan hanya untuk setup bertipe `M3_BREAKOUT_RETEST` / `MULTI_TOUCH_BREAKOUT_RETEST`.
   - Format penyimpanan `data/scanner_cooldowns.json` diperbarui mendukung format granular dengan mempertahankan kompatibilitas mundur.

2. **Stage 1 Radar M4 Flexible Range Discipline (`market_scanner.py`, `config.py`, `.env`)**:
   - `M4_EXTREME_DR_THRESHOLD = 0.70`:
     - M4 BUY di atas 70% Dealing Range (Extreme Premium) di-filter di Stage 1 Radar (0 token), KECUALI jika didukung oleh aliran modal global yang sangat ekstrem (`csm_delta >= +0.035`).
     - M4 SELL di bawah 30% Dealing Range (Extreme Discount) di-filter di Stage 1 Radar (0 token), KECUALI jika didukung oleh `csm_delta <= -0.035`.

3. **Multi-Mechanism Confluence Detection & Dossier Injection (`market_scanner.py`, `src/core/llm_client.py`)**:
   - Sebelum emisi kandidat radar, sistem memeriksa apakah terdapat $\ge 2$ mekanisme yang aktif searah dalam radius $\le 0.35\times\text{ATR}$.
   - Jika terdeteksi, radar menyematkan atribut `multi_confluence = True` dan `confluence_mechanisms` (misal: `['M1_UNIVERSAL_LIQUIDITY_SWEEP', 'M2_PULLBACK', 'M3_BREAKOUT_RETEST']`).
   - Injeksi langsung ke Dossier 3-LLM Jury:
     - Pass 1: Baris `MULTI-MECHANISM CONFLUENCE: ACTIVE (M1+M2+M3 within 0.35xATR)` pada metadata.
     - Pass 2: Parameter `Multi-Mechanism Confluence` pada audit `Trade Specification`.

4. **Sinkronisasi Pemanggilan Rejection Memory (`main.py`)**:
   - Memutakhirkan penanganan VETO Pass 2 dan HOLD konsensus di `main.py` untuk meneruskan `cand.setup_type` dan `cand.direction` ke `scanner_inst.record_setup_rejection()`.

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

---

## 16. 4 September 2026 — Dynamic 3-Point Trajectory Vector Engine, M2+M3 Confluence Fusion & Accurate Origin Tracking

### 🎯 Komponen & Arsitektur Utama:

1. **Pemisahan Titik Origin Breakdown vs Retest Bounce (`market_scanner.py`)**:
   - Memperbaiki algoritma deteksi M3 di `get_radar_standbys()` agar menelusuri mundur riwayat candle fisik:
     * **Titik 1 (Origin Break)**: Mendeteksi bar pertama yang menembus level secara tegas (`origin_time`, `origin_price`, `origin_age`).
     * **Titik 2 (Retest Bounce)**: Mendeteksi bar sentuhan retest terkini (`retest_time`, `retest_price`, `bar_age`).
   - Mengeliminasi anomali loop yang menimpa `event_time` dengan lilin saat ini sehingga label penembusan keliru tertulis `(now)`.

2. **Fusi Konfluensi Otomatis Multi-Setup M2 + M3 (`market_scanner.py` & `dashboard_assets.py`)**:
   - Jika M2 (Pullback EMA) dan M3 (Retest SBR/RBS) bertemu di level yang sama ($\le 0.35\times\text{ATR}$) dengan arah yang sama:
     * Standby ditandai dengan flag `is_confluence = True` dan `confluence_label = "[M2+M3 SELL CONFLUENCE] SBR & EMA Retest"`.
     * Frontend chart hanya menampilkan satu penanda terpadu `[M2+M3 SELL RETEST] SBR & EMA @ level (Nb ago)`, mengeliminasi penumpukan panah ganda yang membingungkan operator.

3. **Dynamic 3-Point Trajectory Vector Engine (`dashboard_assets.py`)**:
   - Kanvas 2D overlay chart TradingView menggambar alur trajektori dinamis bergradasi 3-titik:
     * **Segment 1 (Origin -> Retest)**: Garis putus-putus ungu/cyan beraksen titik awal `1. Break (Nb ago)`.
     * **Segment 2 (Retest Anchor)**: Titik cincin beraksen putih di lilin retest aktif.
     * **Segment 3 (Retest -> Target Projection)**: Garis vektor panah berarah tegas (Hijau BUY / Merah SELL) yang memproyeksikan target ke dinding ZCE terdekat ($F_1/C_1$ atau $F_2/C_2$) dengan label `3. TP Target <price>`.
   - Tergambar mulus 60 FPS saat chart digeser (*pan*) atau di-zoom.

4. **Rich Operational Phase di HUD & Watchlist (`dashboard.py` & `dashboard_assets.py`)**:
   - Header Intel HUD baris kedua diperkaya: label `STATE: CONSOLIDATION_RELOAD` digantikan oleh status alur operasional aktif (`PHASE: RETESTING SBR 181.719 -> TARGET 181.426 [SELL CONFLUENCE]`).
   - Tabel scanner watchlist menyajikan status alur per-pair secara eksplisit (`M2+M3 [BEAR]`, `M3 [BULL]`, dll).

5. **Verifikasi Kuantitatif Penuh**:
   - Seluruh test suite unit test: **115/115 tests PASSED (100% OK)** dalam 27.13s.

