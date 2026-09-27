# Attribution

This file lists the concepts, prior art, and third-party software
Exocortex depends on.  Exocortex itself is © 2026 Eryk Orłowski and
Exocortex contributors, licensed under Apache 2.0 + Commons Clause —
see [`LICENSE`](LICENSE) and [`docs/legal/license.md`](docs/legal/license.md).

## Upstream project

  second-brain-instance   © 2026 Eryk Orłowski
                          Private repo from which Exocortex was extracted
                          during F31.7 (Q2 2026).

## Conceptual prior art

Two essays directly shaped the hybrid architecture (append-only graph
store + LLM-synthesised wiki):

  Karpathy, A. (2025). "LLM Wiki for Notion" — short post arguing for
                       an LLM-compiled personal wiki rendered out of a
                       structured store.

  Jones, N. B. (2026). "The hybrid I'd actually build next."
                       Substack, 22 April 2026.  The "Open Brain"
                       pattern of an append-only event log + typed
                       reasoning edges + on-demand synthesis is the
                       foundational shape of Exocortex.

Both essays are referenced extensively in the design docs under
`docs/architecture/`.  Domain modules (FRP, Work, 3D Printing, Home
Automation) are independent plugins built on top of this core.

## Open Source Software

  pgvector            MIT                https://github.com/pgvector/pgvector
                      Vector similarity for Postgres — embeddings index.
  Apache AGE          Apache 2.0         https://age.apache.org
                      Cypher / graph extension for Postgres — typed
                      reasoning edges (Apache Software Foundation).
  PostgreSQL          PostgreSQL License https://www.postgresql.org
                      The underlying database (BSD-style, OSI-approved).
  Model Context       MIT                https://modelcontextprotocol.io
   Protocol (MCP)                        Tool/resource protocol used by
                      © Anthropic, PBC.  the second-brain MCP server.
  Python              PSF License        https://python.org
  Obsidian            Proprietary        https://obsidian.md/license
                      Freeware           Optional client surface — wiki
                      (free, Feb 2025).  output is plain Markdown so any
                                         editor works.
  Anthropic Claude    Commercial ToS     https://www.anthropic.com/legal/commercial-terms
   API                                   LLM provider for synthesis +
                                         GraphRAG `ask`.

---

## Domain: FRP — Inspiration and Academic Sources

_The following attributions are specific to the Futures Reading
Protocol domain module. Other domains do not currently have
external academic grounding requiring attribution._

### Conceptual Inspiration

  Halicki, P. (2025). The Science of Rehearsing the Future:
  How Science Fiction Trains Strategic Imagination.
  Practical Futures White Paper v1.0.
  Licensed under CC BY-NC 4.0.
  https://practicalfutures.com

This project uses different terminology, independently designed
reflection prompts, and an original technical architecture.
It is not affiliated with, endorsed by, or derived from
Practical Futures or Paweł Halicki. Attribution is provided as
a courtesy acknowledging shared intellectual lineage.

### Academic Sources

The following published research informs the FRP domain module's
methodology. No copyrighted content is reproduced; works are
cited for reference only.

  Bal, P. M., & Veltkamp, M. (2013). How does fiction reading
  influence empathy? PLoS ONE, 8(1), e55341.
  https://doi.org/10.1371/journal.pone.0055341

  Baumeister, R. F., Vohs, K. D., & Oettingen, G. (2016).
  Pragmatic prospection. Review of General Psychology, 20(1).
  https://doi.org/10.1037/gpr0000060

  Benoit, R. G., & Schacter, D. L. (2015). Specifying the core
  network supporting episodic simulation. Neuropsychologia, 75.
  https://doi.org/10.1016/j.neuropsychologia.2015.06.034

  Bleecker, J., Foster, N., Girardin, F., & Nova, N. (2022).
  The Manual of Design Fiction. Near Future Laboratory.
  https://nearfuturelaboratory.com

  Braddock, K., & Dillard, J. P. (2016). Meta-analytic evidence
  for the persuasive effect of narratives. Communication
  Monographs, 83(4).
  https://doi.org/10.1080/03637751.2015.1128555

  Candy, S. (2010). The Futures of Everyday Life [Doctoral
  dissertation]. University of Hawaii at Manoa.
  https://doi.org/10.13140/RG.2.1.1840.0248

  Djikic, M., Oatley, K., Zoeterman, S., & Peterson, J. B.
  (2009). Defenseless against art? Journal of Research in
  Personality, 43(1).
  https://doi.org/10.1016/j.jrp.2008.09.003

  Green, M. C., & Brock, T. C. (2000). The role of
  transportation in the persuasiveness of public narratives.
  Journal of Personality and Social Psychology, 79(5), 701–721.
  https://doi.org/10.1037/0022-3514.79.5.701

  Jasanoff, S., & Kim, S.-H. (Eds.). (2015). Dreamscapes of
  Modernity. University of Chicago Press.

  Kaufman, G. F., & Libby, L. K. (2012). Changing beliefs and
  behavior through experience-taking. Journal of Personality
  and Social Psychology, 103(1).
  https://doi.org/10.1037/a0027525

  Kirby, D. A. (2010). The future is now: Diegetic prototypes.
  Social Studies of Science, 40(1).
  https://doi.org/10.1177/0306312709338325

  Klein, G. (1998). Sources of Power: How People Make
  Decisions. MIT Press.

  Mar, R. A., & Oatley, K. (2008). The function of fiction.
  Perspectives on Psychological Science, 3(3).
  https://doi.org/10.1111/j.1745-6924.2008.00073.x

  Mitchell, A. A., & Ivimey-Cook, E. R. (2023).
  Technology-enhanced simulation for healthcare professionals.
  Frontiers in Medicine, 10.
  https://doi.org/10.3389/fmed.2023.1149048

  Mitchell, D. J., Russo, J. E., & Pennington, N. (1989).
  Back to the future. Journal of Behavioral Decision Making,
  2(1). https://doi.org/10.1002/bdm.3960020103

  Oatley, K. (1999). Why fiction may be twice as true as fact.
  Review of General Psychology, 3(2).
  https://doi.org/10.1037/1089-2680.3.2.101

  Peters, J., & Büchel, C. (2010). Episodic future thinking
  reduces reward delay discounting. Neuron, 66(1).
  https://doi.org/10.1016/j.neuron.2010.03.026

  Rohrbeck, R., & Kum, M. E. (2018). Corporate foresight and
  its impact on firm performance. Technological Forecasting and
  Social Change, 129.
  https://doi.org/10.1016/j.techfore.2017.12.013

  Seligman, M. E. P., Railton, P., Baumeister, R. F., &
  Sripada, C. (2016). Homo Prospectus. Oxford University Press.

  Suddendorf, T., Addis, D. R., & Corballis, M. C. (2009).
  Mental time travel. Philosophical Transactions of the Royal
  Society B, 364(1521).
  https://doi.org/10.1098/rstb.2008.0301

  UNESCO. (2024). Futures Literacy and Foresight.
  https://www.unesco.org/en/futures-literacy

  Van Laer, T., De Ruyter, K., Visconti, L. M., & Wetzels, M.
  (2014). The Extended Transportation-Imagery Model. Journal of
  Consumer Research, 40(5).
  https://doi.org/10.1086/673383

  World Economic Forum. (2025). Future of Jobs Report 2025.
  https://www.weforum.org/publications/the-future-of-jobs-report-2025/

  Ye, J.-Y., et al. (2022). A meta-analysis of the effects of
  episodic future thinking on delay discounting. Quarterly
  Journal of Experimental Psychology, 75(10).
  https://doi.org/10.1177/17470218211066282
