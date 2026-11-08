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
from typing import Any, Dict, List, Tuple


ANTIGRAVITY_SKILL_NAME = "apkx-android-blueprint"

SKILL_TEMPLATE = """---
name: apkx-android-blueprint
description: Master skill for reverse engineering, inspecting, live UI/UX traversal, and translating extracted Android APKs/APKS (using apkx) into clean architectural blueprints and cloned applications (Flutter, React Native, or Native Android). Use whenever the user asks to analyze an Android app extracted via apkx, inspect APK manifests, examine DEX class skeletons, find API endpoints, explore target app screens via ADB, or rebuild/clone an app's features with live device verification.
---

# Android APK Reverse Engineering, Live UI Traversal & Blueprint Synthesis (apkx)

Tujuan utama skill ini adalah memandu AI Agent dalam menganalisis berkas APK/APKS hasil ekstraksi `apkx` secara metodis, mengekstrak arsitektur inti aplikasi, memetakan skema database (termasuk SQLite di `libapp.so`), menjelajahi seluruh fitur UI aplikasi target secara langsung di ponsel melalui ADB (*screencap & tap*), menyusun cetak biru (*blueprint*) arsitektur, dan memverifikasi aplikasi hasil kloningan langsung di perangkat fisik dengan siklus perbaikan mandiri (*Self-Healing Loop*).

---

## 1. Prinsip Utama: Clean-Room Reverse Engineering & Verification

1. **Evidence-Based (Berbasis Bukti):** Jangan pernah menebak struktur data, endpoint API, atau logika bisnis jika Anda bisa memverifikasinya langsung dari artefak `apkx` (Manifest, `endpoints.json`, `class_skeleton.txt`, `sqlite_schema.sql`, atau dekompilasi JADX).
2. **Live Visual Grounding (Eksplorasi Layar Nyata):** Blueprint statis tidak menggambarkan alur UX secara utuh. Buka aplikasi target di ponsel via ADB, ambil screenshot untuk tiap tab dan modal, lalu gunakan penalaran visual multimodal AI untuk mengidentifikasi tata letak, warna, dan kelemahan UI aplikasi asli.
3. **Clean-Room Reimplementation:** Hasil reverse engineering digunakan sebagai acuan arsitektur (kontrak API, model data, dan alur UI), kemudian dibangun ulang secara bersih menggunakan standar framework target (misalnya menerapkan *Flutter Anti-Slop*).
4. **Autonomous Runtime Verification (Self-Healing):** Jangan anggap pekerjaan selesai sebelum aplikasi yang dibangun berhasil diinstall ke HP dan diuji coba langsung. Jalankan simulasi interaksi (tap, form input, submit) dan segera perbaiki jika ditemukan error atau glitch visual.

---

## 2. Alur Kerja Utama 8 Fase (8-Phase Master Workflow)

0. **Fase 0: Pre-Flight Check & Panduan Perangkat** (Cek koneksi perangkat via `apkx_list_devices()`; beri pesan panduan 4-langkah ramah jika belum terhubung atau butuh izin RSA).
1. **Fase 1: Deteksi Framework & Quick Audit** (Audit versi, SDK, dan teknologi Flutter/RN/Native).
2. **Fase 2: Pemetaan Entry-Point, Permissions & Skema Database** (Manifest + pemindaian SQLite biner).
3. **Fase 3: Pemetaan Backend & Endpoint API** (Pencarian domain dan rute API).
4. **Fase 4: Live Target App Exploration via ADB** (Buka aplikasi target via `apkx_launch_app`, ambil tangkapan layar `apkx_take_screenshot`, navigasi tab/FAB/drawer via `apkx_interact`, dan baca titik tombol via `apkx_dump_ui_hierarchy`).
5. **Fase 5: Sintesis Blueprint Kloning Aplikasi** (Kontrak API, skema entity data, dan daftar perbaikan UI).
6. **Fase 6: Rekonstruksi Aplikasi Bersih** (Pembangunan arsitektur Flutter/Clean Architecture dengan standar anti-slop).
7. **Fase 7: Post-Deployment Live Device Testing & Self-Healing Loop** (Install ke ponsel via `apkx_install_apk`, jalankan aplikasi baru via `apkx_launch_app`, verifikasi visual lewat screenshot `apkx_take_screenshot`, simulasikan input form via `apkx_interact`, dan perbaiki bug secara otomatis jika ditemukan anomali).
"""


def load_skill_content() -> str:
    """Loads skill content from package data, local .agents file if available, or falls back to template."""
    # 1. Package resources (included in pip/wheel distribution)
    try:
        import importlib.resources as pkg_resources
        data_text = (
            pkg_resources.files("apk_extractor")
            .joinpath("data", "skills", ANTIGRAVITY_SKILL_NAME, "SKILL.md")
            .read_text(encoding="utf-8")
        )
        if data_text and len(data_text) > 100:
            return data_text.strip()
    except Exception:
        pass

    # 2. Local development checkout (.agents/)
    local_file = Path(__file__).resolve().parent.parent / ".agents" / "skills" / ANTIGRAVITY_SKILL_NAME / "SKILL.md"
    if local_file.is_file():
        try:
            content = local_file.read_text(encoding="utf-8").strip()
            if len(content) > 100:
                return content
        except Exception:
            pass

    # 3. Fallback template
    return SKILL_TEMPLATE.strip()


def sync_antigravity_skill() -> Dict[str, str]:
    """Installs or updates the apkx Antigravity skill in ~/.gemini/config/skills/."""
    try:
        skill_dir = Path.home() / ".gemini" / "config" / "skills" / ANTIGRAVITY_SKILL_NAME
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"
        content = load_skill_content()
        skill_file.write_text(content + "\n", encoding="utf-8")
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
                    loaded = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        data = loaded
                    else:
                        raise ValueError("Root configuration is not a JSON object")
                except Exception:
                    # Backup berkas konfigurasi yang rusak sebelum ditulis ulang
                    backup_path = path.with_suffix(path.suffix + ".bak")
                    try:
                        shutil.copy2(path, backup_path)
                    except Exception:
                        pass
                    data = {}

            if "mcpServers" not in data or not isinstance(data.get("mcpServers"), dict):
                data["mcpServers"] = {}

            data["mcpServers"]["apkx"] = server_entry

            # Atomic write via temporary file
            content_str = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            temp_file = path.with_suffix(".tmp")
            temp_file.write_text(content_str, encoding="utf-8")
            temp_file.replace(path)

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
