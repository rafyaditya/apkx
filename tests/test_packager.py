import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

from apk_extractor.adb import ADBManager
from apk_extractor.packager import APKPackager, sanitize_filename


class TestAPKPackager(unittest.TestCase):
    def setUp(self):
        self.mock_adb = MagicMock(spec=ADBManager)
        self.packager = APKPackager(self.mock_adb)
        self.temp_out_dir = Path(tempfile.mkdtemp(prefix="apkx_test_out_"))

    def tearDown(self):
        if self.temp_out_dir.exists():
            shutil.rmtree(self.temp_out_dir, ignore_errors=True)

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("Easy Budget"), "Easy_Budget")
        self.assertEqual(sanitize_filename("WhatsApp: Test/App?"), "WhatsApp_TestApp")
        self.assertEqual(sanitize_filename(""), "app")

    def test_single_apk_extraction_with_app_name(self):
        package_name = "com.example.single"
        app_name = "My App"
        remote_paths = ["/data/app/com.example.single/base.apk"]

        def fake_pull(remote, local, device_id=None):
            Path(local).write_bytes(b"dummy apk content")

        self.mock_adb.pull_file.side_effect = fake_pull

        res = self.packager.extract(
            package_name=package_name,
            remote_paths=remote_paths,
            output_dir=self.temp_out_dir,
            app_name=app_name,
        )

        self.assertFalse(res.is_split)
        self.assertEqual(res.app_name, app_name)
        self.assertEqual(res.output_path.name, "My_App.apk")
        self.assertTrue(res.output_path.exists())

    def test_split_apk_extraction_with_app_name(self):
        package_name = "com.blodhgard.easybudget"
        app_name = "Easybudget"
        remote_paths = [
            "/data/app/com.blodhgard.easybudget/base.apk",
            "/data/app/com.blodhgard.easybudget/split_config.arm64_v8a.apk",
        ]

        def fake_pull(remote, local, device_id=None):
            # Write a valid zip file for each split
            p = Path(local)
            with zipfile.ZipFile(p, "w") as zf:
                zf.writestr("AndroidManifest.xml", "dummy manifest")

        self.mock_adb.pull_file.side_effect = fake_pull

        res = self.packager.extract(
            package_name=package_name,
            remote_paths=remote_paths,
            output_dir=self.temp_out_dir,
            app_name=app_name,
        )

        self.assertTrue(res.is_split)
        self.assertEqual(res.output_path.name, "Easybudget.apks")
        self.assertTrue(res.output_path.exists())

    def test_unpack_and_detect_flutter(self):
        # Create a mock APK containing Flutter assets
        apk_path = self.temp_out_dir / "flutter_app.apk"
        with zipfile.ZipFile(apk_path, "w") as zf:
            zf.writestr("AndroidManifest.xml", "manifest")
            zf.writestr("lib/arm64-v8a/libapp.so", b"\x7fELF flutter binary")
            zf.writestr("assets/flutter_assets/AssetManifest.json", "{}")

        unpack_dir = self.temp_out_dir / "extracted_flutter"
        self.packager.unpack(apk_path, unpack_dir)

        self.assertTrue((unpack_dir / "AndroidManifest.xml").exists())
        self.assertTrue((unpack_dir / "lib" / "arm64-v8a" / "libapp.so").exists())

        fw = self.packager.detect_framework(unpack_dir)
        self.assertIn("Flutter", fw["framework"])

    def test_unpack_and_detect_react_native(self):
        apk_path = self.temp_out_dir / "rn_app.apk"
        with zipfile.ZipFile(apk_path, "w") as zf:
            zf.writestr("AndroidManifest.xml", "manifest")
            zf.writestr("assets/index.android.bundle", b"var __BUNDLE_START__=true;")

        unpack_dir = self.temp_out_dir / "extracted_rn"
        self.packager.unpack(apk_path, unpack_dir)

        fw = self.packager.detect_framework(unpack_dir)
        self.assertIn("React Native", fw["framework"])


if __name__ == "__main__":
    unittest.main()
