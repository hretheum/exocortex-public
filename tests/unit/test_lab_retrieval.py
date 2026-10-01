# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Experiment kind ``retrieval`` (roadmap task F5.8): question set parsing and validation, corpus files,
retrieval configurations, spec validation and the kind's registration. No database, no network."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from exocortex.lab import cli, specs
from exocortex.lab import retrieval as R

ROOT = Path(__file__).resolve().parents[2]
DOCS = {"d1": "red apples grow on trees", "d2": "green pears grow on trees", "d3": "blue boats float on water",
        "d4": "fast cars drive on roads", "d5": "apples and pears are fruit"}
MODELS = {"bge-m3": {"id": "bge-m3", "family": "bge"},
          "hosted-embed": {"id": "hosted-embed", "provider": "openai", "data_class": "public",
                           "experiments": ["other-experiment"]}}


def problems_of(call):
    with pytest.raises(R.RetrievalInputError) as info:
        call()
    return info.value.problems


# -- question sets: CSV -----------------------------------------------------------

GOOD_CSV = """question_id,question,gold
q1,Which fruit grows on trees?,d1;d2:2;d5:0
q2,"What floats, and where?",d3
"""


def test_csv_question_set_is_read_with_grades():
    questions = R.parse_questions_csv(GOOD_CSV, set(DOCS))
    assert [q.id for q in questions] == ["q1", "q2"]
    assert questions[0].gold == {"d1": 1, "d2": 2, "d5": 0}  # no grade means 1; 0 is kept
    assert questions[1].text == "What floats, and where?"  # a quoted comma is fine


def test_csv_header_may_be_in_any_order_and_a_bom_or_blank_lines_are_harmless(tmp_path):
    path = tmp_path / "q.csv"
    path.write_text("﻿gold,question,question_id\nd1;d2,First?,a\n\n   ,  ,\nd3,Second?,b\n", encoding="utf-8")
    assert [(q.id, q.text, q.gold) for q in R.load_questions(path)] == [
        ("a", "First?", {"d1": 1, "d2": 1}), ("b", "Second?", {"d3": 1})]


@pytest.mark.parametrize("text, expected", [
    ("", "the file is empty"),
    ("question_id,question,gold\n", "no question"),
    ("id,question,gold\nq1,X?,d1\n", "header must be exactly"),
    ("question_id,question\nq1,X?\n", "header must be exactly"),
    ("question_id,question,gold,extra\nq1,X?,d1,y\n", "header must be exactly"),
    ("question_id,question,gold,gold\nq1,X?,d1,d2\n", "header must be exactly"),
    ("question_id,question,gold\nq1,X?,d1\nq1,Y?,d2\n", "line 3: question_id 'q1' is used twice"),
    ("question_id,question,gold\n_q,X?,d1\n", "question_id must be"),
    ("question_id,question,gold\nq 1,X?,d1\n", "question_id must be"),
    ("question_id,question,gold\nq1,   ,d1\n", "the question is empty"),
    ("question_id,question,gold\nq1,\"two\nlines\",d1\n", "control character or a line break"),
    ("question_id,question,gold\nq1,X?,\n", "gold lists no document"),
    ("question_id,question,gold\nq1,X?,d1;\n", "empty entry in gold"),
    ("question_id,question,gold\nq1,X?,d1;;d2\n", "empty entry in gold"),
    ("question_id,question,gold\nq1,X?,d1:4\n", "outside 0 to 3"),
    ("question_id,question,gold\nq1,X?,d1:-1\n", "grade must be an integer"),
    ("question_id,question,gold\nq1,X?,d1:x\n", "grade must be an integer"),
    ("question_id,question,gold\nq1,X?,d1:1.5\n", "grade must be an integer"),
    ("question_id,question,gold\nq1,X?,d1;d1:2\n", "listed twice"),
    ("question_id,question,gold\nq1,X?,d1:0;d2:0\n", "no gold document has a grade above 0"),
    ("question_id,question,gold\nq1,X?,zz\n", "'zz' is not in the corpus"),
    ("question_id,question,gold\nq1,X?,d 1\n", "is not a document id"),
    ("question_id,question,gold\nq1,X? and, more,d1\n", "4 field(s), the header has 3"),
    ("question_id,question,gold\nq1,X?\n", "2 field(s), the header has 3"),
    ('question_id,question,gold\nq1,"X?,d1\n', "not valid CSV"),
])
def test_csv_problems_are_named_with_their_line(text, expected):
    assert any(expected in p for p in problems_of(lambda: R.parse_questions_csv(text, set(DOCS))))


def test_every_problem_of_a_file_is_reported_at_once():
    text = "question_id,question,gold\nq1,X?,zz\nq1,,d1:9\nq3,Y?,d1;d1\nq4,Z?,d1\n"
    found = problems_of(lambda: R.parse_questions_csv(text, set(DOCS), source="my.csv"))
    assert len(found) >= 4
    assert {p.split(":")[0] for p in found} >= {"line 2", "line 3", "line 4"}
    assert not any("line 5" in p for p in found)  # the valid question is not blamed
    error = R.RetrievalInputError("my.csv", found)
    assert str(error).startswith("my.csv: ") and "\n- line 2" in str(error)


