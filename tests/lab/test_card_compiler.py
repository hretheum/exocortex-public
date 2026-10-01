# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Card compiler (F4.2): files only, no database, no model calls.

The compiler is run on the published experiments of this repository (toy-length with results,
intent-vs-fact without) and on small synthetic repositories built in a temporary folder, where gate decisions
and unusual data can be put in place.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from exocortex.lab import card_compiler as cc
from exocortex.lab import card_model, cli, honesty, prereg

ROOT = Path(__file__).resolve().parents[2]
AS_OF = "2026-10-01"
BASE = cc.DEFAULT_BASE_URL


def compile_to(tmp_path: Path, slug: str, root: Path | None = None, **kw) -> cc.Compiled:
    return cc.compile_card(slug, out=tmp_path / "out", root=root, as_of=AS_OF, **kw)


@pytest.fixture(scope="module")
def toy(tmp_path_factory) -> cc.Compiled:
    return cc.compile_card("toy-length", out=tmp_path_factory.mktemp("toy"), as_of=AS_OF)


@pytest.fixture(scope="module")
def intent(tmp_path_factory) -> cc.Compiled:
    return cc.compile_card("intent-vs-fact", out=tmp_path_factory.mktemp("intent"), as_of=AS_OF)


def card_yaml(compiled: cc.Compiled, lang: str) -> dict:
    return yaml.safe_load(Path(compiled.files[f"{compiled.slug}.card.{lang}.yaml"]).read_text(encoding="utf-8"))


def card_md(compiled: cc.Compiled, lang: str) -> str:
    return Path(compiled.files[f"{compiled.slug}.card.{lang}.md"]).read_text(encoding="utf-8")


def sentences(card: dict) -> list[dict]:
    return [st for sec in card["sections"] for st in sec["statements"]]


# ---------------------------------------------------------------- checks ----
@pytest.mark.parametrize("fixture", ["toy", "intent"])
def test_output_passes_the_card_model_and_the_honesty_check(fixture, request):
    compiled = request.getfixturevalue(fixture)
    assert compiled.ok, compiled.checks
    for lang in cc.LANGS:
        assert card_model.check_file(Path(compiled.files[f"{compiled.slug}.card.{lang}.yaml"])) == []
        report, code = honesty.run(Path(compiled.files[f"{compiled.slug}.sentences.{lang}.jsonl"]),
                                   [ROOT / "dowody" / "data" / compiled.slug])
        assert report["violations"] == [] and code == 0
        assert report["sentences"] == len(sentences(card_yaml(compiled, lang)))


def test_command_line_compiles_and_exits_zero(tmp_path, capsys):
    code = cli.main(["card-compile", "toy-length", "--out", str(tmp_path), "--as-of", AS_OF])
    report = json.loads(capsys.readouterr().out)
    assert code == 0 and report["ok"] and report["project_status"] == "draft"
    assert (tmp_path / "toy-length.card.pl.md").is_file() and (tmp_path / "toy-length.card.en.md").is_file()
    # the two commands of the roadmap task, run on the written files
    assert cli.main(["card-check", str(tmp_path / "toy-length.card.en.yaml"),
                     str(tmp_path / "toy-length.card.pl.yaml")]) == 0
    assert cli.main(["honesty", str(tmp_path / "toy-length.sentences.pl.jsonl"),
                     "--data", "dowody/data/toy-length"]) == 0


def test_command_line_reports_a_missing_card_with_exit_two(tmp_path, capsys):
    assert cli.main(["card-compile", "no-such-experiment", "--out", str(tmp_path)]) == 2
    assert "no hypothesis card" in json.loads(capsys.readouterr().out)["error"]


# ----------------------------------------------------------------- links ----
BULLET = re.compile(r"^- (?P<text>.*) \[(?P<label>[^\]]+)\]\((?P<url>[^)]+)\)$")


