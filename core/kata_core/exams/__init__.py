"""Exam results: parsing the result payload that a dojo result or a page exam sends to kata.

`parse.py` turns the JSON payload into an `ExamResult`. Nothing here stores or applies it;
the import service (task-10) does that after the user confirms.
"""
