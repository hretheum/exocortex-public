"""Extract Polish comments, docstrings and developer-facing messages, and apply translations.

Fragments are identified by (file, kind, raw source, occurrence index), so the
tool never needs byte offsets. Only text changes: after applying, the Python
syntax tree is compared with the original with translated strings masked, and
the change is refused if anything else differs.

User-facing output (LLM prompts, generated wiki text, bot replies) is not
extracted: that is product content in its own language, not code.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import libcst as cst

from .detect import is_polish

LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
HELP_KWARGS = {"help", "description", "epilog", "usage"}
HASH_COMMENT_SUFFIXES = {".sh", ".service", ".timer", ".container", ".yaml", ".yml", ".toml", ".cfg", ".ini",
                         ".conf", ".network", ".volume", ".txt", ".example", ""}
SQL_SUFFIXES = {".sql"}


class _Collector(cst.CSTVisitor):
    def __init__(self, module: cst.Module):
        self.module = module
        self.found: list[tuple[str, str]] = []  # (kind, raw)
        self._docstring_nodes: set[int] = set()

    def _code(self, node: cst.CSTNode) -> str:
        return self.module.code_for_node(node)

    def _maybe_docstring(self, body) -> None:
        stmts = getattr(body, "body", body)
        if not stmts:
            return
        first = stmts[0]
        if isinstance(first, cst.SimpleStatementLine) and first.body and isinstance(first.body[0], cst.Expr):
            val = first.body[0].value
            if isinstance(val, (cst.SimpleString, cst.ConcatenatedString)):
                self._docstring_nodes.add(id(val))
                self.found.append(("docstring", self._code(val)))

    def visit_Module(self, node: cst.Module) -> None:
        self._maybe_docstring(node.body)

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self._maybe_docstring(node.body)

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        self._maybe_docstring(node.body)

    def visit_Call(self, node: cst.Call) -> None:
        func = node.func
        name = func.attr.value if isinstance(func, cst.Attribute) else func.value if isinstance(func, cst.Name) else ""
        is_log = isinstance(func, cst.Attribute) and name in LOG_METHODS
        is_exc = name.endswith(("Error", "Exception", "Warning")) or name in {"print", "exit", "SystemExit", "abort"}
        for arg in node.args:
            string_like = isinstance(arg.value, (cst.SimpleString, cst.FormattedString, cst.ConcatenatedString))
            if not string_like:
                continue
            kw = arg.keyword.value if arg.keyword else None
            if (kw is None and (is_log or is_exc)) or kw in HELP_KWARGS:
                self.found.append(("message", self._code(arg.value)))


def _blocks(comments: list[tuple[int, str]]) -> list[tuple[str, str, bool]]:
    """Group comments on consecutive lines; a block is Polish if any line is.

    Returns (kind, raw, force) in source order. force=True marks lines that
    belong to a Polish block, so a block is never half translated.
    """
    out: list[tuple[str, str, bool]] = []
    block: list[tuple[int, str]] = []

    def flush():
        if not block:
            return
        polish = any(is_polish(raw) for _, raw in block)
        out.extend(("comment", raw, polish) for _, raw in block)
        block.clear()

    for lineno, raw in comments:
        if block and lineno != block[-1][0] + 1:
            flush()
        block.append((lineno, raw))
    flush()
    return out


def _py_comments(source: str) -> list[tuple[int, str]]:
    import io
    import tokenize

    out = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            out.append((tok.start[0], tok.string))
    return out


def _py_fragments(path: Path) -> list[tuple[str, str, bool]]:
    source = path.read_text(encoding="utf-8")
    module = cst.parse_module(source)
    c = _Collector(module)
    module.visit(c)
    return _blocks(_py_comments(source)) + [(k, r, False) for k, r in c.found]


def _line_comment_fragments(path: Path, prefix: str) -> list[tuple[str, str, bool]]:
    comments = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith(prefix):
            comments.append((lineno, stripped))
        elif (" " + prefix + " ") in line and not stripped.startswith(("'", '"')):
            comments.append((lineno, line[line.find(" " + prefix + " ") + 1 :]))
    return _blocks(comments)


def fragments_for(path: Path) -> list[tuple[str, str, bool]]:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return _py_fragments(path)
    if suffix in SQL_SUFFIXES:
        return _line_comment_fragments(path, "--")
    if path.name in ("Dockerfile", "Caddyfile", "crontab") or suffix in HASH_COMMENT_SUFFIXES or path.name.endswith(".Dockerfile"):
        return _line_comment_fragments(path, "#")
    return []


def extract(paths: list[Path], root: Path) -> list[dict]:
    items = []
    for base in paths:
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        for f in files:
            if "__pycache__" in f.parts:
                continue
            try:
                frags = fragments_for(f)
            except (UnicodeDecodeError, cst.ParserSyntaxError):
                continue
            seen: dict[tuple[str, str], int] = defaultdict(int)
            for kind, raw, force in frags:
                occ = seen[(kind, raw)]
                seen[(kind, raw)] += 1
                if force or is_polish(raw):
                    items.append({"file": f.relative_to(root).as_posix(), "kind": kind, "occ": occ,
                                  "raw": raw, "translation": None})
    return items


class _Applier(cst.CSTTransformer):
    def __init__(self, module: cst.Module, mapping: dict[tuple[str, int], str]):
        self.module = module
        self.mapping = mapping  # (raw, occurrence) -> new raw
        self.counts: dict[str, int] = defaultdict(int)
        self.applied = 0

    def _next(self, raw: str) -> str | None:
        occ = self.counts[raw]
        self.counts[raw] += 1
        return self.mapping.get((raw, occ))

    def leave_Comment(self, original, updated):
        new = self._next(original.value)
        if new is None:
            return updated
        self.applied += 1
        return updated.with_changes(value=new)

    def _string(self, original, updated):
        raw = self.module.code_for_node(original)
        new = self._next(raw)
        if new is None:
            return updated
        self.applied += 1
        return cst.parse_expression(new)

    leave_SimpleString = _string
    leave_FormattedString = _string

    def leave_ConcatenatedString(self, original, updated):
        return self._string(original, updated)


def _masked_dump(source: str, masked: set[str]) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = "<str>"
        if isinstance(node, ast.JoinedStr):
            node.values = [v if isinstance(v, ast.FormattedValue) else ast.Constant("<str>") for v in node.values]
    return ast.dump(tree, include_attributes=False)


def apply(items: list[dict], root: Path) -> dict[str, int]:
    by_file: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        if it.get("translation"):
            by_file[it["file"]].append(it)
    report = {}
    for rel, its in by_file.items():
        path = root / rel
        src = path.read_text(encoding="utf-8")
        if path.suffix == ".py":
            mapping = {(it["raw"], it["occ"]): it["translation"] for it in its}
            module = cst.parse_module(src)
            applier = _Applier(module, mapping)
            new_src = module.visit(applier).code
            if _masked_dump(src, set()) != _masked_dump(new_src, set()):
                raise RuntimeError(f"{rel}: syntax tree changed beyond strings and comments")
            path.write_text(new_src, encoding="utf-8")
            report[rel] = applier.applied
        else:
            lines = src.split("\n")
            counts: dict[str, int] = defaultdict(int)
            mapping = {(it["raw"], it["occ"]): it["translation"] for it in its}
            applied = 0
            for i, line in enumerate(lines):
                for (raw, occ), new in mapping.items():
                    if raw in line:
                        if counts[raw] == occ:
                            lines[i] = line.replace(raw, new, 1)
                            applied += 1
                        counts[raw] += 1
                        break
            path.write_text("\n".join(lines), encoding="utf-8")
            report[rel] = applied
    return report
