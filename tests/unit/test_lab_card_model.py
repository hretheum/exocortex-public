"""General model of a reference card and its validator (roadmap task F4.1); files only, no database."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml

from exocortex.lab import card_model as cm

ROOT = Path(__file__).resolve().parents[2]
CARD = ROOT / "lab" / "cards" / "toy-length.en.yaml"
SECTIONS = ["goal_and_context", "hypothesis", "experiments_and_iterations", "validation_method", "results",
            "next_steps", "novelty", "risks_and_limitations", "how_to_verify"]


@pytest.fixture(scope="module")
def model() -> dict:
    return cm.load_model()


@pytest.fixture()
def card() -> dict:
    return yaml.safe_load(CARD.read_text(encoding="utf-8"))


def fields(problems: list[cm.Problem]) -> list[str]:
    return [p.field for p in problems]


def section(card: dict, sid: str) -> tuple[int, dict]:
    return next((i, s) for i, s in enumerate(card["sections"]) if s["id"] == sid)


# ------------------------------------------------------------------ model ----
def test_model_is_valid_and_has_the_nine_sections_in_order(model):
    assert cm.check_model(model) == []
    assert [s["id"] for s in model["sections"]] == SECTIONS


def test_every_section_has_a_title_in_both_languages(model):
    for s in model["sections"]:
        assert s["title"]["pl"] and s["title"]["en"]


def test_inventory_names_appear_in_the_files_that_define_them(model):
    for kind in ("nodes", "sources", "edges", "tables"):
        for name, entry in model["inventory"][kind].items():
            text = (ROOT / entry["defined_in"]).read_text(encoding="utf-8")
            assert name in text, f"inventory.{kind}.{name} is not in {entry['defined_in']}"


def test_inventory_files_exist(model):
    for name, entry in model["inventory"]["files"].items():
        assert (ROOT / entry["defined_in"]).is_file(), entry["defined_in"]
        assert list(ROOT.glob(name.replace("<slug>", "*"))), f"no file matches {name}"


def test_inventory_edges_are_values_of_the_edge_type_enum(model):
    sql = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "schema").glob("*.sql"))
    enum = set(re.findall(r"ADD VALUE IF NOT EXISTS '([a-z_]+)'", sql))
    base = re.search(r"CREATE TYPE edge_type AS ENUM \((.*?)\);", sql, re.DOTALL)
    assert base is not None
    enum |= set(re.findall(r"'([a-z_]+)'", base.group(1)))
    assert set(model["inventory"]["edges"]) <= enum


def test_inventory_edges_are_the_ones_the_lab_writes(model):
    written = set()
    for p in (ROOT / "exocortex" / "lab").glob("*.py"):
        written |= set(re.findall(r'insert_edge\(.*"([a-z_]+)"\)\s*$', p.read_text(encoding="utf-8"),
                                   re.MULTILINE))
    assert set(model["inventory"]["edges"]) == written


def test_inventory_nodes_are_the_thought_types_the_lab_writes(model):
    written = set()
    for p in (ROOT / "exocortex" / "lab").glob("*.py"):
        written |= set(re.findall(r'thought_type="([a-z_]+)"', p.read_text(encoding="utf-8")))
    assert set(model["inventory"]["nodes"]) == written


def test_model_modes_are_the_extractor_modes(model):
    from exocortex.lab.extractor import MODES

    assert model["modes"] == list(MODES) == ["fact", "plan", "requirement", "hypothesis"]


def test_model_rejects_a_graph_reference_outside_the_inventory(model):
    broken = copy.deepcopy(model)
    broken["sections"][1]["graph"]["edges"].append("implements_roadmap")
    problems = cm.check_model(broken)
    assert "sections[1].graph.edges[1]" in fields(problems)


def test_model_rejects_an_unknown_open_decision(model):
    broken = copy.deepcopy(model)
    broken["sections"][0]["open_decisions"] = ["OD-99"]
    assert "sections[0].open_decisions[0]" in fields(cm.check_model(broken))


def test_results_accept_only_data_rows_and_facts(model):
    results = next(s for s in model["sections"] if s["id"] == "results")
    assert results["source_kinds"] == ["data"]
    assert results["modes"] == ["fact"]


# ------------------------------------------------------------------- card ----
def test_example_card_passes(card, model):
    assert cm.check_card(card, model) == []


def test_example_card_passes_from_the_command_line(capsys):
    assert cm.main([str(CARD)]) == 0
    assert capsys.readouterr().out.strip().endswith(": ok")


def test_missing_source_is_rejected_with_the_field_path(card, model):
    del card["sections"][4]["statements"][0]["source"]
    problems = cm.check_card(card, model)
    assert fields(problems) == ["sections[4].statements[0].source"]
    assert "required field is missing" in str(problems[0])


def test_unknown_mode_is_rejected_with_the_field_path(card, model):
    card["sections"][1]["statements"][0]["mode"] = "claim"
    problems = cm.check_card(card, model)
    assert fields(problems) == ["sections[1].statements[0].mode"]
    assert "'claim' is not allowed" in problems[0].message


def test_missing_mode_is_rejected(card, model):
    del card["sections"][0]["statements"][1]["mode"]
    assert fields(cm.check_card(card, model)) == ["sections[0].statements[1].mode"]


def test_mode_not_allowed_in_the_section_is_rejected(card, model):
    i, sec = section(card, "results")
    sec["statements"][2]["mode"] = "plan"
    problems = cm.check_card(card, model)
    assert fields(problems) == [f"sections[{i}].statements[2].mode"]
    assert "not allowed in section results" in problems[0].message


def test_missing_section_is_rejected_with_its_position(card, model):
    i, _ = section(card, "results")
    del card["sections"][i]
    problems = cm.check_card(card, model)
    assert [str(p) for p in problems] == ["sections: missing section 'results' (position 4 of the model)"]


def test_sections_out_of_order_are_rejected(card, model):
    card["sections"][0], card["sections"][1] = card["sections"][1], card["sections"][0]
    assert "sections" in fields(cm.check_card(card, model))


def test_duplicate_and_unknown_sections_are_rejected(card, model):
    card["sections"].append(copy.deepcopy(card["sections"][0]))
    card["sections"].append({"id": "budget", "statements": []})
    found = fields(cm.check_card(card, model))
    assert f"sections[{len(card['sections']) - 2}].id" in found
    assert f"sections[{len(card['sections']) - 1}].id" in found


def test_empty_section_is_rejected(card, model):
    card["sections"][6]["statements"] = []
    assert fields(cm.check_card(card, model)) == ["sections[6].statements"]


def test_current_state_needs_a_date(card, model):
    i, sec = section(card, "next_steps")
    del sec["statements"][0]["as_of"]
    assert fields(cm.check_card(card, model)) == [f"sections[{i}].statements[0].as_of"]


def test_date_only_on_a_current_state_statement(card, model):
    card["sections"][0]["statements"][0]["as_of"] = "2026-10-01"
    assert fields(cm.check_card(card, model)) == ["sections[0].statements[0].as_of"]


def test_current_state_is_required(card, model):
    del card["sections"][0]["statements"][0]["current_state"]
    assert fields(cm.check_card(card, model)) == ["sections[0].statements[0].current_state"]


def test_invalid_date_is_rejected(card, model):
    i, sec = section(card, "next_steps")
    sec["statements"][0]["as_of"] = "2026-13-40"
    assert fields(cm.check_card(card, model)) == [f"sections[{i}].statements[0].as_of"]


def test_results_reject_a_file_source(card, model):
    i, sec = section(card, "results")
    sec["statements"][0]["source"] = {"file": "dowody/en/generated/experiments/toy-length.md"}
    problems = cm.check_card(card, model)
    assert fields(problems) == [f"sections[{i}].statements[0].source"]
    assert "accepts sources of kind data" in problems[0].message


def test_source_file_must_exist(card, model):
    card["sections"][0]["statements"][0]["source"]["file"] = "dowody/en/experiments/no-such/hypothesis.md"
    assert fields(cm.check_card(card, model)) == ["sections[0].statements[0].source.file"]


def test_source_path_must_stay_in_the_repository(card, model):
    card["sections"][0]["statements"][0]["source"]["file"] = "../outside.md"
    assert fields(cm.check_card(card, model)) == ["sections[0].statements[0].source.file"]


def test_source_heading_must_exist(card, model):
    card["sections"][0]["statements"][0]["source"]["heading"] = "Background"
    assert fields(cm.check_card(card, model)) == ["sections[0].statements[0].source.heading"]


def test_data_row_must_match_exactly_one_row(card, model):
    i, sec = section(card, "results")
    sec["statements"][0]["source"]["row"] = {"result_id": "toy-length/run-2026-09-29-9/diff/long_unit_share"}
    problems = cm.check_card(card, model)
    assert fields(problems) == [f"sections[{i}].statements[0].source.row"]
    assert "matches 0 rows" in problems[0].message
    sec["statements"][0]["source"]["row"] = {"metric": "long_unit_share_difference"}
    assert "matches 4 rows" in cm.check_card(card, model)[0].message


def test_data_row_column_must_exist(card, model):
    i, sec = section(card, "results")
    sec["statements"][0]["source"]["row"] = {"id": "x"}
    assert fields(cm.check_card(card, model)) == [f"sections[{i}].statements[0].source.row.id"]


def test_data_row_in_a_jsonl_file(card, model, tmp_path):
    root = tmp_path
    (root / "lab").mkdir()
    (root / "lab" / "card-model.yaml").write_text((ROOT / cm.MODEL_PATH).read_text(encoding="utf-8"))
    (root / "reg.jsonl").write_text('{"slug": "a", "version": 1}\n{"slug": "b", "version": 1}\n')
    small = {"card_model": 1, "experiment": "a", "hypothesis": None, "lang": "pl", "title": "A",
             "sections": [{"id": sid, "statements": [{"text": "x", "mode": "fact", "current_state": False,
                                                      "source": {"data": "reg.jsonl", "row": {"slug": "a"}}}]}
                          for sid in SECTIONS]}
    small["sections"][SECTIONS.index("novelty")]["statements"][0]["source"] = {"file": "reg.jsonl"}  # file only
    assert cm.check_card(small, model, root=root) == []
    small["sections"][0]["statements"][0]["source"]["row"] = {"version": 1}
    assert fields(cm.check_card(small, model, root=root)) == ["sections[0].statements[0].source.row"]


def test_unknown_fields_are_rejected(card, model):
    card["status"] = "done"
    card["sections"][0]["statements"][0]["confidence"] = 0.9
    found = fields(cm.check_card(card, model))
    assert "status" in found and "sections[0].statements[0].confidence" in found


def test_header_fields_are_checked(card, model):
    card["lang"] = "de"
    card["card_model"] = 2
    card["hypothesis"] = {"slug": "toy-length"}
    del card["title"]
    assert sorted(fields(cm.check_card(card, model))) == ["card_model", "hypothesis", "lang", "title"]


def test_command_line_reports_every_problem_and_fails(tmp_path, card, capsys):
    del card["sections"][4]["statements"][0]["source"]
    card["sections"][1]["statements"][0]["mode"] = "claim"
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(card, sort_keys=False), encoding="utf-8")
    assert cm.main([str(bad)]) == 1
    out = capsys.readouterr().out
    assert "sections[1].statements[0].mode" in out and "sections[4].statements[0].source" in out


def test_lab_cli_card_check(capsys):
    import json

    from exocortex.lab import cli

    assert cli.main(["card-check", str(CARD)]) == 0
    assert json.loads(capsys.readouterr().out) == {"command": "card-check", "cards": {str(CARD): []}}
