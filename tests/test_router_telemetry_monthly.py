# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Tests for workers/router_telemetry_monthly.py — F-router-O.1 atomic DoD."""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, asdict
from datetime import date

import pytest

from exocortex.router_telemetry_monthly import (
    ANOMALY_CLASSES,
    Anomaly,
    MonthlyMetrics,
    UseCaseMetrics,
    build_anomaly_list,
    compute_delta,
    detect_anomalies,
    parse_period,
    to_json_artifact,
)

# ─────────────────────────── Helpers ───────────────────────────

def _uc(
    use_case: str = 'second_brain.F4_synthesis_client',
    *,
    n: int = 100,
    avg_cost: float = 0.005,
    p95: int = 4000,
    fail: float = 0.05,
    providers: dict[str, int] | None = None,
) -> UseCaseMetrics:
    return UseCaseMetrics(
        use_case=use_case,
        n_calls=n,
        avg_cost_usd=avg_cost,
        total_cost_usd=avg_cost * n,
        p50_latency_ms=int(p95 * 0.6),
        p95_latency_ms=p95,
        fail_rate=fail,
        fallback_event_count=int(n * fail),
        cache_hit_rate=None,
        provider_distribution=providers or {'deepinfra:Qwen/Qwen3.5-397B-A17B': n},
    )


def _mm(by: dict[str, UseCaseMetrics], *, start: str = '2026-04-01', end: str = '2026-05-01') -> MonthlyMetrics:
    total_cost = sum(m.total_cost_usd for m in by.values())
    total_calls = sum(m.n_calls for m in by.values())
    return MonthlyMetrics(
        period_start=date.fromisoformat(start),
        period_end=date.fromisoformat(end),
        by_use_case=by,
        total_cost_usd=total_cost,
        total_call_count=total_calls,
    )


# ─────────────────────────── Dataclass invariants (O.1.1) ───────────────────────────

def test_use_case_metrics_is_frozen():
    m = _uc()
    with pytest.raises(FrozenInstanceError):
        m.n_calls = 999  # type: ignore[misc]


def test_monthly_metrics_json_serializable():
    metrics = _mm({'F4': _uc()})
    serialized = json.dumps({uc: asdict(v) for uc, v in metrics.by_use_case.items()})
    assert 'F4' in serialized


def test_top_provider_picks_max():
    m = _uc(providers={'a:m1': 10, 'b:m2': 30, 'c:m3': 20})
    assert m.top_provider() == 'b:m2'


def test_anomaly_classes_closed_set():
    expected = {
        'cost_spike', 'cost_drop', 'latency_degradation', 'fail_rate_growth',
        'fallback_burnout', 'volume_change', 'new_use_case', 'disappeared',
        'quality_drop',
    }
    assert set(ANOMALY_CLASSES) == expected


# ─────────────────────────── Delta (O.1.3 — non-anomaly path) ───────────────────────────

def test_delta_no_change_no_anomaly():
    cur = _mm({'F4': _uc(n=100, avg_cost=0.005, fail=0.05)})
    prev = _mm({'F4': _uc(n=100, avg_cost=0.005, fail=0.05)},
               start='2026-03-01', end='2026-04-01')
    delta = compute_delta(cur, prev)
    anomalies = detect_anomalies(delta)
    # only volume_change is sensitive to identical numbers — must not fire
    assert all(a.anomaly_class != 'cost_spike' for a in anomalies)
    assert all(a.anomaly_class != 'fail_rate_growth' for a in anomalies)


def test_delta_pct_safe_with_zero_prev():
    cur = _uc(avg_cost=0.005)
    prev = _uc(avg_cost=0.0)
    cur_m = _mm({'F4': cur})
    prev_m = _mm({'F4': prev}, start='2026-03-01', end='2026-04-01')
    delta = compute_delta(cur_m, prev_m)
    assert delta.per_use_case_delta['F4'].cost_pct is None


# ─────────────────────────── Anomaly classes (O.1.3 DoD specs) ───────────────────────────

def test_cost_spike_medium_severity():
    """prev avg=$0.001, cur avg=$0.0017 → cost_pct=0.7 (>0.30, <1.0) + total>$0.10 → medium."""
    cur = _uc(n=100, avg_cost=0.0017)   # total = 0.17
    prev = _uc(n=100, avg_cost=0.001)
    delta = compute_delta(_mm({'F4': cur}), _mm({'F4': prev}, start='2026-03-01', end='2026-04-01'))
    anomalies = detect_anomalies(delta)
    cost_spikes = [a for a in anomalies if a.anomaly_class == 'cost_spike']
    assert len(cost_spikes) == 1
    assert cost_spikes[0].severity == 'medium'


