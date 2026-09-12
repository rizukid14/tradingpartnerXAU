# Institutional Multi-LLM Quant Trading Bot (MT5)

> Bot trading algoritmik **2-Stage Quant Funnel** berbasis konsensus 3-LLM (OpenAI o4-mini + Google Gemini 3.1-Flash + DeepSeek V4-Flash) dan eksekusi kuantitatif presisi tinggi di **MetaTrader 5 (MT5)**.

---

## 🚀 Fitur Utama

- **2-Stage Quant Funnel**:
  - **Stage 1 (Fast Execution Radar — 0 Token)**: Pemindaian paralel sub-milidetik tiap 60 detik pada **26 FX Pairs** di timeframe **H1** dengan 4 mekanisme kuantitatif: M1 (Universal Liquidity Sweep & SFP), M2 (Trend-Aligned Pullback), M3 (Multi-Touch Breakout Retest), dan M4 (DBD/RBR Breakout Continuation).
  - **Stage 2 (3-LLM Consensus Jury)**: Audit mendalam 2-pass (Pass 1 Macro Tactician + Pass 2 CRO Devil's Advocate) hanya dipicu saat setup Grade A / A+ lolos dari filter fisik. Menghemat ~85% biaya API.
- **Smart Money Concepts (SMC) & Active Dealing Range**:
  - Diadopsi dari Pine Script v6 resmi LuxAlgo ([`src/indicators/lux_smc_official.pine`](src/indicators/lux_smc_official.pine)).
  - Mengunci Dealing Range pada origin impulse breakdown/breakout leg aktif dan pelabelan swing berjenjang (anti-false `HH` pada retracement).
- **Macro Strategic Engine (MSE) & Zone Confluence Engine (ZCE)**:
  - Analisis native 6-timeframe (`MN1`, `W1`, `D1`, `H4`, `H1`, `M30`) memetakan 4 stasiun atap ($C_1..C_4$) dan 4 stasiun lantai ($F_1..F_4$) tanpa ketergantungan API.
- **Currency Basket Synchronization System (CBSS)**:
  - Menghitung runway bilateral antar 8 keranjang mata uang utama, proteksi benteng G3, dan pembatasan eksposur maksimal 2 posisi per keranjang.
- **Multi-Pair Cockpit Dashboard & 8-Gate X-Ray**:
  - Real-time web UI berbasis Lightweight Charts dengan visualisasi 300-bar H1, bilateral runway projection, dan dedicated Economic News Blackout Shield.
- **Virtual Paper Engine (`shadow_tracker`)**:
  - Rotasi BTCUSD 24/7 di akhir pekan dan pengujian sinyal XAUUSD tanpa merisikokan modal akun live Cent.

---

## 📋 Quick Start

### 1. Prasyarat
- Python 3.11+
- MetaTrader 5 Terminal (Desktop Windows) terhubung ke broker `VTMarkets-Live 3`
- API Keys: OpenAI, Google Gemini, DeepSeek (dikonfigurasi di `.env`)

### 2. Instalasi Dependensi
```bash
py -3 -m pip install -r requirements.txt
```

### 3. Konfigurasi Lingkungan (`.env`)
Salin atau sesuaikan `.env` dengan kredensial MT5 dan API key:
```ini
MT5_LOGIN=27556325
MT5_SERVER=VTMarkets-Live 3
MT5_PASSWORD=your_password
TRADING_MODE=scanner
DRY_RUN=False
MAX_POSITION_LOT=0.50
RISK_PERCENT=1.0
```

### 4. Menjalankan Bot
```bash
# Terminal 1: Bot Trading Engine
py -3 main.py

# Terminal 2: Multi-Pair Cockpit Dashboard (Port 8765)
py -3 dashboard.py
```

Buka dashboard di browser: `http://localhost:8765`

---

## 🏛️ Struktur Direktori & Dokumentasi

- [`AGENTS.md`](AGENTS.md) — **Aturan Operasional Wajib AI Agent** (Rule 1 s/d Rule 8, cheat sheet operasional ringkas).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — **Dokumentasi Teknis Lengkap** (derivasi matematis ZCE, SMC, CBSS, SL/TP rules, dan gate eksekusi).
- [`docs/CHANGELOG_SEPTEMBER_2026.md`](docs/CHANGELOG_SEPTEMBER_2026.md) — Catatan historis lengkap pembaruan sistem per September 2026.
- [`src/analytics/market_scanner.py`](src/analytics/market_scanner.py) — Stage 1 Fast Execution Radar.
- [`src/analytics/pattern_engine.py`](src/analytics/pattern_engine.py) — SMC Active Dealing Range & Dynamic Envelope Engine.
- [`src/indicators/lux_smc_official.pine`](src/indicators/lux_smc_official.pine) — Source code resmi Pine Script v6 LuxAlgo Smart Money Concepts.
- [`src/core/llm_client.py`](src/core/llm_client.py) — Stage 2 Multi-LLM Consensus Jury.
- [`src/analytics/position_manager.py`](src/analytics/position_manager.py) — Trailing Stop progresif, BEP, Midday Guard, dan Pre-Rollover Shield.

---

## 🛡️ Aturan Manajemen Risiko Kuantitatif

- **Plafon Lot Akun Cent**: Maksimal $0.50$ lot per posisi.
- **Strict Unanimous 3/3**: Wajib 100% kesepakatan bulat 3 model AI (3/3 BUY atau 3/3 SELL).
- **Circuit Breaker Harian**: Maksimal loss $4\%$ equity harian; lockout profit $7\%$ equity bersih.
- **Dead Zone**: 00:00 – 07:00 WIB pembukaan order baru dinonaktifkan.
- **Pre-Rollover Shield**: Jam 03:50 – 04:15 WIB menutup bersih posisi yang berada dalam jarak bahaya lonjakan spread rollover.
