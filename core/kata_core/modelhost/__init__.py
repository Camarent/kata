"""Modelhost: job kinds that control the local model host (start, use, measure, status).

`spec.py` holds the kinds and the payload allow-list. `job_kinds.py` holds the output hooks
that the job runner finds through `load_registry`. This package registers no handlers: the
worker runs the modelhost jobs.
"""
