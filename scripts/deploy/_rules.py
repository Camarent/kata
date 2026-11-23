"""Rules shared by the deploy checks (scripts/deploy/check_image_rules.py, validate_stack.py)."""

from __future__ import annotations


def _image_pinned(image: str) -> bool:
    """A digest pins the image; otherwise the last path part needs a tag other than latest."""
    if "@" in image:
        return True
    last = image.rsplit("/", 1)[-1]
    if ":" not in last:
        return False
    return last.rsplit(":", 1)[1] != "latest"
