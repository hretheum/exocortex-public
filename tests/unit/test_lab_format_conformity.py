# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Experiment kind ``format_conformity`` (roadmap task F5.9): prompt file and schema parsing, the validator, the toy
models, spec validation, the runner and the kind's registration. No database, no network."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import httpx
import pytest
import yaml

from exocortex.lab import cli, specs
from exocortex.lab import format_conformity as F
from exocortex.lab.llm import LabLLM

ROOT = Path(__file__).resolve().parents[2]
TICKET = {"type": "object", "additionalProperties": False, "required": ["category", "priority"],
          "properties": {"category": {"type": "string", "enum": ["billing", "bug"]},
                         "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                         "note": {"type": "string", "minLength": 2, "maxLength": 10, "pattern": "^[a-z ]+$"}}}
TAGS = {"type": "object", "required": ["tags"],
        "properties": {"tags": {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "string"}}}}
MODELS = {"qwen": {"id": "qwen", "family": "qwen"},
          "hosted-chat": {"id": "hosted-chat", "provider": "openai", "data_class": "public",
                          "experiments": ["other-experiment"]}}


def problems_of(call):
    with pytest.raises(F.FormatInputError) as info:
        call()
    return info.value.problems


# -- prompt files: CSV -----------------------------------------------------------------

GOOD_CSV = """item_id,prompt,schema,grammar
a1,Classify the ticket: double charge.,ticket,ticket-gbnf
a2,"Tags for this, please.",tags,
"""


def test_csv_prompt_file_is_read_with_optional_grammar_label():
    items = F.parse_items_csv(GOOD_CSV, {"ticket", "tags"})
    assert [(i.id, i.schema, i.grammar) for i in items] == [("a1", "ticket", "ticket-gbnf"), ("a2", "tags", None)]
    assert items[1].prompt == "Tags for this, please."  # a quoted comma is fine


def test_csv_grammar_column_is_optional_and_the_header_order_is_free(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("\ufeffschema,prompt,item_id\nticket,First?,a\n\n  ,  ,\ntags,Second?,b\n", encoding="utf-8")
    assert [(i.id, i.prompt, i.schema, i.grammar) for i in F.load_items(path)] == [
        ("a", "First?", "ticket", None), ("b", "Second?", "tags", None)]


def test_a_prompt_may_span_lines_and_its_problems_name_the_lines():
    text = 'item_id,prompt,schema\na1,"two\nlines",zz\n'
    found = problems_of(lambda: F.parse_items_csv(text, {"ticket"}))
    assert any(p.startswith("lines 2-3:") and "no file schemas/zz.json" in p for p in found)
    ok = F.parse_items_csv('item_id,prompt,schema\na1,"two\nlines",ticket\n', {"ticket"})
    assert ok[0].prompt == "two\nlines"


@pytest.mark.parametrize("text, expected", [
    ("", "the file is empty"),
    ("item_id,prompt,schema\n", "no item"),
    ("id,prompt,schema\na,b,ticket\n", "the header needs"),
    ("item_id,prompt\na,b\n", "the header needs"),
    ("item_id,prompt,schema,extra\na,b,ticket,x\n", "the header needs"),
    ("item_id,prompt,schema,prompt\na,b,ticket,x\n", "the header needs"),
    ("item_id,prompt,schema\na1,Q?,ticket\na1,R?,tags\n", "line 3: item_id 'a1' is used twice"),
    ("item_id,prompt,schema\n_a,Q?,ticket\n", "item_id must be"),
    ("item_id,prompt,schema\na b,Q?,ticket\n", "item_id must be"),
    ("item_id,prompt,schema\na1,   ,ticket\n", "the prompt is empty"),
    ("item_id,prompt,schema\na1,\"bell\x07\",ticket\n", "control character"),
    ("item_id,prompt,schema\na1,Q?,\n", "schema must be a schema name"),
    ("item_id,prompt,schema\na1,Q?,Ticket\n", "schema must be a schema name"),
    ("item_id,prompt,schema\na1,Q?,nowhere\n", "'nowhere' has no file schemas/nowhere.json"),
    ("item_id,prompt,schema,grammar\na1,Q?,ticket,bad label\n", "grammar must be a label"),
    ("item_id,prompt,schema\na1,Q? and, more,ticket\n", "4 field(s), the header has 3"),
    ("item_id,prompt,schema\na1,Q?\n", "2 field(s), the header has 3"),
    ('item_id,prompt,schema\na1,"Q?,ticket\n', "not valid CSV"),
])
def test_csv_problems_are_named_with_their_line(text, expected):
    assert any(expected in p for p in problems_of(lambda: F.parse_items_csv(text, {"ticket", "tags"})))


def test_a_prompt_longer_than_the_limit_is_refused():
    text = f"item_id,prompt,schema\na1,{'x' * (F.MAX_PROMPT_CHARS + 1)},ticket\n"
    assert any("longer than" in p for p in problems_of(lambda: F.parse_items_csv(text, {"ticket"})))


def test_every_problem_of_a_file_is_reported_at_once():
    text = "item_id,prompt,schema\nq1,X?,zz\nq1,,ticket\nq3,Y?,ticket\nq4,Z?,ticket\n"
    found = problems_of(lambda: F.parse_items_csv(text, {"ticket"}, source="my.csv"))
    assert {p.split(":")[0] for p in found} >= {"line 2", "line 3"} and not any("line 4" in p for p in found)
    error = F.FormatInputError("my.csv", found)
    assert str(error).startswith("my.csv: ") and "\n- line 2" in str(error)


def test_a_long_list_of_problems_is_cut_in_the_message_but_kept_in_full():
    text = "item_id,prompt,schema\n" + "".join(f"q{i},X?,zz\n" for i in range(30))
    error = pytest.raises(F.FormatInputError, F.parse_items_csv, text, {"ticket"}).value
    assert len(error.problems) == 30 and "and 10 more" in str(error)


def test_schema_names_are_not_checked_against_files_when_none_are_given():
    assert F.parse_items_csv("item_id,prompt,schema\nq1,X?,anything-at-all\n")[0].schema == "anything-at-all"


# -- prompt files: JSONL ---------------------------------------------------------------

def _jl(*objs):
    return "\n".join(o if isinstance(o, str) else json.dumps(o) for o in objs) + "\n"


def test_jsonl_prompt_file_is_read():
    text = _jl({"item_id": "a", "prompt": "One?", "schema": "ticket", "grammar": "g1"},
               {"item_id": "b", "prompt": "Two?\nMore.", "schema": "tags"}, "")
    items = F.parse_items_jsonl(text, {"ticket", "tags"})
    assert [(i.id, i.grammar) for i in items] == [("a", "g1"), ("b", None)] and items[1].prompt == "Two?\nMore."


@pytest.mark.parametrize("line, expected", [
    ("not json", "not valid JSON"),
    ("[1, 2]", "an object with the keys"),
    ('{"item_id": "a", "prompt": "Q?"}', "an object with the keys"),
    ('{"item_id": "a", "prompt": "Q?", "schema": "ticket", "extra": 1}', "an object with the keys"),
    ('{"item_id": 7, "prompt": "Q?", "schema": "ticket"}', "item_id must be"),
    ('{"item_id": "a", "prompt": 7, "schema": "ticket"}', "the prompt is empty"),
    ('{"item_id": "a", "prompt": "Q?", "schema": "ticket", "grammar": 3}', "grammar must be a label"),
    ('{"item_id": "a", "prompt": "Q?", "schema": "zz"}', "no file schemas/zz.json"),
])
def test_jsonl_problems_are_named_with_their_line(line, expected):
    found = problems_of(lambda: F.parse_items_jsonl(_jl('{"item_id": "ok", "prompt": "Q?", "schema": "ticket"}', line),
                                                    {"ticket"}))
    assert any(p.startswith("line 2:") and expected in p for p in found) and not any("line 1:" in p for p in found)


def test_load_items_picks_the_format_by_extension_and_refuses_the_rest(tmp_path):
    (tmp_path / "p.txt").write_text(GOOD_CSV, encoding="utf-8")
    assert any("extension must be" in p for p in problems_of(lambda: F.load_items(tmp_path / "p.txt")))
    assert any("does not exist" in p for p in problems_of(lambda: F.load_items(tmp_path / "missing.csv")))
    (tmp_path / "bad.csv").write_bytes(b"item_id,prompt,schema\na,\xff\xfe,ticket\n")
    assert any("not UTF-8" in p for p in problems_of(lambda: F.load_items(tmp_path / "bad.csv")))


def test_the_same_items_in_both_formats_are_the_same_items(tmp_path):
    (tmp_path / "p.csv").write_text(GOOD_CSV, encoding="utf-8")
    (tmp_path / "p.jsonl").write_text(_jl({"item_id": "a1", "prompt": "Classify the ticket: double charge.",
                                          "schema": "ticket", "grammar": "ticket-gbnf"},
                                         {"item_id": "a2", "prompt": "Tags for this, please.", "schema": "tags"}),
                                     encoding="utf-8")
    assert F.load_items(tmp_path / "p.csv") == F.load_items(tmp_path / "p.jsonl")


def test_checksum_covers_prompt_schema_its_content_and_grammar_label():
    base = F.Item("a", "Q?", "ticket", "g")
    digest = F.sha256_of(TICKET)
    sha = F.content_sha256(base, digest)
    assert sha == F.content_sha256(F.Item("a", "Q?", "ticket", "g"), digest)
    for other in (F.Item("a", "R?", "ticket", "g"), F.Item("a", "Q?", "tags", "g"), F.Item("a", "Q?", "ticket", None)):
        assert F.content_sha256(other, digest) != sha
    assert F.content_sha256(base, F.sha256_of({**TICKET, "required": []})) != sha


# -- schemas ---------------------------------------------------------------------------

def test_a_good_schema_is_read_and_its_key_order_does_not_change_its_checksum():
    assert F.parse_schema(json.dumps(TICKET)) == TICKET
    shuffled = dict(reversed(list(TICKET.items())))
    assert F.sha256_of(shuffled) == F.sha256_of(TICKET)


@pytest.mark.parametrize("text, expected", [
    ("{", "line 1: not valid JSON"),
    ("[]", "must be a JSON object"),
    ('{"type": "object", "type": "string"}', "a key is repeated: type"),
    ('{"type": "objekt"}', "not a valid JSON Schema"),
    ('{"type": "object", "minimum": "x"}', "not a valid JSON Schema"),
    ('{"type": "object", "requird": ["a"]}', "keyword 'requird' is not supported"),
    ('{"anyOf": [{"type": "string"}]}', "keyword 'anyOf' is not supported"),
    ('{"$ref": "https://example.com/s.json"}', "keyword '$ref' is not supported"),
    ('{"type": "object", "properties": {"a": {"type": "string", "format": "email"}}}',
     "/properties/a: keyword 'format' is not supported"),
    ('{"type": "array", "items": {"type": "string", "uniqueItems": true}}', "/items: keyword 'uniqueItems'"),
    ('{"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"}', "$schema may only be"),
    ('{"type": "object", "properties": {"a": {"$schema": "https://json-schema.org/draft/2020-12/schema"}}}',
     "$schema may only be"),
    ('{"type": "string", "pattern": "("}', "not a valid JSON Schema"),
    ('{"type": "NaN"}', "not a valid JSON Schema"),
    ('{"minimum": NaN}', "not valid JSON"),
])
def test_schema_problems_are_named(text, expected):
    assert any(expected in p for p in problems_of(lambda: F.parse_schema(text, "s.json")))


def test_the_claims_extractors_own_schemas_fit_the_supported_subset():
    from exocortex.lab import extractor

    for schema in (extractor.output_schema("baseline"), extractor.output_schema("mode"), extractor.JUDGE_SCHEMA):
        assert F.parse_schema(json.dumps(schema)) == schema  # F5.7 can force the extractor's real answer formats


def test_a_pattern_that_does_not_compile_is_caught_even_where_the_meta_schema_check_lets_it_pass():
    problems: list[str] = []
    F._subset_problems({"type": "string", "pattern": "("}, "", problems)
    assert problems and "pattern does not compile" in problems[0]


def test_a_property_may_be_named_like_a_keyword_and_annotations_are_allowed():
    schema = {"$schema": F.DRAFT, "title": "t", "description": "d", "$comment": "c", "type": "object",
              "properties": {"type": {"type": "string"}, "pattern": {"type": "integer"}, "enum": {"type": "null"}}}
    assert F.parse_schema(json.dumps(schema)) == schema


def test_load_schema_reads_the_corpus_folder_and_reports_a_missing_or_broken_file(tmp_path):
    root = make_root(tmp_path)
    schema, digest = F.load_schema("c1", "ticket", root)
    assert schema == TICKET and digest == F.sha256_of(TICKET)
    assert any("no schema 'nope'" in p for p in problems_of(lambda: F.load_schema("c1", "nope", root)))
    (root / "lab/corpora/c1/schemas/broken.json").write_text('{"requird": []}', encoding="utf-8")
    found, problems = F.load_schemas("c1", root)
    assert set(found) == {"ticket", "tags"} and any("schemas/broken.json" in p and "requird" in p for p in problems)
    (root / "lab/corpora/c1/schemas/Bad_Name.json").write_text("{}", encoding="utf-8")
    assert any("Bad_Name.json: the name must be" in p for p in F.load_schemas("c1", root)[1])


# -- the validator ---------------------------------------------------------------------

def codes(text, schema=TICKET, finish=None):
    verdict, reasons = F.judge(text, schema, finish)
    return verdict, sorted({r["code"] for r in reasons})


OK = '{"category": "bug", "priority": 3}'


def test_a_matching_answer_conforms_whatever_white_space_surrounds_it():
    assert F.judge(OK, TICKET) == ("conforming", [])
    assert F.judge(f"\n  {OK} \n\n", TICKET) == ("conforming", [])
    assert F.judge('{"category": "bug", "priority": 3.0, "note": "hello"}', TICKET)[0] == "conforming"  # 3.0 is an integer


@pytest.mark.parametrize("text, finish, expected", [
    ("Sure, the ticket is about billing and looks urgent.", None, "not_json"),
    ("", None, None),
    (f"Here is the answer:\n{OK}", None, "text_around_json"),
    (f"{OK}\nHope that helps!", None, "text_around_json"),
    (f"```json\n{OK}\n```", None, "code_fence"),
    (f"```\n{OK}\n```", None, "code_fence"),
    (f"  ```JSON {OK} ```  ", None, "code_fence"),
    ('{"category": "bug", "prio', "length", "truncated"),
    ('{"category": "bug", "prio', None, "not_json"),
    ('{"category": "bug", "priority": NaN}', None, "non_finite_number"),
    ('{"category": "bug", "priority": Infinity}', None, "non_finite_number"),
    ('{"category": "bug", "priority": 1e999}', None, "non_finite_number"),
    ("```json\nnot json at all\n```", None, "not_json"),
    ("'{\"category\": \"bug\"}'", None, "text_around_json"),
    ("{'category': 'bug', 'priority': 3}", None, "not_json"),
    ('{"category": "bug", "priority": 3,}', None, "not_json"),
    ("\ufeff" + OK, None, "text_around_json"),  # json.loads refuses a byte order mark: it is text before the JSON
])
def test_an_answer_that_is_not_one_json_value_says_how(text, finish, expected):
    verdict, reasons = F.judge(text, TICKET, finish)
    if expected is None:
        assert (verdict, reasons) == ("no_answer", [])
    else:
        assert verdict == "non_conforming" and [r["code"] for r in reasons] == [expected]
        assert reasons[0]["path"] == "" and reasons[0]["detail"]


def test_a_complete_answer_cut_off_exactly_at_the_token_limit_still_conforms():
    assert F.judge(OK, TICKET, "length") == ("conforming", [])


def test_a_whitespace_only_reply_is_no_answer():
    assert F.judge("   \n\t ", TICKET) == ("no_answer", [])


@pytest.mark.parametrize("text, expected", [
    ('{"category": "bug"}', ["missing_field"]),
    ('{"priority": 2}', ["missing_field"]),
    ('{}', ["missing_field"]),
    ('{"category": "bug", "priority": 3, "colour": "red"}', ["extra_field"]),
    ('{"category": "bug", "priority": "3"}', ["wrong_type"]),
    ('{"category": "bug", "priority": 3.5}', ["wrong_type"]),
    ('{"category": "bug", "priority": true}', ["wrong_type"]),
    ('{"category": null, "priority": 3}', ["bad_value", "wrong_type"]),
    ('{"category": "sales", "priority": 3}', ["bad_value"]),
    ('{"category": "bug", "priority": 0}', ["out_of_range"]),
    ('{"category": "bug", "priority": 6}', ["out_of_range"]),
    ('{"category": "bug", "priority": 3, "note": "x"}', ["bad_length"]),
    ('{"category": "bug", "priority": 3, "note": "Far too long a note!"}', ["bad_length", "bad_pattern"]),
    ('{"category": "bug", "priority": 3, "note": "NOPE"}', ["bad_pattern"]),
    ('["bug", 3]', ["wrong_type"]),
    ('"bug"', ["wrong_type"]),
    ('null', ["wrong_type"]),
    ('{"category": "bug", "priority": 3, "category": "bug"}', ["duplicate_key"]),
])
def test_a_json_value_that_breaks_the_schema_names_each_violation(text, expected):
    verdict, found = codes(text)
    assert verdict == "non_conforming" and found == sorted(expected)


def test_a_reason_has_the_pointer_of_the_place_and_a_detail():
    reasons = F.judge('{"tags": [1, "a", 2, "b"]}', TAGS)[1]
    assert [(r["code"], r["path"]) for r in reasons] == [("bad_length", "/tags"), ("wrong_type", "/tags/0"),
                                                          ("wrong_type", "/tags/2")]
    assert reasons[1]["detail"] == "expected string, got integer"
    missing = F.judge('{"category": "bug"}', TICKET)[1]
    assert missing == [{"code": "missing_field", "path": "", "detail": "missing 'priority'"}]
    extra = F.judge('{"category": "bug", "priority": 1, "b": 1, "a": 2}', TICKET)[1]
    assert extra[0]["detail"] == "unexpected 'a', 'b'"


def test_pointers_escape_slashes_and_tildes():
    schema = {"type": "object", "properties": {"a/b": {"type": "string"}, "c~d": {"type": "string"}}}
    assert [r["path"] for r in F.judge('{"a/b": 1, "c~d": 2}', schema)[1]] == ["/a~1b", "/c~0d"]


def test_bool_is_not_an_integer_and_an_enum_tells_true_from_one():
    schema = {"type": "object", "properties": {"n": {"enum": [1, 2]}, "b": {"const": True}}}
    assert codes('{"n": 1, "b": true}', schema) == ("conforming", [])
    assert codes('{"n": 1.0, "b": true}', schema) == ("conforming", [])
    assert codes('{"n": true, "b": 1}', schema) == ("non_conforming", ["bad_value"])


def test_several_problems_in_one_answer_are_all_reported_and_the_list_is_capped():
    assert codes('{"category": "sales", "priority": 9, "colour": 1}') == (
        "non_conforming", ["bad_value", "extra_field", "out_of_range"])
    schema = {"type": "array", "items": {"type": "string"}}
    reasons = F.judge(json.dumps(list(range(200))), schema)[1]
    assert len(reasons) == F.MAX_REASONS


def test_a_deeply_nested_answer_is_not_json_rather_than_a_crash():
    assert codes("[" * 100000 + "]" * 100000) == ("non_conforming", ["not_json"])


def test_nested_objects_and_additional_properties_as_a_schema_are_checked():
    schema = {"type": "object", "additionalProperties": {"type": "integer"},
              "properties": {"name": {"type": "string"}}}
    assert codes('{"name": "x", "a": 1, "b": 2}', schema) == ("conforming", [])
    assert codes('{"name": "x", "a": "1"}', schema) == ("non_conforming", ["wrong_type"])
    deep = {"type": "object", "required": ["a"], "properties": {"a": {"type": "object", "required": ["b"]}}}
    assert F.judge('{"a": {}}', deep)[1][0]["path"] == "/a"


# -- toy models ------------------------------------------------------------------------

def test_example_values_match_their_schemas_for_every_supported_shape():
    shapes = [TICKET, TAGS, {"type": "number", "minimum": 0.5, "maximum": 0.75}, {"type": "boolean"},
              {"type": "null"}, {"enum": ["a", "b"]}, {"const": 5}, {"type": "string", "minLength": 4, "maxLength": 6},
              {"type": "integer", "minimum": -3, "maximum": 3},
              {"type": "array", "items": {"type": "integer"}, "minItems": 2, "maxItems": 4},
              {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}, "y": {"type": "boolean"}}}]
    for n, schema in enumerate(shapes):
        for seed in range(25):
            text = json.dumps(F.example(schema, f"seed-{n}-{seed}"))
            assert F.judge(text, schema) == ("conforming", []) or F.judge(text, schema)[0] == "no_answer", (schema, text)


