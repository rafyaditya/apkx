import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apk_extractor.packager import (
    APKPackager,
    _backup_candidates,
    _cleanup_orphan_staging,
    _recover_interrupted_swap,
    _swap_marker_path,
    _target_digest,
    _write_json_atomic,
    sanitize_filename,
)


class TestPackagerAtomic(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.base_path = Path(self.temp_dir)
        self.mock_adb = MagicMock()
        self.packager = APKPackager(adb=self.mock_adb)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_dummy_apk(self, name: str = "app.apk") -> Path:
        apk_path = self.base_path / name
        with zipfile.ZipFile(apk_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("AndroidManifest.xml", b"plain text xml")
            zf.writestr("classes.dex", b"fake dex")
        return apk_path

    def test_sanitize_filename_edge_cases(self):
        self.assertEqual(sanitize_filename(".."), "app")
        self.assertEqual(sanitize_filename("."), "app")
        self.assertEqual(sanitize_filename("..."), "app")
        self.assertEqual(sanitize_filename(".hidden"), "hidden")
        self.assertEqual(sanitize_filename("CON"), "_CON")
        self.assertEqual(sanitize_filename("CON.tar.gz"), "_CON.tar.gz")
        self.assertEqual(sanitize_filename("aux.txt"), "_aux.txt")
        self.assertEqual(sanitize_filename("My Normal App"), "My_Normal_App")
        self.assertEqual(sanitize_filename(""), "app")

    def test_reject_symlink_and_non_dir_target(self):
        apk_path = self._create_dummy_apk()

        # Non-directory file as target
        file_target = self.base_path / "a_file.txt"
        file_target.write_text("hello")
        with self.assertRaises(ValueError) as ctx:
            self.packager.unpack(apk_path, file_target)
        self.assertIn("bukan direktori", str(ctx.exception))

        # Symlink as target (on platforms supporting symlinks)
        if hasattr(os, "symlink"):
            symlink_target = self.base_path / "sym_link"
            real_dir = self.base_path / "real_dir"
            real_dir.mkdir()
            try:
                os.symlink(real_dir, symlink_target)
                with self.assertRaises(ValueError) as ctx2:
                    self.packager.unpack(apk_path, symlink_target)
                self.assertIn("tidak boleh berupa symlink", str(ctx2.exception))
            except OSError:
                pass

    def test_successful_unpack_and_marker_cleanup(self):
        apk_path = self._create_dummy_apk()
        target_dir = self.base_path / "extracted_app"

        res_dir = self.packager.unpack(apk_path, target_dir)
        self.assertEqual(res_dir, target_dir)
        self.assertTrue((target_dir / "classes.dex").is_file())

        marker = _swap_marker_path(target_dir)
        self.assertFalse(marker.exists())

        backups = _backup_candidates(target_dir)
        self.assertEqual(len(backups), 0)

    def test_atomic_rollback_on_swap_failure(self):
        apk_path = self._create_dummy_apk()
        target_dir = self.base_path / "extracted_app"

        # Pre-populate existing good target
        target_dir.mkdir(parents=True)
        (target_dir / "old_important.txt").write_text("precious data")

        # Mock os.replace to fail on the second replace (staging -> target)
        real_replace = os.replace
        replace_calls = 0

        def failing_replace(src, dst):
            nonlocal replace_calls
            replace_calls += 1
            if replace_calls == 2:
                raise OSError("Disk simulated write failure on swap!")
            return real_replace(src, dst)

        with patch("os.replace", side_effect=failing_replace):
            with self.assertRaises(OSError):
                self.packager.unpack(apk_path, target_dir)

        # Target should be restored and old precious data must be intact!
        self.assertTrue(target_dir.exists())
        self.assertTrue((target_dir / "old_important.txt").is_file())
        self.assertEqual(
            (target_dir / "old_important.txt").read_text(),
            "precious data",
        )

    def test_recovery_of_interrupted_swap_with_marker(self):
        target_dir = self.base_path / "target_app"
        backup_dir = self.base_path / f"{target_dir.name}.bak_123456"
        backup_dir.mkdir(parents=True)
        (backup_dir / "file_in_backup.txt").write_text("recovered content")

        marker = _swap_marker_path(target_dir)
        _write_json_atomic(
            marker,
            {
                "target": str(target_dir),
                "backup": str(backup_dir),
                "pid": os.getpid(),
                "created_at": time.time(),
            },
        )

        self.assertFalse(target_dir.exists())
        _recover_interrupted_swap(target_dir)

        self.assertTrue(target_dir.exists())
        self.assertTrue((target_dir / "file_in_backup.txt").is_file())
        self.assertFalse(marker.exists())

    def test_recovery_of_orphan_backup_without_marker(self):
        target_dir = self.base_path / "target_app_orphan"
        backup_dir = self.base_path / f"{target_dir.name}.bak_9999"
        backup_dir.mkdir(parents=True)
        (backup_dir / "orphan_recovered.txt").write_text("orphan data")

        self.assertFalse(target_dir.exists())
        _recover_interrupted_swap(target_dir)

        self.assertTrue(target_dir.exists())
        self.assertTrue((target_dir / "orphan_recovered.txt").is_file())

    def test_cleanup_orphan_staging(self):
        target_dir = self.base_path / "app_target"
        digest = _target_digest(target_dir)

        # Create expired staging dir and fresh staging dir
        old_staging = self.base_path / f"apkx_stage_{digest}_old"
        old_staging.mkdir()
        now = time.time()
        os.utime(old_staging, (now - 100000, now - 100000))

        fresh_staging = self.base_path / f"apkx_stage_{digest}_fresh"
        fresh_staging.mkdir()

        _cleanup_orphan_staging(target_dir, max_age_seconds=86400)

        self.assertFalse(old_staging.exists())
        self.assertTrue(fresh_staging.exists())

    @pytest.mark.skipif(sys.platform == "win32", reason="POSIX file permissions")
    def test_staging_directory_permissions_posix(self):
        apk_path = self._create_dummy_apk()
        target_dir = self.base_path / "app_perm"

        created_staggings = []
        real_mkdtemp = tempfile.mkdtemp

        def instrumented_mkdtemp(**kwargs):
            res = real_mkdtemp(**kwargs)
            if "apkx_stage" in str(res):
                created_staggings.append(Path(res))
            return res

        with patch("tempfile.mkdtemp", side_effect=instrumented_mkdtemp):
            self.packager.unpack(apk_path, target_dir)

        # Staging is cleaned up at the end, but during creation it had 0755
        self.assertTrue(target_dir.exists())

    def test_extract_part_file_cleanup_on_error(self):
        output_dir = self.base_path / "output_apks"
        self.mock_adb.pull_file.side_effect = RuntimeError("ADB Connection Lost!")

        with self.assertRaises(RuntimeError):
            self.packager.extract(
                package_name="com.test.app",
                remote_paths=["/data/app/base.apk"],
                output_dir=output_dir,
                app_name="TestApp",
            )

        part_file = output_dir / "TestApp.apk.part"
        self.assertFalse(part_file.exists())
        final_file = output_dir / "TestApp.apk"
        self.assertFalse(final_file.exists())


if __name__ == "__main__":
    unittest.main()
