---
id: interactive-lab-design
lang: en
counterpart: ../pl/06-interactive-lab-design.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-29
  human_validated: false
---

# The interactive lab: applications, questions and GraphRAG

This document describes three extensions of the site lab.exocortex.zone: a section on business applications on the hypothesis page, public questions turned into derived hypotheses, and an interface where anyone can ask the graph questions. The tasks are in phase [F8](roadmap/F8-interactive-lab.md).

## Business applications on the hypothesis page

A reader of the page often does not ask about the method, but about what follows from it for their work. The section answers that without promising anything beyond the results. It is built from the dossier, not from imagination.

1. A separate file `experiments/<slug>/applications.md` in both languages is part of the experiment unit and goes out together with it. The site shows it as a section right after the results.
2. A lab processor builds the file from three inputs: the dossier (the question, the results, the gate decisions, the limitations), a short catalogue of general kinds of application (choosing a tool, cost versus quality, risk and compliance, product design, research operations) and, for hypotheses that are not tested yet, both outcome scenarios.
3. The model writes only the text. The strength of evidence is computed by a rule from the state of the dossier, not by the model. The labels are: "hypothesis, no evidence", "preliminary", "confirmed on a sample of N", "refuted on a sample of N", "inconclusive".
4. A checker rejects the draft if a row has no link to a result, if the label differs from the computed one, if the text has a number that is not in the results, a client name, an amount of money or a promise of profit, or if the text fails the language check.
5. The owner approves the draft with the field `human_validated`, like a hypothesis card. A change in the result invalidates the approval and starts a new draft.

The shape of the section:

| Part | Content |
|---|---|
| One sentence | what this hypothesis changes for an organisation |
| Applications | a table: the application, who benefits, which result it rests on, strength of evidence, conditions and limits |
| If we confirm, if we refute | for planned and in-preparation hypotheses: what to do in each of the two cases |
| What must not be concluded | the limitations in plain language |
| What to check next | links to derived hypotheses |

A negative result has business value too, because it says what not to invest in. The section says so plainly instead of skipping refuted hypotheses.

### The evidence rule and approval

The label is computed by the code in `exocortex/lab/evidence.py`, from the dossier files only. What counts is the latest gate decision approved in both languages (`human_validated: true`).

| State of the dossier | Label |
|---|---|
| no results and no approved decision | hypothesis, no evidence |
| results, but no approved decision | preliminary |
| a GO decision with every criterion in its table met | confirmed on a sample of N |
| a NO-GO decision with at least one criterion not met | refuted on a sample of N |
| PIVOT, NOT-NOW, CLOSED or a decision against its own numbers | inconclusive |

N is the smallest sample size among the results the decision names, taken from the file `metrics.csv` in the experiment's data. So the label never promises more than the weakest result. If a result or its sample size is missing, no draft is made.

The draft's header has the label, the source checksum (`source_hash`, SHA-256 of the results, decisions, card, runs and the fields `status` and `stage`), `publish: false` and `human_validated: false`. The owner approves each section separately: sets `publish: true` and `human_validated: true` in both versions. Both fields stay in the header, and the checker rejects a file where only one of them is `true`. The site computes the same checksum from the public dossier and shows the section only when it matches. After a result changes, the page shows a short notice that the section is being updated instead, and the lab composes a new draft with `python -m exocortex.lab applications draft <slug>`.

## Public questions and derived hypotheses

I recommend the name "derived hypothesis" and calling a user's submission a "question" until it passes assessment. The question is the input, and the derived hypothesis is what gets a card, a preregistration and gate decisions. It has a field `parent` (the parent hypothesis) and a field `kind`.

| Kind | Meaning | Example |
|---|---|---|
| auxiliary | challenges an assumption that the parent result stands on | whether the quality of paper summaries affected the result |
| extension | the same method, a different scope | another language or another corpus |
| replication | the same method on new data | a new sample of documents |
| alternative explanation | a different mechanism explains the result | document length instead of the mode field |

Example: a hypothesis is refuted, and the summaries of papers in Polish are sometimes mediocre. The question "did the result depend on the quality of the summaries" is an auxiliary hypothesis. It can be tested, because the same documents can be summarised by a top-tier model and the result compared with the original one.

The path of a question:

1. Input: a GitHub issue form next to the hypothesis. In the first version there is no server of our own, because the button "Ask a question" opens the form with the chosen hypothesis. Submissions are public by design.
2. A first filter: personal data, client material, spam, length and language. A submission with such content goes no further.
3. An assessment of testability by a lab processor, using the template from [F5.3](roadmap/F5-radar-and-experiments.md): whether it can be settled by measurement on public data, which metric, which threshold, what cost and how it relates to the parent hypothesis. The result: a verdict `testable`, `needs-rephrase`, `not-testable`, `duplicate` or `out-of-scope` with a reason, a cost class (S, M, L) and a draft card of the derived hypothesis.
4. Duplicates: similarity to existing questions and hypotheses merges submissions and counts support.
5. A human decision: the owner's G0, as for candidates from the radar. Public questions are the second source of candidates next to arXiv papers. An approved derived hypothesis enters the queue and goes through the same cycle: card, preregistration, test, gates.
6. A public page "Questions": every question with a number, a status and a reason, rejected ones included. The author gets an answer in the submission.

The order in the queue follows the assessment result, the number of supporters, the cost and how much the question concerns a negative result of the parent hypothesis. The lab runs nothing on the submitter's data and uses public data only.

## The GraphRAG interface

The user sees a page `/ask` and the same box next to every hypothesis:

1. A field for a question in natural language, and above it 8 suggestion tiles for the chosen hypothesis, for example "What we found", "Why the result is negative", "Which documents gave the largest spread", "What this means for my organisation", "How to reproduce it", "What we will check next".
2. An answer with citations: the claim, the source document and the verbatim quote. When the corpus has no evidence, the answer is "we do not have this" instead of a guess.
3. A switch between "search" and "graph", two retrieval modes on the same question. It shows the difference and is a practical counterpart of the experiment F5.5.
4. Next to the answer "we do not have this", a button "submit as a question to the lab" that feeds the question into the path from the previous section.

The tiles are built at site build time from the dossier and the graph: question templates for each kind of hypothesis, and questions from the section on limitations. Each tile is tried on the service and stays only if the answer has citations and passes the check. The owner can add tiles by hand.

The architecture has one direction of flow: the lab, the gate, a public graph package, the question service. The service never sees the lab database or the private network. It gets only what is already public (the claims, quotes, edges and vectors of public corpora) as a versioned file with a checksum in the repository. The model answers only from the retrieved passages.

GitHub Pages does not run code on the server side, so questions need a separate service. Three options:

| Option | Description | Assessment |
|---|---|---|
| A. An edge function | the site stays static, the API is a function at an edge provider | cheap, but a tight memory limit for the vector index |
| B. A small container at a provider | a service from an image built in CI, the graph package in SQLite with vectors, the model through an API with a monthly cap | recommended |
| C. The lab server behind a tunnel | the service on the same server as the lab | rejected, because it breaks the isolation rule |

I recommend option B. The site stays on GitHub Pages, and only the API leaves Pages, at `api.lab.exocortex.zone`, so the move away from Pages is partial. Safeguards: a per-address rate limit with anonymisation, bot protection on the provider's side, a hard monthly model budget with a cut-off, no storing of question text outside a deliberate submission, and no tracking. The public service uses a model through an API on public texts only, in line with the data class rule of [F6.2](roadmap/F6-scale-and-collaboration.md).

### The public graph package

The question service gets the graph as a package in the repository: the folder `dowody/data/graph/v1-<hash>/` with CSV files and two descriptions. The script `lab/graph_package.py` builds it from the lab database, on demand. It reaches the repository through the gate like any publication, as a whole or not at all.

| File | What it holds |
|---|---|
| `documents.csv` | documents of the public corpora: paper, kind of text, address, SHA-256 and length of the text |
| `claims.csv` | claims from finished experiment runs, only those with a verbatim quote |
| `quotes.csv` | the quote of every claim, exactly as in the document, with its start and end position |
| `edges.csv` | relations with a type and a weight, for example a claim `derived_from` a document |
| `vectors-0001.png`, … | embeddings of the documents, one row of pixels per document |
| `vectors.csv` | which image and row belongs to which document, and the scale of each vector |
| `datapackage.json` | description of the columns, keys and references in the Frictionless Data format |
| `manifest.json` | SHA-256 of every file and the hash of the whole package |

Choices and reasons:

1. The package does not repeat the texts or titles of the documents. They are already in the repository in the corpus files (`lab/corpora/`), and the package points to them by id and SHA-256. The repository does not keep two copies of the same texts, and the gate does not compare them again with every new version of the package.
2. The embeddings of the bge-m3 model have 1024 dimensions. The package stores every coordinate as an 8-bit number with one scale per vector, as a row of pixels of a grayscale PNG image, so 1 KB per document instead of 4 KB of 32-bit numbers. On the lab's data every vector keeps a cosine similarity of at least 0.998 to the full vector in this form, and the full vectors stay in the lab database. PNG is a binary format the gate knows and checks. The first version stored the vectors in hex in a text file, and then every publication took the gate more than ten minutes. The images are stored uncompressed, so the same numbers always give the same bytes. No file is larger than 2 MiB.
3. The build is byte-deterministic: a fixed order of rows, a fixed way of writing numbers and no build date in the files. The same data give the same hash. The name of the folder is the first 12 characters of the hash, and `latest.json` names the current version. A new version replaces the previous one in the tree of the repository, and older ones stay in the history.
4. Only kinds of text whose source records a basis for redistribution in `lab/sources.yaml` (the `redistribution` field) go into the package. Today these are the arXiv abstracts under CC0 and the engine's Polish summaries, which we published in full with the corpus and which the owner decided on 30 September 2026 to pass on. The lab's documents, cards, gate decisions and radar signals stay out too, because they are not corpora. The lab leaves out claims with personal data already during the build.
5. Checking needs only Python. The command `python lab/graph_package.py verify` computes the checksums and the hash and checks every reference between the files. With the `--corpora` option it also compares every quote with the text of the corpus.

## Place on the roadmap

A new phase [F8](roadmap/F8-interactive-lab.md) appears with nine tasks. [F7.4](roadmap/F7-public-demo.md) (the demo interface of the research knowledge base) now depends on F8.4, so that we do not build a second question interface.

The order: the business applications section (F8.1) comes first, because it needs no change in hosting. Next come public questions (F8.6 to F8.9), because they work on GitHub alone, and last the GraphRAG interface (F8.2 to F8.5), which needs decisions on hosting and budget.

## Owner decisions

1. The name of the object: "derived hypothesis" with kinds (recommended) or "sub-hypothesis".
2. Hosting of the API: a small container at a provider (recommended), an edge function or postponing.
3. The model for public answers: through an API with a monthly cap (an amount is needed) or only a local model, in which case there is no public access.
4. The input of questions: a GitHub form (recommended at the start, needs an account) or a form of our own on the site.
5. Approval of the applications section: every version by the owner (recommended) or publication after the check alone.
