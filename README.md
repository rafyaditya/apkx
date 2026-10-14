# apkx - Android APK & Split-APK Extractor CLI

Tool CLI interaktif dan cepat untuk mengekstrak dan menganalisis file APK dari aplikasi yang sudah terinstall di perangkat Android ke komputer Anda.

Mendukung otomatisasi penuh untuk **Single APK** (`.apk`) maupun **Split APKs / App Bundles** (`.apks`), dengan kemampuan **Unpack Isi Berkas** dan **Deteksi Framework (Flutter / React Native / Native)** secara otomatis.

---

## Fitur Unggulan

1. **Perintah Mandiri (*Standalone Global Command*):**
   * Cukup ketik `apkx` di terminal mana saja tanpa awalan `python`.
2. **Penamaan Berdasarkan Nama Aplikasi Asli:**
   * File installer dan folder ekstrak diberi nama sesuai nama asli aplikasi (misal: `Easybudget.apks`, `WhatsApp.apk`, `DANA.apks`), bukan nama package teknis yang membingungkan.
3. **Pemilihan Tindakan Terintegrasi di TUI (Action Modal):**
   * Saat memilih aplikasi di TUI, dialog elegan akan muncul menanyakan tindakan:
     * `[1]` Ambil File APK Saja (ke `output/apks/`)
     * `[2]` Ambil & Ekstrak Isi APK (ke `output/extracted/<Nama_App>/`)
     * `[3]` Keduanya (Simpan APK + Ekstrak Isi)
4. **Struktur Output yang Rapi:**
   * `output/apks/` : Menyimpan file installer `.apk` atau `.apks`.
   * `output/extracted/<Nama_App>/` : Menyimpan seluruh berkas bongkaran (`classes.dex`, `AndroidManifest.xml`, `assets/`, `res/`, `lib/`).
5. **Smart Framework Detection:**
   * Otomatis mendeteksi apakah aplikasi dibangun dengan **Flutter**, **React Native**, **Unity**, atau **Native Android**, dan menunjukkan lokasi file kode utamanya.
6. **Modern TUI Dashboard:**
   * Tabel 3 kolom (No, Nama Aplikasi, Package ID), kolom pencarian instan, dan kartu preview detail.
7. **Zero-Config ADB (Auto-Download):**
   * Tidak perlu memasang Android Studio yang besar! Jika ADB belum terpasang, `apkx` otomatis mengunduh Google Platform-Tools resmi (~12 MB) secara instan. Bekerja di Windows, macOS, dan Linux.

---

## Prasyarat Sistem

1. **Python**: Python versi 3.10 atau yang lebih baru (pastikan opsi "Add python.exe to PATH" aktif saat instalasi di Windows).
2. **Git**: Git terpasang di sistem untuk mengambil repositori.
3. **Koneksi Internet**: Diperlukan saat instalasi pertama kali untuk mengunduh package dan binary ADB resmi dari Google.

---

## Cara Instalasi Global

Cukup jalankan satu baris perintah ini di terminal (PowerShell / CMD / Bash):
```bash
pip install git+https://github.com/rafyaditya/apkx.git
```

*Atau jika menggunakan `pipx` (alat CLI terisolasi):*
```bash
pipx install git+https://github.com/rafyaditya/apkx.git
```

---

## Persiapan Perangkat Android

1. Aktifkan **USB Debugging** di menu Developer Options HP Anda.
2. Sambungkan HP ke PC via kabel USB dan pilih **Allow / Izinkan USB Debugging**.
3. Cek koneksi di terminal:
   ```powershell
   apkx devices
   ```

---

## Cara Penggunaan

### 1. Mode Interaktif Penuh (TUI Dashboard)
```powershell
apkx
```
Membuka antarmuka TUI interaktif layar penuh. Gunakan tombol panah atas/bawah untuk bernavigasi, ketik kata kunci untuk mencari secara instan, dan tekan Enter untuk membuka menu tindakan (Ambil APK, Ekstrak Isi, atau Keduanya). Tekan tombol Esc untuk keluar.

### 2. Memeriksa Perangkat yang Terhubung
```powershell
apkx devices
# atau
apkx --devices
```
Menampilkan tabel perangkat Android yang terhubung lengkap dengan Serial ID, Merk & Model HP, Versi OS, dan status izin USB Debugging.

### 3. Ekstraksi Cepat dengan Nama atau Package
```powershell
apkx whatsapp
# atau
apkx com.google.android.youtube
```
Langsung mencari aplikasi yang cocok dan mengekstraknya tanpa perlu mencari manual di daftar panjang.

### 4. Menentukan Direktori Penyimpanan Custom
```powershell
apkx -o D:\HasilEkstrak
# atau
apkx whatsapp --output C:\AnalisaAPK
```
Menentukan lokasi folder penyimpanan output. Jika tidak ditentukan, output akan otomatis disimpan di folder `./output`.

