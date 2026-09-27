-- F31.3.1 — cockpit actions pending table.
-- Stores Notion property changes waiting to be applied to vault/PG.
-- Idempotent via UNIQUE (dedup_hash).

CREATE TABLE IF NOT EXISTS cockpit_actions_pending (
    id               BIGSERIAL   PRIMARY KEY,
    audience_name    TEXT        NOT NULL,
    page_id          TEXT        NOT NULL,
    property_name    TEXT        NOT NULL,
    notion_edited_at TIMESTAMPTZ NOT NULL,
    notion_value     JSONB       NOT NULL,
    vault_value      JSONB,
    resolved_value   JSONB,
    winner           TEXT,
    status           TEXT        NOT NULL DEFAULT 'pending',
    dedup_hash       TEXT        NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at     TIMESTAMPTZ,
    CONSTRAINT cockpit_actions_dedup UNIQUE (dedup_hash)
);

CREATE INDEX IF NOT EXISTS cockpit_actions_status_idx
    ON cockpit_actions_pending (status, created_at);

COMMENT ON TABLE cockpit_actions_pending IS
    'F31.3.1 — pending Notion→vault property changes from the cockpit poller.';
