"""
Updater module for apkx.
Checks for new versions on GitHub and performs automatic self-updates.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple
import urllib.request
import urllib.error

from rich.console import Console
from rich.panel import Panel

from apk_extractor import __version__ as CURRENT_VERSION

REPO_OWNER = "rafyaditya"
REPO_NAME = "apkx"
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
GITHUB_RAW_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/main/apk_extractor/__init__.py"
GIT_REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}.git"

console = Console()
console_err = Console(stderr=True)


def parse_semver(ver: str) -> Tuple[int, ...]:
    """Mengurai string versi seperti '1.0.1' atau 'v1.1.0' menjadi tuple angka (1, 0, 1)."""
    clean_ver = ver.strip().lstrip("v")
    parts = re.findall(r"\d+", clean_ver)
    return tuple(map(int, parts)) if parts else (0,)


def is_newer_version(remote: str, local: str = CURRENT_VERSION) -> bool:
    """Mengembalikan True jika versi remote lebih baru daripada versi lokal."""
    return parse_semver(remote) > parse_semver(local)


def fetch_latest_version(timeout: float = 5.0) -> Optional[str]:
    """
    Mengambil versi rilis terbaru dari GitHub.
    Mencoba GitHub Releases API terlebih dahulu, lalu fallback ke raw __init__.py.
    """
    # 1. Coba GitHub Releases API
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "User-Agent": f"apkx-cli/{CURRENT_VERSION}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                tag = data.get("tag_name", "")
                if tag:
                    return tag.strip().lstrip("v")
    except Exception:
        pass

    # 2. Fallback ke raw file di GitHub
    try:
        req_raw = urllib.request.Request(
            GITHUB_RAW_URL,
            headers={"User-Agent": f"apkx-cli/{CURRENT_VERSION}"},
        )
        with urllib.request.urlopen(req_raw, timeout=timeout) as resp:
            if resp.status == 200:
                content = resp.read().decode("utf-8")
                m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
                if m:
                    return m.group(1).strip().lstrip("v")
    except Exception:
        pass

    return None


def detect_install_method() -> Tuple[str, Optional[Path]]:
    """
    Mendeteksi bagaimana apkx terpasang:
    - ('git', repo_root) jika dijalankan langsung dari repository git lokal
    - ('pipx', None) jika berjalan di dalam virtualenv pipx
    - ('pip', None) jika berjalan di virtualenv / pip standar
    """
    repo_root = Path(__file__).resolve().parent.parent
    if (repo_root / ".git").is_dir() and shutil.which("git"):
        return "git", repo_root

    if "pipx" in sys.prefix or "pipx" in sys.executable:
        if shutil.which("pipx"):
            return "pipx", None

    return "pip", None


def execute_update(method: str, repo_root: Optional[Path] = None) -> Tuple[bool, str]:
    """
    Menjalankan proses pembaruan sesuai metode instalasi yang terdeteksi.
    Mengembalikan (success: bool, message: str).
    """
    try:
        if method == "git" and repo_root:
            pull_res = subprocess.run(
                ["git", "-C", str(repo_root), "pull", "--ff-only", "origin", "main"],
                capture_output=True,
                text=True,
                check=False,
            )
            if pull_res.returncode != 0:
                pull_res = subprocess.run(
                    ["git", "-C", str(repo_root), "pull", "--ff-only"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            if pull_res.returncode != 0:
                return False, f"Git pull gagal:\n{pull_res.stderr.strip() or pull_res.stdout.strip()}"

            # Re-install package editable di environment aktif
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", str(repo_root), "--no-deps"],
                capture_output=True,
                check=False,
            )
            return True, "Berhasil memperbarui repository lokal via Git."

        elif method == "pipx":
            upg_res = subprocess.run(
                ["pipx", "upgrade", "apkx"],
                capture_output=True,
                text=True,
                check=False,
            )
            if upg_res.returncode == 0:
                return True, "Berhasil memperbarui apkx via pipx."

            # Fallback jika package diinstal via git URL
            reinst_res = subprocess.run(
                ["pipx", "install", "--force", f"git+{GIT_REPO_URL}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if reinst_res.returncode == 0:
                return True, "Berhasil memperbarui apkx via pipx dari GitHub."
            return False, f"Gagal memperbarui via pipx:\n{reinst_res.stderr.strip()}"

        else:  # pip
            pip_res = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", f"git+{GIT_REPO_URL}"],
                capture_output=True,
                text=True,
                check=False,
            )
            if pip_res.returncode == 0:
                return True, "Berhasil memperbarui apkx via pip."
            return False, f"Gagal memperbarui via pip:\n{pip_res.stderr.strip()}"

    except Exception as e:
        return False, str(e)


def run_updater(check_only: bool = False, as_json: bool = False) -> int:
    """
    Fungsi entrypoint untuk perintah 'apkx update' atau 'apkx update --check'.
    Mengembalikan exit code (0 untuk sukses/up-to-date, 1 jika gagal).
    """
    if not as_json:
        console.print("[bold cyan]Memeriksa pembaruan apkx di GitHub...[/bold cyan]")

    latest_ver = fetch_latest_version()

    if latest_ver is None:
        if as_json:
            print(json.dumps({
                "status": "error",
                "message": "Gagal terhubung ke GitHub untuk memeriksa versi terbaru. Periksa koneksi internet Anda.",
                "current_version": CURRENT_VERSION,
                "latest_version": None,
                "update_available": False,
            }))
        else:
            console.print("[bold red][X][/bold red] Gagal terhubung ke GitHub untuk memeriksa versi terbaru.")
            console.print("[dim]Pastikan koneksi internet aktif atau coba beberapa saat lagi.[/dim]")
        return 1

    newer = is_newer_version(latest_ver, CURRENT_VERSION)
    method, repo_root = detect_install_method()

    if not newer:
        if as_json:
            print(json.dumps({
                "status": "up_to_date",
                "message": f"apkx sudah menggunakan versi terbaru (v{CURRENT_VERSION}).",
                "current_version": CURRENT_VERSION,
                "latest_version": latest_ver,
                "update_available": False,
                "install_method": method,
            }))
        else:
            console.print(f"\n[bold green][V] apkx sudah menggunakan versi terbaru![/bold green] (v{CURRENT_VERSION})")
        return 0

    # Ada versi baru
    if check_only:
        if as_json:
            print(json.dumps({
                "status": "update_available",
                "current_version": CURRENT_VERSION,
                "latest_version": latest_ver,
                "update_available": True,
                "install_method": method,
            }))
        else:
            console.print(Panel(
                f"[bold yellow]Versi baru tersedia: v{latest_ver}[/bold yellow]\n"
                f"Versi saat ini: [dim]v{CURRENT_VERSION}[/dim]\n\n"
                f"Jalankan [bold cyan]apkx update[/bold cyan] untuk menginstal pembaruan secara otomatis.",
                title="[bold green]Pembaruan Tersedia[/bold green]",
                border_style="green",
            ))
        return 0

    # Lakukan update
    if not as_json:
        console.print(f"[bold yellow][*] Memperbarui apkx dari v{CURRENT_VERSION} ke v{latest_ver} (Metode: {method})...[/bold yellow]")

    success, msg = execute_update(method, repo_root)

    if success:
        if as_json:
            print(json.dumps({
                "status": "success",
                "message": f"Berhasil memperbarui ke v{latest_ver}.",
                "current_version": CURRENT_VERSION,
                "new_version": latest_ver,
                "install_method": method,
            }))
        else:
            console.print(f"\n[bold green][V] Pembaruan Berhasil![/bold green] apkx telah diperbarui ke v{latest_ver}.")
            console.print(f"[dim]{msg}[/dim]\n")
        return 0
    else:
        if as_json:
            print(json.dumps({
                "status": "error",
                "message": f"Pembaruan gagal: {msg}",
                "current_version": CURRENT_VERSION,
                "latest_version": latest_ver,
                "install_method": method,
            }))
        else:
            console.print(f"\n[bold red][X] Gagal melakukan pembaruan otomatis:[/bold red]\n{msg}")
        return 1
