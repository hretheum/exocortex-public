# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Radar channels: new public signals into the lab graph (roadmap task F5.2).

Four channels, each on the source allowlist (lab/sources.yaml) with its
basis for use, downloaded through the lab's fetch gateway and captured
through the same allowlist check as the Capture API:

- ``arxiv-new``: new papers in cs.CL, cs.IR, cs.AI and cs.LG on the topics
  the lab works on (arXiv API);
- ``hf-model``: open-weight text-generation models that are trending on the
  Hugging Face Hub;
- ``dane-gov``: new data sets on the Polish open data portal;
- ``tool-release``: releases of the open-source tools the lab runs.

Only metadata is stored: ids, titles, dates, licenses, links, and for papers
the abstract (CC0). Every item becomes a source and a ``signal`` node.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from exocortex.lab.db import capture_source, insert_edge, upsert_thought

Fetch = Callable[[str], bytes]
ATOM = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
ARXIV_CATEGORIES = ("cs.CL", "cs.IR", "cs.AI", "cs.LG")
ARXIV_TOPICS = ('"knowledge graph"', "retrieval", "claim", "hallucination", '"information extraction"',
                '"fact verification"', "provenance", '"scientific text"', "hedging")
TOOLS = ("ggml-org/llama.cpp", "mostlygeek/llama-swap", "containers/podman", "pgvector/pgvector", "apache/age")


@dataclass
class Item:
    channel: str
    source_type: str
    uri: str
    title: str
    body: str
    published: str | None = None
    metadata: dict = field(default_factory=dict)


class LabFetch:
    """Client of the fetch gateway (exocortex/lab/fetch_gateway.py)."""

    def __init__(self, url: str | None = None, client: httpx.Client | None = None, timeout: float = 120.0):
        url = url or os.environ.get("LAB_FETCH_URL", "unix:/run/lab-fetch/fetch.sock")
        if client is None:
            transport = httpx.HTTPTransport(uds=url.removeprefix("unix:")) if url.startswith("unix:") else None
            client = httpx.Client(transport=transport, timeout=timeout, trust_env=False)
        self.client = client
        self.base = "http://gateway" if url.startswith("unix:") else url.rstrip("/")

    def __call__(self, url: str) -> bytes:
        r = self.client.get(self.base + "/fetch", params={"url": url})
        r.raise_for_status()
        return r.content


def _since(days: int, now: dt.datetime | None = None) -> str:
    return ((now or dt.datetime.now(dt.UTC)) - dt.timedelta(days=days)).strftime("%Y-%m-%d")


def arxiv_new(fetch: Fetch, days: int = 7, max_results: int = 200, now: dt.datetime | None = None) -> list[Item]:
    cats = " OR ".join(f"cat:{c}" for c in ARXIV_CATEGORIES)
    topics = " OR ".join(f"abs:{t}" for t in ARXIV_TOPICS)
    query = urllib.parse.urlencode({"search_query": f"({cats}) AND ({topics})", "sortBy": "submittedDate",
                                    "sortOrder": "descending", "max_results": max_results})
    root = ET.fromstring(fetch(f"https://export.arxiv.org/api/query?{query}"))
    since = _since(days, now)
    items = []
    for e in root.findall("a:entry", ATOM):
        full = (e.findtext("a:id", default="", namespaces=ATOM)).rsplit("/abs/", 1)[-1]
        m = re.match(r"(.+?)v(\d+)$", full)
        published = (e.findtext("a:published", default="", namespaces=ATOM))[:10]
        if not m or published < since:
            continue
        title = " ".join(e.findtext("a:title", default="", namespaces=ATOM).split())
        abstract = " ".join(e.findtext("a:summary", default="", namespaces=ATOM).split())
        cats_found = [c.get("term") for c in e.findall("a:category", ATOM)]
        items.append(Item("arxiv", "arxiv-new", f"https://arxiv.org/abs/{m.group(1)}v{m.group(2)}", title,
                          f"{title}\n\n{abstract}", published,
                          {"arxiv_id": m.group(1), "version": int(m.group(2)), "categories": cats_found}))
    return items


