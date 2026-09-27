#!/usr/bin/env python3
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Operator helper — apply a router rule change to config/llm_routing.yaml.

Companion to `workers/router_telemetry_monthly.py` (R3 operator-driven
routing). The monthly cron generates a vault report with action items;
the operator reviews and runs this script to apply each accepted change.

Per architect §16.1 non-goals: the cron NEVER writes yaml. This script
is the sole write path, invoked by the operator from the monthly report.

Workflow:
    python scripts/apply_router_rule.py \\
        --use-case second_brain.F8_8_newsletter_aggregator \\
        --action flip_primary --to anthropic:claude-haiku-4-5-20251001 \\
        --reason "cost spike +47% (period 2026-04)" --period-ref 2026-04

Action enum: flip_primary | add_fallback | raise_cost_cap | pin_off |
investigate | no_action.

Use --dry-run to preview. Without --apply the script edits yaml + audit log
but does NOT scp/restart timers (deploy step optional).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import difflib
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YAML = REPO_ROOT / 'config' / 'llm_routing.yaml'
DEFAULT_AUDIT = REPO_ROOT / 'data' / 'router-monthly' / 'applied-rules.tsv'

ACTIONS = ('flip_primary', 'add_fallback', 'raise_cost_cap', 'pin_off',
           'investigate', 'no_action')

AUDIT_HEADER = ['timestamp', 'operator', 'use_case', 'action',
                'from', 'to', 'reason', 'period_ref']


# ─────────────────────────── yaml IO ───────────────────────────

def _load_yaml(path: Path):
    """Load yaml round-trip preserving comments. Returns (yaml_obj, data)."""
    from ruamel.yaml import YAML

    yaml = YAML(typ='rt')
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 120
    with path.open('r', encoding='utf-8') as f:
        data = yaml.load(f)
    return yaml, data


def _dump_yaml_to_string(yaml_obj, data) -> str:
    """Serialize ruamel data to string."""
    import io
    buf = io.StringIO()
    yaml_obj.dump(data, buf)
    return buf.getvalue()


def _parse_provider_model(spec: str) -> tuple[str, str | None]:
    """`anthropic:claude-haiku-4-5-20251001` → (`anthropic`, `claude-haiku-4-5-20251001`).

    Bare provider name (no `:`) → (provider, None) — caller resolves default model.
    """
    if not spec:
        return '', None
    if ':' in spec:
        provider, model = spec.split(':', 1)
        return provider.strip(), model.strip()
    return spec.strip(), None


def _resolve_model(data, provider: str, model: str | None) -> str:
    """Use yaml `providers.<name>.default_model` when caller omitted model."""
    if model:
        return model
    providers = (data or {}).get('providers') or {}
    p = providers.get(provider) or {}
    default = p.get('default_model')
    if not default:
        raise SystemExit(
            f'error: provider {provider!r} not found in providers: block, '
            'and no model specified after ":". Pass --to provider:model explicitly.'
        )
    return str(default)


def _validate_provider(data, provider: str) -> None:
    providers = (data or {}).get('providers') or {}
    if provider not in providers:
        raise SystemExit(f'error: unknown provider {provider!r} '
                         f'(known: {sorted(providers.keys())}).')


def _ensure_use_case_block(data, use_case: str) -> dict:
    """Locate or create `use_cases.<use_case>` inheriting from defaults."""
    use_cases = data.setdefault('use_cases', {})
    if use_case not in use_cases:
        defaults = data.get('defaults') or {}
        new_block = {
            'primary': dict(defaults.get('primary') or {}),
            'fallback': list(defaults.get('fallback') or []),
            'cost_stop_per_call_usd': defaults.get('cost_stop_per_call_usd', 0.10),
        }
        use_cases[use_case] = new_block
    return use_cases[use_case]


def _current_primary_str(block: dict) -> str:
    primary = block.get('primary') or {}
    p, m = primary.get('provider', ''), primary.get('model', '')
    return f'{p}:{m}' if p or m else ''


# ─────────────────────────── Action handlers ───────────────────────────

def apply_flip_primary(data, use_case: str, target_spec: str) -> tuple[str, str]:
    """Flip primary provider/model. Returns (from_str, to_str)."""
    provider, model = _parse_provider_model(target_spec)
    if not provider:
        raise SystemExit('error: --to required for flip_primary (provider:model).')
    _validate_provider(data, provider)
    model = _resolve_model(data, provider, model)
    block = _ensure_use_case_block(data, use_case)
    from_str = _current_primary_str(block)
    block['primary'] = {'provider': provider, 'model': model}
    return from_str, f'{provider}:{model}'


