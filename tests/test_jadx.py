import shutil
import tempfile
import unittest
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
            # Find the -d argument
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


if __name__ == "__main__":
    unittest.main()
