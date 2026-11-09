import hashlib
import io
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from apk_extractor.jadx import JADXManager, find_jadx_binary


class TestJADXManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="apkx_test_jadx_"))

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_jadx_binary_custom(self):
        self.assertEqual(find_jadx_binary("/custom/path/jadx"), "/custom/path/jadx")

    @patch("shutil.which")
    def test_find_jadx_binary_system(self, mock_which):
        mock_which.return_value = "/usr/bin/jadx"
        self.assertEqual(find_jadx_binary(), "/usr/bin/jadx")

    @patch("pathlib.Path.is_file")
    @patch("shutil.which", return_value=None)
    def test_find_jadx_binary_cached(self, mock_which, mock_is_file):
        mock_is_file.return_value = True
        res = find_jadx_binary()
        self.assertTrue(res.endswith("jadx") or res.endswith("jadx.bat"))

    @patch("pathlib.Path.is_file", return_value=False)
    @patch("shutil.which", return_value=None)
    def test_find_jadx_binary_fallback(self, mock_which, mock_is_file):
        res = find_jadx_binary()
        self.assertIn("jadx", res)

    @patch("shutil.which")
    def test_has_java(self, mock_which):
        mock_which.return_value = "/usr/bin/java"
        self.assertTrue(JADXManager.has_java())

        mock_which.return_value = None
        self.assertFalse(JADXManager.has_java())

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/java")
    def test_is_installed(self, mock_which, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "jadx 1.5.6"
        mock_run.return_value = mock_proc

        manager = JADXManager(jadx_path="mock_jadx")
        self.assertTrue(manager.is_installed())

        # No java
        mock_which.return_value = None
        self.assertFalse(manager.is_installed())

        # Subprocess exception
        mock_which.return_value = "/usr/bin/java"
        mock_run.side_effect = FileNotFoundError("Not found")
        with patch("apk_extractor.jadx.find_jadx_binary", return_value="jadx"):
            self.assertFalse(manager.is_installed())

    def test_ensure_installed(self):
        manager = JADXManager(jadx_path="mock_jadx")

        # Case 1: Already installed
        with patch.object(manager, "is_installed", return_value=True):
            self.assertTrue(manager.ensure_installed())

        # Case 2: Not installed, no java
        messages = []
        with patch.object(manager, "is_installed", return_value=False), patch.object(manager, "has_java", return_value=False):
            self.assertFalse(manager.ensure_installed(on_progress=messages.append))
            self.assertTrue(any("Java Runtime Environment" in m for m in messages))

        # Case 3: Download succeeds
        with patch.object(manager, "is_installed", side_effect=[False, True]), \
             patch.object(manager, "has_java", return_value=True), \
             patch.object(manager, "download_jadx", return_value=True):
            self.assertTrue(manager.ensure_installed())

        # Case 4: Download fails
        with patch.object(manager, "is_installed", return_value=False), \
             patch.object(manager, "has_java", return_value=True), \
             patch.object(manager, "download_jadx", return_value=False):
            self.assertFalse(manager.ensure_installed())

    def test_download_jadx_success(self):
        # Create a real in-memory zip
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("bin/jadx", "#!/bin/sh\necho jadx")
        zip_bytes = zip_buf.getvalue()
        real_hash = hashlib.sha256(zip_bytes).hexdigest()

        with patch("pathlib.Path.home", return_value=self.temp_dir), \
             patch("apk_extractor.jadx.JADX_SHA256", real_hash), \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read = io.BytesIO(zip_bytes).read
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            progress = []
            res = JADXManager.download_jadx(on_progress=progress.append)
            self.assertTrue(res)
            self.assertTrue((self.temp_dir / ".apkx" / "jadx" / "bin" / "jadx").exists())

    def test_download_jadx_checksum_fail(self):
        zip_bytes = b"corrupted content"

        with patch("pathlib.Path.home", return_value=self.temp_dir), \
             patch("apk_extractor.jadx.JADX_SHA256", "wrong_hash"), \
             patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read = io.BytesIO(zip_bytes).read
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            progress = []
            res = JADXManager.download_jadx(on_progress=progress.append)
            self.assertFalse(res)
            self.assertTrue(any("gagal" in m.lower() for m in progress))

    def test_download_jadx_exception(self):
        with patch("pathlib.Path.home", return_value=self.temp_dir), \
             patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            progress = []
            res = JADXManager.download_jadx(on_progress=progress.append)
            self.assertFalse(res)
            self.assertTrue(any("Gagal mengunduh" in m for m in progress))

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/java")
    def test_decompile_class(self, mock_which, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        manager = JADXManager(jadx_path="mock_jadx")
        manager.is_installed = MagicMock(return_value=True)

        # Mock generated file in temp
        def fake_run(cmd, **kwargs):
            d_idx = cmd.index("-d")
            out_d = Path(cmd[d_idx + 1])
            java_file = out_d / "com" / "test" / "TestClass.java"
            java_file.parent.mkdir(parents=True, exist_ok=True)
            java_file.write_text("public class TestClass {}", encoding="utf-8")
            return mock_proc

        mock_run.side_effect = fake_run

        out_dest = self.temp_dir / "out" / "TestClass.java"
        code = manager.decompile_class(Path("dummy.apk"), "com.test.TestClass", output_file=out_dest)

        self.assertIsNotNone(code)
        self.assertIn("class TestClass", code)
        self.assertTrue(out_dest.exists())

        # Test not installed
        manager.is_installed = MagicMock(return_value=False)
        self.assertIsNone(manager.decompile_class(Path("dummy.apk"), "com.test.TestClass"))

        # Test empty result
        manager.is_installed = MagicMock(return_value=True)
        mock_run.side_effect = None
        self.assertIsNone(manager.decompile_class(Path("dummy.apk"), "com.test.NotFound"))

    @patch("subprocess.run")
    def test_decompile_app(self, mock_run):
        manager = JADXManager(jadx_path="mock_jadx")
        manager.is_installed = MagicMock(return_value=True)

        out_dir = self.temp_dir / "decompiled"
        dummy_apk = self.temp_dir / "test.apk"
        dummy_apk.touch()

        # Success case
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc
        res = manager.decompile_app(dummy_apk, out_dir, no_res=True)
        self.assertTrue(res)

        # Timeout case
        mock_run.side_effect = subprocess.TimeoutExpired(cmd=["jadx"], timeout=10)
        progress = []
        res = manager.decompile_app(dummy_apk, out_dir, on_progress=progress.append)
        self.assertFalse(res)
        self.assertTrue(any("Waktu habis" in p for p in progress))

        # Generic exception case
        mock_run.side_effect = RuntimeError("Broken")
        progress = []
        res = manager.decompile_app(dummy_apk, out_dir, on_progress=progress.append)
        self.assertFalse(res)
        self.assertTrue(any("Kesalahan" in p for p in progress))

        # Not installed
        manager.is_installed = MagicMock(return_value=False)
        self.assertFalse(manager.decompile_app(dummy_apk, out_dir))


if __name__ == "__main__":
    unittest.main()
