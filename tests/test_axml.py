import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from apk_extractor.axml import decode_axml


class TestAXMLDecoder(unittest.TestCase):
    def setUp(self):
        self.fixtures_dir = Path(__file__).parent / "fixtures"

    def test_plain_text_passthrough(self):
        plain_xml = '<manifest package="com.test.app"></manifest>'
        result = decode_axml(plain_xml.encode("utf-8"))
        self.assertIn("com.test.app", result)

    def test_empty_or_short_data(self):
        self.assertEqual(decode_axml(b""), "")
        self.assertEqual(decode_axml(b"123"), "")

    def test_standard_axml_decoding(self):
        sample_path = self.fixtures_dir / "sample_manifest.axml"
        self.assertTrue(sample_path.is_file(), f"Fixture {sample_path} must exist")
        data = sample_path.read_bytes()
        decoded = decode_axml(data)
        self.assertIn("<?xml", decoded)
        self.assertIn("<manifest", decoded)
        self.assertIn("android.permission.INTERNET", decoded)
        # Verify it parses into standard XML without syntax or namespace errors
        root = ET.fromstring(decoded)
        self.assertEqual(root.tag, "manifest")

    def test_split_manifest_with_nested_namespaces(self):
        split_path = self.fixtures_dir / "split_manifest.axml"
        self.assertTrue(split_path.is_file(), f"Fixture {split_path} must exist")
        data = split_path.read_bytes()
        decoded = decode_axml(data)
        self.assertIn("<?xml", decoded)
        self.assertIn("<manifest", decoded)
        self.assertIn("xmlns:dist=", decoded)
        # Crucial regression test: ElementTree will raise ParseError if dist: prefix is unbound
        root = ET.fromstring(decoded)
        self.assertEqual(root.tag, "manifest")


if __name__ == "__main__":
    unittest.main()
