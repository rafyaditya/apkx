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

    @patch("subprocess.run")
    def test_list_packages_query_filter(self, mock_run):
        mock_proc = MagicMock(returncode=0, stdout="package:com.example.expense\npackage:com.other.app\npackage:com.example.notes\n")
        mock_run.return_value = mock_proc
        manager = ADBManager(adb_path="mock_adb")

        # No query -> all
        all_pkgs = manager.list_packages()
        self.assertEqual(len(all_pkgs), 3)

        # Query filter -> case-insensitive substring
        filtered = manager.list_packages(query="EXPENSE")
        self.assertEqual(filtered, ["com.example.expense"])

        filtered_ex = manager.list_packages(query="example")
        self.assertEqual(filtered_ex, ["com.example.expense", "com.example.notes"])

        # Invalid query validation
        with self.assertRaises(ValueError):
            manager.list_packages(query="invalid;query")

    @patch("subprocess.run")
    def test_get_package_quick_info_debuggable_and_flags(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")
        with patch.object(manager, "get_package_apk_paths", return_value=["/data/app/com.test.app/base.apk"]):
            # Case 1: Debuggable true
            mock_proc_dbg = MagicMock(
                returncode=0,
                stdout="versionName=1.2.3\nversionCode=45\npkgFlags=[ DEBUGGABLE HAS_CODE ALLOW_CLEAR_USER_DATA ]\n",
            )
            mock_run.return_value = mock_proc_dbg
            info_dbg = manager.get_package_quick_info("com.test.app")
            self.assertTrue(info_dbg["debuggable"])
            self.assertIn("DEBUGGABLE", info_dbg["flags"])

            # Case 2: Release (debuggable false)
            mock_proc_rel = MagicMock(
                returncode=0,
                stdout="versionName=2.0.0\nversionCode=50\nflags=[ HAS_CODE ALLOW_CLEAR_USER_DATA ]\n",
            )
            mock_run.return_value = mock_proc_rel
            info_rel = manager.get_package_quick_info("com.test.app")
            self.assertFalse(info_rel["debuggable"])

            # Case 3: No flags line
            mock_proc_none = MagicMock(returncode=0, stdout="versionName=1.0\n")
            mock_run.return_value = mock_proc_none
            info_none = manager.get_package_quick_info("com.test.app")
            self.assertIsNone(info_none["debuggable"])

    @patch("subprocess.run")
    def test_input_interact_new_actions_and_bounds(self, mock_run):
        mock_proc = MagicMock(returncode=0, stdout="")
        mock_run.return_value = mock_proc
        manager = ADBManager(adb_path="mock_adb")

        # Bounds checking with mocked screen size
        with patch.object(manager, "get_screen_size", return_value=(1080, 2400)):
            # Valid tap
            self.assertTrue(manager.input_interact("tap", x=500, y=1000))
            # Out of bounds tap
            self.assertFalse(manager.input_interact("tap", x=-10, y=100))
            self.assertFalse(manager.input_interact("tap", x=100, y=-5))
            self.assertFalse(manager.input_interact("tap", x=1200, y=1000))
            self.assertFalse(manager.input_interact("tap", x=500, y=2500))

            # long_press action
            self.assertTrue(manager.input_interact("long_press", x=500, y=1000, duration_ms=1500))
            self.assertFalse(manager.input_interact("long_press", x=500, y=1000, duration_ms=100))  # < 200 ms
            self.assertFalse(manager.input_interact("long_press", x=500, y=1000, duration_ms=6000))  # > 5000 ms
            self.assertFalse(manager.input_interact("long_press", x=None, y=1000))

            # backspace action
            self.assertTrue(manager.input_interact("backspace", count=3))
            self.assertFalse(manager.input_interact("backspace", count=0))
            self.assertFalse(manager.input_interact("backspace", count=55))

            # recent_apps action
            self.assertTrue(manager.input_interact("recent_apps"))

            # swipe action bounds validation
            self.assertTrue(manager.input_interact("swipe", swipe_coords=(100, 200, 300, 400, 300)))
            self.assertFalse(manager.input_interact("swipe", swipe_coords=(-1, 200, 300, 400)))
            self.assertFalse(manager.input_interact("swipe", swipe_coords=(100, 200, 1500, 400)))

    @patch("subprocess.run")
    def test_get_screen_state_and_overlay_classification(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")

        # Case 1: Target app in foreground without overlay
        def side_effect_app(cmd, *args, **kwargs):
            mock_proc = MagicMock(returncode=0)
            if "dumpsys" in cmd and "window" in cmd:
                mock_proc.stdout = "mCurrentFocus=Window{abc u0 com.example.app/com.example.app.MainActivity}\n"
            elif "dumpsys" in cmd and "activities" in cmd:
                mock_proc.stdout = "mResumedActivity: ActivityRecord{123 u0 com.example.app/.MainActivity t10}\n"
            elif "pidof" in cmd:
                mock_proc.stdout = "4567\n"
            else:
                mock_proc.stdout = ""
            return mock_proc

        mock_run.side_effect = side_effect_app
        st = manager.get_screen_state(expected_package="com.example.app")
        self.assertEqual(st["package_name"], "com.example.app")
        self.assertEqual(st["activity_name"], "com.example.app.MainActivity")
        self.assertEqual(st["focused_package"], "com.example.app")
        self.assertEqual(st["overlay_type"], "none")
        self.assertFalse(st["is_overlay_active"])
        self.assertTrue(st["is_target_foreground"])
        self.assertEqual(st["target_pid"], 4567)
        self.assertTrue(st["target_running"])

        # Case 2: Overlay active (Google Play Protect)
        def side_effect_overlay(cmd, *args, **kwargs):
            mock_proc = MagicMock(returncode=0)
            if "dumpsys" in cmd and "window" in cmd:
                mock_proc.stdout = "mCurrentFocus=Window{abc u0 com.android.vending/com.google.android.finsky.HsdpAlias}\n"
            elif "dumpsys" in cmd and "activities" in cmd:
                mock_proc.stdout = "topResumedActivity=ActivityRecord{123 u0 com.android.vending/.HsdpAlias t11}\n"
            elif "pidof" in cmd:
                mock_proc.stdout = "9999\n"
            else:
                mock_proc.stdout = ""
            return mock_proc

        mock_run.side_effect = side_effect_overlay
        st_overlay = manager.get_screen_state(expected_package="com.example.app")
        self.assertEqual(st_overlay["focused_package"], "com.android.vending")
        self.assertEqual(st_overlay["overlay_type"], "play_protect")
        self.assertTrue(st_overlay["is_overlay_active"])
        self.assertEqual(st_overlay["overlay_package"], "com.android.vending")
        self.assertFalse(st_overlay["is_target_foreground"])

        # Case 3: Keyboard focused (should NOT be counted as active overlay)
        def side_effect_keyboard(cmd, *args, **kwargs):
            mock_proc = MagicMock(returncode=0)
            if "dumpsys" in cmd and "window" in cmd:
                mock_proc.stdout = "mCurrentFocus=Window{abc u0 com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME}\n"
            else:
                mock_proc.stdout = ""
            return mock_proc

        mock_run.side_effect = side_effect_keyboard
        st_kb = manager.get_screen_state(expected_package="com.example.app")
        self.assertEqual(st_kb["overlay_type"], "keyboard")
        self.assertFalse(st_kb["is_overlay_active"])

    @patch("subprocess.run")
    def test_dump_ui_hierarchy_ex_and_find_ui_element(self, mock_run):
        xml_content = (
            '<hierarchy><node text="Simpan Transaksi" resource-id="com.example.app:id/btn_save" '
            'content-desc="Tombol Simpan" class="android.widget.Button" clickable="true" enabled="true" '
            'bounds="[100,500][400,600]"/>'
            '<node text="Hapus Data" resource-id="com.example.app:id/btn_delete" '
            'content-desc="Hapus" class="android.widget.Button" clickable="true" enabled="false" '
            'bounds="[100,700][400,800]"/></hierarchy>'
        )

        def side_effect(cmd, *args, **kwargs):
            mock_proc = MagicMock(returncode=0)
            if "uiautomator" in cmd:
                mock_proc.stdout = "UI hierchary dumped to: /sdcard/dump.xml"
            elif "exec-out" in cmd and "cat" in cmd:
                mock_proc.stdout = xml_content
            else:
                mock_proc.stdout = ""
            return mock_proc

        mock_run.side_effect = side_effect
        manager = ADBManager(adb_path="mock_adb")

        # Test search by text contains
        res = manager.find_ui_element(query="Simpan", search_by="text", match_mode="contains")
        self.assertEqual(res["status"], "success")
        self.assertEqual(res["code"], "OK")
        self.assertEqual(res["match_count"], 1)
        match = res["matches"][0]
        self.assertEqual(match["text"], "Simpan Transaksi")
        self.assertEqual(match["center"], [250, 550])

        # Test search by resource_id
        res_id = manager.find_ui_element(query="btn_save", search_by="resource_id")
        self.assertEqual(res_id["status"], "success")
        self.assertEqual(res_id["match_count"], 1)

        # Test search with include_disabled=False
        res_disabled = manager.find_ui_element(query="Hapus", search_by="text", include_disabled=False)
        self.assertEqual(res_disabled["status"], "error")
        self.assertEqual(res_disabled["code"], "NOT_FOUND")

        # Test search NOT_FOUND
        res_not_found = manager.find_ui_element(query="ElemenTidakAda", search_by="text")
        self.assertEqual(res_not_found["status"], "error")
        self.assertEqual(res_not_found["code"], "NOT_FOUND")

        # Test invalid arguments
        with self.assertRaises(ValueError):
            manager.find_ui_element(query="", search_by="text")
        with self.assertRaises(ValueError):
            manager.find_ui_element(query="test", search_by="invalid_mode")
        with self.assertRaises(ValueError):
            manager.find_ui_element(query="test", match_mode="invalid_match")

        # Test UI_DUMP_FAILED
        mock_proc_fail = MagicMock(returncode=1, stderr="could not get idle state", stdout="")
        mock_run.side_effect = None
        mock_run.return_value = mock_proc_fail
        res_fail = manager.find_ui_element(query="test", retries=0)
        self.assertEqual(res_fail["status"], "error")
        self.assertEqual(res_fail["code"], "UI_DUMP_FAILED")

    @patch("subprocess.run")
    def test_verify_installed_package(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")

        # Case 1: Package not installed
        with patch.object(manager, "get_package_apk_paths", return_value=[]):
            res_not_found = manager.verify_installed_package("com.not.installed")
            self.assertEqual(res_not_found["code"], "PACKAGE_NOT_FOUND")
            self.assertFalse(res_not_found["verified"])

        # Case 2: Release verified (debuggable=false)
        with patch.object(manager, "get_package_apk_paths", return_value=["/data/app/com.test.app/base.apk"]):
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="versionName=1.0.0\nversionCode=10\npkgFlags=[ HAS_CODE ALLOW_CLEAR_USER_DATA ]\n",
            )
            res_rel = manager.verify_installed_package("com.test.app", expect_release=True, expected_version_name="1.0.0")
            self.assertEqual(res_rel["code"], "OK")
            self.assertTrue(res_rel["verified"])
            self.assertFalse(res_rel["debuggable"])

            # Case 3: DEBUGGABLE_MISMATCH (expected release but got debuggable=true)
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="versionName=1.0.0\nversionCode=10\npkgFlags=[ DEBUGGABLE HAS_CODE ]\n",
            )
            res_mismatch = manager.verify_installed_package("com.test.app", expect_release=True)
            self.assertEqual(res_mismatch["code"], "DEBUGGABLE_MISMATCH")
            self.assertFalse(res_mismatch["verified"])

            # Case 4: VERSION_MISMATCH
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="versionName=1.0.0\nversionCode=10\npkgFlags=[ HAS_CODE ]\n",
            )
            res_vm = manager.verify_installed_package("com.test.app", expect_release=True, expected_version_name="2.0.0")
            self.assertEqual(res_vm["code"], "VERSION_MISMATCH")
            self.assertFalse(res_vm["verified"])

            # Case 5: UNKNOWN (flags missing)
            mock_run.return_value = MagicMock(returncode=0, stdout="versionName=1.0.0\n")
            res_unk = manager.verify_installed_package("com.test.app")
            self.assertEqual(res_unk["code"], "UNKNOWN")
            self.assertFalse(res_unk["verified"])

        # Case 6: Invalid package name
        with self.assertRaises(ValueError):
            manager.verify_installed_package("invalid;pkg")

    @patch("subprocess.run")
    def test_grant_runtime_permission(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")

        with patch.object(manager, "get_package_apk_paths", return_value=["/data/app/com.test.app/base.apk"]):
            def side_effect(cmd, *args, **kwargs):
                mock_proc = MagicMock(returncode=0)
                if "dumpsys" in cmd and "package" in cmd:
                    mock_proc.stdout = "requested permissions:\n    android.permission.CAMERA\n    android.permission.RECORD_AUDIO\n"
                elif "getprop" in cmd and "ro.build.version.sdk" in cmd:
                    mock_proc.stdout = "29\n"
                elif "pm" in cmd and "grant" in cmd:
                    mock_proc.stdout = ""
                else:
                    mock_proc.stdout = ""
                return mock_proc

            mock_run.side_effect = side_effect

            # Success grant with normalization (CAMERA -> android.permission.CAMERA)
            res = manager.grant_runtime_permission("com.test.app", "CAMERA", action="grant")
            self.assertEqual(res["code"], "OK")
            self.assertTrue(res["granted"])
            self.assertEqual(res["permission"], "android.permission.CAMERA")

            # Permission not declared in manifest
            res_not_decl = manager.grant_runtime_permission("com.test.app", "ACCESS_FINE_LOCATION")
            self.assertEqual(res_not_decl["code"], "PERMISSION_NOT_DECLARED")
            self.assertFalse(res_not_decl["declared"])

            # Special permission rejected
            res_special = manager.grant_runtime_permission("com.test.app", "SYSTEM_ALERT_WINDOW")
            self.assertEqual(res_special["code"], "UNSUPPORTED_OPERATION")

            # API < 23 rejected
            def side_effect_old_api(cmd, *args, **kwargs):
                mock_proc = MagicMock(returncode=0)
                if "dumpsys" in cmd:
                    mock_proc.stdout = "requested permissions:\n    android.permission.CAMERA\n"
                elif "getprop" in cmd:
                    mock_proc.stdout = "21\n"
                return mock_proc

            mock_run.side_effect = side_effect_old_api
            res_old = manager.grant_runtime_permission("com.test.app", "CAMERA")
            self.assertEqual(res_old["code"], "UNSUPPORTED_OPERATION")

        # Invalid package or permission argument
        with self.assertRaises(ValueError):
            manager.grant_runtime_permission("invalid;pkg", "CAMERA")
        with self.assertRaises(ValueError):
            manager.grant_runtime_permission("com.test.app", "CAMERA;rm")

    @patch("subprocess.run")
    def test_force_stop_app(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")

        # Hard block protection
        res_hard = manager.force_stop_app("android")
        self.assertEqual(res_hard["code"], "PERMISSION_DENIED")

        res_sysui = manager.force_stop_app("com.android.systemui")
        self.assertEqual(res_sysui["code"], "PERMISSION_DENIED")

        # Soft block protection
        res_soft = manager.force_stop_app("com.google.android.gms", allow_system=False)
        self.assertEqual(res_soft["code"], "PERMISSION_DENIED")

        # Success force-stop
        with patch.object(manager, "get_package_apk_paths", return_value=["/data/app/com.test.app/base.apk"]):
            def side_effect_stop(cmd, *args, **kwargs):
                mock_proc = MagicMock(returncode=0)
                if "pidof" in cmd:
                    mock_proc.stdout = ""  # process terminated
                return mock_proc

            mock_run.side_effect = side_effect_stop
            res_ok = manager.force_stop_app("com.test.app")
            self.assertEqual(res_ok["code"], "OK")
            self.assertFalse(res_ok["is_running"])
            self.assertTrue(res_ok["verified"])

            # com.android.vending allowed with warning
            res_vending = manager.force_stop_app("com.android.vending")
            self.assertEqual(res_vending["code"], "OK")
            self.assertIn("warning", res_vending)

        # Invalid package name
        with self.assertRaises(ValueError):
            manager.force_stop_app("invalid;pkg")

    @patch("subprocess.run")
    def test_diagnostics(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")

        # 1. getprop with target
        mock_run.return_value = MagicMock(returncode=0, stdout="Pixel 8\n")
        res_prop = manager.diagnostics("getprop", target="ro.product.model")
        self.assertEqual(res_prop["code"], "OK")
        self.assertEqual(res_prop["result"]["properties"]["ro.product.model"], "Pixel 8")

        # 2. wm_size
        mock_run.return_value = MagicMock(returncode=0, stdout="Physical size: 1080x2400\nOverride size: 720x1600\n")
        res_size = manager.diagnostics("wm_size")
        self.assertEqual(res_size["result"]["physical"], "1080x2400")
        self.assertEqual(res_size["result"]["override"], "720x1600")

        # 3. wm_density
        mock_run.return_value = MagicMock(returncode=0, stdout="Physical density: 420\n")
        res_density = manager.diagnostics("wm_density")
        self.assertEqual(res_density["result"]["physical"], 420)

        # 4. pidof
        mock_run.return_value = MagicMock(returncode=0, stdout="12345 12346\n")
        res_pidof = manager.diagnostics("pidof", target="com.test.app")
        self.assertTrue(res_pidof["result"]["running"])
        self.assertEqual(res_pidof["result"]["pids"], [12345, 12346])

        # 5. ps with filter
        ps_output = "USER PID PPID VSZ RSS WCHAN ADDR S NAME\nu0_a100 1234 1 1000 200 epoll 0 S com.test.app\nu0_a101 5678 1 1000 200 epoll 0 S com.other.app\n"
        mock_run.return_value = MagicMock(returncode=0, stdout=ps_output)
        res_ps = manager.diagnostics("ps", filter_text="test")
        self.assertEqual(res_ps["result"]["count"], 1)
        self.assertEqual(res_ps["result"]["processes"][0]["name"], "com.test.app")

        # 6. dumpsys_window_focus
        mock_run.return_value = MagicMock(returncode=0, stdout="mCurrentFocus=Window{123 u0 com.test/.Main}\nmFocusedApp=App{456 u0 com.test/.Main}\n")
        res_focus = manager.diagnostics("dumpsys_window_focus")
        self.assertIn("com.test/.Main", str(res_focus["result"]["current_focus"]))

        # 7. Safety: forbidden characters rejected
        with self.assertRaises(ValueError):
            manager.diagnostics("getprop", target="ro.model;rm -rf /")
        with self.assertRaises(ValueError):
            manager.diagnostics("ps", filter_text="foo | bar")

        # 8. Safety: invalid action rejected
        with self.assertRaises(ValueError):
            manager.diagnostics("rm_rf")

        # 10. getprop without target (curated props)
        mock_getprop_all = "[ro.product.model]: [Pixel 8]\n[ro.product.brand]: [google]\n[ro.build.version.sdk]: [34]\n"
        mock_run.return_value = MagicMock(returncode=0, stdout=mock_getprop_all)
        res_curated = manager.diagnostics("getprop")
        self.assertEqual(res_curated["code"], "OK")
        self.assertEqual(res_curated["result"]["properties"]["ro.product.model"], "Pixel 8")

        # 11. dumpsys_package_version
        with patch.object(manager, "verify_installed_package", return_value={"version_name": "1.0", "version_code": "1", "debuggable": False, "flags": ["HAS_CODE"]}):
            res_dpv = manager.diagnostics("dumpsys_package_version", target="com.test.app")
            self.assertEqual(res_dpv["code"], "OK")
            self.assertEqual(res_dpv["result"]["package"]["version_name"], "1.0")

        # 12. Timeout and max_output_chars boundary errors
        with self.assertRaises(ValueError):
            manager.diagnostics("getprop", timeout=0)
        with self.assertRaises(ValueError):
            manager.diagnostics("getprop", timeout=70)
        with self.assertRaises(ValueError):
            manager.diagnostics("getprop", max_output_chars=500)
        with self.assertRaises(ValueError):
            manager.diagnostics("getprop", max_output_chars=70000)
        with self.assertRaises(ValueError):
            manager.diagnostics("pidof")  # missing target
        with self.assertRaises(ValueError):
            manager.diagnostics("dumpsys_package_version")  # missing target

    @patch("subprocess.run")
    def test_force_stop_failed_variant(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")
        with patch.object(manager, "get_package_apk_paths", return_value=["/data/app/com.stubborn.app/base.apk"]):
            # pidof continues returning a PID
            mock_run.return_value = MagicMock(returncode=0, stdout="8888\n")
            res = manager.force_stop_app("com.stubborn.app")
            self.assertEqual(res["code"], "FORCE_STOP_FAILED")
            self.assertTrue(res["is_running"])
            self.assertFalse(res["verified"])

    @patch("subprocess.run")
    def test_verify_installed_package_debug_and_version_code_mismatch(self, mock_run):
        manager = ADBManager(adb_path="mock_adb")
        with patch.object(manager, "get_package_apk_paths", return_value=["/data/app/com.test.app/base.apk"]):
            # Case expect_release=False with debuggable=True -> verified=True
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="versionName=1.0.0\nversionCode=10\npkgFlags=[ DEBUGGABLE HAS_CODE ]\n",
            )
            res_dbg_ok = manager.verify_installed_package("com.test.app", expect_release=False)
            self.assertEqual(res_dbg_ok["code"], "OK")
            self.assertTrue(res_dbg_ok["verified"])
            self.assertTrue(res_dbg_ok["debuggable"])

            # Case expected_version_code mismatch
            res_vc_mismatch = manager.verify_installed_package("com.test.app", expect_release=False, expected_version_code="99")
            self.assertEqual(res_vc_mismatch["code"], "VERSION_MISMATCH")
            self.assertFalse(res_vc_mismatch["verified"])

    @patch("subprocess.run")
    def test_get_apk_metadata_with_axml(self, mock_run):
        import zipfile
        manager = ADBManager(adb_path="mock_adb")

        with tempfile.NamedTemporaryFile(suffix=".apk") as tmp_apk:
            with zipfile.ZipFile(tmp_apk.name, "w") as zf:
                zf.writestr("AndroidManifest.xml", b"fake_axml_content")

            with patch("apk_extractor.axml.decode_axml", return_value='<manifest package="com.decoded.app" android:versionName="3.1" android:versionCode="31" android:debuggable="true"/>'):
                meta = manager.get_apk_metadata(tmp_apk.name)
                self.assertEqual(meta["package_name"], "com.decoded.app")
                self.assertEqual(meta["version_name"], "3.1")
                self.assertEqual(meta["version_code"], "31")
                self.assertTrue(meta["debuggable"])
                self.assertTrue(meta["manifest_found"])

            # Test missing manifest
            with zipfile.ZipFile(tmp_apk.name, "w") as zf:
                zf.writestr("some_other_file.txt", b"hello")
            meta_none = manager.get_apk_metadata(tmp_apk.name)
            self.assertFalse(meta_none["manifest_found"])

    @patch("subprocess.run")
    def test_get_apk_metadata_and_install_apk_enrichment(self, mock_run):
        import zipfile
        manager = ADBManager(adb_path="mock_adb")

        with tempfile.NamedTemporaryFile(suffix=".apk") as tmp_apk:
            # Create a mock APK containing minimal AndroidManifest.xml
            with zipfile.ZipFile(tmp_apk.name, "w") as zf:
                zf.writestr("AndroidManifest.xml", b"not_axml_plain_text")

            # get_apk_metadata with fallback
            meta = manager.get_apk_metadata(tmp_apk.name)
            self.assertIn("package_name", meta)

            # Test install_apk enrichment
            mock_proc = MagicMock(returncode=0, stdout="Performing Streamed Install\nSuccess\n", stderr="")
            mock_run.return_value = mock_proc

            with patch.object(manager, "get_apk_metadata", return_value={"package_name": "com.test.app", "version_name": "1.0", "version_code": "1", "debuggable": False}):
                with patch.object(manager, "verify_installed_package", return_value={"status": "success", "code": "OK", "version_name": "1.0", "version_code": "1", "debuggable": False}):
                    ok, code, detail = manager.install_apk(tmp_apk.name, verify=True)
                    self.assertTrue(ok)
                    self.assertEqual(code, "SUCCESS")
                    self.assertEqual(detail["code"], "OK")
                    self.assertEqual(detail["package_name"], "com.test.app")
                    self.assertEqual(detail["verification"], "verified")
                    self.assertFalse(detail["debuggable"])


if __name__ == "__main__":
    unittest.main()
