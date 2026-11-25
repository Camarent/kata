# Kata image: one image for kata-core (default CMD) and kata-migrate (run the migrate CLI).
#   Build: every line of deploy/versions.env as --build-arg (see that file's header).
#   Serve: docker run -e KATA_CONFIG=/config/kata.toml -v ...  (default CMD: python -m kata_core)
#   Migrate: docker run --rm <image> python -m kata_core.migrate
# Versions and hashes come only from build args; no secret is baked into the image.

ARG PY_BASE_IMAGE
ARG PY_BASE_DIGEST

# Base: the tag comes from versions.env and the digest pins the exact manifest.
FROM ${PY_BASE_IMAGE}@${PY_BASE_DIGEST} AS base

# Fetch: gitleaks and the trainer tarball (dojo CLI), each checked against a pinned sha256.
FROM base AS fetch
ARG GITLEAKS_VERSION
ARG GITLEAKS_SHA256
ARG TRAINER_URL
ARG TRAINER_SHA256
RUN test -n "${GITLEAKS_VERSION}" && test -n "${GITLEAKS_SHA256}" \
 && test -n "${TRAINER_URL}" && test -n "${TRAINER_SHA256}" \
 || { echo "deploy/versions.env: fill GITLEAKS_* and TRAINER_* before building" >&2; exit 1; }
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/gitleaks.tgz \
      "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
 && echo "${GITLEAKS_SHA256}  /tmp/gitleaks.tgz" | sha256sum -c - \
 && tar -xzf /tmp/gitleaks.tgz -C /usr/local/bin gitleaks \
 && rm /tmp/gitleaks.tgz
# Trainer tarball: root layout dojo, dojo.wasm, web/. Unpacked read-only (no write bit) into /opt/trainer.
RUN curl -fsSL -o /tmp/trainer.tgz "${TRAINER_URL}" \
 && echo "${TRAINER_SHA256}  /tmp/trainer.tgz" | sha256sum -c - \
 && mkdir -p /opt/trainer \
 && tar -xzf /tmp/trainer.tgz -C /opt/trainer \
 && chmod -R a=rX /opt/trainer \
 && chmod 0755 /opt/trainer/dojo \
 && rm /tmp/trainer.tgz

# Deps: the runtime dependency list is read from pyproject.toml (pinned versions) into a venv.
FROM base AS deps
COPY pyproject.toml /build/pyproject.toml
RUN python -m venv /opt/venv \
 && python -c "import tomllib; project = tomllib.load(open('/build/pyproject.toml', 'rb'))['project']; print('\n'.join(project['dependencies'] + project['optional-dependencies']['reader']))" > /build/requirements.txt \
 && /opt/venv/bin/pip install --no-cache-dir -r /build/requirements.txt

# Runtime: non-root user, venv, fetched tools, and the core package only.
FROM base AS runtime
ARG EMBED_MODEL_ID
ARG EMBED_MODEL_REVISION
LABEL kata.embed-model="${EMBED_MODEL_ID}@${EMBED_MODEL_REVISION}"
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/core:/app/worker:/app/reader \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KATA_CORE_PORT=8080
RUN groupadd --system --gid 10001 kata \
 && useradd --system --uid 10001 --gid kata --home-dir /app --shell /usr/sbin/nologin kata
# Spool dirs for the worker/reader hand-off. Owned by kata so a new named volume copies that owner on first mount.
RUN mkdir -p /spool/in /spool/out \
 && chown 10001:10001 /spool/in /spool/out
COPY --from=deps /opt/venv /opt/venv
COPY --from=fetch /usr/local/bin/gitleaks /usr/local/bin/
COPY --from=fetch /opt/trainer /opt/trainer
WORKDIR /app
COPY core/ /app/core/
# kata_core.config reads its defaults from /app/config/kata.example.toml (EXAMPLE_PATH).
COPY config/ /app/config/
COPY worker/ /app/worker/
COPY reader/ /app/reader/
USER kata
EXPOSE 8080
# Deep health: DB reachable and all migrations applied. Port follows KATA_CORE_PORT.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['KATA_CORE_PORT'] + '/v1/health/deep', timeout=4)"
CMD ["python", "-m", "kata_core"]