def csv_row_starts(path: Path) -> dict[int, dict[str, str]]:
    """Line a row starts on -> the row, read independently of the compiler."""
    reader = csv.reader(io.StringIO(path.read_text(encoding="utf-8"), newline=""))
    header = next(reader)
    out, start = {}, reader.line_num + 1
    for cells in reader:
        out[start] = dict(zip(header, cells, strict=False))
        start = reader.line_num + 1
    return out


def md_anchors(path: Path) -> set[str]:
    return {cc.github_anchor(h) for h in card_model.headings(path.read_text(encoding="utf-8"))}


@pytest.mark.parametrize("fixture", ["toy", "intent"])
@pytest.mark.parametrize("lang", cc.LANGS)
def test_every_sentence_has_a_link_that_points_into_the_repository(fixture, lang, request):
    compiled = request.getfixturevalue(fixture)
    statements = sentences(card_yaml(compiled, lang))
    bullets = [ln for ln in card_md(compiled, lang).splitlines() if ln.startswith("- ")]
    assert len(bullets) == len(statements)
    for line, st in zip(bullets, statements, strict=True):
        m = BULLET.match(line)
        assert m, f"a sentence without exactly one link at its end: {line[:80]}"
        assert m["text"] == st["text"]
        url = m["url"]
        assert url.startswith(BASE)
        parts = urlsplit(url[len(BASE):])
        path = ROOT / parts.path
        assert path.is_file(), f"{parts.path} does not exist"
        source = st["source"]
        if "data" in source:  # a link to one data row
            assert parts.path == source["data"] and parts.query == "plain=1"
            line_no = int(parts.fragment.removeprefix("L"))
            rows = csv_row_starts(path) if path.suffix == ".csv" else None
            if rows is not None:
                assert line_no in rows, f"line {line_no} of {parts.path} does not start a row"
                assert all(rows[line_no].get(k) == str(v) for k, v in source["row"].items())
                same = [r for r in rows.values() if all(r.get(k) == str(v) for k, v in source["row"].items())]
                assert len(same) == 1, "the link does not single out exactly one row"
            else:  # JSONL: one object per line
                obj = json.loads(path.read_text(encoding="utf-8").splitlines()[line_no - 1])
                assert all(str(obj.get(k)) == str(v) for k, v in source["row"].items())
        else:
            assert parts.path == source["file"]
            if "heading" in source:
                assert parts.fragment in md_anchors(path)
                assert cc.github_anchor(source["heading"]) == parts.fragment
            else:
                assert not parts.fragment


def test_links_can_be_relative_with_an_empty_base(tmp_path):
    compiled = cc.compile_card("toy-length", out=tmp_path, as_of=AS_OF, base_url="")
    for line in card_md(compiled, "en").splitlines():
        if line.startswith("- "):
            m = BULLET.match(line)
            assert m and (ROOT / urlsplit(m["url"]).path).is_file()


def test_github_anchor_follows_github():
    assert cc.github_anchor("The assumption everything depends on") == "the-assumption-everything-depends-on"
    assert cc.github_anchor("Założenie, od którego wszystko zależy") == "założenie-od-którego-wszystko-zależy"
    assert cc.github_anchor("Hypothesis: a `b` rule") == "hypothesis-a-b-rule"


# ----------------------------------------------------------- the content ----
def test_toy_length_numbers_come_from_the_recorded_rows(toy):
    en = " ".join(st["text"] for st in sentences(card_yaml(toy, "en")))
    pl = " ".join(st["text"] for st in sentences(card_yaml(toy, "pl")))
    for shown in ("0.083", "0.833", "0.750", "0.667", "0.015", "0.354", "0.552", "0.953"):
        assert shown in en and shown.replace(".", ",") in pl


