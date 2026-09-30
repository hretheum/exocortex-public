#!/usr/bin/env python3
# © 2026 Eryk Orłowski and Exocortex contributors.
# Licensed under Apache 2.0 + Commons Clause. See LICENSE for details.

"""Build the static site of Exocortex R&D (lab.exocortex.zone) from the repository.

    python lab-site/build.py --docs dowody --corpora lab/corpora --out dist \\
        --base-url https://lab.exocortex.zone --repo-url https://github.com/hretheum/exocortex-public

Pages: /en/ and /pl/ (home, how it works, hypotheses, one dossier per hypothesis, status).
The root page redirects to /en/. Every page links with relative paths, so the output also
works from a sub-folder or from a preview host. Nothing is fetched at build time and the
site loads nothing from third parties (fonts are served from /assets/fonts).
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import posixpath
import re
import shutil
import sys
from pathlib import Path

import xml.etree.ElementTree as ET

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import infog  # noqa: E402
import model  # noqa: E402
from i18n import UI  # noqa: E402

LANGS = ("en", "pl")
esc = html.escape
SEC_KEYS = model.SECTION_KEYS
STATUS_KEY = {"planned": "plan", "preparation": "prep", "running": "run", "decided": "done"}
PILL_KIND = {"planned": "plan", "preparation": "prep", "running": "prep", "decided": "ok"}

# ------------------------------------------------------------------ tables ----
# The same rule as the review desk (tools/gate/desk_static/md.js): at most three columns of short cells
# stay a table; two columns with longer cells become one tile of "field: content" lines; anything wider
# becomes one tile per row, the first cell as the title (its heading kept as hidden text for screen
# readers) and the others as heading and value in a grid that folds into one column on a phone.
SHORT_CELL = 32


def table_mode(heads: list[str], rows: list[list[str]]) -> str:
    """"table", "pairs" or "tiles" for a table with these headings and rows (plain text)."""
    cells = list(heads) + [c for r in rows for c in r]
    if len(heads) <= 3 and all(len((c or "").strip()) <= SHORT_CELL for c in cells):
        return "table"
    return "pairs" if len(heads) == 2 else "tiles"


def _move(src: ET.Element, dst: ET.Element) -> ET.Element:
    dst.text = src.text
    for child in list(src):
        dst.append(child)
    return dst


def _plain(el: ET.Element) -> str:
    return "".join(el.itertext())


def _tiles_of(table: ET.Element) -> ET.Element | None:
    head = [th for th in table.iter("th")]
    rows = [list(tr.iter("td")) for tr in table.iter("tr") if tr.find("td") is not None]
    mode = table_mode([_plain(h) for h in head], [[_plain(c) for c in r] for r in rows])
    if mode == "table":
        return None
    box = ET.Element("div", {"class": "tiles"})
    if mode == "pairs":
        dl = ET.SubElement(box, "dl", {"class": "tile"})
        for r in rows:
            f = ET.SubElement(dl, "div", {"class": "f"})
            _move(r[0], ET.SubElement(f, "dt"))
            if len(r) > 1:
                _move(r[1], ET.SubElement(f, "dd"))
        return box
    box.set("role", "list")
    labels = [_plain(h).strip() for h in head]
    for r in rows:
        tile = ET.SubElement(box, "section", {"class": "tile row", "role": "listitem"})
        title = ET.SubElement(tile, "p", {"class": "tile-t"})
        if r:
            _move(r[0], title)
        if labels and labels[0]:
            sr = ET.Element("span", {"class": "sr"})
            sr.text, sr.tail = f"{labels[0]}: ", title.text
            title.text = None
            title.insert(0, sr)
        dl = ET.SubElement(tile, "dl", {"class": "tile-f"})
        for i, cell in enumerate(r[1:], 1):
            f = ET.SubElement(dl, "div", {"class": "f"})
            ET.SubElement(f, "dt").text = labels[i] if i < len(labels) else ""
            _move(cell, ET.SubElement(f, "dd"))
    return box


class _TileTables(Treeprocessor):
    def run(self, root: ET.Element) -> None:
        for parent in list(root.iter()):
            for i, child in enumerate(list(parent)):
                if child.tag == "table":
                    new = _tiles_of(child)
                    if new is not None:
                        new.tail = child.tail
                        parent.remove(child)
                        parent.insert(i, new)


class TileTables(Extension):
    def extendMarkdown(self, md: markdown.Markdown) -> None:
        md.treeprocessors.register(_TileTables(md), "tile_tables", 5)  # after inline Markdown in the cells


MD = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists", TileTables()])


# ------------------------------------------------------------------ helpers ----
class Site:
    def __init__(self, a):
        self.a = a
        self.base = a.base_url.rstrip("/")
        self.repo = a.repo_url.rstrip("/")
        self.repo_public = a.repo_public
        self.index_links = a.index_links
        self.main = a.main_site.rstrip("/")
        self.asof = a.asof
        self.root_abs = False
        self.written: list[str] = []
        self.out = Path(a.out)

    def write(self, rel: str, content: str | bytes) -> None:
        p = self.out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, str):
            p.write_text(content, encoding="utf-8")
        else:
            p.write_bytes(content)
        self.written.append(rel)


def up(cur: str) -> str:
    depth = len([p for p in cur.split("/") if p])
    return "../" * depth


def href(cur: str, target: str, S: Site) -> str:
    """Relative link from page directory ``cur`` to directory/file ``target`` (site-relative)."""
    tgt = target
    if S.root_abs:
        return "/" + tgt
    if S.index_links and (tgt == "" or tgt.endswith("/")):
        tgt = tgt + "index.html"
    r = posixpath.relpath(tgt or ".", cur or ".") if cur else (tgt or "./")
    if target.endswith("/") and not r.endswith("/") and not S.index_links:
        r += "/"
    return r if r != "./" else "./"


def md_inline(text: str) -> str:
    out = markdown.markdown(text, extensions=[])
    return re.sub(r"^<p>(.*)</p>$", r"\1", out, flags=re.S)


def render_md(text: str, S: Site, lang: str, cur: str, src: str) -> str:
    """Markdown to HTML with links resolved for the site and tables made scrollable."""
    MD.reset()
    h = MD.convert(text)
    h = re.sub(r"<table>", '<div class="tw"><table>', h)
    h = h.replace("</table>", "</table></div>")

    def fix(m):
        attrs, label = m.group(1), m.group(2)
        u = re.search(r'href="([^"]*)"', attrs).group(1)
        return resolve_link(u, label, S, lang, cur, src)
    h = re.sub(r"<a ([^>]*)>(.*?)</a>", fix, h, flags=re.S)
    return h


def repo_url_for(S: Site, path: str) -> str:
    return f"{S.repo}/blob/main/{path}"


def resolve_link(u: str, label: str, S: Site, lang: str, cur: str, src: str) -> str:
    if u.startswith(("http://", "https://")):
        return f'<a href="{esc(u)}" target="_blank" rel="noopener">{label}</a>'
    if u.startswith("#"):
        return f'<a href="{esc(u)}">{label}</a>'
    frag = ""
    if "#" in u:
        u, frag = u.split("#", 1)
        frag = "#" + frag
    target = posixpath.normpath(posixpath.join(posixpath.dirname(src), u))
    m = re.match(rf"dowody/{lang}/experiments/([^/]+)/overview\.md$", target)
    if m:
        return f'<a href="{href(cur, f"{lang}/hypotheses/{m.group(1)}/", S)}{frag}">{label}</a>'
    if target == f"dowody/{lang}/02-roadmap.md" or target.startswith(f"dowody/{lang}/roadmap/"):
        return f'<a href="{href(cur, f"{lang}/status/", S)}">{label}</a>'
    if target == f"dowody/{lang}/04-how-it-works.md":
        return f'<a href="{href(cur, f"{lang}/how-it-works/", S)}">{label}</a>'
    if S.repo_public:
        return f'<a href="{esc(repo_url_for(S, target))}{frag}" target="_blank" rel="noopener">{label}</a>'
    return f'<span class="repo-pending" title="{esc(UI[lang]["repo_pending"])}">{label}</span>'


def strip_h1(body: str) -> str:
    return re.sub(r"\A\s*# .*\n", "", body, count=1).strip()


def pill(kind: str, text: str) -> str:
    return f'<span class="pill {kind}">{esc(text)}</span>'


def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit, div in (("KB", 1024), ("MB", 1024 ** 2), ("GB", 1024 ** 3)):
        if n < div * 1024 or unit == "GB":
            return f"{n / div:.1f}".rstrip("0").rstrip(".") + f" {unit}"
    return str(n)


def fmt_num(n: int | None, lang: str) -> str:
    if n is None:
        return "–"
    s = f"{n:,}"
    return s.replace(",", " " if lang == "pl" else ",")


# ------------------------------------------------------------------ figures ----
def figure_svg(lang: str, n: int, cache: dict) -> tuple[str, str]:
    d = cache[(lang, f"f{n}")]
    s = d["inline"].replace(" width=\"520\"", "", 1)
    s = re.sub(r' height="\d+"', "", s, count=1)
    return s, d["alt"]


def figure_html(lang: str, n: int, cache: dict) -> str:
    svg, alt = figure_svg(lang, n, cache)
    return f'<figure class="fig"><div class="sheet">{svg}</div><figcaption>{esc(alt)}</figcaption></figure>'


def apply_dynamic(dossiers, roadmaps, state):
    for lang in LANGS:
        t4 = infog.T[lang]["f4"]
        rows = []
        for d in dossiers:
            bl = d.by_lang.get(lang)
            if not bl:
                continue
            rows.append((d.roadmap, bl["title"], bl["tagline"], STATUS_KEY.get(d.status, "plan"), d.stage))
        t4["rows"] = rows
        t8 = infog.T[lang]["f8"]
        by_id = {p.id: p for p in roadmaps[lang]}
        new = []
        for code, name, sub, st, done, total in t8["rows"]:
            p = by_id.get(code)
            if p:
                st = {"working": "live", "done": "live", "progress": "wip", "planned": "plan"}[phase_state(p, state)]
                done, total = p.done, len(p.tasks)
            new.append((code, name, sub, st, done, total))
        t8["rows"] = new


def phase_state(p: model.Phase, state: dict) -> str:
    # The phase label is always computed from the task statuses, so nobody has to keep it current by hand.
    # The `state` argument is kept only so old callers and the --state option keep working; it is ignored.
    if p.tasks and p.done == len(p.tasks):
        return "done"
    if p.done or p.doing:
        return "progress"
    return "planned"


# ------------------------------------------------------------------ layout ----
def page(S: Site, lang: str, cur: str, title: str, desc: str, body: str, alt_paths: dict, extra_head: str = "",
         nav_key: str = "", og_type: str = "website", wide: bool = False) -> str:
    T = UI[lang]
    r = "/" if S.root_abs else up(cur)
    wc = "wrap wide" if wide else "wrap"
    canon = f"{S.base}/{cur}/" if cur else f"{S.base}/"
    alts = "".join(f'<link rel="alternate" hreflang="{l}" href="{S.base}/{p}">' for l, p in alt_paths.items())
    alts += f'<link rel="alternate" hreflang="x-default" href="{S.base}/{alt_paths["en"]}">'
    def nav_link(key, label, target):
        cls = ' aria-current="page"' if nav_key == key else ""
        return f'<a href="{href(cur, target, S)}"{cls}>{esc(label)}</a>'
    other = "pl" if lang == "en" else "en"
    nav = (nav_link("how", T["nav_how"], f"{lang}/how-it-works/") + nav_link("hyp", T["nav_hyp"], f"{lang}/hypotheses/")
           + nav_link("status", T["nav_status"], f"{lang}/status/"))
    switch = "".join(
        f'<a href="{href(cur, alt_paths[l], S)}" hreflang="{l}" lang="{l}"' + (' aria-current="true"' if l == lang else "") + f'>{l.upper()}</a>'
        for l in LANGS)
    repo_footer = (f'<a href="{esc(S.repo)}" target="_blank" rel="noopener">{esc(T["footer_repo"])}</a>' if S.repo_public
                   else f'<span class="repo-pending" title="{esc(T["repo_pending"])}">{esc(T["footer_repo_pending"])}</span>')
    fonts = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600..800'
             '&family=Instrument+Sans:wght@400..700&family=JetBrains+Mono:wght@500;600;700&display=swap">'
             if S.a.fonts == "google" else (f'<link rel="stylesheet" href="{r}assets/fonts.css">' if (S.out / "assets" / "fonts.css").exists() else ""))
    icon = ("data:image/svg+xml," + "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='8' fill='%233B4A78'/%3E"
            "%3Cpath d='M12 6h8M13 6v7l-5 9a2 2 0 0 0 1.8 3h12.4a2 2 0 0 0 1.8-3l-5-9V6M10 19h12' fill='none' stroke='%23fff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")
    build_line = f'{esc(T["footer_built"])} {esc(S.asof)}' + (f' · {esc(os.environ["GITHUB_SHA"][:7])}' if os.environ.get("GITHUB_SHA") else "")
    return f"""<!doctype html>
