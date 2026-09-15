# PLAN: High-Speed XAUUSD ZCE Sniper Scalper (Demo Lab)

**Status**: DRAFT / PLANNED FOR DEDICATED BRANCH  
**Target Environment**: `VTMarkets-Demo` (#1157958) | Portable Terminal `C:\Users\Daffa\MT5_Demo\terminal64.exe`  
**Live Isolation**: Zero impact pada akun Live Cent (`VTMarkets-Live 3`) dan branch utama `quant-trade-pattern`.

---

## 1. Latar Belakang & Ide Awal

Eksperimen strategi scalping agresif dengan perputaran cepat (*high-speed execution*) pada instrumen Gold (`XAUUSD-ECNc`) untuk menguji kapabilitas eksekusi micro-ZCE, trailing BEP ketat, dan re-entry berulang (*compounding loop*).

---

## 2. Batasan Kuantitatif & Mikrostruktur Broker (VT Markets)

Berdasarkan audit data langsung dari server MT5 VT Markets:
* **Spread Riil (`XAUUSD-ECNc`)**: **11 points** (\$0.11).
* **`TradeStopsLevel`**: **20 points** (\$0.20)  
  *Server MT5 memiliki hard limit jarak minimal 20 points dari harga live untuk pemasangan Stop Loss, Take Profit, maupun modifikasi order.*

### Implikasi Parameter:
1. **Stop Loss Awal**: Ditetapkan minimal **35 points** (\$0.35). Jarak ini aman di atas `TradeStopsLevel` (20 pts) dan memiliki rasio friksi spread $\approx 31\%$.
2. **Take Profit**: Ditetapkan **60 – 70 points** (\$0.60 – \$0.70) untuk menjaga Net R:R $\ge 1.7:1$ s/d $2:1$.
3. **Trigger BEP**: Wajib dipicu saat harga berjalan minimal **+25 points** (\$0.25).  
   *Jika dipicu di bawah 20 points (misal 15 pts), server MT5 akan me-reject request modifikasi dengan Error 10016 (`TRADE_RETCODE_INVALID_STOPS`) karena melanggar `TradeStopsLevel`.*
4. **Buffer BEP**: Geser SL ke `Harga Entry + 2 points` (mengunci profit tipis untuk menutup komisi ECN).

---

## 3. Alur Logika Eksekusi (High-Speed Loop)

```mermaid
flowchart TD
    A[M1 / M5 Micro-ZCE Scanner] -->|Deteksi Wick Rejection di C1/C2 atau F1/F2| B[Eksekusi Jumbo Market Order]
    B --> C[Set SL: -35 pts | TP: +65 pts]
    C --> D{Monitor Harga Live tiap 500ms}
    D -->|Harga mencapai +25 pts| E[Geser SL ke BEP +2 pts]
    D -->|Kena SL / BEP / TP| F[Posisi Closed]
    E -->|Kena TP atau Kena BEP| F
    F -->|Instant Reset Loop| A
```

---

## 4. Rencana Kerja & File yang Akan Dibuat

1. **Git Branching**:
   * Checkout branch baru: `feat/demo-gold-sniper`
   * Memastikan branch `quant-trade-pattern` tetap terisolasi untuk bot Cent.

2. **Konfigurasi Lingkungan (`.env.demo.gold`)**:
   * Simbol: `XAUUSD-ECNc`
   * Magic ID: `20260699`
   * Terminal Path: `C:\Users\Daffa\MT5_Demo\terminal64.exe`
   * SL: 35 points
   * TP: 65 points
   * BEP Trigger: 25 points
   * Sizing: Lot statis atau % margin

3. **Komponen Engine**:
   * `src/demo/gold_sniper_engine.py`: Radar ZCE M1/M5 + listener eksekusi cepat.
   * `main_demo_gold.py`: Runner khusus terminal demo.

---

## 5. Checklist Verifikasi Sebelum Run
- [ ] Tes koneksi IPC ke terminal demo portabel.
- [ ] Validasi order test 0.01 lot untuk memastikan `TradeStopsLevel` (20 pts) tidak terlanggar.
- [ ] Validasi modifikasi BEP saat profit +25 pts.
- [ ] Uji responsivitas re-entry loop saat posisi close.
