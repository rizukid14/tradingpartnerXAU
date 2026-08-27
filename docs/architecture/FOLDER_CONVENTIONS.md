# Konvensi Arsitektur & Struktur Folder Proyek

> **Standar Arsitektur**: Modular, Terkelompok (*Well-Grouped*), dan Bersih  
> **Status**: ACTIVE PRODUCTION STANDARD  
> **Terakhir Diperbarui**: 27 Agustus 2026

---

## 1. Peta Pohon Direktori (*Directory Tree Structure*)

```text
tradingpartnerXAU/
├── AGENTS.md                  # Master Context & Agent Rules (Wajib dibaca AI sebelum bertindak)
├── README.md                  # Master Repo Overview & Quickstart
├── config.py                  # Single Source of Truth Configuration
├── main.py                    # Production Loop & Bot Runner MT5
├── dashboard.py               # Web Dashboard Monitoring Server
├── dashboard.html             # Web Dashboard UI Template
├── report.html                # Master Quant Dossier (HTML Book Report)
├── requirements.txt           # Python Production Dependencies
├── Dockerfile / compose       # Production Containerization Setup
│
├── 📂 src/                    # PRODUCTION CODE ONLY (Kode bot yang dieksekusi)
│   ├── 📂 core/               # Engine Inti: LLM client, consensus, risk engine, MT5 connector, telegram
│   ├── 📂 analytics/          # Analitik: Macro analyst, currency strength, position manager, trade evaluator
│   └── 📂 indicators/         # Indikator Matematika: Lux SMC, candle quality, sweep detector
│
├── 📂 docs/                   # MASTER DOCUMENTATION (Dokumentasi rapi tematik)
│   ├── README.md              # Master Index Seluruh Dokumen
│   ├── 📂 architecture/       # System blueprint, prompt specs, LLM cost, broker safety, folder conventions
│   ├── 📂 research/           # Research papers, quantitative findings, CSM & Daily Cycle spec
│   ├── 📂 plans/              # RFCs, implementation plans, backlog fitur
│   ├── 📂 deployment/         # Panduan VPS, cron daemon, setup MT5
│   ├── 📂 reports/            # Laporan visual backtest HTML/MD
│   └── 📂 archive/            # Arsip changelog historis (Agustus 2026)
│
├── 📂 scratch/                # EXPERIMENTS & DEVELOPMENT SCRIPTS (Dikelompokkan rapi)
│   ├── 📂 backtests/          # Script runner backtest historis (SMC, CSM, D1/H4/M30)
│   ├── 📂 quick_tests/        # Script verifikasi ad-hoc (test prompt, test live data, inspect logs)
│   ├── 📂 research_tools/     # Data downloaders, pattern miners, whisper generators
│   └── 📂 csv_outputs/        # File output CSV berukuran besar (9MB–11MB)
│
├── 📂 data/                   # DATA RUNTIME & HISTORICAL DATASET
│   ├── 📂 historical/         # Dataset historis offline (FBS multi-year .csv.gz)
│   └── *.json & *.log         # Runtime state files (risk_state, pending_orders, decision_memory)
│
├── 📂 tests/                  # AUTOMATED UNIT TESTS (pytest / unittest suite)
├── 📂 mql5/                   # MT5 Custom Indicators & EAs (.mq5, .ex5)
└── 📂 external_repos/         # Referensi algoritma pihak ketiga (csm.txt Pine Script)
```

---

## 2. Aturan & Konvensi Penempatan File (*Folder Rules*)

### A. Aturan `src/` (Production Code Only)
- **HANYA** berisi kode yang di-import secara langsung oleh `main.py` atau `dashboard.py`.
- **DILARANG** menaruh script pengujian, file scratch, atau eksperimen di dalam `src/`.

### B. Aturan `docs/` (Grouping Tematik)
- Tidak boleh ada file markdown lepas di root `docs/`.
- Setiap dokumen baru **WAJIB** dimasukkan ke subfolder yang sesuai:
  * `docs/architecture/`: Dokumen desain teknis, format prompt, spesifikasi API/broker.
  * `docs/research/`: Laporan riset statistik, temuan edge, backtest multi-tahun.
  * `docs/plans/`: RFC, usulan fitur baru, dan implementation plan.
  * `docs/deployment/`: Setup server, VPS, dan container.
  * `docs/archive/`: Changelog lama dan dokumen historis.

### C. Aturan `scratch/` (Grouping 4 Kategori)
- Semua script eksperimen, riset sementara, dan testing mandiri **WAJIB** masuk ke salah satu dari 4 subdirektori:
  1. `scratch/backtests/` : Runner pengujian strategi historis.
  2. `scratch/quick_tests/` : Script uji coba cepat / smoke test / inspeksi data live.
  3. `scratch/research_tools/` : Script download data, mining pola, dan generator parameter.
  4. `scratch/csv_outputs/` : Tempat penyimpanan file `.csv` hasil eksekusi backtest berukuran besar.

---

## 3. Script Pemeliharaan Otomatis
Jika sewaktu-waktu ada file scratch baru yang tercecer di root `scratch/`, jalankan script perapihan otomatis:
```bash
python scripts/organize_workspace.py
```