def test_every_metric_row_gets_a_results_sentence_citing_it(toy):
    cited = {st["source"]["row"]["result_id"] for st in
             next(s for s in card_yaml(toy, "en")["sections"] if s["id"] == "results")["statements"]}
    with (ROOT / "dowody/data/toy-length/metrics.csv").open(encoding="utf-8", newline="") as fh:
        assert cited == {r["result_id"] for r in csv.DictReader(fh)}


def test_both_languages_cite_the_same_data_rows(toy):
    def rows(lang):
        return [json.dumps(st["source"], sort_keys=True) for st in sentences(card_yaml(toy, lang))
                if "data" in st["source"]]
    en, pl = rows("en"), rows("pl")
    assert sorted(set(en) - set(pl)) == [] and sorted(set(pl) - set(en)) == []
    pl_text = card_md(toy, "pl")
    assert "Karta projektu referencyjnego" in pl_text and "Wyniki" in pl_text


def test_parameters_are_marked_as_code_and_results_are_not(toy):
    en = sentences(card_yaml(toy, "en"))
    h1 = next(s["text"] for s in en if s["text"].startswith("H1:"))
    assert "`120`" in h1 and "0.083" not in h1
    result = next(s["text"] for s in en if "0.083" in s["text"])
    assert "`0.083`" not in result


def test_quoted_card_text_is_word_for_word(toy):
    body = (ROOT / "dowody/en/experiments/toy-length/hypothesis.md").read_text(encoding="utf-8")
    problem = next(s for s in sentences(card_yaml(toy, "en")) if s["source"].get("heading") == "Problem")
    assert problem["text"] in body


def test_a_quoted_state_word_gets_the_date(tmp_path):
    root = make_tree(tmp_path / "repo", problem="The pipeline works.")
    card = card_yaml(compile_to(tmp_path, "synth", root), "en")
    st = next(s for s in sentences(card) if "pipeline works" in s["text"])
    assert st["current_state"] is True and st["as_of"] == AS_OF and st["text"].startswith(f"As of {AS_OF}")


# --------------------------------------------- the hand-written example ----
def test_generated_toy_card_agrees_with_the_hand_written_one(toy):
    """What is factual in lab/cards/toy-length.en.yaml (numbers, data rows) is in the generated card too."""
    hand = yaml.safe_load((ROOT / "lab/cards/toy-length.en.yaml").read_text(encoding="utf-8"))
    generated = sentences(card_yaml(toy, "en"))
    by_source = {json.dumps(g["source"], sort_keys=True): [] for g in generated}
    for g in generated:
        by_source[json.dumps(g["source"], sort_keys=True)].append(g["text"])
    for h in sentences(hand):
        if "data" not in h["source"]:
            continue
        key = json.dumps(h["source"], sort_keys=True)
        assert key in by_source, f"the hand-written card cites a row the generated card does not: {h['source']}"
        numbers = re.findall(r"\d+\.\d+", h["text"])
        if "result_id" in h["source"]["row"]:  # a measured result: its numbers must be the generated ones
            assert all(n in " ".join(by_source[key]) for n in numbers), h["text"]


# ---------------------------------------------------- no results (intent) ----
def test_experiment_without_metrics_says_so(intent):
    en = card_yaml(intent, "en")
    results = next(s for s in en["sections"] if s["id"] == "results")["statements"]
    assert len(results) == 1
    assert "no metric for it has been published" in results[0]["text"]
    assert results[0]["current_state"] is True and results[0]["as_of"] == AS_OF
    assert results[0]["source"]["data"].endswith("intent-vs-fact/runs.csv")
    pl = card_yaml(intent, "pl")
    pl_results = next(s for s in pl["sections"] if s["id"] == "results")["statements"]
    assert "nie opublikowano dla niego żadnej metryki" in pl_results[0]["text"]
    assert not re.search(r"\b\d\.\d{3}\b", " ".join(s["text"] for s in results)), "no measured value may appear"


