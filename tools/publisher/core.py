"""Publisher: the only path from the vault folder to the public repository.

One run:

1. stop if the gate lock file exists (the nightly self-test failed);
2. find files that differ between the source folder and the repository copy;
3. build the would-be tree (repository copy plus the changes) in a staging
   directory and run every check on it: leakgate on each changed file,
   the private corpus comparison (simcheck), the pl/en parity check, the
   header schemas and the language check; files marked ``translation: machine`` are held too;
4. copy only the files that passed into the repository, commit them in one
   commit, check the commit metadata with leakgate and push;
5. append a line to the run log and send a notification about held files.

A Markdown file whose header says ``publish: false`` is not published
(a blind rating page while the rating is in progress, for example).

A second, optional source is the lab's output folder (``lab_source``). The
lab owns a few paths (LAB_OWNED: the preregistration registry, generated
pages and exported data); those come from the lab folder only and are
ignored in the vault. They go through exactly the same checks. Lab-owned
files are deleted in the repository only while the lab folder is present
and not empty, so an unmounted folder never wipes them.

Units of publication (roadmap task F1.12): an experiment is published as a
whole or not at all. Its unit is pl|en/experiments/<slug>/**,
data/<slug>/** and the registry lines with its slug. If any part is held,
or the experiment would be incomplete (a file without its other language
version, a registry line without its card, a removal from the vault while
its data wait for an unmounted lab folder), no part of it is copied,
deleted or appended, and every path gets a reason. Every other file is a
unit together with its language pair. The public registry is built from
lines: the lines of experiments that passed are appended at the end, in
the order of publication. The source must keep every published line
unchanged (the registry only grows); otherwise nothing is appended.

Every path has a publication class (classes.py): project documentation,
experiment, generated page or unknown. The run log records the class of
every file the run touched, a dry run lists the class of every file, and a
file of the unknown class raises an alarm in the notification. Each file
gets the checks of its class (``CHECKS`` in classes.py). Project
documentation skips the semantic comparison. Scanner warnings in it do not
hold it; they go to the run log (``warnings``).

Held files keep their previously published version. The run log records
rule names and paths only, never matched text.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .classes import (
    EXPERIMENT,
    LANGS,
    LANGUAGE,
    LITERAL_BLOCK,
    LITERAL_WARN,
    PARITY,
    REGISTRY,
    SCHEMA,
    SEMANTIC,
    TRANSLATION,
    UNKNOWN,
    checks_for,
    classify_file,
    experiment_slug,
)

IGNORED = {".DS_Store", ".obsidian", ".trash", ".stfolder", ".stversions", ".git"}
LAB_OWNED = (REGISTRY, "pl/generated/", "en/generated/", "data/")


def lab_owned(rel: str) -> bool:
    return any(rel == p or (p.endswith("/") and rel.startswith(p)) for p in LAB_OWNED)


@dataclass
class Settings:
    source: Path                 # vault folder, e.g. ~/vault/_source/dowody
    repo: Path                   # working copy of the public repository
    subdir: str = "dowody"       # where the folder lives inside the repository
    lock_file: Path | None = None
    log_file: Path | None = None
    simcheck_url: str | None = None  # http://127.0.0.1:8099
    push: bool = False
    remote: str = "origin"
    branch: str = "main"
    author: str = "Exocortex publisher <publisher@users.noreply.github.com>"
    dry_run: bool = False
    hashes: Path | None = None       # hashed denylist; default: the one shipped with leakgate
    lab_source: Path | None = None   # the lab's output folder (registry, generated pages, data)


@dataclass
class RunResult:
    status: str = "ok"           # ok | locked | nothing | held-only | error
    published: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    held: dict[str, list[str]] = field(default_factory=dict)
    commit: str | None = None
    pushed: bool = False
    classes: dict[str, str] = field(default_factory=dict)  # path -> publication class (every file in a dry run)
    warnings: dict[str, list[str]] = field(default_factory=dict)  # scanner findings that do not hold the file

    def to_dict(self) -> dict:
        return {
            "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "status": self.status,
            "published": self.published,
            "deleted": self.deleted,
            "held": self.held,
            "commit": self.commit,
            "pushed": self.pushed,
            "classes": self.classes,
            "warnings": self.warnings,
        }


def _files(root: Path) -> dict[str, str]:
    out = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file() or any(part in IGNORED for part in p.relative_to(root).parts):
            continue
        out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def diff(source: Path, published: Path) -> tuple[list[str], list[str]]:
    """(changed or new, deleted) relative paths."""
    src, pub = _files(source), _files(published)
    changed = sorted(k for k, v in src.items() if pub.get(k) != v)
    deleted = sorted(k for k in pub if k not in src)
    return changed, deleted


_NOT_PUBLISHED = re.compile(r"\A---\n(?:.*\n)*?publish:\s*false\s*\n(?:.*\n)*?---\n")


def unpublished(path: Path) -> bool:
    """A Markdown file whose header says ``publish: false`` (e.g. a rating page in progress) stays in the vault."""
    if path.suffix != ".md":
        return False
    with path.open("rb") as fh:
        head = fh.read(4096).decode("utf-8", errors="ignore")
    return bool(_NOT_PUBLISHED.match(head))


def origins(settings: Settings) -> dict[str, Path]:
    """Where each file to publish comes from: the vault, or the lab folder for lab-owned paths."""
    out = {rel: settings.source / rel for rel in _files(settings.source)
           if not lab_owned(rel) and not unpublished(settings.source / rel)}
    lab = settings.lab_source
    if lab is not None and lab.is_dir():
        out.update({rel: lab / rel for rel in _files(lab) if lab_owned(rel)})
    return out


def _lab_present(settings: Settings) -> bool:
    lab = settings.lab_source
    return lab is not None and bool(_files(lab))  # at least one file: empty dirs may mean "not mounted"


def _lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip()]


def _line_slug(line: str) -> str | None:
    """The experiment a registry line belongs to, or None if the line cannot be read."""
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    slug = entry.get("slug") if isinstance(entry, dict) else None
    return slug if isinstance(slug, str) and experiment_slug(f"data/{slug}/x") == slug else None


@dataclass
class Registry:
    """The public registry and what the source adds to it, line by line."""

    published: list[str]  # lines of the public registry, in the order of publication
    new: list[str]        # lines of the source that are not public yet, in the source's order
    dropped: list[str]    # public lines the source no longer has unchanged

    @classmethod
    def read(cls, published: Path, source: Path | None) -> Registry:
        pub = _lines(published.read_text(encoding="utf-8")) if published.is_file() else []
        src = _lines(source.read_text(encoding="utf-8")) if source is not None and source.is_file() else []
        seen, new = set(pub), []
        for ln in src:
            if ln not in seen:
                seen.add(ln)
                new.append(ln)
        have = set(src)
        return cls(pub, new, [ln for ln in pub if ln not in have])


def plan(settings: Settings) -> tuple[list[str], list[str], dict[str, Path]]:
    """(changed or new, deleted, origin of every source file).

    The registry counts as changed when the source has lines that are not
    public yet or lost a public line; its order and blank lines do not count.
    """
    origin = origins(settings)
    pub = _files(settings.repo / settings.subdir)
    changed = sorted(rel for rel, path in origin.items()
                     if rel != REGISTRY and pub.get(rel) != hashlib.sha256(path.read_bytes()).hexdigest())
    if REGISTRY in origin:
        reg = Registry.read(settings.repo / settings.subdir / REGISTRY, origin[REGISTRY])
        if reg.new or reg.dropped:
            changed = sorted([*changed, REGISTRY])
    lab_present = _lab_present(settings)
    deleted = sorted(rel for rel in pub if rel not in origin and (not lab_owned(rel) or lab_present))
    return changed, deleted, origin


def _pair_key(rel: str) -> str:
    parts = rel.split("/", 1)
    return parts[1] if len(parts) == 2 and parts[0] in ("pl", "en") else rel


def _hold(res: RunResult, rel: str, reason: str) -> None:
    res.held.setdefault(rel, [])
    if reason not in res.held[rel]:
        res.held[rel].append(reason)


def _note(res: RunResult, rel: str, reason: str) -> None:
    res.warnings.setdefault(rel, [])
    if reason not in res.warnings[rel]:
        res.warnings[rel].append(reason)


def check_registry(registry: Registry | None, removed: bool, settings: Settings, res: RunResult,
                   denylist=None) -> tuple[dict[str, list[str]], set[str]]:
    """Checks of the registry lines a run would append.

    Returns the new lines grouped by experiment slug and the slugs whose
    lines are held. The registry only grows: if the source dropped the file
    or lost or changed a public line, nothing is appended. A line that
    cannot be read is held on its own. Every new line goes through the
    literal scanner, and so does the registry as it would be published, for
    anything found only across lines.
    """
    from tools.leakgate.denylist import Denylist, load_key
    from tools.leakgate.scan import BLOCK, DATA_DIR, WARN, Config, Scanner

    by_slug: dict[str, list[str]] = {}
    held: set[str] = set()
    if removed:
        _hold(res, REGISTRY, "registry: may not be removed")
    if registry is None:
        return by_slug, held
    for ln in registry.new:
        slug = _line_slug(ln)
        if slug is None:
            _hold(res, REGISTRY, "registry: a line without a readable slug")
        else:
            by_slug.setdefault(slug, []).append(ln)
    if registry.dropped:
        _hold(res, REGISTRY, "registry: published lines changed or removed")
        held |= set(by_slug)
    checks = checks_for(EXPERIMENT)
    if not by_slug or not checks & {LITERAL_BLOCK, LITERAL_WARN}:
        return by_slug, held
    if denylist is None:
        denylist = Denylist.load(settings.hashes or DATA_DIR / "denylist.hmac.json", load_key())
    scanner = Scanner(denylist, Config.load())

    def holds(f) -> bool:
        return (f.tier == BLOCK and LITERAL_BLOCK in checks) or (f.tier == WARN and LITERAL_WARN in checks)

    seen: set[tuple[str, str]] = set()
    for slug, lines in by_slug.items():
        for ln in lines:
            for f in scanner.scan_bytes(REGISTRY, (ln + "\n").encode()):
                seen.add((f.rule, f.digest))
                if holds(f):
                    _hold(res, REGISTRY, f"leakgate:{f.rule} (line of {slug})")
                    held.add(slug)
    whole = "".join(ln + "\n" for ln in registry.published + [ln for lines in by_slug.values() for ln in lines])
    for f in scanner.scan_bytes(REGISTRY, whole.encode()):
        if holds(f) and (f.rule, f.digest) not in seen:  # found only across lines: it cannot be told whose it is
            _hold(res, REGISTRY, f"leakgate:{f.rule}")
            held |= set(by_slug)
    return by_slug, held


def _card_problems(slug: str, lines: list[str], after: set[str]) -> list[str]:
    """A registry line needs both language versions of its card inside the experiment."""
    out = []
    for ln in lines:
        entry = json.loads(ln)
        files = entry.get("files") if isinstance(entry.get("files"), dict) else {}
        for lang in LANGS:
            card = files.get(lang)
            if not (isinstance(card, str) and card.startswith(f"{lang}/") and experiment_slug(card) == slug
                    and card in after):
                out.append(f"incomplete: registry line of {slug} v{entry.get('version')} without its card ({lang})")
    return out


def hold_units(changed: list[str], deleted: list[str], published: set[str], public_lines: list[str],
               lines: dict[str, list[str]], held_lines: set[str], lab_present: bool, res: RunResult) -> set[str]:
    """Hold a whole experiment when any part of it is held or it would be incomplete; returns the held slugs.

    ``published`` holds the public paths, ``public_lines`` the public registry
    and ``lines`` the new registry lines by slug.
    """
    units: dict[str, tuple[list[str], list[str]]] = {slug: ([], []) for slug in lines}
    for rel in changed + deleted:
        slug = experiment_slug(rel)
        if slug is not None:
            units.setdefault(slug, ([], []))[0 if rel in changed else 1].append(rel)
    held_slugs = set()
    for slug, (new, gone) in sorted(units.items()):
        before = {r for r in published if experiment_slug(r) == slug}
        after = (before | set(new)) - set(gone)
        reasons = []
        for rel in sorted(after):
            lang, _, rest = rel.partition("/")
            if lang in LANGS and f"{'en' if lang == 'pl' else 'pl'}/{rest}" not in after:
                reasons.append(f"incomplete: {'en' if lang == 'pl' else 'pl'}/{rest} missing")
        reasons += _card_problems(slug, [ln for ln in public_lines if _line_slug(ln) == slug] + lines.get(slug, []),
                                  after)
        vault_before = any(r.split("/")[0] in LANGS for r in before)
        vault_after = any(r.split("/")[0] in LANGS for r in after)
        if gone and vault_before and not vault_after and not lab_present and any(lab_owned(r) for r in after):
            reasons.append("incomplete: removed from the vault while its data wait for the lab folder")
        if not reasons and slug not in held_lines and not any(r in res.held for r in new):
            continue
        held_slugs.add(slug)
        for rel in new + gone:
            for why in reasons or ([] if rel in res.held else [f"unit held: experiment {slug}"]):
                _hold(res, rel, why)
        if lines.get(slug):
            _hold(res, REGISTRY, f"line of {slug} held with its experiment")
    return held_slugs


def check_changes(stage: Path, changed: list[str], settings: Settings, res: RunResult, denylist=None) -> None:
    """Run the checks of each file's class on the staged tree and record held files in ``res``.

    ``denylist`` replaces the one read from ``settings.hashes`` (the self-test
    plants canaries with a throwaway key).
    """
    from tools.humanlint.core import run as humanlint_run
    from tools.leakgate.denylist import Denylist, load_key
    from tools.leakgate.scan import DATA_DIR, BLOCK, WARN, Config, Scanner
    from tools.paritycheck.core import check as parity_check

    if denylist is None:
        denylist = Denylist.load(settings.hashes or DATA_DIR / "denylist.hmac.json", load_key())
    scanner = Scanner(denylist, Config.load(), stage)
    checks = {rel: checks_for(classify_file(rel, stage / rel)) for rel in changed}
    for rel in changed:
        data = (stage / rel).read_bytes()
        if checks[rel] & {LITERAL_BLOCK, LITERAL_WARN}:
            for f in scanner.scan_bytes(rel, data):
                if (f.tier == BLOCK and LITERAL_BLOCK in checks[rel]) or (f.tier == WARN and LITERAL_WARN in checks[rel]):
                    _hold(res, rel, f"leakgate:{f.rule}")
                elif f.tier in (BLOCK, WARN):
                    _note(res, rel, f"leakgate:{f.rule}")
        if TRANSLATION in checks[rel] and rel.endswith(".md") and b"\ntranslation: machine" in data:
            _hold(res, rel, "machine translation not reviewed")

    if settings.simcheck_url:
        import httpx

        for rel in changed:
            if SEMANTIC not in checks[rel] or not rel.endswith((".md", ".txt", ".yaml", ".yml", ".csv", ".json")):
                continue
            text = (stage / rel).read_text(encoding="utf-8", errors="ignore")
            try:
                r = httpx.post(settings.simcheck_url.rstrip("/") + "/check", json={"text": text},
                               timeout=float(os.environ.get("GATE_SIMCHECK_TIMEOUT", "900")))
                r.raise_for_status()
                if r.json().get("similar"):
                    _hold(res, rel, "simcheck:similar to private corpus")
            except httpx.HTTPError as exc:
                _hold(res, rel, f"simcheck unavailable ({type(exc).__name__})")

    changed_pairs = {_pair_key(r) for r in changed}
    parity = parity_check(stage)
    for p in parity.problems:
        if p.path in changed_pairs:
            for lang in ("pl", "en"):
                rel = f"{lang}/{p.path}"
                present = rel in changed or (stage / rel).exists()
                if present and PARITY in checks.get(rel, checks_for(classify_file(rel, stage / rel))):
                    _hold(res, rel, f"paritycheck:{p.check}")

    from tools.docschema.core import validate_text

    for rel in changed:
        if SCHEMA in checks[rel] and rel.endswith(".md"):
            for err in validate_text(rel, (stage / rel).read_text(encoding="utf-8")):
                _hold(res, rel, f"docschema:{err.field}")

    for rep in humanlint_run([stage]):
        rel = Path(rep.path).relative_to(stage).as_posix()
        if rel in changed and LANGUAGE in checks[rel] and not rep.ok:
            _hold(res, rel, "humanlint:" + ";".join(f.split(":")[0] for f in rep.failures))

    # a held file blocks its pair partner as well, so the two versions never diverge in public
    for rel in list(res.held):
        key = _pair_key(rel)
        if key != rel:
            for lang in ("pl", "en"):
                other = f"{lang}/{key}"
                if other != rel and other in changed:
                    _hold(res, other, f"pair partner held: {rel}")


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=check)


def ensure_checkout(repo: Path, remote_url: str, branch: str, subdir: str) -> None:
    """Keep ``repo`` as a checkout of ``subdir`` only, reset to the remote branch.

    The clone is partial (``--filter=blob:none``) and sparse (non-cone, only
    ``/<subdir>/``), so the file contents of the rest of the repository are
    never downloaded: the machine running the publisher holds the published
    documents and nothing else. Local state is always reset to the remote,
    so a push rejected in an earlier run is simply redone.
    """
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", "--sparse", remote_url, str(repo)],
                       check=True, capture_output=True, text=True)
        _git(repo, "sparse-checkout", "set", "--no-cone", f"/{subdir}/")
    _git(repo, "fetch", "-q", "origin", branch)
    _git(repo, "checkout", "-q", "-B", branch, f"origin/{branch}")
    _git(repo, "reset", "-q", "--hard", f"origin/{branch}")


def publish(settings: Settings) -> RunResult:
    res = RunResult()
    if settings.lock_file and settings.lock_file.exists():
        res.status = "locked"
        return res
    published_dir = settings.repo / settings.subdir
    changed, deleted, origin = plan(settings)
    listed = sorted(set(origin) | set(_files(published_dir))) if settings.dry_run else changed + deleted
    res.classes = {rel: classify_file(rel, origin.get(rel) or published_dir / rel) for rel in listed}
    if not changed and not deleted:
        res.status = "nothing"
        return res

    registry = Registry.read(published_dir / REGISTRY, origin.get(REGISTRY)) if REGISTRY in changed else None
    files = [rel for rel in changed if rel != REGISTRY]  # the registry is checked and built line by line
    with tempfile.TemporaryDirectory(prefix="publisher-") as tmp:
        stage = Path(tmp) / settings.subdir
        if published_dir.is_dir():
            shutil.copytree(published_dir, stage)
        else:
            stage.mkdir(parents=True)
        for rel in files:
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin[rel], stage / rel)
        for rel in deleted:
            (stage / rel).unlink()
        lines, held_lines = check_registry(registry, REGISTRY in deleted, settings, res)
        check_changes(stage, files, settings, res)
    public_lines = _lines((published_dir / REGISTRY).read_text(encoding="utf-8")) if (published_dir / REGISTRY).is_file() else []
    held_units = hold_units(files, deleted, set(_files(published_dir)), public_lines, lines, held_lines,
                            _lab_present(settings), res)
    appended = [ln for ln in (registry.new if registry else []) if _line_slug(ln) in lines
                and _line_slug(ln) not in held_units]

    ok = [r for r in files if r not in res.held] + ([REGISTRY] if appended else [])
    # deleting one half of a pair alone would break parity in public; keep pairs together
    del_ok = [r for r in deleted if r not in res.held and not any(_pair_key(h) == _pair_key(r) for h in res.held)]
    if not ok and not del_ok:
        res.status = "held-only"
        return res
    if settings.dry_run:
        res.published, res.deleted = sorted(ok), del_ok
        return res

    for rel in ok:
        dst = published_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel == REGISTRY:
            dst.write_text("".join(ln + "\n" for ln in registry.published + appended), encoding="utf-8")
        else:
            shutil.copyfile(origin[rel], dst)
    for rel in del_ok:
        (published_dir / rel).unlink(missing_ok=True)
    _git(settings.repo, "add", "-A", "--", settings.subdir)
    if not _git(settings.repo, "diff", "--cached", "--quiet", check=False).returncode:
        res.status = "nothing"
        return res
    ok = sorted(ok)
    n = len(ok) + len(del_ok)
    lab_n = sum(lab_owned(r) for r in ok + del_ok)
    what = "from the vault" if not lab_n else "from the lab" if lab_n == n else "from the vault and the lab"
    msg = f"Publish {n} document file{'s' if n != 1 else ''} {what}\n\n" + "\n".join(
        [f"updated: {r}" for r in ok] + [f"removed: {r}" for r in del_ok]
    )
    env = dict(os.environ)
    name, _, email = settings.author.partition(" <")
    env.update(GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email.rstrip(">"), GIT_COMMITTER_NAME=name,
               GIT_COMMITTER_EMAIL=email.rstrip(">"))
    subprocess.run(["git", "-C", str(settings.repo), "commit", "-q", "-m", msg], check=True, env=env)
    res.commit = _git(settings.repo, "rev-parse", "HEAD").stdout.strip()
    res.published, res.deleted = ok, del_ok

    from tools.leakgate.denylist import Denylist, load_key
    from tools.leakgate.gitscan import scan_commits
    from tools.leakgate.scan import DATA_DIR, BLOCK, Config, Scanner

    scanner = Scanner(Denylist.load(settings.hashes or DATA_DIR / "denylist.hmac.json", load_key()), Config.load())
    if any(f.tier == BLOCK for f in scan_commits(scanner, settings.repo, "HEAD~1..HEAD")):
        _git(settings.repo, "reset", "-q", "--hard", "HEAD~1")
        res.status, res.commit, res.published, res.deleted = "error", None, [], []
        _hold(res, "(commit)", "leakgate:commit metadata")
        return res
    if settings.push:
        _git(settings.repo, "push", "-q", settings.remote, f"HEAD:{settings.branch}")
        res.pushed = True
    return res


def notify(res: RunResult) -> str | None:
    """Tell a person about held files and files of the unknown class: Telegram if configured, else email, else nothing."""
    unknown = sorted(rel for rel, cls in res.classes.items() if cls == UNKNOWN)
    if not res.held and not unknown:
        return None
    lines = []
    if res.held:
        lines += [f"Publisher held {len(res.held)} file(s):"] + [f"- {k}: {', '.join(v)}" for k, v in sorted(res.held.items())]
    if any(r.startswith("simcheck:") for v in res.held.values() for r in v):
        lines.append("Semantic holds: run exocortex-gate-review, tick keep/rewrite on the page, then exocortex-gate-approve.")
    if unknown:
        lines.append(f"Alarm: {len(unknown)} file(s) of the unknown publication class (not on the class list, or a "
                     "documentation path with another extension or over the size limit); they got the strictest checks:")
        lines += [f"- {rel}" for rel in unknown]
    text = "\n".join(lines)
    def _set(name: str) -> str | None:
        v = os.environ.get(name, "").strip()
        return None if v.lower() in ("", "none", "unset") else v

    token, chat = _set("TELEGRAM_BOT_TOKEN"), _set("TELEGRAM_CHAT_ID")
    if token and chat:
        import httpx

        httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text}, timeout=30)
        return "telegram"
    host, to = _set("SMTP_HOST"), _set("PUBLISHER_NOTIFY_EMAIL")
    if host and to:
        import smtplib
        from email.message import EmailMessage

        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = "Publisher: files held", os.environ.get("SMTP_FROM", to), to
        msg.set_content(text)
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587"))) as s:
            s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
        return "email"
    return None


def log(res: RunResult, path: Path | None) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(res.to_dict()) + "\n")
