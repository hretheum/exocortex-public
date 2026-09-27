# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Tests for scripts/apply_router_rule.py — F-router-O.5.2 atomic DoD."""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path
from textwrap import dedent

import pytest

# scripts/ is not a package; load via importlib.
_SPEC = importlib.util.spec_from_file_location(
    'apply_router_rule',
    Path(__file__).resolve().parents[1] / 'scripts' / 'apply_router_rule.py',
)
assert _SPEC is not None and _SPEC.loader is not None
apply_module = importlib.util.module_from_spec(_SPEC)
sys.modules['apply_router_rule'] = apply_module
_SPEC.loader.exec_module(apply_module)


@pytest.fixture
def yaml_file(tmp_path: Path) -> Path:
    """Minimal config/llm_routing.yaml fixture with comments preserved."""
    content = dedent("""\
        # second-brain routing config (test fixture)
        providers:
          anthropic:
            api_key_env: ANTHROPIC_API_KEY
            default_model: claude-haiku-4-5-20251001
          deepinfra:
            api_key_env: DEEPINFRA_API_KEY
            default_model: Qwen/Qwen3.5-397B-A17B

        defaults:
          primary: { provider: deepinfra, model: Qwen/Qwen3.5-397B-A17B }
          fallback:
            - { provider: anthropic, model: claude-haiku-4-5-20251001 }
          cost_stop_per_call_usd: 0.50

        use_cases:
          # F4 synthesis — Qwen primary
          second_brain.F4_synthesis_client:
            primary: { provider: deepinfra, model: Qwen/Qwen3.5-397B-A17B }
            fallback:
              - { provider: anthropic, model: claude-haiku-4-5-20251001 }
            cost_stop_per_call_usd: 1.00
        """)
    p = tmp_path / 'llm_routing.yaml'
    p.write_text(content, encoding='utf-8')
    return p


@pytest.fixture
def audit_file(tmp_path: Path) -> Path:
    return tmp_path / 'data' / 'router-monthly' / 'applied-rules.tsv'


def _run(args: list[str], yaml_file: Path, audit_file: Path,
         extra: list[str] | None = None) -> int:
    full = list(args) + ['--yaml-path', str(yaml_file),
                         '--audit-path', str(audit_file),
                         '--no-confirm', '--operator', 'tester']
    if extra:
        full += extra
    return apply_module.main(full)


# ─────────────────────────── Action handlers ───────────────────────────

def test_flip_primary_changes_yaml(yaml_file, audit_file):
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'flip_primary',
        '--to', 'anthropic:claude-haiku-4-5-20251001',
        '--reason', 'cost spike +47%',
        '--period-ref', '2026-04',
    ], yaml_file, audit_file)
    assert rc == 0
    out = yaml_file.read_text(encoding='utf-8')
    # primary now anthropic for that use_case
    _, data = apply_module._load_yaml(yaml_file)
    block = data['use_cases']['second_brain.F4_synthesis_client']
    assert block['primary']['provider'] == 'anthropic'
    assert block['primary']['model'] == 'claude-haiku-4-5-20251001'
    # comment preserved
    assert '# F4 synthesis — Qwen primary' in out


def test_flip_primary_uses_provider_default_model(yaml_file, audit_file):
    """Bare provider (no `:model`) → default_model from providers: block."""
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'flip_primary',
        '--to', 'anthropic',
    ], yaml_file, audit_file)
    assert rc == 0
    _, data = apply_module._load_yaml(yaml_file)
    block = data['use_cases']['second_brain.F4_synthesis_client']
    assert block['primary']['model'] == 'claude-haiku-4-5-20251001'


def test_unknown_provider_rejected(yaml_file, audit_file):
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'flip_primary',
        '--to', 'acme:gpt-99',
    ], yaml_file, audit_file)
    assert rc == 2  # validation error path


def test_add_fallback_appends(yaml_file, audit_file):
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'add_fallback',
        '--to', 'deepinfra:Qwen/Qwen3.5-397B-A17B',  # not currently in fallback
    ], yaml_file, audit_file)
    assert rc == 0
    _, data = apply_module._load_yaml(yaml_file)
    fb = data['use_cases']['second_brain.F4_synthesis_client']['fallback']
    providers = [e.get('provider') for e in fb]
    assert 'deepinfra' in providers


def test_add_fallback_idempotent(yaml_file, audit_file):
    """Already-present entry → noop, no duplicate."""
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'add_fallback',
        '--to', 'anthropic:claude-haiku-4-5-20251001',  # already there
    ], yaml_file, audit_file)
    assert rc == 0
    _, data = apply_module._load_yaml(yaml_file)
    fb = data['use_cases']['second_brain.F4_synthesis_client']['fallback']
    assert sum(1 for e in fb if e.get('provider') == 'anthropic') == 1