def test_intent_vs_fact_is_frozen_and_not_decided(intent):
    assert intent.status == "frozen"
    status = next(s for s in sentences(card_yaml(intent, "en")) if s["text"].startswith(f"As of {AS_OF}, the project"))
    assert "frozen" in status["text"] and status["source"]["data"] == "dowody/prereg.jsonl"


# --------------------------------------------------- synthetic repositories ----
CARD = """---
type: hypothesis_card
lang: {lang}
counterpart: ../../../{other}/experiments/synth/hypothesis.md
slug: synth
version: 1
supersedes: null
tier_target: S
data_class: public
sources: []
prereg_hash: null
human_validated: {validated}
---

# Hipoteza: test

## Problem

{problem}

## Hypothesis

- H1: the share rises.

## Metrics

| Role | Metric | Definition | Threshold | Baseline | How computed |
|---|---|---|---|---|---|
| deciding | share_difference | the difference of shares | at least 10 percentage points | the old rule | bootstrap |

## Gate criteria

- G1: difference above the threshold; then GO, otherwise NO-GO.

## Stopping condition

No result at all.

## Related work

None.
"""
GATE = """---
type: gate_decision
lang: {lang}
counterpart: ../../../{other}/experiments/synth/gate-g1.md
hypothesis: synth
hypothesis_version: 1
gate: G1
decision: {decision}
date: "2026-09-30"
approved_by: []
return_condition: {rc}
result_ids: [{ids}]
human_validated: {validated}
---

# Gate G1: synth
"""
METRICS = ("result_id,run_id,config,metric,value,ci_low,ci_high,n,method,details\n"
           "synth/run-1/diff/share,run-1,,share_difference,0.5,0.25,0.75,10,bootstrap-by-item,"
           "\"{\"\"a\"\": \"\"old\"\", \"\"b\"\": \"\"new\"\"}\"\n")
RUNS = ("run_id,sample,hypothesis_version,prereg_hash,code_commit,status,created_at,finished_at\n"
        "run-1,tuning-10,1,,abcdef0123456789,done,2026-09-30T00:00:00+00:00,2026-09-30T00:01:00+00:00\n")
SAMPLES = ("name,role,seed,method,data_class,members_sha256,size,touched_at\n"
           "tuning-10,tuning,7,\"drawn at random\",public,0123456789abcdef0123456789abcdef,10,\n")
CONFIGS = "name,model,provider,variant,params\nold,m-a,none,first,{}\nnew,m-b,none,longest,{}\n"


def make_tree(root: Path, *, problem: str = "A plain problem.", validated: bool = False, register: bool = False,
              data: str = "full", decision: str | None = None, decision_validated: bool = True,
              result_id: str = "synth/run-1/diff/share", change_card_after: bool = False) -> Path:
    """A minimal repository with one experiment, ``synth``; returns its root."""
    shutil.copytree(ROOT / "lab", root / "lab", ignore=shutil.ignore_patterns("corpora", "corpus", "experiments"))
    (root / "exocortex/lab").mkdir(parents=True)
    (root / "exocortex/lab/card_compiler.py").write_text("# stub\n", encoding="utf-8")
    (root / "exocortex/lab/gates.py").write_text("# stub\n", encoding="utf-8")
    for lang, other in (("pl", "en"), ("en", "pl")):
        d = root / "dowody" / lang / "experiments" / "synth"
        d.mkdir(parents=True)
        (d / "hypothesis.md").write_text(CARD.format(lang=lang, other=other, problem=problem,
                                                     validated=str(validated).lower()), encoding="utf-8")
    if register:
        pl = (root / "dowody/pl/experiments/synth/hypothesis.md").read_text(encoding="utf-8")
        en = (root / "dowody/en/experiments/synth/hypothesis.md").read_text(encoding="utf-8")
        prereg.append(root / "dowody/prereg.jsonl", {
            "algorithm": prereg.ALGORITHM, "slug": "synth", "version": 1, "sha256": prereg.card_hash(pl, en),
            "registered_at": "2026-09-29T10:00:00+00:00",
            "files": {"pl": "pl/experiments/synth/hypothesis.md", "en": "en/experiments/synth/hypothesis.md"}})
    if change_card_after:
        p = root / "dowody/en/experiments/synth/hypothesis.md"
        p.write_text(p.read_text(encoding="utf-8").replace("the share rises", "the share rises a lot"),
                     encoding="utf-8")
    folder = root / "dowody/data/synth"
    if data != "none":
        folder.mkdir(parents=True)
        (folder / "samples.csv").write_text(SAMPLES, encoding="utf-8")
    if data == "full":
        (folder / "metrics.csv").write_text(METRICS, encoding="utf-8")
        (folder / "runs.csv").write_text(RUNS, encoding="utf-8")
        (folder / "configs.csv").write_text(CONFIGS, encoding="utf-8")
        (folder / "datapackage.json").write_text('{"exocortex": {"recompute": "python lab/recompute.py synth"}}',
                                                 encoding="utf-8")
    if decision:
        for lang, other in (("pl", "en"), ("en", "pl")):
            (root / "dowody" / lang / "experiments/synth/gate-g1.md").write_text(
                GATE.format(lang=lang, other=other, decision=decision, validated=str(decision_validated).lower(),
                            rc='"after more data"' if decision == "NOT-NOW" else "null", ids=result_id),
                encoding="utf-8")
    return root


