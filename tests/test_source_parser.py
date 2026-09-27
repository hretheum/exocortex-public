# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# tests/test_source_parser.py — F27.1: L1 source-file parser.
#
# Pure-filesystem tests: write small `.md` fixtures into a tmp_path tree and
# assert parse_source_file() preserves title, section_path, frontmatter, tags,
# wikilinks, and heading-chunks. No DB / network.

from __future__ import annotations

from pathlib import Path

import exocortex.wiki_compiler as wc


# ── canonical acceptance case (from F27.1 backlog) ────────────────────────────

def test_pillar_file_acceptance(tmp_path: Path):
    """The acceptance test spelled out in `F27.1.md`: parsing the real ACME
    CoE pillar file shape yields the expected title + section_path + tags."""
    vault = tmp_path
    src_root = vault / '_source' / 'work' / 'acme' / 'CoE'
    f = src_root / '01_STRATEGY' / '02_Five Strategic Pillars' / 'Pillar 1 - Design Excellence & QA.md'
    f.parent.mkdir(parents=True)
    f.write_text(
        '---\n'
        'pillar_id: P1\n'
        'status: active\n'
        'tags:\n'
        '  - coe/strategy\n'
        '  - pillar/p1-quality\n'
        '  - coe/ai\n'
        'type: pillar\n'
        '---\n'
        '# Pillar 1 — Design Excellence & QA\n'
        '\n'
        '## Cel\n'
        'Uczynić jakość designu mierzalną.\n'
        '\n'
        'See [[Pillar 2 - Design System Platform]] and [[Roadmap#Q4 2026|the roadmap]].\n',
        encoding='utf-8',
    )

    doc = wc.parse_source_file(f, src_root, vault_root=vault)

    assert doc['title'] == 'Pillar 1 - Design Excellence & QA'  # filename stem
    assert doc['h1'] == 'Pillar 1 — Design Excellence & QA'     # H1 kept separately
    assert doc['canonical_name'] == 'Pillar 1 - Design Excellence & QA'
    assert doc['section_path'] == ['01_STRATEGY', '02_Five Strategic Pillars']
    assert doc['path'] == ('_source/work/acme/CoE/01_STRATEGY/02_Five Strategic Pillars/'
                           'Pillar 1 - Design Excellence & QA.md')
    assert doc['type'] == 'pillar'
    assert doc['status'] == 'active'
    assert doc['frontmatter']['pillar_id'] == 'P1'
    assert doc['tags'] == ['coe/strategy', 'pillar/p1-quality', 'coe/ai']

    # typed_tags: axis-decomposed
    by_axis = {r['raw']: r for r in doc['typed_tags']}
    assert by_axis['pillar/p1-quality'] == {
        'axis': 'pillar', 'value': 'p1-quality', 'raw': 'pillar/p1-quality'}
    assert by_axis['coe/strategy']['axis'] == 'coe'
    assert by_axis['coe/strategy']['value'] == 'strategy'

    # wikilinks
    targets = {(lk['target'], lk['header'], lk['alias']) for lk in doc['links_outgoing']}
    assert ('Pillar 2 - Design System Platform', None, None) in targets
    assert ('Roadmap', 'Q4 2026', 'the roadmap') in targets

    # chunks: leading text (none here) + ## Cel
    headings = [c['heading'] for c in doc['chunks']]
    assert 'Cel' in headings


# ── title fallbacks ───────────────────────────────────────────────────────────

def test_title_prefers_frontmatter_title(tmp_path: Path):
    src_root = tmp_path
    f = src_root / 'note-with-explicit-title.md'
    f.write_text('---\ntitle: A Nicer Display Title\n---\n# Some H1\nbody\n', encoding='utf-8')
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    assert doc['title'] == 'A Nicer Display Title'
    assert doc['h1'] == 'Some H1'
    assert doc['canonical_name'] == 'note-with-explicit-title'


def test_title_falls_back_to_filename_when_no_frontmatter(tmp_path: Path):
    src_root = tmp_path
    f = src_root / 'Just A File.md'
    f.write_text('# An H1 that is not the title source\nbody\n', encoding='utf-8')
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    assert doc['title'] == 'Just A File'
    assert doc['h1'] == 'An H1 that is not the title source'
    assert doc['frontmatter'] == {}


# ── edge cases: missing / broken frontmatter, weird tags, nesting ─────────────

def test_broken_yaml_frontmatter_degrades_gracefully(tmp_path: Path):
    src_root = tmp_path
    f = src_root / 'bad-yaml.md'
    f.write_text('---\nthis: : is : not : valid : yaml\n  - nope\n---\n# Title\ncontent\n',
                 encoding='utf-8')
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    assert doc['frontmatter'] == {}
    assert doc['title'] == 'bad-yaml'
    assert doc['content'].startswith('# Title')


def test_comma_separated_tags_string(tmp_path: Path):
    src_root = tmp_path
    f = src_root / 'csv-tags.md'
    f.write_text('---\ntags: "foo, bar/baz , #qux"\n---\nbody\n', encoding='utf-8')
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    assert doc['tags'] == ['foo', 'bar/baz', 'qux']
    by_axis = {r['raw']: r for r in doc['typed_tags']}
    assert by_axis['bar/baz']['axis'] == 'bar'


