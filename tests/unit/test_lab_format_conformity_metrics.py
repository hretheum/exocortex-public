# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Metrics of the format conformity experiment kind (roadmap task F5.9): hand-computed small cases, the Wilson and
Newcombe intervals, verdict bookkeeping. No database and no network."""

from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import pytest

from exocortex.lab import format_conformity_metrics as fm
from exocortex.lab import stats

ROOT = Path(__file__).resolve().parents[2]


def _row(config, item, verdict, reasons=()):
    return {"config": config, "item_id": item, "verdict": verdict, "reasons": list(reasons)}


def _by_id(metrics):
    return {m["result_id"]: m for m in metrics}


# -- the Wilson interval of a share ----------------------------------------------------

def test_wilson_matches_the_textbook_example():
    # Newcombe (1998), 81 of 263: Wilson score interval 0.2553 to 0.3662
    p, low, high = stats.wilson(81, 263)
    assert (round(p, 4), round(low, 4), round(high, 4)) == (0.3080, 0.2553, 0.3662)


def test_the_share_of_conforming_answers_has_a_wilson_interval():
    rows = [_row("free", f"i{k:02d}", "conforming" if k < 16 else "non_conforming") for k in range(36)]
    m = _by_id(fm.format_metrics(rows, "e/r"))["e/r/free/conforming_share"]
    assert (m["value"], m["ci_low"], m["ci_high"]) == stats.wilson(16, 36)
    assert m["n"] == 36 and m["method"] == "wilson" and m["metric"] == "conforming_share" and m["config"] == "free"
    assert m["details"]["conforming"] == 16 and m["details"]["non_conforming"] == 20


def test_all_conforming_reaches_one_and_keeps_an_honest_lower_bound():
    rows = [_row("c", f"i{k}", "conforming") for k in range(10)]
    m = fm.format_metrics(rows, "e/r")[0]
    assert m["value"] == 1.0 and m["ci_high"] == 1.0 and m["ci_low"] == pytest.approx(0.7225, abs=1e-4)


def test_none_conforming_reaches_zero():
    m = fm.format_metrics([_row("c", f"i{k}", "non_conforming", ["not_json"]) for k in range(10)], "e/r")[0]
    assert m["value"] == 0.0 and m["ci_low"] == 0.0 and m["ci_high"] == pytest.approx(0.2775, abs=1e-4)


# -- verdict bookkeeping -----------------------------------------------------------------

def test_no_answers_and_failed_jobs_are_counted_in_the_details_not_in_the_share():
    rows = [_row("c", "i1", "conforming"), _row("c", "i2", "non_conforming", ["missing_field", "wrong_type"]),
            _row("c", "i3", "non_conforming", ["missing_field"]), _row("c", "i4", "no_answer"),
            _row("c", "i5", "no_answer"), _row("c", "i6", None)]
    m = fm.format_metrics(rows, "e/r")[0]
    assert m["n"] == 3 and m["value"] == pytest.approx(1 / 3)
    assert m["details"] == {"conforming": 1, "non_conforming": 2, "no_answer": 2, "failed_jobs": 1,
                            "reasons": {"missing_field": 2, "wrong_type": 1}}


def test_a_repeated_reason_code_counts_once_per_answer():
    rows = [_row("c", "i1", "non_conforming", ["wrong_type", "wrong_type", "wrong_type"])]
    assert fm.format_metrics(rows, "e/r")[0]["details"]["reasons"] == {"wrong_type": 1}


def test_a_configuration_without_an_answer_has_no_share():
    m = fm.format_metrics([_row("c", "i1", "no_answer"), _row("c", "i2", None)], "e/r")[0]
    assert (m["value"], m["ci_low"], m["ci_high"], m["n"]) == (None, None, None, 0)
    assert m["details"]["no_answer"] == 1 and m["details"]["failed_jobs"] == 1


def test_an_empty_run_has_no_rows():
    assert fm.format_metrics([], "e/r") == []


def test_unknown_verdicts_and_double_results_are_refused():
    with pytest.raises(ValueError, match="unknown verdict"):
        fm.format_metrics([_row("c", "i1", "maybe")], "e/r")
    with pytest.raises(ValueError, match="two results"):
        fm.format_metrics([_row("c", "i1", "conforming"), _row("c", "i1", "conforming")], "e/r")


def test_row_verdict_reads_the_stored_result():
    assert fm.row_verdict(None, None) is None
    assert fm.row_verdict(False, {"verdict": "conforming"}) == "no_answer"
    assert fm.row_verdict(True, {"verdict": "conforming"}) == "conforming"
    assert fm.row_verdict(True, {"verdict": "non_conforming"}) == "non_conforming"
    with pytest.raises(ValueError, match="must carry the verdict"):
        fm.row_verdict(True, {"verdict": "no_answer"})
    with pytest.raises(ValueError, match="must carry the verdict"):
        fm.row_verdict(True, {})


def test_reason_codes_are_read_from_the_output_once_each():
    out = {"reasons": [{"code": "b", "path": "/x"}, {"code": "a", "path": ""}, {"code": "b", "path": "/y"}]}
    assert fm.reason_codes(out) == ["a", "b"] and fm.reason_codes(None) == [] and fm.reason_codes({}) == []


# -- the paired difference ---------------------------------------------------------------

def test_newcombe_paired_by_hand():
    # two items: both configurations conform on the first, only b on the second.
    # share b = 2/2, share a = 1/2, difference 0.5. Wilson (z = 1.959964): b 0.34237 to 1, a 0.09452 to 0.90548.
    # No item is wrong in a and right in b and the reverse, so the correlation term is 0:
    # low = 0.5 - sqrt((1 - 0.34237)^2 + (0.90548 - 0.5)^2) = -0.27257, high = 0.5 + sqrt(0 + (0.5 - 0.09452)^2) = 0.90547
    d, low, high = fm.newcombe_paired(both=1, only_a=0, only_b=1, neither=0)
    assert d == 0.5
    assert low == pytest.approx(-0.27257, abs=1e-5) and high == pytest.approx(0.90547, abs=1e-5)


def test_agreement_between_the_configurations_narrows_the_interval_and_disagreement_widens_it():
    # the same two shares (0.5 and 0.5) in three different pairings of the answers
    agree = fm.newcombe_paired(both=20, only_a=0, only_b=0, neither=20)
    independent = fm.newcombe_paired(both=10, only_a=10, only_b=10, neither=10)
    opposed = fm.newcombe_paired(both=0, only_a=20, only_b=20, neither=0)
    widths = [h - lo for _, lo, h in (agree, independent, opposed)]
    assert widths[0] < widths[1] < widths[2]
    assert agree[0] == independent[0] == opposed[0] == 0.0


def test_newcombe_paired_properties_on_many_tables():
    rng = random.Random(3)
    for _ in range(300):
        both, only_a, only_b, neither = (rng.randrange(0, 40) for _ in range(4))
        n = both + only_a + only_b + neither
        if n == 0:
            continue
        d, low, high = fm.newcombe_paired(both, only_a, only_b, neither)
        assert -1.0 <= low <= d <= high <= 1.0
        assert d == pytest.approx((both + only_b) / n - (both + only_a) / n)
        back = fm.newcombe_paired(both, only_b, only_a, neither)  # swapping the configurations mirrors everything
        assert back[0] == pytest.approx(-d) and back[1] == pytest.approx(-high) and back[2] == pytest.approx(-low)


def test_newcombe_paired_when_every_item_agrees_does_not_collapse():
    d, low, high = fm.newcombe_paired(both=30, only_a=0, only_b=0, neither=0)
    assert d == 0.0 and low < 0.0 < high  # 30 of 30 is not proof that the configurations are identical


def test_newcombe_paired_refuses_bad_counts_and_has_nothing_to_say_about_no_items():
    assert fm.newcombe_paired(0, 0, 0, 0) == (None, None, None)
    for bad in ((-1, 0, 0, 1), (1.5, 0, 0, 1), (True, 0, 0, 1)):
        with pytest.raises(ValueError, match="counts must be integers"):
            fm.newcombe_paired(*bad)


def test_the_difference_is_b_minus_a_on_the_items_both_answered():
    rows = [_row("a", "i1", "conforming"), _row("a", "i2", "non_conforming", ["not_json"]),
            _row("a", "i3", "conforming"), _row("a", "i4", "non_conforming", ["not_json"]),
            _row("a", "i5", "no_answer"),
            _row("b", "i1", "conforming"), _row("b", "i2", "conforming"), _row("b", "i3", "non_conforming", ["x"]),
            _row("b", "i4", "conforming"), _row("b", "i5", "conforming"), _row("b", "i6", "conforming")]
    out = _by_id(fm.format_metrics(rows, "e/r"))
    diff = out["e/r/diff/b_minus_a/conforming_share"]
    # shared items i1 to i4: both on i1, only b on i2 and i4, only a on i3
    assert diff["n"] == 4 and diff["metric"] == "conforming_share_difference" and diff["config"] is None
    assert diff["method"] == "newcombe-paired"
    assert diff["details"] == {"a": "a", "b": "b", "difference": "b - a", "both": 1, "only_a": 1, "only_b": 2,
                               "neither": 0}
    assert (diff["value"], diff["ci_low"], diff["ci_high"]) == fm.newcombe_paired(1, 1, 2, 0)
    assert out["e/r/a/conforming_share"]["n"] == 4 and out["e/r/b/conforming_share"]["n"] == 6


def test_differences_use_every_pair_or_only_those_with_the_baseline():
    rows = [_row(c, f"i{k}", "conforming") for c in "abc" for k in range(3)]
    every = {m["result_id"] for m in fm.format_metrics(rows, "e/r") if m["config"] is None}
    assert every == {"e/r/diff/b_minus_a/conforming_share", "e/r/diff/c_minus_a/conforming_share",
                     "e/r/diff/c_minus_b/conforming_share"}
    versus_b = {m["result_id"] for m in fm.format_metrics(rows, "e/r", baseline="b") if m["config"] is None}
    assert versus_b == {"e/r/diff/a_minus_b/conforming_share", "e/r/diff/c_minus_b/conforming_share"}
    with pytest.raises(ValueError, match="baseline 'z' is not a configuration"):
        fm.format_metrics(rows, "e/r", baseline="z")


def test_a_single_configuration_has_no_differences():
    rows = [_row("a", "i1", "conforming")]
    assert [m["config"] for m in fm.format_metrics(rows, "e/r")] == ["a"]


def test_configurations_with_no_shared_answered_item_have_no_difference():
    rows = [_row("a", "i1", "conforming"), _row("b", "i2", "conforming")]
    diff = _by_id(fm.format_metrics(rows, "e/r"))["e/r/diff/b_minus_a/conforming_share"]
    assert (diff["value"], diff["ci_low"], diff["ci_high"], diff["n"]) == (None, None, None, 0)


def test_the_result_does_not_depend_on_the_order_of_the_rows():
    rng = random.Random(1)
    rows = [_row(c, f"i{k:02d}", rng.choice(["conforming", "non_conforming", "no_answer", None]), ["not_json"])
            for c in ("a", "b", "c") for k in range(30)]
    shuffled = rows[:]
    rng.shuffle(shuffled)
    assert fm.format_metrics(rows, "e/r") == fm.format_metrics(shuffled, "e/r")


# -- the guard reference -----------------------------------------------------------------

def test_the_guard_is_carried_as_a_reference_row_without_a_value():
    guard = {"experiment": "intent-vs-fact", "metric": "usable_per_document"}
    rows = [_row("a", "i1", "conforming"), _row("b", "i1", "conforming")]
    out = _by_id(fm.format_metrics(rows, "e/r", guard=guard))
    ref = out["e/r/guard/intent-vs-fact/usable_per_document"]
    assert ref["metric"] == "guard:intent-vs-fact/usable_per_document" and ref["method"] == "reference"
    assert (ref["value"], ref["ci_low"], ref["ci_high"], ref["n"], ref["config"]) == (None, None, None, 0, None)
    assert ref["details"] == {"guard": guard, "computed_here": False}
    assert not any(m["method"] == "reference" for m in fm.format_metrics(rows, "e/r"))  # no guard, no row


# -- settings ----------------------------------------------------------------------------

def test_settings_defaults_and_forms():
    assert fm.settings(None) == (None, None)
    assert fm.settings({"baseline": "free", "guard": {"experiment": "x", "metric": "y"}}) == (
        "free", {"experiment": "x", "metric": "y"})


@pytest.mark.parametrize("params, message", [
    ({"baseline": 3}, "baseline must be a configuration name"),
    ({"guard": "x"}, "guard must be a mapping"),
    ({"guard": {"experiment": "x"}}, "guard must be a mapping"),
    ({"guard": {"experiment": "x", "metric": "y", "extra": "z"}}, "guard must be a mapping"),
    ({"guard": {"experiment": "x", "metric": ""}}, "guard must be a mapping"),
    ({"guard": {"experiment": 1, "metric": "y"}}, "guard must be a mapping"),
])
def test_settings_refuses_bad_values(params, message):
    with pytest.raises(ValueError, match=message):
        fm.settings(params)


# -- the file stands alone ---------------------------------------------------------------

def test_metrics_and_the_independent_check_agree_on_many_tables():
    spec = importlib.util.spec_from_file_location("independent_format_check", ROOT / "lab" / "independent_format_check.py")
    assert spec is not None and spec.loader is not None
    check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(check)
    rng = random.Random(11)
    for _ in range(200):
        a = {f"i{k}": rng.random() < rng.choice([0.1, 0.5, 0.9, 1.0]) for k in range(rng.randrange(1, 60))}
        b = {k: (v if rng.random() < 0.7 else rng.random() < 0.5) for k, v in a.items()}
        d, low, high, n, table = check.newcombe(a, b)
        assert (d, low, high) == fm.newcombe_paired(table["both"], table["only_a"], table["only_b"], table["neither"])
        assert n == len(a)
        s = sum(a.values())
        assert check.wilson(s, len(a)) == stats.wilson(s, len(a))


def test_the_module_needs_nothing_outside_the_standard_library_and_stats_py():
    source = (ROOT / "exocortex" / "lab" / "format_conformity_metrics.py").read_text(encoding="utf-8")
    imports = {line.split()[1].split(".")[0] for line in source.splitlines() if line.startswith(("import ", "from "))}
    assert imports <= {"__future__", "math", "collections", "exocortex"}
    assert "from exocortex.lab import stats" in source
