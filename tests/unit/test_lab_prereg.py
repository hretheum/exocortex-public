# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Checksums of hypothesis cards and the append-only registry (roadmap task F2.4)."""
from __future__ import annotations

import pytest

from exocortex.lab import prereg

CARD = """---
type: hypothesis_card
lang: {lang}
slug: toy
version: 1
prereg_hash: {hash}
human_validated: {validated}
---

# Hypothesis: toy

| Role | Metric | Threshold |
|---|---|---|
| deciding | share | at least 0.30 |
"""


def _card(lang="pl", validated="false", hash_="null", body_extra=""):
    return CARD.format(lang=lang, validated=validated, hash=hash_) + body_extra


def test_approval_and_the_hash_field_do_not_change_the_checksum():
    draft = prereg.card_hash(_card("pl"), _card("en"))
    approved = prereg.card_hash(_card("pl", "true"), _card("en", "true", "a" * 64))
    assert draft == approved


def test_any_change_of_content_changes_the_checksum():
    base = prereg.card_hash(_card("pl"), _card("en"))
    assert prereg.card_hash(_card("pl").replace("0.30", "0.25"), _card("en")) != base
    assert prereg.card_hash(_card("pl"), _card("en").replace("toy", "toys")) != base
    assert prereg.card_hash(_card("en"), _card("pl")) != base  # the languages are not interchangeable


def test_whitespace_line_endings_and_unicode_form_do_not_count():
    base = prereg.card_hash(_card("pl", body_extra="Zażółć\n"), _card("en"))
    crlf = _card("pl", body_extra="Zażółć\n").replace("\n", "\r\n") + "\r\n\r\n"
    trailing = _card("pl", body_extra="Zażółć   \n")
    decomposed = _card("pl", body_extra="Zażółć\n")  # same letters, NFD
    for variant in (crlf, trailing, decomposed):
        assert prereg.card_hash(variant, _card("en")) == base


def test_registry_is_append_only(tmp_path):
    reg = tmp_path / "prereg.jsonl"
    prereg.append(reg, {"slug": "toy", "version": 1, "sha256": "a" * 64})
    prereg.append(reg, {"slug": "toy", "version": 2, "sha256": "b" * 64})
    with pytest.raises(ValueError):
        prereg.append(reg, {"slug": "toy", "version": 1, "sha256": "c" * 64})
    assert [e["version"] for e in prereg.read_registry(reg)] == [1, 2]
    old = '{"a": 1}\n'
    assert prereg.is_append_only(old, old + '{"b": 2}\n')
    assert not prereg.is_append_only(old + '{"b": 2}\n', old)
    assert not prereg.is_append_only(old, '{"a": 2}\n')


def test_verify_recomputes_from_files(tmp_path):
    for lang in ("pl", "en"):
        f = tmp_path / lang / "experiments" / "toy" / "hypothesis.md"
        f.parent.mkdir(parents=True)
        f.write_text(_card(lang, "true"), encoding="utf-8")
    entry = {"slug": "toy", "version": 1, "sha256": prereg.card_hash(_card("pl"), _card("en")),
             "files": {"pl": "pl/experiments/toy/hypothesis.md", "en": "en/experiments/toy/hypothesis.md"}}
    assert prereg.verify(tmp_path, [entry])[0]["status"] == "ok"
    (tmp_path / "pl/experiments/toy/hypothesis.md").write_text(_card("pl", "true").replace("0.30", "0.20"))
    assert prereg.verify(tmp_path, [entry])[0]["status"] == "changed"
    (tmp_path / "en/experiments/toy/hypothesis.md").unlink()
    assert prereg.verify(tmp_path, [entry])[0]["status"] == "missing"
