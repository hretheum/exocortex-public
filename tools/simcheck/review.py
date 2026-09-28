"""Review list for the owner, and approvals taken from it.

``collect`` finds paragraphs of the documents to publish that are close to
the protected corpus (and asks the judge, if one is configured). ``render``
turns them into a Markdown page for Obsidian: links to both notes, quotes of
both paragraphs, and two checkboxes per paragraph. ``approve`` reads the
ticked boxes back and records the hashes of the paragraphs marked "keep", so
simcheck stops holding them for as long as their text stays the same.

The page quotes private notes. It is written only to a private folder and
never passes through the publisher.
"""

from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from urllib.parse import unquote

from .core import Index, iter_dir_texts, iter_postgres_texts, load_approved, paragraph_hash, paragraphs

LABELS = {
    "pl": {
        "title": "Przegląd semantyczny dokumentów do publikacji, {date}",
        "howto_h": "Co z tym zrobić",
        "howto": [
            "Bramka znalazła akapity znaczeniowo bliskie notatkom chronionym (klienckim i prywatnym). "
            "Zdecyduj dla każdego, czy to tylko wspólny temat, czy powtórzenie konkretu.",
            "",
            "1. Przeczytaj akapit publiczny i najbliższe notatki chronione (cytaty pod spodem, linki otwierają całe notatki).",
            "2. Jeśli łączy je tylko temat albo ogólna metoda, zaznacz „zostawiam”.",
            "3. Jeśli akapit publiczny powtarza konkret z notatki (fakt, liczbę, decyzję, nazwę, zdanie), "
            "zaznacz „do przepisania” i przepisz go albo zleć przepisanie.",
            "",
            "„Model” to podpowiedź lokalnego modelu, decyzja należy do Ciebie. Po zakończeniu uruchom "
            "`systemctl --user start exocortex-gate-approve` na serwerze: akapity oznaczone „zostawiam” "
            "przestaną być zatrzymywane, dopóki ich tekst się nie zmieni.",
        ],
        "summary_h": "Zestawienie",
        "cols": "| # | Plik publiczny | Najbliższa notatka chroniona | Podobieństwo | Akapity: model „powtarza” / wszystkie |",
        "file": "Plik",
        "item": "Podobieństwo {score:.3f}, model: {verdict}",
        "yes": "**powtarza**",
        "no": "tylko temat",
        "public": "Akapit publiczny:",
        "near": "Najbliższe notatki chronione:",
        "sim": "podobieństwo",
        "db": "baza silnika",
        "unknown": "nieznane źródło",
        "keep": "zostawiam, tylko wspólny temat",
        "rewrite": "do przepisania",
        "empty": "Brak akapitów do przejrzenia.",
    },
    "en": {
        "title": "Semantic review of documents to publish, {date}",
        "howto_h": "What to do",
        "howto": [
            "The gate found paragraphs close in meaning to protected notes (client and private). "
            "Decide for each whether they only share a topic or repeat something specific.",
            "",
            "1. Read the public paragraph and the nearest protected notes (quotes below, links open the whole notes).",
            "2. If they only share a topic or a general method, tick “keep”.",
            "3. If the public paragraph repeats something specific from the note (a fact, a figure, a decision, "
            "a name, a sentence), tick “rewrite” and rewrite it or have it rewritten.",
            "",
            "“Model” is a hint from the local model; the decision is yours. When done, run "
            "`systemctl --user start exocortex-gate-approve` on the server: paragraphs marked “keep” are no "
            "longer held for as long as their text stays the same.",
        ],
        "summary_h": "Summary",
        "cols": "| # | Public file | Nearest protected note | Similarity | Paragraphs: model “repeats” / all |",
        "file": "File",
        "item": "Similarity {score:.3f}, model: {verdict}",
        "yes": "**repeats**",
        "no": "topic only",
        "public": "Public paragraph:",
        "near": "Nearest protected notes:",
        "sim": "similarity",
        "db": "engine database",
        "unknown": "unknown source",
        "keep": "keep, topic only",
        "rewrite": "rewrite",
        "empty": "Nothing to review.",
    },
}


