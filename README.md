# Multi-LLM Consensus Trading Bot (MT5 + Python)

Boilerplate bot trading berbasis AI yang mengintegrasikan data pasar dari **MetaTrader 5 (MT5)** dengan tiga model bahasa besar (LLM) terkemuka: **OpenAI**, **Google Gemini**, dan **DeepSeek** via API. 

Dirancang khusus untuk strategi **scalping M5 (5 menit)** pada Forex & Gold (`XAUUSD`). Bot ini memanggil ketiga AI secara paralel, melakukan voting/konsensus (2 dari 3 AI harus sepakat), lalu mengeksekusi order secara otomatis ke terminal MT5 Anda.

---

## 📂 Struktur Proyek

* `config.py` : Berisi konfigurasi trading (symbol, lot, timeframe, SL/TP) dan nama model AI.
* `mt5_connector.py` : Modul untuk berkomunikasi dengan aplikasi MetaTrader 5 (ambil data, hitung indikator teknikal, eksekusi order).
* `llm_client.py` : Modul yang menangani pemanggilan paralel ke API OpenAI, Gemini, dan DeepSeek.
* `consensus.py` : Mesin voting untuk menentukan apakah sinyal BUY/SELL memenuhi threshold kesepakatan (2 dari 3 model).
* `test_apis.py` : Script pembantu untuk memverifikasi apakah semua API Key di file `.env` aktif dan terhubung.
* `main.py` : Script utama yang menjalankan bot secara looping setiap penutupan candle M5.
* `.env.example` : Contoh konfigurasi API Key dan akun MT5.

---

## 🛠️ Langkah-Langkah Instalasi & Penggunaan

### 1. Prasyarat (Prerequisites)
* **Sistem Operasi**: Windows (wajib karena library `MetaTrader5` hanya berjalan di Windows).
* **Python**: Versi 3.8 - 3.11 disarankan.
* **Aplikasi MT5**: Unduh dan instal terminal MetaTrader 5 dari broker Anda (misal: VT Markets) dan login ke akun demo Anda.

### 2. Instalasi Library Python
Buka terminal/PowerShell di direktori proyek ini, lalu jalankan:
```bash
pip install -r requirements.txt
```

### 3. Konfigurasi API Key & Akun
1. Salin file `.env.example` menjadi `.env`:
   ```bash
   copy .env.example .env
   ```
2. Buka file `.env` dan masukkan API Key Anda untuk:
   * `OPENAI_API_KEY`
   * `GEMINI_API_KEY`
   * `DEEPSEEK_API_KEY`
3. (Opsional) Jika ingin bot otomatis login ke akun MT5 Anda, isi data `MT5_LOGIN`, `MT5_PASSWORD`, dan `MT5_SERVER`. Jika dikosongkan, bot akan otomatis menyambung ke terminal MT5 yang saat itu sedang aktif di PC Anda.

### 4. Uji Coba API Key
Jalankan script test untuk memastikan semua kunci API Anda aktif:
```bash
python test_apis.py
```
*Jika salah satu API gagal, periksa saldo atau validitas API Key di dashboard masing-masing provider.*

### 5. Menjalankan Bot
Pastikan aplikasi MT5 Anda dalam keadaan terbuka dan terhubung ke internet, lalu jalankan:
```bash
python main.py
```
Secara default, bot berjalan dalam **`DRY_RUN = True`** (Mode Sinyal / Paper Trading). Bot akan menampilkan analisis di layar, tetapi **tidak akan** melakukan trading dengan uang beneran.

---

## ⚡ Mengaktifkan Live Execution
Jika Anda sudah yakin dengan hasil sinyal AI dan ingin bot langsung mengeksekusi order otomatis ke MT5:
1. Buka `config.py`.
2. Ubah baris berikut:
   ```python
   DRY_RUN = False
   ```
3. Jalankan kembali bot (`python main.py`). *Sangat disarankan mencoba di **Akun Demo** terlebih dahulu!*

---

## ⚠️ Disclaimer
Trading instrumen keuangan seperti Forex dan Gold memiliki tingkat risiko yang sangat tinggi. Bot ini disediakan sebagai kerangka kerja teknologi (boilerplate) dan contoh integrasi AI. Penggunaan bot untuk trading nyata sepenuhnya merupakan tanggung jawab pengguna. Selalu uji coba strategi Anda secara mendalam menggunakan akun demo sebelum mempertaruhkan modal nyata.
