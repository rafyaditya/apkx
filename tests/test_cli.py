import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from apk_extractor import __version__
from apk_extractor.cli import app
from apk_extractor.adb import ADBManager


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


if __name__ == "__main__":
    unittest.main()

