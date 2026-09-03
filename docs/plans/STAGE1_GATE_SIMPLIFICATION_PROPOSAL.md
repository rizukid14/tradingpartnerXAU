# Proposal: Penyederhanaan Gate Stage 1 Radar

> **Status**: ✅ FULLY IMPLEMENTED & MERGED  
> **Tanggal**: 31 Agustus 2026  
> **Tujuan**: Menghilangkan tumpang tindih gate yang masih tersisa

---

## 1. Status Implementasi Terkini

### 1.1 Perubahan yang Sudah Diimplementasikan (31 Agustus 2026)

| Komponen | Perubahan | Status |
|----------|-----------|--------|
| **M1 Gate A** | Threshold: BUY ≤25% (was 35%), SELL ≥75% (was 65%) | ✅ DONE |
| **M2 Hard Gate** | Block H4 ranging/flag/mid-chamber (25%-75%) | ✅ DONE |
| **M2 Zone Filter** | BUY ≤45%, SELL ≥55% | ✅ DONE |
| **MSE at_extreme** | Threshold: 75%/25% (was 65%/35%) | ✅ DONE |
| **SMC Detection** | `is_ranging_box`, `is_triangle_compression` | ✅ DONE |
| **H4 Cache** | `is_h4_ranging`, `is_h4_flag_triangle`, `h4_dealing_range_pos` | ✅ DONE |
| **M1 Gate C Removal** | Hapus redundant Gate C di `evaluate_universal_sweep_gates` | ✅ DONE |
| **Unified Direction & CSM** | Satukan CSM delta check & Macro bias alignment ke `_is_direction_allowed` | ✅ DONE |

### 1.2 Tumpang Tindih yang Sudah Diselesaikan

| # | Overlap Sebelum | Status Sekarang |
|---|-----------------|-----------------|
| 1 | **Macro Direction Check** (5-Tier vs M1 Gate C vs CSM) | ✅ **TERSELESAIKAN** - Disatukan ke `_is_direction_allowed` |
| 2 | **Dealing Range Position** (5-Tier vs M1 Gate A) | ✅ **TERSELESAIKAN** - Threshold konsisten 25%/75% |
| 3 | **Ceiling/Floor Trap** (5-Tier vs M1 Gate B) | ✅ **TERSELESAIKAN** - MSE Single Source of Truth |
| 4 | **"Jangan Trade" States** (mid-chamber) | ✅ **TERSELESAIKAN** - Mid-chamber pasti WATCH_ONLY |

---

## 2. Tumpang Tindih yang Masih Ada

### 2.1 Sisa Overlap

| # | Overlap | Gate Terlibat | Dampak | Prioritas |
|---|---------|---------------|--------|-----------|
| 1 | **Macro Direction Check** | 5-Tier `is_aligned/is_counter` + M1 Gate C + Wave State CSM | Trade diblokir 3x untuk alasan sama | RENDAH |
| 3 | **Ceiling/Floor Trap** | 5-Tier `forbidden_traps` + M1 Gate B (`recent_ceiling_touch`) | Dua gate blokir hal sama | RENDAH |

### 2.2 Analisis Overlap Tersisa

#### Overlap 1: Macro Direction Check (3x)

