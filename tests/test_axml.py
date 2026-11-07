import unittest
from pathlib import Path
from apk_extractor.axml import decode_axml


class TestAXMLDecoder(unittest.TestCase):
    def test_plain_text_passthrough(self):
        plain_xml = '<manifest package="com.test.app"></manifest>'
        result = decode_axml(plain_xml.encode("utf-8"))
        self.assertIn("com.test.app", result)

    def test_empty_or_short_data(self):
        self.assertEqual(decode_axml(b""), "")
        self.assertEqual(decode_axml(b"123"), "")

    def test_real_axml_decoding_if_available(self):
        sample_path = Path("output/extracted/Keluargo/AndroidManifest.xml")
        if sample_path.exists():
            data = sample_path.read_bytes()
            decoded = decode_axml(data)
            self.assertIn("<?xml", decoded)
            self.assertIn("<manifest", decoded)
            self.assertIn("id.keluargo.frontend", decoded)
            self.assertIn("android.permission.INTERNET", decoded)


if __name__ == "__main__":
    unittest.main()