def test_a_long_list_of_problems_is_cut_in_the_message_but_kept_in_full():
    text = "question_id,question,gold\n" + "".join(f"q{i},X?,zz\n" for i in range(30))
    error = pytest.raises(R.RetrievalInputError, R.parse_questions_csv, text, set(DOCS)).value
    assert len(error.problems) == 30 and "and 10 more" in str(error)


def test_gold_ids_are_not_checked_against_a_corpus_when_none_is_given():
    assert R.parse_questions_csv("question_id,question,gold\nq1,X?,anything/at.all-1\n")[0].gold == {"anything/at.all-1": 1}


# -- question sets: JSONL ---------------------------------------------------------

def _jl(*objs):
    return "\n".join(o if isinstance(o, str) else json.dumps(o) for o in objs) + "\n"


def test_jsonl_question_set_accepts_lists_objects_and_maps():
    text = _jl({"question_id": "a", "question": "One?", "gold": ["d1", {"doc": "d2", "grade": 3}, {"doc": "d5"}]},
               {"question_id": "b", "question": "Two?", "gold": {"d3": 2, "d4": 0}}, "")
    questions = R.parse_questions_jsonl(text, set(DOCS))
    assert questions[0].gold == {"d1": 1, "d2": 3, "d5": 1}
    assert questions[1].gold == {"d3": 2, "d4": 0}


@pytest.mark.parametrize("line, expected", [
    ("{not json", "not valid JSON"),
    ("[1, 2]", "exactly the keys"),
    ({"question_id": "a", "question": "X?"}, "exactly the keys"),
    ({"question_id": "a", "question": "X?", "gold": ["d1"], "extra": 1}, "exactly the keys"),
    ({"question_id": 7, "question": "X?", "gold": ["d1"]}, "question_id must be"),
    ({"question_id": "a", "question": 7, "gold": ["d1"]}, "the question is empty"),
    ({"question_id": "a", "question": "X?", "gold": "d1"}, "gold must be a list or an object"),
    ({"question_id": "a", "question": "X?", "gold": []}, "gold lists no document"),
    ({"question_id": "a", "question": "X?", "gold": [7]}, "a gold entry is a document id"),
    ({"question_id": "a", "question": "X?", "gold": [{"doc": "d1", "score": 2}]}, "a gold entry is a document id"),
    ({"question_id": "a", "question": "X?", "gold": [{"grade": 2}]}, "a gold entry is a document id"),
    ({"question_id": "a", "question": "X?", "gold": [{"doc": "d1", "grade": True}]}, "grade must be an integer"),
    ({"question_id": "a", "question": "X?", "gold": [{"doc": "d1", "grade": 1.0}]}, "grade must be an integer"),
    ({"question_id": "a", "question": "X?", "gold": {"d1": 9}}, "outside 0 to 3"),
    ({"question_id": "a", "question": "X?", "gold": {"d1": "2"}}, "grade must be an integer"),
    ({"question_id": "a", "question": "X?", "gold": ["d1", "d1"]}, "listed twice"),
    ({"question_id": "a", "question": "X?", "gold": {"d1": 0}}, "no gold document has a grade above 0"),
    ({"question_id": "a", "question": "X?", "gold": ["nope"]}, "not in the corpus"),
])
def test_jsonl_problems_are_named_with_their_line(line, expected):
    assert any(expected in p for p in problems_of(lambda: R.parse_questions_jsonl(_jl(line), set(DOCS))))


def test_jsonl_duplicate_ids_and_empty_files_are_refused():
    one = {"question_id": "a", "question": "X?", "gold": ["d1"]}
    assert any("used twice" in p for p in problems_of(lambda: R.parse_questions_jsonl(_jl(one, one))))
    assert any("no question" in p for p in problems_of(lambda: R.parse_questions_jsonl("\n\n")))


def test_load_questions_picks_the_format_by_extension_and_refuses_the_rest(tmp_path):
    (tmp_path / "q.jsonl").write_text(_jl({"question_id": "a", "question": "X?", "gold": ["d1"]}), encoding="utf-8")
    assert R.load_questions(tmp_path / "q.jsonl")[0].id == "a"
    (tmp_path / "q.txt").write_text("x", encoding="utf-8")
    assert any("extension" in p for p in problems_of(lambda: R.load_questions(tmp_path / "q.txt")))
    assert any("does not exist" in p for p in problems_of(lambda: R.load_questions(tmp_path / "missing.csv")))
    (tmp_path / "bad.csv").write_bytes(b"question_id,question,gold\nq1,\xff\xfe,d1\n")
    assert any("UTF-8" in p for p in problems_of(lambda: R.load_questions(tmp_path / "bad.csv")))


def test_the_same_questions_in_both_formats_are_the_same_questions():
    csv_q = R.parse_questions_csv(GOOD_CSV, set(DOCS))
    jsonl = _jl({"question_id": "q1", "question": "Which fruit grows on trees?", "gold": {"d1": 1, "d2": 2, "d5": 0}},
                {"question_id": "q2", "question": "What floats, and where?", "gold": ["d3"]})
    assert R.parse_questions_jsonl(jsonl, set(DOCS)) == csv_q
    assert [R.content_sha256(q) for q in csv_q] == [R.content_sha256(q) for q in R.parse_questions_jsonl(jsonl)]


