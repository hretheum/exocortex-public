# Lab site (lab.exocortex.zone)

Static site of Exocortex R&D, built from the repository. Pages: `/en/` and `/pl/`
(home, how it works, hypotheses, one dossier per hypothesis, roadmap status). The root
page redirects to `/en/`.

Everything the site shows comes from files in this repository:

| Shown | Read from |
|---|---|
| hypothesis list, dossiers | `dowody/{en,pl}/experiments/<slug>/overview.md`, plus `hypothesis.md`, `run-*.md`, `gate-*.md` when they exist |
| preregistration register | `dowody/prereg.jsonl` |
| data files, checksums, downloads | `lab/corpora/<slug>/` and `dowody/data/<slug>/` |
| roadmap status | headers of `dowody/{en,pl}/roadmap/**` |
| how it works | `dowody/{en,pl}/04-how-it-works.md` |

A dossier is a short paper in a fixed order: abstract, question, preregistration, data, method,
runs, results, gate decisions, deviations and change log, reproduction, limitations, references.
A section with nothing in it yet says so. Files and checksums are listed with SHA-256 sums and
copied to `/data/<slug>/` with a `SHA256SUMS` file. `hypotheses.json` is the machine-readable list.

## Build

    pip install -r lab-site/requirements.txt
    python lab-site/build.py --docs dowody --corpora lab/corpora --out dist \
        --state lab-site/state.json --cname lab.exocortex.zone --repo-public --extra-assets <folder with fonts.css and fonts/>

Options: `--base-url` (default `https://lab.exocortex.zone`), `--repo-url`, `--fonts local|google`,
`--index-links` (links end in `index.html`, for static preview hosts), `--asof YYYY-MM-DD`.
Leave `--repo-public` off while the repository is private: links to repository files are then
shown as plain text with a note instead of a link.

The phase labels (`planned`, `progress`, `done`) are computed from the task statuses, which come from the
`status` field of each task file or, for phases whose tasks are listed inside the phase file, from its
`task_status` map. `lab-site/state.json` and the `--state` option are no longer used and are ignored.

The site loads nothing from third parties. Fonts (Bricolage Grotesque, Instrument Sans and JetBrains Mono,
SIL Open Font License 1.1) are served from `/assets/fonts`. The font files live in the deployment repository
(`assets/`), not here, because the publishing gate's byte scan raises false alarms on binary files; pass them
with `--extra-assets assets`. Without them the site falls back to system fonts.

## Hosting

exocortex.zone is the Astro documentation site served by GitHub Pages from this repository, and
a repository can serve only one Pages site. The lab site therefore lives in a second, small
repository that contains only the workflow and `state.json` from `lab-site/lab-site-repo/`:

1. Create a public repository (`lab-site-repo`), copy `lab-site/lab-site-repo/` into it and move `pages.workflow.yml` to `.github/workflows/pages.yml`.
2. Settings, Pages: source "GitHub Actions"; custom domain `lab.exocortex.zone`; enforce HTTPS.
3. DNS: a `CNAME` record `lab` pointing to `<github-user>.github.io`.
4. The workflow checks out this repository and builds the site every hour and on demand.
   It works once this repository is public.

The root redirect is a static page (GitHub Pages has no server-side redirects): a script
sends the visitor to `/en/`, or to `/pl/` if they chose Polish earlier, and a `noscript`
fallback does the same.

## Tests

    pytest tests/test_lab_site.py