def apply_add_fallback(data, use_case: str, target_spec: str) -> tuple[str, str]:
    provider, model = _parse_provider_model(target_spec)
    if not provider:
        raise SystemExit('error: --to required for add_fallback (provider:model).')
    _validate_provider(data, provider)
    model = _resolve_model(data, provider, model)
    block = _ensure_use_case_block(data, use_case)
    fallback = block.setdefault('fallback', [])
    new_entry = {'provider': provider, 'model': model}
    # Idempotent: skip duplicate
    for entry in fallback:
        if entry.get('provider') == provider and entry.get('model') == model:
            from_str = ','.join(f"{e.get('provider')}:{e.get('model')}" for e in fallback)
            return from_str, from_str
    from_str = ','.join(f"{e.get('provider')}:{e.get('model')}" for e in fallback) or '(none)'
    fallback.append(new_entry)
    to_str = ','.join(f"{e.get('provider')}:{e.get('model')}" for e in fallback)
    return from_str, to_str


def apply_raise_cost_cap(data, use_case: str, target_spec: str) -> tuple[str, str]:
    try:
        new_cap = float(target_spec)
    except (TypeError, ValueError) as e:
        raise SystemExit(f'error: --to must be float USD for raise_cost_cap: {e}')
    block = _ensure_use_case_block(data, use_case)
    from_val = block.get('cost_stop_per_call_usd', 0.0)
    block['cost_stop_per_call_usd'] = new_cap
    return f'${float(from_val):.4f}', f'${new_cap:.4f}'


def apply_pin_off(data, use_case: str, target_spec: str) -> tuple[str, str]:
    """Set `auto.mode: off` (legacy bandit yaml — kept per spec for forward compat)."""
    block = _ensure_use_case_block(data, use_case)
    auto = block.setdefault('auto', {})
    from_str = str(auto.get('mode', '(unset)'))
    auto['mode'] = 'off'
    return from_str, 'off'


def apply_no_op(*args, **kwargs) -> tuple[str, str]:
    return '(noop)', '(noop)'


_HANDLERS = {
    'flip_primary': apply_flip_primary,
    'add_fallback': apply_add_fallback,
    'raise_cost_cap': apply_raise_cost_cap,
    'pin_off': apply_pin_off,
    'investigate': apply_no_op,
    'no_action': apply_no_op,
}


# ─────────────────────────── Audit log ───────────────────────────

def append_audit(audit_path: Path, row: dict[str, str]) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not audit_path.exists()
    with audit_path.open('a', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=AUDIT_HEADER, delimiter='\t',
                                lineterminator='\n')
        if new_file:
            writer.writeheader()
        writer.writerow(row)


def is_duplicate_within_hour(audit_path: Path, row: dict[str, str]) -> bool:
    """Match on (use_case, action, to) only — `from` shifts after the first
    successful apply, so including it would defeat idempotency."""
    if not audit_path.exists():
        return False
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)
    with audit_path.open('r', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for prior in reader:
            if not all(prior.get(k) == row[k] for k in ('use_case', 'action', 'to')):
                continue
            try:
                ts = dt.datetime.fromisoformat(prior['timestamp'])
            except (KeyError, ValueError):
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=dt.timezone.utc)
            if ts >= cutoff:
                return True
    return False


# ─────────────────────────── Main ───────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='apply_router_rule',
        description='Apply a single router rule change to config/llm_routing.yaml '
                    '(R3 operator-driven routing helper).',
    )
    p.add_argument('--use-case', required=True,
                   help='Target use_case key (e.g. second_brain.F8_8_newsletter_aggregator).')
    p.add_argument('--action', choices=ACTIONS, required=True)
    p.add_argument('--to', default=None,
                   help='Target spec: "provider:model" for flip_primary/add_fallback, '
                        'USD float for raise_cost_cap, ignored for pin_off/investigate/no_action.')
    p.add_argument('--reason', default='',
                   help='Free-text reason logged in audit + git commit.')
    p.add_argument('--period-ref', default='',
                   help='YYYY-MM of the source monthly report (for audit traceability).')
    p.add_argument('--operator', default=os.environ.get('USER', 'unknown'))
    p.add_argument('--yaml-path', default=str(DEFAULT_YAML),
                   help=f'Override yaml path (default: {DEFAULT_YAML}).')
    p.add_argument('--audit-path', default=str(DEFAULT_AUDIT),
                   help=f'Override audit log path (default: {DEFAULT_AUDIT}).')
    p.add_argument('--dry-run', action='store_true',
                   help='Preview yaml diff + audit row, no writes.')
    p.add_argument('--apply', action='store_true',
                   help='Also commit the yaml change + scp to droplet + restart timer. '
                        'Default behavior: edit yaml + audit log only (operator commits manually).')
    p.add_argument('--no-confirm', action='store_true',
                   help='Skip interactive y/N prompt (CI/scripted use).')
    return p


