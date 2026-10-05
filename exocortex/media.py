# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.
"""Archive remote images referenced by a source note into the vault.

Clipped Instagram recipes embed signed CDN URLs that expire in 4-5 days
(measured across 259 notes in the vault), so a page compiled any later shows
nothing. Fetching needs no session: an expired URL answers `URL signature
expired` with no auth challenge and no Set-Cookie, so the signature in the URL
is the only gate — the download just has to happen inside the window. Ingest
runs hourly, comfortably inside it.

Two deliberate non-goals:

* **Source notes are never rewritten.** They sit in a watched folder, so
  editing them would re-trigger ingest and re-run LLM extraction — the exact
  path that wiped 66 recipe titles on 2026-08-02. The archived filename is
  recorded on the thought instead, and the compiled wiki page embeds it.
* **Nothing here is retried or recovered.** Once a signature expires the image
  is gone for good; a failed download is logged and skipped, never fatal to
  the compile or ingest that triggered it.

Files are named by a hash of their content, so re-running is harmless and the
same image shared by two notes is stored once. Note that the name is only known
*after* the download — skipping the fetch entirely is the caller's job, from
what is already recorded on the thought.

URLs come from clipped third-party HTML, so every one is checked against
`_assert_fetchable` before a connection is opened; see that function for the
threat and for the residual risk it does not close.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

# A single recipe photo is well under a megabyte; the cap is a sanity bound on
# a mis-typed URL pointing at something huge, not a tuning knob.
MAX_BYTES = 15 * 1024 * 1024
MAX_IMAGES_PER_NOTE = 10
TIMEOUT_S = 20

# Instagram's CDN serves jpeg/webp; the rest are here so this stays useful for
# other clipping sources. A body whose type is absent from this map is not
# written to disk at all — an HTML error page must never land as a .jpg.
_EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}

_MD_IMAGE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
_HTML_IMAGE = re.compile(r"""<img[^>]+src=["'](https?://[^"']+)["']""", re.IGNORECASE)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


class MediaError(Exception):
    """A single image could not be fetched. Never escapes archive_images()."""


def archiving_enabled() -> bool:
    """Kill switch for the pipeline's only outbound image traffic."""
    return os.environ.get("EXOCORTEX_ARCHIVE_MEDIA", "1").strip() not in (
        "0", "false", "no", ""
    )


def extract_image_urls(body: str | None) -> list[str]:
    """Remote image URLs in a note body, in order, without duplicates.

    Only absolute http(s) URLs — `data:` payloads are already inline and
    Obsidian embeds (`![[...]]`) are already local.
    """
    if not body:
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for pattern in (_MD_IMAGE, _HTML_IMAGE):
        for m in pattern.finditer(body):
            url = m.group(1)
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def filename_for(data: bytes, content_type: str) -> str:
    """Content-addressed filename, so the same image is stored once."""
    ext = _EXT_BY_TYPE.get((content_type or "").split(";")[0].strip().lower(), "")
    return hashlib.sha256(data).hexdigest()[:16] + ext


def _is_public_ip(ip: str) -> bool:
    """False for anything that could reach K12's own services."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private or addr.is_loopback or addr.is_link_local
        or addr.is_multicast or addr.is_reserved or addr.is_unspecified
    )


def _resolve_ips(host: str) -> list[str]:
    """Every address `host` answers with. Raises OSError if it resolves to none."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [str(i[4][0]) for i in infos]  # sockaddr[0] is the address string for AF_INET/AF_INET6


def _assert_fetchable(url: str) -> None:
    """Refuse anything that is not a public http(s) endpoint.

    Image URLs arrive from clipped third-party HTML, so a hostile page could
    otherwise point the pipeline at the host's loopback services (Postgres 5432,
    capture API 8000, llama-swap 8080, Syncthing 8384) or at a cloud metadata
    address. Blind — no response ever reaches the page author — but a GET to
    an internal endpoint is not ours to make.

    Residual risk, stated plainly: the name is resolved here and again by the
    connection itself, so a DNS entry that flips between the two answers could
    still slip through. Closing that needs pinning the connection to the
    validated address; not done, and out of proportion to a personal vault.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise MediaError(f"scheme not allowed: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise MediaError("no host in URL")
    try:
        ips = _resolve_ips(host)
    except OSError as exc:
        raise MediaError(f"cannot resolve {host}: {exc}") from exc
    if not ips:
        raise MediaError(f"{host} resolves to nothing")
    for ip in ips:
        if not _is_public_ip(ip):
            raise MediaError(f"{host} resolves to non-public address {ip}")


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    """A public URL must not be able to redirect us onto a private one."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _assert_fetchable(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_url(req: urllib.request.Request, timeout: int) -> tuple[bytes, str]:
    opener = urllib.request.build_opener(_ValidatingRedirectHandler)
    with opener.open(req, timeout=timeout) as resp:
        return resp.read(MAX_BYTES + 1), resp.headers.get("Content-Type", "")


def _fetch(url: str, *, referer: str | None = None) -> tuple[bytes, str]:
    """Download one URL. Raises MediaError on any failure."""
    _assert_fetchable(url)
    headers = {"User-Agent": _UA}
    if referer:
        # Some CDNs gate on Referer; the post URL is what the note carries.
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    try:
        return _open_url(req, TIMEOUT_S)
    except MediaError:
        raise
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise MediaError(f"{type(exc).__name__}: {exc}") from exc


def archive_images(
    body: str | None,
    dest_dir: Path,
    *,
    referer: str | None = None,
) -> list[str]:
    """Download images referenced in `body` into `dest_dir`.

    Returns the filenames actually stored (already-present ones included).
    Never raises: a source with an unreachable image still gets processed,
    it just gets fewer pictures.
    """
    if not archiving_enabled():
        return []
    urls = extract_image_urls(body)[:MAX_IMAGES_PER_NOTE]
    if not urls:
        return []

    dest_dir = Path(dest_dir)
    stored: list[str] = []
    for url in urls:
        try:
            data, ctype = _fetch(url, referer=referer)
        except MediaError as exc:
            # Expected once a signature expires — worth seeing, not worth failing.
            logger.warning("media: could not fetch %s — %s", url[:120], exc)
            continue
        if len(data) > MAX_BYTES:
            logger.warning("media: %s exceeds %d bytes — skipped", url[:120], MAX_BYTES)
            continue
        name = filename_for(data, ctype)
        if not Path(name).suffix:
            logger.warning(
                "media: %s returned content-type %r, not an image — skipped",
                url[:120], ctype,
            )
            continue
        target = dest_dir / name
        if target.exists():
            stored.append(name)
            continue
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".part")
            tmp.write_bytes(data)
            os.replace(tmp, target)
        except OSError as exc:
            logger.warning("media: could not write %s — %r", target, exc)
            continue
        stored.append(name)
    return stored
