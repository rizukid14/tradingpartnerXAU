# FORENSIC REPORT & RESEARCH: TRADE GEOMETRY RECONSTRUCTION & STRUCTURAL DECOUPLING

> **Document Type**: Quantitative Architecture & Trade Geometry Research  
> **Date**: 11 September 2026  
> **Dataset**: $N=101$ Executed Trades (76 Demo, 19 Live Cent VTMarkets-Live 3, 6 Transitional) & $N=360-444$ Historical Telemetry Pool  
> **Primary File Reference**: `atlas_dna.py`, `consensus.py`, `position_manager.py`, `market_scanner.py`, `risk_engine.py`  
> **Objective**: Cross-AI Knowledge Synchronization, Rigorous Hypothesis Testing, Elimination of Baseline Disparities, and Ground-Truth Architecture Consensus.

---

## 1. KOREKSI KUANTITATIF & KALIBRASI SAINTIFIK (RULE 6 AGENTS.md)

Sebagai wujud komitmen terhadap standar berpikir kuantitatif rigorous, laporan ini mengoreksi 3 kekeliruan analitis dari iterasi sebelumnya:

### A. Koreksi Peluang Bersyarat: P(Menang | MAE ≥ 0.50×ATR) = 37.8% (Bukan <10%)
* Klaim sebelumnya: *"Peluang menang < 10% setelah harga menembus 0.50×ATR"* adalah **kekeliruan pembalikan probabilitas bersyarat (Inversion Fallacy)** antara $P(\text{MAE} \ge 0.5 \mid \text{Win})$ dan $P(\text{Win} \mid \text{MAE} \ge 0.5)$.
* **Uji Empiris Sejati ($N=360-444$)**:
  ```
  ┌────────────┬─────┬────────┬─────────────────────┐
  │ Ambang MAE │ n   │ Menang │ P(Menang | MAE ≥ x) │
  ├────────────┼─────┼────────┼─────────────────────┤
  │ ≥0.50×ATR  │ 164 │ 62     │ 37.8%               │
  │ ≥0.75×ATR  │ 132 │ 40     │ 30.3%               │
  │ ≥1.00×ATR  │ 110 │ 28     │ 25.5%               │
  │ ≥1.50×ATR  │ 66  │ 8      │ 12.1%               │
  └────────────┴─────┴────────┴─────────────────────┘
  ```
* **Biaya Fatal SL 0.50×ATR**: Menetapkan SL pada $0.50\times\text{ATR}$ akan **membunuh 62 dari 249 trade pemenang (24.9%)** dan membuang profit terealisasi sebesar **$+21.8R$**.
* **Statistik P75 MAE = 0.48×ATR**: Justru membuktikan bahwa $25\%$ dari pemenang sah membutuhkan ruang bernapas lebih dari $0.48\times\text{ATR}$ sebelum akhirnya mencetak TP.

### B. Koreksi Baseline dan Pembatalan Klaim Delta "+47.8R"
* Baseline $-1.9R$ (WR 39.7%) pada simulasi sebelumnya berasal dari subset yang tidak sebanding dengan populasi dataset penuh (yang aslinya bernilai $+27.05R$, WR 69.2%).
* Oleh karena itu, klaim delta $+47.8R$ ditarik kembali karena dibangun di atas disparitas basis populasi.

### C. Penolakan Ambang SL 0.50×ATR $\rightarrow$ Adopsi Titik Keseimbangan 1.00×ATR
```
┌──────────┬───────────────────┬─────────────────┐
│ Skala SL │ Pemenang Terbunuh │ Trade yang Aman │
├──────────┼───────────────────┼─────────────────┤
│ 0.50×ATR │ 62 (24.9%)        │ 75.1%           │
│ 0.75×ATR │ 40 (16.1%)        │ 83.9%           │
│ 1.00×ATR │ 28 (11.2%)        │ 88.8%           │
│ 1.50×ATR │ 8  (3.2%)         │ 96.8%           │
└──────────┴───────────────────┴─────────────────┘
```
* **Kesimpulan Dosis Stop Loss**:
  * SL $0.50\times\text{ATR}$ membunuh 1 dari 4 trade pemenang (terlalu sempit / *over-pruning*).
  * SL $1.00\times\text{ATR}$ hanya memangkas 1 dari 9 trade pemenang ($88.8\%$ aman), sekaligus memangkas separuh dari pemborosan SL lama ($2.08\times\text{ATR}$).
  * Titik awal yang didukung data adalah **$1.00\times\text{ATR}$**, bukan $0.50\times\text{ATR}$.

---

## 2. DEKOMPOSISI KAUSAL 2x2: JARAK TARGET & JENDELA LONDON 15–17 WIB

Data 101 trade memisahkan kontribusi jarak dan jam secara aditif dan independen:

```
┌───────────────────────────────────────┬────┬───────────┬────────┬──────────┐
│ Matriks 2x2: Jarak vs Jam             │ n  │ Net P/L   │ WR (%) │ PF       │
├───────────────────────────────────────┼────┼───────────┼────────┼──────────┤
│ TP ≥ 2.5×ATR  DAN  London 15–17 WIB   │ 13 │ -$676.13  │ 38.5%  │ 0.38     │
│ TP ≥ 2.5×ATR  (Bukan London 15–17)    │ 43 │ -$151.86  │ 53.5%  │ 0.88     │
│ TP < 2.5×ATR  DAN  London 15–17 WIB   │ 4  │ -$220.66  │ 50.0%  │ 0.42     │
│ TP < 2.5×ATR  (Bukan London 15–17)    │ 38 │ +$454.40  │ 73.7%  │ 2.49     │
└───────────────────────────────────────┴────┴───────────┴────────┴──────────┘
```

