import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apk_extractor.mcp_server import create_mcp_server


class TestMCPServer(unittest.TestCase):
    def setUp(self):
        self.server = create_mcp_server()

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
            ]
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
    @patch("apk_extractor.adb.ADBManager.get_current_screen")
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

            asyncio.run(run_call())


if __name__ == "__main__":
    unittest.main()
