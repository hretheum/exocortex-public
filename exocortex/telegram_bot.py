# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.0.3 — Thin Telegram bot worker.

Long-polling loop against ``api.telegram.org/bot<token>/getUpdates``. Routes
text messages from whitelisted user IDs to the existing MCP tools
(``ask`` / ``search_thoughts`` / ``find_action_items``) via direct in-process
imports — the bot is expected to run on the same host as the MCP server, so we
skip the HTTP hop. ``/capture <text>`` posts to the Capture API instead, so
the existing F6.3 processor pipeline owns ingestion.

Security model: deny-by-default. Any message from a sender whose numeric ID is
not in ``TG_ALLOWED_USER_IDS`` is dropped silently — no reply, no log line.
This is intentional: bots receive scrapes/probes and we do not want to leak
the bot's existence to non-whitelisted users.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

log = logging.getLogger("exocortex.telegram_bot")

TELEGRAM_API = "https://api.telegram.org/bot{token}"
POLL_TIMEOUT_SEC = 25
HTTP_TIMEOUT_SEC = POLL_TIMEOUT_SEC + 5
MAX_REPLY_CHARS = 3500  # Telegram cap is 4096; keep margin for MarkdownV2 escapes.

# Characters that must be escaped in MarkdownV2 per Telegram docs.
_MARKDOWNV2_SPECIALS = r"_*[]()~`>#+-=|{}.!\\"
_MARKDOWNV2_RE = re.compile("([" + re.escape(_MARKDOWNV2_SPECIALS) + "])")


# ─────────────────────────── Intent classifier ───────────────────────────

# Regex-first classifier. Returns the first matching intent or 'unknown'. The
# order matters: '/capture' is most specific (slash command), then action
# items / search keywords, then the generic question patterns.
_INTENT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "factcheck",
        re.compile(r"^\s*/factcheck(?:@\w+)?(?:\s+(?P<query>.+))?\s*$", re.IGNORECASE | re.DOTALL),
    ),
    (
        "capture",
        re.compile(r"^\s*/capture(?:@\w+)?(?:\s+(?P<body>.+))?\s*$", re.IGNORECASE | re.DOTALL),
    ),
    (
        "action_items",
        re.compile(r"\b(todo|to ?do|zadania|action[\s_-]?items|co\s+do\s+zrobienia)\b", re.IGNORECASE),
    ),
    (
        "search",
        re.compile(r"\b(znajd(z|ź)|search|szukaj|pokaż|pokaz)\b", re.IGNORECASE),
    ),
    (
        "ask",
        re.compile(
            r"(\bco\s+\S+\s+m(o|ó)wi(ł|l)|\bkiedy\b|"
            r"\bczy\s+\S+\s+(decydowali(śmy|smy)?|ustalili(śmy|smy)?)|"
            r"\bjak\b.*\b(dzia(ł|l)a|robi)\b)",
            re.IGNORECASE,
        ),
    ),
]


def classify_intent(text: str) -> str:
    """Return one of ``ask`` | ``search`` | ``action_items`` | ``capture`` | ``unknown``.

    Pure regex — fast, deterministic, predictable. LLM-based disambiguation is
    deliberately *not* done here; the bot fallback is to run ``ask`` on the raw
    text, which is the broadest tool we have. F31.4 may layer an LLM intent
    layer on top later, but for the bot's purpose (the user knows what they
    want) the regex tier is enough.
    """
    if not text:
        return "unknown"
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(text):
            return intent
    return "unknown"


# ─────────────────────────── Whitelist ───────────────────────────


def get_allowed_ids() -> set[int]:
    """Parse comma-separated numeric IDs from ``TG_ALLOWED_USER_IDS``.

    Read fresh from env on every call so that an operator editing
    ``/etc/second-brain.env`` + ``systemctl restart`` always takes effect.
    Returns an empty set when unset (= deny everyone).
    """
    raw = os.environ.get("TG_ALLOWED_USER_IDS", "").strip()
    if not raw:
        return set()
    out: set[int] = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.add(int(chunk))
        except ValueError:
            log.warning("Ignoring non-numeric Telegram user id %r", chunk)
    return out


# ─────────────────────────── HTTP helpers ───────────────────────────


