# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.1.1 — night_shift_briefing perspective.

Daily 5:00 UTC briefing summarising patterns from the last 24h. Unlike other
perspectives, source data is not selected by querying ``thoughts``; the
orchestrator (F31.1.3) pre-assembles an input dict and injects it via
``SynthContext.inputs``. ``select_thoughts`` returns ``[inputs]`` as a single
pseudo-thought so the rest of the synthesizer plumbing stays unchanged.

Output schema (JSONB)::

    {
      "narrative_pl": "2-5 sentences of prose in Polish — patterns/topics only.",
      "contradictions_list": ["A vs B", ...],
      "action_items_due": ["Task X (due: 2026-05-20)", ...],
      "patterns": ["tag 'AI' x3 spike", ...]
    }
"""
from __future__ import annotations

import json
import re
from typing import Any

from exocortex.synth.perspectives.base import PerspectiveType

_NAME = "night_shift_briefing"

_EMPTY_NARRATIVE = "Brak istotnych wzorców w ostatnich 24h."

_SYSTEM_PROMPT = """\
Napisz KRÓTKI BRIEFING (2-5 zdań prozy po polsku) podsumowujący najważniejsze
wzorce z ostatnich 24 godzin. Piszesz do właściciela notatek — nie technicznego,
lecz do osoby która chce wiedzieć co dzieje się w jej wiedzy.

GUARDRAIL — OBOWIĄZKOWE ZASADY:
1. Narracja (narrative_pl): 2-5 zdań prostej prozy opisujących CO SIĘ DZIEJE
   w wiedzy, NIE techniczne wskaźniki. Używaj naturalnego języka, jakbyś pisał
   do znajomego. Żadnych liczb drift, żadnych ratio.
2. Wzorce (patterns): lista maksymalnie 3 krótkich, CZYTELNYCH obserwacji.
   Pisz "częściej pojawia się X", "nowe zainteresowanie Y", "wzrosła aktywność
   wokół Z". NIE pisz "embedding drift 0.4" ani "tag spike x3 ratio 3.1".
3. Sprzeczności (contradictions_list): wypisz jako listę na końcu, NIGDY nie
   pakuj ich w narrację. Użyj podanego opisu myśli, nie technicznych ID.
4. Nie rozstrzygaj za użytkownika — sygnalizuj, nie oceniaj.
5. Jeśli brak danych → narrative_pl = "Brak istotnych wzorców w ostatnich 24h."

Wywołaj narzędzie `night_shift_briefing`, wypełniając pola: narrative_pl,
contradictions_list, action_items_due, patterns.
"""


def _fmt_thought(t: dict[str, Any]) -> str:
    title = (t.get("metadata") or {}).get("title") or t.get("title") or ""
    body = (t.get("body") or "").strip().replace("\n", " ")
    if len(body) > 200:
        body = body[:200] + "..."
    return f"- {title}: {body}" if title else f"- {body}"


def _fmt_list(items: list[Any], limit: int = 20) -> str:
    if not items:
        return "(brak)"
    out: list[str] = []
    for item in items[:limit]:
        if isinstance(item, dict):
            out.append("- " + json.dumps(item, ensure_ascii=False))
        else:
            out.append(f"- {item}")
    return "\n".join(out)


class NightShiftBriefing(PerspectiveType):
    """F31.1.1: daily night-shift briefing (PL guardrailed prose)."""

    _legacy_type = _NAME

    def __init__(self) -> None:
        pass

    @property
    def name(self) -> str:
        return _NAME

    def select_thoughts(self, ctx: Any) -> list[Any]:
        """Return orchestrator-injected inputs as a single pseudo-thought."""
        inputs = getattr(ctx, "inputs", None)
        if not inputs:
            return []
        return [inputs]

    def build_prompt(self, thoughts: list[Any]) -> str:
        data: dict[str, Any] = thoughts[0] if thoughts else {}
        new_thoughts = data.get("new_thoughts") or []
        contradictions = data.get("new_contradictions") or []
        overdue = data.get("overdue_actions") or []
        spikes = data.get("pattern_spikes") or []

        if isinstance(new_thoughts, list) and new_thoughts and isinstance(new_thoughts[0], dict):
            new_block = "\n".join(_fmt_thought(t) for t in new_thoughts[:30])
        else:
            new_block = _fmt_list(new_thoughts, limit=30)

        return (
            _SYSTEM_PROMPT
            + "\n\nDane wejściowe:\n\n"
            + f"Nowe wpisy (24h):\n{new_block or '(brak)'}\n\n"
            + f"Sprzeczności:\n{_fmt_list(contradictions)}\n\n"
            + f"Przeterminowane zadania:\n{_fmt_list(overdue)}\n\n"
            + f"Wzorce (spikes):\n{_fmt_list(spikes)}\n"
        )

    def parse_response(self, response: str) -> dict[str, Any]:
        """Parse LLM JSON output; tolerate code fences and stray prose."""
        text = (response or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
        parsed: dict[str, Any] = {}
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                parsed = obj
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if match:
                try:
                    obj = json.loads(match.group(0))
                    if isinstance(obj, dict):
                        parsed = obj
                except json.JSONDecodeError:
                    parsed = {}

        narrative = parsed.get("narrative_pl")
        if not isinstance(narrative, str) or not narrative.strip():
            narrative = _EMPTY_NARRATIVE

        def _as_str_list(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            out: list[str] = []
            for v in value:
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
                elif isinstance(v, dict):
                    out.append(json.dumps(v, ensure_ascii=False))
            return out

        return {
            "narrative_pl": narrative.strip(),
            "contradictions_list": _as_str_list(parsed.get("contradictions_list")),
            "action_items_due": _as_str_list(parsed.get("action_items_due")),
            "patterns": _as_str_list(parsed.get("patterns")),
        }


def setup(registry: Any) -> None:
    registry.register_perspective(NightShiftBriefing())
