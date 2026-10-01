---
id: F4
lang: en
counterpart: ../../pl/roadmap/F4-reference-card.md
status: doing
task_status: {F4.1: done, F4.2: doing, F4.3: done}
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F4. Reference project card from the graph

[← Roadmap](../02-roadmap.md)

> **Status: in progress** · as of 1 October 2026
>
> Two of the four tasks are done (F4.1, F4.3), one is in progress (F4.2), one is waiting. The phase draws on the results of the first experiment (F3), which is in progress: the hypothesis card is frozen, but there are no measurement results yet. The card model (F4.1) is published, the honesty check (F4.3) stops prepared bad sentences, and the card compiler (F4.2) already writes the card for the toy experiment; the card for the first experiment waits for its results.

## In short

This phase makes the description of a completed project, needed in a bid or tender (a reference project card), assemble itself from the lab's recorded results. Every sentence of such a card points to where it comes from, and a program rejects numbers without a source and plans described as accomplished facts.

## Why this phase

Reference cards are usually written by hand, and they are easy to inflate: a plan written in the present tense, a number remembered from a conversation, the word "works" without a date. The buyer has no way to check. Here the card is made differently. If it contains a sentence about improved accuracy, the compiler inserts it only when the recorded experiment result holds the matching number, and it adds a link to that result in the public repository. A sentence about the current state ("currently") gets a date. The buyer can therefore check every number on their own.

## Goal

The reference project card is no longer written by hand. A compiler assembles it from the lab graph: the hypothesis from the frozen card, the validation method from the experiment description, results from the tables, next steps from gate decisions. Every sentence links to its source in the public repository, and the text goes through a check that catches numbers without a source and plans described as facts.

The tasks are described here, without separate files. Details will be settled after F3.

## The phase is done when

The card for the F3 experiment is generated in both languages, every number has a link, the honesty check passes, and the same card fills in a sample tender form.

## Tasks

### F4.1. General card model

**Status: done** — the model is published: nine sections of a reference card in a fixed order, each with the sentence modes it allows and the places in the lab's records its content comes from. It exists as a data file (`lab/card-model.yaml`) and as the document [General model of a reference card](../07-card-model.md). A program checks every card against it (`exocortex lab card-check`), and a complete card for the toy experiment passes. Seven gaps between what a section needs and what the lab records are written down as open decisions in that document.

Why: it describes the card once, independent of any particular tender, so that the same recorded results can be assembled into different forms.

Card sections as a neutral schema, independent of any particular form: goal and context, hypothesis, experiments and iterations, validation method, results, next steps, what is new compared with related work, risks and limitations, how to verify. For each section: which graph nodes its content comes from. Done when the schema is published in both languages. Depends on F2.

### F4.2. Card compiler

**Status: in progress** — the compiler works: `exocortex lab card-compile <experiment>` writes the card in Polish and in English from the lab's published records, in the nine sections of the card model, with a link next to every sentence to a file or one row of data. The project status comes from the last approved gate decision and is never higher. For the toy experiment it writes 60 sentences in each language, every link opens its source, and the card passes both the model check and the honesty check. See [The reference card compiler](../08-card-compiler.md). What is left from the done condition is the card for the first experiment (F3), which has no published results yet.

Why: without a compiler the card would have to be written by hand, and the compiler guarantees that the card and the recorded results agree.

Generates the card in markdown, in Polish and in English, with a link next to every sentence to a file or data row in the repository. Project status follows from the last approved gate and is never higher. Done when the card for F3 is generated and every link works. Depends on F4.1 and F3.

### F4.3. Honesty check for the card text

**Status: done** — the check runs as `exocortex lab honesty` and enforces three rules: a sentence in fact mode needs a source in fact mode, a number has to appear in a recorded result, and a sentence about the current state needs a date. It stops all 48 prepared bad sentences, in Polish and in English, and the card written by the compiler (F4.2) for the toy experiment passes without remarks. When the first experiment has results, its card goes through the same check.

Why: this check stops sentences that sound more certain than the evidence allows before the card reaches the buyer.

Three rules: a sentence in fact mode must have a source in fact mode (the mode classifier from F3, a program that recognises whether a sentence states a fact, a plan, a requirement or a hypothesis), a number in the card must appear in a recorded result, a sentence about current state ("works", "currently") must have a date. Done when the check stops a set of prepared bad sentences and passes the F4.2 card. Depends on F4.2.

### F4.4. Filling in tender forms

**Status: to do** — not started; waits for F4.2.

Why: the card is useful in a tender only when it can be moved into the buyer's form. The generator is public, while the mapping to a specific form stays private, because the form belongs to the buyer.

The generator code that moves card sections into the fields of a particular form (for example an xlsx sheet) is public and general. The mapping from sections to the fields of a specific form is private and lives outside the repository, because the form belongs to the contracting party. Done when the generator fills in a sample form prepared by us. Depends on F4.2.
