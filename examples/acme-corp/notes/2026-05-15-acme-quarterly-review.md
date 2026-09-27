---
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  session_date: 2026-05-24
  human_validated: false
  session_context: "F31.9.3 example fixture — ACME quarterly review (cross-cutting)"
title: ACME — Q2 quarterly review
date: 2026-05-15
quarter: 2026-q2
type: quarterly_review
client: acme
attendees:
  - eryk-orlowski
  - jan-kowalski
  - anna-nowak
  - piotr-wisniewski
  - tomasz-mazur
tags:
  - acme
  - quarterly-review
  - cross-cutting
  - q2-2026
  - decision
---

## Q2 retrospektywa (2026-02 → 2026-05)

### Co poszło dobrze

- **Kickoff acme-platform** ([[2026-04-15-acme-platform-kickoff]]) — bez slippage, pierwsze deliverables (architecture doc, SSO POC) on time.
- **Q3 roadmap** ([[2026-04-22-acme-q3-roadmap]]) — clear scope dla MVP go-live 2026-06-30.
- **Discovery acme-revamp** start ([[2026-05-08-acme-revamp-discovery]]) — Tomasz onboardował się szybciej niż oczekiwaliśmy mimo sceptycyzmu wobec Medusa.

### Co poszło źle

- **Margin pressure** ([[2026-05-01-acme-margin-review]]) — 15.4% vs 22% target. Trzy drivery (volume rabaty, Stripe fees, engineering allocation) zidentyfikowane, remediation w trakcie.
- **Sales communication** — kommunikacja zmiany cennika do CarrefourPL/Auchan/Selgros opóźniona o 2 tygodnie. Anna pracuje nad recovery.

## Decyzje Q3 (cross-cutting)

- **Pricing model shift** ([[2026-04-22-pricing-model-shift]]) — go-live 2026-08-15, zgodnie z decyzją Q3 workshop.
- **Stripe renegotiation** — priorytetyzowane jako Q3 quick win (zob. action item Alexa w [[2026-05-01-acme-margin-review]]).
- **acme-revamp gate** — decision 2026-09-15, na podstawie outcomu discovery + margin recovery.

## Stakeholder sentiment

- Piotr (CFO): cautious — wymaga monthly margin update, nie quarterly.
- Jan (Head of Product): optymistyczny, ale presuje na faster revamp timeline.
- Tomasz (Head of Engineering, ACME): warming up to Medusa, ale chce dual-track (Medusa + Shopify Plus PoC równolegle, decyzja w decision gate).

## Action items Q3

- [ ] Alex — monthly margin dashboard + Stripe negotiation kickoff do 2026-05-30
- [ ] Piotr — value-based pricing financial model finalize do 2026-06-15
- [ ] Anna — sales retraining program execute do 2026-08-01
- [ ] Tomasz — Shopify Plus PoC scope do 2026-06-01 (parallel z Medusa discovery)