def test_toy_models_are_deterministic_and_offline():
    for model in F.OFFLINE_MODELS.values():
        assert model("free", TICKET, "s", "Classify this ticket: a") == model("free", TICKET, "s", "Classify this ticket: a")


def test_a_forced_format_holds_where_the_toy_says_it_does():
    prompts = [f"Classify ticket number {i}" for i in range(200)]
    verdicts = {}
    for fmt in F.FORMATS:
        verdicts[fmt] = [F.judge(F.toy_answerer(fmt, TICKET, "s", p).text, TICKET, F.toy_answerer(fmt, TICKET, "s", p).finish_reason)
                         for p in prompts]
    share = {fmt: sum(v == "conforming" for v, _ in vs) / len(vs) for fmt, vs in verdicts.items()}
    assert share["grammar"] == 1.0 and share["free"] < 0.7 and share["json_schema"] > share["free"]
    free_codes = {r["code"] for _, reasons in verdicts["free"] for r in reasons}
    assert free_codes >= {"not_json", "text_around_json", "code_fence", "truncated", "missing_field", "wrong_type",
                          "extra_field"}
    assert {r["code"] for _, reasons in verdicts["json_schema"] for r in reasons} == {"out_of_range"}


def test_the_sparse_toy_model_sometimes_returns_nothing():
    replies = [F.toy_sparse("free", TICKET, "s", f"p{i}").text for i in range(200)]
    assert 10 < sum(r == "" for r in replies) < 50
    assert all(F.toy_answerer("free", TICKET, "s", f"p{i}").text for i in range(200))