def test_checksum_covers_question_and_gold_and_ignores_order():
    a = R.Question("q", "Text?", {"d1": 1, "d2": 2})
    assert R.content_sha256(a) == R.content_sha256(R.Question("q", "Text?", {"d2": 2, "d1": 1}))
    assert R.content_sha256(a) != R.content_sha256(R.Question("q", "Text?", {"d1": 2, "d2": 2}))
    assert R.content_sha256(a) != R.content_sha256(R.Question("q", "Other?", {"d1": 1, "d2": 2}))
    assert R.content_sha256(a) != R.content_sha256(R.Question("q", "Text?", {"d1": 1}))


# -- corpus files ------------------------------------------------------------------

def _docs_text(docs=DOCS):
    return "".join(json.dumps({"id": k, "text": v}) + "\n" for k, v in docs.items())


def test_documents_and_edges_are_read_strictly():
    docs = R.parse_documents(_docs_text())
    assert docs == DOCS
    edges = R.parse_edges("src,dst,type\nd1,d2,cites\nd2,d3,related_to\n", docs)
    assert edges == [("d1", "d2", "cites"), ("d2", "d3", "related_to")]


@pytest.mark.parametrize("text, expected", [
    ("", "no document"),
    ("{bad\n", "not valid JSON"),
    ('{"id": "a"}\n', "exactly the keys id and text"),
    ('{"id": "a", "text": "x", "more": 1}\n', "exactly the keys id and text"),
    ('{"id": "a b", "text": "x"}\n', "not a document id"),
    ('{"id": "a", "text": " "}\n', "has no text"),
    ('{"id": "a", "text": "x"}\n{"id": "a", "text": "y"}\n', "appears twice"),
])
def test_bad_documents_are_refused(text, expected):
    assert any(expected in p for p in problems_of(lambda: R.parse_documents(text)))


@pytest.mark.parametrize("text, expected", [
    ("a,b,c\nd1,d2,cites\n", "header must be exactly src,dst,type"),
    ("src,dst,type\nd1,d2\n", "2 field(s), 3 are needed"),
    ("src,dst,type\nd1,zz,cites\n", "not in the corpus"),
    ("src,dst,type\nd1,d1,cites\n", "joined to itself"),
    ("src,dst,type\nd1,d2,Cites\n", "not an edge type"),
    ("src,dst,type\nd1,d2,cites\nd1,d2,cites\n", "appears twice"),
])
def test_bad_edges_are_refused(text, expected):
    assert any(expected in p for p in problems_of(lambda: R.parse_edges(text, DOCS)))


def test_neighbours_follow_direction_and_type():
    corpus = R.Corpus("c", DOCS, [("d1", "d2", "cites"), ("d3", "d1", "related_to"), ("d1", "d4", "cites")])
    assert corpus.neighbours("d1") == [("d2", "cites"), ("d3", "related_to"), ("d4", "cites")]
    assert corpus.neighbours("d1", direction="out") == [("d2", "cites"), ("d4", "cites")]
    assert corpus.neighbours("d1", direction="in") == [("d3", "related_to")]
    assert corpus.neighbours("d1", ["related_to"]) == [("d3", "related_to")]
    assert corpus.neighbours("d5") == []
    assert corpus.edge_types() == {"cites", "related_to"}


# -- the ranking --------------------------------------------------------------------

VEC = {"a": [1.0, 0.0], "b": [0.6, 0.8], "c": [0.0, 1.0], "d": [-0.6, 0.8], "e": [0.8, 0.6]}
Q = [1.0, 0.0]  # scores: a 1.0, e 0.8, b 0.6, c 0.0, d -0.6


def _corpus(edges):
    return R.Corpus("c", {k: k for k in VEC}, edges)


def test_embeddings_alone_rank_by_score_with_ties_by_id():
    ranking = R.retrieve(_corpus([]), VEC, Q)
    assert [e["doc"] for e in ranking] == ["a", "e", "b", "c", "d"]
    assert {e["via"] for e in ranking} == {"embedding"}
    assert ranking[0]["score"] == 1.0 and ranking[1]["score"] == pytest.approx(0.8)
    tied = {"y": [0.0, 1.0], "x": [0.0, 1.0], "z": [1.0, 0.0]}
    assert [e["doc"] for e in R.retrieve(_corpus([]), tied, Q)] == ["z", "x", "y"]


def test_depth_cuts_the_ranking():
    assert [e["doc"] for e in R.retrieve(_corpus([]), VEC, Q, depth=2)] == ["a", "e"]


def test_expansion_lifts_a_neighbour_of_the_best_documents():
    # a (1.0) is a seed; its neighbour d is reached at 0.5 x 1.0 = 0.5, below b (0.6) but above c (0.0)
    ranking = R.retrieve(_corpus([("a", "d", "cites")]), VEC, Q, R.Expansion(seed_k=1))
    assert [e["doc"] for e in ranking] == ["a", "e", "b", "d", "c"]
    by_doc = {e["doc"]: e for e in ranking}
    assert by_doc["d"]["via"] == "expansion:cites" and by_doc["d"]["score"] == 0.5
    assert by_doc["a"]["via"] == "embedding"


