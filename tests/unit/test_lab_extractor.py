# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Claim extractor of the lab: quotes, the claim judge, duplicates (roadmap task F3.3)."""
from __future__ import annotations

import json

from exocortex.lab import extractor as x
from exocortex.lab.llm import Call

DOC = ("We propose SPARROW, a retrieval method for long documents. On three benchmarks it improves "
       "recall by 12 points over BM25. We expect that the approach will also help “multilingual” search, "
       "which we plan to test next.")


class FakeLLM:
    """Scripted replies: the extraction call first, then the judge."""

    url = "fake"

    def __init__(self, extraction: dict | None, verdicts: dict | None = None, error: str | None = None):
        self.replies = [extraction, verdicts]
        self.error = error
        self.calls: list[dict] = []

    def structured(self, **kw) -> Call:
        self.calls.append(kw)
        out = self.replies[len(self.calls) - 1] if len(self.calls) <= 2 else None
        err = self.error if len(self.calls) == 1 else None
        return Call(model=kw["model"], output=None if err else out, error=err or (None if out is not None else "no reply"),
                    prompt_tokens=100, completion_tokens=50, latency_ms=10)


def _claims(*rows, mode=False):
    out = []
    for quote, claim, m in rows:
        c = {"quote": quote, "claim": claim}
        if mode:
            c = {"quote": quote, "mode": m, "claim": claim}
        out.append(c)
    return {"claims": out}


def test_quotes_match_after_normalisation_only():
    assert x.grounded("improves recall by 12 points", DOC) == (True, None)
    assert x.grounded("IMPROVES   recall\nby 12 points", DOC) == (True, None)
    assert x.grounded('help "multilingual" search', DOC) == (True, None)  # typographic quotes in the text
    assert x.grounded("improves recall by 15 points", DOC) == (False, "not_grounded")
    assert x.grounded("recall", DOC) == (False, "quote_too_short")
    assert x.grounded("improves recall ... over BM25", DOC) == (False, "not_grounded")


def test_three_passes_mark_every_rejection():
    llm = FakeLLM(
        _claims(("improves recall by 12 points over BM25", "SPARROW improves recall by 12 points over BM25.", None),
                ("improves precision by 5 points", "SPARROW improves precision by 5 points.", None),
                ("We propose SPARROW", "The paper is about retrieval.", None),
                ("On three benchmarks it improves recall", "SPARROW improves recall on three benchmarks.", None)),
        {"verdicts": [{"n": 1, "claim": True}, {"n": 2, "claim": False}, {"n": 3, "claim": True}]})
    vectors = {"SPARROW improves recall by 12 points over BM25.": [1.0, 0.0],
               "SPARROW improves recall on three benchmarks.": [0.99, 0.05]}
    out = x.extract(llm, DOC, x.Settings(model="m"), embed=lambda texts: [vectors[t] for t in texts])
    assert out["ok"] and out["counts"] == {"extracted": 4, "grounded": 3, "proposition": 2, "redundant": 1,
                                           "usable": 1}
    assert [c["rejection"] for c in out["claims"]] == [None, "not_grounded", "not_proposition", "redundant"]
    assert out["input_tokens"] == 200 and len(out["calls"]) == 2
    judge = llm.calls[1]
    assert judge["user"].startswith("1. SPARROW improves recall by 12 points") and "precision" not in judge["user"]


def test_variants_differ_only_by_the_mode_field():
    base, mode = x.system_prompt("baseline"), x.system_prompt("mode")
    assert mode.startswith(base) and "hypothesis" in mode[len(base):]
    assert list(x.output_schema("baseline")["properties"]["claims"]["items"]["properties"]) == ["quote", "claim"]
    assert list(x.output_schema("mode")["properties"]["claims"]["items"]["properties"]) == ["quote", "mode", "claim"]
    llm = FakeLLM(_claims(("We expect that the approach will also help", "The approach helps.", "hypothesis"),
                          mode=True), {"verdicts": [{"n": 1, "claim": True}]})
    out = x.extract(llm, DOC, x.Settings(model="m", variant="mode"), embed=None)
    assert out["claims"][0]["mode"] == "hypothesis" and out["claims"][0]["usable"] and out["dedupe"] == "off"


def test_invalid_or_missing_output_is_a_reliability_failure():
    bad = FakeLLM(_claims(("We propose SPARROW, a retrieval", "x", "maybe"), mode=True))
    out = x.extract(bad, DOC, x.Settings(model="m", variant="mode"))
    assert not out["ok"] and out["error_reason"].startswith("schema: enum") and out["counts"]["extracted"] == 0
    out = x.extract(FakeLLM(None, error="truncated"), DOC, x.Settings(model="m"))
    assert not out["ok"] and out["error_reason"] == "truncated"


def test_a_failed_judge_leaves_claims_unusable_with_a_reason():
    llm = FakeLLM(_claims(("improves recall by 12 points over BM25", "SPARROW improves recall.", None)), None)
    out = x.extract(llm, DOC, x.Settings(model="m"))
    assert out["ok"] and out["claims"][0]["rejection"] == "judge_failed" and not out["claims"][0]["usable"]


def test_output_is_json_serialisable():
    llm = FakeLLM(_claims(("improves recall by 12 points over BM25", "SPARROW improves recall.", None)),
                  {"verdicts": [{"n": 1, "claim": True}]})
    json.dumps(x.extract(llm, DOC, x.Settings(model="m"), embed=lambda t: [[1.0]] * len(t)))


def test_abbreviation_definitions_and_glossary():
    text = "Large language models (LLMs) use chain-of-thought (CoT) prompting and retrieval (RAG) in KV caches."
    defs = x.definitions(text)
    assert defs["LLM"] == "Large language models" and defs["CoT"] == "chain-of-thought"
    assert "RAG" not in defs  # "retrieval" does not spell RAG
    glossary = x.glossary_for("We cache KV pairs and use an LLM.", {"KV": "key-value", "LLM": "large language models",
                                                                   "GRPO": "group relative policy optimization"})
    assert glossary == {"KV": "key-value", "LLM": "large language models"}
    assert x.glossary_for(text, {"LLM": "large language models"}) == {}  # defined in the text itself


def test_settings_come_from_a_configuration():
    s = x.Settings.from_config({"model": "qwen", "variant": "mode",
                                "params": {"text": "abstract", "call_mode": "tools", "dedupe_threshold": 0.9}})
    assert (s.model, s.variant, s.call_mode, s.dedupe_threshold) == ("qwen", "mode", "tools", 0.9)


def test_dictionary_keeps_only_abbreviations_defined_consistently_in_several_documents():
    from exocortex.lab.abbreviations import build

    texts = ["Large language models (LLMs) help."] * 3 + ["Knowledge graphs (KG) and a knowledge graph (KG)."] + \
            ["Key-value (KV) caches."] * 2
    rows = {r["abbreviation"]: r for r in build(texts, min_docs=3)}
    assert rows["LLM"]["long_form"] == "large language models" and rows["LLM"]["documents"] == 3
    assert "KG" not in rows and "KV" not in rows  # one document, two documents: below the floor
