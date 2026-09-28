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

The owner's steps: review of the code and the documents, and marking reviewed files with the `human_validated` field.

Work: hypothesis cards, gate decisions and experiment tables in the lab (F2.4 to F2.6), then the claim extractor in the lab (F3.3), which will turn the corpus into claims in the graph, and the hypothesis card of the first experiment (F3.4).

Switching the repository to public: after seven nights of the self-test in a row (counting from 29 September) and after the owner's review, according to the conditions in the roadmap.

Deploying the site lab.exocortex.zone (F6.4): the repository `lab-site-repo` is created. What is left is pushing the files from `lab-site/lab-site-repo/` into it (the workflow as `.github/workflows/pages.yml`), enabling GitHub Pages with the source “GitHub Actions” and a custom domain, and a `CNAME` DNS record for `lab`. The site will build once the main repository is public, and until then the workflow only checks whether it is visible.

## 2026-09-28

### The lab site and hypothesis dossiers (F6.4, generator ready)

A generator of the static site lab.exocortex.zone now exists (folder `lab-site/`): `/en` and `/pl` versions, a description of how the lab works, the list of hypotheses with their statuses, a separate dossier for every hypothesis and the roadmap state read from the headers of the task files. A dossier is built like a short paper: abstract, question, preregistration, data with checksums and files to download, method, runs, results, gate decisions, deviations, reproduction, limitations and references. Four hypotheses have a dossier in `experiments/<slug>/overview.md`: “Intent or fact” (in preparation) and three planned ones (F5.5 to F5.7). Deployment has not started: exocortex.zone is Astro on GitHub Pages and occupies the only Pages site of the main repository, so lab.exocortex.zone needs a separate small repository, a DNS record and the main repository being made public. Details of the infrastructure the lab runs on were also removed from the documents.

### The “how it works” document and infographics (Exocortex R&D)

The document [How Exocortex R&D works](04-how-it-works.md) now exists in Polish and in English, together with eight infographics in the `img/` folders: overview, publishing gate, path of a hypothesis, latest hypotheses with their statuses, architecture, isolation of the lab, evidence trail and state of the work. The text is written for readers outside the field, promotes the lab and mentions the private Exocortex only as the project the lab grew out of. The same content is on the working project page, which will become the basis of a subpage on exocortex.zone (F6.4).

### The corpus of the first experiment (F3.1, F3.2)

arXiv is on the lab's allowlist of sources. The corpus of the "intent or fact" experiment has 2478 papers: the abstract downloaded again from arXiv and the Polish summary written by the engine. Five papers were left out because the publishing gate found a name from its private list in them; their ids stay private. Building the corpus on two machines gave identical checksums. The corpus is in the repository and in the lab. The order in this file is now: "Next" at the top, below it the entries, newest first.

### F0.6 closed, the lab starts (F2.1, F2.2)

The owner accepted the measured values of the private corpus comparison in place of the original condition, so F0.6 is closed. The lab runs on the server on a network from which the private instance cannot be reached, which a separate test checks every night. Only what is on the public allowlist of sources gets into the lab; for now that is our own documents. Along the way, CI now tests the model router from the repository instead of an older PyPI release, and no longer rebuilds images on every document publication.

### Review and the calibrated threshold (F0.6)

The owner reviewed the list of 112 paragraphs close to protected material. We rewrote twelve because they gave away operational details, and he approved the rest as a shared topic. The gate now has a review page with links and quotes, and approvals for reviewed paragraphs, so a held file can be released without lowering the threshold. The calibrated threshold of 0.8584 is in force. The hold notification says how to start a review.

### A narrower protected corpus (F0.6)

Following the owner's decision, the protected corpus covers only client and private material. The semantic comparison now works well: at 5% false alarms it lets about 5% of paraphrases through, down from 15 to 17%. It also turned out that 36 of 100 published files have paragraphs close to protected material, mostly client material and private product material. The repository is private, so nothing has gone out. These files are on a private list, and the owner reviews them first before the switch. Until the review, the threshold of 0.93 is in force.

### Two-stage check (F0.6)

A local model judging the candidates did not improve the result: it lets 17% of paraphrases through and holds one in three published files. The cause is not the method but the scope of the private corpus. Our documents are closest to notes about Exocortex itself, and paper summaries are closest to newsletter summaries. In both cases it is the same content, but not client material. The comparison can tell a leak from a shared topic only once the protected corpus covers what really must not be published. For now the plain threshold of 0.93 is in force.

### Relative measures and a new F3 corpus

We tested two relative measures that were meant to tell a paraphrase from a text on the same topic better. Both did worse than plain similarity: they let more than twice as many paraphrases through and hold more of our documents. We rejected the hypothesis; the numbers are in the F0.6 task file. Calibration now compares all three measures on every run and checks the result on a held-out half of the data.

The F3 corpus changed from Polish official documents to the abstracts of the arXiv papers Exocortex has already downloaded, together with the Polish summaries written by the engine. There is no need to wait for documents to be collected, and the experiment gains a second question: whether our summaries turn hypotheses into facts.

### Calibrating the comparison with the private corpus (F0.6)

