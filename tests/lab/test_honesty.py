# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Honesty check of the reference card text (F4.3): no database, no model calls.

The mode classifier is a fake that answers from a table, so the tests run
the check exactly as the card compiler will, with the F3 classifier
swapped out. Recorded results are the published toy-length files.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from exocortex.lab import cli, honesty
from exocortex.lab.honesty import Sentence

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).parent / "data" / "honesty"
TOY = ROOT / "dowody" / "data" / "toy-length"


class FakeClassifier:
    """Answers from a table; sentences it does not know read as their compiler label."""

    def __init__(self, table: dict[str, str]) -> None:
        self.table = table
        self.calls: list[str] = []

    def classify(self, text: str) -> str:
        self.calls.append(text)
        return self.table[text]


def _bad() -> list[dict]:
    return [json.loads(line) for line in (DATA / "bad_sentences.jsonl").read_text(encoding="utf-8").splitlines()]


BAD = _bad()


@pytest.fixture(scope="module")
def recorded() -> honesty.Recorded:
    return honesty.load_recorded([TOY])


def _reads_as(entry: dict) -> str:
    return entry.get("reads_as") or entry["record"]["mode"]


# -- the prepared bad sentences --------------------------------------------------------

def test_the_set_has_at_least_eight_bad_sentences_per_rule_and_language():
    counts = Counter((b["rule"], b["lang"]) for b in BAD)
    for rule in honesty.RULES:
        for lang in ("en", "pl"):
            assert counts[(rule, lang)] >= 8, (rule, lang)


@pytest.mark.parametrize("entry", BAD, ids=[f"{b['rule']}-{b['lang']}-{i}" for i, b in enumerate(BAD)])
def test_every_bad_sentence_is_stopped_by_its_rule(entry, recorded):
    s = Sentence.from_dict(entry["record"])
    violations = honesty.check([s], FakeClassifier({s.text: _reads_as(entry)}), recorded)
    assert entry["rule"] in {v.rule for v in violations}, entry["why"]
    assert all(v.sentence == 1 and v.message for v in violations)


def test_all_bad_sentences_together_are_all_reported_with_their_positions(recorded):
    card = [Sentence.from_dict(b["record"]) for b in BAD]
    violations = honesty.check(card, FakeClassifier({b["record"]["text"]: _reads_as(b) for b in BAD}), recorded)
    found = {(v.sentence, v.rule) for v in violations}
    assert all((i, b["rule"]) in found for i, b in enumerate(BAD, start=1))


# -- the reference card ----------------------------------------------------------------

def test_reference_card_passes_with_the_fake_classifier(recorded):
    card = honesty.read_card(DATA / "reference_card.jsonl")
    fake = FakeClassifier({s.text: s.mode for s in card})
    assert honesty.check(card, fake, recorded) == []
    assert fake.calls == [s.text for s in card]  # every sentence went through the classifier


def test_reference_card_passes_against_every_published_experiment():
    card = honesty.read_card(DATA / "reference_card.jsonl")
    rec = honesty.load_recorded([ROOT / "dowody" / "data"])
    assert honesty.check(card, FakeClassifier({s.text: s.mode for s in card}), rec) == []


def test_reference_card_fails_once_a_bad_sentence_is_slipped_in(recorded):
    card = honesty.read_card(DATA / "reference_card.jsonl")
    slipped = Sentence("As of today the extractor works.", "fact", "lab/recompute.py", "fact")
    card.insert(3, slipped)
    table = {s.text: s.mode for s in card}
    assert [(v.sentence, v.rule) for v in honesty.check(card, FakeClassifier(table), recorded)] == [
        (4, honesty.RULE_DATED_STATE)]


def test_the_classifier_decides_even_when_the_compiler_label_is_modest(recorded):
    s = Sentence("We expect the advantage to hold.", "hypothesis", "hyp.md", "hypothesis")
    assert honesty.check([s], FakeClassifier({s.text: "hypothesis"}), recorded) == []
    [v] = honesty.check([s], FakeClassifier({s.text: "fact"}), recorded)
    assert v.rule == honesty.RULE_FACT_SOURCE and "labelled it hypothesis" in v.message


def test_a_classifier_answer_outside_the_modes_is_an_error(recorded):
    s = Sentence("The pipeline runs.", "fact", "x.md", "fact")
    with pytest.raises(ValueError, match="classifier"):
        honesty.check([s], FakeClassifier({s.text: "opinion"}), recorded)


# -- sentence records ------------------------------------------------------------------

@pytest.mark.parametrize("fields, error", [
    ({"text": "", "mode": "fact"}, "text"),
    ({"text": "x", "mode": "claim"}, "mode"),
    ({"text": "x", "mode": "fact", "source_ref": "a.md", "source_mode": "guess"}, "source_mode"),
    ({"text": "x", "mode": "fact", "source_mode": "fact"}, "source_ref"),
    ({"text": "x", "mode": "fact", "numbers": [float("nan")]}, "finite"),
    ({"text": "x", "mode": "fact", "numbers": [True]}, "finite"),
    ({"text": "x", "mode": "fact", "date": "30.09.2026"}, "ISO date"),
    ({"text": "x", "mode": "fact", "lang": "en"}, "unknown fields"),
])
def test_invalid_records_are_rejected(fields, error):
    with pytest.raises(ValueError, match=error):
        Sentence.from_dict(fields)


def test_record_numbers_become_a_tuple_of_floats():
    s = Sentence.from_dict({"text": "x", "mode": "fact", "numbers": [12, 0.5]})
    assert s.numbers == (12.0, 0.5)


