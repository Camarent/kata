"""Vulture whitelist: names that are used at runtime without a visible caller in code.

Vulture reads this file as code; it is never imported. Route handlers are silenced in
pyproject.toml ([tool.vulture] ignore_decorators).
"""

from kata_core.api.app import create_app
from kata_core.api.routes.auth import EnrolResponse
from kata_core.api.routes.jobs import JobStatusResponse
from kata_core.jobs.queue import Job
from kata_core.storage.marks import get_marks
from kata_core.storage.provision import create_database, drop_database, migrate
from kata_core.storage.taxonomy import find_topic, list_topics
from kata_core.storage.users import delete_user

# Tests and the e2e harness call the app factory; it is the entry point of the API package.
# Response fields: FastAPI serialises them to JSON, no code reads the attribute.
# Job fields: set by the row mapping in jobs/queue.py, read by tests/core/test_job_queue.py.
# Storage functions: called by tests (and scripts/db/kata_db.py for the provision ones), not core.
_ = (
    create_app,
    EnrolResponse.expires_in,
    JobStatusResponse.known,
    Job.lease_expires_at,
    Job.attempts,
    get_marks,
    create_database,
    drop_database,
    migrate,
    find_topic,
    list_topics,
    delete_user,
)
