import unittest
from apk_extractor.app_names import format_fallback_app_name, POPULAR_APPS


class TestAppNames(unittest.TestCase):
    def test_popular_apps_lookup(self):
        self.assertEqual(format_fallback_app_name("com.whatsapp"), "WhatsApp")
        self.assertEqual(format_fallback_app_name("com.facebook.katana"), "Facebook")
        self.assertEqual(format_fallback_app_name("com.spotify.music"), "Spotify")
        self.assertEqual(format_fallback_app_name("id.dana"), "DANA")
        self.assertEqual(format_fallback_app_name("com.openai.chatgpt"), "ChatGPT")

    def test_fallback_launcher_activity(self):
        name = format_fallback_app_name(
            "com.unknown.bank",
            activity_name="com.unknown.bank.view.BankAppMainActivity",
        )
        self.assertEqual(name, "Bank")

    def test_fallback_package_segment(self):
        name = format_fallback_app_name("com.blodhgard.easybudget")
        self.assertIn("Easybudget", name)

        name2 = format_fallback_app_name("com.gamma.scan")
        self.assertIn("Scan", name2)


if __name__ == "__main__":
    unittest.main()
