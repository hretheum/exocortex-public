# Exocortex — capture API + worker container
#
# Build:  docker build -t exocortex-api .
# Run:    docker run -p 8000:8000 --env-file .env exocortex-api
#
# Multi-stage build: <500 MB runtime target.
# Requires Postgres reachable via PG_* env vars (see config/.env.example).

# ── Stage 1: builder ────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Create venv in a fixed path so the runtime stage can copy it.
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY requirements.txt pyproject.toml ./
COPY exocortex/ ./exocortex/
# Bundle llm_router from vendored source (private repo, not on PyPI).
COPY vendor/ ./vendor/

# Install vendored llm_router first (no PyPI lookup needed), then runtime deps
# + the package itself (editable not needed in the image).
RUN pip install --no-cache-dir ./vendor/ \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps .

# ── Stage 2: runtime ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/hretheum/exocortex"
LABEL org.opencontainers.image.description="Exocortex — Personal Knowledge OS (capture API + workers)"
LABEL org.opencontainers.image.licenses="Apache-2.0 WITH Commons-Clause"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    VIRTUAL_ENV=/opt/venv

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/exocortex

COPY --from=builder /opt/venv /opt/venv
COPY . .

RUN mkdir -p /opt/exocortex-vault /var/log/exocortex

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# Default: apply pending migrations, then start the capture API.
# `sh -e` aborts the container if `exocortex migrate up` fails — better to
# crash loudly than to start uvicorn against half-applied schema.
# Override `command:` in docker-compose for worker variants.
CMD ["sh", "-ec", "echo '[entrypoint] running migrations...'; exocortex migrate up; echo '[entrypoint] migrations ok, starting uvicorn on :${PORT:-8000}'; exec uvicorn exocortex.capture_api:app --host 0.0.0.0 --port ${PORT:-8000}"]