def test_cost_spike_high_severity_above_100pct():
    cur = _uc(n=100, avg_cost=0.003)    # total = 0.30
    prev = _uc(n=100, avg_cost=0.001)
    delta = compute_delta(_mm({'F4': cur}), _mm({'F4': prev}, start='2026-03-01', end='2026-04-01'))
    cost_spikes = [a for a in detect_anomalies(delta) if a.anomaly_class == 'cost_spike']
    assert len(cost_spikes) == 1
    assert cost_spikes[0].severity == 'high'


def test_cost_drop_info_severity():
    cur = _uc(n=100, avg_cost=0.0005)    # total = 0.05
    prev = _uc(n=100, avg_cost=0.002)    # total = 0.20 (>0.10 floor)
    delta = compute_delta(_mm({'F4': cur}), _mm({'F4': prev}, start='2026-03-01', end='2026-04-01'))
    anomalies = detect_anomalies(delta)
    drops = [a for a in anomalies if a.anomaly_class == 'cost_drop']
    assert len(drops) == 1 and drops[0].severity == 'info'


def test_fallback_burnout_high_severity():
    cur = _uc(fail=0.25)
    prev = _uc(fail=0.05)
    delta = compute_delta(_mm({'F4': cur}), _mm({'F4': prev}, start='2026-03-01', end='2026-04-01'))
    burnout = [a for a in detect_anomalies(delta) if a.anomaly_class == 'fallback_burnout']
    assert len(burnout) == 1 and burnout[0].severity == 'high'


def test_latency_degradation():
    cur = _uc(p95=12000)
    prev = _uc(p95=4000)
    delta = compute_delta(_mm({'F4': cur}), _mm({'F4': prev}, start='2026-03-01', end='2026-04-01'))
    items = [a for a in detect_anomalies(delta) if a.anomaly_class == 'latency_degradation']
    assert len(items) == 1 and items[0].severity == 'medium'


def test_new_use_case():
    cur = _mm({'F-new': _uc(use_case='F-new', n=15)})
    prev = _mm({}, start='2026-03-01', end='2026-04-01')
    delta = compute_delta(cur, prev)
    items = [a for a in detect_anomalies(delta) if a.anomaly_class == 'new_use_case']
    assert len(items) == 1 and items[0].severity == 'info'


def test_disappeared_use_case():
    cur = _mm({})
    prev = _mm({'F-old': _uc(use_case='F-old', n=50)},
               start='2026-03-01', end='2026-04-01')
    delta = compute_delta(cur, prev)
    items = [a for a in detect_anomalies(delta) if a.anomaly_class == 'disappeared']
    assert len(items) == 1 and items[0].severity == 'medium'


def test_disappeared_under_floor_no_emit():
    """prev had only 5 calls → is_disappeared=False → no emission."""
    cur = _mm({})
    prev = _mm({'F-old': _uc(use_case='F-old', n=5)},
               start='2026-03-01', end='2026-04-01')
    delta = compute_delta(cur, prev)
    items = [a for a in detect_anomalies(delta) if a.anomaly_class == 'disappeared']
    assert items == []


def test_volume_change_info():
    cur = _uc(n=200)
    prev = _uc(n=50)
    delta = compute_delta(_mm({'F4': cur}), _mm({'F4': prev}, start='2026-03-01', end='2026-04-01'))
    items = [a for a in detect_anomalies(delta) if a.anomaly_class == 'volume_change']
    assert len(items) == 1 and items[0].severity == 'info'


def test_multi_class_concurrency_same_use_case():
    """cost_spike + fail_rate_growth concurrently → 2 separate Anomaly entries."""
    cur = _uc(n=100, avg_cost=0.003, fail=0.10)     # total=0.30
    prev = _uc(n=100, avg_cost=0.001, fail=0.01)
    delta = compute_delta(_mm({'F4': cur}), _mm({'F4': prev}, start='2026-03-01', end='2026-04-01'))
    classes = {a.anomaly_class for a in detect_anomalies(delta)}
    assert 'cost_spike' in classes
    assert 'fail_rate_growth' in classes


