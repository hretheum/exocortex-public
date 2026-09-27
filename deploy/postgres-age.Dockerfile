# Postgres 16 + pgvector + Apache AGE 1.6.0
#
# Single-image DB for Exocortex.  Starts from the official pgvector image (PG 16
# + pgvector pre-installed) and adds Apache AGE 1.6.0 built from the
# release/PG16/1.6.0 branch (functionally equivalent to tag PG16/v1.6.0-rc0;
# both point at the same upstream commit).  Both extensions auto-create on
# first init via deploy/postgres-init/*.sql.
#
# Build:  docker build -f deploy/postgres-age.Dockerfile -t exocortex-db .
# First build ~2 min, subsequent <5 s (layer cache).
FROM pgvector/pgvector:pg16

ARG AGE_BRANCH=release/PG16/1.6.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-server-dev-16 build-essential git flex bison ca-certificates \
    && git clone --depth 1 --branch ${AGE_BRANCH} https://github.com/apache/age.git /tmp/age \
    && cd /tmp/age && make PG_CONFIG=$(which pg_config) && make install \
    && rm -rf /tmp/age \
    && apt-get remove -y build-essential git flex bison postgresql-server-dev-16 \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Auto-create vector + age extensions on first DB init
COPY deploy/postgres-init/ /docker-entrypoint-initdb.d/
