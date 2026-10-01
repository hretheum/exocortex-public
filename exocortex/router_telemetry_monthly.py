# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Monthly router telemetry aggregator (R3 — Operator-driven routing).

Aggregates `ag_catalog.llm_provider_runs` into per-use_case metrics for the
just-completed month and the prior month, computes deltas, and classifies
anomalies via the deterministic 9-class taxonomy from
`docs/ARCHITECTURE.md` §16.5 (router repo).

Phase O.1 (this file): aggregate → delta → anomalies → JSON. The LLM
narrative + vault render layer (O.2 + O.3) consumes the JSON output.

CLI:
    python -m workers.router_telemetry_monthly --period 2026-04 --output json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─────────────────────────── Anomaly taxonomy ───────────────────────────
# Closed-set 9-class enum per architect §16.5. Downstream LLM tool schema
# relies on this set being stable; expansion only via design review.
ANOMALY_CLASSES: tuple[str, ...] = (
    'cost_spike',
    'cost_drop',
    'latency_degradation',
    'fail_rate_growth',
    'fallback_burnout',
    'volume_change',
    'new_use_case',
    'disappeared',
    'quality_drop',  # reserved — sec 16.11 Q2; not emitted in O.1
)

SEVERITIES: tuple[str, ...] = ('info', 'medium', 'high')

# Suggested-action templates — first-cut prose; LLM may rewrite in O.2.
_ACTION_TEMPLATES: dict[str, str] = {
    'cost_spike': 'Flip primary {use_case} to a cheaper provider, observe 30 days.',
    'cost_drop': 'Cost dropped — verify hypothesis (cache amortization / volume drop / provider price cut). No action.',
    'latency_degradation': 'Investigate {top_provider} latency; consider fallback chain reorder.',
    'fail_rate_growth': 'Provider {top_provider} unstable; flip primary to fallback[0].',
    'fallback_burnout': 'Primary {top_provider} unreliable — promote fallback[0] to primary.',
    'volume_change': 'Use case volume changed — verify pipeline still healthy.',
    'new_use_case': 'New use_case observed — confirm yaml entry exists or relies on `defaults:`.',
    'disappeared': 'Use case fired 0 times — was the consumer disabled?',
    'quality_drop': '(reserved — needs F-router-quality-signal)',
}


# ─────────────────────────── Dataclass model ───────────────────────────

@dataclass(frozen=True)
class UseCaseMetrics:
    """Per-use_case aggregation for one 30-day window."""
    use_case: str
    n_calls: int
    avg_cost_usd: float
    total_cost_usd: float
    p50_latency_ms: int
    p95_latency_ms: int
    fail_rate: float                          # 0.0-1.0; proxy via fallback_chain populated
    fallback_event_count: int
    cache_hit_rate: float | None              # None when no cache-eligible calls
    provider_distribution: dict[str, int]     # {'anthropic:claude-haiku-...': 142, ...}

    def top_provider(self) -> str:
        if not self.provider_distribution:
            return ''
        return max(self.provider_distribution.items(), key=lambda kv: kv[1])[0]


@dataclass(frozen=True)
class MonthlyMetrics:
    period_start: date
    period_end: date
    by_use_case: dict[str, UseCaseMetrics]
    total_cost_usd: float
    total_call_count: int


@dataclass(frozen=True)
class UseCaseDelta:
    use_case: str
    cost_pct: float | None              # (cur.avg - prev.avg) / prev.avg
    latency_p95_delta_ms: int | None    # cur.p95 - prev.p95 (absolute)
    fallback_delta_x: float | None      # cur.fallback_rate / max(prev.fallback_rate, 0.01)
    volume_delta_pct: float | None      # (cur.n - prev.n) / prev.n
    fail_rate_delta: float | None       # cur.fail_rate - prev.fail_rate (absolute)
    is_new: bool
    is_disappeared: bool


@dataclass(frozen=True)
class MonthlyDelta:
    current: MonthlyMetrics
    previous: MonthlyMetrics | None
    per_use_case_delta: dict[str, UseCaseDelta]


@dataclass(frozen=True)
class Anomaly:
    use_case: str
    anomaly_class: str          # closed-set per ANOMALY_CLASSES
    severity: str               # one of SEVERITIES
    evidence: dict[str, Any]    # raw numbers triggering the trigger
    suggested_action: str
    top_provider: str
    candidate_alt: str | None = None


@dataclass(frozen=True)
class AnomalyList:
    period: str
    items: list[Anomaly]
    total_cost_usd: float
    total_call_count: int
    use_cases_observed: int
    use_cases_anomalous: int


# ─────────────────────────── SQL aggregation ───────────────────────────

_AGG_SQL = """
SELECT
    use_case,
    count(*) AS n_calls,
    avg(cost_usd)::float8 AS avg_cost_usd,
    sum(cost_usd)::float8 AS total_cost_usd,
    percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms)::int AS p50_latency_ms,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms)::int AS p95_latency_ms,
    count(*) FILTER (WHERE cardinality(fallback_chain) > 0) AS fallback_event_count,
    (count(*) FILTER (WHERE cardinality(fallback_chain) > 0))::float8
        / NULLIF(count(*), 0) AS fail_rate,
    count(*) FILTER (WHERE cache_read_input_tokens > 0) AS cache_hit_count,
    count(*) FILTER (WHERE cache_read_input_tokens > 0
                     OR cache_creation_input_tokens > 0) AS cache_eligible_count
FROM ag_catalog.llm_provider_runs
WHERE started_at >= %s AND started_at < %s
GROUP BY use_case
ORDER BY total_cost_usd DESC
"""

_PROVIDER_DIST_SQL = """
SELECT
    use_case,
    provider || ':' || model AS provider_model,
    count(*) AS n
FROM ag_catalog.llm_provider_runs
WHERE started_at >= %s AND started_at < %s
GROUP BY use_case, provider, model
"""


