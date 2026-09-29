---
id: how-it-works
lang: en
counterpart: ../pl/04-how-it-works.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Sonnet 5.5 (Cowork)
  date: 2026-09-28
  human_validated: false
---

# How Exocortex R&D works

This text explains in plain language why Exocortex R&D exists and how it works. The detailed description of the cycle is in [How the evidence cycle works](01-cycle.md), and the order of construction is in the [roadmap](02-roadmap.md).

## Why this lab exists

We usually meet the results of AI work as a finished report. It does not show what was tried earlier and dropped, when the success threshold was set, or whether it was set before the measurement or after seeing the numbers. Exocortex R&D does the opposite: it records and publishes the whole path, from the announcement, through the data and the result, to the report. Anyone who wants to can follow it and repeat it.

Three things follow. Negative results are published like positive ones, because they are results too. Every number in a report has a source. And the record of the work allows us to assemble an honest reference project card, for example for a tender, in which every sentence points to its evidence.

The lab grew out of the Exocortex project, a system for collecting and connecting knowledge. If you would like to read about it, start with the [Exocortex project](https://exocortex.zone) page. Here we describe only what concerns the lab.

## How it works in short

The lab reads only public sources and our own texts. Everything it produces goes into the public repository, a public cabinet for documents and code that keeps the history of every change. Before anything gets there, it passes through the publishing gate. Publishing happens by itself, every 15 minutes, so the repository always shows the current state.

![Diagram: the lab reads only public sources, results pass through the publishing gate into the public repository, and private and client data sit behind a wall, outside the lab.](img/1-overview.svg)

Private data and client projects are outside the lab, behind a wall: a separate database, a separate network, no link in either direction. Two rules have applied from the start. We use no materials from clients, and everything the lab produces is public at once, in Polish and in English.

## The publishing gate

The gate is a set of automatic checks. Every new document has to pass all five.

![Diagram: a new document passes five checks. If all pass, it goes into the repository; if not, it waits for a person to decide.](img/2-gate.svg)

The first check looks for names and personal data that must not leave, including in the hidden data of files. The list of banned names is private, and the repository holds only its digital fingerprints, from which no name can be read back. The second compares the text with a private collection and answers only “similar” or “not similar”, so that not even a reworded fragment gets out. The third makes sure that the Polish and English versions agree in numbers, headings, links and tables. The fourth checks the structure of the file. The fifth catches habits typical of text written carelessly by an AI model, because the documents should read like text written by a person.

When something does not match, the file does not vanish. It stays where it was, the author gets a notice with the reason, and a person decides.

The gate has to be checked as well. Every night it receives a set of files with deliberately planted leaks and has to stop every one of them. If one gets through, publishing stops until someone fixes it.

## The path of one hypothesis

A hypothesis is a question we want to answer with a number, for example: does this way of summarising papers turn authors’ intentions into facts. Every hypothesis goes down the same path.

![Diagram: the path of a hypothesis in seven steps, from a signal, through a hypothesis card frozen before measurement and two gates, to a plan for a large organisation.](img/3-path.svg)

It starts with a signal: once a week the lab looks through new public papers, models and data. A candidate drops out if the answer to any of five questions is “no”: do we know why we are doing it, is there data, is it legal, can it be measured, and is there no simpler way without AI. The first score comes from several models of different families, each on its own, but a person makes the decision.

The heart of the whole cycle is the hypothesis card. In it we write what exactly we are testing, what result would prove us wrong and which single number will settle it. Then we freeze the card and publish it before anything is computed. The date of publication is the proof that we did not fit the method to the result. If we change our mind, a new version of the card appears and the old one stays visible.

After that come three stages. The quick test takes from a few hours to two days and works on a small sample; part of the sample stays sealed and is opened once, at the very end. Most ideas end right here. At the gate the result is compared with the threshold from the card, and a person chooses: go on, stop, change the hypothesis or park it with a written condition for coming back. The pilot is a larger sample rated blind by people, with a second gate at the end. The last stage is only a document: a plan for how to carry out such a rollout in a large organisation, with numbers taken from the pilot.

## Latest hypotheses

This is the list of hypotheses and the stage each one is at today.

![Diagram: four hypotheses and their stage on the path from candidate to report. One is in preparation, three are planned.](img/4-hypotheses.svg)

| Hypothesis | Question | State |
|---|---|---|
| F3. Intent or fact | Does extracting claims from text tell facts apart from intentions, hypotheses and announcements, and do our summaries avoid turning an intention into a fact. | In preparation: corpus of 2478 papers ready, hypothesis card is next |
| F5.5. Graph and search | Does expanding search results along the connections between contents improve their quality. | Planned |
| F5.6. Local or cloud model | Is a local model for finding similar texts as good as a cloud one on a Polish public corpus. | Planned |
| F5.7. Enforced answer format | Does forcing a structure on the model’s answer end the cases where it replies in prose instead of calling a tool. | Planned |

Today no hypothesis has a frozen card or a result yet. The list grows together with the lab, and every new entry gets a card before anything is measured.

## Architecture

The whole has five layers. At the input are public sources, passed through the allowlist: a new source is an entry with a reason and a legal basis, for example arXiv abstracts, which are provided under CC0.

![Diagram: the architecture in five layers. Public sources enter the lab, which has four modules, through the allowlist, and results pass through the publishing gate into the public repository.](img/5-architecture.svg)

In the middle is the lab with four modules. The knowledge graph turns texts into claims and the connections between them. Local models run without sending data to the cloud. The measurement module compares many configurations on the same sample. The cycle record stores hypothesis cards, runs and gate decisions. Results leave through the publishing gate into the public repository, and from it come the result pages and the reference project card. The diagram shows the target architecture, and what already works is marked in green.

## Isolation of the lab

Trust in the lab rests on the fact that it has no access to anything it should not see.

![Diagram: two separate worlds, private and the lab. Only sources from the allowlist enter the lab, and a nightly test checks the isolation.](img/6-isolation.svg)

The lab has its own database and its own closed network. Of the private documents it sees only one folder with published texts, and only for reading. Even a mistake in the settings does not open a road to the private database, because such a road simply does not exist. Email and client notes are not on the allowlist of sources and never will be.

The isolation is checked by a test, every night. From inside the lab it tries to reach the private database at every known address and checks that the private folders are invisible. Every attempt has to fail, and any other answer is an alarm.

## How to check a result

A result is worth something only if it can be checked without taking our word for it. That is why every experiment leaves four traces.

![Diagram: a four-step evidence trail, from the announcement, through data and result, to the report. Anyone can repeat steps two and three.](img/7-evidence.svg)

The announcement is the hypothesis card with a date and a checksum. The data is the list of texts used with their checksums, so anyone can download exactly the same. The result is the raw numbers and the script that computes them. The report is a text in which every sentence points to a file or a data row. A number without a source does not enter the report. Anyone can repeat steps two and three: download the data, run the script and compare the numbers with the report.

Three more things protect us from tuning the results: the frozen card, a control set opened only once, and the history in the repository, which nobody rewrites. We also check the text of the card with a tool that catches sentences describing a plan as if it had already been carried out.

## Who does what

The machine does what repeats, and the person does what needs a decision.

| Task | Machine | Person |
|---|---|---|
| Collecting signals | looks through sources once a week | adds their own ideas |
| Choosing candidates | first scoring by several models | decides |
| Hypothesis card | suggests metrics and sample size | writes and approves |
| Experiment | runs, computes, records | rates samples blind |
| Gate | sets the result against the threshold | decides |
| Translation | first version by a local model | corrects |
| Publication | scans and publishes every 15 minutes | settles held files |

## Where we are

As of 28 September 2026. We separate three kinds of state here, so that nothing looks finished when it is not.

![Diagram: eight roadmap phases. The gate and the repository work, the lab and the first experiment are being built, and the other four phases are planned.](img/8-status.svg)

The publishing gate works, with its nightly tests (F0), and so does the mechanism that moves checked documents into the repository every 15 minutes (F1). The repository itself is still private. We will change that after seven nights of gate tests in a row and after a review by the owner of the project, under the conditions written in the roadmap.

The lab is being built (F2): it already has its own database, the isolation checked every night and the allowlist of sources, but it still lacks support for hypothesis cards, gate decisions and experiment tables. The first experiment (F3) has a ready corpus but has not measured anything yet.

Only planned are the reference project card assembled from recorded results (F4), the weekly look at sources and further experiments (F5), scaling up and collaboration with a second expert (F6) and the public demo (F7). Not one task there is finished yet.

## Frequently asked questions

### How is Exocortex R&D different from Exocortex

Exocortex is a system for collecting and connecting knowledge. Exocortex R&D is the lab that grew out of that project and is used to test ideas about AI. The lab is public, and private data and client projects are kept entirely apart from it.

### Do client materials or private notes get into the lab

No, never. The input data comes from public sources or we create it ourselves. Every night a test checks that the lab has no road to the private database.

### How do we know the gate works

Every night we run it on files with deliberately planted leaks. If even one gets through, publishing stops. The result of the test is recorded.

### Why publish negative results

Because they show that we do not pick only what went well, and they save time for anyone who wanted to check the same thing. A negative result is a result.

### Who decides whether a hypothesis was confirmed

The threshold is written in the card before the measurement, so the number decides, not the mood. A person approves the gate, and in the pilot people rate the samples blind.

### Are these documents written by AI

The first versions are written by an AI model. Every file records in its header who wrote it and whether a person has reviewed it. The review by the owner of the project is still ahead of us.

### When will the repository be public

After seven nights of gate tests in a row and after the owner’s review. There is no date yet.

## Glossary

| Term | Meaning |
|---|---|
| lab | The place where we test ideas about AI. It has no access to private data. |
| repository | A public cabinet for documents and code with the history of every change. |
| publishing gate | A set of checks that stops a file if it finds something that is not allowed. |
| hypothesis | A question we answer with a number. |
| hypothesis card | A one-page description of a hypothesis, how it will be tested, and the threshold at which it counts as confirmed or rejected. |
| control set | Part of the sample set aside in advance and opened only once, at the end. |
| checksum | A short digital fingerprint of a file. Changing even one character changes the fingerprint. |
| blind rating | A rating in which the rater does not know which variant they are rating. |
| negative result | A result that did not confirm the hypothesis. We publish it like any other. |
| allowlist of sources | A list of places the lab may read from, each with a reason. |
