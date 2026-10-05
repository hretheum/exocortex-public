# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Exocortex CLI entry point.

Subcommands:

* ``exocortex init``                — scaffold *.yaml + .env from bundled examples
* ``exocortex migrate up | status`` — apply / inspect schema migrations
* ``exocortex ingest --from PATH``  — bulk-ingest a vault directory
* ``exocortex synth [...]``         — run the synthesizer (LLM perspectives)
* ``exocortex compile [...]``       — compile syntheses into wiki Markdown
* ``exocortex serve [--port N]``    — start the capture API on uvicorn
* ``exocortex query "question"``    — ad-hoc GraphRAG query (no Claude Desktop)
* ``exocortex modules [...]``       — inspect registered plugin modules

Built on :mod:`argparse` to avoid pulling in click/typer — every subcommand is
small and the surface fits cleanly in a single file.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from exocortex.core.db.migrations import (
    MigrationError,
    migrate_status,
    migrate_up,
)
from exocortex.init_cmd import add_init_subparser

logger = logging.getLogger("exocortex.cli")


def _print(*parts: object) -> None:
    """Tiny indirection so tests can capture stdout cleanly via capsys."""
    print(*parts)


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------


def _cmd_migrate_up(args: argparse.Namespace) -> int:
    schema_dir = Path(args.schema_dir) if args.schema_dir else None
    try:
        applied = migrate_up(schema_dir=schema_dir, dry_run=args.dry_run)
    except MigrationError as exc:
        _print(f"ERROR: {exc}")
        return 2

    label = "would apply" if args.dry_run else "applied"
    if not applied:
        _print("nothing to do — database is up to date.")
        return 0
    _print(f"{label} {len(applied)} migration(s):")
    for name in applied:
        _print(f"  + {name}")
    return 0


def _cmd_migrate_status(args: argparse.Namespace) -> int:
    schema_dir = Path(args.schema_dir) if args.schema_dir else None
    try:
        status = migrate_status(schema_dir=schema_dir)
    except MigrationError as exc:
        _print(f"ERROR: {exc}")
        return 2

    _print(f"applied: {len(status.applied)}")
    for name in status.applied:
        _print(f"  ✓ {name}")
    _print(f"pending: {len(status.pending)}")
    for name in status.pending:
        _print(f"  · {name}")
    if status.drift:
        _print(f"drift:   {len(status.drift)} (hash mismatch on disk)")
        for name in status.drift:
            _print(f"  ! {name}")
        return 3
    return 0


# ---------------------------------------------------------------------------
# ingest / synth / compile — delegate to module main()s
# ---------------------------------------------------------------------------


def _cmd_ingest(args: argparse.Namespace) -> int:
    if args.from_path:
        # The worker reads VAULT_PATH / EXOCORTEX_VAULT_PATH from env at call
        # time (in `exocortex.workers.ingest._meeting_notes_dir`).
        vault_path_str = str(Path(args.from_path).expanduser().resolve())
        os.environ["EXOCORTEX_VAULT_PATH"] = vault_path_str
        os.environ["VAULT_PATH"] = vault_path_str  # backward compat
    extra: list[str] = []
    if args.dry_run:
        extra.append("--dry-run")
    if args.limit is not None:
        extra.extend(["--limit", str(args.limit)])
    from exocortex.workers.ingest import main as _ingest_main
    return _ingest_main(extra) or 0


def _cmd_synth(args: argparse.Namespace) -> int:
    extra: list[str] = []
    if args.perspective:
        extra.extend(["--perspective", args.perspective])
    if args.domain:
        extra.extend(["--domain", args.domain])
    if args.key:
        extra.extend(["--key", args.key])
    if args.all:
        extra.append("--all")
    if args.dry_run:
        extra.append("--dry-run")
    if args.limit is not None:
        extra.extend(["--limit", str(args.limit)])
    if args.cost_stop is not None:
        extra.extend(["--cost-stop", str(args.cost_stop)])
    from exocortex.workers.synth import main as _synth_main
    return _synth_main(extra) or 0


def _cmd_compile(args: argparse.Namespace) -> int:
    # Wiki compiler exposes a proper ``python -m exocortex.wiki`` entry-point,
    # so we just delegate to it — keeps argparse compatibility intact.
    from exocortex.wiki.__main__ import main as wiki_main  # local import: heavy

    extra: list[str] = []
    if args.domain:
        extra.extend(["--domain", args.domain])
    if args.dry_run:
        extra.append("--dry-run")
    if args.full_rebuild:
        extra.append("--full-rebuild")
    if args.list_domains:
        extra.append("--list-domains")
    saved_argv = sys.argv
    sys.argv = ["exocortex.wiki", *extra]
    try:
        try:
            wiki_main()
        except SystemExit as exc:
            return int(exc.code or 0)
        return 0
    finally:
        sys.argv = saved_argv


