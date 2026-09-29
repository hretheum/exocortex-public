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

## Goal

Show in a few minutes what an organisational knowledge base fed with research results could look like. The engine reads research reports and data, extracts findings with a verbatim quote, recognises whether a sentence is a finding, a hypothesis, a recommendation or a plan, links findings across studies (supports, contradicts), shows how much evidence stands behind each finding, and keeps a list of hypotheses that nobody has tested yet.

The audience is product teams, researchers and people who run projects. After the demo they should think: this is how we could keep knowledge from our projects, feed it with our own quantitative and qualitative research, and make decisions based on evidence.

The domain should be general and understandable without preparation, for example use of public transport or remote work. The choice is made in F7.1. The demo uses public data only. Qualitative material, of which little is public, can be generated, but then it is clearly marked as synthetic and not counted as evidence.

The phase can run in parallel with F4 to F6, once F3 is finished. The tasks are described here, without separate files.

## The phase is done when

The demo is public in both languages, has been tested with at least three people from the target group, and the guide to feeding it with one's own research is published.

## Tasks

### F7.1. Domain, sources and the demo script

The choice of domain, a list of sources with their basis for use (open access reports, open quantitative data, possibly synthetic material), a five-minute script: a question, an answer with quotes, open hypotheses, adding a new study, a change on the knowledge map. Done when the description is published and the sources are on the allowlist. Depends on F3.

### F7.2. Research data model

Nodes: study (quantitative, qualitative or mixed method, sample size, date, source), finding (with quote and mode), open hypothesis, recommendation, project decision. Edges: supports, contradicts, follows from, justifies. A simple measure of evidence strength (number of independent studies, variety of methods, sample sizes), described openly as a heuristic. Done when the schema and its description are published. Depends on F7.1.

### F7.3. Extracting findings and hypotheses from reports

The F3 extractor extended to recognise sentences that can be treated as a research hypothesis to test. This task goes through the cycle itself: hypothesis card, quick test, blind sample rating, gate. Done when the G1 decision is published. Depends on F7.2.

### F7.4. Demo interface

A public page in both languages: knowledge map, a question with an answer and quotes, a list of open hypotheses, contradicting findings, a view of a single study. The "add your own study" mode works in a sandbox, on sample files, with no permanent storage. Done when the F7.1 script can be walked through from start to finish on the public page. Questions and answers with citations use the service and the interface from F8.3 and F8.4 instead of building a second one. Depends on F7.3 and F8.4.

### F7.5. Test with the audience

Three to five people from the target group go through the script. We check whether they understand what they see and whether they can say how they would feed it with their own research. This part has a hypothesis card too. Session notes are published without personal data. Done when the notes and conclusions are published. Depends on F7.4.

### F7.6. Guide to feeding it with your own research

Which formats the engine accepts, a template for a study report, what a deployment in an organisation looks like and what stays private there. A deployment for a specific organisation is a separate, private project and does not enter the lab. Done when the guide is published in both languages. Depends on F7.5.
