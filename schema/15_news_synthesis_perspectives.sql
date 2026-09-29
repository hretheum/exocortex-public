-- © 2026 Exocortex contributors. Licence: MIT. See LICENSE-CODE.
-- Schema F8.8.x.B — extend syntheses.perspective_type CHECK to allow news_cluster.
-- Apply on the server: sudo -u postgres psql -d second_brain -f /tmp/15_news_synthesis_perspectives.sql

ALTER TABLE syntheses
  DROP CONSTRAINT IF EXISTS syntheses_perspective_type_check;

ALTER TABLE syntheses
  ADD CONSTRAINT syntheses_perspective_type_check
  CHECK (perspective_type = ANY (ARRAY[
    'client'::text,
    'project'::text,
    'person'::text,
    'monthly'::text,
    'tag'::text,
    'type'::text,
    -- F7.3 — FRP synthesizer perspectives
    'frp_per_frame'::text,
    'frp_per_domain'::text,
    'frp_evolution_timeline'::text,
    'frp_per_resonance'::text,
    'frp_monthly'::text,
    -- F8.8.x.B — newsletter cluster synthesis (one per news_topic_clusters.yaml cluster)
    'news_cluster'::text
  ]));

