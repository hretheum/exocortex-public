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

Held files keep their previously published version. The run log records
rule names and paths only, never matched text.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

IGNORED = {".DS_Store", ".obsidian", ".trash", ".stfolder", ".stversions", ".git"}


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


def _pair_key(rel: str) -> str:
    parts = rel.split("/", 1)
    return parts[1] if len(parts) == 2 and parts[0] in ("pl", "en") else rel


def _hold(res: RunResult, rel: str, reason: str) -> None:
    res.held.setdefault(rel, [])
    if reason not in res.held[rel]:
        res.held[rel].append(reason)


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
                r = httpx.post(settings.simcheck_url.rstrip("/") + "/check", json={"text": text}, timeout=120)
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


def publish(settings: Settings) -> RunResult:
    res = RunResult()
    if settings.lock_file and settings.lock_file.exists():
        res.status = "locked"
        return res
    published_dir = settings.repo / settings.subdir
    changed, deleted = diff(settings.source, published_dir)
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
            shutil.copy2(settings.source / rel, stage / rel)
        for rel in deleted:
            (stage / rel).unlink()
        check_changes(stage, changed, settings, res)

    ok = [r for r in changed if r not in res.held]
    # deleting one half of a pair alone would break parity in public; keep pairs together
    del_ok = [r for r in deleted if not any(_pair_key(h) == _pair_key(r) for h in res.held)]
    if not ok and not del_ok:
        res.status = "held-only"
        return res
    if settings.dry_run:
        res.published, res.deleted = ok, del_ok
        return res

    for rel in ok:
        dst = published_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(settings.source / rel, dst)
    for rel in del_ok:
        (published_dir / rel).unlink(missing_ok=True)
    _git(settings.repo, "add", "-A", "--", settings.subdir)
    if not _git(settings.repo, "diff", "--cached", "--quiet", check=False).returncode:
        res.status = "nothing"
        return res
    n = len(ok) + len(del_ok)
    msg = f"Publish {n} document file{'s' if n != 1 else ''} from the vault\n\n" + "\n".join(
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
    text = "\n".join(lines)
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        import httpx

        httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat, "text": text}, timeout=30)
        return "telegram"
    host, to = os.environ.get("SMTP_HOST"), os.environ.get("PUBLISHER_NOTIFY_EMAIL")
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