def query_period_metrics(start: datetime, end: datetime) -> MonthlyMetrics:
    """Aggregate llm_provider_runs over [start, end). Returns MonthlyMetrics."""
    from exocortex.db import query  # local import — keeps module import-able without DB

    rows = query(_AGG_SQL, start, end)
    dist_rows = query(_PROVIDER_DIST_SQL, start, end)

    dist_by_uc: dict[str, dict[str, int]] = {}
    for r in dist_rows:
        dist_by_uc.setdefault(r['use_case'], {})[r['provider_model']] = int(r['n'])

    by_use_case: dict[str, UseCaseMetrics] = {}
    total_cost = 0.0
    total_calls = 0
    for r in rows:
        uc = r['use_case']
        n = int(r['n_calls'])
        cache_eligible = int(r['cache_eligible_count']) if r.get('cache_eligible_count') else 0
        cache_hit = int(r['cache_hit_count']) if r.get('cache_hit_count') else 0
        cache_hit_rate = (cache_hit / cache_eligible) if cache_eligible > 0 else None
        m = UseCaseMetrics(
            use_case=uc,
            n_calls=n,
            avg_cost_usd=float(r['avg_cost_usd'] or 0.0),
            total_cost_usd=float(r['total_cost_usd'] or 0.0),
            p50_latency_ms=int(r['p50_latency_ms'] or 0),
            p95_latency_ms=int(r['p95_latency_ms'] or 0),
            fail_rate=float(r['fail_rate'] or 0.0),
            fallback_event_count=int(r['fallback_event_count'] or 0),
            cache_hit_rate=cache_hit_rate,
            provider_distribution=dist_by_uc.get(uc, {}),
        )
        by_use_case[uc] = m
        total_cost += m.total_cost_usd
        total_calls += m.n_calls

    return MonthlyMetrics(
        period_start=start.date(),
        period_end=end.date(),
        by_use_case=by_use_case,
        total_cost_usd=total_cost,
        total_call_count=total_calls,
    )


# ─────────────────────────── Delta computation ───────────────────────────

def _safe_pct(cur: float, prev: float) -> float | None:
    if prev == 0:
        return None
    return (cur - prev) / prev


def compute_delta(
    current: MonthlyMetrics,
    previous: MonthlyMetrics | None,
) -> MonthlyDelta:
    """Per-use_case relative deltas. Handles new/disappeared use cases."""
    per_uc: dict[str, UseCaseDelta] = {}
    cur_keys = set(current.by_use_case.keys())
    prev_keys: set[str] = set(previous.by_use_case.keys()) if previous else set()
    all_keys = cur_keys | prev_keys

    for uc in all_keys:
        cur = current.by_use_case.get(uc)
        prev = previous.by_use_case.get(uc) if previous else None

        if cur is None and prev is not None:
            per_uc[uc] = UseCaseDelta(
                use_case=uc, cost_pct=None, latency_p95_delta_ms=None,
                fallback_delta_x=None, volume_delta_pct=None,
                fail_rate_delta=None, is_new=False,
                is_disappeared=prev.n_calls >= 10,
            )
            continue
        if prev is None and cur is not None:
            per_uc[uc] = UseCaseDelta(
                use_case=uc, cost_pct=None, latency_p95_delta_ms=None,
                fallback_delta_x=None, volume_delta_pct=None,
                fail_rate_delta=None, is_new=True, is_disappeared=False,
            )
            continue
        # both present
        assert cur is not None and prev is not None
        per_uc[uc] = UseCaseDelta(
            use_case=uc,
            cost_pct=_safe_pct(cur.avg_cost_usd, prev.avg_cost_usd),
            latency_p95_delta_ms=cur.p95_latency_ms - prev.p95_latency_ms,
            fallback_delta_x=cur.fail_rate / max(prev.fail_rate, 0.01),
            volume_delta_pct=_safe_pct(cur.n_calls, prev.n_calls),
            fail_rate_delta=cur.fail_rate - prev.fail_rate,
            is_new=False,
            is_disappeared=False,
        )

    return MonthlyDelta(current=current, previous=previous, per_use_case_delta=per_uc)


# ─────────────────────────── Anomaly detection ───────────────────────────

# Thresholds — module constants; tuning via PR not env vars (sec 16.5).
_TH_COST_PCT = 0.30                  # ±30%
_TH_COST_HIGH_PCT = 1.0              # >100% → severity high
_TH_COST_TOTAL_USD = 0.10            # $0.10 monthly minimum to matter
_TH_LATENCY_DELTA_MS = 5000          # +5s p95 absolute
_TH_LATENCY_FLOOR_MS = 5000          # only when current p95 already >5s
_TH_FALLBACK_DELTA_X = 5.0           # 5× growth in fallback rate
_TH_FALLBACK_FLOOR = 0.05            # fail_rate must exceed 5%
_TH_FALLBACK_BURNOUT = 0.20          # absolute >20%
_TH_VOLUME_PCT = 0.50                # ±50%
_TH_DISAPPEARED_FLOOR = 10           # prev had ≥10 calls


def _emit(
    items: list[Anomaly],
    *,
    use_case: str,
    cls: str,
    severity: str,
    evidence: dict[str, Any],
    cur: UseCaseMetrics | None,
) -> None:
    assert cls in ANOMALY_CLASSES, f'unknown anomaly_class {cls!r}'
    assert severity in SEVERITIES, f'unknown severity {severity!r}'
    top = cur.top_provider() if cur else ''
    template = _ACTION_TEMPLATES[cls]
    items.append(Anomaly(
        use_case=use_case,
        anomaly_class=cls,
        severity=severity,
        evidence=evidence,
        suggested_action=template.format(use_case=use_case, top_provider=top or 'unknown'),
        top_provider=top,
        candidate_alt=None,
    ))


