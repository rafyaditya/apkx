import struct
from typing import Dict, List

from apk_extractor.logger import logger


def _parse_string_pool(chunk_data: bytes) -> List[str]:
    strings: List[str] = []
    if len(chunk_data) < 28:
        return strings

    string_count, _, flags, str_offset, _ = struct.unpack(
        "<IIIII", chunk_data[8:28]
    )
    is_utf8 = bool(flags & (1 << 8))

    offset_table_end = 28 + string_count * 4
    if len(chunk_data) < offset_table_end:
        return strings

    offsets = struct.unpack(
        f"<{string_count}I",
        chunk_data[28:offset_table_end],
    )

    for off in offsets:
        s_idx = str_offset + off
        if s_idx >= len(chunk_data):
            strings.append("")
            continue

        if is_utf8:
            if s_idx >= len(chunk_data):
                strings.append("")
                continue
            u16len = chunk_data[s_idx]
            s_idx += 1
            if u16len & 0x80:
                if s_idx >= len(chunk_data):
                    strings.append("")
                    continue
                u16len = ((u16len & 0x7F) << 8) | chunk_data[s_idx]
                s_idx += 1

            if s_idx >= len(chunk_data):
                strings.append("")
                continue
            u8len = chunk_data[s_idx]
            s_idx += 1
            if u8len & 0x80:
                if s_idx >= len(chunk_data):
                    strings.append("")
                    continue
                u8len = ((u8len & 0x7F) << 8) | chunk_data[s_idx]
                s_idx += 1

            str_bytes = chunk_data[s_idx : s_idx + u8len]
            strings.append(
                str_bytes.decode("utf-8", errors="replace")
            )
        else:
            if s_idx + 2 > len(chunk_data):
                strings.append("")
                continue
            u16len = struct.unpack(
                "<H", chunk_data[s_idx : s_idx + 2]
            )[0]
            s_idx += 2
            if u16len & 0x8000:
                if s_idx + 2 > len(chunk_data):
                    strings.append("")
                    continue
                u16len = (
                    ((u16len & 0x7FFF) << 16)
                    | struct.unpack(
                        "<H", chunk_data[s_idx : s_idx + 2]
                    )[0]
                )
                s_idx += 2

            str_bytes = chunk_data[s_idx : s_idx + u16len * 2]
            strings.append(
                str_bytes.decode("utf-16le", errors="replace")
            )

    return strings


def _escape_xml_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _format_attr_value(
    val_str_idx: int,
    type_code: int,
    data: int,
    strings: List[str],
) -> str:
    if 0 <= val_str_idx < len(strings) and strings[val_str_idx]:
        return strings[val_str_idx]

    t = type_code >> 24

    if t == 3:
        return strings[data] if 0 <= data < len(strings) else ""
    if t == 16:
        signed = data - 0x100000000 if data >= 0x80000000 else data
        return str(signed)
    if t == 17:
        return f"0x{data:x}"
    if t == 18:
        return "true" if data != 0 else "false"
    if t == 1:
        return f"@0x{data:08x}"
    if t == 4:
        try:
            return str(
                struct.unpack("<f", struct.pack("<I", data))[0]
            )
        except Exception:
            return str(data)
    return str(data)


def _alloc_prefix(
    uri: str,
    scope: Dict[str, str],
    pending: Dict[str, str],
) -> str:
    known = {
        "http://schemas.android.com/apk/res/android": "android",
        "http://schemas.android.com/apk/res-auto": "app",
        "http://schemas.android.com/tools": "tools",
    }
    preferred = known.get(uri)
    if preferred:
        if scope.get(preferred) == uri:
            return preferred
        if preferred not in scope:
            scope[preferred] = uri
            pending[preferred] = uri
            return preferred

    idx = 0
    while f"ns{idx}" in scope:
        idx += 1
    generated = f"ns{idx}"
    scope[generated] = uri
    pending[generated] = uri
    return generated


