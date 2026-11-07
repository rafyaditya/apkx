"""
apkx: Fast Pure-Python DEX Class & Package Skeleton Parser.
Extracts class hierarchies and package structures directly from classes*.dex in milliseconds.
"""

import struct
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

THIRD_PARTY_PREFIXES = (
    "android.",
    "androidx.",
    "kotlin.",
    "kotlinx.",
    "com.google.",
    "org.intellij.",
    "org.jetbrains.",
    "io.reactivex.",
    "com.facebook.soloader.",
)


def parse_dex_classes(dex_bytes: bytes) -> List[str]:
    """
    Parses all class descriptors from a single DEX binary file.
    Returns sorted list of class names in dotted format (e.g. 'com.example.MainActivity').
    """
    if len(dex_bytes) < 0x70 or not dex_bytes.startswith(b"dex\n"):
        return []

    try:
        # Header offsets
        string_ids_size, string_ids_off = struct.unpack("<II", dex_bytes[0x38:0x40])
        type_ids_size, type_ids_off = struct.unpack("<II", dex_bytes[0x40:0x48])
        class_defs_size, class_defs_off = struct.unpack("<II", dex_bytes[0x60:0x68])

        if string_ids_off + string_ids_size * 4 > len(dex_bytes):
            return []
        if type_ids_off + type_ids_size * 4 > len(dex_bytes):
            return []
        if class_defs_off + class_defs_size * 32 > len(dex_bytes):
            return []

        string_offsets = struct.unpack(
            f"<{string_ids_size}I",
            dex_bytes[string_ids_off : string_ids_off + string_ids_size * 4],
        )

        def get_string(idx: int) -> str:
            if idx >= len(string_offsets):
                return ""
            off = string_offsets[idx]
            if off >= len(dex_bytes):
                return ""
            # Skip uleb128 utf-16 length
            while off < len(dex_bytes) and dex_bytes[off] & 0x80:
                off += 1
            off += 1
            end = dex_bytes.find(b"\x00", off)
            if end != -1:
                try:
                    return dex_bytes[off:end].decode("utf-8", errors="replace")
                except Exception:
                    return ""
            return ""

        type_indices = struct.unpack(
            f"<{type_ids_size}I",
            dex_bytes[type_ids_off : type_ids_off + type_ids_size * 4],
        )

        classes = []
        for i in range(class_defs_size):
            c_off = class_defs_off + i * 32
            class_idx, _ = struct.unpack("<II", dex_bytes[c_off : c_off + 8])
            if class_idx < len(type_indices):
                s_idx = type_indices[class_idx]
                raw_desc = get_string(s_idx)
                if raw_desc.startswith("L") and raw_desc.endswith(";"):
                    formatted = raw_desc[1:-1].replace("/", ".")
                    classes.append(formatted)
                elif raw_desc:
                    classes.append(raw_desc)

        return sorted(classes)
    except Exception:
        return []


def extract_class_skeleton_from_dir(
    target_dir: Path, target_package: Optional[str] = None
) -> Dict[str, Any]:
    """
    Scans all classes*.dex in target_dir and extracts class hierarchies,
    filtering and organizing classes for AI Agent consumption.
    """
    all_classes: Set[str] = set()

    for dex_file in target_dir.rglob("*.dex"):
        if dex_file.is_file():
            try:
                classes = parse_dex_classes(dex_file.read_bytes())
                all_classes.update(classes)
            except Exception:
                pass

    sorted_all = sorted(list(all_classes))

    # Identify app-specific classes vs standard 3rd party frameworks
    app_classes = []
    third_party_classes = []

    target_root = target_package.split(".")[0] if target_package and "." in target_package else None
    target_pfx = (
        ".".join(target_package.split(".")[:2]) if target_package and "." in target_package else None
    )

    for c in sorted_all:
        if target_pfx and c.startswith(target_pfx):
            app_classes.append(c)
        elif target_root and c.startswith(f"{target_root}."):
            app_classes.append(c)
        elif c.startswith(THIRD_PARTY_PREFIXES):
            third_party_classes.append(c)
        else:
            app_classes.append(c)

    # Group packages
    packages: Set[str] = set()
    for c in sorted_all:
        if "." in c:
            pkg = ".".join(c.split(".")[:-1])
            packages.add(pkg)

    return {
        "total_classes": len(sorted_all),
        "app_classes_count": len(app_classes),
        "third_party_classes_count": len(third_party_classes),
        "packages_count": len(packages),
        "packages": sorted(list(packages)),
        "app_classes": app_classes,
        "all_classes": sorted_all,
    }


def format_skeleton_text(skeleton_data: Dict[str, Any], app_name: str, package_name: str) -> str:
    """
    Generates a clean, compact skeleton text representation of packages and classes
    designed specifically for AI Agent architectural analysis without token bloat.
    """
    lines = [
        "====================================================",
        f"  STRUKTUR KELAS & ARSITEKTUR - {app_name}",
        "====================================================",
        f"Package ID          : {package_name}",
        f"Total Kelas DEX     : {skeleton_data.get('total_classes', 0)}",
        f"Kelas Aplikasi/Fitur: {skeleton_data.get('app_classes_count', 0)}",
        f"Total Package       : {skeleton_data.get('packages_count', 0)}",
        "",
        "--- [ DAFTAR KELAS APLIKASI & MODUL UTAMA ] ---",
    ]

    app_classes = skeleton_data.get("app_classes", [])
    if app_classes:
        # Group by package prefix
        current_pkg = ""
        for c in app_classes:
            pkg = ".".join(c.split(".")[:-1]) if "." in c else "(root)"
            class_name = c.split(".")[-1]
            if pkg != current_pkg:
                current_pkg = pkg
                lines.append(f"\n[Package: {current_pkg}]")
            lines.append(f"  • {class_name}")
    else:
        lines.append("  (Tidak ada kelas spesifik terpisah ditemukan)")

    lines.append("\n--- [ RINGKASAN SELURUH PACKAGE TERDETEKSI ] ---")
    for p in skeleton_data.get("packages", [])[:40]:
        lines.append(f"  📁 {p}")
    if len(skeleton_data.get("packages", [])) > 40:
        lines.append(f"  ... dan {len(skeleton_data['packages']) - 40} package lainnya")

    return "\n".join(lines)
