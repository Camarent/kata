"""Vulture whitelist: names that are used at runtime without a visible caller in code.

Vulture reads this file as code; it is never imported. Route handlers are silenced in
pyproject.toml ([tool.vulture] ignore_decorators).
"""

from kata_core.api.app import create_app
from kata_core.api.routes.auth import EnrolResponse
from kata_core.api.routes.jobs import JobStatusResponse

# Tests and the e2e harness call the app factory; it is the entry point of the API package.
# Response fields: FastAPI serialises them to JSON, no code reads the attribute.
_ = (create_app, EnrolResponse.expires_in, JobStatusResponse.known)