# ---------------------------------------------------------------------------
# serve / query
# ---------------------------------------------------------------------------


def _cmd_serve(args: argparse.Namespace) -> int:
    """Start the capture API on uvicorn.

    Equivalent to:
        uvicorn exocortex.capture_api:app --host HOST --port PORT
    """
    try:
        import uvicorn
    except ImportError:
        _print("ERROR: uvicorn is required — install with `pip install exocortex`")
        return 2

    uvicorn.run(
        "exocortex.capture_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    """Ad-hoc GraphRAG query — wrapper around the MCP `ask` tool, usable
    without Claude Desktop or an MCP client."""
    try:
        from exocortex.graph_rag import TENANT_ID, GraphRAGOrchestrator
    except Exception as exc:  # pragma: no cover - import-time misconfig  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
        _print(f"ERROR: graph_rag unavailable: {exc}")
        return 2

    orch = GraphRAGOrchestrator(tenant_id=TENANT_ID)
    ans = orch.answer(
        args.question,
        max_hops=args.hops,
        top_k_vector=args.top_k,
        use_cache=not args.no_cache,
        query_source="exocortex_cli",
    )

    if args.json:
        import json
        payload = {
            "question": ans.question,
            "response": ans.response,
            "sources": [
                {
                    "thought_id": s.thought_id,
                    "title": s.title,
                    "score": s.score,
                    "rank_vector": s.rank_vector,
                    "rank_graph": s.rank_graph,
                }
                for s in ans.sources
            ],
        }
        _print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    _print(ans.response)
    if ans.sources:
        _print("\nSources:")
        for s in ans.sources:
            _print(f"  - {s.title or s.thought_id}  (score={s.score:.3f})")
    return 0


# ---------------------------------------------------------------------------
# modules — introspect / disable / render systemd & compose snippets
# ---------------------------------------------------------------------------


_MODULE_EXTENSION_POINTS: tuple[tuple[str, str], ...] = (
    ("perspectives", "perspectives"),
    ("mcp_tools", "mcp_tools"),
    ("compile_domains", "compile_domains"),
    ("capture_processors", "capture_processors"),
    ("live_sections", "live_sections"),
    ("sinks", "sinks"),
)


def _discovered_registry():
    """Return the singleton registry, running discovery once.

    The registry is module-level and discovery is non-idempotent, so we guard
    against double-registration with a function attribute flag.
    """
    from exocortex.core.registry import registry

    if not getattr(_discovered_registry, "_done", False):
        try:
            registry.discover()
        except Exception as exc:  # pragma: no cover - discovery is best-effort  # noqa: BLE001 — best-effort fallback; narrowing would change behavior
            log_err = logging.getLogger("exocortex.cli.modules")
            log_err.warning("plugin discovery raised: %s", exc)
        _discovered_registry._done = True  # type: ignore[attr-defined]
    return registry


def _module_entries(registry) -> list[tuple[str, str, str]]:
    """Flatten the registry into ``(type, name, source)`` rows."""
    rows: list[tuple[str, str, str]] = []
    for attr, label in _MODULE_EXTENSION_POINTS:
        bucket: dict[str, object] = getattr(registry, attr, {}) or {}
        for name, obj in bucket.items():
            source = f"{type(obj).__module__}.{type(obj).__name__}"
            rows.append((label, name, source))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


def _print_table(rows: Sequence[tuple[str, ...]], headers: tuple[str, ...]) -> None:
    cols = list(zip(*([headers, *rows] if rows else [headers])))
    widths = [max(len(str(cell)) for cell in col) for col in cols]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    _print(fmt.format(*headers))
    _print(fmt.format(*["-" * w for w in widths]))
    for row in rows:
        _print(fmt.format(*row))


def _cmd_modules_list(args: argparse.Namespace) -> int:
    registry = _discovered_registry()
    rows = _module_entries(registry)
    if not rows:
        _print("no modules registered.")
        return 0
    _print_table(rows, ("TYPE", "NAME", "SOURCE"))
    return 0


def _cmd_modules_status(args: argparse.Namespace) -> int:
    registry = _discovered_registry()
    rows = _module_entries(registry)
    counts: dict[str, int] = {}
    for type_label, _name, _src in rows:
        counts[type_label] = counts.get(type_label, 0) + 1

    _print("registry loaded OK")
    _print("")
    _print_table(
        [(label, str(counts.get(label, 0))) for _attr, label in _MODULE_EXTENSION_POINTS],
        ("TYPE", "COUNT"),
    )

    # Best-effort migration status surface — silent if PG unreachable.
    # Passing schema_dir=None lets ``migrate_status`` resolve the default
    # (repo-root schema/ for editable installs, _bundled/schema for wheels).
    try:
        mig_status = migrate_status(schema_dir=None)
        _print("")
        _print(f"migrations: applied={len(mig_status.applied)} "
               f"pending={len(mig_status.pending)} drift={len(mig_status.drift)}")
    except Exception:  # noqa: BLE001, S110 — failure is ignored on purpose; narrowing would change behavior
        # Migration status is informational — never block `modules status`.
        pass
    return 0


def _config_yaml_path() -> Path:
    """Resolve the writable ``config/exocortex.yaml`` path.

    Prefers a ``config/`` directory in CWD (operator's working dir, both
    dev-checkout and wheel-install cases) and falls back to the package
    parent (editable install) if CWD has nothing.
    """
    cwd_candidate = Path.cwd() / "config" / "exocortex.yaml"
    if cwd_candidate.exists() or (Path.cwd() / "config").is_dir():
        return cwd_candidate
    pkg_parent = Path(__file__).resolve().parent.parent
    return pkg_parent / "config" / "exocortex.yaml"


def _cmd_modules_disable(args: argparse.Namespace) -> int:
    name = args.name
    cfg_path = _config_yaml_path()
    if not cfg_path.exists():
        _print(f"ERROR: config file not found: {cfg_path}")
        return 1

    text = cfg_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Locate (or append) a top-level ``disabled_modules:`` list. Minimal YAML
    # mutation — no PyYAML dependency, list members written as ``  - name``.
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.rstrip()
        if stripped == "disabled_modules:" or stripped.startswith("disabled_modules:"):
            header_idx = i
            break

    if header_idx is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append("disabled_modules:")
        lines.append(f"  - {name}")
    else:
        # Find existing list members (lines that start with `  - `) following
        # the header; bail out if already disabled.
        insert_at = header_idx + 1
        while insert_at < len(lines):
            ln = lines[insert_at]
            if ln.startswith("  - "):
                if ln.strip() == f"- {name}":
                    _print(f"already disabled: {name}")
                    return 0
                insert_at += 1
                continue
            break
        lines.insert(insert_at, f"  - {name}")

    cfg_path.write_text("\n".join(lines) + ("\n" if not text.endswith("\n") else ""),
                        encoding="utf-8")
    _print(f"disabled: {name}")
    return 0


_SYSTEMD_TEMPLATE = """\
[Unit]
Description=Exocortex {label}
After=network-online.target

[Service]
Type=oneshot
User=exocortex
ExecStart=/usr/bin/exocortex {invocation}
Environment=EXOCORTEX_VAULT_PATH=/var/lib/exocortex/vault
Environment=DATABASE_URL=postgresql://exocortex@localhost/exocortex
NoNewPrivileges=yes
ProtectHome=read-only
ProtectSystem=strict
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
"""


def _cmd_modules_render_systemd(args: argparse.Namespace) -> int:
    module = args.module
    registry = _discovered_registry()
    if module is None:
        _print(_SYSTEMD_TEMPLATE.format(
            label="worker (generic template)",
            invocation="<subcommand>  # TODO: fill in actual exocortex subcommand",
        ))
        return 0

    # Look the name up across all extension points.
    for attr, label in _MODULE_EXTENSION_POINTS:
        bucket: dict[str, object] = getattr(registry, attr, {}) or {}
        if module in bucket:
            _print(_SYSTEMD_TEMPLATE.format(
                label=f"{label}:{module}",
                invocation=f"run-module {label} {module}",
            ))
            return 0

    _print(f"# TODO: module '{module}' not found in registry — generic template below")
    _print(_SYSTEMD_TEMPLATE.format(
        label=f"unknown module '{module}'",
        invocation=f"run-module <type> {module}  # TODO: confirm type",
    ))
    return 0


def _cmd_modules_render_compose(args: argparse.Namespace) -> int:
    registry = _discovered_registry()
    rows = _module_entries(registry)
    image = "ghcr.io/hretheum/exocortex:latest"

    out: list[str] = []
    out.append("services:")
    if not rows:
        out.append("  exocortex:")
        out.append(f"    image: {image}")
        out.append("    environment:")
        out.append("      EXOCORTEX_VAULT_PATH: ${EXOCORTEX_VAULT_PATH}")
        out.append("      DATABASE_URL: ${DATABASE_URL}")
        out.append("      TENANT_ID: ${TENANT_ID}")
        _print("\n".join(out))
        return 0

    for type_label, name, _source in rows:
        svc = f"{type_label}-{name}".replace("_", "-").replace(".", "-")
        out.append(f"  {svc}:")
        out.append(f"    image: {image}")
        out.append(f"    command: [\"run-module\", \"{type_label}\", \"{name}\"]")
        out.append("    environment:")
        out.append("      EXOCORTEX_VAULT_PATH: ${EXOCORTEX_VAULT_PATH}")
        out.append("      DATABASE_URL: ${DATABASE_URL}")
        out.append("      TENANT_ID: ${TENANT_ID}")
        out.append("    restart: unless-stopped")
    _print("\n".join(out))
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


_EPILOG = """\
Examples:
  exocortex init                            # scaffold config from bundled examples
  exocortex migrate up                      # apply pending schema migrations
  exocortex ingest --from ~/Documents/vault # bulk-ingest a vault directory
  exocortex synth --all --cost-stop 1.50    # run synthesizer with budget guard
  exocortex compile --domain work --dry-run
  exocortex serve --port 8000               # start capture API
  exocortex query "what did we agree on Q4 remediation?"

Run ``exocortex <command> --help`` for command-specific options.
"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="exocortex",
        description="Exocortex CLI — operate the personal-knowledge engine.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging on stderr.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    add_init_subparser(subparsers)

    # migrate
    migrate = subparsers.add_parser(
        "migrate", help="Schema migration commands.",
        description="Apply or inspect Postgres schema migrations.",
    )
    migrate_sub = migrate.add_subparsers(dest="migrate_command", required=True)

    up = migrate_sub.add_parser(
        "up", help="Apply all pending migrations.",
        epilog="Example:\n  exocortex migrate up --dry-run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    up.add_argument("--schema-dir", help="Directory of *.sql migrations (default: ./schema).")
    up.add_argument("--dry-run", action="store_true",
                    help="Show what would be applied without changing the database.")
    up.set_defaults(func=_cmd_migrate_up)

    status = migrate_sub.add_parser(
        "status", help="Show applied / pending migrations.",
        epilog="Example:\n  exocortex migrate status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    status.add_argument("--schema-dir", help="Directory of *.sql migrations (default: ./schema).")
    status.set_defaults(func=_cmd_migrate_status)

    # ingest
    ingest = subparsers.add_parser(
        "ingest",
        help="Bulk-ingest vault notes into the thoughts table.",
        description="Bulk-ingest a vault directory of Markdown notes.",
        epilog=(
            "Example:\n"
            "  exocortex ingest --from ~/Documents/prv-sync\n"
            "  exocortex ingest --from . --dry-run --limit 5\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ingest.add_argument("--from", dest="from_path", required=False,
                        help="Vault root path (sets VAULT_PATH for the worker). "
                             "Falls back to $VAULT_PATH / $EXOCORTEX_VAULT_PATH if omitted.")
    ingest.add_argument("--dry-run", action="store_true",
                        help="Parse and classify but do not write to Postgres.")
    ingest.add_argument("--limit", type=int, default=None,
                        help="Process at most N notes (smoke testing).")
    ingest.set_defaults(func=_cmd_ingest)

    # synth
    synth = subparsers.add_parser(
        "synth",
        help="Run the LLM synthesizer over selected perspectives.",
        description="Run the synthesizer (LLM perspectives → syntheses table).",
        epilog=(
            "Examples:\n"
            "  exocortex synth --all --cost-stop 1.50\n"
            "  exocortex synth --perspective client --key acme\n"
            "  exocortex synth --dry-run --limit 3\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    synth.add_argument("--perspective", help="Perspective type (e.g. client, project, person).")
    synth.add_argument("--domain", help="Restrict to a single domain (work/news/frp/...).")
    synth.add_argument("--key", help="Single key within the perspective (e.g. client slug).")
    synth.add_argument("--all", action="store_true", help="Run every eligible perspective.")
    synth.add_argument("--dry-run", action="store_true",
                       help="Show what would be synthesized without LLM calls.")
    synth.add_argument("--limit", type=int, default=None,
                       help="Cap the number of perspectives processed.")
    synth.add_argument("--cost-stop", type=float, default=None,
                       help="Abort the run once cumulative LLM cost exceeds this USD value.")
    synth.set_defaults(func=_cmd_synth)

    # compile
    compile_p = subparsers.add_parser(
        "compile",
        help="Compile syntheses into Markdown wiki pages.",
        description="Compile syntheses + raw thoughts into the Obsidian-shaped wiki.",
        epilog=(
            "Examples:\n"
            "  exocortex compile --domain news --dry-run\n"
            "  exocortex compile --domain all --full-rebuild\n"
            "  exocortex compile --list-domains\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    compile_p.add_argument("--domain", help="Domain to compile (work/news/frp/all/...).")
    compile_p.add_argument("--dry-run", action="store_true",
                           help="Render but do not write to the vault.")
    compile_p.add_argument("--full-rebuild", action="store_true",
                           help="Wipe and regenerate every page in the selected domain.")
    compile_p.add_argument("--list-domains", action="store_true",
                           help="Print configured domains and exit.")
    compile_p.set_defaults(func=_cmd_compile)

    # serve
    serve = subparsers.add_parser(
        "serve",
        help="Start the capture API (FastAPI on uvicorn).",
        description="Run the capture API exposing /capture, /mcp, /graph/expand, /health.",
        epilog=(
            "Examples:\n"
            "  exocortex serve\n"
            "  exocortex serve --port 8001 --host 127.0.0.1\n"
            "  exocortex serve --reload   # dev mode\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    serve.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"),
                       help="Bind host (default: 127.0.0.1).")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")),
                       help="Bind port (default: 8000).")
    serve.add_argument("--reload", action="store_true",
                       help="Enable uvicorn auto-reload (development only).")
    serve.set_defaults(func=_cmd_serve)

    # query
    query = subparsers.add_parser(
        "query",
        help="Ad-hoc GraphRAG query (no MCP client required).",
        description="One-shot GraphRAG question, using the same retrieval + LLM "
                    "stack as the MCP `ask` tool.",
        epilog=(
            "Examples:\n"
            "  exocortex query \"what did we agree on Q4 remediation?\"\n"
            "  exocortex query \"who owns the GLOBEX pipeline?\" --json\n"
            "  exocortex query \"recent decisions\" --hops 3 --top-k 20\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    query.add_argument("question", help="Natural-language question.")
    query.add_argument("--top-k", dest="top_k", type=int, default=10,
                       help="Vector search top-K (default: 10).")
    query.add_argument("--hops", type=int, default=2,
                       help="Max graph hops (default: 2).")
    query.add_argument("--no-cache", action="store_true",
                       help="Bypass the in-memory answer cache.")
    query.add_argument("--json", action="store_true",
                       help="Emit JSON instead of the human-formatted view.")
    query.set_defaults(func=_cmd_query)

    # modules
    modules = subparsers.add_parser(
        "modules",
        help="Introspect and operate on registered plugin modules.",
        description="List, disable, and render deployment snippets for plugin modules.",
        epilog=(
            "Examples:\n"
            "  exocortex modules list\n"
            "  exocortex modules status\n"
            "  exocortex modules disable news_cluster\n"
            "  exocortex modules render-systemd night_shift\n"
            "  exocortex modules render-compose\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    modules_sub = modules.add_subparsers(dest="modules_cmd", required=True)

    m_list = modules_sub.add_parser("list", help="List all registered modules.")
    m_list.set_defaults(func=_cmd_modules_list)

    m_status = modules_sub.add_parser(
        "status", help="Show module counts per type + registry health.",
    )
    m_status.set_defaults(func=_cmd_modules_status)

    m_disable = modules_sub.add_parser(
        "disable", help="Add a module name to disabled_modules in config/exocortex.yaml.",
    )
    m_disable.add_argument("name", help="Module name (e.g. 'news_cluster').")
    m_disable.set_defaults(func=_cmd_modules_disable)

    m_systemd = modules_sub.add_parser(
        "render-systemd",
        help="Print a systemd .service snippet (generic, or for a named module).",
    )
    m_systemd.add_argument("module", nargs="?", default=None,
                           help="Optional module name to template.")
    m_systemd.set_defaults(func=_cmd_modules_render_systemd)

    m_compose = modules_sub.add_parser(
        "render-compose",
        help="Print a docker-compose snippet covering all registered workers.",
    )
    m_compose.set_defaults(func=_cmd_modules_render_compose)

    # lab: everything after the word goes to exocortex.lab.cli
    lab = subparsers.add_parser(
        "lab", add_help=False,
        help="Lab jobs: experiments on public data (see `exocortex lab --help`).",
    )
    lab.add_argument("lab_args", nargs=argparse.REMAINDER)
    lab.set_defaults(func=_cmd_lab)

    return parser


def _cmd_lab(args: argparse.Namespace) -> int:
    from exocortex.lab.cli import main as lab_main

    return lab_main(args.lab_args)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["lab"]:
        # passed through whole, so `exocortex lab --help` reaches the lab parser
        from exocortex.lab.cli import main as lab_main

        return lab_main(argv[1:])
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