# -- configurations --------------------------------------------------------------------

def test_config_settings_defaults_and_values():
    default = F.config_settings({"format": "free"})
    assert (default.format, default.max_tokens, default.temperature, default.seed, default.show_schema) == (
        "free", 1024, 0.0, None, True)
    full = F.config_settings({"format": "grammar", "max_tokens": 64, "temperature": 1, "seed": 9, "show_schema": False})
    assert (full.max_tokens, full.temperature, full.seed, full.show_schema) == (64, 1.0, 9, False)


@pytest.mark.parametrize("params, message", [
    (None, "format is required"),
    ({}, "format is required"),
    ({"format": "tools"}, "format is required and must be one of"),
    ({"format": "free", "grammar": "x"}, "unknown params grammar"),
    ({"format": "free", "max_tokens": 4}, "max_tokens must be"),
    ({"format": "free", "max_tokens": True}, "max_tokens must be"),
    ({"format": "free", "max_tokens": 10**6}, "max_tokens must be"),
    ({"format": "free", "temperature": 3}, "temperature must be"),
    ({"format": "free", "temperature": "hot"}, "temperature must be"),
    ({"format": "free", "seed": 1.5}, "seed must be an integer"),
    ({"format": "free", "show_schema": "yes"}, "show_schema must be"),
])
def test_config_settings_refuses_what_it_does_not_know(params, message):
    with pytest.raises(ValueError, match=message):
        F.config_settings(params)