def test_expansion_only_starts_from_the_best_seed_k_documents():
    edges = [("c", "d", "cites")]  # c scores 0.0 and is not among the 2 best: nothing is expanded from it
    ranking = R.retrieve(_corpus(edges), VEC, Q, R.Expansion(seed_k=2))
    assert [e["doc"] for e in ranking] == ["a", "e", "b", "c", "d"]
    assert all(e["via"] == "embedding" for e in ranking)


def test_a_document_keeps_the_higher_of_its_own_and_its_expanded_score():
    ranking = R.retrieve(_corpus([("a", "e", "cites")]), VEC, Q, R.Expansion(seed_k=1))  # 0.5 < own 0.8
    by_doc = {e["doc"]: e for e in ranking}
    assert by_doc["e"]["via"] == "embedding" and by_doc["e"]["score"] == pytest.approx(0.8)
    tie = R.retrieve(_corpus([("a", "b", "cites")]), {"a": [1.0, 0.0], "b": [0.5, 0.0]}, Q, R.Expansion(seed_k=1))
    assert {e["doc"]: e["via"] for e in tie}["b"] == "embedding"  # 0.5 = 0.5: the document's own score wins a tie


def test_expansion_can_be_limited_to_chosen_edge_types_and_directions():
    edges = [("a", "d", "cites"), ("c", "a", "related_to")]
    only_related = R.retrieve(_corpus(edges), VEC, Q, R.Expansion(seed_k=1, edge_types=("related_to",)))
    assert {e["doc"]: e["via"] for e in only_related}["c"] == "expansion:related_to"  # 0.5 beats c's own 0.0
    assert {e["doc"]: e["via"] for e in only_related}["d"] == "embedding"
    out_only = R.retrieve(_corpus(edges), VEC, Q, R.Expansion(seed_k=1, direction="out"))
    assert {e["doc"]: e["via"] for e in out_only}["d"] == "expansion:cites"
    assert {e["doc"]: e["via"] for e in out_only}["c"] == "embedding"
    in_only = R.retrieve(_corpus(edges), VEC, Q, R.Expansion(seed_k=1, direction="in"))
    assert {e["doc"]: e["via"] for e in in_only}["c"] == "expansion:related_to"
    assert {e["doc"]: e["via"] for e in in_only}["d"] == "embedding"


def test_expansion_hops_multiply_the_decay():
    edges = [("a", "c", "cites"), ("c", "d", "cites")]
    one = {e["doc"]: e for e in R.retrieve(_corpus(edges), VEC, Q, R.Expansion(seed_k=1, hops=1))}
    two = {e["doc"]: e for e in R.retrieve(_corpus(edges), VEC, Q, R.Expansion(seed_k=1, hops=2, decay=0.5))}
    assert one["c"]["score"] == 0.5 and one["d"]["score"] == pytest.approx(-0.6) and one["d"]["via"] == "embedding"
    assert two["d"]["score"] == 0.25 and two["d"]["via"] == "expansion:cites"


def test_expansion_is_deterministic_whatever_the_order_of_the_edges():
    edges = [("a", "c", "cites"), ("b", "c", "related_to"), ("a", "d", "cites")]
    exp = R.Expansion(seed_k=3)
    assert R.retrieve(_corpus(edges), VEC, Q, exp) == R.retrieve(_corpus(list(reversed(edges))), VEC, Q, exp)


def test_a_question_and_documents_of_different_dimensions_are_refused():
    with pytest.raises(ValueError, match="dimensions"):
        R.retrieve(_corpus([]), VEC, [1.0, 0.0, 0.0])


# -- offline embedders ----------------------------------------------------------------

def test_offline_embedders_are_deterministic_unit_vectors_that_reward_shared_words():
    embed = R.OFFLINE_EMBEDDERS["toy-hash-64"]
    one, two = embed(["red apples grow"]), embed(["red apples grow"])
    assert one == two and len(one[0]) == 64
    assert sum(x * x for x in one[0]) == pytest.approx(1.0)
    q, near, far = embed(["apples grow"])[0], embed(["red apples grow on trees"])[0], embed(["blue boats float"])[0]
    assert sum(a * b for a, b in zip(q, near)) > sum(a * b for a, b in zip(q, far))
    assert len(R.OFFLINE_EMBEDDERS["toy-hash-16"](["x"])[0]) == 16
    assert embed(["the of and"])[0] == [0.0] * 64  # only common words: nothing to embed, no division by zero


# -- configurations -------------------------------------------------------------------

def test_config_settings_defaults():
    s = R.config_settings(None)
    assert (s.text, s.depth, s.expansion) == ("abstract", 100, None)
    e = R.config_settings({"expansion": {}}).expansion
    assert (e.seed_k, e.hops, e.decay, e.direction, e.edge_types) == (5, 1, 0.5, "both", None)
    assert R.config_settings({}, {"text": "summary"}).text == "summary"
    assert R.config_settings({"text": "abstract"}, {"text": "summary"}).text == "abstract"


def test_config_settings_reads_an_expansion():
    s = R.config_settings({"depth": 20, "expansion": {"seed_k": 3, "hops": 2, "decay": 1, "direction": "out",
                                                      "edge_types": ["cites", "related_to"]}})
    assert s.expansion == R.Expansion(3, 2, 1.0, "out", ("cites", "related_to")) and s.depth == 20