def test_low_volume_cost_jitter_does_not_fire():
    """+30% cost on a $0.05/mc use_case → below total floor, no spike."""
    cur = _uc(n=10, avg_cost=0.005)     # total=0.05 — below $0.10 floor
    prev = _uc(n=10, avg_cost=0.003)
    delta = compute_delta(_mm({'F4': cur}), _mm({'F4': prev}, start='2026-03-01', end='2026-04-01'))
    spikes = [a for a in detect_anomalies(delta) if a.anomaly_class == 'cost_spike']
    assert spikes == []


def test_emit_assertion_guards_closed_set():
    """Internal _emit asserts anomaly_class membership — closed-set guard."""
    from exocortex.router_telemetry_monthly import _emit
    items: list[Anomaly] = []
    with pytest.raises(AssertionError):
        _emit(items, use_case='F4', cls='not_a_real_class', severity='info',
              evidence={}, cur=None)


# ─────────────────────────── Sorting + AnomalyList ───────────────────────────

def test_anomalies_sorted_severity_then_cost():
    cur = _mm({
        'F-low': _uc(use_case='F-low', n=100, avg_cost=0.0005, fail=0.25),  # burnout high, low cost
        'F-high': _uc(use_case='F-high', n=200, avg_cost=0.002, fail=0.25), # burnout high, higher cost
        'F-info': _uc(use_case='F-info', n=200, fail=0.05),
    })
    prev = _mm({
        'F-low': _uc(use_case='F-low', n=50, avg_cost=0.0005, fail=0.05),
        'F-high': _uc(use_case='F-high', n=80, avg_cost=0.0005, fail=0.05),
        'F-info': _uc(use_case='F-info', n=200, fail=0.05),
    }, start='2026-03-01', end='2026-04-01')
    delta = compute_delta(cur, prev)
    items = detect_anomalies(delta)
    severities = [a.severity for a in items]
    sev_rank = {'high': 0, 'medium': 1, 'info': 2}
    assert severities == sorted(severities, key=lambda s: sev_rank[s])


def test_build_anomaly_list_summary():
    cur = _mm({'F4': _uc(use_case='F4', n=100, avg_cost=0.002, fail=0.25)})
    prev = _mm({'F4': _uc(use_case='F4', avg_cost=0.001, fail=0.05)},
               start='2026-03-01', end='2026-04-01')
    delta = compute_delta(cur, prev)
    items = detect_anomalies(delta)
    al = build_anomaly_list('2026-04', delta, items)
    assert al.use_cases_observed == 1
    assert al.use_cases_anomalous == 1
    assert al.period == '2026-04'
    assert al.total_call_count == 100


# ─────────────────────────── Period parsing ───────────────────────────

def test_parse_period_explicit():
    cs, ce, ps, pe, label = parse_period('2026-04')
    assert label == '2026-04'
    assert cs.year == 2026 and cs.month == 4 and cs.day == 1
    assert ce.year == 2026 and ce.month == 5 and ce.day == 1
    assert ps.year == 2026 and ps.month == 3 and ps.day == 1
    assert pe == cs


def test_parse_period_january_wraparound():
    _cs, ce, ps, _pe, label = parse_period('2026-01')
    assert label == '2026-01'
    assert ps.year == 2025 and ps.month == 12
    assert ce.year == 2026 and ce.month == 2


def test_parse_period_invalid_raises():
    with pytest.raises(SystemExit):
        parse_period('not-a-period')


# ─────────────────────────── JSON artifact ───────────────────────────

def test_to_json_artifact_v1_schema():
    cur = _mm({'F4': _uc(use_case='F4', n=200, avg_cost=0.005, fail=0.25)})
    prev = _mm({'F4': _uc(use_case='F4', avg_cost=0.001, fail=0.05)},
               start='2026-03-01', end='2026-04-01')
    delta = compute_delta(cur, prev)
    anomalies = detect_anomalies(delta)
    art = to_json_artifact('2026-04', delta, anomalies)

    # JSON-roundtrips clean
    s = json.dumps(art, ensure_ascii=False)
    restored = json.loads(s)

    assert restored['schema_version'] == 'v1'
    assert restored['period'] == '2026-04'
    assert 'current_window' in restored and 'previous_window' in restored
    assert 'anomalies' in restored and len(restored['anomalies']) >= 1
    assert restored['summary']['use_cases_observed'] == 1
    assert restored['summary']['anomalies_count'] == len(restored['anomalies'])


# ─────────────────────────── Narrative + render (O.2 + O.3) ───────────────────────────

