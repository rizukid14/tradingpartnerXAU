# ZCE Lapis 4 — Live Execution Validation Runbook (Log-Driven)

> Status: **SIAP PAKAI** — ditulis 2 September 2026. Verifikasi Lapis 1–3 sudah 40/40 PASS
> (lihat `docs/CHANGELOG_SEPTEMBER_2026.md` section 13), sehingga Lapis 4 layak dijalankan.
> Dokumen ini = panduan "nanti tinggal baca dari log", bukan script sekali pakai.
> Pelaksana: **user (risk owner)** — bot live cent + baca hasil dari log. Agent hanya menyiapkan
> interpretasi & kriteria di bawah.

## 1. Tujuan

Membuktikan ZCE mode `full` aman & tidak merusak eksekusi live di akun cent:

- Semua trade yang dieksekusi punya SL/TP yang masuk akal secara struktural (tidak ada wall "kabur" jauh).
- Sisi override ZCE (F1/C1 dari peta zona 6-TF) benar-benar dipakai dan menghasilkan anchor yang valid.
- Perilaku risiko (MaxDD, spread filter, dead zone, dst.) tidak menyimpang dari baseline non-ZCE.

## 2. Prasyarat (sudah terpenuhi di `.env`)

```
ZCE_ENABLED=true
ZCE_MODE=full
```

Bot berjalan normal di akun **live cent** dengan magic `20260625`, minimal **7 hari**,
terkumpul **≥ 60 trade** (syarat validitas AGENTS.md — menolak klaim valid dari sample kecil).

## 3. Sumber data (semua dari log — tidak perlu code change)

| # | Sumber | Lokasi | Isi yang dipakai |
|---|---|---|---|
| L1 | Log bot | `data/trading_bot.log` (rotate 2MB, keep 5000 baris — **arsipkan tiap hari** kalau 7 hari > 5000 baris) | baris eksekusi order, status engine, error ZCE |
| L2 | History deals MT5 | akun cent via `mt5.history_deals_get()` (magic `20260625`) | tiket, simbol, arah, entry, SL, TP, exit, profit, R |
| L3 | Snapshot Telegram `/scan` & `/status` | chat Telegram (opsional, penguat) | F1/C1 + grade yang tampil saat jam eksekusi |

> ⚠️ **Arsipkan `data/trading_bot.log` setiap hari** selama periode uji. Satu file log hanya
> menampung 5000 baris terakhir — trade hari ke-3 bisa ter-overwrite sebelum dianalisis.

## 4. Marker log yang relevan (untuk `Select-String` / `grep`)

| Pattern | Arti | Dipakai untuk |
|---|---|---|
| `Order BERHASIL! Ticket:` | order market terkirim | daftar tiket + waktu eksekusi |
| `Mengirim order:` | detail lot/SL/TP sebelum kirim | SL/TP aktual terpasang |
| `Pending BERHASIL!` | pending limit terpasang | entry limit (retest) |
| `MacroStrategicEngine` | refresh directive (0 token) | konteks wall F1/C1 per jam refresh |
| `ZCE` / `Zone Map` / `zce_walls` | status/aktivitas engine ZCE | konfirmasi ZCE hidup & override jalan |
| `ANCHOR_TOO_WIDE` | SL anchor ZCE > ceiling → trade di-skip | hitung insiden skip sah (bukan bug) |
| `ATR_UNAVAILABLE` | ATR gagal → reject (mode ZCE, tanpa fallback statis) | hitung insiden reject sah |
| `permission_state` / `STATE TRANSITION` | status ARM/GO/LOCK per simbol | konteks gate sebelum eksekusi |
| `ERROR` / `Traceback` | exception | pastikan 0 crash ZCE selama periode |

## 5. Prosedur analisis (saat data sudah terkumpul)

### Langkah A — Ekspor trade dari MT5
Query history deals magic `20260625` (rentang tanggal periode uji) → tabel:
`tiket | simbol | arah | entry | SL | TP | exit | profit | R | waktu buka | waktu tutup`.

### Langkah B — Cocokkan tiap trade ke konteks wall saat eksekusi
Untuk tiap tiket: cari timestamp buka di L1 → ambil baris `MacroStrategicEngine` /
snapshot Telegram **terdekat SEBELUM eksekusi** → catat F1/C1 yang sedang berlaku saat itu.

