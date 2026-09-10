# Spec: Quant Shadow Executive Audit & Interactive Dashboard

- **Date**: 2026-09-09
- **Author**: Antigravity & RizqyDaffa
- **Target Repository**: `tradingpartnerXAU` (branch `quant-trade-noAI`)
- **Status**: Draft Spec (Awaiting User Review)

---

## 1. Executive Summary & Problem Statement

### 1.1 Context
Sistem trading bot beroperasi menggunakan arsitektur **2-Stage Quant Funnel**:
- **Stage 1 Fast Radar**: Memindai 26 simbol FX + BTC tiap 60 detik melalui 4 mekanisme kuantitatif (M1 Universal Liquidity Sweep, M2 Trend-Aligned Pullback, M3 Breakout Retest, M4 Systemic Flow Continuation).
- **Stage 2 MT5 Execution**: Terikat oleh batasan institusional ketat (`MAX_OPEN_POSITIONS = 6`, filter spread, dead zone, runway ZCE, directional lock).
- **Quant Shadow Tracker (`shadow_tracker.py`)**: Bertugas sebagai *unconstrained observer* yang mencatat 100% peluang Stage 1 secara paralel tanpa terhalang batasan slot MT5, menyimpan telemetri ke `data/quant_shadow_trades.jsonl` dan `data/quant_shadow_state.json`.

### 1.2 Identified Problems & Needs
1. **Bias Amplifikasi Tiket Duplikat**: Audit telemetri menemukan bahwa pada gelombang tren panjang (misal penurunan JPY), re-trigger radar setiap 30 menit menghasilkan multi-tiket pada simbol dan arah yang sama (misal 4 tiket `CHFJPY SELL` aktif beriringan). Jika dihitung mentah tanpa de-biasing, performa leg tersebut teramplifikasi secara semu.
2. **Kebutuhan Evaluasi Opportunity Cost**: Pengguna membutuhkan data empiris untuk menjawab:
   - Apakah gate pembatas (`MAX_OPEN_POSITIONS = 6`, `ANCHOR_TOO_WIDE`, filter risk) menyelamatkan modal (*Capital Saved*) atau membuang potensi keuntungan (*Lost Opportunity*)?
   - Mekanisme mana (M1, M2, M3, M4) dan Tier mana (`GRADE_S`, `GRADE_A_PLUS`, `GRADE_A`, `GRADE_B`) yang memiliki edge statistik tertinggi?
   - Apakah trailing stop dan ambang BEP (35% vs 50% TP) sudah optimal atau memicu *premature lock / stolen runner*?
3. **Kebutuhan Penyajian Data Eksekutif**: Diperlukan alat analitik CLI mandiri (`py shadow_audit.py`) dan **Executive Dashboard HTML Interaktif** (`docs/shadow_executive_audit.html`) yang menyajikan visualisasi tingkat institusional dengan toggle instan *De-biased Leg* vs *Raw Signals*.

---

## 2. System Architecture & File Structure

```
tradingpartnerXAU/
├── shadow_audit.py                                # CLI Entry point (py shadow_audit.py [--open])
├── src/
│   └── analytics/
│       ├── shadow_audit_engine.py                # Pure Quant Analytics & HTML Generation Engine
│       └── shadow_tracker.py                     # Source of telemetry state & trades
├── docs/
│   └── shadow_executive_audit.html               # Generated Interactive Standalone Dashboard
└── tests/
    └── test_shadow_audit_engine.py               # 100% Passing Unit Test Suite
```

---

## 3. Data Pipeline & De-biasing Algorithm

### 3.1 Data Ingestion
Modul `shadow_audit_engine.py` membaca:
1. `data/quant_shadow_trades.jsonl`: Seluruh trade yang telah selesai (`RESOLVED`).
2. `data/quant_shadow_state.json`: Trade yang sedang berjalan (`ACTIVE` dan `PENDING`).
3. `mt5_connector.get_closed_positions_today(lookback_hours=168)`: Data real deal MT5 untuk benchmarking 1:1.

