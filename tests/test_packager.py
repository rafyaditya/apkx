import io
import json
import os
import shutil
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_generate_analysis_summary_with_endpoints_and_manifest(self):
        test_dir = self.temp_out_dir / "extracted_summary"
        test_dir.mkdir(parents=True, exist_ok=True)

        manifest_file = test_dir / "AndroidManifest.xml"
        manifest_file.write_text('<manifest package="com.test.summary"><uses-permission android:name="android.permission.INTERNET"/></manifest>', encoding="utf-8")

        dex_file = test_dir / "classes.dex"
        dex_file.write_bytes(b"dummy code with https://api.service.com/v1/data inside")

        summary = self.packager.generate_analysis_summary(test_dir, "SummaryApp", "com.test.summary")

        self.assertTrue((test_dir / "endpoints.json").exists())
        self.assertTrue((test_dir / "analysis_info.json").exists())
        self.assertTrue((test_dir / "README_ANALISIS.txt").exists())
        self.assertTrue((test_dir / "AndroidManifest_readable.xml").exists())
        self.assertGreaterEqual(summary.get("total_urls", 0), 1)

    def test_extract_sqlite_schema_nested_parentheses_and_quotes(self):
        from apk_extractor.packager import extract_sqlite_schema_from_dir
        test_dir = self.temp_out_dir / "extracted_sqlite"
        test_dir.mkdir(parents=True, exist_ok=True)

        mock_so = test_dir / "libapp.so"
        sql_payload = (
            b"\x00" * 20
            + b'CREATE TABLE "users" (id INTEGER PRIMARY KEY, name VARCHAR(100), email TEXT)'
            + b"\x00" * 20
            + b'CREATE TABLE [transactions] (id INTEGER PRIMARY KEY, note VARCHAR(255), amount DECIMAL(10, 2), detail TEXT)'
            + b"\x00" * 20
        )
        mock_so.write_bytes(sql_payload)

        schema = extract_sqlite_schema_from_dir(test_dir)
        self.assertEqual(schema["total_tables"], 2)
        self.assertIn("users", schema["tables"])
        self.assertIn("transactions", schema["tables"])

        tx_cols = schema["tables"]["transactions"]
        # Verify no truncation occurred on note VARCHAR(255)
        self.assertIn("note VARCHAR(255)", tx_cols)
        self.assertIn("amount DECIMAL(10, 2)", tx_cols)
        self.assertIn("detail TEXT", tx_cols)

    def test_clean_re_extraction_purges_stale_files(self):
        target_dir = self.temp_out_dir / "target_app"
        target_dir.mkdir(parents=True, exist_ok=True)
        # Create stale files from previous run
        (target_dir / "stale_file.txt").write_text("old data", encoding="utf-8")
        stale_sub = target_dir / "old_split"
        stale_sub.mkdir()
        (stale_sub / "old.dex").write_bytes(b"old dex data")

        # Create new APK
        apk_path = self.temp_out_dir / "new_app.apk"
        with zipfile.ZipFile(apk_path, "w") as zf:
            zf.writestr("classes.dex", b"new dex data")

        self.packager.unpack(apk_path, target_dir)

        # Verify old files are gone and new files exist
        self.assertFalse((target_dir / "stale_file.txt").exists(), "Stale file should be purged")
        self.assertFalse((stale_sub / "old.dex").exists(), "Stale subfolder file should be purged")
        self.assertTrue((target_dir / "classes.dex").exists(), "New unpacked file should exist")
        self.assertEqual((target_dir / "classes.dex").read_bytes(), b"new dex data")

    def test_unpack_corrupt_archive_preserves_existing_target(self):
        target_dir = self.temp_out_dir / "preserve_existing_target"
        target_dir.mkdir(parents=True, exist_ok=True)

        important_file = target_dir / "important_data.txt"
        important_file.write_text("precious existing data", encoding="utf-8")
        important_sub = target_dir / "existing_subdir"
        important_sub.mkdir()
        (important_sub / "nested.txt").write_text("nested data", encoding="utf-8")

        # 1. Unpack corrupt .apk (invalid zip) -> should raise BadZipFile and preserve target_dir
        corrupt_apk = self.temp_out_dir / "corrupted.apk"
        corrupt_apk.write_bytes(b"PK\x03\x04corrupted-archive-garbage-content")

        with self.assertRaises(zipfile.BadZipFile):
            self.packager.unpack(corrupt_apk, target_dir)

        self.assertTrue(important_file.exists(), "File must not be deleted if unpack fails")
        self.assertEqual(important_file.read_text(encoding="utf-8"), "precious existing data")
        self.assertTrue((important_sub / "nested.txt").exists(), "Subdirectory must remain untouched")

        # 2. Unpack unsupported archive extension (.zip) -> should raise ValueError and preserve target_dir
        unsupported_zip = self.temp_out_dir / "unsupported.zip"
        with zipfile.ZipFile(unsupported_zip, "w") as zf:
            zf.writestr("test.txt", "dummy content")

        with self.assertRaises(ValueError):
            self.packager.unpack(unsupported_zip, target_dir)

        self.assertTrue(important_file.exists())
        self.assertTrue((important_sub / "nested.txt").exists())

        # 3. Unpack non-existent archive -> should raise FileNotFoundError and preserve target_dir
        non_existent = self.temp_out_dir / "non_existent.apk"
        with self.assertRaises(FileNotFoundError):
            self.packager.unpack(non_existent, target_dir)

        self.assertTrue(important_file.exists())
        self.assertTrue((important_sub / "nested.txt").exists())

        # 4. Unpack empty .apks bundle (no .apk inside) -> should raise ValueError and preserve target_dir
        empty_apks = self.temp_out_dir / "empty_bundle.apks"
        with zipfile.ZipFile(empty_apks, "w") as zf:
            zf.writestr("not_an_apk.txt", "nothing")

        with self.assertRaises(ValueError):
            self.packager.unpack(empty_apks, target_dir)

        self.assertTrue(important_file.exists())
        self.assertTrue((important_sub / "nested.txt").exists())

    def test_framework_detection_variants(self):
        # Unity
        unity_dir = self.temp_out_dir / "unity_app"
        unity_dir.mkdir()
        (unity_dir / "lib" / "arm64").mkdir(parents=True)
        (unity_dir / "lib" / "arm64" / "libunity.so").touch()
        fw = self.packager.detect_framework(unity_dir)
        self.assertIn("Unity", fw["framework"])

        # React Native with Hermes bytecode
        rn_dir = self.temp_out_dir / "rn_hermes"
        (rn_dir / "assets").mkdir(parents=True)
        (rn_dir / "assets" / "index.android.bundle").write_bytes(b"\xc6\x1f\xbc\x03" + b"hermes_code")
        fw_rn = self.packager.detect_framework(rn_dir)
        self.assertIn("Hermes", fw_rn["framework"])

        # Native fallback with dex
        native_dir = self.temp_out_dir / "native_app"
        native_dir.mkdir()
        (native_dir / "classes.dex").touch()
        fw = self.packager.detect_framework(native_dir)
        self.assertIn("Native Android", fw["framework"])

    def test_extract_error_cleanup(self):
        from apk_extractor.adb import ADBError
        self.mock_adb.pull_file.side_effect = ADBError("ADB Pull Failed")

        # Single APK
        with self.assertRaises(ADBError):
            self.packager.extract(
                package_name="com.fail.single",
                remote_paths=["/data/app/base.apk"],
                output_dir=self.temp_out_dir,
            )
        # Part file should be cleaned up
        parts = list(self.temp_out_dir.glob("*.part"))
        self.assertEqual(parts, [])

        # Split APK
        with self.assertRaises(ADBError):
            self.packager.extract(
                package_name="com.fail.split",
                remote_paths=["/data/app/base.apk", "/data/app/split.apk"],
                output_dir=self.temp_out_dir,
            )

    def test_unpack_with_progress(self):
        apk_path = self.temp_out_dir / "progress.apk"
        with zipfile.ZipFile(apk_path, "w") as zf:
            zf.writestr("test1.txt", "data")
            zf.writestr("test2.txt", "data")

        unpack_dir = self.temp_out_dir / "progress_extracted"
        progress_calls = []
        self.packager.unpack(apk_path, unpack_dir, progress_callback=lambda msg, cur, tot: progress_calls.append((msg, cur, tot)))
        self.assertTrue(len(progress_calls) > 0)

    def test_unpack_apks_multi_split(self):
        apks_path = self.temp_out_dir / "split_bundle.apks"
        base_bytes = io.BytesIO()
        with zipfile.ZipFile(base_bytes, "w") as bzf:
            bzf.writestr("AndroidManifest.xml", "<manifest package='com.test'></manifest>")
            bzf.writestr("classes.dex", b"base dex")

        split_bytes = io.BytesIO()
        with zipfile.ZipFile(split_bytes, "w") as szf:
            szf.writestr("AndroidManifest.xml", "<manifest package='com.test'></manifest>")
            szf.writestr("lib/arm64-v8a/libtest.so", b"dummy so")

        with zipfile.ZipFile(apks_path, "w") as azf:
            azf.writestr("base.apk", base_bytes.getvalue())
            azf.writestr("split_config.arm64_v8a.apk", split_bytes.getvalue())

        unpack_dir = self.temp_out_dir / "split_extracted"
        self.packager.unpack(apks_path, unpack_dir)

        self.assertTrue((unpack_dir / "base" / "classes.dex").exists())
        self.assertTrue((unpack_dir / "split_config.arm64_v8a" / "lib" / "arm64-v8a" / "libtest.so").exists())
        self.assertTrue((unpack_dir / "AndroidManifest_readable.xml").exists())

    @patch("apk_extractor.packager.extract_apk_label", return_value="Official Label")
    def test_extract_official_label_renaming(self, mock_label):
        def fake_pull(remote, local, device_id=None):
            Path(local).write_bytes(b"dummy apk")

        self.mock_adb.pull_file.side_effect = fake_pull
        res = self.packager.extract(
            package_name="com.test.app",
            remote_paths=["/data/app/base.apk"],
            output_dir=self.temp_out_dir,
            app_name="Old_Label",
        )
        self.assertEqual(res.app_name, "Official Label")
        self.assertEqual(res.output_path.name, "Official_Label.apk")
        self.assertTrue(res.output_path.exists())

    def test_generate_analysis_summary_with_sqlite_tables(self):
        target_dir = self.temp_out_dir / "summary_sqlite"
        target_dir.mkdir(parents=True)
        (target_dir / "AndroidManifest.xml").write_text("<manifest package='com.test'></manifest>", encoding="utf-8")
        (target_dir / "classes.dex").write_bytes(b"code")

        with patch("apk_extractor.packager.extract_sqlite_schema_from_dir", return_value={
            "total_tables": 2,
            "tables": {"accounts": ["id", "name"], "transactions": ["id", "amount"]},
            "raw_statements": ["CREATE TABLE accounts(id INT, name TEXT);", "CREATE TABLE transactions(id INT, amount REAL);"],
        }):
            self.packager.generate_analysis_summary(target_dir, "SqliteApp", "com.test.sqlite")
            data = json.loads((target_dir / "analysis_info.json").read_text(encoding="utf-8"))
            self.assertEqual(data["sqlite_tables_count"], 2)
            self.assertTrue((target_dir / "sqlite_schema.json").exists())
            self.assertTrue((target_dir / "sqlite_schema.sql").exists())
            self.assertTrue((target_dir / "README_ANALISIS.txt").exists())
            readme_text = (target_dir / "README_ANALISIS.txt").read_text(encoding="utf-8")
            self.assertIn("2 tabel terdeteksi", readme_text)

    def test_cleanup_orphan_staging_temporary_marker_files(self):
        from apk_extractor.packager import _cleanup_orphan_staging, _target_digest
        target = self.temp_out_dir / "marker_cleanup_app"
        digest = _target_digest(target)
        tmp_marker = self.temp_out_dir / f".apkx_swap_{digest}.json.tmp_test_123"
        tmp_marker.touch()
        old_time = time.time() - 200000
        os.utime(tmp_marker, (old_time, old_time))

        _cleanup_orphan_staging(target, max_age_seconds=86400)
        self.assertFalse(tmp_marker.exists())

    def test_recover_interrupted_swap_corrupt_marker(self):
        from apk_extractor.packager import _recover_interrupted_swap, _swap_marker_path
        target = self.temp_out_dir / "corrupt_marker_app"
        marker = _swap_marker_path(target)
        marker.write_text("invalid json content {{{", encoding="utf-8")

        # Calling _recover_interrupted_swap should not raise exception
        _recover_interrupted_swap(target)


if __name__ == "__main__":
    unittest.main()
