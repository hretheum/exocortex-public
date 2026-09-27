# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/sources/_session_redaction.py.

This is the single barrier between Claude Code transcripts and the database.
Transcripts really do carry secrets — measured across the live corpus on
2026-08-03: JWTs in 8 sessions, TG_BOT_TOKEN in 10, CAPTURE_API_TOKEN in 15.
A leaked secret would flow raw_sources → embeddings → wiki → (via Syncthing)
a second machine, so redaction runs BEFORE anything leaves the user's box and
is fail-closed: anything that looks like a secret but cannot be removed with
certainty takes the whole session out of ingestion.

Every fixture here is SYNTHETIC. Real secret values must never appear in this
repo — that is exactly what the module exists to prevent.
"""
from __future__ import annotations

import pytest

from exocortex.sources._session_redaction import Verdict, redact

# ── clean text passes untouched ────────────────────────────────────────────

def test_ordinary_text_is_clean():
    text = "Naprawiłem bramkę miodka i dopiąłem timer o 22:45."
    out = redact(text)
    assert out.verdict == Verdict.CLEAN
    assert out.text == text


def test_empty_input_is_clean():
    assert redact("").verdict == Verdict.CLEAN
    assert redact(None).verdict == Verdict.CLEAN


# ── high-confidence patterns: redacted, session may pass ───────────────────

def test_jwt_is_redacted_not_refused():
    # Synthetic 3-part token, not a real JWT.
    text = "token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.FAKESIGnature_00"
    out = redact(text)
    assert out.verdict == Verdict.REDACTED
    assert "eyJhbGci" not in out.text
    assert "[REDACTED" in out.text


@pytest.mark.parametrize("secret", [
    "sk-ant-api03-FAKE000000000000000000000000000000000000",
    "ghp_FAKE0000000000000000000000000000000000",
    "AKIAFAKE0000000000EX",
])
def test_provider_keys_are_redacted(secret):
    out = redact(f"export KEY={secret}")
    assert out.verdict == Verdict.REDACTED
    assert secret not in out.text


def test_telegram_bot_token_is_redacted():
    # Shape: <digits>:<35 base64-ish chars>. Synthetic.
    text = "TG_BOT_TOKEN=1234567890:AAFfake_Telegram_bot_token_0000000000000"
    out = redact(text)
    assert out.verdict == Verdict.REDACTED
    assert "1234567890:AAF" not in out.text


def test_private_key_block_is_redacted():
    text = ("-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "b3BlbnNzaC1rZXktdjEFAKEfakefakefake\n"
            "-----END OPENSSH PRIVATE KEY-----")
    out = redact(text)
    assert out.verdict == Verdict.REDACTED
    assert "PRIVATE KEY" not in out.text or "BEGIN" not in out.text


# ── secret split across a line boundary must still be caught ───────────────

def test_secret_across_line_boundary_is_handled():
    """A token wrapped onto two lines must not slip through a line-by-line
    scanner. Redaction sees the whole text, so it is caught."""
    text = "api_key=sk-ant-api03-FAKE00000000000\n0000000000000000000000000"
    out = redact(text)
    assert out.verdict in (Verdict.REDACTED, Verdict.REFUSE)
    assert "sk-ant-api03-FAKE" not in out.text


# ── low-confidence signals: fail-closed, whole session refused ─────────────

def test_password_assignment_refuses():
    """A value bound to a `password`-like name has no fixed shape, so it cannot
    be redacted with certainty — refuse the session."""
    out = redact('config = {"password": "hunter2_whatever_this_is"}')
    assert out.verdict == Verdict.REFUSE
    assert out.reason


@pytest.mark.parametrize("assignment", [
    "secret = 'abc123def456'",
    "api_key: my-inline-key-value",
    "AUTH_TOKEN=some_opaque_value_here",
])
def test_secretish_assignments_refuse(assignment):
    assert redact(assignment).verdict == Verdict.REFUSE


# ── value inside JSON / code block still detected ──────────────────────────

def test_secret_in_json_value_is_caught():
    text = '{"config": {"token": "eyJhbGciOiJFQUtFIn0.eyJhIjoxfQ.SIGfake000"}}'
    assert redact(text).verdict != Verdict.CLEAN


def test_secret_in_code_fence_is_caught():
    text = "```bash\nexport GH=ghp_FAKE0000000000000000000000000000000000\n```"
    out = redact(text)
    assert out.verdict == Verdict.REDACTED
    assert "ghp_FAKE" not in out.text


# ── verdict ordering: refuse dominates redacted dominates clean ────────────

def test_refuse_wins_when_both_present():
    """One redactable token plus one refuse-worthy assignment → the session is
    refused, because we cannot vouch for the whole thing."""
    text = ("token: ghp_FAKE0000000000000000000000000000000000\n"
            "password = whatever_opaque")
    assert redact(text).verdict == Verdict.REFUSE


# ── the reason never echoes the secret ─────────────────────────────────────

def test_reason_does_not_leak_secret():
    secret = "ghp_FAKE0000000000000000000000000000000000"
    out = redact(f"key={secret}")
    assert secret not in (out.reason or "")
    assert secret not in out.text
