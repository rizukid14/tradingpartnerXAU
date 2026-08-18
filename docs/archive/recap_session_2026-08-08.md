# Rekap Kerjaan Trading Bot — Sesi 8 Agustus 2026

Branch: `dev` (pushed)
Dokumen ini untuk review AI lain. Status tiap item: ✅ committed/pushed atau ⚠️ uncommitted (working tree).

---

## A. LATAR BELAKANG MASALAH

1. **Bug SELL SL/TP terbalik** di `_build()` (mt5_connector) — regression dari commit `95053aa`. Log lama menunjukkan SELL sukses (kode lama benar), tapi kode baru hitung SL di bawah/TP di atas untuk SELL → broker reject `10016 INVALID_STOPS` → fallback salah ke RETURN → `10030 Unsupported filling mode`. **Bukti log**: `Mengirim order: SELL BTCUSD.c ... fallback to ORDER_FILLING_RETURN (retcode was 10016)`.

2. **LLM kasih SL/TP terlalu kecil** untuk BTC:
   - Prompt bilang "(1 point = 0.01)" — menyesatkan (itu tick size, bukan nilai USD per point)
   - ATR M5 BTC = $21.83 → prompt suruh SL 3200-4300 pts = cuma $0.32-0.43
   - Hasil: SL/TP di dalam spread $17 → kena spread instan → loss kecil beruntun

3. **Spread BTC ~$17 (1700 pts) terlalu besar untuk M5 scalping**:
   - ATR M5 = $21 → spread = 78% dari ATR
   - Target $10/trade & SL $5 **di bawah spread $17** — struktural mustahil
   - Solusi: BTC pindah ke timeframe H1 (spread cuma ~8% dari ATR H1 $204)

4. **Bug crash startup**: `TradeEvaluator._load_memory()` duplikat (satu tanpa argumen, satu dengan `symbol`) → `TypeError: missing 1 required positional argument: 'symbol'` → bot gagal start.

---

## B. PERUBAHAN — SUDAH DI-COMMIT & PUSH

### Commit `1de0810` (dari Antigravity, reviewed)
- `src/core/mt5_connector.py`: fix SL/TP arah SELL di `_build()`, tambah `get_filling_policy()` (baca `filling_mode` broker, bukan hardcode RETURN).

### Commit `2d3ccbf` (dari Antigravity, reviewed)
- `src/core/consensus.py`: `_apply_sltp_floors()` — floor SL/TP (SL ≥ default & 2× spread, TP ≥ 1.5× SL).
- `config.py`: `LOT_SIZE_BTC = 0.03` (kemudian di-reject user → balik ke 0.01).

### Commit `d9019fa` (saya)
- `src/core/llm_client.py`: inject **money-scale** ke prompt ("1 point = $0.0001, 100000 pts = ~$10, NEVER set SL closer than 2x spread"). Hapus frase menyesatkan "(1 point = 0.01)".
- `src/core/mt5_connector.py`: `get_current_tick()` tambah `usd_per_point` + `spread_usd`; `get_open_positions()` **filter magic number** (bot tidak lagi bisa close posisi manual user).
- `src/analytics/position_manager.py`: manage **semua symbol** (bukan cuma symbol aktif) + **tick-freshness skip** (skip market tutup, e.g. XAU weekend — cek `POSITION_MANAGER_MAX_TICK_AGE_SECONDS`).
- `src/analytics/dynamic_config.py`: BEP trades (|profit| ≤ tolerance) **excluded dari win-rate**.
- `config.py`: `LOT_SIZE_BTC` kembali 0.01; tambah `BREAK_EVEN_TOLERANCE_USD`, `RECOVERY_EXIT_PROFIT_USD`, `POSITION_MANAGER_MAX_TICK_AGE_SECONDS`.
- `tests/test_symbol_rotation.py`: assert referensi ke config (bukan hardcode 600/1200).

### Commit `da74753` (saya)
- `src/core/llm_client.py`: BTC pakai **H1 ATR** sebagai basis SL/TP (XAU tetap M5 ATR).
- `config.py`: `BREAK_EVEN_TOLERANCE_USD = 0.50` (**testing** — 8 trade loss -0.01..-0.44 jadi BEP, bukan loss).
- `src/analytics/trade_evaluator.py`: fix crash `_load_memory()` duplikat.
- `main.py`: per-symbol breakdown tampilkan non-BEP count + BEP note eksplisit.

---

## C. PERUBAHAN — BELUM DI-COMMIT (Working Tree)

