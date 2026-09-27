# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""F31.1.3 — Night shift briefing orchestrator.

One-shot: assemble 24h delta + contradictions + overdue actions + emergent
patterns, hand them to the ``night_shift_briefing`` perspective, persist the
synthesis, push the result to Telegram. Triggered daily at 05:00 UTC by the
sibling systemd timer.

The legacy ``synthesizer.synthesize()`` pipeline assumes meeting-shaped source
thoughts. ``night_shift_briefing`` ingests an orchestrator-injected ``inputs``
dict instead — so this module drives the LLM call directly via the registry
perspective + ``llm_router.call_tool`` and writes the row itself.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

log = logging.getLogger("exocortex.night_shift_briefing")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
TELEGRAM_TIMEOUT_SEC = 15
TELEGRAM_MAX_CHARS = 3500

# Telegram MarkdownV2 reserved characters (per Bot API docs).
_MD_V2_SPECIALS = r"_*[]()~`>#+-=|{}.!\\"

PERSPECTIVE_NAME = "night_shift_briefing"
PROMPT_VERSION = 1
MAX_OUTPUT_TOKENS = 2048


# ─────────────────────────── Telegram formatting ───────────────────────────


def _escape_md_v2(text: str) -> str:
    """Escape every MarkdownV2-reserved char in user-provided text.

    Intentional duplicate of ``telegram_bot._escape_md_v2``: this module
    formats bold markers (*…*) as literal strings around already-escaped
    user content; reusing ``telegram_bot.send_message`` would double-escape
    the bold markers.
    """
    out = []
    for ch in text or "":
        if ch in _MD_V2_SPECIALS:
            out.append("\\")
        out.append(ch)
    return "".join(out)


def format_telegram_message(content: dict[str, Any], date_str: str) -> str:
    """Render the briefing as MarkdownV2 for Telegram.

    Bold markers (``*…*``) are emitted unescaped so Telegram renders them;
    every other dynamic value passes through ``_escape_md_v2`` to avoid the
    Bot API rejecting the payload with `400 can't parse entities`.
    """
    narrative = (content.get("narrative_pl") or "").strip()
    patterns = content.get("patterns") or []
    contradictions = content.get("contradictions_list") or []
    overdue = content.get("action_items_due") or []
    corpus_digest = content.get("corpus_digest") or []
    degraded = bool((content.get("_meta") or {}).get("degraded"))

    lines: list[str] = [
        "\U0001f319 *Nocna Zmiana* — " + _escape_md_v2(date_str),
    ]
    if degraded:
        lines.append("")
        lines.append(_escape_md_v2(
            "⚠️ Tryb awaryjny — synteza LLM nie powiodła się, "
            "poniżej dane surowe."
        ))
    lines.append("")
    lines.append(
        _escape_md_v2(narrative) if narrative else
        _escape_md_v2("Brak istotnych wzorców w ostatnich 24h.")
    )

    if patterns:
        lines.append("")
        lines.append("\U0001f501 *Wzorce \\(24h\\):*")
        for p in patterns[:10]:
            lines.append("• " + _escape_md_v2(str(p)))

    if contradictions:
        lines.append("")
        lines.append("⚡ *Sprzeczności:*")
        for c in contradictions[:10]:
            lines.append("• " + _escape_md_v2(str(c)))

    if overdue:
        lines.append("")
        lines.append("\U0001f4cb *Przeterminowane zadania:*")
        for a in overdue[:10]:
            lines.append("• " + _escape_md_v2(str(a)))

    if corpus_digest:
        # Literal excerpt of area_digest/backlog_health syntheses,
        # not LLM-narrated here (see fetch_corpus_digest docstring). Capped
        # independently of TELEGRAM_MAX_CHARS truncation below so it can't
        # silently crowd out the sections above it.
        lines.append("")
        lines.append("\U0001f4da *Z korpusu:*")
        for entry in corpus_digest[:12]:
            prefix = "  " if entry.startswith("  ") else "• "
            lines.append(prefix + _escape_md_v2(entry.strip()))

    text = "\n".join(lines)
    if len(text) > TELEGRAM_MAX_CHARS:
        text = text[:TELEGRAM_MAX_CHARS] + "\n…"
    return text


