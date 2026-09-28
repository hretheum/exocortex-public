# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for F31.1.1 night_shift_briefing perspective."""
from __future__ import annotations

import json
import os

os.environ.setdefault("TENANT_ID", "test-tenant")

from dataclasses import dataclass, field
from typing import Any

from exocortex.core.registry import Registry
from exocortex.synth.perspectives.base import PerspectiveType
from exocortex.synth.perspectives.night_shift import (
    NightShiftBriefing,
    setup,
)


@dataclass
class _Ctx:
    tenant_id: str = "t1"
    perspective_key: str = "2026-05-24"
    edges: list[dict] = field(default_factory=list)
    inputs: dict[str, Any] | None = None


def test_perspective_name():
    assert NightShiftBriefing().name == "night_shift_briefing"


def test_is_perspective_type():
    assert isinstance(NightShiftBriefing(), PerspectiveType)


def test_setup_registers_perspective():
    reg = Registry()
    setup(reg)
    assert "night_shift_briefing" in reg.perspectives
    assert isinstance(reg.perspectives["night_shift_briefing"], NightShiftBriefing)


def test_select_thoughts_returns_inputs_as_single_pseudo_thought():
    p = NightShiftBriefing()
    ctx = _Ctx(inputs={"new_thoughts": [{"body": "x"}]})
    result = p.select_thoughts(ctx)
    assert len(result) == 1
    assert result[0] is ctx.inputs


def test_select_thoughts_missing_inputs_returns_empty():
    p = NightShiftBriefing()
    ctx = _Ctx(inputs=None)
    assert p.select_thoughts(ctx) == []


def test_build_prompt_contains_guardrail_keywords():
    p = NightShiftBriefing()
    prompt = p.build_prompt([{
        "new_thoughts": [],
        "new_contradictions": [],
        "overdue_actions": [],
        "pattern_spikes": [],
    }])
    # Guardrail markers from system prompt
    assert "GUARDRAIL" in prompt
    assert "2-5 zdań" in prompt
    assert "narrative_pl" in prompt
    assert "contradictions_list" in prompt
    # Output must instruct: contradictions as a list, never narrated.
    # Asserted in the prompt's own words — b2a9e97 ("drop technical jargon")
    # rewrote the wording from a shouted "AS A LIST" to a plain "as a list" and
    # this test kept asserting the old form, so it had been red ever since.
    assert "NIGDY" in prompt
    assert "jako listę" in prompt


def test_build_prompt_renders_all_sections():
    p = NightShiftBriefing()
    prompt = p.build_prompt([{
        "new_thoughts": [{"body": "Spotkanie z X o AI"}],
        "new_contradictions": ["plan A vs plan B"],
        "overdue_actions": ["Zadanie Y due 2026-05-20"],
        "pattern_spikes": ["tag AI x3"],
    }])
    assert "Spotkanie z X o AI" in prompt
    assert "plan A vs plan B" in prompt
    assert "Zadanie Y due 2026-05-20" in prompt
    assert "tag AI x3" in prompt


def test_build_prompt_instructs_tool_call_not_raw_json():
    """Regression test: the prompt must not instruct the model
    to answer with raw JSON — that directly contradicts the forced
    tool_choice used by workers/night_shift_briefing.py's call_llm() and
    reliably breaks tool-calling (confirmed empirically against the
    production model: 0/5 tool-calls with the raw-JSON instruction present,
    5/5 once it points at the tool instead)."""
    p = NightShiftBriefing()
    prompt = p.build_prompt([{
        "new_thoughts": [], "new_contradictions": [],
        "overdue_actions": [], "pattern_spikes": [],
    }])
    assert "czysty JSON" not in prompt
    assert "```json" not in prompt
    assert "wywołaj narzędzie" in prompt.lower()


def test_build_prompt_empty_input_does_not_crash():
    p = NightShiftBriefing()
    prompt = p.build_prompt([])
    assert "GUARDRAIL" in prompt
    assert "(brak)" in prompt


