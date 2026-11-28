"""Exam mode: the in-memory analysis lane. Pure: no I/O, no clock reads, no logging.

`matching.py` validates the model reply that analyses a practice exam (`parse_analysis`) and
matches its topic and concept names to the taxonomy read-only (`match_analysis`). Nothing here
writes; the proposals service (task-7) does that after the user confirms.
"""

from __future__ import annotations