def send_telegram(token: str, chat_id: int, text: str) -> None:
    """POST a MarkdownV2 message. Errors logged, not raised — the briefing
    has already been persisted to ``syntheses`` by the time we get here."""
    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urlrequest.urlopen(req, timeout=TELEGRAM_TIMEOUT_SEC) as resp:
            resp.read()
        log.info("night-shift briefing sent to Telegram chat_id=%s", chat_id)
    except urlerror.URLError as exc:
        log.warning("Telegram send failed: %r", exc)
    except Exception as exc:  # noqa: BLE001 — defensive: never crash the timer
        log.warning("Telegram send unexpected error: %r", exc)


# ─────────────────────────── Data gathering ───────────────────────────


def fetch_new_thoughts(window_hours: int = 24) -> list[dict]:
    """Thoughts created in the last ``window_hours`` — light projection."""
    from exocortex.db import query
    sql = (
        "SELECT id::text AS id, body, metadata, thought_type, created_at "
        "FROM thoughts "
        f"WHERE created_at >= NOW() - INTERVAL '{int(window_hours)} hours' "
        "ORDER BY created_at DESC "
        "LIMIT 200"
    )
    rows = query(sql)
    out: list[dict] = []
    for r in rows or []:
        meta = r.get("metadata") or {}
        title = meta.get("title") if isinstance(meta, dict) else None
        out.append({
            "id": r["id"],
            "title": title,
            "body": r.get("body") or "",
            "thought_type": r.get("thought_type"),
            "metadata": meta if isinstance(meta, dict) else {},
        })
    return out


def _batch_thought_labels(ids: list[str]) -> dict[str, str]:
    """Return ``{id: human_label}`` for a list of thought UUIDs.

    Labels are title (from metadata) if present, else first 80 chars of body.
    Falls back to truncated ID if thought not found.
    """
    if not ids:
        return {}
    from exocortex.db import query
    try:
        rows = query(
            "SELECT id::text AS id, metadata->>'title' AS title, "
            "LEFT(body, 80) AS preview "
            "FROM thoughts WHERE id = ANY(%s::uuid[])",
            ids,
        )
    except Exception:  # noqa: BLE001 — degraded is OK, show truncated IDs
        return {}
    out: dict[str, str] = {}
    for r in rows or []:
        rid = r["id"]
        label = (r.get("title") or "").strip() or (r.get("preview") or "").strip()
        out[rid] = label or rid[:8]
    return out


def fetch_new_contradictions(since_iso: str | None = None) -> list[dict]:
    """Unresolved ``contradicts`` edges created since the last briefing.

    Without a prior briefing the window falls back to 24h so the first run is
    not flooded by historical contradictions.
    """
    from exocortex.db import query
    if since_iso:
        sql = (
            "SELECT src_id::text AS src_id, src_type, "
            "       dst_id::text AS dst_id, dst_type, created_at "
            "FROM edges "
            "WHERE type = 'contradicts' "
            "  AND resolved IS NOT TRUE "
            "  AND created_at > %s "
            "ORDER BY created_at DESC LIMIT 50"
        )
        rows = query(sql, since_iso)
    else:
        sql = (
            "SELECT src_id::text AS src_id, src_type, "
            "       dst_id::text AS dst_id, dst_type, created_at "
            "FROM edges "
            "WHERE type = 'contradicts' "
            "  AND resolved IS NOT TRUE "
            "  AND created_at >= NOW() - INTERVAL '24 hours' "
            "ORDER BY created_at DESC LIMIT 50"
        )
        rows = query(sql)
    return [
        {
            "src_id": r["src_id"], "src_type": r["src_type"],
            "dst_id": r["dst_id"], "dst_type": r["dst_type"],
            "created_at": r["created_at"].isoformat()
            if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
        }
        for r in rows or []
    ]


