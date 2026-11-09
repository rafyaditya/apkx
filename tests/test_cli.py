import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from apk_extractor import __version__
from apk_extractor.cli import app
from apk_extractor.adb import ADBError, ADBManager
from apk_extractor.app_names import AppInfo


class TestCLIFlags(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_version_flag(self):
        result = self.runner.invoke(app, ["--version"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(__version__, result.output)

    def test_version_flag_short(self):
        result = self.runner.invoke(app, ["-v"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn(__version__, result.output)

    def test_conflicting_all_and_system_flags(self):
        result = self.runner.invoke(app, ["--all", "--system"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("tidak dapat digunakan bersamaan", result.output)

    def test_conflicting_action_flags_apk_and_extract(self):
        result = self.runner.invoke(app, ["-k", "-x"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Hanya boleh memilih satu", result.output)

    def test_conflicting_action_flags_apk_and_both(self):
        result = self.runner.invoke(app, ["--apk-only", "--both"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Hanya boleh memilih satu", result.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_devices_with_details")
    def test_devices_json(self, mock_details, mock_installed):
        mock_details.return_value = [
            {"serial": "TEST1234", "brand": "Samsung", "model": "Galaxy", "android_version": "Android 13", "status": "device"}
        ]
        result = self.runner.invoke(app, ["--devices", "--json"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["serial"], "TEST1234")

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices")
    @patch("apk_extractor.adb.ADBManager.get_device_details")
    @patch("apk_extractor.adb.ADBManager.list_packages")
    def test_list_json(self, mock_list_pkgs, mock_dev_details, mock_conn, mock_inst):
        mock_conn.return_value = [("DEV1", "device")]
        mock_dev_details.return_value = {"serial": "DEV1", "status": "device", "brand": "B", "model": "M"}
        mock_list_pkgs.return_value = ["com.whatsapp"]

        result = self.runner.invoke(app, ["--list", "--json"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["package_name"], "com.whatsapp")

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices")
    @patch("apk_extractor.adb.ADBManager.get_device_details")
    @patch("apk_extractor.adb.ADBManager.list_packages")
    @patch("apk_extractor.adb.ADBManager.get_package_quick_info")
    def test_info_json(self, mock_quick_info, mock_list_pkgs, mock_dev_details, mock_conn, mock_inst):
        mock_conn.return_value = [("DEV1", "device")]
        mock_dev_details.return_value = {"serial": "DEV1", "status": "device", "brand": "B", "model": "M"}
        mock_list_pkgs.return_value = ["com.whatsapp"]
        mock_quick_info.return_value = {
            "package_name": "com.whatsapp",
            "version_name": "2.23.1",
            "version_code": "456",
            "target_sdk": "34",
            "min_sdk": "21",
            "apk_paths": ["/data/app/com.whatsapp/base.apk"],
            "apk_format": "Single APK",
            "permissions": ["INTERNET"],
        }

        result = self.runner.invoke(app, ["whatsapp", "--info", "--json"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["package_name"], "com.whatsapp")
        self.assertEqual(data["version_name"], "2.23.1")
        self.assertEqual(data["target_sdk"], "34")

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices")
    @patch("apk_extractor.adb.ADBManager.get_device_details")
    @patch("apk_extractor.adb.ADBManager.list_packages")
    def test_root_json_no_query(self, mock_list_pkgs, mock_dev_details, mock_conn, mock_inst):
        mock_conn.return_value = [("DEV1", "device")]
        mock_dev_details.return_value = {"serial": "DEV1", "status": "device", "brand": "B", "model": "M"}
        mock_list_pkgs.return_value = ["com.whatsapp", "com.facebook.katana"]

        result = self.runner.invoke(app, ["--json"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["package_name"], "com.facebook.katana")
        self.assertEqual(data[1]["package_name"], "com.whatsapp")


class TestADBNewFeatures(unittest.TestCase):
    @patch("subprocess.run")
    def test_list_packages_system_only(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "package:com.android.settings\npackage:com.android.systemui\n"
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        pkgs = manager.list_packages(system_only=True)
        self.assertEqual(pkgs, ["com.android.settings", "com.android.systemui"])

        cmd = mock_run.call_args[0][0]
        self.assertIn("-s", cmd)
        self.assertNotIn("-3", cmd)

    @patch("subprocess.run")
    def test_get_package_recent_order(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = (
            "/data/app/~~h1==/com.whatsapp-h2==\n"
            "/data/app/com.instagram.android-1\n"
            "/data/app/~~random==\n"
        )
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        order = manager.get_package_recent_order()
        self.assertEqual(order, ["com.whatsapp", "com.instagram.android"])

    @patch("subprocess.run")
    def test_get_package_quick_info(self, mock_run):
        path_proc = MagicMock()
        path_proc.returncode = 0
        path_proc.stdout = "package:/data/app/com.test.app/base.apk\npackage:/data/app/com.test.app/split_config.arm64_v8a.apk\n"

        dumpsys_proc = MagicMock()
        dumpsys_proc.returncode = 0
        dumpsys_proc.stdout = """
            versionName=2.4.1
            versionCode=120 minSdk=21 targetSdk=34
            firstInstallTime=2024-01-01 10:00:00
            lastUpdateTime=2024-05-15 14:30:00
            android.permission.INTERNET: granted=true
            android.permission.CAMERA: granted=true
        """
        mock_run.side_effect = [path_proc, dumpsys_proc]

        manager = ADBManager(adb_path="mock_adb")
        info = manager.get_package_quick_info("com.test.app")

        self.assertEqual(info["package_name"], "com.test.app")
        self.assertEqual(info["version_name"], "2.4.1")
        self.assertEqual(info["version_code"], "120")
        self.assertEqual(info["target_sdk"], "34")
        self.assertEqual(info["min_sdk"], "21")
        self.assertIn("Split APK", info["apk_format"])
        self.assertIn("INTERNET", info["permissions"])
        self.assertIn("CAMERA", info["permissions"])


class TestSafeExtract(unittest.TestCase):
    def test_windows_reserved_device_names_sanitization(self):
        import io
        import tempfile
        import zipfile
        from apk_extractor.packager import safe_extract_zip, sanitize_archive_member_path

        # Test sanitize member path directly
        self.assertEqual(sanitize_archive_member_path("res/prn.xml").name, "_prn.xml")
        self.assertEqual(sanitize_archive_member_path("res/con.xml").name, "_con.xml")
        self.assertEqual(sanitize_archive_member_path("res/aux.png").name, "_aux.png")
        self.assertEqual(sanitize_archive_member_path("res/normal.xml").name, "normal.xml")

        # Test zip extraction
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w") as zf:
            zf.writestr("res/prn.xml", b"<xml>test prn</xml>")
            zf.writestr("res/con.xml", b"<xml>test con</xml>")
            zf.writestr("normal.txt", b"hello world")

        bio.seek(0)
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            with zipfile.ZipFile(bio, "r") as zf:
                count = safe_extract_zip(zf, tmp_path)

            self.assertEqual(count, 3)
            self.assertTrue((tmp_path / "res" / "_prn.xml").exists())
            self.assertTrue((tmp_path / "res" / "_con.xml").exists())
            self.assertTrue((tmp_path / "normal.txt").exists())


class TestCLISubcommands(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "DEV1"}))
    @patch("apk_extractor.adb.ADBManager.take_screenshot", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_screen_size", return_value=(1080, 2400))
    def test_cli_screenshot(self, mock_size, mock_shot, mock_ready, mock_inst):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            result = self.runner.invoke(app, ["screenshot", "-o", tmp.name, "--json"])
            self.assertEqual(result.exit_code, 0)
            data = json.loads(result.output)
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["screen_width"], 1080)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    def test_cli_install_missing_target(self, mock_inst):
        result = self.runner.invoke(app, ["install"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("memerlukan path berkas", result.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "DEV1"}))
    @patch("apk_extractor.adb.ADBManager.install_apk")
    def test_cli_install_success(self, mock_install, mock_ready, mock_inst):
        mock_install.return_value = (True, "SUCCESS", {"status": "success", "message": "Berhasil dipasang"})
        result = self.runner.invoke(app, ["install", "app.apk", "--json"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "success")

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "DEV1"}))
    @patch("apk_extractor.adb.ADBManager.uninstall_app")
    def test_cli_uninstall_success(self, mock_uninstall, mock_ready, mock_inst):
        mock_uninstall.return_value = (True, "SUCCESS", {"status": "success", "message": "Berhasil dihapus"})
        result = self.runner.invoke(app, ["uninstall", "com.example.app", "--json"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "success")

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "DEV1"}))
    @patch("apk_extractor.adb.ADBManager.dump_ui_hierarchy", return_value=[{"text": "Simpan", "center": [100, 200]}])
    @patch("apk_extractor.adb.ADBManager.get_screen_size", return_value=(720, 1600))
    def test_cli_dump_ui(self, mock_size, mock_dump, mock_ready, mock_inst):
        result = self.runner.invoke(app, ["dump-ui", "--json"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["total_elements"], 1)
        self.assertEqual(data["elements"][0]["text"], "Simpan")

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "DEV1"}))
    @patch("apk_extractor.adb.ADBManager.get_app_logs", return_value={"package_name": "com.test", "pid": 123, "logs": "FATAL", "has_crash_indicator": True, "total_lines": 1})
    def test_cli_logs(self, mock_logs, mock_ready, mock_inst):
        result = self.runner.invoke(app, ["logs", "com.test", "--json"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["package_name"], "com.test")
        self.assertTrue(data["has_crash_indicator"])

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "DEV1"}))
    @patch("apk_extractor.adb.ADBManager.ensure_device_awake", return_value={"status": "ready", "screen_on": True, "locked": False, "message": "Layar aktif"})
    def test_cli_wake(self, mock_wake, mock_ready, mock_inst):
        result = self.runner.invoke(app, ["wake", "--json"])
        self.assertEqual(result.exit_code, 0)
        data = json.loads(result.output)
        self.assertEqual(data["status"], "ready")


    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready", return_value=(True, "READY", {"serial": "DEV1"}))
    @patch("apk_extractor.adb.ADBManager.take_screenshot")
    @patch("apk_extractor.adb.ADBManager.get_screen_size", return_value=(1080, 2400))
    def test_cli_screenshot_default_path(self, mock_size, mock_take, mock_ready, mock_inst):
        with tempfile.TemporaryDirectory() as tmp_d:
            target_out = Path(tmp_d) / "screenshots"
            def fake_take(out_path, device_id=None):
                out_path.write_bytes(b"fake_png_data")
                return True
            mock_take.side_effect = fake_take
            result = self.runner.invoke(app, ["screenshot", "-o", str(target_out), "--json"])
            self.assertEqual(result.exit_code, 0)
            data = json.loads(result.output)
            self.assertEqual(data["status"], "success")
            self.assertTrue(data["path"].endswith("screen.png"))

    @patch("apk_extractor.mcp_server.run_mcp_server")
    def test_cli_serve_clean_exit(self, mock_run_mcp):
        mock_run_mcp.return_value = None
        result = self.runner.invoke(app, ["serve"])
        self.assertEqual(result.exit_code, 0)

    @patch("apk_extractor.setup_mcp.install_mcp_to_all_clients")
    def test_cli_setup(self, mock_install):
        mock_install.return_value = [
            {"client": "Claude", "status": "success", "path": "/path/claude"},
            {"client": "Cursor", "status": "failed", "error": "file not found"},
        ]
        result = self.runner.invoke(app, ["setup"])
        self.assertEqual(result.exit_code, 0)
        self.assertIn("Claude", result.output)
        self.assertIn("Cursor", result.output)

    @patch("apk_extractor.updater.run_updater")
    def test_cli_update(self, mock_updater):
        mock_updater.return_value = 0
        result = self.runner.invoke(app, ["update"])
        self.assertEqual(result.exit_code, 0)
        mock_updater.assert_called_with(check_only=False, as_json=False)

        result_check = self.runner.invoke(app, ["--check"])
        self.assertEqual(result_check.exit_code, 0)
        mock_updater.assert_called_with(check_only=True, as_json=False)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=False)
    @patch("apk_extractor.adb.ADBManager.ensure_installed")
    def test_cli_adb_install_flow(self, mock_ensure, mock_inst):
        mock_ensure.return_value = False
        result = self.runner.invoke(app, ["devices", "--json"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("Gagal mengunduh atau menginisialisasi ADB", result.output)

        mock_ensure.return_value = True
        with patch("apk_extractor.adb.ADBManager.get_devices_with_details", return_value=[]):
            result_ok = self.runner.invoke(app, ["devices"])
            self.assertEqual(result_ok.exit_code, 0)


class TestCLIOptionErrors(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_typer_bad_option_device(self):
        with self.assertRaises(SystemExit) as ctx:
            app(["-d"])
        self.assertEqual(ctx.exception.code, 2)

    def test_typer_bad_option_output(self):
        with self.assertRaises(SystemExit) as ctx:
            app(["-o"])
        self.assertEqual(ctx.exception.code, 2)

    def test_typer_no_such_option(self):
        with self.assertRaises(SystemExit) as ctx:
            app(["--completely-invalid-opt-1234"])
        self.assertEqual(ctx.exception.code, 2)

    def test_verbose_flag(self):
        with patch("apk_extractor.adb.ADBManager.is_installed", return_value=True), \
             patch("apk_extractor.adb.ADBManager.get_devices_with_details", return_value=[]):
            result = self.runner.invoke(app, ["--verbose", "devices"])
            self.assertEqual(result.exit_code, 0)


class TestCLIExtendedSubcommands(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_devices_with_details")
    def test_devices_table_and_error(self, mock_details, mock_inst):
        # Empty list (non-json)
        mock_details.return_value = []
        res = self.runner.invoke(app, ["devices"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Tidak ada perangkat", res.output)

        # Has devices
        mock_details.return_value = [
            {"serial": "DEV1", "status": "device", "brand": "Google", "model": "Pixel", "android_version": "14"}
        ]
        res = self.runner.invoke(app, ["devices"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("DEV1", res.output)

        # ADBError
        mock_details.side_effect = ADBError("ADB Daemon died")
        res = self.runner.invoke(app, ["devices", "--json"])
        self.assertEqual(res.exit_code, 1)
        self.assertIn("ADB Daemon died", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready")
    def test_screenshot_error_cases(self, mock_ready, mock_inst):
        # Device not ready
        mock_ready.return_value = (False, "UNAUTH", {"status": "error", "message": "Perlu izin HP"})
        res = self.runner.invoke(app, ["screenshot", "--json"])
        self.assertEqual(res.exit_code, 1)
        self.assertIn("Perlu izin HP", res.output)

        # Device ready, but screenshot fails
        mock_ready.return_value = (True, "READY", {})
        with patch("apk_extractor.adb.ADBManager.take_screenshot", return_value=False), \
             patch("apk_extractor.adb.ADBManager.get_screen_size", return_value=(1080, 2400)):
            res = self.runner.invoke(app, ["screenshot", "--json"])
            self.assertEqual(res.exit_code, 1)
            self.assertIn("Gagal mengambil screenshot", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready")
    def test_install_uninstall_error_cases(self, mock_ready, mock_inst):
        # Missing targets
        res = self.runner.invoke(app, ["install"])
        self.assertEqual(res.exit_code, 2)
        res = self.runner.invoke(app, ["uninstall"])
        self.assertEqual(res.exit_code, 2)

        # Device not ready
        mock_ready.return_value = (False, "OFFLINE", {"status": "error", "message": "Perangkat offline"})
        res = self.runner.invoke(app, ["install", "app.apk", "--json"])
        self.assertEqual(res.exit_code, 1)
        res = self.runner.invoke(app, ["uninstall", "com.pkg", "--json"])
        self.assertEqual(res.exit_code, 1)

        # Install failure
        mock_ready.return_value = (True, "READY", {})
        with patch("apk_extractor.adb.ADBManager.install_apk", return_value=(False, "FAIL", {"status": "error", "message": "INSTALL_FAILED"})):
            res = self.runner.invoke(app, ["install", "app.apk"])
            self.assertEqual(res.exit_code, 1)
            self.assertIn("INSTALL_FAILED", res.output)

        # Uninstall failure
        with patch("apk_extractor.adb.ADBManager.uninstall_app", return_value=(False, "FAIL", {"status": "error", "message": "DELETE_FAILED"})):
            res = self.runner.invoke(app, ["uninstall", "com.pkg"])
            self.assertEqual(res.exit_code, 1)
            self.assertIn("DELETE_FAILED", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready")
    def test_dump_ui_and_logs(self, mock_ready, mock_inst):
        mock_ready.return_value = (True, "READY", {})

        # Dump UI rich table
        elements = [{"text": f"Item {i}", "resource_id": f"id/item_{i}", "center": [10, 20], "class": "android.widget.TextView"} for i in range(40)]
        with patch("apk_extractor.adb.ADBManager.dump_ui_hierarchy", return_value=elements), \
             patch("apk_extractor.adb.ADBManager.get_screen_size", return_value=(1080, 2400)):
            res = self.runner.invoke(app, ["dump-ui"])
            self.assertEqual(res.exit_code, 0)
            self.assertIn("Hierarki Elemen UI Layar Aktif", res.output)

        # Logs missing target
        res = self.runner.invoke(app, ["logs"])
        self.assertEqual(res.exit_code, 2)

        # Logs rich text
        with patch("apk_extractor.adb.ADBManager.get_app_logs", return_value={"package_name": "com.test", "pid": "1234", "logs": "Some crash trace", "has_crash_indicator": True, "total_lines": 1}):
            res = self.runner.invoke(app, ["logs", "com.test"])
            self.assertEqual(res.exit_code, 0)
            self.assertIn("Logcat Error Terfilter", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.check_device_ready")
    def test_wake(self, mock_ready, mock_inst):
        mock_ready.return_value = (True, "READY", {})

        with patch("apk_extractor.adb.ADBManager.ensure_device_awake", return_value={"status": "ready", "message": "Layar aktif"}):
            res = self.runner.invoke(app, ["wake"])
            self.assertEqual(res.exit_code, 0)
            self.assertIn("Layar aktif", res.output)

        with patch("apk_extractor.adb.ADBManager.ensure_device_awake", return_value={"status": "locked", "message": "Layar terkunci"}):
            res = self.runner.invoke(app, ["wake"])
            self.assertEqual(res.exit_code, 1)


class TestCLIProcessSingleDeviceFlows(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices")
    def test_device_connection_errors(self, mock_conn, mock_inst):
        # ADBError
        mock_conn.side_effect = ADBError("Connection refused")
        res = self.runner.invoke(app, ["--json"])
        self.assertEqual(res.exit_code, 1)
        self.assertIn("Connection refused", res.output)

        # No devices
        mock_conn.side_effect = None
        mock_conn.return_value = []
        res = self.runner.invoke(app, ["--json"])
        self.assertEqual(res.exit_code, 1)
        self.assertIn("Tidak ada perangkat", res.output)

        # Unauthorized
        mock_conn.return_value = [("DEV1", "unauthorized")]
        res = self.runner.invoke(app, ["--json"])
        self.assertEqual(res.exit_code, 1)
        self.assertIn("belum diotorisasi", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "Brand", "model": "Model"})
    @patch("apk_extractor.adb.ADBManager.list_packages")
    def test_no_apps_found(self, mock_list, mock_dev, mock_conn, mock_inst):
        mock_list.return_value = []
        res = self.runner.invoke(app, ["--json"])
        self.assertEqual(res.exit_code, 1)
        self.assertIn("Tidak ada aplikasi", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "Brand", "model": "Model"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.app1", "com.app2"])
    def test_list_non_json(self, mock_list, mock_dev, mock_conn, mock_inst):
        res = self.runner.invoke(app, ["--list"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Daftar Aplikasi", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "Brand", "model": "Model"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.app1"])
    @patch("apk_extractor.adb.ADBManager.get_package_quick_info")
    def test_info_non_json(self, mock_info, mock_list, mock_dev, mock_conn, mock_inst):
        mock_info.return_value = {
            "package_name": "com.app1",
            "version_name": "1.0",
            "version_code": "1",
            "target_sdk": "34",
            "min_sdk": "21",
            "apk_paths": ["/data/app/base.apk"],
            "apk_format": "Single APK",
            "permissions": [],
        }
        res = self.runner.invoke(app, ["app1", "--info"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Informasi & Audit Aplikasi", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "Brand", "model": "Model"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.example.app"])
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths")
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("apk_extractor.packager.APKPackager.unpack")
    @patch("apk_extractor.packager.APKPackager.generate_analysis_summary")
    def test_full_extraction_both(self, mock_summary, mock_unpack, mock_extract, mock_paths, mock_list, mock_dev, mock_conn, mock_inst):
        mock_paths.return_value = ["/data/app/com.example.app/base.apk"]
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_apk = Path(tmp_dir) / "app.apk"
            out_apk.touch()

            mock_res = MagicMock()
            mock_res.package_name = "com.example.app"
            mock_res.app_name = "Example App"
            mock_res.output_path = out_apk
            mock_res.is_split = False
            mock_res.total_parts = 1
            mock_res.formatted_size = "2.5 MB"
            mock_extract.return_value = mock_res
            mock_summary.return_value = {"framework": "Native Android", "code_path": "classes.dex"}

            res = self.runner.invoke(app, ["example", "--both", "-o", tmp_dir, "--json"])
            self.assertEqual(res.exit_code, 0)
            data = json.loads(res.output)
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["package_name"], "com.example.app")
            self.assertEqual(data["action"], "both")

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "Brand", "model": "Model"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.example.app"])
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/com.example.app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("apk_extractor.packager.APKPackager.unpack")
    @patch("apk_extractor.packager.APKPackager.generate_analysis_summary")
    def test_full_extraction_extract_only_and_summary(self, mock_summary, mock_unpack, mock_extract, mock_paths, mock_list, mock_dev, mock_conn, mock_inst):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_apk = Path(tmp_dir) / "app.apk"
            out_apk.touch()

            mock_res = MagicMock()
            mock_res.package_name = "com.example.app"
            mock_res.app_name = "Example App"
            mock_res.output_path = out_apk
            mock_res.is_split = False
            mock_res.total_parts = 1
            mock_res.formatted_size = "2.5 MB"
            mock_extract.return_value = mock_res
            mock_summary.return_value = {"framework": "Native Android", "code_path": "classes.dex"}

            # extract_only without json (renders show_success_summary and deletes apk)
            res = self.runner.invoke(app, ["example", "--extract-only", "-o", tmp_dir])
            self.assertEqual(res.exit_code, 0)
            self.assertIn("Operasi Berhasil", res.output)
            self.assertFalse(out_apk.exists(), "extract_only should remove the downloaded APK")

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "Brand", "model": "Model"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.example.app"])
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/com.example.app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("apk_extractor.packager.APKPackager.unpack")
    def test_full_extraction_with_decompile(self, mock_unpack, mock_extract, mock_paths, mock_list, mock_dev, mock_conn, mock_inst):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_apk = Path(tmp_dir) / "app.apk"
            out_apk.touch()

            mock_res = MagicMock()
            mock_res.package_name = "com.example.app"
            mock_res.app_name = "Example App"
            mock_res.output_path = out_apk
            mock_res.is_split = False
            mock_res.total_parts = 1
            mock_res.formatted_size = "2.5 MB"
            mock_extract.return_value = mock_res

            with patch("apk_extractor.jadx.JADXManager.is_installed", return_value=True), \
                 patch("apk_extractor.jadx.JADXManager.decompile_class", return_value="public class Main {}"), \
                 patch("apk_extractor.jadx.JADXManager.decompile_app", return_value=True):
                res = self.runner.invoke(app, [
                    "example",
                    "--both",
                    "--decompile",
                    "--decompile-class",
                    "com.example.app.MainActivity",
                    "-o",
                    tmp_dir,
                    "--json",
                ])
                self.assertEqual(res.exit_code, 0)
                data = json.loads(res.output)
                self.assertIsNotNone(data["decompiled_class"])
                self.assertIsNotNone(data["decompiled_src"])

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "Brand", "model": "Model"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.example.app"])
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/com.example.app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("apk_extractor.packager.APKPackager.unpack")
    def test_extraction_bad_zip_handling(self, mock_unpack, mock_extract, mock_paths, mock_list, mock_dev, mock_conn, mock_inst):
        import zipfile
        mock_unpack.side_effect = zipfile.BadZipFile("File is not a zip")
        mock_res = MagicMock()
        mock_res.package_name = "com.example.app"
        mock_res.app_name = "Example App"
        mock_res.output_path = Path("/tmp/app.apk")
        mock_extract.return_value = mock_res

        res = self.runner.invoke(app, ["example", "--both"])
        self.assertEqual(res.exit_code, 1)
        self.assertIn("Gagal membongkar APK", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device"), ("DEV2", "device")])
    @patch("apk_extractor.adb.ADBManager.get_devices_with_details", return_value=[
        {"serial": "DEV1", "brand": "Google", "model": "Pixel", "android_version": "14", "status": "device"},
        {"serial": "DEV2", "brand": "Samsung", "model": "Galaxy", "android_version": "13", "status": "device"},
    ])
    @patch("apk_extractor.cli.select_devices")
    @patch("apk_extractor.cli.process_single_device")
    def test_multi_device_selection(self, mock_process, mock_select, mock_details, mock_conn, mock_inst):
        mock_select.return_value = [
            {"serial": "DEV1", "brand": "Google", "model": "Pixel", "android_version": "14", "status": "device"},
            {"serial": "DEV2", "brand": "Samsung", "model": "Galaxy", "android_version": "13", "status": "device"},
        ]
        res = self.runner.invoke(app, [])
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(mock_process.call_count, 2)

    def test_query_matches_handled(self):
        from apk_extractor.cli import query_matches_handled
        self.assertTrue(query_matches_handled("apk_only"))
        self.assertTrue(query_matches_handled("extract_only"))
        self.assertTrue(query_matches_handled("both"))
        self.assertFalse(query_matches_handled("invalid_action"))


class TestCLIInteractiveAndProcess(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.app"])
    @patch("apk_extractor.cli.resolve_apps", return_value=[AppInfo(package_name="com.test.app", app_name="Test App")])
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("questionary.select")
    def test_interactive_action_prompt_apk_only(self, mock_select, mock_extract, mock_paths, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        mock_ask = MagicMock()
        mock_ask.ask.return_value = "apk_only"
        mock_select.return_value = mock_ask

        mock_res = MagicMock()
        mock_res.package_name = "com.test.app"
        mock_res.app_name = "Test App"
        mock_res.output_path = Path("/tmp/test.apk")
        mock_res.is_split = False
        mock_res.total_parts = 1
        mock_res.formatted_size = "1.5 MB"
        mock_extract.return_value = mock_res

        res = self.runner.invoke(app, ["test"])
        self.assertEqual(res.exit_code, 0)
        self.assertTrue(mock_select.called)
        self.assertTrue(mock_extract.called)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.app"])
    @patch("apk_extractor.cli.resolve_apps", return_value=[AppInfo(package_name="com.test.app", app_name="Test App")])
    @patch("questionary.select")
    def test_interactive_action_prompt_cancelled(self, mock_select, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        mock_ask = MagicMock()
        mock_ask.ask.return_value = None
        mock_select.return_value = mock_ask

        res = self.runner.invoke(app, ["test"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Operasi dibatalkan", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.one", "com.test.two"])
    @patch("apk_extractor.cli.resolve_apps")
    @patch("apk_extractor.cli.run_tui_selector")
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    def test_partial_matches_tui_success(self, mock_extract, mock_paths, mock_tui, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        apps = [
            AppInfo(package_name="com.test.one", app_name="Test One"),
            AppInfo(package_name="com.test.two", app_name="Test Two"),
        ]
        mock_resolve.return_value = apps
        mock_tui.return_value = (apps[0], "both")

        mock_res = MagicMock()
        mock_res.package_name = "com.test.one"
        mock_res.app_name = "Test One"
        mock_res.output_path = Path("/tmp/test.apk")
        mock_res.is_split = False
        mock_res.total_parts = 1
        mock_res.formatted_size = "1.5 MB"
        mock_extract.return_value = mock_res

        with patch("apk_extractor.packager.APKPackager.unpack"), \
             patch("apk_extractor.packager.APKPackager.generate_analysis_summary"):
            res = self.runner.invoke(app, ["test"])
            self.assertEqual(res.exit_code, 0)
            self.assertTrue(mock_tui.called)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.one", "com.test.two"])
    @patch("apk_extractor.cli.resolve_apps")
    @patch("apk_extractor.cli.run_tui_selector", side_effect=RuntimeError("TUI error"))
    @patch("apk_extractor.cli.select_package_interactive", return_value="com.test.two")
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    def test_partial_matches_fallback_interactive(self, mock_extract, mock_paths, mock_select_pkg, mock_tui, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        apps = [
            AppInfo(package_name="com.test.one", app_name="Test One"),
            AppInfo(package_name="com.test.two", app_name="Test Two"),
        ]
        mock_resolve.return_value = apps

        mock_res = MagicMock()
        mock_res.package_name = "com.test.two"
        mock_res.app_name = "Test Two"
        mock_res.output_path = Path("/tmp/test.apk")
        mock_res.is_split = False
        mock_res.total_parts = 1
        mock_res.formatted_size = "1.5 MB"
        mock_extract.return_value = mock_res

        with patch("questionary.select") as mock_action_select:
            mock_action_select.return_value.ask.return_value = "apk_only"
            res = self.runner.invoke(app, ["test"])
            self.assertEqual(res.exit_code, 0)
            self.assertTrue(mock_select_pkg.called)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.app"])
    @patch("apk_extractor.cli.resolve_apps", return_value=[AppInfo(package_name="com.test.app", app_name="Test App")])
    @patch("questionary.confirm")
    def test_no_matches_confirm_no(self, mock_confirm, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        mock_confirm.return_value.ask.return_value = False
        res = self.runner.invoke(app, ["nomatch"])
        self.assertEqual(res.exit_code, 0)
        self.assertTrue(mock_confirm.called)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.app"])
    @patch("apk_extractor.cli.resolve_apps", return_value=[AppInfo(package_name="com.test.app", app_name="Test App")])
    def test_no_matches_json(self, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        res = self.runner.invoke(app, ["nomatch", "--json"])
        self.assertEqual(res.exit_code, 1)
        data = json.loads(res.output)
        self.assertEqual(data["status"], "error")

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", side_effect=ADBError("ADB failure"))
    def test_list_packages_adb_error(self, mock_list, mock_details, mock_conn, mock_inst):
        res = self.runner.invoke(app, ["--list"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("ADB failure", res.output)

        res_json = self.runner.invoke(app, ["--list", "--json"])
        self.assertEqual(res_json.exit_code, 1)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=[])
    def test_no_packages_found(self, mock_list, mock_details, mock_conn, mock_inst):
        res = self.runner.invoke(app, [])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Tidak ada aplikasi", res.output)

        res_json = self.runner.invoke(app, ["--json"])
        self.assertEqual(res_json.exit_code, 1)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.one", "com.test.two"])
    @patch("apk_extractor.cli.resolve_apps", return_value=[
        AppInfo(package_name="com.test.one", app_name="One"),
        AppInfo(package_name="com.test.two", app_name="Two"),
    ])
    @patch("apk_extractor.adb.ADBManager.get_package_recent_order", return_value=["com.test.two", "com.test.one"])
    def test_recent_order_sorting(self, mock_order, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        res = self.runner.invoke(app, ["--list", "--recent", "--json"])
        self.assertEqual(res.exit_code, 0)
        data = json.loads(res.output)
        self.assertEqual(data[0]["package_name"], "com.test.two")
        self.assertEqual(data[1]["package_name"], "com.test.one")

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.app"])
    @patch("apk_extractor.cli.resolve_apps", return_value=[AppInfo(package_name="com.test.app", app_name="Test App")])
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", side_effect=ADBError("Paths unavailable"))
    def test_get_apk_paths_adberror(self, mock_paths, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        res = self.runner.invoke(app, ["test", "--apk-only"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Paths unavailable", res.output)

        res_json = self.runner.invoke(app, ["test", "--apk-only", "--json"])
        self.assertEqual(res_json.exit_code, 1)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.app"])
    @patch("apk_extractor.cli.resolve_apps", return_value=[AppInfo(package_name="com.test.app", app_name="Test App")])
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=[])
    def test_get_apk_paths_empty(self, mock_paths, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        res = self.runner.invoke(app, ["test", "--apk-only"])
        self.assertEqual(res.exit_code, 0)
        self.assertIn("Tidak dapat menemukan path APK", res.output)

        res_json = self.runner.invoke(app, ["test", "--apk-only", "--json"])
        self.assertEqual(res_json.exit_code, 1)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.app"])
    @patch("apk_extractor.cli.resolve_apps", return_value=[AppInfo(package_name="com.test.app", app_name="Test App")])
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("apk_extractor.packager.APKPackager.unpack")
    def test_extract_only_unlinks_apk(self, mock_unpack, mock_extract, mock_paths, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        with tempfile.TemporaryDirectory() as tmp_d:
            fake_apk = Path(tmp_d) / "fake.apk"
            fake_apk.touch()

            mock_res = MagicMock()
            mock_res.package_name = "com.test.app"
            mock_res.app_name = "Test App"
            mock_res.output_path = fake_apk
            mock_res.is_split = False
            mock_res.total_parts = 1
            mock_res.formatted_size = "1.0 MB"
            mock_extract.return_value = mock_res

            with patch("apk_extractor.packager.APKPackager.generate_analysis_summary"):
                res = self.runner.invoke(app, ["test", "--extract-only", "-o", tmp_d])
                self.assertEqual(res.exit_code, 0)
                self.assertFalse(fake_apk.exists())

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.app"])
    @patch("apk_extractor.cli.resolve_apps", return_value=[AppInfo(package_name="com.test.app", app_name="Test App")])
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("apk_extractor.packager.APKPackager.unpack", side_effect=RuntimeError("Unpack error generic"))
    def test_unpack_generic_exception(self, mock_unpack, mock_extract, mock_paths, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        mock_res = MagicMock()
        mock_res.package_name = "com.test.app"
        mock_res.app_name = "Test App"
        mock_res.output_path = Path("/tmp/fake.apk")
        mock_extract.return_value = mock_res

        res = self.runner.invoke(app, ["test", "--both"])
        self.assertEqual(res.exit_code, 1)
        self.assertIn("Gagal membongkar APK: Unpack error generic", res.output)

    @patch("apk_extractor.adb.ADBManager.is_installed", return_value=True)
    @patch("apk_extractor.adb.ADBManager.get_connected_devices", return_value=[("DEV1", "device")])
    @patch("apk_extractor.adb.ADBManager.get_device_details", return_value={"serial": "DEV1", "status": "device", "brand": "B", "model": "M"})
    @patch("apk_extractor.adb.ADBManager.list_packages", return_value=["com.test.app"])
    @patch("apk_extractor.cli.resolve_apps", return_value=[AppInfo(package_name="com.test.app", app_name="Test App")])
    @patch("apk_extractor.adb.ADBManager.get_package_apk_paths", return_value=["/data/app/base.apk"])
    @patch("apk_extractor.packager.APKPackager.extract")
    @patch("apk_extractor.packager.APKPackager.unpack")
    def test_decompile_class_failure_warning(self, mock_unpack, mock_extract, mock_paths, mock_resolve, mock_pkgs, mock_details, mock_conn, mock_inst):
        with tempfile.TemporaryDirectory() as tmp_d:
            fake_apk = Path(tmp_d) / "fake.apk"
            fake_apk.touch()

            mock_res = MagicMock()
            mock_res.package_name = "com.test.app"
            mock_res.app_name = "Test App"
            mock_res.output_path = fake_apk
            mock_res.is_split = False
            mock_res.total_parts = 1
            mock_res.formatted_size = "1.5 MB"
            mock_extract.return_value = mock_res

            with patch("apk_extractor.jadx.JADXManager.is_installed", return_value=False), \
                 patch("apk_extractor.jadx.JADXManager.ensure_installed", return_value=True), \
                 patch("apk_extractor.jadx.JADXManager.decompile_class", return_value=None), \
                 patch("apk_extractor.packager.APKPackager.generate_analysis_summary"):
                res = self.runner.invoke(app, ["test", "--both", "--decompile-class", "com.test.NonExistent", "-o", tmp_d])
                self.assertEqual(res.exit_code, 0)
                self.assertIn("Gagal mendekomposisi kelas", res.output)


if __name__ == "__main__":
    unittest.main()

