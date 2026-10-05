-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/46_query_log_error_reason.sql — outcome of executing a query.
--
-- Why: a question that the engine could not answer (an exception in the
-- pipeline, a timeout, an exhausted daily budget) still gets its one row in
-- query_log, but nothing said it failed. `status` is NOT the place for that:
-- it tracks curation (logged → saved_as_question → promoted_to_source ...),
-- not execution. So execution gets its own nullable column.
--
-- NULL = the engine answered. Non-NULL = a human-readable reason why it did
-- not; rows written by the cockpit worker before the engine was reached start
-- with 'daily_limit:' (the budget query excludes them from the count).

ALTER TABLE query_log ADD COLUMN IF NOT EXISTS error_reason TEXT;

COMMENT ON COLUMN query_log.error_reason IS
    'NULL = answered; otherwise why the engine gave no answer (exception, timeout, daily_limit: ...).';