@pytest.mark.parametrize("params, message", [
    ({"typo": 1}, "unknown params typo"),
    ({"text": "body"}, "text must be one of"),
    ({"depth": 9}, "depth must be an integer from 10"), ({"depth": 1001}, "depth must be"),
    ({"depth": True}, "depth must be"), ({"depth": 10.0}, "depth must be"),
    ({"expansion": "graph"}, "must be a mapping or null"),
    ({"expansion": {"seeds": 2}}, "unknown expansion params seeds"),
    ({"expansion": {"decay": 0}}, "decay must be"), ({"expansion": {"decay": 1.5}}, "decay must be"),
    ({"expansion": {"decay": True}}, "decay must be"), ({"expansion": {"decay": "0.5"}}, "decay must be"),
    ({"expansion": {"direction": "up"}}, "direction must be"),
    ({"expansion": {"hops": 0}}, "hops must be"), ({"expansion": {"hops": 4}}, "hops must be"),
    ({"expansion": {"seed_k": 0}}, "seed_k must be"), ({"depth": 10, "expansion": {"seed_k": 11}}, "seed_k must be"),
    ({"expansion": {"edge_types": []}}, "non-empty list"), ({"expansion": {"edge_types": "cites"}}, "non-empty list"),
    ({"expansion": {"edge_types": ["cites", "cites"]}}, "distinct"),
    ({"expansion": {"edge_types": ["Cites"]}}, "non-empty list"), ({"expansion": {"edge_types": [1]}}, "non-empty list"),
])
def test_config_settings_refuses_what_it_does_not_know(params, message):
    with pytest.raises(ValueError, match=message):
        R.config_settings(params)


# -- spec validation -------------------------------------------------------------------

def make_root(tmp_path, *, questions_a=None, questions_b=None, edges="src,dst,type\nd1,d2,cites\nd3,d4,related_to\n"):
    base = tmp_path / "lab" / "corpora" / "c1"
    base.mkdir(parents=True)
    (base / "documents.jsonl").write_text(_docs_text(), encoding="utf-8")
    if edges is not None:
        (base / "edges.csv").write_text(edges, encoding="utf-8")
    (base / "questions-a.csv").write_text(questions_a or "question_id,question,gold\nq1,Which fruit?,d1;d2:2\n"
                                          "q2,Which boat?,d3\n", encoding="utf-8")
    (base / "questions-b.csv").write_text(questions_b or "question_id,question,gold\nq3,Which car?,d4\n",
                                          encoding="utf-8")
    return tmp_path


def good_spec():
    return {"slug": "my-retrieval", "kind": "retrieval", "title": "T", "hypothesis": None,
            "params": {"corpus": "c1", "index": "files", "recall_k": [5, 10], "bootstrap_seed": 7,
                       "baseline": "embeddings"},
            "configs": [
                {"name": "embeddings", "model": "toy-hash-64", "provider": "none"},
                {"name": "graph-cites", "model": "toy-hash-64", "provider": "none",
                 "params": {"expansion": {"seed_k": 3, "edge_types": ["cites"]}}},
                {"name": "other-model", "model": "toy-hash-16", "provider": "none"},
                {"name": "real-model", "model": "bge-m3", "provider": "local"}],
            "samples": [
                {"name": "tuning-2", "role": "tuning", "seed": 0, "method": "by hand",
                 "items": "lab/corpora/c1/questions-a.csv"},
                {"name": "test-1", "role": "test", "seed": 0, "method": "by hand",
                 "items": "lab/corpora/c1/questions-b.csv"}]}


def check(spec, root):
    return R.check_spec(spec, root=root, models=MODELS)


def test_a_good_spec_has_no_problems(tmp_path):
    assert check(good_spec(), make_root(tmp_path)) == []


def test_the_toy_spec_of_the_repository_is_valid_and_specs_load_checks_it():
    path = ROOT / "lab" / "experiments" / "toy-retrieval.yaml"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert R.check_spec(spec) == []
    assert specs.load(path)["slug"] == "toy-retrieval"


def _mutate(spec, fn):
    spec = copy.deepcopy(spec)
    fn(spec)
    return spec


