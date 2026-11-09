import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apk_extractor.adb import ADBManager
from apk_extractor.app_names import (
    AppInfo,
    _split_compound_words,
    extract_apk_label,
    fetch_launcher_activities,
    find_aapt_binary,
    format_fallback_app_name,
    load_app_cache,
    resolve_apps,
    save_to_app_cache,
)


class TestAppNames(unittest.TestCase):
    def test_popular_apps_lookup(self):
        self.assertEqual(format_fallback_app_name("com.whatsapp"), "WhatsApp")
        self.assertEqual(format_fallback_app_name("com.facebook.katana"), "Facebook")
        self.assertEqual(format_fallback_app_name("com.spotify.music"), "Spotify")
        self.assertEqual(format_fallback_app_name("id.dana"), "DANA")
        self.assertEqual(format_fallback_app_name("com.openai.chatgpt"), "ChatGPT")
        self.assertEqual(format_fallback_app_name("com.pixio.google.mtd"), "Summoner's Greed")

    def test_geoabsen_not_screen(self):
        name = format_fallback_app_name(
            "com.project.aplikasi.Geoabsen",
            activity_name="com.project.aplikasi.Geoabsen.activity.splashscreen_activity",
        )
        self.assertEqual(name, "Geoabsen")
        self.assertNotEqual(name, "Screen")

    def test_unity_game_not_unity_player(self):
        name = format_fallback_app_name(
            "com.fluffyfairygames.idleminertycoon",
            activity_name="com.unity3d.player.UnityPlayerActivity",
        )
        self.assertEqual(name, "Idle Miner Tycoon")
        self.assertNotEqual(name, "Unity Player")

    def test_flutter_app_not_flutter(self):
        name = format_fallback_app_name(
            "com.mycompany.supertool",
            activity_name="io.flutter.embedding.android.FlutterActivity",
        )
        self.assertIn("Tool", name)
        self.assertNotEqual(name, "Flutter")

    def test_react_native_app_not_react(self):
        name = format_fallback_app_name(
            "com.mycompany.shopmaster",
            activity_name="com.facebook.react.ReactActivity",
        )
        self.assertEqual(name, "Shop Master")
        self.assertNotEqual(name, "React")

    def test_fallback_launcher_activity_when_valid(self):
        name = format_fallback_app_name(
            "com.unknown.bank",
            activity_name="com.unknown.bank.view.BankingMainActivity",
        )
        self.assertEqual(name, "Banking")

    def test_fallback_package_segment(self):
        name = format_fallback_app_name("com.blodhgard.easybudget")
        self.assertEqual(name, "Easy Budget")

        name2 = format_fallback_app_name("com.gamma.scan")
        self.assertIn("Scan", name2)

    def test_compound_word_splitting(self):
        self.assertEqual(_split_compound_words("idleminertycoon"), "Idle Miner Tycoon")
        self.assertEqual(_split_compound_words("easybudget"), "Easy Budget")
        self.assertEqual(_split_compound_words("supervpnfree"), "Super VPN Free")

    def test_cache_lookup(self):
        custom_cache = {"com.custom.secret": "My Secret Game"}
        name = format_fallback_app_name("com.custom.secret", cache=custom_cache)
        self.assertEqual(name, "My Secret Game")

    def test_cache_save_load(self):
        with tempfile.TemporaryDirectory() as tmp_d:
            cache_file = Path(tmp_d) / "test_cache.json"
            with patch("apk_extractor.app_names.APP_CACHE_FILE", cache_file):
                save_to_app_cache("com.test.pkg", "Test Friendly Name")
                loaded = load_app_cache()
                self.assertEqual(loaded.get("com.test.pkg"), "Test Friendly Name")

    @patch("shutil.which")
    def test_find_aapt_binary(self, mock_which):
        # 1. In PATH
        mock_which.return_value = "/usr/bin/aapt2"
        self.assertEqual(find_aapt_binary(), "/usr/bin/aapt2")

        # 2. None anywhere
        mock_which.return_value = None
        with patch.dict("os.environ", {}, clear=True), patch("pathlib.Path.exists", return_value=False):
            self.assertIsNone(find_aapt_binary())

    @patch("apk_extractor.app_names.find_aapt_binary")
    @patch("subprocess.run")
    def test_extract_apk_label(self, mock_run, mock_aapt):
        mock_aapt.return_value = "/usr/bin/aapt2"

        with tempfile.NamedTemporaryFile(suffix=".apk") as tmp_apk:
            apk_path = Path(tmp_apk.name)

            # Case 1: application-label
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "package: name='com.test'\napplication-label:'Awesome App'\n"
            mock_run.return_value = mock_proc
            label = extract_apk_label(apk_path)
            self.assertEqual(label, "Awesome App")

            # Case 2: launchable-activity label fallback
            mock_proc.stdout = "launchable-activity: name='com.test.Main'  label='Activity Label'\n"
            label = extract_apk_label(apk_path)
            self.assertEqual(label, "Activity Label")

            # Case 3: Error / failure
            mock_run.side_effect = subprocess.SubprocessError("Error")
            self.assertIsNone(extract_apk_label(apk_path))

        # File does not exist
        self.assertIsNone(extract_apk_label(Path("/nonexistent/app.apk")))

    @patch("subprocess.run")
    def test_fetch_launcher_activities(self, mock_run):
        mock_adb = MagicMock(spec=ADBManager)
        mock_adb._build_base_cmd.return_value = ["mock_adb"]

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = (
            "priority=0\n"
            "com.whatsapp/com.whatsapp.Main\n"
            "com.instagram.android/com.instagram.mainactivity.LauncherActivity\n"
        )
        mock_run.return_value = mock_proc

        res = fetch_launcher_activities(mock_adb)
        self.assertEqual(res.get("com.whatsapp"), "com.whatsapp.Main")
        self.assertEqual(res.get("com.instagram.android"), "com.instagram.mainactivity.LauncherActivity")

    @patch("apk_extractor.app_names.fetch_launcher_activities")
    @patch("apk_extractor.app_names.load_app_cache", return_value={})
    def test_resolve_apps(self, mock_cache, mock_fetch):
        mock_adb = MagicMock(spec=ADBManager)
        mock_fetch.return_value = {
            "com.whatsapp": "com.whatsapp.Main",
        }

        apps = resolve_apps(mock_adb, ["com.whatsapp", "com.blodhgard.easybudget"])
        self.assertEqual(len(apps), 2)
        # Should be sorted by friendly app_name
        self.assertTrue(all(isinstance(a, AppInfo) for a in apps))
        names = [a.app_name for a in apps]
        self.assertIn("WhatsApp", names)
        self.assertIn("Easy Budget", names)


if __name__ == "__main__":
    unittest.main()
