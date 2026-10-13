# ⚡ apkx - Android APK & Split-APK Extractor CLI

Tool CLI interaktif dan cepat untuk mengekstrak dan menganalisis file APK dari aplikasi yang sudah terinstall di perangkat Android ke komputer Anda.

Mendukung otomatisasi penuh untuk **Single APK** (`.apk`) maupun **Split APKs / App Bundles** (`.apks`), dengan kemampuan **Unpack Isi Berkas** dan **Deteksi Framework (Flutter / React Native / Native)** secara otomatis.

---

## 🚀 Fitur Unggulan

1. **Perintah Mandiri (*Standalone Global Command*):**
   * Cukup ketik `apkx` di terminal mana saja tanpa awalan `python`.
2. **Penamaan Berdasarkan Nama Aplikasi Asli:**
   * File installer dan folder ekstrak diberi nama sesuai nama asli aplikasi (misal: `Easybudget.apks`, `WhatsApp.apk`, `DANA.apks`), bukan nama package teknis yang membingungkan.
3. **Pemilihan Tindakan Terintegrasi di TUI (Action Modal):**
   * Saat memilih aplikasi di TUI, dialog elegan akan muncul menanyakan tindakan:
     * `[1]` 📦 **Ambil File APK Saja** (ke `output/apks/`)
     * `[2]` 📂 **Ambil & Ekstrak Isi APK** (ke `output/extracted/<Nama_App>/`)
     * `[3]` ⚡ **Keduanya** (Simpan APK + Ekstrak Isi)
4. **Struktur Output yang Rapi:**
   * `output/apks/` : Menyimpan file installer `.apk` atau `.apks`.
   * `output/extracted/<Nama_App>/` : Menyimpan seluruh berkas bongkaran (`classes.dex`, `AndroidManifest.xml`, `assets/`, `res/`, `lib/`).
5. **Smart Framework Detection:**
   * Otomatis mendeteksi apakah aplikasi dibangun dengan **Flutter 🐦**, **React Native ⚛️**, **Unity 🎮**, atau **Native Android ☕**, dan menunjukkan lokasi file kode utamanya.
6. **Modern TUI Dashboard:**
   * Tabel 3 kolom (No, Nama Aplikasi, Package ID), kolom pencarian instan, dan kartu preview detail.
7. **Zero-Config ADB (Auto-Download):**
   * Tidak perlu memasang Android Studio yang besar! Jika ADB belum terpasang, `apkx` otomatis mengunduh Google Platform-Tools resmi (~12 MB) secara instan. Bekerja di Windows, macOS, dan Linux.

---

## 📦 Cara Instalasi Global

### Cara 1: Install Langsung dari Repositori Private (Komputer Lain)
Jalankan satu baris perintah ini di terminal (PowerShell / CMD / Terminal):
```bash
pip install git+https://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@github.com/rafyaditya/apkx.git
```
*Atau menggunakan `pipx` (alat CLI terisolasi):*
```bash
pipx install git+https://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@github.com/rafyaditya/apkx.git
```

### Cara 2: Install dari Kode Sumber Lokal (Development)
```bash
git clone https://github.com/rafyaditya/apkx.git
cd apk-download-and-extract
pip install -e .
```

---

## 🛠️ Persiapan Perangkat Android

1. Aktifkan **USB Debugging** di menu Developer Options HP Anda.
2. Sambungkan HP ke PC via kabel USB dan pilih **Allow / Izinkan USB Debugging**.
3. Cek koneksi di terminal:
   ```powershell
   adb devices
   ```

---

## 📖 Cara Penggunaan

### 1. Mode Interaktif Penuh (Rekomendasi)
```powershell
apkx
```
*Gunakan panah untuk memilih, ketik huruf untuk mencari, dan tekan **Enter** untuk memunculkan pilihan tindakan.*

### 2. Memilih Langsung dengan Nama Aplikasi
```powershell
apkx easybudget
# atau
apkx whatsapp
```

### 3. Menampilkan Daftar Aplikasi di Terminal
```powershell
apkx --list
```

### 4. Menyertakan Aplikasi Bawaan Sistem
```powershell
apkx -a
```
