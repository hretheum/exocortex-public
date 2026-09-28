# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Hypothesis cards, preregistration and gate decisions in the lab (F2.4, F2.5)."""
from __future__ import annotations

import uuid

import pytest

from exocortex.lab import experiments as ex
from exocortex.lab import gates, hypotheses, prereg
from tests.lab.conftest import needs_engine

pytestmark = needs_engine

HEAD = {"pl": ("Metryki", "| Rola | Metryka | Definicja | Próg | Linia bazowa | Jak liczona |",
               "rozstrzygająca", "ochronna", "nie więcej niż 5%"),
        "en": ("Metrics", "| Role | Metric | Definition | Threshold | Baseline | How computed |",
               "deciding", "guard", "at most 5%")}


def card(lang, slug, version=1, threshold="0,10", validated=False, supersedes=None):
    title, header, deciding, guard, guard_limit = HEAD[lang]
    other = "en" if lang == "pl" else "pl"
    name = "hypothesis.md" if version == 1 else f"hypothesis-v{version}.md"
    return f"""---
type: hypothesis_card
lang: {lang}
counterpart: ../../../{other}/experiments/{slug}/{name}
slug: {slug}
version: {version}
supersedes: {supersedes if supersedes else 'null'}
tier_target: S
data_class: public
sources: []
prereg_hash: null
human_validated: {'true' if validated else 'false'}
---

# {'Hipoteza' if lang == 'pl' else 'Hypothesis'}: {slug}

## {title}

{header}
|---|---|---|---|---|---|
| {deciding} | swap_rate | x | {threshold} | y | z |
| {guard} | failed_share | x | {guard_limit} | y | z |
"""


def decision(lang, slug, result_ids, *, threshold="0,10", decision_="GO", validated=True, version=1,
             return_condition=None, gate="G1"):
    heading = "Kryteria z karty hipotezy (bez zmian)" if lang == "pl" else "Criteria from the hypothesis card (unchanged)"
    guard_heading = "Metryki ochronne" if lang == "pl" else "Guard metrics"
    guard_limit = HEAD[lang][4]
    cols = ("| Kryterium | Próg | Wynik | Przedział ufności | Id wyniku | Spełnione |" if lang == "pl"
            else "| Criterion | Threshold | Result | Confidence interval | Result id | Met |")
    gcols = "| Metryka | Granica | Wynik | Spełnione |" if lang == "pl" else "| Metric | Limit | Result | Met |"
    other = "en" if lang == "pl" else "pl"
    rc = f'"{return_condition}"' if return_condition else "null"
    ids = ", ".join(f'"{r}"' for r in result_ids)
    return f"""---
type: gate_decision
lang: {lang}
counterpart: ../../../{other}/experiments/{slug}/gate-{gate.lower()}.md
hypothesis: {slug}
hypothesis_version: {version}
gate: {gate}
decision: {decision_}
date: "2026-09-30"
approved_by: []
return_condition: {rc}
result_ids: [{ids}]
human_validated: {'true' if validated else 'false'}
---

# Gate {gate}: {slug}

## {heading}

{cols}
|---|---|---|---|---|---|
| swap_rate | {threshold} | 0.05 | 0.02-0.09 | {result_ids[0] if result_ids else ''} | yes |

## {guard_heading}

{gcols}
|---|---|---|---|
| failed_share | {guard_limit} | 0.01 | yes |
"""


