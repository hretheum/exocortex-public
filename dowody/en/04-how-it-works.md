---
id: how-it-works
lang: en
counterpart: ../pl/04-how-it-works.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Claude Code)
  date: 2026-09-29
  human_validated: false
---

# How Exocortex R&D works

Who finds what here:

- Decision makers and business readers: why the lab exists and how far the work has got.
- Risk and compliance owners: what protects the data and who approves each next step.
- Data and ML teams: how we run experiments and how to repeat a result. The details are in the blocks "For data and ML teams" below the main text, the full description of the cycle is in [How the evidence cycle works](01-cycle.md), and the order of the work is in the [roadmap](02-roadmap.md).

## Why this lab exists

Exocortex R&D is a public lab that tests whether specific ideas for using AI in an organisation work. With it, you can base a decision on choosing a tool or on the risk of a rollout on a tested result instead of on opinions. The same goes for a specific project or product: the result suggests how to set up a given feature in it before anyone builds it. We also publish the results of ideas that did not work, because they tell you where not to invest. You can trust the results because we announce how they will be judged before we compute anything, and the whole record of the work is open for anyone to repeat.

An example: can a document search run on an AI model hosted on your own infrastructure, without sending texts to the cloud, and find things no worse than a cloud service? The hypothesis [Local or cloud model](experiments/local-vs-cloud-embeddings/overview.md) will answer that. The experiment is planned and has no result yet.

### For data and ML teams: how this differs from a typical report

We usually meet the results of AI work as a finished report. It does not show what was tried earlier and dropped, when the success threshold was set, or whether it was set before the measurement or after seeing the numbers. Here we publish the whole path. We freeze and publish the hypothesis card with its threshold before the measurement, and then add the data with checksums, the raw results with the script that computes them, and a report in which every number has a source. Negative results are published like positive ones.

## Which decisions it helps with

A result from the lab is useful when you have to choose one of several solutions, or set up a feature in a specific product, and justify the choice. Below are questions that large organisations bring, and what the lab already tests or has planned for them. None of them has a result yet.

| I want to | The question we seek to answer | Status |
|---|---|---|
| Build the knowledge of the organisation, so that employees quickly find answers in company documents | Does search that expands results along the links between contents find better than search by meaning alone? The hypothesis [Graph and search](experiments/graph-vs-search/overview.md). | planned |
| Keep confidential documents in-house and still search them well in Polish | Does a model run on your own hardware find no worse than a cloud service? The hypothesis [Local or cloud model](experiments/local-vs-cloud-embeddings/overview.md). | hypothesis card in preparation |
| Summarise organisation documents so that a summary does not turn a plan into a fact | Does a mandatory mode field in claim extraction reduce the number of such swaps? The hypothesis [Intent or fact](experiments/intent-vs-fact/overview.md). | in preparation, the card awaits approval |
| Build an AI assistant that uses company systems instead of guessing | Does imposing a structure on answers eliminate prose answers where a program expects a tool call? The hypothesis [Enforced answer format](experiments/enforced-answer-format/overview.md). | planned |
| Show in a tender that a reference project is backed by evidence | Can a reference project card be assembled from the record of the work so that every sentence points to evidence? | tool planned |

A result from the lab says what works on the public data we measured. It does not replace a pilot on your organisation's data, but it shows where to start and how to plan a pilot so that it can be checked.

Every hypothesis will get a section on business applications on its page: who can use the result, which result it rests on and how strong the evidence is. The strength of evidence is computed by a fixed rule from the state of the work, so a hypothesis without a result is labelled plainly as "hypothesis, no evidence". Each version of this section needs approval from the owner of the project. We are building the section now.

The record of the work can also be assembled into a reference project card, for example for a tender, in which every sentence points to its evidence. The tool that assembles such a card is planned.

## The problems product teams bring

The questions change with the responsibility. A product manager asks about one feature, an area lead about a whole user journey, and a head of product about a portfolio of ideas and how to justify decisions to the board. Next to each question is what the lab has today: a method, or a hypothesis that is already on the list.

