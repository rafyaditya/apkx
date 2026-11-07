"""
apkx: Native Model Context Protocol (MCP) Server.
Exposes ADB device operations, APK extraction, manifest decoding, and on-demand JADX analysis to AI Agents.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError:
        MCPServer = None

from apk_extractor.adb import ADBManager
from apk_extractor.app_names import resolve_apps
from apk_extractor.axml import decode_axml
from apk_extractor.dex import extract_class_skeleton_from_dir, format_skeleton_text
from apk_extractor.endpoints import extract_endpoints_from_dir
from apk_extractor.jadx import JADXManager
from apk_extractor.packager import APKPackager, sanitize_filename


def create_mcp_server() -> Any:
    """Creates and configures the native apkx MCPServer instance."""
    if MCPServer is None:
        raise RuntimeError("Library 'mcp' belum terpasang. Jalankan: pip install 'mcp>=1.0.0'")

    server = MCPServer(
        name="apkx",
        title="apkx Android Device & APK Analysis Server",
        description="Extract and reverse engineer Android APKs, inspect manifests, API endpoints, and DEX classes.",
    )

    adb = ADBManager()
    jadx = JADXManager()
    packager = APKPackager(adb=adb, jadx=jadx)

    @server.tool()
    def apkx_list_devices() -> List[Dict[str, Any]]:
        """
        Lists all connected Android devices with their Serial ID, brand, model, Android OS version, and authorization status.
        """
        adb.ensure_installed()
        return adb.get_devices_with_details()

    @server.tool()
    def apkx_list_apps(
        device_id: Optional[str] = None,
        include_system_apps: bool = False,
    ) -> List[Dict[str, str]]:
        """
        Lists installed packages on the connected Android device, automatically resolved to human-friendly app names.
        """
        adb.ensure_installed()
        packages = adb.list_packages(
            device_id=device_id,
            third_party_only=not include_system_apps,
            system_only=include_system_apps,
        )
        apps = resolve_apps(adb, packages, device_id=device_id)
        return [{"app_name": a.app_name, "package_name": a.package_name} for a in apps]

    @server.tool()
    def apkx_get_app_info(package_name: str, device_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Retrieves quick technical audit details (versionName, versionCode, targetSdk, minSdk, permissions, APK paths)
        directly from the Android device without downloading the APK.
        """
        adb.ensure_installed()
        return adb.get_package_quick_info(package_name, device_id=device_id)

    @server.tool()
    def apkx_pull_and_extract(
        query_or_package: str,
        device_id: Optional[str] = None,
        output_dir: str = "output",
    ) -> Dict[str, Any]:
        """
        Pulls an application APK (including all Split APKs bundled as .apks) from the Android device,
        unpacks its contents, decodes the AndroidManifest.xml, extracts API endpoints, and generates class skeletons.
        """
        adb.ensure_installed()
        out_path = Path(output_dir)

        # 1. Resolve package
        packages = adb.list_packages(device_id=device_id, third_party_only=False)
        apps = resolve_apps(adb, packages, device_id=device_id)

        target_app = None
        q_clean = query_or_package.strip().lower()
        for a in apps:
            if a.package_name.lower() == q_clean or a.app_name.lower() == q_clean:
                target_app = a
                break
        if not target_app:
            for a in apps:
                if q_clean in a.package_name.lower() or q_clean in a.app_name.lower():
                    target_app = a
                    break

        if not target_app:
            return {
                "status": "error",
                "message": f"Aplikasi '{query_or_package}' tidak ditemukan di perangkat.",
            }

        apk_paths = adb.get_package_apk_paths(target_app.package_name, device_id=device_id)
        if not apk_paths:
            return {
                "status": "error",
                "message": f"Tidak dapat menemukan lokasi file APK untuk {target_app.package_name}.",
            }

        apks_dir = out_path / "apks"
        extracted_dir = out_path / "extracted"
        apks_dir.mkdir(parents=True, exist_ok=True)
        extracted_dir.mkdir(parents=True, exist_ok=True)

        # Pull & package
        extract_res = packager.extract(
            package_name=target_app.package_name,
            remote_paths=apk_paths,
            output_dir=apks_dir,
            app_name=target_app.app_name,
            device_id=device_id,
        )

        # Unpack
        app_folder_name = sanitize_filename(extract_res.app_name)
        app_extracted_folder = extracted_dir / app_folder_name
        packager.unpack(extract_res.output_path, app_extracted_folder)

        # Summary analysis (Manifest, Endpoints, Skeleton)
        summary = packager.generate_analysis_summary(
            app_extracted_folder, extract_res.app_name, extract_res.package_name
        )

        return {
            "status": "success",
            "app_name": extract_res.app_name,
            "package_name": extract_res.package_name,
            "is_split": extract_res.is_split,
            "total_parts": extract_res.total_parts,
            "apk_path": str(extract_res.output_path.resolve()),
            "extracted_folder": str(app_extracted_folder.resolve()),
            "framework": summary.get("framework"),
            "decoded_manifest": str((app_extracted_folder / "AndroidManifest_readable.xml").resolve()),
            "endpoints_file": str((app_extracted_folder / "endpoints.json").resolve()),
            "class_skeleton_file": str((app_extracted_folder / "class_skeleton.txt").resolve()),
            "total_urls_found": summary.get("total_urls", 0),
            "total_classes_found": summary.get("total_classes", 0),
        }

    @server.tool()
    def apkx_get_manifest(target_path: str) -> str:
        """
        Retrieves the decoded, human-readable AndroidManifest.xml from an extracted app directory or APK.
        """
        p = Path(target_path)
        if p.is_dir():
            # Check for readable manifest first
            readable = p / "AndroidManifest_readable.xml"
            if readable.exists():
                return readable.read_text(encoding="utf-8")
            base_readable = p / "base" / "AndroidManifest_readable.xml"
            if base_readable.exists():
                return base_readable.read_text(encoding="utf-8")

            # Check for raw manifest and decode
            raw_manifest = p / "AndroidManifest.xml"
            if not raw_manifest.exists():
                raw_manifest = p / "base" / "AndroidManifest.xml"
            if raw_manifest.exists():
                return decode_axml(raw_manifest.read_bytes())
        elif p.is_file():
            # If APK file or xml file
            if p.suffix.lower() == ".xml":
                return decode_axml(p.read_bytes())
            import zipfile
            with zipfile.ZipFile(p, "r") as zf:
                if "AndroidManifest.xml" in zf.namelist():
                    data = zf.read("AndroidManifest.xml")
                    return decode_axml(data)

        return "Manifest tidak ditemukan atau tidak dapat didekode."

    @server.tool()
    def apkx_get_endpoints(target_path: str) -> Dict[str, Any]:
        """
        Extracts backend URLs, API endpoints, and domains from an extracted app directory or APK.
        """
        p = Path(target_path)
        if p.is_dir():
            endpoints_json = p / "endpoints.json"
            if endpoints_json.exists():
                try:
                    return json.loads(endpoints_json.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return extract_endpoints_from_dir(p)
        return {"error": f"Path '{target_path}' bukan direktori yang valid."}

    @server.tool()
    def apkx_get_class_skeleton(target_path: str, target_package: Optional[str] = None) -> str:
        """
        Returns the compact class and package skeleton (DEX structure) of an application without token bloat.
        """
        p = Path(target_path)
        if p.is_dir():
            skeleton_txt = p / "class_skeleton.txt"
            if skeleton_txt.exists():
                return skeleton_txt.read_text(encoding="utf-8")
            skeleton_data = extract_class_skeleton_from_dir(p, target_package=target_package)
            return format_skeleton_text(skeleton_data, p.name, target_package or p.name)
        return "Path tidak valid untuk membaca class skeleton."

    @server.tool()
    def apkx_inspect_class(target_apk: str, class_name: str) -> str:
        """
        Decompiles a specific Java/Kotlin class on-demand from an APK/APKS file using Headless JADX.
        Returns the decompiled Java source code.
        """
        apk_p = Path(target_apk)
        if not apk_p.is_file():
            return f"File APK '{target_apk}' tidak ditemukan."

        if not jadx.ensure_installed():
            return "Engine JADX belum terpasang atau Java 11+ tidak tersedia pada sistem."

        code = jadx.decompile_class(apk_p, class_name)
        if code:
            return code
        return f"Gagal mendekomposisi kelas '{class_name}'. Pastikan nama kelas dan path APK benar."

    @server.tool()
    def apkx_find_classes(
        target_path: str,
        query: str,
        app_only: bool = True,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Searches for DEX classes matching a keyword or substring within an extracted app directory.
        Allows AI agents to quickly find specific classes (e.g. 'Auth', 'Repository', 'ViewModel', 'Api')
        without dumping entire class skeletons into context.
        """
        p = Path(target_path)
        if not p.is_dir():
            return {"error": f"Path '{target_path}' bukan direktori yang valid.", "matches": []}

        q_clean = query.strip().lower()
        if not q_clean:
            return {"error": "Query pencarian kelas tidak boleh kosong.", "matches": []}

        # Check skeleton JSON first if available
        skeleton_file = p / "class_skeleton.json"
        if skeleton_file.exists():
            try:
                data = json.loads(skeleton_file.read_text(encoding="utf-8"))
            except Exception:
                data = extract_class_skeleton_from_dir(p)
        else:
            data = extract_class_skeleton_from_dir(p)

        classes_to_search = data.get("app_classes", []) if app_only else data.get("all_classes", [])
        matched = [c for c in classes_to_search if q_clean in c.lower()]

        return {
            "query": query,
            "app_only": app_only,
            "total_matches": len(matched),
            "classes": matched[:limit],
            "has_more": len(matched) > limit,
        }

    @server.tool()
    def apkx_search_endpoints(
        target_path: str,
        query: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Searches and filters extracted backend URLs, API endpoints, and domains by keyword
        (e.g. 'auth', 'api', 'v1', 'graphql', or domain names) from an extracted app directory.
        """
        p = Path(target_path)
        if not p.is_dir():
            return {"error": f"Path '{target_path}' bukan direktori yang valid.", "domains": [], "endpoints": []}

        ep_file = p / "endpoints.json"
        if ep_file.exists():
            try:
                data = json.loads(ep_file.read_text(encoding="utf-8"))
            except Exception:
                data = extract_endpoints_from_dir(p)
        else:
            data = extract_endpoints_from_dir(p)

        all_endpoints = data.get("all_endpoints", [])
        domains = data.get("domains", [])

        if not query:
            return {
                "total_domains": len(domains),
                "total_endpoints": len(all_endpoints),
                "domains": domains[:limit],
                "api_endpoints": data.get("api_endpoints", [])[:limit],
            }

        q_clean = query.strip().lower()
        matched_domains = [d for d in domains if q_clean in d.lower()]
        matched_urls = [u for u in all_endpoints if q_clean in u.lower()]

        return {
            "query": query,
            "total_domain_matches": len(matched_domains),
            "total_url_matches": len(matched_urls),
            "domains": matched_domains[:limit],
            "endpoints": matched_urls[:limit],
            "has_more": len(matched_urls) > limit or len(matched_domains) > limit,
        }

    return server


def run_mcp_server(transport: str = "stdio") -> None:
    """Launches the apkx MCP server on standard stdio transport."""
    server = create_mcp_server()
    server.run(transport=transport)


if __name__ == "__main__":
    run_mcp_server()