### 3.2 Dual-Mode Engine

#### Mode A: Raw Signals
- Memproses setiap record trade secara terpisah persis seperti yang dihasilkan oleh Stage 1 Fast Radar.
- Menghitung frekuensi trigger murni per pair dan per mekanisme.

#### Mode B: De-biased Trade Legs (Pure Quant Benchmark)
- **Aturan Pengelompokan (Consolidation)**:
  Jika terdapat 2 atau lebih tiket dengan:
  - `symbol` yang sama,
  - `direction` yang sama (`BUY` atau `SELL`),
  - Rentang waktu overlap: Waktu `created_at` tiket baru terjadi saat tiket sebelumnya masih dalam status `ACTIVE` atau `fill_time` hingga `resolved_time` saling beririsan.
- **Konsolidasi Nilai Leg**:
  - `entry_price`: Entry dari tiket pelopor (tiket pertama pada leg tersebut).
  - `net_r`: Rata-rata dari realized Net R tiket-tiket dalam leg tersebut.
  - `peak_mfe_r`: Nilai $\max(\text{peak\_mfe\_r})$ di antara tiket-tiket dalam leg.
  - `max_mae_r`: Nilai $\min(\text{max\_mae\_r})$ di antara tiket-tiket dalam leg.
  - `outcome`: Diambil dari hasil tiket yang paling representatif (misal jika salah satu TP dan yang lain BEP, leg diklasifikasikan sebagai `TP_HIT` dengan Net R rata-rata).
  - `ticket_count`: Jumlah tiket yang dikonsolidasikan (sebagai indikator intensitas tren).

---

## 4. Quantitative Metrics & Mathematical Formulations

### 4.1 Wilson Score 95% Confidence Interval untuk Win Rate
Untuk menghindari overclaim pada sampel kecil:
$$\hat{p} = \frac{W + \frac{z^2}{2}}{N + z^2} \pm \frac{z}{N + z^2} \sqrt{\frac{W(N - W)}{N} + \frac{z^2}{4}}$$
dengan $z = 1.96$ untuk Confidence Interval 95%, di mana $W$ adalah jumlah kemenangan (TP), dan $N$ adalah jumlah trade yang *decisive* (TP + SL).

### 4.2 Counterfactual Opportunity Cost ($\Delta R$)
$$\Delta R_{\text{gate}} = \sum_{t \in \text{SKIPPED\_GATE}} \text{Net\_R}(t)$$
- $\Delta R > 0$: **Lost Opportunity** (Pembatasan gate menahan potensi laba).
- $\Delta R < 0$: **Capital Saved** (Gate berhasil menyelamatkan akun dari kerugian).

### 4.3 BEP Protection Index
Dari seluruh trade yang berstatus `BEP_HIT`:
- **`SAVED_BY_BEP`**: $\text{MAE} \le -1.0R$ (Harga setelah kena BEP melanjutkan kejatuhan hingga menabrak zona SL awal).
- **`STOLEN_RUNNER`**: $\text{MFE} \ge \text{Target R}$ (Harga setelah kena BEP berbalik dan melesat menuju target TP awal).
$$\text{BEP Efficiency Ratio} = \frac{\text{Count}(\text{SAVED\_BY\_BEP})}{\text{Count}(\text{SAVED\_BY\_BEP}) + \text{Count}(\text{STOLEN\_RUNNER})} \times 100\%$$

### 4.4 Excursion Analytics
- **Safe Excursion Envelope**: Menghitung persentil ke-90 dari MAE pada trade yang berakhir TP. Jika MAE 90th percentile hanya $-0.45R$, membuktikan bahwa Stop Loss $1.0R$ memiliki *safety margin* $55\%$ yang sehat.

---

## 5. User Interface & Executive Dashboard Specification

### 5.1 Design Aesthetics (Anti-UI-Slop Guidelines)
- **Tema Visual**: Institutional Trading Dark Theme.
  - Base Background: `#080b11`
  - Card/Surface: `#0f1523`
  - Border: `#1a2333`
  - Accents: Hijau `#00e676`, Merah `#ff5252`, Cyan `#38bdf8`, Emas `#ffd740`, Ungu `#b388ff`.
