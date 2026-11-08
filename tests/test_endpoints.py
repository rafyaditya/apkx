import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from apk_extractor.endpoints import extract_endpoints_from_dir, extract_endpoints_from_file


class TestEndpointsExtractor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="apkx_test_endpoints_"))

    def tearDown(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extract_endpoints_from_dex_mock(self):
        # Create a mock dex file with embedded URLs
        dex_content = (
            b"\x00\x00some_code\x00\x00"
            b"https://api.mycompany.com/v1/auth/login"
            b"\x00\x00more_code\x00\x00"
            b"https://cdn.mycompany.com/assets/logo.png"
            b"\x00\x00ignored\x00\x00"
            b"http://schemas.android.com/apk/res/android"
            b"\x00\x00end"
        )
        dex_file = self.temp_dir / "classes.dex"
        dex_file.write_bytes(dex_content)

        res = extract_endpoints_from_dir(self.temp_dir)
        self.assertEqual(res["total_urls"], 2)
        self.assertIn("api.mycompany.com", res["domains"])
        self.assertIn("cdn.mycompany.com", res["domains"])
        self.assertNotIn("schemas.android.com", res["domains"])
        self.assertIn("https://api.mycompany.com/v1/auth/login", res["api_endpoints"])

    def test_nonexistent_directory(self):
        res = extract_endpoints_from_dir(Path("/nonexistent/directory/test"))
        self.assertEqual(res["total_urls"], 0)
        self.assertEqual(res["domains"], [])

    def test_extract_endpoints_corrupt_archive(self):
        corrupt_apk = self.temp_dir / "broken.apk"
        corrupt_apk.write_bytes(b"not a valid zip file")
        res = extract_endpoints_from_file(corrupt_apk)
        self.assertEqual(res["status"], "error")
        self.assertIn("bukan arsip zip/APK", res["error"])
        self.assertEqual(res["total_urls"], 0)

    def test_extract_endpoints_from_file_valid_apk(self):
        valid_apk = self.temp_dir / "valid.apk"
        with zipfile.ZipFile(valid_apk, "w") as zf:
            zf.writestr("classes.dex", b"test https://api.valid.com/v1/users data")
        res = extract_endpoints_from_file(valid_apk)
        self.assertEqual(res["total_urls"], 1)
        self.assertIn("api.valid.com", res["domains"])


if __name__ == "__main__":
    unittest.main()
