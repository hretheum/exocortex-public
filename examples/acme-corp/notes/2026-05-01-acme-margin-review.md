---
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  session_date: 2026-05-24
  human_validated: false
  session_context: "F31.9.3 example fixture — ACME margin pressure analysis"
title: ACME — Q3 margin pressure review
date: 2026-05-01
quarter: 2026-q2
type: problem_note
client: acme
project: acme-platform
tags:
  - acme
  - margin-pressure
  - q3-2026
  - cfo-review
  - problem
---

## Problem

Q3 2026 projection margin dla ACME platformy: **15.4%** (vs 22% target z umowy ramowej, vs 19% Q2). Trzy główne drivery spadku:

1. **Volume rabaty wymknęły się spod kontroli** — top-3 klienci ACME (CarrefourPL, Auchan, Selgros) dostali tier-3 rabaty (-12%) bez review komercyjnego. Łączny impact: ~4.2 pkt procentowych margin.
2. **Stripe processing fees** — przeskoczyliśmy próg $500k MRR, ale negotiable Stripe rate (1.4% + $0.25 vs default 2.9%) nie został jeszcze włączony. Impact: ~1.8 pkt.
3. **Engineering allocation** — 35% capacity Alexa idzie na bug fixes w legacy portal (ten sam który chcemy zrewampować). Impact: ~2.1 pkt.

## Decyzja (do 2026-05-08)

CFO ACME (Piotr) wymaga remediation planu do Q3 forecast meeting. Trzy opcje:

- **Pricing model shift** (decision z [[2026-04-22-acme-q3-roadmap]]): value-based pricing zatrzymuje volume erosion ale wymaga sales retraining.
- **Stripe renegotiation**: szybki win (~3 tygodnie), bez sales impact.
- **Engineering reallocation**: dolożenie +1 dev z bench pozwoli wycofać Alexa z bug-fix loop'a; wymaga budget approval $14k/m.

## Powiązania

- Wpływa na decyzję [[2026-04-22-pricing-model-shift]] — value-based pricing to long-term answer, ale Stripe renegotiation to quick win na Q3.
- Powiązane z [[2026-05-08-acme-revamp-discovery]] — revamp likwiduje bug-fix loop, ale dopiero w 2027.

## Action items

- [ ] Alex — propose Stripe renegotiation timeline do 2026-05-04 (talk track + projected savings)
- [ ] Piotr — financial model dla +1 dev allocation do 2026-05-05
- [ ] Anna — sales retraining plan dla value-based pricing do 2026-05-10
