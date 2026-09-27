---
title: License explainer (plain language)
---

# License explainer — what Apache 2.0 + Commons Clause means for you

Exocortex is licensed under **Apache License 2.0 with the Commons Clause
applied**.  The full legal text is in
[`LICENSE`](https://github.com/hretheum/exocortex/blob/main/LICENSE).
This
page is a plain-language guide — it is **not** legal advice, but it
should answer 95% of "can I do X?" questions.

The short version: **you can use Exocortex for almost anything except
turning Exocortex itself into a product you sell.**

## What you can do

- ✅ **Run it personally** for your own knowledge work, learning, research.
- ✅ **Modify it.** Fork the repo, change the code, deploy your fork on
  your own infrastructure.  Keep your changes private if you want.
- ✅ **Contribute back.** Open PRs, file issues, write plugins. The
  Apache 2.0 patent grant protects both you and downstream users.
- ✅ **Build commercial products on top of Exocortex** that use it as
  an internal engine — e.g. a SaaS that uses your Exocortex instance
  privately to synthesise data for *your own* customer-facing product.
  The value your customers pay for must come from *your* product, not
  from Exocortex itself.
- ✅ **Use Exocortex internally at a company** for employees' knowledge
  management (free or paid seats inside the company is fine — you're
  not selling Exocortex to those employees).
- ✅ **Use Exocortex in paid consulting work** where the deliverable is
  *your client's* knowledge artefacts (briefs, syntheses, dashboards
  generated from their own data).  You are charging for your domain
  expertise and the artefacts, not for Exocortex.
- ✅ **Sublicense your modifications** to other open-source code under
  Apache 2.0, including the Commons Clause condition.

## What you cannot do

- ❌ **Sell Exocortex itself.**  You cannot offer Exocortex (or a
  rebranded fork of it) as a paid product — boxed software, downloadable
  binaries, mobile app, anything where the buyer is paying for
  Exocortex.
- ❌ **Run Exocortex as a paid SaaS** where the value your customers
  pay for is, "entirely or substantially", the functionality of
  Exocortex itself.  Hosted-Exocortex-as-a-service is the textbook case
  the Commons Clause exists to prevent.
- ❌ **Sell support / consulting where Exocortex *is* the product.**
  Paid "Exocortex consultancy" — implementations, training courses,
  certifications, "Exocortex experts for hire" — falls under the
  Commons Clause's definition of "Sell". (Internal employer-paid use is
  fine; see "What you can do" above.)
- ❌ **Sell hosting where Exocortex is the headline feature.**  A
  generic VPS that happens to come with Exocortex pre-installed is
  fine; a "managed Exocortex hosting" service is not.

## Why this license?

Exocortex is built by one person on weekends.  Apache 2.0 alone makes
that effort easy to fork-and-resell, which would create an asymmetric
incentive: anyone with capital could outpace the original maintainer
in market reach without contributing back.  The Commons Clause keeps
the project genuinely open for users and contributors while reserving
commercialisation of the engine itself for the maintainer.

If your use case is unclear or you want to negotiate a separate
commercial license — open an issue or email the maintainer.

## Related

- [`LICENSE`](https://github.com/hretheum/exocortex/blob/main/LICENSE)
  — full legal text (Apache 2.0 + Commons Clause v1.0).
- [`NOTICE`](https://github.com/hretheum/exocortex/blob/main/NOTICE)
  — required Apache 2.0 attribution notice.
- [`ATTRIBUTION.md`](https://github.com/hretheum/exocortex/blob/main/ATTRIBUTION.md)
  — third-party components and their licenses.
- Commons Clause project page: <https://commonsclause.com/>
