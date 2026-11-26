"""OpenAPI export: the FastAPI app schema as sorted-key JSON text, the file docs/openapi.json holds.

The dev regenerates the file with `python -m kata_core.api.openapi_export [PATH]`.
tests/core/test_openapi_export.py fails when the committed file differs from this output.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from kata_core.api.app import create_app
from kata_core.config import Config

# core/kata_core/api/openapi_export.py -> repo root is four parents up.
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "docs" / "openapi.json"


def schema_text() -> str:
    """Schema of the app as JSON text with sorted keys; equal on every call.

    The schema needs no config value: routers only read cfg when a request runs.
    """
    app = create_app(Config(sections={}))
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    target = Path(argv[0]) if argv else DEFAULT_PATH
    target.write_text(schema_text(), encoding="utf-8")
    print(f"wrote {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