def hf_models(fetch: Fetch, limit: int = 50) -> list[Item]:
    query = urllib.parse.urlencode({"sort": "trendingScore", "direction": -1, "limit": limit,
                                    "pipeline_tag": "text-generation"})
    items = []
    for m in json.loads(fetch(f"https://huggingface.co/api/models?{query}")):
        license_ = next((t.split(":", 1)[1] for t in m.get("tags", []) if t.startswith("license:")), None)
        created = (m.get("createdAt") or "")[:10] or None
        body = (f"{m['id']}: open-weight model for {m.get('pipeline_tag') or 'unknown task'}, "
                f"license {license_ or 'not declared'}, created {created or 'unknown'}.")
        items.append(Item("models", "hf-model", f"https://huggingface.co/{m['id']}", m["id"], body, created,
                          {"model_id": m["id"], "license": license_, "pipeline_tag": m.get("pipeline_tag"),
                           "likes": m.get("likes"), "downloads": m.get("downloads"),
                           "trending_score": m.get("trendingScore")}))
    return items


_TAG = re.compile(r"<[^>]+>")


def dane_gov(fetch: Fetch, limit: int = 50) -> list[Item]:
    query = urllib.parse.urlencode({"page": 1, "per_page": limit, "sort": "-created"})
    doc = json.loads(fetch(f"https://api.dane.gov.pl/1.4/datasets?{query}"))
    items = []
    for d in doc.get("data") or []:
        a = d.get("attributes") or {}
        notes = " ".join(_TAG.sub(" ", a.get("notes") or "").split())[:2000]
        created = (a.get("created") or "")[:10] or None
        items.append(Item("open-data", "dane-gov", f"https://dane.gov.pl/pl/dataset/{d['id']}",
                          a.get("title") or str(d["id"]), f"{a.get('title') or ''}\n\n{notes}".strip(), created,
                          {"dataset_id": d["id"], "license": a.get("license_name"), "category":
                           (a.get("category") or {}).get("title") if isinstance(a.get("category"), dict) else None,
                           "keywords": a.get("keywords"), "formats": a.get("formats")}))
    return items


def tool_releases(fetch: Fetch, repos: tuple[str, ...] = TOOLS, per_repo: int = 3) -> list[Item]:
    items = []
    for repo in repos:
        rows = json.loads(fetch(f"https://api.github.com/repos/{repo}/releases?per_page={per_repo}"))
        for r in rows:
            if r.get("draft"):
                continue
            date = (r.get("published_at") or "")[:10] or None
            name = r.get("name") or r["tag_name"]
            # the source address is the release in the API, the domain the allowlist names; the page link
            # is kept as metadata
            api_uri = f"https://api.github.com/repos/{repo}/releases/tags/{urllib.parse.quote(r['tag_name'])}"
            items.append(Item("tools", "tool-release", api_uri, f"{repo} {r['tag_name']}",
                              f"{repo}: release {name} ({r['tag_name']}), published {date}.", date,
                              {"repo": repo, "tag": r["tag_name"], "prerelease": bool(r.get("prerelease")),
                               "html_url": r.get("html_url")}))
    return items


CHANNELS = {"arxiv": arxiv_new, "models": hf_models, "open-data": dane_gov, "tools": tool_releases}


def ingest(conn, tenant: str, items: list[Item], embed=None) -> dict:
    """Capture every item (allowlist check) and write its ``signal`` node; returns counts per channel."""
    counts: dict[str, dict] = {}
    new_nodes: list[tuple[str, str]] = []
    for it in items:
        c = counts.setdefault(it.channel, {"items": 0, "new": 0})
        c["items"] += 1
        meta = {**it.metadata, "channel": it.channel, "published": it.published, "title": it.title}
        sid, changed = capture_source(conn, tenant, source_type=it.source_type, uri=it.uri, title=it.title,
                                      metadata={**meta, "raw_payload": it.body})
        tid, created = upsert_thought(conn, tenant, source_id=sid, thought_type="signal", body=it.body,
                                      metadata={**meta, "domain": "lab", "uri": it.uri})
        insert_edge(conn, tenant, tid, "thought", sid, "raw_source", "acquired_from")
        c["new"] += created
        if created:
            new_nodes.append((tid, it.body))
    if embed is not None and new_nodes:
        for i in range(0, len(new_nodes), 32):
            chunk = new_nodes[i:i + 32]
            for (tid, _), vec in zip(chunk, embed([b for _, b in chunk])):
                conn.execute("UPDATE thoughts SET embedding = %s WHERE id = %s",
                             ("[" + ",".join(repr(float(x)) for x in vec) + "]", tid))
    return counts