def test_the_request_forces_the_format_the_configuration_names():
    assert F.request_format("free", TICKET, "ticket") == (None, None)
    response_format, extra = F.request_format("json_schema", TICKET, "ticket")
    assert response_format == {"type": "json_schema", "json_schema": {"name": "ticket", "schema": TICKET, "strict": True}}
    assert extra is None
    assert F.request_format("grammar", TICKET, "ticket") == (None, {"json_schema": TICKET})


def test_the_system_prompt_shows_the_schema_unless_told_not_to():
    assert F.canonical(TICKET) in F.system_prompt(TICKET, True) and F.SYSTEM in F.system_prompt(TICKET, True)
    assert F.system_prompt(TICKET, False) == F.SYSTEM and "category" not in F.SYSTEM


# -- spec ------------------------------------------------------------------------------

def make_root(tmp_path, *, prompts_a=None, prompts_b=None, schemas=True):
    base = tmp_path / "lab" / "corpora" / "c1"
    (base / "schemas").mkdir(parents=True)
    if schemas:
        (base / "schemas" / "ticket.json").write_text(json.dumps(TICKET), encoding="utf-8")
        (base / "schemas" / "tags.json").write_text(json.dumps(TAGS), encoding="utf-8")
    (base / "prompts-a.csv").write_text(prompts_a or "item_id,prompt,schema,grammar\na1,Classify: double charge.,ticket,g1\n"
                                        "a2,Tags for this.,tags,\n", encoding="utf-8")
    (base / "prompts-b.csv").write_text(prompts_b or "item_id,prompt,schema\nb1,Classify: crash.,ticket\n",
                                        encoding="utf-8")
    experiments = tmp_path / "lab" / "experiments"
    experiments.mkdir(parents=True)
    (experiments / "a-claims.yaml").write_text("slug: a-claims\nkind: claims\n", encoding="utf-8")
    (experiments / "a-toy.yaml").write_text("slug: a-toy\nkind: toy\n", encoding="utf-8")
    (experiments / "misnamed.yaml").write_text("slug: other\nkind: claims\n", encoding="utf-8")
    return tmp_path


