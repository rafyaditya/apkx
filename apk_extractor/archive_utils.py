"""
Utilitas ekstraksi arsip yang aman.
Hanya mengimpor standard library agar tidak menimbulkan circular import.
"""

import shutil
import sys
import zipfile
from pathlib import Path
from typing import Callable, List, Optional

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def sanitize_archive_member_path(member_path: str) -> Path:
    if "\x00" in member_path:
        return Path()

    raw = member_path.replace("\\", "/")

    prefixes = ("//?/", "//./", "/?/", "/./")
    changed = True
    while changed:
        changed = False
        for prefix in prefixes:
            if raw.startswith(prefix):
                raw = raw[len(prefix):]
                changed = True
                break

    if len(raw) >= 2 and raw[1] == ":":
        raw = raw[2:]

    raw = raw.replace(":", "_").lstrip("/")

    parts: List[str] = []
    for part in raw.split("/"):
        if part in ("", ".", ".."):
            continue

        part = part.rstrip(" .")
        if not part:
            continue

        first_segment = part.split(".")[0].upper()
        if first_segment in WINDOWS_RESERVED_NAMES:
            part = f"_{part}"

        parts.append(part)

    return Path(*parts) if parts else Path()


def safe_extract_zip(
    zf: zipfile.ZipFile,
    target_dir: Path,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
    task_label: str = "Mengekstrak berkas",
    max_total_size_bytes: int = 8 * 1024 * 1024 * 1024,
    max_compression_ratio: int = 1000,
) -> int:
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    members = zf.infolist()
    total_members = len(members)

    total_size = 0
    for member in members:
        total_size += max(0, member.file_size)
        if total_size > max_total_size_bytes:
            raise ValueError(
                f"Arsip melebihi batas ukuran ekstraksi ({max_total_size_bytes} bytes)."
            )

        if (
            member.compress_size > 0
            and member.file_size > 10 * 1024 * 1024
            and member.file_size / member.compress_size > max_compression_ratio
        ):
            raise ValueError(
                f"Rasio kompresi mencurigakan untuk {member.filename!r}."
            )

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

        if member.is_dir() or member.filename.endswith(("/", "\\")):
            dest_path.mkdir(parents=True, exist_ok=True)
            continue

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

        if progress_callback and (idx % 25 == 0 or idx == total_members):
            progress_callback(
                f"{task_label} ({idx}/{total_members}): {clean_rel_path.name}...",
                idx,
                total_members,
            )

    return extracted_count
