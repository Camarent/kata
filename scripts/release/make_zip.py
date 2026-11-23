"""Build a reproducible release zip from a dist folder.

Usage: python3 -I scripts/release/make_zip.py <dist_dir> <out.zip>

Every regular file under <dist_dir> goes into the zip, under its path relative to <dist_dir>
with forward slashes. Entries are written in sorted name order, with a fixed timestamp
(1980-01-01 00:00:00, the zip epoch) and fixed mode (0644), so two runs over the same tree give
identical bytes. Directories are not entries: the zip name list equals the dist file list.
"""

from __future__ import annotations

import argparse
import stat
import sys
import zipfile
from pathlib import Path

ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
FILE_MODE = 0o644


def dist_files(dist_dir: Path) -> list[str]:
    """Sorted posix paths of every regular file under dist_dir, relative to it."""
    names = [
        path.relative_to(dist_dir).as_posix()
        for path in dist_dir.rglob("*")
        if stat.S_ISREG(path.lstat().st_mode)
    ]
    return sorted(names)


def build_zip(dist_dir: Path, out_zip: Path) -> list[str]:
    """Write out_zip from dist_dir and return the entry names in the order written."""
    names = dist_files(dist_dir)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            info = zipfile.ZipInfo(name, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | FILE_MODE) << 16
            archive.writestr(info, (dist_dir / name).read_bytes())
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a reproducible release zip.")
    parser.add_argument("dist_dir", type=Path, help="folder whose files go into the zip")
    parser.add_argument("out_zip", type=Path, help="zip file to write")
    args = parser.parse_args(argv)
    if not args.dist_dir.is_dir():
        print(f"make_zip: not a folder: {args.dist_dir}", file=sys.stderr)
        return 2
    names = build_zip(args.dist_dir, args.out_zip)
    print(f"make_zip: wrote {len(names)} entries to {args.out_zip}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