def good_spec():
    return {"slug": "my-format", "kind": "format_conformity", "title": "T", "hypothesis": None,
            "params": {"corpus": "c1", "baseline": "free", "guard": {"experiment": "a-claims", "metric": "usable_per_doc"}},
            "configs": [
                {"name": "free", "model": "toy-answerer", "provider": "none", "params": {"format": "free"}},
                {"name": "forced", "model": "toy-answerer", "provider": "none", "params": {"format": "json_schema"}},
                {"name": "real", "model": "qwen", "provider": "local", "params": {"format": "grammar", "seed": 1}}],
            "samples": [
                {"name": "tuning-2", "role": "tuning", "seed": 0, "method": "by hand", "items": "lab/corpora/c1/prompts-a.csv"},
                {"name": "test-1", "role": "test", "seed": 0, "method": "by hand", "items": "lab/corpora/c1/prompts-b.csv"}]}


def check(spec, root):
    return F.check_spec(spec, root=root, models=MODELS)


def test_a_good_spec_has_no_problems(tmp_path):
    assert check(good_spec(), make_root(tmp_path)) == []


def test_the_toy_spec_of_the_repository_is_valid_and_specs_load_checks_it():
    path = ROOT / "lab" / "experiments" / "toy-format.yaml"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert F.check_spec(spec) == []
    assert specs.load(path)["slug"] == "toy-format"


def _mutate(spec, fn):
    spec = copy.deepcopy(spec)
    fn(spec)
    return spec


@pytest.mark.parametrize("fn, expected", [
    (lambda s: s.update(kind="claims"), "kind must be 'format_conformity'"),
    (lambda s: s.update(slug="Bad_Slug"), "slug must be"),
    (lambda s: s.update(params="x"), "params must be a mapping"),
    (lambda s: s["params"].update(seed=1), "params: unknown seed"),
    (lambda s: s["params"].pop("corpus"), "params.corpus must name a folder"),
    (lambda s: s["params"].update(corpus="missing"), "corpus missing: the folder schemas/ has no schema"),
    (lambda s: s["params"].update(baseline="nope"), "params.baseline 'nope' is not a configuration"),
    (lambda s: s.update(configs=[]), "at least one configuration"),
    (lambda s: s["configs"][0].update(name="Bad_Name"), "name must be lower-case"),
    (lambda s: s["configs"][1].update(name="free"), "the name is used twice"),
    (lambda s: s["configs"][0].update(colour="red"), "unknown keys colour"),
    (lambda s: s["configs"][0].pop("model"), "model is required"),
    (lambda s: s["configs"][0].update(model="not-registered"), "not in lab/models.yaml"),
    (lambda s: s["configs"][0].update(provider="local"), "provider must be 'none'"),
    (lambda s: s["configs"][2].update(provider="none"), "qwen is local in lab/models.yaml: provider must be 'local'"),
    (lambda s: s["configs"][2].update(model="hosted-chat", provider="remote"), "may be used only in other-experiment"),
    (lambda s: s["configs"][0].update(params={}), "format is required"),
    (lambda s: s["configs"][0].update(params={"format": "free", "depth": 3}), "unknown params depth"),
    (lambda s: s.update(samples=[]), "at least one sample"),
    (lambda s: s["samples"][0].update(name="Bad"), "name must be lower-case"),
    (lambda s: s["samples"][1].update(name="tuning-2"), "the name is used twice"),
    (lambda s: s["samples"][0].update(role="practice"), "role must be one of"),
    (lambda s: s["samples"][0].update(seed="zero"), "seed must be an integer"),
    (lambda s: s["samples"][0].update(method=""), "method (how the prompts were chosen) is required"),
    (lambda s: s["samples"][0].pop("items"), "the prompt file is required"),
    (lambda s: s["samples"][0].update(items="lab/corpora/other/prompts-a.csv"), "must be a file directly in lab/corpora/c1/"),
    (lambda s: s["samples"][0].update(items="lab/corpora/c1/../c1/prompts-a.csv"), "must be a file directly"),
    (lambda s: s["samples"][0].update(items="lab/corpora/c1/nowhere.csv"), "the file does not exist"),
])
def test_spec_problems_are_named(tmp_path, fn, expected):
    found = check(_mutate(good_spec(), fn), make_root(tmp_path))
    assert any(expected in p for p in found), found


