"""Document extract: check a file, reduce it to page text and PNG page images.

Checks, in order: size <= max_file_bytes (else too_large); magic bytes match the media type
(else bad_type); PDF page count <= max_pages (else too_many_pages); decoded image size under the
PIL bomb ceiling (else bomb); any decoder error ends as bad_file, never as an exception.

A page gets a PNG when it holds an image object or its text is shorter than min_page_chars. PNGs
are re-encoded through Pillow with no metadata, long side capped by max_image_side_px, and
downscaled until they fit max_image_bytes (else too_large). PDF JavaScript is never executed:
pypdfium2 does not run it. Text per page is cut to max_text_chars_per_page, control characters
except newline are dropped.

The only write is the PNG page files into the out dir the caller gives. No network, no env.
"""

from __future__ import annotations

import io
import unicodedata
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_raw
from PIL import Image

from kata_reader.limits import Limits

RESULT_VERSION = 1
PDF = "application/pdf"
PNG = "image/png"
JPEG = "image/jpeg"
WEBP = "image/webp"
ALLOWED_MEDIA = frozenset({PDF, PNG, JPEG, WEBP})
# Decoded pixel ceiling for PIL: a warning above it, DecompressionBombError above twice it.
MAX_IMAGE_PIXELS = 50_000_000
DOWNSCALE_FACTOR = 0.75
DOWNSCALE_TRIES = 6
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
MAGIC_HEAD_BYTES = 12


@dataclass(frozen=True)
class Page:
    n: int
    text: str
    image: str | None = None


@dataclass(frozen=True)
class Result:
    id: str
    status: str
    error: str | None = None
    pages: tuple[Page, ...] = ()
    v: int = RESULT_VERSION

    def to_dict(self) -> dict[str, Any]:
        """The spool result.json v1 shape."""
        return {
            "v": self.v,
            "id": self.id,
            "status": self.status,
            "error": self.error,
            "pages": [{"n": p.n, "text": p.text, "image": p.image} for p in self.pages],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Result:
        """Parse the spool result.json v1 shape; raises ValueError on another version."""
        if raw["v"] != RESULT_VERSION:
            raise ValueError(f"unknown result version {raw['v']!r}")
        pages = tuple(
            Page(n=int(p["n"]), text=str(p["text"]), image=p["image"]) for p in raw["pages"]
        )
        return cls(
            id=str(raw["id"]), status=str(raw["status"]), error=raw["error"], pages=pages
        )


class _Fail(Exception):
    """Stop with one spool error code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def fail(doc_id: str, code: str) -> Result:
    return Result(id=doc_id, status="error", error=code)


def extract(
    path: Path, media_type: str, limits: Limits, out_dir: Path, doc_id: str = ""
) -> Result:
    """Extract one document. Never raises: every failure is a Result with an error code.

    Pillow's pixel ceiling is a module global and warnings.catch_warnings() swaps the process
    warning filters. Both are set here and restored on exit. catch_warnings() is not thread-safe,
    so run extract() in one thread per process; the sandbox child does exactly that.
    """
    saved_pixel_limit = Image.MAX_IMAGE_PIXELS
    try:
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            pages = _extract_checked(path, media_type, limits, out_dir)
    except _Fail as failure:
        return fail(doc_id, failure.code)
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        return fail(doc_id, "bomb")
    except Exception:  # noqa: BLE001 - any decoder or library error is a bad_file, never a crash
        return fail(doc_id, "bad_file")
    finally:
        Image.MAX_IMAGE_PIXELS = saved_pixel_limit
    return Result(id=doc_id, status="ok", pages=pages)


def _extract_checked(
    path: Path, media_type: str, limits: Limits, out_dir: Path
) -> tuple[Page, ...]:
    if path.stat().st_size > limits.max_file_bytes:
        raise _Fail("too_large")
    data = path.read_bytes()
    if media_type not in ALLOWED_MEDIA or not _magic_matches(data[:MAGIC_HEAD_BYTES], media_type):
        raise _Fail("bad_type")
    if media_type == PDF:
        return _extract_pdf(data, limits, out_dir)
    return _extract_image(data, limits, out_dir)


def _magic_matches(head: bytes, media_type: str) -> bool:
    if media_type == PDF:
        return head.startswith(b"%PDF-")
    if media_type == PNG:
        return head.startswith(PNG_SIGNATURE)
    if media_type == JPEG:
        return head.startswith(JPEG_SIGNATURE)
    if media_type == WEBP:
        return head[0:4] == b"RIFF" and head[8:12] == b"WEBP"
    return False


def _extract_pdf(data: bytes, limits: Limits, out_dir: Path) -> tuple[Page, ...]:
    pdf = pdfium.PdfDocument(data)
    try:
        count = len(pdf)
        if count > limits.max_pages:
            raise _Fail("too_many_pages")
        pages: list[Page] = []
        for index in range(count):
            page = pdf[index]
            try:
                text = _clean_text(_page_text(page), limits.max_text_chars_per_page)
                if len(text) < limits.min_page_chars or _has_image_object(page):
                    png = _encode_png(_render_page(page, limits), limits)
                    image: str | None = _store(out_dir, index + 1, png)
                else:
                    image = None
            finally:
                page.close()
            pages.append(Page(n=index + 1, text=text, image=image))
        return tuple(pages)
    finally:
        pdf.close()


def _extract_image(data: bytes, limits: Limits, out_dir: Path) -> tuple[Page, ...]:
    with Image.open(io.BytesIO(data)) as img:
        png = _encode_png(img, limits)
    return (Page(n=1, text="", image=_store(out_dir, 1, png)),)


def _page_text(page: pdfium.PdfPage) -> str:
    textpage = page.get_textpage()
    try:
        return textpage.get_text_range()
    finally:
        textpage.close()


def _has_image_object(page: pdfium.PdfPage) -> bool:
    return any(True for _ in page.get_objects(filter=(pdfium_raw.FPDF_PAGEOBJ_IMAGE,)))


def _render_page(page: pdfium.PdfPage, limits: Limits) -> Image.Image:
    width, height = page.get_size()
    bitmap = page.render(scale=limits.max_image_side_px / max(width, height))
    try:
        return bitmap.to_pil()
    finally:
        bitmap.close()


def _encode_png(img: Image.Image, limits: Limits) -> bytes:
    """PNG with no metadata, long side <= max_image_side_px, size <= max_image_bytes."""
    # Palette and other modes are converted first: a raw copy would drop the palette and turn
    # every index into a grey level. Copying the pixels into a fresh image then drops every
    # info block (text, EXIF, ICC).
    if img.mode not in ("RGB", "RGBA", "L"):
        img = img.convert("RGBA" if "transparency" in img.info else "RGB")
    clean = Image.frombytes(img.mode, img.size, img.tobytes())
    clean.thumbnail((limits.max_image_side_px, limits.max_image_side_px))
    for _ in range(DOWNSCALE_TRIES):
        buf = io.BytesIO()
        clean.save(buf, format="PNG")
        if buf.tell() <= limits.max_image_bytes:
            return buf.getvalue()
        width, height = clean.size
        clean = clean.resize(
            (max(1, int(width * DOWNSCALE_FACTOR)), max(1, int(height * DOWNSCALE_FACTOR)))
        )
    raise _Fail("too_large")


def _store(out_dir: Path, n: int, png: bytes) -> str:
    name = f"p{n:04d}.png"
    (out_dir / name).write_bytes(png)
    return name


def _clean_text(raw: str, max_chars: int) -> str:
    kept = "".join(ch for ch in raw if ch == "\n" or unicodedata.category(ch) != "Cc")
    return kept[:max_chars]
