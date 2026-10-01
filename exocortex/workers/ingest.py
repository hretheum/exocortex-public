# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Bulk-ingest vault meeting notes into the thoughts table.

Importable module entry-point for ``exocortex ingest`` and
``python -m exocortex.workers.ingest``. The thin ``scripts/bulk_ingest_vault.py``
shim re-exports from here for backward compatibility with cron / systemd that
historically called the script path directly.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

# Load config/.env if running from a source checkout. In a wheel install the
# operator is expected to provide env vars directly (systemd Environment=,
# docker -e, etc.), so a missing file is fine.
_repo_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=_repo_root / "config" / ".env")

from exocortex.classifier import classify_meeting
from exocortex.db import (
    emit_meeting_edges,
    get_embedding,
    ingest_note,
    query_one,
    update_where,
)


def _meeting_notes_dir() -> Path:
    """Resolve the meeting-notes directory from env at call time.

    Reading at import-time would bake in the empty default if env is not yet
    set (e.g. tests that mutate env before calling main()).
    """
    vault = os.environ.get("VAULT_PATH") or os.environ.get("EXOCORTEX_VAULT_PATH", "")
    return Path(vault) / "_source" / "work" / "meeting-notes"


THOUGHT_TYPE = "work_meeting_note"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
DATE_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-")
EXTRACTED_SECTIONS = ("Overview", "Action Items", "Key Points", "Notes")

INGEST_ANOMALIES_TSV = _repo_root / "data" / "discovery" / "ingest_anomalies.tsv"


def _tenant_id() -> str:
    return os.environ["TENANT_ID"]


def resolve_title(fm: dict, body_after_fm: str, filename_stem: str) -> str:
    """Resolve title with 3-level fallback: frontmatter.title → first H1 → filename slug."""
    fm_title = fm.get("title")
    if fm_title is not None and str(fm_title).strip():
        return str(fm_title).strip()
    m = H1_RE.search(body_after_fm)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return DATE_PREFIX_RE.sub("", filename_stem)


