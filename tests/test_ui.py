import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apk_extractor.app_names import AppInfo
from apk_extractor.ui import (
    print_banner,
    select_device,
    select_devices,
    select_package_interactive,
    show_app_info,
    show_devices_table,
    show_error,
    show_no_device_help,
    show_package_table,
    show_success_summary,
    show_unauthorized_device_help,
    show_warning,
)


class TestUI(unittest.TestCase):
    def test_banners_and_alerts(self):
        print_banner()
        show_error("Testing error display")
        show_warning("Testing warning display")
        show_no_device_help()
        show_unauthorized_device_help("emulator-5554")

    def test_show_devices_table(self):
        devices = [
            {
                "serial": "emulator-5554",
                "status": "device",
                "brand": "Google",
                "model": "Pixel 7",
                "android_version": "14",
            },
            {
                "serial": "unauth-device",
                "status": "unauthorized",
                "brand": "-",
                "model": "Unknown",
                "android_version": "-",
            },
            {
                "serial": "offline-device",
                "status": "offline",
                "brand": "Samsung",
                "model": "-",
                "android_version": "13",
            },
            {
                "serial": "other-device",
                "status": "other",
                "brand": "-",
                "model": "-",
                "android_version": "-",
            },
        ]
        show_devices_table(devices)

    def test_show_package_table(self):
        packages = ["com.android.settings", "com.whatsapp", "org.mozilla.firefox"]
        show_package_table(packages)

        apps = [
            AppInfo(app_name="App One", package_name="com.app.one"),
            AppInfo(app_name="App Two", package_name="com.app.two"),
        ]
        show_package_table(apps)

    @patch("questionary.select")
    def test_select_device(self, mock_select):
        # 1 device
        self.assertEqual(select_device([("dev1", "device")]), "dev1")

        # Multiple devices, none authorized
        self.assertIsNone(select_device([("dev1", "offline"), ("dev2", "offline")]))

        # Multiple devices
        mock_prompt = MagicMock()
        mock_prompt.ask.return_value = "dev2 (device)"
        mock_select.return_value = mock_prompt
        self.assertEqual(select_device([("dev1", "device"), ("dev2", "device")]), "dev2")

        # Cancelled
        mock_prompt.ask.return_value = None
        self.assertIsNone(select_device([("dev1", "device"), ("dev2", "device")]))

    @patch("questionary.select")
    def test_select_devices(self, mock_select):
        devices = [
            {"serial": "dev1", "status": "device", "brand": "Google", "model": "Pixel", "android_version": "14"},
            {"serial": "dev2", "status": "device", "brand": "-", "model": "Moto", "android_version": "13"},
            {"serial": "dev3", "status": "offline", "brand": "-", "model": "-", "android_version": "-"},
        ]

        # Single device authorized
        single = [{"serial": "dev1", "status": "device"}]
        self.assertEqual(select_devices(single), single)

        # None authorized
        self.assertIsNone(select_devices([{"serial": "dev3", "status": "offline"}]))

        # Select ALL
        mock_prompt = MagicMock()
        mock_prompt.ask.return_value = "ALL"
        mock_select.return_value = mock_prompt
        res = select_devices(devices)
        self.assertEqual(len(res), 2)

        # Select specific
        mock_prompt.ask.return_value = "dev2"
        res = select_devices(devices)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["serial"], "dev2")

        # Cancel / None
        mock_prompt.ask.return_value = None
        self.assertIsNone(select_devices(devices))

        # KeyboardInterrupt
        mock_prompt.ask.side_effect = KeyboardInterrupt
        self.assertIsNone(select_devices(devices))

    @patch("questionary.select")
    def test_select_package_interactive(self, mock_select):
        apps = [
            AppInfo(app_name="App One", package_name="com.app.one"),
            "com.app.str",
        ]
        mock_prompt = MagicMock()
        mock_prompt.ask.return_value = "com.app.one"
        mock_select.return_value = mock_prompt

        chosen = select_package_interactive(apps, prefilter_query="app")
        self.assertEqual(chosen, "com.app.one")

        # Empty apps
        self.assertIsNone(select_package_interactive([]))

        # KeyboardInterrupt
        mock_prompt.ask.side_effect = KeyboardInterrupt
        self.assertIsNone(select_package_interactive(apps))

    def test_show_success_summary(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "test.apks"
            extract_dir = Path(tmp_dir) / "extracted"
            fw = {
                "framework": "Flutter",
                "code_path": "libapp.so",
                "decoded_manifest": "AndroidManifest.xml",
                "total_classes": 100,
                "app_classes_count": 50,
                "total_urls": 12,
                "description": "Flutter app with Dart AOT",
            }

            show_success_summary(
                package_name="com.example.app",
                output_path=out_file,
                is_split=True,
                total_parts=3,
                size_str="12.5 MB",
                app_name="Example App",
                extracted_folder=extract_dir,
                framework_info=fw,
            )

    def test_show_app_info(self):
        info = {
            "package_name": "com.example.app",
            "app_name": "Example App",
            "version_name": "1.0.0",
            "version_code": "100",
            "min_sdk": "21",
            "target_sdk": "34",
            "installed_time": "2024-01-01",
            "updated_time": "2024-02-01",
            "apk_format": "Split APK (3 parts)",
            "apk_paths": ["/data/app/base.apk", "/data/app/split.apk"],
            "launcher_activity": "com.example.app.MainActivity",
            "framework": "Flutter",
            "permissions": [f"android.permission.PERM_{i}" for i in range(15)],
        }
        show_app_info(info)


if __name__ == "__main__":
    unittest.main()
