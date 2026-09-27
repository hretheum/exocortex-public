---
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  session_date: 2026-05-24
  human_validated: false
  session_context: "F31.9.3 example fixture — ACME Q3 roadmap workshop"
title: ACME — Q3 2026 roadmap workshop
date: 2026-04-22
quarter: 2026-q2
type: meeting_note
client: acme
project: acme-platform
attendees:
  - eryk-orlowski
  - jan-kowalski
  - anna-nowak
  - piotr-wisniewski
tags:
  - acme
  - acme-platform
  - roadmap
  - decision
  - q3-2026
---

## Kontekst

Workshop z Janem (Head of Product) i Piotrem (CFO) — zaplanowanie Q3. Centralna decyzja: pivot z volume-based pricing na value-based pricing (zob. [[2026-04-22-pricing-model-shift]]).

## Decyzje

- **Pricing model shift**: porzucamy tiered volume rabaty, wprowadzamy value-based pricing per-customer (margin protection w Q3-Q4).
- **acme-revamp** — nowy sub-projekt: refactor istniejącego portalu legacy do podejścia headless commerce. Discovery start 2026-05-08, decyzja go/no-go po discovery.
- **Q3 milestones**: MVP go-live 2026-06-30, value-pricing rollout 2026-08-15, revamp decision gate 2026-09-15.

## Ryzyka zidentyfikowane

- Margin pressure w Q3 — patrz [[2026-05-01-acme-margin-review]].
- Capacity team Alexa — może wymagać +1 dev jeśli revamp dostanie zielone światło.

## Action items

- [ ] Piotr — projection margin Q3 z 3 scenariuszami pricing do 2026-04-29
- [ ] Alex — proposal acme-revamp scope + kosztorys do 2026-05-08
- [ ] Anna — communications draft dla największych klientów ACME (zmiana cennika) do 2026-05-06