| Who asks | The problem they come with | What the lab can test | What we have today |
|---|---|---|---|
| Product manager | I want to add search or an assistant to a mobile app. I do not know whether users will get answers they can trust. | What share of answers is correct and grounded in a source, rated blind by people, before the feature reaches users? | a pilot with blind rating and a list of typical errors; the calibration of an automatic judge is planned |
| Product manager | I want to test the potential of a feature before anyone builds it. | What must be true for the feature to make sense, and what result of a small test would refute it? | a hypothesis card with a threshold frozen before the measurement, and a quick test that takes from a few hours to two days |
| Product manager | The feature must not send user data to an external service. | Does a model run on your own server give quality no worse than a cloud service? The test concerns a server. We do not test a model running on a phone. | the hypothesis [Local or cloud model](experiments/local-vs-cloud-embeddings/overview.md), card in preparation |
| Product manager | I do not know what to show the user when the model is wrong or answers in the wrong format. | How often does the model answer in prose instead of the structure the app expects, and which errors are most common? | the hypothesis [Enforced answer format](experiments/enforced-answer-format/overview.md), planned; a list of typical errors in every pilot |
| Area lead (senior or group product manager) | I own a journey in which users look for information. I want to know what will improve search first. | Does expanding results along the links between contents improve search beyond search by meaning alone? | the hypothesis [Graph and search](experiments/graph-vs-search/overview.md), planned |
| Area lead | I have more ideas for AI features than a team to build them. | Which ideas can be measured and refuted cheaply, and which drop out before anyone starts work? | five rejection questions, a scoring sheet and a weekly review of new papers and models |
| Area lead | I need a success measure for an AI feature that will not make the rest of the product worse. | Which measure decides success, and which guard measure must not fall? | the hypothesis card requires a deciding measure and a guard measure |
| Head of product | The board asks where we invest in AI and how we know it works. | How to run a portfolio of ideas with gates at which the decision about the next step or about stopping is made? | an evidence cycle with two gates; we publish the decisions together with the results |
| Head of product | I have to decide whether to build our own solution or use a cloud model. | How much quality is lost by moving to your own model, and will your own hardware cope? | the same hypothesis [Local or cloud model](experiments/local-vs-cloud-embeddings/overview.md) measures quality and feasibility separately |
| Head of product | I have to show an auditor and the risk function how we made the decision about an AI feature. | Can an independent person reconstruct from the record of the work why this solution was chosen? | an open record of the cycle with the hypothesis card and the gate decisions |
| Head of product | I want one standard for assessing AI features across all my teams. | Is a shared template for the hypothesis card, the run note and the gate decision enough for teams to assess features the same way? | templates of these three documents |

The lab does not study the users of your app. It will not measure how your product will behave or how use of the feature will change. It gives a tested result on public data, a pilot method to run on your own side, and a hypothesis card template that lets the success criterion be written down before the measurement.

## How it works in short

The lab uses only public sources and our own texts, and you can read everything it produces straight away. It goes into the public repository, a public cabinet for documents and code that keeps the history of every change. Before anything gets there, it passes through the publishing gate. Publishing happens by itself, every 15 minutes, so the repository always shows the current state.

![Diagram: the lab reads only public sources, results pass through the publishing gate into the public repository, and private and client data sit behind a wall, outside the lab.](img/1-overview.svg)

Private data and client projects are outside the lab, behind a wall: a separate database, a separate network, no link in either direction. Two rules have applied from the start. We use no materials from clients, and everything the lab produces is public at once, in Polish and in English.

## What protects against leaks

No file reaches the public repository without automatic checks, and a person decides about every file that is held. We call these checks the publishing gate. Every new document has to pass all five.

![Diagram: a new document passes five checks. If all pass, it goes into the repository; if not, it waits for a person to decide.](img/2-gate.svg)

