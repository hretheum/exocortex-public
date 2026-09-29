# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The public graph package (roadmap task F8.2) built from a real lab database.

Needs the engine schema (raw_sources, thoughts, edges): runs in CI after
`exocortex migrate up` on the project's database image.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from exocortex.lab import experiments as ex
from tests.lab.conftest import URL, needs_engine

pytestmark = needs_engine

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("graph_package_lab", ROOT / "lab" / "graph_package.py")
gp = importlib.util.module_from_spec(_spec)
sys.modules["graph_package_lab"] = gp
_spec.loader.exec_module(gp)

ABSTRACTS = [
    "We show that retrieval “helps” — sometimes. Large models still fail on long inputs, as our tests show.",
    "A second paper measures latency. Caching halves the median latency of the service in every setting.",
]


def _sha(text: str) -> str:
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


def _embed(texts):
    """Deterministic stand-in for the embedding model: 1024 numbers from the text's hash."""
    out = []
    for t in texts:
        h = hashlib.sha256(t.encode()).digest()
        out.append([(h[i % 32] - 128) / 128.0 + i / 100000.0 for i in range(1024)])
    return out


def _sources(tmp_path: Path, basis: bool = True) -> Path:
    red = "\n    redistribution: {corpus_abstract: 'CC0 1.0 (test)'}" if basis else ""
    path = tmp_path / "sources.yaml"
    path.write_text("sources:\n  - id: arxiv-abstracts\n    source_type: arxiv\n    domains: [arxiv.org]\n"
                    "    basis: 'CC0 1.0 metadata'\n    added_by: owner\n    reason: test" + red + "\n",
                    encoding="utf-8")
    return path


def _corpus(conn, tenant, tmp_path: Path) -> tuple[str, Path, list[dict]]:
    """Two papers as lab graph nodes (with embeddings) and the same corpus as the repository ships it."""
    from exocortex.lab.corpus_graph import sync_corpus

    corpus = "c-" + uuid.uuid4().hex[:8]
    folder = tmp_path / "corpora" / corpus
    folder.mkdir(parents=True)
    papers = []
    for i, abstract in enumerate(ABSTRACTS, start=1):
        summary, findings = f"Streszczenie pracy {i}.", "- ustalenie"
        arxiv_id = f"2609.{uuid.uuid4().int % 90000 + 10000}"
        meta = {"corpus": corpus, "arxiv_id": arxiv_id, "version": 1, "raw_payload": abstract,
                "abstract_sha256": _sha(abstract), "summary_pl": summary, "findings_pl": findings,
                "summary_sha256": _sha(summary + "\n" + findings), "title": f"Paper {i}",
                "uri": f"https://arxiv.org/abs/{arxiv_id}v1"}
        conn.execute("""INSERT INTO raw_sources (tenant_id, uri, title, source_type, metadata)
                        VALUES (%s, %s, %s, 'arxiv', %s::jsonb)""",
                     (tenant, meta["uri"] + "#" + corpus, f"Paper {i}", json.dumps(meta)))
        papers.append(meta)
    with (folder / "corpus.jsonl").open("w", encoding="utf-8") as fh:
        for m in papers:
            fh.write(json.dumps({"arxiv_id": m["arxiv_id"], "version": 1, "abstract": m["raw_payload"],
                                 "summary_pl": m["summary_pl"], "findings_pl": m["findings_pl"]}) + "\n")
    (folder / "manifest.csv").write_text("arxiv_id\n" + "".join(m["arxiv_id"] + "\n" for m in papers))
    counts = sync_corpus(conn, tenant, corpus, embed=_embed)
    assert counts["created"] == 4 and counts["embedded"] == 4
    return corpus, tmp_path / "corpora", papers


def _claims_run(conn, tenant, slug: str, corpus: str, papers: list[dict]) -> None:
    """A finished claims experiment with one configuration per text (abstract, summary)."""
    from tools.leakgate.selftest import synthetic_pii

    eid = ex.ensure_experiment(conn, slug, "claims", "graph package test", params={"corpus": corpus})
    configs = [ex.ensure_config(conn, eid, "abs", model="m1", provider="local", variant="baseline",
                                params={"text": "abstract"}),
               ex.ensure_config(conn, eid, "sum", model="m1", provider="local", variant="mode",
                                params={"text": "summary"})]
    items = [{"item_id": m["arxiv_id"], "stratum": "high", "content_sha256": _sha(m["arxiv_id"]),
              "payload": {"abstract_sha256": m["abstract_sha256"], "summary_sha256": m["summary_sha256"]}}
             for m in papers]
    sample = ex.create_sample(conn, eid, "tuning", "tuning", 1, "test", items)
    run = ex.create_run(conn, eid, "run-2026-09-29-1", sample)
    ex.enqueue(conn, run, configs)
    email = synthetic_pii(random.Random(3))["email"]

    def runner(job, item):
        text = job["config"]["params"]["text"]
        if text == "summary":
            claims = [{"i": 1, "quote": "Streszczenie pracy", "claim": "Coś.", "grounded": True, "usable": True}]
        elif item["item_id"] == papers[0]["arxiv_id"]:
            claims = [
                {"i": 1, "quote": 'retrieval "helps" - sometimes', "claim": "Retrieval sometimes helps.",
                 "grounded": True, "proposition": True, "redundant": False, "usable": True},
                {"i": 2, "quote": "models still fail on long inputs", "claim": "Large models fail on long inputs.",
                 "grounded": True, "proposition": True, "redundant": False, "usable": True},
                {"i": 3, "quote": "a sentence the paper does not have", "claim": "Invented.", "grounded": False},
                {"i": 4, "quote": "as our tests show", "claim": f"Tests show it, {email}.", "grounded": True},
            ]
        else:
            claims = [{"i": 1, "quote": "Caching halves the median latency", "claim": "Caching halves latency.",
                       "grounded": True, "proposition": True, "redundant": False, "usable": True}]
        return {"ok": True, "output": {"claims": claims}, "model": "m1", "provider": "local"}

    ex.work(conn, {"claims": runner}, owner="test", run_uuid=run)
    assert ex.finish_run(conn, run) == {"done": 4}