def _telegram_call(token: str, method: str, payload: dict[str, Any],
                   timeout: int = HTTP_TIMEOUT_SEC) -> dict[str, Any]:
    """POST JSON to ``api.telegram.org/bot<token>/<method>`` and return the
    decoded body. Raises ``urllib.error.URLError`` on transport failure."""
    url = TELEGRAM_API.format(token=token) + "/" + method
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def escape_markdown_v2(text: str) -> str:
    """Escape every MarkdownV2 reserved character per Telegram spec."""
    return _MARKDOWNV2_RE.sub(r"\\\1", text)


def send_message(token: str, chat_id: int, text: str, *,
                 reply_to: int | None = None) -> None:
    """Send a MarkdownV2 message. Truncates over-long bodies to keep one
    Telegram request (no pagination today)."""
    body = text if len(text) <= MAX_REPLY_CHARS else text[:MAX_REPLY_CHARS] + "\n…"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": escape_markdown_v2(body),
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to
    try:
        _telegram_call(token, "sendMessage", payload)
    except urlerror.URLError as exc:  # pragma: no cover — defensive
        log.warning("sendMessage failed: %r", exc)


# ─────────────────────────── Response formatters ───────────────────────────


def _format_ask(result: dict[str, Any]) -> str:
    answer = (result.get("answer") or "").strip() or "(brak odpowiedzi)"
    sources = result.get("sources") or []
    if not sources:
        return answer
    cites = []
    for s in sources[:5]:
        title = s.get("title") or s.get("thought_id") or "?"
        cites.append(f"• {title}")
    return f"{answer}\n\nŹródła:\n" + "\n".join(cites)


