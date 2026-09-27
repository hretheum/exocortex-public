# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Unit tests for exocortex/media.py — archiving remote images into the vault.

Clipped Instagram recipes embed signed CDN URLs that expire in 4-5 days
(measured across 259 notes in the vault), so anything compiled later shows
nothing at all. Downloading needs no session: an expired URL answers
`URL signature expired` with no auth challenge, so the signature is the only
gate and the fetch just has to happen inside the window.

The rules that matter here: never write a non-image body to disk (an error
page must not be saved as a .jpg), never let a failed download break the
caller, and stay deterministic so re-running does not duplicate files.
"""
from __future__ import annotations

import pytest

from exocortex import media


# ── extract_image_urls ─────────────────────────────────────────────────────

def test_extracts_markdown_image():
    body = 'tekst\n\n![](https://cdn.example.com/a.jpg)\n\nwiecej'
    assert media.extract_image_urls(body) == ['https://cdn.example.com/a.jpg']


def test_extracts_markdown_image_with_alt_text():
    body = '![zdjecie dania](https://cdn.example.com/a.jpg)'
    assert media.extract_image_urls(body) == ['https://cdn.example.com/a.jpg']


def test_extracts_html_img():
    body = '<img src="https://cdn.example.com/b.png" alt="x">'
    assert media.extract_image_urls(body) == ['https://cdn.example.com/b.png']


def test_skips_non_http_and_relative():
    body = ('![](data:image/png;base64,AAAA)\n'
            '![](./lokalny.png)\n'
            '![[Pasted image 1.png]]\n'
            '![](https://ok.example.com/c.jpg)')
    assert media.extract_image_urls(body) == ['https://ok.example.com/c.jpg']


def test_deduplicates_preserving_order():
    body = ('![](https://e.com/a.jpg) ![](https://e.com/b.jpg) '
            '![](https://e.com/a.jpg)')
    assert media.extract_image_urls(body) == [
        'https://e.com/a.jpg', 'https://e.com/b.jpg']


def test_empty_body():
    assert media.extract_image_urls('') == []
    assert media.extract_image_urls(None) == []


def test_real_instagram_markup():
    """Shape actually present in the vault's recipe notes."""
    body = ('![](https://scontent-waw2-1.cdninstagram.com/v/t51.71878-15/'
            '508229804_736.jpg?stp=dst-jpg&_nc_cat=111&oe=68A66F04)\n\n'
            '**Source:** [Instagram](https://www.instagram.com/p/C9fF/)')
    urls = media.extract_image_urls(body)
    assert len(urls) == 1
    assert urls[0].endswith('oe=68A66F04')


# ── filenames ──────────────────────────────────────────────────────────────

def test_filename_is_deterministic_from_bytes():
    a = media.filename_for(b'abc', 'image/jpeg')
    b = media.filename_for(b'abc', 'image/jpeg')
    assert a == b


def test_filename_differs_for_different_bytes():
    assert media.filename_for(b'abc', 'image/jpeg') != \
        media.filename_for(b'xyz', 'image/jpeg')


@pytest.mark.parametrize('ctype,ext', [
    ('image/jpeg', '.jpg'), ('image/png', '.png'),
    ('image/webp', '.webp'), ('image/gif', '.gif'),
    ('image/jpeg; charset=binary', '.jpg'),
])
def test_extension_follows_content_type(ctype, ext):
    assert media.filename_for(b'x', ctype).endswith(ext)


# ── archive_images ─────────────────────────────────────────────────────────

def _stub_fetch(mapping):
    def _f(url, *, referer=None):
        if url not in mapping:
            raise media.MediaError(f'404 {url}')
        return mapping[url]
    return _f


def test_downloads_and_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(media, '_fetch', _stub_fetch({
        'https://e.com/a.jpg': (b'JPEGDATA', 'image/jpeg')}))
    names = media.archive_images('![](https://e.com/a.jpg)', tmp_path)
    assert len(names) == 1
    saved = tmp_path / names[0]
    assert saved.read_bytes() == b'JPEGDATA'
    assert saved.suffix == '.jpg'


def test_rerun_yields_same_name_and_writes_once(tmp_path, monkeypatch):
    """Content-addressed naming means the name is only known after the fetch,
    so skipping the download entirely has to be decided by the caller (from
    what is already recorded on the thought). What this layer guarantees is
    that re-running is harmless: same name, one file, no duplicate."""
    monkeypatch.setattr(media, '_fetch',
                        lambda u, referer=None: (b'JPEGDATA', 'image/jpeg'))
    body = '![](https://e.com/a.jpg)'
    first = media.archive_images(body, tmp_path)
    second = media.archive_images(body, tmp_path)
    assert first == second
    assert len(list(tmp_path.glob('*.jpg'))) == 1


def test_non_image_content_type_is_rejected(tmp_path, monkeypatch):
    """An HTML error page must never be saved as an image."""
    monkeypatch.setattr(media, '_fetch', _stub_fetch({
        'https://e.com/a.jpg': (b'<html>403</html>', 'text/html')}))
    assert media.archive_images('![](https://e.com/a.jpg)', tmp_path) == []
    assert list(tmp_path.glob('*')) == []


