"""OpenAPI export: deterministic output, committed docs/openapi.json kept in step, review routes listed."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from kata_core.api import openapi_export

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED = REPO_ROOT / "docs" / "openapi.json"


def test_schema_text_is_deterministic() -> None:
    assert openapi_export.schema_text() == openapi_export.schema_text()


def test_committed_openapi_matches_generated_text() -> None:
    committed = COMMITTED.read_text(encoding="utf-8")
    assert committed == openapi_export.schema_text(), (
        "docs/openapi.json is stale: regenerate with "
        "`python -m kata_core.api.openapi_export docs/openapi.json`"
    )


def test_schema_lists_review_routes() -> None:
    paths = json.loads(openapi_export.schema_text())["paths"]
    assert "/v1/review/tree" in paths
    assert "/v1/review/concepts" in paths


def test_main_writes_generated_text_to_given_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "openapi.json"
        assert openapi_export.main([str(target)]) == 0
        assert target.read_text(encoding="utf-8") == openapi_export.schema_text()
