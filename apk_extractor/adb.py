import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple


class ADBError(Exception):
    """Exception raised for ADB related errors."""
    pass


def find_adb_binary(adb_path: Optional[str] = None) -> str:
    """Finds an existing adb executable from arguments, PATH, bundle, or cache."""
    if adb_path:
        return adb_path

    # 1. System PATH
    system_adb = shutil.which("adb")
    if system_adb:
        return system_adb

    exe_name = "adb.exe" if sys.platform == "win32" else "adb"

    # 2. Bundled inside package
    bundled = Path(__file__).parent / "bin" / exe_name
    if bundled.is_file():
        return str(bundled)

    # 3. Cache directory ~/.apkx/platform-tools/
    cached = Path.home() / ".apkx" / "platform-tools" / exe_name
    if cached.is_file():
        return str(cached)

    return "adb"


class ADBManager:
    """Manages interactions with Android Debug Bridge (ADB)."""

    def __init__(self, adb_path: Optional[str] = None):
        self.adb_bin = find_adb_binary(adb_path)

    def is_installed(self) -> bool:
        """Checks if ADB executable is installed and reachable."""
        try:
            res = subprocess.run(
                [self.adb_bin, "version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            return res.returncode == 0
        except FileNotFoundError:
            # Re-check in case it was installed after init
            recheck = find_adb_binary()
            if recheck != self.adb_bin and recheck != "adb":
                self.adb_bin = recheck
                return self.is_installed()
            return False

    def ensure_installed(self, on_progress: Optional[Callable[[str], None]] = None) -> bool:
        """
        Ensures ADB is available. If missing, automatically downloads official Google platform-tools.
        """
        if self.is_installed():
            return True

        success = self.download_platform_tools(on_progress=on_progress)
        if success:
            recheck = find_adb_binary()
            self.adb_bin = recheck
            return self.is_installed()

        return False

    @staticmethod
    def download_platform_tools(on_progress: Optional[Callable[[str], None]] = None) -> bool:
        """
        Downloads and unpacks Google's official platform-tools for the current OS.
        """
        platform = sys.platform
        if platform == "win32":
            url = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
            exe_name = "adb.exe"
        elif platform == "darwin":
            url = "https://dl.google.com/android/repository/platform-tools-latest-darwin.zip"
            exe_name = "adb"
        elif platform.startswith("linux"):
            url = "https://dl.google.com/android/repository/platform-tools-latest-linux.zip"
            exe_name = "adb"
        else:
            return False

        target_base = Path.home() / ".apkx"
        target_base.mkdir(parents=True, exist_ok=True)
        zip_path = target_base / "platform-tools.zip"

        try:
            if on_progress:
                on_progress("Mengunduh Android Platform-Tools resmi dari Google...")

            urllib.request.urlretrieve(url, zip_path)

            if on_progress:
                on_progress("Mengekstrak platform-tools...")

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(target_base)

            if zip_path.is_file():
                zip_path.unlink()

            extracted_bin = target_base / "platform-tools" / exe_name
            if extracted_bin.is_file() and platform != "win32":
                os.chmod(extracted_bin, 0o755)

            return extracted_bin.is_file()
        except Exception as e:
            if on_progress:
                on_progress(f"Gagal mengunduh ADB: {e}")
            return False

    def get_connected_devices(self) -> List[Tuple[str, str]]:
        """
        Returns a list of connected devices as (serial, status) tuples.
        Status is usually 'device', 'unauthorized', or 'offline'.
        """
        try:
            res = subprocess.run(
                [self.adb_bin, "devices"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise ADBError(f"Gagal menjalankan adb devices: {e.stderr.strip()}")

        devices = []
        lines = res.stdout.strip().splitlines()
        for line in lines[1:]:  # Lewati baris pertama 'List of devices attached'
            parts = line.strip().split()
            if len(parts) >= 2:
                devices.append((parts[0], parts[1]))
        return devices

    def get_device_details(self, serial: str, status: str) -> dict:
        """
        Retrieves hardware details (brand, model, Android version) for a device.
        """
        info = {
            "serial": serial,
            "status": status,
            "brand": "-",
            "model": "-",
            "android_version": "-",
        }
        if status != "device":
            return info

        try:
            cmd = self._build_base_cmd(serial)
            cmd.extend([
                "shell",
                "getprop ro.product.brand; getprop ro.product.model; getprop ro.build.version.release",
            ])
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=4,
                check=False,
            )
            if res.returncode == 0:
                lines = [l.strip() for l in res.stdout.strip().splitlines() if l.strip()]
                if len(lines) >= 1 and lines[0]:
                    info["brand"] = lines[0].capitalize()
                if len(lines) >= 2 and lines[1]:
                    info["model"] = lines[1]
                if len(lines) >= 3 and lines[2]:
                    info["android_version"] = f"Android {lines[2]}"
        except Exception:
            pass

        return info

    def get_devices_with_details(self) -> List[dict]:
        """
        Returns a list of dictionaries containing device serial, status, and properties.
        """
        devices = self.get_connected_devices()
        results = []
        for serial, status in devices:
            results.append(self.get_device_details(serial, status))
        return results

    def _build_base_cmd(self, device_id: Optional[str] = None) -> List[str]:
        cmd = [self.adb_bin]
        if device_id:
            cmd.extend(["-s", device_id])
        return cmd

    def list_packages(
        self,
        device_id: Optional[str] = None,
        third_party_only: bool = True,
        system_only: bool = False,
    ) -> List[str]:
        """
        Lists installed package names on the target device.
        """
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "pm", "list", "packages"])
        if system_only:
            cmd.append("-s")
        elif third_party_only:
            cmd.append("-3")

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise ADBError(f"Gagal mengambil daftar package: {e.stderr.strip()}")

        packages = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                pkg = line.replace("package:", "").strip()
                if pkg:
                    packages.append(pkg)

        return sorted(packages)

    def get_package_recent_order(self, device_id: Optional[str] = None) -> List[str]:
        """
        Mengambil urutan package berdasarkan waktu instalasi/update terbaru.
        """
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "ls -td /data/app/* /data/app/*/* 2>/dev/null"])
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
            if res.returncode == 0:
                recent_pkgs = []
                for line in res.stdout.splitlines():
                    line = line.strip().rstrip("/")
                    part = line.split("/")[-1]
                    pkg_candidate = part.split("-")[0]
                    if "." in pkg_candidate and pkg_candidate not in recent_pkgs and not pkg_candidate.startswith("~~"):
                        recent_pkgs.append(pkg_candidate)
                return recent_pkgs
        except Exception:
            pass
        return []

    def get_package_quick_info(self, package_name: str, device_id: Optional[str] = None) -> dict:
        """
        Mengambil informasi teknis cepat dari aplikasi di perangkat tanpa menarik file APK.
        """
        import re
        info = {
            "package_name": package_name,
            "version_name": "-",
            "version_code": "-",
            "target_sdk": "-",
            "min_sdk": "-",
            "installed_time": "-",
            "updated_time": "-",
            "apk_paths": [],
            "apk_format": "Single APK",
            "permissions": [],
        }

        # 1. Ambil path APK
        paths = self.get_package_apk_paths(package_name, device_id=device_id)
        info["apk_paths"] = paths
        if len(paths) > 1:
            info["apk_format"] = f"Split APK ({len(paths)} part / .apks)"
        elif len(paths) == 1:
            info["apk_format"] = "Single APK (.apk)"

        # 2. Query dumpsys package
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", f"dumpsys package {package_name}"])
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
            if res.returncode == 0:
                perms = []
                for line in res.stdout.splitlines():
                    line_s = line.strip()
                    if "versionName=" in line_s and info["version_name"] == "-":
                        m = re.search(r"versionName=([^\s]+)", line_s)
                        if m:
                            info["version_name"] = m.group(1)
                    if "versionCode=" in line_s and info["version_code"] == "-":
                        m = re.search(r"versionCode=([0-9]+)", line_s)
                        if m:
                            info["version_code"] = m.group(1)
                    if "targetSdk=" in line_s and info["target_sdk"] == "-":
                        m = re.search(r"targetSdk=([0-9]+)", line_s)
                        if m:
                            info["target_sdk"] = m.group(1)
                    if "minSdk=" in line_s and info["min_sdk"] == "-":
                        m = re.search(r"minSdk=([0-9]+)", line_s)
                        if m:
                            info["min_sdk"] = m.group(1)
                    if "firstInstallTime=" in line_s and info["installed_time"] == "-":
                        info["installed_time"] = line_s.replace("firstInstallTime=", "").strip()
                    if "lastUpdateTime=" in line_s and info["updated_time"] == "-":
                        info["updated_time"] = line_s.replace("lastUpdateTime=", "").strip()
                    if "permission." in line_s:
                        m = re.search(r"([a-zA-Z0-9_\.]*permission\.[a-zA-Z0-9_]+)", line_s)
                        if m:
                            p = m.group(1).replace("android.permission.", "")
                            if p not in perms:
                                perms.append(p)
                info["permissions"] = perms
        except Exception:
            pass

        return info

    def get_package_apk_paths(self, package_name: str, device_id: Optional[str] = None) -> List[str]:
        """
        Returns all remote APK file paths for a given package.
        A package may have multiple APK paths if it is a Split APK.
        """
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "pm", "path", package_name])

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise ADBError(f"Gagal mengambil path APK untuk '{package_name}': {e.stderr.strip()}")

        paths = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                apk_path = line.replace("package:", "").strip()
                if apk_path:
                    paths.append(apk_path)

        return paths

    def pull_file(self, remote_path: str, local_path: str, device_id: Optional[str] = None) -> None:
        """
        Pulls a remote file from Android device to local filesystem.
        """
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["pull", remote_path, local_path])

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise ADBError(f"Gagal menarik file {remote_path}: {e.stderr.strip()}")