def test_legacy_singular_tag_key(tmp_path: Path):
    src_root = tmp_path
    f = src_root / 'legacy-tag.md'
    f.write_text('---\ntag: solo\n---\nbody\n', encoding='utf-8')
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    assert doc['tags'] == ['solo']


def test_deeply_nested_section_path(tmp_path: Path):
    src_root = tmp_path / 'CoE'
    f = src_root / '10_ACME_PULSE' / 'Evidence Briefs' / 'sub' / 'brief.md'
    f.parent.mkdir(parents=True)
    f.write_text('# Brief\n', encoding='utf-8')
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    assert doc['section_path'] == ['10_ACME_PULSE', 'Evidence Briefs', 'sub']


def test_file_at_section_root_has_empty_section_path(tmp_path: Path):
    src_root = tmp_path / 'CoE'
    src_root.mkdir()
    f = src_root / 'CoE-infra.md'
    f.write_text('# Infra\n', encoding='utf-8')
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    assert doc['section_path'] == []


def test_path_outside_source_root_degrades(tmp_path: Path):
    src_root = tmp_path / 'CoE'
    src_root.mkdir()
    other = tmp_path / 'elsewhere' / 'stray.md'
    other.parent.mkdir(parents=True)
    other.write_text('# Stray\n', encoding='utf-8')
    doc = wc.parse_source_file(other, src_root, vault_root=tmp_path)
    assert doc['section_path'] == []
    assert doc['path'] == 'elsewhere/stray.md'


def test_provenance_pulled_from_frontmatter(tmp_path: Path):
    src_root = tmp_path
    f = src_root / 'ai-doc.md'
    f.write_text('---\nprovenance: ai_authored\n---\nbody\n', encoding='utf-8')
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    assert doc['provenance'] == 'ai_authored'

    f2 = src_root / 'human-doc.md'
    f2.write_text('# Human\nbody\n', encoding='utf-8')
    doc2 = wc.parse_source_file(f2, src_root, vault_root=tmp_path)
    assert doc2['provenance'] is None


# ── wikilink + chunk specifics ────────────────────────────────────────────────

def test_wikilinks_ignore_code_fences_and_dedupe(tmp_path: Path):
    src_root = tmp_path
    f = src_root / 'links.md'
    f.write_text(
        '# Links\n'
        '[[Real Link]] and [[Real Link]] again (dedup).\n'
        '```\n'
        '[[Not A Link Inside Fence]]\n'
        '```\n'
        '[[Another|aliased]]\n',
        encoding='utf-8',
    )
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    targets = [lk['target'] for lk in doc['links_outgoing']]
    assert targets.count('Real Link') == 1
    assert 'Not A Link Inside Fence' not in targets
    assert 'Another' in targets
    assert next(lk for lk in doc['links_outgoing'] if lk['target'] == 'Another')['alias'] == 'aliased'


def test_h1_skips_code_fence(tmp_path: Path):
    src_root = tmp_path
    f = src_root / 'fenced.md'
    f.write_text('```python\n# this is a comment, not an H1\n```\n# Real H1\nbody\n',
                 encoding='utf-8')
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    assert doc['h1'] == 'Real H1'


def test_chunks_split_on_subheadings_keep_leading_text(tmp_path: Path):
    src_root = tmp_path
    f = src_root / 'chunked.md'
    f.write_text(
        '# Doc Title\n'
        'Intro paragraph before any subheading.\n'
        '## Section A\n'
        'Body of A.\n'
        '### Sub A1\n'
        'Body of A1.\n'
        '## Section B\n'
        'Body of B.\n',
        encoding='utf-8',
    )
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    headings = [c['heading'] for c in doc['chunks']]
    assert headings[0] is None  # leading text (incl. the # Doc Title line)
    assert 'Section A' in headings
    assert 'Sub A1' in headings
    assert 'Section B' in headings
    sub = next(c for c in doc['chunks'] if c['heading'] == 'Sub A1')
    assert sub['level'] == 3
    assert sub['text'].endswith('Body of A1.')


def test_no_frontmatter_no_h1(tmp_path: Path):
    src_root = tmp_path
    f = src_root / 'plain.md'
    f.write_text('just some text, no headings, no frontmatter\n', encoding='utf-8')
    doc = wc.parse_source_file(f, src_root, vault_root=tmp_path)
    assert doc['h1'] is None
    assert doc['title'] == 'plain'
    assert doc['tags'] == []
    assert doc['links_outgoing'] == []
    assert len(doc['chunks']) == 1


# ── iter_source_files sweep ───────────────────────────────────────────────────

def test_iter_source_files_skips_obsidian_and_bad_files(tmp_path: Path):
    src_root = tmp_path / 'CoE'
    (src_root / '01_X').mkdir(parents=True)
    (src_root / '.obsidian').mkdir()
    (src_root / '01_X' / 'good.md').write_text('# Good\n', encoding='utf-8')
    (src_root / '.obsidian' / 'config.md').write_text('# Should be skipped\n', encoding='utf-8')
    docs = list(wc.iter_source_files(src_root, vault_root=tmp_path))
    names = {d['canonical_name'] for d in docs}
    assert names == {'good'}
    assert docs[0]['section_path'] == ['01_X']
