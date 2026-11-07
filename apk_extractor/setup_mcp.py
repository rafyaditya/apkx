"""
apkx: Auto-Configurator for AI Agent MCP Clients.
Detects installed AI coding agents (Antigravity, Cursor, Claude Desktop, Windsurf, VS Code)
and automatically configures the apkx MCP server without manual JSON editing.
"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Tuple


ANTIGRAVITY_SKILL_NAME = "apkx-android-blueprint"

SKILL_TEMPLATE = """---
name: apkx-android-blueprint
description: Master skill for reverse engineering, inspecting, and translating extracted Android APKs/APKS (using apkx) into clean architectural blueprints and cloned applications (Flutter, React Native, or Native Android). Use whenever the user asks to analyze an Android app extracted via apkx, inspect APK manifests, examine DEX class skeletons, find API endpoints, or rebuild/clone an app's features from APK blueprints.
---

# Android APK Reverse Engineering & Blueprint Synthesis (apkx)

Tujuan utama skill ini adalah memandu AI Agent dalam menganalisis berkas APK/APKS hasil ekstraksi `apkx` secara metodis, mengekstrak arsitektur inti aplikasi, menemukan endpoint API backend, dan menyusun cetak biru (*blueprint*) yang siap diimplementasikan ulang (dikloning) ke framework modern seperti **Flutter**, **React Native**, atau **Kotlin Clean Architecture**.

---

## 1. Prinsip Utama: Clean-Room Reverse Engineering

1. **Evidence-Based (Berbasis Bukti):** Jangan pernah menebak struktur data, endpoint API, atau logika bisnis jika Anda bisa memverifikasinya langsung dari artefak `apkx` (Manifest, `endpoints.json`, `class_skeleton.txt`, atau dekompilasi JADX).
2. **Precision Over Context Bloat (Fokus & Presisi):** Jangan membaca seluruh file dump raksasa jika tidak diperlukan. Gunakan tool pencarian terarah seperti `apkx_find_classes` dan `apkx_search_endpoints` untuk menemukan jarum di tumpukan jerami.
3. **Clean-Room Reimplementation:** Hasil reverse engineering digunakan sebagai acuan arsitektur (kontrak API, model data, dan alur UI), kemudian dibangun ulang secara bersih menggunakan standar dan *best practices* framework target (misalnya menerapkan *Flutter Anti-Slop*).

---

## 2. Alur Investigasi 5 Langkah (5-Phase Workflow)

### Fase 1: Deteksi Framework & Quick Audit
Sebelum memeriksa kode secara mendalam, kenali teknologi dasar aplikasi target:
1. Jalankan `apkx_get_app_info(package_name)`.
2. Periksa Framework terdeteksi:
   * **Flutter:** Memiliki `libflutter.so` dan `libapp.so`. Logika di compiled native AOT `libapp.so`. Fokus pada string URL di `endpoints.json` dan resource asset di `assets/flutter_assets/`.
   * **React Native:** Memiliki `index.android.bundle`. Fokus pada pemetaan URL, nama rute komponen, dan state schema dari bundle JS.
   * **Java/Kotlin Native:** Menggunakan pure DEX bytecode multi-split. Kode sumber Java/Kotlin dapat didekomposisi sempurna secara selektif via `apkx_inspect_class`.

### Fase 2: Pemetaan Entry-Point & Permissions
Gunakan tool `apkx_get_manifest(target_path)` untuk membaca `AndroidManifest_readable.xml`:
1. Cari Main Launcher Activity (`android.intent.action.MAIN` + `android.intent.category.LAUNCHER`).
2. Identifikasi Deep Links & Navigasi URL (`<data android:scheme="..." android:host="..."/>`).
3. Audit Izin (Permissions).

### Fase 3: Pemetaan Backend & API Endpoints
Gunakan tool `apkx_search_endpoints(target_path, query=...)`:
1. Cari Domain Utama (`apkx_search_endpoints(target_path)`).
2. Cari Endpoint Fitur Tertentu:
   * Otentikasi: `query="auth"` atau `query="login"`.
   * API Versi: `query="/v1/"` atau `query="/v2/"`.
   * Fitur Utama: `query="product"`, `query="user"`, atau `query="cart"`.

### Fase 4: Bedah Model Data & Logika Bisnis (Java/Kotlin Native)
1. Cari Kelas Relevan dengan `apkx_find_classes(target_path, query=...)`.
2. Dekomposisi On-Demand dengan `apkx_inspect_class(target_apk, class_name)`.