def test_anti_table_validation_rejects_table_in_tldr():
    from exocortex.router_telemetry_monthly import _validate_output
    bad = {'tldr': '| col | val |\n|---|---|\n| a | 1 |',
           'anomaly_narratives': [], 'action_items': []}
    ok, reason = _validate_output(bad)
    assert not ok and 'tldr' in reason


def test_anti_table_validation_rejects_bullet_top():
    from exocortex.router_telemetry_monthly import _validate_output
    bad = {'tldr': '* item one\n* item two', 'anomaly_narratives': [], 'action_items': []}
    ok, _reason = _validate_output(bad)
    assert not ok


def test_anti_table_validation_passes_prose():
    from exocortex.router_telemetry_monthly import _validate_output
    good = {'tldr': 'Stabilny miesiąc, 14 use cases, $0.72 spend. Brak anomalii. Brak akcji.',
            'anomaly_narratives': [], 'action_items': []}
    ok, _ = _validate_output(good)
    assert ok


def test_anti_table_validation_rejects_table_in_narrative():
    from exocortex.router_telemetry_monthly import _validate_output
    bad = {
        'tldr': 'Sensible prose two zdania. Trzeci.',
        'anomaly_narratives': [{'use_case': 'F4', 'narrative': '|x|y|\n|-|-|\n|1|2|'}],
        'action_items': [],
    }
    ok, _ = _validate_output(bad)
    assert not ok


def test_templated_fallback_no_anomalies():
    from exocortex.router_telemetry_monthly import _templated_fallback_narrative
    cur = _mm({'F4': _uc()})
    delta = compute_delta(cur, None)
    out = _templated_fallback_narrative('2026-05', delta, [])
    assert 'Stabilny miesiąc' in out.tldr
    assert out.degraded is True
    assert out.anomaly_narratives == []
    assert out.action_items == []


def test_templated_fallback_with_anomalies():
    from exocortex.router_telemetry_monthly import _templated_fallback_narrative
    cur = _mm({'F4': _uc(use_case='F4', n=100, avg_cost=0.005, fail=0.25)})
    delta = compute_delta(cur, None)
    anomalies = detect_anomalies(delta)
    out = _templated_fallback_narrative('2026-05', delta, anomalies)
    assert out.degraded is True
    assert len(out.anomaly_narratives) == len(anomalies)


def test_render_report_section_order():
    """## TL;DR before ## Anomalie before ## Action items before ## Tabele before ## Meta."""
    from exocortex.router_telemetry_monthly import (
        AnomalyNarrative,
        NarrativeOutput,
        render_report,
    )
    cur = _mm({'F4': _uc(use_case='F4', n=100, avg_cost=0.002, fail=0.25)})
    prev = _mm({'F4': _uc(use_case='F4', avg_cost=0.001, fail=0.05)},
               start='2026-03-01', end='2026-04-01')
    delta = compute_delta(cur, prev)
    anomalies = detect_anomalies(delta)
    narrative = NarrativeOutput(
        tldr='Wzrost kosztów F4 o 100%. Flip primary do anthropic.',
        anomaly_narratives=[AnomalyNarrative(use_case='F4', narrative='Koszt +100%. Action: flip primary.')],
        action_items=[],
    )
    md = render_report(narrative, delta, anomalies, '2026-04')
    pos_tldr = md.index('## TL;DR')
    pos_anom = md.index('## Anomalie')
    pos_act = md.index('## Action items')
    pos_tab = md.index('## Tabele (drill-down)')
    pos_meta = md.index('## Meta')
    assert pos_tldr < pos_anom < pos_act < pos_tab < pos_meta


def test_render_report_first_table_appears_after_tabele_heading():
    """CRITICAL DoD invariant: first markdown table line is AFTER `## Tabele` heading."""
    from exocortex.router_telemetry_monthly import NarrativeOutput, render_report
    cur = _mm({'F4': _uc(use_case='F4', n=100, fail=0.25)})
    delta = compute_delta(cur, None)
    anomalies = detect_anomalies(delta)
    narrative = NarrativeOutput(
        tldr='Sensible prose. Drugie zdanie.',
        anomaly_narratives=[], action_items=[],
    )
    md = render_report(narrative, delta, anomalies, '2026-05')
    lines = md.splitlines()
    table_idx = next((i for i, ln in enumerate(lines) if ln.startswith('|')), None)
    tabele_idx = next((i for i, ln in enumerate(lines) if ln == '## Tabele (drill-down)'), None)
    assert table_idx is not None and tabele_idx is not None
    assert table_idx > tabele_idx, f'first table at line {table_idx}, ## Tabele at {tabele_idx}'


