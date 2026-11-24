"""Render each mockup HTML in a directory to light and dark narrow-width PNG screenshots.

Usage: python3 scripts/dev/render_design_shots.py MOCKUP_DIR [--out SHOTS_DIR]

Writes <stem>-light.png and <stem>-dark.png per *.html file into SHOTS_DIR (default
MOCKUP_DIR/shots, created when missing). Uses a local headless Chrome; nothing is fetched
from the network, the pages are opened as file:// URLs.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHROME_NAMES = ("google-chrome", "chromium", "chromium-browser")
# Narrow phone-like viewport: the mockups are checked at this width.
WINDOW_SIZE = "390,844"
# Colour schemes rendered per page. Each one is forced through the <html data-theme> attribute,
# which tokens.css reads. Headless Chrome ignores --blink-settings=preferredColorScheme.
SCHEMES = ("light", "dark")
RENDER_TIMEOUT_SECONDS = 60
HTML_TAG = re.compile(r"<html\b[^>]*>", re.IGNORECASE)
THEME_ATTR = re.compile(r'\sdata-theme="[^"]*"')


def find_chrome() -> str | None:
    """Return the first headless-capable Chrome or Chromium on PATH, or None."""
    for name in CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def themed_html(text: str, scheme: str) -> str:
    """Return the page with <html data-theme=SCHEME> set. Raises RuntimeError without <html>."""
    match = HTML_TAG.search(text)
    if match is None:
        raise RuntimeError("no <html> tag to set the colour scheme on")
    tag = match.group(0)
    if THEME_ATTR.search(tag):
        new_tag = THEME_ATTR.sub(f' data-theme="{scheme}"', tag, count=1)
    else:
        new_tag = f'{tag[:-1]} data-theme="{scheme}">'
    return text[: match.start()] + new_tag + text[match.end() :]


def render_one(chrome: str, html: Path, png: Path, scheme: str) -> None:
    """Screenshot one themed page for one colour scheme. Raises RuntimeError when Chrome fails."""
    command = [
        chrome,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        f"--window-size={WINDOW_SIZE}",
        f"--screenshot={png}",
        html.resolve().as_uri(),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=RENDER_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"chrome timed out on {html.name} ({scheme})") from error
    if result.returncode != 0 or not png.is_file():
        raise RuntimeError(f"chrome failed on {html.name} ({scheme}): {result.stderr.strip()}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render mockup HTML to light and dark PNG shots.")
    parser.add_argument("mockup_dir", type=Path, help="directory holding the mockup *.html files")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory for the PNGs (default: MOCKUP_DIR/shots)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    mockup_dir: Path = args.mockup_dir
    if not mockup_dir.is_dir():
        print(f"render_design_shots: not a directory: {mockup_dir}", file=sys.stderr)
        return 2
    pages = sorted(mockup_dir.glob("*.html"))
    if not pages:
        print(f"render_design_shots: no *.html in {mockup_dir}", file=sys.stderr)
        return 2
    chrome = find_chrome()
    if chrome is None:
        names = ", ".join(CHROME_NAMES)
        print(f"render_design_shots: no headless Chrome found (tried {names})", file=sys.stderr)
        return 1
    out_dir: Path = args.out if args.out is not None else mockup_dir / "shots"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = len(pages) * len(SCHEMES)
    done = 0
    # Themed copies go to a scratch dir removed on exit; source files are never changed.
    with tempfile.TemporaryDirectory() as scratch:
        for scheme in SCHEMES:
            theme_dir = Path(scratch) / scheme
            theme_dir.mkdir()
            for item in mockup_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, theme_dir / item.name)
            for html in pages:
                png = out_dir / f"{html.stem}-{scheme}.png"
                try:
                    source = html.read_text(encoding="utf-8")
                    themed = theme_dir / html.name
                    themed.write_text(themed_html(source, scheme), encoding="utf-8")
                    render_one(chrome, themed, png, scheme)
                except (OSError, RuntimeError) as error:
                    print(f"render_design_shots: {error}", file=sys.stderr)
                    return 1
                done += 1
                line = f"render_design_shots: {done}/{total} {png.name}"
                print(line, file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