@pytest.mark.parametrize("fn, expected", [
    (lambda s: s.update(kind="claims"), "kind must be 'retrieval'"),
    (lambda s: s.update(slug="Bad_Slug"), "slug must be"),
    (lambda s: s["params"].update(corpus="nope"), "corpus nope"),
    (lambda s: s["params"].update(corpus="Bad Name"), "params.corpus must name a folder"),
    (lambda s: s["params"].update(index="sql"), "params.index must be one of"),
    (lambda s: s["params"].update(typo=1), "params: unknown typo"),
    (lambda s: s["params"].update(recall_k=0), "k must be"),
    (lambda s: s["params"].update(bootstrap_seed="x"), "bootstrap_seed"),
    (lambda s: s["params"].update(baseline="missing"), "params.baseline 'missing' is not a configuration"),
    (lambda s: s.update(params=[1]), "params must be a mapping"),
    (lambda s: s.update(configs=[]), "at least one configuration"),
    (lambda s: s["configs"].append(dict(s["configs"][0])), "the name is used twice"),
    (lambda s: s["configs"][0].update(name="Graph_All"), "name must be lower-case letters, digits and '-'"),
    (lambda s: s["configs"][0].update(name="a.b"), "name must be lower-case letters, digits and '-'"),
    (lambda s: s["configs"][0].update(extra=1), "unknown keys extra"),
    (lambda s: s["configs"][0].pop("model"), "model (the embedding model) is required"),
    (lambda s: s["configs"][0].update(model="not-registered"), "not in lab/models.yaml"),
    (lambda s: s["configs"][0].update(provider="local"), "provider must be 'none'"),
    (lambda s: s["configs"][3].update(provider="none"), "provider must be 'local'"),
    (lambda s: s["configs"][3].update(model="hosted-embed", provider="remote"), "may be used only in other-experiment"),
    (lambda s: s["configs"][1]["params"]["expansion"].update(decay=2), "decay must be"),
    (lambda s: s["configs"][1]["params"]["expansion"].update(edge_types=["mentions"]), "no edge of type mentions"),
    (lambda s: s["configs"][1].update(params={"depth": 10}) or s["params"].update(recall_k=[20]),
     "depth 10 is below the recall cutoff 20"),
    (lambda s: s.update(samples=[]), "at least one sample"),
    (lambda s: s["samples"][0].update(name="Sample_A"), "name must be lower-case"),
    (lambda s: s["samples"][1].update(name="tuning-2"), "the name is used twice"),
    (lambda s: s["samples"][0].update(role="train"), "role must be one of"),
    (lambda s: s["samples"][0].update(role="control"), "a control sample belongs to a hypothesis"),
    (lambda s: s["samples"][0].update(seed="0"), "seed must be an integer"),
    (lambda s: s["samples"][0].update(method=" "), "method (how the questions were chosen) is required"),
    (lambda s: s["samples"][0].pop("items"), "the question set file is required"),
    (lambda s: s["samples"][0].update(items="lab/corpora/other/questions-a.csv"), "directly in lab/corpora/c1/"),
    (lambda s: s["samples"][0].update(items="lab/corpora/c1/../c1/questions-a.csv"), "directly in lab/corpora/c1/"),
    (lambda s: s["samples"][0].update(items="lab/corpora/c1/sub/q.csv"), "directly in lab/corpora/c1/"),
    (lambda s: s["samples"][0].update(items="lab/corpora/c1/missing.csv"), "the file does not exist"),
    (lambda s: s["samples"][0].update(items="lab/corpora/c1/documents.jsonl"), "exactly the keys"),
    (lambda s: s["samples"][1].update(items="lab/corpora/c1/questions-a.csv"), "is also in sample tuning-2"),
])
def test_spec_problems_are_named(tmp_path, fn, expected):
    problems = check(_mutate(good_spec(), fn), make_root(tmp_path))
    assert any(expected in p for p in problems), problems


def test_a_hosted_model_is_allowed_only_where_the_registry_lists_the_experiment(tmp_path):
    spec = _mutate(good_spec(), lambda s: s["configs"][3].update(model="hosted-embed", provider="remote"))
    spec["slug"] = "other-experiment"
    assert check(spec, make_root(tmp_path)) == []
    spec["configs"][3]["provider"] = "local"
    assert any("provider must be 'remote'" in p for p in check(spec, tmp_path))


def test_a_control_sample_needs_a_hypothesis_and_is_fine_with_one(tmp_path):
    spec = _mutate(good_spec(), lambda s: s["samples"][1].update(role="control"))
    assert any("belongs to a hypothesis" in p for p in check(spec, make_root(tmp_path)))
    spec["hypothesis"] = {"slug": "h", "version": 1}
    assert check(spec, tmp_path) == []


def test_bad_question_sets_and_gold_ids_stop_the_spec(tmp_path):
    root = make_root(tmp_path, questions_a="question_id,question,gold\nq1,Which fruit?,d1;d2\nq1,Again?,d2\nq2,Which?,d3;zz\n")
    problems = check(good_spec(), root)
    assert any("sample tuning-2, lab/corpora/c1/questions-a.csv: line 4: document 'zz' is not in the corpus" in p
               for p in problems)
    assert any("line 3: question_id 'q1' is used twice" in p for p in problems)


def test_a_corpus_without_documents_or_with_bad_edges_stops_the_spec(tmp_path):
    root = make_root(tmp_path, edges="src,dst,type\nd1,zz,cites\n")
    assert any("corpus c1: line 2" in p and "not in the corpus" in p for p in check(good_spec(), root))
    (root / "lab/corpora/c1/documents.jsonl").unlink()
    assert any("cannot read its documents" in p for p in check(good_spec(), root))


def test_the_graph_index_needs_a_manifest_to_check_gold_ids(tmp_path):
    spec = _mutate(good_spec(), lambda s: s["params"].update(index="graph"))
    root = make_root(tmp_path)
    assert any("cannot read its documents" in p for p in check(spec, root))
    (root / "lab/corpora/c1/manifest.csv").write_text("arxiv_id,stratum\nd1,x\nd2,x\nd3,x\nd4,x\n", encoding="utf-8")
    graph_problems = check(spec, root)
    assert graph_problems == [] or all("no edge of type" not in p for p in graph_problems)
    (root / "lab/corpora/c1/manifest.csv").write_text("arxiv_id,stratum\nd1,x\n", encoding="utf-8")
    assert any("'d3' is not in the corpus" in p for p in check(spec, root))


