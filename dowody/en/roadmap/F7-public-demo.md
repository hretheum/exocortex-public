---
id: F7
lang: en
counterpart: ../../pl/roadmap/F7-public-demo.md
status: todo
provenance: ai_authored
provenance_metadata: {agent: "Claude Opus 5.5 (Cowork)", date: 2026-09-27, human_validated: false}
---

# F7. Public demo: a knowledge base built from research

[← Roadmap](../02-roadmap.md)

> **Status: to do** · as of 30 September 2026
>
> None of the six tasks has been started (0 of 6 done). The phase can run in parallel with F4 to F6, but it begins after F3, which is in progress. The first step is choosing the domain and sources (F7.1). The demo interface (F7.4) also needs the question service from phase F8, which does not exist yet (F8.3 and F8.4).

## In short

This phase is meant to show in a few minutes what an organisation's knowledge base fed with the results of its research would look like. A program reads reports and research data, extracts findings with verbatim quotes, links them across studies and keeps a list of hypotheses nobody has tested yet.

## Why this phase

In many teams the knowledge from research sits in separate reports. The next project starts from zero, and nobody remembers which study confirmed a finding from another one and which contradicted it. The demo shows on public data what it looks like when every finding has a quote, one can see how many studies stand behind it, and one can also see the questions nobody has tested yet. The domain is meant to be understandable without preparation, for example using public transport or remote work. Qualitative material, of which there is little in public, may be generated, but it is then marked as synthetic and does not count as evidence.

## Goal

Show in a few minutes what an organisational knowledge base fed with research results could look like. The engine reads research reports and data, extracts findings with a verbatim quote, recognises whether a sentence is a finding, a hypothesis, a recommendation or a plan, links findings across studies (supports, contradicts), shows how much evidence stands behind each finding, and keeps a list of hypotheses that nobody has tested yet.

The audience is product teams, researchers and people who run projects. After the demo they should think: this is how we could keep knowledge from our projects, feed it with our own quantitative and qualitative research, and make decisions based on evidence.

The domain should be general and understandable without preparation, for example use of public transport or remote work. The choice is made in F7.1. The demo uses public data only. Qualitative material, of which little is public, can be generated, but then it is clearly marked as synthetic and not counted as evidence.

The phase can run in parallel with F4 to F6, once F3 is finished. The tasks are described here, without separate files.

## The phase is done when

The demo is public in both languages, has been tested with at least three people from the target group, and the guide to feeding it with one's own research is published.

## Tasks

### F7.1. Domain, sources and the demo script

**Status: to do** — not started; waits for F3.

Why: without a chosen domain and legal sources the demo has nothing to run on, and the five-minute script says what we show and in what order.

The choice of domain, a list of sources with their basis for use (open access reports, open quantitative data, possibly synthetic material), a five-minute script: a question, an answer with quotes, open hypotheses, adding a new study, a change on the knowledge map. Done when the description is published and the sources are on the allowlist. Depends on F3.

### F7.2. Research data model

**Status: to do** — not started; waits for F7.1.

Why: it fixes what a study, a finding and an open hypothesis are and how they connect, so that the strength of evidence is computed openly and the same way for every finding.

Nodes: study (quantitative, qualitative or mixed method, sample size, date, source), finding (with quote and mode), open hypothesis, recommendation, project decision. Edges: supports, contradicts, follows from, justifies. A simple measure of evidence strength (number of independent studies, variety of methods, sample sizes), described openly as a heuristic. Done when the schema and its description are published. Depends on F7.1.

### F7.3. Extracting findings and hypotheses from reports

**Status: to do** — not started; waits for F7.2.

Why: the extractor from F3 pulls claims out of text, and here it also learns to recognise sentences that are a hypothesis to test. The task is itself an experiment with a hypothesis card and a decision point G1 after a quick test.

The F3 extractor extended to recognise sentences that can be treated as a research hypothesis to test. This task goes through the cycle itself: hypothesis card, quick test, blind sample rating, gate. Done when the G1 decision is published. Depends on F7.2.

### F7.4. Demo interface

**Status: to do** — not started; waits for F7.3 and F8.4.

Why: on a public page a stranger goes through the script on their own, instead of reading a description of it.

A public page in both languages: knowledge map, a question with an answer and quotes, a list of open hypotheses, contradicting findings, a view of a single study. The "add your own study" mode works in a sandbox, on sample files, with no permanent storage. Done when the F7.1 script can be walked through from start to finish on the public page. Questions and answers with citations use the service and the interface from F8.3 and F8.4 instead of building a second one. Depends on F7.3 and F8.4.

### F7.5. Test with the audience

**Status: to do** — not started; waits for F7.4.

Why: it checks whether the audience understands what they see; without it we do not know whether the demo works outside the team that built it.

Three to five people from the target group go through the script. We check whether they understand what they see and whether they can say how they would feed it with their own research. This part has a hypothesis card too. Session notes are published without personal data. Done when the notes and conclusions are published. Depends on F7.4.

### F7.6. Guide to feeding it with your own research

**Status: to do** — not started; waits for F7.5.

Why: it answers what one needs to feed the engine with one's own research, and what stays private in the organisation.

Which formats the engine accepts, a template for a study report, what a deployment in an organisation looks like and what stays private there. A deployment for a specific organisation is a separate, private project and does not enter the lab. Done when the guide is published in both languages. Depends on F7.5.