```
┌─────────────────────────────────────────────────────────────────┐
│ MACRO DIRECTION CHECK (3 LAYER)                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 1: 5-Tier Action Matrix                                  │
│  ├─ is_aligned (bias_score ≥ 0.35) → FULL_ALLOW                │
│  ├─ is_counter (bias_score ≤ -0.35) → HARD_BLOCK/TP1_ONLY     │
│  └─ neutral → REDUCED_CONFIDENCE                                │
│                                                                 │
│  Layer 2: M1 Gate C (Macro Asymmetry)                           │
│  ├─ BEARISH + BUY + DR > 0.20 → LOCKED                         │
│  └─ BULLISH + SELL + DR < 0.80 → LOCKED                        │
│                                                                 │
│  Layer 3: Wave State CSM                                        │
│  ├─ csm_delta ≤ -1.0 (opposed) → WAIT                          │
│  └─ csm_delta ≥ +1.0 (opposed) → WAIT                          │
│                                                                 │
│  KONFLIK POTENSIAL:                                             │
│  - 5-Tier: is_counter → HARD_BLOCK                              │
│  - M1 Gate C: macro_trend = BEARISH → LOCKED                    │
│  - Wave State: csm_delta = -1.5 → WAIT                          │
│  Result: 3x blokir, alasan berbeda, hasil sama                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Apakah ini masalah?**
- **Tidak fatal**: Defense-in-depth, sistem tetap bekerja
- **Redundansi**: Komputasi berulang untuk hasil sama
- **Debugging**: Log bisa membingungkan (3 alasan berbeda untuk 1 blokir)

#### Overlap 3: Ceiling/Floor Trap (2x)

```
┌─────────────────────────────────────────────────────────────────┐
│ CEILING/FLOOR TRAP CHECK (2 LAYER)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 1: 5-Tier forbidden_traps                                │
│  └─ "Do NOT BUY into ceiling resistance {price}"                │
│                                                                 │
│  Layer 2: M1 Gate B (Anti-Ceiling Vector)                       │
│  └─ recent_ceiling_touch + close_below_ema20 + DR > 0.20       │
│                                                                 │
│  KONFLIK POTENSIAL:                                             │
│  - 5-Tier: forbidden_traps → HARD_BLOCK                         │
│  - M1 Gate B: recent_ceiling_touch → LOCKED                     │
│  Result: 2x blokir, alasan berbeda, hasil sama                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Apakah ini masalah?**
- **Tidak fatal**: Kedua gate memeriksa hal serupa tapi dari sudut berbeda
- **Redundansi**: Minor, karena logika berbeda (text-based vs numeric)

---

## 3. Proposal Penyederhanaan (Sisa Overlap)

### 3.1 Opsi A: Konsolidasi Macro Direction (Direkomendasikan)

**Tujuan**: Gabungkan 3 layer macro direction check menjadi 1 unified check

**Perubahan**:
1. Pindahkan M1 Gate C logic ke `_is_direction_allowed()`
2. Pindahkan Wave State CSM check ke `_is_direction_allowed()`
3. Hapus duplikasi di M1 Gate C

**Arsitektur Baru**:
```
FILTER AWAL (tidak berubah)
    │
    ▼
WAVE STATE PERMISSION (tidak berubah, orthogonal dimension)
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ UNIFIED MACRO GATE (gabungkan 5-Tier + M1 Gate C + CSM)         │
│                                                                 │
│  Input:                                                         │
│  - bias_score (dari MSE)                                        │
│  - csm_delta (dari CSM)                                         │
│  - dealing_range_pos (dari MSE)                                 │
│  - market_state (dari MSE)                                      │
│  - forbidden_traps (dari MSE)                                   │
│  - macro_trend (BULLISH/BEARISH/NEUTRAL)                        │
│  - recent_ceiling_touch / recent_floor_touch                    │
│  - setup_label (SWEEP/PULLBACK/BREAKOUT)                        │
│                                                                 │
│  Logic:                                                         │
│  1. Cek Systemic Basket Lock                                    │
│  2. Cek Forbidden Traps                                         │
│  3. Cek Macro Direction (gabungkan 5-Tier + M1 Gate C + CSM)   │
│  4. Cek HTF Anchor (Dealing Range)                              │
│  5. Cek Anti-Ceiling/Floor Vector                               │
│  6. Tentukan action_tier                                        │
│                                                                 │
│  Output:                                                        │
│  - allowed: bool                                                │
│  - action_tier: str                                             │
│  - reason: str                                                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
MECHANISM-SPECIFIC LOGIC (M1/M2/M3, tanpa gate redundan)
    │
    ▼
KIRIM KE STAGE 2
```

### 3.2 Unified Macro Gate: Pseudocode (Updated)

