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
                lines = [line.strip() for line in res.stdout.strip().splitlines() if line.strip()]
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
        query: Optional[str] = None,
    ) -> List[str]:
        """
        Lists installed package names on the target device.
        Supports case-insensitive query substring filter.
        """
        if query is not None:
            if not isinstance(query, str) or len(query) > 100 or not re.match(r"^[A-Za-z0-9_.]+$", query):
                raise ValueError("query filter tidak valid: harus alfanumerik (termasuk '_' dan '.') maksimal 100 karakter")

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

        if query:
            q_lower = query.lower()
            packages = [p for p in packages if q_lower in p.lower()]

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
        info: Dict[str, Any] = {
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
            "debuggable": None,
            "flags": [],
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
                flags_list: List[str] = []
                has_flags_line = False
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
                    if "flags=" in line_s or "pkgFlags=" in line_s:
                        has_flags_line = True
                        m_flags = re.search(r"(?:pkgFlags|flags)=\[([^\]]*)\]", line_s)
                        if m_flags:
                            for f in m_flags.group(1).split():
                                f_clean = f.strip()
                                if f_clean and f_clean not in flags_list:
                                    flags_list.append(f_clean)
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
                info["flags"] = flags_list
                if has_flags_line:
                    info["debuggable"] = "DEBUGGABLE" in flags_list
                else:
                    info["debuggable"] = None
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

    _dump_counter: int = 0

    def dump_ui_hierarchy_ex(
        self,
        retries: int = 2,
        retry_delay_ms: int = 500,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dumps UI hierarchy with retry support and distinguishable error states.
        Uses a unique remote dump filename per process/invocation to prevent race conditions.
        """
        import time
        import xml.etree.ElementTree as ET

        ADBManager._dump_counter += 1
        remote_file = f"/sdcard/apkx_window_dump_{os.getpid()}_{ADBManager._dump_counter}.xml"
        cmd_dump = self._build_base_cmd(device_id)
        cmd_dump.extend(["shell", "uiautomator", "dump", remote_file])

        last_error: Optional[str] = None
        dump_success = False

        for attempt in range(max(1, retries + 1)):
            try:
                res = subprocess.run(
                    cmd_dump,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10,
                    check=False,
                )
                if res.returncode == 0:
                    dump_success = True
                    break
                last_error = res.stderr.strip() or res.stdout.strip() or "uiautomator dump failed"
            except Exception as e:
                last_error = str(e)

            if attempt < retries:
                time.sleep(retry_delay_ms / 1000.0)

        if not dump_success:
            return {
                "elements": [],
                "screen_width": 0,
                "screen_height": 0,
                "error": last_error or "could not get idle state",
            }

        cmd_cat = self._build_base_cmd(device_id)
        cmd_cat.extend(["exec-out", "cat", remote_file])
        cat_res = subprocess.run(cmd_cat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8, check=False)

        cmd_rm = self._build_base_cmd(device_id)
        cmd_rm.extend(["shell", "rm", "-f", remote_file])
        subprocess.run(cmd_rm, timeout=4, check=False)

        xml_data = cat_res.stdout
        if not xml_data or "<hierarchy" not in xml_data:
            return {
                "elements": [],
                "screen_width": 0,
                "screen_height": 0,
                "error": "Hierarki UI kosong atau format tidak valid",
            }

        try:
            root = ET.fromstring(xml_data)
        except Exception as e:
            return {
                "elements": [],
                "screen_width": 0,
                "screen_height": 0,
                "error": f"Gagal mem-parse XML hierarki: {e}",
            }

        elements: List[Dict[str, Any]] = []
        max_w = 0
        max_h = 0

        for node in root.iter("node"):
            bounds_str = node.attrib.get("bounds", "")
            m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
            if not m:
                continue

            x1, y1, x2, y2 = map(int, m.groups())
            max_w = max(max_w, x2)
            max_h = max(max_h, y2)
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

        sw, sh = self.get_screen_size(device_id)
        if sw <= 0:
            sw = max_w
        if sh <= 0:
            sh = max_h

        return {
            "elements": elements,
            "screen_width": sw,
            "screen_height": sh,
            "error": None,
        }

    def find_ui_element(
        self,
        query: str,
        search_by: str = "text",
        match_mode: str = "contains",
        case_sensitive: bool = False,
        max_results: int = 20,
        include_disabled: bool = True,
        clickable_only: bool = False,
        retries: int = 2,
        retry_delay_ms: int = 500,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Searches UI hierarchy for matching elements by text, resource_id, content_desc, or class.
        Returns coordinates and bounding boxes without returning raw bloated XML.
        """
        if not query or not isinstance(query, str) or len(query) > 200:
            raise ValueError("query harus berupa string 1-200 karakter.")
        valid_search_by = {"text", "resource_id", "content_desc", "class", "any"}
        if search_by not in valid_search_by:
            raise ValueError(f"search_by '{search_by}' tidak valid. Pilihan: {', '.join(sorted(valid_search_by))}")
        if match_mode not in ("contains", "exact"):
            raise ValueError(f"match_mode '{match_mode}' tidak valid. Pilihan: contains, exact")
        if max_results < 1 or max_results > 100:
            raise ValueError("max_results harus antara 1 dan 100.")
        if retries < 0 or retries > 3:
            raise ValueError("retries harus antara 0 dan 3.")
        if retry_delay_ms < 0 or retry_delay_ms > 2000:
            raise ValueError("retry_delay_ms harus antara 0 dan 2000 ms.")

        dump = self.dump_ui_hierarchy_ex(retries=retries, retry_delay_ms=retry_delay_ms, device_id=device_id)
        if dump.get("error") is not None:
            return {
                "status": "error",
                "code": "UI_DUMP_FAILED",
                "query": query,
                "match_count": 0,
                "matches": [],
                "error": dump["error"],
                "message": "Gagal membaca hierarki UI.",
            }

        elements = dump.get("elements", [])
        matched: List[Dict[str, Any]] = []
        q_cmp = query if case_sensitive else query.lower()

        for el in elements:
            if not include_disabled and not el.get("enabled", True):
                continue
            if clickable_only and not el.get("clickable", False):
                continue

            match_field: Optional[str] = None

            def test_match(val: str, is_resource_id: bool = False) -> bool:
                target_str = val if case_sensitive else val.lower()
                if is_resource_id:
                    if "/" in query:
                        return target_str == q_cmp if match_mode == "exact" else q_cmp in target_str
                    if query.startswith(":id/"):
                        return target_str.endswith(q_cmp)
                    return target_str == q_cmp or target_str.endswith(":id/" + q_cmp) or (":id/" + q_cmp) in target_str

                if match_mode == "exact":
                    return target_str == q_cmp
                else:
                    return q_cmp in target_str

            if search_by == "text":
                if test_match(el.get("text", "")):
                    match_field = "text"
            elif search_by == "resource_id":
                if test_match(el.get("resource_id", ""), is_resource_id=True):
                    match_field = "resource_id"
            elif search_by == "content_desc":
                if test_match(el.get("content_desc", "")):
                    match_field = "content_desc"
            elif search_by == "class":
                if test_match(el.get("class", "")):
                    match_field = "class"
            elif search_by == "any":
                if test_match(el.get("text", "")):
                    match_field = "text"
                elif test_match(el.get("resource_id", ""), is_resource_id=True):
                    match_field = "resource_id"
                elif test_match(el.get("content_desc", "")):
                    match_field = "content_desc"
                elif test_match(el.get("class", "")):
                    match_field = "class"

            if match_field:
                el_copy = dict(el)
                el_copy["match_field"] = match_field
                matched.append(el_copy)

        if not matched:
            return {
                "status": "error",
                "code": "NOT_FOUND",
                "query": query,
                "match_count": 0,
                "matches": [],
                "message": "Tidak ada elemen yang cocok.",
            }

        total_matched = len(matched)
        result_matches = matched[:max_results]
        return {
            "status": "success",
            "code": "OK",
            "query": query,
            "search_by": search_by,
            "match_mode": match_mode,
            "match_count": len(result_matches),
            "truncated": total_matched > max_results,
            "screen_width": dump.get("screen_width", 0),
            "screen_height": dump.get("screen_height", 0),
            "matches": result_matches,
            "untrusted_content": True,
            "message": f"Ditemukan {len(result_matches)} elemen.",
        }

    def _send_shell_text(
        self,
        text: str,
        device_id: Optional[str] = None,
        timeout: int = 8,
    ) -> bool:
        escaped = text.replace("\\", "\\\\")
        for ch in (
            '"', "'", "&", "|", ";", "$", "`", "<", ">",
            "(", ")", "*", "?", "[", "]", "{", "}", "~", "#", "!",
        ):
            escaped = escaped.replace(ch, f"\\{ch}")

        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "input", "text", escaped])

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
            return proc.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def _send_keyevent(
        self,
        keycode: int,
        device_id: Optional[str] = None,
        timeout: int = 5,
    ) -> bool:
        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "input", "keyevent", str(keycode)])

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                check=False,
            )
            return proc.returncode == 0
        except (subprocess.SubprocessError, OSError):
            return False

    def _send_text_with_literal_percent_s(
        self,
        line: str,
        device_id: Optional[str] = None,
    ) -> bool:
        chunks = line.split("%s")
        ok = True

        for idx, chunk in enumerate(chunks):
            if chunk:
                if not self._send_shell_text(
                    chunk.replace(" ", "%s"),
                    device_id,
                ):
                    ok = False

            if idx < len(chunks) - 1:
                if not self._send_shell_text("%", device_id):
                    ok = False
                if not self._send_shell_text("s", device_id):
                    ok = False

        return ok

    def input_interact(
        self,
        action: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        keycode: Optional[int] = None,
        text: Optional[str] = None,
        swipe_coords: Optional[Tuple[int, ...]] = None,
        duration_ms: Optional[int] = None,
        count: Optional[int] = None,
        device_id: Optional[str] = None,
    ) -> bool:
        """
        Executes simulated UI actions: tap, back, home, enter, keyevent, text, swipe,
        long_press, backspace, or recent_apps.
        """
        if x is not None or y is not None:
            if x is not None and x < 0:
                return False
            if y is not None and y < 0:
                return False

            w, h = self.get_screen_size(device_id)
            if w > 0 and x is not None and x >= w:
                return False
            if h > 0 and y is not None and y >= h:
                return False

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
        elif act_clean == "recent_apps":
            cmd.extend(["input", "keyevent", "187"])
        elif act_clean == "backspace":
            c = count if count is not None else 1
            if c < 1 or c > 50:
                return False
            for _ in range(c):
                if not self._send_keyevent(67, device_id):
                    return False
            return True
        elif act_clean == "long_press":
            if x is None or y is None:
                return False
            dur = duration_ms if duration_ms is not None else 1000
            if dur < 200 or dur > 5000:
                return False
            cmd.extend(["input", "swipe", str(x), str(y), str(x), str(y), str(dur)])
        elif act_clean == "keyevent":
            if keycode is None:
                return False
            cmd.extend(["input", "keyevent", str(keycode)])
        elif act_clean == "text":
            if text is None:
                return False

            normalized = text.replace("\r\n", "\n").replace("\r", "\n")
            lines = normalized.split("\n")
            success = True

            for i, line in enumerate(lines):
                if line:
                    if "%s" in line:
                        if not self._send_text_with_literal_percent_s(
                            line,
                            device_id,
                        ):
                            success = False
                    else:
                        if not self._send_shell_text(
                            line.replace(" ", "%s"),
                            device_id,
                        ):
                            success = False

                if i < len(lines) - 1:
                    if not self._send_keyevent(66, device_id):
                        success = False

            return success
        elif act_clean == "swipe":
            if not swipe_coords or len(swipe_coords) < 4:
                return False
            x1, y1, x2, y2 = swipe_coords[:4]
            if x1 < 0 or y1 < 0 or x2 < 0 or y2 < 0:
                return False
            w_s, h_s = self.get_screen_size(device_id)
            if w_s > 0 and (x1 >= w_s or x2 >= w_s):
                return False
            if h_s > 0 and (y1 >= h_s or y2 >= h_s):
                return False
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

    def get_screen_state(
        self,
        expected_package: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves the package name, activity class, focus status, and overlay details
        of the current screen on device.
        """
        OVERLAY_PACKAGES = {
            "com.android.vending": "play_protect",
            "com.google.android.gms": "gms",
            "com.android.permissioncontroller": "permission",
            "com.google.android.permissioncontroller": "permission",
            "android": "crash",
            "com.android.systemui": "systemui",
            "com.google.android.inputmethod.latin": "keyboard",
            "com.android.inputmethod.latin": "keyboard",
        }

        info: Dict[str, Any] = {
            "status": "success",
            "code": "OK",
            "package_name": "",
            "activity_name": "",
            "component": "",
            "focused_package": None,
            "focused_component": None,
            "resumed_package": None,
            "resumed_component": None,
            "overlay_package": None,
            "overlay_type": "none",
            "is_overlay_active": False,
            "expected_package": expected_package,
            "is_target_foreground": None,
            "pid": None,
            "is_running": False,
            "target_pid": None,
            "target_running": None,
            "message": "Layar aktif berhasil dibaca.",
        }

        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "dumpsys", "window"])
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
            if res.returncode == 0:
                for line in res.stdout.splitlines():
                    if "mCurrentFocus" in line or "mFocusedApp" in line:
                        m = re.findall(r"([a-zA-Z0-9_\.]+)/([a-zA-Z0-9_\.$]+)", line)
                        if m:
                            pkg_name, act_name = m[-1]
                            info["package_name"] = pkg_name
                            info["activity_name"] = act_name
                            info["component"] = f"{pkg_name}/{act_name}"
                            info["focused_package"] = pkg_name
                            info["focused_component"] = f"{pkg_name}/{act_name}"
        except Exception:
            pass

        cmd_act = self._build_base_cmd(device_id)
        cmd_act.extend(["shell", "dumpsys", "activity", "activities"])
        try:
            res_act = subprocess.run(cmd_act, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
            if res_act.returncode == 0:
                for line in res_act.stdout.splitlines():
                    if "mResumedActivity" in line or "topResumedActivity" in line:
                        m = re.findall(r"([a-zA-Z0-9_\.]+)/([a-zA-Z0-9_\.$]+)", line)
                        if m:
                            r_pkg, r_act = m[-1]
                            info["resumed_package"] = r_pkg
                            info["resumed_component"] = f"{r_pkg}/{r_act}"
        except Exception:
            pass

        focused_pkg = info.get("focused_package")
        if focused_pkg:
            overlay_type = OVERLAY_PACKAGES.get(focused_pkg, "none")
            info["overlay_type"] = overlay_type
            if overlay_type in {"play_protect", "gms", "permission", "crash", "systemui"}:
                info["is_overlay_active"] = True
                info["overlay_package"] = focused_pkg
            else:
                info["is_overlay_active"] = False
                info["overlay_package"] = None

            cmd_pid = self._build_base_cmd(device_id)
            cmd_pid.extend(["shell", "pidof", focused_pkg])
            try:
                res_pid = subprocess.run(cmd_pid, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4, check=False)
                if res_pid.returncode == 0 and res_pid.stdout.strip():
                    parts = res_pid.stdout.strip().split()
                    if parts and parts[0].isdigit():
                        info["pid"] = int(parts[0])
                        info["is_running"] = True
            except Exception:
                pass

        if expected_package:
            info["is_target_foreground"] = (focused_pkg == expected_package) and not info["is_overlay_active"]
            cmd_tpid = self._build_base_cmd(device_id)
            cmd_tpid.extend(["shell", "pidof", expected_package])
            try:
                res_tpid = subprocess.run(cmd_tpid, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4, check=False)
                if res_tpid.returncode == 0 and res_tpid.stdout.strip():
                    parts = res_tpid.stdout.strip().split()
                    if parts and parts[0].isdigit():
                        info["target_pid"] = int(parts[0])
                        info["target_running"] = True
                    else:
                        info["target_pid"] = None
                        info["target_running"] = False
                else:
                    info["target_pid"] = None
                    info["target_running"] = False
            except Exception:
                info["target_pid"] = None
                info["target_running"] = False

        return info

    def get_current_screen(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves the package name, activity class, and PID of the foreground window on device.
        Backward-compatible wrapper around get_screen_state().
        """
        return self.get_screen_state(expected_package=None, device_id=device_id)

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
            has_crash = any("FATAL EXCEPTION" in line or "AndroidRuntime" in line or "Exception" in line for line in selected)
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
        grant_permissions: bool = False,
        allow_downgrade: bool = False,
        verify: bool = True,
        device_id: Optional[str] = None,
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Installs an APK or Split-APK (.apks) file to the target Android device via ADB.
        Supports reinstall (-r), permission grant (-g), and downgrade (-d).
        Automatically uses 'adb install-multiple' when installing .apks bundles.
        Parses APK metadata and enriches response with package info and verification.
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

        # Pre-read metadata
        apk_meta = self.get_apk_metadata(p)
        pkg_name = apk_meta.get("package_name")

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
                v_info: Dict[str, Any] = {}
                verification = "unavailable"
                if verify and pkg_name:
                    try:
                        v_info = self.verify_installed_package(pkg_name, expect_release=None, device_id=device_id)
                        if v_info.get("status") == "success":
                            verification = "verified"
                    except Exception:
                        pass

                version_name = v_info.get("version_name") or apk_meta.get("version_name")
                version_code = v_info.get("version_code") or apk_meta.get("version_code")
                debuggable = v_info.get("debuggable") if "debuggable" in v_info else apk_meta.get("debuggable")

                success_detail = {
                    "status": "success",
                    "code": "OK",
                    "apk_path": str(p),
                    "package_name": pkg_name,
                    "version_name": version_name,
                    "version_code": version_code,
                    "debuggable": debuggable,
                    "is_split": is_split,
                    "total_parts": len(apk_files),
                    "file_size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                    "verification": verification,
                    "message": f"Aplikasi '{pkg_name or p.name}' berhasil dipasang ke perangkat{' (Split-APKs)' if is_split else ''}.",
                }
                return (
                    True,
                    "SUCCESS",
                    success_detail,
                )

            # Analyze error patterns
            if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in out:
                return (
                    False,
                    "UPDATE_INCOMPATIBLE",
                    {
                        "status": "error",
                        "code": "UPDATE_INCOMPATIBLE",
                        "package_name": pkg_name,
                        "message": "Gagal memasang APK karena signature/keystore berbeda dengan versi yang sudah terpasang.",
                        "suggested_action": "uninstall_then_install",
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

    def get_apk_metadata(self, apk_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Parses package_name, version_name, version_code, and debuggable flag from an APK/APKS.
        """
        from apk_extractor.axml import decode_axml

        p = Path(apk_path).resolve()
        res: Dict[str, Any] = {
            "package_name": None,
            "version_name": None,
            "version_code": None,
            "debuggable": None,
            "manifest_found": False,
        }
        if not p.is_file():
            return res

        manifest_bytes: Optional[bytes] = None
        try:
            with zipfile.ZipFile(p, "r") as zf:
                if "AndroidManifest.xml" in zf.namelist():
                    manifest_bytes = zf.read("AndroidManifest.xml")
                else:
                    # Could be .apks bundle
                    for name in zf.namelist():
                        if name.endswith(".apk") and ("base" in name.lower() or not manifest_bytes):
                            try:
                                sub_bytes = zf.read(name)
                                import io
                                with zipfile.ZipFile(io.BytesIO(sub_bytes), "r") as sub_zf:
                                    if "AndroidManifest.xml" in sub_zf.namelist():
                                        manifest_bytes = sub_zf.read("AndroidManifest.xml")
                                        if "base" in name.lower():
                                            break
                            except Exception:
                                pass
        except Exception:
            return res

        if not manifest_bytes:
            return res

        try:
            xml_text = decode_axml(manifest_bytes)
            if not xml_text:
                return res

            res["manifest_found"] = True

            m_pkg = re.search(r'package="([^"]+)"', xml_text)
            if m_pkg:
                res["package_name"] = m_pkg.group(1)

            m_vn = re.search(r'android:versionName="([^"]+)"', xml_text)
            if m_vn:
                res["version_name"] = m_vn.group(1)

            m_vc = re.search(r'android:versionCode="([^"]+)"', xml_text)
            if m_vc:
                res["version_code"] = m_vc.group(1)

            m_dbg = re.search(r'android:debuggable="(true|false)"', xml_text)
            if m_dbg:
                res["debuggable"] = m_dbg.group(1).lower() == "true"
        except Exception:
            pass

        return res

    def verify_installed_package(
        self,
        package_name: str,
        expect_release: Optional[bool] = True,
        expected_version_name: Optional[str] = None,
        expected_version_code: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Validates package installation, versionCode, versionName, and DEBUGGABLE flag.
        Fails closed (verified=False) if flags are unknown.
        """
        if not re.match(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$", package_name):
            raise ValueError(f"Nama package '{package_name}' tidak valid.")

        paths = self.get_package_apk_paths(package_name, device_id=device_id)
        if not paths:
            return {
                "status": "error",
                "code": "PACKAGE_NOT_FOUND",
                "verified": False,
                "package_name": package_name,
                "version_name": None,
                "version_code": None,
                "debuggable": None,
                "message": f"Package '{package_name}' tidak terpasang di perangkat.",
            }

        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "dumpsys", "package", package_name])
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10, check=False)
        if res.returncode != 0:
            return {
                "status": "error",
                "code": "ADB_ERROR",
                "verified": False,
                "package_name": package_name,
                "version_name": None,
                "version_code": None,
                "debuggable": None,
                "message": f"Gagal membaca dumpsys package: {res.stderr.strip()}",
            }

        version_name: Optional[str] = None
        version_code: Optional[str] = None
        flags_list: List[str] = []
        has_flags_line = False
        first_install_time: Optional[str] = None
        last_update_time: Optional[str] = None
        code_path: Optional[str] = None

        for line in res.stdout.splitlines():
            line_s = line.strip()
            if "versionName=" in line_s and version_name is None:
                m = re.search(r"versionName=([^\s]+)", line_s)
                if m:
                    version_name = m.group(1)
            if "versionCode=" in line_s and version_code is None:
                m = re.search(r"versionCode=([0-9]+)", line_s)
                if m:
                    version_code = m.group(1)
            if "flags=" in line_s or "pkgFlags=" in line_s:
                has_flags_line = True
                m_flags = re.search(r"(?:pkgFlags|flags)=\[([^\]]*)\]", line_s)
                if m_flags:
                    for f in m_flags.group(1).split():
                        f_clean = f.strip()
                        if f_clean and f_clean not in flags_list:
                            flags_list.append(f_clean)
            if "firstInstallTime=" in line_s and first_install_time is None:
                first_install_time = line_s.replace("firstInstallTime=", "").strip()
            if "lastUpdateTime=" in line_s and last_update_time is None:
                last_update_time = line_s.replace("lastUpdateTime=", "").strip()
            if "codePath=" in line_s and code_path is None:
                code_path = line_s.replace("codePath=", "").strip()

        debuggable: Optional[bool] = None
        if has_flags_line:
            debuggable = "DEBUGGABLE" in flags_list

        base_res: Dict[str, Any] = {
            "package_name": package_name,
            "version_name": version_name,
            "version_code": version_code,
            "debuggable": debuggable,
            "flags": flags_list,
            "first_install_time": first_install_time,
            "last_update_time": last_update_time,
            "code_path": code_path,
            "expected": {
                "release": expect_release,
                "version_name": expected_version_name,
                "version_code": expected_version_code,
            },
        }

        if debuggable is None:
            base_res.update({
                "status": "error",
                "code": "UNKNOWN",
                "verified": False,
                "message": "Tidak dapat menentukan status debuggable dari package flags.",
            })
            return base_res

        if expect_release is True and debuggable is True:
            base_res.update({
                "status": "error",
                "code": "DEBUGGABLE_MISMATCH",
                "verified": False,
                "message": "APK terpasang masih debuggable; bukan release murni.",
            })
            return base_res

        if expect_release is False and debuggable is False:
            base_res.update({
                "status": "error",
                "code": "DEBUGGABLE_MISMATCH",
                "verified": False,
                "message": "APK terpasang adalah release; bukan debuggable seperti yang diharapkan.",
            })
            return base_res

        if expected_version_name is not None and version_name != expected_version_name:
            base_res.update({
                "status": "error",
                "code": "VERSION_MISMATCH",
                "verified": False,
                "message": f"Versi name '{version_name}' tidak sesuai dengan yang diharapkan '{expected_version_name}'.",
            })
            return base_res

        if expected_version_code is not None and version_code != expected_version_code:
            base_res.update({
                "status": "error",
                "code": "VERSION_MISMATCH",
                "verified": False,
                "message": f"Versi code '{version_code}' tidak sesuai dengan yang diharapkan '{expected_version_code}'.",
            })
            return base_res

        base_res.update({
            "status": "success",
            "code": "OK",
            "verified": True,
            "message": f"Instalasi terverifikasi sebagai {'RELEASE' if not debuggable else 'DEBUG'}.",
        })
        return base_res

    def grant_runtime_permission(
        self,
        package_name: str,
        permission: str,
        action: str = "grant",
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Dynamically grants or revokes a runtime permission on Android 6.0+ (API 23+).
        Validates manifest declaration before execution.
        """
        if not re.match(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$", package_name):
            raise ValueError(f"Nama package '{package_name}' tidak valid.")

        perm_norm = permission if "." in permission else f"android.permission.{permission.upper()}"
        if not re.match(r"^[A-Za-z0-9_.]+$", perm_norm):
            raise ValueError(f"Nama permission '{permission}' tidak valid.")

        if action not in ("grant", "revoke"):
            raise ValueError("action harus 'grant' atau 'revoke'.")

        paths = self.get_package_apk_paths(package_name, device_id=device_id)
        if not paths:
            return {
                "status": "error",
                "code": "PACKAGE_NOT_FOUND",
                "package_name": package_name,
                "permission": perm_norm,
                "message": f"Package '{package_name}' tidak terpasang di perangkat.",
            }

        cmd_info = self._build_base_cmd(device_id)
        cmd_info.extend(["shell", "dumpsys", "package", package_name])
        res_info = subprocess.run(cmd_info, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10, check=False)

        # Check API level
        api_level = 0
        cmd_api = self._build_base_cmd(device_id)
        cmd_api.extend(["shell", "getprop", "ro.build.version.sdk"])
        res_api = subprocess.run(cmd_api, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=False)
        if res_api.returncode == 0 and res_api.stdout.strip().isdigit():
            api_level = int(res_api.stdout.strip())

        if api_level > 0 and api_level < 23:
            return {
                "status": "error",
                "code": "UNSUPPORTED_OPERATION",
                "package_name": package_name,
                "permission": perm_norm,
                "api_level": api_level,
                "message": "Runtime permissions hanya didukung pada Android 6.0 (API 23) ke atas.",
            }

        special_perms = {
            "android.permission.SYSTEM_ALERT_WINDOW",
            "android.permission.WRITE_SETTINGS",
            "android.permission.PACKAGE_USAGE_STATS",
            "android.permission.MANAGE_EXTERNAL_STORAGE",
            "android.permission.ACCESS_NOTIFICATION_POLICY",
        }
        if perm_norm in special_perms:
            return {
                "status": "error",
                "code": "UNSUPPORTED_OPERATION",
                "package_name": package_name,
                "permission": perm_norm,
                "message": f"Izin khusus '{perm_norm}' tidak dapat diatur via pm grant/revoke; gunakan appops.",
            }

        # Check requested permissions
        if "requested permissions:" in res_info.stdout.lower():
            req_perms: List[str] = []
            in_req = False
            for line in res_info.stdout.splitlines():
                if "requested permissions:" in line.lower():
                    in_req = True
                    continue
                if in_req:
                    if line.startswith("    ") and not line.startswith("      "):
                        p = line.strip().split(":")[0].strip()
                        if p:
                            req_perms.append(p)
                    elif not line.startswith("    "):
                        in_req = False
            if perm_norm not in req_perms:
                return {
                    "status": "error",
                    "code": "PERMISSION_NOT_DECLARED",
                    "package_name": package_name,
                    "permission": perm_norm,
                    "declared": False,
                    "message": f"Izin '{perm_norm}' tidak dideklarasikan pada AndroidManifest.xml package '{package_name}'.",
                }

        cmd_pm = self._build_base_cmd(device_id)
        cmd_pm.extend(["shell", "pm", action, package_name, perm_norm])
        res_pm = subprocess.run(cmd_pm, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8, check=False)
        out = (res_pm.stdout + " " + res_pm.stderr).strip()

        if res_pm.returncode != 0 or any(err_word in out.lower() for err_word in ("error", "exception", "not a changeable permission type")):
            return {
                "status": "error",
                "code": "PERMISSION_DENIED",
                "package_name": package_name,
                "permission": perm_norm,
                "action": action,
                "message": f"Gagal mengubah izin '{perm_norm}': {out}",
            }

        return {
            "status": "success",
            "code": "OK",
            "package_name": package_name,
            "permission": perm_norm,
            "action": action,
            "granted": (action == "grant"),
            "revoked": (action == "revoke"),
            "declared": True,
            "api_level": api_level,
            "message": f"Izin '{perm_norm}' berhasil {'diberikan' if action == 'grant' else 'dicabut'}.",
        }

    def force_stop_app(
        self,
        package_name: str,
        allow_system: bool = False,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Force-stops an application package and verifies process termination.
        Applies system blocklist protections.
        """
        import time

        hard_block = {"android", "com.android.systemui", "com.android.phone", "com.android.settings"}
        if package_name in hard_block:
            return {
                "status": "error",
                "code": "PERMISSION_DENIED",
                "package_name": package_name,
                "message": f"Package '{package_name}' adalah komponen sistem inti dan dilarang untuk dihentikan paksa.",
            }

        soft_block = {"com.google.android.gms", "com.android.permissioncontroller", "com.google.android.permissioncontroller"}
        if package_name in soft_block and not allow_system:
            return {
                "status": "error",
                "code": "PERMISSION_DENIED",
                "package_name": package_name,
                "message": f"Package '{package_name}' adalah komponen sistem penting. Set allow_system=True jika benar-benar diperlukan.",
            }

        if not re.match(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$", package_name):
            raise ValueError(f"Nama package '{package_name}' tidak valid.")

        paths = self.get_package_apk_paths(package_name, device_id=device_id)
        if not paths:
            return {
                "status": "error",
                "code": "PACKAGE_NOT_FOUND",
                "package_name": package_name,
                "message": f"Aplikasi '{package_name}' tidak terpasang di perangkat.",
            }

        cmd = self._build_base_cmd(device_id)
        cmd.extend(["shell", "am", "force-stop", package_name])
        subprocess.run(cmd, timeout=10, check=False)

        time.sleep(0.3)

        pids: List[int] = []
        is_running = False
        for _ in range(3):
            cmd_pid = self._build_base_cmd(device_id)
            cmd_pid.extend(["shell", "pidof", package_name])
            res_pid = subprocess.run(cmd_pid, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=4, check=False)
            if res_pid.returncode == 0 and res_pid.stdout.strip():
                pids = [int(p) for p in res_pid.stdout.strip().split() if p.isdigit()]
                if pids:
                    is_running = True
                    time.sleep(0.2)
                    continue
            is_running = False
            pids = []
            break

        if is_running:
            return {
                "status": "error",
                "code": "FORCE_STOP_FAILED",
                "package_name": package_name,
                "is_running": True,
                "pids": pids,
                "verified": False,
                "message": f"Gagal menghentikan paksa '{package_name}', proses masih berjalan.",
            }

        res: Dict[str, Any] = {
            "status": "success",
            "code": "OK",
            "package_name": package_name,
            "is_running": False,
            "pids": [],
            "processes": [],
            "verified": True,
            "message": f"Aplikasi '{package_name}' berhasil dihentikan paksa.",
        }
        if package_name == "com.android.vending":
            res["warning"] = "Force-stop pada Play Store dapat memengaruhi unduhan lain."
        return res

    def diagnostics(
        self,
        action: str,
        target: Optional[str] = None,
        filter_text: Optional[str] = None,
        max_output_chars: int = 16_000,
        allow_truncate: bool = True,
        timeout: int = 15,
        device_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Executes strictly controlled, read-only diagnostic inspections on the connected device.
        Applies action allowlist, strict input regex validation, and output truncation caps.
        """
        import json

        ALLOWLIST = {
            "getprop",
            "wm_size",
            "wm_density",
            "pidof",
            "ps",
            "dumpsys_window_focus",
            "dumpsys_package_version",
        }
        if action not in ALLOWLIST:
            raise ValueError(
                f"Aksi diagnostik '{action}' tidak valid. Pilihan allowlist: {', '.join(sorted(ALLOWLIST))}"
            )

        if timeout < 1 or timeout > 60:
            raise ValueError("timeout harus antara 1 dan 60 detik.")

        if max_output_chars < 1_000 or max_output_chars > 64_000:
            raise ValueError("max_output_chars harus antara 1.000 dan 64.000 karakter.")

        forbidden = set("\n\r\t\\\"'`$;|&<>*?[](){}!#~")
        if target:
            if any(ch in forbidden for ch in target):
                raise ValueError("target mengandung karakter berbahaya atau karakter kontrol yang tidak diizinkan.")
        if filter_text:
            if any(ch in forbidden for ch in filter_text):
                raise ValueError("filter_text mengandung karakter berbahaya atau karakter kontrol yang tidak diizinkan.")
            if len(filter_text) > 120 or not re.match(r"^[A-Za-z0-9 _./:\-]+$", filter_text):
                raise ValueError("filter_text maksimal 120 karakter dan hanya boleh berisi alfanumerik serta spasi/simbol dasar.")

        if action == "getprop":
            if target and not re.match(r"^[A-Za-z0-9_.-]+$", target):
                raise ValueError(f"target getprop '{target}' tidak valid.")
        elif action == "pidof":
            if not target:
                raise ValueError("Target wajib untuk aksi 'pidof'.")
            if not re.match(r"^[A-Za-z0-9_.:]+$", target):
                raise ValueError(f"target pidof '{target}' tidak valid.")
        elif action == "dumpsys_package_version":
            if not target:
                raise ValueError("Target wajib untuk aksi 'dumpsys_package_version'.")
            if not re.match(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$", target):
                raise ValueError(f"target package '{target}' tidak valid.")

        result: Dict[str, Any] = {}

        if action == "getprop":
            cmd = self._build_base_cmd(device_id)
            cmd.extend(["shell", "getprop"])
            if target:
                cmd.append(target)
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)
            if target:
                result = {"properties": {target: res.stdout.strip()}}
            else:
                curated_keys = {
                    "ro.product.model",
                    "ro.product.brand",
                    "ro.build.version.sdk",
                    "ro.build.version.release",
                    "ro.build.characteristics",
                    "ro.debuggable",
                }
                props: Dict[str, str] = {}
                for line in res.stdout.splitlines():
                    m = re.match(r"\[([^\]]+)\]:\s*\[([^\]]*)\]", line)
                    if m:
                        k, v = m.group(1), m.group(2)
                        if k in curated_keys:
                            props[k] = v
                result = {"properties": props}

        elif action == "wm_size":
            cmd = self._build_base_cmd(device_id)
            cmd.extend(["shell", "wm", "size"])
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)
            phys: Optional[str] = None
            ovr: Optional[str] = None
            for line in res.stdout.splitlines():
                if "Physical size:" in line:
                    phys = line.replace("Physical size:", "").strip()
                elif "Override size:" in line:
                    ovr = line.replace("Override size:", "").strip()
            result = {"physical": phys, "override": ovr}

        elif action == "wm_density":
            cmd = self._build_base_cmd(device_id)
            cmd.extend(["shell", "wm", "density"])
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)
            phys_d: Optional[int] = None
            ovr_d: Optional[int] = None
            for line in res.stdout.splitlines():
                if "Physical density:" in line:
                    val = line.replace("Physical density:", "").strip()
                    if val.isdigit():
                        phys_d = int(val)
                elif "Override density:" in line:
                    val = line.replace("Override density:", "").strip()
                    if val.isdigit():
                        ovr_d = int(val)
            result = {"physical": phys_d, "override": ovr_d}

        elif action == "pidof":
            assert target is not None
            cmd = self._build_base_cmd(device_id)
            cmd.extend(["shell", "pidof", target])
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)
            pids = [int(p) for p in res.stdout.strip().split() if p.isdigit()]
            result = {"running": len(pids) > 0, "pids": pids}

        elif action == "ps":
            cmd = self._build_base_cmd(device_id)
            cmd.extend(["shell", "ps", "-A"])
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)
            lines = res.stdout.splitlines()
            processes: List[Dict[str, Any]] = []
            f_lower = filter_text.lower() if filter_text else None

            start_idx = 1 if lines and "USER" in lines[0] else 0
            for line in lines[start_idx:]:
                if f_lower and f_lower not in line.lower():
                    continue
                parts = line.split()
                if len(parts) >= 8:
                    user = parts[0]
                    pid_str = parts[1]
                    ppid_str = parts[2]
                    name = parts[-1]
                    processes.append({
                        "user": user,
                        "pid": int(pid_str) if pid_str.isdigit() else pid_str,
                        "ppid": int(ppid_str) if ppid_str.isdigit() else ppid_str,
                        "name": name,
                    })
                if len(processes) >= 200:
                    break
            result = {"count": len(processes), "processes": processes}

        elif action == "dumpsys_window_focus":
            cmd = self._build_base_cmd(device_id)
            cmd.extend(["shell", "dumpsys", "window"])
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, check=False)
            cur_focus: Optional[str] = None
            foc_app: Optional[str] = None
            resumed: Optional[str] = None
            for line in res.stdout.splitlines():
                if "mCurrentFocus" in line:
                    cur_focus = line.strip()
                elif "mFocusedApp" in line:
                    foc_app = line.strip()
                elif "mResumedActivity" in line:
                    resumed = line.strip()
            result = {
                "current_focus": cur_focus,
                "focused_app": foc_app,
                "resumed_activity": resumed,
            }

        elif action == "dumpsys_package_version":
            assert target is not None
            v_info = self.verify_installed_package(target, expect_release=None, device_id=device_id)
            result = {
                "package": {
                    "version_name": v_info.get("version_name"),
                    "version_code": v_info.get("version_code"),
                    "debuggable": v_info.get("debuggable"),
                    "flags": v_info.get("flags", []),
                    "code_path": v_info.get("code_path"),
                }
            }

        serialized = json.dumps(result)
        original_size = len(serialized)
        truncated = False

        if original_size > max_output_chars:
            if not allow_truncate:
                return {
                    "status": "error",
                    "code": "OUTPUT_TOO_LARGE",
                    "action": action,
                    "target": target,
                    "original_size": original_size,
                    "truncated": False,
                    "untrusted_content": True,
                    "message": f"Ukuran output ({original_size} karakter) melebihi batas max_output_chars ({max_output_chars}).",
                }
            truncated = True
            if action == "ps" and "processes" in result:
                while len(result["processes"]) > 1 and len(json.dumps(result)) > max_output_chars:
                    result["processes"].pop()
                result["count"] = len(result["processes"])

        return {
            "status": "success",
            "code": "OK",
            "action": action,
            "target": target,
            "result": result,
            "truncated": truncated,
            "original_size": original_size,
            "untrusted_content": True,
            "message": f"Diagnostik '{action}' berhasil.",
        }
