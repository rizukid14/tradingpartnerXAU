# Arsip Changelog Historis Trading Bot (8–15 Agustus 2026)

> Dokumen ini mengarsipkan seluruh catatan perubahan historis arsitektur, bugfix, dan iterasi konfigurasi bot selama periode awal 8–15 Agustus 2026.

---

## 1. Perubahan Struktural 8 Agustus 2026

1. **BTC pindah ke M30** (dari M5): spread BTC ~$17 = 78% dari ATR M5 ($21), tapi kecil relatif ke ATR M30. `config.get_timeframe()` $\rightarrow$ BTC M30.
2. **MTF per-symbol**: XAU scan M15/M30, FX scan H4/D1, BTC scan H1/H4 (`config.get_higher_timeframes()`).
3. **Weighted confidence consensus**: skor arah = $\Sigma$ confidence; menang jika $\ge 2$ model searah DAN skor > threshold (XAU 1.0, BTC 1.2; defensif $\times 1.5$).
4. **Prompt dinamis per-symbol**: BTC "M30 Intraday Strategy", XAU "M5 Scalping Strategy".
5. **Money scale di prompt**: `usd_per_point`, spread USD, "NEVER set SL closer than 2x spread".
6. **SL/TP floor di consensus (mode-aware)**: ATR-Based $\rightarrow$ SL $\ge \max(2\times \text{spread}, \text{SL\_MULT}\times \text{ATR})$, TP $\ge \max(2\times \text{spread}, \text{TP\_MULT}\times \text{ATR})$ (**R:R 2:1**).
7. **`get_open_positions` filter magic** — bot tidak bisa menutup posisi manual milik user.
8. **Position manager multi-symbol + tick freshness**: kelola semua posisi bot, lewati jika pasar tutup.
9. **BEP tolerance $\pm 0.04$** (`BREAK_EVEN_TOLERANCE_USD`).
10. **Risk-based lot sizing**: lot = risk_usd / (SL pts $\times$ usd_per_point). BTC 1.5%, XAU 1.0%, FX 1.0%.
11. **Slot-3 DeepSeek V4 Flash**: fallback `claude-haiku-4-5-20251001`.
12. **Gemini ganti ke `gemini-3.1-flash-lite`**: benchmark membuktikan 3.1-flash-lite paling konsisten vs 2.5-flash-lite yang sering HOLD.
13. **Deteksi close manual (magic=0)**: `get_closed_positions_today` menerima OUT magic=0 hanya jika posisi dibuka oleh bot.
14. **Post-mortem langsung saat close**: dipicu di loop pas `sync_closed_positions` mendeteksi deal baru.

---

## 2. Iterasi FASE 1 s/d FASE 7 (11–12 Agustus 2026)

1. **FASE 1 — Ekspansi rotasi 7 simbol + FX pindah H1**: pool dari 3 $\rightarrow$ 7 simbol. FX ditetapkan ke H1 swing, risk 1.0%.
2. **FASE 2 — ATR SL Guidance**: AI membaca batas ATR HARD GATE di baris dinamis data pasar.
3. **FASE 3 — Fix terminal wrap**: status line dinamis dipendekkan dan di-render in-place dengan ANSI VT.
4. **FASE 4 — Multi-symbol macro cache**: cache HTF (H4/D1) dirombak menjadi berlaci per-simbol (`self.cache[symbol]`), menghemat download MT5 ~99%.
5. **FASE 5 — Smart Timeframe Rotation**: LLM hanya dipanggil saat lilin timeframe simbol ditutup (FX tiap 1 jam, BTC tiap 30m, XAU tiap 5/15m). Menghemat kuota LLM ~90%.
6. **FASE 6 — Prompt Sync LLM Mode**: penyesuaian teks prompt saat mode SL/TP bebas struktur (LLM).
7. **FASE 7 — Dynamic Micro Candles**: jumlah candle mikro disesuaikan (H1 $\rightarrow$ 24 candle M5 untuk mencakup 2 jam penuh).

---

## 3. Perubahan 13 Agustus 2026 — Pemisahan SL/TP Mode & Trailing Fix

