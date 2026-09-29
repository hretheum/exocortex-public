---
id: progress
lang: en
counterpart: ../pl/03-progress.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# Progress

A log of what has been done under the [roadmap](02-roadmap.md), newest entries first. The "Next" section is at the top; below it come the days and entries, newest first. The state of each task is in the header of its file. Here we record what changed, what is left and what came up along the way.

## Next

The owner's steps, in this order: approval of the test card `toy-length` and of the hypothesis card of the first experiment ([F3.4](roadmap/F3/F3.4-hypothesis-card.md)), and then a review of the code and documents with the reviewed files marked `human_validated`.

Work: once the card is frozen, the quick test on the tuning sample and the blind rating page (F3.6). Independently of the first experiment, the opportunity radar runs every week (F5.1 to F5.3).

The main repository has been public since 29 September. The site lab.exocortex.zone (F6.4) works: it is built by GitHub Actions, with a custom domain and HTTPS, and refreshed every hour. Today it shows three hypothesis dossiers, the roadmap status and the infographics, and the text "How Exocortex R&D works" will appear once that document is published.

In parallel: phase [F8](roadmap/F8-interactive-lab.md), described in the document [The interactive lab: applications, questions and GraphRAG](06-interactive-lab-design.md). First comes the business applications section on the hypothesis page (F8.1), then public questions turned into derived hypotheses (F8.6 to F8.9), and last the GraphRAG interface (F8.2 to F8.5), which needs decisions on hosting and budget.

## 2026-09-29

### The business applications section (F8.1)

The lab has a command that composes the "Business applications" section of a hypothesis in both languages, and a checker that rejects it when a table row does not point to a result of the dossier, the label is not the one the rule computes, the text has a number that is not among the results, a name from the gate's list, an amount, a currency or a promise of profit, the language versions are not a pair, or the text fails the language check. The model writes only text. The strength-of-evidence label and the source checksum are inserted by code, following the rule described in the [interactive lab document](06-interactive-lab-design.md). The site shows the section right after the results, but only when it is approved and its checksum matches. After a result changes, it shows a notice that the section is being updated, and without the file the page looks as before. What is left is running the drafts for the three dossiers on the server and the owner's approval, so the task is in progress.

### The interactive lab design and the roadmap update (F8, F6.4, F7.4)

The new phase F8 gathers three extensions of the site: a business applications section built from the dossier with a strength-of-evidence label computed by a rule, public questions assessed for testability and turned into derived hypotheses (kinds: auxiliary, extension, replication, alternative explanation), and a GraphRAG interface with suggestion tiles, citations and a refusal when there is no evidence. The question interface needs a separate service, because GitHub Pages does not run code; a small container with the API on a separate subdomain is recommended, with the site staying on Pages. F7.4 now uses the F8.4 interface, and F6.4 is marked "in progress", because the site works and what is missing is a build triggered by publication.

### First publication of lab.exocortex.zone (F6.4)

After the repository was switched to public, the site build failed on the missing "How it works" text, which was not published yet. The generator no longer requires that text: the page then shows the infographics with a note that the description is being published, and two tests cover building without documents. The site is published at lab.exocortex.zone with a valid certificate.

### The lab: model, queue, cards and pages (F2.4 to F2.8)

The lab has two narrow paths out, both outside its internal network and reachable by its processes only through sockets in separate volumes. The first leads to the local model server: it lets through three calls and only the models on a list with their licenses. The second is for downloads: it accepts only https addresses on the list of allowed sources and keeps the pauses between requests their terms ask for. The isolation check tests both every night, next to checking that nothing on the lab network can connect to the private database or to the internet. The first night passed: the isolation check and the end-to-end test succeeded.

The lab database has experiment tables with a queue, samples and a control set lock that the database itself enforces. The toy experiment went through the whole path on the server: the jobs of two configurations ran in two blocks, and a second read of the control set ended in a refusal. The processors of hypothesis cards and gate decisions run every 15 minutes. An approved card gets an entry in the preregistration registry, and the publisher accepts that registry only when it gains lines. The lab exports raw results to CSV files with a description of the columns and compiles result pages: the roadmap status, the list of experiments and a dossier each. A script in the repository recomputes the numbers of the pages from the CSV files alone.

### The first experiment ready to be frozen (F3.2 to F3.5)

The corpus is in the lab graph: the abstract and the Polish summary of each of the 2478 papers, with checksums matching the manifest and with embeddings. The claim extractor is written anew and passed a test on five papers in both variants. The [hypothesis card](experiments/intent-vs-fact/hypothesis.md) has drawn samples, thresholds and gate criteria and is waiting for approval; the lab will not run the experiment before it is frozen. The blind sample tool passed a test on the toy experiment, and its confidence intervals agree with computations in other tools.

