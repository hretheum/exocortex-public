# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Tests for area_digest / backlog_health perspective_type
wiring in synthesizer.py + night_shift_briefing corpus_digest wiring."""

from __future__ import annotations

import os
from unittest.mock import patch

os.environ.setdefault("TENANT_ID", "00000000-0000-0000-0000-000000000000")
os.environ.setdefault("EXOCORTEX_VAULT_PATH", "/tmp/exocortex-test-vault")

TENANT = "00000000-0000-0000-0000-000000000000"


# ─────────────────────────── registration ───────────────────────────


def test_corpus_perspectives_registered():
    from exocortex import synthesizer
    for ptype in ("area_digest", "backlog_health"):
        assert ptype in synthesizer.PERSPECTIVE_TYPES
        assert ptype in synthesizer._SELECTORS
        assert ptype in synthesizer.THRESHOLDS
    assert synthesizer.THRESHOLDS["area_digest"] == 3
    assert synthesizer.THRESHOLDS["backlog_health"] == 10


def test_corpus_perspectives_registered_in_runtime_registry():
    from exocortex.core.registry import Registry
    from exocortex.synth.runner import setup_builtins
    reg = Registry()
    setup_builtins(reg)
    assert "area_digest" in reg.perspectives
    assert "backlog_health" in reg.perspectives


# ─────────────────────────── selectors ───────────────────────────


def test_select_thoughts_for_area_digest_filters_by_section_path():
    from exocortex import synthesizer
    with patch("exocortex.synthesizer.query", return_value=[{"id": "t1"}]) as mock_query:
        result = synthesizer._select_thoughts_for_area_digest(TENANT, "globex")
    assert result == [{"id": "t1"}]
    sql, tenant_arg, key_arg = mock_query.call_args[0]
    assert "thought_type = 'vault_note'" in sql
    assert "section_path" in sql
    assert tenant_arg == TENANT
    assert key_arg == "globex"


def test_select_thoughts_for_backlog_health_filters_by_area():
    from exocortex import synthesizer
    with patch("exocortex.synthesizer.query", return_value=[{"id": "b1"}]) as mock_query:
        result = synthesizer._select_thoughts_for_backlog_health(TENANT, "_second-brain")
    assert result == [{"id": "b1"}]
    sql, _tenant_arg, key_arg = mock_query.call_args[0]
    assert "thought_type = 'backlog_item'" in sql
    assert "metadata->>'area'" in sql
    assert key_arg == "_second-brain"


# ─────────────────────────── prompt builders ───────────────────────────


def test_build_area_digest_prompt_counts_wikilinks_touching_area():
    from exocortex.synthesizer import _build_area_digest_prompt
    thoughts = [
        {"id": "d1", "body": "treść 1", "metadata": {"title": "Doc 1", "vault_path": "a/d1.md"}},
        {"id": "d2", "body": "treść 2", "metadata": {"title": "Doc 2", "vault_path": "a/d2.md"}},
    ]
    edges = [
        {"type": "wikilink_to", "src_id": "d1", "dst_id": "d2"},
        {"type": "wikilink_to", "src_id": "d1", "dst_id": "outside"},
        {"type": "blocked_by", "src_id": "d1", "dst_id": "d2"},  # wrong type, must not count
    ]
    prompt = _build_area_digest_prompt(thoughts, "globex", edges)
    assert "Obszar: globex" in prompt
    assert "Liczba dokumentów: 2" in prompt
    assert "Wikilinki dotykające ten obszar: 2" in prompt
    assert "Doc 1" in prompt and "Doc 2" in prompt
    assert "area_digest_synthesis" in prompt


def test_build_backlog_health_prompt_ranks_top_blockers():
    from exocortex.synthesizer import _build_backlog_health_prompt
    thoughts = [
        {"id": "b1", "body": "opis", "created_at": "2026-01-01",
         "metadata": {"ticket_id": "T1", "status": "pending", "priority": "HIGH",
                      "blocked_by_ids": ["T0"]}},
        {"id": "b2", "body": "opis", "created_at": "2026-01-02",
         "metadata": {"ticket_id": "T2", "status": "done", "priority": "LOW",
                      "blocked_by_ids": ["T0"]}},
    ]
    prompt = _build_backlog_health_prompt(thoughts, "globex", edges=[])
    assert "Obszar backlogu: globex" in prompt
    assert "Liczba pozycji: 2" in prompt
    assert "T0 (blokuje 2)" in prompt
    assert "backlog_health_synthesis" in prompt


def test_build_user_prompt_dispatches_to_area_digest():
    from exocortex.synthesizer import build_user_prompt
    thoughts = [{"id": "d1", "body": "x", "metadata": {"title": "D", "vault_path": "p"}}]
    prompt = build_user_prompt("area_digest", "globex", thoughts, edges=[])
    assert "area_digest_synthesis" in prompt


def test_build_user_prompt_dispatches_to_backlog_health():
    from exocortex.synthesizer import build_user_prompt
    thoughts = [{"id": "b1", "body": "x", "created_at": "2026-01-01",
                "metadata": {"ticket_id": "T1", "blocked_by_ids": []}}]
    prompt = build_user_prompt("backlog_health", "globex", thoughts, edges=[])
    assert "backlog_health_synthesis" in prompt


# ─────────────────────────── coercers (defensive normalization) ───────────


def test_coerce_area_digest_handles_well_formed_input():
    from exocortex.synthesizer import _coerce_area_digest
    raw = {
        "stan_dzis": "Obszar dokumentuje strategię.",
        "dokumenty_wyrozniajace_sie": [{"tytul": "ADR-1", "powod": "decyzja"}],
        "powiazania": ["Doc A łączy się z Doc B"],
    }
    out = _coerce_area_digest(raw)
    assert out["stan_dzis"] == "Obszar dokumentuje strategię."
    assert out["dokumenty_wyrozniajace_sie"] == [{"tytul": "ADR-1", "powod": "decyzja"}]
    assert out["powiazania"] == ["Doc A łączy się z Doc B"]


def test_coerce_area_digest_defensive_against_garbage():
    from exocortex.synthesizer import _coerce_area_digest
    assert _coerce_area_digest(None) == {
        "stan_dzis": "", "dokumenty_wyrozniajace_sie": [], "powiazania": [],
    }
    out = _coerce_area_digest({
        "stan_dzis": None,
        "dokumenty_wyrozniajace_sie": "not-a-list",
        "powiazania": [{"nested": "dict, not a str/int"}],
    })
    assert out["stan_dzis"] == ""
    assert out["dokumenty_wyrozniajace_sie"] == []
    assert out["powiazania"] == []  # dict entries filtered out, not stringified


def test_coerce_backlog_health_handles_well_formed_input():
    from exocortex.synthesizer import _coerce_backlog_health
    raw = {
        "stan_dzis": "556 pozycji, dużo archiwalnych.",
        "zaleglosci": [{"ticket": "F34.2", "opis": "brak ruchu"}],
        "lancuchy_blokad": [{"ticket": "T0", "blokuje_ile": 2, "opis": "wąskie gardło"}],
    }
    out = _coerce_backlog_health(raw)
    assert out["zaleglosci"] == [{"ticket": "F34.2", "opis": "brak ruchu"}]
    assert out["lancuchy_blokad"] == [{"ticket": "T0", "blokuje_ile": 2, "opis": "wąskie gardło"}]


def test_coerce_backlog_health_defensive_against_garbage():
    from exocortex.synthesizer import _coerce_backlog_health
    out = _coerce_backlog_health({
        "stan_dzis": 123,  # not a str
        "zaleglosci": None,
        "lancuchy_blokad": [{"ticket": "T0", "blokuje_ile": "nie-liczba", "opis": "x"}],
    })
    assert out["stan_dzis"] == "123"
    assert out["zaleglosci"] == []
    assert out["lancuchy_blokad"] == [{"ticket": "T0", "blokuje_ile": 0, "opis": "x"}]


# ─────────────────────────── synthesize() coercion dispatch ───────────────


def test_synthesize_uses_area_digest_coercer():
    from exocortex import synthesizer
    thoughts = [{"id": f"d{i}", "body": "x", "created_at": "2026-01-01",
                "metadata": {"title": "D", "vault_path": "p", "section_path": ["work", "globex"]}}
               for i in range(3)]
    with patch("exocortex.synthesizer.select_source_thoughts", return_value=thoughts), \
         patch("exocortex.synthesizer.fetch_edges_for_thoughts", return_value=[]), \
         patch("exocortex.synthesizer.get_active_synthesis", return_value=None), \
         patch("exocortex.synthesizer.call_llm", return_value=(
             {"stan_dzis": "ok", "dokumenty_wyrozniajace_sie": [], "powiazania": []},
             {"input_tokens": 1, "output_tokens": 1, "cache_creation_input_tokens": 0,
              "cache_read_input_tokens": 0, "_cost_usd": 0.0},
         )), \
         patch("exocortex.synthesizer.persist_synthesis", return_value="new-id"):
        result = synthesizer.synthesize("area_digest", "globex", thoughts, tenant_id=TENANT)
    assert result.status == "ok"
    assert result.content["stan_dzis"] == "ok"
    assert "dokumenty_wyrozniajace_sie" in result.content
    # Must NOT have leaked the meeting-shaped fields.
    assert "recent_decisions" not in result.content


# ─────────────────────────── discover_perspectives ───────────────────────


def test_discover_perspectives_finds_area_digest_and_backlog_health():
    from exocortex import synthesizer

    def fake_query(sql, *args, **kwargs):
        if "section_path'->>1" in sql and "vault_note" in sql:
            return [{"area": "globex", "n": 5}, {"area": "howto", "n": 1}]  # 1 below threshold
        if "metadata->>'area'" in sql and "backlog_item" in sql:
            return [{"area": "_second-brain", "n": 20}, {"area": None, "n": 169}]
        return []

    with patch("exocortex.synthesizer.query", side_effect=fake_query):
        found = synthesizer.discover_perspectives(TENANT)

    found_by_type = {(t, k) for t, k, _ in found}
    assert ("area_digest", "globex") in found_by_type
    assert ("area_digest", "howto") not in found_by_type  # below threshold (1 < 3)
    assert ("backlog_health", "_second-brain") in found_by_type
    assert ("backlog_health", None) not in found_by_type  # null area excluded


# ─────────────────────────── night_shift_briefing wiring ─────────────────


def test_fetch_corpus_digest_formats_area_and_backlog_entries():
    from workers.night_shift_briefing import fetch_corpus_digest

    rows = [
        {"perspective_type": "area_digest", "perspective_key": "globex",
         "content": {"stan_dzis": "stan A",
                     "dokumenty_wyrozniajace_sie": [{"tytul": "ADR-1", "powod": "decyzja"}]}},
        {"perspective_type": "backlog_health", "perspective_key": "_second-brain",
         "content": {"stan_dzis": "stan B",
                     "zaleglosci": [{"ticket": "F34.2", "opis": "brak ruchu"}]}},
    ]
    with patch("exocortex.db.query", return_value=rows):
        digest = fetch_corpus_digest(window_hours=24)

    assert "obszar globex — stan A" in digest
    assert any("ADR-1: decyzja" in d for d in digest)
    assert "backlog _second-brain — stan B" in digest
    assert any("F34.2: brak ruchu" in d for d in digest)


def test_fetch_corpus_digest_degrades_gracefully_on_db_error():
    from workers.night_shift_briefing import fetch_corpus_digest
    with patch("exocortex.db.query", side_effect=RuntimeError("db down")):
        digest = fetch_corpus_digest(window_hours=24)
    assert digest == []


def test_format_telegram_message_renders_corpus_digest_section():
    from workers.night_shift_briefing import format_telegram_message
    content = {
        "narrative_pl": "Test.",
        "patterns": [], "contradictions_list": [], "action_items_due": [],
        "corpus_digest": ["obszar globex — stan", "  ADR-1: decyzja"],
    }
    text = format_telegram_message(content, "2026-07-31")
    assert "Z korpusu" in text
    assert "obszar globex" in text


def test_format_telegram_message_omits_corpus_section_when_empty():
    from workers.night_shift_briefing import format_telegram_message
    content = {
        "narrative_pl": "Test.",
        "patterns": [], "contradictions_list": [], "action_items_due": [],
        "corpus_digest": [],
    }
    text = format_telegram_message(content, "2026-07-31")
    assert "Z korpusu" not in text


def test_empty_content_includes_corpus_digest_key():
    from workers.night_shift_briefing import _empty_content
    assert _empty_content()["corpus_digest"] == []