- **Tipografi**:
  - Teks: `'Inter', sans-serif`
  - Angka & Data Finansial: `'JetBrains Mono', monospace`
- **Iconography**: 0% emoji basi; 100% Google Material Symbols dan micro SVG badges.

### 5.2 Layout Components
1. **Header & Navigation**:
   - Status snapshot timestamp & broker account sync.
   - **Interactive Switch**: `[ De-biased Legs ]` vs `[ Raw Signals ]` (re-render visual instan via JavaScript).
   - Time Filters: `All`, `Last 48h`, `Today`.
   - Setup & Pair Filters.
2. **Row 1 — 5 KPI Cards**:
   - Real MT5 Profit (USD & Realized R).
   - Decisive Win Rate (dengan Wilson 95% CI badge).
   - Profit Factor & Expected Value ($EV$).
   - Net Opportunity Cost ($\Delta R$).
   - BEP Protection Index (% Saved vs % Stolen).
3. **Row 2 — Dual Interactive Charts (Chart.js 4.x)**:
   - **Chart A**: Comparative Cumulative Equity Curves (`EXECUTED_MT5` vs `SKIPPED_MAX_POSITIONS` vs `TOTAL_UNCONSTRAINED`).
   - **Chart B**: Gate Disposition Breakdown (Diagram batang horizontal per alasan skip).
4. **Row 3 — Deep-Dive Edge & Scatter**:
   - **Chart C**: Mechanism Performance (M1 vs M2 vs M3 vs M4 Net R & Win Rate).
   - **Chart D**: MFE vs MAE Scatter Plot (Setiap trade di-plot titiknya untuk melihat kurva ekskursi).
5. **Row 4 — Interactive Data Explorer (Table)**:
   - Full sortable columns, live search bar, outcome badges, filter per status.

---

## 6. CLI Terminal Output Specification

Perintah:
```powershell
py shadow_audit.py [--open]
```
Output terminal:
```text
+-- [ QUANT SHADOW EXECUTIVE AUDIT ] ------------------------------------+
| Audit Time   : 2026-09-09 09:50 WIB | Sample: 169 Resolved Trades      |
+------------------------------------------------------------------------+
| • Data Mode      : DE-BIASED LEGS (102 Legs) vs RAW (169 Triggers)     |
| • Live MT5 Deals : 59 Deals | Win: 69.5% | Net: +$285.48 (PF 1.22)     |
| • Opportunity    : Lost Profit (+14.2R) | Saved Capital (+8.5R)        |
| • Top Edge       : M2 Pullback (71.4% Winrate | PF 2.15)               |
| • BEP Efficiency : 76.2% Saved by BEP vs 23.8% Stolen Runner          |
+------------------------------------------------------------------------+
 [OK] Executive Dashboard generated: docs/shadow_executive_audit.html
 [BROWSER] Auto-launching dashboard in default browser...
```

---

## 7. Verification & Testing Plan

1. **Unit Test Suite (`tests/test_shadow_audit_engine.py`)**:
   - Test data ingestion from JSONL and state JSON.
   - Test de-biasing algorithm (verifikasi bahwa overlapping trades pada pair & arah yang sama terkonsolidasi dengan benar).
   - Test formula matematis (Wilson Score CI, Opportunity Cost Delta, BEP Efficiency).
   - Test HTML rendering integrity (pastikan output HTML valid dan memuat payload JSON lengkap).
   - Pastikan **100% PASS** di unit test suite.
2. **End-to-End Execution**:
   - Jalankan `py shadow_audit.py` di terminal.
   - Verifikasi file `docs/shadow_executive_audit.html` terbuat dan terisi data live yang sinkron dengan MT5.
   - Buka di browser dan uji toggle *De-biased vs Raw*, filter pencarian, dan interaktivitas chart.