def decode_axml(data: bytes) -> str:
    if not data or len(data) < 8:
        return ""

    magic, header_size, _ = struct.unpack("<HHI", data[:8])

    if magic != 0x0003:
        try:
            return data.decode("utf-8")
        except Exception:
            return ""

    start_offset = header_size if header_size >= 8 else 8

    # Pass 1: string pool + keseimbangan namespace
    offset = start_offset
    strings: List[str] = []
    ns_balance = 0

    while offset + 8 <= len(data):
        chunk_type, _, chunk_sz = struct.unpack(
            "<HHI", data[offset : offset + 8]
        )
        if chunk_sz == 0 or offset + chunk_sz > len(data):
            break

        chunk_data = data[offset : offset + chunk_sz]

        if chunk_type == 0x0001:
            strings = _parse_string_pool(chunk_data)
        elif chunk_type == 0x0100:
            ns_balance += 1
        elif chunk_type == 0x0101:
            ns_balance -= 1

        offset += chunk_sz

    if ns_balance != 0:
        logger.warning(
            "AXML namespace tidak seimbang (balance=%d); "
            "melanjutkan dengan scoped parser.",
            ns_balance,
        )

    # Pass 2: scoped parser
    offset = start_offset
    xml_lines: List[str] = [
        '<?xml version="1.0" encoding="utf-8"?>'
    ]
    indent = 0

    ns_stack: List[Dict[str, str]] = [{}]
    pending_ns: Dict[str, str] = {}
    element_stack: List[str] = []

    while offset + 8 <= len(data):
        chunk_type, _, chunk_sz = struct.unpack(
            "<HHI", data[offset : offset + 8]
        )
        if chunk_sz == 0 or offset + chunk_sz > len(data):
            break

        chunk_data = data[offset : offset + chunk_sz]

        if chunk_type == 0x0100:
            if len(chunk_data) >= 24:
                pfx_idx, uri_idx = struct.unpack(
                    "<II", chunk_data[16:24]
                )
                pfx = (
                    strings[pfx_idx]
                    if 0 <= pfx_idx < len(strings)
                    else ""
                )
                uri = (
                    strings[uri_idx]
                    if 0 <= uri_idx < len(strings)
                    else ""
                )
                if uri:
                    new_scope = dict(ns_stack[-1])
                    new_scope[pfx] = uri
                    ns_stack.append(new_scope)
                    pending_ns[pfx] = uri

        elif chunk_type == 0x0101:
            if len(ns_stack) > 1:
                ns_stack.pop()
                pending_ns = {
                    p: u
                    for p, u in pending_ns.items()
                    if ns_stack[-1].get(p) == u
                }

        elif chunk_type == 0x0102:
            if len(chunk_data) >= 30:
                (
                    ns_idx,
                    name_idx,
                    attr_start,
                    attr_size,
                    attr_count,
                ) = struct.unpack(
                    "<IIHHH", chunk_data[16:30]
                )

                elem_name = (
                    strings[name_idx]
                    if 0 <= name_idx < len(strings)
                    else "tag"
                )
                elem_uri = (
                    strings[ns_idx]
                    if 0 <= ns_idx < len(strings)
                    else ""
                )

                scope = ns_stack[-1]
                pending_decl = dict(pending_ns)
                pending_ns.clear()

                if elem_uri:
                    if scope.get("") == elem_uri:
                        elem_prefix = ""
                    else:
                        matches = sorted(
                            p
                            for p, u in scope.items()
                            if u == elem_uri and p
                        )
                        elem_prefix = (
                            matches[0]
                            if matches
                            else _alloc_prefix(
                                elem_uri,
                                scope,
                                pending_decl,
                            )
                        )
                else:
                    elem_prefix = ""

                qname = (
                    f"{elem_prefix}:{elem_name}"
                    if elem_prefix
                    else elem_name
                )
                element_stack.append(qname)

                attr_parts: List[str] = []
                extra_ns: Dict[str, str] = {}
                attr_offset = 16 + attr_start
                step = attr_size if attr_size >= 20 else 20

                for _ in range(attr_count):
                    if attr_offset + 20 > len(chunk_data):
                        break

                    (
                        a_ns,
                        a_name,
                        a_val_str,
                        a_type,
                        a_data,
                    ) = struct.unpack(
                        "<IIIII",
                        chunk_data[
                            attr_offset : attr_offset + 20
                        ],
                    )
                    attr_offset += step

                    name = (
                        strings[a_name]
                        if 0 <= a_name < len(strings)
                        else f"attr_{a_name}"
                    )
                    attr_uri = (
                        strings[a_ns]
                        if 0 <= a_ns < len(strings)
                        else ""
                    )

                    if attr_uri:
                        matches = sorted(
                            p
                            for p, u in scope.items()
                            if u == attr_uri and p
                        )
                        if matches:
                            attr_prefix = matches[0]
                        else:
                            attr_prefix = _alloc_prefix(
                                attr_uri,
                                scope,
                                extra_ns,
                            )
                        name = f"{attr_prefix}:{name}"

                    value = _format_attr_value(
                        a_val_str,
                        a_type,
                        a_data,
                        strings,
                    )
                    attr_parts.append(
                        f'{name}="{_escape_xml_attr(value)}"'
                    )

                declarations = dict(pending_decl)
                declarations.update(extra_ns)

                attrs: List[str] = []
                for pfx, uri in declarations.items():
                    escaped_uri = _escape_xml_attr(uri)
                    if pfx:
                        attrs.append(
                            f'xmlns:{pfx}="{escaped_uri}"'
                        )
                    else:
                        attrs.append(f'xmlns="{escaped_uri}"')

                attrs.extend(attr_parts)
                attr_str = (
                    " " + " ".join(attrs) if attrs else ""
                )
                spaces = "  " * indent
                xml_lines.append(
                    f"{spaces}<{qname}{attr_str}>"
                )
                indent += 1

        elif chunk_type == 0x0103:
            indent = max(0, indent - 1)
            qname = element_stack.pop() if element_stack else "tag"
            spaces = "  " * indent
            xml_lines.append(f"{spaces}</{qname}>")

        elif chunk_type == 0x0104:
            if len(chunk_data) >= 20:
                data_idx = struct.unpack(
                    "<I", chunk_data[16:20]
                )[0]
                text = (
                    strings[data_idx]
                    if 0 <= data_idx < len(strings)
                    else ""
                )
                if text.strip():
                    text = (
                        text.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                    )
                    spaces = "  " * indent
                    xml_lines.append(f"{spaces}{text.strip()}")

        offset += chunk_sz

    return "\n".join(xml_lines)
