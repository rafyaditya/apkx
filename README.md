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
   * `output/extracted/<Nama_App>/` : Menyimpan seluruh berkas bongkaran (`classes.dex`, `AndroidManifest.xml`, `assets/`, `res/`, `lib/`). Untuk Split APKs (`.apks`), pecahan diekstrak rapi ke subfolder (`base/`, `split_config.<arch>/`, dll.) dengan artefak analisis terintegrasi.
5. **Smart Framework Detection:**
   * Otomatis mendeteksi apakah aplikasi dibangun dengan **Flutter**, **React Native**, **Unity**, atau **Native Android**, dan menunjukkan lokasi file kode utamanya.
6. **Pure-Python Manifest & Endpoint Extractor:**
   * Mendekode binary `AndroidManifest.xml` menjadi teks XML valid tanpa AAPT/Java (`AndroidManifest_readable.xml`), menangani namespace bersarang, serta memindai seluruh URL backend, domain, dan REST/GraphQL API ke `endpoints.json`.
7. **Fast Pure-Python DEX Class Skeleton Parser:**
   * Membaca struktur paket dan kelas aplikasi tanpa Java (hanya puluhan hingga ratusan ms pada multi-DEX) tanpa pembengkakan token AI ke `class_skeleton.txt`.
8. **Ekstraksi Skema SQLite dari Biner Native (`libapp.so` / DEX):**
   * Memindai definisi tabel (`CREATE TABLE`), nama kolom, dan relasi database langsung dari file biner terkompilasi Flutter AOT (`libapp.so`) maupun bytecode Android DEX ke `sqlite_schema.sql` dan `sqlite_schema.json`.
9. **Headless On-Demand JADX Decompiler:**
   * Mengunduh JADX portable otomatis untuk dekompilasi source code Java/Kotlin, termasuk dekompilasi selektif untuk satu kelas tertentu (`--decompile-class`).
10. **Live Device Traversal & UI/UX Inspection via ADB:**
    * Mengontrol perangkat secara live: screenshot berkecepatan tinggi (`exec-out screencap`), ekstraksi posisi tombol presisi (`dump_ui_hierarchy`), simulasi interaksi sentuh (tap, swipe, input teks, tombol kembali), bangunkan layar, dan auto-unlock PIN.
11. **Autonomous Closed-Loop Testing & APK Deployment:**
    * Pasang langsung APK hasil build ke perangkat fisik (`apkx_install_apk`), reset data seketika (`pm clear`), diagnosa crash/exception tertarget via filtered logcat (`apkx_get_app_logs`), serta verifikasi adaptasi Dark Mode / Light Mode.
12. **AI-Native MCP Server & Antigravity Skill (23 Tools):**
    * Siap berkolaborasi langsung dengan AI Coding Agent (Antigravity, Cursor, Claude Desktop, Windsurf, VS Code) via `apkx setup`, dilengkapi protokol pre-flight check perangkat dan SOP blueprint 8 fase.
13. **Zero-Config ADB (Auto-Download):**
    * Tidak perlu memasang Android Studio yang besar! Jika ADB belum terpasang, `apkx` otomatis mengunduh Google Platform-Tools resmi (~12 MB) secara instan. Bekerja di Windows, macOS, dan Linux.

---

## Prasyarat Sistem

1. **Python**:
   * Python versi **3.10 atau yang lebih baru** (mendukung Python 3.10, 3.11, 3.12, 3.13, 3.14).
   * Pada Windows, pastikan opsi *"Add python.exe to PATH"* dicentang saat instalasi Python.
2. **Git**:
   * Git terpasang di sistem untuk mengambil repositori dan menjalankan fitur `apkx update`.
3. **Java Runtime Environment / JRE 11+** *(Opsional, direkomendasikan)*:
   * **Dibutuhkan jika:** Anda ingin menggunakan fitur dekompilasi kode sumber Java/Kotlin menggunakan JADX (`--decompile`, `--decompile-class`, atau tool MCP `apkx_inspect_class`).
   * **Tidak dibutuhkan jika:** Anda hanya melakukan ekstraksi APK, membaca manifest terdekode (AXML), memindai endpoint API, atau membaca class skeleton (semua fitur ini berjalan dengan *pure Python* tanpa Java).
   * *Cara cek di terminal:* `java -version`.
4. **ADB (Android Debug Bridge)** *(Otomatis / Zero-Config)*:
   * Jika ADB sudah terpasang di sistem Anda, `apkx` akan otomatis menggunakannya. Jika belum ada, `apkx` akan otomatis mengunduh binary resmi dari Google tanpa konfigurasi manual.
