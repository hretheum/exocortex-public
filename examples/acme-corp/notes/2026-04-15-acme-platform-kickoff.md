---
provenance: ai_authored
provenance_metadata:
  agent: claude-opus-4.7
  session_date: 2026-05-24
  human_validated: false
  session_context: "F31.9.3 example fixture — fictional ACME Corp kickoff meeting"
title: ACME Platform — kickoff
date: 2026-04-15
quarter: 2026-q2
type: meeting_note
client: acme
project: acme-platform
attendees:
  - eryk-orlowski
  - jan-kowalski
  - anna-nowak
tags:
  - acme
  - acme-platform
  - kickoff
  - meeting
---

## Kontekst

Pierwszy oficjalny meeting z ACME Corp po podpisaniu umowy ramowej. Cel: ustalić scope MVP platformy (B2B portal: katalog, ceny dynamiczne, CRM-lite) i kalendarz dostaw na Q2-Q3 2026.

## Decyzje

- **MVP scope**: katalog produktów + dynamiczne ceny per-customer + integracja SSO z istniejącym AD ACME. Bez CRM-lite na pierwszą iterację.
- **Stack**: Next.js 15 + Supabase + Stripe Billing — zgodny z preferencjami ACME IT.
- **Pierwszy release planowany 2026-06-30** (10 tygodni od kickoff).

## Action items

- [ ] Alex — przygotować architecture doc do 2026-04-22 (jan-kowalski review)
- [ ] Jan — udostępnić access do test instancji AD do 2026-04-18
- [ ] Anna — review wzorca cennika z 3 największych klientów ACME do 2026-04-25

## Następny meeting

2026-04-22 — Q3 roadmap workshop.
