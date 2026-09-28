# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Corpus documents as nodes of the lab graph (roadmap task F3.2).

Every paper of a corpus captured into the lab (``raw_sources`` of type
``arxiv``, loaded by lab/corpus/load.py) gets two nodes:

- ``corpus_abstract``: the abstract from arXiv, in English,
  ``acquired_from`` the source;
- ``corpus_summary``: the engine's Polish summary with its key findings,
  ``acquired_from`` the source and ``derived_from`` the abstract.

Both carry the corpus checksums, and the job checks them against the text
it writes, so every node can be matched with ``manifest.csv`` in the
repository. Embeddings (bge-m3 through the lab gateway) are optional.

No claims are extracted here. Claims are measurements of the first
experiment and appear only in its runs, after the hypothesis card is frozen
(F3.4).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from exocortex.lab.db import insert_edge, upsert_thought

Embed = Callable[[list[str]], list[list[float]]]


def normalise(text: str) -> str:
    return " ".join(text.split())


def sha256(text: str) -> str:
    """Same checksum as lab/corpus/intent_vs_fact.py: over whitespace-normalised text."""
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def nodes_for(source: dict) -> tuple[dict, dict, list[str]]:
    """(abstract node, summary node, problems) for one captured paper."""
    meta = source.get("metadata") or {}
    abstract = normalise(meta.get("raw_payload") or "")
    summary_pl = normalise(meta.get("summary_pl") or "")
    findings = (meta.get("findings_pl") or "").strip()
    problems = []
    if sha256(abstract) != meta.get("abstract_sha256"):
        problems.append("abstract checksum")
    if sha256(summary_pl + "\n" + findings) != meta.get("summary_sha256"):
        problems.append("summary checksum")
    common = {"domain": "lab", "corpus": meta.get("corpus"), "arxiv_id": meta.get("arxiv_id"),
              "version": meta.get("version"), "stratum": meta.get("stratum"), "relevance": meta.get("relevance"),
              "title": source.get("title"), "uri": source.get("uri")}
    abstract_node = {"body": abstract, "metadata": {**common, "lang": "en", "text": "abstract",
                                                   "sha256": meta.get("abstract_sha256")}}
    summary_body = summary_pl + ("\n\n" + findings if findings else "")
    summary_node = {"body": summary_body, "metadata": {**common, "lang": "pl", "text": "summary",
                                                      "sha256": meta.get("summary_sha256"),
                                                      "summary_date": meta.get("summary_date")}}
    return abstract_node, summary_node, problems


def sync_corpus(conn, tenant: str, corpus: str, embed: Embed | None = None, batch: int = 64) -> dict:
    """Create or update the nodes of every paper in ``corpus``; returns counts."""
    sources = conn.execute(
        """SELECT id, uri, title, metadata FROM raw_sources
           WHERE tenant_id = %s AND source_type = 'arxiv' AND deleted_at IS NULL
             AND metadata->>'corpus' = %s
           ORDER BY metadata->>'arxiv_id'""",
        (tenant, corpus),
    ).fetchall()
    counts = {"papers": len(sources), "created": 0, "updated": 0, "checksum_problems": 0, "embedded": 0}
    pending: list[tuple[str, str]] = []  # (thought id, body) still without an embedding
    for src in sources:
        sid = str(src["id"])
        abstract, summary, problems = nodes_for(src)
        if problems:
            counts["checksum_problems"] += 1
            continue  # a node must match the published manifest; report instead of writing
        aid, a_new = upsert_thought(conn, tenant, source_id=sid, thought_type="corpus_abstract",
                                    body=abstract["body"], metadata=abstract["metadata"])
        mid, m_new = upsert_thought(conn, tenant, source_id=sid, thought_type="corpus_summary",
                                    body=summary["body"], metadata=summary["metadata"])
        counts["created"] += a_new + m_new
        counts["updated"] += (not a_new) + (not m_new)
        insert_edge(conn, tenant, aid, "thought", sid, "raw_source", "acquired_from")
        insert_edge(conn, tenant, mid, "thought", sid, "raw_source", "acquired_from")
        insert_edge(conn, tenant, mid, "thought", aid, "thought", "derived_from")
    if embed is not None:
        rows = conn.execute(
            """SELECT id, body FROM thoughts WHERE tenant_id = %s AND embedding IS NULL
                 AND thought_type IN ('corpus_abstract', 'corpus_summary') AND metadata->>'corpus' = %s
               ORDER BY id""",
            (tenant, corpus),
        ).fetchall()
        pending = [(str(r["id"]), r["body"]) for r in rows]
        for i in range(0, len(pending), batch):
            chunk = pending[i:i + batch]
            vectors = embed([body for _, body in chunk])
            for (tid, _), vec in zip(chunk, vectors):
                conn.execute("UPDATE thoughts SET embedding = %s WHERE id = %s",
                             ("[" + ",".join(repr(float(x)) for x in vec) + "]", tid))
            counts["embedded"] += len(chunk)
    return counts
