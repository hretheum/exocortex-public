# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Opportunity radar (roadmap task F5.1)."""
from __future__ import annotations

import datetime as dt
import json
import uuid

from exocortex.lab import radar, signals
from exocortex.lab.llm import Call
from tests.lab.conftest import needs_engine

pytestmark = needs_engine


class FakeLLM:
    url = "fake"

    def embed(self, model, texts):
        return [[0.6, 0.8] if " not " in t else [1.0, 0.0] if "retrieval" in t else [0.0, 1.0] for t in texts]

    def structured(self, **kw):
        return Call(model=kw["model"], output={"contradict": "not" in kw["user"]})


def test_week_boundaries():
    assert radar.week_of(dt.date(2026, 9, 29)) == ("2026-W40", dt.date(2026, 9, 28), dt.date(2026, 10, 4))


def test_topics_group_close_papers():
    papers = [{"vec": [1.0, 0.0], "meta": {}}, {"vec": [0.99, 0.1], "meta": {}}, {"vec": [0.98, 0.15], "meta": {}},
              {"vec": [0.0, 1.0], "meta": {}}]
    groups = radar.topics(papers)
    assert len(groups) == 1 and len(groups[0]) == 3


def test_a_week_of_signals_becomes_a_page_pair(conn, tmp_path, monkeypatch):
    from tools.paritycheck.core import check

    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
    tenant = str(uuid.uuid4())
    may = {"claim": "Graph retrieval may improve recall.", "quote": "q", "mode": "hypothesis"}
    does_not = {"claim": "Graph retrieval does not improve recall.", "quote": "q", "mode": "hypothesis"}
    fact = {"claim": "We measured 3 benchmarks.", "quote": "q", "mode": "fact"}
    per_paper = [{"claims": [may, fact]}, {"claims": [does_not]}, {"claims": [dict(may)]}]  # paper 2 repeats paper 0
    items = [signals.Item("arxiv", "arxiv-new", f"https://arxiv.org/abs/2609.9{i}v1", f"Paper {i}", f"Paper {i}",
                          "2026-09-29", {"arxiv_id": f"2609.9{i}", "categories": ["cs.IR"]}) for i in range(3)]
    items.append(signals.Item("models", "hf-model", "https://huggingface.co/org/m", "org/m", "org/m", "2026-09-30",
                              {"license": "mit"}))
    signals.ingest(conn, tenant, items, embed=lambda texts: [[1.0] + [0.0] * 1023] * len(texts))  # bge-m3 size
    for it, meta in zip(items[:3], per_paper):
        conn.execute("UPDATE thoughts SET metadata = metadata || %s::jsonb WHERE metadata->>'uri' = %s",
                     (json.dumps({"radar": meta}), it.uri))
    result = radar.run(conn, tenant, FakeLLM(), tmp_path, day=dt.date(2026, 9, 30), extract=False)
    assert result["week"] == "2026-W40" and result["papers"] == 3 and result["candidates"] == 2
    assert result["contradictions"] == 1 and result["topics"] == 1 and result["new_items"] == 1
    pl = (tmp_path / "pl" / "generated" / "radar" / "2026-W40.md").read_text()
    assert "Graph retrieval may improve recall." in pl and "hipoteza" in pl and "We measured" not in pl
    assert "https://huggingface.co/org/m" in pl and "Za mało tygodni wstecz" in pl
    assert (tmp_path / "en" / "generated" / "radar.md").exists()
    res = check(tmp_path)
    assert res.ok, [str(p) for p in res.problems]


def test_corpus_papers_are_never_processed(conn, tmp_path, monkeypatch):
    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
    tenant = str(uuid.uuid4())
    reserved = min(radar.corpus_ids())
    items = [signals.Item("arxiv", "arxiv-new", f"https://arxiv.org/abs/{reserved}v9", "Corpus paper", "text", "2026-09-29",
                          {"arxiv_id": reserved, "categories": ["cs.CL"]})]
    signals.ingest(conn, tenant, items)

    class Boom(FakeLLM):
        def structured(self, **kw):
            raise AssertionError("the extractor must not run on a corpus paper")

    result = radar.run(conn, tenant, Boom(), tmp_path, day=dt.date(2026, 9, 30))
    assert result["papers"] == 0 and result["left_out_corpus_papers"] == 1


def test_items_with_personal_data_are_left_out():
    claim = {"mode": "hypothesis", "uri": "https://arxiv.org/abs/1", "title": "Paper"}
    new = {"channel": "open-data", "uri": "https://dane.gov.pl/pl/dataset/1", "license": "CC BY 4.0"}
    found = {"claims": [{**claim, "claim": "A fine claim."},
                        {**claim, "claim": "Contact us at someone@example.com for data."}],
             "contradictions": [], "topics": [],
             "new": [{"meta": {**new, "title": "Open budget 2026"}},
                     {"meta": {**new, "title": "Grants of the Jan Kowalski foundation"}}]}
    assert radar.without_personal_data(found) == 2
    assert [c["claim"] for c in found["claims"]] == ["A fine claim."]
    assert [p["meta"]["title"] for p in found["new"]] == ["Open budget 2026"]
    assert "Pominięto pozycje" in radar.page("2026-W40", "pl", {**found, "omitted": 2, "rises": [],
                                                                "has_baseline": False})