def test_setup_members_are_the_questions_with_checksums_and_gold(tmp_path):
    root = make_root(tmp_path)
    spec = good_spec()
    members = specs_members(spec, spec["samples"][0], root)
    assert [m["item_id"] for m in members] == ["q1", "q2"]
    assert members[0]["payload"] == {"question": "Which fruit?", "gold": {"d1": 1, "d2": 2}}
    assert members[0]["content_sha256"] == R.content_sha256(R.Question("q1", "Which fruit?", {"d1": 1, "d2": 2}))
    assert members[0]["stratum"] is None
    # the checksum moves with the gold answers, so a changed answer can never pass for the stored sample
    (root / "lab/corpora/c1/questions-a.csv").write_text(
        "question_id,question,gold\nq1,Which fruit?,d1;d2\nq2,Which boat?,d3\n", encoding="utf-8")
    changed = specs_members(spec, spec["samples"][0], root)
    assert changed[0]["content_sha256"] != members[0]["content_sha256"]
    assert changed[1]["content_sha256"] == members[1]["content_sha256"]


def specs_members(spec, sample, root):
    return R.sample_items(spec, sample, root)


def test_sample_items_refuse_gold_outside_the_corpus(tmp_path):
    root = make_root(tmp_path, questions_a="question_id,question,gold\nq1,Which fruit?,zz\n")
    spec = good_spec()
    assert any("not in the corpus" in p for p in problems_of(lambda: R.sample_items(spec, spec["samples"][0], root)))


# -- registration ------------------------------------------------------------------------

def test_the_kind_is_registered_with_the_queue(monkeypatch):
    from exocortex.lab import claims, toy

    monkeypatch.setattr(toy, "make_runner", lambda conn, tenant: "toy-runner")
    monkeypatch.setattr(claims, "make_runner", lambda conn, tenant: "claims-runner")
    runners = cli.runners(None, "tenant")
    assert set(runners) >= {"toy", "claims", "retrieval"}
    assert callable(runners[R.KIND]) and runners["toy"] == "toy-runner"
    assert R.KIND == "retrieval"


def test_specs_hand_retrieval_samples_to_the_kind_and_others_to_the_corpus_reader(monkeypatch):
    spec = yaml.safe_load((ROOT / "lab/experiments/toy-retrieval.yaml").read_text(encoding="utf-8"))
    members = specs.sample_members(spec, spec["samples"][1])
    assert len(members) == 12 and members[0]["item_id"] == "t01"
    seen = []
    monkeypatch.setattr(specs, "sample_items", lambda s, sample: seen.append(s["kind"]) or ["paper"])
    assert specs.sample_members({"kind": "claims"}, {}) == ["paper"] and seen == ["claims"]


def test_specs_load_refuses_an_invalid_retrieval_spec_with_every_problem(tmp_path):
    spec = good_spec()
    spec["configs"][0]["model"] = "not-registered"
    spec["samples"][0]["items"] = "lab/corpora/nowhere/q.csv"
    path = tmp_path / "s.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    with pytest.raises(R.RetrievalInputError) as info:
        specs.load(path)
    assert len(info.value.problems) >= 3 and info.value.source == str(path)
    assert isinstance(info.value, ValueError)  # callers that only know ValueError still refuse


def test_the_command_line_knows_the_retrieval_command_and_its_instance_names():
    args = cli.build_parser().parse_args(["retrieval", "validate", "--experiment", "toy-retrieval"])
    assert (args.action, args.experiment, args.func) == ("validate", "toy-retrieval", cli._cmd_retrieval)
    assert cli.parse_run_instance("toy-retrieval_test-12_embeddings.graph-cites_queue") == {
        "experiment": "toy-retrieval", "sample": "test-12", "configs": ["embeddings", "graph-cites"], "queue_only": True}