def test_the_package_comes_from_the_graph_and_two_builds_are_identical(conn, tenant, tmp_path, slug):
    corpus, corpora, papers = _corpus(conn, tenant, tmp_path)
    _claims_run(conn, tenant, slug, corpus, papers)
    sources = _sources(tmp_path)
    first, report = gp.collect(conn, tenant, [corpus], sources)
    second, _ = gp.collect(conn, tenant, [corpus], sources)
    files = gp.render(first)
    assert files == gp.render(second)

    assert [d["kind"] for d in first.documents] == ["abstract", "abstract"]  # summaries have no basis recorded
    assert len(first.vectors) == 2 and first.dimensions == 1024
    assert sorted(c["text"] for c in first.claims) == ["Caching halves latency.", "Large models fail on long inputs.",
                                                       "Retrieval sometimes helps."]
    quote = next(q for q in first.quotes if q["claim_id"].endswith("/1") and papers[0]["arxiv_id"] in q["claim_id"])
    assert quote["text"] == "retrieval “helps” — sometimes"
    assert ABSTRACTS[0][quote["start"]:quote["end"]] == quote["text"]
    assert len(first.edges) == 3 and {e["type"] for e in first.edges} == {"derived_from"}
    left = report["left_out"]
    assert left[f"summary of corpus {corpus}: no basis for redistribution of corpus_summary under "
                "arxiv-abstracts in lab/sources.yaml"] == 2
    assert report["claims_left_out"] == {"their document is not in the package": 2,
                                         "personal data the gate would hold": 1}

    placed = gp.place(files, tmp_path / "out", tmp_path / "staging")
    assert gp.verify(tmp_path / "out" / placed["version"], corpora) == []


def test_a_source_without_a_recorded_basis_stays_out(conn, tenant, tmp_path):
    corpus, _, _ = _corpus(conn, tenant, tmp_path)
    pkg, report = gp.collect(conn, tenant, [corpus], _sources(tmp_path, basis=False))
    assert pkg.documents == [] and pkg.vectors == []
    assert report["left_out"][f"abstract of corpus {corpus}: no basis for redistribution of corpus_abstract "
                              "under arxiv-abstracts in lab/sources.yaml"] == 2


def test_the_build_command_writes_the_package_and_a_rebuild_keeps_it(conn, tenant, tmp_path, slug):
    corpus, corpora, papers = _corpus(conn, tenant, tmp_path)
    _claims_run(conn, tenant, slug, corpus, papers)
    env = {**os.environ, "DATABASE_URL": URL, "TENANT_ID": tenant}
    cmd = [sys.executable, str(ROOT / "lab" / "graph_package.py"), "build", "--out", str(tmp_path / "out"),
           "--staging", str(tmp_path / "staging"), "--corpora", str(corpora), "--sources", str(_sources(tmp_path))]
    runs = [subprocess.run(cmd, env=env, capture_output=True, text=True) for _ in range(2)]
    assert [r.returncode for r in runs] == [0, 0], runs[0].stdout + runs[0].stderr
    first, second = (json.loads(r.stdout) for r in runs)
    assert first["package_sha256"] == second["package_sha256"] and second["unchanged"] is True
    assert first["counts"] == {"documents": 2, "claims": 3, "quotes": 3, "edges": 3, "vectors": 2}
    check = subprocess.run([sys.executable, str(ROOT / "lab" / "graph_package.py"), "verify",
                            str(tmp_path / "out" / first["version"]), "--corpora", str(corpora)],
                           capture_output=True, text=True)
    assert check.returncode == 0, check.stdout


def test_the_build_command_refuses_an_empty_package(conn, tenant, tmp_path):
    corpus, corpora, _ = _corpus(conn, tenant, tmp_path)
    env = {**os.environ, "DATABASE_URL": URL, "TENANT_ID": tenant}
    proc = subprocess.run([sys.executable, str(ROOT / "lab" / "graph_package.py"), "build", "--out",
                           str(tmp_path / "out"), "--corpora", str(corpora),
                           "--sources", str(_sources(tmp_path, basis=False))],
                          env=env, capture_output=True, text=True)
    assert proc.returncode == 1 and "nothing to publish" in proc.stdout
    assert not (tmp_path / "out").exists()


@pytest.fixture(autouse=True)
def _no_allowlist(monkeypatch):
    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
