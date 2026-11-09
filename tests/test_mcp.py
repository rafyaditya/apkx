import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from apk_extractor.adb import ADBError
from apk_extractor.mcp_server import create_mcp_server


class TestMCPServer(unittest.TestCase):
    def setUp(self):
        self.server = create_mcp_server()

    def _parse_res(self, res):
        if hasattr(res, "structured_content") and isinstance(res.structured_content, dict) and "result" in res.structured_content:
            return res.structured_content["result"]
        if hasattr(res, "content") and res.content:
            try:
                return json.loads(res.content[0].text)
            except Exception:
                return res.content[0].text
        return res

    def test_registered_tools(self):
        async def run_check():
            tools = await self.server.list_tools()
            tool_names = [t.name for t in tools]
            expected = [
                "apkx_list_devices",
                "apkx_list_apps",
                "apkx_get_app_info",
                "apkx_pull_and_extract",
                "apkx_get_manifest",
                "apkx_get_endpoints",
                "apkx_get_class_skeleton",
                "apkx_inspect_class",
                "apkx_find_classes",
                "apkx_search_endpoints",
                "apkx_extract_sqlite_schema",
                "apkx_launch_app",
                "apkx_take_screenshot",
                "apkx_dump_ui_hierarchy",
                "apkx_interact",
                "apkx_ensure_device_awake",
                "apkx_get_current_screen",
                "apkx_get_app_logs",
                "apkx_reset_app_data",
                "apkx_open_deep_link",
                "apkx_toggle_night_mode",
                "apkx_install_apk",
                "apkx_uninstall_app",
                "apkx_diagnostics",
                "apkx_force_stop_app",
                "apkx_find_ui_element",
                "apkx_verify_install",
                "apkx_grant_permission",
            ]
            self.assertEqual(len(tool_names), 28)
            for exp in expected:
                self.assertIn(exp, tool_names)

        asyncio.run(run_check())

    def test_get_manifest_readable(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            readable = p / "AndroidManifest_readable.xml"
            readable.write_text("<manifest package='com.test'></manifest>", encoding="utf-8")

            async def run_call():
                # Call tool directly or via call_tool
                res = await self.server.call_tool("apkx_get_manifest", {"target_path": str(p)})
                self.assertIn("com.test", str(res))

            asyncio.run(run_call())

    @patch("apk_extractor.mcp_server.decode_axml", return_value="<manifest package='com.split.app'></manifest>")
    def test_get_manifest_from_apks(self, mock_decode):
        import io
        import zipfile
        with tempfile.TemporaryDirectory() as tmp_d:
            apks_file = Path(tmp_d) / "test.apks"
            base_buffer = io.BytesIO()
            with zipfile.ZipFile(base_buffer, "w") as base_zf:
                base_zf.writestr("AndroidManifest.xml", b"raw_manifest_bytes")

            with zipfile.ZipFile(apks_file, "w") as apks_zf:
                apks_zf.writestr("base.apk", base_buffer.getvalue())
                apks_zf.writestr("split.apk", b"split_bytes")

            async def run_call():
                res = await self.server.call_tool("apkx_get_manifest", {"target_path": str(apks_file)})
                self.assertIn("com.split.app", str(res))

            asyncio.run(run_call())

    def test_get_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            ep_file = p / "endpoints.json"
            ep_file.write_text('{"total_urls": 1, "domains": ["api.test.com"]}', encoding="utf-8")

            async def run_call():
                res = await self.server.call_tool("apkx_get_endpoints", {"target_path": str(p)})
                self.assertIn("api.test.com", str(res))

            asyncio.run(run_call())

    def test_find_classes(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            skeleton_file = p / "class_skeleton.json"
            skeleton_file.write_text(
                '{"app_classes": ["com.example.AuthService", "com.example.UserRepository"], "all_classes": []}',
                encoding="utf-8",
            )

            async def run_call():
                res = await self.server.call_tool(
                    "apkx_find_classes", {"target_path": str(p), "query": "auth"}
                )
                self.assertIn("com.example.AuthService", str(res))
                self.assertNotIn("com.example.UserRepository", str(res))

            asyncio.run(run_call())

    def test_search_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            ep_file = p / "endpoints.json"
            ep_file.write_text(
                '{"domains": ["auth.example.com", "cdn.example.com"], "all_endpoints": ["https://auth.example.com/v1/login", "https://cdn.example.com/img.png"]}',
                encoding="utf-8",
            )

            async def run_call():
                res = await self.server.call_tool(
                    "apkx_search_endpoints", {"target_path": str(p), "query": "login"}
                )
                self.assertIn("https://auth.example.com/v1/login", str(res))
                self.assertNotIn("https://cdn.example.com/img.png", str(res))

            asyncio.run(run_call())

    def test_extract_sqlite_schema(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            mock_so = p / "libapp.so"
            # Write a binary slice with SQLite CREATE TABLE
            mock_so.write_bytes(b"\x00" * 50 + b"CREATE TABLE `account` (`id` TEXT PRIMARY KEY, `title` TEXT)" + b"\x00" * 50)

            async def run_call():
                res = await self.server.call_tool("apkx_extract_sqlite_schema", {"target_path": str(p)})
                self.assertIn("account", str(res))

            asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.launch_app", return_value=True)
    def test_launch_app_tool(self, mock_launch, mock_ready, mock_ensured):
        async def run_call():
            res = await self.server.call_tool(
                "apkx_launch_app", {"package_name": "com.example.app", "restart": True}
            )
            self.assertIn("success", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.input_interact", return_value=True)
    def test_interact_tool(self, mock_interact, mock_ready, mock_ensured):
        async def run_call():
            res = await self.server.call_tool("apkx_interact", {"action": "back"})
            self.assertIn("success", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.dump_ui_hierarchy")
    @patch("apk_extractor.adb.ADBManager.get_screen_size", return_value=(720, 1600))
    def test_dump_ui_hierarchy_tool(self, mock_size, mock_dump, mock_ready, mock_ensured):
        mock_dump.return_value = [{"text": "Simpan", "bounds": [10, 10, 50, 50], "center": [30, 30]}]

        async def run_call():
            res = await self.server.call_tool("apkx_dump_ui_hierarchy", {})
            self.assertIn("Simpan", str(res))
            self.assertIn("720", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.ensure_device_awake")
    def test_ensure_device_awake_tool(self, mock_awake, mock_ready, mock_ensured):
        mock_awake.return_value = {"status": "ready", "screen_on": True, "locked": False}
        async def run_call():
            res = await self.server.call_tool("apkx_ensure_device_awake", {})
            self.assertIn("ready", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.get_screen_state")
    def test_get_current_screen_tool(self, mock_scr, mock_ready, mock_ensured):
        mock_scr.return_value = {"package_name": "com.test", "activity_name": ".MainActivity", "pid": 999}
        async def run_call():
            res = await self.server.call_tool("apkx_get_current_screen", {})
            self.assertIn("com.test", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.get_app_logs")
    def test_get_app_logs_tool(self, mock_logs, mock_ready, mock_ensured):
        mock_logs.return_value = {"package_name": "com.test", "logs": "FATAL EXCEPTION"}
        async def run_call():
            res = await self.server.call_tool("apkx_get_app_logs", {"package_name": "com.test"})
            self.assertIn("FATAL EXCEPTION", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.reset_app_data", return_value=True)
    def test_reset_app_data_tool(self, mock_reset, mock_ready, mock_ensured):
        async def run_call():
            res = await self.server.call_tool("apkx_reset_app_data", {"package_name": "com.test"})
            self.assertIn("success", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.open_deep_link", return_value=True)
    def test_open_deep_link_tool(self, mock_link, mock_ready, mock_ensured):
        async def run_call():
            res = await self.server.call_tool("apkx_open_deep_link", {"url": "app://test"})
            self.assertIn("success", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.toggle_night_mode", return_value=True)
    def test_toggle_night_mode_tool(self, mock_night, mock_ready, mock_ensured):
        async def run_call():
            res = await self.server.call_tool("apkx_toggle_night_mode", {"enable": True})
            self.assertIn("Dark Mode", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_devices_with_details", return_value=[])
    @patch("apk_extractor.adb.ADBManager.check_device_ready")
    def test_list_devices_no_device(self, mock_ready, mock_devs, mock_ensured):
        mock_ready.return_value = (
            False,
            "NO_DEVICE",
            {
                "message": "Tidak ada perangkat Android yang terdeteksi via ADB.",
                "troubleshooting": ["1. Sambungkan kabel USB."],
            },
        )
        async def run_call():
            res = await self.server.call_tool("apkx_list_devices", {})
            self.assertIn("not_ready", str(res))
            self.assertIn("NO_DEVICE", str(res))
            self.assertIn("kabel USB", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready")
    def test_tool_fails_gracefully_when_no_device(self, mock_ready, mock_ensured):
        mock_ready.return_value = (
            False,
            "NO_DEVICE",
            {
                "status": "error",
                "code": "NO_DEVICE",
                "message": "Tidak ada perangkat Android yang terdeteksi via ADB.",
                "troubleshooting": ["1. Sambungkan kabel USB."],
            },
        )
        async def run_call():
            # Test launch_app
            res_launch = await self.server.call_tool("apkx_launch_app", {"package_name": "com.test"})
            self.assertIn("NO_DEVICE", str(res_launch))
            self.assertIn("kabel USB", str(res_launch))

            # Test list_apps
            res_apps = await self.server.call_tool("apkx_list_apps", {})
            self.assertIn("NO_DEVICE", str(res_apps))

            # Test get_app_info
            res_info = await self.server.call_tool("apkx_get_app_info", {"package_name": "com.test"})
            self.assertIn("NO_DEVICE", str(res_info))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.install_apk")
    def test_install_apk_tool(self, mock_install, mock_ready, mock_ensured):
        mock_install.return_value = (
            True,
            "SUCCESS",
            {"status": "success", "message": "Aplikasi berhasil dipasang."},
        )
        async def run_call():
            res = await self.server.call_tool("apkx_install_apk", {"apk_path": "dummy.apk"})
            self.assertIn("success", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "mock_device"}))
    @patch("apk_extractor.adb.ADBManager.uninstall_app")
    def test_uninstall_app_tool(self, mock_uninstall, mock_ready, mock_ensured):
        mock_uninstall.return_value = (
            True,
            "SUCCESS",
            {"status": "success", "message": "Aplikasi berhasil dihapus."},
        )
        async def run_call():
            res = await self.server.call_tool("apkx_uninstall_app", {"package_name": "com.example.app"})
            self.assertIn("success", str(res))

        asyncio.run(run_call())


    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=False)
    def test_list_devices_adb_missing(self, mock_ensured):
        async def run_call():
            res = await self.server.call_tool("apkx_list_devices", {})
            self.assertIn("adb_not_found", str(res))
            self.assertIn("not_ready", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.android.settings", "com.whatsapp"])
    @patch("apk_extractor.app_names.resolve_apps")
    def test_list_apps_include_system_flag(self, mock_resolve, mock_list_pkgs, mock_ready, mock_ensured):
        mock_resolve.return_value = []
        async def run_call():
            await self.server.call_tool("apkx_list_apps", {"include_system_apps": True})
            mock_list_pkgs.assert_called_with(
                device_id=None,
                third_party_only=False,
                system_only=False,
                query=None,
            )

        asyncio.run(run_call())

    def test_get_endpoints_from_apk_file(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp_d:
            apk_path = Path(tmp_d) / "sample.apk"
            with zipfile.ZipFile(apk_path, "w") as zf:
                zf.writestr("classes.dex", b"data with https://api.sample.com/v1/auth endpoint")

            async def run_call():
                res = await self.server.call_tool("apkx_get_endpoints", {"target_path": str(apk_path)})
                self.assertIn("api.sample.com", str(res))

            asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.corrupt.app"])
    @patch("apk_extractor.app_names.resolve_apps")
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/com.corrupt.app/base.apk"])
    @patch("apk_extractor.adb.ADBManager.pull_file")
    def test_pull_and_extract_corrupt_apk_returns_error(
        self, mock_pull, mock_paths, mock_resolve, mock_pkgs, mock_ready, mock_ensured
    ):
        from apk_extractor.app_names import AppInfo
        mock_resolve.return_value = [AppInfo(app_name="CorruptApp", package_name="com.corrupt.app")]
        with tempfile.TemporaryDirectory() as tmp_d:
            def fake_pull(remote, local, device_id=None):
                Path(local).write_bytes(b"not a valid zip binary content")
            mock_pull.side_effect = fake_pull

            async def run_call():
                res = await self.server.call_tool("apkx_pull_and_extract", {
                    "query_or_package": "com.corrupt.app",
                    "output_dir": tmp_d,
                })
                self.assertIn("error", str(res))
                self.assertIn("rusak atau tidak lengkap", str(res))
                self.assertIn("INVALID_ARCHIVE", str(res))

            asyncio.run(run_call())

    def test_pull_and_extract_empty_query_returns_invalid_query(self):
        async def run_call():
            res = await self.server.call_tool("apkx_pull_and_extract", {
                "query_or_package": "   ",
            })
            self.assertIn("INVALID_QUERY", str(res))

        asyncio.run(run_call())

    def test_pull_and_extract_invalid_path_returns_error(self):
        async def run_call():
            res = await self.server.call_tool("apkx_pull_and_extract", {
                "query_or_package": "com.example.app",
                "output_dir": "../../evil_dir",
            })
            self.assertIn("INVALID_PATH", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(False, "DEVICE_NOT_READY", {"status": "error", "message": "No device"}))
    def test_pull_and_extract_device_not_ready(self, mock_ready, mock_ensured):
        async def run_call():
            res = await self.server.call_tool("apkx_pull_and_extract", {
                "query_or_package": "com.example.app",
            })
            self.assertIn("DEVICE_NOT_READY", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=[])
    @patch("apk_extractor.app_names.resolve_apps", return_value=[])
    def test_pull_and_extract_app_not_found(self, mock_resolve, mock_pkgs, mock_ready, mock_ensured):
        async def run_call():
            res = await self.server.call_tool("apkx_pull_and_extract", {
                "query_or_package": "com.nonexistent.app",
            })
            self.assertIn("APP_NOT_FOUND", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.found.app"])
    @patch("apk_extractor.app_names.resolve_apps")
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=[])
    def test_pull_and_extract_apk_not_found(self, mock_paths, mock_resolve, mock_pkgs, mock_ready, mock_ensured):
        from apk_extractor.app_names import AppInfo
        mock_resolve.return_value = [AppInfo(app_name="FoundApp", package_name="com.found.app")]
        async def run_call():
            res = await self.server.call_tool("apkx_pull_and_extract", {
                "query_or_package": "com.found.app",
            })
            self.assertIn("APK_NOT_FOUND", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.found.app"])
    @patch("apk_extractor.app_names.resolve_apps")
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("apk_extractor.packager.APKPackager.unpack")
    @patch("apk_extractor.packager.APKPackager.generate_analysis_summary")
    def test_pull_and_extract_success(self, mock_summary, mock_unpack, mock_extract, mock_paths, mock_resolve, mock_pkgs, mock_ready, mock_ensured):
        from apk_extractor.app_names import AppInfo
        mock_resolve.return_value = [AppInfo(app_name="FoundApp", package_name="com.found.app")]
        with tempfile.TemporaryDirectory() as tmp_d:
            out_p = Path(tmp_d) / "app.apk"
            out_p.touch()

            mock_res = MagicMock()
            mock_res.app_name = "FoundApp"
            mock_res.package_name = "com.found.app"
            mock_res.is_split = False
            mock_res.total_parts = 1
            mock_res.output_path = out_p
            mock_extract.return_value = mock_res
            mock_summary.return_value = {"framework": "Flutter", "total_urls": 5, "total_classes": 10}

            async def run_call():
                res = await self.server.call_tool("apkx_pull_and_extract", {
                    "query_or_package": "com.found.app",
                    "output_dir": tmp_d,
                })
                self.assertIn("success", str(res))
                self.assertIn("FoundApp", str(res))

            asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.found.app"])
    @patch("apk_extractor.app_names.resolve_apps")
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("apk_extractor.packager.APKPackager.unpack", side_effect=OSError("Disk full"))
    def test_pull_and_extract_io_error(self, mock_unpack, mock_extract, mock_paths, mock_resolve, mock_pkgs, mock_ready, mock_ensured):
        from apk_extractor.app_names import AppInfo
        mock_resolve.return_value = [AppInfo(app_name="FoundApp", package_name="com.found.app")]
        with tempfile.TemporaryDirectory() as tmp_d:
            out_p = Path(tmp_d) / "app.apk"
            out_p.touch()

            mock_res = MagicMock()
            mock_res.app_name = "FoundApp"
            mock_res.package_name = "com.found.app"
            mock_res.output_path = out_p
            mock_extract.return_value = mock_res

            async def run_call():
                res = await self.server.call_tool("apkx_pull_and_extract", {
                    "query_or_package": "com.found.app",
                    "output_dir": tmp_d,
                })
                self.assertIn("IO_ERROR", str(res))

            asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.found.app"])
    @patch("apk_extractor.app_names.resolve_apps")
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("apk_extractor.packager.APKPackager.unpack", side_effect=RuntimeError("Unexpected blow up"))
    def test_pull_and_extract_internal_error(self, mock_unpack, mock_extract, mock_paths, mock_resolve, mock_pkgs, mock_ready, mock_ensured):
        from apk_extractor.app_names import AppInfo
        mock_resolve.return_value = [AppInfo(app_name="FoundApp", package_name="com.found.app")]
        with tempfile.TemporaryDirectory() as tmp_d:
            out_p = Path(tmp_d) / "app.apk"
            out_p.touch()

            mock_res = MagicMock()
            mock_res.app_name = "FoundApp"
            mock_res.package_name = "com.found.app"
            mock_res.output_path = out_p
            mock_extract.return_value = mock_res

            async def run_call():
                res = await self.server.call_tool("apkx_pull_and_extract", {
                    "query_or_package": "com.found.app",
                    "output_dir": tmp_d,
                })
                self.assertIn("INTERNAL_ERROR", str(res))

            asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_devices_with_details", return_value=[{"serial": "DEV1", "status": "device"}])
    def test_list_devices_tool(self, mock_devs, mock_ensured):
        async def run_call():
            res = await self.server.call_tool("apkx_list_devices", {})
            self.assertIn("DEV1", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.pkg1"])
    @patch("apk_extractor.app_names.resolve_apps")
    def test_list_apps_tool(self, mock_resolve, mock_pkgs, mock_ready, mock_ensured):
        from apk_extractor.app_names import AppInfo
        mock_resolve.return_value = [AppInfo(app_name="PkgOne", package_name="com.pkg1")]
        async def run_call():
            res = await self.server.call_tool("apkx_list_apps", {})
            self.assertIn("com.pkg1", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.get_package_quick_info", return_value={"package_name": "com.pkg1", "version_name": "1.0"})
    def test_get_app_info_tool(self, mock_info, mock_ready, mock_ensured):
        async def run_call():
            res = await self.server.call_tool("apkx_get_app_info", {"package_name": "com.pkg1"})
            self.assertIn("com.pkg1", str(res))

        asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.take_screenshot", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_screen_size", return_value=(1080, 2400))
    def test_take_screenshot_tool(self, mock_size, mock_shot, mock_ready, mock_ensured):
        with tempfile.TemporaryDirectory() as tmp_d:
            screen_file = Path(tmp_d) / "screen.png"
            screen_file.write_bytes(b"image")

            async def run_call():
                res = await self.server.call_tool("apkx_take_screenshot", {"output_path": str(screen_file)})
                self.assertIn("success", str(res))

            asyncio.run(run_call())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.install_apk", return_value=(True, "SUCCESS", {"status": "success"}))
    def test_install_uninstall_tools(self, mock_install, mock_ready, mock_ensured):
        with tempfile.NamedTemporaryFile(suffix=".apk") as tmp:
            async def run_call():
                res = await self.server.call_tool("apkx_install_apk", {"apk_path": tmp.name})
                self.assertIn("success", str(res))

            asyncio.run(run_call())

        with patch("apk_extractor.adb.ADBManager.uninstall_app", return_value=(True, "SUCCESS", {"status": "success"})):
            async def run_uninstall():
                res = await self.server.call_tool("apkx_uninstall_app", {"package_name": "com.test"})
                self.assertIn("success", str(res))

            asyncio.run(run_uninstall())

    def test_class_skeleton_tool(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            # Test when class_skeleton.txt exists
            (p / "class_skeleton.txt").write_text("class TestClass {}", encoding="utf-8")
            async def run1():
                res = await self.server.call_tool("apkx_get_class_skeleton", {"target_path": str(p)})
                self.assertIn("TestClass", str(res))
            asyncio.run(run1())

            (p / "class_skeleton.txt").unlink()
            # Test fallback to extract_class_skeleton_from_dir
            with patch("apk_extractor.mcp_server.extract_class_skeleton_from_dir", return_value={"total_classes": 1, "app_classes": ["com.test.Foo"]}), \
                 patch("apk_extractor.mcp_server.format_skeleton_text", return_value="Formatted Skeleton"):
                async def run2():
                    res = await self.server.call_tool("apkx_get_class_skeleton", {"target_path": str(p)})
                    self.assertIn("Formatted Skeleton", str(res))
                asyncio.run(run2())

            # Test invalid path (non-directory)
            async def run3():
                res = await self.server.call_tool("apkx_get_class_skeleton", {"target_path": str(p / "nonexistent")})
                self.assertIn("Path tidak valid", str(res))
            asyncio.run(run3())

    def test_inspect_class_tool(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            # 1. Non-existent APK
            async def run_nonexistent():
                res = await self.server.call_tool("apkx_inspect_class", {"target_apk": str(Path(tmp_d) / "none.apk"), "class_name": "com.test.Main"})
                self.assertIn("tidak ditemukan", str(res))
            asyncio.run(run_nonexistent())

            real_apk = Path(tmp_d) / "app.apk"
            real_apk.touch()

            # 2. JADX unavailable
            with patch("apk_extractor.jadx.JADXManager.ensure_installed", return_value=False):
                async def run_no_jadx():
                    res = await self.server.call_tool("apkx_inspect_class", {"target_apk": str(real_apk), "class_name": "com.test.Main"})
                    self.assertIn("Engine JADX belum terpasang", str(res))
                asyncio.run(run_no_jadx())

            # 3. Success decompile
            with patch("apk_extractor.jadx.JADXManager.ensure_installed", return_value=True), \
                 patch("apk_extractor.jadx.JADXManager.decompile_class", return_value="public class Main {}"):
                async def run_success():
                    res = await self.server.call_tool("apkx_inspect_class", {"target_apk": str(real_apk), "class_name": "com.test.Main"})
                    self.assertIn("public class Main", str(res))
                asyncio.run(run_success())

            # 4. Failure decompile
            with patch("apk_extractor.jadx.JADXManager.ensure_installed", return_value=True), \
                 patch("apk_extractor.jadx.JADXManager.decompile_class", return_value=None):
                async def run_fail():
                    res = await self.server.call_tool("apkx_inspect_class", {"target_apk": str(real_apk), "class_name": "com.test.Main"})
                    self.assertIn("Gagal mendekomposisi kelas", str(res))
                asyncio.run(run_fail())

    def test_find_classes_tool_extended(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            # 1. Non-directory
            async def run1():
                res = await self.server.call_tool("apkx_find_classes", {"target_path": str(p / "none"), "query": "auth"})
                self.assertIn("bukan direktori yang valid", str(res))
            asyncio.run(run1())

            # 2. Empty query
            async def run2():
                res = await self.server.call_tool("apkx_find_classes", {"target_path": str(p), "query": "  "})
                self.assertIn("tidak boleh kosong", str(res))
            asyncio.run(run2())

            # 3. Corrupt skeleton json fallback
            (p / "class_skeleton.json").write_text("{corrupt-json}", encoding="utf-8")
            with patch("apk_extractor.mcp_server.extract_class_skeleton_from_dir", return_value={"app_classes": ["com.test.AuthService"], "all_classes": []}):
                async def run3():
                    res = await self.server.call_tool("apkx_find_classes", {"target_path": str(p), "query": "auth"})
                    self.assertIn("AuthService", str(res))
                asyncio.run(run3())

    def test_search_endpoints_tool(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            # 1. Non-directory
            async def run1():
                res = await self.server.call_tool("apkx_search_endpoints", {"target_path": str(p / "none")})
                self.assertIn("bukan direktori yang valid", str(res))
            asyncio.run(run1())

            # 2. Endpoints file missing, fallback
            with patch("apk_extractor.mcp_server.extract_endpoints_from_dir", return_value={"domains": ["api.example.com"], "all_endpoints": ["https://api.example.com/v1"]}):
                async def run2():
                    res = await self.server.call_tool("apkx_search_endpoints", {"target_path": str(p)})
                    self.assertIn("api.example.com", str(res))
                asyncio.run(run2())

            # 3. With query
            (p / "endpoints.json").write_text('{"domains": ["api.example.com", "cdn.other.com"], "all_endpoints": ["https://api.example.com/login"]}', encoding="utf-8")
            async def run3():
                res = await self.server.call_tool("apkx_search_endpoints", {"target_path": str(p), "query": "login"})
                self.assertIn("https://api.example.com/login", str(res))
            asyncio.run(run3())

    def test_extract_sqlite_schema_tool(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            p = Path(tmp_d)
            # 1. Non-existent path
            async def run1():
                res = await self.server.call_tool("apkx_extract_sqlite_schema", {"target_path": str(p / "none")})
                self.assertIn("tidak ditemukan", str(res))
            asyncio.run(run1())

            # 2. Existing path
            with patch("apk_extractor.mcp_server.extract_sqlite_schema_from_dir", return_value={"total_tables": 1, "tables": {"users": ["id"]}}):
                async def run2():
                    res = await self.server.call_tool("apkx_extract_sqlite_schema", {"target_path": str(p)})
                    self.assertIn("users", str(res))
                asyncio.run(run2())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(False, "DEVICE_NOT_READY", {"status": "error", "message": "Device offline"}))
    def test_tools_device_not_ready(self, mock_ready, mock_ensured):
        async def run_not_ready():
            res1 = await self.server.call_tool("apkx_take_screenshot", {})
            self.assertIn("offline", str(res1))
            res2 = await self.server.call_tool("apkx_dump_ui_hierarchy", {})
            self.assertIn("offline", str(res2))
            res3 = await self.server.call_tool("apkx_interact", {"action": "tap", "x": 100, "y": 200})
            self.assertIn("offline", str(res3))
            res4 = await self.server.call_tool("apkx_get_current_screen", {})
            self.assertIn("offline", str(res4))
            res5 = await self.server.call_tool("apkx_open_deep_link", {"url": "https://test.com"})
            self.assertIn("offline", str(res5))
            res6 = await self.server.call_tool("apkx_toggle_night_mode", {"enable": True})
            self.assertIn("offline", str(res6))
            res7 = await self.server.call_tool("apkx_install_apk", {"apk_path": "/tmp/a.apk"})
            self.assertIn("offline", str(res7))
            res8 = await self.server.call_tool("apkx_uninstall_app", {"package_name": "com.test"})
            self.assertIn("offline", str(res8))
            res9 = await self.server.call_tool("apkx_launch_app", {"package_name": "com.test"})
            self.assertIn("offline", str(res9))
            res10 = await self.server.call_tool("apkx_reset_app_data", {"package_name": "com.test"})
            self.assertIn("offline", str(res10))
            res11 = await self.server.call_tool("apkx_get_app_logs", {"package_name": "com.test"})
            self.assertIn("offline", str(res11))
            res12 = await self.server.call_tool("apkx_diagnostics", {"action": "getprop"})
            self.assertIn("offline", str(res12))
            res13 = await self.server.call_tool("apkx_force_stop_app", {"package_name": "com.test"})
            self.assertIn("offline", str(res13))
            res14 = await self.server.call_tool("apkx_find_ui_element", {"query": "Save"})
            self.assertIn("offline", str(res14))
            res15 = await self.server.call_tool("apkx_verify_install", {"package_name": "com.test"})
            self.assertIn("offline", str(res15))
            res16 = await self.server.call_tool("apkx_grant_permission", {"package_name": "com.test", "permission": "CAMERA"})
            self.assertIn("offline", str(res16))
        asyncio.run(run_not_ready())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.list_packages")
    @patch("apk_extractor.app_names.resolve_apps")
    def test_list_apps_with_query(self, mock_resolve, mock_list, mock_ready, mock_ensured):
        from apk_extractor.app_names import AppInfo
        mock_list.return_value = ["com.example.expense"]
        mock_resolve.return_value = [AppInfo(package_name="com.example.expense", app_name="Expense Tracker")]

        async def run_list():
            # Success with query
            raw_res = await self.server.call_tool("apkx_list_apps", {"query": "expense"})
            res = self._parse_res(raw_res)
            self.assertIsInstance(res, list)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["package_name"], "com.example.expense")
            mock_list.assert_called_with(device_id=None, third_party_only=True, system_only=False, query="expense")

            # Error with invalid query -> returns [error_dict]
            mock_list.side_effect = ValueError("query filter tidak valid")
            raw_err = await self.server.call_tool("apkx_list_apps", {"query": "invalid;q"})
            res_err = self._parse_res(raw_err)
            self.assertIsInstance(res_err, list)
            self.assertEqual(res_err[0]["code"], "INVALID_ARGUMENT")

        asyncio.run(run_list())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.get_screen_state")
    def test_get_current_screen_with_expected(self, mock_state, mock_ready, mock_ensured):
        mock_state.return_value = {
            "status": "success",
            "code": "OK",
            "package_name": "com.example.app",
            "activity_name": ".MainActivity",
            "is_target_foreground": True,
            "is_overlay_active": False,
        }

        async def run_screen():
            raw_res = await self.server.call_tool("apkx_get_current_screen", {"expected_package": "com.example.app"})
            res = self._parse_res(raw_res)
            self.assertIsInstance(res, dict)
            self.assertTrue(res["is_target_foreground"])
            mock_state.assert_called_with(expected_package="com.example.app", device_id=None)

        asyncio.run(run_screen())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.input_interact")
    def test_interact_new_actions(self, mock_interact, mock_ready, mock_ensured):
        mock_interact.return_value = True

        async def run_interact():
            # long_press
            res_lp = self._parse_res(await self.server.call_tool("apkx_interact", {"action": "long_press", "x": 100, "y": 200, "duration_ms": 1500}))
            self.assertEqual(res_lp["status"], "success")
            mock_interact.assert_called_with(
                action="long_press", x=100, y=200, keycode=None, text=None, swipe_coords=None, duration_ms=1500, count=None, device_id=None
            )

            # backspace
            res_bs = self._parse_res(await self.server.call_tool("apkx_interact", {"action": "backspace", "count": 3}))
            self.assertEqual(res_bs["status"], "success")

            # recent_apps
            res_ra = self._parse_res(await self.server.call_tool("apkx_interact", {"action": "recent_apps"}))
            self.assertEqual(res_ra["status"], "success")

        asyncio.run(run_interact())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.install_apk")
    def test_install_apk_enriched_and_defaults(self, mock_install, mock_ready, mock_ensured):
        mock_install.return_value = (
            True,
            "SUCCESS",
            {
                "status": "success",
                "code": "OK",
                "package_name": "com.test.release",
                "version_name": "1.0.0",
                "version_code": "1",
                "debuggable": False,
                "verification": "verified",
            },
        )

        async def run_install():
            raw_res = await self.server.call_tool("apkx_install_apk", {"apk_path": "release.apk"})
            res = self._parse_res(raw_res)
            self.assertIsInstance(res, dict)
            self.assertEqual(res["code"], "OK")
            self.assertEqual(res["package_name"], "com.test.release")
            self.assertFalse(res["debuggable"])
            mock_install.assert_called_with(
                apk_path="release.apk",
                reinstall=True,
                grant_permissions=False,
                allow_downgrade=False,
                verify=True,
                device_id=None,
            )

        asyncio.run(run_install())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.diagnostics")
    def test_diagnostics_tool(self, mock_diag, mock_ready, mock_ensured):
        mock_diag.return_value = {
            "status": "success",
            "code": "OK",
            "action": "getprop",
            "result": {"properties": {"ro.product.model": "Pixel"}},
            "untrusted_content": True,
        }

        async def run_diag():
            res = self._parse_res(await self.server.call_tool("apkx_diagnostics", {"action": "getprop"}))
            self.assertEqual(res["status"], "success")
            self.assertEqual(res["code"], "OK")

            # Error boundary tests
            mock_diag.side_effect = TimeoutError()
            res_to = self._parse_res(await self.server.call_tool("apkx_diagnostics", {"action": "getprop"}))
            self.assertEqual(res_to["code"], "TIMEOUT")

            mock_diag.side_effect = ValueError("Aksi diagnostik tidak valid")
            res_val = self._parse_res(await self.server.call_tool("apkx_diagnostics", {"action": "bad_act"}))
            self.assertEqual(res_val["code"], "INVALID_ARGUMENT")

            mock_diag.side_effect = ADBError("ADB communication failed")
            res_adb = self._parse_res(await self.server.call_tool("apkx_diagnostics", {"action": "getprop"}))
            self.assertEqual(res_adb["code"], "ADB_ERROR")

            mock_diag.side_effect = Exception("General crash")
            res_unk = self._parse_res(await self.server.call_tool("apkx_diagnostics", {"action": "getprop"}))
            self.assertEqual(res_unk["code"], "UNKNOWN")

        asyncio.run(run_diag())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.force_stop_app")
    def test_force_stop_app_tool(self, mock_stop, mock_ready, mock_ensured):
        mock_stop.return_value = {"status": "success", "code": "OK", "is_running": False}

        async def run_stop():
            res = self._parse_res(await self.server.call_tool("apkx_force_stop_app", {"package_name": "com.test.app"}))
            self.assertEqual(res["status"], "success")

            mock_stop.side_effect = ValueError("Package invalid")
            res_err = self._parse_res(await self.server.call_tool("apkx_force_stop_app", {"package_name": "invalid;"}))
            self.assertEqual(res_err["code"], "INVALID_ARGUMENT")

        asyncio.run(run_stop())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.find_ui_element")
    def test_find_ui_element_tool(self, mock_find, mock_ready, mock_ensured):
        mock_find.return_value = {"status": "success", "code": "OK", "matches": [{"text": "Save"}]}

        async def run_find():
            res = self._parse_res(await self.server.call_tool("apkx_find_ui_element", {"query": "Save"}))
            self.assertEqual(res["status"], "success")

            mock_find.return_value = {"status": "error", "code": "NOT_FOUND", "matches": []}
            res_nf = self._parse_res(await self.server.call_tool("apkx_find_ui_element", {"query": "Save"}))
            self.assertEqual(res_nf["code"], "NOT_FOUND")

            mock_find.return_value = {"status": "error", "code": "UI_DUMP_FAILED", "matches": []}
            res_fail = self._parse_res(await self.server.call_tool("apkx_find_ui_element", {"query": "Save"}))
            self.assertEqual(res_fail["code"], "UI_DUMP_FAILED")

        asyncio.run(run_find())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.verify_installed_package")
    def test_verify_install_tool(self, mock_verify, mock_ready, mock_ensured):
        mock_verify.return_value = {"status": "success", "code": "OK", "verified": True, "debuggable": False}

        async def run_v():
            res = self._parse_res(await self.server.call_tool("apkx_verify_install", {"package_name": "com.test.app", "expect_release": True}))
            self.assertTrue(res["verified"])
            self.assertFalse(res["debuggable"])

            mock_verify.return_value = {"status": "error", "code": "DEBUGGABLE_MISMATCH", "verified": False}
            res_mismatch = self._parse_res(await self.server.call_tool("apkx_verify_install", {"package_name": "com.test.app", "expect_release": True}))
            self.assertEqual(res_mismatch["code"], "DEBUGGABLE_MISMATCH")

        asyncio.run(run_v())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.grant_runtime_permission")
    def test_grant_permission_tool(self, mock_grant, mock_ready, mock_ensured):
        mock_grant.return_value = {"status": "success", "code": "OK", "granted": True}

        async def run_gp():
            res = self._parse_res(await self.server.call_tool("apkx_grant_permission", {"package_name": "com.test.app", "permission": "CAMERA"}))
            self.assertEqual(res["code"], "OK")

            mock_grant.side_effect = ValueError("Invalid permission")
            res_inv = self._parse_res(await self.server.call_tool("apkx_grant_permission", {"package_name": "com.test.app", "permission": ";bad"}))
            self.assertEqual(res_inv["code"], "INVALID_ARGUMENT")

        asyncio.run(run_gp())

    @patch("apk_extractor.adb.ADBManager.ensure_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {}))
    @patch("apk_extractor.adb.ADBManager.take_screenshot", return_value=False)
    @patch("apk_extractor.adb.ADBManager.get_screen_size", return_value=(1080, 2400))
    def test_take_screenshot_failure(self, mock_size, mock_shot, mock_ready, mock_ensured):
        async def run_fail():
            res = await self.server.call_tool("apkx_take_screenshot", {"output_path": "/tmp/nonexistent/screen.png"})
            self.assertIn("Gagal mengambil tangkapan layar", str(res))
        asyncio.run(run_fail())

    @patch("apk_extractor.mcp_server.create_mcp_server")
    def test_run_mcp_server_entrypoint(self, mock_create):
        from apk_extractor.mcp_server import run_mcp_server
        mock_srv = MagicMock()
        mock_create.return_value = mock_srv
        run_mcp_server(transport="stdio")
        mock_srv.run.assert_called_once_with(transport="stdio")


if __name__ == "__main__":
    unittest.main()