def test_a_control_sample_needs_a_hypothesis_and_is_fine_with_one(tmp_path):
    root = make_root(tmp_path)
    spec = _mutate(good_spec(), lambda s: s["samples"][1].update(role="control"))
    assert any("a control sample belongs to a hypothesis" in p for p in check(spec, root))
    spec["hypothesis"] = {"slug": "x", "version": 1}
    assert check(spec, root) == []


@pytest.mark.parametrize("guard, expected", [
    ({"experiment": "a-claims"}, "exactly the keys experiment and metric"),
    ({"experiment": "a-claims", "metric": "m", "x": 1}, "exactly the keys"),
    ("a-claims", "exactly the keys"),
    ({"experiment": "a-claims", "metric": "Usable Claims"}, "guard.metric must be a metric name"),
    ({"experiment": "a-claims", "metric": 3}, "guard.metric must be a metric name"),
    ({"experiment": "A claims", "metric": "m"}, "guard.experiment must be the slug"),
    ({"experiment": "my-format", "metric": "m"}, "must be another experiment"),
    ({"experiment": "no-such-spec", "metric": "m"}, "has no readable spec lab/experiments/no-such-spec.yaml"),
    ({"experiment": "a-toy", "metric": "m"}, "is of the kind 'toy'; the guard metric (claim quality) belongs to"),
    ({"experiment": "misnamed", "metric": "m"}, "has the slug 'other'"),
])
def test_the_guard_reference_is_checked_when_the_spec_is_loaded(tmp_path, guard, expected):
    found = check(_mutate(good_spec(), lambda s: s["params"].update(guard=guard)), make_root(tmp_path))
    assert any(expected in p for p in found), found


def test_a_spec_may_have_no_guard(tmp_path):
    assert check(_mutate(good_spec(), lambda s: s["params"].pop("guard")), make_root(tmp_path)) == []


def test_bad_prompt_files_and_schemas_stop_the_spec(tmp_path):
    root = make_root(tmp_path, prompts_a="item_id,prompt,schema\na1,Q?,zz\na1,,ticket\n")
    found = check(good_spec(), root)
    assert any("prompts-a.csv" in p and "no file schemas/zz.json" in p for p in found)
    assert any("line 3" in p and "the prompt is empty" in p for p in found)
    (root / "lab/corpora/c1/schemas/ticket.json").write_text('{"requird": []}', encoding="utf-8")
    assert any("corpus c1: schemas/ticket.json" in p and "requird" in p for p in check(good_spec(), root))
    empty = make_root(tmp_path / "e", schemas=False)
    assert any("the folder schemas/ has no schema" in p for p in check(good_spec(), empty))


def test_an_item_in_two_samples_is_refused(tmp_path):
    root = make_root(tmp_path, prompts_b="item_id,prompt,schema\na1,Again?,ticket\n")
    assert any("item 'a1' is also in sample tuning-2" in p for p in check(good_spec(), root))


def test_setup_members_are_the_items_with_checksums_and_the_schema_digest(tmp_path):
    root = make_root(tmp_path)
    spec = good_spec()
    members = F.sample_items(spec, spec["samples"][0], root)
    assert [m["item_id"] for m in members] == ["a1", "a2"] and [m["stratum"] for m in members] == ["ticket", "tags"]
    assert members[0]["payload"] == {"prompt": "Classify: double charge.", "schema": "ticket",
                                     "schema_sha256": F.sha256_of(TICKET), "grammar": "g1"}
    assert members[0]["content_sha256"] == F.content_sha256(F.Item("a1", "Classify: double charge.", "ticket", "g1"),
                                                           F.sha256_of(TICKET))
    # a schema changed after the sample was stored moves the checksum, so the stored sample can never match it
    (root / "lab/corpora/c1/schemas/ticket.json").write_text(json.dumps({**TICKET, "required": ["category"]}),
                                                             encoding="utf-8")
    changed = F.sample_items(spec, spec["samples"][0], root)
    assert changed[0]["content_sha256"] != members[0]["content_sha256"]
    assert changed[1]["content_sha256"] == members[1]["content_sha256"]  # the other schema did not change


def test_sample_items_refuse_a_schema_without_a_file_and_a_broken_schema(tmp_path):
    root = make_root(tmp_path, prompts_a="item_id,prompt,schema\na1,Q?,zz\n")
    spec = good_spec()
    assert any("no file schemas/zz.json" in p for p in problems_of(lambda: F.sample_items(spec, spec["samples"][0], root)))
    (root / "lab/corpora/c1/schemas/tags.json").write_text("{", encoding="utf-8")
    assert any("not valid JSON" in p for p in problems_of(lambda: F.sample_items(spec, spec["samples"][1], root)))


# -- registration ----------------------------------------------------------------------

def test_the_kind_is_registered_with_the_queue(monkeypatch):
    from exocortex.lab import claims, retrieval, toy

    monkeypatch.setattr(toy, "make_runner", lambda conn, tenant: "toy-runner")
    monkeypatch.setattr(claims, "make_runner", lambda conn, tenant: "claims-runner")
    monkeypatch.setattr(retrieval, "make_runner", lambda conn, tenant: "retrieval-runner")
    runners = cli.runners(None, "tenant")
    assert set(runners) >= {"toy", "claims", "retrieval", "format_conformity"}
    assert callable(runners[F.KIND]) and F.KIND == "format_conformity"


