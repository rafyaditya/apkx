"""
Unit tests for apk_extractor.updater.
"""
import io
import json
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from apk_extractor import updater
from apk_extractor.updater import (
    parse_semver,
    is_newer_version,
    fetch_latest_version,
    detect_install_method,
    execute_update,
    run_updater,
)


class TestUpdater(unittest.TestCase):
    def test_parse_semver(self):
        self.assertEqual(parse_semver("1.0.1"), (1, 0, 1))
        self.assertEqual(parse_semver("v2.3.4"), (2, 3, 4))
        self.assertEqual(parse_semver("10.20.30"), (10, 20, 30))
        self.assertEqual(parse_semver("v1"), (1,))
        self.assertEqual(parse_semver("unknown"), (0,))

    def test_is_newer_version(self):
        self.assertTrue(is_newer_version("1.1.0", "1.0.1"))
        self.assertTrue(is_newer_version("2.0.0", "1.9.9"))
        self.assertTrue(is_newer_version("1.0.2", "1.0.1"))
        self.assertFalse(is_newer_version("1.0.1", "1.0.1"))
        self.assertFalse(is_newer_version("1.0.0", "1.0.1"))
        self.assertFalse(is_newer_version("0.9.0", "1.0.1"))

    @patch("urllib.request.urlopen")
    def test_fetch_latest_version_releases_api(self, mock_urlopen):
        # Mock release API response
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"tag_name": "v1.2.0"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        ver = fetch_latest_version(timeout=1.0)
        self.assertEqual(ver, "1.2.0")

    @patch("urllib.request.urlopen")
    def test_fetch_latest_version_raw_fallback(self, mock_urlopen):
        # First call fails (API), second call succeeds (Raw)
        mock_resp_raw = MagicMock()
        mock_resp_raw.status = 200
        mock_resp_raw.read.return_value = b'__version__ = "1.3.0"\n'
        mock_resp_raw.__enter__.return_value = mock_resp_raw

        mock_urlopen.side_effect = [Exception("API 404"), mock_resp_raw]

        ver = fetch_latest_version(timeout=1.0)
        self.assertEqual(ver, "1.3.0")

    @patch("urllib.request.urlopen")
    def test_fetch_latest_version_failure(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Network offline")
        ver = fetch_latest_version(timeout=1.0)
        self.assertIsNone(ver)

    @patch("shutil.which")
    @patch("pathlib.Path.is_dir")
    def test_detect_install_method_git(self, mock_is_dir, mock_which):
        mock_is_dir.return_value = True
        mock_which.return_value = "/usr/bin/git"

        method, root = detect_install_method()
        self.assertEqual(method, "git")
        self.assertIsNotNone(root)

    @patch("shutil.which")
    @patch("pathlib.Path.is_dir")
    def test_detect_install_method_pipx(self, mock_is_dir, mock_which):
        mock_is_dir.return_value = False
        mock_which.side_effect = lambda cmd: "/usr/bin/pipx" if cmd == "pipx" else None

        with patch("sys.prefix", "/home/user/.local/share/pipx/venvs/apkx"):
            method, root = detect_install_method()
            self.assertEqual(method, "pipx")
            self.assertIsNone(root)

    @patch("shutil.which")
    @patch("pathlib.Path.is_dir")
    def test_detect_install_method_pip(self, mock_is_dir, mock_which):
        mock_is_dir.return_value = False
        mock_which.return_value = None

        with patch("sys.prefix", "/usr"):
            with patch("sys.executable", "/usr/bin/python3"):
                method, root = detect_install_method()
                self.assertEqual(method, "pip")
                self.assertIsNone(root)

    @patch("subprocess.run")
    def test_execute_update_git_success(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_res.stdout = "Already up to date."
        mock_res.stderr = ""
        mock_run.return_value = mock_res

        success, msg = execute_update("git", repo_root=Path("/tmp/repo"))
        self.assertTrue(success)
        self.assertIn("Git", msg)

    @patch("subprocess.run")
    def test_execute_update_pipx_success(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        success, msg = execute_update("pipx")
        self.assertTrue(success)
        self.assertIn("pipx", msg)

    @patch("subprocess.run")
    def test_execute_update_pip_success(self, mock_run):
        mock_res = MagicMock()
        mock_res.returncode = 0
        mock_run.return_value = mock_res

        success, msg = execute_update("pip")
        self.assertTrue(success)
        self.assertIn("pip", msg)

    @patch("apk_extractor.updater.fetch_latest_version")
    def test_run_updater_offline(self, mock_fetch):
        mock_fetch.return_value = None
        code = run_updater(check_only=False, as_json=False)
        self.assertEqual(code, 1)

    @patch("apk_extractor.updater.fetch_latest_version")
    def test_run_updater_up_to_date(self, mock_fetch):
        mock_fetch.return_value = "1.0.1"
        with patch("apk_extractor.updater.CURRENT_VERSION", "1.0.1"):
            code = run_updater(check_only=False, as_json=False)
            self.assertEqual(code, 0)

    @patch("apk_extractor.updater.fetch_latest_version")
    def test_run_updater_check_only(self, mock_fetch):
        mock_fetch.return_value = "2.0.0"
        with patch("apk_extractor.updater.CURRENT_VERSION", "1.0.1"):
            code = run_updater(check_only=True, as_json=False)
            self.assertEqual(code, 0)

    @patch("apk_extractor.updater.execute_update")
    @patch("apk_extractor.updater.fetch_latest_version")
    def test_run_updater_upgrade_success(self, mock_fetch, mock_exec):
        mock_fetch.return_value = "2.0.0"
        mock_exec.return_value = (True, "Updated successfully")
        with patch("apk_extractor.updater.CURRENT_VERSION", "1.0.1"):
            code = run_updater(check_only=False, as_json=False)
            self.assertEqual(code, 0)

    @patch("apk_extractor.updater.fetch_latest_version")
    def test_run_updater_json_output(self, mock_fetch):
        mock_fetch.return_value = "1.0.1"
        with patch("apk_extractor.updater.CURRENT_VERSION", "1.0.1"):
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                code = run_updater(check_only=False, as_json=True)
                self.assertEqual(code, 0)
                out_val = fake_out.getvalue()
                data = json.loads(out_val)
                self.assertEqual(data["status"], "up_to_date")
                self.assertFalse(data["update_available"])


if __name__ == "__main__":
    unittest.main()
