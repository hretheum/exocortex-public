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

The owner's steps, in this order: approval of the test card `toy-length` (the first experiment's card, [F3.4](roadmap/F3/F3.4-hypothesis-card.md), is already approved and frozen), and then a review of the code and documents with the reviewed files marked `human_validated`.

The on-demand units (F2.9) and rating in the interface (F2.10) are ready, so the quick test can start. The draft of the applications section of "Intent or fact" waits for approval in the interface (F8.1). The lab's graph package (F8.2) is in the repository in the version with the Polish summaries and checked on a fresh clone.

Work: the quick test on the tuning sample and the blind rating page (F3.6). Independently of the first experiment, the opportunity radar runs every week (F5.1 to F5.3).

The main repository has been public since 29 September. The site lab.exocortex.zone (F6.4) works: it is built by GitHub Actions, with a custom domain and HTTPS, and refreshed every hour. Today it shows three hypothesis dossiers, the roadmap status and the infographics, and the text "How Exocortex R&D works" will appear once that document is published.

In parallel: phase [F8](roadmap/F8-interactive-lab.md), described in the document [The interactive lab: applications, questions and GraphRAG](06-interactive-lab-design.md). First comes the business applications section on the hypothesis page (F8.1), then public questions turned into derived hypotheses (F8.6 to F8.9), and last the GraphRAG interface: its graph package is built (F8.2), and the question service and page (F8.3 to F8.5) need decisions on hosting and budget.

## 2026-09-30

### Desk: menu counters and tiles instead of wide tables (F2.11)

The desk menu shows next to "Queue" and "Ocena na ślepo" how much waits for a decision and how many claims wait for a rating; the counters refresh after every action and when the tab comes back, and disappear at zero. On the rating screen rated items move into a folded list from which a rating can be changed. Wide tables on the desk and on the lab site become tiles: one row is one tile with a title from the first column and "heading: value" pairs. The metrics table of the "Intent or fact" card was 799 pixels wide in a 724 pixel box on the site and cut off its last column; now it fits at 1280 and 400 pixels, in the dark theme too. On the way, two gate tests that still expected the semantic comparison for lab output after it was switched off now check the new rule.

### Graph package with Polish summaries published, F8.2 done

The second version of the package (`v1-0bcb2ed5a3cd`, 6.6 MB): 4956 documents (2478 abstracts and 2478 Polish summaries by the engine), 186 claims with quotes, 2664 edges. It replaced the first version in the repository. The `verify` command on a fresh clone of the repository passes, so the task has the status "done".

### Quick test of the first experiment: extraction done, rating pending (F3.6)

