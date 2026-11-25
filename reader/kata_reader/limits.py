"""Reader limits: one frozen value the caller builds from the [reader] config block.

The defaults equal the [reader] values in config/kata.example.toml, so a bare Limits() is the
documented configuration. Nothing here reads a file or the environment.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    max_file_bytes: int = 10485760
    max_pages: int = 50
    min_page_chars: int = 40
    max_image_side_px: int = 1600
    max_image_bytes: int = 2097152
    max_text_chars_per_page: int = 20000
    child_memory_mb: int = 1024
    child_cpu_seconds: int = 30
    wall_seconds: int = 60