def test_specs_hand_format_conformity_samples_to_the_kind_and_others_to_the_corpus_reader(monkeypatch):
    spec = yaml.safe_load((ROOT / "lab/experiments/toy-format.yaml").read_text(encoding="utf-8"))
    members = specs.sample_members(spec, spec["samples"][1])
    assert len(members) == 36 and members[0]["item_id"] == "t01"
    seen = []
    monkeypatch.setattr(specs, "sample_items", lambda s, sample: seen.append(s["kind"]) or ["paper"])
    assert specs.sample_members({"kind": "claims"}, {}) == ["paper"] and seen == ["claims"]


def test_specs_load_refuses_an_invalid_spec_with_every_problem(tmp_path):
    spec = good_spec()
    spec["configs"][0]["model"] = "not-registered"
    spec["samples"][0]["items"] = "lab/corpora/nowhere/q.csv"
    path = tmp_path / "s.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    with pytest.raises(F.FormatInputError) as info:
        specs.load(path)
    assert len(info.value.problems) >= 3 and info.value.source == str(path)
    assert isinstance(info.value, ValueError)  # callers that only know ValueError still refuse


def test_the_command_line_knows_the_format_conformity_command_and_its_instance_names():
    args = cli.build_parser().parse_args(["format_conformity", "validate", "--experiment", "toy-format"])
    assert (args.action, args.experiment, args.func) == ("validate", "toy-format", cli._cmd_format_conformity)
    alias = cli.build_parser().parse_args(["format-conformity", "summary", "--experiment", "toy-format", "--run", "r1"])
    assert (alias.action, alias.run, alias.func) == ("summary", "r1", cli._cmd_format_conformity)
    assert cli.parse_run_instance("toy-format_test-36_free.schema-forced_queue") == {
        "experiment": "toy-format", "sample": "test-36", "configs": ["free", "schema-forced"], "queue_only": True}


