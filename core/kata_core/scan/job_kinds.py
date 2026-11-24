"""Scan job kinds, found by the job runner through `load_registry`.

`scan.classify` has an output hook that resolves the classified page to the owner's taxonomy.
Task 11 adds the extract hook to `OUTPUT_HOOKS`.
"""

from __future__ import annotations

from kata_core.jobs.runner import Handler, OutputHook
from kata_core.scan.classify import classify_output_hook

SCAN_CLASSIFY_KIND = "scan.classify"

HANDLERS: dict[str, Handler] = {}
OUTPUT_HOOKS: dict[str, OutputHook] = {SCAN_CLASSIFY_KIND: classify_output_hook}
