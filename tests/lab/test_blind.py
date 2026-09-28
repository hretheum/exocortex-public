# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Blind sample tool on the toy experiment (roadmap task F3.5)."""
from __future__ import annotations

import re
import uuid

import pytest

from exocortex.lab import blind
from exocortex.lab import experiments as ex
from tests.lab.conftest import needs_engine
from tests.lab.test_graph_and_toy import _docs

pytestmark = needs_engine


@pytest.fixture()
def toy_run(conn, tenant, tmp_path, monkeypatch):
    from exocortex.lab import toy
    from exocortex.lab.cli import _document_text, runners
    from exocortex.lab.docsync import sync_documents

    monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
    monkeypatch.setattr(toy, "SLUG", "toy-" + uuid.uuid4().hex[:8])
    folder = "b-" + uuid.uuid4().hex[:8]
    _docs(tmp_path, n=10, folder=folder)
    sync_documents(conn, tenant, tmp_path, base_uri=f"file:///vault/_source/dowody/{uuid.uuid4().hex[:8]}/")
    items = [i for i in toy.frame(conn, tenant) if f"/{folder}/" in i["item_id"]]
    ids = toy.setup(conn, tenant, tuning=8, control=4, items=items)
    run = ex.create_run(conn, ids["experiment"], "run-2026-09-30-1", ids["samples"]["tuning"], hypothesis_version=1)
    ex.enqueue(conn, run, list(ids["configs"].values()))
    ex.work(conn, runners(conn, tenant), owner="test", run_uuid=run)
    return ids, run, _document_text(conn, tenant, "toy", None)


def _tick(page: str, choose) -> str:
    """Tick boxes on a rendered page: choose(position) -> (verdicts, source mode)."""
    out, position = [], 0
    for line in page.splitlines():
        m = re.match(r"^## \S+ (\d+)$", line)
        if m:
            position = int(m.group(1))
        verdicts, mode = choose(position) if position else ((), None)
        for label in [blind.LABELS["pl"][v] for v in verdicts] + ([blind.LABELS["pl"][mode]] if mode else []):
            if line == f"- [ ] {label}":
                line = f"- [x] {label}"
        out.append(line)
    return "\n".join(out).replace("rating_complete: false", "rating_complete: true").replace('rater: ""', "rater: tester")


def test_page_hides_the_configuration_and_ratings_reach_the_table(conn, toy_run):
    ids, run, text_of = toy_run
    candidates = blind.units(conn, [run], text_of)
    assert len(candidates) == 16  # one sentence per document and configuration
    sample = blind.draw(conn, ids["experiment"], "blind-tuning", candidates, seed=5, repeats=2)
    page = blind.render(conn, sample, "pl", "toy", "../../../en/experiments/toy/blind-tuning.md")
    assert "publish: false" in page and "first-sentence" not in page and "longest-sentence" not in page
    assert page.count("## Pozycja ") == 18  # 16 units and 2 repeats
    rated = _tick(page, lambda n: (("correct",), "fact") if n % 3 else (("mode_swap",), "hypothesis"))
    front, items = blind.read_page(rated, "pl")
    assert front["rating_complete"] is True and len(items) == 18
    result = blind.store(conn, sample, "tester", items)
    assert result["stored"] == 18 and not result["without_verdict"]
    s = blind.summary(conn, sample, "tester")
    assert s["items"] == 16 and s["repeats"] == 2
    total = sum(c["swap_rate"]["n"] for c in s["per_config"].values())
    assert total == 16
    for c in s["per_config"].values():
        v = c["swap_rate"]
        assert v["ci_low"] <= v["value"] <= v["ci_high"]
    assert "longest-sentence - first-sentence/swap_rate" in s["differences"]


def test_rated_page_names_configurations_after_rating(conn, toy_run):
    ids, run, text_of = toy_run
    sample = blind.draw(conn, ids["experiment"], "blind-x", blind.units(conn, [run], text_of), seed=1)
    page = blind.render(conn, sample, "pl", "toy", "x.md")
    _, items = blind.read_page(_tick(page, lambda n: (("correct",), "fact")), "pl")
    blind.store(conn, sample, "tester", items)
    out = blind.rated_page(conn, sample, "tester", "en", "toy", "../x.md")
    assert "first-sentence" in out and "longest-sentence" in out and "| correct |" in out


def test_unticked_and_contradictory_items_are_reported(conn, toy_run):
    ids, run, text_of = toy_run
    sample = blind.draw(conn, ids["experiment"], "blind-y", blind.units(conn, [run], text_of), seed=2, size=6)
    page = blind.render(conn, sample, "pl", "toy", "x.md")
    rated = _tick(page, lambda n: ((), None) if n == 1 else (("correct", "mode_swap"), None) if n == 2
                  else (("other_error",), "plan"))
    _, items = blind.read_page(rated, "pl")
    result = blind.store(conn, sample, "tester", items)
    assert result["without_verdict"] == [1] and result["correct_with_errors"] == [2] and result["stored"] == 4


def test_effective_swap_respects_a_non_fact_mode_label():
    assert blind.effective_swap({"labels": ["mode_swap"], "mode_label": None})
    assert blind.effective_swap({"labels": ["mode_swap"], "mode_label": "fact"})
    assert not blind.effective_swap({"labels": ["mode_swap"], "mode_label": "hypothesis"})
    assert not blind.effective_swap({"labels": ["correct"], "mode_label": "fact"})


def test_context_is_found_around_the_quote():
    doc = "Alpha beta gamma. " * 30 + "The key sentence is here. " + "Delta epsilon. " * 30
    ctx = blind.context_around(doc, "key sentence is here", width=20)
    assert "key sentence is here" in ctx and ctx.startswith("…") and ctx.endswith("…")
