"""Scan job kinds, found by the job runner through `load_registry`.

`scan.classify` has an output hook that resolves the classified page to the owner's taxonomy.
`scan.extract` has an output hook that filters the blocks, resolves the concepts and rewrites the output.
"""

from __future__ import annotations

from kata_core.jobs.runner import Handler, OutputHook
from kata_core.scan.classify import classify_output_hook
from kata_core.scan.extract import extract_output_hook

SCAN_CLASSIFY_KIND = "scan.classify"
SCAN_EXTRACT_KIND = "scan.extract"

HANDLERS: dict[str, Handler] = {}
OUTPUT_HOOKS: dict[str, OutputHook] = {
    SCAN_CLASSIFY_KIND: classify_output_hook,
    SCAN_EXTRACT_KIND: extract_output_hook,
}