5. **AAPT / AAPT2** *(Opsional)*:
   * `apkx` menggunakan heuristik cerdas (termasuk Android `dumpsys`, cache codename internal, dan `aapt`/`aapt2` jika tersedia di PATH) untuk menampilkan nama ramah aplikasi (seperti "WhatsApp" alih-alih `com.whatsapp`). Jika `aapt` terpasang, resolusi nama dari resource string APK akan semakin lengkap.
6. **Koneksi Internet**:
   * Diperlukan saat instalasi pertama kali, pengunduhan binary ADB/JADX otomatis, serta saat menjalankan pembaruan `apkx update`.

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
Opsi ini melewati dialog pemilihan tindakan sehingga proses berlangsung otomatis dan cepat. Pada eksekusi langsung via CLI (misal: `apkx whatsapp`), `apkx` secara default menjalankan mode `--both` (simpan installer APK sekaligus ekstrak isinya) kecuali jika `-k` (`--apk-only`) atau `-x` (`--extract-only`) ditentukan.

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

### 12. Dekompilasi Kode Sumber Java/Kotlin (--decompile & --decompile-class)
`apkx` mengintegrasikan engine JADX Headless portable secara otomatis untuk merekonstruksi kode sumber Java dari file DEX:
```powershell
# Dekompilasi seluruh source code aplikasi:
apkx whatsapp --decompile

# Dekompilasi on-demand hanya untuk satu kelas spesifik (sangat cepat & hemat token AI):
apkx whatsapp --decompile-class "com.whatsapp.authentication.FingerprintView"
```
*(Catatan: Memerlukan JRE/JDK 11+ terpasang pada komputer Anda).*

### 13. Perintah Kontrol Perangkat & Testing dari Terminal (CLI Parity)
Pengguna manusia dapat menjalankan seluruh perintah interaksi perangkat langsung dari terminal tanpa mengetik sintaks ADB mentah:
```powershell
# Ambil screenshot HP berkecepatan tinggi:
apkx screenshot -o output/screen.png

# Pasang aplikasi (.apk biasa maupun .apks Split-APK via adb install-multiple otomatis):
apkx install build/app/outputs/flutter-apk/app-debug.apk
apkx install output/apks/WhatsApp.apks

# Hapus instalasi aplikasi dari perangkat:
apkx uninstall com.example.app

# Dapatkan hierarki UI dan koordinat sentuh tombol layar aktif:
apkx dump-ui
apkx dump-ui --json

# Lihat logcat error, exception, dan crash tertarget:
apkx logs com.example.app --tail 100

# Bangunkan layar dan buka kunci ponsel:
apkx wake --pin 1234
```

### 14. Integrasi Otomatis AI Coding Agent (MCP Server & Antigravity Skill)
Hubungkan `apkx` langsung ke AI Agent Anda (Google Antigravity, Cursor, Claude Desktop, Windsurf, VS Code) cukup dengan satu perintah tanpa perlu mengedit file JSON konfigurasi secara manual:
```bash
apkx setup
```
Perintah ini otomatis:
1. Memindai AI coding agent yang terpasang dan mendaftarkan server MCP `apkx serve`.
2. Menyinkronkan **Skill Antigravity** (`apkx-android-blueprint`) ke `~/.gemini/config/skills/` agar AI Agent memahami SOP analisis APK secara metodis.

Server MCP `apkx` menyediakan 23 tools siap pakai:
* `apkx_list_devices`: Pre-flight check & daftar perangkat Android terhubung lengkap dengan status kesiapan (READY, NO_DEVICE, UNAUTHORIZED) dan panduan troubleshooting.
* `apkx_list_apps`: Daftar aplikasi terpasang (nama aplikasi ramah + package ID).
* `apkx_get_app_info`: Audit teknis cepat (versi, SDK, permission) tanpa unduh APK.
* `apkx_pull_and_extract`: Tarik APK/APKS dari ponsel dan ekstrak seluruh artefak blueprint.
* `apkx_get_manifest`: Baca XML terbaca dari `AndroidManifest.xml` (termasuk dari dalam arsip `.apks`).
* `apkx_get_endpoints`: Ambil seluruh URL dan domain backend dari binary aplikasi.
* `apkx_get_class_skeleton`: Baca struktur paket dan kelas DEX tanpa token bloat.
* `apkx_inspect_class`: Dekompilasi on-demand satu kelas spesifik via JADX.
* `apkx_find_classes`: Cari kelas spesifik (misal: Auth, Repository, ViewModel) berdasarkan kata kunci.
* `apkx_search_endpoints`: Filter endpoint dan domain API berdasarkan kata kunci (misal: login, api, v1, graphql).
* `apkx_extract_sqlite_schema`: Ekstrak skema tabel SQLite dari biner `libapp.so` atau DEX secara otomatis (bebas truncation tipe kolom bersarang).
* `apkx_install_apk`: Pasang file APK atau .apks ke perangkat fisik (auto install-multiple, auto flag -r, -g, -d & diagnosa error).
* `apkx_uninstall_app`: Hapus instalasi aplikasi dari perangkat untuk reinstall bersih atau ganti signature.
* `apkx_launch_app`: Buka aplikasi target atau aplikasi kloningan di HP Android (`am start -S`).
* `apkx_take_screenshot`: Ambil tangkapan layar perangkat berkecepatan tinggi via `adb exec-out`.
* `apkx_dump_ui_hierarchy`: Dapatkan posisi titik tengah `[center_x, center_y]` seluruh tombol & elemen UI.
* `apkx_interact`: Jalankan aksi tap koordinat, tombol kembali (back), home, swipe, atau pengetikan teks.
* `apkx_ensure_device_awake`: Bangunkan layar, auto-unlock PIN/swipe, dan aktifkan pencegah layar tidur USB.
* `apkx_get_current_screen`: Deteksi nama Activity & proses PID yang sedang aktif di puncak layar.
* `apkx_get_app_logs`: Perekam log error & crash tertarget khusus aplikasi target (Flutter/React Native/Android).
* `apkx_reset_app_data`: Reset total data aplikasi (`pm clear`) untuk pengujian ulang fresh-install state.
* `apkx_open_deep_link`: Buka rute halaman spesifik via URL/Deep Link Intent secara langsung.
* `apkx_toggle_night_mode`: Beralih antara Dark Mode dan Light Mode untuk verifikasi visual multi-tema.