### Temuan Seleksi vs Paksaan (Selection vs Forcing):
* Menurunkan TP secara artifisial (capping $1.25R$ atau $1.50R$) pada trade yang aslinya menarget jauh hampir tidak memberi delta (+0.85R).
* Cohort $TP < 2.5\times\text{ATR}$ profit bukan karena TP-nya dipotong di tengah jalan, melainkan karena **struktur stasiun ZCE-nya memang secara alami dekat sejak awal**.
* **Prinsip Radar**: Saring radar untuk memprioritaskan setup yang dinding ZCE-nya secara alami $< 2.5\times\text{ATR}$.

---

## 3. SOLUSI ARSITEKTUR KONSENSUS LENGKAP (THE UNIFIED BLUEPRINT)

Berikut adalah konsensus arsitektur terpadu yang disepakati oleh seluruh agen AI:

### A. Pilar 1: Pisahkan Kontrol Lot Size dari Geometri SL (Separation of Concerns)
* **Dilarang memperlebar SL demi menahan lot akun Cent!**
* Hapus ketergantungan pada floor statis 120/180/250 pts.
* Kunci batas lot secara langsung di **`src/core/risk_engine.py`**:
  $$\text{MAX\_POSITION\_LOT} = 0.40\text{ lot}$$
  $$\text{Calculated Lot} = \min\left(\frac{\text{Equity} \times \text{Risk\%}}{\text{SL Pts} \times \text{USD/pt}}, 0.40\right)$$

### B. Pilar 2: Dekopling TP dari Kelipatan Mekanis SL
* Hapus klausul `if tp_points < min_tp: tp_points = min_tp` di `src/core/consensus.py`.
* Biarkan dinding ZCE ($C_1/F_1$) memegang kendali penuh atas TP. Jangan memaksakan TP melompati dinding jika tidak ada rezim ekspansi.

### C. Pilar 3: Floor Turunan Friksi (Friction-Derivative Floor)
Floor SL tidak boleh dilepas mentah (mencegah beban komisi broker melonjak ke $25\% - 36\%$ saat SL sangat rapat), melainkan dikontrol oleh rumus turunan friksi:
$$\text{SL}_{\min} = \frac{\text{Spread Pts} + \text{Komisi Pts}}{\text{FRICTION\_FLOOR\_DIVISOR}} = \frac{\text{Spread Pts} + 6\text{ pts}}{0.20}$$

**Kalibrasi divisor (terverifikasi 27 simbol live MT5)**:
* **`0.20` adalah nilai final** — **0/27 simbol** membuat floor mengikat di atas ATR H1, sekaligus menahan beban friksi $\le 20\%$.
* Usulan `0.12` **dibatalkan**: membuat floor mengikat di 6/27 simbol volatilitas rendah (EURCAD 1.24×, USDCAD 1.09×, GBPCAD 1.09×, EURGBP 1.06×, AUDCAD 1.04×, EURUSD 1.03×) dan median SL naik 101 → 103 pts tanpa manfaat terukur.
* Usulan `0.25` **dibatalkan**: hasilnya identik dengan `0.20` (0/27 mengikat, median SL 101 pts).
* Catatan: premis awal `SL_min EURUSD = 175 pts` **tidak berlaku** — berbasis spread $15\text{ pts}$, padahal spread EURUSD terekam **2 pts** (median 18 trade minggu ini; snapshot live 1 pt).

### D. Pilar 4: Formula Geometri SL Seimbang (Tiga Suku Lengkap + Buffer Invalidasi)
> **Koreksi kritis — jebakan `struct_dist` degenerate**: pada limit order M2/M3, `entry_lim = target_sup`/`target_res`/`base_ceiling` dan `origin_level` di-set ke level yang sama, sehingga `abs(entry − origin) = 0`. Tanpa buffer, `struct_dist` **tidak pernah berkontribusi** dan SL selalu jatuh ke floor ATR secara statis. Verifikasi source: `market_scanner.py:4748` (`entry_lim = target_res - …`, `origin_level=target_res`), `:4955` (`entry_lim = target_sup + …`, `origin_level=target_sup`).

$$\text{invalidation\_buffer} = \max\left(0.15 \times \text{ATR H1},\ 2 \times \text{Spread} + 10\text{ pts}\right)$$
$$\text{struct\_dist} = \left|\text{entry} - \text{origin\_level}\right| + \text{invalidation\_buffer}$$
$$\text{sl\_dist} = \max\left(\text{struct\_dist},\ 1.00 \times \text{ATR H1},\ \frac{\text{Spread} + 6}{0.20}\right)$$

* **Tiga suku wajib dipertahankan.** Menghapus $1.00 \times \text{ATR}$ membuat pair ATR besar terpotong terlalu rapat (mis. GBPJPY: struct 14 p, friksi 160 p, ATR 289 p → SL jauh di bawah $1\times$ATR).
* Memberikan ruang bernapas $88.8\%$ bagi pemenang sah.
* Menghilangkan $50\%$ inflasi SL lama ($2.08\times\text{ATR} \rightarrow 1.00\times\text{ATR}$).

### E. Pilar 5: Defensif di London 15:00–17:00 WIB
* Jendela ini menyumbang $120\%$ total kerugian.
* Terapkan penalti lot size ($0.25\times - 0.50\times$) dan larang pending limit pasif (`sell_limit`).

### F. Pilar 6: Target Jauh Bersyarat
* Target $\ge 2.5\times\text{ATR}$ hanya diizinkan jika `Sesi == Tokyo` DAN `|CSM Delta| >= 2.00` DAN `Rigid Breached Wall Law Terpenuhi`.
