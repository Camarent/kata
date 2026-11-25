"""Quiz: the allowlist of sources a quiz question may be grounded in, and the checked fetch of them.

The fetch (SSRF block, size cap, plain text, no link following) lives in `kata_core.quiz.fetch`.
"""

from kata_core.quiz.allowlist import DEFAULT_SOURCES, Source, Tier, classify, exams_allowed

__all__ = ["DEFAULT_SOURCES", "Source", "Tier", "classify", "exams_allowed"]
