# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/db/__init__.py — backwards-compatible re-exports from the split package.
#
# F2.1: workers/db.py was split into:
#   - pool.py      — connection pool + query helpers
#   - embeddings.py — OpenAI embedding generation
#   - graph.py     — AGE graph dual-write
#   - ingest.py    — high-level ingestion + edge emission
#
# All existing `from exocortex.db import X` imports continue to work.

from .embeddings import (
    get_embedding,
    get_embeddings_batch,
)
from .graph import (
    _insert_edge,
)
from .ingest import (
    _emit_meeting_edges,
    _emit_synthesis_edges,
    _emit_thread_edges,
    _is_uuid,
    _split_participants,
    _upsert_entity,
    add_revisit,
    append_session_thought,
    complete_session,
    create_frp_session,
    emit_meeting_edges,
    emit_synthesis_edges,
    emit_thread_edges,
    find_session_by_date,
    ingest_note,
    ingest_print_log,
    ingest_source,
)
from .pool import (
    Jsonb as Jsonb,  # noqa: F401
)
from .pool import (
    _conninfo,
    conn,
    execute,
    get_pool,
    get_tenant_id,
    insert_returning,
    query,
    query_one,
    update_where,
)

__all__ = [  # noqa: RUF022 — grouped by submodule, comments kept
    # pool
    'conn', 'execute', 'get_pool', 'get_tenant_id',
    'insert_returning', 'query', 'query_one', 'update_where', '_conninfo',
    # embeddings
    'get_embedding', 'get_embeddings_batch',
    # graph
    '_insert_edge',
    # ingest
    'add_revisit', 'append_session_thought', 'complete_session',
    'create_frp_session', 'emit_meeting_edges', 'emit_synthesis_edges',
    'emit_thread_edges', 'find_session_by_date', 'ingest_note',
    'ingest_print_log', 'ingest_source',
    '_emit_meeting_edges', '_emit_synthesis_edges', '_emit_thread_edges',
    '_is_uuid', '_split_participants', '_upsert_entity',
]
