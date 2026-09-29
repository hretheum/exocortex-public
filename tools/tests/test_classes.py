import pytest

from tools.publisher.classes import (
    DOCS,
    DOCS_MAX_BYTES,
    EXPERIMENT,
    GENERATED,
    UNKNOWN,
    classify,
    classify_file,
)

SMALL = 2_000


@pytest.mark.parametrize("lang", ["pl", "en"])
@pytest.mark.parametrize("rel", [
    "01-cycle.md", "02-roadmap.md", "03-progress.md", "04-how-it-works.md", "05-publication-design.md",
    "06-interactive-lab-design.md", "roadmap/F1-public-repo.md", "roadmap/F1/F1.11-publication-classes.md",
    "templates/hypothesis-card.md", "img/9-quarantine.svg", "img/deeper/figure.svg",
])
def test_documentation_paths(lang, rel):
    assert classify(f"{lang}/{rel}", SMALL) == DOCS


@pytest.mark.parametrize("rel", [
    "pl/img/photo.png", "en/roadmap/tasks.csv", "pl/templates/run.py", "pl/roadmap/F1.MD", "en/img/figure.SVG",
    "pl/roadmap/notes.md.txt", "pl/03-progress.txt",
])
def test_documentation_paths_accept_only_md_and_svg(rel):
    assert classify(rel, SMALL) == UNKNOWN


def test_documentation_size_limit():
    assert classify("pl/03-progress.md", DOCS_MAX_BYTES) == DOCS
    assert classify("pl/03-progress.md", DOCS_MAX_BYTES + 1) == UNKNOWN
    assert classify("pl/img/1-overview.svg", DOCS_MAX_BYTES + 1) == UNKNOWN
    assert classify("pl/03-progress.md", None) == UNKNOWN  # size not known: strictest class
    assert classify("pl/03-progress.md", -1) == UNKNOWN
    assert classify("pl/03-progress.md", "1") == UNKNOWN


@pytest.mark.parametrize("rel", [
    "pl/experiments/intent-vs-fact/hypothesis.md", "en/experiments/intent-vs-fact/overview.md",
    "pl/experiments/toy-length/nested/run-1.md", "en/experiments/x/figure.svg", "data/toy-length/results.csv",
    "data/intent-vs-fact/datapackage.json", "data/x/deeper/file.bin", "prereg.jsonl",
])
def test_experiment_paths(rel):
    assert classify(rel, SMALL) == EXPERIMENT
    assert classify(rel, 10 * DOCS_MAX_BYTES) == EXPERIMENT  # no size limit outside documentation


@pytest.mark.parametrize("rel", ["pl/generated/radar.md", "en/generated/triage/2026-W40.md",
                                 "pl/generated/experiments/toy-length.md"])
def test_generated_paths(rel):
    assert classify(rel, SMALL) == GENERATED


@pytest.mark.parametrize("rel", [
    # the four areas that are never documentation, whatever the name or size
    "pl/experiments/x/01-cycle.md", "en/experiments/roadmap/roadmap/F1.md", "data/roadmap/03-progress.md",
    "pl/generated/03-progress.md", "en/generated/roadmap/F1.md", "prereg.jsonl",
])
def test_never_documentation(rel):
    assert classify(rel, 10) != DOCS


@pytest.mark.parametrize("rel", [
    "README.md", "glossary.md", "notes.md", "de/01-cycle.md", "PL/01-cycle.md", "pl/01-Cycle.md",
    "pl/sub/01-cycle.md", "pl/07-new-document.md", "pl/roadmap", "pl/generated", "pl/experiments/x.md",
    "pl/experiments/slug", "data/results.csv", "data", "pl/prereg.jsonl", "data/prereg.jsonl",
    "pl/roadmap/../experiments/x/card.md", "pl/./01-cycle.md", "/pl/01-cycle.md", "pl//01-cycle.md",
    "pl\\01-cycle.md", "pl/roadmap/.hidden.md", ".obsidian/workspace.json", "", "pl/",
])
def test_everything_else_is_unknown(rel):
    assert classify(rel, SMALL) == UNKNOWN


@pytest.mark.parametrize("rel", [None, 7, b"pl/01-cycle.md", ["pl", "01-cycle.md"]])
def test_errors_give_the_strictest_class(rel):
    assert classify(rel, SMALL) == UNKNOWN


def test_classify_file_reads_the_size(tmp_path):
    small, big = tmp_path / "a.md", tmp_path / "b.md"
    small.write_text("x\n")
    big.write_bytes(b"x" * (DOCS_MAX_BYTES + 1))
    assert classify_file("pl/03-progress.md", small) == DOCS
    assert classify_file("pl/03-progress.md", big) == UNKNOWN
    assert classify_file("pl/03-progress.md", tmp_path / "missing.md") == UNKNOWN
    assert classify_file("pl/generated/x.md", tmp_path / "missing.md") == GENERATED