### 15. Pembaruan Otomatis (Self-Update)
Periksa dan perbarui `apkx` ke versi terbaru langsung dari GitHub:
```bash
# Periksa dan perbarui otomatis jika versi baru tersedia:
apkx update

# Hanya periksa ketersediaan versi baru tanpa menginstal:
apkx update --check
```

---

## Ringkasan Argumen dan Opsi (CLI Reference)

| Argumen / Opsi | Alias | Tipe | Keterangan |
| :--- | :--- | :--- | :--- |
| `[query]` | - | String | Nama aplikasi, package ID, atau sub-perintah (`devices`, `screenshot`, `install`, `uninstall`, `logs`, `dump-ui`, `wake`, `serve`, `setup`, `update`). |
| `[target]` | - | String | Target berkas APK/APKS atau nama package untuk perintah `install`, `uninstall`, dan `logs`. |
| `--devices` | - | Flag | Menampilkan daftar perangkat Android yang terhubung (output JSON berupa array `List[DeviceInfo]` atau `[]` jika kosong). |
| `--output` | `-o` | Path | Direktori utama penyimpanan hasil (default: `./output`). |
| `--device` | `-d` | String | Serial ID perangkat spesifik jika ada lebih dari satu ponsel terhubung. |
| `--tail` | `-t` | Int | Jumlah baris logcat terakhir untuk perintah `apkx logs` (default: 80). |
| `--pin` | - | String | PIN perangkat untuk membuka layar pada perintah `apkx wake`. |
| `--list` | `-l` | Flag | Menampilkan daftar aplikasi di terminal tanpa melakukan ekstraksi. |
| `--all` | `-a` | Flag | Menyertakan seluruh aplikasi (pihak ketiga + sistem). |
| `--system` | `-s` | Flag | Memfilter hanya aplikasi bawaan sistem Android. |
| `--apk-only` | `-k` | Flag | Hanya simpan installer APK (.apk/.apks) tanpa mengekstrak isinya. |
| `--extract-only` | `-x` | Flag | Hanya ekstrak isi APK (dex, res, assets) tanpa menyimpan file APK. |
| `--both` | `-b` | Flag | Simpan file installer APK sekaligus ekstrak isinya (default eksekusi langsung CLI). |
| `--info`, `--analyze` | - | Flag | Tampilkan audit dan informasi teknis aplikasi tanpa ekstraksi. |
| `--recent` | `-r` | Flag | Urutkan aplikasi berdasarkan waktu instalasi atau pembaruan terbaru. |
| `--json` | - | Flag | Keluarkan output dalam format JSON untuk otomasi dan scripting. |
| `--decompile` | - | Flag | Dekomposisi penuh seluruh kode sumber Java menggunakan JADX. |
| `--decompile-class` | - | String | Dekomposisi on-demand untuk satu kelas tertentu menggunakan JADX. |
| `--serve`, `--mcp` | - | Flag | Jalankan server Model Context Protocol (MCP) untuk AI Agent. |
| `--update` | `-u` | Flag | Periksa dan perbarui apkx ke versi terbaru dari GitHub. |
| `--check` | - | Flag | Hanya periksa pembaruan tanpa mengunduh atau menginstal. |
| `--version` | `-v` | Flag | Tampilkan versi apkx dan keluar. |
| `--help` | - | Flag | Menampilkan bantuan ringkas seluruh perintah dan opsi yang tersedia. |
