-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- schema/41_corpus_synthesis_perspectives.sql — zadanie-19-synteza-korpusu.md.
-- Extend syntheses.perspective_type CHECK to allow 'area_digest' and
-- 'backlog_health' — same additive pattern as 14/15/28 (FRP, news_cluster,
-- night_shift_briefing/globex_*). Zero data migration: purely widens the
-- allowed value set, no existing rows touched.
--
-- Diagnosis + design: docs/synteza/DIAGNOZA.md, docs/synteza/PERSPEKTYWY.md.
-- area_digest    — one synthesis per vault_note metadata.section_path[1].
-- backlog_health — one synthesis per backlog_item metadata.area.

ALTER TABLE syntheses DROP CONSTRAINT IF EXISTS syntheses_perspective_type_check;

ALTER TABLE syntheses ADD CONSTRAINT syntheses_perspective_type_check
  CHECK (perspective_type IN (
    'client', 'project', 'person', 'monthly', 'tag', 'type',
    'frp_per_frame', 'frp_per_domain', 'frp_evolution_timeline',
    'frp_per_resonance', 'frp_monthly',
    'news_cluster',
    'globex_pillar', 'globex_topic', 'globex_concept',
    'night_shift_briefing',
    'gap_radar',
    'area_digest', 'backlog_health'
  ));