def _show_diff(before: str, after: str) -> bool:
    """Print unified diff to stdout. Returns True if any change."""
    diff = list(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile='config/llm_routing.yaml (before)',
        tofile='config/llm_routing.yaml (after)',
    ))
    if not diff:
        return False
    sys.stdout.writelines(diff)
    return True


def _confirm(prompt: str) -> bool:
    try:
        ans = input(f'{prompt} [y/N] ').strip().lower()
    except EOFError:
        return False
    return ans in ('y', 'yes')


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    yaml_path = Path(args.yaml_path)
    audit_path = Path(args.audit_path)

    if not yaml_path.exists():
        print(f'error: yaml not found: {yaml_path}', file=sys.stderr)
        return 1

    yaml_obj, data = _load_yaml(yaml_path)
    before_text = _dump_yaml_to_string(yaml_obj, data)

    handler = _HANDLERS[args.action]
    target_spec = args.to or ''
    try:
        from_str, to_str = handler(data, args.use_case, target_spec)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    after_text = _dump_yaml_to_string(yaml_obj, data)

    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    audit_row = {
        'timestamp': timestamp,
        'operator': args.operator,
        'use_case': args.use_case,
        'action': args.action,
        'from': from_str,
        'to': to_str,
        'reason': args.reason,
        'period_ref': args.period_ref,
    }

    # Idempotency: same action within an hour → skip.
    if is_duplicate_within_hour(audit_path, audit_row):
        print(f'noop: identical {args.action} on {args.use_case} already '
              'applied within last hour (audit log).', file=sys.stderr)
        return 0

    print('--- audit row preview ---')
    for k in AUDIT_HEADER:
        print(f'  {k}: {audit_row[k]}')
    print('--- yaml diff ---')
    has_diff = _show_diff(before_text, after_text)
    if not has_diff and args.action not in ('investigate', 'no_action'):
        print('(yaml unchanged — likely already in target state)', file=sys.stderr)

    if args.dry_run:
        print('\n[dry-run] no writes performed.')
        return 0

    if not args.no_confirm and not _confirm('Apply yaml edit + append audit log?'):
        print('aborted.', file=sys.stderr)
        return 3

    # Backup + write yaml.
    if has_diff:
        backup = yaml_path.with_suffix(
            yaml_path.suffix + f'.{timestamp.replace(":", "")}.bak'
        )
        shutil.copy2(yaml_path, backup)
        with yaml_path.open('w', encoding='utf-8') as f:
            f.write(after_text)
        print(f'wrote {yaml_path} (backup: {backup})')

    # Always append audit row (even no_action / investigate).
    append_audit(audit_path, audit_row)
    print(f'appended audit row → {audit_path}')

    if not args.apply:
        print('hint: re-run with --apply to git-commit + scp + restart droplet timer.')
        return 0

    # Optional deployment hooks (best-effort; failure does not roll back yaml).
    commit_msg = (
        f'[F-router-rule] {args.action} {args.use_case} → {to_str} '
        f'({args.reason or "no reason given"})'
    )
    try:
        subprocess.run(['git', 'add', str(yaml_path)], cwd=REPO_ROOT, check=True)
        subprocess.run(['git', 'commit', '-m', commit_msg], cwd=REPO_ROOT, check=True)
    except subprocess.CalledProcessError as e:
        print(f'warn: git commit failed ({e}); leaving yaml uncommitted.', file=sys.stderr)
        return 4

    droplet_yaml = '/etc/second-brain/llm_routing.yaml'
    try:
        subprocess.run(
            ['scp', str(yaml_path), f'second-brain-pg:{droplet_yaml}'],
            check=True,
        )
        subprocess.run(
            ['ssh', 'second-brain-pg',
             'sudo systemctl restart second-brain-router-monthly.timer'],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f'warn: scp/restart failed ({e}); yaml committed locally — '
              f'deploy manually.', file=sys.stderr)
        return 5
    print('deploy: scp + timer restart OK.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