1. **Pemisahan Mode per Kategori**:
   - `XAUUSD` & `BTCUSD` $\rightarrow$ Fix ATR-Based (R:R 2:1).
   - `FX pairs` $\rightarrow$ LLM Mode (bebas struktur + safety floor 50 pts).
2. **BEP & Trailing SL-Based di Mode LLM**:
   - BEP trigger: $\min(1\times \text{SL original}, 50\% \text{ TP})$.
   - Trailing activation: $\max(1.5\times \text{SL}, \text{fallback})$.
   - State `original_sl_points` di `position_manager_state.json`.
3. **Gate OVER-RISK di Consensus**:
   - Menolak trade jika SL melebihi toleransi risiko maksimal akun pada minimum lot broker.

---

## 4. Perubahan 14–15 Agustus 2026 — LLM Rules Baru & BEP/Trailing Pure % TP

1. **Daily Profit Target 6%** (`DAILY_PROFIT_TARGET_PERCENT = 6.0`): menolak posisi baru jika target profit harian telah tercapai.
2. **Dead Zone 02:00–06:00 WIB** (`DANGER_ZONES_WIB`): blokir pembukaan posisi baru saat likuiditas subuh tipis (kecuali BTC).
3. **R:R minimum 1.25:1** (`LLM_MIN_RR_RATIO = 1.25`): TP dinaikkan otomatis jika AI mengusulkan R:R di bawah 1.25.
4. **Perubahan Format Harga FX 5-Desimal**: perbaikan bug formatting `.2f` pada pair Forex.
5. **AI Re-evaluator tetap aktif saat posisi MAX (6/6)**: jika slot penuh, bot tetap memanggil re-evaluator untuk mencari peluang *early exit* pada posisi yang melemah.

---

## 5. Perubahan 24 Agustus 2026 — Transisi ke Ultra-Compact Chain-of-Thought JSON Schema

### 📜 Arsip Skema JSON Lama (Digantikan):
```json
// Skema Lama (HOLD):
{
  "signal": "HOLD",
  "reasoning": "string (MAX 20 WORDS: single key technical reason why no setup exists)"
}

// Skema Lama (BUY/SELL):
{
  "signal": "BUY" | "SELL",
  "confidence": float (0.50 to 1.00),
  "setup": "string (short label for setup type)",
  "reasoning": "string (MAX 60 WORDS: detailed entry thesis, key levels, and core edge for this trade)",
  "invalidation": "string (key technical condition that invalidates this thesis)",
  "sl_points": integer (Stop Loss distance in broker POINTS from current price),
  "tp_points": integer (Take Profit distance in broker POINTS from current price),
  "invalidation_price": float (OPTIONAL: reference price level for invalidation),
  "target_price": float (OPTIONAL: reference price level for target),
  "entry_type": "market" | "buy_stop" | "sell_stop" | "buy_limit" | "sell_limit",
  "entry_price": float
}
```

### ✨ Skema Baru: Ultra-Compact Chain-of-Thought JSON:
```json
{
  "trend": "BULL_PULLBACK | BEAR_PULLBACK | BREAKOUT | RANGING",
  "velocity": "NORMAL | CRASH | STAGNANT",
  "rr_valid": true | false,
  "signal": "BUY" | "SELL" | "HOLD",
  "confidence": float (0.00 to 1.00),
  "sl_points": integer (Stop Loss distance in broker POINTS),
  "tp_points": integer (Take Profit distance in broker POINTS),
  "invalidation_price": float (OPTIONAL reference price level),
  "target_price": float (OPTIONAL reference price level),
  "reasoning": "string (1 concise sentence explaining the trade thesis)"
}
```

### 💎 Rangkuman Peningkatan 24 Agustus 2026:
1. **Forced Logic Chain-of-Thought**: Token `trend`, `velocity`, dan `rr_valid` diproses sebelum `signal`, memangkas halusinasi & salah arah pada OpenAI, Gemini, dan DeepSeek.
2. **Kenaikan Threshold FX/XAU $\rightarrow$ 1.20**: Meningkatkan standar kualitas konsensus Forex dan Emas (wajib $\ge 2$ model searah, skor $\ge 1.20$).
3. **Efisiensi & Kecepatan Respons**: Ukuran output terpangkas menjadi ~35 token dengan waktu respons < 5 detik per simbol.