The previous calibration gave wrong thresholds because some of the public texts used to measure false alarms were copies of notes in the private corpus. This was the engine documentation, written from notes in the vault. The published documents themselves matched nothing. The negatives are now the published documents and the summaries of 2,486 arXiv papers. The summaries are public, so we removed them from the private corpus and rebuilt the index (65,415 paragraphs).

Result: the literal layer works without fault, the semantic layer poorly. At 5% false alarms it lets 12% of paragraphs rewritten by the model through, and at its calibrated threshold one in five published files would be held. There is no way yet for a person to release a held file. So until a decision, a threshold of 0.93 is in force, which holds none of the current documents. The F0.6 completion condition as worded cannot be met with this method. F0.6 stays in progress.

Along the way a deployment bug turned up: the nightly image update restarted the comparison service, and when another job finished at the same moment, the whole pod stopped and the service did not come back. The pod now has a "do not stop" policy and the service shuts down properly on a signal. Every gate job can also be run on demand, without waiting for the night, and every GitHub workflow has a manual run button.

### Server, CI and the end-to-end test

The steps on the list were done together with the owner. The gate key is in the GitHub secrets and the repository is pushed. The publisher (every 15 minutes), the nightly index rebuild and the nightly self-test run on the server as Quadlet units. The self-test on the server caught 73 of 73 cases. A trial with a file containing personal data ended in a hold, a lock trial stopped the publisher, and the notification arrived through Telegram.

CI on GitHub passes in full, except lint, which only reports. Schema validation runs on the real database image. The engine, database and gate images reach GHCR only after the scan.

The end-to-end test (loading notes, synthesis, wiki compilation, a GraphRAG question with citations) had never passed before. It needed a paid API key and had several bugs in the test itself. It now runs in two places. In CI a stand-in server answers instead of a model, so the test needs no key and checks the data flow. On the server the same test runs every night at 01:15 with a real local model, on a throwaway database kept in memory. The first run on the server found a bug: the local model sometimes answers with plain text instead of a tool call, and the GraphRAG question ended with an exception. The model router now accepts such a reply if the tool has one required text field. The second run passed in 25 seconds.

Along the way it turned out that a fresh database has no AGE graph, because no migration creates it. The database image now creates it on first start. The `docker compose` stack test now runs only by hand, because production runs on Quadlet units.

Known debt: the example ACME plugin has a synthesis perspective that the program never calls, and its query reads a column that does not exist. The test now uses the ordinary tag perspective. Tag extraction by the model is skipped, because the `scripts.extract_tags_batch` module did not make it into the export. Three unit tests are disabled in CI.

### The night of 27 to 28 September: F0, F1 and the first F2 task

The F0 and F1 work was done overnight by the agent, without the owner. Everything it did is waiting for review. The `human_validated` fields stay `false`.

#### F0. The gate

The `leakgate` scanner checks text, files with metadata (photos, PDF, office documents), archives, Python packages, container images and commit metadata. The denylist has 11,613 HMAC hashes. In container images the scanner checks the configuration and the files that come from the repository. Executables and compiled Python code in an image are allowed, but their strings are checked too. The self-test plants 73 cases and all of them are caught.

The private corpus comparison (`simcheck`) has a calibrated literal similarity threshold (0.40). The semantic part needs an embedding model on the server and is not calibrated yet. That is why F0.6 has the status `doing`.

The nightly self-test is ready, but the nights do not count yet: they start after the first run on the server and in CI. The old package release on PyPI is waiting to be deleted by the owner.

#### F1. The repository

A private working repository has been created. The engine code went through the export with an allowlist of paths, and the example configuration was written again with fictional data. The `code_en` tool found 604 fragments with Polish text in comments, docstrings and messages. 341 of them were changed. The rest were in English and had been flagged by a detector that was too sensitive and was fixed afterwards. Along the way, references to private task notes were removed.

Known debt: some user-facing strings (wiki headings, bot replies) are still in Polish, because they are program behaviour, not comments. Moving them to English needs language support in the engine and will be a separate task. The second debt is lint: `ruff` reports several hundred findings, so in CI that job reports but does not block.

The image and the package are built from an explicit list of paths. Package 0.2.0 passes the gate locally. CI on GitHub will run after the repository is first pushed and the gate key is added as a secret.

Documents have the `paritycheck` tool (PL and EN versions match) and `humanlint` (language model habits), plus a glossary of terms. The `humanlint` thresholds were set from texts written by people. The publisher and the rest of the gate run as a rootless Podman pod started by Quadlet, from their own container image, and are tested against a local repository. No source code goes to the server: the publisher keeps only a partial clone with the documents folder, and the Quadlet files come from the image. The engine jobs were moved to Quadlet as well. One step ran a script from the server's disk (language correction of wiki pages) and was removed until it gets its own image. The first publication moved the documents into the working repository. Pushing to GitHub and starting it on the server are for the owner.

#### F2. The first task

Task F2.3 does not need the server, so it was done right after F1. The headers of hypothesis cards, run notes, gate decisions and task files have JSON Schemas. The `docschema` script checks them in CI and in the publisher, and an error names the file, the field and the reason. A run note template was added, and the README describes the layout of experiment folders.
