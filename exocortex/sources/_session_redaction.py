# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Secret redaction for Claude Code session ingestion — the one barrier.

Transcripts carry real secrets (measured 2026-08-03: JWTs in 8 sessions,
TG_BOT_TOKEN in 10, CAPTURE_API_TOKEN in 15). A leak would flow
raw_sources → embeddings → wiki → a second machine via Syncthing, so this
runs BEFORE anything leaves the box and is **fail-closed**: text that looks
like a secret but cannot be scrubbed with certainty takes the whole session
out of ingestion.

Two tiers:

* **High-confidence patterns** — tokens with a fixed, self-identifying shape
  (JWT, `sk-…`, `ghp_…`, `AKIA…`, Telegram bot token, PEM private-key block).
  These can be excised exactly, so the text is returned REDACTED and the
  session may still be ingested.
* **Low-confidence signals** — a value bound to a `password`/`secret`/
  `token`/`api_key`-like name. Such a value has no fixed shape, so we cannot
  prove we removed all of it. One of these REFUSES the whole session.

`refuse` dominates `redacted` dominates `clean`: if any part of the text is
untrustworthy, the whole session is untrustworthy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Verdict(str, Enum):
    CLEAN = "clean"
    REDACTED = "redacted"
    REFUSE = "refuse"


@dataclass(frozen=True)
class RedactionResult:
    text: str
    verdict: Verdict
    reason: str = ""


# ── High-confidence secrets: fixed shape → exact excision ──────────────────
# Each (name, compiled regex). Order irrelevant; all are applied. The
# replacement never echoes the matched value, so a redacted transcript — and
# any log or reason built from it — is safe to store.
_HIGH_CONFIDENCE: list[tuple[str, re.Pattern]] = [
    # JWT: three base64url segments joined by dots. The header almost always
    # begins with eyJ ( == '{"' base64url-encoded ), which anchors the match.
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")),
    # Anthropic / OpenAI style keys.
    ("api-key", re.compile(r"sk-[A-Za-z0-9-]{16,}")),
    # GitHub tokens (classic + fine-grained prefixes).
    ("github-token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}")),
    # AWS access key id.
    ("aws-key", re.compile(r"AKIA[0-9A-Z]{12,}")),
    # Telegram bot token: <digits>:<35 base64-ish>.
    ("telegram-token", re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}")),
    # PEM private-key block, across newlines.
    ("private-key", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
        re.DOTALL)),
]

# ── Low-confidence signals: a value bound to a secret-ish name ─────────────
# No fixed shape, so any hit refuses the whole session. Matches
#   password = "..."   |   "api_key": ...   |   AUTH_TOKEN=...
# with a non-trivial value after the separator. `token`/`secret`/`password`/
# `api_key`/`auth_token` as a bare word next to = or : with a value.
_SECRETISH_NAME = r"(?:password|passwd|secret|api[_-]?key|auth[_-]?token|access[_-]?token)"
_REFUSE_ASSIGNMENT = re.compile(
    r"['\"]?" + _SECRETISH_NAME + r"['\"]?\s*[:=]\s*['\"]?(?P<val>[^\s'\"]{6,})",
    re.IGNORECASE,
)

_PLACEHOLDER_VALUES = {
    # Obvious non-secrets that a secret-ish name might legitimately carry.
    "true", "false", "none", "null", "<atrapa>", "changeme", "xxx",
    "your_key_here", "redacted",
}


def _looks_like_placeholder(val: str) -> bool:
    low = val.lower()
    return (
        low in _PLACEHOLDER_VALUES
        or low.startswith(("fake", "example", "dummy", "test-", "test_", "[redacted"))
        or set(low) <= {"x", "*", "."}          # xxxx, ****, ....
    )


def redact(text: str | None) -> RedactionResult:
    """Scrub high-confidence secrets; refuse on any low-confidence signal.

    Returns a RedactionResult; never raises. `clean` text is returned
    byte-identical. A `refuse` verdict means the caller must drop the whole
    session — see module docstring.
    """
    if not text:
        return RedactionResult(text or "", Verdict.CLEAN)

    scrubbed = text
    redacted_any = False
    for name, pat in _HIGH_CONFIDENCE:
        scrubbed, n = pat.subn(f"[REDACTED-{name.upper()}]", scrubbed)
        if n:
            redacted_any = True

    # Low-confidence pass runs on the ALREADY-scrubbed text, so a value we just
    # replaced with a placeholder does not itself trigger a refuse.
    for m in _REFUSE_ASSIGNMENT.finditer(scrubbed):
        val = m.group("val")
        if _looks_like_placeholder(val):
            continue
        # A named secret with an opaque value — cannot vouch for it.
        return RedactionResult(
            scrubbed, Verdict.REFUSE,
            reason=f"secret-shaped assignment to a {m.group(0).split('=')[0].split(':')[0].strip()!r}-like name",
        )

    if redacted_any:
        return RedactionResult(scrubbed, Verdict.REDACTED,
                               reason="high-confidence secret pattern(s) excised")
    return RedactionResult(text, Verdict.CLEAN)
