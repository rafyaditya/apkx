import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from apk_extractor.adb import ADBManager
from apk_extractor.app_names import extract_apk_label, save_to_app_cache
from apk_extractor.axml import decode_axml
from apk_extractor.dex import extract_class_skeleton_from_dir, format_skeleton_text
from apk_extractor.endpoints import extract_endpoints_from_dir
from apk_extractor.jadx import JADXManager

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def sanitize_archive_member_path(member_path: str) -> Path:
    """
    Sanitizes archive member paths to prevent Zip Slip and Windows reserved names (CON, PRN, AUX, etc.).
    """
    parts = []
    for part in Path(member_path).parts:
        if part in ("..", "/", "\\", ""):
            continue
        p_stem = Path(part).stem.upper()
        if p_stem in WINDOWS_RESERVED_NAMES:
            part = f"_{part}"
        parts.append(part)
    return Path(*parts) if parts else Path()


def safe_extract_zip(
    zf: zipfile.ZipFile,
    target_dir: Path,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    task_label: str = "Mengekstrak berkas",
) -> int:
    """
    Safely extracts all members from a ZipFile into target_dir.
    Guards against Zip Slip and Windows reserved device names (PRN, CON, AUX, etc.).
    Returns the total number of files extracted.
    """
    target_dir = target_dir.resolve()
    members = zf.infolist()
    total_members = len(members)
    extracted_count = 0

    for idx, member in enumerate(members, start=1):
        clean_rel_path = sanitize_archive_member_path(member.filename)
        if not clean_rel_path.parts:
            continue

        dest_path = (target_dir / clean_rel_path).resolve()
        try:
            dest_path.relative_to(target_dir)
        except ValueError:
            continue

        if progress_callback and (idx % 25 == 0 or idx == total_members):
            progress_callback(f"{task_label} ({idx}/{total_members}): {clean_rel_path.name}...", idx, total_members)

        if member.is_dir() or member.filename.endswith("/"):
            dest_path.mkdir(parents=True, exist_ok=True)
        else:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_str = str(dest_path)
            if sys.platform == "win32" and not dest_str.startswith("\\\\?\\"):
                dest_str = f"\\\\?\\{dest_str}"

            try:
                with zf.open(member) as src, open(dest_str, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            except Exception:
                with zf.open(member) as src, open(dest_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            extracted_count += 1

    return extracted_count


def sanitize_filename(name: str) -> str:
    """
    Membersihkan nama aplikasi agar aman digunakan sebagai nama file / folder di Windows & Linux.
    """
    clean = re.sub(r'[\\/*?:"<>|]', "", name).strip()
    clean = re.sub(r"\s+", "_", clean)
    return clean if clean else "app"


def extract_sqlite_schema_from_dir(target_dir: Path) -> Dict[str, Any]:
    """
    Scans binary files (libapp.so, other .so, .dex) in target_dir to detect
    embedded SQLite CREATE TABLE statements and column definitions.
    """
    if not target_dir.is_dir() and target_dir.is_file():
        scan_files = [target_dir]
    elif target_dir.is_dir():
        scan_files = [
            f for f in target_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in (".so", ".dex", ".db", ".sqlite", ".bin")
        ]
    else:
        return {"total_tables": 0, "tables": {}, "raw_statements": []}

    found_statements = set()
    tables: Dict[str, List[str]] = {}

    header_regex = re.compile(
        rb"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"'\[]?([a-zA-Z0-9_]+)[`\"'\]]?)\s*\(",
        re.IGNORECASE,
    )

    def _split_columns(body_text: str) -> List[str]:
        cols = []
        current_col = []
        paren_depth = 0
        for char in body_text:
            if char == "(":
                paren_depth += 1
                current_col.append(char)
            elif char == ")":
                if paren_depth > 0:
                    paren_depth -= 1
                current_col.append(char)
            elif char == "," and paren_depth == 0:
                col_str = "".join(current_col).strip()
                if col_str:
                    cols.append(" ".join(col_str.split()))
                current_col = []
            else:
                current_col.append(char)
        last_col = "".join(current_col).strip()
        if last_col:
            cols.append(" ".join(last_col.split()))
        return cols

    for f in scan_files:
        try:
            data = f.read_bytes()
            for match in header_regex.finditer(data):
                try:
                    tbl_raw = match.group(2) or match.group(1)
                    tbl_name = tbl_raw.decode("utf-8", errors="ignore").strip("`'\"[] ")

                    if not (1 < len(tbl_name) < 60):
                        continue

                    start_pos = match.end()
                    depth = 1
                    end_pos = -1
                    max_scan = min(len(data), start_pos + 4000)

                    for i in range(start_pos, max_scan):
                        b = data[i : i + 1]
                        if b == b"(":
                            depth += 1
                        elif b == b")":
                            depth -= 1
                            if depth == 0:
                                end_pos = i
                                break
                        elif b == b"\x00" and depth > 0:
                            # End of string or binary segment
                            break

                    if end_pos != -1:
                        body_bytes = data[start_pos:end_pos]
                        body_text = body_bytes.decode("utf-8", errors="ignore").strip()

                        if 2 < len(body_text) < 3500:
                            cols = []
                            for col in _split_columns(body_text):
                                clean_col = " ".join(col.split()).strip()
                                if clean_col and len(clean_col) < 200:
                                    cols.append(clean_col)

                            if cols and tbl_name.lower() not in ("room_master_table", "android_metadata"):
                                tables[tbl_name] = cols
                                found_statements.add(f"CREATE TABLE `{tbl_name}` (\n  " + ",\n  ".join(cols) + "\n);")
                except Exception:
                    pass
        except Exception:
            pass

    return {
        "total_tables": len(tables),
        "tables": tables,
        "raw_statements": sorted(list(found_statements)),
    }