<html lang="{T['html_lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{canon}">
{alts}
<meta property="og:type" content="{og_type}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{canon}"><meta property="og:site_name" content="Exocortex R&amp;D">
<meta name="color-scheme" content="light dark">
<link rel="icon" href="{icon}">
<script>try{{var t=localStorage.getItem('lab-theme');if(t==='dark'||t==='light')document.documentElement.setAttribute('data-theme',t)}}catch(e){{}}</script>
{fonts}
<link rel="stylesheet" href="{r}assets/site.css">
{extra_head}
</head>
<body>
<a class="skip" href="#main">{esc(T['skip'])}</a>
<header class="site-h">
  <div class="{wc} bar">
    <a class="brand" href="{href(cur, lang + '/', S)}">Exocortex&nbsp;R&amp;D</a>
    <nav class="nav" aria-label="{esc(T['menu'])}">{nav}</nav>
    <div class="tools">
      <a class="exo" href="{esc(S.main)}" target="_blank" rel="noopener">{esc(T['nav_exo'])} <span aria-hidden="true">↗</span></a>
      <div class="seg" role="group" aria-label="{esc(T['language'])}">{switch}</div>
      <button class="theme" type="button" aria-label="{esc(T['theme'])}" title="{esc(T['theme'])}"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 3.5a8.5 8.5 0 0 1 0 17z" fill="currentColor"/></svg></button>
    </div>
  </div>
