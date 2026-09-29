# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""The lab's fetch gateway and the radar channels (roadmap task F5.2)."""
from __future__ import annotations

import datetime as dt
import io
import json
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from exocortex.lab import signals
from exocortex.lab.fetch_gateway import Fetcher
from exocortex.source_allowlist import Allowlist

ROOT = Path(__file__).resolve().parents[2]


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeOpener:
    def __init__(self, routes: dict):
        self.routes, self.seen = routes, []

    def open(self, req, timeout=None):
        url = req.full_url
        self.seen.append(url)
        target = self.routes[url]
        if isinstance(target, str):  # a redirect
            headers = Message()
            headers["Location"] = target
            raise urllib.error.HTTPError(url, 302, "Found", headers, io.BytesIO(b""))
        return FakeResponse(target)


def _fetcher(routes, **kw):
    clock = {"t": 0.0}
    waits = []

    def sleep(s):
        waits.append(round(s, 3))
        clock["t"] += s

    f = Fetcher(Allowlist.load(ROOT / "lab" / "sources.yaml"), opener=FakeOpener(routes), clock=lambda: clock["t"],
                sleep=sleep, **kw)
    return f, waits


def test_only_https_urls_of_allowed_sources_are_fetched():
    f, _ = _fetcher({"https://api.github.com/repos/a/b/releases": b"[]"})
    assert f.handle("GET", "/fetch?url=https%3A%2F%2Fapi.github.com%2Frepos%2Fa%2Fb%2Freleases")[0] == 200
    for url in ("https://example.com/", "http://api.github.com/repos/a/b", "https://user:pw@api.github.com/x",
                "https://api.github.com:8443/x", "file:///etc/passwd", "https://api.github.com.evil.io/x"):
        assert f.refusal(url) is not None, url
    assert f.handle("POST", "/fetch?url=https://api.github.com/x")[0] == 403
    assert f.handle("GET", "/other")[0] == 403
    assert f.handle("GET", "http://evil/fetch?url=https://api.github.com/x")[0] == 403
    assert f.handle("GET", "/fetch")[0] == 400
    assert f.handle("GET", "/health")[0] == 200


def test_redirects_are_followed_only_to_allowed_urls():
    f, _ = _fetcher({"https://huggingface.co/api/a": "https://huggingface.co/api/b", "https://huggingface.co/api/b": b"ok",
                     "https://huggingface.co/api/c": "https://evil.example/x"})
    assert f.fetch("https://huggingface.co/api/a")[:2] == (200, b"ok")
    status, body, _, _ = f.fetch("https://huggingface.co/api/c")
    assert status == 403 and b"domain not on the allowlist" in body
    assert "https://evil.example/x" not in f.opener.seen


def test_requests_to_one_host_keep_the_source_interval():
    f, waits = _fetcher({f"https://export.arxiv.org/api/query?n={i}": b"<feed/>" for i in range(3)})
    for i in range(3):
        f.fetch(f"https://export.arxiv.org/api/query?n={i}")
    assert waits == [3.0, 3.0]  # arXiv asks for three seconds between requests


def test_large_responses_are_cut_off():
    f, _ = _fetcher({"https://api.github.com/big": b"x" * 100}, max_bytes=10)
    assert f.fetch("https://api.github.com/big")[0] == 502


ARXIV = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>http://arxiv.org/abs/2609.34056v1</id><published>2026-09-28T00:26:19Z</published>
    <title>Steering  Goals</title><summary>We study   value transplant.</summary>
    <category term="cs.CL"/><category term="cs.LG"/></entry>
  <entry><id>http://arxiv.org/abs/2601.00001v2</id><published>2026-01-02T00:00:00Z</published>
    <title>Old</title><summary>Old paper.</summary></entry>
</feed>"""


def test_arxiv_channel_keeps_recent_papers_with_their_abstract():
    seen = []

    def fetch(url):
        seen.append(url)
        return ARXIV.encode()

    items = signals.arxiv_new(fetch, days=7, now=dt.datetime(2026, 9, 29, tzinfo=dt.timezone.utc))
    assert [i.uri for i in items] == ["https://arxiv.org/abs/2609.34056v1"]
    assert items[0].body == "Steering Goals\n\nWe study value transplant." and items[0].metadata["categories"] == [
        "cs.CL", "cs.LG"]
    assert "cat%3Acs.CL" in seen[0] and "export.arxiv.org" in seen[0]


def test_models_open_data_and_tool_channels_parse_their_apis():
    hf = [{"id": "org/model", "createdAt": "2026-09-16T06:44:40.000Z", "pipeline_tag": "text-generation",
           "likes": 3, "downloads": 5, "trendingScore": 7, "tags": ["license:apache-2.0", "gguf"]}]
    items = signals.hf_models(lambda url: json.dumps(hf).encode())
    assert items[0].uri == "https://huggingface.co/org/model" and items[0].metadata["license"] == "apache-2.0"
    dane = {"data": [{"id": 4242, "attributes": {"title": "Jakość powietrza", "notes": "<p>Dane <b>godzinowe</b></p>",
                                                  "created": "2026-09-20T10:00:00Z", "license_name": "CC BY 4.0"}}]}
    items = signals.dane_gov(lambda url: json.dumps(dane).encode())
    assert items[0].uri == "https://dane.gov.pl/pl/dataset/4242" and items[0].body.endswith("Dane godzinowe")
    assert items[0].metadata["license"] == "CC BY 4.0"
    rel = [{"tag_name": "v1.2", "name": "", "published_at": "2026-09-27T01:00:00Z", "html_url": "https://github.com/a/b/releases/tag/v1.2",
            "draft": False, "prerelease": False}, {"tag_name": "v1.3-draft", "draft": True}]
    items = signals.tool_releases(lambda url: json.dumps(rel).encode(), repos=("a/b",))
    assert [i.title for i in items] == ["a/b v1.2"] and items[0].published == "2026-09-27"


def test_every_channel_uses_an_allowed_source_type_and_domain():
    allow = Allowlist.load(ROOT / "lab" / "sources.yaml")
    samples = {"arxiv": ("arxiv-new", "https://arxiv.org/abs/2609.34056v1"),
               "models": ("hf-model", "https://huggingface.co/org/model"),
               "open-data": ("dane-gov", "https://dane.gov.pl/pl/dataset/1"),
               "tools": ("tool-release", "https://api.github.com/repos/a/b/releases")}
    for channel, (source_type, uri) in samples.items():
        assert channel in signals.CHANNELS
        assert allow.check(source_type, uri)[0], channel


@pytest.mark.parametrize("url", ["https://export.arxiv.org/api/query?x=1", "https://huggingface.co/api/models",
                                 "https://api.dane.gov.pl/1.4/datasets", "https://api.github.com/repos/a/b/releases"])
def test_every_channel_url_passes_the_fetch_gateway(url):
    f, _ = _fetcher({})
    assert f.refusal(url) is None
