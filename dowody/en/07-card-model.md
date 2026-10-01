---
id: card-model
lang: en
counterpart: ../pl/07-card-model.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Code (cloud session)
  date: 2026-10-01
  human_validated: false
---

# General model of a reference card

A reference card describes a completed project for a bid or a tender. This document describes such a card once, in a way that does not depend on any particular form: which sections it has, what each section answers, and where in the lab's records its content comes from. The same description exists as a data file, [lab/card-model.yaml](https://github.com/hretheum/exocortex-public/blob/main/lab/card-model.yaml), and a program checks every card against it. This is task F4.1 of phase [F4](roadmap/F4-reference-card.md).

## Why

A card written by hand is easy to inflate. A plan ends up in the present tense, a number comes from memory, and "it works" has no date. The buyer cannot check any of it. Here a card is built from the lab's records, and every sentence says what kind of sentence it is and where it comes from. To make that possible, the card first needs a fixed shape that does not change from one tender to the next. This model is that shape. The program that assembles cards (task F4.2) and the check that stops sentences sounding more certain than the evidence (task F4.3) both rely on it.

## The nine sections

A card has these sections, always in this order. Each one has a title in both languages.

| Section | What it answers | Allowed sentence modes | Where its content comes from |
|---|---|---|---|
| Goal and context | What problem was addressed and within which larger piece of work | fact, requirement | the "Problem" section of the hypothesis card; the roadmap task the card names; the experiment title |
| Hypothesis | What exactly was claimed in advance, and in which card version | hypothesis, fact | H1 and H0 from the hypothesis card; the card's state and version; the preregistration registry |
| Experiments and iterations | What was run, on which samples and settings, how many times | fact | the table of runs, configurations, samples and per-document results; run notes; earlier versions of the card |
| Validation method | How the hypothesis was tested | fact, requirement | the card sections on metrics, samples and gate criteria; how each sample was drawn; the statistical method behind each number; blind checks by people |
| Results | What the measurements showed | fact only | rows of the results table (each number with its confidence interval and sample size); the results a gate decision rests on |
| Next steps | What happens next and on what condition | plan, requirement, fact | the last approved gate decision; the gate criteria and stopping condition of the card; open roadmap tasks |
| What is new compared with related work | Which known work this builds on or differs from | fact, hypothesis | the "Related work" section of the hypothesis card |
| Risks and limitations | What the result does not show and what could make it wrong | fact, hypothesis | the card sections on its main assumption, what the method will not detect and when to stop; guard metrics; failed documents; sample sizes |
| How to verify | How a reader repeats every number without access to the lab | fact | the recompute command published with the data; the preregistration check; the code version of every run; the graph package |

The Results section is the strictest: a sentence there can only be a fact, and it must point to a row of data, never to a piece of text.

## Three fields on every sentence

Every sentence of a card carries three pieces of information. These are what the honesty check (F4.3) reads.

1. **Mode.** One of four: fact, plan, requirement, hypothesis. These are the same four modes the lab's extractor uses in the first experiment (F3). Each section allows only some of them; a plan in the Results section is rejected.
2. **Source.** Either a file in the public repository, optionally with a heading inside it, or one row of a data file (CSV or JSON lines), given by the values of its columns. The program checks that the file exists, that the heading is in it, and that the values pick exactly one row. A sentence without a source is rejected.
3. **Date, for sentences about the current state.** Each sentence says whether it describes the current state ("is a draft", "no decision yet"). If it does, it must carry the date on which it was true. Other sentences have no date.

## Where the content comes from

The model names only what the lab already records. Nothing was added for the card. The lab keeps three kinds of records.

- **Nodes of the graph.** Published documents of the lab, versions of hypothesis cards, applied gate decisions, papers of the corpus (their abstracts and the engine's summaries) and radar signals. Corpus papers can also have embeddings, but the card does not use them.
- **Links between nodes.** The lab writes four kinds: a node comes from a source (acquired_from), a card or a summary is derived from a document (derived_from), a newer card version replaces an older one (supersedes), and a gate decision decides a card version (decides).
- **Tables outside the graph.** Experiments, configurations, samples, runs, results per document, the numbers cited on pages under fixed result ids, blind judgments by people, card versions and gate decisions. They are published as CSV files next to the documents, so anyone can recompute the numbers.

A test checks that every name in the model really appears in the code or the database migrations that define it, and that every link type is one the database allows. Where a section would need something the lab does not record, the model does not invent it: the gap is written down as an open decision (below).

## Example: the toy experiment

The file [lab/cards/toy-length.en.yaml](https://github.com/hretheum/exocortex-public/blob/main/lab/cards/toy-length.en.yaml) is a complete card for the toy experiment toy-length. That experiment tests the lab's machinery, not a real question: it compares two fixed rules for picking a sentence from a document. Every number in the card comes from the experiment's published data, for example:

> On the control sample (run run-2026-09-29-2, 6 documents) the difference was 0.667, confidence interval 0.333 to 1.000.

This sentence has the mode "fact", it is not about the current state, and its source is the row with that result id in `dowody/data/toy-length/metrics.csv`. A sentence about the current state looks like this:

> No gate decision has been recorded for this experiment.

Its source is the "Gate decisions" section of the experiment's dossier, and its date is 1 October 2026.

The toy card was chosen because it is the only toy experiment with published results. The other one, toy-retrieval, has no result files in the repository yet.

## How to check a card

```
python -m exocortex.lab.card_model lab/cards/toy-length.en.yaml
```

The program prints "ok", or one line per problem with the exact place of the problem, for example `sections[4].statements[0].source: required field is missing`. The number in brackets is the position in the list, counted from zero. The same check runs as `exocortex lab card-check`.

## Open decisions

These questions need the owner's decision. Each one comes from a gap between what a section needs and what the lab records today.

1. **A card and its roadmap task.** Today they are tied only by a list of paths in the card's header. A link type for this exists in the database, but the lab does not write it.
2. **Experiments and runs in the graph.** They are table rows, not nodes. A card reaches them through the experiment name and the card version; no link connects a run with a card version.
3. **Run notes.** They are published documents with a checked header, but nothing reads them into the graph or links them to runs.
4. **Which runs a result may come from.** The results table holds every run, including tuning runs and runs on a changed sample. The model does not yet limit results to the runs a gate decision names.
5. **How the project status is worded.** A card version has a state (draft, frozen, GO, NO-GO, PIVOT, NOT-NOW, CLOSED). There is no agreed wording of these states for a buyer.
6. **Related work.** Today it is only free text in the card. The lab knows papers, but nothing links a card to them.
7. **Strength of evidence.** The lab computes a label (none, preliminary, confirmed, refuted, inconclusive) by a fixed rule, but does not store it. It is open whether the card computes it again or the label is stored with the card version.

## What this model does not do

It does not write cards; the compiler (F4.2) will. It does not judge whether a sentence sounds more certain than its source; that is the honesty check (F4.3). It does not know any tender form; moving sections into a buyer's form is task F4.4.
