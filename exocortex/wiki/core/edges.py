# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Edges index and synthesis loaders for wiki compilation."""

from __future__ import annotations

import logging
from collections import defaultdict

from exocortex.db import query

from exocortex.wiki.util.slugs import _slug_from_email


def _load_active_syntheses(tenant_id: str) -> dict[tuple[str, str], dict]:
    """Bulk-load latest active syntheses keyed by (perspective_type, perspective_key).

    One round-trip instead of N. Returns {} on failure (synthesis is optional —
    wiki must compile even when synthesizer hasn't run yet).
    """
    sql = (
        "SELECT perspective_type, perspective_key, id, content, "
        "       generated_at, source_thought_ids, input_hash, model, prompt_version "
        "FROM syntheses "
        "WHERE tenant_id = %s AND superseded_by IS NULL"
    )
    try:
        rows = query(sql, tenant_id)
    except Exception as exc:
        logging.warning("[wiki_compiler] cannot load syntheses: %r", exc)
        return {}
    return {(r["perspective_type"], r["perspective_key"]): r for r in rows}


# F4.6.2 — edges index built once per compile and shared across entity renderers.
class EdgesIndex:
    """Read-only index over the `edges` table for entity-page rendering.

    All members are dicts populated in one DB round-trip. Empty dicts when the
    table is empty (graceful no-op for fresh installs).

    Members:
      attended_by_meeting: meeting_id (str) -> list of person slugs (str)
      attended_by_person:  person slug (str) -> list of meeting_ids (str)
      decided_in_by_meeting: thought_id -> list of synthesis ids that decided in it
      addresses_problem_by_meeting: thought_id -> list of synthesis ids
      mentions_person_by_synthesis: synthesis_id -> list of person slugs
      mentions_synthesis_by_person: person slug -> list of synthesis ids
    """

    __slots__ = (
        "attended_by_meeting",
        "attended_by_person",
        "decided_in_by_meeting",
        "addresses_problem_by_meeting",
        "mentions_person_by_synthesis",
        "mentions_synthesis_by_person",
        "meetings_classified_as_client",
        "meetings_classified_as_project",
        "inspirations_by_client_slug",
    )

    def __init__(self) -> None:
        self.attended_by_meeting: dict[str, list[str]] = defaultdict(list)
        self.attended_by_person: dict[str, list[str]] = defaultdict(list)
        self.decided_in_by_meeting: dict[str, list[str]] = defaultdict(list)
        self.addresses_problem_by_meeting: dict[str, list[str]] = defaultdict(list)
        self.mentions_person_by_synthesis: dict[str, list[str]] = defaultdict(list)
        self.mentions_synthesis_by_person: dict[str, list[str]] = defaultdict(list)
        self.meetings_classified_as_client: dict[str, list[str]] = defaultdict(list)
        self.meetings_classified_as_project: dict[str, list[str]] = defaultdict(list)
        # F8.8.x.G T3 — cross-domain newsletter inspirations per client.
        # Each entry: {cluster_slug, relevance_score, reason, judged_at}.
        self.inspirations_by_client_slug: dict[str, list[dict]] = defaultdict(list)