def test_oversized_image_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'MAX_BYTES', 10)
    monkeypatch.setattr(media, '_fetch', _stub_fetch({
        'https://e.com/a.jpg': (b'x' * 100, 'image/jpeg')}))
    assert media.archive_images('![](https://e.com/a.jpg)', tmp_path) == []


def test_failed_download_does_not_raise_and_keeps_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(media, '_fetch', _stub_fetch({
        'https://e.com/ok.jpg': (b'DATA', 'image/jpeg')}))
    body = '![](https://e.com/dead.jpg)\n![](https://e.com/ok.jpg)'
    names = media.archive_images(body, tmp_path)
    assert len(names) == 1, 'zdrowy obrazek musi przejsc mimo bledu sasiada'


def test_respects_per_note_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'MAX_IMAGES_PER_NOTE', 2)
    monkeypatch.setattr(media, '_fetch',
                        lambda u, referer=None: (u.encode(), 'image/jpeg'))
    body = '\n'.join(f'![](https://e.com/{i}.jpg)' for i in range(5))
    assert len(media.archive_images(body, tmp_path)) == 2


def test_kill_switch_disables_archiving(tmp_path, monkeypatch):
    monkeypatch.setenv('EXOCORTEX_ARCHIVE_MEDIA', '0')
    monkeypatch.setattr(media, '_fetch', _stub_fetch({
        'https://e.com/a.jpg': (b'DATA', 'image/jpeg')}))
    assert media.archive_images('![](https://e.com/a.jpg)', tmp_path) == []


def test_creates_destination_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(media, '_fetch', _stub_fetch({
        'https://e.com/a.jpg': (b'DATA', 'image/jpeg')}))
    dest = tmp_path / 'glebiej' / '_attachments'
    names = media.archive_images('![](https://e.com/a.jpg)', dest)
    assert (dest / names[0]).exists()


def test_referer_is_passed_through(tmp_path, monkeypatch):
    """CDNs commonly gate on Referer; the post URL is what we have."""
    seen = {}

    def _f(url, *, referer=None):
        seen['referer'] = referer
        return (b'DATA', 'image/jpeg')
    monkeypatch.setattr(media, '_fetch', _f)
    media.archive_images('![](https://e.com/a.jpg)', tmp_path,
                         referer='https://www.instagram.com/p/ABC/')
    assert seen['referer'] == 'https://www.instagram.com/p/ABC/'


# ── SSRF ───────────────────────────────────────────────────────────────────
# Image URLs come from clipped pages, i.e. from arbitrary third-party HTML.
# Without a guard a malicious page could make the pipeline GET K12's loopback
# services (Postgres 5432, capture API 8000, llama-swap 8080, Syncthing 8384).
# Blind — nothing is returned to the attacker — but still ours to close.

@pytest.mark.parametrize('host', [
    '127.0.0.1', 'localhost', '10.0.0.5', '192.168.1.1', '172.16.0.1',
    '169.254.169.254',            # cloud metadata
    '[::1]', '0.0.0.0',
])
def test_private_and_loopback_hosts_are_refused(host, tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(media, '_open_url',
                        lambda *a, **k: called.append(a) or (b'x', 'image/jpeg'))
    names = media.archive_images(f'![](http://{host}/a.jpg)', tmp_path)
    assert names == []
    assert called == [], 'zadne polaczenie nie moze wyjsc'


def test_public_host_is_allowed(tmp_path, monkeypatch):
    monkeypatch.setattr(media, '_resolve_ips', lambda h: ['93.184.216.34'])
    monkeypatch.setattr(media, '_open_url', lambda *a, **k: (b'DATA', 'image/jpeg'))
    assert len(media.archive_images('![](https://example.com/a.jpg)', tmp_path)) == 1


def test_unresolvable_host_is_refused(tmp_path, monkeypatch):
    def _boom(h):
        raise OSError('NXDOMAIN')
    monkeypatch.setattr(media, '_resolve_ips', _boom)
    monkeypatch.setattr(media, '_open_url', lambda *a, **k: (b'x', 'image/jpeg'))
    assert media.archive_images('![](https://nie-ma.example/a.jpg)', tmp_path) == []


def test_host_resolving_to_mixed_public_and_private_is_refused(tmp_path, monkeypatch):
    """A hostname that also answers with a private address must not pass."""
    monkeypatch.setattr(media, '_resolve_ips',
                        lambda h: ['93.184.216.34', '127.0.0.1'])
    monkeypatch.setattr(media, '_open_url', lambda *a, **k: (b'x', 'image/jpeg'))
    assert media.archive_images('![](https://zly.example/a.jpg)', tmp_path) == []


@pytest.mark.parametrize('ip,public', [
    ('93.184.216.34', True), ('8.8.8.8', True),
    ('127.0.0.1', False), ('10.1.2.3', False), ('192.168.0.1', False),
    ('172.20.0.1', False), ('169.254.169.254', False), ('::1', False),
    ('fc00::1', False), ('224.0.0.1', False),
])
def test_is_public_ip(ip, public):
    assert media._is_public_ip(ip) is public