### Langkah C — Klasifikasi sumber anchor tiap trade
| Kelas | Definisi |
|---|---|
| `ZCE_FULL` | F1 **dan** C1 dari ZCE (override penuh) |
| `ZCE_MIXED` | hanya satu sisi ZCE (override per-sisi — F1 ZCE + C1 MSE atau sebaliknya) |
| `MSE_BASE` | dua sisi dari baseline MSE (ZCE tidak punya zona dekat / kena cap 2.0×ATR) |
| `ZCE_SKIP` | trade tidak jadi karena `ANCHOR_TOO_WIDE` / `ATR_UNAVAILABLE` (bukan trade, dihitung terpisah) |

### Langkah D — Hitung metrik (lihat §6) per kelas di atas

### Langkah E — Verifikasi manual spot-check (30 menit)
Ambil 5–10 trade acak dari kelas `ZCE_FULL`/`ZCE_MIXED` → buka chart MT5:
apakah level SL/TP yang terpasang **persis di dinding fisik** yang terlihat
(swing/OB/psych/FVG)? Kalau ada SL jatuh di "hutan" candle tanpa struktur → indikasi koordinat salah.

## 6. Metrik & kriteria lulus (proposal — angka bisa direvisi risk owner)

| Metrik | Ambang lulus | Catatan |
|---|---|---|
| Sample size | ≥ 60 trade **dan** ≥ 7 hari kalender | syarat AGENTS.md; di bawah ini = belum bisa klaim apa pun |
| Crash/exception ZCE | 0 | `ERROR`/`Traceback` di jalur ZCE selama periode |
| Insiden wall kabur saat eksekusi | 0 | jarak entry ke C1/F1 yang berlaku > 2.0×ATR H1 pada jam eksekusi (INV-2 dilanggar di runtime) |
| Insiden `ANCHOR_TOO_WIDE` | dilaporkan, bukan gagal | itu mekanisme safety — hitung rasionya vs total kandidat |
| Insiden `ATR_UNAVAILABLE` | ≤ 2 | kalau sering → data MT5 bermasalah |
| Max drawdown periode | ≤ 4% equity | sudah di-enforce risk engine; konfirmasi tidak ada bocor |
| Coverage override ZCE | dilaporkan (target: `ZCE_FULL`+`ZCE_MIXED` ≥ 40% trade) | kalau < 40% → ZCE jarang menangkap zona dekat → evaluasi cap/peta zona |
| Perbandingan hasil | PF / win rate kelas `MSE_BASE` vs `ZCE_*` dilaporkan berdampingan | **belum tentu harus ZCE lebih unggul** — sample 7 hari belum cukup buat klaim edge; fungsi Lapis 4 = deteksi anomali/regresi, bukan bukti superioritas |

**LOLOS**: semua ambang di atas terpenuhi, spot-check manual tidak menemukan anchor non-struktural,
tidak ada regresi perilaku risiko.

**TIDAK LOLOS**: ada wall kabur tereksekusi (0 toleransi), crash ZCE, atau spot-check menemukan
anchor asal-asalan → stop, laporkan ke planner dengan tiket + baris log, jangan lanjut ke
produksi akun utama.

**ABU-ABU (belum bisa disimpulkan)**: sample < 60 atau coverage override < 40% tanpa anomali →
perpanjang periode observasi, bukan ganti kode.

## 7. Gap logging yang diketahui (penting — baca dulu)

Log saat ini **tidak mencatat per-trade atribusi sumber F1/C1** (`ZCE_FULL`/`ZCE_MIXED`/`MSE_BASE`)
secara eksplisit di baris eksekusi. Rekonstruksi di Langkah B–C berbasis pencocokan waktu
(refresh engine vs timestamp order) + snapshot Telegram — bisa subjektif kalau jarak waktu jauh.

Kalau mau analisis **murni dari log tanpa rekonstruksi**, perlu 1 baris log tambahan saat order
dikirim, kira-kira formatnya:

```
[ZCE-AUDIT] ticket=12345678 EURUSD BUY entry=1.16123 sl=1.15780 tp=1.16500
  src_f1=ZCE(1.15780,1.92xATR) src_c1=MSE(1.16500,1.10xATR) tier=FULL_ALLOW
```

Itu edit kode di jalur eksekusi (`consensus.py`/`mt5_connector.py`) — **butuh konfirmasi user
dulu**. Selama belum ada, analisis pakai prosedur §5 (rekonstruksi waktu).

## 8. Larangan

- DILARANG menyimpulkan "ZCE superior/buruk" dari < 60 trade / < 7 hari (AGENTS.md rule 6).
- DILARANG mengubah kode produksi dari dokumen ini.
- DILARANG menyentuh akun live utama (login `27556325`) untuk uji ini — khusus akun cent.
