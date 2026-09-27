-- schema/28_night_shift_perspective.sql — F31.1.3
-- Extend syntheses.perspective_type CHECK to allow 'night_shift_briefing'.
-- Applied after 27_notify_triggers.sql.

ALTER TABLE syntheses DROP CONSTRAINT IF EXISTS syntheses_perspective_type_check;

ALTER TABLE syntheses ADD CONSTRAINT syntheses_perspective_type_check
  CHECK (perspective_type IN (
    'client', 'project', 'person', 'monthly', 'tag', 'type',
    'frp_per_frame', 'frp_per_domain', 'frp_evolution_timeline',
    'frp_per_resonance', 'frp_monthly',
    'news_cluster',
    'globex_pillar', 'globex_topic', 'globex_concept',
    'night_shift_briefing'
  ));
