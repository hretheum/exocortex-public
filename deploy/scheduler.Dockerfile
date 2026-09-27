# Exocortex — scheduler image (supercronic + exocortex workers)
#
# Inherits the same Python env as the API image but adds supercronic
# so cron-in-Docker works with proper signal handling and env inheritance.
#
# Build: docker build -f deploy/scheduler.Dockerfile -t exocortex-scheduler .

ARG SUPERCRONIC_VERSION=0.2.33

# ── Stage 1: builder (same venv pattern as main Dockerfile) ──────────────────
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

COPY requirements.txt pyproject.toml ./
COPY exocortex/ ./exocortex/
COPY vendor/ ./vendor/

RUN pip install --no-cache-dir ./vendor/ \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --no-deps .

# ── Stage 2: fetch supercronic ───────────────────────────────────────────────
FROM alpine:3.20 AS supercronic-dl

ARG SUPERCRONIC_VERSION
RUN apk add --no-cache curl ca-certificates \
    && curl -fsSL \
        "https://github.com/aptible/supercronic/releases/download/v${SUPERCRONIC_VERSION}/supercronic-linux-amd64" \
        -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic

# ── Stage 3: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/hretheum/exocortex"
LABEL org.opencontainers.image.description="Exocortex — scheduler (supercronic)"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    VIRTUAL_ENV=/opt/venv

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/exocortex

COPY --from=builder /opt/venv /opt/venv
COPY . .
COPY --from=supercronic-dl /usr/local/bin/supercronic /usr/local/bin/supercronic

RUN mkdir -p /etc/exocortex /var/log/exocortex /opt/exocortex-vault
COPY deploy/crontab.docker /etc/exocortex/crontab

CMD ["/usr/local/bin/supercronic", "/etc/exocortex/crontab"]