def test_parse_response_extracts_full_structure():
    p = NightShiftBriefing()
    raw = json.dumps({
        "narrative_pl": "Dziś dominował temat AI w rozmowach z klientami.",
        "contradictions_list": ["A vs B", "C vs D", "E vs F"],
        "action_items_due": ["Task X (due: 2026-05-20)"],
        "patterns": ["tag 'AI' x3"],
    })
    parsed = p.parse_response(raw)
    assert parsed["narrative_pl"].startswith("Dziś")
    assert parsed["contradictions_list"] == ["A vs B", "C vs D", "E vs F"]
    assert parsed["action_items_due"] == ["Task X (due: 2026-05-20)"]
    assert parsed["patterns"] == ["tag 'AI' x3"]


def test_parse_response_strips_code_fences():
    p = NightShiftBriefing()
    raw = "```json\n" + json.dumps({
        "narrative_pl": "ok",
        "contradictions_list": [],
        "action_items_due": [],
        "patterns": [],
    }) + "\n```"
    parsed = p.parse_response(raw)
    assert parsed["narrative_pl"] == "ok"


def test_parse_response_handles_malformed_json_with_fallback():
    p = NightShiftBriefing()
    parsed = p.parse_response("totally not json")
    # Empty / unparseable → fallback narrative + empty lists
    assert parsed["narrative_pl"] == "Brak istotnych wzorców w ostatnich 24h."
    assert parsed["contradictions_list"] == []
    assert parsed["action_items_due"] == []
    assert parsed["patterns"] == []


def test_parse_response_empty_response_uses_fallback_narrative():
    p = NightShiftBriefing()
    parsed = p.parse_response("")
    assert parsed["narrative_pl"] == "Brak istotnych wzorców w ostatnich 24h."


def test_guardrail_contradictions_as_list_not_in_narrative():
    """If the LLM correctly follows the guardrail, contradictions show up
    as ≥3 list entries and the narrative does not paraphrase them."""
    p = NightShiftBriefing()
    raw = json.dumps({
        "narrative_pl": (
            "W ostatnich 24h pojawiło się sporo aktywności wokół AI i strategii produktowej. "
            "Dominował temat priorytetów Q3 oraz roli zespołu platformowego."
        ),
        "contradictions_list": [
            "Roadmapa Q3 vs deklaracje na all-hands",
            "Plan zatrudnień vs budżet zatwierdzony",
            "ETA projektu X vs zależności od zespołu Y",
        ],
        "action_items_due": [],
        "patterns": [],
    })
    parsed = p.parse_response(raw)
    assert len(parsed["contradictions_list"]) >= 3
    narrative = parsed["narrative_pl"].lower()
    # Guardrail invariant: the narrative does not enumerate the contradictions
    for c in parsed["contradictions_list"]:
        assert c.lower() not in narrative
    # The narrative should not contain the trigger word 'sprzeczno' either
    assert "sprzeczno" not in narrative


def test_empty_input_graceful_no_crash():
    """Empty input dict → build_prompt + parse_response don't crash and
    fallback narrative is set."""
    p = NightShiftBriefing()
    ctx = _Ctx(inputs={})
    thoughts = p.select_thoughts(ctx)
    prompt = p.build_prompt(thoughts)
    assert "GUARDRAIL" in prompt
    parsed = p.parse_response("")
    assert parsed["narrative_pl"] == "Brak istotnych wzorców w ostatnich 24h."


def test_parse_response_drops_non_string_list_items_gracefully():
    p = NightShiftBriefing()
    raw = json.dumps({
        "narrative_pl": "ok",
        "contradictions_list": ["A vs B", {"x": 1}, ""],
        "action_items_due": "not-a-list",
        "patterns": [None, "valid"],
    })
    parsed = p.parse_response(raw)
    # str entries kept, empty dropped, dicts serialised to JSON string
    assert "A vs B" in parsed["contradictions_list"]
    assert any(s.startswith("{") for s in parsed["contradictions_list"])
    assert "" not in parsed["contradictions_list"]
    # non-list field coerced to []
    assert parsed["action_items_due"] == []
    # None dropped, valid kept
    assert parsed["patterns"] == ["valid"]
