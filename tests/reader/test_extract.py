"""extract() on the hostile corpus: each bad file gets its exact error code, nothing crashes."""

from __future__ import annotations

import dataclasses
import io

from kata_reader import Limits, extract
from kata_reader.extract import PDF, PNG
from PIL import Image

from tests.reader.conftest import PAGE_TEXT, Corpus, bomb_png, make_pdf, png_bytes

JS_CATALOG = "/OpenAction << /S /JavaScript /JS (app.alert) >>"


def _run(corpus: Corpus, name: str, data: bytes, media: str, limits: Limits | None = None):
    path = corpus.write(name, data)
    return extract(path, media, limits or Limits(), corpus.out_dir(), doc_id="d1")


def _png_long_side(data: bytes) -> int:
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return max(width, height)


def test_good_two_page_pdf_extracts_text_per_page(corpus: Corpus) -> None:
    data = make_pdf([PAGE_TEXT, PAGE_TEXT])
    result = _run(corpus, "good.pdf", data, PDF)
    assert result.status == "ok", result
    assert result.error is None
    assert result.id == "d1"
    assert [p.n for p in result.pages] == [1, 2]
    assert PAGE_TEXT in result.pages[0].text


def test_truncated_pdf_is_bad_file(corpus: Corpus) -> None:
    good = make_pdf([PAGE_TEXT, PAGE_TEXT])
    result = _run(corpus, "trunc.pdf", good[: len(good) // 2], PDF)
    assert result.status == "error"
    assert result.error == "bad_file"


def test_page_count_bomb_is_too_many_pages(corpus: Corpus) -> None:
    data = make_pdf([""] * 51)
    result = _run(corpus, "pages.pdf", data, PDF, Limits(max_pages=50))
    assert result.error == "too_many_pages"


def test_decompression_bomb_png_is_bomb(corpus: Corpus) -> None:
    # 60000 x 60000 claimed pixels: far above twice MAX_IMAGE_PIXELS, from a tiny file.
    result = _run(corpus, "bomb.png", bomb_png(60000, 60000), PNG)
    assert result.error == "bomb"


def test_wrong_magic_png_labelled_pdf_is_bad_type(corpus: Corpus) -> None:
    result = _run(corpus, "fake.pdf", png_bytes(8, 8), PDF)
    assert result.error == "bad_type"


def test_pdf_with_javascript_action_still_extracts_text(corpus: Corpus) -> None:
    result = _run(corpus, "js.pdf", make_pdf([PAGE_TEXT], JS_CATALOG), PDF)
    assert result.status == "ok", result
    assert PAGE_TEXT in result.pages[0].text


def test_polyglot_pdf_header_with_png_tail_is_bad_type(corpus: Corpus) -> None:
    # A PDF header on a PNG body: labelled as png, the signature check must refuse it.
    data = b"%PDF-1.4\n" + png_bytes(8, 8)
    result = _run(corpus, "poly.png", data, PNG)
    assert result.error == "bad_type"


def test_oversize_file_is_too_large(corpus: Corpus) -> None:
    data = make_pdf([PAGE_TEXT])
    limits = dataclasses.replace(Limits(), max_file_bytes=len(data) - 1)
    result = _run(corpus, "big.pdf", data, PDF, limits)
    assert result.error == "too_large"


def test_scan_page_gets_bounded_png_image(corpus: Corpus) -> None:
    # Page 1 has text; page 2 has none, so it is a scan and gets a rendered PNG.
    result = _run(corpus, "scan.pdf", make_pdf([PAGE_TEXT, ""]), PDF)
    assert result.status == "ok", result
    scan = result.pages[1]
    assert scan.image is not None
    assert result.pages[0].image is None
    png = (corpus.out_dir() / scan.image).read_bytes()
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert _png_long_side(png) <= Limits().max_image_side_px


def test_extract_restores_pillow_pixel_limit(corpus: Corpus) -> None:
    before = Image.MAX_IMAGE_PIXELS
    result = _run(corpus, "ok.png", png_bytes(8, 8), PNG)
    assert result.status == "ok", result
    assert Image.MAX_IMAGE_PIXELS == before


def test_palette_png_keeps_its_colours(corpus: Corpus) -> None:
    # Left half palette index 0 (red), right half index 1 (blue); a raw copy would lose both.
    src = Image.new("P", (40, 20))
    src.putpalette([255, 0, 0, 0, 0, 255] + [0, 0, 0] * 254)
    src.putdata([0 if x < 20 else 1 for _ in range(20) for x in range(40)])
    buf = io.BytesIO()
    src.save(buf, format="PNG")
    result = _run(corpus, "palette.png", buf.getvalue(), PNG)
    assert result.status == "ok", result
    out = Image.open(corpus.out_dir() / result.pages[0].image).convert("RGB")
    assert out.getpixel((5, 10)) == (255, 0, 0)
    assert out.getpixel((35, 10)) == (0, 0, 255)


def test_png_input_is_reencoded_within_side_cap(corpus: Corpus) -> None:
    result = _run(corpus, "ok.png", png_bytes(3000, 1200), PNG)
    assert result.status == "ok", result
    png = (corpus.out_dir() / result.pages[0].image).read_bytes()
    assert _png_long_side(png) <= Limits().max_image_side_px