def status_of(compiled: cc.Compiled, lang: str = "en") -> dict:
    return next(s for s in sentences(card_yaml(compiled, lang)) if "project status is" in s["text"]
                or "status projektu to" in s["text"])


def test_a_card_without_a_decision_never_says_go(tmp_path):
    for register in (False, True):
        root = make_tree(tmp_path / f"repo{register}", validated=register, register=register)
        compiled = compile_to(tmp_path / f"o{register}", "synth", root)
        assert compiled.ok, compiled.checks
        assert compiled.status == ("frozen" if register else "draft")
        for lang in cc.LANGS:
            text = status_of(compiled, lang)["text"]
            assert not re.search(r"\b(GO|NO-GO|PIVOT|NOT-NOW|CLOSED)\b", text), text


def test_project_status_is_never_higher_than_the_last_decision():
    assert cc.project_status("draft", None) == "draft"
    assert cc.project_status("frozen", None) == "frozen"
    for decision in cc.DECISIONS:
        assert cc.project_status("frozen", decision) == decision
    with pytest.raises(ValueError):
        cc.project_status("frozen", "frozen")
    # a card that is not frozen reads as a draft, whatever else is said
    assert cc.project_status("changed", None) == "draft"


def test_an_applied_decision_sets_the_status_and_its_sources(tmp_path):
    root = make_tree(tmp_path / "repo", validated=True, register=True, decision="GO")
    compiled = compile_to(tmp_path, "synth", root)
    assert compiled.ok, compiled.checks
    assert compiled.status == "GO"
    st = status_of(compiled)
    assert "GO at gate G1" in st["text"] and st["source"]["file"] == "dowody/en/experiments/synth/gate-g1.md"
    assert status_of(compiled, "pl")["source"]["file"] == "dowody/pl/experiments/synth/gate-g1.md"
    texts = " ".join(s["text"] for s in sentences(card_yaml(compiled, "en")))
    assert "is GO" in texts and "synth/run-1/diff/share" in texts


def test_not_now_carries_its_return_condition(tmp_path):
    root = make_tree(tmp_path / "repo", validated=True, register=True, decision="NOT-NOW")
    compiled = compile_to(tmp_path, "synth", root)
    assert compiled.status == "NOT-NOW"
    assert any(s["text"] == "Return condition: after more data" for s in sentences(card_yaml(compiled, "en")))


