"""
apkx: Zero-Config Headless JADX Integration.
Manages automatic detection, downloading, and execution of JADX (Dex-to-Java Decompiler).
"""

import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Optional

JADX_VERSION = "1.5.6"
JADX_DOWNLOAD_URL = f"https://github.com/skylot/jadx/releases/download/v{JADX_VERSION}/jadx-{JADX_VERSION}.zip"


class JADXError(Exception):
    """Exception raised for JADX related errors."""
    pass


def find_jadx_binary(custom_path: Optional[str] = None) -> str:
    """Finds an existing JADX executable from arguments, PATH, or ~/.apkx/jadx/."""
    if custom_path:
        return custom_path

    exe_name = "jadx.bat" if sys.platform == "win32" else "jadx"

    # 1. System PATH
    system_jadx = shutil.which("jadx")
    if system_jadx:
        return system_jadx

    if sys.platform == "win32":
        system_bat = shutil.which("jadx.bat")
        if system_bat:
            return system_bat

    # 2. Cache directory ~/.apkx/jadx/bin/
    cached = Path.home() / ".apkx" / "jadx" / "bin" / exe_name
    if cached.is_file():
        return str(cached)

    return exe_name


class JADXManager:
    """Manages headless interactions with the JADX decompiler."""

    def __init__(self, jadx_path: Optional[str] = None):
        self.jadx_bin = find_jadx_binary(jadx_path)

    @staticmethod
    def has_java() -> bool:
        """Checks if a Java Runtime Environment (JRE) is available in PATH."""
        return shutil.which("java") is not None

    def is_installed(self) -> bool:
        """Checks if JADX executable is available and can execute with Java."""
        if not self.has_java():
            return False

        try:
            res = subprocess.run(
                [self.jadx_bin, "-v"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=5,
            )
            return res.returncode == 0 or "jadx" in res.stdout.lower() or "jadx" in res.stderr.lower()
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            recheck = find_jadx_binary()
            if recheck != self.jadx_bin and recheck != "jadx":
                self.jadx_bin = recheck
                return self.is_installed()
            return False

    def ensure_installed(self, on_progress: Optional[Callable[[str], None]] = None) -> bool:
        """
        Ensures JADX is available. If missing and Java is present,
        automatically downloads the official portable JADX release.
        """
        if self.is_installed():
            return True

        if not self.has_java():
            if on_progress:
                on_progress("Java Runtime Environment (JRE) tidak ditemukan. Pasang Java 11+ terlebih dahulu.")
            return False

        success = self.download_jadx(on_progress=on_progress)
        if success:
            self.jadx_bin = find_jadx_binary()
            return self.is_installed()

        return False

    @staticmethod
    def download_jadx(on_progress: Optional[Callable[[str], None]] = None) -> bool:
        """
        Downloads and unpacks the official portable JADX release from GitHub.
        """
        target_base = Path.home() / ".apkx"
        jadx_dir = target_base / "jadx"
        zip_path = target_base / f"jadx-{JADX_VERSION}.zip"
        target_base.mkdir(parents=True, exist_ok=True)

        try:
            if on_progress:
                on_progress(f"Mengunduh JADX v{JADX_VERSION} portable dari GitHub...")

            # Use browser-like User-Agent for GitHub redirects
            req = urllib.request.Request(
                JADX_DOWNLOAD_URL,
                headers={"User-Agent": "apkx-installer/1.0"},
            )
            with urllib.request.urlopen(req) as resp, open(zip_path, "wb") as out_file:
                shutil.copyfileobj(resp, out_file)

            if on_progress:
                on_progress("Mengekstrak JADX portable...")

            jadx_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(jadx_dir)

            if zip_path.is_file():
                zip_path.unlink()

            bin_path = jadx_dir / "bin" / ("jadx.bat" if sys.platform == "win32" else "jadx")
            if bin_path.is_file() and sys.platform != "win32":
                os.chmod(bin_path, 0o755)

            return bin_path.is_file()
        except Exception as e:
            if on_progress:
                on_progress(f"Gagal mengunduh JADX: {e}")
            if zip_path.is_file():
                try:
                    zip_path.unlink()
                except Exception:
                    pass
            return False

    def decompile_class(
        self,
        target_path: Path,
        class_name: str,
        output_file: Optional[Path] = None,
    ) -> Optional[str]:
        """
        Decompiles a single specific class on-demand using headless JADX.
        Returns the decompiled Java source code string.
        """
        if not self.is_installed():
            return None

        temp_dir = Path(tempfile.mkdtemp(prefix="apkx_single_class_"))
        try:
            cmd = [
                self.jadx_bin,
                "-r",
                "--single-class",
                class_name,
                "-d",
                str(temp_dir),
                str(target_path),
            ]
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
                check=False,
            )
            # Find generated .java file
            java_files = list(temp_dir.glob("**/*.java"))
            if java_files:
                code = java_files[0].read_text(encoding="utf-8", errors="replace")
                if output_file:
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    output_file.write_text(code, encoding="utf-8")
                return code
            return None
        except Exception:
            return None
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def decompile_app(
        self,
        target_path: Path,
        output_dir: Path,
        no_res: bool = True,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        Decompiles an entire APK or APKS into Java sources.
        """
        if not self.is_installed():
            return False

        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [self.jadx_bin]
        if no_res:
            cmd.append("-r")
        cmd.extend(["-d", str(output_dir), str(target_path)])

        try:
            if on_progress:
                on_progress(f"Mendekomposisi kode dengan JADX ke {output_dir.name}...")

            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            return res.returncode == 0 or any(output_dir.glob("**/*.java"))
        except Exception as e:
            if on_progress:
                on_progress(f"Kesalahan saat menjalankan JADX: {e}")
            return False
