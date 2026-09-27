# Schema migrations

Postgres schema for Exocortex is split into ordered `*.sql` files in this
directory. The `exocortex migrate` CLI applies them idempotently and tracks
every successful apply in the `exocortex_migrations` table.

## Quick start

```bash
# 1. point at your database (see config/.env.example)
export PG_HOST=localhost PG_PORT=5432 PG_DATABASE=exocortex \
       PG_USER=exocortex PG_PASSWORD=...

# 2. show what would happen
exocortex migrate status

# 3. apply all pending migrations
exocortex migrate up
```

A second `exocortex migrate up` is a no-op when nothing changed on disk.

## Ordering

Files are applied in lexicographic order, so prefix every new migration with
the next free two-digit index. `00_migrations.sql` is the bootstrap; it
creates the tracking table itself and **must remain first**.

```
00_migrations.sql            ← tracking table (bootstrap)
01_base.sql                  ← thoughts / edges / sources
…
25_knowledge_arch_edge_types.sql
```

`views.sql` is **not** tracked — it contains idempotent `CREATE OR REPLACE
VIEW` statements that are safe to re-apply by hand:

```bash
psql "$EXOCORTEX_DB_URL" -f schema/views.sql
```

## Adding a new migration

1. Pick the next free prefix (e.g. `26_my_feature.sql`).
2. **Do not** wrap statements in `BEGIN; … COMMIT;`. The runner owns the
   transaction: every file is applied inside one explicit transaction and
   recorded in `exocortex_migrations` atomically. An embedded `COMMIT;` would
   commit the outer transaction early and leak the tracking-table `INSERT`
   outside of it — on the next failure the migration would be applied but
   never recorded, causing a re-apply on the following run.
3. Statements that **cannot** run inside a transaction (`CREATE INDEX
   CONCURRENTLY`, `VACUUM`, `CREATE DATABASE`, `ALTER SYSTEM`, …) do not
   belong in tracked migrations — apply them out-of-band and document the
   step in the runbook. None of the migrations shipped today need this.
4. Run `exocortex migrate up` locally to verify it applies cleanly.
5. Commit the file. The next `exocortex migrate up` in CI / production will
   pick it up automatically.

## Drift detection

Each tracked file is hashed with SHA-256 at apply time. On every later run
the hash is recomputed; if it differs from the stored value the migrate
command **refuses to run** any new migrations and reports the offending
file. This prevents the common foot-gun of editing an already-applied file
and getting a half-migrated database.

If you genuinely need to change an applied migration:

- prefer **forward-only**: write a new migration that fixes things.
- if recovery is the only option, manually update the row in
  `exocortex_migrations` (set the new hash) **after** you have replayed the
  changes against your database.

### F31.8.3 rebaseline (one-off)

F31.8.3 stripped the embedded `BEGIN; … COMMIT;` blocks out of every shipped
schema file — the runner now owns the transaction. The file *contents* are
otherwise unchanged, but every hash flipped. Existing deployments that
already have rows in `exocortex_migrations` must rebaseline once:

```sql
-- run after pulling the F31.8.3 post-review commit
-- recomputes the stored hash for every already-applied file
UPDATE exocortex_migrations m
SET hash = encode(digest(pg_read_file('schema/' || m.filename), 'sha256'), 'hex');
```

Alternatively, recompute the hashes off-line and `UPDATE` each row by hand.
Without this step the next `exocortex migrate up` will refuse to run with a
`MigrationError("drift")`.

## Anatomy of the tracking table

```sql
CREATE TABLE exocortex_migrations (
    filename   TEXT PRIMARY KEY,
    hash       TEXT NOT NULL,         -- sha256 hex digest
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

The runner inserts one row per successfully applied file. Failed applies
roll back the entire file transaction, so no partial state is recorded.