</header>
<main id="main" class="{wc}">
{body}
</main>
<footer class="site-f"><div class="{wc}">
  <p>{esc(T['footer_a'])} <a href="{esc(S.main)}" target="_blank" rel="noopener">exocortex.zone</a></p>
  <p>{esc(T['footer_c'])}</p>
  <p class="meta">{repo_footer} · {build_line}</p>
</div></footer>
<script src="{r}assets/site.js" defer></script>
</body>
</html>
"""


# ------------------------------------------------------------------ pieces ----
def track(lang: str, d: model.Dossier) -> str:
    T = UI[lang]
    active = d.status in ("preparation", "running")
    items = []
    for i, key in enumerate(model.STAGES):
        state = "done" if i < d.stage else ("cur" if i == d.stage and active else "todo")
        items.append(f'<li class="{state}"><span class="dot" aria-hidden="true"></span><span class="lbl">{esc(T["stages"][key])}</span></li>')
    return f'<ol class="track" aria-label="{esc(T["stage_word"])}">{"".join(items)}</ol>'


def apps_line(lang: str, d: model.Dossier) -> str:
    """One plain sentence on the business use, for a hypothesis card: the opening sentence of the approved section."""
    T = UI[lang]
    item = d.applications.get(lang) if d.applications_state == "current" else None
    first = next((p.strip() for p in re.split(r"\n\s*\n", strip_h1(item.body)) if p.strip() and not p.lstrip().startswith("#")), "") if item else ""
    text = " ".join(first.split())
    cls = "apps-line" if text else "apps-line wait"
    return f'<p class="{cls}"><span class="k">{esc(T["apps_card"])}:</span> {esc(text or T["apps_card_wait"])}</p>'


def hyp_card(S: Site, lang: str, cur: str, d: model.Dossier) -> str:
    T = UI[lang]
    bl = d.by_lang[lang]
    link = href(cur, f"{lang}/hypotheses/{d.slug}/", S)
    return (f'<article class="hyp"><div class="hyp-h"><span class="code">{esc(d.roadmap)}</span>'
            f'<h3><a href="{link}">{esc(bl["title"])}</a></h3>{pill(PILL_KIND[d.status], T["hstatus"][d.status])}</div>'
            f'<p>{esc(bl["tagline"])}</p>{apps_line(lang, d)}{track(lang, d)}'
            f'<p class="more"><a href="{link}">{esc(T["open_dossier"])} <span aria-hidden="true">→</span></a></p></article>')


def alt_map(path_for) -> dict:
    return {l: path_for(l) for l in LANGS}


# ------------------------------------------------------------------ pages ----
def page_home(S, lang, dossiers, fig):
    T = UI[lang]
    cur = f"{lang}"
    hero = (f'<section class="hero"><h1>{esc(T["home_title"])}</h1><p class="lead">{esc(T["home_lead"])}</p>'
            f'<p class="cta"><a class="btn primary" href="{href(cur, lang + "/hypotheses/", S)}">{esc(T["cta_hyp"])}</a>'
            f'<a class="btn" href="{href(cur, lang + "/how-it-works/", S)}">{esc(T["cta_how"])}</a></p></section>')
    principles = "".join(f'<div class="pr"><h3>{esc(T[k + "_t"])}</h3><p>{esc(T[k + "_d"])}</p></div>' for k in ("p1", "p2", "p3"))
    hyps = "".join(hyp_card(S, lang, cur, d) for d in dossiers[:3])
    body = (hero + f'<section class="principles">{principles}</section>'
            f'<section><h2>{esc(T["home_hyp_h"])}</h2><p>{esc(T["home_hyp_p"])}</p><div class="hyps">{hyps}</div>'
            f'<p class="more"><a href="{href(cur, lang + "/hypotheses/", S)}">{esc(T["all_hyp"])} <span aria-hidden="true">→</span></a></p></section>'
            f'<section><h2>{esc(T["home_how_h"])}</h2><p>{esc(T["home_how_p"])}</p>{figure_html(lang, 1, fig)}'
            f'<p class="more"><a href="{href(cur, lang + "/how-it-works/", S)}">{esc(T["cta_how"])} <span aria-hidden="true">→</span></a></p></section>'
            f'<section class="origin"><p>{esc(T["home_origin"])} <a href="{esc(S.main)}" target="_blank" rel="noopener">{esc(T["home_origin_link"])} <span aria-hidden="true">↗</span></a></p></section>')
    ld = json.dumps({"@context": "https://schema.org", "@type": "WebSite", "name": "Exocortex R&D", "url": f"{S.base}/{lang}/",
                     "inLanguage": lang, "description": T["home_desc"]}, ensure_ascii=False)
    return page(S, lang, cur, T["home_title"], T["home_desc"], body, alt_map(lambda l: f"{l}/"),
                extra_head=f'<script type="application/ld+json">{ld}</script>')


def page_how(S, lang, dossiers, fig, docs):
    T = UI[lang]
    cur = f"{lang}/how-it-works"
    src = f"dowody/{lang}/04-how-it-works.md"
    doc = docs / lang / "04-how-it-works.md"
    if not doc.is_file():
        # The text is published on its own schedule (it may still wait for a review). The page then shows
        # the figures with a notice instead of failing the whole build; the next build picks the text up.
        body = (f'<h1>{esc(T["how_title"])}</h1><p class="lead">{esc(T["how_pending"])}</p>'
                + "".join(figure_html(lang, n, fig) for n in range(1, 9)))
        return page(S, lang, cur, f'{T["how_title"]} · Exocortex R&D', T["how_desc"], body,
                    alt_map(lambda l: f"{l}/how-it-works/"), nav_key="how")
    front, text = model.read_md(doc)
    head, sections = model.split_sections(text)
    intro = re.sub(r"^# .*\n", "", head.strip(), count=1, flags=re.M).strip()
    parts = [f'<h1>{esc(T["how_title"])}</h1>']
    if intro:
        rendered = render_md(intro, S, lang, cur, src)
        parts.append(re.sub(r"^<p>", '<p class="lead">', rendered, count=1))
    toc = []
    body_secs = []
    for i, (heading, md) in enumerate(sections):
        sid = f"h{i + 1}"
        toc.append(f'<a href="#{sid}">{esc(heading)}</a>')
        md = re.sub(r"!\[[^\]]*\]\(img/(\d)-[^)]*\.svg\)", lambda m: f"\n\n@@FIG{m.group(1)}@@\n\n", md)
        # FAQ: every H3 with its paragraph becomes a collapsible question
        faq_html = ""
        if re.search(r"(?m)^### ", md):
            pieces = re.split(r"(?m)^### ", md)
            md = pieces[0]
            opened = False
            for piece in pieces[1:]:
                q, _, a = piece.partition("\n")
                q = q.strip()
                # A heading of the form "Label: subject" is a labelled block (for example the notes for data teams):
                # shown as written and folded. Any other heading is a question: it gets a "?" and the first one is open.
                labelled = ":" in q
                summary = q if labelled or q.endswith(("?", ".", "!")) else q + "?"
                is_open = not labelled and not opened
                opened = opened or is_open
                faq_html += (f'<details class="faqi"{" open" if is_open else ""}><summary>{esc(summary)}</summary>'
                             f'{render_md(a.strip(), S, lang, cur, src)}</details>')
        html_parts = []
        for chunk in re.split(r"(@@FIG\d@@)", md):
            if not chunk.strip():
                continue
            m = re.match(r"@@FIG(\d)@@", chunk)
            if m:
                html_parts.append(figure_html(lang, int(m.group(1)), fig))
            elif re.search(r"^\|\s*(Hipoteza|Hypothesis)\s*\|", chunk, re.M):
                rest = re.sub(r"(?m)^\|.*\|[ \t]*\n?", "", chunk).strip()
                if rest:
                    html_parts.append(render_md(rest, S, lang, cur, src))
                html_parts.append(f'<p class="more"><a href="{href(cur, lang + "/hypotheses/", S)}">{esc(T["all_hyp"])} <span aria-hidden="true">→</span></a></p>')
            else:
                html_parts.append(render_md(chunk, S, lang, cur, src))
        body_secs.append(f'<section id="{sid}"><h2>{esc(heading)}</h2>{"".join(html_parts)}{faq_html}</section>')
    body = "".join(parts) + f'<nav class="toc" aria-label="{esc(T["on_page"])}">{"".join(toc)}</nav>' + "".join(body_secs)
    return page(S, lang, cur, f'{T["how_title"]} · Exocortex R&D', T["how_desc"], body, alt_map(lambda l: f"{l}/how-it-works/"), nav_key="how")


def page_hyps(S, lang, dossiers, fig):
    T = UI[lang]
    cur = f"{lang}/hypotheses"
    cards = "".join(hyp_card(S, lang, cur, d) for d in dossiers)
    body = (f'<h1>{esc(T["hyp_title"])}</h1><p class="lead">{esc(T["hyp_intro"])}</p>'
            f'<div class="hyps">{cards}</div>'
            f'<p class="more">{esc(T["hyp_machine_p"])} <a href="{href(cur, "hypotheses.json", S)}">{esc(T["hyp_machine"])} (JSON)</a></p>')
    return page(S, lang, cur, f'{T["hyp_title"]} · Exocortex R&D', T["hyp_desc"], body, alt_map(lambda l: f"{l}/hypotheses/"), nav_key="hyp")


def phase_pill(lang, st):
    return pill({"done": "ok", "working": "ok", "progress": "prep", "planned": "plan"}[st], UI[lang]["phase_state"][st])


def page_status(S, lang, roadmaps, state, fig):
    T = UI[lang]
    cur = f"{lang}/status"
    secs = []
    for p in roadmaps[lang]:
        st = phase_state(p, state)
        pct = round(100 * p.done / len(p.tasks)) if p.tasks else 0
        rows = "".join(
            f'<tr><td class="mono">{esc(t.id)}</td><td>{esc(t.title)}</td>'
            f'<td>{pill({"done": "ok", "doing": "prep", "todo": "plan"}[t.status] if t.status in ("done", "doing", "todo") else "plan", T["task_state"].get(t.status, t.status))}</td>'
            f'<td class="mono">{esc(t.estimate)}</td></tr>' for t in p.tasks)
        goal = md_inline(p.goal) if p.goal else ""
        secs.append(
            f'<details class="phase"><summary><span class="code">{esc(p.id)}</span><span class="pt">{esc(p.title)}</span>{phase_pill(lang, st)}'
            f'<span class="pbar" role="img" aria-label="{p.done} / {len(p.tasks)} {esc(T["done_of"])}"><i style="width:{pct}%"></i></span>'
            f'<span class="cnt mono">{p.done}/{len(p.tasks)}</span></summary>'
            f'<p>{goal}</p><div class="tw"><table><thead><tr><th>ID</th><th>{esc(T["task"])}</th><th>{esc(T["state"])}</th><th>{esc(T["estimate"])}</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div></details>')
    body = (f'<h1>{esc(T["status_title"])}</h1><p class="lead">{esc(T["status_intro"])}</p>'
            f'<p class="note">{esc(T["status_note"])} {esc(T["as_of"])} {esc(S.asof)}.</p>'
            f'<div class="phases">{"".join(secs)}</div>')
    return page(S, lang, cur, f'{T["status_title"]} · Exocortex R&D', T["status_desc"], body, alt_map(lambda l: f"{l}/status/"), nav_key="status")


def dossier_blocks(S, lang, cur, d, key, md_html) -> str:
    """Extra generated content that follows or replaces the authored text of a section."""
    T = UI[lang]
    if key == "prereg":
        extra = ""
        card = d.cards.get(lang)
        if card:
            fr = card.front
            extra += (f'<div class="panel"><p><strong>{esc(T["card_open"])}</strong> · {esc(T["card_version"])} {esc(str(fr.get("version", "")))}'
                      + (f' · {esc(T["card_hash"])} <code>{esc(str(fr.get("prereg_hash")))}</code>' if fr.get("prereg_hash") else "")
                      + f'</p><details open><summary>{esc(card.title)}</summary>{render_md(strip_h1(card.body), S, lang, cur, card.file)}</details></div>')
        if d.prereg:
            rows = "".join(f'<tr><td class="mono">{esc(str(e.get("version", "")))}</td><td class="mono">{esc(str(e.get("sha256", e.get("hash", ""))))}</td>'
                           f'<td class="mono">{esc(str(e.get("date", "")))}</td></tr>' for e in d.prereg)
            extra += (f'<h3>{esc(T["prereg_entries"])}</h3><div class="tw"><table><thead><tr><th>{esc(T["card_version"])}</th><th>{esc(T["card_hash"])}</th>'
                      f'<th>{esc(T["date"])}</th></tr></thead><tbody>{rows}</tbody></table></div>')
        return md_html + extra
    if key == "data":
        if not d.files:
            return md_html + f'<p class="note">{esc(T["no_files"])}</p>'
        rows = ""
        for f in d.files:
            desc = T["fdesc"].get(f.name, "")
            rows += (f'<tr><td class="mono"><a href="{href(cur, f"data/{d.slug}/{f.name}", S)}" download>{esc(f.name)}</a></td><td>{esc(desc)}</td>'
                     f'<td class="mono r">{fmt_size(f.size)}</td><td class="mono r">{fmt_num(f.records, lang)}</td>'
                     f'<td class="mono sha">{f.sha256}</td></tr>')
        return (md_html + f'<h3>{esc(T["data_files"])}</h3><div class="tw"><table class="files"><thead><tr><th>{esc(T["file"])}</th><th>{esc(T["what"])}</th>'
                f'<th>{esc(T["size"])}</th><th>{esc(T["records"])}</th><th>{esc(T["sha"])}</th></tr></thead><tbody>{rows}</tbody></table></div>'
                f'<p class="note">{esc(T["files_note"])} <a href="{href(cur, f"data/{d.slug}/SHA256SUMS", S)}">{esc(T["files_all"])}</a></p>')
    if key == "runs" and d.runs.get(lang):
        items = "".join(
            f'<details class="item"><summary><span class="mono">{esc(str(i.front.get("run_id", "")))}</span> · {esc(str(i.front.get("date", "")))} · '
            f'{esc(str(i.front.get("sample", "")))} · {esc(str(i.front.get("configuration", "")))}</summary>{render_md(strip_h1(i.body), S, lang, cur, i.file)}</details>'
            for i in d.runs[lang])
        return f'<div class="items">{items}</div>'
    if key == "gates" and d.gates.get(lang):
        items = "".join(
            f'<details class="item" open><summary>{esc(str(i.front.get("gate", "")))} · {pill("ok" if str(i.front.get("decision")) == "GO" else "prep", str(i.front.get("decision")))} · '
            f'{esc(str(i.front.get("date", "")))}</summary>{render_md(strip_h1(i.body), S, lang, cur, i.file)}</details>' for i in d.gates[lang])
        return f'<div class="items">{items}</div>'
    return md_html


# The file keeps "result it rests on" and "strength of evidence" for the checks; the page does not show them
# (the reader is already in the dossier, where the results and the evidence are).
HIDDEN_APPLICATION_COLUMNS = (2, 3)


def drop_table_columns(md: str, drop: tuple[int, ...]) -> str:
    """Remove columns (0-based) from every five-column Markdown table in ``md``."""
    out = []
    for line in md.split("\n"):
        if line.lstrip().startswith("|"):
            cells = line.strip().strip("|").split("|")
            if len(cells) == 5:
                line = "| " + " | ".join(c.strip() for i, c in enumerate(cells) if i not in drop) + " |"
                if all(re.fullmatch(r":?-{3,}:?", c.strip()) for c in cells):
                    line = "|" + "---|" * (5 - len(drop))
        out.append(line)
    return "\n".join(out)


def applications_block(S, lang, cur, d) -> str:
    """The approved applications section (F8.1), or a notice while it waits for a new approved draft."""
    T = UI[lang]
    if d.applications_state == "absent":
        return f'<p class="note">{esc(T["apps_absent"])}</p>'
    item = d.applications.get(lang) if d.applications_state == "current" else None
    if item is None:
        return f'<p class="note">{esc(T["apps_updating"])}</p>'
    body = re.sub(r"^## ", "### ", strip_h1(item.body), flags=re.MULTILINE)  # inside a section with its own h2
    body = drop_table_columns(body, HIDDEN_APPLICATION_COLUMNS)
    main, nerd = body, ""
    m = re.search(rf"^### {re.escape(T['apps_nerd'])}\s*$", body, re.MULTILINE)
    if m:  # the technical details sit in a framed box below the plain-language text
        main, nerd = body[: m.start()], body[m.start():]
    out = render_md(main, S, lang, cur, item.file)
    if nerd:
        out += f'<aside class="nerd">{render_md(nerd, S, lang, cur, item.file)}</aside>'
    return out + f'<p class="note">{esc(T["apps_note"])}</p>'


def bibtex(S, lang, d, title) -> tuple[str, str]:
    year = (d.updated or S.asof)[:4]
    url = f"{S.base}/{lang}/hypotheses/{d.slug}/"
    key = f"exocortexrd{year}{re.sub('[^a-z0-9]', '', d.slug)[:24]}"
    bib = (f"@misc{{{key},\n  author = {{Exocortex R\\&D}},\n  title = {{{title}}},\n  year = {{{year}}},\n"
           f"  version = {{{d.version}}},\n  url = {{{url}}},\n  note = {{Dossier of hypothesis {d.roadmap}}}\n}}")
    plain = f"Exocortex R&D ({year}). {title}. Dossier of hypothesis {d.roadmap}, version {d.version}. {url}"
    return plain, bib


def page_dossier(S, lang, d):
    T = UI[lang]
    bl = d.by_lang[lang]
    cur = f"{lang}/hypotheses/{d.slug}"
    src = f"dowody/{lang}/experiments/{d.slug}/overview.md"
    secs, toc = [], []
    n = 0
    # business applications come first, on every hypothesis page: what the reader can do with it
    n += 1
    toc.append(f'<li><a href="#s-applications">{esc(T["apps_h"])}</a></li>')
    secs.append(f'<section id="s-applications" class="dsec"><h2><span class="n" aria-hidden="true">{n}</span>'
                f'{esc(T["apps_h"])}</h2>{applications_block(S, lang, cur, d)}</section>')
    keyed = [(SEC_KEYS[i] if i < len(SEC_KEYS) else f"s{i + 1}", heading, md) for i, (heading, md) in enumerate(bl["sections"])]
    # deviations and change history are for the careful reader: near the end, after the sources, before "how to cite"
    keyed.sort(key=lambda t: t[0] == "changes")
    for key, heading, md in keyed:
        sid = f"s-{key}"
        n += 1
        toc.append(f'<li><a href="#{sid}">{esc(heading)}</a></li>')
        md_html = render_md(md, S, lang, cur, src)
        # runs/gates/results with live items replace the "nothing yet" paragraph
        full = dossier_blocks(S, lang, cur, d, key, md_html)
        secs.append(f'<section id="{sid}" class="dsec"><h2><span class="n" aria-hidden="true">{n}</span>{esc(heading)}</h2>{full}</section>')
    plain, bib = bibtex(S, lang, d, bl["title"])
    total_records = next((f.records for f in d.files if f.name == "manifest.csv"), None)
    prereg_txt = T["prereg_frozen"] if (d.cards.get(lang) and d.cards[lang].front.get("prereg_hash")) or d.prereg else T["prereg_none"]
    stage_name = T["stages"][model.STAGES[min(d.stage, len(model.STAGES) - 1)]]
    facts = [
        (T["kf_status"], pill(PILL_KIND[d.status], T["hstatus"][d.status])),
        (T["kf_stage"], esc(stage_name if d.status in ("preparation", "running") else "–")),
        (T["kf_scale"], esc(T["tiers"].get(d.tier, d.tier))),
        (T["kf_task"], f'<span class="mono">{esc(d.roadmap)}</span>'),
        (T["kf_prereg"], esc(prereg_txt)),
        (T["kf_version"], f'<span class="mono">{esc(d.version)}</span>'),
        (T["kf_updated"], f'<span class="mono">{esc(d.updated)}</span>'),
        (T["kf_data"], esc(f'{T["files_word"]} {len(d.files)}, {T["records_word"]} {fmt_num(total_records, lang)}') if d.files else "–"),
    ]
    kf = "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in facts)
    hist = (f'<a href="{esc(repo_url_for(S, src))}" target="_blank" rel="noopener">{esc(T["history"])}</a>' if S.repo_public
            else f'<span class="repo-pending" title="{esc(T["repo_pending"])}">{esc(T["history"])}</span>')
    cite = (f'<section id="s-cite" class="dsec cite"><h2>{esc(T["cite_h"])}</h2><p>{esc(T["cite_p"])}</p><pre id="cite-plain">{esc(plain)}</pre>'
            f'<div class="bib"><div class="bib-h"><span class="mono">{esc(T["bibtex"])}</span><button class="copy" type="button" data-target="cite-bib" data-done="{esc(T["copied"])}">{esc(T["copy"])}</button></div>'
            f'<pre id="cite-bib">{esc(bib)}</pre></div><p class="note">{esc(T["cite_doi"])} · {hist}</p></section>')
    toc.append(f'<li><a href="#s-cite">{esc(T["cite_h"])}</a></li>')
    body = (f'<article class="dossier-wrap"><header class="dh"><p class="eyebrow">{esc(T["dossier"])} · {esc(d.roadmap)}</p>'
            f'<h1>{esc(bl["title"])}</h1><p class="lead">{esc(bl["tagline"])}</p>{track(lang, d)}<dl class="facts">{kf}</dl></header>'
            f'<div class="dgrid"><aside class="dtoc"><details class="tocd" open><summary>{esc(T["on_page"])}</summary><ol>{"".join(toc)}</ol></details></aside>'
            f'<div class="dmain">{"".join(secs)}{cite}</div></div></article>')
    ld = {"@context": "https://schema.org", "@type": "Dataset" if d.files else "CreativeWork", "name": bl["title"], "description": bl["tagline"],
          "url": f"{S.base}/{cur}/", "inLanguage": lang, "version": d.version, "creator": {"@type": "Organization", "name": "Exocortex R&D"}}
    if d.files:
        ld["distribution"] = [{"@type": "DataDownload", "contentUrl": f"{S.base}/data/{d.slug}/{f.name}", "encodingFormat": f.path.suffix.lstrip("."),
                               "sha256": f.sha256} for f in d.files]
    return page(S, lang, cur, f'{bl["title"]} · Exocortex R&D', bl["tagline"], body, alt_map(lambda l: f"{l}/hypotheses/{d.slug}/"),
                extra_head=f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>', nav_key="hyp", og_type="article", wide=True)


def page_404(S, lang="en"):
    T = UI[lang]
    S.root_abs = True  # a 404 page is served from any depth, so it links with absolute paths
    body = (f'<h1>{esc(T["notfound_t"])}</h1><p class="lead">{esc(T["notfound_p"])}</p>'
            f'<p class="cta"><a class="btn primary" href="/{lang}/hypotheses/">{esc(T["nav_hyp"])}</a><a class="btn" href="/{lang}/">{esc(T["brand"])}</a></p>')
    out = page(S, lang, "en", T["notfound_t"] + " · Exocortex R&D", T["notfound_p"], body, {"en": "en/", "pl": "pl/"})
    S.root_abs = False
    return out


def root_index(S) -> str:
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Exocortex R&amp;D</title>
<meta name="description" content="A public lab where we test ideas about AI and show the whole path to the result, even when it goes badly.">
<link rel="canonical" href="%(base)s/en/">
<link rel="alternate" hreflang="en" href="%(base)s/en/"><link rel="alternate" hreflang="pl" href="%(base)s/pl/"><link rel="alternate" hreflang="x-default" href="%(base)s/en/">
<meta name="robots" content="noindex,follow">
<meta name="color-scheme" content="light dark">
<script>try{if(localStorage.getItem('lab-lang')==='pl'){location.replace('pl/')}else{location.replace('en/')}}catch(e){location.replace('en/')}</script>
<noscript><meta http-equiv="refresh" content="0; url=en/"></noscript>
<style>body{font:17px/1.6 system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 1rem}a{color:#06695B}@media (prefers-color-scheme:dark){body{background:#0E1320;color:#E9EDF6}a{color:#5ED8C4}}</style>
</head>
<body><p><a href="en/">Exocortex R&amp;D</a> · <a href="pl/">Polski</a></p></body>
</html>
""" % {"base": S.base}