# -- numbers and the rounding tolerance -------------------------------------------------

@pytest.mark.parametrize("shown, decimals, recorded, ok", [
    (0.083, 3, 0.08333333333333333, True),   # 8.3%
    (0.08, 2, 0.08333333333333333, True),    # 8%: half a unit and within 5 %
    (0.10, 2, 0.08333333333333333, False),   # 10%
    (2522, 0, 2521.5, True),                 # half up
    (2500, 0, 2521.5, False),                # rounded to hundreds
    (0.7, 1, 0.75, False),                   # within half a unit, but 6.7 % off
    (1, 0, 0.75, False),                     # coarse rounding never passes a different number
    (12, 0, 12.0, True),
])
def test_rounding_tolerance(shown, decimals, recorded, ok):
    assert honesty.matches(shown, decimals, recorded) is ok


@pytest.mark.parametrize("text, values", [
    ("The share was 8.3%.", [(8.3, 1)]),
    ("Udział wyniósł 8,3%.", [(8.3, 1)]),
    ("Accuracy rose by seventy-five percent.", [(75.0, 0)]),
    ("Objęło to dwunastu autorów.", [(12.0, 0)]),
    ("A sample of one hundred twenty items.", [(120.0, 0)]),
    ("Change of −0.2 overall.", [(-0.2, 1)]),
    ("Over 2 521,5 znaku.", [(2521.5, 1)]),
])
def test_numbers_in_text(text, values):
    assert [c for n in honesty.numbers_in(text) for c in n.candidates[:1]] == values


@pytest.mark.parametrize("text", [
    "Phase F3 and gate G1 used qwen3.6 and model v1.",
    "Run run-2026-09-29-1 is in `results.csv` at https://example.org/a/b?x=12.",
    "See [the table](dowody/data/x.csv#row-12).",
    "As of 30 September 2026, on 2026-09-30 and in 2026, stan na 30 września 2026 r.",
    "One of the models; jeden z modeli.",
    "Related works report this.",
])
def test_identifiers_dates_and_pronouns_are_not_numbers(text):
    assert honesty.numbers_in(text) == []


def test_a_comma_with_three_digits_is_read_both_ways():
    [n] = honesty.numbers_in("1,000 items")
    assert n.candidates == ((1.0, 3), (1000.0, 0))


def test_a_percent_sign_after_a_range_covers_both_ends():
    lo, hi = honesty.numbers_in("from 1.5–35.4% of items")
    assert lo.percent and hi.percent


# -- current state ---------------------------------------------------------------------

@pytest.mark.parametrize("text, dated", [
    ("As of 30 September 2026 it works.", True),
    ("Stan na 30 września 2026: działa.", True),
    ("On 2026-09-30 it works.", True),
    ("As of September 2026 it works.", True),
    ("Since September it works.", False),
])
def test_a_date_in_the_text_counts(text, dated):
    assert honesty.has_date(text) is dated


def test_the_record_date_counts(recorded):
    s = Sentence("The extractor currently runs on the lab server.", "fact", "x.md", "fact", date="2026-09-30")
    assert honesty.check([s], FakeClassifier({s.text: "fact"}), recorded) == []


# -- recorded results ------------------------------------------------------------------

def test_recorded_results_hold_metrics_and_result_counts(recorded):
    rid = "toy-length/run-2026-09-29-1/first-sentence/long_unit_share"
    assert recorded.by_result[rid][:4] == pytest.approx([0.08333333, 0.01486509, 0.35387991, 12.0])
    assert 1.0 in recorded.by_result[rid]  # details: successes
    assert recorded.by_result["toy-length/run-2026-09-29-1/first-sentence"] == [12.0, 12.0, 0.0]


def test_a_path_without_results_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        honesty.load_recorded([tmp_path / "missing.csv"])


# -- command line ----------------------------------------------------------------------

def _cli(capsys, *argv: str) -> tuple[int, dict]:
    code = cli.main(["honesty", *argv])
    return code, json.loads(capsys.readouterr().out)


def test_cli_passes_the_reference_card(capsys):
    code, report = _cli(capsys, str(DATA / "reference_card.jsonl"), "--data", str(TOY))
    assert code == 0 and report["violations"] == [] and report["sentences"] == 15


def test_cli_exits_one_on_violations_with_the_classifier_output(tmp_path, capsys):
    card = tmp_path / "card.jsonl"
    card.write_text("\n".join(json.dumps(b["record"], ensure_ascii=False) for b in BAD), encoding="utf-8")
    modes = tmp_path / "modes.jsonl"
    modes.write_text("\n".join(json.dumps({"text": b["record"]["text"], "mode": _reads_as(b)}, ensure_ascii=False)
                               for b in BAD), encoding="utf-8")
    code, report = _cli(capsys, str(card), "--data", str(TOY), "--modes", str(modes))
    assert code == 1 and report["classifier"] == "precomputed"
    assert {v["sentence"] for v in report["violations"]} == set(range(1, len(BAD) + 1))
    assert set(report["violations"][0]) == {"sentence", "rule", "message"}


def test_cli_exits_two_on_an_invalid_card(tmp_path, capsys):
    card = tmp_path / "card.jsonl"
    card.write_text(json.dumps({"text": "x", "mode": "maybe"}), encoding="utf-8")
    code, report = _cli(capsys, str(card), "--data", str(TOY))
    assert code == 2 and "sentence 1" in report["error"]