### 🟡 Implementasi BTC H1 (dari plan, user approved)
| File | Perubahan |
|------|-----------|
| `config.py` | `get_timeframe(symbol)` → H1 utk crypto / M5 utk XAU; `get_higher_timeframes(symbol)` → H4/D1 utk crypto / M30/H1 utk XAU; `H1_TIMEFRAME`, `HIGHER_TIMEFRAMES_CRYPTO` |
| `main.py` | `get_market_data` & candle detection pakai `config.get_timeframe(...)`; banner "Timeframe: H1" utk BTC; banner spread filter pakai `max_spread_points_for` (per-symbol) |
| `src/analytics/macro_analyst.py` | MTF pakai `config.get_higher_timeframes(...)` → BTC scan H4+D1 |
| `src/core/consensus.py` | `_apply_sltp_floors` **hapus floor default**, cuma 2× spread (SL natural ATR H1 30000-40000 pts dibiarkan) |
| `src/core/llm_client.py` | ATR range **murni tanpa floor** (BTC H1 ATR $204 → SL 30655-40874, TP 45982-81748) |

### Verifikasi BTC H1
- Syntax OK semua file
- `tests/test_symbol_rotation.py` PASS (0 failures)
- `tests/test_macro.py` PASS (XAU M30/H1)
- Timeframe: XAU=5 (M5), BTC=16385 (H1)
- Consensus floor: SL 2500 → 3408 (2× spread), SL 30000 natural → dibiarkan

---

## D. KEPUTUSAN / STATE SAAT INI

1. **Lot BTC = 0.01** (reject 0.03 dari Antigravity, reject 0.25). Risk SL 50000 pts = $5 (0.5% balance $1000).
2. **BEP tolerance = 0.50** (testing) — komentar di config ditandai "for testing". Untuk LIVE defensif, kembalikan ke 0.04.
3. **Risk state & dynamic rules di-reset**: streak 0, threshold 2/3 sementara. `adapt_from_performance` akan set 3/3 kalau win rate < 40% (defensif — user setuju utk LIVE).
4. **Bot tidak jalan** saat ini (user matikan manual). Perlu restart utk load kode baru.

---

## E. RISIKO / CATATAN UNTUK REVIEW

1. **BTC H1 mengubah frekuensi trading drastis**: full cycle cuma tiap H1 close (bukan tiap M5). Trade jarang tapi berkualitas. **Perlu observasi**: trailing/BE/partial close BTC (activation 25000 pts) mungkin perlu di-scale ke H1.
2. **`get_open_positions` filter magic** — aman tapi perlu dipastikan tidak ada posisi manual yang perlu dikelola bot.
3. **Position manager tick-freshness 300 detik** — XAU weekend skip otomatis. Perlu pastikan threshold tidak terlalu ketat saat MT5 slow.
4. **BEP 0.50** — loss -0.44 jadi "BEP" artinya loss streak & max daily loss TIDAK menghitung loss kecil. Di LIVE harus 0.04.
5. **Money-scale di prompt** pakai `usd_per_point` dari `trade_tick_value` — terverifikasi live BTC = $0.0001/pt utk 0.01 lot.
6. **`LLM_TIMEOUT_SECONDS = 24`** — Gemini kadang slow (fallback ke model lain).

---

## F. FILE YANG TERLIBAT

| File | Peran |
|------|-------|
| `config.py` | Semua parameter + helper per-symbol (timeframe, MTF, lot, SL/TP, spread) |
| `main.py` | Loop utama, cycle, banner, per-symbol breakdown |
| `src/core/mt5_connector.py` | Order send/close, tick, positions (magic filter) |
| `src/core/consensus.py` | Konsensus 2/3 + SL/TP floor |
| `src/core/llm_client.py` | Prompt build + 3 LLM paralel + money-scale |
| `src/core/risk_engine.py` | Gate: spread, sesi, daily loss, recovery (BEP tolerance) |
| `src/analytics/position_manager.py` | Trailing/BE/partial (multi-symbol + tick freshness) |
| `src/analytics/macro_analyst.py` | MTF per-symbol (H4/D1 utk BTC) |
| `src/analytics/dynamic_config.py` | Adaptive threshold (BEP excluded) |
| `src/analytics/trade_evaluator.py` | Post-mortem lessons (fix crash) |
| `tests/test_symbol_rotation.py` | Test rotasi symbol + helper per-symbol |

## G. LOG BOT

- `logs/trading_bot.log` — campur sesi demo + live. Jangan hitung profit dari log; query MT5 langsung lebih akurat.
