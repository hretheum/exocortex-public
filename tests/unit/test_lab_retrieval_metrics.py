# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Metrics of the retrieval experiment kind (roadmap task F5.8): hand-computed small cases, bootstrap conventions.

No database and no network: every number here can be checked with a pencil.
"""

from __future__ import annotations

import inspect
import math

import pytest

from exocortex.lab import retrieval_metrics as rm
from exocortex.lab import stats

# -- the metrics of one question, worked by hand ---------------------------------

def test_ndcg_binary_gold_by_hand():
    # gold a, b, c (grade 1); ranking x, a, y, b: DCG = 1/log2(3) + 1/log2(5) = 1.06161,
    # ideal DCG = 1 + 1/log2(3) + 1/2 = 2.13093, so nDCG = 0.49819
    value = rm.ndcg_at_k(["x", "a", "y", "b"], {"a": 1, "b": 1, "c": 1})
    assert value == pytest.approx(0.49818925746641285, abs=1e-12)
    assert value == pytest.approx((1 / math.log2(3) + 1 / math.log2(5)) / (1 + 1 / math.log2(3) + 1 / 2))


def test_ndcg_graded_gold_by_hand():
    # gold a:3, b:2, c:0; ranking b, a: DCG = 2 + 3/log2(3) = 3.89279, ideal (3, 2) = 3 + 2/log2(3) = 4.26186
    assert rm.ndcg_at_k(["b", "a"], {"a": 3, "b": 2, "c": 0}) == pytest.approx(0.9134015924715543, abs=1e-12)


def test_ndcg_of_the_ideal_ranking_is_one_and_of_a_miss_is_zero():
    gold = {"a": 2, "b": 1, "c": 1}
    assert rm.ndcg_at_k(["a", "b", "c", "z"], gold) == pytest.approx(1.0)
    assert rm.ndcg_at_k(["a", "c", "b"], gold) == pytest.approx(1.0)  # equal grades may swap: a tie in the gold
    assert rm.ndcg_at_k(["b", "a", "c"], gold) < 1.0
    assert rm.ndcg_at_k(["x", "y", "z"], gold) == 0.0


def test_ndcg_counts_only_the_first_k_places():
    ranking = [f"x{i}" for i in range(10)] + ["a"]  # the only relevant document is at rank 11
    assert rm.ndcg_at_k(ranking, {"a": 1}) == 0.0
    assert rm.ndcg_at_k(ranking, {"a": 1}, k=11) == pytest.approx(1 / math.log2(12))


def test_ndcg_grade_zero_documents_change_nothing():
    assert rm.ndcg_at_k(["z", "a"], {"a": 1, "z": 0}) == rm.ndcg_at_k(["z", "a"], {"a": 1})


def test_ranking_shorter_than_k_is_not_an_error():
    # k = 10 but two places: missing places are empty
    assert rm.ndcg_at_k(["a"], {"a": 1, "b": 1}) == pytest.approx(0.6131471927654584, abs=1e-12)
    assert rm.recall_at_k(["a"], {"a": 1, "b": 1}, k=10) == 0.5
    assert rm.recall_at_k([], {"a": 1}, k=10) == 0.0
    assert rm.reciprocal_rank([], {"a": 1}) == 0.0
    assert rm.ndcg_at_k([], {"a": 1}) == 0.0


def test_k_larger_than_the_ranking_equals_k_equal_to_it():
    ranking, gold = ["x", "a", "b"], {"a": 1, "b": 1, "c": 1}
    assert rm.recall_at_k(ranking, gold, k=3) == rm.recall_at_k(ranking, gold, k=1000) == pytest.approx(2 / 3)
    assert rm.ndcg_at_k(ranking, gold, k=3) == rm.ndcg_at_k(ranking, gold, k=1000)


def test_recall_by_hand():
    gold = {"a": 1, "b": 2, "c": 1, "d": 0}
    ranking = ["b", "x", "a", "d", "c"]
    assert rm.recall_at_k(ranking, gold, k=1) == pytest.approx(1 / 3)
    assert rm.recall_at_k(ranking, gold, k=3) == pytest.approx(2 / 3)
    assert rm.recall_at_k(ranking, gold, k=5) == 1.0  # d has grade 0: it is neither relevant nor missing


def test_mrr_by_hand():
    assert rm.reciprocal_rank(["x", "y", "b", "a"], {"a": 1, "b": 1}) == pytest.approx(1 / 3)
    assert rm.reciprocal_rank(["a", "b"], {"a": 1}) == 1.0
    assert rm.reciprocal_rank(["z", "a"], {"a": 1, "z": 0}) == 0.5  # a grade 0 document is not a hit
    assert rm.reciprocal_rank(["x", "y"], {"a": 1}) == 0.0


def test_a_repeated_document_counts_at_its_first_place_only():
    assert rm.dedupe(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]
    assert rm.reciprocal_rank(["x", "x", "a"], {"a": 1}) == 0.5
    # without the repeat, a would be at rank 2, so nDCG is not helped or hurt by it
    assert rm.ndcg_at_k(["x", "x", "a"], {"a": 1}) == rm.ndcg_at_k(["x", "a"], {"a": 1})
    assert rm.recall_at_k(["a", "a", "a"], {"a": 1, "b": 1}, k=3) == 0.5


def test_empty_gold_sets_are_undefined_not_zero():
    for gold in ({}, {"a": 0}, {"a": 0, "b": 0}):
        assert rm.ndcg_at_k(["a", "b"], gold) is None
        assert rm.recall_at_k(["a", "b"], gold, k=10) is None
        assert rm.reciprocal_rank(["a", "b"], gold) is None
    assert rm.question_values(["a"], {}) == {"ndcg@10": None, "recall@10": None, "mrr": None}


@pytest.mark.parametrize("k", [0, -1, 1.5, True, "10", None])
def test_k_must_be_a_positive_integer(k):
    with pytest.raises(ValueError, match="k must be an integer"):
        rm.recall_at_k(["a"], {"a": 1}, k=k)
    with pytest.raises(ValueError, match="k must be an integer"):
        rm.ndcg_at_k(["a"], {"a": 1}, k=k)


@pytest.mark.parametrize("grade", [-1, True])
def test_a_bad_grade_is_refused(grade):
    with pytest.raises(ValueError, match="gold grade"):
        rm.ndcg_at_k(["a"], {"a": grade})


def test_rank_by_score_breaks_ties_by_document_id():
    assert rm.rank_by_score({"b": 0.5, "a": 0.5, "c": 0.9, "d": 0.5}) == ["c", "a", "b", "d"]
    assert rm.rank_by_score({"b": 0.0, "a": 0.0}) == ["a", "b"]
    assert rm.rank_by_score({"y": -1.0, "x": -0.5}) == ["x", "y"]
    assert rm.rank_by_score({}) == []


def test_dcg_by_hand():
    assert rm.dcg([]) == 0
    assert rm.dcg([3, 2, 0, 1]) == pytest.approx(3 + 2 / math.log2(3) + 0 + 1 / math.log2(5))


def test_question_values_names_follow_the_cutoffs():
    assert rm.metric_names() == ["ndcg@10", "recall@10", "mrr"]
    assert rm.metric_names([5, 20]) == ["ndcg@10", "recall@5", "recall@20", "mrr"]
    values = rm.question_values(["a", "x"], {"a": 1, "b": 1}, recall_ks=[1, 2, 3])
    assert list(values) == ["ndcg@10", "recall@1", "recall@2", "recall@3", "mrr"]
    assert values["recall@1"] == values["recall@2"] == values["recall@3"] == 0.5
    assert values["mrr"] == 1.0


# -- settings from the spec --------------------------------------------------------

def test_settings_defaults_and_forms():
    assert rm.settings(None) == ([10], stats.BOOTSTRAP_SEED, None)
    assert rm.settings({}) == ([10], stats.BOOTSTRAP_SEED, None)
    assert rm.settings({"recall_k": 5}) == ([5], stats.BOOTSTRAP_SEED, None)
    assert rm.settings({"recall_k": [5, 10, 20], "bootstrap_seed": 7, "baseline": "a"}) == ([5, 10, 20], 7, "a")


@pytest.mark.parametrize("params, message", [
    ({"recall_k": 0}, "k must be"), ({"recall_k": [5, -1]}, "k must be"), ({"recall_k": [5, 5]}, "repeated"),
    ({"recall_k": True}, "k must be"), ({"bootstrap_seed": 1.5}, "bootstrap_seed"),
    ({"bootstrap_seed": True}, "bootstrap_seed"), ({"bootstrap_seed": "7"}, "bootstrap_seed"),
])
def test_settings_refuses_bad_values(params, message):
    with pytest.raises(ValueError, match=message):
        rm.settings(params)


# -- over questions: means, intervals, differences -----------------------------------

def _row(config, question, ranking, gold, ok=True):
    return {"config": config, "item_id": question, "ok": ok, "ranking": ranking, "gold": gold}


def _by_id(rows):
    return {m["result_id"]: m for m in rows}


def _two_configs():
    gold = {"a": 1}
    return [
        _row("good", "q1", ["a", "x"], gold), _row("good", "q2", ["a", "x"], gold), _row("good", "q3", ["a", "x"], gold),
        _row("late", "q1", ["x", "a"], gold), _row("late", "q2", ["x", "y", "a"], gold),
        _row("late", "q3", ["x", "y", "z", "a"], gold),
    ]


def test_metrics_are_means_over_questions_with_bootstrap_intervals():
    out = _by_id(rm.retrieval_metrics(_two_configs(), "exp/run-1", replicates=300))
    good, late = out["exp/run-1/good/mrr"], out["exp/run-1/late/mrr"]
    assert good["value"] == 1.0 and (good["ci_low"], good["ci_high"]) == (1.0, 1.0)
    assert late["value"] == pytest.approx((1 / 2 + 1 / 3 + 1 / 4) / 3)  # (0.5 + 0.3333 + 0.25) / 3
    assert late["ci_low"] < late["value"] < late["ci_high"]
    assert late["n"] == 3 and late["method"] == "bootstrap-by-question" and late["config"] == "late"
    assert out["exp/run-1/late/recall@10"]["value"] == 1.0
    ndcg = out["exp/run-1/late/ndcg@10"]  # one relevant document: nDCG is 1/log2(rank + 1)
    assert ndcg["value"] == pytest.approx((1 / math.log2(3) + 1 / math.log2(4) + 1 / math.log2(5)) / 3)
    assert ndcg["details"] == {"failed": 0, "undefined": 0, "k": 10}
    assert out["exp/run-1/late/mrr"]["details"] == {"failed": 0, "undefined": 0}


def test_recall_cutoffs_are_configurable_and_named_in_the_result_id():
    out = _by_id(rm.retrieval_metrics(_two_configs(), "e/r", recall_ks=[1, 3], replicates=50))
    assert out["e/r/late/recall@1"]["value"] == 0.0
    assert out["e/r/late/recall@3"]["value"] == pytest.approx(2 / 3)
    assert "e/r/late/recall@10" not in out
    assert out["e/r/late/recall@3"]["details"]["k"] == 3


def test_difference_is_b_minus_a_with_a_paired_interval():
    out = _by_id(rm.retrieval_metrics(_two_configs(), "e/r", replicates=300))
    diff = out["e/r/diff/late_minus_good/mrr"]
    assert diff["metric"] == "mrr_difference" and diff["config"] is None
    assert diff["value"] == pytest.approx((1 / 2 + 1 / 3 + 1 / 4) / 3 - 1.0)
    assert diff["details"] == {"a": "good", "b": "late", "difference": "b - a"}
    assert diff["n"] == 3
    assert diff["ci_low"] <= diff["value"] <= diff["ci_high"] < 0  # paired: the good one wins on every question


def test_differences_use_every_pair_or_only_those_with_the_baseline():
    rows = _two_configs() + [_row("mid", q, ["x", "a"], {"a": 1}) for q in ("q1", "q2", "q3")]
    every = rm.retrieval_metrics(rows, "e/r", replicates=20)
    assert sorted(m["result_id"] for m in every if m["config"] is None and m["metric"] == "mrr_difference") == [
        "e/r/diff/late_minus_good/mrr", "e/r/diff/mid_minus_good/mrr", "e/r/diff/mid_minus_late/mrr"]
    based = rm.retrieval_metrics(rows, "e/r", baseline="mid", replicates=20)
    assert sorted(m["result_id"] for m in based if m["config"] is None and m["metric"] == "mrr_difference") == [
        "e/r/diff/good_minus_mid/mrr", "e/r/diff/late_minus_mid/mrr"]
    with pytest.raises(ValueError, match="baseline 'nope'"):
        rm.retrieval_metrics(rows, "e/r", baseline="nope", replicates=20)


def test_a_single_configuration_has_no_differences():
    rows = [r for r in _two_configs() if r["config"] == "good"]
    assert all(m["config"] == "good" for m in rm.retrieval_metrics(rows, "e/r", replicates=20))


def test_identical_configurations_differ_by_exactly_zero():
    rows = [_row(c, q, ["x", "a", "b"], {"a": 2, "b": 1}) for c in ("p", "q") for q in ("q1", "q2", "q3", "q4")]
    diff = _by_id(rm.retrieval_metrics(rows, "e/r", replicates=200))["e/r/diff/q_minus_p/ndcg@10"]
    assert (diff["value"], diff["ci_low"], diff["ci_high"]) == (0.0, 0.0, 0.0)


def test_failed_results_and_undefined_questions_are_counted_not_averaged():
    rows = [_row("c", "q1", ["a"], {"a": 1}), _row("c", "q2", [], {}, ok=False),
            _row("c", "q3", ["a"], {}), _row("c", "q4", ["x", "a"], {"a": 1})]
    out = _by_id(rm.retrieval_metrics(rows, "e/r", replicates=50))
    mrr = out["e/r/c/mrr"]
    assert mrr["n"] == 2 and mrr["value"] == pytest.approx((1 + 0.5) / 2)
    assert mrr["details"] == {"failed": 1, "undefined": 1}


def test_paired_difference_uses_the_questions_both_configurations_have():
    rows = [_row("a", "q1", ["x"], {"x": 1}), _row("a", "q2", ["x"], {"x": 1}), _row("a", "q3", ["y"], {"x": 1}),
            _row("b", "q2", ["y"], {"x": 1}), _row("b", "q3", ["x"], {"x": 1}), _row("b", "q4", ["x"], {"x": 1})]
    out = _by_id(rm.retrieval_metrics(rows, "e/r", recall_ks=[1], replicates=50))
    diff = out["e/r/diff/b_minus_a/recall@1"]
    assert diff["n"] == 2  # q2 and q3
    assert diff["value"] == pytest.approx(0.5 - 0.5)  # b - a on q2: 0 - 1; on q3: 1 - 0
    assert out["e/r/a/recall@1"]["n"] == 3 and out["e/r/b/recall@1"]["n"] == 3


def test_an_empty_run_has_no_rows():
    assert rm.retrieval_metrics([], "e/r", replicates=10) == []
    only_failed = rm.retrieval_metrics([_row("c", "q1", [], {}, ok=False)], "e/r", replicates=10)
    assert {m["value"] for m in only_failed} == {None} and {m["n"] for m in only_failed} == {0}


# -- bootstrap conventions -------------------------------------------------------------

def _many(n=25):
    rows = []
    for i in range(n):
        gold = {f"d{i % 5}": 1}
        rows.append(_row("a", f"q{i:02d}", [f"d{(i * 3) % 7}", f"d{i % 5}"], gold))
        rows.append(_row("b", f"q{i:02d}", [f"d{i % 5}", f"d{(i * 3) % 7}"], gold))
    return rows


def test_bootstrap_is_deterministic_and_independent_of_row_order():
    rows = _many()
    one = rm.retrieval_metrics(rows, "e/r", replicates=200)
    assert one == rm.retrieval_metrics(rows, "e/r", replicates=200)
    assert one == rm.retrieval_metrics(list(reversed(rows)), "e/r", replicates=200)


def test_the_seed_changes_the_interval_and_defaults_to_the_labs():
    rows = _many()
    default = rm.retrieval_metrics(rows, "e/r", replicates=200)
    assert default == rm.retrieval_metrics(rows, "e/r", seed=stats.BOOTSTRAP_SEED, replicates=200)
    other = rm.retrieval_metrics(rows, "e/r", seed=1, replicates=200)
    assert [m["value"] for m in default] == [m["value"] for m in other]  # the estimates never depend on the seed
    assert [(m["ci_low"], m["ci_high"]) for m in default] != [(m["ci_low"], m["ci_high"]) for m in other]


def test_defaults_are_10000_resamples_and_the_labs_seed():
    sig = inspect.signature(rm.retrieval_metrics)
    assert sig.parameters["replicates"].default == stats.BOOTSTRAP_REPLICATES == 10_000
    assert sig.parameters["seed"].default == stats.BOOTSTRAP_SEED


def test_intervals_are_the_percentile_bootstrap_of_stats_py():
    rows = [r for r in _many(12) if r["config"] == "a"]
    values = {r["item_id"]: rm.reciprocal_rank(r["ranking"], r["gold"]) for r in rows}
    mean, low, high = stats.bootstrap_mean(values, 10_000, 123)
    got = _by_id(rm.retrieval_metrics(rows, "e/r", seed=123))["e/r/a/mrr"]  # 10,000 resamples by default
    assert (got["value"], got["ci_low"], got["ci_high"]) == (mean, low, high)


def test_difference_interval_is_the_paired_bootstrap_of_stats_py():
    rows = _many(12)
    va = {r["item_id"]: (rm.reciprocal_rank(r["ranking"], r["gold"]), 1.0) for r in rows if r["config"] == "a"}
    vb = {r["item_id"]: (rm.reciprocal_rank(r["ranking"], r["gold"]), 1.0) for r in rows if r["config"] == "b"}
    want = stats.bootstrap_difference(va, vb, 10_000, 5)
    got = _by_id(rm.retrieval_metrics(rows, "e/r", seed=5))["e/r/diff/b_minus_a/mrr"]
    assert (got["value"], got["ci_low"], got["ci_high"]) == want