The extraction on the tuning sample (20 documents, model qwen3.6-35b-a3b) finished without errors in both variants: 20 of 20 documents, 194 claims without the mode field and 193 with it, 377 claims in all that can be rated. The blind rating page is drawn (10 repeats to check the rater's agreement with themselves, as the card requires) and waits for the rater on the "Blind rating" screen. Once the tuning sample is rated we open the control set, and then the G1 decision is written. The task has the status "in progress".

### Roadmap written for an outside reader

Every roadmap file now opens with a visible status block (done, in progress or to do, with what exactly is ready and what the task waits for), a short "In brief" and a "Why", written without jargon. Phase files have a "Status" column in their task table, and the main document has a "Where we are" section. The description of the first experiment in the main document is corrected: the corpus is arXiv abstracts, not official documents.

### Lab data no longer compared with the private corpus

The similarity check held experiment tables and results because the private corpus contains the same public papers, so the comparison found a paper next to itself. Lab data (`data/**`) now has its own class: the literal scan stays, the semantic comparison goes. The lab reads only sources on the allowlist, and the nightly isolation test checks that it cannot reach the private instance. Pages written by hand in the vault keep their existing checks.

### Polish summaries in the graph package (F8.2)

On 30 September the owner decided that the summaries and key findings the engine wrote in Polish from the CC0 abstracts go into the graph package together with them. They are the engine's own output and are already published in full in `lab/corpora/intent-vs-fact/corpus.jsonl`, so the package reveals nothing beyond what is public. `lab/sources.yaml` has a separate `corpus_summary` entry with the basis for redistribution, and a test checks that the basis is recorded for both kinds of text. The description in the design document (06) is corrected. Next step: rebuild the package (version 2), approve it on the desk and check it on a fresh clone.

### Lab jobs on demand (F2.9)

New units run on the server: one sample of one experiment (`exocortex-lab-run@<experiment>_<sample>`, also in a form that only adds the jobs to the queue), working through the queue grouped by model (`exocortex-lab-work`, with a nightly timer that is in the repository but not switched on) and the steps of blind rating (`exocortex-lab-blind@<step>_<experiment>_<sample>`: draw, load ratings, summary, publish). The unit for drafts of the applications section is installed too. The new units have the same network and secrets as the radar and no way to download anything. The deployment description has a rule: every recurring job can be started by hand with one command, and a test in the repository checks that every timer has such a counterpart described in the documentation. The toy experiment went through `run`, `work` and `blind` on the server. A bug came up on the way: the toy experiment drew its samples again from the current documents every time, and these had changed since the first draw, so every run of it failed. It now uses the stored samples. The nightly isolation test still passes. The task is done.

### Blind rating in the owner's interface (F2.10)

The owner's interface has a "Blind rating" screen: one claim at a time, with its quote and the text around it, without the configuration name, in the random order of the draw. It has buttons for the categories and for the mode in the source, a comment field, keys (1 to 8, Enter, arrows) and resuming: every rating is saved at once, and after a break the screen returns to the first unrated item. The header shows only how many items are rated and how many are left. The interface has no access to the lab database. It reads the rating page the lab prepared, and when rating is finished the ticks go onto the page in Obsidian. The lab reads that page with the same code as a page filled in by hand, which stays as the fallback. On the toy experiment 4 claims and 2 repeats were rated in the interface (test ratings by the agent, not a judgement of the content), and the same ratings ticked by hand on the page gave identical results: shares, Wilson intervals, bootstrap differences and the rater's agreement with themselves. The task is done.

### Draft of the applications section of "Intent or fact" waits for approval (F8.1)

After the card was frozen the checksum of the section's sources changed, so the hypothesis page shows that the section is being updated. The lab generated a new draft on the server (model qwen3.6-35b-a3b, at the first attempt), and the draft passes the full checker. It waits in the owner's interface as a new draft from the lab. It reaches the documents only after approval and publication, and only if its text has not changed. F8.1 stays in progress until that approval.

### Lighter form of the graph package (F8.2)

While the first version of the package waited for review, every publication took the gate almost 20 minutes, because the semantic comparison processed vectors written in hex as text. The vectors are now in grayscale PNG images, one row of pixels per document, with the same 8-bit numbers. The titles, like the texts, stay in the corpus file. The new version `v1-675457aaecbd` takes 3.4 MB instead of 6.1 MB and replaced the previous one in the lab's folder, and two builds from the same data gave the same hash. In this form every vector keeps a cosine similarity of at least 0.998 to the full one.

## 2026-09-29

### First build of the graph package (F8.2)

The lab has an on-demand job that builds the graph package from its database into the folder the publisher reads. The first build gave version `v1-9f3e6a3ae962`, 6.1 MB: 2478 abstracts with embeddings of 1024 dimensions and 99 claims with verbatim quotes from the extractor's test run. A second build from the same data gave the same hash. The Polish summaries (2478) and the 87 claims taken from them stayed out, because `lab/sources.yaml` records no basis for redistribution for them. The package now goes through the gate like any publication.

### Graph package script: build and check (F8.2)

The script `lab/graph_package.py` builds the package from the lab database and checks it from its files alone. The check needs only Python: it computes the checksums and the hash of the whole package and checks every reference between the files, and with the corpus texts also every quote. The tests show that two builds from the same data give identical bytes. They also show that the check finds a corrupted file and a reference to a document that does not exist, and that a corpus without a recorded basis for redistribution is left out. The basis for the arXiv abstracts (CC0) is recorded in `lab/sources.yaml`.

### Format of the public graph package (F8.2)

The lab's graph package has a fixed format. It holds the documents of the public corpora without repeating their texts, which are already in the repository, and the claims with verbatim quotes and their positions in the document. Relations with a type and a weight and embeddings of the documents stored as 8-bit numbers come on top. A file in the Frictionless Data format with checksums describes all of it. For 2478 abstracts the package should take about 6 MB, so it fits in the repository without extra tools. The choices and their reasons are in the [document on the interactive lab](06-interactive-lab-design.md).

### “How it works” rewritten for a business reader (F8.10)

The text in both languages starts with what the business reader gets from it, and the technical detail sits in boxes for data and machine learning teams below the main text. The owner marked the task as done. The reading test with two people from outside the project, named in the done condition, has not been carried out.

### First experiment's card frozen (F3.4)

The owner approved the hypothesis card "Intent or fact" in both languages, and the lab froze it and recorded the preregistration. The entry is in the repository, and the verification script on a fresh clone confirms its checksum. The first run on the corpus has not happened yet, so the order (card before measurement) is kept. Task F3.4 is done. Before the quick test (F3.6), the on-demand units (F2.9) and rating in the interface (F2.10) are still missing.

### Mechanisms the first experiment needs (F2.9, F2.10, F5.8, F5.9)

A readiness review before the first experiment showed four gaps that are not specific to "Intent or fact" but common to every experiment. Added to the roadmap: F2.9 (units `run`, `work` and `blind` on the server, every job on demand), F2.10 (blind rating in the owner's interface instead of a page in Obsidian), F5.8 (a retrieval experiment kind for F5.5 and F5.6) and F5.9 (an answer-format-conformity kind for F5.7). F3.6 now depends on F2.9 and F2.10. Judge calibration (F3.9), the error inventory (F3.8) and the report (F3.10) are already on the roadmap.

### Raw results export closed (F2.8)

On a fresh clone of the repository from GitHub, the script `lab/recompute.py` reproduced from the CSV files alone all 10 numbers of the toy experiment, the same ones its dossier shows. The data description (`datapackage.json`), missing until now, is published, so the task is done.

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