def test_validate_command_reports_ok_and_problems(capsys, tmp_path):
    assert cli.main(["retrieval", "validate", "--experiment", "toy-retrieval"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["questions"] == {"tuning-6": 6, "test-12": 12}
    spec = yaml.safe_load((ROOT / "lab/experiments/toy-retrieval.yaml").read_text(encoding="utf-8"))
    spec["configs"][0]["model"] = "unknown-model"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    assert cli.main(["retrieval", "validate", "--spec", str(path)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and any("not in lab/models.yaml" in p for p in out["problems"])
    assert cli.main(["retrieval", "validate", "--experiment", "no-such-experiment"]) == 2
    assert "refused" in json.loads(capsys.readouterr().out)


# -- the runner, without a database ---------------------------------------------------------

def _job_and_item(question, config, params=None):
    item = {"item_id": question.id, "content_sha256": R.content_sha256(question), "stratum": None,
            "payload": {"question": question.text, "gold": question.gold}}
    return {"config": config, "experiment": {"slug": "x", "kind": "retrieval",
                                             "params": params or {"corpus": "c1", "index": "files"}}}, item


def test_the_runner_ranks_with_offline_models_and_never_reaches_for_the_gateway(tmp_path, monkeypatch):
    import exocortex.lab.llm as llm_module

    monkeypatch.setattr(llm_module, "LabLLM", lambda *a, **k: pytest.fail("the gateway client must not be built"))
    runner = R.make_runner(None, "tenant", root=make_root(tmp_path))
    question = R.Question("q1", "which apples grow on trees", {"d1": 1, "d2": 1})
    job, item = _job_and_item(question, {"name": "e", "model": "toy-hash-64", "provider": "none", "params": {}})
    result = runner(job, item)
    assert result["ok"] is True and result["provider"] == "none" and result["base_url"] is None
    out = result["output"]
    assert out["gold"] == {"d1": 1, "d2": 1} and out["question"] == "q1" and out["documents"] == 5
    assert [e["doc"] for e in out["ranking"]][:2] == ["d1", "d2"] and len(out["ranking"]) == 5
    assert out["expansion"] is None
    assert runner(job, item)["output"] == out  # the same job gives the same ranking


def test_the_runner_expands_along_edges_and_says_so(tmp_path):
    runner = R.make_runner(None, "tenant", root=make_root(tmp_path))
    question = R.Question("q1", "red apples", {"d1": 1, "d2": 1})
    plain, item = _job_and_item(question, {"name": "e", "model": "toy-hash-64", "provider": "none", "params": {}})
    graph, _ = _job_and_item(question, {"name": "g", "model": "toy-hash-64", "provider": "none",
                                        "params": {"expansion": {"seed_k": 1, "edge_types": ["cites"]}}})
    a, b = runner(plain, item)["output"], runner(graph, item)["output"]
    assert b["expansion"] == {"seed_k": 1, "hops": 1, "decay": 0.5, "direction": "both", "edge_types": ["cites"]}
    assert {e["doc"]: e["via"] for e in b["ranking"]}["d2"] == "expansion:cites"  # d1 -> d2 along a cites edge
    assert {e["doc"]: e["via"] for e in a["ranking"]}["d2"] == "embedding"


def test_the_runner_raises_instead_of_guessing(tmp_path):
    runner = R.make_runner(None, "tenant", root=make_root(tmp_path))
    cfg = {"name": "e", "model": "toy-hash-64", "provider": "none", "params": {}}
    good = R.Question("q1", "apples", {"d1": 1})
    job, item = _job_and_item(good, cfg)
    with pytest.raises(RuntimeError, match="does not match the checksum"):
        runner(job, {**item, "payload": {"question": "changed", "gold": {"d1": 1}}})
    job, item = _job_and_item(R.Question("q9", "apples", {"zz": 1}), cfg)
    with pytest.raises(RuntimeError, match="not in corpus c1: zz"):
        runner(job, item)
    job, item = _job_and_item(good, {**cfg, "params": {"expansion": {"edge_types": ["mentions"]}}})
    with pytest.raises(RuntimeError, match="no edge of type mentions"):
        runner(job, item)
    job, item = _job_and_item(good, {**cfg, "params": {"depth": 3}})
    with pytest.raises(ValueError, match="depth must be"):
        runner(job, item)
    job, item = _job_and_item(good, cfg, {"corpus": "missing", "index": "files"})
    with pytest.raises(FileNotFoundError):
        runner(job, item)


def test_a_model_from_the_registry_is_embedded_through_the_gateway_client_only(tmp_path):
    class Gateway:
        url = "unix:/run/lab-llm/gateway.sock"

        def __init__(self):
            self.calls = []

        def embed(self, model, texts):
            self.calls.append((model, list(texts)))
            return [[float(len(t) % 3), float(len(t) % 5), 1.0] for t in texts]

    gateway = Gateway()
    runner = R.make_runner(None, "tenant", llm=gateway, root=make_root(tmp_path))
    question = R.Question("q1", "apples", {"d1": 1})
    job, item = _job_and_item(question, {"name": "r", "model": "bge-m3", "provider": "local", "params": {}})
    result = runner(job, item)
    assert result["base_url"] == gateway.url and result["provider"] == "local" and result["model"] == "bge-m3"
    assert [m for m, _ in gateway.calls] == ["bge-m3", "bge-m3"]  # the documents, then the question
    assert gateway.calls[0][1] == [DOCS[d] for d in sorted(DOCS)] and gateway.calls[1][1] == ["apples"]
    runner(job, item)
    assert len(gateway.calls) == 3  # the documents are embedded once per process, the question every time


def test_the_gateway_client_is_built_lazily_and_a_failed_embedding_fails_the_job(tmp_path, monkeypatch):
    import exocortex.lab.llm as llm_module

    class Broken:
        url = "unix:/x"

        def __init__(self, *a, **k):
            pass

        def embed(self, model, texts):
            raise RuntimeError("gateway down")

    monkeypatch.setattr(llm_module, "LabLLM", Broken)
    runner = R.make_runner(None, "tenant", root=make_root(tmp_path))
    job, item = _job_and_item(R.Question("q1", "apples", {"d1": 1}),
                              {"name": "r", "model": "bge-m3", "provider": "local", "params": {}})
    with pytest.raises(RuntimeError, match="gateway down"):
        runner(job, item)