def _load_edges_index(tenant_id: str) -> EdgesIndex:
    """Bulk-load all reasoning edges and bucket them into per-entity lookup tables.

    For person/client/project edges, the dst_id is an `entities.id` UUID (not a
    slug). We resolve UUID -> wiki slug via the entities table:
      - person:  canonical_name is either an email (-> _slug_from_email) or an
                 already-slug-style name (julia / pawikowska) -> used as-is.
      - client/project: canonical_name is the slug.
    Unknown UUIDs are dropped silently — they correspond to free-text mentions
    the synthesizer can't reconcile to a wiki entity.

    One query per edge type. Returns an empty EdgesIndex when DB is unreachable
    (compile must still succeed for users without edges populated).
    """
    idx = EdgesIndex()
    try:
        ent_rows = query(
            "SELECT id::text AS id, canonical_name, type "
            "FROM entities WHERE tenant_id = %s",
            tenant_id,
        )
    except Exception as exc:
        logging.warning("[wiki_compiler] cannot load entities: %r", exc)
        ent_rows = []

    person_uuid_to_slug: dict[str, str] = {}
    other_uuid_to_slug: dict[str, str] = {}
    for er in ent_rows:
        eid = er["id"]
        cname = (er.get("canonical_name") or "").strip()
        if not cname:
            continue
        if er["type"] == "person":
            if "@" in cname:
                person_uuid_to_slug[eid] = _slug_from_email(cname)
            else:
                person_uuid_to_slug[eid] = cname.lower().replace(" ", "-")
        else:  # client / project — canonical_name already a slug
            other_uuid_to_slug[eid] = cname

    sql = (
        "SELECT src_id::text AS src_id, src_type, dst_id::text AS dst_id, dst_type, type "
        "FROM edges WHERE tenant_id = %s"
    )
    try:
        rows = query(sql, tenant_id)
    except Exception as exc:
        logging.warning("[wiki_compiler] cannot load edges: %r", exc)
        return idx

    for r in rows:
        et = r["type"]
        s, d = r["src_id"], r["dst_id"]
        if et == "attended_meeting":
            # thought (meeting) -> person  (dst_id = entity_id of person)
            person_slug = person_uuid_to_slug.get(d)
            if not person_slug:
                continue
            idx.attended_by_meeting[s].append(person_slug)
            idx.attended_by_person[person_slug].append(s)
        elif et == "decided_in":
            # synthesis -> thought (the decision's source meeting)
            idx.decided_in_by_meeting[d].append(s)
        elif et == "addresses_problem":
            idx.addresses_problem_by_meeting[d].append(s)
        elif et == "mentions_person":
            person_slug = person_uuid_to_slug.get(d)
            if not person_slug:
                continue
            idx.mentions_person_by_synthesis[s].append(person_slug)
            idx.mentions_synthesis_by_person[person_slug].append(s)
        elif et == "classified_as_client":
            client_slug = other_uuid_to_slug.get(d)
            if not client_slug:
                continue
            idx.meetings_classified_as_client[client_slug].append(s)
        elif et == "classified_as_project":
            project_slug = other_uuid_to_slug.get(d)
            if not project_slug:
                continue
            idx.meetings_classified_as_project[project_slug].append(s)

    # F8.8.x.G T3 — load cross-domain matches (newsletter cluster × client
    # syntheses, score >=6) and bucket per client slug. Sidecar table only
    # exists on installs that ran schema/16_cross_domain_matches.sql; defensive
    # try/except keeps the compile working on fresh DBs.
    try:
        cdm_rows = query(
            "SELECT "
            "  c.perspective_key AS client_slug, "
            "  n.perspective_key AS cluster_slug, "
            "  cdm.relevance_score, "
            "  cdm.reason, "
            "  cdm.judged_at "
            "FROM cross_domain_matches cdm "
            "JOIN syntheses c ON c.id = cdm.client_synthesis_id "
            "JOIN syntheses n ON n.id = cdm.cluster_synthesis_id "
            "WHERE cdm.tenant_id = %s "
            "  AND cdm.relevance_score >= 6 "
            "  AND c.superseded_by IS NULL "
            "  AND n.superseded_by IS NULL "
            "ORDER BY c.perspective_key ASC, "
            "         cdm.relevance_score DESC, "
            "         cdm.judged_at DESC, "
            "         n.perspective_key ASC",
            tenant_id,
        )
    except Exception as exc:
        logging.warning("[wiki_compiler] cannot load cross_domain_matches: %r", exc)
        cdm_rows = []

    for r in cdm_rows:
        cs = (r.get("client_slug") or "").strip().lower()
        nls = (r.get("cluster_slug") or "").strip().lower()
        if not cs or not nls:
            continue
        idx.inspirations_by_client_slug[cs].append(
            {
                "cluster_slug": nls,
                "relevance_score": int(r["relevance_score"]),
                "reason": (r.get("reason") or "").strip(),
                "judged_at": r.get("judged_at"),
            }
        )

    print(
        f"[wiki_compiler] loaded edges index ({len(rows)} rows, "
        f"{len(ent_rows)} entities; "
        f"{len(idx.attended_by_meeting)} meetings have attendance, "
        f"{len(idx.decided_in_by_meeting)} meetings sourced decisions, "
        f"{len(idx.mentions_person_by_synthesis)} syntheses mention persons; "
        f"{sum(len(v) for v in idx.inspirations_by_client_slug.values())} "
        f"cross-domain inspirations across {len(idx.inspirations_by_client_slug)} clients)"
    )
    return idx
