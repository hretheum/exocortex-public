---
id: F4
lang: en
counterpart: ../../pl/roadmap/F4-reference-card.md
status: todo
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F4. Reference project card from the graph

[← Roadmap](../02-roadmap.md)

> **Status: to do** · as of 30 September 2026
>
> None of the four tasks has been started (0 of 4 done). The phase draws on the results of the first experiment (F3), which is in progress: the hypothesis card is frozen, but there are no measurement results yet. The first task (F4.1, the general card model) depends only on F2 and can start independently of F3, while the card compiler (F4.2) waits for the results.

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

**Status: to do** — not started; depends on F2, which is in progress.

Why: it describes the card once, independent of any particular tender, so that the same recorded results can be assembled into different forms.

Card sections as a neutral schema, independent of any particular form: goal and context, hypothesis, experiments and iterations, validation method, results, next steps, what is new compared with related work, risks and limitations, how to verify. For each section: which graph nodes its content comes from. Done when the schema is published in both languages. Depends on F2.

### F4.2. Card compiler

**Status: to do** — not started; waits for F4.1 and for the results of the first experiment in F3.

Why: without a compiler the card would have to be written by hand, and the compiler guarantees that the card and the recorded results agree.

Generates the card in markdown, in Polish and in English, with a link next to every sentence to a file or data row in the repository. Project status follows from the last approved gate and is never higher. Done when the card for F3 is generated and every link works. Depends on F4.1 and F3.

### F4.3. Honesty check for the card text

**Status: to do** — not started; waits for F4.2.

Why: this check stops sentences that sound more certain than the evidence allows before the card reaches the buyer.

Three rules: a sentence in fact mode must have a source in fact mode (the mode classifier from F3, a program that recognises whether a sentence states a fact, a plan, a requirement or a hypothesis), a number in the card must appear in a recorded result, a sentence about current state ("works", "currently") must have a date. Done when the check stops a set of prepared bad sentences and passes the F4.2 card. Depends on F4.2.

### F4.4. Filling in tender forms

**Status: to do** — not started; waits for F4.2.

Why: the card is useful in a tender only when it can be moved into the buyer's form. The generator is public, while the mapping to a specific form stays private, because the form belongs to the buyer.

The generator code that moves card sections into the fields of a particular form (for example an xlsx sheet) is public and general. The mapping from sections to the fields of a specific form is private and lives outside the repository, because the form belongs to the contracting party. Done when the generator fills in a sample form prepared by us. Depends on F4.2.