def source_map(corpus: Path | None, exclude: list[str], dsn: str | None) -> dict[str, dict]:
    """Paragraph text -> where it comes from (vault path, or database row)."""
    out: dict[str, dict] = {}
    if corpus is not None and corpus.is_dir():
        for src, text in iter_dir_texts([corpus], exclude):
            rel = str(Path(src).relative_to(corpus))
            for p in paragraphs(text):
                out.setdefault(p, {"vault": rel})
    if dsn:
        query = ("SELECT t.thought_type || '|' || t.id::text || '|' || coalesce(r.uri, ''), t.body FROM thoughts t "
                 "LEFT JOIN raw_sources r ON r.id = t.source_id WHERE t.body IS NOT NULL")
        for key, body in iter_postgres_texts(dsn, query):
            ttype, tid, uri = key.split("|", 2)
            for p in paragraphs(body):
                if p in out:
                    continue
                if uri.startswith("file:///vault/"):
                    out[p] = {"vault": unquote(uri[len("file:///vault/"):]), "db": ttype}
                else:
                    out[p] = {"db": ttype, "ref": uri or tid}
    return out


def collect(index: Index, docs: Path, sources: dict[str, dict], judge=None, low: float | None = None,
            show: float | None = None, approved: set[str] | None = None) -> list[dict]:
    """Paragraphs of the documents under ``docs`` worth a person's look.

    A paragraph is listed when its similarity reaches ``show`` (default: the
    semantic threshold in force), or when it reaches ``low`` (default: the
    candidate threshold, else ``show``) and the judge says it repeats a note.
    Already approved paragraphs are skipped.
    """
    show = show if show is not None else index.thresholds["semantic"]
    low = low if low is not None else index.thresholds.get("semantic_candidate", show)
    approved = approved or set()
    files = []
    for src, text in iter_dir_texts([docs]):
        paras = [p for p in paragraphs(text) if paragraph_hash(p) not in approved]
        if not paras:
            continue
        q = index._embed_queries(paras)
        raw, nn = index.semantic_neighbours(paras, 3, q=q)
        items = []
        for i, p in enumerate(paras):
            if raw[i] < min(low, show):
                continue
            neigh = [{"score": float(q[i] @ index.vectors[j]), "text": index.texts[j],
                      "source": sources.get(index.texts[j], {})} for j in nn[i]]
            verdict = judge.is_restatement(p, [n["text"] for n in neigh]) if judge is not None else False
            if raw[i] >= show or (verdict and raw[i] >= low):
                items.append({"para": p, "score": raw[i], "judge": verdict, "neighbours": neigh})
        if items:
            files.append({"file": str(Path(src).relative_to(docs)), "max": max(x["score"] for x in items),
                          "items": items})
    return files


def _link(path: str, table: bool = False) -> str:
    target = re.sub(r"\.md$", "", path)
    sep = "\\|" if table else "|"
    return f"[[{target}{sep}{Path(target).name}]]"


def _src(src: dict, lab: dict, table: bool = False) -> str:
    if "vault" in src:
        return _link(src["vault"], table)
    if "db" in src:
        return f"{lab['db']}: {src['db']} ({src.get('ref', '')})"
    return lab["unknown"]


def _quote(text: str, limit: int | None = None) -> str:
    t = text.strip()
    if limit and len(t) > limit:
        t = t[:limit].rstrip() + " […]"
    return "\n".join("> " + line if line.strip() else ">" for line in t.splitlines())


