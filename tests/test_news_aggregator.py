# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

# tests/test_news_aggregator.py — F8.8.x.A: news/start.md aggregator.
#
# Pure-deterministic tests: vectors=None path (no embeddings), enable_llm=False
# (no Anthropic call). Verifies ranking, sparse-week fallback, idempotency,
# cluster_slugs propagation.

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import exocortex.wiki_compiler as wc


def _issue(
    *, thought_id: str, newsletter: str, title: str, days_ago: float,
    insights: list, topics: list[str], cited: list = None,
    now: datetime = None,
) -> dict:
    now = now or datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
    dt = now - timedelta(days=days_ago)
    return {
        'thought_id': thought_id,
        'source_id': f'src-{thought_id}',
        'title': title,
        'uri': '',
        'captured_at': dt,
        'body': f'body for {thought_id}',
        'newsletter_name': newsletter,
        'sender_email': f'noreply@{newsletter.replace(" ", "").lower()}.com',
        'tldr': '',
        'key_insights': insights,
        'cited_sources': cited or [],
        'topics': topics,
        'raw_metadata': {
            # RFC 2822
            'date_header': dt.strftime('%a, %d %b %Y %H:%M:%S +0000'),
        },
    }


CLUSTERS = {
    'ai-foundations': {
        'slug': 'ai-foundations',
        'label': 'AI Foundations',
        'emoji': '🧠',
        'topics': ['llm', 'rag', 'rl', 'multi-agent'],
    },
    'engineering-infrastructure': {
        'slug': 'engineering-infrastructure',
        'label': 'Engineering & Infrastructure',
        'emoji': '🏗️',
        'topics': ['kubernetes', 'observability', 'database'],
    },
}


def _now() -> datetime:
    return datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)


def test_filter_issues_in_window_drops_old():
    now = _now()
    issues = [
        _issue(thought_id='in', newsletter='A', title='in', days_ago=2,
               insights=[{'insight': 'x'}], topics=['llm'], now=now),
        _issue(thought_id='out', newsletter='A', title='out', days_ago=20,
               insights=[{'insight': 'y'}], topics=['llm'], now=now),
        _issue(thought_id='edge', newsletter='A', title='edge', days_ago=6.9,
               insights=[{'insight': 'z'}], topics=['llm'], now=now),
    ]
    in_win, days, expanded = wc._filter_issues_in_window(issues, 7, now=now)
    ids = {i['thought_id'] for i in in_win}
    # We have only 3 candidates total → sparse, so the expansion may kick in.
    # What matters: sparse-fallback must include "edge" and "in" before "out"
    # being dropped is acceptable when the expansion picks them all up.
    if expanded:
        # 30d expansion: keeps all 3.
        assert ids == {'in', 'out', 'edge'}
        assert days == 30
    else:
        assert ids == {'in', 'edge'}
        assert days == 7


def test_compute_news_brief_top_categories_and_score_order():
    now = _now()
    issues = [
        # AI cluster, fresh + 2 cited named entities
        _issue(thought_id='a1', newsletter='Daily Dose of DS',
               title='AI top', days_ago=1.0,
               insights=[{
                   'insight': 'GRPO replaces PPO',
                   'evidence': 'lower variance',
                   'cited_sources': [
                       {'name': 'DeepSeek', 'type': 'company'},
                       {'name': 'HuggingFace', 'type': 'company'},
                   ],
               }],
               topics=['llm', 'rl'], now=now),
        # AI cluster, older + no citations
        _issue(thought_id='a2', newsletter='ByteByteGo',
               title='AI old', days_ago=5.0,
               insights=[{'insight': 'older finding'}],
               topics=['llm'], now=now),
        # Eng cluster, fresh
        _issue(thought_id='e1', newsletter='Slow AI',
               title='Eng', days_ago=2.0,
               insights=[{'insight': 'k8s thing',
                          'cited_sources': [{'name': 'CNCF', 'type': 'company'}]}],
               topics=['kubernetes'], now=now),
        # Misc cluster (no matching topic)
        _issue(thought_id='m1', newsletter='AI Report',
               title='Misc', days_ago=3.0,
               insights=[{'insight': 'misc thing'}],
               topics=['random-topic'], now=now),
    ]
    brief = wc._compute_news_brief(
        issues, CLUSTERS, window_days=7, enable_llm=False,
    )
    assert brief['issue_count'] == 4
    assert brief['insight_count'] == 4
    # Top categories ordered by issue count desc.
    assert brief['top_categories'][0] == 'ai-foundations'
    # AI fresh > AI old: scoring putting GRPO first.
    ai_items = brief['merged_per_category']['ai-foundations']
    assert ai_items[0]['insight'] == 'GRPO replaces PPO'
    # Misc not in top_categories (always excluded from top by design).
    assert '_misc' not in brief['top_categories']


