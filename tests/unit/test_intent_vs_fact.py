# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F3.2 corpus builder: pages, arXiv feed, exclusions, stable checksums."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "lab" / "corpus" / "intent_vs_fact.py"
_spec = importlib.util.spec_from_file_location("intent_vs_fact", _PATH)
ivf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ivf)

WORDS = " ".join(["word"] * 60)


def _page(folder: Path, name: str, url: str, score: int, summary: str = "Streszczenie artykułu.") -> None:
    (folder / name).write_text(
        f"---\ntype: arxiv_paper\nurl: {url}\ncreated_at: '2026-08-12T21:36:45+00:00'\nrelevance_score: {score}\n---\n\n"
        f"# T\n\n## Streszczenie\n{summary}\n\n## Key findings\n- Ustalenie.\n")


def _feed(entries: list[tuple[str, str]]) -> bytes:
    items = "".join(
        f"<entry><id>http://arxiv.org/abs/{i}</id><title>T {i}</title><summary>{s}</summary>"
        f"<published>2026-08-01T00:00:00Z</published><updated>2026-08-02T00:00:00Z</updated></entry>"
        for i, s in entries)
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{items}</feed>'.encode()


def test_build_applies_exclusions_and_strata(tmp_path):
    pages = tmp_path / "papers"
    pages.mkdir()
    _page(pages, "a.md", "https://arxiv.org/abs/2608.00001v1", 9)
    _page(pages, "b.md", "https://arxiv.org/abs/2608.00002v1", 3)
    _page(pages, "b2.md", "https://arxiv.org/abs/2608.00002v2", 3)  # newer version of the same paper
    _page(pages, "c.md", "https://arxiv.org/abs/2608.00003v1", 6)
    _page(pages, "d.md", "https://arxiv.org/abs/2608.00004v1", 6)
    papers, excluded = ivf.read_pages(pages)
    assert sorted(papers) == ["2608.00001", "2608.00002", "2608.00003", "2608.00004"]
    assert papers["2608.00002"]["page"] == "b2.md"
    feed = _feed([("2608.00001v1", WORDS), ("2608.00002v2", "  " + WORDS + "\n  more  "),
                  ("2608.00003v1", "This paper has been withdrawn by the author.")])
    urls = []
    abstracts = ivf.fetch_abstracts(sorted(papers), get=lambda u: urls.append(u) or feed, pause=0)
    assert "max_results=4" in urls[0]
    corpus = ivf.build(papers, abstracts, "2026-09-28", excluded)
    assert [r["arxiv_id"] for r in corpus] == ["2608.00001", "2608.00002"]
    assert {r["stratum"] for r in corpus} == {"high", "low"}
    reasons = dict(excluded)
    assert reasons["2608.00003"] == "withdrawn" and reasons["2608.00004"].startswith("no abstract")
    assert reasons["b.md"].startswith("duplicate")
    # whitespace does not change the checksum
    assert corpus[1]["abstract_sha256"] == ivf.sha256(WORDS + " more")
    ivf.write(tmp_path / "out", corpus, excluded)
    lines = (tmp_path / "out" / "corpus.jsonl").read_text().splitlines()
    assert json.loads(lines[0])["summary_model"] is None
    assert (tmp_path / "out" / "manifest.csv").read_text().count("\n") == 3


def test_repository_allowlist_admits_arxiv():
    from exocortex.source_allowlist import Allowlist

    allow = Allowlist.load(Path(__file__).resolve().parents[2] / "lab" / "sources.yaml")
    assert allow.check("arxiv", "https://arxiv.org/abs/2608.11050v1")[0]
    assert allow.check_url("https://export.arxiv.org/api/query?id_list=2608.11050")[0]


def test_leave_out_list_is_honoured(tmp_path):
    pages = tmp_path / "papers"
    pages.mkdir()
    _page(pages, "a.md", "https://arxiv.org/abs/2608.00001v1", 9)
    papers, excluded = ivf.read_pages(pages)
    feed = _feed([("2608.00001v1", WORDS)])
    abstracts = ivf.fetch_abstracts(sorted(papers), get=lambda u: feed, pause=0)
    corpus = ivf.build(papers, abstracts, "2026-09-28", excluded, {"2608.00001": "held by the gate"})
    assert corpus == [] and ("(withheld)", "held by the gate") in excluded
    assert not any("2608.00001" in item for item, _ in excluded)


def test_loader_item_shape():
    spec = importlib.util.spec_from_file_location("load", _PATH.parent / "load.py")
    load = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(load)
    rec = {"arxiv_id": "2608.00001", "version": 2, "title": "T", "abstract": "A", "abstract_sha256": "x",
           "summary_sha256": "y", "summary_pl": "S", "findings_pl": "F", "published": "2026-08-01",
           "summary_date": "2026-08-12", "relevance": 9, "stratum": "high"}
    it = load.item(rec, "intent-vs-fact")
    assert it["source_type"] == "arxiv" and it["uri"] == "https://arxiv.org/abs/2608.00001v2"
    assert it["raw_payload"] == "A" and it["metadata"]["corpus"] == "intent-vs-fact"
