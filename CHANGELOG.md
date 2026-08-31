# CHANGELOG — Multi-LLM Quant Consensus Trading System

Semua pembaruan, evolusi arsitektur, optimasi kuantitatif, dan bugfix sistem trading bot dicatat secara kronologis di dokumen ini.

---

## Rangkuman Arsitektur Terkini (31 Agustus 2026)

* **2-Stage Quant Funnel**: Universe 26 FX terkurasi dipindai paralel setiap 60 detik (0 token API) oleh Stage 1 Fast Radar. Hanya 8–15 setup Grade S / A+ yang diteruskan ke Stage 2 Triple-LLM Jury.
* **3-LLM Sequential Consensus**: Pass 1 (~3s) paralel `OpenAI o4-mini` (Structure) + `Gemini 3.1-Flash` (Specialist) $\rightarrow$ Pass 2 (~1.5s) `DeepSeek V4-Flash` (Chief Risk Officer & 24-Candle M5 Microscope).
* **Pure Quant 6-TF Native Sockets**: Integrasi komputasi kuantitatif 6 timeframe (`MN1/W1/D1/H4/H1/M30`), SBR/RBS hierarchy, dan continuous macro score $[-1.0, +1.0]$.
* **Apex Paragon Macro Fundamental Engine (40% Weight)**: Ingestion kalender dual-source (ForexFactory + TradingView), exponential half-life decay (4h/12h/36h), 8-currency composite scorecard, dan 7 master risk veto flags.
* **Symmetrical 4D Wave State Engine**: Direction FSM (D1+H4) + Phase FSM (H1 Wave) + Boitoki CSM Pressure + Event Reclaim Layer.
* **5-Layer Risk-Weighted Slot Allocation**: Kuota At-Risk $\le 6$ posisi, Free Runner (TP1+BEP) bebas kuota, plafon akun $\le 8$ posisi, free margin $\ge 60\%$, max 3 posisi per mata uang.
* **Eliminasi Total XAUUSD**: Gold dimatikan permanen per 30 Agustus 2026 setelah audit empiris membuktikan portofolio 26 FX menghasilkan $+\$387.08$ net profit sedangkan Gold menyumbang $-\$1,067.79$ drawdown.

---

## Kronologi Pembaruan (Agustus 2026)

### [30–31 Agustus 2026] — Hybrid Confluence, Apex Fundamental Engine & TSD Master
- **Apex Paragon Fundamental Engine**: Skor fundamental komposit 8 mata uang global berbasis baseline bank sentral, rilis kalender ekonomi, dan live headline TradingView dengan decay waktu eksponensial.
- **Symmetrical Dual-Directional Wave State**: Standardisasi siklus BUY di Diskon Reload dan SELL di Premium SBR Reload.
- **Eliminasi Permanen Gold (`XAUUSD-ECNc`)**: Penutupan total pair Gold dari universe scanner demi menjaga drawdown akun live.
- **Master TSD & Report 2026**: Penerbitan [docs/technical_specification.html](file:///c:/Vibe/tradingpartner/docs/technical_specification.html) (14 Bab) dan [docs/report.html](file:///c:/Vibe/tradingpartner/docs/report.html) (15 Bab).
- **Perbaikan Link & Dokumentasi Proyek**: Standardisasi link lokal di `AGENTS.md`, `docs/README.md`, dan perapian universe 26 simbol FX.

### [29 Agustus 2026] — 6-TF Macro Strategic Engine & 8-Currency Basket Gate
- **Pure Quant Hierarchical MSE (6-TF Native Sockets)**: Komputasi instan $<50\text{ ms}$ pada MN1, W1, D1, H4, H1, M30 dengan dual-grid psychological stations (100-pip major vs 50-pip minor).
- **Universal 8-Currency Basket Flow Circuit Breaker**: Hard lock posisi counter-trend saat terjadi systemic surge/dump ($\pm 20.0$) atau delta divergence ekstrem ($|\Delta| \ge 18.0$).
- **End-to-End Live Multi-LLM Replay Validation**: Validasi audit 11 pair live menghasilkan $+2.85\text{ R}$ net return (+135% vs riwayat live lama).

### [28 Agustus 2026] — LuxSMC, FRVP Confluence & 4-Layer Permission
- **LuxAlgo SMC + FRVP Confluence**: Porting 1:1 LuxAlgo Pine v5 ke Python + Fixed Range Volume Profile (POC/VAL/VAH). Memangkas 59.2% trade noise dan menaikkan EV hingga $+104\%$.
- **4-Layer Trend-Aligned Permission Engine**: Memisahkan Direction Makro dari Trade Permission Intraday. Menghilangkan impulse chase dan waterfall catching.
- **M3 HTF Weekly Wall Reversal**: Menggantikan NY ADR Reversal yang toksik dengan tap dinding H4/D1/W1 $\rightarrow$ foothold 50% equilibrium.
- **Telegram 2-Way Interactive Controller**: Menu keyboard interaktif `[ Menu ]`, `/analisa <symbol>`, `/news`, `/radar`, dan Cyberpunk Bento HUD live ticker.

### [26–27 Agustus 2026] — 2-Stage Quant Funnel & Boitoki CSM
- **2-Stage Quant Funnel (Branch `quant-trade`)**: Transisi dari full-cycle scan ke Stage 1 60s Fast Radar + Stage 2 3-LLM Jury. Menghemat ~85% token API.
- **Boitoki Currency Strength Matrix (CSM)**: Perhitungan Net Delta 8 mata uang intraday untuk memfilter trade yang melawan arah arus modal institusional.
- **Multi-Touch Cluster Breakout & Delayed Retest**: Mekanisme limit order pada retest level cluster setelah breakout momentum.

### [16–25 Agustus 2026] — Dataset FBS 3.78M Bar & Multi-Decade Expansion
- **Multi-Year FBS Backtest Validation**: Pengujian 396.183 trade pada 22 simbol (10.7 tahun H1 & 4.6 tahun M30). Pembuktian empiris H1 > M30 (+22.8% PF).
- **Multi-Decade Macro Expansion**: Pembuktian hukum fraktal: *Macro Expands (Breakout) vs Micro Mean-Reverts*.
- **2-Pass Cross-Examination Consensus**: Desain awal 3-LLM Jury dengan pemisahan peran Structure Analyst vs Devil's Advocate (CRO).

### [8–15 Agustus 2026] — Fase Awal & Fondasi Sistem
- *Rincian lengkap periode ini diarsipkan di [docs/archive/CHANGELOG_AUGUST_2026.md](file:///c:/Vibe/tradingpartner/docs/archive/CHANGELOG_AUGUST_2026.md)*:
  - FASE 1–7: Ekspansi pool 7 simbol, multi-symbol HTF cache, smart timeframe rotation.
  - Pemisahan mode SL/TP per aset dan dynamic lot sizing berbasis risk equity.
  - Integrasi risk engine (max daily loss 4%, profit target 6%, dead zone 02:00–06:00 WIB).

---

## Referensi Dokumen
* **Spesifikasi Teknis Lengkap**: [docs/technical_specification.html](file:///c:/Vibe/tradingpartner/docs/technical_specification.html)
* **Master Quant Research Dossier**: [docs/report.html](file:///c:/Vibe/tradingpartner/docs/report.html)
* **Indeks Master Direktori**: [docs/README.md](file:///c:/Vibe/tradingpartner/docs/README.md)
* **Panduan Operasional AI**: [AGENTS.md](file:///c:/Vibe/tradingpartner/AGENTS.md)
