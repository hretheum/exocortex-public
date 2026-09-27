-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/13_email_threads.sql — F6.1.1: Gmail thread aggregation.
--
-- One row per Gmail thread (conversation). Capture-API receives gmail-thread
-- payloads from `workers/sources/gmail.py` (F6.2.2) and upserts into this table
-- BEFORE INSERTing the corresponding raw_sources row (uri = gmail thread URL).
--
-- Status transitions (F6.3.2):
--   active             → at least one new message in last 24h
--   ready_for_synthesis → quiescent for 24h+, processor not run yet
--   synthesized        → email_thread_synthesis thought emitted, summary_thought_id set
--   archived           → user-marked done (manual flag in Gmail or wiki)
--
-- Idempotent (UNIQUE on tenant_id + gmail_thread_id).

CREATE TABLE IF NOT EXISTS email_threads (
    id                    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id             UUID         NOT NULL,
    gmail_thread_id       TEXT         NOT NULL,
    subject               TEXT,
    message_count         INTEGER      NOT NULL DEFAULT 0,
    first_message_at      TIMESTAMPTZ,
    last_message_at       TIMESTAMPTZ,
    status                TEXT         NOT NULL DEFAULT 'active'
                                        CHECK (status IN ('active',
                                                          'ready_for_synthesis',
                                                          'synthesized',
                                                          'archived')),
    summary_thought_id    UUID         REFERENCES thoughts(id) ON DELETE SET NULL,
    metadata              JSONB        NOT NULL DEFAULT '{}',
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, gmail_thread_id)
);

CREATE INDEX IF NOT EXISTS idx_email_threads_tenant_status
    ON email_threads(tenant_id, status);

CREATE INDEX IF NOT EXISTS idx_email_threads_last_message
    ON email_threads(tenant_id, last_message_at DESC);

COMMENT ON TABLE email_threads IS
    'F6.1.1 — Gmail thread aggregation. One row per conversation, updated as '
    'new messages arrive. summary_thought_id points to the email_thread_synthesis '
    'thought once F6.3.2 processor runs.';