class Lab:
    """A documents folder, the lab processors and the registry, for one test."""

    def __init__(self, conn, tenant, root, monkeypatch):
        monkeypatch.delenv("EXOCORTEX_SOURCE_ALLOWLIST", raising=False)
        self.conn, self.tenant, self.root = conn, tenant, root
        self.base = f"file:///vault/_source/dowody/{uuid.uuid4().hex[:8]}/"
        self.registry = root.parent / "out" / "prereg.jsonl"
        self.slug = "h-" + uuid.uuid4().hex[:8]

    def write(self, rel, text):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def card(self, **kw):
        name = "hypothesis.md" if kw.get("version", 1) == 1 else f"hypothesis-v{kw['version']}.md"
        for lang in ("pl", "en"):
            self.write(f"{lang}/experiments/{self.slug}/{name}", card(lang, self.slug, **kw))

    def decision(self, result_ids, **kw):
        for lang in ("pl", "en"):
            self.write(f"{lang}/experiments/{self.slug}/gate-{kw.get('gate', 'G1').lower()}.md",
                       decision(lang, self.slug, result_ids, **kw))

    def sync(self):
        from exocortex.lab.docsync import current_documents, sync_documents

        sync_documents(self.conn, self.tenant, self.root, base_uri=self.base)
        docs = [d for d in current_documents(self.conn, self.tenant) if f"/{self.slug}/" in d["rel"]]
        h = hypotheses.process(self.conn, self.tenant, docs, self.registry)
        g = gates.process(self.conn, self.tenant, docs)
        return h, g

    def hypothesis(self, version=1):
        return self.conn.execute("SELECT * FROM lab_hypotheses WHERE slug = %s AND version = %s",
                                 (self.slug, version)).fetchone()

    def decision_row(self, gate="G1"):
        return self.conn.execute("SELECT * FROM lab_gate_decisions WHERE key = %s",
                                 (f"experiments/{self.slug}/gate-{gate.lower()}.md",)).fetchone()

    def result_id(self):
        exp = ex.ensure_experiment(self.conn, self.slug, "count", "test", hypothesis_slug=self.slug)
        cfg = ex.ensure_config(self.conn, exp, "a")
        sample = ex.create_sample(self.conn, exp, "tuning-1", "tuning", 1, "test",
                                  [{"item_id": "x", "content_sha256": "0" * 64}])
        run = ex.create_run(self.conn, exp, "run-2026-09-30-1", sample, hypothesis_version=1)
        rid = f"{self.slug}/run-2026-09-30-1/a/swap_rate"
        ex.record_metric(self.conn, rid, run, cfg, "swap_rate", 0.05, 0.02, 0.09, 100, "wilson")
        return rid


@pytest.fixture()
def lab(conn, tenant, tmp_path, monkeypatch):
    return Lab(conn, tenant, tmp_path / "dowody", monkeypatch)


# -- F2.4 ----------------------------------------------------------------------

def test_a_draft_card_is_a_node_but_not_registered(lab):
    lab.card()
    h, _ = lab.sync()
    assert h["cards"] == 1 and h["registered"] == 0
    row = lab.hypothesis()
    assert row["state"] == "draft" and row["prereg_sha256"] is None and row["thought_id"] is not None
    assert row["metrics"]["pl"][0] == {"role": "rozstrzygająca", "metric": "swap_rate", "threshold": "0,10",
                                       "baseline": "y"}
    assert not lab.registry.exists()


def test_approval_registers_the_card_once(lab):
    lab.card(validated=True)
    h, _ = lab.sync()
    assert h["registered"] == 1
    entries = prereg.read_registry(lab.registry)
    assert len(entries) == 1 and entries[0]["slug"] == lab.slug and entries[0]["version"] == 1
    assert entries[0]["files"]["pl"] == f"pl/experiments/{lab.slug}/hypothesis.md"
    row = lab.hypothesis()
    assert row["state"] == "frozen" and row["prereg_sha256"] == entries[0]["sha256"] and not row["violated"]
    assert lab.sync()[0]["registered"] == 0  # nothing new on the next run
    assert prereg.verify(lab.root, entries)[0]["status"] == "ok"