def _format_search(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Nic nie znalazłem."
    lines = []
    for r in rows[:10]:
        title = r.get("title") or r.get("thought_id") or "?"
        score = r.get("score")
        score_str = f" ({score:.2f})" if isinstance(score, (int, float)) else ""
        lines.append(f"• {title}{score_str}")
    return "Wyniki:\n" + "\n".join(lines)


_FACT_CHECK_ICONS = {
    "supported": "✅",
    "contradicts": "❌",
    "no_evidence": "❓",
}


def _format_fact_check(verdicts: list[dict[str, Any]]) -> str:
    """Format graph_fact_check output for Telegram.

    Each verdict gets an icon by verdict type + up to 3 source titles. Empty
    list → friendly "nothing to verify" message so the bot never sends blank
    replies.
    """
    if not verdicts:
        return "Nie znalazłem weryfikowalnych twierdzeń w tekście."
    lines = [f"Fact-check: {len(verdicts)} twierdzenie(ń)\n"]
    for v in verdicts:
        icon = _FACT_CHECK_ICONS.get(v.get("verdict", "no_evidence"), "❓")
        claim = (v.get("claim") or "").strip() or "(no claim text)"
        lines.append(f"{icon} {claim}")
        srcs = v.get("sources") or []
        if srcs:
            titles = ", ".join(
                (s.get("title") or s.get("thought_id") or "?") for s in srcs[:3]
            )
            lines.append(f"   → {titles}")
        lines.append("")
    return "\n".join(lines).strip()


def _split_long_message(text: str, limit: int = MAX_REPLY_CHARS) -> list[str]:
    """Split a long reply on ``\\n\\n`` paragraph boundaries to stay under
    Telegram's 4096-char cap (we keep margin via ``MAX_REPLY_CHARS``).

    Falls back to a single hard-truncated chunk only if the text has no
    paragraph breaks at all.
    """
    if len(text) <= limit:
        return [text]
    paragraphs = text.split("\n\n")
    if len(paragraphs) == 1:
        # No paragraph breaks → hard-truncate to the limit, single chunk.
        return [text[:limit]]
    parts: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        added = len(para) + (2 if current else 0)
        if current and current_len + added > limit:
            parts.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += added
    if current:
        parts.append("\n\n".join(current))
    return parts or [text[:limit]]


class _FileTooLargeError(Exception):
    """Telegram file exceeded the local size cap for fact-check ingestion."""


def _download_telegram_file(token: str, file_id: str, *,
                            max_bytes: int = 50 * 1024,
                            wall_timeout: float = 30.0) -> str:
    """Download a Telegram file by ``file_id`` and return its content as
    str. Raises :class:`_FileTooLargeError` if the file is bigger than
    ``max_bytes``. Raises ``TimeoutError`` if total download exceeds
    ``wall_timeout`` seconds (separate from socket-level timeout)."""
    resp = _telegram_call(token, "getFile", {"file_id": file_id})
    file_path = ((resp or {}).get("result") or {}).get("file_path")
    if not file_path:
        raise ValueError("getFile response missing file_path")
    url = f"https://api.telegram.org/file/bot{token}/{file_path}"
    req = urlrequest.Request(url)
    deadline = time.monotonic() + wall_timeout
    chunks: list[bytes] = []
    total = 0
    with urlrequest.urlopen(req, timeout=10) as r:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError(f"download exceeded {wall_timeout}s")
            chunk = r.read(8192)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise _FileTooLargeError(f"file > {max_bytes} bytes")
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8", errors="replace")


def _format_action_items(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Brak otwartych action items."
    lines = []
    for r in rows[:20]:
        owner = r.get("owner_name") or r.get("owner_slug") or "?"
        content = (r.get("content") or "").strip()
        due = r.get("due_date") or ""
        suffix = f" [{due}]" if due else ""
        lines.append(f"• [{owner}] {content}{suffix}")
    return "Action items:\n" + "\n".join(lines)


# ─────────────────────────── Capture API call ───────────────────────────


def post_capture(*, base_url: str, api_token: str | None,
                 user_id: int, message_id: int, text: str,
                 timeout: int = 10) -> tuple[bool, str]:
    """POST a quick-note style capture to ``{base_url}/capture``.

    Returns ``(ok, message)``. On error returns ``(False, reason)``; the bot
    surfaces the reason to the user so they know the capture failed.
    """
    payload: dict[str, Any] = {
        "source_type": "telegram-capture",
        "uri": f"telegram://message/{user_id}/{message_id}",
        "title": (text.splitlines()[0][:140] or "Telegram capture").strip(),
        "raw_payload": text,
        "metadata": {
            "telegram_user_id": user_id,
            "telegram_message_id": message_id,
        },
    }
    headers = {"Content-Type": "application/json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    req = urlrequest.Request(
        base_url.rstrip("/") + "/capture",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return True, str(body.get("source_id") or "ok")
    except urlerror.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except urlerror.URLError as exc:
        return False, f"transport: {exc.reason}"


# ─────────────────────────── Message handling ───────────────────────────


_CAPTURE_PATTERN = next(p for name, p in _INTENT_PATTERNS if name == "capture")
_FACTCHECK_PATTERN = next(p for name, p in _INTENT_PATTERNS if name == "factcheck")


def _strip_command_prefix(text: str) -> str:
    """``/capture foo`` → ``foo``; everything else passes through."""
    m = _CAPTURE_PATTERN.match(text)
    if m:
        return (m.group("body") or "").strip()
    return text


def _strip_factcheck_prefix(text: str) -> str:
    """``/factcheck claim`` → ``claim``; everything else passes through."""
    m = _FACTCHECK_PATTERN.match(text)
    if m:
        return (m.group("query") or "").strip()
    return text.strip()


def handle_message(token: str, message: dict[str, Any], *,
                   allowed_ids: set[int] | None = None,
                   capture_base_url: str | None = None,
                   capture_token: str | None = None) -> str | None:
    """Dispatch a single Telegram message. Returns the intent that was
    handled (mostly for testing); ``None`` when the message was ignored
    (non-whitelist, no text, etc.)."""
    user = message.get("from") or {}
    user_id = user.get("id")
    if not isinstance(user_id, int):
        return None
    ids = allowed_ids if allowed_ids is not None else get_allowed_ids()
    if user_id not in ids:
        # Silent ignore — no log, no reply. See module docstring.
        return None

    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id") or user_id
    message_id = message.get("message_id") or 0

    # ── Auto fact-check for .md attachments ────────────────────────────────
    doc = message.get("document") or {}
    doc_name = (doc.get("file_name") or "").strip()
    if doc_name.lower().endswith(".md"):
        file_id = doc.get("file_id")
        if file_id:
            try:
                file_content = _download_telegram_file(token, file_id)
                from exocortex.mcp_server import graph_fact_check
                verdicts = graph_fact_check(file_content)
                reply = _format_fact_check(verdicts)
            except _FileTooLargeError:
                reply = "Plik za duży (maks 50KB)"
            except Exception as exc:  # pragma: no cover — runtime safety net
                log.exception("MD attachment fact-check failed")
                reply = f"Błąd: {exc!s}"
            for part in _split_long_message(reply):
                send_message(token, chat_id, part)
            return "factcheck"

    if not text:
        return None
    intent = classify_intent(text)

    if intent == "unknown":
        try:
            from exocortex.telegram_intent import classify_intent_llm
            intent = classify_intent_llm(text)
        except Exception:  # pragma: no cover — defensive  # noqa: BLE001, S110 — failure is ignored on purpose; narrowing would change behavior
            pass

    if intent in ("factcheck", "graph_fact_check"):
        query_text = _strip_factcheck_prefix(text)
        if not query_text:
            send_message(token, chat_id, "Użycie: /factcheck <twierdzenie>")
            return intent
        try:
            from exocortex.mcp_server import graph_fact_check
            verdicts = graph_fact_check(query_text)
            reply = _format_fact_check(verdicts)
        except Exception as exc:  # pragma: no cover — runtime safety net  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            if "timeout" in str(exc).lower():
                reply = "⏱️ Timeout — spróbuj z krótszym tekstem"
            else:
                reply = f"Błąd fact-check: {exc!s}"
        parts = _split_long_message(reply)
        for i, part in enumerate(parts):
            send_message(
                token, chat_id, part,
                reply_to=message_id if i == 0 else None,
            )
        return intent

    if intent == "capture":
        body = _strip_command_prefix(text)
        if not body:
            send_message(token, chat_id, "Użycie: /capture <treść>")
            return intent
        base_url = capture_base_url or os.environ.get(
            "CAPTURE_API_URL", "http://localhost:8000"
        )
        api_token = capture_token if capture_token is not None else os.environ.get(
            "CAPTURE_API_TOKEN"
        )
        ok, info = post_capture(
            base_url=base_url, api_token=api_token,
            user_id=user_id, message_id=message_id, text=body,
        )
        reply = f"✓ Zapisane ({info})" if ok else f"✗ Nie udało się: {info}"
        send_message(token, chat_id, reply, reply_to=message_id)
        return intent

    # All remaining intents call into the in-process MCP tools.
    try:
        if intent == "search":
            from exocortex.mcp_server import search_thoughts  # local import — keeps the
            # module importable in unit tests where mcp_server's heavy deps are absent.
            rows = search_thoughts(text)
            reply = _format_search(rows)
        elif intent == "action_items":
            from exocortex.mcp_server import find_action_items
            rows = find_action_items()
            reply = _format_action_items(rows)
        else:
            # 'ask' or 'unknown' both fall through to ask — it is the broadest tool.
            from exocortex.mcp_server import ask
            result = ask(text)
            reply = _format_ask(result)
    except Exception as exc:  # pragma: no cover — runtime safety net
        log.exception("MCP tool failed for intent=%s", intent)
        reply = f"Błąd: {exc!s}"

    send_message(token, chat_id, reply, reply_to=message_id)
    return intent if intent != "unknown" else "ask"


# ─────────────────────────── Polling loop ───────────────────────────


def get_updates(token: str, offset: int, *,
                timeout: int = POLL_TIMEOUT_SEC) -> list[dict[str, Any]]:
    """One ``getUpdates`` call. Returns the result list (empty on
    timeout / no new messages)."""
    payload = {
        "offset": offset,
        "timeout": timeout,
        "allowed_updates": ["message"],
    }
    try:
        body = _telegram_call(token, "getUpdates", payload,
                              timeout=timeout + 5)
    except urlerror.URLError as exc:
        log.warning("getUpdates transport error: %r", exc)
        return []
    if not body.get("ok"):
        log.warning("getUpdates non-ok response: %s", body)
        return []
    return body.get("result") or []


def run_polling(token: str, *, sleep_on_error: float = 5.0) -> None:
    """Long-polling main loop. Runs until interrupted."""
    offset = 0
    log.info("Telegram bot polling started (allowed=%s)", sorted(get_allowed_ids()))
    while True:
        try:
            updates = get_updates(token, offset)
        except Exception:  # pragma: no cover
            log.exception("getUpdates raised")
            time.sleep(sleep_on_error)
            continue
        for update in updates:
            offset = max(offset, update.get("update_id", 0) + 1)
            message = update.get("message")
            if not message:
                continue
            try:
                handle_message(token, message)
            except Exception:  # pragma: no cover
                log.exception("handle_message raised")


def _main() -> int:
    logging.basicConfig(
        level=os.environ.get("EXOCORTEX_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    if not token:
        print("TG_BOT_TOKEN is not set", file=sys.stderr)
        return 2
    if not get_allowed_ids():
        log.warning(
            "TG_ALLOWED_USER_IDS is empty — bot will silently drop every message."
        )
    run_polling(token)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_main())