def test_validate_command_reports_ok_and_problems(capsys, tmp_path):
    assert cli.main(["format_conformity", "validate", "--experiment", "toy-format"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["items"] == {"tuning-6": 6, "test-36": 36}
    assert out["guard"] == {"experiment": "intent-vs-fact", "metric": "usable_per_document"}
    assert out["configs"] == ["free", "schema-forced", "grammar-forced", "free-sparse"]
    spec = yaml.safe_load((ROOT / "lab/experiments/toy-format.yaml").read_text(encoding="utf-8"))
    spec["configs"][0]["model"] = "unknown-model"
    spec["params"]["guard"]["experiment"] = "toy-format"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    assert cli.main(["format_conformity", "validate", "--spec", str(path)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False and any("not in lab/models.yaml" in p for p in out["problems"])
    assert any("must be another experiment" in p for p in out["problems"])
    assert cli.main(["format_conformity", "validate", "--experiment", "no-such-experiment"]) == 2
    assert "refused" in json.loads(capsys.readouterr().out)
    assert cli.main(["format_conformity", "validate", "--experiment", "toy-retrieval"]) == 2
    assert "kind 'retrieval'" in json.loads(capsys.readouterr().out)["refused"]
    assert cli.main(["format_conformity", "summary"]) == 2


# -- the runner, without a database ----------------------------------------------------

def _job_and_item(item, config, schema=TICKET, params=None):
    digest = F.sha256_of(schema)
    member = {"item_id": item.id, "content_sha256": F.content_sha256(item, digest), "stratum": item.schema,
              "payload": {"prompt": item.prompt, "schema": item.schema, "schema_sha256": digest, "grammar": item.grammar}}
    return {"config": config, "experiment": {"slug": "x", "kind": "format_conformity",
                                             "params": params or {"corpus": "c1"}}}, member


def _cfg(model="toy-answerer", format_="free", **extra):
    return {"name": "c", "model": model, "provider": "none" if model.startswith("toy") else "local",
            "params": {"format": format_, **extra}}


def test_the_runner_judges_offline_models_and_never_reaches_for_the_gateway(tmp_path, monkeypatch):
    import exocortex.lab.llm as llm_module

    monkeypatch.setattr(llm_module, "LabLLM", lambda *a, **k: pytest.fail("the gateway client must not be built"))
    runner = F.make_runner(None, "tenant", root=make_root(tmp_path))
    item = F.Item("a1", "Classify: double charge.", "ticket", "g1")
    job, member = _job_and_item(item, _cfg(format_="grammar"))
    result = runner(job, member)
    assert result["ok"] is True and result["provider"] == "none" and result["base_url"] is None
    out = result["output"]
    assert out["verdict"] == "conforming" and out["reasons"] == [] and out["format"] == "grammar"
    assert (out["item"], out["schema"], out["grammar"], out["schema_sha256"]) == ("a1", "ticket", "g1", F.sha256_of(TICKET))
    assert json.loads(out["answer"])  # the raw answer is kept
    assert runner(job, member)["output"] == out  # the same job gives the same answer and verdict
    assert result["input_tokens"] > 0 and result["output_tokens"] > 0


def test_the_runner_stores_a_bad_answer_as_a_measurement_with_its_reasons(tmp_path):
    runner = F.make_runner(None, "tenant", root=make_root(tmp_path))
    seen = set()
    for n in range(40):
        job, member = _job_and_item(F.Item(f"a{n}", f"Classify ticket {n}", "ticket"), _cfg(format_="free"))
        result = runner(job, member)
        assert result["ok"] is True  # a bad answer is still a valid result
        out = result["output"]
        seen.add(out["verdict"])
        assert (out["verdict"] == "conforming") == (out["reasons"] == [])
        assert F.judge(out["answer"], TICKET, out["finish_reason"])[0] == out["verdict"]
    assert seen == {"conforming", "non_conforming"}


def test_an_empty_reply_is_a_result_that_is_not_ok(tmp_path):
    runner = F.make_runner(None, "tenant", root=make_root(tmp_path))
    results = []
    for n in range(60):
        job, member = _job_and_item(F.Item(f"a{n}", f"Classify ticket {n}", "ticket"), _cfg("toy-sparse"))
        results.append(runner(job, member))
    silent = [r for r in results if not r["ok"]]
    assert silent and all(r["error_reason"] == "empty reply" and r["output"]["verdict"] == "no_answer"
                          and r["output"]["answer"] == "" for r in silent)
    assert all(r["error_reason"] is None for r in results if r["ok"])


def test_the_runner_raises_instead_of_guessing(tmp_path):
    root = make_root(tmp_path)
    runner = F.make_runner(None, "tenant", root=root)
    item = F.Item("a1", "Classify: double charge.", "ticket")
    job, member = _job_and_item(item, _cfg())
    with pytest.raises(RuntimeError, match="does not match the checksum"):
        runner(job, {**member, "payload": {**member["payload"], "prompt": "changed"}})
    with pytest.raises(ValueError, match="format is required"):
        runner({**job, "config": {**job["config"], "params": {}}}, member)
    (root / "lab/corpora/c1/schemas/ticket.json").write_text(json.dumps({**TICKET, "required": ["category"]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="schema ticket changed since the sample of a1 was stored"):
        F.make_runner(None, "tenant", root=root)(job, member)
    job, member = _job_and_item(F.Item("a2", "Q?", "zz"), _cfg(), schema=TICKET)
    with pytest.raises(F.FormatInputError, match="no schema 'zz'"):
        runner(job, member)


class Gateway:
    """Stands in for the lab gateway client: records what chat was asked and answers with a fixed reply."""

    url = "unix:/run/lab-llm/gateway.sock"

    def __init__(self, raw=OK, finish="stop", error=None):
        self.raw, self.finish, self.error, self.calls = raw, finish, error, []

    def chat(self, **kwargs):
        from exocortex.lab.llm import Call

        self.calls.append(kwargs)
        return Call(model=kwargs["model"], raw=self.raw, error=self.error, finish_reason=self.finish,
                    prompt_tokens=21, completion_tokens=8)


def test_a_model_from_the_registry_is_called_through_the_gateway_client_only(tmp_path):
    root = make_root(tmp_path)
    item = F.Item("a1", "Classify: double charge.", "ticket")
    gateway = Gateway()
    runner = F.make_runner(None, "tenant", llm=gateway, root=root)
    for fmt, response_format, extra in (
            ("free", None, None),
            ("json_schema", {"type": "json_schema", "json_schema": {"name": "ticket", "schema": TICKET, "strict": True}}, None),
            ("grammar", None, {"json_schema": TICKET})):
        job, member = _job_and_item(item, _cfg("qwen", fmt, max_tokens=64, temperature=0.5, seed=3))
        result = runner(job, member)
        call = gateway.calls[-1]
        assert call["model"] == "qwen" and call["user"] == "Classify: double charge."
        assert call["response_format"] == response_format and call["extra"] == extra
        assert (call["max_tokens"], call["temperature"], call["seed"]) == (64, 0.5, 3)
        assert F.canonical(TICKET) in call["system"]
        assert result["base_url"] == gateway.url and result["provider"] == "local" and result["model"] == "qwen"
        assert (result["input_tokens"], result["output_tokens"]) == (21, 8) and result["output"]["verdict"] == "conforming"
    job, member = _job_and_item(item, _cfg("qwen", "free", show_schema=False))
    runner(job, member)
    assert gateway.calls[-1]["system"] == F.SYSTEM


def test_a_real_models_bad_answers_are_judged_and_a_failed_call_raises(tmp_path):
    root = make_root(tmp_path)
    item = F.Item("a1", "Q?", "ticket")
    job, member = _job_and_item(item, _cfg("qwen", "free"))
    prose = F.make_runner(None, "t", llm=Gateway("I think it is billing."), root=root)(job, member)
    assert prose["output"]["verdict"] == "non_conforming" and prose["output"]["reasons"][0]["code"] == "not_json"
    cut = F.make_runner(None, "t", llm=Gateway('{"category": "b', "length"), root=root)(job, member)
    assert cut["output"]["reasons"][0]["code"] == "truncated" and cut["output"]["finish_reason"] == "length"
    empty = F.make_runner(None, "t", llm=Gateway(""), root=root)(job, member)
    assert empty["ok"] is False and empty["output"]["verdict"] == "no_answer"
    with pytest.raises(RuntimeError, match="no reply from qwen: http 502"):
        F.make_runner(None, "t", llm=Gateway(error="http 502"), root=root)(job, member)


def test_a_nul_character_in_an_answer_is_replaced_before_it_is_judged_and_stored(tmp_path):
    job, member = _job_and_item(F.Item("a1", "Q?", "ticket"), _cfg("qwen", "free"))
    result = F.make_runner(None, "t", llm=Gateway('{"category": "b\x00ug", "priority": 3}'),
                           root=make_root(tmp_path))(job, member)
    assert "\x00" not in result["output"]["answer"] and result["output"]["nul_replaced"] is True
    assert result["output"]["reasons"][0]["code"] == "bad_value"
    json.dumps(result["output"])


def test_the_gateway_client_is_built_lazily_and_talks_to_the_gateway_in_the_shape_chat_expects(tmp_path, monkeypatch):
    import exocortex.lab.llm as llm_module

    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": OK}, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 3, "completion_tokens": 2}})

    monkeypatch.setattr(llm_module, "LabLLM", lambda: LabLLM(url="http://gw", client=httpx.Client(
        transport=httpx.MockTransport(handler))))
    runner = F.make_runner(None, "t", root=make_root(tmp_path))
    job, member = _job_and_item(F.Item("a1", "Q?", "ticket"), _cfg("qwen", "json_schema"))
    result = runner(job, member)
    assert result["output"]["verdict"] == "conforming" and result["base_url"] == "http://gw"
    assert seen["response_format"]["json_schema"]["schema"] == TICKET and seen["model"] == "qwen"