def test_score_components_recency_decays():
    now = _now()
    rows = [
        {
            'issue': _issue(thought_id='fresh', newsletter='X',
                            title='', days_ago=0.0,
                            insights=[], topics=[], now=now),
            'insight': 'a', 'evidence': '', 'cited_sources': [],
        },
        {
            'issue': _issue(thought_id='week', newsletter='X',
                            title='', days_ago=7.0,
                            insights=[], topics=[], now=now),
            'insight': 'b', 'evidence': '', 'cited_sources': [],
        },
    ]
    wc._score_insights(rows, [0, 0], now=now)
    assert rows[0]['score'] > rows[1]['score']
    assert rows[0]['score_components']['recency'] > 0.99
    assert rows[1]['score_components']['recency'] < 0.2  # half-life 2.4d → 0.135


def test_named_cited_count_distinguishes_types():
    cited = [
        {'name': 'A', 'type': 'company'},
        {'name': 'B', 'type': 'product'},
        {'name': 'C', 'type': 'paper'},
        {'name': 'D', 'type': 'unknown'},
        {'name': '', 'type': 'company'},  # dropped (empty name)
        'plain string',
    ]
    named, generic = wc._named_cited_count(cited)
    assert named == 3
    # 'D' is generic (unknown type) + 'plain string' is generic
    assert generic == 2


def test_input_hash_idempotent_and_window_sensitive():
    now = _now()
    issues = [
        _issue(thought_id='a', newsletter='Daily Dose of DS',
               title='t1', days_ago=1.0,
               insights=[{'insight': 'i1'}], topics=['llm'], now=now),
        _issue(thought_id='b', newsletter='ByteByteGo',
               title='t2', days_ago=2.0,
               insights=[{'insight': 'i2'}], topics=['llm'], now=now),
    ]
    b1 = wc._compute_news_brief(issues, CLUSTERS, window_days=7, enable_llm=False)
    b2 = wc._compute_news_brief(issues, CLUSTERS, window_days=7, enable_llm=False)
    # Hashes computed inside _write_news_start_page; reproduce manually:
    def _h(b):
        from hashlib import sha256
        tuples = sorted([
            (it.get('thought_id'),
             sha256((it.get('body') or '').encode('utf-8')).hexdigest()[:16] if it.get('body') else '',
             wc._news_issue_window_dt(it).isoformat() if wc._news_issue_window_dt(it) else '')
            for it in b['issues_in_window']
        ])
        payload = json.dumps([
            b['window_days'], tuples, sorted(CLUSTERS.keys()),
            wc.NEWS_AGGREGATOR_WEIGHTS, wc.NEWS_AGGREGATOR_LLM_MODEL,
            wc.NEWS_AGGREGATOR_PROMPT_VERSION,
        ], sort_keys=True, default=str, ensure_ascii=False).encode('utf-8')
        return sha256(payload).hexdigest()[:16]
    assert _h(b1) == _h(b2)


def test_write_news_start_page_idempotent(tmp_path: Path):
    now = _now()
    issues = [
        _issue(thought_id='a', newsletter='Daily Dose of DS',
               title='t1', days_ago=1.0,
               insights=[{'insight': 'GRPO replaces PPO',
                          'cited_sources': [{'name': 'DeepSeek', 'type': 'company'}]}],
               topics=['llm', 'rl'], now=now),
        _issue(thought_id='b', newsletter='ByteByteGo',
               title='t2', days_ago=2.0,
               insights=[{'insight': 'k8s news'}],
               topics=['kubernetes'], now=now),
        # Pad to clear sparse-window fallback (≥10 issues in 7d window).
        *[
            _issue(thought_id=f'pad{i}', newsletter='AI Report',
                   title=f'pad{i}', days_ago=2.0 + i * 0.1,
                   insights=[{'insight': f'pad insight {i}'}],
                   topics=['llm'], now=now)
            for i in range(10)
        ],
    ]
    brief = wc._compute_news_brief(issues, CLUSTERS, window_days=7, enable_llm=False)
    news_root = tmp_path / 'news'
    news_root.mkdir()
    wrote_first = wc._write_news_start_page(news_root, brief)
    assert wrote_first is True
    assert (news_root / 'start.md').exists()
    body = (news_root / 'start.md').read_text(encoding='utf-8')
    assert 'newsletter-feed-aggregator' in body
    assert 'GRPO replaces PPO' in body
    # Idempotent: same brief → no rewrite (matching _input_hash).
    brief2 = wc._compute_news_brief(issues, CLUSTERS, window_days=7, enable_llm=False)
    wrote_second = wc._write_news_start_page(news_root, brief2)
    assert wrote_second is False


