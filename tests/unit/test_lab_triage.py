# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""First scoring of radar candidates by three model families (roadmap task F5.3)."""
from __future__ import annotations

from exocortex.lab import triage
from exocortex.lab.llm import Call


class FakeLLM:
    def __init__(self):
        self.order = []

    def structured(self, **kw):
        self.order.append(kw["model"])
        base = {d: 4 for d, _ in triage.DIMENSIONS}
        if kw["model"].startswith("gemma"):
            base["value"] = 2  # two points below the others: a spread worth a discussion
        if kw["model"].startswith("gpt-oss"):
            if "broken" in kw["user"]:
                return Call(model=kw["model"], error="no JSON object in the reply")
            assert kw["mode"] == "tools"  # this model supports native tool calls only
        knock = {k: True for k in triage.KNOCKOUTS}
        if "illegal" in kw["user"]:
            knock["legal"] = False
        return Call(model=kw["model"], output={"knockouts": knock, "scores": base, "reason": "Short reason."})


def test_three_families_score_each_candidate_and_disagreements_are_flagged():
    llm = FakeLLM()
    cands = [{"claim": "Graph expansion may help recall.", "uri": "https://arxiv.org/abs/1", "title": "P1"},
             {"claim": "An illegal idea.", "uri": "https://arxiv.org/abs/2", "title": "P2"},
             {"claim": "A broken answer.", "uri": "https://arxiv.org/abs/3", "title": "P3"}]
    out = triage.assess(cands, llm)
    assert llm.order == ["qwen3.6-35b-a3b"] * 3 + ["gemma-4-26b-a4b"] * 3 + ["gpt-oss-20b"] * 3  # grouped by model
    assert out[0]["discuss"] == ["value"] and out[0]["knocked_out_by"] == [] and out[0]["complete"]
    assert out[1]["knocked_out_by"] == ["legal"]
    assert not out[2]["complete"] and "error" in out[2]["answers"]["gpt-oss-20b"]
    assert out[0]["weighted"]["qwen3.6-35b-a3b"] == 4.0 and out[0]["weighted"]["gemma-4-26b-a4b"] == 3.5


def test_the_page_pairs_pass_the_parity_check(tmp_path):
    from tools.paritycheck.core import check

    out = triage.assess([{"claim": "Graph expansion may help recall.", "uri": "https://arxiv.org/abs/1", "title": "P"}],
                        FakeLLM())
    for lang in ("pl", "en"):
        path = tmp_path / lang / "generated" / "triage" / "2026-W40.md"
        path.parent.mkdir(parents=True)
        path.write_text(triage.page("2026-W40", lang, out))
    assert check(tmp_path).ok
    assert "G0" in (tmp_path / "pl" / "generated" / "triage" / "2026-W40.md").read_text()


def test_weights_sum_to_one_hundred():
    assert sum(w for _, w in triage.DIMENSIONS) == 100