@pytest.mark.parametrize("case", ["not_validated", "unknown_result", "card_changed", "card_unregistered"])
def test_a_decision_that_the_gate_would_refuse_does_not_set_the_status(tmp_path, case):
    kw: dict = {"validated": True, "register": True, "decision": "GO"}
    if case == "not_validated":
        kw["decision_validated"] = False
    elif case == "unknown_result":
        kw["result_id"] = "synth/run-9/diff/share"
    elif case == "card_changed":
        kw["change_card_after"] = True
    else:
        kw["register"] = False
    compiled = compile_to(tmp_path, "synth", make_tree(tmp_path / "repo", **kw))
    assert compiled.ok, compiled.checks
    assert compiled.status == ("draft" if case in ("card_changed", "card_unregistered") else "frozen")
    assert compiled.status not in cc.DECISIONS
    texts = [s["text"] for s in sentences(card_yaml(compiled, "en"))]
    assert any("is not applied" in t for t in texts)
    assert not any("is GO" in t for t in texts)


def test_a_changed_card_is_treated_as_a_draft(tmp_path):
    compiled = compile_to(tmp_path, "synth", make_tree(tmp_path / "repo", validated=True, register=True,
                                                       change_card_after=True))
    assert compiled.status == "draft"
    assert any("no longer matches the registered checksum" in s["text"] for s in sentences(card_yaml(compiled, "en")))


def test_synthetic_experiment_with_results_passes_every_check(tmp_path):
    compiled = compile_to(tmp_path, "synth", make_tree(tmp_path / "repo", validated=True, register=True))
    assert compiled.ok, compiled.checks
    en = card_yaml(compiled, "en")
    result = next(s for s in sentences(en) if s["source"].get("data", "").endswith("metrics.csv")
                  and "share_difference" in s["text"] and "was 0.500" in s["text"])
    assert "comparing `new` with `old`" in result["text"] and "n = 10" in result["text"]


def test_experiment_without_runs_says_so_and_cites_what_exists(tmp_path):
    compiled = compile_to(tmp_path, "synth", make_tree(tmp_path / "repo", data="samples-only"))
    assert compiled.ok, compiled.checks
    en = card_yaml(compiled, "en")
    texts = {s["id"]: [x["text"] for x in s["statements"]] for s in en["sections"]}
    assert f"As of {AS_OF}, no result of this experiment has been published: there is no run and no metric yet." \
        in texts["results"]
    assert f"As of {AS_OF}, no run is recorded for this experiment." in texts["experiments_and_iterations"]
    results = next(s for s in en["sections"] if s["id"] == "results")["statements"]
    assert results[0]["source"]["data"] == "dowody/data/synth/samples.csv"
    assert any("no data package" in t for t in texts["how_to_verify"])


def test_experiment_with_nothing_to_cite_is_an_error_not_an_invention(tmp_path):
    root = make_tree(tmp_path / "repo", data="none")
    with pytest.raises(cc.CompileError, match="nothing to cite for the results section"):
        compile_to(tmp_path, "synth", root)


def test_missing_language_version_is_an_error(tmp_path):
    root = make_tree(tmp_path / "repo")
    (root / "dowody/pl/experiments/synth/hypothesis.md").unlink()
    with pytest.raises(cc.CompileError, match="no hypothesis card"):
        compile_to(tmp_path, "synth", root)


def test_bad_slug_and_date_are_refused(tmp_path):
    with pytest.raises(cc.CompileError):
        cc.compile_card("../x", out=tmp_path, as_of=AS_OF)
    with pytest.raises(cc.CompileError):
        cc.compile_card("toy-length", out=tmp_path, as_of="1 October")


def test_the_compiler_makes_no_model_or_network_calls():
    source = (ROOT / "exocortex/lab/card_compiler.py").read_text(encoding="utf-8")
    for forbidden in ("llm", "httpx", "requests", "urllib", "socket", "psycopg", "subprocess"):
        assert not re.search(rf"^\s*(import|from)\s+\S*{forbidden}", source, re.MULTILINE), forbidden
