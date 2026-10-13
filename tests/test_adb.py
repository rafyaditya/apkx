import unittest
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


if __name__ == "__main__":
    unittest.main()