def test_render_report_frontmatter_keys():
    from exocortex.router_telemetry_monthly import NarrativeOutput, render_report
    cur = _mm({'F4': _uc(use_case='F4', n=100, fail=0.25)})
    delta = compute_delta(cur, None)
    anomalies = detect_anomalies(delta)
    narrative = NarrativeOutput(tldr='OK prose. Drugie zdanie.', anomaly_narratives=[],
                                action_items=[], cost_usd=0.0087,
                                provider='anthropic', model='claude-haiku-4-5-20251001')
    md = render_report(narrative, delta, anomalies, '2026-05',
                       artifact_relpath='.router/monthly_metrics_2026-05.json')
    head = md.split('---', 2)[1]
    expected_keys = [
        'type:', 'period:', 'generated_at:', 'total_use_cases:', 'total_calls:',
        'total_cost_usd:', 'anomalies_count:', 'anomalies_high_severity:',
        'schema_version:', 'artifact:',
        'llm_summary_use_case:', 'llm_summary_provider:', 'llm_summary_model:',
        'llm_summary_cost_usd:', 'status_summary:',
    ]
    for k in expected_keys:
        assert k in head, f'missing frontmatter key: {k}'


def test_status_summary_enum_derivation():
    from exocortex.router_telemetry_monthly import _status_summary
    assert _status_summary(0, 0) == 'healthy'
    assert _status_summary(1, 1) == 'investigation'
    assert _status_summary(3, 0) == 'needs_action'


def test_render_report_empty_state_placeholders():
    from exocortex.router_telemetry_monthly import NarrativeOutput, render_report
    cur = _mm({'F4': _uc()})
    delta = compute_delta(cur, None)
    narrative = NarrativeOutput(tldr='Brak anomalii ten miesiąc. Spokój.',
                                anomaly_narratives=[], action_items=[])
    md = render_report(narrative, delta, [], '2026-05')
    assert 'Brak anomalii w tym miesiącu' in md
    assert 'Brak akcji do zaaplikowania' in md


def test_period_pl_polish_months():
    from exocortex.router_telemetry_monthly import _period_pl
    assert _period_pl('2026-04') == 'Kwiecień 2026'
    assert _period_pl('2026-12') == 'Grudzień 2026'


def test_write_to_vault_idempotent(tmp_path):
    from exocortex.router_telemetry_monthly import write_to_vault
    (tmp_path / 'wiki').mkdir()
    md = '---\ntype: x\n---\n# test'
    p1 = write_to_vault(md, '2026-05', vault_path=tmp_path)
    p2 = write_to_vault(md, '2026-05', vault_path=tmp_path)  # identical → no-op
    assert p1 == p2
    assert p1.read_text() == md


def test_write_to_vault_refuses_overwrite_without_force(tmp_path):
    from exocortex.router_telemetry_monthly import write_to_vault
    (tmp_path / 'wiki').mkdir()
    write_to_vault('first', '2026-05', vault_path=tmp_path)
    with pytest.raises(FileExistsError):
        write_to_vault('second-different', '2026-05', vault_path=tmp_path)


def test_write_to_vault_force_overwrite_creates_backup(tmp_path):
    from exocortex.router_telemetry_monthly import write_to_vault
    (tmp_path / 'wiki').mkdir()
    write_to_vault('first content', '2026-05', vault_path=tmp_path)
    target = write_to_vault('second content', '2026-05', vault_path=tmp_path,
                            force_overwrite=True)
    assert target.read_text() == 'second content'
    backups = list((tmp_path / 'wiki').glob('*.bak'))
    assert len(backups) == 1


def test_write_to_vault_missing_wiki_dir(tmp_path):
    from exocortex.router_telemetry_monthly import write_to_vault
    with pytest.raises(FileNotFoundError):
        write_to_vault('x', '2026-05', vault_path=tmp_path)


def test_to_json_artifact_no_baseline():
    cur = _mm({'F4': _uc(use_case='F4', n=20)})
    delta = compute_delta(cur, None)
    anomalies = detect_anomalies(delta)
    art = to_json_artifact('2026-05', delta, anomalies)
    assert art['previous_window'] is None
    # First-month: only new_use_case anomalies
    assert all(a['anomaly_class'] == 'new_use_case' for a in art['anomalies'])
