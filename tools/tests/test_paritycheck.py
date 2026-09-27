from pathlib import Path

import pytest

from tools.paritycheck.core import check

PL = """---
id: t1
lang: pl
counterpart: ../../en/notes/t1.md
status: todo
depends_on: [F0.1]
---

# Tytuł

Próg wynosi 0,40 przy 11 613 skrótach. Zobacz [cykl](../01-cycle.md).

## Tabela

| a | b |
|---|---|
| 1 | 2 |
"""

EN = """---
id: t1
lang: en
counterpart: ../../pl/notes/t1.md
status: todo
depends_on: [F0.1]
---

# Title

The threshold is 0.40 with 11,613 hashes. See [the cycle](../01-cycle.md).

## Table

| a | b |
|---|---|
| 1 | 2 |
"""


def tree(tmp_path: Path, pl: str | None = PL, en: str | None = EN) -> Path:
    for lang, text in (("pl", pl), ("en", en)):
        if text is not None:
            p = tmp_path / lang / "notes" / "t1.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
    return tmp_path


def test_matching_pair_passes(tmp_path):
    res = check(tree(tmp_path))
    assert res.pairs == 1 and res.ok, [str(p) for p in res.problems]


def test_missing_pair(tmp_path):
    res = check(tree(tmp_path, en=None))
    assert [p.check for p in res.problems] == ["pair"]


def test_different_number(tmp_path):
    res = check(tree(tmp_path, en=EN.replace("0.40", "0.45")))
    assert [p.check for p in res.problems] == ["numbers"]


def test_missing_heading(tmp_path):
    res = check(tree(tmp_path, en=EN.replace("## Table\n", "")))
    assert "headings" in [p.check for p in res.problems]


def test_front_matter_and_links(tmp_path):
    res = check(tree(tmp_path, en=EN.replace("status: todo", "status: done").replace("../01-cycle.md", "../02-roadmap.md")))
    assert {p.check for p in res.problems} == {"front matter", "links"}


def test_wiki_links_rejected(tmp_path):
    res = check(tree(tmp_path, pl=PL.replace("[cykl](../01-cycle.md)", "[[01-cycle]] [cykl](../01-cycle.md)")))
    assert any("wiki link" in p.detail for p in res.problems)


def test_repository_documents_pass():
    root = Path(__file__).resolve().parents[2] / "dowody"
    if not root.is_dir():
        pytest.skip("dowody/ not present in this checkout")
    res = check(root)
    assert res.ok, [str(p) for p in res.problems]