def test_changing_a_threshold_without_a_new_version_violates_the_card(lab):
    lab.card(validated=True)
    lab.sync()
    lab.card(validated=True, threshold="0,05")
    h, _ = lab.sync()
    assert h["violated"] == 1 and lab.hypothesis()["violated"]
    assert prereg.verify(lab.root, prereg.read_registry(lab.registry))[0]["status"] == "changed"
    # a new version is the honest way to change the card; the old one stays frozen
    lab.card(validated=True, threshold="0,10")
    lab.card(version=2, supersedes=1, threshold="0,05", validated=True)
    h, _ = lab.sync()
    assert h["registered"] == 1 and not lab.hypothesis(1)["violated"] and lab.hypothesis(2)["state"] == "frozen"
    assert len(prereg.read_registry(lab.registry)) == 2


def test_an_invalid_header_blocks_registration(lab):
    lab.card(validated=True)
    bad = card("en", lab.slug, validated=True).replace("tier_target: S", "tier_target: XL")
    lab.write(f"en/experiments/{lab.slug}/hypothesis.md", bad)
    lab.sync()
    row = lab.hypothesis()
    assert row["prereg_sha256"] is None
    assert any("tier_target" in p for p in row["problems"])


# -- F2.5 ----------------------------------------------------------------------

def test_a_valid_approved_decision_changes_the_state(lab):
    lab.card(validated=True)
    lab.sync()
    lab.decision([lab.result_id()])
    _, g = lab.sync()
    assert g == {"decisions": 1, "applied": 1, "rejected": 0, "ignored": 0}
    assert lab.hypothesis()["state"] == "GO"
    edge = lab.conn.execute("SELECT count(*) AS n FROM edges e JOIN thoughts t ON t.id = e.src_id "
                            "WHERE t.thought_type = 'gate_decision' AND t.metadata->>'hypothesis' = %s "
                            "AND e.type = 'decides'", (lab.slug,)).fetchone()
    assert edge["n"] == 1


def test_a_different_threshold_without_pivot_is_rejected(lab):
    lab.card(validated=True)
    lab.sync()
    lab.decision([lab.result_id()], threshold="0,20")
    _, g = lab.sync()
    assert g["rejected"] == 1 and lab.hypothesis()["state"] == "frozen"
    assert any("threshold of 'swap_rate'" in r for r in lab.decision_row()["reasons"])


def test_an_unapproved_decision_changes_nothing(lab):
    lab.card(validated=True)
    lab.sync()
    lab.decision([lab.result_id()], validated=False)
    _, g = lab.sync()
    assert g["ignored"] == 1 and lab.hypothesis()["state"] == "frozen"
    row = lab.decision_row()
    assert row["status"] == "ignored" and not row["approved"] and row["thought_id"] is None


def test_pivot_may_change_criteria_only_with_a_new_card_version(lab):
    lab.card(validated=True)
    lab.sync()
    rid = lab.result_id()
    lab.decision([rid], threshold="0,20", decision_="PIVOT")
    assert lab.sync()[1]["rejected"] == 1
    lab.card(version=2, supersedes=1, threshold="0,20")
    assert lab.sync()[1]["applied"] == 1
    assert lab.hypothesis(1)["state"] == "PIVOT"


def test_other_reasons_to_reject(lab):
    lab.card(validated=True)
    lab.sync()
    rid = lab.result_id()
    lab.decision([rid], decision_="NOT-NOW")
    assert lab.sync()[1]["rejected"] == 1  # no return condition
    lab.decision(["no/such/result"])
    lab.sync()
    assert any("no/such/result" in r for r in lab.decision_row()["reasons"])
    lab.decision([rid])
    lab.card(validated=True, threshold="0,01")  # the card changed after freezing
    assert lab.sync()[1]["rejected"] == 1
    assert any("gates are blocked" in r for r in lab.decision_row()["reasons"])


def test_a_decision_for_a_card_that_is_not_frozen_is_rejected(lab):
    lab.card()
    lab.sync()
    lab.decision([lab.result_id()])
    assert lab.sync()[1]["rejected"] == 1
    assert any("not frozen" in r for r in lab.decision_row()["reasons"])