### Opportunity radar (F5.1 to F5.3)

The lab downloads four channels of signals: new arXiv papers in four categories, open-weight models, new public data sets and releases of the tools it uses. From them, every week, comes a radar page with hypotheses and plans from new papers, possible contradictions, dense topics and sudden rises. In the first full week the radar went through 198 papers. Models of three families each gave ten candidates a first score, on their own, with the selection template; the decision is a person's. The radar skips papers from experiment corpora and items the gate would count as personal data.

## 2026-09-28

### The lab site and hypothesis dossiers (F6.4, generator ready)

A generator of the static site lab.exocortex.zone now exists (folder `lab-site/`): `/en` and `/pl` versions, a description of how the lab works, the list of hypotheses with their statuses, a separate dossier for every hypothesis and the roadmap state read from the headers of the task files. A dossier is built like a short paper: abstract, question, preregistration, data with checksums and files to download, method, runs, results, gate decisions, deviations, reproduction, limitations and references. Four hypotheses have a dossier in `experiments/<slug>/overview.md`: “Intent or fact” (in preparation) and three planned ones (F5.5 to F5.7). Deployment has not started: exocortex.zone is Astro on GitHub Pages and occupies the only Pages site of the main repository, so lab.exocortex.zone needs a separate small repository, a DNS record and the main repository being made public. Details of the infrastructure the lab runs on were also removed from the documents.

### The “how it works” document and infographics (Exocortex R&D)

The document [How Exocortex R&D works](04-how-it-works.md) now exists in Polish and in English, together with eight infographics in the `img/` folders: overview, publishing gate, path of a hypothesis, latest hypotheses with their statuses, architecture, isolation of the lab, evidence trail and state of the work. The text is written for readers outside the field, promotes the lab and mentions the private Exocortex only as the project the lab grew out of. The same content is on the working project page, which will become the basis of a subpage on exocortex.zone (F6.4).

### The corpus of the first experiment (F3.1, F3.2)

arXiv is on the lab's allowlist of sources. The corpus of the "intent or fact" experiment has 2478 papers: the abstract downloaded again from arXiv and the Polish summary written by the engine. Five papers were left out because the publishing gate found a name from its private list in them; their ids stay private. Building the corpus on two machines gave identical checksums. The corpus is in the repository and in the lab. The order in this file is now: "Next" at the top, below it the entries, newest first.

### The lab starts (F2.1, F2.2)

The lab runs on the server on a network from which the private instance cannot be reached, which a separate test checks every night. Only what is on the public allowlist of sources gets into the lab; for now that is our own documents. Along the way, CI now tests the model router from the repository instead of an older PyPI release, and no longer rebuilds images on every document publication.

### A new F3 corpus

The F3 corpus changed from Polish official documents to the abstracts of the arXiv papers Exocortex has already downloaded, together with the Polish summaries written by the engine. There is no need to wait for documents to be collected, and the experiment gains a second question: whether our summaries turn hypotheses into facts.

### CI and the end-to-end test

CI on GitHub passes in full, except lint, which only reports. Schema validation runs on the real database image. The engine, database and gate images reach GHCR only after the scan.

The end-to-end test (loading notes, synthesis, wiki compilation, a GraphRAG question with citations) had never passed before. It needed a paid API key and had several bugs in the test itself. It now runs in two places. In CI a stand-in server answers instead of a model, so the test needs no key and checks the data flow. On the server the same test runs every night at 01:15 with a real local model, on a throwaway database kept in memory. The first run on the server found a bug: the local model sometimes answers with plain text instead of a tool call, and the GraphRAG question ended with an exception. The model router now accepts such a reply if the tool has one required text field. The second run passed in 25 seconds.

Along the way it turned out that a fresh database has no AGE graph, because no migration creates it. The database image now creates it on first start. The `docker compose` stack test now runs only by hand, because production runs on Quadlet units.

Known debt: the example ACME plugin has a synthesis perspective that the program never calls, and its query reads a column that does not exist. The test now uses the ordinary tag perspective. Tag extraction by the model is skipped, because the `scripts.extract_tags_batch` module did not make it into the export. Three unit tests are disabled in CI.

### The first F2 task (F2.3)

Task F2.3 does not need the server, so it was done right away, on the night of 27 to 28 September. The headers of hypothesis cards, run notes, gate decisions and task files have JSON Schemas. The `docschema` script checks them in CI and in the publisher, and an error names the file, the field and the reason. A run note template was added, and the README describes the layout of experiment folders.
