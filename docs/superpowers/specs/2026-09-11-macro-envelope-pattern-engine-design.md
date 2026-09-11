# Design Spec: Macro Dynamic Envelope & Pattern Recognition Engine

**Date**: 2026-09-11  
**Status**: Draft → Siap Ditinjau  
**Branch**: `quant-trade-pattern`  
**Komponen Terdampak**:
- `src/analytics/pattern_engine.py` [BARU] — Menggantikan modul usang `pattern_detector.py`
- `src/analytics/macro_strategic_engine.py` [INTEGRASI] — Konsumsi Direction Director & Vector Clearance
- `src/analytics/zone_confluence_engine.py` [INTEGRASI] — Penyerapan Rejection/Absorption Wick Density
- `dashboard.py` & `dashboard_assets.py` [VISUAL] — Rendering Dynamic Envelope Ribbon di Lightweight Charts
- `tests/test_pattern_engine.py` [UNIT TEST BARU]

---

## 1. Latar Belakang & Masalah Kuantitatif

Sistem trading membutuhkan pembacaan struktur makro (H4) yang stabil dalam rentang 100 bar (~16.6 hari pasar) untuk:
1. Menentukan apakah instrumen sedang membentuk tren sehat ($\text{HH/HL}$ atau $\text{LH/LL}$) atau kompresi/konsolidasi.
2. Mengukur sisa ruang gerak (*clearance runway*) di dalam lorong harga sebelum membentur plafon atau lantai.
3. Mendeteksi tekanan penolakan (*rejection*) dan penyerapan (*absorption*) melalui rasio akumulasi ekor lilin (*wick*).
4. Menyajikan visualisasi lorong dinamis (*dynamic ribbon*) yang intuitif di Dashboard Cockpit tanpa lag diskret.

### Jebakan Klasik yang Wajib Dieliminasi:
- **Jebakan Repainting Ujung Kurva (Non-Causality)**: Algoritma penghalus kurva (*spline*) standar bersifat dua-arah (*two-sided*). Bar terbaru selalu berubah bentuk setiap ada bar baru masuk. Jika MSE mengambil keputusan arah dari kurva yang berubah-ubah, bot akan mengalami false breakout dan salah arah di live execution.
- **Jebakan Regresi Rata-rata vs Envelope Sejati**: Least-squares spline standar memotong bagian tengah candle (mean regression), bukan membungkus ekor/badan harga.
- **Jebakan Outlier Rollover**: Lonjakan spread/gap likuiditas sesaat (terutama pada pair CHF di jam 03:55–04:15 WIB) merusak deteksi swing jika tidak difilter.

---

## 2. Arsitektur Inti: Decoupled Dual-Track Architecture

Untuk memecahkan dilema antara **estetika visual yang mulus** dan **keamanan eksekusi live yang anti-repainting**, sistem dipecah menjadi dua jalur independen:

```
                            ┌────────────────────────────────────────────────────────┐
                            │                    Raw 100 Bar H4                      │
                            └──────────────────────────┬─────────────────────────────┘
                                                       │
                                        [Outlier & Rollover Filter]
                                        (MAD / ATR-Winsorizing)
                                                       │
                           ┌───────────────────────────┴───────────────────────────┐
                           ▼                                                       ▼
        ┌──────────────────────────────────────┐               ┌──────────────────────────────────────┐
        │ Track A: Causal Decision Engine      │               │ Track B: Visual Ribbon Generator     │
        │ (Untuk MSE & ZCE — 100% Anti-Repaint)│               │ (Untuk Dashboard UI — Smooth & Fluid)│
        ├──────────────────────────────────────┤               ├──────────────────────────────────────┤
        │ • Causal ATR-Pivot (HH, HL, LH, LL)  │               │ • Rolling Extremum Envelope (Quantile│
        │ • Provisional Bar Status Tagging     │               │ • Savitzky-Golay / Spline Smoothing  │
        │ • Wick Rejection/Absorption Matrix   │               │ • Continuous Ribbon (Upper/Lower)    │
        │ • Directional Probability Vector     │               │ • Translucent Wick Cloud Coordinates │
        └──────────────────┬───────────────────┘               └──────────────────┬───────────────────┘
                           │                                                       │
                           ▼                                                       ▼
             [MSE & ZCE Integration]                                   [Dashboard Lightweight Charts]
```

---

## 3. Formulasi Matematis & Alur Algoritma

### 3.1. Pra-pemrosesan & Penyaringan Outlier (Robust Statistics)
Untuk setiap bar $t \in [0, 99]$ pada H4:
1. Hitung $\text{ATR}_{14}$ pada timeframe H4.
2. Identifikasi bar rollover (03:55–04:15 WIB).
3. Jika selisih ekor $(H_t - \max(O_t, C_t)) > 2.5 \times \text{ATR}$ atau $(\min(O_t, C_t) - L_t) > 2.5 \times \text{ATR}$ pada jendela rollover / spread spike, ekor tersebut di-*winsorize*:
   $$H_t^{\text{clean}} = \max(O_t, C_t) + \min(H_t - \max(O_t, C_t), 1.5 \times \text{ATR})$$
   $$L_t^{\text{clean}} = \min(O_t, C_t) - \min(\min(O_t, C_t) - L_t, 1.5 \times \text{ATR})$$

### 3.2. Track A: Causal Quantitative Engine (Logika Eksekusi)
1. **Ekstraksi Pivot Kausal ($N=3$ bar konfirmasi)**:
   - Titik puncak lokal $P_k$ dan lembah lokal $V_k$ hanya dikonfirmasi jika telah tertutup 3 bar di kanannya.
   - Bar $t \in [97, 99]$ diklasifikasikan sebagai status `PROVISIONAL` (tidak boleh mengubah status tren makro secara prematur).
   - Klasifikasi:
     - $P_k > P_{k-1} \implies \text{HH}$; $P_k < P_{k-1} \implies \text{LH}$
     - $V_k > V_{k-1} \implies \text{HL}$; $V_k < V_{k-1} \implies \text{LL}$
