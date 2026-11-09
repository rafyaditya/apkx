import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from apk_extractor.archive_utils import (
    WINDOWS_RESERVED_NAMES,
    safe_extract_zip,
    sanitize_archive_member_path,
)


class TestArchiveUtils(unittest.TestCase):
    def test_windows_reserved_names_set(self):
        self.assertIn("CON", WINDOWS_RESERVED_NAMES)
        self.assertIn("PRN", WINDOWS_RESERVED_NAMES)
        self.assertIn("NUL", WINDOWS_RESERVED_NAMES)

    def test_sanitize_zip_slip_and_traversal(self):
        self.assertEqual(
            sanitize_archive_member_path("../../etc/passwd"),
            Path("etc/passwd"),
        )
        self.assertEqual(
            sanitize_archive_member_path("/absolute/path/file.txt"),
            Path("absolute/path/file.txt"),
        )
        self.assertEqual(
            sanitize_archive_member_path("..\\..\\windows\\system32\\calc.exe"),
            Path("windows/system32/calc.exe"),
        )

    def test_sanitize_null_byte_and_empty(self):
        self.assertEqual(sanitize_archive_member_path("evil\x00file"), Path())
        self.assertEqual(sanitize_archive_member_path(""), Path())
        self.assertEqual(sanitize_archive_member_path("."), Path())
        self.assertEqual(sanitize_archive_member_path(".."), Path())

    def test_sanitize_windows_prefixes_and_drive(self):
        self.assertEqual(
            sanitize_archive_member_path("//?/C:/foo/bar.txt"),
            Path("foo/bar.txt"),
        )
        self.assertEqual(
            sanitize_archive_member_path("C:\\foo\\bar.txt"),
            Path("foo/bar.txt"),
        )
        self.assertEqual(
            sanitize_archive_member_path("/./relative/path.txt"),
            Path("relative/path.txt"),
        )

    def test_sanitize_colon_ntfs_ads(self):
        self.assertEqual(
            sanitize_archive_member_path("foo:bar"),
            Path("foo_bar"),
        )
        self.assertEqual(
            sanitize_archive_member_path("dir/foo:bar:baz"),
            Path("dir/foo_bar_baz"),
        )

    def test_sanitize_windows_reserved_names_multi_dot(self):
        self.assertEqual(
            sanitize_archive_member_path("CON.tar.gz"),
            Path("_CON.tar.gz"),
        )
        self.assertEqual(
            sanitize_archive_member_path("prn.txt"),
            Path("_prn.txt"),
        )
        self.assertEqual(
            sanitize_archive_member_path("aux"),
            Path("_aux"),
        )
        self.assertEqual(
            sanitize_archive_member_path("path/NUL.bin"),
            Path("path/_NUL.bin"),
        )

    def test_sanitize_hidden_files_preserved(self):
        self.assertEqual(
            sanitize_archive_member_path(".hidden"),
            Path(".hidden"),
        )
        self.assertEqual(
            sanitize_archive_member_path("folder/.bashrc"),
            Path("folder/.bashrc"),
        )

    def test_safe_extract_zip_normal(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("test.txt", b"Hello, World!")
            zf.writestr("sub/nested.txt", b"Nested content")

        buf.seek(0)
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "output"
            with zipfile.ZipFile(buf, "r") as zf:
                count = safe_extract_zip(zf, target)

            self.assertEqual(count, 2)
            self.assertTrue((target / "test.txt").is_file())
            self.assertTrue((target / "sub/nested.txt").is_file())
            self.assertEqual(
                (target / "test.txt").read_bytes(), b"Hello, World!"
            )

    def test_safe_extract_zip_bomb_total_size(self):
        class FakeMember:
            filename = "bomb.bin"
            file_size = 9 * 1024 * 1024 * 1024
            compress_size = 1024

            def is_dir(self):
                return False

        class FakeZip:
            def infolist(self):
                return [FakeMember()]

        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError) as ctx:
                safe_extract_zip(FakeZip(), Path(tmp_dir))  # type: ignore[arg-type]
            self.assertIn("melebihi batas ukuran", str(ctx.exception))

    def test_safe_extract_zip_bomb_compression_ratio(self):
        class FakeMember:
            filename = "bomb_ratio.bin"
            file_size = 20 * 1024 * 1024  # 20MB (>10MB threshold)
            compress_size = 10  # ratio = 2,000,000 (>1000)

            def is_dir(self):
                return False

        class FakeZip:
            def infolist(self):
                return [FakeMember()]

        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError) as ctx:
                safe_extract_zip(FakeZip(), Path(tmp_dir))  # type: ignore[arg-type]
            self.assertIn("Rasio kompresi mencurigakan", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