# ------------------------------------------------------------------ main ----
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--docs", required=True, type=Path, help="the dowody/ folder")
    ap.add_argument("--corpora", type=Path, help="lab/corpora/ (data files of experiments)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--base-url", default="https://lab.exocortex.zone")
    ap.add_argument("--main-site", default="https://exocortex.zone")
    ap.add_argument("--repo-url", default="https://github.com/hretheum/exocortex-public")
    ap.add_argument("--repo-public", action="store_true", help="link to repository files (leave off while the repository is private)")
    ap.add_argument("--fonts", choices=["local", "google"], default="local")
    ap.add_argument("--index-links", action="store_true", help="link to .../index.html (for static preview hosts)")
    ap.add_argument("--state", type=Path, help="JSON with phase labels, e.g. {\"F0\": \"working\"}")
    ap.add_argument("--asof", default=dt.date.today().isoformat())
    ap.add_argument("--extra-assets", type=Path, help="folder copied over assets/ (e.g. fonts.css and fonts/)")
    ap.add_argument("--cname", default="", help="custom domain to write into CNAME (GitHub Pages)")
    a = ap.parse_args()

    S = Site(a)
    if S.out.exists():
        shutil.rmtree(S.out)
    S.out.mkdir(parents=True)
    dossiers = model.load_dossiers(a.docs, a.corpora)
    roadmaps = {l: model.load_roadmap(a.docs, l) for l in LANGS}
    state = json.loads(a.state.read_text(encoding="utf-8")) if a.state else {}
    apply_dynamic(dossiers, roadmaps, state)
    fig = infog.build_all()

    # assets
    shutil.copytree(HERE / "assets", S.out / "assets")
    if a.extra_assets:
        shutil.copytree(a.extra_assets, S.out / "assets", dirs_exist_ok=True)
    if a.fonts == "google":
        shutil.rmtree(S.out / "assets" / "fonts", ignore_errors=True)
        (S.out / "assets" / "fonts.css").unlink(missing_ok=True)
    tpl = (HERE / "site.css.tpl").read_text(encoding="utf-8")
    css = (tpl.replace("/*@@TOKENS_LIGHT@@*/", infog.token_block(infog.TOKENS_LIGHT))
              .replace("/*@@TOKENS_DARK@@*/", infog.token_block(infog.TOKENS_DARK)).replace("/*@@IG@@*/", infog.class_rules()))
    (S.out / "assets" / "site.css").write_text(css, encoding="utf-8")
    S.written += [str(p.relative_to(S.out)) for p in (S.out / "assets").rglob("*") if p.is_file()]

    for lang in LANGS:
        S.write(f"{lang}/index.html", page_home(S, lang, dossiers, fig))
        S.write(f"{lang}/how-it-works/index.html", page_how(S, lang, dossiers, fig, a.docs))
        S.write(f"{lang}/hypotheses/index.html", page_hyps(S, lang, dossiers, fig))
        S.write(f"{lang}/status/index.html", page_status(S, lang, roadmaps, state, fig))
        for d in dossiers:
            if lang in d.by_lang:
                S.write(f"{lang}/hypotheses/{d.slug}/index.html", page_dossier(S, lang, d))

    # data files, checksums, machine-readable index
    index = []
    for d in dossiers:
        if d.files:
            sums = ""
            (S.out / "data" / d.slug).mkdir(parents=True, exist_ok=True)
            for f in d.files:
                shutil.copyfile(f.path, S.out / "data" / d.slug / f.name)
                S.written.append(f"data/{d.slug}/{f.name}")
                sums += f"{f.sha256}  {f.name}\n"
            S.write(f"data/{d.slug}/SHA256SUMS", sums)
        index.append({"slug": d.slug, "roadmap": d.roadmap, "status": d.status, "stage": model.STAGES[min(d.stage, 5)] if d.status in ("preparation", "running") else None,
                      "version": d.version, "updated": d.updated,
                      "title": {l: d.by_lang[l]["title"] for l in d.by_lang}, "url": {l: f"{S.base}/{l}/hypotheses/{d.slug}/" for l in d.by_lang},
                      "files": [{"name": f.name, "bytes": f.size, "records": f.records, "sha256": f.sha256, "url": f"{S.base}/data/{d.slug}/{f.name}"} for f in d.files]})
    S.write("hypotheses.json", json.dumps({"generated": S.asof, "hypotheses": index}, ensure_ascii=False, indent=2))

    S.write("index.html", root_index(S))
    S.write("404.html", page_404(S))
    S.write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {S.base}/sitemap.xml\n")
    urls = ["en/", "pl/"] + [f"{l}/{p}/" for l in LANGS for p in ("how-it-works", "hypotheses", "status")] + [
        f"{l}/hypotheses/{d.slug}/" for l in LANGS for d in dossiers if l in d.by_lang]
    def alt_of(u):
        if u.startswith("en/"):
            return "pl/" + u[3:]
        return "en/" + u[3:]
    sm = "".join(f'<url><loc>{S.base}/{u}</loc><xhtml:link rel="alternate" hreflang="{u[:2]}" href="{S.base}/{u}"/>'
                 f'<xhtml:link rel="alternate" hreflang="{alt_of(u)[:2]}" href="{S.base}/{alt_of(u)}"/></url>' for u in urls)
    S.write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            f'xmlns:xhtml="http://www.w3.org/1999/xhtml">{sm}</urlset>\n')
    S.write(".nojekyll", "")
    if a.cname:
        S.write("CNAME", a.cname + "\n")
    print(json.dumps({"pages": len([w for w in S.written if w.endswith(".html")]), "files": len(S.written), "dossiers": len(dossiers)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