def test_raise_cost_cap(yaml_file, audit_file):
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'raise_cost_cap',
        '--to', '2.50',
    ], yaml_file, audit_file)
    assert rc == 0
    _, data = apply_module._load_yaml(yaml_file)
    assert float(data['use_cases']['second_brain.F4_synthesis_client']['cost_stop_per_call_usd']) == 2.5


def test_raise_cost_cap_invalid_value(yaml_file, audit_file):
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'raise_cost_cap',
        '--to', 'not-a-number',
    ], yaml_file, audit_file)
    assert rc == 2


def test_pin_off_sets_auto_mode(yaml_file, audit_file):
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'pin_off',
    ], yaml_file, audit_file)
    assert rc == 0
    _, data = apply_module._load_yaml(yaml_file)
    assert data['use_cases']['second_brain.F4_synthesis_client']['auto']['mode'] == 'off'


def test_investigate_audit_only_no_yaml_change(yaml_file, audit_file):
    before = yaml_file.read_text(encoding='utf-8')
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'investigate',
        '--reason', 'latency growth needs root cause',
    ], yaml_file, audit_file)
    assert rc == 0
    assert yaml_file.read_text(encoding='utf-8') == before
    # audit row appended
    rows = list(csv.DictReader(audit_file.open('r'), delimiter='\t'))
    assert len(rows) == 1
    assert rows[0]['action'] == 'investigate'


def test_no_action_audit_only(yaml_file, audit_file):
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'no_action',
        '--reason', 'variance within natural range',
    ], yaml_file, audit_file)
    assert rc == 0
    rows = list(csv.DictReader(audit_file.open('r'), delimiter='\t'))
    assert rows[0]['action'] == 'no_action'


# ─────────────────────────── New use_case path ───────────────────────────

def test_creates_use_case_block_inheriting_defaults(yaml_file, audit_file):
    """Acting on a use_case absent from yaml → create block from defaults."""
    rc = _run([
        '--use-case', 'second_brain.brand_new',
        '--action', 'flip_primary',
        '--to', 'anthropic',
    ], yaml_file, audit_file)
    assert rc == 0
    _, data = apply_module._load_yaml(yaml_file)
    assert 'second_brain.brand_new' in data['use_cases']


# ─────────────────────────── Audit log ───────────────────────────

def test_audit_header_and_row(yaml_file, audit_file):
    _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'flip_primary',
        '--to', 'anthropic',
        '--reason', 'cost spike',
        '--period-ref', '2026-04',
    ], yaml_file, audit_file)
    with audit_file.open('r', encoding='utf-8') as f:
        first = f.readline().rstrip('\n').split('\t')
    assert first == apply_module.AUDIT_HEADER
    rows = list(csv.DictReader(audit_file.open('r'), delimiter='\t'))
    row = rows[0]
    assert row['use_case'] == 'second_brain.F4_synthesis_client'
    assert row['action'] == 'flip_primary'
    assert row['reason'] == 'cost spike'
    assert row['period_ref'] == '2026-04'
    assert row['operator'] == 'tester'


def test_audit_idempotent_within_hour(yaml_file, audit_file):
    _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'flip_primary',
        '--to', 'anthropic',
    ], yaml_file, audit_file)
    # Repeat — should be detected as duplicate (same use_case+action+from+to within 1h)
    _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'flip_primary',
        '--to', 'anthropic',
    ], yaml_file, audit_file)
    rows = list(csv.DictReader(audit_file.open('r'), delimiter='\t'))
    assert len(rows) == 1


# ─────────────────────────── Dry-run ───────────────────────────

def test_dry_run_does_not_write(yaml_file, audit_file):
    before = yaml_file.read_text(encoding='utf-8')
    rc = _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'flip_primary',
        '--to', 'anthropic',
        '--dry-run',
    ], yaml_file, audit_file)
    assert rc == 0
    assert yaml_file.read_text(encoding='utf-8') == before
    assert not audit_file.exists()


# ─────────────────────────── Round-trip preserves comments ───────────────────────────

def test_round_trip_preserves_comments(yaml_file, audit_file):
    _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'flip_primary',
        '--to', 'anthropic',
    ], yaml_file, audit_file)
    text = yaml_file.read_text(encoding='utf-8')
    assert '# second-brain routing config (test fixture)' in text
    assert '# F4 synthesis — Qwen primary' in text


# ─────────────────────────── Backup created ───────────────────────────

def test_backup_created_on_write(yaml_file, audit_file, tmp_path):
    _run([
        '--use-case', 'second_brain.F4_synthesis_client',
        '--action', 'flip_primary',
        '--to', 'anthropic',
    ], yaml_file, audit_file)
    backups = list(yaml_file.parent.glob('llm_routing.yaml.*.bak'))
    assert len(backups) == 1
    # backup is byte-identical to pre-write content
    backup_text = backups[0].read_text(encoding='utf-8')
    assert '# second-brain routing config (test fixture)' in backup_text
    # primary in backup is still original (deepinfra)
    assert 'provider: deepinfra' in backup_text
