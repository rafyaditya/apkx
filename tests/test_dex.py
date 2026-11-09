import struct
import unittest
from pathlib import Path
from apk_extractor.dex import format_skeleton_text, parse_dex_classes


def create_minimal_dex(classes: list) -> bytes:
    """Helper to construct a valid minimal DEX binary with string_ids, type_ids, and class_defs."""
    # We will build strings table
    strings = []
    for c in classes:
        # Descriptor Lcom/test/Class;
        desc = f"L{c.replace('.', '/')};"
        strings.append(desc)

    string_data = bytearray()
    string_offsets = []
    for s in strings:
        string_offsets.append(len(string_data))
        encoded = s.encode("utf-8")
        # uleb128 length
        string_data.append(len(encoded))
        string_data.extend(encoded)
        string_data.append(0)

    header_size = 0x70
    string_ids_off = header_size
    string_ids_size = len(strings)

    type_ids_off = string_ids_off + string_ids_size * 4
    type_ids_size = len(strings)

    class_defs_off = type_ids_off + type_ids_size * 4
    class_defs_size = len(classes)

    string_data_start = class_defs_off + class_defs_size * 32

    # Build header
    header = bytearray(0x70)
    header[0:4] = b"dex\n"
    header[4:8] = b"035\x00"

    struct.pack_into("<II", header, 0x38, string_ids_size, string_ids_off)
    struct.pack_into("<II", header, 0x40, type_ids_size, type_ids_off)
    struct.pack_into("<II", header, 0x60, class_defs_size, class_defs_off)

    buf = bytearray(header)

    # string_ids (pointer to string data)
    for off in string_offsets:
        buf.extend(struct.pack("<I", string_data_start + off))

    # type_ids (pointer to string_id)
    for idx in range(len(strings)):
        buf.extend(struct.pack("<I", idx))

    # class_defs (class_idx at offset 0)
    for idx in range(len(classes)):
        cdef = bytearray(32)
        struct.pack_into("<I", cdef, 0, idx)
        buf.extend(cdef)

    buf.extend(string_data)
    return bytes(buf)


class TestDEXParser(unittest.TestCase):
    def test_parse_dex_classes(self):
        sample_classes = ["com.test.app.MainActivity", "com.test.app.model.User"]
        dex_bytes = create_minimal_dex(sample_classes)
        parsed = parse_dex_classes(dex_bytes)
        self.assertEqual(parsed, sample_classes)

    def test_invalid_dex_bytes(self):
        self.assertEqual(parse_dex_classes(b""), [])
        self.assertEqual(parse_dex_classes(b"invalid_header_bytes"), [])

    def test_format_skeleton_text(self):
        skeleton_data = {
            "total_classes": 2,
            "app_classes_count": 2,
            "packages_count": 1,
            "packages": ["com.test.app"],
            "app_classes": ["com.test.app.MainActivity", "com.test.app.Service"],
        }
        txt = format_skeleton_text(skeleton_data, "TestApp", "com.test.app")
        self.assertIn("TestApp", txt)
        self.assertIn("MainActivity", txt)
        self.assertIn("Service", txt)

        # Empty classes
        txt_empty = format_skeleton_text({"packages": [f"pkg{i}" for i in range(50)]}, "EmptyApp", "com.empty")
        self.assertIn("Tidak ada kelas spesifik", txt_empty)
        self.assertIn("package lainnya", txt_empty)

    def test_extract_class_skeleton_from_dir(self):
        import tempfile
        from apk_extractor.dex import extract_class_skeleton_from_dir
        with tempfile.TemporaryDirectory() as tmp_d:
            tmp_path = Path(tmp_d)
            dex_file = tmp_path / "classes.dex"
            sample_classes = [
                "com.mycompany.app.MainActivity",
                "com.mycompany.app.data.Repository",
                "android.view.View",
                "androidx.core.App",
            ]
            dex_file.write_bytes(create_minimal_dex(sample_classes))

            skeleton = extract_class_skeleton_from_dir(tmp_path, target_package="com.mycompany.app")
            self.assertEqual(skeleton["total_classes"], 4)
            self.assertEqual(skeleton["app_classes_count"], 2)
            self.assertEqual(skeleton["third_party_classes_count"], 2)
            self.assertIn("com.mycompany.app", skeleton["packages"])


if __name__ == "__main__":
    unittest.main()
