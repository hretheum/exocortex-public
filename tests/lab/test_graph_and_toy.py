# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Lab graph nodes (documents, corpus) and the toy experiment end to end.

These tests need the engine schema (raw_sources, thoughts, edges): they run
in CI after `exocortex migrate up` on the project's database image.
"""
from __future__ import annotations

import hashlib
import json
import uuid

import pytest

from exocortex.lab import experiments as ex
from tests.lab.conftest import needs_engine

pytestmark = needs_engine


def _write(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _docs(root, n=10, folder="notes"):
    for lang in ("pl", "en"):
        for i in range(n):
            _write(root, f"{lang}/{folder}/n{i:02d}.md",
                   f"---\nid: n{i}\nlang: {lang}\n---\n\n# Note {i}\n\n" + "Sentence number one is here. " * (i + 1)
                   + ("A much longer sentence that goes on and on, well past the limit of one hundred and twenty "
                      "characters, so the longest rule picks it. " if i % 2 else ""))


def test_documents_become_sources_and_nodes(conn, tenant, tmp_path, monkeypatch):
    from exocortex.lab.docsync import current_documents, sync_documents

    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
    base = f"file:///vault/_source/dowody/{uuid.uuid4().hex[:8]}/"
    folder = "d-" + uuid.uuid4().hex[:8]
    _docs(tmp_path, n=2, folder=folder)
    first = sync_documents(conn, tenant, tmp_path, base_uri=base)
    assert first == {"documents": 4, "changed": 4, "removed": 0}
    assert sync_documents(conn, tenant, tmp_path, base_uri=base)["changed"] == 0
    (tmp_path / f"en/{folder}/n01.md").unlink()
    assert sync_documents(conn, tenant, tmp_path, base_uri=base)["removed"] == 1
    docs = {d["rel"] for d in current_documents(conn, tenant) if folder in d["rel"]}
    assert docs == {f"pl/{folder}/n00.md", f"pl/{folder}/n01.md", f"en/{folder}/n00.md"}
    edges = conn.execute("""SELECT count(*) AS n FROM edges e JOIN thoughts t ON t.id = e.src_id
                            WHERE t.thought_type = 'dowody_document' AND e.type = 'acquired_from'""").fetchone()
    assert edges["n"] >= 3


def test_documents_outside_the_allowlist_are_refused(conn, tenant, tmp_path, monkeypatch):
    from exocortex.lab.docsync import sync_documents
    from exocortex.source_allowlist import SourceNotAllowed

    allow = tmp_path / "sources.yaml"
    allow.write_text("sources:\n  - {id: x, source_type: arxiv, domains: [arxiv.org], basis: b, added_by: a, reason: r}\n")
    monkeypatch.setenv("EXOCORTEX_SOURCE_ALLOWLIST", str(allow))
    _docs(tmp_path / "docs", n=1)
    with pytest.raises(SourceNotAllowed):
        sync_documents(conn, tenant, tmp_path / "docs", base_uri="file:///vault/_source/dowody/x/")


def _sha(text):
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


def test_corpus_papers_become_two_linked_nodes(conn, tenant, monkeypatch):
    from exocortex.lab.corpus_graph import sync_corpus

    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
    corpus = "c-" + uuid.uuid4().hex[:8]
    for i, bad in ((1, False), (2, True)):
        abstract, summary, findings = f"We measure thing {i}. " * 20, f"Mierzymy rzecz {i}.", "- ustalenie"
        meta = {"corpus": corpus, "arxiv_id": f"2609.0000{i}", "version": 1, "raw_payload": abstract,
                "abstract_sha256": _sha(abstract) if not bad else "0" * 64,
                "summary_pl": summary, "findings_pl": findings, "summary_sha256": _sha(summary + "\n" + findings)}
        conn.execute("""INSERT INTO raw_sources (tenant_id, uri, title, source_type, metadata)
                        VALUES (%s, %s, %s, 'arxiv', %s::jsonb)""",
                     (tenant, f"https://arxiv.org/abs/2609.0000{i}v1-{corpus}", f"Paper {i}", json.dumps(meta)))
    counts = sync_corpus(conn, tenant, corpus, embed=lambda texts: [[0.1] * 1024 for _ in texts])
    assert counts["papers"] == 2 and counts["checksum_problems"] == 1 and counts["created"] == 2
    assert counts["embedded"] == 2
    again = sync_corpus(conn, tenant, corpus)
    assert again["created"] == 0 and again["updated"] == 2
    rows = conn.execute("""SELECT thought_type, metadata->>'lang' AS lang FROM thoughts
                           WHERE metadata->>'corpus' = %s ORDER BY thought_type""", (corpus,)).fetchall()
    assert [(r["thought_type"], r["lang"]) for r in rows] == [("corpus_abstract", "en"), ("corpus_summary", "pl")]
    derived = conn.execute("""SELECT count(*) AS n FROM edges e JOIN thoughts s ON s.id = e.src_id
                              WHERE s.metadata->>'corpus' = %s AND e.type = 'derived_from'""", (corpus,)).fetchone()
    assert derived["n"] == 1


def test_toy_experiment_end_to_end(conn, tenant, tmp_path, monkeypatch):
    from exocortex.lab import toy
    from exocortex.lab.cli import runners
    from exocortex.lab.docsync import sync_documents

    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
    monkeypatch.setattr(toy, "SLUG", "toy-" + uuid.uuid4().hex[:8])
    folder = "t-" + uuid.uuid4().hex[:8]
    _docs(tmp_path, n=12, folder=folder)
    sync_documents(conn, tenant, tmp_path, base_uri=f"file:///vault/_source/dowody/{uuid.uuid4().hex[:8]}/")
    items = [i for i in toy.frame(conn, tenant) if f"/{folder}/" in i["item_id"]]
    ids = toy.setup(conn, tenant, tuning=8, control=4, items=items)
    run = ex.create_run(conn, ids["experiment"], "run-2026-09-29-1", ids["samples"]["tuning"], hypothesis_version=1)
    assert ex.enqueue(conn, run, list(ids["configs"].values())) == 16
    summary = ex.work(conn, runners(conn, tenant), owner="test", run_uuid=run)
    assert summary.done == 16 and summary.switches() == 1
    result_ids = toy.compute_metrics(conn, run)
    assert len(result_ids) == 5
    diff = conn.execute("SELECT value, ci_low, ci_high FROM exp_metrics WHERE result_id = %s",
                        (result_ids[-1],)).fetchone()
    assert diff["ci_low"] <= diff["value"] <= diff["ci_high"]
    ex.create_run(conn, ids["experiment"], "run-2026-09-29-2", ids["samples"]["control"], hypothesis_version=1)
    with pytest.raises(ex.ControlSampleAlreadyOpened):
        ex.create_run(conn, ids["experiment"], "run-2026-09-29-3", ids["samples"]["control"], hypothesis_version=1)
