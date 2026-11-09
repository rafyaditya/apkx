import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from apk_extractor.adb import ADBManager, find_adb_binary


class TestADBManager(unittest.TestCase):
    def test_find_adb_binary_explicit(self):
        self.assertEqual(find_adb_binary("custom_adb"), "custom_adb")

    @patch("shutil.which")
    def test_find_adb_binary_system_path(self, mock_which):
        mock_which.return_value = "/usr/bin/adb"
        self.assertEqual(find_adb_binary(), "/usr/bin/adb")

    @patch("subprocess.run")
    def test_get_connected_devices(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "List of devices attached\nEU99MJMVKREIWCDY\tdevice\nemulator-5554\tunauthorized\n"
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        devices = manager.get_connected_devices()
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0], ("EU99MJMVKREIWCDY", "device"))
        self.assertEqual(devices[1], ("emulator-5554", "unauthorized"))

    @patch("subprocess.run")
    def test_get_device_details(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "realme\nRMX2180\n10\n"
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        details = manager.get_device_details("EU99MJMVKREIWCDY", "device")
        self.assertEqual(details["brand"], "Realme")
        self.assertEqual(details["model"], "RMX2180")
        self.assertEqual(details["android_version"], "Android 10")
        self.assertEqual(details["status"], "device")

    def test_get_device_details_unauthorized(self):
        manager = ADBManager(adb_path="mock_adb")
        details = manager.get_device_details("emulator-5554", "unauthorized")
        self.assertEqual(details["brand"], "-")
        self.assertEqual(details["model"], "-")
        self.assertEqual(details["status"], "unauthorized")

    def test_select_devices_single_device(self):
        from apk_extractor.ui import select_devices
        devs = [{"serial": "dev1", "status": "device", "brand": "Brand", "model": "M1"}]
        res = select_devices(devs)
        self.assertEqual(res, devs)

    @patch("questionary.select")
    def test_select_devices_all_option(self, mock_select):
        from apk_extractor.ui import select_devices
        mock_ask = MagicMock()
        mock_ask.ask.return_value = "ALL"
        mock_select.return_value = mock_ask

        devs = [
            {"serial": "dev1", "status": "device", "brand": "Brand1", "model": "M1"},
            {"serial": "dev2", "status": "device", "brand": "Brand2", "model": "M2"},
        ]
        res = select_devices(devs)
        self.assertEqual(res, devs)

    @patch("questionary.select")
    def test_select_devices_specific_option(self, mock_select):
        from apk_extractor.ui import select_devices
        mock_ask = MagicMock()
        mock_ask.ask.return_value = "dev2"
        mock_select.return_value = mock_ask

        devs = [
            {"serial": "dev1", "status": "device", "brand": "Brand1", "model": "M1"},
            {"serial": "dev2", "status": "device", "brand": "Brand2", "model": "M2"},
        ]
        res = select_devices(devs)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["serial"], "dev2")

    @patch("subprocess.run")
    def test_get_screen_size(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Physical size: 720x1600\n"
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        w, h = manager.get_screen_size()
        self.assertEqual(w, 720)
        self.assertEqual(h, 1600)

    @patch("subprocess.run")
    def test_take_screenshot_exec_out(self, mock_run):
        import tempfile
        from pathlib import Path
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = b"\x89PNG\r\n\x1a\n" + b"\x00" * 1500
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        with tempfile.TemporaryDirectory() as tmp_d:
            out_png = Path(tmp_d) / "screen.png"
            ok = manager.take_screenshot(out_png)
            self.assertTrue(ok)
            self.assertTrue(out_png.is_file())
            self.assertGreater(out_png.stat().st_size, 1000)

    @patch("subprocess.run")
    def test_launch_app(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Starting: Intent { cmp=com.test/.MainActivity }\n"
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        ok = manager.launch_app("com.test", "MainActivity", restart=True)
        self.assertTrue(ok)

    @patch("subprocess.run")
    def test_dump_ui_hierarchy(self, mock_run):
        def side_effect(cmd, *args, **kwargs):
            mock_proc = MagicMock()
            if "uiautomator" in cmd:
                mock_proc.returncode = 0
                mock_proc.stdout = "UI hierchary dumped to: /sdcard/apkx_window_dump.xml"
            elif "exec-out" in cmd and "cat" in cmd:
                mock_proc.returncode = 0
                mock_proc.stdout = (
                    '<hierarchy><node text="Lanjutkan" resource-id="com.test:id/btn" '
                    'class="android.widget.Button" clickable="true" '
                    'bounds="[100,200][300,400]"/></hierarchy>'
                )
            else:
                mock_proc.returncode = 0
                mock_proc.stdout = ""
            return mock_proc

        mock_run.side_effect = side_effect
        manager = ADBManager(adb_path="mock_adb")
        elements = manager.dump_ui_hierarchy()
        self.assertEqual(len(elements), 1)
        el = elements[0]
        self.assertEqual(el["text"], "Lanjutkan")
        self.assertEqual(el["resource_id"], "com.test:id/btn")
        self.assertEqual(el["bounds"], [100, 200, 300, 400])
        self.assertEqual(el["center"], [200, 300])

    @patch("subprocess.run")
    def test_input_interact_tap_and_back(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        self.assertTrue(manager.input_interact("tap", x=100, y=200))
        self.assertTrue(manager.input_interact("back"))
        self.assertTrue(manager.input_interact("home"))
        self.assertTrue(manager.input_interact("enter"))
        self.assertTrue(manager.input_interact("text", text="hello world"))
        self.assertFalse(manager.input_interact("tap"))  # Missing x,y
        self.assertFalse(manager.input_interact("unknown_action"))

    @patch("subprocess.run")
    def test_ensure_device_awake_unlocked(self, mock_run):
        def side_effect(cmd, *args, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if "power" in cmd:
                mock_proc.stdout = "mWakefulness=Awake\nDisplay Power: state=ON\n"
            elif "window" in cmd:
                mock_proc.stdout = "mKeyguardShowing=false\nisStatusBarKeyguard=false\n"
            else:
                mock_proc.stdout = ""
            return mock_proc

        mock_run.side_effect = side_effect
        manager = ADBManager(adb_path="mock_adb")
        res = manager.ensure_device_awake()
        self.assertEqual(res["status"], "ready")
        self.assertFalse(res["locked"])

    @patch("subprocess.run")
    def test_ensure_device_awake_safe_stop_when_pin_missing(self, mock_run):
        def side_effect(cmd, *args, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if "power" in cmd:
                mock_proc.stdout = "mWakefulness=Asleep\n"
            elif "window" in cmd:
                mock_proc.stdout = "mKeyguardShowing=true\n"
            else:
                mock_proc.stdout = ""
            return mock_proc

        mock_run.side_effect = side_effect
        manager = ADBManager(adb_path="mock_adb")
        res = manager.ensure_device_awake(pin=None)
        self.assertEqual(res["status"], "locked")
        self.assertTrue(res["requires_pin"])
        self.assertEqual(res["action_required"], "manual_unlock")

    @patch("subprocess.run")
    def test_get_current_screen(self, mock_run):
        def side_effect(cmd, *args, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if "window" in cmd:
                mock_proc.stdout = "mCurrentFocus=Window{123 u0 com.example.app/com.example.app.DetailActivity}\n"
            elif "pidof" in cmd:
                mock_proc.stdout = "12345\n"
            else:
                mock_proc.stdout = ""
            return mock_proc

        mock_run.side_effect = side_effect
        manager = ADBManager(adb_path="mock_adb")
        info = manager.get_current_screen()
        self.assertEqual(info["package_name"], "com.example.app")
        self.assertEqual(info["activity_name"], "com.example.app.DetailActivity")
        self.assertEqual(info["pid"], 12345)
        self.assertTrue(info["is_running"])

    @patch("subprocess.run")
    def test_get_app_logs(self, mock_run):
        def side_effect(cmd, *args, **kwargs):
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            if "pidof" in cmd:
                mock_proc.stdout = "12345\n"
            elif "logcat" in cmd:
                mock_proc.stdout = "11-08 10:00:00.000 12345 12345 E AndroidRuntime: FATAL EXCEPTION: main\n"
            else:
                mock_proc.stdout = ""
            return mock_proc

        mock_run.side_effect = side_effect
        manager = ADBManager(adb_path="mock_adb")
        logs_res = manager.get_app_logs("com.example.app")
        self.assertEqual(logs_res["package_name"], "com.example.app")
        self.assertEqual(logs_res["pid"], 12345)
        self.assertTrue(logs_res["has_crash_indicator"])
        self.assertIn("FATAL EXCEPTION", logs_res["logs"])

    @patch("subprocess.run")
    def test_reset_app_data(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Success\n"
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        self.assertTrue(manager.reset_app_data("com.example.app"))

    @patch("subprocess.run")
    def test_open_deep_link(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Starting: Intent { act=android.intent.action.VIEW dat=app://test }\n"
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        self.assertTrue(manager.open_deep_link("app://test"))

    @patch("subprocess.run")
    def test_toggle_night_mode(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        self.assertTrue(manager.toggle_night_mode(True))
        self.assertTrue(manager.toggle_night_mode(False))

    @patch("apk_extractor.adb.ADBManager.get_connected_devices")
    def test_check_device_ready_no_devices(self, mock_devs):
        mock_devs.return_value = []
        manager = ADBManager(adb_path="mock_adb")
        ready, code, detail = manager.check_device_ready()
        self.assertFalse(ready)
        self.assertEqual(code, "NO_DEVICE")
        self.assertIn("troubleshooting", detail)
        self.assertEqual(len(detail["troubleshooting"]), 4)

    @patch("apk_extractor.adb.ADBManager.get_connected_devices")
    def test_check_device_ready_unauthorized(self, mock_devs):
        mock_devs.return_value = [("dev_unauth", "unauthorized")]
        manager = ADBManager(adb_path="mock_adb")
        ready, code, detail = manager.check_device_ready()
        self.assertFalse(ready)
        self.assertEqual(code, "UNAUTHORIZED")
        self.assertIn("troubleshooting", detail)
        self.assertEqual(detail["serial"], "dev_unauth")

    @patch("apk_extractor.adb.ADBManager.get_connected_devices")
    def test_check_device_ready_offline(self, mock_devs):
        mock_devs.return_value = [("dev_off", "offline")]
        manager = ADBManager(adb_path="mock_adb")
        ready, code, detail = manager.check_device_ready()
        self.assertFalse(ready)
        self.assertEqual(code, "OFFLINE")
        self.assertIn("troubleshooting", detail)

    @patch("apk_extractor.adb.ADBManager.get_connected_devices")
    def test_check_device_ready_not_found(self, mock_devs):
        mock_devs.return_value = [("dev_ok", "device")]
        manager = ADBManager(adb_path="mock_adb")
        ready, code, detail = manager.check_device_ready(device_id="missing_id")
        self.assertFalse(ready)
        self.assertEqual(code, "DEVICE_NOT_FOUND")
        self.assertEqual(detail["requested_id"], "missing_id")

    @patch("apk_extractor.adb.ADBManager.get_device_details")
    @patch("apk_extractor.adb.ADBManager.get_connected_devices")
    def test_check_device_ready_success(self, mock_devs, mock_details):
        mock_devs.return_value = [("dev_ok", "device")]
        mock_details.return_value = {
            "serial": "dev_ok",
            "status": "device",
            "brand": "Google",
            "model": "Pixel 7",
            "android_version": "Android 14",
        }
        manager = ADBManager(adb_path="mock_adb")
        ready, code, detail = manager.check_device_ready()
        self.assertTrue(ready)
        self.assertEqual(code, "READY")
        self.assertEqual(detail["serial"], "dev_ok")
        self.assertEqual(detail["details"]["brand"], "Google")

    @patch("apk_extractor.adb.ADBManager.get_connected_devices")
    def test_check_device_ready_adb_error(self, mock_devs):
        from apk_extractor.adb import ADBError
        mock_devs.side_effect = ADBError("ADB daemon not running")
        manager = ADBManager(adb_path="mock_adb")
        ready, code, detail = manager.check_device_ready()
        self.assertFalse(ready)
        self.assertEqual(code, "ADB_ERROR")
        self.assertIn("troubleshooting", detail)

    def test_install_apk_file_not_found(self):
        manager = ADBManager(adb_path="mock_adb")
        ok, code, detail = manager.install_apk("non_existent_file.apk")
        self.assertFalse(ok)
        self.assertEqual(code, "FILE_NOT_FOUND")

    def test_install_apk_invalid_type(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".txt") as tmp:
            manager = ADBManager(adb_path="mock_adb")
            ok, code, detail = manager.install_apk(tmp.name)
            self.assertFalse(ok)
            self.assertEqual(code, "INVALID_FILE_TYPE")

    @patch("subprocess.run")
    def test_install_apk_success(self, mock_run):
        import tempfile
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Performing Streamed Install\nSuccess\n"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with tempfile.NamedTemporaryFile(suffix=".apk") as tmp:
            manager = ADBManager(adb_path="mock_adb")
            ok, code, detail = manager.install_apk(tmp.name)
            self.assertTrue(ok)
            self.assertEqual(code, "SUCCESS")

    @patch("subprocess.run")
    def test_install_apks_split_success(self, mock_run):
        import tempfile
        import zipfile
        from pathlib import Path

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Success\n"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with tempfile.TemporaryDirectory() as tmp_dir:
            apks_file = Path(tmp_dir) / "test_app.apks"
            with zipfile.ZipFile(apks_file, "w") as zf:
                zf.writestr("base.apk", b"PKdummybase")
                zf.writestr("split_config.arm64_v8a.apk", b"PKdummysplit")

            manager = ADBManager(adb_path="mock_adb")
            ok, code, detail = manager.install_apk(apks_file)
            self.assertTrue(ok)
            self.assertEqual(code, "SUCCESS")
            self.assertTrue(detail.get("is_split"))
            self.assertEqual(detail.get("total_parts"), 2)

            called_cmd = mock_run.call_args[0][0]
            self.assertIn("install-multiple", called_cmd)

    @patch("subprocess.run")
    def test_install_apk_update_incompatible(self, mock_run):
        import tempfile
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = "Failure [INSTALL_FAILED_UPDATE_INCOMPATIBLE: Package signatures do not match]\n"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        with tempfile.NamedTemporaryFile(suffix=".apk") as tmp:
            manager = ADBManager(adb_path="mock_adb")
            ok, code, detail = manager.install_apk(tmp.name)
            self.assertFalse(ok)
            self.assertEqual(code, "UPDATE_INCOMPATIBLE")
            self.assertIn("suggestion", detail)

    @patch("subprocess.run")
    def test_uninstall_app_success(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Success\n"
        mock_proc.stderr = ""
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        ok, code, detail = manager.uninstall_app("com.example.app")
        self.assertTrue(ok)
        self.assertEqual(code, "SUCCESS")

    def test_uninstall_app_empty_name(self):
        manager = ADBManager(adb_path="mock_adb")
        ok, code, detail = manager.uninstall_app("  ")
        self.assertFalse(ok)
        self.assertEqual(code, "INVALID_PACKAGE")

    @patch("subprocess.run")
    def test_input_interact_text_escaping_and_newlines(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")

        # Test special characters and globbing escaping
        ok = manager.input_interact("text", text="Hello* [World]? $100 & 'quotes'")
        self.assertTrue(ok)
        cmd_text = mock_run.call_args[0][0]
        # Verify shell input command
        self.assertEqual(cmd_text[:3], ["mock_adb", "shell", "input"])
        self.assertEqual(cmd_text[3], "text")
        # Verify wildcards and spaces escaped
        self.assertIn("Hello\\*", cmd_text[4])
        self.assertIn("\\[World\\]\\?", cmd_text[4])
        self.assertIn("\\$100", cmd_text[4])
        self.assertIn("\\&", cmd_text[4])
        self.assertIn("\\'quotes\\'", cmd_text[4])

        # Test newline split into text + keyevent 66
        mock_run.reset_mock()
        ok_nl = manager.input_interact("text", text="Line1\nLine2")
        self.assertTrue(ok_nl)
        # Should have called subprocess.run 3 times: Line1 text, Enter keyevent, Line2 text
        self.assertEqual(mock_run.call_count, 3)
        first_call_cmd = mock_run.call_args_list[0][0][0]
        second_call_cmd = mock_run.call_args_list[1][0][0]
        third_call_cmd = mock_run.call_args_list[2][0][0]
        self.assertIn("Line1", first_call_cmd)
        self.assertIn("66", second_call_cmd)
        self.assertIn("Line2", third_call_cmd)

        # Test CRLF normalization and % literal escaping
        mock_run.reset_mock()
        ok_crlf = manager.input_interact("text", text="Discount 50%\r\nPromo 100%")
        self.assertTrue(ok_crlf)
        self.assertEqual(mock_run.call_count, 3)
        crlf_call1 = mock_run.call_args_list[0][0][0]
        crlf_call2 = mock_run.call_args_list[1][0][0]
        crlf_call3 = mock_run.call_args_list[2][0][0]
        # Space converted to %s and literal % kept as % (not \%)
        self.assertIn("Discount%s50%", crlf_call1[4])
        self.assertIn("66", crlf_call2)
        self.assertIn("Promo%s100%", crlf_call3[4])

        # Test chunking of literal %s in raw text
        mock_run.reset_mock()
        mock_run.side_effect = None
        mock_run.return_value = mock_proc
        ok_literal_s = manager.input_interact("text", text="Code%sVal")
        self.assertTrue(ok_literal_s)
        # Should split on %s and send: "Code", "%", "s", "Val"
        calls = [call[0][0] for call in mock_run.call_args_list]
        sent_texts = [c[4] for c in calls if len(c) > 4 and c[3] == "text"]
        self.assertEqual(sent_texts, ["Code", "%", "s", "Val"])

        # Test keyevent 66 failure returns False
        mock_run.reset_mock()
        mock_fail = MagicMock()
        mock_fail.returncode = 1
        mock_run.side_effect = [mock_proc, mock_fail, mock_proc]
        ok_fail = manager.input_interact("text", text="LineA\nLineB")
        self.assertFalse(ok_fail)


class TestADBAdditionalFeatures(unittest.TestCase):
    @patch("pathlib.Path.is_file")
    @patch("shutil.which", return_value=None)
    def test_find_adb_binary_bundled_and_cached(self, mock_which, mock_is_file):
        from apk_extractor.adb import find_adb_binary
        mock_is_file.side_effect = [True, False]
        res1 = find_adb_binary()
        self.assertIn("adb", res1)

        mock_is_file.side_effect = [False, True]
        res2 = find_adb_binary()
        self.assertIn("adb", res2)

        mock_is_file.side_effect = [False, False]
        res3 = find_adb_binary()
        self.assertEqual(res3, "adb")

    def test_ensure_installed_lifecycle(self):
        manager = ADBManager(adb_path="mock_adb")
        with patch.object(manager, "is_installed", side_effect=[True]):
            self.assertTrue(manager.ensure_installed())

        with patch.object(manager, "is_installed", side_effect=[False, True]), \
             patch.object(manager, "download_platform_tools", return_value=True):
            self.assertTrue(manager.ensure_installed())

        with patch.object(manager, "is_installed", return_value=False), \
             patch.object(manager, "download_platform_tools", return_value=False):
            self.assertFalse(manager.ensure_installed())

    def test_download_platform_tools(self):
        import io
        import zipfile
        import tempfile
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("platform-tools/adb", "#!/bin/sh\n")
        zip_bytes = zip_buf.getvalue()

        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch("pathlib.Path.home", return_value=Path(tmp_dir)), \
             patch("urllib.request.urlretrieve") as mock_retrieve:
            def fake_retrieve(url, path):
                Path(path).write_bytes(zip_bytes)
            mock_retrieve.side_effect = fake_retrieve

            progress = []
            res = ADBManager.download_platform_tools(on_progress=progress.append)
            self.assertTrue(res)
            self.assertTrue((Path(tmp_dir) / ".apkx" / "platform-tools" / "adb").exists())

        with patch("urllib.request.urlretrieve", side_effect=Exception("Network error")):
            self.assertFalse(ADBManager.download_platform_tools())

    @patch("subprocess.run")
    def test_install_apk_failure_variants(self, mock_run):
        import tempfile
        manager = ADBManager(adb_path="mock_adb")

        with tempfile.NamedTemporaryFile(suffix=".apk") as tmp:
            # Downgrade error
            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout = "Failure [INSTALL_FAILED_VERSION_DOWNGRADE]\n"
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc
            ok, code, _ = manager.install_apk(tmp.name)
            self.assertFalse(ok)
            self.assertEqual(code, "VERSION_DOWNGRADE")

            # Insufficient storage
            mock_proc.stdout = "Failure [INSTALL_FAILED_INSUFFICIENT_STORAGE]\n"
            ok, code, _ = manager.install_apk(tmp.name)
            self.assertFalse(ok)
            self.assertEqual(code, "INSUFFICIENT_STORAGE")

            # Generic failure
            mock_proc.stdout = "Failure [INSTALL_PARSE_FAILED_BAD_MANIFEST]\n"
            ok, code, _ = manager.install_apk(tmp.name)
            self.assertFalse(ok)
            self.assertEqual(code, "INSTALL_FAILED")

            # Timeout
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["install"], timeout=180)
            ok, code, _ = manager.install_apk(tmp.name)
            self.assertFalse(ok)
            self.assertEqual(code, "TIMEOUT")

            # Generic Exception
            mock_run.side_effect = RuntimeError("Broken Pipe")
            ok, code, _ = manager.install_apk(tmp.name)
            self.assertFalse(ok)
            self.assertEqual(code, "EXECUTION_ERROR")

    @patch("subprocess.run")
    def test_device_controls_and_diagnostics(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")

        # Night mode
        self.assertTrue(manager.toggle_night_mode(True))
        self.assertTrue(manager.toggle_night_mode(False))

        # Deep link
        self.assertTrue(manager.open_deep_link("https://example.com/app"))

        # Reset app data
        mock_proc.stdout = "Success\n"
        self.assertTrue(manager.reset_app_data("com.test.app"))

        # Launch app
        self.assertTrue(manager.launch_app("com.test.app", "com.test.app.MainActivity"))

        # Get current screen
        mock_proc.stdout = "mCurrentFocus=Window{123 u0 com.test.app/com.test.app.MainActivity}\n"
        screen = manager.get_current_screen()
        self.assertEqual(screen["package_name"], "com.test.app")
        self.assertEqual(screen["activity_name"], "com.test.app.MainActivity")

    @patch("subprocess.run")
    def test_check_device_ready_variants(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")

        with patch.object(manager, "get_connected_devices") as mock_conn:
            # No devices
            mock_conn.return_value = []
            ready, code, _ = manager.check_device_ready()
            self.assertFalse(ready)
            self.assertEqual(code, "NO_DEVICE")

            # Unauthorized
            mock_conn.return_value = [("DEV1", "unauthorized")]
            ready, code, _ = manager.check_device_ready()
            self.assertFalse(ready)
            self.assertEqual(code, "UNAUTHORIZED")

            # Offline
            mock_conn.return_value = [("DEV1", "offline")]
            ready, code, _ = manager.check_device_ready()
            self.assertFalse(ready)
            self.assertEqual(code, "OFFLINE")

            # Ready
            mock_conn.return_value = [("DEV1", "device")]
            with patch.object(manager, "get_device_details", return_value={"serial": "DEV1", "status": "device"}):
                ready, code, _ = manager.check_device_ready()
                self.assertTrue(ready)
                self.assertEqual(code, "READY")

    @patch("subprocess.run")
    def test_dump_ui_hierarchy(self, mock_run):
        xml_content = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
<hierarchy rotation="0">
  <node index="0" text="Masuk" resource-id="com.app:id/btn_login" class="android.widget.Button" package="com.app" content-desc="" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" long-clickable="false" password="false" selected="false" bounds="[100,200][300,280]">
  </node>
</hierarchy>"""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = xml_content
        mock_run.return_value = mock_proc

        manager = ADBManager(adb_path="mock_adb")
        elements = manager.dump_ui_hierarchy()
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0]["text"], "Masuk")
        self.assertEqual(elements[0]["resource_id"], "com.app:id/btn_login")
        self.assertEqual(elements[0]["center"], [200, 240])

    @patch("subprocess.run")
    def test_pull_file_error_handling(self, mock_run):
        from apk_extractor.adb import ADBError
        manager = ADBManager(adb_path="mock_adb")

        # Timeout
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["pull"], timeout=180)
        with self.assertRaises(ADBError) as ctx:
            manager.pull_file("/remote/app.apk", "/local/app.apk")
        self.assertIn("Waktu habis", str(ctx.exception))

        # CalledProcessError
        mock_err = subprocess.CalledProcessError(returncode=1, cmd=["pull"], stderr="Permission denied")
        mock_run.side_effect = mock_err
        with self.assertRaises(ADBError) as ctx2:
            manager.pull_file("/remote/app.apk", "/local/app.apk")
        self.assertIn("Permission denied", str(ctx2.exception))

    @patch("subprocess.run")
    def test_take_screenshot_fallback(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")

        # First call (exec-out) returns corrupt/small data
        mock_exec_out = MagicMock(returncode=1, stdout=b"")
        mock_shell_screencap = MagicMock(returncode=0)
        mock_rm = MagicMock(returncode=0)

        mock_run.side_effect = [mock_exec_out, mock_shell_screencap, mock_rm]

        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            with patch.object(manager, "pull_file") as mock_pull:
                def fake_pull(rem, loc, device_id=None):
                    Path(loc).write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")
                mock_pull.side_effect = fake_pull

                ok = manager.take_screenshot(tmp.name)
                self.assertTrue(ok)

    @patch("subprocess.run")
    def test_ensure_device_awake_asleep_and_pin(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")

        # Case 1: Asleep -> wakes up with keyevent 224, then unlocked
        proc_stay = MagicMock(returncode=0)
        proc_pwr_asleep = MagicMock(returncode=0, stdout="mWakefulness=Asleep\n")
        proc_win_unlocked = MagicMock(returncode=0, stdout="mKeyguardShowing=false\nisStatusBarKeyguard=false\n")

        mock_run.side_effect = [proc_stay, proc_pwr_asleep, proc_win_unlocked]
        with patch.object(manager, "input_interact") as mock_interact:
            res = manager.ensure_device_awake(stay_on=True)
            self.assertEqual(res["status"], "ready")
            mock_interact.assert_called_with("keyevent", keycode=224, device_id=None)

        # Case 2: Locked -> unlocked by PIN
        proc_pwr_awake = MagicMock(returncode=0, stdout="mWakefulness=Awake\n")
        proc_win_locked = MagicMock(returncode=0, stdout="mKeyguardShowing=true\n")
        proc_win_still_locked = MagicMock(returncode=0, stdout="mKeyguardShowing=true\n")
        proc_win_pin_unlocked = MagicMock(returncode=0, stdout="mKeyguardShowing=false\n")

        mock_run.side_effect = [proc_stay, proc_pwr_awake, proc_win_locked, proc_win_still_locked, proc_win_pin_unlocked]
        with patch.object(manager, "input_interact"):
            res2 = manager.ensure_device_awake(pin="1234", stay_on=True)
            self.assertEqual(res2["status"], "ready")
            self.assertIn("PIN", res2["message"])


if __name__ == "__main__":
    unittest.main()
