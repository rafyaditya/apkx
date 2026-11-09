# 📋 PANDUAN LENGKAP HANDOVER AGENT — PROYEK APKX (v1.4.3)

> **Untuk Agent Baru**: Dokumen ini merangkum seluruh konteks historis, keputusan arsitektur, hasil audit independen, status pengujian, dan instruksi tindakan konkret untuk melanjutkan pengembangan tool `apkx` tanpa kehilangan arah atau mengulang kesalahan masa lalu.

---

## 1. 📌 Identitas & Lingkungan Proyek

* **Repositori**: `$REPO_ROOT` (mis. `~/projects/apkx`)
* **Remote Git**: `https://github.com/rafyaditya/apkx.git` (Cabang rilis: `release/v1.4.3`, Cabang utama: `main`)
* **Python Environment (pipx)**: `$PIPX_VENV/bin/python` (mis. `~/.local/share/pipx/venvs/apkx/bin/python`)
* **Linter Executable**: `$RUFF` (mis. `~/.local/share/pipx/venvs/apkx/bin/ruff`)
* **Test Suite Runner**: `pytest --cov=apk_extractor --cov-report=term tests/`
* **Reinstall Command**: `pipx install --editable . --force`
* **GitHub Actions**: `.github/workflows/ci.yml` menguji 5 versi Python matrix (`3.10`, `3.11`, `3.12`, `3.13`, `3.14`) dan build/smoke verification job.
* **Kredensial Git**: Gunakan kredensial lokal pengguna yang terkonfigurasi pada mesin (`gh auth login` atau SSH key). Jangan pernah menyimpan token/kredensial ke dalam file repository.

---

## 2. 📜 Rekapitulasi Perjalanan & Kronologi Perbaikan

### Fase 1: Rilis v1.4.0 (Pembersihan Bug Fundamental)
1. **Import `Any` di Python ≤ 3.13**: Memperbaiki `NameError` di `packager.py` dan `setup_mcp.py`.
2. **Exit Code CLI `apkx serve`**: Mengubah alur exception agar tidak menangkap `typer.Exit(0)` sebagai kegagalan.
3. **Screenshot Path**: Memastikan folder output kosong menghasilkan `output/screen.png`, bukan file bernama `output`.
4. **Decoder AXML (Binary XML)**: Menambahkan algoritma 2-pass root namespace hoisting untuk mengatasi namespace bersarang.
5. **Backup Konfigurasi MCP**: Menambahkan pembuatan backup `.bak` otomatis saat file konfigurasi klien AI rusak/korup.
6. **Packaging Wheel**: Menambahkan file `SKILL.md` dan `LICENSE` (MIT) ke dalam metadata Wheel.
7. **Filter List Apps & Devices**: Memperbaiki `list_apps(include_system_apps=True)` dan penanganan `adb_not_found` yang ramah JSON.
8. **JADX & ADB**: Memperbaiki checksum SHA-256 JADX dan menambahkan batas timeout subprocess.

### Fase 2: Rilis v1.4.1 (Ketahanan Terhadap File Korup & CI Matrix)
1. **Penanganan Arsip Rusak pada MCP**: Tool `apkx_pull_and_extract` mengembalikan JSON terstruktur `status: error`.
2. **Penanganan Arsip Rusak pada Endpoints**: `extract_endpoints_from_file` menolak arsip korup dengan format JSON error yang bersih.
3. **Escaping Input Teks ADB**: Menangani karakter shell khusus (`"`, `'`, `&`, `|`, `$`, `*`, `?`, `[`, `]`, dsb.) dan baris baru (`\n`).
4. **Pembersihan File Stale (Clean Re-extraction)**: Menghapus file sisa dari ekstraksi sebelumnya saat melakukan unpack ulang.
5. **CI 5 Matrix Jobs**: Menyiapkan GitHub Actions CI untuk Python 3.10–3.14.

### Fase 3: Rilis v1.4.2 (Audit & Atomic Staging)
1. **Atomic Staging Unpack**: Mencegah data loss saat membongkar APK korup.
2. **Ruff Clean**: Memperbaiki ambiguous variable names (E741) dan linter warnings.
3. **SPDX License & Typing**: Memperbaiki metadata `license = "MIT"` pada `pyproject.toml`.

### Fase 4: Rilis v1.4.3 (Arsitektur Produksi & Keandalan Menyeluruh)
1. **P1 (Atomic Commit & Staging Same-FS)**: Staging direktori di filesystem yang sama dengan target (`target.parent`), atomic swap via `os.replace`, marker JSON pemulihan transaksi crash, lock file anti-race condition, dan pembersihan berkas sementara `.part` secara atomik.
2. **P2 (MCP Boundary & Structured Errors)**: Seluruh tool MCP dibungkus error boundary terstruktur (`APP_NOT_FOUND`, `APK_NOT_FOUND`, `DEVICE_NOT_READY`, `ADB_ERROR`, `INVALID_ARCHIVE`, `INVALID_PATH`, `INVALID_QUERY`, `IO_ERROR`, `INTERNAL_ERROR`), tidak ada yang melempar uncaught exception. Validasi path containment mencegah path traversal.
3. **P3 (AXML Scoped Namespace Parser)**: Implementasi namespace stack berbasis scope event XML, parsing multi-byte length UTF-8 (135+ bytes), unsigned 32-bit hex attribute formatting, dan CDATA `0x0104`.
4. **P4 (ADB Literal `%s` Chunking)**: Pembagian teks ADB aman tanpa mengubah literal `%` menjadi `\%` yang merusak input teks biasa.
5. **P5 (Skill Preservation)**: Integritas direktori `.agents/skills` dan package data terjamin byte-identical.
6. **P6 (Testing & Code Quality)**:
   - Modul `archive_utils.py` mandiri mencegah circular import dan memvalidasi Zip Slip / path traversal / zip bomb.
   - Modul `logger.py` terpusat dengan `NullHandler`.
   - Coverage pengujian komprehensif mencapai ≥ 85% dengan 275+ unit test.
   - Dual-job CI workflow: matrix testing (3.10–3.14) dengan mypy dan coverage threshold, disusul package build, twine check, dan fresh venv smoke testing.

---

## 3. 🚀 Verifikasi Mandiri

Jalankan perintah berikut sebelum merilis:

```bash
# 1. Jalankan Linter (Wajib 0 error)
$RUFF check .

# 2. Jalankan Type Checker (Wajib 0 error)
$PIPX_VENV/bin/mypy apk_extractor

# 3. Jalankan Test Suite & Coverage (Wajib 100% lulus, Coverage >= 85%)
$PIPX_VENV/bin/pytest --cov=apk_extractor --cov-report=term tests/

# 4. Build Wheel & SDist
$PIPX_VENV/bin/python -m build

# 5. Verifikasi Metadata Package
$PIPX_VENV/bin/twine check dist/*
```

---

## 4. 🛡️ Prinsip Kerja Penting (`RULE[user_global]`)

Agent baru **wajib** mematuhi:
1. **Factual Accuracy & Calibrated Honesty**: Jangan pernah berhalusinasi, membuat-buat angka, atau mengklaim perbaikan tanpa bukti verifikasi nyata dari test runner atau linter.
2. **Tidak Defensif**: Jika auditor atau pengguna menemukan bug/regresi, verifikasi dengan tenang, akui secara terbuka, dan perbaiki akar masalahnya dengan arsitektur yang solid.
3. **Format Komunikasi**: Gunakan bahasa Indonesia yang lugas, profesional, dan cantumkan clickable link file markdown `file:///...` untuk setiap file yang dimodifikasi.