def detect_anomalies(delta: MonthlyDelta) -> list[Anomaly]:
    """Apply 9-class taxonomy thresholds. Multi-class concurrency allowed."""
    items: list[Anomaly] = []
    current = delta.current
    previous = delta.previous

    for uc, d in delta.per_use_case_delta.items():
        cur = current.by_use_case.get(uc)
        prev = previous.by_use_case.get(uc) if previous else None

        # new_use_case — no prev baseline
        if d.is_new and cur is not None:
            _emit(items, use_case=uc, cls='new_use_case', severity='info',
                  evidence={'n_calls': cur.n_calls, 'total_cost_usd': cur.total_cost_usd},
                  cur=cur)
            continue  # other anomaly classes need a baseline

        # disappeared
        if d.is_disappeared and prev is not None:
            _emit(items, use_case=uc, cls='disappeared', severity='medium',
                  evidence={'prev_n_calls': prev.n_calls, 'prev_total_cost_usd': prev.total_cost_usd},
                  cur=prev)
            continue

        if cur is None or prev is None:
            continue

        # cost_spike / cost_drop
        if d.cost_pct is not None:
            if d.cost_pct > _TH_COST_PCT and cur.total_cost_usd > _TH_COST_TOTAL_USD:
                sev = 'high' if d.cost_pct > _TH_COST_HIGH_PCT else 'medium'
                _emit(items, use_case=uc, cls='cost_spike', severity=sev,
                      evidence={'cost_pct': d.cost_pct, 'total_cost_usd': cur.total_cost_usd,
                                'prev_total_cost_usd': prev.total_cost_usd},
                      cur=cur)
            elif d.cost_pct < -_TH_COST_PCT and prev.total_cost_usd > _TH_COST_TOTAL_USD:
                _emit(items, use_case=uc, cls='cost_drop', severity='info',
                      evidence={'cost_pct': d.cost_pct, 'total_cost_usd': cur.total_cost_usd,
                                'prev_total_cost_usd': prev.total_cost_usd},
                      cur=cur)

        # latency_degradation
        if (d.latency_p95_delta_ms is not None
                and d.latency_p95_delta_ms > _TH_LATENCY_DELTA_MS
                and cur.p95_latency_ms > _TH_LATENCY_FLOOR_MS):
            _emit(items, use_case=uc, cls='latency_degradation', severity='medium',
                  evidence={'latency_p95_delta_ms': d.latency_p95_delta_ms,
                            'p95_latency_ms': cur.p95_latency_ms},
                  cur=cur)

        # fail_rate_growth
        if (d.fallback_delta_x is not None
                and d.fallback_delta_x > _TH_FALLBACK_DELTA_X
                and cur.fail_rate > _TH_FALLBACK_FLOOR):
            _emit(items, use_case=uc, cls='fail_rate_growth', severity='high',
                  evidence={'fallback_delta_x': d.fallback_delta_x,
                            'fail_rate': cur.fail_rate, 'prev_fail_rate': prev.fail_rate},
                  cur=cur)

        # fallback_burnout — absolute trigger
        if cur.fail_rate > _TH_FALLBACK_BURNOUT:
            _emit(items, use_case=uc, cls='fallback_burnout', severity='high',
                  evidence={'fail_rate': cur.fail_rate,
                            'fallback_event_count': cur.fallback_event_count},
                  cur=cur)

        # volume_change
        if d.volume_delta_pct is not None and abs(d.volume_delta_pct) > _TH_VOLUME_PCT:
            _emit(items, use_case=uc, cls='volume_change', severity='info',
                  evidence={'volume_delta_pct': d.volume_delta_pct,
                            'n_calls': cur.n_calls, 'prev_n_calls': prev.n_calls},
                  cur=cur)

    # Sort: severity DESC, then total_cost DESC of the use_case
    sev_rank = {'high': 0, 'medium': 1, 'info': 2}
    def _key(a: Anomaly) -> tuple[int, float]:
        cur = current.by_use_case.get(a.use_case)
        cost = cur.total_cost_usd if cur else 0.0
        return (sev_rank.get(a.severity, 3), -cost)
    items.sort(key=_key)
    return items


def build_anomaly_list(period: str, delta: MonthlyDelta, anomalies: list[Anomaly]) -> AnomalyList:
    cur = delta.current
    return AnomalyList(
        period=period,
        items=anomalies,
        total_cost_usd=cur.total_cost_usd,
        total_call_count=cur.total_call_count,
        use_cases_observed=len(cur.by_use_case),
        use_cases_anomalous=len({a.use_case for a in anomalies}),
    )


# ─────────────────────────── Period parsing ───────────────────────────

