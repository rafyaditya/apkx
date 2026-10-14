import unittest
from apk_extractor.app_names import (
    format_fallback_app_name,
    POPULAR_APPS,
    is_framework_or_wrapper_activity,
    _split_compound_words,
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


if __name__ == "__main__":
    unittest.main()

