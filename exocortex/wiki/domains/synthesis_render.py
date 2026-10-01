# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Cross-domain synthesis rendering helpers.

Extracted from exocortex.wiki.domains.work to break cross-domain coupling
(frp, news) that previously called _render_synthesis_banner via the
wiki_compiler facade import.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# F4.3.4 — synthesis "stale" warning threshold (days since regeneration).
SYNTHESIS_STALE_DAYS = 14


def _humanize_age(generated_at: Any) -> str:
    """Return Polish-language relative age, e.g. '3 dni temu' (3 days ago), '2 tyg. temu'."""
    if not generated_at:
        return "?"
    if isinstance(generated_at, str):
        try:
            generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            return generated_at
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - generated_at
    days = delta.days
    if days <= 0:
        return "dziś"
    if days == 1:
        return "wczoraj"
    if days < 7:
        return f"{days} dni temu"
    if days < 30:
        return f"{days // 7} tyg. temu"
    if days < 365:
        return f"{days // 30} mies. temu"
    return f"{days // 365} lat temu"


def _is_synthesis_stale(generated_at: Any) -> bool:
    """Return True if the synthesis is older than SYNTHESIS_STALE_DAYS."""
    if not generated_at:
        return False
    if isinstance(generated_at, str):
        try:
            generated_at = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        except ValueError:
            return False
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - generated_at).days > SYNTHESIS_STALE_DAYS


def _render_synthesis_banner(
    syn: dict | None, n_meetings: int, extra: str | None = None
) -> list[str]:
    """Return Markdown lines for the `>[!info] Synteza` banner + stale warning."""
    if not syn:
        return [
            "> [!info] Synteza",
            "> Brak syntezy. Strona ze statystyk + Dataview.",
            "",
        ]
    age = _humanize_age(syn.get("generated_at"))
    bits = [f"wygenerowana z **{n_meetings} spotkań**"]
    if extra:
        bits.append(extra)
    bits.append(f"regeneracja: **{age}**")
    if syn.get("model"):
        bits.append(f"model: `{syn['model']}`")
    lines = [
        "> [!info] Synteza",
        "> " + " · ".join(bits),
        "",
    ]
    if _is_synthesis_stale(syn.get("generated_at")):
        ga = syn["generated_at"]
        if isinstance(ga, str):
            try:
                ga = datetime.fromisoformat(ga.replace("Z", "+00:00"))
            except ValueError:
                ga = None
        if ga is not None:
            if ga.tzinfo is None:
                ga = ga.replace(tzinfo=UTC)
            days = (datetime.now(UTC) - ga).days
        else:
            days = SYNTHESIS_STALE_DAYS + 1
        lines += [
            "> [!warning] Synteza nieaktualna",
            (f"> Minęło {days} dni od regeneracji ({SYNTHESIS_STALE_DAYS}+ dni). "
            f"Re-run `python -m scripts.run_synthesizer` lub `compile_all`."),
            "",
        ]
    return lines
