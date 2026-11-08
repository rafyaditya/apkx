"""
apkx: Pure-Python Android Binary XML (AXML) Decoder.
Decodes compiled AndroidManifest.xml and layout binary XML files into human-readable XML.
"""

import struct
from typing import Dict, List, Optional, Set, Tuple


def decode_axml(data: bytes) -> str:
    """
    Decodes binary Android Binary XML (AXML) into standard XML text.
    If the data is already plain text XML, returns it decoded.
    """
    if not data or len(data) < 8:
        return ""

    magic, header_size, _ = struct.unpack("<HHI", data[:8])

    # Check for AXML magic number (0x0003)
    if magic != 0x0003:
        try:
            return data.decode("utf-8")
        except Exception:
            return ""

    offset = header_size
    strings: List[str] = []
    namespaces: Dict[str, str] = {}
    pending_namespaces: List[Tuple[str, str]] = []
    declared_namespaces: Set[str] = set()
    xml_lines: List[str] = ['<?xml version="1.0" encoding="utf-8"?>']
    indent = 0

    while offset < len(data):
        if offset + 8 > len(data):
            break

        chunk_type, chunk_hdr_size, chunk_sz = struct.unpack("<HHI", data[offset:offset + 8])
        if chunk_sz == 0 or offset + chunk_sz > len(data):
            break

        chunk_data = data[offset:offset + chunk_sz]

        if chunk_type == 0x0001:  # RES_STRING_POOL_TYPE
            if len(chunk_data) >= 28:
                string_count, style_count, flags, str_offset, _ = struct.unpack("<IIIII", chunk_data[8:28])
                is_utf8 = bool(flags & (1 << 8))

                offset_table_end = 28 + string_count * 4
                if len(chunk_data) >= offset_table_end:
                    offsets = struct.unpack(f"<{string_count}I", chunk_data[28:offset_table_end])
                    for off in offsets:
                        s_idx = str_offset + off
                        if s_idx >= len(chunk_data):
                            strings.append("")
                            continue

                        if is_utf8:
                            u16len = chunk_data[s_idx]
                            s_idx += 1
                            if u16len & 0x80:
                                s_idx += 1
                            u8len = chunk_data[s_idx]
                            s_idx += 1
                            if u8len & 0x80:
                                s_idx += 1
                            str_bytes = chunk_data[s_idx:s_idx + u8len]
                            try:
                                strings.append(str_bytes.decode("utf-8", errors="replace"))
                            except Exception:
                                strings.append("")
                        else:
                            if s_idx + 2 <= len(chunk_data):
                                u16len = struct.unpack("<H", chunk_data[s_idx:s_idx + 2])[0]
                                s_idx += 2
                                if u16len & 0x8000:
                                    s_idx += 2
                                str_bytes = chunk_data[s_idx:s_idx + u16len * 2]
                                try:
                                    strings.append(str_bytes.decode("utf-16le", errors="replace"))
                                except Exception:
                                    strings.append("")
                            else:
                                strings.append("")

        elif chunk_type == 0x0100:  # RES_XML_START_NAMESPACE_TYPE
            if len(chunk_data) >= 24:
                prefix_idx, uri_idx = struct.unpack("<II", chunk_data[16:24])
                prefix = strings[prefix_idx] if 0 <= prefix_idx < len(strings) else ""
                uri = strings[uri_idx] if 0 <= uri_idx < len(strings) else ""
                if prefix and uri:
                    namespaces[prefix] = uri
                    pending_namespaces.append((prefix, uri))

        elif chunk_type == 0x0101:  # RES_XML_END_NAMESPACE_TYPE
            pass

        elif chunk_type == 0x0102:  # RES_XML_START_ELEMENT_TYPE
            if len(chunk_data) >= 30:
                ns_idx, name_idx, attr_start, attr_size, attr_count = struct.unpack("<IIHHH", chunk_data[16:30])
                elem_name = strings[name_idx] if 0 <= name_idx < len(strings) else "tag"

                attrs = []
                if pending_namespaces:
                    for pfx, uri in pending_namespaces:
                        attrs.append(f'xmlns:{pfx}="{uri}"')
                        declared_namespaces.add(pfx)
                    pending_namespaces.clear()

                attr_offset = 36
                for _ in range(attr_count):
                    if attr_offset + 20 > len(chunk_data):
                        break
                    a_ns, a_name, a_val_str, a_type, a_data = struct.unpack("<IIIIi", chunk_data[attr_offset:attr_offset + 20])
                    attr_offset += 20

                    name = strings[a_name] if 0 <= a_name < len(strings) else f"attr_{a_name}"
                    ns_prefix = ""
                    if 0 <= a_ns < len(strings):
                        ns_uri = strings[a_ns]
                        for p, u in namespaces.items():
                            if u == ns_uri:
                                ns_prefix = f"{p}:"
                                break

                    if ns_prefix:
                        pfx = ns_prefix.rstrip(":")
                        if pfx not in declared_namespaces and pfx in namespaces:
                            attrs.append(f'xmlns:{pfx}="{namespaces[pfx]}"')
                            declared_namespaces.add(pfx)

                    val = ""
                    type_code = a_type >> 24
                    if 0 <= a_val_str < len(strings) and strings[a_val_str]:
                        val = strings[a_val_str]
                    elif type_code == 3:  # TYPE_STRING
                        val = strings[a_data] if 0 <= a_data < len(strings) else ""
                    elif type_code == 16:  # TYPE_INT_DEC
                        val = str(a_data)
                    elif type_code == 17:  # TYPE_INT_HEX
                        val = f"0x{a_data:x}"
                    elif type_code == 18:  # TYPE_INT_BOOLEAN
                        val = "true" if a_data != 0 else "false"
                    elif type_code == 1:  # TYPE_REFERENCE
                        val = f"@0x{a_data:08x}"
                    elif type_code == 4:  # TYPE_FLOAT
                        try:
                            val = str(struct.unpack("f", struct.pack("i", a_data))[0])
                        except Exception:
                            val = str(a_data)
                    else:
                        val = str(a_data)

                    val_escaped = (
                        val.replace("&", "&amp;")
                        .replace('"', "&quot;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    attrs.append(f'{ns_prefix}{name}="{val_escaped}"')

                attr_str = (" " + " ".join(attrs)) if attrs else ""
                xml_lines.append(f"{'  ' * indent}<{elem_name}{attr_str}>")
                indent += 1

        elif chunk_type == 0x0103:  # RES_XML_END_ELEMENT_TYPE
            indent = max(0, indent - 1)
            if len(chunk_data) >= 24:
                ns_idx, name_idx = struct.unpack("<II", chunk_data[16:24])
                elem_name = strings[name_idx] if 0 <= name_idx < len(strings) else "tag"
                xml_lines.append(f"{'  ' * indent}</{elem_name}>")

        elif chunk_type == 0x0104:  # RES_XML_CDATA_TYPE
            if len(chunk_data) >= 20:
                data_idx = struct.unpack("<I", chunk_data[16:20])[0]
                cdata_str = strings[data_idx] if 0 <= data_idx < len(strings) else ""
                if cdata_str.strip():
                    xml_lines.append(f"{'  ' * indent}{cdata_str.strip()}")

        offset += chunk_sz

    return "\n".join(xml_lines)
