"""
apkx: API Endpoints & URL Extractor.
Scans extracted application binaries (DEX, SO, JS bundles, JSON) for backend URLs and endpoints.
"""

import io
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, Set

URL_REGEX = re.compile(rb"https?://[a-zA-Z0-9\.\-_]+(?::\d+)?(?:/[a-zA-Z0-9\.\-_~:/?#[\]@!$&'()*+,;=%]*)?")

IGNORED_PATTERNS = {
    "schemas.android.com",
    "www.w3.org",
    "xml.org",
    "json-schema.org",
    "plus.google.com",
    "apache.org",
    "xmlns.com",
    "example.com",
}

API_KEYWORDS = ("/api/", "/v1/", "/v2/", "/v3/", "/graphql", "/rest/", "/auth/", "/oauth/", "/service/", "/endpoint/")
SCAN_EXTS = {".dex", ".so", ".bundle", ".json", ".js", ".bin"}


def _scan_binary_content(
    content: bytes,
    found_urls: Set[str],
    found_domains: Set[str],
    api_endpoints: Set[str],
) -> None:
    """Helper to scan binary content and extract URLs, domains, and API endpoints."""
    matches = URL_REGEX.findall(content)
    for m in matches:
        try:
            url = m.decode("utf-8", errors="ignore").strip().rstrip('.)("\'')
            if not any(ign in url for ign in IGNORED_PATTERNS) and 10 < len(url) < 300:
                found_urls.add(url)
                domain_match = re.search(r"https?://([a-zA-Z0-9\.\-_]+)", url)
                if domain_match:
                    found_domains.add(domain_match.group(1))

                url_lower = url.lower()
                if any(k in url_lower for k in API_KEYWORDS):
                    api_endpoints.add(url)
        except Exception:
            pass


def extract_endpoints_from_dir(target_dir: Path) -> Dict[str, Any]:
    """
    Scans a directory containing unpacked APK assets for URLs, domains, and API endpoints.
    """
    found_urls: Set[str] = set()
    found_domains: Set[str] = set()
    api_endpoints: Set[str] = set()

    if not target_dir.is_dir():
        return {
            "total_urls": 0,
            "domains": [],
            "api_endpoints": [],
            "all_endpoints": [],
        }

    for f in target_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in SCAN_EXTS:
            try:
                _scan_binary_content(f.read_bytes(), found_urls, found_domains, api_endpoints)
            except Exception:
                pass

    return {
        "total_urls": len(found_urls),
        "domains": sorted(list(found_domains)),
        "api_endpoints": sorted(list(api_endpoints)),
        "all_endpoints": sorted(list(found_urls)),
    }


def extract_endpoints_from_file(file_path: Path) -> Dict[str, Any]:
    """
    Scans an APK, APKS, ZIP, DEX, or SO binary file directly for URLs and endpoints
    without requiring manual prior extraction to disk.
    """
    found_urls: Set[str] = set()
    found_domains: Set[str] = set()
    api_endpoints: Set[str] = set()

    if not file_path.is_file():
        return {
            "total_urls": 0,
            "domains": [],
            "api_endpoints": [],
            "all_endpoints": [],
        }

    archive_exts = {".apk", ".apks", ".zip"}
    if file_path.suffix.lower() in archive_exts and not zipfile.is_zipfile(file_path):
        return {
            "status": "error",
            "error": f"Berkas '{file_path.name}' bukan arsip zip/APK yang valid atau berkas rusak.",
            "total_urls": 0,
            "domains": [],
            "api_endpoints": [],
            "all_endpoints": [],
        }

    # Check if archive (.apk, .apks, .zip)
    if zipfile.is_zipfile(file_path):
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                for info in zf.infolist():
                    name_lower = info.filename.lower()
                    suffix = Path(name_lower).suffix

                    # If nested APK in .apks bundle
                    if suffix == ".apk":
                        try:
                            nested_bytes = zf.read(info)
                            with zipfile.ZipFile(io.BytesIO(nested_bytes), "r") as sub_zf:
                                for sub_info in sub_zf.infolist():
                                    sub_suffix = Path(sub_info.filename.lower()).suffix
                                    if sub_suffix in SCAN_EXTS:
                                        _scan_binary_content(
                                            sub_zf.read(sub_info),
                                            found_urls,
                                            found_domains,
                                            api_endpoints,
                                        )
                        except Exception:
                            pass
                    elif suffix in SCAN_EXTS:
                        try:
                            _scan_binary_content(
                                zf.read(info),
                                found_urls,
                                found_domains,
                                api_endpoints,
                            )
                        except Exception:
                            pass
        except Exception:
            pass
    elif file_path.suffix.lower() in SCAN_EXTS:
        try:
            _scan_binary_content(file_path.read_bytes(), found_urls, found_domains, api_endpoints)
        except Exception:
            pass

    return {
        "total_urls": len(found_urls),
        "domains": sorted(list(found_domains)),
        "api_endpoints": sorted(list(api_endpoints)),
        "all_endpoints": sorted(list(found_urls)),
    }