def fetch_overdue_actions(now_iso: str | None = None) -> list[str]:
    """Open ``[ ]`` action items whose ``metadata.due_date`` is past today.

    We scan thought metadata rather than maintaining a denormalised view —
    Pattern A keeps source-of-truth in thoughts/syntheses and we want this
    daemon to keep working even when the (not-yet-built) ``action_items``
    table lags."""
    from exocortex.db import query
    sql = (
        "SELECT id::text AS id, metadata, body FROM thoughts "
        "WHERE metadata ? 'action_items' "
        "   OR metadata ? 'due_date' "
        "ORDER BY created_at DESC LIMIT 500"
    )
    try:
        rows = query(sql)
    except Exception as exc:  # noqa: BLE001 — degraded mode is acceptable
        log.warning("overdue scan skipped: %r", exc)
        return []

    today = (now_iso or datetime.now(timezone.utc).date().isoformat())[:10]
    out: list[str] = []
    for r in rows or []:
        meta = r.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        due = meta.get("due_date")
        if isinstance(due, str) and due[:10] < today:
            title = (meta.get("title") or "(no title)").strip()
            out.append(f"{title} (due: {due[:10]})")
        ai = meta.get("action_items")
        if isinstance(ai, list):
            for item in ai:
                if not isinstance(item, dict):
                    continue
                if item.get("status") == "done":
                    continue
                idue = item.get("due_date") or item.get("due")
                if isinstance(idue, str) and idue[:10] < today:
                    text = (item.get("content") or item.get("text") or "").strip()
                    if text:
                        out.append(f"{text} (due: {idue[:10]})")
        if len(out) >= 20:
            break
    return out


def fetch_corpus_digest(window_hours: int = 24, max_areas: int = 3,
                        max_points_per_area: int = 2) -> list[str]:
    """Deterministic excerpt of the freshest area_digest /
    backlog_health syntheses (already LLM-synthesized nightly by
    `exocortex synth --all`). NOT re-summarized here on purpose: running
    already-synthesized content through a SECOND LLM pass would risk the
    same paraphrase-drift class of error the rest of this
    pipeline works hard to avoid. This is a literal excerpt, not a new
    synthesis — a layer added to the briefing, not blended into the
    narrative.

    ``generated_at`` within the window is a proxy for "changed" — synthesis
    idempotency (input_hash) means a row's generated_at only advances when
    its underlying source thoughts actually changed; `thoughts` has no
    `updated_at` column to check directly."""
    from exocortex.db import query
    from exocortex.settings import get_tenant_id
    sql = (
        "SELECT perspective_type, perspective_key, content "
        "FROM syntheses "
        "WHERE tenant_id = %s AND perspective_type IN ('area_digest', 'backlog_health') "
        "  AND superseded_by IS NULL "
        f"  AND generated_at >= NOW() - INTERVAL '{int(window_hours)} hours' "
        "ORDER BY generated_at DESC LIMIT %s"
    )
    try:
        rows = query(sql, get_tenant_id(), max_areas)
    except Exception as exc:  # noqa: BLE001 — corpus digest is best-effort
        log.warning("fetch_corpus_digest skipped: %r", exc)
        return []

    out: list[str] = []
    for r in rows or []:
        ptype, pkey = r.get("perspective_type"), r.get("perspective_key")
        content = r.get("content") or {}
        if not isinstance(content, dict):
            continue
        state = (content.get("stan_dzis") or "").strip()
        if ptype == "area_digest":
            label = f"obszar {pkey}"
            items = content.get("dokumenty_wyrozniajace_sie") or []
            points = [
                f"{it.get('tytul')}: {it.get('powod')}"
                for it in items[:max_points_per_area] if isinstance(it, dict)
            ]
        elif ptype == "backlog_health":
            label = f"backlog {pkey}"
            items = content.get("zaleglosci") or []
            points = [
                f"{it.get('ticket')}: {it.get('opis')}"
                for it in items[:max_points_per_area] if isinstance(it, dict)
            ]
        else:
            continue
        out.append(f"{label} — {state}" if state else label)
        out.extend(f"  {p}" for p in points)
    return out