2. **Wick Rejection & Absorption Density Matrix**:
   - Ketebalan ekor atas dinormalisasi:
     $$\rho_{\text{reject}}(t) = \frac{H_t^{\text{clean}} - \max(O_t, C_t)}{\text{ATR}_{14}}$$
   - Ketebalan ekor bawah dinormalisasi:
     $$\rho_{\text{absorb}}(t) = \frac{\min(O_t, C_t) - L_t^{\text{clean}}}{\text{ATR}_{14}}$$
   - Akumulasi 10-bar terakhir:
     $$\text{Net\_Wick\_Delta} = \sum_{t=90}^{99} \rho_{\text{absorb}}(t) - \sum_{t=90}^{99} \rho_{\text{reject}}(t)$$
     - $\text{Net\_Wick\_Delta} > +1.5$: Tekanan beli bawah kuat (Bullish Absorption).
     - $\text{Net\_Wick\_Delta} < -1.5$: Tekanan jual atas kuat (Bearish Rejection).

### 3.3. Track B: Visual Manifold Ribbon (Visual Dashboard)
1. **Rolling Extremum Bounding (True Envelope)**:
   $$U_{\text{raw}}(t) = \max_{i \in [t-2, t]} (\max(O_i, C_i))$$
   $$L_{\text{raw}}(t) = \min_{i \in [t-2, t]} (\min(O_i, C_i))$$
2. **Smoothing Filter (Savitzky-Golay / Cubic Spline)**:
   - Diterapkan pada $U_{\text{raw}}$ dan $L_{\text{raw}}$ dengan jendela lokal 7-bar dan derajat polinomial 2.
   - Menghasilkan dua kurva halus kontinu: $U(t)$ (Upper Body Ribbon) dan $L(t)$ (Lower Body Ribbon).
   - Batas ekor luar: $U_{\text{wick}}(t)$ dan $L_{\text{wick}}(t)$ diekspor sebagai area pita transparan.

### 3.4. Topologi Ruang & Confluence dengan ZCE / MSE
1. **Posisi Relatif dalam Lorong**:
   $$\tau(t) = \frac{P_{\text{curr}} - L(t)}{U(t) - L(t)} \in [0.0, 1.0]$$
2. **Clearance Runway**:
   $$R_{\text{up}} = U(t) - P_{\text{curr}}, \quad R_{\text{down}} = P_{\text{curr}} - L(t)$$
3. **Kombinasi dengan ZCE**:
   - Jika $\tau(t) \le 0.25$ (dekat lantai lorong) dan di ZCE terdapat lantai $F_1$ aktif dalam radius $0.35 \times \text{ATR}$, serta $\text{Net\_Wick\_Delta} > 0 \implies$ Peluang Pantulan Beli (**High-Probability Floor Rebound**).
   - Jika $U'(t) < 0$ dan $L'(t) < 0$ (lorong miring ke bawah), namun harga sedang retest ke $U(t)$ dan $C_1$ masih berada di atasnya $\implies$ Skenario *"Naik dulu baru turun"* (**Retest-then-Drop Directive**).

---

## 4. Struktur Data Output (Zero Token, Sub-Milidetik)

Modul `src/analytics/pattern_engine.py` menghasilkan dataclass:

```python
@dataclass
class MacroEnvelopeResult:
    symbol: str
    timeframe: str = "H4"
    structural_trend: str          # "BULLISH_EXPANSION" (HH+HL), "BEARISH_EXPANSION" (LH+LL), "COMPRESSION", "RANGING"
    instantaneous_slope: float     # Turunan pertama dS/dt (pips/bar)
    curvature: float               # Turunan kedua d2S/dt2 (akselerasi/deselerasi)
    channel_position_tau: float    # 0.0 (lantai) hingga 1.0 (plafon)
    net_wick_delta: float          # Akumulasi absorpsi vs rejection 10-bar
    clearance_up_pips: float       # Jarak ke plafon ribbon
    clearance_down_pips: float     # Jarak ke lantai ribbon
    provisional_state: str         # "CONFIRMED" atau "PENDING_BAR_CLOSE"
    
    # Payload serializable untuk Dashboard
    visual_payload: dict = field(default_factory=dict)
```

---

## 5. Rencana Implementasi & Pengujian

1. **Pembersihan Modul Usang**:
   - Menghapus `src/analytics/pattern_detector.py` dan `src/analytics/whisper_registry.json`.
2. **Pembuatan Modul Baru `src/analytics/pattern_engine.py`**:
   - Mengimplementasikan `MacroEnvelopeEngine` dengan Track A (Causal Quant) dan Track B (Visual Ribbon).
3. **Penyelarasan ke `macro_strategic_engine.py`**:
   - Mengintegrasikan `MacroEnvelopeResult` sebagai parameter penentu arah makro dan clearance filter.
4. **Penyelarasan ke Dashboard (`dashboard.py` & `dashboard_assets.py`)**:
   - Menyediakan endpoint API data ribbon dan script Lightweight Charts untuk merender visual ribbon H4 secara real-time.
5. **Unit Test Suite (`tests/test_pattern_engine.py`)**:
   - Uji pembersihan outlier (CHF rollover).
   - Uji kekebalan repainting (memastikan confirmed pivots tidak berubah bentuk saat bar baru ditambahkan).
   - Uji kalkulasi rasio wick-to-body.
   - Uji performa kalkulasi $\le 5\text{ ms}$ untuk 100 bar.
