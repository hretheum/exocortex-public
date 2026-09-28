# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The lab's own documents as sources and nodes of its graph.

Every Markdown file of the published documents folder (mounted read-only
at /vault/_source/dowody) is captured as a ``vault-note`` source, through
the same allowlist check as the Capture API, and gets one node
(``dowody_document``) with its header as metadata. Hypothesis cards, gate
decisions and roadmap pages are built from these nodes. A file that
disappeared from the folder marks its source deleted.
"""

from __future__ import annotations

from pathlib import Path

from exocortex.lab.db import capture_source, insert_edge, upsert_thought
from exocortex.lab.docs import Doc, iter_docs

BASE_URI = "file:///vault/_source/dowody/"


def kind_of(doc: Doc) -> str:
    t = doc.front.get("type")
    if isinstance(t, str):
        return t
    parts = doc.key.split("/")
    if parts[0] == "roadmap" and len(parts) == 3:
        return "roadmap_task"
    if parts[0] == "roadmap" and len(parts) == 2:
        return "roadmap_phase"
    if parts[0] == "templates":
        return "template"
    return "document"


def sync_documents(conn, tenant: str, root: Path, base_uri: str = BASE_URI) -> dict:
    docs = iter_docs(root)
    counts = {"documents": len(docs), "changed": 0, "removed": 0}
    seen = set()
    for doc in docs:
        uri = base_uri + doc.rel
        seen.add(uri)
        meta = {"rel": doc.rel, "lang": doc.lang, "key": doc.key, "kind": kind_of(doc), "sha256": doc.sha256,
                "front": doc.front}
        sid, changed = capture_source(conn, tenant, source_type="vault-note", uri=uri, title=doc.title,
                                      metadata={**meta, "raw_payload": doc.text})
        tid, _ = upsert_thought(conn, tenant, source_id=sid, thought_type="dowody_document", body=doc.text,
                                metadata={**meta, "domain": "lab", "title": doc.title})
        insert_edge(conn, tenant, tid, "thought", sid, "raw_source", "acquired_from")
        counts["changed"] += changed
    stale = conn.execute(
        """UPDATE raw_sources SET deleted_at = NOW()
           WHERE tenant_id = %s AND source_type = 'vault-note' AND uri LIKE %s AND deleted_at IS NULL
             AND NOT (uri = ANY(%s))
           RETURNING id""",
        (tenant, base_uri + "%", sorted(seen)),
    ).fetchall()
    counts["removed"] = len(stale)
    return counts


def current_documents(conn, tenant: str) -> list[dict]:
    """Nodes of documents whose source is not deleted: rel, lang, key, kind, front, body."""
    rows = conn.execute(
        """SELECT t.id, t.body, t.metadata FROM thoughts t JOIN raw_sources s ON s.id = t.source_id
           WHERE t.tenant_id = %s AND t.thought_type = 'dowody_document' AND s.deleted_at IS NULL
           ORDER BY t.metadata->>'rel'""",
        (tenant,),
    ).fetchall()
    return [{"id": str(r["id"]), "body": r["body"], **r["metadata"]} for r in rows]
