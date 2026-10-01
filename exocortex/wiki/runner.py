# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Wiki compilation runner — domain registry + RunContext.

Thin orchestration layer over the legacy wiki_compiler globals.
Reads the Registry for compile_domains, sets module-level state in
wiki_compiler, then calls each DomainCompiler.compile(ctx).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class RunContext:
    """Immutable context threaded through every DomainCompiler.compile() call."""

    tenant_id: str
    since: datetime | None = None


def setup_builtins(registry: Any) -> None:
    """Register all built-in domain compilers into *registry*."""
    from exocortex.wiki.domains import (
        clippings,
        cross_domain,
        live_sections,
    )
    from exocortex.wiki.domains.frp import setup as frp_setup
    from exocortex.wiki.domains.home import setup as home_setup
    from exocortex.wiki.domains.news import setup as news_setup
    from exocortex.wiki.domains.work import setup as work_setup

    for setup_fn in (
        work_setup,
        frp_setup,
        news_setup,
        home_setup,
        cross_domain.setup,
        live_sections.setup,
        clippings.setup,
    ):
        setup_fn(registry)


def compile_all(
    registry: Any,
    tenant_id: str,
    domain: str = "all",
    since: datetime | None = None,
    dry_run: bool = False,
    full_rebuild: bool = False,
) -> None:
    """Compile wiki domains using the registry.

    Sets legacy globals in wiki_compiler before dispatching to each
    DomainCompiler so existing compile_* functions keep working unchanged.
    """
    import exocortex.wiki_compiler as _wc

    VALID = set(_wc.VALID_DOMAINS)
    if domain != "all" and domain not in VALID:
        raise ValueError(f"Unknown domain: {domain!r}. Valid: {sorted(VALID)}")

    from exocortex.db import execute, query_one
    from exocortex.pipeline_log import log_run_end, log_run_start

    _pl_id = log_run_start(
        "wiki_compiler",
        domain=domain,
        dry_run=dry_run,
        since=str(since) if since else None,
    )

    _wc._pages_written.clear()
    _wc._llm_tokens_used = 0
    _wc.DRY_RUN = dry_run
    _wc.FULL_REBUILD = full_rebuild

    if dry_run:
        print("[wiki_compiler] DRY RUN — no filesystem changes will be made")
        _wc.current_run_id = None
    else:

        started = datetime.now(UTC).isoformat()
        run = query_one(
            "INSERT INTO compile_runs (tenant_id, domain, triggered_by, "
            "schema_version, started_at) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            tenant_id,
            domain,
            "manual",
            _wc.SCHEMA_VERSION,
            started,
        )
        _wc.current_run_id = str(run["id"]) if run else None

    ctx = RunContext(tenant_id=tenant_id, since=since)
    failed: list[str] = []

    for name, compiler in registry.compile_domains.items():
        if domain not in (name, "all"):
            continue
        try:
            compiler.compile(ctx)
        except NotImplementedError:
            print(f"[wiki_compiler] WARN: {name} module not implemented — skipped")
            failed.append(name)
            continue
        except Exception as exc:
            print(f"[wiki_compiler] ERROR: {name} module failed: {exc!r}")
            failed.append(name)
            continue
        # Pruning runs only after a clean compile — pruning against a
        # half-written domain could delete pages whose replacement never
        # got written. A failure here is reported but does not fail the
        # domain: stale files are untidy, a missing compile is not.
        try:
            compiler.prune_orphans(ctx)
        except Exception as exc:
            print(f"[wiki_compiler] WARN: {name} prune_orphans failed: {exc!r}")

    if _wc.current_run_id and not dry_run:

        execute(
            "UPDATE compile_runs SET finished_at = %s, pages_written = %s, "
            "failed_domains = %s, llm_tokens_used = %s WHERE id = %s",
            datetime.now(UTC).isoformat(),
            list(_wc._pages_written),
            failed,
            _wc._llm_tokens_used or None,
            _wc.current_run_id,
        )

    status = "success" if not failed else "failure"
    log_run_end(_pl_id, status, counts={"pages_written": len(_wc._pages_written)})
    print(
        f"[wiki_compiler] done: {len(_wc._pages_written)} pages "
        f"{'would change' if dry_run else 'written'}, "
        f"{len(failed)} failed"
    )
