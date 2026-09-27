---
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  session_date: 2026-05-24
  human_validated: false
  session_context: "F31.9.3 example fixture — acme-revamp discovery kickoff"
title: ACME Revamp — discovery kickoff
date: 2026-05-08
quarter: 2026-q2
type: meeting_note
client: acme
project: acme-revamp
attendees:
  - eryk-orlowski
  - jan-kowalski
  - tomasz-mazur
tags:
  - acme
  - acme-revamp
  - discovery
  - headless-commerce
  - meeting
---

## Kontekst

Start sub-projektu **acme-revamp** — discovery 4 tygodnie (2026-05-08 → 2026-06-05), decision gate 2026-09-15. Cel discovery: ocenić koszt + ryzyko refaktoru istniejącej platformy legacy do headless commerce.

## Założenia in scope

- Frontend: Next.js 15 App Router + RSC (zgodne z acme-platform MVP).
- Backend: Medusa.js jako headless commerce engine + custom microservices dla pricing engine.
- Migration path: strangler-fig — gradually moving traffic z legacy do nowego stacka, no big-bang.

## Założenia out of scope (na razie)

- Mobile native app — odkładamy do 2027.
- B2C kanał — ACME pozostaje B2B-only.

## Stakeholders + ryzyka

- Tomasz Mazur (Head of Engineering, ACME) — sceptyczny wobec Medusa.js, preferuje Shopify Plus. Risk: technology buy-in.
- Jan Kowalski (Head of Product) — pełen support, ale chce pierwszy prototype za 6 tygodni (vs 12 zakładanych).
- Budget cap z Piotra (CFO): $180k discovery + first MVP iteration, nie więcej. Powiązane z [[2026-05-01-acme-margin-review]] — discretionary spend ograniczone do czasu rozwiązania margin pressure.

## Action items

- [ ] Alex — competitive analysis Medusa vs Shopify Plus vs Saleor do 2026-05-15
- [ ] Tomasz — share existing legacy portal access + production data sample (anonimowy)
- [ ] Jan — prepare user research recruitment dla 8 customer interviews