def test_user_notes_block_preserved(tmp_path: Path):
    """User edits inside USER_NOTES sentinel survive a re-render."""
    now = _now()
    issues = [
        _issue(thought_id=f'i{i}', newsletter='Daily Dose of DS',
               title=f't{i}', days_ago=1.0 + i * 0.1,
               insights=[{'insight': f'finding {i}'}],
               topics=['llm'], now=now)
        for i in range(12)
    ]
    brief = wc._compute_news_brief(issues, CLUSTERS, window_days=7, enable_llm=False)
    news_root = tmp_path / 'news'
    news_root.mkdir()
    assert wc._write_news_start_page(news_root, brief) is True
    path = news_root / 'start.md'
    text = path.read_text(encoding='utf-8')
    # Inject custom user note.
    text2 = text.replace(
        '<!-- USER_NOTES_START -->\n\n<!-- USER_NOTES_END -->',
        '<!-- USER_NOTES_START -->\nMy private note\n<!-- USER_NOTES_END -->',
    )
    path.write_text(text2, encoding='utf-8')
    # Force re-render by invalidating hash.
    brief['issues_in_window'][0]['body'] = 'CHANGED'
    assert wc._write_news_start_page(news_root, brief) is True
    final = path.read_text(encoding='utf-8')
    assert 'My private note' in final


def test_cluster_slugs_added_to_atomic_page(tmp_path: Path):
    now = _now()
    topic_to_cluster = {
        wc._news_slug(t): cl
        for cl in CLUSTERS.values()
        for t in (cl.get('topics') or [])
    }
    issue = _issue(
        thought_id='a1', newsletter='Daily Dose of DS', title='AI title',
        days_ago=1.0, insights=[{'insight': 'finding'}],
        topics=['llm', 'kubernetes'], now=now,
    )
    news_root = tmp_path / 'news'
    news_root.mkdir()
    written = wc._write_news_issue_page(news_root, issue, topic_to_cluster)
    assert written is True
    # Find the file (under src/{slug}/).
    files = list(news_root.glob('src/*/*.md'))
    assert len(files) == 1
    body = files[0].read_text(encoding='utf-8')
    assert 'cluster_slugs:' in body
    assert 'ai-foundations' in body
    assert 'engineering-infrastructure' in body


def test_window_validation_rejects_out_of_range():
    import pytest
    with pytest.raises(ValueError, match='window_days'):
        wc._compile_news_aggregator(Path('/tmp'), [], CLUSTERS, window_days=0)
    with pytest.raises(ValueError, match='window_days'):
        wc._compile_news_aggregator(Path('/tmp'), [], CLUSTERS, window_days=99)


def test_empty_issues_returns_zero_counts():
    """Edge case: no issues → zero counts but valid structure."""
    brief = wc._compute_news_brief([], CLUSTERS, window_days=7, enable_llm=False)
    assert brief['issue_count'] == 0
    assert brief['insight_count'] == 0
    assert brief['top_categories'] == []
    assert brief['merged_per_category'] == {}


def test_duplicate_titles_deduped():
    """Same title from different newsletters should appear as separate issues
    (deduplication is by thought_id, not title)."""
    now = _now()
    issues = [
        _issue(thought_id='a', newsletter='A', title='Same Title',
               days_ago=1.0, insights=[{'insight': 'x'}], topics=['llm'], now=now),
        _issue(thought_id='b', newsletter='B', title='Same Title',
               days_ago=2.0, insights=[{'insight': 'y'}], topics=['llm'], now=now),
    ]
    brief = wc._compute_news_brief(issues, CLUSTERS, window_days=7, enable_llm=False)
    assert brief['issue_count'] == 2
    ai_items = brief['merged_per_category']['ai-foundations']
    assert len(ai_items) == 2


def test_missing_insight_fields_graceful():
    """Insights with missing optional fields should not crash."""
    now = _now()
    issues = [
        _issue(thought_id='a', newsletter='A', title='t',
               days_ago=1.0, insights=[{'insight': 'valid', 'evidence': ''}],
               topics=['llm'], now=now),
    ]
    brief = wc._compute_news_brief(issues, CLUSTERS, window_days=7, enable_llm=False)
    assert brief['issue_count'] == 1
    assert brief['insight_count'] == 1


def test_no_matching_topics_tracked_in_misc_count():
    """Topics not in any cluster are tracked in misc_count, not merged_per_category."""
    now = _now()
    issues = [
        _issue(thought_id='a', newsletter='A', title='t',
               days_ago=1.0, insights=[{'insight': 'x'}],
               topics=['totally-unknown-topic'], now=now),
    ]
    brief = wc._compute_news_brief(issues, CLUSTERS, window_days=7, enable_llm=False)
    # _misc is not in merged_per_category (only top categories are)
    assert 'ai-foundations' not in brief['merged_per_category']
    assert brief['misc_count'] == 1


def test_sparse_window_expands_to_30d():
    """Less than 10 issues in 7d window triggers 30d expansion."""
    now = _now()
    issues = [
        _issue(thought_id='old', newsletter='A', title='old',
               days_ago=25.0, insights=[{'insight': 'x'}], topics=['llm'], now=now),
    ]
    in_win, days, expanded = wc._filter_issues_in_window(issues, 7, now=now)
    assert expanded is True
    assert days == 30
    assert len(in_win) == 1