def get_last_briefing_time() -> str | None:
    """ISO timestamp of the previous active briefing, or None on first run."""
    from exocortex.db import query_one
    from exocortex.settings import get_tenant_id
    row = query_one(
        "SELECT generated_at FROM syntheses "
        "WHERE tenant_id = %s AND perspective_type = %s "
        "  AND superseded_by IS NULL "
        "ORDER BY generated_at DESC LIMIT 1",
        get_tenant_id(), PERSPECTIVE_NAME,
    )
    if not row or not row.get("generated_at"):
        return None
    ts = row["generated_at"]
    return ts.isoformat() if hasattr(ts, "isoformat") else str(ts)


# ─────────────────────────── Synthesis + persist ───────────────────────────


_OUTPUT_SCHEMA = {
    "name": "night_shift_briefing",
    "description": "Daily night-shift briefing (PL prose + structured lists).",
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative_pl": {"type": "string"},
            "contradictions_list": {
                "type": "array", "items": {"type": "string"},
            },
            "action_items_due": {
                "type": "array", "items": {"type": "string"},
            },
            "patterns": {
                "type": "array", "items": {"type": "string"},
            },
        },
        "required": ["narrative_pl", "contradictions_list",
                     "action_items_due", "patterns"],
        "additionalProperties": False,
    },
}


def call_llm(prompt: str) -> tuple[dict, dict]:
    """Drive the LLM via llm_router so telemetry / fallback chain behave like
    every other synthesis call. Returns ``(tool_input, usage)``."""
    from exocortex import llm_routing
    llm_routing.initialize()
    from llm_router import call_tool as _router_call_tool

    tool_input, usage = _router_call_tool(
        use_case="second_brain.F4_synthesis_night_shift_briefing",
        system="Jesteś asystentem wieczornej syntezy. Odpowiadaj WYŁĄCZNIE "
               "wywołaniem narzędzia `night_shift_briefing` z polami "
               "narrative_pl, contradictions_list, action_items_due, patterns.",
        user=prompt,
        schema=_OUTPUT_SCHEMA,
        max_tokens=MAX_OUTPUT_TOKENS,
        cache_system=False,
    )
    legacy_usage = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation_input_tokens": usage.cache_creation_input_tokens,
        "cache_read_input_tokens": usage.cache_read_input_tokens,
        "_provider": usage.provider,
        "_model": usage.model,
        "_cost_usd": usage.cost_usd,
        "_latency_ms": usage.latency_ms,
        "_use_case": usage.use_case,
        "_fallback_chain": list(usage.fallback_chain),
    }
    return tool_input, legacy_usage


def _empty_content() -> dict[str, Any]:
    return {
        "narrative_pl": "Brak istotnych wzorców w ostatnich 24h.",
        "contradictions_list": [],
        "action_items_due": [],
        "patterns": [],
        "corpus_digest": [],  # overwritten by run() with a fresh fetch
    }


def _normalize_content(raw: Any) -> dict[str, Any]:
    """Coerce LLM output (or fallback dict) into the persisted shape."""
    out = _empty_content()
    if not isinstance(raw, dict):
        return out
    narr = raw.get("narrative_pl")
    if isinstance(narr, str) and narr.strip():
        out["narrative_pl"] = narr.strip()
    for key in ("contradictions_list", "action_items_due", "patterns"):
        v = raw.get(key)
        if isinstance(v, list):
            out[key] = [str(x).strip() for x in v if str(x).strip()]
    return out


