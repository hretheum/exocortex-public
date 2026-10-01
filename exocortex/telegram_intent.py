# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.4.1 — LLM intent classifier (fallback when regex returns 'unknown').

The regex tier in :mod:`exocortex.telegram_bot` is fast but rigid; ambiguous
phrasings ("what did my colleague think about Q4?", "contradictions in posts
about GLOBEX") fall through to ``unknown`` and the bot blindly defaults to
``ask``. This module adds a cheap LLM disambiguator (Qwen via ``llm_router``)
that only fires for unknowns, with a strict confidence floor so we route to
``ask`` rather than mis-route.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

log = logging.getLogger("exocortex.telegram_intent")

_TOOLS = (
    "ask",
    "search",
    "action_items",
    "find_contradictions",
    "graph_fact_check",
)

_CONFIDENCE_FLOOR = 0.6

_SYSTEM_PROMPT = (
    "You are an intent router for a personal knowledge base bot. Given a user "
    "message in Polish or English, classify which tool should handle it.\n\n"
    "Tools:\n"
    "- ask: natural language question about past knowledge, events, decisions\n"
    "- search: explicit request to find/list/show items\n"
    "- action_items: todos, tasks, what needs to be done\n"
    "- find_contradictions: finding conflicting information\n"
    "- graph_fact_check: verifying if a claim is true based on the knowledge graph\n\n"
    "Set confidence below 0.6 (and tool='unknown') when you cannot decide — "
    "the caller will safely fall back to 'ask'."
)

_INTENT_SCHEMA: dict[str, Any] = {
    "name": "telegram_intent",
    "description": "Classify the Telegram message into one of the MCP tools.",
    "input_schema": {
        "type": "object",
        "properties": {
            "tool": {
                "type": "string",
                "enum": list(_TOOLS) + ["unknown"],
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
            },
        },
        "required": ["tool", "confidence"],
    },
}


@functools.lru_cache(maxsize=100)
def classify_intent_llm(text: str) -> str:
    """Return one of :data:`_TOOLS` or ``'unknown'``.

    Cached on the raw text — Telegram users tend to retry near-identical
    phrasings, so even a 100-entry LRU clips a meaningful slice of cost.
    Any failure (router missing, network error, malformed JSON, low
    confidence) collapses to ``'unknown'`` so the caller falls through
    to ``ask``.
    """
    if not text or not text.strip():
        return "unknown"

    try:
        from exocortex import llm_routing
        llm_routing.initialize()
        from llm_router import call_tool as _router_call_tool
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        log.debug("LLM intent: llm_router unavailable (%r)", exc)
        return "unknown"

    try:
        tool_input, _usage = _router_call_tool(
            use_case="second_brain.F31_telegram_intent",
            system=_SYSTEM_PROMPT,
            user=text.strip(),
            schema=_INTENT_SCHEMA,
            max_tokens=64,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        log.debug("LLM intent: call_tool failed (%r)", exc)
        return "unknown"

    if not isinstance(tool_input, dict):
        return "unknown"
    tool = tool_input.get("tool", "unknown")
    try:
        confidence = float(tool_input.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence < _CONFIDENCE_FLOOR or tool not in _TOOLS:
        return "unknown"
    return tool
