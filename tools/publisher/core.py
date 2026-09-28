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
ignored in the vault. They go through exactly the same checks. The
registry may only grow: a version that changes or drops a published line
is held. Lab-owned files are deleted in the repository only while the lab
folder is present and not empty, so an unmounted folder never wipes them.

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

IGNORED = {".DS_Store", ".obsidian", ".trash", ".stfolder", ".stversions", ".git"}
REGISTRY = "prereg.jsonl"
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

    def to_dict(self) -> dict:
        return {
            "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "status": self.status,
            "published": self.published,
            "deleted": self.deleted,
            "held": self.held,
            "commit": self.commit,
            "pushed": self.pushed,
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


def plan(settings: Settings) -> tuple[list[str], list[str], dict[str, Path]]:
    """(changed or new, deleted, origin of every source file)."""
    origin = origins(settings)
    pub = _files(settings.repo / settings.subdir)
    lab = settings.lab_source
    lab_present = lab is not None and bool(_files(lab))  # at least one file: empty dirs may mean "not mounted"
    changed = sorted(rel for rel, path in origin.items()
                     if pub.get(rel) != hashlib.sha256(path.read_bytes()).hexdigest())
    deleted = sorted(rel for rel in pub if rel not in origin and (not lab_owned(rel) or lab_present))
    return changed, deleted, origin


def _append_only(old: str, new: str) -> bool:
    old_lines = [ln for ln in old.splitlines() if ln.strip()]
    return [ln for ln in new.splitlines() if ln.strip()][:len(old_lines)] == old_lines


def _pair_key(rel: str) -> str:
    parts = rel.split("/", 1)
    return parts[1] if len(parts) == 2 and parts[0] in ("pl", "en") else rel


def _hold(res: RunResult, rel: str, reason: str) -> None:
    res.held.setdefault(rel, [])
    if reason not in res.held[rel]:
        res.held[rel].append(reason)


def check_registry(stage: Path, published: Path, changed: list[str], deleted: list[str], res: RunResult) -> None:
    """The preregistration registry may only grow."""
    if REGISTRY in deleted:
        _hold(res, REGISTRY, "registry: may not be removed")
    if REGISTRY in changed:
        old = (published / REGISTRY).read_text(encoding="utf-8") if (published / REGISTRY).exists() else ""
        if not _append_only(old, (stage / REGISTRY).read_text(encoding="utf-8")):
            _hold(res, REGISTRY, "registry: published lines changed or removed")


def check_changes(stage: Path, changed: list[str], settings: Settings, res: RunResult) -> None:
    """Run all checks on the staged tree and record held files in ``res``."""
    from tools.humanlint.core import run as humanlint_run
    from tools.leakgate.denylist import Denylist, load_key
    from tools.leakgate.scan import DATA_DIR, BLOCK, WARN, Config, Scanner
    from tools.paritycheck.core import check as parity_check

    scanner = Scanner(Denylist.load(settings.hashes or DATA_DIR / "denylist.hmac.json", load_key()), Config.load(), stage)
    for rel in changed:
        data = (stage / rel).read_bytes()
        for f in scanner.scan_bytes(rel, data):
            if f.tier in (BLOCK, WARN):  # warnings also hold: a person decides
                _hold(res, rel, f"leakgate:{f.rule}")
        if rel.endswith(".md") and b"\ntranslation: machine" in data:
            _hold(res, rel, "machine translation not reviewed")

    if settings.simcheck_url:
        import httpx

        for rel in changed:
            if not rel.endswith((".md", ".txt", ".yaml", ".yml", ".csv", ".json")):
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
                if rel in changed or (stage / rel).exists():
                    _hold(res, rel, f"paritycheck:{p.check}")

    from tools.docschema.core import validate_text

    for rel in changed:
        if rel.endswith(".md"):
            for err in validate_text(rel, (stage / rel).read_text(encoding="utf-8")):
                _hold(res, rel, f"docschema:{err.field}")

    for rep in humanlint_run([stage]):
        rel = Path(rep.path).relative_to(stage).as_posix()
        if rel in changed and not rep.ok:
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
    if not changed and not deleted:
        res.status = "nothing"
        return res

    with tempfile.TemporaryDirectory(prefix="publisher-") as tmp:
        stage = Path(tmp) / settings.subdir
        if published_dir.is_dir():
            shutil.copytree(published_dir, stage)
        else:
            stage.mkdir(parents=True)
        for rel in changed:
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(origin[rel], stage / rel)
        for rel in deleted:
            (stage / rel).unlink()
        check_registry(stage, published_dir, changed, deleted, res)
        check_changes(stage, changed, settings, res)

    ok = [r for r in changed if r not in res.held]
    # deleting one half of a pair alone would break parity in public; keep pairs together
    del_ok = [r for r in deleted if r not in res.held and not any(_pair_key(h) == _pair_key(r) for h in res.held)]
    if not ok and not del_ok:
        res.status = "held-only"
        return res
    if settings.dry_run:
        res.published, res.deleted = ok, del_ok
        return res

    for rel in ok:
        dst = published_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin[rel], dst)
    for rel in del_ok:
        (published_dir / rel).unlink(missing_ok=True)
    _git(settings.repo, "add", "-A", "--", settings.subdir)
    if not _git(settings.repo, "diff", "--cached", "--quiet", check=False).returncode:
        res.status = "nothing"
        return res
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
    """Tell a person about held files: Telegram if configured, else email, else nothing."""
    if not res.held:
        return None
    lines = [f"Publisher held {len(res.held)} file(s):"] + [f"- {k}: {', '.join(v)}" for k, v in sorted(res.held.items())]
    if any(r.startswith("simcheck:") for v in res.held.values() for r in v):
        lines.append("Semantic holds: run exocortex-gate-review, tick keep/rewrite on the page, then exocortex-gate-approve.")
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