def persist_briefing(content: dict, usage: dict, perspective_key: str) -> str:
    """Append-only insert into ``syntheses``. Supersedes any previous active
    row for the same (tenant, perspective_type, perspective_key)."""
    from exocortex.db import conn
    from exocortex.settings import get_tenant_id

    tenant_id = get_tenant_id()
    new_id = str(uuid.uuid4())
    tokens = (
        usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )
    cost = float(usage.get("_cost_usd") or 0.0)
    model = usage.get("_model") or "unknown"

    # Techdebt: two concurrent runs for the same (tenant, perspective_key) could
    # both SELECT the same active row and both supersede it, leaving an orphaned
    # superseded pointer.  Acceptable for a once-daily cron; fix with a DB-level
    # unique partial index or advisory lock if parallel execution is ever needed.
    with conn() as c:
        with c.transaction():
            c.execute(
                "UPDATE syntheses SET superseded_by = %s "
                "WHERE tenant_id = %s AND perspective_type = %s "
                "  AND perspective_key = %s AND superseded_by IS NULL",
                (new_id, tenant_id, PERSPECTIVE_NAME, perspective_key),
            )
            c.execute(
                "INSERT INTO syntheses ("
                "  id, tenant_id, perspective_type, perspective_key, content,"
                "  source_thought_ids, input_hash, llm_tokens_used, llm_cost_usd,"
                "  model, prompt_version"
                ") VALUES (%s, %s, %s, %s, %s::jsonb, %s::uuid[], %s, %s, %s, %s, %s)",
                (
                    new_id, tenant_id, PERSPECTIVE_NAME, perspective_key,
                    json.dumps(content), [], new_id[:16],
                    int(tokens), round(cost, 6), model, PROMPT_VERSION,
                ),
            )
    return new_id


# ─────────────────────────── Main orchestrator ───────────────────────────


def build_inputs(window_hours: int = 24, baseline_days: int = 30) -> dict:
    """Assemble the orchestrator inputs dict for the perspective."""
    from exocortex.pattern_detector import detect_patterns

    new_thoughts = fetch_new_thoughts(window_hours=window_hours)
    since = get_last_briefing_time()
    contradictions = fetch_new_contradictions(since_iso=since)
    overdue = fetch_overdue_actions()
    try:
        spikes = detect_patterns(
            window_hours=window_hours, baseline_days=baseline_days,
        )
    except Exception as exc:  # noqa: BLE001 — pattern detector is best-effort
        log.warning("pattern_detector failed: %r", exc)
        spikes = []

    pattern_strings: list[str] = []
    for s in spikes:
        if not isinstance(s, dict):
            continue
        term = s.get("term", "?")
        if term == "_embedding_drift":
            top_tags = s.get("top_terms") or []
            if top_tags:
                tags_str = ", ".join(top_tags[:3])
                pattern_strings.append(f"nowe tematy w centrum uwagi: {tags_str}")
            else:
                pattern_strings.append("zmiana tematyczna — pojawiły się nowe obszary zainteresowania")
        else:
            term_clean = term.replace("-", " ").replace("_", " ")
            n = s.get("frequency_now", 0)
            pattern_strings.append(f"wzrost aktywności: {term_clean} ({n}× w ostatniej dobie)")

    # Enrich contradictions with readable thought labels instead of raw UUIDs.
    all_ids = []
    for c in contradictions:
        all_ids.append(c["src_id"])
        all_ids.append(c["dst_id"])
    labels = _batch_thought_labels(all_ids)
    enriched_contradictions = [
        f"{labels.get(c['src_id'], c['src_id'][:8])} ↔ {labels.get(c['dst_id'], c['dst_id'][:8])}"
        for c in contradictions
    ]

    return {
        "new_thoughts": new_thoughts,
        "new_contradictions": enriched_contradictions,
        "overdue_actions": overdue,
        "pattern_spikes": pattern_strings,
    }


