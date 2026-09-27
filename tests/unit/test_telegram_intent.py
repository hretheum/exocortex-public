# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.4.1 — Unit tests for the LLM intent classifier."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _stub_llm_router(monkeypatch):
    """Install fake ``llm_router`` + ``exocortex.llm_routing`` modules and
    reset the lru_cache between tests so each test sees a fresh call count."""
    # Fake llm_router with a swappable call_tool.
    fake_router = types.ModuleType("llm_router")
    fake_router.call_tool = MagicMock()
    monkeypatch.setitem(sys.modules, "llm_router", fake_router)

    # Fake exocortex.llm_routing with a no-op initialize().
    fake_routing = types.ModuleType("exocortex.llm_routing")
    fake_routing.initialize = MagicMock()
    monkeypatch.setitem(sys.modules, "exocortex.llm_routing", fake_routing)

    # Reload the intent module so its top-level imports bind to the stubs and
    # the lru_cache is empty.
    sys.modules.pop("exocortex.telegram_intent", None)
    from exocortex import telegram_intent as _ti  # noqa: WPS433
    _ti.classify_intent_llm.cache_clear()
    yield fake_router, _ti
    sys.modules.pop("exocortex.telegram_intent", None)


def _set_response(fake_router, tool: str, confidence: float) -> None:
    fake_router.call_tool.return_value = ({"tool": tool, "confidence": confidence}, {})


# ─────────────────────────── happy path ───────────────────────────


@pytest.mark.parametrize(
    "text,tool",
    [
        ("co Ola myślała o Q4", "ask"),
        ("znajdź notatki o GLOBEX", "search"),
        ("co mam dzisiaj do zrobienia", "action_items"),
        ("gdzie są sprzeczności w postach", "find_contradictions"),
        ("czy to prawda że Ola zatwierdziła remediation", "graph_fact_check"),
        ("podsumuj decyzje z ostatniego tygodnia", "ask"),
        ("list all clients", "search"),
        ("show open tasks", "action_items"),
        ("are these statements consistent", "find_contradictions"),
        ("verify: GLOBEX budget was 1M PLN", "graph_fact_check"),
    ],
)
def test_classify_returns_high_confidence_tool(_stub_llm_router, text, tool):
    fake_router, ti = _stub_llm_router
    _set_response(fake_router, tool, 0.85)
    assert ti.classify_intent_llm(text) == tool


# ─────────────────────────── low confidence / bad output ───────────────────────────


def test_low_confidence_returns_unknown(_stub_llm_router):
    fake_router, ti = _stub_llm_router
    _set_response(fake_router, "ask", 0.42)
    assert ti.classify_intent_llm("ambiguous thing") == "unknown"


def test_unknown_tool_returns_unknown(_stub_llm_router):
    fake_router, ti = _stub_llm_router
    _set_response(fake_router, "clarify", 0.9)
    assert ti.classify_intent_llm("dziwna sprawa") == "unknown"


def test_call_tool_exception_returns_unknown(_stub_llm_router):
    fake_router, ti = _stub_llm_router
    fake_router.call_tool.side_effect = RuntimeError("network down")
    assert ti.classify_intent_llm("anything") == "unknown"


def test_non_dict_response_returns_unknown(_stub_llm_router):
    fake_router, ti = _stub_llm_router
    fake_router.call_tool.return_value = ("not a dict", {})
    assert ti.classify_intent_llm("foo") == "unknown"


def test_non_numeric_confidence_returns_unknown(_stub_llm_router):
    fake_router, ti = _stub_llm_router
    fake_router.call_tool.return_value = (
        {"tool": "ask", "confidence": "not-a-number"},
        {},
    )
    assert ti.classify_intent_llm("foo") == "unknown"


def test_empty_text_returns_unknown_without_llm_call(_stub_llm_router):
    fake_router, ti = _stub_llm_router
    assert ti.classify_intent_llm("") == "unknown"
    assert ti.classify_intent_llm("   ") == "unknown"
    fake_router.call_tool.assert_not_called()


# ─────────────────────────── cache behaviour ───────────────────────────


def test_lru_cache_collapses_repeated_calls(_stub_llm_router):
    fake_router, ti = _stub_llm_router
    _set_response(fake_router, "ask", 0.9)
    ti.classify_intent_llm("same text")
    ti.classify_intent_llm("same text")
    ti.classify_intent_llm("same text")
    assert fake_router.call_tool.call_count == 1


def test_lru_cache_distinguishes_inputs(_stub_llm_router):
    fake_router, ti = _stub_llm_router
    _set_response(fake_router, "ask", 0.9)
    ti.classify_intent_llm("question one")
    ti.classify_intent_llm("question two")
    assert fake_router.call_tool.call_count == 2


# ─────────────────────────── boundary: confidence exactly at floor ───────────────────────────


def test_confidence_at_floor_accepted(_stub_llm_router):
    fake_router, ti = _stub_llm_router
    _set_response(fake_router, "ask", 0.6)
    assert ti.classify_intent_llm("borderline") == "ask"


def test_confidence_just_below_floor_rejected(_stub_llm_router):
    fake_router, ti = _stub_llm_router
    _set_response(fake_router, "ask", 0.599)
    assert ti.classify_intent_llm("borderline-low") == "unknown"
