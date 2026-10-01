# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# tests/test_graph_rag_provenance.py — F27.5: provenance-aware ranking + scope.
#
# Pure-function tests over rrf_fuse() / provenance helpers. No DB / network.

from __future__ import annotations

import os

os.environ.setdefault('TENANT_ID', 'test-tenant')

from exocortex.graph_rag import (
    PROVENANCE_WEIGHT,
    _client_scope_of,
    provenance_of,
    provenance_weight,
    rrf_fuse,
)


def _hit(thought_id: str, *, provenance: str | None = None,
         human_validated: bool | None = None, title: str = '', scope=None) -> dict:
    meta: dict = {'title': title}
    if provenance is not None:
        meta['provenance'] = provenance
        if human_validated is not None:
            meta['provenance_metadata'] = {'human_validated': human_validated}
    if scope is not None:
        meta['client_scope'] = scope
    return {'id': thought_id, 'metadata': meta, 'body': f'body of {thought_id}'}


# ── provenance_of ─────────────────────────────────────────────────────────────

def test_provenance_of_defaults_to_human():
    assert provenance_of(None) == 'human'
    assert provenance_of({}) == 'human'
    assert provenance_of({'provenance': ''}) == 'human'
    assert provenance_of({'provenance': '   '}) == 'human'


def test_provenance_of_passthrough_lowercased():
    assert provenance_of({'provenance': 'AI_Extracted'}) == 'ai_extracted'
    assert provenance_of({'provenance': 'ai_assisted'}) == 'ai_assisted'


def test_ai_authored_validated_promotes_tier():
    assert provenance_of({'provenance': 'ai_authored'}) == 'ai_authored'
    assert provenance_of({
        'provenance': 'ai_authored',
        'provenance_metadata': {'human_validated': True},
    }) == 'ai_authored_validated'
    # tolerate string 'true' (yaml frontmatter quirks)
    assert provenance_of({
        'provenance': 'ai_authored',
        'provenance_metadata': {'human_validated': 'true'},
    }) == 'ai_authored_validated'
    # not validated → stays ai_authored
    assert provenance_of({
        'provenance': 'ai_authored',
        'provenance_metadata': {'human_validated': False},
    }) == 'ai_authored'


def test_provenance_weight_ordering():
    w = PROVENANCE_WEIGHT
    assert w['human'] == 1.0 == w['ai_assisted']
    assert w['ai_authored_validated'] < w['human']
    assert w['ai_extracted'] < w['human']
    assert w['ai_authored'] < w['ai_authored_validated']
    assert w['ai_answer'] <= w['ai_authored']
    # unknown label → neutral 1.0
    assert provenance_weight({'provenance': 'something_new'}) == 1.0


# ── rrf_fuse ranking ──────────────────────────────────────────────────────────

def test_human_outranks_unvalidated_ai_at_same_vector_rank():
    # AI doc at vector rank 1, human doc at vector rank 2.
    # base(ai) = 1/(60+1)*0.70 ≈ 0.01148 ; base(human) = 1/(60+2)*1.0 ≈ 0.01613
    vh = [
        _hit('aaaaaaaa-0000-0000-0000-000000000001', provenance='ai_authored', title='AI'),
        _hit('bbbbbbbb-0000-0000-0000-000000000002', provenance='human', title='Human'),
    ]
    fused = rrf_fuse(vh, {})
    assert fused[0]['id'] == 'bbbbbbbb-0000-0000-0000-000000000002'
    assert fused[0]['provenance'] == 'human'
    assert fused[1]['provenance'] == 'ai_authored'


def test_validated_ai_outranks_unvalidated_ai_at_same_vector_rank():
    vh = [
        _hit('cccccccc-0000-0000-0000-000000000003', provenance='ai_authored', title='unvalidated'),
        _hit('dddddddd-0000-0000-0000-000000000004', provenance='ai_authored',
             human_validated=True, title='validated'),
    ]
    fused = rrf_fuse(vh, {})
    # validated is at vector rank 2 but weight 0.96 vs 0.70 → 1/62*0.96 ≈ 0.01548
    # > 1/61*0.70 ≈ 0.01148
    assert fused[0]['id'] == 'dddddddd-0000-0000-0000-000000000004'
    assert fused[0]['provenance'] == 'ai_authored_validated'


def test_relevance_still_dominates_large_rank_gap():
    # Human doc buried at vector rank 10, strong AI doc at rank 1.
    # base(ai)=1/61*0.70≈0.01148 ; base(human)=1/70*1.0≈0.01429 — human still wins
    # at rank 10, but a doc at rank 30 would lose: assert that boundary.
    vh = [_hit('aaaaaaaa-0000-0000-0000-00000000aaaa', provenance='ai_authored')] \
        + [_hit(f'0000000{i}-0000-0000-0000-00000000000{i}', provenance='human') for i in range(2, 9)] \
        + [_hit('ffffffff-0000-0000-0000-00000000ffff', provenance='human')]  # rank 9
    fused = rrf_fuse(vh, {})
    # AI at rank1 weighted 0.01148; human at rank9 weighted 1/69 ≈ 0.01449 → human top
    assert fused[0]['provenance'] == 'human'
    # but a *very* deep human doc would not flip the strong AI doc — sanity:
    # AI rank1 vs human rank 50 (fillers also ai_authored so they can't take top spot).
    vh2 = [_hit('aaaaaaaa-1111-1111-1111-111111111111', provenance='ai_authored')] \
        + [_hit(f'{i:08x}-1111-1111-1111-111111111111', provenance='ai_authored') for i in range(2, 50)] \
        + [_hit('ffffffff-1111-1111-1111-111111111111', provenance='human')]  # rank 50
    fused2 = rrf_fuse(vh2, {})
    # base(ai@1)=1/61*0.70≈0.01148 ; base(human@50)=1/110≈0.00909 → strong AI on top
    assert fused2[0]['id'] == 'aaaaaaaa-1111-1111-1111-111111111111'


def test_fused_dicts_expose_provenance_fields():
    vh = [_hit('aaaaaaaa-2222-2222-2222-222222222222', provenance='ai_extracted')]
    [row] = rrf_fuse(vh, {})
    assert row['provenance'] == 'ai_extracted'
    assert row['provenance_weight'] == PROVENANCE_WEIGHT['ai_extracted']
    assert 'rrf_score' in row and 'rrf_score_raw' in row
    assert row['rrf_score'] == row['rrf_score_raw'] * row['provenance_weight']


# ── client_scope ──────────────────────────────────────────────────────────────

def test_client_scope_of_defaults_internal():
    assert _client_scope_of(None) == ['internal']
    assert _client_scope_of({}) == ['internal']
    assert _client_scope_of({'client_scope': []}) == ['internal']


def test_client_scope_of_normalizes():
    assert _client_scope_of({'client_scope': 'ACME'}) == ['acme']
    assert _client_scope_of({'client_scope': ['ACME', ' BetaBank ']}) == ['acme', 'betabank']


def test_nested_frontmatter_fallback():
    # Some ingest paths nest the raw parsed frontmatter under `frontmatter`.
    meta = {'frontmatter': {'provenance': 'ai_authored',
                            'provenance_metadata': {'human_validated': True},
                            'client_scope': ['acme']}}
    assert provenance_of(meta) == 'ai_authored_validated'
    assert _client_scope_of(meta) == ['acme']
    # top-level wins over nested
    meta2 = {'provenance': 'human', 'frontmatter': {'provenance': 'ai_authored'}}
    assert provenance_of(meta2) == 'human'
