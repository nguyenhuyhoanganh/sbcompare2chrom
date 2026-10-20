"""Generate files for upload / open / import tests (kept out of git, created on demand)."""
from __future__ import annotations

import struct
import zlib
from pathlib import Path


def text_file(folder: Path, name: str = "sample.txt", content: str = "sbtest sample text\n") -> Path:
    p = Path(folder) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def binary_file(folder: Path, name: str = "sample.bin", size: int = 1024) -> Path:
    p = Path(folder) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(bytes(i % 256 for i in range(size)))
    return p


def png_file(folder: Path, name: str = "sample.png", w: int = 8, h: int = 8, rgb=(200, 30, 30)) -> Path:
    """Valid solid-color PNG without external dependencies."""
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    p = Path(folder) / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(png)
    return p


def bookmarks_html(folder: Path, items: list[tuple[str, str]], name: str = "bookmarks.html") -> Path:
    """Netscape bookmark file, for "Import bookmarks" test cases."""
    rows = "\n".join(f'    <DT><A HREF="{url}">{title}</A>' for title, url in items)
    content = ("<!DOCTYPE NETSCAPE-Bookmark-file-1>\n<META HTTP-EQUIV=\"Content-Type\" CONTENT=\"text/html; charset=UTF-8\">\n"
               "<TITLE>Bookmarks</TITLE>\n<H1>Bookmarks</H1>\n<DL><p>\n" + rows + "\n</DL><p>\n")
    return text_file(folder, name, content)
