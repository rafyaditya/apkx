import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apk_extractor.setup_mcp import get_target_config_paths, install_mcp_to_all_clients


class TestSetupMCP(unittest.TestCase):
    def test_get_target_config_paths(self):
        targets = get_target_config_paths()
        names = [n for n, _ in targets]
        self.assertIn("Google Antigravity", names)
        self.assertIn("Cursor (Global)", names)
        self.assertIn("Claude Desktop", names)

    def test_install_mcp_to_clients_mock(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            fake_conf = Path(tmp_d) / "mcp_config.json"
            fake_conf.write_text("{}", encoding="utf-8")

            with patch(
                "apk_extractor.setup_mcp.get_target_config_paths",
                return_value=[("Google Antigravity", fake_conf)],
            ):
                with patch("apk_extractor.setup_mcp.sync_antigravity_skill") as mock_sync:
                    mock_sync.return_value = {
                        "client": "Antigravity Skill (apkx-android-blueprint)",
                        "status": "success",
                        "path": "/fake/skill/path",
                    }
                    results = install_mcp_to_all_clients()
                    self.assertEqual(len(results), 2)
                    self.assertEqual(results[0]["status"], "success")
                    self.assertEqual(results[1]["status"], "success")

                    data = json.loads(fake_conf.read_text(encoding="utf-8"))
                    self.assertIn("mcpServers", data)
                    self.assertIn("apkx", data["mcpServers"])
                    self.assertIn("serve", data["mcpServers"]["apkx"]["args"])

    def test_sync_antigravity_skill(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            fake_home = Path(tmp_d)
            with patch("pathlib.Path.home", return_value=fake_home):
                from apk_extractor.setup_mcp import sync_antigravity_skill
                res = sync_antigravity_skill()
                self.assertEqual(res["status"], "success")
                expected_skill = fake_home / ".gemini" / "config" / "skills" / "apkx-android-blueprint" / "SKILL.md"
                self.assertTrue(expected_skill.exists())
                self.assertIn("apkx-android-blueprint", expected_skill.read_text(encoding="utf-8"))

    def test_install_mcp_corrupt_json_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            fake_conf = Path(tmp_d) / "mcp_config.json"
            fake_conf.write_text("{ corrupt json: [", encoding="utf-8")

            with patch(
                "apk_extractor.setup_mcp.get_target_config_paths",
                return_value=[("Google Antigravity", fake_conf)],
            ):
                with patch("apk_extractor.setup_mcp.sync_antigravity_skill", return_value=None):
                    results = install_mcp_to_all_clients()
                    self.assertEqual(results[0]["status"], "success")
                    backup_file = fake_conf.with_suffix(".json.bak")
                    self.assertTrue(backup_file.is_file(), "Backup file should be created when JSON is corrupt")
                    self.assertEqual(backup_file.read_text(encoding="utf-8"), "{ corrupt json: [")
                    data = json.loads(fake_conf.read_text(encoding="utf-8"))
                    self.assertIn("apkx", data["mcpServers"])

    def test_agents_and_package_skill_byte_identical(self):
        repo_skill = (
            Path(__file__).parent.parent
            / ".agents"
            / "skills"
            / "apkx-android-blueprint"
            / "SKILL.md"
        )
        pkg_skill = (
            Path(__file__).parent.parent
            / "apk_extractor"
            / "data"
            / "skills"
            / "apkx-android-blueprint"
            / "SKILL.md"
        )
        self.assertTrue(repo_skill.is_file(), f"Repo skill must exist: {repo_skill}")
        self.assertTrue(pkg_skill.is_file(), f"Package skill must exist: {pkg_skill}")
        self.assertEqual(repo_skill.read_bytes(), pkg_skill.read_bytes())

    def test_antigravity_home_skill_byte_identical(self):
        repo_skill = (
            Path(__file__).parent.parent
            / ".agents"
            / "skills"
            / "apkx-android-blueprint"
            / "SKILL.md"
        )
        home_skill = Path.home() / ".gemini" / "config" / "skills" / "apkx-android-blueprint" / "SKILL.md"
        if home_skill.exists():
            self.assertEqual(repo_skill.read_bytes(), home_skill.read_bytes())

    def test_sync_antigravity_skill_byte_identical_with_temp_home(self):
        repo_skill = (
            Path(__file__).parent.parent
            / ".agents"
            / "skills"
            / "apkx-android-blueprint"
            / "SKILL.md"
        )
        with tempfile.TemporaryDirectory() as tmp_d:
            fake_home = Path(tmp_d)
            with patch("pathlib.Path.home", return_value=fake_home):
                from apk_extractor.setup_mcp import sync_antigravity_skill
                res = sync_antigravity_skill()
                self.assertEqual(res["status"], "success")
                synced_skill = fake_home / ".gemini" / "config" / "skills" / "apkx-android-blueprint" / "SKILL.md"
                self.assertTrue(synced_skill.is_file())
                self.assertEqual(repo_skill.read_bytes(), synced_skill.read_bytes())

    def test_load_skill_content(self):
        from apk_extractor.setup_mcp import load_skill_content
        content = load_skill_content()
        self.assertIsInstance(content, str)
        self.assertGreater(len(content), 1000)
        self.assertIn("apkx-android-blueprint", content)

    def test_load_skill_content_fallbacks(self):
        from apk_extractor.setup_mcp import load_skill_content
        with patch("importlib.resources.files", side_effect=Exception("No package data")):
            content = load_skill_content()
            self.assertIn("apkx-android-blueprint", content)

    def test_sync_antigravity_skill_error(self):
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("Permission denied")):
            from apk_extractor.setup_mcp import sync_antigravity_skill
            res = sync_antigravity_skill()
            self.assertEqual(res["status"], "error")
            self.assertIn("Permission denied", res["error"])

    def test_install_mcp_skips_uninstalled_clients(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            non_existent_parent = Path(tmp_d) / "does_not_exist" / "config.json"
            with patch(
                "apk_extractor.setup_mcp.get_target_config_paths",
                return_value=[("Cursor (Global)", non_existent_parent)],
            ):
                with patch("apk_extractor.setup_mcp.sync_antigravity_skill", return_value=None):
                    results = install_mcp_to_all_clients()
                    self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
