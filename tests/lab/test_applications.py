# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Business applications section (F8.1): the evidence rule, the source checksum, the checker and the draft.

Synthetic documents only; the model is a stand-in object. No database.
"""

from __future__ import annotations

import datetime as dt
import secrets
import sys
from pathlib import Path

import pytest

from exocortex.lab import applications as ap
from exocortex.lab import evidence
from exocortex.lab.llm import Call
from tests.lab.applications_tree import make, model_output

ROOT = Path(__file__).resolve().parents[2]
TODAY = dt.date(2026, 9, 29)
MODELS = {"qwen3.6-35b-a3b"}
M_GO = ("toy/run-1/a/acc,run-1,a,accuracy,0.75,0.6,0.86,40,wilson,{}\n"
        "toy/run-1/b/acc,run-1,b,accuracy,0.5,0.4,0.6,25,wilson,{}\n")


def label(docs: Path, slug: str = "toy") -> evidence.Evidence:
    return evidence.assess(docs, slug)[2]


# ------------------------------------------------------------------ the rule ----
@pytest.mark.parametrize("setup, key, n", [
    ({}, "none", None),
    ({"metrics": M_GO}, "preliminary", None),
    ({"runs": {"run-1.md": ["toy/run-1/a/acc"]}}, "preliminary", None),
    ({"metrics": M_GO, "gates": {"gate-g1.md": ("GO", ["tak", "tak"], ["toy/run-1/a/acc", "toy/run-1/b/acc"])}},
     "confirmed", 25),
    ({"metrics": M_GO, "gates": {"gate-g1.md": ("NO-GO", ["tak", "nie"], ["toy/run-1/a/acc"])}}, "refuted", 40),
    ({"metrics": M_GO, "gates": {"gate-g1.md": ("PIVOT", ["tak"], ["toy/run-1/a/acc"])}}, "inconclusive", None),
    ({"metrics": M_GO, "gates": {"gate-g1.md": ("NOT-NOW", ["nie"], ["toy/run-1/a/acc"])}}, "inconclusive", None),
    ({"metrics": M_GO, "gates": {"gate-g1.md": ("CLOSED", ["tak"], ["toy/run-1/a/acc"])}}, "inconclusive", None),
    # a decision against its own numbers is not a confirmation or a refutation
    ({"metrics": M_GO, "gates": {"gate-g1.md": ("GO", ["tak", "nie"], ["toy/run-1/a/acc"])}}, "inconclusive", None),
    ({"metrics": M_GO, "gates": {"gate-g1.md": ("NO-GO", ["tak"], ["toy/run-1/a/acc"])}}, "inconclusive", None),
    # a decision nobody approved does not count
    ({"metrics": M_GO, "gates": {"gate-g1.md": ("GO", ["tak"], ["toy/run-1/a/acc"], False)}}, "preliminary", None),
    # the latest approved decision wins
    ({"metrics": M_GO, "gates": {"gate-g1.md": ("GO", ["tak"], ["toy/run-1/a/acc"], True, "2026-10-01"),
                                 "gate-g2.md": ("NO-GO", ["nie"], ["toy/run-1/b/acc"], True, "2026-10-09", "G2")}},
     "refuted", 25),
])
def test_label_rule(tmp_path, setup, key, n):
    ev = label(make(tmp_path, **setup))
    assert (ev.key, ev.n, ev.problems) == (key, n, [])


def test_labels_in_both_languages(tmp_path):
    ev = label(make(tmp_path, metrics=M_GO,
                    gates={"gate-g1.md": ("GO", ["tak"], ["toy/run-1/a/acc", "toy/run-1/b/acc"])}))
    assert ev.label("pl") == "potwierdzone na próbie 25" and ev.label("en") == "confirmed on a sample of 25"
    assert evidence.Evidence("none").label("pl") == "hipoteza, bez dowodu"
    assert {evidence.Evidence(k, 7).label("pl") for k in evidence.KEYS} == {
        "hipoteza, bez dowodu", "wstępne", "potwierdzone na próbie 7", "obalone na próbie 7", "nierozstrzygnięte"}


def test_unknown_sample_size_is_a_problem_not_a_guess(tmp_path):
    ev = label(make(tmp_path, metrics="toy/x,run-1,a,accuracy,0.7,,,,wilson,{}\n",
                    gates={"gate-g1.md": ("GO", ["tak"], ["toy/x", "toy/missing"])}))
    assert ev.key == "inconclusive" and ev.n is None
    assert any("no sample size" in p for p in ev.problems) and any("not in metrics.csv" in p for p in ev.problems)


def test_decision_in_one_language_only_is_ignored(tmp_path):
    make(tmp_path, metrics=M_GO, gates={"gate-g1.md": ("GO", ["tak"], ["toy/run-1/a/acc"])})
    (tmp_path / "en" / "experiments" / "toy" / "gate-g1.md").unlink()
    assert label(tmp_path).key == "preliminary"


# ------------------------------------------------------------------ the checksum ----
def test_source_hash_follows_results_decisions_and_fields_only(tmp_path):
    docs = make(tmp_path, metrics=M_GO)
    first = evidence.assess(docs, "toy")[1]
    assert evidence.assess(docs, "toy")[1] == first
    overview = docs / "pl" / "experiments" / "toy" / "overview.md"
    text = overview.read_text(encoding="utf-8")
    overview.write_text(text.replace("## Streszczenie\n\nText.", "## Streszczenie\n\nAnother text.") + "\n\n",
                        encoding="utf-8")
    assert evidence.assess(docs, "toy")[1] == first  # other sections and trailing blank lines do not count

    metrics = docs / "data" / "toy" / "metrics.csv"
    metrics.write_text(metrics.read_text(encoding="utf-8").replace("0.75", "0.74"), encoding="utf-8")
    changed = evidence.assess(docs, "toy")[1]
    assert changed != first

    overview.write_text(overview.read_text(encoding="utf-8").replace("status: planned", "status: running"),
                        encoding="utf-8")
    assert evidence.assess(docs, "toy")[1] != changed
    moved = evidence.assess(docs, "toy")[1]
    overview.write_text(overview.read_text(encoding="utf-8").replace("Brak wyników.", "Są wyniki."), encoding="utf-8")
    assert evidence.assess(docs, "toy")[1] != moved
    after_results = evidence.assess(docs, "toy")[1]
    make(docs, metrics=None, gates={"gate-g1.md": ("GO", ["tak"], ["toy/run-1/a/acc"], False)})
    assert evidence.assess(docs, "toy")[1] != after_results  # a new decision file, even unapproved


def test_the_site_uses_the_same_function():
    sys.path.insert(0, str(ROOT / "lab-site"))
    try:
        import model
    finally:
        sys.path.remove(str(ROOT / "lab-site"))
    assert Path(model.EVIDENCE_PY).resolve() == Path(evidence.__file__).resolve()
    assert model.evidence.source_hash({"a": 1}) == evidence.source_hash({"a": 1})
    assert model.evidence.ALGORITHM == evidence.ALGORITHM
    assert model.SECTION_KEYS.index("results") == evidence.RESULTS_POSITION


def test_evidence_imports_nothing_from_the_package():
    text = Path(evidence.__file__).read_text(encoding="utf-8")
    assert "from exocortex" not in text and "import exocortex" not in text


# ------------------------------------------------------------------ the checker ----
class FakeLLM:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.prompts: list[str] = []

    def structured(self, *, model, system, user, schema, name, **kw):
        self.prompts.append(user)
        out = self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]
        return Call(model=model, output=out) if isinstance(out, dict) else Call(model=model, error=out)


@pytest.fixture()
def scanner(tmp_path):
    from tools.leakgate.denylist import Denylist, build
    from tools.leakgate.scan import Config, Scanner

    key = bytes.fromhex(secrets.token_hex(32))
    src = tmp_path / "deny.yaml"
    src.write_text('version: 1\nentries:\n  - {term: "Vexalor", tier: block}\n', encoding="utf-8")
    return Scanner(Denylist(build(src, key)["hashes"], key), Config.load())


def _kinds():
    return ap.catalogue(ROOT / "lab" / "applications-catalogue.yaml")


def _draft(docs, llm, scanner, **kw):
    return ap.draft(docs, "toy", llm, scanner=scanner, kinds=_kinds(), models=MODELS, today=TODAY, **kw)


def _texts(docs, slug="toy"):
    return ap.read_pair(docs, slug)


def _check_texts(docs, texts, scanner):
    inputs, digest, ev = evidence.assess(docs, "toy")
    return ap.check_texts("toy", texts, inputs, digest, ev, scanner=scanner)


def test_draft_writes_a_pair_that_passes_the_checker(tmp_path, scanner):
    docs = make(tmp_path)
    result = _draft(docs, FakeLLM(model_output()), scanner)
    assert result["written"] == ["pl/experiments/toy/applications.md", "en/experiments/toy/applications.md"]
    texts = _texts(docs)
    pl, _ = ap._front(texts["pl"])
    assert pl["publish"] is False and pl["human_validated"] is False
    assert pl["label"] == "hipoteza, bez dowodu" and pl["source_hash"] == evidence.assess(docs, "toy")[1]
    assert "## Jeśli potwierdzimy, jeśli obalimy" in texts["pl"] and "## If we confirm, if we refute" in texts["en"]
    assert "| hipoteza, bez dowodu |" in texts["pl"] and "| hypothesis, no evidence |" in texts["en"]
    rep = ap.check(docs, "toy", scanner=scanner)
    assert rep.ok, rep.problems


def test_a_current_draft_is_kept_and_a_changed_result_redrafts(tmp_path, scanner):
    docs = make(tmp_path)
    _draft(docs, FakeLLM(model_output()), scanner)
    assert "skipped" in _draft(docs, FakeLLM(model_output()), scanner)
    make(docs, metrics=M_GO)
    assert not ap.check(docs, "toy", scanner=scanner).ok  # the old draft is stale now
    result = _draft(docs, FakeLLM(model_output(scenarios=True)), scanner)
    assert "written" in result, result
    assert ap._front(_texts(docs)["pl"])[0]["label"] == "wstępne"


def test_draft_refuses_a_model_outside_the_allowlist(tmp_path, scanner):
    result = ap.draft(make(tmp_path), "toy", FakeLLM(model_output()), model="some-cloud-model", scanner=scanner,
                      kinds=_kinds(), models=MODELS)
    assert "refused" in result and not (tmp_path / "pl" / "experiments" / "toy" / "applications.md").exists()
    assert ap.allowed_models(ROOT / "lab" / "models.yaml") >= MODELS


def test_draft_with_a_foreign_number_is_retried_then_refused(tmp_path, scanner):
    llm = FakeLLM(model_output(number=" w 42 zespołach"))
    result = _draft(make(tmp_path), llm, scanner)
    assert result["refused"] == "no draft passed the checks" and result["attempts"] == 2
    assert "number 42" in llm.prompts[1]  # the second call is told why the first was rejected
    assert not (tmp_path / "pl" / "experiments" / "toy" / "applications.md").exists()


def test_draft_refuses_when_the_label_cannot_be_computed(tmp_path, scanner):
    docs = make(tmp_path, metrics="toy/x,run-1,a,accuracy,0.7,,,,wilson,{}\n",
                gates={"gate-g1.md": ("GO", ["tak"], ["toy/x"])})
    assert _draft(docs, FakeLLM(model_output()), scanner)["refused"] == "the label cannot be computed"


def test_a_reply_outside_the_schema_is_rejected(tmp_path, scanner):
    bad = model_output()
    bad["rows"][0]["result"] = "gate:gate-g9.md"  # not an item of this dossier
    assert "refused" in _draft(make(tmp_path), FakeLLM(bad), scanner)


def _good(tmp_path, scanner, **setup):
    docs = make(tmp_path, **setup)
    result = _draft(docs, FakeLLM(model_output(result=setup.pop("ref", "results-section"))), scanner)
    assert "written" in result, result
    return docs, _texts(docs)


@pytest.mark.parametrize("lang, old, new, expect", [
    ("pl", "[wyniki w dossier](overview.md#s-results)", "przyszłe badania", "does not refer to a result"),
    ("en", "[results in the dossier](overview.md#s-results)", "[results](other.md)", "does not refer to a result"),
    ("pl", "label: hipoteza, bez dowodu", "label: wstępne", "is not the computed"),
    ("pl", "| hipoteza, bez dowodu |", "| potwierdzone na próbie 25 |", "strength"),
    ("pl", "jeden korpus publiczny", "jeden korpus publiczny z 1200 dokumentami", "number 1200"),
    ("en", "one public corpus", "one public corpus, 35% faster", "number 35%"),
    ("pl", "zespoły produktowe", "zespoły produktowe w Vexalor", "leakgate rule denylist"),
    ("pl", "zespoły produktowe", "zespoły produktowe (koszt w PLN)", "currency"),
    ("en", "product teams", "product teams paying in $", "currency"),
    ("en", "product teams", "product teams with 2 million users", "amount"),
    ("pl", "wybór sposobu", "zysk z wyboru sposobu", "profit"),
    ("pl", "wybór sposobu", "zarobek przy wyborze sposobu", "profit"),
    ("en", "choosing how", "higher revenue from choosing how", "profit"),
    ("en", "choosing how", "a guaranteed ROI when choosing how", "profit"),
    ("en", "## If we confirm, if we refute", "## Scenarios", "sections are"),
    ("pl", "source_hash: ", "source_hash: 0", "source_hash"),
    ("pl", "Hipoteza mówi", "Hipoteza mówi 🚀", "humanlint"),
])
def test_checker_rejects(tmp_path, scanner, lang, old, new, expect):
    docs, texts = _good(tmp_path, scanner)
    assert old in texts[lang], old
    texts[lang] = texts[lang].replace(old, new, 1)
    rep = _check_texts(docs, texts, scanner)
    assert any(expect in p for p in rep.problems), rep.problems


def test_checker_rejects_versions_that_are_not_a_pair(tmp_path, scanner):
    docs, texts = _good(tmp_path, scanner)
    row = next(line for line in texts["en"].splitlines() if line.startswith("| Tool choice"))
    texts["en"] = texts["en"].replace(row, row + "\n" + row)
    rep = _check_texts(docs, texts, scanner)
    assert any(p.startswith("pair:") for p in rep.problems), rep.problems
    rep = _check_texts(docs, {"pl": texts["pl"]}, scanner)
    assert "en: missing" in rep.problems


def test_checker_accepts_numbers_of_the_results(tmp_path, scanner):
    docs = make(tmp_path, metrics=M_GO, gates={"gate-g1.md": ("GO", ["tak"], ["toy/run-1/a/acc"])})
    one_sided = model_output(result="result:toy/run-1/a/acc")
    one_sided["sentence"]["pl"] = "Trafność 75% wskazuje prostszy wybór."
    result = _draft(docs, FakeLLM(one_sided), scanner)
    assert "refused" in result  # a number of the results, but only in Polish: not a pair
    assert any(p.startswith("pair: numbers") for p in result["problems"]), result["problems"]
    good = model_output(result="result:toy/run-1/a/acc")
    good["sentence"] = {"pl": "Trafność 0,75 na próbie 40 wskazuje prostszy wybór.",
                        "en": "Accuracy of 0.75 on a sample of 40 points to the simpler choice."}
    result = _draft(docs, FakeLLM(good), scanner)
    assert "written" in result, result
    texts = _texts(docs)
    assert "| `toy/run-1/a/acc` | potwierdzone na próbie 40 |" in texts["pl"]
    assert "## Jeśli potwierdzimy" in texts["pl"]  # status is still planned in this dossier
    assert ap.check(docs, "toy", scanner=scanner).ok


def test_checker_fails_without_the_name_scanner(tmp_path, scanner):
    docs, _ = _good(tmp_path, scanner)
    rep = ap.check(docs, "toy", scanner=None, scanner_missing="names: not checked (no key)")
    assert rep.problems == ["names: not checked (no key)"]
    rep = ap.check(docs, "toy", scanner=None, require_all=False)
    assert rep.ok and rep.not_run == ["names: not checked (no scanner)"]


def test_scenarios_only_for_planned_and_prepared_or_without_evidence(tmp_path, scanner):
    docs = make(tmp_path, status="decided", metrics=M_GO,
                gates={"gate-g1.md": ("NO-GO", ["nie"], ["toy/run-1/b/acc"])})
    out = model_output(scenarios=True, result="gate:gate-g1.md")
    assert "refused" in _draft(docs, FakeLLM(out), scanner)  # the schema has no scenarios for this dossier
    result = _draft(docs, FakeLLM(model_output(scenarios=False, result="gate:gate-g1.md")), scanner)
    assert "written" in result, result
    texts = _texts(docs)
    assert "Jeśli potwierdzimy" not in texts["pl"] and "| obalone na próbie 25 |" in texts["pl"]
    assert "[gate-g1](gate-g1.md)" in texts["en"]


@pytest.mark.parametrize("written, pct, allowed, ok", [
    ("0,75", False, [0.75], True), ("0.8", False, [0.75], True), ("75", True, [0.75], True),
    ("75", False, [0.75], False), ("1", False, [0.75], False), ("40", False, [40.0], True),
    ("41", False, [40.0], False), ("8", True, [0.0833], True),
])
def test_number_matching(written, pct, allowed, ok):
    assert ap.number_allowed(written, pct, allowed) is ok


def test_numbers_that_are_not_results_are_ignored():
    text = ap._plain("Zadanie F5.5, bramka G1, nDCG@10, bge-m3, `run-2026-09-29-1`, 2026-09-29, [x](a/1.md)\n1. lista")
    assert ap.numbers_in(text) == []


def test_catalogue_has_the_five_kinds_in_both_languages():
    kinds = _kinds()
    assert [k["id"] for k in kinds] == ["tool-choice", "cost-vs-quality", "risk-and-compliance", "product-design",
                                        "research-organisation"]
    for k in kinds:
        for lang in ("pl", "en"):
            assert k[lang]["name"] and k[lang]["description"].endswith(".")
            assert not ap.check_money(k[lang]["description"], 0)


@pytest.mark.parametrize("publish, validated, ok", [
    ("false", "false", True),   # a draft
    ("true", "true", True),     # approved by the owner
    ("false", "true", False),   # approved but still held back
    ("true", "false", False),   # released without approval
])
def test_approval_needs_publish_true_and_human_validated_true(tmp_path, scanner, publish, validated, ok):
    docs, texts = _good(tmp_path, scanner)
    for lang in ("pl", "en"):
        texts[lang] = (texts[lang].replace("publish: false", f"publish: {publish}")
                       .replace("human_validated: false", f"human_validated: {validated}"))
    rep = _check_texts(docs, texts, scanner)
    assert rep.ok is ok, rep.problems
    if not ok:
        assert any("approval needs both publish: true and human_validated: true" in p for p in rep.problems)


def test_removing_the_publish_field_is_not_an_approval(tmp_path, scanner):
    docs, texts = _good(tmp_path, scanner)
    for lang in ("pl", "en"):
        texts[lang] = texts[lang].replace("publish: false\n", "").replace("human_validated: false", "human_validated: true")
    rep = _check_texts(docs, texts, scanner)
    assert any("header field publish is missing" in p for p in rep.problems), rep.problems