### 5. Memilih Perangkat Spesifik atau Multi-Perangkat
```powershell
apkx -d EU99MJMVKREIWCDY
# atau
apkx --device emulator-5554
```
Menentukan perangkat secara spesifik menggunakan Serial ID jika terdapat lebih dari satu ponsel yang terhubung. Jika opsi -d tidak disertakan saat beberapa ponsel tersambung, apkx akan menampilkan menu pilihan untuk memilih perangkat target atau opsi "[Semua Perangkat]" untuk memproses seluruh perangkat secara berurutan.

### 6. Menampilkan Daftar Aplikasi di Terminal (Non-Interaktif)
```powershell
apkx --list
# atau
apkx -l
```
Mencetak seluruh daftar aplikasi terpasang langsung ke layar terminal dalam bentuk tabel ringkas tanpa membuka TUI.

### 7. Filter Aplikasi Bawaan Sistem (System Apps)
```powershell
apkx -s
# atau hanya aplikasi sistem tertentu:
apkx -s settings
```
Gunakan `-s` atau `--system` untuk memfilter hanya aplikasi bawaan sistem. Gunakan `-a` atau `--all` untuk menampilkan seluruh aplikasi (pihak ketiga + sistem).

### 8. Memilih Tindakan Eksekusi Langsung (--apk-only, --extract-only, --both)
```powershell
# Hanya download installer APK tanpa ekstrak isi:
apkx whatsapp -k

# Hanya ekstrak isi file APK tanpa menyimpan file installer APK:
apkx whatsapp -x

# Simpan APK sekaligus ekstrak isinya secara eksplisit:
apkx whatsapp -b
```
Opsi ini melewati dialog pemilihan tindakan sehingga proses berlangsung otomatis dan cepat.

### 9. Audit & Informasi Teknis Aplikasi (--info / --analyze)
```powershell
apkx whatsapp --info
# atau dengan output JSON:
apkx whatsapp --info --json
```
Menampilkan audit teknis lengkap (versi aplikasi, versionCode, target/min SDK, izin/permissions, lokasi berkas APK di ponsel, format Single/Split APK) tanpa perlu mengunduh file APK.

### 10. Mengurutkan Berdasarkan Aplikasi Terbaru (--recent)
```powershell
apkx -r
# atau dikombinasikan dengan tabel daftar:
apkx -l -r
```
Mengurutkan aplikasi berdasarkan waktu pemasangan atau pembaruan terakhir di perangkat Android.

### 11. Mode Integrasi & Otomasi JSON (--json)
```powershell
# Daftar perangkat dalam format JSON:
apkx --devices --json

# Daftar aplikasi dalam format JSON:
apkx --list --json

# Ekstraksi dengan output status JSON untuk scripting:
apkx whatsapp -k --json
```

---

## Ringkasan Argumen dan Opsi (CLI Reference)

| Argumen / Opsi | Alias | Tipe | Keterangan |
| :--- | :--- | :--- | :--- |
| `[query]` | - | String | Nama aplikasi atau potongan Package ID (opsional). Jika dikosongkan, membuka mode interaktif TUI. |
| `--devices` | - | Flag | Menampilkan daftar perangkat Android yang terhubung ke komputer. |
| `--output` | `-o` | Path | Direktori utama penyimpanan hasil (default: `./output`). |
| `--device` | `-d` | String | Serial ID perangkat spesifik jika ada lebih dari satu ponsel terhubung. |
| `--list` | `-l` | Flag | Menampilkan daftar aplikasi di terminal tanpa melakukan ekstraksi. |
| `--all` | `-a` | Flag | Menyertakan seluruh aplikasi (pihak ketiga + sistem). |
| `--system` | `-s` | Flag | Memfilter hanya aplikasi bawaan sistem Android. |
| `--apk-only` | `-k` | Flag | Hanya simpan installer APK (.apk/.apks) tanpa mengekstrak isinya. |
| `--extract-only` | `-x` | Flag | Hanya ekstrak isi APK (dex, res, assets) tanpa menyimpan file APK. |
| `--both` | `-b` | Flag | Simpan file installer APK sekaligus ekstrak isinya (default). |
| `--info`, `--analyze` | - | Flag | Tampilkan audit dan informasi teknis aplikasi tanpa ekstraksi. |
| `--recent` | `-r` | Flag | Urutkan aplikasi berdasarkan waktu instalasi atau pembaruan terbaru. |
| `--json` | - | Flag | Keluarkan output dalam format JSON untuk otomasi dan scripting. |
| `--version` | `-v` | Flag | Tampilkan versi apkx dan keluar. |
| `--help` | - | Flag | Menampilkan bantuan ringkas seluruh perintah dan opsi yang tersedia. |