The first check looks for names and personal data that must not leave, including in the hidden data of files. The list of banned names is private, and the repository holds only its digital fingerprints, from which no name can be read back. The second compares the text with a private collection and answers only “similar” or “not similar”, so that not even a reworded fragment gets out. The third makes sure that the Polish and English versions agree in numbers, headings, links and tables. The fourth checks the structure of the file. The fifth catches habits typical of text written carelessly by an AI model, because the documents should read like text written by a person.

When something does not match, the file does not vanish. It stays where it was, the author gets a notice with the reason, and a person decides.

The checks are tested as well. Every night they receive a set of files with deliberately planted leaks and have to stop every one of them. If one gets through, publishing stops until someone fixes it.

## Isolation of the lab

The lab has no access to client data or private notes and cannot gain it, even by mistake.

![Diagram: two separate worlds, private and the lab. Only sources from the allowlist enter the lab, and a nightly test checks the isolation.](img/6-isolation.svg)

The lab has its own database and its own closed network. Of the private documents it sees only one folder with published texts, and only for reading. Even a mistake in the settings does not open a road to the private database, because such a road simply does not exist. Email and client notes are not on the allowlist of sources and never will be.

The isolation is checked by a test, every night. From inside the lab it tries to reach the private database at every known address and checks that the private folders are invisible. Every attempt has to fail, and any other answer is an alarm.

## The path of one hypothesis

A person decides about every next step, and most ideas drop out early, after a short test. A hypothesis is a question we want to answer with a number, for example: does this way of summarising papers turn authors’ intentions into facts.

![Diagram: the path of a hypothesis in seven steps, from a signal, through a hypothesis card frozen before measurement and two gates, to a plan for a large organisation.](img/3-path.svg)

Ideas come from a weekly look at new public papers, models and data. An idea drops out if nobody knows why to test it, there is no data, it is not legal, it cannot be measured, or it can be done more simply without AI. Before we compute anything, we write down and publish the hypothesis card: what we are testing and what result would prove us wrong. After that come three stages: a quick test on a small sample, where most ideas end, a pilot on a larger sample rated by people, and finally a plan for a rollout in a large organisation, based on numbers from the pilot. After the quick test and after the pilot, a person decides whether we go on.

### For data and ML teams: how it is done

Candidates get a first score from several models of different families, each on its own. A wide spread of scores means the candidate needs a longer look. A person makes the decision.

The hypothesis card holds what exactly we are testing, the result that would refute the hypothesis, the single number that settles it, the reference point and the samples. Once the card is approved, the lab computes its checksum and publishes it before anything is computed. The date of publication shows that we did not fit the method to the result. A change of mind means a new version of the card, and the old one stays visible.

The quick test (scale S) takes from a few hours to two days and runs on local models. Part of the sample is set aside as a control set and opened only once, at the end. At the gate the result is compared with the threshold from the card, and a person chooses: go on, stop, change the hypothesis, park it with a written condition for coming back, or close it because the question is settled. The pilot (scale M) is a larger sample rated blind by people, a comparison of several variants, a list of typical errors, cost and time. Someone other than the author has to try the pilot result, and a second gate comes at the end. Scale L is only a document: a rollout plan for thousands of users with numbers from the pilot.

## Latest hypotheses

This shows what the lab is testing now. No hypothesis has a result yet.

![Diagram: four hypotheses and their stage on the path from candidate to report. One is in preparation, three are planned.](img/4-hypotheses.svg)

| Hypothesis | Question | State |
|---|---|---|
| Intent or fact | Does extracting claims from text tell facts apart from intentions, hypotheses and announcements, and do our summaries avoid turning an intention into a fact. | In preparation: 2478 papers ready, the hypothesis card waits for approval |
| Graph and search | Does expanding search results along the connections between contents improve their quality. | Planned |
| Local or cloud model | Is a local model for finding similar texts as good as a cloud one on a Polish public corpus. | Hypothesis card in preparation |
| Enforced answer format | Does forcing a structure on the model’s answer end the cases where it replies in prose instead of calling a tool. | Planned |

