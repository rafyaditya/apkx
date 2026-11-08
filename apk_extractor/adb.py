import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


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

    def check_device_ready(
        self, device_id: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates ADB device connectivity and authorization state.
        Returns (is_ready, status_code, details_dict).

        Possible status codes:
        - 'READY': Device is connected, authorized, and ready for operations.
        - 'NO_DEVICE': No Android devices/emulators attached via ADB.
        - 'DEVICE_NOT_FOUND': Specified device_id does not match any attached device.
        - 'UNAUTHORIZED': Device is attached but not yet authorized (pending RSA prompt).
        - 'OFFLINE': Device is attached but in offline state.
        - 'ADB_ERROR': Error executing ADB command.
        """
        try:
            connected = self.get_connected_devices()
        except ADBError as e:
            return (
                False,
                "ADB_ERROR",
                {
                    "status": "error",
                    "code": "ADB_ERROR",
                    "message": f"Gagal mengecek status perangkat via ADB: {str(e)}",
                    "troubleshooting": [
                        "1. Pastikan ADB terpasang dan executable dapat dijalankan.",
                        "2. Coba jalankan: adb kill-server diikuti adb start-server.",
                    ],
                },
            )
        except Exception as e:
            return (
                False,
                "ADB_ERROR",
                {
                    "status": "error",
                    "code": "ADB_ERROR",
                    "message": f"Terjadi kesalahan saat memeriksa perangkat: {str(e)}",
                    "troubleshooting": [
                        "1. Pastikan ADB terpasang dan executable dapat dijalankan.",
                        "2. Coba jalankan: adb kill-server diikuti adb start-server.",
                    ],
                },
            )

        if not connected:
            return (
                False,
                "NO_DEVICE",
                {
                    "status": "error",
                    "code": "NO_DEVICE",
                    "message": "Tidak ada perangkat Android yang terdeteksi via ADB.",
                    "devices": [],
                    "troubleshooting": [
                        "1. Pastikan HP atau emulator Android terhubung ke komputer menggunakan kabel USB atau ADB Wi-Fi.",
                        "2. Pastikan 'Developer Options' (Opsi Pengembang) dan 'USB Debugging' sudah aktif di perangkat Android.",
                        "3. Buka layar HP dan periksa notifikasi/dialog USB debugging lalu pilih 'Allow' / 'Izinkan'.",
                        "4. Verifikasi status koneksi di terminal dengan perintah: apkx devices atau adb devices.",
                    ],
                },
            )

        # If specific device_id requested
        if device_id:
            matched = [d for d in connected if d[0] == device_id]
            if not matched:
                return (
                    False,
                    "DEVICE_NOT_FOUND",
                    {
                        "status": "error",
                        "code": "DEVICE_NOT_FOUND",
                        "message": f"Perangkat dengan Serial ID '{device_id}' tidak ditemukan di antara perangkat yang terhubung.",
                        "requested_id": device_id,
                        "connected_serials": [d[0] for d in connected],
                        "troubleshooting": [
                            "1. Jalankan tool apkx_list_devices untuk melihat daftar Serial ID perangkat yang terhubung.",
                            "2. Pastikan parameter device_id sesuai dengan salah satu Serial ID yang terdaftar.",
                        ],
                    },
                )
            target_serial, target_status = matched[0]
        else:
            # Prefer first ready ('device') device
            ready_devices = [d for d in connected if d[1] == "device"]
            if ready_devices:
                target_serial, target_status = ready_devices[0]
            else:
                target_serial, target_status = connected[0]

        if target_status == "unauthorized":
            return (
                False,
                "UNAUTHORIZED",
                {
                    "status": "error",
                    "code": "UNAUTHORIZED",
                    "message": f"Perangkat '{target_serial}' terdeteksi namun belum diizinkan (unauthorized).",
                    "serial": target_serial,
                    "troubleshooting": [
                        "1. Nyalakan dan buka kunci layar HP Anda.",
                        "2. Periksa dialog pop-up bertuliskan 'Allow USB debugging?' / 'Izinkan debugging USB?'.",
                        "3. Centang opsi 'Always allow from this computer' lalu tekan tombol 'Allow' / 'Izinkan'.",
                        "4. Cabut dan colokkan kembali kabel USB jika dialog tidak kunjung muncul di layar HP.",
                    ],
                },
            )

        if target_status == "offline":
            return (
                False,
                "OFFLINE",
                {
                    "status": "error",
                    "code": "OFFLINE",
                    "message": f"Perangkat '{target_serial}' dalam status offline.",
                    "serial": target_serial,
                    "troubleshooting": [
                        "1. Cabut dan colokkan kembali kabel USB perangkat.",
                        "2. Buka terminal dan jalankan: adb reconnect atau adb kill-server && adb start-server.",
                    ],
                },
            )

        if target_status == "device":
            details = self.get_device_details(target_serial, target_status)
            return (
                True,
                "READY",
                {
                    "status": "ready",
                    "code": "READY",
                    "serial": target_serial,
                    "details": details,
                    "message": f"Perangkat '{target_serial}' ({details.get('brand', '')} {details.get('model', '')}) siap digunakan.",
                },
            )

        return (
            False,
            target_status.upper(),
            {
                "status": "error",
                "code": target_status.upper(),
                "message": f"Perangkat '{target_serial}' dalam status '{target_status}'.",
                "serial": target_serial,
                "troubleshooting": [
                    "1. Periksa status koneksi perangkat.",
                    "2. Restart ADB server menggunakan perintah: adb kill-server && adb start-server.",
                ],
            },
        )

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
        cmd.extend(["shell", "dumpsys", "package", package_name])
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

    def pull_file(
        self,
        remote_path: str,
        local_path: str,
        device_id: Optional[str] = None,
        timeout: int = 180,
    ) -> None:
        """
        Pulls a remote file from Android device to local filesystem.
        """
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["pull", remote_path, local_path])

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise ADBError(f"Waktu habis ({timeout} detik) saat menarik file {remote_path} via ADB.")
        except subprocess.CalledProcessError as e:
            raise ADBError(f"Gagal menarik file {remote_path}: {e.stderr.strip()}")

    def get_screen_size(self, device_id: Optional[str] = None) -> Tuple[int, int]:
        """
        Retrieves physical screen resolution (width, height) of the connected Android device.
        """
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "wm", "size"])
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
            if res.returncode == 0:
                m = re.search(r"(\d+)x(\d+)", res.stdout)
                if m:
                    return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
        return (0, 0)

    def take_screenshot(self, output_path: Union[str, Path], device_id: Optional[str] = None) -> bool:
        """
        Captures a high-speed lossless screenshot from the connected device via exec-out screencap.
        Falls back to shell screencap and pull if needed.
        """
        dest_path = Path(output_path).resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Try exec-out screencap -p
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["exec-out", "screencap", "-p"])
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
            if res.returncode == 0 and len(res.stdout) > 1000 and res.stdout[:8] == b"\x89PNG\r\n\x1a\n":
                dest_path.write_bytes(res.stdout)
                return True
        except Exception:
            pass

        # 2. Fallback to shell screencap and pull
        try:
            remote_tmp = "/sdcard/apkx_screencap_tmp.png"
            c1 = self._build_base_cmd(device_id)
            c1.extend(["shell", "screencap", "-p", remote_tmp])
            subprocess.run(c1, timeout=8, check=False)

            self.pull_file(remote_tmp, str(dest_path), device_id=device_id)

            c2 = self._build_base_cmd(device_id)
            c2.extend(["shell", "rm", "-f", remote_tmp])
            subprocess.run(c2, timeout=5, check=False)

            return dest_path.is_file() and dest_path.stat().st_size > 0
        except Exception:
            return False

    def launch_app(
        self,
        package_name: str,
        activity_name: Optional[str] = None,
        restart: bool = True,
        device_id: Optional[str] = None,
    ) -> bool:
        """
        Launches an application activity on the device.
        If activity_name is omitted, attempts to auto-resolve the launcher activity.
        """
        target_activity = activity_name
        if not target_activity:
            cmd_res = self._build_base_cmd(device_id)
            cmd_res.extend(["shell", "cmd", "package", "resolve-activity", "--brief", package_name])
            try:
                p = subprocess.run(cmd_res, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4, check=False)
                if p.returncode == 0:
                    for line in p.stdout.splitlines():
                        line = line.strip()
                        if "/" in line and not line.startswith("priority="):
                            parts = line.split("/", 1)
                            if len(parts) == 2 and parts[1]:
                                target_activity = parts[1]
                                break
            except Exception:
                pass

        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "am", "start"])
        if restart:
            cmd.append("-S")

        if target_activity:
            comp = target_activity if "/" in target_activity else f"{package_name}/{target_activity}"
            cmd.extend(["-n", comp])
        else:
            cmd.extend(["-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", package_name])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8, check=False)
            return res.returncode == 0 and "error" not in res.stdout.lower()
        except Exception:
            return False

    def dump_ui_hierarchy(self, device_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Dumps current screen UI hierarchy using uiautomator and parses visible elements
        with their bounding boxes, text labels, and calculated center click points.
        """
        remote_file = "/sdcard/apkx_window_dump.xml"
        cmd_dump = self._build_base_cmd(device_id)
        cmd_dump.extend(["shell", "uiautomator", "dump", remote_file])

        try:
            dump_res = subprocess.run(cmd_dump, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10, check=False)
            if dump_res.returncode != 0:
                return []

            cmd_cat = self._build_base_cmd(device_id)
            cmd_cat.extend(["exec-out", "cat", remote_file])
            cat_res = subprocess.run(cmd_cat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8, check=False)

            cmd_rm = self._build_base_cmd(device_id)
            cmd_rm.extend(["shell", "rm", "-f", remote_file])
            subprocess.run(cmd_rm, timeout=4, check=False)

            xml_data = cat_res.stdout
            if not xml_data or "<hierarchy" not in xml_data:
                return []

            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_data)
            elements: List[Dict[str, Any]] = []

            for node in root.iter("node"):
                bounds_str = node.attrib.get("bounds", "")
                m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
                if not m:
                    continue

                x1, y1, x2, y2 = map(int, m.groups())
                width = x2 - x1
                height = y2 - y1
                if width <= 0 or height <= 0:
                    continue

                center_x = x1 + width // 2
                center_y = y1 + height // 2

                text = node.attrib.get("text", "").strip()
                res_id = node.attrib.get("resource-id", "").strip()
                content_desc = node.attrib.get("content-desc", "").strip()
                cls_name = node.attrib.get("class", "").strip()
                clickable = node.attrib.get("clickable", "false") == "true"
                scrollable = node.attrib.get("scrollable", "false") == "true"
                enabled = node.attrib.get("enabled", "true") == "true"

                if text or res_id or content_desc or clickable or scrollable:
                    elements.append({
                        "text": text,
                        "resource_id": res_id,
                        "content_desc": content_desc,
                        "class": cls_name,
                        "clickable": clickable,
                        "scrollable": scrollable,
                        "enabled": enabled,
                        "bounds": [x1, y1, x2, y2],
                        "center": [center_x, center_y],
                        "width": width,
                        "height": height,
                    })

            return elements
        except Exception:
            return []

    def input_interact(
        self,
        action: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        keycode: Optional[int] = None,
        text: Optional[str] = None,
        swipe_coords: Optional[Tuple[int, int, int, int]] = None,
        device_id: Optional[str] = None,
    ) -> bool:
        """
        Executes simulated UI actions: tap, back, home, enter, keyevent, text, or swipe.
        """
        cmd = self._build_base_cmd(device_id)
        cmd.append("shell")

        act_clean = action.strip().lower()
        if act_clean == "tap":
            if x is None or y is None:
                return False
            cmd.extend(["input", "tap", str(x), str(y)])
        elif act_clean in ("back", "key_back"):
            cmd.extend(["input", "keyevent", "4"])
        elif act_clean in ("home", "key_home"):
            cmd.extend(["input", "keyevent", "3"])
        elif act_clean in ("enter", "key_enter"):
            cmd.extend(["input", "keyevent", "66"])
        elif act_clean == "keyevent":
            if keycode is None:
                return False
            cmd.extend(["input", "keyevent", str(keycode)])
        elif act_clean == "text":
            if text is None:
                return False
            # Jika teks memiliki newline, kirim per baris dengan keyevent 66 (Enter)
            lines = text.split("\n")
            success = True
            for i, line in enumerate(lines):
                if line:
                    safe_text = line.replace("\\", "\\\\")
                    safe_text = safe_text.replace(" ", "%s")
                    for ch in (
                        '"', "'", "&", "|", ";", "$", "`", "<", ">",
                        "(", ")", "*", "?", "[", "]", "{", "}", "~", "#", "!"
                    ):
                        safe_text = safe_text.replace(ch, f"\\{ch}")
                    sub_cmd = self._build_base_cmd(device_id)
                    sub_cmd.extend(["shell", "input", "text", safe_text])
                    try:
                        p = subprocess.run(sub_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8, check=False)
                        if p.returncode != 0:
                            success = False
                    except Exception:
                        success = False
                if i < len(lines) - 1:
                    enter_cmd = self._build_base_cmd(device_id)
                    enter_cmd.extend(["shell", "input", "keyevent", "66"])
                    try:
                        subprocess.run(enter_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
                    except Exception:
                        pass
            return success
        elif act_clean == "swipe":
            if not swipe_coords or len(swipe_coords) < 4:
                return False
            x1, y1, x2, y2 = swipe_coords[:4]
            duration = swipe_coords[4] if len(swipe_coords) > 4 else 300
            cmd.extend(["input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)])
        else:
            return False

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8, check=False)
            return res.returncode == 0
        except Exception:
            return False

    def ensure_device_awake(
        self,
        pin: Optional[str] = None,
        stay_on: bool = True,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ensures device screen is awake and unlocked.
        - Activates stay_on_while_plugged_in if stay_on=True.
        - Wakes screen if asleep (keyevent 224).
        - Automatically unlocks swipe lockscreens (keyevent 82).
        - Unlocks with PIN if provided or if APKX_DEVICE_PIN environment variable is set.
        - Safely stops without guessing if locked with PIN/Password but no PIN is available.
        """
        if stay_on:
            try:
                cmd_stay = self._build_base_cmd(device_id)
                cmd_stay.extend(["shell", "settings", "put", "global", "stay_on_while_plugged_in", "3"])
                subprocess.run(cmd_stay, timeout=4, check=False)
            except Exception:
                pass

        is_asleep = False
        try:
            cmd_pwr = self._build_base_cmd(device_id)
            cmd_pwr.extend(["shell", "dumpsys", "power"])
            res_pwr = subprocess.run(cmd_pwr, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
            if "mWakefulness=Asleep" in res_pwr.stdout or "Display Power: state=OFF" in res_pwr.stdout:
                is_asleep = True
        except Exception:
            pass

        if is_asleep:
            self.input_interact("keyevent", keycode=224, device_id=device_id)
            import time
            time.sleep(0.5)

        is_locked = False
        try:
            cmd_win = self._build_base_cmd(device_id)
            cmd_win.extend(["shell", "dumpsys", "window"])
            res_win = subprocess.run(cmd_win, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
            if "mKeyguardShowing=true" in res_win.stdout or "isStatusBarKeyguard=true" in res_win.stdout:
                is_locked = True
        except Exception:
            pass

        if not is_locked:
            return {
                "status": "ready",
                "screen_on": True,
                "locked": False,
                "message": "Layar ponsel menyala dan tidak terkunci.",
            }

        target_pin = pin or os.environ.get("APKX_DEVICE_PIN")

        self.input_interact("keyevent", keycode=82, device_id=device_id)
        import time
        time.sleep(0.5)

        try:
            cmd_win = self._build_base_cmd(device_id)
            cmd_win.extend(["shell", "dumpsys", "window"])
            res_win = subprocess.run(cmd_win, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
            if "mKeyguardShowing=false" in res_win.stdout and "isStatusBarKeyguard=false" in res_win.stdout:
                return {
                    "status": "ready",
                    "screen_on": True,
                    "locked": False,
                    "message": "Layar ponsel berhasil dibuka (kunci geser/swipe).",
                }
        except Exception:
            pass

        if target_pin:
            self.input_interact("text", text=target_pin, device_id=device_id)
            time.sleep(0.3)
            self.input_interact("enter", device_id=device_id)
            time.sleep(0.5)

            try:
                cmd_win = self._build_base_cmd(device_id)
                cmd_win.extend(["shell", "dumpsys", "window"])
                res_win = subprocess.run(cmd_win, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
                if "mKeyguardShowing=false" in res_win.stdout:
                    return {
                        "status": "ready",
                        "screen_on": True,
                        "locked": False,
                        "message": "Layar ponsel berhasil dibuka menggunakan PIN.",
                    }
            except Exception:
                pass

        return {
            "status": "locked",
            "screen_on": True,
            "locked": True,
            "requires_pin": True,
            "action_required": "manual_unlock",
            "message": (
                "Layar ponsel telah dinyalakan, namun saat ini terkunci PIN/Password. "
                "Silakan buka kunci di HP Anda secara manual atau sediakan PIN untuk melanjutkan."
            ),
        }

    def get_current_screen(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves the package name, activity class, and PID of the foreground window on device.
        """
        info = {
            "package_name": "",
            "activity_name": "",
            "component": "",
            "pid": None,
            "is_running": False,
        }
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "dumpsys", "window"])
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if "mCurrentFocus" in line or "mFocusedApp" in line:
                        m = re.search(r"([a-zA-Z0-9_\.]+)/([a-zA-Z0-9_\.]+)", line)
                        if m:
                            info["package_name"] = m.group(1)
                            info["activity_name"] = m.group(2)
                            info["component"] = f"{info['package_name']}/{info['activity_name']}"
                            break
        except Exception:
            pass

        if info["package_name"]:
            cmd_pid = self._build_base_cmd(device_id)
            cmd_pid.extend(["shell", "pidof", info["package_name"]])
            try:
                res_pid = subprocess.run(cmd_pid, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4, check=False)
                if res_pid.returncode == 0 and res_pid.stdout.strip():
                    parts = res_pid.stdout.strip().split()
                    if parts:
                        info["pid"] = int(parts[0])
                        info["is_running"] = True
            except Exception:
                pass

        return info

    def get_app_logs(
        self,
        package_name: str,
        tail: int = 80,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Captures targeted logcat error output, stacktraces, and crashes for a specific application.
        """
        pid = None
        cmd_pid = self._build_base_cmd(device_id)
        cmd_pid.extend(["shell", "pidof", package_name])
        try:
            res_pid = subprocess.run(cmd_pid, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4, check=False)
            if res_pid.returncode == 0 and res_pid.stdout.strip():
                parts = res_pid.stdout.strip().split()
                if parts:
                    pid = parts[0]
        except Exception:
            pass

        cmd = self._build_base_cmd(device_id)
        cmd.extend(["logcat", "-d"])
        if pid:
            cmd.extend(["--pid", str(pid)])
        cmd.extend([
            "-s",
            "flutter:V",
            "ReactNative:V",
            "ReactNativeJS:V",
            "AndroidRuntime:E",
            "CRASH:E",
            "DEBUG:E",
            "System.err:W",
            "*:E",
        ])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8, check=False)
            lines = res.stdout.strip().splitlines()
            selected = lines[-tail:] if len(lines) > tail else lines
            has_crash = any("FATAL EXCEPTION" in l or "AndroidRuntime" in l or "Exception" in l for l in selected)
            return {
                "package_name": package_name,
                "pid": int(pid) if pid else None,
                "scope": "app" if pid else "global (aplikasi belum berjalan atau PID tidak ditemukan)",
                "has_crash_indicator": has_crash,
                "total_lines": len(selected),
                "logs": "\n".join(selected) if selected else "(Tidak ada error logcat terdeteksi)",
            }
        except Exception as e:
            return {
                "package_name": package_name,
                "pid": None,
                "scope": "unknown",
                "has_crash_indicator": False,
                "total_lines": 0,
                "logs": f"Gagal mengambil logcat: {e}",
            }

    def reset_app_data(self, package_name: str, device_id: Optional[str] = None) -> bool:
        """
        Instantly clears all data, databases, preferences, and cache for an app (pm clear).
        Allows testing fresh-install state in 0.5s without re-installing.
        """
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "pm", "clear", package_name])
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=6, check=False)
            return res.returncode == 0 and "success" in res.stdout.lower()
        except Exception:
            return False

    def open_deep_link(self, url: str, device_id: Optional[str] = None) -> bool:
        """
        Triggers an Android Intent VIEW for a deep link / URL route directly.
        """
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "am", "start", "-W", "-a", "android.intent.action.VIEW", "-d", url])
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8, check=False)
            return res.returncode == 0 and "error" not in res.stdout.lower()
        except Exception:
            return False

    def toggle_night_mode(self, enable: bool = True, device_id: Optional[str] = None) -> bool:
        """
        Toggles system dark mode (yes/no) to verify app UI adaptability across themes.
        """
        cmd = self._build_base_cmd(device_id)
        mode = "yes" if enable else "no"
        cmd.extend(["shell", "cmd", "uimode", "night", mode])
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
            return res.returncode == 0
        except Exception:
            return False

    def install_apk(
        self,
        apk_path: Union[str, Path],
        reinstall: bool = True,
        grant_permissions: bool = True,
        allow_downgrade: bool = True,
        device_id: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Installs an APK or Split-APK (.apks) file to the target Android device via ADB.
        Supports reinstall (-r), permission grant (-g), and downgrade (-d).
        Automatically uses 'adb install-multiple' when installing .apks bundles.
        Returns (success, code, details).
        """
        p = Path(apk_path).resolve()
        if not p.is_file():
            return (
                False,
                "FILE_NOT_FOUND",
                {
                    "status": "error",
                    "code": "FILE_NOT_FOUND",
                    "message": f"File APK '{apk_path}' tidak ditemukan di komputer.",
                    "apk_path": str(p),
                },
            )

        if p.suffix.lower() not in [".apk", ".apks"]:
            return (
                False,
                "INVALID_FILE_TYPE",
                {
                    "status": "error",
                    "code": "INVALID_FILE_TYPE",
                    "message": f"Berkas '{p.name}' bukan berkas APK Android (.apk atau .apks).",
                    "apk_path": str(p),
                },
            )

        is_split = p.suffix.lower() == ".apks"
        temp_dir_obj: Optional[tempfile.TemporaryDirectory] = None
        apk_files: List[str] = []

        if is_split:
            temp_dir_obj = tempfile.TemporaryDirectory()
            temp_dir = Path(temp_dir_obj.name)
            try:
                with zipfile.ZipFile(p, "r") as zf:
                    zf.extractall(temp_dir)
                extracted_apks = list(temp_dir.glob("*.apk"))
                if not extracted_apks:
                    temp_dir_obj.cleanup()
                    return (
                        False,
                        "INVALID_APKS_ARCHIVE",
                        {
                            "status": "error",
                            "code": "INVALID_APKS_ARCHIVE",
                            "message": f"Berkas .apks '{p.name}' tidak memuat berkas .apk di dalamnya.",
                            "apk_path": str(p),
                        },
                    )

                def apk_sort_key(f: Path) -> int:
                    name = f.name.lower()
                    if name == "base.apk":
                        return 0
                    if name.startswith("base"):
                        return 1
                    return 2

                extracted_apks.sort(key=apk_sort_key)
                apk_files = [str(f) for f in extracted_apks]
            except Exception as e:
                if temp_dir_obj:
                    temp_dir_obj.cleanup()
                return (
                    False,
                    "CORRUPTED_ARCHIVE",
                    {
                        "status": "error",
                        "code": "CORRUPTED_ARCHIVE",
                        "message": f"Gagal mengekstrak berkas .apks: {str(e)}",
                        "apk_path": str(p),
                    },
                )
        else:
            apk_files = [str(p)]

        cmd = self._build_base_cmd(device_id)
        if is_split:
            cmd.append("install-multiple")
        else:
            cmd.append("install")

        if reinstall:
            cmd.append("-r")
        if allow_downgrade:
            cmd.append("-d")
        if grant_permissions:
            cmd.append("-g")
        cmd.extend(apk_files)

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180,
                check=False,
            )
            out = (res.stdout + " " + res.stderr).strip()

            if res.returncode == 0 and "Success" in res.stdout:
                return (
                    True,
                    "SUCCESS",
                    {
                        "status": "success",
                        "code": "SUCCESS",
                        "apk_path": str(p),
                        "is_split": is_split,
                        "total_parts": len(apk_files),
                        "file_size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                        "message": f"Aplikasi dari '{p.name}' berhasil dipasang ke perangkat{' (Split-APKs)' if is_split else ''}.",
                    },
                )

            # Analyze error patterns
            if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out:
                return (
                    False,
                    "UPDATE_INCOMPATIBLE",
                    {
                        "status": "error",
                        "code": "UPDATE_INCOMPATIBLE",
                        "message": "Gagal memasang APK karena signature/keystore berbeda dengan versi yang sudah terpasang.",
                        "suggestion": "Hapus aplikasi versi sebelumnya terlebih dahulu menggunakan tool apkx_uninstall_app.",
                        "raw_output": out,
                    },
                )

            if "INSTALL_FAILED_VERSION_DOWNGRADE" in out:
                return (
                    False,
                    "VERSION_DOWNGRADE",
                    {
                        "status": "error",
                        "code": "VERSION_DOWNGRADE",
                        "message": "Gagal memasang APK karena versionCode lebih rendah dari yang terpasang di HP.",
                        "suggestion": "Hapus aplikasi versi lama terlebih dahulu menggunakan tool apkx_uninstall_app.",
                        "raw_output": out,
                    },
                )

            if "INSTALL_FAILED_INSUFFICIENT_STORAGE" in out:
                return (
                    False,
                    "INSUFFICIENT_STORAGE",
                    {
                        "status": "error",
                        "code": "INSUFFICIENT_STORAGE",
                        "message": "Gagal memasang APK karena kapasitas penyimpanan HP tidak mencukupi.",
                        "suggestion": "Kosongkan ruang memori pada perangkat Android Anda.",
                        "raw_output": out,
                    },
                )

            return (
                False,
                "INSTALL_FAILED",
                {
                    "status": "error",
                    "code": "INSTALL_FAILED",
                    "message": f"Gagal memasang APK ke perangkat: {out}",
                    "raw_output": out,
                },
            )

        except subprocess.TimeoutExpired:
            return (
                False,
                "TIMEOUT",
                {
                    "status": "error",
                    "code": "TIMEOUT",
                    "message": "Proses instalasi APK ke perangkat melebihi batas waktu (timeout 180 detik).",
                },
            )
        except Exception as e:
            return (
                False,
                "EXECUTION_ERROR",
                {
                    "status": "error",
                    "code": "EXECUTION_ERROR",
                    "message": f"Terjadi kesalahan saat mengeksekusi adb install: {str(e)}",
                },
            )
        finally:
            if temp_dir_obj:
                try:
                    temp_dir_obj.cleanup()
                except Exception:
                    pass

    def uninstall_app(
        self,
        package_name: str,
        keep_data: bool = False,
        device_id: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Uninstalls an application package from the target Android device via ADB.
        Returns (success, code, details).
        """
        pkg_clean = package_name.strip()
        if not pkg_clean:
            return (
                False,
                "INVALID_PACKAGE",
                {"status": "error", "code": "INVALID_PACKAGE", "message": "Nama package tidak boleh kosong."},
            )

        cmd = self._build_base_cmd(device_id)
        cmd.append("uninstall")
        if keep_data:
            cmd.append("-k")
        cmd.append(pkg_clean)

        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
                check=False,
            )
            out = (res.stdout + " " + res.stderr).strip()

            if res.returncode == 0 and "Success" in res.stdout:
                return (
                    True,
                    "SUCCESS",
                    {
                        "status": "success",
                        "code": "SUCCESS",
                        "package_name": pkg_clean,
                        "keep_data": keep_data,
                        "message": f"Aplikasi '{pkg_clean}' berhasil dihapus dari perangkat.",
                    },
                )

            return (
                False,
                "UNINSTALL_FAILED",
                {
                    "status": "error",
                    "code": "UNINSTALL_FAILED",
                    "package_name": pkg_clean,
                    "message": f"Gagal menghapus aplikasi '{pkg_clean}': {out}",
                    "raw_output": out,
                },
            )
        except Exception as e:
            return (
                False,
                "EXECUTION_ERROR",
                {
                    "status": "error",
                    "code": "EXECUTION_ERROR",
                    "package_name": pkg_clean,
                    "message": f"Terjadi kesalahan saat mengeksekusi adb uninstall: {str(e)}",
                },
            )
