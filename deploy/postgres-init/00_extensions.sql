-- Auto-create extensions on first DB init.
-- This runs once when the data volume is empty (standard postgres image
-- behaviour for /docker-entrypoint-initdb.d/*.sql).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;

-- AGE requires search_path to INCLUDE ag_catalog for Cypher functions to
-- resolve unqualified (cypher(), create_graph(), ...) — it does NOT require
-- ag_catalog to come FIRST. Putting it first was the 2026-07-28 incident:
-- every unqualified CREATE TABLE in schema/*.sql landed in ag_catalog instead
-- of public, because that's simply the first schema Postgres tries for an
-- unqualified name. public first fixes new installs; an existing database
-- has to be repaired separately.
ALTER DATABASE exocortex SET search_path = public, "$user", ag_catalog;