The card of the first hypothesis is written and waits for approval by the owner of the project. The lab will start the experiment only after the card is frozen. Every new entry on the list also gets a card before anything is measured.

## Architecture

This section shows data and ML teams where the lab takes its data from and which way the results leave. The whole has five layers. At the input are public sources, passed through the allowlist: a new source is an entry with a reason and a legal basis, for example arXiv abstracts, which are provided under CC0.

![Diagram: the architecture in five layers. Public sources enter the lab, which has four modules, through the allowlist, and results pass through the publishing gate into the public repository.](img/5-architecture.svg)

In the middle is the lab with four modules. The knowledge graph turns texts into claims and the connections between them. Local models run without sending data to the cloud. The measurement module compares many configurations on the same sample. The cycle record stores hypothesis cards, runs and gate decisions. Results leave through the publishing gate into the public repository, and from it come the result pages and the reference project card. The diagram shows the target architecture, and what already works is marked in green.

## How to check a result

Every result can be checked without taking our word for it. That is why every experiment leaves four traces.

![Diagram: a four-step evidence trail, from the announcement, through data and result, to the report. Anyone can repeat steps two and three.](img/7-evidence.svg)

The announcement is the hypothesis card with a date and a checksum. The data is the list of texts used with their checksums, so anyone can download exactly the same. The result is the raw numbers and the script that computes them. The report is a text in which every sentence points to a file or a data row. A number without a source does not enter the report.

### For data and ML teams: how to repeat a result

Anyone can repeat steps two and three: download the data, run the script and compare the numbers with the report. The frozen card, a control set opened only once and the history in the repository, which nobody rewrites, also protect against tuning the results. We check the text of the card with a tool that catches sentences describing a plan as if it had already been carried out.

## Who does what

A person makes every decision, and the machine does what repeats.

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

As of 29 September 2026. We keep what works apart from what is being built and from what is only planned.

![Diagram: six roadmap phases. The lab and the first experiment are being built, and the other four phases are planned.](img/8-status.svg)

The diagram shows the roadmap phases, and the current state of the tasks is in the [roadmap](02-roadmap.md).

The checks before publication work, with their nightly tests, and so does publishing every 15 minutes. The repository has been public since 29 September, and the site lab.exocortex.zone shows the hypothesis dossiers and the state of the work. The lab has its own database, isolation checked every night, the allowlist of sources, an experiment queue and the first hypothesis cards. Every week it looks through new public papers (F5).

The first experiment (F3) is being built: its card waits for approval and nothing has been measured yet. The section on business applications on the hypothesis pages (F8) is being built as well.

Only planned are the reference project card assembled from recorded results (F4), further experiments (F5), collaboration with a second expert (F6) and the public demo (F7).

## Frequently asked questions

### How is Exocortex R&D different from Exocortex

Exocortex is a system for collecting and connecting knowledge. Exocortex R&D is the lab that grew out of that project and is used to test ideas about AI. The lab is public, and private data and client projects are kept entirely apart from it. You can read about Exocortex itself on the [Exocortex project](https://exocortex.zone) page.

### Do client materials or private notes get into the lab

No, never. The input data comes from public sources or we create it ourselves. Every night a test checks that the lab has no road to the private database.

### How do we know the gate works

Every night we run it on files with deliberately planted leaks. If even one gets through, publishing stops. The result of the test is recorded.

### Why publish negative results

Because they show that we do not pick only what went well, and they save time for anyone who wanted to check the same thing. A negative result is a result.

### Who decides whether a hypothesis was confirmed

The threshold is written in the card before the measurement, so the result is settled by a number fixed in advance. A person approves the gate, and in the pilot people rate the samples blind.

### Are these documents written by AI

The first versions are written by an AI model. Every file records in its header who wrote it and whether a person has reviewed it. The review by the owner of the project is still ahead of us.

### Is the repository public yet

Yes, since 29 September 2026, together with the site lab.exocortex.zone.

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