def normalize_participants(raw, source_path: Optional[Path] = None) -> list[str]:
    """Coerce ``participants`` frontmatter to a clean list of single-email strings.

    Fixes the F4.5/F4.6.5 source-quality bug where Fireflies sometimes emits a
    single string with comma-separated emails (``"a@x,b@y,c@z"``) inside a 1-item
    list, instead of a 3-item list. Splits and logs to
    ``data/discovery/ingest_anomalies.tsv`` so we can audit which source files
    were affected over time.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    cleaned: list[str] = []
    anomalies: list[tuple[str, int]] = []
    for entry in raw:
        if entry is None:
            continue
        s = str(entry).strip()
        if not s:
            continue
        if "," in s:
            parts = [e.strip() for e in s.split(",") if e.strip()]
            anomalies.append((s, len(parts)))
            cleaned.extend(parts)
        else:
            cleaned.append(s)
    if anomalies and source_path is not None:
        try:
            INGEST_ANOMALIES_TSV.parent.mkdir(parents=True, exist_ok=True)
            with INGEST_ANOMALIES_TSV.open("a", encoding="utf-8") as f:
                ts = datetime.now(timezone.utc).isoformat()
                for original, n_parts in anomalies:
                    f.write(f"{ts}\t{source_path.name}\t{original}\t{n_parts}\n")
        except OSError:
            pass  # best-effort logging; never block ingest
    seen: set[str] = set()
    deduped: list[str] = []
    for e in cleaned:
        key = e.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return deduped


def parse_frontmatter(text: str) -> dict:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    try:
        return yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return {}


def extract_section(text: str, name: str) -> str | None:
    """Extract '## NAME' content. Stops at next non-bold '## ' header or EOF.
    (Notes' '## **bold**' subsections are kept as part of Notes content.)"""
    start = re.search(rf"^## {re.escape(name)}\s*$\n", text, re.MULTILINE)
    if not start:
        return None
    rest = text[start.end():]
    end = re.search(r"^## (?!\*\*)", rest, re.MULTILINE)
    content = rest[:end.start()] if end else rest
    content = content.strip()
    return content or None


def parse_sections(text: str) -> dict[str, str]:
    body = FRONTMATTER_RE.sub("", text, count=1).lstrip()
    out: dict[str, str] = {}
    for name in EXTRACTED_SECTIONS:
        content = extract_section(body, name)
        if content:
            out[name.lower().replace(" ", "_")] = content
    return out


def build_body(fm: dict, title: str, sections: dict[str, str],
               participants: Optional[list[str]] = None) -> str:
    parts = [f"Meeting: {title}"]
    if fm.get("date"):
        parts.append(f"Date: {fm['date']}")
    if fm.get("duration_minutes"):
        parts.append(f"Duration: {int(fm['duration_minutes'])} min")
    if fm.get("organizer"):
        parts.append(f"Organizer: {fm['organizer']}")
    if participants is None:
        participants = fm.get("participants") or []
    if participants:
        parts.append(f"Participants: {', '.join(str(p) for p in participants)}")
    tags = fm.get("tags") or []
    if tags:
        parts.append(f"Tags: {', '.join(str(t) for t in tags)}")
    if fm.get("transcript_url"):
        parts.append(f"Transcript: {fm['transcript_url']}")

    for key in ("overview", "key_points", "action_items", "notes"):
        if sections.get(key):
            heading = key.replace("_", " ").title()
            parts.append(f"\n## {heading}\n{sections[key]}")
    return "\n".join(parts)


def find_existing(meeting_id: str) -> Optional[dict]:
    row = query_one(
        "SELECT id, metadata->>'body_hash' AS body_hash "
        "FROM thoughts WHERE tenant_id = %s AND thought_type = %s "
        "AND metadata->>'meeting_id' = %s LIMIT 1",
        _tenant_id(), THOUGHT_TYPE, meeting_id,
    )
    return {"id": str(row["id"]), "body_hash": row["body_hash"]} if row else None


def _body_hash(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]


def _run_llm_extraction(thought_id: str) -> Optional[dict]:
    """F3.3 hook: synchronous LLM tag extraction. Errors are caught and logged."""
    try:
        from scripts.extract_tags_batch import extract_tags_for_thought
    except ImportError as exc:
        print(f"  ⚠ LLM extraction unavailable ({exc}); skipping")
        return None
    try:
        result = extract_tags_for_thought(thought_id)
    except Exception as exc:  # noqa: BLE001 — never block ingest
        print(f"  ⚠ LLM extraction error for {thought_id[:8]}: {exc!r}")
        return {"id": thought_id, "status": "error", "reason": repr(exc)}
    if result.get("status") == "ok":
        out = result.get("output", {})
        c = len(out.get("client") or [])
        p = len(out.get("project") or [])
        t = len(out.get("topic") or [])
        print(f"  ✦ tags extracted: C={c} P={p} T={t} conflicts={result.get('conflicts', 0)}")
    elif result.get("status") == "skipped":
        print(f"  ✦ tags cached (run_id={result.get('run_id', '')[:8]})")
    elif result.get("status") == "error":
        print(f"  ⚠ tag extraction error: {result.get('reason', '')}")
    return result


def _emit_edges(thought_id: str, metadata: dict) -> None:
    try:
        et = query_one(
            "SELECT extracted_tags FROM thoughts WHERE id = %s",
            thought_id,
        ) or {}
        thought_for_classify = {
            "id": thought_id,
            "metadata": metadata,
            "extracted_tags": et.get("extracted_tags") or {},
        }
        cls = classify_meeting(thought_for_classify)
        counts = emit_meeting_edges(thought_id, metadata, cls, _tenant_id())
        new_total = sum(counts.values())
        if new_total:
            print(f"  ⚭ edges emitted: attended={counts['attended_meeting']} "
                  f"client={counts['classified_as_client']} "
                  f"project={counts['classified_as_project']}")
    except Exception as exc:  # noqa: BLE001 — never block ingest
        print(f"  ⚠ edge emit error for {thought_id[:8]}: {exc!r}")


def ingest_file(path: Path, dry_run: bool = False, force: bool = False,
                skip_llm_tags: bool = False) -> str:
    text = path.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    sections = parse_sections(text)
    body_after_fm = FRONTMATTER_RE.sub("", text, count=1).lstrip()
    title = resolve_title(fm, body_after_fm, path.stem)

    meeting_id = fm.get("meeting_id") or path.stem
    existing = None if dry_run else find_existing(meeting_id)

    if existing and not force:
        return "skip"

    participants_clean = normalize_participants(fm.get("participants"), source_path=path)
    body = build_body(fm, title, sections, participants=participants_clean)
    body_hash = _body_hash(body)
    metadata = {
        "title": title,
        "meeting_id": meeting_id,
        "source": fm.get("source", "fireflies"),
        "transcript_url": fm.get("transcript_url"),
        "organizer": fm.get("organizer"),
        "participants": participants_clean,
        "tags": fm.get("tags") or [],
        "meeting_type": fm.get("meeting_type"),
        "duration_minutes": fm.get("duration_minutes"),
        "synced_at": str(fm.get("synced_at", "")),
        "overview": sections.get("overview"),
        "action_items": sections.get("action_items"),
        "key_points": sections.get("key_points"),
        "notes": sections.get("notes"),
        "body_hash": body_hash,
    }

    if dry_run:
        return "dry"

    if existing:
        update_where("thoughts", {
            "body": body,
            "metadata": {"domain": "work", **metadata},
            "embedding": get_embedding(body),
        }, "id = %s", existing["id"])
        thought_id = existing["id"]
        body_unchanged = existing.get("body_hash") == body_hash
        if not skip_llm_tags and not body_unchanged:
            _run_llm_extraction(thought_id)
        elif body_unchanged and not skip_llm_tags:
            print("  ✦ tags skipped (body unchanged)")
        _emit_edges(thought_id, metadata)
        return "updated"

    result = ingest_note(
        body=body,
        domain="work",
        thought_type=THOUGHT_TYPE,
        metadata=metadata,
        tenant_id=_tenant_id(),
    )
    thought_id = result.get("thought_id") if isinstance(result, dict) else None
    if thought_id and not skip_llm_tags:
        _run_llm_extraction(str(thought_id))
    if thought_id:
        _emit_edges(str(thought_id), metadata)
    return "ok"


def run_bulk_ingest(dry_run: bool = False, force: bool = False,
                    skip_llm_tags: bool = False, limit: Optional[int] = None) -> int:
    """Iterate meeting-notes dir; ingest each file. Returns exit code."""
    files = sorted(_meeting_notes_dir().glob("*.md"))
    if limit is not None:
        files = files[:limit]
    if not files:
        print(f"No files in {_meeting_notes_dir()}")
        return 0

    counts = {"ok": 0, "updated": 0, "skip": 0, "error": 0, "dry": 0}
    for i, path in enumerate(files, 1):
        try:
            status = ingest_file(path, dry_run=dry_run, force=force,
                                 skip_llm_tags=skip_llm_tags)
            counts[status] = counts.get(status, 0) + 1
            if status in ("ok", "updated"):
                marker = "✓" if status == "ok" else "↻"
                print(f"[{i}/{len(files)}] {marker} {path.name}")
            elif status == "skip":
                print(f"[{i}/{len(files)}] - skip {path.name}")
        except Exception as exc:  # noqa: BLE001
            counts["error"] += 1
            print(f"[{i}/{len(files)}] ERROR {path.name}: {exc}")

    mode = "DRY RUN" if dry_run else "DONE"
    print(f"\n{mode}: ok={counts['ok']}  updated={counts['updated']}  "
          f"skip={counts['skip']}  dry={counts['dry']}  "
          f"error={counts['error']}  total={len(files)}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="exocortex-ingest",
        description="Bulk-ingest vault meeting notes into the thoughts table.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Report counts but skip writes.")
    parser.add_argument("--force", action="store_true",
                        help="Re-ingest even if body hash unchanged.")
    parser.add_argument("--skip-llm-tags", action="store_true",
                        help="Skip LLM tag extraction.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process at most N notes (smoke testing).")
    args = parser.parse_args(list(argv) if argv is not None else None)
    return run_bulk_ingest(
        dry_run=args.dry_run,
        force=args.force,
        skip_llm_tags=args.skip_llm_tags,
        limit=args.limit,
    )


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