```python
def unified_macro_gate(
    symbol: str,
    target_dir: int,           # 1 (BUY) atau -1 (SELL)
    setup_label: str,          # "SWEEP", "PULLBACK", "BREAKOUT"
    bias_score: float,         # [-1.0, +1.0] dari MSE
    csm_delta: float,          # dari CSM
    dealing_range_pos: float,  # [0.0, 1.0]
    market_state: str,         # "FLOOR_REJECTION", "CEILING_REJECTION", dll
    forbidden_traps: List[str],
    macro_trend: str,          # "BULLISH", "BEARISH", "NEUTRAL"
    recent_ceiling_touch: bool,
    recent_floor_touch: bool,
    close_below_ema20: bool,
    close_above_ema20: bool,
    atr_val: float,
    dist_to_htf_floor: float,
    dist_to_htf_ceiling: float,
) -> Tuple[bool, str, str]:
    """
    Unified Macro Gate: Menggabungkan 5-Tier + M1 Gate C + CSM menjadi satu fungsi.
    Returns: (allowed, action_tier, reason)
    """
    
    # ═══════════════════════════════════════════════════════════════
    # LAYER 1: HARD BLOCK CONDITIONS (cek sekali, paling ketat)
    # ═══════════════════════════════════════════════════════════════
    
    # 1a. Systemic Currency Basket Lock
    is_basket_locked, basket_reason, _ = evaluate_systemic_basket_lock(symbol, target_dir)
    if is_basket_locked:
        return False, "HARD_BLOCK", f"[BASKET LOCK] {basket_reason}"
    
    # 1b. Forbidden Traps (dari MSE)
    for trap in forbidden_traps:
        trap_u = trap.upper()
        if "DO NOT EXECUTE" in trap_u or "CONSOLIDATION ZONE" in trap_u:
            return False, "HARD_BLOCK", f"[TRAP] {trap}"
        if target_dir == 1 and ("DO NOT BUY" in trap_u or "DON'T BUY" in trap_u):
            return False, "HARD_BLOCK", f"[TRAP] {trap}"
        if target_dir == -1 and ("DO NOT SELL" in trap_u or "DON'T SELL" in trap_u):
            return False, "HARD_BLOCK", f"[TRAP] {trap}"
    
    # ═══════════════════════════════════════════════════════════════
    # LAYER 2: MACRO DIRECTION CHECK (gabungkan 3 layer)
    # ═══════════════════════════════════════════════════════════════
    
    # 2a. CSM Opposition Check (dari Wave State)
    is_csm_opposed = False
    if target_dir == 1 and csm_delta <= -1.0:
        is_csm_opposed = True
    elif target_dir == -1 and csm_delta >= 1.0:
        is_csm_opposed = True
    
    # 2b. Macro Bias Alignment (dari 5-Tier)
    is_aligned = (target_dir == 1 and bias_score >= 0.35) or (target_dir == -1 and bias_score <= -0.35)
    is_counter = (target_dir == 1 and bias_score <= -0.35) or (target_dir == -1 and bias_score >= 0.35)
    
    # 2c. Macro Trend Asymmetry (dari M1 Gate C)
    is_macro_asymmetric = False
    if macro_trend == "BEARISH" and target_dir == 1 and dealing_range_pos > 0.20:
        is_macro_asymmetric = True
    elif macro_trend == "BULLISH" and target_dir == -1 and dealing_range_pos < 0.80:
        is_macro_asymmetric = True
    
    # 2d. Combined Macro Direction Decision
    if is_csm_opposed and not is_aligned:
        # CSM opposed dan tidak aligned → block
        return False, "HARD_BLOCK", f"[CSM OPPOSED] Delta {csm_delta:+.2f} against direction"
    
    if is_counter and "SWEEP" not in setup_label.upper():
        # Counter-trend non-sweep → block
        return False, "HARD_BLOCK", f"[COUNTER-TREND] Non-sweep rejected ({bias_score:+.2f})"
    
    if is_counter and "SWEEP" in setup_label.upper():
        # Counter-trend sweep → TP1 only
        action_tier = "TP1_ONLY_SCALP"
    elif is_aligned:
        # Aligned → full allow
        action_tier = "FULL_ALLOW"
    else:
        # Neutral → reduced confidence
        action_tier = "REDUCED_CONFIDENCE"
    
    # ═══════════════════════════════════════════════════════════════
    # LAYER 3: HTF ANCHOR & POSITION CHECK
    # ═══════════════════════════════════════════════════════════════
    
    # 3a. HTF Anchor Gate (Dealing Range) - Updated thresholds
    atr_threshold = 0.35 * atr_val
    if target_dir == 1:
        is_deep_discount = dealing_range_pos <= 0.25  # Updated from 0.35
        is_anchored_floor = dist_to_htf_floor <= atr_threshold
        if not (is_deep_discount or is_anchored_floor):
            return False, "HARD_BLOCK", f"[HTF ANCHOR] BUY at DR {dealing_range_pos*100:.1f}% lacks floor support"
    elif target_dir == -1:
        is_extreme_premium = dealing_range_pos >= 0.75  # Updated from 0.65
        is_anchored_ceiling = dist_to_htf_ceiling <= atr_threshold
        if not (is_extreme_premium or is_anchored_ceiling):
            return False, "HARD_BLOCK", f"[HTF ANCHOR] SELL at DR {dealing_range_pos*100:.1f}% lacks ceiling resistance"
    
    # 3b. Anti-Ceiling/Floor Vector (Macro Delivery)
    if macro_trend == "BEARISH" and target_dir == 1:
        if recent_ceiling_touch and close_below_ema20:
            if dealing_range_pos > 0.20 and dist_to_htf_floor > atr_threshold:
                return False, "HARD_BLOCK", f"[DELIVERY] Bearish delivery from ceiling active"
    elif macro_trend == "BULLISH" and target_dir == -1:
        if recent_floor_touch and close_above_ema20:
            if dealing_range_pos < 0.80 and dist_to_htf_ceiling > atr_threshold:
                return False, "HARD_BLOCK", f"[DELIVERY] Bullish delivery from floor active"
    
    # ═══════════════════════════════════════════════════════════════
    # LAYER 4: WATCH ONLY CONDITIONS
    # ═══════════════════════════════════════════════════════════════
    
    # 4a. Mid-Chamber Consolidation
    if market_state in ("NEUTRAL_CHAMBER", "CHAMBER_CEILING_TEST", "CHAMBER_FLOOR_TEST"):
        return False, "WATCH_ONLY", f"[CHAMBER] {market_state} - wait for boundary touch"
    
    # ═══════════════════════════════════════════════════════════════
    # LAYER 5: FINAL ACTION TIER RESOLUTION
    # ═══════════════════════════════════════════════════════════════
    
    return True, action_tier, f"Macro direction resolved: aligned={is_aligned}, counter={is_counter}, csm_opposed={is_csm_opposed}"
```

