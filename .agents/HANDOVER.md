# 📋 PANDUAN LENGKAP HANDOVER AGENT — PROYEK APKX (v1.4.2)

> **Untuk Agent Baru**: Dokumen ini merangkum seluruh konteks historis, keputusan arsitektur, hasil audit independen, status pengujian, dan instruksi tindakan konkret untuk melanjutkan pengembangan tool `apkx` tanpa kehilangan arah atau mengulang kesalahan masa lalu.

---

## 1. 📌 Identitas & Lingkungan Proyek

* **Repositori**: `/home/bakso/projects/apkx`
* **Remote Git**: `https://github.com/rafyaditya/apkx.git` (Cabang aktif: `main`)
* **Python Environment (pipx)**: `/home/bakso/.local/share/pipx/venvs/apkx/bin/python`
* **Linter Executable**: `/home/bakso/.local/share/pipx/venvs/apkx/bin/ruff`
* **Test Suite Runner**: `python3 -m unittest discover tests` (atau menggunakan binary pipx venv)
* **Reinstall Command**: `pipx install --editable . --force`
* **GitHub Actions**: `.github/workflows/ci.yml` menguji 5 versi Python matrix (`3.10`, `3.11`, `3.12`, `3.13`, `3.14`). Semua job saat ini berstatus **HIJAU / SUCCESS**.
* **Kredensial Git**: GitHub Personal Access Token (PAT) user sudah memiliki izin `Read and write` untuk `Contents` dan `Workflows`. `git push origin main` berjalan lancar tanpa hambatan autentikasi.

---

## 2. 📜 Rekapitulasi Perjalanan & Kronologi Perbaikan

### Fase 1: Rilis v1.4.0 (Pembersihan Bug Fundamental)
1. **Import `Any` di Python ≤ 3.13**: Memperbaiki `NameError` di `packager.py` dan `setup_mcp.py`.
2. **Exit Code CLI `apkx serve`**: Mengubah alur exception agar tidak menangkap `typer.Exit(0)` sebagai kegagalan.
3. **Screenshot Path**: Memastikan folder output kosong menghasilkan `output/screen.png`, bukan file bernama `output`.
4. **Decoder AXML (Binary XML)**: Menambahkan algoritma 2-pass root namespace hoisting untuk mengatasi namespace bersarang; terverifikasi valid pada 28 manifest APK Android nyata.
5. **Backup Konfigurasi MCP**: Menambahkan pembuatan backup `.bak` otomatis saat file konfigurasi klien AI rusak/korup.
6. **Packaging Wheel**: Menambahkan file `SKILL.md` dan `LICENSE` (MIT) ke dalam metadata Wheel.
7. **Filter List Apps & Devices**: Memperbaiki `list_apps(include_system_apps=True)` dan penanganan `adb_not_found` yang ramah JSON.
8. **JADX & ADB**: Memperbaiki checksum SHA-256 JADX dan menambahkan batas timeout subprocess.

### Fase 2: Rilis v1.4.1 (Ketahanan Terhadap File Korup & CI Matrix)
1. **Penanganan Arsip Rusak pada MCP**: Tool `apkx_pull_and_extract` kini mengembalikan JSON terstruktur `status: error` jika APK yang ditarik korup/rusak, bukan melempar uncaught exception.
2. **Penanganan Arsip Rusak pada Endpoints**: `extract_endpoints_from_file` menolak arsip korup dengan format JSON error yang bersih.
3. **Escaping Input Teks ADB**: Menangani karakter shell khusus (`"`, `'`, `&`, `|`, `$`, `*`, `?`, `[`, `]`, dsb.) dan baris baru (`\n`).
4. **Pembersihan File Stale (Clean Re-extraction)**: Menghapus file sisa dari ekstraksi sebelumnya saat melakukan unpack ulang.
5. **CI 5 Matrix Jobs**: Menyiapkan GitHub Actions CI untuk Python 3.10–3.14.

---

## 3. 🔍 Hasil Audit Independen v1.4.1 & Temuan Kritis

Seorang agent reviewer independen telah menguji repositori `v1.4.1` (commit `d0f5fd8`). Hasil verifikasinya membuktikan:
- ✅ CI 5 job hijau (Run ID: 42483099000).
- ✅ 133 unit test lulus 100%.
- ✅ 28 manifest AXML lokal terurai valid oleh ElementTree.
- ✅ Penanganan APK korup pada MCP dan endpoints berfungsi benar.

**NAMUN**, auditor menemukan **1 Regresi Kritis (High Severity: Data Loss)** dan beberapa perbaikan minor yang wajib diselesaikan pada **v1.4.2**:

### 🚨 Temuan #1 (High Severity): Regresi Data Loss pada `packager.unpack()`
* **Lokasi**: `apk_extractor/packager.py:342-352`
* **Penyebab**: Kode pembersihan file lama menghapus isi `target_dir` **sebelum** `zipfile.ZipFile(archive_path)` memvalidasi arsip.
* **Dampak**: Jika file APK korup, terpotong, atau berekstensi tidak didukung (misal `.zip`), isi folder ekstraksi lama yang masih valid **musnah terhapus**.
* **Solusi Wajib (Atomic Staging Pattern)**:
  1. Validasi ekstensi `.apk` dan `.apks` (lempar `ValueError` eksplisit jika ekstensi lain).
  2. Validasi `zipfile.is_zipfile(archive_path)` sebelum menyentuh `target_dir`.
  3. Ekstrak konten ke temporary staging directory (`tempfile.mkdtemp(prefix="apkx_stage_unpack_")`).
  4. Hanya jika ekstraksi ke temporary directory berhasil 100%, bersihkan `target_dir` dan pindahkan file dari staging ke `target_dir`.
  5. Dalam blok `finally`: bersihkan folder temporary staging dengan `shutil.rmtree(..., ignore_errors=True)`.
  6. Tambahkan unit test: pastikan file lama di `target_dir` tetap ada jika unpack file korup gagal.

### ⚠️ Temuan #2 (Medium Severity): MCP Catch Terlalu Luas
* **Lokasi**: `apk_extractor/mcp_server.py:184`
* **Masalah**: `except (zipfile.BadZipFile, OSError, Exception) as e:` menelan semua error pemrograman dan menyamarkannya sebagai "arsip rusak".
* **Solusi**: Ubah menjadi `except (zipfile.BadZipFile, OSError, ValueError) as e:`.

### ⚠️ Temuan #3 (Low Severity): Linter `ruff check .` Menemukan 2 Error `E741`
* **Lokasi**: `apk_extractor/adb.py:183` dan `adb.py:983`
* **Masalah**: Menggunakan nama variabel ambiguous satu huruf `l` (`[l.strip() for l in ...]` dan `for l in selected`).
* **Solusi**: Ganti variabel `l` menjadi `line`.
* **CI Update**: Perbarui `.github/workflows/ci.yml` agar menjalankan `ruff check .` penuh, bukan `--select F,E9`.

### ⚠️ Temuan #4 (Low Severity): Deprecation `project.license` di `pyproject.toml`
* **Lokasi**: `pyproject.toml:11`
* **Masalah**: `license = { text = "MIT" }` memicu warning deprecation dari setuptools.
* **Solusi**: Ubah menjadi `license = "MIT"` (format SPDX) dan naikkan versi paket ke `1.4.2`.

### ⚠️ Temuan #5 (Low Severity): CLI Help `--devices` Belum Menyebut Kontrak JSON
* **Lokasi**: `apk_extractor/cli.py:159-163`
* **Solusi**: Perbarui `help` string pada opsi `--devices` agar mendokumentasikan output JSON berupa `List[DeviceInfo]` atau `[]`.

### ⚠️ Temuan #6 (Low Severity): Edge Case Escaping Teks ADB
* **Lokasi**: `apk_extractor/adb.py:930-960`
* **Masalah**: Karakter `\r` belum dinormalisasi, karakter literal `%` dapat bentrok dengan representasi spasi `%s` Android, dan returncode dari `keyevent 66` sebelumnya diabaikan tanpa cek.
* **Solusi**: Normalisasi `\r\n` dan `\r` ke `\n`, amankan karakter `%`, dan periksa returncode `keyevent 66`.

---

## 4. 🚀 Daftar Tindakan Konkret untuk Agent Baru (Release v1.4.2)

Agent baru disarankan langsung mengeksekusi perbaikan v1.4.2 berikut:

```bash
# 1. Edit apk_extractor/packager.py -> Atomic staging unpack + validation
# 2. Edit apk_extractor/mcp_server.py -> Persempit tuple exception
# 3. Edit apk_extractor/adb.py -> Fix l -> line, normalisasi \r dan keyevent returncode
# 4. Edit pyproject.toml -> license = "MIT", version = "1.4.2"
# 5. Edit apk_extractor/__init__.py -> __version__ = "1.4.2"
# 6. Edit apk_extractor/cli.py -> Update help text --devices
# 7. Edit .github/workflows/ci.yml -> ruff check .
# 8. Tambah unit test di tests/test_packager.py -> test_unpack_corrupt_archive_preserves_existing_target
```

### Verifikasi Mandiri Sebelum Push:
```bash
# Jalankan Linter (Wajib 0 Error)
/home/bakso/.local/share/pipx/venvs/apkx/bin/ruff check .

# Jalankan Test Suite (Wajib Lulus Semua, 134+ test)
python3 -m unittest discover tests

# Build & Reinstall Editable
pipx install --editable . --force

# Git Commit & Push
git add -A
git commit -m "fix(v1.4.2): atomic unpack staging to prevent data loss, fix ruff E741, license spdx, and adb escaping"
git push origin main
```

---

## 5. 🛡️ Prinsip Kerja Penting (`RULE[user_global]`)

Agent baru **wajib** mematuhi:
1. **Factual Accuracy & Calibrated Honesty**: Jangan pernah berhalusinasi, membuat-buat angka, atau mengklaim perbaikan tanpa bukti verifikasi nyata dari test runner atau linter.
2. **Tidak Defensif**: Jika auditor atau pengguna menemukan bug/regresi, verifikasi dengan tenang, akui secara terbuka, dan perbaiki akar masalahnya dengan arsitektur yang solid.
3. **Format Komunikasi**: Gunakan bahasa Indonesia yang lugas, profesional, dan cantumkan clickable link file markdown `file:///...` untuk setiap file yang dimodifikasi.