def parse_period(period: str | None) -> tuple[datetime, datetime, datetime, datetime, str]:
    """Return (cur_start, cur_end, prev_start, prev_end, period_label).

    `period` is YYYY-MM (the month being reviewed). Defaults to the just-completed
    calendar month. Windows are calendar months in UTC (boundaries exclusive on `end`).
    """
    if period is None:
        today = datetime.now(timezone.utc).date()
        # previous calendar month: take 1st-of-current minus 1 day
        first_of_current = today.replace(day=1)
        last_of_prev = first_of_current.fromordinal(first_of_current.toordinal() - 1)
        period_year, period_month = last_of_prev.year, last_of_prev.month
    else:
        try:
            y, m = period.split('-')
            period_year, period_month = int(y), int(m)
        except (ValueError, AttributeError) as e:
            raise SystemExit(f'invalid --period {period!r} (expected YYYY-MM): {e}')

    cur_start = datetime(period_year, period_month, 1, tzinfo=timezone.utc)
    if period_month == 12:
        cur_end = datetime(period_year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        cur_end = datetime(period_year, period_month + 1, 1, tzinfo=timezone.utc)
    if period_month == 1:
        prev_start = datetime(period_year - 1, 12, 1, tzinfo=timezone.utc)
    else:
        prev_start = datetime(period_year, period_month - 1, 1, tzinfo=timezone.utc)
    prev_end = cur_start
    label = f'{period_year:04d}-{period_month:02d}'
    return cur_start, cur_end, prev_start, prev_end, label


# ─────────────────────────── JSON serialization ───────────────────────────

def _json_default(o: Any) -> Any:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(f'not serializable: {type(o).__name__}')


def to_json_artifact(period: str, delta: MonthlyDelta, anomalies: list[Anomaly]) -> dict[str, Any]:
    """Build the v1 intermediate JSON artifact (sec 16.6)."""
    def _serialize_window(m: MonthlyMetrics | None) -> dict[str, Any] | None:
        if m is None:
            return None
        return {
            'start': m.period_start.isoformat(),
            'end': m.period_end.isoformat(),
            'by_use_case': {uc: asdict(v) for uc, v in m.by_use_case.items()},
            'total_cost_usd': m.total_cost_usd,
            'total_call_count': m.total_call_count,
        }

    al = build_anomaly_list(period, delta, anomalies)
    return {
        'schema_version': 'v1',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'period': period,
        'current_window': _serialize_window(delta.current),
        'previous_window': _serialize_window(delta.previous),
        'deltas': {uc: asdict(d) for uc, d in delta.per_use_case_delta.items()},
        'anomalies': [asdict(a) for a in al.items],
        'summary': {
            'total_cost_usd': al.total_cost_usd,
            'total_call_count': al.total_call_count,
            'use_cases_observed': al.use_cases_observed,
            'use_cases_anomalous': al.use_cases_anomalous,
            'anomalies_count': len(al.items),
            'anomalies_high_severity': sum(1 for a in al.items if a.severity == 'high'),
        },
    }


# ─────────────────────────── Markdown debug dump ───────────────────────────

def to_markdown_debug(period: str, delta: MonthlyDelta, anomalies: list[Anomaly]) -> str:
    """Plain markdown dump for developer inspection. NOT a user-facing artifact."""
    lines: list[str] = [f'# Router monthly debug — {period}', '']
    cur = delta.current
    lines.append(f'**Current window**: {cur.period_start} → {cur.period_end} '
                 f'({cur.total_call_count} calls, ${cur.total_cost_usd:.4f})')
    if delta.previous:
        p = delta.previous
        lines.append(f'**Previous window**: {p.period_start} → {p.period_end} '
                     f'({p.total_call_count} calls, ${p.total_cost_usd:.4f})')
    lines += ['', '## Anomalies', '']
    if not anomalies:
        lines.append('_brak — stabilny miesiąc_')
    else:
        for a in anomalies:
            lines.append(f'- **{a.use_case}** — `{a.anomaly_class}` ({a.severity})')
            lines.append(f'  - evidence: `{json.dumps(a.evidence, default=_json_default)}`')
            lines.append(f'  - action: {a.suggested_action}')
    lines += ['', '## Per-use_case (current)', '',
              '| use_case | calls | avg_cost | p95_lat | fail_rate |',
              '|---|---:|---:|---:|---:|']
    for uc, m in sorted(cur.by_use_case.items(), key=lambda kv: -kv[1].total_cost_usd):
        lines.append(f'| {uc} | {m.n_calls} | ${m.avg_cost_usd:.4f} '
                     f'| {m.p95_latency_ms}ms | {m.fail_rate:.1%} |')
    return '\n'.join(lines) + '\n'


# ─────────────────────────── LLM narrative (O.2) ───────────────────────────

# Canonical use_case from yaml (sec 16.7) — anthropic claude-haiku PRIMARY,
# NOT Qwen (F8.8 "stiff Polish" lesson). Cost ~$0.12/year, negligible.
_NARRATIVE_USE_CASE = '_router_monthly_summary'
_NARRATIVE_COST_CAP_USD = 0.05
_NARRATIVE_MAX_REPROMPTS = 2


_NARRATIVE_SYSTEM_PROMPT = """\
Jesteś analitykiem operacji LLM router. Generujesz miesięczny raport po polsku
dla operatora, który ma 10 minut na przegląd.

Reguły:
1. TL;DR = 2-5 zdań naturalnym polskim. Zacznij od stanu ogólnego (X z Y use cases stabilne),
   wyróżnij top 1 anomaly, zakończ konkretną akcją w imperatywie LUB "brak akcji".
2. Per-anomaly narrative = 1-3 zdania each. Format: liczby + hipoteza + action.
   NIE rób bullet listów. NIE pisz "consider"/"might"/"warto rozważyć".
   Używaj imperatywu: "flip", "pin", "observe", "investigate", "no action needed".
3. Tone: imagine że tłumaczysz userowi router state przy kawie — krótko, językiem domeny,
   z jasną rekomendacją. Unikaj corporate-speak.
4. Reference do anomaly_class jest INPUT — Twoja narrative ma to przełożyć na ludzki język,
   nie powtarzać kategorię verbatim ('cost_spike' → 'koszt wzrósł o 47%').
5. Action_items: 0-3 items max. Tylko gdy jest konkretne yaml-actionable change. Brak akcji
   = empty list, NIE wymyślaj akcji żeby coś było.
6. Język: polski. Liczby zostaw cyframi. USD zostaw $.
7. NIE generuj tabel markdown ani bullet listów >5 itemów. Tabele żyją tylko w `## Appendix`.
"""


_NARRATIVE_TOOL_SCHEMA: dict[str, Any] = {
    'name': 'generate_monthly_summary',
    'description': 'Generate Polish-language monthly router report narrative.',
    'input_schema': {
        'type': 'object',
        'properties': {
            'tldr': {
                'type': 'string',
                'description': (
                    "2-5 zdań w naturalnym polskim — co działo się w miesiącu, "
                    "jedna konkretna rekomendacja albo 'brak akcji'. Tone: "
                    "tłumaczę userowi przy kawie. Zacznij od liczby use cases, "
                    "wyróżnij top anomaly, zakończ akcją w imperatywie."
                ),
                'minLength': 80,
                'maxLength': 800,
            },
            'anomaly_narratives': {
                'type': 'array',
                'maxItems': 8,
                'items': {
                    'type': 'object',
                    'properties': {
                        'use_case': {'type': 'string'},
                        'narrative': {
                            'type': 'string',
                            'description': (
                                "1-3 zdania PO polsku. Format: 'F-X — koszt $Y/call (delta), "
                                "latency Zms, fail rate W%. Hipoteza: <reason>. Action: <imperative>.' "
                                "NIE używać bullet listów. NIE 'consider'/'might'/'maybe' — "
                                "używać 'flip', 'pin', 'observe', 'no action needed'."
                            ),
                            'minLength': 40,
                            'maxLength': 400,
                        },
                    },
                    'required': ['use_case', 'narrative'],
                },
            },
            'action_items': {
                'type': 'array',
                'maxItems': 8,
                'items': {
                    'type': 'object',
                    'properties': {
                        'imperative': {
                            'type': 'string',
                            'description': (
                                "Konkretna akcja yaml w imperatywie, np. 'Flip primary "
                                "second_brain.F8_8 do anthropic:claude-haiku-4-5-20251001'. "
                                "NIE 'consider'."
                            ),
                        },
                        'use_case': {'type': 'string'},
                        'expected_effect': {
                            'type': 'string',
                            'description': (
                                "Krótkie 'co się zmieni' — np. '+$0.20/mc cost, eliminuje 12% fail rate'."
                            ),
                        },
                    },
                    'required': ['imperative', 'use_case', 'expected_effect'],
                },
            },
        },
        'required': ['tldr', 'anomaly_narratives', 'action_items'],
    },
}


@dataclass(frozen=True)
class AnomalyNarrative:
    use_case: str
    narrative: str


@dataclass(frozen=True)
class ActionItem:
    imperative: str
    use_case: str
    expected_effect: str


@dataclass(frozen=True)
class NarrativeOutput:
    tldr: str
    anomaly_narratives: list[AnomalyNarrative]
    action_items: list[ActionItem]
    cost_usd: float = 0.0
    provider: str = ''
    model: str = ''
    degraded: bool = False              # True when LLM call failed; templated fallback used
    reason: str = ''                    # populated when degraded=True


_TABLE_LINE_RE = re.compile(r'^\s*\|')
_BULLET_LINE_RE = re.compile(r'^\s*\*\s')


def _has_table_or_bullets(text: str) -> bool:
    """True if text starts with markdown table or bullet, or contains many bullets."""
    if not text:
        return False
    stripped = text.lstrip()
    if _TABLE_LINE_RE.match(stripped):
        return True
    if _BULLET_LINE_RE.match(stripped):
        return True
    bullet_count = sum(1 for line in text.splitlines() if _BULLET_LINE_RE.match(line))
    return bullet_count > 5


def _validate_output(payload: dict[str, Any]) -> tuple[bool, str]:
    """Anti-table validation per CRITICAL DoD invariant. Returns (ok, reason)."""
    tldr = payload.get('tldr', '')
    if _has_table_or_bullets(tldr):
        return False, 'tldr contains markdown table or bullet list'
    for item in payload.get('anomaly_narratives', []) or []:
        if _has_table_or_bullets(item.get('narrative', '')):
            return False, f"anomaly_narratives[{item.get('use_case')}].narrative contains table/bullet"
    for item in payload.get('action_items', []) or []:
        if _has_table_or_bullets(item.get('imperative', '')):
            return False, "action_items[].imperative contains table/bullet"
    return True, ''


def _build_llm_input(period: str, delta: MonthlyDelta, anomalies: list[Anomaly]) -> str:
    """JSON-only input (sec 16.7) — keep LLM away from markdown table echo."""
    al = build_anomaly_list(period, delta, anomalies)
    cur = delta.current
    # Top-N=12 by anomalous use cases first, then by cost desc.
    anomalous_uc = {a.use_case for a in anomalies}
    by_cost = sorted(cur.by_use_case.values(), key=lambda m: -m.total_cost_usd)
    selected: list[UseCaseMetrics] = []
    for m in by_cost:
        if m.use_case in anomalous_uc:
            selected.append(m)
    for m in by_cost:
        if m.use_case not in anomalous_uc and len(selected) < 12:
            selected.append(m)
    truncated = max(0, len(cur.by_use_case) - len(selected))
    truncated_cost = sum(m.total_cost_usd for m in by_cost[len(selected):])

    payload = {
        'period': period,
        'summary': {
            'use_cases_observed': al.use_cases_observed,
            'use_cases_anomalous': al.use_cases_anomalous,
            'total_call_count': al.total_call_count,
            'total_cost_usd': al.total_cost_usd,
        },
        'use_cases_top_n': [asdict(m) for m in selected],
        'truncated_use_cases': truncated,
        'truncated_total_cost_usd': truncated_cost,
        'anomalies': [asdict(a) for a in al.items],
    }
    return json.dumps(payload, ensure_ascii=False, default=_json_default, indent=2)


def _templated_fallback_narrative(period: str, delta: MonthlyDelta, anomalies: list[Anomaly]) -> NarrativeOutput:
    """Deterministic narrative used when LLM call fails (sec 16.7 graceful degrade)."""
    cur = delta.current
    n_uc = len(cur.by_use_case)
    high_count = sum(1 for a in anomalies if a.severity == 'high')
    if not anomalies:
        tldr = (f'Stabilny miesiąc — {n_uc} use cases, {cur.total_call_count} calls, '
                f'${cur.total_cost_usd:.2f} spend. Brak anomalii. Brak zalecanych zmian.')
    elif high_count > 0:
        tldr = (f'{n_uc} use cases obserwowanych ({cur.total_call_count} calls, '
                f'${cur.total_cost_usd:.2f}). {high_count} high-severity anomalii — '
                f'review szczegółów w sekcji Anomalie. UWAGA: narrative LLM padł, '
                f'raport degraded (deterministic templates only).')
    else:
        tldr = (f'{n_uc} use cases obserwowanych ({cur.total_call_count} calls, '
                f'${cur.total_cost_usd:.2f}). {len(anomalies)} anomalii info/medium — '
                f'review szczegółów w sekcji Anomalie. UWAGA: narrative LLM padł, '
                f'raport degraded.')
    narratives = [
        AnomalyNarrative(
            use_case=a.use_case,
            narrative=(f'`{a.anomaly_class}` (severity {a.severity}). '
                       f'Top provider: {a.top_provider or "n/a"}. '
                       f'Suggested: {a.suggested_action}'),
        )
        for a in anomalies
    ]
    return NarrativeOutput(
        tldr=tldr, anomaly_narratives=narratives, action_items=[],
        cost_usd=0.0, provider='', model='', degraded=True,
        reason='LLM narrative call failed — templated fallback used.',
    )


def generate_narrative(
    period: str,
    delta: MonthlyDelta,
    anomalies: list[Anomaly],
    *,
    raw_failure_path: Path | None = None,
) -> NarrativeOutput:
    """Call LLM via llm_router.call_tool with anti-table validation + 2× re-prompt.

    Hard-fail path (after 2 re-prompts or hard exception): writes raw_output to
    `raw_failure_path` (if provided) and returns a templated fallback narrative
    so the cron still produces a vault report.
    """
    user_text = _build_llm_input(period, delta, anomalies)
    schema = dict(_NARRATIVE_TOOL_SCHEMA)

    try:
        # Import workers.llm_routing first — its module-level initialize()
        # wires set_routing_config() + set_telemetry_sink() on import. Without
        # this the bare `llm_router.call_tool()` raises RoutingNotConfigured.
        from llm_router import call_tool as _router_call_tool

        import exocortex.llm_routing  # noqa: F401  (import-only side effect)
    except Exception as e:
        logger.error('llm_router init/import failed: %s', e)
        return _templated_fallback_narrative(period, delta, anomalies)

    last_payload: dict[str, Any] = {}
    last_usage: Any = None
    reprompt_suffix = ''
    last_reason = ''

    for attempt in range(_NARRATIVE_MAX_REPROMPTS + 1):
        try:
            payload, usage = _router_call_tool(
                use_case=_NARRATIVE_USE_CASE,
                system=_NARRATIVE_SYSTEM_PROMPT + reprompt_suffix,
                user=user_text,
                schema=schema,
                max_tokens=2000,
                cache_system=False,
            )
        except Exception as e:
            logger.warning('LLM call attempt %d failed: %s', attempt + 1, e)
            last_reason = f'llm_router.call_tool exception: {e}'
            break

        last_payload = payload or {}
        last_usage = usage
        ok, reason = _validate_output(last_payload)
        if ok:
            anomaly_narratives = [
                AnomalyNarrative(use_case=item.get('use_case', ''),
                                 narrative=item.get('narrative', ''))
                for item in (payload.get('anomaly_narratives') or [])
            ]
            action_items = [
                ActionItem(imperative=item.get('imperative', ''),
                           use_case=item.get('use_case', ''),
                           expected_effect=item.get('expected_effect', ''))
                for item in (payload.get('action_items') or [])
            ]
            return NarrativeOutput(
                tldr=payload.get('tldr', ''),
                anomaly_narratives=anomaly_narratives,
                action_items=action_items,
                cost_usd=float(getattr(usage, 'cost_usd', 0.0) or 0.0),
                provider=getattr(usage, 'provider', '') or '',
                model=getattr(usage, 'model', '') or '',
                degraded=False,
                reason='',
            )

        last_reason = reason
        logger.warning('Anti-table validation failed (attempt %d): %s', attempt + 1, reason)
        reprompt_suffix = (
            '\n\nUWAGA: Twój poprzedni output naruszył regułę "no tables / no bullet '
            'list >5 items". Wygeneruj ponownie naturalnym akapitem prozą.'
        )

    # Hard fail — save raw + return templated fallback
    if raw_failure_path is not None and last_payload:
        try:
            raw_failure_path.parent.mkdir(parents=True, exist_ok=True)
            raw_failure_path.write_text(
                json.dumps(last_payload, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
        except OSError as e:
            logger.error('failed to write raw failure log %s: %s', raw_failure_path, e)
    fallback = _templated_fallback_narrative(period, delta, anomalies)
    return NarrativeOutput(
        tldr=fallback.tldr,
        anomaly_narratives=fallback.anomaly_narratives,
        action_items=fallback.action_items,
        cost_usd=float(getattr(last_usage, 'cost_usd', 0.0) or 0.0) if last_usage else 0.0,
        provider=getattr(last_usage, 'provider', '') or '' if last_usage else '',
        model=getattr(last_usage, 'model', '') or '' if last_usage else '',
        degraded=True,
        reason=last_reason or 'LLM narrative validation failed after re-prompts.',
    )


# ─────────────────────────── Vault report (O.3) ───────────────────────────

_PL_MONTHS = {
    1: 'Styczeń', 2: 'Luty', 3: 'Marzec', 4: 'Kwiecień',
    5: 'Maj', 6: 'Czerwiec', 7: 'Lipiec', 8: 'Sierpień',
    9: 'Wrzesień', 10: 'Październik', 11: 'Listopad', 12: 'Grudzień',
}


def _period_pl(period: str) -> str:
    """'2026-04' → 'April 2026' (month name rendered in Polish)."""
    try:
        y, m = period.split('-')
        return f'{_PL_MONTHS[int(m)]} {int(y)}'
    except (ValueError, KeyError):
        return period


def _status_summary(anomalies_count: int, anomalies_high: int) -> str:
    if anomalies_count == 0:
        return 'healthy'
    if anomalies_high >= 1:
        return 'investigation'
    return 'needs_action'


def render_report(
    narrative: NarrativeOutput,
    delta: MonthlyDelta,
    anomalies: list[Anomaly],
    period: str,
    *,
    artifact_relpath: str = '',
) -> str:
    """Compose vault markdown per architect §16.8 (5-section + <details> tables)."""
    cur = delta.current
    al = build_anomaly_list(period, delta, anomalies)
    high_count = sum(1 for a in anomalies if a.severity == 'high')

    fm: list[str] = ['---',
                     'type: router-monthly-report',
                     f'period: {period}',
                     f'generated_at: {datetime.now(timezone.utc).isoformat()}',
                     f'total_use_cases: {al.use_cases_observed}',
                     f'total_calls: {al.total_call_count}',
                     f'total_cost_usd: {al.total_cost_usd:.4f}',
                     f'anomalies_count: {len(anomalies)}',
                     f'anomalies_high_severity: {high_count}',
                     'schema_version: v1',
                     f'artifact: {artifact_relpath}' if artifact_relpath else 'artifact: ""',
                     f'llm_summary_use_case: {_NARRATIVE_USE_CASE}',
                     f'llm_summary_provider: {narrative.provider or ""}',
                     f'llm_summary_model: {narrative.model or ""}',
                     f'llm_summary_cost_usd: {narrative.cost_usd:.4f}',
                     f'status_summary: {_status_summary(len(anomalies), high_count)}']
    if narrative.degraded:
        fm.append('narrative_degraded: true')
    fm.append('---')

    body: list[str] = ['', f'# Router monthly review — {_period_pl(period)}', '']

    body += ['## TL;DR', '', narrative.tldr.strip() or '_(brak narrative)_', '']

    body += ['## Anomalie', '']
    if not narrative.anomaly_narratives and not anomalies:
        body.append('Brak anomalii w tym miesiącu — router działa stabilnie.')
        body.append('')
    elif not narrative.anomaly_narratives:
        # narrative empty but anomalies present (shouldn't normally happen) — fall back to deterministic
        for a in anomalies:
            body.append(f'### `{a.use_case}`')
            body.append('')
            body.append(f'`{a.anomaly_class}` (severity {a.severity}). {a.suggested_action}')
            body.append('')
    else:
        for n in narrative.anomaly_narratives:
            body.append(f'### `{n.use_case}`')
            body.append('')
            body.append(n.narrative.strip())
            body.append('')

    body += ['## Action items', '']
    if not narrative.action_items:
        body.append('*Brak akcji do zaaplikowania w tym miesiącu.*')
        body.append('')
    else:
        for item in narrative.action_items:
            body.append(f'- [ ] **{item.use_case}** — {item.imperative}')
            if item.expected_effect:
                body.append(f'      *Expected*: {item.expected_effect}')
        body.append('')

    body += ['## Tabele (drill-down)', '',
             '<details>',
             '<summary>Pełna tabela per-use-case</summary>',
             '',
             '| use_case | provider | n_calls | avg_cost | p95_latency | fail_rate |',
             '|----------|----------|--------:|---------:|------------:|----------:|']
    for uc, m in sorted(cur.by_use_case.items(), key=lambda kv: -kv[1].total_cost_usd):
        body.append(
            f'| `{uc}` | {m.top_provider() or "n/a"} | {m.n_calls} '
            f'| ${m.avg_cost_usd:.4f} | {m.p95_latency_ms}ms | {m.fail_rate:.1%} |'
        )
    body += ['', '</details>', '']

    body += ['<details>',
             '<summary>Anomaly raw evidence</summary>',
             '',
             '| use_case | anomaly_class | severity | evidence |',
             '|----------|---------------|----------|----------|']
    if not anomalies:
        body.append('| _(brak)_ | — | — | — |')
    else:
        for a in anomalies:
            ev = json.dumps(a.evidence, ensure_ascii=False, default=_json_default)
            body.append(f'| `{a.use_case}` | {a.anomaly_class} | {a.severity} | `{ev}` |')
    body += ['', '</details>', '']

    body += ['## Meta', '',
             f'- **Period**: {_period_pl(period)} ({period})',
             '- **Source**: `ag_catalog.llm_provider_runs` (last 30d + previous 30d)',
             f'- **Intermediate JSON**: `{artifact_relpath}`' if artifact_relpath else '- **Intermediate JSON**: _(not persisted)_',
             f'- **Narrative LLM cost**: ${narrative.cost_usd:.4f} '
             f'(use_case `{_NARRATIVE_USE_CASE}`, '
             f'{narrative.provider}:{narrative.model})',
             '- **Generated by**: `workers/router_telemetry_monthly.py`']
    if narrative.degraded:
        body.append(f'- **NOTE**: narrative degraded — {narrative.reason}')
    body.append('')

    return '\n'.join(fm + body)


def _hash_content(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:12]


def _resolve_vault_path(override: str | None = None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    from pydantic import ValidationError

    from exocortex.settings import Settings
    try:
        return Settings().vault_path.expanduser().resolve()
    except ValidationError as exc:
        raise RuntimeError(
            'vault path not configured: set EXOCORTEX_VAULT_PATH '
            '(or pass --vault-path)'
        ) from exc


def write_to_vault(
    report_md: str,
    period: str,
    *,
    vault_path: Path | None = None,
    force_overwrite: bool = False,
) -> Path:
    """Idempotent write to {vault}/wiki/_routing-monthly-{period}.md.

    Returns the written path. If the file exists with identical content hash,
    skips write and returns the existing path. Different content + no
    --force-overwrite → raises FileExistsError (operator-controlled re-emit).
    """
    base = vault_path or _resolve_vault_path()
    target_dir = base / 'wiki'
    if not target_dir.exists():
        raise FileNotFoundError(f'vault wiki directory missing: {target_dir}')
    target = target_dir / f'_routing-monthly-{period}.md'
    new_hash = _hash_content(report_md)
    if target.exists():
        existing_hash = _hash_content(target.read_text(encoding='utf-8'))
        if existing_hash == new_hash:
            logger.info('vault file unchanged: %s', target)
            return target
        if not force_overwrite:
            raise FileExistsError(
                f'{target} exists with different content; pass --force-overwrite '
                'to replace (preserves SAFETY constraint).'
            )
        backup = target.with_suffix(f'.{existing_hash}.bak')
        target.rename(backup)
        logger.warning('backed up prior report to %s', backup)
    target.write_text(report_md, encoding='utf-8')
    logger.info('wrote vault report: %s', target)
    return target


def write_artifact_json(
    artifact: dict[str, Any],
    period: str,
    *,
    vault_path: Path | None = None,
) -> Path:
    """Persist intermediate JSON to {vault}/.router/monthly_metrics_{period}.json (sec 16.6)."""
    base = vault_path or _resolve_vault_path()
    target_dir = base / '.router'
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f'monthly_metrics_{period}.json'
    target.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, default=_json_default),
        encoding='utf-8',
    )
    return target


# ─────────────────────────── CLI entry point ───────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='router_telemetry_monthly',
        description='Aggregate llm_provider_runs into monthly delta + anomaly JSON / vault report.',
    )
    p.add_argument('--period', default=None,
                   help='YYYY-MM (default: previous calendar month)')
    p.add_argument('--output', choices=('json', 'markdown', 'vault'), default='json',
                   help='Output target. json/markdown → stdout; vault → write report '
                        'to {vault}/wiki/_routing-monthly-{period}.md.')
    p.add_argument('--vault-path', default=None,
                   help='Override vault root (default: $EXOCORTEX_VAULT_PATH; '
                        '$VAULT_PATH and $SECOND_BRAIN_VAULT_PATH are deprecated '
                        'aliases honoured by Settings).')
    p.add_argument('--force-overwrite', action='store_true',
                   help='Allow overwrite of existing vault report (creates .bak).')
    p.add_argument('--dry-run', action='store_true',
                   help='With --output vault: print rendered markdown to stdout, '
                        'do not touch vault, do not call LLM (templated narrative).')
    p.add_argument('--log-level', default='WARNING')
    return p


def _run_pipeline(period_label: str, cur_start: datetime, cur_end: datetime,
                  prev_start: datetime, prev_end: datetime,
                  ) -> tuple[MonthlyDelta, list[Anomaly]]:
    current = query_period_metrics(cur_start, cur_end)
    previous = query_period_metrics(prev_start, prev_end)
    prev_arg: MonthlyMetrics | None = previous if previous.total_call_count > 0 else None
    delta = compute_delta(current, prev_arg)
    anomalies = detect_anomalies(delta)
    return delta, anomalies


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.WARNING),
                        format='%(asctime)s %(levelname)s %(name)s %(message)s')

    cur_start, cur_end, prev_start, prev_end, period_label = parse_period(args.period)

    # Phase 1 telemetry shipped 2026-05; reject pre-2026-05 backfill cleanly.
    if (cur_start.year, cur_start.month) < (2026, 5):
        print(f'error: no telemetry data before 2026-05 (asked for {period_label})',
              file=sys.stderr)
        return 2

    try:
        delta, anomalies = _run_pipeline(period_label, cur_start, cur_end, prev_start, prev_end)
    except Exception as e:
        logger.error('DB query failed: %s', e, exc_info=True)
        print(f'error: DB query failed — {e}', file=sys.stderr)
        return 1

    if args.output == 'json':
        artifact = to_json_artifact(period_label, delta, anomalies)
        print(json.dumps(artifact, indent=2, ensure_ascii=False, default=_json_default))
        return 0
    if args.output == 'markdown':
        print(to_markdown_debug(period_label, delta, anomalies))
        return 0

    # output == 'vault'
    vault_path = _resolve_vault_path(args.vault_path)
    artifact = to_json_artifact(period_label, delta, anomalies)

    if args.dry_run:
        narrative = _templated_fallback_narrative(period_label, delta, anomalies)
        report = render_report(narrative, delta, anomalies, period_label,
                               artifact_relpath=f'.router/monthly_metrics_{period_label}.json')
        print(report)
        return 0

    artifact_path = write_artifact_json(artifact, period_label, vault_path=vault_path)
    artifact_relpath = str(artifact_path.relative_to(vault_path))

    raw_failure_path = vault_path / 'data' / 'router-monthly' / f'raw-output-failed-{period_label}.json'
    narrative = generate_narrative(period_label, delta, anomalies,
                                   raw_failure_path=raw_failure_path)
    report = render_report(narrative, delta, anomalies, period_label,
                           artifact_relpath=artifact_relpath)
    try:
        target = write_to_vault(report, period_label, vault_path=vault_path,
                                force_overwrite=args.force_overwrite)
    except FileExistsError as e:
        print(f'error: {e}', file=sys.stderr)
        return 5
    except FileNotFoundError as e:
        print(f'error: {e}', file=sys.stderr)
        return 4
    print(f'wrote {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
