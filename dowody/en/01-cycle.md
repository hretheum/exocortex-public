---
id: cycle
lang: en
counterpart: ../pl/01-cycle.md
provenance: ai_authored
provenance_metadata:
  agent: Claude Opus 5.5 (Cowork)
  date: 2026-09-27
  human_validated: false
---

# How the evidence cycle works

This document follows one idea from the first signal to a published result. Technical details and the build order are in the [roadmap](02-roadmap.md).

## What it is for

We do research and development on applications of AI, and we want every piece of it to be checkable from the outside. Anyone who opens the repository should be able to see what the hypothesis was, how we measured it, which variants we compared, what came out and what we decided next. This is useful in many situations. One of them is the reference project card in a tender: the evaluation committee asks for the hypothesis, the validation method and the results, and we can point to a public record of the work that the card was assembled from.

Two rules apply from the start. The lab uses no material from clients: input data comes from public sources or is created by us. Everything the lab produces is public immediately, in Polish and in English. Client projects are a separate world. They stay private and never enter the lab.

## Three places

The Obsidian vault, folder `dowody/`. This is where we write hypothesis cards, experiment notes, gate decisions, documentation and the roadmap. It is the only place where a person edits content.

The lab, a separate Exocortex instance on the home server K12. Here content is loaded into the database and the relationship graph, experiment scripts and local language models run, and result pages are generated. The lab has its own database. The private Exocortex, which holds notes from professional work, runs next to it and has no connection to the lab in either direction.

The public repository on GitHub. It receives the engine and lab code, the documentation, the roadmap with the current state of tasks, hypothesis cards, raw results and reports. Publishing runs on its own every fifteen minutes, so the repository always shows the current state, and the commit history shows when each thing was created.

Between the vault and the repository sits the publishing gate. Before any file goes out it is checked: does it contain names or fragments of client material, personal data, hidden metadata; does it have a version in the other language; are the numbers the same in both versions. A file that fails stays in the vault and the author gets a notification with the reason.

## The path of one hypothesis

1. Signal. Once a week the lab goes through what came in from public sources: new research papers, new open-weight models, open datasets, gaps and contradictions in the lab's own knowledge base. The result is a short list of candidates, each with a link to its source.

2. Selection. A candidate is dropped if the answer to any of five questions is "no": do we know why we are doing this; is there data; is it legal; can it be measured; is there no simpler way to do it without AI. Candidates that pass get a score. The first scoring is done by several models from different families, each on its own. If their scores differ a lot, that tells us the candidate needs more thought. A person makes the decision.

3. Hypothesis card. We write down exactly what we are testing, what result would refute the hypothesis, which single number decides it, what the baseline is and which samples we will use. Once approved, the card is frozen: the lab computes its checksum and publishes the card in the repository before anything is measured. The date of that commit shows that we did not fit the method to the result. If we change our mind along the way, a new version of the card is created and the previous one stays visible.

4. Quick test (scale S, from a few hours to two days). On K12, with local models, on a small sample. Part of the sample is set aside as a control set and opened only once, at the end. Most ideas stop at this stage.

5. Gate. We compare the result with the threshold written in the card. Possible decisions: go on, stop, change the hypothesis, postpone with a recorded condition for coming back, or close because the question has been answered. A person approves the decision and it is published too. Negative results are published together with a description of why it did not work.

6. Pilot (scale M, from one to several weeks). A larger sample rated blind by people, a comparison of several variants, a list of typical errors, a measurement of cost and time. Someone other than the author has to try the result. A second gate closes this stage.

7. Plan for a large organisation (scale L). We do not carry out this stage. We write a document on how to run such a deployment for thousands of users, and the numbers in it, for example cost per unit, the share of cases that need manual review or hardware requirements, come from the pilot measurements.

8. Record. Every step leaves a trace in the lab graph and a file in the repository. The result pages and the reference project card are assembled from these traces. Every sentence in the card points to where it came from. A number that cannot be linked to a recorded result does not go into the card.

## What protects against leaks

The first protection is separation. The lab reads only from sources on the allowlist and from the `dowody/` folder. It has no access to the private Exocortex.

The second is a scanner on every publication. It checks a list of forbidden names (the list itself is private, the repository only knows its cryptographic hashes), detects personal data, strips and checks file metadata. It unpacks packages and container images and scans their contents before they are pushed to a registry.

The third is a comparison with the private corpus. On K12 we check whether text meant for publication resembles any fragment of client material, also after rewording. The comparison returns only "similar" or "not similar"; nothing else leaves the private database.

The scanner is tested as well. Every night it gets a set of files with deliberately planted leaks and has to stop each of them. If it lets one through, publishing stops until someone fixes it.

## What protects against stretching the results

The hypothesis card is frozen before measurement, and the control set is opened once. A person approves every gate, and the repository history is complete and never rewritten. The reference card contains no numbers without a source. We also run the text of the card through a tool that detects sentences describing a plan as if it were already done.

## Who does what

| Activity | Machine | Person |
|---|---|---|
| Collecting signals | weekly pass over the sources | adds own ideas |
| Selecting candidates | first scoring by several models | decides |
| Hypothesis card | suggests metrics and sample size | writes and approves |
| Experiment | runs, computes, records | rates samples blind |
| Gate | sets the result against the threshold | decides |
| Translation | first version by a local model | corrects |
| Publishing | scans and publishes every fifteen minutes | resolves held files |

## Where things stand today

Most of the cycle described here does not exist yet. Exocortex already has many of the parts it needs: loading content into the graph, finding gaps and contradictions, local models, a bench for comparing configurations. What is missing is a separate lab, the publishing gate, a public repository showing the current state, and support for hypothesis cards. The [roadmap](02-roadmap.md) sets out the build order.