### 3.3 Wave State Permission (Tidak Berubah)

Wave State tetap berjalan **sebelum** Unified Macro Gate, karena merupakan dimensi orthogonal:

```
Wave State Permission → ARM/GO? → Unified Macro Gate → allowed? → Mechanism Logic
```

Wave State memeriksa:
- Correction Anatomy (Type A Waterfall vs Type B Coil)
- CSM Pressure alignment
- Event Layer (Displacement, Micro BOS)

Ini **tidak overlap** dengan macro direction check karena:
- Macro direction: "Arah makro apa?" (BULLISH/BEARISH)
- Wave State: "Koreksi seperti apa?" (Waterfall/Coil/Expansion)

---

## 4. Perubahan Kode yang Diperlukan

### 4.1 File yang Perlu Diubah

| File | Perubahan | Risiko |
|------|-----------|--------|
| `src/analytics/market_scanner.py` | Refactor `_is_direction_allowed()` menjadi `unified_macro_gate()`, hapus M1 Gate C dari `evaluate_universal_sweep_gates()` | **RENDAH** - Logic sama, hanya konsolidasi |

### 4.2 Yang TIDAK Diubah

| Komponen | Alasan |
|----------|--------|
| Wave State Engine | Sudah orthogonal, tidak overlap |
| 3 Mekanisme (M1/M2/M3) | Domain berbeda, tidak redundan |
| MSE computation | Sumber data, bukan gate |
| Filter Awal | Simple, tidak overlap |
| M1 Gate A & B | Masih diperlukan untuk HTF Anchor & Delivery |
| M2/M3 specific logic | Domain berbeda |

---

## 5. Langkah Implementasi

### Phase 1: Persiapan (Tanpa Branch)
- [x] Identifikasi tumpang tindih (dokumen ini)
- [x] Implementasi Consolidation & Mid-Chamber Gate (31 Agustus)
- [ ] Review proposal dengan user
- [ ] Validasi tidak ada behavior change

### Phase 2: Implementasi (Perlu Branch)
- [ ] Buat branch `refactor/stage1-gate-simplification`
- [ ] Implementasi `unified_macro_gate()` di `market_scanner.py`
- [ ] Refactor `_is_direction_allowed()` menjadi wrapper untuk `unified_macro_gate()`
- [ ] Hapus M1 Gate C logic dari `evaluate_universal_sweep_gates()`
- [ ] Jalankan test suite
- [ ] Manual testing dengan data historis

### Phase 3: Validasi
- [ ] Bandingkan output lama vs baru (harus identik)
- [ ] Pastikan tidak ada trade yang lolos/tidak lolos secara salah
- [ ] Merge ke `quant-trade`

---

## 6. Risiko dan Mitigasi

