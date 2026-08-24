# Dokumentasi Proyek Trading Bot Multi-LLM

Selamat datang di pusat dokumentasi bot trading MetaTrader 5 dengan arsitektur **Multi-LLM Consensus**. Seluruh materi, riset kuantitatif, rancangan arsitektur, dan referensi telah dikelompokkan ke dalam direktori tematik berikut:

---

## 🗂️ Direktori Dokumentasi

```
docs/
├── 📂 architecture/   # Desain teknis sistem, skema prompt LLM, blueprint, & estimasi biaya
├── 📂 research/       # Riset statistik 3-4 tahun, temuan edge, perankingan pair, & hasil backtest
├── 📂 plans/          # RFC fitur baru, rancangan eksperimen, & rencana implementasi aktif
├── 📂 deployment/     # Panduan operasional dan panduan deployment bot ke VPS
├── 📂 reference/      # Buku trading (PDF), Expert Advisor MT5 (.mq5/.ex5), & spesifikasi UI
└── 📂 archive/        # Arsip histori changelog (8-15 Agustus) dan dokumen lawas
```

---

## 📚 Daftar Dokumen Lengkap

### 1. 🏗️ Architecture (`docs/architecture/`)
* [blueprint.md](file:///c:/Vibe/tradingpartner/docs/architecture/blueprint.md) — Cetak biru awal dan rancangan arsitektur dasar sistem bot.
* [PROMPT_COMPARISON.md](file:///c:/Vibe/tradingpartner/docs/architecture/PROMPT_COMPARISON.md) — Riwayat perbandingan skema JSON output prompt antar iterasi.
* [prompt_claude.md](file:///c:/Vibe/tradingpartner/docs/architecture/prompt_claude.md) — Referensi skema prompt khusus Claude Sonnet / Haiku.
* [LLM_COST_ESTIMATION.md](file:///c:/Vibe/tradingpartner/docs/architecture/LLM_COST_ESTIMATION.md) — Simulasi kuota token, frekuensi call harian, dan perbandingan biaya API bulanan (DeepSeek vs Claude).

### 2. 📊 Research (`docs/research/`)
* [LLM_PROMPT_BENCHMARK_EXPERIMENTS.md](file:///c:/Vibe/tradingpartner/docs/research/LLM_PROMPT_BENCHMARK_EXPERIMENTS.md) — **Riset & Eksperimen Benchmark LLM (Agustus 2026)**: Hasil pengujian empiris diagnostik 4 model AI (o4-mini, Gemini, Claude, DeepSeek), perbandingan Structured JSON CoT vs Anti-Paralysis Directive, dan Master Matrix 36 evaluasi di pool bot.
* [QUANT_RESEARCH_EDGES.md](file:///c:/Vibe/tradingpartner/docs/research/QUANT_RESEARCH_EDGES.md) — Hasil riset statistik 3–4 tahun bebas bias (*lookahead-bias-free*), 112 Edge Bearish NY, perankingan pair Forex, riset CAD/EUR/GBP, JPY, dan Donchian XAU BUY NY.
* [backtest_augustus_2026.md](file:///c:/Vibe/tradingpartner/docs/research/backtest_augustus_2026.md) — Hasil backtest 10 strategi buku (NotebookLM), erratum S9 Horn, dan verifikasi S9 HTF Structural Target pada GBPUSD.
* [hasilnotebooklm.md](file:///c:/Vibe/tradingpartner/docs/research/hasilnotebooklm.md) — Ekstraksi 10 strategi teknikal dari literatur buku trading via Google NotebookLM.

### 3. 💡 Plans & RFCs (`docs/plans/`)
* [IDEAS_AND_PLANS.md](file:///c:/Vibe/tradingpartner/docs/plans/IDEAS_AND_PLANS.md) — **Backlog Ide & RFC**:
  * **RFC 1**: One-Shot Emergency Drawdown Re-Evaluator (80% SL + High-Density Prompt Makro H4/D1 & M15).
  * **RFC 2**: Refaktorisasi Konsensus Pending vs Market (Kuorum limit vs stop vs market fallback).
  * **RFC 3**: Parabolic Filter di Position Manager (Rayner Teo).
  * **RFC 4**: Anti-Hedge Gate per Simbol.
* [implementation_plan_pattern_whisper.md](file:///c:/Vibe/tradingpartner/docs/plans/implementation_plan_pattern_whisper.md) — Rencana implementasi integrasi bisikan pola kuantitatif ke dalam prompt LLM.

### 4. 🚀 Deployment (`docs/deployment/`)
* [vps_deployment.md](file:///c:/Vibe/tradingpartner/docs/deployment/vps_deployment.md) — Panduan lengkap konfigurasi dan deployment bot serta MetaTrader 5 di server VPS.

### 5. 📖 Reference (`docs/reference/`)
* **`books/`** — Kumpulan 11 e-book trading referensi (Candlestick Bible, Rayner Teo Trend Line/Breakout/Price Action, S&D, dll).
* **`specs/`** — [2026-08-09-trading-dashboard-design.md](file:///c:/Vibe/tradingpartner/docs/reference/specs/2026-08-09-trading-dashboard-design.md) (Spesifikasi desain UI/UX Dashboard monitoring).
* **`trading-robots/`** — Kode sumber Expert Advisor MT5 (.mq5, .ex5) dan panduan optimasi EA.

### 6. 📜 Archive (`docs/archive/`)
* [CHANGELOG_AUGUST_2026.md](file:///c:/Vibe/tradingpartner/docs/archive/CHANGELOG_AUGUST_2026.md) — Arsip detail perubahan historis bot periode 8–15 Agustus 2026 (FASE 1–7, pemisahan mode SL/TP, evolusi lot sizing).
