---
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  session_date: 2026-05-24
  human_validated: false
  session_context: "F31.9.3 example fixture — ACME decision log entry"
title: Pricing model shift — volume → value-based
date: 2026-04-22
type: decision
client: acme
project: acme-platform
decision_id: ACME-2026-04-22-PRICING
status: approved
stakeholders:
  - jan-kowalski (Head of Product, ACME)
  - piotr-wisniewski (CFO, ACME)
  - eryk-orlowski (vendor lead)
tags:
  - acme
  - decision
  - pricing
  - q3-2026
---

## Decyzja

Przejście z **tiered volume-based pricing** (rabaty 5%/10%/15% per tier MRR) na **value-based pricing** per-customer:

- Cena bazowa zachowana
- Rabaty wyłącznie negocjowane indywidualnie przez sales, z minimum margin gate (18%) enforced w CPQ
- Volume tiery zostają wyłącznie jako trigger do reviewa, nie automatic discount

## Kontekst

Volume rabaty wymknęły się spod kontroli w Q1-Q2 2026 (zob. [[2026-05-01-acme-margin-review]]). Top-3 klienci dostali tier-3 rabaty bez review komercyjnego, łączny impact ~4.2 pkt procentowych margin.

## Alternatywy rozważone

1. **Status quo + tighter tier review** — odrzucone, sales workflow już ma review gate (nie jest egzekwowany).
2. **Pure cost-plus pricing** — odrzucone przez Jana, "kills our differentiation story".
3. **Value-based pricing** — **wybrane** — pozwala sales argue na ROI value vs cost, naturalna margin protection.

## Implementation timeline

- 2026-05-06 — sales retraining plan (Anna)
- 2026-06-15 — value-based pricing financial model finalized (Piotr)
- 2026-08-01 — sales retraining execute
- 2026-08-15 — production rollout (zgodne z [[2026-04-22-acme-q3-roadmap]])

## Powiązane

- [[2026-04-22-acme-q3-roadmap]] — workshop w którym decyzja zapadła
- [[2026-05-01-acme-margin-review]] — primary driver
- [[2026-05-15-acme-quarterly-review]] — Q3 commitments

## Review

Margin impact 90 dni po rollout (2026-11-15) — jeśli margin nie wraca do >=20%, decision reopen.