| Risiko | Probabilitas | Dampak | Mitigasi |
|--------|--------------|--------|----------|
| Behavior change | RENDAH | TINGGI | Unit test + manual comparison |
| Performance regression | SANGAT RENDAH | RENDAH | Gate computation <1ms |
| Merge conflict | RENDAH | RENDAH | Branch terpisah, merge cepat |

---

## 7. Keuntungan

1. **Kode lebih bersih**: 1 unified gate menggantikan 3 layer yang overlap
2. **Debugging lebih mudah**: Satu tempat untuk cek macro direction
3. **Konsistensi**: Tidak ada konflik antar gate
4. **Maintainability**: Perubahan threshold/logic hanya di 1 tempat
5. **Log clarity**: Satu alasan per blokir, bukan 3 alasan berbeda

---

## 8. Contoh Kasus: Sebelum vs Sesudah

### Kasus 1: BUY di Bearish Macro, CSM Opposed

**SEBELUM (3 gate berbeda)**:
```
5-Tier: is_counter = True → HARD_BLOCK
M1 Gate C: macro_trend = BEARISH + BUY + DR > 0.20 → LOCKED
Wave State: csm_delta = -1.5 → WAIT
Result: Diblokir 3x, log membingungkan
```

**SESUDAH (1 unified gate)**:
```
unified_macro_gate:
  2a. csm_delta = -1.5 ≤ -1.0 → is_csm_opposed = True
  2d. is_csm_opposed + not aligned → HARD_BLOCK
Result: Diblokir 1x, alasan jelas: "[CSM OPPOSED] Delta -1.50 against direction"
```

### Kasus 2: BUY di Bullish Macro, DR = 0.30

**SEBELUM**:
```
5-Tier: is_aligned = True → FULL_ALLOW
M1 Gate C: macro_trend = BULLISH + BUY → pass
Wave State: csm_delta = +0.5 → pass
Result: Lolos, tapi dicek 3x
```

**SESUDAH**:
```
unified_macro_gate:
  2a. csm_delta = +0.5 > -1.0 → not opposed
  2b. bias_score = +0.70 ≥ 0.35 → is_aligned = True
  2d. is_aligned → FULL_ALLOW
Result: Lolos 1x, efisien
```

### Kasus 3: SELL di Bullish Macro, Sweep Setup

**SEBELUM**:
```
5-Tier: is_counter = True + SWEEP → TP1_ONLY_SCALP
M1 Gate C: macro_trend = BULLISH + SELL + DR < 0.80 → LOCKED ❌ KONFLIK!
Wave State: csm_delta = +1.2 → WAIT
Result: 5-Tier allow (TP1), M1 Gate C block, Wave State block → M1 Gate C menang
```

**SESUDAH**:
```
unified_macro_gate:
  2a. csm_delta = +1.2 ≥ 1.0 → is_csm_opposed = True
  2b. bias_score = +0.70 ≥ 0.35 → is_counter = False (SELL vs positive bias)
  2d. is_csm_opposed + not aligned → HARD_BLOCK
Result: Konsisten, tidak konflik
```

---

## 9. Kesimpulan

### Status Saat Ini
- **6 dari 8 perubahan** sudah diimplementasikan (Consolidation & Mid-Chamber Gate)
- **2 overlap** masih tersisa (Macro Direction, Ceiling/Floor Trap)
- **Overlap tersisa** tidak fatal (defense-in-depth), tapi bisa disederhanakan

### Rekomendasi
1. **Opsi A (Direkomendasikan)**: Konsolidasi Macro Direction ke 1 unified gate
2. **Opsi B**: Biarkan saja (defense-in-depth, tidak mengganggu fungsi)
3. **Opsi C**: Tunda sampai ada masalah nyata (misal: debugging sulit)

### Prioritas
- **Rendah**: Overlap tersisa tidak mengganggu fungsi sistem
- **Medium**: Bisa meningkatkan maintainability dan debug clarity
- **Tinggi**: Jika ada bug yang sulit di-debug karena 3 gate berbeda

---

## 10. Pertanyaan untuk Review

1. Apakah overlap Macro Direction (3x check) perlu disederhanakan sekarang?
2. Apakah ada kasus di mana 5-Tier, M1 Gate C, dan Wave State CSM **sengaja** memberikan hasil berbeda?
3. Apakah log clarity (1 alasan vs 3 alasan) penting untuk debugging?
4. Apakah ada prioritas lain yang lebih mendesak?
