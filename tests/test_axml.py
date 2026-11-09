import struct
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from apk_extractor.axml import (
    _alloc_prefix,
    _format_attr_value,
    _parse_string_pool,
    decode_axml,
)


def _build_string_pool_bytes(strings, is_utf8=True):
    data_parts = []
    offsets = []
    curr_off = 0
    for s in strings:
        offsets.append(curr_off)
        b = s.encode("utf-8")
        u16len = len(s)
        u8len = len(b)
        len_b = (
            bytes([(u16len >> 8) | 0x80, u16len & 0xFF])
            if u16len >= 0x80
            else bytes([u16len])
        )
        len_b += (
            bytes([(u8len >> 8) | 0x80, u8len & 0xFF])
            if u8len >= 0x80
            else bytes([u8len])
        )
        part = len_b + b + b"\x00"
        data_parts.append(part)
        curr_off += len(part)

    str_data = b"".join(data_parts)
    pad = (4 - (len(str_data) % 4)) % 4
    str_data += b"\x00" * pad
    str_offset = 28 + len(strings) * 4
    chunk_sz = str_offset + len(str_data)
    header = struct.pack(
        "<HHI5I",
        0x0001,
        28,
        chunk_sz,
        len(strings),
        0,
        1 << 8 if is_utf8 else 0,
        str_offset,
        0,
    )
    offsets_data = struct.pack(f"<{len(strings)}I", *offsets)
    return header + offsets_data + str_data


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
        root = ET.fromstring(decoded)
        self.assertEqual(root.tag, "manifest")

    def test_string_pool_utf8_long_string_not_truncated(self):
        long_str = "x" * 135  # >128 bytes, triggers multi-byte length encoding
        sp_chunk = _build_string_pool_bytes(["short", long_str])
        strings = _parse_string_pool(sp_chunk)
        self.assertEqual(len(strings), 2)
        self.assertEqual(strings[0], "short")
        self.assertEqual(len(strings[1]), 135)
        self.assertEqual(strings[1], long_str)

    def test_format_attr_value_unsigned_hex_and_types(self):
        # Type 17: TYPE_INT_HEX with high-bit data (0xFFFFFFFF) must be unsigned hex, not 0x-1
        val_hex = _format_attr_value(-1, 0x11000000, 0xFFFFFFFF, [])
        self.assertEqual(val_hex, "0xffffffff")

        # Type 16: TYPE_INT_DEC with negative signed value
        val_dec = _format_attr_value(-1, 0x10000000, 0xFFFFFFFF, [])
        self.assertEqual(val_dec, "-1")

        # Type 18: Boolean
        self.assertEqual(_format_attr_value(-1, 0x12000000, 1, []), "true")
        self.assertEqual(_format_attr_value(-1, 0x12000000, 0, []), "false")

        # Type 1: Reference
        self.assertEqual(
            _format_attr_value(-1, 0x01000000, 0x7F040001, []),
            "@0x7f040001",
        )

    def test_synthetic_axml_cdata_and_namespaces(self):
        strings = [
            "android",
            "http://schemas.android.com/apk/res/android",
            "manifest",
            "package",
            "com.synthetic.app",
            "my_cdata_text",
        ]
        sp = _build_string_pool_bytes(strings)

        # NS start: prefix=android(0), uri=http://...(1)
        ns_start = struct.pack("<HHI4I", 0x0100, 16, 24, 1, 0xFFFFFFFF, 0, 1)
        # Element start: manifest(2), 1 attr: package(3)=com.synthetic.app(4)
        elem_start = struct.pack(
            "<HHI II II HHH HHH",
            0x0102,
            16,
            56,
            1,
            0xFFFFFFFF,
            0xFFFFFFFF,
            2,
            20,
            20,
            1,
            0,
            0,
            0,
        )
        attr = struct.pack("<5I", 0xFFFFFFFF, 3, 4, 0x03000000, 4)
        # CDATA chunk: text=my_cdata_text(5)
        cdata = struct.pack("<HHI5I", 0x0104, 16, 28, 1, 0xFFFFFFFF, 5, 0, 0)
        # Element end: manifest(2)
        elem_end = struct.pack(
            "<HHI4I", 0x0103, 16, 24, 1, 0xFFFFFFFF, 0xFFFFFFFF, 2
        )
        # NS end: prefix=0, uri=1
        ns_end = struct.pack("<HHI4I", 0x0101, 16, 24, 1, 0xFFFFFFFF, 0, 1)

        body = sp + ns_start + elem_start + attr + cdata + elem_end + ns_end
        total_sz = 8 + len(body)
        header = struct.pack("<HHI", 0x0003, 8, total_sz)
        axml_data = header + body

        decoded = decode_axml(axml_data)
        self.assertIn('package="com.synthetic.app"', decoded)
        self.assertIn("my_cdata_text", decoded)
        root = ET.fromstring(decoded)
        self.assertEqual(root.tag, "manifest")
        self.assertIn("my_cdata_text", root.text or "")

    def test_synthetic_axml_default_namespace(self):
        # Default namespace has empty prefix ""
        strings = ["", "http://example.com/ns/default", "root"]
        sp = _build_string_pool_bytes(strings)

        ns_start = struct.pack("<HHI4I", 0x0100, 16, 24, 1, 0xFFFFFFFF, 0, 1)
        elem_start = struct.pack(
            "<HHI II II HHH HHH",
            0x0102,
            16,
            36,
            1,
            0xFFFFFFFF,
            0xFFFFFFFF,
            2,
            20,
            20,
            0,
            0,
            0,
            0,
        )
        elem_end = struct.pack(
            "<HHI4I", 0x0103, 16, 24, 1, 0xFFFFFFFF, 0xFFFFFFFF, 2
        )
        ns_end = struct.pack("<HHI4I", 0x0101, 16, 24, 1, 0xFFFFFFFF, 0, 1)

        body = sp + ns_start + elem_start + elem_end + ns_end
        total_sz = 8 + len(body)
        header = struct.pack("<HHI", 0x0003, 8, total_sz)
        axml_data = header + body

        decoded = decode_axml(axml_data)
        self.assertIn('xmlns="http://example.com/ns/default"', decoded)
        root = ET.fromstring(decoded)
        self.assertTrue(root.tag.endswith("root"))

    def test_alloc_prefix_behavior(self):
        # Known URI
        scope = {}
        pending = {}
        pfx = _alloc_prefix("http://schemas.android.com/apk/res/android", scope, pending)
        self.assertEqual(pfx, "android")
        self.assertEqual(scope["android"], "http://schemas.android.com/apk/res/android")
        self.assertEqual(pending["android"], "http://schemas.android.com/apk/res/android")

        # Unknown URI generates ns0, ns1
        pfx1 = _alloc_prefix("http://unknown.com/1", scope, pending)
        self.assertEqual(pfx1, "ns0")
        pfx2 = _alloc_prefix("http://unknown.com/2", scope, pending)
        self.assertEqual(pfx2, "ns1")

    def test_format_attr_float_and_strings(self):
        # Type 4: Float
        float_bytes = struct.pack("<f", 3.14)
        float_int = struct.unpack("<I", float_bytes)[0]
        val_float = _format_attr_value(-1, 0x04000000, float_int, [])
        self.assertTrue(val_float.startswith("3.14"))

        # Type 3: String index
        val_str = _format_attr_value(-1, 0x03000000, 0, ["hello"])
        self.assertEqual(val_str, "hello")

    def test_utf16_string_pool_parsing(self):
        # Create UTF-16 string pool manually
        strings = ["hello", "world"]
        offsets = []
        body = bytearray()
        for s in strings:
            offsets.append(len(body))
            encoded = s.encode("utf-16le")
            body.extend(struct.pack("<H", len(s)))
            body.extend(encoded)
            body.extend(b"\x00\x00")

        header = struct.pack(
            "<HHI5I",
            0x0001,
            28,
            28 + len(strings) * 4 + len(body),
            len(strings),
            0,
            0,  # is_utf8 = False
            28 + len(strings) * 4,
            0,
        )
        offsets_data = struct.pack(f"<{len(strings)}I", *offsets)
        res = _parse_string_pool(header + offsets_data + bytes(body))
        self.assertEqual(res, strings)


if __name__ == "__main__":
    unittest.main()