### Fase 5: Sintesis Blueprint Kloning Aplikasi
Susun laporan Blueprint Arsitektur untuk pengguna:
1. Ringkasan Identitas Aplikasi.
2. Pohon Arsitektur Fitur.
3. Kontrak API & Model Data (Entity / DTO).
4. Rancangan Implementasi di Framework Target (Flutter / React Native).
"""


def sync_antigravity_skill() -> Dict[str, str]:
    """Installs or updates the apkx Antigravity skill in ~/.gemini/config/skills/."""
    try:
        skill_dir = Path.home() / ".gemini" / "config" / "skills" / ANTIGRAVITY_SKILL_NAME
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(SKILL_TEMPLATE.strip() + "\n", encoding="utf-8")
        return {
            "client": "Antigravity Skill (apkx-android-blueprint)",
            "status": "success",
            "path": str(skill_file.resolve()),
        }
    except Exception as e:
        return {
            "client": "Antigravity Skill (apkx-android-blueprint)",
            "status": "error",
            "path": "",
            "error": str(e),
        }


def get_target_config_paths() -> List[Tuple[str, Path]]:
    """Returns detected configuration paths for supported AI clients."""
    home = Path.home()
    configs = []

    # 1. Antigravity Global Config
    antigravity_path = home / ".gemini" / "config" / "mcp_config.json"
    configs.append(("Google Antigravity", antigravity_path))

    # 2. Claude Desktop
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            claude_path = Path(appdata) / "Claude" / "claude_desktop_config.json"
            configs.append(("Claude Desktop", claude_path))
    elif sys.platform == "darwin":
        claude_path = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        configs.append(("Claude Desktop", claude_path))
    else:
        claude_path = home / ".config" / "Claude" / "claude_desktop_config.json"
        configs.append(("Claude Desktop", claude_path))

    # 3. Cursor
    cursor_global = home / ".cursor" / "mcp.json"
    configs.append(("Cursor (Global)", cursor_global))

    # 4. Windsurf
    windsurf_path = home / ".codeium" / "windsurf" / "mcp_config.json"
    configs.append(("Windsurf", windsurf_path))

    # 5. VS Code (Cline / Roo-Code)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            cline_path = (
                Path(appdata)
                / "Code"
                / "User"
                / "globalStorage"
                / "saoudrizwan.claude-dev"
                / "settings"
                / "cline_mcp_settings.json"
            )
            configs.append(("VS Code Cline/Roo-Code", cline_path))
    else:
        cline_path = (
            home
            / ".config"
            / "Code"
            / "User"
            / "globalStorage"
            / "saoudrizwan.claude-dev"
            / "settings"
            / "cline_mcp_settings.json"
        )
        configs.append(("VS Code Cline/Roo-Code", cline_path))

    return configs


def get_apkx_executable_command() -> Tuple[str, List[str]]:
    """
    Returns the exact command line and arguments to run apkx serve.
    Uses the system apkx executable if available, or sys.executable -m apk_extractor.mcp_server.
    """
    apkx_bin = shutil.which("apkx")
    if apkx_bin:
        return (apkx_bin, ["serve"])
    return (sys.executable, ["-m", "apk_extractor.mcp_server"])


def install_mcp_to_all_clients() -> List[Dict[str, str]]:
    """
    Automatically discovers and updates all installed AI client configuration files.
    Returns summary results for each client.
    """
    cmd, args = get_apkx_executable_command()
    server_entry = {
        "command": cmd,
        "args": args,
    }

    results = []
    targets = get_target_config_paths()

    for name, path in targets:
        # Check if parent folder exists (meaning client is installed or relevant)
        # For Antigravity, we always create and configure it
        is_antigravity = "Antigravity" in name
        if not path.parent.exists() and not is_antigravity:
            continue

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data: Dict[str, Any] = {}
            if path.is_file() and path.stat().st_size > 0:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}

            if "mcpServers" not in data:
                data["mcpServers"] = {}

            data["mcpServers"]["apkx"] = server_entry
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

            results.append({
                "client": name,
                "status": "success",
                "path": str(path.resolve()),
            })
        except Exception as e:
            results.append({
                "client": name,
                "status": "error",
                "path": str(path.resolve()),
                "error": str(e),
            })

    # Sinkronisasi skill Antigravity otomatis
    skill_res = sync_antigravity_skill()
    if skill_res:
        results.append(skill_res)

    return results
