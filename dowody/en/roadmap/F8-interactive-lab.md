---
id: F8
lang: en
counterpart: ../../pl/roadmap/F8-interactive-lab.md
status: doing
task_status: {F8.1: doing, F8.10: done}
provenance: ai_authored
provenance_metadata: {agent: "Claude Sonnet 5.5 (Cowork)", date: 2026-09-29, human_validated: false}
---

# F8. The interactive lab: applications, questions and GraphRAG

[← Roadmap](../02-roadmap.md)

## Goal

The lab site stops being only a reading room for results. Every hypothesis says what follows from it for an organisation, the public can ask a question that becomes a derived hypothesis in the queue after a testability assessment, and the graph can be queried in natural language with citations. The design is in the document [The interactive lab: applications, questions and GraphRAG](../06-interactive-lab-design.md).

The tasks are described here, without separate files. F8.1 comes first, then F8.6 to F8.9, while F8.2 to F8.5 need decisions on hosting and budget.

## The phase is finished when

Every hypothesis dossier in preparation or finished has an approved applications section, at least five public questions have been assessed and have a public status, and the question interface answers with citations for at least one hypothesis.

## Tasks

### F8.1. Business applications section

A lab processor builds the file `experiments/<slug>/applications.md` in both languages from the dossier, a catalogue of kinds of application and, for hypotheses that are not tested, two outcome scenarios. A rule computes the strength of evidence, a checker reviews the text (a link to a result in every row, no numbers outside the results, no client names or amounts, a language check) and the owner approves it. The site generator shows the section right after the results. The design is in the [document on the interactive lab](../06-interactive-lab-design.md). Done when the three dossiers on the site have an approved section with labels computed by the rule, and a change in the result invalidates the approval. Depends on F6.4.

State on 29 September: the label rule, the source checksum, the processor with its checker and the section on the site are ready. The drafts for the three dossiers on the site are made on the server with `python -m exocortex.lab applications draft <slug>`, because only there is the model gateway. Then the owner approves each section separately.

### F8.2. Public graph bundle

An export from the lab graph of only what is public: claims, verbatim quotes, edges and vectors of public corpora, as a versioned file with a checksum and a script that rebuilds it from the data. The bundle goes through the gate like any publication. Done when the bundle is in the repository and rebuilding it from the data gives the same digest. Depends on F2.8 and F3.2.

### F8.3. Question service

A small container at `api.lab.exocortex.zone`, built in CI, with the graph bundle in SQLite with vectors. Two retrieval modes (vector and graph), a model answer only from the retrieved passages, citations, a refusal when there is no evidence, a per-address rate limit, bot protection, a hard monthly budget with a cut-off and no storing of question text. The choice of provider and model is the owner's decision from the design document. Done when the service answers ten test questions with citations, refuses questions outside the corpus and switches itself off after the budget is exceeded. Depends on F8.2.

### F8.4. Question interface

A page `/ask` and the same box next to every hypothesis, in both languages: a question field, suggestion tiles, an answer with citations, a switch between "search" and "graph", a link for sharing an answer and a button "submit as a question to the lab". The page is static and calls the API. Done when the scenario from a tile to an answer with a citation works on a phone and on a computer, and the page works with a keyboard and a screen reader. Depends on F8.3.

### F8.5. Suggestion tiles

A tile generator at site build time: question templates for each kind of hypothesis and questions from the section on limitations, each tried on the service. A tile stays only if the answer has citations and passes the check, and the owner can add their own. Done when every hypothesis with a dossier has at least six tiles that passed the trial. Depends on F8.3.

### F8.6. Public question intake

A GitHub issue form in the repository and a button "Ask a question" on the hypothesis page that opens it with the chosen hypothesis. A first filter rejects personal data, client material and spam before a submission goes to assessment. Done when a submission from the form appears in the lab queue and a submission with personal data is held. Depends on F6.4.

### F8.7. Question testability assessment

A lab processor assesses every question with the template `templates/question-assessment.md` (based on the selection template from F5.3): whether a measurement on public data settles it, which metric and threshold, what cost (S, M, L), and how it relates to the parent hypothesis. The result is a verdict `testable`, `needs-rephrase`, `not-testable`, `duplicate` or `out-of-scope` with a reason, and a draft card of the derived hypothesis. Similarity to existing questions merges repeats and counts support. Done when ten questions, some of them deliberately bad, got correct verdicts according to the owner's manual assessment. Depends on F8.6 and F5.3.

### F8.8. Derived hypotheses

The hypothesis card schema gets the fields `parent` and `kind` (auxiliary, extension, replication, alternative explanation). A question with the verdict `testable` goes to the owner's G0 decision next to the radar candidates, and an approved derived hypothesis goes through the normal cycle: card, preregistration, test, gates. The order in the queue follows the assessment, support, cost and the weight of the parent result. Done when one derived hypothesis has a card with a link to its parent and an entry in the preregistration registry. Depends on F8.7 and F2.4.

### F8.9. The Questions page and links in the dossier

A public page "Questions" with the list of all questions, their status and the reason for the verdict, rejected ones included, plus a section "derived hypotheses" and a block "ask a question" in the dossier of the parent hypothesis. The author gets an answer in the submission. Done when at least five questions have a public status and the dossier shows its derived hypotheses. Depends on F8.8.

### F8.10. Rewriting "How it works" for a business reader

The "How it works" text in both languages describes the mechanism, not the purpose. The section "What is this lab for" is the most important one: in a few sentences it has to tell a business reader what they get from it, without terms such as success threshold or measurement. We rewrite it from the reader's side: which decisions (choice of a tool, cost, risk) can be made on evidence instead of opinion, and one short example from a real dossier. The rest of the text gets the same test: every section starts with what it means for the reader. Technical detail does not disappear, because credibility needs it: it goes into clearly marked "For the technical reader" boxes (for people in data science and machine learning teams on the client side who want to understand how it is done), collapsed or placed below the main text. The illustrations stay. The main text has to stand on its own without reading the boxes. Done when two people from outside the project, one reading in Polish and one in English, can say in their own words what the lab is for after reading the first section for a minute, and the text passes the language check and the parity check. It does not depend on the other tasks of this phase.

As of 29 September: the text in both languages is rewritten and published, and the owner marked the task as done. The test with two people from outside the project has not been carried out.
