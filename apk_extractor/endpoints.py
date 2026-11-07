"""
apkx: API Endpoints & URL Extractor.
Scans extracted application binaries (DEX, SO, JS bundles, JSON) for backend URLs and endpoints.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Set

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


def extract_endpoints_from_dir(target_dir: Path) -> Dict[str, Any]:
    """
    Scans a directory containing unpacked APK assets for URLs, domains, and API endpoints.
    """
    found_urls: Set[str] = set()
    found_domains: Set[str] = set()
    api_endpoints: Set[str] = set()

    scan_exts = {".dex", ".so", ".bundle", ".json", ".js", ".bin"}

    if not target_dir.is_dir():
        return {
            "total_urls": 0,
            "domains": [],
            "api_endpoints": [],
            "all_endpoints": [],
        }

    for f in target_dir.rglob("*"):
        if f.is_file() and f.suffix.lower() in scan_exts:
            try:
                # Read binary file
                content = f.read_bytes()
                matches = URL_REGEX.findall(content)
                for m in matches:
                    try:
                        url = m.decode("utf-8", errors="ignore").strip().rstrip('.)("\'')
                        # Filter ignored domains and invalid lengths
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
            except Exception:
                pass

    return {
        "total_urls": len(found_urls),
        "domains": sorted(list(found_domains)),
        "api_endpoints": sorted(list(api_endpoints)),
        "all_endpoints": sorted(list(found_urls)),
    }