@dataclass
class ExtractionResult:
    package_name: str
    app_name: str
    output_path: Path
    is_split: bool
    total_parts: int
    size_bytes: int
    extracted_folder: Optional[Path] = None
    framework_info: Optional[Dict[str, str]] = None

    @property
    def formatted_size(self) -> str:
        size = float(self.size_bytes)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


class APKPackager:
    """Handles pulling, packaging, unpacking, and analyzing APK files."""

    def __init__(self, adb: ADBManager, jadx: Optional[JADXManager] = None):
        self.adb = adb
        self.jadx = jadx or JADXManager()

    def extract(
        self,
        package_name: str,
        remote_paths: List[str],
        output_dir: Path,
        app_name: Optional[str] = None,
        device_id: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> ExtractionResult:
        """
        Extracts APK files from the device.
        - Files are named using the sanitized app_name (e.g. Easybudget.apks, WhatsApp.apk)
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        total_parts = len(remote_paths)

        if total_parts == 0:
            raise ValueError(f"Tidak ada file APK yang ditemukan untuk package '{package_name}'.")

        display_name = app_name or package_name
        file_base_name = sanitize_filename(display_name)

        if total_parts == 1:
            # Single APK
            remote_path = remote_paths[0]
            dest_file = output_dir / f"{file_base_name}.apk"

            if progress_callback:
                progress_callback(f"Menarik {remote_path.split('/')[-1]}...", 1, 1)

            self.adb.pull_file(remote_path, str(dest_file), device_id=device_id)

            # Auto-resolusi nama resmi dari APK jika tersedia
            official_label = extract_apk_label(dest_file)
            if official_label:
                save_to_app_cache(package_name, official_label)
                if official_label != display_name:
                    display_name = official_label
                    new_file_base = sanitize_filename(display_name)
                    new_dest_file = output_dir / f"{new_file_base}.apk"
                    if new_dest_file != dest_file:
                        try:
                            if new_dest_file.exists():
                                new_dest_file.unlink()
                            dest_file.rename(new_dest_file)
                            dest_file = new_dest_file
                        except Exception:
                            pass

            size_bytes = dest_file.stat().st_size
            return ExtractionResult(
                package_name=package_name,
                app_name=display_name,
                output_path=dest_file,
                is_split=False,
                total_parts=1,
                size_bytes=size_bytes,
            )

        # Split APKs (App Bundle)
        temp_dir = Path(tempfile.mkdtemp(prefix=f"apkx_{file_base_name}_"))
        try:
            pulled_files: List[Path] = []
            for idx, remote_path in enumerate(remote_paths, start=1):
                part_name = remote_path.split("/")[-1]
                local_part_path = temp_dir / part_name

                if progress_callback:
                    progress_callback(f"Menarik split ({idx}/{total_parts}): {part_name}...", idx, total_parts)

                self.adb.pull_file(remote_path, str(local_part_path), device_id=device_id)
                pulled_files.append(local_part_path)

            # Auto-resolusi nama resmi dari base.apk jika tersedia
            base_apk = next((f for f in pulled_files if "base" in f.name.lower()), pulled_files[0])
            official_label = extract_apk_label(base_apk)
            if official_label:
                save_to_app_cache(package_name, official_label)
                if official_label != display_name:
                    display_name = official_label
                    file_base_name = sanitize_filename(display_name)

            apks_bundle_path = output_dir / f"{file_base_name}.apks"
            if progress_callback:
                progress_callback(f"Mengemas {total_parts} split APK ke dalam {apks_bundle_path.name}...", total_parts, total_parts)

            with zipfile.ZipFile(apks_bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_bundle:
                for file_path in pulled_files:
                    zip_bundle.write(file_path, arcname=file_path.name)

            size_bytes = apks_bundle_path.stat().st_size
            return ExtractionResult(
                package_name=package_name,
                app_name=display_name,
                output_path=apks_bundle_path,
                is_split=True,
                total_parts=total_parts,
                size_bytes=size_bytes,
            )
        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def unpack(
        self,
        archive_path: Path,
        target_dir: Path,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Path:
        """
        Membongkar isi file .apk atau .apks ke dalam target_dir.
        - Jika .apk: langsung diekstrak secara aman.
        - Jika .apks: mengekstrak seluruh pecahan APK, di mana tiap split dibongkar ke subfolder.
        """
        target_dir.mkdir(parents=True, exist_ok=True)

        if archive_path.suffix.lower() == ".apk":
            # Ekstrak langsung file APK tunggal
            with zipfile.ZipFile(archive_path, "r") as zf:
                safe_extract_zip(
                    zf,
                    target_dir,
                    progress_callback=progress_callback,
                    task_label=f"Mengekstrak {archive_path.name}",
                )

        elif archive_path.suffix.lower() == ".apks":
            # Ekstrak paket APKS ke temporary
            temp_split_dir = Path(tempfile.mkdtemp(prefix="apkx_unpack_apks_"))
            try:
                with zipfile.ZipFile(archive_path, "r") as bundle_zf:
                    safe_extract_zip(
                        bundle_zf,
                        temp_split_dir,
                        progress_callback=progress_callback,
                        task_label="Membuka bundle APKS",
                    )

                split_files = sorted(list(temp_split_dir.glob("*.apk")))
                total_splits = len(split_files)
                for split_idx, split_file in enumerate(split_files, start=1):
                    subfolder_name = split_file.stem
                    sub_out_dir = target_dir / subfolder_name
                    sub_out_dir.mkdir(parents=True, exist_ok=True)
                    if progress_callback:
                        progress_callback(
                            f"Mengekstrak split ({split_idx}/{total_splits}): {split_file.name}",
                            split_idx,
                            total_splits,
                        )
                    with zipfile.ZipFile(split_file, "r") as split_zf:
                        safe_extract_zip(
                            split_zf,
                            sub_out_dir,
                            progress_callback=progress_callback,
                            task_label=f"Mengekstrak {split_file.stem}",
                        )
            finally:
                if temp_split_dir.exists():
                    shutil.rmtree(temp_split_dir, ignore_errors=True)

        # Otomatis decode AndroidManifest.xml biner ke teks XML terbaca
        self.decode_manifest_files(target_dir)

        return target_dir

    def decode_manifest_files(self, target_dir: Path) -> Optional[Path]:
        """
        Mencari dan mendekode seluruh AndroidManifest.xml biner (AXML) di target_dir
        menjadi berkas XML teks biasa (AndroidManifest_readable.xml).
        """
        candidates = list(target_dir.glob("**/AndroidManifest.xml"))
        decoded_root_path = target_dir / "AndroidManifest_readable.xml"

        for manifest_path in candidates:
            try:
                raw_bytes = manifest_path.read_bytes()
                decoded_xml = decode_axml(raw_bytes)
                if decoded_xml and "<manifest" in decoded_xml:
                    readable_path = manifest_path.parent / "AndroidManifest_readable.xml"
                    readable_path.write_text(decoded_xml, encoding="utf-8")
                    if not decoded_root_path.exists() or "base" in manifest_path.parts:
                        decoded_root_path.write_text(decoded_xml, encoding="utf-8")
            except Exception:
                pass

        return decoded_root_path if decoded_root_path.exists() else None

    def detect_framework(self, extracted_dir: Path) -> Dict[str, str]:
        """
        Mendeteksi teknologi/framework yang digunakan oleh aplikasi
        (Flutter, React Native, Unity, atau Native Android).
        """
        # 1. Cek Flutter
        flutter_so = list(extracted_dir.glob("**/libapp.so"))
        flutter_assets = list(extracted_dir.glob("**/flutter_assets"))
        if flutter_so or flutter_assets:
            code_loc = str(flutter_so[0].relative_to(extracted_dir)) if flutter_so else "assets/flutter_assets"
            return {
                "framework": "Flutter 🐦",
                "code_path": code_loc,
                "description": "Logika aplikasi dikompilasi ke binary Dart AOT (libapp.so). Aset UI ada di folder flutter_assets.",
            }

        # 2. Cek React Native
        rn_bundles = list(extracted_dir.glob("**/index.android.bundle"))
        if rn_bundles:
            bundle_rel = str(rn_bundles[0].relative_to(extracted_dir))
            is_hermes = False
            try:
                magic = rn_bundles[0].read_bytes()[:4]
                # Magic bytes Hermes bytecode
                if magic in (b"\xc6\x1f\xbc\x03", b"\x03\xbc\x1f\xc6"):
                    is_hermes = True
            except Exception:
                pass

            engine_type = "Hermes Bytecode" if is_hermes else "JavaScript Standard"
            return {
                "framework": f"React Native ⚛️ ({engine_type})",
                "code_path": bundle_rel,
                "description": f"Kode logika dan komponen UI tersimpan di berkas JavaScript bundle ({bundle_rel}).",
            }

        # 3. Cek Unity
        unity_data = list(extracted_dir.glob("**/bin/Data")) or list(extracted_dir.glob("**/libunity.so"))
        if unity_data:
            return {
                "framework": "Unity 🎮",
                "code_path": "assets/bin/Data",
                "description": "Aplikasi game berbasis Unity engine.",
            }

        # 4. Default: Native Android
        dex_files = list(extracted_dir.glob("**/*.dex"))
        dex_count = len(dex_files)
        return {
            "framework": "Native Android (Java/Kotlin) ☕",
            "code_path": f"{dex_count} file classes.dex",
            "description": "Kode logika dikompilasi ke bytecode Dalvik/ART (.dex). Gunakan JADX untuk membaca kode Java.",
        }

    def generate_analysis_summary(self, extracted_dir: Path, app_name: str, package_name: str) -> Dict[str, Any]:
        """
        Menghasilkan ringkasan analisis teknologi, dekode manifest, ekstraksi endpoint,
        dan menulis file catatan di folder ekstraksi.
        """
        # Bersihkan artefak analisis usang jika ada sebelumnya
        for artifact_name in (
            "endpoints.json",
            "class_skeleton.json",
            "class_skeleton.txt",
            "sqlite_schema.json",
            "sqlite_schema.sql",
            "analysis_info.json",
            "README.txt",
        ):
            stale_file = extracted_dir / artifact_name
            if stale_file.is_file():
                try:
                    stale_file.unlink()
                except Exception:
                    pass

        fw_info = self.detect_framework(extracted_dir)

        # 1. Pastikan Manifest terbaca
        decoded_manifest = self.decode_manifest_files(extracted_dir)

        # 2. Ekstrak Endpoints & URLs
        endpoints_data = extract_endpoints_from_dir(extracted_dir)
        endpoints_file = extracted_dir / "endpoints.json"
        try:
            endpoints_file.write_text(json.dumps(endpoints_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        # 3. Ekstrak Struktur & Kerangka Kelas (DEX Class Skeleton)
        skeleton_data = extract_class_skeleton_from_dir(extracted_dir, target_package=package_name)
        skeleton_json_file = extracted_dir / "class_skeleton.json"
        skeleton_txt_file = extracted_dir / "class_skeleton.txt"
        try:
            skeleton_json_file.write_text(json.dumps(skeleton_data, indent=2, ensure_ascii=False), encoding="utf-8")
            skeleton_txt = format_skeleton_text(skeleton_data, app_name, package_name)
            skeleton_txt_file.write_text(skeleton_txt, encoding="utf-8")
        except Exception:
            pass

        # 4. Ekstrak Skema SQLite dari Biner (.so, .dex)
        sqlite_data = extract_sqlite_schema_from_dir(extracted_dir)
        sqlite_json_file = extracted_dir / "sqlite_schema.json"
        sqlite_sql_file = extracted_dir / "sqlite_schema.sql"
        if sqlite_data.get("total_tables", 0) > 0:
            try:
                sqlite_json_file.write_text(json.dumps(sqlite_data, indent=2, ensure_ascii=False), encoding="utf-8")
                raw_sql = "\n\n".join(sqlite_data.get("raw_statements", []))
                sqlite_sql_file.write_text(raw_sql, encoding="utf-8")
            except Exception:
                pass

        summary_data = {
            "app_name": app_name,
            "package_name": package_name,
            "framework": fw_info["framework"],
            "primary_code_location": fw_info["code_path"],
            "description": fw_info["description"],
            "extracted_directory": str(extracted_dir.resolve()),
            "decoded_manifest": str(decoded_manifest.name) if decoded_manifest else None,
            "total_urls_found": endpoints_data.get("total_urls", 0),
            "domains": endpoints_data.get("domains", []),
            "sample_api_endpoints": endpoints_data.get("api_endpoints", [])[:10],
            "total_classes": skeleton_data.get("total_classes", 0),
            "app_classes_count": skeleton_data.get("app_classes_count", 0),
            "class_skeleton": "class_skeleton.txt" if skeleton_txt_file.exists() else None,
            "sqlite_tables_count": sqlite_data.get("total_tables", 0),
            "sqlite_schema": "sqlite_schema.json" if sqlite_json_file.exists() else None,
        }

        # Tulis JSON
        info_json = extracted_dir / "analysis_info.json"
        try:
            info_json.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
        except Exception:
            pass

        # Format README
        domains_list = endpoints_data.get("domains", [])
        domains_str = "\n".join(f"  • {d}" for d in domains_list[:10])
        if len(domains_list) > 10:
            domains_str += f"\n  • ... dan {len(domains_list) - 10} domain lainnya"

        endpoints_sample = endpoints_data.get("api_endpoints", [])[:8]
        if not endpoints_sample:
            endpoints_sample = endpoints_data.get("all_endpoints", [])[:8]

        endpoints_sample_str = "\n".join(f"  • {ep}" for ep in endpoints_sample)
        if not endpoints_sample_str:
            endpoints_sample_str = "  (Tidak ada URL API terdeteksi)"

        readme_file = extracted_dir / "README_ANALISIS.txt"
        readme_text = (
            f"====================================================\n"
            f"  RINGKASAN ANALISIS APLIKASI - apkx\n"
            f"====================================================\n\n"
            f"Nama Aplikasi       : {app_name}\n"
            f"Package ID          : {package_name}\n"
            f"Teknologi/Framework : {fw_info['framework']}\n"
            f"Lokasi Kode Utama   : {fw_info['code_path']}\n"
            f"Decoded Manifest    : {decoded_manifest.name if decoded_manifest else '-'}\n"
            f"Total URL Ditemukan : {endpoints_data.get('total_urls', 0)}\n"
            f"Tabel SQLite Biner  : {sqlite_data.get('total_tables', 0)} tabel terdeteksi\n\n"
            f"Domain Backend Terdeteksi:\n"
            f"{domains_str or '  (Tidak ada domain terdeteksi)'}\n\n"
            f"Contoh API Endpoints:\n"
            f"{endpoints_sample_str}\n\n"
            f"Keterangan:\n"
            f"{fw_info['description']}\n\n"
            f"Tips untuk AI Agent & Antigravity IDE:\n"
            f"- Buka file 'AndroidManifest_readable.xml' untuk melihat permission & activities lengkap.\n"
            f"- Buka file 'class_skeleton.txt' untuk melihat seluruh struktur kelas & modul aplikasi.\n"
            f"- Buka file 'endpoints.json' untuk melihat seluruh endpoint API aplikasi.\n"
            f"- Buka file 'sqlite_schema.sql' untuk melihat skema tabel database SQLite aplikasi.\n"
        )
        try:
            readme_file.write_text(readme_text, encoding="utf-8")
        except Exception:
            pass

        res = dict(fw_info)
        res["total_urls"] = endpoints_data.get("total_urls", 0)
        res["decoded_manifest"] = str(decoded_manifest.name) if decoded_manifest else None
        res["total_classes"] = skeleton_data.get("total_classes", 0)
        res["app_classes_count"] = skeleton_data.get("app_classes_count", 0)
        res["class_skeleton"] = "class_skeleton.txt" if skeleton_txt_file.exists() else None
        return res
