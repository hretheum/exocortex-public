# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# workers/db/graph.py — AGE graph dual-write helpers.

from __future__ import annotations
import os
import re

from exocortex.settings import get_settings

AGE_GRAPH = os.environ.get('PG_AGE_GRAPH') or get_settings().age_graph

# Mapping src_type/dst_type → AGE node label (Cypher labels need to be valid identifiers)
_AGE_LABEL = {
    'thought': 'Thought',
    'entity': 'Entity',
    'frp_session': 'FrpSession',
    'raw_source': 'RawSource',
    'project': 'Project',
    'person': 'Person',
    'client': 'Client',
    'email_thread': 'EmailThread',
    'material': 'Material',
    'ingredient': 'Ingredient',
    'synthesis': 'Synthesis',
}

# All valid edge-type nodes in the graph (anything not here is rejected)
_AGE_LABEL_RE = re.compile(r'^[A-Z][A-Za-z0-9]*$')
_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


def _age_label(node_type: str) -> str:
    """Map relational src_type/dst_type to AGE node label.

    Only known types are mapped; unknown types that don't start with an
    uppercase letter and contain only alphanumeric chars are rejected.
    """
    label = _AGE_LABEL.get(node_type)
    if label is not None:
        return label
    # Accept simple CamelCase fallbacks from known tables only
    if _AGE_LABEL_RE.match(node_type):
        return node_type
    raise ValueError(f"Invalid AGE node type: {node_type!r}")


def _escape_cypher_string(s: str) -> str:
    """Escape a string value for safe interpolation into a Cypher query."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\0", "")


def _validate_uuid(value: str, context: str) -> str:
    """Validate that value is a UUID string, return it unchanged."""
    if _UUID_RE.match(value):
        return value
    raise ValueError(f"Invalid UUID in {context}: {value!r}")


def _age_upsert_edge(c, src_id: str, src_type: str, dst_id: str, dst_type: str,
                     edge_type: str, props: dict | None = None) -> None:
    """Sync edge to AGE graph (called from _insert_edge).

    Note: AGE doesn't support parameterized cypher, so we string-interpolate.
    Safety: src_id/dst_id validated as UUIDs; edge_type is constrained by
    edge_type ENUM; src_type/dst_type validated via _age_label(); props values
    are escaped via _escape_cypher_string().
    """
    src_label = _age_label(src_type)
    dst_label = _age_label(dst_type)
    src_id_safe = _validate_uuid(src_id, 'src_id')
    dst_id_safe = _validate_uuid(dst_id, 'dst_id')
    set_clause = ''
    if props:
        clean = {
            k: _escape_cypher_string(str(v))
            for k, v in props.items()
            if v is not None
        }
        if clean:
            kvs = ', '.join(f"e.{k} = '{v}'" for k, v in clean.items())
            set_clause = f" SET {kvs}"
    cypher = (
        f"MERGE (s:{src_label} {{id: '{src_id_safe}'}}) "
        f"MERGE (d:{dst_label} {{id: '{dst_id_safe}'}}) "
        f"MERGE (s)-[e:{edge_type}]->(d){set_clause}"
    )
    c.execute(f"SELECT * FROM cypher('{AGE_GRAPH}', $$ {cypher} $$) AS (e agtype)")


def _insert_edge(c, edge: dict) -> dict | None:
    """Insert into edges table + sync to AGE graph (dual-write).

    Idempotent (F4.6.1): `uq_edges_dedupe` UNIQUE INDEX on (tenant_id, src_id,
    dst_id, type) + `ON CONFLICT DO NOTHING` makes re-emits a no-op in PG. AGE
    Cypher MERGE is natively idempotent. Returns the inserted row dict, or None
    when the edge already existed.

    `edge` keys: tenant_id, src_id, src_type, dst_id, dst_type, type,
                 confidence (opt), created_by (opt), resolved (opt).
    """
    cols = ['tenant_id', 'src_id', 'src_type', 'dst_id', 'dst_type', 'type',
            'confidence', 'created_by', 'resolved']
    vals = [edge.get(k) for k in cols]
    placeholders = ', '.join(['%s'] * len(cols))
    sql = (
        f'INSERT INTO edges ({", ".join(cols)}) VALUES ({placeholders}) '
        f'ON CONFLICT (tenant_id, src_id, dst_id, type) DO NOTHING RETURNING *'
    )
    res = c.execute(sql, vals).fetchone()

    _age_upsert_edge(
        c,
        edge['src_id'], edge['src_type'],
        edge['dst_id'], edge['dst_type'],
        edge['type'],
        props={
            'tenant_id': edge.get('tenant_id'),
            'created_by': edge.get('created_by'),
        },
    )
    return res