def render(files: list[dict], docs_prefix: str, lang: str = "pl", date: str | None = None) -> str:
    """Markdown page; ``docs_prefix`` is the documents folder relative to the vault root."""
    lab = LABELS[lang]
    date = date or dt.date.today().isoformat()
    for f in files:
        f["yes"] = sum(1 for i in f["items"] if i["judge"])
    files = sorted(files, key=lambda f: (-f["yes"], -f["max"]))
    prefix = docs_prefix.rstrip("/") + "/"
    out = ["---", "tymczasowe: true" if lang == "pl" else "temporary: true", f"review_docs: {prefix}", "---", "",
           f"# {lab['title'].format(date=date)}", "", f"## {lab['howto_h']}", "", *lab["howto"], "",
           f"## {lab['summary_h']}", ""]
    if not files:
        return "\n".join(out + [lab["empty"], ""])
    out += [lab["cols"], "|---|---|---|---|---|"]
    for n, f in enumerate(files, 1):
        best = max(f["items"], key=lambda i: i["score"])
        out.append(f"| [[#{n}. {f['file']}\\|{n}]] | {_link(prefix + f['file'], True)} | "
                   f"{_src(best['neighbours'][0]['source'], lab, True)} | {f['max']:.3f} | {f['yes']} / {len(f['items'])} |")
    out.append("")
    for n, f in enumerate(files, 1):
        out += [f"## {n}. {f['file']}", "", f"{lab['file']}: {_link(prefix + f['file'])}", ""]
        for k, it in enumerate(sorted(f["items"], key=lambda i: (-i["judge"], -i["score"])), 1):
            verdict = lab["yes"] if it["judge"] else lab["no"]
            out += [f"### {n}.{k}. {lab['item'].format(score=it['score'], verdict=verdict)}", "",
                    lab["public"], "", _quote(it["para"]), "", lab["near"], ""]
            for m, nb in enumerate(it["neighbours"], 1):
                out += [f"{m}. {_src(nb['source'], lab)} ({lab['sim']} {nb['score']:.3f})", "",
                        _quote(nb["text"], 900 if m == 1 else 400), ""]
            out += [f"- [ ] {lab['keep']}", f"- [ ] {lab['rewrite']}", ""]
    return "\n".join(out) + "\n"


def _unquote(block: str) -> str:
    lines = [ln[2:] if ln.startswith("> ") else ln[1:] if ln.startswith(">") else ln for ln in block.strip().splitlines()]
    return "\n".join(lines).strip()


def decisions(page: str) -> list[dict]:
    """(file, public paragraph, keep, rewrite) for every item on a review page, in either language."""
    out = []
    for m in re.finditer(r"\n## \d+\. (\S+)\n(.*?)(?=\n## \d+\. |\Z)", page, re.S):
        path, body = m.group(1), m.group(2)
        for it in re.finditer(r"\n### \d+\.\d+\. [^\n]*\n(.*?)(?=\n### |\Z)", body, re.S):
            sec = it.group(1)
            parts = re.split(r"\n(?:Akapit publiczny:|Public paragraph:)\n|\n(?:Najbliższe notatki chronione:|Nearest protected notes:)\n", "\n" + sec)
            if len(parts) < 3:
                continue
            keep = re.search(r"- \[[xX]\] (?:zostawiam|keep)", sec) is not None
            rewrite = re.search(r"- \[[xX]\] (?:do przepisania|rewrite)", sec) is not None
            out.append({"file": path, "para": _unquote(parts[1]), "keep": keep, "rewrite": rewrite})
    return out


def approve(page_path: Path, docs: Path, approved_path: Path) -> dict:
    """Record the paragraphs marked "keep" (and not "rewrite") whose text is
    still in the current documents. Returns counts."""
    items = decisions(page_path.read_text(encoding="utf-8"))
    known = load_approved(approved_path)
    added, missing = [], 0
    current: dict[str, set[str]] = {}
    for it in items:
        if not it["keep"] or it["rewrite"]:
            continue
        path = docs / it["file"]
        parts = Path(it["file"]).parts
        for i in range(1, len(parts)):
            if path.is_file():
                break
            path = docs.joinpath(*parts[i:])  # pages that list paths with a folder name in front
        if it["file"] not in current:
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
            current[it["file"]] = {paragraph_hash(p) for p in paragraphs(text)}
        h = paragraph_hash(it["para"])
        if h not in current[it["file"]]:
            missing += 1  # the paragraph changed since the review; it has to be looked at again
            continue
        if h not in known:
            known.add(h)
            added.append((h, it["file"]))
    if added:
        approved_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with approved_path.open("a", encoding="utf-8") as fh:
            for h, f in added:
                fh.write(f"{h}  # {f} {stamp} {page_path.name}\n")
        os.chmod(approved_path, 0o644)
    return {"items": len(items), "keep": sum(1 for i in items if i["keep"] and not i["rewrite"]),
            "rewrite": sum(1 for i in items if i["rewrite"]), "undecided": sum(1 for i in items if not i["keep"] and not i["rewrite"]),
            "approved_added": len(added), "changed_since_review": missing}