def run(dry_run: bool = False, *, window_hours: int = 24,
        baseline_days: int = 30) -> dict:
    """Single orchestrator pass. Returns the persisted content dict."""
    from exocortex.synth.perspectives.night_shift import NightShiftBriefing
    from exocortex.pipeline_log import log_run_end, log_run_start

    # This worker used to be invisible to pipeline_log (F14):
    # a failed LLM call degraded to a raw-inputs fallback silently (WARNING
    # log only), so the timer kept exiting 0 and nobody noticed for 5 days.
    run_id = None if dry_run else log_run_start(
        "night_shift_briefing", window_hours=window_hours,
        baseline_days=baseline_days,
    )

    inputs = build_inputs(window_hours=window_hours, baseline_days=baseline_days)
    # Fetched and merged in AFTER the LLM call (see below), not
    # passed through build_inputs()/the LLM prompt: area_digest/backlog_health
    # content is already LLM-synthesized once (nightly `exocortex synth`);
    # a literal excerpt avoids a second paraphrase pass over already-synthesized text.
    corpus_digest = fetch_corpus_digest(window_hours=window_hours)
    has_signal = any((
        inputs["new_thoughts"], inputs["new_contradictions"],
        inputs["overdue_actions"], inputs["pattern_spikes"], corpus_digest,
    ))

    perspective = NightShiftBriefing()
    today = datetime.now(timezone.utc).date().isoformat()

    degraded = False
    degraded_reason: str | None = None

    if not has_signal:
        content = _empty_content()
        usage = {"_cost_usd": 0.0, "_model": "noop"}
    else:
        prompt = perspective.build_prompt([inputs])
        try:
            llm_raw, usage = call_llm(prompt)
            content = _normalize_content(llm_raw)
        except Exception as exc:  # noqa: BLE001 — degraded mode beats crash
            log.warning("LLM call failed, falling back to raw inputs: %r", exc)
            degraded = True
            degraded_reason = f"{type(exc).__name__}: {exc}"
            content = _normalize_content({
                "narrative_pl": (
                    "LLM niedostępny — surowy podgląd: "
                    f"{len(inputs['new_thoughts'])} nowych wpisów, "
                    f"{len(inputs['pattern_spikes'])} wzorców, "
                    f"{len(inputs['new_contradictions'])} sprzeczności."
                ),
                "contradictions_list": inputs["new_contradictions"],
                "action_items_due": inputs["overdue_actions"],
                "patterns": inputs["pattern_spikes"],
            })
            usage = {"_cost_usd": 0.0, "_model": "fallback-raw"}

    content["corpus_digest"] = corpus_digest
    content["_meta"] = {"degraded": degraded}

    # Persist before sending — Telegram failures must not lose the briefing.
    if not dry_run:
        try:
            persist_briefing(content, usage, today)
        except Exception as exc:  # noqa: BLE001 — still try to send
            log.error("persist_briefing failed: %r", exc)

    token = os.environ.get("TG_BOT_TOKEN") or os.environ.get(
        "EXOCORTEX_TG_BOT_TOKEN")
    chat_id_raw = os.environ.get("TG_CHAT_ID") or os.environ.get(
        "EXOCORTEX_TG_CHAT_ID")
    if not dry_run and token and chat_id_raw:
        try:
            chat_id = int(chat_id_raw)
            text = format_telegram_message(content, today)
            send_telegram(token, chat_id, text)
        except ValueError:
            log.warning("TG_CHAT_ID is not numeric: %r", chat_id_raw)
    elif not dry_run:
        log.info("Telegram credentials missing — skipping push.")

    if run_id:
        log_run_end(
            run_id,
            "failure" if degraded else "success",
            counts={
                "new_thoughts": len(inputs["new_thoughts"]),
                "contradictions": len(inputs["new_contradictions"]),
                "overdue_actions": len(inputs["overdue_actions"]),
                "patterns": len(inputs["pattern_spikes"]),
            },
            error_message=degraded_reason,
            cost_usd=float(usage.get("_cost_usd") or 0.0),
        )

    return content


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Build inputs + LLM call, skip persist + send.")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--baseline-days", type=int, default=30)
    parser.add_argument("--print", action="store_true",
                        help="Print resulting content JSON to stdout.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        content = run(
            dry_run=args.dry_run,
            window_hours=args.window_hours,
            baseline_days=args.baseline_days,
        )
    except Exception as exc:  # noqa: BLE001 — surface DB / config failures cleanly
        log.error("night_shift_briefing failed: %r", exc)
        return 1

    if args.print:
        print(json.dumps(content, ensure_ascii=False, indent=2))

    # A degraded (fallback) briefing must not exit 0: that's
    # the exit code `exo last`/`exo run` on K12 checks (systemd Result),
    # and it's what made 5 days of silent LLM-parsing failures invisible.
    if (content.get("_meta") or {}).get("degraded"):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
