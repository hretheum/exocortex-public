# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for wiki/domains/work/__init__.py::_summarize_workdash.

_summarize_workdash used to call the Anthropic cloud API directly
(os.environ['ANTHROPIC_API_KEY']) — the only LLM call site in the codebase
that bypassed llm_router. Rerouted onto llm_router.call_tool() so it goes
through the same local-only (K12: 127.0.0.1:8080) path as every other call."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault("TENANT_ID", "test-tenant")

from exocortex.wiki.domains.work import _summarize_workdash


def _fake_usage(input_tokens=50, output_tokens=30):
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    return usage


def test_summarize_workdash_routes_through_llm_router():
    meetings = [
        {"projects": ["GLOBEX"], "meeting_type": "status", "date": "2026-07-01"},
        {"projects": ["GLOBEX"], "meeting_type": "one-on-one", "date": "2026-07-15"},
    ]
    with patch("exocortex.llm_routing.initialize") as init, \
         patch("llm_router.call_tool",
               return_value=({"summary": "Dużo pracy nad GLOBEX."}, _fake_usage())) as call:
        summary, tokens = _summarize_workdash(meetings)
    init.assert_called_once()
    call.assert_called_once()
    kwargs = call.call_args.kwargs
    assert kwargs["schema"]["name"] == "workdash_summary"
    assert "GLOBEX" in kwargs["user"]
    assert summary == "Dużo pracy nad GLOBEX."
    assert tokens == 80


def test_summarize_workdash_prompt_does_not_contradict_tool_calling():
    """Regression: zadanie-20 found that instructing the model to answer
    with raw JSON while forcing tool_choice reliably breaks tool-calling
    (0/5 vs 5/5 on the same model/schema). Guard against reintroducing that
    pattern here."""
    meetings = [{"projects": [], "meeting_type": None, "date": None}]
    with patch("exocortex.llm_routing.initialize"), \
         patch("llm_router.call_tool",
               return_value=({"summary": "ok"}, _fake_usage())) as call:
        _summarize_workdash(meetings)
    system = call.call_args.kwargs["system"]
    assert "czysty JSON" not in system
    assert "```json" not in system


def test_summarize_workdash_never_touches_anthropic_api_key():
    """The whole point of the fix: no direct Anthropic client, regardless
    of whether ANTHROPIC_API_KEY happens to be set in the environment."""
    meetings = [{"projects": [], "meeting_type": None, "date": None}]
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        with patch("exocortex.llm_routing.initialize"), \
             patch("llm_router.call_tool",
                   return_value=({"summary": "ok"}, _fake_usage())):
            summary, _ = _summarize_workdash(meetings)
    assert summary == "ok"
