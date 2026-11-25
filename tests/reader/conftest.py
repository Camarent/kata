"""Hostile corpus builders for the reader tests. Every file is made in the test's own tmp_path."""

from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image

PAGE_TEXT = "Hello reader test page with plenty of plain words for the text check."


def make_pdf(pages: list[str], catalog_extra: str = "") -> bytes:
    """A minimal valid PDF: one Helvetica line per page ("" leaves the page empty)."""
    count = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(count))
    objects: dict[int, str] = {
        1: f"<< /Type /Catalog /Pages 2 0 R {catalog_extra} >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {count} >>",
        3: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for i, text in enumerate(pages):
        page_id, content_id = 4 + 2 * i, 5 + 2 * i
        stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET" if text else ""
        objects[page_id] = (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            "/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        objects[content_id] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for obj_id in sorted(objects):
        offsets[obj_id] = len(out)
        out += f"{obj_id} 0 obj\n{objects[obj_id]}\nendobj\n".encode("latin-1")
    xref_at = len(out)
    size = len(objects) + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode("latin-1")
    for obj_id in range(1, size):
        out += f"{offsets[obj_id]:010d} 00000 n \n".encode("latin-1")
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode(
        "latin-1"
    )
    return bytes(out)


def png_chunk(kind: bytes, body: bytes) -> bytes:
    crc = zlib.crc32(kind + body) & 0xFFFFFFFF
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)


def png_bytes(width: int, height: int) -> bytes:
    """A small valid RGB PNG of the stated size, built with Pillow."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, format="PNG")
    return buf.getvalue()


def bomb_png(width: int, height: int) -> bytes:
    """A tiny PNG whose header claims width x height pixels, with a small zlib body."""
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" * 16)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", idat)
        + png_chunk(b"IEND", b"")
    )


class Corpus:
    """Writes named test files into one tmp dir; the dir is pytest's and is cleaned by pytest."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def write(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def out_dir(self) -> Path:
        out = self.root / "out"
        out.mkdir(exist_ok=True)
        return out


@pytest.fixture
def corpus(tmp_path: Path) -> Corpus:
    return Corpus(tmp_path)
