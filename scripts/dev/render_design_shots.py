"""Render each mockup HTML in a directory to light and dark narrow-width PNG screenshots.

Usage: python3 scripts/dev/render_design_shots.py MOCKUP_DIR [--out SHOTS_DIR]

Writes <stem>-light.png and <stem>-dark.png per *.html file into SHOTS_DIR (default
MOCKUP_DIR/shots, created when missing). Uses a local headless Chrome; nothing is fetched
from the network, the pages are opened as file:// URLs.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

CHROME_NAMES = ("google-chrome", "chromium", "chromium-browser")
# Narrow phone-like viewport: the mockups are checked at this width.
WINDOW_SIZE = "390,844"
# Blink preferredColorScheme values: 1 is dark, 2 is light.
SCHEMES = {"light": 2, "dark": 1}
RENDER_TIMEOUT_SECONDS = 60


def find_chrome() -> str | None:
    """Return the first headless-capable Chrome or Chromium on PATH, or None."""
    for name in CHROME_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


def render_one(chrome: str, html: Path, png: Path, scheme: str) -> None:
    """Screenshot one page in one colour scheme. Raises RuntimeError when Chrome fails."""
    command = [
        chrome,
        "--headless=new",
        "--no-sandbox",
        "--disable-gpu",
        f"--window-size={WINDOW_SIZE}",
        f"--blink-settings=preferredColorScheme={SCHEMES[scheme]}",
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
    for html in pages:
        for scheme in SCHEMES:
            png = out_dir / f"{html.stem}-{scheme}.png"
            try:
                render_one(chrome, html, png, scheme)
            except RuntimeError as error:
                print(f"render_design_shots: {error}", file=sys.stderr)
                return 1
            done += 1
            print(f"render_design_shots: {done}/{total} {png.name}", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
